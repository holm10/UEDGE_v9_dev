#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""
Imports the To Do tickets of one Jira epic into the tracker (tracker #6). Jira is read by the agent through the
Atlassian MCP, never by this script: the input is a saved search result (the snapshot), e.g.
`searchJiraIssuesUsingJql` with `jql = parent = <EPIC> OR key = <EPIC>`, fields `summary, description, comment, status,
issuetype, parent, labels, issuelinks, created` and `responseContentFormat: markdown`.

Per run: the epic becomes an Epic issue, each To Do child a sub-issue (label `from-jira`, plus `ai-layer` when Jira has
it), all on the Project with Status To Do, the `Jira key` field and the Tier the Jira text states (else empty); "is
blocked by" links between imported tickets become relations. Then one tracker commit with the epic's `epic.md`,
`breakdown.md` (the Jira key -> T<N> mapping) and `progress.md`, and each ticket's record through `ticket_page.py`
(create, status Backfilled, owner and `PIV record` comments logged). The body's first line names the Jira key, so a
re-run creates nothing that exists. The tracker is named only in `.claude/tracker.toml`.

Exit codes: 0 ok; 1 refused (secret-like text; nothing written); 2 bad input, a failed `gh` call or record call.
"""
import argparse
import fcntl
import json
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ticket_page as tp  # noqa: E402

HELPER = Path(__file__).resolve().parent / "ticket_page.py"
TYPES = {"Story": "Feature", "Task": "Task", "Bug": "Bug", "Epic": "Epic", "Sub-task": "Task", "Subtask": "Task"}
FIRST = re.compile(r"_Imported from Jira ([A-Z][A-Z0-9]*-\d+) ")


def die(msg, code=2):
    print("jira_import: " + msg, file=sys.stderr)
    sys.exit(code)


def load(paths):
    issues = {}
    for p in paths:
        d = json.loads(Path(p).read_text())
        if d.get("nextPageToken") or d.get("isLast") is False:
            die(f"{p} is not the last page of its search; save every page and pass each one")
        for i in d["issues"]:
            f = i["fields"]
            if i["key"] in issues:
                die(f"{i['key']} is in two snapshots")
            if "comment" not in f or "description" not in f:
                die(f"{i['key']}: the snapshot lacks the comment or description field; fetch them")
            c = f["comment"] or {}
            if c.get("total", 0) != len(c.get("comments", [])):
                die(f"{i['key']}: {len(c.get('comments', []))} of {c.get('total')} comments in the snapshot; "
                    "re-fetch it with getJiraIssue")
            issues[i["key"]] = i
    return issues


def comments(i):
    return (i["fields"]["comment"] or {}).get("comments", [])


def kind(i):
    return i["fields"]["issuetype"]["name"]


def ai(i):
    return "ai-layer" in (i["fields"].get("labels") or [])


def tier(i):
    text = (i["fields"].get("description") or "") + "\n" + "\n".join(c["body"] for c in comments(i))
    hits = re.findall(r"\bTier[: ]+\**([SML])\b", text)
    return hits[-1] if hits else ""


def links(i):
    out = []
    for ln in i["fields"].get("issuelinks") or []:
        for side, word in (("outwardIssue", ln["type"]["outward"]), ("inwardIssue", ln["type"]["inward"])):
            if side in ln:
                out.append((word, ln[side]["key"], ln[side]["fields"]["status"]["name"]))
    return out


def first_line(text):
    return tp.one_line(next((x for x in text.strip().split("\n") if x.strip()), "")).strip("*_ ")


def body(i, today):
    f = i["fields"]
    out = [f"_Imported from Jira {i['key']} ({kind(i)}, {f['status']['name']}, created {(f.get('created') or '')[:10]})"
           f" on {today}. Jira is the read-only archive; this issue and its record carry the ticket on._", "",
           "## Jira description", "", (f.get("description") or "").strip() or "none", "", "## Jira comments", ""]
    out += ["none", ""] if not comments(i) else []
    for c in comments(i):
        out += [f"#### Comment {c['id']} ({c['created'][:10]})", "", c["body"].strip(), ""]
    if kind(i) != "Epic":
        t = tier(i)
        out += [f"Tier: {t} (stated in the Jira text)" if t else "Tier: not stated (set at plan-feature)",
                "Branch: feature/v9-ai-<slug> (ai-layer)" if ai(i) else "Branch: feature/v9-T<N>-<slug>"]
    out += ["Jira links: " + ("; ".join(f"{w} {k} ({s})" for w, k, s in links(i)) or "none"),
            "Jira labels: " + (", ".join(x for x in f.get("labels") or [] if x != "ai-layer") or "none")]
    return "\n".join(out) + "\n"


class Run:
    def __init__(self, a, t):
        self.a, self.t, self.dry, self.failed = a, t, a.dry_run, False
        self.new = 0

    def gh(self, *args, read=False):
        if self.dry and not read:
            print("would run: gh " + " ".join(args))
            return ""
        return tp.gh(*args)

    def helper(self, *args):
        cmd = [sys.executable, str(HELPER), "--repo", self.a.repo, "--date", self.t.today, "--caller", "jira-import"]
        cmd += ["--tracker-dir", str(self.t.dir)] + list(args)
        if self.dry:
            print("would run: ticket_page.py " + " ".join(args))
            return
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            self.failed = True
            print(f"jira_import: ticket_page.py {' '.join(args[:2])} failed: {r.stderr.strip()}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", action="append", required=True, help="a saved MCP search result (repeatable)")
    ap.add_argument("--epic", required=True, help="the Jira epic key, e.g. AIUE-299")
    ap.add_argument("--first", help="the ticket to import first after the epic")
    ap.add_argument("--out", required=True, help="the mapping JSON to write; bodies go to <its dir>/bodies/")
    ap.add_argument("--dry-run", action="store_true", help="read only; print each write")
    ap.add_argument("--repo", default=".", help="the UEDGE checkout (worktree) the call comes from")
    ap.add_argument("--tracker-dir", help="the tracker checkout (default: next to the main checkout)")
    ap.add_argument("--date", help="the import date (default: today)")
    a = ap.parse_args()
    a.date = a.date or date.today().isoformat()
    issues = load(a.snapshot)
    epic = issues.get(a.epic) or die(f"the epic {a.epic} is not in the snapshot")
    kids = [i for i in issues.values() if (i["fields"].get("parent") or {}).get("key") == a.epic]
    take = [i for i in kids if i["fields"]["status"]["statusCategory"]["key"] == "new"]
    others = [i for i in kids if i not in take]
    if a.first and a.first not in [i["key"] for i in take]:
        die(f"--first {a.first} is not a To Do child of {a.epic} in the snapshot")
    take.sort(key=lambda i: (i["key"] != a.first, int(i["key"].rsplit("-", 1)[1])))
    bodies = {}
    for i in [epic, *take]:  # every text is checked before anything is written
        text = body(i, a.date) + i["fields"]["summary"]
        tp.refuse_secrets(text, f"Jira {i['key']}")
        bodies[i["key"]] = tp.sanitize(body(i, a.date), a.repo)
    out = Path(a.out)
    (out.parent / "bodies").mkdir(parents=True, exist_ok=True)
    for k, b in bodies.items():
        (out.parent / "bodies" / f"{k}.md").write_text(b)

    t = tp.Tracker(a)
    fcntl.flock(t.lock, fcntl.LOCK_UN)  # held again only around the epic-docs commit
    r = Run(a, t)
    seen = {}
    for x in json.loads(tp.gh("issue", "list", "-R", t.slug, "--label", "from-jira", "--state", "all", "--limit",
                              "1000", "--json", "number,body,url")):
        m = FIRST.match(x["body"] or "")
        if m:
            seen[m.group(1)] = x
    fields = {f["name"]: f for f in json.loads(tp.gh("project", "field-list", str(t.project), "--owner", t.owner,
                                                      "--format", "json"))["fields"]}
    for name in ("Status", "Tier", "Jira key"):
        fields.get(name) or die(f"the Project has no '{name}' field")
    pid = json.loads(tp.gh("project", "view", str(t.project), "--owner", t.owner, "--format", "json"))["id"]
    def item_list():
        return {it["content"]["number"]: it for it in json.loads(tp.gh(
            "project", "item-list", str(t.project), "--owner", t.owner, "--format", "json", "--limit", "1000"))["items"]
            if (it.get("content") or {}).get("repository") == t.slug and "number" in it["content"]}
    items = item_list()

    def item_for(n, url):
        """The issue's Project item. The Project may add a new issue itself between the create and the item-add,
        which then fails with "already exists" (seen on the AIUE-299 import): read the item list again."""
        if n in items:
            return items[n]
        if r.dry:
            r.gh("project", "item-add", str(t.project), "--owner", t.owner, "--url", url)
            return {"id": f"ITEM-{n}"}
        res = tp.run(["gh", "project", "item-add", str(t.project), "--owner", t.owner, "--url", url, "--format",
                      "json", "--jq", ".id"], check=False)
        if res.returncode == 0:
            return {"id": res.stdout.strip()}
        if "already exists" not in res.stderr:
            die(f"gh project item-add failed: {res.stderr.strip()}")
        for _ in range(5):  # the item list can lag behind the Project's own add by seconds (#20 on AIUE-299)
            items.update(item_list())
            if n in items:
                return items[n]
            time.sleep(2)
        die(f"#{n}: item-add says it is on the Project, but the item list still lacks it; re-run in a minute")

    def opt(field, name):
        return next((o["id"] for o in fields[field]["options"] if o["name"] == name), None) \
            or die(f"the Project's {field} has no option '{name}'")

    def edit(item, field, **v):
        flag, val = next(iter(v.items()))
        r.gh("project", "item-edit", "--id", item, "--project-id", pid, "--field-id", fields[field]["id"],
             f"--{flag.replace('_', '-')}", val)

    num, rows = {}, []
    for i in [epic, *take]:
        k, title = i["key"], tp.one_line(tp.sanitize(i["fields"]["summary"], a.repo))
        if k in seen:
            n, url, created = seen[k]["number"], seen[k]["url"], False
        else:
            args = ["issue", "create", "-R", t.slug, "--type", TYPES.get(kind(i), "Task"), "--title", title,
                    "--body-file", str(out.parent / "bodies" / f"{k}.md"), "--label", "from-jira"]
            args += ["--label", "ai-layer"] if ai(i) else []
            args += ["--parent", str(num[a.epic])] if i is not epic else []
            r.new += 1
            url = r.gh(*args).strip().split("\n")[-1] or f"#new-{r.new}"
            n, created = (int(url.rstrip("/").rsplit("/", 1)[1]) if not r.dry else f"new-{r.new}"), True
        num[k] = n
        item = item_for(n, url)
        if not item.get("status"):
            edit(item["id"], "Status", single_select_option_id=opt("Status", "To Do"))
        if i is not epic and tier(i) and not item.get("tier"):
            edit(item["id"], "Tier", single_select_option_id=opt("Tier", tier(i)))
        if not item.get("jira key"):
            edit(item["id"], "Jira key", text=k)
        rows.append({"jira": k, "number": n, "url": url, "created": created, "title": title, "issue": i})

    for row in rows[1:]:  # "is blocked by" between imported tickets
        want = [str(num[k]) for w, k, _ in links(row["issue"]) if w == "is blocked by" and k in num]
        have = [] if r.dry or not want else json.loads(r.gh(
            "api", f"repos/{t.slug}/issues/{row['number']}/dependencies/blocked_by", "--jq", "[.[].number]",
            read=True) or "[]")
        missing = [m for m in want if m not in map(str, have)]
        if missing:
            r.gh("issue", "edit", str(row["number"]), "-R", t.slug, "--add-blocked-by", ",".join(missing))

    # The epic's documents: one commit (written under --out's directory instead with --dry-run).
    E = num[a.epic]
    fcntl.flock(t.lock, fcntl.LOCK_EX)
    if not r.dry:
        t.pull()
    edir = next(iter(sorted(t.dir.glob(f"docs/T{E}-*/"))), None) or t.dir / "docs" / f"T{E}-{tp.slug(rows[0]['title'])}"
    if r.dry:
        edir = out.parent / "epic"
    edir.mkdir(parents=True, exist_ok=True)
    changed = epic_docs(a, edir, E, rows, others)
    if changed and not r.dry:
        t.commit(changed, f"T{E} jira-import: epic documents from {a.epic}")
    else:
        fcntl.flock(t.lock, fcntl.LOCK_UN)

    for row in rows[1:]:  # each ticket's record, through ticket_page.py
        i, n = row["issue"], row["number"]
        if not r.dry and t.record(n):
            row["record"] = str(t.record(n).relative_to(t.dir))
            continue
        cs = comments(i)
        r.helper("create", f"T{n}")
        r.helper("status", f"T{n}", "Backfilled", f"Ticket section: imported from Jira {row['jira']} on {a.date} "
                 f"(description and {len(cs)} comments), not as filed; Tier "
                 + (f"{tier(i)} (stated in the Jira text)" if tier(i) else "not stated, set at plan-feature"))
        for c in cs:
            if re.match(r"\W*Owner\b", c["body"]):
                r.helper("log", f"T{n}", "Findings and decisions", f"Owner (Jira {row['jira']} comment {c['id']}, "
                         f"{c['created'][:10]}; quoted in the Ticket section): {first_line(c['body'])}")
            elif re.match(r"\W*PIV record\b", c["body"]):
                r.helper("log", f"T{n}", "Progress", f"Jira PIV record comment {c['id']} ({c['created'][:10]}): "
                         f"{first_line(c['body'])}")
        rec = None if r.dry else t.record(n)
        row["record"] = str(rec.relative_to(t.dir)) if rec else None

    mapping = [{k: v for k, v in row.items() if k != "issue"} for row in rows]
    out.write_text(json.dumps(mapping, indent=1) + "\n")
    print(f"{'Jira key':10} {'ticket':9} {'created':8} {'tier':5} record")
    for row in rows:
        print(f"{row['jira']:10} T{str(row['number']):8} {str(row['created']):8} "
              f"{(tier(row['issue']) if row['issue'] is not epic else 'epic') or '-':5} {row.get('record') or '-'}")
    print(f"jira_import: {r.new} {'to create' if r.dry else 'created'}, {len(rows) - r.new} already imported; "
          f"mapping: {out}")
    sys.exit(2 if r.failed else 0)


def epic_docs(a, edir, E, rows, others):
    """Writes the epic's epic.md, breakdown.md and progress.md where missing or incomplete; returns the paths it
    changed."""
    epic, tickets, changed = rows[0], rows[1:], []
    f = epic["issue"]["fields"]
    em = edir / "epic.md"
    if not em.exists():
        owner = [f"- {c['created'][:10]} Owner: {first_line(c['body'])} (Jira {a.epic} comment {c['id']})"
                 for c in comments(epic["issue"]) if re.match(r"\W*Owner\b", c["body"])]
        done = [f"{i['key']} ({i['fields']['status']['name']})" for i in others]
        em.write_text(
            f"# T{E}: {epic['title']}\n\n| | |\n|---|---|\n| Issue | #{E} (type Epic) |\n| Status | In progress |\n"
            f"| Breakdown | `breakdown.md` |\n| Progress | `progress.md` |\n| Last update | {a.date} |\n\n"
            f"## Goal\n\nImported from Jira {a.epic} on {a.date}; its description follows verbatim (Scope).\n\n"
            f"## Scope\n\n{tp.demote(tp.sanitize((f.get('description') or 'none').strip(), a.repo))}\n\n"
            "## Success criteria\n\nNot stated in Jira; to be set by the owner or `create-prd T" + str(E) + "`.\n\n"
            "## Jira status of the other children\n\nChildren not imported (Done ones finished in Jira, In Progress "
            "ones finish there): " + (", ".join(done) or "none") + ".\n\n"
            "## Decisions\n\n" + "".join(x + "\n" for x in owner)
            + f"- {a.date} Agent: imported from Jira {a.epic} with its {len(tickets)} To Do children by "
            "`jira_import.py` (tracker #6).\n\n## Reviews\n")
        changed.append(em)
    bd = edir / "breakdown.md"
    text = bd.read_text() if bd.exists() else (
        f"# T{E}: {epic['title']}, ticket breakdown\n\nThe source is Jira {a.epic} (imported {a.date}; each ticket's "
        "scope is the Ticket section of its record). Each ticket is a sub-issue of #" + str(E) + ". Dependencies are "
        "also set as \"blocked by\" relations on the issues.\n\n| Jira key | Ticket | Type | Tier | Blocked by |\n"
        "|---|---|---|---|---|\n")
    num = {row["jira"]: row["number"] for row in rows}
    add_rows, add_entries = [], []
    for row in tickets:
        n, i = row["number"], row["issue"]
        if f"## T{n}: " in text:
            continue
        dep = ", ".join(f"T{num[k]}" for w, k, _ in links(i) if w == "is blocked by" and k in num) or "none"
        typ, ti = TYPES.get(kind(i), "Task"), tier(i) or "not stated"
        add_rows.append(f"| {row['jira']} | T{n} | {typ} | {ti} | {dep} |")
        branch = "`feature/v9-ai-<slug>` (AI-layer work)" if ai(i) else f"`feature/v9-T{n}-<slug>`"
        add_entries.append(f"## T{n}: {row['title']}\n\n- **Issue:** #{n} · **Type:** {typ} · **Tier:** {ti}\n"
                           f"- **Branch:** {branch}\n- **Depends on:** {dep}\n- **Jira key:** {row['jira']}\n"
                           f"- **Record:** `T{n}-{tp.slug(row['title'])}/record.md`\n")
    if add_rows:
        lines = text.rstrip("\n").split("\n")
        last = max(j for j, ln in enumerate(lines) if ln.startswith("|"))
        lines[last + 1:last + 1] = add_rows
        bd.write_text("\n".join(lines) + "\n\n" + "\n".join(add_entries))
        changed.append(bd)
    pg = edir / "progress.md"
    if add_rows or not pg.exists():
        old = pg.read_text().rstrip("\n") + "\n" if pg.exists() else (
            f"# T{E}: {epic['title']}, progress\n\nDated, append-only lines, one per milestone of any ticket in the "
            "epic. Owner decisions are attributed as `Owner:` with their source.\n\n")
        pg.write_text(old + f"- {a.date} T{E} (jira-import): imported {len(add_rows)} tickets from Jira {a.epic}.\n")
        changed.append(pg)
    return changed


if __name__ == "__main__":
    main()
