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
| A4 | `com` timers (F6) | `Timing` (`com/com.v:502-521`): `ttimpfe`, `ttimpjf` (`bbb/pandf.m:758,760`, `timimpfj`), `ttnpg` (`bbb/pandf.m:636`), `ttngxlog`, `ttngylog`, `ttngfd2`, `ttngfxy` (`bbb/pandf_gas_continuity.m:664,765,777,876`), `ttimpc` (`api/fmombal.m:248`); `Timespl` (`com/com.v:564-567`): `totintrv` (`com/comutil.m:3654,3902`, `B2VAhL`/`B1VAhL`, reached from `emissbs`), `totb2val` (`aph/aphrates.m:596,773,1031`). Other readers: reset `bbb/odesolve.m:87-93` and print `:984-988`, master only | lost updates (TSan: 199 of the in-loop reports in AIUE-50) | `+threadprivate` on these 10 accumulators only. Not on the inputs `istimingon`/`iprinttim` and not on the master-only `ttotfe`, `ttotjf`, `ttmatfac`, … (written outside the parallel regions). With OpenMP the reported values then count the master thread only: say so in each doc string |
| A5 | Clip index | serial `bbb/oderhs.m:1187`: `abs(jacelem*sfscal(ii))`; parallel `ppp/parallel.F90:292`: `abs(jacelem*sfscal(iv))`; debug print `:288` prints `sfscal(iv)` | `ii` is the row (equation), `iv` the perturbed variable (column). `sfscal` scales equations, so serial is right. Probe C: no effect at `jaccliplim=0`; at `1e-6` the OpenMP build keeps exactly the column-rule set (full problem: 812 962 entries differ from serial) | `sfscal(ii)` at `:292` and in the debug print `:288` |
| A6 | `emcoef` in `copyin` (F15) | `ppp/omp_parallel.F90:721` (`copyin(yinc,xlinc,xrinc,emcoef)`), `USE Imslwrk, ONLY: emcoef` `:654` | `copyin` pointer-assigns each worker's `emcoef` to the master's array, and that stays after the loop: from the second Jacobian on, `OmpCopyPointeremcoef` has 3 workers write the same values into the master's array (outside the column loop; benign). Inside the loop `emcoef` is only read | **Document, don't change here** (`openmp-jacobian.md`). Since AIUE-56 the `copyin` is redundant. Removing it touches the directive AIUE-61 rewrites, so it is offered to AIUE-61 (merge note) |
| A7 | `fmombal` SAVE arrays (F9, F10) | `api/fmombal.m:70` (`uresp`, `usave`, `caplams`), `:368` (`mrespond`), `:1064` (`zrespond`) | reached only via `mombal` for `isimpon=5` (`bbb/pandf_plasma_momentum.m:669-671,701-703`). Probe S: that path also writes 9 non-threadprivate `Reduced_ion_interface` arrays (`bbb/bbb.v:3937-3954`), the 12 `api` `Reduced_ion_variables` (`api/api.v:224-235`) and 4 `Reduced_ion_constants` scalars (`api/fmombal.m:536,774,819,1086`). `mombal` always passes `ldir=2` (`:1014`), so the SAVE arrays are per-call scratch that threads would overwrite | **Document; no code.** The roadblock already stops OpenMP with `isimpon=5` (`bbb/odesetup.m:6728-6737`). Making the path thread-safe is AIUE-69 |

### Part B — same-class races found by Probe S, fixed here (per-call scratch, attribute only)

| # | Variables | Written at | Path (default off) | Why `+threadprivate` is safe |
|---|---|---|---|---|
| B2 | `bbb.sputflxllim`, `sputflxrlim` (`bbb/bbb.v:986-987`, `Rccoef`) | `bbb/pandf_boundary.m:4957-4990,5041-5070` (`limiter_patch`), zeroed then accumulated per `iy`, then read in the same routine | `islimon≠0` with limiter sputtering | no reader outside `limiter_patch`; value never needed on another thread or across calls |
| B4 | `aph.workh`, `iflag_aph` (`aph/aph.v:210,203`, `Aphwrk`) | `B2VAhL` (work array, flag; `B2VAhL` sets `IFLAG=0` first) in `rqa`/`rra`/`rsa` (`aph/aphrates.m:569,594,748,771,1006,1029`) | `istabon=5,6` (spline hydrogen rates) | scratch written before read; the `api` analogue (`work2`, `iworki`, `icont`, `iflagi`) is already threadprivate (`api/api.v:154-160`) |

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
4. **Reported timers** (`com.ttimpjf` and the others in A4) count only the master thread in an OpenMP run. That is
   diagnostic output, not a result, and is stated in the doc strings and the PR.

