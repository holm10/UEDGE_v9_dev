#!/bin/bash
# AIUE-61 G9a: upstream pytests D_only, one process per test file (pytest-isolate is not installed in the venvs),
# with a given build (decks' default switches). Writes OUT/<name>.txt: one line "<test file> <pytest summary>".
# Usage: AIUE-61-donly.sh OUTDIR NAME PYTHON
OUT=$1; NAME=$2; PY=$3
P=/Users/holma/Documents/uedge/src/uedge-pytests
mkdir -p "$OUT/home_$NAME"; : > "$OUT/$NAME.txt"
for f in $(cd $P && ls pytests/unittests/D_only/nonog/*/test_*.py); do
  s=$(cd $P && env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 HOME="$OUT/home_$NAME" OMP_NUM_THREADS=1 OMP_STACKSIZE=512M \
      $PY -m pytest -q -p no:cacheprovider "$f" 2>&1 | tr -d '\000' | grep -a -E "passed|failed|error" | tail -1)
  echo "$f ${s:-NO-SUMMARY}" >> "$OUT/$NAME.txt"
done
