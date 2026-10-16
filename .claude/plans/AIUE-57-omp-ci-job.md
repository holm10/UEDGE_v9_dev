# Feature: AIUE-57 — OpenMP CI job `build-test-omp.yml`

Validate the patterns and file references below before implementing.

## Summary
**Type**: Python/Build (CI workflow + test tooling; no Fortran, `.v`, `setup.py` or `src/uedge` change)
**Complexity**: Medium
**Default results**: Unchanged (no product physics or numerics touched)
**Packages / files**: `.github/workflows/build-test-omp.yml`; `tests/deterministic_omp/ci/{run_omp_ci.sh,report.py,
test_report.py}` (update); `tests/deterministic_omp/ci/{jac_bound.py,test_jac_bound.py,common_check.py,
test_common_check.py}` (new); `tests/deterministic_omp/linux/{run_ci_replay.sh,README.md}` (new / update);
`tests/deterministic_omp/README.md` (CI section); `docs/reviews/AIUE-56-c1-gate.py` (docstring note only);
`.claude/context/{testing,openmp-jacobian}.md` (code-facts); `docs/reviews/AIUE-57-validation.txt` (new section)
**Branch / worktree**: `feature/v9-AIUE-57-omp-ci-job` @ `../uedge-wt/AIUE-57` (base: `bugfix/v9-openmp-determinism-fix` @ `9fa2a0e`; the AIUE-57 commits were rebased onto it, old base `3c03d1c`)
**Ticket page**: pending (written by the ticket-page skill)

The rework is **Amendment 1** below. The original plan (approved, implemented, reviewed to APPROVE in round 2) follows
it unchanged under "Original plan"; where the two disagree, Amendment 1 wins.

## Amendment 1 — rework on the combined OpenMP fix branch (2026-10-15)

### Why the rework
The original job was built for the pre-fix code and gated bitwise, with a "do not merge" condition: AIUE-56 merged,
and the gate able to be green (decision 9 or AIUE-61). Since then (owner decisions, merge record
`docs/reviews/omp-determinism-merge-validation.txt`):

- **Decision 9 = option F, implemented as AIUE-61**: fixed chunks, every chunk starting from a fresh full `pandf`
  (`ppp/ppp.v:60-75`, `OMPJacFixedChunks=1`, `OMPJacNchunksFixed=64`, `OMPJacMinChunkLen=300` by default; chunk count
  `min(64, max(1, neq/300))`, `ppp/omp_parallel.F90:317`). Reproducible and thread-count independent.
- **Linux x86-64: the fixed build is bitwise equal to serial** (AIUE-61 R5, `docs/reviews/AIUE-61-validation.txt:138-149`:
  tebox 25 chunks, full 2/4/8 threads, up 4/8 threads, all PASS; AIUE-62 `docs/rca/AIUE-8-omp-jacobian-nondeterminism.md`
  §Linux characterisation: no C2 on x86-64; M3 absent with AIUE-61). On macOS arm64 C2 remains (full 12 275 Te-row
  entries, worst 4.59e-9 × row max; tebox with 25 chunks 2 entries), so a tolerance applies there.
- **AIUE-64**: `setup.py:769-785` links the Linux OpenMP extensions with `-fopenmp`; no `LDFLAGS` workaround is needed.
  (The workflow never had one; the AIUE-62 Linux scripts did.)
- **The RHS arm (`OMPParallelPandf1=1`) moved to epic AIUE-70** (AIUE-58 R1–R4; AIUE-74 out-of-bounds write in
  `MakeXptChunks` on small grids). It **stays report-only**.
- **Gate-tool issue**: `docs/reviews/AIUE-56-c1-gate.py:36-43` judges `captured[k]` (raw, unscaled) whenever the build
  has the AIUE-47 capture hook, giving a false FAIL on the full problem (raw 1.98e-4 vs scaled 4.59e-9); the decision
  recorded at `docs/reviews/omp-determinism-merge-validation.txt:68-80`: the C1 bound is defined on the **scaled
  `post_exmain`** Jacobian.
- **Default tebox is 1 chunk now** (neq 25 < 300): with the default settings the Te-box flows would compare serial
  with serial-equivalent code and test nothing. They must set `OMPJacMinChunkLen=1` (25 chunks, as AIUE-61's
  `tebox1` did) to exercise the parallel path.

