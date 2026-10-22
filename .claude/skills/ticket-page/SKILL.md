---
name: ticket-page
description: Keeps a ticket's hosted PIV record, one per ticket for its whole life. For a Jira ticket under an epic with a PRD page, it keeps one Confluence page under the PRD (container "Ticket plans <EPIC>", page "Plan <KEY> - <summary>"), created by spec when it files the ticket with the ticket's scope, then filled by plan-feature with the plan (or by implement-fix with the RCA), published from the ticket's local, untracked working copy, with append-only Progress, Validation, Reviews and Findings-and-decisions sections, linked once from the ticket. A ticket with no epic or no PRD page gets a few short "PIV record" Jira comments instead. Entries are queued locally and sent only at milestones. Called by spec, plan-feature, execute, validate, implement-fix and the end-to-end-feature review loop; never blocks them. Supports --dry-run and --no-tracker.
argument-hint: "<KEY> create [--ticket <file>] | publish [--plan <file> | --rca <file>] | log <Section> <text> [--flush] | progress <text> | flush | status <status> [<note>] [--dry-run] [--no-tracker]"
---

# Ticket page: the hosted record of a ticket's PIV loop

## Why

Plans, review reports and responses, validation records and the other working documents live in the ticket's
gitignored working folder `<worktree>/.claude/work/<KEY>/` and are never committed (`.claude/context/branching.md`).
The ticket record is where their lasting content goes: the scope, the plan as published, what was done, measured,
found and decided. It is the **only** lasting copy: the working folder and this skill's local store go with the
worktree, so **flush before removing a worktree**.

**One page per ticket, for its whole life.** `spec` creates it when it files the ticket (status `Planned`, a Ticket
section, a Plan placeholder, empty log sections); `plan-feature` (or `implement-fix`) fills the Plan (or RCA) section;
`execute`, `validate` and the review gates add log entries; the commit closes it. An existing To Do or In Progress
child gets a page marked `Backfilled`, which claims nothing about its past. A skill that finds no page creates it the
same way; a re-run never creates a second one (two runs at once can; the listing after a batch detects it).

**This is a wrapper, kept small on purpose** (`.claude/context/process-tiers.md` → Simplicity budget). The helper
holds only what must be mechanical: one page per ticket (`find` never concludes "none" without the evidence), no
silent loss of log entries (merge, refusals, `verify`), plan provenance (sha256), sanitising, the offline outbox.
Everything else is convention in this file.

## Calls

- `<KEY>`: the Jira key. Without one there is nothing to record: say so and return.
- `create [--ticket <file>]`: make sure the page exists (`spec`, once per filed ticket): find it, or create the
  skeleton ("Create") and link it from the ticket. An existing page is left as it is. Jira fallback: the `PIV record:
  ticket filed` comment.
- `publish`: mirror the working copy (`--plan <file>`, default `.claude/work/<KEY>/plan.md`; or `--rca <file>`,
  default `.claude/work/<KEY>/rca.md` or `.claude/work/issue-<N>/rca.md`). The page cites it by publish date and
  sha256. Run it when the plan is written and each time it is revised. It flushes. Other flushes repeat the copy last
  published, so the Plan section only changes on `publish`.
- `log <Section> <text>`: queue one dated entry (`Progress`, `Validation`, `Reviews`, `Findings and decisions`). **No
  Atlassian call** unless `--flush`.
