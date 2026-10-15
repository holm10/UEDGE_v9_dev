#!/bin/bash
# AIUE-61 validation protocol (plan .claude/plans/AIUE-61-omp-static-partition.md, "Validation protocol").
# Usage: AIUE-61-run_protocol.sh OUTDIR PHASE...     phases: g0 g1 ctl g2 g3 g4 g5 g6 g9 g10 g10nc5 g10b
# Shared machine: at most 2 UEDGE processes at a time, at most 4 threads each; 8-thread runs one at a time.
# Preliminary run (AIUE-56 base): every phase except G7/R2/R4/R5. The final run repeats it on the AIUE-60-combined tree.
set -u
OUT=$1; shift
W=/Users/holma/Documents/uedge/src/uedge-wt
V=$W/venvs
NEW=$V/AIUE-61-omp/bin/python          # built from $W/AIUE-61-omp (detached at the product commit)
NEWS=$V/AIUE-61-serial/bin/python      # built from $W/AIUE-61-serial (same commit)
CHK=$V/AIUE-61-chk/bin/python          # OpenMP + --checkbounds
OLD=$V/AIUE-56-omp/bin/python          # the old default (C1-fixed)
HD=$W/AIUE-57/tests/deterministic_omp  # reviewed harness core 8ee189d
H=$HD/harness/cli.py
SC=$W/AIUE-53/tests/deterministic_omp/harness/serial_check.py   # 15ae327
GATE=$W/AIUE-56/docs/reviews/AIUE-56-c1-gate.py                # 1553e75
GF=$W/AIUE-62/tests/deterministic_omp/linux/gate_flows.py
T50=$W/AIUE-50/tests/deterministic_omp/tools
R=$(cd "$(dirname "$0")" && pwd)
L=$R/AIUE-61-launch.sh
FIX='{"OMPJacFixedChunks": 1, "OMPJacNchunksFixed": 64, "OMPJacMinChunkLen": 300}'
FIX1='{"OMPJacFixedChunks": 1, "OMPJacNchunksFixed": 64, "OMPJacMinChunkLen": 1}'
mkdir -p "$OUT"; LOG=$OUT/protocol.log
log() { echo "$(date +%H:%M:%S) $*" >> "$LOG"; }
# chk NAME PY PRESET THREADS REPEATS PPPJSON [extra cli args...]
chk() { local n=$1 py=$2 p=$3 t=$4 k=$5 pp=$6; shift 6
  [ -e "$OUT/$n" ] && { log "$n exists, skipped"; return; }
  $py $H check --preset $p --arm jac --threads $t --repeats $k --python $py --out "$OUT/$n" --ppp "$pp" "$@" \
    > "$OUT/$n.txt" 2>&1; log "$n exit $? :: $(tail -1 "$OUT/$n.txt")"; }
# cmp NAME DIR_A DIR_B   (bitwise comparison of two run directories)
cmp() { $NEW $H compare "$1" "$2" > "$OUT/cmp_$3.txt" 2>&1; log "cmp_$3 exit $? :: $(tail -1 "$OUT/cmp_$3.txt")"; }
# jw NAME PY THREADS PRESET 'json'   (AIUE-61-jworker.py through the launcher)
jw() { "$L" "$2" "$OUT/jw/$1" "$3" "$R/AIUE-61-jworker.py" "$4" jac "$3" "$5" >> "$LOG" 2>&1; }
# jww: as jw, for runs expected to stop on a Fortran runtime error. Such an error in an OpenMP worker leaves the
# process hanging (seen in NC5), so the run is killed 10 s after the message appears (or after 600 s).
jww() { jw "$@" & local p=$! n=0
  while kill -0 $p 2>/dev/null && [ $n -lt 600 ]; do
    grep -aq "Fortran runtime error" "$OUT/jw/$1/run.log" 2>/dev/null && { sleep 10; break; }
    sleep 2; n=$((n+2)); done
  pkill -f "AIUE-61-chk/bin/python -I $R/AIUE-61-jworker.py" 2>/dev/null; wait $p 2>/dev/null
  log "$1 (watched): $(grep -a -m1 -o "Fortran runtime error.*" "$OUT/jw/$1/run.log" 2>/dev/null | head -1)"; }

for PHASE in "$@"; do log "== phase $PHASE"; case $PHASE in
g0)  # G0a, G0b (1 thread each, two at a time)
  "$L" $NEWS "$OUT/g0a" 1 "$R/AIUE-61-state_probe.py" >> "$LOG" 2>&1 &
  "$L" $NEWS "$OUT/g0b" 1 "$R/AIUE-61-shared-full.py" "$T50" "$W/AIUE-61-serial" >> "$LOG" 2>&1 &
  wait ;;