### Rebase (done in phase 1)
`git rebase --onto 9fa2a0e 3c03d1c feature/v9-AIUE-57-omp-ci-job` (`3c03d1c` = AIUE-52 round-3 APPROVE, the parent of
the first AIUE-57 commit `4008105` and the merge base with `9fa2a0e`). 8 commits replayed (new `ea03fe5..c338684`).
Conflicts: `.claude/context/openmp-jacobian.md` in 3 commits (`34c1647`, `a401258`, `df15508`): AIUE-57's CI
sentence(s) at the end of the test-flow section vs AIUE-53's "Serial old-vs-new bitwise check" section added after
it. Resolved keeping both: AIUE-57's (latest) CI wording at the end of the test-flow paragraph, then AIUE-53's
section unchanged. `testing.md` and `README.md` merged cleanly. Backup ref `backup/AIUE-57-pre-rebase-8ee189d`.
After the rebase: `check_context_refs.py --changed origin/v9-develop` OK; `change_kind.py --range 9fa2a0e..HEAD`
OK; `pytest tests/deterministic_omp/harness tests/deterministic_omp/ci` 142 passed.

### Context references — read before implementing
- `tests/deterministic_omp/ci/run_omp_ci.sh:52` (`TOL`), `:54-57` (sets), `:76-93` (unit + smoke), `:95-106` (gate
  mode stub), `:108-139` (flow loop, `IFS='|' read` at `:113`), `:142-148` (report) — the script to change.
- `tests/deterministic_omp/ci/report.py:71-118` (`problem_lines`), `:169-243` (`main`, `--gate-mode` at `:174`).
- `.github/workflows/build-test-omp.yml:1-13` (header, DO NOT MERGE), `:42-51` (env, `OMP_CI_JAC_TOLERANCE`),
  `:68-79` (build, run).
- `tests/deterministic_omp/harness/flow.py:75-100` (`group_verdict`: `deterministic` `:93`, `failing_sections`
  `:99`), `:411-423` (`run_flow`, `ppp` is applied to serial and OpenMP runs alike), run dirs
  `<config>/serial`, `<config>/<arm>_t<threads>/run<k>`.
- `tests/deterministic_omp/harness/worker.py:184-212` (record arrays `jac_post`, `jacj_post`, `jaci_post`, `suscal`,
  `eq`; `post_exmain_permuted`; `capture.count`, `capjac_k`).
- `tests/deterministic_omp/harness/cli.py:133,153` (`--ppp` JSON on `check`/`flow`).
- `docs/reviews/AIUE-56-c1-gate.py` (whole; the bound to port), `docs/reviews/AIUE-60-common-check.py` (whole; the
  check to port; ELF branch `:37-46`).
- `tests/deterministic_omp/linux/{Dockerfile.ubuntu,build_uedge.sh,README.md}` (AIUE-62; the replay base).
- `ppp/ppp.v:60-75`, `ppp/omp_parallel.F90:314-317` (fixed-chunk knobs and count).
- `.claude/context/testing.md:80-93`, `.claude/context/openmp-jacobian.md:146-148,177-179` (code facts to update).

### Patterns to mirror
- Flow spec parsing (`run_omp_ci.sh:113`): `IFS='|' read -r name configs threads repeats arms itermx <<< "$spec"`;
  a 7th field `ppp` (JSON; contains no `|` or `;`) is read the same way, empty = none.
- Fail-closed exit codes everywhere: 0 pass, 1 gated mismatch, 2 cannot judge (`run_omp_ci.sh` header, flow.py
  `exit_code`, `AIUE-60-common-check.py` `main`).
- Unit tests without a build: `tests/deterministic_omp/ci/test_report.py` (`_flow` fixture writing `flow.json`) — the
  new tests write synthetic `record.json` + `record.npz` and generated `*_p.F90` the same way.

### Step-by-step tasks

