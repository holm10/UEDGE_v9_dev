# PRD review: AIUE-9 "Create end-to-end test suite" (round 4)

PRD: `docs/prds/AIUE-9-create-end-to-end-test-suite.md` (984 lines, uncommitted in worktree `AIUE-9-planning`)
Repo checked: worktree `AIUE-9-planning` at `0fac655` (v9-develop). Old suite: `upstream/pytests` at `b535508`
(read with `git show`/`git ls-tree`, not checked out).
Previous rounds: round 1 (REVISE, 0/7/9), round 2 (REVISE, 0/1/8), round 3 (REVISE, 0/1/7).
Reviewer: uedge-reviewer (PRD stage), round 4, 2026-10-14.

## Verdict

**REVISE**: 0 BLOCKER, 1 MAJOR, 5 MINOR.

## Summary

Round 3's MAJOR (P3-M1, the guard perimeter) is resolved. Tolerances, `family.toml`, existing overrides and the
comparison code are now guarded, with a stricter rule for loosening. Tests check `.h5` integrity against the manifest,
and §11 has test PRs for both paths. I checked the round-3 MINOR fixes against the code. The `cfqydt` fix works,
because `pandf` recomputes the saved-state interpolants on every call. The normal form, the renumbered locality steps,
the separate guard workflow and the forkserver isolation are all in place. One fix brought in a new MAJOR. P3-m6 now
points `validate` §4 at `measure_roundoff.py`'s OpenMP row, but that row only checks the RHS. The current check also
compares the parallel Jacobian against the serial one (`CheckJac`). Nothing else in the PRD covers that, so the adopt
PR would quietly drop the only check for OpenMP races in the Jacobian. The MINORs are a few stale sentences, some
storage and guard details, and calibration wording. `/spec` can settle all of them.

## Findings

### MAJOR

**P4-M1: The new `validate` §4 OpenMP check drops the parallel-Jacobian comparison.**
*Location:* §8 "AI-layer PR 1, adopt" (lines 714-715), §7.7 (line 610), §4 Out of scope (lines 185-187), §9 (line 754).

