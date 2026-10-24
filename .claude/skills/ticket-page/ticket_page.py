#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""
Deterministic helpers for the `ticket-page` skill (SKILL.md next to this file). The skill makes the Atlassian calls;
this script only builds and checks text, so a dry run and a real run write the same thing.

  render        The ticket page body: header, Ticket section, the four append-only log sections (the current page's
                entries + any entry of the sent log the page lost + the queue + --entry) and the plan: --plan mirrors
                the working copy (cited by publish date and sha256), --mirrored repeats the copy last published.
                Neither: the skeleton a new page is created with, or the log entries of a page that has no plan yet
                (Plan placeholder kept). For an existing page it needs --current (the page as read) or --local
                --listing (the page is what this worktree last sent), and it refuses a current page that lacks a
                log heading or holds fewer entries than this worktree last sent, and a no-plan render of a page
                that holds a plan.
  ticket        The Ticket section: the ticket's entry in the epic breakdown (heading naming the key), or --text.
  find          A ticket's page id from the state file, the Jira link comment and a complete container listing.
                Exit 3 (no page) only with a complete listing and a readable comment list; 2 = several or can't tell.
  queue         The local outbox and sent log (untracked, in the git dir): --add, --list, --mark-sent.
  state         Per-ticket state: page id, parent id, last version written and its time (modified), published plan
                (sha256, date, title), status.
  verify        The body the last logged create/update call sent (PostToolUse log) equals the rendered file.
  extract-plan  Rebuild the plan (or RCA) working copy from the page's mirror (a fresh worktree has none).
  progress      The epic's `Progress: <EPIC>` page: its skeleton (--new), or its entries + this worktree's epic lines.
  sanitize      stdin -> stdout: local paths masked, secret-like strings refused, a length cap (Jira fallback).

Exit codes: 0 ok; 1 refused (secret-like string, over the cap, verify mismatch); 2 could not run or unsafe input;
3 nothing found (find: no page; ticket: no entry; extract-plan: no plan; verify: no logged call).
Each command's options: ticket_page.py <command> --help.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

SECTIONS = ["Progress", "Validation", "Reviews", "Findings and decisions"]
EPIC_SECTION = "Entries"
EMPTY = "_No entries yet._"
# Every flush re-sends the whole body (the update tool has no partial update): warn above this many characters.
BODY_WARN_CHARS = 25_000
META_KEYS = ["key", "key_url", "summary", "epic", "epic_url", "prd_title", "prd_url", "branch", "status", "updated",
             "skill"]
PLAN_PLACEHOLDER = ("_Not written yet: `plan-feature` mirrors the ticket's plan here (`implement-fix` mirrors its RCA"
                    " under an RCA heading instead)._")
PLAN_BACKFILLED = ("_Not mirrored here yet: this page was created after the ticket was filed (see Backfilled above);"
                   " the plan, if any, is a working copy in the ticket's worktree. The next `publish` mirrors it here._")
ATTRIBUTION = ("> **Posted by an agent** through the owner's Atlassian account. Entries are the agent's unless marked"
               " Owner or Reviewer; an owner decision is marked Owner only when a source records it as the owner's"
               " (attribution rules in `close-epic`).")

