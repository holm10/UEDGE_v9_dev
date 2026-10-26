"""Generate the yldot suite's reference files from one commit: the defaults and the classified variants (epic AIUE-9,
PRD sections 7.2, 7.3 and 7.6; AIUE-88, AIUE-94).

Usage (from a checkout whose tests/yldot is the commit's, references/ aside):
    python make_references.py generate --from-commit SHA [--platform linux|host] [--release yldot-data-v<N>]
                                       [--out DIR] [--write] [--jobs N]
                                       [--defaults-only | --locality-only | --only VAR ... [--full]] [family ...]
    <built python> make_references.py _child family ... [--sweep all|none] [--only VAR ...] [--full]
                                       [--locality-only] [--jobs N] --out DIR --build FILE

generate  builds SHA --serial and, per family (default: every family with sigma.h5 that is not an owner family, the
          five small ones), evaluates the steady and timestep defaults with both Jacobian flags (harness/state.py, PRD
          section 6) and the diagnostics, then every variant of harness/variants.plan() in a fresh child each, and
          writes DIR/references/<family>.h5 (harness/store.py, with the family's sigma_i of families/<f>/sigma.h5,
          AIUE-87; a sketch store also its weights 1/tol_i, AIUE-174, and the default's sketch thresholds, PRD 7.11 d,
          AIUE-92) and the manifest with
          provenance and one entry per variant (harness/manifest.py). It prints each file's
          SHA-256 and size, the family's summary line (PRD section 5, story 3, with MARGINAL) and its cost. Only with
          --write does it copy the files to tests/yldot/references/ and write references/<family>.manifest.json,
          then open each through open_store as a check.
            --platform linux (default): a git archive of SHA, built and evaluated in the pinned image yldot-linux:24.04
                (tests/yldot/linux/Dockerfile, AIUE-87) by linux/generate.sh; the manifest's runner_image names the
                image id. The only release-grade path (owner, 2026-10-22, AIUE-88 D1), run by
                regenerate-references.yml on native amd64 (owner, 2026-10-25, AIUE-98; below).
            --platform host: a temporary worktree of SHA and a venv with the image's pins, built here. A preview:
                the manifest's release is null, and --release is refused (owner, 2026-10-22, AIUE-88 D2).
          --release names the data release the manifests point to; the files are published with release_data.py.
          --defaults-only: the defaults without the sweep (AIUE-88); never --writes over classified variants.
          --only VAR ...: the named variant ids or keys (a key: all its ids) are classified again; every other
                entry and its stored data are copied from the installed reference, whose defaults this build must
                reproduce bit for bit (exit 3 otherwise), so their SHA-256s stay identical (PRD 7.6).
          --full (with --only): also DIR/references/full/<family>.<id>.npz, the dense default and variant vectors
                with the row labels, for localization; never with --write.
          --locality-only: as --only with no variant named: every entry is copied and only the locality data (the
                default's pattern and the variants', PRD 7.5) is computed; every guarded SHA-256 of the installed
                reference must come out the same (exit 3 otherwise; AIUE-101).
          --jobs N: the child evaluates N families at once, one process each, largest first (default: its CPU count).
_child    runs inside the built environment and writes, from the build record FILE (JSON: commit, compiler,
          runner_image), DIR/<family>.h5, DIR/<family>.json (the manifest without release and external),
          <family>.findings.json, .summary, .cost.json and samples/<family>.npz (the tolerance-inheritance sample of
          tools/variant_tolerances.py).

Classification (PRD section 7.2; M_CLS = 100, tol_i the default's per-entry tolerance of the variant's
configuration, for yldot and yldot_J alike): SENSITIVE if some entry differs by more than M_cls*tol_i, then
evaluated a second time in another process, and stored only if both runs agree bit for bit (else INVALID
"nondeterministic", a finding: file a bugfix ticket). Both runs are children of the one forkserver that preloaded
uedge (harness/process.py), with the same heap and address layout, so the second run shows run-to-run nondeterminism
only: a result that depends on the build or on the memory layout (an uninitialised read; a bbb.ziin hydrogenic slot
set to 1 with isupgon(1) = 1, AIUE-179, is a suspect) is stable here and is found by replaying every stored variant
on other builds (tools/variant_tolerances.py replay) and by AIUE-95's audit. INERT if bitwise equal; MARGINAL if
0 < difference <= M_cls*tol_i; INVALID on an error (the reason holds the exception's text, for an xerrab the '***'
message of the child's log), crash, timeout, neq change, an equation layout change at the same neq (index arrays or
is*onxy masks; owner, 2026-10-22, AIUE-94 D4) or non-finite yldot; EXCLUDED as variants.plan() says, and where the
application changes nothing in the family (value equals d, no valid index, unallocated; owner, 2026-10-22, AIUE-94
D1). Results that fit no class (bitwise differences of size zero, a harness FamilyError such as variants.Mismatch)
and a reference file over its CAPS_MB cap (PRD 7.3) are findings for the epic owner (decision 23): generate prints
them and writes nothing (exit 3).

The container and the host venv run this working tree's harness and families against SHA's UEDGE, so generate
refuses unless tests/yldot (references/ excepted) is exactly SHA's: no difference, no untracked file, no ignored
file in the families' directories or data/, except an owner family's release assets (its manifest's
families/<f>/ externals, and its sigma.h5) at their recorded SHA-256s. A preview (no --release) never --writes over a
released manifest. It refuses a family without sigma.h5, whose sigma.h5 differs from tolerances.toml's SHA-256, or
whose manifest names release assets of another family. An owner family (manifest.owner_family: its grid, inputs and
states are release assets) is generated only when named, swept like the others (AIUE-99) or with --defaults-only;
its new manifest carries those assets and adds families/<f>/sigma.h5 (owner, 2026-10-22, AIUE-92 D6), all under
the new release. Every evaluation runs
in a fresh child process (harness/process.py). Writing the same results twice gives the same bytes
(track_times=False, variants in plan order). Two Linux runs from one commit gave the same SHA-256s on one host
(Docker Desktop, x86 emulation on Apple silicon, AIUE-88), and so did two native amd64 runs (AIUE-98). Native and
emulated runs of one commit and image differ in three variant vectors (d_only:bbb.ineudif, d_c:bbb.ineudif,
d_c:bbb.rtg2ti; cause not probed), so release-grade references come from .github/workflows/regenerate-references.yml
on native amd64 only (owner, 2026-10-25, AIUE-98); a local --platform linux run is a preview of them.

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
CAPS_MB = {"d_only": 2, "ortho": 2, "d_mols": 2, "d_c": 7, "slab_phi": 9,  # reference file caps, PRD 7.3; 10^6 bytes
           "large_dd2c": 13, "dnull_imp2": 13, "imp7": 13}  # owner, 2026-10-24 (AIUE-99; 9 MB in AIUE-92 B4)
# variants whose application changes nothing in the family: EXCLUDED (owner, 2026-10-22, AIUE-94 D1)
NOOP = {"equal-to-d": "value equals d", "no-valid-index": "no valid index", "unallocated": "unallocated"}
SKETCH_DEFAULT_RE = re.compile(r"/default/sketch_(weight$|threshold/)")  # a sketch store's, not the default's own
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


def variant_tolerance(fdir, ref, config, imap, suite=SUITE):
    """The per-entry tolerance a SENSITIVE variant is checked with (owner, 2026-10-22, AIUE-94 D8):
    tol_i(variant) = max(rtol_eq*|ref_i(variant)|, k*sigma_i), the PRD section 7.4 rule (compare.tolerances) with the
    variant's own stored yldot ref in the rtol term and the default's sigma_i of the variant's configuration
    (sigma.h5), floors as usual; for yldot and the flag difference alike. The classification against the default
    keeps tolerance() of the default (M_CLS * tol_i)."""
    return tolerance(fdir, ref, config, imap, suite)


def applied_record(data):
    """The variant's apply record (variants.apply): the POST one for a POST variant, else the PRE one."""
    v = data.get("variant") or {}
    return v.get("POST") or v.get("PRE")


