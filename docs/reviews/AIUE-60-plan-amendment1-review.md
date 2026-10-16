# AIUE-60 plan review: Amendment 1 (after implementation review round 1, I1-B1)

Ticket AIUE-60 (epic AIUE-8), branch `bugfix/v9-AIUE-60-omp-races`, commit `cb05472`. Reviewed: section "Amendment 1"
of `.claude/plans/AIUE-60-omp-races.md`, `docs/reviews/AIUE-60-implementation-round1-response.md`, and the plan body
the amendment changes. Finding IDs use `LA1-` (plan stage, amendment 1).

## Verdict

**REVISE**: 0 BLOCKER, 4 MAJOR, 6 MINOR.

## Summary

The design is sound. I checked each part:
- **The atomic helper.** A `c$omp atomic` line in `com/misc.m` survives the MPPL conversion unchanged. Fixed form
  compiles it to a CAS loop with `-fopenmp` and to a plain add without it.
- **Call-site coverage.** The listed call sites are every write to the 10 timers in the tree. `tock` writes no shared
  state, and the rewrite is line-neutral.
- **`iflag_aph`.** It is never read after the `rqa`/`rra`/`rsa` calls, so replacing it with a local is result-neutral.
- **Invariant and Probe S.** The load-order invariant is correct. Applying the amendment to a scratch copy of the
  tree gives exactly the Probe S numbers the plan predicts (147 and 145, with the stated diffs).

The problems are in the gates and in the plan's bookkeeping:
- **G-iotable** as pre-registered ("0 changed words") would fail on correct code. The AIUE-56 build, which has no
  overflow, legitimately changes 2 `iotable` words in the same run.
- **The negative controls of G-common and G-iotable** depend on the pre-amendment venv and `build/temp` files. The
  planned rebuild overwrites both.
- **The two gate scripts** are not in the commit, although the plan says they are committed.
- **The plan body and the committed AI layer** still describe the superseded design. Once the amendment lands,
  `openmp-jacobian.md` would state a false fact ("threadprivate timers report the master thread only").

## Findings

### MAJOR

**LA1-M1: The G-iotable pass criterion "0 changed `iotable` words" is wrong. A correct build changes 2 words.**
- *Location:* plan, Amendment 1, "G-iotable (dynamic)".
- *Evidence:* I ran the reviewer's probe on `venvs/AIUE-56-omp`, the base without the overflow. It was made robust to
  a missing `com` block (`/tmp/aiue60amd/scripts/iotable_probe2.py`); the setup was tebox, `jac` arm, 4 threads,
  `itermx=1`. Output:
  `compy ompcommonscalarcopy_ at absent`, `ijactot 2 OMPParallelJac 1 Nthreads 4`,
  `iotable int64 words changed by the run: 2`, `word (11, 0, 1)`, `word (12, 0, 1)`, `nonzero words after: 4`.
  `exmain` opens files (impurity rate file, sputtering tables), and the unit allocator legitimately marks units in use.
  The amended build should behave like AIUE-56, so as written the gate fails on correct code. That invites a post-hoc
  reinterpretation, which the plan's pre-registration rules forbid. (In the reviewer's pre-amendment run, words 11 and
  12 became 70 and 69: the overflow overwrote these same flags.)
- *Resolution:* make the criterion differential. Run the probe on AIUE-56 and on the amended AIUE-60 in the same way.
  Pass when the before-state and after-state of all 128 words are identical between the two builds. The expected
  change set is exactly {11: 0→1, 12: 0→1}. Record the AIUE-56 run as the positive control, next to the pre-amendment
  negative control.