# (name, pattern). Only the name is ever printed, never the match.
SECRET_PATTERNS = [
    ("atlassian-token", r"ATATT[0-9A-Za-z_\-=]{20,}"),
    ("github-token", r"\bgh[pousr]_[0-9A-Za-z]{30,}"),
    ("github-fine-grained-token", r"\bgithub_pat_[0-9A-Za-z_]{40,}"),
    ("gitlab-token", r"\bglpat-[0-9A-Za-z_\-]{20,}"),
    ("sk-api-key", r"\bsk-[0-9A-Za-z_\-]{20,}"),
    ("slack-token", r"\bxox[abprs]-[0-9A-Za-z\-]{10,}"),
    ("aws-access-key-id", r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),
    ("google-api-key", r"\bAIza[0-9A-Za-z_\-]{35}"),
    ("jwt", r"\beyJ[0-9A-Za-z_\-]{8,}\.eyJ[0-9A-Za-z_\-]{8,}\.[0-9A-Za-z_\-]{8,}"),
    ("bearer-token", r"(?i)\bbearer\s+[0-9A-Za-z_\-.=]{16,}"),
    ("private-key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("credentials-in-url", r"\b[a-z][a-z0-9+.\-]*://[^\s/:@]+:[^\s/@]+@"),
    ("secret-assignment",
     r"(?i)(password|passwd|secret|api[_-]?key|access[_-]?key|access[_-]?token|auth[_-]?token|token|"
     r"[a-z0-9]+_(token|secret|key|password))[\"']?\s*[:=]\s*[\"']?[^\s\"'`]{8,}"),
]

# Local absolute paths under these roots (workstations and HPC clusters). The look-behind keeps URL paths and relative
# paths; short or common words count as roots only when a path segment follows ("the /p option" stays text).
PATH_ROOTS = r"(?:Users|home|homes|private|tmp|var|Volumes|opt|mnt|srv|root|scratch|gpfs|lustre)"
SHORT_ROOTS = r"(?:global|nfs|work|project|projects|data|p|g|usr/workspace|usr/WS\d+)"
_TAIL = r"[^\s`'\"<>()\[\]{}|,;]"
ABS_PATH = re.compile(r"(?<![\w:/.\-~{}])/(?:" + PATH_ROOTS + r"(?=/|\b)(?:/" + _TAIL + r"*)?|"
                      + SHORT_ROOTS + r"/[\w.\-]" + _TAIL + r"*)")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def die(msg, code=2):
    print("ticket_page: " + msg, file=sys.stderr)
    sys.exit(code)


def today(a):
    return getattr(a, "date", None) or date.today().isoformat()


# ---------------------------------------------------------------- sanitising

def _variants(p):
    """A path and its /tmp <-> /private/tmp, /var <-> /private/var twins (macOS)."""
    p = str(p).rstrip("/")
    out = {p}
    for a, b in (("/private/tmp", "/tmp"), ("/private/var", "/var"), ("/tmp", "/private/tmp"),
                 ("/var", "/private/var")):
        if p == a or p.startswith(a + "/"):
            out.add(b + p[len(a):])
    return sorted(out, key=len, reverse=True)


def sanitize(text, repo):
    """Replace local absolute paths with placeholders ({worktree}, {worktrees}, {home}, {local}/<name>)."""
    repo = Path(repo).resolve()
    text = re.sub(r"\bfile://(?=/)", "\x00", text)  # file:///abs/path: masked like any other absolute path
    for base, ph in ((repo, "{worktree}"), (repo.parent, "{worktrees}"), (Path.home().resolve(), "{home}")):
        for p in _variants(base):
            text = re.sub(r"(?<![\w:/.\-])" + re.escape(p) + r"(?=/|[\s`'\"<>()\[\]{}|,;:]|\.(?:\s|$)|$)", ph, text)

    def other(m):
        parts = [x for x in m.group(0).split("/") if x]
        return "{local}/" + parts[-1] if len(parts) > 1 else "{local}"
    text = ABS_PATH.sub(other, text)
    text = re.sub(r"-(Users|home)-[A-Za-z0-9._]+-", r"-\1-{user}-", text)  # path-derived ids (-Users-<name>-...)
    return text.replace("\x00", "file://")


def refuse_secrets(text, what):
    hits = sorted({name for name, pat in SECRET_PATTERNS if re.search(pat, text)})
    if hits:
        die(f"refused: {what} contains secret-like strings ({', '.join(hits)}); rewrite it", 1)


# ---------------------------------------------------------------- markdown

def split_fences(lines):
    """Yield (line, in_fence) so heading and bullet logic skips fenced code."""
    fence = None
    for ln in lines:
        m = re.match(r"^\s*(```+|~~~+)", ln)
        if m and (fence is None or m.group(1)[0] * 3 == fence):
            fence = m.group(1)[0] * 3 if fence is None else None
            yield ln, True
            continue
        yield ln, fence is not None


def shift_headings(md, by):
    """Demote (by > 0) or promote (by < 0) headings outside fences, kept within levels 1-6. Demoting past h6 is lossy:
    a plan's h5/h6 headings come back from the page as h4."""
    out = []
    for ln, in_fence in split_fences(md.splitlines()):
        m = None if in_fence else re.match(r"^(#{1,6})(\s.*)$", ln)
        out.append("#" * max(1, min(6, len(m.group(1)) + by)) + m.group(2) if m else ln)
    return "\n".join(out)


def demote_below_h2(md):
    """Shift headings so none is H1 or H2: a section must not end at one of its own lines."""
    levels = [len(m.group(1)) for ln, f in split_fences(md.splitlines()) if not f
              for m in [re.match(r"^(#{1,6})\s", ln)] if m]
    return shift_headings(md, max(0, 3 - min(levels))) if levels else md


def norm(s):
    """Comparison key that ignores markdown escaping, emphasis, bullet style, indentation and line wrapping."""
    return re.sub(r"[^0-9a-z]", "", s.lower())


def heading(ln):
    """(level, title) of an H1/H2 line, title stripped of '*' and trailing '#', or (0, None)."""
    m = re.match(r"^(#{1,2})\s+(.*?)\s*#*\s*$", ln)
    return (len(m.group(1)), m.group(2).strip().strip("*").strip()) if m else (0, None)


def entry_blocks(lines):
    """A section's entries: a top-level bullet plus every following line up to the next one (Confluence drops the
    indent of continuation lines, so indentation can't be relied on)."""
    blocks = []
    for ln, in_fence in split_fences(lines):
        if (not in_fence and re.match(r"^[-*+]\s", ln)) or (not blocks and ln.strip()):
            blocks.append([ln])
        elif blocks:
            blocks[-1].append(ln)
    out = ["\n".join(b).rstrip() for b in blocks]
    return [t for t in out if norm(t) != norm(EMPTY)]


def entry_text(e):
    """One entry as a list item; continuation lines indented, a leading '#' outside a fence escaped."""
    out = []
    for i, (ln, in_fence) in enumerate(split_fences(e["text"].strip().splitlines())):
        if i and not in_fence and ln.lstrip().startswith("#"):
            ln = "\\" + ln.lstrip()
        out.append(ln if i == 0 else "  " + ln)
    return f"- **{e['date']}** · {e['source']} · " + "\n".join(out)


def load_json(path):
    """A saved tool result: plain JSON or the MCP content-array form [{"type": "text", "text": "{...}"}]."""
    data = json.loads(Path(path).read_text())
    if isinstance(data, list) and data and all(isinstance(x, dict) and "text" in x for x in data):
        data = json.loads("".join(x["text"] for x in data))
    return data


def load_current(path):
    """The page body as markdown: a markdown file, or a saved fetch or getConfluencePage result (plain or MCP-wrapped
    JSON)."""
    raw = Path(path).read_text()
    try:
        data = json.loads(raw)
    except ValueError:
        return raw
    if isinstance(data, list):
        joined = "".join(x.get("text", "") for x in data if isinstance(x, dict))
        try:
            data = json.loads(joined)
        except ValueError:
            return joined
    if isinstance(data, dict):  # getConfluencePage: {"content": {"nodes": [page]}}; fetch: {"text", "metadata"}
        nodes = data["content"].get("nodes") if isinstance(data.get("content"), dict) else None
        if isinstance(nodes, list) and len(nodes) == 1 and isinstance(nodes[0], dict):
            data = nodes[0]
    body = data.get("body") if isinstance(data, dict) else None
    if body is None and isinstance(data, dict) and "metadata" in data:
        body = data.get("text")
    if isinstance(body, str):
        return body
    die("--current: no markdown page body (read the page with contentFormat \"markdown\")")


def parse_page(md):
    """({section: [entries]}, log headings found, Ticket section or None) for the part of a page before the mirror.
    Only the Ticket heading, the four log headings and the mirror heading are boundaries."""
    cur, seen, ticket = None, set(), []
    lines = {s: [] for s in SECTIONS}
    for ln, in_fence in split_fences(md.splitlines()):
        title = None if in_fence else heading(ln)[1]
        if title in ("Plan", "RCA"):
            break
        if title in SECTIONS or title == "Ticket":
            cur = title
            seen.add(title)
            continue
        if cur == "Ticket":
            ticket.append(ln)
        elif cur:
            lines[cur].append(ln)
    return {s: entry_blocks(lines[s]) for s in SECTIONS}, seen, ("\n".join(ticket).strip() or None)


def plan_hash(text):
    """The published plan's identity: sha256 of its text without trailing whitespace (16 hex digits)."""
    return hashlib.sha256(text.rstrip().encode()).hexdigest()[:16]


def store_dir(repo, outbox=None):
    return Path(outbox) if outbox else Path(git(repo, "rev-parse", "--absolute-git-dir").strip()) / "ticket-page-outbox"


def read_jsonl(p):
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()] if p.exists() else []


