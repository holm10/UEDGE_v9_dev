# AIUE-55 implementation review, round 1: Jacobian RCA and Phase 2 exit decision

Reviewed: `feature/v9-AIUE-55-omp-jacobian-rca` at `080dd8a` (diff `e4f738c..080dd8a`):
`docs/rca/AIUE-8-omp-jacobian-nondeterminism.md` §"Jacobian RCA and Phase 2 exit decision (AIUE-55)" and
`.claude/plans/AIUE-55-omp-jacobian-rca.md`. Reference: the AIUE-55 ticket acceptance criteria, PRD AIUE-8 §7.4, §9,
§11 and binding decisions 4, 7, 8 and 9, and the reviewed AIUE-50 facts (`86ec027`).

## Verdict

**REVISE**

## Summary

C1 (copy order), its effect on the RHS arm, its serial impact (none) and the refuted-hypothesis table hold up. I
checked the code references and reproduced the key experiments. The `-ffp-contract=off` scratch build makes the
Te-box OpenMP Jacobian bitwise equal to its own serial reference and deterministic (3/3). That build's serial
reference really does differ from the default serial (fnrm `0x1.49db83f93d961p-2` → `0x1.49db840c19087p-2`, all 25
yldot entries and 149/169 Jacobian values). The section's main conclusion is that bitwise OpenMP = serial "is not
reachable without changing serial results", so §9(a) applies. That conclusion is not established, and my
experiments contradict it. In my extension of the author's own emulation, each chunk starts from the fresh full-RHS
state (as an OpenMP worker does) and then replays the restoring local evaluations of the columns before the chunk.
That gives back the serial Jacobian bitwise, with serial untouched: one replayed column suffices on the Te box, and
ml+mu = 7840 on the full problem. This is an OpenMP-only "reset" change, and PRD §9
puts such changes in scope without escalation. The option table also labels option B as the PRD §11 fallback gate,
although it drops §11's run-to-run reproducibility requirement. The exit decision is not given per configuration.
The owner would be choosing from an incomplete and partly mislabelled menu, so the decision section has to be
redone before it goes to the owner.

## Findings

### BLOCKER

**I1-B1. "Bitwise OpenMP = serial is not reachable without changing serial" is unproven, and contradicted by
emulation on both the Te box and the full problem. An OpenMP-only option that keeps serial bitwise was not examined.**
- *Location:* RCA §Residual after C1, "So: … bitwise OpenMP = serial is not reachable without changing serial
  results"; §Exit decision, "Not without changing serial results … §9(a) applies to the only change found"; the C2
  row of §Root causes ("Fix: owner's decision 9", "changes serial at round-off"); options A–D.
- *What is wrong:* The RCA's own mechanism says the residual comes from *state carried from column to column* in
  the serial loop. The trigger is the ulp difference between local-loop and full-row evaluations. An OpenMP worker
  differs only because it starts its chunk from the full-RHS state, not from the state serial has at that column.
  Removing the trigger (A, A′, C) changes serial. Giving the worker serial's start state does not change serial, and
  that remedy is not in the table. PRD §9 lists "chunking, resets and copy coverage" as OpenMP-only changes that
  are "in scope without escalation". So the §9(a) escalation and the "unreachable" answer to decision 9 are
  premature.
