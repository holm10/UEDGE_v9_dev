# Feature: AIUE-56 — Fix the OpenMP Jacobian root cause C1 (OmpCopy order)

Validate the patterns and file references below before implementing.

## Summary
**Type**: Bug fix (numerics/parallel; OpenMP-only code path)
**Complexity**: Low (code), Medium (validation)
**Default results**: Unchanged. The changed routine runs only with `ppp.OMPParallelJac=1` in the OpenMP build; the
`--serial` build doesn't contain the call, and the OpenMP build with both switches 0 never reaches it.
OpenMP Jacobian results change, towards serial (PRD §9).
**Packages / files**: `ppp/omp_parallel.F90` (`OMPJacBuilder`), `.claude/context/openmp-jacobian.md` (code facts)
**Branch / worktree**: `bugfix/v9-AIUE-56-omp-jacobian-fix` @ `../uedge-wt/AIUE-56` (base: `origin/v9-develop`)

## Dependencies and merge order (round-1 L1-M1)

Unattended run; nothing is merged. This ticket is ordered by the Jira dependencies but runs before its predecessors
land, so it depends on **unmerged, pinned** branches (deviation from "base `v9-develop` after AIUE-55", recorded for
the owner; the owner decides the merge order):

- Diagnosis: candidate root cause C1, `docs/rca/AIUE-8-omp-jacobian-nondeterminism.md` on
  `feature/v9-AIUE-50-shared-state-scan` (in adversarial review) and the RCA ticket AIUE-55 (being written in
  parallel; its branch will be `feature/v9-AIUE-55-omp-jacobian-rca`, not created yet). If either review refutes C1,
  this plan is void.
- Tools (not on this branch, used read-only from their worktrees, commits recorded in the validation file):
  **every gating comparison uses the reviewed harness core** (`feature/v9-AIUE-49-omp-harness-core` at `71b0e3b` or
  later, APPROVE in its round 2: `check_arm`, strict comparator, ±0 rule, permuted-Jacobian labelling), via
  `cli.py check`, and each run's `check_arm` result (empty = arm took effect) is recorded. The AIUE-52 flow (still on
  the pre-review core until it is restacked) is used only for the report-only summary table. Serial check
  (`feature/v9-AIUE-53-serial-bitwise-check`), OmpCopy scan (`tests/deterministic_omp/tools/scan_ompcopy.py` on
  AIUE-50). Pre-fix baselines: AIUE-54 (K=20 at 4 threads on `base-omp`, `docs/rca/AIUE-8-data/` on
  `feature/v9-AIUE-54-omp-characterisation`), for comparison only; the negative controls are the fresh `base-omp` runs named in Testing (they go through the same gate script).
- Intended merge order: AIUE-46 → 47 → 49 → 52, 53 → 50 → 54 → 55 → **56** → 57.

## Problem and solution
Root cause C1 (AIUE-50, `docs/rca/AIUE-8-omp-jacobian-nondeterminism.md` on `feature/v9-AIUE-50-shared-state-scan`):

- `OMPJacBuilder` copies the master's `+threadprivate` state to the workers before the column loop:
  arrays first (`OmpCopyPointer{bbb,com,api}`, `ppp/omp_parallel.F90:681-686`), then scalars
  (`OmpCopyScalar{bbb,com,api}`, `ppp/omp_parallel.F90:688-693`).
- The Forthon-generated `OmpCopyPointer<var>` copies the section `(1:n)` **inside** the parallel region, where `n` is
  the worker's own copy of the threadprivate bound scalar (e.g. `build/temp.*/api_p.F90`, `OmpCopyPointerxdata_api`:
  `xdata_api(1:nxdata_api)=xdata_apicopy(1:nxdata_api)` with `nxdata_api` threadprivate).
- For the 12 `api` `Imslwrk` spline arrays (`api/api.v:145-172`) the bounds are threadprivate scalars (DATA `/1/`
  for most; `ldf_api`, `mdf` have none) that `splinem` (`api/apip93.m:102-108`, called from `bbb/odesetup.m:1130,1150`) sets on the
  master only. Only these 12 arrays have threadprivate bounds (round-1 review: all `bbb` copy routines use shared
  `com` `Dim` bounds; `com` and the other packages have no threadprivate variables). On the first OpenMP Jacobian of a session the
  workers therefore copy element 1 and keep zeros elsewhere. `emissbs` (`api/apip93.m:189`) then evaluates the
  `isimpon=7` fixed-fraction impurity radiation (`bbb/pandf_plasma_energy.m:822`, Te residual only) on zero tables:
  wrong Te rows in worker-built columns, ~1e43 entries, a sparsity pattern that depends on the column-to-thread map.
