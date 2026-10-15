"""AIUE-61 G9b: the OpenMP Jacobian on an upstream pytests case, against serial.

run  mode (one fresh process, in a copy of the case directory, environment as AIUE-61-launch.sh):
    AIUE-61-pytests_omp.py run ARM THREADS '{"ppp": {...}}'      -> pyomp.json, jac.npz
  The sequence of AIUE-53's harness/pytests_worker.py (and of the test's test_reference):
  exec input.py; issfon=1; ftol=1e20; exmain(); equation switches from solution.h5:pytests/default and nis..phis
  from solution.h5:bbb; exmain(). ARM is serial | jac (OMPParallelJac=1, OMPParallelPandf1=0).
compare mode:
    AIUE-61-pytests_omp.py compare SERIAL_RUNDIR RUNDIR...       -> prints one line per run and G9b PASS/FAIL
  Per run: bitwise equal to the first run of the same settings (determinism), the post-exmain Jacobian against
  serial with the AIUE-56 C1-gate bounds over ALL rows (magnitude: max|J| <= 10 x serial; deviation: every
  mismatching entry, absent = 0, |a-b| <= 1e-6 x the serial row max), and, across thread counts with the same
  ppp settings, bitwise identity.
"""
import hashlib, importlib.util, json, os, sys


def run(arm, threads, extra):
    import numpy as np
    from h5py import File
    sys.path.insert(0, os.getcwd())
    from uedge import bbb, ppp
    from Forthon import package, packageobject
    spec = importlib.util.spec_from_file_location("input", "input.py")
    spec.loader.exec_module(importlib.util.module_from_spec(spec))
    for k in ("CheckJac", "CheckPandf1", "ForceSerialCheck"):
        setattr(ppp, k, 0)
    ppp.OMPParallelPandf1 = 0
    ppp.OMPParallelJac = 1 if arm == "jac" else 0
    ppp.Nthreads = threads
    for k, v in extra.get("ppp", {}).items():
        setattr(ppp, k, v)
    bbb.issfon = 1
    bbb.ftol = 1e20
    bbb.exmain()

    def setdata(var, value):
        for pkg in package():
            obj = packageobject(pkg)
            if var in obj.varlist():
                obj.__setattr__(var, value)

    with File("solution.h5", "r") as f:
        for eq in ["isnion", "isupon", "isteon", "istion", "isngon", "istgon", "isphion"]:
            setdata(eq, f["pytests"]["default"][eq][()])
        g = f["bbb"] if "bbb" in f else f["restore/bbb"]
        for var in ["nis", "ups", "tes", "tis", "ngs", "tgs", "phis"]:
            setdata(var, g[var][()])
    bbb.exmain()
    neq = int(bbb.neq); nnz = int(bbb.jaci[neq]) - 1
    jac, jacj, jaci = np.array(bbb.jac[:nnz]), np.array(bbb.jacj[:nnz]), np.array(bbb.jaci[:neq + 1])
    h = hashlib.sha256()
    for a in (jac, jacj, jaci, np.array(bbb.yldot[:neq]), np.array(bbb.sfscal[:neq])):
        h.update(np.ascontiguousarray(a).tobytes())
    out = {"arm": arm, "threads": threads, "extra": extra, "neq": neq, "nnz": nnz, "hash": h.hexdigest()[:16],
           "fnrm": float(bbb.get_fnrm(bbb.dtreal)).hex(), "ParallelJac": int(bbb.ParallelJac),
           "NchunksJac": int(ppp.NchunksJac) if arm == "jac" else None, "OMP_NUM_THREADS": os.environ.get(
               "OMP_NUM_THREADS")}
    np.savez("jac.npz", jac=jac, jacj=jacj, jaci=jaci)
    json.dump(out, open("pyomp.json", "w"), indent=1)


def load(d):
    import numpy as np
    meta = json.load(open(os.path.join(d, "pyomp.json")))
    z = np.load(os.path.join(d, "jac.npz"))
    ptr = z["jaci"].astype(np.int64)
    rows = np.repeat(np.arange(len(ptr) - 1), np.diff(ptr))
    return meta, {(int(r), int(c)): float(v) for r, c, v in zip(rows, z["jacj"].astype(np.int64), z["jac"])}


def compare(sdir, rdirs):
    smeta, s = load(sdir)
    rmax = {}
    for (r, _), v in s.items():
        rmax[r] = max(rmax.get(r, 0.0), abs(v))
    smag = max(abs(v) for v in s.values())
    ok = True
    first = {}
    for d in rdirs:
        meta, a = load(d)
        key = json.dumps(meta["extra"], sort_keys=True)
        problems = []
        if meta["arm"] != "jac" or meta["ParallelJac"] != 1 or str(meta["OMP_NUM_THREADS"]) != str(meta["threads"]):
            problems.append("arm/threads not as requested")
        if max(abs(v) for v in a.values()) > 10 * smag:
            problems.append("magnitude")
        worst, nmis = 0.0, 0
        for k in set(s) | set(a):
            x, y = a.get(k, 0.0), s.get(k, 0.0)
            if x != y or (k in a) != (k in s):
                nmis += 1
                rm = rmax.get(k[0], 0.0)
                ratio = abs(x - y) / rm if rm > 0 else float("inf")
                worst = max(worst, ratio)
        if worst > 1e-6:
            problems.append("deviation")
        if key in first:
            if meta["hash"] != first[key]["hash"]:
                problems.append("differs from {} (same settings)".format(first[key]["dir"]))
        else:
            first[key] = {"hash": meta["hash"], "dir": d}
        ok = ok and not problems
        print("{}: threads {} chunks {} hash {} vs serial {} entries, worst {:.3g} x row max {}".format(
            d, meta["threads"], meta["NchunksJac"], meta["hash"], nmis, worst, "OK" if not problems else problems))
    print("G9b", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(sys.argv[2], int(sys.argv[3]), json.loads(sys.argv[4]) if len(sys.argv) > 4 else {})
    else:
        sys.exit(compare(sys.argv[2], sys.argv[3:]))
