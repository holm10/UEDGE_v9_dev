# AIUE-55 implementation review, round 3: Jacobian RCA and Phase 2 exit decision

Reviewed: `feature/v9-AIUE-55-omp-jacobian-rca` at `77c5958` (diff `48e877c..77c5958`: the RCA, plus the round-2 report
and response). Base `45a9aa1` (AIUE-54, reviewed). No product code, skills, agents or hooks changed. References: PRD
AIUE-8 §9 and §11, decision 9, the round-2 report and the response.

## Verdict

**REVISE**

## Summary

Round 2's two majors are essentially fixed. B now cites the default-chunk data (70 entries). The static row is correct.
The new option F and its column in the per-configuration table match the scratch records. The cost figures are
labelled as estimates, the thread dependence is given, and the PRD §9 measurement is marked as pending. The F9
correction is right. The new option F brings one decision-relevant problem. It is described as "contiguous chunks
fixed per thread", and it says it "meets PRD §11's fallback as written". But the code it was tested on assigns chunks
to threads with `schedule(dynamic,1)`, so its run-to-run reproducibility is an empirical observation (3 + 2
single-evaluation runs at 4 threads), not a property of the design. §11 also asks for reproducibility "at each thread
count", and only 4 was run. The fix is a few sentences. The recommendation is still neutral.

## Findings

### BLOCKER

None.

### MAJOR

**I3-M1. Option F's determinism is presented as a property of the partition. The tested code does not fix chunks to
threads, and "meets §11's fallback as written" goes further than the evidence.**
- *Location:* RCA status line ("a static partition gives run-to-run reproducibility without replay"); option F row
  (line 157: "contiguous chunks fixed per thread (no auto-balance) … meets PRD §11's fallback as written, on this
  evidence"); the new F column of the per-configuration table.
- *Evidence:*
  - `OMPJacBuilder` distributes chunks with `!$omp parallel do schedule(dynamic,OMPLoopJacNchunk)`
    (`ppp/omp_parallel.F90:712`), and `OMPLoopJacNchunk` defaults to 1 (`ppp/ppp.v:54`). The provenance of
    `replay/te_contig_R0/check.json` records `OMPLoopJacNchunk: 1`. `OMPAutoBalance=0` fixes the chunk *boundaries*
    (`OMPivmin/ivmax`). It does not fix which thread runs which chunk.
  - `LocalJacBuilder` (`ppp/parallel.F90:159-345`) does not reset the worker state at the start of a chunk. The
    threadprivate state is copied from the master once per Jacobian (`pandf(-1,-1)` and `OmpCopy*`, `omp_parallel.F90:680-693`)
    and then carried from chunk to chunk. By the RCA's own M2 mechanism (history over at most `ubw` preceding
    columns), chunk k sees serial-like history near its start if the same thread ran chunk k-1 earlier in the loop,
    and fresh-like history otherwise. So F's residual pattern depends on the chunk-to-thread assignment, and under
    `schedule(dynamic,1)` that assignment depends on timing.
  - For the full-problem F evidence (16 chunks on 4 threads, `t_c1_n16_1/_2`), chunks are handed out dynamically. The
    two runs being bitwise identical (I re-checked: every array in `record.npz` is equal) shows that the assignment
    came out the same twice, not that it is fixed. For the Te box (one chunk per thread, about 6 columns each),
    nothing stops a thread from taking two chunks either. 6/6 identical runs over two builds is good evidence but
    not a guarantee.
  - PRD §11's fallback requires "bitwise reproducibility across fresh sessions **at each thread count**". The F row
    lists 2/8 threads as not shown, so "meets … as written" contradicts its own gap list. "On this evidence" does not
    cover a requirement that was not tested.
  - Contrast with E: replay rebuilds the history from the preceding `ubw` columns whichever thread runs the chunk, so
    E does not depend on the assignment. This difference matters to the owner's E-vs-F choice, and the RCA does not
    state it.
  - I should note that my round-2 finding I2-M1 assumed "a fixed column-to-thread mapping" without checking the
    `schedule` clause. The author took that framing over. The data I asked to be reported are correct. The mechanism
    is not.
