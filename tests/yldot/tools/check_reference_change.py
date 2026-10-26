"""The reference guard of the yldot suite (epic AIUE-9, PRD sections 7.3 and 7.6; decision 29).

Usage (from anywhere; PR_BODY holds the PR description):
    python check_reference_change.py check --base REV --head REV [--repo PATH] [--gh-repo OWNER/REPO]
                                           [--no-download] [--summary FILE] [--json FILE]
    python check_reference_change.py history [--rev REV] [--repo PATH] [--gh-repo OWNER/REPO]
                                             [--release-limit-mb 200] [--git-limit-mb 30]

check compares the PR head with its merge base as data: it computes the merge base once (git merge-base), lists the
changed paths from it to the head with git diff, reads every base-side copy (manifests, TOML) at the merge base, never
at the base tip, and the head copies with git cat-file, and parses the manifests and TOML files. It never imports, runs
or checks out code of the head (reference-guard.yml runs the base branch's copy of this script, AIUE-104). The PR
description is read without its HTML comments and fenced code blocks. Every printed line has its control characters
escaped (\\x0a), so a path or name chosen by the PR cannot start a log line. Each changed path needs one or more
declaration lines in the PR description (owner decisions, 2026-10-22, AIUE-97 ticket page):

    Default results: changed     a manifest change that is not an addition, a prune of an entry not SENSITIVE in any
                                 family, a rename with identical data or a diagnostics-only change; followed, anywhere
                                 below, by every changed item as <family>:<id> (the guard prints the list)
    Test criteria: changed       any change to the guarded set (tests/yldot/** and the four workflows) other than
                                 manifests and new files under mutations/; with a justification
    Test criteria: loosened      a loosening (PRD 7.6: larger tolerances, changed sigma or stored sketch thresholds,
                                 changed or removed overrides,
                                 harness and test code, this guard, the non-monotone parameters, deleted files, and
                                 any key it cannot show to be tighter); with a justification, besides the changed
                                 line, and approval by a CODEOWNER of tests/yldot/** (branch protection, AIUE-104)

Which paths count (tests/yldot/ unless noted): conftest.py, test_*.py, *_test.py, pytest.ini, .pytest.ini, pytest.toml,
.pytest.toml, tox.ini, setup.cfg and pyproject.toml at any depth, harness/ and this guard are test code (loosened); an added file under mutations/ that
pytest does not load (not *.py, conftest.py, *.ini, *.cfg, *.toml) is not guarded; a conftest.py, pytest.ini, .pytest.ini, pytest.toml,
.pytest.toml or tox.ini in the repository root or tests/ is loosened, and so is a pyproject.toml or setup.cfg there when its pytest section
([tool.pytest] / [tool:pytest]) changes or either side does not parse (other edits of those two are not guarded).

A line matches with leading list markers, '>' and surrounding ** or backticks ignored; the keywords are exact.

A base manifest that is invalid is treated as absent: the PR that changes it needs Default results: changed with the
item <family>:* (the head manifest must be valid); an invalid manifest the PR does not touch is not charged to it. An external file over 200 MB is refused before the download.

For every external file a head manifest names anew or differently (or under a new release) check downloads the
release asset with gh into a temporary directory and refuses a size or SHA-256 that differs from the manifest; for
the reference .h5 it also recomputes every dataset's SHA-256 against the manifest's datasets, and it checks that
the head manifest's guarded, unguarded and variant SHA-256s follow from its datasets (store.check_derived).

history reports the total size of the yldot-data-v* releases, the size of tests/yldot/ in the tree at --rev and of
every blob under it in that history, and the orphan releases (named by no manifest at --rev, which the owner may
delete). It exits 1 above the owner's review limits: 200 MB of releases, 30 MB in git (owner, 2026-10-22).

Exit codes: 0 every required declaration present and every check passed (history: within the limits), 1 a
declaration missing, an integrity or validity check failed (history: over a limit, an invalid manifest), 2 usage (an unknown revision,
PR_BODY unset, gh failed in history).
"""
import argparse
import configparser
import fnmatch
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # tests/, for the yldot package
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tools/, for fetch_data

import fetch_data  # noqa: E402
from yldot.harness import manifest as mf  # noqa: E402
from yldot.harness import store  # noqa: E402

GUARDED = "tests/yldot/"
REFERENCES = GUARDED + "references/"
WORKFLOWS = {".github/workflows/build-test-wheel.yml": "changed", ".github/workflows/nightly-tests.yml": "changed",
             ".github/workflows/reference-guard.yml": "loosened",
             ".github/workflows/regenerate-references.yml": "changed"}
DEFAULT, CHANGED, LOOSENED = "default", "changed", "loosened"
KEYWORDS = {DEFAULT: "Default results: changed", CHANGED: "Test criteria: changed",
            LOOSENED: "Test criteria: loosened"}
CODEOWNER = "REQUIRED: CODEOWNER approval of tests/yldot/** (enforced by branch protection, AIUE-104)"
MANIFEST_RE = re.compile(r"^references/([^/]+)\.manifest\.json$")
FAMILY_TOML_RE = re.compile(r"^families/([^/]+)/family\.toml$")
SIGMA_H5_RE = re.compile(r"^families/[^/]+/sigma\.h5$")
PYTEST_INI = ("pytest.ini", ".pytest.ini", "pytest.toml", ".pytest.toml", "tox.ini")  # whole file is configuration
PYTEST_CONFIG = PYTEST_INI + ("setup.cfg", "pyproject.toml")
MAX_EXTERNAL_BYTES = 200 * 10**6  # per external file (AIUE-104 adds runner-side caps)
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
GUARDED_DEFAULT_RE = re.compile(r"^/[^/]+/(default/(yldot|sigma|jflag/|sketch_threshold/|sketch_weight$)|locality/|"
                                r"locality_variants/)")

