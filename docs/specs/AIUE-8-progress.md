# AIUE-8 — unattended run progress log

Run started 2026-10-15 ~00:05 PDT, while the owner is away (6–7 h). Nothing is pushed, no PRs are opened, nothing is
merged into `v9-develop`: every ticket lives on a local branch and worktree under `../uedge-wt/`, stacked where it
depends on an unmerged ticket. Each ticket gets a fresh `uedge-reviewer` adversarial review before it counts as done
(reports in that ticket's `docs/reviews/`). Jira: In Progress while worked on, **In Review** once the adversarial
review approves (awaiting the owner's review / PR). Owner decisions are prepared, never taken.

## Status board (updated 03:10)

| Ticket | Branch (local, not pushed) | State | Notes |
|---|---|---|---|
| AI layer | `feature/v9-ai-adversarial-ticket-review` | **APPROVED** (r2) | Review gates in `end-to-end-feature`, `execute`, `plan-feature`, `implement-fix` |
| AIUE-46 case | `feature/v9-AIUE-46-omp-reproducer-case` | **APPROVED** r1 → Jira In Review | |
| AIUE-47 capture hook | `feature/v9-AIUE-47-raw-jacobian-capture` | r1 REVISE → fixed (lazy slots) → r2 review running | |
| AIUE-49 harness core | `feature/v9-AIUE-49-omp-harness-core` (on 46) | **APPROVED** r3 → Jira In Review, tip `de57d59` | `check_arm`, strict comparator |
| AIUE-50 shared-state scan | `feature/v9-AIUE-50-shared-state-scan` (on 46) | r1 REVISE (doc-level; C1 confirmed) → fixes queued after the M2 hunt | **found root cause C1** |
| AIUE-52 test flow | `feature/v9-AIUE-52-omp-test-flow` | r2 REVISE (core API mismatch) → being rebased onto the core | |
| AIUE-53 serial check | `feature/v9-AIUE-53-serial-bitwise-check` (on 49) | r1 REVISE → fixed, rebased → r2 review running | 42 cases incl. Newton iterations |
| AIUE-54 characterisation | `feature/v9-AIUE-54-omp-characterisation` (on 50) | r1 review running | K=20 pre-fix rates |
| AIUE-55 RCA | `feature/v9-AIUE-55-omp-jacobian-rca` (on 54) | drafted (uncommitted); waits for the M2 findings | **owner decision 9 prepared here** |
| AIUE-56 fix (C1) | `bugfix/v9-AIUE-56-omp-jacobian-fix` | fix committed `4fae2f9`; plan review escalated after r3 (verification detail, applied); validation running | C1 gate PASS on all Te-box runs so far |
| AIUE-57 CI job | `feature/v9-AIUE-57-omp-ci-job` (on 52) | subagent implementing | can't run on GitHub without a push |
| AIUE-51 / 58 / 59 / 48 | — | not started (optional / bonus / owner task) | the C1 fix also fixes the Te-box RHS arm |

## Log

- **00:05** Reference builds of `v9-develop` (serial + OpenMP) in `../uedge-wt/venvs/base-{serial,omp}`, built with
  Homebrew LLVM clang + gfortran 15 (~2 min each). Build helper: `../uedge-wt/build_uedge.sh`.
- **00:10** AI-layer branch committed (review gates).
- **00:15** Finding: the rate files `ehr2.dat` and `C_rates.adas` are **already tracked** in
  `builder/test/Forthon_cases/Forthon_case5/`, byte-identical to the owner's copies. No download or env var needed
  in CI. (PRD §6.3/§7.1 said the repo doesn't bundle them.)
- **00:20** Serial full problem: `iter=0 fnrm=1.918820629111277` (matches PRD), ~31 s.
- **00:25** AIUE-46: trimmed data 4.5 MB total; bitwise-identical fingerprints vs original for full problem, Te box,
  `itermx=3`. OpenMP Te box at 4 threads reproduced: 3 runs → fnrm 0.1742, 0.1622, 0.1441 (serial 0.3221), different
  sparsity each run.
- **00:30** Gotcha found: when stdout is redirected to a file, the Fortran runtime's buffered output overwrites lines
  Python printed. Tools write results to files instead.
- **00:20** User asked about parallel delegation. Switched to the planned parallel waves: AIUE-47 and AIUE-50 to
  subagents (Wave 1/2), then AIUE-52 and AIUE-53 (Wave 3) once the harness core existed. The main session runs the
  adversarial reviews, the integration, and the critical path.
- **00:30** AIUE-49 harness core works: Te box check in 4.4 s (exit 1, all mismatches te/te); serial vs serial exit 0;
  full problem check ~70 s.
- **00:30** New data (full problem, 4 threads, 2 OMP runs): printed fnrm stable (1.535419111648367, as the PRD said),
  but the **Jacobian itself is not run-to-run stable**: 345k Te-row entries differ between the two OMP runs, and the
  OMP pattern has ~498k extra Te-row entries vs serial (3.69M vs 3.19M nonzeros). Only Te rows; all column equations.
- **00:35** **Lead for the RCA (L1 confirmed as dominant):** Te box with `bbb.afracs=0` (impurity radiation sink of
  `isimpon=7` zeroed): the 1e43 entries vanish and `get_fnrm()` is bitwise equal to serial in 3/3 OMP runs. Remaining
  differences are round-off level: serial has 5 entries of 4.547e-05 (≈ one ulp of yldot / dyl) where OMP has exact 0,
  3 entries differ in the 8th digit, and one tiny entry moves between OMP runs. So two mechanisms: **M1** gross, in the
  isimpon=7 radiation path on worker threads; **M2** history-dependent ulp noise in local pandf, present in serial too
  (bears on PRD P3-m3 and the owner's decision 9: whether bitwise equality with serial is reachable). Forwarded to the
  AIUE-50 agent.
- **00:35** Checked and ruled out as the cause here: the clip index difference (`sfscal(ii)` serial vs `sfscal(iv)`
  parallel) — `jaccliplim=0` so it has no effect on this case (still a latent bug for jaccliplim>0); `del` vs
  `delperturb` — both 1e-8.
- **00:40** AIUE-46 adversarial review: APPROVE, 0/0/8. Fixed all minors (relative rate path for deep checkouts,
  fingerprint hashes yldot before get_fnrm, README corrections, provenance hashes). Jira → In Review.
- **00:45** AI-layer review round 1: REVISE (5 major): "done" must be defined by APPROVE not by commit; fallback when an
  agent can't spawn a reviewer; run budget + "not independently verified" category; re-review after post-APPROVE
  edits; implement-fix/execute/plan-feature ungated. All fixed in `4e191a7`; round 2 running.
- **00:55** AIUE-47 done by subagent: capture hook (`bbb.jaccapture`, `jaccapv/j/i`, per-slot source/caller), default
  off bitwise-neutral on the reproducer + D_only/D+C/D_mols in both builds; captured×(1/suscal) == bbb.jac bit for bit.
- **01:00** AIUE-49 harness now compares the raw captured Jacobians. Te box, 3 Newton iterations: only 2 Jacobians
  (sfsetnk + one psetnk); the OMP psetnk Jacobian differs from serial in 1 entry, the sfsetnk one in ~40.
- Note: machine load average ~75 on 14 cores while 6–7 agents run; timings measured now are inflated.
- (Timestamps above were corrected: some had been written ahead of the real clock.)
- **01:10** AIUE-53 (serial check) and AIUE-52 (flow) delivered by subagents; full matrix: ti/ni/up/ng PASS on both
  arms at 2/4/8 threads; every Te configuration FAILs in Te rows only; the RHS arm crashes (SIGSEGV) for te and te+phi,
  overflows on the full problem at 2 threads. Phi can't be isolated without Te (all phi-without-Te isolations fail in
  serial: "Jacobian row = 0").
- **01:20** **ROOT CAUSE C1 found (AIUE-50 subagent), confirmed on a scratch build:** `OMPJacBuilder` copies the
  threadprivate arrays before the threadprivate scalars (`ppp/omp_parallel.F90:681-693`). The generated
  `OmpCopyPointer<var>` writes `(1:n)` on each worker with the worker's own `n`; for the 12 `api` `Imslwrk` spline
  arrays `n` is a threadprivate scalar still at its DATA default on the workers, so they get element 1 + zeros, and the
  `isimpon=7` impurity radiation (Te residual only) is evaluated on empty tables (emissbs = 1.0 instead of 1.9e-35).
  Swapping the two copy blocks → Te-box Jacobian bitwise equal to serial (pattern, fnrm) except 1–2 tiny entries.
  Independent review confirmed: exactly these 12 arrays in all packages; the swap alone suffices; it also fixes the
  RHS arm on the Te box.
- **01:20** K=20 pre-fix rates at 4 threads: Te box 0/20 agree, 20 distinct results; full 0/20 agree, 16 distinct
  fnrm in 20 runs (PRD said 7/7 equal — corrected in AIUE-54).
- **01:55** P3-m3: serial Jacobian is bitwise insensitive to outside history (40 random local pandf evaluations + a
  full pandf before exmain). Residual after the C1 swap (M2): Te box 0–2 entries (row te(4,20)); full problem
  860–1800 Te-row entries at ~1e-7 relative, varying run to run, sfscal/fnrm equal to serial. Even one contiguous chunk
  per thread leaves it → likely another per-thread state effect (C2?) — AIUE-50 agent investigating.
- **02:15** Several review rounds in flight; the plan-stage gate for AIUE-56 caught a weak verification protocol twice
  (pre-registered C1 gate now: static scan, serial check, magnitude and deviation bounds, check_arm).
- **02:35** AIUE-56 fix committed (`4fae2f9`: copy threadprivate scalars before arrays in `OMPJacBuilder`). Static scan:
  12 copy-order hazards on `base-omp` → **0** on AIUE-56. C1 gate (pre-registered: max|J| Te rows ≤ 10× serial and every
  differing entry ≤ 1e-6 × serial row max): **PASS** in Te box K=30 at 4 threads, K=5 at 2 and 8 threads, `te`, `te_phi`
  (worst 7e-9 of row max); pre-fix control FAIL (2.6e38). Ti/ni/up/ng still bitwise equal. Bitwise agreement with
  serial: Te box 1/30 — the residual M2 (finite-difference-noise level) is what keeps the epic's bitwise criterion
  open; that is the owner's decision 9.
- **02:40** Plan review for AIUE-56 reached round 3 without APPROVE (each round narrowed: 3M → 3M → 1M, all about the
  verification protocol; all three confirmed the code fix itself). Per the review loop: escalated to the owner;
  implementation proceeded under the open escalation (recorded in `docs/reviews/AIUE-56-plan-responses.md`).
- **03:00** Machine load average ~140 on 14 cores (7–9 agents + validation runs): everything is slow, timings inflated.

## Final state when the run stopped (~04:00, usage limit reached)

- **Root causes:** C1 (copy order in `OMPJacBuilder`) is fixed on `bugfix/v9-AIUE-56-omp-jacobian-fix` (`4fae2f9`,
  validation `ba12d94`). Defaults are bitwise unchanged (AIUE-53 serial check: AGREE on 42/42 cases in both builds).
  The C1 gate PASSes in every post-fix run, and the pre-fix controls FAIL. **C2/M2** (FMA rounding history, ≤ 7e-9 ×
  row max) is the only residual. Removing it (`-ffp-contract=off`) changes serial results at round-off level, so it is
  **the owner's decision 9** (options in the AIUE-55 RCA; AIUE-61 is blocked on it).
- **Approved:** AI layer, AIUE-46, AIUE-49.
- **Fixed, in or awaiting round 2:** AIUE-47 (r2 running), AIUE-50 (fixes `86ec027`, no r2 yet), AIUE-52 (rebased onto
  the core, r2 fixes `8d4c2c9`, no r3 yet), AIUE-53 (r2 running).
- **Open reviews:** AIUE-54 r1 REVISE (6 major: CSV numbers, the RHS-arm runs that iterated, §6.3 row by row, Linux,
  timings, records not committed), not yet addressed. AIUE-55 r1 review running.
- **Still running when stopped:** the AIUE-57 CI-job subagent. AIUE-57 must be rebased onto AIUE-52 `8d4c2c9`.
- **Escalated to the owner:** the AIUE-56 plan (round cap reached; the code is confirmed correct), decision 9, Linux
  validation (no Docker daemon), and the AIUE-56 implementation review (not yet run).
- **Not done:** restacking every branch onto merged parents, Jira updates for AIUE-47/50/52/53/54/55/56, PRs, push.

## Resumed 04:50 (usage limit reset)

- AIUE-47 **APPROVED** r2 (minors fixed `63370bd`, refs `e71fafc`) → Jira In Review.
- AIUE-53 r2 REVISE (1 major: unknown or off-v9-develop build source must be INCOMPLETE) → implementer fixing and
  rebasing onto the final core.
- AIUE-57 delivered (`47ddc26`, `a3535a3`, `6dfcdeb`): workflow + `ci/run_omp_ci.sh`, PR set ~17 min est., nightly
  `--all`. Pre-fix and seeded-race (`resee` un-threadprivate) both red locally. Under a bitwise gate the job stays red
  after C1 because of M2 → depends on decision 9 / AIUE-61. Being rebased onto AIUE-52 `8d4c2c9`.
- **AIUE-55 r1 REVISE with a BLOCKER that changes the conclusion:** the reviewer's emulation reaches bitwise equality
  with serial using an **OpenMP-only** remedy: each chunk replays the restoring local `pandf` calls of the preceding
  columns (full problem: 0 mismatches with ml+mu = 7840 replayed columns per chunk; Te box: 1 is enough). So bitwise
  may be reachable **without changing serial**; the §9(a) escalation was premature. The M2 agent is prototyping the
  replay in the real threaded code (minimal depth, cost, chunking). The RCA will be revised from that result.
- Reviews launched: AIUE-50 r2, AIUE-52 r3, AIUE-56 implementation r1. AIUE-54 revision delegated.
