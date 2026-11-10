#!/bin/bash
# Line and branch coverage of bbb/pandf*.F under the yldot suite (epic AIUE-9, PRD section 7.10; AIUE-107).
#
# Usage (from anywhere; the python on PATH, or $PYTHON, must hold a coverage build of this checkout:
#        pip install . -C "--build-option=--coverage", and gcovr: pip install gcovr):
#   coverage.sh new OUTDIR [--jobs N] [-- PYTEST ARGS]   the PR tier, then the nightly tier (or only PYTEST ARGS)
#   coverage.sh report OUTDIR [--base FILE]              coverage_compare.py on OUTDIR/new.json [against another
#                                                        run's new.json, e.g. before a change: its branches "old"]
#
# A run deletes the build's .gcda files, runs the suite, writes OUTDIR/new.json (gcovr --json, filtered to
# bbb/pandf*.F), OUTDIR/new.txt and OUTDIR/new.meta (commit, build record, CPU, wall time, pass/fail counts), and
# deletes the .gcda files again. Facts it relies on (AIUE-105, AIUE-107 probes, macOS arm64, gcov 15):
#   - the yldot harness's children keep their counts only when started by spawn (forkserver children leave none), so
#     YLDOT_START_METHOD=spawn is exported;
#   - processes running at once merge their counts into the same .gcda files exactly, so pytest -n is safe;
#   - no pytest --timeout (owner, 2026-11-10, D4): -O0 --coverage runs 2.3-2.8x slower than -O3; a test killed early
#     would under-report. The harness's own child timeouts (family.toml timeout_s) are unchanged; a child it kills
#     writes no counts, so the run lists the tests whose JUnit record has a "no result after" message and a nonzero
#     count is reported as a failure.
# Exit codes: 0 done (test failures are recorded in the .meta, not fatal), 1 a check failed (no counts written, a
# harness timeout), 2 usage or a refused setup.
set -uo pipefail

usage() { sed -n '2,9p' "$0" >&2; exit 2; }
die() { echo "coverage.sh: $*" >&2; exit 2; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$(cd "$HERE/../../.." && pwd)"
PY="${PYTHON:-python}"

[ $# -ge 2 ] || usage
MODE="$1"; OUT="$2"; shift 2
JOBS=1; BASE=""; EXTRA=()
while [ $# -gt 0 ]; do
  case "$1" in
    --jobs) JOBS="$2"; shift 2 ;;
    --base) BASE="$2"; shift 2 ;;
    --) shift; EXTRA=("$@"); break ;;
    *) usage ;;
  esac
done
case "$MODE" in new|report) ;; *) usage ;; esac
mkdir -p "$OUT" || die "cannot create $OUT"
OUT="$(cd "$OUT" && pwd)"

if [ "$MODE" = report ]; then
  [ -f "$OUT/new.json" ] || die "$OUT/new.json missing (run: coverage.sh new $OUT)"
  args=(--src "$SRC" "$OUT/new.json" --out "$OUT")
  if [ -n "$BASE" ]; then
    [ -f "$BASE" ] || die "--base $BASE: no such file"
    args+=(--old "$BASE")
  fi
  "$PY" -I "$HERE/coverage_compare.py" "${args[@]}"
  exit $?
fi

# --- the build: a coverage build installed for $PY, its objects under this checkout ---
RECORD="$("$PY" -I -c 'import importlib.util, pathlib
s = importlib.util.find_spec("uedge")
print(pathlib.Path(s.origin).parent / "_build_info.json" if s else "")' 2>/dev/null)"
[ -n "$RECORD" ] && [ -f "$RECORD" ] || die "$PY has no uedge with a build record (_build_info.json)"
"$PY" -I -c 'import json, sys
r = json.load(open(sys.argv[1]))
sys.exit(0 if "--coverage" in (r.get("fargs") or "").split() else 1)' "$RECORD" \
  || die "the uedge of $PY is not a coverage build ($RECORD); build with -C \"--build-option=--coverage\""
