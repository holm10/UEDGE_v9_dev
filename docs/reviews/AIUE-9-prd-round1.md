# PRD review: AIUE-9 "Create end-to-end test suite" (round 1)

PRD: `docs/prds/AIUE-9-create-end-to-end-test-suite.md`
Repo checked: worktree `AIUE-9-planning` at `0fac655` (v9-develop). Old suite: `upstream/pytests` at `b535508`.
Reviewer: uedge-reviewer (PRD stage), 2026-10-14.

## Verdict

**REVISE**: 0 BLOCKER, 7 MAJOR, 9 MINOR. There are also 2 notes on the user's own decisions, which are not PRD defects.

## Summary

The PRD follows the 13 binding decisions closely and is complete against the `create-prd` template. Almost every
factual claim about the code and the old suite holds up, so the premise is sound and there is no BLOCKER. The weak
points are in the parts that must be specified exactly before `/spec` can slice them:

- the locality check is stated as a correctness assertion ("must agree"), but local and full evaluation differ in UEDGE by design;
- the PR-tier runtime budget has no cost model, and the design as written is very likely to exceed it;
- the old suite contains documented evidence of history dependence ("fnrm changes after 1 exmain, but not after 2"), and the PRD does not mention it;
- the variant definition leaves open which value is varied, what is recorded, and what happens when a refactor removes an input;
- variant safety (crashes, hangs, out-of-bounds reads) is not handled;
- one user story presents INERT as proof that an option is dead, which is unsafe;
- the round-off measurement uses `-Og` with FPE traps, which is not the `-O0` the user decided on.

Each of these can be fixed in the PRD text.

## Findings

### MAJOR

**P1-M1 — The locality check is a correctness assertion with no protocol, and UEDGE's local and full evaluations differ by design.**
*Location:* §1 paragraph "A locality check also confirms…", §4 "Locality check", §7.5, §11 (locality success criterion).

*Problem.* §7.5 asserts that the rows changed by `pandf(xc,yc)` "match within tolerance and are the same set of rows"
as those changed by `pandf(-1,-1)`. §11 requires this for every column of every small family, and for every `meth*`
variant. The code shows the two paths are not meant to be equivalent in general.

*Evidence.*
- **The `yl(neq+1)` flag selects different physics.**
  - `jac_calc` runs with `yl(neq+1)=+1` (`bbb/oderhs.m:1716`, `:1939`).
  - `ishosor=1` integrates sources over neighbouring cells only when `yl(neq+1)<0` (`bbb/pandf_plasma_continuity.m:714`). Its `.v` line reads "full RHS only" (`bbb/bbb.v:180`, tagged `+input`).
  - `ismcnon=2/3` switches the neutral model on the sign of the flag (`bbb/pandf_plasma_continuity.m:39-62`).
  - `add_timestep` runs only when `yl(neq+1)<0` (`bbb/pandf.m:739-740`). It loops over the whole domain whenever `ParallelPandfCall=0`. So if the harness keeps its pinned `yl[neq]=-1` for the local call, the time-step term is applied a second time to the out-of-window rows that hold copies of the base `yldot`.
- **Rows outside the window are deliberately not recomputed.**
  - `jac_calc` copies `yldot00` into `wk` over the band `iv-mu…iv+ml` (`bbb/oderhs.m:1142`). Only the window that `initialize_ranges` sets is overwritten.
  - The band is widened for `ExtendedJacPhi` with `isphion*isnewpot=1` and for `isextr*` boundary conditions (`bbb/oderhs.m:1125-1138`). `initialize_ranges` does not mirror these widenings (`bbb/pandf.m:31-245`).
  - The Jacobian is only a preconditioner, so this approximation is legitimate. A full evaluation will still show couplings that the local one omits.
- **The protocol is undefined.** The PRD does not say:
  - what fills the rows outside the window;
  - which value `yl(neq+1)` takes;
  - how the state is restored between columns. `jac_calc` calls `pandf(xc,yc)` again at the restored `yl` (`bbb/oderhs.m:1216`). After the PRD's step 3, a full evaluation at the perturbed state leaves stale intermediates for the next column.
- **The slab result is not general.** The bit-identical slab result from planning is one configuration (§7.5). The large family "includes drifts and potential if the case has them" (§4).

