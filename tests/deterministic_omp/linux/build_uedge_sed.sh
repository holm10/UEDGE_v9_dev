#!/bin/bash
# build_uedge_sed.sh NAME COMMIT FILE SEDEXPR : as build_uedge.sh, but FILE in the clone is edited with sed -E SEDEXPR
# first (control builds only; the clone is left dirty on purpose and the diff saved as /out/patch_NAME.diff).
set -eu
NAME=$1; COMMIT=$2; FILE=$3; EXPR=$4
SRC=/work/src-$NAME; VENV=/work/venv-$NAME
git clone -q --no-checkout /mnt/repo "$SRC"
git -C "$SRC" checkout -q "$COMMIT"
sed -E -i "$EXPR" "$SRC/$FILE"
git -C "$SRC" diff > /out/patch_$NAME.diff
test -s /out/patch_$NAME.diff
python -m venv "$VENV"
"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q "forthon>=0.10.7" numpy==1.26.4 h5py pytest
cd "$SRC"
t0=$(date +%s)
{ gfortran --version | head -1; echo "LDFLAGS=${LDFLAGS-<unset>}"; "$VENV/bin/python" -m pip install -v . ; } > /out/build_$NAME.log 2>&1
echo "BUILD_S $(( $(date +%s) - t0 ))" >> /out/build_$NAME.log
"$VENV/bin/python" -m pip freeze > /out/freeze_$NAME.txt
echo "built $NAME at $(git -C "$SRC" rev-parse HEAD) (patched) in $(( $(date +%s) - t0 )) s"
