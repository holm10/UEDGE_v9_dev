# AIUE-55 implementation review, round 4: Jacobian RCA and Phase 2 exit decision

Reviewed: `feature/v9-AIUE-55-omp-jacobian-rca` at `9599d77` (round-3 changes: `git show HEAD -- docs/rca`). The branch
was rebased onto the reviewed AIUE-54 tip `c4cc9ff`. The owner authorised this round beyond the 3-round cap. No product
code, skills, agents or hooks changed. References: PRD AIUE-8 §9 and §11, decision 9, the round-3 report and response.
The main session is adding the Newton-trajectory/fnrm and `te_phi` experiments separately, so their absence is not
counted here.

## Verdict

**APPROVE**

## Summary

All four round-3 findings are fixed where the owner will look for them. The option F row now states the tested
scheduling (`schedule(dynamic,OMPLoopJacNchunk)`, carried worker state), that the reproducibility is empirical and was
seen only at 4 threads, and what a production F needs to be reproducible by construction. It also states the E/F
asymmetry. The cost is labelled as an estimate with its T-dependence, the table renders, and F's gate result is given.
I checked the code and the scratch records again and they agree with the text. When I read §Jacobian RCA through as
the owner would, I found no remaining BLOCKER or MAJOR problem. The options are neutral, and each option states its
serial impact and its gaps. Two small leftovers remain. Three summary sentences still describe F/worker state the old
way, and one emulation claim ("0 for 4 chunks") is not backed by a record. I missed the second one in round 3. Neither
changes the decision. Both are optional one-phrase fixes.

## Findings

### BLOCKER

None.

### MAJOR

None.

### MINOR (leftovers of earlier findings; optional, they do not block)

**I4-m1. The F/worker-state wording outside the F row was not updated (leftover of I3-M1, acceptance item 1).**
- Status line (line 5): "a static partition gives run-to-run reproducibility without replay". This is still stated
  as a property, but the F row now correctly calls it empirical. Acceptance item 1 named the status line explicitly.
- Recommendation (line 162): "F … cheaper, also OpenMP-only, also needs the crash fix". It leaves out the second
  requirement the F row now gives: a fixed chunk-to-thread mapping (`schedule(static)`, one chunk per thread) or a
  fixed worker state at every chunk start.
- C2 root-cause row (line 27): "OpenMP workers start each chunk from the fresh full-RHS state". This is true only for
  a worker's first chunk. With `schedule(dynamic,1)` the state carries over from that worker's earlier chunks
  (`ppp/omp_parallel.F90:680-693,712`; `LocalJacBuilder` does not reset the state). Emulation item 1 ("what an OpenMP
  worker effectively does", line 56) is the same approximation.
- The F row is correct and explicit, and an AIUE-61 implementer will read it, so the risk named in round 3 is
  covered. *Acceptance:* add "(empirically, at 4 threads)" to the status line, add "and a fixed chunk-to-thread
  mapping or per-chunk state reset" to the recommendation's F clause, and change "each chunk" to "their first chunk"
  in the C2 row.

**I4-m2. "R = `ubw` … 0 for 4, 8 and 16 chunks" (item 5, line 78) is not supported for 4 chunks (leftover of I2-M2,
part 1, which I missed in round 3).** The emulation records hold R = 3920 only for 8 and 16 chunks
(`replay/em_chunks8_r3920`, `em_chunks16_r3920`: mul n = 0). The 4-chunk records are R = 14/1036/1554/2072, giving
479/162/112/0. There is no `em_chunks4_r3920`. The cost bullet of the same item correctly says "nor emulated at
R=`ubw` with 4 chunks", so the item contradicts itself. Practically, 4 chunks already reach 0 at R = 2072 < `ubw`, and
the per-configuration table only claims 16 chunks for the full problem, so the decision is not affected.
*Acceptance:* write "0 for 8 and 16 chunks (4 chunks: 0 already at R = 2072; R = `ubw` not run)".

## Status of previous findings

| Finding | Status | Evidence |
|---|---|---|
| I3-M1 F's determinism presented as a property of the partition | **Resolved in the decision text**; summary-text leftover I4-m1 | F row (line 157) now has: `schedule(dynamic,OMPLoopJacNchunk)` at `ppp/omp_parallel.F90:712` (confirmed: `!$omp parallel do schedule(dynamic,OMPLoopJacNchunk)`), `OMPLoopJacNchunk=1` (confirmed `ppp/ppp.v:54`, `/1/`), carried worker state (confirmed: one master `pandf(-1,-1)` + `OmpCopy*` per Jacobian at `:680-693`, no reset per chunk), "empirically", "reproducibility is empirical, not guaranteed", the production requirement (`schedule(static)` one chunk per thread, or a fixed worker state per chunk start; with `OMPJacNchunks<0`, `NchunksJac=Nthreads` at `:312-317`, so the static variant is well defined), "consistent with PRD §11's fallback at 4 threads on this evidence" instead of "meets as written", the gaps (2/8 threads, fresh CI sessions, Newton iterations), and the E/F contrast. The status line, the recommendation and the C2 row were not updated (I4-m1). |
| I3-m1 two unlabelled cost figures, "at best" wrong | **Resolved** | Line 107 and the E row both say "estimated", give ≈ 4.4 % × T, and say "not measured". "At best" is gone. Arithmetic: 3920/(2·44352) = 4.42 %, giving 8.8 / 17.7 / 35.4 % at 2/4/8 threads. "Exceeds 10 % from 4 threads on" is correct. |
| I3-m2 table header `||` | **Resolved** | Header, delimiter and every data row have 7 cells (lines 140-148). The options table has 5 cells in every row (150-158). |
| I3-m3 F's tolerance result missing | **Resolved** | F row: "AIUE-56 tolerance gate PASS on those records, worst 4.59e-9 × row max". This matches my round-3 gate output (`rev55r3/gate.txt`: `gate_n16` run0/run1 PASS, worst 4.59e-09). |
| I2-M2 (closed as "mostly resolved" in round 3) | Leftover I4-m2 found on re-reading | See I4-m2. |
| Earlier minors (I1-*, I2-m*) | Not reopened | Accepted in rounds 2 and 3. |

**Read-through as the owner (claims vs evidence, neutrality, completeness).**
- *Exit-decision answer* (line 133). "Yes for the configurations tested so far (one evaluation, 4 threads, Te box and
  full problem)" is scoped to the evidence. The per-configuration table marks every untested cell "not run".
  `te`/`te_phi` with replay, the jacrhs arm, 2/8 threads and Linux are all open and shown as open.
