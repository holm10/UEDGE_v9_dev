#!/bin/zsh
# usage: build_pair.sh <outdir>   builds AIUE-64 omp then serial from the worktree
OUT=$1; WT=/Users/holma/Documents/uedge/src/uedge-wt/AIUE-64; V=/Users/holma/Documents/uedge/src/uedge-wt/venvs
git -C $WT rev-parse HEAD > $OUT/build_head.txt
git -C $WT status --porcelain > $OUT/build_status.txt
/Users/holma/Documents/uedge/src/uedge-wt/build_uedge.sh $WT $V/AIUE-64-omp omp > $OUT/build_omp.log 2>&1; echo "omp exit $?" >> $OUT/build_exit.txt
/Users/holma/Documents/uedge/src/uedge-wt/build_uedge.sh $WT $V/AIUE-64-serial serial > $OUT/build_serial.log 2>&1; echo "serial exit $?" >> $OUT/build_exit.txt
