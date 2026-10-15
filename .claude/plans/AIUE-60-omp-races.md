# Feature: AIUE-60 — Fix the remaining OpenMP races in the `pandf` tree and the clip-index inconsistency

Validate the patterns and file references below before implementing. Line numbers are at `1553e75` (AIUE-56 tip).
Revised after plan reviews round 1 and 2 (`docs/reviews/AIUE-60-plan-round{1,2}.md`, responses in
`docs/reviews/AIUE-60-plan-round{1,2}-response.md`).

## Summary
**Type**: Bug fix (numerics/parallel; OpenMP build only)
**Complexity**: Low (code: `.v` attributes, one MPPL hunk, one `.F90` line), Medium (validation: TSan, flow, clip check)
**Default results**: Unchanged, bitwise, in the `--serial` build and in the OpenMP build with both switches 0 (argument
below). OpenMP Jacobian: unchanged at the default `jaccliplim=0`; with `jaccliplim>0` it changes to the serial pattern.
**Packages / files**: `bbb/bbb.v`, `com/com.v`, `aph/aph.v` (attributes only), `bbb/pandf.m` (`initialize_ranges`,
`nfsp`), `ppp/parallel.F90` (`LocalJacBuilder`, clip index), `.claude/context/openmp-jacobian.md`,
`.claude/context/variables-forthon.md`, `CLAUDE.md` (code facts), test tools in `docs/reviews/` (committed with this plan)
**Branch / worktree**: `bugfix/v9-AIUE-60-omp-races` @ `/Users/holma/Documents/uedge/src/uedge-wt/AIUE-60`
(base: `bugfix/v9-AIUE-56-omp-jacobian-fix` at `1553e75`, stacked; PR targets that branch until AIUE-56 merges)
**Follow-up ticket**: AIUE-69 (non-default paths: double-null x-point `ghxpt`, coupled wall sources, `isimpon=5`,
PETSc clip index)

## Amendment 1 (implementation review round 1, I1-B1): no threadprivate scalars outside `bbb`

**Problem.** Forthon's `--omp` generator gives every package's `OmpCopyScalar<pkg>` the same common block,
`common /ompcommonscalarcopy/ <that package's scalar copies>`, with `firstprivate(/ompcommonscalarcopy/)`.
- The extensions are loaded `RTLD_GLOBAL` in the order com, grd, flx, bbb, svr, wdf, api, aph, ppp
  (`src/uedge/__init__.py:21-33`), and they are flat-namespace bundles. So the first loaded definition of
  `_ompcommonscalarcopy_` serves every package.
- Before AIUE-60 only `bbbpy.so` (89 scalars, 712 B) and `apipy.so` (96 B, loaded later) defined it. The A4 timers made `compy.so`
  define an 80-byte block, and it loads first. So `OmpCopyScalarbbb` (now 91 scalars, 728 B) writes into it on every OpenMP Jacobian,
  past its end into `com`'s `/iotable/` (the reviewer's probe: 62 words changed).
- `iflag_aph` (B4) adds an 8-byte `aphpy.so` block. It is latent only because `aph` loads after `bbb`.

**Options considered.**
1. *Timers threadprivate, upstream fix.* Package-specific common names in Forthon's generator. This is out of this
   repo, so not now; a follow-up ticket is proposed (below).
2. *Timers move into `bbb`.* This changes the Python API (`com.ttimpjf` …) and the `wdf`/`api`/`aph` users. Rejected.
3. *Timers shared, accumulation skipped inside parallel regions* via `omp_in_parallel()`. In MPPL that needs an
   `external`/`logical` declaration in an OpenMP-only (`c!omp`) line. With `-fdefault-integer-8` a plain `logical`
   declaration is `logical(8)`, against `omp_lib`'s `logical(4)` return (ABI risk). It also drops the timing of all
   parallel work. Rejected.
4. **Timers shared, update made atomic (chosen).**
   - A new helper `acctim(acc, dt)` at the end of `com/misc.m` (after `tock`) does `acc = acc + dt` under a
     fixed-form OpenMP sentinel line `c$omp atomic`.
   - MPPL passes comment lines through unchanged (checked: `c ...` lines survive into `bbb/pandf.F`). gfortran with
     `-fopenmp` therefore compiles the directive, and the serial build sees a comment: the same `acc = acc + dt`.
   - Every A4 accumulation becomes `call acctim(<timer>, tock(<t>))` on the same line, so the change is line-neutral:
     `bbb/pandf.m:636,758,760`; `bbb/pandf_gas_continuity.m:664,765,777,876`; `com/comutil.m:3654,3902`;
     `aph/aphrates.m:596,773,1031`; `api/fmombal.m:248` (the `isimpon=5` path, blocked under OpenMP; converted for
     uniformity).
   - The 10 `com/com.v` lines go back to their original text: no `+threadprivate`, original doc strings.
   - Timers then sum thread-seconds exactly over threads under OpenMP and can exceed the elapsed time (before
     AIUE-60: lost updates). gcc instruments only the atomic's initial load for TSan, not the compare-and-swap, so
     TSan does not confirm atomicity. A lost directive would still show as a plain read/write race. Atomicity is
     checked statically instead (G-atomic, below).
   - **Exact helper text (LA1-m1)**, appended to `com/misc.m`. There is no `Use` line, because `MoveDecs` would move
     the declarations below the directive. The directive line stands directly before the assignment:
     ```
     c-----------------------------------------------------------------------
           subroutine acctim(acc, dt)
     c ... acc = acc + dt for the com timing accumulators (Timing, Timespl),
     c     which OpenMP threads share: the next line makes the update atomic
     c     in the OpenMP build and is a comment in the serial build (AIUE-60).
           implicit none
           real acc, dt
     c$omp atomic
           acc = acc + dt
           return
           end
     ```
5. **`iflag_aph` (B4): replaced by a local, not threadprivate.**
   - `rqa`, `rra` and `rsa` get a local `iflagl`, appended to their existing `integer nxcoef,nycoef` line
     (`aph/aphrates.m:433,641,897`), and pass it to `B2VAhL` instead of `iflag_aph` (`:570,595,749,772,1007,1030`).
     This is line-neutral.
   - `iflag_aph` is not read after these calls (`git grep`), so results are unchanged. The Python-visible
     `aph.iflag_aph` then reflects only the `aphread` setup calls (`aph/aphread.m:920-951`), not the rate
     evaluations. This is listed in the PR (LA1-m5).
   - `aph/aph.v:203` goes back to its original text. `workh` (an array: per-routine `pcopy__`, not the scalar common)
     stays `+threadprivate`, with the paren-free bound of `02e6e60`.

**Invariant (to record in `openmp-jacobian.md` and `variables-forthon.md` checklist 4, code-facts).**
- A `+threadprivate` **scalar** in package P adds a definition of the shared common `/ompcommonscalarcopy/`, sized by
  P's threadprivate scalars.
- The first definer in load order serves all packages. So **no package that loads before `bbb` (`com`, `grd`, `flx`)
  may define threadprivate scalars**, and **no later package's block (`api`, `aph`, `ppp`, …) may be larger than
  `bbb`'s**.
