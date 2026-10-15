"""Static probe: non-threadprivate .v variables passed as actual arguments (CALL or known spline functions)
in units reachable from pandf. Heuristic; reads the AIUE-50 scanner for units and call graph."""
import glob, os, re, sys, importlib.util
TOOLS = "/Users/holma/Documents/uedge/src/uedge-wt/AIUE-50/tests/deterministic_omp/tools/scan_saved_locals.py"
spec = importlib.util.spec_from_file_location("ssl", TOOLS); ssl = importlib.util.module_from_spec(spec); spec.loader.exec_module(ssl)
src = sys.argv[1]
VAR = re.compile(r"^\s*([A-Za-z_]\w*)\s*(\([^#]*?\))?\s+(_?)(real|integer|logical|character|double|complex)\b", re.I)
vars_ = {}
for v in glob.glob(os.path.join(src, "*/*.v")):
    pkg = os.path.basename(v)[:-2]; grp = None
    for line in open(v, errors="replace"):
        m = re.match(r"^\*{4,5}\s*(\w+)\s*:", line)
        if m: grp = m.group(1); continue
        if grp is None or grp.lower() == "subs": continue
        code = line.split("#", 1)[0]
        m = VAR.match(code)
        if m and "function" not in code and "subroutine" not in code:
            vars_.setdefault(m.group(1).lower(), []).append((pkg, grp, "+threadprivate" in code))
units = []
for g in ssl.SRC_GLOBS:
    for p in sorted(glob.glob(os.path.join(src, g))):
        rel = os.path.relpath(p, src)
        if rel.startswith(("build", "tests", "pyscripts", "builder")): continue
        units += ssl.split_units(p, rel)
funcs = {u["name"] for u in units if u["kind"] == "function"}
info = {u["name"]: ssl.analyse(u, funcs) for u in units}
byname = {}
for u in units: byname.setdefault(u["name"], u)
reach, stack = set(), ["pandf"]
while stack:
    n = stack.pop()
    if n in reach or n not in info: continue
    reach.add(n); stack += [c for c in info[n][0] if c in info]
SPL = ("b2vahl", "b1vahl", "b3val", "b2val", "intrhv")
hits = {}
for name in sorted(reach):
    u = byname[name]; used = set()
    for ln, t in u["lines"]:
        used |= set(re.findall(r"use\s*\(\s*(\w+)\s*\)", t.lower()))
    for ln, t in u["lines"]:
        low = t.lower()
        args = []
        for m in re.finditer(r"\bcall\s+(\w+)\s*\((.*)\)", low): args.append((m.group(1), m.group(2)))
        for f in SPL:
            for m in re.finditer(rf"\b{f}\s*\((.*)\)", low): args.append((f, m.group(1)))
        for callee, a in args:
            for n in set(re.findall(r"\b([a-z_]\w*)\b", a)):
                for pkg, grp, tp in vars_.get(n, []):
                    if not tp and grp.lower() in used:
                        hits.setdefault((pkg, grp, n), set()).add(f"{u['file']}:{ln}({name}->{callee})")
for k, w in sorted(hits.items()):
    print(".".join(k), len(w), "; ".join(sorted(w)[:3]))
