# AIUE-47 Raw-Jacobian capture hook: implementation review, round 1 (plan included)

Reviewer: uedge-reviewer (independent). Branch `feature/v9-AIUE-47-raw-jacobian-capture` at 2cb855b/d4c2fb9
(Fortran is 5f0a633; nothing after it touches `.m`/`.v`/`.F90`/build files). Reference: ticket acceptance
criteria and `.claude/plans/AIUE-47-raw-jacobian-capture.md`. Finding prefixes: L = plan/design, I = implementation.

## Verdict

**REVISE**: one MAJOR finding (L-M1), fixable with one line or a documented limit. No BLOCKERs.

## Summary

The hook does what the ticket asks. It sits at the one point that sees both `jac_calc` and `jac_calc_parallel`,
it copies before any `suscal`/`sfscal` scaling, row normalisation or reordering, it is a single integer test
when off, and it is correctly not `+threadprivate`. I reran the AC1 bitwise comparison on the full 44352-equation
reproducer (serial), on D+C (serial, 3 Newton iterations) and on D_only (OpenMP build, both switches 0,
4 threads, 3 Newton iterations, `incpset=1`). All of them match `v9-develop` bit for bit. I also reran the AC2
identity on the full problem (serial `jac_calc`) and on the Te box (`jac_calc_parallel`). Both pass bitwise.
They are not vacuous: `suscal` is not 1 and the raw hash differs from the `bbb.jac` hash. My own edge-case
script confirmed that slots survive `gchange` growth when `neq` grows between Jacobians (300 to 420), that a
`gfree` followed by a capture does not crash, and that the overflow, skip and restart logic is right. The open
problem is a design one: `jaccapture` allocates all K slots when the first Jacobian is captured. "Keep every
Jacobian = large `jaccapture`" (the plan's own recipe) therefore costs about 51-58 MB per requested slot on the
reproducer, before any of them is filled.

## Findings

### BLOCKER

None.

### MAJOR

**L-M1: Eager allocation of all `jaccapture` slots makes "keep every Jacobian" a memory trap.**
- Location: `bbb/oderhs.m` `jac_capture`, `jaccapnslot = max(jaccapnslot, jaccapture)` followed by
  `call gchange("Jacobian_capture",0)`. Plan, Design: "Keep every Jacobian = large `jaccapture`,
  `jaccapskip=0`". `bbb/bbb.v` `jaccapture` description: "Max. number of Jacobians kept".
- What is wrong: the slot dimension is sized to the requested maximum, not to the slots actually used. Forthon's
  `gchange` then allocates the whole array and writes the initial value into every element
  (`Forthon.h` `ForthonPackage_gchange`, the fill loop before `PyArray_CopyInto`). So all of that memory is
  touched at the first capture. If allocation fails, Forthon calls `exit(EXIT_FAILURE)` and the Python session
  is gone. The ticket's main use case ("keep **every** Jacobian of a run") needs an upper bound that the user
  cannot know in advance. The design tells them to pick a large one, and the documentation does not say that
  this is paid for up front.
- Evidence: D_only (neq=420, nnz=8194), `jaccapture=1000`, one `ftol=1e20` exmain gives `jaccapn=1`,
  `jaccapv.shape=(8194, 1000)` and 134 MB allocated (`scratchpad/rev47/ds/eager.py`). On the reproducer one slot
  is 3190290·16 + 44353·8 ≈ 51 MB (serial) or 3621751·16 ≈ 58 MB (`jac_calc_parallel`). `jaccapture=100` is
  therefore about 5-6 GB allocated and initialised at the first Jacobian, even for a run that computes 4. When
  `nnz` grows (it does on the parallel path: 169/173/189 between Jacobians), every growth also reallocates and
  copies all K slots, so the peak is about twice that.
