---
name: ticket-page
description: Keeps a ticket's hosted PIV record. For a Jira ticket under an epic with a PRD page, it creates or updates a Confluence page under the PRD (container "Ticket plans <EPIC>", page "Plan <KEY> - <summary>") that mirrors the ticket's plan and holds append-only Progress, Validation, Reviews and Findings-and-decisions sections, and links it from the ticket once. A ticket with no epic or no PRD page gets brief dated Jira comments instead. Called by plan-feature, execute, validate, implement-fix and the end-to-end-feature review gates; never blocks them. Supports --dry-run and --no-tracker.
argument-hint: "<KEY> publish|log <Section> <text>|status <status> [--plan <path>] [--dry-run] [--no-tracker]"
---

# Ticket page: the hosted record of a ticket's PIV loop

## Why

The plan file and the review reports live on the ticket branch, which may sit in a local worktree for days. The ticket
page is the copy on the platform: the plan, what was done, what was measured, what the reviewers said and what was
decided, readable by anyone with the Jira ticket and still there if the worktree or the session is lost. The repo
stays the source of truth; the page mirrors it and logs the steps.

## Callers

| Caller | When | Call |
|---|---|---|
| `plan-feature` | after the plan is written and committed; again after every revision (re-plan, amendment) | `publish` (+ `log Progress "Plan revised: <why>"` on a revision) |
| plan review (`end-to-end-feature` loop, `stage: plan`) | after each round | `log Reviews …` |
| `execute` | after each task or commit; when it deviates from the plan | `log Progress …`, `log Findings and decisions …` |
| `validate` | after each run | `log Validation …` |
| implementation review (`stage: implementation`) | after each round | `log Reviews …` |
| any step | an owner decision, an escalation, an amendment | `log Findings and decisions …`, `status …` |
| `implement-fix` | only when the GitHub issue maps to a Jira ticket (the RCA or the user names the key) | as `execute`/`validate` |

A caller runs this skill as one step and continues whatever happens here (see **Failures**).

## Arguments

- `<KEY>`: the Jira key (`AIUE-61`). Without one there is nothing to record: say so and return.
- `publish`: create or update the page from the committed plan (`--plan <repo-relative path>`, default: the
  plan whose `**Branch / worktree**` line names the current branch, in `.claude/plans/`).
- `log <Section> <text>`: append one dated entry. `<Section>` is `Progress`, `Validation`, `Reviews` or
  `Findings and decisions`.
- `status <status>`: set the header status, one of `Planning`, `Plan review`, `Executing`, `Validating`,
  `Implementation review`, `Approved`, `Escalated`, `Committed`. Can be combined with `publish` or `log`.
- `--dry-run`: Atlassian reads only, no writes to Atlassian, the repo, or the outbox; print what would be written.
- `--no-tracker` (alias `--no-confluence`): do nothing and say "ticket record skipped (--no-tracker)". A caller
  passes it on when its own arguments contain it.

## Configuration

| Setting | Value |
|---|---|
| Container page | child of the epic's PRD page, title `Ticket plans: <EPIC>`, one per epic |
| Ticket page | child of the container, title `Plan: <KEY> - <Jira summary without trailing period>` |
| Page id in the repo | the plan's Summary line `**Ticket page**: Confluence page <id> (<url>)` |
| Helper | `uv run .claude/skills/ticket-page/ticket_page.py` (`render`, `queue`, `sanitize`; `--help`) |
| Outbox (unsent entries) | `<git dir of the worktree>/ticket-page-outbox/<KEY>.jsonl`, untracked |
| Scratch for bodies | the session scratchpad, or `${TMPDIR:-/tmp}/ticket-page/` |
| Jira fallback comment cap | about 1500 characters per comment |

The exact titles and the lookup under the PRD and the container (step 2) are what keep the pages single. Don't rely
on Confluence to refuse a duplicate title.

## Process

### 1. Queue the entry first

For `log` (not in a dry run), queue the entry before any Atlassian call, so a failure later can't lose it:

```bash
uv run .claude/skills/ticket-page/ticket_page.py queue --repo <worktree> --key <KEY> \
  --add "<Section>" "<caller skill>" "<text>"
```

The helper dates the entry, replaces local absolute paths, and refuses secret-like strings (exit 1: rewrite the
text). Entries from earlier failed runs are still in the outbox and go out with this one.

### 2. Resolve (reads only)

