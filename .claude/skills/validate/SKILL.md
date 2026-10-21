---
name: validate
description: Run UEDGE's quality gate — serial build (as CI), import smoke test, the regression suites from the pytests branch, and the OpenMP serial-vs-parallel check when RHS/Jacobian code changed — and report health with ✅/❌. Use before opening a PR and at the end of execute/implement-fix.
argument-hint: [suites e.g. "D_only D_mols" | "all"] [--omp] [--ticket <KEY>] [--no-tracker] [--tracker-dry-run]
---

# Validate

Run the UEDGE gate and report results. Mirror CI (`.github/workflows/build-test-wheel.yml`) so "green
locally" means "green in CI". Commands and background: `CLAUDE.md` → *Build & validation commands*,
`.claude/context/testing.md`.

Arguments: `$ARGUMENTS`. Suites default to `D_only` plus the suites matching the changed area (below). `all` runs
every suite; `--omp` forces step 4.

This is the **full gate**: run it once a change is complete, not after every edit. While iterating, run the subset
(one case, two thread counts, the one affected suite) and leave heavy matrices to CI (`.claude/context/testing.md` →
Fast iteration).

## 0. Branch hygiene

```bash
uv run .claude/hooks/change_kind.py --range origin/v9-develop...HEAD
```

❌ if it reports a VIOLATION, i.e. the wrong kind of change on this branch, or a working document (plan, review,
RCA, validation record) committed on it (`.claude/context/branching.md`). Report it verbatim. ⚠️ for a `WARNING:
PR size budget` line (too many files or lines outside product source and tests, a file over 1 MB, data-like files):
not a failure, but move raw data out of the branch (summarise it on the ticket page) or justify it in the PR. A ticket started before
working documents left git fails here until they are removed: follow `branching.md` → "Tickets started before this
rule" (their content to the page, the tag `archive/<KEY>-docs`, then `git rm`).

```bash
uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop
```

❌ on any BROKEN, STALE, MOVED, NEW or MISSING line: the AI layer's description of the code is now wrong. Fix it on this
branch: `--fix` handles moved line numbers; anything else means re-reading the claim and rewriting it. Then lock
it with `--update` and commit with the trailer `AI-layer: code-facts`. Also list the "docs that cite files changed"
output: re-read those passages and confirm they are still true (⚠️ until you have). In a worktree, make sure the active venv belongs to this worktree (`python -c "import uedge; print(uedge.__file__)"`).

## 1. Build (serial, as CI)

```bash
pip install -v --no-build-isolation . -C "--build-option=--serial" 2>&1 | tee /tmp/uedge-build.log | tail -30
```

Build in the worktree's own venv with the install mode of the base venv it is compared with: same Python, same
Forthon/numpy/setuptools, `--no-build-isolation`, same `CC` (`.claude/context/testing.md` → "Compared builds use one
install mode"). A venv with none of them installed yet: `pip install "forthon>=0.10.7" numpy setuptools h5py` first.

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
git fetch origin pytests                 # v9: the fork's pytests branch holds v9's references (testing.md)
[ -d ../uedge-pytests ] || git worktree add --detach ../uedge-pytests origin/pytests
git -C ../uedge-pytests log -1 --oneline  # must be origin/pytests; if not: git -C ../uedge-pytests checkout --detach origin/pytests
pip install -q pytest pytest-isolate
cd ../uedge-pytests && pytest --isolate --tb=long pytests/unittests/<suite> -s
```

Choose suites by what changed: impurities/`api` → `D+C`; molecules / gas → `D_mols`; slab or geometry →
`slab_D_only`; anything in `bbb/pandf*`, `convert.m`, `odesetup.m`, `svr/` → all `unittests` + `fulltests`.

A failure listed in `.claude/context/testing.md` → "Known failures on `v9-develop`" is ⚠️ pre-existing (quote it and
say so). Any other failure is the change's until a run on the base venv shows the same output.

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

Longer validation records and run protocols (full logs, per-case tables) go in the ticket's working folder
`.claude/work/<KEY>/validation/` (`<slug>` without a ticket): local, never committed. What must last goes on the
ticket page (below): the report block and every failure verbatim.

## Ticket record

The Jira key comes from `--ticket <KEY>` (callers pass it: `execute`, `implement-fix` and `end-to-end-feature`
always do, since a `bugfix/v9-issue-<N>-…` branch has none), else from the branch name (`feature/v9-<KEY>-…`,
`bugfix/v9-<KEY>-…`), else from the `**Jira**` line or the H1 of the plan or RCA in the worktree's working folder
(`.claude/work/*/`). No key: no record (the report block then belongs in the PR description). With a key, run
`ticket-page <KEY> log Validation "<entry>"`: the report block's lines with the branch tip, and for each ❌ the failing
output verbatim, trimmed to the failing part (the first error, the mismatching fnrm or variable lines). Add `--flush`
only when `validate` was run on its own, and then also `ticket-page <KEY> progress "validate: <Overall line>"`;
inside `execute`, `implement-fix` or `end-to-end-feature` the entry goes out with the flush that ends that step
(`ticket-page` → "When to flush").
`--no-tracker` skips it; `--tracker-dry-run` passes `--dry-run` (nothing is queued; the entry is shown). A failed call
is noted under the report and never changes the verdict.
