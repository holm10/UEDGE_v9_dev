---
name: implement-fix
description: Implements a UEDGE bug fix for a GitHub issue from its RCA document, verifies it on the reproducing case, and runs the validate gate. Use after an RCA document exists and you are ready to fix the issue.
argument-hint: [github-issue-id] [--no-tracker] [--tracker-dry-run]
allowed-tools: Read, Write, Edit, Grep, Glob, Bash(git:*), Bash(gh:*), Bash(pip:*), Bash(python:*), Bash(python3:*), Bash(pytest:*), Bash(make:*), Bash(uv:*), mcp__atlassian__getAccessibleAtlassianResources, mcp__atlassian__getJiraIssue, mcp__atlassian__searchConfluenceUsingCql, mcp__atlassian__getConfluencePage, mcp__atlassian__getConfluencePageDescendants, mcp__atlassian__fetch
---

# Implement Fix: GitHub Issue #$ARGUMENTS

## Prerequisites

- RCA at `.claude/work/issue-$ARGUMENTS/rca.md` in the issue's worktree (a local working copy, never committed;
  create it with the `rca` skill first). If the worktree has no copy (a fresh worktree, another machine), rebuild it
  from its published copy: with a Jira key, read the ticket page with `fetch` (`ticket-page` step 3.1, saved), then
  `ticket_page.py extract-plan --current <saved page> --out <that path>` (the page's RCA section), then
  `ticket_page.py state --repo <worktree> --key <KEY> --save-plan <that path> --plan-title RCA --set
  plan_source="page version <N>"` (`N` = the fetch's `metadata.version`); otherwise from the RCA comment on the
  GitHub issue (`gh issue view $ARGUMENTS --comments`). Neither exists → run `rca` again.
- On the issue's own branch `bugfix/v9-issue-<N>-<slug>` and worktree (created by `rca`; create it now as in
  `.claude/context/branching.md` if missing), never on `v9-develop` or an AI-layer branch.
- Ticket record: only if the issue maps to a Jira ticket (the RCA or the user names the key); a GitHub issue with no
  Jira key gets no record (its RCA is a comment on the GitHub issue, posted by `rca`). With an epic PRD page, the RCA
  is this ticket's plan: `rca` has normally published it already; if not (or after a revision), run `ticket-page
  <KEY> publish --rca .claude/work/issue-$ARGUMENTS/rca.md` (it fills the ticket's page that `spec` created, or
  creates it if there is none; the page mirrors the RCA under `## RCA`, cited by publish date and sha256; nothing is
  committed). Without one, the same call posts a short `PIV record: plan` comment summarising the RCA.
  `--no-tracker` skips the record; `--tracker-dry-run` only shows it. The allowed tools above
  pre-approve the helper and the Atlassian reads; writes to Jira and Confluence still go through the normal
  permission prompt.
- Optional: `gh` authenticated. Issues may live upstream — use `gh issue view $ARGUMENTS -R LLNL/UEDGE` if the
  issue is not on `origin`.

## 1. Read and understand

- Read the RCA in full: root cause, fix strategy, files, reproduction, validation.
- Read `CLAUDE.md` and the `.claude/context/` modules for the files involved (`mppl-fortran.md` for `.m`,
  `variables-forthon.md` for `.v`, `openmp-jacobian.md` for anything in the `pandf` tree or `ppp/`,
  `uedge-gotchas.md` when reproducing or checking the fix runs cases).
- Decide whether the fix **changes default results**. A bug fix in physics/numerics often does: if so, the
  moved cases are expected but must be listed and explained (`CLAUDE.md` → Hard rules). A fix in a refactor
  path or Python/build code should leave results unchanged.

## 2. Reproduce first

Follow the RCA reproduction on the current build and confirm the failure (error, wrong value, crash,
serial/parallel mismatch). Record the observed output — you will compare against it.

## 2b. Plan review (high-risk fixes only)

