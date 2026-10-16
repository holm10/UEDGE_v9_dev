# AIUE-50 implementation review, round 1

Ticket AIUE-50 "Shared-state and OmpCopy coverage scan" (epic AIUE-8). Branch `feature/v9-AIUE-50-shared-state-scan`,
diff `483d57a..HEAD` (fa4fd42, 4c0abd7). Reviewed outputs: `docs/rca/AIUE-8-omp-jacobian-nondeterminism.md`
§Shared-state scan, and `tests/deterministic_omp/tools/{scan_ompcopy,scan_saved_locals,scan_shared_state,tsan_summary}.py`.

## Verdict

**REVISE** (0 BLOCKER, 1 MAJOR, 8 MINOR).

## Summary

The root cause C1 holds up. I read the generated `OmpCopyPointerxdata_api`, `OmpCopyScalarapi` and
`apisetarraypointer*` code and it does what the RCA says. My own static scan of all ten generated `<pkg>_p.F90` files
finds exactly the same 12 copy-order hazards, all in `api` `Imslwrk`, and none in any other package. I reproduced the
key evidence myself: the unmodified build gives a Te-box Jacobian of order 1e43, the copy-order swap alone gives
serial `fnrm`/nnz/sparsity on the Te box with only the M2 round-off entries left, and a second `exmain` gives the clean
second-call `fnrm` (E2). An emulation of the worker state makes `emissbs` return exactly 1.0 instead of about 1e-35.
The one MAJOR finding is about how far C1 reaches. It also corrupts the **parallel RHS** (`OMPParallelPandf1=1`),
because `OMPPandf1Rhs` runs on whatever worker state the last Jacobian copy left behind. On the unmodified build this
gives an iteration-0 `fnrm` of 8.7e30, which pushes nksol into an extra Newton step and changes the final state. The
RCA does not say this, and the fix ticket AIUE-56 has to validate against it. The other findings are minor
inaccuracies in the explanation, the counts and the scripts.

## Findings

### BLOCKER

None.

### MAJOR

