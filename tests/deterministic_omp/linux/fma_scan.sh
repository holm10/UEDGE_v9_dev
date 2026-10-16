#!/bin/bash
# fma_scan.sh BUILD : FMA / AVX instruction counts in every extension of the installed uedge package, the OpenMP
# runtime it links, and the Fortran compile flags from the build log.
B=$1
PY=/work/venv-$B/bin/python
PKG=$($PY -c "import os,uedge;print(os.path.dirname(uedge.__file__))" 2>/dev/null)
echo "== build $B, package $PKG, arch $(uname -m)"
echo "== source commit $(git -C /work/src-$B rev-parse HEAD), dirty: $(git -C /work/src-$B status --porcelain | wc -l) paths"
gfortran --version | head -1
for so in $(find "$PKG" -name '*.so' | sort); do
  d=$(objdump -d --no-show-raw-insn "$so")
  if [ "$(uname -m)" = x86_64 ]; then
    fma=$(grep -cE '\s(vfn?m(add|sub)[0-9a-z]*|vfmaddsub[0-9a-z]*|vfmsubadd[0-9a-z]*)\s' <<< "$d")
    fma4=$(grep -cE '\svfn?m(add|sub)(ss|sd|ps|pd)\s' <<< "$d")
    ymm=$(grep -c '%ymm' <<< "$d"); zmm=$(grep -c '%zmm' <<< "$d")
    mulsd=$(grep -cE '\smul[sp]d\s' <<< "$d")
    echo "$(basename $so): insns $(grep -cP '^\s+[0-9a-f]+:\t' <<< "$d") fma3/fma4(vf*m{add,sub}*) $fma ymm-operands $ymm zmm-operands $zmm mulsd/mulpd $mulsd"
  else
    fma=$(grep -cE '\s(fmadd|fmsub|fnmadd|fnmsub|fmla|fmls)\s' <<< "$d")
    fmul=$(grep -cE '\sfmul\s' <<< "$d")
    echo "$(basename $so): insns $(grep -cP '^\s+[0-9a-f]+:\t' <<< "$d") fmadd/fmsub/fnmadd/fnmsub/fmla/fmls $fma fmul $fmul"
  fi
  echo "   needs: $(objdump -p "$so" | awk '/NEEDED/ {print $2}' | tr '\n' ' ')"
  echo "   .comment: $(readelf -p .comment "$so" 2>/dev/null | grep -o 'GCC: .*' | sort -u | tr '\n' ';')"
done
echo "== Fortran compile lines in the build log (distinct flag sets)"
grep -a -oE '(gfortran|f95)[^ ]* .* -c [^ ]+\.(F|F90|f|f90)\b' /out/build_$B.log | sed -E 's/ -c [^ ]+\.(F|F90|f|f90)$//; s#-I[^ ]+##g; s#-J[^ ]+##g; s#/work/src-[a-z]+#SRC#g' | sort | uniq -c | sort -rn | head -10
echo "== cpu flags (fma/avx)"; grep -m1 -oE '\b(fma|avx|avx2|avx512f)\b' /proc/cpuinfo | tr '\n' ' '; echo
