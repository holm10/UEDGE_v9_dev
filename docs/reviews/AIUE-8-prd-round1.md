# AIUE-8 PRD review, round 1

PRD: `docs/prds/AIUE-8-investigate-non-deterministic-openmp-jacobian.md` (local copy, branch
`feature/v9-AIUE-8-planning` at `v9-develop` tip `0fac655`).
Reviewer: `uedge-reviewer`, stage `prd`, round 1, 2026-10-14.

## Verdict

**REVISE**: 0 BLOCKER, 7 MAJOR, 8 MINOR.

## Summary

The PRD is well structured and matches the binding decisions in scope: investigate, fix, test and CI. It handles
branch classes correctly and has a sensible reproduce, explain, fix, guard sequence. Most file:line citations are
accurate. However, several of its working inferences about the OpenMP path are wrong or incomplete when checked
against the code.
- The Newton iterations after iteration 0 depend just as much on the **OpenMP RHS** as on the Jacobian. The
  harness's planned "OpenMP `yldot` at the starting state" actually runs the **serial** RHS.
- The serial `jac_calc` does *not* have the same structure as `LocalJacBuilder`.
- Requiring `CheckJac` to pass (absolute `1e-14`) amounts to bitwise equality with serial, which the PRD itself puts
  out of scope.

The "nothing may change" interpretation has no escalation route for a fix that changes the OpenMP RHS, and no runnable
bitwise check for serial results. The CI job's ability to detect regressions is statistical and has not been
quantified. Story 6 implies a skill change that cannot go on a ticket branch. The overlap with AIUE-9 (reference
guard over `tests/`, two epics both claiming the "randomness" RCA, and both replacing `validate` §4) is not
addressed. All of these can be fixed in the text. None requires a different approach.

## Findings

### MAJOR

**P1-M1: The OpenMP RHS is under-weighted, and the planned RHS check measures the serial path.**
*Sections: §6 "`fnrm`" bullet, H5, §7.2 "Per repeat", §9 "OpenMP results", Appendix assumptions.*

The PRD reasons that "the owner sees the same `yldot` but different `fnrm`, which points first at the **Jacobian**".
It plans to verify the OpenMP RHS with "`yldot` at the starting state: one OpenMP RHS evaluation". Both rest on a
wrong model of the code path.

- `OMPPandf1Rhs` runs the parallel loop only when `ijactot.gt.0`. Otherwise it calls `InitOMPPandf1(1)` and the
  **serial** `pandf(-1,-1,…)` (`ppp/omp_parallel.F90:949`, `:989-991`). `ijactot` is reset to 0 at the start of
  `exmain` when `icntnunk=0` (`bbb/odesetup.m:6799`), and the OpenMP Jacobian increments it only when a Jacobian is
  built (`ppp/omp_parallel.F90:581`). So iteration-0 `fnrm` and any "starting-state" `yldot` taken before the first
  Jacobian come from the serial RHS. That alone explains "same `yldot`" without saying anything about the
  parallel RHS.
- After the first Jacobian, every residual evaluation in `nksol` goes through the parallel RHS. This covers the
  line-search evaluations and the Krylov matrix-vector products. The products are difference quotients of `f`
  because `mdif=0` by default (`bbb/bbb.v:1213`, so `mfdif=2`, `svr/nksol.m:865`, `atv` at `svr/nksol.m:1912`).
  The chain is `f` = `rhsnk` (`bbb/odesolve.m:368`) → `pandfrhs_interface` (`bbb/oderhs.m:1005`) →
  `OMPPandf1Rhs` (`bbb/pandf.m:19-21`). The Jacobian only enters through the ILUT preconditioner. A
  non-reproducible parallel RHS at the perturbed states is therefore just as consistent with the symptom as a
  non-reproducible Jacobian.
- H1 applies to the RHS as well as to the Jacobian. `OMPPandf` evaluates padded chunks with `xc=yc=-1`
  (`ppp/omp_parallel.F90:1036-1092`) on per-thread module state that carries over from earlier chunks and Jacobian
  columns. The schedule is `SCHEDULE(dynamic)`, and there is no re-copy from the master before the RHS loop. H5 only
  covers summation order.

**Resolve by:**
- (a) Remove or soften the "points first at the Jacobian" inference.
- (b) Specify that the harness measures the OpenMP RHS only once `ijactot>0`, for example right after the first
  Jacobian, at the post-step state, and at a few Krylov-perturbed states. Assert that the parallel branch actually
  ran.
