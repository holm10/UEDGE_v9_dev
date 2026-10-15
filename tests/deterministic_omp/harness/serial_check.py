"""Serial old-vs-new bitwise check (AIUE-53): does a change leave serial results bit for bit as they were?

  python tests/deterministic_omp/harness/serial_check.py \\
      --base-python BASE_SERIAL/bin/python --new-python NEW_SERIAL/bin/python \\
      --base-omp-python BASE_OMP/bin/python --new-omp-python NEW_OMP/bin/python \\
      [--cases quick|all|NAME,NAME,...] [--jobs N] --out DIR

Runs every case once per build, each in a fresh `python -I` process with an empty HOME, on the
serial path (ppp.OMPParallelJac = ppp.OMPParallelPandf1 = 0, Nthreads = 1, OMP_NUM_THREADS = 1),
and compares new against base with the AIUE-49 comparator (compare.compare_records): the
Jacobians the records hold (post-exmain sfsetnk Jacobian; raw captures when both builds have the
AIUE-47 hook), sfscal, suscal, yldot, one more RHS through ffun, the final fnrm (float.hex) and the
printed fnrm sequence. Bitwise: +0.0 and -0.0 differ, any NaN/Inf fails.

Pairs: "serial" (--base-python vs --new-python, the --serial builds) and "omp0" (--base-omp-python
vs --new-omp-python, the default OpenMP builds with both switches 0). The PR gate needs both.
Before running, every interpreter is probed (build_probe.py): its path, uedge.__file__, version,
SHA-256 of the compiled extensions, and whether bbbpy is an OpenMP build. It is a harness error if
base and new are the same build (same extension hashes; --allow-same-build to compare a build with
itself on purpose), or if a build is of the wrong kind for its pair.

Cases (--list): reproducer presets (repro-*, config.PRESETS, serial arm) and upstream pytests
cases (pytests-*), run as their test_reference does (pytests_worker.py). The pytests checkout is
--pytests-dir, else $UEDGE_PYTESTS_DIR, else ../uedge-pytests or ../../uedge-pytests next to the
repository (git worktree add ../uedge-pytests upstream/pytests).

Writes DIR/serial_check.json (builds, cases, every report), DIR/summary.txt, and the runs under
DIR/<pair>/<base|new>/<case>/. record.npz of agreeing cases is deleted unless --keep-records.
Exit codes: 0 every case agrees, 1 at least one mismatch, 2 harness error (wins over 1).
"""
import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from harness.compare import compare_records, format_report  # noqa: E402
from harness.config import PRESETS, RunSpec  # noqa: E402
from harness.runner import REPO_DIR, HarnessError, Record, parse_iterations, run_spec  # noqa: E402

CRUMPET = ["rates/aph/crumpet_nrates.dat", "rates/aph/crumpet_Erates.dat"]  # D_mols decks read them from cwd

# name -> case. kind "repro": a reproducer preset on the serial arm. kind "pytests": a case directory
# of the upstream pytests checkout; add_files are repository files copied next to it.
CASES = {}
for _p in PRESETS:
    CASES["repro-" + _p] = {"kind": "repro", "preset": _p}
CASES.update({
    "pytests-D_only": {"kind": "pytests", "path": "unittests/D_only/nonog/default"},
    "pytests-D+C": {"kind": "pytests", "path": "unittests/D+C/nonog_carbon/default"},
    "pytests-D_mols": {"kind": "pytests", "path": "unittests/D_mols/nonog_mols/default", "add_files": CRUMPET},
    "pytests-full-d_c-16x8": {"kind": "pytests", "path": "fulltests/nonog_d_c-fb_16x8"},
    "pytests-D_mols-drift": {"kind": "pytests", "path": "unittests/D_mols/nonog_mols/tg_mol_atoms_drift",
                             "add_files": CRUMPET},
    "pytests-orthogonal": {"kind": "pytests", "path": "fulltests/orthogonal_unittest"},
    "pytests-slab": {"kind": "pytests", "path": "unittests/slab_D_only/slab/default"},
})
QUICK = ["repro-tebox", "pytests-D_only", "pytests-D+C", "pytests-D_mols", "pytests-full-d_c-16x8"]
# slowest first, so that parallel jobs finish together
ALL = ["repro-full", "repro-ni", "repro-up", "repro-ti", "repro-te", "repro-ng", "repro-tebox",
       "pytests-full-d_c-16x8", "pytests-D+C", "pytests-D_only", "pytests-D_mols", "pytests-D_mols-drift",
       "pytests-slab"]
# Cases that fail on v9-develop itself (0fac655), in both builds: left out of "all", still runnable by name.
EXCLUDED = {
    "repro-full_note": "serial exmain stops with 'Jacobian row = 0 for eqn iv = 1092' (RuntimeError)",
    "pytests-orthogonal": "input.py stops with 'ueinit -- error in sign sx, sy'; the upstream test fails the same way",
}
assert sorted(ALL + list(EXCLUDED)) == sorted(CASES) and not set(ALL) & set(EXCLUDED)

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
                       "'git worktree add ../uedge-pytests upstream/pytests' or pass --pytests-dir"
                       .format(candidates))


