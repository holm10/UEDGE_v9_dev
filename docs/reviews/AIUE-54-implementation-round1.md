# AIUE-54 implementation review, round 1: "Characterise both arms and record pre-fix rates"

Reviewed: `feature/v9-AIUE-54-omp-characterisation` at `e4f738c`, diff `4c0abd7..HEAD`. The diff touches
`docs/rca/AIUE-8-omp-jacobian-nondeterminism.md` §"Characterisation before any fix (AIUE-54)" and `docs/rca/AIUE-8-data/`
(the per-run CSV `prefix_k20_4threads.csv` and two flow summaries). The ticket's acceptance criteria are the reference.

## Verdict

**REVISE**

## Summary

The headline results hold. I recomputed them from the raw records. At 4 threads the full problem disagrees with serial
in 20/20 runs. The Te box disagrees in 20/20 runs on both arms, and no two of its 20 runs are identical. Ti, ni, up and
ng alone agree bitwise with serial on both arms at 2/4/8 threads. Every record shows the OpenMP arm actually took
effect, so the pre-`check_arm` harness produced no false "agree". Even so, the section does not yet meet its acceptance
criteria:
- several numbers in the K=20 table contradict the committed CSV;
- the RHS-arm Te-box results describe a different object from what was measured (18 of the 20 runs took a Newton step
  and recorded a second, row-normalised Jacobian);
- the PRD §6.3 observations are not confirmed or corrected row by row;
- Linux is missing, and the deferral target does not cover it;
- the timing table contradicts the doc's own data and leaves out the ≥ 3-iteration cost that the CI budget depends on;
- the JSON records are neither attached nor durably referenced, even though they total 160 KB.

All of these are fixable without new physics. Most of them need no new UEDGE runs.

## Findings

### BLOCKER

None.

### MAJOR

