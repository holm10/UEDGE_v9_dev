# AIUE-58 RHS RCA — implementation review, round 1

Ticket AIUE-58 "RHS RCA (bonus)" (epic AIUE-8). Branch `feature/v9-AIUE-58-omp-rhs-rca`, commits `dc96bc5`, `ee291a4`
on `8277210`. Reference: the ticket's acceptance criteria (RCA RHS section with root causes or a known-limitation
statement with evidence; owner decision prepared) and the scope list in the ticket.

## Verdict

**REVISE**

## Summary

R1 holds. The `hcyn`/`feixy` chunk-range mismatch is real, its geometry matches the 26 rows, the carrier search singles
out `hcyn`, and I reproduced the scratch fix: bitwise equal to serial with a different seed and preset. R4 is shown by
the two lldb traces. R2's observation is sound. The refutations are supported for this single-null deck with the
default chunking, as stated. R3's mechanism is wrong. Forthon's generated `apisetarraypointer<var>` re-points every
worker's pointer whenever `gallot` reallocates, so after `ueinit` the workers do not point at the freed block. They
point at private copies of the new, still-unfilled block, and this happens for all 12 `Imslwrk` arrays, not only
`emcoef`. A discriminating run refutes the "dangling `copyin` pointer" model. So the R3 fix direction ("drop `emcoef`
from `copyin`") would not fix R3, and the jac-arm "use-after-free write" paragraph is wrong. The RCA also does not say
plainly that only R1's fix was built and tested, and the refresh points for the owner's chosen option (A plus the
AIUE-61 Q6 referral) are underspecified.

## Findings

### BLOCKER

**I1-B1: R3's mechanism, its fix direction and the jac-arm "R3 relative" are wrong.** Location: §RHS RCA → Root causes, row
R3; "Remaining issues", 4th bullet ("Static, not demonstrated: the jac arm has an R3 relative…"); Decision table,
option A (R2+R3 cell) and option C ("Leaves a use-after-free"); status line ("R3 a dangling `emcoef` association").

*What the RCA claims:* `copyin(emcoef)` leaves each worker's `emcoef` associated with the master's array. `ueinit` →
`splinem` → `gallot("Imslwrk",0)` frees and reallocates the master's array, so the workers dangle at freed memory
(use-after-free) until the next `copyin`. Fix: drop `emcoef` from `copyin` and refresh per `exmain`.

*Evidence against it (code):*
- Forthon's `gallot` (`venvs/AIUE-56-omp/.../Forthon/Forthon.h:1241-1262`) runs `Forthon_freearray` (old block), then
  `ForthonPackage_PyArrayFromFarray` (new block), then calls `setarraypointer` **before** it fills the array with
  the init value (`:1262-1270`). Only after that does `splinem1` fill the master's tables.
- The generated `apisetarraypointeremcoef` (`AIUE-56/build/temp.macosx-26.3-arm64-cpython-313/api_p.F90:1222-1252`):
  copies `p__` (the new block, not yet filled) into the `SAVE`, threadprivate `pcopy__`, then
  `!$omp parallel copyin(pcopy__)`, and on `tid>0` sets `emcoef => pcopy__`. Every worker is re-pointed to its own
  copy of the unfilled block, inside the `gallot` call, before any worker code runs. There is no window in which a
  worker points at the freed block. Forthon generates the same routine for every `+threadprivate` dynamic array:
  `xdata_api`, `ydata_api`, `zdata`, `fdata_api`, `work2`, `work3`, the three knot arrays, `emcoef`, `z1coef` and
  `z2coef` (`api/api.v:148-172`).

*Evidence against it (run, check 1 of 2):* `te` preset, AIUE-56 OpenMP venv, 4 threads, jacrhs, `ftol=1e20`. Script
`/tmp/aiue58-review/scripts/r3_discriminate.py`, output `/tmp/aiue58-review/run_r3/r3.json`.
- I held Python references to all 12 `Imslwrk` arrays across `bbb.ueinit()`. `Forthon_getarray` increfs `pya`, so the
  old blocks stay alive and keep their valid tables. All 12 arrays moved, and the old and new knots and `emcoef` were
  `array_equal`.
- Under the RCA's model the workers read the old, alive, identical `emcoef`, so P must equal S. **Observed: P ≠ S in
  1162 Te rows, up to 3.7e34 relative**, with 78,876 lines of SLATEC `B1VAhL` "NO LEFT LIMITING VALUE" errors starting
  after the `ueinit` output. Those errors mean invalid **knots** on the workers, which the emcoef-only model cannot
  produce. The author's own `te_t4_ueinit` log has none: there the new blocks probably reused the freed ones, so the
  unfilled copies happened to hold the old values. That is also the reviewer-model explanation of the "survivors
  near serial" and of the full-problem "same address, 1 row" observation.
- Reassigning all 12 arrays from Python (`setattr`, which runs `setarraypointer` with the filled master data) brings
  it down to 889 rows ≤ 5.5e-9 relative. Workers are fixed by a copy, not by `copyin`. The remaining 889 rows show
  that other worker state is stale after `ueinit` too (not localised).

*Consequences:*
1. R3 is an uninitialised read: workers hold copies of an allocation-time block. It is not a use-after-free.
2. Dropping `emcoef` from `copyin` does not fix R3. The fix is a refresh of all worker state (at least every
   `Imslwrk` array; given the 889 rows, the full `OmpCopy*`) **after** `ueinit` and before the first
   `OMPPandf1Rhs` of the `exmain`. A refresh "at the start of each `exmain`" (R2 row wording) placed before `ueinit`
   would leave R3 in place.
3. The jac-arm paragraph is wrong. After `gallot` the workers point at their own `pcopy__`, so the first
   `OmpCopyPointeremcoef` of the next Jacobian writes into the workers' own buffers, not into a freed block.
4. With the mechanism corrected, AIUE-50 F15 / F16 "`emcoef` `copyin` (benign)" (this RCA's fix-tickets row) and
   AIUE-60 plan A6 ("redundant; benign") stand. The current R3 text contradicts them inside the same document.
5. The same mechanism also bears on R2: see I1-m3.

*Acceptance:* the R3 row, the jac-arm bullet, the status line, options A and C and the fix-tickets row describe the
`gallot` → `setarraypointer` copy mechanism. They cite the Forthon and generated-code lines and this (or an equivalent)
discriminating run. The R3 fix direction is a full worker refresh after `ueinit`, and dropping `copyin` is at most
hygiene. The text is consistent with F15/F16 and AIUE-60 A6.

### MAJOR

**I1-M1: The RCA does not say plainly which fixes were tested.** Location: status line; §Scratch test; Decision
table option A.

I confirm the coordinator's reading. Only R1's fix was built and tested (scratch `AIUE-58-hcyn`). The R2, R3 and R4
fix directions were neither built nor run, and R2 and R3 were not re-run on the R1 build ("R2 and R3 were not re-run on
this build; by mechanism the change does not touch them").

The RCA does not imply the R2–R4 fixes are shown, but nowhere says so either. Option A's "Expected bitwise equal to
serial on the RHS for the default chunking (R1 fix shown…)" reads close to a demonstrated outcome. The R1 test itself
covers only fixed inputs, `same`/`pert`/`back`, `full` and (my rerun) `ti`. And I1-B1 shows the R3 fix as written
would not work.

The status line's "with C1-RHS they explain every RHS-arm failure seen so far" rests on one lldb trace per build (see
I1-m2) and on R3's now-refuted mechanism.

*Acceptance:* one plain sentence in the status line and in the Decision section: only R1's fix was built and shown
(probe bitwise and `ti --itermx 5` 3/3, default chunking, fixed inputs); the R2, R3 and R4 fixes are untested
proposals; whether option A restores correctness is to be shown in AIUE-59 with the probe (`pert`, `afrac`, `atau`,
`ueinit`) and the two-`exmain` sequence. "Explain every" is scoped to what was traced.

**I1-M2: The refresh points for the chosen scope are underspecified, and the Q6 referral and AIUE-61 interaction
are missing.** Location: Decision for the owner; R2 row, fix-direction column.

The owner chose A plus the AIUE-61 Q6 post-Jacobian worker reset (coordinator, this round). The options do not cover
Q6. Option A refreshes "once per `exmain`", which:
- (a) must sit after `ueinit` (I1-B1);
- (b) does not cover later Jacobians inside the same `exmain`, after which the workers hold whatever the last
  columns of their chunks left (schedule-dependent);
- (c) under AIUE-61's design (fresh full `pandf` at each chunk start, dynamic schedule, 64 chunks) leaves a worker
  that drew no chunk with its old state. So AIUE-61's per-chunk reset almost gives Q6, but not on the idle-worker path.

There is also evidence that matters for the cost discussion. With R1 fixed, the probe at fixed inputs is bitwise
equal after perturbations, so for this deck and the default chunking the RHS does not depend on stale worker *state*.
In that configuration Q6 is defence in depth. It is needed for correctness only for inputs and reallocations (R2/R3)
and for `Nxchunks>1`, where R1-class reads remain.

*Acceptance:* the Decision section records the owner's decision (A + Q6) and defines the refresh points for AIUE-59:
after `ueinit`/before the first parallel RHS of each `exmain`, and after each OpenMP Jacobian (Q6), including the
idle-worker case under AIUE-61. It says what AIUE-61's per-chunk reset already covers, and names one owner for dropping
`emcoef` from `copyin` (AIUE-59 option A, AIUE-60 A6 and AIUE-61 all touch it).

### MINOR

**I1-m1: The scratch R1 fix also widens the `hcxi`/`hcyi` `+=` updates.** `bbb/pandf_plasma_energy.m:1496` (scratch).
The widened loop also runs `hcxi(ix,iy) += …hcxn` and `hcyi(ix,iy) += …hcyn` (`:1522-1527`) at `ix = i6pomp = xe+1`.
Those arrays are zeroed only over `i1momp..i6omp` (`:1272-1278`), so on a worker they accumulate at `xe+1`. This is
benign here: `conxi` runs over `i1momp..i5omp` (`:75-76`), `conyi` over `i4omp..i8omp` (`:135-136`), and nothing reads
`hcxi`/`hcyi` at a neighbour index (grep). That matches the bitwise probe. Serial is unchanged (`i6pomp = i6omp` in
`initialize_ranges`, `bbb/pandf.m:226-227` region, both the full and the local path). *Acceptance:* the RCA notes this,
so that AIUE-59 computes `hcyn` to `i6pomp` without the `hcxi`/`hcyi` updates, or resets them over the same range.

**I1-m2: R4's attribution to all AIUE-54 SIGSEGVs is inferred.** The chain (`localjacbuilder_` `parallel.F90:296` →
`kaboom_` → `cstrfromfstr` → `_PyObject_Malloc` on worker thread #3) is shown in `lldb_base_te.txt` (one base `te`
re-run) and `lldb_te.txt` (one nofma sequence). "The AIUE-54 pre-fix SIGSEGVs are the same chain" (`te_phi`, other
thread counts) and the 5 other exit-139 sequence runs are inferred. *Acceptance:* label them inferred, as is already
done for the RuntimeError.

**I1-m3: R2 needs Forthon's assignment semantics.** A whole-array `setattr` of a dynamic threadprivate array goes
through `setarraypointer` (`Forthon.h:823`) and so copies to the workers at assignment time. In-place and indexed
writes and threadprivate scalars do not. `continuation_solve` uses both paths (`src/uedge/rundt.py:857-860`), so "changes
a user variable exactly like this" holds only for indexed variables and scalars. Fortran-side writes (`ueinit`'s
`afrac = afracs`) are always master-only, as stated. *Acceptance:* one sentence in R2 and in the static input list.

