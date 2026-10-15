# AIUE-8 PRD review, round 3

PRD: `docs/prds/AIUE-8-investigate-non-deterministic-openmp-jacobian.md` (revised local copy, branch
`feature/v9-AIUE-8-planning` at `v9-develop` tip `0fac655`).
Previous reviews: `docs/reviews/AIUE-8-prd-round1.md`, `docs/reviews/AIUE-8-prd-round2.md`. Author responses:
`docs/reviews/AIUE-8-prd-round1-response.md`, `docs/reviews/AIUE-8-prd-round2-response.md`.
Reviewer: `uedge-reviewer`, stage `prd`, round 3, 2026-10-14.

## Verdict

**APPROVE**: 0 BLOCKER, 0 MAJOR, 4 MINOR.

## Summary

The revision resolves the one open round-2 MAJOR (P2-M1). The 1-thread evidence now says only what it shows. The RHS
structural differences are listed. §4, §9 and R2 now agree: OpenMP-only code changes are in scope, and escalation covers
both "serial would move" and "bitwise unreachable". The owner has confirmed A1 and A2 (decisions 7 and 9), and the PRD
reflects both, together with the two-track split (decision 8). All seven round-2 MINORs are resolved. The code facts I
re-checked are accurate, with one exception that came from my own round-2 wording (P3-m1). The four remaining MINORs
tighten requirements that tickets will inherit. None of them blocks publication.

## Findings

### BLOCKER

None.

### MAJOR

None.

### MINOR

**P3-m1: What `bbb.jac` holds after `exmain` depends on whether `psetnk` ran, and "the Jacobian" is ambiguous over a
multi-iteration run.** *§6.1 "What `bbb.jac` holds after `exmain`", §7.2 item 1, §11 MVP "Requirement".*
- **The §6.1 statement is not always true.** It came from my round-2 P2-m4, and I did not qualify it then.
  - With `ftol=1e20`, `nksol` stops in `nkstp0` right after the iteration-0 `fnrm` (`svr/nksol.m`, the `call f` →
    `vnormnk` → `nkstp0` → `go to 500` sequence just before `iter = iter + 1`). It never reaches `model`/`pset`.
  - So `bbb.jac` holds the `sfsetnk` Jacobian. It is column-scaled by `1/su` (`bbb/oderhs.m:2337-2342`), but it is
    **not** row-scaled by `sf`, row-normalised or RCM-permuted. Those steps happen only in `psetnk`
    (`bbb/oderhs.m:1955-1963`, `jac_reorder` at `:1308`, `ireorder`/`premeth` test at `:1402`).
  - This is good news for §6.3, because the planning comparisons used `ftol=1e20`, so the RCM permutation did not
    contaminate them. The §6.1 text should still say "after a `psetnk` call".
- **Several Jacobians per run.** A run with ≥ 3 iterations evaluates at least two Jacobians:
  - the `sfsetnk` one, without `nufak`;
  - one per `psetnk` call (`yl(neq+1)=1`, so `nufak` is included; `incpset=5`, `bbb/bbb.v:1233`).
  §7.2 item 1 and §11 say "the Jacobian". The post-`exmain` alternative captures only the last `psetnk` Jacobian, and
  in scaled form.
- **No Python entry point.** `jac_calc` is not Python-callable (only `ffun` is exposed near there, `bbb/bbb.v:3397`).
  The "as it comes out of `jac_calc`" capture therefore needs an off-by-default hook (§7.5).

*Fix:* qualify the §6.1 bullet. In §7.2 item 1, say which Jacobian evaluations are compared: every evaluation in the
run, or at least the `sfsetnk` one and each `psetnk` one. Note that the raw capture uses a §7.5 diagnostic hook.

**P3-m2: The "±0 differ" rule will flag a sign-of-zero flip that the RHS reduction is known to produce.** *§7.2 item 2
vs §6.1 "each `yldot` index is summed … exact when ownership is disjoint", §6.4 R-H.*
- In `OMPPandf1Rhs`, each private `yldottot` starts at `+0.0` (`REDUCTION(+:yldottot)`). The owned entry is formed as
  `yldottot(iv) + yldotcopy(iv)` (`ppp/omp_parallel.F90:947-975`).
- Under round-to-nearest, `+0.0 + (−0.0) = +0.0`. So every `−0.0` in serial `yldot` comes back as `+0.0` on the RHS
  arm.
- The value is exact, but under §7.2's definition the comparison fails. The Jacobian arm is not affected: zero entries
  are never stored (`jaccliplim=0`, `bbb/bbb.v:3308`; test `abs(jacelem*sfscal) > jaccliplim`), and `sfscal` and
  `fnrm` are nonzero.
- Nobody has checked whether serial `yldot` actually holds `−0.0` entries in this deck. If it does, the RHS track
  starts with a false failure.

*Fix:* state the treatment for `yldot` on the RHS arm: either treat ±0 as equal there, or require the RCA to classify
sign-only differences separately. Alternatively, keep the strict rule and list this mechanism under R-H as a known
source.

