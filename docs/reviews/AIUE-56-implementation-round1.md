# AIUE-56 implementation review, round 1

Ticket: AIUE-56 "Fix the OpenMP Jacobian root cause(s)" (epic AIUE-8). Branch `bugfix/v9-AIUE-56-omp-jacobian-fix`
(4fae2f9 fix, ba12d94 validation record), base `origin/v9-develop` (3865c79; product code identical to the `base-*`
trees at 0fac655, which differ only in docs). Reference: `.claude/plans/AIUE-56-omp-jacobian-fix.md` (pre-registered C1
gate) and the ticket acceptance criteria.

## Verdict

**REVISE**: 0 BLOCKER, 4 MAJOR, 4 MINOR.

The code change is correct, minimal and default-safe, and the plan's own C1 gate passes. I reproduced it. The REVISE
is about plan and ticket-acceptance deliverables that are missing. None of them needs the Fortran to change.

## Summary

The diff to product code is exactly the planned swap: `OmpCopyScalar{bbb,com,api}` now runs before
`OmpCopyPointer{bbb,com,api}` in `OMPJacBuilder`, with a correct explanatory comment. Nothing else in `.m/.v/.F90`,
the build files or `src/` changed. The installed `AIUE-56-omp` extensions are byte-identical to this tree's build
output. The disassembly confirms the new call order, and the generated `*_p.F90` files are identical to `base-omp`.
Every gate in the pre-registered C1 gate (static 12→0, defaults bitwise unchanged in both builds, magnitude and
deviation bounds, `check_arm`) holds on the recorded runs and on my own fresh runs. The negative and positive controls
behave as pre-registered.

What is missing is the rest of the plan and the ticket acceptance:
- the `.claude/context/openmp-jacobian.md` code-facts update (the context checker fails with 6 problems);
- the interleaved timing;
- the OpenMP-build pytests;
- the report-only material: the residual characterisation, the jacrhs and `--itermx 3` summaries, and a
  met / not met / not run table for the epic criterion.

The epic's bitwise criterion is **not met** (residual C2). Under the plan, that is not this ticket's gate; it is the
owner's decision 9.

## This ticket's gate vs the epic criterion

**Ticket gate (plan "Acceptance", pre-registered): PASS, independently reproduced.**

| Gate | Result | My check |
|---|---|---|
| 1. `scan_ompcopy.py` hazards 12 → 0 | PASS | Re-ran it on both build trees: `base-omp` lists 12 (`api.xdata_api` … `api.z2coef`), AIUE-56 lists 0 |
| 2. Defaults unchanged, serial check AGREE in both builds | PASS | `serial_check.json`: `agree: true`, `gate_complete: true`, 42 cases. The pairs are `base-serial`/`AIUE-56-serial` and `base-omp`/`AIUE-56-omp` (omp0); heads are 0fac655 and 4fae2f9, all clean |
| 3. Magnitude bound (one-evaluation runs) | PASS (ratio 1 everywhere) | Re-ran the gate on `new_full_t8_k5`, `new_te_phi_t4_k5`, the jacrhs dirs, and my own fresh runs |
| 4. Deviation bound ≤ 1e-6 × serial row max | PASS (worst 7.15e-9, te_phi) | As above. Worst values reproduce exactly |
| 5. `check_arm` empty | PASS | Gate re-run with an explicit `--harness …/AIUE-49/tests/deterministic_omp` |
| Controls on `base-omp` | tebox/full/te/te_phi FAIL (ratio ~4e37, deviation up to 6.9e38); ti/ni/up/ng PASS | Re-ran on `base_full_t4_k3` and `base_ti_t4_k3` |

**Epic Jacobian-track criterion (carried by the last fix ticket): NOT MET**. This is not this ticket's gate.

| Epic line | Status from the recorded runs |
|---|---|
| Te box, 4 threads, 30/30 with 0 mismatches | not met: 1/30 bitwise |
| Full problem, 4 threads, 30/30 | not met: 0/30 |
| 2 and 8 threads, 0/5 | not met: tebox t2 1/5, t8 0/5; full t2 2/5, t8 0/5 |
| Other configurations at 4 threads, 0/5 | te 0/5 and te_phi 0/5 not met; ti/ni/up/ng 5/5 met |
| ≥ 3 Newton iterations with every Jacobian compared | not run as specified: no capture hook in this build, only the last (permuted) Jacobian compared; the `--itermx 3` runs mismatch |
| Linux | not run. **Not independently verified (environment)** |
| Ti/ni/up/ng isolations bitwise equal to serial | met (5/5 each, AGREE exit 0) |

## Findings

### BLOCKER

None.

### MAJOR

**I1-M1. The `.claude/context/openmp-jacobian.md` code-facts update is missing, and the context checker fails.**
- *Location:* `.claude/context/openmp-jacobian.md` (unchanged on the branch) and `.claude/context/mppl-fortran.md:69`.
- *Problem:* The ticket acceptance requires "New +threadprivate/copy rules in `.claude/context/openmp-jacobian.md`
  (AI-layer: code-facts)". The plan has a dedicated task for it. The diff stat shows no `.claude/context/` change and no
  commit with the trailer.
