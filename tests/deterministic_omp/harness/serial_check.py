"""Serial old-vs-new bitwise check (AIUE-53): does a change leave serial results bit for bit as they were?

  python tests/deterministic_omp/harness/serial_check.py \\
      --base-python BASE_SERIAL/bin/python --new-python NEW_SERIAL/bin/python \\
      --base-omp-python BASE_OMP/bin/python --new-omp-python NEW_OMP/bin/python \\
      [--cases all|quick|NAME,NAME,...] [--jobs N] [--partial-ok] --out DIR

Runs every case once per build, each in a fresh `python -I` process with an empty HOME, on the
serial path (ppp.OMPParallelJac = ppp.OMPParallelPandf1 = 0, Nthreads = 1, OMP_NUM_THREADS = 1;
checked in every record), and compares new against base with the AIUE-49 comparator
(compare.compare_records): every Jacobian the records hold (the post-exmain bbb.jac, and the raw
sfsetnk/psetnk Jacobians of the AIUE-47 capture hook when both builds have it), sfscal, suscal,
yldot, one more RHS through ffun, the final fnrm (float.hex) and the printed fnrm sequence.
Bitwise: +0.0 and -0.0 differ, any NaN/Inf fails. Cases ending in -itN run N Newton iterations,
so that psetnk, the ILU preconditioner, the Krylov solve and the line search are covered too.

Pairs: "serial" (--base-python vs --new-python, the --serial builds) and "omp0" (--base-omp-python
vs --new-omp-python, the default OpenMP builds with both switches 0).

Before running, every interpreter is probed (build_probe.py): path, uedge.__file__, version,
SHA-256 of the compiled extensions, OpenMP or not, and the source tree pip installed it from
(direct_url.json), whose git HEAD and dirty state are read now (at check time, not build time).
Harness errors: a build of the wrong kind for its pair; base and new the same build, the same source
tree, or the same clean commit (unless --allow-same-build). Warnings: a base HEAD that is not
origin/v9-develop or an ancestor of it, an unknown source, serial/OpenMP builds of different commits.

The gate is complete only with both pairs, base and new different builds, and every case of "all".
Anything less that agrees prints RESULT: INCOMPLETE and exits 2, unless --partial-ok (exit 0, and the
RESULT line says PARTIAL and why).

Cases (--list): reproducer presets (repro-*, config.PRESETS, serial arm) and upstream pytests
cases (pytests-*, run as their test_reference does, pytests_worker.py), plus ad hoc names
repro:<preset>[@itN] and pytests:<path below pytests/>[@itN]. The pytests checkout is --pytests-dir,
else $UEDGE_PYTESTS_DIR, else ../uedge-pytests or ../../uedge-pytests next to the repository.

Writes DIR/serial_check.json (builds, sources, cases, every report), DIR/summary.txt, and the runs
under DIR/<pair>/<base|new>/<case>/. record.npz of agreeing cases is deleted unless --keep-records.
Exit codes: 0 the complete gate agrees (or a --partial-ok run agrees), 1 at least one mismatch,
2 harness error or incomplete gate (an error wins over a mismatch).
"""
import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from urllib.parse import unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from harness.cli import exit_code  # noqa: E402
from harness.compare import compare_records, format_report  # noqa: E402
from harness.config import PRESETS, RunSpec  # noqa: E402
from harness.runner import REPO_DIR, HarnessError, Record, parse_iterations, run_spec  # noqa: E402

CRUMPET = ["rates/aph/crumpet_nrates.dat", "rates/aph/crumpet_Erates.dat"]  # base builds before AIUE-110 read them from cwd
CAPTURE_SLOTS = 16  # raw Jacobians kept per run with the AIUE-47 hook (more is a harness error)
BASE_REF = "origin/v9-develop"

# name -> case. kind "repro": a reproducer preset on the serial arm. kind "pytests": a case directory
# of the upstream pytests checkout; add_files are repository files copied next to it. itermx: exactly N
# Newton iterations (config.force_newton) instead of one evaluation at ftol=1e20.
CASES = {}
for _p in PRESETS:
    CASES["repro-" + _p] = {"kind": "repro", "preset": _p}
