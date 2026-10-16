"""AIUE-58: two time steps as rundt/continuation_solve take them, the second with icntnunk=1 (no new
Jacobian at its start, so with OMPParallelPandf1=1 its RHS runs on the worker state of the previous
exmain's last Jacobian).

Run with run_probe.sh in a copy of the case. Spec keys: harness, preset, arm (serial|jac|jacrhs), threads,
dtreal (default 1e-9), itermx (default 30), change (optional "<var>:<factor>", applied to bbb.<var>
on the master between the two exmain calls, e.g. "afracs:1.1"), out (default seq.json).
Writes <out> (iterm, ijactot, get_fnrm per exmain) and seq.npz (yl after each exmain). The fnrm sequence
nksol printed is in run.log ("iter=" / "OMP iter=" lines).
"""
import json
import os
import sys
import traceback


def main(spec_path):
    with open(spec_path) as f:
        spec = json.load(f)
    sys.path.insert(0, spec["harness"])
    sys.path.insert(0, os.getcwd())
    result = {"spec": spec, "exmain": []}
    try:
        run(spec, result)
    except Exception:
        result["error"] = traceback.format_exc()
    with open(spec.get("out", "seq.json"), "w") as f:
        json.dump(result, f, indent=1)


def run(spec, result):
    import numpy as np
    from harness.config import ARMS, DIAGNOSTIC_SWITCHES, apply_preset
    from harness.worker import build_identity
    from input_mod4 import bbb, ppp

    apply_preset(bbb, spec["preset"])
    for name in DIAGNOSTIC_SWITCHES:
        setattr(ppp, name, 0)
    for name, value in ARMS[spec["arm"]].items():
        setattr(ppp, name, value)
    ppp.Nthreads = spec["threads"]
    bbb.dtreal = float(spec.get("dtreal", 1e-9))
    bbb.itermx = int(spec.get("itermx", 30))
    result["provenance"] = {"build": build_identity(), "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS")}
    arrays = {}
    for k in (1, 2):
        if k == 2:
            if spec.get("change"):
                var, _, fac = spec["change"].partition(":")
                arr = getattr(bbb, var)
                arr[...] = np.array(arr) * float(fac)
            bbb.icntnunk = 1
        else:
            bbb.icntnunk = 0
        bbb.exmain()
        neq = int(bbb.neq)
        arrays["yl{}".format(k)] = np.array(bbb.yl[:neq])
        result["exmain"].append({"k": k, "icntnunk": int(bbb.icntnunk), "iterm": int(bbb.iterm),
                                 "ijactot": int(bbb.ijactot),
                                 "ParallelPandf1": int(bbb.ParallelPandf1), "ParallelJac": int(bbb.ParallelJac),
                                 "get_fnrm_hex": float(bbb.get_fnrm(bbb.dtreal)).hex()})
    np.savez(os.path.join(os.path.dirname(os.path.abspath(spec.get("out", "seq.json"))), "seq.npz"), **arrays)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
