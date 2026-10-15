# AIUE-56 implementation review, round 2

Ticket: AIUE-56 "Fix the OpenMP Jacobian root cause(s)" (epic AIUE-8). Branch `bugfix/v9-AIUE-56-omp-jacobian-fix`,
new commits since round 1: 47e02cc and 205bd09 (code facts, `AI-layer: code-facts`) and 19116fe (validation addendum,
gate-script pairing fix, protocol driver, round-1 report and response). Inputs: the round-1 report
(`docs/reviews/AIUE-56-implementation-round1.md`) and the response (`docs/reviews/AIUE-56-implementation-round1-response.md`).

## Verdict

**REVISE**: 0 BLOCKER, 1 MAJOR, 2 MINOR.

The only open MAJOR is the unfinished part of I1-M4. It needs a short addendum to the record and no code change.

## Summary

Product code is unchanged since round 1: `git diff ba12d94..HEAD -- ppp bbb api com svr` is empty, and the
branch-wide diff touches only `ppp/omp_parallel.F90`, `.claude/context/`, `.claude/plans/` and `docs/reviews/`. The
ticket's pre-registered C1 gate still passes. I re-ran the revised gate script on two directories, and the results
match the record. I also confirmed that the new pairing check catches what the old `zip` silently passed.
- I1-M1 (code facts) is **resolved**: the context checker is clean, and the new bullet matches the code. Its rationale
  for why the parallel RHS always follows a copy names the wrong mechanism (I2-m1).
- I1-M2 (timing) and I1-M3 (pytests) are **resolved in substance**:
  - my own interleaved timing gives the same ratio of medians, 0.995;
  - I reproduced the D_only outcomes on two files in both builds;
  - but the record misdescribes how both were run, and what came out (I2-m2).
- I1-M4 is **partially resolved**: three plan step 4 items of the residual characterisation are still missing
  (size vs ulp, plate adjacency, the serial-history test).

The epic's bitwise criterion stays **not met** (residual C2, owner decision 9). It is not this ticket's gate.

## This ticket's gate vs the epic criterion

- **Ticket gate (plan "Acceptance"): PASS.** Unchanged from round 1, and re-confirmed on `new_tebox_t2_k5`
  (PASS, worst 5.62e-10) and the control `base_tebox_t4_k3` (FAIL, ratio 4e37). Both match the recorded `.gate`
  files exactly.
- **Epic Jacobian-track criterion: NOT MET.** The record's new met / not met / not run table agrees with the round-1
  table and with the run directories. Linux is still **not independently verified (environment)**.

## Findings

### BLOCKER

None.

### MAJOR

**I2-M1 (carries I1-M4). The residual characterisation is missing three of the plan's pre-registered items.**
- *Location:* `docs/reviews/AIUE-56-validation.txt`, section "residual location", compared with plan step 4
  (`.claude/plans/AIUE-56-omp-jacobian-fix.md:103-106`).
- *Problem:* Plan step 4 asks, for every residual mismatch, for:
  1. which rows and columns;
  2. which cells, and whether they are plate-adjacent;
  3. the magnitude vs `ulp(yldot)/dyl`;
  4. whether it varies between OpenMP runs;
  5. whether a serial run with a different history reproduces it.

  The addendum covers 1, 2 without the plate-adjacency verdict, and 4 (per-run counts). Item 3 and item 5 are absent.
  The response says "Added: residual characterisation", which overstates what the record contains.
- *Evidence:* `grep -n -i -E "history|ulp|plate" docs/reviews/AIUE-56-validation.txt` finds nothing. The full-problem
  hot rows `te(ix=1,iy=4)` and `te(ix=68,iy=3)` sit at the poloidal ends of the grid, so plate adjacency is a live
  question.
- *Why it matters:* Items 3 and 5 are what owner decision 9 needs. They decide whether the residual is
  round-off-level reordering (a relative deviation of about 5e-9 is what a 1-ulp `yldot` difference divided by a
  ~1e-8 relative `dyl` would give) or a state or history effect.
- *Acceptance condition:* either
  - add items 3 and 5 and the plate-adjacency verdict, reported neutrally as the plan requires; or
  - state explicitly in the record and the PR that they were not done and are handed to AIUE-55, and have the owner
    accept that in the PR.

### MINOR

