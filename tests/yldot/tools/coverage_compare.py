"""Line and branch coverage of bbb/pandf*.F from gcovr JSON, and the comparison of two runs (epic AIUE-9, PRD
section 7.10; AIUE-107).

Usage:
    python coverage_compare.py --src REPO NEW.json [--old OLD.json] [--out DIR]

NEW.json and OLD.json are `gcovr --json` reports of one coverage build (`pip install . -C
"--build-option=--coverage"`), written by tools/coverage.sh. Per report: lines executed, branches taken at least once
(gcovr's branch metric, the one the retirement gate uses) and branches executed (gcov -b's "Branches executed": the
branch's line ran), per .F file and in total. With --old: the branches OLD takes and NEW does not ("old-only") and the
reverse, keyed by (file, line, position of the branch among that line's branches), each old-only branch with its .F
line, the approximate .m line and the source text. gcovr lists the branches of one line in a fixed order for one
build, so the key is stable between two runs of the same build; reports of different builds are refused (their
instrumented lines differ).

The .F -> .m map is approximate (PRD 7.10): setup.py's MPPL conversion keeps each pandf file's line count but moves
declarations (MoveDecs) and rewrites '#' comments to '!'. A .F line maps to the same .m line when the two are equal
after that rewrite and whitespace normalisation, else to the one .m line with that normalised text, else "unmapped"
(AIUE-107 planning: 5315 same line, 393 unique elsewhere, 247 unmapped of 5955 instrumented lines).

Writes DIR/summary.md (and DIR/old_only.json with --old); prints the totals and, with --old, the gate line
    GATE: new branches taken >= old: yes|no; old-only branches: N (on L lines)
The gate's outcome is the owner's to accept (PRD 12 Phase 4); this tool only reports it.

Exit codes: 0 reported, 2 usage (unreadable report, reports of different builds).
"""
import argparse
import json
import sys
from collections import Counter, OrderedDict
from pathlib import Path


def fail(msg):
    print("coverage_compare: " + msg, file=sys.stderr)
    sys.exit(2)


