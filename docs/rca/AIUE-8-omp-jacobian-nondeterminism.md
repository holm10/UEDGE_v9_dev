# AIUE-8: Non-deterministic OpenMP Jacobian (RCA working document)

Status: shared-state scan (AIUE-50), characterisation (AIUE-54) and the Jacobian RCA (AIUE-55) done; the Phase 2
exit decision is **open for the owner** (decision 9, §Jacobian RCA → Exit decision: bitwise is reachable without
changing serial via an OpenMP-only replay, at an estimated +18–35 % Jacobian cost; fixed chunk boundaries
gave run-to-run reproducibility without replay at 4 threads, empirically). Linux x86-64 characterised (AIUE-62; Debian gcc 12.2 (K=20) and Ubuntu 24.04 gcc 13.3 (K=5), both emulated x86-64 under Rosetta; native CI hardware not run): with the AIUE-56
fix no post-fix run has a Te-row (C2/M2) difference; runs are bitwise equal to serial and deterministic except where a
separate, smaller residual M3 (AIUE-65: `up` rows at the plate, ≥ 4 threads, pre-existing) appears. The default
OpenMP build does not import on Debian/Ubuntu (AIUE-64). RHS section (AIUE-58) to follow.

Epic AIUE-8. Reproducer: `tests/deterministic_omp/` (AIUE-46). All results below except §Linux characterisation
(AIUE-62) and the Linux rows marked as such were obtained on macOS arm64,
gfortran 15.2, Homebrew LLVM clang/libomp, `v9-develop` at `0fac655`, `OMP_STACKSIZE=512M`, a fresh process per run,
`python -I` with an empty `HOME`. "Serial" means a reference run of the same build with `OMP_NUM_THREADS=1` or the
`--serial` build, as stated.

## Linux characterisation (AIUE-62)

Linux x86-64 with libgomp, in Docker on this Mac (`linux/amd64`, Rosetta emulation, `--cpus 5`; one container at a
time). **Scope of every Linux statement below: Debian gcc 12.2 (K=20) and Ubuntu 24.04 gcc 13.3 (K=5), both emulated x86-64 under Rosetta; native CI hardware not run.** The
first green AIUE-57 run on `ubuntu-latest` (after the AIUE-64 link fix) is the confirming check on native hardware. Data: `docs/rca/AIUE-8-data/linux/` — every run's `record.json` (`records/<data set>/…`), `runs.csv` and
`stats.txt` written by `make_prefix_data.py` unchanged (renamed from `prefix_*`, since they also hold post-fix
data), each flow's `flow_summary.md`, `flows.log` (commands and wall times), `c1_gate.txt`/`c1_gate_summary.txt`
(the AIUE-56 gate script, unchanged, on every Jacobian-arm group) and `build_info.txt` (images, compiler, flags,
objdump counts, link evidence). Scripts, Dockerfiles and the run order: `tests/deterministic_omp/linux/` (`README.md` there). `record.npz` arrays stay
in the session scratch directory. **linux/arm64 (native libgomp) was not run** (stopped at the build step for time).

- **Environment.** `python:3.11-bookworm` (pinned by digest in the `Dockerfile`), gfortran/gcc 12.2.0 (Debian), Python 3.11,
  `numpy==1.26.4`, the CI command `python -m pip install -v .` (default OpenMP build: `-O3`, no `-march`). Harness:
  the reviewed one at `feature/v9-AIUE-57-omp-ci-job` `8ee189d`. Builds: `base` = `origin/v9-develop` `3865c79`
  (product code = `0fac655`), `fix` = AIUE-56 `1553e75`. Serial references are bitwise equal between the two builds
  in all 8 configurations, and between flows. Ubuntu 24.04 (`Dockerfile.ubuntu`, gcc/gfortran 13.3.0, Python 3.12): the fix build
  only (`ubuntu/`, data sets `ubuntu_fix_k5_*`), the same harness and `LDFLAGS=-fopenmp`.
- **The default OpenMP build does not import on Debian or Ubuntu (AIUE-64).** `import uedge` stops with `bbbpy…so: undefined
  symbol: GOMP_parallel` (Debian 12 gcc 12, and Ubuntu 24.04 gcc 13.3, the CI runner's distribution). Forthon links the
  package extensions without `-fopenmp`; only `uedgeC` gets it, and the distributions' `--as-needed` default drops
  `libgomp` there too. So the AIUE-57 job's smoke test would fail on `ubuntu-latest` (inferred from the
  Ubuntu 24.04 image; saved in `ubuntu/import_default_ldflags.txt`). **Every Linux build here used `LDFLAGS=-fopenmp`**; that is the only deviation from the CI command.
  (Product fix: link the extensions with `-fopenmp`, AIUE-64; not in this ticket.)
- **No FMA in the x86-64 build.** `objdump -d` of all 11 extensions: 0 `vf*madd/sub*` instructions and 0 `ymm`/`zmm`
  operands (Debian base and fix builds, `bbbpy` 808 359 instructions; Ubuntu fix build, `bbbpy` 842 911). The emulated CPU advertises `fma avx avx2`, so glibc may pick
  FMA variants of `exp`/`log` at run time; those are pure functions of their arguments. The build does call glibc
  `libmvec` (`_ZGVbN2v_exp/log/cos`, `_ZGVbN2vv_pow`) from vectorised loops.

### Results (4 threads unless stated; agree = bitwise in every compared quantity, as in §Characterisation)

| Data set | Configuration / arm | Runs | Agree with serial | Deterministic | C1 gate (AIUE-56) |
|---|---|---|---|---|---|
| `amd64_base_k20_tebox` | `tebox` / jac | 20 | **0/20** | no (18 distinct of 20) | FAIL 20/20 |
| `amd64_base_k20_tebox` | `tebox` / jacrhs | 20 | **0/20** (13 took a Newton step) | no | — |
| `amd64_base_k20_full` | `full` / jac | 20 | **0/20** | no (20 distinct) | FAIL 20/20 |
| `amd64_fix_k20_tebox` | `tebox` / jac | 20 | **20/20** | yes | PASS, deviation 0 in 20/20 |
| `amd64_fix_k20_tebox` | `tebox` / jacrhs | 20 | **20/20** | yes | — |
| `amd64_fix_k20_full` | `full` / jac | 20 | **20/20** | yes | PASS, deviation 0 in 20/20 |
| `amd64_fix_k2_all` | `tebox`, `te`, `ti`, `ni`, `ng`, `phi` (`te_phi`), both arms, 2/4/8 threads | 2 per group | **2/2 in every group** | yes | PASS, deviation 0 |
| `amd64_fix_k2_all` | `full`, both arms, 2/4 threads; jac 8 threads | 2 per group | 2/2 | yes | PASS, deviation 0 |
| `amd64_fix_k2_all` | `full` / jacrhs 8 | 2 | 1/2 (M3) | no | not gated (jacrhs) |
| `amd64_fix_k2_all` | `up` jac 8, jacrhs 8 | 2 each | 0/2; 0/2 (M3) | no | jac: PASS, worst 6.63e-10 × row max |
| `ctl_fix_t8_up_full_k5` | `full` jac 8, jacrhs 8; `up` jac 8, jacrhs 8 | 5 each | 0/5; 3/5; 0/5; 0/5 (all M3) | no | jac: PASS (worst 3.04e-10 full, 6.63e-10 up) |
| `ubuntu_fix_k5_tebox`, `ubuntu_fix_k5_full` (Ubuntu 24.04 gcc 13.3) | `tebox` jac, jacrhs; `full` jac | 5 each | **5/5; 5/5; 5/5** | yes | PASS, deviation 0 in 10/10 |
| `amd64_base_k2_all` | as `k2_all` on macOS (below) | 2 per group | 0/2 in `tebox`, `full`, `te`, `phi`; 2/2 in `ti`, `ni`, `ng`; `up` 2/2 at 2/4 threads, 0/2 at 8 | — | FAIL in every Te group |

**Pre-fix (C1) on Linux** reproduces the macOS picture, with three differences (from `stats.txt`):
- Te box jac: iteration-0 `fnrm` 0.1322747614580312 – 0.181059468674829 (15 distinct; serial 0.3221264488412611,
  nnz 169), nnz 175–182, `sfscal` 18–19 rows, max |J| 2.22e43–2.60e43, `yldot` equal 20/20, pattern a superset of
  serial's (6–13 extra, 0 missing).
- **Full problem: one iteration-0 `fnrm` in all 20 runs** (1.535419111984408; serial 1.918820629909679, nnz 3 185 635)
  where macOS had 16 distinct values; nnz 3 686 595 – 3 695 034 (20 distinct), 500 960 – 509 399 extra entries and
  **0 missing** (macOS: 225–1736 missing), `sfscal` 2940 Te rows, `yldot` equal 20/20, max |J| 5.98e43. The missing
  entries and the `fnrm` spread on macOS are the C2 noise on top of C1; on x86-64 only the C1 corruption varies.
- RHS arm: the Te box took a Newton step in 13/20 runs (macOS 18/20). The full problem's jacrhs arm did **not**
  overflow at 2 threads (0/2; macOS 10/10): `fnrm` 1.535419111984453 (2 threads), …467/…468 (4), …466/…479 (8);
  `yldot` differs in 1514 / 2176 / 2548–2582 Te entries plus 345 opposite-sign zeros. `te` and `te_phi` jacrhs fail in 11 of
  12 runs (10 SIGSEGV with no record, 1 RuntimeError in `te_phi` at 2 threads; one `te_phi` run at 8 threads
  completed), as on macOS.

**C2/M2 on x86-64: no Te-row difference in any post-fix run** (Debian gcc 12.2 (K=20) and Ubuntu 24.04 gcc 13.3 (K=5), both emulated x86-64 under Rosetta; native CI hardware not run). With
the AIUE-56 fix and the default `-O3` (no FMA instructions), no OpenMP run differs from serial in a Te row:
Debian Te box 20/20 bitwise on both arms, full problem 20/20, and every Te group of `flow --all` (K=2, 2/4/8
threads); Ubuntu 24.04 gcc 13.3 (`ubuntu_fix_k5_*`): Te box 5/5 bitwise on both arms, full problem 5/5,
deterministic, C1-gate deviation 0; its serial references are bitwise equal to Debian's, and its 11 extensions have 0
FMA instructions and 0 `ymm`/`zmm` operands (`ubuntu/fma_fixld.txt`) (macOS, same fix: Te box 1/30, full 0/30 at 4
threads). The C1 gate's deviation is 0 in all Debian Te runs except the M3 runs (full at 8 threads: ≤ 3.5e-10). **Bitwise and deterministic except where M3 appears:**
`up` at ≥ 4 threads, and the full problem at 8 threads (K=5: jac 0/5, jacrhs 3/5, non-deterministic,
`ctl_fix_t8_up_full_k5`; K=2: jac 2/2, jacrhs 1/2); every one of those mismatches is in `up` rows.

**Control: FMA on x86-64 does not bring C2 back** (`fixfma`, `-mfma` added: 2574 FMA instructions in `bbbpy`).
Serial results change (Te box `fnrm` 0.3221264488412611 → 0.3221264476514322; full 1.918820629909679 →
1.918820628546987, nnz 3 185 635 → 3 186 351), yet OpenMP equals serial: Te box 20/20 (both arms), full 5/5. So, **with gcc 12.2 on emulated x86-64**, FMA
contraction is not sufficient for C2. Caveats: `-mfma` also enables AVX (`ymm` operands 0 → 2574 in `bbbpy`) and may
switch the libmvec variants, so it does not isolate fused rounding; whether Rosetta executes FMA fused was not
verified; and linux/arm64 (which would separate ISA and compiler from the OpenMP runtime) was not run. *Hypothesis,
not shown:* the trigger on macOS is specific to that code generation (arm64, gfortran 15, e.g. how the vectorised and
scalar versions of the `vsoree` loop are contracted). The AIUE-55 result (`-ffp-contract=off` removes C2 on arm64)
stands.