#### UPDATE `tests/deterministic_omp/ci/run_omp_ci.sh`
- **IMPLEMENT**:
  1. Flow spec gains a 7th field `ppp` (JSON, passed as `--ppp`). New sets:
     - `pr`: `tebox1|tebox|2,4|3|jac|none|{"OMPJacMinChunkLen": 1}`; `tebox|tebox|2,4|5|jac,jacrhs|3|{"OMPJacMinChunkLen": 1}`;
       `up1|up|4|3|jac|none|` (default 21 chunks; the configuration where M3 showed before AIUE-61);
       `full|full|2,4|2|jac|3|` (default 64 chunks). The full-problem `jacrhs` stays out of the PR set (report-only,
       expensive).
     - `nightly`: `all1|ALL||2|jac,jacrhs|none|` (default partition per configuration); `tebox1|tebox|2,4,8|3|jac,jacrhs|none|{"OMPJacMinChunkLen": 1}`;
       `all|ALL||3|jac,jacrhs|3|`.
  2. **Common-block check** (new step 3, after the smoke test): when `OMP_CI_GEN_DIR` is set, run
     `ci/common_check.py --pkgdir <pkgdir> --gen $OMP_CI_GEN_DIR`, with `<pkgdir>` from
     `$PY -I -c "import importlib.util as u; print(u.find_spec('uedge').submodule_search_locations[0])"` (no import
     of `uedge`, so no `.uedgerc`). Exit 1 → job exit 1 ("common block FAIL"); 2 → exit 2. Unset → print
     "common-block check skipped (OMP_CI_GEN_DIR not set)"; the workflow always sets it.
  3. **Gate mode** (replaces the `--jac-tolerance` forwarding stub `:95-106`): `OMP_CI_JAC_TOLERANCE` empty → mode
     `bitwise`; a value → must parse as a float in (0, 1e-3], else exit 2; mode `tolerance <v>`. Nothing is passed to
     the flow; the flows always run with `--gate $GATE` (bitwise verdicts).
  4. **Bound step** (after the flows): `ci/jac_bound.py --flow <dir> --tol <v or 1e-6> --json <dir>/bound.json` for
     every flow dir (jac arm groups only). Its exit code is passed to `report.py` (`--bound-codes`).
  5. `report.py` gets `--gate-mode`, `--tol`, and reads each flow's `bound.json`.
- **GOTCHA**: bash 3.2 compatible (macOS), `set -u` with empty arrays; `--ppp` must not be passed when the field is
  empty (a pre-AIUE-61 build has no `OMPJacMinChunkLen`: Forthon raises "no such attribute", the serial reference
  fails, the flow is an ERROR — that is the correct outcome for the unmodified `pr` set on such a build).
- **VALIDATE**: `bash -n`, `shellcheck tests/deterministic_omp/ci/run_omp_ci.sh`; `OMP_CI_JAC_TOLERANCE=abc …` → exit 2.

#### CREATE `tests/deterministic_omp/ci/jac_bound.py` (+ `test_jac_bound.py`)
- **IMPLEMENT**: the AIUE-56 C1 bound, fixed. For each jac group's runs vs that configuration's serial record:
  judge **only `post_exmain`** (the scaled matrix the bound was registered on; `jac_post`, natural order → per-row
  bound `tol × serial row max` and the Te-row magnitude ratio ≤ 10; permuted (`post_exmain_permuted`) → global max,
  as the original). `captured[k]` (raw, unscaled) is **reported, not judged**: worst raw `|a-b|/rowmax` and a line
  "captured[k]: raw (unscaled), not judged; the bound is defined on the scaled post_exmain Jacobian". Runs without a
  record (crash) are skipped (the flow already FAILs them). Output: one line per run, `bound.json`
  (`{group: {run: {pass, worst_ratio, worst_dev, over, raw_worst}}}`), exit 0/1/2. Also usable on a `cli.py check`
  directory (`CHECKDIR...`, the old interface) so `linux/gate_flows.py` can take it.
- **PATTERN**: `docs/reviews/AIUE-56-c1-gate.py:46-99` (`as_dict`, `gate`), unchanged arithmetic.
- **GOTCHA**: `record.npz` of the full problem is ~60 MB per run; load one run at a time.
- **VALIDATE** (unit tests, no build): synthetic serial/run records where (a) `captured[0]` differs by 1.98e-4 × row
  max (one entry dropped to 0) and `post_exmain` by 4.6e-9 → PASS with the raw line printed; (b) `post_exmain` off
  by 2e-6 → FAIL; (c) Te-row magnitude ×11 → FAIL; (d) permuted `post_exmain` → global-max bound; (e) a missing
  `record.npz` for the serial → exit 2.

