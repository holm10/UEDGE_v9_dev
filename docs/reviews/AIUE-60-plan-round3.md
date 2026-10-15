# AIUE-60 plan review, round 3

Reviewed: `.claude/plans/AIUE-60-omp-races.md` and `docs/reviews/AIUE-60-clip-check.py` at `4872387` (branch
`bugfix/v9-AIUE-60-omp-races`; round 2 reviewed `203a5ff`). Also read: the round-2 report and response, the diff
`203a5ff..4872387`, the AIUE-56 validation record, the AIUE-54 RCA and its `k2_all` flow summary, the AIUE-58 RCA
(`3aa0357`), the reviewed harness core (AIUE-57 `8ee189d`: `compare.py`, `flow.py`, `worker.py`), the AIUE-56 C1-gate
script and the AIUE-61 plan (`e0769d3`).

Decisions in force, not re-opened: B1/B3 go to AIUE-69; `isimpon=5` relies on the `exmain` roadblock; AIUE-60 merges
first; `nfsp` in the RHS path goes to AIUE-58/59; the `jacrhs` gate is no-regression only.

## Verdict

**APPROVE**

## Summary

The revision resolves L2-M1. The flow gates are now per run and per section, and the classes are fixed in advance.
Each gate rests on a property that no recorded run of its kind has violated, on AIUE-56 or, where AIUE-56 has no
record, on the base build and the AIUE-58 probes. The equation-set blind spot is gone, because gate (d) is checked per
section on both arms. I re-ran the new G1 offline on Probe C. It reproduces the response's numbers, and the negative
control still bites: on `full` the old column rule leaves non-flips in all six equations, up to 0.999999 × row max.
Three minors remain, all optional:
- the K=5 re-run rule is statistically weak, and one sentence about it is false;
- G1's `τ_eff` is global, and G3 is not aligned with the C2 tolerance;
- the Class X evidence is cited inaccurately.

None of them can let a wrong implementation pass.

## Findings

### BLOCKER

None.

### MAJOR

None.

### MINOR

**L3-m1: The K=5 re-run rule confirms a "regression" on a one-run margin. The claim that "a single unlucky run can't
fail the ticket" is false.**
Location: plan Testing 3, "Re-run rule" and "Why false failures are unlikely".

The rule confirms a regression when AIUE-60 fails the property in more of its 5 re-runs than AIUE-56 does. A result
of 1 vs 0 therefore confirms. Suppose the property is intermittent at the same rate q on both builds. Then the
probability of a false confirmation, P(X₆₀ > X₅₆), is:

| q | P(X₆₀ > X₅₆) | With a margin of 2 or more |
|---|---|---|
| 0.02 | 0.087 | 0.003 |
| 0.05 | 0.18 | 0.018 |
| 0.1 | 0.27 | 0.05 |
| 0.5 | 0.38 | 0.17 |

The rule is reached only after an initial gate failure, and every gated property has no recorded failure. The overall
false-failure probability is therefore small, and the rule errs toward failing, which is the safe direction for a
race fix. So this is not a MAJOR. But the stated reason ("a single unlucky run can't fail the ticket") is wrong.

To resolve, either:
- correct the sentence; or
- pre-register a tie-break: on a margin of 1, re-run K=10 more on both builds and decide on the totals; or require a
  margin of at least 2.

Either is acceptable. Don't weaken the rule for a deterministic regression (5 vs 0 must still confirm).

**L3-m2: G1's `τ_eff` uses the run's global maximum `sfscal` change, and G3 doesn't use G1's C2 tolerance.**
Location: `AIUE-60-clip-check.py` `pattern_diff` (`sf_rel`, `tau_eff`) and `check` (G3).

- **One row widens every row's band.** `tau_eff = TAU + max_r |sf_omp(r)/sf_ser(r) − 1|` is applied to every row. A
  large `sfscal` change in one row would widen the band for all rows and make G1 nearly blind, and G2 is report-only.
  - Today this is guarded only indirectly. The flow's gate (d) requires `sfscal` to be bitwise in a related
    configuration: one evaluation, without the clip. The clip run's `sfscal` comes from the same `sfsetnk` path, and
    A5 can't change it, because `sfscal = 1` during `sfsetnk`.
  - Probe C had `sfscal` bitwise, so `τ_eff = τ` there.
  - A per-row `τ_eff` (τ + |sf_omp(r)/sf_ser(r) − 1|), or a G1 failure when `sfscal_max_rel_diff` exceeds the C2
    scale (for example 1e-7), would close this cheaply.
- **G3 is looser than G1.** G3 passes if `non_flips > 0`. On `full`, a base run whose only non-flips were C2-tolerated
  would pass G3 without showing that the case is sensitive.
  - In practice the base build gives 734 080 non-flips in all six equations, and the `rules_differ > 0`
    precondition stands. So the control is real.
  - Defining G3 as `g1_verdict(base run, strict) == "FAIL"` would make the negative control use the same rule as G1.
