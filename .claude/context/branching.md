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
  page keeps the same record as short `PIV record` Jira comments; a GitHub issue with no Jira ticket gets its RCA
  and its outcome as comments on the issue (`rca`, `implement-fix`). The full working files are disposable.
- **Epic documents** live on Confluence, under the PRD page: the PRD itself (the page is the source; `create-prd`
  keeps a local working copy), `PRD reviews: <EPIC>` (each review round summarised), `Spec: <epic> - Ticket
  Breakdown` (the breakdown, with each ticket's key and page id), `Progress: <EPIC>` (the progress log: dated,
  append-only entries, owner decisions attributed as in `close-epic`), `Ticket plans: <EPIC>` with one page per
  ticket, and `Close-out: <EPIC> - …`. Local working copies (the PRD draft, review reports, the breakdown draft, the
  close-out record and its sources snapshot) go in `.claude/work/<EPIC>/` of the checkout the skill runs in.
- **No planning branch.** An epic no longer has a `feature/v9-<EPIC>-planning` branch: nothing it held is committed
  any more. Existing planning branches are left as they are; `close-epic` may read one as a historical source.
- **Physics specs stay in the repo.** `docs/physics_specs/<feature>.md` is product documentation: the approved spec
  is committed on the ticket branch with the physics change it specifies (`CLAUDE.md` → Hard rules,
  `physics-workflow.md`). Its review reports are working documents like any other.
- **Robustness.** Confluence or Jira being down never blocks code work: the working files and the `ticket-page`
  outbox and sent log (in the worktree's git directory) keep the record until the next flush. **Both are lost when the
  worktree is removed** (`git worktree remove`), so flush the ticket page (`ticket-page <KEY> flush`, and
  `queue --list` empty) before removing a worktree; anything not on the page by then is gone.
- **Enforcement.** `.gitignore` lists every working path, and `change_kind.py` refuses a staged working document on
  any branch, pointing to the ticket page.
- **Tickets started before this rule** may track a plan or reviews on their branch (`.claude/plans/`,
  `docs/reviews/`). Copy the plan to `.claude/work/<KEY>/plan.md` and work on that copy (`ticket-page publish`
  mirrors it); a tracked working document may be deleted in a commit (`git rm`), never changed or added.


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
- Remove a worktree after its PR merges: `git worktree remove ../uedge-wt/AIUE-12`. **Flush first**: the working
  folder `.claude/work/<KEY>/` and the `ticket-page` outbox go with the worktree, so run `ticket-page <KEY> flush`
  and check that nothing is queued (`ticket_page.py queue --repo <worktree> --key <KEY> --list` prints nothing).

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
uv run .claude/hooks/change_kind.py --range origin/v9-develop..HEAD   # a whole branch, before opening a PR
uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop   # are the AI layer's code facts still true?
```

Exit 0 means clean, 1 means violations (printed with the offending paths), 2 means the check couldn't run.
