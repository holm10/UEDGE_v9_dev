"""Run one yldot family (epic AIUE-9) serially, with an optional settings file, and record it (AIUE-106).

Executed by serial_check.py as   python -I family_worker.py <spec.json>   in an empty run directory
(the working directory when uedge is imported, so no .uedgerc.py of a family is read). Never import
this module in a process that should keep running: it imports uedge, whose state is global.

The sequence:
  import uedge; chdir to the family directory (its input.py reads ../../data by relative paths);
  exec input.py; exec the settings file, if any (tests/deterministic_omp/settings/: the lines an
  upstream regression-suite variant deck added to its default deck, owner 2026-10-24); serial arm;
  allocate; restore spec "state" (reference_state.h5, owner 2026-10-24); restart = 1; issfon = 1;
  ftol = 1e20; exmain(); exmain().
Differences from the upstream-suite worker this replaces (AIUE-53): the state is restored before the
first exmain, from the family's own file, and the equation switches are the deck's (no reset from the
suite's stored switches). com.iprint is left as the deck sets it, so that nksol prints the fnrm
sequence. Nothing under tests/yldot/ is imported: that would pin OMP_NUM_THREADS (uedge-gotchas.md).

With spec "itermx": N (an iterating case), the final exmain instead runs exactly N Newton iterations,
with ftol and stptol forced far below the noise floor (config.force_newton, AIUE-169), so that psetnk,
the preconditioner, the Krylov solve and the line search run too, however converged the state is.

Writes record.npz / record.json in the run directory, in the format of worker.py, so that
compare.compare_records works on them (spec carries preset "yldot:<label>", arm "serial", threads 1).
With the AIUE-47 hook in the build, every raw Jacobian of the final exmain (sfsetnk and psetnk) is
recorded as capjac_k (worker.collect_capture; spec "capture" slots). meta "inputs" holds the SHA-256
of input.py, the settings file and the state file read.
Exit status: 0 on success, 2 on any error (record.json then holds "error").
"""
import hashlib
import json
import os
import platform
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # tests/deterministic_omp, for "harness"

from harness.config import ARMS, DIAGNOSTIC_SWITCHES, force_newton  # noqa: E402
from harness.worker import (build_identity, collect_capture, equation_map, git_state, has_capture_hook,  # noqa: E402
                            start_capture)


def _sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _exec(path, name):
    """Run a deck file in its own namespace, as tests/yldot/harness/state.py runs input.py."""
    with open(path) as f:
        source = f.read()
    exec(compile(source, path, "exec"), {"__name__": name})


def run(spec, rundir):
    import numpy as np
    import uedge  # noqa: F401  cwd is the empty run directory here
    from uedge import bbb, com, ppp
    from uedge.hdf5 import hdf5_restore

    family = spec["family"]
    if os.path.exists(os.path.join(family, ".uedgerc.py")):
        raise RuntimeError("{} holds .uedgerc.py, which import uedge would execute".format(family))
    os.chdir(family)
    deck = os.path.join(family, "input.py")
    _exec(deck, "__family_input__")
    inputs = {"input.py": _sha256(deck)}
    if spec.get("settings"):
        _exec(spec["settings"], "__family_settings__")
        inputs["settings"] = _sha256(spec["settings"])

    for name in DIAGNOSTIC_SWITCHES:  # never on in a measured run
        setattr(ppp, name, 0)
    for name, value in ARMS["serial"].items():
        setattr(ppp, name, value)
    ppp.Nthreads = 1
    state = os.path.realpath(os.path.join(family, spec["state"]))
    inputs["state"] = _sha256(state)
    bbb.allocate()
    hdf5_restore(state)
    bbb.restart = 1
    bbb.issfon = 1
    bbb.ftol = 1e20
    bbb.exmain()

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
        "inputs": inputs,
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
    np.savez(os.path.join(rundir, "record.npz"), **arrays)
    return meta


def main():
    rundir = os.getcwd()
    with open(sys.argv[1]) as f:
        spec = json.load(f)
    try:
        meta, status = run(spec, rundir), 0
    except BaseException:  # noqa: B902  (SystemExit from the deck counts as a harness error too)
        meta, status = {"error": traceback.format_exc()}, 2
    with open(os.path.join(rundir, "record.json"), "w") as f:
        json.dump(meta, f, indent=1, sort_keys=True)
    sys.exit(status)


if __name__ == "__main__":
    main()
