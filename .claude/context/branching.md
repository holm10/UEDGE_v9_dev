# Branching — one ticket, one branch; the AI layer on its own track

Two kinds of work happen in this repo: **changing how agents work** (the AI layer) and **changing what UEDGE does**
(product). Mixing them on one branch makes PRs hard to review, makes a process change ride along with
physics, and leaves feature branches depending on unmerged tooling. This module is the policy.
`.claude/hooks/change_kind.py` enforces it (run before every agent `git commit` by `pre_tool_use.py`).

## Change classes (by path)

| Class | Paths | Belongs on |
|---|---|---|
| **process** | `CLAUDE.md`, `.mcp.json`, `.claude/**` (skills, agents, context, hooks, settings), `.githooks/**`, `.github/workflows/claude-*.yml` | an AI-layer branch (`CLAUDE.md` and `.claude/context/**` also on ticket branches as code-facts) |
| **working** | `.claude/work/**`, and the paths these documents used to be committed under: `.claude/plans/**`, `.claude/execution-reports/**`, `.claude/system-reviews/**`, `.claude/code-reviews/**`, `docs/{prds,specs,reviews,rca}/**` | **no branch**: gitignored, never committed (below). Deleting one that is still tracked is allowed |
| **product** | everything else: `*/*.m`/`.F`/`.v`/`.F90`, `setup.py`, `Makefile.Forthon`, `src/uedge/`, CI, `doc/`, and `docs/physics_specs/**` | a ticket branch |
| **shared** | `.gitignore` | any branch |

## Working documents live outside git; the record lives on Confluence and Jira

Ticket and epic documentation lives on Confluence and Jira, never in the repo. (Before this rule, plans, reviews and
epic documents were committed on the ticket and planning branches; PR #2 removed 1 282 of them, kept in the tag
`archive/AIUE-8-docs`.)

