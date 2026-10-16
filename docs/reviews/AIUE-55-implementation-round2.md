# AIUE-55 implementation review, round 2: Jacobian RCA and Phase 2 exit decision

Reviewed: `feature/v9-AIUE-55-omp-jacobian-rca` at `48e877c`, rebased onto `45a9aa1` (AIUE-54, reviewed) → `f516b40`
(AIUE-50). Diff `45a9aa1..HEAD`: `docs/rca/AIUE-8-omp-jacobian-nondeterminism.md` §"Jacobian RCA and Phase 2 exit
decision (AIUE-55)", `.claude/plans/AIUE-55-omp-jacobian-rca.md`, the round-1 review and the response. No product code,
skills, agents or hooks changed. Reference: PRD AIUE-8 §9, §11, binding decisions 4/7/8/9, and the round-1 report.

## Verdict

**REVISE**

## Summary

The blocker is resolved. The replay remedy was prototyped in the real `LocalJacBuilder` path. I checked the scratch
outputs and they support the bitwise claims: Te box 3/3 (I re-ran it at the current scratch head), full problem 3/3
with 16 contiguous chunks, and serial of the replay build equal to `base-serial` bitwise. C2 is now framed correctly,
and the per-configuration table states its gaps. Two decision-relevant problems remain. (1) The RCA still says the
static partition without replay is not deterministic. It cites a control run that in fact shows 3/3 identical runs.
The author's own full-problem data show the same, so the "static partition + tolerance" option (round-1 I1-M1(b)) is
still missing, and it may meet §11 as written. (2) The "+18 %" cost is a count of extra evaluations for a
configuration that was never run on the full problem (every attempt segfaulted). It is not labelled as an estimate,
it holds only at 4 threads (it grows linearly with the thread count), and the one measured cost (16 chunks) rests on
two runs per arm of whole-process wall time, whose repeat-to-repeat spread (~9 s) is about half the reported
difference (16–19 s). PRD §9 asks for a measurement.

## Findings

### BLOCKER

None.

### MAJOR

**I2-M1. The static partition without replay is reported as non-deterministic, against the data. The option of a
static partition with a tolerance is still not offered (I1-M1(b) not resolved).**
- *Location:* RCA §Residual after C1, row "Te box, one contiguous chunk per thread (`OMPJacNchunks=-1`,
  `OMPAutoBalance=0`) | 0–2 | … | yes" (line 33, unchanged since round 1). Option B row: "**not deterministic** (Te
  box contiguous chunks without replay: 2 mismatches in 2/3 runs in the replay controls)". Response to I1-M1: "The
  static partition alone is not deterministic in the replay controls … so it isn't offered on its own".
- *Evidence (scratch outputs, read with the reviewed harness `compare`):*
  - `replay/te_contig_R0/check.json` is the control cited (replay build `918bdb6`, R = 0, `OMPJacNchunks=-1`,
    `OMPAutoBalance=0`, 4 threads). All 3 runs have the **same 2 mismatches** against serial: te(4,20) × te(3,21),
    `380.24309105821885` vs `380.243045583…`. The determinism reports run0 vs run1 and run0 vs run2 are both
    **AGREE**. That is 2 mismatches in 3/3 runs, and the runs are bitwise identical to each other.
  - `m2/tebox_static.txt` (round 1, swap build) gives the same result: 2 mismatches in 3/3 runs, run0≡run1≡run2.
  - Full problem, static 16 chunks without replay (`replay/t_c1_n16_1`, `t_c1_n16_2`, AIUE-56 build,
    `OMPAutoBalance=0`, `OMPlenpfac=2`): `compare t_c1_n16_1 t_c1_n16_2` gives **AGREE**. Each run has the same
    5698 mismatches against `bs_full_serial`.
  - The non-determinism belongs to the **default dynamic one-column chunks**: `compare t_c1_dflt_1 t_c1_dflt_2` gives
    MISMATCH, 70 entries. So B (C1 build with the default chunks) is non-deterministic, but the evidence the RCA
    cites for it is wrong. The partition that the cited evidence describes is deterministic: 6/6 Te-box runs over
    two builds, and 2/2 full-problem runs.
