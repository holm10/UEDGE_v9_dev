#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""
Drift check: are the AI layer's code references still true?

CLAUDE.md, .claude/context/*.md, .claude/agents/*.md and .claude/skills/*/SKILL.md cite code as
`path:line`, `path:a-b` or `path:a,b,c`, and name files as `path/to/file.ext`. Tickets move that code. This
script finds the references that a change has made wrong, so the fix ships on the same ticket
(`.claude/context/branching.md`, trailer `AI-layer: code-facts`).

How it knows: `.claude/context/refs.lock.json` stores, for every cited `file:line`, the text of that line
when someone last checked the reference by hand. A reference is

  OK       the cited line still has the locked text;
  MOVED    the locked text now sits on exactly one other line (`--fix` rewrites the number in the doc);
  STALE    the locked text is gone. The claim must be re-checked by a person or agent, then `--update`;
  BROKEN   the file is missing, or the line is past the end of the file;
  NEW      the reference isn't in the lock yet. Check it, then `--update`;
  MISSING  a backticked repo path (no line number) that doesn't exist.

Usage
  uv run .claude/hooks/check_context_refs.py                    # check everything (exit 1 on any problem)
  uv run .claude/hooks/check_context_refs.py --fix              # rewrite MOVED line numbers in the docs
  uv run .claude/hooks/check_context_refs.py --update           # accept current text for all refs (after review)
  uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop
        # also list which AI-layer docs cite files changed since that base (working tree included)