def read_state(d, key):
    p = d / f"{key}.state.json"
    return json.loads(p.read_text()) if p.exists() else {}


def write_out(path, text, what):
    refuse_secrets(text, what)
    Path(path).write_text(text)


# ---------------------------------------------------------------- render

def cmd_render(a):
    meta = json.loads(Path(a.meta).read_text())
    missing = [k for k in META_KEYS if not meta.get(k)]
    if missing:
        die("meta.json is missing " + ", ".join(missing))
    key, pid = meta["key"], str(meta.get("page_id") or "")
    skeleton = not (a.plan or a.mirrored)  # no plan yet: a new page, or log entries on a page with only the placeholder
    if skeleton and not pid and not a.ticket:
        die("the skeleton (no --plan/--mirrored) of a new page needs --ticket")
    if pid and not (a.current or a.local):
        die("the page exists (meta has page_id): pass --current (the page as read) or --local --listing <parent listing>")
    d = store_dir(a.repo, a.outbox)
    state = read_state(d, key)
    same_page = bool(pid) and str(state.get("page_id", "")) == pid  # the recorded version belongs to state.page_id
    recorded = state.get("version") if same_page else None

    plan = tip = None
    plan_title = a.plan_title
    if a.plan:  # publish: the working copy as it is now
        src = Path(a.plan) if Path(a.plan).is_absolute() else Path(a.repo) / a.plan
        if not src.is_file():
            die(f"--plan: {src} doesn't exist (in a fresh worktree: extract-plan, or --mirrored)")
        plan, published = src.read_text(), today(a)
    elif a.mirrored:  # any other flush: the copy last published, so the Plan section only moves on publish
        copy = d / f"{key}.plan.md"
        if not copy.exists() or plan_hash(copy.read_text()) != state.get("plan_hash"):
            die(f"--mirrored: no published plan in the store matching the recorded sha256 ({copy}); publish with "
                "--plan, or rebuild it from the page (extract-plan, then state --save-plan)")
        plan, published = copy.read_text(), state.get("plan_published") or "unknown date"
        plan_title = state.get("plan_title") or plan_title
    if plan is not None:
        try:
            tip = git(a.repo, "rev-parse", "--short", "HEAD").strip()
        except subprocess.CalledProcessError:
            pass

    last = d / f"{key}.last-body.md"
    current = a.current
    if a.local:  # the version check: the parent's child listing carries lastModified, never a version
        nodes = []
        for f in a.listing:
            try:
                nodes += load_json(f).get("results") or []
            except (ValueError, AttributeError):
                die(f"--local: {f} is not a saved getConfluencePageDescendants result; read the page and pass --current")
        mod = next((n.get("lastModified") for n in nodes if isinstance(n, dict) and str(n.get("id")) == pid), None)
        mine = state.get("modified") if same_page else None
        if not mod or mod != mine or not recorded or not last.exists():
            die(f"--local: page {pid} was last modified {mod or '(not in the listing)'}, this worktree's last update "
                f"at {mine or 'unknown'}; read the page and pass --current")
        current = last
    logs, ticket = {s: [] for s in SECTIONS}, None
    if current:
        md = load_current(current)
        logs, seen, ticket = parse_page(md)
        if pid and not set(SECTIONS) <= seen:
            die("--current lacks the log heading(s) " + ", ".join(f"'## {s}'" for s in SECTIONS if s not in seen)
                + "; refusing to build a body that would drop their entries (a truncated copy?)")
        if skeleton and pid:  # the placeholder must never replace a published plan
            title, held = page_plan(md)
            if held or (same_page and state.get("plan_hash")):
                die(f"page {pid} holds a published {title or 'plan'}: render with --mirrored (in a fresh worktree: "
                    "extract-plan, then state --save-plan)")

    def merge(entries):
        n = 0
        for e in entries:
            if e["section"] not in SECTIONS:
                die(f"unknown section {e['section']!r}")
            block = entry_text(e)
            if norm(block) not in {norm(x) for x in logs[e["section"]]}:
                logs[e["section"]].append(block)
                n += 1
        return n
    restored = merge(read_jsonl(d / f"{key}.sent.jsonl"))
    # After re-adding its own entries the page must hold everything this worktree last sent: fewer means a truncated
    # copy, an overwrite by another writer, or a person's deliberate removal (--allow-fewer).
    if a.current and same_page and last.exists() and not a.allow_fewer:
        before, _, last_ticket = parse_page(last.read_text())
        fewer = [s for s in SECTIONS if len(logs[s]) < len(before[s])]
        if fewer or (last_ticket and not ticket and not a.ticket):
            die("the page has fewer entries (or lacks the Ticket section) than this worktree last sent: "
                + (", ".join(fewer) or "Ticket") + "; read the page again; if a person removed them on purpose, pass "
                "--allow-fewer")
    extra = [{"section": s, "source": src, "text": sanitize(t, a.repo), "date": today(a)} for s, src, t in a.entry or []]
    added = merge(read_jsonl(d / f"{key}.jsonl") + extra)
    ticket = Path(a.ticket).read_text().strip() if a.ticket else ticket

    status = meta["status"] + (f" ({meta['status_note']})" if meta.get("status_note") else "")
    page_ref = f"[page {pid}]({meta.get('page_url', '')})" if pid else "not yet created"
    header = [f"> **Jira:** [{key}]({meta['key_url']}) - {meta['summary']} · **Epic:** [{meta['epic']}]"
              f"({meta['epic_url']}) · **PRD:** [{meta['prd_title']}]({meta['prd_url']})"]
    if skeleton:
        bf = meta.get("backfilled")
        header += [f"> **Branch:** `{meta['branch']}` · **Plan:** " + ("not mirrored here" if bf else "not written yet"),
                   f"> **Status:** {status} · **Last updated:** {meta['updated']} by {meta['skill']}"]
        if bf:
            header.append(f"> **Backfilled:** {bf} · page created by `{meta['skill']}` after the ticket was filed"
                          + (f" (Jira status then: {meta['jira_status']})" if meta.get("jira_status") else "")
                          + "; the Ticket section is the scope as read then; earlier history is in the Jira comments.")
        header += [ATTRIBUTION, "> This page is the ticket's PIV record" + ("" if bf else ", created when the ticket"
                   " was filed") + ". `plan-feature` mirrors the plan into the Plan section; `execute`, `validate` and"
                   " the review gates add to the four log sections, which are append-only."]
    else:
        what = "RCA" if plan_title == "RCA" else "plan"
        rebuilt = f", rebuilt from {state['plan_source']}" if a.mirrored and state.get("plan_source") else ""
        header += [f"> **Branch:** `{meta['branch']}`" + (f" at `{tip}`" if tip else "") + f" · **{plan_title}:** "
                   f"published {published} (sha256 `{plan_hash(plan)}`{rebuilt}) · **This page:** {page_ref}",
                   f"> **Status:** {status} · **Last updated:** {meta['updated']} by {meta['skill']}", ATTRIBUTION,
                   f"> The {what} is a working document kept outside the repo (never committed); the {plan_title}"
                   f" section is its published copy, replaced only when the {what} is published again (date and"
                   " sha256 above). The four log sections are append-only."]
    body = [x for h in header for x in (h, ">")][:-1] + [""]  # separate quote paragraphs (the import joins them)
    if ticket:
        body += ["## Ticket", "", demote_below_h2(ticket), ""]
    for s in SECTIONS:
        body += [f"## {s}", ""] + (logs[s] or [EMPTY]) + [""]
    if skeleton:
        body += ["## Plan", "", PLAN_BACKFILLED if meta.get("backfilled") else PLAN_PLACEHOLDER, ""]
    else:
        body += [f"## {plan_title}", "", shift_headings(plan.strip(), 2), ""]
    text = sanitize("\n".join(body), a.repo)
    write_out(a.out, text, "the page body")
    print(f"ticket_page: wrote {a.out} ({len(text)} chars; " + ("skeleton" if skeleton else f"{plan_title} sha256 "
          f"{plan_hash(plan)}") + "; " + ", ".join(f"{s}: {len(logs[s])}" for s in SECTIONS)
          + f"; {added} new, {restored} restored from the sent log)")
    if len(text) > BODY_WARN_CHARS:
        print(f"ticket_page: WARNING: the body is {len(text) // 1000} KB (over {BODY_WARN_CHARS // 1000} KB) and every "
              "flush re-sends all of it: send the milestones that fall in this session in one flush (SKILL.md -> When "
              "to flush), and keep log entries to their caps", file=sys.stderr)
    return 0


