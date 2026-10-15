# AIUE-8 PRD – response to review round 2

Besides the round-2 findings, the owner made three decisions in this round:
- **Decision 7.** A1 (the reading of "nothing may change") is confirmed.
- **Decision 8.** The work splits into a Jacobian track and a Jacobian + RHS track, with separate tickets. The Jacobian
  is top priority and gates the epic. The RHS is a bonus.
- **Decision 9.** A2 is confirmed: the gate is bitwise agreement with serial, with a fallback gate the owner picks at
  the Phase 2 exit.

The revised PRD splits the scope (§4), the RCA (§7.4), CI gating (§7.6), the success criteria (§11) and the phases
(Phase 5 is the bonus) along the two tracks.

| Finding | Response | Where |
|---|---|---|
| P2-M1 bitwise gate feasibility unproven; RHS differences missing; scope rules contradict; A2 unconfirmed | **Fixed.** (1) The 1-thread evidence is restated as reproducing serial history, not as proving that N threads can match. The Ti/ni/up/ng evidence is limited to those equations on the Jacobian arm. (2) The RHS structural differences are added: chunks and core rings, `auxrange`, edge-only `bouncon`, no master refresh, disjoint `REDUCTION`, and the non-local boundary conditions in the deck. (3) §4 now excludes only *default values* of chunking switches, and OpenMP-only code changes are in scope. §9 escalates on (a) serial moving or (b) bitwise unreachable, and R2 points to §9(b). (4) A2 is confirmed by the owner as decision 9. "Is bitwise reachable?" is the Phase 2 exit decision, and the fallback gate is predefined in §11. | §1, §2, §4, §6.1, §6.3, §7.4, §9, §11, R2, Appendix 9 |
| P2-m1 conclusions beyond the data | **Fixed.** The `OMPJacNchunks=-1` run is described as still `schedule(dynamic)`. The race reading is softened to "consistent with a race or with uninitialised or incompletely copied worker state", and that is added as H6. "Deterministic but wrong" is qualified by the max-norm caveat and the fact that full-Jacobian stability was not checked. The H1 status is corrected. H5 is dropped as unlikely, because ownership is disjoint. The 15th-digit variation is noted as unexplained under R-H. | §1, §6.3, §6.4 |
| P2-m2 L1 wrong at default settings | **Accepted.** L1 is replaced by the reviewer's suggested lead: the Te-only impurity-radiation sink (`isimpon=7`). | §6.4 L1 |
| P2-m3 `ijactot` and deck description | **Fixed.** `exmain` resets `ijactot`. `yldot0` in `sfsetnk` is serial, the first Jacobian sets `ijactot=1`, and iteration-0 `f(u0)` goes through the parallel RHS. The RHS-arm row now names the measured quantity (`ffun` after `exmain`). The deck row describes the populate `exmain`, then `ftol=1e-8` and the later restore, which `testscript2`'s `itermx=3` relies on. A per-evaluation branch check is required. | §6.1, §6.2, §6.3, §7.2 item 1 |
| P2-m4 capture point, bitwise definition, repeat counts | **Fixed.** The capture point is the unscaled, unpermuted Jacobian from `jac_calc`/`jac_calc_parallel`, or the post-`exmain` arrays with the RCM permutation inverted. The scaling, normalisation and reordering facts are added to §6.1. Bitwise means equal IEEE-754 bit patterns: `±0` differ, and any NaN or Inf fails. The repeat counts are stated once, in §11: 30/30 for the Te box and full problem at 4 threads, 5/5 at 2 and 8 threads, and 5/5 for other configurations. | §6.1, §7.2, §11 |
| P2-m5 run environment incomplete | **Fixed.** The rate files `ehr2.dat` and `C_rates.adas` are not in the repo, and their source is a ticket decision (A5). `mist.dat` is needed from the working directory. The harness prepares a run directory with the case files. `python -I` needs the case directory on `sys.path`. The commit and do-not-commit file lists are explicit. | §6.3, §6.6, §7.1, R6, A5 |
| P2-m6 CI cost basis | **Fixed.** The 12 s figure is labelled iteration 0 only. The real cost includes ≥ 3 iterations plus serial references and is measured in Phase 4. The nightly fallback is stated. | §6.3, §7.6, R5 |
| P2-m7 untracked AI-layer and AIUE-9 items | **Fixed / tracked.** `CLAUDE.md` line 38 and testing.md's "no tests in this repository" are added to the code-facts updates. The AIUE-9 PRD lines to mirror (~191, ~662-667, ~697) are listed as an action for that PRD's owner on its own branch. | §4 Integration, §11, §13 |
