# AIUE-56 implementation review, round 3 (final before escalation)

Ticket: AIUE-56 "Fix the OpenMP Jacobian root cause(s)" (epic AIUE-8). Branch `bugfix/v9-AIUE-56-omp-jacobian-fix`.
New commits since round 2: 4066277 (validation addendum, round-2 report and response) and ebe8f3c (code facts,
`AI-layer: code-facts`). Inputs: `docs/reviews/AIUE-56-implementation-round2.md` and
`docs/reviews/AIUE-56-implementation-round2-response.md`.

## Verdict

**APPROVE**: 0 BLOCKER, 0 MAJOR, 3 MINOR.

The MINORs are about wording in the validation record. They are optional, but I3-m1 and I3-m2 would make the
report to the owner (decision 9) more accurate, so I recommend fixing them before the PR.

## Summary

Product code is unchanged since round 1: `git diff ba12d94..HEAD -- ppp bbb api com svr` is 0 lines. The two new
commits touch only `docs/reviews/` and `.claude/context/openmp-jacobian.md`, and the context checker is clean.

I recomputed the round-2 residual characterisation independently from the run records with
`harness.compare.matrix_mismatch`. Every number in the record reproduces exactly: 14202 entries, the cell
histogram, 3266 plate-window entries, ulp ratio median 1 / p90 9 / max 83.6, and Te box 0.5 at cell (4,20). The
"lower bound" claim points the right way. But it is a factor of 2 low, and that factor is known, not a loose bound
(I3-m1). The plate verdict is correct for the record's own definition. It leaves out that 93 % of the entries sit in
divertor-leg cells, and it calls the Te-box cell "far from any plate" when it is 4 cells from the inner plate
(I3-m2). The history item is covered by a valid pointer to the AIUE-55 emulation.

The corrected context sentence matches `ppp/omp_parallel.F90:955` and `bbb/odesetup.m:6799`.

The ticket gate still PASSES. The epic bitwise criterion is still **NOT MET** (C2, owner decision 9).

## This ticket's gate vs the epic criterion

- **Ticket gate (plan "Acceptance"): PASS.** No product code or gate input has changed since round 2, so the
  round-2 re-runs still hold:
  - `new_tebox_t2_k5` PASS;
  - control `base_tebox_t4_k3` FAIL;
  - both identical to the recorded `.gate` files.
- **Epic Jacobian-track bitwise criterion: NOT MET.** About 1,000 to 2,400 Te-row entries per full-problem run, and
  0 to 2 per Te-box run, still differ from serial. That residual is C2 (in-loop history, the AIUE-55 RCA). The exit
  decision belongs to the owner (decision 9) and is not this ticket's gate.
- Linux: still **not independently verified (environment)**.

## Findings

### BLOCKER

None.

### MAJOR

None.

### MINOR

**I3-m1. The ulp ratio is reported as a "lower bound", but the true value is known: twice the recorded value. The
interpretation also covers only the median.**
- *Location:* `docs/reviews/AIUE-56-validation.txt`, section "Residual: size, location, history", the two
  `|dJ| * dyl / ulp` lines and the "Size:" bullet.
- *Evidence:*
  1. `jac_calc` uses `dyl = del*(|yl| + dylconst/suscal)` (`bbb/oderhs.m:1156`).
  2. With the default `iscolnorm=3`, `suscal = 1/max(|yl|, floor)` (`bbb/odesetup.m:2470-2476`,
     `bbb/bbb.v:1284`). So `|yl| = 1/suscal` in every column whose `suscal` is not floored: all 25 Te-box columns,
     and every full-problem column except those with `suscal = 1e7`, which make up fewer than 428 of 44352 columns.
  3. The true `dyl` is therefore `2·del/suscal`: exactly twice the `del·dylconst/suscal` the record uses.
  4. My recomputation gives:

     | Case | Recorded (lower bound) | With the true `dyl` |
     |---|---|---|
     | Te box | 0.5 | **1.0** (exactly 1.00000001) |
     | Full problem, median | 1 | **2** |
     | Full problem, p90 | 9 | **18** |
     | Full problem, max | 83.6 | **167** |

     Using `ulp` of the perturbed residual instead of `yldot` changes nothing.
  5. The definition writes `|dJ|`. The value that actually reproduces the numbers is the unscaled difference, i.e.
     `jac_post × suscal(col)`, because the sfsetnk `jac` is column-scaled by `1/suscal` (`bbb/oderhs.m`, `sfsetnk`,
     `amudia`).
  6. The "Size:" bullet ("about one ulp ... i.e. finite-difference noise from a 1-ulp difference") fits the Te box
     exactly. It does not describe the full-problem tail, which reaches tens to ~170 ulp.
