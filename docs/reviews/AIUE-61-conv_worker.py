"""AIUE-61 validation driver (recreated from the AIUE-8 q1 driver): run the deck, apply a preset/arm, then NSTEP exmain calls
(fixed dtreal, Jacobian recomputed each step); save per-step iterm/get_fnrm and the final state.
Usage: conv_worker.py HARNESS_DIR PRESET ARM THREADS NSTEP '{"bbb": {...}, "ppp": {...}}'"""
import json, os, sys, time
hd, preset, arm, threads, nstep = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
extra = json.loads(sys.argv[6]) if len(sys.argv) > 6 else {}
sys.path.insert(0, hd); sys.path.insert(0, os.getcwd())
import numpy as np
from harness.config import ARMS, apply_preset
from input_mod4 import bbb, com, ppp
apply_preset(bbb, preset)
for k in ("CheckJac", "CheckPandf1", "ForceSerialCheck"):
    setattr(ppp, k, 0)
for k, v in ARMS[arm].items():
    setattr(ppp, k, v)
ppp.Nthreads = threads
for k, v in extra.get("ppp", {}).items():
    setattr(ppp, k, v)
for k, v in extra.get("bbb", {}).items():
    setattr(bbb, k, v)
out = {"dtreal": float(bbb.dtreal), "ftol": float(bbb.ftol), "itermx": int(bbb.itermx), "extra": extra, "steps": []}
for i in range(nstep):
    bbb.icntnunk = 0
    t0 = time.time()
    bbb.exmain()
    out["steps"].append({"iterm": int(bbb.iterm), "fnrm": float(bbb.get_fnrm(bbb.dtreal)).hex(), "s": time.time() - t0})
    json.dump(out, open("conv.json", "w"))
    if int(bbb.iterm) != 1:
        break
np.savez("state.npz", **{k: np.array(getattr(bbb, k)) for k in ("te", "ti", "ni", "up", "ng", "phi")})
json.dump(out, open("conv.json", "w"))