- Threadprivate arrays are not affected.
- New threadprivate scalars belong in `bbb`. AIUE-61 must check this if it adds any to `ppp.v`.

**New pre-registered gates (in addition to Testing 1–6, all re-run on the amended tree).**
- **G-common (static).** Script `docs/reviews/AIUE-60-common-check.py`. For each extension in the OpenMP venv, in
  load order:
  - whether it defines `_ompcommonscalarcopy_` (`nm -m`);
  - the block size from the generated `build/temp.*/<pkg>_p.F90` (the variables of its `common /ompcommonscalarcopy/`
    statement, joined over its `&` continuation lines, × 8 B; sizes checked at plan time: AIUE-56 `bbb` 89/712 B,
    `api` 12/96 B; pre-amendment AIUE-60 `bbb` 91/728 B, `api` 96 B, `com` 10/80 B, `aph` 1/8 B).

  The load order is parsed from the venv's `uedge/__init__.py` (`uedgeC`, `com`, `grd`, `flx`, `bbb`, `svr`, `wdf`,
  `api`, `aph`, `ppp`, `ncl`). Sizes come from the declared kinds of the `copy` variables (`<type>(kind=K)`). The
  generated-source directory is an argument and must belong to the same build. A definer without a size, or a
  missing `.so`, is an ERROR (fail closed). `nm -m` is macOS-only; the script uses `nm -S` on Linux (LA1-m2).
  **Pass:** the first definer in load order is `bbb`, and every other definer's block is ≤ `bbb`'s. Expected:
  definers exactly `bbb` (91 scalars, 728 B) and `api` (96 B); `com` and `aph` define none. It is also run on the
  AIUE-56 venv as a control (`bbb` 712 B, `api` 96 B: pass), and on the pre-amendment AIUE-60 venv as a negative
  control (`com` first, 80 B: fail).
  **Controls already run on preserved artefacts (LA1-M2)**, before any rebuild:
  - The pre-amendment venv was copied to `venvs/AIUE-60-omp-pre`, and its generated `*_p.F90` to
    `logs/AIUE-60/pre_amend_gen/`.
  - AIUE-56: `RESULT: PASS (first definer bbbpy 712 B; others apipy 96 B)`.
  - Pre-amendment: `RESULT: FAIL: first definer is compy (80 B), not bbbpy; bbbpy block 728 B > first definer compy
    80 B; apipy block 96 B > first definer compy 80 B`.
  - The outputs are recorded in `docs/reviews/AIUE-60-amendment1-controls.txt`.
- **G-iotable (dynamic).** The reviewer's probe, made robust to a missing `com` block, committed as
  `docs/reviews/AIUE-60-iotable-probe.py`. Te box, `jac` arm, 4 threads, `itermx=1` (≥ 2 OpenMP Jacobians).
  **Pass (differential, LA1-M1):** in each of 2 repeats, the amended AIUE-60 build's before- and after-states of all
  128 `iotable` words equal the AIUE-56 build's. The AIUE-56 build must be repeatable across its own repeats; if it
  isn't, the result is ERROR. A correct build legitimately changes words, because `exmain` opens files.
  - **Positive control, already run:** AIUE-56 changes exactly `{11: 0→1, 12: 0→1}`, identically in 2/2 repeats.
  - **Negative control, already run:** the preserved pre-amendment build changes 62 words in 2/2 repeats (`0→4`,
    `5: 0→4592291131226807497`, `9,10: 1→0`, `11: 0→70`, `12: 0→69`, …), so it differs from AIUE-56: `RESULT: FAIL`.
  - The outputs are recorded in `docs/reviews/AIUE-60-amendment1-controls.txt`.
- **TSan (Testing 5) after the amendment.** Same gate. The timer groups must stay absent. TSan shows only that no plain
  racing read/write remains; atomicity itself is shown by G-atomic. The pre-registered expectation for out-of-loop
  groups adds: no `ompcommonscalarcopy_` report located in `compy` or `aphpy`.
- **G-atomic (static, LA1-m1).** Two checks:
  - In the OpenMP build's generated `com/misc.F`, the line directly above `acc = acc + dt` is `c$omp atomic`.
  - `otool -tV` of the OpenMP `compy*.so`, routine `_acctim_`, shows a compare-and-swap loop (`cas`/`casal`, or
    `ldaxr`/`stlxr`). The serial build's `_acctim_` shows a plain load, add and store (`fadd`), with no CAS.
- **Probe S, updated expectations.** Reachable units 145 → **146** (`acctim` is new, LA1-m3). `shared-writes`
  161 → 147, with exactly the same 14 removals: the timer writes
  become `call acctim(...)` arguments, so the assignment scan no longer lists them. `passed-args`: `workh` and
  `iflag_aph` disappear; the timer variables now appear as `acctim` arguments (`com.Timing.*` and `com.Timespl.*`, 10
  entries), so 137 → 145; they are listed and classified as atomic updates in the validation record. Any other change fails.
- **Timing (report, flag > 10 %).** Interleaved full-problem `jac` runs at 4 threads, AIUE-56 and AIUE-60, K=5 each:
  the ratio of medians of the harness `elapsed_s`, so the cost of the atomics is visible. `totintrv`/`totb2val` and
  `ttimpfe`/`ttimpjf` are updated without an `istimingon` guard, so their atomics are on the spline hot path.
  **A flag (> 10 %) is reported to the owner as a decision** (accept, or guard the hot-path updates with
  `istimingon`); it doesn't block the ticket (LA1-m4).