g1)  # defaults unchanged, complete gate (base-* = v9-develop product 0fac655)
  $NEW $SC --base-python $V/base-serial/bin/python --new-python $NEWS --base-omp-python $V/base-omp/bin/python \
    --new-omp-python $NEW --jobs 2 --out "$OUT/g1" > "$OUT/g1.txt" 2>&1; log "g1 exit $? :: $(grep RESULT "$OUT/g1.txt")" ;;
ctl) # controls NC1, NC3, NC4, C-isjr, C-guard (<= 4 threads, two at a time); NC2 alone at 8 threads
  chk nc1_t2 $NEW full 2 2 '{"OMPJacFixedChunks": 1, "OMPJacChunkReset": 0}' &
  chk nc1_t4 $NEW full 4 2 '{"OMPJacFixedChunks": 1, "OMPJacChunkReset": 0}' & wait
  cmp "$OUT/nc1_t2/run0" "$OUT/nc1_t4/run0" nc1_t2_t4
  chk nc3_old $OLD full 4 1 '{"OMPJacNchunks": 16, "OMPAutoBalance": 0}' &
  chk nc3_new $NEW full 4 1 '{"OMPJacFixedChunks": 0, "OMPJacNchunks": 16, "OMPAutoBalance": 0}' & wait
  chk nc4_old_full $OLD full 1 1 '{}' & chk nc4_new_full $NEW full 1 1 '{"OMPJacFixedChunks": 0}' & wait
  chk nc4_old_tebox $OLD tebox 1 1 '{}' & chk nc4_new_tebox $NEW tebox 1 1 '{"OMPJacFixedChunks": 0}' & wait
  cmp "$OUT/nc4_old_full/run0" "$OUT/nc4_new_full/run0" nc4_full
  cmp "$OUT/nc4_old_tebox/run0" "$OUT/nc4_new_tebox/run0" nc4_tebox
  jw isjr_def $NEW 4 full '{"ppp": '"$FIX"'}' & jw isjr_off $NEW 4 full '{"ppp": '"$FIX"', "bbb": {"isjacreset": 0}}' & wait
  jw guard_mcn $NEW 4 full '{"bbb": {"ismcnon": 4}}' & jw guard_imp5 $NEW 4 full '{"bbb": {"isimpon": 5}}' & wait
  chk nc2_t8 $NEW full 8 5 '{"OMPJacFixedChunks": 0}' ;;
g2)  # K=20 determinism, 4 threads
  chk g2_full $NEW full 4 20 "$FIX"
  chk g2_tebox1 $NEW tebox 4 20 "$FIX1" & chk g2_tebox $NEW tebox 4 20 "$FIX" & wait ;;
g3)  # thread identity 1/2/3/4/8, G3-sched, G3-count
  for p in full tebox1 tebox; do
    case $p in full) pr=full; pp=$FIX;; tebox1) pr=tebox; pp=$FIX1;; tebox) pr=tebox; pp=$FIX;; esac
    chk g3_${p}_t1 $NEW $pr 1 3 "$pp" & chk g3_${p}_t2 $NEW $pr 2 3 "$pp" & wait
    chk g3_${p}_t3 $NEW $pr 3 3 "$pp" & wait
    chk g3_${p}_t4 $NEW $pr 4 3 "$pp" & wait
    chk g3_${p}_t8 $NEW $pr 8 3 "$pp"
    for t in 1 2 3 8; do cmp "$OUT/g3_${p}_t$t/run0" "$OUT/g3_${p}_t4/run0" g3_${p}_t${t}_t4; done
  done
  chk g3_sched3 $NEW full 4 1 '{"OMPJacFixedChunks": 1, "OMPJacNchunksFixed": 64, "OMPJacMinChunkLen": 300, "OMPLoopJacNchunk": 3}'
  cmp "$OUT/g3_sched3/run0" "$OUT/g3_full_t4/run0" g3_sched3
  for t in 1 2 4 8; do
    jw cnt_full_t$t $NEW $t full '{"ppp": '"$FIX"'}'; jw cnt_tebox_t$t $NEW $t tebox '{"ppp": '"$FIX"'}'
    jw cnt_tebox1_t$t $NEW $t tebox '{"ppp": '"$FIX1"'}'
  done ;;
g4)  # Newton path, --itermx 3
  chk g4_full_t4 $NEW full 4 5 "$FIX" --itermx 3
  chk g4_tebox1_t4 $NEW tebox 4 5 "$FIX1" --itermx 3 & chk g4_tebox1_t2 $NEW tebox 2 1 "$FIX1" --itermx 3 & wait
  chk g4_full_t2 $NEW full 2 1 "$FIX" --itermx 3
  chk g4_full_t8 $NEW full 8 1 "$FIX" --itermx 3
  chk g4_tebox1_t8 $NEW tebox 8 1 "$FIX1" --itermx 3
  for p in full tebox1; do for t in 2 8; do cmp "$OUT/g4_${p}_t$t/run0" "$OUT/g4_${p}_t4/run0" g4_${p}_t${t}_t4; done; done ;;
