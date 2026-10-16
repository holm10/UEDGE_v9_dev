"""AIUE-61 validation worker: one Jacobian (ftol=1e20) of a harness preset; hash of the post-exmain Jacobian and timing.
Usage: jworker.py HARNESS_DIR PRESET ARM THREADS '{"ppp": {...}, "bbb": {...}}'. Writes jrun.json."""
import hashlib, json, os, sys, time
hd, preset, arm, threads = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
extra = json.loads(sys.argv[5]) if len(sys.argv) > 5 else {}
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
bbb.ftol = 1e20  # one Jacobian; an extra "bbb" setting (e.g. ftol, itermx for timing over Newton iterations) wins
for k, v in extra.get("bbb", {}).items():
    setattr(bbb, k, v)
t0 = time.time()
bbb.exmain()
out = {"preset": preset, "arm": arm, "threads": threads, "extra": extra, "wall": time.time() - t0,
       "ttjstor": float(com.ttjstor), "iterm": int(bbb.iterm), "ijactot": int(bbb.ijactot)}
neq = int(bbb.neq); nnz = int(bbb.jaci[neq]) - 1
h = hashlib.sha256()
for a in (bbb.jac[:nnz], bbb.jacj[:nnz], bbb.jaci[:neq + 1]):
    h.update(np.ascontiguousarray(a).tobytes())
out["jachash"] = h.hexdigest()[:16]
out["nnz"] = nnz
out["fnrm"] = float(bbb.get_fnrm(bbb.dtreal)).hex()
if int(ppp.OMPParallelJac) == 1:
    out["NchunksJac"] = int(ppp.NchunksJac)
    out["ivmin"] = np.array(ppp.OMPivmin).tolist()[:8]
np.savez("jac.npz", jac=np.array(bbb.jac[:nnz]), jacj=np.array(bbb.jacj[:nnz]), jaci=np.array(bbb.jaci[:neq + 1]))
json.dump(out, open("jrun.json", "w"), indent=1)
