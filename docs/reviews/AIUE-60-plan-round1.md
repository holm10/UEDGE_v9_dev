# AIUE-60 plan review, round 1

Reviewed: `.claude/plans/AIUE-60-omp-races.md` and `docs/reviews/AIUE-60-clip-check.py` at `d2fac6e`
(branch `bugfix/v9-AIUE-60-omp-races`, stacked on `1553e75`). Reference: the ticket scope and acceptance criteria quoted
in the plan, the AIUE-8 RCA (§Shared-state scan, on the AIUE-62 branch), and the AIUE-61 plan at `4dea642`.

## Verdict

**REVISE**

## Summary

Part A is sound. `areapl` and the timers are safe as `+threadprivate`: there is no reader outside `pandf` or in Python,
and `areapl` is written before every read. The `nfsp` write-on-change leaves the value identical in serial. The clip
fix matches `jac_calc`, and the serial and "both switches 0" bitwise arguments hold (Forthon keeps `threadprivate` out of
`v.attr`, and the serial build has 0 `threadprivate` lines). The problems are in Part B and the validation:

- Two Part-B items (B1 `ghxpt/gvxpt/sxyxpt`, B3 `fngysi/fngyso`) turn values computed **outside** `pandf` (geometry,
  `walsor` from the user's gas-puff inputs) into per-thread copies. The parallel RHS never refreshes those copies.
- The `jacrhs` arm that runs this code on workers is explicitly left out of the flow.
- The Probe S script the plan cites is not at the cited path.
- The G1 tolerance of the clip check is not derived in the scale its justification uses.
- The merge note allows "either order" with AIUE-61, so the combined tree would never be validated.

## Findings

### BLOCKER

None.

### MAJOR

**L1-M1: B1 and B3 make inputs computed outside `pandf` copy-dependent on worker threads, and the parallel RHS never copies.**
Location: plan Part B (B1, B3) and "Why defaults stay bitwise unchanged" item 3.

- `ghxpt/gvxpt/sxyxpt` are set by `bbb/geometry.m:1019-1025` at setup. `pandf` writes them only for `nxpt=2`
  (`bbb/pandf_plasma_momentum.m:298-306`). For the common single-null case they are read-only geometry constants
  today.
- `fngysi/fngyso` are set for every wall cell by `walsor` (`bbb/pandf_boundary.m:460-461,535-556`), which runs in
  `ueinit` at every `exmain` (`bbb/odesetup.m:1339`) and uses the user's puff inputs `igasi/igaso`. `pandf` writes
  them only in `wsmodi/wsmodo` for coupled cells (`:633,703`).

With `+threadprivate`, a worker sees these values only through `OmpCopyScalarcom` and `OmpCopyPointerbbb` in
`OMPJacBuilder`. `.claude/context/openmp-jacobian.md` already states that `OMPPandf1Rhs` never copies and runs on what
the last Jacobian copy left, including with `icntnunk=1` or an RHS call from Python after an `exmain`. Two scenarios
follow:

- A user changes `igaso` and continues with `icntnunk=1`. `rundt` sets `icntnunk=1` routinely
  (`src/uedge/rundt.py:685,696,956`). Under `OMPParallelPandf1=1`, the worker chunks then evaluate the wall BCs with the
  old puff until the next Jacobian.
- `OMPCopyScalar=0` gives `ghxpt=0` on the workers for single null.

Today both values are shared, so the workers read the master's current value. The race B1 removes exists only for
`nxpt=2`, and the race B3 removes exists only for coupled wall sources. The attribute approach buys those two
non-default cases at the price of a new staleness hazard on default paths (single null, uncoupled puffs) in the RHS
arm. The "unchanged" argument in item 3 covers the Jacobian loop only.

Resolution, either of:

1. Drop B1 and B3 from the attribute approach. Fix B1 without a global write: select the lower/upper values into
   locals in `calc_plasma_momentum`. Document coupled wall sources as not OpenMP-safe (Part C), or open a follow-up.
2. Keep them, and show by argument and by a `jacrhs` test (L1-M2) that no default path depends on the copy. That needs
   a refresh in `OMPPandf1Rhs`, which is AIUE-58's area.

B2 (`sputflxllim/rlim`: zeroed then accumulated per `iy` inside `limiter_patch`, no reader outside it) and B4 (`workh`
scratch, `iflag_aph` output only; `B2VAhL` sets `IFLAG=0` first, `com/comutil.m`) are pure per-call scratch like
`areapl`, and are fine to keep.

**L1-M2: The validation excludes the parallel-RHS arm, which the change affects.**
Location: Testing 3.

The flow is run with `--arms jac`, but the harness default is `jac,jacrhs` (`AIUE-57/.../harness/cli.py:146`). Under
`jacrhs`, worker threads run code that reads the changed variables:

- `OMPPandf` → `bouncon` → `left_boundary/right_boundary`: `areapl`.
- `OMPPandf_XPT` → `calc_plasma_momentum`: `ghxpt`, `sxyxpt` (single null exercises this on every RHS).
- `OMPPandf_XPT` reads `TimingPandfOn` at `ppp/omp_parallel.F90:1227,1232,1294`. After the change this is the worker's
  own copy, not the master's. I traced it to be 0 in both cases (`ParallelPandf1=1` forces it to 0, and copies and
  column evaluations use `yl(neq+1)=1`). The plan doesn't say so.
