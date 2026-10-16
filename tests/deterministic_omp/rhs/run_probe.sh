#!/bin/bash
# AIUE-58: run one script of this folder (rhs_probe.py or rhs_sequence.py) in a fresh process,
# in a fresh copy of the case, with an empty HOME, python -I and pinned OpenMP settings
# (as the AIUE-49 harness runner does).
#   run_probe.sh <python> <script> <rundir> <threads> '<spec json without harness/threads>'
# HARNESS: tests/deterministic_omp of a branch that holds harness/ (default: the AIUE-57 worktree).
# CASE: the case folder (default: ../case next to this script). RATES: the rate-file folder.
set -e
PY=$1; SCRIPT=$2; RUNDIR=$3; T=$4; SPEC=$5
HERE=$(cd "$(dirname "$0")" && pwd)
HARNESS=${HARNESS:-/Users/holma/Documents/uedge/src/uedge-wt/AIUE-57/tests/deterministic_omp}
CASE=${CASE:-$HERE/../case}
RATES=${RATES:-$HERE/../../../builder/test/Forthon_cases/Forthon_case5}
RATES=$(cd "$RATES" && pwd)
mkdir "$RUNDIR"
mkdir "$RUNDIR/home"
for f in input_mod4.py b0p1.hdf5 gridue.hdf5 save_input_mod4.h5 mist.dat; do cp "$CASE/$f" "$RUNDIR/"; done
echo "$SPEC" | "$PY" -I -c "import json,sys; s=json.load(sys.stdin); s['harness']='$HARNESS'; s['threads']=$T; json.dump(s, open('$RUNDIR/spec.json','w'))"
cd "$RUNDIR"
start=$(date +%s)
set +e
env -i PATH=/usr/bin:/bin HOME="$RUNDIR/home" UEDGE_OMP_RATES_DIR="$RATES" OMP_NUM_THREADS=$T OMP_STACKSIZE=512M \
    "$PY" -I "$HERE/$SCRIPT" "$RUNDIR/spec.json" > "$RUNDIR/run.log" 2>&1
rc=$?
echo "exit $rc elapsed $(( $(date +%s) - start )) s load $(uptime | sed 's/.*averages: //')" > "$RUNDIR/status.txt"
exit $rc
