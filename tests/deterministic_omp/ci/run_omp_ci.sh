#!/usr/bin/env bash
# OpenMP determinism CI steps (AIUE-57): the same steps locally and in .github/workflows/build-test-omp.yml.
#
#   tests/deterministic_omp/ci/run_omp_ci.sh [pr|nightly]
#
# Expects an installed OpenMP build of UEDGE (`pip install -v .`) in $PYTHON (default: python).
# Steps: harness and CI unit tests, import smoke test, the common-block check (ci/common_check.py, when
# OMP_CI_GEN_DIR is set), the AIUE-52 test flow (`harness/cli.py flow`) for the selected set, the C1 bound on
# every flow (ci/jac_bound.py), then ci/report.py (combined summary, first mismatch, the job's exit code).
#
# Sets (each entry is one flow: name|configurations|threads|repeats K|arms|itermx|ppp JSON):
#   pr       tebox1: Te box at 2,4 threads K=3, Jacobian arm, ONE EVALUATION (its post-exmain Jacobian is in
#                    natural order, so the first mismatch is the defect cell);
#            tebox:  Te box at 2,4 threads K=5, both arms, --itermx 3 (the Newton path);
#                    both Te-box flows set OMPJacMinChunkLen=1 (25 one-column chunks; the default 300 gives
#                    the 25-equation box a single chunk, i.e. no parallelism) and OMPJacVerbose=1 (the chunk
#                    count appears in run.log and in the report);
#            up1:    up alone at 4 threads K=3, Jacobian arm, one evaluation (default 21 chunks; where M3
#                    showed before AIUE-61);
#            full:   full problem at 2,4 threads K=2, Jacobian arm only, --itermx 3 (default 64 chunks; the
#                    RHS arm is report-only, so the PR set skips its costly full-problem runs).
#            Over budget (20 min) on the runner: drop up1, then tebox K 5 -> 3, then full at 4 threads only.
#   nightly  all1:   every configuration (--all: threads 2,4,8) K=2, both arms, one evaluation, defaults;
#            tebox1: Te box at 2,4,8 threads K=3, both arms, one evaluation, 25 chunks;
#            all:    every configuration K=3, both arms, --itermx 3
#
# Environment (all optional):
#   PYTHON                 interpreter of the build under test (default: python)
#   OMP_CI_OUT             new output directory (default: ./omp-ci-out); must not exist
#   OMP_CI_CORES           core budget for concurrent runs (default: all cores; in a container `nproc` may
#                          report the host's cores, so set it there)
#   OMP_CI_MAX_JOBS        at most this many runs at a time (default: OMP_CI_CORES)
#   OMP_CI_GATE            arm(s) that set the exit code: jac (default), jacrhs, all, none
#   OMP_CI_ITERMX          Newton iterations for flows whose itermx field is empty (default 3; set but
#                          empty: one evaluation)
#   OMP_CI_FLOWS           custom flows instead of the set, "name|configs|threads|K|arms|itermx|ppp;..." (configs
#                          ALL: --all; empty threads: the flow default; empty arms: jac,jacrhs; itermx none:
#                          one evaluation, empty: OMP_CI_ITERMX; ppp: JSON for --ppp, empty: none)
#   OMP_CI_SKIP_UNIT_TESTS 1 skips the harness and CI unit tests
#   OMP_CI_GEN_DIR         the build's generated sources (build/temp.<plat>-cpython-<ver>, with bbb_p.F90):
#                          enables the common-block check (the workflow always sets it); unset: skipped
#   OMP_CI_JAC_TOLERANCE   Empty (default): the Jacobian arm gates bitwise, with the C1 bound (1e-6 x serial row
#                          max on the scaled post_exmain Jacobian) as a backstop. A value V in (0, 1e-6]:
#                          tolerance mode (one-evaluation flows only; --itermx flows stay bitwise): a jac group
#                          that differs from serial only in Jacobian sections,
#                          is deterministic and has every run within V counts as PASS (for macOS, where C2
#                          leaves round-off differences; never set on the Linux CI runner).
#
# Exit code: 0 the gated arm agrees bitwise with serial and between repeats (or within tolerance), within the
# C1 bound, and the common-block check passed or was skipped; 1 a gated mismatch, a bound or a common-block
# FAIL; 2 harness or setup error (unit tests, smoke test, a bad switch, a failed serial reference, a missing
# bound result).
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
TEBOX_PPP='{"OMPJacMinChunkLen": 1, "OMPJacVerbose": 1}'

case "$SET" in
    pr)      FLOWS="tebox1|tebox|2,4|3|jac|none|$TEBOX_PPP;tebox|tebox|2,4|5|jac,jacrhs|3|$TEBOX_PPP"
             FLOWS="$FLOWS;up1|up|4|3|jac|none|;full|full|2,4|2|jac|3|" ;;
    nightly) FLOWS="all1|ALL||2|jac,jacrhs|none|;tebox1|tebox|2,4,8|3|jac,jacrhs|none|$TEBOX_PPP"
             FLOWS="$FLOWS;all|ALL||3|jac,jacrhs|3|" ;;
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

