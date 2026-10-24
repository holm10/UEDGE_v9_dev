---
name: code-review
description: Performs a technical code review of changed UEDGE files (MPPL Fortran, .v variable files, OpenMP/Jacobian code, Python layer, build files) for real bugs and rule violations, then writes a report. Use before committing, and in CI on pull requests.
---

# Code Review

Review recently changed files for **real bugs and rule violations**, not style preferences.

## Load the standards first

- `CLAUDE.md` (naming, core patterns, hard rules, gotchas).
- The `.claude/context/` modules that match what changed:
  `.m` → `mppl-fortran.md`; `.v` → `variables-forthon.md`; `bbb/pandf*`, `convert.m`, `ppp/` →
  `openmp-jacobian.md`; `src/uedge/` → `python-layer.md`; physics → `physics-workflow.md`; code that runs cases or
  reads states (`tests/`, `src/uedge/`, tools) → `uedge-gotchas.md`; `tests/` → `testing.md`.

## Gather the change

Locally:

```bash
git status
git diff HEAD --stat
git diff HEAD
git ls-files --others --exclude-standard
```

On a PR, diff against the base branch instead (`git diff origin/<base>...HEAD`). List the yldot suite's changed
files on their own (`git diff --name-only origin/<base>...HEAD -- tests/yldot/`): the defaults rule (5) needs them.
Read every changed `.m`/`.F90`/`.py` file **in full** around the changed routines, not just the hunks.
Classify the change as **refactor** or **physics** (from the PR description, plan, or spec) — it decides how
the defaults rule applies.

## Checklist

### 1. Correctness (Fortran)
- Loop bounds and guard cells (`0:nx+1`, `0:ny+1`); interior vs boundary cells.
- Neighbours via `ixm1(ix,iy)` / `ixp1(ix,iy)`, never `ix±1` (cuts, X-points).
- Staggered quantities: cell-centre vs x-face/y-face indices; `ifld`/`igsp` ranges (`nisp`, `nusp`, `ngsp`).
- Integer division, int↔real mixing (`-Wconversion`), uninitialised locals, division by zero / negative
  densities or temperatures.
- Units: temperatures are stored in **J** (`te`, `ti`, `tg`); `ev` converts.

### 2. Residual, Jacobian, OpenMP (anything in the `pandf` call tree)
- Every module variable **assigned** during RHS evaluation is `+threadprivate` in its `.v` file.
- New loops use the `Selec` ranges (`i1..i8`, `j1..j8`) from `initialize_ranges`, not full-grid loops.
- Stencil width unchanged, or the padding / `xlinc`/`xrinc`/`yinc` updated to match.
- No `save`d locals; no accumulation into module arrays across calls (see `psorcxg` zeroing in `ppp`).
- Non-smooth functions of solution variables (`if` on `te`, `max/min`, `abs`) flagged — they hurt Newton
  convergence.

### 3. MPPL conversion hazards (`setup.py` `M2F` rules)
- `#` inside strings/formats (becomes `!`); identifiers containing `float`, `break`, `while (`.
- New `.m` file registered in **both** lists of `Makefile.Forthon` and the package `Package` file.
- New `.f`/`.c` files force-added (gitignored patterns). No edits to generated `.F` files.

### 4. Variables and interfaces (`.v`)
- Units `[...]`, default `/.../`, `#` description on every new variable; `+input` on user switches.
- Group placement matches the `Use(Group)` sites; dynamic `_real` arrays allocated via `gchange`.
- `{}` parameters mirrored in `<pkg>.h`. Restart/save-relevant variables added to `src/uedge/hdf5.py`.

### 5. Defaults rule
- **Refactor:** any change in default results is a bug (CRITICAL).
- **Physics:** default changes must be intended and documented (which defaults, why, which cases move).
  New models/terms otherwise default off (`is*on = 0`, `cf* = 0.`).
- **yldot reference data.** In a refactor, a change to `tests/yldot/references/*.manifest.json`,
  `tests/yldot/families/*/sigma.h5`, `tests/yldot/tolerances.toml`, `tests/yldot/overrides.toml` or a
  `tests/yldot/families/*/family.toml` is a finding: CRITICAL when the reference guard requires `Default results:
  changed`, HIGH when it requires `Test criteria: loosened`, MEDIUM otherwise. Run the guard where you have a shell
  (`validate` step 3b); in CI without one, list the paths. In a physics or bug-fix PR, the description must carry every
  declaration the guard requires (`CLAUDE.md` → Hard rules), and its `<family>:<id>` list must match the cases the
  plan, spec or RCA says move.

### 6. Python layer (`src/uedge/`)
- Logic errors, exception handling, save/restore format compatibility (old flat, UETOOLS, `uedge.hdf5`).
- Matches surrounding style (no type-hint or logging framework demanded).

### 7. AI-layer facts (`.claude/context/physics-models.md`, `branching.md`)
- Run `uv run .claude/hooks/check_context_refs.py --changed origin/<base>`. Any problem line is a finding
  (severity medium; high if a context module now gives wrong guidance on `pandf`, threadprivate or defaults).
- The change adds or moves a model, switch, routine, file or build step, and `CLAUDE.md`, `.claude/context/`
  or `physics-models.md` weren't updated to match: finding. The plan's "AI-layer facts affected" list is the checklist.
- The PR changes AI-layer **process** files (skills, agents, hooks, settings) on a ticket branch: finding (high).

### 8. Hygiene
- No unrelated reformatting, debug prints left in `pandf`, or commented-out blocks added.
- No secrets or local paths committed.

## Verify findings are real

Point to the exact line and the concrete failure (input/state → wrong result). Where cheap, confirm by reading
the call sites or building. Drop anything you cannot substantiate.

## Output

**Locally:** save the report to `.claude/work/<KEY>/code-review.md` (`<slug>` without a ticket): a working document,
gitignored and never committed. Fixes it leads to are recorded where the work is (commits; the ticket page through
`execute` or the review loop).
**In CI (pull request):** post the same content as a single PR comment and do not modify files.

```
Stats: files modified/added/deleted, +lines/-lines; change type: refactor | physics

severity: critical|high|medium|low
file: bbb/pandf_plasma_energy.m
line: 412
issue: <one line>
detail: <why it is wrong, concrete failure scenario>
suggestion: <fix>
```

If nothing survives verification: "Code review passed. No technical issues detected."

Severity guide: CRITICAL = wrong results/defaults changed in a refactor/data race; HIGH = wrong in some
configurations (X-point, multi-species, OMP); MEDIUM = robustness/solver risk; LOW = maintainability.
Do not start fixing without the user's approval — hand off to `code-review-fix`.
