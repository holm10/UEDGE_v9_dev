#!/bin/zsh
# AIUE-60 TSan before/after (plan Testing 5). One UEDGE process at a time, 4 threads. The harness worker is started
# directly in a prepared run directory (launching through cli.py run under TSan segfaults at start-up).
W=/Users/holma/Documents/uedge/src/uedge-wt
WK=$W/AIUE-57/tests/deterministic_omp/harness/worker.py
S=$W/AIUE-50/tests/deterministic_omp/tools/tsan_summary.py
OUT=$W/logs/AIUE-60/tsan2
mkdir -p $OUT
TSANLIB=/opt/homebrew/opt/llvm/lib/clang/23/lib/darwin/libclang_rt.tsan_osx_dynamic.dylib
log() { echo "$(date '+%F %T') $*" >> $OUT/tsan.log; }
for b in pre post; do
  case $b in pre) py=$W/venvs/AIUE-60-tsan-pre/bin/python;; post) py=$W/venvs/AIUE-60-tsan/bin/python;; esac
  for spec in "tebox:" "ng:" "tebox:2" "full:"; do
    p=${spec%%:*}; it=${spec#*:}; name=${b}_${p}${it:+_it$it}
    rd=$OUT/run_$name; mkdir -p $OUT/logs_$name
    python3 -I $W/logs/AIUE-60/tsan_prep.py $rd $p 4 $it
    (cd $rd && env HOME=$rd/home OMP_NUM_THREADS=4 OMP_STACKSIZE=64M \
       UEDGE_OMP_RATES_DIR=$W/AIUE-57/builder/test/Forthon_cases/Forthon_case5 \
       DYLD_INSERT_LIBRARIES=$TSANLIB TSAN_OPTIONS="log_path=$OUT/logs_$name/tsan halt_on_error=0" \
       $py -I -u $WK spec.json > run.log 2>&1)
    rc=$?
    log "$name exit $rc record=$([ -f $rd/record.json ] && echo yes || echo no) reports=$(cat $OUT/logs_$name/tsan.* 2>/dev/null | grep -c 'WARNING: ThreadSanitizer: data race')"
    python3 -I $S $OUT/logs_$name/tsan.* > $OUT/summary_$name.txt 2>&1
  done
done
log end
