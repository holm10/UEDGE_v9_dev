# Branching — one ticket, one branch; the AI layer on its own track

Two kinds of work happen in this repo: **changing how agents work** (the AI layer) and **changing what UEDGE does**
(product). Mixing them on one branch makes PRs hard to review, makes a process change ride along with
physics, and leaves feature branches depending on unmerged tooling. This module is the policy.
`.claude/hooks/change_kind.py` enforces it (run before every agent `git commit` by `pre_tool_use.py`).

## Change classes (by path)

| Class | Paths | Belongs on |
|---|---|---|
| **process** | `CLAUDE.md`, `.mcp.json`, `.claude/**` (skills, agents, context, hooks, settings), `.githooks/**`, `.github/workflows/claude-*.yml` | an AI-layer branch (`CLAUDE.md` and `.claude/context/**` also on ticket branches as code-facts) |
| **artifact** | `.claude/plans/**`, `docs/{prds,specs,reviews,rca,physics_specs}/**` | the ticket/epic branch it belongs to |
| **product** | everything else: `*/*.m`/`.F`/`.v`/`.F90`, `setup.py`, `Makefile.Forthon`, `src/uedge/`, CI, `doc/` | a ticket branch |
| **record** | `.claude/execution-reports/**`, `.claude/system-reviews/**` | any branch |
| **shared** | `.gitignore` | any branch |

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
| AI layer | `feature/v9-ai-<slug>` (legacy: `v9-agentic`) | `v9-develop` | process + record |
| Jira ticket | `feature/v9-<KEY>-<slug>`, e.g. `feature/v9-AIUE-12-freeze-bbb` (or `bugfix/v9-<KEY>-<slug>`) | `v9-develop`, or the branch of the ticket it depends on (stacked) | product + artifact (+ code-facts) |
| GitHub issue | `bugfix/v9-issue-<N>-<slug>` | `v9-develop` | product + artifact |
| Epic planning | `feature/v9-<EPIC>-planning` | `v9-develop` | the PRD, its review reports, the `docs/specs/` breakdown, the progress log and the close-out record (`docs/specs/<EPIC>-closeout.md`, from `close-epic`) |

Names must match the mandatory patterns in `doc/workflow.md` (`feature/v9-*`, `bugfix/v9-*`). `<slug>` is
kebab case and at most about 40 characters. Putting the Jira key in the branch name makes Jira link the branch,
commits and PR to the ticket automatically.

**One branch per ticket, not per epic.** An epic is the set of its ticket PRs. Use an epic integration branch
(`feature/v9-<EPIC>-integration`) only when tickets really can't land on `v9-develop` one by one. Say so
in the spec breakdown, and target the ticket PRs at it.

**Stacked tickets.** A ticket that depends on an unmerged ticket branches from that ticket's branch, and its PR
targets that branch. After the parent merges, rebase it onto `v9-develop` (`git rebase --onto v9-develop <parent>`).

## Worktrees — one per active ticket

```bash
git fetch origin
git worktree add -b feature/v9-AIUE-12-freeze-bbb ../uedge-wt/AIUE-12 origin/v9-develop
cd ../uedge-wt/AIUE-12
python -m venv .venv && . .venv/bin/activate      # own env: `pip install .` installs compiled modules
pip install . -C "--build-option=--serial"
```

- **Give each worktree its own virtualenv.** Two worktrees that install into the same env overwrite each other's
  `uedge` build, and the tests then run the wrong code.
- The regression worktree `../uedge-pytests` is shared. It holds only tests and reference data.
- Parallel tickets run by subagents use `isolation: "worktree"` (Agent tool) or the explicit worktree above.
- Remove a worktree after its PR merges: `git worktree remove ../uedge-wt/AIUE-12`.

## Improving the AI layer while doing ticket work

Don't fix a skill, agent or hook on a ticket branch, even when the ticket exposed the problem.

1. Note it in the ticket's execution report (`execution-report` → `.claude/execution-reports/`, which is a record and
   allowed anywhere).
2. Run `system-review` on it. Apply its recommendations on a `feature/v9-ai-<slug>` branch in its own PR.
3. If the problem blocks the ticket, merge the AI-layer PR first, then rebase the ticket branch.

## Bootstrap (until the AI layer is on `v9-develop`)

Ticket branches based on `v9-develop` don't have `.claude/` yet. Until the AI-layer branch (`v9-agentic`) is merged:

- Base ticket and planning branches on the AI-layer branch tip, and record that in the PR description.
- After the AI layer merges, `git rebase --onto origin/v9-develop v9-agentic <ticket-branch>` drops the AI commits
  from the ticket's history.
- Prefer merging the AI layer first. Then this section goes away.

## Guard rails on the AI layer changing itself

- **Agents never apply process changes automatically.** `system-review` files them as `ai-layer` Jira issues
  (fallback: `.claude/system-reviews/backlog.md`). They land through a `feature/v9-ai-*` PR that a person reviews.
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
uv run .claude/hooks/change_kind.py --range origin/v9-develop..HEAD   # a whole branch, before opening a PR
uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop   # are the AI layer's code facts still true?
```

Exit 0 means clean, 1 means violations (printed with the offending paths), 2 means the check couldn't run.
