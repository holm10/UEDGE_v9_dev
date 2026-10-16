# AIUE-64 implementation review, round 2

Stage: implementation. Ticket AIUE-64, "OpenMP build does not import on Linux: extensions linked without -fopenmp"
(epic AIUE-8). Reference: the approved plan `.claude/plans/AIUE-64-omp-linux-link.md` with its L5 amendment
(`8a867c9`). Branch `bugfix/v9-AIUE-64-omp-linux-link` at `cd29a53` (round 1 reviewed `a738e92`). Worktree
`/Users/holma/Documents/uedge/src/uedge-wt/AIUE-64`. Response: `docs/reviews/AIUE-64-implementation-round1-response.md`.

## Verdict

**APPROVE** (0 BLOCKER, 0 MAJOR, 1 MINOR).

## Summary

Round 2 changes only records, review text and the plan. No product file has changed since the fix commit `1e8eb78`.
The README now has an M4 row and an "M4 in detail" section. Both are marked as deviating from the pre-registered
expectation and identical on base. They quote the `D_only` failures, the fnrm lines and the two `>>>>` mismatch lines
verbatim, and every one of those matches the scratch validate logs byte for byte. The attribution now reads
"consistent with AIUE-58 R1 (not shown)". The PR notes carry the same text. The pre-registered L5 amendment is
unchanged, with a post-run note added below it. The `build_log_line.txt` counts match all 14 scratch build logs. All
four round-1 findings are resolved. One cosmetic minor remains in a new record file.

## Findings

### BLOCKER

None.

### MAJOR

None.

### MINOR

**I2-m1. `validate/d_only.txt` has two empty sections.** The headings "fix: fnrm result lines (Returned/Reference,
plus their traceback source lines)" and the matching "base:" heading have nothing under them. The fnrm lines appear
later, under "fix: fnrm lines verbatim (identical on base)". The record is still correct, because the diff sections
and the verbatim block carry the content. A reader may think something is missing, though. *Resolution (optional):*
drop the two empty headings or add one line saying where the lines are.

## Status of previous findings

- **I1-M1 (M4 missing from the committed record): resolved.**
  - The README has an M4 row ("Deviates from the pre-registered expectation ...; identical on base") and an "M4 in
    detail" section. `docs/reviews/AIUE-64-pr-notes.md` repeats the same content under "Validation that did not come
    out green".
  - `D_only`. I compared against the scratch `validate/d_only.log` and `validate/d_only_base.log`:
    - The summary line `5 failed, 120 passed, 1 warning` is the same in both logs.
    - The `FAILED` lists are identical (`diff` empty), and the five names match the README.
    - `ValueError: operands could not be broadcast together with shapes (10,6,2) (10,6)` occurs 3 times in each log,
      which matches "Three of them".
    - The 10 `Returned/Reference fnrm` lines in `d_only.txt` are byte-identical to the log, and the fix and base
      fnrm lines are identical.
  - OpenMP check:
    - The committed `omp_check.txt` table matches the scratch `omp_repeat.txt` line for line.
    - The two `>>>>` lines in the README and the PR notes match `rep/*.log` exactly (272: `1.1658757793646371E-011`;
      428: `4.3812075279923317E-009`), in all six runs.
    - I re-diffed `rep/AIUE-64-omp_i.log` against `rep/base-omp_i.log` after removing NULs. For i = 1, 2, 3 the only
      differences are the two "Serial Evaluation of jacobian done in: ... s" timing lines. That supports "identical
      once NULs and timing lines are removed".
    - The committed `scripts/omp_check.py` and `omp_repeat.sh` are identical to the scratch copies.
  - One-off exits:
    - `omp_check_AIUE-64-omp.log` ends after the banner, with no "Reading" line.
    - `~/Library/Logs/DiagnosticReports/gtimeout-2026-10-15-151128.ips` has the quoted `captureTime`, `exception`
      (`SIGTRAP`) and `termination` (`byProc gtimeout`) lines verbatim. Exit 133 = 128 + 5 is consistent with this.
    - `omp_check_AIUE-64-omp_r2.log` ends with `RuntimeError: diff in rhsnk`, as stated.
    - The python report the record rules out (`python3.13-2026-10-14-150202.ips`, mtime 15:11 on 10-15) has
      `captureTime 2026-10-14 15:02:01`, `SIGSEGV` and `H5FL_garbage_coll`, as stated.
  - Attribution: both the README and the PR notes say "consistent with AIUE-58 R1 (not shown)", note that the
    Jacobians are identical, and give the Ti-row reading. This is the wording round 1 asked for.
  - Validate build facts:
    - The scratch `build_head.txt` is `a738e92`, and the build exit codes are 0/0.
    - The warning-line counts are 315 (OpenMP) and 308 (serial), on both `validate/` and `mac_before/`. They match
      `build_smoke.txt` and the README.
