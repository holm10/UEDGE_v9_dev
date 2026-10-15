# AIUE-56 plan review, round 3

Plan: `.claude/plans/AIUE-56-omp-jacobian-fix.md` (revised, untracked). Previous reports: `AIUE-56-plan-round1.md`
(REVISE 0/3/7) and `AIUE-56-plan-round2.md` (REVISE 0/3/1). Responses: `AIUE-56-plan-responses.md`.
Reviewer: uedge-reviewer (plan stage, finding prefix L). Read-only; no builds or runs.

## Verdict

**REVISE**: 0 BLOCKER, 1 MAJOR, 1 MINOR (both new). All three round-2 majors, the round-2 minor and the three
partially resolved round-1 minors (m2, m3, m5) are resolved. The remaining major is narrow and needs only a
scoping change to the gate.

## Summary

The code change (swap the `OmpCopyScalar*` and `OmpCopyPointer*` blocks) and the default-safety argument are
unchanged and still correct. Gating now runs on the reviewed AIUE-49 core with `check_arm`. The epic-criterion
overclaim is gone. The C1 gate is pre-registered with numbers.

For the **one-evaluation** runs, gates 3–5 pass all three tests in the brief. They are decided by C1. They fail on
the pre-fix build by about 37 orders of magnitude. They are tight enough to catch any O(1e-6)-relative error in an
entry that matters.

The gate is also applied to the `--itermx 3` runs. There it doesn't work. After `psetnk` the stored Jacobian is
row-normalised, RCM-permuted and is not the first Jacobian of the process, so:
- gate 3 can't fail;
- the `eq`-based Te-row selection is wrong;
- gate 4 can fail because M2 changes the sparsity pattern, which changes the permutation.

## Findings

### MAJOR

