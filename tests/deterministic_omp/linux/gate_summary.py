"""Summarise AIUE-56-c1-gate.py output per group: pass/fail, worst magnitude ratio and worst |a-b|/rowmax."""
import collections
import os
import re
import sys

pat = re.compile(r"^(\S+) (run\d+): (PASS|FAIL) \(worst magnitude ratio (\S+), worst \|a-b\|/rowmax (\S+)\)")
g = collections.OrderedDict()
for line in open(sys.argv[1]):
    m = pat.match(line)
    if m:
        d = os.path.basename(m.group(1))
        s = g.setdefault(d, {"pass": 0, "fail": 0, "mag": 0.0, "dev": 0.0, "zero": 0})
        s["pass" if m.group(3) == "PASS" else "fail"] += 1
        s["mag"] = max(s["mag"], float(m.group(4)))
        s["dev"] = max(s["dev"], float(m.group(5)))
        s["zero"] += float(m.group(5)) == 0.0
for d, s in g.items():
    print("{}: GATE {} pass={} fail={} worst_magnitude_ratio={:.4g} worst_dev={:.3g} runs_with_zero_deviation={}/{}".format(
        d, "PASS" if not s["fail"] else "FAIL", s["pass"], s["fail"], s["mag"], s["dev"], s["zero"], s["pass"] + s["fail"]))
