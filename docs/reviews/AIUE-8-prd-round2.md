# AIUE-8 PRD review, round 2

PRD: `docs/prds/AIUE-8-investigate-non-deterministic-openmp-jacobian.md` (revised local copy, branch
`feature/v9-AIUE-8-planning` at `v9-develop` tip `0fac655`).
Previous review: `docs/reviews/AIUE-8-prd-round1.md`. Author response: `docs/reviews/AIUE-8-prd-round1-response.md`.
Reviewer: `uedge-reviewer`, stage `prd`, round 2, 2026-10-14.

## Verdict

**REVISE**: 0 BLOCKER, 1 MAJOR, 7 MINOR.

## Summary

The revision is a large improvement. All seven round-1 MAJORs are resolved in substance. The OpenMP RHS is now
treated as a suspect in its own right. The `fnrm`/`sfscal` mechanism is documented correctly. A serial old-vs-new
bitwise check exists. CI detection no longer depends on chance. The skill edit is out of scope. The AIUE-9 split is
stated. Almost every code fact I re-checked is accurate.

One MAJOR remains, and it is new. Bitwise agreement with serial (A2) is now the primary gate and the basis for the CI
design. The PRD argues that this is achievable from evidence that cannot show it. It does not list the RHS-path
structural differences. Its scope rule (§4) and its escalation rule (§9, R2) contradict each other in exactly the case
the planning data points at. The MINORs cover planning inferences that go too far, a wrong lead (L1, which I introduced
in round 1 and withdraw here), the Jacobian capture point and the meaning of "bitwise", the run environment, and the
CI cost basis. Every finding can be fixed in the text. The approach is sound.

## Findings

### MAJOR

**P2-M1: The bitwise-with-serial gate is argued from evidence that cannot show it, the RHS-path structural
differences are missing, and §4, §9 and R2 contradict each other.**
*Sections: §2 principle 2, §4 Out of scope, §6.1, §9 "Escalation rule", R2, Appendix A2, Phase 3 estimate.*

1. **The feasibility argument is not valid.** §2 says "The 1-thread OpenMP path already meets it", and R2 says
   "Planning evidence says bitwise is achievable: 1-thread OpenMP equals serial". With one thread and
   `NchunksJac=neq` (`ppp/omp_parallel.F90:313`), the dynamic loop (`:712-715`) gives the single thread columns
   1..neq in order. It starts from the master's full evaluation (`:680`). That is the same history as `jac_calc`,
   which restores each box with a `pandf` call after every column (`bbb/oderhs.m:1215-1216`). So the 1-thread result
   shows that the OpenMP code path reproduces serial *when it has serial's history*. It says nothing about N threads,
   where each thread has a different history. The 4-thread Ti/ni/up/ng isolations are real evidence, but only for
   those equations and only on the Jacobian-only arm. There is no evidence yet for Te, or for the RHS arm.
2. **§6.1 lists the structural differences only for the Jacobian.** The RHS path differs from serial `pandf` too:
   - `OMPPandf1Rhs` evaluates subdomain chunks (`rangechunk`, built in `InitOMPPandf1`). These include dedicated
     iy=0..1 chunks around the core ring (`ppp/omp_parallel.F90:64-84`).
   - `OMPPandf` widens `convsr_aux2` to whole flux tubes through `auxrange`, with "TODO: Figure out why this is
     needed??" (`:1015-1030`).
   - `bouncon` is called only for chunks that touch a domain edge, with a second TODO about `ixrb` (`:1093-1105`).
   - Each chunk runs on per-thread state, and nothing re-copies the master state before the RHS loop.

   Bitwise RHS agreement requires that every owned `yldot` entry from a subdomain evaluation equals the full
   evaluation. The deck uses non-local boundary conditions: a ring sum for `iflcore=1` (`bbb/pandf_boundary.m:1744-1763`)
   and for `isnicore=3` (`:1483-1500`). Whether they come out exact depends on that decomposition. Planning saw about
   2200 wrong Te rows on this arm.
3. **The scope and escalation rules contradict each other.** Suppose bitwise RHS agreement needs an OpenMP-only,
   serial-neutral change to the chunk decomposition, the state refresh or the boundary handling in `OMPPandf1Rhs`.
   - §4 puts "changing its chunking or load-balancing defaults" out of scope. Its "unless the RCA shows…" exception
     covers only the `jac_calc`/`LocalJacBuilder` differences.
   - §9 escalates only when the fix would move serial results, so under §9 such a change is neither escalated nor
     forbidden.
   - R2 says that a structural difference, or H5, should "Escalate under §9". §9's text does not cover that case.

   A ticket author cannot tell whether to do the work, skip it, or escalate. The Phase 3 estimate (≈ 1 week) assumes
   the easy case.
