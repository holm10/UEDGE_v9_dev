# AIUE-8 PRD – response to review round 1

Besides the review findings, the PRD changed for two other reasons:
- The owner supplied the reproducer `tests/deterministic_omp/`, and planning ran a short characterisation with it.
  The results are in §6.3.
- A new binding decision 6 says the PRD documents the issue and the test logic, and the tickets design the test flow.

| Finding | Response | Where |
|---|---|---|
| P1-M1 OpenMP RHS under-weighted; RHS check hit the serial path | **Fixed.** The "points first at the Jacobian" claim is removed. The iteration-0 `fnrm` dependence on the Jacobian through `sfsetnk` is now documented, with `bbb/oderhs.m:2292`. The `ijactot>0` fallback is documented. The test flow requires the RHS to be measured after `ijactot>0`, with a check that the parallel branch ran. There are two arms (Jacobian-only, and Jacobian + RHS), and ≥ 3 Newton iterations. H1 covers RHS chunks. Planning evidence: the OpenMP RHS disagrees with serial in about 2200 Te rows. | §1, §6.1, §6.3, §6.4 H1/H5, §7.2 items 1 and 3 |
| P1-M2 CheckJac means bitwise; "same structure" was false | **Fixed with option (a), made consistent.** Agreement with serial, bitwise, is now the primary gating criterion. It is no longer out of scope. The "same structure" sentence is replaced by a list of the structural differences. Removing them is out of scope unless the RCA shows one breaks agreement. Planning shows that 1-thread OpenMP already equals serial bitwise, so the target is achievable. An escalation exists for when it is not (R2). | §2 principle 2, §4 out of scope, §6.1, §9, §11, R2 |
| P1-M3 "nothing may change" incoherent for the OpenMP RHS; serial ambiguous | **Fixed.** Serial means both the `--serial` build and the OpenMP build with the switches off. OpenMP results may change only towards bitwise equality with serial. OpenMP quantities that equal serial today must keep doing so. Everything else escalates. This is marked A1 for owner confirmation. | §2, §9, Appendix A1 |
| P1-M4 no runnable serial-bitwise check | **Fixed.** The new §7.3 is a serial old-vs-new check: two venvs, both builds, the reproducer configurations plus ≥ 3 coverage cases, bitwise comparison, exit codes. It is required in every PR that touches Fortran. `pytests` is explicitly not a substitute. | §4, §7.3, §11, Phase 1 and 3 |
| P1-M5 CI detection statistical and unquantified | **Fixed.** The primary check compares against serial and is deterministic: the pre-fix full problem disagrees on every run (7/7 in planning). CI is required to fail in 20/20 runs on the pre-fix code and on a seeded race. Post-fix acceptance is 0/30 for the Te box and the full problem, which bounds the residual below 10 % at 95 % confidence. | §7.6, §11, A2 |
| P1-M6 story 6 implies a skill edit on a ticket branch | **Fixed.** Story 6 is reworded to documentation in `openmp-jacobian.md`. The `validate`/`code-review` edits are out of scope here and go in a later `feature/v9-ai-*` PR. | §4, §5 story 6, §13 |
| P1-M7 AIUE-9 conflicts | **Fixed in this PRD.** It states that AIUE-8 owns the RCA of the randomness, the `Test criteria: changed` rule or an unguarded listing for `tests/deterministic_omp/`, one tool (the AIUE-8 test flow) for `validate` §4, and that thread pinning is overridden. Mirroring it in the AIUE-9 PRD is an action for that PRD's owner on its own branch. | §13 |
| P1-m1 wrong facts | **Fixed.** `ParallelMatfac` (`bbb/bbb.v:4133`, `bbb/oderhs.m:4656`); `idx*` at `bbb/bbb.v:2002-2008` including `idxtg`; `-fopenmp` from `FARGS`/`CARGS` (`setup.py:79,82`); `OMP_NUM_THREADS` sets the team size; the `dtold` and `ue_*` candidates are dropped, because the heuristic scan is replaced by the planning sentinel scan. | §4, §6.1, §6.4, §7.2, §7.6 |
| P1-m2 missing leads | **Fixed.** Added L1 (the `*old` values captured in box loops), L2 (`wk`/`yl_check`) and L3 (`OMPTimeLocalJac` indexing). | §6.4 |
| P1-m3 `fnrm` "bitwise" vs 16 digits | **Fixed.** Both are compared: float64 bitwise, and the 16 printed digits. | §7.2 item 1, A2 |
| P1-m4 thread counts inconsistent | **Fixed.** 2, 4 and 8 throughout. 16 is a non-gating indicator. | §7.2, §11 |
| P1-m5 CI budget and pip deps | **Fixed.** The budget is ≤ 20 min, measured, with tunable repeat counts. The per-repeat cost is stated, and h5py is listed. | §7.6, §8 |
| P1-m6 R4 runtime wrong | **Fixed.** libgomp for the Fortran code on both platforms; libomp only possibly, through the C toolchain on macOS. | R4, §8 |
| P1-m7 no risk for the reproducer | **Fixed.** The reproducer has arrived. R5 covers size, speed and trimming. | §7.1, R5 |
| P1-m8 diagnostics alter solver state | **Fixed.** Diagnostic runs are kept separate from measured runs, and `ForceSerialCheck` is noted as unusable as a baseline. | §6.1, §7.2 item 6 |