- (c) Add a characterisation arm with `OMPParallelJac=1, OMPParallelPandf1=0`, set against both switches on. This
  separates the Jacobian from the RHS. `OMPParallelPandf1=1` forces `OMPParallelJac=1` (`ppp/parallel.F90:30-36`),
  so this is the only factorial that is possible.
- (d) Add "history-dependent per-thread state in RHS chunks" to H1, or as its own hypothesis.

---

**P1-M2: Requiring `CheckJac` to pass amounts to bitwise equality with serial, which conflicts with the out-of-scope
list. The PRD's "same structure" premise is false.**
*Sections: §6 "Per-column reset", §9 "OpenMP results", §11 functional requirements, §7.5 "Also run once", §4 Out of
scope, R1.*

§4 puts "bitwise equal to serial" out of scope, and §11 lists it as a non-gating quality indicator. But §9 and §11
require "`CheckJac=1` … pass on the reproducer case", and the CI job runs it with abort. `CheckJac` compares the CSR
arrays entry by entry with an **absolute** tolerance of `1e-14` (`ppp/parallel.F90:119-120`). For any Jacobian entry
with |J| above roughly 50 that is tighter than one ulp. In practice, this is bitwise equality with serial. The
diagonal alone carries `-1/dtuse`, which is huge for small `dtreal`. `CheckPandf1` is effectively bitwise too
(absolute and relative `1e-14`, `ppp/parallel.F90:354-356`).

The PRD also says "The serial `jac_calc` has the same structure (`bbb/oderhs.m:1012-1240`)". The code says
otherwise:
- **Reset call.** The serial reset call is commented out (`bbb/oderhs.m:1220-1222`). `LocalJacBuilder` makes an
  extra `pandf(xc,yc)` call whenever `isjacreset>=1` (default 1, `bbb/bbb.v:3305`) and `mod(iv,numvar)==0`
  (`ppp/parallel.F90:320-325`). The sequence of `pandf` calls per column, and so the module-state history, differs
  from serial.
- **Clipping test.** Serial scales by `sfscal(ii)` (`bbb/oderhs.m:1187`); parallel scales by `sfscal(iv)`
  (`ppp/parallel.F90:292`). The two agree at the default `jaccliplim=0` (`bbb/bbb.v:3308`) but not in general.
- **Perturbation size.** Serial uses `del` (`bbb/oderhs.m:1156`); parallel uses `delperturb`
  (`ppp/parallel.F90:253`). These are separate user variables (`bbb/bbb.v:3301-3302`).
- **Diagonal terms.** Serial adds `1/dtuse` and `nufak` only when `svrpkg` is `nksol` or `petsc`. Parallel always
  adds them.
- **Initial evaluation.** The master's full evaluation before the parallel loop uses `t=0.0`
  (`ppp/omp_parallel.F90:680`).
- **`ijactot` timing.** It is incremented before the build in the OpenMP path and after it in serial.

A fix that makes the OpenMP Jacobian deterministic may therefore still fail `CheckJac`. R1's own fallback, "a
per-column reset in `LocalJacBuilder`", would add further differences from serial.

**Resolve by:** making the requirement consistent. Either (a) keep `CheckJac` and `CheckPandf1` passing as gating
criteria, explicitly accept that this means near-bitwise equality with serial, and move it out of the out-of-scope
list; or (b) demote it to a measured quality indicator, and replace the CI step with a non-aborting serial-vs-OpenMP
report. In both cases, correct the "same structure" sentence, list the known structural differences, and state
whether removing them is in scope. Under P1-M3 they may change OpenMP results.

---

**P1-M3: The "nothing may change" interpretation is incoherent for the OpenMP RHS and does not say which build
"serial" means.**
*Sections: Appendix "How decision 4 is read", §9, §7.4, R1.*

The interpretation adds "the OpenMP RHS `yldot` does not change", but the escalation rule (§9, R1) covers only fixes
that move **serial** results. Given P1-M1, the OpenMP RHS may well be non-reproducible itself, or may be the root
cause. Then the fix necessarily changes it, and the PRD gives no route: the work is neither allowed nor escalated.
"Does not change" also has no reference value if the pre-fix OpenMP RHS turns out to be run-dependent.