**Follow-up ticket text proposed (Forthon / generated OpenMP copies).** "Forthon `--omp`
(`wrappergenerator_ompextension.py`):
(1) `OmpCopyScalar<pkg>` uses the same `common /ompcommonscalarcopy/` in every package. With `RTLD_GLOBAL` and
flat-namespace / ELF interposition, the first loaded definition serves all packages. A package that loads earlier and
has fewer threadprivate scalars makes later packages overflow the block (AIUE-60: `com` timers → `bbb` overwrote
`com`'s `/iotable/`). Fix: package-specific names (`ompcommonscalarcopy_<pkg>`), or module variables instead of a
common block.
(2) `ProcessDim`/`GetSize` take `S.split('(')[1].split(')')[0]`, the text between the first `(` and the next `(` or
`)`. So a nested `(` in a bound, such as `2*k*(n+1)`, truncates it and produces uncompilable copy routines.
Filed as **AIUE-71**.
Until fixed, UEDGE keeps the invariant in `openmp-jacobian.md` and checks it with `docs/reviews/AIUE-60-common-check.py`
(candidate for the AIUE-57 OpenMP CI job)."

**I1-m1 (stated).** B2 (`sputflxllim/rlim`) and B4 (`workh`) were never executed in a threaded run: no preset
enables limiter sputtering or `istabon=5/6`, and the `nwfits` data `istabon=5/6` needs isn't on this machine. They
are covered by Probe S, the build, the generated-code check (same `copyin(pcopy__)` per-thread allocation as the 500+
exercised `bbb` arrays) and `B2VAhL`'s write-before-read. The validation record and the PR state this as untested at
run time.

**I1-m2 (deviations recorded in the validation record).**
- (i) The plan's defaults gate (AIUE-56 bases) returns `INCOMPLETE` on tool policy: the base is not on
  `origin/v9-develop`. Every comparison agreed. The substitute complete gate uses `base-serial`/`base-omp` at `0fac655`.
  Reasoning: `0fac655` is an ancestor of `origin/v9-develop` and of `1553e75`, and the only product diff
  `0fac655..1553e75` is AIUE-56's `OMPJacBuilder` copy order, which runs neither in serial nor with both switches 0.
- (ii) After `02e6e60` the generated serial `aph_p.F90` and `aphpymodule.c` differ from the base in the text of
  `workh`'s bound. The two forms are arithmetically equal, and the array size is unchanged.

## Problem and solution

The AIUE-50 scan and the AIUE-55 RCA (`docs/rca/AIUE-8-omp-jacobian-nondeterminism.md` on the AIUE-62 branch,
§Shared-state scan F5–F7, F9–F10, F15–F16; §Refuted or minor hypotheses) left these items for AIUE-60. A static probe
made for this plan ("Probe S", below) found more races of the same kind on non-default model paths. Two of them (B2, B4)
are pure per-call scratch like `areapl` and are fixed here. The others move to AIUE-69 (Part C).

### Existing protection (cited, not changed)
`exmain`'s setup stops any OpenMP run (`ParallelJac>0` or `ParallelPandf1>0`) with `isimpon` other than 0, 2, 6 or 7,
with `ismcnon>0`, `ishosor>0`, `ispsorave>0`, or `cfvisxneoq`/`cfvisxneov≠0` (`xerrab`, "Roadblockers … added by
J.Guterl", `bbb/odesetup.m:6727-6770`). So `isimpon=3,4,5` and the Monte Carlo neutral coupling never run threaded.

### Part A — the ticket's items

| # | Item | Where (re-located) | What happens | Fix |
|---|---|---|---|---|
| A1 | `areapl` (F16) | decl `bbb/bbb.v:951` (`Rccoef`, `+work`); written at `bbb/pandf_boundary.m:3091,3166,3446,3544` (`left_boundary`) and `:3797,3882,4180,4277` (`right_boundary`), each followed by reads in the same block (`:3095`, `:3173,3179`, `:3453,3461`, `:3548`, `:3812`, `:3888,3894`, `:4188,4196`, `:4281`). No reader outside these blocks or in Python | shared scalar written and read by every thread whose box touches a plate: a race on physics state | `+threadprivate` |
| A2 | `TimingPandfOn` (F5) | decl `bbb/bbb.v:4136` (`PandfTiming`); written every call at `bbb/pandf.m:573-579`, read at `:580-598,713`, `bbb/oderhs.m:88,532`, and, without being set, in the parallel RHS at `ppp/omp_parallel.F90:1227,1232,1294` (`OMPPandf`/`OMPPandf_XPT`) | every thread writes it. It is 0 in every parallel context: `yl(neq+1)=1` in Jacobian columns and copies, and `ParallelPandf1=1` forces 0 for the full RHS (`bbb/pandf.m:573-574`) | `+threadprivate`. In the parallel RHS a worker reads its own copy (0 from its last column or from `OmpCopyScalarbbb`) instead of the master's (also 0): no change |
| A3 | `com.nfsp` (F7) | decl `com/com.v:28` (`Dim`); written every call at `bbb/pandf.m:50-51` (`initialize_ranges`) | every thread writes it, always the same value under OpenMP: the second assignment (`nhsp`) applies only to `isimpon=3,4`, which are documented as disabled (`bbb/bbb.v:3878-3879`) and blocked for OpenMP by the roadblock above | write only when the value changes (line-neutral MPPL hunk, below). Not `+threadprivate`: it is in `Dim` with the grid dimensions, and the RHS path writes it too (`ppp/omp_parallel.F90:831-832`, AIUE-58/59) |
| A4 | `com` timers (F6) | `Timing` (`com/com.v:502-521`): `ttimpfe`, `ttimpjf` (`bbb/pandf.m:758,760`, `timimpfj`), `ttnpg` (`bbb/pandf.m:636`), `ttngxlog`, `ttngylog`, `ttngfd2`, `ttngfxy` (`bbb/pandf_gas_continuity.m:664,765,777,876`), `ttimpc` (`api/fmombal.m:248`); `Timespl` (`com/com.v:564-567`): `totintrv` (`com/comutil.m:3654,3902`, `B2VAhL`/`B1VAhL`, reached from `emissbs`), `totb2val` (`aph/aphrates.m:596,773,1031`). Other readers: reset `bbb/odesolve.m:87-93` and print `:984-988`, master only | lost updates (TSan: 199 of the in-loop reports in AIUE-50) | **Superseded by Amendment 1:** the timers stay shared, and every update goes through the atomic `acctim` helper (no `+threadprivate`; the `com.v` lines are unchanged from `1553e75`). Under OpenMP the values are thread-seconds summed over threads. The inputs `istimingon`/`iprinttim` and the master-only `ttotfe`, `ttotjf`, `ttmatfac`, … are untouched |
| A5 | Clip index | serial `bbb/oderhs.m:1187`: `abs(jacelem*sfscal(ii))`; parallel `ppp/parallel.F90:292`: `abs(jacelem*sfscal(iv))`; debug print `:288` prints `sfscal(iv)` | `ii` is the row (equation), `iv` the perturbed variable (column). `sfscal` scales equations, so serial is right. Probe C: no effect at `jaccliplim=0`; at `1e-6` the OpenMP build keeps exactly the column-rule set (full problem: 812 962 entries differ from serial) | `sfscal(ii)` at `:292` and in the debug print `:288` |
| A6 | `emcoef` in `copyin` (F15) | `ppp/omp_parallel.F90:721` (`copyin(yinc,xlinc,xrinc,emcoef)`), `USE Imslwrk, ONLY: emcoef` `:654` | `copyin` pointer-assigns each worker's `emcoef` to the master's array, and that stays after the loop: from the second Jacobian on, `OmpCopyPointeremcoef` has 3 workers write the same values into the master's array (outside the column loop; benign). Inside the loop `emcoef` is only read | **Document, don't change here** (`openmp-jacobian.md`). Since AIUE-56 the `copyin` is redundant. Removing it touches the directive AIUE-61 rewrites, so it is offered to AIUE-61 (merge note) |
| A7 | `fmombal` SAVE arrays (F9, F10) | `api/fmombal.m:70` (`uresp`, `usave`, `caplams`), `:368` (`mrespond`), `:1064` (`zrespond`) | reached only via `mombal` for `isimpon=5` (`bbb/pandf_plasma_momentum.m:669-671,701-703`). Probe S: that path also writes 9 non-threadprivate `Reduced_ion_interface` arrays (`bbb/bbb.v:3937-3954`), the 12 `api` `Reduced_ion_variables` (`api/api.v:224-235`) and 4 `Reduced_ion_constants` scalars (`api/fmombal.m:536,774,819,1086`). `mombal` always passes `ldir=2` (`:1014`), so the SAVE arrays are per-call scratch that threads would overwrite | **Document; no code.** The roadblock already stops OpenMP with `isimpon=5` (`bbb/odesetup.m:6728-6737`). Making the path thread-safe is AIUE-69 |

### Part B — same-class races found by Probe S, fixed here (per-call scratch, attribute only)

| # | Variables | Written at | Path (default off) | Why `+threadprivate` is safe |
|---|---|---|---|---|
| B2 | `bbb.sputflxllim`, `sputflxrlim` (`bbb/bbb.v:986-987`, `Rccoef`) | `bbb/pandf_boundary.m:4957-4990,5041-5070` (`limiter_patch`), zeroed then accumulated per `iy`, then read in the same routine | `islimon≠0` with limiter sputtering | no reader outside `limiter_patch`; value never needed on another thread or across calls |
| B4 | `aph.workh`, `iflag_aph` (`aph/aph.v:210,203`, `Aphwrk`) | `B2VAhL` (work array, flag; `B2VAhL` sets `IFLAG=0` first) in `rqa`/`rra`/`rsa` (`aph/aphrates.m:569,594,748,771,1006,1029`) | `istabon=5,6` (spline hydrogen rates) | scratch written before read; the `api` analogue (`work2`, `iworki`, `icont`, `iflagi`) is already threadprivate (`api/api.v:154-160`). **Amendment 1:** only `workh` (an array) is threadprivate; `iflag_aph` is replaced by a local `iflagl` in `rqa`/`rra`/`rsa` |

Both arrays have bounds from shared `com` `Dim` scalars or non-threadprivate `aph` scalars, so no copy-order hazard
(AIUE-56). `workh` needs no copy; `aph` gets no `OmpCopy` call. Workers get their own `workh` buffer at allocation time
from the generated `aphsetarraypointerworkh` (the `copyin(pcopy__)` pattern of `apisetarraypointeremcoef`,
`build/temp.*/api_p.F90:1222-1257` in the AIUE-56 build); `InitOMPJac` uses `OMP_GET_MAX_THREADS()`, so the allocation
team covers the Jacobian team.

### Part C — not fixed here (AIUE-69 or existing roadblock), documented in `openmp-jacobian.md`

| Path | Shared state written in `pandf` | Why not `+threadprivate` here | Where |
|---|---|---|---|
| Full double null (`nxpt=2`) | `com.ghxpt`, `gvxpt`, `sxyxpt` (`com/com.v:427-429`), set to the lower, then the upper x-point values on every call (`bbb/pandf_plasma_momentum.m:298-306`), read in `fmihxpt`/`fmivxpt` (`:338-345`) | for single null they are geometry constants set at setup (`bbb/geometry.m:1019-1025`) and read in `pandf`; per-thread copies would go stale on the parallel-RHS workers (`OMPPandf1Rhs` never copies; `icntnunk=1`). Suggested fix for AIUE-69: select the values into locals in `calc_plasma_momentum` (`real ave` at `:180` has room for the declarations, so the change can be line-neutral) | AIUE-69 |
| Coupled wall sources (`iscpli`/`iscplo`=1) | `bbb.iwalli`, `iwallo`, `fngysi`, `fngyso` (`bbb/bbb.v:669-670,679,683`), in `wsmodi`/`wsmodo` (`bbb/pandf_boundary.m:574-715`) | `fngysi/fngyso` are set for every wall cell by `walsor` from the user's puff inputs at every `exmain` (`bbb/pandf_boundary.m:460-461,535-556`, `bbb/odesetup.m:1339`): per-thread copies would go stale (e.g. `rundt` with `icntnunk=1`) | AIUE-69 |
| `isimpon=5` (reduced ion) | see A7 | roadblock stops it | roadblock; AIUE-69 |
| Monte Carlo neutrals (`ismcnon≠0`) | `initialize_ismcnon` (`bbb/pandf_plasma_continuity.m:31-122`, rewrites `cfneut`, `cfvgpx`, …, `dtreal` by Jacobian/RHS mode), `bbb/ext_neutrals.m` (`MCN_*`, `PNC_*`, equation switches) | roadblock stops it | roadblock |
| MPI domain decomposition | `sendbdry` (`bbb/odesetup.m:5010-5021`) | not an OpenMP path | — |
| PETSc solver | same clip-index bug, `svr/petsc-uedge.F90:682` (`sfscal(iv)`) | not built here; not edited | AIUE-69, noted in the PR |

### Probes made for this plan

- **Probe S (static)**, committed as `docs/reviews/AIUE-60-shared-writes.py` (SHA-256 `6eeeacda…6b0b1d`, recovered
  from the session scratchpad after review L1-M3) and `docs/reviews/AIUE-60-passed-args.py` (`c8c8ce78…164f`).
  It lists every `.v` variable (all packages) that is assigned, or passed to `B2VAhL`/`B1VAhL`/`B3VAL`/a CALL, in the
  145 units reachable from `pandf`, minus threadprivate ones and locals, keeping only units that `Use` the group. It
  builds on the AIUE-50 `scan_saved_locals.py` call graph, which it reads from the AIUE-50 worktree. Before the fix:
  161 variables, all in Parts A–C, plus `ext_verbose`, the MC/PNC variables, and the `PandfTiming` accumulators gated by
  `TimingPandfOn` (never written in a parallel context, A2).
- **Probe C (clip)**: `docs/reviews/AIUE-60-clip-check.py` on the AIUE-56 OpenMP build, 4 threads, `jaccliplim=1e-6`.
  - The first (`sfsetnk`) Jacobian of an `exmain` is clipped with `sfscal = 1`. The smallest kept `|raw|` is exactly
    `1.000e-6`, so that Jacobian can't distinguish the rules. The `psetnk` Jacobian at Newton iteration 0 can (same
    state, `sfscal` from `sfsetnk`). The script uses it, with `itermx=1`, `isrnorm=0`, `ireorder=0` in both arms.
  - Te box: 0 entries where the rules differ, so it can't detect the bug and isn't used.
  - `ni`: predicted 69 401. Measured 55 897 + 13 504 = 69 401 one-sided entries. OpenMP nnz 594 104 = the predicted
    column-rule count.
  - Full problem: predicted 812 962. Measured 442 576 + 370 386 = 812 962. OpenMP nnz 2 402 093 = the column-rule count.
  - Common values and `sfscal` are bitwise equal to serial in both runs.
  - The G1 band (L1-M4 definition, below), re-evaluated offline on the same data: 16 717 of 636 497 serial `ni` entries
    (2.6 %) and 59 033 of 2 474 283 full entries (2.4 %) lie in it. The band is not small, because at large `suscal`
    the threshold `L/su(c)` is far below `τ·rowmax`. The AIUE-56 runs still give 62 006 (`ni`) and 734 080 (full)
    non-flips.
  - Run time: `ni` ~20 s and full ~50 s per OpenMP run.

## Why defaults stay bitwise unchanged

1. **`--serial` build.** Forthon emits `!$omp threadprivate` and the `OmpCopy*` routines only with `--omp`. The
   parser sets a flag (`interfaceparser.py:343-346`), not `v.attr`, and `wrappergenerator_ompextension.py` runs only
   with `--omp`; `setup.py` drops `--omp` for `--serial`. The generated Fortran is therefore identical; the doc-string
   edits change only the Python docs. `nfsp`: the new code leaves `nfsp` with the value the old code ended with, and
   nothing runs between the two old assignments. `LocalJacBuilder` is compiled but never called (`jac_calc_parallel` is
   reached only through a `c!omp` line, `bbb/oderhs.m:4697`).
2. **OpenMP build, both switches 0.** Only the master thread runs `pandf`. Its copy of a threadprivate variable
   behaves like the old shared variable, Python sees the master copy (as for the 522 existing `bbb` ones), and the
   arithmetic is unchanged. `LocalJacBuilder` is not called.
3. **OpenMP, `jaccliplim=0`, both arms.**
   - Every new threadprivate variable is written before it is read in the same call (A1, B2, B4), or is a timer, or is
     `TimingPandfOn`, which is 0 in every parallel context (A2). Neither the Jacobian loop nor the parallel RHS
     (`OMPPandf`, `OMPPandf_XPT`) depends on a value copied from the master. This is the reason B1/B3 were moved to
     Part C.
   - The clip test `abs(x*s) > 0` keeps the same entries for `s = sfscal(ii)` and `s = sfscal(iv)`, because `sfscal`
     is positive and finite (`sfsetnk` stops on a zero row, `bbb/oderhs.m:2349-2352`). The only exception would be an
     underflow of `x*s` to 0, which needs `|x| < ~1e-309`. The flow checks this empirically.
4. **Reported timers** (`com.ttimpjf` and the others in A4): *Amendment 1.* Under OpenMP they are thread-seconds
   summed over threads, through atomic updates. In serial the update is the same `acc = acc + dt` as before. This is
   diagnostic output, not a result, and is stated in `openmp-jacobian.md` and the PR. The `com.v` doc strings stay
   unchanged, because `com.v` returns to its `1553e75` text.

## Context references — read before implementing
- `bbb/bbb.v:819-821` (`xcnearlb … +threadprivate`) and `api/api.v:152-160` (threadprivate work arrays): patterns.
- `bbb/pandf.m:46-51` (`nfsp`), `:573-580` (`TimingPandfOn`), `:751-765` (`timimpfj`).
- `ppp/parallel.F90:280-299` (`LocalJacBuilder` debug print and storage), `bbb/oderhs.m:1180-1197` (serial storage).
- `ppp/omp_parallel.F90:678-699` (copy order), `:718-721` (the parallel directive, `copyin`), `:1000-1300` (parallel RHS).
- `bbb/odesetup.m:6727-6770` (OpenMP roadblocks).
- `.claude/context/openmp-jacobian.md` (rules 1–4), `.claude/context/variables-forthon.md` (attributes, checklist 4),
  `.claude/context/mppl-fortran.md` (fixed form, `#` comments; no `float`, `break`, `while (` tokens).

## Step-by-step tasks

### 1. UPDATE `bbb/bbb.v`, `aph/aph.v` — `+threadprivate` (A1, A2, B2, B4); A4 per Amendment 1
- **IMPLEMENT**: append `+threadprivate` after the type/default/existing attributes on these lines (same line, so no
  line moves): `bbb/bbb.v:951` (`areapl`, keep `+work`), `:4136` (`TimingPandfOn`), `:986-987` (`sputflxllim`,
  `sputflxrlim`); `aph/aph.v:210` (`workh`, with the paren-free bound). Add a short `#` doc to `TimingPandfOn` (none
  today). No units change.
- **Amendment 1 (supersedes the earlier `com.v`/`aph.v:203` part).** `com/com.v` and `aph/aph.v:203` keep their
  `1553e75` text: no threadprivate scalar outside `bbb`. A4 is done by the `acctim` helper and the 13 call-site
  rewrites, and `iflag_aph` by the `iflagl` locals, both as listed in Amendment 1.
- **PATTERN**: `work2(nwork2) _real +threadprivate # work array for B3VAL` (`api/api.v:156`).
- **GOTCHA**: keep the `.v` descriptions plain. Do **not** touch `com/com.v:427-429` or `bbb/bbb.v:669-670,679,683` (Part C).
- **VALIDATE**: OpenMP build; `grep -n 'threadprivate(areapl)\|threadprivate(sputflxllim)\|threadprivate(workh)' build/temp.*/{bbb,aph}_p.F90`
  finds each, and `grep -c 'threadprivate(ghxpt)\|threadprivate(fngysi)\|threadprivate(ttimpjf)\|threadprivate(iflag_aph)'`
  finds none; then G-common and G-atomic (Amendment 1); serial build:
  `grep -c threadprivate build/temp.*/*_p.F90` is 0 in every file.

### 2. UPDATE `bbb/pandf.m:48-51` — `nfsp` written only on change (A3)
- **IMPLEMENT** (line-neutral: 2 comment + 2 code lines replace 2 + 2):
  ```
  c ... Upper limit of species loops with ion sources/fluxes/velocities. nfsp (com
  c     Dim) is shared by OpenMP threads: write it only when it changes (AIUE-60).
        if ((isimpon.eq.3 .or. isimpon.eq.4) .and. nfsp.ne.nhsp) nfsp = nhsp
        if (isimpon.ne.3 .and. isimpon.ne.4 .and. nfsp.ne.nisp) nfsp = nisp
  ```
- **GOTCHA**: fixed form, code from column 7. The two code lines are 74 and 73 columns. That is fine:
  Forthon compiles fixed form with `-ffixed-line-length-132` (`Forthon/compilers.py:306`). The edit is line-neutral,
  so the `bbb/pandf.m:513`, `:535-544`, `:573-575` references in `CLAUDE.md` and the context stay valid.
  `OMPJacBuilder` runs a full `pandf` on the master before every parallel loop (`ppp/omp_parallel.F90:680`), so in the
  loop the condition is always false.
- **VALIDATE**: serial build; the serial check (below) covers it.

### 3. UPDATE `ppp/parallel.F90:288,292` — clip with the row's `sfscal` (A5)
- **IMPLEMENT**: `storage: if (abs(jacelem*sfscal(ii)) .gt. jaccliplim) then` and `sfscal(ii)` in the debug write. No
  new lines.
- **GOTCHA**: free form `.F90`. Touch nothing else in `LocalJacBuilder`: AIUE-61 edits its argument list, its
  declarations and the loop start.
- **VALIDATE**: OpenMP build; clip check (Testing 4).

### 4. Run Probe S and `scan_ompcopy.py` on the built tree
- `python -I docs/reviews/AIUE-60-shared-writes.py <tree> pandf` and `AIUE-60-passed-args.py <tree>`.
- **Numeric expectations (L2-m2).** Today the outputs list 161 and 137 variables (re-confirmed at `203a5ff`).
  - `shared-writes`: **161 → 147**. Exactly these 14 disappear: `areapl`, `sputflxllim`, `sputflxrlim`,
    `timingpandfon`, the 8 `com.Timing` entries and the 2 `com.Timespl` entries.
  - `passed-args`: **137 → 135**. Exactly `workh` and `iflag_aph` disappear.
  - The post-fix outputs are diffed against the pre-fix outputs (saved in the validation record). Any other added or
    removed line fails this check.
  - `nfsp` stays in the list: the probe still sees the guarded assignment.
- `scan_ompcopy.py` (AIUE-50, `tests/deterministic_omp/tools/`) on the AIUE-60 OpenMP build tree: 0 copy-order hazards.

### 5. UPDATE the AI layer (own commit, trailer `AI-layer: code-facts`)
- `.claude/context/openmp-jacobian.md`:
  - Rule 1: a scalar that every column recomputes to one value may instead be written only when it changes (`nfsp`).
    *(Amendment 1: rewrite the committed sentence "Threadprivate timers (`com.ttimpjf`, …) report the master thread
    only".)* The `com` timers are shared and updated atomically through `acctim` (`com/misc.m`), so under OpenMP they
    report thread-seconds summed over threads.
  - New invariant (Amendment 1): a threadprivate *scalar* adds a definition of the shared `/ompcommonscalarcopy/`.
    No package that loads before `bbb` may have one, and no later package's block may exceed `bbb`'s. Checked by
    `docs/reviews/AIUE-60-common-check.py`. The same invariant goes into `variables-forthon.md` checklist 4.
  - New bullet "Known OpenMP-unsafe paths": cite the roadblock `bbb/odesetup.m:6727-6770`. Also double null `ghxpt`,
    coupled wall sources, and the PETSc clip index (AIUE-69), with the A6 `emcoef` `copyin` note.
  - Jacobian bullet: the parallel clip uses the row's `sfscal`, as serial does. Note the remaining
    `jac_calc`/`LocalJacBuilder` differences: the diagonal `1/dtuse` is applied for every `svrpkg`, and `nufak` also
    for `cvode`; both are the same for `nksol`.
  - Warn against `+threadprivate` on values computed outside `pandf`: the parallel RHS never copies (the B1/B3 lesson).
- `CLAUDE.md:23` and `.claude/context/variables-forthon.md:48` (checklist 4): add "(or written only on change; see
  `openmp-jacobian.md` rule 1)" so the rule texts match the exception (L1-m3).
- `variables-forthon.md:37`: the `+threadprivate` count in `bbb.v` goes from 522 to 526 (A1, A2, B2).
- `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` clean (re-lock only re-read claims).

## Testing strategy (pre-registered)

Builds: `venvs/AIUE-60-omp` (this worktree) and `venvs/AIUE-60-serial` (detached tree
`../AIUE-60-serial` at the implementation commit), via `build_uedge.sh`. Base: `venvs/AIUE-56-omp`,
`venvs/AIUE-56-serial` (AIUE-56 fix `4fae2f9`; `1553e75` differs only in docs). Every run: fresh `python -I` process,
empty `HOME`, `OMP_STACKSIZE=512M`. Shared machine: ≤ 4 threads per process, ≤ 2 UEDGE processes at a time. Tool
commits and the Probe S hashes are recorded in `docs/reviews/AIUE-60-validation.txt`.

1. **Build hygiene**: both builds import; no new warnings in the touched files (`grep -a -i warning` in the build logs
   for `pandf.F`, `parallel.F90`, `*_p.F90`); the threadprivate greps of task 1.
2. **Defaults unchanged (hard rule)**: AIUE-53 `serial_check.py` (`feature/v9-AIUE-53-serial-bitwise-check`),
   `--base-python AIUE-56-serial --new-python AIUE-60-serial --base-omp-python AIUE-56-omp --new-omp-python AIUE-60-omp
   --cases all --jobs 2`. **Gate: `RESULT: AGREE` (complete gate), exit 0.** Plus upstream pytests `D_only` with both
   AIUE-60 builds: pass.
3. **OpenMP results unchanged or closer to serial, both arms.** Use the AIUE-52 flow from the reviewed harness:
   `/Users/holma/Documents/uedge/src/uedge-wt/AIUE-57/tests/deterministic_omp/harness/cli.py flow --all --arms jac,jacrhs --threads 2,4 --repeats 2 --max-jobs 2 --gate none`.
   Run it for `AIUE-56-omp` and `AIUE-60-omp`, one after the other. The gates are judged per run and per section
   (`flow.json`: every comparison report with its `sections`), not on group verdicts or merged equation sets (L2-M1).
   - **Classes, fixed in advance from AIUE-56 evidence, not from this flow's outcome.**
     - **Class X** (`ti`, `ni`, `up`, `ng`) was bitwise in every recorded run (L3-m3 attribution):
       - AIUE-56 `jac` at 4 threads, 5/5 per preset (`AIUE-56-validation.txt:17-20`);
       - the base-build controls, 3/3 (`:25-28`);
       - AIUE-54's `k2_all` flow on the base build, 2/2 at 2/4/8 threads on both arms
         (`AIUE-54/docs/rca/AIUE-8-data/records/k2_all/flow_summary.md`);
       - the AIUE-58 probes on AIUE-56: `ni`/`up`/`ng` equal in every step, `ti` equal at `yl0`.

       For AIUE-56 at 2 threads and on `jacrhs`, the support is the base-build data plus those probes. If the class is
       wrong anywhere, the mechanical fallback below catches it.
     - **Class Y** (`tebox`, `full`, `te`, `phi`=`te_phi`) carries the C2 residual in Te rows, which is only
       intermittently bitwise (`AIUE-56-validation.txt`: Te box 1/5 and 1/30, full 2/5 and 0/30, `te`/`te_phi` 0/5).
   - **Section families.**
     - Jacobian sections: `jacobian:*`.
     - RHS sections: `yldot`, `yldot_probe`, `sfscal`, `suscal`, `fnrm_final`, `fnrm_printed`. The harness's ±0 rule
       for parallel-RHS vectors stays in force.
   - **Gates. Every AIUE-60 run must satisfy all of these, on both arms:**
     - (a) **Class X, every section:** bitwise equal to serial and to the group's other runs, i.e. group PASS.
     - (b) **Class Y, Jacobian sections:** every mismatch lies in a Te row (C2).
     - (c) **Class Y, Jacobian sections:** the AIUE-56 C1-gate bounds hold on every one-evaluation run
       (`docs/reviews/AIUE-56-c1-gate.py`: Te-row max ≤ 10 × serial; every deviation ≤ 1e-6 × serial row max).
       The gate script reads a directory holding `serial/` and `run*/`, so `docs/reviews/AIUE-60-flow-gates.py` stages
       one per group with symlinks (`serial` → `<config>/serial`, `run<k>` → `<config>/<arm>_t<n>/run<k>`) and runs it
       there.
     - (d) **Every class, RHS sections:** bitwise equal to serial in every run.
       - On `jac` this is a property of the serial RHS, the scaling and the solver.
       - On `jacrhs` it holds on AIUE-56 for one-evaluation runs: Te box and full K=5, all agreeing in
         `AIUE-56-validation.txt`, and AIUE-58 RCA "Why the earlier RHS checks were green". R1 needs a state change,
         and R2/R3 need an input change or a second `exmain`, none of which a one-evaluation run has.
       - (d) is checked **per section**. A new Te-row mismatch in `yldot` or `yldot_probe`, for example from the plate
         BCs that read `areapl`, therefore fails even in a group whose Jacobian sections carry C2 in Te rows. This closes
         the blind spot of the old equation-set gate (e).
     - (f) No run fails by a crash, timeout or UEDGE error on AIUE-60 unless the same group/arm/threads also did on
       AIUE-56 in this flow.
   - **Mechanical fallback (fixed in advance).** If an AIUE-56 run in this flow itself violates (a) or (d) for a group
     and section, AIUE-56 has shown that the property is intermittent there. For that group and section, AIUE-60 is then
     judged by the re-run rule below instead of (a)/(d).
   - **Re-run rule (L3-m1).** Any group that fails (a)–(d) or (f), or is marked RERUN by the fallback, is re-run at K=5
     on **both** builds, with the same configuration, arm and thread count, one build after the other. Let
     n₆₀ and n₅₆ be the numbers of re-runs that violate the property. Then:
     - n₆₀ − n₅₆ ≥ 2: **confirmed regression**. A deterministic regression (5 vs 0) always confirms.
     - n₆₀ − n₅₆ = 1: tie-break. Re-run K=10 more on both builds; a **confirmed regression** if AIUE-60 violates the
       property in more of those 10 runs than AIUE-56.
     - Otherwise: recorded as pre-existing, with all counts.

     Each confirmed regression fails the acceptance criterion.
   - **Why false failures are unlikely.** Each gate rests on a property that held in every recorded run of the same
     kind:
     - (a) and (d): bitwise in 5/5, 3/3, K=2 and K=5 samples;
     - (b) and (c): held in all 110 C1-gated AIUE-56 one-evaluation runs;
     - (f): no AIUE-56 crash in one-evaluation runs.

     So no gate depends on which way an intermittent baseline group fell. If a property is intermittent at the same
     rate q on both builds, a margin of ≥ 2 at K=5 is a false confirmation with probability 0.003 at q = 0.02 and
     0.05 at q = 0.1 (round-3 table). The tie-break adds K=10 at a margin of 1. False confirmation is not impossible;
     the rule errs toward failing, which is the safe direction for a race fix.
   - Reported, not gated: the counts of runs agreeing with serial per group, and group verdicts.
   - 8 threads are not run (machine rule); this is stated as a gap.
   - **Cross-build bitwise (deterministic configuration):** `cli.py check --preset tebox --arm jac --threads 4 --repeats 2
     --ppp '{"OMPJacNchunks": -1, "OMPAutoBalance": 0}'` for both builds. With contiguous chunks the runs are identical to
     each other (RCA). Then `cli.py compare` AIUE-56 run0 vs AIUE-60 run0. **Gate: AGREE** (the change doesn't alter
     arithmetic).
   - The same check is run on the `jacrhs` arm. It is gated as AGREE only if both builds show run0 = run1 (then it is
     deterministic); otherwise it is report-only and stated.
4. **Clip, `jaccliplim>0`**: `docs/reviews/AIUE-60-clip-check.py check --python AIUE-60-omp --base-python AIUE-56-omp
   --clip 1e-6 --threads 4`, presets `ni` (`--repeats 3 --strict`) and `full` (`--repeats 2`, not strict). Precondition,
   met by Probe C: `rules_differ` > 0 for both presets. **Gates:**
   - **G1**: every one-sided entry of an AIUE-60 OpenMP run is a threshold flip,
     `| |J(r,c)| − L/suscal(c) | ≤ τ_eff(r)·max_c'|J(r,c')|`, computed on the side that holds the entry, with τ = 1e-8
     and a per-row `τ_eff(r) = τ + |sfscal_omp(r)/sfscal_serial(r) − 1|` (L3-m2: one row's `sfscal` change doesn't
     widen another row's band).
     - **τ is an observed value, not a bound.** The largest C2 deviation seen in AIUE-56 is 7.15e-9 × row max (`te_phi`).
       When `sfscal` differs, the distance to the threshold also gains the relative `sfscal` change, which is why that
       term is added. Together this can reach about 1.4e-8 × row max.
     - **`ni` (`--strict`, a class-X preset with no C2):** τ_eff is used, and in addition a run whose common values and
       `sfscal` are bitwise equal to serial must have **0 one-sided entries**. Expected: 0.
     - **`full` (C2 preset; the strict rule is not applied):** a straddling C2-perturbed entry can be one-sided while the
       common values stay bitwise, because the C2 entries may all be clipped at L = 1e-6.
       - A run with non-flips under τ_eff gets the verdict "PASS (C2 tolerance)" if **every** non-flip lies in a Te row
         and within 1e-6 × row max of the threshold (the AIUE-56 C1-gate bound, the same tolerance gate 3(c) uses).
       - Anything else is FAIL. The old column rule fails this decisively: it gives non-flips in every equation, up to
         1 × row max (Probe C: 734 080, worst 0.999999 × row max).
       - "PASS (C2 tolerance)" counts as a pass and is reported with the number of such entries.
     - The band population (Probe C: 2.4–2.6 % of entries) is reported per run.
     - The script records the Te rows from the harness equation map.
   - **G2 (report only)**: `sfscal` differences between serial and OpenMP. `sfscal` comes from the `sfsetnk` Jacobian,
     which C2 round-off may change. Each side's `bbb.jac` is scaled by its own `sfscal`, so the G1 test stays
     consistent within each side, and the run is judged by G1 with the band rule. `suscal` must be bitwise equal; if it
     isn't, the script exits 2 (not comparable). Such a run is re-run once, and if it persists it is reported as a
     harness error, never as a G1–G4 result.
   - **G3**: `g1_verdict(base run) == "FAIL"` for every AIUE-56 OpenMP run, with the same strictness and tolerance as G1
     (L3-m2). This is the negative control that shows the case detects the old rule; Probe C found 62 006 and 734 080
     non-flips. The round-3 observation applies: the C2-tolerance escape is ~100 × τ wide, and the control bites
     because the clip defect hits every equation.
   - **G4**: the AIUE-56 and AIUE-60 serial clipped Jacobians are bitwise equal.
5. **TSan, before/after** (procedure of AIUE-50, `tsan_summary.py` on `feature/v9-AIUE-50-shared-state-scan`):
   - Two scratch detached trees: `../AIUE-60-tsan-pre` at `1553e75` and `../AIUE-60-tsan` at the implementation commit;
     in each, an **uncommitted** scratch edit adds `-fsanitize=thread` to `FLAGS['FARGS']` in `setup.py`; build with
     `build_uedge.sh <tree> venvs/AIUE-60-tsan[-pre] omp`.
   - Runs at 4 threads, with
     `DYLD_INSERT_LIBRARIES=/opt/homebrew/opt/llvm/lib/clang/23/lib/darwin/libclang_rt.tsan_osx_dynamic.dylib` and
     `TSAN_OPTIONS="log_path=<dir>/tsan halt_on_error=0"`, through the harness `cli.py run --arm jac --threads 4` (its
     runner keeps these variables; it filters only `OMP_/GOMP_/KMP_/PYTHON*`). Presets:
     - `tebox`: the `emissbs` timers;
     - `ng`: the gas plate BCs, which reach the `areapl` site `:3446`;
     - `full`, if memory allows (expected ~5–10 × 1.4 GB; one run at a time);
     - `tebox` with `--itermx 2`: two Jacobians, so the A6 `emcoef` copy race shows outside the loop.
   - Summary per build: `python -I tsan_summary.py <dir>/tsan.*`.
   - **Gate (after):** no report group with "in Jacobian loop = yes" on a global symbol. An in-loop heap/stack group is
     allowed only if the other access is outside any parallel region (the AIUE-50 false positive: a numpy array the
     master writes before the region). Each such group is classified in the validation record.
   - **Expected before (negative control):** in-loop groups for `ttimpjf`, `totintrv`, `ttngxlog`, `ttngfd2`,
     `ttngylog`, `ttngfxy`, `ttnpg`, `TimingPandfOn` and `nfsp`, and for `areapl` on `ng`/`full`.
   - Reports outside the loop (copy routines, `emcoef`) are listed, not gated.
   - **Unexpected in-loop global-symbol group (L1-m4), pre-registered rule.** It fails the TSan gate. It is classified
     with the Probe S method. If it is a per-call scratch variable of the A/B kind, the fix is proposed to the main
     session as a plan amendment (re-reviewed) before it is applied. Anything else (state set outside `pandf`, or a
     larger change) stays a recorded failure of this criterion, with a follow-up named in the PR. It is never
     reclassified as benign after the fact.
6. **Static**: Probe S after the fix and `scan_ompcopy.py` (task 4).

## AI-layer facts affected
- `.claude/context/openmp-jacobian.md` (task 5).
- `CLAUDE.md:23` and `variables-forthon.md:48`: the pointer to the `nfsp` exception (L1-m3).
- `variables-forthon.md:37`: the count, 522 → 526.
- `CLAUDE.md` cites `bbb/pandf.m:513,535-544,573-575,31` and `bbb/bbb.v:1629,1622,217-222,236,279,331,336,33-41`.
  Task 2 is line-neutral, and the `.v` edits add attributes on existing lines, so none of these moves.
- `physics-models.md` (impurities row) and `architecture.md` mention `fmombal` only as a file: unchanged.
- Run `check_context_refs.py --changed origin/v9-develop` after the code commit to confirm.

## Validation commands
`validate` skill (suites: `D_only`; `--omp` OpenMP check: the flow above), plus Testing 1–6.

## Acceptance criteria
- [ ] Builds without new warnings in touched files; threadprivate directives present (OpenMP) and absent (serial)
- [ ] AIUE-53 serial check AGREE, complete gate, both pairs; `D_only` passes in both builds
- [ ] Flow gates 3(a)–(d), (f) per run and section, no confirmed regression after the re-run rule; the cross-build
      bitwise AGREE on `jac` (and on `jacrhs` if it is deterministic)
- [ ] Clip check: G1 PASS on `ni` (strict), PASS or "PASS (C2 tolerance)" on `full`; G3 and G4 PASS; G2 reported
- [ ] TSan after: no global-symbol race in the Jacobian loop; before shows the listed groups
- [ ] Probe S after the fix (Amendment 1): 146 reachable units; 147 and 145 entries, exactly the listed changes;
      `scan_ompcopy.py` 0 hazards
- [ ] Amendment 1: G-common PASS; G-iotable PASS (differential vs AIUE-56); G-atomic PASS; no `ompcommonscalarcopy_`
      TSan report in `compy`/`aphpy`; timing ratio reported (flag → owner)
- [ ] AI-layer edits of task 5 (`AI-layer: code-facts`); drift check clean
- [ ] Not this ticket's acceptance: the Linux M3 `up`-row residual (AIUE-65); AIUE-62 already saw that making `areapl`
      threadprivate doesn't remove it

## Merge order and note for AIUE-61 (`bugfix/v9-AIUE-61-omp-static-partition`, plan `4dea642`)
- **AIUE-60 lands first. AIUE-61 then rebases onto AIUE-60 and re-runs its gates on the combined tree** (AIUE-61's plan
  says the same, `:29-31,303`). Reason: AIUE-61's per-chunk reset (a full `pandf(-1,-1)` on each worker) adds
  parallel full evaluations, which write `areapl`, `nfsp`, `TimingPandfOn` and `ttimpfe` (the `xc<0` timer) on workers.
  AIUE-60 makes all of these safe, so AIUE-61's determinism gates are measured on race-free code.
- Textual overlap:
  - AIUE-61 edits `ppp/ppp.v`, `ppp/omp_parallel.F90` (`InitOMPJac`, `jac_calc_omp`, `OMPJacBuilder`) and, in
    `LocalJacBuilder`, the argument list (`ppp/parallel.F90:159-160,185`), the loop start (`:211`) and the storage
    target (heap fix).
  - AIUE-60 touches `ppp/` only at `ppp/parallel.F90:288,292`. Expected: a clean rebase. If the heap fix rewrites the
    `storage:` block, keep AIUE-61's target arrays and AIUE-60's `sfscal(ii)`.
  - `openmp-jacobian.md` and `.claude/context/refs.lock.json` will conflict textually in AIUE-61's rebase: keep both
    sets of bullets, then re-lock with `check_context_refs.py` after re-reading the cited lines.
- A6: AIUE-61 rewrites the `!$omp parallel do` directive. Dropping `emcoef` from `copyin` there is a one-token change
  (results unchanged after AIUE-56). It is suggested to AIUE-61, not done here.

## Notes (round-1 resolutions)
1. Part B scope: B2 and B4 in; B1 and B3 moved to AIUE-69 (Part C) because per-thread copies of values computed outside
   `pandf` would go stale on the parallel-RHS workers.
2. `isimpon=5`: no new guard. The existing roadblock (`bbb/odesetup.m:6728-6737`) already stops OpenMP runs with it.
   It is documented, and AIUE-69 owns the fix.
3. The RHS-path `nfsp` write (`ppp/omp_parallel.F90:831-832`) goes to AIUE-58/59.
4. PETSc clip index (`svr/petsc-uedge.F90:682`): not edited; noted in the PR; AIUE-69.
5. Other differences between `jac_calc` and `LocalJacBuilder` (diagonal `1/dtuse` for every `svrpkg`, `nufak` also
   for `cvode`): out of scope, recorded in `openmp-jacobian.md`.
6. Probe C observation, reported to the owner: the first (`sfsetnk`) Jacobian of each `exmain` is clipped with
   `sfscal = 1`, so in it `jaccliplim` acts as an absolute threshold. Not changed.
7. 8 threads and Linux are not run here: stated gaps (machine rule; AIUE-57 CI).
