#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""
Deterministic helpers for the `ticket-page` skill (`.claude/skills/ticket-page/SKILL.md`).

The skill makes the Atlassian calls; this script only builds and checks text, so a dry run and a real run write the
same thing.

  render    Build the ticket page body: header, the Ticket section (the ticket's scope as filed), the four log
            sections and the plan (or RCA): --plan mirrors the working copy (a local, untracked file, identified by
            its sha256 and the publish date; no commit involved), --mirrored repeats the copy last published (kept in
            the store by `state --save-plan`), so the Plan section only moves on publish. Without either it builds
            the skeleton
            that `spec` creates a page with (Ticket section, empty logs, a Plan placeholder); it never rewrites an
            existing page except a legacy stub. Log sections = the current page's entries, plus any entry of the
            local sent log that the page lost, plus the outbox, plus --entry. The Ticket section is --ticket, else
            the current page's (or the last body's) carried over. For an existing page it refuses (exit 2) unless it
            gets a current page with all four log headings and at least the entries (and the Ticket section) this
            worktree last sent, or --local with the version this worktree last wrote, or --new-page with exactly
            the stub of a page just created.
  ticket    Build the Ticket section: the ticket's entry in the epic breakdown (a local file: the breakdown page as
            read from Confluence, or spec's working copy of what it published; found by key), or a given text (the
            Jira description), with its source.
  progress  The epic's `Progress: <EPIC>` page: its skeleton (--new), or its entries plus this worktree's queued
            epic entries (queue --epic), one dated line per ticket milestone.
  extract-plan  Rebuild the plan (or RCA) working copy from the page's mirror (headings promoted back two levels),
            for a worktree that has no local plan (a fresh worktree, another session).
  find      Find a ticket's page id from the state file (--state-id), an older plan's Ticket page line, the ticket's
            Jira link comment and a CQL
            listing of the container (title prefix "Plan: <KEY> - "); exit 2 on several pages, 3 on none.
  queue     The per-ticket outbox (entries not yet sent) and sent log (every entry that reached the page or Jira),
            both untracked, in the worktree's git directory: add, list, mark sent, list sent.
  state     Small per-ticket state: page id, last version written, the published plan's sha256, date and title (and
            with --save-plan its copy), status, fallback comment ids and count.
  verify    Check that the body the last updateConfluencePage call sent for a page (or, with --created, the last
            createConfluencePage call with that title) equals the rendered file (up to trailing whitespace), using
            the PostToolUse hook log (logs/post_tool_use.jsonl); prints the version (and the new page id).
  sanitize  Read text on stdin, replace local absolute paths, refuse secret-like strings, enforce a length cap.

