"""AIUE-61 G9a OpenMP self-checks (validate skill step 4) on a pytests case, run in a copy of the case directory.
Usage: AIUE-61-ompcheck.py pandf1|jac|time THREADS ['{"OMPJacMinChunkLen": 1, ...}']
  jac:    OMPParallelJac=1, CheckJac=1. GATING in G9a (no difference reported).
  pandf1: OMPParallelPandf1=1, OMPParallelJac=1, CheckPandf1=1. REPORT ONLY in G9a (owner decision 2026-10-15 15:35:
          parallel-RHS work is epic AIUE-70); Compare() stops with "diff in rhsnk" on a difference.
  time:   OMPParallelJac=1, no self-check: prints the first Jacobian's com.ttjstor (R4, D_only time).
  The optional third argument sets extra ppp variables (e.g. the AIUE-61 chunking inputs).
Sequence: exec input.py; issfon=1, ftol=1e20, exmain(); then ftol=1e-8, itermx=3, exmain().
Prints "CHECK OK" or "CHECK FAILED ..." with NchunksJac and the first Jacobian's time; the caller records the process
exit status (a crash leaves no CHECK line). Run with GFORTRAN_UNBUFFERED_ALL=y so UEDGE's output survives a crash.
"""
import importlib.util, json, sys
mode, threads = sys.argv[1], int(sys.argv[2])
extra = json.loads(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else {}
from uedge import bbb, com, ppp
spec = importlib.util.spec_from_file_location("input", "input.py")
spec.loader.exec_module(importlib.util.module_from_spec(spec))
ppp.OMPParallelJac = 1
ppp.OMPParallelPandf1 = 1 if mode == "pandf1" else 0
ppp.Nthreads = threads
ppp.CheckPandf1 = 1 if mode == "pandf1" else 0
ppp.CheckJac = 1 if mode == "jac" else 0
for k, v in extra.items():
    setattr(ppp, k, v)
bbb.issfon = 1
bbb.ftol = 1e20
t1 = None
try:
    bbb.exmain()
    t1 = float(com.ttjstor)
    bbb.ftol = 1e-8
    bbb.itermx = 3
    bbb.exmain()
    print("CHECK OK", mode, "iterm", int(bbb.iterm), "NchunksJac", int(ppp.NchunksJac),
          "first-Jacobian ttjstor %.4f s" % t1, flush=True)
except Exception as e:  # noqa: BLE001
    print("CHECK FAILED", mode, type(e).__name__, e, "| NchunksJac", int(ppp.NchunksJac), flush=True)
