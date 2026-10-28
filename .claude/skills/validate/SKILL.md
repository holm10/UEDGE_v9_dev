---
name: validate
description: Run UEDGE's quality gate — serial build (as CI), import smoke test, the regression suites from the pytests branch and the yldot suite (`tests/yldot`), the AIUE-8 OpenMP test flow when RHS/Jacobian code changed, and the serial old-vs-new bitwise check when Fortran, `.v` or `ppp/` changed — and report health with ✅/❌. Use before opening a PR and at the end of execute/implement-fix.
argument-hint: [suites e.g. "D_only D_mols" | "all"] [--omp] [--ticket <KEY>] [--no-tracker] [--tracker-dry-run]
---

# Validate

Run the UEDGE gate and report results. Mirror CI (`.github/workflows/build-test-wheel.yml`) so "green
locally" means "green in CI". Commands and background: `CLAUDE.md` → *Build & validation commands*,
`.claude/context/testing.md`.

Arguments: `$ARGUMENTS`. Suites (the pytests branch, step 3) default to `D_only` plus the suites matching the changed
area (below). `all` runs every suite; step 3b runs the yldot suite's PR tier whenever step 3 runs; `--omp` forces
step 4.

This is the **full gate**: run it once a change is complete, not after every edit. While iterating, run the subset
(one case, two thread counts, the one affected suite) and leave heavy matrices to CI (`.claude/context/testing.md` →
Fast iteration).

## 0. Branch hygiene

Immediately before the full run, `git fetch origin v9-develop`. If it moved past the branch's merge base (`git
merge-base HEAD origin/v9-develop` is not `origin/v9-develop`'s sha), rebase first and re-run the drift check below,
so the gate runs on the tree the PR will merge (AIUE-204: the base moved twice during AIUE-103, and one full run was
repeated).

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

Build in the worktree's own venv, with its `bin` first on `PATH` (the build runs `Forthon3` from `PATH`), and with
the install mode of the base venv it is compared with: same Python, same
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

## 3b. yldot regression suite (`tests/yldot`, epic AIUE-9)

Runs alongside step 3 (the retire ticket AIUE-108 removes step 3). In the worktree's own serial venv (step 1), from
the worktree root:

```bash
pip install -q pytest h5py
pytest tests/yldot -m "not nightly"      # the PR tier, 15-20 min on a serial build; never `pytest tests/`
```

`pytest tests/yldot` (no `-m`) adds the nightly tier: run it for an L-tier change. The session fetches the reference
data first and nothing skips (`.claude/context/testing.md` → the yldot bullets). Reading the result:
- A `test_default.py` failure means the defaults moved. Refactor: ❌. Physics or bug fix: ⚠️ only for the
  `<family>:<id>` entries the plan or RCA names, ❌ for any other.
- `test_manifest_inventory` failing with `missing:` after a new `+input` variable: regenerate its variant
  (`.claude/context/physics-workflow.md` → A new switch in the yldot suite).
- On a macOS `-O3` build two `BuildLimitWarning`s (d_c `bbb.mvolcur`, slab_phi `bbb.icnucx`) are recorded limits:
  ⚠️, not ❌.
- Never pass `--yldot-no-fetch`, and never edit a tolerance, override, manifest or `family.toml` to get green. A test,
  variant or block that behaves irregularly goes to the epic owner (AIUE-9 decision 23).

When the branch changes anything under `tests/yldot/`, also run the reference guard. Write the PR description to a
file and run it from a script file (the permission check refuses a `VAR=… cmd` prefix, `CLAUDE.md` → Gotchas):

```bash
PR_BODY="$(cat <pr description file>)" python tests/yldot/tools/check_reference_change.py check \
    --base origin/v9-develop --head HEAD --no-download
```

Report its `required:` line. Exit 1 means the description lacks a declaration it names (`CLAUDE.md` → Hard rules).

## 4. OpenMP check (when `bbb/pandf*`, `bbb/convert.m`, `ppp/`, or any `+threadprivate` var changed, or `--omp`)

The AIUE-8 test flow (`tests/deterministic_omp/README.md` → Test flow). It needs a default (OpenMP) build of this
worktree, in a venv of its own beside the serial one (one venv per build kind), and on macOS also the base OpenMP
venv of the branch point (`.claude/context/testing.md` → Fast iteration). Run the same command with each, from the
worktree root, with an absolute `<venv>` and an absolute, new `--out` (the workers run in their own directories,
so a relative path fails every run with ERROR):

```bash
<venv>/bin/python tests/deterministic_omp/harness/cli.py flow --python <venv>/bin/python \
    --out <worktree>/.claude/work/<KEY>/flow-<base|new>   # quick set: tebox and full at 2 and 4 threads, about 2 min
```

- **Linux:** ✅ on exit 0.
- **macOS:** `full` fails on the base too, from the documented C2 round-off (`.claude/context/openmp-jacobian.md`).
  ✅ when the change's summary table equals the base's: verdict, agreement and determinism of every group, and the
  mismatch rows and first mismatch of every deterministic one (a nondeterministic group's cell moves from run to
  run). ❌ for any group that differs (owner, 2026-10-24, AIUE-102).
- Exit 2 (ERROR, the flow cannot judge) is ❌ everywhere. The `jacrhs` arm is report-only (epic AIUE-70).
- The gate is `build-test-omp.yml`'s run on the PR (Linux, bitwise): quote its result.

While iterating, `--configs tebox --threads 4` takes about 5 s (it passed bitwise on macOS at 45ee607; it did not
at 0fac655, `tests/deterministic_omp/README.md`, so judge it against the base too). When the change touches
`ppp/` or the Jacobian, run `--all` (every configuration at 2, 4 and 8 threads) once, judged the same way. The flow
has one case, the AIUE-8 single-null deck, so for X-point or boundary code also run a double-null case with the
diagnostics of `.claude/context/openmp-jacobian.md` → "Verifying a change touches this correctly" (a diagnostic,
not the gate).

## 5. Serial old-vs-new bitwise check (when any Fortran — `*.m`, `*.F90`, hand-written `*.f` — a `.v` file or `ppp/` changed)

Run `tests/deterministic_omp/harness/serial_check.py` against base venvs of the branch point, as in
`.claude/context/testing.md` → "Serial old-vs-new bitwise check" (four venvs from clean committed trees). ✅ on
`RESULT: AGREE (bitwise identical; complete gate)`. For an intended change to results (a bug fix or physics that is
meant to move cases), ⚠️ when exactly the cases the plan or RCA names move, ❌ for any other. Quote the `RESULT` line.

Build the compared venvs from the final committed HEAD, code and code-facts included. A fix after the gate, even a
comment, needs a rebuild before the gate counts (`RESULT: INCOMPLETE … build older than HEAD`). Keep review-minor
fixes to comments on existing lines where possible, so the AI layer's line references don't move.

## Report

```
UEDGE validation — <branch> @ <short sha>
  Build (serial) ........ ✅/❌  <first error or "n warnings in touched files">
  Smoke import .......... ✅/❌  uedge_ver=<…>
  Suites ................ ✅/⚠️/❌  <suite: passed/failed, moved cases>
  yldot suite ........... ✅/⚠️/❌  <passed/failed, moved <family>:<id>; guard: required declarations or "not run">
  OpenMP flow ........... ✅/❌/skipped  <arm verdicts, new vs base on macOS; build-test-omp.yml run; or why skipped>
  Serial bitwise ........ ✅/⚠️/❌/skipped  <RESULT line, moved cases, or why skipped>
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
