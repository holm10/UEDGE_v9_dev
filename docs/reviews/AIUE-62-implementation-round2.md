# AIUE-62 implementation review, round 2

Ticket AIUE-62, "Characterise the OpenMP Jacobian on Linux (libgomp), AIUE-54 follow-up" (epic AIUE-8). Branch
`feature/v9-AIUE-62-linux-characterisation`, tip `9a7b8a1` (round 1 reviewed `234fae7`). Reference: the ticket
acceptance criteria, `.claude/plans/AIUE-62-linux-characterisation.md`, the round-1 report and the authors' response
`docs/reviews/AIUE-62-implementation-round1-response.md`.

## Verdict

**APPROVE.** 0 BLOCKER, 0 MAJOR, 2 MINOR (both optional).

## Summary

Round 1 found two MAJOR problems. I1-M1: the x86-64 answer was presented as the CI runner's, but the only toolchain
measured was Debian gcc 12.2. I1-M2: the text said "bitwise in every Te configuration", which the M3 records
contradict. The authors fixed both. For I1-M1 they ran the Te box and the full problem in the Ubuntu 24.04 / gcc 13.3
image. I recomputed those verdicts from the scratch records with the reviewed harness (`8ee189d`), and they match: Te
box jac 5/5, Te box jacrhs 5/5, full jac 5/5, one distinct result per group. The Ubuntu serial references are bitwise
equal to the Debian ones. The scope sentence now appears at every place where the x86-64 answer is used, and the M3
exception is stated with the K=5 8-thread numbers. All seven minors are resolved. The two new minors are wording
slips with no effect on the owner's decision.

## Findings

### BLOCKER

None.

### MAJOR

None.

### MINOR

**I2-m1. Two scope labels were left behind by the new Ubuntu run.**
- `docs/rca/AIUE-8-data/linux/build_info.txt:5` still labels the Ubuntu image "(link check only)". That image now
  also produced the `ubuntu_fix_k5_*` bitwise records.
- The AIUE-8 status table row at RCA l. 320 says "(x86-64; arm64 not run)" without "emulated". Every other use of
  the answer carries the scope sentence.
- Resolve: relabel the image in `build_info.txt`, and add "emulated" (or the scope sentence) to the l. 320 row.

**I2-m2. "The C1 gate's deviation is 0 in all Debian Te runs" (RCA l. 83) is literally false for the M3 runs of the
full problem.**
- `c1_gate_summary.txt` has `ctl_fix_t8_up_full_k5__full__jac_t8`: worst_dev 3.04e-10, 0/5 runs with zero
  deviation. It also has `ctl_fixtp_t8_up_full_k5__full__jac_t8`: worst_dev 3.52e-10, 2/5.
- The next sentence names these runs as M3, and the Results table (l. 59) gives the 3.04e-10. So nothing is hidden,
  but this sentence on its own overclaims.
- Resolve: e.g. "in all Debian Te runs except the M3 runs below".

## Status of previous findings