def last_line(message):
    lines = [s for s in str(message).strip().splitlines() if s.strip()]
    return (lines[-1].strip() if lines else "")[:REASON_CHARS]


BARE_EXCEPTION = re.compile(r"^[A-Za-z_][\w.]*$")  # a traceback's last line without text, e.g. "RuntimeError"


ERROR_LINE = re.compile(r"\berror\b", re.IGNORECASE)


def logged_error(tail):
    """The message UEDGE printed before an xerrab, which Forthon raises as a bare RuntimeError: the last run of '***'
    lines in a child's log tail (blank lines inside it kept out), whitespace collapsed and joined by ' / '. If a line
    naming an error follows that run (a solver's own report, e.g. "Error return from ilut: ierr = -5" after the
    "**** mhdgeo=-1: cartesian grid generated *****" banner), the first such line instead. '' if there is neither."""
    lines = str(tail).splitlines()
    marked = [i for i, s in enumerate(lines) if s.lstrip().startswith("***")]
    after = marked[-1] + 1 if marked else 0
    later = [s for s in lines[after:] if ERROR_LINE.search(s)]
    if later:
        return " ".join(later[0].split())
    if not marked:
        return ""
    run = []
    for s in reversed(lines[:marked[-1] + 1]):
        if s.lstrip().startswith("***"):
            run.append(" ".join(s.split()))
        elif s.strip():
            break
    return " / ".join(reversed(run))


