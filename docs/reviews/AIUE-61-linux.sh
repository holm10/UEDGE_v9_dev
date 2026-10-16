#!/bin/bash
# AIUE-61 R5: Linux x86-64 (libgomp) in AIUE-62's Debian image aiue62:amd64 (emulated on macOS arm64 by Rosetta),
# run inside the container. The OpenMP build uses LDFLAGS=-fopenmp (AIUE-64 not on this branch).
# Host side (one container at a time, --cpus 5):
#   docker run -d --name aiue61-amd64 --platform linux/amd64 --cpus 5 --memory 7g -v <main repo>:/mnt/repo:ro \
#     -v <out>:/out -v <AIUE-62>/tests/deterministic_omp/linux:/scripts:ro -v <AIUE-61>/docs/reviews:/a61:ro \
#     aiue62:amd64 sleep infinity
#   docker exec aiue61-amd64 /a61/AIUE-61-linux.sh ; docker stop aiue61-amd64 ; docker rm aiue61-amd64
set -u
A61=b717734f6f508be43a0d20a16e459affd7a3cfc3   # bugfix/v9-AIUE-61-omp-static-partition, combined with AIUE-60 f8db593
/scripts/clone_harness.sh 8ee189d76b0232cedfe17088574935b10b857df5
LDFLAGS=-fopenmp /scripts/build_uedge.sh a61 $A61
FIX='{"OMPJacFixedChunks": 1, "OMPJacNchunksFixed": 64, "OMPJacMinChunkLen": 300}'
FIX1='{"OMPJacFixedChunks": 1, "OMPJacNchunksFixed": 64, "OMPJacMinChunkLen": 1}'
C="--cores 5 --max-jobs 1 --gate none --arms jac"
/scripts/run_flow.sh a61 k5_tebox1 --configs tebox --threads 4 --repeats 5 --ppp "$FIX1" $C
/scripts/run_flow.sh a61 k5_full --configs full --threads 4 --repeats 5 --ppp "$FIX" $C
/scripts/run_flow.sh a61 k2_full_t28 --configs full --threads 2,8 --repeats 2 --ppp "$FIX" $C
/scripts/run_flow.sh a61 k5_up --configs up --threads 4,8 --repeats 5 --ppp "$FIX" $C
PY=/work/venv-a61/bin/python; H=/work/harness/tests/deterministic_omp/harness/cli.py; O=/out/a61
cmpr() { $PY -I $H compare "$1" "$2" > "$O/cmp_$3.txt" 2>&1; echo "cmp_$3 exit $?" >> /out/flows.log; }
cmpr $O/k2_full_t28/full/jac_t2/run0 $O/k5_full/full/jac_t4/run0 full_t2_t4
cmpr $O/k2_full_t28/full/jac_t8/run0 $O/k5_full/full/jac_t4/run0 full_t8_t4
cmpr $O/k5_up/up/jac_t8/run0 $O/k5_up/up/jac_t4/run0 up_t8_t4
echo ALLDONE >> /out/flows.log