# ---------------------------------------------------------------- local store

def cmd_queue(a):
    d = store_dir(a.repo, a.outbox)
    tag = ".epic" if a.epic else ""
    box, sent = d / f"{a.key}{tag}.jsonl", d / f"{a.key}{tag}.sent.jsonl"
    if a.add:
        sec, source, text = a.add
        if a.epic:
            sec, source = EPIC_SECTION, f"{a.key} {source}"
        elif sec not in SECTIONS:
            die(f"section must be one of {SECTIONS}")
        text = sanitize(text, a.repo)
        refuse_secrets(text, "the entry")
        d.mkdir(parents=True, exist_ok=True)
        with box.open("a") as f:
            f.write(json.dumps({"section": sec, "source": source, "text": text, "date": today(a)}) + "\n")
    elif a.mark_sent:
        entries = read_jsonl(box)
        if entries:
            with sent.open("a") as f:
                f.writelines(json.dumps(e) + "\n" for e in entries)
            box.unlink()
        print(f"ticket_page: {len(entries)} entries moved to the sent log")
    else:
        for e in read_jsonl(box):
            print(f"[{e['section']}] {entry_text(e)}")
    return 0


def cmd_state(a):
    d = store_dir(a.repo, a.outbox)
    st = read_state(d, a.key)
    if a.set or a.save_plan or a.save_body:
        d.mkdir(parents=True, exist_ok=True)
    if a.save_body:
        (d / f"{a.key}.last-body.md").write_text(Path(a.save_body).read_text())
    if a.save_plan:
        if not a.plan_title:
            die("--save-plan needs --plan-title Plan|RCA (the section the page mirrors it under)")
        text = Path(a.save_plan).read_text()
        (d / f"{a.key}.plan.md").write_text(text)
        st.update(plan_hash=plan_hash(text), plan_published=today(a), plan_title=a.plan_title)
        st.pop("plan_source", None)
    for kv in a.set or []:
        k, sep, v = kv.partition("=")
        if not k or not sep:
            die(f"bad --set {kv!r}, expected NAME=VALUE")
        st[k] = v
    if a.set or a.save_plan:
        (d / f"{a.key}.state.json").write_text(json.dumps(st, indent=1) + "\n")
    print(json.dumps(st, indent=1))
    return 0


