#!/bin/bash
# AIUE-64 L5 amended thread probe (formal L5 result, plan "Amendment to a pre-registered check").
# Usage: run_ubuntu64_probe2.sh FIXCOMMIT
set -u
FIX=$(git -C /mnt/repo rev-parse "$1"); echo "FIX $FIX"
/scripts/clone_harness.sh 8ee189d76b0232cedfe17088574935b10b857df5
env -u LDFLAGS /scripts/build_uedge.sh fix "$FIX"
R=/work/harness/builder/test/Forthon_cases/Forthon_case5
run() { # NAME ARM N
  mkdir -p /tmp/hp
  ( cd /tmp && env HOME=/tmp/hp OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=$3 UEDGE_OMP_RATES_DIR=$R \
    /work/venv-fix/bin/python -I /scripts/thread_probe2.py /work/p2_$1 $2 $3 ) > /out/probe2_$1.log 2>&1
  echo "$1 exit $?"
}
run jac_t2 jac 2
run ctl_t2 serial 2
run jac_t4 jac 4
run ctl_t4 serial 4
python3 /scripts/probe2_verdict.py /out > /out/thread_probe2.txt 2>&1
cat /out/thread_probe2.txt
echo ALLDONE