g5)  # flow --all, K=2, both arms; cores 8 so an 8-thread run runs alone
  $NEW $H flow --all --repeats 2 --python $NEW --out "$OUT/g5" --ppp "$FIX" --max-jobs 2 --cores 8 --gate none \
    > "$OUT/g5.txt" 2>&1; log "g5 exit $?"
  for c in tebox full te ti ni up ng phi; do for t in 2 8; do
    [ -d "$OUT/g5/$c/jac_t$t/run0" ] && cmp "$OUT/g5/$c/jac_t$t/run0" "$OUT/g5/$c/jac_t4/run0" g5_${c}_t${t}_t4
  done; done ;;
g6)  # AIUE-56 C1 gate on every one-evaluation jac run (G2, G3, G5)
  $NEW $GATE --harness "$HD" "$OUT"/g2_* "$OUT"/g3_*_t[12348] > "$OUT/g6_checks.txt" 2>&1; log "g6 checks exit $?"
  mkdir -p "$OUT/g6_links"
  $NEW $GF $GATE "$OUT/g6_links" "$HD" g5="$OUT/g5" > "$OUT/g6_flow.txt" 2>&1; log "g6 flow exit $?" ;;
g9)  # G9b (D_only default case), G9a's OpenMP check is run by hand (validate skill)
  CASE=/Users/holma/Documents/uedge/src/uedge-pytests/pytests/unittests/D_only/nonog/default
  pyrun() { local n=$1 py=$2 arm=$3 t=$4 pp=$5; mkdir -p "$OUT/g9b/$n/home"; cp -R "$CASE"/. "$OUT/g9b/$n/";
    (cd "$OUT/g9b/$n" && env -i PATH=/usr/bin:/bin HOME="$OUT/g9b/$n/home" OMP_NUM_THREADS=$t OMP_STACKSIZE=512M \
      $py -I "$R/AIUE-61-pytests_omp.py" run $arm $t "$pp" > run.log 2>&1); log "g9b $n exit $?"; }
  pyrun serial $NEW serial 1 '{}'
  for k in 0 1 2; do pyrun def_t4_$k $NEW jac 4 '{"ppp": '"$FIX"'}' & pyrun min1_t4_$k $NEW jac 4 '{"ppp": '"$FIX1"'}' & wait; done
  pyrun def_t2 $NEW jac 2 '{"ppp": '"$FIX"'}' & pyrun min1_t2 $NEW jac 2 '{"ppp": '"$FIX1"'}' & wait
  (cd "$OUT/g9b" && $NEW -I "$R/AIUE-61-pytests_omp.py" compare serial def_t4_0 def_t4_1 def_t4_2 def_t2 \
     min1_t4_0 min1_t4_1 min1_t4_2 min1_t2) > "$OUT/g9b.txt" 2>&1; log "g9b compare exit $? :: $(tail -1 "$OUT/g9b.txt")" ;;
g10) # bounds (checkbounds build) and the default OMP_STACKSIZE
  python3 "$R/AIUE-61-gate10_static.py" "$W/AIUE-61-omp/ppp/omp_parallel.F90" > "$OUT/g10_static.txt" 2>&1
  log "g10 static exit $?"
  jw chk_tebox_t4 $CHK 4 tebox '{"ppp": '"$FIX"'}'
  for k in 1 2 3 4 5; do jw chk_tebox12_t8_$k $CHK 8 tebox '{"ppp": {"OMPJacFixedChunks": 1, "OMPJacNchunksFixed": 64, "OMPJacMinChunkLen": 12}}'; done
  for k in 1 2 3 4 5; do jw chk_full2_t8_$k $CHK 8 full '{"ppp": {"OMPJacFixedChunks": 1, "OMPJacNchunksFixed": 2, "OMPJacMinChunkLen": 300}}'; done
  ;;
g10nc5) # NC5 (legacy out-of-bounds on the checkbounds build; watched, because the runtime error hangs the process)
  for k in 1 2 3 4 5; do [ -e "$OUT/jw/nc5_$k/jrun.json" ] || [ -e "$OUT/jw/nc5_${k}.done" ] && continue
    jww nc5_$k $CHK 4 tebox '{"ppp": {"OMPJacFixedChunks": 0, "OMPJacNchunks": 2}}'; touch "$OUT/jw/nc5_${k}.done"; done
  ;;
g10b) # the default OMP_STACKSIZE (variable not set), new and old build
  for t in 4 8; do
    AIUE61_NOSTACK=1 jw nostack_new_t$t $NEW $t full '{"ppp": '"$FIX"'}'
    AIUE61_NOSTACK=1 jw nostack_old_t$t $OLD $t full '{}'
  done ;;
esac; done
log "done: $*"
