#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""
Deterministic helpers for the `ticket-page` skill (`.claude/skills/ticket-page/SKILL.md`).

The skill does the Atlassian calls; this script only builds text, so a dry run and a real run write the same thing.

  render    Build the ticket page body: header, the four log sections (kept from the current page, plus any queued
            entries not yet on it), and the plan mirrored from a *committed* revision of the plan file.
  queue     Add an entry to the ticket's outbox, list it, or clear it after a successful write. The outbox lives
            in the worktree's git directory (untracked, per worktree), so an entry survives a failed Atlassian
            write and the next skill run retries it.
  sanitize  Read text on stdin, replace local absolute paths, refuse secret-like strings, enforce a length cap
            (for Jira comments of the no-epic fallback).

Usage:
  ticket_page.py render --repo <worktree> --plan <repo-relative plan path> [--rev HEAD] --meta meta.json
                        [--current current.md] [--entry SECTION SOURCE TEXT]... [--outbox DIR] --out body.md
  ticket_page.py queue  --repo <worktree> --key KEY [--outbox DIR]
                        (--add SECTION SOURCE TEXT [--date YYYY-MM-DD] | --list | --clear)
  ticket_page.py sanitize --repo <worktree> [--max-chars 1500] < text > text

meta.json keys: key, key_url, summary, epic, epic_url, prd_title, prd_url, branch, status, updated, skill,
                page_id (optional), page_url (optional).

Exit codes: 0 ok, 1 refused (secret-like string, or the text is over the cap), 2 could not run.
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

SECTIONS = ["Progress", "Validation", "Reviews", "Findings and decisions"]
PLAN_HEADING = "Plan"
EMPTY = "_No entries yet._"

SECRET_PATTERNS = [
    r"ATATT[0-9A-Za-z_\-=]{20,}",          # Atlassian API token
    r"gh[pousr]_[0-9A-Za-z]{30,}",          # GitHub token
    r"sk-[0-9A-Za-z_\-]{20,}",              # API keys of the sk- form
    r"xox[abprs]-[0-9A-Za-z\-]{10,}",       # Slack token
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*\S{6,}",
]


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def sanitize(text, repo):
    """Replace local absolute paths with placeholders that survive Confluence's markdown import."""
    repo = Path(repo).resolve()
    for p, ph in ((str(repo), "{worktree}"), (str(repo.parent), "{worktrees}")):
        text = text.replace(p + "/", ph + "/").replace(p, ph)
    home = str(Path.home())
    text = text.replace(home + "/", "{home}/").replace(home, "{home}")
    # Any other user or temp path: keep only the last component.
    text = re.sub(r"(/Users/|/home/|/private/var/folders/|/var/folders/)[^\s`'\")\]|]*/([^\s`'\")\]|/]+)",
                  r"{local}/\2", text)
    return text


def secret_hits(text):
    return [m.group(0)[:12] + "..." for pat in SECRET_PATTERNS for m in re.finditer(pat, text)]


def split_fences(lines):
    """Yield (line, in_fence) so heading logic skips fenced code."""
    fence = None
    for ln in lines:
        m = re.match(r"^\s*(```+|~~~+)", ln)
        if m:
            tok = m.group(1)[0] * 3
            if fence is None:
                fence = tok
                yield ln, True
                continue
            if tok == fence:
                fence = None
                yield ln, True
                continue
        yield ln, fence is not None


def demote(md, by=2):
    out = []
    for ln, in_fence in split_fences(md.splitlines()):
        if not in_fence:
            m = re.match(r"^(#{1,6})(\s.*)$", ln)
            if m:
                ln = "#" * min(6, len(m.group(1)) + by) + m.group(2)
        out.append(ln)
    return "\n".join(out)


def parse_sections(md):
    """Return {section: [lines]} for the log sections of a current page body (markdown)."""
    found, cur = {}, None
    for ln, in_fence in split_fences(md.splitlines()):
        if not in_fence:
            m = re.match(r"^#{1,2}\s+(.*?)\s*#*\s*$", ln)
            if m and len(re.match(r"^(#+)", ln).group(1)) <= 2:
                title = m.group(1).strip().strip("*").strip()
                cur = title if title in SECTIONS else None
                if title == PLAN_HEADING or title.startswith(PLAN_HEADING + " "):
                    break
                if cur is not None:
                    found.setdefault(cur, [])
                continue
        if cur is not None:
            found[cur].append(ln)
    for k, v in found.items():
        while v and not v[0].strip():
            v.pop(0)
        while v and not v[-1].strip():
            v.pop()
        found[k] = [ln for ln in v if norm(ln) != norm(EMPTY)]
    return found


def norm(s):
    """Comparison key that ignores markdown escaping and bullet/emphasis style changes from a round trip."""
    return re.sub(r"[^0-9a-z]", "", s.lower())


def outbox_path(repo, key, outbox=None):
    base = Path(outbox) if outbox else Path(git(repo, "rev-parse", "--absolute-git-dir").strip()) / "ticket-page-outbox"
    return base / f"{key}.jsonl"


def read_outbox(repo, key, outbox=None):
    p = outbox_path(repo, key, outbox)
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


def entry_line(e):
    text = e["text"].strip().replace("\n", "\n  ")
    return f"- **{e['date']}** · {e['source']} · {text}"


