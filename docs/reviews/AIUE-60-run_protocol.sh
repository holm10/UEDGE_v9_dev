#!/bin/zsh
# AIUE-60 validation protocol (plan Testing 2-4 and pytests). <= 2 UEDGE processes at a time, <= 4 threads each.
W=/Users/holma/Documents/uedge/src/uedge-wt
V=$W/venvs
OUT=$W/logs/AIUE-60/val
H=$W/AIUE-57/tests/deterministic_omp/harness/cli.py
SC=$W/AIUE-53/tests/deterministic_omp/harness/serial_check.py
R=$W/AIUE-60/docs/reviews
P=$V/AIUE-60-omp/bin/python
B=$V/AIUE-56-omp/bin/python
mkdir -p $OUT
log() { echo "$(date '+%F %T') $*" >> $OUT/protocol.log; }
log start
$P -I $SC --base-python $V/AIUE-56-serial/bin/python --new-python $V/AIUE-60-serial/bin/python \
   --base-omp-python $B --new-omp-python $P --cases all --jobs 2 --out $OUT/serial_check > $OUT/serial_check.txt 2>&1
log "serial_check exit $? :: $(grep -a RESULT $OUT/serial_check.txt | tail -1)"
$B $H flow --all --arms jac,jacrhs --threads 2,4 --repeats 2 --max-jobs 2 --gate none --python $B --out $OUT/flow56 > $OUT/flow56.txt 2>&1
log "flow56 exit $?"
$P $H flow --all --arms jac,jacrhs --threads 2,4 --repeats 2 --max-jobs 2 --gate none --python $P --out $OUT/flow60 > $OUT/flow60.txt 2>&1
log "flow60 exit $?"
python3 -I $R/AIUE-60-flow-gates.py --base $OUT/flow56 --new $OUT/flow60 --json $OUT/flow_gates.json > $OUT/flow_gates.txt 2>&1
log "flow gates exit $? :: $(tail -1 $OUT/flow_gates.txt)"
for arm in jac jacrhs; do
  for b in 56 60; do
    py=$V/AIUE-$b-omp/bin/python
    $py $H check --preset tebox --arm $arm --threads 4 --repeats 2 --ppp '{"OMPJacNchunks": -1, "OMPAutoBalance": 0}' \
        --python $py --out $OUT/xb_${arm}_$b > $OUT/xb_${arm}_$b.txt 2>&1
    log "xb $arm $b exit $? :: $(tail -1 $OUT/xb_${arm}_$b.txt)"
  done
  $P $H compare $OUT/xb_${arm}_56/run0 $OUT/xb_${arm}_60/run0 --json $OUT/xb_${arm}_cmp.json > $OUT/xb_${arm}_cmp.txt 2>&1
  log "xb compare $arm exit $? :: $(tail -1 $OUT/xb_${arm}_cmp.txt)"
  for b in 56 60; do
    $P $H compare $OUT/xb_${arm}_$b/run0 $OUT/xb_${arm}_$b/run1 > $OUT/xb_${arm}_${b}_det.txt 2>&1
    log "xb determinism $arm $b exit $?"
  done
done
$P -I $R/AIUE-60-clip-check.py check --python $P --base-python $B --preset ni --clip 1e-6 --threads 4 --repeats 3 --strict --out $OUT/clip_ni > $OUT/clip_ni.txt 2>&1
log "clip ni exit $? :: $(tail -1 $OUT/clip_ni.txt)"
$P -I $R/AIUE-60-clip-check.py check --python $P --base-python $B --preset full --clip 1e-6 --threads 4 --repeats 2 --out $OUT/clip_full > $OUT/clip_full.txt 2>&1
log "clip full exit $? :: $(tail -1 $OUT/clip_full.txt)"
python3 -I $W/logs/AIUE-60/run_donly.py $P $OUT/donly_omp.json 2 > $OUT/donly_omp.txt 2>&1
log "D_only omp :: $(tail -1 $OUT/donly_omp.txt)"
python3 -I $W/logs/AIUE-60/run_donly.py $V/AIUE-60-serial/bin/python $OUT/donly_serial.json 2 > $OUT/donly_serial.txt 2>&1
log "D_only serial :: $(tail -1 $OUT/donly_serial.txt)"
log end
