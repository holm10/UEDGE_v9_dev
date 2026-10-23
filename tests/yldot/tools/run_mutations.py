"""Run the yldot suite's mutation set and write the coverage matrix (epic AIUE-9, PRD sections 7.8 and 7.11 (c),
decision 25; AIUE-90).

Usage (from a checkout whose tests/yldot is the commit's, references/ aside):
    python run_mutations.py list
    python run_mutations.py run --out DIR [--from-commit SHA] [mutation ...]
    python run_mutations.py gates DIR
    <built python> run_mutations.py _child --families F [F ...] --out FILE [--locality]

list      parses and checks every tests/yldot/mutations/*.patch (header keys, the single-line diff, the families and
          blocks against the stored references) and prints the set.
run       applies the mutations (default: all) one at a time to a scratch worktree DIR/src of SHA (default HEAD) and
          builds each --serial into one venv DIR/venv (make_references.PINS). First a baseline build of SHA: every
          referenced family must pass. Per mutation: git apply, build (DIR/<mutation>/build.log), the built bbbpy
          extension's SHA-256 must be new in the run (a stale build fails it), the evaluations, test_default.py with
          the built python as a cross-check (and test_locality.py for a range mutation), git apply -R, the scratch
          tree clean again. The locality check runs only for a mutation whose Check is locality (owner, 2026-10-22,
          AIUE-100 D4), and only in families with [locality] (owner, 2026-10-23, AIUE-92: the owner families have
          none); elsewhere the part is absent ("not run"). Inner-loop rule: the
          mutation's first family (the smallest referenced family where its code is active) runs first; a verdict
          other than expected there stops the mutation (its other families: not run). Otherwise every other
          referenced family runs, active or not (owner, 2026-10-22, AIUE-90 Q8: a block firing where the code is
          inactive is unexpected). Pending mutations run on every referenced family as negative controls (Q6).
          Writes DIR/matrix.json after each mutation, then DIR/matrix.md, and prints the gates.
gates     recomputes and prints the gates of DIR/matrix.json.
_child    runs inside the built venv: per family and configuration one fresh evaluation, decided by Store.check as
          test_default.py decides it, with the fired blocks, failing cells and largest |diff|/tol per part (yldot,
          flag difference) and the first differing intermediate (array-scaled, as Store.check's report). With
          --locality also the steady part locality, decided by locality.compare_pattern as test_locality.py decides
          it (fired blocks: those of the failing rows; largest ratio: score/M_loc, 1/score or the magnitude ratio).

The matrix (owner, 2026-10-22, AIUE-90 Q5) is a working document: summarise it on the ticket page, never commit it.

Header of a mutation patch (`Key: value`; a line starting with a space continues the previous key, one family per
line for Blocks and Cells), a blank line, then the single-line `git diff` (git apply skips the header):
    Mutation      the file's stem
    Kind          physics | range | flag-gating
    Equation      ni | up | te | ti | ng | tg | phi; or all (range and flag-gating only)
    Fault         sign | factor 2 | dropped term | off-by-one | wrong multiplier | loop bound | window coupling |
                  gating
    Check         yldot | flag difference | locality (physics: yldot; flag-gating: flag difference; range: locality)
    Configs       the configurations where the check fires (steady, timestep)
    Blocks        <family>: primary <eq[sp]>, ...[; coupled <eq[sp]>, ...]: the blocks that must fire (primary) and
                  may fire (coupled); optional for a pending mutation
    Cells         optional, <family>: <eq[sp]> (ix,iy), ...: the primary block fails only in these cells
    Intermediate  the first differing intermediate expected (a residual array), or none; then optional per-family
                  exceptions approved by the epic owner, `; <family>: <array or none> (<who, date, why>)`
    Families      the families where the code is active, the inner-loop family first
    Pending       optional, AIUE-<n>[, AIUE-<n>] (<reason>): the ticket whose check will catch it
    Source        <file>:<line> (at <sha>), the mutated line
    Description   free text
Species are Fortran's 1-based ifld/igsp.

Exit codes: 0 the gates pass (run, gates) or the set is valid (list); 1 refused (an invalid set, a tree that differs
from SHA, absent references); 2 usage, a failed build or a harness error; 3 the epic owner (a mutation missed, firing
unexpectedly, crashing, or flagged: decision 23).
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # tests/, for the yldot package
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tools/, for make_references

import make_references as mr  # noqa: E402

from yldot.harness import manifest as mf  # noqa: E402
from yldot.harness.compare import EQUATIONS  # noqa: E402

SUITE = Path(__file__).resolve().parents[1]
MUTATIONS = SUITE / "mutations"
FAMILIES = SUITE / "families"
CONFIGS = ("steady", "timestep")
PARTS = ("yldot", "flag difference", "locality")  # locality: steady only, for Check: locality (owner, AIUE-100 D4)
DEFAULT_PARTS = PARTS[:2]  # the parts test_default.py decides
EQ_NAMES = tuple(e for e, _, _ in EQUATIONS)
KINDS = {"physics": "yldot", "flag-gating": "flag difference", "range": "locality"}  # kind -> its check
FAULTS = ("sign", "factor 2", "dropped term", "off-by-one", "wrong multiplier", "loop bound", "window coupling",
          "gating")
REQUIRED = ("Mutation", "Kind", "Equation", "Fault", "Check", "Configs", "Intermediate", "Families", "Source",
            "Description")
OPTIONAL = ("Blocks", "Cells", "Pending")
LIST_KEYS = ("Blocks", "Cells")  # one entry per line
BLOCK_RE = re.compile(r"^([a-z]+)\[(\d+)\]$")
CELL_RE = re.compile(r"\((\d+),(\d+)\)")
SOURCE_RE = re.compile(r"^(\S+):(\d+) \(at ([0-9a-f]{7,40})\)$")
PENDING_RE = re.compile(r"^AIUE-\d+(, AIUE-\d+)* \(.+\)$")
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")
# the set PRD 7.8 fixes (decision 25; owner, 2026-10-22, AIUE-90 Q2: the quiet-cell mutation is one of the 21)
COMPOSITION = {"physics": 23, "range": 2, "flag-gating": 2}
OWNER = "a gate failed: ask the epic owner (decision 23); never tune a tolerance, header or site to pass"


class Stop(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- the patch set


@dataclass
class Mutation:
    path: Path
    keys: dict
    diff: str
    name: str = ""
    kind: str = ""
    equation: str = ""
    fault: str = ""
    check: str = ""
    configs: list = field(default_factory=list)
    blocks: dict = field(default_factory=dict)  # {family: {"primary": [...], "coupled": [...]}}
    cells: dict = field(default_factory=dict)  # {family: (block, [(ix, iy), ...])}
    intermediate: str = ""
    intermediate_by: dict = field(default_factory=dict)  # {family: array or none}, owner-approved exceptions
    families: list = field(default_factory=list)
    pending: str = None
    source: tuple = None  # (file, line, sha)

    def summary(self):
        return {"kind": self.kind, "equation": self.equation, "fault": self.fault, "check": self.check,
                "configs": self.configs, "families": self.families, "pending": self.pending,
                "intermediate": self.intermediate, "intermediate_by": self.intermediate_by, "blocks": self.blocks,
                "cells": {f: [b, [list(c) for c in cells]] for f, (b, cells) in self.cells.items()},
                "source": "{}:{}".format(*self.source[:2]) if self.source else None}


def split_list(value):
    return [v.strip() for v in value.split(",") if v.strip()]


def parse_header(text):
    """{key: value} (a list of lines for Blocks and Cells), the diff body; ValueError on a malformed header."""
    head, sep, body = text.partition("\n\n")
    if not sep or not body.startswith("diff --git "):
        raise ValueError("no blank line followed by a git diff")
    keys, last = {}, None
    for line in head.splitlines():
        if line.startswith(" "):
            if last is None:
                raise ValueError("continuation line before any key: {!r}".format(line))
            if last in LIST_KEYS:
                keys[last].append(line.strip())
            else:
                keys[last] += " " + line.strip()
            continue
        key, colon, value = line.partition(": ")
        if not colon or not re.match(r"^[A-Z][a-z]+$", key):
            raise ValueError("not a `Key: value` line: {!r}".format(line))
        if key in keys:
            raise ValueError("key {} twice".format(key))
        keys[key] = [value.strip()] if key in LIST_KEYS else value.strip()
        last = key
    return keys, body


def parse_blocks(entries):
    out = {}
    for entry in entries:
        family, _, rest = entry.partition(": ")
        primary, _, coupled = rest.partition("; coupled ")
        if not primary.startswith("primary "):
            raise ValueError("Blocks entry {!r}: need `<family>: primary <blocks>[; coupled <blocks>]`".format(entry))
        if family in out:
            raise ValueError("Blocks: family {} twice".format(family))
        out[family] = {"primary": split_list(primary[len("primary "):]), "coupled": split_list(coupled)}
    return out


def parse_cells(entries):
    out = {}
    for entry in entries:
        family, _, rest = entry.partition(": ")
        block, _, cells = rest.partition(" ")
        found = [(int(a), int(b)) for a, b in CELL_RE.findall(cells)]
        if not found:
            raise ValueError("Cells entry {!r}: need `<family>: <eq[sp]> (ix,iy), ...`".format(entry))
        out[family] = (block, found)
    return out


def parse_intermediate(value):
    """(the expected intermediate, {family: exception}) of an Intermediate value."""
    default, *rest = value.split("; ")
    out = {}
    for entry in rest:
        hit = re.match(r"^(\w+): (\w+) \((.+)\)$", entry)
        if not hit:
            raise ValueError("Intermediate exception {!r}: need `<family>: <array or none> (<who, date, why>)`".format(
                entry))
        out[hit.group(1)] = hit.group(2)
    return default, out


def load(path):
    """The Mutation of one patch file; ValueError on a malformed file."""
    keys, body = parse_header(Path(path).read_text())
    m = Mutation(Path(path), keys, body)
    missing = [k for k in REQUIRED if k not in keys]
    unknown = [k for k in keys if k not in REQUIRED + OPTIONAL]
    if missing or unknown:
        raise ValueError("keys missing {}, unknown {}".format(missing, unknown))
    m.name, m.kind, m.equation, m.fault = keys["Mutation"], keys["Kind"], keys["Equation"], keys["Fault"]
    m.check = keys["Check"]
    m.intermediate, m.intermediate_by = parse_intermediate(keys["Intermediate"])
    m.configs, m.families = split_list(keys["Configs"]), split_list(keys["Families"])
    m.blocks = parse_blocks(keys.get("Blocks", []))
    m.cells = parse_cells(keys.get("Cells", []))
    m.pending = keys.get("Pending")
    hit = SOURCE_RE.match(keys["Source"])
    if not hit:
        raise ValueError("Source {!r}: need `<file>:<line> (at <sha>)`".format(keys["Source"]))
    m.source = (hit.group(1), int(hit.group(2)), hit.group(3))
    return m


def mutation_paths():
    return sorted(MUTATIONS.glob("*.patch"))


def diff_line(body):
    """(file, old line number) of the single changed line of a one-hunk diff; ValueError otherwise."""
    files = re.findall(r"^diff --git a/(\S+) b/(\S+)$", body, re.MULTILINE)
    if len(files) != 1 or files[0][0] != files[0][1]:
        raise ValueError("the diff must change exactly one file, got {}".format(files))
    lines = body.splitlines()
    hunks = [i for i, l in enumerate(lines) if l.startswith("@@")]
    if len(hunks) != 1:
        raise ValueError("the diff must have exactly one hunk, got {}".format(len(hunks)))
    old = int(HUNK_RE.match(lines[hunks[0]]).group(1))
    removed, added = [], 0
    for l in lines[hunks[0] + 1:]:
        if l.startswith("-"):
            removed.append(old)
            old += 1
        elif l.startswith("+"):
            added += 1
        elif l.startswith(" ") or l == "":
            old += 1
        elif not l.startswith("\\"):
            raise ValueError("unexpected diff line {!r}".format(l))
    if len(removed) != 1 or added > 1:
        raise ValueError("the diff must remove one line and add at most one: -{} +{}".format(len(removed), added))
    return files[0][0], removed[0]


def problems(m, stores=None):
    """Every defect of one mutation's header and diff. stores: {family: {"neq": n, "blocks": [eq[sp], ...]}} of the
    referenced families (the inner-loop order and the blocks are checked against them)."""
    out = []
    if m.name != m.path.stem:
        out.append("Mutation {} is not the file's stem {}".format(m.name, m.path.stem))
    if m.kind not in KINDS:
        out.append("Kind {!r} not in {}".format(m.kind, sorted(KINDS)))
    elif m.check != KINDS[m.kind]:
        out.append("Check {!r}: a {} mutation is caught by {!r}".format(m.check, m.kind, KINDS[m.kind]))
    if m.equation not in EQ_NAMES and not (m.equation == "all" and m.kind != "physics"):
        out.append("Equation {!r} not in {} (all: range and flag-gating only)".format(m.equation, EQ_NAMES))
    if m.fault not in FAULTS:
        out.append("Fault {!r} not in {}".format(m.fault, FAULTS))
    if not m.configs or set(m.configs) - set(CONFIGS):
        out.append("Configs {} not a subset of {}".format(m.configs, CONFIGS))
    if not m.families or len(set(m.families)) != len(m.families):
        out.append("Families {} empty or repeated".format(m.families))
    for f in m.families:
        if not (FAMILIES / f / "input.py").is_file():
            out.append("Families: no family {}".format(f))
    if m.pending is not None and not PENDING_RE.match(m.pending):
        out.append("Pending {!r}: need `AIUE-<n>[, AIUE-<n>] (<reason>)`".format(m.pending))
    if not m.blocks and m.pending is None:
        out.append("Blocks missing (only a pending mutation may leave them out)")
    if m.blocks and list(m.blocks) != m.families:
        out.append("Blocks name the families {}, Families {} (same order)".format(list(m.blocks), m.families))
    for f, b in m.blocks.items():
        if not b["primary"]:
            out.append("Blocks {}: no primary block".format(f))
        for label in b["primary"] + b["coupled"]:
            hit = BLOCK_RE.match(label)
            if not hit or hit.group(1) not in EQ_NAMES:
                out.append("Blocks {}: {!r} is not eq[species]".format(f, label))
            elif stores and f in stores and label not in stores[f]["blocks"]:
                out.append("Blocks {}: {} is not a block of the family's reference".format(f, label))
        if set(b["primary"]) & set(b["coupled"]):
            out.append("Blocks {}: {} both primary and coupled".format(f, sorted(set(b["primary"]) & set(b["coupled"]))))
    for f in m.intermediate_by:
        if f not in m.families:
            out.append("Intermediate: exception for {}, which is not in Families".format(f))
    for f, (block, _) in m.cells.items():
        if f not in m.blocks or block not in m.blocks[f]["primary"]:
            out.append("Cells {}: {} is not a primary block of that family".format(f, block))
    if stores and m.pending is None:
        active = [f for f in m.families if f in stores]
        if not active:
            out.append("Families: no referenced family, so the mutation can't run: mark it Pending")
        elif m.families[0] not in stores or stores[m.families[0]]["neq"] > min(stores[f]["neq"] for f in active):
            out.append("Families: the inner-loop family {} is not the smallest referenced one ({})".format(
                m.families[0], min(active, key=lambda f: stores[f]["neq"])))
    try:
        path, line = diff_line(m.diff)
        if (path, line) != m.source[:2]:
            out.append("Source {}:{} but the diff changes {}:{}".format(m.source[0], m.source[1], path, line))
    except ValueError as e:
        out.append(str(e))
    return out


def composition(ms):
    """Defects of the set as a whole (PRD 7.8: 27 patches; 7 equations x sign, factor 2, dropped term)."""
    out = []
    kinds = {k: sum(m.kind == k for m in ms) for k in COMPOSITION}
    if kinds != COMPOSITION:
        out.append("kinds {} differ from {}".format(kinds, COMPOSITION))
    for eq in EQ_NAMES:
        faults = sorted(m.fault for m in ms if m.kind == "physics" and m.equation == eq
                        and m.fault in ("sign", "factor 2", "dropped term"))
        if faults != ["dropped term", "factor 2", "sign"]:
            out.append("{}: physics faults {}, need one sign, one factor 2, one dropped term".format(eq, faults))
    for fault in ("off-by-one", "wrong multiplier"):
        n = sum(m.kind == "physics" and m.fault == fault for m in ms)
        if n != 1:
            out.append("{} physics {} mutations, need 1".format(n, fault))
    return out


def referenced():
    """The families whose manifest names a reference file (as test_default.py)."""
    names = sorted(p.name for p in FAMILIES.iterdir() if (p / "input.py").is_file())
    return [f for f in names if mf.path(f).is_file() and mf.reference_path(f) in mf.load(f)["external"]]


def store_facts(families):
    """{family: {"neq", "blocks", "equations"}} from the stored references."""
    from yldot.harness import open_store

    out = {}
    for f in families:
        with open_store(f) as s:
            blocks = ["{}[{}]".format(e, sp) for e, sp in s.imap.blocks()]
            out[f] = {"neq": int(s.imap.neq), "blocks": blocks, "equations": sorted({b.split("[")[0] for b in blocks})}
    return out


def load_set(names=None, stores=None):
    """The mutations (all, or the named ones), checked; Stop(1) on any defect."""
    ms, bad = [], []
    for p in mutation_paths():
        try:
            ms.append(load(p))
        except ValueError as e:
            bad.append("{}: {}".format(p.name, e))
    for m in ms:
        bad += ["{}: {}".format(m.path.name, e) for e in problems(m, stores)]
    if names is None:
        bad += composition(ms)
    if bad:
        raise Stop(1, "invalid mutation set:\n  " + "\n  ".join(bad))
    if names:
        unknown = sorted(set(names) - {m.name for m in ms})
        if unknown:
            raise Stop(2, "no mutation {}".format(unknown))
        ms = [m for m in ms if m.name in names]
    return ms


# ---------------------------------------------------------------- verdicts and gates


def fired(result):
    """{(config, part): {block: [cells]}} of one family's child result (configs that ran)."""
    out = {}
    for config, r in result.items():
        if r.get("status") != "ok":
            continue
        for part, p in r["parts"].items():
            if p["n_fail"]:
                out[(config, part)] = p["cells"]
    return out


