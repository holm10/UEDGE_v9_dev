#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""
Deterministic helpers for the `ticket-page` skill (`.claude/skills/ticket-page/SKILL.md`).

The skill makes the Atlassian calls; this script only builds and checks text, so a dry run and a real run write the
same thing.

  render    Build the ticket page body: header, the four log sections and the plan (or RCA) mirrored from a
            committed revision. Log sections = the current page's entries, plus any entry of the local sent log that
            the page lost, plus the outbox, plus --entry. For an existing page it refuses (exit 2) unless it gets a
            current page with all four log headings and at least the entries this worktree last sent, or --local
            with the version this worktree last wrote, or --new-page with exactly the stub of a page just created.
  queue     The per-ticket outbox (entries not yet sent) and sent log (every entry that reached the page or Jira),
            both untracked, in the worktree's git directory: add, list, mark sent, list sent.
  state     Small per-ticket state: page id, last version written, plan revision, fallback comment ids and count.
  verify    Check that the body the last updateConfluencePage call sent for a page equals the rendered file (up to
            trailing whitespace), using the PostToolUse hook log (logs/post_tool_use.jsonl); prints the version.
  sanitize  Read text on stdin, replace local absolute paths, refuse secret-like strings, enforce a length cap.

Usage:
  ticket_page.py render --repo WT --plan PATH [--plan-rev REV] [--plan-title Plan|RCA] --meta meta.json
                        [--current page.md|page.json [--new-page] [--allow-fewer] | --local --page-version N]
                        [--entry SECTION SOURCE TEXT]... [--outbox DIR] [--date YYYY-MM-DD] --out body.md
  ticket_page.py queue  --repo WT --key KEY [--outbox DIR]
                        (--add SECTION SOURCE TEXT [--date D] | --list | --mark-sent | --sent)
  ticket_page.py state  --repo WT --key KEY [--outbox DIR] [--set NAME=VALUE ...] [--save-body body.md]
  ticket_page.py verify --body body.md --page-id ID [--after-version N] [--log PATH] [--repo WT]
  ticket_page.py stub --key KEY        (prints the one-line body to create a new ticket page with)
  ticket_page.py summary --repo WT --key KEY [--outbox DIR] (--check | --returned-id ID | --failed | --superseded-by ID)
                                       (Jira fallback: running-summary bookkeeping; exit 1 = stopped, make no call)
  ticket_page.py sanitize --repo WT [--max-chars 1500] < text > text

meta.json keys: key, key_url, summary, epic, epic_url, prd_title, prd_url, branch, status, updated, skill;
optional: page_id, page_url, status_note.

