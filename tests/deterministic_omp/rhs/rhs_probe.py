"""AIUE-58: probe the OpenMP parallel RHS (OMPPandf1Rhs) against the serial pandf, in one process.

Run as   python -I rhs_probe.py <spec.json>   in a copy of tests/deterministic_omp/case (see run_probe.sh).
The spec (JSON) holds: harness (path to tests/deterministic_omp of a branch with the harness, for
harness.config.apply_preset and harness.worker.equation_map), preset, threads, steps (list, below),
seed, out (record file name, default probe.json).

Sequence: the deck, the preset, OMPParallelJac=OMPParallelPandf1=1, Nthreads, ftol=1e20, exmain (one
Jacobian, so ijactot>0 and the workers hold the state OMPJacBuilder left). Then each step:
  "same"            P(yl0) twice, then S(yl0)                  (P: bbb.ffun, the parallel RHS; S: bbb.pandf(-1,-1))
  "pert:<eps>"      yl1 = yl0*(1+eps*r), r uniform in [-1,1]: P(yl1) twice, S(yl1), P(yl1) once more
  "back"            P(yl0) after the earlier steps, vs S(yl0)
  "afrac:<f>"       bbb.afrac *= f on the master (Python sees the master's threadprivate copy):
                    P(yl0) twice, S(yl0); afrac restored afterwards
  "atau:<f>"        the same for bbb.atau
Every P is compared with the S of the same yl, bitwise; differences in the sign of a zero are counted
separately (REDUCTION(+) turns -0.0 into +0.0). Writes the comparisons to <out>.
"""
import json
import os
import sys
import time
import traceback


def main(spec_path):
    with open(spec_path) as f:
        spec = json.load(f)
    sys.path.insert(0, spec["harness"])
    sys.path.insert(0, os.getcwd())
    out_path = spec.get("out", "probe.json")
    result = {"spec": spec, "steps": []}
    try:
        run(spec, result)
    except Exception:
        result["error"] = traceback.format_exc()
    with open(out_path, "w") as f:
        json.dump(result, f, indent=1)
    return 2 if "error" in result else 0


