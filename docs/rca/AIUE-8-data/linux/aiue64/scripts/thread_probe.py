"""AIUE-64 L5 thread probe: did OpenMP threads actually run in the fix build?
Usage (cwd anywhere): python -I thread_probe.py RUNDIR   with OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=2 and
UEDGE_OMP_RATES_DIR set. Prepares RUNDIR from the AIUE-57 harness case, runs the deck, applies the tebox preset
and the jac arm at Nthreads=2, runs one evaluation (ftol=1e20, as the harness does), and counts the threads in
/proc/self/task before and after, and the libgomp mappings in /proc/self/maps."""
import os
import sys

H = "/work/harness/tests/deterministic_omp"
sys.path.insert(0, H)
from harness.config import ARMS, DIAGNOSTIC_SWITCHES, apply_preset  # noqa: E402
from harness.runner import prepare_rundir  # noqa: E402


def ntask():
    return len(os.listdir("/proc/self/task"))


rundir = sys.argv[1]
prepare_rundir(rundir)
os.chdir(rundir)
sys.path.insert(0, rundir)
print("threads at start", ntask())
import uedge  # noqa: E402,F401
n0 = ntask()
print("n0 (after import uedge)", n0)
from input_mod4 import bbb, ppp  # noqa: E402  runs the deck (serial)
print("threads after the deck", ntask())
apply_preset(bbb, "tebox")
for name in DIAGNOSTIC_SWITCHES:
    setattr(ppp, name, 0)
for name, value in ARMS["jac"].items():
    setattr(ppp, name, value)
ppp.Nthreads = 2
bbb.ftol = 1e20
bbb.exmain()
n1 = ntask()
gomp = sum(1 for line in open("/proc/self/maps") if "libgomp" in line)
print("n1 (after the tebox jac exmain, Nthreads=2)", n1)
print("OMPParallelJac", int(ppp.OMPParallelJac), "Nthreads", int(ppp.Nthreads))
print("libgomp mappings", gomp)
print("RESULT", "PASS" if (n1 - n0 >= 1 and gomp >= 1) else "FAIL", "n1-n0 =", n1 - n0)