# tolerances.toml (PRD 7.4, 7.6): a larger value loosens, a smaller one tightens; the rule texts and floor_limit
# only loosen; the record sections are measurements and owner bookkeeping
RULE_MONOTONE = ("k", "rtol_factor", "rtol_floor")
RULE_TEXT = ("floor_limit", "floor", "sigma", "rtol")
TOLERANCE_RECORDS = ("builds", "pairs", "raw", "rtol_source", "openmp", "floor", "findings", "owner")
# family.toml: [evaluation] (W, P, child reuse, timeout, dt) and [regions] are non-monotone parameters
FAMILY_LOOSE = ("evaluation", "regions")
FAMILY_RECORDS = ("source", "reference_state", "perturbation", "limiter_report", "history")
# family.toml [locality] (PRD 7.5, 7.6; AIUE-100): a new section is a new criterion; m_loc is a margin (larger
# loosens), delta_loc a non-monotone parameter; the calibration record and the causes are bookkeeping
LOCALITY_MONOTONE = ("m_loc",)
LOCALITY_LOOSE = ("delta_loc",)
LOCALITY_RECORDS = ("calibration", "causes")
# the column set and the variant scope (AIUE-101): a narrower one loosens, a wider one is a new criterion; absent
# columns meant every column, absent variants none; sample (interior columns) the larger the tighter, seed a new sample
LOCALITY_SCOPE = {"columns": {None: 2, "all": 2, "special": 1}, "variants": {None: 0, "meth": 1, "listed": 2, "all": 3}}


class GuardError(Exception):
    """A usage error: an unknown revision, a failed git or gh command."""


class Finding:
    """One requirement a changed path imposes: req is DEFAULT, CHANGED, LOOSENED or None (allowed, a note)."""

    def __init__(self, req, path, why, item=None):
        self.req, self.path, self.why, self.item = req, path, why, item

    def line(self):
        return "  [{}] {}: {}{}".format(self.req or "allowed", self.path, self.why,
                                        " ({})".format(self.item) if self.item else "")

    def as_dict(self):
        return {"req": self.req, "path": self.path, "why": self.why, "item": self.item}


# ---------------------------------------------------------------- git, as data only


def git(repo, *args):
    """stdout (bytes) of a git command in repo; never through a shell, never with external diff or textconv."""
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if r.returncode != 0:
        raise GuardError("git {} failed ({}): {}".format(" ".join(args), r.returncode,
                                                         r.stderr.decode(errors="replace").strip()))
    return r.stdout


def commit(repo, rev):
    try:
        return git(repo, "rev-parse", "--verify", "--quiet", rev + "^{commit}").decode().strip()
    except GuardError:
        raise GuardError("unknown revision {!r}".format(rev)) from None


def merge_base(repo, base, head):
    try:
        return git(repo, "merge-base", base, head).decode().strip()
    except GuardError:
        raise GuardError("{} and {} have no merge base".format(base[:12], head[:12])) from None


def name_status(repo, base, head):
    """[(status letter, path)] from base (the merge base) to head; renames are a delete and an add."""
    raw = git(repo, "diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--name-status", "-z",
              "{}..{}".format(base, head)).decode()
    parts = raw.split("\0")
    return [(parts[i][0], parts[i + 1]) for i in range(0, len(parts) - 1, 2)]


def blob(repo, rev, path):
    """The bytes of path at rev, or None if it is not there."""
    r = subprocess.run(["git", "-C", str(repo), "cat-file", "blob", "{}:{}".format(rev, path)], capture_output=True)
    return r.stdout if r.returncode == 0 else None


def manifests_at(repo, rev):
    """{family: (manifest or None, problem or None)} for every references/*.manifest.json at rev."""
    names = git(repo, "ls-tree", "-z", "--name-only", rev, "--", REFERENCES).decode().split("\0")
    out = {}
    for p in names:
        hit = MANIFEST_RE.match(p[len(GUARDED):]) if p.startswith(GUARDED) else None
        if hit:
            out[hit.group(1)] = load_manifest(blob(repo, rev, p), hit.group(1))
    return out


def load_manifest(data, family):
    try:
        m = mf.loads(data)
        mf.validate(m)
    except (ValueError, mf.ManifestError) as e:
        return None, "{}: {}".format(family, e)
    if m["family"] != family:
        return None, "{}: the manifest names family {!r}".format(family, m["family"])
    return m, None


# ---------------------------------------------------------------- the rules


def loaded_by_pytest(name):
    """A file name pytest might import or read as configuration (any Python file, any .ini, .cfg, .toml)."""
    return name.endswith((".py", ".ini", ".cfg", ".toml"))


def is_test_code(name):
    """A file name pytest collects or reads as configuration, at any depth below tests/yldot: test code."""
    return name == "conftest.py" or name in PYTEST_CONFIG or fnmatch.fnmatch(name, "test_*.py") \
        or fnmatch.fnmatch(name, "*_test.py")


