# AIUE-8 — unattended run progress log

Run started 2026-10-15 ~00:05 PDT, while the owner is away (6–7 h). Nothing is pushed, no PRs are opened, nothing is
merged into `v9-develop`: every ticket lives on a local branch and worktree under `../uedge-wt/`, stacked where it
depends on an unmerged ticket. Each ticket gets a fresh `uedge-reviewer` adversarial review before it counts as done
(reports in that ticket's `docs/reviews/`). Jira: In Progress while worked on, **In Review** once the adversarial
review approves (awaiting the owner's review / PR). Owner decisions are prepared, never taken.

## Status board (final, 06:05)

**Bottom line.** Root cause C1 is found and fixed (AIUE-56): defaults bitwise unchanged, no slowdown, the C1 gate
passes everywhere, and the RHS arm is fixed too. The remaining residual C2 (≈1–2 ulp(yldot)/dyl, Te rows, mostly
divertor legs) is explained: history inside the serial Jacobian loop. A threaded prototype of an **OpenMP-only replay**
makes the OpenMP Jacobian bitwise equal to serial and deterministic, with serial unchanged (estimated ≈ 4.4 % × T
Jacobian cost, not measured). **Decision 9 is yours** (AIUE-55 §Exit decision): E replay, F static partition +
tolerance, A `-ffp-contract=off` (changes serial), B tolerance gate (interim CI only), D Linux without FMA.

| Ticket | Branch (local, not pushed) | Tip | Review | Jira |
|---|---|---|---|---|
| AI layer | `feature/v9-ai-adversarial-ticket-review` | 7303742 | **APPROVED** r2 | — |
| AIUE-46 case | `feature/v9-AIUE-46-omp-reproducer-case` | f5fee63 | **APPROVED** r1 | In Review |
| AIUE-47 capture hook | `feature/v9-AIUE-47-raw-jacobian-capture` | e71fafc | **APPROVED** r2 | In Review |
| AIUE-49 harness core | `feature/v9-AIUE-49-omp-harness-core` | c02dd42 | **APPROVED** r3 | In Review |
| AIUE-50 shared-state scan | `feature/v9-AIUE-50-shared-state-scan` | 32ac1af | **APPROVED** r2 (found C1) | In Review |
| AIUE-52 test flow | `feature/v9-AIUE-52-omp-test-flow` | 3c03d1c | **APPROVED** r3 | In Review |
| AIUE-53 serial check | `feature/v9-AIUE-53-serial-bitwise-check` | 15ae327 | **APPROVED** r3 | In Review |
| AIUE-54 characterisation | `feature/v9-AIUE-54-omp-characterisation` | c4cc9ff | I1-M4 resolved by AIUE-62 (owner, 13:42) | In Review |
| AIUE-55 RCA + decision 9 | `feature/v9-AIUE-55-omp-jacobian-rca` | 01e2d8e | **APPROVED** r4 (owner-authorised); addendum: Newton steps, phi | In Review |
| AIUE-56 C1 fix | `bugfix/v9-AIUE-56-omp-jacobian-fix` | 1553e75 | implementation **APPROVED** r3; plan **APPROVED** r4 (owner-authorised) | In Review |
| AIUE-57 CI job | `feature/v9-AIUE-57-omp-ci-job` | 8ee189d | **APPROVED** r2. **Don't merge** before AIUE-56 and a gate that can be green | In Review |
| AIUE-60 races | — | — | filed, not started | To Do |
| AIUE-61 C2 replay + stack crash | scratch `uedge-wt/AIUE-61-replay` | — | prototype; production awaits decision 9 | To Do |
| AIUE-62 Linux | `feature/v9-AIUE-62-linux-characterisation` (on AIUE-55) | 8277210 | **APPROVED** r2 | In Review |
| AIUE-51 / 58 / 59 / 48 | — | — | not started (optional / bonus / owner task) | To Do |

Stack, restacked after the review fixes (each child contains its parent's tip): v9-develop ← 46 ← {49 ← {52 ← 57,
53}, 50 ← 54 ← 55}; 47 and 56 on v9-develop. Merge order: 46 → 47 → 49 → 52, 53 → 50 → 54 → 55 → 56 → 57.
Harness unit tests after restacking: AIUE-57 tree 117 passed, AIUE-53 tree 57 passed.

**Your decisions:** (1) decision 9 (path for C2); (2) accept the escalated AIUE-56 plan and AIUE-55 RCA; (3) AIUE-54's
Linux criterion → AIUE-62 or not; (4) phi has no verdict of its own (`te_phi` only; phi can't be isolated without Te);
(5) deferred minors: AIUE-52/53 I3-m1 tests, AIUE-56 I1-m2 bounds-checked run.

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
- **05:00–05:45** Reviews converged: AIUE-47, 50, 52, 53, 57 approved (minors fixed or deferred with responses).
  AIUE-56: interleaved timing ratio 0.995 (no slowdown); D_only pytests identical in both OpenMP builds; residual is
  ≈1 ulp(yldot)/dyl, Te rows, not plate-concentrated. **Replay prototype**: R = `ubw` (3920) replayed columns per chunk
  → bitwise + deterministic (Te box 3/3, full 3/3 with 16 chunks), serial unchanged; cost ≈ +18 % (one chunk per
  thread, estimate) to +70 % (16 chunks, measured); also found a pre-existing crash for any `OMPJacNchunks≠0`
  (firstprivate arrays on the 8 MB main stack) → AIUE-61 scope. Filed AIUE-62 (Linux).
- **05:45–06:05** AIUE-56 implementation r3 APPROVE (wording minors fixed). AIUE-55 r2 REVISE (static partition
  is reproducible run to run → option F; cost labelled as estimate), r3 REVISE (F's reproducibility is empirical under
  dynamic scheduling; wording) → applied, escalated at the round cap. Restacked 49/52/53/57 and 50/54/55 onto the
  reviewed parents (clean rebases). Jira: AIUE-55, AIUE-56 → In Review; AIUE-61 rewritten around the replay.
- **Owner follow-up (09:00–10:00)** Owner authorised round 4: AIUE-56 plan APPROVE, AIUE-55 APPROVE. Experiments: at
  dtreal=1e-9 over 5 steps serial and replay are bitwise identical; the C1-only OpenMP build converges in 3/5 runs
  (state within 1e-11 to 1e-8 relative), 2/5 fail the hard first step, like an -ffp-contract=off serial build. te_phi is
  bitwise equal without C2, so phi adds nothing. Docker Desktop started (linux/arm64 native, linux/amd64 emulated), so
  AIUE-62 can run locally. AIUE-54 set to In Progress in Jira (it showed To Do).
- **Owner follow-up 2** Owner approved AIUE-62 (Linux, local Docker) and asked for an F-vs-E cost study (scratch,
  subagent) and a close-epic skill (`feature/v9-ai-close-epic`). Post-fix RHS-arm probe: `te` no longer crashes and
  `full` no longer overflows (2 and 4 threads); `yldot` and the parallel RHS equal serial. Full/jacrhs also gave a
  bitwise Jacobian 3/3 on a heavily loaded machine, against the earlier residual: to re-check quietly (AIUE-58).
  Tips after restacking come from git; some Jira comments quote pre-restack tips (49, 54, 56).
- **Owner follow-up 3 (12:00–12:50)** AIUE-62 APPROVED r2: on emulated x86-64 (Debian gcc 12.2 K=20, Ubuntu 24.04
  gcc 13.3 K=5, libgomp, no FMA) the C1 fix alone is bitwise = serial and deterministic for the Te configurations;
  exceptions are M3 (`up` rows by the inner plate, Linux, >=4 threads, pre-existing) -> AIUE-65. The Linux OpenMP build
  doesn't import without `LDFLAGS=-fopenmp` -> AIUE-64 (blocks AIUE-57 CI). Cost study (scratch, unreviewed; AIUE-61
  comment): F with round-robin fixed chunks +4-6 % vs default, reproducible; F with one chunk per thread +70-108 %;
  E +27-154 % (+44 % at best), bitwise = serial; auto-balancing is inactive in the default by code. AI layer
  consolidated onto local v9-develop (4faed39, 7 commits, not pushed); AI branches and worktrees deleted.
- **Owner decision 9 (13:30):** option F, static partition of many fixed contiguous chunks dealt round-robin (~5 %),
  as the new default OpenMP Jacobian behaviour; the owner confirmed this as an exception to the no-default-change rule.
  Implementation: AIUE-61 (rewritten). Started AIUE-61, AIUE-64 (Linux link), AIUE-60 (races) to plan review, and
  AIUE-58 (RHS RCA) to completion.
- **13:45** Owner: AIUE-62 resolves AIUE-54's I1-M4 → AIUE-54 In Review. M3 split out of AIUE-8 into the new epic
  **AIUE-66** ("OpenMP Jacobian on Linux: plate-boundary momentum rows"), AIUE-65 moved under it with the arm64 Linux run
  added; AIUE-61 reports whether option F removes M3. After a Claude Code restart the AIUE-61/60/58 agents were wrongly
  assumed lost and relaunched; the originals had survived, so the duplicates were stopped after ~4 minutes (they had
  only read code). AIUE-64's plan landed (`75108da`); its plan review is running.
