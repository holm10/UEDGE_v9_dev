# Feature: AIUE-60 — Fix the remaining OpenMP races in the `pandf` tree and the clip-index inconsistency

Validate the patterns and file references below before implementing. Line numbers are at `1553e75` (AIUE-56 tip).

## Summary
**Type**: Bug fix (numerics/parallel; OpenMP build only)
**Complexity**: Low (code: `.v` attributes, one MPPL hunk, one `.F90` line), Medium (validation: TSan, flow, clip check)
**Default results**: Unchanged, bitwise, in the `--serial` build and in the OpenMP build with both switches 0 (argument
below). OpenMP Jacobian: unchanged at the default `jaccliplim=0`; with `jaccliplim>0` it changes to the serial pattern.
**Packages / files**: `bbb/bbb.v`, `com/com.v`, `aph/aph.v` (attributes only), `bbb/pandf.m` (`initialize_ranges`,
`nfsp`), `ppp/parallel.F90` (`LocalJacBuilder`, clip index), `.claude/context/openmp-jacobian.md` (code facts),
`docs/reviews/AIUE-60-clip-check.py` (test tool, committed with this plan)
**Branch / worktree**: `bugfix/v9-AIUE-60-omp-races` @ `/Users/holma/Documents/uedge/src/uedge-wt/AIUE-60`
(base: `bugfix/v9-AIUE-56-omp-jacobian-fix` at `1553e75`, stacked; PR targets that branch until AIUE-56 merges)

## Problem and solution

The AIUE-50 scan and the AIUE-55 RCA (`docs/rca/AIUE-8-omp-jacobian-nondeterminism.md` on the AIUE-62 branch,
§Shared-state scan F5–F7, F9–F10, F15–F16; §Refuted or minor hypotheses) left these items for AIUE-60. A static probe
made for this plan (below, "Probe S") found more of the same kind on non-default model paths. They are listed
separately (part B) so they can be kept or dropped as a block.

### Part A — the ticket's items

