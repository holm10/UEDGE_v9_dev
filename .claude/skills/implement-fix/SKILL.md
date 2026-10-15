---
name: implement-fix
description: Implements a UEDGE bug fix for a GitHub issue from its RCA document, verifies it on the reproducing case, and runs the validate gate. Use after an RCA document exists and you are ready to fix the issue.
argument-hint: [github-issue-id]
allowed-tools: Read, Write, Edit, Grep, Glob, Bash(git:*), Bash(gh:*), Bash(pip:*), Bash(python:*), Bash(python3:*), Bash(pytest:*), Bash(make:*)
---

# Implement Fix: GitHub Issue #$ARGUMENTS

## Prerequisites

- RCA document at `docs/rca/issue-$ARGUMENTS.md` (create it with the `rca` skill first if missing).
- On the issue's own branch `bugfix/v9-issue-<N>-<slug>` and worktree (created by `rca`; create it now as in
  `.claude/context/branching.md` if missing), never on `v9-develop` or an AI-layer branch.
- Optional: `gh` authenticated. Issues may live upstream — use `gh issue view $ARGUMENTS -R LLNL/UEDGE` if the
  issue is not on `origin`.

## 1. Read and understand

- Read the RCA in full: root cause, fix strategy, files, reproduction, validation.
- Read `CLAUDE.md` and the `.claude/context/` modules for the files involved (`mppl-fortran.md` for `.m`,
  `variables-forthon.md` for `.v`, `openmp-jacobian.md` for anything in the `pandf` tree or `ppp/`).
- Decide whether the fix **changes default results**. A bug fix in physics/numerics often does: if so, the
  moved cases are expected but must be listed and explained (`CLAUDE.md` → Hard rules). A fix in a refactor
  path or Python/build code should leave results unchanged.

## 2. Reproduce first

Follow the RCA reproduction on the current build and confirm the failure (error, wrong value, crash,
serial/parallel mismatch). Record the observed output — you will compare against it.

## 2b. Plan review (high-risk fixes)

If the fix touches the `pandf` tree, `ppp/`, the Jacobian or a `.v` file, run the **Adversarial review loop** in
`.claude/skills/end-to-end-feature/SKILL.md` with `stage: plan` on the intended change (the RCA's fix section, or a
short plan) **before writing code**.

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

## 4b. AI-layer facts

Run `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`. If the fix moved or renamed code that `CLAUDE.md` or `.claude/context/` cite, or changed a default
listed in `.claude/context/physics-models.md`, update those facts (as in `execute` step 3b). Commit them with the
trailer `AI-layer: code-facts`.

## 4c. Adversarial review

Run the **Adversarial review loop** in `.claude/skills/end-to-end-feature/SKILL.md` with `stage: implementation`. The reference is the RCA document (root cause, the fix it proposes, the
reproduction) and, for a Jira ticket, its acceptance criteria. The fix is done only after APPROVE on the final
diff.

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

## 6. Process lessons

After the fix is approved and committed, run `execution-report` and then `system-review`. Its recommendations become `ai-layer`
issues (see `system-review`), never edits on this branch.

## Notes

- If the RCA turns out to be wrong, update it with the new findings before changing more code.
- Extra problems found along the way go into separate issues/RCAs, not this fix.
