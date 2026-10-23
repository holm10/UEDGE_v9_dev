"""Run one upstream pytests case the way its test_reference does, serially, and record it.

Executed by serial_check.py as   python -I pytests_worker.py <spec.json>   in a run directory
that holds a copy of the case directory (input.py, gridue, solution.h5, ...). Never import this
module in a process that should keep running: it imports uedge, whose state is global.

The sequence is the one of pytests/*/test_*.py (TestClass.test_reference and matches()):
  exec input.py; issfon=1; ftol=1e20; exmain();
  equation switches from solution.h5:pytests/default; nis..phis from solution.h5:bbb; exmain().
Differences from the test, none of which changes a number:
  - com.iprint is left at 1 (the test sets 0) so that nksol prints the fnrm sequence;
  - the serial arm (ppp.OMPParallelJac = ppp.OMPParallelPandf1 = 0, Nthreads = 1) is set
    explicitly after input.py, before the first exmain (these are the defaults);
  - perturb_solution is never called. The test does not call it either: it is used only by
    write_data, when the reference solution.h5 is made, so the stored solution is used as it is.

With spec "itermx": N (an iterating case, not part of the test), the final exmain instead runs
exactly N Newton iterations, with ftol and stptol forced far below the noise floor
(config.force_newton, AIUE-169), so that psetnk, the preconditioner, the Krylov solve and the line
search run too, however converged the stored solution is.

Writes record.npz / record.json in the format of worker.py, so that compare.compare_records
works on them (spec carries preset "pytests:<case>", arm "serial", threads 1). With the AIUE-47 hook in the build, every raw Jacobian of the final exmain
(sfsetnk and psetnk) is recorded as capjac_k (worker.collect_capture; spec "capture" slots).
Exit status: 0 on success, 2 on any error (record.json then holds "error").
"""
import importlib.util
import json
import os
import platform
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # tests/deterministic_omp, for "harness"
sys.path.insert(0, os.getcwd())  # the run directory, as conftest.py's chdir gives the test

from harness.config import ARMS, DIAGNOSTIC_SWITCHES, force_newton  # noqa: E402
from harness.worker import (build_identity, collect_capture, equation_map, git_state, has_capture_hook,  # noqa: E402
                            start_capture)

EQUATION_SWITCHES = ["isnion", "isupon", "isteon", "istion", "isngon", "istgon", "isphion"]
STATE = ["nis", "ups", "tes", "tis", "ngs", "tgs", "phis"]


def _setdata(var, value):
    """Set var in every Forthon package that holds it, as test_reference's setdata does."""
    from Forthon import package, packageobject

    found = False
    for pkg in package():
        obj = packageobject(pkg)
        if var in obj.varlist():
            obj.__setattr__(var, value)
            found = True
    if not found:
        raise KeyError("no package holds {}".format(var))


def run(spec):
    import numpy as np
    from h5py import File
    from uedge import bbb, com, ppp

    deck = spec.get("deck", "input.py")
    inputspec = importlib.util.spec_from_file_location("input", deck)
    inputspec.loader.exec_module(importlib.util.module_from_spec(inputspec))

    for name in DIAGNOSTIC_SWITCHES:  # never on in a measured run
        setattr(ppp, name, 0)
    for name, value in ARMS["serial"].items():
        setattr(ppp, name, value)
    ppp.Nthreads = 1
    bbb.issfon = 1
    bbb.ftol = 1e20
    bbb.exmain()  # the test's first exmain ("fnrm still changes after 1 exmain, but not after 2")

    with File("solution.h5", "r") as f:
        defref = f["pytests"]["default"]
        for eq in EQUATION_SWITCHES:
            _setdata(eq, defref[eq][()])
        group = f["bbb"] if "bbb" in f else f["restore/bbb"]
        for var in STATE:
            _setdata(var, group[var][()])
    itermx = spec.get("itermx")
    if itermx:
        force_newton(bbb, int(itermx))
    slots = int(spec.get("capture", 16))
    hook = has_capture_hook(bbb) and slots > 0
    if hook:
        start_capture(bbb, slots)  # only the final exmain is captured
    bbb.exmain()

    neq = int(bbb.neq)
    nnz = int(bbb.jaci[neq]) - 1
    arrays = {
        "yldot": np.array(bbb.yldot[:neq]),
        "sfscal": np.array(bbb.sfscal[:neq]),
        "suscal": np.array(bbb.suscal[:neq]),
        "jac_post": np.array(bbb.jac[:nnz]),
        "jacj_post": np.array(bbb.jacj[:nnz]),
        "jaci_post": np.array(bbb.jaci[: neq + 1]),
        "igyl": np.array(bbb.igyl[:neq, :]),
    }
    arrays["eq"], arrays["species"] = equation_map(bbb, com, neq)
    capture = collect_capture(bbb, arrays) if hook else {"hook": False, "count": 0}
    # as worker.run: which Jacobian bbb.jac holds after exmain, and whether jac_reorder permuted it
    if capture["count"]:
        last = capture["caller"][-1]
    else:
        last = "psetnk" if int(bbb.ijactot) > 1 else "sfsetnk"
    meta = {
        "spec": spec,
        "neq": neq,
        "nnz_post": nnz,
        "numvar": int(bbb.numvar),
        "ijactot": int(bbb.ijactot),
        "capture": capture,
        "ftol": float(bbb.ftol),
        "stptol": float(bbb.stptol),
        "iterm": int(bbb.iterm),  # as worker.run: why nksol stopped; informational
        "post_exmain_from": last,
        "post_exmain_permuted": last == "psetnk" and int(bbb.ireorder) == 1,
    }
    if spec.get("rhs_probe", True):
        # as worker.run: before get_fnrm, with the whole neq+2 yl (pandf reads yl(neq+1))
        yl = np.array(bbb.yl[: neq + 2])
        out = np.zeros(neq + 2)
        bbb.ffun(neq, 0.0, yl, out)
        arrays["yldot_probe"] = out[:neq].copy()
        meta["rhs_probe_parallel"] = bool(int(bbb.ParallelPandf1) > 0 and int(bbb.ijactot) > 0)
    meta["fnrm_final_hex"] = float(bbb.get_fnrm(bbb.dtreal)).hex()
    harness_head, harness_dirty = git_state(HERE)
    meta["provenance"] = {
        "harness_commit": harness_head,
        "harness_dirty": harness_dirty,
        "build": build_identity(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS"),
        "OMP_STACKSIZE": os.environ.get("OMP_STACKSIZE"),
        "Nthreads": int(ppp.Nthreads),
        "OMPParallelJac": int(ppp.OMPParallelJac),
        "OMPParallelPandf1": int(ppp.OMPParallelPandf1),
        "ParallelJac": int(bbb.ParallelJac),
        "ParallelPandf1": int(bbb.ParallelPandf1),
        "ireorder": int(bbb.ireorder),
    }
    for name in DIAGNOSTIC_SWITCHES:
        meta["provenance"][name] = int(getattr(ppp, name))
    meta["provenance"]["openmp_build"] = meta["provenance"]["build"]["openmp_build"]
    np.savez("record.npz", **arrays)
    return meta


def main():
    with open(sys.argv[1]) as f:
        spec = json.load(f)
    try:
        meta, status = run(spec), 0
    except BaseException:  # noqa: B902  (SystemExit from the deck counts as a harness error too)
        meta, status = {"error": traceback.format_exc()}, 2
    with open("record.json", "w") as f:
        json.dump(meta, f, indent=1, sort_keys=True)
    sys.exit(status)


if __name__ == "__main__":
    main()
