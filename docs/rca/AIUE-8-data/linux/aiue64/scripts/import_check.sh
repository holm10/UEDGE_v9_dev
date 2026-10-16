#!/bin/bash
# import_check.sh NAME... : the import in an empty HOME, isolated mode, as the AIUE-57 smoke test does it
mkdir -p /tmp/h
for b in "$@"; do
  echo "\$ cd /tmp && HOME=/tmp/h OMP_NUM_THREADS=1 /work/venv-$b/bin/python -I -c \"import uedge; from uedge import bbb, ppp; print('uedge_ver', bbb.uedge_ver, 'OMPParallelJac', ppp.OMPParallelJac)\""
  (cd /tmp && HOME=/tmp/h OMP_NUM_THREADS=1 /work/venv-$b/bin/python -I -c "import uedge; from uedge import bbb, ppp; print('uedge_ver', bbb.uedge_ver, 'OMPParallelJac', ppp.OMPParallelJac)") 2>&1
  echo "exit status $?"
done
