"""Summarise ThreadSanitizer reports from an OpenMP Jacobian run (AIUE-50).

Groups the "data race" reports in TSan log files by the memory location (global symbol, or "heap"/"stack") and by
whether the racing access happened inside the Jacobian column loop (a frame `localjacbuilder_` in either stack) or
elsewhere (OmpCopy*/setarraypointer copies across parallel regions, which an uninstrumented OpenMP runtime makes
TSan report as races: likely false positives).

How the logs were produced (macOS arm64, Homebrew gfortran 15 has no libtsan, LLVM's runtime works):
    1. scratch tree: add '-fsanitize=thread' to FLAGS['FARGS'] in setup.py; build with build_uedge.sh ... omp
    2. run with DYLD_INSERT_LIBRARIES=<llvm>/lib/clang/<v>/lib/darwin/libclang_rt.tsan_osx_dynamic.dylib
       TSAN_OPTIONS="log_path=<dir>/tsan halt_on_error=0" OMP_NUM_THREADS=4 OMP_STACKSIZE=512M
       python -I <driver> --tebox  (with ppp.OMPParallelJac=1)

Usage:
    python -I tsan_summary.py <dir>/tsan.*
Prints one line per (location, in-loop) group with the count and the first source line of each access.
"""
import collections
import re
import sys


def main(paths):
    groups = collections.OrderedDict()
    for p in paths:
        txt = open(p, errors="replace").read()
        for blk in txt.split("==================\n"):
            if "WARNING: ThreadSanitizer: data race" not in blk:
                continue
            loc = re.search(r"Location is (global '([^']+)'|heap block|stack of [^\n]*)", blk)
            where = loc.group(2) if loc and loc.group(2) else (loc.group(1).split(" of")[0] if loc else "unknown")
            inloop = "localjacbuilder_" in blk
            frames = re.findall(r"#0 (\S+) (\S+:\d+)", blk)
            key = (where, inloop)
            g = groups.setdefault(key, {"n": 0, "frames": collections.Counter()})
            g["n"] += 1
            for f in frames[:2]:
                g["frames"][f"{f[0]} {f[1]}"] += 1
    print(f"{'count':>5}  {'in Jacobian loop':16}  location  |  first frames")
    for (where, inloop), g in sorted(groups.items(), key=lambda kv: (not kv[0][1], -kv[1]["n"])):
        fr = "; ".join(k for k, _ in g["frames"].most_common(3))
        print(f"{g['n']:5d}  {'yes' if inloop else 'no':16}  {where}  |  {fr}")


if __name__ == "__main__":
    main(sys.argv[1:])
