# AIUE-62 implementation review, round 1

Ticket AIUE-62, "Characterise the OpenMP Jacobian on Linux (libgomp), AIUE-54 follow-up" (epic AIUE-8). Branch
`feature/v9-AIUE-62-linux-characterisation` (838784e plan, 6987f5a records and scripts, 234fae7 RCA text), stacked on
`feature/v9-AIUE-55-omp-jacobian-rca`. Reference: the ticket acceptance criteria and
`.claude/plans/AIUE-62-linux-characterisation.md`.

## Verdict

**REVISE.** 0 BLOCKER, 2 MAJOR, 7 MINOR.

## Summary

The data are sound. I recomputed the decision-relevant verdicts from the scratch `record.npz` files with the reviewed
harness at `8ee189d`, and they match. `make_prefix_data.py` run on the scratch flows regenerates `stats.txt` byte for byte
and `runs.csv` up to row order. All 440 committed `record.json` files are identical to the run records. The link
failure finding (`GOMP_parallel`) is correctly diagnosed against `setup.py` and the build logs.

The problems are in how far the RCA text generalises. The headline "C2/M2 does not appear on x86-64" and option D,
titled "Linux x86-64 (the CI runner)", rest on Debian gcc 12.2 under Rosetta. The CI runner uses native Ubuntu 24.04
gcc 13.3, which was not measured. "Bitwise and deterministic in every Te configuration" is also contradicted by the
branch's own committed control records for the full problem at 8 threads (jac 0/5, jacrhs 3/5, non-deterministic,
from M3). Both are wording fixes, but they sit in the text the owner reads for decision 9.

## Findings

### MAJOR

