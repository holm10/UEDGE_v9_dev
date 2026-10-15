# Response to AIUE-56 plan round 1 (REVISE: 0 blocker, 3 major, 7 minor)

| Finding | Response |
|---|---|
| L1-M1 dependencies not stated | Fixed: new "Dependencies and merge order" section — the unmerged, pinned branches (diagnosis on AIUE-50 + AIUE-55 in parallel; tools on AIUE-52/53/50; baselines on AIUE-54), tool commits pinned in the validation file, pre-fix negative controls re-run on `base-omp` where a protocol differs, and the intended merge order. Recorded as a deviation for the owner. |
| L1-M2 protocol vs acceptance | Fixed: K=30 (4 threads) and K=5 `--itermx 3` for Te box and full; K=5 at 2 and 8 threads; K=5 for te/ti/ni/up/ng/te_phi; OpenMP-build pytests D_only; Linux marked "not independently verifiable" (no Docker daemon) → CI/owner. |
| L1-M3 residual pre-labelled; acceptance mixed | Fixed: residual reported neutrally (rows/cols, cells, plate-adjacent, size vs ulp, run-to-run, serial history test), attribution left to AIUE-55; this ticket's own acceptance separated from the epic criterion carried by the last fix ticket. |
| m1 `copyin(emcoef)` | Documented in Problem and solution (benign pre-existing race; keep `copyin`). |
| m2 static proof | Added: `scan_ompcopy.py` 0 hazards after, 12 on `base-omp`. |
| m3 `splinem`, no DATA for ldf_api/mdf | Corrected. |
| m4 `OMPCopyScalar=0` | Noted in the task's GOTCHA and the code comment. |
| m5 timing metric | Median full-problem OpenMP Jacobian time over K=30 at 4 threads, before vs after. |
| m6 RHS arm | Stated: `OMPPandf1Rhs` never copies and relies on the last `OMPJacBuilder` copy. |
| m7 line refs | `check_context_refs.py --fix` for `openmp-jacobian.md`; RCA/PRD references outside the checker are left (the RCA cites pre-fix lines on purpose). |

# Response to plan round 2 (REVISE: 0 blocker, 3 major, 1 minor)

| Finding | Response |
|---|---|
| L2-M1 pinned tools can false-AGREE | Fixed: every gating comparison uses the reviewed core (`feature/v9-AIUE-49-omp-harness-core` ≥ `71b0e3b`, APPROVE round 2) via `cli.py check`; each run's `check_arm` result is recorded; the AIUE-52 flow only for the report-only table. |
| L2-M2 gate includes a criterion the residual breaks | Fixed: the gate is now C1-specific and pre-registered: static scan 0 hazards; serial check AGREE; magnitude bound (Te-row max|J| ≤ 10× serial); deviation bound (every mismatching entry, incl. one-sided, |a−b| ≤ 1e-6 × serial row max); `check_arm` empty. Pattern/bitwise counts are reported, not gated. |
| L2-M3 overclaim | Fixed: sentence removed; the epic criterion is listed separately with the known gaps (itermx only for Te box/full at 4 threads, no capture hook in this build, no Linux); the PR lists every line as met / not met / not run. |
| L2-m1 AIUE-55 branch | Fixed: "will be ..., not created yet". |
| m3 splinem caller | Fixed: `bbb/odesetup.m:1130,1150`. |
| m5 timing | Fixed: `elapsed_s` from interleaved base/new runs (K=10 each, same load); `com.ttotjf` named correctly and noted as not recorded. |

# Response to plan round 3 (REVISE: 0 blocker, 1 major, 1 minor) — round cap reached, escalated

| Finding | Response |
|---|---|
| L3-M1 gates 3–4 invalid on `--itermx 3` runs | Applied: gates 3–4 restricted to the one-evaluation runs (first, `sfsetnk`, unpermuted Jacobian); `--itermx` runs report-only, with their sfscal/final-fnrm agreement reported. |
| L3-m1 negative control ill-defined | Applied: named controls on fresh `base-omp` runs with the reviewed core — tebox/full/te/te_phi must FAIL, ti/ni/up/ng must PASS. |

**Escalation.** Round 3 ended without APPROVE, so under the review loop (end-to-end-feature, step 6) the plan is
escalated to the owner. All three rounds confirmed the code change itself (copy scalars before arrays) is correct and
leaves defaults unchanged; the open points were verification details, now applied. Running unattended, the session
proceeded with implementation and validation under this open escalation (nothing merged or pushed); the owner decides
whether to accept the plan as revised.

# Response to plan round 4 (APPROVE, 0/0/0; round authorised by the owner beyond the cap)

The optional alignment is applied: plan lines 31 and 102 now point to the named `base-omp` negative controls instead of
the old "re-run where a protocol differs" / AIUE-54-data wording. The escalation is closed by this approval.