- *Evidence (reviewer experiment, no product code):* I extended the author's `m2/emul.py` with a variant
  (`rev55/emul_replay.py`). At the start of each chunk it calls `pandf(-1,-1)`, exactly like the author's `chunksK`
  mode. It then replays the restoring local `pandf(xc,yc)` (plus the `isjacreset` call) of the R columns before the
  chunk, with `yl` unperturbed. Default serial build (`venvs/base-serial`), Te box:

  | mode | mismatches vs `exmain` Jacobian (serial) |
  |---|---|
  | `serial` (author's) | 0 |
  | `chunks4` (author's: fresh state per chunk, what a worker does) | 2 (row 12 = te(4,20)), as in the RCA |
  | `fresh` | 2 |
  | `chunks4_r1` (replay 1 preceding column) | **0** |
  | `chunks4_r2`, `_r3`, `_r5`, `_r8`, `_r24`; `chunks2_r3` | **0** |

  Full problem (neq 44352, band ml = mu = 3920, numvar 14), same build, 8 contiguous chunks:

  | mode | mismatches vs `exmain` Jacobian (serial) |
  |---|---|
  | `serial` emulation | 0 |
  | `chunks8` (fresh state per chunk) | 1971 in 28 Te rows (1273 entries serial has and the emulation lacks): the M2 residual |
  | `chunks8_r1` | 1971 (one column is not enough here) |
  | `chunks8_rB`, B = ml+mu = 7840 restore evaluations per chunk start | **0: bitwise equal to serial** |

  So on both test cases the serial Jacobian can be rebuilt bitwise from a worker-style fresh start, without touching
  serial code. The open questions are the minimum replay depth (between 1 and 7840 columns on the full problem) and
  the cost: at depth 7840 with 8 chunks that is about 63k extra local evaluations against about 89k in the loop,
  spread over the workers. They are not whether it is possible. A slowdown above 10 % is a §9 "report to the owner"
  item, not a §9(a) escalation.
- *Acceptance:* (1) Add an OpenMP-only option of this kind: a worker warm-up that replays the restoring evaluations
  of the columns before `ivmin` of each chunk, or any equivalent way of reproducing the serial start state. Measure
  the replay depth needed and the overhead on Te box and full problem, on a scratch build in the real
  `LocalJacBuilder`/`OMPJacBuilder` path, against the PRD §9 10 % slowdown rule. (2) Restate the exit question from
  the result: if it reaches bitwise, the primary gate is reachable without §9(a). (3) Reframe C2 as "column-to-column
  history in the serial loop (stale threadprivate values read outside the recomputed range), triggered by
  local-vs-full rounding differences (FMA/vectorisation, inferred)". The fix list then contains both "remove the
  trigger" (changes serial) and "reproduce the history" (serial unchanged). If the experiment fails, record why.

### MAJOR

**I1-M1. Option B is presented as the PRD §11 fallback gate, but it does not meet §11. And a determinism lever that
the RCA's own data shows is misreported and not offered.**
- *Location:* §Exit decision, row "B. **Fallback gate** (PRD §11)"; §Residual table, row "one contiguous chunk per
  thread … Varies run to run: yes".
- *What is wrong:* (a) PRD §11's fallback gate requires "**Bitwise reproducibility across fresh sessions at each
  thread count**" *and* agreement within a tolerance, "for example … on `fnrm`". B's own cost column says "no
  run-to-run determinism". Its tolerance (the AIUE-56 C1 gate) covers only one-evaluation Jacobians. The AIUE-56 plan
  makes the `--itermx 3` runs report-only, so B sets no bound on the ≥3-iteration `fnrm` sequence that §11's MVP
  definition is about. B is therefore a *relaxation* of the §11 fallback. Relaxing it is the owner's call, and the
  RCA has to say plainly that it is one. As written, the owner could adopt B believing it is the pre-agreed
  fallback. (b) In the scratch data behind the static-chunk row (`m2/tebox_static.txt`), all three runs have the
  same 2 mismatches, and run0 vs run1 and run0 vs run2 are **AGREE**. So on the evidence shown, the static
  partition is run-to-run deterministic. That is what §11's first bullet needs, and it follows from the mechanism: a
  fixed column-to-thread mapping gives fixed worker start states. The table says the opposite ("0–2", "yes").
- *Acceptance:* Label B as a relaxation of §11 and list exactly which §11 bullets it drops. Give B a multi-iteration
  `fnrm` criterion, or state that it has none. Correct the static-chunk row from the data, or cite the run that
  showed variation. Add "static partition (`OMPJacNchunks=-1`, `OMPAutoBalance=0`) + tolerance" as an option that
  may satisfy §11 as written, with its measured determinism on Te box and full problem and its cost.

**I1-M2. The exit decision is not given per configuration and per arm, as decision 9 and PRD §7.4 require.**
- *Location:* §Exit decision.
- *What is wrong:* Decision 9 and §7.4/§11 are per configuration: "the owner chooses the fallback gate (§11) for the
  configurations where it isn't [reachable]". The RCA gives a single global answer. After C1, the available data
  are: `ti`, `ni`, `up`, `ng` bitwise on the jac arm at 4 threads (AIUE-56 validation, `new_*_t4_k5`: 5/5); `tebox`,
  `full`, `te`, `te_phi` with M2 residuals (worst 5.6e-10, 4.6e-9, 4.6e-9, 7.15e-9); 2 and 8 threads only for tebox
  and full. Option A has evidence only for tebox and full, jac arm, 4 threads, 3 runs each. Nothing shows that A
  keeps `ti`/`ni`/`up`/`ng` bitwise (§9: "must keep doing so"), or that it helps `te`/`te_phi` or the jacrhs arm. The
  "every configuration" question therefore has no answer for most of the matrix.
- *Acceptance:* Add a table with configuration × thread count × arm, the post-C1 status, and which options are
  shown (not expected) to reach bitwise. Mark each untested cell as such.

### MINOR

**I1-m1. The P3-m3 "history outside the loop" test is described inaccurately and cannot detect much.** In
`p3m3/hist.py`, mode `history` runs `exmain()`, then 40 local `pandf` calls at **perturbed** `y2`, then a full
`pandf(-1,-1)`, then `exmain()` again. It is bitwise equal to `twice`, not to `fresh` (I checked the saved `J.npz`:
history==twice True, history==fresh False, for both Te box and full). The trailing full `pandf` overwrites every
work array, so this test could not show history even if history mattered. The literal P3-m3 check (permute the
column order) was not run. The conclusion (serial depends on history inside the loop) is still right, from the
emulation. Acceptance: describe the experiment as run ("after a first `exmain`; compared with a second `exmain`") and
say what it can and cannot detect.

**I1-m2. "Round-off level" understates option A's serial change.** Te box: fnrm changes by 3.4e-9 relative (about
1.5e7 ulp). All 25 `yldot`, all 25 `sfscal`, 1 `suscal` and 149 of 169 Jacobian values change (my compare). That is
round-off amplified by cancellation in the Te residual. Say so, and give relative sizes. Also, "pytests `rtol=1e-5`
unaffected" was not measured. The pytests also compare `fnrm` with `rtol=epsilon=1e-5`
(`pytests/fulltests/*/test_*.py:71,77`), and near convergence `fnrm` is sensitive to round-off. Mark it as
expected, not shown.

**I1-m3. C2's mechanism is stated as fact in §Root causes but is only inferred.** The FMA/vectorisation explanation
(why a 2–3-cell loop rounds differently from the full row) is an inference: the assembly was not inspected, which
the text admits further down. The table row should carry the same caveat. "Reproduces exactly the OpenMP residual"
is also stronger than the emulation output shows: it matches the count and the row. If values were compared with
an OpenMP run, cite that comparison.

**I1-m4. Hazards from the reviewed AIUE-50 record have no ticket.** (a) The `emcoef` `copyin` pointer
re-association (reviewed F15 / AIUE-50 I1-m5: a formal write race from the second Jacobian on) is not in the races
row or in AIUE-60. AIUE-56 was asked to decide it, so record the outcome. (b) The `fmombal` SAVE arrays (F9/F10): H3
calls them "a hazard, not exercised by the Te error". In fact `fmombal` is called only from `mombal`
(`bbb/pandf_plasma_momentum.m:1018`), and `mombal` is used only for `isimpon=5`. `isimpon` 6/7 call `mombalni`
(`:667-675`, `:700-706`), so the reproducer never runs it. The AIUE-50 F9 text ("isimpon 6/7") is wrong on this
point. Assign the latent race to AIUE-60 or a note.

**I1-m5. Small reference fixes.** `jac_calc` is `bbb/oderhs.m:1012-1241` (the column loop starts at `:1095`); the
cited `:1100-1226` is inside the loop. After the rebase onto the reviewed AIUE-50 (`86ec027`), recheck that the
AIUE-50 section below no longer says `readpost`/`:102-108` and that the two sections agree (F15 `emcoef`, the M2
counts "0 and 472 … 1217").

**I1-m6. B's tolerance is a margin, not a derivation.** 1e-6 × row max is about 50 × eps/del (2.2e-8) and about 140 ×
the worst observed post-C1 deviation (7.15e-9, `te_phi`). P3-m4 also allows "the serial spread under a benign
history change". That spread is now measurable directly with the emulation (`chunksK`/`fresh` vs `serial`), and is
≤ 5.6e-10 on the Te box. Show both numbers, so the owner can see how much tighter the bound could be and what size
of real defect 1e-6 would let through.

## Status of previous findings

Round 1: none.

## What was checked and how

All runs on macOS arm64. Fresh `python -I` processes, empty `HOME`, `OMP_STACKSIZE=512M` (harness default). Outputs
are under `/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev55/`.

1. **Scratch tree contents.** `AIUE-50-scratch` at `14abb0d` = `0fac655` + `de2d327` (threadprivate checker, gated by
   `OMPJacDebug.eq.-7`, so inert by default) + `c9d2872` (scalar-before-array swap) + `14abb0d`
   (`-ffp-contract=off` in `FARGS`). The `direct_url.json` files confirm that `venvs/AIUE-50-nofma` (built 02:29)
   and `venvs/AIUE-50-swap` (built 00:43, before `14abb0d`) were both built from this tree. The nofma build
   therefore also contains the swap and the (inert) checker, as the RCA says.
2. **(1) nofma Te box, OpenMP vs its own serial.** `cli.py check --preset tebox --arm jac --threads 4 --repeats 3
   --python venvs/AIUE-50-nofma/bin/python`: **AGREE** in all quantities, and determinism AGREE (run0 vs run1, run0
   vs run2). Reproduced.
3. **(2) nofma serial vs default serial.** `cli.py run --arm serial` on `base-serial`, then `compare` against the
   nofma serial reference: MISMATCH. 149 Jacobian values; sfscal 25; suscal 1; yldot 25; fnrm
   `0x1.49db83f93d961p-2` (0.3221264477609989) vs `0x1.49db840c19087p-2` (0.3221264488586332). Reproduced. Control:
   `AIUE-50-swap` serial vs `base-serial`: AGREE (the swap does not touch serial).
4. **(3) Serial-history claims.** The author's emulation, re-run on `base-serial`: `serial` = `exmain` bitwise (Te
   box 0 mismatches; full problem 0 mismatches, a new result). `chunks4`/`fresh` give 2 mismatches in te(4,20),
   reproduced. `chunks8` on the full problem gives 1971 mismatches in 28 Te rows. P3-m3 `J.npz`: history==twice,
   history≠fresh, twice≠fresh (Te box and full).