- *Why it matters:* This is the mechanism the RCA itself states: a fixed column-to-thread mapping gives fixed worker
  start states. With the same crash fix that E needs, and no replay, a static partition plus the AIUE-56 tolerance
  meets §11 bullet 1 ("bitwise reproducibility across fresh sessions") on the evidence so far. It may also meet
  bullet 2. Its cost is the static schedule only, with no +18 % to +70 %. If the owner rejects E's cost, this is the
  natural alternative, and it is also a stronger interim CI gate than B. As written, the menu leaves it out on the
  strength of a misread control.
- *Acceptance:*
  1. Correct the line-33 row and the B-row evidence. B's non-determinism should cite the default-chunk data.
  2. Add "static contiguous partition + tolerance" as an option. Give its serial impact (none), the measured
     determinism (Te box 6/6, full problem 2/2 at 16 chunks; say if more runs are needed), its dependence on the
     `OMPJacNchunks≠0` crash fix, and whether its residual passes the AIUE-56 bounds. The 16-chunk residual (5698
     entries) is larger than the default-chunk one and has not been run through the gate script.
  3. State which §11 bullets it meets. If the author holds a run where the static partition did vary, cite it instead.

**I2-M2. The cost of option E is an unlabelled count estimate, for a configuration that was never run. It holds only
at 4 threads. The PRD §9 measurement was not made.**
- *Location:* the RCA status line ("at ≈ +18 % Jacobian cost"); §M2 item 5, "Cost"; option E row; the
  Recommendation; the response to I1-B1 ("Cost ≈ +18 % at one chunk per thread").
- *What is wrong:*
  1. **Not measured.** "+18 %" is `4·3920 ≈ 16k` extra local evaluations against `~89k`, which is arithmetic. The
     configuration it describes is the full problem with one contiguous chunk per thread and R = `ubw`. It was never
     run threaded: `full_try0`, `full_try0b`, `full_try1`, `full_c1only_contig`, `full_c4_lp1`, `full_contig_R2072`
     and `full_contig_R3920` all have `OMPJacNchunks=-1` and all exited with −11 and no record. It was not emulated
     at R = 3920 either: there is no `em_chunks4_r3920`. Only R = 2072 with 4 chunks gives 0 (`em_r2072`, "mul"
     compare). So the item-5 bullet "R = `ubw` … 0 for 4, 8 and 16 chunks" is also unsupported for 4 chunks.
     PRD §9 requires "OpenMP Jacobian and RHS times are **measured** before and after".
  2. **Thread scaling.** The slowest thread does 2·neq/T + `ubw` local evaluations instead of 2·neq/T, so the
     wall-clock overhead is about T·ubw/(2·neq) = 4.4 % × T on the full problem. That is +18 % at 4 threads, +35 %
     at 8 and +71 % at 16. The PRD scope includes 2 and 8 threads, but the text quotes only the 4-thread figure. The
     formula given (`4·3920` against the total 89k) is the total-work ratio. The wall-clock ratio 3920/22 176 happens
     to give the same 18 % at T = 4 only.
  3. **Baseline.** The overhead is taken relative to the same static chunking. The cost of leaving the default
     dynamic, auto-balanced schedule is not included or measured.
  4. **The 16-chunk "measured +16–19 s".** This rests on two whole-process `elapsed_s` values per arm (`t_c1_n16`
     44.76 / 35.56 s; `t_rp_n16` 60.88 / 53.94 s). The C1 arms themselves vary by about 9 s between repeats
     (`t_c1_dflt` 44.26 / 34.98 s), and the Jacobian time is not separated from setup. "≈ +70 % Jacobian work" is
     again an evaluation count, not a timing.
- *Acceptance:* Label the +18 % (and +70 %, ≈ 2000×) figures as evaluation-count estimates wherever they appear,
  including the status line. Give the T-dependence, or the 2- and 8-thread figures. State plainly that the PRD §9
  Jacobian-time measurement is still to be done, in AIUE-61, against the current default schedule and at the thread
  counts in scope. A threaded full-problem run of one chunk per thread is possible under `ulimit -s 65520` with a small
  `OMPlenpfac`, but it is not required here. Alternatively, measure it now and report the Jacobian timers
  (`OMPTotTimeLocal`).

### MINOR