Separately, "serial" is ambiguous. The default `pip install .` build and the published wheels are **OpenMP builds**
(`setup.py:73-95`; `build-test-wheel.yml:100-135` builds wheels with no `--serial`). Most users therefore run the
OpenMP build with `OMPParallel*=0`. A `+threadprivate` edit or a `ppp.v` change regenerates the `OmpCopy*` modules
and changes the code generated for that build, not for `--serial`.

**Resolve by:**
- (a) Restating the rule as follows. The OpenMP RHS is held to bitwise-unchanged only if Phase 1 shows it is
  reproducible pre-fix. If it is not, it falls into the same "allowed to become deterministic" class as the OpenMP
  Jacobian.
- (b) Extending the escalation rule to any fix that changes a pre-fix *reproducible* OpenMP quantity.
- (c) Defining "serial results unchanged" as holding in **both** the `--serial` build and the default OpenMP build
  with both `OMPParallel*` switches 0.
- (d) Getting the owner to confirm this reading. It is an assumption, not a decision.

---

**P1-M4: The "bitwise unchanged" serial claim has no runnable check, and one case gives too little coverage.**
*Sections: §9 "Default-results impact", §11 serial criterion, story 5, Phase 1 and Phase 3 validation.*

§9 requires serial results "bitwise identical to `v9-develop` on the reproducer case **and on the serial regression
suites**". But the suites:
- compare against stored references with `rtol=1e-5`, not old against new and not bitwise (`.claude/context/testing.md`,
  "Suite structure", step 3);
- fail at checkout in CI on any non-`master` branch (`build-test-wheel.yml:57-65`).

"All serial regression suites pass" therefore cannot show bitwise identity. No command is named for the old-vs-new
comparison: two builds and two venvs, dump `yldot`, the serial Jacobian and `fnrm`, and compare. The fixes will land
in shared `pandf` code, for example `pandf_plasma_energy.m` or `pandf_boundary.m`. A single OpenMP reproducer case
exercises only the options it switches on. A fix could move serial results for impurities (`isimpon`), molecules,
`isphion` or double null without the reproducer noticing.

**Resolve by:** naming the check, for example `tests/omp/serial_bitwise.py --ref-venv … --new-venv …`. It should run
the reproducer **plus** the upstream `pytests` case inputs (or AIUE-9 families if available) in both builds (see
P1-M3) and compare `yldot`, the serial Jacobian (`jac`/`jacj`/`jaci`) and the `fnrm` history bitwise. Make it a
success criterion with an exit code, and require its output in every Phase 1 and Phase 3 PR.

---

**P1-M5: The CI determinism check, and the post-fix acceptance, depend on chance, and the chance is not quantified.**
*Sections: §7.1 (≥ 3/10), §7.5 (5 + 3 repeats), §11 (10/10, "shown to fail … run once", seeded race "checked once"),
R2.*

Decision 1 requires a CI job that catches non-determinism. With the stated minimum pre-fix rate (each run differs from
run 1 with probability around 0.3), 5 repeats at 4 threads give 4 comparisons. They miss the defect with probability
about 0.7^4 ≈ 0.24. Adding the 3 runs at 2 threads still leaves about a 1-in-8 chance per CI run that a real
regression passes. Showing the failure "once" on the pre-fix code or on a seeded race says nothing about this rate.

The same weakness affects acceptance. If an incomplete fix leaves a residual root cause with a 5 % rate, it passes
"10/10 identical" with probability about 0.95^9 ≈ 0.63. `CheckJacRepro` makes detection more sensitive, but it is
still statistical under dynamic scheduling.

**Resolve by:**
- (a) Stating a required detection probability per CI run (for example ≥ 99 %) and showing it by measurement on the
  pre-fix code and on the seeded race, over ≥ 20 CI-equivalent runs. Tune the repeat count to meet it.
- (b) Sizing the post-fix acceptance so that zero failures bound the residual rate. For example, 0/30 bounds it below
  10 % at 95 % confidence.
- (c) Preferably, adding a deterministic amplifier to `CheckJacRepro`: a second evaluation under a *different but
  fixed* column-to-thread assignment, such as `schedule(static)` or a reversed column order, set against the dynamic
  one. Under H1 this makes any history dependence fail with near certainty, independent of timing. A diagnostic
  switch for this falls under §7.3's diagnostics, not "a switch just for an experiment".

---

