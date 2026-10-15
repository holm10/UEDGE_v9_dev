# AIUE-47 implementation review, round 1: response

Review: `docs/reviews/AIUE-47-implementation-round1.md` (verdict REVISE: 0 blocker, 1 major, 3 minor).
All four findings are fixed; none is rebutted. Fortran, `.v` text, plan and tool checks are in `3625b48`;
the context doc in `b085978` and `460aa5f` (code-facts, lock prune); tool follow-ups in `d137d53`
(no crash on unallocated arrays when nothing was captured) and `531de6f` (compare skips capture-only fields).
Round-2 validation is appended to `docs/reviews/AIUE-47-validation.txt` (section "ROUND 2"):

- AC1 (switch off) bitwise equal to `v9-develop`: reproducer full case (ftol and 3 Newton iterations) and D_only
  (ftol and newton), serial and OpenMP builds (OMP switches 0, 4 threads): 8/8 PASS.
- AC2 identity `raw * (1/suscal)[ja-1] == bbb.jac` bitwise: serial `jac_calc` on the reproducer (both builds),
  `jac_calc_parallel` on the reproducer and Te box: PASS; hook-on results still equal base.
- L-M1: `jaccapture=1000` with one Jacobian allocates `jaccapnslot=1` (D_only: 134472 bytes, shape (8194, 1);
  reproducer: 51399464 bytes serial, 59111720 bytes parallel). Te box with 4 Jacobians and `jaccapture=1000`:
  `jaccapnslot=4` (growth 1->2->4), `jaccapture=3`: 3; slot hashes identical to round 1 and to the skip runs.
- I-m1: negative test (D_only, `issfon=0`, `--capture 4`, no Jacobian) exits 1 with `captured_at_least_one = False`.

| Finding | Resolution | Where |
|---|---|---|
| **L-M1** (MAJOR) eager allocation of all `jaccapture` slots | **Fixed, option (a).** The slot dimension now grows only when the slot being filled does not exist: `jaccapnslot = min(jaccapture, max(islot, 2*jaccapnslot))` (doubling, capped at `jaccapture`), so at most twice the filled slots are allocated and N captures reallocate O(log N) times. `jaccapnnzmx`/`jaccapneqp1` grow as before; `gchange` keeps the stored slots (verified again by the bookkeeping runs, where nnz and the slot count grow between captures). `jaccapture` is documented as a cap only, with the memory cost. | `bbb/oderhs.m` `jac_capture`; `bbb/bbb.v` group header, `jaccapture`, `jaccapnslot`; plan (Design and Memory); `.claude/context/openmp-jacobian.md` |
| **I-m1** (minor) tool passes a capture run that captured/checked nothing | **Fixed.** With `--capture K>0` the child emits run-level checks and the run FAILS (exit 1) unless `jaccapn>0`, every slot has a caller tag (`sfsetnk`/`psetnk`), the allocated slots satisfy `jaccapn <= jaccapnslot <= min(jaccapture, 2*max(1,jaccapn))`, and (ftol mode) the bitwise identity was actually evaluated. A negative test (D_only, `issfon=0`, no Jacobian) now exits 1. | `tests/deterministic_omp/tools/capture_check.py` (`child`, `capture_checks`) |
| **I-m2** (minor) "raw d(yldot)/d(yl)" overstates the capture | **Fixed.** `jaccapv` now says it holds the matrix returned by `jac_calc`/`jac_calc_parallel`: finite-difference `d(yldot)/d(yl)` including the `-1/dtuse`, `-1/dtphi` and `-nufak` diagonal terms, with entries `|J*sfscal| <= jaccliplim` dropped, so the pattern depends on `sfscal`. It also states (without changing it) that serial `jac_calc` clips with `sfscal` of the row (`sfscal(ii)`, `bbb/oderhs.m:1187`) and `LocalJacBuilder` with `sfscal` of the column (`sfscal(iv)`, `ppp/parallel.F90:292`). The context doc says the same and no longer calls `bbb.jac` "not the raw Jacobian" in the loose sense. | `bbb/bbb.v` `jaccapv`; `.claude/context/openmp-jacobian.md` |
| **I-m3** (minor) behaviour after `gfree` undocumented | **Fixed.** The `.v` group header, the `jac_capture` comment and the context doc state that after `bbb.gfree("Jacobian_capture")` the stored slots are gone (the next capture reallocates zero-filled arrays) and `jaccapcount = jaccapn = 0` must be reset before reuse. | `bbb/bbb.v`; `bbb/oderhs.m`; `.claude/context/openmp-jacobian.md` |

## Note on the memory figure

The request gave the per-slot cost as "(8+4) bytes x nnz + 4 x (neq+1)". In this build integers are 8 bytes
(`-fdefault-integer-8 -DISZ=8`, see the build logs; the review also notes `jaccapj` is int64), so the documented
figure is about `16*nnz + 8*(neq+1)` bytes per slot (~51 MB on the 44352-equation reproducer, serial; ~58 MB on
the parallel path whose nnz is larger). The measured D_only slot is 134472 bytes = 16*8194 + 8*421.

## Observation for the epic

The row-versus-column `sfscal` in the clipping test is a real serial/parallel difference in `jac_calc` vs
`LocalJacBuilder`. With the default `jaccliplim = 0` it only matters where `sfscal` is zero or where an element is
exactly zero, but AIUE-49/the root-cause tickets should keep it in mind when comparing sparsity patterns.