*Acceptance.* The PRD states the locality protocol:
- the flag value for both calls (as in `jac_calc`);
- rows outside the window initialized to the base `yldot`;
- the restore step between columns.

It also turns the check into an old-vs-new comparison, in line with decision 1. Store the locality outcome per family and configuration (the set of mismatching rows and their sizes) in the reference, and assert that it is unchanged. Do not assert perfect locality. Name the known by-design exceptions. §11 must be reworded so that it can be met when legitimate non-local couplings exist.

**P1-M2 — The PR-tier runtime budget (≤ 20 min) has no cost model, and the design as written very likely exceeds it.**
*Location:* §4 Technical/Integration, §7.5, §11 Quality indicators, Risk 4, Phase 2 validation.

*Evidence.*
- **Variant sweep.** The PR tier runs about 970 variants × 5 small families ≈ 4,850 variants. Each one runs "in its own process" (§4 Technical). Each process pays for:
  - Python start-up and `import uedge`;
  - `exec(input.py)`, which includes `bbb.allocate()`. The slab family also regenerates its 32x17 grid every time (`templates/grids/slab/default.py`; `gridue` is 0 bytes on `upstream/pytests`);
  - the `exmain` set-up: geometry and reading the rate tables.
- **Locality.** The locality check runs on every column:
  - slab has neq ≈ 4–5k (34×19 cells);
  - `d_c` has about 3.6–4k;
  - each column takes 2–3 `pandf` calls;
  - it is repeated for every `meth*` variant: `methu/e/i/p` each have 3 alternatives, `methg` 5 and `methn` 1, which is about 18 configurations.
- **Large-family locality.** The PR tier also includes the large family's sampled locality check: about 600 cells × numvar × 2–3 calls on a 100x50 grid, also over the `meth*` variants. Near cuts and the core (`isjaccorall`, `xccuts`, `bbb/pandf.m:53-55,114-155`), a "local" evaluation spans the full ix range, so it costs about as much as a full one.
- **Lost parallelism.** The PRD removes the 5-way CI matrix (§8 "Changed") and puts everything into one `-n auto` job on a 4-vCPU runner.
- **Contradictory mitigation.** Risk 4's mitigation ("workers reused across variants where state can be reset safely") contradicts the per-process isolation in §4, and it depends on the history independence questioned in P1-M3.

*Acceptance.* The PRD gives a cost model per tier, from a short measurement (per-variant process cost and the cost of one `pandf` call per family), or at least an order-of-magnitude estimate with its assumptions. It names a design that fits the budget without breaking decision 13. Examples:
- fork-after-setup (one import and set-up per family, then `fork()` per variant, which keeps isolation);
- a CI matrix sharded per family;
- coloured or simultaneous column perturbations for the locality check;
- moving the large family's locality check to the nightly / pandf-PR tier.

The runtime check moves to, or is repeated in, Phase 3, once locality is in the PR tier.

**P1-M3 — Documented history dependence in the old suite is not addressed, and determinism evidence comes from one family.**
*Location:* §6 "Facts the design relies on", §7.7, §11 Determinism, Risk 1, Risk 4.

*Evidence.*
- Both the old test template and the old generator say: "For some reason fnrm still changes after 1 exmain, but not after 2. Thus, assert a first exmain here" (`upstream/pytests:templates/tests/uedge_tst_template.py:38`, `MakeTests.py:31`).
- This is direct evidence of state carried between calls. It is probably the "apparent randomness" behind decision 9.
- The PRD's protocol is exactly one `exmain` followed by one `pandf` (§6 steps 3–4).
- The PRD's history-independence evidence (yA, yB, yA) covers only the slab case.
- The locality check (many calls at different `yl` in one process) and the Risk 4 worker reuse both assume history independence.
- The §11 determinism criterion compares *separate processes*. It cannot detect within-process history dependence.

*Acceptance.*
- The PRD cites the old-suite comment.
- Phase 1 has a deliverable that characterizes history dependence on **every** family: `exmain`×1 against ×2, A-B-A, and the number of `pandf` calls before the observed one.
- The harness protocol fixes the warm-up sequence explicitly.
- Any dependence found is filed like same-build nondeterminism.
- Worker reuse and the locality protocol are allowed only on families that pass this check.

**P1-M4 — The variant definition is underspecified: base value, recorded value, inventory changes, and timing.**
*Location:* §7.2, §7.3 manifest contents, §11 Inventory completeness, Risk 7.