**P3-m3: The serial history-independence experiment from P2-M1(d) was not carried into Phase 2.** *§12 Phase 2,
§7.4.*
- P2-M1(d) asked for one experiment showing whether the serial Jacobian is history-independent for Te: for example,
  serial `jac_calc` with a different column order, or with an extra unrelated local evaluation between columns, giving
  the same Jacobian bitwise.
- The response covers the exit decision, but not this experiment, and the PRD has no equivalent (H1 is phrased for
  per-thread state only).
- It is the most direct input to the Phase 2 exit question. If serial Te is history-dependent, N-thread bitwise
  equality needs serial's history, and the answer is "unreachable" whatever the fix. The §7.5 "deterministic
  amplifier" is the OpenMP-side counterpart, but it is optional.

*Fix:* add one Phase 2 bullet requiring this experiment, with its result recorded in the RCA before the exit decision.

**P3-m4: Two success-criteria details.** *§11 "Fallback gate", §11 "Before the fix".*
- **The fallback tolerance example is circular.** "set from the observed spread of the configurations that are
  bitwise" gives zero, because bitwise configurations have zero spread against serial. A usable basis is the
  finite-difference noise level (`del=delperturb=1e-8`, `bbb/bbb.v:3301-3302`, so relative noise ≈ ε/δ ≈ 10⁻⁸ in each
  entry), or the spread of serial Jacobians under a benign change of evaluation history (see P3-m3).
- **No thread count on the pre-fix rates.** "full problem disagrees in 20/20" and "Te box non-deterministic in ≥ 19/20"
  do not name a thread count. Planning used 4 (and 8 for the full problem).

*Fix:* replace the example basis, and add "at 4 threads" (or the intended count) to the pre-fix criteria.

## Status of previous findings