# ---------------------------------------------------------------- verify

def cmd_verify(a):
    """Compare the body of the last logged createConfluencePage (--created, by title) or updateConfluencePage (by
    page id) call with the rendered file. The PostToolUse hook logs successful calls only."""
    tool = "createConfluencePage" if a.created else "updateConfluencePage"
    if (a.created and not a.title) or (not a.created and not a.page_id):
        die("verify needs --page-id, or --created --title")
    want = Path(a.body).read_text().rstrip()
    logs = [Path(a.log)] if a.log else []
    for args in (["rev-parse", "--show-toplevel"], ["rev-parse", "--path-format=absolute", "--git-common-dir"]):
        try:
            p = Path(git(a.repo or ".", *args).strip())
            logs.append((p.parent if "--git-common-dir" in args else p) / "logs" / "post_tool_use.jsonl")
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    for logp in dict.fromkeys(x for x in logs if x.exists()):
        for ln in reversed(logp.read_text().splitlines()):
            if tool not in ln:
                continue
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            ti = d.get("tool_input") or {}
            if not str(d.get("tool_name", "")).endswith(tool):
                continue
            if a.created and (ti.get("title") != a.title or (a.parent_id and str(ti.get("parentId")) != a.parent_id)):
                continue
            if not a.created and str(ti.get("pageId")) != a.page_id:
                continue
            resp = json.dumps(d.get("tool_response"))
            m = re.search(r'number\\*"?:\s*(\d+)', resp)
            version = int(m.group(1)) if m else (1 if a.created else None)
            pid = a.page_id or (re.search(r'\\*"id\\*"\s*:\s*\\*"?(\d+)', resp) or [None, "unknown"])[1]
            if not a.created and a.after_version is not None and (version is None or version <= a.after_version):
                print(f"ticket_page: the last logged update of page {pid} returned version {version}, not one after "
                      f"{a.after_version}: the update just made was not logged as successful", file=sys.stderr)
                return 3
            sent = str(ti.get("body", "")).rstrip()
            if sent == want:
                print(f"ticket_page: verified: page {pid} version {version} holds the rendered body ({len(sent)} chars)")
                return 0
            first = next((i for i, (x, y) in enumerate(zip(sent, want)) if x != y), min(len(sent), len(want)))
            print(f"ticket_page: MISMATCH: the {tool} call for page {pid} sent {len(sent)} chars, the rendered body "
                  f"has {len(want)}; first difference at char {first}", file=sys.stderr)
            return 1
    print(f"ticket_page: no logged {tool} call for {a.title or a.page_id}; unverified", file=sys.stderr)
    return 3


# ---------------------------------------------------------------- ticket section

