# AIUE-54 implementation review, round 2: "Characterise both arms and record pre-fix rates"

Reviewed: `feature/v9-AIUE-54-omp-characterisation` at `c235271`, rebased onto the reviewed AIUE-50 tip `f516b40`.
New commits: `03c3995` (the rebased original), `87e92fb` (the round-1 report), `c235271` (the revision). Inputs: the
round-1 report, `docs/reviews/AIUE-54-implementation-round1-response.md`, `docs/rca/AIUE-8-data/` and the section
§"Characterisation before any fix (AIUE-54)" of `docs/rca/AIUE-8-omp-jacobian-nondeterminism.md`.

## Verdict

**REVISE**

The verdict rests on one finding: I1-M4 (Linux). The author can't close it, because the document correctly records
the owner's decision as **still open**. Once the owner writes the decision into the section, and if no other changes
are made, I expect to approve. The minors below are optional.

## Summary

The revision is thorough, and it is reproducible. I re-ran `make_prefix_data.py` over the original scratch run
directories. Its CSV, stats file and 244 record copies are byte-identical to the committed ones, except for the
directory naming of the four `k2_extra` data sets (I2-m3). I checked every number in the K=20 table, the matrix, the
Newton-step table and the §6.3 row-by-row table against the CSV. For the contested `yldot` count I also went back to
the raw `.npz`. All of them are correct except one swapped pair (I2-m1). The author is right that `yldot` equals
serial in **2/20** K=20 jacrhs runs, not 1/20. My round-1 count was wrong, and so was my "1.005e32" (it is 1.005e31).
Five of the six round-1 majors and all five minors are resolved. The Linux finding is disclosed precisely, but the
decision has not been made.

## Findings

### BLOCKER

None.

### MAJOR

No new majors. I1-M4 remains open (see "Status of previous findings").

### MINOR (new, all on changed material)