**New: M3 (AIUE-65), an up-row residual at the inner plate (Linux, ≥ 4 threads, pre-existing).** Not C1, not C2:
- Where: rows always `up[1]` at ix=1; columns at ix=0 (the plate cell) over iy−2…iy+2, of `up` and `ni` and, in the
  full problem, also `phi`, `ti`, `ng` (review round 1 localisation). 4–60 differing entries per run, 1–32 of them
  only in the OpenMP Jacobian (58 M3 runs in `runs.csv`: base, fix and `fixtp` builds). `sfscal`, `suscal`, `yldot`, the
  probe and `fnrm` stay equal. Size ≤ 6.63e-10 × the serial row max (C1 gate PASS on the jac arm; the jacrhs arm is
  not gated).
- Rate (fix build, agree with serial): `up` jac 4 threads 3/5, 5 threads 2/5, 6 threads 0/5, 8 threads 0/5 (K=2: 0/2);
  `up` jacrhs 2/2 at 2 and 4 threads (K=2), 0/5 at 8; full problem jac 8 threads 0/5 (K=5) and 2/2 (K=2), jacrhs 8
  threads 3/5 (K=5) and 1/2 (K=2); full jac 4 threads 20/20. Present in the **base** build as well (`up` at 8
  threads, 0/2 on both arms). Not seen on macOS (`up` passed in every run there).
- Not removed by making `areapl` `+threadprivate` (F16, `fixtp`, K=5 at 8 threads): `up` jac 0/5, jacrhs 0/5; full jac
  2/5 (fix: 0/5), jacrhs 1/5 (fix: 3/5). At K=5 that is "not removed", not a measured rate change.
- Gone with fixed contiguous chunks (`OMPJacNchunks=-1`, `OMPAutoBalance=0`): `up` jac 8 threads **5/5 agree,
  deterministic** (`ctl_fix_up_t8_static_k5`; jac arm only). That points at column history (as for C2) rather than a
  data race, but it is not shown.
- A follow-up (AIUE-65) should test: linux/arm64 (libgomp vs x86-64); the replay prototype (AIUE-61) on `up`; a
  carrier search like AIUE-55's (state left by a column whose box contains ix=0); K ≥ 20 rates at 4 threads for the
  full problem.

**Timing (emulated x86-64, 5 CPUs, not a CI budget):** full problem serial 49–54 s, 4 threads 17–24 s per run; Te box
3–5 s; `flow --all` K=2 with `--max-jobs 1` 1011–1077 s; builds 190–235 s (`flows.log`, `build_info.txt`).

**Not run:** linux/arm64; `--itermx` flows; the jacrhs arm of the full problem at K=20 (AIUE-54 ran jac only).

## Jacobian RCA and Phase 2 exit decision (AIUE-55)

Sources: §Characterisation (AIUE-54), §Shared-state scan (AIUE-50) and its adversarial review, the AIUE-56 plan
reviews, and the experiments below (all macOS, OpenMP build, Jacobian-only arm unless stated; scratch outputs are
referenced, not committed).

### Root causes

