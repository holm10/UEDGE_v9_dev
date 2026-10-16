# AIUE-60 implementation review, round 1

Ticket AIUE-60 (epic AIUE-8): "Fix remaining OpenMP races in the pandf tree and the clip-index inconsistency".
Branch `bugfix/v9-AIUE-60-omp-races`, tip `a2e1550`, stacked on AIUE-56 `1553e75`. Reference: the approved plan
`.claude/plans/AIUE-60-omp-races.md` (plan review round 3 APPROVE).

## Verdict

**REVISE**: 1 BLOCKER, 0 MAJOR, 2 MINOR.

## Summary

The code diff does what the plan says, line for line. The edits are line-neutral, the clip index is fixed at
`ppp/parallel.F90:288,292`, `nfsp` is written only when it changes, and the `workh` bound rewrite is arithmetically
the same size in the Fortran and C wrappers. I reproduced the recorded results:
- the flow gates (64/64 RHS sections bitwise, every class-Y Jacobian mismatch in Te rows);
- the clip counts (69 401 / 812 962; OpenMP pattern = serial in every AIUE-60 run, = the column-rule set in every
  AIUE-56 run);
- Probe S (161→147, 137→135);
- the D_only per-file outcomes;
- the TSan classification of all 23 post-fix in-loop heap reports.

The defaults evidence is valid. However, making ten `com` scalars `+threadprivate` makes Forthon emit a second, smaller
definition of the shared common block `/ompcommonscalarcopy/` in `compy.so`. Because `com` is loaded first with
`RTLD_GLOBAL`, `bbb`'s scalar copy now binds to that 80-byte block. Every OpenMP Jacobian then writes `bbb`'s 728-byte
copy past its end into `com`'s `/iotable/`. I showed this directly: one OpenMP Jacobian changes 62 words of `iotable`,
including two in-use unit flags reset to 0. This memory corruption is new. It must be removed before merge.

## Findings

### BLOCKER

**I1-B1: The `com` threadprivate scalars add an 80-byte `/ompcommonscalarcopy/` in `compy.so`. `bbb`'s 728-byte scalar
copy binds to it and overwrites `com`'s `/iotable/` on every OpenMP Jacobian.**
- **Location:** `com/com.v:506,508,514,517-521,566-567` (`+threadprivate` on the 10 timers), with the generated
  `OmpCopyScalarcom` (`build/temp.*/com_p.F90:~495-510`) and `OmpCopyScalarbbb` (`bbb_p.F90:~11234`). The same applies,
  latently, to `aph/aph.v:203` (`iflag_aph`, an 8-byte block in `aphpy.so`).
- **Mechanism.**
  - Forthon's `--omp` generator gives every package's `OmpCopyScalar<pkg>` the same common name,
    `common /ompcommonscalarcopy/ <pkg's scalar copies>`, with `firstprivate(/ompcommonscalarcopy/)`.
  - The extensions are loaded `RTLD_GLOBAL` in the order `com, grd, flx, bbb, …, api, aph, ppp`
    (`src/uedge/__init__.py:1,24-32`). The Mach-O bundles are flat-namespace, `WEAK_DEFINES/BINDS_TO_WEAK`
    (`otool -hv`). So the first loaded definition of `_ompcommonscalarcopy_` serves every package.
  - Before AIUE-60, `com` had no threadprivate scalars. Only `bbbpy.so` (91 scalars, 728 B) and `apipy.so` (12, 96 B)
    defined the block, so everyone bound to `bbb`'s, which is the largest.
  - Now `compy.so` defines it with 10 reals (80 B), and `aphpy.so` with 8 B (`nm -m`: `compy … 0x538d0 (__DATA,__common)
    external _ompcommonscalarcopy_`, followed directly by `_iotable_` at `0x53920`).
