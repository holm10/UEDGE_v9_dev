#!/usr/bin/env bash
# gen_dir.sh [SRCDIR]: print the absolute path of the build's generated-source directory, SRCDIR/build/temp.*
# (where `pip install -v .` leaves the Forthon-generated <pkg>_p.F90), for ci/common_check.py (OMP_CI_GEN_DIR).
# Exactly one such directory holding bbb_p.F90 is required; anything else is an error (exit 1), so the
# workflow step fails instead of the check silently judging the wrong build. Used by
# .github/workflows/build-test-omp.yml and linux/run_ci_replay.sh.
set -u
SRC=${1:-.}
found=()
for d in "$SRC"/build/temp.*; do
    if [ -f "$d/bbb_p.F90" ]; then
        found+=("$d")
    fi
done
if [ ${#found[@]} -ne 1 ]; then
    echo "gen_dir.sh: expected exactly one $SRC/build/temp.* directory with bbb_p.F90, found ${#found[@]}" >&2
    exit 1
fi
(cd "${found[0]}" && pwd)