| # | Item | Where (re-located) | What happens | Fix |
|---|---|---|---|---|
| A1 | `areapl` (F16) | decl `bbb/bbb.v:951` (`Rccoef`, `+work`); written at `bbb/pandf_boundary.m:3091,3166,3446,3544` (`left_boundary`) and `:3797,3882,4180,4277` (`right_boundary`), each followed by reads in the same block (`:3095`, `:3173,3179`, `:3453,3461`, `:3548`, `:3812`, `:3888,3894`, `:4188,4196`, `:4281`) | shared scalar written and read by every thread whose box touches a plate: a race on physics state | `+threadprivate` |
| A2 | `TimingPandfOn` (F5) | decl `bbb/bbb.v:4136` (`PandfTiming`); written every call at `bbb/pandf.m:573-579`, read at `:580-598,713`, `bbb/oderhs.m:88,532`, `ppp/omp_parallel.F90:1227,1232,1294` | every thread writes it (always 0 in a Jacobian column, `yl(neq+1)=1`) | `+threadprivate` |
| A3 | `com.nfsp` (F7) | decl `com/com.v:28` (`Dim`); written every call at `bbb/pandf.m:50-51` (`initialize_ranges`) | every thread writes it. For `isimpon=3,4` it is written **twice with different values** (`nisp`, then `nhsp`), so another thread can read the transient `nisp` as a species-loop bound: a real race on results for `isimpon=3,4`, benign otherwise | write only when the value changes (line-neutral MPPL hunk, below). Not `+threadprivate`: it is in `Dim` with the grid dimensions, and the RHS path writes it too (`ppp/omp_parallel.F90:831-832`, see Notes) |
| A4 | `com` timers (F6) | `Timing` (`com/com.v:502-521`): `ttimpfe`, `ttimpjf` (`bbb/pandf.m:758,760`, `timimpfj`), `ttnpg` (`bbb/pandf.m:636`), `ttngxlog`, `ttngylog`, `ttngfd2`, `ttngfxy` (`bbb/pandf_gas_continuity.m:664,765,777,876`), `ttimpc` (`api/fmombal.m:248`); `Timespl` (`com/com.v:564-567`): `totintrv` (`com/comutil.m:3654,3902`, `B2VAhL`/`B1VAhL`, reached from `emissbs`), `totb2val` (`aph/aphrates.m:596,773,1031`) | lost updates (TSan: 199 of the in-loop reports in AIUE-50) | `+threadprivate` on these 10 accumulators only. Not on the inputs `istimingon`/`iprinttim` and not on the master-only `ttotfe`, `ttotjf`, `ttmatfac`, … (written outside the parallel regions). With OpenMP the reported values then count the master thread only: say so in each doc string |
| A5 | Clip index | serial `bbb/oderhs.m:1187`: `abs(jacelem*sfscal(ii))`; parallel `ppp/parallel.F90:292`: `abs(jacelem*sfscal(iv))`; debug print `:288` prints `sfscal(iv)` | `ii` is the row (equation), `iv` the perturbed variable (column). `sfscal` scales equations, so serial is right. Probe C: no effect at `jaccliplim=0`; at `1e-6` the OpenMP build keeps exactly the column-rule set (full problem: 812 962 entries differ from serial) | `sfscal(ii)` at `:292` and in the debug print `:288` |
| A6 | `emcoef` in `copyin` (F15) | `ppp/omp_parallel.F90:721` (`copyin(yinc,xlinc,xrinc,emcoef)`), `USE Imslwrk, ONLY: emcoef` `:654` | `copyin` pointer-assigns each worker's `emcoef` to the master's array, and that stays after the loop: from the second Jacobian on, `OmpCopyPointeremcoef` has 3 workers write the same values into the master's array (outside the column loop; benign). Inside the loop `emcoef` is only read | **Document, don't change here** (`openmp-jacobian.md`). Since AIUE-56 the `copyin` is redundant (the scalars-first copy gives each worker correct tables in its own buffer). Removing it touches the directive AIUE-61 rewrites (`schedule`, `firstprivate` of the per-chunk arrays), so it is offered to AIUE-61 (merge note) |
| A7 | `fmombal` SAVE arrays (F9, F10) | `api/fmombal.m:70` (`uresp`, `usave`, `caplams`), `:368` (`mrespond`), `:1064` (`zrespond`) | race when `fmombal` runs on several threads, reached only via `mombal` for `isimpon=5` (`bbb/pandf_plasma_momentum.m:669-671,701-703`). Probe S shows the `isimpon=5` path also writes 9 non-threadprivate `bbb` `Reduced_ion_interface` arrays (`amu`, `nuion`, `nurec`, `qneut`, `uneut`, `friction`, `friccomp`, `qcond`, `ucond`, `bbb/bbb.v:3937-3954`), all 12 `api` `Reduced_ion_variables` (`api/api.v:224-235`) and 4 `Reduced_ion_constants` scalars (`sumforce`, `totmass`, `anorm`, `acci0`, `api/fmombal.m:819,774,1086,536`). The SAVE locals hold state between calls only for `ldir<2`; `mombal` always passes `ldir=2` (`bbb/pandf_plasma_momentum.m:1014`) | **Document as not OpenMP-safe; propose a follow-up ticket.** A fix needs ~25 attributes plus per-thread SAVE locals, which MPPL can't declare `threadprivate` (no `!$omp` directive survives the fixed-form conversion), and there is no `isimpon=5` case anywhere (pytests, `builder/test`, the reproducer) to validate it on |

### Part B — same-class races found by Probe S (not in the ticket; recommended in, each a `.v` attribute)