def verdict(m, family, result, junit=None, junit_loc=None):
    """{"verdict", "problems", "flags"} of one mutation on one family. result: the child's {config: ...}; junit: the
    test_default.py outcome {config: failed} for the family (None: not run); junit_loc: the test_locality.py outcome
    (failed: bool) for the family (None: not run)."""
    crashed = ["{}: {} {}".format(c, r.get("status"), r.get("message", "")) for c, r in result.items()
               if r.get("status") != "ok"]
    if crashed:
        return {"verdict": "crash", "problems": crashed, "flags": []}
    got = fired(result)
    flags = []
    if junit is not None:
        for config in CONFIGS:
            fails = any(part in DEFAULT_PARTS for (c, part) in got if c == config)
            if junit.get(config) != fails:
                flags.append("test_default[{}-{}] {} while the check {}".format(
                    family, config, "failed" if junit.get(config) else "passed", "fired" if fails else "passed"))
    if junit_loc is not None:
        fails = ("steady", "locality") in got
        if junit_loc != fails:
            flags.append("test_locality[{}] {} while the check {}".format(
                family, "failed" if junit_loc else "passed", "fired" if fails else "passed"))
    active = family in m.families and m.pending is None
    if not active:
        if not got:
            return {"verdict": "quiet", "problems": [], "flags": flags}
        return {"verdict": "unexpected", "flags": flags, "problems": [
            "{} {} fired {} where the mutation is {}".format(c, p, sorted(b), "pending" if m.pending else "inactive")
            for (c, p), b in sorted(got.items())]}
    want = m.blocks[family]
    allowed = set(want["primary"]) | set(want["coupled"])
    probs, caught = [], 0
    for config in CONFIGS:
        for part in PARTS:
            blocks = got.get((config, part))
            if config in m.configs and part == m.check:
                if not blocks:
                    probs.append("{} {}: nothing fired".format(config, part))
                    continue
                caught += 1
                missing = sorted(set(want["primary"]) - set(blocks))
                extra = sorted(set(blocks) - allowed)
                if missing:
                    probs.append("{} {}: primary {} did not fire".format(config, part, missing))
                if extra:
                    probs.append("{} {}: {} fired outside primary and coupled".format(config, part, extra))
                if family in m.cells:
                    block, cells = m.cells[family]
                    outside = sorted({tuple(c) for c in blocks.get(block, [])} - set(cells))
                    if outside:
                        probs.append("{} {}: {} failed in cells {} outside {}".format(config, part, block, outside,
                                                                                     cells))
                if part == "yldot":
                    first = result[config].get("intermediate")
                    want_first = m.intermediate_by.get(family, m.intermediate)
                    if (first or "none") != want_first:
                        flags.append("{}: first differing intermediate {}, expected {}".format(
                            config, first, want_first))
            elif blocks:
                probs.append("{} {} fired {} (not the expected check or configuration)".format(config, part,
                                                                                           sorted(blocks)))
    if caught == 0 and not [p for p in probs if "nothing fired" not in p]:
        return {"verdict": "missed", "problems": probs, "flags": flags}
    return {"verdict": "unexpected" if probs else "expected", "problems": probs, "flags": flags}


