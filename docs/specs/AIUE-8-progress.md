# AIUE-8 — unattended run progress log

Run started 2026-10-15 ~00:05 PDT, while the owner is away (6–7 h). Nothing is pushed, no PRs are opened, nothing is
merged into `v9-develop`: every ticket lives on a local branch and worktree under `../uedge-wt/`, stacked where it
depends on an unmerged ticket. Each ticket gets a fresh `uedge-reviewer` adversarial review before it counts as done
(reports in that ticket's `docs/reviews/`). Jira: In Progress while worked on, **In Review** once the adversarial
review approves (awaiting the owner's review / PR). Owner decisions are prepared, never taken.

## Status board

| Ticket | Branch (local) | State | Notes |
|---|---|---|---|
| AI layer | `feature/v9-ai-adversarial-ticket-review` | round 1 REVISE (5 major) → fixed `4e191a7`; round 2 review running | Gates in `end-to-end-feature`, `execute`, `plan-feature`, `implement-fix`; `plan` stage + run budget in `uedge-reviewer` |
| AIUE-46 case | `feature/v9-AIUE-46-omp-reproducer-case` | **APPROVED** round 1 (8 minor, all fixed `f5fee63`); Jira In Review | Trim bitwise-proven; bug reproduced |
| AIUE-47 capture hook | `feature/v9-AIUE-47-raw-jacobian-capture` | implemented (subagent), 16/16 bitwise default-off; adversarial review running | `bbb.jaccapture` etc. |
| AIUE-50 shared-state scan | `feature/v9-AIUE-50-shared-state-scan` (on AIUE-46) | subagent implementing | |
| AIUE-49 harness core | `feature/v9-AIUE-49-omp-harness-core` (on AIUE-46) | implemented `e1f5808` (incl. capture); adversarial review running | critical path |
| AIUE-52 test flow | `feature/v9-AIUE-52-omp-test-flow` (on AIUE-49) | subagent implementing | |
| AIUE-53 serial check | `feature/v9-AIUE-53-serial-bitwise-check` (on AIUE-49) | subagent implementing | |
| AIUE-51 diagnostics | — | deferred (optional) | |
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
- **00:45** User asked about parallel delegation. Switched to the planned parallel waves: AIUE-47 and AIUE-50 to
  subagents (Wave 1/2), then AIUE-52 and AIUE-53 (Wave 3) once the harness core existed. The main session runs the
  adversarial reviews, the integration, and the critical path.
- **01:05** AIUE-49 harness core works: Te box check in 4.4 s (exit 1, all mismatches te/te); serial vs serial exit 0;
  full problem check ~70 s.
- **01:05** New data (full problem, 4 threads, 2 OMP runs): printed fnrm stable (1.535419111648367, as the PRD said),
  but the **Jacobian itself is not run-to-run stable**: 345k Te-row entries differ between the two OMP runs, and the
  OMP pattern has ~498k extra Te-row entries vs serial (3.69M vs 3.19M nonzeros). Only Te rows; all column equations.
- **01:15** **Lead for the RCA (L1 confirmed as dominant):** Te box with `bbb.afracs=0` (impurity radiation sink of
  `isimpon=7` zeroed): the 1e43 entries vanish and `get_fnrm()` is bitwise equal to serial in 3/3 OMP runs. Remaining
  differences are round-off level: serial has 5 entries of 4.547e-05 (≈ one ulp of yldot / dyl) where OMP has exact 0,
  3 entries differ in the 8th digit, and one tiny entry moves between OMP runs. So two mechanisms: **M1** gross, in the
  isimpon=7 radiation path on worker threads; **M2** history-dependent ulp noise in local pandf, present in serial too
  (bears on PRD P3-m3 and the owner's decision 9: whether bitwise equality with serial is reachable). Forwarded to the
  AIUE-50 agent.
- **01:15** Checked and ruled out as the cause here: the clip index difference (`sfscal(ii)` serial vs `sfscal(iv)`
  parallel) — `jaccliplim=0` so it has no effect on this case (still a latent bug for jaccliplim>0); `del` vs
  `delperturb` — both 1e-8.
- **01:25** AIUE-46 adversarial review: APPROVE, 0/0/8. Fixed all minors (relative rate path for deep checkouts,
  fingerprint hashes yldot before get_fnrm, README corrections, provenance hashes). Jira → In Review.
- **01:30** AI-layer review round 1: REVISE (5 major): "done" must be defined by APPROVE not by commit; fallback when an
  agent can't spawn a reviewer; run budget + "not independently verified" category; re-review after post-APPROVE
  edits; implement-fix/execute/plan-feature ungated. All fixed in `4e191a7`; round 2 running.
- **01:45** AIUE-47 done by subagent: capture hook (`bbb.jaccapture`, `jaccapv/j/i`, per-slot source/caller), default
  off bitwise-neutral on the reproducer + D_only/D+C/D_mols in both builds; captured×(1/suscal) == bbb.jac bit for bit.
- **01:55** AIUE-49 harness now compares the raw captured Jacobians. Te box, 3 Newton iterations: only 2 Jacobians
  (sfsetnk + one psetnk); the OMP psetnk Jacobian differs from serial in 1 entry, the sfsetnk one in ~40.
- Note: machine load average ~75 on 14 cores while 6–7 agents run; timings measured now are inflated.
