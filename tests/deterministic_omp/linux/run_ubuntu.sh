#!/bin/bash
# AIUE-62 round 1 (I1-M1, I1-m6): the CI runner's distribution, ubuntu:24.04 (gcc/gfortran 13.3), linux/amd64.
# 1. the default OpenMP build (CI command, no LDFLAGS) and its import, saved to /out/import_default_ldflags.txt;
# 2. the AIUE-56 build with LDFLAGS=-fopenmp, the FMA scan, Te box K=5 (both arms) and full problem K=5 (jac), 4 threads.
F=1553e756539bb4e66b2241b840fc697e23101a36
/scripts/clone_harness.sh 8ee189d76b0232cedfe17088574935b10b857df5
env -u LDFLAGS /scripts/build_uedge.sh fixnold $F
mkdir -p /tmp/h
{ echo "\$ cd /tmp && HOME=/tmp/h /work/venv-fixnold/bin/python -I -c 'import uedge; from uedge import bbb, ppp'"
  (cd /tmp && HOME=/tmp/h /work/venv-fixnold/bin/python -I -c "import uedge; from uedge import bbb, ppp; print('import OK')") 2>&1
  echo "exit status $?"; gcc --version | head -1; echo "gcc -dumpspecs as-needed occurrences: $(gcc -dumpspecs | grep -c as-needed)"
} > /out/import_default_ldflags.txt
LDFLAGS=-fopenmp /scripts/build_uedge.sh fixld $F
/scripts/fma_scan.sh fixld > /out/fma_fixld.txt 2>&1
C="--cores 5 --max-jobs 1 --gate none"
/scripts/run_flow.sh fixld k5_tebox --configs tebox --threads 4 --repeats 5 $C
/scripts/run_flow.sh fixld k5_full --configs full --threads 4 --repeats 5 --arms jac $C
echo ALLDONE >> /out/flows.log
