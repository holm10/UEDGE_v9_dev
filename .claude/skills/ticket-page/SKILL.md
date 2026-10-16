---
name: ticket-page
description: Keeps a ticket's hosted PIV record, one per ticket for its whole life. For a Jira ticket under an epic with a PRD page, it keeps one Confluence page under the PRD (container "Ticket plans <EPIC>", page "Plan <KEY> - <summary>"), created by spec when it files the ticket with the ticket's scope, then filled by plan-feature with the plan (or by implement-fix with the RCA), published from the ticket's local, untracked working copy, with append-only Progress, Validation, Reviews and Findings-and-decisions sections, linked once from the ticket. A ticket with no epic or no PRD page gets a few short "PIV record" Jira comments instead. Entries are queued locally and sent only at milestones. Called by spec, plan-feature, execute, validate, implement-fix and the end-to-end-feature review loop; never blocks them. Supports --dry-run and --no-tracker.
argument-hint: "<KEY> create [--ticket <file>] | publish [--plan <file> | --rca <file>] | log <Section> <text> [--flush] | progress <text> | flush | status <status> [<note>] [--dry-run] [--no-tracker]"
---

# Ticket page: the hosted record of a ticket's PIV loop

## Why

The plan, the review reports and responses, the validation records and the other working documents are written to
the ticket's working folder `<worktree>/.claude/work/<KEY>/`, which is gitignored and never committed
(`.claude/context/branching.md`). The ticket record is where their lasting content lives: what the ticket is for, the
plan as published, what was done, what was measured, what the reviewers found and what was decided, readable from the
Jira ticket. It is the **only** lasting copy: the working folder and this skill's local store go with the worktree, so
anything worth keeping must reach the page before the worktree is removed (**flush before removing a worktree**). The
working files are disposable once their content is on the page.

**One page per ticket, for its whole life.** `spec` creates the page when it files the ticket (status `Planned`, the
ticket's scope in a Ticket section, a Plan placeholder and the empty log sections). Every later skill writes to that
same page: `plan-feature` (or `implement-fix`) fills the Plan (or RCA) section, `execute`, `validate` and the review
gates add log entries, the commit closes it. An existing To Do or In Progress child gets a page marked
`Backfilled`, which claims nothing about its past. A skill that finds no page (a ticket not filed through `spec`)
creates it the same way; a re-run never creates a second page for a ticket (two runs at once can, and that is
detected and reported).

## Calls

- `<KEY>`: the Jira key (`AIUE-61`). Without one there is nothing to record: say so and return.
- `create [--ticket <file>]`: make sure the ticket's page exists (spec's call, once per filed ticket): find it, or
  create it as the skeleton (see "Create"); link it from the ticket. An existing page is left as it is. `--ticket` is
  the Ticket section (`ticket_page.py ticket`); in the Jira fallback this posts the `PIV record: ticket filed`
  comment instead.
- `publish`: mirror the plan's working copy (`--plan <file>`; default `.claude/work/<KEY>/plan.md`) or, for
  `implement-fix`, the RCA (`--rca <file>`; default `.claude/work/<KEY>/rca.md`, or `.claude/work/issue-<N>/rca.md`).
  Nothing has to be committed: the page cites the copy by its publish date and sha256. Run it when the plan is written
  and each time it is revised or amended. It flushes. Every other flush repeats the copy last published, so the Plan
  section only changes on `publish`.
- `log <Section> <text>`: queue one dated entry locally. `<Section>` is `Progress`, `Validation`, `Reviews` or
  `Findings and decisions`. **No Atlassian call** unless `--flush` is given.
- `progress <text>`: queue one dated line for the epic's progress page `Progress: <EPIC>` (a child of the PRD):
  `ticket_page.py queue --repo <worktree> --key <KEY> --epic --add - <caller> "<text>"`; the line is prefixed with the
  key and the caller. Callers: `execute` (its end), `validate` (a run on its own), the review loop (approval or
  escalation), `end-to-end-feature` and `implement-fix` (the commit), and whoever records an owner decision. It goes
  out with the next flush (step 6). No PRD page (the Jira fallback): there is no progress page; mark the lines sent
  (`queue --epic --mark-sent`) and say so.