**LA1-M2: The G-common and G-iotable negative controls cannot be run as described once the amended tree is built.**
- *Location:* Amendment 1, "G-common" ("sizes from the generated `build/temp.*/<pkg>_p.F90`"; "on the pre-amendment
  AIUE-60 venv as a negative control") and "G-iotable" ("Control: the pre-amendment build reports > 0"). Builds:
  plan `:288-290` (`venvs/AIUE-60-omp` from this worktree).
- *Evidence:*
  - The only pre-amendment OpenMP build is `venvs/AIUE-60-omp` (`.so` files dated Oct 15 15:20:50). Its generated
    sources are in `AIUE-60/build/temp.macosx-26.3-arm64-cpython-313/*_p.F90` (15:19).
  - The plan rebuilds the amended tree into the same venv from the same worktree, so both are overwritten.
  - After that, G-common on "the pre-amendment venv" would read definers (`nm`) from a venv that no longer exists. Or,
    if it were run on a saved copy, it would read block sizes from the amended `_p.F90`, which has no `com`/`aph`
    common statement. The definer and its size would come from different builds. The plan doesn't say how the script
    behaves when a definer has no size (fail, or treat as 0).
- *Resolution:* before rebuilding, do one of these and say which:
  - preserve the pre-amendment artefacts (copy the venv to e.g. `venvs/AIUE-60-omp-pre` and the `*_p.F90` files next
    to it);
  - or run both negative controls now and record their outputs as the pre-registered control results.

  In both cases the script must take the size source as an argument tied to the artefact it checks, and must fail
  closed on a definer without a size.

**LA1-M3: The two new gate scripts are not in the commit.**
- *Location:* Amendment 1, "Script `docs/reviews/AIUE-60-common-check.py`" and "committed as
  `docs/reviews/AIUE-60-iotable-probe.py`". The plan header says the test tools are "committed with this plan".
- *Evidence:*
  - `git show --stat cb05472` lists only the plan, the review and the response.
  - Neither file exists in the worktree (`ls docs/reviews | grep -e common -e iotable`: empty) or anywhere under
    `src/uedge-wt`.
  - I could not run them as asked. Instead I re-implemented G-common (below) and ran the reviewer's probe.
- *Resolution:* commit both scripts before implementation, with the output of each control (AIUE-56 pass,
  pre-amendment fail, and the AIUE-56 iotable positive control of LA1-M1), so the gate logic is fixed before the
  amended results exist.

**LA1-M4: The plan body and the committed AI layer still state the superseded design. One AI-layer fact becomes
false.**
- *Location:*
  - plan Task 1 (`:225-232`: `+threadprivate` on the `com` timers and `iflag_aph`, "; OpenMP: master thread only");
  - "Default results" point 4 (`:211-212`);
  - Task 5 (`:272-274`: "Threadprivate timers report the master thread only");
  - Testing checklist (`:444`: "Probe S … 147 and 135 entries"); Part A table row A4 (`:139`);
  - the committed `.claude/context/openmp-jacobian.md` rule 1 (from `1442d23`): "Threadprivate timers (`com.ttimpjf`,
    …) report the master thread only."
- *Evidence:* the amendment reverts the timers to shared with atomic updates, so they sum over threads, and changes
  `passed-args` to 145. None of the passages above is marked superseded. Task 5 doesn't list the correction of the
  committed rule-1 sentence; it lists only the new invariant. An implementer following Task 1 would re-apply the
  blocked design. The AI layer would keep a false statement (CLAUDE.md "Keep the AI layer true").
- *Resolution:*
  - mark or replace each superseded passage (row A4, Task 1 for `com.v`/`aph.v:203`, Default-results 4, Task 5, the
    Testing checklist numbers 147/145);
  - add to Task 5: rewrite the `openmp-jacobian.md` rule-1 timer sentence (timers are shared, updated through
    `acctim` atomically, and report the sum over threads), next to the new invariant.

### MINOR

**LA1-m1: Pin the `acctim` text and check the directive statically. TSan doesn't observe the atomic write.**
- *Evidence (MPPL hazard):* I emulated the `M2F` rule chain from `setup.py` (classes extracted with `ast`). The plain
  helper converts unchanged:

  ```
  subroutine acctim(acc, dt) / implicit none / real acc, dt / c$omp atomic / acc = acc + dt
  ```

  But if a `Use(...)` line follows the declarations, `MoveDecs` emits the comment line before the moved declarations.
  The output is then `use Timing / c$omp atomic / implicit none / real acc, dt / acc = acc + dt`, and the directive is
  misplaced.
