#!/bin/bash
# build_uedge.sh NAME COMMIT [serial] : clone the read-only repo at COMMIT into /work/src-NAME, make /work/venv-NAME
# with the CI pip dependencies, and run the CI build command (python -m pip install -v .; with "serial":
# -C "--build-option=--serial"). Honours LDFLAGS. Log: /out/build_NAME.log. (AIUE-62 build_uedge.sh + serial.)
set -eu
NAME=$1; COMMIT=$2; MODE=${3:-omp}
SRC=/work/src-$NAME; VENV=/work/venv-$NAME
git clone -q --no-checkout /mnt/repo "$SRC"
git -C "$SRC" checkout -q "$COMMIT"
python -m venv "$VENV"
"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q "forthon>=0.10.7" numpy==1.26.4 h5py pytest
cd "$SRC"
EXTRA=()
if [ "$MODE" = serial ]; then EXTRA=(-C "--build-option=--serial"); fi
t0=$(date +%s)
{ gfortran --version | head -1; echo "LDFLAGS=${LDFLAGS-<unset>}"; echo "MODE=$MODE"
  "$VENV/bin/python" -m pip install -v . "${EXTRA[@]}" ; } > /out/build_$NAME.log 2>&1
echo "BUILD_S $(( $(date +%s) - t0 ))" >> /out/build_$NAME.log
"$VENV/bin/python" -m pip freeze > /out/freeze_$NAME.txt
echo "built $NAME ($MODE) at $(git -C "$SRC" rev-parse HEAD), dirty paths: $(git -C "$SRC" status --porcelain | wc -l), $(( $(date +%s) - t0 )) s"