def error_reason(res):
    """The INVALID reason of a failed evaluation: its status and the exception's last line, with the log's '***'
    message (logged_error) when the exception carries no text (an xerrab), as "RuntimeError (log: ...)"."""
    text = last_line(res.message)
    if BARE_EXCEPTION.match(text):
        logged = logged_error(res.log_tail)
        if logged:
            text = "{} (log: {})".format(text, logged)
    return "{}: {}".format(res.status, text[:REASON_CHARS])


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
        return "INVALID", error_reason(res), None
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
    open_ = sum(f["id"] not in variables and not f["id"].startswith("locality:") for f in findings)
    line = "{}: {} variants: {} sensitive, {} inert, {} marginal, {} invalid, {} excluded; {} nondeterministic".format(
        name, len(variables) + open_, n["SENSITIVE"], n["INERT"], n["MARGINAL"], n["INVALID"], n["EXCLUDED"], nondet)
    return line + ("; {} unclassified (owner)".format(open_) if open_ else "")


def locality_labels(e, imap, n=3):
    """'column -> row' labels of the first n entries of locality Entries e, for a finding."""
    from yldot.harness.locality import short

    return "; ".join("{} -> {}".format(short(imap, c), short(imap, r)) for c, r in zip(e.column[:n], e.row[:n]))


def default_differences(fresh, stored, previous, data, sig):
    """Which of a stored default's datasets differ from this build's, and how (the --only refusal's detail)."""
    out = ["only stored: {}".format(sorted(set(stored) - set(fresh))) if set(stored) - set(fresh) else "",
           "only this build's: {}".format(sorted(set(fresh) - set(stored))) if set(fresh) - set(stored) else ""]
    for k in sorted(set(fresh) & set(stored)):
        if fresh[k] == stored[k]:
            continue
        config, what = k.split("/")[1], k.split("/")[3]  # /<config>/default/<yldot|sigma|jflag>[/...]
        d = data[config]
        if what == "jflag":
            i, v = jflag_sparse(d["yldot"], d["yldot_J"])
            new, old = np.zeros(len(d["yldot"])), previous.jflag(config)
            new[i] = v
        else:
            new = d["yldot"] if what == "yldot" else sig[config]
            old = previous.default(config) if what == "yldot" else previous.sigma(config)
        new, old = np.asarray(new, np.float64), np.asarray(old, np.float64)
        if new.shape != old.shape:
            out.append("{}: shape {}, stored {}".format(k, new.shape, old.shape))
            continue
        rows = np.flatnonzero(differs(new, old))
        out.append("{}: {} rows differ (first {}), max |diff| {:.3g}".format(
            k, rows.size, listed((rows[:5] + 1).tolist()), float(np.max(np.abs(new - old), initial=0.0))))
    return "; ".join(x for x in out if x)


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


