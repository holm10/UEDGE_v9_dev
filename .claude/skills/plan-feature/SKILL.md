---
name: plan-feature
description: Creates a context-rich, one-pass implementation plan for a UEDGE change (refactor, numerics, OpenMP, build, Python layer, or wiring of an approved physics spec) through codebase analysis and research. Use before writing code for any non-trivial change.
argument-hint: [feature-description] [--no-tracker] [--tracker-dry-run]
---

# Plan a new task

## Feature: $ARGUMENTS

## Mission

Turn the request into an implementation plan that an execution agent can complete in one pass. **No code is
written in this phase.** The plan must carry everything needed: files and routines, patterns with `file:line`,
gotchas, and executable validation.

## Phase 0: Route the request

Classify first — it decides the workflow and how the defaults rule applies (`CLAUDE.md` → Hard rules):

| Type | Examples | Workflow |
|---|---|---|
| **New physics** | new transport term, atomic/molecular process, BC, source, closure, neutral/impurity model | **Stop.** Physics goes through `uedge-physics` → `uedge-reviewer` → `uedge-implementer` (`.claude/context/physics-workflow.md`). Only plan here if an **approved** spec exists in `docs/physics_specs/`; then the plan implements that spec and must not change its physics. |
| **Refactor / restructure** | splitting routines, v9 reorganisation, renaming, moving code between files/packages | Plan here. Default results must be unchanged to round-off. |
| **Numerics / parallel** | OpenMP chunking, Jacobian, preconditioner, solver options | Plan here. Defaults unchanged unless the change is an intended, documented numerics change. |
| **Bug fix** | wrong results, crash, wrong BC indexing | Prefer `rca` → `implement-fix`; plan here if large. |
| **Python / build / tooling** | `src/uedge/*.py`, `setup.py`, `Makefile.Forthon`, CI | Plan here. |

If the type is unclear, ask the user before continuing.

**Tier** (`.claude/context/process-tiers.md`): take it from the ticket's breakdown entry (`Tier:`), else assign it now
from what the change touches (L: the `pandf` tree, Jacobian/preconditioner, `ppp/`, `.v`, the build, physics; S:
investigation, characterisation, doc/tooling, small fixes elsewhere; M: the rest). The tier sets the plan's budget:
**S ≤150 lines, M ≤300, L ≤300** (up to 500 with a one-line reason in Notes). Omit template sections that don't apply
("n/a") rather than filling them.

## Phase 0b: Branch and worktree

Each ticket gets its own branch and worktree (`.claude/context/branching.md`). Do this before writing anything:

1. Name it. Use `feature/v9-<KEY>-<slug>` for a Jira ticket (take the key and the branch from the ticket's `Branch:`
   line in its breakdown entry, i.e. the Ticket section of its page or the epic's breakdown page, if `spec` wrote one),
   `bugfix/v9-<KEY>-<slug>` for a Jira bug,
   `bugfix/v9-issue-<N>-<slug>` for a GitHub issue, and `feature/v9-<slug>` when there is no ticket.
   **If the request changes the AI layer itself** (skills, agents, hooks, settings), use `feature/v9-ai-<slug>`
   and note that the plan is process work.
2. If the current branch already is that branch, continue. Otherwise create a worktree from the base: `origin/v9-develop`, or
   the parent ticket's branch for a stacked ticket. Until the AI layer is merged, use the AI-layer tip (see Bootstrap in
   `branching.md`).
   ```bash
   git fetch origin
   git worktree add -b <branch> ../uedge-wt/<KEY-or-slug> <base>
   ```
3. Tell the user the worktree path and that it needs its own venv before building
   (`python -m venv .venv && . .venv/bin/activate`). Write the plan in the worktree's working folder
   `.claude/work/<KEY>/` (gitignored; `<slug>` for work without a ticket).
4. Never plan product work on an AI-layer branch, and never plan AI-layer process changes on a ticket branch.

## Phase 1: Understand the request