- **I1-m1 (macOS "before" commit): resolved.** The README states that the macOS "before" build is at `1adea93`, with
  the same product tree as `4faed39`, and quotes the `git diff` (checked empty in round 1). It also states that the
  Linux `base` builds cloned `4faed39`.
- **I1-m2 (amendment wording and the 5× factor): resolved.**
  - `git diff a738e92..cd29a53 -- .claude/plans` adds 7 lines only. The pre-registered amendment text is untouched.
  - The new post-run note says that "no region during `exmain`" was inaccurate. It gives the control's 5.3 ms and
    6.0–10.3 ms, and states that the 5× factor was chosen after the diagnostic ("fixed before the run, but not
    blind").
  - The README's L5 row carries both caveats and the ratios 10.1× and ≥ 8.0×. These match my round-1 recomputation.
- **I1-m3 (log-line checks on uncommitted logs): resolved.** I re-ran `grep -c` for the log line on all 14 scratch
  build logs:
  - It is 1 in `linux/{ubuntu,ubuntu_diag,ubuntu_probe2,debian}/build_fix.log`.
  - It is 0 in the Ubuntu `base`, `wkld`, `base-ser` and `fix-ser` logs, in the four `mac_before`/`mac_after` logs
    and in the two `validate/` logs.
  - The matching line text, `Linux OpenMP build: linking the Forthon extensions with LDFLAGS='-fopenmp'`, is the same
    in all four logs where it appears.
  - All of this matches `build_log_line.txt`, and the README says the logs themselves are not committed.

## Not independently verified (environment)

- **The exit codes 133 and 139.** They still come only from the driver shell's printout ("Exit codes as printed by
  the driver shell"), and the record says so. Both are consistent with the files: the gtimeout SIGTRAP report fits
  133, and the r2 log, which stops right after the `RuntimeError`, fits 139.
- These items are unchanged from round 1:
  - the Linux Docker runs themselves (I checked records and scratch logs, no re-run);
  - native x86-64 CI;
  - Linux wheels (owner-deferred);
  - arm64 Linux;
  - non-`--as-needed` distributions;
  - `CC=clang` on Linux.

## What was checked and how

- **Product unchanged since `1e8eb78`:**
  - `git diff --name-only 1e8eb78..cd29a53` outside `docs/` and `.claude/` lists 0 files.
  - `git diff --stat a738e92..cd29a53` touches only `docs/` and `.claude/plans/AIUE-64-omp-linux-link.md`. No skills,
    agents or hooks change.
  - The worktree is clean.
- **Context refs:** `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` from the worktree prints
  the usual re-read list and `OK`, with exit 0.
- **Records against scratch:** `diff`, `grep -c` and `tr -d '\000'` on the files in
  `/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/5faeea63-d2a3-45e8-a9fe-5854bff514ed/scratchpad/aiue64/{validate,linux,mac_before,mac_after}/`,
  as described under each finding above. The crash reports were read with `grep`.
- **PR notes:** I read `docs/reviews/AIUE-64-pr-notes.md` in full. Its M4 text, the quoted `>>>>` lines, the
  attribution wording and the one-off exits match the README. Its "Not tested" list and the AIUE-67 follow-up match
  the plan and round 1.
- **Budget:** read-only. No builds, no runs and no Docker.