def locality_tolerance(fdir, kind, e, run_yldot, base_yldot, stored_variant=None, suite=SUITE, imap=None):
    """The per-entry tolerance a variant's locality pattern is scored with (generation and test_locality alike): a
    sketch store's, tolerance() of the run's yldot (AIUE-99 Q2); a full store's SENSITIVE variant, variant_tolerance
    of its stored yldot (stored_variant); INERT and MARGINAL, the default's of the variant's configuration
    (base_yldot)."""
    if kind == "sketch":
        return tolerance(fdir, run_yldot, e["config"], imap, suite)
    if e["class"] == "SENSITIVE":
        return variant_tolerance(fdir, stored_variant, e["config"], imap, suite)
    return tolerance(fdir, base_yldot, e["config"], imap, suite)


def locality_columns(loc, variant=False):
    """The columns option of Runner.evaluate for a family's [locality] table: None (every column) or the table,
    which the child resolves on the live grid; a variant perturbs the special cells only (owner, 2026-10-25,
    AIUE-101 Q2)."""
    if loc is None or loc["columns"] == "all":
        return None
    return dict(loc, sample=0) if variant else loc


def child(families, out, build, sweep="all", only=None, full=False, suite=SUITE, repo=None, locality_only=False):
    """Evaluate and write each family's reference file and manifest fields into out.

    repo: the source tree of the built commit, whose */*.v files are the variant inventory (variants.plan; the
    container mounts only tests/, so its repository root holds no .v file); None: this tree's.

    sweep "all": classify every variant of variants.plan() (PRD section 7.2), SENSITIVE ones twice in separate
    processes; "none": the defaults only (AIUE-88); a list of ids or keys: those only (tests). only: --only, a list of
    ids or keys: those are classified again, every other entry is copied from the installed reference of suite (its
    stored default must be reproduced bit for bit). full: with only, the dense vectors of the selected variants in
    out/full/. locality_only: --only with no variant selected, so every entry is copied and only the locality data
    is computed; every guarded SHA-256 of the installed reference must come out the same (AIUE-101). Besides
    <family>.h5 and <family>.json, writes <family>.findings.json (results for the epic owner), .summary, .cost.json
    and samples/<family>.npz (the tolerance-inheritance sample, variant_tolerances.py).

    Locality (PRD 7.5; AIUE-100, AIUE-101), for a family with [locality]: the steady default over its columns
    (locality_columns), the entries with score > 1 stored; then, after the sweep, every variant of
    locality.variant_scope evaluated once more with its applied value replayed, its pattern scored with the
    tolerance it is checked with (a full store's SENSITIVE variant: variant_tolerance of its stored yldot; INERT and
    MARGINAL: the default's; a sketch store: tolerance() of the run's yldot, AIUE-99 Q2) and stored as its difference
    from the default pattern. Findings for the owner: stale columns, a failed run, and a default entry within 3x of
    M_loc (rule D3) unless [locality].near_margin records the owner's acceptance; the counts of such entries, the
    variants' included, go to <family>.locality.json (owner, 2026-10-25, AIUE-101: the 3x rule is the default's)."""
    import statistics

    from yldot.harness import FamilyError, Runner, compare, load_evaluation, locality, open_store, store, variants
    from yldot.harness.state import INDEX_ARRAYS

    if locality_only:
        if only is not None or sweep == "none" or full:
            raise Stop(2, "--locality-only takes no --only, --sweep none or --full")
        only = []
    rec = json.loads(Path(build).read_text())
    with open(suite / "tolerances.toml", "rb") as f:
        rtol = tomllib.load(f)["rtol"]
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    runner = Runner()
    plan = variants.plan() if repo is None else variants.plan(repo=Path(repo))
    inventory = {v.id for v in plan}
    by_id = {v.id: v for v in plan}
    scope = set(select_ids(plan, sweep)) if isinstance(sweep, (list, tuple)) else None
    selected = set(select_ids(plan, only)) if only is not None else None
    if scope is not None:
        plan = [v for v in plan if v.id in scope]
    for name in families:
        fdir = family_dir(name)
        with open(fdir / "family.toml", "rb") as f:
            kind = tomllib.load(f)["family"]["store"]
        loc = locality.load_config(fdir)
        timeout = TIMEOUT_FACTOR * float(load_evaluation(fdir)["timeout_s"])
        walls = []
        data = {}
        for config in mf.CONFIG_NAMES:
            delta = loc["delta_loc"] if loc is not None and config == "steady" else None
            r = runner.evaluate(name, config=config, diagnostics=True, timeout=timeout, locality=delta,
                                columns=locality_columns(loc) if delta is not None else None)
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
            # a sketch store's weights are kept from it and its thresholds follow from them and the defaults
            # (below), so they are not part of the defaults' check (AIUE-99)
            stored = {k: s for k, s in previous.manifest["datasets"].items() if "/default/" in k
                      and "/diagnostics/" not in k and not SKETCH_DEFAULT_RE.search(k)}
            fresh = default_shas(data, sig)
            if fresh != stored:
                raise Stop(3, "{}: the stored default differs from this build's (--only needs the same defaults): "
                              "regenerate in full; {}".format(name, default_differences(fresh, stored, previous,
                                                                                         data, sig)))
            stale = sorted(set(previous.manifest["variables"]) - inventory)
            if stale:
                raise Stop(1, "{}: the manifest has entries no longer in the inventory, {}: prune them first "
                              "(AIUE-95)".format(name, listed(stale)))
        w = store.create(out / "{}.h5".format(name), kind, name, data["steady"], imap)
        for config, d in data.items():
            w.write_default(config, d["yldot"], d["yldot_J"], sig[config], d["diagnostics"])
            if kind == "sketch":  # PRD 7.11 (d), AIUE-92: what one entry or cell must move for the sketch to see it;
                # the weights (AIUE-174): 1/tol_i, or with --only the stored ones, which its copied variants are in
                keep = previous.weights(config) if previous is not None and previous.kind == "sketch" else None
                w.write_sketch_thresholds(config, tolerance(fdir, d["yldot"], config, imap, suite), keep)
        if loc is not None:  # the locality pattern (PRD 7.5; AIUE-100): the entries with score > 1
            run = data["steady"]["locality"]
            if run["stale"].size:
                raise Stop(2, "{}: {} stale locality columns (first rows {}): ask the epic owner (decision 23)".format(
                    name, run["stale"].size, run["stale"][:10] + 1))
            t = tolerance(fdir, data["steady"]["yldot"], "steady", imap, suite)
            rteq = locality.rtol_rows(rtol, imap)
            default_p = locality.pattern(locality.Entries.of(run["entries"]), t, rteq)
            w.write_locality("steady", run["delta"], default_p, columns=run["columns"])
        variables, findings, kept = {}, [], {}
        near_counts = {}  # entries within 3x of M_loc: "default" and per variant (written to <family>.locality.json)
        if loc is not None:
            near = locality.near_margin(default_p, t, rteq, float(loc["m_loc"]))
            near_counts["default"] = len(near)
            if len(near) and "near_margin" not in loc:
                findings.append({"id": "locality:default", "finding": "owner: {} default locality entries within 3x "
                                 "of M_loc (rule D3), first {}".format(len(near), locality_labels(near, imap))})
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
                    try:  # forked from the same forkserver: run-to-run nondeterminism only (module docstring)
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
        if loc is not None and sweep != "none":
            special = None
            if loc["columns"] != "all":
                special = locality.special_columns(dict(data["steady"], neq=imap.neq))
            base_p = locality.variant_base(default_p, special)
            for vid in locality.variant_scope(loc, variables):
                e = variables[vid]
                try:
                    r = runner.evaluate(name, variant=by_id[vid], replay=e["applied"], timeout=timeout,
                                        locality=loc["delta_loc"], columns=locality_columns(loc, variant=True))
                except FamilyError as ex:
                    findings.append({"id": vid, "finding": "owner: locality: {}".format(last_line(ex))})
                    continue
                walls.append(r.wall_s)
                if not r.ok:
                    findings.append({"id": vid, "finding": "owner: locality run {}: {}".format(r.status,
                                                                                               error_reason(r))})
                    continue
                lrun = r.data["locality"]
                if lrun["stale"].size:
                    findings.append({"id": vid, "finding": "owner: {} stale locality columns".format(
                        lrun["stale"].size)})
                    continue
                ref = None
                if kind == "full" and e["class"] == "SENSITIVE":
                    ref = kept[vid]["yldot"] if vid in kept else previous.variant(e["config"], vid)[0]
                tv = locality_tolerance(fdir, kind, e, r.data["yldot"], data[e["config"]]["yldot"], ref, suite, imap)
                pv = locality.pattern(locality.Entries.of(lrun["entries"]), tv, rteq)
                near = locality.near_margin(pv, tv, rteq, float(loc["m_loc"]))
                if len(near):  # counted only: the 3x rule calibrates delta on the default (owner, AIUE-101)
                    near_counts[vid] = len(near)
                w.write_locality_variant(e["config"], vid, *locality.diff(base_p, pv))
        written = w.finish()
        prev_guarded = previous.manifest["guarded"] if previous is not None else None
        if previous is not None:
            previous.close()
        for vid, e in variables.items():
            if e["class"] == "SENSITIVE":
                e["sha256"] = mf.variant_sha(written["datasets"], e["config"], vid)
        guarded, unguarded = mf.summarize(written["datasets"])
        if locality_only:  # only locality data may be new (AIUE-101): every installed guarded SHA-256 stays
            moved = sorted(k for k, s in prev_guarded.items() if guarded.get(k) != s)
            if moved:
                raise Stop(3, "{}: --locality-only moved the guarded {} of the installed reference: regenerate in "
                              "full".format(name, moved))
        fields = {"schema": mf.SCHEMA, "family": name, "store": kind, "datasets": written["datasets"],
                  "guarded": guarded, "unguarded": unguarded, "variables": variables,
                  "provenance": mf.provenance(rec["commit"], rec["compiler"], FLAGS, rec["runner_image"])}
        if kind == "sketch":
            fields["sketch"] = {"k": store.K, "seed": store.SEED}
        if written["locality_variants"]:
            fields["locality_variants"] = written["locality_variants"]
        (out / "{}.json".format(name)).write_text(mf.dumps(fields))
        (out / "{}.findings.json".format(name)).write_text(json.dumps(findings, indent=1) + "\n")
        if near_counts:
            (out / "{}.locality.json".format(name)).write_text(json.dumps({"near_margin": near_counts}, indent=1,
                                                                          sort_keys=True) + "\n")
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