- Core problem, who benefits (users running cases, developers, CI), complexity (Low/Medium/High). For a Jira ticket,
  the scope and acceptance criteria as filed are in the Ticket section of its page (from the epic's breakdown page on
  Confluence) and its Jira description; `prime` reads the page.
- Affected packages and equations (`isnion`, `isupon`, `isteon`, `istion`, `isngon`, `istgon`, `isphion`).
- Whether default results are expected to change, and if so which cases.

## Phase 2: Codebase intelligence

1. Read `CLAUDE.md` and the matching `.claude/context/` modules (`architecture.md` always;
   `mppl-fortran.md`, `variables-forthon.md`, `openmp-jacobian.md`, `python-layer.md`, `testing.md` as relevant).
2. Locate the code: the `pandf` call chain (`bbb/pandf.m:513`), the equation file
   (`bbb/pandf_<plasma|gas>_<eq>.m`), boundary code (`bbb/pandf_boundary.m`), setup/allocation (`bbb/odesetup.m`),
   and the `.v` groups involved (`Use(Group)` sites).
3. Find the closest existing pattern to mirror (a similar term, switch, or BC) and record it with `file:line`.
4. Check RHS/Jacobian implications: loop ranges (`initialize_ranges`), stencil width, `+threadprivate` needs,
   X-point/cut handling (`ixm1/ixp1`), OMP chunk padding.
5. Check build implications: new `.m` files (both `Makefile.Forthon` lists + `Package`), new `.v` routines,
   `.h` parameter mirrors, save/restore lists (`src/uedge/hdf5.py`).
6. Recent history in the area: `git log --oneline -15 -- <paths>`.
7. Use `research-agent` instances in parallel only when the user has asked for subagents.

## Phase 3: External research (when needed)

Numerical methods, Forthon/gfortran/OpenMP behaviour, or library docs — with section-anchored URLs. Physics
literature belongs in the physics spec, not here.

## Phase 4: Think it through

- Order of operations and dependencies between files.
- What could break: guard cells, multi-species indexing, double-null/snowflake topologies, `nxpt=2`,
  slab geometry, time-dependent vs steady-state (`dtreal`), MC-neutral paths (`ismcnon`).
- Solver impact: differentiability, Jacobian sparsity, preconditioner.
- Backward compatibility of inputs and save files.

## Phase 5: Write the plan

Save to `.claude/work/<KEY>/plan.md` in the worktree (create the directory if needed; `<slug>` instead of `<KEY>`
without a ticket), using the template below. It is a **working document**: gitignored, never committed
(`.claude/context/branching.md`). For a Jira ticket its lasting copy is the Plan section of the ticket page (Phase
6); without a ticket record it lives only in this worktree, so whatever must outlive it goes in the PR description.