**I1-M1: numbers in the K=20 table do not match the committed CSV or the records** (doc, table "Pre-fix rates at 4
threads", and the matrix row `full` / Jacobian + RHS)

| Doc says | CSV / records say |
|---|---|
| `tebox`/jac fnrm "0.1487 … 0.1775" | min 0.1357213635807744 (run13), max 0.1786270608456234 (run18) |
| `tebox`/jac nonzeros "176–189" | 176–187, with 10 distinct counts (that count is correct) |
| `tebox`/jacrhs fnrm "20 (≈8e30)" | 18 runs between 4.9e30 and 1.005e32. Runs 5 and 14 are ordinary: 0.1645 and 0.1670 |
| `full`/jac nonzeros "3.62–3.69M" | 3,632,025–3,677,607 |
| matrix, `full` jacrhs at 2 threads "(fnrm 2.4e31)" | The acceptance run the matrix cites (`acc2_all_k2`) has 6.06e30 and 1.74e24. The value 2.4e31 comes from the earlier first `--all` run (`acc_all_k2`, run0) |
| matrix, "2–2.5k Te entries of `yldot`" | 2158–2560 |

- **Why it matters.** This section is the pre-fix data record. The PRD §11 fallback gate sets tolerances "from the
  observed spread", so readers will copy these ranges.
- **To resolve.** Generate every number in the table from the CSV or the records, preferably with the script that
  wrote the CSV, and say so. Show the Te-box jacrhs fnrm as two populations: 18 runs at ~1e31 and 2 at ~0.165.

**I1-M2: the RHS-arm characterisation misdescribes what was measured** (doc, "One evaluation per run … unless
stated"; the K=20 `tebox`/jacrhs row; the matrix `full`/jacrhs cell for 4 and 8 threads)

- **Te box, more than one evaluation.** In 18 of the 20 Te-box jacrhs runs the parallel-RHS iteration-0 fnrm (~1e31)
  is above `ftol=1e20`, so nksol takes a Newton step:
  - `run.log` shows `npe = 2` and `OMP iter= 1`;
  - `record.json` has `ijactot: 2` and two entries in `iterations`;
  - `grep -la 'iter=   1'` finds 18/20 jacrhs logs, 0/20 jac logs, and 0/20 full-problem logs.
- **What the records hold in those 18 runs.** The "post-exmain" Jacobian, `sfscal`, `yldot`, `fnrm_final` and the nnz
  in the CSV come from iteration 1, not from iteration 0. The stored Jacobian has every |entry| ≈ 1 (max = min = 1.0 in
  15 runs, min 0.002 in 3 runs). In other words, it is the row-normalised matrix that `post_exmain_jacobian` says is
  not stored. So "Distinct nonzero counts: 4" (15 × 304, 3 × 169, 177, 181) compares the serial iteration-0 pattern
  with a different object. The FAIL verdicts are still correct, because serial takes no step, but the description is
  not.
- **Full problem at 4 threads.** The same blow-up also happens on the full problem at 4 threads. The matrix cell
  "4, 8: FAIL in Te rows" hides that. Among the 4-thread K=2 runs in the scratch directories:
  - `acc_all_k2` 2/2 and the AIUE-52 reviewer's `rev52/quick` 2/2 have an iteration-0 fnrm of 1.9e25–2.5e31, and the
    AIUE-52 validation section 5 says this run stopped with the lusol0 overflow;
  - `acc2_all_k2`, `quick` and `r1/quick` 0/6 are well-behaved (fnrm 1.535419111648416–441).

  So the overflow is a rate at 4 threads, not a 2-thread-only effect. The well-behaved jacrhs runs also show the PRD's
  "fnrm varied in the 15th digit". The doc doesn't say so.
- **`yldot` on the Te box.** In K=20, `yldot` agrees with serial in 1/20 jacrhs runs and `yldot_probe` in 1/20. So
  "FAIL … Te rows of the Jacobian and of `yldot`" is not universal.
- **Why it matters.** The ticket asks for RHS-arm data "so the bonus track starts from data". The bonus track would
  start from a wrong picture.
- **To resolve.**
  - State the iteration-0 fnrm blow-up and its rate per configuration and thread count.
  - Mark records with `ijactot > 1` as such, and don't report their Jacobian or nnz as iteration-0 quantities. Either
    drop those columns for them or label them.
  - Correct the `full`/jacrhs 4-thread cell, with the run counts behind it.

**I1-M3: the PRD §6.3 observations are not confirmed or corrected explicitly** (acceptance criterion 2)

The section addresses only five items:
- Ti/ni/up/ng;
- Te alone (implicitly);
- phi;
- the stability of the full-problem fnrm (corrected);
- the full-problem Jacobian's run-to-run stability (newly answered).

It is silent on the rest. Several of those can be settled from data already on disk:

| §6.3 observation | Status from the K=20 records (my check) |
|---|---|
| Te box: `sfscal` differs in **4–19** of 25 rows | 17–20 rows on both arms. This is a correction |
| Te box: `yldot` bitwise identical (jac arm) | Confirmed, 20/20 |
| Te box: entries up to ≈ −2.6e43 | Confirmed. max |J| is 2.2–2.6e43 against 5.6e5 in serial |
| Te box: fnrm 0.146–0.185, pattern differs every run | Range 0.136–0.179. The pattern differs from serial in 20/20 runs and is a superset of it (0 entries missing) |
| Full: 2940 of 3168 Te rows of `sfscal` differ | Confirmed: 2937–2940 per run, all of them Te rows |
| Full: `yldot` unchanged on the jac arm | Confirmed, 20/20 |
| Full RHS arm: ~2200 Te rows of `yldot`; 15th-digit fnrm variation | Matrix: 2158–2560 (confirmed). The 15th-digit variation shows in the well-behaved runs, but see I1-M2 |
| Te box: serial repeated is bitwise; OpenMP with 1 thread equals serial; `OMPJacNchunks=-1`/`OMPAutoBalance=0` still non-deterministic; physics-off runs; both builds (April beta) | Not re-measured. The doc must say so explicitly |
| Run time ~2 s / ~12 s | See I1-M5 |

To resolve: add a short "§6.3 row by row" list. Each row is marked confirmed, corrected (with the new value), or not
re-measured (with the reason).

**I1-M4: Linux is missing, and the stated deferral does not cover it** (ticket scope R4; acceptance criterion 1, "per
… platform")

- **The disclosure is good.** It is bold and prominent, and every number is marked macOS-only.
- **The deferral target doesn't cover the gap.** AIUE-57's CI job, as the PRD defines it (§7.6), runs only the Te box
  and the full problem, at 2 and 4 threads. It never covers `te`, `ti`, `ni`, `up`, `ng`, phi or 8 threads on Linux.
  As things stand, nothing in the plan characterises them on Linux before a fix.
- **The PRD asks for Phase 1 measurement.** The R4 mitigation says "Measure on both in Phase 1". R4's specific concern
  is that libomp may be loaded on macOS through the C toolchain, and this build uses Homebrew LLVM clang with libomp.
  A Linux libgomp-only build might behave differently, for example in which configurations are clean.
- **To resolve.** Either:
  - run the matrix (K=2) and the K=20 rates on Linux, for example a `workflow_dispatch` job on a fork or a remote
    Linux host; or
  - record an owner decision that defers it, and name the follow-up ticket and the exact Linux matrix it will run.

  This is a decision for the owner, not something the author can waive.

**I1-M5: the timing table does not support a CI budget** (doc, "Timing (for the CI budget, AIUE-57)")

- **It contradicts its own data.** The table is labelled "upper bounds", but the committed CSV breaks them:

  | Row | Table | CSV |
  |---|---|---|
  | Full problem, 4 threads, one evaluation | 11–13 s | 54–157 s |
  | Full problem, serial reference | 35–55 s | 317.9 s |

  The acceptance run (`acc2_all_k2`) also lies outside both ranges: serial 56.45 s, 4 threads 18.2–19.9 s. I could
  not find the source of the "1260 s (load ~90)" quick-set figure in the cited material.
- **It is missing the cost CI depends on.** PRD §7.6 requires ≥ 3 Newton iterations per run plus serial references.
  The harness's own test fixture shows `nfe = 62` at iteration 1 of the full problem, so iterations after the first are
  not cheap. Every row in the table is a single evaluation. Also missing: the time for the OpenMP build, the comparison
  time for ≥ 3-iteration records, and any 4-vCPU Linux measurement.
- **The "upper bound" logic doesn't transfer.** A loaded 14-core M-series machine does not bound an ubuntu-latest
  runner with 4 vCPU.
- **To resolve.** Re-label the numbers with their load and job settings and make them consistent with the CSV. Add at
  least one timed ≥ 3-iteration run of the Te box and the full problem, at 2 and 4 threads, plus serial. If that has
  to wait for AIUE-57's Linux runner, say so explicitly and state what the CI budget can and cannot take from this
  table.

**I1-M6: the JSON records are not attached, and the references are not durable** (acceptance criterion 1)

- **What is committed.** Only a 5-column CSV and two summaries.
- **The CSV drops the fields that matter.** It leaves out:
  - `ijactot` and the iterations after the first, which is exactly the information that exposes I1-M2;
  - the provenance (`ParallelJac`, `ParallelPandf1`, `Nthreads`, and the harness commit), which is what proves there
    was no false agree;
  - mismatch counts by section.
- **The references don't resolve from this branch.**
  - The K=2 matrix cites `docs/reviews/AIUE-52-validation.txt` on another branch, which is a text summary, not
    records.
  - The JSON files themselves sit in a session `/private/tmp` scratchpad, and the doc doesn't reference them at all.
- **Committing them is cheap.** All `record.json` files of the three runs (K=2 acceptance, K=20 Te box, K=20 full)
  total **160 KB**. The `flow.json` files are 0.37–0.71 MB each. Only the full-problem `record.npz` (59 MB each) is
  too big to commit.
- **To resolve.** Commit the `record.json` files, and the `flow.json` files or a trimmed per-group extract, under
  `docs/rca/AIUE-8-data/`. Or attach them to the Jira ticket and give the attachment names in the doc. Either way,
  state which flow commit produced them.

### MINOR

**I1-m1: the harness commits are not named, and the false-agree question is not addressed in the doc.**
- **The commits.** The K=20 records carry `commit 5fb700b`, the AIUE-52 head before review and before `check_arm`
  (`260720f`). The K=2 records carry `fbe0adf` plus the then-uncommitted flow code.
- **No false agree.** I checked for false agrees and there are none:
  - all 155 readable records have `ParallelJac`, `ParallelPandf1`, `Nthreads` and `OMP_NUM_THREADS` as their arm
    requires;
  - every record holds `sfscal`, `suscal`, `yldot` and `yldot_probe`, so the I1-M1-of-AIUE-52 one-sided skip could not
    have hidden anything;
  - my own bitwise comparison of the 48 ti/ni/up/ng PASS records against serial (with the ±0 rule only on the
    parallel-RHS `yldot`) agrees.
- **To resolve.** State the commits and add a one-line note to this effect.

**I1-m2: paths that don't resolve on this branch.** `tests/deterministic_omp/harness/` and
`docs/reviews/AIUE-52-validation.txt` are not on this branch: AIUE-52 (`11ad769`) is not an ancestor of `e4f738c`.
State the merge-order dependency, or merge AIUE-52 first.

**I1-m3: the phi evidence.**
- **The phi-alone case.** It ("iv = 84") rests on the planning note in the PRD. No log of it exists in the material, and
  the doc's iv list (924/1008/1092) leaves it out.
- **The mapping.** The mapping to phi(ix=11, iy=1) checks out. With nx+2 = 72 and numvar = 11/12/13, iv 924, 1008 and
  1092 all map to cell 83, phi. Iv 84 with numvar = 1 maps to the same cell.
- **The wording.** "Phi shows no defect of its own" goes beyond the evidence. What was observed is that no phi-row
  mismatch appears in `te_phi` on the Jacobian arm. The RHS arm segfaults there, so it gives no verdict. Prefer that
  wording, and cite the logs.

**I1-m4: the sample size behind "Ti clean".** It is K=2 at each of 3 thread counts per arm. Adding that the 20/20
full-problem runs have mismatches only in Te rows strengthens the claim for Ti in the coupled problem. My check found
no Ti-row value or pattern differences in any of the 20.

**I1-m5: the full-problem pattern is not a superset.** Each run also lacks 225–1736 serial entries, and the extras are
0.443–0.488M. The matrix's "0.61M entries vs serial" counts entries that differ in value or pattern, which is a
different measure from "~0.5M extra entries". Label the two. Measured breakdown of the extra entries' columns in run0:
ni 53 %, up 18 %, ng 9 %, te 7 %, phi 6 %, ti 6 %.

## What was checked and how

- `git diff 4c0abd7..HEAD` (4 files, docs only). `uv run .claude/hooks/check_context_refs.py --changed
  origin/v9-develop` gives OK. No changes to `.claude/`, skills, agents or hooks.
- **The CSV against the records.** Every CSV row matches its `record.json` (fnrm printed, `fnrm_final_hex`, nnz,
  elapsed), via `scratchpad/rev54/k20.py`.
- **Te box, from the raw `record.npz` and `record.json`:**
  - agreement with serial over fnrm, `sfscal`, `suscal`, `yldot`, `yldot_probe`, Jacobian pattern and values: 0/20 on
    jac, 0/20 on jacrhs;
  - all 190 pairs of the 20 runs differ, on both arms;
  - distinct fnrm, nnz ranges, `sfscal` row counts, max |J| and `yldot` differences.
- **Full problem** (`scratchpad/rev54/full.py`, vectorised): 20/20 disagree. 20 distinct pattern+value hashes. Extra,
  missing and value-differing entries by row and column equation. 2937–2940 Te rows of `sfscal` differ. `yldot` agrees
  20/20. Max |J| is 5.98e43 against 1.7e14 in serial. 16 distinct fnrm, the most common 1.535419111648367 in 5 runs.
- **Provenance** (`scratchpad/rev54/prov.py`): 155 records across `AIUE-52/acc2_all_k2`, `char_tebox_k20` and
  `char_full_k20`. All have their arm engaged and the right thread count. One `acc2` record is empty: the `phi_te`
  jacrhs t2 run1 crash. The commits are `fbe0adf` (K=2) and `5fb700b` (K=20).
- **The ti/ni/up/ng PASS rows** (`scratchpad/rev54/pass.py`): independently bitwise-equal to serial, 48/48 records.
- **Iteration counts.** `grep -la 'iter=   1'` over the K=20 logs, `ijactot` and `iterations` in the jacrhs records,
  and the iteration-0 fnrm of every full/jacrhs log under the scratchpad (`acc_all_k2`, `acc2_all_k2`, `quick`,
  `r1/quick`, `rev52/quick`, `ci_base_pr`).
- **Phi.** `phi/*/out.log` (iv 924 and 1008, serial). The ni+up+te+phi run succeeded, with neq 38016. Also
  `AIUE-52/phi_*/…/serial/run.log` and `acc_all_k2/full_note` (iv 1092), and the PRD §6.3 row for phi alone (iv 84).
  I recomputed the iv-to-cell mapping by hand.
- **Sources read.** `AIUE-52-validation.txt`, both the matrix and the round-1 revision section;
  `AIUE-52-implementation-round1.md` (I1-B1, I1-M1); PRD §6.3, §7.6, §11, §12 and R4; and the harness `runner.py`
  iteration parser at `5fb700b` and at HEAD.
- **Not run.** No UEDGE runs and no builds, as the run budget required.