**I1-m4: The scratch patch is not a committed record.** The R1 scratch change lives only as an uncommitted edit in
`uedge-wt/AIUE-58-hcyn`. The provenance in `hcyn_*` records `source_dirty: true` but not the diff. *Acceptance:* commit
the one-line patch (`git -C uedge-wt/AIUE-58-hcyn diff`) under `docs/rca/AIUE-8-data/rhs/`.

## Not independently verified (environment)

- Linux (R1–R4 "platform-independent by mechanism"): not measured by the author, not checked here.
- R1 at 1, 2 and 8 threads, `Nxchunks=4`, full-problem `--itermx 5`, the `ti`/`te` sequences, the full-problem
  Jacobian re-check (3/3 at load 7–11) and the 6/8 SIGSEGV count: checked against the committed records only (numbers
  match, e.g. iteration-0 `fnrm` 1.327538656680116 / 1.326787171822271 / 1.327580678916788, exit 139 in 6 of 8 `te`
  jacrhs runs). Not rerun, within the 2-run budget.
- R2 probe counts (1410–2538 Te rows): from records. The mechanism was checked in code (`afrac`/`atau` `+threadprivate`
  at `bbb/bbb.v:3920,3922`; `ueinit` `afrac = afracs`, `bbb/odesetup.m:1617-1621`).
