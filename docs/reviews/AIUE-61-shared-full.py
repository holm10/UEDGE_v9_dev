"""AIUE-61 G0b: shared (non-threadprivate) variables written by ONE FULL pandf(-1,-1) in Jacobian mode.

The per-chunk reset of AIUE-61 runs full evaluations on every OpenMP worker. This applies the sentinel test of AIUE-50's
tests/deterministic_omp/tools/scan_shared_state.py (feature/v9-AIUE-50-shared-state-scan) with its column pair
replaced by one full pandf: every variable of every package that is NOT +threadprivate (per the .v files of --src) is
set to a sentinel (reals: the next representable number above the value, elementwise; integers +1; logicals negated)
in a forked child, a full pandf runs with yl(neq+1)=1, and the variable is WRITTEN if any element no longer holds the
sentinel. Character variables are not tested.
Usage (through AIUE-61-launch.sh, 1 thread; serial or OpenMP build with the switches 0):
    AIUE-61-shared-full.py HARNESS_DIR AIUE50_TOOLS_DIR SRC_TREE   -> shared_full.json
PASS (plan G0b): WRITTEN is a subset of AIUE-60 Probe S Parts A and B (on the combined tree: of whatever AIUE-60 leaves
non-threadprivate). Anything else: stop and report.
"""
import json, os, sys
hd, tools, src = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, hd); sys.path.insert(0, tools); sys.path.insert(0, os.getcwd())
import numpy as np
from scan_ompcopy import parse_v  # AIUE-50 tool: the +threadprivate list from the .v files
from harness.config import ARMS, apply_preset
from input_mod4 import bbb, ppp
import uedge
apply_preset(bbb, "full")
for k, v in ARMS["serial"].items():
    setattr(ppp, k, v)
ppp.Nthreads = 1
bbb.ftol = 1e20
bbb.exmain()
neq = int(bbb.neq)
PK = ["bbb", "com", "api", "aph", "ppp", "flx", "grd", "svr", "wdf", "ncl"]
mods = {p: getattr(uedge, p) for p in PK if hasattr(uedge, p)}
tp = set()
for p in mods:
    v = os.path.join(src, p, f"{p}.v")
    if os.path.exists(v):
        tp |= {(p, r["name"]) for r in parse_v(v, p)}
names = [(p, n) for p, m in mods.items() for n in m.varlist() if (p, n) not in tp]
yl = np.array(bbb.yl, copy=True)
yl[neq] = 1.0  # Jacobian mode, as OMPJacBuilder's ylcopy
wk = np.zeros_like(yl)
bbb.pandf(-1, -1, neq, 0.0, yl, wk)

# AIUE-60 Probe S (plan d2fac6e): Part A (default paths) and Part B (non-default paths)
PART_A = {"bbb.areapl", "bbb.TimingPandfOn", "com.nfsp", "com.ttimpfe", "com.ttimpjf", "com.ttnpg", "com.ttngxlog",
          "com.ttngylog", "com.ttngfd2", "com.ttngfxy", "com.totintrv"}
PART_B = {"com.ghxpt", "com.gvxpt", "com.sxyxpt", "bbb.sputflxllim", "bbb.sputflxrlim", "bbb.iwalli", "bbb.iwallo",
          "bbb.fngysi", "bbb.fngyso", "aph.workh", "aph.iflag_aph"}
res = {"neq": neq, "yl_neq_plus_1": float(yl[neq]), "n_candidates": len(names), "n_threadprivate": len(tp),
       "written": {}, "errors": {}}
for (p, n) in names:
    try:
        val = mods[p].getpyobject(n)
    except Exception:
        continue
    if isinstance(val, (bytes, str)) or (isinstance(val, np.ndarray) and (val.dtype.kind in "SUO" or val.size == 0)):
        continue
    if isinstance(val, np.ndarray):
        val = val.copy()
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(r)
        out = "error"
        try:
            m = mods[p]
            if isinstance(val, np.ndarray):
                arr = m.getpyobject(n)
                sent = np.nextafter(val, np.inf) if arr.dtype.kind == "f" else (~val if arr.dtype.kind == "b" else val + 1)
                arr[...] = sent
            else:
                sent = (np.nextafter(val, np.inf) if isinstance(val, float)
                        else (not val) if isinstance(val, bool) else val + 1)
                setattr(m, n, sent)
            bbb.pandf(-1, -1, neq, 0.0, yl, wk)
            now = m.getpyobject(n)
            if isinstance(val, np.ndarray):
                a, b = np.asarray(sent), np.asarray(now)
                nw = int(np.count_nonzero(a.view(np.int64) != b.view(np.int64))) if a.dtype.kind == "f" else int(
                    np.count_nonzero(a != b))
            else:
                nw = int(type(val)(sent) != type(val)(now))
            out = f"WRITTEN:{nw}" if nw else "not written"
        except BaseException as e:  # noqa: BLE001
            out = f"error:{type(e).__name__}"
        os.write(w, out.encode())
        os._exit(0)
    os.close(w)
    data = os.read(r, 200).decode()
    os.close(r)
    _, status = os.waitpid(pid, 0)
    if not data:
        data = f"crash(status={status})"
    key = f"{p}.{n}"
    if data.startswith("WRITTEN"):
        res["written"][key] = data
    elif data != "not written":
        res["errors"][key] = data
w = set(res["written"])
res["in_part_A"] = sorted(w & PART_A)
res["in_part_B"] = sorted(w & PART_B)
res["outside_probe_S"] = sorted(w - PART_A - PART_B)
res["G0b"] = "PASS" if not res["outside_probe_S"] else "STOP: outside Probe S"
json.dump(res, open("shared_full.json", "w"), indent=1, sort_keys=True)