def gates(matrix):
    """[(gate, ok, detail)] of PRD 7.11 (c) over the matrix: G1 every non-pending mutation expected on a family;
    G2 nothing missed, unexpected, crashed or flagged, and no non-pending mutation left unrun; G3 every equation with
    a block in some referenced family caught by a mutation of that equation (its Equation key), in a primary block
    of it; G4 every referenced family catches a mutation. G3 and G4 judge the whole set: a run of named mutations
    (matrix["partial"]) reports them as not evaluated."""
    muts = matrix["mutations"]
    live = {n: m for n, m in muts.items() if m["header"]["pending"] is None}
    g1 = sorted(n for n, m in live.items() if not any(r["verdict"] == "expected" for r in m["results"].values()))
    g2 = []
    for n, m in sorted(muts.items()):
        for f, r in sorted(m["results"].items()):
            if r["verdict"] in ("missed", "unexpected", "crash") or r["flags"]:
                g2.append("{} on {}: {}{}".format(n, f, r["verdict"], "; flags: " + "; ".join(r["flags"])
                                                  if r["flags"] else ""))
            elif r["verdict"] == "not run" and m["header"]["pending"] is None:
                g2.append("{} on {}: not run".format(n, f))
    equations = sorted({e for f in matrix["families"].values() for e in f["equations"]})
    g3 = []
    for eq in equations:
        if not any(r["verdict"] == "expected" and m["header"]["equation"] == eq
                   and any(b.split("[")[0] == eq for b in m["header"]["blocks"][f]["primary"])
                   for m in live.values() for f, r in m["results"].items()):
            g3.append(eq)
    g4 = sorted(f for f in matrix["families"]
                if not any(m["results"].get(f, {}).get("verdict") == "expected" for m in live.values()))
    partial = matrix.get("partial", False)
    return [("G1 every mutation caught in its expected check and block on a family", not g1,
             "not caught: {}".format(g1) if g1 else "{} mutations".format(len(live))),
            ("G2 no miss, unexpected firing, crash or flag", not g2, "; ".join(g2) if g2 else "none"),
            ("G3 every equation caught in its own block", partial or not g3,
             "not evaluated (a run of named mutations)" if partial else
             "uncaught: {}".format(g3) if g3 else ", ".join(equations)),
            ("G4 every family catches a mutation", partial or not g4,
             "not evaluated (a run of named mutations)" if partial else
             "catch nothing: {}".format(g4) if g4 else ", ".join(sorted(matrix["families"])))]