def path_class(path, status):
    """None (not guarded), "manifest", "tolerances", "overrides", "family", or a requirement for the path itself."""
    if path in WORKFLOWS:
        return WORKFLOWS[path]
    if not path.startswith(GUARDED):
        above = path[len("tests/"):] if path.startswith("tests/") else path  # the repository root or tests/
        if above == "conftest.py" or above in PYTEST_INI:  # a name only: tests/other/pytest.ini is not matched
            return LOOSENED  # pytest config above tests/yldot
        if path in ("pyproject.toml", "tests/pyproject.toml", "setup.cfg", "tests/setup.cfg"):
            return "pytestcfg"  # only its pytest sections count
        return None
    rel = path[len(GUARDED):]
    name = PurePosixPath(rel).name
    if rel.startswith("mutations/") and status == "A" and not loaded_by_pytest(name):
        return None
    if MANIFEST_RE.match(rel):
        return "manifest"
    if status == "D":
        return LOOSENED
    if SIGMA_H5_RE.match(rel):
        return CHANGED if status == "A" else LOOSENED  # a new family's sigma is an addition
    if rel.startswith("harness/") or rel in ("conftest.py", "__init__.py", "tools/check_reference_change.py"):
        return LOOSENED
    if is_test_code(name):
        return LOOSENED
    if rel == "tolerances.toml":
        return "tolerances"
    if rel == "overrides.toml":
        return "overrides"
    if FAMILY_TOML_RE.match(rel):
        return "family"
    return CHANGED


def monotone(a, b):
    """A tolerance value from a to b (None: absent): new or smaller CHANGED; removed, larger, not a number or not
    finite (on either side) LOOSENED."""
    if b is None:
        return CHANGED if a is None else LOOSENED
    vals = [v for v in (a, b) if v is not None]
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in vals):
        return LOOSENED
    return CHANGED if a is None or b <= a else LOOSENED


def diff_tolerances(t0, t1):
    """[(requirement, what)] for two parsed tolerances.toml."""
    out = []
    for sec in sorted(set(t0) | set(t1)):
        a, b = t0.get(sec), t1.get(sec)
        if a == b:
            continue
        if sec in TOLERANCE_RECORDS:
            out.append((CHANGED, "[{}] (record)".format(sec)))
        elif sec in ("rule", "rtol", "sigma") and isinstance(a or {}, dict) and isinstance(b or {}, dict):
            a, b = a or {}, b or {}
            for key in sorted(set(a) | set(b)):
                va, vb = a.get(key), b.get(key)
                if va == vb:
                    continue
                what = "[{}].{}: {!r} -> {!r}".format(sec, key, va, vb)
                if sec == "rtol" or (sec == "rule" and key in RULE_MONOTONE):
                    out.append((monotone(va, vb), what))
                elif sec == "sigma" and isinstance(va or {}, dict) and isinstance(vb or {}, dict):
                    va, vb = va or {}, vb or {}
                    if va and va.get("sha256") != vb.get("sha256"):
                        out.append((LOOSENED, "[sigma.{}].sha256 changed or removed (stored sigma)".format(key)))
                    else:
                        out.append((CHANGED, "[sigma.{}] (record)".format(key)))
                else:
                    out.append((LOOSENED, what + (" (rule text)" if key in RULE_TEXT else " (unknown key)")))
        else:
            out.append((LOOSENED, "[{}] (unknown section)".format(sec)))
    return out


def diff_overrides(o0, o1, pruned):
    """[(requirement, what)] for two parsed overrides.toml; pruned: the keys whose variants this change prunes."""
    out = []
    for key in sorted(set(o0) | set(o1)):
        a, b = o0.get(key), o1.get(key)
        if a == b:
            continue
        if a is None:
            out.append((CHANGED, "[{}] new override".format(key)))
        elif b is None and key in pruned:
            out.append((CHANGED, "[{}] removed with its pruned variable".format(key)))
        else:
            out.append((LOOSENED, "[{}] override {}".format(key, "removed" if b is None else "changed")))
    return out


def diff_family_toml(f0, f1):
    """[(requirement, what)] for two parsed family.toml."""
    out = []
    for sec in sorted(set(f0) | set(f1)):
        a, b = f0.get(sec), f1.get(sec)
        if a == b:
            continue
        if sec in FAMILY_LOOSE:
            out.append((LOOSENED, "[{}] (non-monotone parameters)".format(sec)))
        elif sec == "family" and isinstance(a or {}, dict) and isinstance(b or {}, dict):
            a, b = a or {}, b or {}
            if a.get("store") != b.get("store"):
                out.append((LOOSENED, "[family].store"))
            if {k: v for k, v in a.items() if k != "store"} != {k: v for k, v in b.items() if k != "store"}:
                out.append((CHANGED, "[family] (record)"))
        elif sec in FAMILY_RECORDS:
            out.append((CHANGED, "[{}] (record)".format(sec)))
        elif sec == "locality" and isinstance(a or {}, dict) and isinstance(b or {}, dict):
            out.extend(diff_locality(a, b))
        else:
            out.append((LOOSENED, "[{}] (unknown section)".format(sec)))
    return out