- Acceptance condition: one of the following.
  (a) Size the slot dimension by use (`jaccapnslot = max(jaccapnslot, islot)`, optionally with geometric
  growth). Keep `jaccapture` as a cap only. Re-run the bookkeeping checks.
  (b) Keep eager allocation, but state in the `jaccapture` `.v` description and in `openmp-jacobian.md` that K
  slots of about `nnzmx·16 + (neq+1)·8` bytes are allocated at the first capture. Also replace the plan's
  "large `jaccapture`" recipe with guidance (for example use `itermx`/`incpset` to bound the count, and pre-set
  `jaccapnnzmx` to avoid repeated growth).
  Either is acceptable. (a) is the more robust choice for AIUE-49.

### MINOR

**I-m1: `capture_check.py` reports PASS when a capture run performed no capture check.**
- Location: `tests/deterministic_omp/tools/capture_check.py` `child()` (the identity check runs only when
  `from == "sfsetnk"`, `newton == 0` and on the last slot) and `capture_checks()` (returns True when `slots` is
  empty).
- Problem: with `--capture K`, a regression that stores nothing (`jaccapn=0`), or that loses the caller tag
  (`jaccapfrom=0`, so the identity check is skipped), still gives `RESULT ...: PASS` and exit code 0. The
  round-1 validation log shows that the checks did run, so this ticket's evidence holds. But the tool is meant to
  be reused (AIUE-49/53), and its exit code is the contract.
- Acceptance: with `--capture K>0`, FAIL when `jaccapn == 0`. In `ftol` mode, also FAIL when no
  `check_raw_times_inv_suscal_bitwise_eq_bbb_jac` was evaluated.

**I-m2: The `.v` text "Raw Jacobian nonzeros d(yldot)/d(yl)" overstates what is captured.**
- Location: `bbb/bbb.v` `jaccapv` description, and "raw finite-difference Jacobian" in `openmp-jacobian.md`.
- Problem: the capture is the output of `jac_calc`/`jac_calc_parallel`. That output already includes the
  `-1/dtuse(iv)` diagonal for time-dependent runs and `-nufak` when `nufak>0` (`bbb/oderhs.m` `jac_calc`, the
  `jacelem` updates after the finite difference). It also drops elements with `|jacelem·sfscal| <= jaccliplim`
  (default 0, so exact zeros only). The sparsity pattern therefore depends on `sfscal` at the time of the call.
  This matters when AIUE-49 compares patterns. Note also that `psetnk` Jacobians are taken with
  `yl(neq+2)=nufak`.
- Acceptance: the description says "the matrix returned by `jac_calc`/`jac_calc_parallel` (finite-difference
  `d(yldot)/d(yl)` including the `-1/dtuse` and `-nufak` diagonal terms; entries with
  `|J·sfscal| <= jaccliplim` dropped)", or equivalent wording.

**I-m3: Undocumented behaviour after `gfree` and on growth.**
- Location: `jac_capture` comment ("allocates the group if it was freed from Python"), `.v`, `openmp-jacobian.md`.
- Problem: after `bbb.gfree("Jacobian_capture")`, the counters keep running. New captures land in slot
  `jaccapn+1`, and slots `1..jaccapn` come back zero-filled with `jaccapneq=jaccapnnz=0`. My test T3 showed this:
  no crash, but the earlier slots are lost silently. This is acceptable behaviour, but a reader of `jaccapn`
  would assume those slots are valid.
- Acceptance: one sentence in the `.v` or context doc: after `gfree`, reset `jaccapcount=jaccapn=0`.

## Status of previous findings

Round 1: none.

## Points checked and found correct (no finding)

- **Capture point and pre-scaling (both callers).** `jac_calc_interface` (`bbb/oderhs.m:4676`) is called only
  from `psetnk` and `sfsetnk`. The other `jac_calc` callers (`jacd1`, `jacd2`, `jacnw`, `jacvd`, `FPRECO`, and in
  `ppp` `ForceSerialCheck`/`CheckJac`/`DumpFullJac`/`EvalDumpJac`) call `jac_calc` directly, so nothing is
  captured twice. `amudia`, `diamua`, `jac_norm_rows` and `jac_lu_decomp` all run after the call in both
  callers. `rnrms` (`svr/svrut4.m`) only reads `a`. PETSc uses `Petscjac_calc` and never reaches
  `jac_calc_interface`, as documented.