- *Evidence (compile):* gfortran 15.2, `-ffixed-line-length-132 -fdefault-real-8 -fdefault-integer-8 -O3`:
  - with `-fopenmp`: `_acctim_` is a `cas` loop;
  - without it: `ldr/fadd/str`.
- *Evidence (TSan):* with `-fsanitize=thread`, GCC instruments the initial load (`___tsan_atomic64_load`) but not the
  `cas`. TSan therefore never sees the timer writes. "TSan sees atomics, so it doesn't report them" is imprecise. A
  lost directive would still show (plain read and write), but TSan cannot confirm atomicity.
- *Resolution:*
  - state the exact helper text: no `Use`, directive line immediately before the assignment;
  - add a static check: generated `com/misc.F` has `c$omp atomic` directly above `acc = acc + dt`; `otool -tV` of the
    OpenMP `compy` shows the CAS (or LL/SC) loop in `_acctim_`, and the serial build shows a plain add.

**LA1-m2: Make G-common robust and portable.**
- *Load order:* iterate the import order parsed from `src/uedge/__init__.py`, not a fixed list. The plan's list omits
  `uedgeC` (first) and `ncl` (last).
- *Block size:* compute it from the declared kinds of the `copy` variables, not "× 8 B". It is 8 B for every variable
  today, but the generator emits `logical(kind=8)`, `integer(kind=8)` and `real(kind=8)`, and a future kind change
  would silently mis-size the block.
- *Linux:* `nm -m` is macOS only. If the script is offered to the AIUE-57 Linux CI job, give a Linux path (`nm -S`
  gives sizes directly).
- *Independent check of the stated sizes:* matches the plan:
  - AIUE-56: `bbb` 89 = 712 B, `api` 96 B;
  - pre-amendment AIUE-60: `bbb` 91 = 728 B, `api` 96 B, `com` 80 B, `aph` 8 B;
  - definers (`nm -m`): AIUE-56 `bbbpy`, `apipy`; AIUE-60 `compy`, `bbbpy`, `apipy`, `aphpy`;
  - in `compy`, `_iotable_` follows the block directly (0x538d0 → 0x53920 = 80 B).

  So the stated controls would behave as claimed.

**LA1-m3: Pre-register the reachable-unit count of Probe S.**
- The amended scratch tree gives `146 reachable units; 147 variables` (base and pre-amendment: 145), because `acctim`
  is a new reachable unit.
- The plan says "Any other change fails". State 146 so this isn't argued after the fact.
- Otherwise the predictions are exact: shared-writes minus the same 14 names; passed-args `−workh −iflag_aph +10`
  timers, 145.

**LA1-m4: Timer semantics and the timing flag.**
- With atomics the OpenMP values are thread-seconds summed over workers and can exceed the elapsed time. The plan
  restores the original doc strings ("time spent in …"). Say "summed over threads under OpenMP" in the doc strings, or
  at least in the PR and `openmp-jacobian.md`.
- `totintrv`/`totb2val` and `ttimpfe`/`ttimpjf` are updated without an `istimingon` guard, in the spline routines,
  so their atomics are on the hot path.
- The ">10 % flag" in the timing report has no stated consequence. Say what a flag triggers (owner decision, or a
  guarded update).

**LA1-m5: Record the loss of a Python-visible diagnostic.**
- `aph.iflag_aph` stays a Python variable, but `rqa`/`rra`/`rsa` no longer update it. It then reflects only the
  `aphread` setup calls (`aph/aphread.m:920-951`).
- Results are unaffected: `B2VAhL` sets `IFLAG=0` first (`com/comutil.m:3608`) and reports errors itself (`:9900`).
  It is still a behaviour change of a user-visible variable. List it in the PR.

**LA1-m6: Make the Forthon follow-up text (2) precise.**
- `ProcessDim`/`GetSize` take `S.split('(')[1].split(')')[0]`
  (`Forthon/wrappergenerator_ompextension.py:53,64`). They keep the text between the first `(` and the next `(` or
  `)`, so a nested `(` truncates the bound. This is not "cut at the first `)`".
- Point (1) is accurate: `common /ompcommonscalarcopy/` and `firstprivate(/ompcommonscalarcopy/)` are emitted with a
  fixed name for every package (`:161,166`).

## Not independently verified (environment)

