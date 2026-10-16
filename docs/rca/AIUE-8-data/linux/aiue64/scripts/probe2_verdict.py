"""Verdict for the AIUE-64 amended L5 probe: for N in 2, 4, every jac-arm worker CPU increase during exmain
must be >= max(5 x the largest serial-control worker increase at the same N, 1 ms floor). Usage: probe2_verdict.py OUTDIR"""
import re
import sys

out = sys.argv[1]


def parse(name):
    text = open("{}/probe2_{}.log".format(out, name), errors="replace").read()
    lines = [l for l in text.splitlines() if re.match(r"^(resolution|threads after|arm |main_ns|WORKER_NS)", l)]
    m = re.search(r"^WORKER_NS(.*)$", text, re.M)
    meta = re.search(r"^arm \S+ Nthreads (\d+) OMPParallelJac (\d+) threads (\d+) libgomp_mappings (\d+)", text, re.M)
    res = re.search(r"^resolution (.*)$", text, re.M)
    return lines, ([int(v) for v in m.group(1).split()] if m else None), meta, (res.group(1) if res else "?")


ok_all = True
for n in (2, 4):
    jl, jw, jm, jres = parse("jac_t{}".format(n))
    cl, cw, cm, cres = parse("ctl_t{}".format(n))
    print("== N={}".format(n))
    for l in jl:
        print("  jac:     " + l)
    for l in cl:
        print("  control: " + l)
    if jw is None or cw is None or jm is None:
        print("  RESULT N={}: ERROR (missing output)".format(n))
        ok_all = False
        continue
    floor = 1_000_000 if "schedstat" in jres else int(re.search(r"\(([\d.]+) ns\)", jres).group(1).split(".")[0])
    threshold = max(5 * max(cw, default=0), floor)
    ok = (len(jw) >= n - 1 and all(v >= threshold for v in jw) and int(jm.group(2)) == 1 and int(jm.group(4)) >= 1)
    print("  threshold = max(5 x control max {} ns, floor {} ns) = {} ns".format(max(cw, default=0), floor, threshold))
    print("  jac worker increases (ns): {}; min {}".format(jw, min(jw) if jw else None))
    print("  RESULT N={}: {}".format(n, "PASS" if ok else "FAIL"))
    ok_all = ok_all and ok
print("RESULT L5 amended probe: {}".format("PASS" if ok_all else "FAIL"))
