#!/bin/bash
# run_ci_replay.sh NAME COMMIT [SET]: replay the steps of .github/workflows/build-test-omp.yml inside the Ubuntu 24.04
# image (Dockerfile.ubuntu, gcc/gfortran 13.3, the CI runner's distribution; Python 3.12 where CI has 3.11).
#   1. clone the read-only repo (/mnt/repo) at COMMIT into /work/ci-NAME;
#   2. make /work/venv-ci-NAME with the workflow's pip line and build with the workflow's command
#      (`python -m pip install -v .`, in the clone; LDFLAGS only if the caller sets it), log /out/build_ci_NAME.log;
#   3. resolve OMP_CI_GEN_DIR with ci/gen_dir.sh, as the workflow step does;
#   4. run ci/run_omp_ci.sh SET (default pr) from the tree root with OMP_CI_OUT=/out/NAME and OMP_CI_CORES=4
#      (ubuntu-latest has 4 vCPUs; `nproc` in a container reports the host's cores, --cpus only caps time).
# RUN_TREE=DIR runs the CI scripts of another, existing clone (e.g. /work/ci-fix) against this build: the
# negative control on a tree without tests/deterministic_omp/ci. OMP_CI_* variables are passed through.
# Host side (one container at a time):
#   docker run -d --name aiue57-ci --platform linux/amd64 --cpus 5 --memory 7g -v <repo>:/mnt/repo:ro \
#     -v <out>:/out -v <repo>/tests/deterministic_omp/linux:/scripts:ro aiue62-ubuntu:amd64 sleep infinity
#   docker exec aiue57-ci /scripts/run_ci_replay.sh fix <commit> pr
set -u
NAME=$1
COMMIT=$2
SET=${3:-pr}
SRC=/work/ci-$NAME
VENV=/work/venv-ci-$NAME
mkdir -p /work /out
git clone -q --no-checkout /mnt/repo "$SRC" || exit 2
git -C "$SRC" checkout -q "$COMMIT" || exit 2
python -m venv "$VENV" || exit 2
"$VENV/bin/python" -m pip install -q --upgrade pip || exit 2
"$VENV/bin/python" -m pip install -q "forthon>=0.10.7" numpy==1.26.4 h5py pytest || exit 2
t0=$(date +%s)
if ! (cd "$SRC" && { gfortran --version | head -1; echo "LDFLAGS=${LDFLAGS-<unset>}";
                     "$VENV/bin/python" -m pip install -v .; }) > "/out/build_ci_$NAME.log" 2>&1; then
    echo "REPLAY $NAME: build failed (see /out/build_ci_$NAME.log)"
    exit 2
fi
echo "REPLAY $NAME: built $(git -C "$SRC" rev-parse HEAD) in $(( $(date +%s) - t0 )) s"
"$VENV/bin/python" -m pip freeze > "/out/freeze_ci_$NAME.txt"
RUN=${RUN_TREE:-$SRC}
GEN=$(bash "$RUN/tests/deterministic_omp/ci/gen_dir.sh" "$SRC") || exit 2
echo "REPLAY $NAME: OMP_CI_GEN_DIR=$GEN; CI scripts from $RUN ($(git -C "$RUN" rev-parse --short HEAD))"
t0=$(date +%s)
(cd "$RUN" && OMP_CI_GEN_DIR=$GEN OMP_CI_CORES=${OMP_CI_CORES:-4} OMP_CI_OUT=/out/$NAME \
    PYTHON="$VENV/bin/python" bash tests/deterministic_omp/ci/run_omp_ci.sh "$SET")
rc=$?
echo "REPLAY $NAME: run_omp_ci.sh exit $rc, $(( $(date +%s) - t0 )) s"
exit $rc
