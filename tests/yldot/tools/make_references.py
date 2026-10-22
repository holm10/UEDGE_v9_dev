"""Generate the yldot suite's reference files from one commit: the defaults and the classified variants (epic AIUE-9,
PRD sections 7.2, 7.3 and 7.6; AIUE-88, AIUE-94).

Usage (from a checkout whose tests/yldot is the commit's, references/ aside):
    python make_references.py generate --from-commit SHA [--platform linux|host] [--release yldot-data-v<N>]
                                       [--out DIR] [--write] [--defaults-only | --only VAR ... [--full]]
                                       [family ...]
    <built python> make_references.py _child family ... [--sweep all|none] [--only VAR ...] [--full]
                                       --out DIR --build FILE

generate  builds SHA --serial and, per family (default: every family with sigma.h5, the five small ones), evaluates
          the steady and timestep defaults with both Jacobian flags (harness/state.py, PRD section 6) and the
          diagnostics, then every variant of harness/variants.plan() in a fresh child each, and writes
          DIR/references/<family>.h5 (harness/store.py, with the family's sigma_i of families/<f>/sigma.h5, AIUE-87)
          and the manifest with provenance and one entry per variant (harness/manifest.py). It prints each file's
          SHA-256 and size, the family's summary line (PRD section 5, story 3, with MARGINAL) and its cost. Only with
          --write does it copy the files to tests/yldot/references/ and write references/<family>.manifest.json,
          then open each through open_store as a check.
            --platform linux (default): a git archive of SHA, built and evaluated in the pinned image yldot-linux:24.04
                (tests/yldot/linux/Dockerfile, AIUE-87) by linux/generate.sh; the manifest's runner_image names the
                image id. The only release-grade references (owner, 2026-10-22, AIUE-88 D1).
            --platform host: a temporary worktree of SHA and a venv with the image's pins, built here. A preview:
                the manifest's release is null, and --release is refused (owner, 2026-10-22, AIUE-88 D2).
          --release names the data release the manifests point to; the files are published with release_data.py.
          --defaults-only: the defaults without the sweep (AIUE-88); never --writes over classified variants.
          --only VAR ...: the named variant ids or keys (a key: all its ids) are classified again; every other
                entry and its stored data are copied from the installed reference, whose defaults this build must
                reproduce bit for bit (exit 3 otherwise), so their SHA-256s stay identical (PRD 7.6).
          --full (with --only): also DIR/references/full/<family>.<id>.npz, the dense default and variant vectors
                with the row labels, for localization; never with --write.
_child    runs inside the built environment and writes, from the build record FILE (JSON: commit, compiler,
          runner_image), DIR/<family>.h5, DIR/<family>.json (the manifest without release and external),
          <family>.findings.json, .summary, .cost.json and samples/<family>.npz (the tolerance-inheritance sample of
          tools/variant_tolerances.py).

Classification (PRD section 7.2; M_CLS = 100, tol_i the default's per-entry tolerance of the variant's
configuration, for yldot and yldot_J alike): SENSITIVE if some entry differs by more than M_cls*tol_i, then
evaluated a second time in another process, and stored only if both runs agree bit for bit (else INVALID
"nondeterministic", a finding: file a bugfix ticket); INERT if bitwise equal; MARGINAL if 0 < difference <=
M_cls*tol_i; INVALID on an error, crash, timeout, neq change, an equation layout change at the same neq (index arrays
or is*onxy masks; owner, 2026-10-22, AIUE-94 D4) or non-finite yldot; EXCLUDED as variants.plan() says, and where the
application changes nothing in the family (value equals d, no valid index, unallocated; owner, 2026-10-22, AIUE-94
D1). Results that fit no class (bitwise differences of size zero, a harness FamilyError such as variants.Mismatch)
and a reference file over its CAPS_MB cap (PRD 7.3) are findings for the epic owner (decision 23): generate prints
them and writes nothing (exit 3).

The container and the host venv run this working tree's harness and families against SHA's UEDGE, so generate
refuses unless tests/yldot (references/ excepted) is exactly SHA's: no difference, no untracked file, no ignored
file in the families' directories or data/. A preview (no --release) never --writes over a released manifest. It
refuses a family without sigma.h5, whose sigma.h5 differs from tolerances.toml's SHA-256, or whose manifest names
release assets other than its reference file (the owner families' grids and states: AIUE-92). Every evaluation runs
in a fresh child process (harness/process.py). Writing the same results twice gives the same bytes
(track_times=False, variants in plan order). Two Linux runs from one commit gave the same SHA-256s on one host
(Docker Desktop, x86 emulation on Apple silicon, AIUE-88); whether a native amd64 host reproduces them bit for bit
(glibc picks libm variants by CPU) is AIUE-98's check.

Exit codes: 0 done; 1 refused; 2 usage, a failed build or a failed evaluation; 3 findings for the epic owner.
"""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # tests/, for the yldot package