| # | Variables | Written at | Path (default off) | Effect |
|---|---|---|---|---|
| B1 | `com.ghxpt`, `gvxpt`, `sxyxpt` (`com/com.v:427-429`, `Comgeo`) | `bbb/pandf_plasma_momentum.m:298-306`, inside the x-point loop that runs on every call | `nxpt=2` (full double null): set to the lower values, then the upper ones, on every call | real race on the x-point momentum fluxes `fmihxpt`/`fmivxpt` (`:338-345`); read-only for `nxpt=1` |
| B2 | `bbb.sputflxllim`, `sputflxrlim` (`bbb/bbb.v:986-987`, `Rccoef`) | `bbb/pandf_boundary.m:4957-4990,5041-5070` (`limiter_patch`), zeroed then accumulated per `iy` | `islimon≠0` with limiter sputtering | real race (two threads accumulate the same element) |
| B3 | `bbb.iwalli`, `iwallo` (`bbb/bbb.v:669-670`), `fngysi`, `fngyso` (`bbb/bbb.v:679,683`) | `wsmodi`/`wsmodo` (`bbb/pandf_boundary.m:574-715`), called from the wall BCs at `:1412,1896,2447,2687` | coupled wall sources (`iscpli`/`iscplo`=1) | real race (zeroed, accumulated, then written to `fngysi`) |
| B4 | `aph.workh`, `iflag_aph` (`aph/aph.v:210,203`, `Aphwrk`) | written by `B2VAhL` (work array, flag) in `rqa`/`rra`/`rsa` (`aph/aphrates.m:569,594,748,771,1006,1029`) | `istabon=5,6` (spline hydrogen rates) | real race on the spline work array; the `api` analogue (`work2`, `iworki`, `icont`, `iflagi`) is already threadprivate (`api/api.v:154-160`) |

Every Part-B array has bounds from shared `com` `Dim` scalars or non-threadprivate `aph` scalars, so it has no
copy-order hazard (AIUE-56). `workh` is scratch (written before read in `B2VAhL`) and needs no copy; `aph` has no
`OmpCopy` call in `OMPJacBuilder` and doesn't get one. Workers get their own `workh` buffer at allocation time from
the generated `aphsetarraypointerworkh` (the `copyin(pcopy__)` pattern seen for `emcoef` in
`build/temp.*/api_p.F90:1222-1257` of the AIUE-56 build).

### Part C — documented as not OpenMP-safe, out of scope

Probe S also lists: the `isimpon=5` reduced-ion path (A7); Monte Carlo neutral coupling, `ismcnon≠0`
(`initialize_ismcnon`, `bbb/pandf_plasma_continuity.m:31-122`, rewrites `cfneut`, `cfvgpx`, …, `dtreal` on every call
by Jacobian/RHS mode; `bbb/ext_neutrals.m` reads and writes `MCN_*`/`PNC_*` and the equation switches); MPI domain
decomposition (`sendbdry`, `bbb/odesetup.m:5010-5021`). These go into `openmp-jacobian.md` as known unsafe paths.

### Probes made for this plan (scratch, not committed except the clip-check script)

- **Probe S (static):** every `.v` variable (all packages) assigned, or passed to `B2VAhL`/`B1VAhL`/`B3VAL`/a CALL, in
  the 145 units reachable from `pandf`, minus threadprivate ones and locals, filtered to units that `Use` the group.
  Built on the AIUE-50 `scan_saved_locals.py` call graph. Scripts: `/Users/holma/Documents/uedge/src/uedge-wt/logs/AIUE-60/{shared_writes,passed_args}.py`
  (they read the AIUE-50 tool; the execution phase copies them to `docs/reviews/AIUE-60-shared-writes.py` so the
  validation record can re-run them). Everything in Parts A–C comes from it or from the RCA; nothing else on default paths.
