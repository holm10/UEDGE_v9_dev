"""Prepare a harness run directory (case files + spec.json) without running it. Args: rundir preset threads [itermx]."""
import sys
sys.path.insert(0, "/Users/holma/Documents/uedge/src/uedge-wt/AIUE-57/tests/deterministic_omp")
from harness.config import RunSpec
from harness.runner import prepare_rundir
import os
rundir, preset, threads = sys.argv[1], sys.argv[2], int(sys.argv[3])
itermx = int(sys.argv[4]) if len(sys.argv) > 4 else None
spec = RunSpec(preset=preset, arm="jac", threads=threads, itermx=itermx, omp_stacksize="64M")
spec.validate()
prepare_rundir(rundir)
os.makedirs(os.path.join(rundir, "home"))
open(os.path.join(rundir, "spec.json"), "w").write(spec.to_json())