- *Evidence:* `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` exits 1 with **6 problems**:
  - MOVED `openmp-jacobian.md:17` (902→908), `:21` (715→721) and `:32` (953→959, 955→961);
  - **STALE** `mppl-fortran.md:69 ppp/omp_parallel.F90:902-930`.
  The plan's claim "Nothing else cites the moved lines" is wrong: `mppl-fortran.md` cites them too. The CLAUDE.md hard
  rule requires the checker to be clean before a PR.
- *Acceptance condition:* add a separate commit with the `AI-layer: code-facts` trailer that:
  - states the copy-order rule: `OmpCopyScalar*` before `OmpCopyPointer*`, because the generated array copies size the
    section with the worker's own threadprivate bounds;
  - states that `OMPPandf1Rhs` does no copy of its own (see I1-m1);
  - fixes both files' line references.
  The checker must then be clean.

**I1-M2. The before/after Jacobian timing was not measured.**
- *Location:* plan "Testing strategy" step 6; ticket acceptance "Measure OpenMP Jacobian time before/after; report a
  slowdown > 10 %".
- *Problem:* There is no timing section in `AIUE-56-validation.txt` and no interleaved run in `v56/`.
- *Evidence:* For reference only, I took `elapsed_s` medians from the existing records: full problem 105.3 s on the
  new build (K=30) vs 101.8 s on base (K=3), +3.4 %; Te box 9.84 s vs 12.15 s. These come from three concurrent
  protocol lanes and unequal K, so they are **not** a valid measurement. A slowdown is plausible in principle: the fix
  copies the whole spline tables to every worker where it used to copy one element.
- *Acceptance condition:* the interleaved base/new full-problem runs at 4 threads (K=10 each, one at a time), as in
  the plan, with the median ratio recorded and flagged if > 10 %. Or the owner explicitly waives this in the PR.

**I1-M3. The OpenMP-build pytests suites were not run.**
- *Location:* plan "Testing strategy" step 2 ("Also the upstream `pytests` D_only suite with the OpenMP build");
  ticket acceptance "OpenMP-build pytests suites still pass".
- *Problem:* No pytest run is recorded. `defaults.sh` and the serial check run pytests-derived *cases* through the
  serial-check tool (1 or 5 Newton iterations, bitwise vs base). They do not run the suites against their reference
  solutions.
- *Evidence:* There is nothing in `v56/` or the validation record. I tried to run D_only myself with
  `venvs/AIUE-56-omp`, but `pytest-isolate` is not installed in that venv and the budget forbids reinstalling.
- *Mitigation and acceptance condition:* the 31 bitwise-AGREE omp0 pytests cases make a failure very unlikely, and the
  changed routine is not reached with default switches. Still, this is a listed acceptance item. Run at least
  `pytests/unittests/D_only` (preferably the suites the ticket names) with `--isolate` on the OpenMP build and record
  the pass counts verbatim. Or have the owner accept the serial-check equivalence argument explicitly in the PR.

**I1-M4. The report-only deliverables are missing from the validation record.**
- *Location:* `docs/reviews/AIUE-56-validation.txt`, compared with plan steps 4 and 5, the "Acceptance" paragraph
  (`--itermx 3`: "their `sfscal`/final-`fnrm` agreement is reported too") and "The PR lists every line of it as met /
  not met / not run".
- *Problem:* The record gives only the exit codes for the four `--itermx 3` and jacrhs runs. It is missing:
  - the residual characterisation (rows/columns, cells, plate adjacency, size vs ulp, run-to-run variation, the
    serial-history test);
  - the jacrhs summary;
  - the `--itermx 3` sfscal/fnrm agreement;
  - the epic met / not met / not run table.
- *Evidence:* the facts are in the run outputs but not in the record. Three of them matter for the owner's decision 9:
  - `new_full_t4_it3_k5.txt`: sfscal is equal, but `fnrm` at Newton iteration 1 varies run to run (1.8364, 1.8424,
    1.8464 against serial 1.8361). After 3 iterations, 43,562 `yldot` entries differ across all equations.
  - `new_tebox_t4_it3_k5.txt`: fnrm differs from iteration 1 onward, and one run is bitwise AGREE with serial.
  - jacrhs: `yldot`/`fnrm` are equal to serial in all runs, and the Jacobian residual is the same size as on the jac arm
    (I re-gated it: worst 4.59e-9). The RCA (`AIUE-8-omp-jacobian-nondeterminism.md:22`) says C1-RHS is "validated there
    (AIUE-56)", but the AIUE-56 record never states it.
- *Acceptance condition:* add these sections to the validation record. The two tables in this report can be reused.
  Report the residual neutrally, as the plan requires.

### MINOR

