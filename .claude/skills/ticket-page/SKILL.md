---
name: ticket-page
description: Keeps a ticket's hosted PIV record. For a Jira ticket under an epic with a PRD page, it keeps a Confluence page under the PRD (container "Ticket plans <EPIC>", page "Plan <KEY> - <summary>") that mirrors the ticket's plan (or RCA) and holds append-only Progress, Validation, Reviews and Findings-and-decisions sections, linked once from the ticket. A ticket with no epic or no PRD page gets a few short "PIV record" Jira comments instead. Entries are queued locally and sent only at milestones. Called by plan-feature, execute, validate, implement-fix and the end-to-end-feature review loop; never blocks them. Supports --dry-run and --no-tracker.
argument-hint: "<KEY> publish [--plan <path> | --rca <path>] | log <Section> <text> [--flush] | flush | status <status> [<note>] [--dry-run] [--no-tracker]"
---

# Ticket page: the hosted record of a ticket's PIV loop

## Why

The plan, the review reports and the validation records live on the ticket branch, which may sit in a local worktree
for days. The ticket record is the copy on the platform: the plan, what was done, what was measured, what the
reviewers said and what was decided, readable from the Jira ticket and still there if the worktree or the session is
lost. The repo stays the source of truth; the page mirrors it and logs the steps.

## Calls

- `<KEY>`: the Jira key (`AIUE-61`). Without one there is nothing to record: say so and return.
- `publish`: mirror the committed plan (`--plan <repo-relative path>`; default: the plan in `.claude/plans/` whose
  `**Branch / worktree**` line names the current branch) or, for `implement-fix`, the RCA (`--rca docs/rca/<file>.md`).
  Run it when the plan is written and each time it is revised or amended. It flushes.
- `log <Section> <text>`: queue one dated entry locally. `<Section>` is `Progress`, `Validation`, `Reviews` or
  `Findings and decisions`. **No Atlassian call** unless `--flush` is given.
- `flush`: send the queued entries (and the current status) now. Only at the milestones below.
- `status <status> [<note>]`: one of `Planning`, `Plan review`, `Executing`, `Validating`, `Implementation review`,
  `Approved`, `Escalated`, `Committed`, with an optional short note. Stored locally; goes out with the next flush.
- `--dry-run`: Atlassian reads only. Nothing is written to Atlassian, the repo or the local store; print what would
  be written. Callers pass it as `--tracker-dry-run`, so it is never mistaken for "don't write code".
- `--no-tracker` (alias `--no-confluence`): do nothing and say "ticket record skipped (--no-tracker)". Callers pass it
  on, also to sub-agents and to whoever they hand a review loop to.

## When to flush (milestones)

| Milestone | Who | What goes out |
|---|---|---|
| Plan (or RCA) written, revised or amended | `plan-feature`, `implement-fix`, the review loop | `publish` |
| A review round closes: APPROVE, or REVISE once its response is written | the review loop | the verdict and the response; for a plan revision this flush is the `publish` |
| End of `execute` | `execute` | **one** Progress summary (tasks, commits, deviations), the validate entries queued during it |
| A `validate` result | `validate` | its result: flushed at once when `validate` runs on its own; inside `execute`, `implement-fix` or `end-to-end-feature` it goes out with the flush that ends the same step (end of `execute`, or the review round whose re-validation it is) |
| An owner decision or an escalation | whoever records it | the Findings and decisions entry, `status Escalated` |
| The final commit | `commit` step of `end-to-end-feature` / `implement-fix` | Progress "Committed <sha>", `status Committed` |

Everything else is `log` without `--flush`. Per-task entries are not logged at all; `execute` sends one summary.

**Deliberate batching of `validate`.** The decision lists each validate result as a milestone. Every result does reach
the page (failures included, verbatim), but inside a larger step it rides on that step's flush instead of making its
own: a `validate` inside `execute` is followed by the end-of-`execute` flush, and a re-validation in a review round by
that round's flush. That saves one full-page flush per validate run (see Cost) and delays the entry by at most the
rest of the step.