- `progress <text>`: queue one line for the epic's `Progress: <EPIC>` page: `ticket_page.py queue --repo <worktree>
  --key <KEY> --epic --add - <caller> "<text>"`. It goes out with the next flush (step 6). No PRD page: there is no
  progress page; `queue --epic --mark-sent` and say so.
- `flush`: send the queued entries (and the status) now. Only at the milestones below.
- `status <status> [<note>]`: `Planned`, `Backfilled`, `Planning`, `Plan review`, `Executing`, `Validating`,
  `Implementation review`, `Approved`, `Escalated`, `Committed`. Stored locally (`state --set status=… status_note=…`);
  goes out with the next flush.
- `--dry-run`: Atlassian reads only; nothing is written anywhere; print what would be written (render with
  `--entry "<Section>" "<caller>" "<text>"` instead of queueing, `--outbox <scratch>` if there is no store). Callers pass
  it as `--tracker-dry-run`.
- `--no-tracker` (alias `--no-confluence`): do nothing; say "ticket record skipped (--no-tracker)". Callers pass it on,
  also to sub-agents.

## When to flush (milestones)

| Milestone | Who | What goes out |
|---|---|---|
| Ticket filed (or a backfill) | `spec` | `create`: the skeleton and the link comment (fallback: the `ticket filed` / `record started` comment) |
| Plan (or RCA) written, revised or amended | `plan-feature`, `implement-fix`, the review loop | `publish` |
| A review round closes (APPROVE, or REVISE once its response is written) | the review loop | verdict and response |
| End of `execute` | `execute` | **one** Progress summary, plus the validate entries queued during it (sent by the review verdict's flush, below) |
| A `validate` run on its own | `validate` | its result (inside a larger step it rides on that step's flush) |
| An owner decision or an escalation | whoever records it | the Findings and decisions entry, `status Escalated` |
| The final commit, execution report and system review | `end-to-end-feature` / `implement-fix` | Progress "Committed <sha>", `status Committed`, the two Findings and decisions entries: one flush, by `system-review` |
| Before a worktree is removed, or a subagent doing ticket work returns | that agent | `flush`, then `queue --list` and `queue --epic --list` must print nothing; a failed flush is reported with the worktree path |

Everything else is `log` without `--flush`; per-task entries are not logged. Epic progress lines go out with any flush.

**Milestones in one session share one flush.** When the next milestone follows in the same session, queue this one's
entries and let the next flush send both. Nothing is lost meanwhile: the queue lives in the worktree. Two pairs
always qualify:
- the end of `execute` and the implementation review verdict that follows it (the review loop's flush sends both);
- the final commit, the execution report and the system review at the end of `end-to-end-feature` or
  `implement-fix` (one flush, after the system review entry).

Never defer past a point that can lose the queue: a subagent returning, a worktree being removed, or the session
ending (flush first). An owner decision or an escalation still flushes at once.

**Cost.** The update tool takes the whole body, so each flush costs about the page size twice. Ticket pages run 24-31
KB (AIUE-82, AIUE-83, AIUE-93), about 70% of it the Plan section, which only changes on `publish`. A 30 KB page is
about 9k output tokens plus 9k in context per flush. Reading the page back adds about 9k more, so `--local` (step 3) is
the default when nobody else wrote. With shared flushes, a ticket with one plan and one implementation round flushes
about 3-4 times (plan, review verdict, end; plus any plan revision). `render` warns on stderr when a body passes 25 KB.
A session short of context hands the flush to a fresh agent with the scratch directory; it never skips it.

## Configuration

| Setting | Value |
|---|---|
| Container | child of the PRD page, `Ticket plans: <EPIC>` |
| Ticket page | child of the container, `Plan: <KEY> - <Jira summary without trailing period>` |
| Layout | header (Jira, epic, PRD, branch and tip, plan publish date and sha256, this page, status, last update, "posted by an agent"), `## Ticket`, `## Progress`, `## Validation`, `## Reviews`, `## Findings and decisions`, `## Plan` (or `## RCA`) |
| Page id recorded in | the ticket's Jira link comment (`Ticket page: … (Confluence page id <id>)`; `Plan page:` on older tickets), the breakdown entry (`- **Ticket page:** …`), the worktree's state file (`page_id`, or `fallback=1`) |
| Helper | `uv run .claude/skills/ticket-page/ticket_page.py <render|ticket|find|queue|state|verify|extract-plan|progress|sanitize> --help`; test: `.claude/skills/ticket-page/selftest.sh` (run it after changing the helper) |
| Local store (untracked) | `<git dir>/ticket-page-outbox/`: `<KEY>.jsonl` (queued), `<KEY>.sent.jsonl` (sent, append-only), `<KEY>.state.json`, `<KEY>.last-body.md`, `<KEY>.plan.md` (the plan as last published), and `<KEY>.epic*.jsonl` |
| Scratch | the session scratchpad, or `${TMPDIR:-/tmp}/ticket-page/` |
| Jira fallback | at most 8 `PIV record` comments per ticket, each at most 1500 characters |