def diff_locality(a, b):
    """[(requirement, what)] for two family.toml [locality] tables (None: absent)."""
    if a is None:
        return [(CHANGED, "[locality] new (the locality check of this family)")]
    if b is None:
        return [(LOOSENED, "[locality] removed")]
    out = []
    for key in sorted(set(a) | set(b)):
        va, vb = a.get(key), b.get(key)
        if va == vb:
            continue
        what = "[locality].{}: {!r} -> {!r}".format(key, va, vb)
        if key in LOCALITY_MONOTONE:
            out.append((monotone(va, vb), what))
        elif key in LOCALITY_SCOPE:
            rank = LOCALITY_SCOPE[key]
            wider = isinstance(vb, str) and vb in rank and (va is None or isinstance(va, str) and va in rank) \
                and rank[vb] >= rank[va]
            out.append((CHANGED if wider else LOOSENED, what + (" (wider or equal)" if wider else " (narrower)")))
        elif key in ("sample", "seed") and a.get("columns", "all") != b.get("columns", "all"):
            continue  # part of the change of columns, judged there
        elif key == "sample":
            more = all(isinstance(v, int) and not isinstance(v, bool) for v in (va or 0, vb)) and vb >= (va or 0)
            out.append((CHANGED if more else LOOSENED, what + (" (more columns)" if more else " (fewer columns)")))
        elif key == "seed":
            out.append((CHANGED if vb is not None else LOOSENED, what + " (another sample)"))
        elif key == "excluded" and isinstance(va or {}, dict) and isinstance(vb or {}, dict):
            va, vb = va or {}, vb or {}
            more = sorted(k for k in vb if k not in va)
            if more:
                out.append((LOOSENED, "[locality].excluded adds {} (fewer variant patterns)".format(more)))
            if any(k in va and va[k] != vb[k] for k in vb) or any(k not in vb for k in va):
                out.append((CHANGED, "[locality].excluded reasons changed or entries removed (record)"))
        elif key in LOCALITY_LOOSE:
            out.append((LOOSENED, what + " (non-monotone parameter)"))
        elif key in LOCALITY_RECORDS:
            out.append((CHANGED, "[locality].{} (record)".format(key)))
        else:
            out.append((LOOSENED, what + " (unknown key)"))
    return out


def stored(m, config, vid):
    """{dataset path below the variant: SHA-256} of one stored variant."""
    prefix = "/{}/variants/{}/".format(config, vid)
    return {n[len(prefix):]: s for n, s in m.get("datasets", {}).items() if n.startswith(prefix)}


def same_entry(m0, a, va, m1, b, vb):
    """A rename: the entries agree in every field but the reason and the variant SHA (which hashes the id), and the
    stored datasets are the same SHA-256s under the new id."""
    keep = ("class", "applied", "d", "phase", "config", "block_l2", "jflag_block_l2")
    return (all(va[k] == vb[k] for k in keep)
            and stored(m0, va["config"], a) == stored(m1, vb["config"], b))


def diff_manifest(family, m0, m1, base_classes):
    """(findings, externals to verify) for a family's manifest from m0 to m1 (None: absent). base_classes: {variant
    id: set of its classes in every base manifest}."""
    where = "{}{}.manifest.json".format(REFERENCES, family)
    if m1 is None:
        return [Finding(DEFAULT, where, "manifest removed", "{}:*".format(family))], []
    new_family = m0 is None
    m0 = m0 or {"store": m1["store"], "release": None, "external": {}}
    found = []

    def add(req, why, item=None):
        found.append(Finding(req, where, why, item))

    had_data = "datasets" in m0
    if had_data and m0["store"] != m1["store"]:
        add(LOOSENED, "store {} -> {}".format(m0["store"], m1["store"]))
    if had_data and m0.get("sketch") != m1.get("sketch"):
        add(LOOSENED, "sketch {} -> {}".format(m0.get("sketch"), m1.get("sketch")))
    g0, g1 = m0.get("guarded", {}), m1.get("guarded", {})
    for key in sorted(g0):
        if g1.get(key) != g0[key]:
            if key.startswith("locality_variants/"):
                continue  # judged per variant below, through locality_variants
            if key.endswith("/sigma"):
                add(LOOSENED, "stored sigma {} {}".format(key, "removed" if key not in g1 else "changed"))
            elif key.endswith("/sketch_threshold"):  # the manifest cannot show the thresholds smaller (AIUE-92)
                add(LOOSENED, "stored sketch thresholds {} {}".format(key, "removed" if key not in g1 else "changed"))
            else:  # the defaults, the locality pattern and a sketch store's weights (AIUE-174): a default change
                add(DEFAULT, "guarded {} {}".format(key, "removed" if key not in g1 else "changed"),
                    "{}:{}".format(family, key))
    if sorted(set(g1) - set(g0)):
        add(None, "addition: guarded {}".format(sorted(set(g1) - set(g0))))
    if m0.get("unguarded", {}) != m1.get("unguarded", {}):
        add(None, "diagnostics changed (unguarded)")
    # the variants' locality patterns (AIUE-101): a new one is a new criterion, a changed one a default change of
    # that variant, a removed one a loosening
    l0, l1 = m0.get("locality_variants", {}), m1.get("locality_variants", {})
    new_loc = sorted(set(l1) - set(l0))
    if new_loc:
        add(CHANGED, "new locality patterns of variants {}".format(new_loc))
    for vid in sorted(set(l0) - set(l1)):
        add(LOOSENED, "locality pattern of variant {} removed".format(vid))
    for vid in sorted(set(l0) & set(l1)):
        if l0[vid] != l1[vid]:
            add(DEFAULT, "locality pattern of variant {} changed".format(vid), "{}:{}".format(family, vid))
    d0, d1 = m0.get("datasets", {}), m1.get("datasets", {})
    for name in sorted(d0):
        if d1.get(name) == d0[name] or "/diagnostics/" in name or store.STORED_VARIANT.match(name):
            continue
        if GUARDED_DEFAULT_RE.match(name):
            continue  # judged through guarded, which check_derived ties to the datasets
        add(DEFAULT, "dataset {} {}".format(name, "removed" if name not in d1 else "changed"),
            "{}:index".format(family) if name.startswith("/index/") else "{}:{}".format(family, name))
    v0, v1 = m0.get("variables", {}), m1.get("variables", {})
    added = sorted(set(v1) - set(v0))
    for vid in sorted(set(v0) - set(v1)):
        twin = next((b for b in added if same_entry(m0, vid, v0[vid], m1, b, v1[b])), None)
        if twin:
            added.remove(twin)
            add(None, "rename {} -> {} (identical data)".format(vid, twin))
        elif "SENSITIVE" in base_classes.get(vid, set()):
            add(DEFAULT, "variant {} removed, SENSITIVE in a base manifest".format(vid), "{}:{}".format(family, vid))
        else:
            add(None, "prune {} ({} in every family)".format(vid, "/".join(sorted(base_classes.get(vid, set())))))
    if added:
        add(None, "addition: variants {}".format(added))
    for vid in sorted(set(v0) & set(v1)):
        diff = sorted(k for k in v0[vid] if k != "reason" and v0[vid][k] != v1[vid][k])
        if diff:
            add(DEFAULT, "variant {} changed: {}".format(vid, ", ".join(diff)), "{}:{}".format(family, vid))
    ref = mf.reference_path(family) if "datasets" in m1 else None  # judged through the datasets, if there are any
    e0, e1 = m0["external"], m1["external"]
    for p in sorted(set(e0) | set(e1)):
        if p == ref or e0.get(p) == e1.get(p):
            continue
        if p not in e0:
            add(None, "addition: external {}".format(p))
        else:
            add(DEFAULT, "external {} {}".format(p, "removed" if p not in e1 else "changed"),
                "{}:{}".format(family, p))
    if new_family:
        add(None, "new family")
    moved = m1["release"] != m0["release"] or d1 != d0
    verify = [p for p, e in sorted(e1.items()) if moved or e0.get(p) != e]
    return found, verify


