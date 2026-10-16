#!/bin/bash
# link_record.sh NAME : per extension of /work/venv-NAME: NEEDED, ldd, undefined OpenMP runtime symbols
# (nm -D, anchored), and `ldd -r` undefined GOMP_/omp_ symbols; plus the normalised -shared link lines of the build.
# Writes /out/rec_NAME/{needed,ldd,nm_omp,ldd_r_omp,links}.txt
B=$1; O=/out/rec_$B; mkdir -p $O
PKG=$(cd /tmp && /work/venv-$B/bin/python -I -c "import importlib.util as u, os; print(os.path.dirname(u.find_spec('uedge').origin))")
: > $O/needed.txt; : > $O/ldd.txt; : > $O/nm_omp.txt; : > $O/ldd_r_omp.txt
for so in $(find "$PKG" -maxdepth 1 -name '*.so' | sort); do
  e=$(basename "$so" | sed -E 's/\.cpython.*//')
  echo "$e: $(readelf -d "$so" | awk '/NEEDED/ {gsub(/[\[\]]/,"",$5); print $5}' | tr '\n' ' ')" >> $O/needed.txt
  { echo "== $e"; ldd "$so" | sed -E 's/ \(0x[0-9a-f]+\)//'; } >> $O/ldd.txt
  echo "$e: $(nm -D --undefined-only "$so" | awk '{print $NF}' | grep -E '^(GOMP_|omp_)' | sort | tr '\n' ' ')" >> $O/nm_omp.txt
  r=$(ldd -r "$so" 2>&1 | grep -E 'undefined symbol: (GOMP_|omp_)' | sed -E 's/\t\(.*\)$//' | sort | tr '\n' ' ')
  echo "$e: $r" >> $O/ldd_r_omp.txt
done
grep -a -E '^[[:space:]]*(x86_64-linux-gnu-)?(gcc|cc)[^ ]* .*-shared ' /out/build_$B.log \
  | sed -E "s#/work/src-$B#SRC#g; s#/work/venv-$B#VENV#g; s#/tmp/[A-Za-z0-9_.-]+#TMP#g" \
  | awk '{ m=""; if (match($0, /[A-Za-z0-9_]+\.cpython-[^ ]*\.so/)) m=substr($0,RSTART,RLENGTH); sub(/\.cpython.*/,"",m); print m ": " $0 }' \
  | sort > $O/links.txt
echo "link lines: $(wc -l < $O/links.txt)"; echo "dir $PKG"