def gate_lines(results):
    return ["{} {}: {}".format("PASS" if ok else "FAIL", name, detail) for name, ok, detail in results]


SHORT = {"expected": "caught", "quiet": "quiet", "missed": "MISSED", "unexpected": "UNEXPECTED", "crash": "CRASH",
         "not run": "not run"}


def markdown(matrix):
    fams = sorted(matrix["families"], key=lambda f: matrix["families"][f]["neq"])
    lines = ["# Mutation coverage matrix", "",
             "Commit {} (baseline bbbpy SHA-256 {}). Cells: verdict, failing entries / largest |diff|/tol of the "
             "expected check over the configurations.".format(matrix["commit"][:12], matrix["baseline_so"][:16]), "",
             "| mutation | eq | fault | pending | " + " | ".join(fams) + " |",
             "|---|---|---|---|" + "---|" * len(fams)]
    for n, m in matrix["mutations"].items():
        h = m["header"]
        cells = []
        for f in fams:
            r = m["results"].get(f)
            if r is None:
                cells.append("")
                continue
            text = SHORT[r["verdict"]]
            if r.get("n_fail"):
                text += " {} / {:.3g}".format(r["n_fail"], r["max_ratio"])
            if r["flags"]:
                text += " (flag)"
            cells.append(text)
        lines.append("| {} | {} | {} | {} | {} |".format(n, h["equation"], h["fault"],
                                                         (h["pending"] or "").split(" (")[0], " | ".join(cells)))
    lines += ["", "## Gates", ""] + ["- " + l for l in gate_lines(gates(matrix))]
    details = []
    for n, m in matrix["mutations"].items():
        for f, r in m["results"].items():
            if r["problems"] or r["flags"]:
                details.append("- {} on {} ({}): {}".format(n, f, r["verdict"], "; ".join(r["problems"] + r["flags"])))
    if details:
        lines += ["", "## Problems and flags", ""] + details
    return "\n".join(lines) + "\n"