**I1-M1. C1 also corrupts the parallel RHS (and so the solution), not only the first Jacobian. The RCA's impact
statement is incomplete.**
*Location:* RCA §Summary ("Only after the first copy do the workers hold the right scalars, so later Jacobians in the
same process are clean"), §E4, §Not covered (bullet 4).
*What is wrong:* `OMPPandf1Rhs` (`ppp/omp_parallel.F90:900-997`) calls no `OmpCopy*` routine. Its workers evaluate
`pandf` on the threadprivate state that the last `OMPJacBuilder` copy left behind. After the first Jacobian the
workers hold the correct `Imslwrk` bounds but tables that are still mostly zero (only element 1, or 1:5 for the knots;
`emcoef` is the exception, because `copyin` re-associated it with the master's array). So every parallel-RHS
evaluation between the first and the second Jacobian computes `emissbs = 1` on the worker chunks.
*Evidence (Te box, 4 threads, harness `--arm jacrhs`):*
- Unmodified `base-omp`: `yldot` and `yldot_probe` differ in all 25 Te rows; `sfscal` differs in 18. The run log shows
  `OMP iter= 0 fnrm= 0.8703667898605588E+31`, followed by `OMP iter= 1 fnrm= 0.2014...`. With `ftol=1e20` the serial
  run takes no Newton step, but this run takes one, and `fnrm_final` differs (`0x1.9c7df3d50ba02p-3` against serial
  `0x1.49db83f93d961p-2`). In this arm the defect changes the result, not only the preconditioner.
- `AIUE-50-swap`: `yldot`, `yldot_probe`, `sfscal`, `fnrm_final` and `fnrm_printed` all match serial. Only the 2 M2
  entries in row te(4,20) remain. So the swap also fixes the RHS arm.
*Acceptance:* §Summary/§E4 say that with `OMPParallelPandf1=1`, C1 corrupts the parallel residual (Te rows) from the
first Jacobian until the second one and can change the converged state. The "Not covered" bullet is narrowed so it no
longer reads as if the parallel RHS were unaffected. The suggested fix directions for AIUE-56 name the `jacrhs` arm as
a required validation arm.

### MINOR

**I1-m1. Wrong routine and default in the C1 statement.** §Summary says "`readpost` sets them on the master thread only
(`api/apip93.m:102-108`)" and that the DATA default of all bound scalars, including `k?ords*`, is `/1/`. The bounds are
set in `splinem` (`api/apip93.m:101-107`, called from `ueinit`, `bbb/odesetup.m:1130,1150`), not `readpost`, and
`kxords_api`/`kyords_api`/`kzords` default to `/4/` (`api/api.v:161-165`). That is also why the knot vectors keep
elements 1:5, not "just element 1" (E1 shows `xknots_api ... first=6`, which agrees). F2 has it right; make §Summary
match.

**I1-m2. E4 gives the wrong reason for the corrupted values and their variation.** E4 says "`B3VAL` on all-zero knot
vectors works with degenerate intervals". On the worker, `zdata(nzdata)=0`, so `emissbs` clips `zuse` to 0, below
`TZ(1)`. `B3VAL` then fails its range test, goes to 9999 and returns 0, and `emissbs = 10**0 = 1.0` exactly (true value
1.9e-35 at te(4,20); emulation below). The value is deterministic per cell. Run-to-run variation comes only from the
`schedule(dynamic)` column-to-thread mapping. Correct the bullet. The conclusion does not change.

**I1-m3. Guard count and guard column are wrong.** The RCA says "446 copies are behind a `size >= declared` guard".
The generated code has 442 guarded copies (bbb 430 of 433, api 12 of 13). The four fixed-size arrays
(`cftgtipltl`, `cftgtipltr`, `psordisold`, `iworki`) have no guard. `scan_ompcopy.py` (`guard = re.search(r"^if
\((.*)\) then\s*$", sub, re.M)`, line 109) picks up `if (tid.gt.0) then` as their "guard". Its summary prints 433 and
13, and the table shows `tid.gt.0` in the guard column for those rows. Fix the regex so it matches only `.le.size(`,
and correct the number.

**I1-m4. `scan_shared_state.py` runs local `pandf` in nksol mode, not Jacobian mode.** The script passes `bbb.yl` as
it is after `exmain`, so `yl(neq+1) = -1`. `jac_calc`/`OMPJacBuilder` run with `yl(neq+1) = 1`
(`bbb/oderhs.m:1716`). This changes `TimingPandfOn` (`bbb/pandf.m:573-579`), `add_timestep` (`:739`), the `ishosor`
volume averaging (`bbb/pandf_plasma_continuity.m:714`) and the `ismcnon` paths (`bbb/pandf_jacobian.m:126`). For this
deck (`ishosor=0`, `ismcnon=0`, `dtreal=1e20`) the only effect is that the `PandfTiming` accumulators in F6
(`TimePandf`, `TotTimePandf`, `TimeConvert*`, `Timefd2tra`) appear. They are not written in the real Jacobian loop,
which is also why TSan does not report them. F6 also leaves out `com.ttimpfe`, which my rerun of the scan reports.
Set `yl[neq] = 1` in the column emulation (and restore it), and re-label F6.

**I1-m5. The consequence of `emcoef` in `copyin` is not recorded.** F15 rates the `copyin(...,emcoef)` as "Correct".
`emcoef` is a Forthon pointer (`real(kind=8), pointer:: emcoef(:,:,:)`), so `copyin` pointer-assigns each worker's
`emcoef` to the master's target, and the assignment persists after the loop. From the second Jacobian on, the three
workers' `OmpCopyPointeremcoef` all write `emcoef(1:n)` into the master's array at the same time. The values are
identical, so it is harmless in practice, but formally it is a data race. The worker's own copy is leaked. This is
relevant to fix direction 3 (making the tables shared), and AIUE-56 should decide whether `emcoef` stays in `copyin`.
The one TSan run covered only one Jacobian, so it could not see this.

**I1-m6. No full-problem sentinel scan (disclosed).** The ticket scope asks for sentinel tests "on the Te box and the
full problem". Only the diff test ran on the full problem, and the sentinel ran on one Te-box column. "Not covered"
says so honestly, and the full-problem diff did find F16 (`areapl`). Since a value-preserving race like `areapl` is
the kind of thing the sentinel catches, record a follow-up: a restricted variable list, or batched children, on a few
plate-adjacent full-problem columns.

**I1-m7. The M2 residual on the full problem varies more than reported.** My one full-problem run on the swap build
was not bitwise equal: 1217 differing entries (370 values, 844 serial-only, 3 OpenMP-only) in 26 Te rows. All are at
noise level: |Δ|·sfscal ≤ 4.6e-9, the largest serial-only entry is 1.0e-4 against max|jac| 1.70e14, `fnrm` and
`yldot` are equal, and max|jac| matches. This is the same class as the RCA's run 2 (472 entries, 7 rows). State the
observed range so AIUE-54/56 do not treat 472 as a bound.

**I1-m8. Documentation pointers.** The docstring of `scan_ompcopy.py` refers to a "run_tpcheck.md in the RCA" that
does not exist (the procedure is in the RCA's §How to reproduce). The file table in `tests/deterministic_omp/README.md`
does not list the four new tools. "How to reproduce" does not say that `scan_shared_state.py` needs
`UEDGE_OMP_RATES_DIR` when run from a copy of the case outside the repository.

## Specific questions from the main session

- **Is C1's mechanism what the generated code does?** Yes. `OmpCopyPointerxdata_api`
  (`base-omp/build/temp.*/api_p.F90:218-232`) sizes the copy buffer and checks the guard with the master's
  `nxdata_api` (41), but inside `!$omp parallel` the worker executes `xdata_api(1:nxdata_api)=...` with its own
  threadprivate `nxdata_api`, which is still the DATA value 1. The workers' storage comes from
  `apisetarraypointerxdata_api` (`:898-932`). There, `copyin(pcopy__)` gives each worker its own array, with the size
  and contents (zeros) the master's array had at `gallot` time, and the worker's pointer is associated with it. That is
  why E1 shows `nbad=40 of 41`. `OmpCopyScalarapi` (`:426-472`) runs only afterwards.
- **Does the swap alone fix the gross corruption?** Yes. Patch 0002 changes only the order of the two blocks. The
  checker in patch 0001 is behind `OMPJacDebug.eq.-7`, so it is inert in harness runs (default `OMPJacDebug=0`). I
  confirmed this in 3/3 Te-box `jac` runs, 1/1 Te-box `jacrhs` run and 1/1 full-problem `jac` run. I also confirmed
  that the remaining differences are M2 and independent of C1: with `afracs=0` both the unmodified build and the swap
  build show the same ulp-level row-12 (and row-3) differences, `4.547e-5` serial entries that OpenMP computes as
  exact zero, and nnz 169-172 against serial 175.
- **Could the swap break something?** I found nothing. Scalar copies do not depend on arrays, and `OmpCopyPointer*`
  copies data only; it does not re-associate pointers. No `bbb` or `com` array copy uses a threadprivate bound, so the
  swap changes behaviour only for the 12 `Imslwrk` copies. After the swap each worker writes `1:n_master` into storage
  that `setarraypointer` sized with the master's bounds at `gallot` time. `splinem` sets the bounds before `gallot`, so
  the two agree. AIUE-56 should still run one `--checkbounds` OpenMP Te-box run.
- **Are other variables affected by the same hazard?** None. I scanned every `OmpCopyPointer<var>` in all ten
  generated `<pkg>_p.F90` files (446 routines) for bound identifiers that carry `!$omp threadprivate` in any package
  (547 variables). The only hits are the 12 `Imslwrk` arrays. `OmpCopyScalarbbb` copies 89 scalars and none is an
  array bound. No other package has threadprivate variables. `OmpInitZero*` is never called.
- **Spot-checked table rows.** F16 `areapl`: `bbb/bbb.v:951` is a non-threadprivate `+work` scalar, written and then
  read on the next line at all 8 cited `pandf_boundary.m` lines. Correct. F7 `nfsp` (`bbb/pandf.m:50-51`) and F5
  `TimingPandfOn` (`:573-579`): correct, apart from I1-m4. F9/F10 `fmombal` SAVE (`api/fmombal.m:70`, call sites
  `pandf_plasma_momentum.m:671,703,1018`): correct, and `scan_saved_locals.py` reproduces them. F4 `impradloc(0)`: the
  `radimpmc` loop starts at `kk=1` (`api/inelrates.m:397-414`), and the case uses `ismctab=2`. Correct. F13
  `wk`/`yl_check`: the reads in `LocalJacBuilder` are limited to `ii1:ii2`, which is always initialised. Correct.
- **Are the scripts runnable as documented?** `scan_ompcopy.py` (0.3 s, same summary, 547-variable checker) and
  `scan_saved_locals.py` (70 rows; `emissbs`, `b3val`, `b1vahl`, `intrhv`, `fmombal` and `left_boundary` are
  reachable) both ran. `scan_shared_state.py --tebox` (diff mode, 17 s) gave the same changed set as the RCA, plus
  `com.ttimpfe`. I did not run `--sentinel` or the full-problem mode, and `tsan_summary.py` had no logs to read.
- **Is "Not covered" honest?** Mostly. It should add the parallel-RHS consequence (I1-M1) and the nksol-mode emulation
  (I1-m4).

## Not independently verified (environment)

- Linux/libgomp behaviour. The mechanism does not depend on the runtime: OpenMP threadprivate and `copyin` semantics
  plus Forthon's generated code. Whether libgomp keeps the threadprivate copies between the `setarraypointer` region
  and the Jacobian region (the persistence conditions: `dyn-var` false, unchanged team size) was not tested.
- The TSan run (351 reports) and the emutls/flat-namespace TLS claim. I did not rerun them.
- E1 checker output (I read the code it reflects but did not rebuild with the checker), and the RCA's full-problem
  run 1 being bitwise equal.
- The column-to-thread mapping in E4 (also unrecorded in the RCA).

## What was checked and how

- Diff scope: `git diff 483d57a..HEAD --stat`. Only the RCA document and four new scripts changed, with no product
  code. `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`: OK. No `.claude/` skill, agent or
  hook changes on this ticket's commits.
- Generated code: `base-omp/build/temp.macosx-26.3-arm64-cpython-313/api_p.F90` (module `Imslwrk` declarations and
  threadprivate directives `:83-134`, `OmpCopyPointer*` `:218-424`, `OmpCopyScalarapi` `:426-472`,
  `apisetarraypointerxdata_api`/`emcoef` `:898-932`/`:1222-1257`). Source: `ppp/omp_parallel.F90:645-748` and
  `:900-997`, `api/apip93.m:90-225`, `api/api.v:143-172`, `com/comutil.m:1013-1130` (B3VAL; no SAVE/DATA),
  `ppp/ppp.v` (`OMPCopyArray`/`OMPCopyScalar` default 1).
- My own order-hazard scan: `.../scratchpad/rev50/orderscan.py` over all generated `*_p.F90` files. 12 hazards, all in
  `api`.
- Harness (`AIUE-49/.../cli.py check`), outputs under `.../scratchpad/rev50/`:
  `swap_tebox` (jac, 3 repeats, swap build): fnrm and nnz equal, 1-2 values different in row 12;
  `base_tebox` (jac, 2 repeats, unmodified): fnrm 0.1438/0.1741, 40-45 mismatches, max|jac| 2.4-2.6e43;
  `swap_full` (jac, full problem, 1 repeat): see I1-m7;
  `jacrhs_base-omp` and `jacrhs_AIUE-50-swap` (jacrhs, Te box): see I1-M1.
- E2 reproduction (`rev50/e2_check.py`, base-omp): with OpenMP the first `exmain` gives nnz 186, max|jac| 2.60e43 and
  the second gives nnz 169, max 5.564e5, fnrm `0x1.49db83f99a136p-2`. That equals the serial second call. The second
  Jacobian still has 3 ulp-level differences (M2).
- Worker-state emulation (`rev50/emiss_check.py`, serial build). I zeroed the `Imslwrk` tables beyond the elements a
  worker receives. `emissbs` at te(4,20) went from 1.90e-35 to 1.0, and at te(5,20) from 2.77e-34 to 1.0, with or
  without `emcoef` intact.
- `afracs=0` discrimination of M2 (`rev50/afr_check.py`): the unmodified build (3 OpenMP runs) and the swap build (3
  OpenMP runs) were each compared bitwise with serial.
- Scripts run: `scan_ompcopy.py --src base-omp --md --emit-checker`, `scan_saved_locals.py --md`, and
  `scan_shared_state.py --tebox` from a copy of the case.
