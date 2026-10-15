"""AIUE-64 L5 amended thread probe (plan, L5 amendment). One process = one measurement.
Usage: python -I thread_probe2.py RUNDIR ARM NTHREADS   (OMP_NUM_THREADS=NTHREADS, OPENBLAS_NUM_THREADS=1 and
UEDGE_OMP_RATES_DIR set by the caller). Runs the AIUE-57 harness deck, applies the tebox preset and ARM
(jac or serial), takes the baseline, runs one evaluation (ftol=1e20), and prints each thread's CPU time
increase during exmain (ns, from /proc/self/task/<tid>/schedstat; stat ticks as a fallback)."""
import os
import sys

H = "/work/harness/tests/deterministic_omp"
sys.path.insert(0, H)
from harness.config import ARMS, DIAGNOSTIC_SWITCHES, apply_preset  # noqa: E402
from harness.runner import prepare_rundir  # noqa: E402

TICK_NS = 1e9 / os.sysconf("SC_CLK_TCK")
USE_SCHEDSTAT = os.path.exists("/proc/self/task/{}/schedstat".format(os.getpid()))


def cpu_ns():
    out = {}
    for tid in os.listdir("/proc/self/task"):
        if USE_SCHEDSTAT:
            with open("/proc/self/task/{}/schedstat".format(tid)) as f:
                out[int(tid)] = int(f.read().split()[0])
        else:
            with open("/proc/self/task/{}/stat".format(tid)) as f:
                text = f.read()
            rest = text[text.rindex(")") + 2:].split()
            out[int(tid)] = int((int(rest[11]) + int(rest[12])) * TICK_NS)
    return out


rundir, arm, nth = sys.argv[1], sys.argv[2], int(sys.argv[3])
prepare_rundir(rundir)
os.chdir(rundir)
sys.path.insert(0, rundir)
print("resolution", "schedstat ns" if USE_SCHEDSTAT else "stat ticks ({} ns)".format(TICK_NS))
import uedge  # noqa: E402,F401
print("threads after import uedge", len(os.listdir("/proc/self/task")))
from input_mod4 import bbb, ppp  # noqa: E402
apply_preset(bbb, "tebox")
for name in DIAGNOSTIC_SWITCHES:
    setattr(ppp, name, 0)
for name, value in ARMS[arm].items():
    setattr(ppp, name, value)
ppp.Nthreads = nth
bbb.ftol = 1e20
before = cpu_ns()
bbb.exmain()
after = cpu_ns()
main = os.getpid()
workers = sorted(t for t in after if t != main)
inc = [after[t] - before.get(t, 0) for t in workers]
gomp = sum(1 for line in open("/proc/self/maps") if "libgomp" in line)
print("arm {} Nthreads {} OMPParallelJac {} threads {} libgomp_mappings {}".format(
    arm, int(ppp.Nthreads), int(ppp.OMPParallelJac), len(after), gomp))
print("main_ns", after[main] - before.get(main, 0))
print("WORKER_NS", " ".join(str(v) for v in inc))