- **Producer tag.** `jcsrc` is computed from `ParallelJac`, the same condition `jac_calc_interface` dispatches
  on. In the serial `.F` the `c!omp` line stays a column-1 comment, so the tag is always 1. In the OpenMP `.F`
  it becomes `         if (ParallelJac.eq.1) jcsrc = 2` (`setup.py` `Omp.parse` replaces `c!omp` with
  5 blanks). I checked both generated files: `AIUE-47-serial/bbb/oderhs.F` and `AIUE-47/bbb/oderhs.F` are
  identical except for the `c!omp` lines.
- **`jaccapcur` tagging.** These are plain integer stores around the call, with no other caller of
  `jac_calc_interface`, so a stale value after an `xerrab` unwind cannot be mis-attributed. They are bitwise
  harmless (AC1 below). They are written by the master thread only.
- **Not `+threadprivate`.** The only `!$omp parallel` regions are in `ppp/omp_parallel.F90` (`InitOMPJac`,
  `jac_calc_omp`, `OMPPandf1Rhs`), and they close before `jac_calc_parallel` returns. `pandf`/`rhsnk` never
  call `psetnk`/`sfsetnk`. The generated `bbb_p.F90` has no `threadprivate` directive for any `jaccap*` name.
- **Fortran bounds and CSR.** `islot` is at most `jaccapture`, which is at most `jaccapnslot`. A negative
  `jaccapskip` cannot give `islot < 1`. Also `nnz = ia(neq+1)-1` is at most `nnzmx`, `jaccapi` is written for
  `1..neq+1`, which is at most `jaccapneqp1`, and the tails are zeroed. `real jac(*)`/`integer ja(*)` keep the
  caller's integer kind (`jaccapj` is int64, matching `jacj`). There is no integer division, mixed precision or
  new automatic array. Forthon `gchange` copies the overlap with stride-aware `PyArray_CopyInto`, so slots are
  preserved when the leading dimension changes. My test T2 confirmed this: slot 1 hashes were unchanged after
  growing from neq 300 to 420 and from nnz 5335 to 8197.
- **`.v` docs.** Every variable has a units bracket and a `#` description. The continuation `#` lines are
  merged into the Forthon doc strings (checked with `getvardoc`). The attribute `+input` is on `jaccapture` and
  `jaccapskip` only. The group is appended at the end of `bbb.v`, so existing cited line numbers are unchanged.
- **MPPL hazards.** The added lines contain none of the substitution tokens (`float`, `break`, `while (`, `#` in
  strings). The only string is `"Jacobian_capture"`. There are no fixed-form overflows, and no new compiler
  diagnostics (per the build-log grep in the validation file, which I re-read).
- **AI-layer.** `openmp-jacobian.md` is factually right, and its line citations (`bbb/bbb.v:4221,4249,4252`,
  `bbb/oderhs.m:4676,4716,4738`) point at the stated lines.
  `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` from the worktree prints `OK`
  (exit 0). There are no skill, agent or hook changes. The code-facts commit (2cb855b) has the
  `AI-layer: code-facts` trailer, and `.claude/plans/**` is an artifact path. This is not a physics model, so no
  `physics-models.md` row is needed.
- **Plan facts.** The claims about `EvalDumpJac` are right: the `.v` signature `EvalDumpJac(FileName:string)`
  differs from the Fortran `(FileName,neq,yl,yldot00)`, and the routine uses `neq*neq` stack arrays, so it is
  not reusable. With `ftol=1e20` there is a single Jacobian (`ijactot=1` in every ftol run). The
  `ForceSerialCheck` caveat is documented. The plan should have been reviewed before coding. Reviewed now,
  apart from L-M1 it is sound.

## Observation for the epic (not a finding against this ticket)

The hook already shows the AIUE-8 symptom. On the Te box at the identical `sfsetnk` state, `jac_calc_parallel`
returned nnz=183 in my run and nnz=189 in the implementer's run, while serial `jac_calc` gives 169 in all six of
the implementer's runs. On the full problem, parallel and serial nnz are 3621751 and 3190290. In both cases the
parallel pattern holds entries that the serial one drops.