def family_weight(name):
    """The size of a family's reference_state.h5, a proxy for its neq (0 if absent): parallel_children starts the
    largest first, so the longest family bounds the wall time."""
    p = family_dir(name) / "reference_state.h5"
    return p.stat().st_size if p.exists() else 0


def child_argv(args, family):
    """The _child command line for one family of a parallel run (args: the parsed _child options)."""
    cmd = [sys.executable, str(Path(__file__).resolve()), "_child", family, "--out", args.out, "--build", args.build,
           "--sweep", args.sweep, "--jobs", "1"]
    cmd += (["--only"] + list(args.only) if args.only else []) + (["--full"] if args.full else [])
    cmd += (["--repo", args.repo] if args.repo else []) + (["--locality-only"] if args.locality_only else [])
    return cmd


def parallel_children(args, popen=subprocess.Popen, poll_s=1.0):
    """_child --jobs N: one process per family, at most N at a time, largest first (each family's files are its
    own); a freed slot starts the next family at once. Stop with exit 2 if any family failed with an error (2 or
    another code), else 3 if any reported findings for the owner, listing every family; on an exception the running
    children are killed."""
    import time

    queue = sorted(args.family, key=lambda f: (-family_weight(f), f))
    running, failed = [], []
    try:
        while queue or running:
            while queue and len(running) < args.jobs:
                name = queue.pop(0)
                running.append((name, popen(child_argv(args, name))))
            done = [(n, p) for n, p in running if p.poll() is not None]
            if not done:
                time.sleep(poll_s)
                continue
            for n, p in done:
                running.remove((n, p))
                if p.returncode != 0:
                    failed.append((n, p.returncode))
    finally:
        for _, p in running:
            p.kill()
    if failed:
        code = 3 if all(c == 3 for _, c in failed) else 2
        raise Stop(code, "families failed: {}".format(", ".join("{} (exit {})".format(n, c) for n, c in failed)))


