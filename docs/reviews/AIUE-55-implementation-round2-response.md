# Response to AIUE-55 implementation round 2 (REVISE: 0 blocker, 2 major, 2 minor)

| Finding | Response |
|---|---|
| I2-M1 static partition misreported as non-deterministic; not offered | Corrected: the contiguous-chunk row now says the runs are bitwise identical to each other (`te_contig_R0` 3/3, `m2/tebox_static.txt`); B is restricted to the default dynamic chunks (full `t_c1_dflt_1` vs `_2`: 70 entries). New option **F, static partition + tolerance**: meets PRD §11's fallback as written on this evidence, OpenMP-only, needs the same crash fix as E; gaps stated (load-balance cost, 2/8 threads, fresh CI sessions, Newton iterations). Added as a column in the per-configuration table and to the recommendation. |
| I2-M2 +18 % is an unlabelled estimate | Labelled as estimates: ≈ 4.4 % × T (+18 % at 4 threads, +35 % at 8), for a configuration that was not run (crash) and not emulated at R=`ubw` with 4 chunks; excludes the cost of leaving dynamic scheduling. The 16-chunk figure is "measured" with its basis (two whole-process timings per arm, ~9 s spread). PRD §9's measured Jacobian times are pending (AIUE-61). |
| I2-m1 crash details | Fixed: arrays at `ppp/omp_parallel.F90:672,675`, `firstprivate` at `:713-714`, sized at `:321`; full problem only (Te box runs with `OMPJacNchunks=-1`); cause marked as inferred, no backtrace. |
| I2-m2 scope of "reachable" | Stated where claimed (one evaluation, 3 runs, 4 threads, Te box + full) and in the evidence bullet with the scratch commits per row; the extra `isjacreset` call is left for AIUE-61 to decide. |
| Residual minors | F9 row (AIUE-50 section) corrected to match H3 and the code (`mombal` only for `isimpon=5`, `bbb/pandf_plasma_momentum.m:669-671,701-703`); column loop starts at `bbb/oderhs.m:1095`. |