*Evidence and gaps.*
1. **Which `d` is varied?** It is not stated whether `d` is the `.v` default or the family's value after `input.py`. `inputs.py` parses the `.v` "default" (§6 tree).
   - The families override many switches. For example, `isphion` has `.v` default 0 (`bbb/bbb.v:226`), but `d_only`, `d_mols` and `ortho` set it to 1.
   - With the `.v` default, `1−d` reproduces the family value. The variant is then a no-op, it is classified INERT, and its "stays inert" assertion passes forever.
2. **The applied value is not recorded.** The manifest holds class, reason, SHA, norms and provenance (§7.3), but not the value applied.
   - If a PR changes a `.v` default or a value rule, the test applies a different value from the one the reference used.
3. **Inventory changes are not handled.** The motivating use case is "dead options removed" (§1). Removing or renaming a tagged variable makes the inventory and the manifest disagree, so the test fails (§11).
   - Risk 7 says "Refactor PRs must show zero reference changes".
   - The PRD defines no procedure for pruning a manifest entry in a refactor PR. Removing an INERT entry is harmless. Removing a SENSITIVE one is a behaviour change.
4. **Keys and timing.**
   - Variables are not keyed by package. Some names exist in more than one package; the old template already handles `com.iprint`/`bbb.iprint`.
   - 247 tagged inputs are dynamic arrays (`_real`/`_integer`). Some are "input after alloc" (`bbb/bbb.v:834-835`). The PRD does not say whether a variant is applied before or after `allocate`/restore.

*Acceptance.* §7.2 and §7.3 state all of the following:
- the base value is the family's value after `input.py`;
- the manifest records the exact applied value, so the test replays it rather than recomputing it from the rules;
- a defined prune/rename path for refactor PRs, with how a reviewer tells it apart from a reference change;
- package-qualified keys;
- the order of application relative to `allocate` and the state restore.

**P1-M5 — Variant safety: crashes, hangs and silent out-of-bounds access are not classified.**
*Location:* §7.2 classes, Risk 3.

*Evidence.*
- INVALID covers "setup raises, `neq` changes, or `yldot` non-finite" (§7.2). It does not cover a segfault, a timeout or a hang.
- OFAT rules applied to index-like integers can index past an array. For example, `jxsori(10)` and `jxsoro(10)` with default 1 become 2, a mesh-region index, on single-null families (`bbb/bbb.v:644,646`). Other examples are `ixfixnc` and `ix_sjcsor…iy_ejcsor` (`bbb/bbb.v:521,1840-1843`).
- The CI build has no bounds checking. An out-of-bounds read can produce a finite, apparently SENSITIVE `yldot` that depends on the build or platform. That value would then be committed as a reference and become a flaky test.
- `setup.py` already has `--checkbounds` (`setup.py:741-745`).

*Acceptance.*
- The classification run covers process crash and timeout, as INVALID with a reason.
- Classification, or a one-off audit of the inventory, runs on a `--checkbounds` build. A variant that triggers a bounds error is INVALID.
- Each SENSITIVE variant is generated twice before it is committed. This is partly covered by §11 Determinism; say that it applies at generation time.
- Every variant gets a per-variant timeout.

**P1-M6 — User story 2 presents INERT as evidence that an option can be deleted safely.**
*Location:* §5 story 2, §13 "inert-input report to feed the code-reduction epics".

*Evidence.* INERT means "`yldot` unchanged at one OFAT value on six base configurations".
- An input that matters only when another switch is on is INERT in every family. This is the interaction case that decision 2 explicitly leaves untested.
- The story says "so that I can delete them safely, knowing the suite will notice if I removed a live one". The suite cannot notice that, because by construction it never exercised the live path.
- Deleting options is the main refactor this epic exists to protect (§1). The story invites exactly the unsafe change.

*Acceptance.* Story 2 and §13 say that INERT is a *candidate* signal only. Deleting an option also needs code inspection: grep for every use and the coverage report from Phase 4. What the suite guarantees is the reverse direction: SENSITIVE becoming INERT is caught.

**P1-M7 — The round-off measurement uses `--debug` (`-Og` plus FPE traps), not the `-O0` the user decided on, and the traps may stop it running.**
*Location:* §4 Technical ("`-Og` against `-O3`"), §7.7, decision 9 in the Appendix.