- `emcoef` is `copyin`'d at the loop (`ppp/omp_parallel.F90:715`), so workers point at the master's `emcoef`; the
  zero tables were the data and knot arrays. Later `OmpCopyPointeremcoef` calls then have the workers write identical
  values into the master's buffer concurrently — a benign, pre-existing race the swap doesn't change; keep the
  `copyin` and note it.
- `OMPPandf1Rhs` (the RHS arm) never copies: its workers rely on whatever the last `OMPJacBuilder` copy left, so the
  same C1 state affects the RHS arm until the first copy with the right order.
- The worker arrays themselves are allocated at the master's size (`apisetarraypointer<var>` uses
  `copyin(pcopy__)` of a master-sized buffer), so the full section fits once the bounds are right.

**Fix:** copy the scalars before the arrays. Then every worker's bound scalars equal the master's when the array
sections are copied, for every package. Comment the ordering requirement at the call site.

## Context references — read before implementing
- `ppp/omp_parallel.F90:644-700` — `OMPJacBuilder`, the only call site of `OmpCopyPointer*`/`OmpCopyScalar*`
  (`grep -n OmpCopy ppp/*.F90`).
- `ppp/ppp.v:35,38` — `OMPCopyArray`, `OMPCopyScalar` debug switches (default 1); keep both switches working
  independently.
- `/Users/holma/Documents/uedge/src/uedge-wt/base-omp/build/temp.*/api_p.F90` — generated copy and allocation
  routines (read-only evidence; never edit generated files).
- `.claude/context/openmp-jacobian.md` — "OpenMP parallelism" section (add the ordering fact).

## Step-by-step tasks

### UPDATE `ppp/omp_parallel.F90` (`OMPJacBuilder`)
- **IMPLEMENT**: move the `if (OMPCopyScalar.gt.0) ... OmpCopyScalar{bbb,com,api}` block before the
  `if (OMPCopyArray.gt.0) ... OmpCopyPointer{bbb,com,api}` block. Add a comment: the generated `OmpCopyPointer<var>`
  copies `(1:n)` with the worker's own threadprivate bounds, so the scalars must be copied first (AIUE-8, C1).
- **GOTCHA**: `.F90` file, not MPPL — free form, `!` comments. No other change. With the debug switches
  `OMPCopyScalar=0, OMPCopyArray=1` the hazard comes back (the bounds are never copied): say so in the comment.
- **VALIDATE**: OpenMP build (`build_uedge.sh <tree> venvs/AIUE-56-omp omp`) and serial build from a second tree at
  the same commit (`venvs/AIUE-56-serial`); both import.

### UPDATE `.claude/context/openmp-jacobian.md` (code facts, own commit, `AI-layer: code-facts`)
- **IMPLEMENT**: state that `OMPJacBuilder` copies threadprivate scalars before arrays and why; `check_context_refs.py
  --changed origin/v9-develop` clean (`--fix` for the moved lines `ppp/omp_parallel.F90` cited there).

## Testing strategy (round-1 L1-M2, L1-M3, m2, m5)

Tool commits are pinned in `docs/reviews/AIUE-56-validation.txt`. Fresh `python -I` process per run, empty HOME,
`OMP_STACKSIZE=512M`. Builds: `venvs/AIUE-56-omp` (this branch) and `venvs/AIUE-56-serial` (second tree, same commit);
references `venvs/base-omp`, `venvs/base-serial`.

1. **C1 removed, statically:** `scan_ompcopy.py` on the AIUE-56 OpenMP build tree reports 0 copy-order hazards; on
   `base-omp` it reports the 12 (negative control).
2. **Defaults unchanged (hard rule):** AIUE-53 serial check, both pairs (`base-serial` vs `AIUE-56-serial`,
   `base-omp` vs `AIUE-56-omp` with both switches 0), its full case set including the Newton-iteration cases it is
   adding; plus `capture_check.py` AC1-style `--newton 3` on the reproducer if those cases aren't in yet. Expected:
   AGREE / exit 0. Also the upstream `pytests` D_only suite with the OpenMP build (both switches 0).
