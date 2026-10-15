# AIUE-50 implementation review, round 2

Ticket AIUE-50 "Shared-state and OmpCopy coverage scan" (epic AIUE-8). Branch `feature/v9-AIUE-50-shared-state-scan`,
new commit `86ec027` (diff `4c0abd7..HEAD`). Round 1: `docs/reviews/AIUE-50-implementation-round1.md` (REVISE, 1
MAJOR, 8 MINOR). Response: `docs/reviews/AIUE-50-implementation-round1-response.md`.

## Verdict

**APPROVE** (0 BLOCKER, 0 MAJOR, 2 MINOR).

## Summary

All nine round-1 findings are resolved. I re-ran the changed scripts myself. `scan_ompcopy.py` now reports 430 + 12 =
442 guarded copies and leaves the guard column empty for the four fixed-size arrays. `scan_shared_state.py --tebox`
now runs in Jacobian mode (`yl(neq+1)=1`, recorded in the JSON), and the `PandfTiming` accumulators disappear exactly
as the RCA says. The new parallel-RHS paragraph (I1-M1) is correct. I also checked the window it describes against
the code: `OMPPandf1Rhs` falls back to the serial `pandf` while `ijactot = 0` (`ppp/omp_parallel.F90:949,989-992`), so
"between the first and the second Jacobian" is exactly the affected window. Two new minor points remain, both in
text that changed or that the main session asked me to check. `com.ttimpfe` is listed in F6 as a race, but it is an
artefact of the scan's own reset call. That entry came from my round-1 note, which was wrong. Also, one sentence in
§Mechanism M2 is contradicted by the later AIUE-55 finding.

## Findings

### BLOCKER

None.

### MAJOR

None.

### MINOR

**I2-m1. `com.ttimpfe` in F6 is a false positive of the diff scan (my round-1 note I1-m4 was wrong).**
*Location:* RCA F6 row; `tests/deterministic_omp/tools/scan_shared_state.py` column loop (the
`bbb.pandf(-1, -1, ...)` "undo" call after each column).
*What is wrong:* `ttimpfe` is written only in `timimpfj` when `xc < 0` (`bbb/pandf.m:751-761`). A local Jacobian
`pandf(xc,yc)` always has `xc >= 0`, so it writes `ttimpjf` and never `ttimpfe`. The scan reports `ttimpfe` because
it calls a full `pandf(-1,-1)` after each column to reset the state. The next column's snapshots are then compared
with a base taken before that reset.
*Evidence:* My Jacobian-mode full-problem run shows the same pattern: `ttimpfe` changes from the second sampled column on, but `areapl` already changes at iv=1. My Jacobian-mode Te-box run (`/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev50r2/ss_jac/shared_state.json`): `com.ttimpfe` changes in 24 of 25
columns, starting at iv=2 and never at iv=1, while `com.ttimpjf` changes in all 25 from iv=1. The sentinel, which runs
only `column()` without the reset, flags `ttimpjf` but not `ttimpfe`. The RCA's own TSan table lists `ttimpjf`,
`totintrv` and the `ttng*`/`ttnpg` timers inside the Jacobian loop, but not `ttimpfe`. `OMPJacBuilder` calls
`pandf(-1,-1)` only on the master and before the parallel loop (`ppp/omp_parallel.F90:680`).
*Impact:* None on the conclusions, because F6 is a benign timer row. But the diff test can attribute anything
accumulated by a full `pandf` to the local evaluation.
*Acceptance:* Remove `ttimpfe` from F6, or label it as written only by the full-RHS call (not a Jacobian-loop race).
Either take the base snapshot again after each reset, or document the artefact in the script docstring.

