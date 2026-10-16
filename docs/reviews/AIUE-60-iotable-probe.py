"""AIUE-60 G-iotable: does an OpenMP Jacobian change com's Fortran unit table /iotable/ differently from the base?

  python3 -I AIUE-60-iotable-probe.py check --base-python BASE --new-python NEW [--neg-python PRE] --out DIR [--repeats 2]

Each probe (a fresh process, `run`): the AIUE-46 deck in a prepared run directory, Te box preset, jac arm, 4 threads,
itermx=1 (>= 2 OpenMP Jacobians); reads compy's iotable_ (128 int64 words) through ctypes before and after exmain.
The reviewer's probe of implementation review round 1 (I1-B1), made robust to a missing com block.
A correct build legitimately changes some words (exmain opens files: AIUE-56 shows {11: 0->1, 12: 0->1}).
PASS: for every repeat, the new build's before- and after-states of all 128 words equal the base build's (the base
being repeatable across its own repeats). The optional negative-control build (pre-amendment) is reported; it is
expected to differ. Exit 0 PASS, 1 FAIL, 2 ERROR. Writes DIR/iotable.json.
"""
import argparse
import ctypes
import glob
import json
import os
import subprocess
import sys

HARNESS = "/Users/holma/Documents/uedge/src/uedge-wt/AIUE-57/tests/deterministic_omp"


def probe(a):
    sys.path.insert(0, a.harness)
    os.chdir(a.rundir)
    sys.path.insert(0, a.rundir)
    from harness.config import ARMS, DIAGNOSTIC_SWITCHES, apply_preset
    from input_mod4 import bbb, ppp  # runs the deck
    import uedge
    compy = glob.glob(os.path.join(os.path.dirname(uedge.__file__), "compy*.so"))[0]
    lib = ctypes.CDLL(compy, mode=ctypes.RTLD_GLOBAL)
    io = (ctypes.c_int64 * 128).in_dll(lib, "iotable_")
    try:
        ctypes.c_char.in_dll(lib, "ompcommonscalarcopy_")
        com_block = True
    except ValueError:
        com_block = False
    before = list(io)
    apply_preset(bbb, "tebox")
    for n in DIAGNOSTIC_SWITCHES:
        setattr(ppp, n, 0)
    for k, v in ARMS["jac"].items():
        setattr(ppp, k, v)
    ppp.Nthreads = a.threads
    bbb.itermx = 1
    bbb.exmain()
    after = list(io)
    rec = {"before": before, "after": after, "com_defines_block": com_block, "ijactot": int(bbb.ijactot),
           "OMPParallelJac": int(ppp.OMPParallelJac), "Nthreads": int(ppp.Nthreads)}
    with open(os.path.join(a.rundir, "iotable.json"), "w") as f:
        json.dump(rec, f)


def launch(python, rundir, threads, harness):
    sys.path.insert(0, harness)
    from harness.runner import DEFAULT_RATES, prepare_rundir
    prepare_rundir(rundir)
    home = os.path.join(rundir, "home")
    os.makedirs(home)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("OMP_", "GOMP_", "KMP_", "PYTHON"))}
    env.update({"HOME": home, "UEDGE_OMP_RATES_DIR": DEFAULT_RATES, "OMP_NUM_THREADS": str(threads),
                "OMP_STACKSIZE": "512M"})
    cmd = [python, "-I", os.path.abspath(__file__), "run", "--rundir", rundir, "--threads", str(threads),
           "--harness", harness]
    with open(os.path.join(rundir, "run.log"), "wb") as log:
        rc = subprocess.run(cmd, cwd=rundir, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
    path = os.path.join(rundir, "iotable.json")
    if rc != 0 or not os.path.exists(path):
        raise RuntimeError("probe failed (exit {}) in {}".format(rc, rundir))
    rec = json.load(open(path))
    if rec["OMPParallelJac"] != 1 or rec["Nthreads"] != threads or rec["ijactot"] < 2:
        raise RuntimeError("arm did not take effect in {}: {}".format(rundir, {k: rec[k] for k in ("OMPParallelJac", "Nthreads", "ijactot")}))
    rec["changed"] = [(i, b, c) for i, (b, c) in enumerate(zip(rec["before"], rec["after"])) if b != c]
    return rec


def check(a):
    os.makedirs(a.out)
    builds = [("base", a.base_python), ("new", a.new_python)] + ([("neg", a.neg_python)] if a.neg_python else [])
    res = {}
    try:
        for label, py in builds:
            res[label] = [launch(py, os.path.join(a.out, "{}_{}".format(label, k)), a.threads, a.harness)
                          for k in range(a.repeats)]
            for k, r in enumerate(res[label]):
                print("{} run{}: com block {}; {} words changed: {}".format(
                    label, k, "present" if r["com_defines_block"] else "absent", len(r["changed"]), r["changed"][:12]))
    except RuntimeError as err:
        print("ERROR:", err)
        return 2
    base0 = res["base"][0]
    base_repeatable = all(r["before"] == base0["before"] and r["after"] == base0["after"] for r in res["base"])
    new_ok = all(r["before"] == base0["before"] and r["after"] == base0["after"] for r in res["new"])
    out = {"base_repeatable": base_repeatable, "new_equals_base": new_ok,
           "neg_equals_base": (all(r["before"] == base0["before"] and r["after"] == base0["after"] for r in res["neg"])
                               if "neg" in res else None),
           "runs": {k: [{"changed": r["changed"], "com_defines_block": r["com_defines_block"]} for r in v]
                    for k, v in res.items()}}
    json.dump(out, open(os.path.join(a.out, "iotable.json"), "w"), indent=1)
    print("base repeatable:", base_repeatable, "| new equals base:", new_ok,
          "| negative control equals base:", out["neg_equals_base"])
    if not base_repeatable:
        print("RESULT: ERROR (base not repeatable)")
        return 2
    print("RESULT:", "PASS" if new_ok else "FAIL")
    return 0 if new_ok else 1


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--rundir", required=True)
    r.add_argument("--threads", type=int, default=4)
    r.add_argument("--harness", default=HARNESS)
    c = sub.add_parser("check")
    c.add_argument("--base-python", required=True)
    c.add_argument("--new-python", required=True)
    c.add_argument("--neg-python", default=None)
    c.add_argument("--out", required=True)
    c.add_argument("--threads", type=int, default=4)
    c.add_argument("--repeats", type=int, default=2)
    c.add_argument("--harness", default=HARNESS)
    a = p.parse_args()
    if a.cmd == "run":
        probe(a)
        return 0
    return check(a)


if __name__ == "__main__":
    sys.exit(main())