Exit 0 = clean, 1 = problems, 2 = could not run.
"""

import argparse
import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / ".claude/context/refs.lock.json"
DOC_GLOBS = ["CLAUDE.md", ".claude/context/*.md", ".claude/agents/*.md", ".claude/skills/*/SKILL.md"]

EXT = r"(?:m|v|F|F90|f|py|c|h|yml|yaml|toml|json|md|pack|cfg|txt)"
PATH = rf"(?:[A-Za-z0-9_.-]+/)*(?:[A-Za-z0-9_.-]+\.{EXT}|Makefile\.[A-Za-z]+)"
# `path:12`, `path:12-30`, `path:12,14,20` (inside or outside backticks)
REF = re.compile(rf"(?<![A-Za-z0-9_./-])(?P<path>{PATH}):(?P<nums>\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*)")
# a bare `:12` reference (ambiguous: which file?)
BARE = re.compile(r"`:(\d+)")
# backticked path without line number
TICKPATH = re.compile(rf"`(?P<path>{PATH})`")
# paths that legitimately live outside this checkout or are created later (.claude/work/ and the legacy
# working-document paths are local and untracked: .claude/context/branching.md)
EXTERNAL = ("pytests/", "../", "./", "~", "docs/", ".claude/work/", ".claude/plans/", ".claude/execution-reports/",
            ".claude/system-reviews/", ".claude/code-reviews/", "logs/", "build/", "upstream/")


def docs():
    out = []
    for g in DOC_GLOBS:
        out += sorted(glob.glob(str(ROOT / g)))
    return [Path(p) for p in out]


def resolve(path: str):
    """Return a repo-relative path for a cited path, or None if it cannot be found."""
    if (ROOT / path).is_file():
        return path
    if "/" not in path:  # bare file name: accept a unique match
        hits = [p for p in ROOT.glob(f"**/{path}") if ".git" not in p.parts and "build" not in p.parts]
        if len(hits) == 1:
            return str(hits[0].relative_to(ROOT))
    return None


def numbers(spec: str):
    """'12-30,40' -> [(12, 30), (40, 40)]."""
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out.append((int(a), int(b or a)))
    return out


_cache = {}


def lines_of(path):
    if path not in _cache:
        _cache[path] = (ROOT / path).read_text(errors="replace").splitlines()
    return _cache[path]


def norm(text: str) -> str:
    return " ".join(text.split())


def scan():
    """Yield (doc, lineno, match, resolved_path) for every line reference."""
    for doc in docs():
        rel = str(doc.relative_to(ROOT))
        for i, line in enumerate(doc.read_text().splitlines(), 1):
            for m in REF.finditer(line):
                yield rel, i, m, resolve(m.group("path"))


def check(lock, changed=None):
    problems, moved, seen = [], [], set()
    for doc, i, m, path in scan():
        where = f"{doc}:{i}"
        cited = m.group(0)
        if path is None:
            if not m.group("path").startswith(EXTERNAL):
                problems.append(("BROKEN", where, cited, "file not found"))
            continue
        lines = lines_of(path)
        for a, b in numbers(m.group("nums")):
            for n in {a, b}:
                key = f"{path}:{n}"
                seen.add(key)
                if n > len(lines):
                    problems.append(("BROKEN", where, cited, f"{path} has only {len(lines)} lines"))
                    continue
                want = lock.get(key)
                have = norm(lines[n - 1])
                if want is None:
                    problems.append(("NEW", where, cited, f"line {n}: {have[:70]!r}"))
                elif want != have:
                    hits = [k for k, t in enumerate(lines, 1) if norm(t) == want]
                    if len(hits) == 1:
                        moved.append((doc, i, path, n, hits[0]))
                        problems.append(("MOVED", where, cited, f"line {n} -> {hits[0]}"))
                    else:
                        problems.append(("STALE", where, cited, f"line {n} was {want[:60]!r}, now {have[:60]!r}"))
    for doc in docs():
        rel = str(doc.relative_to(ROOT))
        for i, line in enumerate(doc.read_text().splitlines(), 1):
            for m in BARE.finditer(line):
                problems.append(("BROKEN", f"{rel}:{i}", m.group(0) + "`", "bare line number; write path:line"))
            for m in TICKPATH.finditer(line):
                p = m.group("path")
                if "/" in p and not p.startswith(EXTERNAL) and "<" not in p and "*" not in p \
                        and not (ROOT / p).exists():
                    problems.append(("MISSING", f"{rel}:{i}", p, "path does not exist"))
    return problems, moved, seen


def fix(moved):
    """Rewrite moved line numbers in the docs (only exact `path:N` occurrences on the reporting line)."""
    by_line = {}
    for doc, i, path, old, new in moved:
        by_line.setdefault((doc, i), []).append((path, old, new))
    for (doc, i), items in by_line.items():
        p = ROOT / doc
        text = p.read_text().splitlines(keepends=True)
        line = text[i - 1]

        def repl(m):
            path = resolve(m.group("path"))
            parts = []
            for part in m.group("nums").split(","):
                a, sep, b = part.partition("-")
                mp = {o: n for (pp, o, n) in items if pp == path}
                a2 = str(mp.get(int(a), int(a)))
                b2 = str(mp.get(int(b), int(b))) if b else ""
                parts.append(a2 + (sep + b2 if b else ""))
            return f"{m.group('path')}:{','.join(parts)}"

        text[i - 1] = REF.sub(repl, line)
        p.write_text("".join(text))


def git(args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def changed_files(base):
    files = set(git(["diff", "--name-only", base]).split())
    files |= set(git(["ls-files", "--others", "--exclude-standard"]).split())
    return files


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fix", action="store_true", help="rewrite MOVED line numbers in the docs")
    ap.add_argument("--update", action="store_true", help="lock the current text of every reference")
    ap.add_argument("--changed", metavar="BASE", help="list AI-layer docs citing files changed since BASE")
    a = ap.parse_args()
    try:
        lock = json.loads(LOCK.read_text()) if LOCK.exists() else {}
    except (OSError, ValueError) as e:
        print(f"cannot read {LOCK}: {e}", file=sys.stderr)
        return 2

    if a.update:
        new = {}
        for doc, i, m, path in scan():
            if path is None:
                continue
            lines = lines_of(path)
            for x, y in numbers(m.group("nums")):
                for n in {x, y}:
                    if n <= len(lines):
                        new[f"{path}:{n}"] = norm(lines[n - 1])
        LOCK.write_text(json.dumps(dict(sorted(new.items())), indent=1) + "\n")
        print(f"locked {len(new)} references in {LOCK.relative_to(ROOT)}")
        return 0

    problems, moved, seen = check(lock)
    if a.fix and moved:
        fix(moved)
        for _doc, _i, path, old, new in moved:  # the locked text travels with the line
            lock[f"{path}:{new}"] = lock[f"{path}:{old}"]
        LOCK.write_text(json.dumps(dict(sorted(lock.items())), indent=1) + "\n")
        _cache.clear()
        print(f"fixed {len(moved)} moved line number(s) in the docs and the lock")
        problems, moved, seen = check(lock)

    if a.changed:
        try:
            files = changed_files(a.changed)
        except subprocess.CalledProcessError as e:
            print(e.stderr.strip(), file=sys.stderr)
            return 2
        cites = {}
        for doc, i, m, path in scan():
            if path in files:
                cites.setdefault(doc, set()).add(path)
        for doc in docs():
            rel = str(doc.relative_to(ROOT))
            for line in doc.read_text().splitlines():
                for m in TICKPATH.finditer(line):
                    if m.group("path") in files:
                        cites.setdefault(rel, set()).add(m.group("path"))
        if cites:
            print(f"AI-layer docs that cite files changed since {a.changed} (re-read them; update facts with "
                  f"the 'AI-layer: code-facts' trailer):")
            for doc in sorted(cites):
                print(f"  {doc}: " + ", ".join(sorted(cites[doc])))
        else:
            print(f"No AI-layer doc cites a file changed since {a.changed}.")

    for kind, where, cited, info in problems:
        print(f"{kind:8s} {where}  {cited}  ({info})")
    unused = sorted(set(lock) - seen)
    if unused:
        print(f"note: {len(unused)} lock entries are no longer cited (pruned on next --update)")
    print("OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