5. **Replay experiment (I1-B1).** `rev55/emul_replay.py` (author's `emul.py` + a `_rR` mode; diff in
   `rev55/emul_replay.diff`). Te-box and full-problem results in the I1-B1 tables (full problem: one process,
   4 modes, 418 s; log `rev55/emul_full.log`). This is an emulation in Python around `bbb.pandf` on one thread, not
   the threaded code path. The author's own `chunksK` emulation already reproduces the threaded residual, which
   makes it the right model.
6. **Code references verified:** `ppp/omp_parallel.F90:681-693` (arrays before scalars); `api/api.v:145-172`
   (Imslwrk, DATA /1/ and /4/); `api/apip93.m:101-107` (`splinem` sets the bounds, `gallot`);
   `bbb/odesetup.m:1130,1150` (`splinem` after `readpost`, isimpon 2 and 7); `emissbs` `w=10**vlogw`
   (`api/apip93.m:217-220`, so 1.0 when B3VAL returns 0); `bbb/pandf_plasma_energy.m:613-619` (vsoreec), `:640-645`
   (vsoree = vsoreec for iseesorave=0), `:819-824` (isimpon=7 emissbs), `:1114-1118` (resee −cnimp·pwrze);
   `OMPPandf1Rhs` `ppp/omp_parallel.F90:902-996` calls no `OmpCopy*` (it only `USE`s the module);
   `ppp/parallel.F90:318-323` (extra `isjacreset` pandf); `bbb/bbb.v:951` (`areapl` `+work`, not threadprivate);
   clip `sfscal(iv)` (`ppp/parallel.F90:292`) vs `sfscal(ii)` (`bbb/oderhs.m:1187`); `del`/`delperturb` both 1e-8
   (`bbb/bbb.v:3301-3302`); `fmombal` only from `mombal` (`bbb/pandf_plasma_momentum.m:1018`).