```markdown
# Feature: <name>

Validate the patterns and file references below before implementing.

## Summary
**Type**: Physics (spec: docs/physics_specs/<x>.md) | Refactor | Numerics/Parallel | Bug fix | Python/Build
**Tier**: S | M | L (why) · **Complexity**: Low/Medium/High
**Default results**: Unchanged | Changed — <which defaults, why, which reference cases move>
**Packages / files**: <list>
**Branch / worktree**: <branch> @ <worktree path> (base: <base>)
**Jira**: <KEY> | none

## Problem and solution
<What is wrong or missing; how this change addresses it.>

## Context references — read before implementing
- `bbb/<file>.m:<lines>` — why
- `bbb/bbb.v:<lines>` (group `<Group>`) — why
- `.claude/context/<module>.md` — which section applies

## Patterns to mirror
<Actual snippets from the code with file:line: the analogous term/switch, its .v declaration, the loop/range
idiom, error handling via xerrab/remark.>

## Step-by-step tasks
Execute top to bottom; each task is atomic.

### {CREATE|UPDATE|ADD|REMOVE|REFACTOR|MIRROR} <file>
- **IMPLEMENT**: <specific change>
- **PATTERN**: <file:line>
- **GOTCHA**: <threadprivate / ranges / MPPL hazard / units in J / registration>
- **VALIDATE**: `<command>` (e.g. build, a python one-liner checking a new variable)

## Testing strategy
- Regression suites to run and expected outcome (unchanged / named cases move).
- Case-level checks: a specific input deck, `bbb.exmain()` convergence, `checkbal()` balances.
- OpenMP check (`ppp.CheckPandf1` / `CheckJac`) if the `pandf` tree or threadprivate vars change.
- Edge cases: <topologies, species counts, switches>.

## AI-layer facts affected
<Every fact in `CLAUDE.md`, `.claude/context/*.md` (incl. `physics-models.md`, `architecture.md`) that this change
makes untrue or incomplete: moved routines, new or renamed files, new switches/models, changed build steps,
changed defaults. Find candidates with `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`
after a dry run, or by grepping the AI layer for the files and routines you touch. Write "none" only after
checking. Each entry becomes a final task with the trailer `AI-layer: code-facts`.>

## Validation commands
Run the `validate` skill (suites: <list>; `--omp` if applicable), plus any feature-specific commands.

## Acceptance criteria
- [ ] Builds without new warnings in touched files
- [ ] Refactor: all suites unchanged · Physics: only the documented cases move
- [ ] New variables visible from Python with units/docs
- [ ] OpenMP serial-vs-parallel identical (if applicable)
- [ ] AI-layer facts updated; drift check clean (`check_context_refs.py`)
- [ ] <feature-specific criteria>

## Notes
<Design decisions, trade-offs, open questions.>
```

## Quality bar

- Within the tier's line budget; no section padded to look complete.
- Another developer could execute it with no extra context; every file reference has line numbers.
- Every task has a runnable validation step.
- No generic placeholders left; no physics invented in a non-physics plan.

## Phase 6: Publish the plan to the ticket record (no commit)

1. **Don't commit the plan.** It stays in `.claude/work/<KEY>/` (gitignored; `change_kind.py` refuses it on every
   branch). Nothing is committed in this phase.
2. For a Jira ticket, run the `ticket-page` skill: `<KEY> status Planning` (`Plan review` if the review below is
   required), then `<KEY> publish` (it mirrors `.claude/work/<KEY>/plan.md`). Pass on `--no-tracker` (skip the
   record) or `--tracker-dry-run` (as `--dry-run`: show the record without writing it; the plan is still written).
   Under an epic with a PRD page it fills **the ticket's existing page**, `Plan: <KEY> - <summary>` under `Ticket
   plans: <EPIC>`, which `spec` created when it filed the ticket: it finds it from the worktree's state file, the
   ticket's `Ticket page:` link comment, or the title search under the container (`title ~ "Plan: <KEY>"` filtered on
   the `Plan: <KEY> - ` prefix), and creates it (the same skeleton `spec` makes) only when `find` concludes there is
   none, never a second one. It records the page id in its state file and mirrors the plan into the page's Plan
   section, cited by publish date and sha256; the Ticket section and any earlier entries stay. Without an epic PRD
   page it posts a short `PIV record: plan` comment instead. A failure there is noted in the report and retried at
   the next flush (the plan and the queued entries stay local until then); it never stops planning.

## Adversarial plan review (L tier only)

If the plan touches the `pandf` tree, `ppp/`, Jacobian or preconditioner code, a `.v` file, or the build
(`setup.py`, `Makefile.Forthon`), run the **Adversarial review loop** in `.claude/skills/end-to-end-feature/SKILL.md` with `stage: plan` before any code is written.
Every other plan (S, and M outside those areas) skips this review: it is published and executed.
The loop records each round on the ticket record. A revision is published, not committed: `ticket-page <KEY> log
Progress "Plan revised: <what changed>"`, then `ticket-page <KEY> publish` (the page records the new date and
sha256), which is that round's flush.

## Report

Plan path (local working copy, not committed), type, tier, length in lines and complexity, whether defaults change, key risks, the ticket
record (page URL, Jira comment, or why it was skipped), and a confidence score (#/10) for one-pass execution.
