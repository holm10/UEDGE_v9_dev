---
name: execute
description: Executes an implementation plan task-by-task with validation at every step. Use when you have a completed feature plan and want to implement it in one pass.
argument-hint: [path-to-plan]
---

# Execute: Implement from Plan

## Plan to Execute

Read plan file: `$ARGUMENTS`

## Execution Instructions

### 1. Read and Understand

- Check the branch first: you must be on the plan's **Branch / worktree** (`git branch --show-current`). If you
  aren't, `cd` into that worktree. If it doesn't exist, create it as in `plan-feature` Phase 0b. Never execute on a protected
  or AI-layer branch (`.claude/context/branching.md`)
- Read the ENTIRE plan carefully
- Read `CLAUDE.md` and every `.claude/context/` module the plan references
- Note the plan's **type** (physics / refactor / numerics / bug fix / Python-build) and whether default results
  are expected to change
- Understand all tasks and their dependencies
- Note the validation commands to run
- Review the testing strategy

### 2. Execute Tasks in Order

For EACH task in "Step by Step Tasks":

#### a. Navigate to the task
- Identify the file and action required
- Read existing related files if modifying

#### b. Implement the task
- Follow the detailed specifications exactly
- Maintain consistency with existing code patterns
- Edit `.m`/`.v`/`.F90`/`.py` sources only — never the generated `.F` files
- New variables: units, default and `#` description in the `.v` file; `+threadprivate` if written inside `pandf`
- Physics plans implement the approved spec exactly; do not alter equations or coefficients
- If the work shows that a skill, agent or hook should change, **don't** change it here. Note it for the execution
  report (`branching.md` → "Improving the AI layer while doing ticket work"). Updating `CLAUDE.md`/context
  facts that this change makes untrue is allowed, in its own commit with the trailer `AI-layer: code-facts`

#### c. Verify as you go
- After each Fortran/`.v` change, rebuild (`pip install . -C "--build-option=--serial"`) and fix the `.m`
  source for any error reported in the generated `.F`
- Run the task's VALIDATE command before moving on

### 3. Implement Testing Strategy

After completing implementation tasks:

- Run the case-level checks the plan lists (input decks, `bbb.exmain()` convergence, `checkbal()`)
- Run the OpenMP serial-vs-parallel check if the plan calls for it
- Add any test or example artefacts the plan specifies (the regression suite itself lives on the `pytests`
  branch — do not invent a new test location)

### 3b. Update the AI-layer facts

Before validating, bring the AI layer's description of the code up to date (`.claude/context/branching.md`):

1. Work through the plan's **AI-layer facts affected** list.
2. Run `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`. Apply `--fix` for moved line numbers. Rewrite stale claims after re-reading the code. Lock with
   `--update` only once each claim has been checked.
3. New or changed model, switch or default → update the row in `.claude/context/physics-models.md`. New file,
   package or build step → update `.claude/context/architecture.md` (and `CLAUDE.md` if a rule or gotcha changed).
4. Commit these separately with the trailer `AI-layer: code-facts`. Only `CLAUDE.md` and `.claude/context/` may
   change this way. Skills, agents and hooks never change on a ticket branch.

### 4. Run Validation Commands

Run the `validate` skill with the suites the plan names, then any feature-specific commands from the plan:

```bash
# Run each command exactly as specified in plan
```

If any command fails:
- Fix the issue (never loosen tolerances or skip suites)
- Re-run the command
- Continue only when it passes

### 5. Final Verification

Before completing:

- ✅ All tasks from plan completed
- ✅ Validate gate green (refactor: suites unchanged; physics: only documented cases moved)
- ✅ All validation commands pass
- ✅ Code follows project conventions
- ✅ Documentation added/updated as needed
- ✅ AI-layer facts updated and the drift check is clean (step 3b)

### 6. Adversarial review

The work is not done until a fresh `uedge-reviewer` has approved it: run the **Adversarial review loop** in `.claude/skills/end-to-end-feature/SKILL.md` with `stage: implementation`
(`end-to-end-feature` does this as its Step 3b). If you can't spawn a reviewer, say so in the report and hand the
caller the ready-to-use reviewer prompt that loop describes.

## Output Report

Provide summary:

### Completed Tasks
- List of all tasks completed
- Files created (with paths)
- Files modified (with paths)

### Checks Run
- Case-level checks and results (convergence, balances)
- OpenMP check result (if applicable)
- Default-results status: unchanged / changed as documented (list moved cases)

### Validation Results
```bash
# Output from each validation command
```

### Ready for Commit
- Confirm all changes are complete
- Confirm all validations pass
- Ready for the `commit` skill (and for the adversarial review, step 6, if it hasn't run)

## Notes

- If you encounter issues not addressed in the plan, document them
- If you need to deviate from the plan, explain why
- If tests fail, fix implementation until they pass
- Don't skip validation steps