## Context references — read before implementing
- `bbb/bbb.v:819-821` (`xcnearlb … +threadprivate`) and `api/api.v:152-160` (threadprivate work arrays): patterns.
- `bbb/pandf.m:46-51` (`nfsp`), `:573-580` (`TimingPandfOn`), `:751-765` (`timimpfj`).
- `ppp/parallel.F90:280-299` (`LocalJacBuilder` debug print and storage), `bbb/oderhs.m:1180-1197` (serial storage).
- `ppp/omp_parallel.F90:678-699` (copy order), `:718-721` (the parallel directive, `copyin`), `:1000-1300` (parallel RHS).
- `bbb/odesetup.m:6727-6770` (OpenMP roadblocks).
- `.claude/context/openmp-jacobian.md` (rules 1–4), `.claude/context/variables-forthon.md` (attributes, checklist 4),
  `.claude/context/mppl-fortran.md` (fixed form, `#` comments; no `float`, `break`, `while (` tokens).

## Step-by-step tasks

### 1. UPDATE `bbb/bbb.v`, `com/com.v`, `aph/aph.v` — `+threadprivate` (A1, A2, A4, B2, B4)
- **IMPLEMENT**: append `+threadprivate` after the type/default/existing attributes on these lines (same line, so no
  line moves): `bbb/bbb.v:951` (`areapl`, keep `+work`), `:4136` (`TimingPandfOn`), `:986-987` (`sputflxllim`,
  `sputflxrlim`); `com/com.v:506,508,514,517-521` (`ttimpfe`, `ttimpjf`, `ttimpc`, `ttnpg`, `ttngxlog`, `ttngylog`,
  `ttngfd2`, `ttngfxy`), `:566-567` (`totb2val`, `totintrv`); `aph/aph.v:203,210` (`iflag_aph`, `workh`). Extend each
  A4 doc string with `; OpenMP: master thread only`. Add a short `#` doc to `TimingPandfOn` (none today). No units
  change.
- **PATTERN**: `work2(nwork2) _real +threadprivate # work array for B3VAL` (`api/api.v:156`).
- **GOTCHA**: keep the `.v` descriptions plain. Do **not** touch `com/com.v:427-429` or `bbb/bbb.v:669-670,679,683` (Part C).
- **VALIDATE**: OpenMP build; `grep -n 'threadprivate(areapl)\|threadprivate(ttimpjf)\|threadprivate(sputflxllim)\|threadprivate(workh)' build/temp.*/{bbb,com,aph}_p.F90`
  finds each, and `grep -c 'threadprivate(ghxpt)\|threadprivate(fngysi)'` finds none; serial build:
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
    Threadprivate timers report the master thread only.
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
     - **Class X** (`ti`, `ni`, `up`, `ng`) was bitwise in every recorded AIUE-56 run: `jac` 5/5 at 4 threads, the
       `base-omp` controls 3/3, and AIUE-52 PASS at 2/4/8 threads. The AIUE-58 probes at `yl0` were equal for these
       presets.
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
   - **Re-run rule.** Any group that fails (a)–(d) or (f) is re-run at K=5 on **both** builds, with the same
     configuration, arm and thread count, one build after the other. The failure is a **confirmed regression** only if
     the violated property fails in more AIUE-60 re-runs than AIUE-56 re-runs. Otherwise it is recorded as
     pre-existing, with both counts. Each confirmed regression fails the acceptance criterion.
   - **Why false failures are unlikely.** Each gate rests on a property that held in every recorded AIUE-56 run of the
     same kind:
     - (a) and (d): bitwise in 5/5, 3/3, K=2 and K=5 samples;
     - (b) and (c): held in all 70+ AIUE-56 one-evaluation runs, with C1 gate PASS throughout;
     - (f): no AIUE-56 crash in one-evaluation runs.

     So no gate depends on which way an intermittent baseline group fell. A false failure would need an event never
     observed on AIUE-56, and the re-run rule then compares rates on both builds, so a single unlucky run can't fail
     the ticket.
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
     `| |J(r,c)| − L/suscal(c) | ≤ τ_eff·max_c'|J(r,c')|`, computed on the side that holds the entry, with
     `τ_eff = τ + sfscal_max_rel_diff` of the run and τ = 1e-8.
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
   - **G3**: every AIUE-56 OpenMP run has non-flip differences. This is the negative control that shows the case detects
     the old rule; Probe C found 62 006 and 734 080.
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
- [ ] Probe S after the fix: 147 and 135 entries, exactly the listed removals; `scan_ompcopy.py` 0 hazards
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
