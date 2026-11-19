---
name: ticket-page
description: Keeps a tracker ticket's record, one per ticket for its whole life, in the private tracker repository named by .claude/tracker.toml. The record is the GitHub issue (Project Status, a few one-line comments) plus docs/<epic>/T<N>-<slug>/record.md, with a Ticket section and the append-only Progress, Validation, Reviews and Findings-and-decisions sections, and plan.md or rca.md next to it. Every call is one commit in the tracker checkout, pushed after a rebase onto the remote; nothing is queued. Called by spec, plan-feature, execute, validate, implement-fix and the end-to-end-feature review loop; never blocks them. Supports --dry-run and --no-tracker.
argument-hint: "T<N> create | publish [--plan <file> | --rca <file>] | log <Section> <text> | progress <text> | status <status> [<note>] [--dry-run] [--no-tracker]"
---

# Ticket page: the record of a tracker ticket

## Why

The ticket's working documents (plan drafts, review reports, probes, raw data) stay in the gitignored scratch folder
`<worktree>/.claude/work/<KEY>/` (owner, 2026-11-18, tracker #3). The record is where their lasting content goes: the
scope as filed, the plan as published, what was done, measured, found and decided. It lives in the tracker repository,
so it is plain git: reviewable, greppable, and safe from worktree removal. **Every call is a commit** in the tracker
checkout, which sits outside every worktree, so nothing is ever waiting to be sent (owner, 2026-11-18, tracker #2).

**One record per ticket.** It is found by its key: `docs/*/T<N>-*/record.md`. `create` makes it if there is none and
never makes a second one; two records for one key stop every call (exit 2) until a person merges them.

## Calls

Run the helper from the ticket's worktree; `--caller <skill>` names the writer in each entry:

```bash
uv run .claude/skills/ticket-page/ticket_page.py --caller <skill> <command> T<N> [...]
```

- `create T<N>`: the record from the issue: the Ticket section is the issue body (H1/H2 outside code fences demoted; title and body masked), the header has
  the issue type, the Project's Tier and status `Planned`. Placed under the issue's parent epic (`docs/T<E>-<slug>/`),
  or `docs/no-epic/`. An existing record is left as it is. `spec` calls it when it files a ticket; any skill that finds
  no record calls it first.
- `publish T<N> [--plan <file> | --rca <file>]`: copy the working copy (default `.claude/work/T<N>/plan.md`) to
  `plan.md` (or `rca.md`) next to the record, local paths masked; the header cites the publish date and the sha256 of the published file, a
  Progress entry and a one-line issue comment say so. Run it when the plan is written and each time it is revised.
- `log T<N> <Section> <text>`: one entry `- <date> (<caller>): <text>` at the end of `Progress`, `Validation`,
  `Reviews` or `Findings and decisions`. Multi-line text (verbatim test output) keeps its first line on the bullet and
  the rest in a code fence indented under it, so it can never open a section.
- `progress T<N> <text>`: one line in the epic's `progress.md` (`- <date> T<N> (<caller>): <text>`). A ticket with no
  epic has none; the helper says so.
- `status T<N> <status> [<note>]`: `Planned`, `Backfilled`, `Planning`, `Plan review`, `Executing`, `Validating`,
  `Implementation review`, `Approved`, `Escalated`, `Committed`. Sets the header and a Progress entry, and the
  Project Status: Planned/Backfilled → To Do; Planning/Executing/Validating/Escalated → In Progress; Plan review/
  Implementation review/Approved → In Review; Committed → Done, and the issue is closed with a comment linking the
  record. Escalated also comments. (Owner, 2026-11-18; Backfilled and Escalated are the agent's additions: a
  backfilled ticket hasn't started, an escalated one is still open.) The note is one line in the header.
- `sanitize [--repo <worktree>] [--max-chars <n>]`: stdin → stdout with local paths masked; secret-like strings, or
  more than `n` characters, are refused (exit 1). `rca` uses it for an RCA posted on a GitHub issue.
- **Kept as no-ops (no skill calls them since tracker #4 and #9):** `flush`, `queue …` (`--list` prints nothing) and `state …`
  are no-ops, since nothing is queued. `find`, `ticket`, `render`, `verify` and `extract-plan` were retired with the
  Confluence route and exit 2.
- `--dry-run` (callers pass it as `--tracker-dry-run`): print the helper command(s) the call would run; run nothing.
- `--no-tracker`: do nothing; say "ticket record skipped (--no-tracker)". Callers pass it on, also to sub-agents.

**Keys.** Only tracker keys `T<N>` (the issue number). The Jira/Confluence route is retired (owner, 2026-11-18,
tracker #2): an In Progress Jira ticket finishes in Jira and its `PIV record` comments are written by hand; a To Do
Jira ticket is imported (below) and then worked as its own `T<N>`, found by the Project's `Jira key` field or the
first line of its issue body. The helper refuses any other key (exit 2).

## Importing from Jira (`jira_import.py`)

One Jira epic and its To Do children per run (tracker #6; owner, 2026-11-18: pilot AIUE-299 first, the rest after it).
`--epic none` imports the To Do issues with no epic instead, and an epic with no To Do children is imported alone
(tracker #28).

1. **Snapshot** (the agent, through the Atlassian MCP; no script calls Jira): `searchJiraIssuesUsingJql` with `jql =
   parent = <EPIC> OR key = <EPIC>` (for `--epic none`: `project = AIUE AND parent is EMPTY AND issuetype != Epic AND
   statusCategory = "To Do"`), fields `summary, description, comment, status, issuetype, parent, labels,
   issuelinks, created`, `responseContentFormat: markdown`, `maxResults: 100`. A result over the token cap is saved to a
   file whole; that file, or the JSON written out, is the snapshot. Keep it in `../uedge-wt/data/<KEY>/`. The MCP
   leaves out an empty description (probed on AIUE-6, tracker #28); the script reads it as empty, and refuses only a
   missing `comment` field.
2. **Import**, from the worktree: `uv run .claude/skills/ticket-page/jira_import.py --snapshot <file> --epic <EPIC>
   [--first <KEY>] --out <dir>/mapping.json [--dry-run]`. Check the GraphQL budget first (`gh api rate_limit --jq
   .resources.graphql.remaining`; every session on the account shares it) and run no other `gh`-heavy session alongside.
   Every `gh` call of both scripts waits out a rate limit and retries (`ticket_page.gh_run`: until the reset, or 60 s
   per attempt for a secondary limit; at most 4 retries). Run `--dry-run` first: it reads only, prints each write and
   renders the bodies (`<dir>/bodies/`) and the epic documents (`<dir>/epic/`, started from the epic's existing ones, so
   only the changes show). It skips tickets whose record is complete. Like every ticket-page call it clones the tracker
   if its checkout is missing.
   - The epic becomes an Epic issue and each To Do child a sub-issue, with the label `from-jira` (`ai-layer` when Jira
     has it). Each is on the Project with Status To Do, the `Jira key` field and the Tier its Jira text states (the last
     `Tier S|M|L` with no other letter after it: "Tier M or L" and "Tier S/M" state none; otherwise empty, and
     `plan-feature` assigns it). "is blocked by" links between imported tickets
     become relations; other links are listed in the body.
   - The body is the Jira description and comments verbatim, after the line `_Imported from Jira <KEY> …_`, which makes
     a re-run skip what exists (or, if that line was edited, the Project item's `Jira key`).
   - One commit writes the epic's `epic.md` (the Jira description, owner comments under Decisions, the children not
     imported), `breakdown.md` (the Jira key → `T<N>` table and an entry per ticket) and `progress.md`. An epic with no
     To Do children gets no `breakdown.md` (its `epic.md` says so). With `--epic none` the issues get no parent, their
     records go to `docs/no-epic/`, and the commit writes only `docs/no-epic/breakdown.md`.
   - A tracker epic that already exists for a Jira epic (T10 for AIUE-222) is reused once its Project item's `Jira key`
     is set to the Jira epic: its `epic.md` is kept, `breakdown.md` and `progress.md` are added to.
   - Each ticket's record comes from `create`, then `status Backfilled` (the Ticket section is the import, not as
     filed). A re-run completes a record that lacks the Backfilled entry or a comment's entry (matched by `comment <id>`).
     A comment opening with `Owner,` / `Owner:` / `Owner (` / `Owner decision(s)` (not "Owner's ...") becomes a Findings and decisions entry; one opening with `PIV record`
     becomes a Progress entry.
   - The script refuses (exit 2) a snapshot whose comments are incomplete, and refuses (exit 1) secret-like text, both
     before anything is written.
3. **Jira pointer** (the agent, MCP `addOrEditJiraIssueComment`, `addCommentToJiraIssue` in older MCP versions, one per
   `mapping.json` entry): "Moved to the tracker
   (<date>): this ticket continues as T<N> (tracker issue #<N>). Jira is now its read-only archive." The Jira status is
   left as it is (owner, 2026-11-18).

## When to write (milestones)

| Milestone | Who | Call |
|---|---|---|
| Ticket filed (or a backfill) | `spec` | `create` (a backfill of a To Do ticket: then `status Backfilled`; of an In Progress one: a `log Progress` entry instead, `spec` step 4) |
| Plan (or RCA) written, revised or amended | `plan-feature`, `implement-fix`, the review loop | `publish`, `status Planning` / `Plan review` |
| A review round closes (APPROVE, or REVISE once its response is written) | the review loop | `log Reviews` (verdict and response) |
| End of `execute` | `execute` | **one** `log Progress` summary; `status Implementation review` |
| A `validate` run | `validate` | `log Validation` |
| An owner decision or an escalation | whoever records it | `log "Findings and decisions"`; `status Escalated` |
| The final commit, execution report and system review | `end-to-end-feature` / `implement-fix` | `log Progress "Committed <sha>"`, the two Findings and decisions entries, `status Committed <sha>` after the merge |

Per-task entries are not logged. Each call costs a fetch, a commit and a push (seconds), so log at milestones, not
per step.

## Configuration

| Setting | Value |
|---|---|
| Tracker | `.claude/tracker.toml` in the main checkout: `owner`, `repo`, `project`. Nothing else names it |
| Checkout | `<parent of the main checkout>/<repo>`, cloned on first use (`--tracker-dir` overrides) |
| Layout | the tracker's `README.md`: `docs/T<E>-<slug>/{epic.md, breakdown.md, progress.md}`, `docs/T<E>-<slug>/T<N>-<slug>/{record.md, plan.md \| rca.md}`, `docs/no-epic/T<N>-<slug>/` |
| Record | header table (Issue, Epic, Type / tier, Branch, PR, Status, Plan, Last update), the attribution line, `## Ticket`, `## Progress`, `## Validation`, `## Reviews`, `## Findings and decisions` |
| Test | `.claude/skills/ticket-page/selftest.sh` (offline: fake `gh`, a bare repo as the remote); run it after changing the helper |

## Process

Each write holds a lock on the tracker checkout (`<git dir>/ticket-page.lock`) from its checks to the push, so
parallel calls in one checkout take turns (a waiting call says so); the GitHub calls after the push run unlocked. It checks that the checkout is clean (no uncommitted changes to tracked files) and on its
default branch, runs `git fetch` and a rebase onto the remote, edits the file, makes one commit of the named paths
(`T<N> <command>: …`) and pushes. Only then the GitHub side (Project Status, comment, close), so a refused write
changes nothing on GitHub.

- **Remote unreachable:** the fetch or push fails, the helper says so and exits 0; the commit stays in the tracker
  checkout and the next call pushes it. Removing a worktree loses nothing.
- **Rebase conflict** (two sessions edited the same lines): the rebase is aborted, nothing is written, exit 2. Resolve
  it in the tracker checkout, then call again. Appends to different sections or files don't conflict.
- **Dirty checkout or another branch** (a hand edit not committed, a feature branch left checked out): nothing is
  written, exit 2, and the message names the files or the branch. Commit, discard or switch back, then call again.
- **Refused text** (exit 1): rewrite it without the secret-like string; the error names only its kind.
- Header edits (Branch, PR) the helper doesn't set are made by hand in the tracker checkout and committed the same
  way, with a Progress entry saying so.

## Attribution

Agents write through the owner's account, so the commit author proves nothing; the record's attribution line says so.
Mark **Owner** only when a source records it as the owner's, and cite it (an issue comment, the session's date);
**Reviewer** for a review report; **Agent** for the agent's own choices; otherwise **attribution unverified**
(`close-epic` rules).

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

The log sections are append-only: a later entry corrects an earlier one. Removing or editing an entry happens only on
the owner's or the coordinator's request, as a commit in the tracker checkout whose message says what was corrected and
why, plus a Progress entry saying so.

## Output

One line for the caller: what was written (`record created|exists`, `<kind> published`, `<Section> entry added`,
`status <S>`, `epic progress line added`) with the commit, or `skipped (<why>)`, plus any push or fetch failure and any
error verbatim.