**L3-M1. Gates 3 and 4 are not valid on the `--itermx 3` runs.** In those runs they don't depend on C1, can't
fail pre-fix (gate 3), and can fail because of M2 (gate 4).
*Location:* Acceptance, gates 3–4 ("in every OpenMP run of step 3") together with Testing 3 ("K=5 with
`--itermx 3`"). The same holds for the gate script's description ("evaluates the two bounds on the Te rows").

- **What is wrong.** With `--itermx 3`, `jac_post` is the last `psetnk` Jacobian
  (`AIUE-49/tests/deterministic_omp/harness/worker.py:197-204`; `ijactot > 1`). That matrix has three properties
  that break the gate.
  1. **It is row-normalised.** `psetnk` calls `jac_norm_rows` (`bbb/oderhs.m:1963`). The defaults are
     `isrnorm=1` and `normtype=0`, i.e. the max norm (`bbb/bbb.v:3293,3296`). Every row's max |J| is therefore 1 in
     both the OpenMP run and the serial run. Gate 3 ("max |J| Te rows ≤ 10× serial") passes trivially, before and
     after the fix. So it can't fail on the pre-fix build.
  2. **It is permuted.** The deck sets `premeth="ilut"` (`case/input_mod4.py:38`), and `ireorder` defaults to 1
     (`bbb/bbb.v:2975`). `jac_lu_decomp` therefore calls `jac_reorder` (`bbb/oderhs.m:1308`), which applies a
     reverse Cuthill–McKee permutation in place (`:1402-1428`). The permutation is computed by `bfs` from each run's
     own sparsity pattern.
     - `eq` is in the original ordering (from `igyl`), so selecting "Te rows" by `eq` picks the wrong rows. The
       reviewed core itself marks this matrix as non-localisable (`compare.py:135-145,258`).
     - Post-fix, M2 removes or adds ulp-scale entries in Te rows (RCA E3, full problem run 2: 416 missing, 3 extra).
       That is enough to change the BFS order, and then the OpenMP and serial matrices are compared position by
       position under different permutations. Gate 4 would then fail massively for a reason that is not C1. That
       breaks requirement (a) and repeats the L2-M2 problem in a new form.
  3. **It is not the C1-affected Jacobian.** E2 shows that only the first Jacobian of a process is wrong. In an
     `--itermx` run that is the `sfsetnk` one. The build has no AIUE-47 capture hook, so that Jacobian is never
     compared in these runs. Pre-fix, C1 reaches the last `psetnk` Jacobian only indirectly, through the wrong
     `sfscal`. That changes the Newton trajectory, and the row normalisation cancels `sf` itself. Any gate-4 failure
     pre-fix would therefore come from a different state, not from the C1 tables.
- **Resolve by** applying gates 3–4 only to one-evaluation runs. There the compared Jacobian is the `sfsetnk` one:
  unpermuted, not row-normalised, and the first of the process. The `--itermx 3` runs then become report-only,
  for example `fnrm` sequence, `sfscal`, and bitwise or pattern counts. Alternatively, give the `--itermx 3` runs
  their own criterion that doesn't depend on the permutation, such as `sfscal` and the final `fnrm` within a stated
  tolerance of serial. That criterion must fail on `base-omp`, where `sfscal` comes from the 1e43 Jacobian. Either
  way, say explicitly which runs the gate is evaluated on.

### MINOR

**L3-m1. The negative control for the gate script is not well defined.**
*Location:* "Its own negative control: the same script on the pre-fix `base-omp` runs must FAIL both bounds";
Testing 3, last line.

- **Presets that C1 can't affect.** C1 acts only through `emissbs` in the Te residual (RCA E4). The `ti`, `ni`,
  `up` and `ng` presets have `isteon=0` (`AIUE-49/.../config.py:35-42`).
  - They have no Te rows, so gate 3 is undefined for them.
  - Pre-fix they should pass both bounds. "Must FAIL" is therefore false for these four presets, and for gate 3 on
    the `--itermx` runs (L3-M1).
- **No pre-fix records.** No `record.npz` from AIUE-54 survives: the data directory holds only a CSV and two
  summaries, and `find` finds no `record.npz` under the worktrees. The AIUE-54 data were also made with the
  pre-review core. The script can therefore only be checked against fresh `base-omp` runs made with the reviewed
  core.
- **Resolve by** naming the negative-control set: one-evaluation `tebox`, `full`, `te` and `te_phi` on `base-omp`
  with the reviewed core, at least at 4 threads, all expected to FAIL. Also state that `ti`, `ni`, `up` and `ng`
  are expected to pass pre-fix, which makes them positive controls of the script.

## Assessment of the C1 gate against the brief (one-evaluation runs)

- **(a) Decided by C1 alone.**
  - Gates 1, 2 and 5 are independent of M2.
  - Gate 4's tolerance is 1e-6 × the serial row max. FD noise relative to the row max is about
    eps/del = 2.2e-16/1e-8 ≈ 2e-8 times a cancellation factor of order one. That leaves a margin of about 50×.
  - The known post-fix residual is consistent with this. RCA E3 reports absolute differences of about
    4.5e-5 ≈ ulp(yldot)/dyl, and one-sided entries ≤ 7e-5. For the Te box, the serial max is 5.564e5. Those
    differences pass as long as the affected rows' max |J| is ≳ 70.
  - This is not demonstrated for the 7 full-problem rows. No records survive. It is a residual risk, not a defect:
    if gate 4 fails post-fix, the pre-registered result is FAIL and goes to the owner. I accept the rebuttal to
    L2-M2 on this basis.
- **(b) Can fail pre-fix.** Yes, for every C1-sensitive preset. The bad entries are about 2.6e43 and 6e43, against
  serial row maxima of about 5.6e5 and 1.7e14. Both bounds are violated by more than 29 orders of magnitude.
- **(c) Not too loose.**
  - Every entry with |a−b| > 1e-6 of its row's max fails, including one-sided entries. That covers a partial
    copy, a wrong table, a wrong column-to-thread result, or a dropped or extra significant entry, in any row
    (gate 4 is on all rows).
  - It doesn't catch errors in entries smaller than 1e-6 of the row max, or relative errors below 1e-6. Those are
    caught by the reported bitwise and pattern counts, not by the ticket gate. For a C1 ticket gate, with the epic
    criterion carried separately, I accept this.
  - Gate 3 is redundant with gate 4 (any 1e43 entry also fails gate 4), but harmless.

## Status of previous findings

| Finding | Status | Evidence |
|---|---|---|
| L2-M1 pinned tools can false-AGREE | **Resolved** | Dependencies: "every gating comparison uses the reviewed harness core (`feature/v9-AIUE-49-omp-harness-core` at `71b0e3b` or later …) via `cli.py check`, and each run's `check_arm` result … is recorded"; the AIUE-52 flow is used only for the report-only table. I verified that `71b0e3b` is the AIUE-49 HEAD and that `check_arm` exists (`compare.py:153-188`). It checks `ParallelJac`, `openmp_build`, `Nthreads` and `OMP_NUM_THREADS`, which closes I1-B1 for this ticket. |
| L2-M2 gate broken by the residual | **Resolved** for one-evaluation runs (see the assessment above); pattern and bitwise counts are now report-only. Not valid for `--itermx` runs (new L3-M1). |
| L2-M3 epic-criterion overclaim | **Resolved** | The sentence is removed. The epic criterion is stated as not decided here. The known gaps are listed: `--itermx` only for the Te box and the full problem at 4 threads, no capture hook, no Linux. The PR lists every line as met / not met / not run. |
| L2-m1 AIUE-55 branch | **Resolved** | "its branch will be `feature/v9-AIUE-55-omp-jacobian-rca`, not created yet". |
| L1-m2 indirect C1 criterion and missing threshold | **Resolved** | Numeric bounds are pre-registered: 10× and 1e-6 × the row max. The script has a negative control (see L3-m1 for its scope). |
| L1-m3 `splinem` caller | **Resolved** | The plan's Problem section now reads "called from `bbb/odesetup.m:1130,1150`". `grep -n "call splinem" bbb/odesetup.m` gives 1130 and 1150, and there is no `readpost` left in the plan. |
| L1-m5 timing | **Resolved** | Interleaved `base-omp`/`AIUE-56-omp` runs, K=10 each, under the same load. `com.ttotjf` (`com/com.v:507`) is named correctly and noted as not recorded. `elapsed_s` includes deck setup, which dilutes the ratio. That is acceptable for a flag, not a gate. |

## What was checked and how

- **Plan and responses.** Read the revised plan in full, the round-2 report, and the authors' responses to both
  rounds.
- **Harness (AIUE-49 at `71b0e3b`).**
  - `git log` of the branch.
  - `worker.py:120-256`: capture, `jac_post` source, and the psetnk/permuted labelling.
  - `cli.py:61-90` (`cmd_check`: a serial reference plus K OpenMP runs, `record.npz` per run directory).
  - `compare.py:135-145,153-188,258`: permuted matrices are non-localisable; `check_arm`.
  - `config.py:28-42`: the presets; `ti`, `ni`, `up` and `ng` have no Te equation.
  - `case/input_mod4.py:38,302-307`: `premeth="ilut"`, `isimpon=7`.
- **Solver path.**
  - `bbb/oderhs.m`: `psetnk` (`:1940-1975`: amudia, diamua, `jac_norm_rows`, `jac_lu_decomp`), the
    `jac_reorder` call (`:1308`), RCM (`:1402-1428`), `jac_norm_rows`/`roscal` (`:1438-1470`), and `jaccliplim`
    (`:1187`; default 0, `bbb/bbb.v:3308`).
  - `bbb/bbb.v:2975,3293,3296`: the defaults of `ireorder`, `normtype` and `isrnorm`.
- **RCA (AIUE-54).** `docs/rca/AIUE-8-omp-jacobian-nondeterminism.md` §C1 E2–E4 and §M2, for the
  first-Jacobian-only behaviour, the post-swap residual magnitudes and the maxima. `docs/rca/AIUE-8-data/` holds
  CSV and summaries only.
- **Retained records.** `find … -name record.npz` over the worktrees found none.
- **Not done.** No builds or runs, by design.
