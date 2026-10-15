# Feature: AIUE-52 — OpenMP test flow: configuration matrix, repeats, per-arm verdicts

## Summary
**Type**: Python (test tooling; no Fortran, `.v` or `src/uedge` change)
**Complexity**: Low–medium
**Default results**: Unchanged (no product code touched)
**Packages / files**: `tests/deterministic_omp/harness/{flow.py,cli.py,test_flow.py}`, `tests/deterministic_omp/README.md`,
`.claude/context/openmp-jacobian.md`
**Branch / worktree**: `feature/v9-AIUE-52-omp-test-flow` @ `../uedge-wt/AIUE-52` (base: `feature/v9-AIUE-49-omp-harness-core`)

## Problem and solution
The AIUE-49 harness answers "does this one configuration agree with serial?" (`check`). AIUE-52 adds a driver that
runs a matrix (configuration × OpenMP arm × thread count × K repeats) against one serial reference per configuration
and gives one verdict per arm, so CI can gate on the Jacobian arm and only report the Jacobian + RHS arm.

## Decisions
- **Driver:** `harness/flow.py` (library: plan, scheduler, comparison, verdicts, summary) and a `flow` subcommand in
  `cli.py`. It reuses `runner.run_spec`, `runner.Record` and `compare.compare_records` unchanged; `worker.py` and
  `compare.jacobians()` are not touched (AIUE-47 integration happens there concurrently).
- **Configuration table** `flow.CONFIGS`: `tebox`, `full`, `te`, `ti`, `ni`, `up`, `ng`, `phi`. The phi isolation's
  preset is named once (`flow.PHI_PRESET`, currently `full_note`). `full_note` fails in serial on this case
  (`Jacobian row = 0` for phi(ix=11,iy=1)); so does phi with ni and up (tested with a temporary preset). The preset is
  being revised on the AIUE-49 branch, so `config.py` presets are not changed here, and the `phi` configuration
  reports ERROR (serial reference failed) until then. Arms: `jac`, `jacrhs`. `flow --list` prints the table.
- **Sets:** default (quick) = `tebox,full` at threads 2,4; `--all` = every configuration at 2,4,8; `--configs` and
  `--threads` override either. K = `--repeats` (default 2).
- **One serial reference per configuration**, shared by both arms and all thread counts.
- **Group verdict** (configuration, arm, threads): PASS iff all K runs agree bitwise with serial AND run 0 agrees with
  every run k (determinism); FAIL otherwise; ERROR if a run or the serial reference failed or a report is missing.
  **Arm verdict:** ERROR > FAIL > PASS over its groups.
- **Exit code:** `--gate jac` (default) | `jacrhs` | `all` | `none`. 2 if a gated arm is ERROR, else 1 if a gated arm
  FAILs, else 0. Ungated arms are reported only. An OpenMP run that crashes or stops with a solver error while the
  serial reference ran is a FAIL of its group (a finding about the build); ERROR is kept for "cannot judge" (serial
  reference failed, unreadable record). `--gate none` always returns 0 once the flow ran. Setup errors
  (unknown configuration, existing `--out`, gate on an arm not run) return 2.
- **Concurrency:** a core budget (`--cores`, default all cores) where a run takes `threads` cores (serial: 1; a run
  wider than the budget runs alone) and `--max-jobs` (default 8; a full-problem run peaks at ~1.4 GB RSS). Serial
  references and expensive configurations start first; smaller runs backfill. Results are bitwise comparisons, so
  co-scheduling changes only timing (a loaded machine is, if anything, harder on a race than an idle one);
  `--max-jobs 1` runs one at a time when a quiet machine is wanted.
- **Outputs:** `flow.json` (settings, provenance of the serial reference, timings, verdicts, every report) and
  `summary.md` (also printed): configuration, arm, threads, verdict, K agreement count, determinism, mismatching row
  equations, failing sections, first mismatch (section, equation and cell, and which comparison).
- **Memory in comparison:** records are loaded from disk per group (serial reference + run 0 + run k), never all at once.

## Tasks
1. CREATE `harness/flow.py`. VALIDATE: `flow --configs tebox` on the OpenMP build.
2. UPDATE `harness/cli.py`: `flow` subcommand, docstring. VALIDATE: `flow --list`, existing tests.
3. CREATE `harness/test_flow.py`: verdicts, exit codes per arm and gate, nondeterminism, harness errors, setup errors,
   scheduler budget, all with fake runs. VALIDATE: `python -m pytest tests/deterministic_omp/harness`.
4. Acceptance runs (`docs/reviews/AIUE-52-validation.txt`): `--all --repeats 2` (both arms, 2/4/8), Te box at 4 threads
   timing, default quick set.
5. UPDATE `tests/deterministic_omp/README.md` (usage). Separate commit `AI-layer: code-facts`:
   `.claude/context/openmp-jacobian.md` "Verifying" section. VALIDATE: `check_context_refs.py --changed origin/v9-develop`.

## Acceptance criteria (ticket)
- [ ] Jacobian arm fails for the Te box and the full problem with localised Te mismatches; Ti/ni/up/ng pass — task 4
- [ ] Te-box command < 2 min at 4 threads — task 4
- [ ] Per-arm exit codes tested — task 3
- [ ] Usage in README and `openmp-jacobian.md` — task 5