def exit_code(matrix):
    if all(ok for _, ok, _ in gates(matrix)):
        return 0
    print(OWNER, file=sys.stderr)
    return 3


# ---------------------------------------------------------------- child side


def part_summary(c, imap):
    cells = {}
    for i in map(int, c.fail_mask.nonzero()[0]):
        cells.setdefault("{}[{}]".format(imap.eq[i], imap.species[i]), []).append([int(imap.ix[i]), int(imap.iy[i])])
    return {"ok": bool(c.ok), "n_fail": int(c.n_fail), "max_ratio": float(c.worst[0]["ratio"]) if c.worst else 0.0,
            "cells": cells}


def has_locality(family):
    """Whether the family runs the locality check: a [locality] table in its family.toml (AIUE-100)."""
    from yldot.harness import locality as L

    return L.load_config(FAMILIES / family) is not None


def locality_part(runner, family, regions, tol):
    """The locality part of one family (test_locality.py's decision): (status record or None, part summary); (None,
    None) for a family without [locality], where the part is not run (owner, 2026-10-23, AIUE-92)."""
    from yldot.harness import FAMILIES, compare, open_store
    from yldot.harness import locality as L

    cfg = L.load_config(FAMILIES / family)
    if cfg is None:
        return None, None
    r = runner.evaluate(family, locality=cfg["delta_loc"])
    if not r.ok:
        return {"status": r.status, "message": r.message, "log_tail": r.log_tail}, None
    with open_store(family) as s:
        stored = s.locality("steady")
        if stored is None:
            raise Stop(2, "{}: the reference stores no locality pattern".format(family))
        imap = compare.index_map(r.data, regions)
        t = compare.tolerances(s.default("steady"), s.sigma("steady"), tol["rtol"], tol["rule"]["k"], imap).tol
        c = L.compare_pattern(stored[1], L.Entries.of(r.data["locality"]["entries"]), t,
                              L.rtol_rows(tol["rtol"], imap), float(cfg["m_loc"]), imap, family)
    stale = r.data["locality"]["stale"]
    if stale.size:
        return {"status": "error", "message": "{} stale locality columns".format(stale.size), "log_tail": ""}, None
    return None, {"ok": bool(c.ok), "n_fail": int(c.n_fail), "max_ratio": float(c.max_ratio),
                  "cells": {b: [list(x) for x in cells] for b, cells in c.fired.items()},
                  "headline": c.headline()}