- **Linux ELF binding.** Not run; reasoned only. `RTLD_GLOBAL` with default-visibility COMMON definitions in `-fPIC`
  extensions puts `compy` in the global lookup scope first, so the invariant should hold on Linux too. Verifying it
  needs a Linux OpenMP build with `nm -S`/`readelf -s` on the 11 extensions and the iotable probe.
- **Amended full build, TSan, timing.** I didn't build the amended tree; plan stage, no build budget. I compiled only
  the converted `misc.F` with the helper (OpenMP and serial). The TSan gate on the amended build and the cost of the
  atomics are for the implementation round.
- **Repeatability of the 2-word `iotable` change on AIUE-56.** One run only. Deterministic unit allocation makes it
  likely, but it isn't shown.

## What was checked and how

- **Conversion.**
  - Read `setup.py` (`M2F` rules `:634-660`; `Use2use`, `Omp`, `MoveDecs`, `Elseifthen`).
  - Emulated the rule chain on the helper in three variants (`/tmp/aiue60amd/conv.py`): plain, `Use` first, `Use`
    after the declarations.
- **Compilation.**
  - Forthon's gfortran fixed-form flags include `-ffixed-line-length-132` (`Forthon/compilers.py:306`).
  - Compiled the converted `misc.F` with and without `-fopenmp`, and with `-fsanitize=thread`, using gfortran 15.2.
  - Inspected the generated assembly with `otool -tV` and `-S`.
- **Timer writes.** `git grep -w` of all 10 timers across the tree:
  - writes only at the 13 listed lines (pandf.m 636, 758, 760; pandf_gas_continuity.m 664, 765, 777, 876;
    comutil.m 3654, 3902; aphrates.m 596, 773, 1031; fmombal.m 248);
  - master-side resets at `odesolve.m:89-90`, `comutil.m:44-45` and `apifcn.m:221`;
  - prints, and `USE` lines in `ppp`/`svr` with no writes;
  - start-time variables (`tsval`, `tsint`, `tsn*`) are not `.v` variables;
  - `tick`/`tock` (`com/misc.m:91-105`) call only `system_clock`.
- **Line neutrality and Probe S.** Applied the amendment to a scratch copy of `cb05472`
  (`/tmp/aiue60amd/tree`: `com.v` from `1553e75`, `aph.v:203` reverted, 13 call sites rewritten, `iflagl` locals,
  helper appended):
  - the file line counts are unchanged except `com/misc.m`, which grows at the end;
  - the longest new line is 61 columns;
  - ran `AIUE-60-shared-writes.py` and `AIUE-60-passed-args.py` on the base, pre-amendment and amended trees:
    161/137, 147/135, 147/145; diffed the variable lists.
- **`iflag_aph`.** `git grep -w`: only the 6 `B2VAhL` arguments and the master-side `aphread.m` setup. `B2VAhL`
  `IFLAG=0` at `comutil.m:3608`. No Python reader (`src/`, `pyscripts/`). No `save` in `rqa`/`rra`/`rsa`.
- **Common blocks.**
  - Ran `nm -m` on all 11 extensions of `venvs/AIUE-56-omp` and `venvs/AIUE-60-omp`.
  - Scanned for duplicated external data symbols: `_ompcommonscalarcopy_` is the only Fortran one; `pcopy__` copies
    are non-external.
  - Computed block sizes and kinds from the generated `*_p.F90` of both worktrees (`/tmp/aiue60amd/gcommon.py`).
  - Counted threadprivate scalars per `.v`: `ppp`, `ncl`, `svr`, `wdf`, `grd` and `flx` have none.
  - Read the Forthon generator (`wrappergenerator_ompextension.py:51-75,140-175`).
- **Dynamic.** UEDGE runs:
  - 2 full probe runs on `venvs/AIUE-56-omp`. The first run's Python output was lost to a shared-file-offset
    redirect, so it was repeated through a pipe.
  - One more attempt stopped at import (rates directory not set) before any UEDGE computation.
- **Read.** The plan (whole file), implementation review round 1, the response, the TSan scripts and the committed
  `openmp-jacobian.md` diff (`1442d23`).
