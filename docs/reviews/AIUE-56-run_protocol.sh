#!/bin/zsh
# AIUE-56 validation protocol (plan: testing strategy 3-6, acceptance gates), reviewed core at AIUE-49 HEAD.
OUT=/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/v56
V=/Users/holma/Documents/uedge/src/uedge-wt/venvs
NEW=$V/AIUE-56-omp/bin/python
BASE=$V/base-omp/bin/python
H=/Users/holma/Documents/uedge/src/uedge-wt/AIUE-49/tests/deterministic_omp/harness/cli.py
chk() { # name python preset arm threads repeats [extra...]
  local name=$1 py=$2 preset=$3 arm=$4 th=$5 k=$6; shift 6
  $py $H check --preset $preset --arm $arm --threads $th --repeats $k --python $py --out $OUT/$name "$@" > $OUT/$name.txt 2>&1
  echo "$name exit $? :: $(tail -1 $OUT/$name.txt)" >> $OUT/protocol.log
}
lane1() {
  chk new_tebox_t4_k30 $NEW tebox jac 4 30
  chk new_full_t4_k30 $NEW full jac 4 30
}
lane2() {
  chk new_tebox_t2_k5 $NEW tebox jac 2 5
  chk new_tebox_t8_k5 $NEW tebox jac 8 5
  chk new_full_t2_k5 $NEW full jac 2 5
  chk new_full_t8_k5 $NEW full jac 8 5
  chk new_tebox_t4_it3_k5 $NEW tebox jac 4 5 --itermx 3
  chk new_full_t4_it3_k5 $NEW full jac 4 5 --itermx 3
}
lane3() {
  for p in te ti ni up ng te_phi; do chk new_${p}_t4_k5 $NEW $p jac 4 5; done
  for p in tebox full te te_phi ti ni up ng; do chk base_${p}_t4_k3 $BASE $p jac 4 3; done
  chk new_tebox_rhs_t4_k5 $NEW tebox jacrhs 4 5
  chk new_full_rhs_t4_k5 $NEW full jacrhs 4 5
}
echo "start $(date)" >> $OUT/protocol.log
lane1 & lane2 & lane3 & wait
echo "end $(date)" >> $OUT/protocol.log
