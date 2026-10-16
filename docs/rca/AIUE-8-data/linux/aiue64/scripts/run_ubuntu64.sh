#!/bin/bash
# AIUE-64 Ubuntu 24.04 driver: L1-L5. Usage: run_ubuntu64.sh FIXCOMMIT
set -u
BASE=$(git -C /mnt/repo rev-parse 4faed39); FIX=$(git -C /mnt/repo rev-parse "$1")
echo "BASE $BASE FIX $FIX"; nproc; free -g | awk '/Mem:/ {print $2 " GB RAM"}'
/scripts/clone_harness.sh 8ee189d76b0232cedfe17088574935b10b857df5
# L1 + L2: default OpenMP build, no LDFLAGS
env -u LDFLAGS /scripts/build_uedge.sh base "$BASE"
env -u LDFLAGS /scripts/build_uedge.sh fix "$FIX"
{ /scripts/import_check.sh base fix; gcc --version | head -1
  echo "gcc -dumpspecs as-needed occurrences: $(gcc -dumpspecs | grep -c as-needed)"; } > /out/import.txt 2>&1
/scripts/link_record.sh base; /scripts/link_record.sh fix
# L3: BASE with the AIUE-62 workaround
env LDFLAGS=-fopenmp /scripts/build_uedge.sh wkld "$BASE"
/scripts/link_record.sh wkld
# L4: serial builds
env -u LDFLAGS /scripts/build_uedge.sh base-ser "$BASE" serial
env -u LDFLAGS /scripts/build_uedge.sh fix-ser "$FIX" serial
/scripts/import_check.sh wkld base-ser fix-ser > /out/import_other.txt 2>&1
/scripts/link_record.sh base-ser; /scripts/link_record.sh fix-ser
# L5: AIUE-57 "Unit tests, smoke test and OpenMP test flow" step on the fix build (reduced flow set)
echo "== L5 CI replay start $(date -u +%FT%TZ)"
( cd /work && echo "nproc $(nproc); $(free -g | awk '/Mem:/ {print $2}') GB RAM" && \
  OMP_CI_OUT=/out/ci OMP_CI_CORES=4 OMP_CI_MAX_JOBS=1 OMP_CI_GATE=none \
  OMP_CI_FLOWS="tebox1|tebox|2,4|2|jac|none" PYTHON=/work/venv-fix/bin/python \
  bash /work/harness/tests/deterministic_omp/ci/run_omp_ci.sh pr ) > /out/ci_step.log 2>&1
echo "CI step exit $?" | tee -a /out/ci_step.log
# L5 thread probe
mkdir -p /tmp/hp
( cd /tmp && env HOME=/tmp/hp OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=2 \
  UEDGE_OMP_RATES_DIR=/work/harness/builder/test/Forthon_cases/Forthon_case5 \
  /work/venv-fix/bin/python -I /scripts/thread_probe.py /work/probe ) > /out/thread_probe_full.log 2>&1
echo "probe exit $?" >> /out/thread_probe_full.log
grep -E '^(threads|n0|n1|OMPParallelJac|libgomp|RESULT|probe exit)' /out/thread_probe_full.log > /out/thread_probe.txt
echo ALLDONE
