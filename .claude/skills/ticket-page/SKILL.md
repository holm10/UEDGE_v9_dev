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

- `create T<N>`: the record from the issue: the Ticket section is the issue body (headings demoted), the header has
  the issue type, the Project's Tier and status `Planned`. Placed under the issue's parent epic (`docs/T<E>-<slug>/`),
  or `docs/no-epic/`. An existing record is left as it is. `spec` calls it when it files a ticket; any skill that finds
  no record calls it first.
- `publish T<N> [--plan <file> | --rca <file>]`: copy the working copy (default `.claude/work/T<N>/plan.md`) to
  `plan.md` (or `rca.md`) next to the record, local paths masked; the header cites the publish date and sha256, a
  Progress entry and a one-line issue comment say so. Run it when the plan is written and each time it is revised.
- `log T<N> <Section> <text>`: one entry `- <date> (<caller>): <text>` at the end of `Progress`, `Validation`,
  `Reviews` or `Findings and decisions`.
- `progress T<N> <text>`: one line in the epic's `progress.md` (`- <date> T<N> (<caller>): <text>`). A ticket with no
  epic has none; the helper says so.
- `status T<N> <status> [<note>]`: `Planned`, `Backfilled`, `Planning`, `Plan review`, `Executing`, `Validating`,
  `Implementation review`, `Approved`, `Escalated`, `Committed`. Sets the header and a Progress entry, and the
  Project Status: Planned/Backfilled → To Do; Planning/Executing/Validating/Escalated → In Progress; Plan review/
  Implementation review/Approved → In Review; Committed → Done, and the issue is closed with a comment linking the
  record. Escalated also comments.
- `sanitize`: stdin → stdout with local paths masked and secret-like strings refused (exit 1).
- **Compatibility until tracker #4 adapts the callers:** `flush`, `queue …` (`--list` prints nothing) and `state …`
  are no-ops, since nothing is queued. `find`, `ticket`, `render`, `verify` and `extract-plan` were retired with the
  Confluence route and exit 2.
- `--dry-run` (callers pass it as `--tracker-dry-run`): print the helper command(s) the call would run; run nothing.
- `--no-tracker`: do nothing; say "ticket record skipped (--no-tracker)". Callers pass it on, also to sub-agents.

**Keys.** Only tracker keys `T<N>` (the issue number). The Jira/Confluence route is retired (owner, 2026-11-18,
tracker #2): an In Progress Jira ticket finishes in Jira and its `PIV record` comments are written by hand; a To Do
Jira ticket is worked after the import (tracker #6). The helper refuses any other key (exit 2).

## When to write (milestones)

| Milestone | Who | Call |
|---|---|---|
| Ticket filed (or a backfill) | `spec` | `create` (a backfill: then `status Backfilled`) |
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

Each write: `git fetch` in the tracker checkout, then a rebase onto the remote, then the file edit, one commit
(`T<N> <command>: …`) and `git push`. Then the GitHub side (Project Status, comment, close), so a refused write
changes nothing on GitHub.

- **Remote unreachable:** the fetch or push fails, the helper says so and exits 0; the commit stays in the tracker
  checkout and the next call pushes it. Removing a worktree loses nothing.
- **Rebase conflict** (two sessions edited the same lines): the rebase is aborted, nothing is written, exit 2. Resolve
  it in the tracker checkout, then call again. Appends to different sections or files don't conflict.
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
