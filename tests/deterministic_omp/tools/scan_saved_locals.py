"""Static scan for saved local state in routines reachable from pandf (AIUE-50).

A local variable that keeps its value between calls (SAVE statement, DATA statement, or an F90 initialiser in a
type declaration, which implies SAVE) and COMMON-block variables are one storage location shared by all OpenMP
threads, unless they are named in `!$omp threadprivate`. If such a variable is assigned during a Jacobian column
(`pandf` and everything it calls), threads race on it.

The scan reads the hand-written sources (MPPL `*.m`, free-form `*.F90`, tracked fixed-form `*.f`), splits them into
program units, builds a call graph (CALL statements plus references to known FUNCTION names), and reports, for
every unit reachable from the roots (default: `pandf`), every saved/DATA/COMMON variable and whether the unit
assigns it after initialisation (`assigned` = an assignment statement with that variable on the left-hand side;
`passed` = the variable is an actual argument of a CALL in that unit and may be modified by the callee).

Usage:
    python -I scan_saved_locals.py [--src <tree>] [--roots pandf,LocalJacBuilder] [--all] [--md out.md]

    --src    source tree (default: three levels up from this file)
    --all    also list units NOT reachable from the roots
Prints a markdown table to stdout (or --md). Line numbers refer to the .m/.F90/.f source, not the generated .F.
Limitations: function references through dummy procedures and generic interfaces are not followed; ENTRY
statements are treated as part of the enclosing unit; variables that are saved because the whole unit is
compiled with -fno-automatic are not detected (UEDGE does not use that flag; with -fopenmp gfortran implies
-frecursive, so ordinary locals are on the stack).
"""
import argparse
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
UNIT_RE = re.compile(r"^\s*(?:(?:real(?:\*\d+)?|integer(?:\*\d+)?|logical|double\s+precision|character(?:\*\d+)?|"
                     r"recursive|pure|elemental|real\s*\(\s*kind\s*=\s*\d+\s*\))\s+)*"
                     r"(subroutine|function)\s+(\w+)", re.I)
END_RE = re.compile(r"^\s*end\s*(subroutine|function)?\s*(\w+)?\s*$", re.I)
SRC_GLOBS = ["*/*.m", "ppp/*.F90", "svr/*.F90", "com/*.F90", "com/*.f", "ncl/*.f", "svr/*.f"]


def logical_lines(path):
    """Yield (lineno, text) with comments removed and continuations joined."""
    free = path.endswith(".F90")
    out = []
    with open(path, errors="replace") as f:
        raw = f.read().splitlines()
    for i, line in enumerate(raw, 1):
        if not free:
            if line[:1] in ("c", "C", "*", "!") and not line.lower().startswith("c!omp"):
                continue
            if line.lower().startswith("c!omp"):
                line = "!$omp" + line[5:]
            else:
                line = re.split(r"[#!]", line, maxsplit=1)[0] if not line.lstrip().startswith("!$omp") else line
            if len(line) > 5 and line[5] not in (" ", "0", "\t") and out and not line[:5].strip():
                out[-1] = (out[-1][0], out[-1][1] + " " + line[6:])
                continue
        else:
            s = line.strip()
            if s.startswith("!") and not s.lower().startswith("!$omp"):
                continue
            if not s.lower().startswith("!$omp"):
                line = line.split("!", 1)[0]
            if out and out[-1][1].rstrip().endswith("&"):
                out[-1] = (out[-1][0], out[-1][1].rstrip()[:-1] + " " + line.strip().lstrip("&"))
                continue
        if line.strip():
            out.append((i, line))
    return out


def split_units(path, rel):
    units = []
    cur = None
    depth = 0
    for ln, text in logical_lines(path):
        m = UNIT_RE.match(text)
        if m and not re.match(r"^\s*end\b", text, re.I):
            if cur is None:
                cur = {"name": m.group(2).lower(), "kind": m.group(1).lower(), "file": rel, "line": ln, "lines": []}
                depth = 0
            else:
                depth += 1  # internal procedure (contains); keep in parent
            cur["lines"].append((ln, text))
            continue
        if cur is not None:
            cur["lines"].append((ln, text))
            e = END_RE.match(text)
            if e and re.match(r"^\s*end\s*$", text, re.I) or (e and e.group(1)):
                if depth == 0:
                    units.append(cur)
                    cur = None
                else:
                    depth -= 1
    return units