**I2-m1. The crash finding is right in substance but overstated and mis-cited.** I read the code.
`OMPJacBuilder` declares `iJacColCopy(nnzmxperchunk)` and `rJacElemCopy(nnzmxperchunk)` as automatic arrays
(`ppp/omp_parallel.F90:672,675`) and makes them `firstprivate` (`:713-714`). `nnzmxperchunk =
ceiling(nnzmx/NchunksJac)·omplenpfac` (`:321`, the line the RCA cites, which is the sizing and not the allocation),
with `nnzmx = lenpfac·neq = 60·neq` (`bbb/odesetup.m:364`, `bbb/bbb.v:2994`). With `OMPJacNchunks=0`, NchunksJac = neq
and the arrays are tiny. With few chunks on the full problem they reach tens of MB, and the master's private copies
live on the main-thread stack. `OMP_STACKSIZE` does not size that stack, and the macOS default is 8 MB, so the
explanation is consistent with the `ulimit -s 65520` workaround. Three corrections: (a) "any `OMPJacNchunks≠0`
segfaults" is too broad, because the Te box with `OMPJacNchunks=-1` runs fine (`te_contig_R0`/`R25`), so the crash is
size-dependent; (b) cite `:672,675,713-714` as well as `:321`; (c) say that the stack attribution is inferred from the
workaround, since no backtrace was kept (`replay/lldb16` holds no log).