- The wall BCs: `fngysi/fngyso`.

The "OpenMP results unchanged" acceptance criterion is shown for one of the two OpenMP modes only.

Resolution: run the flow with `--arms jac,jacrhs`. Gate `jacrhs` as "no group worse than AIUE-56, no new mismatch rows",
because `jacrhs` has known issues for AIUE-58. Add a cross-build `compare` on `jacrhs` in a deterministic configuration
if one exists. Otherwise state in the plan, with the trace above, why `jacrhs` is unaffected.

**L1-M3: The Probe S script is not where the plan says.**
Location: plan "Probes made for this plan", task 4, acceptance criterion 6.

`/Users/holma/Documents/uedge/src/uedge-wt/logs/AIUE-60/` contains `passed_args.py`, `an1.py` and `an2.py`, but no
`shared_writes.py`. The only copies are in ephemeral session scratchpads:
`/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-.../scratchpad/probe/shared_writes.py`
(the AIUE-61 plan notes that such a scratchpad was already lost once). Part B and the acceptance criterion "Probe S
after the fix lists only Part C" depend on this script.

I re-ran the scratchpad copy on the AIUE-60 tree. It reports 145 reachable units and 161 variables, and its list
matches Parts A–C (plus `ext_verbose`, the `PandfTiming` accumulators gated by `TimingPandfOn`, and the MC/PNC
variables).

Resolution: put `shared_writes.py` in the logs directory now (or commit it with the plan as the artifact of task 4),
and record its hash or commit in the validation record.

**L1-M4: The G1 "round-off tolerance of the threshold" is not in the scale its justification uses.**
Location: Testing 4 G1; `docs/reviews/AIUE-60-clip-check.py:20-23,125-136`.

`|v/L−1| ≤ 1e-8/L` is the same as an absolute band `|v−L| ≤ 1e-8` on `v = |bbb.jac(r,c)|·suscal(c)`. The justification
is the C2 residual "≤ 7.2e-9 × row max", which is relative to the serial row max of `bbb.jac`
(`docs/reviews/AIUE-56-c1-gate.py`), not of `v`.

On the Probe C full-problem clip-0 data (`logs/AIUE-60/probeB_full/new/serial_clip0/clip.npz`):

- Every row max of `|bbb.jac|` is 1 (max-norm row scaling).
- `suscal` spans `6.0e-4 … 1.0e7`.
- The C2 bound in the scale of `v` is `7.2e-9·su(c)`, which spans `4.3e-12 … 0.072`.
- Of the 13 896 entries within 5 % of `L`, 5 997 have a C2 bound larger than the G1 band. A legitimate round-off flip
  there would count as a non-flip, so G1 can fail falsely. In the other columns the band is up to about 2000× too wide.
- 2 765 entries lie in the band, and in the AIUE-56 build 1 390 genuine rule differences were classed as "flips".

G1 still catches a regression to the column rule (811 572 non-flips), but its tolerance is arbitrary.

Resolution: define the band per entry in the C2 scale, `| |bbb.jac(r,c)| − L/su(c) | ≤ τ·max_c'|bbb.jac(r,c')|`, with
τ pre-registered (≥ 7.2e-9, e.g. 1e-8). Report how many entries fall in the band, so a reader sees that the band is
small. Also consider the strict form "0 one-sided entries" for any run whose common-entry values are bitwise equal to
serial. Probe C shows `value_diffs_common = 0` for the full problem.

**L1-M5: The merge order with AIUE-61 is left open, and the combination is never validated.**
Location: the "Merge order" line of the merge note.