def git_head(path):
    try:
        return subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=10).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def resolve_cases(text):
    if text == "quick":
        return list(QUICK)
    if text == "all":
        return list(ALL)
    names = [n.strip() for n in text.split(",") if n.strip()]
    unknown = [n for n in names if n not in CASES]
    if unknown or not names:
        raise HarnessError("unknown case(s) {}; known: quick, all, {}".format(unknown, ", ".join(sorted(CASES))))
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


def check_pair(pair, base, new, want_openmp, allow_same):
    """Errors (list of str) for a base/new build pair: wrong build kind, or the same build twice."""
    errors = []
    for role, b in (("base", base), ("new", new)):
        if b["openmp_build"] != want_openmp:
            errors.append("{} {} build {} is {}an OpenMP build; the {} pair needs {}".format(
                pair, role, b["python_arg"], "" if b["openmp_build"] else "not ", pair,
                "the default OpenMP build" if want_openmp else "the --serial build"))
    if base["extensions_sha256"] == new["extensions_sha256"] and not allow_same:
        errors.append("{} pair: base and new are the same build (extension SHA-256 {}; base {}, new {}). "
                      "Pass --allow-same-build to compare a build with itself on purpose."
                      .format(pair, base["extensions_sha256"][:16], base["uedge_file"], new["uedge_file"]))
    return errors


# ------------------------------------------------------------------ runs
def run_pytests_case(case, case_dir, rundir, python, timeout=3600):
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
    spec = {"case": case["path"], "deck": "input.py", "rhs_probe": True}
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


def run_case(name, rundir, python, pytests_dir, timeout):
    case = CASES[name]
    if case["kind"] == "repro":
        spec = RunSpec(preset=case["preset"], arm="serial", threads=1)
        return run_spec(spec, rundir, python=python, timeout=timeout)
    return run_pytests_case(case, os.path.join(pytests_dir, case["path"]), rundir, python, timeout=timeout)


class _View:
    """A record whose capture count is lowered, so that compare_records skips the extra captures."""

    def __init__(self, record, count, label):
        self.meta = dict(record.meta)
        self.meta["capture"] = dict(record.meta.get("capture", {}), count=count)
        self.arrays = record.arrays
        self.label = label


def compare_pair(name, base, new):
    """compare_records(base, new), comparing captured Jacobians only as far as both builds have them."""
    cb = int(base.meta.get("capture", {}).get("count", 0))
    cn = int(new.meta.get("capture", {}).get("count", 0))
    notes = []
    n = min(cb, cn)
    if cb != cn:
        notes.append("captured Jacobians: base {}, new {}; compared the first {} (AIUE-47 hook not in both "
                     "builds); the post-exmain Jacobian is always compared".format(cb, cn, n))
    report = compare_records(_View(base, n, "base:" + name), _View(new, n, "new:" + name),
                             rhs_signed_zero_equal=False)
    report["notes"] = notes
    return report


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

    result = {"agree": None, "exit_code": None, "cases": names, "pairs": pairs, "skipped_pairs":
              [p for p in PAIRS if p not in pairs], "harness_commit": git_head(HERE), "pytests_dir": pytests_dir,
              "pytests_commit": git_head(pytests_dir) if pytests_dir else None, "builds": {}, "results": {},
              "errors": []}

    def save():
        with open(os.path.join(out, "serial_check.json"), "w") as f:
            json.dump(result, f, indent=1, sort_keys=True, default=str)

    # probe the builds
    for p in pairs:
        b, n, want_openmp = PAIRS[p]
        probes = {}
        for role, attr in (("base", b), ("new", n)):
            probes[role] = probe_build(os.path.abspath(getattr(args, attr)), os.path.join(out, "probe", p, role))
        result["builds"][p] = probes
        result["errors"] += check_pair(p, probes["base"], probes["new"], want_openmp, args.allow_same_build)
        if probes["base"]["extensions_sha256"] == probes["new"]["extensions_sha256"]:
            result.setdefault("warnings", []).append("{}: base and new are the same build (--allow-same-build)"
                                                     .format(p))
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
            futures[pool.submit(run_case, name, rundir, python, pytests_dir, args.timeout)] = (p, role, name)
        for fut in concurrent.futures.as_completed(futures):
            key = futures[fut]
            try:
                records[key] = fut.result()
            except (HarnessError, OSError, ValueError, KeyError) as err:
                failures[key] = str(err)
            print("  done {}/{}/{}{}".format(*key, " (FAILED)" if key in failures else ""), flush=True)

    # compare
    any_mismatch = False
    for p in pairs:
        result["results"][p] = {}
        for name in names:
            entry = {"base_rundir": os.path.join(out, p, "base", name), "new_rundir": os.path.join(out, p, "new", name)}
            errs = [failures[(p, r, name)] for r in ("base", "new") if (p, r, name) in failures]
            if errs:
                entry.update({"status": "ERROR", "error": "\n".join(errs)})
                result["errors"].append("{}/{}: {}".format(p, name, errs[0].splitlines()[0]))
            else:
                base, new = records[(p, "base", name)], records[(p, "new", name)]
                try:
                    report = compare_pair(name, base, new)
                except Exception as err:  # a comparator crash is a harness error, not a verdict
                    entry.update({"status": "ERROR", "error": "compare failed: {!r}".format(err)})
                    result["errors"].append("{}/{}: compare failed: {!r}".format(p, name, err))
                else:
                    entry.update({"status": "AGREE" if report["agree"] else "MISMATCH", "report": report,
                                  "first_mismatch": first_mismatch(report), "neq": base.meta["neq"],
                                  "elapsed_s": [base.meta.get("elapsed_s"), new.meta.get("elapsed_s")]})
                    any_mismatch |= not report["agree"]
                    if report["agree"] and not args.keep_records:
                        _prune(base)
                        _prune(new)
            result["results"][p][name] = entry

    code = 2 if result["errors"] else (1 if any_mismatch else 0)
    result["agree"] = code == 0
    result["exit_code"] = code
    result["elapsed_s"] = round(time.time() - started, 1)
    save()
    text = summary_text(result)
    with open(os.path.join(out, "summary.txt"), "w") as f:
        f.write(text + "\n")
    print(text)
    return code