**I2-m1: run5 and run14 nonzero counts are swapped** (doc line 105, K=20 table, row "`tebox` / jacrhs, no Newton step
(run5, run14)")

- **What the doc says.** The row gives fnrm in the order run5, run14 (0.1645…, 0.1670…), which is correct. It then
  gives nnz as "181, 177".
- **What the CSV says.** run5 has `nnz_post_exmain` 177 and run14 has 181.
- **To resolve.** Write "177, 181".

**I2-m2: "every number comes from this file or from the CSV" claims too much** (doc line 38)

Several numbers in the section come from material that is neither committed nor in the CSV:
- the `ci_base_pr` overflow counts (lines 81–83), including the 4-thread run with an ordinary iteration-0 fnrm,
  1.535419111648428, that overflowed later;
- the `v56/new_*_it3_k5` timings and the AIUE-57 §5 timings;
- the build-log times;
- the phi `out.log` files;
- `scratchpad/m2`.

I checked the `ci_base_pr` and `v56` values in the scratch directory, and they are correct. The `ci_base_pr`
observation matters for the bonus track: an ordinary iteration 0 does not rule out a later overflow on the RHS arm.
Yet it is the one RHS-arm result that has no committed record.

**To resolve.** Either add the `ci_base_pr` jacrhs `record.json` and `run.log` lines to `records/` (they are small), or
change line 38 so it names these exceptions and their locations.

**I2-m3: the script's documented invocation doesn't reproduce the committed paths**
(`make_prefix_data.py` docstring)

- **The names.** The docstring gives the extra data sets as `k2_extra/<flow>/full/jacrhs_t<N>`, for example
  `k2_extra/AIUE-52/acc_all_k2/...`. The committed data uses `k2_extra/AIUE-52_acc_all_k2/...`, `AIUE-52_quick`,
  `AIUE-52_r1_quick` and `rev52_quick`. Run as documented, the script writes 18 CSV rows, 9 stats lines and the record
  tree under different names. The content is identical: I diffed it.
- **The summaries.** The three `records/*/flow_summary.md` files are not written by the script, and the docstring does
  not mention them.
- **To resolve.** Make the docstring give the NAME=DIR pairs that were actually used, and note where the
  `flow_summary.md` copies come from.

**I2-m4: two timing labels are inconsistent** (doc lines 171 and 192)

- **The load on line 171.** The row gives load "10–40" but includes the `r54_new` runs. The data-set table (line 46)
  gives those runs a load of 24–113.
- **The baseline on line 192.** The "~2× at 4 threads" ratio uses 1.5–1.8 s as the one-evaluation baseline. Those are
  the `OMPJacNchunks=-1` runs, not default-setting runs.
- **To resolve.** Label the load and the baseline correctly. The ratios are only approximate in any case.

## Status of previous findings

| ID | Status | Evidence I checked |
|---|---|---|
| **I1-M1**: numbers don't match the CSV | **Resolved** (one swap left, I2-m1) | See the checks listed below the table |
| **I1-M2**: RHS-arm misdescribed | **Resolved** | See the checks listed below the table |
| **I1-M3**: §6.3 not addressed row by row | **Resolved** | See the checks listed below the table |
| **I1-M4**: Linux | **Partially resolved; remains MAJOR, for the owner** | See the judgement below the table |
| **I1-M5**: timing table | **Resolved** | See the checks listed below the table |
| **I1-M6**: records not committed | **Resolved** (I2-m2 and I2-m3 are leftovers) | See the checks listed below the table |
| **I1-m1**: harness commits, false agree | **Resolved** | 197 `ok` rows, all engaged. `fbe0adf`, `5fb700b` and `de57d59` are named per data set. `de57d59` is the tip of `feature/v9-AIUE-49-omp-harness-core` |
| **I1-m2**: paths not on this branch | **Resolved** | Both branches exist. `docs/reviews/AIUE-52-validation.txt` is on `feature/v9-AIUE-52-omp-test-flow`, and `tests/deterministic_omp/harness/` is on AIUE-49. The merge order is stated |
| **I1-m3**: phi evidence | **Resolved** | The wording now says "no phi-row mismatch was observed, but phi can't be judged independently". `te_phi` jac: mismatch rows `te` only in 6/6 K=2 runs and 3/3 controls. jacrhs: 6/6 have no record (crash). The iv list includes 84, flagged as planning-note only |
| **I1-m4**: sample behind "Ti clean" | **Resolved** | 12 K=2 runs plus 3 controls, all agreeing. `mismatch_row_eqs` is `te` for all 20 `k20_full` runs and for the 6 jac and 4 jacrhs completed `k2_all` full runs |
| **I1-m5**: full pattern not a superset | **Resolved** | Over the 20 `k20_full` runs: extra 443,011–487,854, missing 225–1736, entries differing 602,423–665,917. Column split: ni 53–54 %, up 17–18 % and so on, from the stats file |

**I1-M1 checks.** Each value matches the CSV:
- Te-box jac fnrm 0.1357213635807744–0.1786270608456234, with 10 distinct nnz between 176 and 187.
- Full nnz 3,632,025–3,677,607 (20 distinct).
- Full fnrm: 16 distinct values; the most common is 1.535419111648367 (5 runs) and the maximum 1.537122945485376.
- Te-box jacrhs, split into the two populations: 18 runs at 4.9e30–1.005e31 and 2 at 0.1645/0.1670.
- Matrix `full` jac entries: 448,768–449,736 / 601,948–610,901 / 774,378–777,247.
- Matrix `full` jacrhs, 4 and 8 threads: entries 651,109–655,853 and 627,405–766,390; `yldot` 2198–2560 and 2158–2560;
  345 opposite-sign zeros.
- The "2.4e31" explanation: the value printed was `0.2395993421575909E+31`, which is 2.4e30, as the author says.

**I1-M2 checks.** The new subsection is correct:
- **Te box.** 18/20 runs have an iteration-0 fnrm above 1e20 and `ijactot=2`. Their stored |J| max is 1.0. Their last
  printed fnrm is 0.0043–0.207. The K=2 split is 1/2, 2/2, 2/2. The jac arm has 0 of 46 Te-box runs above 1e20.
- **Full problem, overflow.** Above 1e20 in 10/10 runs at 2 threads (1.74e24–1.31e31), 4/10 at 4 threads
  (`acc_all_k2` 2, `rev52/quick` 2) and 0/4 at 8 threads. Every overflowing run ends with
  `lusol0 loop 40`.
- **Full problem, the rest.** Ordinary runs at 4 threads: 1.535419111648416–…429. At 8: …427–…441.
- **`ci_base_pr`.** The 2/2 + 2/2 overflow and the ordinary-then-overflow 4-thread run0 are confirmed from
  `ci_base_pr/full/full/jacrhs_t*/run*/run.log` and `summary.md`.
- **The `stored_jacobian` column.** It separates the iteration-0 runs from the later-iteration runs, and the K=20 table
  reports them separately.

The author's disagreement: **I accept the rebuttal.**
- Direct `.npz` comparison: `yldot` is bitwise equal to serial in jacrhs run5 and run14, which is **2/20**.
  `yldot_probe` equals serial in run5 only, which is 1/20.
- My round-1 "1/20 for `yldot`" was wrong.
- In run14 the probe is around −5e35 while `yldot` itself is ordinary. That is consistent with the doc's "all 25
  entries differ".

**I1-M3 checks.** The new table has 19 rows, and I spot-checked these against the CSV:
- Te box: "0.1357–0.1930 over all 25" one-evaluation default 4-thread jac runs; `sfscal` 17–21 over the same 25;
  14–15 at 2 threads and 21 at 8 threads.
- Te box: 7–18 extra entries and 0 missing; max |J| 2.22e43–2.60e43.
- Te alone: 0/5 runs agree with serial.
- Ti, ni, up and ng: 48/48 runs plus 12/12 controls agree.
- Serial: K=3, all 3 agree. One thread: 3/3 on each arm.
- `OMPJacNchunks=-1` plus `OMPAutoBalance=0`: 0.2612 × 2, 0.0456 and 0.0877. `OMPJacNchunks=-1` alone: 0.2612 × 3 and
  0.1606.

The rows marked "not re-measured" each give a defensible reason. Labelling `scratchpad/m2` as a post-C1 result is
correct and important.

**I1-M4 judgement.** The record is adequate as a disclosure:
- it is prominent;
- it lists exactly what Linux lacks beyond the AIUE-57 CI job;
- it gives the exact commands to run;
- it makes no Linux claim.

It is not a decision, though. Line 14 says "owner decision, **still open**", and no follow-up ticket key is named.
Acceptance criterion 1 ("per … platform") and PRD R4 ("Measure on both in Phase 1") can't be signed off while the
choice is open.

Acceptance condition: the section records the owner's actual choice. That is one of:
- accept the gap for AIUE-54, with who and when;
- defer it to a named Jira key that runs the listed commands on a libgomp-only build;
- run it now.

That is a one-line edit once the owner has decided. I make no judgement on which option the owner should choose.

**I1-M5 checks.** The table is rebuilt with build and load per row, and the values match the records:
- Te box: controls 11.08–12.6 s. `r54_new`, `--itermx 3`: serial 1.69–1.71, 2 threads 1.69–2.64 and 4 threads
  2.94–3.22 s.
- Full problem: K=20 54.51–157.5 s with serial 317.88 s; controls 99.04–110.73 s with serial 297.79 s.
- Full problem, `--itermx 3`: serial 212.42/213.73 s, 2 threads 237.7 s, 4 threads 128.64 s.
- `v56`: Te box 9.9–12.98 s with serial 11.07 s; full 114.59–492.95 s with serial 953.58 s.

The "upper bound" claim is gone. The 1259.3 s figure is traced to `rev52/quick`. The limits for a 4-vCPU Linux
budget are stated explicitly. Two labels are slightly off (I2-m4).

**I1-M6 checks.** 247 tracked files under `records/` (988 KB), including the failed runs. The CSV has 40 columns,
covering:
- `ijactot`, the iteration counts and `stored_jacobian`;
- provenance (`ParallelJac`, `ParallelPandf1`, `Nthreads`, `OMP_NUM_THREADS`);
- the per-section mismatch counts;
- a result digest.

It is regenerable bit-for-bit (I2-m3 aside). The `.npz` files are excluded, and the doc says so.

## What was checked and how

- **Branch contents.** `git log --oneline f516b40..HEAD` gives 3 commits. `git diff --name-only f516b40..HEAD`
  touches only `docs/`. The AIUE-50 sections are unchanged: the only deleted line is the Status line.
  `git merge-base --is-ancestor f516b40 HEAD` holds.
- **The context check.** `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` gives OK, exit 0.
  The listed AI-layer citations all come from the base commits on `f516b40` (AIUE-46/50), not from this ticket. There
  are no `.claude/`, skill, agent or hook changes in `f516b40..HEAD`.
- **Reproducing the data.** I re-ran
  `scratchpad/rev54/regen.sh` (`/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev54/regen.sh`).
  It calls `make_prefix_data.py` with the docstring's NAME=DIR pairs and writes to `scratchpad/rev54/r2out/`. Then:
  - `diff` against the committed CSV, stats and `records/` shows only the `k2_extra` naming;
  - `diff -r` of each renamed `k2_extra` subtree shows the contents are identical.
- **Checking the numbers.** Python over `prefix_runs.csv` covers every number cited above.
- **The rebuttal and the eq encoding.** Direct `.npz` comparison of `yldot` and `yldot_probe` for all 40 `k20_tebox`
  runs. The `eq` encoding in a full record (0, 1, 2, 3, 4, 6) matches the script's `EQ` list, with phi = 6.
- **Scratch sources.** `ci_base_pr` logs and summary; `v56/new_*_it3_k5` record `elapsed_s`.
- **Branches and the PRD.** Both cited branches and their files exist. PRD lines 121, 138, 503, 554 and 603 (R4) were
  read for the Linux finding.
- **Not run.** No UEDGE runs and no builds.