- *Why it matters:* this is the size statement the owner will read for decision 9. It does not change the
  conclusion that the residual is round-off-level finite-difference noise. But "≈1 ulp, lower bound" undersells a
  distribution with median 2 ulp and p90 18 ulp.
- *Acceptance:* state the factor 2 and why (`iscolnorm=3` gives `|yl| = 1/suscal`). Give the corrected numbers, or
  keep the current ones and say they are exactly half the true value. Say that `dJ` is unscaled. Mention the tail in
  the bullet.

**I3-m2. The location verdict leaves out the divertor-leg concentration and misplaces the Te-box cell.**
- *Location:* same section, the "Location:" bullet and the `nx=71` / `nx=7` labels.
- *Evidence:*
  1. **Grid.** `case/gridue.hdf5` gives `nxm=70`, `ixpt1=10`, `ixpt2=50`, `iysptrx1=12`, and `igyl` spans
     ix 0..71. So `nx=70`, not 71.
  2. **Full-problem window.** The script's window (`ix<=2` or `ix>=69`) is symmetric and correct, but the label
     "ix>=nx-2, nx=71" is wrong. With the true `nx`, the written formula would also include the second-hottest
     cell, (68,3), with 894 entries.
  3. **Te-box label.** The Te box is a subset of the same grid (ix 3..7, iy 18..22). The label `nx=7` treats the
     box as its own grid.
  4. **Te-box placement.** Cell (4,20) is in the inner divertor leg (ix ≤ ixpt1 = 10), 4 cells from the plate guard
     cell. "Far from any plate" is not accurate. "Outside the 3-cell plate window" is.
  5. **Leg concentration (omitted from the record).** With my own script, 13279 of 14202 entries (93.5 %; 30 runs:
     46514 of 50262, 92.5 %) and 60 of 71 distinct cells are in divertor-leg cells (ix ≤ 10 or ix > 50). The legs
     are only 32 of the 72 poloidal positions. The 11 core-region cells are all at iy ≥ 23, near the outer wall.

  A strong leg concentration fits the AIUE-55 carrier: `vsoree` is the ionisation/recombination energy source,
  which is largest where the neutral density is high. Reporting it neutrally strengthens the record.
- *Acceptance:* fix the `nx` labels. Replace "far from any plate" with the actual placement. Add the divertor-leg
  fraction to the location verdict.

**I3-m3. The record's parenthetical "correct state after this fix" for the `icntnunk=1` parallel RHS is not
demonstrated.**
- *Location:* validation record, "C1 on the RHS arm" paragraph, last sentence.
- *Problem:* No run on this branch exercises `icntnunk=1`, or a Python RHS call after an earlier `exmain`, with
  `OMPParallelPandf1=1`. The fix guarantees only that the copy order is right at the time of the last
  `OMPJacBuilder`. It does not guarantee that the worker copies are still current after the user changes anything
  set outside `pandf` between `exmain` calls. The context bullet in `openmp-jacobian.md` correctly says
  "whatever worker state the previous Jacobian left" and makes no correctness claim.
- *Acceptance:* qualify the parenthetical (for example "copied in the right order; not tested with `icntnunk=1`"),
  or drop it and leave the case to AIUE-58.

## Status of previous findings

