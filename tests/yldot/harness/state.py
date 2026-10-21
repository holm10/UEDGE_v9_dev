"""Child side of the yldot harness: one evaluation per process, the protocol of PRD section 6.

run(conn, job) executes in a fresh child (forkserver or spawn, see process.py) and sends one message back:
(status, data, message), status "ok", "error" (an exception, including xerrab, which Forthon's kaboom raises as
RuntimeError), "refused" (the family directory holds .uedgerc.py), "owner" (svrpkg/ifixpsor not as the PRD asserts)
or "harness" (uedge was not preloaded).

The steps, numbered as in the PRD (the timestep configuration adds 6a-6c):
    1   chdir to the family directory, exec input.py verbatim; assert svrpkg == 'nksol' and ifixpsor == 0
    2   PRE hook, then the variant's PRE application (scalars and static arrays; variants.apply)
    6a  timestep only: allocate, restore reference_state.h5 (owner, 2026-10-19: not converged_state.h5), POST hook
        and variant, exmain once; keep y_c = yl[:neq] and the restored saved arrays
    3   allocate, restore base_state.h5, restart = 1
    4   POST hook, then the variant's POST application (dynamic arrays; in timestep the value of 6a again)
    6b  timestep only: isyloext = 1, yloext[:neq] = y_c, so exmain sets ylodt = y_c (bbb/odesolve.m:150-153)
    5   issfon = 0, ftol = 1e50, dtreal = 1e20; exmain x W
    6c  timestep only: dtreal = dtuse = dt, saved arrays = the reference values (bbb/pandf_potencur.m:217-222)
    7   yl[neq] = -1 (nksol-RHS flag), yl[neq+1] = 0 (nufak)
    8   pandf(-1, -1, ...) x P: yldot
    8b  yl[neq] = +1 (Jacobian flag), pandf x P: yldot_J; yl[neq] = -1 again
    9   results back through the pipe

uedge is never imported at module level: spawn imports this module to unpickle the target, before run() can check
the isolation.
"""
import importlib
import os
import sys
import traceback
from pathlib import Path

import numpy as np

from . import variants

STATE_VARS = ["nis", "ups", "tes", "tis", "ngs", "tgs", "phis"]  # the saved arrays of step 6c
INDEX_ARRAYS = ["idxn", "idxu", "idxte", "idxti", "idxg", "idxtg", "idxphi", "igyl"]
DIAGNOSTIC_GROUPS = ("Rhsides", "Comflo")  # res*, sources; fluxes (owner, 2026-10-19)
LOG_TAIL = 40