AIUE-61 adds a full `pandf(-1,-1)` on worker threads at every chunk start. That writes `areapl` at every plate cell
concurrently, plus `nfsp`, `TimingPandfOn` and `ttimpfe`, which widens the F16 race. The AIUE-61 plan's own text
defers this ("if a determinism run fails in plate rows … probable F16 effect … coordinated with AIUE-60"). Its
determinism and thread-identity gates (G2 K=20, G3) would then be measured on racy code. With "either order", whichever
branch lands second reaches the integration branch with neither ticket's gates run on the combined code.

Resolution:

- Require AIUE-60 to land before AIUE-61 (recommended: it is attribute-only and makes AIUE-61's resets race-free),
  or have AIUE-61's validation run on a tree with AIUE-60 merged.
- In either case, state that the second branch to land re-runs flow gate 3, the cross-build compare and the TSan
  "after" Te-box run on the combined tree.

### MINOR

**L1-m1: Task 2 (`nfsp`) framing and the gotcha.**

- The plan calls the `isimpon=3,4` case "a real race on results". The `.v` documents both models as "(disabled)"
  (`bbb/bbb.v:3878-3879`), so say so. The fix itself is right: the final value is identical, the `+input` override
  is still reset every call, and nothing reads `nfsp` between the two old assignments.
- The snippet's code lines are 74 and 73 columns long, against the plan's own "≤ 72 columns" gotcha. This is harmless,
  because Forthon compiles fixed form with `-ffixed-line-length-132` (`Forthon/compilers.py:306`), but correct the
  gotcha or wrap the lines.

**L1-m2: Clip check G2 is a precondition that legitimate round-off can break.**
`sfscal` comes from the `sfsetnk` Jacobian, which in the OMP arm is the OpenMP Jacobian. A C2 round-off difference in
a row-max entry changes `sfscal` and exits with 2. Say what happens then (re-run, classify), so a harness error is not
read as a G1–G4 result.

**L1-m3: The rule texts that the `nfsp` exception contradicts.**
`CLAUDE.md:23` ("Shared state written inside `pandf` must be marked `+threadprivate`") and
`.claude/context/variables-forthon.md:48` (checklist 4) both state the rule without exception. Task 5 adds the
"write only on change" exception to `openmp-jacobian.md` only. Add a pointer to both texts in the same
`AI-layer: code-facts` commit, or say why they stay as they are.

**L1-m4: The TSan "after" gate has no rule for an unexpected in-loop group.**
The `ng` and `full` presets have never been run under TSan (AIUE-50 ran the Te box only). If they show an in-loop
global-symbol group outside Parts A–C, the plan doesn't say whether that fails the ticket or becomes a classified
follow-up. Pre-register which.

## Recommendations on the plan's open questions

1. **Part B scope.** Keep B2 and B4 (per-call scratch, same class as `areapl`). Leave B1 and B3 out of the attribute
   approach (L1-M1): fix B1 with locals, or file both as a follow-up and list coupled wall sources and the double-null
   `ghxpt` write as known unsafe paths.
2. **`isimpon=5`.** I recommend a loud guard over documentation alone, because the race corrupts results silently
   (`ldir=2` makes the SAVE arrays per-call scratch that threads overwrite) and no case exists to validate a fix. For
   example, `xerrab` in `InitParallel` (`ppp/parallel.F90:1-43`, which AIUE-61 doesn't edit) when `OMPParallelJac>0`
   and `isimpon==5`, naming the follow-up ticket. This changes behaviour for OpenMP users with `isimpon=5` (from a
   silently racy result to an error), so it is the owner's decision and must be stated in the PR. A `remark` warning
   is the minimum.
3. **The RHS `nfsp` write** (`ppp/omp_parallel.F90:831-832`). I agree it goes to AIUE-58.
4. **The PETSc clip index** (`svr/petsc-uedge.F90:682`). Don't edit code that can't be built here. Note it in the PR and
   file a follow-up, or fix it only together with a PETSc build.
5. **Other differences between `jac_calc` and `LocalJacBuilder`.** Agreed, out of scope. Worth a line in
   `openmp-jacobian.md` next to the clip note.
6. **`sfsetnk` clipping with `sfscal=1`.** Report it to the owner, as planned.
7. **8 threads and Linux.** Acceptable as stated gaps.

## Status of previous findings

Round 1: none.

## Not independently verified (environment)

- TSan feasibility on `ng` and `full`, and the memory estimate (~5–10 × 1.4 GB). The procedure has a precedent (RCA
  §TSan: gfortran `-fsanitize=thread` objects linked against LLVM's `libclang_rt.tsan_osx_dynamic.dylib`, Te box,
  4 threads). The harness runner keeps `DYLD_INSERT_LIBRARIES` and `TSAN_OPTIONS`: it filters only
  `OMP_/GOMP_/KMP_/PYTHON*` (`harness/runner.py:99`).
- The Probe C numbers (69 401 and 812 962). I checked them against `logs/AIUE-60/probeB_full/clip_check.json`
  (`only_serial + only_omp = 812 962 = rules_differ`, `nnz_omp = col_rule_keeps`) but did not re-run UEDGE.
- Whether `isimpon=3,4` would change results through the old race: these models are disabled, so it can't be run.
- Bitwise identity of the generated Fortran for the serial build after the change. This is argued from Forthon's
  parser (`interfaceparser.py:343-346`: `threadprivate` sets a flag, not `v.attr`) and from 0 `threadprivate` lines in
  `base-serial/build/temp.*/*_p.F90`. The doc-string edits change only the wrapper docs. Not built.

## What was checked and how

- **Plan references.** Every `file:line` in Part A and B and in tasks 1–3 at `1553e75` (bbb.v 669-670, 679, 683, 951,
  986-987, 4136; com.v 28, 427-429, 502-521, 564-567; aph.v 203, 210; pandf.m 46-51, 573-579, 636, 751-761;
  pandf_gas_continuity.m 664, 765, 777, 876; fmombal.m 70, 248, 368, 1064; oderhs.m 1187, 2349-2352, 4697;
  parallel.F90 288, 292; omp_parallel.F90 680-721, 831-832, 1227; pandf_plasma_momentum.m 298-345, 669, 701, 1014).
  All correct.
- **Readers outside `pandf`.**
  - `git grep -w` over `.m/.v/.F90/.py` for `areapl` (only `pandf_boundary.m`) and the timers (`odesolve.m:87-93`
    reset and `:984-988` print, master only).
  - `ghxpt` (geometry.m, debug dump), `fngysi` (`walsor`, `bbb2wdf`, MPI scatter) and `sputflxllim`.
  - Python layer (`src/uedge/`): no reads of any changed variable.
- **The generated OpenMP machinery** (`AIUE-56/build/temp.*/{bbb,api,aph,com}_p.F90`):
  - The `OmpCopyScalarbbb` body.
  - `OmpCopyPointerwork2/emcoef` copy into the existing worker buffers. `apisetarraypointeremcoef` creates the worker
    buffers at allocation time with `copyin(pcopy__)`.
  - `com_p` and `aph_p` currently have 0 `threadprivate` lines, and `OmpCopyPointeraph` is empty.
  - `OmpInitZero*` is never called.
  - `InitOMPJac` sets the team to `OMP_GET_MAX_THREADS()`, so the allocation-time teams cover the Jacobian team.
- **Forthon.** Attribute parsing (`interfaceparser.py`), `DeclareThreadPrivate` (`wrappergenerator_ompextension.py`),
  and `-ffixed-line-length-132` (`compilers.py:306`).
- **Parallel RHS path.** `OMPPandf1Rhs`, `OMPPandf`, `OMPPandf_XPT` and `InitParallel` (`OMPParallelPandf1` forces
  `OMPParallelJac`). `TimingPandfOn` logic, and `yl(neq+1)=1` in Jacobian contexts (`oderhs.m:1716,1939,2325`).
- **Clip.** Serial versus parallel test; `jaccliplim` default 0 (`bbb.v:3308`); `sfscal` initialised to 1
  (`odesetup.m:1943`) and set by `sfsetnk` with a zero-row stop; the same `sfscal(iv)` in PETSc.
- **G1 scale.** I computed the G1 band against the C2 scale with a short numpy script on the Probe C clip-0 `.npz`,
  run with `venvs/AIUE-56-omp/bin/python -I`.
- **Probe S.** I located the script (missing from the logs directory) and re-ran it read-only on the AIUE-60 tree.
- **AIUE-61 interaction.** I read the AIUE-61 plan (`4dea642`) tasks 3–5 and its F16 note.
- **RCA.** The F5–F16 rows and the TSan section.
- **Precedents.** `+threadprivate` on static arrays (`cftgtipltl`, `psordisold`) and on `+maybeinput` arrays
  (`bcel`). `+work` sits in `v.attr`, independent of the `threadprivate` flag.
- **Not done.** No builds and no UEDGE runs, as the run budget required.