**I1-m1. With the RHS alone parallel, the workers still never get copies.** `OMPPandf1Rhs`
(`ppp/omp_parallel.F90:908-1002`) does not call any `OmpCopy*` routine. In particular `USE OmpCopybbb` is unused, and
`grep` finds no call there. With `OMPParallelPandf1=1, OMPParallelJac=0`, `OMPJacBuilder` never runs, so by
inspection the worker spline tables stay at element 1 and zeros: C1 for `isimpon=7`. I could not run this
configuration: the reviewed harness rejects `--ppp '{"OMPParallelJac":0}'`. This is pre-existing and outside "the
Jacobian-then-RHS sequence nksol uses", and the RCA routes remaining RHS issues to AIUE-58. *Acceptance:* name this
configuration in the context note (I1-M1) or the code comment, and confirm that AIUE-58 (or another ticket) owns it.

**I1-m2. No bounds-checked run.** The fix makes each worker write the full section `(1:n_master)` where it used to
write one element. I checked statically that this is safe: `apisetarraypointer<var>` allocates the master's `pcopy__`
with the master's bound and `copyin`s it, so the worker targets are master-sized. The `size()` guard in
`OmpCopyPointer<var>` is evaluated only on the master. A single `--checkbounds` (or `--debug`) OpenMP Te-box jac run
would make this empirical. This is not a plan item, so it is optional.

**I1-m3. The record does not match the run provenance.** The validation header pins harness `cf23ddf`. The records
show 15 of the 24 directories (all base controls, the jacrhs and `--itermx 3` runs, and some new runs, two of them
mixed) ran on `de57d59`, because the AIUE-49 branch moved during the protocol. `git diff cf23ddf de57d59` touches only
README, docs and `.claude/context`, so there is no effect on results. *Acceptance:* state both commits in the header.

**I1-m4. Gate-script robustness and where the artefacts live.**
- `AIUE-56-c1-gate.py` pairs matrices with `zip(...)`, which silently truncates if a run and its serial reference hold
  different numbers of captured Jacobians. This is harmless here (no capture hook), but it should be an error once
  AIUE-47 lands.
- The `.gate` outputs, `run_protocol.sh` and `defaults.sh` exist only in the session scratchpad. The committed record
  cannot be reproduced from the repository alone. Consider committing the two protocol scripts next to the gate script.

## What was checked and how

- **Diff.** I read `git diff origin/v9-develop...HEAD`: product code changes only in `ppp/omp_parallel.F90` (block swap
  plus comment), and the comment is accurate. No skills, agents or hooks changed. The plan is under `.claude/plans/`,
  which is an artifact path (`branching.md:13`).
- **Build identity.**
  - `cmp` shows all 11 installed `.so` in `venvs/AIUE-56-omp` byte-identical to `build/lib.*`.
  - `objdump -d -r omp_parallel.o` shows the call order: AIUE-56 is scalar bbb/com/api then pointer bbb/com/api;
    `base-omp` is the reverse.
  - Records give `source_head` 4fae2f9, not dirty. HEAD differs from 4fae2f9 only in the validation txt.
  - `api_p.F90`, `bbb_p.F90`, `com_p.F90` and `ppp_p.F90` are identical to `base-omp`.
  - The `AIUE-56-serial` tree is at 4fae2f9 and clean.
- **Fix mechanism.** Read the generated `OmpCopyPointerxdata_api`, `OmpCopyScalarapi` and `apisetarraypointerxdata_api`.
  Copying the scalars first sets the worker bounds to the master's before the section copy, and the worker arrays are
  master-sized. The final scalar state is unchanged from before. Only the api section lengths change.
- **Static gate.** Ran `AIUE-50/tests/deterministic_omp/tools/scan_ompcopy.py --src … --build …` on both trees: 0 vs 12.
- **Validation artefacts.** Read `protocol.log`, `gate_summary.txt`, every `.gate` (run counts match the directories),
  `check.json`, `serial_check.json` and the log. `cf23ddf` descends from `71b0e3b`.
- **Gate re-runs** (`venvs/AIUE-56-omp/bin/python -I AIUE-56-c1-gate.py --harness …`) on `new_full_t8_k5`,
  `new_te_phi_t4_k5`, `base_full_t4_k3`, `base_ti_t4_k3`, `new_full_rhs_t4_k5` and `new_tebox_rhs_t4_k5`. All match the
  record.
- **Fresh runs** with the reviewed core, under
  `/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev56/`:
  - `cli.py check --preset tebox --arm jac --threads 4 --repeats 3`: MISMATCH vs serial at 1–2 Te/Te entries, at
    `te(ix=4,iy=20)` with columns `(4,21)`/`(3,21)`. Gate PASS, worst 5.62e-10.
  - `--arm jacrhs`, same settings: `yldot` and `fnrm` equal to serial, 1 of 3 runs bitwise AGREE. Gate PASS.
  - An RHS-only probe was rejected by the harness, as noted in I1-m1.
- **Context checker.** `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` gives 6 problems,
  exit 1 (I1-M1).
- **Not run:**
  - pytests: `pytest-isolate` is missing in the venv and reinstalling was out of budget;
  - the timing protocol: about 20 full-problem runs, over budget;
  - a `--checkbounds` build: no reinstall allowed;
  - Linux: **not independently verified (environment)**.