**I2-m2. One sentence in §Mechanism M2 is contradicted by the AIUE-55 result.**
*Location:* RCA §Mechanism M2, the sentence "The serial code shows the same history dependence: two consecutive
serial `exmain()` calls give `fnrm` ... and then ...".
*What is wrong:* AIUE-55 (P3-m3 in `AIUE-55/docs/rca/AIUE-8-omp-jacobian-nondeterminism.md`, §Residual after C1)
shows that a second `exmain` in a session gives a different Jacobian because the state changes. It is "not a history
test". AIUE-55 also shows that serial is insensitive to history outside the column loop, and that the M2 history
lives inside the serial column loop (C2: FMA contraction in `vsoree`). The rest of AIUE-50's M2 paragraph agrees with
this. The ulp noise in serial local evaluations, the 4.5e-5 ≈ ulp(yldot)/dyl entries, the threadprivate work state
carrying column history and the absence of a non-threadprivate carrier all match. Only the "two consecutive
`exmain()` calls" evidence is mis-attributed. The section is explicitly "not resolved here", so this is minor.
*Acceptance:* Drop the `exmain`-twice sentence, or reword it as a state change. A forward pointer to the AIUE-55
§Residual after C1 is enough.

## Status of previous findings

| Finding | Status | Evidence |
|---|---|---|
| I1-M1: C1 also corrupts the parallel RHS | **Resolved** | The new §Summary paragraph states it correctly, cites the `jacrhs` evidence (all 25 Te rows, 18 `sfscal` rows, iteration-0 `fnrm` 0.87e31, the extra Newton step and the two `fnrm_final` hex values, which match my round-1 log), and says the swap build matches serial on that arm. I confirmed the window independently: `OMPPandf1Rhs` uses the parallel path only `if (ijactot.gt.0)` and otherwise calls serial `pandf` (`ppp/omp_parallel.F90:949,989-992`). So the parallel RHS before the first Jacobian is serial, and the corrupted window runs from the first copy to the second, as stated. The `emcoef` exception is right (copyin at `:715`). The fix directions now require the `jacrhs` arm and one `--checkbounds` run, and the "Not covered" bullet no longer suggests the parallel RHS is unaffected. |
| I1-m1: `splinem`, `/4/` defaults | **Resolved** | `api/apip93.m:101-107` sets `nxdata_api`, `nydata_api`, `nzdata`, `nwork2`, `nwork3` and then calls `gallot` ("the first five" is right). `api/api.v:161-165` gives `k?ords` `/4/`. `bbb/odesetup.m:1130,1150` call `splinem` after `readpost`. The knot vectors keep elements 1:5 (`n+k` = 1+4). F2 is updated. |
| I1-m2: E4 mechanism | **Resolved** | §Summary and the E4 bullet now give the clip, the failed range test, `B3VAL`=0 and `emissbs`=1.0 exactly. The text says the value is deterministic per cell and that the run-to-run variation comes from the `schedule(dynamic)` mapping. |
| I1-m3: guard regex and count | **Resolved** | Re-ran `scan_ompcopy.py --src base-omp`: "bbb ... 430 behind a size guard", "api ... 12 behind a size guard", 12 order hazards, all in `Imslwrk`. In the `--md` table, `cftgtipltl`, `cftgtipltr`, `psordisold` and `iworki` now have an empty guard column. The RCA says 442 and names the four. |
| I1-m4: nksol mode | **Resolved** (see I2-m1 for the `ttimpfe` side effect) | The script sets `yl[neq] = 1.0` by default and offers `--nksol-mode`, and the JSON records `yl_neq_plus_1`. The cited `bbb/oderhs.m:2325` is in `sfsetnk`, which sets `yl(neq+1)=1` before `rhsnk`/`jac_calc_interface`. `psetnk` (`:1939`) does the same, and `OMPJacBuilder` passes `yl(1:neq+2)` through unchanged (`:704`). My Te-box runs: in Jacobian mode the diff gives the 8 `com` timers and no `PandfTiming` accumulators, and the sentinel gives `TimingPandfOn`, `nfsp` and the timers. With `--nksol-mode` the diff adds `TimePandf`, `TotTimePandf`, `TimeConvert0/1`, `TotTimeConvert0/1` and `Timefd2tra`. This matches the relabelled F6/Method text. Full-problem diff in Jacobian mode (12 columns): `bbb.areapl` (11 of 12 columns, including iv=1, so it really is the local call) plus the same `com` timers, and no `PandfTiming` accumulators. This matches F16/F6. |
| I1-m5: `emcoef` in `copyin` | **Resolved** | F15 now records the pointer association, the race from the second Jacobian on, the leak, and that AIUE-56 has to decide. |
| I1-m6: no full-problem sentinel | **Resolved** (disclosed, follow-up recorded) | A new "Not covered" bullet names the restricted-list/batched follow-up on plate-adjacent columns. |
| I1-m7: M2 range on the full problem | **Resolved** | §Summary gives 0/472, 860-1037, and 1217 entries in 26 rows, at noise level, and says that 472 is not a bound. This agrees with AIUE-55's table (860-1040, up to 1217). |
| I1-m8: documentation pointers | **Resolved** | The docstring points to "How to reproduce". The README table lists the four tools. "How to reproduce" and the `scan_shared_state.py` docstring both mention `UEDGE_OMP_RATES_DIR`. |