- Double null, `isimpon=2`, TSan: not run by the author (stated); not run here.

## What was checked and how

- Diff `8277210..HEAD`: RCA section plus records and scripts only; no `.m`/`.v`/`.F90`/build/`.claude/` change.
  `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`: **OK**.
  `uv run .claude/hooks/change_kind.py --range 8277210..HEAD`: **OK** (artifacts + `tests/` scripts, ticket branch).
- R1 code: `feixy` reads `hcyn(ix2,iy)` and `hcyn(ix4,iy1)` (`bbb/pandf_plasma_energy.m:476-477`) over
  `i1momp..i6omp`; `hcyn` loop `:1494-1530`. Chunk ranges in `OMPinitialize_ranges2D`
  (`ppp/omp_parallel.F90:860-872`: `i6omp = xe`, `i6pomp = xe+1`). Serial `i6pomp = i6omp` (`bbb/pandf.m`
  `initialize_ranges`). Chunk geometry (`MakeBulkChunks` `:63-76`, `MakeXptChunks` X-cut `ixpt..ixpt+2`) matches the
  26 rows (ix 8, 12, 52). Carrier record: `sufficient = ["bbb.hcyn"]`, the only reducing variable. The fix diff in
  `uedge-wt/AIUE-58-hcyn` is the stated one-liner (plus I1-m1).