**Cost.** The Confluence update tool takes the whole page body, which the model has to emit, so every flush costs
about the page size twice: for AIUE-61 (48.5 KB) about 14k output tokens to emit it, and about 14k input tokens to
have it in context first (reading `body.md`). Both stay in the session's context, so each flush grows it by about
28k tokens; reading the page back, only when someone else wrote since this worktree's last flush, adds about 14k
more. A ticket with one plan round and one implementation round flushes 5 times (publish, plan verdict, end of
execute, implementation verdict, commit): about 70k output tokens and 140k of context growth if one session runs them
all (`end-to-end-feature`); each extra review round adds one flush. The version check is one small CQL search. A
session that runs short of context should hand the flush to a fresh agent with the scratch directory, not skip it.
The Jira fallback costs little (comments of at most 1500 characters).

## Configuration

| Setting | Value |
|---|---|
| Container page | child of the epic's PRD page, title `Ticket plans: <EPIC>`, one per epic |
| Ticket page | child of the container, title `Plan: <KEY> - <Jira summary without trailing period>` |
| Page id in the repo | the plan's (or RCA's) Summary line `**Ticket page**: Confluence page <id> (<url>)`, or `**Ticket page**: none (no epic PRD page); PIV record in Jira comments on <KEY>` |
| Helper | `uv run .claude/skills/ticket-page/ticket_page.py` (`render`, `queue`, `state`, `verify`, `stub`, `summary`, `sanitize`; `--help`); its end-to-end test without Atlassian: `.claude/skills/ticket-page/selftest.sh` (run it after changing the helper) |
| Local store (untracked, per worktree) | `<git dir>/ticket-page-outbox/`: `<KEY>.jsonl` (queued), `<KEY>.sent.jsonl` (every entry sent, append-only), `<KEY>.state.json` (page id, last version written, plan revision, status, fallback comment ids), `<KEY>.last-body.md` (the last body sent). `git worktree remove` deletes it, so flush before removing a worktree |
| Scratch for bodies | the session scratchpad, or `${TMPDIR:-/tmp}/ticket-page/` |
| Jira fallback | at most 8 `PIV record` comments per ticket (9 if the running summary has to be superseded once), each at most 1500 characters |

## Process: Confluence route

### 1. Queue

For `log` (not in a dry run): `ticket_page.py queue --repo <worktree> --key <KEY> --add "<Section>" "<caller>" "<text>"`.
The helper dates the entry, replaces local absolute paths, and refuses secret-like strings (exit 1, naming only the
kind: rewrite the text). For `status`: `ticket_page.py state … --set status=<status> status_note=<note>`. Without
`--flush`, stop here.

### 2. Resolve (reads only; skipped when the state file has the page id and the plan line agrees)

1. `getAccessibleAtlassianResources` → `cloudId`. No Atlassian MCP → stop, note "ticket record not updated:
   Atlassian not connected (entries kept queued)".
2. `getJiraIssue` on `<KEY>` (`fields: ["summary", "status", "parent", "issuetype", "comment"]`,
   `responseContentFormat: "markdown"`). The epic is `fields.parent` when its type is `Epic`.
3. **PRD page**, as `spec` and `close-epic` find it: `searchConfluenceUsingCql` with `type = page AND title ~ "PRD:
   <EPIC>"`, keeping titles that are exactly `PRD: <EPIC>` or start with `PRD: <EPIC> - `; else the epic's `PRD: ...
   (Confluence page id ...)` comment.
4. **No epic, or no PRD page** → the **Jira fallback** below. Never invent a Confluence location.
5. **Container**: CQL `type = page AND parent = <PRD id> AND title = "Ticket plans: <EPIC>"`.
6. **Ticket page**: the id in the plan's `**Ticket page**` line or the state file, confirmed by CQL `id = <id>`
   (title starts with `Plan: <KEY> - `); else CQL `type = page AND parent = <container id> AND title ~ "Plan: <KEY>"`,
   keeping titles that start with `Plan: <KEY> - `. CQL with exact titles avoids paging through children; if a search
   says there are more results, follow `next`.
7. Two PRD pages, two containers or two ticket pages → **stop and ask**; in an unattended run, report it, write
   nothing and leave the entries queued. Never pick one silently.

### 3. Check the version, then build the body

1. **Version check** (existing page): CQL `id = <page id>` with `expand: "content.version"` (plain `version` returns
   no number); the number is `content.version.number`. If it equals `state.version`, the page is what this worktree
   last sent: render with `--local --page-version <number>` (the helper re-checks the number against the state file
   and reads `<KEY>.last-body.md`). Otherwise read the page (`getConfluencePage`, `contentFormat: "markdown"`) and pass
   it as `--current`: a saved tool result file works as it is (plain or MCP-wrapped JSON); otherwise save the part
   before `## Plan` (or `## RCA`) **in full**: the helper refuses a copy that lacks any of the four log headings, or
   that has fewer entries than this worktree last sent (after re-adding its own lost ones from the sent log).
   **If the page still holds only the stub** (its first fill failed or never happened), render it with `--new-page`
   as in "Page missing" step 3; the helper says so if it is given the stub without it.
   The recorded version (and last body) belong to the page id stored with them (`state.page_id`): for a page that was
   deleted and created again under a new id the helper treats the page as new (it notes this) and `--new-page` works.
   To start the same page over on purpose (for example after a person reset it to the stub), check its history, then
   clear the record with `ticket_page.py state … --set version=`.
