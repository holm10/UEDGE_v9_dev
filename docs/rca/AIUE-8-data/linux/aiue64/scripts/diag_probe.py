"""AIUE-64 DIAGNOSTIC (not a gate, run after the pre-registered L5 thread probe failed): when are libgomp
worker threads created, and do they do work during the Jacobian? Prints, at each stage, every thread of the
process (tid: utime+stime in clock ticks from /proc/self/task/<tid>/stat).
Usage: python -I diag_probe.py RUNDIR PRESET ARM NTHREADS   (OMP_NUM_THREADS set by the caller)."""
import os
import sys

H = "/work/harness/tests/deterministic_omp"
sys.path.insert(0, H)
from harness.config import ARMS, DIAGNOSTIC_SWITCHES, apply_preset  # noqa: E402
from harness.runner import prepare_rundir  # noqa: E402


def threads():
    out = {}
    for tid in sorted(os.listdir("/proc/self/task"), key=int):
        with open("/proc/self/task/{}/stat".format(tid)) as f:
            text = f.read()
        rest = text[text.rindex(")") + 2:].split()
        out[int(tid)] = int(rest[11]) + int(rest[12])  # utime + stime
    return out


def show(stage):
    t = threads()
    print("STAGE {:<32s} n={} ticks={}".format(stage, len(t), t), flush=True)
    return t


rundir, preset, arm, nth = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
prepare_rundir(rundir)
os.chdir(rundir)
sys.path.insert(0, rundir)
show("start")
import uedge  # noqa: E402,F401
show("after import uedge")
from input_mod4 import bbb, ppp  # noqa: E402
before = show("after the deck")
apply_preset(bbb, preset)
for name in DIAGNOSTIC_SWITCHES:
    setattr(ppp, name, 0)
for name, value in ARMS[arm].items():
    setattr(ppp, name, value)
ppp.Nthreads = nth
bbb.ftol = 1e20
bbb.exmain()
after = show("after exmain ({} {} N={})".format(preset, arm, nth))
main = os.getpid()
work = {tid: after[tid] - before.get(tid, 0) for tid in after if tid != main}
print("DELTA non-main thread ticks during exmain:", work, flush=True)
print("OMPParallelJac", int(ppp.OMPParallelJac), "Nthreads", int(ppp.Nthreads), flush=True)