- *Serial impact per option.* E, B, F and D are unchanged (E: `bs_*_serial` = `rp_*_serial`, checked in round 2). A
  and A′ change, with the fnrm/nnz/yldot effect quantified for A and "pytests effect not measured" stated. C changes
  at round-off ("expected"). Each option row lists its gaps or marks its claim as "expected"/"to be measured".
- *Neutrality.* The recommendation is conditional for every branch: E if bitwise is wanted, F if the §11 fallback is
  enough, B interim only, D after Linux measurements, A if a build change is preferred. It states the downside that
  matters for each: E's estimated cost, F's lack of bitwise agreement and its scheduling requirement (row), B not
  being deterministic, A changing the defaults. "A only if the owner prefers changing the build" follows from the
  hard rule on default changes. It does not steer the owner. E's claim to be independent of the chunk assignment is
  a mechanism argument, but it is backed by the 16-chunk-on-4-threads prototype under the dynamic schedule (3/3
  AGREE, deterministic). So it is no more empirical than F's claim, and the asymmetry is fair.
- *Cost.* Every cost figure is now labelled as an estimate or as a measurement with its basis, and the §9 measurement
  is marked as pending (AIUE-61).

## What was checked and how

All read-only, on macOS arm64. No UEDGE runs.

1. `git show HEAD -- docs/rca` and `git diff --name-only c4cc9ff..HEAD`: only the RCA, the review files and the
   ticket plan `.claude/plans/AIUE-55-omp-jacobian-rca.md` changed. No skills, agents, hooks or settings.
   `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`: OK.
2. Code: `ppp/omp_parallel.F90:300-330` (NchunksJac), `:645-748` (OMPJacBuilder: copy once, dynamic schedule,
   per-chunk write-back by `ichunk`); `ppp/ppp.v:45-56` (`OMPAutoBalance /1/`, `OMPLoopJacNchunk /1/`).
3. Records: `scratchpad/rev55r3/gate.txt` (round-3 gate), and `scratchpad/replay/em_*/emul.json` for every emulation
   depth and chunk count (neq 44352, nnz_ref 3 190 290; "mul" counts 479/162/112/0 at 4 chunks with
   R = 14/1036/1554/2072, 84/0 at 8 chunks with R = 2072/3920, 0 at 16 chunks with R = 3920).
4. Arithmetic: `python3 -I -c` gives the T·ubw/(2·neq) overhead (8.8/17.7/35.4/70.7 % at T = 2/4/8/16).
5. Table cell counts with `awk` over lines 140-158.
6. A full read of §Jacobian RCA (lines 13-174) against PRD §9/§11 and the round-1 to round-3 evidence.