**P1-M6: Story 6 implies a change to the `validate` skill, which is a process change and cannot go on a ticket
branch.**
*Sections: §5 story 6, §3 "AI agents" persona, §4 Integration.*

Story 6 says the OpenMP step of `validate` becomes mechanical through `run_determinism.py`. That step is defined in
`.claude/skills/validate/SKILL.md:70-83`. Editing a skill is a **process** change. `change_kind.py` rejects it on any
ticket branch even with the `AI-layer: code-facts` trailer (`.claude/hooks/change_kind.py`, the `never` branch;
`.claude/context/branching.md`, "Guard rails"). The PRD's AI-layer bullet lists only the two context files, so the
skill change is either missing from scope or would be attempted on a ticket branch. The reviewer brief makes the
latter a BLOCKER at implementation.

**Resolve by:** stating that the `validate` (and, if wanted, `code-review`) update is a separate
`feature/v9-ai-<slug>` PR, filed through `system-review`/`ai-layer` after the harness lands. Alternatively, rephrase
story 6 so that the ticket only documents the harness in `.claude/context/openmp-jacobian.md` (code facts).

---

**P1-M7: The AIUE-9 coordination misses three real conflicts.**
*Sections: §4 "Coordination with AIUE-9", §13, Appendix related documents.*

The AIUE-9 PRD (`docs/prds/AIUE-9-create-end-to-end-test-suite.md` on `feature/v9-AIUE-9-planning`) conflicts in
three places:
- **The reference guard covers `tests/omp/`.** AIUE-9's guard covers "**everything under `tests/`**" (line ~611). Any
  change needs a `Test criteria: changed` line, harness changes count as loosening by default, `tests/**` requires
  CODEOWNER review, and `test_inventory.py` parses every Python file under `tests/`. If AIUE-9 merges first,
  every AIUE-8 PR that touches `tests/omp/` is gated by those rules. That includes tuning the repeat counts in
  Phase 4.
- **Both epics claim the same RCA.** AIUE-9 §7.7 says "The epic owner's observed 'randomness' … must be explained"
  and files any same-build difference as a defect. That is the AIUE-8 RCA.
- **Both replace `validate` §4.** AIUE-9's `tests/tools/omp_check.py` is "the harness replacement for today's
  `validate` §4". So is AIUE-8's story 6. AIUE-9 also pins `OMP_NUM_THREADS=1` in its harness, which AIUE-8's
  `--threads` must override.

"Whichever epic merges second reconciles" does not cover the guard. That is a procedural rule, not a merge
reconciliation.

**Resolve by:** stating in §4 and §13 that:
- AIUE-8 owns the explanation of the owner's run-to-run randomness, and AIUE-9 links to the AIUE-8 RCA;
- if AIUE-9's guard lands first, the AIUE-8 PRs carry `Test criteria: changed` (or `tests/omp/` is listed as
  unguarded additions);
- exactly one tool replaces `validate` §4, and which one.

Ideally, record the agreement in both PRDs.

### MINOR

**P1-m1: Code facts that are wrong or imprecise.**
- §4 Out of scope says "`OMPilut` is disabled, `bbb/oderhs.m:4657`". It is selectable through `ParallelMatfac`
  (default 0, `bbb/bbb.v:4133`; dispatch at `bbb/oderhs.m:4656`), and it contains no OpenMP directives. Say "off by
  default and serial in effect".
- §7.2(c) cites `bbb/bbb.v:2006-2008` for six index arrays. `idxn`, `idxg` and `idxu` are at 2002-2005. `idxtg`
  (gas temperature, `bbb/bbb.v:2004`) is missing, but the `istgon` characterisation needs it.
- §4 Deployment says "`-fopenmp`, set through Forthon `--omp`, `setup.py:94-95`". `-fopenmp` comes from `FARGS`
  (`setup.py:79`). `--omp` (`setup.py:95`) is the Forthon flag that generates the `OmpCopy*` modules.
- §6 "Pinned threads": `ppp.Nthreads` does not set the team size. `InitOMPJac` calls
  `OMP_SET_NUM_THREADS(OMP_GET_MAX_THREADS())` (`ppp/omp_parallel.F90:296`). Neither parallel loop has a
  `num_threads` clause. `Nthreads` is only clamped and used for `NchunksJac` when `OMPJacNchunks<0`
  (`ppp/omp_parallel.F90:299-317`). `OMP_NUM_THREADS` is the real control. The harness should record the
  **effective** team size (`omp_get_num_threads()` inside the region), and the stories and criteria should be phrased
  in terms of it.