- **Probe C (clip):** `docs/reviews/AIUE-60-clip-check.py` on the AIUE-56 OpenMP build, 4 threads, `jaccliplim=1e-6`:
  - The first (`sfsetnk`) Jacobian of an `exmain` is clipped with `sfscal = 1` (in the clipped Jacobian the smallest
    `|raw|` is exactly `1.000e-6`), so it can't distinguish the rules. The `psetnk` Jacobian at Newton iteration 0
    (same state, `sfscal` from `sfsetnk`) can; the script uses it (`itermx=1`, `isrnorm=0`, `ireorder=0` in both arms).
  - Te box: 0 entries where the rules differ (insensitive, not used). `ni`: predicted 69 401, measured 55 897 + 13 504 =
    69 401 one-sided entries, OpenMP nnz 594 104 = the predicted column-rule count. Full problem: predicted 812 962,
    measured 442 576 + 370 386 = 812 962, OpenMP nnz 2 402 093 = column-rule count. Run time: `ni` ~20 s and full
    ~50 s per OpenMP run, full check ~4.5 min with K=1.

## Why defaults stay bitwise unchanged

1. **`--serial` build.** Forthon emits `!$omp threadprivate` and the `OmpCopy*` routines only with `--omp`
   (`Forthon/wrappergenerator_ompextension.py`, used only then; `setup.py` drops `--omp` for `--serial`). The
   `+threadprivate` attributes therefore produce identical generated Fortran. `nfsp`: the new code leaves `nfsp`
   with the value the old code ended with, and nothing runs between the two old assignments. `LocalJacBuilder` is
   compiled but never called (`jac_calc_parallel` is reached only through a `c!omp` line, `bbb/oderhs.m:4697`).
2. **OpenMP build, both switches 0.** Only the master thread runs `pandf`. Its copy of a threadprivate variable
   behaves like the old shared variable, Python sees the master copy (as for the 522 existing `bbb` ones), and the
   arithmetic is unchanged. `LocalJacBuilder` is not called.
3. **OpenMP Jacobian, `jaccliplim=0`.** Threadprivate copies hold the same values as before, minus the interference.
   The clip test `abs(x*s) > 0` keeps the same entries for `s = sfscal(ii)` and `s = sfscal(iv)`, because `sfscal` is
   positive and finite (`sfsetnk` stops on a zero row, `bbb/oderhs.m:2349-2352`). The only exception would be an
   underflow of `x*s` to 0, which needs `|x| < ~1e-309` at the smallest `sfscal` seen (5.9e-15); it is checked
   empirically by the flow. Workers get the Part-B values that pandf reads (e.g. `ghxpt` for `nxpt=1`) from
   `OmpCopyScalarcom`/`OmpCopyPointerbbb`, which `OMPJacBuilder` already calls, scalars first (AIUE-56). The
   reproducer is single null, so the flow exercises the `ghxpt` copy on every worker column near the x-point.
4. **Reported timers** (`com.ttimpjf` and the others in A4) count only the master thread in an OpenMP run. That is
   diagnostic output, not a result, and is stated in the doc strings and the PR.

## Context references — read before implementing
- `bbb/bbb.v:819-821` (`xcnearlb … +threadprivate`) and `api/api.v:152-160` (threadprivate work arrays): patterns.
- `bbb/pandf.m:46-51` (`nfsp`), `:573-580` (`TimingPandfOn`), `:751-765` (`timimpfj`).
- `ppp/parallel.F90:280-299` (`LocalJacBuilder` debug print and storage), `bbb/oderhs.m:1180-1197` (serial storage).
- `ppp/omp_parallel.F90:678-699` (copy order), `:718-721` (the parallel directive, `copyin`).
- `.claude/context/openmp-jacobian.md` (rules 1–4), `.claude/context/variables-forthon.md` (attributes, checklist 4),
  `.claude/context/mppl-fortran.md` (fixed form, `#` comments; no `float`, `break`, `while (` tokens).

## Step-by-step tasks

