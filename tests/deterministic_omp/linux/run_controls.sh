#!/bin/bash
# AIUE-62 control experiments on the AIUE-56 build (amd64):
#  fixtp : areapl made +threadprivate (bbb/bbb.v), the AIUE-60 F16 remedy -> are the 8-thread up-row mismatches the areapl race?
#  fixfma: -mfma added to FARGSOPT -> does FMA contraction bring the C2/M2 residual back on x86-64?
export LDFLAGS=-fopenmp
F=1553e756539bb4e66b2241b840fc697e23101a36
/scripts/build_uedge_sed.sh fixtp $F bbb/bbb.v 's|^(areapl +real +/0\./ +\+work)|\1 +threadprivate|'
/scripts/build_uedge_sed.sh fixfma $F setup.py "s/'FARGSOPT': \['-O3'\],/'FARGSOPT': ['-O3', '-mfma'],/"
/scripts/fma_scan.sh fixfma > /out/fma_fixfma.txt 2>&1
C="--cores 5 --max-jobs 1 --gate none"
/scripts/run_flow.sh fixld t8_up_full_k5 --configs up,full --threads 8 --repeats 5 $C
/scripts/run_flow.sh fixtp t8_up_full_k5 --configs up,full --threads 8 --repeats 5 $C
/scripts/run_flow.sh fixfma k20_tebox --configs tebox --threads 4 --repeats 20 $C
/scripts/run_flow.sh fixfma k5_full --configs full --threads 4 --repeats 5 --arms jac $C
echo CONTROLSDONE >> /out/flows.log