- **Ticket working documents** (the plan, review reports and responses, validation records and run protocols, the
  RCA, the code review, the execution report and the system-review notes) are written to the ticket's **working
  folder** `<worktree>/.claude/work/<KEY>/` (`issue-<N>` for a GitHub issue, the slug for work without a ticket). It
  is gitignored and never committed. Their lasting content goes to the ticket's Confluence page through the
  `ticket-page` skill: the plan (or RCA) is mirrored into the Plan (or RCA) section; each review round's verdict,
  counts, findings (one line each) and the response go to Reviews; validation results, failures quoted verbatim, go
  to Validation; decisions and anything a later reader needs go to Findings and decisions. A ticket with no epic PRD
  page keeps only a capped summary: at most 8-9 `PIV record` Jira comments of at most 1500 characters, MINOR detail
  dropped (`ticket-page` → Jira fallback). A GitHub issue with no Jira ticket gets its RCA as a comment on the issue
  (`rca`). **Work with no ticket record** (no Jira key, `--no-tracker`, or physics without a ticket) has no page: the
  review summary it would have had (each round's verdict, counts, one line per finding, the response) goes into the
  **PR description**, as does whatever else must outlive the worktree. The full working files are disposable.
- **Raw data a later ticket must re-read** (measurement collections, build records) is not a working document.
  Before the worktree is removed, copy it to `../uedge-wt/data/<KEY>/` (local, outside every worktree) or publish it
  as a release asset, and record where it is on the ticket page and in a comment on the dependent ticket. AIUE-87's
  collections are kept in `../uedge-wt/data/AIUE-87/` (AIUE-148); AIUE-92 re-collected all eight families and used
  them as a bitwise cross-check, and its own collections, which a later `measure_roundoff.py analyze --write`
  needs, are in `../uedge-wt/data/AIUE-92/`.
- **Epic documents** live on Confluence, under the PRD page: the PRD itself (the page is the source; `create-prd`
  keeps a local working copy), `PRD reviews: <EPIC>` (each review round summarised), `Spec: <epic> - Ticket
  Breakdown` (the breakdown, with each ticket's key and page id), `Progress: <EPIC>` (the progress log: dated,
  append-only lines, owner decisions attributed as in `close-epic`; `spec` creates it, `execute`, `validate`, the
  review loop, `end-to-end-feature` and `implement-fix` append a line per milestone through `ticket-page progress`,
  `close-epic` reads it), `Ticket plans: <EPIC>` with one page per
  ticket, and `Close-out: <EPIC> - …`. Local working copies (the PRD draft, review reports, the breakdown draft, the
  close-out record and its sources snapshot) go in `.claude/work/<EPIC>/` of the checkout the skill runs in.
- **No planning branch.** An epic no longer has a `feature/v9-<EPIC>-planning` branch: nothing it held is committed
  any more. Existing planning branches are left as they are; `close-epic` may read one, or its archive tag, as a
  historical source. **Before a planning branch is ever deleted**: tag its tip `archive/<EPIC>-planning` and push the
  tag (`git tag archive/<EPIC>-planning <branch> && git push origin archive/<EPIC>-planning`), and write its PRD review
  rounds (verdict, counts, one line per finding, the response) to `PRD reviews: <EPIC>`, citing the tag. Done for all
  three: the planning branches of AIUE-5, AIUE-8 and AIUE-9 are deleted, and live on as the pushed tags
  `archive/AIUE-5-planning`, `archive/AIUE-8-planning` and `archive/AIUE-9-planning` (AIUE-5's and AIUE-9's review
  rounds are on `PRD reviews: AIUE-5` and `PRD reviews: AIUE-9`).
- **Physics specs stay in the repo.** `docs/physics_specs/<feature>.md` is product documentation: the approved spec
  is committed on the ticket branch with the physics change it specifies (`CLAUDE.md` → Hard rules,
  `physics-workflow.md`). Its review reports are working documents like any other.
- **Robustness.** Confluence or Jira being down never blocks code work: the working files and the `ticket-page`
  outbox and sent log (in the worktree's git directory) keep the record until the next flush. **Both are lost when the
  worktree is removed** (`git worktree remove`), so flush the ticket page (`ticket-page <KEY> flush`, and
  `queue --list` empty) before removing a worktree; anything not on the page by then is gone. For the same reason
  ticket work never runs in a worktree that something else can remove (see Worktrees), and a subagent doing ticket
  work flushes and checks that `queue --list` is empty before it returns.
- **Enforcement.** `.gitignore` lists every working path, and `change_kind.py` refuses a staged working document on
  any branch, pointing to the ticket page.
- **Renames.** Moving a working document into a product path (`git mv`) is refused like adding it. A document that
  really belongs in the repo (a physics spec) is added as a new file on purpose, with the reason in the commit.
- **Tickets started before this rule** may track a plan, reviews or other working documents on their branch
  (`.claude/plans/`, `docs/reviews/`, …). They **must be removed before `validate` and the PR**: the range check
  (`validate` step 0, and CI) refuses the branch until they are gone. Before removing them:
  1. copy the plan to `.claude/work/<KEY>/plan.md` and work on that copy (`ticket-page <KEY> publish` mirrors it);
  2. put each review round that the page records only as a path on the ticket page: one `ticket-page <KEY> log
     Reviews` entry per round with its verdict, counts, one line per finding and the response (marked "backfilled
     from <path> at <sha>"), then `flush`;
  3. tag the branch tip `archive/<KEY>-docs` and push the tag (`git tag archive/<KEY>-docs && git push origin
     archive/<KEY>-docs`), and cite the tag on the page (`log "Findings and decisions" "Agent: the committed working
     documents are archived in tag archive/<KEY>-docs" --flush`), as was done for AIUE-8 (`archive/AIUE-8-docs`);
  4. `git rm` them in one commit ("Removes the <KEY> working documents from git"; deletions are allowed).

**The code-facts exception.** The AI layer *describes* the code (`CLAUDE.md` naming and gotchas,
`.claude/context/*.md`). When a ticket changes a fact it describes (AIUE-5 retiring MPPL makes
`mppl-fortran.md` wrong), the matching AI-layer edit ships **with that ticket**, so the docs and the code
never disagree on any branch. Mark that commit with the trailer:

```
AI-layer: code-facts
```

The trailer means: *this edit only keeps the AI layer accurate about code this branch changes.* It never
covers a process change (a new skill step, a changed review gate, a new hook rule). Those go on an AI-layer
branch.

## Branches

| Kind | Name | Base | Carries |
|---|---|---|---|
| Protected | `main`, `develop`, `v9-main`, `v9-develop` | — | **nothing directly**; PRs only |
| AI layer | `feature/v9-ai-<slug>` (legacy: `v9-agentic`) | `v9-develop` | process |
| Jira ticket | `feature/v9-<KEY>-<slug>`, e.g. `feature/v9-AIUE-12-freeze-bbb` (or `bugfix/v9-<KEY>-<slug>`) | `v9-develop`, or the branch of the ticket it depends on (stacked) | product, incl. an approved physics spec (+ code-facts) |
| GitHub issue | `bugfix/v9-issue-<N>-<slug>` | `v9-develop` | product |

An epic has no branch of its own (no planning branch; see above).

Names must match the mandatory patterns in `doc/workflow.md` (`feature/v9-*`, `bugfix/v9-*`). `<slug>` is
kebab case and at most about 40 characters. Putting the Jira key in the branch name makes Jira link the branch,
commits and PR to the ticket automatically.

**One branch per ticket, not per epic.** An epic is the set of its ticket PRs. Use an epic integration branch
(`feature/v9-<EPIC>-integration`) only when tickets really can't land on `v9-develop` one by one. Say so
in the spec breakdown, and target the ticket PRs at it.

**Stacked tickets.** A ticket that depends on an unmerged ticket branches from that ticket's branch, and its PR
targets that branch. After the parent merges, rebase it onto `v9-develop` (`git rebase --onto v9-develop <parent>`).
A rebase of a branch that is already pushed (a stacked PR after its parent changes or merges) needs `git push
--force-with-lease=<branch>:<old sha> origin <branch>`. Auto mode refuses it ("Git Destructive"); don't retry it or
work around it. As soon as the rebase is done and checked, give the owner that exact command with the old sha, then
wait for their push. When planning a stacked ticket, budget one owner-run force-push per parent change (AIUE-218:
refused for #73, #74 and #75 in AIUE-211).

## Worktrees — one per active ticket

```bash
git fetch origin
git worktree add -b feature/v9-AIUE-12-freeze-bbb ../uedge-wt/AIUE-12 origin/v9-develop
cd ../uedge-wt/AIUE-12
python -m venv .venv && . .venv/bin/activate      # own env: `pip install .` installs compiled modules
pip install . -C "--build-option=--serial"
```

Run `git worktree add` from the main checkout (the first line of `git worktree list`), or give the absolute path: the
path is relative to the current directory, and from inside a ticket worktree `../uedge-wt/<KEY>` lands in
`uedge-wt/uedge-wt/<KEY>` (AIUE-217).

- **Give each worktree its own virtualenv.** Two worktrees that install into the same env overwrite each other's
  `uedge` build, and the tests then run the wrong code.
- The regression worktree `../uedge-pytests` is shared. It holds only tests and reference data.
- **Ticket work always runs in an explicit worktree** (`git worktree add … ../uedge-wt/<KEY>`, above), also when a
  subagent does it. Never use the Agent tool's `isolation: "worktree"` for ticket work: Claude Code removes such a
  worktree by itself when the subagent finishes without committed changes, and sweeps old ones later, and gitignored
  working documents don't stop either. The working folder and the unsent `ticket-page` entries would go with it.
  Give the subagent the worktree path instead. A subagent doing ticket work flushes the ticket page and checks that
  `queue --list` (and `queue --epic --list`) prints nothing before it returns; if a flush fails, it says so with the
  worktree path, and the caller flushes later.
- Remove a worktree after its PR merges: `git worktree remove ../uedge-wt/AIUE-12`. **Flush first**: the working
  folder `.claude/work/<KEY>/` and the `ticket-page` outbox go with the worktree, so run `ticket-page <KEY> flush`
  and check that nothing is queued (`ticket_page.py queue --repo <worktree> --key <KEY> --list` prints nothing).
  Raw data a later ticket re-reads goes to `../uedge-wt/data/<KEY>/` first (Working documents, above). A ticket run
  as `plan-feature` → `execute` (not `end-to-end-feature`) runs `execution-report` and `system-review` before its
  worktree is removed, while `.claude/work/<KEY>/` still holds the plan; for an S ticket only when the run diverged
  (as `end-to-end-feature` Step 5). AIUE-161's retrospective had to read its plan back from the ticket page.
  For a Jira ticket, after the PR merges: `ticket-page <KEY> status Committed` with the merge sha, then transition
  the ticket to Done (`getTransitionsForJiraIssue`, then `transitionJiraIssue`), then flush and remove. The owner's
  merge is the confirmation, so a ticket's Done needs no extra question, unlike `close-epic`'s for an epic, which
  never transitions the children itself (AIUE-201; `plan-feature` Phase 6 moves it to In Progress).

## Improving the AI layer while doing ticket work

Don't fix a skill, agent or hook on a ticket branch, even when the ticket exposed the problem.

1. Note it in the ticket's execution report (`execution-report` → `.claude/work/<KEY>/execution-report.md`, local; its
   divergences and recommendations go to the ticket page's Findings and decisions).
2. Run `system-review` on it. Apply its recommendations on a `feature/v9-ai-<slug>` branch in its own PR.
3. If the problem blocks the ticket, merge the AI-layer PR first, then rebase the ticket branch.

## Bootstrap (until the AI layer is on `v9-develop`)

Ticket branches based on `v9-develop` don't have `.claude/` yet. Until the AI-layer branch (`v9-agentic`) is merged:

- Base ticket branches on the AI-layer branch tip, and record that in the PR description.
- After the AI layer merges, `git rebase --onto origin/v9-develop v9-agentic <ticket-branch>` drops the AI commits
  from the ticket's history.
- Prefer merging the AI layer first. Then this section goes away.

## Guard rails on the AI layer changing itself

- **Simplicity budget.** Prefer conventions and short skill text over new code paths. An AI-layer change that adds
  more than 300 lines of tooling code or more than 40 test cases states a one-line justification in its PR
  (`.claude/context/process-tiers.md` → Simplicity budget). AI-layer changes get one review round plus their tests;
  round 2 only for an open BLOCKER/MAJOR.
- **Agents never apply process changes automatically.** `system-review` files them as `ai-layer` Jira issues
  (fallback without Jira: `.claude/work/<KEY>/ai-layer-backlog.md`, local, plus a Findings and decisions entry on the
  ticket page, filed as issues at the next session that has Jira). They land through a `feature/v9-ai-*` PR that a
  person reviews.
- **The code-facts trailer is narrow.** It covers only `CLAUDE.md` and `.claude/context/**`. The hook blocks
  skills, agents, hooks and settings on ticket branches even with the trailer.
- **Facts are checked, not trusted.** `check_context_refs.py` compares every cited `path:line` with the locked
  text. `--update` (re-locking) is only allowed after the claim has been re-read. A reviewer who sees a lock
  change without the matching doc or code change treats it as a finding.
- **Backstop.** `.github/workflows/claude-context-drift.yml` runs the drift check and the branch-policy range check
  on every PR to `v9-develop`, and the drift check weekly on `v9-develop`. A scheduled failure opens an `ai-layer`
  GitHub issue.

## Checking

```bash
uv run .claude/hooks/change_kind.py --staged                 # before a commit (the hook does this for agents)
uv run .claude/hooks/change_kind.py --range origin/v9-develop...HEAD   # a whole branch, before opening a PR
uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop   # are the AI layer's code facts still true?
bash .claude/hooks/test_change_kind.sh                    # after changing change_kind.py or pre_tool_use.py
```

Exit 0 means clean, 1 means violations (printed with the offending paths), 2 means the check couldn't run.
`--staged` can't see the commit message: `CLAUDE.md` or `.claude/context/` on a ticket branch gets a `NOTE:` (exit 0)
and the trailer is checked on `git commit`; `--staged --message "<message>"` checks it now.

`--range` also checks the **PR size budget** and prints `WARNING: PR size budget …` lines (never a failure): more
than 40 added files or 3,000 added lines outside product source and tests, any added file over 1 MB, or data-like
files (`*.npz`, `*.hdf5`/`*.h5`, `*.log`, JSON records). Raw run data belongs in `.claude/work/<KEY>/` or a scratch
directory and is summarised on the ticket page; a file that really belongs in the PR is justified in its
description. (PR #2 carried 1,282 generated files.)