#### UPDATE `tests/deterministic_omp/ci/report.py` (+ `test_report.py`)
- **IMPLEMENT**:
  - Bitwise mode (default): unchanged verdicts; each failing jac line gains "C1 bound: within (worst x)" or
    "C1 bound: EXCEEDED (n entries, worst x)"; a bound FAIL (`bound.json` pass false) on any jac run is a gated
    failure even if the flow passed (backstop: independent implementation). Bound exit 2 → job exit 2.
  - Tolerance mode: a gated jac group that is FAIL in the flow becomes **PASS (within tolerance v)** iff: no run
    failures/ERROR; `deterministic` is true; every agreement report fails only in `jacobian:*` sections; every run
    passes `jac_bound` at `tol=v`. Otherwise it stays FAIL. Under `--itermx N` a Jacobian difference that moves the
    Newton path makes `yldot`/`fnrm` differ → FAIL (by design; documented).
  - Headline `## OpenMP determinism CI: PASS|FAIL|ERROR (set, gate, mode)` and `OMP CI RESULT:` line unchanged.
  - Drop the "expected FAIL" wording nowhere needed: report.py has no pre-fix assumption; only docs do.
- **VALIDATE**: new tests: bound line in bitwise mode; bound FAIL on a flow-PASS group → exit 1; tolerance mode:
  Jacobian-only + deterministic + bound pass → PASS; with `yldot` failing → FAIL; non-deterministic → FAIL; run
  failure → FAIL.

#### CREATE `tests/deterministic_omp/ci/common_check.py` (+ `test_common_check.py`)
- **IMPLEMENT**: port of `docs/reviews/AIUE-60-common-check.py` with `--pkgdir DIR` (the installed `uedge` package
  directory) instead of `--venv` (setup-python is not a venv); logic, output and exit codes unchanged (ELF:
  `nm -D -S`, symbol class `[BCDVbcdv]`; Mach-O: `nm -m`).
- **VALIDATE**: unit tests with a fake `nm` (monkeypatched `subprocess.run`) and synthetic `bbb_p.F90`/`api_p.F90`:
  PASS; FAIL (first definer `compy`; or a larger later block); ERROR (nm failure, no definer, size unknown); ELF and
  Mach-O parsing.

#### UPDATE `.github/workflows/build-test-omp.yml`
- **IMPLEMENT**: remove the DO-NOT-MERGE header (`:7-12`); header states what is gated (jac arm bitwise on Linux with
  the C1 bound as a backstop; `jacrhs` report-only, epic AIUE-70). Build step unchanged (`python -m pip install -v .`,
  no `LDFLAGS`; AIUE-64). New step after the build: resolve `OMP_CI_GEN_DIR` (exactly one `build/temp.*` dir with
  `bbb_p.F90`, else fail) into `$GITHUB_ENV`. `OMP_CI_JAC_TOLERANCE: ""` comment rewritten (bitwise on Linux; a value
  switches to the tolerance mode above, e.g. for macOS replays). Triggers, concurrency, timeouts (30 / 150 min),
  artifacts unchanged; add `omp-ci-out/**/bound.json` to the artifact paths.
- **VALIDATE**: `python -c 'import yaml; yaml.safe_load(open(".github/workflows/build-test-omp.yml"))'`;
  `uvx --from actionlint-py actionlint .github/workflows/build-test-omp.yml`.

