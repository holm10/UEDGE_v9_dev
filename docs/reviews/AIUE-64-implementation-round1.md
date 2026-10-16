# AIUE-64 implementation review, round 1

Stage: implementation. Ticket AIUE-64, "OpenMP build does not import on Linux: extensions linked without -fopenmp"
(epic AIUE-8). Reference: the approved plan `.claude/plans/AIUE-64-omp-linux-link.md` (plan review round 2 APPROVE),
including the L5 amendment `8a867c9`. Branch `bugfix/v9-AIUE-64-omp-linux-link` at `a738e92`, worktree
`/Users/holma/Documents/uedge/src/uedge-wt/AIUE-64`.

## Verdict

**REVISE** (0 BLOCKER, 1 MAJOR, 3 MINOR).

## Summary

The `setup.py` change is the planned one, almost word for word. It runs only on Linux and only in the OpenMP build.
It appends `-fopenmp` to `LDFLAGS` once (token check) in a copy of the environment that only the Forthon make sees,
and macOS and serial builds take the old call (`env=None`). The committed records back every claim I recomputed:
the macOS links are identical before and after (I re-derived `otool -L`, `otool -hv` and the anchored `nm -u` from
the current venvs and they match the records and the `base-*` venvs). On Ubuntu, `base` fails and `fix` imports.
The `ldd -r` filter, NEEDED, the equivalence with the `LDFLAGS=-fopenmp` workaround (link lines token-identical),
Linux serial and Debian all check out. The M3 serial check is a non-stale AGREE on 42 cases. The L5 amendment is
legitimate: the reason is sound, the threshold was committed before the re-run, the failed original is kept, and the
amended result shows what L5 was meant to show. The one MAJOR finding is the record itself. M4 is the only check
that did not come out green, and it is missing from the committed results. The README says it covers M1–M4 but its
table has no M4 row, and the two one-off abnormal exits are written down nowhere. On the evidence I checked, the M4
deviations are pre-existing and identical on base, so this needs text, not code.

## Findings

### MAJOR

**I1-M1. M4 is not green, and the committed record leaves it out.**
*Location:* `docs/rca/AIUE-8-data/linux/aiue64/README.md` §Results (its intro cites "§Testing strategy M1–M4, L1–L6").
*What is wrong:* M4 was pre-registered as "serial build, smoke, `D_only` passes; `--omp` check result is the same as
on `base-omp`". The plan's Pass/fail rule says any deviation "is reported verbatim and stops the ticket". Two parts
of M4 deviated, and the results table has no M4 row:
- `D_only` on `AIUE-64-serial`: `5 failed, 120 passed, 1 warning` (concap, ineudif0, ineudif1, ineudif3,
  tg_atom_cftiexclg0p5);
- the macOS OpenMP CheckPandf1/CheckJac check stops with `RuntimeError: diff in rhsnk`, with
  `>>>> 272 387.04448987743109 387.04448987291863 1.1658757793646371E-011` and
  `>>>> 428 -102.89970684190475 -102.89970639107977 4.3812075279923317E-009`.

The two one-off abnormal exits from the main session's brief (133 from the `gtimeout` wrapper, 139 once) are in no
file at all. The scratch `omp_check_AIUE-64-omp.log` stops after the banner and does not record an exit code.
CLAUDE.md asks for fnrm and diff failures to be reported verbatim. A reader of the committed table would conclude
that everything passed.
*Evidence that the deviations are pre-existing (checked, and accepted):*
- `diff` of the `FAILED` lines in `validate/d_only.log` (fix) and `validate/d_only_base.log` (`base-serial`) is
  empty. All `Returned fnrm`/`Reference fnrm` lines are identical. The `ineudif*` `ValueError` failures were already
  recorded on AIUE-56 (`AIUE-56/docs/reviews/AIUE-56-implementation-round2.md:100`).