7. **PRD and decisions.** §7.4, §9 ("resets" in scope without escalation; (a)/(b)), §11 fallback bullets, Appendix
   decisions 4, 7, 8, 9.
8. **AIUE-56 records.** `docs/reviews/AIUE-56-c1-gate.py` (bounds: Te-row max|J| ≤ 10×; every mismatch ≤ 1e-6 × serial
   row max; one evaluation only); `AIUE-56-validation.txt` (worst 5.62e-10/4.59e-9/4.61e-9/7.15e-9; ti/ni/up/ng 5/5
   bitwise). jacrhs arm after the swap: `yldot`, `fnrm` and `yldot_probe` equal to serial in all Te-box and full runs;
   only M2 Jacobian entries differ (`v56/new_*_rhs_t4_k5.txt`). This supports the C1-RHS row.
9. `uv run .claude/hooks/check_context_refs.py --changed e4f738c`: OK. The branch touches only artifact paths
   (`.claude/plans/**`, `docs/rca/**`), which `branching.md:13` allows.

**Not independently verified (environment):** that x86-64 gfortran `-O3` without `-march` emits no FMA, so M2 might
not occur on the Linux CI runner (no Linux/x86-64 here); the A′ per-file variant; the speed cost of
`-ffp-contract=off`; that AIUE-60 and AIUE-61 exist in Jira (no Jira access from this review); full-problem nofma
3/3 runs (not re-run, within the run budget).
