# AIUE-60 plan review, round 2

Reviewed: `.claude/plans/AIUE-60-omp-races.md`, `docs/reviews/AIUE-60-clip-check.py`,
`docs/reviews/AIUE-60-shared-writes.py` and `docs/reviews/AIUE-60-passed-args.py` at `203a5ff`
(branch `bugfix/v9-AIUE-60-omp-races`; round 1 reviewed `d2fac6e`). Also read: the round-1 report and its response, the
diff `d2fac6e..203a5ff`, the AIUE-58 RHS RCA (`AIUE-58` worktree `3aa0357`), the AIUE-56 validation record
(`AIUE-56/docs/reviews/AIUE-56-validation.txt`), and the AIUE-61 plan (`AIUE-61` worktree).

Decisions in force, not re-opened: B1/B3 go to AIUE-69; `isimpon=5` relies on the existing `exmain` roadblock; AIUE-60
merges first; `nfsp` in the RHS path goes to AIUE-58/59; the `jacrhs` gate is no-regression only.

## Verdict

**REVISE**

## Summary

The revision resolves L1-M1, L1-M3, L1-M4 and L1-M5, and all four minors. B2 and B4 are per-call scratch. The recovered
Probe S script is byte-identical to the one round 1 re-ran and reproduces 145 units and 161 variables. The new G1 band
is in the C2 scale. Re-run offline on the Probe C data, it reproduces the plan's numbers, and the negative control
still fails decisively.

One new MAJOR remains, in the flow gates that L1-M2 added and in the unchanged gate (a). Gates (a), (d) and (e) compare
"PASS" and equation-name sets between two K=2 samples. On macOS, three groups per arm are bitwise only some of the time
on AIUE-56, so the pre-registered gates can fail with no regression. I estimate this at roughly 15–30 % for the whole
flow. Gate (e) also can't see a `yldot` regression in any equation that C2 already puts into the set (`te`).

## Findings

### BLOCKER

None.

### MAJOR

**L2-M1: The flow no-regression gates (a), (d) and (e) can fail by chance, and (e) can't see RHS-section
regressions.**
Location: plan Testing 3, gates (a), (d) and (e), and acceptance criterion 3.

How the gates work:

- A flow group is PASS only if all K runs agree bitwise with serial and with each other
  (`AIUE-57/tests/deterministic_omp/harness/flow.py`, `group_verdict`).
- The "mismatch rows" set is the set of row-equation names over all failing sections, Jacobian and vectors
  together (`mismatch_equations`).
- The flow runs K=2 at 2 and 4 threads.

The AIUE-56 build that serves as the baseline is only intermittently bitwise in several of these groups
(`AIUE-56-validation.txt`, C1-gate block, one-evaluation `jac`):

- Te box: 2 threads 1/5, 4 threads 1/30.
- Full problem: 2 threads 2/5, 4 threads 0/30.
- `te` and `te_phi`: 0/5.
- `ti`, `ni`, `up`, `ng`: 5/5.

The one-evaluation `jacrhs` arm carries the same Jacobian C2. Its `yldot`, probe and `fnrm` are bitwise
(`AIUE-56-validation.txt`, `jacrhs` K=5 block; AIUE-58 RCA "Why the earlier RHS checks were green").

Consequences:

1. **False failures.** With a per-run bitwise rate p, AIUE-56 PASSes a K=2 group with probability p². In that case
   AIUE-60 fails (a)/(d) with probability 1−p², and fails (e) as well, because `{te}` is not a subset of ∅. With the
   rates above (Te box 2 and 4 threads, full 2 threads), that is about 17 % per arm, or about 30 % over `jac` and
   `jacrhs`. The rates come from K=5/30 samples, so take this as an order of magnitude. The plan pre-registers no
   handling, and its own rule (Testing 5) forbids reclassifying after the fact.
2. **Blind spot in (e).** Gate (e) compares equation names, not sections. All groups that evolve Te are FAIL on AIUE-56
   because of C2: Te box, `te`, `te_phi` and full. In those groups a new `yldot` or `yldot_probe` mismatch in `te`
   rows (for example, from the plate BCs that read `areapl`) still gives a subset of `{te}`, so it passes. Gate (d)
   doesn't apply to these groups. On the `jacrhs` arm, the RHS sections are where this ticket's changes (A1, A2)
   actually run on workers.

