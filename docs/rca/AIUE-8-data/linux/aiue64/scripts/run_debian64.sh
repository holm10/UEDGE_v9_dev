#!/bin/bash
# AIUE-64 Debian 12 driver: L6. Usage: run_debian64.sh FIXCOMMIT
set -u
FIX=$(git -C /mnt/repo rev-parse "$1"); echo "FIX $FIX"
env -u LDFLAGS /scripts/build_uedge.sh fix "$FIX"
{ /scripts/import_check.sh fix; gcc --version | head -1
  echo "gcc -dumpspecs as-needed occurrences: $(gcc -dumpspecs | grep -c as-needed)"; } > /out/import.txt 2>&1
/scripts/link_record.sh fix
echo ALLDONE