CASES.update({
    "repro-tebox-it5": {"kind": "repro", "preset": "tebox", "itermx": 5},
    "repro-te-it3": {"kind": "repro", "preset": "te", "itermx": 3},
    "repro-full-it3": {"kind": "repro", "preset": "full", "itermx": 3},
    "pytests-D_only": {"kind": "pytests", "path": "unittests/D_only/nonog/default"},
    "pytests-D+C": {"kind": "pytests", "path": "unittests/D+C/nonog_carbon/default"},
    "pytests-D_mols": {"kind": "pytests", "path": "unittests/D_mols/nonog_mols/default", "add_files": CRUMPET},
    "pytests-full-d_c-16x8": {"kind": "pytests", "path": "fulltests/nonog_d_c-fb_16x8"},
    "pytests-D_mols-drift": {"kind": "pytests", "path": "unittests/D_mols/nonog_mols/tg_mol_atoms_drift",
                             "add_files": CRUMPET},
    "pytests-orthogonal": {"kind": "pytests", "path": "fulltests/orthogonal_unittest"},
    "pytests-slab": {"kind": "pytests", "path": "unittests/slab_D_only/slab/default"},
})
for _name in ("D_only", "D+C", "D_mols", "full-d_c-16x8", "slab"):
    CASES["pytests-{}-it5".format(_name)] = dict(CASES["pytests-" + _name], itermx=5)
# boundary-condition, transport and drift variants of the D_only and D_mols families (one switch each)
UNIT = ["istewc3", "istiwc4", "isnwcono3", "isnwconi2", "istepfc2", "isupwo3", "isupwi3", "recycmlb_therm_momflux",
        "recycmrb", "tg_atom_drifts", "tg_atom_istgwc2", "newbcl_iskaplex", "isnewpot", "ishosor", "curcore",
        "convis", "isfdiax", "isvylog", "core_nogradient"]
for _v in UNIT:
    CASES["pytests-unit-" + _v] = {"kind": "pytests", "path": "unittests/D_only/nonog/" + _v}
CASES["pytests-unit-tg_mol_istgpfc4"] = {"kind": "pytests", "path": "unittests/D_mols/nonog_mols/tg_mol_istgpfc4",
                                         "add_files": CRUMPET}

QUICK = ["repro-tebox", "repro-tebox-it5", "pytests-D_only", "pytests-D+C", "pytests-D_mols", "pytests-full-d_c-16x8",
         "pytests-D_only-it5", "pytests-D+C-it5"]
# slowest first, so that parallel jobs finish together
ALL = (["repro-full-it3", "repro-full", "repro-ni", "repro-up", "repro-te_phi", "repro-te-it3", "repro-ti", "repro-te",
        "repro-ng",
        "pytests-full-d_c-16x8-it5", "pytests-slab-it5", "repro-tebox-it5", "repro-tebox", "pytests-full-d_c-16x8",
        "pytests-D+C-it5", "pytests-D_mols-it5", "pytests-D_only-it5", "pytests-slab", "pytests-D+C",
        "pytests-D_only", "pytests-D_mols", "pytests-D_mols-drift"]
       + sorted(n for n in CASES if n.startswith("pytests-unit-")))
# Cases that fail on v9-develop itself (0fac655), in both builds: left out of "all", still runnable by name.
EXCLUDED = {
    "pytests-orthogonal": "input.py stops with 'ueinit -- error in sign sx, sy' on builds before AIUE-110",
}
assert sorted(ALL + list(EXCLUDED)) == sorted(CASES) and not set(ALL) & set(EXCLUDED) and set(QUICK) <= set(ALL)

PAIRS = {"serial": ("base_python", "new_python", False), "omp0": ("base_omp_python", "new_omp_python", True)}