3. **Acceptance protocol, jac arm, `AIUE-56-omp`** (all with the reviewed core's `cli.py check`):
   - Te box and full problem at 4 threads: K=30, one evaluation, and K=5 with `--itermx 3`;
   - Te box and full problem at 2 and 8 threads: K=5;
   - `te`, `ti`, `ni`, `up`, `ng`, `te_phi` at 4 threads: K=5.
   Negative controls: the fresh `base-omp` runs named below (one evaluation, 4 threads, K=3), not the AIUE-54 data.
4. **Residual, reported neutrally:** for every mismatch left after the fix: which equation rows/columns, which cells
   (plate-adjacent or not; `areapl` F16 is written in plate BCs), magnitude vs ulp(yldot)/dyl, whether it varies
   between OpenMP runs, and whether a serial run with different history reproduces it. No attribution (M2, F16, …)
   without that evidence; attribution belongs to AIUE-55.
5. **jacrhs arm:** run the same 4-thread K=5 set, report only (not gated, bonus track).
6. **Timing:** median wall time of the full-problem OpenMP run (`elapsed_s` in the harness record; the Jacobian time
   proper is `com.ttotjf`, `com/com.v:507`, not recorded by the harness) at 4 threads, from **interleaved** runs of
   `base-omp` and `AIUE-56-omp` (K=10 each, alternating, one at a time) so both see the same machine load; report the
   ratio, and flag > 10 % slower.

## Acceptance (round-2 L2-M2, L2-M3: gates only C1 decides; the epic's criterion separately)

**This ticket's gate (C1 removed), pre-registered:**

1. `scan_ompcopy.py` reports 0 copy-order hazards on the AIUE-56 OpenMP build tree (12 on `base-omp`).
2. Defaults unchanged: the serial check AGREEs in both builds (testing step 2).
Gates 3 and 4 apply to the **one-evaluation runs** only (`ftol=1e20`: the compared Jacobian is the first, `sfsetnk`
one — unpermuted, not row-normalised, and the one C1 corrupts). The `--itermx 3` runs compare the last `psetnk`
Jacobian (row-normalised, RCM-permuted, and not the first of the process), so they are **report-only** (round-3
L3-M1); their `sfscal`/final-`fnrm` agreement is reported too.

3. **Magnitude bound** in every one-evaluation OpenMP run of step 3: max |J| over the Te rows ≤ 10 × the serial reference's
   (pre-fix: ~1e43 vs ~5.6e5 on the Te box, ~6e43 on the full problem).
4. **Deviation bound** in every one-evaluation OpenMP run of step 3: every mismatching entry — value mismatch or entry present on
   one side only (absent = 0) — has |a − b| ≤ 1e-6 × the largest |J| of the serial row. Pre-fix runs violate this by
   >30 orders of magnitude; finite-difference noise (`del=1e-8`) sits well inside it.
5. `check_arm` empty for every run (the OpenMP path really ran with the requested threads).

Gates 3–5 are computed by `docs/reviews/AIUE-56-c1-gate.py` (committed with the validation record) from the
`cli.py check` run directories: it loads each run's and the serial reference's `record.npz` (`jac_post`, `jacj_post`,
`jaci_post`, `eq`), evaluates the two bounds on the Te rows (and on all rows), and prints PASS/FAIL per run with the
worst ratio. **Controls (round-3 L3-m1), fresh `base-omp` runs with the reviewed core, one evaluation, 4 threads, K=3:**
`tebox`, `full`, `te`, `te_phi` must FAIL both bounds (negative controls); `ti`, `ni`, `up`, `ng` have no Te rows and
must PASS (positive controls, C1 doesn't reach them).

**Reported, not gated here:** bitwise agreement counts, pattern differences (entries only in a/b), the residual
characterisation of step 4, the jacrhs arm, timing.

**The epic's Jacobian-track criterion** (0 mismatches in 30/30 and 5/5 at 2/4/8 threads, ≥ 3 Newton iterations with
every Jacobian compared, Linux and macOS) is carried by the last fix ticket to merge and is **not** decided here. The
PR lists every line of it as met / not met / not run. Known gaps of this ticket's runs: `--itermx 3` only for the Te
box and the full problem at 4 threads; the AIUE-56 build has no AIUE-47 capture hook (it is based on `v9-develop`), so
only the post-`exmain` Jacobian is compared; Linux not run (no Docker daemon locally → CI, owner). If a residual
remains, whether bitwise equality with serial is reachable is the owner's Phase 2 exit decision (decision 9, AIUE-55).

## AI-layer facts affected
`.claude/context/openmp-jacobian.md` (copy order; moved `ppp/omp_parallel.F90` line refs). Nothing else cites the
moved lines (check with `check_context_refs.py`).

## Notes
- Alternative fix (rejected): change Forthon's generator to use the master's bounds — out of this repo.
- Not in scope here (sibling tickets from AIUE-55): `areapl` race (`bbb/bbb.v:951`, written in plate BCs, not
  threadprivate); timer/flag races; M2.
