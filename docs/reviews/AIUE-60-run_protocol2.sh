#!/bin/zsh
# AIUE-60 re-validation after amendment 1 (all gates). <= 2 UEDGE processes at a time, <= 4 threads each.
W=/Users/holma/Documents/uedge/src/uedge-wt
V=$W/venvs
OUT=$W/logs/AIUE-60/val2
H=$W/AIUE-57/tests/deterministic_omp/harness/cli.py
SC=$W/AIUE-53/tests/deterministic_omp/harness/serial_check.py
R=$W/AIUE-60/docs/reviews
P=$V/AIUE-60-omp/bin/python
B=$V/AIUE-56-omp/bin/python
mkdir -p $OUT
log() { echo "$(date '+%F %T') $*" >> $OUT/protocol.log; }
log start
# static Amendment-1 gates
python3 -I $R/AIUE-60-common-check.py --venv $V/AIUE-60-omp --gen $(ls -d $W/AIUE-60/build/temp.*) > $OUT/gcommon.txt 2>&1
log "G-common exit $? :: $(tail -1 $OUT/gcommon.txt)"
{ for t in AIUE-60 AIUE-60-serial; do echo "== $t/com/misc.F"; grep -n -B1 -A1 'acc = acc + dt' $W/$t/com/misc.F; done
  for v in AIUE-60-omp AIUE-60-serial; do echo "== $v compy _acctim_"; so=$(ls $V/$v/lib/python3.13/site-packages/uedge/compy*.so); otool -tV $so | awk '/^_acctim_:/{f=1} f{print} f&&/ret$/{exit}'; done; } > $OUT/gatomic.txt 2>&1
log "G-atomic collected"
python3 -I $R/AIUE-60-iotable-probe.py check --base-python $B --new-python $P --neg-python $V/AIUE-60-omp-pre/bin/python --repeats 2 --out $OUT/iotable > $OUT/iotable.txt 2>&1
log "G-iotable exit $? :: $(tail -1 $OUT/iotable.txt)"
# defaults
$P -I $SC --base-python $V/base-serial/bin/python --new-python $V/AIUE-60-serial/bin/python --base-omp-python $V/base-omp/bin/python --new-omp-python $P --cases all --jobs 2 --out $OUT/serial_check_vs_v9dev > $OUT/serial_check_vs_v9dev.txt 2>&1
log "serial_check vs v9dev exit $? :: $(grep -a '^RESULT' $OUT/serial_check_vs_v9dev.txt)"
$P -I $SC --base-python $V/AIUE-56-serial/bin/python --new-python $V/AIUE-60-serial/bin/python --base-omp-python $B --new-omp-python $P --cases all --jobs 2 --out $OUT/serial_check_vs_aiue56 > $OUT/serial_check_vs_aiue56.txt 2>&1
log "serial_check vs AIUE-56 exit $? :: $(grep -a '^RESULT' $OUT/serial_check_vs_aiue56.txt)"
# flow
$B $H flow --all --arms jac,jacrhs --threads 2,4 --repeats 2 --max-jobs 2 --gate none --python $B --out $OUT/flow56 > $OUT/flow56.txt 2>&1
log "flow56 exit $?"
$P $H flow --all --arms jac,jacrhs --threads 2,4 --repeats 2 --max-jobs 2 --gate none --python $P --out $OUT/flow60 > $OUT/flow60.txt 2>&1
log "flow60 exit $?"
python3 -I $R/AIUE-60-flow-gates.py --base $OUT/flow56 --new $OUT/flow60 --json $OUT/flow_gates.json > $OUT/flow_gates.txt 2>&1
log "flow gates exit $? :: $(tail -1 $OUT/flow_gates.txt)"
for arm in jac jacrhs; do
  for b in 56 60; do
    py=$V/AIUE-$b-omp/bin/python
    $py $H check --preset tebox --arm $arm --threads 4 --repeats 2 --ppp '{"OMPJacNchunks": -1, "OMPAutoBalance": 0}' --python $py --out $OUT/xb_${arm}_$b > $OUT/xb_${arm}_$b.txt 2>&1
    $P $H compare $OUT/xb_${arm}_$b/run0 $OUT/xb_${arm}_$b/run1 > $OUT/xb_${arm}_${b}_det.txt 2>&1
  done
  $P $H compare $OUT/xb_${arm}_56/run0 $OUT/xb_${arm}_60/run0 > $OUT/xb_${arm}_cmp.txt 2>&1
  log "xb $arm compare exit $? :: $(grep -a -o 'AGREE\|MISMATCH' $OUT/xb_${arm}_cmp.txt | head -1); det56 $(grep -a -o 'AGREE\|MISMATCH' $OUT/xb_${arm}_56_det.txt | head -1) det60 $(grep -a -o 'AGREE\|MISMATCH' $OUT/xb_${arm}_60_det.txt | head -1)"
done
# clip
$P -I $R/AIUE-60-clip-check.py check --python $P --base-python $B --preset ni --clip 1e-6 --threads 4 --repeats 3 --strict --out $OUT/clip_ni > $OUT/clip_ni.txt 2>&1
log "clip ni exit $? :: $(tail -1 $OUT/clip_ni.txt)"
$P -I $R/AIUE-60-clip-check.py check --python $P --base-python $B --preset full --clip 1e-6 --threads 4 --repeats 2 --out $OUT/clip_full > $OUT/clip_full.txt 2>&1
log "clip full exit $? :: $(tail -1 $OUT/clip_full.txt)"
# D_only
python3 -I $R/AIUE-60-run-donly.py $P $OUT/donly_omp.json 2 > $OUT/donly_omp.txt 2>&1
log "D_only omp :: $(tail -1 $OUT/donly_omp.txt)"
python3 -I $R/AIUE-60-run-donly.py $V/AIUE-60-serial/bin/python $OUT/donly_serial.json 2 > $OUT/donly_serial.txt 2>&1
log "D_only serial :: $(tail -1 $OUT/donly_serial.txt)"
# timing: interleaved full jac 4 threads, K=5 each, one run at a time
for k in 1 2 3 4 5; do
  for b in 56 60; do
    py=$V/AIUE-$b-omp/bin/python
    $py $H run --preset full --arm jac --threads 4 --python $py --out $OUT/timing/${b}_$k > /dev/null 2>&1
    log "timing $b $k exit $? elapsed $(python3 -I -c "import json;print(json.load(open('$OUT/timing/${b}_$k/record.json'))['elapsed_s'])" 2>/dev/null)"
  done
done
log end