- `omp_repeat.txt` has 3 alternating runs on each of `AIUE-64-omp` and `base-omp`. All exit 1, each with 2
  "jacobian are identical" lines, 4 "pandf are identical" lines and 2 `>>>>` lines. After removing NULs and the timing
  lines, I diffed `rep/AIUE-64-omp_i.log` against `rep/base-omp_i.log` and they are identical for i = 1, 2, 3,
  mismatch values included.
- On macOS the change is inactive by construction. The link lines, `otool` and `nm` are identical (M1, re-checked
  below), and M3 gives bitwise AGREE on 42 cases. So a build-caused difference or crash on macOS has no mechanism.
*Attribution (for the record text):* `diff in rhsnk` comes from the RHS check (CheckPandf1). The same log says the
parallel and serial Jacobians are identical. That rules out C2, which is a Jacobian column-history defect. By my
reading of the variable ordering for this deck (`nonog_d_c-fb_16x8`: 8 ni, 2 up, te, ti, 1 ng = 13 per cell, 2340/13
= 180 cells), rows 272 and 428 are both the 12th variable of their cell, i.e. **Ti** rows, at (ix=2, iy=1) and
(ix=14, iy=1). The deck has `isnonog=1` and `isupgon(1)=1`. That is consistent with AIUE-58's R1 class (`hcyn` chunk
range, Ti rows, present on pre-fix builds), but it is not shown. The record should say "RHS-class, consistent with
R1", not "R1".
*Resolution:* add an M4 row (and a few small files, e.g. the `FAILED` list with the fnrm lines and `omp_repeat.txt`)
that gives the deviations verbatim, the base comparison above, and the two one-off exits with their exit codes and
whatever is known about them (run, venv, signal). Mark M4 "deviates from the pre-registered expectation; identical on
base". Carry the same text into the PR description.

### MINOR

