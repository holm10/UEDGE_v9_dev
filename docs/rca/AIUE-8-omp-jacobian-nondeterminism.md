# AIUE-8: Non-deterministic OpenMP Jacobian (RCA working document)

Status: in progress (sections filled by AIUE-50; characterisation AIUE-54 and RCA AIUE-55 to follow).

Epic AIUE-8. Reproducer: `tests/deterministic_omp/` (AIUE-46). All results below were obtained on macOS arm64,
gfortran 15.2, Homebrew LLVM clang/libomp, `v9-develop` at `0fac655`, `OMP_STACKSIZE=512M`, a fresh process per run,
`python -I` with an empty `HOME`. "Serial" means a reference run of the same build with `OMP_NUM_THREADS=1` or the
`--serial` build, as stated.

## Shared-state scan (AIUE-50)

### Summary

The gross corruption (Te diagonals around −2.6e43, a sparsity pattern that changes from run to run, M1) has one
cause, found and confirmed on a scratch build.

**Candidate root cause C1: the OmpCopy order in `OMPJacBuilder` leaves the worker threads' impurity-emissivity
spline tables mostly zero on the first OpenMP Jacobian.** `OMPJacBuilder` copies threadprivate arrays
(`OmpCopyPointer<pkg>`, `ppp/omp_parallel.F90:681-686`) before threadprivate scalars (`OmpCopyScalar<pkg>`,
`ppp/omp_parallel.F90:688-693`). Each generated `OmpCopyPointer<var>` sizes the section it writes on a worker
with that worker's own copy of the bounds. For the twelve `Imslwrk` arrays in `api` those bounds are themselves
threadprivate scalars: `nxdata_api`, `nydata_api`, `nzdata`, `nwork2`, `nwork3` with DATA default `/1/`
(`api/api.v:145-147,155,157`), and `kxords_api`, `kyords_api`, `kzords` with default `/4/` (`api/api.v:161-165`).
`splinem` (`api/apip93.m:101-107`, called from `ueinit` at `bbb/odesetup.m:1130,1150` after `readpost`) sets the
first five on the master thread only. So on the first Jacobian each worker copies just element 1 of `xdata_api`,
`ydata_api`, `zdata`, `fdata_api`, `work2`, `work3`, `emcoef`, `z1coef`, `z2coef`, and elements 1:5 of the knot
vectors (bounds `n+k` = 1+4), and keeps zeros everywhere else. `emissbs` (`api/apip93.m:189-225`) then clips its
arguments to the zeroed data range. `B3VAL` fails its range test and returns 0, so `emissbs = 10**0 = 1.0` exactly,
against a true value of about 1.9e-35 at te(4,20). That is the `isimpon=7` fixed-fraction radiation term
(`bbb/pandf_plasma_energy.m:819-824`), which enters only the electron-energy residual (`cnimp*pwrze`,
`bbb/pandf_plasma_energy.m:1117`). So the corruption is limited to Te rows and to columns computed on worker
threads, and it vanishes with 1 thread or `afracs=0`. Only after the first copy do the workers hold the right
scalars, so later Jacobians in the same process are clean.

**C1 also corrupts the parallel RHS (`OMPParallelPandf1=1`), and through it the solution.** `OMPPandf1Rhs`
(`ppp/omp_parallel.F90:900-997`) calls no `OmpCopy*` routine, so its workers run on whatever threadprivate state the
last `OMPJacBuilder` copy left. Between the first and the second Jacobian the workers have the right `Imslwrk`
bounds but tables that are still mostly zero. (`emcoef` is the exception: `copyin` points it at the master's
array.) So every parallel-RHS evaluation in that window gets `emissbs = 1` on the worker chunks. Reviewer's
evidence (harness `--arm jacrhs`, Te box, 4 threads, unmodified build): `yldot` is wrong in all 25 Te rows and
`sfscal` in 18. The log shows `OMP iter= 0 fnrm= 0.87e31`. With `ftol=1e20` serial takes no Newton step, but this
run takes one, and `fnrm_final` differs (`0x1.9c7df3d50ba02p-3` against serial `0x1.49db83f93d961p-2`). With
`OMPParallelPandf1=1` the defect therefore changes the result, not only the preconditioner. The swap build matches
serial on this arm, apart from the M2 entries. **AIUE-56 must validate the `jacrhs` arm as well as `jac`.**