import numpy as np  # noqa: E402

from yldot.harness import manifest as mf  # noqa: E402
from yldot.harness.compare import listed  # noqa: E402
from yldot.harness.process import family_dir  # noqa: E402
from yldot.harness.store import SEED, dataset_sha256, differs, file_sha256, jflag_sparse  # noqa: E402

SUITE = Path(__file__).resolve().parents[1]
IMAGE = "yldot-linux:24.04"
PINS = ("setuptools==84.2.1", "forthon==0.10.10", "numpy==2.5.4", "h5py==3.16.0")  # linux/Dockerfile, the image's
FLAGS = "--serial"
TIMEOUT_FACTOR = 5  # x family.toml timeout_s per child: x86 emulation runs slower (measure_roundoff.py)
M_CLS = 100.0  # the classification margin (PRD section 7.2)
CAPS_MB = {"d_only": 2, "ortho": 2, "d_mols": 2, "d_c": 7, "slab_phi": 9}  # reference file caps, PRD 7.3; 10^6 bytes
# variants whose application changes nothing in the family: EXCLUDED (owner, 2026-10-22, AIUE-94 D1)
NOOP = {"equal-to-d": "value equals d", "no-valid-index": "no valid index", "unallocated": "unallocated"}
SAMPLE_N = 20  # the tolerance-inheritance sample per family, plus every SENSITIVE timestep variant (PRD 7.4; D2)
REASON_CHARS = 300


