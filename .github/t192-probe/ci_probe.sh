#!/bin/bash
# T192 CI probe (temporary; removed before review): one leg of .github/workflows/t192-probe.yml, from the repo root.
# Usage: ci_probe.sh LEG  (pad0..pad3: d_mols, an env pad of 8-byte steps over 2048 bytes each; padall: all 14 entries,
# pads 0..8192 in 128-byte steps; plain: all 14 x 50 plain, nohook 20, PYTHONHASHSEED 0-9 x 3; pytest: the CI test
# command itself, repeated). Results in t192-results/ (uploaded as an artifact). Never fails the job on a probe result.
set -u
P=.github/t192-probe
OUT=t192-results
mkdir -p "$OUT"
python3 $P/inventory.py --json | python3 -c "import json,sys;print(' '.join(r['family']+':'+r['id'] for r in json.load(sys.stdin)))" > "$OUT/entries.txt"
read -r -a ALL < "$OUT/entries.txt"
O="$OUT/$1.jsonl"
run() {  # TAG N ENTRY... [-- repeat.py args]
  local tag=$1 n=$2
  shift 2
  python $P/repeat.py --out "$O" --cache "$OUT/cache" --n "$n" --tag "$tag" "$@" 2>&1 \
    | grep --line-buffered -E '"family"|Error|Traceback|assert' | cut -c1-260
}
echo "env bytes of this step: $(python3 -c 'import os; print(sum(len(k)+len(v)+2 for k, v in os.environ.items()))')"
case "$1" in
  pad[0-3])
    k=${1#pad}
    for L in $(seq $((k * 2048)) 8 $((k * 2048 + 2040))); do
      T192_PAD=$(head -c "$L" /dev/zero | tr '\0' x) run "pad$L" 1 d_mols:set:plate-mol-zerograd
    done ;;
  padall)
    for L in $(seq 0 128 8192); do T192_PAD=$(head -c "$L" /dev/zero | tr '\0' x) run "pad$L" 1 "${ALL[@]}"; done ;;
  plain)
    run plain 50 "${ALL[@]}"
    run nohook 20 --no-hook "${ALL[@]}"
    for s in 0 1 2 3 4 5 6 7 8 9; do PYTHONHASHSEED=$s run "hashseed$s" 3 "${ALL[@]}"; done ;;
  smoke)
    run smoke 1 "${ALL[@]}" ;;
  pytest)
    for i in $(seq 1 15); do
      python -m pytest tests/yldot -n auto -m "not nightly" --yldot-shard d_mols -k "test_invalid" --timeout 900 \
        -p no:cacheprovider -q 2>&1 | grep -E "passed|failed|FAILED" | sed "s/^/invalid-only $i: /" | tee -a "$OUT/pytest.txt"
    done
    for i in 1 2 3; do
      python -m pytest tests/yldot -n auto -m "not nightly" --yldot-shard d_mols --timeout 900 \
        -p no:cacheprovider -q 2>&1 | grep -E "passed|failed|FAILED" | sed "s/^/full-shard $i: /" | tee -a "$OUT/pytest.txt"
    done ;;
esac
python3 $P/summarize.py "$O" 2>/dev/null | tee "$OUT/$1.summary.txt" || true
exit 0