Fixing the copy order on a scratch build makes the Te-box OpenMP Jacobian match serial in sparsity and `fnrm`, bitwise,
in 3 of 3 runs, and the full-problem Jacobian bitwise equal to serial in 1 of 2 of my runs. The remaining
differences are round-off-level entries in Te rows (mechanism M2, below). They are a separate, much smaller effect.
On the full problem their count varies widely from run to run: 0 and 472 entries (7 rows) in my two runs, 860-1037
per run in the main session's harness, and 1217 entries in 26 Te rows in the reviewer's run. All are at noise level
(|Δ|·sfscal ≤ 4.6e-9), with `fnrm` and `yldot` equal. 472 is not a bound.

No other shared-state defect that could produce M1 was found. Secondary findings: one real race on physics state
in the plate boundary conditions (`areapl`, F16; full problem only, not seen to change results), benign races on
timers, flags and `nfsp` (F5-F7), and SAVE arrays in `api/fmombal.m` (F9-F10).

### Method

| Check | Tool | What it covers |
|---|---|---|
| OmpCopy coverage, static | `tests/deterministic_omp/tools/scan_ompcopy.py` | Every `+threadprivate` variable in every `.v`. Does the generated `<pkg>_p.F90` have the `!$omp threadprivate` directive? Is the variable copied by `OmpCopyPointer<var>`/`OmpCopyScalar<pkg>`, is that package's copy called by `OMPJacBuilder`, which size guard can skip the copy, is it in `copyin`, and does the copied section depend on threadprivate scalars that are copied later (copy-order hazard)? |
| OmpCopy coverage, dynamic | `scan_ompcopy.py --emit-checker` + scratch build | Generated `OMPCheckThreadprivateCopy(tag)`: compares every worker's copy of all 547 threadprivate variables (bbb 522, api 25), bit for bit, with the master's copy, right after the copy and after the loop. |
| Shared state written by a local `pandf`, before/after | `tests/deterministic_omp/tools/scan_shared_state.py` | All 3480 non-threadprivate variables of bbb, com, api, aph, ppp, flx, grd, svr, wdf, ncl, of every type (real, integer, logical, character; scalars and arrays). Snapshots after `pandf(-1,-1)`, after the perturbed local `pandf(xc,yc)` and after the restoring one, for all 25 Te-box columns and 12 full-problem columns. Evaluated in Jacobian mode, `yl(neq+1)=1`. The first version used nksol mode (`-1`). After review, both the Te box (diff + sentinel) and the full-problem diff were re-run in Jacobian mode, giving the same findings except for the `PandfTiming` accumulators (F6). |
| Same, sentinel | `scan_shared_state.py --sentinel` | Catches value-preserving writes and set/reset toggles. Each variable is set to a sentinel (next float up, int+1, negated logical), one column is run, and any variable no longer holding the sentinel is reported. Each test runs in a forked child, so a crash marks only that variable. |
| Saved locals, DATA, COMMON | `tests/deterministic_omp/tools/scan_saved_locals.py` | 865 program units in `*/*.m`, `ppp/*.F90`, tracked `*.f`. Call graph from `pandf` (145 reachable units); SAVE, DATA, F90-initialised locals and COMMON variables, and whether the unit assigns them or passes them to a CALL. |
| Automatic arrays in `LocalJacBuilder` | Code reading (`ppp/parallel.F90:195-196,229-345`) | Is `wk`/`yl_check` read before it is written? |
| `ppp` module variables | Code reading (`ppp/omp_parallel.F90:645-760`, `ppp/parallel.F90`) + shared-state scan | Writes to `ppp` state inside the parallel loop. |
| ThreadSanitizer | Scratch build with `-fsanitize=thread` | See "ThreadSanitizer" below. |
| TLS sanity | `nm`/`dyld_info` on the installed extensions | gfortran on Darwin uses emulated TLS. `__emutls_get_address` is defined in `bbbpy`, `apipy` and `ppppy`, but every call goes through a flat-namespace GOT bind, so a single emutls runtime serves all packages. The per-package TLS split hypothesis is ruled out. |

