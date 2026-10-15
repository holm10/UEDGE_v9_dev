"""Run one configuration of the reproducer and save everything the comparison needs.

Executed by runner.py as   python -I worker.py <spec.json>   in a prepared run directory
(a copy of tests/deterministic_omp/case). Never import this module in a process that
should keep running: it imports uedge, whose state is global.

Writes, in the run directory:
  record.npz   arrays (Jacobians, yldot, sfscal, suscal, index maps)
  record.json  scalars, provenance and the capture description
Exit status: 0 on success, 2 on any error (record.json then holds "error").
"""
import json
import os
import platform
import subprocess
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # tests/deterministic_omp, for "harness"
sys.path.insert(0, os.getcwd())  # the run directory, for input_mod4

from harness.config import ARMS, RunSpec, apply_preset  # noqa: E402

EQ_CODES = ["ni", "up", "te", "ti", "ng", "tg", "phi"]


def git_commit():
    try:
        return subprocess.run(["git", "-C", HERE, "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=10).stdout.strip()
    except Exception:
        return "unknown"


def equation_map(bbb, com, neq):
    """For every equation index iv (0-based), its equation code (index into EQ_CODES; -1 not found,
    -2 claimed by two tables) and species (-1 if none), from the idx* tables (bbb/bbb.v Indexes)."""
    import numpy as np

    eq = np.full(neq, -1, dtype=np.int64)
    species = np.full(neq, -1, dtype=np.int64)
    tables = [("ni", bbb.idxn, True), ("up", bbb.idxu, True), ("te", bbb.idxte, False),
              ("ti", bbb.idxti, False), ("ng", bbb.idxg, True), ("tg", bbb.idxtg, True),
              ("phi", bbb.idxphi, False)]
    switches = {"ni": bbb.isnion, "up": bbb.isupon, "te": [bbb.isteon], "ti": [bbb.istion],
                "ng": bbb.isngon, "tg": bbb.istgon, "phi": [bbb.isphion]}
    for name, idx, per_species in tables:
        arr = np.asarray(idx)
        if arr.size == 0:
            continue
        if not per_species:
            arr = arr[..., None]
        for isp in range(arr.shape[2]):
            on = np.atleast_1d(switches[name])
            if isp >= on.size or on[isp] == 0:
                continue
            ivs = arr[:, :, isp].ravel()
            ivs = ivs[(ivs >= 1) & (ivs <= neq)] - 1
            clash = eq[ivs] != -1
            eq[ivs] = np.where(clash, -2, EQ_CODES.index(name))  # -2: assigned twice, unreliable
            species[ivs] = isp if per_species else -1
    return eq, species


def capture_description(bbb):
    """Which Jacobians this build can give us (AIUE-47 capture hook, or post-exmain arrays)."""
    return {"hook": False}


def run(spec):
    import numpy as np
    from input_mod4 import bbb, com, ppp  # runs the deck in the current directory

    apply_preset(bbb, spec.preset)
    for name, value in ARMS[spec.arm].items():
        setattr(ppp, name, value)
    ppp.Nthreads = spec.threads
    for name, value in spec.ppp.items():
        setattr(ppp, name, value)
    if spec.itermx is None:
        bbb.ftol = 1e20
    else:
        bbb.itermx = spec.itermx

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
        "spec": json.loads(spec.to_json()),
        "neq": neq,
        "nnz_post": nnz,
        "numvar": int(bbb.numvar),
        "fnrm_final_hex": float(bbb.get_fnrm(bbb.dtreal)).hex(),
        "ijactot": int(bbb.ijactot),
        "capture": capture_description(bbb),
        "post_exmain_jacobian": ("sfsetnk Jacobian scaled by 1/suscal (ftol=1e20: no psetnk row "
                                 "normalisation or reordering)" if spec.itermx is None else
                                 "last psetnk Jacobian: scaled, row-normalised, possibly RCM-permuted"),
    }

    if spec.rhs_probe:
        # One more RHS evaluation through the solver's path (ffun -> PandfRHS_interface).
        # With OMPParallelPandf1=1 and ijactot>0 this is the parallel RHS (OMPPandf1Rhs).
        yl = np.array(bbb.yl[:neq])
        out = np.zeros(neq)
        bbb.ffun(neq, 0.0, yl, out)
        arrays["yldot_probe"] = out
        meta["rhs_probe_parallel"] = bool(int(bbb.ParallelPandf1) > 0 and int(bbb.ijactot) > 0)

    meta["provenance"] = {
        "commit": git_commit(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "uedge_ver": bytes(bbb.uedge_ver[0]).decode(errors="replace").strip()
        if hasattr(bbb.uedge_ver, "__getitem__") else str(bbb.uedge_ver),
        "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS"),
        "OMP_STACKSIZE": os.environ.get("OMP_STACKSIZE"),
        "Nthreads": int(ppp.Nthreads),
        "OMPParallelJac": int(ppp.OMPParallelJac),
        "OMPParallelPandf1": int(ppp.OMPParallelPandf1),
        "ParallelJac": int(bbb.ParallelJac),
        "ParallelPandf1": int(bbb.ParallelPandf1),
        "OMPJacNchunks": int(ppp.OMPJacNchunks),
        "OMPAutoBalance": int(ppp.OMPAutoBalance),
        "OMPLoopJacNchunk": int(ppp.OMPLoopJacNchunk),
        "OMPlenpfac": int(ppp.OMPlenpfac),
    }
    np.savez("record.npz", **arrays)
    return meta


def main():
    spec = RunSpec.from_json(open(sys.argv[1]).read())
    try:
        meta = run(spec)
        status = 0
    except BaseException:  # noqa: B902  (SystemExit from the deck counts as a harness error too)
        meta = {"error": traceback.format_exc()}
        status = 2
    # stdout is shared with the Fortran runtime, which can overwrite what Python prints,
    # so results only go to files
    with open("record.json", "w") as f:
        json.dump(meta, f, indent=1, sort_keys=True)
    # a normal exit, so that the Fortran runtime flushes its buffered output to the log
    sys.exit(status)


if __name__ == "__main__":
    main()
