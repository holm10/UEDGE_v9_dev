# PRD review: AIUE-9 "Create end-to-end test suite" (round 3)

PRD: `docs/prds/AIUE-9-create-end-to-end-test-suite.md` (932 lines, uncommitted in worktree `AIUE-9-planning`)
Repo checked: worktree `AIUE-9-planning` at `0fac655` (v9-develop). Old suite: `upstream/pytests` at `b535508`
(read with `git show`/`git ls-tree`, not checked out).
Previous rounds: `docs/reviews/AIUE-9-prd-round1.md` (REVISE, 0/7/9), `docs/reviews/AIUE-9-prd-round2.md` (REVISE, 0/1/8).
Reviewer: uedge-reviewer (PRD stage), round 3 (final before escalation), 2026-10-14.

## Verdict

**REVISE**: 0 BLOCKER, 1 MAJOR, 7 MINOR.

## Summary

The round-2 MAJOR (P2-M1) is resolved. Each child now runs the family `input.py` verbatim, and the harness owns
`allocate` and the restore. Every dynamic array gets a defined phase and a defined base value. For the default
configuration this reproduces the old suite's setup sequence exactly. Most round-2 MINORs are fixed, and I checked
those fixes against the code. One new MAJOR remains, and it is about the reference guard's perimeter. The guard only
watches the manifests. `tolerances.toml` (and the other test-time comparison parameters) decide pass/fail but sit
outside it. So a refactor that moves `yldot` can turn CI green by loosening a tolerance, with no declaration. That
defeats the suite's single purpose and Risk 7's mitigation. The fix is small. The MINORs are mostly stale sentences
that contradict the revised sections, one input (`cfqydt`) that stays inert even in the new `timestep`
configuration, and a few harness details for `/spec`.

## Findings

### MAJOR

**P3-M1: The reference guard does not cover the data that decides pass/fail at test time.**
*Location:* §7.6 "The guard", §4 Integration "Reference-change guard", §7.7 Output (`tolerances.toml`), §11 CI
criteria, Risk 7.

*Evidence.*
- **The guard reads manifests only.** It "compares the manifests of the PR base and head" (§7.6, line 543). The
  guarded items are the default/`timestep` SHAs, the locality-pattern SHAs and the SENSITIVE entries (§7.3,
  lines 441-444; §7.6, lines 548-555).
- **Tolerances are outside it.** `compare.py` reads `tolerances.toml` at test time (§7.4: `atol_eq`, `rtol_eq`; §7.5
  normalizes locality by the same quantities). Nothing in §4, §7.6, §11 or Risk 7 puts `tolerances.toml` under the
  guard. The margin `M`, the safety factor (100), the 1e-14 floor and `family.toml`'s `W`/`P` are also outside it.
- **Effect.** A refactor that shifts `yldot` by 1e-6 fails `test_default.py`. Raising `rtol` for that equation in
  `tolerances.toml` turns the PR green, with no manifest change and no `Default results: changed` line. Risk 7
  ("References only come from the CI regeneration workflow … only accepts declared changes") does not hold for this
  path.