- `flush`: send the queued entries (and the current status) now. Only at the milestones below.
- `status <status> [<note>]`: one of `Planned` or `Backfilled` (set by `spec` on the skeleton), `Planning`,
  `Plan review`, `Executing`, `Validating`, `Implementation review`, `Approved`, `Escalated`, `Committed`, with an
  optional short note. Stored locally; goes out with the next flush.
- `--dry-run`: Atlassian reads only. Nothing is written to Atlassian, the repo or the local store; print what would
  be written. Callers pass it as `--tracker-dry-run`, so it is never mistaken for "don't write code".
- `--no-tracker` (alias `--no-confluence`): do nothing and say "ticket record skipped (--no-tracker)". Callers pass it
  on, also to sub-agents and to whoever they hand a review loop to.

## When to flush (milestones)

| Milestone | Who | What goes out |
|---|---|---|
| Ticket filed (or an existing To Do / In Progress child without a page: a backfill) | `spec` | `create`: the skeleton page and the Jira link comment, or the `ticket filed` (`record started`) comment |
| Plan (or RCA) written, revised or amended | `plan-feature`, `implement-fix`, the review loop | `publish` |
| A review round closes: APPROVE, or REVISE once its response is written | the review loop | the verdict and the response; for a plan revision this flush is the `publish` |
| End of `execute` | `execute` | **one** Progress summary (tasks, commits, deviations), the validate entries queued during it |
| A `validate` result | `validate` | its result: flushed at once when `validate` runs on its own; inside `execute`, `implement-fix` or `end-to-end-feature` it goes out with the flush that ends the same step (end of `execute`, or the review round whose re-validation it is) |
| An owner decision or an escalation | whoever records it | the Findings and decisions entry, `status Escalated` |
| The final commit | `commit` step of `end-to-end-feature` / `implement-fix` | Progress "Committed <sha>", `status Committed` |
| Before the worktree is removed | whoever removes it | `flush`, then `queue --list` (and `queue --epic --list`) must print nothing: the working folder and this store go with the worktree |
| Before a subagent doing ticket work returns | that subagent | `flush` and the same empty-queue check; a flush that failed is reported to the caller with the worktree path, so the caller flushes later (`.claude/context/branching.md`: ticket work never runs in an automatically removed worktree) |

The epic progress lines queued with `progress` go out with any flush: after the ticket page's update, step 6 appends
them to `Progress: <EPIC>`.

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
`spec`'s `create` per ticket: one `getJiraIssue` with all comments (large on a long-running ticket), two writes
(the create and the link comment, each a permission prompt; the create's input and response are the skeleton, a few
KB), and in a batch a share of two container listings (`spec` → Step 6b, "Cost and prompts"). The Jira fallback costs little (comments of at most 1500 characters).

## Configuration