def load(path):
    """{file: OrderedDict(line -> (count, [branch counts]))} from a gcovr JSON report. gcovr can list one line more
    than once (one entry per function or block group); counts are summed and branches concatenated in report order."""
    try:
        data = json.loads(Path(path).read_text())
        files = data["files"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        fail("{}: not a gcovr JSON report ({})".format(path, exc))
    out = {}
    for f in files:
        lines = OrderedDict()
        for entry in sorted(f["lines"], key=lambda e: e["line_number"]):
            n = entry["line_number"]
            count, branches = lines.get(n, (0, []))
            lines[n] = (count + entry["count"], branches + [b["count"] for b in entry.get("branches", [])])
        out[f["file"]] = lines
    if not out:
        fail("{}: no files (was the report filtered to bbb/pandf*.F?)".format(path))
    return out


def totals(lines):
    """(lines, lines executed, branches, taken at least once, executed) of one file's line table."""
    n_l = len(lines)
    e_l = sum(1 for c, _ in lines.values() if c > 0)
    n_b = sum(len(b) for _, b in lines.values())
    t_b = sum(1 for _, b in lines.values() for x in b if x > 0)
    x_b = sum(len(b) for c, b in lines.values() if c > 0)
    return n_l, e_l, n_b, t_b, x_b


def pct(a, b):
    return "{:.2f} %".format(100.0 * a / b) if b else "n/a"


def norm(text):
    return " ".join(text.replace("#", "!").split())


class SourceMap:
    """The approximate .F -> .m line map of one pandf file (module docstring)."""

    def __init__(self, src, ffile):
        self.f = (src / ffile).read_text(errors="replace").split("\n")
        mpath = (src / ffile).with_suffix(".m")
        self.m = mpath.read_text(errors="replace").split("\n") if mpath.is_file() else []
        self.mname = str(Path(ffile).with_suffix(".m"))
        self.where = {}
        for i, text in enumerate(self.m):
            self.where.setdefault(norm(text), []).append(i + 1)

    def text(self, n):
        return self.f[n - 1].strip() if 0 < n <= len(self.f) else ""

    def mline(self, n):
        """The mapped .m line number, or None (unmapped)."""
        if not 0 < n <= len(self.f):
            return None
        key = norm(self.f[n - 1])
        if n <= len(self.m) and norm(self.m[n - 1]) == key:
            return n
        hits = self.where.get(key, [])
        return hits[0] if len(hits) == 1 and key else None


def table(report):
    rows = ["| file | lines | executed | branches | taken ≥ 1 | executed (gcov -b) |", "|---|---|---|---|---|---|"]
    acc = [0] * 5
    for name in sorted(report):
        t = totals(report[name])
        acc = [a + b for a, b in zip(acc, t)]
        rows.append("| `{}` | {} | {} ({}) | {} | {} ({}) | {} ({}) |".format(
            name, t[0], t[1], pct(t[1], t[0]), t[2], t[3], pct(t[3], t[2]), t[4], pct(t[4], t[2])))
    rows.append("| **total** | {} | {} ({}) | {} | {} ({}) | {} ({}) |".format(
        acc[0], acc[1], pct(acc[1], acc[0]), acc[2], acc[3], pct(acc[3], acc[2]), acc[4], pct(acc[4], acc[2])))
    return rows, acc


def diff(new, old):
    """(old-only, new-only) lists of (file, line, k, old count, new count)."""
    if set(new) != set(old):
        fail("the reports cover different files: {}".format(sorted(set(new) ^ set(old))))
    old_only, new_only = [], []
    for name in sorted(new):
        a, b = new[name], old[name]
        if list(a) != list(b) or any(len(a[n][1]) != len(b[n][1]) for n in a):
            fail("{}: the reports' instrumented lines or branches differ (two different builds?)".format(name))
        for n in a:
            for k, (cn, co) in enumerate(zip(a[n][1], b[n][1])):
                if co > 0 and cn == 0:
                    old_only.append((name, n, k, co, cn))
                elif cn > 0 and co == 0:
                    new_only.append((name, n, k, co, cn))
    return old_only, new_only


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("new", help="gcovr JSON report of the new (yldot) suite")
    ap.add_argument("--old", help="gcovr JSON report of the suite to compare against")
    ap.add_argument("--src", required=True, help="repository root the reports' paths are relative to")
    ap.add_argument("--out", help="directory for summary.md and old_only.json (default: the new report's)")
    args = ap.parse_args(argv)
    src = Path(args.src).resolve()
    out = Path(args.out) if args.out else Path(args.new).resolve().parent
    out.mkdir(parents=True, exist_ok=True)
    new = load(args.new)
    md = ["# pandf*.F coverage", "", "New report: `{}`".format(args.new), ""]
    rows, acc_new = table(new)
    md += ["## New"] + [""] + rows + [""]
    print("new: lines {}/{} ({}), branches taken {}/{} ({}), executed {} ({})".format(
        acc_new[1], acc_new[0], pct(acc_new[1], acc_new[0]), acc_new[3], acc_new[2], pct(acc_new[3], acc_new[2]),
        acc_new[4], pct(acc_new[4], acc_new[2])))
    if args.old:
        old = load(args.old)
        rows, acc_old = table(old)
        md += ["## Old", "", "Old report: `{}`".format(args.old), ""] + rows + [""]
        print("old: lines {}/{} ({}), branches taken {}/{} ({}), executed {} ({})".format(
            acc_old[1], acc_old[0], pct(acc_old[1], acc_old[0]), acc_old[3], acc_old[2],
            pct(acc_old[3], acc_old[2]), acc_old[4], pct(acc_old[4], acc_old[2])))
        old_only, new_only = diff(new, old)
        maps = {name: SourceMap(src, name) for name in {o[0] for o in old_only}}
        records = []
        for name, n, k, co, cn in old_only:
            sm = maps[name]
            records.append({"file": name, "line": n, "branch": k, "old_count": co, "m_file": sm.mname,
                            "m_line": sm.mline(n), "text": sm.text(n)})
        (out / "old_only.json").write_text(json.dumps(records, indent=1) + "\n")
        lines_old_only = Counter((r["file"], r["line"]) for r in records)
        unmapped = sum(1 for r in records if r["m_line"] is None)
        md += ["## Comparison", "",
               "- branches taken by new: {}, by old: {}".format(acc_new[3], acc_old[3]),
               "- old-only branches: {} on {} lines ({} on unmapped lines); new-only branches: {}".format(
                   len(records), len(lines_old_only), unmapped, len(new_only)), "",
               "### Old-only branches", "",
               "| .m line | .F line | branches (index: old count) | source |", "|---|---|---|---|"]
        for (name, n), _ in sorted(lines_old_only.items()):
            rs = [r for r in records if r["file"] == name and r["line"] == n]
            ml = rs[0]["m_line"]
            md.append("| `{}` | `{}:{}` | {} | `{}` |".format(
                "{}:{}".format(rs[0]["m_file"], ml) if ml else "unmapped", name, n,
                ", ".join("{}: {}".format(r["branch"], r["old_count"]) for r in rs),
                rs[0]["text"].replace("|", "\\|")[:100]))
        gate = "GATE: new branches taken >= old: {}; old-only branches: {} (on {} lines)".format(
            "yes" if acc_new[3] >= acc_old[3] else "no", len(records), len(lines_old_only))
        md += ["", gate]
        print("new-only branches: {}".format(len(new_only)))
        print(gate)
    (out / "summary.md").write_text("\n".join(md) + "\n")
    print("wrote " + str(out / "summary.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