4. **A2 is the primary acceptance gate and drives the CI design, but it is not flagged for owner confirmation.** Only
   A1 is. A2 turns decision 3 (reproducibility) into a correctness target, which can force escalations that decision
   3 alone would not.

**Resolve by:**
- (a) Restating the feasibility evidence so it says only what it shows. For example: "1-thread equality shows the
  OpenMP code path reproduces serial given serial's column order; N-thread equality is shown so far only for the
  Ti/ni/up/ng isolations on the Jacobian-only arm."
- (b) Listing the RHS-path structural differences in §6.1, and stating whether changing them (decomposition,
  per-chunk state refresh, `bouncon` handling) is in scope.
- (c) Aligning §9 and R2. Escalate whenever bitwise agreement on a tested configuration cannot be reached by in-scope
  changes, whether or not serial would move.
- (d) Making "is bitwise reachable on every configuration and arm?" an explicit Phase 1/2 exit question, decided with
  the owner before Phase 3. The per-equation, both-arm characterisation in §7.2.3 already supplies most of the data.
  Add one experiment that shows whether the serial Jacobian is history-independent for Te.
- (e) Adding A2 to the owner-confirmation list, together with the fallback gate if the owner relaxes it: either
  determinism-only per §7.2 item 2, or a per-configuration tolerance per R2.

### MINOR

**P2-m1: Some planning conclusions go further than the data.** *§1 "It is a thread race", §6.3 rows "truly static"
and "Full problem … deterministic, but wrong", §6.4 H1/H2/H5 status.*
- **"Truly static" is not static.** `OMPJacNchunks=-1` gives `NchunksJac=Nthreads`, but the loop stays
  `schedule(dynamic,OMPLoopJacNchunk)` (`ppp/omp_parallel.F90:712`). One thread can take two chunks, so per-thread
  history is not excluded.
- **The 1-thread vs N-thread contrast has other explanations.** It also separates state that only reaches workers
  through `OmpCopy*` (only `bbb`/`com`/`api` are copied, `:681-692`) from uninitialised automatic arrays on worker
  stacks (L2). Te entries near 2.6·10⁴³ are a typical uninitialised-memory signature. "A data race is at least one
  cause" should be stated as the leading hypothesis, not as a finding.
- **"Deterministic, but wrong" rests on 7 equal `fnrm` values.** With `normtype=0` (`bbb/bbb.v:3293`), `sfscal` uses
  the row max-norm (`svr/svrut4.m:1034-1036`). Equal `fnrm` therefore shows only that each row's largest entry is
  stable, not that the Jacobian is.
- **The H1 status is backwards.** Under `schedule(dynamic)` with one column per chunk, H1 predicts variation from run
  to run, so H1 "may explain why the full-problem Jacobian is stable but wrong" does not hold.
- **H5 is unlikely.** `OMPPandf1Rhs` combines chunks with `REDUCTION(+:yldottot)`, and each index is owned by one
  chunk (`:950-982`). Each entry is therefore v + 0 + … + 0, which is exact in any order (only the sign of zero can
  change). H5 is unlikely to explain 15th-digit `fnrm` differences, and R2 should not cite it as an expected reason
  for tolerances.

*Fix:* soften the §1 and §6.3 wording. Have Phase 1 compare full Jacobians bitwise across repeats before labelling a
configuration deterministic. Correct the H1 and H5 status entries.