2. Write `meta.json` in the scratch directory: `key`, `key_url`, `summary`, `epic`, `epic_url`, `prd_title`,
   `prd_url`, `branch`, `status`, `status_note` (from the state file), `updated` (today, local date), `skill`
   (the caller), and `page_id`/`page_url` once known. A missing key stops the render (exit 2).
3. Render:

   ```bash
   uv run .claude/skills/ticket-page/ticket_page.py render --repo <worktree> --plan <path> [--plan-title RCA] \
     --plan-rev <rev> --meta <scratch>/meta.json \
     (--local --page-version <N> | --current <file> | --new-page --current <the stub as read>) \
     --out <scratch>/body.md
   ```

   `--plan-rev` is the commit just made on `publish`, and `state.plan_rev` on any other flush, so the mirror only
   moves on `publish`. The body has no H1 (Confluence shows the title): a header (Jira link, epic, PRD, branch tip,
   the commit that last changed the plan, this page, status, last updated by which skill, the "posted by an agent"
   line), the four log sections, and `## Plan` (or `## RCA`), the file as committed with headings demoted two levels.
   The log sections keep every entry of the current page, re-add any entry of the sent log the page lost, and append
   the queued entries; entries are compared ignoring formatting and line wrapping (Confluence returns `_x_` as `*x*`
   and drops continuation indents), so a retry never duplicates one. Local paths become `{worktree}`, `{worktrees}`,
   `{home}`, `{local}/<name>` (paths under the usual workstation and cluster roots: `/Users`, `/home`, `/tmp`,
`/private`, `/var`, `/Volumes`, `/opt`, `/scratch`, `/gpfs`, and, when a path segment follows, `/global/…`, `/p/…`, `/g/…`, `/usr/workspace/…`, …, also inside
`file://` URLs; other absolute paths are left as they are, so don't paste them); a secret-like string stops the render
(exit 1).
   A line of an entry that starts with `#` is escaped, so it stays text; only the four log headings and the mirror's
   heading end a section when the page is read back.
   **Safety:** for an existing page, `render` refuses (exit 2) without `--current`, `--local --page-version N` or
   `--new-page`; when `--current` is in storage (HTML) form, lacks one of the four log headings, or has fewer entries
   than the last body sent; and for `--local` when the version differs from the state file. Never work around it by
   dropping `page_id`. `--allow-fewer` is only for a deliberate correction (see Corrections).

### 4. Write

- **Dry run:** print the resolution (epic, PRD page, container and page found or "would be created", the title), the
  version check, the body's header and log sections, and the Jira comment that would be added. Pass new entries with
  `render --entry "<Section>" "<caller>" "<text>"` instead of queueing them, and `--outbox <scratch>` if the real store
  doesn't exist. Stop.
- **Container missing:** `createConfluencePage` (PRD's `spaceId`, `parentId` = PRD id, title `Ticket plans: <EPIC>`,
  `contentFormat: "markdown"`), body: "Ticket plans for epic [<EPIC>](<epic url>), one child page per ticket, kept by
  the ticket-page skill (posted by an agent through the owner's account). The repo plan file on each ticket branch is
  the source of truth." Then repeat the container search: if there are now two (a sibling ticket created one at the
  same time), stop as in step 2.7.
- **Page missing:** `createConfluencePage` (`parentId` = container id, the exact title, `contentFormat: "markdown"`,
  and as body exactly the output of `ticket_page.py stub --key <KEY>`: "Plan page for <KEY>; content follows."). The
  create call returns the whole stored body, so never create with the full body. Then:
  1. Record only the page id: `state --set page_id=<id>`. The version is recorded after the first verified update;
     until then `--new-page` is allowed.
  2. Add the `**Ticket page**` line to the plan (or RCA) and commit it ("Records the <KEY> ticket page").
  3. Read the new page (`getConfluencePage`, `contentFormat: "markdown"`; it is one line) and render the first fill:
     `render … --plan-rev <that commit> --new-page --current <the read page>`. `--new-page` accepts only exactly the
     stub, and only while the state file has no version; every other refusal stays.
  4. Update, verify and record as below. A first fill that fails leaves the stub: the next flush finds no recorded
     version, reads the stub again, and repeats step 3.
- **Update:** `updateConfluencePage` (`contentFormat: "markdown"`, `versionMessage` naming the caller and the
  milestone, the new `title` if the Jira summary changed) with the body **exactly as rendered**.
- **Verify, only after an update that returned a version** (a failed update returns an error and no version; then
  nothing is verified or recorded, the entries stay queued, and the flush ends with the error reported):
  `ticket_page.py verify --body <scratch>/body.md --page-id <id> --after-version <V> --repo <worktree>`, where `V` is
  the version checked in step 3 (1 for a new page). It compares the body the update call sent (from the PostToolUse
  hook log, which records successful calls only) with the rendered file. Exit 1 (mismatch) → **one** retry of the
  update with the file's content, then verify again with `--after-version` = the version the first update returned;
  a second mismatch → record nothing, report it, stop. Exit 3 (no logged update after `V`) → note "transcription
  unverified" and go on. Then record what is on the page:
  `state --set version=<returned version> plan_rev=<rev> page_id=<id> --save-body <scratch>/body.md`, then
  `queue --mark-sent`.
- **Another writer:** the update tool has no version check. Expected version = `V` + the number of this flush's own
  successful updates (1, or 2 after a retry). If the final returned version is higher, someone else's update in
  between was overwritten. Entries it carried from this worktree are in the sent log and come back on the next
  render. Entries from another worktree can't be recovered here: queue `Findings and decisions` "Possible lost
  entries: versions <V+1>..<returned-1> other than this flush's own were overwritten by a concurrent update; compare
  the page history", read the page, render with `--current` and flush once more. A jump fully explained by this
  flush's own retry is not a finding.

### 5. Link it from the ticket (once)

If no comment on `<KEY>` contains the page id, `addCommentToJiraIssue` (`contentFormat: "markdown"`):

```markdown
Plan page: [<page title>](<page url>) (Confluence page id `<id>`), under [Ticket plans: <EPIC>](<container url>).
It mirrors `<plan path>` and logs progress, validation, reviews and decisions for this ticket.
_Posted by an agent (ticket-page skill) through the owner's account._
```

## Jira fallback: no epic, or no PRD page

Keep the record in the ticket itself, briefly: never paste the plan or a report; summarise and point to the repo
file. Same milestones as above; **one comment per flush**, combining the queued entries, each at most 1500
characters (check with `ticket_page.py sanitize --repo <worktree>`, which also replaces paths and refuses secrets;
over the cap → summarise again).

- **`publish`**:

  ```markdown
  **PIV record: plan** (<date>, <caller>) · _posted by an agent through the owner's account_
  Goal: <one sentence>.
  Approach:
  - <3–5 bullets>
  Branch `<branch>`, plan `<plan path>` at `<sha>`. Default results: <unchanged / changed: which>.
  No epic PRD page, so the record is kept in these comments (at most 8).
  ```

  Write `**Ticket page**: none (no epic PRD page); PIV record in Jira comments on <KEY>` into the plan (or RCA) and
  commit it whether or not the post succeeds. If it fails, save the text to `<store>/<KEY>.fallback-plan.md`; the next
  flush posts it first. A revised plan gets a `**PIV record: plan revised**` comment with what changed.
- **Other flushes**:
  `**PIV record: <milestone>** (<date>, <caller>) · _posted by an agent through the owner's account_` and one line per
  queued entry: status, key results or the verdict with counts and the report path, decisions with their attribution.
- **Cap.** Count the ticket's `**PIV record` comments (`state.fallback_count`, checked against the ticket's comments).
  The 8th is `**PIV record: running summary (updated in place)**`; later milestones update it with
  `addCommentToJiraIssue` and its `commentId` (`state.fallback_summary_id`), rewriting it to stay within 1500
  characters (latest status, then one line per milestone, oldest dropped first with "earlier: see comments above").
  The helper keeps the bookkeeping, so the cap holds mechanically (`ticket_page.py summary --repo <worktree> --key
  <KEY> …`):
  - before any summary call: `--check`. Exit 1 means stopped: make no Jira call, say so in the caller's report;
  - after a call that returned a comment id: `--returned-id <id>`. The same id → updated. Another id means the call
    created a comment instead of updating: the helper adopts it as the running summary, counting as the one
    superseding comment (don't post another); a second such id → stopped (exit 1);
  - after a failed call: `--failed`. The first time, post **once** a new comment that starts "Supersedes comment
    <id>." with the current summary (as `close-epic` does for its epic comment) and record it with
    `--superseded-by <new id>`; the second time → stopped (exit 1).

  At most 9 `PIV record` comments in all; once stopped, later milestones make no Jira call.
- **Escalation.** In the fallback, the `PIV record` escalation comment is the Jira escalation comment that
  `end-to-end-feature` asks for: post one comment, not two.
- `queue --mark-sent` after each successful post, so the sent log also records the fallback.
- Dry run: print the comment that would be posted; post nothing.
- `publish` always resolves again, so a ticket whose epic gains a PRD page moves to a page; its first Progress entry
  links the earlier Jira comments.

## Attribution

Agents post through the owner's account, so the author field proves nothing. Every page and comment carries "posted
by an agent". In entries, mark who: **Owner** only when a source records it as the owner's (the owner in this
session, a progress-log line saying the owner decided, a Jira comment headed as owner decisions and matched by the
progress log), and cite it; quote or paraphrase the source without adding to it. **Reviewer** for a review report,
**Agent** for the agent's own choices, otherwise **attribution unverified**. These are the `close-epic` rules.

