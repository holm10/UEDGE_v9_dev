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

Writes record.npz / record.json in the format of worker.py, so that compare.compare_records
works on them. Raw captured Jacobians (AIUE-47) are not recorded here: with ftol=1e20 the
post-exmain bbb.jac is the sfsetnk Jacobian (the capture point) scaled by 1/suscal.
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

from harness.config import ARMS  # noqa: E402
from harness.worker import equation_map, git_commit  # noqa: E402

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
    meta = {
        "spec": spec,
        "neq": neq,
        "nnz_post": nnz,
        "numvar": int(bbb.numvar),
        "fnrm_final_hex": float(bbb.get_fnrm(bbb.dtreal)).hex(),
        "ijactot": int(bbb.ijactot),
        "capture": {"hook": False, "count": 0, "note": "pytests worker: post-exmain Jacobian only"},
        "post_exmain_jacobian": "sfsetnk Jacobian scaled by 1/suscal (ftol=1e20)",
    }
    if spec.get("rhs_probe", True):
        yl = np.array(bbb.yl[:neq])
        out = np.zeros(neq)
        bbb.ffun(neq, 0.0, yl, out)
        arrays["yldot_probe"] = out
        meta["rhs_probe_parallel"] = bool(int(bbb.ParallelPandf1) > 0 and int(bbb.ijactot) > 0)
    meta["provenance"] = {
        "commit": git_commit(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS"),
        "Nthreads": int(ppp.Nthreads),
        "OMPParallelJac": int(ppp.OMPParallelJac),
        "OMPParallelPandf1": int(ppp.OMPParallelPandf1),
        "ParallelJac": int(bbb.ParallelJac),
        "ParallelPandf1": int(bbb.ParallelPandf1),
    }
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