**P2-m2: L1 is wrong at default settings (reviewer's own round-1 error, withdrawn).** *§6.4 L1, R1 example.*
- For Jacobian calls, `initialize_ranges` collapses `ixs1:ixf6`, `iys1:iyf6`, `ixs:ixf` and `iys:iyf` to the single
  cell `(xc,yc)` (`bbb/pandf.m:171-188`). The exception is `xrinc` or `yinc` ≥ 20, while the defaults are 1 and 2
  (`bbb/bbb.v:1111-1113`).
- So `erlizold`, `erlrcold`, `eeliold`, `pradold` and `pwrebkgold` (`bbb/pandf_plasma_energy.m:574-575,597,771,909`)
  are captured at `(xc,yc)`, which matches `jacobian_reset` (`bbb/pandf_jacobian.m:87-92`).

My P1-m2 claim that "they hold the value at the last cell of the box" was incorrect.

*Fix:* drop L1, or restrict it to `xrinc`/`yinc` ≥ 20, and reword R1's example. Optional lead instead: the Te-only
impurity-radiation sink that this case activates (`isimpon=7` with `ismctab=2`, `pwrzec`;
`bbb/pandf_plasma_energy.m:771-825`; `emissbs` → `B3VAL` with `threadprivate` `api` work arrays). It was not among
the terms switched off in §6.3.

**P2-m3: The `ijactot` sentence and the deck description are inaccurate.** *§6.3 "Jacobian + RHS" row, §6.2
`input_mod4.py` row.*
- "after `ijactot>0`, which the deck's initial `exmain` causes" is wrong. `exmain` with `icntnunk=0` resets
  `ijactot=0` (`bbb/odesetup.m:6799`).
- In the test's own `exmain`, `sfsetnk` first evaluates `yldot0` with the serial RHS (`bbb/oderhs.m:2327`). It then
  builds the Jacobian (`:2333`), which sets `ijactot=1` (`ppp/omp_parallel.F90:581`). So in the RHS arm, `nksol`'s
  iteration-0 `f(u0)` already goes through the parallel RHS.
- The deck restores `save_input_mod4.h5` *after* the populate `exmain`, and it resets `ftol=1e-8`.
  `testscript2.py`'s `itermx=3` depends on that reset.

*Fix:* correct both texts, and require the "parallel branch actually ran" check for each measured evaluation.

**P2-m4: The comparison points and tolerances in the test logic are underspecified.** *§7.2 items 1, 2 and 4; §11.*
- **Capture point.** After `exmain`, `bbb.jac`/`jacj`/`jaci` are not the raw finite-difference Jacobian:
  - they are column-scaled by 1/`suscal` (`bbb/oderhs.m:2342`, `:1955`);
  - they are row-normalised in `psetnk` (`:1963`);
  - they are permuted in place by reverse Cuthill-McKee when `ireorder=1`, the default (`bbb/bbb.v:2975`;
    `bbb/oderhs.m:1308`, `:1402-1427`). That permutation depends on the sparsity pattern.

  The PRD must name the capture point. Localisation through `igyl`/`idx*` needs the unpermuted Jacobian or the
  inverse permutation.
- **"Bitwise".** Define it as byte equality or value equality, and say how signed zeros and NaNs are treated.
- **Repeat counts.** §7.2 item 2 says K ≥ 20 for acceptance, but §11 says 30/30. The 30/30 applies only at 4 threads,
  and K at 2 and 8 threads is not stated.

**P2-m5: The run environment for the case is incomplete.** *§6.6, §7.1, §6.3 "Environment facts".*
- **Rate files.** The deck needs three:
  - `ehr2.dat` (`istabon=10`, `aph/aphread.m:75-80`, from `aphdir`);
  - `C_rates.adas` (`ismctab=2`, `readmc`, `apidir`);
  - `mist.dat` (`isimpon=7` → `readpost(coronalimpfname)`, default `'mist.dat'`, `com/com.v:322`,
    `bbb/odesetup.m:1150`). It is opened relative to the working directory (`api/apip93.m:18-20`). So §7.1's
    "check whether `mist.dat` is needed" has the answer yes.
- **No rate bundle in the repo.** "The bundled rates" do not exist. The only copies are under
  `builder/test/Forthon_cases/Forthon_case5/`, with `C_rates.adas` at 437 KB and `ehr2.dat` at 97 KB.
- **Working-directory paths.** All the deck's data paths are relative to the working directory: `gridue.hdf5`,
  `b0p1.hdf5`, `save_input_mod4.h5` and `mist.dat`. The "clean working directory" of §6.6 must therefore be populated.
- **`python -I`.** It implies `-P`, so the script's own directory is not on `sys.path`, and
  `from input_mod4 import *` fails unless the runner handles it.
- **What to commit.** The owner's directory also holds `testjac.hdf5` (6.1 MB), `to_tom/` (duplicate data and a
  `.taz`), a `.swp`, `.DS_Store` and `__pycache__`. Say which of these are committed.
- `comp_jac.sh` overwrites `run1_2.txt` on its third line. This is harmless, but it should not be copied into the test
  flow.

**P2-m6: The CI cost basis does not match the requirements.** *§7.6 "Budget", §7.2.3, §11.*
The 12 s per repeat was measured with `ftol=1e20`, meaning one Jacobian and iteration 0. §7.2.3 and §11 require at
least 3 Newton iterations. That adds more Jacobians, ILUT factorisations with `lfililut=300` and `lenplufac=1000`,
and Krylov products. Every comparison also needs a serial reference run of the same build.