## What goes in an entry

Short, dated, factual, with repo-relative paths and commit hashes:

```text
Progress:                execute: tasks 1-6 done (`ppp/ppp.v`, `ppp/omp_parallel.F90`), commits c95342e..a72694b.
                         Plan amended (`572c2c8`): AIUE-60 references updated.
Validation:              the validate report block's lines; failing output verbatim, trimmed to the failing part.
Reviews:                 Reviewer: plan round 1 REVISE (1 BLOCKER / 3 MAJOR / 6 MINOR), report `docs/reviews/<KEY>-plan-round1.md`.
Findings and decisions:  Owner: <decision> (source) / Agent: <choice, why> / Reviewer: <finding that changed direction>.
```

## Corrections

The log sections are append-only: a later entry corrects an earlier one. Removing or rewording an entry happens only
on the owner's or the coordinator's request: edit a copy of the current page's log part, render it with `--current`,
render it with `--allow-fewer` if entries were removed, send it with a `versionMessage` that says what was corrected
and why, and say so in a Progress entry (a new one, or the corrected entry itself when that entry is what was wrong).

## Failures

Atlassian failures never block the caller. Report the error verbatim in the caller's output as "ticket record not
updated: <error>; <n> entries kept queued". The entries stay queued and the next flush sends them. Don't retry into
another page or space. In an unattended run, every "stop and ask" above becomes "report, write nothing, keep the
entries queued".

## Output

One line for the caller: `Ticket page <created|updated vN|queued (n entries)|skipped (<why>)>: <title> <url>`
(fallback: `Jira PIV comment <added <id>|updated <id>|queued>`), the verify result, and any error verbatim.