- H2: `dtold`/`dtreal` (`bbb/pandf_plasma_continuity.m:117-122`) sits inside the `ismcnon` branch, which OpenMP
  blocks (`bbb/odesetup.m:6740-6745`). It is not a live candidate. The `ue_*_flux*` writes in `bouncon`
  (`bbb/pandf_boundary.m:1176-1200`) are diagnostic outputs and are not read by the residual. Say so, so that Phase 2
  does not chase benign races first.

**P1-m2: Concrete leads missing from the hypothesis list.**
- **Store/reset mechanism.** The `jacobian_store_*` / `jacobian_reset` mechanism (`bbb/pandf.m:565-568`, `:710`;
  `bbb/pandf_jacobian.m`) carries state from one column to the next. It restores the electron-energy quantities
  `erliz`, `erlrc`, `eeli`, `pwrebkg` and `pwrzec` at `(xc,yc)`. Their `*old` scalars are captured **inside box loops**
  (`bbb/pandf_plasma_energy.m:572-597`, `:905-911`), so they hold the pre-call value at the *last cell of the box*,
  not at `(xc,yc)`. This is an H1-class lead in exactly the equation the owner flagged. Any fix there lies in the
  serial code path, which makes R1 concrete.
- **Uninitialised work arrays.** `LocalJacBuilder` uses automatic, uninitialised `wk(neq)` and `yl_check(neq)` on
  each thread's stack (`ppp/parallel.F90:195-196`). Serial uses the caller's persistent work array. The `wkcopy`
  prepared in `OMPJacBuilder` (`ppp/omp_parallel.F90:705`) is never passed on. A cheap test is the existing `--debug`
  build (`-finit-real=snan`, `setup.py:84-91`).
- **Timing index.** `OMPTimeLocalJac(tid+1)` is indexed by thread, not by chunk (`ppp/omp_parallel.F90:734`).
  It is harmless at the default `NchunksJac=neq` but matters for the H4 experiment with `OMPJacNchunks<0`.

Add these as hypotheses or first places to look.

**P1-m3: The acceptance quantity for `fnrm` is defined two ways.** The PRD says both "bitwise" and "the 16-digit
`fnrm` printed by `nksol`". `g26.16` (`svr/nksol.m:1100`) can hide a last-ulp difference in a double. "Computed
internally … where a hook is available" is not specified. Define one quantity. Also compare the final state (`yl`,
or `nis`/`tes`/… after the fixed schedule) bitwise, which needs no hook.

**P1-m4: Thread counts in the acceptance criteria disagree.** The MVP definition says "4 threads on Linux CI and
4 and 8 locally". The functional requirement and the Phase 3 validation say "2, 4 and 8, on Linux and on macOS". Pick
one set, and say which machine provides the local Linux runs.

**P1-m5: The CI budget and setup do not add up.** At the stated upper limits, the job needs a `-O3` build (several
minutes), plus 8 runs of ≤ 60 s, plus a `CheckJac` run that also builds a serial Jacobian. That exceeds 15 minutes. Set
a tighter per-run budget (for example ≤ 30 s), or a budget for the build. List the pip dependencies, mirroring
`build-test-wheel.yml:76-81` (`forthon>=0.10.7`, `h5py`). The 4-vCPU runner assumption holds only while the repository
stays public. It is public now, as checked through the GitHub API.

**P1-m6: R4's platform description is inaccurate.** The parallel regions are Fortran compiled by gfortran, which
means libgomp on **both** platforms. On macOS the C extension is compiled with clang and libomp
(`build-test-wheel.yml:116-135`), and `bbb/exmain.c:38,102,114` contains `#pragma omp master`. Both runtimes can
therefore be loaded at once. Record the linked runtimes (`otool -L`/`ldd`) and `OMP_STACKSIZE` in the provenance:
the automatic arrays in P1-m2 live on worker stacks.

**P1-m7: There is no risk entry for the reproducer not arriving or not fitting.** Decision 5 leaves the case TBD,
and it is on the critical path for Phases 1 to 4. Add a risk covering a case that is late, too large, or slower than
60 s. As a fallback, the harness and Fortran diagnostics tickets can start on an upstream `pytests` case.