def cmd_ticket(a):
    """The Ticket section: the breakdown entry whose heading names the key (`KEY` in backticks first, else the key
    in a heading that names no other backticked key), or --text; with its source line."""
    if a.breakdown:
        lines = load_current(a.breakdown).splitlines()
        heads = [(i, len(m.group(1)), m.group(2)) for i, (ln, f) in enumerate(split_fences(lines)) if not f
                 for m in [re.match(r"^(#{2,6})\s+(.*)$", ln)] if m]
        tok = r"(?<![A-Za-z0-9-])" + re.escape(a.key) + r"(?![0-9])"
        entries = [h for h in heads if h[1] >= 3]
        found = ([h for h in entries if f"`{a.key}`" in h[2]] or [h for h in entries if re.search(tok, h[2])
                 and not re.search(r"`[A-Za-z][A-Za-z0-9]*-\d+`", h[2])])
        if not found:
            print(f"ticket_page: no entry for {a.key} in {a.breakdown}; use the Jira description (--text)",
                  file=sys.stderr)
            return 3
        if len(found) > 1:
            die(f"several breakdown entries match {a.key}: " + "; ".join(h[2] for h in found))
        i, lvl, title = found[0]
        end = next((j for j, l2, _ in heads if j > i and l2 <= lvl), len(lines))
        text, where = "\n".join(lines[i + 1:end]).strip(), f"the ticket's entry \"{re.sub(r'[`*]', '', title)}\" in "
    elif a.text:
        text, where = Path(a.text).read_text().strip(), ""
    else:
        die("ticket needs --breakdown or --text")
    src = (f"_Scope as read on {today(a)}, when this page was created after the ticket was filed: "
           if a.backfill else "_Scope as filed: ") + where + a.source + "._"
    out = sanitize(src + "\n\n" + demote_below_h2(text) + "\n", a.repo)
    write_out(a.out, out, "the Ticket section")
    print(f"ticket_page: wrote {a.out} ({len(out)} chars)")
    return 0


# ---------------------------------------------------------------- find

def search_hits(path):
    """(hits, total, has_next) from a searchConfluenceUsingCql result, REST form (results[].content, totalSize,
    _links.next) or nodes form (content.nodes, totalCount, pageInfo.hasNextPage)."""
    data = load_json(path)
    if isinstance(data, dict) and isinstance(data.get("content"), dict) and "nodes" in data["content"]:
        c = data["content"]
        hits = [(str(n["id"]), n["title"]) for n in c.get("nodes") or [] if n.get("id") and n.get("title")]
        return hits, c.get("totalCount"), bool((c.get("pageInfo") or {}).get("hasNextPage"))
    if not isinstance(data, dict) or "results" not in data:
        die(f"{path}: not a searchConfluenceUsingCql result")
    hits = []
    for r in data.get("results") or []:
        c = r.get("content", r) if isinstance(r, dict) else {}
        if c.get("id") and (c.get("title") or r.get("title")):
            hits.append((str(c["id"]), c.get("title") or r.get("title")))
    return hits, data.get("totalSize"), bool((data.get("_links") or {}).get("next") or data.get("next"))


def adf_text(n):
    """Atlassian Document Format to the markdown the link and PIV-record patterns expect (strong -> **, code -> `)."""
    if isinstance(n, list):
        return "".join(adf_text(x) for x in n)
    if not isinstance(n, dict):
        return ""
    if n.get("type") == "text":
        marks = {m.get("type") for m in n.get("marks") or []}
        txt = f"`{n.get('text', '')}`" if "code" in marks else n.get("text", "")
        return f"**{txt}**" if "strong" in marks else txt
    if n.get("type") in ("inlineCard", "blockCard"):
        return (n.get("attrs") or {}).get("url", "")
    inner = "\n" if n.get("type") == "hardBreak" else adf_text(n.get("content") or [])
    return inner + ("\n" if n.get("type") in ("paragraph", "heading", "listItem", "blockquote", "codeBlock") else "")


def jira_comments(path, key):
    """(comment bodies as text, problem); problem is set when the list can't be trusted to be complete."""
    data = load_json(path)
    if isinstance(data, dict) and isinstance(data.get("issues"), dict):  # {"issues": {"nodes": [issue]}}
        nodes = [x for x in data["issues"].get("nodes") or [] if x.get("key") in (key, None)]
        if len(nodes) != 1:
            return None, f"{len(nodes)} issues for {key} in the response"
        data = nodes[0]
    block = (data.get("fields") or {}).get("comment") if isinstance(data, dict) else None
    if isinstance(block, dict) and isinstance(block.get("comments"), list):
        comments = block["comments"]
        if isinstance(block.get("total"), int) and block["total"] > len(comments):
            return None, f"the response holds {len(comments)} of {block['total']} comments (paged); read them all"
    elif isinstance(data, dict) and isinstance(data.get("comments"), list):
        comments = data["comments"]
    else:
        return None, "no comment list (read the issue with fields [\"comment\"])"
    out = []
    for c in comments:
        b = c.get("body")
        if not (isinstance(b, str) or (isinstance(b, dict) and b.get("type") == "doc")):
            return None, f"comment {c.get('id')} has a body in an unknown form"
        out.append(b if isinstance(b, str) else adf_text(b))
    return out, None