**I1-M1. The x86-64 answer is presented as the CI runner's, but the measured toolchain is different.**
Location: RCA status line (l. 6-8); §Linux characterisation "C2/M2 on x86-64: absent"; AIUE-55 attribution sentence
(l. 201-202); option D row (l. 252) and the recommendation's D sentence (l. 258).
- Evidence: every measured build is Debian 12 `gfortran 12.2.0`, run under Rosetta (`build_info.txt`).
- `.github/workflows/build-test-omp.yml` (AIUE-57) builds with the system gfortran on `ubuntu-latest`, which is
  Ubuntu 24.04 `gcc 13.3.0` (the branch's own Ubuntu build log: `GNU Fortran (Ubuntu 13.3.0-6ubuntu2~24.04.1)`).
- That build was used only for the import check. No bitwise run was made with gcc 13 or on native x86 hardware.
- The RCA itself attributes C2 to compiler code generation ("arm64, gfortran 15 … how the vsoree loop is
  contracted"). On that hypothesis, the compiler version is exactly the variable that could bring C2 back on the CI
  runner.
- Option D is headed "Bitwise gate on Linux x86-64 (the CI runner)" and says "**measured (AIUE-62)**". The status
  line says "C2/M2 does not appear on x86-64" with no qualifier.
- Resolve with either of:
  - State the scope everywhere the answer is used: Debian gcc 12.2, `-O3`, emulated x86-64. Say that the CI runner's
    gcc 13.3 on native x86 is untested, and that the first green AIUE-57 run (after the link fix) is the confirming
    check.
  - Or run the Te box and full problem (K ≥ 5, 4 threads) in the Ubuntu 24.04 image with `LDFLAGS=-fopenmp`, and
    record the result.

**I1-M2. "Bitwise and deterministic in every Te configuration" is contradicted by committed records. The
per-configuration table omits them.**
Location: status line (l. 6); "C2/M2 on x86-64: absent" paragraph; AIUE-55 per-configuration table row l. 240
(`te, te_phi, ti, ni, ng, full | … | 2/4/8 | bitwise 2/2 per group (except full jacrhs 8: 1/2, M3)`); option D row
("bitwise and deterministic in every Te configuration").
- Evidence (`stats.txt` l. 2425-2469, rechecked from the npz):
  - `ctl_fix_t8_up_full_k5` full jac at 8 threads: 0/5 agree with serial, 5 distinct results.
  - The same flow's full jacrhs at 8 threads: 3/5 agree.
  - `fixtp` full jac at 8 threads: 2/5.
- The full problem at 8 threads is therefore neither bitwise nor deterministic on Linux. The cause is M3: every
  mismatch is an `up` row, and there are no Te-row mismatches.
- What the data do support: no Te-row difference in any post-fix Linux run (so the C2 signature is absent), and
  bitwise agreement except M3. Row l. 240 reports only the K=2 result for `full` at 8 threads (2/2 on jac) and leaves
  out the K=5 0/5. Option D's cost column mentions "full at 8 threads would gate red", but its result column and the
  status line say "bitwise and deterministic".
- Resolve: phrase the claim as "no Te-row (C2) difference in any post-fix run; not bitwise and not deterministic
  where M3 appears (`up` at ≥ 4 threads, `full` at 8 threads: jac 0/5, jacrhs 3/5 at K=5)". Add the K=5 8-thread
  numbers to row l. 240, or split `full` at 8 threads into its own row.

### MINOR

**I1-m1. The FMA control's conclusion is slightly stronger than the evidence.** Location: "Control: FMA on x86-64
does not bring C2 back"; option D row ("it is not 'no FMA' that matters but the platform's code generation").
- What the evidence supports: a gcc 12.2 `-mfma` build, with 2574 FMA instructions in `bbbpy` and changed serial
  results, still gives OpenMP = serial.
- It does not separate fused rounding from the other effects of `-mfma`:
  - `-mfma` implies AVX: `ymm` operands go from 0 to 2574 in `bbbpy`.
  - GCC may switch libmvec calls to the AVX2 variants, which can change the serial results on their own.
  - Rosetta's execution of FMA (fused or not) is not verified.
- The discriminating experiment (linux/arm64 native libgomp, which would separate ISA and compiler from the OpenMP
  runtime) was not run.
- "FMA contraction is not sufficient for C2" is acceptable if it is scoped to this compiler. "The platform's code
  generation" should be labelled a hypothesis, as the M3 section already does for its own mechanism.

**I1-m2. The M3 description is narrower than the data.** Location: §Linux characterisation, "New: M3"; Results-table row
"full / jacrhs 8; up jac 8, jacrhs 8"; per-configuration row l. 241.
- Columns. "Mostly of `up`, some of `ni`": in the full-problem M3 runs the columns also include `phi`, `ti` and `ng`
  (e.g. `ctl_fix_t8_up_full_k5` run0: up 14, ni 27, phi 4, ti 3), and they span iy-2..iy+2 at ix=0. That the rows
  are always `up[1]` at ix=1 is confirmed.
- Counts. "9-15 of the 27-48 differing entries" describes only the two `k2_all` `up` runs. Across the committed M3
  runs, the counts are 4-56 differing entries, 1-27 of them only in the OpenMP Jacobian.
- `fixtp`. "The rate is unchanged": full jac at 8 threads went 0/5 → 2/5 and jacrhs 3/5 → 1/5. At K=5 that is "not
  removed", not "unchanged".
- Row l. 241. It gives jac-arm rates for "jac, jacrhs". jacrhs was 2/2 at 2 and 4 threads (K=2) and 0/5 at 8; the
  static-chunk 5/5 is jac only.
- Results-table row. "PASS (up, worst 6.63e-10)" sits in a row that also lists the ungated `full` jacrhs 8.

**I1-m3. Crash count wording.** Location: "Pre-fix (C1) on Linux", last bullet: "`te` and `te_phi` jacrhs crash
(SIGSEGV) in 11 of 12 runs". The scratch run directories show 10 runs with no record (crash) and one
`RuntimeError` (`phi/jacrhs_t2/run0`); one run completed. The matrix row already says "SIGSEGV or RuntimeError".
Make the bullet match.

**I1-m4. Stale AIUE-54 intro.** Location: l. 305-309. The intro still says the Linux characterisation is "proposed to
be deferred to AIUE-62 (… the owner confirms …)" and "Until that run exists, nothing in this section says anything
about Linux". That is now contradicted by the Linux columns and rows added to the same section. Mark the paragraph as
historical, or update it.

**I1-m5. Reproducibility gaps in the committed scripts.** Location: `tests/deterministic_omp/linux/`.
- Not scripted. Each of these is only in `build_info.txt`/`flows.log`, or not recorded at all:
  - the `baseld`/`fixld` builds (`LDFLAGS=-fopenmp build_uedge.sh …`);
  - the no-`LDFLAGS` import check;
  - the Ubuntu check;
  - the `up_threads_k5`/`up_t8_static_k5` flows;
  - the `make_prefix_data.py` and gate invocations.
- `gate_flows.py` as committed differs from the version that produced `c1_gate.txt`: a `GATESCRIPT` argument was
  added afterwards. The logic is the same, but this should be disclosed.
- Pinning. `Dockerfile` uses `FROM python:3.11-bookworm` without the digest; the digest is only in `build_info.txt`.
  `forthon`/`h5py` are unpinned (the freeze is recorded).
- No README gives the run order, and `tests/deterministic_omp/README.md`'s file table doesn't list `linux/`.
- A short README with the exact command sequence, and the digest in `FROM`, would close this.
- I confirmed the records themselves are reproducible from the scratch flows: `stats.txt` is identical, and
  `runs.csv` is identical when sorted.

**I1-m6. The Ubuntu import-failure evidence is not saved.** `build_info.txt` quotes it as "(console output of the
check, not saved to a log)". The claim that the AIUE-57 job "would stop at its smoke test (exit 2) on `ubuntu-latest`"
rests on that unsaved output plus inference. Save the output (or re-run the import in the existing image), and word
the CI consequence as an inference.

**I1-m7. Some AIUE-54 tables have no Linux row.**
- The overflow-rate table (l. ~365-376) and the Newton-step table have no Linux row. The Linux numbers are in prose
  only: full jacrhs 0/2 overflow at 2, 4 and 8 threads, and 13/20 Newton steps.
- The matrix and the K=20 table, which the acceptance criterion names, do have Linux columns and rows, so the
  criterion is met.
- Either add a Linux row to these two tables or say they are covered in §Linux characterisation.

## Not independently verified (environment)

- Native x86-64 hardware and the CI runner's toolchain (Ubuntu 24.04 gcc 13.3). All runs are Rosetta-emulated
  Debian gcc 12.2. Rosetta's FP fidelity for FMA (fused rounding) and its memory-ordering and timing behaviour, which
  affect race visibility, cannot be checked here. To verify: one AIUE-57 run on `ubuntu-latest` after the link fix,
  or the Ubuntu-image run in I1-M1.
- The Ubuntu 24.04 import failure. The build log is saved, the import output is not (I1-m6).
- linux/arm64: not run by the author; nothing to check.
- The macOS comparison numbers quoted next to the Linux ones (e.g. "macOS 16 distinct", "10/10 overflow") come from
  the existing AIUE-54 sections. I checked that they match those sections' text, not their records.
- Per the run budget, no UEDGE or Docker runs were made.

## What was checked and how

- Diff: `git diff feature/v9-AIUE-55-omp-jacobian-rca..HEAD` (471 files; RCA +133/-17; scripts; 440 record JSONs;
  2.1 MB data). The worktree is clean.
- Recomputed with the reviewed harness (`AIUE-57` worktree at `8ee189d`, `compare.compare_records`), using a script
  at `/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/review62/recheck.py`:
  - fix full jac K=20: 20/20 agree, 1 distinct.
  - base Te box jac K=20: 0/20, 18 distinct.
  - fix Te box jac and jacrhs K=20: 20/20 each.
  - `fixfma` Te box jac and jacrhs 20/20, full 5/5; `fixfma` serial differs from `fixld` serial (fnrm
    0.3221264476514322 vs …488412611).
  - M3 `up` thread scan: 3/5, 2/5, 0/5, 0/5; static chunks 5/5, 1 distinct.
  - Serial references: `fixld` = `baseld` bitwise in all 8 configurations; K=20 = K=2 serial.
- M3 localisation (`m3loc.py`, same directory): every mismatch row is `up[1]` at ix=1, with columns at ix=0. Column
  equations and counts are as in I1-m2. `sfscal`, `suscal` and fnrm are equal in all jac-arm runs.
- `make_prefix_data.py` (unchanged) re-run on all 12 scratch flows: `stats.txt` identical, `runs.csv` identical after
  sorting.
- All 440 committed `records/**.json` compared with the scratch `record.json` (JSON equality): 0 differences.
- C1 gate. `c1_gate_summary.txt` was checked against `c1_gate.txt`. The gate script used (scratch copy) is identical
  to `1553e75:docs/reviews/AIUE-56-c1-gate.py`.
- Link finding:
  - The `bbbpy` link line in `build_base.log` has no `-fopenmp`, while the `uedgeC` link line has it (from
    `setup.py:799`, `extra_link_args=FLAGS['CARGS']`).
  - `fma_fixld.txt` NEEDED lists: libgomp only in `bbbpy`/`ppppy`/`apipy`, and not in `uedgeC` even with
    `LDFLAGS=-fopenmp` (`--as-needed`).
  - `import_default_ldflags.txt` shows `undefined symbol: GOMP_parallel` for both default builds.
- No-FMA evidence:
  - The `fma_scan.sh` regexes were read.
  - 0 `vf*madd/sub*`, `ymm` and `zmm` in all 11 extensions of the default build; the compile flags are the same with
    and without `LDFLAGS`.
  - The `-mfma` counts match `build_info.txt`.
- Commits:
  - `3865c79` is in `origin/v9-develop`, and `0fac655..3865c79` changes only docs.
  - `4fae2f9` is an ancestor of `1553e75`, and `3865c79..1553e75` changes only `ppp/omp_parallel.F90` in product code.
  - Every record's provenance shows harness `8ee189d` with a clean harness tree, and a source head of `1553e75` or
    `3865c79` as expected (dirty only for the two control builds).
- RCA numbers checked against `stats.txt`:
  - Te box: fnrm range and 15 distinct, nnz 175-182, extra 6-13, `sfscal` 18-19, max |J|.
  - Full: one fnrm value 1.535419111984408, nnz 3,686,595-3,695,034, extra 500,960-509,399, 0 missing, `sfscal` 2940.
  - jacrhs: 13/20 Newton steps; full jacrhs fnrm and `yldot` counts at 2/4/8 threads.
  - Matrix columns against both `flow_summary.md` files.
  - K=20 rows, including 17 distinct for Te box jacrhs.
- The macOS columns of the AIUE-54 matrix and the K=20 table are unchanged (diff shows only appended columns and
  rows). The recommendation still names E/F and treats D as conditional, so the text is neutral on decision 9 apart
  from I1-M1/M2.
- `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`: `OK`, exit 0. Its listed citing docs come
  from the stacked base branches, and none describes anything AIUE-62 changed.
- `uv run .claude/hooks/change_kind.py --range feature/v9-AIUE-55-omp-jacobian-rca..HEAD`: `OK`. It finds only
  artifacts plus test scripts under `tests/deterministic_omp/linux/`, and no skill, agent, hook or settings changes.