Resolution: pre-register gates whose outcome doesn't depend on which way an intermittent baseline group fell, and
that are section-aware on `jacrhs`. For example:

- Apply "PASS stays PASS" only to groups that were bitwise in every AIUE-56 run (here `ti`, `ni`, `up`, `ng`). Judge
  every other group by (b)/(c).
- On `jacrhs`, require the non-Jacobian sections (`yldot`, `yldot_probe`, `sfscal`, `fnrm_*`) to agree with serial
  in every run, as they do on AIUE-56. Judge the `jacobian:*` sections by (b)/(c).
- Alternatively, pre-register a re-run rule: a group that fails (a), (d) or (e) is re-run on both builds at K≥5 and
  judged by rate.

Acceptance: the plan states the rule and gives a short argument why its false-failure probability is small. The data
for the section-aware form is already in `flow.json` (`failing_sections` per group).

### MINOR

**L2-m1: G1's τ and the strict rule rest on observed values, not bounds. Pre-register the edge cases.**
Location: Testing 4 G1; `AIUE-60-clip-check.py:126,166-170`.

- τ = 1e-8 covers the largest C2 deviation seen in AIUE-56, 7.15e-9 × row max (`te_phi`). It is not a bound: the
  C1-gate threshold is 1e-6. When `sfscal` differs (G2), the entry's distance to the threshold also gains the
  relative `sfscal` change, which is itself C2-sized, giving up to about 1.4e-8 × row max in the worst case.
- The strict rule assumes that common values and `sfscal` being bitwise equal means the run has no residual. For
  `full` that need not hold:
  - The full problem has C2 in every 4-thread run (AIUE-56 0/30 bitwise), yet Probe C's full run shows
    `value_diffs_common = 0`. So at L = 1e-6 the C2-affected entries were all clipped.
  - A C2-perturbed entry that straddles L would then be one-sided while the common values stay bitwise, and the
    strict rule would fail on a legitimate flip.
  - Probe C's exact count match (442 576 + 370 386 = 812 962 = predicted) shows this didn't happen in that one run.

Suggested: pre-register the handling. For example, apply the strict form only to presets with no C2 (`ni`). Or state
what a G1 failure means when every offending entry lies within (τ + `sfscal_max_rel_diff`) × row max, or lies in C2
rows.

**L2-m2: Make the Probe S post-fix expectation numeric.**
Location: task 4; acceptance criterion 6.

On the AIUE-60 tree today, `AIUE-60-shared-writes.py` lists 161 variables and `AIUE-60-passed-args.py` lists 137. Most
of the 137 are read-only inputs, such as `rsacoef`, `kxords_aph`, `methe` and `nx`, which "only the listed remainder"
doesn't name. After the fix the expected lists are:

- shared-writes: 161 − 14 = **147**, with `areapl`, `sputflxllim`, `sputflxrlim`, `timingpandfon`, the 8 `com.Timing`
  and the 2 `com.Timespl` entries gone;
- passed-args: **135**, with exactly `workh` and `iflag_aph` gone.