Tier the fix (`.claude/context/process-tiers.md`). If it touches the `pandf` tree, `ppp/`, the Jacobian, a `.v` file
or the build (L), run the **Adversarial review loop** in `.claude/skills/end-to-end-feature/SKILL.md` with `stage:
plan` on the intended change (the RCA's fix section, or a short plan) **before writing code**. Any other fix skips it, until the diff says otherwise: the review gate re-tiers a fix whose diff prints
`HIGH-RISK: yes` (`process-tiers.md` → Check the tier against the diff). A fix in any other Fortran source (`.m`, `.F90`, hand-written `.f`) needs no plan
review, but is at least M: its implementation review runs on Opus (`FORTRAN: yes`).

## 3. Implement

- Edit the `.m`/`.v`/`.F90`/`.py` sources named in the RCA — never generated `.F` files.
- Follow surrounding style (fixed-form MPPL, `#` comments, `xerrab`/`remark`, `ixm1`/`ixp1`, `Selec` ranges).
- Keep the change minimal; note any related code that needs the same fix (other BC branches, the other
  X-point, other species loops) and fix it consistently.
- Comment non-obvious fixes briefly (what was wrong, not the history).

## 4. Verify

1. Rebuild: `pip install . -C "--build-option=--serial"`; fix errors at the `.m` source.
2. Re-run the reproduction — the failure must be gone.
3. If the fix touches the `pandf` tree, threadprivate variables, or `ppp/`: run the OpenMP serial-vs-parallel
   check (`validate --omp`).
4. Run the `validate` skill with the suites matching the area.

Do not proceed while anything is ❌. Never loosen tolerances or skip suites.

With a Jira key, queue the reproduction before/after (`log Progress`), and run `validate` with `--ticket <KEY>` (the
issue branch name has no key), so it queues its result. They go out
with the implementation review's flush (4c) or the end-of-ticket flush (step 6).

## 4b. AI-layer facts

Run `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`. If the fix moved or renamed code that `CLAUDE.md` or `.claude/context/` cite, or changed a default
listed in `.claude/context/physics-models.md`, update those facts (as in `execute` step 3b). Commit them with the
trailer `AI-layer: code-facts`.

## 4c. Adversarial review

Write the handoff note `.claude/work/issue-$ARGUMENTS/handoff.md` (≤60 lines: state, branch and tip, done, open items,
how to verify). Then run the **Adversarial review loop** in `.claude/skills/end-to-end-feature/SKILL.md` with `stage:
implementation`. The reference is the RCA document (root cause, the fix it proposes, the reproduction) and, for a
Jira ticket, its acceptance criteria. The fix is done only after APPROVE on the final diff. Fix rounds follow the
loop: plain MINORs fixed by the loop's runner, BLOCKER/MAJOR fixes by a fresh small agent from the handoff note (never
by resuming the long agent), rounds 2+ as verification rounds.

## 5. Regression coverage

The regression suite lives on the `pytests` branch and is being redesigned. Do not add tests to this repo.
Instead, record in the report the exact case (input deck/script and settings) that reproduces the bug, so a
regression case can be added there.

## Output report

```
Fix: GitHub issue #$ARGUMENTS — <title>  (<issue URL>)
Root cause: <one line from RCA>

Changes:
  <file>:<lines> — <what changed>

Reproduction: before <observed>, after <observed>
Default results: unchanged | changed — <cases moved, why this is correct>
Validate: <validate report block>
Regression case to add on pytests branch: <case + settings>
```

Suggested commit message (repo style, see `commit` skill):

```
Fixes <short description> (#$ARGUMENTS)

<What was wrong and how it is fixed; whether default results change.>
```

Optional follow-ups with `gh` (comment, labels, close) only when the user asks.

**Where the record goes without a Jira key.** The review reports and responses are local working files
(`.claude/work/issue-$ARGUMENTS/reviews/`, never committed), and there is no ticket page. Put the review outcome
(verdict, rounds, open or deferred findings, criteria not independently verified) and the reproduction before/after
in the PR description; post it on the issue only when the user asks.

## 5b. Ticket record after the commit

With a Jira key, after the fix is committed: `ticket-page <KEY> status Committed`, `ticket-page <KEY> progress
"committed <sha>"` and `ticket-page <KEY> log Progress "Committed <sha>: <subject>"`, queued: step 6's
`system-review` flushes it (`ticket-page` → "When to flush"); add `--flush` if step 6 won't run in this session. If
this skill runs as a
subagent, it runs in the issue's explicit worktree (never an Agent `isolation: "worktree"` one) and checks before
returning that `queue --list` and `queue --epic --list` print nothing.

## 6. Process lessons

After the fix is approved and committed, run `execution-report` and then `system-review`. Its recommendations become `ai-layer`
issues (see `system-review`), never edits on this branch.

## Notes

- If the RCA turns out to be wrong, update the working copy with the new findings before changing more code, and
  publish the revision (`ticket-page <KEY> publish --rca …`, or, for a GitHub issue only, a new comment on the issue
  that starts "Revises the RCA above:", asking first as `rca` does).
- Flush the ticket page (nothing queued) before the worktree is removed: the working folder goes with it.
- Extra problems found along the way go into separate issues/RCAs, not this fix.