def run(spec, result):
    import numpy as np
    from harness.config import DIAGNOSTIC_SWITCHES, apply_preset
    from harness.worker import EQ_CODES, build_identity, equation_map
    from input_mod4 import bbb, com, ppp

    apply_preset(bbb, spec["preset"])
    for name in DIAGNOSTIC_SWITCHES:
        setattr(ppp, name, 0)
    ppp.OMPParallelJac = 1
    ppp.OMPParallelPandf1 = 1
    ppp.Nthreads = spec["threads"]
    for name, value in spec.get("ppp", {}).items():
        setattr(ppp, name, value)
    bbb.ftol = 1e20
    t0 = time.time()
    bbb.exmain()
    neq = int(bbb.neq)
    eq, species = equation_map(bbb, com, neq)
    igyl = np.array(bbb.igyl[:neq, :])
    result["neq"] = neq
    result["ijactot"] = int(bbb.ijactot)
    result["exmain_s"] = round(time.time() - t0, 2)
    result["provenance"] = {"build": build_identity(), "Nthreads": int(ppp.Nthreads),
                            "ParallelPandf1": int(bbb.ParallelPandf1), "ParallelJac": int(bbb.ParallelJac),
                            "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS"),
                            "ix_fl_bc": int(bbb.ix_fl_bc) if "ix_fl_bc" in bbb.varlist() else None,
                            "iflcore": int(bbb.iflcore), "isnicore": [int(v) for v in np.atleast_1d(bbb.isnicore)]}
    result["layout"] = {
        "nx": int(com.nx), "ny": int(com.ny), "nxpt": int(com.nxpt),
        "ixlb": np.atleast_1d(com.ixlb).tolist(), "ixpt1": np.atleast_1d(com.ixpt1).tolist(),
        "ixpt2": np.atleast_1d(com.ixpt2).tolist(), "ixrb": np.atleast_1d(com.ixrb).tolist(),
        "iysptrx1": np.atleast_1d(com.iysptrx1).tolist(), "iysptrx": int(com.iysptrx),
        "Nchunks": int(ppp.Nchunks), "Nxptchunks": np.atleast_1d(ppp.Nxptchunks).tolist(),
        "rangechunk": np.array(ppp.rangechunk).tolist(), "rangexptchunk": np.array(ppp.rangexptchunk).tolist(),
    }
    yl0 = np.array(bbb.yl[: neq + 2])
    rng = np.random.default_rng(spec.get("seed", 58))

    def par(yl):
        out = np.zeros(neq + 2)
        bbb.ffun(neq, 0.0, yl.copy(), out)
        return out[:neq].copy()

    def ser(yl):
        out = np.zeros(neq + 2)
        bbb.pandf(-1, -1, neq, 0.0, yl.copy(), out)
        return out[:neq].copy()

    def compare(name, p, s):
        both_zero = (p == 0) & (s == 0)
        signed = both_zero & (np.signbit(p) != np.signbit(s))
        diff = (p != s) & ~both_zero
        idx = np.nonzero(diff)[0]
        rel = np.abs(p[idx] - s[idx]) / np.maximum(np.abs(s[idx]), 1e-300)
        by_eq = {}
        for i in idx:
            code = EQ_CODES[eq[i]] if eq[i] >= 0 else str(eq[i])
            by_eq[code] = by_eq.get(code, 0) + 1
        cells = sorted({(int(igyl[i, 0]), int(igyl[i, 1])) for i in idx})
        rows = [{"iv": int(i) + 1, "eq": EQ_CODES[eq[i]] if eq[i] >= 0 else int(eq[i]), "species": int(species[i]),
                 "ix": int(igyl[i, 0]), "iy": int(igyl[i, 1]), "par": float(p[i]), "ser": float(s[i]),
                 "rel": float(r)} for i, r in zip(idx[:60], rel[:60])]
        entry = {"name": name, "ndiff": int(idx.size), "nsigned_zero": int(signed.sum()), "by_eq": by_eq,
                 "cells": cells[:80], "ncells": len(cells), "max_rel": float(rel.max()) if idx.size else 0.0,
                 "rows": rows}
        result["steps"].append(entry)
        return entry

    s0 = None
    for step in spec["steps"]:
        kind, _, arg = step.partition(":")
        if kind == "same":
            pa, pb = par(yl0), par(yl0)
            s0 = ser(yl0)
            compare("same/P1", pa, s0)
            compare("same/P2", pb, s0)
        elif kind == "pert":
            eps = float(arg)
            r = rng.uniform(-1.0, 1.0, neq)
            yl1 = yl0.copy()
            yl1[:neq] = yl0[:neq] * (1.0 + eps * r)
            pa, pb = par(yl1), par(yl1)
            s1 = ser(yl1)
            pc = par(yl1)
            compare("pert{}/P1".format(arg), pa, s1)
            compare("pert{}/P2".format(arg), pb, s1)
            compare("pert{}/P3_after_serial".format(arg), pc, s1)
        elif kind == "back":
            pa = par(yl0)
            s0 = ser(yl0)
            compare("back/P1", pa, s0)
        elif kind in ("afrac", "atau"):
            fac = float(arg)
            arr = getattr(bbb, kind)
            saved = np.array(arr)
            arr[...] = saved * fac
            pa, pb = par(yl0), par(yl0)
            s = ser(yl0)
            compare("{}{}/P1".format(kind, arg), pa, s)
            compare("{}{}/P2".format(kind, arg), pb, s)
            arr[...] = saved
            pa = par(yl0)
            s = ser(yl0)
            compare("{}{}/restored".format(kind, arg), pa, s)
        elif kind == "ueinit":
            # what a second exmain does before nksol: ueinit -> splinem -> gallot("Imslwrk") reallocates the
            # master's spline tables; with icntnunk=1 no Jacobian (no OmpCopy, no copyin) follows
            from input_mod4 import api
            before = int(np.asarray(api.emcoef).ctypes.data)
            bbb.ueinit()
            after = int(np.asarray(api.emcoef).ctypes.data)
            result.setdefault("emcoef_address", []).append([before, after])
            pa, pb = par(yl0), par(yl0)
            s0 = ser(yl0)
            compare("ueinit/P1", pa, s0)
            compare("ueinit/P2", pb, s0)
        else:
            raise ValueError("unknown step " + step)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