*Fix:* state the cost basis, or allow CI to run the full problem at iteration 0 plus one post-Jacobian RHS while the
≥ 3-iteration runs use the Te box.

**P2-m7: An AI-layer fact and the AIUE-9 follow-up are not tracked.** *§4 Integration, §13.*
- `CLAUDE.md:38` says the regression tests are "not in this repo". That becomes partly stale once
  `tests/deterministic_omp/` lands. Add it to the code-facts update list.
- The AIUE-9 PRD (`feature/v9-AIUE-9-planning`) still says `omp_check.py` replaces `validate` §4 (lines 191 and
  662-667) and still claims the randomness RCA (line 697). The agreement is recorded only in this PRD. Record the
  mirroring as a tracked action, for example a Jira link, or a precondition on the AIUE-9 phase that builds
  `omp_check.py`.

## Status of previous findings

| Finding | Status | Evidence |
|---|---|---|
| P1-M1 OpenMP RHS under-weighted | **Resolved** | "Points first at the Jacobian" is removed. §6.1 documents the `ijactot>0` fallback (`ppp/omp_parallel.F90:949,989-991`, checked) and the `sfsetnk` mechanism (`bbb/oderhs.m:2292-2360`, checked: `rhsnk`, then `jac_calc_interface`, `amudia`, `rnrms`, `sf=1/norm`). §7.2 requires the RHS to be measured after `ijactot>0` with a branch check, both arms, and ≥ 3 iterations. H1 covers RHS chunks. One inaccurate sentence remains (P2-m3). |
| P1-M2 `CheckJac` means bitwise; "same structure" false | **Resolved** | Option (a) is adopted consistently: §4 no longer excludes bitwise, §9/§11 gate on it, and the five structural differences are listed correctly (checked against `ppp/parallel.F90:253,292,320-325` and `bbb/oderhs.m:1156,1187,1220-1222`). The feasibility of this choice is raised as a new issue in P2-M1. |
| P1-M3 "nothing may change" incoherent | **Resolved** | A1 defines serial as both builds, allows OpenMP to change only towards serial, protects OpenMP quantities that already equal serial, and is marked for owner confirmation. This is a faithful reading of decision 4: the defaults are serial (`ppp/ppp.v:6-7`). |
| P1-M4 no runnable serial-bitwise check | **Resolved** | §7.3 defines two venvs, both builds, the reproducer configurations plus ≥ 3 coverage cases, bitwise comparison, exit codes, a mandatory PR artefact, and a Phase 1 self-test. Under decision 6, the tool's design is left to the ticket. |
| P1-M5 statistical CI detection | **Resolved** | The primary check is deterministic against serial. 20/20 failures on the pre-fix code and on the seeded race are measured. 0/30 bounds the residual rate below 1 − 0.05^(1/30) ≈ 9.5 % at 95 % confidence (arithmetic checked). The determinism-only fallback depends on P2-M1(e). |
| P1-M6 skill edit on a ticket branch | **Resolved** | Story 6 is now documentation only. §4 puts the `validate`/`code-review` edits out of scope, as a later `feature/v9-ai-*` PR. |
| P1-M7 AIUE-9 conflicts | **Resolved in this PRD** | §13 covers the RCA owner, the `Test criteria: changed` rule, a single `validate` §4 tool, and thread pinning. The mirroring is still pending in the AIUE-9 PRD (P2-m7). |
| P1-m1 wrong facts | **Resolved** | `ParallelMatfac` (`bbb/bbb.v:4133`, `bbb/oderhs.m:4656`), `idx*` at `bbb/bbb.v:2002-2008` including `idxtg`, `setup.py:79,82,95`, and the `OMP_NUM_THREADS` wording are all checked. The H2 non-candidates are dropped. |
| P1-m2 missing leads | **Resolved, but L1 withdrawn** | L2 is confirmed (`ppp/parallel.F90:195-196`). L3 is confirmed (`ppp/omp_parallel.F90:734`). L1 was my error (P2-m2). |
| P1-m3 `fnrm` quantity | **Resolved** | Both float64 and the 16 printed digits are compared. |
| P1-m4 thread counts | **Resolved** | 2, 4 and 8 throughout, with 16 non-gating. |
| P1-m5 CI budget / dependencies | **Resolved, but the basis needs fixing** | ≤ 20 min, measured, `h5py` listed. Cost basis is P2-m6. |
| P1-m6 runtimes | **Resolved** | R4 and §8 are corrected. |
| P1-m7 reproducer risk | **Resolved** | The case has arrived, and R5 covers size and speed. |
| P1-m8 diagnostic side effects | **Resolved** | §6.1 and §7.2.6 keep diagnostics out of measured runs, and note that `ForceSerialCheck` cannot serve as a baseline. |

