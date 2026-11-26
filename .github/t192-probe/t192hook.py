"""T192 post hook, run in the yldot child (Runner.evaluate(..., post="t192hook:post")) after allocate and the
restore, before the variant's POST application and exmain. Read-only: it maps the addresses of one out-of-bounds read
(the control file T192_CTRL names the read and the output file) onto the Forthon arrays and appends one JSON line. The probes dir must be on
the child's sys.path (PYTHONPATH, set before the forkserver starts)."""
import json
import os
import re

import numpy as np

PKGS = ("bbb", "com", "api", "aph", "grd", "flx", "svr", "wdf")


def reads(bbb, com, key):
    """(pkg, array, lower bounds, [Fortran index tuples]) of the read key."""
    nx, ny = int(com.nx), int(com.ny)
    if key == "ni3":  # pandf_boundary.m:3474-3475, ni(ixt1,iy,ifld) - ni(ixt,iy,ifld), ifld = nisp + 1, left plate
        ixt = int(np.asarray(com.ixlb).ravel()[0])
        return "bbb", "ni", (0, 0, 1), [(i, iy, 3) for iy in range(ny + 2) for i in (ixt + 1, ixt)]
    if key == "tg2":  # pandf_boundary.m:1876-1881, tg(ix,0,iigsp), iigsp = 2, ngsp = 1
        return "bbb", "tg", (0, 0, 1), [(ix, 0, 2) for ix in range(nx + 2)]
    if key == "fngysi0":  # pandf_boundary.m:556, fngysi(ix, igspsori(isor) = 0): a WRITE before the start
        return "bbb", "fngysi", (0, 1), [(ix, 0) for ix in range(nx + 2)]
    raise KeyError(key)


def arrays():
    import uedge
    out = []
    for pkg in PKGS:
        mod = getattr(__import__("uedge", fromlist=[pkg]), pkg, None)
        if mod is None:
            continue
        for name in mod.varlist():
            try:
                x = getattr(mod, name)
            except Exception:  # noqa: BLE001  unallocated
                continue
            if isinstance(x, np.ndarray) and x.size:
                s = x.__array_interface__["data"][0]
                out.append((s, s + x.nbytes, "{}.{}".format(pkg, name), x.itemsize))
    del uedge
    return sorted(out)


def where(addr, table):
    """'pkg.name[k]' (k the flat element) when addr is inside an array, else 'gap(-a,+b)': the bytes after the array
    that ends before addr and before the one that starts after it, with their names."""
    prev = nxt = None
    for s, e, name, isz in table:
        if s <= addr < e:
            return "{}[{}]".format(name, (addr - s) // isz)
        if e <= addr and (prev is None or e > prev[1]):
            prev = (name, e)
        if s > addr and (nxt is None or s < nxt[1]):
            nxt = (name, s)
    return "gap({}+{}|{}-{})".format(prev[0] if prev else "-", addr - prev[1] if prev else 0,
                                     nxt[0] if nxt else "-", nxt[1] - addr if nxt else 0)


def post(bbb, com):
    ctrl = json.loads(open(os.environ["T192_CTRL"]).read())  # {"read": key or null, "out": path}: the parent sets it
    key = ctrl["read"]
    rec = {"pid": os.getpid(), "env_bytes": sum(len(k) + len(v) + 2 for k, v in os.environ.items())}
    if key:
        pkg, name, lb, idx = reads(bbb, com, key)
        a = np.asarray(getattr(getattr(__import__("uedge", fromlist=[pkg]), pkg), name))
        base = a.__array_interface__["data"][0]
        table = arrays()
        hits = []
        for t in idx:
            off, stride = 0, 1
            for i, n, l in zip(t, a.shape, lb):
                off += (i - l) * stride
                stride *= n
            hits.append(where(base + off * a.itemsize, table))
        rec.update(read=key, array="{}.{}".format(pkg, name), first=hits[0], last=hits[-1],
                   hits=sorted(set(re.sub(r"[+-]\d+", "", h.split("[")[0]) for h in hits)))
    with open(ctrl["out"], "a") as f:
        f.write(json.dumps(rec) + "\n")
