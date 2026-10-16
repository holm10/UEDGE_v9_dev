---
name: validate
description: Run UEDGE's quality gate — serial build (as CI), import smoke test, the regression suites from the pytests branch, and the OpenMP serial-vs-parallel check when RHS/Jacobian code changed — and report health with ✅/❌. Use before opening a PR and at the end of execute/implement-fix.
argument-hint: [suites e.g. "D_only D_mols" | "all"] [--omp] [--no-tracker]
---

# Validate

Run the UEDGE gate and report results. Mirror CI (`.github/workflows/build-test-wheel.yml`) so "green
locally" means "green in CI". Commands and background: `CLAUDE.md` → *Build & validation commands*,
`.claude/context/testing.md`.

Arguments: `$ARGUMENTS`. Suites default to `D_only` plus the suites matching the changed area (below). `all` runs
every suite; `--omp` forces step 4.

## 0. Branch hygiene

```bash
uv run .claude/hooks/change_kind.py --range origin/v9-develop..HEAD
```

❌ if it reports a VIOLATION, i.e. the wrong kind of change on this branch (`.claude/context/branching.md`). Report it
verbatim.

```bash
uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop
```

❌ on any BROKEN, STALE, MOVED, NEW or MISSING line: the AI layer's description of the code is now wrong. Fix it on this
branch: `--fix` handles moved line numbers; anything else means re-reading the claim and rewriting it. Then lock
it with `--update` and commit with the trailer `AI-layer: code-facts`. Also list the "docs that cite files changed"
output: re-read those passages and confirm they are still true (⚠️ until you have). In a worktree, make sure the active venv belongs to this worktree (`python -c "import uedge; print(uedge.__file__)"`).

## 1. Build (serial, as CI)

```bash
pip install . -C "--build-option=--serial" 2>&1 | tee /tmp/uedge-build.log | tail -30
```

- ❌ on any compile error. Report the first error with its `.F` line **mapped back to the `.m` source** (the `.F`
  is generated; fix the `.m`).
- List any **new** `-Wconversion` / implicit-typing warnings in files you touched.

## 2. Smoke test

```bash
python -c "import uedge; from uedge import bbb, com; print(bbb.uedge_ver)"
```

If new variables/routines were added in a `.v` file, also confirm they are visible:
`python -c "from uedge import bbb; print(bbb.<newvar>)"`.

## 3. Regression suites (pytests branch)

```bash
git fetch upstream pytests
[ -d ../uedge-pytests ] || git worktree add ../uedge-pytests upstream/pytests
pip install -q pytest pytest-isolate
cd ../uedge-pytests && pytest --isolate --tb=long pytests/unittests/<suite> -s
```

Choose suites by what changed: impurities/`api` → `D+C`; molecules / gas → `D_mols`; slab or geometry →
`slab_D_only`; anything in `bbb/pandf*`, `convert.m`, `odesetup.m`, `svr/` → all `unittests` + `fulltests`.

Interpret failures with the **defaults rule** (`CLAUDE.md` → Hard rules):
- **Refactor / restructuring:** any fnrm or variable mismatch is a ❌ — the refactor changed results.
- **Intended physics change to defaults:** mismatches are expected only in the cases the plan/spec named.
  Report them as ⚠️ "expected, documented", list every moved case, and flag any *unexpected* one as ❌.

## 4. OpenMP check (when `bbb/pandf*`, `bbb/convert.m`, `ppp/`, or any `+threadprivate` var changed, or `--omp`)

Requires a default (OpenMP) build: `pip install .` (re-run step 2 afterwards). Then, in a case directory
(e.g. one of the pytests cases):

```python
from uedge import bbb, ppp
exec(open("input.py").read())
ppp.OMPParallelPandf1 = 1; ppp.OMPParallelJac = 1; ppp.Nthreads = 4
ppp.CheckPandf1 = 1; ppp.CheckJac = 1
bbb.exmain()
```

❌ if the serial/parallel comparison reports differences. Prefer a double-null or snowflake case when the change
touches X-point or boundary code. Rebuild serial afterwards if you will run step 3 again.

## Report

```
UEDGE validation — <branch> @ <short sha>
  Build (serial) ........ ✅/❌  <first error or "n warnings in touched files">
  Smoke import .......... ✅/❌  uedge_ver=<…>
  Suites ................ ✅/⚠️/❌  <suite: passed/failed, moved cases>
  OpenMP check .......... ✅/❌/skipped  <why skipped>
  Branch / AI-layer facts ✅/⚠️/❌  <policy violations; drift check result; docs re-read>
Overall: ✅ READY / ❌ NOT READY
```

Quote failing output verbatim. Never loosen tolerances or skip a suite to get green.

## Ticket record

On a ticket branch with a Jira key (from the branch name), run `ticket-page <KEY> log Validation "<entry>"` with
`status Validating`: the report block's lines with the branch tip, and for each ❌ the failing output verbatim,
trimmed to the failing part (the first error, the mismatching fnrm or variable lines). Skip it with `--no-tracker`.
A failed call is noted under the report and never changes the verdict.