def cmd_find(a):
    """Exit 0 found (prints the id), 3 none (only with the evidence: a complete listing and a readable comment list;
    --fallback: the comment list), 2 several or can't tell: stop and report, never treat it as none."""
    report, gone = {"key": a.key}, set(a.gone or [])

    def done(code, msg):
        print(json.dumps(report, indent=1))
        print(f"ticket_page: {msg}", file=sys.stderr)
        return code
    recorded = {str(a.state_id): ["state file"]} if a.state_id else {}
    linked = set()
    if a.comments:
        bodies, problem = jira_comments(a.comments, a.key)
        if problem:
            report["reason"] = problem
            return done(2, f"can't tell from the comments: {problem}")
        piv = sum(1 for b in bodies if b.lstrip().startswith("**PIV record"))
        report.update(piv_record_comments=piv, piv_cap_reached=piv >= 8)
        for b in bodies:
            m = re.match(r"\s*\**(?:Ticket|Plan) page:\**.*?Confluence page id\s*`?(\d+)`?", b, re.S)
            if m:
                recorded.setdefault(m.group(1), []).append("Jira link comment")
                linked.add(m.group(1))
    if a.fallback:
        if not a.comments:
            return done(2, "--fallback needs --comments (the getJiraIssue result with all comments)")
        n = report["piv_record_comments"]
        return done(0 if n else 3, f"{a.key} has {n} PIV record comment(s)")
    listed, totals, last_pages = [], [], 0
    for sp in a.search or []:
        hits, total, has_next = search_hits(sp)
        listed += hits
        totals += [total] if total is not None else []
        last_pages += 0 if has_next else 1
    complete = bool(a.search) and last_pages > 0 and (not totals or len(dict.fromkeys(listed)) >= max(totals))
    if a.search and not complete:
        report["reason"] = "incomplete container listing (a further page is linked, or fewer results than the total)"
        return done(2, "can't tell from an incomplete listing: follow next and pass every page")
    mine = sorted({i for i, t in listed if t.startswith(f"Plan: {a.key} - ") and i not in gone})
    recorded = {i: v for i, v in recorded.items() if i not in gone}
    report["recorded"] = recorded
    if len(mine) > 1:
        report["listed"] = mine
        return done(2, f"several pages for {a.key} under the container: stop and ask; never pick one silently")
    if mine or len(recorded) == 1:
        pid = mine[0] if mine else next(iter(recorded))
        report["page_id"] = pid
        if a.comments:
            report["missing_link_comment"] = pid not in linked
        stale = [i for i in recorded if i != pid]
        if stale:
            report["stale_records"] = stale
            report["note"] = (f"the listed page {pid} wins; confirm each stale id with CQL id = <id>: gone -> fine "
                              "(--gone <id> drops it); still exists -> two pages: stop and ask")
        if not mine and a.search:
            report["not_listed"] = True
            report["note"] = (f"page {pid} is recorded but not under this container: confirm with CQL id = {pid}; "
                              f"exists -> use it (a moved ticket keeps its page); gone -> find again with --gone {pid}")
        return done(0, f"page {pid}")
    if recorded:
        return done(2, f"several recorded ids for {a.key} ({', '.join(recorded)}) and none listed: stop and ask")
    if not a.search or a.comments is None:
        report["reason"] = "no container listing" if not a.search else "no comments"
        return done(2, "can't conclude that there is no page without both --search and --comments")
    return done(3, f"no page for {a.key}")


# ---------------------------------------------------------------- extract-plan, progress, sanitize

def page_plan(md):
    """(title, body) of the page's Plan or RCA section; body is "" while it holds a placeholder (no plan mirrored)."""
    lines, start, title = md.splitlines(), None, None
    for i, (ln, in_fence) in enumerate(split_fences(lines)):
        lvl, t = (0, None) if in_fence else heading(ln)
        if lvl == 2 and t in ("Plan", "RCA"):
            start, title = i + 1, t
            break
    body = "\n".join(lines[start:]).strip() if start is not None else ""
    if norm(body).startswith((norm("_Not written yet"), norm("_Not mirrored here yet"))):
        body = ""
    return title, body


def cmd_extract_plan(a):
    title, body = page_plan(load_current(a.current))
    if not body:
        print("ticket_page: the page has no plan mirrored yet", file=sys.stderr)
        return 3
    text = shift_headings(body, -2)
    Path(a.out).write_text(text.rstrip() + "\n")
    print(f"ticket_page: wrote {a.out} ({title} section rebuilt from the page; local paths come back as placeholders). "
          f"Record it with: state --save-plan {a.out} --plan-title {title}")
    return 0


def cmd_progress(a):
    if a.new:
        meta = json.loads(Path(a.meta).read_text())
        missing = [k for k in ("epic", "epic_url", "prd_title", "prd_url") if not meta.get(k)]
        if missing:
            die("meta.json is missing " + ", ".join(missing))
        text = "\n".join([
            f"> **Epic:** [{meta['epic']}]({meta['epic_url']}) · **PRD:** [{meta['prd_title']}]({meta['prd_url']})",
            ">", "> **Posted by an agent** through the owner's Atlassian account. The epic's progress log: one dated line"
            " per ticket milestone and per owner decision (marked Owner only with its source), appended by the"
            " ticket-page skill. Append-only; `close-epic` reads it.", "", f"## {EPIC_SECTION}", "", EMPTY, ""])
        write_out(a.out, sanitize(text, a.repo or "."), "the page body")
        print(f"ticket_page: wrote {a.out} (Progress page skeleton)")
        return 0
    if not (a.repo and a.key and a.current):
        die("progress needs --new --meta, or --repo --key --current")
    head, entries, seen = [], [], False
    for ln, in_fence in split_fences(load_current(a.current).splitlines()):
        if not in_fence and heading(ln)[1] == EPIC_SECTION:
            seen = True
            continue
        (entries if seen else head).append(ln)
    if not seen:
        die(f"--current lacks the '## {EPIC_SECTION}' heading; refusing to build a body that would drop its entries")
    have = entry_blocks(entries)
    d = store_dir(a.repo, a.outbox)
    new = 0
    for e in read_jsonl(d / f"{a.key}.epic.sent.jsonl") + read_jsonl(d / f"{a.key}.epic.jsonl"):
        if norm(entry_text(e)) not in {norm(x) for x in have}:
            have.append(entry_text(e))
            new += 1
    text = "\n".join(head).rstrip() + f"\n\n## {EPIC_SECTION}\n\n" + "\n".join(have or [EMPTY]) + "\n"
    write_out(a.out, sanitize(text, a.repo), "the page body")
    print(f"ticket_page: wrote {a.out} ({len(have)} entries, {new} added from this worktree)")
    return 0