**I2-m1. The context bullet names the wrong mechanism for "the parallel RHS always follows a copy".**
- *Location:* `.claude/context/openmp-jacobian.md`, the "Copy order matters" bullet (last sentence), and the last
  paragraph of the validation record.
- *Problem:* The text says that `OMPParallelPandf1=1` forces `OMPParallelJac=1` (true, `ppp/parallel.F90:30-36`), "so
  a Jacobian always comes first in the nksol sequence". That inference is wrong:
  - nksol evaluates `f(u0)` before its first Jacobian;
  - that call is serial only because `OMPPandf1Rhs` takes the parallel branch when `ijactot.gt.0`
    (`ppp/omp_parallel.F90:955`), and otherwise calls serial `pandf`;
  - `ijactot` is reset per `exmain` only when `icntnunk == 0` (`bbb/odesetup.m:6799`).

  With `icntnunk=1` (continuation, as used in time-step loops) or a Python-level `pandf1` call, the parallel RHS runs
  on the worker state from the **previous** `exmain`'s last copy. The bullet's main fact ("its workers run on what the
  last `OMPJacBuilder` copy left") is correct. The parenthetical rationale is not, and it hides the staleness case that
  the RHS track (AIUE-58) may need.
- *Acceptance:* cite the `ijactot` guard as the mechanism and note the `icntnunk=1` staleness, in the same
  `AI-layer: code-facts` style. Re-lock the reference.

**I2-m2. The addendum misdescribes how the timing and pytests were run, and the harness provenance.** None of this
changes a conclusion.
- *Timing:* The record says "interleaved, one run at a time". But the two D_only pytest runs ran concurrently with the
  timing:
  - pytests: `pytests/base-omp.txt` born 05:07:21 to `AIUE-56-omp.txt` modified 05:18:56;
  - timing: 05:07:21 to 05:20:49 (file birth/mod times).

  This overlaps timing pairs 1 to 7, which explains the 14.9 to 80 s spread on base. Also K=8, not the plan's K=10.
  My own sequential ABBA re-run (below) confirms the conclusion, but the record should state the actual conditions.
- *Pytests:* The record says "the same 3 files fail in both builds". In both builds the outcome is:
  - 116 passed, plus 1 passed with a warning;
  - 3 failed: `ineudif0/1/3`, `ValueError: operands could not be broadcast together with shapes (10,6,2) (10,6)`,
    identical in both;
  - **5 produced no pytest summary**: the `tg_atom_*` files, where the process ends after the `cftiexclg`/`istgon`
    consistency warning.

  Per-file outcomes are identical. Record these counts verbatim.
- *Provenance:* The record says "the first 9 directories in protocol.log used cf23ddf". Per `record.json`, it was the
  first 6. Two later directories are mixed: `new_full_t2_k5` 3 cf23ddf / 3 de57d59, and `new_full_t4_k30` 2 / 29. The
  difference is docs-only, so there is no effect on results.
- *Acceptance:* correct the three statements.

## Status of previous findings

| Finding | Status | Evidence |
|---|---|---|
| I1-M1 code facts / checker | **Resolved** | `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` prints `OK`, exit 0. The new bullet matches `OMPJacBuilder` (`ppp/omp_parallel.F90:681-699`: scalar bbb/com/api then pointer bbb/com/api, debug switches `OMPCopyScalar`/`OMPCopyArray`), and `OMPPandf1Rhs` (`:908-1002`) has no `OmpCopy*` call (`grep -n OmpCopy` finds only lines 650-698 plus the unused `USE` at 911). The moved references (908, 721, 959/961) and `mppl-fortran.md:69` (908-936, the free-form `USE … &` block) are correct. Both code-facts commits carry the trailer and touch only `.claude/context/`. The rationale wording is I2-m1. |
| I1-M2 timing | **Resolved** (record wording: I2-m2) | Recorded ratio of medians 0.995. My own run: 8 full-problem jac runs, 4 threads, strictly sequential, ABBA order. base 34.85 / 39.48 / 39.92 / 59.59 s (median 39.70); AIUE-56 37.3 / 57.25 / 38.61 / 40.39 s (median 39.50); ratio **0.995**. There was external load from another session's UEDGE workers (load avg 20 to 48), so paired ratios are noisy (0.68 to 1.45), but the medians agree. A priori bound: the fix copies the `Imslwrk` tables (`api/api.v`, four `nx×ny×nz` arrays plus knots and work arrays) once per Jacobian, which is negligible against 44,352 column evaluations. A > 10 % slowdown is not plausible. |
| I1-M3 OpenMP pytests | **Resolved** (counts: I2-m2) | D_only was run on both OpenMP builds, one process per file. Outcomes are identical ignoring timings (`diff` of the stripped files is empty). I re-ran `ineudif0` and `tg_atom_cftiexclg0p5` on both builds and got the same outcomes, with an identical failure message for `ineudif0`. I accept the argument for not running the other suites: with both switches 0, `OMPJacBuilder` is unreachable, and the 42-case omp0 serial check (bitwise AGREE) covers D+C, D_mols, fulltest and slab cases. |
| I1-M4 report-only deliverables | **Partially resolved** (open as I2-M1) | Added and checked: the jacrhs summary (`yldot`, `yldot_probe`, `fnrm_*` equal to serial in every run of both `*_rhs_*` dirs; Jacobian residual only), the `--itermx 3` table (matches `residual.txt` and the run outputs), the epic table and the RHS-arm C1 statement. Missing: size vs ulp, plate adjacency, the serial-history test. |
| I1-m1 RHS-only parallel never copies | **Resolved: rebuttal accepted** | My round-1 premise ("`OMPParallelPandf1=1, OMPParallelJac=0` never runs `OMPJacBuilder`") was wrong. `InitParallel` forces `OMPParallelJac=1`/`ParallelJac=1` (`ppp/parallel.F90:30-36`), and `OMPPandf1Rhs` goes parallel only once `ijactot>0`. The remaining staleness subtlety is I2-m1. |
| I1-m2 no bounds-checked run | Not done; accepted as optional | Static size check from round 1 stands. Left to the owner. |
| I1-m3 harness commit in header | **Partially resolved** | Both commits are named, but the "first 9 directories" count is wrong (I2-m2). |
| I1-m4 gate `zip`; scratch-only scripts | **Resolved** | I built a synthetic pair from `new_tebox_t2_k5` (run0 given an extra `captured[0]`). The new gate FAILs with "different Jacobians: serial ['post_exmain'] vs run ['captured[0]', 'post_exmain']", exit 1. The round-1 script (`git show ba12d94:…`) PASSes the same input, exit 0. `AIUE-56-run_protocol.sh` is committed and matches the recorded protocol. The timing and pytests drivers are still scratch-only; not raised. |

## What was checked and how

- `git log --oneline ba12d94..HEAD`, `git diff --stat ba12d94..HEAD`, and `git show --stat` per commit. Product-code
  diff since round 1: 0 lines. The branch-wide diff vs `origin/v9-develop` changes no skills, agents or hooks.
- `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`: OK, exit 0.
- Code read: `ppp/omp_parallel.F90:640-760` and `900-1010`, `ppp/parallel.F90:1-43`,
  `bbb/odesetup.m:355-375` and `6785-6802`, `bbb/pandf.m:19-21`, the `api/api.v` `Imslwrk` group, and
  `grep ijactot` across `bbb/`, `ppp/`, `svr/`.
- Gate re-runs, with `venvs/AIUE-56-omp/bin/python -I docs/reviews/AIUE-56-c1-gate.py --harness …/AIUE-49/tests/deterministic_omp`:
  - `new_tebox_t2_k5`: PASS;
  - `base_tebox_t4_k3`: FAIL;
  - both identical to the recorded `.gate`;
  - plus the synthetic pairing test above, run with the new and the old script.
- Artefacts read:
  - `v56/timing/*` (`summary.txt`, records, birth/mod times via `stat`);
  - `v56/pytests/*` (stripped and diffed, outcome counts with `awk | uniq -c`);
  - `v56/residual.txt`, `new_*_rhs_t4_k5.txt`, `protocol.log`;
  - `harness_commit` across all `record.json`.
- My runs, all under
  `/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev56r2/`:
  - `timing.sh`: 8 sequential `cli.py run --preset full --arm jac --threads 4` runs, ABBA order (log in `timing/log.txt`);
  - `pt_*` outputs: two D_only files on each OpenMP build.

  At most one of my UEDGE processes ran at a time.
- Not run: Linux (**not independently verified, environment**), a `--checkbounds` build, and the remaining pytests
  suites (argument accepted above).
