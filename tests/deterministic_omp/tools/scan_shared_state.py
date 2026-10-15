"""Shared (non-threadprivate) Forthon state written during a local pandf (AIUE-50).

Runs the reproducer deck from the current directory (like fingerprint.py), optionally restricted to the Te box,
then mimics one OpenMP Jacobian column outside any parallel region:

    pandf(-1,-1)                        # what OMPJacBuilder does before copying threadprivate state
    yl(iv) += dyl; pandf(xc,yc)         # perturbed local evaluation   -> snapshot "mid"
    yl(iv)  = yold; pandf(xc,yc)        # restoring local evaluation   -> snapshot "after"

for a set of columns iv, and reports every variable that is NOT +threadprivate (per the .v files) in
bbb, com, api, aph, ppp, flx, grd, svr, wdf, ncl whose value differs between the full-RHS state and "mid" or
"after". All Forthon types are covered: real, integer and logical scalars and arrays, and character variables.

Value-preserving writes (a variable set to the value it already holds, or set and reset within the call) are not
visible in a before/after diff, so --sentinel adds a second test: each candidate variable is set to a sentinel
(reals: the next representable number above the value, elementwise; integers: value+1; logicals: negated), the
perturbed+restoring pair of pandf calls is run, and the variable is reported as WRITTEN if any element no longer
holds the sentinel. Every sentinel test runs in a forked child so a sentinel that crashes the code (an index
variable, a dimension) only marks that variable "crash" instead of killing the scan. Character variables are not
sentinel-tested.

Usage (from a copy of tests/deterministic_omp/case, environment as in the README; use the --serial build):
    python -I scan_shared_state.py [--tebox] [--cols all|N|iv,iv,...] [--sentinel] [--pkgs bbb,com,...]
                                   [--src <tree with the .v files>] [--out shared_state.json]

    --cols   columns to perturb: "all" (default for --tebox), N evenly spaced columns (default 12 for the full
             problem), or an explicit comma-separated list of 1-based iv
    --src    source tree for the +threadprivate lists (default: three levels up from this file)

Writes the JSON report (default ./shared_state.json) and prints a summary. Exit status 0.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, ".")

from scan_ompcopy import parse_v  # noqa: E402

PKGS = ["bbb", "com", "api", "aph", "ppp", "flx", "grd", "svr", "wdf", "ncl"]


def opt(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def snapshot(mods, names):
    snap = {}
    for pkg, var in names:
        try:
            v = mods[pkg].getpyobject(var)
        except Exception:
            continue
        if isinstance(v, np.ndarray):
            snap[(pkg, var)] = v.copy()
        elif isinstance(v, (bytes, str, int, float, bool, np.generic)):
            snap[(pkg, var)] = v
    return snap


def differs(a, b):
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        if not (isinstance(a, np.ndarray) and isinstance(b, np.ndarray)) or a.shape != b.shape:
            return -1
        if a.dtype.kind == "f":
            ab, bb = a.view(np.int64) if a.dtype.itemsize == 8 else a, b.view(np.int64) if b.dtype.itemsize == 8 else b
            return int(np.count_nonzero(ab != bb))
        return int(np.count_nonzero(a != b))
    if isinstance(a, float) and isinstance(b, float):
        return int(a.hex() != b.hex())
    return int(a != b)


def main(argv):
    src = opt(argv, "--src", os.path.normpath(os.path.join(HERE, "..", "..", "..")))
    pkgs = opt(argv, "--pkgs", ",".join(PKGS)).split(",")
    out = opt(argv, "--out", "shared_state.json")
    from input_mod4 import bbb  # noqa: E402  (runs the deck)
    import uedge

    mods = {p: getattr(uedge, p) for p in pkgs if hasattr(uedge, p)}
    tp = set()
    for p in mods:
        v = os.path.join(src, p, f"{p}.v")
        if os.path.exists(v):
            tp |= {(p, r["name"]) for r in parse_v(v, p)}
    if "--tebox" in argv:
        bbb.isnion = 0
        bbb.isngon = 0
        bbb.isupon = 0
        bbb.istion = 0
        bbb.isphion = 0
        bbb.isphiofft = 1
        bbb.isteoffxy = 1
        bbb.isteoffxy[3:8, 18:23] = 0
    bbb.ftol = 1e20
    bbb.exmain()
    neq = int(bbb.neq)
    cols = opt(argv, "--cols", "all" if "--tebox" in argv else "12")
    if cols == "all":
        ivs = list(range(1, neq + 1))
    elif "," in cols or not cols.isdigit() or int(cols) > neq:
        ivs = [int(c) for c in cols.split(",")]
    else:
        ivs = sorted(set(np.linspace(1, neq, int(cols)).astype(int).tolist()))

    names = [(p, n) for p, m in mods.items() for n in m.varlist() if (p, n) not in tp]
    yl = np.array(bbb.yl, copy=True)
    yldot0 = np.zeros_like(yl)
    bbb.pandf(-1, -1, neq, 0.0, yl, yldot0)
    base = snapshot(mods, names)

    def column(iv):
        xc, yc = int(bbb.igyl[iv - 1, 0]), int(bbb.igyl[iv - 1, 1])
        yold = yl[iv - 1]
        dyl = float(bbb.delperturb) * (abs(yold) + float(bbb.dylconst) / float(bbb.suscal[iv - 1]))
        wk = yldot0.copy()
        yl[iv - 1] = yold + dyl
        bbb.pandf(xc, yc, neq, 0.0, yl, wk)
        mid = snapshot(mods, names)
        yl[iv - 1] = yold
        bbb.pandf(xc, yc, neq, 0.0, yl, wk)
        return xc, yc, mid

    report = {"neq": neq, "columns": ivs, "tebox": "--tebox" in argv, "n_vars_scanned": len(base),
              "n_threadprivate_skipped": len(tp), "changed_mid": {}, "changed_after": {}, "sentinel": {}}
    for iv in ivs:
        xc, yc, mid = column(iv)
        after = snapshot(mods, names)
        for key in base:
            for tag, snap in (("changed_mid", mid), ("changed_after", after)):
                d = differs(base[key], snap.get(key))
                if d:
                    report[tag].setdefault(f"{key[0]}.{key[1]}", []).append([iv, xc, yc, d])
        # undo persistent changes so every column starts from the full-RHS state
        bbb.pandf(-1, -1, neq, 0.0, yl, yldot0)

    if "--sentinel" in argv:
        iv_s = ivs[len(ivs) // 2]
        for key in base:
            val = base[key]
            if isinstance(val, (bytes, str)) or (isinstance(val, np.ndarray) and val.dtype.kind in "SUO"):
                continue
            if isinstance(val, np.ndarray) and val.size == 0:
                continue
            r, w = os.pipe()
            pid = os.fork()
            if pid == 0:
                os.close(r)
                res = "error"
                try:
                    m = mods[key[0]]
                    if isinstance(val, np.ndarray):
                        arr = m.getpyobject(key[1])
                        if arr.dtype.kind == "f":
                            sent = np.nextafter(val, np.inf)
                        elif arr.dtype.kind == "b":
                            sent = ~val
                        else:
                            sent = val + 1
                        arr[...] = sent
                    else:
                        sent = (np.nextafter(val, np.inf) if isinstance(val, float)
                                else (not val) if isinstance(val, bool) else val + 1)
                        setattr(m, key[1], sent)
                    column(iv_s)
                    now = m.getpyobject(key[1])
                    nw = differs(np.asarray(sent), np.asarray(now)) if isinstance(val, np.ndarray) else differs(
                        type(val)(sent), type(val)(now))
                    res = f"WRITTEN:{nw}" if nw else "not written"
                except BaseException as e:  # noqa: BLE001
                    res = f"error:{type(e).__name__}"
                os.write(w, res.encode())
                os._exit(0)
            os.close(w)
            data = os.read(r, 200).decode()
            os.close(r)
            _, status = os.waitpid(pid, 0)
            if not data:
                data = f"crash(status={status})"
            if data != "not written":
                report["sentinel"][f"{key[0]}.{key[1]}"] = data
        report["sentinel_column"] = iv_s

    with open(out, "w") as f:
        json.dump(report, f, indent=1, sort_keys=True)
    print(f"neq={neq} columns={len(ivs)} vars={len(base)} (threadprivate skipped: {len(tp)})")
    print("changed by perturbed local pandf (mid):", sorted(report["changed_mid"]))
    print("changed after restoring local pandf (after):", sorted(report["changed_after"]))
    if "--sentinel" in argv:
        written = {k: v for k, v in report["sentinel"].items() if v.startswith("WRITTEN")}
        other = {k: v for k, v in report["sentinel"].items() if not v.startswith("WRITTEN")}
        print("sentinel WRITTEN:", written)
        print("sentinel errors/crashes:", other)


if __name__ == "__main__":
    main(sys.argv[1:])