class Stop(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def run(conn, job):
    """Entry point of the child. Output (Python and Fortran) goes to job['log']."""
    sys.stdout.flush()
    sys.stderr.flush()
    fd = os.open(job["log"], os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    os.close(fd)
    try:
        status, data, message = "ok", evaluate(job), ""
    except Stop as e:
        status, data, message = e.status, None, str(e)
    except BaseException:
        status, data, message = "error", None, traceback.format_exc()
    sys.stdout.flush()
    sys.stderr.flush()
    conn.send((status, data, message))
    conn.close()


def text(value):
    """A Forthon character variable as a str."""
    s = value.tobytes().decode(errors="replace") if hasattr(value, "tobytes") else str(value)
    return s.strip().strip("b'\" ")


def hook(spec):
    """'module:function' -> the function, called as f(bbb, com); None -> no-op. Variants go through job['variant']."""
    if spec is None:
        return lambda bbb, com: None
    module, _, name = spec.partition(":")
    return getattr(importlib.import_module(module), name)


def steady(bbb):
    """Step 5's settings: evaluate only, unscaled, no time step."""
    bbb.issfon = 0
    bbb.ftol = 1e50
    bbb.dtreal = 1e20


def diagnostics(bbb):
    """Every allocated real array of the diagnostic groups, copied."""
    out = {}
    for name in bbb.varlist():
        if bbb.getgroup(name) not in DIAGNOSTIC_GROUPS:
            continue
        a = getattr(bbb, name, None)
        if isinstance(a, np.ndarray) and a.size and a.dtype.kind == "f":
            out[name] = a.copy()
    return out


def evaluate(job):
    family = Path(job["family"])
    if job["mode"] == "spawn":
        import uedge  # noqa: F401  cwd and HOME are the empty directory here (process.py)
    if "uedge" not in sys.modules:
        raise Stop("harness", "uedge is not in sys.modules: the forkserver preload failed")
    if (family / ".uedgerc.py").exists():
        raise Stop("refused", "{} holds .uedgerc.py, which import uedge would execute".format(family))

    # 1
    os.chdir(family)
    source = family / "input.py"
    exec(compile(source.read_text(), str(source), "exec"), {"__name__": "__family_input__"})

    from uedge import bbb, com
    from uedge.hdf5 import hdf5_restore

    svrpkg, ifixpsor = text(bbb.svrpkg), int(bbb.ifixpsor)
    if svrpkg != "nksol" or ifixpsor != 0:
        raise Stop("owner", "{}: svrpkg={!r} ifixpsor={}; PRD section 6 asserts nksol and 0: ask the epic owner"
                   .format(family.name, svrpkg, ifixpsor))
    pre, post = hook(job["pre"]), hook(job["post"])
    variant = job["variant"]
    timestep = job["config"] == "timestep"

    # 2
    pre(bbb, com)
    rec_pre = variants.apply(variant, "PRE")
    rec_post = None

    # 6a
    if timestep:
        bbb.allocate()
        hdf5_restore("reference_state.h5")
        bbb.restart = 1
        saved = {v: np.array(getattr(bbb, v)).copy() for v in STATE_VARS}
        post(bbb, com)
        rec_post = variants.apply(variant, "POST")
        steady(bbb)
        bbb.exmain()
        neq_c = int(bbb.neq)
        y_c = bbb.yl[:neq_c].copy()

    # 3, 4
    bbb.allocate()
    hdf5_restore("base_state.h5")
    bbb.restart = 1
    post(bbb, com)
    try:
        rec_post = variants.apply(variant, "POST", previous=rec_post)
    except variants.Mismatch as e:
        raise Stop("owner", "{}; irregular: ask the epic owner (decision 23)".format(e))

    # 6b
    if timestep:
        bbb.isyloext = 1
        bbb.yloext[:neq_c] = y_c

    # 5
    steady(bbb)
    for _ in range(job["w"]):
        bbb.exmain()
    neq = int(bbb.neq)
    if timestep and neq != neq_c:
        raise Stop("error", "neq changed between the passes: {} at reference_state.h5, {} at base_state.h5"
                   .format(neq_c, neq))
    if bbb.yl.size < neq + 2:
        raise Stop("error", "yl holds {} entries, need neq+2 = {}".format(bbb.yl.size, neq + 2))

    # 6c
    if timestep:
        bbb.dtreal = job["dt"]
        bbb.dtuse[:] = job["dt"]
        for v, a in saved.items():
            getattr(bbb, v)[...] = a

    # 7, 8
    bbb.yl[neq] = -1.0
    bbb.yl[neq + 1] = 0.0
    for _ in range(job["p"]):
        bbb.pandf(-1, -1, neq, 0.0, bbb.yl, bbb.yldot)
    yldot = bbb.yldot[:neq].copy()

    # 8b
    bbb.yl[neq] = 1.0
    for _ in range(job["p"]):
        bbb.pandf(-1, -1, neq, 0.0, bbb.yl, bbb.yldot)
    yldot_j = bbb.yldot[:neq].copy()
    bbb.yl[neq] = -1.0

    # 9
    out = {"neq": neq, "yldot": yldot, "yldot_J": yldot_j, "dtreal": float(bbb.dtreal),
           "uedge_ver": text(bbb.uedge_ver)}
    for name in INDEX_ARRAYS:
        out[name] = np.array(getattr(bbb, name)).copy()
    if timestep:
        # what steps 6b and 6c left in place at the pandf calls, for the smoke test
        out["timestep_state"] = {"y_c": y_c, "ylodt": bbb.ylodt[:neq].copy(), "yl": bbb.yl[:neq].copy(),
                                 "saved": {v: np.array(getattr(bbb, v)).copy() for v in STATE_VARS}}
    if variant:
        out["variant"] = {"PRE": rec_pre, "POST": rec_post}
    if job["diagnostics"]:
        out["diagnostics"] = diagnostics(bbb)
    return out
