#!/bin/zsh
# mac_record.sh OUTDIR : records for the AIUE-64-omp and AIUE-64-serial venvs (M1): otool -L, otool -hv,
# anchored nm -u OpenMP symbols, normalised -bundle link lines, and the new-line check, per build.
OUT=$1; V=/Users/holma/Documents/uedge/src/uedge-wt/venvs; WT=/Users/holma/Documents/uedge/src/uedge-wt/AIUE-64
for m in omp serial; do
  P=$(echo $V/AIUE-64-$m/lib/python3.13/site-packages/uedge); D=$OUT/rec_$m; mkdir -p $D
  : > $D/otool_L.txt; : > $D/otool_hv.txt; : > $D/nm_omp.txt
  for so in $(ls $P/*.so | sort); do
    e=$(basename $so | sed -E 's/\.cpython.*//')
    { echo "== $e"; otool -L $so | tail -n +2; } >> $D/otool_L.txt
    { echo "== $e"; otool -hv $so | tail -n +3; } >> $D/otool_hv.txt
    echo "$e: $(nm -u $so | grep -E '^_(GOMP_|omp_)' | sort | tr '\n' ' ')" >> $D/nm_omp.txt
  done
  grep -a -E ' -bundle ' $OUT/build_$m.log | sed -E "s#$WT#WT#g; s#$V/AIUE-64-$m#VENV#g; s#/private/var/folders/[^ ]*#TMP#g; s#/var/folders/[^ ]*#TMP#g; s#/tmp/[A-Za-z0-9_.-]+#TMP#g" \
    | awk '{ m=""; if (match($0, /[A-Za-z0-9_]+\.cpython-[^ ]*\.so/)) m=substr($0,RSTART,RLENGTH); sub(/\.cpython.*/,"",m); print m ": " $0 }' | sort > $D/links.txt
  echo "$m: link lines $(wc -l < $D/links.txt); 'Linux OpenMP build:' lines in log: $(grep -c 'Linux OpenMP build:' $OUT/build_$m.log)" >> $OUT/summary.txt
done