**I1-m1. The macOS "before" build is not at the commit the README names.** `macos/before/build_head.txt` is `1adea93`
(the plan's last commit), but the README gives `BASE = 4faed39` and plan task 0 says "build the untouched branch
(`4faed39`)". The product tree is the same: `git diff 4faed39 1adea93 -- . ':!.claude' ':!docs' ':!CLAUDE.md'` is
empty. *Resolution:* one line in the README.

**I1-m2. One sentence in the L5 amendment is inaccurate, and the README omits a caveat.** The amendment (plan L5)
says the serial-arm control "has no region during `exmain`". The control's workers gained 5.3 ms (N=2) and
6.0–10.3 ms (N=4) of CPU during `exmain`, so either there are regions or the spin from earlier regions carries on.
The 5× margin handles either case, so the verdict stands. Separately, the 5× factor was picked after the diagnostic
(14:27) had shown rough magnitudes (A: 7 ticks on a jac worker; C: 1–2 ticks on control workers, other preset). The
threshold is therefore not fully blind, although those numbers would not obviously have passed it. *Resolution:*
reword the sentence, or note both points in the README L5 row.

**I1-m3. Two pre-registered checks have no committed record.** L2 ("the build log contains `Linux OpenMP build:
linking the Forthon extensions with LDFLAGS='-fopenmp'`") and L4 ("the new line absent") are checked only against
build logs that were not committed. I confirmed both in scratch: the line is present in Ubuntu `build_fix.log`,
Debian `build_fix.log` and `ubuntu_probe2/build_fix.log`, and absent from `build_base`, `build_wkld`, `build_base-ser`
and `build_fix-ser`. *Resolution:* commit a one-line `grep -c` per build or mention it in the README.

## Not independently verified (environment)

- **The Linux runs themselves** (Docker, emulated amd64). I checked only the committed records and the scratch build
  logs. The records agree with each other and with the driver scripts, so the scripts would produce them, but I did
  not re-run them (no Docker in this budget).
- **The 133 and 139 exits**: neither exit code is in any file. Only the main session's statement supports them.
- **Native x86-64 CI** (the AIUE-57 workflow on a GitHub runner), **Linux wheels** (cibuildwheel/manylinux: the
  change is active there and adds `libgomp.so.1` NEEDED to `apipy`/`bbbpy`/`ppppy`; the owner deferred this and the
  plan lists it as not claimed), **arm64 Linux**, **non-`--as-needed` distributions** and **`CC=clang` on Linux**.
  The plan states that these are untested.

## What was checked and how

- **The fix against the plan** (`git diff 4faed39 -- setup.py`). The code is identical to plan task 1. The only
  difference is that the comment's last two lines are merged. Guard: `not arglist['serial'] and
  platform.startswith('linux')`, where `platform` is `sys.platform` (`setup.py:14`). `makeenv = dict(os.environ)` is
  built at call time, after `OMP`/`NOCLEAN` are set, so `os.environ` is not changed. The token check is
  `'-fopenmp' not in ldflags.split()`. The new value is appended to the user's string, not split and re-joined.
  `env=makeenv` goes only to the Forthon `make`. `build.run(self)` (the `uedgeC` link) inherits the unchanged
  process environment. `env=None` is the old behaviour on macOS and in serial builds.
- **Commits**: `1e8eb78` touches only `setup.py`. `8a867c9` touches only the plan. `eae662c` adds only
  `docs/rca/.../aiue64/` (816 KB in total). `a738e92` touches only `architecture.md` and `refs.lock.json` and carries
  the `AI-layer: code-facts` trailer. No skills, agents or hooks change on the branch. The worktree is clean.
- **Code facts**: `sed -n` on the edited `setup.py` gives :769 = the AIUE-64 comment, :785 = the `call([...],
  env=makeenv)`, :787 = `build.run(self)`, :798 = `Extension(` for `uedgeC`, :814 = `extra_link_args=FLAGS['CARGS']...`.
  All five are locked in `refs.lock.json` with exactly that text. No other AI-layer file cites a `setup.py` line
  above 768. `Makefile.Forthon` only runs `rm -f uedgeC.so`, so the "not `uedgeC`" correction holds. The step 4
  wording is true (in the serial build too, per the side finding). `uv run .claude/hooks/check_context_refs.py
  --changed origin/v9-develop` gives `OK`, exit 0, and so does `--changed v9-develop`.
- **M1 (recomputed)**: I ran the `mac_record.sh` loop (`otool -L`, `otool -hv`, `nm -u | grep -E
  '^_(GOMP_|omp_)'`) on the current `AIUE-64-omp`, `AIUE-64-serial`, `base-omp` and `base-serial` venvs. The current
  `AIUE-64-*` venvs were rebuilt by validate from `a738e92`, which has the same product tree as `1e8eb78`. All three
  record types are identical to `macos/after/rec_*` and to the matching `base-*` venv. libomp appears only in
  `uedgeC`. The OpenMP counts are apipy 4, bbbpy 4, ppppy 13, and serial ppppy 2. `diff -r macos/before macos/after`
  differs only in `build_head.txt` (and `m2_import.txt` exists only in `after`). The validate build logs have 11
  `-bundle` lines and 0 "Linux OpenMP build" lines.
- **M2**: `macos/after/m2_import.txt` shows exit 0 for both builds.
- **M3**: `serial_check.json` has `agree: true`, `gate_complete: true`, `incomplete: []`, `errors: []`, pairs
  `serial` and `omp0`, 42 cases, new builds with `source_head 1e8eb78`, `source_dirty: false`. The run ended at about
  14:13, before the next commit (`8a867c9`, 14:58:52), so it is not stale.
- **L1**: `ubuntu/import.txt` shows `base` failing with `undefined symbol: GOMP_parallel`, exit status 127, and `fix`
  at exit status 0. In `rec_base/ldd_r_omp.txt` only apipy, bbbpy and ppppy are non-empty (4/4/13 symbols).
  `rec_fix` is empty for all 11. The `base` output shows the filter does catch symbols when they are there.
- **L2/L3 (recomputed)**: I compared the `rec_*/links.txt` token lists in Python. For every Forthon extension,
  `fix` = `base` + exactly one `-fopenmp` at token 9, and `fix` == `wkld` token for token. `uedgeC` is identical in
  `fix` and `base`, and `wkld`'s `uedgeC` has 2 `-fopenmp`. `needed.txt` gives `fix` == `wkld`, with
  apipy/bbbpy/ppppy NEEDing `libgomp.so.1` and `uedgeC` NEEDing `libreadline.so.8 libc.so.6`. There are 0 `not
  found` and no libomp/libiomp in any `ldd.txt`.
- **L4**: `diff` of `rec_base-ser` against `rec_fix-ser` is empty for `needed.txt`, `links.txt`, `nm_omp.txt` and
  `ldd.txt`. The serial ppppy leaves `omp_get_thread_num_` and `omp_get_wtime_` unresolved in both (AIUE-67). All
  three imports in `import_other.txt` give exit status 0.
- **L5 CI replay**: `ci_step.log` shows 117 harness tests passed, the smoke line printed, and the Te-box flow ran
  5 runs, all `ok`. The jac arm is FAIL at te(4,18), report-only, which is expected on pre-AIUE-56 code.
  `OMP CI RESULT: PASS (exit 0)`.
- **L5 amendment**: the plan diff in `8a867c9` adds the amendment after the original L5 text and keeps that text.
  On timing, the commit is at 14:58:52. The scratch `thread_probe2.py`, `probe2_verdict.py` and
  `run_ubuntu64_probe2.sh` have mtimes of 14:59:04–14:59:18, the probe2 build log ends at 15:02:47, and the probe
  outputs are from 15:02:50 to 15:03:01. The threshold was therefore fixed before the run. The diagnostic (14:27)
  came before it (see I1-m2). The original failure is kept in `ubuntu/thread_probe.txt` and
  `ubuntu/thread_probe_full.log`. The full log matches the `.txt`: n0 = n1 = 2, `RESULT FAIL n1-n0 = 0`. The README
  has a FAIL row. The diagnostic `ubuntu_diag/driver.log` shows n equal to `OMP_NUM_THREADS` right after
  `import uedge` (1/2/4), so the original probe could not pass on any build, a correct one included. That makes the
  original a broken test, not a failed fix. I recomputed the verdicts: 5 × 5 314 835 = 26 574 175 ns, and the single
  N=2 worker had 53 501 586 (10.1× control). 5 × 10 314 332 = 51 571 660 ns, and the N=4 workers had a minimum of
  82 850 354 (8.0×). `OMPParallelJac` was 1 and there were 5 libgomp mappings. Every worker of the jac arm used 8–10×
  the CPU of the control's busiest worker. That is what review L1-m7 asked for: proof that the OpenMP workers took
  part during the Jacobian, beyond the libgomp mapping.
- **L6**: `debian/import.txt` shows exit status 0, gcc 12.2.0 and `as-needed` occurrences 3. `ldd_r_omp` is empty
  for all 11. NEEDED is identical to Ubuntu `fix`, all 11 link lines carry `-fopenmp`, and there are 0 `not found`.
  This agrees with AIUE-62 `build_info.txt` (`fixld` uses the `LDFLAGS=-fopenmp` workaround, and apipy, bbbpy and
  ppppy NEED libgomp).
- **M4**: see I1-M1 for the `D_only` and OpenMP-check comparisons. I read the deck's species setup in
  `uedge-pytests/pytests/fulltests/nonog_d_c-fb_16x8/input.py` (lines 28, 71–81, 107–114) to decide which variables
  rows 272 and 428 are. For the R1 and C2 descriptions I used AIUE-58's
  `docs/rca/AIUE-8-omp-jacobian-nondeterminism.md:81,373`.
- **Other places the change reaches**: `.github/workflows/build-test-wheel.yml` builds Linux wheels with
  cibuildwheel in the OpenMP default, where the change is now active. The plan lists this as owner-deferred and not
  claimed. Nothing in `CLAUDE.md` or `.claude/` describes the old Linux behaviour or the `LDFLAGS` workaround.
  `init-project` sets `LDFLAGS` only for macOS libomp.
- Runs stayed within the budget: read-only, plus `otool` and `nm` on the existing venvs. No builds, no Docker, no
  case runs.