| Setting | Value |
|---|---|
| Container page | child of the epic's PRD page, title `Ticket plans: <EPIC>`, one per epic |
| Ticket page | child of the container, title `Plan: <KEY> - <Jira summary without trailing period>` (the title the first pages had; kept so `close-epic` and existing pages keep working) |
| Page layout | header (Jira, epic, PRD, branch, the plan's publish date and sha256, this page, status, last update, "posted by an agent"), `## Ticket` (the scope as filed: the ticket's breakdown entry, or the Jira description), `## Progress`, `## Validation`, `## Reviews`, `## Findings and decisions`, then `## Plan` (or `## RCA`): a placeholder until the plan is published |
| Where the page id is recorded | the ticket's Jira link comment (`Ticket page: … (Confluence page id <id>)`, by `spec` or the first creator); the ticket's entry on the epic breakdown page (`- **Ticket page:** Confluence page <id> (<url>)`, written by `spec`); the worktree's state file (`page_id`, or `fallback=1` for a ticket on the Jira fallback). Nothing in the repo: plans written before this rule may still carry a `**Ticket page**` line, which `find --plan` reads |
| Helper | `uv run .claude/skills/ticket-page/ticket_page.py` (`render`, `ticket`, `find`, `extract-plan`, `progress`, `queue`, `state`, `verify`, `stub`, `summary`, `sanitize`; `--help`); its end-to-end test without Atlassian: `.claude/skills/ticket-page/selftest.sh` (run it after changing the helper) |
| Working folder (untracked, per worktree) | `<worktree>/.claude/work/<KEY>/` (gitignored): `plan.md` or `rca.md`, `reviews/`, `validation/`, the execution report and system-review notes. Never committed; the page is their lasting record |
| Local store (untracked, per worktree) | `<git dir>/ticket-page-outbox/`: `<KEY>.jsonl` (queued), `<KEY>.sent.jsonl` (every entry sent, append-only), `<KEY>.state.json` (page id, last version written, the published plan's sha256, date and title, status, fallback comment ids), `<KEY>.last-body.md` (the last body sent), `<KEY>.plan.md` (the plan as last published). `git worktree remove` deletes it and the working folder, so **flush before removing a worktree** and check that `queue --list` prints nothing |
| Scratch for bodies | the session scratchpad, or `${TMPDIR:-/tmp}/ticket-page/` |
| Jira fallback | at most 8 `PIV record` comments per ticket (9 if the running summary has to be superseded once), each at most 1500 characters |

## Process: Confluence route

### 1. Queue

For `log` (not in a dry run): `ticket_page.py queue --repo <worktree> --key <KEY> --add "<Section>" "<caller>" "<text>"`.
The helper dates the entry, replaces local absolute paths, and refuses secret-like strings (exit 1, naming only the
kind: rewrite the text). For `status`: `ticket_page.py state … --set status=<status> status_note=<note>`. Without
`--flush`, stop here.

### 2. Resolve (reads only; skipped when the state file has the page id)

1. `getAccessibleAtlassianResources` → `cloudId`. No Atlassian MCP → stop, note "ticket record not updated:
   Atlassian not connected (entries kept queued)".
2. `getJiraIssue` on `<KEY>` (`fields: ["summary", "status", "parent", "issuetype", "comment"]`,
   `responseContentFormat: "markdown"`). The epic is `fields.parent` when its type is `Epic`.
3. **PRD page**, as `spec` and `close-epic` find it: `searchConfluenceUsingCql` with `type = page AND title ~ "PRD:
   <EPIC>"`, keeping titles that are exactly `PRD: <EPIC>` or start with `PRD: <EPIC> - `; else the epic's `PRD: ...
   (Confluence page id ...)` comment.
4. **No epic, or no PRD page** → the **Jira fallback** below. Never invent a Confluence location.
5. **Container**: CQL `type = page AND parent = <PRD id> AND title = "Ticket plans: <EPIC>"`.
6. **Ticket page**, in this order: the id in the state file (or, for a plan written before this rule, its
   `**Ticket page**` line); else the id in the
   ticket's link comment (`Ticket page:`, or `Plan page:` on older tickets, `… (Confluence page id <id>)`, in the
   comments read in step 2), which is where a page made by `spec` is found from a fresh ticket worktree; else CQL
   `type = page AND parent = <container id> AND title ~ "Plan: <KEY>"`, keeping titles that start with
   `Plan: <KEY> - ` (so `AIUE-5` never matches `AIUE-50`). A recorded id is confirmed by CQL `id = <id>` (title starts
   with `Plan: <KEY> - `). Save the results as they come back (the issue JSON with all comments, read with
   `responseContentFormat: "markdown"`, every page of the CQL listing) and let `ticket_page.py find --key <KEY>
   [--state-id <state.page_id>] [--plan …] --comments … --search … [--search …]` apply these rules. It reads both response shapes the MCP server
   returns and flattens ADF comment bodies.
   - exit 0 prints the id; record it: `state --set page_id=<id>`. `stale_records` (ids the state file or a link comment
     names but the listing doesn't, e.g. a page deleted and created again): the listed page wins; confirm each stale
     id once with CQL `id = <id>`: gone → fine (pass `--gone <id>` to drop it from the report); still exists → two
     existing pages: stop as in step 7. `not_listed: true` means the id is recorded but not under this
     container: confirm it with CQL `id = <id>`; if it exists (a ticket moved from another epic keeps its page under
     the old epic's container; it is not moved), use it; if it is gone, run `find` again with `--gone <id>`.
   - exit 3, no page (→ "Page missing"): only when it was given a complete listing **and** a readable comment list.
   - exit 2: several pages, or it can't tell (no listing, a listing that says there are more results, comments it
     can't read or a paged comment list). Stop as in step 7; never treat it as "none".
7. Two PRD pages, two containers or two **existing** ticket pages (two listed, or a stale id that CQL confirms still
   exists) → **stop and ask**; in an unattended run, report it, write nothing and leave the entries queued. Never pick
   one silently. A recorded id that CQL confirms is gone is not a second page.
8. A state file that says `fallback=1` while a page is now found (the epic gained a PRD page since): use the page
   (`state --set page_id=<id> fallback=`); its first Progress entry links the earlier Jira comments.

### 3. Check the version, then build the body

1. **Version check** (existing page): CQL `id = <page id>` with `expand: "content.version"` (plain `version` returns
   no number); the number is `content.version.number`. If it equals `state.version`, the page is what this worktree
   last sent: render with `--local --page-version <number>` (the helper re-checks the number against the state file
   and reads `<KEY>.last-body.md`). Otherwise read the page (`getConfluencePage`, `contentFormat: "markdown"`) and pass
   it as `--current`: a saved tool result file works as it is (plain or MCP-wrapped JSON); otherwise save the part
   before `## Plan` (or `## RCA`) **in full**: the helper refuses a copy that lacks any of the four log headings, or
   that has fewer entries than this worktree last sent (after re-adding its own lost ones from the sent log).
   A page made by `spec` (or by "Page missing") is an ordinary page here: the first `publish` from a ticket worktree
   has no recorded version, reads it and renders with `--current`, which keeps its Ticket section and replaces the
   Plan placeholder with the plan. **If the page still holds only the legacy stub** (`Plan page for <KEY>; content
   follows.`, from a create before pages were made with the skeleton, whose first fill failed), render it with
   `--new-page` (and `--ticket`, to give it its Ticket section); the helper says so if it is given the stub without it.
   The recorded version (and last body) belong to the page id stored with them (`state.page_id`): for a page that was
   deleted and created again under a new id the helper treats the page as new (it notes this) and `--new-page` works.
   To start the same page over on purpose (for example after a person reset it to the stub), check its history, then
   clear the record with `ticket_page.py state … --set version=`.
2. Write `meta.json` in the scratch directory: `key`, `key_url`, `summary`, `epic`, `epic_url`, `prd_title`,
   `prd_url`, `branch`, `status`, `status_note` (from the state file), `updated` (today, local date), `skill`
   (the caller), and `page_id`/`page_url` once known. A missing key stops the render (exit 2).
3. Render:

   ```bash
   uv run .claude/skills/ticket-page/ticket_page.py render --repo <worktree> \
     (--plan <working copy> [--plan-title RCA] | --mirrored) --meta <scratch>/meta.json \
     (--local --page-version <N> | --current <file> | --new-page --current <the stub as read>) \
     --out <scratch>/body.md
   ```

   `--plan <working copy>` on `publish` (the file as it is now, from the working folder; nothing is committed), and
   `--mirrored` on any other flush: the copy last published, kept in the store, so the mirror only moves on
   `publish`. `--mirrored` refuses when the store has no published copy (a fresh worktree, or another session's): then
   read the page (as for `--current`), `ticket_page.py extract-plan --current <the page as read> --out <file>`
   (`.claude/work/<KEY>/plan.md` if the working folder has none, else the scratch directory; exit 3 means the page has
   no plan yet, so there is nothing to repeat: publish first), and `state --save-plan <file> --plan-title <Plan|RCA>
   --set plan_source="page version <N>"` (the title `extract-plan` printed); the header then says the copy was rebuilt
   from the page. A rebuilt copy keeps the plan's heading levels (headings deeper than the page's six levels carry `▸`
   marks there, which `extract-plan` reverses) and fenced code, but local paths come back as the placeholders
   `{worktree}`, `{worktrees}`, `{home}`, `{local}/<name>` and Confluence may have changed some formatting, so its
   sha256 differs from the original's: fix the paths by hand before the next `publish` if they matter. The body has no H1
   (Confluence shows the title): a header (Jira link, epic, PRD, branch and its tip, the plan's publish date and
   sha256, this page, status, last updated by which skill, the "posted by an agent" line), `## Ticket`, the four log
   sections, and `## Plan` (or `## RCA`), the published copy with headings demoted two levels. The Ticket section
   is carried over from the page (or, with `--local`, from the last body sent); pass
   `--ticket <file>` only to replace it on purpose (the breakdown entry changed: rebuild it with
   `ticket_page.py ticket` and say so in a Progress entry). A page made before `spec` created pages has no Ticket
   section and gets none.
   The log sections keep every entry of the current page, re-add any entry of the sent log the page lost, and append
   the queued entries; entries are compared ignoring formatting and line wrapping (Confluence returns `_x_` as `*x*`
   and drops continuation indents), so a retry never duplicates one. Local paths become `{worktree}`, `{worktrees}`,
   `{home}`, `{local}/<name>`, also inside `file://` URLs. Masked roots (the helper's `PATH_ROOTS` and
   `SHORT_ROOTS`): `/Users`, `/home`, `/homes`, `/private`, `/tmp`, `/var`, `/Volumes`, `/opt`, `/mnt`, `/srv`,
   `/root`, `/scratch`, `/gpfs`, `/lustre` as they are; and, only when a path segment follows (so "the /p option" stays
   text), `/global/…`, `/nfs/…`, `/work/…`, `/project/…`, `/projects/…`, `/data/…`, `/p/…`, `/g/…`, `/usr/workspace/…`
   and `/usr/WS<n>/…`. Other absolute paths are left as they are, so don't paste them. A secret-like string stops the
   render (exit 1).
   A line of an entry that starts with `#` is escaped, so it stays text; only the four log headings and the mirror's
   heading end a section when the page is read back.
   **Safety:** for an existing page, `render` refuses (exit 2) without `--current`, `--local --page-version N` or
   `--new-page`; when `--current` is in storage (HTML) form, lacks one of the four log headings, has fewer entries
   than the last body sent, or lacks the Ticket section the last body sent (unless `--ticket` is given); for `--local`
   when the version differs from the state file; and for the skeleton (no `--plan`) whenever the page exists, except
   a legacy stub with `--new-page`. Never work around it by dropping `page_id`. `--allow-fewer` is only for a
   deliberate correction (see Corrections).

### 4. Write

- **Dry run:** print the resolution (epic, PRD page, container and page found or "would be created", the title), the
  version check, the body's header and log sections, and the Jira comment that would be added. Pass new entries with
  `render --entry "<Section>" "<caller>" "<text>"` instead of queueing them, and `--outbox <scratch>` if the real store
  doesn't exist. For `create`: the page found (id, title, how) or "would be created" with the skeleton's full body
  (it is small), and the link comment. Stop.
- **Container missing:** `createConfluencePage` (PRD's `spaceId`, `parentId` = PRD id, title `Ticket plans: <EPIC>`,
  `contentFormat: "markdown"`), body: "Ticket plans for epic [<EPIC>](<epic url>), one child page per ticket, kept by
  the ticket-page skill (posted by an agent through the owner's account). Each page is created when `spec` files the
  ticket and records the ticket's whole PIV loop. Plans, reviews and validation records are working documents that
  are never committed; each page is their lasting record." Then repeat the container search: if there are now two
  (a sibling ticket created one at the
  same time), stop as in step 2.7.
- **Create (the skeleton; `spec`'s `create`, and "Page missing" below).** Pages are created complete but small, in
  one call, so there is never a half-made page:
  1. Ticket section: `ticket_page.py ticket --repo <checkout> --key <KEY> --breakdown <file> --source "the epic
     breakdown page \`<title>\` (Confluence page <id>, version <N>)" [--backfill] --out <scratch>/ticket.md`. The
     breakdown file is the breakdown page as read (`getConfluencePage`, `contentFormat: "markdown"`; a saved tool
     result works as it is; the source then names its version), or `spec`'s working copy
     `.claude/work/<EPIC>/breakdown.md` of what it publishes (the source names the page "as published by this spec
     run"). The ticket's entry is found by `` `<KEY>` `` in its heading, else by a `Branch:` line (plain or bold) naming `v9-<KEY>-` or `v9-ai-<KEY>-` among the entry's own
     lines, else by the key in a heading that names no other key. Exit 3 (no entry, e.g. a ticket added after the
     breakdown, or an epic without a breakdown page) or exit 2 (several entries match; report it) → write the Jira
     description's scope and acceptance criteria to a file and use `ticket … --text <file> --source "the Jira
     description of <KEY>"`. `--backfill` (a page made after the ticket was filed) makes the source line say "as read
     on <date>" instead of "as filed".
  2. `meta.json` as in step 3.2, no `page_id`, `branch` the ticket's branch (`none` for a ticket without one),
     `skill` `spec` (or the caller), and `branch_state` only as checked (`git branch --list <branch>` and `git
     ls-remote --heads origin <branch>`): `exists` or `absent`; left out, the header says "not checked". Status
     `Planned` for a ticket just filed. For a **backfill** (the ticket was filed before its page): status
     `Backfilled`, `backfilled` = today, `jira_status` = its Jira status. The header then carries a `**Backfilled:**`
     field saying the page was made after the ticket was filed and the plan, if any, is not yet mirrored, and the Plan
     placeholder says "not mirrored here yet"; nothing claims the ticket was never planned.
  3. `render --repo <worktree> --meta <scratch>/meta.json --ticket <scratch>/ticket.md --out <scratch>/body.md` (no
     `--plan`: the skeleton).
  4. Search once more (step 2.6): a page that appeared meanwhile is used instead, nothing is created. In a batch
     (`spec`), the container listing taken at the start of the batch serves.
  5. `createConfluencePage` (PRD's `spaceId`, `parentId` = container id, the exact title, `contentFormat:
     "markdown"`) with the body **exactly as rendered**. Then `ticket_page.py verify --body <scratch>/body.md
     --created --title "<title>" --parent-id <container id> --repo <worktree>`: it prints the new page id (from the
     logged response). Exit 1 (mismatch) → **one** `updateConfluencePage` with the file's content, verified as an
     update with `--after-version 1`; a second mismatch → report it. Exit 3 → "transcription unverified"; take the id
     from the create response.
  6. Search the container again: two pages with the title (a concurrent creator) → stop as in step 2.7. In a batch,
     one listing after the batch serves.
  7. Link it from the ticket (step 5). A `spec` run records nothing in a state file (no ticket worktree exists yet):
     the link comment and the breakdown page are the records; `spec` adds `- **Ticket page:** Confluence page <id>
     (<url>)` to the ticket's entry on the breakdown page.
- **Page missing** (on `publish` or a flush, for a ticket `spec` didn't file): create it as above, from this
  worktree, with `status` from the state file and `skill` the caller. Then:
  1. Record only the page id: `state --set page_id=<id>`. The version is recorded after the first verified update.
  2. Read the new page (`getConfluencePage`, `contentFormat: "markdown"`) and render the first fill with
     `--current <the read page>` and `--plan <working copy>`, as for any page this worktree hasn't written.
  3. Update, verify and record as below. A first fill that fails leaves the skeleton: the next flush finds no
     recorded version, reads it, and repeats step 3.
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
  `state --set version=<returned version> page_id=<id> --save-body <scratch>/body.md`, on `publish` also
  `--save-plan <the working copy> --plan-title <Plan|RCA>` (the copy every later flush repeats, and the section it is
  mirrored under; required), then `queue --mark-sent`.
- **Another writer:** the update tool has no version check. Expected version = `V` + the number of this flush's own
  successful updates (1, or 2 after a retry). If the final returned version is higher, someone else's update in
  between was overwritten. Entries it carried from this worktree are in the sent log and come back on the next
  render. Entries from another worktree can't be recovered here: queue `Findings and decisions` "Possible lost
  entries: versions <V+1>..<returned-1> other than this flush's own were overwritten by a concurrent update; compare
  the page history", read the page, render with `--current` and flush once more. A jump fully explained by this
  flush's own retry is not a finding.

### 5. Link it from the ticket (once)

If no comment on `<KEY>` contains the page id (`find` reports `missing_link_comment: true`, also when the only link
comment names a stale page), `addCommentToJiraIssue` (`contentFormat: "markdown"`):

```markdown
Ticket page: [<page title>](<page url>) (Confluence page id `<id>`), under [Ticket plans: <EPIC>](<container url>).
It is this ticket's PIV record for its whole life: the scope as filed, the plan (published from the ticket's working
copy, which is not kept in the repo), and dated progress, validation, review and decision entries.
_Posted by an agent (ticket-page skill) through the owner's account._
```

Older tickets have the same comment headed `Plan page:`; both count (step 2.6, `prime`).

### 6. Epic progress lines (after the update, when `queue --epic --list` is not empty)

1. Find `Progress: <EPIC>`: CQL `type = page AND parent = <PRD id> AND title = "Progress: <EPIC>"`. Two → stop as in
   step 2.7. None (an epic sliced before `spec` created it) → `ticket_page.py progress --new --meta <scratch>/meta.json
   --repo <worktree> --out <scratch>/progress.md` and `createConfluencePage` (PRD's `spaceId`, `parentId` = PRD id,
   that title, `contentFormat: "markdown"`), verified with `verify --created`.
2. Read it (`getConfluencePage`, markdown, saved) and `ticket_page.py progress --repo <worktree> --key <KEY> --current
   <saved page> --out <scratch>/progress-body.md`: the page's entries, any of this worktree's epic lines the page lost
   (from `<KEY>.epic.sent.jsonl`), then the queued lines. It refuses a page without its `## Entries` heading.
3. `updateConfluencePage` with the body exactly as rendered (`versionMessage` "<KEY> progress lines, <caller>"),
   `verify --page-id <id> --after-version <V>` as in step 4, then `queue --epic --mark-sent`. A failure leaves the
   lines queued for the next flush and never blocks the caller. The page is small, so this costs little.

## Jira fallback: no epic, or no PRD page

Keep the record in the ticket itself, briefly: never paste the plan or a report; summarise. The working files are
not kept anywhere (no page, no repo), so each comment carries what a later reader needs: the goal, the decisions, the
verdicts and the open findings. Same milestones as above; **one comment per flush**, combining the queued entries, each at most 1500
characters (check with `ticket_page.py sanitize --repo <worktree>`, which also replaces paths and refuses secrets;
over the cap → summarise again).

- **`create`** (`spec`): first `find --key <KEY> --fallback --comments <issue.json>` (all comments, markdown): exit
  0 (a `PIV record` comment exists) → post nothing; exit 2 (can't tell) → post nothing, report it; exit 3 → post:

  ```markdown
  **PIV record: ticket filed** (<date>, spec) · _posted by an agent through the owner's account_
  Scope: <1-3 sentences from the breakdown entry or the description>.
  Acceptance: <the criteria, shortened>.
  Depends on: <keys or none>. Branch `<branch>` (<not created yet | exists | not checked>, as checked);
  breakdown: <the breakdown page's title and id | none on Confluence; this comment is the record>.
  No epic PRD page, so the record is kept in these comments (at most 8).
  ```

  For a backfill (a ticket filed before its record), the heading is `**PIV record: record started**` and the first
  line after it says "This ticket was filed before its record started (Jira status <status>); the scope below is as
  read on <date> from <source>, and its plan, if any, is in the ticket's working folder." Nothing in it claims the
  ticket is unplanned.
  Either comment counts towards the cap below: the ticket worktree's first flush starts `state.fallback_count` from
  `find --fallback`'s `piv_record_comments`, since `spec` keeps no state. `spec` writes `- **Ticket page:** none (no
  epic PRD page); PIV record in Jira comments on <KEY>` into the breakdown entry.
- **`publish`**:

  ```markdown
  **PIV record: plan** (<date>, <caller>) · _posted by an agent through the owner's account_
  Goal: <one sentence>.
  Approach:
  - <3–5 bullets>
  Branch `<branch>`, plan published <date> (sha256 `<hash>`, not kept in the repo). Default results: <unchanged /
  changed: which>.
  No epic PRD page, so the record is kept in these comments (at most 8).
  ```

  Record `state --set fallback=1` whether or not the post succeeds. If it fails, save the text to
  `<store>/<KEY>.fallback-plan.md`; the next flush posts it first. A revised plan gets a `**PIV record: plan
  revised**` comment with what changed.
- **Other flushes**:
  `**PIV record: <milestone>** (<date>, <caller>) · _posted by an agent through the owner's account_` and one line per
  queued entry: status, key results or the verdict with counts and the open BLOCKER/MAJOR findings in a few words (the
  report itself is a local working file), decisions with their attribution.
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
- `publish` always resolves again, so a ticket whose epic gains a PRD page moves to a page (created as in "Page
  missing"); its first Progress entry links the earlier Jira comments.

## Attribution

Agents post through the owner's account, so the author field proves nothing. Every page and comment carries "posted
by an agent". In entries, mark who: **Owner** only when a source records it as the owner's (the owner in this
session, a progress-log line saying the owner decided, a Jira comment headed as owner decisions and matched by the
progress log), and cite it; quote or paraphrase the source without adding to it. **Reviewer** for a review report,
**Agent** for the agent's own choices, otherwise **attribution unverified**. These are the `close-epic` rules.

## What goes in an entry

Short, dated, factual, with repo-relative paths of product files and commit hashes. Working files are not kept, so an
entry never just points to one: it carries the content that matters.

```text
Progress:                execute: tasks 1-6 done (`ppp/ppp.v`, `ppp/omp_parallel.F90`), commits c95342e..a72694b.
                         Plan amended (published 2026-10-16, sha256 `3f2a…`): AIUE-60 references updated.
Validation:              the validate report block's lines; failing output verbatim, trimmed to the failing part.
Reviews:                 Reviewer: plan round 1 REVISE (1 BLOCKER / 3 MAJOR / 6 MINOR).
                         L1-B1 OMP chunk padding ignores nxpt=2; L1-M1 no serial-vs-parallel check for the cut cells;
                         L1-M2 …; L1-m1 … (one line per finding).
                         Agent: round 1 response: L1-B1 fixed (task 3 now pads both X-points); L1-M2 rebutted (…).
Findings and decisions:  Owner: <decision> (source) / Agent: <choice, why> / Reviewer: <finding that changed direction>.
```

## Corrections

The log sections are append-only: a later entry corrects an earlier one. Removing or rewording an entry happens only
on the owner's or the coordinator's request: edit a copy of the current page's log part, render it with `--current`,
render it with `--allow-fewer` if entries were removed, send it with a `versionMessage` that says what was corrected
and why, and say so in a Progress entry (a new one, or the corrected entry itself when that entry is what was wrong).

## Failures

Atlassian failures never block the caller. Report the error verbatim in the caller's output as "ticket record not
updated: <error>; <n> entries kept queued". The entries stay queued (with the working files, the record until then)
and the next flush sends them. They are lost with the worktree, so a worktree is removed only after a flush that
left nothing queued, and a subagent doing ticket work flushes and checks the queue before it returns. Don't retry
into another page or space. In an unattended run, every "stop and ask" above becomes "report, write nothing, keep the
entries queued".


## Output

One line for the caller: `Ticket page <created|exists|updated vN|queued (n entries)|skipped (<why>)>: <title> <url>`
(fallback: `Jira PIV comment <added <id>|updated <id>|queued>`), the verify result, and any error verbatim.