- *Why it matters:* If the owner picks F, AIUE-61 could ship `OMPAutoBalance=0` plus few contiguous chunks under the
  existing dynamic schedule. It would then hit intermittent run-to-run differences in the 30/30 and CI gates, which
  is exactly the failure F is meant to remove.
- *Acceptance:*
  1. In the F row and the status line, say that the tested code assigns chunks with `schedule(dynamic,1)`, and that
     the observed reproducibility (Te box 3/3 at `918bdb6`, plus 3/3 on the swap build; full problem 2/2 at 16
     chunks; all one evaluation, 4 threads) is empirical.
  2. State what a production F needs to be reproducible by construction: a fixed chunk-to-thread mapping
     (`schedule(static)` with `NchunksJac = Nthreads`), or a fixed worker state at every chunk start (for example a
     fresh copy or `pandf(-1,-1)` per chunk). Note that this is an OpenMP-only change like E.
  3. Replace "meets PRD §11's fallback as written" with a statement that matches the gaps. For example: "consistent
     with the §11 fallback at 4 threads on this evidence; 2/8 threads, CI fresh sessions and ≥ 3 Newton iterations
     not shown".

  If the author can show that the chunk assignment cannot affect the residual (for example by an emulation that
  permutes which chunks each worker runs before chunk k), a rebuttal on that basis would be accepted instead of
  item 2.

### MINOR

**I3-m1. Two cost statements are still unlabelled (remainder of I2-M2).** Line 107 says "The cost exceeds 10 % (≈
+18 % at best)". The E row (line 152) says "≈ +18 % Jacobian work at one chunk per thread (reported per §9)". Both
are evaluation-count estimates. "At best" is also wrong by the RCA's own formula: 4.4 % × T gives ≈ +9 % at 2
threads, which is below the §9 report threshold. Label both as estimates and give the T-dependence, or point to item
5.

**I3-m2. The per-configuration table does not render.** The header (line 140) has `… (+ C1) || static partition …`.
That double pipe makes 8 header cells against 7 cells in the delimiter row and in every data row (I counted them).
GitHub-flavoured Markdown then shows the whole table as plain text. Remove the extra `|`.

**I3-m3. F's tolerance result is not stated (round-2 acceptance I2-M1 item 2).** The F row says "tolerance as in B"
but does not say whether F's residual passes. I ran the AIUE-56 gate on the existing records, and it passes:
`t_c1_n16_1` and `_2` against `bs_full_serial` give GATE PASS (magnitude ratio 1, worst |a−b|/rowmax 4.59e-9),
`check_arm` clean. The residual is larger in count (5698 entries) but has the same maximum relative size as the
default-chunk runs. Add one line saying this.

## Status of previous findings

| Finding | Status | Evidence |
|---|---|---|
| I2-M1 static partition misreported; static + tolerance not offered | **Resolved** (acceptance items 1 and 3); item 2 partially (gate result not stated, I3-m3); the new F text has a separate problem (I3-M1) | Line 37 now says "2 … no: the runs are bitwise identical to each other". I confirmed `te_contig_R0/check.json` (2 mismatches te(4,20)×te(3,21) in 3/3 runs; determinism run0–run1 and run0–run2 AGREE) and `m2/tebox_static.txt` (same). B now cites `t_c1_dflt_1` vs `_2`: my array compare shows `jac_post`/`jaci_post`/`jacj_post` differ, which matches the 70 entries from round 2. F is added as an option, a table column and a recommendation branch. |
| I2-M2 +18 % unlabelled estimate, T-dependence, §9 measurement | **Mostly resolved**; remainder I3-m1 | Item 5 now says "**estimates**, except where marked measured", "≈ 4.4 % × T", "not run … nor emulated at R=`ubw` with 4 chunks", excludes the cost of leaving the dynamic schedule, describes the 16-chunk figure as two whole-process timings with a ~9 s spread, and says "measured Jacobian times PRD §9 asks for are pending (AIUE-61)". The status line and recommendation say "estimated". Lines 107 and 152 do not. |
| I2-m1 crash details | **Resolved** | Line 98 now has the full problem only, the Te box running with `OMPJacNchunks=-1`, `:672,675` / `:713-714` / `:321`, and "Inferred cause … no backtrace kept". These match the code I read. |
| I2-m2 scope of "reachable" | **Resolved** | The exit-decision question says "(one evaluation, 4 threads, Te box and full problem)". The new scope bullet gives the commits per row (`918bdb6` Te box, `db6a8ea` full) and the leftover `isjacreset` call is left to AIUE-61. These match the `check.json` provenance. |
| Residual minor: F9 row | **Resolved** | `mombal` is called only under `isimpon .eq. 5` (`bbb/pandf_plasma_momentum.m:669-671`, `:701-703`). `isimpon` 6/7 call `mombalni` (`:673-675`, `:705-707`). `fmombal`'s only caller is `mombal` (`:1018`; grep over `bbb/`, `api/`). The deck uses `isimpon=6`, then 7 (`tests/deterministic_omp/case/input_mod4.py:27,307`), so "not exercised by this deck" is right. The row now agrees with H3. |
| Residual minor: column loop start | **Resolved** | `bbb/oderhs.m:1095-1226`. |
| I1-m1, I1-m3, I1-m4 remainders, I1-m6 caveat | Not reopened | These were accepted as non-blocking in round 2. Per the round-3 rules, no new minors on unchanged material. |