*Evidence.*
- Decision 9 says the "`-O0`/`-O3` round-off spread".
- `--debug` adds `-Og`, `-fcheck=all`, `-ffpe-trap=invalid,overflow,underflow` and `-finit-real=snan` (`setup.py:84-91`).
- Trapping **underflow** aborts on any exponential rate or coefficient that underflows. That is common in edge-plasma rate evaluation. In that case `--debug` yields a crash instead of a spread.
- `setup.py` has no `-O0` path without traps. The flags are only `FARGSOPT=['-O3']` or `FARGSDEBUG` (`setup.py:93,747-751`).

*Acceptance.* The PRD either:
- adds an `-O0`, no-trap measurement build as a results-neutral, opt-in build-flag ticket, like the coverage flag in §8; or
- justifies `-Og` explicitly and gets the user to agree, because decision 9 names `-O0`.

It also states what happens if the trapping build aborts.

### MINOR

**P1-m1 — Inventory facts are slightly off.**
- There are 971 tag lines (bbb 842 + 108, com 19, aph 1, api 1), not 972.
- Three of the 971 are inside comments, so a naive parser would pick them up: `bbb/bbb.v:558` (`istepfcix`), `:2073` (`bctype`) and `:2076` (`capx`). The parser should ignore tags that come after `#`.
- There are 7 character or `Filename` inputs, not 6: `geometry`, `mcfilename`, `coronalimpfname`, `svrpkg`, `petscoptfile`, `petscopts` and `GridFileName`.
- `methn` allows only 22/33 (`bbb/bbb.v:35`). The §7.2 `meth*` row implies 22/33/44/55 for all of them.

**P1-m2 — The family table and the §7.1 rationale are inaccurate.**
- `d_only`, `d_mols` and `ortho` all run with `isphion=1`. See the assembled `input.py` files on `upstream/pytests`, and `orthogonal_unittest/input.py:69`.
- The slab family has an ExB drift (`cfyef=0.6`) and is **32x17**: `nxcore=8` plus `nxleg=24`, and `nycore=1` plus `nysol=16`.
- So slab already exercises unclipped interior windows. The claim "the unclipped path of `initialize_ranges` goes untested" applies only to the 8x4 grids. §13's "a large case with drifts if `large_dd2c` has none" overlooks slab.
- Slab is missing from the size table in §7.3. With neq ≈ 4–5k it is larger than `d_c`. Adding it probably pushes the ≤ 25 MB / ≤ 6 MB-per-family estimates past their limits. Add the row and re-check the budget.

**P1-m3 — The nightly trigger's path filter is too narrow.**
§4 and §11 list `bbb/pandf*`, `convert.m`, `oderhs.m` and `*.v`. Many other files change `yldot`:
- `aph/*.m` and `api/*.m` (rates, impurities, sputtering);
- `bbb/odesetup.m`, `geometry.m`, `turbulence.m` and `ext_neutrals.m`;
- `com/*.m` and `ppp/*.F90`;
- `setup.py` and `Makefile.Forthon` (compiler flags);
- `tests/**`.

Use all Fortran sources plus the build files.

**P1-m4 — Retirement sequencing and the Phase 4 grep.**
- Phase 3 switches CI to `tests/`. That removes the old suite from CI before the Phase 4 retirement gate that §4 says must come first.
- This is harmless in practice, because CI already fails to check out the old suite on non-master branches (verified: `git ls-remote` shows only `pytests` and `stale/pytests` upstream). Say so explicitly, or keep the old checkout until Phase 4.
- The Phase 4 grep `uedge-pytests\|pytests-develop` misses these references:
  - "`pytests` branch" in `.claude/skills/implement-fix/SKILL.md:58,74`, `execute/SKILL.md:57` and `validate/SKILL.md:3,53`;
  - "upstream/pytests" in `testing.md`.
- The same grep will match `docs/prds/` and `docs/reviews/`. Widen the pattern and list the expected matches.

**P1-m5 — Risk 7's mitigation depends on files outside the AI-layer scope.**
- "The `code-review` checklist flags manifest diffs in refactor PRs" (Risk 7), but `.claude/skills/code-review/SKILL.md` is not in the §8 AI-layer list.
- Story 4 (adding a variant for a new switch) should also reach `.claude/agents/uedge-implementer.md` (process, on the AI-layer PR) and `.claude/context/physics-workflow.md` (a code-fact).
- Consider a mechanical CI guard as well, for example: fail when `tests/references/**` changes unless the PR declares "Default results: changed".

