# AIUE-47 — Raw-Jacobian capture hook (off by default)

Epic AIUE-8 (non-deterministic OpenMP Jacobian), spec task T2
(`docs/specs/AIUE-8-investigate-non-deterministic-openmp-jacobian.md` on `feature/v9-AIUE-8-planning`).
Branch `feature/v9-AIUE-47-raw-jacobian-capture`, base `origin/v9-develop`.

## Problem

`jac_calc` is not callable from Python. `bbb.jac` after `exmain` is the last Jacobian after `sfsetnk`
(columns scaled by `1/suscal`) or `psetnk` (columns `1/su`, rows `sf`, row-normalised, RCM-permuted/LU'd).
The AIUE-49 harness needs the raw finite-difference Jacobian of every evaluation, serial and parallel.

## Facts checked in the code

- `jac_calc_interface` (`bbb/oderhs.m`) is the single point that sees both `jac_calc` (serial) and
  `jac_calc_parallel` (`ppp/parallel.F90`, OpenMP build with `ParallelJac=1`). Its only callers are
  `psetnk` and `sfsetnk` (`bbb/oderhs.m`), which are called from `nksol` (`svr/nksol.m`, via `pset`) and
  from `odesolve.m` (`sfsetnk`). None of them runs inside an OpenMP parallel region: the only
  `!$omp parallel` regions in the tree are in `ppp/omp_parallel.F90` (`InitOMPJac`, `jac_calc_omp`,
  `OMPPandf1Rhs`) and they close before `jac_calc_parallel` returns. The PETSc driver
  (`svr/petsc-uedge.F90`) does not call `jac_calc_interface`. So the capture state is written by the master
  thread only and is **not** `+threadprivate`.
- Other solvers (`vodpk`, `daspk`, `jacvnk`, `jacd1`...) call `jac_calc` directly and are not captured.
  The hook is for `svrpkg='nksol'` (the solver the epic investigates).
- With `ftol=1e20`, `nksol` stops in `nkstp0` (`fmax <= 0.01*ftol`) before the first `pset`, so the only
  Jacobian of the run is the `sfsetnk` one, and post-`exmain` `bbb.jac(k) = raw(k) * (1/suscal(ja(k)))`
  (`amudia` column scaling with `sf(i) = 1./su(i)`; `rnrms` does not modify `jac`). The check therefore
  recomputes `raw * (1.0/suscal)[ja-1]` in numpy with the same IEEE operations and compares bitwise.
- `ppp` `EvalDumpJac` (`ppp/debug_parallel.F90`) evaluates a *new* full-bandwidth serial Jacobian into
  stack arrays of size `neq*neq` and writes ASCII; it captures nothing from a run, cannot see the parallel
  result, and its `.v` signature (`FileName` only) does not match the Fortran one
  (`FileName, neq, yl, yldot00`). Not reusable; left untouched.
- Caveat for `jac_calc_parallel`: with `ppp.ForceSerialCheck>0` it overwrites the parallel result with a
  serial `jac_calc` result; with `ppp.CheckJac>0` it only returns if they agree. The source tag records
  which routine `jac_calc_interface` called, so measured runs must keep those switches off (the AIUE-49
  spec already requires that).

## Design

New group `***** Jacobian_capture:` at the end of `bbb/bbb.v` (keeps all cited `bbb.v` line numbers),
new subroutine `jac_capture` at the end of `bbb/oderhs.m`.

- `jaccapture` (input, default 0): maximum number of Jacobians kept; 0 = off. When 0 the hook is a single
  integer test and nothing else runs (bitwise-unchanged results).
- `jaccapskip` (input, default 0): number of Jacobians (counted while capture is on) skipped before storing
  starts. "Keep every Jacobian" = large `jaccapture`, `jaccapskip=0`; "keep only the k-th" =
  `jaccapture=1, jaccapskip=k-1`.
- `jaccapcount`: Jacobians seen by `jac_calc_interface` while capture is on; `jaccapn`: Jacobians stored
  (slots `1..jaccapn`). Stored are the Jacobians with sequence numbers `jaccapskip+1 .. jaccapskip+jaccapture`
  (first-N, no ring buffer: deterministic and simple). Counters are not reset by `exmain`; the user restarts
  by setting `jaccapcount=0, jaccapn=0` (memory is kept and reused).
- Storage per slot `k` (2-D dynamic arrays, leading dimension = largest captured size, reallocated with
  `gchange("Jacobian_capture",0)`, which preserves already-stored slots; unused tails are zeroed):
  `jaccapv(:,k)` values, `jaccapj(:,k)` column indices, `jaccapi(:,k)` row pointers (CSR, 1-based, exactly
  as `bbb.jac/jacj/jaci`), `jaccapneq(k)`, `jaccapnnz(k)`, `jaccapsrc(k)` (1 = `jac_calc`,
  2 = `jac_calc_parallel`), `jaccapfrom(k)` (1 = `sfsetnk`, 2 = `psetnk`), `jaccapseq(k)` (its sequence number).
- `jaccapcur` is the caller tag set to 1/2 by `sfsetnk`/`psetnk` just before their `jac_calc_interface`
  call and back to 0 after (a plain integer store; no effect on results).
- The capture runs after `ttotjf` is accumulated, so the copy time is not charged to Jacobian timing.
- Memory: ~3.2M nonzeros for the full reproducer case, about 3.2M*(8+8) bytes per slot (~51 MB); four slots
  are ~200 MB.

## Tasks

1. `bbb/bbb.v`: add the group with units brackets and `#` descriptions (not `+threadprivate`, say why).
2. `bbb/oderhs.m`: hook in `jac_calc_interface`, caller tags in `sfsetnk`/`psetnk`, new `jac_capture`.
3. `tests/deterministic_omp/tools/capture_check.py`: generic child/compare/verify tool
   (fresh `python -I` per run, empty `HOME`, SHA-256 of raw bytes, `float.hex`, printed `fnrm` sequence).
4. Build `--serial` and OpenMP from two worktrees at the same commit.
5. Validation (output in `docs/reviews/AIUE-47-validation.txt`):
   - AC1: base vs new, switch off: reproducer full case (ftol=1e20, and itermx=3 for the fnrm sequence),
     D_only `nonog`, D+C `nonog_carbon`, D_mols `nonog_mols` (ftol=1e20 and itermx=3), serial build and
     OpenMP build with `OMPParallelJac=OMPParallelPandf1=0`.
   - AC2: switch on, ftol=1e20: capture slot 1 times `1/suscal` equals `bbb.jac` bitwise (serial path,
     both builds); OpenMP build with `OMPParallelJac=1`: `jaccapsrc=2` and the same identity holds.
     Also a multi-Jacobian run (itermx>0) to show sfsetnk + psetnk captures and `jaccapskip`.
   - AC3: MPPL hazard grep on the added lines.
6. `.claude/context/openmp-jacobian.md`: document the switch (separate code-facts commit), then
   `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`.