class Stop(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def run(cmd, cwd=None):
    """(returncode, stdout, stderr) of a git or docker query."""
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return r.returncode, r.stdout, r.stderr


def stream(cmd, cwd=None, env=None, log=None):
    """Return code of a long command (build, container), its output to the terminal or to the file log."""
    if log is None:
        return subprocess.run(cmd, cwd=cwd, env=env).returncode
    with open(log, "w") as f:
        return subprocess.run(cmd, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT).returncode


# ---------------------------------------------------------------- child side


def sigma(fdir, config):
    import h5py

    with h5py.File(fdir / "sigma.h5", "r") as f:
        return f[config]["sigma"][()]


def same_index(a, b):
    from yldot.harness.state import INDEX_ARRAYS, MASK_ARRAYS

    return (a["neq"] == b["neq"] and all(np.array_equal(a[n], b[n]) for n in INDEX_ARRAYS)
            and all(np.array_equal(a["masks"][n], b["masks"][n]) for n in MASK_ARRAYS))


def tolerance(fdir, yldot, config, imap, suite=SUITE):
    """The per-entry tolerance tol_i of the default yldot (PRD section 7.4), from sigma.h5 and tolerances.toml."""
    from yldot.harness import compare

    with open(suite / "tolerances.toml", "rb") as f:
        t = tomllib.load(f)
    return compare.tolerances(yldot, sigma(fdir, config), t["rtol"], t["rule"]["k"], imap).tol


def applied_record(data):
    """The variant's apply record (variants.apply): the POST one for a POST variant, else the PRE one."""
    v = data.get("variant") or {}
    return v.get("POST") or v.get("PRE")


def last_line(message):
    lines = [s for s in str(message).strip().splitlines() if s.strip()]
    return (lines[-1].strip() if lines else "")[:REASON_CHARS]


def layout_changes(a, b):
    """The index arrays and equation masks that differ between two runs of the same neq."""
    from yldot.harness.state import INDEX_ARRAYS, MASK_ARRAYS

    out = [n for n in INDEX_ARRAYS if not np.array_equal(a[n], b[n])]
    return out + [n for n in MASK_ARRAYS if not np.array_equal(a["masks"][n], b["masks"][n])]


def classify(res, base, tol, m_cls=M_CLS):
    """(class, reason, finding) of one variant evaluation against the default data base of its configuration (PRD
    section 7.2). tol: the default's per-entry tolerance, used for yldot and yldot_J alike (PRD 7.3). A finding (an
    irregular result for the epic owner, decision 23) has no class: (None, None, text)."""
    if not res.ok:
        return "INVALID", "{}: {}".format(res.status, last_line(res.message)), None
    d = res.data
    rec = applied_record(d)
    if rec is not None and rec["status"] in NOOP:
        why = NOOP[rec["status"]]
        if "bound" in rec:
            why += " (bound {})".format(rec["bound"])
        return "EXCLUDED", "not applicable in {}: {}".format(res.family, why), None
    if d["neq"] != base["neq"]:
        return "INVALID", "neq {} -> {}".format(base["neq"], d["neq"]), None
    changed = layout_changes(d, base)
    if changed:  # the rows mean other equations: like a neq change (owner, 2026-10-22, AIUE-94 D4)
        return "INVALID", "equation layout changed ({}) at the same neq".format(", ".join(changed)), None
    y, yj = np.asarray(d["yldot"], np.float64), np.asarray(d["yldot_J"], np.float64)
    bad = np.flatnonzero(~(np.isfinite(y) & np.isfinite(yj)))
    if bad.size:
        return "INVALID", "non-finite yldot or yldot_J at rows {}".format(listed((bad + 1).tolist())), None
    if not (differs(y, base["yldot"]).any() or differs(yj, base["yldot_J"]).any()):
        return "INERT", "", None
    r = max(float((np.abs(y - base["yldot"]) / tol).max()), float((np.abs(yj - base["yldot_J"]) / tol).max()))
    if r > m_cls:
        return "SENSITIVE", "max |diff|/tol = {:.3g}".format(r), None
    if r == 0:
        return None, None, "bitwise differences of size zero only (signed zeros)"
    return "MARGINAL", ("max |diff|/tol = {:.3g} <= M_cls = {:g}: treated as EXCLUDED until an override gives a "
                        "larger value (PRD 7.2)".format(r, m_cls)), None


def entry(v, cls, reason, rec=None, sha=None, l2=None):
    """A manifest variables entry (harness/manifest.py); l2: (block_l2, jflag_block_l2)."""
    return {"class": cls, "reason": reason, "applied": rec.get("applied") if rec else None,
            "d": rec.get("d") if rec else None, "phase": v.phase, "config": v.config, "sha256": sha,
            "block_l2": l2[0] if l2 else {}, "jflag_block_l2": l2[1] if l2 else {}}


def norms(w, res, base):
    """(block_l2, jflag_block_l2) of a variant against the default (test_store_unit.py's pattern)."""
    from yldot.harness import store

    y, yj = res.data["yldot"], res.data["yldot_J"]
    return (store.block_l2(y - base["yldot"], w.labels, w.rows),
            store.block_l2((yj - y) - (base["yldot_J"] - base["yldot"]), w.labels, w.rows))


def same_run(a, b):
    """Rows where two evaluations of one variant differ (yldot or yldot_J, bitwise), or None if their apply
    records or status differ."""
    if a.status != b.status or not (a.ok and b.ok):
        return None
    if json.dumps(a.data.get("variant"), sort_keys=True) != json.dumps(b.data.get("variant"), sort_keys=True):
        return None
    if a.data["neq"] != b.data["neq"]:
        return None
    return np.flatnonzero(differs(a.data["yldot"], b.data["yldot"]) | differs(a.data["yldot_J"], b.data["yldot_J"]))


def tolerance_sample(sensitive, timestep, seed=SEED, n=SAMPLE_N):
    """The tolerance-inheritance sample (PRD 7.4; owner, 2026-10-22, AIUE-94 D2): the n SENSITIVE ids with the
    smallest sha256("<seed>:<id>"), plus every SENSITIVE timestep id, in the order given."""
    ranked = sorted(sensitive, key=lambda vid: hashlib.sha256("{}:{}".format(seed, vid).encode()).hexdigest())
    pick = set(ranked[:n]) | set(timestep)
    return [vid for vid in sensitive if vid in pick]


def select_ids(plan, only):
    """The ids of plan that --only names (a key names all its ids); Stop if one names nothing."""
    ids = []
    for name in only:
        hit = [v.id for v in plan if v.id == name or v.key == name]
        if not hit:
            raise Stop(1, "--only {}: no such variant id or key in the inventory".format(name))
        ids += [i for i in hit if i not in ids]
    return ids


def summary(name, variables, findings):
    """The per-family line (PRD section 5, story 3, with MARGINAL)."""
    n = {c: sum(e["class"] == c for e in variables.values()) for c in mf.CLASSES}
    nondet = sum(f["finding"].startswith("nondeterministic") for f in findings)
    line = "{}: {} variants: {} sensitive, {} inert, {} marginal, {} invalid, {} excluded; {} nondeterministic".format(
        name, len(variables) + sum(f["id"] not in variables for f in findings), n["SENSITIVE"], n["INERT"],
        n["MARGINAL"], n["INVALID"], n["EXCLUDED"], nondet)
    open_ = sum(f["id"] not in variables for f in findings)
    return line + ("; {} unclassified (owner)".format(open_) if open_ else "")


def default_shas(data, sig):
    """The dataset SHA-256s a default writes (store.Writer.write_default), to check a stored default against."""
    out = {}
    for config, d in data.items():
        i, v = jflag_sparse(d["yldot"], d["yldot_J"])
        base = "/{}/default/".format(config)
        out.update({base + "yldot": dataset_sha256(np.ascontiguousarray(d["yldot"], np.float64)),
                    base + "sigma": dataset_sha256(np.ascontiguousarray(sig[config], np.float64)),
                    base + "jflag/index": dataset_sha256(i), base + "jflag/value": dataset_sha256(v)})
    return out


def child(families, out, build, sweep="all", only=None, full=False, suite=SUITE, repo=None):
    """Evaluate and write each family's reference file and manifest fields into out.

    repo: the source tree of the built commit, whose */*.v files are the variant inventory (variants.plan; the
    container mounts only tests/, so its repository root holds no .v file); None: this tree's.

    sweep "all": classify every variant of variants.plan() (PRD section 7.2), SENSITIVE ones twice in separate
    processes; "none": the defaults only (AIUE-88); a list of ids or keys: those only (tests). only: --only, a list of
    ids or keys: those are classified again, every other entry is copied from the installed reference of suite (its
    stored default must be reproduced bit for bit). full: with only, the dense vectors of the selected variants in
    out/full/. Besides <family>.h5 and <family>.json, writes <family>.findings.json (results for the epic owner),
    .summary, .cost.json and samples/<family>.npz (the tolerance-inheritance sample, variant_tolerances.py)."""
    import statistics

    from yldot.harness import FamilyError, Runner, compare, load_evaluation, open_store, store, variants
    from yldot.harness.state import INDEX_ARRAYS

    rec = json.loads(Path(build).read_text())
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    runner = Runner()
    plan = variants.plan() if repo is None else variants.plan(repo=Path(repo))
    inventory = {v.id for v in plan}
    scope = set(select_ids(plan, sweep)) if isinstance(sweep, (list, tuple)) else None
    selected = set(select_ids(plan, only)) if only is not None else None
    if scope is not None:
        plan = [v for v in plan if v.id in scope]
    for name in families:
        fdir = family_dir(name)
        with open(fdir / "family.toml", "rb") as f:
            kind = tomllib.load(f)["family"]["store"]
        timeout = TIMEOUT_FACTOR * float(load_evaluation(fdir)["timeout_s"])
        walls = []
        data = {}
        for config in mf.CONFIG_NAMES:
            r = runner.evaluate(name, config=config, diagnostics=True, timeout=timeout)
            if not r.ok:
                raise Stop(2, "{} {}: {} {}\n{}".format(name, config, r.status, r.message, r.log_tail))
            walls.append(r.wall_s)
            data[config] = r.data
        if not same_index(data["steady"], data["timestep"]):
            raise Stop(2, "{}: the steady and timestep runs have different index arrays".format(name))
        imap = compare.index_map(data["steady"], compare.load_regions(fdir))
        sig = {config: sigma(fdir, config) for config in mf.CONFIG_NAMES}
        previous = None
        if only is not None:
            previous = open_store(name, suite)
            stored = {k: s for k, s in previous.manifest["datasets"].items() if "/default/" in k
                      and "/diagnostics/" not in k}
            if default_shas(data, sig) != stored:
                raise Stop(3, "{}: the stored default differs from this build's (--only needs the same defaults): "
                              "regenerate in full".format(name))
            stale = sorted(set(previous.manifest["variables"]) - inventory)
            if stale:
                raise Stop(1, "{}: the manifest has entries no longer in the inventory, {}: prune them first "
                              "(AIUE-95)".format(name, listed(stale)))
        w = store.create(out / "{}.h5".format(name), kind, name, data["steady"], imap)
        for config, d in data.items():
            w.write_default(config, d["yldot"], d["yldot_J"], sig[config], d["diagnostics"])
        variables, findings, kept = {}, [], {}
        if sweep != "none":
            tol = {config: tolerance(fdir, d["yldot"], config, imap) for config, d in data.items()}
            for v in plan:
                if selected is not None and v.id not in selected:
                    e = previous.manifest["variables"].get(v.id)
                    if e is None:
                        raise Stop(1, "{}: --only needs every other variant in the manifest; {} has none: "
                                      "regenerate in full".format(name, v.id))
                    if e["class"] == "SENSITIVE":
                        w.copy_variant(e["config"], v.id, previous)
                    variables[v.id] = e
                    continue
                if v.excluded:
                    variables[v.id] = entry(v, "EXCLUDED", v.reason)
                    continue
                try:
                    r = runner.evaluate(name, variant=v, timeout=timeout)
                except FamilyError as e:
                    findings.append({"id": v.id, "finding": "owner: {}".format(last_line(e))})
                    continue
                walls.append(r.wall_s)
                base = data[v.config]
                cls, reason, finding = classify(r, base, tol[v.config])
                if finding is not None:
                    findings.append({"id": v.id, "finding": finding})
                    continue
                rec_v = applied_record(r.data) if r.ok else None
                if cls == "SENSITIVE":
                    try:
                        again = runner.evaluate(name, variant=v, timeout=timeout)
                    except FamilyError as e:
                        findings.append({"id": v.id, "finding": "owner: {}".format(last_line(e))})
                        continue
                    walls.append(again.wall_s)
                    rows = same_run(r, again)
                    if rows is None or rows.size:
                        what = ("{} rows differ".format(rows.size) if rows is not None
                                else "the status, apply record or neq differs")
                        reason = "nondeterministic: {} between two processes".format(what)
                        findings.append({"id": v.id, "finding": "nondeterministic: {}; file a bugfix ticket".format(
                            what)})
                        variables[v.id] = entry(v, "INVALID", reason, rec_v)
                        continue
                    w.write_variant(v.config, v.id, r.data["yldot"], r.data["yldot_J"])
                    kept[v.id] = r.data
                    variables[v.id] = entry(v, "SENSITIVE", reason, rec_v, sha="", l2=norms(w, r, base))
                elif cls == "MARGINAL":
                    variables[v.id] = entry(v, cls, reason, rec_v, l2=norms(w, r, base))
                else:
                    variables[v.id] = entry(v, cls, reason, rec_v)
                if full and selected is not None and r.ok:
                    (out / "full").mkdir(exist_ok=True)
                    np.savez(out / "full" / "{}.{}.npz".format(name, v.id), default=base["yldot"],
                             default_J=base["yldot_J"], yldot=r.data["yldot"], yldot_J=r.data["yldot_J"],
                             labels=np.array([imap.label(i) for i in range(imap.neq)]))
        written = w.finish()
        if previous is not None:
            previous.close()
        for vid, e in variables.items():
            if e["class"] == "SENSITIVE":
                e["sha256"] = mf.variant_sha(written["datasets"], e["config"], vid)
        guarded, unguarded = mf.summarize(written["datasets"])
        fields = {"schema": mf.SCHEMA, "family": name, "store": kind, "datasets": written["datasets"],
                  "guarded": guarded, "unguarded": unguarded, "variables": variables,
                  "provenance": mf.provenance(rec["commit"], rec["compiler"], FLAGS, rec["runner_image"])}
        if kind == "sketch":
            fields["sketch"] = {"k": store.K, "seed": store.SEED}
        (out / "{}.json".format(name)).write_text(mf.dumps(fields))
        (out / "{}.findings.json".format(name)).write_text(json.dumps(findings, indent=1) + "\n")
        line = summary(name, variables, findings)
        (out / "{}.summary".format(name)).write_text(line + "\n")
        cost = {"evaluations": len(walls), "child_wall_s": round(sum(walls), 3),
                "median_s": round(statistics.median(walls), 4), "max_s": round(max(walls), 4)}
        (out / "{}.cost.json".format(name)).write_text(json.dumps(cost, sort_keys=True) + "\n")
        sens = [vid for vid, e in variables.items() if e["class"] == "SENSITIVE" and vid in kept]
        sample = tolerance_sample(sens, [vid for vid in sens if variables[vid]["config"] == "timestep"])
        if sample:
            (out / "samples").mkdir(exist_ok=True)
            np.savez(out / "samples" / "{}.npz".format(name), ids=np.array(sample),
                     configs=np.array([variables[vid]["config"] for vid in sample]),
                     yldot=np.array([kept[vid]["yldot"] for vid in sample]),
                     yldot_J=np.array([kept[vid]["yldot_J"] for vid in sample]),
                     **{"tol_" + c: tol[c] for c in mf.CONFIG_NAMES},
                     **{n: np.asarray(data["steady"][n]) for n in INDEX_ARRAYS})
        print("{}: {} {} bytes".format(name, written["sha256"], written["bytes"]), flush=True)
        print(line, flush=True)


# ---------------------------------------------------------------- host side: checks


def resolve(commit, root, run=run):
    rc, out, err = run(["git", "-C", str(root), "rev-parse", "--verify", "{}^{{commit}}".format(commit)])
    if rc != 0:
        raise Stop(1, "--from-commit {}: not a commit ({})".format(commit, err.strip()))
    return out.strip()


def check_tree(sha, root, families, run=run):
    """tests/yldot in the working tree is sha's, references/ excepted, and no ignored file sits where an evaluation of
    the families reads (their directories, data/; __pycache__ excepted)."""
    rc, _, err = run(["git", "-C", str(root), "diff", "--quiet", sha, "--", "tests/yldot",
                      ":(exclude)tests/yldot/references"])
    if rc == 1:
        raise Stop(1, "tests/yldot differs from {} (references/ excepted): commit it, or generate from the commit "
                      "the working tree holds".format(sha[:12]))
    if rc != 0:
        raise Stop(2, "git diff failed: {}".format(err.strip()))
    rc, out, err = run(["git", "-C", str(root), "status", "--porcelain", "--ignored", "--untracked-files=all", "--",
                        "tests/yldot"])
    if rc != 0:
        raise Stop(2, "git status failed: {}".format(err.strip()))
    read = tuple("tests/yldot/families/{}/".format(f) for f in families) + ("tests/yldot/data/",)
    extra = []
    for line in out.splitlines():
        path = line[3:]
        if path.startswith("tests/yldot/references/") or "__pycache__/" in path:
            continue
        if not line.startswith("!!") or path.startswith(read):  # ignored files elsewhere (.data/, owner assets)
            extra.append(path)
    if extra:
        raise Stop(1, "tests/yldot holds files {} does not: {}".format(sha[:12], ", ".join(extra[:10])))


def select(families, suite):
    """The families to generate, checked: sigma.h5 as tolerances.toml records it, no release assets but the
    reference file."""
    fams = suite / "families"
    if not families:
        families = sorted(p.name for p in fams.iterdir() if (p / "sigma.h5").is_file())
    with open(suite / "tolerances.toml", "rb") as f:
        recorded = tomllib.load(f).get("sigma", {})
    problems = []
    for name in families:
        fdir = fams / name
        if not (fdir / "input.py").is_file():
            problems.append("{}: no such family".format(name))
            continue
        if not (fdir / "sigma.h5").is_file():
            problems.append("{}: no sigma.h5 (its round-off is not measured yet: AIUE-92 for the owner families)"
                            .format(name))
            continue
        want = recorded.get(name, {}).get("sha256")
        if file_sha256(fdir / "sigma.h5") != want:
            problems.append("{}: sigma.h5 differs from tolerances.toml's SHA-256 {}".format(name, want))
        if mf.path(name, suite).is_file():
            other = sorted(set(mf.load(name, suite)["external"]) - {mf.reference_path(name)})
            if other:
                problems.append("{}: its manifest names release assets {}; moving them is AIUE-92's".format(
                    name, other))
    if problems:
        raise Stop(1, "; ".join(problems))
    return list(families)


# ---------------------------------------------------------------- host side: builds


def base_image(suite):
    """The FROM line of linux/Dockerfile: the base image by digest."""
    hit = re.search(r"^FROM\s+(\S+)", (suite / "linux" / "Dockerfile").read_text(), re.MULTILINE)
    return hit.group(1)


def child_options(args):
    """The _child options of a generate run: the sweep, --only and --full."""
    if args.defaults_only:
        return ["--sweep", "none"]
    return (["--only"] + list(args.only) if args.only else []) + (["--full"] if args.full else [])


def build_linux(sha, families, out, suite, root, run=run, stream=stream, opts=()):
    rc, image_id, _ = run(["docker", "image", "inspect", "--format", "{{.Id}}", IMAGE])
    if rc != 0:
        raise Stop(1, "image {} not found: docker build --platform linux/amd64 -t {} tests/yldot/linux".format(
            IMAGE, IMAGE))
    rc, _, err = run(["git", "-C", str(root), "archive", "--format=tar", "-o", str(out / "src.tar"), sha])
    if rc != 0:
        raise Stop(2, "git archive failed: {}".format(err.strip()))
    runner_image = "{} {} ({})".format(IMAGE, image_id.strip(), base_image(suite))
    cmd = ["docker", "run", "--rm", "--platform", "linux/amd64", "-v", "{}:/tests:ro".format(suite.parent),
           "-v", "{}:/out".format(out), IMAGE, "bash", "/tests/yldot/linux/generate.sh", sha, runner_image]
    cmd += families + list(opts)
    print(" ".join(cmd), flush=True)
    if stream(cmd) != 0:
        raise Stop(2, "the container failed (build log: {})".format(out / "build.log"))


def build_host(sha, families, out, root, run=run, stream=stream, opts=()):
    src, venv = out / "src", out / "venv"
    rc, _, err = run(["git", "-C", str(root), "worktree", "add", "--detach", str(src), sha])
    if rc != 0:
        raise Stop(2, "git worktree add failed: {}".format(err.strip()))
    try:
        if stream([sys.executable, "-m", "venv", str(venv)]) != 0:
            raise Stop(2, "python -m venv failed")
        # the venv first on PATH: Forthon3 otherwise resolves to another Python (../venvs/base-a8446eb.BUILD.txt)
        env = dict(os.environ, PATH="{}{}{}".format(venv / "bin", os.pathsep, os.environ.get("PATH", "")),
                   OMP_NUM_THREADS="1")
        pip = [str(venv / "bin" / "python"), "-m", "pip"]
        if stream(pip + ["install", "-q"] + list(PINS), env=env) != 0:
            raise Stop(2, "pip install {} failed".format(" ".join(PINS)))
        if stream(pip + ["install", "-v", "--no-build-isolation", "--no-deps", ".", "-C",
                         "--build-option={}".format(FLAGS)], cwd=src, env=env, log=out / "build.log") != 0:
            raise Stop(2, "the build failed (log: {})".format(out / "build.log"))
        rc, gf, _ = run(["gfortran", "--version"])
        rec = {"commit": sha, "compiler": gf.splitlines()[0] if rc == 0 and gf else "unknown",
               "runner_image": "host {} {} python {} (preview)".format(sys.platform, platform.machine(),
                                                                        platform.python_version())}
        (out / "build.json").write_text(json.dumps(rec, indent=1) + "\n")
        cmd = [str(venv / "bin" / "python"), str(Path(__file__).resolve()), "_child"] + families + list(opts) + [
            "--repo", str(src), "--out", str(out / "references"), "--build", str(out / "build.json")]
        if stream(cmd, cwd=out, env=env) != 0:
            raise Stop(2, "the evaluation failed")
    finally:
        run(["git", "-C", str(root), "worktree", "remove", "--force", str(src)])


# ---------------------------------------------------------------- host side: manifests


def assemble(sha, families, out, release):
    """({family: manifest}, findings) from the child's files in out/references; prints each family's summary and
    cost. findings: the child's (variants for the epic owner) and every reference file over its PRD 7.3 cap."""
    manifests, findings = {}, []
    for name in families:
        h5, js = out / "references" / "{}.h5".format(name), out / "references" / "{}.json".format(name)
        if not (h5.is_file() and js.is_file()):
            raise Stop(2, "{}: the child wrote no {} and {}".format(name, h5.name, js.name))
        m = json.loads(js.read_text())
        if m["provenance"]["commit"] != sha:
            raise Stop(2, "{}: provenance commit {} is not {}".format(name, m["provenance"]["commit"], sha))
        m["release"] = release
        m["external"] = {mf.reference_path(name): {"sha256": file_sha256(h5), "bytes": h5.stat().st_size}}
        mf.validate(m)
        manifests[name] = m
        ref = out / "references"
        for f in json.loads((ref / "{}.findings.json".format(name)).read_text()) if m["variables"] else []:
            findings.append("{} {}: {}".format(name, f["id"], f["finding"]))
        cap = CAPS_MB.get(name)
        size = h5.stat().st_size
        if cap is None:
            findings.append("{}: no cap recorded (PRD 7.3)".format(name))
        elif size > cap * 10 ** 6:
            findings.append("{}: {} is {} bytes, over its {} MB cap (PRD 7.3: the epic owner decides)".format(
                name, mf.reference_path(name), size, cap))
        if (ref / "{}.summary".format(name)).is_file():
            print((ref / "{}.summary".format(name)).read_text().strip())
            cost = json.loads((ref / "{}.cost.json".format(name)).read_text())
            print("  {} bytes of {} MB; {} evaluations, {} s in children (median {} s, max {} s)".format(
                size, cap, cost["evaluations"], cost["child_wall_s"], cost["median_s"], cost["max_s"]))
    return manifests, findings


def install(manifests, out, suite):
    from yldot.harness import open_store

    for name, m in manifests.items():
        target = suite / mf.reference_path(name)
        if target.is_symlink() or target.exists():
            target.unlink()  # a fetched file is a link into .data/<tag>/: never write through it
        shutil.copyfile(out / "references" / "{}.h5".format(name), target)
        mf.dump(m, mf.path(name, suite))
        open_store(name, suite).close()


def generate(args, suite=SUITE, run=run, stream=stream):
    root = suite.parents[1]
    if args.release is not None and not mf.TAG_RE.match(args.release):
        raise Stop(2, "--release {!r}, need yldot-data-v<N>".format(args.release))
    if args.platform == "host" and args.release is not None:
        raise Stop(1, "--platform host makes previews only (release null; owner, AIUE-88 D2): drop --release")
    if args.full and not args.only:
        raise Stop(2, "--full needs --only")
    if args.full and args.write:
        raise Stop(2, "--full writes localization vectors, never references: drop --write")
    if args.only and args.defaults_only:
        raise Stop(2, "--only and --defaults-only together")
    sha = resolve(args.from_commit, root, run)
    families = select(args.family, suite)
    check_tree(sha, root, families, run)
    if args.defaults_only and args.write:
        swept = [f for f in families if mf.path(f, suite).is_file() and mf.load(f, suite).get("variables")]
        if swept:
            raise Stop(1, "--defaults-only --write would drop the classified variants of {}".format(", ".join(swept)))
    if args.only:
        from yldot.harness import StoreError, open_store

        for f in families:
            try:
                with open_store(f, suite) as s:
                    if not s.manifest["variables"]:
                        raise StoreError("{}: its manifest holds no classified variants".format(f))
            except (StoreError, OSError) as e:
                raise Stop(1, "--only regenerates against the installed references: {}".format(e))
    if args.write and args.release is None:
        released = [f for f in families if mf.path(f, suite).is_file() and mf.load(f, suite)["release"] is not None]
        if released:
            raise Stop(1, "a preview never replaces released references ({}): drop --write".format(
                ", ".join(released)))
    out = Path(args.out or tempfile.mkdtemp(prefix="yldot-references-")).resolve()
    if out.exists() and any(out.iterdir()):
        raise Stop(1, "--out {} is not empty".format(out))
    out.mkdir(parents=True, exist_ok=True)
    if args.platform == "linux":
        build_linux(sha, families, out, suite, root, run, stream, child_options(args))
    else:
        build_host(sha, families, out, root, run, stream, child_options(args))
    manifests, findings = assemble(sha, families, out, args.release)
    for name, m in manifests.items():
        e = m["external"][mf.reference_path(name)]
        print("{}  {}  {} bytes".format(e["sha256"], mf.reference_path(name), e["bytes"]))
    if findings:
        raise Stop(3, "{} findings for the epic owner (decision 23), nothing written; the preview is in {}:\n  {}"
                   .format(len(findings), out, "\n  ".join(findings)))
    if args.write:
        install(manifests, out, suite)
        print("wrote {} reference files and manifests (release {})".format(len(manifests), args.release))
    else:
        print("preview in {} (--write copies it to tests/yldot/references)".format(out))


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("generate", help="build a commit and write its default references")
    p.add_argument("family", nargs="*", help="default: every family with sigma.h5")
    p.add_argument("--from-commit", required=True)
    p.add_argument("--platform", choices=("linux", "host"), default="linux")
    p.add_argument("--release", help="yldot-data-v<N>, the release the manifests name (linux only)")
    p.add_argument("--out", help="an empty or new working directory (default: a temporary one)")
    p.add_argument("--write", action="store_true", help="copy to tests/yldot/references and write the manifests")
    p.add_argument("--defaults-only", action="store_true", help="the defaults only, no variant sweep (AIUE-88)")
    p.add_argument("--only", nargs="+", metavar="VAR", help="regenerate these variant ids or keys only")
    p.add_argument("--full", action="store_true", help="with --only: the dense vectors in --out/references/full")
    p = sub.add_parser("_child", help="inside the built environment: evaluate and write")
    p.add_argument("family", nargs="+")
    p.add_argument("--out", required=True)
    p.add_argument("--build", required=True, help="JSON: commit, compiler, runner_image")
    p.add_argument("--sweep", choices=("all", "none"), default="all")
    p.add_argument("--only", nargs="+")
    p.add_argument("--full", action="store_true")
    p.add_argument("--repo", help="the built commit's source tree: its .v files are the inventory")
    args = parser.parse_args(argv[1:])
    try:
        if args.cmd == "_child":
            child(args.family, args.out, args.build, sweep=args.sweep, only=args.only, full=args.full,
                  repo=args.repo)
        else:
            generate(args)
    except (Stop, mf.ManifestError) as e:
        print(str(e), file=sys.stderr)
        return getattr(e, "code", 2)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