## What was checked and how

Scratch directory: `/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev47/`.

- **Provenance.** `git diff 5f0a633 HEAD -- '*.m' '*.v' '*.F90' '*.f' setup.py Makefile.Forthon` is empty.
  `0fac655` and `3865c79` have no source differences. The base worktrees are at 0fac655 and clean. The AIUE-47
  and AIUE-47-serial trees are clean, and their generated `.F` files are identical modulo `c!omp`.
  `direct_url.json` of each venv points to the expected tree.
- **AC1, full reproducer, serial, `ftol=1e20`.** `capture_check.py compare` with base-serial against
  AIUE-47-serial: PASS, all fields EQUAL, including `jac` b974ef0b…, `yldot` 64e38678… and
  `fnrm 0x1.eb37d428ec4f0p+0` (`ac1_serial_full.txt`).
- **AC1, D+C, serial, 3 Newton iterations.** PASS, fnrm sequence n=4 equal (`ac1_serial_dc.txt`).
- **AC1, D_only, OpenMP build.** `OMPParallelJac=OMPParallelPandf1=0`, 4 threads, `incpset=1`, 3 Newton
  iterations: PASS, `ijactot=4` (`ac1_omp_donly.txt`).
- **AC2, full reproducer, serial, hook on in the new build only.** Results still equal base. Slot 1:
  `src=jac_calc`, `from=sfsetnk`, `raw_times_inv_suscal_bitwise_eq_bbb_jac = True`, raw hash 711d35… differs
  from `jac` hash b974ef… (`ac2_serial_full.txt`).
- **AC2, Te box, OpenMP build, `OMPParallelJac=1`.** `src=jac_calc_parallel`, bitwise identity True
  (`ac2_omp_tebox.txt`).
- **Own script `edge.py` (independent of the tool), D_only, serial build.**
  - T1: `isupon=0` (neq 300). `suscal` is not all 1 (range 0.417 to 9.87e4), the identity holds, raw ≠ `jac`,
    and the CSR is valid (`ia(1)=1`, `ia(neq+1)=nnz+1`, monotone, `ja` in range, zero tails).
  - T2: neq grows to 420. Slot 1 is preserved bitwise, and the slot 2 identity holds.
  - T3: `gfree`, then a capture. No crash, slot 3 is valid, slots 1 and 2 are lost.
  - T4: overflow is counted but not stored.
  - T5: restart with `jaccapture=2, jaccapskip=1` and 3 Newton iterations gives seq [2,3] and from
    [psetnk, psetnk].
  - T6: `jaccapcur=0` after exmain, and `jaccapture=0` stops counting.
  - Output: `edge_serial.txt`.
- **Eager allocation (L-M1).** `ds/eager.py`.
- **Source reading.** `sfsetnk`/`psetnk`/`jac_calc`/`jac_calc_interface` (`bbb/oderhs.m`), `odesolve.m` call
  sites, `ppp/parallel.F90` (`InitParallel`, `jac_calc_parallel`), `ppp/omp_parallel.F90` parallel regions,
  `ppp/debug_parallel.F90` `EvalDumpJac`, `svr/svrut4.m` `rnrms`/`amudia`, `setup.py` `Omp`/flags, Forthon
  0.10.10 `Forthon.h` `gchange`, and the generated `bbb_p.F90`.
- **Validation log.** I re-read `docs/reviews/AIUE-47-validation.txt` in full. Its bookkeeping hashes are
  consistent: slot k of capture-all equals the single slot of skip=k-1. The tool does not assert this equality;
  I verified it by eye.

### Not independently verified (environment)

- The `--debug`/`--checkbounds` builds. I reasoned through the bounds instead.
- Linux/CI wheels.
- The MPI/PETSc builds. These paths do not reach `jac_calc_interface` according to the source.
- The D_mols reruns. These are covered only by the implementer's log.