def cmd_render(a):
    meta = json.loads(Path(a.meta).read_text())
    tip = git(a.repo, "rev-parse", "--short", a.rev).strip()
    # The commit that last changed the plan, so the header doesn't move when only other files change.
    sha = git(a.repo, "log", "-1", "--format=%h", a.rev, "--", a.plan).strip() or tip
    plan = git(a.repo, "show", f"{a.rev}:{a.plan}")
    current = Path(a.current).read_text() if a.current else ""
    try:  # also accept the getConfluencePage tool result (JSON with a markdown "body"), e.g. one saved to a file
        cur_json = json.loads(current)
        if isinstance(cur_json, dict) and isinstance(cur_json.get("body"), str):
            current = cur_json["body"]
    except ValueError:
        pass
    logs = parse_sections(current)
    extra = [{"section": sec, "source": src, "text": sanitize(txt, a.repo), "date": a.date or date.today().isoformat()}
             for sec, src, txt in (a.entry or [])]
    for e in read_outbox(a.repo, meta["key"], a.outbox) + extra:
        sec = e["section"]
        if sec not in SECTIONS:
            print(f"ticket_page: unknown section {sec!r}", file=sys.stderr)
            return 2
        lines = logs.setdefault(sec, [])
        line = entry_line(e)
        if norm(line) not in {norm(x) for x in lines}:
            lines.append(line)
    page_ref = (f"[page {meta['page_id']}]({meta['page_url']})" if meta.get("page_id") else "not yet created")
    header = [
        f"> **Jira:** [{meta['key']}]({meta['key_url']}) - {meta['summary']} · **Epic:** [{meta['epic']}]({meta['epic_url']})"
        f" · **PRD:** [{meta['prd_title']}]({meta['prd_url']})",
        f"> **Branch:** `{meta['branch']}` at `{tip}` · **Plan:** `{a.plan}` as of `{sha}` · **This page:** {page_ref}",
        f"> **Status:** {meta['status']} · **Last updated:** {meta['updated']} by {meta['skill']}",
        "> **Posted by an agent** through the owner's Atlassian account. Entries are the agent's unless marked"
        " Owner or Reviewer; an owner decision is marked Owner only when a source records it as the owner's"
        " (attribution rules in `close-epic`).",
        "> The plan file in the repo is the source of truth; the Plan section mirrors it as of the commit above"
        " (local paths shown as `{worktree}`, `{local}`). The four log sections are append-only.",
    ]
    # No H1: Confluence shows the page title (`Plan: <KEY> - <summary>`) above the body.
    # Confluence's markdown import joins consecutive quote lines into one paragraph: separate them.
    body = [x for h in header for x in (h, ">")][:-1] + [""]
    for sec in SECTIONS:
        body += [f"## {sec}", ""] + (logs.get(sec) or [EMPTY]) + [""]
    body += [f"## {PLAN_HEADING}", "", demote(plan.strip(), 2), ""]
    text = sanitize("\n".join(body), a.repo)
    hits = secret_hits(text)
    if hits:
        print("ticket_page: refused, secret-like strings: " + ", ".join(hits), file=sys.stderr)
        return 1
    Path(a.out).write_text(text)
    print(f"ticket_page: wrote {a.out} ({len(text)} chars; plan {a.plan} at {sha}; "
          + ", ".join(f"{s}: {len(logs.get(s, []))}" for s in SECTIONS) + ")")
    return 0


def cmd_queue(a):
    p = outbox_path(a.repo, a.key, a.outbox)
    if a.add:
        sec, source, text = a.add
        if sec not in SECTIONS:
            print(f"ticket_page: section must be one of {SECTIONS}", file=sys.stderr)
            return 2
        text = sanitize(text, a.repo)
        if secret_hits(text):
            print("ticket_page: refused, secret-like string in the entry", file=sys.stderr)
            return 1
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            f.write(json.dumps({"section": sec, "source": source, "text": text,
                                "date": a.date or date.today().isoformat()}) + "\n")
    elif a.clear:
        if p.exists():
            p.unlink()
    for e in read_outbox(a.repo, a.key, a.outbox):
        print(f"[{e['section']}] {entry_line(e)}")
    return 0


def cmd_sanitize(a):
    text = sanitize(sys.stdin.read(), a.repo)
    hits = secret_hits(text)
    if hits:
        print("ticket_page: refused, secret-like strings: " + ", ".join(hits), file=sys.stderr)
        return 1
    sys.stdout.write(text)
    if a.max_chars and len(text) > a.max_chars:
        print(f"\nticket_page: {len(text)} chars is over the cap of {a.max_chars}; summarise", file=sys.stderr)
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("--repo", required=True)
    r.add_argument("--plan", required=True)
    r.add_argument("--rev", default="HEAD")
    r.add_argument("--meta", required=True)
    r.add_argument("--current")
    r.add_argument("--entry", nargs=3, action="append", metavar=("SECTION", "SOURCE", "TEXT"),
                   help="an entry to add without queueing it (dry run)")
    r.add_argument("--date")
    r.add_argument("--outbox", help="outbox directory (default: <git dir>/ticket-page-outbox)")
    r.add_argument("--out", required=True)
    q = sub.add_parser("queue")
    q.add_argument("--repo", required=True)
    q.add_argument("--key", required=True)
    g = q.add_mutually_exclusive_group(required=True)
    g.add_argument("--add", nargs=3, metavar=("SECTION", "SOURCE", "TEXT"))
    g.add_argument("--list", action="store_true")
    g.add_argument("--clear", action="store_true")
    q.add_argument("--date")
    q.add_argument("--outbox", help="outbox directory (default: <git dir>/ticket-page-outbox)")
    s = sub.add_parser("sanitize")
    s.add_argument("--repo", required=True)
    s.add_argument("--max-chars", type=int, default=1500)
    a = ap.parse_args()
    try:
        return {"render": cmd_render, "queue": cmd_queue, "sanitize": cmd_sanitize}[a.cmd](a)
    except subprocess.CalledProcessError as e:
        print(f"ticket_page: git failed: {e.stderr.strip()}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
