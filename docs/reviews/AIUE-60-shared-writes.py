"""Static probe: non-threadprivate .v module variables assigned in units reachable from the roots."""
import glob, os, re, sys, importlib.util
TOOLS = "/Users/holma/Documents/uedge/src/uedge-wt/AIUE-50/tests/deterministic_omp/tools/scan_saved_locals.py"
spec = importlib.util.spec_from_file_location("ssl", TOOLS); ssl = importlib.util.module_from_spec(spec); spec.loader.exec_module(ssl)
src = sys.argv[1]; roots = sys.argv[2].split(",") if len(sys.argv) > 2 else ["pandf"]
# .v variables: name -> list of (pkg, group, tp)
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
            vars_.setdefault(m.group(1).lower(), []).append((pkg, grp, "+threadprivate" in code, line.strip()[:60]))
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
reach, stack, parent = set(), [r.lower() for r in roots], {}
while stack:
    n = stack.pop()
    if n in reach or n not in info: continue
    reach.add(n)
    for c in info[n][0]:
        if c not in reach and c in info: parent.setdefault(c, n); stack.append(c)
decl_kw = re.compile(r"^\s*(real|integer|logical|character|double|type|complex|dimension)\b", re.I)
asg = re.compile(r"^\s*(?:\d+\s+)?(?:(?:else\s*)?if\s*\(.*\)\s*(?:then)?\s*)?([a-z_]\w*)\s*(\([^=]*\))?\s*=(?!=)", re.I)
hits = {}
for name in sorted(reach):
    u = byname[name]
    used = set(); local = set()
    for ln, t in u["lines"]:
        low = t.lower()
        for g in re.findall(r"use\s*\(\s*(\w+)\s*\)", low): used.add(g)
        m = re.match(r"^\s*use\s+(\w+)", low)
        if m: used.add(m.group(1))
        if decl_kw.match(low):
            body = re.sub(r"\([^()]*\)", "", low.split("::")[-1])
            body = re.sub(r"^\s*(real|integer|logical|character|double\s+precision|complex|dimension)(\*\d+)?", "", body)
            for n in re.findall(r"\b([a-z_]\w*)\b", body): local.add(n)
        # first-line args
    head = u["lines"][0][1].lower()
    m = re.search(r"\((.*)\)", head)
    if m: local |= set(x.strip() for x in m.group(1).split(","))
    for ln, t in u["lines"]:
        m = asg.match(t.lower())
        if not m: continue
        n = m.group(1)
        if n in local or n not in vars_ or n in ("if", "do"): continue
        for pkg, grp, tp, d in vars_[n]:
            if tp: continue
            if grp.lower() not in used: continue
            hits.setdefault((pkg, grp, n), []).append(f"{u['file']}:{ln}({name})")
for (pkg, grp, n), where in sorted(hits.items()):
    print(f"{pkg}.{grp}.{n}: {len(where)}  " + ", ".join(where[:4]))
print(len(reach), "reachable units;", len(hits), "variables")