### 1. UPDATE `bbb/bbb.v`, `com/com.v`, `aph/aph.v` — `+threadprivate` (Part A1, A2, A4; Part B)
- **IMPLEMENT**: append `+threadprivate` after the type/default/existing attributes on these lines (same line, so no
  line moves): `bbb/bbb.v:951` (`areapl`, keep `+work`), `:4136` (`TimingPandfOn`); `com/com.v:506,508,514,517-521`
  (`ttimpfe`, `ttimpjf`, `ttimpc`, `ttnpg`, `ttngxlog`, `ttngylog`, `ttngfd2`, `ttngfxy`), `:566-567` (`totb2val`,
  `totintrv`); Part B: `com/com.v:427-429`, `bbb/bbb.v:669-670,679,683,986-987`, `aph/aph.v:203,210`. Extend each A4
  doc string with `; OpenMP: master thread only`. Add a short `#` doc to `TimingPandfOn` and `areapl` only where none exists
  (no units change). If Part B is dropped in review, skip its lines.
- **PATTERN**: `work2(nwork2) _real +threadprivate # work array for B3VAL` (`api/api.v:156`).
- **GOTCHA**: no `#`-in-string or MPPL tokens in `.v` (not converted, but keep descriptions plain). `fngysi`/`fngyso`
  have a continuation doc line (`bbb/bbb.v:680,684`): put the attribute on the declaration line.
- **VALIDATE**: OpenMP build; `grep -n 'threadprivate(areapl)\|threadprivate(ttimpjf)\|threadprivate(ghxpt)\|threadprivate(workh)' build/temp.*/{bbb,com,aph}_p.F90`
  finds each; serial build: `grep -c threadprivate build/temp.*/*_p.F90` is 0.

### 2. UPDATE `bbb/pandf.m:48-51` — `nfsp` written only on change (A3)
- **IMPLEMENT** (line-neutral: 2 comment + 2 code lines replace 2 + 2):
  ```
  c ... Upper limit of species loops with ion sources/fluxes/velocities. nfsp (com
  c     Dim) is shared by OpenMP threads: write it only when it changes (AIUE-60).
        if ((isimpon.eq.3 .or. isimpon.eq.4) .and. nfsp.ne.nhsp) nfsp = nhsp
        if (isimpon.ne.3 .and. isimpon.ne.4 .and. nfsp.ne.nisp) nfsp = nisp
  ```
- **GOTCHA**: fixed form, code from column 7, ≤ 72 columns. Line-neutral so the `bbb/pandf.m:513`, `:535-544`,
  `:573-575` references in `CLAUDE.md` and the context stay valid. `OMPJacBuilder` runs a full `pandf` on the master
  before every parallel loop (`ppp/omp_parallel.F90:680`), so in the loop the condition is always false.
- **VALIDATE**: serial build; the serial check (below) covers it.