OBJS=()
for d in "$SRC"/build/temp.*; do [ -f "$d/pandf.gcno" ] && OBJS+=("$d"); done
[ ${#OBJS[@]} -eq 1 ] || die "need exactly one build/temp.*/ with pandf.gcno under $SRC, found ${#OBJS[@]}"
OBJ="${OBJS[0]}"
if [ -n "${GCOV:-}" ]; then
  GC="$GCOV"
else
  major="$(gfortran -dumpversion 2>/dev/null | cut -d. -f1)"
  GC="gcov"
  [ -n "$major" ] && command -v "gcov-$major" >/dev/null && GC="gcov-$major"
fi
"$GC" --version 2>/dev/null | head -1 | grep -q GCC || die "$GC is not GCC's gcov (set GCOV, e.g. GCOV=gcov-15)"
"$PY" -I -m gcovr --version >/dev/null 2>&1 || die "gcovr is not installed for $PY (pip install gcovr)"
[ -f "$HOME/.uedgerc.py" ] && echo "coverage.sh: warning: $HOME/.uedgerc.py exists and runs on import uedge" >&2

clean() { find "$OBJ" -name '*.gcda' -delete; }
cpu() { sysctl -n machdep.cpu.brand_string 2>/dev/null || grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2; }
junit_counts() {  # tests failures errors skipped over the given JUnit XML files
  "$PY" -I -c 'import sys, xml.etree.ElementTree as ET
t = [0, 0, 0, 0]
for p in sys.argv[1:]:
    try:
        root = ET.parse(p).getroot()
    except Exception:
        continue
    for s in ([root] if root.tag == "testsuite" else root.iter("testsuite")):
        for i, k in enumerate(("tests", "failures", "errors", "skipped")):
            t[i] += int(s.get(k, 0))
print("tests {} failures {} errors {} skipped {}".format(*t))' "$@"
}
timed_out() {  # the test cases whose JUnit record holds a harness "no result after" (a killed child), one per line
  "$PY" -I -c 'import sys, xml.etree.ElementTree as ET
for p in sys.argv[1:]:
    try:
        root = ET.parse(p).getroot()
    except Exception:
        continue
    for tc in root.iter("testcase"):
        if "no result after" in ET.tostring(tc, encoding="unicode"):
            print("{}::{}".format(tc.get("classname"), tc.get("name")))' "$@"
}
finish() {  # $1 suite name, $2 wall seconds, rest: lines for the .meta
  local suite="$1" wall="$2"; shift 2
  local n
  n="$(find "$OBJ" -name 'pandf*.gcda' | wc -l | tr -d ' ')"
  {
    echo "suite: $suite"
    echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "commit: $(git -C "$SRC" rev-parse --short HEAD) dirty: $(git -C "$SRC" status --porcelain --untracked-files=no | wc -l | tr -d ' ')"
    echo "build record: $(tr -d '\n' < "$RECORD")"
    echo "cpu: $(cpu | sed 's/^ *//')"
    echo "gcov: $("$GC" --version | head -1)"
    echo "wall_s: $wall"
    echo "pandf_gcda_files: $n"
    printf '%s\n' "$@"
  } > "$OUT/$suite.meta"
  if [ "$n" -eq 0 ]; then
    echo "coverage.sh: no pandf .gcda written: the run left no counts (forkserver children? another build?)" >&2
    exit 1
  fi
  (cd "$SRC" && "$PY" -I -m gcovr --gcov-executable "$GC" --root "$SRC" --object-directory "$OBJ" \
      --gcov-suspicious-hits-threshold 0 --filter 'bbb/pandf.*\.F$' --json "$OUT/$suite.json" --txt "$OUT/$suite.txt" --txt-summary) \
    > "$OUT/$suite.gcovr.log" 2>&1 || { cat "$OUT/$suite.gcovr.log" >&2; exit 1; }
  tail -4 "$OUT/$suite.gcovr.log"
  clean
  cat "$OUT/$suite.meta" | grep -v '^build record'
}

export YLDOT_START_METHOD=spawn
clean
start=$SECONDS

# MODE = new: the yldot suite
cd "$SRC" || die "cannot cd to $SRC"
par=()
[ "$JOBS" -gt 1 ] && par=(-n "$JOBS" --dist worksteal)
common=(-p no:cacheprovider -rf --tb=short --durations=0)
status=()
if [ ${#EXTRA[@]} -gt 0 ]; then
  "$PY" -m pytest ${par[@]+"${par[@]}"} "${common[@]}" --junitxml "$OUT/new-custom.xml" "${EXTRA[@]}" > "$OUT/new-custom.log" 2>&1
  status+=("pytest custom (${EXTRA[*]}): exit $?")
  tail -3 "$OUT/new-custom.log"
else
  for tier in pr nightly; do
    [ $tier = pr ] && sel="not nightly" || sel="nightly"
    t0=$SECONDS
    "$PY" -m pytest tests/yldot ${par[@]+"${par[@]}"} "${common[@]}" -m "$sel" --junitxml "$OUT/new-$tier.xml" \
      > "$OUT/new-$tier.log" 2>&1
    status+=("pytest $tier tier: exit $? in $((SECONDS - t0)) s")
    tail -3 "$OUT/new-$tier.log"
  done
fi
killed="$(timed_out "$OUT"/new-*.xml)"
timeouts="$(printf '%s' "$killed" | grep -c .)"
finish new $((SECONDS - start)) "${status[@]}" "junit: $(junit_counts "$OUT"/new-*.xml)" \
  "harness_timeouts: $timeouts${killed:+ ($(printf '%s' "$killed" | tr '\n' ' '))}"
if [ "$timeouts" -ne 0 ]; then
  echo "coverage.sh: $timeouts test(s) with a harness timeout (children killed, so they wrote no counts):" >&2
  printf '%s\n' "$killed" >&2
  exit 1
fi
exit 0