- **Observation (no change required).** Under the old column rule, 45 700 of the 94 248 Te-row non-flips on Probe C
  `full` lie within 1e-6 × row max. The C2-tolerance escape is about 100 × τ wide.
  - The negative control still bites only because the clip-index defect also hits the other equations.
  - That holds for this defect, which affects every row the same way. It wouldn't hold for a Te-row-only defect.

**L3-m3: The Class X evidence citation is inaccurate. (Implementation note on gate (c) included.)**
Location: plan Testing 3, "Classes".

- The plan says Class X "was bitwise in every recorded AIUE-56 run". It then cites the `base-omp` controls (3/3) and
  "AIUE-52 PASS at 2/4/8 threads". Neither comes from AIUE-56:
  - The 3/3 controls are base-build runs (`AIUE-56-validation.txt:25-28`).
  - The 2/4/8-thread, both-arm 2/2 PASSes are AIUE-54's `k2_all` flow on the base build
    (`AIUE-54/docs/rca/AIUE-8-data/records/k2_all/flow_summary.md`).
  - The AIUE-56 runs are `jac` at 4 threads only, 5/5 per preset (`:17-20`).
  - For AIUE-56 at 2 threads and on `jacrhs`, the support is the base-build data plus the AIUE-58 probes on AIUE-56
    (`ni`/`up`/`ng` equal in every step; `ti` equal at `yl0`).
- The classification is sound, and the mechanical fallback covers it if it is wrong. Fix the attribution
  ("AIUE-56 jac 4 threads 5/5; base build 3/3 and AIUE-54 `k2_all` 2/4/8 both arms").
- Implementation note, no finding: `AIUE-56-c1-gate.py` expects a directory that holds `serial/` and `run*/`
  together. The flow writes `<config>/serial` and `<config>/<arm>_t<n>/run<k>`. Gate (c) on flow output therefore
  needs a small adapter (symlinks or a staging directory). Without one, the script reports "cannot read" (exit 2),
  not a false pass.

## Status of previous findings

| Finding | Status | Evidence (checked here) |
|---|---|---|
| L2-M1 flow gates (a)/(d)/(e) can fail by chance; (e) blind to RHS-section regressions | **Resolved** | See below the table. |
| L2-m1 τ observed, not a bound; strict rule vs C2 | **Resolved** | See below the table. |
| L2-m2 numeric Probe S expectations | **Resolved** | See below the table. |
| L2-m3 AIUE-61 stale references | **Resolved (main session, AIUE-61 `e0769d3`)** | AIUE-61 `:29` gives the owner's order AIUE-56 → AIUE-60 → AIUE-61, and `:303` gives the final run on the combined tree. Its cites now say "`d2fac6e`, revised to `203a5ff`", one revision behind `4872387`. That is trivial. |

**L2-M1, resolved.**

- **Classes are fixed in advance.** I checked the Class X evidence: AIUE-56 `jac` 4 threads 5/5 for each of
  `ti`/`ni`/`up`/`ng` (`AIUE-56-validation.txt:17-20`), and on the base build 3/3 (`:25-28`) and `k2_all` 2/2 at
  2/4/8 threads on both arms. The citation is fixed in L3-m3.
- **Class Y.** Te box 1/5 and 1/30, full 2/5 and 0/30, `te`/`te_phi` 0/5 (`:9-16`), as the plan states.
- **Gate (d): no recorded counter-example in any run whose sections were recorded.**
  - On the AIUE-56 `jacrhs` K=5 runs (Te box and full, 4 threads), the failing set is `{'jacobian:post_exmain'}` only
    in all 10 runs (`:103-114`). So `yldot`, `yldot_probe`, `sfscal`, `suscal` and `fnrm_*` were bitwise.
  - On `jac`, the Te box and full K=30 runs report "other differing sections: none" (`:118-121`).
  - The `--itermx 3` runs show "sfscal mism 0".
  - AIUE-58 adds `jacrhs` one-evaluation runs: `te` 3/3, full 3/3 at 2 and 4 threads, and Te box `yldot`/probe 10/10.
    Its probes on AIUE-56 at `yl0` are equal for every preset, `te_phi` included.
- **Why gate (d) holds.**
  - In `worker.py:216-225`, `yldot_probe` is `bbb.ffun` (`OMPPandf1Rhs`) at the Jacobian's `yl`.
  - AIUE-58 §"Why the earlier RHS checks were green" explains why that state is the one where stale worker state
    can't show.
  - `sfscal` is the max-norm (`normtype=0`, `bbb.v:3293`; `sfsetnk`, `oderhs.m:2292-2350`). It changes only if a C2
    entry is the row maximum, which no recorded post-fix run shows.
- **The blind spot is closed.** (d) is checked per section, so a new Te-row `yldot`/`yldot_probe` mismatch fails even
  where the Jacobian carries C2. `compare_records` produces exactly the section names the plan lists
  (`compare.py:258-288`).