**P1-m8: The diagnostics have side effects when on.**
- **`CheckJacRepro`.** Calling `jac_calc_omp` twice increments `ijactot`/`ijac` (`ppp/omp_parallel.F90:581-582`) and
  updates `OMPLoadWeight`/`OMPTimeLocalJac`. Specify which Jacobian goes back to the solver, and that the counters
  are restored.
- **`ForceSerialCheck`.** It runs only inside `jac_calc_parallel`, so only with `OMPParallelJac=1`. It overwrites the
  solver's Jacobian with the serial one (`ppp/parallel.F90:87`), so it cannot serve as the Phase 1 "serial
  baseline". Use plain serial fresh-process repeats.
- **`CheckPandf1`.** It runs a full serial `pandf` on the master after every parallel RHS
  (`ppp/omp_parallel.F90:984-985`), which changes the master's state history. Keep these checks out of the repeat
  runs. §7.5 already isolates them; say why.

## What was checked and how

- **PRD.** Read in full and checked against the five binding decisions. Scope, success criteria and phases reflect
  decisions 1, 2, 3 and 5. Decision 4's interpretation is addressed in P1-M3 and P1-M4. The re-characterisation of
  `isnion` and `isupon` is verification, not a widening of scope.
- **Code facts verified in the worktree** (`git log` at `0fac655`).
  - **`ppp/` files.**
    - `ppp/ppp.v`: lines 6-7, 9, 14, 43, 50 and 54 checked; groups `ParallelSettings` and `ParallelDebug`.
    - `ppp/parallel.F90`: lines 45-156, 84-152, 92, 120, 159-340 and 348-365 checked.
    - `ppp/omp_parallel.F90`: lines 281-330, 495-642, 645-748, 753-800, 902-996 and 999-1100 checked; all
      `!$omp` directives listed with grep.
  - **`bbb/` files.**
    - `bbb/oderhs.m`: lines 955-1010 (`rhsnk`), 1012-1240 (`jac_calc`) and 4645-4705 checked.
    - `bbb/pandf.m`: lines 7-28, 540-620 and 695-715 checked.
    - Also read: `bbb/pandf_jacobian.m` and `bbb/pandf_plasma_energy.m:545-610,895-935`.
    - `bbb/odesetup.m:6720-6800` checked.
    - `bbb/bbb.v`: lines 56, 1213-1215, 2000-2012, 2263-2268, 2891, 2920-2940, 3005-3039, 3298-3308 and 4127-4133
      checked.
  - **`svr/nksol.m`.** Lines 850-870, 1090-1100 and 1912-2003 checked.
  - **`setup.py`.** Lines 60-110, 200-220 and 720-745 checked.
  - **Other files.** `api/fmombal.m:70,368,1064`; `src/uedge/__init__.py:58-67`; `bbb/exmain.c` (omp pragmas).
- **Confirmed accurate.** `ppp/ppp.v:6-7,43,50`; `ppp/omp_parallel.F90:313,495,645,712-715,902-996,953-955,294-310`;
  `ppp/parallel.F90:45-156,92,120,84-150`; `svr/nksol.m:1100` (`g26.16`); `bbb/bbb.v:2927-2934`;
  `bbb/odesetup.m:6727-6774`; `api/fmombal.m` `save` lines; `setup.py:209-214,731-737`.
- **CI and policy.**
  - Workflows read: `build-test-wheel.yml` (serial tests; OpenMP wheels on Linux and macOS) and the workflow list.
  - Repository visibility confirmed public with `curl https://api.github.com/repos/holm10/UEDGE_v9_dev` (HTTP 200).
  - `.claude/context/branching.md` and `.claude/hooks/change_kind.py` read: `tests/omp/` and the new workflow are
    product, `docs/rca/` is artifact, the context edits are code-facts, and skill edits are never allowed on a ticket
    branch.
  - `.claude/skills/validate/SKILL.md:70-83` and `.claude/skills/create-prd/SKILL.md` read; all 15 required sections
    are present.
- **AIUE-9 PRD.** Grepped and read §4 out of scope (lines 188-191), the reference guard (around lines 597-650) and
  §7.7 (lines 653-700).
- **Statistics.** The detection probabilities in P1-M5 are back-of-envelope binomial estimates. They assume
  independent runs at the PRD's stated minimum rate.
- **Not run.** No builds or test suites. Every claim could be checked by reading the code.