# ---------------------------------------------------------------- host side: checks


def resolve(commit, root, run=run):
    rc, out, err = run(["git", "-C", str(root), "rev-parse", "--verify", "{}^{{commit}}".format(commit)])
    if rc != 0:
        raise Stop(1, "--from-commit {}: not a commit ({})".format(commit, err.strip()))
    return out.strip()


def check_tree(sha, root, families, run=run, allowed=()):
    """tests/yldot in the working tree is sha's, references/ excepted, and no ignored file sits where an evaluation of
    the families reads (their directories, data/; __pycache__ excepted) but the paths allowed (owner_assets)."""
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
        if line.startswith("!!") and path in allowed:
            continue
        if not line.startswith("!!") or path.startswith(read):  # ignored files elsewhere (.data/, owner assets)
            extra.append(path)
    if extra:
        raise Stop(1, "tests/yldot holds files {} does not: {}".format(sha[:12], ", ".join(extra[:10])))


def select(families, suite):
    """The families to generate (default: the small ones, every family with sigma.h5 that is not an owner family),
    checked: sigma.h5 as tolerances.toml records it, no release assets but the reference file and its own."""
    fams = suite / "families"
    if not families:
        families = sorted(p.name for p in fams.iterdir()
                          if (p / "sigma.h5").is_file() and not mf.owner_family(p.name, suite))
    with open(suite / "tolerances.toml", "rb") as f:
        recorded = tomllib.load(f).get("sigma", {})
    problems = []
    for name in families:
        fdir = fams / name
        if not (fdir / "input.py").is_file():
            problems.append("{}: no such family".format(name))
            continue
        if not (fdir / "sigma.h5").is_file():
            problems.append("{}: no sigma.h5 (its round-off is not measured, or the file is not fetched: "
                            "tools/fetch_data.py)".format(name))
            continue
        want = recorded.get(name, {}).get("sha256")
        if file_sha256(fdir / "sigma.h5") != want:
            problems.append("{}: sigma.h5 differs from tolerances.toml's SHA-256 {}".format(name, want))
        if mf.path(name, suite).is_file():
            m = mf.load(name, suite)
            other = sorted(set(m["external"]) - {mf.reference_path(name)} - set(mf.family_assets(m)))
            if other:
                problems.append("{}: its manifest names release assets of other families {}".format(name, other))
    if problems:
        raise Stop(1, "; ".join(problems))
    return list(families)


