# AIUE-60 implementation review round 1 — response

Review: `docs/reviews/AIUE-60-implementation-round1.md` (REVISE, 1 blocker / 0 major / 2 minor). The blocker needs a
design change, so this round adds **Amendment 1** to the plan for re-review; no code changed yet.

| Finding | Resolution | Where |
|---|---|---|
| I1-B1 `com` threadprivate scalars add an 80-byte `/ompcommonscalarcopy/` in `compy.so`; `bbb`'s 728-byte copy overwrites `/iotable/` | Accepted. Amendment 1: (1) the 10 `com` timers are no longer threadprivate. Their updates go through a new `acctim(acc, dt)` helper in `com/misc.m` with a fixed-form `c$omp atomic` sentinel: a directive in the OpenMP build, a comment in serial. Call sites are rewritten line-neutrally. (2) `iflag_aph` is replaced by a local `iflagl` in `rqa`/`rra`/`rsa` (line-neutral), so neither `com` nor `aph` defines the common. (3) The invariant (only `bbb` and later, smaller blocks may define threadprivate scalars) goes into `openmp-jacobian.md` and `variables-forthon.md`. (4) Two new pre-registered gates: G-common (static: definers and block sizes in load order, `nm` + generated sizes, with AIUE-56 and pre-amendment controls) and G-iotable (the reviewer's probe: 0 changed words). TSan, Probe S (updated expectations), timing (report), and every earlier gate are re-run on the amended tree. Options 1–3 and why they were rejected are in the plan. A follow-up ticket text for Forthon is proposed | Plan "Amendment 1" |
| I1-m1 B2/B4 not exercised in a threaded run | Accepted. Stated as untested at run time in the plan, and will be stated in the validation record and the PR, with the reasons the risk is low | Plan Amendment 1 (I1-m1) |
| I1-m2 two deviations not labelled | Accepted. (i) The `0fac655` base substitution with its reasoning, and (ii) the `workh` bound text difference in the generated serial code are listed as deviations in the plan, and will be in the validation record | Plan Amendment 1 (I1-m2) |
