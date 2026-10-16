"""AIUE-61 G10-static: in OMPJacBuilder, OMPTimeLocalJac may be indexed by the thread id (tid+1) only inside the
legacy branch (the else branch of an `if (OMPJacFixedChunks.gt.0)` block). Exit 0 if so, 1 otherwise.
Usage: python AIUE-61-gate10_static.py ppp/omp_parallel.F90
"""
import re, sys

src = open(sys.argv[1]).read().splitlines()
start = next(i for i, l in enumerate(src) if re.match(r"\s*SUBROUTINE OMPJacBuilder", l))
end = next(i for i in range(start, len(src)) if re.match(r"\s*END SUBROUTINE OMPJacBuilder", src[i]))
bad, stack = [], []  # stack of [kind, branch] for if-blocks; kind "fixed" for if (OMPJacFixedChunks.gt.0)
for i in range(start, end):
    l = src[i].split("!")[0].strip()
    low = l.lower()
    if re.match(r"if\s*\(.*\)\s*then$", low):
        stack.append(["fixed" if "ompjacfixedchunks.gt.0" in low.replace(" ", "") else "other", "then"])
    elif re.match(r"else\s*if\s*\(.*\)\s*then$", low) or low == "else":
        if stack:
            stack[-1][1] = "else"
    elif re.match(r"end\s*if$", low):
        if stack:
            stack.pop()
    if "omptimelocaljac(tid+1)" in low.replace(" ", ""):
        in_legacy = any(k == "fixed" and b == "else" for k, b in stack)
        if not in_legacy:
            bad.append((i + 1, src[i].strip()))
for ln, text in bad:
    print("OMPTimeLocalJac(tid+1) outside the legacy branch at line {}: {}".format(ln, text))
print("G10-static", "PASS" if not bad else "FAIL")
sys.exit(1 if bad else 0)