**Is the decision neutral?** Yes. The recommendation sets out E (if bitwise is wanted, with estimated cost), F (if
the fallback is enough), B (interim only), D (Linux first) and A (if a build change is preferred), and leaves the
choice to the owner. Once I3-M1 is fixed, the one asymmetry the owner needs to see will be stated: E is
schedule-independent, F needs a fixed mapping.

## What was checked and how

All read-only, on macOS arm64. No UEDGE runs. Outputs are in
`/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev55r3/`.

1. **Diff.** `git diff 48e877c..77c5958`. Only the RCA and the two review files changed. `git diff --name-only
   45a9aa1..HEAD` shows no `.claude/skills|agents|hooks` or settings. `uv run .claude/hooks/check_context_refs.py
   --changed origin/v9-develop`: OK.
2. **F evidence.** I read `replay/te_contig_R0/check.json` (spec, provenance, reports) and `m2/tebox_static.txt`.
   `rev55r3/cmp.py` compares the full `record.npz` contents bitwise: `t_c1_n16_1` vs `_2`, no differing arrays;
   `t_c1_dflt_1` vs `_2`, Jacobian arrays differ; `bs_full_serial` vs `t_c1_n16_1`, Jacobian differs;
   `bs_full_serial` vs `t_rp_n16_1`, no differences. `t_c1_n16_1/spec.json`: `OMPJacNchunks=16`,
   `OMPAutoBalance=0`, `OMPlenpfac=2`, 4 threads, single evaluation (`itermx` null).
3. **Gate.** `python -I docs/reviews/AIUE-56-c1-gate.py --harness <AIUE-49 tests/deterministic_omp>` (from the AIUE-56
   worktree) on directories symlinked from `bs_full_serial` with `t_c1_n16_1/_2` (`rev55r3/gate_n16`) and with
   `t_c1_dflt_1/_2` (`rev55r3/gate_dflt`). GATE PASS. Worst deviations: 4.59e-9 for the 16-chunk runs; 0 and 1.48e-10
   for the default-chunk runs (`rev55r3/gate.txt`).
4. **Scheduling code.** `ppp/omp_parallel.F90:312-323` (NchunksJac, `nnzmxperchunk`), `:645-748` (OMPJacBuilder: one
   master `pandf(-1,-1)` and copy per Jacobian, `schedule(dynamic,OMPLoopJacNchunk)`, chunk loop);
   `ppp/parallel.F90:159-345` (LocalJacBuilder: no state reset per chunk); `ppp/ppp.v:50,54` (`OMPAutoBalance` /1/,
   `OMPLoopJacNchunk` /1/).
5. **F9.** `bbb/pandf_plasma_momentum.m:660-710, 867, 1018, 1042-1201`; grep for `fmombal` callers; `isimpon` in the
   deck.
6. **PRD.** §11 (MVP, fallback bullets "at each thread count", acceptance sizes) and §9 (measurement, 10 % report).
7. **Table.** I counted the cells in lines 140-142 of the RCA: header 8, delimiter 7, rows 7.
