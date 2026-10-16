#!/bin/bash
# AIUE-61 I2-M1: repeat the G9a OpenMP self-checks (AIUE-61-ompcheck.py) on the D_only default case.
# Usage: AIUE-61-ompcheck_rep.sh OUTDIR VENV MODE K [ppp-json] -- runs K fresh processes (env -i, empty HOME,
# OMP_NUM_THREADS=4, OMP_STACKSIZE=512M, GFORTRAN_UNBUFFERED_ALL=y; no timeout wrapper) and appends one line per
# run to OUTDIR/summary.txt: name, exit status, the CHECK line and the first '>>>>' line.
OUT=$1; VENV=$2; MODE=$3; K=$4; PPP=${5:-}
R=$(cd "$(dirname "$0")" && pwd)
CASE=/Users/holma/Documents/uedge/src/uedge-pytests/pytests/unittests/D_only/nonog/default
PY=/Users/holma/Documents/uedge/src/uedge-wt/venvs/$VENV/bin/python
for k in $(seq 1 $K); do
  d=$OUT/${VENV}_${MODE}${PPP:+_ppp}_$k; mkdir -p $d/home; cp -R $CASE/. $d/
  (cd $d && env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 HOME=$d/home OMP_NUM_THREADS=4 OMP_STACKSIZE=512M \
     GFORTRAN_UNBUFFERED_ALL=y $PY -I "$R/AIUE-61-ompcheck.py" $MODE 4 "$PPP" > run.log 2>&1)
  rc=$?
  echo "$(basename $d) exit=$rc | $(tr -d '\000' < $d/run.log | grep -a 'CHECK ' | tail -1) | $(tr -d '\000' < $d/run.log | grep -a -m1 '>>>>' | tr -s ' ')" >> $OUT/summary.txt
done