def child(families, out, locality=False):
    """Evaluate each family in both configurations and write {family: {config: ...}} as JSON to out. locality: also
    the steady locality check (a range mutation, AIUE-100 D4), as the part "locality" of the steady configuration."""
    import numpy as np

    from yldot.harness import Runner, compare, open_store
    from yldot.harness.compare import DIAG_SCALED_RTOL, first_difference

    with open(SUITE / "tolerances.toml", "rb") as f:
        tol = tomllib.load(f)
    runner, res = Runner(), {}
    for family in families:
        res[family] = {}
        regions = compare.load_regions(family)
        for config in CONFIGS:
            r = runner.evaluate(family, config=config, diagnostics=True)
            if not r.ok:
                res[family][config] = {"status": r.status, "message": r.message, "log_tail": r.log_tail}
                continue
            with open_store(family) as s:
                imap = compare.index_map(r.data, regions)
                t = compare.tolerances(s.default(config), s.sigma(config), tol["rtol"], tol["rule"]["k"], imap).tol
                y, yj = np.asarray(r.data["yldot"]), np.asarray(r.data["yldot_J"])
                chk = s.check(config, None, y, yj, t, imap, r.data["diagnostics"])
                parts = {part: part_summary(compare.compare(new, ref, t, imap, worst=1), imap)
                         for part, new, ref in (("yldot", y, s.default(config)),
                                                ("flag difference", yj - y, s.jflag(config)))}
                if chk.ok != all(p["ok"] for p in parts.values()):
                    raise Stop(2, "{} {}: Store.check says {} but the comparisons {}".format(
                        family, config, chk.ok, {k: p["ok"] for k, p in parts.items()}))
                d = first_difference(*s.diagnostic_pair(config, r.data["diagnostics"]), rtol=DIAG_SCALED_RTOL,
                                     scaled=True)
            res[family][config] = {"status": "ok", "parts": parts, "intermediate": d.name if d else None,
                                   "first_difference": str(d) if d else None}
        if locality and res[family]["steady"].get("status") == "ok":
            failed, part = locality_part(runner, family, regions, tol)
            if failed is not None:
                res[family]["steady"] = failed
            elif part is not None:
                res[family]["steady"]["parts"]["locality"] = part
    Path(out).write_text(json.dumps(res, indent=1) + "\n")


# ---------------------------------------------------------------- host side