#### CREATE `tests/deterministic_omp/linux/run_ci_replay.sh` (+ README row)
- **IMPLEMENT**: inside `aiue62-ubuntu:amd64` (`Dockerfile.ubuntu`, Ubuntu 24.04, gcc 13.3): `run_ci_replay.sh NAME
  COMMIT [SET]` clones `/mnt/repo` at COMMIT into `/work/ci-NAME`, makes a venv with the workflow's pip line
  (`"forthon>=0.10.7" numpy==1.26.4 h5py pytest`), runs `python -m pip install -v .` in that tree (no `LDFLAGS`
  unless the caller sets it), resolves `OMP_CI_GEN_DIR` as the workflow step does, and runs
  `OMP_CI_CORES=4 PYTHON=<venv python> bash tests/deterministic_omp/ci/run_omp_ci.sh SET` with `OMP_CI_OUT=/out/NAME`
  (`OMP_CI_CORES=4`: `nproc` in the container reports the host's cores, `--cpus 5` only caps time).
  `RUN_TREE=DIR` optionally runs the CI scripts of another clone against this build (negative control).
- **VALIDATE**: `bash -n`, `shellcheck`.

#### UPDATE docs: `tests/deterministic_omp/README.md` (CI section), `docs/reviews/AIUE-56-c1-gate.py` (docstring)
- README `:332-345`: remove the "Do not merge" block; state the gate (bitwise on Linux, C1 bound backstop on the
  scaled matrix, tolerance mode for macOS), the new sets (table), `OMP_CI_GEN_DIR` and the common-block check, the
  `ppp` field and why the Te box needs `OMPJacMinChunkLen=1`, RHS arm report-only (AIUE-70).
- `AIUE-56-c1-gate.py`: docstring note only — "judges raw `captured[k]` when present; the bound is defined on the
  scaled `post_exmain` (merge validation); use `tests/deterministic_omp/ci/jac_bound.py`". Logic unchanged so the
  historical records stay reproducible.

#### UPDATE `.claude/context/testing.md:80-93`, `.claude/context/openmp-jacobian.md:146-148,177-179` (code-facts)
- New sets, gate (bitwise + bound backstop + tolerance mode), common-block check, remove the merge condition.
  Separate commit, trailer `AI-layer: code-facts`.
- **VALIDATE**: `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` → OK.

#### UPDATE `docs/reviews/AIUE-57-validation.txt` — section "9. Rework on the combined branch" with every result below.

### Testing strategy — pre-registered validation
Pass criteria fixed now; results recorded verbatim in `docs/reviews/AIUE-57-validation.txt` §9. Docker: one
container at a time, `--platform linux/amd64 --cpus 5 --memory 7g`, image `aiue62-ubuntu:amd64`, repo mounted
read-only at `/mnt/repo` (the main checkout; the worktree commits are in its object store). Everything at the
committed rebased tip `T` (clean tree).

| # | Check | Command (abridged) | Pass criterion |
|---|---|---|---|
| V1 | Unit tests | `python -m pytest -q tests/deterministic_omp/harness tests/deterministic_omp/ci` | all pass (≥ 142 + new) |
| V2 | Static | `bash -n` + `shellcheck` (run_omp_ci.sh, run_ci_replay.sh); `yaml.safe_load`; `actionlint` | all clean |
| V3 | Gate script raw vs scaled (unit) | `test_jac_bound.py` cases (a)–(e) above | (a) PASS with raw line, (b)(c) FAIL, (d) global bound, (e) exit 2 |
| V4 | Gate script on real data | `ci/jac_bound.py` on `uedge-wt/logs/omp-determinism/chk_full_t4` (merge validation, macOS) vs `docs/reviews/AIUE-56-c1-gate.py` on the same | new: PASS, worst 4.59e-09, raw line 1.98e-04 "not judged"; old: FAIL (reproduces the tool issue) |
| V5 | **CI replay, rebased tree** | `run_ci_replay.sh fix T pr` | `OMP CI RESULT: PASS (exit 0)`; common-block check `RESULT: PASS` (first definer `bbbpy`); import OK with no `LDFLAGS`; every jac group 100 % agree with serial and deterministic; bound worst 0; `jacrhs` lines are warnings only |
| V6 | **Negative control, pre-fix** | build `origin/v9-develop` `e52a44d` with `LDFLAGS=-fopenmp` (pre-AIUE-64 needs it); `RUN_TREE=T`, `OMP_CI_FLOWS` = the `pr` flows with the `ppp` field empty (the knob does not exist pre-AIUE-61) | exit 1, `OMP CI RESULT: FAIL`; every jac group in `tebox1`/`tebox`/`full` FAIL with Te-row first mismatch and C1 bound EXCEEDED; `FIRST MISMATCH` line names a Te cell |
| V6b | Pre-fix with the unmodified `pr` set | as V6, `OMP_CI_FLOWS` = `tebox1` flow only, with its `ppp` | exit 2, ERROR naming `OMPJacMinChunkLen` (fail closed) |
| V6c | Common-block check on the pre-fix build | part of V6 | recorded; expected FAIL (a package other than `bbbpy` defines the block first, as AIUE-60's pre-amendment build); if PASS, record it — the FAIL path is then covered only by V1 |
| V7 | **Seeded race on the rebased tree** | `T` + `+threadprivate` removed from `resee` (`bbb/bbb.v`, as AIUE-57 §2), scratch commit, `run_ci_replay.sh race <sha>` with `OMP_CI_FLOWS` = the two Te-box `pr` flows | exit 1; every tebox jac group FAIL (mismatch or crash); rate recorded |
| V8 | Tolerance mode (macOS, `venvs/omp-determinism-omp`) | `OMP_CI_FLOWS='tebox1|tebox|4|3|jac|none|{"OMPJacMinChunkLen": 1}'` bitwise, then `OMP_CI_JAC_TOLERANCE=1e-6` | bitwise: exit 1 (C2, Te-row entries); tolerance: exit 0 "PASS (within tolerance 1e-6)" |
| V9 | Tolerance mode does not hide C1 | V8's tolerance run on `venvs/base-omp` (pre-fix; `ppp` field empty) | exit 1, bound EXCEEDED |
| V10 | Drift and branch | `check_context_refs.py --changed origin/v9-develop`; `change_kind.py --range 9fa2a0e..HEAD` | both OK |

Nightly set: not run in full (emulated time); `run_ci_replay.sh` with `nightly` is optional and informational.
Order: V1–V4, V10 locally; then V5, V6/V6b, V7 in Docker one after another; V8–V9 on the Mac (not during a Docker run).

**Only the real GitHub run on the PR can confirm**: native `ubuntu-latest` hardware (all Linux evidence is Rosetta-
emulated x86-64), Python 3.11 from setup-python (the image has 3.12), the measured PR wall time (≤ 20 min budget;
emulated timings are not a prediction), the in-tree `build/temp.*` path on the runner, the nightly schedule (default
branch only), the 20/20 red-run criterion of the ticket (needs pushes of red trees), and annotations/step summary.

### AI-layer facts affected
- `.claude/context/testing.md:80-93` — the CI bullet (sets, gate, merge condition): rewritten.
- `.claude/context/openmp-jacobian.md:146-148` and `:177-179` — gate wording (bitwise + bound backstop; tolerance
  mode) and the PR set.
- Checked: `CLAUDE.md`, `architecture.md` do not describe the CI job or `tests/deterministic_omp/ci`; the `validate`
  skill is process (not touched on this branch).

### Validation commands
`validate` skill parts that apply (no Fortran change: no serial build or regression suites needed; the D_only stale
references are not a concern per the owner) plus V1–V10.

### Acceptance criteria
- [ ] V1–V10 pass as pre-registered (V6c recorded either way)
- [ ] Workflow builds like `setup.py` does now (no `LDFLAGS`), triggers/budget/timeouts unchanged
- [ ] RHS arm report-only, citing AIUE-70
- [ ] AI-layer facts updated; drift check clean
- [ ] Not pushed; the first PR run's wall time and verdict go into the PR description

### Notes and open questions
- **Tolerance mode in the CI layer** (recommended) vs dropping `OMP_CI_JAC_TOLERANCE` (Linux is bitwise; YAGNI). The
  mode makes local macOS replays meaningful (C2) and keeps the switch honest; it never relaxes anything on CI unless
  someone sets the variable in the workflow.
- `up1` in the PR set (+~1 min) is a guard for M3 (`up` rows at ≥ 4 threads before AIUE-61); can be dropped if the
  measured PR time is tight.
- `OMPJacMinChunkLen=1` on the Te box tests a non-default partition (25 chunks); the default (1 chunk) is covered by
  `all1` nightly and is serial-equivalent. The full problem runs the default (64 chunks).
- Python 3.12 in the replay image vs 3.11 on CI: accepted deviation (AIUE-62 used the same image).

# Original plan (approved 2026-10-15; superseded where Amendment 1 differs)

### Original summary
**Type**: CI (workflow + test tooling; no Fortran, `.v` or `src/uedge` change)
**Complexity**: Low–medium
**Default results**: Unchanged (no product physics or numerics touched)
**Files (original)**: `.github/workflows/build-test-omp.yml`, `tests/deterministic_omp/ci/{run_omp_ci.sh,report.py,test_report.py}`,
`tests/deterministic_omp/README.md` (CI section), `.claude/context/{testing,openmp-jacobian}.md` (code-facts),
`docs/reviews/AIUE-57-validation.txt`
**Branch (original)**: `feature/v9-AIUE-57-omp-ci-job` @ `../uedge-wt/AIUE-57` (stacked on
`feature/v9-AIUE-52-omp-test-flow`; restacked by the main session once AIUE-49's stricter comparator lands)

> **DO NOT MERGE before AIUE-56 (the OpenMP Jacobian fix) AND before the gate can be green on it.** The job is red
> on the pre-fix code by design. The AIUE-56 build is still red under the bitwise gate while C2/M2 (round-off-level
> Te-row entries) remains, so merging also waits for decision 9 (a tolerance gate) or AIUE-61 (C2/M2 removed).
> (Review round 1, R1-M2.)

## Problem and solution
CI builds only `--serial` (`build-test-wheel.yml`), so OpenMP races are never seen. AIUE-57 adds a workflow that builds
the default OpenMP build and runs the AIUE-52 flow on the Te box and the full problem, gating on the Jacobian arm.
All steps live in a script so they run the same locally and in CI.

## Decisions
- **Workflow calls only the CLI** (`harness/cli.py flow`) through `ci/run_omp_ci.sh`; nothing imports harness
  internals, so the AIUE-49 restack does not touch the CI files. `ci/report.py` reads only `flow.json` fields the
  AIUE-52 flow writes (`groups[].{config,arm,threads,verdict,first_mismatch,agree_serial,errors,run_failures}`,
  `gated`, `exit_code`, `settings`, `timing`).
- **Triggers:** `pull_request`, `push` to `v9-develop`/`main` → `pr` set (review R1-m3: no duplicate push + PR
  runs); `schedule` (daily 03:17 UTC) → `nightly` set; `workflow_dispatch`
  with a `set` choice. One job, set and timeout chosen by expression (30 min PR, 150 min nightly). `concurrency`
  cancels superseded pull-request runs only. `permissions: contents: read`.
- **PR set** (reduced, budget ≤ 20 min): `tebox1` 2,4 threads K=3 `jac`, one evaluation (locates the defect
  cell; review R1-M1); `tebox` 2,4 threads K=5 both arms; `full` 2,4 threads K=2 `jac` only; the last two
  `--itermx 3`. Per-flow `itermx` is the sixth field of a flow spec. The full-problem `jacrhs` runs are dropped from the PR set because the arm is report-only and they
  are the most expensive runs (≈ 40 % of the full flow); the nightly set runs them.
- **Nightly set:** `--all` (8 configurations, 2,4,8 threads) one evaluation K=2, and `--all` K=3 `--itermx 3`;
  both arms.
- **Gate:** `--gate jac` (bitwise, the flow's own jac-arm verdict). `jacrhs` failures become `::warning::`
  annotations only. Exit 2 (cannot judge) is red as well.
- **Decision-9 switch:** `OMP_CI_JAC_TOLERANCE` (workflow `env`). Empty = bitwise. Non-empty is forwarded as
  `--jac-tolerance VALUE`; the script first checks `flow --help` for that option and stops with exit 2 if the harness
  lacks it. No tolerance comparator is implemented here (out of scope; harness ticket).
- **Failure message:** `report.py` prints one `GATED` line per failing gated group (configuration, arm, threads,
  equation and cell parsed from the flow's `first_mismatch`, runs agreeing), emits `::error::` on Actions, writes
  the combined `summary.md` and appends it to `$GITHUB_STEP_SUMMARY`.
- **Artifacts:** summaries, `flow.json`, logs, `record.json`/`spec.json`; not `record.npz` (~60 MB per full run).
- **Install:** mirrors `build-test-wheel.yml` (`forthon>=0.10.7` quoted — the existing workflow's unquoted `>=`
  is a shell redirect — `numpy==1.26.4`, `h5py`, `pytest`), then `pip install -v .`.

## Tasks
1. `ci/run_omp_ci.sh` (sets, env knobs, unit tests, smoke test, flows, report; bash 3.2 compatible; shellcheck clean).
2. `ci/report.py` + `ci/test_report.py`.
3. `.github/workflows/build-test-omp.yml` (actionlint clean).
4. README CI section; context code-facts (`testing.md` CI facts, `openmp-jacobian.md`), separate commit with
   `AI-layer: code-facts`.
5. Local evidence: pre-fix build red (exit 1, named first mismatch); seeded race (`resee` without `+threadprivate`)
   on v9-develop and on v9-develop + C1 swap red; C1-swap proxy build to show what the bitwise gate does after C1.
6. `docs/reviews/AIUE-57-validation.txt`; `check_context_refs.py --changed origin/v9-develop` clean.

## Validation
- `bash -n`, `shellcheck`, `actionlint` (via `uvx --from actionlint-py`), YAML load.
- `python -m pytest tests/deterministic_omp/harness tests/deterministic_omp/ci`.
- Local script runs (macOS, heavily loaded; `--cores 4 --max-jobs ≤ 2`) as listed in the validation record.
- Not verifiable locally: CI wall time, 20/20 CI runs, green on the fixed code (pending AIUE-56).