def pytest_sections(path, data):
    """The pytest sections of a pyproject.toml or setup.cfg (bytes or None), as data; None if it does not parse."""
    if data is None:
        return {}
    try:
        text = data.decode()
        if path.endswith(".toml"):
            tool = tomllib.loads(text).get("tool", {})
            return {"tool.pytest": tool["pytest"]} if "pytest" in tool else {}
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        parser.read_string(text)
        return {"tool:pytest": dict(parser["tool:pytest"])} if parser.has_section("tool:pytest") else {}
    except (tomllib.TOMLDecodeError, configparser.Error, UnicodeDecodeError, AttributeError):
        return None


def guarded_paths(repo, base, head):
    """(findings, manifests to verify {family: (manifest, [paths])}, errors) for the change from base (the merge base
    of the PR's base and head) to head; everything on the base side is read at base."""
    found, errors, toml = [], [], {}
    changes = name_status(repo, base, head)
    changed_manifests = {p for _, p in changes}
    kinds = {}
    for status, path in changes:
        kind = path_class(path, status)
        if kind is None:
            continue
        if kind in (DEFAULT, CHANGED, LOOSENED):
            why = "deleted" if status == "D" else "added" if status == "A" else "modified"
            found.append(Finding(kind, path, why))
        elif kind == "pytestcfg":
            s0, s1 = (pytest_sections(path, blob(repo, rev, path)) for rev in (base, head))
            if s0 is None or s1 is None:
                found.append(Finding(LOOSENED, path, "does not parse: its pytest sections can't be compared"))
            elif s0 != s1:
                found.append(Finding(LOOSENED, path, "pytest section changed"))
        else:
            kinds[path] = (kind, status)
    if any(k == "manifest" for k, _ in kinds.values()) or any(k == "overrides" for k, _ in kinds.values()):
        before, after = manifests_at(repo, base), manifests_at(repo, head)
    else:
        before, after = {}, {}
    def touched(family):
        return "{}{}.manifest.json".format(REFERENCES, family) in changed_manifests

    errors += [e for f, (_, e) in sorted(after.items()) if e and touched(f)]  # an untouched one is not this PR's
    for family, (_, problem) in sorted(before.items()):
        if problem and touched(family):
            found.append(Finding(DEFAULT, "{}{}.manifest.json".format(REFERENCES, family),
                                 "the base manifest is invalid and counts as absent ({})".format(problem),
                                 "{}:*".format(family)))
    base_m = {f: m for f, (m, _) in before.items() if m}
    head_m = {f: m for f, (m, _) in after.items() if m}
    base_classes = {}
    for m in base_m.values():
        for vid, v in m.get("variables", {}).items():
            base_classes.setdefault(vid, set()).add(v["class"])
    verify = {}
    for path, (kind, status) in sorted(kinds.items()):
        rel = path[len(GUARDED):]
        if kind == "manifest":
            family = MANIFEST_RE.match(rel).group(1)
            if family in after and family not in head_m:
                continue  # invalid head manifest: in errors
            if status == "D":
                found.append(Finding(LOOSENED, path, "deleted"))
            f, paths = diff_manifest(family, base_m.get(family), head_m.get(family), base_classes)
            found += f
            if head_m.get(family) is not None and "datasets" in head_m[family]:
                try:
                    store.check_derived(head_m[family], path)
                except store.StoreIntegrityError as e:
                    errors.append(str(e))
            if paths:
                verify[family] = (head_m[family], paths)
            continue
        if status == "A" and kind == "family":
            found.append(Finding(CHANGED, path, "added (new family)"))
            continue
        try:
            t0, t1 = (tomllib.loads((blob(repo, rev, path) or b"").decode()) for rev in (base, head))  # base: merge base
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
            errors.append("{}: not valid TOML: {}".format(path, e))
            continue
        if kind == "tolerances":
            diffs = diff_tolerances(t0, t1)
        elif kind == "overrides":
            pruned = {k for k in set(t0) | set(t1)
                      if any(_names(m, k) for m in base_m.values()) and not any(_names(m, k) for m in head_m.values())}
            diffs = diff_overrides(t0, t1, pruned)
        else:
            diffs = diff_family_toml(t0, t1)
        found += [Finding(req, path, what) for req, what in diffs] or [Finding(CHANGED, path, "text only")]
    return found, verify, errors


