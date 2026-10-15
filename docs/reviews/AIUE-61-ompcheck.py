"""AIUE-61 G9a OpenMP check (validate skill step 4) on a pytests case, run in a copy of the case directory.
Usage: AIUE-61-ompcheck.py pandf1|jac THREADS
  pandf1: OMPParallelPandf1=1, OMPParallelJac=1, CheckPandf1=1 (gating: Compare() stops on a difference)
  jac:    OMPParallelJac=1, CheckJac=1 (report only: absolute 1e-14 entry-by-entry comparison)
Prints CHECK OK, or the exception; UEDGE's own messages are in the log.
"""
import importlib.util, sys
mode, threads = sys.argv[1], int(sys.argv[2])
from uedge import bbb, ppp
spec = importlib.util.spec_from_file_location("input", "input.py")
spec.loader.exec_module(importlib.util.module_from_spec(spec))
ppp.OMPParallelJac = 1
ppp.OMPParallelPandf1 = 1 if mode == "pandf1" else 0
ppp.Nthreads = threads
ppp.CheckPandf1 = 1 if mode == "pandf1" else 0
ppp.CheckJac = 1 if mode == "jac" else 0
bbb.issfon = 1
bbb.ftol = 1e20
try:
    bbb.exmain()
    bbb.ftol = 1e-8
    bbb.itermx = 3
    bbb.exmain()
    print("CHECK OK", mode, "iterm", int(bbb.iterm), flush=True)
except Exception as e:  # noqa: BLE001
    print("CHECK FAILED", mode, type(e).__name__, e, flush=True)
