---
name: plan-feature
description: Creates a context-rich, one-pass implementation plan for a UEDGE change (refactor, numerics, OpenMP, build, Python layer, or wiring of an approved physics spec) through codebase analysis and research. Use before writing code for any non-trivial change.
argument-hint: [feature-description] [--no-tracker] [--dry-run]
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

## Phase 0b: Branch and worktree

Each ticket gets its own branch and worktree (`.claude/context/branching.md`). Do this before writing anything:

1. Name it. Use `feature/v9-<KEY>-<slug>` for a Jira ticket (take the key and the branch from the ticket's `Branch:`
   line in `docs/specs/` if `spec` wrote one), `bugfix/v9-<KEY>-<slug>` for a Jira bug,
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
   (`python -m venv .venv && . .venv/bin/activate`). Write the plan inside the worktree.
4. Never plan product work on an AI-layer branch, and never plan AI-layer process changes on a ticket branch.

## Phase 1: Understand the request

- Core problem, who benefits (users running cases, developers, CI), complexity (Low/Medium/High).
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

Save to `.claude/plans/<kebab-case-name>.md` (create the directory if needed), using this template:

```markdown
# Feature: <name>

Validate the patterns and file references below before implementing.

## Summary
**Type**: Physics (spec: docs/physics_specs/<x>.md) | Refactor | Numerics/Parallel | Bug fix | Python/Build
**Complexity**: Low/Medium/High
**Default results**: Unchanged | Changed — <which defaults, why, which reference cases move>
**Packages / files**: <list>
**Branch / worktree**: <branch> @ <worktree path> (base: <base>)
**Ticket page**: Confluence page <id> (<url>) | none (no epic PRD page); PIV record in Jira comments on <KEY> | none (no Jira key)

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

- Another developer could execute it with no extra context; every file reference has line numbers.
- Every task has a runnable validation step.
- No generic placeholders left; no physics invented in a non-physics plan.

## Phase 6: Commit the plan and publish the ticket record

1. Commit the plan on the ticket branch (it is an artifact path): `git add .claude/plans/<file>.md`, then a commit
   such as "Adds the <KEY> plan: <short description>".
2. For a Jira ticket, run the `ticket-page` skill: `<KEY> publish status Planning` (`Plan review` if the review below
   is required), passing on `--dry-run` or `--no-tracker` if this skill got them. Under an epic with a PRD page it
   creates or updates `Plan: <KEY> - <summary>` under `Ticket plans: <EPIC>` and links it from the ticket; without
   one it posts a short plan comment on the ticket. It then fills the plan's `**Ticket page**` line and commits that.
   A failure there is noted in the report and retried by the next step; it never stops planning.

## Adversarial plan review

If the plan touches the `pandf` tree, `ppp/`, Jacobian or preconditioner code, a `.v` file, or the build
(`setup.py`, `Makefile.Forthon`), run the **Adversarial review loop** in `.claude/skills/end-to-end-feature/SKILL.md` with `stage: plan` before any code is written.
The loop logs each verdict to the ticket record; after a revision, commit the plan and run `ticket-page <KEY> publish`
again with `log Progress "Plan revised (<sha>): <what changed>"`.

## Report

Plan path, type and complexity, whether defaults change, key risks, the ticket record (page URL, Jira comment, or
why it was skipped), and a confidence score (#/10) for one-pass execution.