Stating these numbers (or diffing against today's outputs) turns acceptance criterion 6 into a sharp check.

**L2-m3: The cross-ticket references in AIUE-61's plan are stale. This is for the main session, not an AIUE-60
defect.**
Location: `AIUE-61/.claude/plans/AIUE-61-omp-static-partition.md:32,135-137,329`.

- AIUE-61's plan still cites AIUE-60 plan `d2fac6e` and its "Parts A and B" (G0b). At `d2fac6e`, Part B included B1
  and B3, which are now Part C.
- The merge order there already matches this plan (line 29: owner, AIUE-56 → AIUE-60 → AIUE-61). AIUE-60's line 285
  ("AIUE-61's plan is being revised to say the same") can say "says the same".

## Status of previous findings

| Finding | Status | Evidence (checked here) |
|---|---|---|
| L1-M1 B1/B3 staleness | **Resolved** | See below the table. |
| L1-M2 `jacrhs` arm excluded | **Partially resolved** | The arm is now in the flow (`--arms jac,jacrhs`) with no-regression gates (d)–(f) and a gated cross-build compare when deterministic. The `TimingPandfOn` trace is in A2; I re-checked `bbb/pandf.m:573-579` and `ppp/omp_parallel.F90:1227,1232,1294`. The gate design is not sound yet: L2-M1. |
| L1-M3 Probe S script missing | **Resolved** | See below the table. |
| L1-M4 G1 band scale | **Resolved** | See below the table. |
| L1-M5 merge order | **Resolved** | Plan "Merge order": AIUE-60 first, AIUE-61 rebases and re-runs. The AIUE-61 plan records the same order as the owner's (`:29-31`) and its final validation on the combined tree (`:303`). |
| L1-m1 `isimpon=3,4` wording, line length | **Resolved** | A3 cites "(disabled)" and the roadblock. The snippet lines are 74 and 73 columns, as the gotcha now states. The new code ends with the same `nfsp` as `bbb/pandf.m:50-51`. |
| L1-m2 G2 round-off | **Resolved** | G2 is report-only. Only a `suscal` mismatch gives exit 2, with a pre-registered re-run once, then a harness error. |
| L1-m3 rule texts | **Resolved (planned)** | Task 5 edits `CLAUDE.md:23` and `variables-forthon.md:48` (both lines verified). The count `variables-forthon.md:37` (522) becomes 526: today `grep -c +threadprivate bbb/bbb.v` gives 522, and A1, A2 and B2 add 4 `bbb` variables. No `refs.lock.json` key sits on a touched line (`bbb.v` 951, 986-987, 4136; `com.v`; `aph.v`; `pandf.m` 48-51; `parallel.F90` 288/292). `check_context_refs.py --changed origin/v9-develop` reports OK at `203a5ff`. |
| L1-m4 TSan unexpected groups | **Resolved** | Testing 5 pre-registers fail, classify, then a re-reviewed amendment or a recorded failure, never reclassified. |

**L1-M1, resolved.** B1 and B3 are out of task 1. The GOTCHA forbids `com.v:427-429` and `bbb.v:669-670,679,683`, the
VALIDATE step checks that the `ghxpt`/`fngysi` directives are absent, and both items are in Part C → AIUE-69. B2 and B4
are per-call scratch, with no value taken from the master:

- **B2.**
  - `sputflxllim`/`sputflxrlim` appear only in `bbb/bbb.v:986-987` and `limiter_patch`.
  - Each `(iy,igsp)` is zeroed (`pandf_boundary.m:4957,5041`) and accumulated before it is read at `:4995,5078`, in the
    same iteration.
  - The neighbours `sputflxlb/rb/w/pf` are already `+threadprivate` (`bbb.v:984-989`).
  - The worker copy that `OmpCopyPointerbbb` makes is overwritten before it is read.
- **B4.**
  - `B2VAhL` sets `IFLAG = 0` first (`com/comutil.m:3608`) and fills `WORK` before it reads it (`:3685` → `:3692`).
  - The writes to `workh`/`iflag_aph` in `aph/aphread.m:920-951` are master-side `B2INhL` setup. `B2VAhL` does not
    read them back.
  - No `OmpCopy*aph` is called (`ppp/omp_parallel.F90:687-698`).
  - The only other hit, `pyscripts/bas2py_rules.py:3329`, is a name-translation rule, not a reader.

**L1-M3, resolved.**

- `shasum -a 256` of the committed `AIUE-60-shared-writes.py` is `6eeeacda…6b0b1d`. That equals the plan, and it equals
  the scratchpad copy round 1 re-ran (`/private/tmp/.../2129e705-.../scratchpad/probe/shared_writes.py`).
- `AIUE-60-passed-args.py` equals `logs/AIUE-60/passed_args.py` (`c8c8ce78…164f`).
- A different, dynamic `shared_writes.py` in another scratchpad (`4fd741ca…`, Oct 14) is unrelated.
- Re-run on the AIUE-60 tree: "145 reachable units; 161 variables". Every entry falls in Parts A–C, the MC/PNC and
  `ext_neutrals` paths, `sendbdry` (MPI), or the `TimingPandfOn`-gated `PandfTiming`.
- The AIUE-50 `scan_saved_locals.py` it imports is committed (`77fd77b`) and clean.

**L1-M4, resolved.**

- The band is `| |J| − L/su(c) | ≤ τ·rowmax_side`, consistent with the C2 statement "≤ 7.2e-9 × row max" (τ = 1e-8 ≥
  7.15e-9; see L2-m1 for the edge cases).
- Re-run offline on `logs/AIUE-60/probeB_{ni,full}` (AIUE-56 build, so the column rule):
  - Band population: 16 717/636 497 (`ni`) and 59 033/2 474 283 (`full`). Matches the plan.
  - Non-flips: 62 006 and 734 080. Matches the plan.
  - Of the predicted rule-difference entries, 7 395/69 401 and 78 882/812 962 are in the band.
  - G1 = FAIL on both. With `value_diffs_common = 0` and `sfscal` bitwise, the strict rule also fails them.
  - Serial against itself: G1 PASS.
- The negative control (G3) still bites.

## Not independently verified (environment)

- Nothing was built or run in UEDGE, per the budget. Not checked here:
  - the claim that the AIUE-60 OpenMP clip runs will have bitwise common values;
  - the TSan feasibility on `ng`/`full`;
  - the Forthon output for `aph` with a threadprivate dynamic array (round 1 checked the `api` precedent).
- The false-failure estimate in L2-M1 uses the AIUE-56 validation rates (K=5/30, `jac` arm). `jacrhs` rates at 2
  threads were not measured there.

## What was checked and how

- **Diff and response.** `git diff d2fac6e..203a5ff` (6 files), the response table against each plan section, and
  the AIUE-61 plan's merge text.
- **B2/B4.** `git grep -n -w` over `*.m *.v *.F90 *.py *.f` for `sputflxllim`, `sputflxrlim`, `workh` and
  `iflag_aph`. Read `limiter_patch` (`pandf_boundary.m:4940-5000`), `B2VAhL` (`comutil.m:3417-3700`) and `aph.v:195-215`.
  Checked the `OmpCopy*` calls in `ppp/omp_parallel.F90`.
- **Roadblock.**
  - `bbb/odesetup.m:6727-6772` lies in `exmain_f`, after `call allocate` (`:6649`). `allocate` runs `c!omp call
    InitParallel` (`:369`), which sets `ParallelJac`/`ParallelPandf1` (`ppp/parallel.F90:10-40`). So the roadblock
    sees the switches on every `exmain`.
  - The `isimpon` condition allows only 0, 2, 6 and 7.
  - B2's path is `isimpon` 4–7, so it is reachable under OpenMP with 6 and 7.
- **Flow semantics.** `harness/flow.py` (`group_verdict`, `mismatch_equations`), `harness/compare.py` section names,
  and `harness/worker.py:174-177` (one evaluation: `ftol=1e20`). Also the AIUE-56 validation C1-gate and `jacrhs` blocks,
  and the AIUE-58 RCA §"Why the earlier RHS checks were green".
- **Clip check.** Loaded the committed script through `importlib` and re-evaluated `pattern_diff`, `g1_pass`,
  `in_band` and `predicted` on the Probe C `.npz` files with `venvs/AIUE-56-omp/bin/python -I` (scratch script in
  `/tmp/aiue60r2/`). Computed row maxima (all 1), the fraction of entries with `L/su(c) < τ·rowmax` (18.7 % `ni`,
  13.9 % full), and the `sfscal`/`suscal` equality.
- **Probe S.** Ran both scripts with `python3 -I` on the AIUE-60 tree (read-only). Hashed them with `shasum -a 256`.
- **AI-layer.** `CLAUDE.md:23`; `variables-forthon.md:37,48`; the `threadprivate` counts in `bbb/com/aph/api.v`
  (522/0/0/25); the `refs.lock.json` keys in the touched files; `.claude/hooks/change_kind.py` (plans are artifacts,
  and `CLAUDE.md`/context need the code-facts trailer); `uv run .claude/hooks/check_context_refs.py --changed
  origin/v9-develop` gives OK. The worktree was left clean.
- **Line references re-checked.** `com/com.v:506,508,514,517-521,566-567`, `bbb/bbb.v:951,986-987,4136`,
  `aph/aph.v:203,210`, `api/fmombal.m:247-248`, `bbb/pandf.m:48-51,573-579`.
- **Tools.** `serial_check.py` options (AIUE-53 `15ae327`) and `AIUE-56-c1-gate.py` bounds (1e-6 × row max).
