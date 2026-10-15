# Response to AIUE-56 implementation round 1 (REVISE: 0 blocker, 4 major, 4 minor)

| Finding | Response |
|---|---|
| I1-M1 code-facts update missing; drift check 6 problems | Fixed: `openmp-jacobian.md` gains a "Copy order matters" bullet (scalars before arrays, why, the debug-switch caveat, `OMPPandf1Rhs` never copies but always follows a Jacobian because `OMPParallelPandf1=1` forces `OMPParallelJac=1`); moved `ppp/omp_parallel.F90` references fixed; the STALE range in `mppl-fortran.md:69` corrected to 908-936 after re-reading; lock updated (47e02cc, 205bd09). `check_context_refs.py --changed origin/v9-develop` OK. |
| I1-M2 no interleaved timing | Done: 8 interleaved runs each, full problem, 4 threads, one at a time: median base vs new ratio 0.995 — no slowdown. |
| I1-M3 OpenMP-build pytests not run | D_only run with both OpenMP builds, one process per test file: identical per-file outcomes (the same 3 failures in both). Other suites not run (time); the bitwise serial check covers D+C, D_mols, fulltest and slab cases in the OpenMP build. |
| I1-M4 validation record incomplete | Added: residual characterisation (Te box 0–2 entries, always row te(4,20); full problem 903–2428 per run, Te rows only, mostly te/ni; no other section differs), jacrhs summary (fnrm/yldot equal serial; Jacobian residual only), `--itermx 3` table (sfscal equal; printed fnrm differs from iteration 1 on — the Newton path moves with the residual), the epic met/not-met table, the RHS-arm C1 statement. |
| I1-m1 RHS-only parallel never copies | Not reachable: `OMPParallelPandf1=1` forces `OMPParallelJac=1` (`ppp/parallel.F90:30-36`); stated in the context bullet. |
| I1-m2 no bounds-checked run | Not done (time); the reviewer checked array sizes statically. Left for the owner. |
| I1-m3 pinned harness commit | Fixed: the record names both cf23ddf and de57d59 (docs-only difference). |
| I1-m4 gate script `zip`; scratch-only scripts | Fixed: differing Jacobian lists are a FAIL; the protocol driver is committed as `docs/reviews/AIUE-56-run_protocol.sh`. |
