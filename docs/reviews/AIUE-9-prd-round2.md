# PRD review: AIUE-9 "Create end-to-end test suite" (round 2)

PRD: `docs/prds/AIUE-9-create-end-to-end-test-suite.md` (852 lines, uncommitted in worktree `AIUE-9-planning`)
Repo checked: worktree `AIUE-9-planning` at `0fac655` (v9-develop). Old suite: `upstream/pytests` at `b535508`
(read with `git show`/`git ls-tree`; not checked out).
Previous round: `docs/reviews/AIUE-9-prd-round1.md` (REVISE, 0 BLOCKER / 7 MAJOR / 9 MINOR).
Reviewer: uedge-reviewer (PRD stage), 2026-10-14.

## Verdict

**REVISE**: 0 BLOCKER, 1 MAJOR, 8 MINOR.

## Summary

The revision is substantial and mostly sound. Six of the seven round-1 MAJORs are resolved, and I checked each fix
against the code. The locality protocol now matches `jac_calc` on flag, restore call and out-of-window rows. The cost
model is plausible. History dependence is cited and measured on every family. Variant safety and the INERT wording
are fixed, and the `-O0` build is now a separate opt-in. One MAJOR is left, and it is in the core harness protocol.
§6 and §7.2 still do not say how the ~248 dynamic-array inputs get a base value or when their variant is applied. The
"parent runs `input.py` without allocate" design also clashes with the real family inputs: three of the five small
families set dynamic arrays after a mid-file `bbb.allocate()`. The MINORs are about protocol details: timestep-case
ordering, the locality threshold, CI guard triggers, the path filter, fork assumptions, and AI-layer sequencing.
`/spec` should settle them, but none blocks it.

## Findings

### MAJOR

**P2-M1: Dynamic-array inputs have no defined base value or application time, and the fork protocol clashes with the
family inputs (P1-M4, partly resolved).**
*Location:* §6 evaluation protocol (parent line; child steps 1–3), §7.2 "Base value `d`", "Timing", and the value-rule row
"array: rule applied to the whole array".

*Evidence.*
- **How many.** 248 tagged `+input`/`+maybeinput` lines are dynamic (`_real`/`_integer`/`_character`). Only six are
  marked "input after alloc": `tvapi`, `tvapo` (`bbb/bbb.v:834-835`), `tvaplb`, `tvaprb` (`:1011-1012`), and
  `tvapllim`, `tvaprlim` (`:1019-1020`).
- **What the PRD defines.** Scalars and static arrays are applied before `allocate`. The six "input after alloc"
  arrays are applied after `allocate` and the restore.
- **The gap.** The other ~242 dynamic arrays have no stated phase. Examples are `nwallo`/`nwalli(0:nx+1)`
  (`bbb/bbb.v:621-622`) and `recycflb`/`recycfrb` (`:925-926`).
- **Base value undefined.** `d` is "the family's live value after `input.py`, read from the Forthon variable". The
  §6 parent runs `input.py` "inputs only, no allocate/restore". A dynamic array whose shape depends on `nx`/`ny`
  has no allocated live value at that point, so `d` is undefined for about a quarter of the inventory.
- **The family inputs contradict "no allocate".** `d_only`, `d_mols` and `ortho` call `bbb.allocate()` part-way
  through and then set the dynamic arrays `bbb.nwallo`/`bbb.nwalli` (D_only `input.py:58-60`;
  `orthogonal_unittest/input.py:57`; D_mols `input.py:61`). Every family ends with `bbb.allocate()` +
  `hdf5_restore`. Copying these files "as assembled" (§8) does not give the input-only script the parent needs.
  Stripping the allocate calls changes when `nwallo` is set.
- **Shared state.** Some `+input` arrays are recomputed during `allocate`/`exmain`. An array set before that can be
  overwritten, so its variant becomes a silent INERT. That is why the phase must be explicit.

*Acceptance.*
1. §6/§7.2 state the default phase for **all** dynamic arrays (for example: after `allocate` and the restore, before
   `exmain`). `overrides.toml` remains the exception mechanism.
