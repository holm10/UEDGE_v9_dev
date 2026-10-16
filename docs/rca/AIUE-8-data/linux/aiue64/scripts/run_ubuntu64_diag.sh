#!/bin/bash
# AIUE-64 DIAGNOSTIC after the pre-registered L5 thread probe failed (not a gate).
# Usage: run_ubuntu64_diag.sh FIXCOMMIT
set -u
FIX=$(git -C /mnt/repo rev-parse "$1"); echo "FIX $FIX"
/scripts/clone_harness.sh 8ee189d76b0232cedfe17088574935b10b857df5
env -u LDFLAGS /scripts/build_uedge.sh fix "$FIX"
R=/work/harness/builder/test/Forthon_cases/Forthon_case5
run() { # NAME OMP_NUM_THREADS PRESET ARM NTHREADS
  mkdir -p /tmp/hd
  echo "=== $1: OMP_NUM_THREADS=$2 preset $3 arm $4 Nthreads $5"
  ( cd /tmp && env HOME=/tmp/hd OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=$2 UEDGE_OMP_RATES_DIR=$R \
    /work/venv-fix/bin/python -I /scripts/diag_probe.py /work/diag_$1 $3 $4 $5 ) > /out/diag_$1.log 2>&1
  echo "exit $?"
  grep -a -E '^(STAGE|DELTA|OMPParallelJac|Traceback|  File|[A-Za-z]*Error)' /out/diag_$1.log
}
run A_orig_t2 2 tebox jac 2
run B_t4_te 4 te jac 4
run C_serial_te 4 te serial 1
run D_t1 1 tebox serial 1
echo ALLDONE