- **Run 2 of 2** (R1 fix): committed `rhs_probe.py` via `run_probe.sh`, venv `AIUE-58-hcyn`, `ti` preset, 4 threads,
  seed 7, steps `same, pert:1e-8, pert:1e-3, back, pert:1e-3`. Every step `ndiff = 0` (36 signed zeros at `yl0`),
  against the committed AIUE-56 `ti_t4_r0`, which has 26/16/6 Ti rows. Output `/tmp/aiue58-review/run_hcyn_ti/probe.json`.
- **Run 1 of 2** (R3 discrimination): see I1-B1.
- R3 code path: `api/apip93.m:101-107` (`gallot("Imslwrk",0)` in `splinem`), `bbb/odesetup.m:1130,1150`; `copyin`
  at `ppp/omp_parallel.F90:721` (AIUE-56). The copy order (`OmpCopyScalar*` before `OmpCopyPointer*`, `:687-698`) is
  consistent with AIUE-56. Generated `OmpCopyPointeremcoef` (`api_p.F90:366-380`) and
  `apisetarraypointeremcoef` (`:1222-1252`). Forthon `gallot`/`getarray`/`setattr` in `Forthon.h`.
- R4: `ppp/parallel.F90:292-296` (`xerrab("")` in the parallel loop); both lldb files show the chain.
- Probe method: `same` at `yl0` gives 0 differences, which anchors `bbb.ffun` against `bbb.pandf(-1,-1)` as a fair
  baseline. Serial `pandf` at a perturbed `yl` is what a correct chunked RHS must reproduce, since the chunks only
  partition rows. "Earlier checks green" holds: the one-evaluation check runs at the Jacobian's `yl`, where the workers
  were just refreshed.
- Refutations: core-ring sums `ixc1 = ixpt1+1 … ix_fl_bc = ixpt2` (`bbb/pandf_boundary.m:1351-1361,1487-1497`) lie
  inside the iy=0..1 chunk `ixpt1-1 … ixpt2+2`. Signed-zero reasoning (`+0 + (−0) = +0`) is correct. 15th-digit
  `fnrm` is labelled inferred. The full-problem C2 re-check is against the same AIUE-56 build (0/30 under load), K=3,
  and states its limits.
- Cross-ticket: AIUE-60 plan A6 (`uedge-wt/AIUE-60/.claude/plans/AIUE-60-omp-races.md:32,232`) and AIUE-50 F15 (RCA
  `:779`); see I1-B1 item 4 and I1-M2.