def analyse(unit, func_names):
    calls, saved, common, tp = set(), {}, {}, set()
    save_all = False
    body = unit["lines"]
    decl_kw = re.compile(r"^\s*(real|integer|logical|character|double|type|complex)\b", re.I)
    for ln, t in body:
        low = t.lower()
        for c in re.findall(r"\bcall\s+(\w+)", low):
            calls.add(c)
        for fn in re.findall(r"\b(\w+)\s*\(", low):
            if fn in func_names and fn != unit["name"]:
                calls.add(fn)
        m = re.match(r"^\s*save\b\s*(.*)$", low)
        if m:
            lst = m.group(1).strip().lstrip(":").strip()
            if not lst:
                save_all = True
            for n in re.findall(r"\b([a-z_]\w*)\b", lst.replace("/", " ")):
                saved.setdefault(n, ("SAVE", ln))
        m = re.match(r"^\s*data\s+(.*)$", low)
        if m:
            for grp in re.findall(r"([^/]+)/[^/]*/", m.group(1)):
                for n in re.findall(r"\b([a-z_]\w*)\b", re.sub(r"\([^)]*\)", "", grp)):
                    saved.setdefault(n, ("DATA", ln))
        if decl_kw.match(low) and "::" in low and "parameter" not in low.split("::")[0]:
            rhs = low.split("::", 1)[1]
            for n in re.findall(r"\b([a-z_]\w*)\s*(?:\([^)]*\))?\s*=(?!=)", rhs):
                saved.setdefault(n, ("init", ln))
        m = re.match(r"^\s*common\s*/\s*(\w*)\s*/(.*)$", low)
        if m:
            for n in re.findall(r"\b([a-z_]\w*)\b", re.sub(r"\([^)]*\)", "", m.group(2))):
                common[n] = (m.group(1), ln)
        m = re.match(r"^\s*!\$omp\s+threadprivate\s*\((.*)\)", low)
        if m:
            tp |= set(x.strip().strip("/") for x in m.group(1).split(","))
    rows = []
    for name, (how, ln) in list(saved.items()) + [(n, (f"COMMON /{b}/", ln)) for n, (b, ln) in common.items()]:
        assigned, passed = [], []
        pat_asg = re.compile(rf"^\s*(?:\d+\s+)?(?:if\s*\(.*\)\s*)?{re.escape(name)}\s*(\([^=]*\))?\s*=(?!=)", re.I)
        for l2, t in body:
            if (l2, t) and pat_asg.match(t) and not re.match(r"^\s*data\b", t, re.I) and not decl_kw.match(t):
                assigned.append(l2)
            elif re.search(rf"\bcall\s+\w+\s*\(.*\b{re.escape(name)}\b", t, re.I):
                passed.append(l2)
        rows.append({"var": name, "how": how, "decl_line": ln, "assigned": assigned, "passed": passed,
                     "threadprivate": name in tp or (how.startswith("COMMON") and how.split("/")[1] in tp)})
    return calls, rows, save_all


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.normpath(os.path.join(HERE, "..", "..", "..")))
    ap.add_argument("--roots", default="pandf")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--md")
    a = ap.parse_args(argv)
    units = []
    for g in SRC_GLOBS:
        for p in sorted(glob.glob(os.path.join(a.src, g))):
            rel = os.path.relpath(p, a.src)
            if rel.startswith(("build", "tests", "pyscripts", "builder")):
                continue
            units += split_units(p, rel)
    byname = {}
    for u in units:
        byname.setdefault(u["name"], u)
    funcs = {u["name"] for u in units if u["kind"] == "function"}
    info = {}
    for u in units:
        info[u["name"]] = analyse(u, funcs)
    reach, stack, parent = set(), [r.lower() for r in a.roots.split(",")], {}
    while stack:
        n = stack.pop()
        if n in reach or n not in info:
            continue
        reach.add(n)
        for c in info[n][0]:
            if c not in reach and c in info:
                parent.setdefault(c, n)
                stack.append(c)
    out = [f"# Saved locals / DATA / COMMON in units reachable from {a.roots}", "",
           f"{len(units)} program units scanned, {len(reach)} reachable from {a.roots}.", "",
           "| unit | file:line | reachable (via) | variable | kind | declared at | assigned at | passed to CALL at |"
           " threadprivate |", "|---|---|---|---|---|---|---|---|---|"]
    nrows = 0
    for u in sorted(units, key=lambda u: (u["name"] not in reach, u["file"], u["line"])):
        calls, rows, save_all = info[u["name"]]
        r = u["name"] in reach
        if not (r or a.all):
            continue
        if save_all:
            rows = [{"var": "(all locals)", "how": "SAVE", "decl_line": u["line"], "assigned": [], "passed": [],
                     "threadprivate": False}] + rows
        for row in rows:
            nrows += 1
            via = parent.get(u["name"], "root") if r else "no"
            out.append(f"| {u['name']} | {u['file']}:{u['line']} | {'yes (' + via + ')' if r else 'no'} | {row['var']} |"
                       f" {row['how']} | {u['file']}:{row['decl_line']} |"
                       f" {', '.join(map(str, row['assigned'][:6])) or '-'} | {', '.join(map(str, row['passed'][:6])) or '-'} |"
                       f" {'yes' if row['threadprivate'] else 'no'} |")
    out.append("")
    out.append(f"{nrows} rows.")
    text = "\n".join(out) + "\n"
    if a.md:
        open(a.md, "w").write(text)
    print(text)


if __name__ == "__main__":
    main(sys.argv[1:])