**P1-m6 — Classification thresholds and reference platform are not defined.**
- INERT is not defined as bitwise equality on the generating build. A variant with an effect near the tolerance can flip between INERT and SENSITIVE across platforms, or after a refactor that reorders operations. Define the classes with a margin.
- Risk 1 says "generate references on the CI platform", but §7.6 builds in a local worktree. State where references are produced.
- Pin the runner image and the gfortran version. `ubuntu-latest` rolls over and moves `-O3` round-off.
- §7.7 measures spread only for the default. Say whether variants inherit those tolerances.

**P1-m7 — Mutation set.**
- §11 says "at least 12", but the listed set is 7 equations × 3 mutations + 3 = 24.
- Commit the mutation patches and a runner (for example `tests/mutations/`) so that the criterion can be re-checked in each phase, rather than living on a throwaway branch.

**P1-m8 — Harness details that `/spec` will need.**
- `hdf5_restore` also restores `tipers` (`src/uedge/hdf5.py:30-35`); §4 lists only seven arrays.
- The values to which `ylodt` and `dtuse` are pinned are not given.
- Set `OMP_NUM_THREADS=1` per worker on OpenMP builds when running under xdist.
- `bbb.pandf` from Python runs the serial path even on an OpenMP build. `OMPPandf1Rhs` is reached only through `PandfRHS_interface`/`ffun` (`bbb/pandf.m:7-28`). State that the suite does not exercise the OpenMP RHS except through `measure_roundoff.py`.
- The Phase 1 convergence check needs the scaled `fnrm` (`issfon=1`), not the harness setting `issfon=0`.
- Say whether intermediates are pass/fail assertions or only diagnostics. If they are assertions, a refactor that legitimately drops or reshapes an intermediate fails.
- Add `*.gcno`, `*.gcda` and `*.gcov` to `.gitignore`.
- The `.F`→`.m` line map is non-trivial because of the `MoveDecs` reordering (`setup.py:217`).

**P1-m9 — The MVP goal overclaims.**
"CI detects any accidental change to `yldot`" (§1, §11). OFAT cannot see changes that are visible only in untested configurations or combinations. Reword it to "any change visible in the tested configurations".

### Notes on the user's decisions (not PRD defects)

- **Decision 8 (variants = all `+input`/`+maybeinput` tags).** The tags are documentation, not a contract.
  - Some switches change raw `yldot` but are untagged: `isflxvar` and `isrscalf` (`bbb/bbb.v:1298,1301`; `rscalf` is applied at `bbb/pandf.m:724`).
  - `xlinc`, `xrinc`, `yinc` and `isjaccorall` (`bbb/bbb.v:1111-1114`) set the locality windows.
  - None of these will be swept.
  - The user may want `overrides.toml` to be able to *add* untagged variables. That is a superset of decision 8, not a change to it.
- **Decision 12 (one binary reference file per family).** A tracked HDF5 file does not delta-compress well. Every regeneration adds a whole new blob, up to the family's size, to git history. The ≤ 25 MB budget measures the working tree (`du -sh tests`), not history growth. Over a long code-reduction epic, the user may want a history budget, or an earlier LFS trigger.

## Status of previous findings

Not applicable (round 1).

## What was checked and how