# ------------------------------------------------------------------ environment
def clean_env(home, threads=1, stacksize="512M"):
    """The runner's environment: no OMP_/GOMP_/KMP_/PYTHON* variables, empty HOME, pinned threads."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("OMP_", "GOMP_", "KMP_", "PYTHON"))}
    env.update({"HOME": home, "OMP_NUM_THREADS": str(threads), "OMP_STACKSIZE": stacksize})
    return env


def find_pytests_dir(arg=None):
    candidates = [arg] if arg else []
    candidates += [os.environ.get("UEDGE_PYTESTS_DIR")] if os.environ.get("UEDGE_PYTESTS_DIR") else []
    if not arg:
        for up in ("..", os.path.join("..", "..")):
            candidates.append(os.path.join(REPO_DIR, up, "uedge-pytests"))
    for c in candidates:
        for d in (c, os.path.join(c, "pytests")):
            if os.path.isdir(os.path.join(d, "unittests")):
                return os.path.normpath(d)
    raise HarnessError("no pytests checkout found (tried {}); create one with "
                       "'git worktree add --detach ../uedge-pytests origin/pytests' or pass --pytests-dir"
                       .format(candidates))


def git(path, *args):
    """(returncode, stdout) of git -C path args; (None, "") if git cannot run."""
    try:
        p = subprocess.run(["git", "-C", path] + list(args), capture_output=True, text=True, timeout=30)
        return p.returncode, p.stdout.strip()
    except Exception:
        return None, ""


def git_head(path):
    code, out = git(path, "rev-parse", "HEAD")
    return out if code == 0 and out else "unknown"


ADHOC = re.compile(r"^(repro|pytests):([^@]+)(?:@it(\d+))?$")


def resolve_cases(text):
    """Case names for --cases (quick, all, or a comma list); ad hoc names are added to CASES."""
    if text == "quick":
        return list(QUICK)
    if text == "all":
        return list(ALL)
    names = [n.strip() for n in text.split(",") if n.strip()]
    unknown = []
    for n in names:
        if n in CASES:
            continue
        m = ADHOC.match(n)
        if m and m.group(1) == "repro" and m.group(2) in PRESETS:
            CASES[n] = {"kind": "repro", "preset": m.group(2)}
        elif m and m.group(1) == "pytests":
            CASES[n] = {"kind": "pytests", "path": m.group(2).strip("/")}
            if "D_mols" in m.group(2):
                CASES[n]["add_files"] = CRUMPET
        else:
            unknown.append(n)
            continue
        if m.group(3):
            CASES[n]["itermx"] = int(m.group(3))
    if unknown or not names:
        raise HarnessError("unknown case(s) {}; known: quick, all, {}, repro:<preset>[@itN], "
                           "pytests:<path>[@itN]".format(unknown, ", ".join(sorted(CASES))))
    return names


# ------------------------------------------------------------------ builds
def probe_build(python, workdir, timeout=300):
    """Run build_probe.py with `python` in a fresh process. Returns the probe dict."""
    if not (os.path.isfile(python) and os.access(python, os.X_OK)):
        raise HarnessError("not an executable interpreter: {}".format(python))
    os.makedirs(workdir)
    home = os.path.join(workdir, "home")
    os.makedirs(home)
    out = os.path.join(workdir, "probe.json")
    with open(os.path.join(workdir, "probe.log"), "wb") as log:
        proc = subprocess.run([python, "-I", os.path.join(HERE, "build_probe.py"), out], cwd=workdir,
                              env=clean_env(home), stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
    if not os.path.exists(out):
        raise HarnessError("build probe of {} exited with {} and wrote nothing (see {})".format(
            python, proc.returncode, workdir))
    with open(out) as f:
        result = json.load(f)
    if "error" in result or proc.returncode != 0:
        raise HarnessError("build probe of {} failed:\n{}".format(python, result.get("error")))
    result["python_arg"] = python
    return result


def source_info(probe):
    """Where the build came from: the source directory in pip's direct_url.json, its git HEAD,
    whether it has uncommitted changes, and whether HEAD is BASE_REF or an ancestor of it.
    All read now, at check time."""
    du = probe.get("direct_url") or {}
    url = du.get("url", "")
    info = {"url": url or None, "editable": bool(du.get("dir_info", {}).get("editable")), "dir": None,
            "head": None, "head_time": None, "dirty": None, "on_base_ref": None}
    parsed = urlparse(url)
    if parsed.scheme != "file":
        return info
    path = os.path.realpath(unquote(parsed.path))
    info["dir"] = path
    if not os.path.isdir(path):
        return info
    code, head = git(path, "rev-parse", "HEAD")
    if code != 0 or not head:
        return info
    info["head"] = head
    code, ct = git(path, "log", "-1", "--format=%ct", head)
    info["head_time"] = int(ct) if code == 0 and ct.isdigit() else None
    code, status = git(path, "status", "--porcelain", "--untracked-files=no")
    info["dirty"] = bool(status) if code == 0 else None
    code, _ = git(path, "merge-base", "--is-ancestor", head, BASE_REF)
    info["on_base_ref"] = {0: True, 1: False}.get(code)
    return info


def is_stale(build):
    """True if the source HEAD was committed after the build's extensions were written: the HEAD
    read now may then not be what was built."""
    s = build.get("source") or {}
    t, m = s.get("head_time"), build.get("extensions_mtime")
    return t is not None and m is not None and t > m


def check_pair(pair, base, new, want_openmp, allow_same):
    """(errors, warnings, gate, same) for a base/new build pair.
    errors: wrong build kind; the same build, source tree or clean commit twice (unless allow_same).
    gate: reasons the run cannot be the gate (-> INCOMPLETE): an unknown source, a dirty tree, a base
    that is not BASE_REF or an ancestor of it (or the check failed), a build older than its HEAD.
    same: True if base and new are the same build/source (allowed with allow_same)."""
    errors, warnings, gate, same = [], [], [], []
    for role, b in (("base", base), ("new", new)):
        if b["openmp_build"] != want_openmp:
            errors.append("{} {} build {} is {}an OpenMP build; the {} pair needs {}".format(
                pair, role, b["python_arg"], "" if b["openmp_build"] else "not ", pair,
                "the default OpenMP build" if want_openmp else "the --serial build"))
    if base["extensions_sha256"] == new["extensions_sha256"]:
        same.append("the same build (extension SHA-256 {}; base {}, new {})".format(
            base["extensions_sha256"][:16], base["uedge_file"], new["uedge_file"]))
    sb, sn = base.get("source") or {}, new.get("source") or {}
    if sb.get("dir") and sb.get("dir") == sn.get("dir"):
        same.append("built from the same source tree {}".format(sb["dir"]))
    elif sb.get("head") and sb.get("head") == sn.get("head"):
        if sb.get("dirty") is False and sn.get("dirty") is False:
            same.append("built from the same clean commit {}".format(sb["head"][:12]))
        else:
            warnings.append("{}: base and new are the same commit {}, different only by uncommitted changes "
                            "(read now, not at build time)".format(pair, sb["head"][:12]))
    for role, b, s in (("base", base, sb), ("new", new, sn)):
        if not s.get("head"):
            gate.append("{} {}: source unknown (direct_url {}), so the same-source and base checks could not run"
                        .format(pair, role, s.get("url")))
            continue
        if s.get("dirty") is not False:
            gate.append("{} {}: source tree {} {} (provenance not reproducible; build from a clean commit)".format(
                pair, role, s["dir"], "has uncommitted changes" if s.get("dirty") else "dirty state unknown"))
        if is_stale(b):
            gate.append("{} {}: HEAD {} of {} was committed after the build was installed; the recorded HEAD may "
                        "not be what was built (reinstall)".format(pair, role, s["head"][:12], s["dir"]))
    if sb.get("head") and sb.get("on_base_ref") is not True:
        gate.append("{} base: HEAD {} is not {} or an ancestor of it{}".format(
            pair, sb["head"][:12], BASE_REF, "" if sb.get("on_base_ref") is False else " (the check failed)"))
    if same and not allow_same:
        errors.append("{} pair: base and new are {}. Pass --allow-same-build to compare on purpose."
                      .format(pair, "; ".join(same)))
    return errors, warnings, gate, bool(same)


# ------------------------------------------------------------------ runs
def run_pytests_case(case, case_dir, rundir, python, timeout=3600, capture=CAPTURE_SLOTS):
    """Run one pytests case directory with pytests_worker.py in a fresh process. Returns a Record."""
    if not os.path.isfile(os.path.join(case_dir, "input.py")):
        raise HarnessError("pytests case missing: {}".format(case_dir))
    if os.path.exists(rundir):
        raise HarnessError("run directory {} already exists".format(rundir))
    shutil.copytree(case_dir, rundir, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for rel in case.get("add_files", []):
        src = os.path.join(REPO_DIR, rel)
        if not os.path.isfile(src):
            raise HarnessError("file needed by the case is missing: {}".format(src))
        shutil.copy2(src, rundir)
    home = os.path.join(rundir, "home")
    os.makedirs(home)
    # preset/arm/threads/itermx as in a RunSpec, so that compare.check_arm and the spec checks apply
    spec = {"case": case["path"], "deck": "input.py", "rhs_probe": True, "itermx": case.get("itermx"),
            "capture": capture, "preset": "pytests:" + case["path"], "arm": "serial", "threads": 1}
    with open(os.path.join(rundir, "spec.json"), "w") as f:
        json.dump(spec, f, sort_keys=True)
    cmd = [python, "-I", os.path.join(HERE, "pytests_worker.py"), os.path.join(rundir, "spec.json")]
    start = time.time()
    with open(os.path.join(rundir, "run.log"), "wb") as log:
        try:
            proc = subprocess.run(cmd, cwd=rundir, env=clean_env(home), stdout=log, stderr=subprocess.STDOUT,
                                  timeout=timeout)
        except subprocess.TimeoutExpired:
            raise HarnessError("run in {} timed out after {} s".format(rundir, timeout))
    elapsed = time.time() - start
    if not os.path.exists(os.path.join(rundir, "record.json")):
        raise HarnessError("run in {} exited with {} and wrote no record (see run.log)".format(rundir, proc.returncode))
    record = Record(rundir)
    if proc.returncode != 0:
        raise HarnessError("run in {} exited with {}".format(rundir, proc.returncode))
    with open(os.path.join(rundir, "run.log"), "rb") as f:
        text = f.read().replace(b"\x00", b"").decode(errors="replace")
    record.meta["iterations"] = parse_iterations(text)
    record.meta["elapsed_s"] = round(elapsed, 2)
    record.meta["label"] = case["path"]
    with open(os.path.join(rundir, "record.json"), "w") as f:
        json.dump(record.meta, f, indent=1, sort_keys=True)
    return record


def run_case(name, rundir, python, pytests_dir, timeout, capture=CAPTURE_SLOTS, identity=None):
    """Run one case; capture = raw-Jacobian slots (0 when not both builds of the pair have the hook);
    identity = the probed provenance["build"] the record must show (a reinstall mid-check fails)."""
    case = CASES[name]
    if case["kind"] == "repro":
        spec = RunSpec(preset=case["preset"], arm="serial", threads=1, itermx=case.get("itermx"), capture=capture)
        record = run_spec(spec, rundir, python=python, timeout=timeout)
    else:
        record = run_pytests_case(case, os.path.join(pytests_dir, case["path"]), rundir, python, timeout=timeout,
                                  capture=capture)
    if identity is not None:
        got = record.meta.get("provenance", {}).get("build", {}).get("extensions_sha256")
        if got != identity.get("extensions_sha256"):
            raise HarnessError("run in {} used a different build than was probed (extensions {} vs {}): "
                               "reinstalled during the check?".format(rundir, str(got)[:16],
                                                                     str(identity.get("extensions_sha256"))[:16]))
    return record


def compare_pair(name, base, new):
    """compare_records(base, new) with the serial-path checks (compare.check_arm) on both records.
    Returns (report, status) with status AGREE, MISMATCH or ERROR (cli.exit_code 0/1/2)."""
    base.meta["label"], new.meta["label"] = "base:" + name, "new:" + name
    report = compare_records(base, new, rhs_signed_zero_equal=False)
    report["captured_compared"] = int(base.meta.get("capture", {}).get("count", 0)) if not report["errors"] else 0
    return report, {0: "AGREE", 1: "MISMATCH", 2: "ERROR"}[exit_code([report])]


def iteration_problems(name, base, new):
    """For a case with itermx: both records must show >= 2 printed iterations and a post-exmain
    Jacobian from psetnk, i.e. the solver path really ran. Returns the problems (empty = fine)."""
    if not CASES[name].get("itermx"):
        return []
    problems = []
    for role, rec in (("base", base), ("new", new)):
        n = len(rec.meta.get("iterations", []))
        frm = rec.meta.get("post_exmain_from")
        if n < 2 or frm != "psetnk":
            problems.append("{} ({}): an -itN case that did not iterate ({} printed iteration(s), post-exmain "
                            "Jacobian from {}); the solver path was not exercised".format(role, name, n, frm))
    return problems


def first_mismatch(report):
    """One line naming the first mismatching quantity and its first entry."""
    for sec_name, sec in report["sections"].items():
        if "error" in sec:
            return "{}: {}".format(sec_name, sec["error"])
        n = sec.get("mismatches", 0)
        nf = sec.get("nonfinite_a", 0) + sec.get("nonfinite_b", 0)
        if not n and not nf:
            continue
        first = (sec.get("first") or [None])[0]
        if first and "row" in first:
            return "{} ({} entries): first {} at row {} col {} (iv {},{}): base {} new {}".format(
                sec_name, n, first["kind"], first["row"], first["col"], first["iv_row"], first["iv_col"],
                first.get("a", "-"), first.get("b", "-"))
        if first and "at" in first:
            return "{} ({} entries): first at {} (iv {}): base {} new {}".format(
                sec_name, n, first["at"], first["iv"], first["a"], first["b"])
        if "a" in sec:
            return "{}: base {} new {}".format(sec_name, sec["a"], sec["b"])
        return "{}: {} mismatch(es), {} non-finite".format(sec_name, n, nf)
    return None


def error_cause(message, rundir):
    """The informative part of a failed run: the last line of the traceback, and the last
    error line UEDGE printed to run.log (often the only cause given, e.g. '*** Error: ...')."""
    lines = [ln.strip() for ln in message.splitlines() if ln.strip()]
    cause = lines[-1] if lines else message
    log = os.path.join(rundir, "run.log")
    if os.path.exists(log):
        with open(log, "rb") as f:
            text = f.read().replace(b"\x00", b"").decode(errors="replace")
        hits = [ln.strip() for ln in text.splitlines()
                if re.search(r"\*\*\*|error|Error|ERROR", ln) and "Traceback" not in ln]
        if hits and hits[-1] not in cause:
            cause = "{}; log: {}".format(cause, hits[-1])
    return cause


def _prune(record):
    path = os.path.join(record.rundir, "record.npz")
    if os.path.exists(path):
        os.remove(path)


# ------------------------------------------------------------------ main
def serial_check(args):
    out = os.path.abspath(args.out)
    if os.path.exists(out) and os.listdir(out):
        raise HarnessError("output directory {} exists and is not empty".format(out))
    os.makedirs(out, exist_ok=True)
    started = time.time()
    names = resolve_cases(args.cases)
    pairs = [p for p, (b, n, _) in PAIRS.items() if getattr(args, b) or getattr(args, n)]
    for p in pairs:
        b, n, _ = PAIRS[p]
        if not (getattr(args, b) and getattr(args, n)):
            raise HarnessError("pair {} needs both --{} and --{}".format(p, b.replace("_", "-"), n.replace("_", "-")))
    if not pairs:
        raise HarnessError("give --base-python/--new-python and/or --base-omp-python/--new-omp-python")
    pytests_dir = None
    if any(CASES[n]["kind"] == "pytests" for n in names):
        pytests_dir = find_pytests_dir(args.pytests_dir)

    result = {"agree": None, "exit_code": None, "gate_complete": None, "incomplete": [], "cases": names,
              "pairs": pairs, "skipped_pairs": [p for p in PAIRS if p not in pairs],
              "skipped_cases": [n for n in ALL if n not in names], "harness_commit": git_head(HERE),
              "pytests_dir": pytests_dir, "pytests_commit": git_head(pytests_dir) if pytests_dir else None,
              "builds": {}, "results": {}, "errors": [], "warnings": []}

    def save():
        with open(os.path.join(out, "serial_check.json"), "w") as f:
            json.dump(result, f, indent=1, sort_keys=True, default=str)

    # probe the builds and their sources
    same_pairs, source_gate = [], []
    for p in pairs:
        b, n, want_openmp = PAIRS[p]
        probes = {}
        for role, attr in (("base", b), ("new", n)):
            probes[role] = probe_build(os.path.abspath(getattr(args, attr)), os.path.join(out, "probe", p, role))
            probes[role]["source"] = source_info(probes[role])
        result["builds"][p] = probes
        # compare.compare_records needs captures on both sides or neither
        hooks = [bool(probes[r].get("capture_hook")) for r in ("base", "new")]
        result.setdefault("capture_slots", {})[p] = CAPTURE_SLOTS if all(hooks) else 0
        if any(hooks) and not all(hooks):
            result["warnings"].append("{}: the AIUE-47 capture hook is in one build only, so no raw Jacobians are "
                                      "captured; the post-exmain Jacobian is compared".format(p))
        errs, warns, gate, same = check_pair(p, probes["base"], probes["new"], want_openmp, args.allow_same_build)
        result["errors"] += errs
        result["warnings"] += warns
        source_gate += gate
        if same:
            same_pairs.append(p)
    if len(pairs) == 2:
        for role in ("base", "new"):
            hs = [result["builds"][p][role]["source"].get("head") for p in pairs]
            stale = [p for p in pairs if is_stale(result["builds"][p][role])]
            if hs[0] and hs[1] and hs[0] != hs[1] and stale:
                result["warnings"].append("{}: the serial and OpenMP trees are at different commits ({}, {}), but "
                                          "the {} build is older than its HEAD, so the builds may well contain the "
                                          "same code".format(role, hs[0][:12], hs[1][:12], "/".join(stale)))
            elif hs[0] and hs[1] and hs[0] != hs[1]:
                result["warnings"].append("{}: the serial and OpenMP builds come from different commits ({}, {})"
                                          .format(role, hs[0][:12], hs[1][:12]))
    if result["errors"]:
        save()
        raise HarnessError("\n".join(result["errors"]))

    # run every (pair, role, case) in a fresh process
    tasks = [(p, role, name) for name in names for p in pairs for role in ("base", "new")]
    records, failures = {}, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {}
        for p, role, name in tasks:
            python = os.path.abspath(getattr(args, PAIRS[p][0 if role == "base" else 1]))
            rundir = os.path.join(out, p, role, name)
            os.makedirs(os.path.dirname(rundir), exist_ok=True)
            futures[pool.submit(run_case, name, rundir, python, pytests_dir, args.timeout,
                                result["capture_slots"][p], result["builds"][p][role].get("identity"))] = (p, role, name)
        for fut in concurrent.futures.as_completed(futures):
            key = futures[fut]
            try:
                records[key] = fut.result()
            except Exception as err:  # any failure of a run is a harness error, never a verdict
                msg = str(err) if isinstance(err, HarnessError) else "".join(
                    traceback.format_exception(type(err), err, err.__traceback__))
                failures[key] = (msg, error_cause(msg, os.path.join(out, *key)))
            print("  done {}/{}/{}{}".format(*key, " (FAILED)" if key in failures else ""), flush=True)

    # compare
    any_mismatch = False
    for p in pairs:
        result["results"][p] = {}
        for name in names:
            entry = {"base_rundir": os.path.join(out, p, "base", name), "new_rundir": os.path.join(out, p, "new", name)}
            errs = [(r, failures[(p, r, name)]) for r in ("base", "new") if (p, r, name) in failures]
            if errs:
                entry.update({"status": "ERROR", "error": "\n".join(m for _, (m, _) in errs),
                              "cause": "; ".join("{}: {}".format(r, c) for r, (_, c) in errs)})
                result["errors"].append("{}/{}: {}".format(p, name, entry["cause"]))
            else:
                base, new = records[(p, "base", name)], records[(p, "new", name)]
                try:
                    report, status = compare_pair(name, base, new)
                except Exception as err:  # a comparator crash is a harness error, not a verdict
                    entry.update({"status": "ERROR", "error": "compare failed: {!r}".format(err),
                                  "cause": "compare failed: {!r}".format(err)})
                    result["errors"].append("{}/{}: compare failed: {!r}".format(p, name, err))
                    status = None
                if status in ("AGREE", "MISMATCH"):
                    problems = iteration_problems(name, base, new)
                    if problems:  # an -itN case that did not iterate covers less than it claims
                        report["errors"] = report.get("errors", []) + problems
                        status = "ERROR"
                if status == "ERROR":  # compare.check_arm or the record checks found a problem
                    entry.update({"status": "ERROR", "report": report, "error": "\n".join(report["errors"]),
                                  "cause": "; ".join(report["errors"])})
                    result["errors"].append("{}/{}: {}".format(p, name, entry["cause"]))
                elif status:
                    entry.update({"status": status, "report": report,
                                  "first_mismatch": first_mismatch(report), "neq": base.meta["neq"],
                                  "iterations": len(base.meta.get("iterations", [])),
                                  "post_exmain_from": base.meta.get("post_exmain_from"),
                                  "elapsed_s": [base.meta.get("elapsed_s"), new.meta.get("elapsed_s")]})
                    any_mismatch |= status == "MISMATCH"
                    if status == "AGREE" and not args.keep_records:
                        _prune(base)
                        _prune(new)
            result["results"][p][name] = entry

    incomplete = ["pair {} not checked".format(p) for p in result["skipped_pairs"]]
    incomplete += ["{}: base and new are the same build/source (--allow-same-build)".format(p) for p in same_pairs]
    incomplete += source_gate
    if result["skipped_cases"]:
        incomplete.append("{} case(s) of 'all' not run: {}".format(
            len(result["skipped_cases"]), ", ".join(result["skipped_cases"])))
    result["incomplete"] = incomplete
    result["gate_complete"] = not incomplete
    if result["errors"]:
        code = 2
    elif any_mismatch:
        code = 1
    elif incomplete and not args.partial_ok:
        code = 2
    else:
        code = 0
    result["agree"] = not result["errors"] and not any_mismatch
    result["exit_code"] = code
    result["elapsed_s"] = round(time.time() - started, 1)
    save()
    text = summary_text(result)
    with open(os.path.join(out, "summary.txt"), "w") as f:
        f.write(text + "\n")
    print(text)
    return code


def _source_line(s):
    if not s.get("head"):
        return "source unknown ({})".format(s.get("url"))
    return "source {} @ {}{}{}".format(s["dir"], s["head"][:12], " DIRTY" if s.get("dirty") else "",
                                       "" if s.get("on_base_ref") else " (not on {})".format(BASE_REF))


# short names of the reasons a run is not the gate, for the RESULT line (full text in NOT THE GATE lines)
INCOMPLETE_TAGS = [("not checked", "pair skipped"), ("same build/source", "same build"),
                   ("of 'all' not run", "cases skipped"), ("source unknown", "source unknown"),
                   ("uncommitted changes", "dirty tree"), ("dirty state unknown", "dirty tree"),
                   ("committed after the build", "build older than HEAD"),
                   ("is not origin/v9-develop", "base not on origin/v9-develop")]


def result_line(result):
    scope = "pairs {}, cases {} ({})".format("+".join(result["pairs"]),
                                            "all" if not result["skipped_cases"] else "partial", len(result["cases"]))
    code = result["exit_code"]
    if code == 1:
        verdict = "MISMATCH"
    elif result["errors"]:
        verdict = "HARNESS ERROR"
    elif result["incomplete"]:
        tags = sorted({tag for item in result["incomplete"] for key, tag in INCOMPLETE_TAGS if key in item})
        verdict = "{} (what ran agrees bitwise; not the gate: {})".format(
            "INCOMPLETE" if code == 2 else "AGREE, PARTIAL (--partial-ok)", ", ".join(tags) or "see NOT THE GATE")
    else:
        verdict = "AGREE (bitwise identical; complete gate)"
    return "RESULT: {}  [{}]  ({} s)".format(verdict, scope, result.get("elapsed_s"))


def summary_text(result):
    lines = ["SERIAL BITWISE CHECK (AIUE-53)  harness {}  pytests {}".format(
        result["harness_commit"][:12], (result["pytests_commit"] or "-")[:12])]
    for p, probes in result["builds"].items():
        for role in ("base", "new"):
            b = probes[role]
            lines.append("  build {:6s} {:4s} {}  ext-sha256 {}  openmp {}".format(
                p, role, b["python_arg"], b["extensions_sha256"][:16], b["openmp_build"]))
            lines.append("               uedge {}".format(b["uedge_file"]))
            lines.append("               {}".format(_source_line(b.get("source") or {})))
    for w in result.get("warnings", []):
        lines.append("  WARNING: " + w)
    for p, cases in result["results"].items():
        for name, e in cases.items():
            if e["status"] == "ERROR":
                lines.append("[{}] {:30s} ERROR    {}".format(p, name, e["cause"]))
                continue
            el = e["elapsed_s"]
            lines.append("[{}] {:30s} {:8s} neq {:6d}  iters {}  jacobians {}+post({})  {} s / {} s".format(
                p, name, e["status"], e["neq"], e["iterations"], e["report"].get("captured_compared", 0),
                e.get("post_exmain_from"), el[0], el[1]))
            if e["status"] == "MISMATCH":
                lines.append("    first mismatch: " + e["first_mismatch"])
                lines += ["    " + ln for ln in format_report(e["report"]).splitlines()[1:]
                          if not ln.endswith(": equal")]
    for item in result["incomplete"]:
        lines.append("  NOT THE GATE: " + item)
    lines.append(result_line(result))
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-python", help="interpreter of the --serial build of the base (v9-develop)")
    p.add_argument("--new-python", help="interpreter of the --serial build of the change")
    p.add_argument("--base-omp-python", help="interpreter of the default (OpenMP) build of the base")
    p.add_argument("--new-omp-python", help="interpreter of the default (OpenMP) build of the change")
    p.add_argument("--cases", default="all", help="all (the gate), quick, or a comma-separated list (--list)")
    p.add_argument("--out", help="new (or empty) directory for the runs and the report")
    p.add_argument("--jobs", type=int, default=4, help="processes run at the same time (each one serial)")
    p.add_argument("--pytests-dir", default=None, help="upstream pytests checkout (or its pytests/ folder)")
    p.add_argument("--allow-same-build", action="store_true",
                   help="allow base and new to be the same build, source tree or commit (self-test of the tool)")
    p.add_argument("--partial-ok", action="store_true",
                   help="exit 0 when what ran agrees although the gate is incomplete (RESULT says PARTIAL)")
    p.add_argument("--keep-records", action="store_true", help="keep record.npz of agreeing cases")
    p.add_argument("--timeout", type=int, default=3600, help="seconds per run")
    p.add_argument("--list", action="store_true", help="list the cases and exit")
    args = p.parse_args(argv)
    if args.list:
        for name in ALL + sorted(EXCLUDED):
            c = CASES[name]
            where = "preset " + c["preset"] if c["kind"] == "repro" else c["path"]
            group = "quick" if name in QUICK else ("all" if name in ALL else "-")
            print("{:30s} {:6s} {}{}{}{}".format(
                name, group, where, "  itermx={}".format(c["itermx"]) if c.get("itermx") else "",
                "  (+ {})".format(", ".join(c["add_files"])) if c.get("add_files") else "",
                "  EXCLUDED: " + EXCLUDED[name] if name in EXCLUDED else ""))
        return 0
    if not args.out:
        p.error("--out is required")
    try:
        return serial_check(args)
    except HarnessError as err:
        print("HARNESS ERROR: {}".format(err), file=sys.stderr)
        return 2
    except Exception:  # anything unexpected is a harness error too, never "mismatch"
        print("HARNESS ERROR (unexpected):\n{}".format(traceback.format_exc()), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
