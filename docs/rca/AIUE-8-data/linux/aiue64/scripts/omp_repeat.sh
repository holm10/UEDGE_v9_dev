#!/bin/zsh
# omp_repeat.sh N : run the validate step-4 OpenMP check N times on AIUE-64-omp and base-omp (alternating),
# fresh case copy each time; print exit code, the last meaningful line, and the check lines.
S=/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/5faeea63-d2a3-45e8-a9fe-5854bff514ed/scratchpad/aiue64/validate
P=/Users/holma/Documents/uedge/src/uedge-pytests/pytests/fulltests/nonog_d_c-fb_16x8
V=/Users/holma/Documents/uedge/src/uedge-wt/venvs
for i in $(seq 1 $1); do
  for b in AIUE-64-omp base-omp; do
    C=$S/rep/${b}_$i; mkdir -p $C; cp $P/* $C/
    (cd /tmp && HOME=$(mktemp -d) OMP_NUM_THREADS=4 $V/$b/bin/python -I -X faulthandler $S/omp_check.py $C) > $C.log 2>&1
    rc=$?
    echo "$b run $i exit $rc | jac-identical $(grep -a -c 'jacobian are identical' $C.log) | pandf-identical $(grep -a -c 'pandf are identical' $C.log) | >>>> $(grep -a -c '>>>>' $C.log) | last: $(grep -a -v -E '^\s*$' $C.log | tail -1 | cut -c1-90)"
  done
done