- **Why it matters here.** §3 lists the agentic pipeline (`execute`, `implement-fix`) as a primary user. Loosening a
  tolerance to make a failing comparison pass is exactly the change the suite exists to stop. §11 ("Every tolerance
  cites its measurement") is a review-time property, not something CI enforces.
- **A second, smaller gap.** Nothing says the test run checks the `.h5` contents against the manifest SHAs. A PR that
  changes `references/<family>.h5` without a matching manifest change passes the guard, because the manifest is
  unchanged.

*Acceptance.*
1. §7.6 puts `tolerances.toml` and the comparison parameters (`M`, safety factor, floor, per-family `W`/`P`) inside the
   guard. Any loosening needs the declaration, or a separate declared keyword with a link to the new measurement.
   Tightening may be allowed without one.
2. The test run (for example `test_inventory.py`) checks that each family's `.h5` matches the SHAs in its manifest.
3. §11 adds a test PR showing that a loosened tolerance is rejected without the declaration.

### MINOR

**P3-m1: `cfqydt` stays inert in the `timestep` configuration as specified (P2-m1 residual).**
*Location:* §6 "Time-step configuration" and step 6.
- `fqydt` does not use `ylodt`. It uses the difference between the current interpolated fields and the **saved `*s`
  arrays**: `tiy1d = (tiy1 - tiy1s)/dtreal` and so on (`bbb/pandf_potencur.m:217-222`). The `*s` arrays are filled
  from `nis/tis/phis` in `convsr_vo2` (`bbb/convert.m:880-930`).
- The harness restores the *perturbed* base state into `nis/tis/phis`, and `yl` is built from that same state. So
  `tiy1 = tiy1s` and the other pairs match, which makes `fqydt = 0`. Setting `ylodt` to the unperturbed `yl` (step 6)
  does not change that.
- `cfqydt` would therefore classify INERT/MARGINAL even in the `timestep` configuration. The `fdt*xy` inputs are
  correctly covered, because `add_timestep` multiplies `yldot` by `(1-fdt*)` (`bbb/pandf.m:440-491`).
- *Acceptance:* either set the saved `*s` arrays to the unperturbed state in the `timestep` configuration (after
  `exmain`, as for `ylodt`; that matches a real time step), or drop `cfqydt` from the initial list and record it as
  uncovered.
- *Related detail for `/spec`:* storing the unperturbed state as a packed `yl` ties `ylodt` to the family's
  normalization (`n0`, `isflxvar`, `isrscalf`, …). Any override that runs a normalization-changing variant in
  `timestep` would then compare against an inconsistent `ylodt`. Storing physical arrays and packing them in the child
  avoids this.

**P3-m2: Normal form of a family `input.py` (P2-M1 residual).**
*Location:* §6 "Family `input.py`", §12 Phase 1.
- `d_c`'s `input.py` has no `templates/restore/default.py` snippet. It ends with an inline `bbb.allocate()` +
  `hdf5_restore("solution.h5")` (`templates/fulltests/nonog_d_c-fb_16x8/input.py:143-144`), after its own
  `bbb.restart = 1` (`:132`).
- Running it "verbatim, with the snippet removed" either fails (no `solution.h5`) or does a redundant restore of the
  unperturbed state.
- The epic owner's large deck is likely to be even less regular.
- *Acceptance:* define the normal form: the family `input.py` sets inputs only and never loads a state. Name the d_c
  lines to remove. Phase 1 normalizes the large deck the same way.
- Count nit: 248 tagged lines are dynamic, but three of them are the comment-embedded tags (`bbb/bbb.v:558,2073,2076`).
  That leaves **245 effective** dynamic inputs, not 248.

**P3-m3: Locality threshold sensitivity is not shown (P2-m2 residual).**
*Location:* §7.5 steps 3-5 and "Pattern with a margin band".
- Normalizing by `atol_eq + rtol_eq·|Δ_full|`, with the `yldot` tolerances (`atol_eq = rtol_eq·max|ref_eq|`, §7.4),
  is a sound noise model. But the real signal is about `del·|∂f_r/∂y_iv|·|y|`, with `del = 1e-8`
  (`bbb/bbb.v:3302`).
- Assume `σ ≈ 0.03` and a cross-platform `rtol_eq ≈ 1e-9`. A missing *weak* coupling (1 % of the diagonal) then
  normalizes to about 3. That is inside the unasserted band, so a new one would pass. Strong couplings are around
  300, so they are caught.
- *Acceptance:* Phase 3 reports, per family, the distribution of normalized mismatch for rows a deliberately
  narrowed window drops, and shows they sit well above `M`. If they do not, use a larger locality perturbation than
  `jac_calc`'s `del`; the *row set* does not depend on `del`.
- Also, steps 3-5 are numbered as top-level steps but run per column. Indent them under step 2 so the 2+2 cost
  reading is unambiguous.

**P3-m4: Where the guard runs (P2-m4 residual).**
*Location:* §4 "Reference-change guard", §7.6.
- If the `edited` type is added to `build-test-wheel.yml`'s `pull_request` trigger, every description edit re-runs
  the whole build and test matrix.
- If the jobs are conditioned to skip on `edited` instead, the newest check run for a required job reads "skipped".
  GitHub treats that as passing, so it can mask an earlier failure on the same SHA.
- *Acceptance:* the guard is its own workflow (or a required job that never shares a run with the test jobs) triggered
  on `edited`, and the test workflow keeps the default types.

**P3-m5: Forkserver residuals (P2-m5 residual).**
- **`.uedgerc.py`.** `import uedge` runs `.uedgerc.py` at import (`src/uedge/__init__.py:58-67`). That now happens in
  the forkserver's preload, not in the child after `chdir`.
  - §10 ("Workers run with `HOME` and the working directory set to the family directory") does not match a forkserver
    shared by several families.
  - State that `HOME`, the working directory and the `.uedgerc.py` check are set at forkserver start.
- **Silent preload failure.** `multiprocessing` ignores `ImportError` in forkserver preload, so a broken preload
  silently falls back to a per-child import. The harness should assert that `uedge` is in `sys.modules` in the
  forkserver.
- **§8.** "Fork is used on both; spawn is the fallback" contradicts §6. It should say forkserver.

**P3-m6: `validate`'s OpenMP check loses its case directory at retirement (P2-m6 residual).**
- `.claude/skills/validate/SKILL.md:72-79` runs the OpenMP check "in a case directory (e.g. one of the pytests cases)"
  with `exec(open("input.py").read())`, relying on that file's trailing restore.
- The new family `input.py` deliberately has no restore. Pointing the check at `tests/families/<f>/` would run it on
  an un-restored state.
- §4 Out of scope relies on this check for OpenMP equality, and the retire PR's list (§8, lines 674-679) covers only
  `validate` §3 and its description.
- *Acceptance:* the retire (or adopt) PR rewrites `validate` §4 to load a family through the harness, for example a
  `state.py` helper. The Phase 4 grep would otherwise flag `SKILL.md:73`.

**P3-m7: Stale sentences contradict the revised sections.**
Each of these would mislead a `/spec` ticket written from that paragraph.
- §6 Key patterns (line 332): "switches to sketches if it exceeds its cap" contradicts §7.3 (line 463: "The move is
  not automatic", decision 12). Risk 4 ("Sketch fallback above the per-family caps") has the same problem. *(P2-m7
  partly resolved.)*
- Story 4 (lines 210-213): "the guard accepts the change because the PR declares `Default results: changed (new
  variant)`" contradicts §7.6 and §11, which let additions through without a declaration. *(P2-m4/P2-m8 partly
  resolved.)*
- §7.9 row 1: "Parent setup (`import uedge` + `input.py`) … once", with `input.py` missing from the per-child row.
  Under the new protocol `input.py` (with its own `allocate` in three families) runs in every child. Risk 4 also
  still says "Fork after setup". Re-label the rows; Phase 1 measures them anyway.

### Notes on the user's decisions (not PRD defects)

None. Decision 13 is applied more broadly than stated (the nightly tier runs on every non-doc PR, not only Fortran
PRs). That is a superset and is consistent with the decision.

## Status of previous findings (round 2)

| ID | Status | Evidence |
|---|---|---|
| P2-M1 dynamic arrays / base value / `input.py` split | **Resolved** (residual normal-form detail in P3-m2) | §6 lines 241-262 and §7.2 lines 388-390, 406-407 now give a phase for every dynamic array (POST) and say `d` is read live at application. `input.py` is executed verbatim per child, so the mid-file `bbb.allocate()` followed by `nwallo`/`nwalli` in D_only (`input.py:58-60`), D_mols (`:61-63`) and ortho (`:57-59`) runs as authored. The old suite did the same: mid allocate, then snippet `restart=1; allocate(); hdf5_restore` (`templates/restore/default.py`), so the default configuration reproduces it exactly. The "force PRE" override remains for arrays that `allocate` reads. |
| P2-m1 timestep ordering / inert inputs | **Partially resolved** (P3-m1) | Ordering fixed. `ylodt`, `dtuse` and `dtreal` are set after `exmain`. Verified: `ylodt` is overwritten at `bbb/odesolve.m:151`, and `set_dt` (which sets `dtuse` from `dtreal`) is called in `uedriv` at `odesolve.m:299`. The `timestep` configuration, overrides and the §11 "differs from steady" criterion are present. `fdt*xy` covered (`pandf.m:440-491`). `cfqydt` is not, because `fqydt` uses the `*s` arrays, not `ylodt`. `isbcwdt` (`bbb/bbb.v:179`, `+solver`) and `dtphi` (`:2896`, untagged) are not in the inventory, so no gap there. |
| P2-m2 locality details | **Resolved** except threshold sensitivity (P3-m3) | Per-column reset to `f00` matches `oderhs.m:1141-1143`. Restore call matches `:1215-1216`. Cost is now 2 local + 2 full (§7.5 step 4, §7.9). Pattern sizes are in the §7.3 budget (< 0.5 MB). Large-family `meth*` locality is limited to special cells and costed (§7.9). Locality inputs run nightly (§7.5). A margin band is defined (`> M` stored, `≤ 1`…`M` ignored). |
| P2-m3 path filter | **Resolved** | `paths-ignore` (`docs/**`, `doc/**`, `.claude/**`, `**/*.md`) replaces the include list, so headers, `.c`, `.inc`, `src/uedge/**` and the workflow file all trigger the nightly tier. |
| P2-m4 guard triggers, scope, additions | **Mostly resolved** (P3-m4; story 4 in P3-m7) | `pull_request` only, with `edited`. Body passed through the `PR_BODY` env var. Skipped on push/schedule. Guarded SHAs for default, `timestep` and locality; diagnostics unguarded. Additions, prunes, renames and diagnostics-only allowed. `--only` includes the bounds audit and double generation. Verified that `build-test-wheel.yml:4` is `on: [push, pull_request]`. |
| P2-m5 fork / threads / import | **Resolved** (P3-m5 residuals) | Forkserver, plus `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1` and `UEDGE_BANNER=0`. Verified that `UEDGE_BANNER` gates `maybe_print_banner` before the PyPI check (`src/uedge/_banner.py:42,77,87`). |
| P2-m6 AI-layer sequencing | **Resolved** (P3-m6 residual) | Two AI-layer PRs: adopt before Phase 3, retire after the Phase 4 gate (§4 lines 163-170, §8 lines 665-679). `physics-workflow.md` moved to the adopt PR. `MANIFEST.in:3` in the Phase 4 expected matches. Every other `pytests` reference from my repo-wide grep is accounted for, except `validate/SKILL.md:73` (P3-m6). |
| P2-m7 sketch fallback / RNG | **Partially resolved** (P3-m7) | §7.3 lines 463-465: epic owner decides; slab cap 9 MB; Rademacher signs from `PCG64.random_raw`. NumPy's compatibility policy confirms that BitGenerators carry stronger stream guarantees than `Generator` methods. §6 line 332 and Risk 4 still describe automatic switching. |
| P2-m8 accuracy / pinned variables | **Resolved** (story-4 wording in P3-m7) | `bbb.restart` (`bbb/bbb.v:3083`, `+input`) is in the initial EXCLUDED list, asserted by `test_inventory.py`. `issfon` (`:3295`), `ftol` (`:1204`) and `com.iprint` (`com/com.v:709`) carry no tag, so the conditional clause is correctly empty today. The keyword goes into CLAUDE.md through the adopt PR. |

## What was checked and how

**Code claims (commands: `sed -n`, `grep -n` in the worktree)**
- **`add_timestep` and its gating:** body at `bbb/pandf.m:390-510`, `fdt*` factors and the `dtphi` relaxation;
  gating at `:728-742` (the `dtreal < 1e15` test and the `yl(neq+1)<0` flag).
- **`dtreal` users:** `pandf_potencur.m:217-222,286` (`fqydt`, `cfqydt`); `pandf_plasma_continuity.m:117-122`.
- **Saved-array interpolation:** `bbb/convert.m:880-930` (`niy0s`, `tiy1s`, `phiy1s`).
- **`ylodt` and `dtuse`:** `odesolve.m:140-153` and `:299` (`set_dt`); `oderhs.m:2366-2490` (the `dtuse` rules).
- **`jac_calc`:** `bbb/oderhs.m:1120-1220` (band widening, per-column reset, `dyl`, restore call); flag handling at
  `:1712-1730,1928-1935`.
- **`.v` declarations:** `bbb/bbb.v` lines 179, 250, 352-353, 366, 558, 644-646, 660-662, 925-926, 1204, 1311-1312,
  1427-1431, 1452-1453, 2073-2076, 2108-2111, 2887-2905, 3083, 3295-3304; `com/com.v:709`.
- **Tag recount:** 971 lines (bbb 950, com 19, aph 1, api 1). 248 dynamic, of which 3 are comment-embedded, so 245
  effective. Character/Filename: 7.
- **Python layer:** `src/uedge/_banner.py:22-95` (`UEDGE_BANNER` gating); `src/uedge/__init__.py:14,58-67,100`.
- **AI layer and repo:** `grep -rn -i pytests --exclude-dir=.git --exclude-dir=docs .` (results mapped against §8 and
  the Phase 4 expected list); `.claude/skills/validate/SKILL.md:50-80`; `.claude/context/branching.md:60-66`;
  `.github/workflows/build-test-wheel.yml:1-12`.

**`upstream/pytests` at b535508**
- `git ls-tree` of the five family sources and `templates/restore/default.py`.
- `git show` of all five family `input.py` files:
  - the mid-file `allocate` + `nwallo`/`nwalli` in D_only, D_mols and ortho;
  - the trailing restore snippet in four families;
  - d_c's inline allocate + restore at `:143-144`;
  - slab's `recycflb`/`recycfrb` set before allocate;
  - the `oldseec`/`jhswitch` try blocks (tagged `+input`, `bbb/bbb.v:352-353`).

**External:** NumPy random compatibility policy (`numpy.org/doc/stable/reference/random/compatibility.html`):
BitGenerators carry stronger stream guarantees than `Generator` methods.

**Decision fidelity:** all 13 binding decisions were checked against §4, §6, §7, §11, §12 and the Appendix. There are
no contradictions in the authoritative sections. The stale sentences in P3-m7 contradict decision 12 (automatic
sketch fallback) and §7.6, but not a decision itself.

**Template:** all 15 sections of `.claude/skills/create-prd/SKILL.md` are present and substantive. Assumptions are
stated (§15).

**Not run** (as instructed): no build, no test suite, no `pandf` timing. The locality sensitivity numbers in P3-m3
are order-of-magnitude estimates from `del`, an assumed `σ` and an assumed `rtol`. They are not measurements.