class Scratch:
    """One scratch worktree of sha and one venv for a whole run (make_references.build_host's recipe)."""

    def __init__(self, sha, out, root, run=mr.run, stream=mr.stream):
        self.sha, self.out, self.root, self.run, self.stream = sha, out, root, run, stream
        self.src, self.venv = out / "src", out / "venv"
        self.python = self.venv / "bin" / "python"
        self.env = dict(os.environ, PATH="{}{}{}".format(self.venv / "bin", os.pathsep, os.environ.get("PATH", "")),
                        OMP_NUM_THREADS="1")
        self.builds = []  # bbbpy SHA-256s of this run

    def git(self, *args):
        rc, out, err = self.run(["git", "-C", str(self.src)] + list(args))
        if rc != 0:
            raise Stop(2, "git {} failed: {}".format(" ".join(args), err.strip()))
        return out

    def setup(self):
        rc, _, err = self.run(["git", "-C", str(self.root), "worktree", "add", "--detach", str(self.src), self.sha])
        if rc != 0:
            raise Stop(2, "git worktree add failed: {}".format(err.strip()))
        if self.stream([sys.executable, "-m", "venv", str(self.venv)]) != 0:
            raise Stop(2, "python -m venv failed")
        try:
            pytest_pin = "pytest=={}".format(importlib.metadata.version("pytest"))
        except importlib.metadata.PackageNotFoundError:
            pytest_pin = "pytest"
        pins = list(mr.PINS) + [pytest_pin]
        if self.stream([str(self.python), "-m", "pip", "install", "-q"] + pins, env=self.env) != 0:
            raise Stop(2, "pip install {} failed".format(" ".join(pins)))

    def build(self, log):
        log.parent.mkdir(parents=True, exist_ok=True)
        # setup.py before AIUE-163 returned to getenv("PWD"), not the cwd, for the MPPL conversion: without PWD set
        # it converted and made the caller's checkout (AIUE-90); --from-commit may name such a commit
        env = dict(self.env, PWD=str(self.src))
        if self.stream([str(self.python), "-m", "pip", "install", "-v", "--no-build-isolation", "--no-deps", ".",
                        "-C", "--build-option={}".format(mr.FLAGS)], cwd=self.src, env=env, log=log) != 0:
            raise Stop(2, "the build failed (log: {})".format(log))
        so = sorted(self.venv.glob("lib/python*/site-packages/uedge/bbbpy*.so"))
        if len(so) != 1:
            raise Stop(2, "expected one bbbpy extension in the venv, found {}".format(so))
        sha = hashlib.sha256(so[0].read_bytes()).hexdigest()
        if sha in self.builds:
            raise Stop(2, "the build left bbbpy unchanged (SHA-256 {}): a stale build ({})".format(sha[:16], log))
        self.builds.append(sha)
        return sha

    def clean(self):
        if self.git("status", "--porcelain", "--untracked-files=no").strip():
            raise Stop(2, "the scratch tree {} is not clean after reverting".format(self.src))

    def remove(self):
        self.run(["git", "-C", str(self.root), "worktree", "remove", "--force", str(self.src)])

    def evaluate(self, families, out, locality=False):
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = [str(self.python), str(Path(__file__).resolve()), "_child", "--families"] + families + [
            "--out", str(out)] + (["--locality"] if locality else [])
        if self.stream(cmd, cwd=self.out, env=self.env, log=out.with_suffix(".log")) != 0:
            raise Stop(2, "the evaluation of {} failed (log: {})".format(families, out.with_suffix(".log")))
        return json.loads(out.read_text())

    def test_default(self, families, out):
        """{family: {config: failed}} from test_default.py run with the built python."""
        expr = " or ".join(families)
        cmd = [str(self.python), "-m", "pytest", "tests/yldot/test_default.py", "-k", expr, "-q", "-p",
               "no:cacheprovider", "--junitxml", str(out)]
        rc = self.stream(cmd, cwd=self.root, env=self.env, log=out.with_suffix(".log"))
        if rc not in (0, 1):
            raise Stop(2, "test_default.py exited {} (log: {})".format(rc, out.with_suffix(".log")))
        return parse_junit(out, families)

    def test_locality(self, families, out):
        """{family: failed} from test_locality.py's test_locality cases, run with the built python."""
        expr = "test_locality and ({})".format(" or ".join(families))
        cmd = [str(self.python), "-m", "pytest", "tests/yldot/test_locality.py", "-k", expr, "-q", "-p",
               "no:cacheprovider", "--junitxml", str(out)]
        rc = self.stream(cmd, cwd=self.root, env=self.env, log=out.with_suffix(".log"))
        if rc not in (0, 1):
            raise Stop(2, "test_locality.py exited {} (log: {})".format(rc, out.with_suffix(".log")))
        return parse_junit_locality(out, families)


def parse_junit_locality(path, families):
    """{family: failed} of the test_locality[<family>] cases in a JUnit XML file; a case collected twice or a family
    without its case is a harness error (the test must run where the check ran)."""
    res = {}
    for case in ET.parse(path).getroot().iter("testcase"):
        hit = re.match(r"^test_locality\[(.+)\]$", case.get("name", ""))
        if not hit or hit.group(1) not in families:
            continue
        if hit.group(1) in res:
            raise Stop(2, "test_locality[{}] collected twice ({})".format(hit.group(1), path))
        if case.find("skipped") is not None:
            raise Stop(2, "test_locality[{}] skipped ({})".format(hit.group(1), path))
        res[hit.group(1)] = case.find("failure") is not None or case.find("error") is not None
    missing = sorted(set(families) - set(res))
    if missing:
        raise Stop(2, "test_locality has no case for {} ({})".format(missing, path))
    return res


def parse_junit(path, families):
    """{family: {config: failed}} of the test_default cases in a JUnit XML file. A skipped case has no entry (verdict()
    then flags it against the check); a case collected twice is a harness error."""
    res, seen = {f: {} for f in families}, set()
    for case in ET.parse(path).getroot().iter("testcase"):
        hit = re.match(r"^test_default\[(.+)\]$", case.get("name", ""))
        if not hit:
            continue
        ids = hit.group(1).split("-")
        family = next((i for i in ids if i in res), None)
        config = next((i for i in ids if i in CONFIGS), None)
        if not (family and config):
            continue
        if (family, config) in seen:
            raise Stop(2, "test_default[{}-{}] collected twice ({})".format(family, config, path))
        seen.add((family, config))
        if case.find("skipped") is None:
            res[family][config] = case.find("failure") is not None or case.find("error") is not None
    return res


def entry(m, family, result, junit, junit_loc=None):
    v = verdict(m, family, result, junit, junit_loc)
    got = [(c, p) for c, r in result.items() if r.get("status") == "ok" for p in r["parts"]]
    want = [(c, p) for c, p in got if c in m.configs and p == m.check]
    v["n_fail"] = sum(result[c]["parts"][p]["n_fail"] for c, p in want)
    v["max_ratio"] = max([result[c]["parts"][p]["max_ratio"] for c, p in want] or [0.0])
    v["configs"] = result
    return v


