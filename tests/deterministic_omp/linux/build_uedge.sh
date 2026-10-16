#!/bin/bash
# build_uedge.sh NAME COMMIT : clone the read-only repo at COMMIT into /work/src-NAME, make /work/venv-NAME with the
# CI pip dependencies, and run the CI build command (python -m pip install -v .). Log: /out/build_NAME.log
set -eu
NAME=$1; COMMIT=$2
SRC=/work/src-$NAME; VENV=/work/venv-$NAME
git clone -q --no-checkout /mnt/repo "$SRC"
git -C "$SRC" checkout -q "$COMMIT"
python -m venv "$VENV"
"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q "forthon>=0.10.7" numpy==1.26.4 h5py pytest
cd "$SRC"
t0=$(date +%s)
{ gfortran --version | head -1; echo "LDFLAGS=${LDFLAGS-<unset>}"; "$VENV/bin/python" -m pip install -v . ; } > /out/build_$NAME.log 2>&1
echo "BUILD_S $(( $(date +%s) - t0 ))" >> /out/build_$NAME.log
"$VENV/bin/python" -m pip freeze > /out/freeze_$NAME.txt
echo "built $NAME at $(git -C "$SRC" rev-parse HEAD) in $(( $(date +%s) - t0 )) s"