def sigma_path(name):
    return "families/{}/sigma.h5".format(name)


def owner_assets(families, suite):
    """{family: {path: {sha256, bytes}}} of the owner families among families: their manifest's families/<f>/
    externals, each checked in the working tree (links resolved) against its recorded SHA-256 and size, and
    families/<f>/sigma.h5 (already checked against tolerances.toml by select). The new manifest's externals besides
    the reference file (owner, 2026-10-22, AIUE-92 D6); check_tree allows these ignored files."""
    out, problems = {}, []
    for name in families:
        if not mf.owner_family(name, suite):
            continue
        m = mf.load(name, suite)
        carried = {}
        for p in mf.family_assets(m):
            if p == sigma_path(name):
                continue  # re-recorded below from the file select checked
            f, e = suite / p, m["external"][p]
            if not f.is_file():
                problems.append("{} is missing or a dangling link: run tools/fetch_data.py {}".format(p, name))
            elif (file_sha256(f), f.stat().st_size) != (e["sha256"], e["bytes"]):
                problems.append("{} differs from its manifest's SHA-256 or size".format(p))
            carried[p] = dict(e)
        s = suite / sigma_path(name)
        if not s.is_file():
            problems.append("{} is missing or a dangling link: run tools/fetch_data.py {}".format(sigma_path(name),
                                                                                              name))
        else:
            carried[sigma_path(name)] = {"sha256": file_sha256(s), "bytes": s.stat().st_size}
        out[name] = carried
    if problems:
        raise Stop(1, "; ".join(problems))
    return out


# ---------------------------------------------------------------- host side: builds


def base_image(suite):
    """The FROM line of linux/Dockerfile: the base image by digest."""
    hit = re.search(r"^FROM\s+(\S+)", (suite / "linux" / "Dockerfile").read_text(), re.MULTILINE)
    return hit.group(1)