Exit codes: 0 ok; 1 refused (secret-like string, over the cap, verify mismatch); 2 could not run or unsafe input
(missing meta key, unparseable current page, git error); 3 verify found no logged call (unverified).
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
    rev = a.plan_rev or "HEAD"
    tip = git(a.repo, "rev-parse", "--short", "HEAD").strip()
    # The commit that last changed the mirrored file at that revision, so the header doesn't move with other commits.
    sha = git(a.repo, "log", "-1", "--format=%h", rev, "--", a.plan).strip() or git(
        a.repo, "rev-parse", "--short", rev).strip()
    plan = git(a.repo, "show", f"{rev}:{a.plan}")

    logs = {s: [] for s in SECTIONS}
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
        logs, seen = parse_sections(load_current(current), a.plan_title)
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
        before, _ = parse_sections(load_current(last), a.plan_title)
        fewer = [s for s in SECTIONS if len(logs[s]) < len(before[s])]
        if fewer:
            die("the page has fewer entries than this worktree last sent in " + ", ".join(fewer)
                + "; read the page again; if a person removed them on purpose, pass --allow-fewer")
    added = merge(pending + extra)

    page_ref = f"[page {meta['page_id']}]({meta['page_url']})" if meta.get("page_id") else "not yet created"
    status = meta["status"] + (f" ({meta['status_note']})" if meta.get("status_note") else "")
    header = [
        f"> **Jira:** [{key}]({meta['key_url']}) - {meta['summary']} · **Epic:** [{meta['epic']}]({meta['epic_url']})"
        f" · **PRD:** [{meta['prd_title']}]({meta['prd_url']})",
        f"> **Branch:** `{meta['branch']}` at `{tip}` · **{a.plan_title}:** `{a.plan}` as of `{sha}` · "
        f"**This page:** {page_ref}",
        f"> **Status:** {status} · **Last updated:** {meta['updated']} by {meta['skill']}",
        "> **Posted by an agent** through the owner's Atlassian account. Entries are the agent's unless marked"
        " Owner or Reviewer; an owner decision is marked Owner only when a source records it as the owner's"
        " (attribution rules in `close-epic`).",
        f"> The {'RCA' if a.plan_title == 'RCA' else 'plan'} file in the repo is the source of truth; the"
        f" {a.plan_title} section mirrors it"
        " as of the commit above (local paths shown as `{worktree}`, `{local}`). The four log sections are"
        " append-only.",
    ]
    # No H1: Confluence shows the page title. Separate quote paragraphs: the import joins consecutive quote lines.
    body = [x for h in header for x in (h, ">")][:-1] + [""]
    for s in SECTIONS:
        body += [f"## {s}", ""] + (logs[s] or [EMPTY]) + [""]
    body += [f"## {a.plan_title}", "", demote(plan.strip(), 2), ""]
    text = sanitize("\n".join(body), a.repo)
    refuse_secrets(text, "the page body")
    Path(a.out).write_text(text)
    digest = hashlib.sha256(text.rstrip().encode()).hexdigest()[:16]
    print(f"ticket_page: wrote {a.out} ({len(text)} chars, sha256 {digest}; {a.plan_title} {a.plan} as of {sha}; "
          + ", ".join(f"{s}: {len(logs[s])}" for s in SECTIONS)
          + f"; {added} new, {restored} restored from the sent log)")
    return 0


def cmd_queue(a):
    d = store_dir(a.repo, a.outbox)
    box, sent = d / f"{a.key}.jsonl", d / f"{a.key}.sent.jsonl"
    if a.add:
        sec, source, text = a.add
        if sec not in SECTIONS:
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
    for kv in a.set or []:
        k, sep, v = kv.partition("=")
        if not k or not sep:
            die(f"bad --set {kv!r}, expected NAME=VALUE")
        st[k] = v
    if a.set:
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


def cmd_verify(a):
    want = Path(a.body).read_text().rstrip()
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
    r.add_argument("--plan", required=True, help="repo-relative path of the plan (or RCA) file")
    r.add_argument("--plan-rev", help="revision to mirror it from (default HEAD)")
    r.add_argument("--plan-title", default="Plan", choices=["Plan", "RCA"])
    r.add_argument("--meta", required=True)
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
    q.add_argument("--date")
    s = sub.add_parser("state")
    s.add_argument("--repo", required=True)
    s.add_argument("--key", required=True)
    s.add_argument("--outbox")
    s.add_argument("--set", nargs="+", metavar="NAME=VALUE")
    s.add_argument("--save-body", metavar="BODY", help="record BODY as the last body sent (after a verified update)")
    v = sub.add_parser("verify")
    v.add_argument("--body", required=True)
    v.add_argument("--page-id", required=True)
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
    st = sub.add_parser("stub")
    st.add_argument("--key", required=True)
    z = sub.add_parser("sanitize")
    z.add_argument("--repo", required=True)
    z.add_argument("--max-chars", type=int, default=1500)
    a = ap.parse_args()
    try:
        return {"render": cmd_render, "queue": cmd_queue, "state": cmd_state, "verify": cmd_verify,
                "stub": cmd_stub, "summary": cmd_summary, "sanitize": cmd_sanitize}[a.cmd](a)
    except subprocess.CalledProcessError as e:
        die("git failed: " + (e.stderr or "").strip())
    except (OSError, ValueError, KeyError) as e:
        die(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    sys.exit(main())