Usage:
  ticket_page.py render --repo WT [--plan FILE [--plan-title Plan|RCA] | --mirrored] --meta meta.json
                        [--ticket ticket.md]
                        [--current page.md|page.json [--new-page] [--allow-fewer] | --local --page-version N]
                        [--entry SECTION SOURCE TEXT]... [--outbox DIR] [--date YYYY-MM-DD] --out body.md
                        (neither --plan nor --mirrored: the skeleton; needs --ticket, and no page_id unless
                        --new-page on a stub)
  ticket_page.py ticket --repo WT --key KEY (--breakdown FILE | --text FILE) --source TEXT [--backfill] --out ticket.md
                        (exit 3: no breakdown entry for KEY; exit 2: several)
  ticket_page.py find   --key KEY [--state-id ID] [--plan FILE] [--comments issue.json] [--search cql.json ...] [--gone ID ...]
                        [--fallback]   (exit 0 found; 3 none, only on a complete listing and comment list
                        (--fallback: the comment list); 2 several or can't tell: stop and report)
  ticket_page.py queue  --repo WT --key KEY [--outbox DIR]
                        [--epic] (--add SECTION SOURCE TEXT [--date D] | --list | --mark-sent | --sent)
                        (--epic: the epic Progress page's queue; SECTION is ignored, pass -)
  ticket_page.py progress (--new --meta meta.json | --repo WT --key KEY --current page [--entry SOURCE TEXT]...)
                        [--outbox DIR] --out body.md
  ticket_page.py state  --repo WT --key KEY [--outbox DIR] [--set NAME=VALUE ...] [--save-body body.md]
                        [--save-plan FILE --plan-title Plan|RCA [--date D]]
  ticket_page.py extract-plan --current page.md|page.json --out FILE   (exit 3: the page has no plan mirrored yet)
  ticket_page.py verify --body body.md (--page-id ID [--after-version N] | --created --title T [--parent-id P])
                        [--log PATH] [--repo WT]
  ticket_page.py stub --key KEY        (prints the one-line body to create a new ticket page with)
  ticket_page.py summary --repo WT --key KEY [--outbox DIR] (--check | --returned-id ID | --failed | --superseded-by ID)
                                       (Jira fallback: running-summary bookkeeping; exit 1 = stopped, make no call)
  ticket_page.py sanitize --repo WT [--max-chars 1500] < text > text

meta.json keys: key, key_url, summary, epic, epic_url, prd_title, prd_url, branch, status, updated, skill;
optional: page_id, page_url, status_note; for the skeleton: branch_state (absent | exists, as checked; otherwise
"not checked"), backfilled (the date, for a page created after the ticket was filed), jira_status.

Exit codes: 0 ok; 1 refused (secret-like string, over the cap, verify mismatch); 2 could not run or unsafe input
(missing meta key, unparseable current page, git error); 3 verify found no logged call (unverified), find found no
page, ticket found no breakdown entry, extract-plan found no mirrored plan.
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
EMPTY = "_No entries yet._"
META_KEYS = ["key", "key_url", "summary", "epic", "epic_url", "prd_title", "prd_url", "branch", "status", "updated",
             "skill"]

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

# Local absolute paths under these roots (workstations and HPC clusters: /scratch, /gpfs, /global/homes, /p/lustre*,
# /g/g*, /usr/workspace, ...). The look-behind keeps URL paths (https://host/home/...) and relative paths; file://
# URLs are handled separately.
PATH_ROOTS = r"(?:Users|home|homes|private|tmp|var|Volumes|opt|mnt|srv|root|scratch|gpfs|lustre)"
# Short or common words count as roots only when a path segment follows (/p/lustre1/..., not "the /p option").
SHORT_ROOTS = r"(?:global|nfs|work|project|projects|data|p|g|usr/workspace|usr/WS\d+)"
_TAIL = r"[^\s`'\"<>()\[\]{}|,;]"
ABS_PATH = re.compile(r"(?<![\w:/.\-~{}])/(?:" + PATH_ROOTS + r"(?=/|\b)(?:/" + _TAIL + r"*)?|"
                      + SHORT_ROOTS + r"/[\w.\-]" + _TAIL + r"*)")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def die(msg, code=2):
    print("ticket_page: " + msg, file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------- sanitising

def _variants(p):
    """A path and its /tmp <-> /private/tmp, /var <-> /private/var twins (macOS)."""
    p = str(p).rstrip("/")
    out = {p}
    for a, b in (("/private/tmp", "/tmp"), ("/private/var", "/var")):
        for x, y in ((a, b), (b, a)):
            if p == x or p.startswith(x + "/"):
                out.add(y + p[len(x):])
    return sorted(out, key=len, reverse=True)


def _replace_prefix(text, prefix, placeholder):
    """Replace `prefix` only as a whole path (followed by '/', a delimiter or the end), never inside a URL."""
    pat = r"(?<![\w:/.\-])" + re.escape(prefix) + r"(?=/|[\s`'\"<>()\[\]{}|,;:]|\.(?:\s|$)|$)"
    return re.sub(pat, placeholder, text)


def sanitize(text, repo):
    """Replace local absolute paths with placeholders that survive Confluence's markdown import."""
    repo = Path(repo).resolve()
    # file:///abs/path: hide the scheme behind a marker so the path is handled like any other absolute path.
    text = re.sub(r"\bfile://(?=/)", "\x00", text)
    for p in _variants(repo):
        text = _replace_prefix(text, p, "{worktree}")
    for p in _variants(repo.parent):
        text = _replace_prefix(text, p, "{worktrees}")
    for p in _variants(Path.home().resolve()):
        text = _replace_prefix(text, p, "{home}")

    def _other(m):
        parts = [x for x in m.group(0).split("/") if x]
        return "{local}/" + parts[-1] if len(parts) > 1 else "{local}"
    text = ABS_PATH.sub(_other, text)
    # User names encoded in path-derived identifiers, e.g. -Users-<name>-Documents-... (session and project dirs).
    text = re.sub(r"-(Users|home)-[A-Za-z0-9._]+-", r"-\1-{user}-", text)
    text = text.replace("\x00", "file://")
    return text


def secret_hits(text):
    return sorted({name for name, pat in SECRET_PATTERNS if re.search(pat, text)})


def refuse_secrets(text, what):
    hits = secret_hits(text)
    if hits:
        die(f"refused: {what} contains secret-like strings ({', '.join(hits)}); rewrite it", 1)


# ---------------------------------------------------------------- markdown

def split_fences(lines):
    """Yield (line, in_fence) so heading and bullet logic skips fenced code."""
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


DEEP = "\u25b8"  # marks a heading deeper than markdown's six levels after demotion: "###### \u25b8 h5", "\u25b8\u25b8 h6"


def demote_marked(md, by=2):
    """Demote headings (outside fences) by `by`; a heading pushed past level 6 stays at 6 and keeps its depth as one
    DEEP mark per level beyond 6, so extract-plan can restore it."""
    out = []
    for ln, in_fence in split_fences(md.splitlines()):
        if not in_fence:
            m = re.match(r"^(#{1,6})(\s+)(.*)$", ln)
            if m:
                lvl = len(m.group(1)) + by
                extra = max(0, lvl - 6)
                ln = "#" * min(6, lvl) + " " + (DEEP * extra + " " if extra else "") + m.group(3)
        out.append(ln)
    return "\n".join(out)


def promote_marked(md, by=2):
    """Undo demote_marked: promote headings (outside fences) by `by`, restoring the DEEP-marked ones."""
    out = []
    for ln, in_fence in split_fences(md.splitlines()):
        if not in_fence:
            m = re.match(r"^(#{1,6})\s+(" + DEEP + r"*)\s*(.*)$", ln)
            if m and len(m.group(1)) > by:
                lvl = len(m.group(1)) + len(m.group(2)) - by
                ln = "#" * lvl + " " + m.group(3)
        out.append(ln)
    return "\n".join(out)


def demote(md, by=2):
    out = []
    for ln, in_fence in split_fences(md.splitlines()):
        if not in_fence:
            m = re.match(r"^(#{1,6})(\s.*)$", ln)
            if m:
                ln = "#" * min(6, len(m.group(1)) + by) + m.group(2)
        out.append(ln)
    return "\n".join(out)


def norm(s):
    """Comparison key that ignores markdown escaping, emphasis, bullet style, indentation and line wrapping."""
    return re.sub(r"[^0-9a-z]", "", s.lower())


def entry_blocks(lines):
    """Group a section's lines into entries: a top-level bullet plus every following line up to the next one
    (Confluence returns continuation lines without their indent, so indentation can't be relied on)."""
    blocks, cur = [], None
    for ln, in_fence in split_fences(lines):
        if not in_fence and re.match(r"^[-*+]\s", ln):
            if cur:
                blocks.append(cur)
            cur = [ln]
        elif cur is not None:
            cur.append(ln)
        elif ln.strip():
            cur = [ln]
    if cur:
        blocks.append(cur)
    out = []
    for b in blocks:
        while b and not b[-1].strip():
            b.pop()
        text = "\n".join(b)
        if b and norm(text) != norm(EMPTY):
            out.append(text)
    return out


def load_current(path):
    """The page body as markdown, from a markdown file, the tool's JSON, or the MCP content-array form."""
    raw = Path(path).read_text()
    try:
        data = json.loads(raw)
    except ValueError:
        return raw
    if isinstance(data, list):  # [{"type": "text", "text": "{...}"}]
        joined = "".join(x.get("text", "") for x in data if isinstance(x, dict))
        try:
            data = json.loads(joined)
        except ValueError:
            return joined
    if isinstance(data, dict):
        body = data.get("body")
        if isinstance(body, str):
            return body
        if isinstance(body, dict):
            die("the current page is in storage (HTML) form; read it again with contentFormat \"markdown\"")
    die("can't find a markdown page body in --current")


def load_json(path):
    """A saved tool result: plain JSON or the MCP content-array form [{"type": "text", "text": "{...}"}]."""
    data = json.loads(Path(path).read_text())
    if isinstance(data, list) and data and all(isinstance(x, dict) and "text" in x for x in data):
        data = json.loads("".join(x["text"] for x in data))
    return data


def parse_sections(md, plan_title):
    """Return ({section: [entries]}, set of log headings found) for the part of a page before the mirror.
    Only the four log headings and the mirror's heading are boundaries; any other heading-like line (for example a
    `# ...` line of an entry whose escape a round trip dropped) stays in the section it is in."""
    cur, seen = None, set()
    lines = {s: [] for s in SECTIONS}
    for ln, in_fence in split_fences(md.splitlines()):
        if not in_fence:
            m = re.match(r"^#{1,2}\s+(.*?)\s*#*\s*$", ln)
            title = m.group(1).strip().strip("*").strip() if m else None
            if title in (plan_title, "Plan", "RCA"):
                break
            if title in SECTIONS:
                cur = title
                seen.add(title)
                continue
        if cur is not None:
            lines[cur].append(ln)
    return {s: entry_blocks(lines[s]) for s in SECTIONS}, seen


def entry_text(e):
    """One entry as a list item. Continuation lines are indented, and a line starting with '#' outside a code fence
    is escaped, so it can't become a heading on the page."""
    out = []
    for i, (ln, in_fence) in enumerate(split_fences(e["text"].strip().splitlines())):
        if i and not in_fence and ln.lstrip().startswith("#"):
            ln = "\\" + ln.lstrip()
        out.append(ln if i == 0 else "  " + ln)
    return f"- **{e['date']}** · {e['source']} · " + "\n".join(out)


STUB = "Plan page for {key}; content follows."
TICKET = "Ticket"
PLAN_BACKFILLED = ("_Not mirrored here yet: this page was created after the ticket was filed (see Backfilled above);"
                   " the plan, if any, is a working copy in the ticket's worktree (or, for older tickets, committed on"
                   " its branch). The next `publish` from that worktree mirrors it here._")
# The same placeholder as pages made before plans left git carry it (extract-plan must not take it for a plan).
OLD_PLAN_BACKFILLED = ("_Not mirrored here yet: this page was created after the ticket was filed (see Backfilled"
                       " above); the plan, if any, is on the ticket branch. The next `publish` from that branch mirrors"
                       " it here._")
PLAN_PLACEHOLDER = ("_Not written yet: `plan-feature` mirrors the ticket's plan here (`implement-fix` mirrors its RCA"
                    " under an RCA heading instead)._")


def _heading(ln):
    """(level, title) of an H1/H2 line, title stripped of '*' and trailing '#', or (0, None)."""
    m = re.match(r"^(#{1,2})\s+(.*?)\s*#*\s*$", ln)
    return (len(m.group(1)), m.group(2).strip().strip("*").strip()) if m else (0, None)


def parse_ticket(md):
    """The Ticket section of a page (the text between '## Ticket' and the next log or mirror heading), or None."""
    out, inside = [], False
    for ln, in_fence in split_fences(md.splitlines()):
        if not in_fence:
            _, title = _heading(ln)
            if title == TICKET:
                inside = True
                continue
            if title in SECTIONS or title in ("Plan", "RCA"):
                if inside:
                    break
                continue
        if inside:
            out.append(ln)
    text = "\n".join(out).strip()
    return text or None


def demote_below_h2(md):
    """Shift headings (outside fences) so none is H1 or H2: the section must not end at one of its own lines."""
    levels = [len(m.group(1)) for ln, f in split_fences(md.splitlines()) if not f
              for m in [re.match(r"^(#{1,6})\s", ln)] if m]
    return demote(md, max(0, 3 - min(levels))) if levels else md


def plan_hash(text):
    """The published plan's identity: sha256 of its text without trailing whitespace (16 hex digits)."""
    return hashlib.sha256(text.rstrip().encode()).hexdigest()[:16]


# ---------------------------------------------------------------- local files

def store_dir(repo, outbox=None):
    if outbox:
        return Path(outbox)
    return Path(git(repo, "rev-parse", "--absolute-git-dir").strip()) / "ticket-page-outbox"


def read_jsonl(p):
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


# ---------------------------------------------------------------- commands

def cmd_render(a):
    meta = json.loads(Path(a.meta).read_text())
    missing = [k for k in META_KEYS if not meta.get(k)]
    if missing:
        die("meta.json is missing " + ", ".join(missing))
    skeleton = not (a.plan or a.mirrored)
    if skeleton:
        if not a.ticket:
            die("the skeleton (no --plan) needs --ticket (the Ticket section, from: ticket_page.py ticket)")
        if a.local or (meta.get("page_id") and not a.new_page):
            die("the skeleton is only for creating a page (or filling a legacy stub with --new-page): an existing "
                "page is never rewritten with it; plan-feature fills the page with --plan")
    if meta.get("page_id") and not (a.current or a.local):
        die("the page exists (meta has page_id): pass --current (the page read with contentFormat \"markdown\"), "
            "--local --page-version N, or for the first fill of a just-created stub --new-page --current <stub>")
    d = store_dir(a.repo, a.outbox)
    key = meta["key"]
    state_p = d / f"{key}.state.json"
    state = json.loads(state_p.read_text()) if state_p.exists() else {}
    # The recorded version and last body belong to state.page_id. A recreated page (another id) has none yet.
    same_page = bool(meta.get("page_id")) and str(state.get("page_id", "")) == str(meta.get("page_id"))
    recorded = state.get("version") if same_page else None
    if meta.get("page_id") and state.get("version") and not same_page:
        print(f"ticket_page: note: the state file's version {state['version']} belongs to page "
              f"{state.get('page_id')}, not {meta['page_id']}; treating the page as new", file=sys.stderr)
    tip = digest_plan = plan = published = None
    plan_title = a.plan_title
    if a.plan:  # publish: the working copy as it is now (a local, untracked file)
        src = Path(a.plan) if Path(a.plan).is_absolute() else Path(a.repo) / a.plan
        if not src.is_file():
            die(f"--plan: {src} doesn't exist (the plan's working copy; in a fresh worktree rebuild it with "
                "extract-plan, or use --mirrored to repeat the published copy)")
        plan = src.read_text()
        published = a.date or date.today().isoformat()
    elif a.mirrored:  # any other flush: the copy last published, so the Plan section only moves on publish
        copy = d / f"{key}.plan.md"
        if not copy.exists() or not state.get("plan_hash"):
            die(f"--mirrored: no published plan in the store ({copy}); publish the working copy (--plan), or rebuild "
                "it from the page (extract-plan, then state --save-plan)")
        plan = copy.read_text()
        if plan_hash(plan) != state["plan_hash"]:
            die(f"--mirrored: {copy} doesn't match the published sha256 {state['plan_hash']} in the state file; "
                "refusing (publish again with --plan)")
        published = state.get("plan_published") or "unknown date"
        plan_title = state.get("plan_title") or a.plan_title
    if plan is not None:
        digest_plan = plan_hash(plan)
        try:
            tip = git(a.repo, "rev-parse", "--short", "HEAD").strip()
        except subprocess.CalledProcessError:
            tip = None

    logs = {s: [] for s in SECTIONS}
    carried_ticket = None
    current = a.current
    if a.local:  # the page is what this worktree last sent: the helper checks the version the caller read
        if a.page_version is None:
            die("--local needs --page-version N (the version the CQL check returned)")
        if not recorded or str(recorded) != str(a.page_version):
            die(f"--local: the page is at version {a.page_version}, but this worktree last wrote version "
                f"{recorded or 'none'}; read the page and pass --current")
        current = d / f"{key}.last-body.md"
        if not current.exists():
            die(f"--local: {current} doesn't exist; read the page and pass --current")
    if a.new_page:
        # First fill of a page just created with the stub body: accepted only for exactly that stub, and only before
        # this worktree has written any version of the page.
        if not (meta.get("page_id") and a.current):
            die("--new-page needs page_id in meta.json and --current with the page as read after the create")
        if recorded:
            die(f"--new-page: this worktree already wrote version {recorded} of page {meta['page_id']}; use --local "
                "or --current (to start this page over on purpose: state --set version=)")
        if norm(load_current(a.current)) != norm(STUB.format(key=key)):
            die("--new-page: the current page is not the stub '" + STUB.format(key=key) + "'; refusing")
    elif current:
        if a.current and norm(load_current(current)) == norm(STUB.format(key=key)):
            die("the page still holds only the stub (its first fill didn't happen or failed): render it with "
                "--new-page" + ("" if not recorded else
                                f"; this worktree recorded version {recorded} of this page, so check the page "
                                "history first, then reset with: state --set version="))
        logs, seen = parse_sections(load_current(current), plan_title)
        carried_ticket = parse_ticket(load_current(current))
        if meta.get("page_id") and len(seen) < len(SECTIONS):
            die("--current lacks the log section heading(s) " + ", ".join(f"'## {s}'" for s in SECTIONS
                                                                          if s not in seen)
                + "; refusing to build a body that would drop their entries (a truncated copy?)")

    sent = read_jsonl(d / f"{key}.sent.jsonl")
    pending = read_jsonl(d / f"{key}.jsonl")
    extra = [{"section": s, "source": src, "text": sanitize(t, a.repo), "date": a.date or date.today().isoformat()}
             for s, src, t in (a.entry or [])]
    restored = added = 0

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
    restored = merge(sent)
    # After restoring this worktree's own entries, the page must still hold everything this worktree last sent:
    # fewer entries means a truncated copy, an overwrite by another worktree, or a person's deliberate removal.
    last = d / f"{key}.last-body.md"
    if a.current and not a.new_page and same_page and last.exists() and not a.allow_fewer:
        before, _ = parse_sections(load_current(last), plan_title)
        fewer = [s for s in SECTIONS if len(logs[s]) < len(before[s])]
        if fewer:
            die("the page has fewer entries than this worktree last sent in " + ", ".join(fewer)
                + "; read the page again; if a person removed them on purpose, pass --allow-fewer")
        if not a.ticket and not carried_ticket and parse_ticket(load_current(last)):
            die("the page lacks the Ticket section this worktree last sent; read the page again, or pass --ticket "
                "(rebuilt with: ticket_page.py ticket), or --allow-fewer if a person removed it on purpose")
    added = merge(pending + extra)

    ticket_md = Path(a.ticket).read_text().strip() if a.ticket else carried_ticket
    page_ref = f"[page {meta['page_id']}]({meta['page_url']})" if meta.get("page_id") else "not yet created"
    status = meta["status"] + (f" ({meta['status_note']})" if meta.get("status_note") else "")
    attribution = ("> **Posted by an agent** through the owner's Atlassian account. Entries are the agent's unless"
                   " marked Owner or Reviewer; an owner decision is marked Owner only when a source records it as the"
                   " owner's (attribution rules in `close-epic`).")
    jira = (f"> **Jira:** [{key}]({meta['key_url']}) - {meta['summary']} · **Epic:** [{meta['epic']}]"
            f"({meta['epic_url']}) · **PRD:** [{meta['prd_title']}]({meta['prd_url']})")
    if skeleton:
        backfilled = meta.get("backfilled")
        bstate = {"absent": " (planned; checked: not created yet)",
                  "exists": " (exists; its plan, if any, is not mirrored here yet)"}.get(meta.get("branch_state"),
                                                                                     " (not checked)")
        header = [
            jira,
            f"> **Branch:** `{meta['branch']}`{bstate} · **Plan:** "
            + ("not mirrored here" if backfilled else "not written yet")
            + (f" · **This page:** {page_ref}" if meta.get("page_id") else ""),
            f"> **Status:** {status} · **Last updated:** {meta['updated']} by {meta['skill']}",
        ]
        if backfilled:
            header.append(
                f"> **Backfilled:** {backfilled} · page created by `{meta['skill']}` after the ticket was filed"
                + (f" (Jira status then: {meta['jira_status']})" if meta.get("jira_status") else "")
                + "; the Ticket section is the scope as read then (its source line names where it was read); the"
                " plan, if any, is in the ticket's worktree (older tickets: on its branch) and not yet mirrored here;"
                " earlier history is in the Jira comments.")
        header += [
            attribution,
            ("> This page is the ticket's PIV record from now on." if backfilled else
             "> This page is the ticket's PIV record, created when the ticket was filed. The Ticket section is its"
             " scope as filed.")
            + " `plan-feature` mirrors the plan into the Plan section, and `execute`, `validate` and the review gates"
            " add to the four log sections, which are append-only.",
        ]
    else:
        what = "RCA" if plan_title == "RCA" else "plan"
        rebuilt = (f", rebuilt from {state['plan_source']}" if a.mirrored and state.get("plan_source") else "")
        header = [
            jira,
            f"> **Branch:** `{meta['branch']}`" + (f" at `{tip}`" if tip else "")
            + f" · **{plan_title}:** published {published} (sha256 `{digest_plan}`{rebuilt}) · "
            f"**This page:** {page_ref}",
            f"> **Status:** {status} · **Last updated:** {meta['updated']} by {meta['skill']}",
            attribution,
            f"> The {what} is a working document kept outside the repo (never committed); the {plan_title} section"
            f" is its published copy and its lasting record, replaced only when the {what} is published again"
            " (date and sha256 above; local paths shown as `{worktree}`, `{local}`)."
            + (" The Ticket section is the ticket's scope as filed." if ticket_md else "")
            + " The four log sections are append-only.",
        ]
    # No H1: Confluence shows the page title. Separate quote paragraphs: the import joins consecutive quote lines.
    body = [x for h in header for x in (h, ">")][:-1] + [""]
    if ticket_md:
        body += [f"## {TICKET}", "", demote_below_h2(ticket_md), ""]
    for s in SECTIONS:
        body += [f"## {s}", ""] + (logs[s] or [EMPTY]) + [""]
    if skeleton:
        body += ["## Plan", "", PLAN_BACKFILLED if meta.get("backfilled") else PLAN_PLACEHOLDER, ""]
    else:
        body += [f"## {plan_title}", "", demote_marked(plan.strip(), 2), ""]
    text = sanitize("\n".join(body), a.repo)
    refuse_secrets(text, "the page body")
    Path(a.out).write_text(text)
    digest = hashlib.sha256(text.rstrip().encode()).hexdigest()[:16]
    print(f"ticket_page: wrote {a.out} ({len(text)} chars, sha256 {digest}; "
          + ("skeleton; " if skeleton else f"{plan_title} " + ("working copy" if a.plan else "as published")
                                             + f" sha256 {digest_plan}; ")
          + ("Ticket section " + ("given" if a.ticket else "carried over") if ticket_md else "no Ticket section")
          + "; " + ", ".join(f"{s}: {len(logs[s])}" for s in SECTIONS)
          + f"; {added} new, {restored} restored from the sent log)")
    return 0


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
            f.write(json.dumps({"section": sec, "source": source, "text": text,
                                "date": a.date or date.today().isoformat()}) + "\n")
    elif a.mark_sent:
        entries = read_jsonl(box)
        if entries:
            with sent.open("a") as f:
                for e in entries:
                    f.write(json.dumps(e) + "\n")
            box.unlink()
        print(f"ticket_page: {len(entries)} entries moved to the sent log")
        return 0
    elif a.sent:
        for e in read_jsonl(sent):
            print(f"[{e['section']}] {entry_text(e)}")
        return 0
    for e in read_jsonl(box):
        print(f"[{e['section']}] {entry_text(e)}")
    return 0


def cmd_state(a):
    d = store_dir(a.repo, a.outbox)
    p = d / f"{a.key}.state.json"
    st = json.loads(p.read_text()) if p.exists() else {}
    if a.save_body:
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{a.key}.last-body.md").write_text(Path(a.save_body).read_text())
        print(f"ticket_page: saved {a.save_body} as the last body sent")
    if a.save_plan:
        if not a.plan_title:
            die("--save-plan needs --plan-title Plan|RCA (the section the page mirrors it under)")
        text = Path(a.save_plan).read_text()
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{a.key}.plan.md").write_text(text)
        st.update(plan_hash=plan_hash(text), plan_published=a.date or date.today().isoformat(),
                  plan_title=a.plan_title)
        st.pop("plan_source", None)
        print(f"ticket_page: saved {a.save_plan} as the published plan (sha256 {st['plan_hash']})")
    for kv in a.set or []:
        k, sep, v = kv.partition("=")
        if not k or not sep:
            die(f"bad --set {kv!r}, expected NAME=VALUE")
        st[k] = v
    if a.set or a.save_plan:
        d.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(st, indent=1) + "\n")
    print(json.dumps(st, indent=1))
    return 0


def _log_candidates(a):
    if a.log:
        return [Path(a.log)]
    cands = []
    for args, up in ((["rev-parse", "--show-toplevel"], False),
                     (["rev-parse", "--path-format=absolute", "--git-common-dir"], True)):
        try:
            p = Path(git(a.repo or ".", *args).strip())
            cands.append((p.parent if up else p) / "logs" / "post_tool_use.jsonl")
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    return [c for c in dict.fromkeys(cands) if c.exists()]


def _response_json(d):
    try:
        r = d.get("tool_response")
        if isinstance(r, list):
            r = json.loads("".join(x.get("text", "") for x in r if isinstance(x, dict)))
        return r if isinstance(r, dict) else {}
    except ValueError:
        return {}


def verify_created(a, want):
    """The last logged createConfluencePage call with this title (and parent): compare its body, print the new id."""
    for logp in _log_candidates(a):
        with logp.open() as f:
            lines = f.readlines()
        for ln in reversed(lines):
            if "createConfluencePage" not in ln:
                continue
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            ti = d.get("tool_input") or {}
            if not str(d.get("tool_name", "")).endswith("createConfluencePage") or ti.get("title") != a.title:
                continue
            if a.parent_id and str(ti.get("parentId")) != a.parent_id:
                continue
            resp = _response_json(d)
            pid = str(resp.get("id") or "")
            sent = str(ti.get("body", "")).rstrip()
            if sent == want:
                print(f"ticket_page: verified: the create of '{a.title}' sent the rendered body ({len(sent)} chars); "
                      f"page id {pid or 'unknown'}, version 1")
                return 0
            first = next((i for i, (x, y) in enumerate(zip(sent, want)) if x != y), min(len(sent), len(want)))
            print(f"ticket_page: MISMATCH: the create of '{a.title}' (page id {pid or 'unknown'}) sent {len(sent)} "
                  f"chars, the rendered body has {len(want)}; first difference at char {first}", file=sys.stderr)
            return 1
    print(f"ticket_page: no logged createConfluencePage call titled '{a.title}'; unverified", file=sys.stderr)
    return 3


def cmd_verify(a):
    want = Path(a.body).read_text().rstrip()
    if a.created:
        if not a.title:
            die("--created needs --title")
        return verify_created(a, want)
    if not a.page_id:
        die("verify needs --page-id (or --created --title)")
    for logp in _log_candidates(a):
        with logp.open() as f:
            lines = f.readlines()
        for ln in reversed(lines):
            if "updateConfluencePage" not in ln or a.page_id not in ln:
                continue
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            ti = d.get("tool_input") or {}
            if not str(d.get("tool_name", "")).endswith("updateConfluencePage") or str(ti.get("pageId")) != a.page_id:
                continue
            sent = str(ti.get("body", "")).rstrip()
            m = re.search(r'number\\*"?:\s*(\d+)', json.dumps(d.get("tool_response")))
            version = int(m.group(1)) if m else None
            if a.after_version is not None and (version is None or version <= a.after_version):
                print(f"ticket_page: the last logged update of page {a.page_id} returned version {version}, not one "
                      f"after {a.after_version}: the update just made was not logged as successful; don't retry "
                      "blindly, check the update call's result", file=sys.stderr)
                return 3
            if sent == want:
                print(f"ticket_page: verified: the last update of page {a.page_id} sent the rendered body "
                      f"({len(sent)} chars); version {version}")
                return 0
            first = next((i for i, (x, y) in enumerate(zip(sent, want)) if x != y), min(len(sent), len(want)))
            print(f"ticket_page: MISMATCH: the last update of page {a.page_id} sent {len(sent)} chars, the rendered "
                  f"body has {len(want)}; first difference at char {first}; version {version}", file=sys.stderr)
            return 1
    print(f"ticket_page: no logged updateConfluencePage call for page {a.page_id}; unverified", file=sys.stderr)
    return 3


def cmd_summary(a):
    """Jira fallback: the running-summary comment's bookkeeping, so the comment cap holds mechanically.
    --check before an update call; --returned-id after a call that returned a comment id; --failed after a call that
    failed; --superseded-by after posting the one "Supersedes comment <id>." comment."""
    d = store_dir(a.repo, a.outbox)
    p = d / f"{a.key}.state.json"
    st = json.loads(p.read_text()) if p.exists() else {}

    def save(msg, code):
        d.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(st, indent=1) + "\n")
        print("ticket_page: " + msg)
        return code
    cur = str(st.get("fallback_summary_id", ""))
    if st.get("fallback_stopped") == "1":
        return save("the running summary is stopped (cap reached): make no Jira call; report it", 1)
    if a.check:
        if not cur:
            return save("no running summary yet: post it as a new comment and record its id with --returned-id", 0)
        return save(f"update comment {cur} in place, then report the returned id with --returned-id", 0)
    if a.returned_id is not None:
        if not cur:
            st["fallback_summary_id"] = a.returned_id
            return save(f"recorded comment {a.returned_id} as the running summary", 0)
        if a.returned_id == cur:
            return save(f"comment {cur} updated in place", 0)
        if st.get("fallback_superseded") != "1":
            st.update(fallback_summary_id=a.returned_id, fallback_superseded="1")
            return save(f"the update created comment {a.returned_id} instead of updating {cur}: adopted it as the "
                        "running summary (counts as the one superseding comment); don't post another", 0)
        st["fallback_stopped"] = "1"
        return save(f"the update created another comment ({a.returned_id}) after the summary was already superseded: "
                    "stopped; make no further Jira calls and report it", 1)
    if a.failed:
        if st.get("fallback_superseded") != "1":
            return save(f"the update of {cur or 'the summary'} failed: post once a new comment starting "
                        f"'Supersedes comment {cur}.' with the summary, then record it with --superseded-by <id>", 0)
        st["fallback_stopped"] = "1"
        return save("the update failed after the summary was already superseded: stopped; make no further Jira calls "
                    "and report it", 1)
    if a.superseded_by:
        st.update(fallback_summary_id=a.superseded_by, fallback_superseded="1")
        return save(f"comment {a.superseded_by} now supersedes {cur}", 0)
    die("summary needs --check, --returned-id, --failed or --superseded-by")


KEY_TOKEN = r"(?<![A-Za-z0-9-]){key}(?![0-9])"


def cmd_ticket(a):
    """The Ticket section: the ticket's entry in the epic breakdown (a local file: the page as read, or spec's working
    copy), or a given text, with its source line."""
    if not a.source:
        die("ticket needs --source: where the text comes from (the breakdown page with its id and version, or 'the "
            "Jira description of <KEY>')")
    if a.breakdown:
        doc = load_current(a.breakdown)
        lines = doc.splitlines()
        heads = [(i, len(m.group(1)), m.group(2).strip()) for i, (ln, f) in enumerate(split_fences(lines)) if not f
                 for m in [re.match(r"^(#{2,6})\s+(.*)$", ln)] if m]
        tok = KEY_TOKEN.format(key=re.escape(a.key))

        def body(h):
            i, lvl, _ = h
            end = next((j for j, l2, _ in heads if j > i and l2 <= lvl), len(lines))
            return "\n".join(lines[i + 1:end]).strip()

        def own_lines(h):  # up to the next heading of any level: an entry's own lines, not its children's
            i = h[0]
            end = next((j for j, _, _ in heads if j > i), len(lines))
            return lines[i + 1:end]
        branch = re.compile(r"^\s*[-*+]\s*\**Branch\**\s*:?\s*\**:?.*\bv9-(?:ai-)?" + re.escape(a.key) + r"-")
        tiers = [
            [h for h in heads if h[1] >= 3 and re.search(r"`" + re.escape(a.key) + r"`", h[2])],
            [h for h in heads if h[1] >= 3 and any(branch.search(x) for x in own_lines(h))],
            # A plain mention only in a heading that names no ticket key of its own: "Coordinate with AIUE-9 ·
            # `AIUE-48`" is AIUE-48's entry, not AIUE-9's.
            [h for h in heads if h[1] >= 3 and re.search(tok, h[2])
             and not re.search(r"`[A-Za-z][A-Za-z0-9]*-[0-9]+`", h[2])],
        ]
        found = next((t for t in tiers if t), [])
        if not found:
            print(f"ticket_page: no entry for {a.key} in {a.breakdown}; build the section from the Jira "
                  "description (--text, --source)", file=sys.stderr)
            return 3
        if len(found) > 1:
            die(f"several breakdown entries match {a.key}: " + "; ".join(h[2] for h in found))
        h = found[0]
        title = re.sub(r"[`*]", "", h[2])
        where = f"the ticket's entry \"{title}\" in {a.source}"
        src = (f"_Scope as read on {a.date or date.today().isoformat()}, when this page was created after the ticket "
               f"was filed: {where}._" if a.backfill else f"_Scope as filed: {where}._") + (
            " _The breakdown is the source of truth; a later change to it is not copied here automatically._")
        text = body(h)
    else:
        if not a.text:
            die("ticket needs --breakdown or --text")
        text = Path(a.text).read_text().strip()
        src = (f"_Scope as read on {a.date or date.today().isoformat()}, when this page was created after the ticket "
               f"was filed: {a.source}._" if a.backfill else f"_Scope as filed: {a.source}._")
    out = sanitize(src + "\n\n" + demote_below_h2(text) + "\n", a.repo)
    refuse_secrets(out, "the Ticket section")
    Path(a.out).write_text(out)
    print(f"ticket_page: wrote {a.out} ({len(out)} chars)")
    return 0


def _search_hits(path):
    """(hits, total, has_next) from a searchConfluenceUsingCql result: the REST form (results[].content, totalSize,
    _links.next) or the GraphQL-like form (content.nodes, totalCount, pageInfo.hasNextPage). total is None when the
    result doesn't say; has_next is True when it links a further page of results."""
    data = load_json(path)
    if isinstance(data, dict) and isinstance(data.get("content"), dict) and "nodes" in data["content"]:
        c = data["content"]
        nodes, total = c.get("nodes") or [], c.get("totalCount")
        has_next = bool((c.get("pageInfo") or {}).get("hasNextPage"))
        return [(str(n["id"]), n["title"]) for n in nodes if n.get("id") and n.get("title")], total, has_next
    if not isinstance(data, dict) or "results" not in data:
        die(f"{path}: not a searchConfluenceUsingCql result (no 'results' or 'content.nodes')")
    out = []
    for r in data.get("results") or []:
        c = r.get("content", r) if isinstance(r, dict) else {}
        if c.get("id") and (c.get("title") or r.get("title")):
            out.append((str(c["id"]), c.get("title") or r.get("title")))
    return out, data.get("totalSize"), bool((data.get("_links") or {}).get("next") or data.get("next"))


def adf_text(n):
    """Atlassian Document Format to the markdown the link and PIV-record patterns expect (strong -> **, code -> `)."""
    if isinstance(n, list):
        return "".join(adf_text(x) for x in n)
    if not isinstance(n, dict):
        return ""
    t = n.get("type")
    if t == "text":
        txt, marks = n.get("text", ""), {m.get("type") for m in n.get("marks") or []}
        txt = f"`{txt}`" if "code" in marks else txt
        return f"**{txt}**" if "strong" in marks else txt
    if t == "hardBreak":
        return "\n"
    if t in ("inlineCard", "blockCard"):
        return (n.get("attrs") or {}).get("url", "")
    inner = adf_text(n.get("content") or [])
    return inner + "\n" if t in ("paragraph", "heading", "listItem", "blockquote", "codeBlock") else inner


def _jira_comments(path, key):
    """(comment bodies as text, problem). problem is set when the list can't be trusted to be complete."""
    data = load_json(path)
    if isinstance(data, dict) and isinstance(data.get("issues"), dict):  # {"issues": {"nodes": [issue]}}
        nodes = [x for x in data["issues"].get("nodes") or [] if x.get("key") in (key, None)]
        if len(nodes) != 1:
            return None, f"{len(nodes)} issues for {key} in the response"
        data = nodes[0]
    if not isinstance(data, dict):
        return None, "not a getJiraIssue result"
    block = (data.get("fields") or {}).get("comment")
    if isinstance(block, dict) and isinstance(block.get("comments"), list):
        comments = block["comments"]
        total = block.get("total")
        if isinstance(total, int) and total > len(comments):
            return None, f"the response holds {len(comments)} of {total} comments (paged); read them all"
    elif isinstance(data.get("comments"), list):
        comments = data["comments"]
    else:
        return None, "no comment list (read the issue with fields [\"comment\"])"
    out = []
    for c in comments:
        b = c.get("body")
        if isinstance(b, str):
            out.append(b)
        elif isinstance(b, dict) and b.get("type") == "doc":
            out.append(adf_text(b))
        else:
            return None, f"comment {c.get('id')} has a body in an unknown form"
    return out, None


def cmd_find(a):
    """Resolve a ticket's page id (or, with --fallback, whether its PIV record comments exist). Exit 0 found, 3 none
    (only when the evidence to conclude that was given: a complete container listing, or for --fallback a complete
    comment list), 2 several or can't tell (stop and report)."""
    prefix = f"Plan: {a.key} - "
    gone = set(a.gone or [])
    report = {"key": a.key}

    def done(code, msg):
        print(json.dumps(report, indent=1))
        print(f"ticket_page: {msg}", file=sys.stderr)
        return code
    recorded = {}  # id -> [how]
    if a.state_id:
        recorded.setdefault(str(a.state_id), []).append("state file")
    if a.plan:
        m = re.search(r"\*\*Ticket page\*\*:\s*Confluence page (\d+)", Path(a.plan).read_text())
        if m:
            recorded.setdefault(m.group(1), []).append("plan line")
    comments_ok = False
    if a.comments:
        bodies, problem = _jira_comments(a.comments, a.key)
        if problem:
            report["reason"] = problem
            return done(2, f"can't tell from the comments: {problem}")
        comments_ok = True
        piv = sum(1 for b in bodies if b.lstrip().startswith("**PIV record"))
        report.update(piv_record_comments=piv, piv_cap_reached=piv >= 8)
        for b in bodies:
            m = re.match(r"\s*\**(?:Ticket|Plan) page:\**.*?Confluence page id\s*`?(\d+)`?", b, re.S)
            if m:
                recorded.setdefault(m.group(1), []).append("Jira link comment")
    if a.fallback:
        if not comments_ok:
            report["reason"] = "no comment list given"
            return done(2, "--fallback needs --comments (the getJiraIssue result with all comments, markdown)")
        if report["piv_record_comments"]:
            return done(0, f"{a.key} already has {report['piv_record_comments']} PIV record comment(s)")
        return done(3, f"{a.key} has no PIV record comment")
    # Complete = the files given hold every page: at least one of them links no further page, and together they hold
    # as many results as any of them says there are.
    listed, totals, last_pages = [], [], 0
    for sp in a.search or []:
        hits, total, has_next = _search_hits(sp)
        listed += hits
        totals += [total] if total is not None else []
        last_pages += 0 if has_next else 1
    complete = bool(a.search) and last_pages > 0 and (not totals or len(dict.fromkeys(listed)) >= max(totals))
    report["listing_complete"] = complete
    if a.search and not complete:
        report["reason"] = "the container listing is incomplete (a further page is linked, or fewer results than the "\
                           "total): pass every page of it"
        return done(2, "can't tell from an incomplete listing: follow next and pass every page")
    mine = list(dict.fromkeys((i, t) for i, t in listed if t.startswith(prefix) and i not in gone))
    linked = {i for i, v in recorded.items() if "Jira link comment" in v and i not in gone}
    for i in list(recorded):
        if i in gone:
            del recorded[i]
    report["listed"] = {i: t for i, t in mine}
    report["recorded"] = recorded
    if len({i for i, _ in mine}) > 1:
        return done(2, f"several pages for {a.key} under the container: stop and ask; never pick one silently")
    if mine:
        pid = mine[0][0]
        report["page_id"] = pid
        stale = [i for i in recorded if i != pid]
        if a.comments:
            report["missing_link_comment"] = pid not in linked
        if stale:
            report["stale_records"] = stale
            report["note"] = (f"the listed page {pid} wins; recorded id(s) {', '.join(stale)} name another page. "
                              "Confirm each once with CQL id = <id>: gone (an earlier page deleted and created again) "
                              "-> fine, pass --gone <id> to drop it; still exists -> two existing pages: stop and ask")
        return done(0, f"page {pid}")
    if len(recorded) > 1:
        return done(2, f"several recorded ids for {a.key} ({', '.join(recorded)}) and none listed: stop and ask")
    if recorded:
        pid = next(iter(recorded))
        report.update(page_id=pid, not_listed=bool(a.search))
        if a.comments:
            report["missing_link_comment"] = pid not in linked
        if a.search:
            report["note"] = (f"page {pid} is recorded but not under this container: confirm with CQL id = {pid}. If "
                              "it exists (a ticket moved from another epic keeps its page there), use it; if it is "
                              f"gone, run find again with --gone {pid}")
        return done(0, f"page {pid} (recorded{', not listed' if a.search else ''})")
    if not a.search:
        report["reason"] = "no container listing given"
        return done(2, "can't conclude that there is no page without the container listing (--search)")
    if a.comments is None:
        report["reason"] = "no comments given"
        return done(2, "pass the ticket's comments too (--comments): its link comment may name a page elsewhere")
    return done(3, f"no page for {a.key}")


def cmd_extract_plan(a):
    """The plan (or RCA) as mirrored on the page, with its headings promoted back two levels: the working copy for a
    worktree that has none. Exit 3 when the page has no plan mirrored (a placeholder or no Plan/RCA section)."""
    md = load_current(a.current)
    lines, start, title = md.splitlines(), None, None
    for i, (ln, in_fence) in enumerate(split_fences(lines)):
        if not in_fence:
            lvl, t = _heading(ln)
            if lvl == 2 and t in ("Plan", "RCA"):
                start, title = i + 1, t
                break
    body = "\n".join(lines[start:]).strip() if start is not None else ""
    if not body or norm(body) in (norm(PLAN_PLACEHOLDER), norm(PLAN_BACKFILLED), norm(OLD_PLAN_BACKFILLED)):
        print("ticket_page: the page has no plan mirrored yet (no Plan/RCA section, or only its placeholder)",
              file=sys.stderr)
        return 3
    text = promote_marked(body, 2)
    Path(a.out).write_text(text.rstrip() + "\n")
    print(f"ticket_page: wrote {a.out} ({title} section, {len(text.splitlines())} lines; rebuilt from the page: local "
          "paths come back as the placeholders {worktree}, {worktrees}, {home}, {local}/<name>, and Confluence may "
          f"have changed some formatting). Record it with: state --save-plan {a.out} --plan-title {title}")
    return 0


EPIC_SECTION = "Entries"


def cmd_progress(a):
    """The epic's `Progress: <EPIC>` page: --new builds the skeleton; otherwise the current page's entries, plus any
    entry of this worktree's epic sent log the page lost, plus the queued epic entries (and --entry)."""
    if a.new:
        meta = json.loads(Path(a.meta).read_text())
        missing = [k for k in ("epic", "epic_url", "prd_title", "prd_url") if not meta.get(k)]
        if missing:
            die("meta.json is missing " + ", ".join(missing))
        body = [f"> **Epic:** [{meta['epic']}]({meta['epic_url']}) · **PRD:** [{meta['prd_title']}]({meta['prd_url']})",
                ">",
                "> **Posted by an agent** through the owner's Atlassian account. The epic's progress log: one dated line"
                " per ticket milestone (execute finished, a validate run on its own, approval, escalation, commit) and"
                " per owner decision (marked Owner only with its source), appended by the ticket-page skill."
                " Append-only; `close-epic` reads it.", "", f"## {EPIC_SECTION}", "", EMPTY, ""]
        text = sanitize("\n".join(body), a.repo or ".")
        refuse_secrets(text, "the page body")
        Path(a.out).write_text(text)
        print(f"ticket_page: wrote {a.out} (Progress page skeleton)")
        return 0
    if not (a.repo and a.key and a.current):
        die("progress needs --new --meta, or --repo --key --current")
    md = load_current(a.current)
    head, entries, seen = [], [], False
    for ln, in_fence in split_fences(md.splitlines()):
        if not in_fence and _heading(ln)[1] == EPIC_SECTION:
            seen = True
            continue
        (entries if seen else head).append(ln)
    if not seen:
        die(f"--current lacks the '## {EPIC_SECTION}' heading; refusing to build a body that would drop its entries")
    have = entry_blocks(entries)
    d = store_dir(a.repo, a.outbox)
    sent, pending = read_jsonl(d / f"{a.key}.epic.sent.jsonl"), read_jsonl(d / f"{a.key}.epic.jsonl")
    extra = [{"section": EPIC_SECTION, "source": f"{a.key} {src}", "text": sanitize(t, a.repo),
              "date": a.date or date.today().isoformat()} for src, t in (a.entry or [])]
    counts = []
    for group in (sent, pending + extra):
        n = 0
        for e in group:
            block = entry_text(e)
            if norm(block) not in {norm(x) for x in have}:
                have.append(block)
                n += 1
        counts.append(n)
    text = "\n".join(head).rstrip() + f"\n\n## {EPIC_SECTION}\n\n" + "\n".join(have or [EMPTY]) + "\n"
    text = sanitize(text, a.repo)
    refuse_secrets(text, "the page body")
    Path(a.out).write_text(text)
    print(f"ticket_page: wrote {a.out} ({len(have)} entries; {counts[1]} new, {counts[0]} restored from the sent log)")
    return 0


def cmd_stub(a):
    print(STUB.format(key=a.key))
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
    r = sub.add_parser("render")
    r.add_argument("--repo", required=True)
    pg = r.add_mutually_exclusive_group()
    pg.add_argument("--plan", help="the plan (or RCA) working copy to publish (absolute, or relative to --repo); "
                    "without --plan or --mirrored: the skeleton")
    pg.add_argument("--mirrored", action="store_true",
                    help="repeat the plan as last published (the store's copy; state --save-plan records it)")
    r.add_argument("--plan-title", default="Plan", choices=["Plan", "RCA"])
    r.add_argument("--meta", required=True)
    r.add_argument("--ticket", help="the Ticket section (from: ticket_page.py ticket); default: carried over")
    g = r.add_mutually_exclusive_group()
    g.add_argument("--current")
    g.add_argument("--local", action="store_true")
    r.add_argument("--page-version", help="with --local: the page version the CQL check returned")
    r.add_argument("--new-page", action="store_true",
                   help="first fill of a page just created with the stub body (--current = the stub)")
    r.add_argument("--allow-fewer", action="store_true",
                   help="accept a page with fewer entries than the last body sent (a deliberate correction)")
    r.add_argument("--entry", nargs=3, action="append", metavar=("SECTION", "SOURCE", "TEXT"))
    r.add_argument("--date")
    r.add_argument("--outbox", help="directory of the outbox, sent log and state (default <git dir>/ticket-page-outbox)")
    r.add_argument("--out", required=True)
    q = sub.add_parser("queue")
    q.add_argument("--repo", required=True)
    q.add_argument("--key", required=True)
    q.add_argument("--outbox")
    qg = q.add_mutually_exclusive_group(required=True)
    qg.add_argument("--add", nargs=3, metavar=("SECTION", "SOURCE", "TEXT"))
    qg.add_argument("--list", action="store_true")
    qg.add_argument("--mark-sent", action="store_true")
    qg.add_argument("--sent", action="store_true")
    q.add_argument("--epic", action="store_true",
                   help="the epic's Progress page instead of the ticket page (--add's SECTION is ignored)")
    q.add_argument("--date")
    s = sub.add_parser("state")
    s.add_argument("--repo", required=True)
    s.add_argument("--key", required=True)
    s.add_argument("--outbox")
    s.add_argument("--set", nargs="+", metavar="NAME=VALUE")
    s.add_argument("--save-body", metavar="BODY", help="record BODY as the last body sent (after a verified update)")
    s.add_argument("--save-plan", metavar="FILE",
                   help="record FILE as the published plan (after a verified publish): its copy, sha256 and date")
    s.add_argument("--plan-title", choices=["Plan", "RCA"], help="with --save-plan: Plan or RCA (required)")
    s.add_argument("--date")
    v = sub.add_parser("verify")
    v.add_argument("--body", required=True)
    v.add_argument("--page-id")
    v.add_argument("--created", action="store_true", help="check the last createConfluencePage call with --title")
    v.add_argument("--title")
    v.add_argument("--parent-id")
    v.add_argument("--log")
    v.add_argument("--after-version", type=int,
                   help="the version checked before the update: only a logged update that returned a later version "
                        "counts")
    v.add_argument("--repo")
    sm = sub.add_parser("summary")
    sm.add_argument("--repo", required=True)
    sm.add_argument("--key", required=True)
    sm.add_argument("--outbox")
    smg = sm.add_mutually_exclusive_group(required=True)
    smg.add_argument("--check", action="store_true")
    smg.add_argument("--returned-id")
    smg.add_argument("--failed", action="store_true")
    smg.add_argument("--superseded-by")
    tk = sub.add_parser("ticket")
    tk.add_argument("--repo", required=True)
    tk.add_argument("--key", required=True)
    tk.add_argument("--breakdown", help="the epic breakdown as a local file: the breakdown page as read "
                    "(markdown, or the saved tool result), or spec's working copy of what it published")
    tk.add_argument("--text", help="file with the scope text, when the breakdown has no entry")
    tk.add_argument("--source", help="where the text comes from, for the source line: e.g. 'the epic breakdown page "
                    "`Spec: X - Ticket Breakdown` (Confluence page 123, version 4)', 'the Jira description of AIUE-61'")
    tk.add_argument("--backfill", action="store_true",
                    help="the page is created after the ticket was filed: say 'as read on <date>', not 'as filed'")
    tk.add_argument("--date")
    tk.add_argument("--out", required=True)
    fd = sub.add_parser("find")
    fd.add_argument("--key", required=True)
    fd.add_argument("--state-id", help="the page id in this worktree's state file (state.page_id)")
    fd.add_argument("--plan", help="an older plan or RCA file that still has a **Ticket page** line")
    fd.add_argument("--comments", help="the getJiraIssue result with fields.comment")
    fd.add_argument("--search", action="append", help="a searchConfluenceUsingCql result (repeatable, one per page "
                    "of results)")
    fd.add_argument("--gone", action="append", help="an id confirmed deleted (CQL id = <id> found nothing)")
    fd.add_argument("--fallback", action="store_true",
                    help="Jira fallback: exit 0 if the ticket has PIV record comments, 3 if none (needs --comments)")
    xp = sub.add_parser("extract-plan")
    xp.add_argument("--current", required=True, help="the page as read (markdown, or the saved tool result)")
    xp.add_argument("--out", required=True)
    pr = sub.add_parser("progress")
    pr.add_argument("--new", action="store_true", help="the skeleton of a new Progress page (needs --meta)")
    pr.add_argument("--meta")
    pr.add_argument("--repo")
    pr.add_argument("--key")
    pr.add_argument("--current", help="the Progress page as read (markdown, or the saved tool result)")
    pr.add_argument("--entry", nargs=2, action="append", metavar=("SOURCE", "TEXT"))
    pr.add_argument("--outbox")
    pr.add_argument("--date")
    pr.add_argument("--out", required=True)
    st = sub.add_parser("stub")
    st.add_argument("--key", required=True)
    z = sub.add_parser("sanitize")
    z.add_argument("--repo", required=True)
    z.add_argument("--max-chars", type=int, default=1500)
    a = ap.parse_args()
    try:
        return {"render": cmd_render, "queue": cmd_queue, "state": cmd_state, "verify": cmd_verify,
                "stub": cmd_stub, "summary": cmd_summary, "sanitize": cmd_sanitize, "ticket": cmd_ticket,
                "find": cmd_find, "extract-plan": cmd_extract_plan,
                "progress": cmd_progress}[a.cmd](a)
    except subprocess.CalledProcessError as e:
        die("git failed: " + (e.stderr or "").strip())
    except (OSError, ValueError, KeyError) as e:
        die(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    sys.exit(main())