| Finding | Status | Evidence |
|---|---|---|
| P2-M1 bitwise gate argued from insufficient evidence; RHS differences missing; §4/§9/R2 contradict; A2 unconfirmed | **Resolved** (sub-item (d) partly, see P3-m3) | (a) The §6.3 1-thread row now says it "reproduces serial's history and does **not** show that N threads can match serial". The Ti/ni/up/ng row is limited to "these equations on this arm only". (b) §6.1 lists the RHS differences: chunks and core rings (`:64-84`), `auxrange` (`:1015-1030`), edge-only `bouncon` (`:1093-1105`), no master refresh, disjoint `REDUCTION` (`:950-982`), and the non-local core BCs. All re-checked. (c) §4 now excludes only *default values* of chunking switches. §9 adds escalation (b), "bitwise unreachable", and R2 points to §9(b). The three are consistent. (d) The Phase 2 exit decision is in §7.4, §9 and §12, but the serial history experiment is missing (P3-m3). (e) A2 is confirmed as decision 9, and the fallback gate is predefined in §11. |
| P2-m1 conclusions beyond data | **Resolved** | The `OMPJacNchunks=-1` row notes `schedule(dynamic)`. The race reading is softened, and H6 is added. The full-problem row carries the max-norm caveat and says Jacobian stability was not checked. The H1 status is corrected, and H5 is dropped with the reason (disjoint ownership). |
| P2-m2 L1 wrong at defaults | **Resolved** | L1 is now the `isimpon=7` Te radiation sink. The deck sets `isimpon=7`, `afracs=1.5e-2` after the populate `exmain` (owner's `input_mod4.py:294-295`, read only). |
| P2-m3 `ijactot` sentence and deck description | **Resolved** | §6.1 matches `bbb/odesetup.m:6799`, `bbb/oderhs.m:2327-2333` and `bbb/pandf.m:19-21` (`PandfRHS_interface` → `OMPPandf1Rhs` when `ParallelPandf1>0`). `mfdif = 2 - mdif` with `mdif=0` (`svr/nksol.m:865`, `bbb/bbb.v:1213`) is correct. The §6.2 deck row matches `input_mod4.py:277-338`. A per-evaluation branch check is in §7.2 item 1. |
| P2-m4 capture point, bitwise definition, repeat counts | **Resolved**, with a follow-up (P3-m1, P3-m2) | The capture point is named and the RCM/scaling facts are added. Bitwise is defined. The repeat counts are stated once, in §11 (30/30 at 4 threads; 5/5 at 2 and 8 threads and for the other configurations), and §7.2 item 3 points there. |
| P2-m5 run environment | **Resolved** | Rate files (A5, §7.1), `mist.dat` from the working directory, a prepared run directory, `python -I` with an explicit `sys.path`, and explicit commit / do-not-commit lists (checked against the owner's directory listing). |
| P2-m6 CI cost basis | **Resolved** | §6.3 labels 12 s as "iteration 0 only". §7.6 states the real cost basis, measures it in Phase 4, and has a nightly fallback (R5). |
| P2-m7 AI-layer fact, AIUE-9 follow-up | **Resolved (tracked)** | `CLAUDE.md` line 38 (verified: "Regression tests live on a separate branch … not in this repo") and both `testing.md` sentences (lines 3 and 48, verified) are on the code-facts list. §13 records the AIUE-9 mirroring as an owner action with line numbers. The AIUE-9 PRD is still unchanged at lines 191, 662 and 697 (grepped), which is expected, because that change belongs on its own branch. |

## Checking against the binding decisions

| Decision | How the PRD handles it |
|---|---|
| 1 | Investigate, fix, test and the OpenMP CI job are in scope (§4, §7.6, Phases 1-4). The CI job runs the §7.2 flow, which includes fresh-session repeats. |
| 2 | Reproduced faithfully (§1, Appendix 2). |
| 3 | Subsumed by the decision-9 gate, and kept explicitly in the fallback ("bitwise reproducibility across fresh sessions"). |
| 4, 7 | §2 principle 1 and §9 apply to both builds. No default switch value changes. OpenMP changes are allowed only towards serial. Quantities already equal to serial stay equal. Everything else escalates (§9(a)/(b)). §7.3 implements the check. |
| 5 | The case is described accurately (§6.2). The commit list is explicit (§7.1). |
| 6 | Respected. §7 states requirements and §11 sets acceptance, while the harness, the RCA and the fixes are left to tickets. My MINORs ask only for clearer requirements. |
| 8 | Separate tracks run through §1, §4, §7.4, §7.6 (the RHS arm reports but does not gate), §11 and Phase 5, which depends on Phase 3. |
| 9 | The primary gate in §1 and §11 is bitwise agreement with serial plus fresh-session reproducibility. The Phase 2 exit decision and the predefined fallback are in §7.4, §9 and §11. |

## What was checked and how

- **Documents read in full.** The revised PRD, the round-2 report and both responses. All 15 sections required by
  `.claude/skills/create-prd/SKILL.md` are present. The Assumptions section (A3-A5) remains, and A1/A2 are now
  decisions.
- **Code facts re-verified in the worktree (`0fac655`):**
  - `ppp/omp_parallel.F90`: routine locations (`InitOMPJac` 281, `jac_calc_omp` 495, `OMPJacBuilder` 645,
    `OMPPandf1Rhs` 902-996, `OMPPandf` 999, `OMPPandf_XPT` 1132); the RHS reduction at 940-995.
  - `ppp/parallel.F90`: 1-45 (switch mapping, `OMPParallelPandf1` forcing `OMPParallelJac`), 45/156, 159-345
    (`LocalJacBuilder` loop: clipping, perturbation, diagonal terms, reset call).
  - `bbb/oderhs.m`:
    - 1140-1240 (serial column loop);
    - 1290-1312, 1370-1430 and 1438-1470 (reorder and row normalisation);
    - 1935-1970 (`psetnk`), 2320-2360 (`sfsetnk`);
    - 4670-4704 (`jac_calc_interface`).
  - Other `bbb` sources:
    - `bbb/pandf.m` 10-30;
    - `bbb/odesolve.m` 255-300;
    - `bbb/odesetup.m` 6720-6800 (OpenMP roadblocks, `ijactot` reset).
  - `bbb/bbb.v`: 1213, 1233, 1284, 2263-2265, 2975, 2994, 3301-3308, 3397, 4129-4130. `ppp/ppp.v`: 6-7.
  - `svr/nksol.m`: 857-865 and the iteration-0 path (`call f`, `vnormnk`, `nkstp0`, before `model`/`pset`),
    1085-1100.
  - `setup.py`: 205-216 and 726-740.
  - OpenMP directives in the repo: `c!omp`/`!$omp` occur only in `bbb/oderhs.m`, `bbb/odesetup.m`, `bbb/pandf.m` and
    `ppp/omp_parallel.F90`. The only parallel regions are in `ppp/`.
- **Defaults relevant to the structural differences.** `jaccliplim=0`, `del=delperturb=1e-8` and `svrpkg='nksol'` make
  the clipping, perturbation and diagonal differences listed in §6.1 inert at defaults. This supports the PRD's choice
  to leave them alone unless the RCA implicates them.
- **AI-layer statements.** `CLAUDE.md:38` and `.claude/context/testing.md:3,48`.
- **AIUE-9 PRD.** Grepped `../AIUE-9-planning/docs/prds/AIUE-9-create-end-to-end-test-suite.md` for `omp_check`,
  "randomness" and AIUE-8. It is unchanged, as expected.
- **Owner's reproducer, read only.** The directory listing, `input_mod4.py` (grep plus lines 270-345),
  `testscript.py`, `testscript2.py` and `comp.sh`. Nothing was run or written there.
- **CI runner.** The GitHub API reports `holm10/UEDGE_v9_dev` as public, so `ubuntu-latest` has 4 vCPU, as §7.6
  states.
- **Not checked.** As instructed, I did not reproduce the §6.3 measurements. No builds or tests were run.