2. §7.2 states where `d` is read for dynamic arrays (for example, in a reference child after `allocate`, restore and
   the family's own post-allocate lines).
3. §6/§7.1 say how a family `input.py` is split into a pre-allocate part (run in the parent) and a post-allocate part
   (replayed in each child after `allocate` + restore). Name the three affected families.

### MINOR

**P2-m1: Timestep-case ordering, and inputs that are inert because `dtreal=1e20`.**
*Location:* §6 "Time-step term", §7.2.
- **Ordering.** `exmain` overwrites `ylodt` with the current `yl` (`bbb/odesolve.m:151`: `ylodt(i) =
  (1-isyloext)*yl(i)+isyloext*yloext(i)`).
  - If the `timestep` case sets `ylodt` before step 4, then `yl−ylodt = 0`. The case then tests only the
    `(1−fdt*)·yldot` factors (`bbb/pandf.m:440-492`).
  - Fix: state that `dtreal`, `dtuse` and `ylodt` are set after `exmain` and before `pandf`, or use
    `isyloext=1`/`yloext`.
- **Inert inputs.** Several `+input` variables act only when `dtreal < 1e15`: `fdtnixy`, `fdtphixy`, … (`bbb/bbb.v:250-256`,
  used only in `add_timestep`) and `cfqydt` (`bbb/bbb.v:366`, multiplying `fqydt ∝ 1/dtreal` at
  `bbb/pandf_potencur.m:217-222,286`).
  - Under the default protocol they are INERT or MARGINAL in every family, and no override value can fix that.
  - Acceptance: an override can assign a variant to the `timestep` configuration, and the initial list names these
    inputs. Otherwise the PRD should say explicitly that they are uncovered.

**P2-m2: Locality protocol details (residual from P1-M1).**
*Location:* §7.5, §7.9.
- **Per-column reset.** `jac_calc` re-initializes `wk` to `yldot00` over the band **for every column**
  (`bbb/oderhs.m:1141-1143`). §7.5 initializes the work vector once (step 1).
  - The restore call in step 4 writes `local(y0)` into the window. Wherever that differs from `f00`, the difference
    leaks into the next column's "local difference", so the mismatch is attributed to the wrong column.
  - State a per-column re-initialization.
- **Threshold.** "Disagree beyond tolerance" has no definition. Column differences are about `del`≈1e-8 (`bbb/bbb.v:3302`)
  times `yldot`, so the `yldot` round-off spread in `tolerances.toml` is amplified by about `1/del` relative to them.
  Rows whose by-design mismatch lies near the threshold can flip between Linux (where references are made) and macOS
  (where §11 also requires a pass).
  - Define the threshold relative to the column scale.
  - Use a margin band, as the variant classes do, and ignore rows inside it.
  - Have Phase 1/3 measure cross-platform reproduction of the pattern.
- **Cost and size.**
  - The §7.9 row says "3 full + 1 local per column". The §7.5 steps give 2 full + 2 local.
  - The pattern sizes are not in the §7.3 size table or the caps.
  - The nightly `meth*` locality on `large_dd2c` (about 18 configurations × the sampled check) is not in the nightly
    cost estimate.
- **Locality additions.** `xlinc`, `xrinc`, `yinc` and `isjaccorall` were added because they "affect locality"
  (§7.2). They do nothing in a full evaluation (the `xc<0` branch, `bbb/pandf.m:53-66`), so the sweep classifies them
  INERT. §7.5 runs locality only for the default and the `meth*` variants. Either run locality for these additions too
  (nightly) or drop them.

**P2-m3: Nightly path filter still misses included headers and C sources (P1-m3, partly resolved).**
*Location:* §4 Integration, §11 CI.
- Every `.m` file `c!include`s `bbb.h`, `../com/com.h`, `../mppl.h` and `../sptodp.h` (for example
  `bbb/pandf.m:1-4`). These define the array-size macros (`nispmx`, `ngspmx`, …).
- Also not covered by the filter: `**/*.c` (`com/handlers.c`, `com/vector.c`, `bbb/exmain.c`), `ncl/*.inc`, and
  `src/uedge/__init__.py` (import-time behaviour), as well as the workflow file itself.
- Add `**/*.h`, `**/*.c`, `**/*.inc`, `src/uedge/**` and `.github/workflows/nightly-tests.yml`.

**P2-m4: Reference guard: triggers, scope and additions.**
*Location:* §4 "Reference-change guard", §7.6, story 4.
- **Push events.** `build-test-wheel.yml` runs `on: [push, pull_request]` (`:4`). On a push there is no PR base and no
  description. Say that the guard runs only on `pull_request`, or how a push is handled.
- **Description edits.** The guard reads the PR description, but the default `pull_request` types do not include
  `edited`. Adding "Default results: changed" after the first run does not re-run the guard. Add
  `types: [opened, synchronize, reopened, edited]`.
- **Shell safety.** Read the description through an environment variable, never interpolated into the shell.
- **Coverage of the guard.** The guard compares manifests "per variable". The default vector, the diagnostic
  intermediates, the `timestep` case and the locality patterns all live in the `.h5` file. The manifest must carry a
  SHA for each of them, or a change to them passes as "no manifest change".
- **Pure additions.** Story 4 requires `Default results: changed` for a pure addition (a new default-off switch).
  Under CLAUDE.md that declaration means default results moved, which they did not. Allow pure additions of entries
  for variables that are new to the inventory without a declaration, in the same way as prunes.
- **Bounds audit.** The `--checkbounds` audit runs only "on a full run" (§7.6 step 3). Variants added with `--only`
  should be audited too.

**P2-m5: The fork-safety premise and import-time side effects.**
*Location:* §6 "Fork safety", §10 `.uedgerc.py` isolation.
- **Threads.** "The parent … has no threads at that point" does not hold if the family parent is the xdist worker:
  - execnet runs a receiver thread in each worker;
  - numpy 1.26.4 wheels start an OpenBLAS thread pool at import unless `OPENBLAS_NUM_THREADS=1`.
- **Fix for threads.** State that each family parent is a dedicated subprocess, with the thread variables set before
  `import numpy`. Otherwise drop the claim and rely on the spawn fallback.
- **Network call at import.** `import uedge` makes a synchronous PyPI request with no timeout (`_banner.py:87` →
  `_checkver.py:17`, `urllib.request.urlopen(...)`), unless `UEDGE_BANNER=0` or `UEDGE_VERSION=0`.
  - With the spawn fallback this happens once per variant.
  - On an offline runner it can stall until the TCP timeout.
  - The harness environment should set `UEDGE_BANNER=0`, next to the `HOME`/`.uedgerc.py` guard.

**P2-m6: AI-layer sequencing contradicts the Phase 4 retirement gate (P1-m4/P1-m5 residual).**
*Location:* §4 Deployment, §8 "AI-layer PR", Phase 3/4.
- **The contradiction.** §4 says `upstream/pytests` leaves "the AI layer and local validation once the Phase 4 gate
  passes". But the single AI-layer PR is "merged before the CI switch" (Phase 3), and it rewrites the `validate`
  skill's "Regression suites (pytests branch)" section. It also drops `pytests/` from `check_context_refs.py:55`
  "once retired".
- **Phase 4 branch.** Phase 4 then removes "the remaining references … from the AI layer". That is a process change,
  which belongs on a `feature/v9-ai-*` branch, not the ticket branch (`branching.md`, "never covers a process change").
- **What to state.** Either:
  - two AI-layer PRs: Phase 3 adds the new suite while keeping the old one in `validate`, and Phase 4 removes the old
    suite; or
  - that the old suite leaves local validation in Phase 3, accepted by the epic owner.
- **`physics-workflow.md`.** On the ticket branch only the factual part (where the regression suite lives) qualifies
  as a code-fact. A new *obligation* ("add a variant and regenerate for a new switch") is a process step and goes in
  the AI-layer PR. Round 1 suggested this file as a code-fact, so this is a narrowing, not a reversal.
- **Phase 4 grep.** The expected-match list should also include `MANIFEST.in:3` (`#recursive-include pytests *`).

**P2-m7: The sketch fallback for small families narrows decision 12 without saying so.**
*Location:* §6 Key patterns ("switches to sketches if it exceeds its cap"), §7.3 SketchStore, §11 Localization.
- Decision 12 says full vectors for small families. §11 promises `(ix,iy)` localization for small families.
- `slab_phi` is estimated at 6.5 MB against a 7 MB cap, so the fallback is likely to trigger. That would silently
  break both.
- Make the fallback for a small family need the epic owner's confirmation (or a cap raise) rather than happen
  automatically.
- A related point: the seeded Gaussian projection vectors are regenerated at test time. numpy's `Generator`
  distributions carry no stream-compatibility guarantee across versions, but the legacy `RandomState` does.
  - Either generate the vectors with `RandomState` or your own deterministic generator, or record the numpy version
    used to build them.
  - Otherwise a numpy upgrade on a developer machine fails every sketch test.
  - The same "data, not seeds" principle §6 applies to base states should apply here.

**P2-m8: Minor accuracy and consistency points.**
- **Locality cost row.** §7.9 says "3 full + 1 local"; see P2-m2.
- **`Default results: changed`.** It is used both as a CLAUDE.md declaration and as a guard keyword. Story 4's
  "(new variant)" suffix should be accepted by the parser, or the keyword split from the declaration; see P2-m4.
- **`restart`.** `bbb.restart` (`bbb/bbb.v:3083`) is a tagged `+input` that the harness pins to 1. It belongs in the
  initial EXCLUDED list with a reason, alongside `svrpkg`. Any other tagged variable the harness overrides needs the
  same: an OFAT value there is overwritten and reads as INERT.

### Notes on the user's decisions (not PRD defects)

None new. The round-1 notes on decisions 8 and 12 are addressed:
- Decision 8: the additions list is put to the epic owner for confirmation (§7.2, Appendix decision 8).
- Decision 12: a history monitor is added, with review at 150 MB (§7.3).

## Status of previous findings

| ID | Status | Evidence |
|---|---|---|
| P1-M1 locality | **Resolved** (residual details in P2-m2) | §7.5 now sets flag +1 for both calls, as `jac_calc` does: `oderhs.m:1716,1939` set it before `ffun`/`rhsnk`, and `jac_calc` calls `pandf` at `:1160`. Rows outside the window keep `f00` (`:1142`). There is a restore plus local re-call (`:1216`) and a clean full re-evaluation. The check is an old-vs-new pattern comparison. The by-design causes are named and correct: `ExtendedJacPhi` default 1 (`bbb/bbb.v:3298`); band widening at `oderhs.m:1125-1138` that `initialize_ranges` does not mirror; full-ix windows at `pandf.m:53-66,114-155`. §11, story 6 and Risk 8 are reworded. |
| P1-M2 runtime | **Resolved** (P2-m2 notes one missing nightly cost item) | §7.9 gives a cost model with assumptions. My arithmetic: 970 × 0.2–0.6 s ≈ 3–10 CPU-min per small family; slab locality 4,522 columns × 4 calls × a few ms ≈ 1 min. Both fit sharded 4-vCPU jobs within 20 min. The CI design is build once, then shard per family; large-family locality and `meth*` locality move to nightly. Budgets are re-checked in Phases 2 and 3. Risk 4 no longer contradicts the isolation design. |
| P1-M3 history | **Resolved** | The old-suite comment is cited in §6. `measure_history.py` (exmain ×1 against ×2, first against second `pandf`, A→B→A) runs on every family and fixes `W`/`P`. Defects are filed. Families with history dependence run with a fresh process (§11). The fork happens before any `allocate`/`exmain`, so it carries no solver history. |
| P1-M4 variant definition | **Partly resolved**; see **P2-M1** | Resolved: base value = live value; applied value recorded and replayed; package-qualified keys; `--prune`/`--rename` with guard rules; story 10. Not resolved: the timing and base value for the ~242 dynamic arrays not marked "input after alloc", and the clash with the family `input.py` allocate calls. |
| P1-M5 variant safety | **Resolved** | INVALID now covers crash, timeout, nondeterministic and bounds-audit errors. Per-variant timeouts. SENSITIVE variants generated twice. `--checkbounds` exists (`setup.py:741-745`). Override for `jxsori`/`jxsoro` (`bbb/bbb.v:644,646`) confirmed. The `--only` audit gap is in P2-m4. |
| P1-M6 INERT | **Resolved** | Story 2, §13 and Risk 2 say INERT is only a candidate; deletion needs code inspection plus coverage; SENSITIVE→INERT is what the suite guarantees. |
| P1-M7 `-O0` | **Resolved** | §7.7 and §8 add a separate opt-in `-O0` build without traps. `--debug` is also attempted, and a trap is recorded as a finding (flags confirmed at `setup.py:84-93,747-751`). |
| P1-m1 counts | **Resolved** | Recount: 971 tag lines (bbb 950, com 19, aph 1, api 1). Comment-embedded tags at `bbb/bbb.v:558,2073,2076`, leaving 968. Seven character/`Filename` inputs. `methn` is 22/33. |
| P1-m2 family table | **Resolved** (new side effect in P2-m7) | `isphion=1` in d_only, d_mols and ortho. Slab: `cfyef=0.6` (`input.py:102`), `isphion=1` (`:123`), 8+24 × 1+16 = 32x17. neq 34·19·7 = 4,522 checks out. Slab row added; budget 30 MB. |
| P1-m3 path filter | **Partly resolved**; see P2-m3 | Now covers all `.m`/`.F90`/`.f`/`.v` and the build files. Still misses the `c!include`d headers and `.c`. |
| P1-m4 retirement/grep | **Partly resolved**; see P2-m6 | Phase 3 note with the `ls-remote` evidence added. The grep is widened and the expected matches listed (`MANIFEST.in:3` missing). The AI-layer PR timing now contradicts the Phase 4 gate. |
| P1-m5 AI-layer scope | **Resolved** (classification caveat in P2-m6) | `code-review`, `uedge-implementer` and `check_context_refs.py:55` (verified `EXTERNAL` tuple) are in the AI-layer PR. CI guard added. |
| P1-m6 thresholds/platform | **Resolved** | M=100 margin, MARGINAL class, INERT = bitwise on the generating build, pinned runner and gfortran, `regenerate-references.yml`, variants inherit tolerances with a sample check. |
| P1-m7 mutations | **Resolved** | 24 committed patches, `run_mutations.py`, expected test named for each; §11 says 24/24. |
| P1-m8 harness details | **Resolved** (new ordering issue in P2-m1) | `tipers` is in the base state (`src/uedge/hdf5.py:30-35`). `ylodt`/`dtuse` values given. `OMP_NUM_THREADS=1`. Serial path stated (`bbb/pandf.m:7-28`). Scaled `fnrm` for convergence. Intermediates are diagnostics only. gcov in `.gitignore`. `.F`→`.m` map caveat. |
| P1-m9 MVP wording | **Resolved** | §1 and §11 now say "visible in the tested configurations". |

## What was checked and how

**Code claims re-verified (commands: `sed -n`, `grep -n` in the worktree)**
- **`jac_calc`** (`bbb/oderhs.m:1012-1240`):
  - band and widening at `:1125-1138`;
  - per-column `wk` reset at `:1141-1143`;
  - local call at `:1160`, restore call at `:1216`.
  - The callers set `yl(neq+1)=1` before `ffun`/`rhsnk` (`:1716,1939`).
- **Flag-gated code:**
  - `add_timestep` gating (`bbb/pandf.m:735-741`) and body (`:390-510`);
  - `ishosor` (`pandf_plasma_continuity.m:714`);
  - `ismcnon` (`:39-122`);
  - `jacobian_reset` with `ismcnon=4` (`pandf_jacobian.m:126`).
- **`initialize_ranges`** (`bbb/pandf.m:31-245`): the `xc<0` and `isjaccorall` branch, `xccuts`/`xcturb`, and the
  point-wise source ranges.
- **`ylodt` assignment:** `bbb/odesolve.m:151` (the only Fortran writer); also `src/uedge/rundt.py:548,647`.
- **dtreal-dependent physics:** `pandf_potencur.m:217-222,286`; `cfqydt` at `bbb/bbb.v:366`.
- **`.v` lines checked:** `bbb/bbb.v` lines 33-41, 155-158, 180, 233, 250-256, 607, 621-624, 640-646, 834-835,
  925-926, 1011-1020, 1111-1114, 1298-1301, 2887-2905, 3070-3083, 3295-3304, 3377.
- **Tag inventory:**
  - counted with `grep -cE "\+(input|maybeinput)"` per `.v` file;
  - comment-embedded tags found with an awk position test;
  - dynamic tagged lines counted (248).
- **Build flags:** `setup.py:60-110,725-760`.
- **CI:** `build-test-wheel.yml` read in full. It triggers on `[push, pull_request]`; the matrix is at `:51`, the
  `testbranch` logic at `:55-66`, and the `LLNL/UEDGE` checkout at `:88-92`.
- **Python layer:**
  - `src/uedge/hdf5.py:14-80` (the restore list includes `tipers`/`tgs` when they exist);
  - `src/uedge/__init__.py:55-67` (`.uedgerc.py`);
  - `src/uedge/_banner.py:40-110` and `_checkver.py` (PyPI request at import).
- **AI layer:**
  - `grep -rn -i pytests` over the repo, excluding `.git`;
  - `.claude/context/branching.md:1-41` (change classes, code-facts rule);
  - `.claude/context/physics-workflow.md`;
  - `.claude/hooks/check_context_refs.py:45-56`;
  - `.claude/skills/create-prd/SKILL.md:51-131` (template: all 15 sections present and substantive).

**`upstream/pytests` at b535508**
- `git ls-tree` listing of all `input.py` files.
- `git show` of the D_only, D_mols, ortho, d_c and slab inputs:
  - mid-file `bbb.allocate()` followed by `nwallo`/`nwalli` in three families;
  - the final allocate plus `hdf5_restore` in all five;
  - slab grid, drift and potential settings;
  - d_c `isimpon=6`, `ngsp=2`.

**Decision fidelity:** all 13 binding decisions were checked against §4, §7, §11, §12 and the Appendix.
- No contradictions found.
- One unflagged narrowing of decision 12 (P2-m7).
- The additions to decision 8 are correctly flagged for the epic owner's confirmation.

**Not run** (as instructed): no build, no test suite, no `pandf` timing. The cost figures were checked only for
arithmetic consistency against the PRD's own per-call estimates.
