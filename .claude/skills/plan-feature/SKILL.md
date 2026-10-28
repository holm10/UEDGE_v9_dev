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
from what the change touches (L: the `pandf` tree, Jacobian/preconditioner, `ppp/`, `.v`, the build, physics; at
least M: any other Fortran source (`.m`, `.F90`, hand-written `.f`), whose implementation review runs on Opus; S: investigation, characterisation,
doc/tooling, small fixes elsewhere; M: the rest). Check the files the plan modifies against `HIGH_RISK` (L) and
`FORTRAN` (at least M) in `.claude/hooks/change_kind.py`, so the review gate doesn't re-tier the ticket after the
code is written. The tier sets the plan's budget:
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
   The path is relative to the main checkout (the first line of `git worktree list`): run the command from there, or
   give the absolute path. From inside a ticket worktree a bare `../uedge-wt` nests the new worktree under
   `uedge-wt/uedge-wt/` (AIUE-217).
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
   `mppl-fortran.md`, `variables-forthon.md`, `openmp-jacobian.md`, `python-layer.md`, `testing.md`,
   `uedge-gotchas.md` as relevant).
2. Locate the code: the `pandf` call chain (`bbb/pandf.m:513`), the equation file
   (`bbb/pandf_<plasma|gas>_<eq>.m`), boundary code (`bbb/pandf_boundary.m`), setup/allocation (`bbb/odesetup.m`),
   and the `.v` groups involved (`Use(Group)` sites).
3. Find the closest existing pattern to mirror (a similar term, switch, or BC) and record it with `file:line`.
4. Check RHS/Jacobian implications: loop ranges (`initialize_ranges`), stencil width, `+threadprivate` needs,
   X-point/cut handling (`ixm1/ixp1`), OMP chunk padding.
5. Check build implications: new `.m` files (both `Makefile.Forthon` lists + `Package`), new `.v` routines,
   `.h` parameter mirrors, save/restore lists (`src/uedge/hdf5.py`).
6. Recent history in the area: `git log --oneline -15 -- <paths>`.
   Then the parallel work on the same files: the open PRs (`gh pr list --repo holm10/UEDGE_v9_dev --state open
   --limit 100 --json number,headRefName,files`; the fork, since plain `gh` resolves to upstream LLNL/UEDGE), the
   other active ticket worktrees (`git worktree list`; `git diff --name-only origin/v9-develop...<branch>`), and the
   Files touched of the other tickets in the same wave (their breakdown entries or plans). A sibling that has no
   commits or PR yet is not evidence of no overlap: its breakdown entry is. Without `gh`, use the worktrees and the
   breakdown, and say so in Notes. For each file this plan modifies that another ticket also touches, record the
   expected conflict and the merge order in Notes (the second to merge rebases and re-runs its tests).
   A ticket that publishes a `yldot-data-vN` release through `regenerate-references.yml` doesn't reserve a number:
   its N is the next free one when the owner approves the publish job (`release_data.py --renumber`; in AIUE-98's A4
   the second dispatch got v11), and it records the N it got on its ticket page. A hand publish with
   `release_data.py` (no `--renumber`) still reserves N = highest + 1 as a Findings and decisions entry once the owner
   agrees (AIUE-161 planned v8 while AIUE-174 held v7 with no manifests yet). Planning reads the in-flight tickets'
   pages for both (`testing.md` → Tools, `release_data.py`; AIUE-207).