## What was checked and how

- Scope: `git diff --stat 4c0abd7..HEAD` shows only the RCA, the README, two scripts and the two review files. There
  is no product code, and `483d57a..HEAD` has no `.claude/` skill, agent or hook change.
  `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` returns `OK` (rc 0). Its advisory list
  includes `testing.md` → `tests/deterministic_omp/README.md`. `testing.md:7-8` cites the README only generically,
  so it needs no update.
- `scan_ompcopy.py --src base-omp --md` (base-serial venv). Output is in `/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev50r2/ompcopy.{out,md}`.
- `scan_shared_state.py --tebox --sentinel` (default Jacobian mode) and `--tebox --nksol-mode`, each from a fresh
  copy of the case with `UEDGE_OMP_RATES_DIR`, an empty `HOME` and `python -I` (base-serial). Outputs are in
  `/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev50r2/ss_jac/` and `.../rev50r2/ss_nk/`. In the Jacobian-mode sentinel, five variables returned
  `error:RuntimeError` (`bbb.ishymol`, `bbb.znucl`, `com.isnonog`, `com.nhsp`, `com.nzsp`). The perturbed switch or
  dimension makes `pandf` abort, so those five were not sentinel-tested. They are input switches and dimensions,
  and the diff test covers them. This is only an observation, not a finding, but AIUE-56 may want it stated in F8.
- `scan_shared_state.py --cols 12` (full problem, Jacobian mode, diff only, 117 s; `/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev50r2/ss_full/`): the changed set is `bbb.areapl` plus the `com` timers. `ttimpfe` again appears only from the second sampled column on (I2-m1).
- Code read: `ppp/omp_parallel.F90:645-720` (`OMPJacBuilder`), `:902-997` (`OMPPandf1Rhs`, the `ijactot` gate),
  `bbb/pandf.m:568-580,740-761` (`TimingPandfOn`, `timimpfj`), `bbb/oderhs.m:1688-1726,1883-1948,2292-2336` (the
  `yl(neq+1)` flag in `jacnw`/`psetnk`/`sfsetnk`), `api/api.v:143-172`, `api/apip93.m:95-110`,
  `bbb/odesetup.m:1128-1151`, and the writers of the F6 timers (grep over `bbb`, `com`, `api`, `ppp`).
- M2 consistency: I compared AIUE-50 §Mechanism M2 with AIUE-55's §Residual after C1 and C2. The only conflict is
  I2-m2. Note for the main session: the AIUE-55 branch is stacked on `4c0abd7` and does not contain `86ec027`. Its
  copy of the §Shared-state scan text predates this round (for example "in a few Te rows", the old F6 row and the old
  guard count), so it has to be rebased and reconciled before AIUE-55 lands.
