"""validate step 4 (AIUE-64): CheckPandf1/CheckJac with 4 threads on a pytests case. Usage: python omp_check.py CASEDIR"""
import os
import sys

os.chdir(sys.argv[1])
sys.path.insert(0, os.getcwd())
from uedge import bbb, ppp  # noqa: E402

exec(open("input.py").read())
ppp.OMPParallelPandf1 = 1
ppp.OMPParallelJac = 1
ppp.Nthreads = 4
ppp.CheckPandf1 = 1
ppp.CheckJac = 1
bbb.exmain()
print("OMPCHECK done iterm", int(bbb.iterm), flush=True)