| Finding | Status | Evidence |
|---|---|---|
| I2-M1 residual size vs ulp, plate adjacency, serial history | **Resolved** (wording: I3-m1, I3-m2) | **Size (item 3):** added. My independent script (`rev56r3/ulp.py`, `harness.compare.matrix_mismatch`, serial vs run0..9) reproduces exactly: `new_full_t4_k30` 14202 entries (value 3756, only-a 10421, only-b 25; the sum matches the 10 per-run counts in `new_full_t4_k30.txt`), median 1 / p90 9 / max 83.6; `new_tebox_t4_k30` 13 entries, all 0.5. The "lower bound" direction is correct, since `dyl ≥ del·dylconst/suscal`; it is exactly a factor 2 low (I3-m1). **Plate adjacency:** added. 3266 entries and 71 distinct cells reproduce; Te box 0 of 13, all at (4,20). Omissions and labels: I3-m2. **History (item 5):** answered by pointer. I checked it: `docs/rca/AIUE-8-omp-jacobian-nondeterminism.md` on `feature/v9-AIUE-55-omp-jacobian-rca` (§P3-m3 and M2 items 1 to 5) reports that serial `jac_calc` emulation is bitwise equal to exmain, that fresh-per-chunk starts reproduce the OpenMP Te-box residual exactly, that `vsoree` is the carrier, that `-ffp-contract=off` gives bitwise on 3/3 + 3/3, and that replay with R=`ubw` gives 0 mismatches on the full problem. A serial run with the workers' history does reproduce the residual, which is what item 5 asks. Accepted. |
| I2-m1 context bullet mechanism | **Resolved** | `ppp/omp_parallel.F90:955` `if (ijactot.gt.0)` selects the parallel loop, and `:995-997` otherwise calls serial `pandf`. `bbb/odesetup.m:6799` `if (icntnunk == 0) ijactot = 0`. `:6793` requires `ijactot>1` for `icntnunk=1` with nksol, so in that case the first RHS is parallel on the previous workers' state. `ppp/parallel.F90:30-36` forces `OMPParallelJac=1`. The bullet now states exactly this. Commit ebe8f3c touches only `openmp-jacobian.md` and carries `AI-layer: code-facts`. The checker is clean. |
| I2-m2 run descriptions | **Resolved** | The record now states K=8 (plan: 10), that timing overlapped the pytests for pairs 1 to 7, 117 pass (116 + 1 with a warning) / 3 fail / 5 with no summary in both builds, and 6 directories on cf23ddf with two straddling. All agree with what I found in round 2. |
| I1-m2 no bounds-checked run | Left to the owner (unchanged) | — |

## What was checked and how

- `git log --oneline 19116fe..HEAD` and `git show --stat 4066277 ebe8f3c`: docs and context only.
  `git diff ba12d94..HEAD -- ppp bbb api com svr | wc -l` gives 0. No skills, agents, hooks or settings are changed
  on the branch (`git diff --name-only origin/v9-develop..HEAD`).
- `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`: `OK`, exit 0. It lists
  `mppl-fortran.md`, `openmp-jacobian.md` and `CLAUDE.md` for re-reading. The cited lines are still correct.
- Code read:
  - `bbb/oderhs.m:1012-1241` (`jac_calc`, `dyl` at :1156) and `:2292-2350` (`sfsetnk`, column scaling via `amudia`);
  - `rhsnk` entry (`:1000`, unscaled `pandf`);
  - `bbb/odesetup.m:1941` and `:2426-2484` (`set_var_norm`);
  - `bbb/odesetup.m:6790-6800`;
  - `ppp/omp_parallel.F90:940-1002`, `ppp/parallel.F90:25-40`;
  - `bbb/bbb.v` (`iscolnorm`, `del`, `dylconst`, `jaccliplim`, `dtreal` not threadprivate);
  - harness `worker.py:160-230` and `compare.py`.
- Independent recomputation, scripts in
  `/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev56r3/`:
  - `ulp.py`: ulp ratio, recorded and corrected definitions, and plate window;
  - `loc.py`: equation of each row, divertor-leg and separatrix split, over runs 0..9 and 0..29.

  Grid parameters come from `AIUE-49/tests/deterministic_omp/case/gridue.hdf5`. Record metadata
  (`post_exmain_from=sfsetnk`, iteration 0) comes from `record.json`.
- AIUE-55 RCA read with `git show feature/v9-AIUE-55-omp-jacobian-rca:docs/rca/AIUE-8-omp-jacobian-nondeterminism.md`.
- No UEDGE runs (budget: read-only plus Python over the records).