### 3. UPDATE `ppp/parallel.F90:288,292` — clip with the row's `sfscal` (A5)
- **IMPLEMENT**: `storage: if (abs(jacelem*sfscal(ii)) .gt. jaccliplim) then` and `sfscal(ii)` in the debug write;
  add a one-line comment `! ii is the row (equation): same test as jac_calc, bbb/oderhs.m (AIUE-60)` above
  `storage:` **only if** it can replace an existing blank line (keep the routine's line numbers for the AIUE-61 merge),
  otherwise no comment.
- **GOTCHA**: free form `.F90`, `!` comments. Touch nothing else in `LocalJacBuilder` (AIUE-61 edits its argument
  list, declarations and the loop start).
- **VALIDATE**: OpenMP build; clip check (Testing 5).

### 4. Copy Probe S into `docs/reviews/AIUE-60-shared-writes.py` (artifact) and run it on the built tree
- Expected after the fix: only Part C entries remain (plus the `PandfTiming` accumulators gated by `TimingPandfOn`,
  never written in a parallel region, and `ext_verbose`), listed in the validation record. Also run
  `scan_ompcopy.py` (AIUE-50, `tests/deterministic_omp/tools/`) on the AIUE-60 OpenMP build tree: 0 copy-order hazards.

### 5. UPDATE `.claude/context/openmp-jacobian.md` (own commit, trailer `AI-layer: code-facts`)
- Rule 1: add that a scalar every column recomputes to one value may instead be written only on change (`nfsp`), and
  that threadprivate timers report the master thread only.
- New bullet "Known OpenMP-unsafe paths": `isimpon=5` (reduced-ion `mombal`/`fmombal`), `ismcnon≠0`, MPI domain
  decomposition; and the `emcoef` `copyin` note (A6).
- Jacobian bullet: the parallel clip uses the row's `sfscal`, as serial; keep `jac_calc` and `LocalJacBuilder` in
  step (the existing WARNING comment in `jac_calc`).
- `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` clean (re-lock only re-read claims).

## Testing strategy (pre-registered)

Builds: `venvs/AIUE-60-omp` (this worktree) and `venvs/AIUE-60-serial` (detached tree
`../AIUE-60-serial` at the implementation commit), via `build_uedge.sh`. Base: `venvs/AIUE-56-omp`,
`venvs/AIUE-56-serial` (AIUE-56 fix `4fae2f9`; `1553e75` differs only in docs). Every run: fresh `python -I` process,
empty `HOME`, `OMP_STACKSIZE=512M`. Shared machine: ≤ 4 threads per process, ≤ 2 UEDGE processes at a time. Tool
commits are recorded in `docs/reviews/AIUE-60-validation.txt`.

1. **Build hygiene**: both builds import; no new warnings in the touched files (`grep -a -i warning` in the build logs
   for `pandf.F`, `parallel.F90`, `*_p.F90`); the threadprivate greps of task 1.
2. **Defaults unchanged (hard rule)**: AIUE-53 `serial_check.py` (`feature/v9-AIUE-53-serial-bitwise-check`),
   `--base-python AIUE-56-serial --new-python AIUE-60-serial --base-omp-python AIUE-56-omp --new-omp-python AIUE-60-omp
   --cases all --jobs 2`. **Gate: `RESULT: AGREE` (complete gate), exit 0.** Plus upstream pytests `D_only` with both
   AIUE-60 builds: pass.
3. **OpenMP results unchanged or closer to serial**, AIUE-52 flow from the reviewed harness
   (`/Users/holma/Documents/uedge/src/uedge-wt/AIUE-57/tests/deterministic_omp/harness/cli.py flow --all --arms jac
   --threads 2,4 --repeats 2 --max-jobs 2`), run for `AIUE-56-omp` and `AIUE-60-omp` one after the other.
   **Gates:** (a) every group that is PASS for AIUE-56 is PASS for AIUE-60; (b) in every other group, every AIUE-60
   mismatch is in Te rows (as for AIUE-56, residual C2) and the AIUE-56 C1-gate bounds hold on every AIUE-60
   one-evaluation run (`docs/reviews/AIUE-56-c1-gate.py`: Te-row max ≤ 10 × serial, every deviation ≤ 1e-6 × serial
   row max); (c) no row equation appears in AIUE-60 mismatches that doesn't appear for AIUE-56. 8 threads is not run
   (machine rule); stated as a gap.
   **Cross-build bitwise (deterministic configuration):** `cli.py check --preset tebox --arm jac --threads 4 --repeats 2
   --ppp '{"OMPJacNchunks": -1, "OMPAutoBalance": 0}'` for both builds (contiguous chunks: runs identical to each other,
   RCA), then `cli.py compare` AIUE-56 run0 vs AIUE-60 run0. **Gate: AGREE** (the change doesn't alter arithmetic).
4. **Clip, `jaccliplim>0`**: `docs/reviews/AIUE-60-clip-check.py check --python AIUE-60-omp --base-python AIUE-56-omp
   --clip 1e-6 --threads 4`, presets `ni` (`--repeats 3`) and `full` (`--repeats 2`). **Gates:** G1 every AIUE-60 OpenMP
   one-sided entry is a threshold flip (`|v/L−1| ≤ 1e-8/L`; for `ni`, whose groups are bitwise, 0 one-sided entries);
   G2 `sfscal` bitwise equal serial vs OpenMP; G3 every AIUE-56 OpenMP run has non-flip differences (negative control:
   the case detects the old rule; probe: 69 401 / 812 962); G4 AIUE-56 and AIUE-60 serial clipped Jacobians bitwise
   equal. Precondition met by Probe C (`rules_differ` > 0 for both presets).
5. **TSan, before/after** (procedure of AIUE-50, `tsan_summary.py` on `feature/v9-AIUE-50-shared-state-scan`):
   - Two scratch detached trees: `../AIUE-60-tsan-pre` at `1553e75` and `../AIUE-60-tsan` at the implementation commit;
     in each, an **uncommitted** scratch edit adds `-fsanitize=thread` to `FLAGS['FARGS']` in `setup.py`; build with
     `build_uedge.sh <tree> venvs/AIUE-60-tsan[-pre] omp`.
   - Runs (4 threads, `DYLD_INSERT_LIBRARIES=/opt/homebrew/opt/llvm/lib/clang/23/lib/darwin/libclang_rt.tsan_osx_dynamic.dylib`,
     `TSAN_OPTIONS="log_path=<dir>/tsan halt_on_error=0"`), through the harness `cli.py run --arm jac --threads 4`
     (its runner keeps these variables): presets `tebox` (`emissbs` timers), `ng` (gas plate BCs: the `areapl` site
     `:3446`), and `full` if memory allows (expected ~5–10 × 1.4 GB; one run at a time); one with `--itermx 2` on
     `tebox` (two Jacobians, so the A6 `emcoef` copy race shows outside the loop).
   - Summary per build: `python -I tsan_summary.py <dir>/tsan.*`. **Gate (after):** no report group with "in Jacobian
     loop = yes" on a global symbol; an in-loop heap/stack group is allowed only if the other access is outside any
     parallel region (the AIUE-50 false positive: numpy array written by the master before the region), each one
     classified in the validation record. **Expected before (negative control):** in-loop groups for `ttimpjf`,
     `totintrv`, `ttngxlog`, `ttngfd2`, `ttngylog`, `ttngfxy`, `ttnpg`, `TimingPandfOn`, `nfsp`, and `areapl` on `ng`/`full`.
     Reports outside the loop (copy routines, `emcoef`) are listed, not gated.
6. **Static**: Probe S after the fix (task 4) and `scan_ompcopy.py`: 0 copy-order hazards.

## AI-layer facts affected
`.claude/context/openmp-jacobian.md` (task 5). Checked: `CLAUDE.md` cites `bbb/pandf.m:513,535-544,573-575,31` and
`bbb/bbb.v:1629,1622,217-222,236,279,331,336,33-41` — task 2 is line-neutral and the `.v` edits add attributes on
existing lines, so none of them moves. `variables-forthon.md` counts "`+threadprivate` (522)" in `bbb.v`: becomes 524 with
Part A (A1, A2), 530 with Part B (B2, B3) — update the count. `physics-models.md` (impurities row) and `architecture.md` mention
`fmombal` only as a file: unchanged. Run `check_context_refs.py --changed origin/v9-develop` after the code commit to
confirm.

## Validation commands
`validate` skill (suites: `D_only`; `--omp` OpenMP check: the flow above), plus Testing 1–6.

## Acceptance criteria
- [ ] Builds without new warnings in touched files; threadprivate directives present (OpenMP) and absent (serial)
- [ ] AIUE-53 serial check AGREE, complete gate, both pairs; `D_only` passes in both builds
- [ ] Flow gates 3(a)–(c) and the cross-build bitwise AGREE
- [ ] Clip check G1–G4 PASS on `ni` and `full`
- [ ] TSan after: no global-symbol race in the Jacobian loop; before shows the listed groups
- [ ] Probe S after the fix lists only Part C (documented); `scan_ompcopy.py` 0 hazards
- [ ] `openmp-jacobian.md` and `variables-forthon.md` updated (`AI-layer: code-facts`); drift check clean
- [ ] Not this ticket's acceptance: the Linux M3 `up`-row residual (AIUE-65); AIUE-62 already saw that making `areapl`
      threadprivate doesn't remove it

## Merge note for AIUE-61 (`bugfix/v9-AIUE-61-omp-static-partition`, plan `4dea642`)
- Both branches stack on `1553e75`. AIUE-61 edits `ppp/ppp.v`, `ppp/omp_parallel.F90` (`InitOMPJac`, `jac_calc_omp`,
  `OMPJacBuilder`) and `LocalJacBuilder`'s argument list (`ppp/parallel.F90:159-160,185`), its loop start (`:211`)
  and its storage target (heap fix). AIUE-60 touches `ppp/` only at `ppp/parallel.F90:288,292`. Expected: clean
  auto-merge; if the heap fix rewrites the `storage:` block, keep AIUE-61's target arrays and AIUE-60's `sfscal(ii)`.
- `openmp-jacobian.md` and `.claude/context/refs.lock.json` will conflict textually: keep both sets of bullets, then
  re-lock with `check_context_refs.py` after re-reading the cited lines.
- Semantics: AIUE-61's per-chunk reset (a full `pandf(-1,-1)` on each worker) adds parallel full evaluations, which
  write `areapl`, `nfsp`, `TimingPandfOn` and `ttimpfe` (the `xc<0` timer) on workers. AIUE-60 makes all of them safe.
  AIUE-61's plan already defers the `areapl` question to AIUE-60.
- A6: AIUE-61 rewrites the `!$omp parallel do` directive; dropping `emcoef` from `copyin` there is a one-token change
  (results unchanged after AIUE-56) — suggested to AIUE-61, not done here.
- Merge order: AIUE-56, then AIUE-60 and AIUE-61 in either order.

## Notes / open questions
1. **Part B scope** (owner/reviewer): recommended in (same class as `areapl`, attribute-only, in the `pandf` tree). Gap:
   there is no double-null, limiter, coupled-wall-source or `istabon=5,6` case to show the races or the fix
   dynamically; validation is static (Probe S) plus "nothing changes" on the reproducer.
2. **A7 `isimpon=5`**: document and open a follow-up ticket (≈25 attributes + per-thread SAVE locals + a test case).
   Owner may instead prefer that the OpenMP Jacobian refuse `isimpon=5` with `xerrab` until then.
3. **RHS path**: `OMPinitialize_ranges2D` writes `nfsp` unconditionally (`ppp/omp_parallel.F90:831-832`). Same fix,
   but in AIUE-61's file and in the RHS path → proposed for AIUE-58.
4. **PETSc path** has the same clip-index bug (`svr/petsc-uedge.F90:682`, `sfscal(iv)`); not built here. Fix with a
   PETSc build, or note it in the PR.
5. **Other `jac_calc` vs `LocalJacBuilder` differences** (not races, not changed): the parallel builder subtracts
   `1/dtuse` on the diagonal for every `svrpkg` (serial only for `nksol`/`petsc`) and `nufak` also for `cvode`.
   For `nksol` (the only solver the reproducer and pytests use) they agree.
6. Observation from Probe C: the first (`sfsetnk`) Jacobian of each `exmain` is clipped with `sfscal = 1`, so in it
   `jaccliplim` acts as an absolute threshold. Not changed here; reported for the owner.
7. 8 threads not run (≤ 4 threads per process on the shared machine). Linux not run here (AIUE-57 CI).