## Checking against the binding decisions

| Decision | How the PRD handles it |
|---|---|
| 1 | Investigate, fix, test and the OpenMP CI job are all in scope (§4, §7.6, Phase 4). |
| 2 | Reproduced faithfully in the Appendix and §1. |
| 3 | Met through A2, which is stricter. A2's coherence is P2-M1(e). |
| 4 | Met through A1, which is coherent (see P1-M3 above). |
| 5 | The case is described accurately (§6.2), apart from P2-m3. |
| 6 | Respected. §7 states requirements, not a harness design, and the phases slice into tickets. My findings ask only for clear, consistent requirements, not for designs. |

## What was checked and how

- **Documents read in full.** The PRD, the round-1 report and the response, all checked against decisions 1-6.
  `.claude/skills/create-prd/SKILL.md` lists the required sections, and all 15 are present.
- **Owner's case, read only.** `input_mod4.py`, `testscript.py`, `testscript1.py`, `testscript2.py`, `comp.sh`,
  `comp_jac.sh`, the directory listing with file sizes, and the head of `run1_2.txt`. Nothing was run and nothing was
  written there.
- **Code facts re-verified in the worktree** (`0fac655`):
  - `ppp/ppp.v`: lines 1-50.
  - `ppp/omp_parallel.F90`:
    - 60-84 (RHS chunk ranges)
    - 290-318
    - 545-585
    - 670-748 (copy, loop, `OMPTimeLocalJac`)
    - 900-1106 (`OMPPandf1Rhs`, `OMPPandf`, `REDUCTION`, `auxrange`, `bouncon` gating)
  - `ppp/parallel.F90`: 28-38, 80-125, 159-327, 345-360.
  - `bbb/oderhs.m`:
    - 1140-1240 (`jac_calc` column loop and restore)
    - 1300-1430 (reorder)
    - 1946-1963 (`psetnk` scaling)
    - 2292-2360 (`sfsetnk`)
    - 4656
  - `bbb/odesolve.m`: 260-300 (`sfsetnk` call sites).
  - `bbb/odesetup.m`: 6790-6800 (`ijactot` reset) and 1136-1165 (rate-table reads).
  - `bbb/pandf.m`: 17-22, 31-200 (`initialize_ranges`, source-range collapse at 171-188), 555-575, 700-715.
  - `bbb/pandf_jacobian.m`: 1-120.
  - `bbb/pandf_plasma_energy.m`: 565-600, 765-850, 900-912.
  - `bbb/pandf_boundary.m`: 1475-1510, 1744-1770.
  - `bbb/bbb.v`: 440-456, 1111-1114, 2000-2010, 2124, 2925-2935, 2975, 3293, 3896-3920.
  - `api/api.v`: 145-172. `api/apip93.m`: 10-30, 198-230. `aph/aphread.m`: 70-90. `com/com.v`: 322.
  - `com/comutil.m`: `B3VAL` and its callees, plus a scan for `SAVE`.
  - `svr/svrut4.m`: 1002-1040. `svr/nksol.m`: 860-868, 1098-1101.
  - `setup.py`: 70-100, 205-216, 726-740.
- **Repository scans.**
  - `threadprivate` counts per `.v` file: `bbb` 522, `api` 25, `ppp` 0 real markers (4 hits, all in comments).
  - Rate-file presence in the repo (`git ls-files`) and on `origin/pytests`.
  - `.github/workflows/build-test-wheel.yml` (dependencies and test checkout).
  - `CLAUDE.md`, `.claude/context/testing.md` and `.claude/skills/validate/SKILL.md` for statements the epic makes
    stale.
- **AIUE-9.** Grepped `docs/prds/AIUE-9-create-end-to-end-test-suite.md` in the `AIUE-9-planning` worktree for
  `omp_check`, `OMP_NUM_THREADS`, "randomness" and AIUE-8.
- **Statistics.** I checked the 0/30 bound arithmetic.
- **Not checked.** The §6.3 numbers are the author's planning measurements. I did not reproduce them, as instructed,
  and assessed only the logic built on them. No builds or tests were run.