- **Gaps in the AIUE-56 record.** It has no `jacrhs` run at 2 threads for the Te box, and no flow-style `te_phi`
  `jacrhs` run. The mechanical fallback covers these: if AIUE-56 itself violates (a)/(d) in this flow, that group and
  section go to the re-run rule. The fallback is pre-registered and mechanical.
- **Gates (b)/(c)** rest on 110 C1-gated one-evaluation runs, all PASS (`:9-20`).
- **Gate (f).** AIUE-58 records that `te`/`te_phi` `jacrhs` complete post-fix.
- **Re-run rule.** Sound in the safe direction. Its stated rationale is corrected in L3-m1.

**L2-m1, resolved.**

- τ is labelled an observed value.
- `τ_eff = τ + sfscal_max_rel_diff` covers the case of about 1.4e-8; see L3-m2 for its global form.
- `--strict` applies only to `ni`.
- For `full`, "PASS (C2 tolerance)" needs every non-flip in a Te row within 1e-6 × row max.
- I re-ran the committed functions offline on Probe C:

  | Preset | Mode | G1 | Non-flips | Te-row non-flips within 1e-6 |
  |---|---|---|---|---|
  | `ni` | strict | FAIL | 62 006 | n/a |
  | `full` | non-strict | FAIL | 734 080 | 45 700 |

  - `full` has non-flips in the ni, up, te, ti, ng and phi rows.
  - Serial against itself is PASS for both.
  - All other numbers match round 2.
- If `is_te` were missing, every non-flip would fail, which is the safe direction.

**L2-m2, resolved.**

- I re-ran both scripts on the tree: "145 reachable units; 161 variables", and 137 passed-args entries.
- The 14 named removals are all present today: `areapl`, `sputflxllim`, `sputflxrlim`, `timingpandfon`, 8
  `com.Timing` entries and 2 `com.Timespl` entries. So are `workh` and `iflag_aph`.
- Tasks 1–3 are line-neutral, as the plan states (attributes on existing `.v` lines; `pandf.m:48-51` 4 → 4 lines;
  `parallel.F90:288,292` in place). The pre/post line diff therefore can't false-fail on shifted locations.

## Not independently verified (environment)

Nothing was built or run in UEDGE, per the budget. Not checked:
- the AIUE-60 flow and clip outcomes;
- AIUE-56 `jacrhs` behaviour at 2 threads and for `te_phi`, `ti`, `ni`, `up` and `ng` in a flow run (the record has
  only probe and base-build data there);
- the TSan feasibility;
- whether Forthon accepts `+threadprivate` on the `aph` dynamic array (round 1 checked the `api` precedent).

The `is_te` map for the offline `full` re-check came from the harness record
`AIUE-58-scratch/hcyn_full_serial/record.npz`, the same `full` preset with neq 44 352. Probe C's own files predate the
`is_te` field.

## What was checked and how

- **Diff and response.** `git diff 203a5ff..4872387` (4 files; plan, clip script, round-2 report and response). There
  are no product or AI-layer files on the branch since `1553e75` (`git diff --stat 1553e75..4872387 -- . ':!docs'
  ':!.claude/plans'` is empty).
- **Evidence for the classes and gate (d).**
  - `AIUE-56-validation.txt` (C1-gate block, raw exit codes, `jacrhs` K=5 block, residual-location block, epic table).
  - `AIUE-54/docs/rca/AIUE-8-omp-jacobian-nondeterminism.md` §Matrix and §6.3, and
    `records/k2_all/flow_summary.md`.
  - `AIUE-58/docs/rca/...` §"Why the earlier RHS checks were green", the R1–R4 table, and the pre/post table.
- **Harness.** `compare.py:204-288` (section names, ±0 rule), `flow.py` (layout, `group_verdict`, the `CONFIGS` `phi`
  → `te_phi` mapping) and `worker.py:160-230` (`ftol=1e20`, the probe is `ffun` after `exmain`).
- **`sfscal` mechanism.** `bbb/oderhs.m:2292-2350` (`sfsetnk`); `bbb/bbb.v:3293` (`normtype` /0/).
- **Clip check.** Loaded the committed script through `importlib` with `venvs/AIUE-56-omp/bin/python -I`. Ran
  `pattern_diff` and `g1_verdict` (strict and non-strict) on `logs/AIUE-60/probeB_{ni,full}`, serial against itself,
  and a per-equation breakdown of the non-flips (scratch `/tmp/aiue60r3/recheck.py`).
- **Re-run rule statistics.** Computed P(X₆₀ > X₅₆) and P(X₆₀ ≥ X₅₆ + 2) for Binomial(5, q).
- **Probe S.** `python3 -I` on `AIUE-60-shared-writes.py` and `AIUE-60-passed-args.py` (tree read-only, output in
  `/tmp/aiue60r3/`).
- **AI layer.** `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` gives OK. The worktree was
  left clean apart from this report.
- **AIUE-61 plan.** `e0769d3`, lines 27-33, 135, 173 and 303.
