#!/usr/bin/env bash
# OpenMP determinism CI steps (AIUE-57): the same steps locally and in .github/workflows/build-test-omp.yml.
#
#   tests/deterministic_omp/ci/run_omp_ci.sh [pr|nightly]
#
# Expects an installed OpenMP build of UEDGE (`pip install -v .`) in $PYTHON (default: python).
# Steps: harness unit tests, import smoke test, then the AIUE-52 test flow (`harness/cli.py flow`)
# for the selected set, then ci/report.py (combined summary, first mismatch per failing group).
#
# Sets (each entry is one flow: name|configurations|threads|repeats K|arms|itermx):
#   pr       tebox1: tebox at 2,4 threads K=3, Jacobian arm, ONE EVALUATION (no --itermx): its
#                    post-exmain Jacobian is in natural order, so the first mismatch is the defect cell;
#            tebox:  tebox at 2,4 threads K=5, both arms, --itermx 3 (the Newton path);
#            full:   full at 2,4 threads K=2, Jacobian arm only, --itermx 3 (the RHS arm is report-only, so
#                    the PR set skips its costly full-problem runs). Every flow is gated the same way.
#   nightly  all1: every configuration (--all: threads 2,4,8) K=2, both arms, one evaluation;
#            all:  every configuration K=3, both arms, --itermx 3
#
# Environment (all optional):
#   PYTHON                 interpreter of the build under test (default: python)
#   OMP_CI_OUT             new output directory (default: ./omp-ci-out); must not exist
#   OMP_CI_CORES           core budget for concurrent runs (default: all cores)
#   OMP_CI_MAX_JOBS        at most this many runs at a time (default: OMP_CI_CORES)
#   OMP_CI_GATE            arm(s) that set the exit code: jac (default), jacrhs, all, none
#   OMP_CI_ITERMX          Newton iterations for flows whose itermx field is empty (default 3; set but
#                          empty: one evaluation)
#   OMP_CI_FLOWS           custom flows instead of the set, "name|configs|threads|K|arms|itermx;..." (configs
#                          ALL: --all; empty threads: the flow default; empty arms: jac,jacrhs; itermx none:
#                          one evaluation, empty: OMP_CI_ITERMX)
#   OMP_CI_SKIP_UNIT_TESTS 1 skips the harness unit tests
#   OMP_CI_JAC_TOLERANCE   THE GATE-MODE SWITCH (decision 9). Empty (default): the Jacobian arm gates
#                          bitwise. Non-empty: passed to the flow as `--jac-tolerance VALUE`. The harness
#                          has no such option yet; until it does, setting this stops with exit 2.
#
# Exit code: 0 the gated arm agrees bitwise with serial and between repeats; 1 a gated mismatch;
# 2 harness or setup error (unit tests, smoke test, unsupported switch, a failed serial reference).
set -u

SET=${1:-pr}
PY=${PYTHON:-python}
HERE=$(cd "$(dirname "$0")" && pwd)
OMPDIR=$(dirname "$HERE")
CLI=$OMPDIR/harness/cli.py
OUT=${OMP_CI_OUT:-$PWD/omp-ci-out}
if [ -z "${OMP_CI_CORES:-}" ]; then
    OMP_CI_CORES=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 2)
fi
CORES=$OMP_CI_CORES
MAXJOBS=${OMP_CI_MAX_JOBS:-$CORES}
GATE=${OMP_CI_GATE:-jac}
ITERMX=${OMP_CI_ITERMX-3}
TOL=${OMP_CI_JAC_TOLERANCE:-}

case "$SET" in
    pr)      FLOWS="tebox1|tebox|2,4|3|jac|none;tebox|tebox|2,4|5|jac,jacrhs|3;full|full|2,4|2|jac|3" ;;
    nightly) FLOWS="all1|ALL||2|jac,jacrhs|none;all|ALL||3|jac,jacrhs|3" ;;
    *)       echo "run_omp_ci.sh: unknown set '$SET' (pr, nightly)"; exit 2 ;;
esac
if [ -n "${OMP_CI_FLOWS:-}" ]; then
    FLOWS=$OMP_CI_FLOWS
    SET=custom
fi

