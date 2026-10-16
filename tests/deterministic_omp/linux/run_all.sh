#!/bin/bash
# AIUE-62 run order: K=20 Te box, K=20 full (jac), then --all K=2; fixed build first in each step.
C="--cores 5 --max-jobs 1 --gate none"
for b in fixld baseld; do /scripts/run_flow.sh $b k20_tebox --configs tebox --threads 4 --repeats 20 $C; done
for b in fixld baseld; do /scripts/run_flow.sh $b k20_full --configs full --threads 4 --repeats 20 --arms jac $C; done
for b in fixld baseld; do /scripts/run_flow.sh $b k2_all --all --repeats 2 $C; done
echo ALLDONE >> /out/flows.log
