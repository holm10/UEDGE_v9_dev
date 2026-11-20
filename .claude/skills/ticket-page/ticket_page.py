#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""
Helper of the `ticket-page` skill (SKILL.md next to this file): keeps a tracker ticket's record, the issue plus
`docs/<epic>/T<N>-<slug>/record.md` (and `plan.md` or `rca.md`) in the tracker checkout. Every write is one commit,
pushed after a rebase onto the remote, under a lock on the checkout; there is no queue (owner, 2026-11-18, tracker #2).
The tracker is named only in `.claude/tracker.toml`.

  create   T<N>                          the record (Ticket section from the issue), or the existing one's path
  publish  T<N> [--plan F | --rca F]     plan.md / rca.md next to the record, cited by date and sha256
  log      T<N> <Section> <text>         one dated entry in an append-only section (multi-line text is fenced)
  status   T<N> <Status> [note]          header status, Project Status, issue closed on Committed
  progress T<N> <text>                   one line in the epic's progress.md
  sanitize [--max-chars N]               stdin -> stdout: local paths masked, secret-like strings refused
Global options (before the command): --caller <skill> (shown in the entry), --repo, --tracker-dir, --date.

Exit codes: 0 ok (a failed fetch or push is reported; the commit stays and the next call pushes it); 1 refused
(secret-like string, over --max-chars); 2 could not run (bad key, section or status, two records, a dirty checkout or
one on another branch, a rebase conflict, a retired subcommand, any other error).
"""
import argparse
import fcntl
import hashlib
import json
import re
import os
import subprocess
import sys
import time
import tomllib
from datetime import date
from pathlib import Path

SECTIONS = ["Progress", "Validation", "Reviews", "Findings and decisions"]
# Owner, 2026-11-18 (tracker #2); Backfilled and Escalated are the agent's additions (Escalated: work stays open).
STATUSES = {"Planned": "To Do", "Backfilled": "To Do", "Planning": "In Progress", "Executing": "In Progress",
            "Validating": "In Progress", "Plan review": "In Review", "Implementation review": "In Review",
            "Approved": "In Review", "Escalated": "In Progress", "Committed": "Done"}
RETIRED = ["find", "ticket", "render", "verify", "extract-plan"]
AGENT = "_Posted by an agent through the owner's account._"

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


def die(msg, code=2):
    print("ticket_page: " + msg, file=sys.stderr)
    sys.exit(code)


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


def clean(text, a):
    refuse_secrets(text, "the text")
    return sanitize(text, a.repo)


def one_line(text):
    return " ".join(text.split())


def run(cmd, cwd=None, check=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode:
        die(f"{' '.join(cmd[:3])} failed: {r.stderr.strip()}")
    return r


# `gh project` reports a rate-limited owner lookup as "unknown owner type" (seen on the T28 import, 2026-11-19).
RATE = re.compile(r"rate limit|unknown owner type", re.I)


RATE_JQ = r'.resources|[.graphql,.core]|map("\(.remaining) \(.reset)")|.[]'  # one "remaining reset" line each


def gh_run(args, check=True):
    """Runs `gh`, waiting out a GitHub rate limit (tracker #28): a secondary limit 60 s per attempt, a primary one until
    the reset of the exhausted resource (graphql or core; `gh api rate_limit` itself costs nothing), or, with neither
    at zero (a burst limit rate_limit does not show), 120 s per attempt. At most 4 retries;
    TICKET_PAGE_MAX_WAIT caps each wait (s) and the printed line shows the computed wait before the cap. Any other
    failure is returned (check=False) or fatal, as before."""
    cap = float(os.environ.get("TICKET_PAGE_MAX_WAIT", "3700"))
    for k in range(1, 6):
        r = run(["gh", *args], check=False)
        limited = r.returncode != 0 and RATE.search(r.stderr)
        if not limited or k == 5:
            break
        if "secondary" in r.stderr.lower():
            wait = 60.0 * k
        else:
            q = run(["gh", "api", "rate_limit", "--jq", RATE_JQ], check=False)
            rows = [ln.split() for ln in q.stdout.split("\n")] if q.returncode == 0 else []
            resets = [float(x[1]) for x in rows if len(x) == 2 and x[0] == "0" and x[1].isdigit()]  # exhausted ones
            # neither at zero: a burst limit that rate_limit does not show (T28: it lasted about 5-10 min)
            wait = max(resets) - time.time() + 5 if resets else 120.0 * k
        capped = min(max(wait, 0.0), cap)
        print(f"ticket_page: GitHub rate limit; waiting {capped:.0f} s (computed {wait:.0f} s, retry {k}/4)",
              file=sys.stderr)
        time.sleep(capped)
    if check and r.returncode:
        die(f"gh {' '.join(args[:2])} failed: {r.stderr.strip()}")
    return r


def gh(*args):
    return gh_run(list(args)).stdout


def slug(title):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", title.lower())).strip("-")[:40].rstrip("-")


def fenced(lines):
    """Per line: inside (or on) a code fence; and the fence still open at the end. A fence closes on the same character
    at least as long (CommonMark)."""
    out, fence = [], None
    for ln in lines:
        m = re.match(r"^\s*(`{3,}|~{3,})", ln)
        if m and (fence is None or (m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence))):
            fence = m.group(1) if fence is None else None
            out.append(True)
        else:
            out.append(fence is not None)
    return out, fence


def demote(md):
    """H1/H2 lines outside code fences become H3, and an unclosed fence is closed, so a body never ends or hides a
    record section."""
    lines = md.split("\n")
    inside, fence = fenced(lines)
    out = [ln if f else re.sub(r"^#{1,2}(\s)", r"###\1", ln) for ln, f in zip(lines, inside)]
    return "\n".join(out + ([fence] if fence else []))


def entry(today, caller, text):
    """`- <date> (<caller>): <first line>`; further lines go into an indented code fence (never a heading)."""
    first, *rest = text.strip("\n").split("\n")
    out = f"- {today} ({caller}): {first}"
    if rest:
        fence = "`" * max(3, 1 + max((len(x) for x in re.findall(r"`+", text)), default=0))
        out += "\n" + "\n".join("  " + ln for ln in [fence + "text", *rest, fence])
    return out


class Tracker:
    def __init__(self, a):
        common = Path(run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=a.repo)
                      .stdout.strip())
        cfg = tomllib.loads((common.parent / ".claude" / "tracker.toml").read_text())["tracker"]
        self.owner, self.repo, self.project = cfg["owner"], cfg["repo"], int(cfg["project"])
        self.slug = f"{self.owner}/{self.repo}"
        self.dir = Path(a.tracker_dir) if a.tracker_dir else common.parent.parent / self.repo
        if not self.dir.exists():
            run(["gh", "repo", "clone", self.slug, str(self.dir)])
        self.today = a.date or date.today().isoformat()
        self.lock = open(Path(run(["git", "rev-parse", "--absolute-git-dir"], cwd=self.dir).stdout.strip())
                         / "ticket-page.lock", "w")
        try:  # one write at a time in this checkout, from the checks to the push (released in commit)
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("ticket_page: waiting for another ticket-page call on the tracker checkout", file=sys.stderr)
            fcntl.flock(self.lock, fcntl.LOCK_EX)

    def issue(self, n):
        q = ("query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){issue(number:$n){title body "
             "issueType{name} parent{number title} projectItems(first:10){nodes{id project{number} "
             "tier:fieldValueByName(name:\"Tier\"){... on ProjectV2ItemFieldSingleSelectValue{name}}}}}}}")
        out = json.loads(gh("api", "graphql", "-f", f"query={q}", "-f", f"o={self.owner}", "-f", f"r={self.repo}",
                            "-F", f"n={n}"))
        issue = out["data"]["repository"]["issue"] or die(f"issue #{n} not found in {self.slug}")
        items = [i for i in issue["projectItems"]["nodes"] if i["project"]["number"] == self.project]
        issue["item"] = items[0] if items else None
        return issue

    def record(self, n):
        hits = sorted(self.dir.glob(f"docs/*/T{n}-*/record.md"))
        if len(hits) > 1:
            die(f"T{n} has {len(hits)} records: " + ", ".join(str(h.relative_to(self.dir)) for h in hits))
        return hits[0] if hits else None

    def pull(self):
        """Checks, then `git pull --rebase` in two steps: an unreachable remote -> write locally (the next call
        pushes); a rebase conflict -> write nothing."""
        dirty = run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=self.dir).stdout.strip()
        if dirty:
            die(f"the tracker checkout has uncommitted changes; nothing written (commit or discard them):\n{dirty}")
        head = run(["git", "symbolic-ref", "--short", "-q", "HEAD"], cwd=self.dir, check=False).stdout.strip()
        main = run(["git", "symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD"], cwd=self.dir,
                   check=False).stdout.strip().removeprefix("origin/") or "main"
        if head != main:
            die(f"the tracker checkout is on '{head or 'a detached HEAD'}', not '{main}'; records go to '{main}'")
        fetch = run(["git", "fetch", "-q"], cwd=self.dir, check=False)
        if fetch.returncode:
            print(f"ticket_page: fetch failed, writing locally (pushed on the next call): {fetch.stderr.strip()}")
            return
        if run(["git", "rebase", "-q", "@{u}"], cwd=self.dir, check=False).returncode:
            run(["git", "rebase", "--abort"], cwd=self.dir, check=False)
            die("rebase onto the tracker's remote failed; nothing written (resolve it in the tracker checkout)")

    def commit(self, paths, message):
        paths = [str(p) for p in paths]
        run(["git", "add", "--", *paths], cwd=self.dir)
        run(["git", "commit", "-q", "-m", message, "--", *paths], cwd=self.dir)
        sha = run(["git", "rev-parse", "--short", "HEAD"], cwd=self.dir).stdout.strip()
        push = run(["git", "push", "-q"], cwd=self.dir, check=False)
        fcntl.flock(self.lock, fcntl.LOCK_UN)  # the GitHub calls that follow don't hold up other writers
        if push.returncode:
            print(f"ticket_page: committed {sha}, push failed (retried on the next call): {push.stderr.strip()}")
        return sha

    def set_status(self, issue, status):
        if not issue["item"]:
            print(f"ticket_page: the issue is not on Project {self.project}; Project Status not set")
            return
        fields = json.loads(gh("project", "field-list", str(self.project), "--owner", self.owner, "--format", "json"))
        f = next((f for f in fields["fields"] if f["name"] == "Status"), None) or die("the Project has no Status")
        opt = next((o["id"] for o in f["options"] if o["name"] == STATUSES[status]), None) \
            or die(f"the Project's Status has no option '{STATUSES[status]}'")
        pid = json.loads(gh("project", "view", str(self.project), "--owner", self.owner, "--format", "json"))["id"]
        gh("project", "item-edit", "--id", issue["item"]["id"], "--project-id", pid, "--field-id", f["id"],
           "--single-select-option-id", opt)


def key_number(key):
    m = re.fullmatch(r"T(\d+)", key)
    if not m:
        die(f"'{key}' is not a tracker key (T<N>). Jira keys are archived: an imported ticket has its own T<N> (the "
            "Project's `Jira key` field), and Jira itself is in the tracker's docs/archive/jira/")
    return int(m.group(1))


def add_entry(text, section, item):
    """Append `item` as the last entry of `## section` (before the next `## ` heading, or at the end)."""
    lines = text.rstrip("\n").split("\n")
    heads = [i for i, (ln, f) in enumerate(zip(lines, fenced(lines)[0])) if not f and ln.startswith("## ")]
    hits = [i for i in heads if lines[i] == f"## {section}"]
    if not hits:
        die(f"the record has no '## {section}' section")
    start = hits[-1]  # the record's own heading: the log sections follow the Ticket section
    end = next((i for i in heads if i > start), len(lines))
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    new = [item] if end > start + 1 else ["", item]
    lines[end:end] = new
    if end + len(new) < len(lines) and lines[end + len(new)].startswith("## "):
        lines.insert(end + len(new), "")
    return "\n".join(lines) + "\n"


def set_row(text, row, value):
    cell = one_line(value).replace("|", "\\|")
    new, n = re.subn(rf"^\| {re.escape(row)} \|.*\|$", lambda m: f"| {row} | {cell} |", text, count=1, flags=re.M)
    return new if n else die(f"the record has no '{row}' header row")


def need_record(t, n):
    return t.record(n) or die(f"T{n} has no record yet: run `create T{n}` first")


def write_record(t, rec, text, message, extra=()):
    rec.write_text(set_row(text, "Last update", t.today))
    return t.commit([rec, *extra], message)


def cmd_create(a, t, n):
    t.pull()
    if (rec := t.record(n)):
        print(f"ticket_page: record exists: {rec.relative_to(t.dir)}")
        return
    issue = t.issue(n)
    title = one_line(clean(issue["title"], a))
    if issue["parent"]:
        e = issue["parent"]
        epic = next(iter(sorted(t.dir.glob(f"docs/T{e['number']}-*/"))), None) \
            or t.dir / "docs" / f"T{e['number']}-{slug(e['title'])}"
        epic_cell = f"#{e['number']} `docs/{epic.name}/`"
    else:
        epic, epic_cell = t.dir / "docs" / "no-epic", "none"
    rec = epic / f"T{n}-{slug(title)}" / "record.md"
    tier = ((issue["item"] or {}).get("tier") or {}).get("name", "")
    kind = (issue["issueType"] or {}).get("name", "")
    rows = [("Issue", f"#{n}"), ("Epic", epic_cell), ("Type / tier", f"{kind} / {tier}"), ("Branch", ""), ("PR", ""),
            ("Status", "Planned"), ("Plan", "not written yet"), ("Last update", t.today)]
    text = (f"# T{n}: {title}\n\n| | |\n|---|---|\n" + "".join(f"| {k} | {v} |\n" for k, v in rows)
            + "\n_Records are written by agents through the owner's account; attribution follows the README._\n\n"
            + f"## Ticket\n\n{demote(clean(issue['body'] or '', a)).strip()}\n\nSource: issue #{n} as filed "
            + f"({t.today}).\n\n" + "".join(f"## {s}\n\n" for s in SECTIONS))
    rec.parent.mkdir(parents=True, exist_ok=True)
    write_record(t, rec, add_entry(text, "Progress", entry(t.today, a.caller, "record created.")), f"T{n} create")
    print(f"ticket_page: record created: {rec.relative_to(t.dir)}")


def cmd_publish(a, t, n):
    kind = "rca" if a.rca else "plan"
    src = Path(a.rca or a.plan or Path(a.repo) / ".claude" / "work" / f"T{n}" / "plan.md")
    body = clean(src.read_text(), a)
    sha = hashlib.sha256(body.encode()).hexdigest()[:12]  # of the published (masked) text
    t.pull()
    rec = need_record(t, n)
    (rec.parent / f"{kind}.md").write_text(body)
    text = set_row(rec.read_text(), "Plan", f"`{kind}.md`, published {t.today}, sha256 {sha}")
    text = add_entry(text, "Progress", entry(t.today, a.caller, f"{kind} published (sha256 {sha})."))
    write_record(t, rec, text, f"T{n} publish: {kind}", [rec.parent / f"{kind}.md"])
    path = f"{rec.parent.relative_to(t.dir)}/{kind}.md"
    gh("issue", "comment", str(n), "-R", t.slug, "--body",
       f"{'RCA' if kind == 'rca' else 'Plan'} published {t.today} (sha256 {sha}): `{path}`. {AGENT}")
    print(f"ticket_page: {kind} published: {path}")


def cmd_log(a, t, n):
    if a.section not in SECTIONS:
        die(f"unknown section '{a.section}'; one of: {', '.join(SECTIONS)}")
    item = entry(t.today, a.caller, clean(" ".join(a.text), a))
    t.pull()
    rec = need_record(t, n)
    sha = write_record(t, rec, add_entry(rec.read_text(), a.section, item), f"T{n} log: {a.section}")
    print(f"ticket_page: {a.section} entry added ({sha})")


def cmd_status(a, t, n):
    if a.status not in STATUSES:
        die(f"unknown status '{a.status}'; one of: {', '.join(STATUSES)}")
    note = one_line(clean(" ".join(a.note), a))
    t.pull()
    rec = need_record(t, n)
    text = set_row(rec.read_text(), "Status", a.status + (f" ({note})" if note else ""))
    text = add_entry(text, "Progress", entry(t.today, a.caller, f"status {a.status}" + (f": {note}" if note else "")))
    sha = write_record(t, rec, text, f"T{n} status: {a.status}")
    t.set_status(t.issue(n), a.status)
    what = f"{a.status}{': ' + note if note else ''}. Record: `{rec.relative_to(t.dir)}`. {AGENT}"
    if a.status == "Committed":
        gh("issue", "close", str(n), "-R", t.slug, "--reason", "completed", "--comment", what)
    elif a.status == "Escalated":
        gh("issue", "comment", str(n), "-R", t.slug, "--body", what)
    print(f"ticket_page: status {a.status} ({sha}); Project Status {STATUSES[a.status]}")


def cmd_progress(a, t, n):
    line = f"- {t.today} T{n} ({a.caller}): {one_line(clean(' '.join(a.text), a))}"
    t.pull()
    rec = need_record(t, n)
    if rec.parent.parent.name == "no-epic":
        print(f"ticket_page: T{n} has no epic, so no epic progress log")
        return
    log = rec.parent.parent / "progress.md"
    old = log.read_text() if log.exists() else f"# {rec.parent.parent.name}: progress\n\n"
    log.write_text(old.rstrip("\n") + f"\n{line}\n")
    print(f"ticket_page: epic progress line added ({t.commit([log], f'T{n} progress')})")


def main():
    argv = sys.argv[1:]
    if argv and (argv[0] in RETIRED or (argv[0] == "progress" and "--new" in argv)):
        die(f"'{' '.join(argv[:2])}' was retired with the Confluence route (tracker #2): see ticket-page SKILL.md")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", help="the UEDGE checkout (worktree) the call comes from")
    ap.add_argument("--tracker-dir", help="the tracker checkout (default: next to the main checkout)")
    ap.add_argument("--date", help="entry date (default: today)")
    ap.add_argument("--caller", default="agent", help="the skill or person writing (shown in the entry)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("create", "publish", "log", "status", "progress"):
        p = sub.add_parser(name)
        p.add_argument("key")
        if name == "publish":
            g = p.add_mutually_exclusive_group()
            g.add_argument("--plan")
            g.add_argument("--rca")
        elif name == "log":
            p.add_argument("section")
            p.add_argument("text", nargs="+")
        elif name == "status":
            p.add_argument("status")
            p.add_argument("note", nargs="*")
        elif name == "progress":
            p.add_argument("text", nargs="+")
    p = sub.add_parser("sanitize")
    p.add_argument("--repo", default=argparse.SUPPRESS)  # callers pass it after the command (rca)
    p.add_argument("--max-chars", type=int)
    a = ap.parse_args()
    if a.cmd == "sanitize":
        text = sys.stdin.read()
        refuse_secrets(text, "stdin")
        out = sanitize(text, a.repo)
        if a.max_chars and len(out) > a.max_chars:
            die(f"{len(out)} chars is over the cap of {a.max_chars}; summarise", 1)
        sys.stdout.write(out)
        return
    n = key_number(a.key)
    try:
        globals()[f"cmd_{a.cmd}"](a, Tracker(a), n)
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as e:
        die(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