def _names(m, key):
    return any(vid == key or vid.startswith(key + "=") for vid in m.get("variables", {}))


# ---------------------------------------------------------------- integrity


def check_h5(path, m):
    """Problems of a downloaded reference file against its manifest: dataset set and SHA-256s, root attributes."""
    import h5py

    problems, shas = [], {}
    with h5py.File(path, "r") as f:
        f.visititems(lambda name, obj: shas.__setitem__("/" + name, store.dataset_sha256(obj[()]))
                     if hasattr(obj, "shape") else None)
        attrs = {k: f.attrs.get(k) for k in ("schema", "family", "store")}
        sketch = {"k": int(f.attrs["k"]), "seed": int(f.attrs["seed"])} if "k" in f.attrs else None
    want = m["datasets"]
    extra, missing = sorted(set(shas) - set(want)), sorted(set(want) - set(shas))
    if extra or missing:
        problems.append("datasets not in the manifest {}, in the manifest but not the file {}".format(extra, missing))
    bad = sorted(n for n in set(shas) & set(want) if shas[n] != want[n])
    if bad:
        problems.append("datasets whose SHA-256 differs from the manifest {}".format(bad))
    if attrs != {"schema": store.SCHEMA, "family": m["family"], "store": m["store"]}:
        problems.append("root attributes {} do not match the manifest".format(attrs))
    if m["store"] == "sketch" and sketch != m.get("sketch"):
        problems.append("k/seed {} differ from the manifest's sketch {}".format(sketch, m.get("sketch")))
    with h5py.File(path, "r") as f:
        try:
            slices = store.locality_slices(f)
        except (ValueError, KeyError) as e:
            slices = None
            problems.append("locality_variants unreadable: {}".format(e))
    if slices is not None:
        want = {vid: (e["config"], e["sha256"]) for vid, e in m.get("locality_variants", {}).items()}
        bad = sorted(vid for vid in set(want) | set(slices) if want.get(vid) != slices.get(vid))
        if bad:
            problems.append("locality_variants slices differ from the manifest: {}".format(bad))
    return problems