7. **Probe runtime claims.** Check every claim the plan makes about run-time behaviour (Forthon, UEDGE, the compiler,
   the build) with a short probe before writing it down: in the worktree's venv if it has one, else in a base venv
   (name its commit). Examples: what reading an unallocated array does, whether `allocate()` keeps values, which
   assignment types Forthon accepts, what a link line pulls in. Cite the probe in the plan (the command and the output
   line that settles it). When the conclusion depends on what an input value means (a solver option set to 0, a flag
   that selects a path), cite the source line that defines that meaning next to the output: an output code alone
   (`iterm`, a return flag) doesn't show which path ran (AIUE-134: `itermx=0` means 200 iterations,
   `svr/nksol.m:973`). A claim not probed, including behaviour that only the ticket's own change creates, is marked
   *assumed*, and the task that relies on it checks it first. For a build change, plan a link check on every
   platform the change claims (the link line, plus `nm -u` or an import), and give every runtime gate a way to fail
   (a count, not a file's existence). The same holds for a repo tool used as a VALIDATE step: probe what that mode
   actually verifies (run it once on the current tree, or cite the contract in its docstring), else mark it
   *assumed* (AIUE-91: `fetch_data.py --check` verifies only cached files, not the files at their manifest paths).
   An estimate that decides a gate (a size cap, a budget, a runtime) is probed with the code that will produce it:
   the real writer and serializer on each case the gate applies to, from that case's own output (a sibling's pattern
   is *assumed*), and the plan states the margin to the cap: a margin under about 10 % before a run of an hour or
   more is an owner question at planning. An estimate from a hand-built subset is *assumed* (AIUE-94: a subset
   put the manifests at 3 MB; the real `manifest.dumps` wrote 8.9 MB. AIUE-99, AIUE-196: d_c's pattern put
   imp7 at 11.15 of 12 MB; it wrote 12.06 MB after a 2 h sweep). A runtime estimate for a CI job names the runner CPU it was measured
   on, and a job limit is checked against the slowest model the job accepts (AIUE-214: the fastest runner seen set
   two wrong ETAs; `testing.md` → `regenerate-references.yml`).
   A claim about what a check reports on a fault (which blocks fire, what it localizes to, the message text) is
   probed with the fault applied, against the references the suite really uses (another platform's, if they are),
   even when a build takes minutes (AIUE-89: `rscalf` couples a continuity fault into the up/te/ti rows, and the
   localizer fired on macOS-vs-Linux round-off).
   When the change touches code that a repo tool or test drives through stubs, read how it calls that code and run a
   prototype of the change through it before writing the per-task VALIDATE lines (AIUE-181: `build_flags.py` runs
   `uedgeBuild.run` with a fake `self` and a fake `FCompiler`, so task 1's check could only pass after task 2). A task
   whose check needs a later task is a plan defect: merge the tasks or move the check.
   Specific probes:
   - **A command the change writes into a skill, agent or doc is probed as written:** the same arguments, with only
     the placeholders filled, run from the directory the text implies. For each path argument, say what it is
     relative to (AIUE-102, AIUE-194: the probe used an absolute `--out`, the text a relative one, and the text's
     form gave ERROR in every group).
   - **A rule that selects or partitions tests** (a marker, a `-k`, a conftest option) is probed itself: a throwaway
     conftest plugin applied to `--collect-only` on the real suite, with the per-group counts, not an approximation
     from node ids (AIUE-103, AIUE-203).
   - **A new `workflow_dispatch` workflow** can be dispatched only once its file is on the default branch. Plan that
     step (a placeholder PR with the same inputs and no permissions, or merge first and test after), and probe `gh
     workflow run <file> --ref <branch>` during planning (AIUE-98, AIUE-205).
   - **Platform- or CPU-dependent results** (round-off between machines, emulated vs native): first list the math
     symbols the build links (`nm -u` on the built objects, or `nm` of the extension), separating scalar libm (`exp`,
     `log`, …) from glibc's vector library libmvec (`_ZGV*`). Vectorized calls do not go through scalar libm, so a
     probe of `libm.so.6` alone can return a false negative (AIUE-210, AIUE-215).
8. Use `research-agent` instances in parallel only when the user has asked for subagents.

## Phase 3: External research (when needed)

Numerical methods, Forthon/gfortran/OpenMP behaviour, or library docs — with section-anchored URLs. Physics
literature belongs in the physics spec, not here.

## Phase 4: Think it through

- Order of operations and dependencies between files.
- What could break: guard cells, multi-species indexing, double-null/snowflake topologies, `nxpt=2`,
  slab geometry, time-dependent vs steady-state (`dtreal`), MC-neutral paths (`ismcnon`).
- Solver impact: differentiability, Jacobian sparsity, preconditioner.
- Backward compatibility of inputs and save files.
- **Inputs a later ticket regenerates from.** If a later ticket will rebuild this ticket's output from its raw data
  (measurement collections, build records; AIUE-87's `tolerances.toml`, which AIUE-92 rewrites), the plan names where
  that data is kept after the worktree goes (`branching.md` → Working documents) and ends with a task that puts it
  there.
- **Generated data that records its own commit** (provenance, a build id): plan the commit order (the tool, then a
  data-only commit), check that the plan's own tests pass at every commit in that order, and plan one regeneration
  after every later change to the generator and after every rebase, since the recorded commit must stay in the PR's
  history. Note the cost of one regeneration (AIUE-88 regenerated its manifests twice, unplanned).
  Budget one targeted regeneration round (`--only` or the tool's equivalent) after the authoritative-build validation
  and the owner's review of the classified lists, and prototype, at planning, every generator mode the plan may need
  on each store kind it will write (AIUE-99, AIUE-197: `--only` on a sketch store always refused; -O0 found three
  switches to exclude after a 2 h sweep). A rebase that leaves the generator's inputs byte-identical (`git diff <gen-commit>
  <rebased> -- <tool tree>` empty) needs no regeneration if the owner agrees; keep the generating commit as a local
  tag until merge. A check that reproduces a data release reads the release's history first (`git log` of its
  manifests, and the releases they were regenerated from): an `--only` release copies every other entry, and its
  `reason` text, from the installed release, so the manifest's provenance commit is where only the regenerated
  entries were computed (AIUE-98, AIUE-206).
- **Outcomes cited from another run.** When a gate's expected result comes from another ticket's run (a matrix, a
  measurement, a report), copy that run's entries into the plan, not its summary line, so execute can tell a known
  entry from a new one (AIUE-188).
- **Report-only paths.** When a test reports a condition instead of failing (a warning, a print), name every consumer
  of that test (CI tiers, the mutation cross-check, tools that run it in a child) and say whether each one treats the
  report as a pass or a failure (AIUE-188).
- **CI gating.** A change that un-gates or re-gates CI jobs (removes a job they `needs`, changes an `if:`) checks
  their run history (`gh run list --workflow <file>`) and states their expected first run; jobs that have never run
  get an owner decision (AIUE-103, AIUE-203).
- **Samples and populations.** When an acceptance criterion confirms a property on a sample (the criterion's ≥ N
  cases) and checking the whole population would take under about 10 minutes, or under about twice the sample's run,
  the plan checks the population too; otherwise it records that estimate in one line. A sample
  pass alone is reported as a sample pass, not as the property (AIUE-94: 26 of ~330 variants per family passed the
  tolerance check; the full replay, minutes per family, found failures).
- **Owner questions cover the whole class.** When a rule needs exceptions that are the owner's to decide (the meaning
  of an index, term, flag or layout; an epic rule such as AIUE-9's decision 23), list every member of the class, not
  only the examples the ticket or PRD names, and ask once, during planning. Build the list with the same tool or query
  the ticket implements, e.g. every integer input whose name or `.v` comment marks an index, a cell range or an
  enumerated selector. Unattended (no owner to ask), put the whole list in the plan's Notes as one open owner
  decision with the proposed answer for each member, and stop there as `end-to-end-feature` does for owner decisions.

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
- Regression suites include the yldot suite (`validate` step 3b), and a new `+input` switch its variant (`physics-workflow.md`).
- OpenMP check (the AIUE-8 test flow, `validate` step 4) if the `pandf` tree or threadprivate vars change.
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
- [ ] OpenMP test flow passes (if applicable; `validate` step 4)
- [ ] AI-layer facts updated; drift check clean (`check_context_refs.py`)
- [ ] <feature-specific criteria>

## Notes
<Design decisions, trade-offs, open questions.>
```

## Quality bar

- Within the tier's line budget; no section padded to look complete.
- Another developer could execute it with no extra context; every file reference has line numbers.
- Every task has a runnable validation step.
- Every run-time or build claim cites its probe or is marked *assumed* (Phase 2, step 7).
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
3. A Jira ticket still in To Do moves to In Progress (`getTransitionsForJiraIssue`, then `transitionJiraIssue`; not
   with `--no-tracker` or `--tracker-dry-run`). Done follows the merge (`branching.md` → worktree removal; AIUE-201).

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
