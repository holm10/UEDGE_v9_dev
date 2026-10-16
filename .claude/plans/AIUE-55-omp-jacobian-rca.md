# Feature: AIUE-55 — Jacobian RCA and Phase 2 exit decision

**Type**: Investigation / documentation (artifact only). **Default results**: unchanged (no product code).
**Branch / worktree**: `feature/v9-AIUE-55-omp-jacobian-rca` @ `../uedge-wt/AIUE-55` (stacked on AIUE-54 → AIUE-50 → AIUE-46).

Tasks: (1) test H1–H4, H6, L1–L3 with minimal experiments (AIUE-50 scan + E1–E3, the afracs=0 experiment, the swap
build, chunking experiments); (2) P3-m3 serial history experiment; (3) residual mechanism (emulation, carrier search,
`-ffp-contract=off`); (4) RCA Jacobian section with root causes, refuted hypotheses, fix tickets; (5) prepare the
exit decision (decision 9) with options and evidence — the owner decides; (6) file one fix ticket per independent
root cause (AIUE-56 exists; AIUE-60, AIUE-61 filed).

Acceptance (ticket): minimal experiment per root cause removes the mismatch (C1: swap; C2: `-ffp-contract=off`);
serial impact stated per fix; owner's exit decision recorded (here: prepared, **pending the owner**); fix tickets filed.
