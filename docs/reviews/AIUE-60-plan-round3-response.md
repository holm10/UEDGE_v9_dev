# AIUE-60 plan review round 3 — response

Review: `docs/reviews/AIUE-60-plan-round3.md` (APPROVE, 0/0/3 optional minors). All three folded in before implementation.

| Finding | Resolution | Where |
|---|---|---|
| L3-m1 re-run rule confirms on a 1-run margin; false sentence | Pre-registered: margin n60 − n56 ≥ 2 at K=5 confirms (5 vs 0 always confirms); margin 1 → K=10 more on both builds, confirmed if AIUE-60 violates more there; else pre-existing. The "single unlucky run" sentence is replaced by the false-confirmation probabilities and "errs toward failing" | Plan Testing 3 |
| L3-m2 global tau_eff; G3 looser than G1 | Per-row `tau_eff(r) = TAU + |sf_omp(r)/sf_ser(r) − 1|`; G3 is `g1_verdict(base run) == "FAIL"` with the same strictness. Re-checked offline on Probe C: `ni` and `full` base runs FAIL, serial vs itself PASS | Plan Testing 4; `AIUE-60-clip-check.py` |
| L3-m3 Class X attribution; gate (c) adapter | Attribution corrected (AIUE-56 jac 4 threads 5/5; base build 3/3; AIUE-54 `k2_all` 2/4/8 both arms; AIUE-58 probes). New `docs/reviews/AIUE-60-flow-gates.py` evaluates gates (a), (b), (d), (f) per run and section from both `flow.json` files, applies the mechanical fallback, and stages symlinked `serial/` + `run*/` directories to run `AIUE-56-c1-gate.py` for gate (c) | Plan Testing 3; `AIUE-60-flow-gates.py` |