def summary_text(result):
    lines = ["SERIAL BITWISE CHECK (AIUE-53)  harness {}  pytests {}".format(
        result["harness_commit"][:12], (result["pytests_commit"] or "-")[:12])]
    for p, probes in result["builds"].items():
        for role in ("base", "new"):
            b = probes[role]
            lines.append("  build {:6s} {:4s} {}  uedge {}  ext-sha256 {}  openmp {}".format(
                p, role, b["python_arg"], b["uedge_file"], b["extensions_sha256"][:16], b["openmp_build"]))
    for w in result.get("warnings", []):
        lines.append("  WARNING: " + w)
    for p in result["skipped_pairs"]:
        lines.append("  WARNING: pair {} not checked; the PR gate needs both pairs".format(p))
    for p, cases in result["results"].items():
        for name, e in cases.items():
            if e["status"] == "ERROR":
                lines.append("[{}] {:24s} ERROR    {}".format(p, name, e["error"].splitlines()[0]))
                continue
            el = e["elapsed_s"]
            lines.append("[{}] {:24s} {:8s} neq {:6d}  {} s / {} s".format(p, name, e["status"], e["neq"], el[0], el[1]))
            if e["status"] == "MISMATCH":
                lines.append("    first mismatch: " + e["first_mismatch"])
                lines += ["    " + ln for ln in format_report(e["report"]).splitlines()[1:]
                          if not ln.endswith(": equal")]
            for note in e["report"].get("notes", []):
                lines.append("    note: " + note)
    verdict = {0: "AGREE (bitwise identical)", 1: "MISMATCH", 2: "HARNESS ERROR"}[result["exit_code"]]
    lines.append("RESULT: {}  ({} s)".format(verdict, result.get("elapsed_s")))
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-python", help="interpreter of the --serial build of the base (v9-develop)")
    p.add_argument("--new-python", help="interpreter of the --serial build of the change")
    p.add_argument("--base-omp-python", help="interpreter of the default (OpenMP) build of the base")
    p.add_argument("--new-omp-python", help="interpreter of the default (OpenMP) build of the change")
    p.add_argument("--cases", default="quick", help="quick, all, or a comma-separated list (--list)")
    p.add_argument("--out", help="new (or empty) directory for the runs and the report")
    p.add_argument("--jobs", type=int, default=4, help="processes run at the same time (each one serial)")
    p.add_argument("--pytests-dir", default=None, help="upstream pytests checkout (or its pytests/ folder)")
    p.add_argument("--allow-same-build", action="store_true",
                   help="allow base and new to be the same build (self-test of the tool)")
    p.add_argument("--keep-records", action="store_true", help="keep record.npz of agreeing cases")
    p.add_argument("--timeout", type=int, default=3600, help="seconds per run")
    p.add_argument("--list", action="store_true", help="list the cases and exit")
    args = p.parse_args(argv)
    if args.list:
        for name in ALL + sorted(EXCLUDED):
            c = CASES[name]
            where = "preset " + c["preset"] if c["kind"] == "repro" else c["path"]
            group = "quick" if name in QUICK else ("all" if name in ALL else "-")
            print("{:24s} {:6s} {}{}{}".format(name, group, where,
                                              "  (+ {})".format(", ".join(c["add_files"])) if c.get("add_files") else "",
                                              "  EXCLUDED: " + EXCLUDED[name] if name in EXCLUDED else ""))
        return 0
    if not args.out:
        p.error("--out is required")
    try:
        return serial_check(args)
    except (HarnessError, OSError, ValueError, KeyError, subprocess.SubprocessError) as err:
        print("HARNESS ERROR: {}".format(err), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