1. `getAccessibleAtlassianResources` → `cloudId`. No Atlassian MCP → stop here, note "ticket record not updated:
   Atlassian not connected (entries kept in the outbox)".
2. `getJiraIssue` on `<KEY>` with `fields: ["summary", "status", "parent", "issuetype", "comment"]`,
   `responseContentFormat: "markdown"`. The epic is `fields.parent` when its `issuetype` is `Epic`.
3. **PRD page** (as `spec` and `close-epic` find it): `searchConfluenceUsingCql` with
   `type = page AND title ~ "PRD: <EPIC>"`, keeping only titles that are exactly `PRD: <EPIC>` or start with
   `PRD: <EPIC> - ` (so `AIUE-8` doesn't match `AIUE-80`); else the epic's `PRD: ... (Confluence page id ...)`
   comment. Several matches → ask which one.
4. **No epic, or no PRD page** → the **Jira fallback** below. Never invent a Confluence location.
5. **Container:** `getConfluencePageDescendants` on the PRD (`depth: 1`), exact title `Ticket plans: <EPIC>`.
6. **Ticket page:** the id in the plan's `**Ticket page**` line, confirmed with `getConfluencePage` (title starts
   with `Plan: <KEY> - `). Otherwise `getConfluencePageDescendants` on the container, keeping only titles that
   start with `Plan: <KEY> - `. Two or more → stop and ask; never pick one silently.

### 3. Build the body

