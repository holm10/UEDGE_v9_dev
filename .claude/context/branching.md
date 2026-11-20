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

## Working documents live outside git; the record lives in the tracker

Ticket and epic documentation lives in the private tracker repository, never in this repo. `.claude/tracker.toml` is
the only place in this repo that names it (owner, repo, Project number); nothing else hard-codes them, and its local
checkout sits next to `uedge-wt/` (AIUE-287, tracker epic #1). The work before the tracker is archived read-only as
Markdown in the tracker's `docs/archive/` (T164): `jira/AIUE-<n>.md` for every Jira issue, `confluence/<id>-<slug>.md`
for every Confluence page (the folder's index lists the page ids). AIUE keys and page ids are cited as history; Jira and
Confluence are no longer read or written, and the Atlassian MCP is gone. (Before the
working-documents rule, plans, reviews and epic documents were committed on the ticket and planning branches; PR #2
removed 1 282 of them, kept in the tag `archive/AIUE-8-docs`.)

- **The record of a ticket.** A tracker ticket's key is `T<N>`, its issue number. Its record is the issue (status,
  Project fields, short discussion) plus `docs/<epic>/T<N>-<slug>/` in the tracker: `record.md` (Ticket, then the
  append-only Progress, Validation, Reviews, and Findings and decisions sections) and `plan.md` or `rca.md`. The
  layout is in the tracker's README. `ticket-page` writes it; each call is one commit straight to the tracker's `main`
  after `git pull --rebase`. The branch policy (Enforcement, below) covers this repository only, so it doesn't check
  commits in the tracker (owner, 2026-11-18, tracker #3).
- **Ticket working documents** (the plan, review reports and responses, validation records and run protocols, the
  RCA, the code review, the execution report, the system-review notes and the probe scripts a plan cites, under
  `probes/`, AIUE-238) are written to the ticket's **working
  folder** `<worktree>/.claude/work/<KEY>/` (`issue-<N>` for a GitHub issue, the slug for work without a ticket). It
  is gitignored and never committed. Their lasting content goes to the record through `ticket-page`: the plan (or
  RCA) is published as `plan.md` (or `rca.md`) next to `record.md`; each review round's verdict, counts, findings (one
  line each) and the response go to Reviews; validation results, failures quoted verbatim, go to Validation;
  decisions and anything a later reader needs go to Findings and decisions. A GitHub issue with no tracker ticket gets
  its RCA as a comment on the issue (`rca`). **Work with no ticket record** (no tracker ticket, `--no-tracker`, or
  physics without a ticket) has no record: the review summary it would have had (each round's verdict, counts, one
  line per finding, the response) goes into the **PR description**, as does whatever else must outlive the worktree.
  The full working files are disposable.
- **Raw data a later ticket must re-read** (measurement collections, build records) is not a working document.
  Before the worktree is removed, copy it to `../uedge-wt/data/<KEY>/` (local, outside every worktree) or publish it
  as a release asset, and record where it is in the record and in a comment on the dependent ticket. AIUE-87's
  collections are kept in `../uedge-wt/data/AIUE-87/` (AIUE-148); AIUE-92 re-collected all eight families and used
  them as a bitwise cross-check, and its own collections, which a later `measure_roundoff.py analyze --write`
  needs, are in `../uedge-wt/data/AIUE-92/`.
- **Epic documents** live in the tracker under `docs/T<E>-<slug>/`: `epic.md` (the PRD, with its review rounds in its
  Reviews section; `create-prd`), `breakdown.md` and `progress.md` (`spec` creates them; the progress log is dated,
  append-only lines, owner decisions attributed as in `close-epic`; `execute`, `validate`, the review loop,
  `end-to-end-feature` and `implement-fix` append a line per milestone through `ticket-page progress`), the tickets'
  record directories, and `closeout.md` (`close-epic`). The epic is an issue of type Epic, its tickets sub-issues.
  Local working copies (the PRD draft, review reports, the breakdown draft, the close-out record and its sources
  snapshot) go in `.claude/work/<EPIC>/` of the checkout the skill runs in. The Confluence PRD, `PRD reviews`,
  `Spec`, `Progress`, `Ticket plans` and `Close-out` pages of the Jira epics are archive.
- **No planning branch.** An epic has no `feature/v9-<EPIC>-planning` branch: nothing it held is committed any more.
  `close-epic` may read an old one, or its archive tag, as a historical source. **Before a planning branch is ever
  deleted**: tag its tip `archive/<EPIC>-planning` and push the tag (`git tag archive/<EPIC>-planning <branch> && git
  push origin archive/<EPIC>-planning`). Done for all three: the planning branches of AIUE-5, AIUE-8 and AIUE-9 are
  deleted, and live on as the pushed tags `archive/AIUE-5-planning`, `archive/AIUE-8-planning` and
  `archive/AIUE-9-planning` (AIUE-5's and AIUE-9's review rounds are on the archived Confluence pages `PRD reviews:
  AIUE-5` and `PRD reviews: AIUE-9`).
- **Physics specs stay in the repo.** `docs/physics_specs/<feature>.md` is product documentation: the approved spec
  is committed on the ticket branch with the physics change it specifies (`CLAUDE.md` → Hard rules,
  `physics-workflow.md`). Its review reports are working documents like any other.
- **Robustness.** A record has nothing queued: each `ticket-page` call is a commit in the tracker checkout, which sits
  outside every worktree, and a failed push is retried on the next call (tracker #2). The working folder
  `.claude/work/<KEY>/` is lost with the worktree (`git worktree remove`), so whatever must outlive it is in the record
  or `../uedge-wt/data/<KEY>/` first. For the same reason ticket work never runs in a worktree that something else can
  remove (see Worktrees).
- **Enforcement.** `.gitignore` lists every working path, and `change_kind.py` refuses a staged working document on
  any branch, pointing to the working folder and the record. The hook applies the branch policy to commits in this
  repository only (any checkout sharing its git directory, worktrees included); a commit in another repository is not
  checked.
- **Renames.** Moving a working document into a product path (`git mv`) is refused like adding it. A document that
  really belongs in the repo (a physics spec) is added as a new file on purpose, with the reason in the commit.
- **Tickets started before this rule** may track a plan, reviews or other working documents on their branch
  (`.claude/plans/`, `docs/reviews/`, …). They **must be removed before `validate` and the PR**: the range check
  (`validate` step 0, and CI) refuses the branch until they are gone. Before removing them:
  1. copy the plan to `.claude/work/<KEY>/plan.md` and work on that copy (`ticket-page T<N> publish` publishes it);
  2. put each review round that is recorded only as a path into the record: one `ticket-page T<N> log Reviews` entry
     per round with its verdict, counts, one line per finding and the response (marked "backfilled from <path> at
     <sha>") (legacy Jira tickets used `PIV record` comments; none is left, T164);
  3. tag the branch tip `archive/<KEY>-docs` and push the tag (`git tag archive/<KEY>-docs && git push origin
     archive/<KEY>-docs`), and cite the tag in the record (`log T<N> "Findings and decisions" "Agent: the committed
     working documents are archived in tag archive/<KEY>-docs"`), as was done for AIUE-8 (`archive/AIUE-8-docs`);
  4. `git rm` them in one commit ("Removes the <KEY> working documents from git"; deletions are allowed).
- **Jira tickets at the switch.** Jira tickets already In Progress when the tracker started finished in Jira, with their
  `PIV record` comments written by hand (owner, 2026-11-18); none was left at the archive export (T164). To Do Jira
  tickets are imported as tracker issues (label `from-jira`, the old key in the Project's `Jira key` field; tracker #6)
  and worked as `T<N>` tickets.

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
| Tracker ticket | `feature/v9-T<N>-<slug>`, e.g. `feature/v9-T12-freeze-bbb` (or `bugfix/v9-T<N>-<slug>`), `<N>` the tracker issue number | `v9-develop`, or the branch of the ticket it depends on (stacked) | product, incl. an approved physics spec (+ code-facts) |
| Jira ticket (legacy: In Progress at the switch) | `feature/v9-<KEY>-<slug>`, e.g. `feature/v9-AIUE-12-freeze-bbb` (or `bugfix/v9-<KEY>-<slug>`) | as a tracker ticket | product, as a tracker ticket |
| GitHub issue | `bugfix/v9-issue-<N>-<slug>` | `v9-develop` | product |

An epic has no branch of its own (no planning branch; see above).

Names must match the mandatory patterns in `doc/workflow.md` (`feature/v9-*`, `bugfix/v9-*`). `<slug>` is
kebab case and at most about 40 characters. The `T<N>` key in the branch name names the tracker issue that the branch,
its commits and its PR belong to.

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
git worktree add -b feature/v9-T12-freeze-bbb ../uedge-wt/T12 origin/v9-develop
cd ../uedge-wt/T12
python -m venv .venv && . .venv/bin/activate      # own env: `pip install .` installs compiled modules
pip install . -C "--build-option=--serial"
```

Run `git worktree add` from the main checkout (the first line of `git worktree list`), or give the absolute path: the
path is relative to the current directory, and from inside a ticket worktree `../uedge-wt/<KEY>` lands in
`uedge-wt/uedge-wt/<KEY>` (AIUE-217).

- **Give each worktree its own virtualenv.** Two worktrees that install into the same env overwrite each other's
  `uedge` build, and the tests then run the wrong code.
- **Ticket work always runs in an explicit worktree** (`git worktree add … ../uedge-wt/<KEY>`, above), also when a
  subagent does it. Never use the Agent tool's `isolation: "worktree"` for ticket work: Claude Code removes such a
  worktree by itself when the subagent finishes without committed changes, and sweeps old ones later, and gitignored
  working documents don't stop either. The working folder would go with it. Give the subagent the worktree path
  instead. (`ticket-page` writes go straight to the tracker checkout, outside the worktree, so nothing is left to
  flush; a subagent reports any `push failed` line it saw, and the next `ticket-page` call pushes the commit.)
- Remove a worktree after its PR merges: `git worktree remove ../uedge-wt/T12`. The working folder
  `.claude/work/<KEY>/` goes with the worktree, so what must outlive it is in the record first. Raw data a later ticket re-reads goes to `../uedge-wt/data/<KEY>/` first (Working documents, above). A ticket run
  as `plan-feature` → `execute` (not `end-to-end-feature`) runs `execution-report` and `system-review` before its
  worktree is removed, while `.claude/work/<KEY>/` still holds the plan; for an S ticket only when the run diverged
  (as `end-to-end-feature` Step 5). AIUE-161's retrospective had to read its plan back from the archived Confluence ticket page.
  For a tracker ticket, after the PR merges: `ticket-page T<N> status Committed <merge sha>` (Project Status Done,
  issue closed), then remove the worktree. The owner's merge is the confirmation, so a ticket's Done needs no extra
  question, unlike `close-epic`'s for an epic, which never closes the children itself (AIUE-201; `plan-feature`
  Phase 6 moves it to In Progress). Jira takes no writes: no Jira ticket was In Progress at the archive export (0 of
  317, 2026-11-20, T164).

## Improving the AI layer while doing ticket work

Don't fix a skill, agent or hook on a ticket branch, even when the ticket exposed the problem.

1. Note it in the ticket's execution report (`execution-report` → `.claude/work/<KEY>/execution-report.md`, local; its
   divergences and recommendations go to the record's Findings and decisions).
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
- **Agents never apply process changes automatically.** `system-review` files them as `ai-layer` issues in the
  tracker (`.claude/tracker.toml`) under the parent issue "AI-layer improvements" (fallback without `gh`:
  `.claude/work/<KEY>/ai-layer-backlog.md`, local, plus a Findings and decisions entry in the ticket's record, filed
  as issues at the next session that has `gh`). They land through a `feature/v9-ai-*` PR that a person reviews.
- **Every AI-layer issue lives under the parent issue "AI-layer improvements"** in the tracker (label `ai-layer`;
  found by its title, never by a hard-coded number): a fix, gotcha, tooling or process ticket for the AI layer,
  whoever files it, is a Task, Feature or Bug sub-issue of it with the label `ai-layer`, never an epic of its own.
  History: the owner's rule of 2026-10-28 put them under the Jira epic AIUE-222 (AIUE-72 was converted to a story
  under it); the tracker's parent took its place (tracker #4). A GitHub `ai-layer` issue (the weekly drift check's,
  below) that is turned into a ticket goes there too. The one exception is an AI-layer slice of another epic's
  breakdown (`spec`), such as AIUE-17 (AIUE-5) and AIUE-102/AIUE-108 (AIUE-9): it keeps that epic as its parent and
  carries the label.
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
directory and is summarised in the ticket's record; a file that really belongs in the PR is justified in its
description. (PR #2 carried 1,282 generated files.)