if [ -e "$OUT" ]; then
    echo "run_omp_ci.sh: output directory $OUT exists; remove it or set OMP_CI_OUT"
    exit 2
fi
mkdir -p "$OUT" || exit 2
OUT=$(cd "$OUT" && pwd)
exec > >(tee -a "$OUT/ci.log") 2>&1

START=$(date +%s)
echo "== OpenMP CI: set $SET, gate $GATE, cores $CORES, max jobs $MAXJOBS, itermx $ITERMX, python $PY"
echo "== flows: $FLOWS"

# 1. harness unit tests (no UEDGE build needed)
if [ "${OMP_CI_SKIP_UNIT_TESTS:-0}" != 1 ]; then
    echo "== harness unit tests"
    if ! "$PY" -m pytest -q -p no:cacheprovider "$OMPDIR/harness" "$OMPDIR/ci"; then
        echo "run_omp_ci.sh: harness unit tests failed (exit 2)"
        exit 2
    fi
fi

# 2. smoke test: import in an empty HOME, isolated mode (no ~/.uedgerc.py, no PYTHON* variables)
echo "== smoke test"
SMOKE=$OUT/smoke
mkdir -p "$SMOKE/home"
if ! (cd "$SMOKE" && HOME="$SMOKE/home" OMP_NUM_THREADS=1 "$PY" -I -c \
        "import uedge; from uedge import bbb, ppp; print('uedge_ver', bbb.uedge_ver, 'OMPParallelJac', ppp.OMPParallelJac)"); then
    echo "run_omp_ci.sh: smoke test failed (exit 2)"
    exit 2
fi

# 3. gate mode (decision 9): bitwise unless OMP_CI_JAC_TOLERANCE is set and the harness supports it
TOLARGS=()
GATEMODE=bitwise
if [ -n "$TOL" ]; then
    if ! "$PY" -I "$CLI" flow --help | grep -q -- "--jac-tolerance"; then
        echo "run_omp_ci.sh: OMP_CI_JAC_TOLERANCE=$TOL is set, but harness/cli.py flow has no --jac-tolerance"
        echo "               option yet (decision 9; see tests/deterministic_omp/README.md, CI section) (exit 2)"
        exit 2
    fi
    TOLARGS=(--jac-tolerance "$TOL")
    GATEMODE="tolerance $TOL"
fi

# 4. the flows
DIRS=()
CODES=""
IFS=';' read -r -a FLOWLIST <<< "$FLOWS"
for spec in "${FLOWLIST[@]}"; do
    IFS='|' read -r name configs threads repeats arms itermx <<< "$spec"
    args=(flow --repeats "$repeats" --arms "${arms:-jac,jacrhs}" --gate "$GATE" --cores "$CORES"
          --max-jobs "$MAXJOBS" --python "$PY" --out "$OUT/$name")
    if [ -z "$itermx" ]; then
        itermx=$ITERMX
    fi
    if [ -n "$itermx" ] && [ "$itermx" != none ]; then
        args+=(--itermx "$itermx")
    fi
    if [ "$configs" = ALL ]; then
        args+=(--all)
    else
        args+=(--configs "$configs")
    fi
    if [ -n "$threads" ]; then
        args+=(--threads "$threads")
    fi
    if [ ${#TOLARGS[@]} -gt 0 ]; then
        args+=("${TOLARGS[@]}")
    fi
    echo "== flow $name: $PY -I $CLI ${args[*]}"
    t0=$(date +%s)
    "$PY" -I "$CLI" "${args[@]}"
    rc=$?
    echo "== flow $name: exit $rc, $(( $(date +%s) - t0 )) s"
    DIRS+=("$OUT/$name")
    CODES="${CODES:+$CODES,}$rc"
done

# 5. combined summary, annotations, exit code
WALL=$(( $(date +%s) - START ))
"$PY" -I "$HERE/report.py" --set "$SET" --gate "$GATE" --gate-mode "$GATEMODE" --wall "$WALL" \
    --codes "$CODES" "${DIRS[@]}"
rc=$?
echo "== OpenMP CI done: exit $rc, wall $WALL s (unit tests, smoke test and flows; build not included)"
exit $rc
