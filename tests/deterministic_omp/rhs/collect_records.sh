#!/bin/bash
# AIUE-58: copy the small records of the RHS RCA runs from the working folder into docs/rca/AIUE-8-data/rhs/
# and write the summaries. Arrays (record.npz, seq.npz) and the case copies stay in the working folder.
#   collect_records.sh <working folder> <repo worktree>
set -e
W=$1; REPO=$2
D=$REPO/docs/rca/AIUE-8-data/rhs
HERE=$(cd "$(dirname "$0")" && pwd)
PY=${PY:-python3}
mkdir -p "$D/probe" "$D/seq" "$D/harness" "$D/lldb"
for r in "$W"/probe/*/; do
  n=$(basename "$r"); [ -f "$r/probe.json" ] || continue
  case $n in *_err) continue;; esac
  mkdir -p "$D/probe/$n"; cp "$r"/{probe.json,spec.json,status.txt} "$D/probe/$n/" 2>/dev/null || true
done
for r in "$W"/probe/carrier_*/; do n=$(basename "$r"); mkdir -p "$D/probe/$n"; cp "$r"/{carrier.json,spec.json,status.txt} "$D/probe/$n/"; done
{ for r in "$D"/probe/*/; do [ -f "$r/probe.json" ] || continue; echo "=== $(basename "$r")  ($(cat "$r/status.txt"))"; $PY "$HERE/probe_show.py" "$r"; done; } > "$D/probe_summary.txt"
for r in "$W"/seq/*/; do
  n=$(basename "$r"); case $n in lldb*) continue;; esac
  mkdir -p "$D/seq/$n"; cp "$r"/{spec.json,status.txt} "$D/seq/$n/"; [ -f "$r/seq.json" ] && cp "$r/seq.json" "$D/seq/$n/"
  tr -d '\000' < "$r/run.log" | grep -a 'iter=\|Updating\|storage\|nnz=' > "$D/seq/$n/nksol.log" || true
done
for f in "$W"/re_*.txt "$W"/it5_*.txt "$W"/hcyn_*.txt; do
  n=$(basename "$f" .txt); mkdir -p "$D/harness/$n"; cp "$f" "$D/harness/$n/check.txt"
  [ -f "$W/$n/check.json" ] && cp "$W/$n/check.json" "$D/harness/$n/"
  [ -f "$W/$n/record.json" ] && cp "$W/$n/record.json" "$D/harness/$n/record.json"
  for r in "$W/$n"/*/; do [ -f "$r/record.json" ] && cp "$r/record.json" "$D/harness/$n/$(basename "$r").json"; done
done
cp "$W"/cmp_*.txt "$D/harness/" 2>/dev/null || true
for l in "$W"/seq/lldb_*/; do
  n=$(basename "$l"); tr -d '\000' < "$l/lldb.log" | grep -a -v '^\s*$' | awk '/iter=|storage|nnz=|stop reason|frame #|thread #/' | head -120 > "$D/lldb/$n.txt"
done
cp "$W"/*.log "$D/" 2>/dev/null || true