| ID | Root cause | Mechanism | Evidence | Fix | Effect on serial | Ticket |
|---|---|---|---|---|---|---|
| **C1** | `OMPJacBuilder` copies threadprivate **arrays before scalars** (`ppp/omp_parallel.F90:681-693`) | The generated `OmpCopyPointer<var>` writes `(1:n)` on each worker with the worker's own threadprivate `n`. For the 12 `api` `Imslwrk` spline arrays (`api/api.v:145-172`) `n` is a threadprivate scalar that `splinem` (`api/apip93.m:101-107`, from `bbb/odesetup.m:1130,1150`) sets on the master only, so on the first OpenMP Jacobian the workers hold element 1 (knots: 1:5) and zeros. `emissbs` then gets `B3VAL`'s out-of-range 0 and returns 1.0 instead of ~1.9e-35: the `isimpon=7` fixed-fraction radiation, which enters only the Te residual (`bbb/pandf_plasma_energy.m:822,1117`), is wrong in every column a worker builds. | E1–E3 (§Shared-state scan); independent review: exactly these 12 arrays across all packages, the swap alone removes the gross corruption; afracs=0 removes it on the unmodified build (00:35 experiment); the second Jacobian of a session is correct (E2) because the scalars were copied after the arrays the first time | Copy the scalars first (AIUE-56) | None: the routine runs only with `ParallelJac=1` in the OpenMP build | AIUE-56 |
| C1-RHS | The same stale worker state is used by the parallel RHS | `OMPPandf1Rhs` (`ppp/omp_parallel.F90:900-997`) never copies; its workers run on whatever the last `OMPJacBuilder` copy left | Te box `jacrhs`: all 25 Te rows of `yldot` wrong, fnrm ≈ 8e30, an extra Newton step; the swap build matches serial on that arm (AIUE-50 review) | Fixed by the same swap for the Jacobian-then-RHS sequence nksol uses | None | AIUE-56 (validated there); remaining RHS issues → AIUE-58 |
| F16 | `areapl` (`bbb/bbb.v:951`) is written in the plate BCs during `pandf` but is not `+threadprivate` | A data race on physics state (CLAUDE.md rule 1 for the `pandf` tree) | Static/dynamic scan (F16); not seen to change results so far | Mark `+threadprivate` | None (serial build unaffected; OpenMP build with switches 0 unaffected) | AIUE-60 |
| (races) | Timers, `TimingPandfOn`, `com.nfsp` written in `pandf`, not threadprivate | Lost timer updates; every thread writes the same `nfsp` | TSan on the swap build | Optional cleanup | None | AIUE-60 |
| **C2** (M2) | Column-to-column history in the serial loop: stale threadprivate values that a column reads outside its recomputed box (carrier `vsoree`, `bbb/pandf_plasma_energy.m:613-619`), triggered by local-vs-full-row rounding differences (FMA contraction — *inferred*, assembly not inspected). OpenMP workers start their first chunk from the fresh full-RHS state (later chunks from whatever the thread's previous chunk left), so they don't share serial's history | ulp history → finite-difference noise entries | emulation, carrier search; `-ffp-contract=off` → bitwise; **replay of the preceding `ubw` columns per chunk → bitwise, serial unchanged** (below) | **reproduce the history** (OpenMP-only replay; serial unchanged) or remove the trigger (changes serial) | replay: **none**; flag/history-free columns: round-off change | AIUE-61 |

### Residual after C1 (M2) and its mechanism C2

Measured with the scratch swap build (`venvs/AIUE-50-swap`), reviewed harness core, 4 threads; the pre-registered
AIUE-56 gate script (`docs/reviews/AIUE-56-c1-gate.py` on the AIUE-56 branch) on the same runs:

| Case | Mismatches vs serial per run | Where | Size | Varies run to run | C1 gate |
|---|---|---|---|---|---|
| Te box (25 eq), K=3, dynamic chunks | 1–2 | row te(ix=4,iy=20), cols te(3,21)/te(4,21) | ≤ 5.6e-10 × serial row max | yes (one run bitwise equal to serial) | PASS |
| Te box, one contiguous chunk per thread (`OMPJacNchunks=-1`, `OMPAutoBalance=0`), no replay | 2 | same | same | **no: the runs are bitwise identical to each other** (replay control `te_contig_R0`, 3/3; `m2/tebox_static.txt`) | — |
| Full problem, K=3 | 860–1040 (reviewer saw up to 1217 in 26 Te rows) | Te rows only, every column equation (te/ni most); ~600–800 are entries serial has and OpenMP lacks | ≤ 4.6e-9 × serial row max (e.g. 110.015618 vs 110.015617) | yes (1600–1800 between two OpenMP runs) | PASS |

`sfscal`, `suscal`, the iteration-0 `fnrm` and `get_fnrm` are bitwise equal to serial in all these runs (the row
max-norm hides entries this small).

**P3-m3 (is the serial Jacobian history-independent?)** Two experiments. (a) Same state, different history
*outside* the loop: 40 random local `pandf` evaluations (yl restored), followed by a full `pandf`, before `exmain` →
bitwise identical Jacobian. The trailing full `pandf` recomputes everything, so this only shows that history outside
the loop is wiped by the full RHS at the start of `exmain`; it does not test column order. (b) Column order was not
permuted directly; instead the emulation below starts columns from a different state (fresh per chunk) — that changes
the Jacobian. So the serial Jacobian **does** depend on the history inside its column loop. Note: a second `exmain` in a session gives a different Jacobian than the first (known UEDGE behaviour, a state
change, not noise), so "fresh vs second" is not a history test.

**M2 mechanism: history inside the serial column loop, from FMA contraction (C2).** (AIUE-50 follow-up
investigation; scratch scripts and outputs in the session scratchpad `m2/`.)

1. *Emulation.* A Python re-implementation of `jac_calc` (`bbb/oderhs.m:1012-1241`, column loop `:1095-1226`) around `bbb.pandf`, in serial
   column order, reproduces the `exmain` Jacobian bitwise (169/169 entries, Te box). Inserting a fresh `pandf(-1,-1)`
   at the start of each of 2 or 4 chunks — what an OpenMP worker effectively does — reproduces exactly the OpenMP
   residual (2 entries in row te(4,20)), with no threads involved. The extra `isjacreset` call of `LocalJacBuilder`
   (`ppp/parallel.F90:323`) changes nothing.
2. *Carrier.* Of ~110 variables that differ between "state after serial columns 1..c−1" and "fresh state", only
   `bbb.vsoree` is sufficient: 2 cells differ by 1 ulp, although every input of `vsoreec` there (`psorc`, `psorrgc`,
   `erliz`, `erlrc`, `edisse`) is bitwise equal. The same expression (`bbb/pandf_plasma_energy.m:613-619`;
   `vsoree = vsoreec` at `:644`, `iseesorave=0`) gives a different last bit when it runs in a 2–3-cell local loop than
   in the full-row loop. That ulp survives the restoring evaluation and is read by later columns: columns that don't
   touch a row then yield `(wk−yldot00)/dyl` noise (the 4.5e-5 entries serial has and OpenMP doesn't, and the ~1e-7
   relative value differences).
3. *Confirmation.* With `-ffp-contract=off` added to the Fortran flags (plus the C1 swap): the emulation is
   history-free; the OpenMP Jacobian is **bitwise equal to serial in 3/3 Te-box and 3/3 full-problem runs at 4
   threads, and the OpenMP runs are bitwise equal to each other** (full problem nnz 3 177 289, `fnrm`
   `0x1.eb37d433e0603p+0`).
4. *Effect on serial.* The flag changes serial results: Te box `fnrm` 0.3221264477609989 → 0.32212644885863323
   (3.4e-9 relative); full problem `get_fnrm` `0x1.eb37d428ec4f0p+0` → `0x1.eb37d433e0603p+0`, nnz 3 190 290 →
   3 177 289 (13 001 noise entries gone), and all 25 Te-box `yldot`/`sfscal` entries change. The effect on the pytests
   suites (`rtol=1e-5`) was not measured.
5. *OpenMP-only remedy: replay.* (Reviewer's emulation, then a threaded prototype; scratch, session scratchpad
   `replay/`, tree `uedge-wt/AIUE-61-replay`.) Before its first column, each chunk replays the restoring local
   `pandf(xc,yc)` of the R columns preceding it (yl unperturbed), so the worker reaches serial's state.
   - Emulation, full problem: R = `numvar` 479 mismatches (4 chunks), one grid row (1036) 162, two rows (2072) 0 for 4
     chunks but 84 for 8; **R = `ubw` (= `mu` = 3920) 0 for 8 and 16 chunks** (4 chunks not emulated at R = `ubw`; already 0 at R = 2072). Proposed rule: R = `ubw` (the columns
     whose Jacobian band reaches the chunk's first column).
   - Threaded prototype (`LocalJacBuilder` warm-up, scratch switch `OMPJacReplay`; the worker loop otherwise mirrors
     serial `jac_calc`), reviewed harness, 4 threads, K=3, same build's serial reference: Te box with contiguous
     chunks R=25 **AGREE 3/3, deterministic**; Te box with the default one-column chunks R=25 AGREE 3/3; full problem
     with 16 contiguous chunks (`OMPAutoBalance=0`) R=3920 **AGREE 3/3** (Jacobian, `sfscal`, `fnrm`), deterministic.
     Controls without replay fail. The build's serial equals `base-serial` bitwise (Te box, full problem): serial
     unchanged by construction.
   - Cost (**estimates**, except where marked measured): R extra local evaluations per chunk start, i.e. about
     T·`ubw` extra against ~2·neq ≈ 89k in the Jacobian for T chunks: ≈ +18 % at one chunk per thread on 4 threads,
     ≈ +35 % on 8 threads (≈ 4.4 % × T). This configuration was **not run** (the full problem with one chunk per
     thread segfaults, below), nor emulated at R=`ubw` with 4 chunks; the cost of leaving the default dynamic,
     auto-balanced schedule is not included. *Measured:* 16 chunks, +16–19 s per full-problem run, from two
     whole-process timings per arm (repeats vary by ~9 s). The default one column per chunk (`OMPJacNchunks=0`) would be
     ≈ 2000× (estimate), which is unusable, so a production fix needs OpenMP-only chunk construction with few
     contiguous chunks. The measured Jacobian times PRD §9 asks for are pending (AIUE-61).
   - Scope of the evidence: one Jacobian evaluation per run, 3 runs, 4 threads, Te box and full problem only (scratch
     commits: Te-box rows at `918bdb6`, re-run by the reviewer at `db6a8ea`; full-problem rows at `db6a8ea`). The
     epic's ≥ 3 Newton iterations at 2/4/8 threads are not shown. The worker loop still makes `LocalJacBuilder`'s
     extra `isjacreset` call, which serial doesn't; AIUE-61 decides that deliberately.
   - **Pre-existing crash found on the way:** on the full problem, `OMPJacNchunks≠0` segfaults at the start of the
     parallel loop. The Te box runs fine with `OMPJacNchunks=-1`, so the crash depends on problem size. Inferred cause
     (from the `ulimit` workaround; no backtrace kept): the automatic arrays `iJacColCopy` and `rJacElemCopy`
     (`ppp/omp_parallel.F90:672,675`) are made `firstprivate` at `:713-714` and sized `nnzmxperchunk` at `:321`; the
     master thread's private copies live on the 8 MB main-thread stack, which `OMP_STACKSIZE` doesn't size. Worked
     around for the prototype with `ulimit -s 65520`, `OMPlenpfac=2`. A production fix moves these to the heap.

So: **the serial Jacobian depends on the history inside its column loop, and bitwise OpenMP = serial is reachable
without changing serial results** — by reproducing that history on the workers (replay), an OpenMP-only change
(PRD §9: "chunking, resets and copy coverage … in scope without escalation"). The estimated cost (≈ 4.4 % × T for one chunk per thread: ≈ +9 % at 2 threads,
+18 % at 4, +35 % at 8; not measured) exceeds 10 % from 4 threads on, which is a §9 *report to the owner*, not a §9(a) escalation. Removing the trigger instead (`-ffp-contract=off`,
history-free columns) also reaches bitwise but changes serial. The FMA attribution is inferred (identical inputs plus
the flag's effect); arm64/gfortran 15 only. AIUE-62 (Debian gcc 12.2 (K=20) and Ubuntu 24.04 gcc 13.3 (K=5), both emulated x86-64 under Rosetta; native CI hardware not run): no post-fix Te-row (M2)
difference on Linux x86-64, also with `-mfma` on gcc 12.2, so FMA instructions alone did not produce it there
(§Linux characterisation).

Ruled out as M2 carriers: `areapl` (bitwise equality reached while it is still shared — it stays a real race to
fix), the `isjacreset` call, the `emissbs`/`B3VAL` work arrays and `emcoef`, non-local Te BCs, the clip index.

### Refuted or minor hypotheses

| # | Hypothesis / lead | Verdict |
|---|---|---|
| H1 | History-dependent per-thread state | Part of the residual's character (varies with column→thread mapping); not the gross error |
| H2 | Race on shared state written in `pandf` | No `.v` floating-point array; only `areapl` (F16) and timers/flags — not the gross error |
| H3 | `save`d locals / post-DATA changes | `fmombal` SAVE arrays exist, but `fmombal` is reached only through `mombal` (`isimpon=5`), not for this deck (6/7) — a hazard for `isimpon=5`, AIUE-60; C1 is a post-DATA threadprivate scalar problem, found via H6 |
| H4 | Timing-dependent partitioning | Modulates which columns land on workers (hence run-to-run variation); not a cause |
| **H6** | Uninitialised / incompletely copied worker state | **Confirmed: C1** |
| L1 | `isimpon=7` radiation sink | **Confirmed as the carrier of C1** (emissbs on zero tables) |
| L2 | `wk`/`yl_check` partly initialised | Ruled out: only the always-initialised `ii1:ii2` range is read |
| L3 | `OMPTimeLocalJac` indexed by thread | Affects load balancing only |
| — | Clip index `sfscal(iv)` (parallel) vs `sfscal(ii)` (serial) | No effect here (`jaccliplim=0`); a latent inconsistency for `jaccliplim>0` — AIUE-60 |
| — | `del` vs `delperturb` | Both 1e-8 |

### Exit decision (decision 9) — for the owner

Question (PRD §9(b), decision 9): is bitwise equality with serial reachable for every tested configuration? **Yes for
the configurations tested so far (one evaluation, 4 threads, Te box and full problem), without changing serial — by the
OpenMP-only replay remedy (prototype), at an estimated cost above the 10 % report threshold.** No §9(a) escalation is needed for that path. What the owner decides is which path
to take and whether the cost is acceptable; the evidence per option:

**Per configuration, thread count and arm (macOS):**

| Configuration | Arm | Threads | C1 fix alone (AIUE-56) | + replay R=ubw (prototype) | `-ffp-contract=off` (+ C1) | static partition, no replay (F) |
|---|---|---|---|---|---|---|
| `ti`, `ni`, `up`, `ng` | jac | 4 | **bitwise 5/5** (AIUE-56) | not run (no residual to remove) | not run | not run |
| `tebox` | jac | 2 / 4 / 8 | 1/5 / 1/30 / 0/5 bitwise; C1 gate PASS | 4 threads: **3/3** (contiguous and default chunks) | 4 threads: **3/3** | 4 threads: 0/3 bitwise vs serial, runs identical to each other 3/3 |
| `full` | jac | 2 / 4 / 8 | 2/5 / 0/30 / 0/5; C1 gate PASS | 4 threads, 16 chunks: **3/3** | 4 threads: **3/3** | 4 threads, 16 chunks: 0/2 vs serial, 2 runs identical |
| `te`, `te_phi` | jac | 4 | 0/5; C1 gate PASS | `te_phi` **3/3** (addendum); `te` not run | `te_phi` **3/3**, also 5 Newton its; `te` not run | not run |
| `tebox`, `full` | jacrhs | 4 | yldot/fnrm equal serial; Jacobian residual only | not run | not run | not run |
| any | any | 2 / 8 | — | not run | not run | not run |
| `tebox`, `full` | jac (both arms for `tebox`) | Linux x86-64 (Debian gcc 12.2), 4 | **bitwise 20/20 each** (AIUE-62) | not needed | not run | not run |
| `tebox` (both arms), `full` (jac) | as stated | Linux x86-64 (Ubuntu 24.04 gcc 13.3), 4 | **bitwise 5/5 each** (AIUE-62, K=5) | not run | not run | not run |
| `te`, `te_phi`, `ti`, `ni`, `ng`, `full` | jac, jacrhs | Linux x86-64 (Debian), 2 / 4 / 8 | **bitwise 2/2 per group** (K=2), except `full` jacrhs 8: 1/2 (M3) | not needed | not run | not run |
| `full` | jac, jacrhs | Linux x86-64 (Debian), 8 | M3 (AIUE-65): jac 0/5, jacrhs 3/5 (K=5), non-deterministic; no Te-row difference | not run | not run | not run |
| `up` | jac | Linux x86-64 (Debian), 4 / 5 / 6 / 8 | M3: 3/5, 2/5, 0/5, 0/5 (K=5) | not run | not run | 5/5 at 8 threads, deterministic |
| `up` | jacrhs | Linux x86-64 (Debian), 2 / 4 / 8 | 2/2, 2/2 (K=2); 0/5 at 8 (K=5, M3) | not run | not run | not run |
| any | any | Linux arm64 | not run | not run | not run | not run |

| Option | What | OpenMP vs serial | Serial results | Cost / risk |
|---|---|---|---|---|
| **E. Replay** (OpenMP-only): few contiguous chunks + replay of the preceding `ubw` columns per chunk; heap-allocated per-chunk arrays (fixes the `OMPJacNchunks≠0` crash) | reproduces serial's history on the workers | bitwise and deterministic where tested (Te box, full, 4 threads) | **unchanged** | estimated ≈ 4.4 % × T Jacobian work at one chunk per thread (+18 % at 4 threads; not measured; reported per §9); needs OpenMP-only chunk construction (the default switch values stay); remaining configurations/threads/arms and Linux to be shown |
| A. `-ffp-contract=off` for the Fortran build | removes the trigger | bitwise and deterministic where tested | **changes** (fnrm 3.4e-9 relative; every Te-box yldot) → declared change of defaults, references re-blessed; pytests effect not measured | speed effect not measured |
| A′. the flag only on the `pandf` tree | narrower A | expected same (not shown) | changes in those files | per-file build rules |
| C. History-free columns (restore from a saved full-RHS state) | removes the history in both loops | bitwise expected | changes at round-off | larger change in `jac_calc` + `LocalJacBuilder` |
| B. **Tolerance gate** (keep the C1 build, default dynamic chunks) | none | not bitwise, **not deterministic** with the default dynamic, auto-balanced chunks (full problem: two runs differ in 70 entries, `replay/t_c1_dflt_1` vs `_2`) — so it does **not** meet PRD §11's fallback; usable only as an interim CI gate | unchanged | gate: AIUE-56's bounds; measured serial-history spread ≤ 5.6e-10 × row max (Te box) and ≤ 4.6e-9 (full) — the 1e-6 bound is a margin over that, not derived from it |
| F. **Static partition + tolerance** (candidate §11 fallback): contiguous chunk boundaries fixed (`OMPAutoBalance=0`), no replay; heap per-chunk arrays (crash fix as in E). **As tested, chunks are still handed out by `schedule(dynamic,OMPLoopJacNchunk)` (`ppp/omp_parallel.F90:712`, `OMPLoopJacNchunk=1`) and worker state carries from chunk to chunk, so which history a chunk starts from depends on the timing-dependent assignment**; a production F needs `schedule(static)` with one chunk per thread, or a fixed worker state at every chunk start | removes the run-to-run variation (empirically), not the residual | not bitwise vs serial (Te box: the same 2 entries every run; full, 16 static chunks: 5698 entries vs serial; AIUE-56 tolerance gate PASS on those records, worst 4.59e-9 × row max) but **bitwise identical between runs where tested** (Te box 3/3; full `t_c1_n16_1` vs `_2`): consistent with PRD §11's fallback at 4 threads on this evidence; reproducibility is empirical, not guaranteed, with the tested scheduling | unchanged | tolerance as in B; load-balance cost of static scheduling not measured; 2/8 threads, fresh CI sessions and Newton iterations not shown. Unlike F, E rebuilds the history whichever thread runs a chunk |
| D. Bitwise gate on Linux x86-64 | none | **measured (AIUE-62; Debian gcc 12.2 (K=20) and Ubuntu 24.04 gcc 13.3 (K=5), both emulated x86-64 under Rosetta; native CI hardware not run):** no Te-row (C2) difference in any post-fix run (Debian: Te box 20/20, full 20/20, `--all` K=2; Ubuntu: Te box 5/5 both arms, full 5/5); bitwise and deterministic except where M3 (AIUE-65) appears: `up` at ≥ 4 threads, `full` at 8 threads (jac 0/5, jacrhs 3/5 at K=5), ≤ 6.6e-10 × row max. Also with `-mfma` on gcc 12.2 (hypothesis: C2 depends on the arm64/gfortran 15 code generation, not on FMA alone) | unchanged | platform-dependent: macOS arm64 keeps C2; the M3 groups would gate red; the default Linux OpenMP build does not import without `LDFLAGS=-fopenmp` (AIUE-64); native CI hardware untested — the first green AIUE-57 run after AIUE-64 is the confirming check |

**Recommendation (owner to accept or reject):** E if bitwise agreement with serial is wanted (AIUE-61: OpenMP-only,
serial untouched; cost estimated at ≈ +18 % on 4 threads and ≈ +35 % on 8, to be measured). F if the PRD §11 fallback
(bitwise reproducibility plus a tolerance against serial) is enough: cheaper, also OpenMP-only, also needs the crash
fix, and needs a fixed chunk-to-thread mapping (`schedule(static)`, one chunk per thread) or a worker-state reset at
each chunk start to make the reproducibility guaranteed rather than empirical. B only as the interim CI gate until E or F lands (AIUE-57's `OMP_CI_JAC_TOLERANCE` switch). D: AIUE-62 measured it on emulated x86-64 (no
Te-row difference post-fix; not bitwise where M3/AIUE-65 appears; the CI build needs the AIUE-64 link fix; native CI
hardware untested). A only if the owner prefers changing the build over the replay cost.

### Addendum (owner questions, after review round 4): effect on Newton solves, and phi

Scratch runs, macOS, 4 threads (session scratchpad `q1/`, `q4/`); not reviewed.

**Does the residual show up in fnrm?** The full problem as the deck leaves it (`dtreal=1e20`) never converges even
in serial (30 Newton iterations, fnrm 1.65–1.83, `iterm=4`), so its trajectory is no test. With `dtreal=1e-9`
(`rundt`'s default step), 5 fixed time steps, the Jacobian recomputed every step:

| Build / arm | Runs | Step 1 converged | Newton iterations per step | Final state vs serial | Final fnrm |
|---|---|---|---|---|---|
| serial (C1 build) | 2 | 2/2 | 21, 4, 3, 4, 3 | bitwise between the two runs | 7.645e-10 |
| replay prototype, 16 chunks, R=3920 | 2 | 2/2 | 21, 4, 3, 4, 3 | **bitwise equal to serial**, all 5 steps | 7.645e-10 |
| replay build, serial arm | 1 | 1/1 | same | bitwise equal to serial | 7.645e-10 |
| OpenMP, C1 fix only | 5 | **3/5** | 21/20/21, 3, 3, 4, 3 | max rel. diff 1e-11 (te, ti, ng), up to 2e-9 (ni) and 1e-8 (phi) | 1.1e-9 to 5.2e-9 |
| serial with `-ffp-contract=off` (+ C1) | 1 | **0/1** | 30, failed | — | 0.42 |

So: in a well-converging step the difference stays at round-off (1e-11 relative, 1e-8 for phi). But the first,
hard step (fnrm wanders for ~17 iterations before converging) is sensitive to round-off: 2 of 5 OpenMP runs did not
converge in 30 iterations where serial did. An equally valid serial build (`-ffp-contract=off`) didn't converge
either, so this is the solve's sensitivity to round-off, which the residual exposes. In a `rundt` run it would show up
as a different time-step history from run to run. The printed fnrm agrees with serial to 6–9 digits in the first
iterations and then drifts. Only the replay remedy reproduced serial's trajectory exactly.

**Does phi add a problem of its own?** No, on this evidence (`te_phi` preset, isteon+isphion, neq 6336):
- C1 build: all Jacobian mismatches are in Te rows (5/5 runs; none in phi rows); `yldot`, the parallel-RHS probe,
  `sfscal` and fnrm equal serial (jac and jacrhs arms).
- `-ffp-contract=off` build: **bitwise equal to serial**, jac arm 3/3, jacrhs arm 3/3, and over 5 Newton iterations
  3/3. The replay build (4 contiguous chunks, R=1000 ≥ `ubw`): Jacobian bitwise 3/3.
- C1 build over 5 Newton iterations: the fnrm sequence drifts (1.5671 vs 1.5711 at iteration 1), as for Te alone.

### Fix tickets

| Root cause | Ticket | Status |
|---|---|---|
| C1 (copy order; also the RHS arm) | AIUE-56 | fix committed on `bugfix/v9-AIUE-56-omp-jacobian-fix`; validation: static hazards 12 → 0, defaults bitwise unchanged (serial check, 42 cases, both builds), C1 gate PASS in every Te configuration, no slowdown |
| F16 `areapl` race, timer/flag races, clip-index inconsistency, `emcoef` `copyin` (benign), `fmombal` SAVE arrays (`isimpon=5`) | **AIUE-60** | not started |
| C2 / M2 (history inside the column loop) + the `OMPJacNchunks≠0` stack crash | **AIUE-61** | prototype shows option E works; production fix pending the owner's choice of path |
| Linux characterisation, FMA on x86-64 | **AIUE-62** | done on `feature/v9-AIUE-62-linux-characterisation` (emulated x86-64; arm64 not run). New: M3 (`up` rows, Linux) → **AIUE-65**; the Linux OpenMP build's missing `libgomp` link → **AIUE-64** |

## Characterisation before any fix (AIUE-54)

**Platform: macOS only** in this section; the Linux x86-64 runs of the same commands are in §Linux characterisation
(AIUE-62), and their K=2 columns and K=20 rows are added to the matrix and the K=20 table below; the Newton-step and
overflow numbers for Linux are in that section's text. *Historical (written for AIUE-54):* no Linux host was
available then, and the Linux characterisation (`flow --all --repeats 2`, `flow --configs tebox|full --threads 4
--repeats 20` on a libgomp-only build, PRD R4) was deferred to AIUE-62, which has now run it on emulated x86-64.

Build: OpenMP build of `v9-develop` `0fac655` (`venvs/base-omp`), macOS arm64, gfortran 15.2, Homebrew LLVM
clang/libomp. Every run is a fresh `python -I` process with an empty `HOME` and `OMP_STACKSIZE=512M`. "Serial" is a
reference run of the same build with both OpenMP switches 0. Unless stated, a run is one evaluation (`ftol=1e20`: the
`sfsetnk` Jacobian and the iteration-0 residual). **"Agree"** means bitwise equal in every compared quantity:
- the post-`exmain` Jacobian, pattern and values;
- `sfscal` and `suscal`;
- `fnrm`, both the final value's hex and every printed value;
- `ijactot`;
- `yldot` and the RHS probe. Here a difference in the sign of a zero is allowed only when the RHS ran in parallel
  (PRD P3-m2).

### Data and provenance

Everything below is generated from the committed data in `docs/rca/AIUE-8-data/`:
- `records/<data set>/…/<run>.json`: every run's `record.json`, including the failed runs. The `record.npz` arrays
  stay in the session scratch directory; the full-problem ones are 59 MB each.
- `prefix_runs.csv`: one row per run, with the harness commit, status, `ijactot`, the iteration count, the
  iteration-0 and last printed `fnrm`, which Jacobian is stored, and mismatch counts per section against the run's
  serial reference.
- `prefix_stats.txt`: per-group numbers. Every number in this section comes from this file or from the CSV, except:
  the `ci_base_pr` overflow counts (AIUE-57 scratch records), the `v56` and AIUE-57 timings (AIUE-56/AIUE-57
  validation records), the build-log times, and the phi serial logs (session scratchpad `phi/`).
- `make_prefix_data.py`: the script that wrote all three from the run directories (it needs the `.npz` files).

| Data set | What | Harness commit | Machine load (1-min average) |
|---|---|---|---|
| `k2_all` | AIUE-52 acceptance run `flow --all --repeats 2`: 8 configurations × 2 arms × 2/4/8 threads, 104 runs | `fbe0adf` (AIUE-49 core) plus the AIUE-52 flow code, then uncommitted | 10–40 |
| `k20_tebox`, `k20_full` | `flow --configs tebox` / `--configs full`, `--threads 4 --repeats 20` | `5fb700b`: the AIUE-52 tip before its round-1 review, which was later rebased away. That is before the flow's arm check | ~40 (full) |
| `ctl_base_t4_k3` | Pre-fix controls for AIUE-56: `check --arm jac --threads 4 --repeats 3`, for the same 8 configurations | `de57d59` (reviewed AIUE-49 core) | 60–180 |
| `r54_new` | This revision: the PRD §6.3 Te-box rows, and timings with `--itermx 3` | `de57d59` | 24–113 |
| `k2_extra` | `full`/jacrhs runs from the other one-evaluation K=2 flows, used only for the overflow rate: `acc_all_k2` (the first `--all` run) and `quick`, both `fbe0adf`; `r1/quick` (`5fb700b`); `rev52/quick` (the AIUE-52 reviewer's run) | as listed. A failed run writes no provenance | 10–40 (`acc_all_k2`, `quick`); not recorded for the others |

- **No false agree.** All 197 records that completed have `ParallelJac`, `ParallelPandf1`, `Nthreads` and
  `OMP_NUM_THREADS` as their arm requires. Every one of them holds `sfscal`, `suscal`, `yldot` and `yldot_probe`. So
  the harness versions from before the arm check (`fbe0adf`, `5fb700b`) produced no "agree" for an arm that did not
  take effect.
- **Paths.** The harness (`tests/deterministic_omp/harness/`) is not on this branch: it lives on
  `feature/v9-AIUE-49-omp-harness-core` (core) and `feature/v9-AIUE-52-omp-test-flow` (flow). The AIUE-52 record
  cited below is `docs/reviews/AIUE-52-validation.txt` on `feature/v9-AIUE-52-omp-test-flow`. Merge order: AIUE-49,
  AIUE-52, then this branch.

### Which runs took a Newton step (read this before the tables)

`ftol=1e20` stops `nksol` after iteration 0 only if the iteration-0 `fnrm` is at most 1e20. When the parallel RHS
makes it larger, `nksol` takes a step:
- the log shows `npe = 2` and `OMP iter= 1`;
- the record has `ijactot = 2` and two entries in `iterations`.

The stored Jacobian, `nnz`, `sfscal`, `yldot` and `fnrm_final` then come from the **later** iteration. That Jacobian
is the row-normalised one: max |entry| = 1.0 in all 18 such K=20 runs. It is therefore not comparable with serial's
iteration-0 Jacobian. The CSV column `stored_jacobian` marks these runs. Where a group mixes the two kinds, the
tables below report them separately.

| Configuration / arm | Threads | Iteration-0 `fnrm` > 1e20 | Outcome |
|---|---|---|---|
| `tebox` / jacrhs | 4 (K=20) | **18/20**: 4.9e30 – 1.005e31 | The step recovers: last printed `fnrm` 0.0043–0.207. The other 2 runs (run5, run14) are ordinary: 0.1645, 0.1670 |
| `tebox` / jacrhs | 2 / 4 / 8 (K=2) | 1/2, 2/2, 2/2 | as above |
| `tebox` / jac | 1, 2, 4, 8 | 0 of all 46 runs | — |
| `full` / jacrhs | 2 | **10/10** (`k2_all`, `k2_extra`): 1.7e24 – 1.31e31 | every run stops with `overflow: SVR routine lusol0 loop 40` |
| `full` / jacrhs | 4 | **4/10**: `acc_all_k2` 2/2 (1.9e25, 9.9e25), `rev52/quick` 2/2 (2.5e30, 1.8e26) | the 4 stop with the lusol0 overflow. In the other 6 (`k2_all`, `quick`, `r1/quick`) `fnrm` is 1.535419111648416–…429 |
| `full` / jacrhs | 8 | 0/4 (`k2_all`, `acc_all_k2`) | `fnrm` 1.535419111648427–…441 |
| `full` / jac, and every other configuration and arm whose iteration 0 completed | all | 0 | — |
| **Linux x86-64 (Debian)** `tebox` / jacrhs | 4 (K=20) | **13/20**: 6.17e30 – 9.16e30 | last printed `fnrm` 0.0879–0.198; the other 7 runs ordinary |
| **Linux x86-64 (Debian)** `full` / jacrhs | 2 / 4 / 8 (K=2) | **0/2, 0/2, 0/2** | no overflow; `fnrm` 1.535419111984453 (2), …467/…468 (4), …466/…479 (8) |

So the RHS-arm overflow on the full problem is a rate, not a 2-thread effect: 10/10 at 2 threads, 4/10 at 4, 0/4
at 8. With `--itermx 3`, the AIUE-57 CI run `ci_base_pr` overflows in 2/2 runs at 2 threads and 2/2 at 4 threads.
One of those 4-thread runs had an ordinary iteration-0 `fnrm` (1.535419111648428) and overflowed in a later
iteration. The earlier text of this section gave "fnrm 2.4e31". That value came from `acc_all_k2` run0, which
printed `0.2395993421575909E+31`, so it is in fact 2.4e30, and it was misread. The runs the matrix cites
(`k2_all`) have 6.06e30 and 1.74e24.

### Matrix: every configuration, both arms, 2/4/8 threads (K=2 fresh runs each, `k2_all`)

`phi_te` was a temporary preset equal to the committed `te_phi` (Te and phi on). "Entries" counts Jacobian
entries that differ from serial in value or pattern (extra + missing + value).

| Configuration | neq | Jacobian arm (2/4/8 threads) | Jacobian + RHS arm (2/4/8 threads) | Linux x86-64, pre-fix (`amd64_base_k2_all`) | Linux x86-64, AIUE-56 fix (`amd64_fix_k2_all`) |
|---|---|---|---|---|---|
| `tebox` (owner's Te box) | 25 | FAIL at all three: Te rows only, repeats differ | FAIL at all three, but 5 of the 6 runs took a Newton step (table above). The one comparable run (2 threads) differs in Te rows of the Jacobian | FAIL both arms at 2/4/8, Te rows; jacrhs took a Newton step in 5/6 runs | PASS both arms at 2/4/8 |
| `full` | 44352 | FAIL at all three: Te rows only. 448,768–449,736 / 601,948–610,901 / 774,378–777,247 entries. Repeats differ | 2: both runs stop with the lusol0 overflow. 4 and 8: FAIL in Te rows only. 651,109–655,853 and 627,405–766,390 entries; `yldot` differs in 2198–2560 and 2158–2560 Te entries, plus 345 zeros of opposite sign | FAIL both arms at 2/4/8, Te rows; jacrhs ran at 2 threads (no overflow), `yldot` 1514–2582 Te entries | PASS, except jacrhs 8: 1/2 (M3, `up` rows) |
| `te` (Te alone) | 3168 | FAIL at all three: Te rows only, repeats differ | Every run crashes: SIGSEGV (exit −11), or a RuntimeError at 2 threads | jac FAIL (Te rows); jacrhs SIGSEGV in 6/6 | PASS both arms at 2/4/8 |
| `ti`, `ni`, `up`, `ng` (each alone) | 3168 / 25344 / 6336 / 3168 | **PASS** at all three | **PASS** at all three. `ni` and `ti` have 255 and 36 zeros of opposite sign in `yldot`, which P3-m2 allows | PASS, except `up` at 8 threads: 0/2 on both arms (M3) | PASS, except `up` at 8 threads: 0/2 on both arms (M3) |
| `te_phi` (Te + phi) | 6336 | FAIL at all three: only Te rows differ, phi rows agree | Every run crashes (SIGSEGV) | jac FAIL (Te rows only); jacrhs: 5/6 crash (SIGSEGV or RuntimeError) | PASS both arms at 2/4/8 |

### Pre-fix rates at 4 threads (K=20 fresh runs, PRD §11, P3-m4)

| Configuration / arm | Runs | Agree with serial | Distinct results | Iteration-0 `fnrm` | Stored nonzeros | Serial reference |
|---|---|---|---|---|---|---|
| `tebox` / jac | 20 | **0/20** | 20 of 20 (no two runs equal) | 20 distinct, 0.1357213635807744 – 0.1786270608456234 | 10 distinct, 176–187 | `fnrm` 0.3221264477609989, nnz 169 |
| `tebox` / jacrhs, no Newton step (run5, run14) | 2 | **0/2** | 2 of 2 | 0.1645118081253171, 0.1670300684916609 | 177, 181 | as above |
| `tebox` / jacrhs, Newton step taken | 18 | **0/18**, not comparable: the stored quantities are from iteration 1 | 18 of 18 | 18 distinct, 4.9e30 – 1.005e31 | not iteration 0: 304 (15 runs) or 169 (3 runs), row-normalised | as above |
| `full` / jac | 20 | **0/20** | 20 of 20 | 16 distinct, 1.535419111648367 (5 runs) – 1.537122945485376 | 20 distinct, 3,632,025 – 3,677,607 | `fnrm` 1.918820629111277, nnz 3,190,290 |
| **Linux x86-64** `tebox` / jac | 20 | **0/20** | 18 of 20 | 15 distinct, 0.1322747614580312 – 0.181059468674829 | 7 distinct, 175–182 | `fnrm` 0.3221264488412611, nnz 169 |
| **Linux x86-64** `tebox` / jacrhs | 20 | **0/20** (13 took a Newton step) | 17 of 20 | 7 comparable runs: 0.156194351810621 – 0.1803218335027441 | 7 runs 176–181; 13 runs 304 | as above |
| **Linux x86-64** `full` / jac | 20 | **0/20** | 20 of 20 | **1 value in all 20**: 1.535419111984408 | 20 distinct, 3,686,595 – 3,695,034 | `fnrm` 1.918820629909679, nnz 3,185,635 |
| **Linux x86-64, AIUE-56 fix** `tebox` jac / jacrhs, `full` jac | 20 each | **20/20 each** | 1 | equal to serial | equal to serial | as the two rows above |

- **The §11 pre-fix requirements hold.** The full problem disagrees with serial in 20/20 runs. The Te box disagrees
  in 20/20 runs on each arm, and no two of its runs are equal.
- **The full Jacobian is never stable.** Every run differs from every other in pattern and values. In each run:
  - the Te rows of `sfscal` differ in 2937–2940 places, and no other rows;
  - `yldot` is equal to serial (20/20);
  - max |J| is 5.98e43, against 1.7e14 in serial.
- **The full pattern is not a superset of serial's.** Each run has 443,011–487,854 extra entries and lacks 225–1736
  of serial's entries, all in Te rows. By column equation, the extra entries are ni 53–54 %, up 17–18 %, ng 9 %,
  te 7–8 %, ti 6 %, phi 6–7 %, the same in every run. This is a different count from the matrix's "entries"
  (602,423–665,917 at 4 threads in K=20), which also counts value differences.
- **The Te-box pattern (jac arm) is a superset of serial's.** Each run has 7–18 extra entries and 0 missing.
- **RHS arm, comparable runs only.** In run5 and run14, `yldot` equals serial in both. The RHS probe equals
  serial in run5 only; in run14 all 25 entries differ. The 18 runs that took a Newton step all differ in `yldot`
  (8–25 Te entries), but that `yldot` belongs to a different iterate.

### PRD §6.3, row by row

| §6.3 observation | Status | Evidence |
|---|---|---|
| Te box, 4 threads: `fnrm` differed in 10/10 runs (0.146–0.185; serial 0.322) | **Confirmed, range corrected**: 20/20 runs differ (K=20). The range is 0.1357–0.1786; 0.1357–0.1930 over all 25 one-evaluation 4-thread jac runs | `k20_tebox`, `ctl_base_t4_k3` |
| …the sparsity pattern differed every run | **Confirmed**: 10 distinct nnz in 20 runs, and a superset of serial in every run | `k20_tebox` |
| …`sfscal` differed in 4–19 of 25 rows | **Corrected**: 17–20 rows (K=20), 17–21 over all 25 4-thread jac runs; 14–15 at 2 threads and 21 at 8 (K=2) | `k20_tebox`, `ctl_base_t4_k3`, `k2_all` |
| …`yldot` bitwise identical | **Confirmed** on the jac arm, in 20/20 runs | `k20_tebox` |
| …Te diagonal entries reached ≈ −2.6e43 | **Confirmed**: max \|J\| is 2.22e43–2.60e43 per run, against 5.6e5 in serial | `k20_tebox` |
| …off-diagonal entries equal another column's diagonal exactly | **Not re-measured** here. AIUE-50 §C1 explains it (stale column) | — |
| …both builds behaved the same (April 2026 beta) | **Not re-measured.** That build was not rebuilt, and the epic's acceptance is on `v9-develop` | — |
| Te box, serial, repeated: bitwise identical | **Confirmed**: 3/3 serial repeats agree with the serial reference | `r54_new/tebox_serial_k3` |
| Te box, OpenMP with 1 thread: equal to serial | **Confirmed**: 3/3 on the jac arm, and **extended**: 3/3 on the jacrhs arm | `r54_new/tebox_jac_t1_k3`, `tebox_jacrhs_t1_k3` |
| Te box, 4 threads, `OMPJacNchunks=-1`, `OMPAutoBalance=0`: still non-deterministic, 3 distinct `fnrm` in 4 runs | **Confirmed**: 0/4 agree, 3 distinct `fnrm` in 4 runs (0.2612 × 2, 0.0456, 0.0877). `OMPJacNchunks=-1` alone: 0/4 agree, 2 distinct (0.2612 × 3, 0.1606). The M2 investigation measured the same settings on the C1-swap build (`scratchpad/m2/tebox_static.txt`). That is **after** the C1 fix (2 Te entries off, `fnrm` equal) and is not a pre-fix result | `r54_new/tebox_jac_t4_static_k4`, `tebox_jac_t4_nchunks_k4` |
| Te box, 4 threads, individual physics off (H radiation, Joule, E×B, grad-B, flux limit) | **Not re-measured.** The harness has no switch for deck physics, and AIUE-50 found the cause (C1) in the Jacobian loop, independent of these terms | — |
| Te only, whole grid, 4 threads: non-deterministic in 3/3 runs, different pattern each time | **Confirmed**: 0/5 agree (K=2 plus 3 controls). Every run has its own result, with the mismatch in Te rows only | `k2_all`, `ctl_base_t4_k3/te` |
| Ti / ni / up / ng only, 4 threads: bitwise equal to serial, 3 runs each | **Confirmed and extended**: 48/48 K=2 runs agree, on both arms and at 2/4/8 threads, plus 12/12 controls (3 per configuration, 4 threads, jac arm) | `k2_all`, `ctl_base_t4_k3` |
| phi only: not a valid isolation (serial aborts, "Jacobian row = 0 for eqn iv = 84") | **Not re-measured for phi alone.** iv 84 rests on the planning note only. Confirmed for the other phi isolations, each in serial: phi+ni+up (iv 924), phi+ni+up+ti (iv 1008), and the full problem without Te (iv 1092). All these iv map to phi(ix=11, iy=1), with nx+2 = 72 and numvar = 11/12/13 (and 1 for iv 84) | `scratchpad/phi/*/out.log`; `AIUE-52/{probe_phi_niup_serial, phi_all/phi/serial, acc_all_k2/full_note/serial}/run.log` |
| Full problem, 4 and 8 threads: the same `fnrm` in 7/7 runs (1.53541911164836…) | **Corrected**: 16 distinct values in 20 runs at 4 threads. The most common is 1.535419111648367 (5 runs); the range runs to 1.537122945485376 | `k20_full` |
| …2940 of the 3168 Te rows of `sfscal` differ | **Confirmed**: 2937–2940 per run, all of them Te rows | `k20_full` |
| …the run-to-run stability of the full Jacobian was not checked | **Answered**: it is never stable (20 distinct results in 20 runs) | `k20_full` |
| Full problem, jacrhs, 4 threads: `yldot` differs in about 2200 Te rows | **Confirmed, in the runs without the blow-up**: 2198–2560 Te entries (4 and 8 threads), plus 345 opposite-sign zeros. 4/10 runs at 4 threads instead blow up and overflow (table above) | `k2_all`, `k2_extra` |
| …`fnrm` varied in the 15th digit | **Confirmed, in the same runs**: 1.535419111648416–…441. These also differ from every jac-arm value | `k2_all`, `k2_extra` |
| Run time ≈ 2 s (Te box) and 12 s (full problem) at 4 threads, iteration 0 | See the timing below. The Te box is 1.4–4.6 s at load 10–40. The full problem took 17–20 s at the lowest load measured, and 54–158 s under load | — |

### Answers to the PRD's open questions

- **Ion energy (Ti): clean.** Alone, it agrees on both arms at 2/4/8 threads. That rests on 12 K=2 runs plus 3
  controls at 4 threads. In the coupled full problem, the 20/20 K=20 runs and the 6 jac and 4 jacrhs K=2 runs that
  completed (one evaluation each) have mismatches only in Te rows: no Ti row differs in value, pattern, `sfscal` or `yldot`.
- **Potential (phi): no phi-row mismatch was observed, but phi can't be judged independently.**
  - Phi can't be isolated without Te, because every phi isolation that was run stops in **serial** (row above).
  - With Te on (`te_phi`), the jac arm differs from serial only in Te rows: phi rows agree in 6/6 runs (K=2) and in
    3/3 controls.
  - The jacrhs arm segfaults in `te_phi` in 6/6 runs, so it gives no verdict on phi.
- **The RHS arm is worse than the Jacobian arm.** It crashes (SIGSEGV) whenever Te is on without the other plasma
  equations. Its iteration-0 `fnrm` blows up to 4.9e30–1.0e31 in 18/20 Te-box runs at 4 threads. On the full problem,
  that blow-up overflows the linear solver in 10/10 runs at 2 threads and 4/10 at 4 threads.

### Timing (for the CI budget, AIUE-57)

These are wall times from the committed records (`elapsed_s`, one process) and the flow summaries, on this
14-core M-series machine. The machine was shared with other sessions at all times, so the load is stated per row.
No measurement here is on an idle machine, and **none is on a 4-vCPU Linux runner**.

| Run | Build | Load (1-min average) | Wall time |
|---|---|---|---|
| Te box, one evaluation, serial or 1–8 threads | base | 10–40 (K=2, K=20); 24–113 (`r54_new`) | 1.4–4.6 s per run (K=2, K=20, `r54_new`); up to 5.9 s for a jacrhs run that takes a Newton step |
| Te box, one evaluation, 4 threads | base | 60–180 | 11–13 s per run (controls) |
| Te box, `--itermx 3`, serial / 2 threads / 4 threads | base | ~30 | 1.7 / 1.7–2.6 / 2.9–3.2 s per run (`r54_new`) |
| Te box, `--itermx 3`, serial / 4 threads | AIUE-56 fix | 60–180 | 11.1 / 9.9–13.0 s per run (`v56/new_tebox_t4_it3_k5`) |
| Full problem, one evaluation, serial | base | 10–40 | 56.4 s (`k2_all`), 51.5 s (`quick`) |
| Full problem, one evaluation, serial | base | ~40, and 60–180 | 317.9 s (`k20_full`), 297.8 s (controls) |
| Full problem, one evaluation, 2 / 4 / 8 threads | base | 10–40 | 33.6–34.4 / 18.2–19.9 / 7.0–7.1 s (`k2_all`, jac); jacrhs 4 and 8 threads: 17.2–17.4 / 10.4–10.9 s |
| Full problem, one evaluation, 4 threads | base | ~40 (K=20, 2 jobs on 8 cores), and 60–180 | 54.5–157.5 s (`k20_full`), 99.0–110.7 s (controls) |
| Full problem, `--itermx 3`, serial / 2 threads / 4 threads, one run each, two checks side by side | base | 24–113 | 212.4–213.7 / 237.7 / 128.6 s (`r54_new/full_jac_t*_it3_k1`). After 3 iterations the mismatch is in every equation's rows, not only Te: the iterate has moved |
| Full problem, `--itermx 3`, serial / 4 threads | AIUE-56 fix | 60–180 | 953.6 / 114.6–493.0 s (`v56/new_full_t4_it3_k5`) |
| Full problem, `--itermx 3`, serial / 4 threads (AIUE-57 validation §5) | not stated there | 15–25 | 99.3 / 46.3 s; serial one evaluation in the same session 38.2 s |
| `flow` quick set (Te box + full, 2 and 4 threads, both arms, K=2) | base | ~40 | 127.2 s total (`quick`) |
| same | base | not recorded (reviewer session, heavy) | 632.5 s (`r1/quick`), 1259.3 s (`rev52/quick`) |
| `flow --all` (K=2, 104 runs) | base | 10–40 | 367.6 s total (276.5 s runs, 91 s comparison) |
| `flow --configs tebox --threads 4 --repeats 20`, both arms | base | ~40 | 75.0 s total |
| `flow --configs full --threads 4 --repeats 20`, `--cores 8 --max-jobs 2` | base | ~40 | 1755.0 s total (1292.1 s runs) |
| OpenMP build (`pip install -v .`), from log creation to its last write | base and branches | outside / inside 02:18–03:37, when AIUE-57 reports load 60–180 | 110–317 s (8 builds) / 565–1164 s (5 builds) (`uedge-wt/logs/*omp*build*.log`, `*nofma*`, `*tsan*`; local Homebrew toolchain) |

What the CI budget can take from this:
- **Ratios, not absolute times.** Measured in the same session at low load, `--itermx 3` costs about 2.6× a single
  evaluation for the full serial reference (AIUE-57, 99.3 s against 38.2 s). In this revision's runs (load ~30) it costs
  ~1.1× for the Te box serial and ~2× at 4 threads (2.9–3.2 s against 1.5–1.8 s for one evaluation at 4 threads, the
  latter measured with `OMPJacNchunks=-1`, not the default chunking).
- **4 threads against serial.** At 4 threads, a full-problem evaluation takes about a third of the serial time
  (18–20 s against 56 s).
- **Load matters more than anything else.** At load ≥ 60, the same run takes 5–8× its time at load 10–40 (full serial 56 s → 298–318 s, full 4 threads 18–20 s → 99–111 s, Te box 1.5 s → 11–13 s).

What is missing for a 4-vCPU Linux budget: any measurement on Linux or on 4 cores; a CI build time; and a
comparison time for `--itermx 3` records. The CI job's own "Wall time" step (AIUE-57) is the first source for all
three. Until it has run, the AIUE-57 estimate (~14–21 min) stays an estimate.

## Shared-state scan (AIUE-50)

### Summary

The gross corruption (Te diagonals around −2.6e43, a sparsity pattern that changes from run to run, M1) has one
cause, found and confirmed on a scratch build.

**Candidate root cause C1: the OmpCopy order in `OMPJacBuilder` leaves the worker threads' impurity-emissivity
spline tables mostly zero on the first OpenMP Jacobian.** `OMPJacBuilder` copies threadprivate arrays
(`OmpCopyPointer<pkg>`, `ppp/omp_parallel.F90:681-686`) before threadprivate scalars (`OmpCopyScalar<pkg>`,
`ppp/omp_parallel.F90:688-693`). Each generated `OmpCopyPointer<var>` sizes the section it writes on a worker
with that worker's own copy of the bounds. For the twelve `Imslwrk` arrays in `api` those bounds are themselves
threadprivate scalars: `nxdata_api`, `nydata_api`, `nzdata`, `nwork2`, `nwork3` with DATA default `/1/`
(`api/api.v:145-147,155,157`), and `kxords_api`, `kyords_api`, `kzords` with default `/4/` (`api/api.v:161-165`).
`splinem` (`api/apip93.m:101-107`, called from `ueinit` at `bbb/odesetup.m:1130,1150` after `readpost`) sets the
first five on the master thread only. So on the first Jacobian each worker copies just element 1 of `xdata_api`,
`ydata_api`, `zdata`, `fdata_api`, `work2`, `work3`, `emcoef`, `z1coef`, `z2coef`, and elements 1:5 of the knot
vectors (bounds `n+k` = 1+4), and keeps zeros everywhere else. `emissbs` (`api/apip93.m:189-225`) then clips its
arguments to the zeroed data range. `B3VAL` fails its range test and returns 0, so `emissbs = 10**0 = 1.0` exactly,
against a true value of about 1.9e-35 at te(4,20). That is the `isimpon=7` fixed-fraction radiation term
(`bbb/pandf_plasma_energy.m:819-824`), which enters only the electron-energy residual (`cnimp*pwrze`,
`bbb/pandf_plasma_energy.m:1117`). So the corruption is limited to Te rows and to columns computed on worker
threads, and it vanishes with 1 thread or `afracs=0`. Only after the first copy do the workers hold the right
scalars, so later Jacobians in the same process are clean.

**C1 also corrupts the parallel RHS (`OMPParallelPandf1=1`), and through it the solution.** `OMPPandf1Rhs`
(`ppp/omp_parallel.F90:900-997`) calls no `OmpCopy*` routine, so its workers run on whatever threadprivate state the
last `OMPJacBuilder` copy left. Between the first and the second Jacobian the workers have the right `Imslwrk`
bounds but tables that are still mostly zero. (`emcoef` is the exception: `copyin` points it at the master's
array.) So every parallel-RHS evaluation in that window gets `emissbs = 1` on the worker chunks. Reviewer's
evidence (harness `--arm jacrhs`, Te box, 4 threads, unmodified build): `yldot` is wrong in all 25 Te rows and
`sfscal` in 18. The log shows `OMP iter= 0 fnrm= 0.87e31`. With `ftol=1e20` serial takes no Newton step, but this
run takes one, and `fnrm_final` differs (`0x1.9c7df3d50ba02p-3` against serial `0x1.49db83f93d961p-2`). With
`OMPParallelPandf1=1` the defect therefore changes the result, not only the preconditioner. The swap build matches
serial on this arm, apart from the M2 entries. **AIUE-56 must validate the `jacrhs` arm as well as `jac`.**

Fixing the copy order on a scratch build makes the Te-box OpenMP Jacobian match serial in sparsity and `fnrm`, bitwise,
in 3 of 3 runs, and the full-problem Jacobian bitwise equal to serial in 1 of 2 of my runs. The remaining
differences are round-off-level entries in Te rows (mechanism M2, below). They are a separate, much smaller effect.
On the full problem their count varies widely from run to run: 0 and 472 entries (7 rows) in my two runs, 860-1037
per run in the main session's harness, and 1217 entries in 26 Te rows in the reviewer's run. All are at noise level
(|Δ|·sfscal ≤ 4.6e-9), with `fnrm` and `yldot` equal. 472 is not a bound.

No other shared-state defect that could produce M1 was found. Secondary findings: one real race on physics state
in the plate boundary conditions (`areapl`, F16; full problem only, not seen to change results), benign races on
timers, flags and `nfsp` (F5-F7), and SAVE arrays in `api/fmombal.m` (F9-F10).

### Method

| Check | Tool | What it covers |
|---|---|---|
| OmpCopy coverage, static | `tests/deterministic_omp/tools/scan_ompcopy.py` | Every `+threadprivate` variable in every `.v`. Does the generated `<pkg>_p.F90` have the `!$omp threadprivate` directive? Is the variable copied by `OmpCopyPointer<var>`/`OmpCopyScalar<pkg>`, is that package's copy called by `OMPJacBuilder`, which size guard can skip the copy, is it in `copyin`, and does the copied section depend on threadprivate scalars that are copied later (copy-order hazard)? |
| OmpCopy coverage, dynamic | `scan_ompcopy.py --emit-checker` + scratch build | Generated `OMPCheckThreadprivateCopy(tag)`: compares every worker's copy of all 547 threadprivate variables (bbb 522, api 25), bit for bit, with the master's copy, right after the copy and after the loop. |
| Shared state written by a local `pandf`, before/after | `tests/deterministic_omp/tools/scan_shared_state.py` | All 3480 non-threadprivate variables of bbb, com, api, aph, ppp, flx, grd, svr, wdf, ncl, of every type (real, integer, logical, character; scalars and arrays). Snapshots after `pandf(-1,-1)`, after the perturbed local `pandf(xc,yc)` and after the restoring one, for all 25 Te-box columns and 12 full-problem columns. Evaluated in Jacobian mode, `yl(neq+1)=1`. The first version used nksol mode (`-1`). After review, both the Te box (diff + sentinel) and the full-problem diff were re-run in Jacobian mode, giving the same findings except for the `PandfTiming` accumulators (F6). |
| Same, sentinel | `scan_shared_state.py --sentinel` | Catches value-preserving writes and set/reset toggles. Each variable is set to a sentinel (next float up, int+1, negated logical), one column is run, and any variable no longer holding the sentinel is reported. Each test runs in a forked child, so a crash marks only that variable. |
| Saved locals, DATA, COMMON | `tests/deterministic_omp/tools/scan_saved_locals.py` | 865 program units in `*/*.m`, `ppp/*.F90`, tracked `*.f`. Call graph from `pandf` (145 reachable units); SAVE, DATA, F90-initialised locals and COMMON variables, and whether the unit assigns them or passes them to a CALL. |
| Automatic arrays in `LocalJacBuilder` | Code reading (`ppp/parallel.F90:195-196,229-345`) | Is `wk`/`yl_check` read before it is written? |
| `ppp` module variables | Code reading (`ppp/omp_parallel.F90:645-760`, `ppp/parallel.F90`) + shared-state scan | Writes to `ppp` state inside the parallel loop. |
| ThreadSanitizer | Scratch build with `-fsanitize=thread` | See "ThreadSanitizer" below. |
| TLS sanity | `nm`/`dyld_info` on the installed extensions | gfortran on Darwin uses emulated TLS. `__emutls_get_address` is defined in `bbbpy`, `apipy` and `ppppy`, but every call goes through a flat-namespace GOT bind, so a single emutls runtime serves all packages. The per-package TLS split hypothesis is ruled out. |

### Findings

| # | Variable | file:line | Kind | Written where | Threadprivate | Copied | Verdict |
|---|---|---|---|---|---|---|---|
| F1 | `xdata_api`, `ydata_api`, `zdata`, `fdata_api`, `work2`, `work3`, `xknots_api`, `yknots_api`, `zknots`, `emcoef`, `z1coef`, `z2coef` (`Imslwrk`) | `api/api.v:148-151,156,158,167-172` | dynamic real arrays, bounds = threadprivate scalars | filled by `splinem1` after `gallot("Imslwrk")` on the master (`api/apip93.m:108-185`); `work2` written by `B3VAL` in `emissbs` inside `pandf` | yes | **partially**: only element 1 on the first Jacobian, because `OmpCopyPointerapi` (`ppp/omp_parallel.F90:685`) runs before `OmpCopyScalarapi` (`:692`) and sizes the section with the worker's `nxdata_api` etc. (still `/1/`); `emcoef` is also in `copyin` (`:715`), so in the loop the workers' `emcoef` points at the master's array | **Candidate root cause C1 of M1** (evidence E1-E4) |
| F2 | `nxdata_api`, `nydata_api`, `nzdata`, `nwork2`, `nwork3`, `kxords_api`, `kyords_api`, `kzords`, `ldf_api`, `mdf` | `api/api.v:145-147,152-153,155,157,161-165` | integer scalars, DATA `/1/` or `/4/` | `splinem`/`splinem1` on the master (`api/apip93.m:101-106,142-143`) | yes | yes, but after the arrays that depend on them (see F1); workers hold the DATA defaults until the first `OmpCopyScalarapi` | Part of C1 |
| F3 | `icont`, `iflagi`, `iworki` | `api/api.v:154,159-160` | int scalars / fixed int array | `emissbs` sets `icont=0` (`api/apip93.m:215`); `B3VAL` writes `iflagi`, `iworki` | yes | yes | Correct (per-thread work state) |
| F4 | `impradloc(0)` | `bbb/bbb.v:3898` | element of a threadprivate work array | never written by `radimpmc` (`api/inelrates.m:397-414` loops `kk=1,nzarg`), but read into `pradzc(..,0,..)`/`pradc` (`bbb/pandf_plasma_energy.m:812-815`) | yes | yes | Stale/uninitialised read, but only for `ismctab=1` (this case uses `ismctab=2`/`radmc`), and `pradc`/`prad` are diagnostics, not the Te residual (`pwrze`). Not a cause; report to the fix ticket |
| F5 | `TimingPandfOn` | `bbb/bbb.v:4136` | integer scalar | set and reset on every `pandf` call (`bbb/pandf.m:573-579`) | **no** | n/a | Data race between threads (sentinel: WRITTEN). It only gates timing, so it does not affect results. Should be threadprivate or not written in the Jacobian |
| F6 | `com.ttimpjf`, `ttnpg`, `ttngxlog`, `ttngylog`, `ttngfd2`, `ttngfxy`, `totintrv` (`Timing`, `TimeSpl`) | `com/com.v:503-567` | real scalars | accumulated in `pandf` (`bbb/pandf.m:760`), `neudifpg` (`bbb/pandf_gas_continuity.m`), `B1VAhL` (`com/comutil.m:3654`) (`istimingon=1` by default, `com/com.v:503`) | **no** | n/a | Benign data races on timers (lost updates only). The `PandfTiming` accumulators (`TimePandf`, `TotTimePandf`, `TimeConvert*`, `Timefd2tra`) were reported by the first scan only because it ran `pandf` in nksol mode (`yl(neq+1)=-1`). In Jacobian mode (`yl(neq+1)=1`, the default of the fixed scan) `TimingPandfOn=0` and they are not written, which agrees with TSan. (`ttimpfe` is written only for `xc<0`, `bbb/pandf.m:751-761`: it showed up only through the scan's own reset `pandf(-1,-1)` after each column, so it is not a race of the Jacobian loop) |
| F7 | `com.nfsp` | `com/com.v:28` (`Dim`) | integer scalar | `nfsp = nisp` / `= nhsp` on every `pandf` (`bbb/pandf.m:50-51`) | **no** | n/a | Race, but every thread writes the same value (it depends only on `isimpon`, `nisp`, `nhsp`). Benign |
| F16 | `areapl` (`Rccoef`) | `bbb/bbb.v:951` | real scalar, `+work` | written and immediately read in the plate recycling/albedo boundary conditions, `left_boundary`/`right_boundary` (`bbb/pandf_boundary.m:3091,3166,3446,3544,3797,3882,4180,4277`) | **no** | n/a | **Real data race on physics state**, found by the full-problem diff scan (changed in every sampled column whose box touches a plate: 11 of 12). Two threads at plate cells can overwrite each other's value between the write and the read on the next line. Not observed to change results (the full-problem OpenMP Jacobian with C1 fixed differs from serial only in Te rows, and is bitwise equal in 1 of 2 runs), probably because the compiler keeps the value in a register. Still, it must become a local or `+threadprivate` (fix ticket). Not involved in the Te box |
| F8 | all other non-threadprivate variables (3480 scanned), every type | all `.v` | — | not written by a local `pandf` (diff on 25 Te-box + 12 full-problem columns; sentinel on one Te-box column only, since the full-problem sentinel run did not finish within the time box) | no | n/a | Clean. With F5-F7 and F16 this closes H2 for scalars and integer arrays on the sampled columns |
| F9 | `uresp`, `usave`, `caplams` | `api/fmombal.m:70` | SAVE local arrays | passed to `zrespond`/`mrespond`/`mzrespond`, which write them (`api/fmombal.m:223-238`) | no | n/a | **Race when `fmombal` runs on several threads** (called from `mombal`, which runs only for `isimpon=5`, `bbb/pandf_plasma_momentum.m:669-671,701-703`, `:1018`; `isimpon` 6/7 call `mombalni` instead). Not exercised by this deck (`isimpon` 6/7); a hazard for `isimpon=5` (AIUE-60), not for M1 or M2 |
| F10 | `nrow`, `bmat`, `sbar0`, `ubar0` (`mrespond`); `zmat`, `source`, `scaz`, `lsz`, `msz`, `nrowz` (`zrespond`) | `api/fmombal.m:368`, `api/fmombal.m:1064` | SAVE locals | passed to CALLs in the same routines (`:466-480`, `:1199-1213`) | no | n/a | Same as F9 (H3 confirmed as a hazard, not as the M1 cause) |
| F11 | `lunit`, `mesflg` (`parmsetget`), `args` (`ijmgetmr`), COMMON `/iotable/` (`freeus`) | `com/error.f:144`, `com/getmsg.f:11`, `com/dummy_py.f:66` | SAVE/DATA/COMMON | error-message and interrupt paths (`xermshg`, `check_kaboom`) | no | n/a | Only on error or interrupt paths. Benign for the Jacobian |
| F12 | DATA tables in `rcxr_zn6`, `rcxr_zn6b` (`api/fimp.m:219-252`), `yhaasz*` (`api/sputt.m:501-765`), F90 initialisers in `run_uedge`/`run_degas2` (`bbb/ext_neutrals.m:118-162`, duplicated in `bbb/s.m`) | as listed | DATA/initialised locals | never assigned | no | n/a | Read-only constants. Safe |
| F13 | `wk(neq)`, `yl_check(neq)` (`LocalJacBuilder`) | `ppp/parallel.F90:195-196` | automatic arrays (per call, per thread) | `wk(ii1:ii2)=yldot00` before every `pandf` (`:237-239`); `pandf` rescales `yldot(iv)` in place (`bbb/pandf.m:436-504`) over its own loop range; `yl_check(1:neq)=wk(1:neq)` (`:321`) | n/a (stack) | n/a | No read-before-write reaches the Jacobian: `jacelem` and the `isjacreset` check read only `ii1:ii2`, which is always initialised. Entries outside `ii1:ii2` may hold garbage but are never used. On the Te box `ii1:ii2` covers all 25 equations. Ruled out (H6 part 2) |
| F14 | `ppp` module state written in the loop: `iJacCol(:,ichunk)`, `rJacElem(:,ichunk)`, `iJacRow(ivmin:ivmax)`, `OMPTimeJacRow(ivmin:ivmax)`, `nnz(ichunk)`, `OMPTimeLocalJac(tid+1)` | `ppp/omp_parallel.F90:728-735` | shared arrays | inside `!$omp parallel do`, indexed by `ichunk`/`tid` | no | n/a | Disjoint per chunk/thread. No race. `ppp` has no threadprivate variables (`ppp/ppp.v`); `OmpCopyppp` is empty. Clean |
| F15 | `yinc`, `xlinc`, `xrinc` (`Selec`), `emcoef` | `ppp/omp_parallel.F90:715` | threadprivate | `copyin` | yes | yes (twice: OmpCopy and copyin) | Correct for the `Selec` scalars. **`emcoef` is a Forthon pointer**, so `copyin` pointer-assigns each worker's `emcoef` to the master's target, and the association persists after the loop. From the second Jacobian on, every worker's `OmpCopyPointeremcoef` writes `emcoef(1:n)` into the master's array at the same time: a formal data race, harmless because the values are identical, and the workers' own copies are leaked. AIUE-56 should decide whether `emcoef` stays in `copyin`; see also fix direction 3. My TSan run covered only one Jacobian, so it could not see this |

The full coverage table, with one row per threadprivate variable (547 rows), is regenerated with
`scan_ompcopy.py --md`. Its summary for `0fac655` is: bbb 522 threadprivate, 522 copied; api 25 threadprivate, 25
copied; no threadprivate variable lacks the directive or a copy routine; 442 copies (bbb 430 of 433, api 12 of 13)
are behind a `size >= declared` guard, while the 4 fixed-size arrays (`cftgtipltl`, `cftgtipltr`, `psordisold`,
`iworki`) have none, and none of those guards fails for this case (the checker found 0 mismatches outside
`Imslwrk`); **12 copy-order hazards, all in `api` `Imslwrk`** (F1).

### Candidate root cause C1: evidence

**E1. Worker state after the copy, unmodified code.** Scratch build `0fac655` + generated checker (no other
change). Te box, 4 threads. `TPCHK after-copy`: 36 mismatching (variable, thread) pairs, i.e. exactly the 12
`Imslwrk` arrays × 3 workers, and nothing else among the 547 variables. Every one shows the same pattern: element 1
correct, the rest 0:

```
TPCHK after-copy api.xdata_api tid=  1 nbad=   40 of    41 first=  2 worker= 0 master= C032FF0E5F804024
TPCHK after-copy api.xknots_api tid= 1 nbad=   40 of    45 first=  6 worker= 0 master= C032CBDB30DB0347
TPCHK after-copy api.emcoef tid=     1 nbad= 25255 of 25256 first=  2 worker= 0 master= C04926B02D96F303
TPCHK after-copy api.work3 tid=      1 nbad= 25412 of 25592 first=  2 worker= 0 master= 3BB657BAF3E546E8
TPCHK after-copy done:     36 mismatching (variable,thread) pairs over   547 variables
```

The generated copy that does it (`build/temp.*/api_p.F90`, Forthon `--omp`):

```fortran
subroutine OmpCopyPointerxdata_api
  use Imslwrk
  real(kind=8)::xdata_apicopy(1:nxdata_api)          ! master: nxdata_api = 41
if ((nxdata_api-1+1).le.size(xdata_api)) then
xdata_apicopy(1:nxdata_api)=xdata_api(1:nxdata_api)
!$omp parallel private(tid) firstprivate(xdata_apicopy)
tid=omp_get_thread_num()
if (tid.gt.0) then
xdata_api(1:nxdata_api)=xdata_apicopy(1:nxdata_api)  ! worker: its own nxdata_api, still the DATA default 1
```

**E2. Only the first Jacobian of a process is wrong.** Unmodified `base-omp` build. Te box, two `exmain()` calls
(ftol=1e20) in one process, 4 threads, 3 fresh runs. First Jacobian: max|jac| 2.37e43, 2.60e43, 2.60e43; nnz 186,
177, 178 (serial 169). Second Jacobian: max|jac| 5.564e5 in all runs (serial 5.564e5), nnz 169, and `fnrm`
bitwise equal to the serial second call (`0x1.49db83f99a136p-2`). By then the first `OmpCopyScalarapi` has given
the workers the right `nxdata_api` etc.

**E3. Copy order swapped (scalars first), scratch build.** The only change from `0fac655` is moving the
`OmpCopyScalar*` block before the `OmpCopyPointer*` block in `OMPJacBuilder` (patch below), plus the checker.
Te box, 4 threads, 3 fresh runs:

| | serial (same build) | OMP run 1 | run 2 | run 3 |
|---|---|---|---|---|
| `TPCHK after-copy` mismatches | — | 0 | 0 | 0 |
| nnz | 169 | 169 | 169 | 169 |
| `fnrm` | `0x1.49db83f93d961p-2` | same | same | same |
| `jaci`/`jacj` SHA-256 | `995b8308…`/`47a3c6d7…` | same | same | same |
| differing `jac` values | — | 1 (row 12) | 2 (row 12) | 1 (row 12) |

Unmodified `base-omp`, same configuration: fnrm 0.1742/0.1622/0.1441 (AIUE-46), nnz 177-191, max|jac| ≈ 2.6e43.

Full problem (neq 44352, 4 threads, ftol=1e20), same scratch build: run 1 is **bitwise equal** to serial (nnz
3 190 290, all values and `fnrm` `0x1.eb37d428ec4f0p+0`). Run 2 has `fnrm` bitwise equal and 472 differing entries,
all in 7 Te rows: 416 serial entries of magnitude ≤ 7e-5 missing, 3 extra, and 53 values differing (median relative
difference 5e-5). Max|jac| matches serial (1.70e14). Unmodified `base-omp`: 663 257 differing entries, all in Te
rows, nnz 3 675 793, max|jac| 5.98e43.

Patch used (scratch only, not committed as product code):

```diff
--- a/ppp/omp_parallel.F90  (OMPJacBuilder)
-    if (OMPCopyArray.gt.0) then
-        call OmpCopyPointerbbb; call OmpCopyPointercom; call OmpCopyPointerapi
-    endif
-    if (OMPCopyScalar.gt.0) then
-        call OmpCopyScalarbbb; call OmpCopyScalarcom; call OmpCopyScalarapi
-    endif
+    if (OMPCopyScalar.gt.0) then
+        call OmpCopyScalarbbb; call OmpCopyScalarcom; call OmpCopyScalarapi
+    endif
+    if (OMPCopyArray.gt.0) then
+        call OmpCopyPointerbbb; call OmpCopyPointercom; call OmpCopyPointerapi
+    endif
```

**E4. Consistency with the known symptoms.**

* *Te rows only.* `emissbs` is used only in `pwrzec`/`pwrze` → `resee` (`bbb/pandf_plasma_energy.m:775,822,1117`).
* *1 thread bitwise equal.* There are no workers, so nothing is copied.
* *Thread-count dependent; master columns are correct.* Rows 3, 7, 11, 14, 18 and 22 are bitwise correct in the
  unmodified run. That is consistent with those columns running on thread 0 (the column-to-thread mapping was not
  recorded).
* *Off-diagonal entries equal another column's diagonal.* Every column whose stencil contains cell r recomputes
  `emissbs` at r with the same zeroed tables. That gives the same wrong `wk(r)` divided by an almost equal `dyl`
  (the values agree to the last 1-2 ulp).
* *Run-to-run variation.* On a worker, `emissbs` clips its arguments into the zeroed data range. `B3VAL` then fails
  its range test and returns 0, so `emissbs = 1.0` exactly (reviewer's emulation: 1.90e-35 → 1.0 at te(4,20),
  2.77e-34 → 1.0 at te(5,20)). The wrong value is deterministic per cell. The variation comes only from which
  columns `schedule(dynamic)` puts on worker threads.
* *`afracs=0` cures it* (main-session experiment). `pradcff = na*ne*emissbs` with `na=afrac*ne=0`.
* *Full problem: stable `fnrm`, unstable Jacobian.* The iteration-0 `fnrm` comes from the master's RHS.

Suggested fix directions for AIUE-56 (not implemented here):

1. In `OMPJacBuilder`, call `OmpCopyScalar*` before `OmpCopyPointer*`. It is the smallest change; it also covers
   any future array whose bounds are threadprivate scalars.
2. Or make the generated `OmpCopyPointer<var>` pass the master's bounds into the parallel region. This is a
   Forthon template change, so it needs upstream work.
3. Independently, consider making the `Imslwrk` tables (read-only after `splinem1`) non-threadprivate shared data,
   leaving only the B3VAL work arrays (`work2`, `iworki`, `icont`, `iflagi`) threadprivate.

`scan_ompcopy.py` flags the order hazard statically, so it can serve as a regression check. Validation for AIUE-56
must include the `jacrhs` arm (`OMPParallelPandf1=1`), not only `jac`, and one `--checkbounds` OpenMP Te-box run.

### Mechanism M2 (round-off-level, history dependent), not resolved here

After C1 is removed, the OpenMP Jacobian still differs from serial in a handful of Te-row entries of ulp size:
4.5e-5 ≈ ulp(yldot)/dyl. These are entries that the serial run stores because of round-off noise and the OpenMP run
computes as exact zero, or the reverse. (Two consecutive serial `exmain()` calls give different `fnrm`, but that is a
state change between the calls, not a history test; see AIUE-55, P3-m3, which locates the history inside the serial
column loop.) The shared-state scan rules out a shared non-threadprivate variable as the
carrier (F8). Candidates for AIUE-54/55: threadprivate work arrays that a local `pandf` reads outside its own
recomputed box. On a worker those hold the values of the worker's previous columns, not the master's full-RHS
values; the `after-loop` checker output lists them (for example `bbb.qfl`, `csh`, `qsh`, `mfl`, `msh`, `fxe`, `fxi`,
`zcoef` differ per thread after the loop). Another candidate is the SAVE arrays in `api/fmombal.m` (F9/F10) for the
full problem. Below `jaccliplim`, tiny differences turn into sparsity changes.

### ThreadSanitizer

Homebrew gfortran 15 ships no `libtsan` for Darwin, but objects built with `gfortran -fsanitize=thread` link and
run against LLVM's `libclang_rt.tsan_osx_dynamic.dylib`. A toy racy `!$omp parallel do` is reported correctly.
I ran a full scratch build with `-fsanitize=thread` added to `FARGS` (copy-order patch and checker included, so C1
is removed) on the Te box with 4 threads (`DYLD_INSERT_LIBRARIES=<llvm>/lib/clang/23/lib/darwin/libclang_rt.tsan_osx_dynamic.dylib`,
`TSAN_OPTIONS="log_path=... halt_on_error=0"`). `fnrm` matched serial. It produced 351 reports, grouped by
`tests/deterministic_omp/tools/tsan_summary.py`:

| Reports | In the Jacobian loop | Location | Verdict |
|---|---|---|---|
| 105, 17, 16, 16, 15, 15, 15 | yes | `Timing::ttimpjf`, `TimeSpl::totintrv` (`B1VAhL` via `emissbs`), `ttngxlog`, `ttngfd2`, `ttngylog`, `ttngfxy`, `ttnpg` | real races on timing accumulators (F6), harmless to results |
| 14 | yes | `PandfTiming::TimingPandfOn` (`bbb/pandf.m:573-579`) | real race (F5), harmless to results |
| 13 | yes | `Dim::nfsp` (`bbb/pandf.m:50-51`) | real race, same value written (F7) |
| 30 | yes (read) | heap block (numpy array) | false positive: written by the master in `gridseq` after the region, read in the loop (`convsr_aux2`); TSan does not see libomp's join |
| 95 | no | stack/heap in `bbbsetarraypointer*`, `OmpCopyScalar*`, `OmpCopyPointer*` | false positives: firstprivate/copyin buffers across parallel regions, synchronised by the uninstrumented libomp barrier |

So TSan finds no race on physics state inside the column loop once C1 is fixed. This is the same result as the
sentinel scan, from an independent method. TSan cannot detect C1 itself, because C1 is a missing copy, not a race.
The serial reference and the unpatched code were not run under TSan.

### Not covered

* Units reached only through procedure arguments or ENTRY points, and code reached only through Python callbacks,
  are not followed by `scan_saved_locals.py`. `com/*.f` and `ncl/*.f` are scanned; `svr` (nksol) runs outside the
  Jacobian column loop and was not included in the reachability roots.
* The full-problem **sentinel** run (`--cols 12 --sentinel`) was stopped after about 20 minutes. Forking the
  44352-equation process once per variable is too slow. For the full problem only the before/after diff on 12
  columns was done. Restricting the sentinel to a list of variables, or reusing one child per batch, would make
  it feasible.
* The sentinel test runs one column (Te box: column 13).
  A variable written only for other cells or boundary columns would be missed by the sentinel, but would still
  show in the diff test if its value changes.
* `OMPParallelPandf1=1` (parallel RHS) was not scanned for shared state of its own. It has its own chunking path,
  and it writes the shared `com.nfsp` in `OMPinitialize_ranges2D` (`ppp/omp_parallel.F90`). It is **not** unaffected
  by C1, though: it inherits the workers' state from the last Jacobian copy (see Summary).
* Follow-up for the sentinel on the full problem: run it on a restricted variable list, or with batched children,
  on a few plate-adjacent columns. The `areapl` race (F16) is the kind of value-preserving write the sentinel is
  meant to catch.
* Other platforms and runtimes (Linux/libgomp) were not tried. C1 does not depend on the platform.
* M2 is characterised only as far as above.

### How to reproduce

From the AIUE-50 worktree, with the case copied as in `tests/deterministic_omp/README.md`. Set
`UEDGE_OMP_RATES_DIR=<repo>/builder/test/Forthon_cases/Forthon_case5` whenever the case runs outside the repository
(the deck finds the rate files relative to itself). Also set `OMP_STACKSIZE=512M`, use an empty `HOME`, and run
`python -I`:

```bash
T=tests/deterministic_omp/tools
# static OmpCopy coverage (needs a built OpenMP tree with build/temp.*/<pkg>_p.F90)
python -I $T/scan_ompcopy.py --src <omp-built-tree> --md ompcopy.md --emit-checker tpcheck.F90
# saved locals / DATA / COMMON reachable from pandf
python -I $T/scan_saved_locals.py --md saved_locals.md
# shared state written during a local pandf (serial build), from a copy of the case
python -I $T/scan_shared_state.py --tebox --sentinel --src <worktree>
python -I $T/scan_shared_state.py --cols 12 --sentinel --src <worktree>
```

Dynamic checker (scratch tree only): append `tpcheck.F90` inside an `#ifdef _OPENMP` block at the end of
`ppp/omp_parallel.F90`, and add `if (OMPJacDebug.eq.-7) call OMPCheckThreadprivateCopy('after-copy')` after the
`OmpCopyScalar*` block in `OMPJacBuilder` (and `'after-loop'` after `!$omp END PARALLEL DO`). Build with
`build_uedge.sh <tree> <venv> omp`, then run the Te box with `ppp.OMPJacDebug=-7` and `grep -a TPCHK` the log.
For E3, also apply the copy-order patch above.