## Process: Confluence route

### 1. Queue

`log`: `ticket_page.py queue --repo <worktree> --key <KEY> --add "<Section>" "<caller>" "<text>"`. The helper dates the
entry, masks local paths and refuses secret-like strings (exit 1, naming only the kind: rewrite the text). Without
`--flush`, stop here.

### 2. Resolve (reads only; skipped when the state file has the page id)

1. `getAccessibleAtlassianResources` → `cloudId`. No Atlassian MCP → "ticket record not updated: Atlassian not
   connected (entries kept queued)".
2. `getJiraIssue` (`fields: ["summary", "status", "parent", "issuetype", "comment"]`, `responseContentFormat:
   "markdown"`), saved. The epic is `fields.parent` when its type is `Epic`.
3. PRD page: CQL `type = page AND title ~ "PRD: <EPIC>"`, keeping titles `PRD: <EPIC>` or `PRD: <EPIC> - …`; else the
   epic's `PRD: … (Confluence page id …)` comment. No epic or no PRD page → **Jira fallback**. Never invent a location.
4. Container: CQL `type = page AND parent = <PRD id> AND title = "Ticket plans: <EPIC>"`.
5. Page: CQL `type = page AND parent = <container id>` (save every page of results, following `next`), then
   `ticket_page.py find --key <KEY> [--state-id <id>] --comments <issue.json> --search <listing> [--search …]`:
   - exit 0 prints the id → `state --set page_id=<id> parent_id=<container id>`. `stale_records` (an id recorded
     elsewhere that the listing doesn't hold): the listed page wins; confirm each stale id once with CQL `id = <id>`:
     gone → fine; exists → two pages, stop (step 6). `not_listed`: the recorded page is not under this container;
     confirm it with CQL `id = <id>`: exists → use it (a moved ticket keeps its page; its flushes then read it, since
     the container's listing lacks it); gone → `find` again with `--gone <id>`.
     `missing_link_comment: true` → post the link comment (step 5).
   - exit 3 → "Page missing" (below). `find` says "none" only with a complete listing and a readable comment list.
   - exit 2 (several, or can't tell) → stop (step 6); never treat it as "none".
6. Two PRD pages, two containers or two existing ticket pages → **stop and ask**; unattended: report, write nothing,
   keep the entries queued.
7. `fallback=1` in the state file but a page is now found (the epic gained a PRD page): use it (`state --set
   page_id=<id> fallback=`); its first Progress entry links the earlier Jira comments.

### 3. Version check, then render

1. Don't look for the version without the body: `searchConfluenceUsingCql` and `getConfluencePage` switch between two
   response shapes, one with a version and one without (both seen in the same sessions, 2026-10-20 to 22; AIUE-143).
   The check is the time of the last change instead. `getConfluencePageDescendants` kept one shape in every logged
   call: `pageId` = `state.parent_id`, `depth: 1`, `limit: 100`; follow `_links.next` with its `cursor` until the page
   is listed, saving each result. It has no bodies, and each child's `lastModified` is exactly the `version.createdAt`
   that the child's last create or update returned. Render with `--local --listing <saved>` (one `--listing` per
   result). It takes the version from the state file (`V` below) and refuses (exit 2) unless the page's
   `lastModified` equals `state.modified`. On that refusal (someone else wrote, the page isn't listed, or the state
   file has no `modified` yet) read the page with `fetch` (`id`: `ari:cloud:confluence:<cloudId>:page/<page id>`),
   save the result and pass it as `--current`. Its `text` is the page as markdown (log entries are compared ignoring
   formatting), and its `metadata.version` is `V`. No `state.parent_id` (step 2 is skipped once the page id is
   known): run step 2.4 for the container id and record it. A page made by `spec` is an ordinary page here: the
   first `publish` reads it and fills the Plan placeholder.
2. `meta.json` in scratch: `key`, `key_url`, `summary`, `epic`, `epic_url`, `prd_title`, `prd_url`, `branch`,
   `status`, `status_note`, `updated` (today), `skill` (the caller), and `page_id`/`page_url` once known.
3. Render:

   ```bash
   uv run .claude/skills/ticket-page/ticket_page.py render --repo <worktree> \
     (--plan <working copy> [--plan-title RCA] | --mirrored) --meta <scratch>/meta.json \
     (--local --listing <saved listing> | --current <page as read>) --out <scratch>/body.md
   ```

   `--plan` on `publish`; `--mirrored` on any other flush (the copy last published, from the store). `--mirrored`
   refuses when the store has no published copy (a fresh worktree): read the page, `ticket_page.py extract-plan
   --current <page> --out <file>` (exit 3: no plan on the page yet, publish first), then `state --save-plan <file>
   --plan-title <Plan|RCA> --set plan_source="page version <N>"`; the header then says the copy was rebuilt. A rebuilt
   copy has local paths as placeholders (`{worktree}`, `{home}`, `{local}/<name>`) and plan headings deeper than h4
   come back as h4; fix them by hand before the next `publish` if they matter.
   The log sections keep every entry of the current page, re-add any entry of the sent log the page lost, and append
   the queued ones (compared ignoring formatting, so a retry never duplicates). The Ticket section is carried over;
   `--ticket <file>` replaces it on purpose (say so in a Progress entry). A secret-like string stops the render.
   **Refusals (exit 2), never worked around by dropping `page_id`:** an existing page without `--current` or
   `--local`; `--local` whose listing doesn't show the page at `state.modified`; a `--current` in storage form, lacking a log heading,
   holding fewer entries than the last body sent, or lacking its Ticket section (pass `--ticket`); the skeleton for a
   page that exists. `--allow-fewer` is only for a deliberate correction (see Corrections).

### 4. Write

- **Dry run:** print the resolution, the version check, the body's header and log sections, and any Jira comment.
- **Container missing:** `createConfluencePage` (PRD's `spaceId`, `parentId` = PRD id, `contentFormat: "markdown"`,
  title `Ticket plans: <EPIC>`), body: "Ticket plans for epic [<EPIC>](<url>), one child page per ticket, kept by the
  ticket-page skill (posted by an agent through the owner's account)." Search again: two → stop (step 2.6).
- **Create (the skeleton; `spec`'s `create`, and "Page missing").** One call, so there is never a half-made page:
  1. Ticket section: `ticket_page.py ticket --repo <checkout> --key <KEY> --breakdown <file> --source "the epic
     breakdown page \`<title>\` (Confluence page <id>, version <N>)" [--backfill] --out <scratch>/ticket.md`. The
     breakdown is the page as read or `spec`'s working copy `.claude/work/<EPIC>/breakdown.md` (source "as published
     by this spec run"). The entry is the heading naming `` `<KEY>` ``. Exit 3 (no entry) or 2 (several; report it) →
     the Jira description's scope and criteria: `ticket … --text <file> --source "the Jira description of <KEY>"`.
  2. `meta.json` as in 3.2 without `page_id`; status `Planned`. A **backfill**: status `Backfilled`, `backfilled` =
     today, `jira_status`, and `ticket --backfill`; the page then says "as read on" and "not mirrored here".
  3. `render --repo <worktree> --meta <scratch>/meta.json --ticket <scratch>/ticket.md --out <scratch>/body.md`.
  4. Search once more (a batch's listing serves): a page that appeared meanwhile is used instead.
  5. `createConfluencePage` (`parentId` = container id, the exact title, `contentFormat: "markdown"`) with the body
     **exactly as rendered**, then `ticket_page.py verify --body <scratch>/body.md --created --title "<title>"
     --parent-id <container id> --repo <worktree>` (prints the new id). Exit 1 → **one** `updateConfluencePage` with
     the file, verified as an update with `--after-version 1`; a second mismatch → report it. Exit 3 → "transcription
     unverified"; take the id from the response.
  6. Link it from the ticket (step 5). `spec` keeps no state file; the link comment and the breakdown entry are the
     records.
- **Page missing** (on `publish` or a flush): create it as above (`skill` the caller), `state --set page_id=<id> parent_id=<container id>`,
  read it and render the first fill with `--current` and `--plan`; then update as below.
- **Update:** `updateConfluencePage` (`contentFormat: "markdown"`, `versionMessage` naming the caller and milestone,
  the new `title` if the summary changed) with the body **exactly as rendered**.
- **Verify** (only after an update that returned a version): `ticket_page.py verify --body <scratch>/body.md --page-id
  <id> --after-version <V> --repo <worktree>`, `V` the version checked in step 3 (`state.version` on the `--local`
  path). Exit 1 → **one** retry, verified with `--after-version` = the first update's version; a second mismatch →
  record nothing, report, stop. Exit 3 → "transcription unverified", go on. Then record: `state --set
  version=<returned> modified=<returned version.createdAt> page_id=<id> parent_id=<container id> --save-body
  <scratch>/body.md` (on `publish` also `--save-plan <working copy> --plan-title <Plan|RCA>`), then `queue
  --mark-sent`. A failed update: nothing is recorded, entries stay queued, the error is reported.
- **Another writer:** expected version = `V` + this flush's own updates. Higher → someone's update in between was
  overwritten. This worktree's entries come back from the sent log on the next render; other worktrees' can't: queue
  `Findings and decisions` "Possible lost entries: versions <V+1>..<returned-1> were overwritten by a concurrent
  update; compare the page history", read the page, render with `--current` and flush once more.

### 5. Link it from the ticket (once)

When `find` reports `missing_link_comment: true`, `addCommentToJiraIssue` (`contentFormat: "markdown"`):

```markdown
Ticket page: [<page title>](<page url>) (Confluence page id `<id>`), under [Ticket plans: <EPIC>](<container url>).
It is this ticket's PIV record for its whole life: the scope as filed, the plan (published from the ticket's working
copy, which is not kept in the repo), and dated progress, validation, review and decision entries.
_Posted by an agent (ticket-page skill) through the owner's account._
```

### 6. Epic progress lines (after the update, when `queue --epic --list` is not empty)

1. CQL `type = page AND parent = <PRD id> AND title = "Progress: <EPIC>"`. Two → stop (step 2.6). None → `ticket_page.py
   progress --new --meta <scratch>/meta.json --repo <worktree> --out <scratch>/progress.md`, `createConfluencePage`
   (`parentId` = PRD id), `verify --created`.
2. Read it (`fetch` as in step 3.1, saved; always, since every ticket of the epic writes here; `metadata.version` is
   `V`), `ticket_page.py progress --repo <worktree> --key <KEY> --current <saved> --out
   <scratch>/progress-body.md` (the page's entries, this worktree's lines the page lost, then the queued lines; it
   refuses a page without `## Entries`).
3. `updateConfluencePage` with the body as rendered, `verify --page-id <id> --after-version <V>`, then `queue --epic
   --mark-sent`. A failure leaves the lines queued.

## Jira fallback: no epic, or no PRD page

Keep the record in the ticket, briefly: never paste the plan or a report; summarise the goal, decisions, verdicts and
open findings. Same milestones; **one comment per flush**, at most 1500 characters (check with `ticket_page.py
sanitize --repo <worktree>`, which also masks paths and refuses secrets).

- **`create`**: `find --key <KEY> --fallback --comments <issue.json>`: exit 0 (a `PIV record` comment exists) → post
  nothing; 2 → post nothing, report; 3 → post `**PIV record: ticket filed** (<date>, spec) · _posted by an agent
  through the owner's account_` with Scope (1-3 sentences), Acceptance (shortened), Depends on, Branch, the breakdown
  page (or "none; this comment is the record") and "No epic PRD page, so the record is kept in these comments (at most
  8)". A backfill is headed `**PIV record: record started**` and says the ticket was filed before its record started.
- **`publish`**: `**PIV record: plan** (<date>, <caller>)` with the goal, 3-5 approach bullets, the branch, the plan's
  publish date and sha256 (not kept in the repo) and whether default results change. `state --set fallback=1`. A
  revision gets `**PIV record: plan revised**`.
- **Other flushes**: `**PIV record: <milestone>** (<date>, <caller>)` and one line per queued entry (status, results,
  verdict with counts and the open BLOCKER/MAJOR findings, decisions with attribution).
- **Cap.** Count the ticket's `**PIV record` comments (`find --fallback` reports `piv_record_comments` and
  `piv_cap_reached`). The 8th is `**PIV record: running summary (updated in place)**`; later milestones update that
  comment (record its id: `state --set fallback_summary_id=<id>`), rewritten to stay within 1500 characters. If an
  update fails or creates a new comment instead, make no further Jira calls for this ticket and report it.
- An escalation's `PIV record` comment is the Jira escalation comment `end-to-end-feature` asks for: post one, not two.
- `queue --mark-sent` after each successful post. Dry run: print the comment, post nothing.
- `publish` always resolves again, so a ticket whose epic gains a PRD page moves to a page.

## Attribution

Agents post through the owner's account, so the author field proves nothing; every page and comment says "posted by
an agent". Mark **Owner** only when a source records it as the owner's, and cite it; **Reviewer** for a review report;
**Agent** for the agent's own choices; otherwise **attribution unverified** (`close-epic` rules).

## What goes in an entry

Short, dated, factual, with repo-relative paths and commit hashes; never just a pointer to a working file. Size caps
(`.claude/context/process-tiers.md` → Report caps): a review round is the verdict, counts and one line per finding; a
response is one line per finding; a validation entry is the verdicts and the failures verbatim, nothing else.

```text
Progress:                execute: tasks 1-6 done (`ppp/ppp.v`, `ppp/omp_parallel.F90`), commits c95342e..a72694b.
Validation:              the validate report block's lines; failing output verbatim, trimmed to the failing part.
Reviews:                 Reviewer: plan round 1 REVISE (1 BLOCKER / 3 MAJOR / 6 MINOR). L1-B1 OMP chunk padding
                         ignores nxpt=2; L1-M1 …; L1-m1 … (one line per finding).
                         Agent: round 1 response: L1-B1 fixed (task 3 pads both X-points); L1-M2 rebutted (…).
Findings and decisions:  Owner: <decision> (source) / Agent: <choice, why> / Reviewer: <finding that changed direction>.
```

## Corrections

Log sections are append-only: a later entry corrects an earlier one. Removing an entry happens only on the owner's or
the coordinator's request: render an edited copy of the page with `--current … --allow-fewer`, send it with a
`versionMessage` saying what was corrected and why, and add a Progress entry saying so.

## Failures

Atlassian failures never block the caller. Report "ticket record not updated: <error>; <n> entries kept queued". The
entries stay queued and the next flush sends them; they are lost with the worktree, so flush (nothing queued) before a
worktree is removed. Don't retry into another page or space. Unattended, every "stop and ask" becomes "report, write
nothing, keep the entries queued".

## Output

One line for the caller: `Ticket page <created|exists|updated vN|queued (n entries)|skipped (<why>)>: <title> <url>`
(fallback: `Jira PIV comment <added <id>|updated <id>|queued>`), the verify result, and any error verbatim.