Write `meta.json` in the scratch directory: `key`, `key_url` (`https://<site>/browse/<KEY>`), `summary`, `epic`,
`epic_url`, `prd_title`, `prd_url`, `branch`, `status` (the new one, else the page's current one, else `Planning`),
`updated` (today's local date), `skill` (the caller), and `page_id`/`page_url` once known.

If the page exists, read it (`getConfluencePage`, `contentFormat: "markdown"`) and save the part **before** the
`## Plan` heading to `<scratch>/current.md`: the log sections are taken from there, the plan never is. If the tool
saved its (large) result to a file instead, pass that file as it is: `--current` also takes the tool's JSON and stops
at `## Plan`. Then:

```bash
uv run .claude/skills/ticket-page/ticket_page.py render --repo <worktree> --plan <plan path> --rev HEAD \
  --meta <scratch>/meta.json [--current <scratch>/current.md] --out <scratch>/body.md
```

The body is (no H1: Confluence shows the title): a header (Jira link, epic, PRD, branch, plan path and commit, this
page, status, last updated by which skill, the "posted by an agent" attribution line); the four log sections
(earlier entries kept, outbox entries not already on the page appended, compared ignoring markdown formatting, so
a retry never duplicates one: Confluence returns `_x_` as `*x*` and re-spaces tables); and `## Plan`, the plan
**as committed at `--rev`** with its headings demoted two levels. The header cites the commit that last changed the
plan file. Commit the plan before `publish`; an uncommitted edit is not mirrored. Local absolute paths become
`{worktree}`, `{worktrees}`, `{home}` or `{local}/<name>`; a secret-like string stops the render (exit 1).

### 4. Write

- **Dry run:** print the resolution (epic, PRD page, container found or "would be created", page found or "would
  be created", the title), the body path, its header and log sections, and the Jira comment that would be added.
  Pass the entry with `render --entry "<Section>" "<caller>" "<text>"` instead of `queue`, so nothing is written to
  the worktree's git directory (the outbox is only read, to show what is pending). Stop.
- **Container missing:** `createConfluencePage` with the PRD's `spaceId`, `parentId` = PRD id, title
  `Ticket plans: <EPIC>`, `contentFormat: "markdown"`, body: "Ticket plans for epic [<EPIC>](<epic url>), one child
  page per ticket. Created and updated by the ticket-page skill (plan-feature, execute, validate, review gates).
  The repo plan file on each ticket branch is the source of truth."
- **Page missing:** `createConfluencePage` with `parentId` = container id, the exact title,
  `contentFormat: "markdown"` and a **one-line stub body** ("Plan page for <KEY>; content follows."). The create
  call returns the whole stored body, which for a full plan is too large for the tool output, so never create with
  the full body. Then set `page_id`/`page_url` in `meta.json`, render, and `updateConfluencePage` with the full body:
  the first real version already shows the page's own id.
- **Page exists:** `updateConfluencePage` with the body, `contentFormat: "markdown"`, and a `versionMessage` naming
  the caller and what changed ("validate: D_only PASS", "plan revised to <sha>"). Confluence bumps the version. If the
  Jira summary changed, pass the new `title`.
- Check that the version you got back is exactly one more than the one you read. More than one means another agent
  wrote in between and the update tool overwrites without a version check, so its entries may be gone: read the
  page again, render again with the same outbox (entries already there are skipped) and update once more. Then
  `queue --clear` (not in a dry run). The container must still have exactly one `Plan: <KEY> - ` child.

### 5. Link it from the ticket (once)

If no comment on `<KEY>` contains the page id, `addCommentToJiraIssue` (`contentFormat: "markdown"`):

```markdown
Plan page: [<page title>](<page url>) (Confluence page id `<id>`), under [Ticket plans: <EPIC>](<container url>).
It mirrors the plan in `<plan path>` and logs progress, validation, reviews and decisions for this ticket.
```

### 6. Record the page id in the plan (`publish`, first time only)

Add `**Ticket page**: Confluence page <id> (<url>)` to the plan's Summary, after `**Branch / worktree**`, and commit
it on the ticket branch ("Records the <KEY> ticket page"). Later calls find the page by id; the title search is the
fallback.

## Jira fallback: no epic, or no PRD page

Keep the record in the ticket itself, briefly, as one comment per step. Never paste the plan or a report: summarise
and point to the repo file.

- **`publish`** → one comment, at most about 1500 characters:

  ```markdown
  **PIV record: plan** (<date>, <caller>; posted by an agent)
  Goal: <one sentence>.
  Approach:
  - <3–5 bullets>
  Branch `<branch>`, plan `<plan path>` at `<sha>`. Default results: <unchanged / changed: which>.
  No epic PRD page, so the record is kept in these comments.
  ```

  A revised plan gets a new comment `**PIV record: plan revised**` with what changed, not an edit of the old one.
- **`log`** → one comment per call: `**PIV record: <Section>** (<date>, <caller>)` and one to three lines: status,
  key results or the verdict with counts and the report path, decisions with their attribution. Entries still in the
  outbox from failed calls go out first, one comment each, oldest first; then `queue --clear`.
- `status` alone posts nothing; the status goes into the next comment's first line.
- `publish` also adds `**Ticket page**: none (no epic PRD page); PIV record in Jira comments on <KEY>` to the plan's
  Summary (step 6). Later `log` calls take this route without resolving again; `publish` always resolves, so a ticket
  whose epic gains a PRD page moves to a page (its first Progress entry links the earlier Jira comments).
- Before posting, run the text through `ticket_page.py sanitize --repo <worktree>` (paths, secrets, the cap). Over
  the cap → summarise again. Skip a comment whose text already exists on the ticket (retries).
- Past about ten PIV comments on one ticket, add one line to the next comment suggesting the ticket be put under an
  epic so it gets a page.
- Dry run: print the comment that would be posted; post nothing.

## Attribution

Agents post through the owner's account, so the author field proves nothing. In entries, mark who: **Owner** only
when a source records it as the owner's (the owner in this session, a progress-log line saying the owner decided, a
Jira comment headed as owner decisions and matched by the progress log) and cite that source; **Reviewer** for a
review report; **Agent** for the agent's own choices; otherwise **attribution unverified**. These are the
`close-epic` rules, so the epic record can reuse the entries.

## What goes in an entry

Short, dated, factual, with repo-relative paths and commit hashes:

```text
Progress:                Task 3 done (`ppp/omp_parallel.F90`), commit `155e562`.
                         Plan revised to revision 3 (`6703d6a`): round-2 minors folded in.
Validation:              the validate report block's lines; failing output verbatim, trimmed to the failing part.
Reviews:                 Reviewer: plan round 1 REVISE (1 BLOCKER / 3 MAJOR / 6 MINOR), report `docs/reviews/<KEY>-plan-round1.md`.
Findings and decisions:  Owner: <decision> (source) / Agent: <choice, why> / Reviewer: <finding that changed direction>.
```

## Failures

Atlassian failures never block the caller. Report the error verbatim in the caller's output as
"ticket record not updated: <error>; <n> entries kept in the outbox". The entries stay in the outbox and the next
call sends them. Don't retry into another page or space. A failed `publish` is retried by the next step's call.

## Output

One line for the caller: `Ticket page <created|updated vN|unchanged|skipped (<why>)>: <title> <url>` (Jira fallback:
`Jira PIV comment added: <id>`), plus any error verbatim and the outbox count.