**I2-m2. The scope of "reachable" is not stated where it is claimed.** The status line and the E row say "bitwise
and deterministic where tested". Every replay run is a single Jacobian evaluation (`it0`, `itermx` null) with K = 3
at 4 threads. §11's MVP is the `fnrm` sequence over ≥ 3 Newton iterations, at 2/4/8 threads, 30/30 runs. Add "one
evaluation, K=3" to the table cells, and qualify the status line ("in the prototype, for the Te box and the full
problem at 4 threads"). Also, the Te-box threaded results in the RCA come from scratch head `918bdb6`, where the
worker loop still has the `isjacreset` block. Only the full-problem runs used `db6a8ea` ("mirrors serial
`jac_calc`"). I re-ran the Te box at `db6a8ea`: AGREE 3/3, deterministic, so the claim holds, but say which commit
produced which row. Note also that the replay loop itself still makes the extra `isjacreset` call (patch 1), which
serial does not (`bbb/oderhs.m:1220` is commented out). AIUE-61 should decide that deliberately.

## Status of previous findings

| Finding | Status | Evidence |
|---|---|---|
| I1-B1 OpenMP-only remedy not examined | **Resolved** | Replay prototyped in `LocalJacBuilder` (`patches/0001`, `0002`). Te box R=25: `te_contig_R25` and `te_dflt_R25` AGREE 3/3 and deterministic; reproduced by me at `db6a8ea`. Full problem, 16 chunks, R=3920: `full_n16_R3920.out` AGREE in all sections, 3/3, determinism AGREE. My cross-build `compare bs_full_serial t_rp_n16_1`: AGREE. Controls fail: `te_contig_R0` 2 mismatches; `t_c1_n16_*` 5698. Serial unchanged: `compare bs_te_serial rp_te_serial` and `bs_full_serial rp_full_serial` both AGREE (fnrm `0x1.49db83f93d961p-2`, `0x1.eb37d428ec4f0p+0`). Emulation counts (479 / 162 / 0 / 84 / 0 / 0) match `em_*/emul.json` ("mul"). C2 reframed and the exit question restated. The cost-measurement part of acceptance (1) carries over as I2-M2. |
| I1-M1 B labelled §11 fallback; static option missing | **Partially resolved** | (a) B is now "tolerance gate, interim CI only" and explicitly does not meet §11: resolved. B still states no multi-iteration `fnrm` criterion, and does not say it has none (minor remainder). (b) The static row is not corrected and the static option is not offered, on misread evidence: **not resolved**, see I2-M1. |
| I1-M2 decision not per configuration | **Resolved** | A configuration × arm × threads table with "not run" cells is present. The single-evaluation scope caveat is in I2-m2. |
| I1-m1 P3-m3 description | Partially resolved (accepted) | The text now bounds what (a) can show and says column order was not permuted. It still says "(yl restored)" and does not say the comparison was against a second `exmain`. Not blocking. |
| I1-m2 size of A's serial change | Resolved | 3.4e-9 relative; all Te-box `yldot`/`sfscal`; pytests "not measured". |
| I1-m3 FMA stated as fact | Resolved in the table | Item 1 (line 55) still says "reproduces exactly the OpenMP residual"; the count and row match, the values were not compared. Not blocking. |
| I1-m4 `emcoef` / `fmombal` hazards | Partially resolved | Both are in the AIUE-60 row, and H3 is correct (`fmombal` only via `mombal`, `isimpon=5`; checked `bbb/pandf_plasma_momentum.m:669-707,1018`). The AIUE-50 F9 row (line 431) still says "`mombal` for `isimpon` 6/7", so the document now contradicts itself. |
| I1-m5 references, rebase | Partially resolved | Rebase verified (`45a9aa1`, `f516b40` ancestors). The `jac_calc` range is right, but the column loop starts at `bbb/oderhs.m:1095`, not `:1100`. |
| I1-m6 1e-6 is a margin | Resolved | Spreads are shown next to the bound. Small caveat: the "full ≤ 4.6e-9" figure is the AIUE-56 OpenMP-vs-serial residual, not an emulation spread, and `te_phi` (7.15e-9) is not mentioned. |

## What was checked and how

All on macOS arm64. Outputs are under
`/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev55r2/`.
I ran one UEDGE process at a time.

1. **Diff and response.** `git diff 45a9aa1..HEAD` and `git diff ca9c0b9..48e877c`. Only docs and plan files changed,
   with no `.claude` skills, agents or hooks.
2. **Scratch tree.** `uedge-wt/AIUE-61-replay` is at `db6a8ea` = `0fac655` + PRD + C1 fix `4fae2f9` + replay patches
   `918bdb6` and `db6a8ea`. It is clean, and the patches match `replay/patches/`. Venv `.so` files are from 05:22,
   after `db6a8ea` (05:16). Provenance in each `check.json` and `record.json` gave the commit behind each result
   (Te box: `918bdb6`; full and serial checks: `db6a8ea`).
3. **Harness outputs.** A script printed every `replay/*/check.json` (spec, provenance, per-report mismatches). Then
   `cli.py compare` on: `bs_te_serial`/`rp_te_serial`, `bs_full_serial`/`rp_full_serial` (AGREE);
   `t_c1_n16_1`/`_2` (AGREE); `t_c1_dflt_1`/`_2` (MISMATCH 70); `t_rp_n16_1`/`_2` (AGREE); `bs_full_serial` against
   `t_c1_n16_1`/`_2` (5698 each), `t_rp_n16_1` (AGREE) and `t_c1_dflt_1` (AGREE: one default-chunk C1 run bitwise
   equal to serial, which AIUE-56 reported 0/30 at 4 threads; this suggests the residual rate depends on load). The
   `run.log` and `.out` files of the `full_*` runs with `OMPJacNchunks=-1` all show exit −11 and no record.
4. **Emulation.** I read `replay/emul_replay.py` and printed the "mul" mismatch counts from `em_*/emul.json`
   (`isjacreset` = 1). There is no 4-chunk run at R = 3920.
5. **Reviewer run (allowed budget).** `cli.py check --preset tebox --arm jac --threads 4 --repeats 3 --ppp
   '{"OMPJacReplay": 25, "OMPJacNchunks": -1, "OMPAutoBalance": 0}' --python venvs/AIUE-61-replay/bin/python`. The
   harness accepted the diagnostic key. Result: **AGREE** in all sections against serial, 3/3, and determinism AGREE
   (`rev55r2/te_contig_R25/`), at `db6a8ea`.
6. **Code.** `ppp/omp_parallel.F90:309-333` (InitOMPJac chunk count and `nnzmxperchunk`), `:645-748` (OMPJacBuilder:
   automatic arrays `:672,675`, `firstprivate` `:713-714`, `schedule(dynamic)`); `ppp/parallel.F90:320`
   (`isjacreset` block); `bbb/oderhs.m:1095,1220` (serial loop; `isjacreset` commented out); `bbb/bbb.v:3305`
   (`isjacreset` /1/); `bbb/odesetup.m:326-336,362-364` (`ubw`, `nnzmx`); `bbb/bbb.v:2994` (`lenpfac` /60/);
   `bbb/pandf_plasma_momentum.m:669-707,1018`; `setup.py:73-93` (no `-Ofast` or `-fstack-arrays`).
7. **Cost arithmetic.** neq = 44352, `ubw` = 3920. Per thread at T threads: 2·neq/T + ubw evaluations, so the
   overhead is T·3920/88704 = 4.42 % × T (17.7 % at T = 4). Replay elapsed times as in I2-M2.
8. **PRD.** §9 (in-scope OpenMP-only changes, escalation, "measured before and after", 10 % report), §11 (MVP and
   fallback bullets), decisions 4/7/9.
