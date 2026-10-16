"""AIUE-58: find which threadprivate variable carries the parallel-RHS error between evaluations.

Run with 1 thread (run_probe.sh ... 1 ...), so the chunk order of OMPPandf1Rhs is fixed and the only state
is the master's, which Python can read and write. Spec keys: harness, preset, eps, seed, src (source tree
with bbb/bbb.v, com/com.v, api/api.v, for the +threadprivate list), out.

  S1 = state after the serial pandf(yl1); S0 = state after the serial pandf(yl0)
  base:  restore S0 (serial pandf(yl0)), P(yl1) vs pandf(yl1)  -> the error
  all:   restore S0, set every candidate to its S1 value, P(yl1)  -> should remove it
  each:  restore S0, set one candidate (that differs between S0 and S1) to S1, P(yl1)
A candidate whose S1 value alone removes the error is a sufficient carrier.
"""
import json
import os
import re
import sys
import traceback


def threadprivate_names(src):
    names = []
    for pkg, path in (("bbb", "bbb/bbb.v"), ("com", "com/com.v"), ("api", "api/api.v")):
        with open(os.path.join(src, path)) as f:
            for line in f:
                code = line.split("#", 1)[0]
                if "+threadprivate" in code:
                    m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)", code)
                    if m:
                        names.append((pkg, m.group(1)))
    return names


def main(spec_path):
    with open(spec_path) as f:
        spec = json.load(f)
    sys.path.insert(0, spec["harness"])
    sys.path.insert(0, os.getcwd())
    result = {"spec": spec}
    try:
        run(spec, result)
    except Exception:
        result["error"] = traceback.format_exc()
    with open(spec.get("out", "carrier.json"), "w") as f:
        json.dump(result, f, indent=1)


def run(spec, result):
    import numpy as np
    from harness.config import DIAGNOSTIC_SWITCHES, apply_preset
    from harness.worker import EQ_CODES, equation_map
    from input_mod4 import api, bbb, com, ppp

    pkgs = {"bbb": bbb, "com": com, "api": api}
    apply_preset(bbb, spec["preset"])
    for name in DIAGNOSTIC_SWITCHES:
        setattr(ppp, name, 0)
    ppp.OMPParallelJac = 1
    ppp.OMPParallelPandf1 = 1
    ppp.Nthreads = spec["threads"]
    bbb.ftol = 1e20
    bbb.exmain()
    neq = int(bbb.neq)
    eq, _ = equation_map(bbb, com, neq)
    igyl = np.array(bbb.igyl[:neq, :])
    yl0 = np.array(bbb.yl[: neq + 2])
    rng = np.random.default_rng(spec.get("seed", 58))
    yl1 = yl0.copy()
    yl1[:neq] = yl0[:neq] * (1.0 + float(spec["eps"]) * rng.uniform(-1.0, 1.0, neq))

    def par(yl):
        out = np.zeros(neq + 2)
        bbb.ffun(neq, 0.0, yl.copy(), out)
        return out[:neq].copy()

    def ser(yl):
        out = np.zeros(neq + 2)
        bbb.pandf(-1, -1, neq, 0.0, yl.copy(), out)
        return out[:neq].copy()

    cands = []
    for pkg, name in threadprivate_names(spec["src"]):
        try:
            val = getattr(pkgs[pkg], name)
        except Exception:
            continue
        if isinstance(val, np.ndarray) and val.dtype.kind == "f" and val.size > 0:
            cands.append((pkg, name))

    def snap():
        return {c: np.array(getattr(pkgs[c[0]], c[1])).copy() for c in cands}

    s1 = ser(yl1)
    S1 = snap()
    ser(yl0)
    S0 = snap()
    differ = [c for c in cands if S0[c].shape == S1[c].shape and not np.array_equal(S0[c], S1[c], equal_nan=True)]
    result["ncandidates"] = len(cands)
    result["ndiffer"] = len(differ)

    def count(p):
        bad = (p != s1) & ~((p == 0) & (s1 == 0))
        idx = np.nonzero(bad)[0]
        return int(idx.size), sorted({"{}({},{})".format(EQ_CODES[eq[i]], int(igyl[i, 0]), int(igyl[i, 1]))
                                      for i in idx})[:40]

    def restore0():
        ser(yl0)

    restore0()
    result["base"] = count(par(yl1))
    restore0()
    for c in differ:
        getattr(pkgs[c[0]], c[1])[...] = S1[c]
    result["all"] = count(par(yl1))
    tests = []
    for c in differ:
        restore0()
        getattr(pkgs[c[0]], c[1])[...] = S1[c]
        n, rows = count(par(yl1))
        tests.append({"var": "{}.{}".format(*c), "ndiff": n})
    result["each"] = tests
    result["sufficient"] = [t["var"] for t in tests if t["ndiff"] == 0]
    result["reducing"] = [t for t in tests if t["ndiff"] < result["base"][0]]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
