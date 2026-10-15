"""Reviewer check for AIUE-58 R3: dangling pointer (RCA) vs Forthon re-pointing workers to copies of the
uninitialised new block (reviewer hypothesis).

Setup as rhs_probe.py (te preset, jacrhs, ftol=1e20, one exmain). Then:
  base      P(yl0) vs S(yl0)
  keep      hold Python references to every Imslwrk array (old buffers stay alive with valid tables),
            bbb.ueinit(), P vs S twice.
            RCA model (workers' emcoef points at the master's old block): old block alive and valid -> P == S.
            Reviewer model (gallot -> setarraypointer copies the unfilled new block to each worker): P != S.
  reassign  api.<arr> = copy of the master's (filled) array for every Imslwrk array -> setarraypointer copies
            the filled data to the workers; P vs S twice (reviewer model predicts P == S).
"""
import json
import sys

import numpy as np

spec = json.load(open(sys.argv[1]))
sys.path.insert(0, spec["harness"])
sys.path.insert(0, ".")
from harness.config import DIAGNOSTIC_SWITCHES, apply_preset  # noqa: E402
from input_mod4 import api, bbb, ppp  # noqa: E402

apply_preset(bbb, spec["preset"])
for name in DIAGNOSTIC_SWITCHES:
    setattr(ppp, name, 0)
ppp.OMPParallelJac = 1
ppp.OMPParallelPandf1 = 1
ppp.Nthreads = spec["threads"]
bbb.ftol = 1e20
bbb.exmain()
neq = int(bbb.neq)
yl0 = np.array(bbb.yl[: neq + 2])
out = {"ijactot": int(bbb.ijactot), "steps": []}


def par():
    o = np.zeros(neq + 2)
    bbb.ffun(neq, 0.0, yl0.copy(), o)
    return o[:neq].copy()


def ser():
    o = np.zeros(neq + 2)
    bbb.pandf(-1, -1, neq, 0.0, yl0.copy(), o)
    return o[:neq].copy()


def cmp(name, p, s):
    nz = ~((p == 0) & (s == 0))
    d = (p != s) & nz
    idx = np.nonzero(d)[0]
    rel = np.abs(p[idx] - s[idx]) / np.maximum(np.abs(s[idx]), 1e-300)
    out["steps"].append({"name": name, "ndiff": int(idx.size), "max_rel": float(rel.max()) if idx.size else 0.0})


names = ["xdata_api", "ydata_api", "zdata", "fdata_api", "work2", "work3", "xknots_api", "yknots_api",
         "zknots", "emcoef", "z1coef", "z2coef"]
cmp("base/P1", par(), ser())
keep = {n: getattr(api, n) for n in names}
addr_before = {n: int(keep[n].ctypes.data) for n in names}
bbb.ueinit()
addr_after = {n: int(np.asarray(getattr(api, n)).ctypes.data) for n in names}
out["moved"] = {n: addr_before[n] != addr_after[n] for n in names}
out["tables_equal_old_new"] = {n: bool(np.array_equal(keep[n], getattr(api, n))) for n in
                               ["xknots_api", "yknots_api", "zknots", "emcoef"]}
s = ser()
cmp("keep_ueinit/P1", par(), s)
cmp("keep_ueinit/P2", par(), s)
for n in names:
    setattr(api, n, np.array(getattr(api, n)).copy())
s = ser()
cmp("reassign/P1", par(), s)
cmp("reassign/P2", par(), s)
json.dump(out, open("r3.json", "w"), indent=1)
print(json.dumps(out, indent=1))
