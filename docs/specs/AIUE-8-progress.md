# AIUE-8 — unattended run progress log

Run started 2026-10-15 ~00:05 PDT, while the owner is away (6–7 h). Nothing is pushed, no PRs are opened, nothing is
merged into `v9-develop`: every ticket lives on a local branch and worktree under `../uedge-wt/`, stacked where it
depends on an unmerged ticket. Each ticket gets a fresh `uedge-reviewer` adversarial review before it counts as done
(reports in that ticket's `docs/reviews/`). Jira: In Progress while worked on, **In Review** once the adversarial
review approves (awaiting the owner's review / PR). Owner decisions are prepared, never taken.

## Status board (updated 02:20)

| Ticket | Branch (local, not pushed) | State | Notes |
|---|---|---|---|
| AI layer | `feature/v9-ai-adversarial-ticket-review` | **APPROVED** (round 2), minors fixed `7303742` | Review gates in `end-to-end-feature`, `execute`, `plan-feature`, `implement-fix`; `plan` stage + run budget in `uedge-reviewer`. Reports on the planning branch |
| AIUE-46 case | `feature/v9-AIUE-46-omp-reproducer-case` | **APPROVED** r1; Jira In Review | Trim bitwise-proven; rate files already in repo |
| AIUE-47 capture hook | `feature/v9-AIUE-47-raw-jacobian-capture` | r1 REVISE (slots allocated up front) → implementer fixing | `bbb.jaccapture`, default-off bitwise-neutral |
| AIUE-49 harness core | `feature/v9-AIUE-49-omp-harness-core` (on 46) | r1 REVISE (1B/5M) → fixed → **r2 APPROVE**; r2 minors fixed `f46f7a4`; r3 delta review running | `check_arm`, strict comparator, provenance |
| AIUE-50 shared-state scan | `feature/v9-AIUE-50-shared-state-scan` (on 46) | r1 REVISE (1 major: C1 also breaks the RHS arm) → fixes queued; agent now hunting M2 | **Found root cause C1** |
| AIUE-52 test flow | `feature/v9-AIUE-52-omp-test-flow` (on 49 @fbe0adf) | r1 REVISE (1B) → fixed; r2 review running | full matrix data |
| AIUE-53 serial check | `feature/v9-AIUE-53-serial-bitwise-check` (on 49 @fbe0adf) | r1 REVISE (1B: no Newton iterations) → implementer fixing + rebasing | |
| AIUE-54 characterisation | `feature/v9-AIUE-54-omp-characterisation` (on 50) | written `e4f738c`; review pending | K=20 pre-fix rates |
| AIUE-55 RCA | — | data being collected (P3-m3, M2) | owner decision 9 prepared here |
| AIUE-56 fix (C1) | `bugfix/v9-AIUE-56-omp-jacobian-fix` | plan r1, r2 REVISE (verification protocol) → r3 (final) running; code not yet written | fix = copy scalars before arrays |
| AIUE-57 CI job | `feature/v9-AIUE-57-omp-ci-job` (on 52) | subagent implementing | can't run on GitHub without pushing |
| AIUE-51 diagnostics | — | not needed so far (optional) | |
| AIUE-58/59 RHS (bonus) | — | not started; C1 fix also fixes the Te-box RHS arm | |
| AIUE-48 coordination | — | owner task | |

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