def run_one(m, scratch, out, families):
    """The matrix entry of one mutation: apply, build, evaluate (inner-loop family first), revert."""
    patch, mdir = str(m.path), out / m.name
    scratch.git("apply", "--check", patch)
    scratch.git("apply", patch)
    try:
        so = scratch.build(mdir / "build.log")
        inner = m.families[0] if m.pending is None and m.families[0] in families else None
        order = ([inner] if inner else []) + [f for f in families if f != inner]
        results = {}
        loc = m.check == "locality"  # the locality check runs for the range mutations only (owner, AIUE-100 D4)

        def evaluate(fams, name):
            res = scratch.evaluate(fams, mdir / "{}.json".format(name), locality=loc)
            junit = scratch.test_default(fams, mdir / "{}.junit.xml".format(name))
            with_loc = [f for f in fams if has_locality(f)] if loc else []
            jloc = scratch.test_locality(with_loc, mdir / "{}.locality.junit.xml".format(name)) if with_loc else {}
            for f in fams:
                results[f] = entry(m, f, res[f], junit[f], jloc.get(f))

        first = [inner] if inner else order
        evaluate(first, "first")
        rest = [f for f in order if f not in first]
        if inner and results[inner]["verdict"] != "expected":
            for f in rest:
                results[f] = {"verdict": "not run", "problems": ["the inner-loop family {} failed".format(inner)],
                              "flags": []}
        elif rest:
            evaluate(rest, "rest")
    finally:
        scratch.git("apply", "-R", patch)
    scratch.clean()
    return {"header": m.summary(), "so": so, "results": results}


def run(args, run=mr.run, stream=mr.stream):
    root = SUITE.parents[1]
    families = referenced()
    stores = store_facts(families)
    ms = load_set(args.mutation or None, stores)
    sha = mr.resolve(args.from_commit, root, run)
    mr.check_tree(sha, root, families, run)
    rc = stream([sys.executable, str(Path(__file__).resolve().parent / "fetch_data.py"), "--check"] + families)
    if rc != 0:
        raise Stop(1, "the reference files are not all present: run tests/yldot/tools/fetch_data.py {}".format(
            " ".join(families)))
    out = Path(args.out).resolve()
    if out.exists() and any(out.iterdir()):
        raise Stop(1, "--out {} is not empty".format(out))
    out.mkdir(parents=True, exist_ok=True)
    scratch = Scratch(sha, out, root, run, stream)
    matrix = {"commit": sha, "families": stores, "mutations": {}, "partial": bool(args.mutation)}
    try:
        scratch.setup()
        matrix["baseline_so"] = scratch.build(out / "baseline" / "build.log")
        base = scratch.evaluate(families, out / "baseline" / "eval.json")
        noisy = {f: sorted(fired(base[f])) for f in families if fired(base[f])}
        crashed = [f for f in families if any(r.get("status") != "ok" for r in base[f].values())]
        if noisy or crashed:
            raise Stop(2, "the unmutated build of {} does not pass: fired {}, crashed {}".format(
                sha[:12], noisy, crashed))
        print("baseline {}: every referenced family passes".format(sha[:12]), flush=True)
        for m in ms:
            matrix["mutations"][m.name] = run_one(m, scratch, out, families)
            (out / "matrix.json").write_text(json.dumps(matrix, indent=1) + "\n")
            print("{}: {}".format(m.name, ", ".join("{} {}".format(f, r["verdict"]) for f, r in
                                                   matrix["mutations"][m.name]["results"].items())), flush=True)
    finally:
        scratch.remove()
    (out / "matrix.md").write_text(markdown(matrix))
    print("\n".join(gate_lines(gates(matrix))))
    print("matrix: {} and {}".format(out / "matrix.json", out / "matrix.md"))
    return exit_code(matrix)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="check and list the mutation set")
    p = sub.add_parser("run", help="build and run the mutations, write the coverage matrix")
    p.add_argument("mutation", nargs="*", help="default: all")
    p.add_argument("--from-commit", default="HEAD")
    p.add_argument("--out", required=True, help="an empty or new working directory")
    p = sub.add_parser("gates", help="the gates of a written matrix")
    p.add_argument("dir")
    p = sub.add_parser("_child", help="inside the built venv: evaluate")
    p.add_argument("--families", nargs="+", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--locality", action="store_true", help="also the steady locality check (range mutations)")
    args = parser.parse_args(argv[1:])
    try:
        if args.cmd == "_child":
            child(args.families, args.out, args.locality)
            return 0
        if args.cmd == "list":
            ms = load_set(stores=store_facts(referenced()))
            for m in ms:
                print("{:36s} {:12s} {:4s} {:16s} {:16s} {}{}".format(
                    m.name, m.kind, m.equation, m.fault, m.check, ", ".join(m.families),
                    "  [pending {}]".format(m.pending.split(" (")[0]) if m.pending else ""))
            print("{} mutations".format(len(ms)))
            return 0
        if args.cmd == "gates":
            matrix = json.loads((Path(args.dir) / "matrix.json").read_text())
            print("\n".join(gate_lines(gates(matrix))))
            return exit_code(matrix)
        return run(args)
    except (Stop, mr.Stop) as e:
        print(str(e), file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