# gate mode: bitwise, or tolerance V with 0 < V <= 1e-6 (the registered C1 bound)
GATEMODE=bitwise
BTOL=1e-6
if [ -n "$TOL" ]; then
    if ! "$PY" -I -c 'import sys; v = float(sys.argv[1]); sys.exit(0 if 0 < v <= 1e-6 else 1)' "$TOL" 2>/dev/null; then
        echo "run_omp_ci.sh: OMP_CI_JAC_TOLERANCE=$TOL is not a number in (0, 1e-6] (exit 2)"
        exit 2
    fi
    GATEMODE=tolerance
    BTOL=$TOL
fi

START=$(date +%s)
echo "== OpenMP CI: set $SET, gate $GATE ($GATEMODE, bound $BTOL), cores $CORES, max jobs $MAXJOBS, itermx $ITERMX, python $PY"
echo "== flows: $FLOWS"

# 1. harness and CI unit tests (no UEDGE build needed)
if [ "${OMP_CI_SKIP_UNIT_TESTS:-0}" != 1 ]; then
    echo "== unit tests"
    if ! "$PY" -m pytest -q -p no:cacheprovider "$OMPDIR/harness" "$OMPDIR/ci"; then
        echo "run_omp_ci.sh: unit tests failed (exit 2)"
        exit 2
    fi
fi

# 2. smoke test: import in an empty HOME, isolated mode (no ~/.uedgerc.py, no PYTHON* variables)
echo "== smoke test"
SMOKE=$OUT/smoke
mkdir -p "$SMOKE/home"
if ! (cd "$SMOKE" && HOME="$SMOKE/home" OMP_NUM_THREADS=1 "$PY" -I -c \
        "import uedge; from uedge import bbb, ppp; print('uedge_ver', bbb.uedge_ver, 'OMPParallelJac', ppp.OMPParallelJac, 'OMPJacFixedChunks', getattr(ppp, 'OMPJacFixedChunks', 'n/a'))"); then
    echo "run_omp_ci.sh: smoke test failed (exit 2)"
    exit 2
fi
# every key of the flows' ppp fields must exist in this build (names the key instead of "no such attribute")
if ! (cd "$SMOKE" && HOME="$SMOKE/home" OMP_NUM_THREADS=1 "$PY" -I "$HERE/ppp_keys.py" "$FLOWS"); then
    echo "run_omp_ci.sh: ppp check failed (exit 2)"
    exit 2
fi

# 3. common-block check (AIUE-60 G-common); its code goes to the report, the flows run anyway
COMMONARGS=()
if [ -n "${OMP_CI_GEN_DIR:-}" ]; then
    echo "== common-block check (generated sources in $OMP_CI_GEN_DIR)"
    PKGDIR=$(cd "$SMOKE" && "$PY" -I -c \
        "import importlib.util as u; s = u.find_spec('uedge'); print(s.submodule_search_locations[0])" 2>/dev/null)
    if [ -z "$PKGDIR" ]; then
        echo "run_omp_ci.sh: cannot locate the installed uedge package (common-block check: exit 2)"
        COMMON=2
    else
        "$PY" -I "$HERE/common_check.py" --pkgdir "$PKGDIR" --gen "$OMP_CI_GEN_DIR"
        COMMON=$?
    fi
    COMMONARGS=(--common-code "$COMMON")
else
    echo "== common-block check skipped (OMP_CI_GEN_DIR not set)"
fi

# 4. the flows
DIRS=()
CODES=""
IFS=';' read -r -a FLOWLIST <<< "$FLOWS"
for spec in "${FLOWLIST[@]}"; do
    IFS='|' read -r name configs threads repeats arms itermx ppp <<< "$spec"
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
    if [ -n "${ppp:-}" ]; then
        args+=(--ppp "$ppp")
    fi
    echo "== flow $name: $PY -I $CLI ${args[*]}"
    t0=$(date +%s)
    "$PY" -I "$CLI" "${args[@]}"
    rc=$?
    echo "== flow $name: exit $rc, $(( $(date +%s) - t0 )) s"
    DIRS+=("$OUT/$name")
    CODES="${CODES:+$CODES,}$rc"
done

# 5. the C1 bound on the scaled post_exmain Jacobian of every jac run (backstop; tolerance mode uses it)
BCODES=""
for d in "${DIRS[@]}"; do
    echo "== C1 bound: $(basename "$d") (tol $BTOL)"
    "$PY" -I "$HERE/jac_bound.py" --flow "$d" --tol "$BTOL" --json "$d/bound.json"
    BCODES="${BCODES:+$BCODES,}$?"
done

# 6. combined summary, annotations, exit code
WALL=$(( $(date +%s) - START ))
"$PY" -I "$HERE/report.py" --set "$SET" --gate "$GATE" --gate-mode "$GATEMODE" --tol "$BTOL" \
    --bound-codes "$BCODES" ${COMMONARGS[@]+"${COMMONARGS[@]}"} --wall "$WALL" --codes "$CODES" "${DIRS[@]}"
rc=$?
echo "== OpenMP CI done: exit $rc, wall $WALL s (unit tests, smoke test, checks and flows; build not included)"
exit $rc