def cmd_sanitize(a):
    text = sanitize(sys.stdin.read(), a.repo)
    refuse_secrets(text, "the text")
    sys.stdout.write(text)
    if a.max_chars and len(text) > a.max_chars:
        die(f"{len(text)} chars is over the cap of {a.max_chars}; summarise", 1)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    common = {"repo": dict(required=True), "key": dict(required=True), "date": {}, "out": dict(required=True),
              "outbox": dict(help="store directory (default <git dir>/ticket-page-outbox)")}

    def cmd(name, *opts):
        p = sub.add_parser(name)
        for o in opts:
            p.add_argument("--" + o, **common[o])
        return p
    r = cmd("render", "repo", "outbox", "date", "out")
    g = r.add_mutually_exclusive_group()
    g.add_argument("--plan", help="the plan (or RCA) working copy to publish (absolute, or relative to --repo)")
    g.add_argument("--mirrored", action="store_true", help="repeat the copy last published (any flush but publish)")
    r.add_argument("--plan-title", default="Plan", choices=["Plan", "RCA"])
    r.add_argument("--meta", required=True, help="meta.json: " + ", ".join(META_KEYS)
                   + "; optional page_id, page_url, status_note, backfilled, jira_status")
    r.add_argument("--ticket", help="the Ticket section (from: ticket); default: carried over from the page")
    c = r.add_mutually_exclusive_group()
    c.add_argument("--current", help="the page as read (markdown, or the saved fetch or getConfluencePage result)")
    c.add_argument("--local", action="store_true", help="the page is what this worktree last sent (needs --listing)")
    r.add_argument("--listing", action="append", help="with --local: the getConfluencePageDescendants result of the "
                   "page's parent (one per page of results); its lastModified must equal state.modified")
    r.add_argument("--allow-fewer", action="store_true", help="a deliberate correction that removes entries")
    r.add_argument("--entry", nargs=3, action="append", metavar=("SECTION", "SOURCE", "TEXT"), help="dry run")
    q = cmd("queue", "repo", "key", "outbox", "date")
    qg = q.add_mutually_exclusive_group()
    qg.add_argument("--add", nargs=3, metavar=("SECTION", "SOURCE", "TEXT"))
    qg.add_argument("--list", action="store_true")
    qg.add_argument("--mark-sent", action="store_true")
    q.add_argument("--epic", action="store_true", help="the epic Progress page's queue (SECTION is ignored: pass -)")
    s = cmd("state", "repo", "key", "outbox", "date")
    s.add_argument("--set", nargs="+", metavar="NAME=VALUE")
    s.add_argument("--save-body", metavar="BODY", help="record BODY as the last body sent (after a verified update)")
    s.add_argument("--save-plan", metavar="FILE", help="record FILE as the published plan (needs --plan-title)")
    s.add_argument("--plan-title", choices=["Plan", "RCA"])
    v = cmd("verify")
    v.add_argument("--body", required=True)
    v.add_argument("--page-id")
    v.add_argument("--after-version", type=int, help="the version checked before the update")
    v.add_argument("--created", action="store_true", help="check the last createConfluencePage call with --title")
    v.add_argument("--title")
    v.add_argument("--parent-id")
    v.add_argument("--log", help="the PostToolUse log (default: logs/post_tool_use.jsonl of the checkout)")
    v.add_argument("--repo")
    t = cmd("ticket", "repo", "key", "date", "out")
    t.add_argument("--breakdown", help="the epic breakdown (the page as read, or spec's working copy)")
    t.add_argument("--text", help="file with the scope text (the Jira description) when the breakdown has no entry")
    t.add_argument("--source", required=True, help="where the text comes from, e.g. 'the Jira description of <KEY>'")
    t.add_argument("--backfill", action="store_true", help="the page is made after the ticket was filed")
    f = cmd("find", "key")
    f.add_argument("--state-id", help="the page id in this worktree's state file")
    f.add_argument("--comments", help="the getJiraIssue result with all comments")
    f.add_argument("--search", action="append", help="a searchConfluenceUsingCql result (one per page of results)")
    f.add_argument("--gone", action="append", help="an id CQL confirmed deleted")
    f.add_argument("--fallback", action="store_true", help="Jira fallback: does a PIV record comment exist?")
    x = cmd("extract-plan", "out")
    x.add_argument("--current", required=True)
    p = cmd("progress", "outbox", "date", "out")
    p.add_argument("--new", action="store_true", help="the skeleton of a new Progress page (needs --meta)")
    p.add_argument("--meta")
    p.add_argument("--repo")
    p.add_argument("--key")
    p.add_argument("--current")
    z = cmd("sanitize", "repo")
    z.add_argument("--max-chars", type=int, default=1500)
    a = ap.parse_args()
    if a.cmd == "render" and a.local and not a.listing:
        die("--local needs --listing (the parent's getConfluencePageDescendants result)")
    try:
        return {"render": cmd_render, "queue": cmd_queue, "state": cmd_state, "verify": cmd_verify,
                "ticket": cmd_ticket, "find": cmd_find, "extract-plan": cmd_extract_plan, "progress": cmd_progress,
                "sanitize": cmd_sanitize}[a.cmd](a)
    except subprocess.CalledProcessError as e:
        die(f"git failed: {(e.stderr or '').strip() or e}")


if __name__ == "__main__":
    sys.exit(main())
