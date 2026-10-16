#!/bin/bash
# run_flow.sh BUILD NAME [flow args...] : one AIUE-52 flow with the reviewed harness (/work/harness) on
# /work/venv-BUILD, output /out/BUILD/NAME; the command line and timing go to /out/flows.log
set -u
B=$1; N=$2; shift 2
PY=/work/venv-$B/bin/python
H=/work/harness/tests/deterministic_omp/harness/cli.py
mkdir -p /out/$B
echo "$(date -u +%FT%TZ) START $B $N: $PY -I $H flow $* --python $PY --out /out/$B/$N" >> /out/flows.log
t0=$(date +%s)
"$PY" -I "$H" flow "$@" --python "$PY" --out "/out/$B/$N" > "/out/$B/$N.stdout" 2>&1
rc=$?
echo "$(date -u +%FT%TZ) END $B $N exit $rc $(( $(date +%s) - t0 )) s" >> /out/flows.log