- **Evidence.**
  1. *TSan location of the block, pre vs post* (your own `tsan2` logs):
     - pre-fix (`logs_pre_tebox`, `logs_pre_full`): every `ompcommonscalarcopy_` report is at
       `bbbpy.cpython-313-darwin.so+…`;
     - post-fix: every report is at `compy.cpython-313-darwin.so+0x676e0…`, and `__ompcopybbb_MOD_ompcopyscalarbbb`
       reads that `compy` address (`logs_post_tebox/tsan.95233`: "Previous read … at 0x00010e7376e0 by thread T3:
       #0 __ompcopybbb_MOD_ompcopyscalarbbb._omp_fn.0 bbb_p.F90:11234 … Location is global 'ompcommonscalarcopy_' at
       0x00010e7376e0 (compy.cpython-313-darwin.so+0x676e0)").
  2. *Direct probe* (`/tmp/aiue60rev/scripts/iotable_probe.py`, AIUE-60-omp venv, tebox preset, `jac` arm, 4 threads,
     one `exmain` with `itermx=1`, 2 OpenMP Jacobians). It reads `compy.so`'s `iotable_` through `ctypes` before and
     after. Result: "iotable int64 words changed by the run: 62". Examples: word 5 `0 → 4592291131226807497` (a double's
     bit pattern), words 9 and 10 `1 → 0` (in-use unit flags cleared), words 11 and 12 `0 → 70, 69` (index scalars).
     `iotable` is the Fortran unit allocator (`com/dummy_py.f:48-85`, `freeus`/`basclose`). After this, `freeus` can
     hand out a unit that is still open. The AIUE-56 build has no `_ompcommonscalarcopy_` in `compy.so` (`nm`), so
     the overflow did not exist before. (My probe on AIUE-56 stopped at that missing symbol, which is itself the
     evidence; I didn't run it further, to stay within budget.)
  3. On Linux (CI, wheels), `RTLD_GLOBAL` with ELF interposition should bind the same way. What sits after
     `compy.so`'s COMMON there depends on the linker, so the victim may be other `com` data. Not verified here.
- **Why the gates missed it.** The copied values reach the workers correctly: both the master's write and the
  workers' `firstprivate` copy use `bbb`'s layout. So the flow, clip and serial checks agree bitwise. The TSan
  record saw the symptom ("ompcommonscalarcopy_ now also from OmpCopyScalarcom", §5) and listed it as report-only.
  `scan_ompcopy.py` doesn't check common-block sizes.
- **Not affected:** default results. The serial build has no `OmpCopy*` routines, and with `ParallelJac=0`
  `OMPJacBuilder` is never called. Every OpenMP-Jacobian run is affected.
- **What would resolve it.** Any change after which no package defines a `/ompcommonscalarcopy/` that is smaller than
  `bbb`'s and binds first. Examples:
  - give the 10 timers (and `iflag_aph`) per-thread storage that doesn't go through Forthon's scalar-copy common;
  - leave the timers shared and treat them as diagnostic-only. This needs a plan amendment for the TSan gate;
  - an upstream Forthon change to package-specific common names.

  The choice is yours, but a changed design is a plan amendment for re-review.
- **Acceptance.**
  - (a) In both OpenMP venvs that matter (AIUE-60, and AIUE-61 after its rebase), `nm -m` shows no
    `_ompcommonscalarcopy_` in a package loaded before `bbbpy.so` that is smaller than `bbb`'s. Or an equivalent
    probe like mine shows `iotable` unchanged across an OpenMP Jacobian.
  - (b) The plan's gates re-run on the new tree: serial check, flow, clip, TSan, Probe S with updated expectations.
  - (c) `openmp-jacobian.md` and `variables-forthon.md` (checklist 4) record the hazard: a `+threadprivate` scalar in a
    package other than `bbb` adds a `/ompcommonscalarcopy/` definition. That is a code fact AIUE-61 also needs if it
    adds threadprivate scalars to `ppp.v`.

### MAJOR

None.

### MINOR

**I1-m1: B2 and B4 were never executed in a threaded run.**
- **Location:** validation record §§1-6; plan Part B.
- **What is wrong.** No preset enables `islimon` limiter sputtering or `istabon=5/6`. The deck uses `istabon=10`, and
  the `nwfits` file `istabon=5/6` needs isn't on this machine. So the new per-thread `sputflxllim/rlim` and `workh`
  buffers were exercised only by Probe S and the build.
- **Why the risk is low.** I checked the generated code. `aphsetarraypointerworkh` and
  `bbbsetarraypointersputflxllim` use the same `copyin(pcopy__)` per-thread allocation as the 500+ `bbb`
  threadprivate arrays the flows do exercise. `B2VAhL` writes `WORK` before it reads it (`com/comutil.m:3607-3692`).
  `InitOMPJac` caps the team at `OMP_GET_MAX_THREADS()` (`ppp/omp_parallel.F90:296-302`).
- **Resolution.** State these as untested runtime paths in the record and the PR.

**I1-m2: The record doesn't list two deviations as deviations.**
- **Location:** `docs/reviews/AIUE-60-validation.txt` §"Deviation from the plan", §2.
- **(i) The defaults gate.** The plan's gate (AIUE-56 bases, complete gate) returned `INCOMPLETE` on tool policy. The
  substitute gate against `base-serial`/`base-omp` (`0fac655`) is valid, and I checked why:
  - `0fac655` is an ancestor of `origin/v9-develop` and of `1553e75`;
  - `git diff 0fac655 1553e75` over product sources is only `ppp/omp_parallel.F90` (AIUE-56's `OMPJacBuilder` copy
    order), which runs neither in serial nor with both switches 0;
  - the AIUE-60 venvs were built from clean `02e6e60` after its commit (15:20/15:22 vs 15:18:55), and the
    `bbbpy*.so` hash in the venv equals the build tree's;
  - the tool reports `gate_complete: true` with no warnings.

  The record shows both results but doesn't call the substitution a deviation or give this reasoning.
- **(ii) The generated serial Fortran.** Plan §"Why defaults…" 1 says the generated serial Fortran is identical. After
  `02e6e60` the serial `aph_p.F90:681` and `aphpymodule.c` (doc string; C dims at `:1166`) differ in the text of
  `workh`'s bound. The two forms are arithmetically equal (`a*b+2k(a+1) = a*b+2ka+2k`); I diffed them.
- **Resolution.** Add both points to the deviation section.

## Not independently verified (environment)

- **Linux/CI:** whether I1-B1 binds the same way on ELF and what it overwrites there. The code path is the same
  (`RTLD_GLOBAL`, same generated commons). To verify: the `iotable` probe, or `nm`/`readelf` of the wheel's
  `compy*.so`, on the Linux OpenMP CI build.
- **8 threads:** not run (machine rule; stated in the plan).
- **`istabon=5/6`:** can't run here, because the `nwfits` file is missing (I1-m1).

## What was checked and how

- **Code diff vs plan.**
  - `git diff 1553e75..a2e1550` on `aph/aph.v`, `bbb/bbb.v`, `com/com.v`, `bbb/pandf.m`, `ppp/parallel.F90`. Every
    attribute is on its existing line; all five files keep their line counts (766, 368, 4219, 710, 220).
  - The `nfsp` rewrite leaves the same final value for every `isimpon`.
  - `sfscal(ii)` is now used at both `:288` and `:292`, matching `bbb/oderhs.m:1187`.
  - `TimingPandfOn` gates only `tick`/`tock` calls (`git grep`), so a per-thread value can't change results.
  - No reader of `areapl`, `sputflxllim/rlim`, `workh` or `iflag_aph` needs another thread's value across the region
    boundary.
- **The `workh` deviation.**
  - Forthon `wrappergenerator_ompextension.py:51-76` (`ProcessDim`/`GetSize`) cuts at the first `)`, as claimed.
  - In the generated code, `aph_p.F90` (OpenMP: `:140-153`, `:726-756`; serial: `:681`) and the `aphpymodule.c` dims
    expression are arithmetically equal to the old bound.
  - `diff` of the AIUE-56-serial vs AIUE-60-serial `bbb/com/api/ppp_p.F90` shows them identical.
- **Threadprivate directives.**
  - OpenMP: present in `bbb_p.F90:917,920,921,3623`, `com_p.F90:354-361,389-390` and `aph_p.F90:132-133`.
  - Absent for `ghxpt`, `fngysi` and `nfsp`.
  - Serial: 0 in every `*_p.F90`.
  - The `bbb.v` count is 526 (base 522).
- **Defaults.**
  - I read `serial_check_vs_v9dev/summary.txt` and `serial_check.json` (`agree true`, `gate_complete true`,
    `warnings []`, sources clean at `02e6e60`/`0fac655`).
  - I checked ancestry, the product diff `0fac655..1553e75`, the venv `.so` mtimes and the hashes.
- **Flow gates.**
  - I re-ran `AIUE-60-flow-gates.py` on the records into a separate stage directory; the output is identical to
    `flow_gates.txt`.
  - An independent script (`/tmp/aiue60rev/scripts/indep.py`) found, for both flows: 64 agreement reports, 0 class-X
    mismatches, 0 RHS-section mismatches, 0 Jacobian mismatches outside Te rows, and no report with errors.
  - Run records show `ParallelJac=1`, `ParallelPandf1=1` on `jacrhs`, and `Nthreads=4`.
  - The cross-build compares (`xb_jac_cmp.txt`, `xb_jacrhs_cmp.txt`) are AGREE on every section, and both builds are
    deterministic.
- **Clip.** An independent script (`/tmp/aiue60rev/scripts/clip_indep.py`) used the saved `clip.npz`:
  - From the serial clip-0 Jacobian it predicts row-rule 636 497 / column-rule 594 104 / differ 69 401 (`ni`) and
    2 474 283 / 2 402 093 / 812 962 (`full`).
  - Every AIUE-60 OpenMP run has exactly the serial pattern (0+0 one-sided entries).
  - Every AIUE-56 run has exactly the column-rule set (13 504 + 55 897; 370 386 + 442 576).
  - `sfscal` is bitwise equal in all runs.
  - G4: the base and new serial patterns and values are equal.
- **TSan.**
  - Scripts: the committed `tsan.sh`/`tsan-prep.py` match the copies that ran.
  - Run records: `ParallelJac=1`, `Nthreads=4`, `ijactot` 1 or 2, sources at `1553e75`/`02e6e60` (dirty only through
    the `-fsanitize=thread` edit to `setup.py`).
  - My classifier (`/tmp/aiue60rev/scripts/tsan_pairs.py`) over every post-fix report found that every report has
    exactly one access inside a parallel region. The one exception is the `ompcopypointeremcoef` `copyin` race (A6,
    outside the loop, documented). So the pre-registered heap/stack rule is applied correctly.
  - The pre runs show every expected group (the positive control).
  - The exit 134 happens after the record is written, and reports are logged as they occur. It doesn't undermine the
    result.
- **Probe S.** I re-ran both scripts (the SHA-256 prefixes match): 147 and 135 entries, the same as
  `sw_post2.txt`/`pa_post2.txt`. The diff against the pre-fix outputs is exactly the 14 + 2 planned removals.
- **D_only.** Outcomes in `donly_{omp,serial}.json` vs `donly56_*` are identical file by file, ignoring timings.
- **AI layer.**
  - `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`: OK.
  - `uv run .claude/hooks/change_kind.py --range 1553e75..HEAD`: OK.
  - The process files are only in `1442d23`, which has the `AI-layer: code-facts` trailer.
  - The cited lines are correct: `bbb/odesetup.m:6727-6772`, `ppp/omp_parallel.F90:721`, `ppp/parallel.F90:292`,
    `bbb/oderhs.m:1187`, and the `jac_calc`/`LocalJacBuilder` diagonal and `nufak` differences.
- **AIUE-61 readiness.** `git merge-tree a2e1550 bugfix/v9-AIUE-61-omp-static-partition` conflicts only in
  `openmp-jacobian.md` and `refs.lock.json`. `ppp/parallel.F90` auto-merges and keeps `sfscal(ii)` (merged `:292,296`).
  Once I1-B1 is fixed, AIUE-61 can rebase; it should check whether its `ppp.v` additions bring in threadprivate
  scalars (see I1-B1 (c)).
- **Runs used.** Three short tebox runs with the existing venvs, 4 threads. Two were the `iotable` probe on AIUE-60,
  run twice because the first output was buffered. One was on AIUE-56; it stopped early, as described in I1-B1. No
  builds and no reinstalls.