### Findings

| # | Variable | file:line | Kind | Written where | Threadprivate | Copied | Verdict |
|---|---|---|---|---|---|---|---|
| F1 | `xdata_api`, `ydata_api`, `zdata`, `fdata_api`, `work2`, `work3`, `xknots_api`, `yknots_api`, `zknots`, `emcoef`, `z1coef`, `z2coef` (`Imslwrk`) | `api/api.v:148-151,156,158,167-172` | dynamic real arrays, bounds = threadprivate scalars | filled by `splinem1` after `gallot("Imslwrk")` on the master (`api/apip93.m:108-185`); `work2` written by `B3VAL` in `emissbs` inside `pandf` | yes | **partially**: only element 1 on the first Jacobian, because `OmpCopyPointerapi` (`ppp/omp_parallel.F90:685`) runs before `OmpCopyScalarapi` (`:692`) and sizes the section with the worker's `nxdata_api` etc. (still `/1/`); `emcoef` is also in `copyin` (`:715`), so in the loop the workers' `emcoef` points at the master's array | **Candidate root cause C1 of M1** (evidence E1-E4) |
| F2 | `nxdata_api`, `nydata_api`, `nzdata`, `nwork2`, `nwork3`, `kxords_api`, `kyords_api`, `kzords`, `ldf_api`, `mdf` | `api/api.v:145-147,152-153,155,157,161-165` | integer scalars, DATA `/1/` or `/4/` | `splinem`/`splinem1` on the master (`api/apip93.m:101-106,142-143`) | yes | yes, but after the arrays that depend on them (see F1); workers hold the DATA defaults until the first `OmpCopyScalarapi` | Part of C1 |
| F3 | `icont`, `iflagi`, `iworki` | `api/api.v:154,159-160` | int scalars / fixed int array | `emissbs` sets `icont=0` (`api/apip93.m:215`); `B3VAL` writes `iflagi`, `iworki` | yes | yes | Correct (per-thread work state) |
| F4 | `impradloc(0)` | `bbb/bbb.v:3898` | element of a threadprivate work array | never written by `radimpmc` (`api/inelrates.m:397-414` loops `kk=1,nzarg`), but read into `pradzc(..,0,..)`/`pradc` (`bbb/pandf_plasma_energy.m:812-815`) | yes | yes | Stale/uninitialised read, but only for `ismctab=1` (this case uses `ismctab=2`/`radmc`), and `pradc`/`prad` are diagnostics, not the Te residual (`pwrze`). Not a cause; report to the fix ticket |
| F5 | `TimingPandfOn` | `bbb/bbb.v:4136` | integer scalar | set and reset on every `pandf` call (`bbb/pandf.m:573-579`) | **no** | n/a | Data race between threads (sentinel: WRITTEN). It only gates timing, so it does not affect results. Should be threadprivate or not written in the Jacobian |
| F6 | `com.ttimpjf`, `ttnpg`, `ttngxlog`, `ttngylog`, `ttngfd2`, `ttngfxy`, `totintrv` (`Timing`, `TimeSpl`) | `com/com.v:503-567` | real scalars | accumulated in `pandf` (`bbb/pandf.m:760`), `neudifpg` (`bbb/pandf_gas_continuity.m`), `B1VAhL` (`com/comutil.m:3654`) (`istimingon=1` by default, `com/com.v:503`) | **no** | n/a | Benign data races on timers (lost updates only). The `PandfTiming` accumulators (`TimePandf`, `TotTimePandf`, `TimeConvert*`, `Timefd2tra`) were reported by the first scan only because it ran `pandf` in nksol mode (`yl(neq+1)=-1`). In Jacobian mode (`yl(neq+1)=1`, the default of the fixed scan) `TimingPandfOn=0` and they are not written, which agrees with TSan. (`ttimpfe` is written only for `xc<0`, `bbb/pandf.m:751-761`: it showed up only through the scan's own reset `pandf(-1,-1)` after each column, so it is not a race of the Jacobian loop) |
| F7 | `com.nfsp` | `com/com.v:28` (`Dim`) | integer scalar | `nfsp = nisp` / `= nhsp` on every `pandf` (`bbb/pandf.m:50-51`) | **no** | n/a | Race, but every thread writes the same value (it depends only on `isimpon`, `nisp`, `nhsp`). Benign |
| F16 | `areapl` (`Rccoef`) | `bbb/bbb.v:951` | real scalar, `+work` | written and immediately read in the plate recycling/albedo boundary conditions, `left_boundary`/`right_boundary` (`bbb/pandf_boundary.m:3091,3166,3446,3544,3797,3882,4180,4277`) | **no** | n/a | **Real data race on physics state**, found by the full-problem diff scan (changed in every sampled column whose box touches a plate: 11 of 12). Two threads at plate cells can overwrite each other's value between the write and the read on the next line. Not observed to change results (the full-problem OpenMP Jacobian with C1 fixed differs from serial only in Te rows, and is bitwise equal in 1 of 2 runs), probably because the compiler keeps the value in a register. Still, it must become a local or `+threadprivate` (fix ticket). Not involved in the Te box |
| F8 | all other non-threadprivate variables (3480 scanned), every type | all `.v` | — | not written by a local `pandf` (diff on 25 Te-box + 12 full-problem columns; sentinel on one Te-box column only, since the full-problem sentinel run did not finish within the time box) | no | n/a | Clean. With F5-F7 and F16 this closes H2 for scalars and integer arrays on the sampled columns |
| F9 | `uresp`, `usave`, `caplams` | `api/fmombal.m:70` | SAVE local arrays | passed to `zrespond`/`mrespond`/`mzrespond`, which write them (`api/fmombal.m:223-238`) | no | n/a | **Race when `fmombal` runs on several threads** (called from `mombal` for `isimpon` 6/7 parallel force balance, `bbb/pandf_plasma_momentum.m:671,703`, `:1018`). Not involved in the Te box (`isupon=0`); a candidate for non-Te round-off in the full problem, not for M1 |
| F10 | `nrow`, `bmat`, `sbar0`, `ubar0` (`mrespond`); `zmat`, `source`, `scaz`, `lsz`, `msz`, `nrowz` (`zrespond`) | `api/fmombal.m:368`, `api/fmombal.m:1064` | SAVE locals | passed to CALLs in the same routines (`:466-480`, `:1199-1213`) | no | n/a | Same as F9 (H3 confirmed as a hazard, not as the M1 cause) |
| F11 | `lunit`, `mesflg` (`parmsetget`), `args` (`ijmgetmr`), COMMON `/iotable/` (`freeus`) | `com/error.f:144`, `com/getmsg.f:11`, `com/dummy_py.f:66` | SAVE/DATA/COMMON | error-message and interrupt paths (`xermshg`, `check_kaboom`) | no | n/a | Only on error or interrupt paths. Benign for the Jacobian |
| F12 | DATA tables in `rcxr_zn6`, `rcxr_zn6b` (`api/fimp.m:219-252`), `yhaasz*` (`api/sputt.m:501-765`), F90 initialisers in `run_uedge`/`run_degas2` (`bbb/ext_neutrals.m:118-162`, duplicated in `bbb/s.m`) | as listed | DATA/initialised locals | never assigned | no | n/a | Read-only constants. Safe |
| F13 | `wk(neq)`, `yl_check(neq)` (`LocalJacBuilder`) | `ppp/parallel.F90:195-196` | automatic arrays (per call, per thread) | `wk(ii1:ii2)=yldot00` before every `pandf` (`:237-239`); `pandf` rescales `yldot(iv)` in place (`bbb/pandf.m:436-504`) over its own loop range; `yl_check(1:neq)=wk(1:neq)` (`:321`) | n/a (stack) | n/a | No read-before-write reaches the Jacobian: `jacelem` and the `isjacreset` check read only `ii1:ii2`, which is always initialised. Entries outside `ii1:ii2` may hold garbage but are never used. On the Te box `ii1:ii2` covers all 25 equations. Ruled out (H6 part 2) |
| F14 | `ppp` module state written in the loop: `iJacCol(:,ichunk)`, `rJacElem(:,ichunk)`, `iJacRow(ivmin:ivmax)`, `OMPTimeJacRow(ivmin:ivmax)`, `nnz(ichunk)`, `OMPTimeLocalJac(tid+1)` | `ppp/omp_parallel.F90:728-735` | shared arrays | inside `!$omp parallel do`, indexed by `ichunk`/`tid` | no | n/a | Disjoint per chunk/thread. No race. `ppp` has no threadprivate variables (`ppp/ppp.v`); `OmpCopyppp` is empty. Clean |
| F15 | `yinc`, `xlinc`, `xrinc` (`Selec`), `emcoef` | `ppp/omp_parallel.F90:715` | threadprivate | `copyin` | yes | yes (twice: OmpCopy and copyin) | Correct for the `Selec` scalars. **`emcoef` is a Forthon pointer**, so `copyin` pointer-assigns each worker's `emcoef` to the master's target, and the association persists after the loop. From the second Jacobian on, every worker's `OmpCopyPointeremcoef` writes `emcoef(1:n)` into the master's array at the same time: a formal data race, harmless because the values are identical, and the workers' own copies are leaked. AIUE-56 should decide whether `emcoef` stays in `copyin`; see also fix direction 3. My TSan run covered only one Jacobian, so it could not see this |

The full coverage table, with one row per threadprivate variable (547 rows), is regenerated with
`scan_ompcopy.py --md`. Its summary for `0fac655` is: bbb 522 threadprivate, 522 copied; api 25 threadprivate, 25
copied; no threadprivate variable lacks the directive or a copy routine; 442 copies (bbb 430 of 433, api 12 of 13)
are behind a `size >= declared` guard, while the 4 fixed-size arrays (`cftgtipltl`, `cftgtipltr`, `psordisold`,
`iworki`) have none, and none of those guards fails for this case (the checker found 0 mismatches outside
`Imslwrk`); **12 copy-order hazards, all in `api` `Imslwrk`** (F1).

### Candidate root cause C1: evidence

**E1. Worker state after the copy, unmodified code.** Scratch build `0fac655` + generated checker (no other
change). Te box, 4 threads. `TPCHK after-copy`: 36 mismatching (variable, thread) pairs, i.e. exactly the 12
`Imslwrk` arrays × 3 workers, and nothing else among the 547 variables. Every one shows the same pattern: element 1
correct, the rest 0:

```
TPCHK after-copy api.xdata_api tid=  1 nbad=   40 of    41 first=  2 worker= 0 master= C032FF0E5F804024
TPCHK after-copy api.xknots_api tid= 1 nbad=   40 of    45 first=  6 worker= 0 master= C032CBDB30DB0347
TPCHK after-copy api.emcoef tid=     1 nbad= 25255 of 25256 first=  2 worker= 0 master= C04926B02D96F303
TPCHK after-copy api.work3 tid=      1 nbad= 25412 of 25592 first=  2 worker= 0 master= 3BB657BAF3E546E8
TPCHK after-copy done:     36 mismatching (variable,thread) pairs over   547 variables
```

The generated copy that does it (`build/temp.*/api_p.F90`, Forthon `--omp`):

```fortran
subroutine OmpCopyPointerxdata_api
  use Imslwrk
  real(kind=8)::xdata_apicopy(1:nxdata_api)          ! master: nxdata_api = 41
if ((nxdata_api-1+1).le.size(xdata_api)) then
xdata_apicopy(1:nxdata_api)=xdata_api(1:nxdata_api)
!$omp parallel private(tid) firstprivate(xdata_apicopy)
tid=omp_get_thread_num()
if (tid.gt.0) then
xdata_api(1:nxdata_api)=xdata_apicopy(1:nxdata_api)  ! worker: its own nxdata_api, still the DATA default 1
```

**E2. Only the first Jacobian of a process is wrong.** Unmodified `base-omp` build. Te box, two `exmain()` calls
(ftol=1e20) in one process, 4 threads, 3 fresh runs. First Jacobian: max|jac| 2.37e43, 2.60e43, 2.60e43; nnz 186,
177, 178 (serial 169). Second Jacobian: max|jac| 5.564e5 in all runs (serial 5.564e5), nnz 169, and `fnrm`
bitwise equal to the serial second call (`0x1.49db83f99a136p-2`). By then the first `OmpCopyScalarapi` has given
the workers the right `nxdata_api` etc.

**E3. Copy order swapped (scalars first), scratch build.** The only change from `0fac655` is moving the
`OmpCopyScalar*` block before the `OmpCopyPointer*` block in `OMPJacBuilder` (patch below), plus the checker.
Te box, 4 threads, 3 fresh runs:

| | serial (same build) | OMP run 1 | run 2 | run 3 |
|---|---|---|---|---|
| `TPCHK after-copy` mismatches | — | 0 | 0 | 0 |
| nnz | 169 | 169 | 169 | 169 |
| `fnrm` | `0x1.49db83f93d961p-2` | same | same | same |
| `jaci`/`jacj` SHA-256 | `995b8308…`/`47a3c6d7…` | same | same | same |
| differing `jac` values | — | 1 (row 12) | 2 (row 12) | 1 (row 12) |

Unmodified `base-omp`, same configuration: fnrm 0.1742/0.1622/0.1441 (AIUE-46), nnz 177-191, max|jac| ≈ 2.6e43.

Full problem (neq 44352, 4 threads, ftol=1e20), same scratch build: run 1 is **bitwise equal** to serial (nnz
3 190 290, all values and `fnrm` `0x1.eb37d428ec4f0p+0`). Run 2 has `fnrm` bitwise equal and 472 differing entries,
all in 7 Te rows: 416 serial entries of magnitude ≤ 7e-5 missing, 3 extra, and 53 values differing (median relative
difference 5e-5). Max|jac| matches serial (1.70e14). Unmodified `base-omp`: 663 257 differing entries, all in Te
rows, nnz 3 675 793, max|jac| 5.98e43.

Patch used (scratch only, not committed as product code):

```diff
--- a/ppp/omp_parallel.F90  (OMPJacBuilder)
-    if (OMPCopyArray.gt.0) then
-        call OmpCopyPointerbbb; call OmpCopyPointercom; call OmpCopyPointerapi
-    endif
-    if (OMPCopyScalar.gt.0) then
-        call OmpCopyScalarbbb; call OmpCopyScalarcom; call OmpCopyScalarapi
-    endif
+    if (OMPCopyScalar.gt.0) then
+        call OmpCopyScalarbbb; call OmpCopyScalarcom; call OmpCopyScalarapi
+    endif
+    if (OMPCopyArray.gt.0) then
+        call OmpCopyPointerbbb; call OmpCopyPointercom; call OmpCopyPointerapi
+    endif
```

**E4. Consistency with the known symptoms.**

* *Te rows only.* `emissbs` is used only in `pwrzec`/`pwrze` → `resee` (`bbb/pandf_plasma_energy.m:775,822,1117`).
* *1 thread bitwise equal.* There are no workers, so nothing is copied.
* *Thread-count dependent; master columns are correct.* Rows 3, 7, 11, 14, 18 and 22 are bitwise correct in the
  unmodified run. That is consistent with those columns running on thread 0 (the column-to-thread mapping was not
  recorded).
* *Off-diagonal entries equal another column's diagonal.* Every column whose stencil contains cell r recomputes
  `emissbs` at r with the same zeroed tables. That gives the same wrong `wk(r)` divided by an almost equal `dyl`
  (the values agree to the last 1-2 ulp).
* *Run-to-run variation.* On a worker, `emissbs` clips its arguments into the zeroed data range. `B3VAL` then fails
  its range test and returns 0, so `emissbs = 1.0` exactly (reviewer's emulation: 1.90e-35 → 1.0 at te(4,20),
  2.77e-34 → 1.0 at te(5,20)). The wrong value is deterministic per cell. The variation comes only from which
  columns `schedule(dynamic)` puts on worker threads.
* *`afracs=0` cures it* (main-session experiment). `pradcff = na*ne*emissbs` with `na=afrac*ne=0`.
* *Full problem: stable `fnrm`, unstable Jacobian.* The iteration-0 `fnrm` comes from the master's RHS.

Suggested fix directions for AIUE-56 (not implemented here):

1. In `OMPJacBuilder`, call `OmpCopyScalar*` before `OmpCopyPointer*`. It is the smallest change; it also covers
   any future array whose bounds are threadprivate scalars.
2. Or make the generated `OmpCopyPointer<var>` pass the master's bounds into the parallel region. This is a
   Forthon template change, so it needs upstream work.
3. Independently, consider making the `Imslwrk` tables (read-only after `splinem1`) non-threadprivate shared data,
   leaving only the B3VAL work arrays (`work2`, `iworki`, `icont`, `iflagi`) threadprivate.

`scan_ompcopy.py` flags the order hazard statically, so it can serve as a regression check. Validation for AIUE-56
must include the `jacrhs` arm (`OMPParallelPandf1=1`), not only `jac`, and one `--checkbounds` OpenMP Te-box run.

### Mechanism M2 (round-off-level, history dependent), not resolved here

After C1 is removed, the OpenMP Jacobian still differs from serial in a handful of Te-row entries of ulp size:
4.5e-5 ≈ ulp(yldot)/dyl. These are entries that the serial run stores because of round-off noise and the OpenMP run
computes as exact zero, or the reverse. (Two consecutive serial `exmain()` calls give different `fnrm`, but that is a
state change between the calls, not a history test; see AIUE-55, P3-m3, which locates the history inside the serial
column loop.) The shared-state scan rules out a shared non-threadprivate variable as the
carrier (F8). Candidates for AIUE-54/55: threadprivate work arrays that a local `pandf` reads outside its own
recomputed box. On a worker those hold the values of the worker's previous columns, not the master's full-RHS
values; the `after-loop` checker output lists them (for example `bbb.qfl`, `csh`, `qsh`, `mfl`, `msh`, `fxe`, `fxi`,
`zcoef` differ per thread after the loop). Another candidate is the SAVE arrays in `api/fmombal.m` (F9/F10) for the
full problem. Below `jaccliplim`, tiny differences turn into sparsity changes.

### ThreadSanitizer

Homebrew gfortran 15 ships no `libtsan` for Darwin, but objects built with `gfortran -fsanitize=thread` link and
run against LLVM's `libclang_rt.tsan_osx_dynamic.dylib`. A toy racy `!$omp parallel do` is reported correctly.
I ran a full scratch build with `-fsanitize=thread` added to `FARGS` (copy-order patch and checker included, so C1
is removed) on the Te box with 4 threads (`DYLD_INSERT_LIBRARIES=<llvm>/lib/clang/23/lib/darwin/libclang_rt.tsan_osx_dynamic.dylib`,
`TSAN_OPTIONS="log_path=... halt_on_error=0"`). `fnrm` matched serial. It produced 351 reports, grouped by
`tests/deterministic_omp/tools/tsan_summary.py`:

| Reports | In the Jacobian loop | Location | Verdict |
|---|---|---|---|
| 105, 17, 16, 16, 15, 15, 15 | yes | `Timing::ttimpjf`, `TimeSpl::totintrv` (`B1VAhL` via `emissbs`), `ttngxlog`, `ttngfd2`, `ttngylog`, `ttngfxy`, `ttnpg` | real races on timing accumulators (F6), harmless to results |
| 14 | yes | `PandfTiming::TimingPandfOn` (`bbb/pandf.m:573-579`) | real race (F5), harmless to results |
| 13 | yes | `Dim::nfsp` (`bbb/pandf.m:50-51`) | real race, same value written (F7) |
| 30 | yes (read) | heap block (numpy array) | false positive: written by the master in `gridseq` after the region, read in the loop (`convsr_aux2`); TSan does not see libomp's join |
| 95 | no | stack/heap in `bbbsetarraypointer*`, `OmpCopyScalar*`, `OmpCopyPointer*` | false positives: firstprivate/copyin buffers across parallel regions, synchronised by the uninstrumented libomp barrier |

So TSan finds no race on physics state inside the column loop once C1 is fixed. This is the same result as the
sentinel scan, from an independent method. TSan cannot detect C1 itself, because C1 is a missing copy, not a race.
The serial reference and the unpatched code were not run under TSan.

### Not covered

* Units reached only through procedure arguments or ENTRY points, and code reached only through Python callbacks,
  are not followed by `scan_saved_locals.py`. `com/*.f` and `ncl/*.f` are scanned; `svr` (nksol) runs outside the
  Jacobian column loop and was not included in the reachability roots.
* The full-problem **sentinel** run (`--cols 12 --sentinel`) was stopped after about 20 minutes. Forking the
  44352-equation process once per variable is too slow. For the full problem only the before/after diff on 12
  columns was done. Restricting the sentinel to a list of variables, or reusing one child per batch, would make
  it feasible.
* The sentinel test runs one column (Te box: column 13).
  A variable written only for other cells or boundary columns would be missed by the sentinel, but would still
  show in the diff test if its value changes.
* `OMPParallelPandf1=1` (parallel RHS) was not scanned for shared state of its own. It has its own chunking path,
  and it writes the shared `com.nfsp` in `OMPinitialize_ranges2D` (`ppp/omp_parallel.F90`). It is **not** unaffected
  by C1, though: it inherits the workers' state from the last Jacobian copy (see Summary).
* Follow-up for the sentinel on the full problem: run it on a restricted variable list, or with batched children,
  on a few plate-adjacent columns. The `areapl` race (F16) is the kind of value-preserving write the sentinel is
  meant to catch.
* Other platforms and runtimes (Linux/libgomp) were not tried. C1 does not depend on the platform.
* M2 is characterised only as far as above.

### How to reproduce

From the AIUE-50 worktree, with the case copied as in `tests/deterministic_omp/README.md`. Set
`UEDGE_OMP_RATES_DIR=<repo>/builder/test/Forthon_cases/Forthon_case5` whenever the case runs outside the repository
(the deck finds the rate files relative to itself). Also set `OMP_STACKSIZE=512M`, use an empty `HOME`, and run
`python -I`:

```bash
T=tests/deterministic_omp/tools
# static OmpCopy coverage (needs a built OpenMP tree with build/temp.*/<pkg>_p.F90)
python -I $T/scan_ompcopy.py --src <omp-built-tree> --md ompcopy.md --emit-checker tpcheck.F90
# saved locals / DATA / COMMON reachable from pandf
python -I $T/scan_saved_locals.py --md saved_locals.md
# shared state written during a local pandf (serial build), from a copy of the case
python -I $T/scan_shared_state.py --tebox --sentinel --src <worktree>
python -I $T/scan_shared_state.py --cols 12 --sentinel --src <worktree>
```

Dynamic checker (scratch tree only): append `tpcheck.F90` inside an `#ifdef _OPENMP` block at the end of
`ppp/omp_parallel.F90`, and add `if (OMPJacDebug.eq.-7) call OMPCheckThreadprivateCopy('after-copy')` after the
`OmpCopyScalar*` block in `OMPJacBuilder` (and `'after-loop'` after `!$omp END PARALLEL DO`). Build with
`build_uedge.sh <tree> <venv> omp`, then run the Te box with `ppp.OMPJacDebug=-7` and `grep -a TPCHK` the log.
For E3, also apply the copy-order patch above.