*Evidence.*
- **What the check does today.** `.claude/skills/validate/SKILL.md:70-79` sets `ppp.OMPParallelPandf1 = 1`,
  `ppp.OMPParallelJac = 1`, `ppp.CheckPandf1 = 1` and `ppp.CheckJac = 1`, then runs `bbb.exmain()`. That compares the
  serial and parallel RHS, and also the serial and parallel **Jacobian** (`ppp/ppp.v:7,9`, "on-the-fly comparison of
  parallel vs serial evaluation of Jacobian").
- **Why that matters.** `.claude/context/openmp-jacobian.md:21-27,38-46` names the parallel Jacobian
  (`jac_calc_omp`/`OMPJacBuilder`, with each thread calling `pandf` locally on its own module copies) as where missing
  `+threadprivate` races show up. It also says the serial CI build "will not catch OpenMP races".
- **What the PRD puts in its place.** §8 replaces the check with "`measure_roundoff.py`'s OpenMP row". §7.7 line 610
  defines that row as "serial against OpenMP with 1 and N threads, via the `ffun` path with
  `ppp.OMPParallelPandf1=1`", which is the RHS only.
- **The harness cannot build a Jacobian.** Its `exmain` runs with `ftol=1e50`. `nksol` evaluates `f` once and returns
  through `nkstp0` before the iteration block (`svr/nksol.m:1005-1015`), so no Jacobian is ever built.
- **Nothing else covers it.** §4 and §9 mention OpenMP equality only for the RHS. §13 lists "Jacobian value tests …
  OpenMP RHS tests in CI" as future work.
- **Result.** After the adopt PR, the CLAUDE.md hard rule ("the OpenMP check when the `pandf` tree changed") would no
  longer exercise the parallel Jacobian. A `/spec` ticket written from §8 would remove that check without anyone
  noticing. This is a loss of existing coverage, and the PRD does not record it.

*Acceptance.* The replacement for `validate` §4 keeps both comparisons. For example:
- a harness helper (`state.py`) loads a family's converged state (`input.py`, `allocate`, restore);
- it runs `exmain` with the family's normal `ftol`, so a Jacobian is built, with `OMPParallelPandf1`, `OMPParallelJac`,
  `CheckPandf1` and `CheckJac` set to 1 and `Nthreads > 1`.

Alternatively, `measure_roundoff.py`'s OpenMP row is extended to include the Jacobian comparison. Either way, §4 Out of
scope, §7.7 and §9 say that the parallel Jacobian is still checked locally.

### MINOR

**P4-m1: Stale sentences left by the round-3 revisions.**
- **Guard location.** These lines still put the guard in `build-test-wheel.yml`, which contradicts §7.6 lines 599-601
  and the directory tree (line 337: its own `reference-guard.yml`, and the test workflow keeps its triggers):
  - §8 Changed, line 698: "add … PR-tier test shards per family, and the reference guard";
  - §11 CI, line 799: "`build-test-wheel.yml` … runs the PR tier and the reference guard on every PR";
  - Phase 3, line 873.

  A ticket written from §8 would rebuild the exact problem P3-m4 fixed.
- **Step number.** §6 "Facts", line 293: "The explicit `pandf` call in step 6" should now read step 8. Step 6 is the
  time-step setup.

**P4-m2: Step 6 needs the unperturbed physical arrays, but only a packed `yl` is stored.**
- **What is stored.** §4 (lines 108-109) and §7.1 Output (line 375) store "the unperturbed converged `yl`". Step 6
  (lines 249-252) also sets `nis, ups, tes, tis, ngs, tgs, phis` to the unperturbed state.
- **The fix itself is right.** `pandf` calls `convsr_vo` at `bbb/pandf.m:589`, which calls `convsr_vo2`. That recomputes
  `niy*s`, `tiy*s` and `phiy*s` from `nis/tis/phis` on every call (`bbb/convert.m:858-930`). So setting the `*s` arrays
  after `exmain` does reach `fqydt` (`bbb/pandf_potencur.m:216-222`).
- **What is missing.** The arrays have to come from somewhere, and unpacking a `yl` depends on the normalization.
- *Acceptance:* §4 and §7.1 store the unperturbed physical arrays, for example the original `solution.h5` datasets.
  The child packs `ylodt` from them, which also settles round 3's normalization note.

**P4-m3: Guard rule details for `/spec`.**
- **Loosening is not always decidable.**
  - For `compare.py`, `store.py` and `locality.py`, and for non-monotone parameters (`δ_loc`, `W`/`P`, sketch
    `k`/seed/regions, timeouts), the guard cannot tell loosening from tightening.
  - Define the default, for example: any such change counts as loosening.
- **Override cleanup collides with prune.**
  - A refactor that prunes a removed input which has an `overrides.toml` entry (an index-like value, or an EXCLUDED
    reason) must also delete that override. That is a "removed existing override", which is a loosening and needs
    `Default results: changed`.
  - This contradicts story 10 and the allowed-prune rule.
  - Allow removing overrides whose keys are pruned in the same PR.
- **Unguarded files.**
  - Outside the guarded set: `tests/test_*.py`, `conftest.py`, `state.py`, `variants.py`, `inputs.py`,
    `check_reference_change.py` and the three test workflows.
  - An added `skip` or `xfail` on a failing variant therefore passes CI silently. A PR can also edit the guard script
    that then judges it, because `pull_request` runs the head's copy.
  - Suggested fix: put these paths under `Test criteria: changed`, make `conftest.py` fail on any skip or xfail outside
    the `nightly` marker, and run the guard script from the base ref.
- **Required check.** `reference-guard.yml` must be a required status check on `v9-develop`. Otherwise it is only
  advisory. No section says so.

**P4-m4: Details of the `input.py` normal form.**
- **The `hdf5_restore` grep trips on imports.** The assembled D_only, D_mols and slab files have
  `from uedge.hdf5 import hdf5_restore` at line 8 (`pytests/unittests/*/…/default/input.py` on `upstream/pytests`). The
  ortho template has it at line 8 too. If the trailing snippet is removed as written, the
  `test_inventory.py` grep for `hdf5_restore` still fails. Either remove the import as well, or grep for calls only.
- **d_c also needs `restart` removed.** It sets `bbb.restart = 1` at `input.py:132`. That line must go too. The grep
  catches it, but §6 names only lines 143-144.
- **Ortho is grouped with d_c by mistake.** It ends with the standard snippet (`input.py:105-108`), not an inline
  allocate + restore. Its mid-file `bbb.allocate()` at `:57`, followed by `nwallo`/`nwalli`, must stay. The wording at
  line 269 could be read as removing it.
- **The spawn fallback needs the same isolation.** It (line 286) says "with the same environment". It should also say
  that spawned children import `uedge` with `HOME` and cwd set to the empty temp directory, and `chdir` to the family
  directory only after the import. Otherwise `./.uedgerc.py` in the pytest working directory runs.

**P4-m5: Wording of the locality calibration (§7.5, lines 519-525).**
- **The second mutation must narrow the window.** "A second mutation that drops a single weak off-diagonal coupling",
  if read as a physics mutation, removes the coupling from the local and the full evaluation alike. The mismatch is
  then 0, so locality can never catch it. It has to be a range/window mutation that leaves out a weakly coupled row,
  which was the intent of P3-m3. Also say whether it joins the committed mutation set: §7.8 still counts 24.
- **"On every family" may be impossible.** §7.1 says the 8x4 windows are clipped by the domain for almost every cell.
  A range mutation can therefore be structurally invisible on some families, and no `δ_loc` fixes that. Use "on every
  family where the mutation changes the window".
- **`M` has two jobs.** It is the classification margin (§7.2, used in Phase 2) and the locality band (§7.5, chosen in
  Phase 3). Name them separately (for example `M_class` and `M_loc`), so that calibrating locality in Phase 3 cannot
  reclassify the Phase 2 references.

### Notes on the user's decisions (not PRD defects)

None. All 13 binding decisions are reflected without contradiction. Decision 13 is applied as a superset: the nightly
tier also runs on every PR that is not docs or AI-layer only.

## Status of previous findings (round 3)

| ID | Status | Evidence |
|---|---|---|
| P3-M1 guard perimeter | **Resolved** (residual details in P4-m3) | §7.6 lines 585-595 guard `tolerances.toml`, every `family.toml` (`M`, `W`/`P`, `δ_loc`, sketch parameters, timeouts, `Δt`), existing overrides and `compare.py`/`store.py`/`locality.py`. Any change needs `Test criteria: changed`, and loosening also needs `Default results: changed`. Lines 596-598 add the test-time SHA check of the `.h5` datasets against the manifest. §11 lines 804-806 add the loosened-tolerance and `.h5`-tamper test PRs. All three round-3 acceptance conditions are met. |
| P3-m1 `cfqydt` inert | **Resolved** (storage detail in P4-m2) | Step 6 (lines 249-252) sets the `*s` arrays to the unperturbed state after `exmain`. Verified that this takes effect: `pandf.m:589` → `convsr_vo` → `convsr_vo2` recomputes `niy*s`/`tiy*s`/`phiy*s` from `nis`/`tis`/`phis` on every `pandf` call (`convert.m:158-164,858-930`), and `fqydt` differences them against the live interpolants (`pandf_potencur.m:216-222`). |
| P3-m2 normal form | **Resolved** (details in P4-m4) | §6 lines 263-273 define the form (inputs only, may `allocate`, never loads a state) plus the `test_inventory.py` grep. Count re-verified with a comment-aware parser: 971 tag lines, 968 effective, 248 dynamic, **245 effective dynamic**. |
| P3-m3 locality threshold | **Resolved** (wording in P4-m5) | Per-column steps are now sub-steps 2.1-2.6 (lines 507-517). A harness-chosen `δ_loc` is calibrated in Phase 3 against mutations and stored in guarded `family.toml` (lines 519-525). |
| P3-m4 where the guard runs | **Resolved in §7.6; stale elsewhere** (P4-m1) | Lines 599-601 and 337: its own `reference-guard.yml` on `edited`, while `build-test-wheel.yml` keeps `on: [push, pull_request]` (verified `:4`) with no skip-on-edited. §8 line 698, §11 line 799 and Phase 3 line 873 still say otherwise. |
| P3-m5 forkserver residuals | **Resolved** (spawn-fallback note in P4-m4) | Lines 279-288 and 774-777: the forkserver starts with `HOME` and cwd set to an empty temp dir. Children assert `uedge` is in `sys.modules` and that there is no `.uedgerc.py`. §8 line 737 now says forkserver. Verified that `src/uedge/__init__.py:59-60` uses `path.expanduser('~')`, which follows `HOME`, and `'.'`, which is the cwd. |
| P3-m6 `validate` OpenMP check | **Partially resolved** (P4-M1) | The case-directory dependency is gone (§8 lines 714-715). But the replacement checks only the RHS and drops `OMPParallelJac`/`CheckJac` (`SKILL.md:79`). |
| P3-m7 stale sentences | **Resolved** | §6 Key patterns (lines 349-350): escalation, no automatic switch. Story 4 (lines 212-213): additions accepted without a declaration. §7.9 (lines 644-645): forkserver preload, and the child runs `input.py`. Risk 4 (line 932) is updated. New stale lines are in P4-m1. |

## What was checked and how

**Code claims (`sed -n`, `grep -n` in the worktree)**
- **Saved-state interpolants:** `bbb/pandf.m:589` (`call convsr_vo`); `bbb/convert.m:158-164` (`convsr_vo` calls
  `vo1` + `vo2`); `:858-930` (`niy*s`, `tiy*s`, `phiy*s` from `nis`/`tis`/`phis`); `bbb/pandf_potencur.m:210-225`
  (`fqydt`).
- **`ylodt` and the post-`exmain` conversion:** `bbb/odesolve.m:140-153,415-418`.
- **`add_timestep` gating:** `bbb/pandf.m:735-742`.
- **`nksol` early exit:** `svr/nksol.m:1000-1016` (one `f` evaluation, then `nkstp0` before the iteration block).
- **OpenMP checks:** `.claude/skills/validate/SKILL.md:70-93`; `.claude/context/openmp-jacobian.md:1-46`;
  `ppp/ppp.v:1-30` (`OMPParallelJac`, `CheckJac`, `CheckPandf1`).
- **Line references:** `.claude/hooks/check_context_refs.py:55` (`EXTERNAL` contains `"pytests/"`);
  `bbb/bbb.v:1295-1302,1109-1115` (`isflxvar`, `isrscalf`, `xlinc`/`xrinc`/`yinc`/`isjaccorall`).
- **`.uedgerc.py` loading:** `src/uedge/__init__.py:55-67`.
- **Workflows:** `.github/workflows/` (no `reference-guard.yml` yet, as expected); `build-test-wheel.yml:1-12`.
- **Tag recount:** a comment-aware parser over `*/*.v` (scratch script) gives 971 / 968 / 248 / 245.

**`upstream/pytests` at b535508**
- `git ls-tree` of `templates/grids`, `templates/fulltests` and all `input.py` paths (158).
- `git show` and grep of the five family `input.py` files for `restart`, `hdf5_restore`, `exmain` and `allocate`:
  - d_c: lines 132, 143-144;
  - ortho: lines 8, 57, 105-108;
  - D_only: lines 8, 58, 106-109;
  - D_mols: lines 8, 61, 151-154;
  - slab: lines 8, 163-166.
- Path note (unchanged material, not raised as a finding): the assembled files live under
  `pytests/unittests/...`, not `unittests/...` as written in the §4 table.

**Decision fidelity.** All 13 binding decisions were checked against §4, §6, §7, §11, §12 and the Appendix. There are
no contradictions.

**Template.** All 15 sections of the `create-prd` template are present. Assumptions are stated (§15).

**Not run** (as instructed): no build, no test suite, no `pandf` timing.