def child_options(args):
    """The _child options of a generate run: the sweep, --only and --full."""
    jobs = ["--jobs", str(args.jobs)] if args.jobs else []
    if args.defaults_only:
        return ["--sweep", "none"] + jobs
    if args.locality_only:
        return ["--locality-only"] + jobs
    return (["--only"] + list(args.only) if args.only else []) + (["--full"] if args.full else []) + jobs


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
        # PWD for the build only: setup.py before AIUE-163 converts and makes in getenv("PWD"), not the cwd, and
        # --from-commit may name such a commit
        if stream(pip + ["install", "-v", "--no-build-isolation", "--no-deps", ".", "-C",
                         "--build-option={}".format(FLAGS)], cwd=src, env=dict(env, PWD=str(src)),
                  log=out / "build.log") != 0:
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


def assemble(sha, families, out, release, assets=None):
    """({family: manifest}, findings) from the child's files in out/references; prints each family's summary and
    cost. findings: the child's (variants for the epic owner) and every reference file over its PRD 7.3 cap. assets:
    owner_assets, the externals an owner family's manifest carries besides the reference file."""
    manifests, findings = {}, []
    assets = assets or {}
    for name in families:
        h5, js = out / "references" / "{}.h5".format(name), out / "references" / "{}.json".format(name)
        if not (h5.is_file() and js.is_file()):
            raise Stop(2, "{}: the child wrote no {} and {}".format(name, h5.name, js.name))
        m = mf.loads(js.read_text())
        if m["provenance"]["commit"] != sha:
            raise Stop(2, "{}: provenance commit {} is not {}".format(name, m["provenance"]["commit"], sha))
        m["release"] = release
        m["external"] = dict({mf.reference_path(name): {"sha256": file_sha256(h5), "bytes": h5.stat().st_size}},
                             **assets.get(name, {}))
        mf.validate(m)
        manifests[name] = m
        ref = out / "references"
        for f in json.loads((ref / "{}.findings.json".format(name)).read_text()):  # with --sweep none: locality's
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
        if (ref / "{}.locality.json".format(name)).is_file():
            near = json.loads((ref / "{}.locality.json".format(name)).read_text())["near_margin"]
            print("  locality entries within 3x of M_loc: {}".format(
                ", ".join("{} {}".format(k, v) for k, v in sorted(near.items(), key=lambda kv: kv[0] != "default"))))
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
    if sum(bool(x) for x in (args.only, args.defaults_only, args.locality_only)) > 1:
        raise Stop(2, "two of --only, --defaults-only and --locality-only together: pick one")
    sha = resolve(args.from_commit, root, run)
    families = select(args.family, suite)
    assets = owner_assets(families, suite)
    check_tree(sha, root, families, run, {"tests/yldot/" + p for a in assets.values() for p in a})
    if args.defaults_only and args.write:
        swept = [f for f in families if mf.path(f, suite).is_file() and mf.load(f, suite).get("variables")]
        if swept:
            raise Stop(1, "--defaults-only --write would drop the classified variants of {}".format(", ".join(swept)))
    if args.only or args.locality_only:
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
    manifests, findings = assemble(sha, families, out, args.release, assets)
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
    p.add_argument("--locality-only", action="store_true",
                   help="copy the installed references and compute only the locality data (AIUE-101)")
    p.add_argument("--jobs", type=int, help="families evaluated in parallel by the child (default: the CPU count)")
    p = sub.add_parser("_child", help="inside the built environment: evaluate and write")
    p.add_argument("family", nargs="+")
    p.add_argument("--out", required=True)
    p.add_argument("--build", required=True, help="JSON: commit, compiler, runner_image")
    p.add_argument("--sweep", choices=("all", "none"), default="all")
    p.add_argument("--only", nargs="+")
    p.add_argument("--full", action="store_true")
    p.add_argument("--repo", help="the built commit's source tree: its .v files are the inventory")
    p.add_argument("--locality-only", action="store_true")
    p.add_argument("--jobs", type=int, default=os.cpu_count() or 1,
                   help="families in parallel, one process each, largest first (default: the CPU count)")
    args = parser.parse_args(argv[1:])
    try:
        if args.cmd == "_child" and args.jobs > 1 and len(args.family) > 1:
            parallel_children(args)
        elif args.cmd == "_child":
            child(args.family, args.out, args.build, sweep=args.sweep, only=args.only, full=args.full,
                  repo=args.repo, locality_only=args.locality_only)
        else:
            generate(args)
    except (Stop, mf.ManifestError) as e:
        print(str(e), file=sys.stderr)
        return getattr(e, "code", 2)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