def verify_externals(verify, gh_repo, download=fetch_data.download):
    """Errors from downloading and checking every external file in verify {family: (manifest, [paths])}."""
    errors = []
    tmp = Path(tempfile.mkdtemp(prefix="yldot-guard-"))
    try:
        for family, (m, paths) in sorted(verify.items()):
            tag = m["release"]
            if tag is None:
                errors.append("{}: external files {} changed but release is null (a local preview can't be merged)"
                              .format(family, paths))
                continue
            big = [p for p in paths if m["external"][p]["bytes"] > MAX_EXTERNAL_BYTES]
            errors += ["{}: external {} is {} bytes, over the {} MB limit per file".format(
                family, p, m["external"][p]["bytes"], MAX_EXTERNAL_BYTES // 10**6) for p in big]
            paths = [p for p in paths if p not in big]
            if not paths:
                continue
            dest = tmp / family
            dest.mkdir()
            try:
                download(tag, [mf.asset_name(p) for p in paths], dest, gh_repo)
            except fetch_data.FetchError as e:
                errors.append("{}: {}".format(family, e))
                continue
            for p in paths:
                got = dest / mf.asset_name(p)
                if not got.is_file():
                    errors.append("{}: {} not in release {}".format(family, mf.asset_name(p), tag))
                    continue
                bad = fetch_data.matches(got, m["external"][p])
                if bad:
                    errors.append("{}: {} from {} has {}".format(family, mf.asset_name(p), tag, bad))
                elif p == mf.reference_path(family):
                    errors += ["{}: {}: {}".format(family, p, e) for e in check_h5(got, m)]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return errors


# ---------------------------------------------------------------- the PR description

PREFIX = re.compile(r"^\s*(?:>\s*)*(?:(?:[-*+]|\d+[.)])\s+)?")
PUNCT = " \t-:;,.–—"


def declaration(line):
    """(requirement, rest of the line) if the line is a declaration, else None."""
    s = PREFIX.sub("", line, count=1).lstrip("*`")
    for req, kw in KEYWORDS.items():
        if s.startswith(kw) and not s[len(kw):len(kw) + 1].isalnum():
            return req, s[len(kw):].lstrip("*`").strip(PUNCT)
    return None


def parse_declarations(body):
    """{requirement: {"line": index, "justification": text}} of the first line of each declaration in body."""
    lines = body.splitlines()
    out = {}
    for i, line in enumerate(lines):
        hit = declaration(line)
        if not hit or hit[0] in out:
            continue
        req, text = hit
        if not text:
            nxt = next((x for x in lines[i + 1:] if x.strip()), "")
            if not declaration(nxt):
                text = PREFIX.sub("", nxt, count=1).strip(PUNCT + "*`")
        out[req] = {"line": i, "justification": text}
    return out


def named(text, item):
    """item appears in text as a whole token (a trailing sentence period is allowed)."""
    return re.search(r"(?<![\w./:=-])" + re.escape(item) + r"(?![\w/:=-]|\.\w)", text) is not None


def strip_noise(body):
    """The description without what a reader does not see as text: HTML comments (an unclosed one runs to the end) and
    fenced code blocks (``` or ~~~; an unclosed one runs to the end)."""
    body = re.sub(r"<!--.*?(?:-->|\Z)", "", body, flags=re.DOTALL)
    out, fence = [], None
    for line in body.splitlines():
        hit = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence is None and hit:
            fence = hit.group(1)
        elif fence is not None:
            if hit and hit.group(1)[0] == fence[0] and len(hit.group(1)) >= len(fence) \
                    and not line.strip().strip(fence[0]):
                fence = None
        else:
            out.append(line)
    return "\n".join(out)


def judge(found, errors, body):
    """The verdict: a dict with required, present, missing, items, missing_items, notes, codeowner_approval, errors."""
    body = strip_noise(body)
    required = {f.req for f in found if f.req}
    if LOOSENED in required:
        required.add(CHANGED)
    items = sorted({f.item for f in found if f.req == DEFAULT and f.item})
    decl = parse_declarations(body)
    missing, notes, missing_items = [], [], []
    for req in (DEFAULT, CHANGED, LOOSENED):
        if req not in required:
            if req in decl:
                notes.append("'{}' is declared but this change does not need it".format(KEYWORDS[req]))
            continue
        if req not in decl:
            missing.append(KEYWORDS[req])
        elif req == DEFAULT:
            rest = "\n".join(body.splitlines()[decl[req]["line"]:])
            missing_items = [it for it in items if not named(rest, it)]
        elif not decl[req]["justification"]:
            missing.append(KEYWORDS[req] + " (with a justification)")
    return {"required": [KEYWORDS[r] for r in (DEFAULT, CHANGED, LOOSENED) if r in required],
            "present": [KEYWORDS[r] for r in (DEFAULT, CHANGED, LOOSENED) if r in decl],
            "missing": missing, "items": items, "missing_items": missing_items, "notes": notes,
            "codeowner_approval": LOOSENED in required, "errors": errors,
            "findings": [f.as_dict() for f in found]}


def clean(text):
    """text with its control characters escaped (\\x0a), so that it stays one log line."""
    return CONTROL_RE.sub(lambda c: "\\x{:02x}".format(ord(c.group())), text)


def report(v, found, out):
    out("changes:" if found else "changes: nothing guarded")
    for f in found:
        out(f.line())
    out("required: {}".format(", ".join(v["required"]) or "nothing"))
    for n in v["notes"]:
        out("note: " + n)
    for m in v["missing"]:
        out("missing: " + m)
    if v["missing_items"]:
        out("missing: the changed items below the '{}' line; add:".format(KEYWORDS[DEFAULT]))
        out(KEYWORDS[DEFAULT])
        for it in v["missing_items"]:
            out("- " + it)
    if v["codeowner_approval"]:
        out(CODEOWNER)
    for e in v["errors"]:
        out("error: " + e)


def summary_md(v):
    lines = ["### yldot reference guard", "", "Required: {}".format(", ".join(v["required"]) or "nothing")]
    lines += ["- missing: `{}`".format(m) for m in v["missing"]]
    if v["missing_items"]:
        lines += ["- missing items below `{}`:".format(KEYWORDS[DEFAULT]), "", "```", KEYWORDS[DEFAULT]]
        lines += ["- " + it for it in v["missing_items"]] + ["```"]
    if v["codeowner_approval"]:
        lines.append("- **" + CODEOWNER + "**")
    lines += ["- error: {}".format(e) for e in v["errors"]]
    return "\n".join(clean(line) for line in lines) + "\n"


def check(repo, base, head, body, gh_repo=fetch_data.REPO, download=fetch_data.download, no_download=False,
          summary=None, json_out=None, out=print):
    """Returns the exit code."""
    emit, out = out, lambda line: emit(clean(line))
    try:
        base, head = commit(repo, base), commit(repo, head)
        mbase = merge_base(repo, base, head)
        found, verify, errors = guarded_paths(repo, mbase, head)
    except GuardError as e:
        out("error: {}".format(e))
        return 2
    out("reference guard: base {}, merge base {} .. head {}".format(base[:12], mbase[:12], head[:12]))
    if verify and no_download:
        out("note: external files not downloaded (--no-download): {}".format(
            ", ".join("{}: {}".format(f, p) for f, (_, ps) in sorted(verify.items()) for p in ps)))
    elif verify:
        errors += verify_externals(verify, gh_repo, download)
    v = judge(found, errors, body)
    report(v, found, out)
    if summary:
        with open(summary, "a") as f:
            f.write(summary_md(v))
    if json_out:
        Path(json_out).write_text(json.dumps(dict(v, base=base, merge_base=mbase, head=head), indent=2, sort_keys=True) + "\n")
    return 1 if v["missing"] or v["missing_items"] or v["errors"] else 0


# ---------------------------------------------------------------- history


def run(cmd):
    """(returncode, stdout, stderr) of a gh command."""
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def history(repo, rev, gh_repo=fetch_data.REPO, release_limit_mb=200.0, git_limit_mb=30.0, run=run, out=print):
    """Returns the exit code."""
    emit, out = out, lambda line: emit(clean(line))
    try:
        rev = commit(repo, rev)
        rc, listing, err = run(["gh", "release", "list", "-R", gh_repo, "--limit", "1000", "--json", "tagName"])
        if rc != 0:
            raise GuardError("gh release list failed: {}".format(err.strip()))
        tags = sorted((t["tagName"] for t in json.loads(listing) if mf.TAG_RE.match(t["tagName"])),
                      key=lambda t: int(t.rsplit("v", 1)[1]))
        sizes = {}
        for tag in tags:
            rc, view, err = run(["gh", "release", "view", tag, "-R", gh_repo, "--json", "assets"])
            if rc != 0:
                raise GuardError("gh release view {} failed: {}".format(tag, err.strip()))
            sizes[tag] = sum(a["size"] for a in json.loads(view)["assets"])
        at_rev = manifests_at(repo, rev)
        named_tags = {m["release"] for m, _ in at_rev.values() if m and m["release"]}
        invalid = sorted(problem for _, problem in at_rev.values() if problem)
        tree = 0
        for entry in git(repo, "ls-tree", "-r", "-l", "-z", rev, "--", GUARDED).decode().split("\0"):
            fields = entry.split(None, 4)
            if len(fields) == 5 and fields[1] == "blob":
                tree += int(fields[3])
        objects = git(repo, "rev-list", "--objects", rev, "--", GUARDED).decode().splitlines()
        shas = [o.split(" ", 1)[0] for o in objects if " " in o and o.split(" ", 1)[1].startswith(GUARDED)]
        blobs = 0
        if shas:  # a rev without a blob under tests/yldot has no history to size
            r = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch-check=%(objecttype) %(objectsize)"],
                               input="\n".join(shas) + "\n", capture_output=True, text=True)
            blobs = sum(int(f[1]) for f in (line.split() for line in r.stdout.splitlines())
                        if len(f) == 2 and f[0] == "blob")
    except GuardError as e:
        out("error: {}".format(e))
        return 2
    mb = 1e6
    total = sum(sizes.values())
    out("data releases: {} ({:.2f} MB in total; review limit {:.0f} MB)".format(len(tags), total / mb,
                                                                              release_limit_mb))
    for problem in invalid:
        out("error: manifest at {} is invalid: {}".format(rev[:12], problem))
    for tag in tags:
        out("  {}: {:.2f} MB{}".format(tag, sizes[tag] / mb, "" if tag in named_tags else
                                       " (uncertain: a manifest at {} is invalid, it may name this)".format(rev[:12])
                                       if invalid else " (orphan: no manifest at {} names it)".format(rev[:12])))
    out("tests/yldot in git at {}: {:.2f} MB in the tree (cap {:.0f} MB), {:.2f} MB of blobs in its history".format(
        rev[:12], tree / mb, git_limit_mb, blobs / mb))
    over = []
    if total > release_limit_mb * mb:
        over.append("the data releases exceed {:.0f} MB: owner review".format(release_limit_mb))
    if tree > git_limit_mb * mb:
        over.append("tests/yldot in git exceeds {:.0f} MB".format(git_limit_mb))
    for line in over:
        out("over limit: " + line)
    return 1 if over or invalid else 0


def main(argv, out=print):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="judge a PR's change against its description (PR_BODY)")
    c.add_argument("--base", required=True)
    c.add_argument("--head", required=True)
    c.add_argument("--no-download", action="store_true", help="skip the release-asset checks (local use only)")
    c.add_argument("--summary", help="append a Markdown summary (GITHUB_STEP_SUMMARY)")
    c.add_argument("--json", help="write the verdict as JSON")
    h = sub.add_parser("history", help="data-release and in-git sizes, orphan releases")
    h.add_argument("--rev", default="origin/v9-develop")
    h.add_argument("--release-limit-mb", type=float, default=200.0)
    h.add_argument("--git-limit-mb", type=float, default=30.0)
    for p in (c, h):
        p.add_argument("--repo", default=".", help="the git checkout to read (default: the current directory)")
        p.add_argument("--gh-repo", default=fetch_data.REPO, help="the GitHub repository holding the data releases")
    args = parser.parse_args(argv[1:])
    if args.cmd == "history":
        return history(args.repo, args.rev, args.gh_repo, args.release_limit_mb, args.git_limit_mb, out=out)
    body = os.environ.get("PR_BODY")
    if body is None:
        out("error: PR_BODY is not set (the PR description; empty is allowed)")
        return 2
    return check(args.repo, args.base, args.head, body, args.gh_repo, no_download=args.no_download,
                 summary=args.summary, json_out=args.json, out=out)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