**Claims verified as correct**
- `pandf` is Python-callable (`bbb/bbb.v:3377`). v9 has no `pandf1` routine (grep in `bbb/` and `ppp/`).
- `nksol` evaluates `f` once and stops at `nkstp0` when `fmax ≤ 0.01·ftol` (`svr/nksol.m:1005-1015,1364-1399`).
- `uedriv` calls `convsr_vo1/vo2/aux` after the solver (`bbb/odesolve.m:416-418`). These convert variables; they do not compute the fluxes. The PRD's explicit `pandf` call covers that.
- `issfon=0` sets `sfscal=1` (`bbb/odesolve.m:289-296`).
- `yl(neq+1)` and `yl(neq+2)` are control flags (`bbb/oderhs.m:1716,1726,1931`; `bbb/odesetup.m:876-880`).
- `add_timestep` depends on `dtuse` and `ylodt` (`bbb/pandf.m:390-510`).
- `xlinc/xrinc/yinc` = 2/1/2 at `bbb/bbb.v:1111-1113`.
- `xerrab` calls `kaboom` under Forthon (`com/error.f`).
- `jac_calc` is at `bbb/oderhs.m:1012` to about 1240. `jacobian_store_*` and `jacobian_reset` are in `bbb/pandf_jacobian.m`.
- `initialize_ranges` is at `bbb/pandf.m:31` and `calc_rhs` at `:251`.
- The `Rhsides` and `Comflo` groups exist (`bbb/bbb.v:2250,1913`).
- The `.uedgerc.py` logic is at `src/uedge/__init__.py:59-67`.
- `rates/` holds only the CRUMPET files.
- Packaging lists `uedge` and `uedge.rates` explicitly (`pyproject.toml`), so `tests/` would not be packaged. `.gitignore` does not ignore any planned test file (`git check-ignore`).
- CI: the `testbranch` logic is at `build-test-wheel.yml:55-65`, the `LLNL/UEDGE` checkout at `:88-92`, and the 5-way matrix at `:51`. `git ls-remote https://github.com/LLNL/UEDGE.git` shows no `pytests-develop`.
- `origin/HEAD` is `v9-develop`, so a scheduled workflow runs on the right branch.
- Tag counts: `grep -c` per `.v` file gives 971. Comment-embedded tags and the character types were inspected by hand.

**`upstream/pytests` at b535508**
- `git ls-tree -r -l` gives 1,022 blobs, 129.15 MB in total.
- There are 163 `solution.h5` files, 114.46 MB in total (88.6 %), all with distinct blob hashes.
- The template `solution.h5` files are 31,880 to 168,304 bytes.
- `perturb_solution` is applied in `write_data` to the copy in the case directory (`uedge_tst_template.py:203-204`). `MakeTests.make_unittests` copies the template files there first, so the templates stay unperturbed.
- `gridue` headers: nonog, ortho and carbon are `8 4 2 6 1`; `d_c` is `16 8 4 12 4`. The slab grid is generated: `templates/grids/slab/gridue` is 0 bytes and `default.py` gives a 32x17 grid.
- Family inputs were read: `D_only`, `D_mols` and `ortho` have `isphion=1`; `d_c` has `isimpon=6` with `C_rates.strahl`; slab has `cfyef=0.6`.

**Locality and Jacobian semantics** (P1-M1)
- `bbb/oderhs.m:1012-1240` (band, `wk` initialization, re-call at restore).
- `bbb/pandf.m:31-245` (windows, `xccuts`, `xcturb`, `isjaccorall`, point-wise source ranges), and `:735-742` (`add_timestep` gating).
- `bbb/pandf_plasma_continuity.m:39-62,704-740` (`ismcnon` and `ishosor` gated by the flag).
- `ppp/parallel.F90` and `bbb/pandf.m:7-28` (the OpenMP RHS path).

**Build flags** (P1-M5, P1-M7): `setup.py:35-110,730-751`.

**AI-layer scope**
- I grepped the whole repo for `pytests`, `uedge-pytests` and `pytests-develop`. Matches are in `CLAUDE.md`, `.claude/context/{testing,branching}.md`, the skills `validate`, `init-project`, `execute` and `implement-fix`, `.claude/hooks/check_context_refs.py:55` (the `EXTERNAL` list, which is harmless), `MANIFEST` (legacy) and `doc/docs/stale-branches-log.md`.
- `branching.md` and `change_kind.py`: `.github/workflows/build-test-wheel.yml` and `tests/` are product. The lock file `.claude/context/refs.lock.json` is covered by the code-facts trailer.

**Citations**: arXiv:1602.06747 resolves to Dudson et al., "Verification of BOUT++ by the Method of Manufactured Solutions". I did not fetch Kuhn et al. (IEEE TSE 30(6), 2004) or Baker et al. (GMD 8, 2829, 2015). Neither supports a key requirement.

**Not verified (each needs a build and runs; none was done, as instructed)**
- That slab gives bit-identical results under repeated and A-B-A `pandf` calls.
- That the template states are converged.
- Per-variant and per-`pandf` cost.
- That locality holds on the default configurations.

P1-M2 and P1-M3 ask the PRD to turn these into Phase-1 measurements rather than assumptions.