| Finding | Status | Evidence |
|---|---|---|
| I1-M1 (x86-64 answer presented as the CI runner's) | **Resolved** | The author took both options: the Ubuntu run, and the scope sentence. **Ubuntu run.** The reviewed harness `compare.compare_records` on `scratchpad/linux/ubuntu2/fixld/` gives: `k5_tebox` jac_t4 5/5 agree, 1 distinct; jacrhs_t4 5/5, 1 distinct; `k5_full` jac_t4 5/5, 1 distinct. **Provenance** (every record): `GCC: (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0`, glibc 2.39, x86_64, source `1553e75` clean, harness `8ee189d` clean. **Serial references.** Ubuntu serial vs Debian `fixld` serial agrees in all 7 sections (including `jacobian:post_exmain`) for Te box (vs K=20 and vs K=2) and full (vs K=20 and vs K=2). fnrm 0.3221264488412611 and 1.918820629909679, the same on both. **C1 gate.** `ubuntu/c1_gate_summary.txt`: PASS, worst_dev 0, 5/5 zero deviation in both jac groups. **Committed files.** All 17 committed Ubuntu record JSONs equal the scratch `record.json` files. `make_prefix_data.py` re-run on the two Ubuntu flows reproduces the 15 new `runs.csv` rows (sorted, byte-equal) and the added `stats.txt` blocks; the only differences are the file header and section headers already present in the merged file. **FMA scan.** `ubuntu/fma_fixld.txt` (identical to scratch): 0 FMA, 0 `ymm`/`zmm` in all 11 extensions, `bbbpy` 842 911 instructions. **Scope sentence.** Present in the status line (l. 6), the §Linux intro (l. 20, "every Linux statement below"), the C2 paragraph (l. 77), the AIUE-55 attribution (l. 218), option D (l. 273), and as a short form ("emulated x86-64 … native CI hardware untested") in the recommendation (l. 279-281). The per-configuration rows name the toolchain. The l. 20 and option D text names the first green AIUE-57 run after AIUE-64 as the native check. (Small leftover: I2-m1.) |
| I1-M2 ("bitwise and deterministic in every Te configuration") | **Resolved** | Status line, C2 paragraph and option D now say: no Te-row difference post-fix; bitwise and deterministic except where M3 appears (`up` ≥ 4 threads; `full` at 8 threads: jac 0/5, jacrhs 3/5 at K=5). The per-configuration table has its own `full` 8-thread row (l. 260), plus `up` jac and jacrhs rows. The Results table has a `ctl_fix_t8_up_full_k5` row. From `runs.csv`, I get: fix `full` jac 8 K=5 0/5, jacrhs 3/5; K=2 jac 2/2, jacrhs 1/2; `up` jac 4/5/6/8 3/5, 2/5, 0/5, 0/5; `up` jacrhs K=2 2/2, 2/2, 0/2, and K=5 at 8 threads 0/5; static 5/5. No post-fix dataset has a Te mismatch row (all 58 non-base mismatches with `mismatch_row_eqs` set are `up`; the 97 `te` mismatches are all in base datasets). (Small leftover: I2-m2.) |
| I1-m1 (FMA control conclusion) | Resolved | Scoped to "gcc 12.2 on emulated x86-64". The caveats (AVX/libmvec, Rosetta fusion, arm64 not run) are added, and the code-generation explanation is labelled *Hypothesis, not shown* (l. 87-95, and option D). |
| I1-m2 (M3 description) | Resolved | Recounted from `runs.csv`: 58 runs with `up`-only mismatches (`ctl_fix_t8_up_full_k5` 17, `ctl_fixtp_t8_up_full_k5` 17, `ctl_fix_up_threads_k5` 15, `amd64_fix_k2_all` 5, `amd64_base_k2_all` 4); `jac_entries_differ` 4-60, `jac_extra` 1-32, as stated. `fixtp` numbers (up 0/5, 0/5; full jac 2/5, jacrhs 1/5) match and are worded as "not removed". The static chunks are marked "jac arm only". The Results-table row is split, and jacrhs is "not gated". |
| I1-m3 (crash wording) | Resolved | `runs.csv`: 10 `te`/`te_phi` jacrhs runs "no record … exit -11", 1 `error: RuntimeError` (`phi/jacrhs_t2/run0`), 1 ok (`phi/jacrhs_t8/run0`). Matches the new bullet. |
| I1-m4 (stale AIUE-54 intro) | Resolved | Updated (l. 324-328). The pre-run text is marked *Historical*. |
| I1-m5 (reproducibility) | Resolved | `tests/deterministic_omp/linux/README.md` gives the files, the run order including the no-`LDFLAGS` builds, the `up` flows, `make_prefix_data.py` and the gate, and the disclosed deviations. Both `FROM` lines are pinned to the digests in `build_info.txt`. The `linux/` row is added to `tests/deterministic_omp/README.md`. The committed scripts are byte-identical to the scratch copies that were run, except `gate_flows.py` (disclosed) and the Dockerfiles (digest pin only). |
| I1-m6 (Ubuntu import evidence) | Resolved | `ubuntu/import_default_ldflags.txt` is identical to the scratch copy: `undefined symbol: GOMP_parallel`, exit 127, gcc 13.3, 3 `as-needed` in the specs. It is produced by the committed `run_ubuntu.sh`. The CI consequence is now worded "(inferred …)". |
| I1-m7 (Linux rows in other tables) | Resolved | Linux rows added to the overflow/Newton-step table (l. 392-393). The values match round 1's checks (13/20, 6.17e30-9.16e30; full jacrhs 0/2 at 2/4/8 with the fnrm values). |

**Ticket keys.** On the branch, AIUE-64 is always the link bug and AIUE-65 is always M3: status line, l. 34/39,
l. 97/112, per-configuration table, option D, recommendation, AIUE-8 status table, and `linux/README.md:31`. "To be
filed" no longer appears. No other worktree or the planning worktree uses AIUE-63..66 for anything else. I could not
confirm that these Jira issues exist (no Jira access).

## Not independently verified (environment)

- **Native x86-64 hardware and the GitHub `ubuntu-latest` runner.** Both toolchains were run under Rosetta. Rosetta's
  FP fidelity and its memory-ordering and timing behaviour (which affect race visibility) cannot be checked here. The
  RCA now names this gap and the confirming check: the first green AIUE-57 run after AIUE-64. The owner decides
  whether that check is enough.
- **Ubuntu run versus CI.** The Ubuntu run used the image's system Python 3.12; CI uses `setup-python` 3.11. The RCA
  discloses this. It does not change the Fortran build flags (the compile lines in `fma_fixld.txt` match the Debian
  ones apart from paths), but it was not tested.
- **The image digest.** I did not check that the Ubuntu image used for the round-2 run was built from the digest now
  pinned in `Dockerfile.ubuntu`. The scratch Dockerfile has an unpinned `FROM ubuntu:24.04`, and the digest comes
  from the original image record. The records' compiler and glibc strings are consistent with that image.
- **Jira.** Whether AIUE-64 and AIUE-65 exist and say what the RCA says.
- **Run budget.** No UEDGE or Docker runs were made.

## What was checked and how

Scripts are in `/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/review62r2/`.

- `git diff 234fae7..9a7b8a1`: 37 files, all docs, data, review files and test scripts. The worktree is clean.
- `ubu.py` (imports `recheck.group` from round 1) with the AIUE-57 harness at `8ee189d`, which has a clean tree. It
  computes the Ubuntu verdicts, the serial cross-checks and the provenance.
- `jsoncmp.py`: compares the committed Ubuntu JSONs with the scratch `record.json` files (17 files, 0 differences).
- `cmp` of the committed `ubuntu/{import_default_ldflags,fma_fixld,flows.log,freeze_fixld}.txt` with
  `scratchpad/linux/ubuntu2/`: all identical.
- `make_prefix_data.py` re-run on `ubuntu_fix_k5_tebox=fixld/k5_tebox ubuntu_fix_k5_full=fixld/k5_full`, then
  compared with the new `runs.csv` rows and the `stats.txt` hunks.
- `m3count.py` and `rates.py` on `runs.csv`: the M3 run count and ranges, and the agree rates per group, for every
  number in the rewritten M3, C2 and per-configuration text.
- `c1_gate_summary.txt` (Debian and Ubuntu): the worst-deviation values quoted in the Results table, and I2-m2.
- `grep -n "x86\|Linux"` over the RCA: the scope sentence at each use. `git grep -E "AIUE-6[3-9]|to be filed"` over
  the branch, and `grep -rn` over the other worktrees: the key consistency.
- `run_ubuntu.sh` read against `ubuntu/flows.log` and `driver.log` (the same build and flow commands). Committed
  scripts `cmp`'d against `scratchpad/linux/docker*/`.
- `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`: `OK`, exit 0. Its list of citing docs
  comes from the stacked base branches. `.claude/context/testing.md` cites `tests/deterministic_omp/README.md`, which
  only gained a table row and is still true.
- `uv run .claude/hooks/change_kind.py --range feature/v9-AIUE-55-omp-jacobian-rca..HEAD`: `OK`, exit 0. It finds
  only artifacts (RCA, data, reviews, the plan) and "product" test scripts and READMEs under `tests/deterministic_omp/`.
  There are no skill, agent, hook, settings, `CLAUDE.md`, `.github`, `setup.py` or Fortran changes on the branch.
