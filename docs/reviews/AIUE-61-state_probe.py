"""AIUE-61 G0a: does a full pandf(-1,-1) in Jacobian mode erase the column-loop history?

Serial path, full problem. S0 = every variable of every package after a full pandf with yl(neq+1)=1 (Jacobian mode,
as sfsetnk/jac_calc callers set it, bbb/oderhs.m:1716). For each of 4 column regions: a Jacobian-like column loop
(perturbed local pandf, restoring local pandf, the isjacreset call; values discarded) -> S1, then a full pandf -> S2.
Reports the variables with S1 != S0 (the history) and S2 != S0 (what a full pandf doesn't reset), bitwise
(+0/-0 and NaN payloads included).
Usage (through AIUE-61-launch.sh, 1 thread, a serial or OpenMP build with the switches 0):
    AIUE-61-state_probe.py HARNESS_DIR      -> state_probe.json
PASS (plan G0a): in every region, S2 != S0 only for timers/counters and the Jacobian_restore scratch.
"""
import json, os, sys
hd = sys.argv[1]
sys.path.insert(0, hd); sys.path.insert(0, os.getcwd())
import numpy as np
from harness.config import ARMS, apply_preset
from input_mod4 import bbb, com, ppp
import uedge
apply_preset(bbb, "full")
for k, v in ARMS["serial"].items():
    setattr(ppp, k, v)
ppp.Nthreads = 1
bbb.ftol = 1e20
bbb.exmain()
neq = int(bbb.neq)
numvar = int(bbb.numvar)
yl = np.array(bbb.yl, copy=True)
yl[neq] = 1.0  # Jacobian mode
wk = np.zeros_like(yl)
PKGS = {p: getattr(uedge, p) for p in ("bbb", "com", "api", "aph", "wdf", "svr", "flx", "grd", "ppp", "ncl")
        if hasattr(uedge, p)}
# timers, counters and per-call scratch: allowed to differ after the reset (plan G0a)
ALLOWED_GROUPS = {("bbb", "Jacobian_restore"), ("bbb", "PandfTiming"), ("com", "Timing"), ("com", "Timespl")}


def group_of(p, name):
    try:
        return PKGS[p].getgroup(name)
    except Exception:
        return "?"


def snap():
    out = {}
    for pn, p in PKGS.items():
        for name in p.varlist():
            try:
                v = p.getpyobject(name)
            except Exception:
                continue
            if isinstance(v, np.ndarray):
                if v.dtype.kind in "fiucb":
                    out[(pn, name)] = np.array(v, copy=True)
            elif isinstance(v, (int, float, bool, np.generic)):
                out[(pn, name)] = np.array(v)
    return out


def diff(a, b):
    bad = []
    for k in a:
        if k not in b or a[k].shape != b[k].shape:
            bad.append([k[0] + "." + k[1], "shape"])
            continue
        x, y = a[k], b[k]
        if x.dtype.kind == "f" and x.dtype.itemsize == 8:
            ne = x.view(np.int64) != y.view(np.int64)
        else:
            ne = x != y
        n = int(np.count_nonzero(ne))
        if n:
            bad.append([k[0] + "." + k[1], n])
    return bad


def column_loop(iv0, iv1):
    """Mirror of LocalJacBuilder's column loop (values discarded), 1-based iv0..iv1."""
    suscal = np.array(bbb.suscal); igyl = np.array(bbb.igyl)
    for iv in range(iv0, iv1 + 1):
        xc, yc = int(igyl[iv - 1, 0]), int(igyl[iv - 1, 1])
        yold = yl[iv - 1]
        dyl = float(bbb.delperturb) * (abs(yold) + float(bbb.dylconst) / suscal[iv - 1])
        yl[iv - 1] = yold + dyl
        bbb.pandf(xc, yc, neq, 0.0, yl, wk)
        yl[iv - 1] = yold
        bbb.pandf(xc, yc, neq, 0.0, yl, wk)
        if iv % numvar == 0:
            bbb.pandf(xc, yc, neq, 0.0, yl, wk)


res = {"neq": neq, "numvar": numvar, "yl_neq_plus_1": float(yl[neq]), "packages": sorted(PKGS), "regions": []}
bbb.pandf(-1, -1, neq, 0.0, yl, wk)
y0 = wk.copy()
S0 = snap()
res["n_vars"] = len(S0)
ok = True
for (a, b) in [(1, 3000), (12001, 15000), (20001, 23000), (41001, neq)]:
    column_loop(a, b)
    S1 = snap()
    bbb.pandf(-1, -1, neq, 0.0, yl, wk)
    S2 = snap()
    after = diff(S0, S2)
    unexpected = [d for d in after if (d[0].split(".")[0], group_of(d[0].split(".")[0], d[0].split(".", 1)[1]))
                  not in ALLOWED_GROUPS]
    ok = ok and not unexpected and bool(np.array_equal(wk.view(np.int64), y0.view(np.int64)))
    res["regions"].append({"cols": [a, b], "history_vars": diff(S0, S1), "after_reset_vars": after,
                           "after_reset_groups": sorted({group_of(d[0].split(".")[0], d[0].split(".", 1)[1])
                                                         for d in after}),
                           "unexpected_after_reset": unexpected,
                           "yldot_bitwise_equal": bool(np.array_equal(wk.view(np.int64), y0.view(np.int64)))})
    json.dump(res, open("state_probe.json", "w"), indent=1)
res["G0a"] = "PASS" if ok else "FAIL"
json.dump(res, open("state_probe.json", "w"), indent=1)
