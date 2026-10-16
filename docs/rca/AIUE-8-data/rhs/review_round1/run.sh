#!/bin/bash
# run.sh <python> <script> <rundir> <threads> <preset>
set -e
PY=$1; SCRIPT=$2; RUNDIR=$3; T=$4; PRESET=$5
WT=/Users/holma/Documents/uedge/src/uedge-wt/AIUE-58
HARNESS=/Users/holma/Documents/uedge/src/uedge-wt/AIUE-57/tests/deterministic_omp
CASE=$WT/tests/deterministic_omp/case
RATES=$WT/builder/test/Forthon_cases/Forthon_case5
mkdir -p "$RUNDIR/home"
for f in input_mod4.py b0p1.hdf5 gridue.hdf5 save_input_mod4.h5 mist.dat; do cp "$CASE/$f" "$RUNDIR/"; done
printf '{"harness": "%s", "threads": %s, "preset": "%s"}' "$HARNESS" "$T" "$PRESET" > "$RUNDIR/spec.json"
cd "$RUNDIR"
set +e
env -i PATH=/usr/bin:/bin HOME="$RUNDIR/home" UEDGE_OMP_RATES_DIR="$RATES" OMP_NUM_THREADS=$T OMP_STACKSIZE=512M \
    "$PY" -I "$SCRIPT" "$RUNDIR/spec.json" > "$RUNDIR/run.log" 2>&1
echo "exit $? load $(uptime | sed 's/.*averages: //')" > "$RUNDIR/status.txt"
