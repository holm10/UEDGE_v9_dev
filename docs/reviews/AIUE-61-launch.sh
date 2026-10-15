#!/bin/bash
# AIUE-61 validation launcher: copies the AIUE-57 harness case into RUNDIR and runs SCRIPT there in a clean
# environment (env -i, empty HOME, python -I).
# Usage: AIUE-61-launch.sh PY RUNDIR THREADS SCRIPT [args...]   (SCRIPT gets HARNESS_DIR as its first argument)
# OMP_STACKSIZE=512M unless AIUE61_NOSTACK=1, in which case it is not set at all (G10b: env -i starts from an empty
# environment, and env -u removes it explicitly in case env -i is ever dropped).
H=${AIUE61_HARNESS:-/Users/holma/Documents/uedge/src/uedge-wt/AIUE-57/tests/deterministic_omp}
RATES=/Users/holma/Documents/uedge/src/uedge-wt/AIUE-57/builder/test/Forthon_cases/Forthon_case5
PY=$1; RD=$2; T=$3; S=$4; shift 4
mkdir -p "$RD/home" && cp "$H"/case/{input_mod4.py,b0p1.hdf5,gridue.hdf5,save_input_mod4.h5,mist.dat} "$RD"/
if [ "${AIUE61_NOSTACK:-0}" = 1 ]; then STACK=(); else STACK=(OMP_STACKSIZE=512M); fi
cd "$RD" && env -i -u OMP_STACKSIZE PATH=/usr/bin:/bin HOME="$RD/home" UEDGE_OMP_RATES_DIR=$RATES OMP_NUM_THREADS=$T \
  "${STACK[@]}" "$PY" -I "$S" "$H" "$@" > run.log 2>&1
echo "$RD exit $?"
