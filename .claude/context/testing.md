# Testing — what actually exists

**The regression suite is not in this repository.** It lives on a `pytests` branch. **v9 work uses `origin/pytests`**
(the holm10 fork): it holds v9's own references, regenerated for the v9 physics and listed with their reason in
`V9_REFERENCE_CHANGES.md` on that branch, for a later merge into LLNL's `upstream/pytests`. CI still checks out
LLNL's branch after building (`.github/workflows/build-test-wheel.yml:56-96`, quirks below).
There are no unit tests of individual Fortran routines and no coverage measurement.

The repository holds two test trees. `tests/deterministic_omp/` is the OpenMP Jacobian reproducer of AIUE-8 (deck, trimmed
data, `tests/deterministic_omp/tools/fingerprint.py`; see `tests/deterministic_omp/README.md`), with the bitwise
harness in `tests/deterministic_omp/harness/` (OpenMP vs serial: `cli.py`, with the test flow `cli.py flow`, see
`openmp-jacobian.md`; serial old vs new: `serial_check.py`). No CI job runs them yet.

`tests/yldot/` is the yldot suite (epic AIUE-9). Run it as `pytest tests/yldot` (never `pytest tests/`). One bullet
per component; a ticket that adds a component adds a bullet, one that changes a component edits only its bullet:

- **Families** `tests/yldot/families/<f>/`: `input.py` in normal form (it never loads a state), the grid,
  `reference_state.h5`, a seeded perturbed `base_state.h5` and `family.toml` (provenance, convergence norms, σ, seed,
  floors, `[evaluation]` W/P/timeout/Δt, owner-confirmed `[regions]`); the rate files once in `data/`. A measured
  family (AIUE-86) has W = P = 1, `child_reuse = false` (owner: one fresh child per evaluation; d_mols' `input.py`
  cannot run twice in one process) and a `[history]` table; an unmeasured one keeps the 2/2 placeholders.
  Both states are round-trip fixed points: re-saved after one `exmain`, so a further `exmain` changes no saved entry
  (AIUE-140: `convert` and `convsr_vo1` do not round-trip exactly, and `gridseq` re-saves the result).
  The five small families keep all their files in git; the three owner families (`large_dd2c`, `dnull_imp2`,
  `imp7`, AIUE-91) keep only `input.py` and `family.toml` there: their grid, `inputs.h5`, states and `sigma.h5` are
  release assets of the release their manifest names (`yldot-data-v6` since AIUE-92; owner, 2026-10-22, D6),
  gitignored, with their SHA-256s only in `references/<f>.manifest.json` (owner, 2026-10-21); a manifest naming
  release assets under `families/<f>/` is what makes an owner family (`manifest.owner_family`). `conftest.py` fetches every manifest's release assets at the start of the session
  (`fetch_data.fetch`: download if absent, SHA-256 check, link; decision 23, owner 2026-10-22, AIUE-156); nothing
  under `tests/yldot/` skips. If the fetch is impossible or `--yldot-no-fetch` is given, a test parametrised over a
  family with absent `families/<f>/` assets fails at setup naming the cause, except those marked `toml_only`;
  different files fail (`test_smoke.py::test_external_files`).
  Every family holds `sigma.h5`, the measured round-off spread σ_i per configuration (see Tolerances). The
  reference files `references/<f>.h5` are release assets of the release their manifest names, gitignored, named by
  `references/<f>.manifest.json`; `fetch_data.py` fetches them. The small families' hold the defaults and the
  SENSITIVE variants and their manifests classify every variant (`yldot-data-v5` since AIUE-159; AIUE-88, AIUE-94);
  the owner families' (sketch stores) hold the defaults only (`yldot-data-v6`, AIUE-92; their sweep is AIUE-99).
- **Runner** `tests/yldot/harness/process.py` (package `yldot.harness`): every evaluation in an isolated child
  (forkserver preloading `uedge`, or spawn; HOME/cwd in an empty directory; timeouts; results
  `ok`/`error`/`crash`/`timeout`, `FamilyError` for a family defect). Importing the package pins `OMP_NUM_THREADS=1`
  for the process; an OpenMP run imports `uedge` first (`uedge-gotchas.md` → Test tooling, AIUE-147).
- **Protocol** `tests/yldot/harness/state.py`: PRD §6, the `steady` and `timestep` configurations returning `yldot` and
  `yldot_J`, and the `intake` configuration (`issfon=1` at `reference_state.h5`, no variant) returning `yldot` and
  `sfscal`; every configuration also returns `idx*`, `igyl`, the `is<eq>onxy` masks and the grid indices.
- **Comparator** `tests/yldot/harness/compare.py`: maps every row to (equation, species, ix, iy, region) from those
  arrays only, checked as a bijection (`IndexTruthError`). Regions follow one of three rules, chosen by the
  `[regions]` source keys and checked against the live grid: single null (ixpt1, ixpt2, iysptrx), slab half mesh
  (nxcore, nxleg, nycore), or double null (`nxpt = 2`, upper X-point primary: ixlb, ixrb, ixpt1, ixpt2, iysptrx1,
  iysptrx2 per mesh half; guard also at the cut, ix = ixrb(1)+1 and ixlb(2); regions pf_upper, pf_lower,
  sol_between and four legs; owner, 2026-10-21, AIUE-91). The species in a label is Fortran's 1-based `ifld`/`igsp`.
  Then the PRD §7.4 per-entry tolerance (σ = 0 floors,
  `ToleranceEscalation`), the full-vector comparator and the first differing diagnostic in `pandf` order. A
  `Store.check` report finds that diagnostic array-scaled: max|a-b| over the array's max |value| above
  `DIAG_SCALED_RTOL = 1e-8`. The entry-relative measure always fires on round-off between macOS runs and the
  Linux-built references; the scaled one stays below 3.5e-10 unmutated (owner, 2026-10-22, AIUE-89), except
  dnull_imp2 on macOS `-O3`: `resmo` at its half-1 plate face (36,34,2), an algebraic row, differs by 1.9e-6 (FMA, a
  near-cancellation) and the `resei`/`reseg` NaN cells at ix = 37 differ by build, so its hint names `resmo` (open,
  AIUE-176). For a sketch store `Store.diagnostic_pair` cuts the new run's diagnostics to the stored `res*` names.
- **Variants** (PRD §7.2): `tests/yldot/harness/inputs.py` is the input inventory, read with Forthon's own `.v` parser
  (968 `+input`/`+maybeinput` variables; a line grep overcounts); `tests/yldot/harness/variants.py` holds the value
  rules, `plan()` and `apply()` (in the child: `d` read live, the applied value recorded exactly and replayable
  through `Runner.evaluate(..., variant=, replay=)`); `tests/yldot/overrides.toml` holds the additions, exclusions,
  explicit values, bounds, phase and configuration, each with a reason. Switches that pick the geometry, the topology
  or the species model (`isudsym`, `islimon`, `isfixlb`, `isnonog`, `mhdgeo`, `gengrid`, `ishymol`) are EXCLUDED as
  family-level and are covered only by families of their own (owner, 2026-10-23, AIUE-159).
- **Store** (PRD §7.3): `tests/yldot/harness/store.py` writes and reads one HDF5 reference file per family
  (`create`, `open_store`): `FullVectorStore` (full default, variants as the rows that differ bitwise) or
  `SketchStore` (full default, per (equation, species, region) block k = 8 projections onto Rademacher signs from
  `PCG64.random_raw`, summed with `math.fsum`; `sketch_compare` with c = 6.5), both with the sparse Jacobian-flag
  difference; files written with `track_times=False` so the bytes are reproducible, in the HDF5 1.10 format
  (`LIBVER`, superblock version 3: smaller group headers keep the variant groups within the caps; owner,
  2026-10-22, AIUE-94); `Writer.copy_variant` copies a stored variant verbatim. `tests/yldot/harness/manifest.py`
  is the schema of `references/<f>.manifest.json`, the only record of the external files' SHA-256s (owner,
  2026-10-21); `dumps` writes it indented and sorted, each encoded value's `data` list on one line (owner,
  2026-10-22, AIUE-94). `open_store` checks the file SHA-256, the dataset set, the blocks and that the manifest's
  `guarded`, `unguarded` and variant SHA-256s and its variant set follow from the datasets; every read recomputes
  the dataset's SHA-256 (`StoreIntegrityError`). A family with `[locality]` also stores
  `/steady/locality/{delta, column, row, mismatch, dfull}` (the entries with score > 1), guarded as `locality/steady`
  and derived from the datasets like the defaults (AIUE-100). A sketch store also stores, per configuration,
  `/<config>/default/sketch_threshold/{block, cell_ix, cell_iy, cell_m, cell_block}` (`store.sketch_thresholds` of
  the default's tol_i: per block δ_b = c·sqrt(Σtol²), the smallest detectable single-entry change; per cell the
  smallest multiple of its tolerances; PRD §7.11 d), guarded as `<config>/sketch_threshold` (AIUE-92). Single-entry
  ratios run far above c·sqrt(N) in the owner families; the owner set R_max = 2·c·sqrt(N_block) with a
  tolerance-weighted sketch as the remedy (AIUE-174, before AIUE-99).
- **Locality** (PRD §7.5; AIUE-100) `tests/yldot/harness/locality.py`: `jac_calc`'s protocol (`bbb/oderhs.m:1095-1226`)
  in the child after step 8b (`Runner.evaluate(family, locality=delta)`, steady, no variant): flag +1, `f00` (must
  equal `yldot_J` bitwise), then per column reset to `f00`, perturb by `delta·(|y|+dylconst/suscal)`, local `pandf`,
  full evaluation, restore, local again, full again (must equal `f00`: no stale column). Score per entry
  `|Δ_full−Δ_local| / (tol_r + rtol_eq·|Δ_full|)`; the pattern P is the stored entries above `M_loc`, (1, M_loc] is the
  unasserted band (owner, 2026-10-22, D3). `family.toml` `[locality]`: `delta_loc = 1e-6`, `m_loc = 100` (the only
  grid δ with no stored entry within 3× of M_loc), the calibration record and the causes. The isnonog = 1 families
  (d_only, d_mols, d_c) have a by-design default pattern, all in the band at 1e-6: the neutral-conductivity
  4-point average in `feixy` (`bbb/pandf_plasma_energy.m:458-459,476-477`) reaches ix−1, one cell beyond `xrinc`
  (owner, D2); ortho and slab_phi are bit-identical on every column. Every column of the five takes about 12 s.
- **Mutations** (PRD §7.8, decision 25) `tests/yldot/mutations/*.patch`: 27 patches (AIUE-89, AIUE-90), a sign
  flip, a factor 2 and a dropped term per equation, the X-point off-by-one, a wrong `cf*` multiplier, two range and
  two flag-gating mutations. A `Key: value` header (`Mutation`, `Kind`, `Equation`, `Fault`, `Check`, `Configs`,
  `Blocks` per family, optional `Cells`, `Intermediate`, `Families` with the inner-loop family first, optional
  `Pending`, `Source`, `Description`; a line starting with a space continues the previous key's value, e.g. one
  `Blocks` line per family as `<family>: primary <blocks>; coupled <blocks>`; the keys are documented in
  `run_mutations.py`), a blank line, then a single-line `git diff`; `git apply` skips the header. Applied only in a
  scratch worktree, never to a source on a branch. One is `Pending` (`ishosor`: AIUE-96) and runs as a negative
  control (owner, 2026-10-22, AIUE-90); the gas-energy ones fire in large_dd2c's `tg[2]` since AIUE-92, which added
  the owner families to the headers (predicted before the run; appended in ascending `neq`, dnull_imp2, large_dd2c,
  imp7). The two range mutations
  (AIUE-100) are `initialize_ranges`' `i5` bound (`bbb/pandf.m:73`) and the point-wise `vsoree` copy
  (`bbb/pandf_plasma_energy.m:646`, a weak `te` self-coupling; owner, D1, after the `j5p` site proved window padding).
- **Tools** `tests/yldot/tools/`: `make_base_state.py` (`check`, which also reports `fixed_point`; `make`, which
  re-saves both states after one `exmain` and refuses one that is not a fixed point); `intake_check.py` (per-row
  scaled residuals at `reference_state.h5`, tables for the owner, no automatic flag); `measure_history.py` (`run`:
  W and P from exmain/pandf repeats in fresh processes, the -1 → +1 → -1 flag sequence, steady +1 vs -1 with the
  `ishosor = 0` counterfactual, a reuse sequence in one process, child costs and the sweep estimate, as a TOML
  fragment; `check`: family.toml's W, P against W+1, P+1 and the flag rules; exit 4 = defect, 3 = owner);
  `fetch_data.py` (plain HTTPS download of a manifest's `yldot-data-v<N>` assets, the release being public, with
  `gh release download` as the fallback, into the gitignored `.data/<tag>/`,
  refusing any SHA-256 mismatch, then a relative symlink at each manifest path; `--check` verifies only);
  `release_data.py` (the release command: checks the files, the tag number (no remote git tag either) and the
  target, prints `gh release create`; publishes only with `--publish`, which the owner runs or approves);
  `measure_roundoff.py` (`collect`, run with each build's own python or in the Linux image: per family and
  configuration two fresh processes, pickled `yldot`/`yldot_J` and index arrays with the build record; `--omp N` adds
  the `ffun` RHS with the `ppp` OpenMP flags set in the `post` hook; `analyze`: the pairs `same_build:<label>`,
  `o0_vs_o3`, `mac_vs_linux` (serial, they feed σ and rtol), `debug_vs_o3` and the OpenMP rows (report only), the
  floor report, the AIUE-81 re-check; `--write` writes the files below; exit 4 = a nonzero same-build spread, 3 = owner);
  `make_references.py` (`generate --from-commit SHA`: builds SHA `--serial` and writes each family's steady and
  `timestep` defaults, Jacobian-flag difference, diagnostics and σ_i with the manifest's provenance, and for a family
  with `[locality]` the steady locality pattern (AIUE-100); `--platform
  linux` (default) in the pinned image through `linux/generate.sh`, the only release-grade path, `--platform host` a
  temporary worktree and venv, built with `PWD` set to it (for commits before AIUE-163), a preview with `release:
  null` (owner, 2026-10-22, AIUE-88); default families: the small ones
  (with `sigma.h5`, not owner families); an owner family only when named and with `--defaults-only`, its
  `families/<f>/` assets checked against its manifest and carried into the new one with its `sigma.h5` (AIUE-92);
  a sketch store also gets the sketch thresholds; refuses a `tests/yldot` that differs from SHA (references/
  excepted; also an ignored file in the families' directories or `data/` other than those owner assets), a
  `sigma.h5` that differs from `tolerances.toml`, a family whose manifest names another family's release assets and
  a preview `--write` over a released manifest; `--write` installs the files and manifests and opens each with
  `open_store`). It also sweeps every variant of `variants.plan()` in a fresh child each and
  classifies it (PRD §7.2, `M_CLS = 100` × the default's `tol_i`, for `yldot` and `yldot_J`): SENSITIVE (evaluated
  twice, stored only if both agree bit for bit, else INVALID "nondeterministic"), INERT (bitwise equal), MARGINAL,
  INVALID (error, crash, timeout, `neq` change, an equation layout change at the same `neq`, non-finite; owner,
  2026-10-22, AIUE-94), EXCLUDED (as planned, or the application changes nothing
  in the family: value equals d, no valid index, unallocated; owner, 2026-10-22, AIUE-94). Results that fit no class
  and a file over its PRD §7.3 cap (`CAPS_MB`) are findings: exit 3, nothing written. `--defaults-only` (the AIUE-88
  run), `--only VAR…` (the rest copied verbatim from the installed reference, whose defaults must be reproduced bit
  for bit) and `--full` (dense vectors for localization). Per family it prints the summary line (PRD §5 story 3, with
  marginal) and the cost, and writes the tolerance-inheritance sample `samples/<f>.npz`. An INVALID reason holds the
  exception's text; for a bare `RuntimeError` (an `xerrab`) the log's message (the first error line after the last
  `***` run, else that run). The second SENSITIVE run is forked from the same forkserver: it shows run-to-run
  nondeterminism only, not build or memory-layout dependence. Two Linux runs from one
  commit gave the same SHA-256s on one host (x86 emulation on Apple silicon); bit-identity on a native amd64 host is
  AIUE-98's check. A variant is checked with `make_references.variant_tolerance`: the PRD §7.4 rule with the
  variant's own reference in the `rtol_eq` term and the default's σ_i (owner, 2026-10-22, AIUE-94: the default's
  absolute `tol_i` is too small for variants that scale `yldot`; classification still uses the default's).
  `variant_tolerances.py` (PRD §7.4, AIUE-94): `replay REFS|installed` replays every SENSITIVE variant with a build's
  own python and checks it under that rule (exit 3 = owner); on the yldot-data-v3 references mac-noopt passes every
  family (largest 0.006 × tol_i) and mac-serial (`-O3`) fails three variants by 1.7–3.1 × (d_c `bbb.mvolcur`, ortho
  `com.isnonog`, slab_phi `bbb.icnucx`; a recorded macOS `-O3` limit, owner, 2026-10-22, for AIUE-96's test
  design); on yldot-data-v5, where `com.isnonog` is EXCLUDED as family-level (AIUE-159), mac-serial fails the other
  two (d_c `bbb.mvolcur` 1.74 ×, slab_phi `bbb.icnucx` 3.07 ×); `collect` and `check` do the same on the seeded sample against the serial pairs.
  `run_mutations.py` (`list`: checks the mutation set; `run --out DIR`: one scratch worktree and venv for the run, a
  baseline build that must pass, then per mutation apply, build `--serial`, evaluate the inner-loop family first (a
  miss there stops the mutation) and then every other referenced family, cross-check with `test_default.py`, revert;
  a range mutation (Check `locality`) also gets the steady part `locality` (`_child --locality`) and
  `test_locality.py` as its cross-check, the others never (owner, 2026-10-22, AIUE-100 D4), and only in families
  with `[locality]` (owner, 2026-10-23, AIUE-92); writes the coverage matrix `matrix.json`/`matrix.md` (a working
  document, not committed) and its four gates (PRD §7.11 c; a run of named mutations evaluates G1 and G2 only);
  `gates DIR`; exit 3 = owner; run at the end of every phase, about 3 min per mutation).
  `sketch_sensitivity.py` (PRD §7.11 d, AIUE-92): `run <family>... --from-collection DIR | --from-store` per
  sketch-store block the single-entry threshold δ_b (bisection-checked), R_i = δ_b/tol_i, the worst cell's multiple
  per region and, with `--collections`, the round-off pairs against the bound; `--from-store` also checks the stored
  thresholds (exit 2 = harness, 3 = owner).
- **Tolerances** (PRD §7.4, §7.7; AIUE-87): `tests/yldot/tolerances.toml`, generated by `measure_roundoff.py analyze
  --write`: `k`, `rtol_eq` per equation (100 × the largest block-normalised spread over the serial pairs, floored at
  1e-14) with its source, the build records, the pairs, the raw spreads, the floor-report counts, the owner's answers
  and the findings; `families/<f>/sigma.h5` (`/<config>/sigma`, `/<config>/source` = the serial pair that set σ_i, -1
  where σ_i = 0). The Linux side is `tests/yldot/linux/` (Ubuntu 24.04 amd64 by digest, exact apt and pip pins;
  `collect.sh` builds a `git archive` of one commit; `generate.sh`, run from the mounted `tests/`, does the same for
  `make_references.py`). macOS `-O3` is the outlier the serial pairs measure. Since AIUE-92 it covers all eight
  families: `tg` gets its first `rtol` (from large_dd2c) and `up` 1.589e-8 (dnull_imp2's atoms on its wall ring);
  imp7 sets none (`com.redopltvtag = 1`, AIUE-170). Its collections are kept in `../uedge-wt/data/AIUE-92/`.
- **Build flags** (PRD §8) `tests/yldot/tools/build_flags.py`: runs `setup.py` per option set on `linux` and `darwin`
  without building (Forthon's `FCompiler`, `setup()`, `os.system`, the `make` calls, `mppl2f90`, `check_output` and
  `build.run` stubbed; `argv` as pip passes `-C "--build-option=--<opt>"`) and records the `--fargs`/`--cargs` strings,
  `OMPFLAGS`, make's `LDFLAGS`, `OMP` and other changed environment variables, and the uedgeC link and compile
  arguments and macros; it needs setuptools, which a venv of Python >= 3.12 lacks until installed. Not covered: what
  reaches Forthon's real `FCompiler` and its own flags, `-g`/`-t`/`-F`, `--noclean`, `--parallel`, PETSc.
  `tests/yldot/test_build_flags.py` pins that table (27 cases: the default, `--serial`, `--debug`, `--checkbounds`,
  `--noopt`, `--coverage`, combinations, the two refusals, a preset `LDFLAGS`) to `v9-develop`'s, checks that
  `--coverage` changes only its own build, and edits a copy of `setup.py` seven ways to show each is caught. An
  intended flag change updates its `EXPECTED`, with the reason in the PR. `build_flags.py --conversion` runs the real
  `mppl2f90` on two scratch trees with the working directory and `$PWD` differing; the test requires it to convert
  in and stay in the working directory, and a copy with the pre-AIUE-163 `getenv("PWD")` lines to fail (AIUE-163).
- **Reference guard** (PRD §7.6; AIUE-97) `tests/yldot/tools/check_reference_change.py`: `check --base --head` reads
  the head only as data (`git diff`/`git cat-file`, base side at the merge base, the PR description from `PR_BODY`
  without its comments and code fences) and prints which of `Default
  results: changed` (with every changed `<family>:<id>` below it), `Test criteria: changed` and `Test criteria:
  loosened` (plus CODEOWNER approval) the change needs, by path class and by the manifest, `tolerances.toml`,
  `overrides.toml` and `family.toml` rules (owner, 2026-10-22, AIUE-97 ticket page; `[locality]`, AIUE-100: a new
  section is a change, `m_loc` monotone, `delta_loc` non-monotone, the record keys a change, and a changed or
  removed `locality/steady` key `Default results: changed`; a changed or removed `<config>/sketch_threshold` key is a
  loosening, as a changed σ, since a manifest cannot show it smaller, AIUE-92); it downloads the release assets a
  changed manifest names and checks file and dataset SHA-256s. `history` reports the data releases (limit 200 MB), the
  in-git size of `tests/yldot/` (cap 30 MB) and orphan releases. Exit 1 = a declaration missing or a check failed,
  2 = usage. The workflow that runs it is AIUE-104's.
- **Tests** (the whole suite, `-m "not nightly"`: about 860 tests, none skipped, about 8 min, serial build, Darwin
  arm64, 2026-10-23; update these figures only when a ticket moves the count or the runtime by more than about 10 %,
  the exact count goes in the ticket's Validation record; about 250 s of the runtime
  are the three owner families' `test_states`, `test_index_truth` and `test_history` runs):
  `tests/yldot/test_default.py` the live steady and timestep defaults of every family whose manifest names a
  reference file against the stored ones, the Jacobian-flag difference under the same tolerance, the story-1
  headline, and `test_timestep_exercised` (timestep − steady equals minus the stored timestep flag difference bit
  for bit, and the rows beyond tolerance are those where that term exceeds tol_i; owner, 2026-10-23, AIUE-92; about
  2 s); `tests/yldot/test_thresholds.py` the synthetic threshold test (PRD §7.11 b) of the full-vector,
  flag-difference and sketch comparators on the stored defaults, and for a sketch store the single-entry check (the
  stored thresholds recomputed; 10 δ_b on one entry fails that block alone, 0.1 δ_b passes; AIUE-92), pure Python. The session fetches absent reference files first; one still absent fails both through `open_store`
  (decision 23, AIUE-156); `tests/yldot/test_locality.py` the locality check of every family with `[locality]` (one
  steady child each, every column: the `f00` cross-check, no stale column, the stored delta, the pattern with its
  band; story 6 headline), `test_locality_configured` (every small family) and `compare_pattern`'s band rules on
  synthetic entries (AIUE-100);
  `tests/yldot/test_smoke.py` the smoke test, `tests/yldot/test_compare_unit.py` the
  comparator's unit tests, `tests/yldot/test_inventory.py` index truth per family, `tests/yldot/test_inputs.py` the
  input inventory, overrides and value rules, `tests/yldot/test_variant_apply.py` variant application and replay,
  `tests/yldot/test_states.py` both states of every family are round-trip fixed points, `tests/yldot/test_history.py`
  `measure_history.py check` per family (about 3 s each) and the `[evaluation]` keys (measured, or the W = P = 2
  placeholders), `tests/yldot/test_store_unit.py` the store, manifest, `fetch_data.py` and `release_data.py` (sketch
  known-answer vector; fakes for `gh` and `git`), `tests/yldot/test_fetch_unit.py` `fetch_data.py`'s HTTPS download
  and `gh` fallback (fakes, no network),
  `tests/yldot/test_build_flags.py` the build options' flags (about 2 s, no build),
  `tests/yldot/test_roundoff_unit.py` `measure_roundoff.py analyze` on synthetic collections,
  `tests/yldot/test_sketch_sensitivity_unit.py` `sketch_sensitivity.py`'s thresholds, bisection, cell multiple,
  round-off ratio and stored-threshold check on synthetic data,
  `tests/yldot/test_make_references_unit.py` `make_references.py` (its child on `d_only` twice, the same bytes; a
  ten-variant sweep with every class as probed, `--only` reproducing the file bit for bit, a nondeterministic second
  run; `classify` on synthetic results; its refusals, caps and the git/docker commands with fakes; the manifests that
  hold data), `tests/yldot/test_variant_tolerances_unit.py` `variant_tolerances.py` (synthetic sides; a collect and
  a `replay` on `d_only`, `replay` failing on an offset, a NaN and an error),
  `tests/yldot/test_guard_unit.py` the reference guard on scratch git repositories (about 20 s; fakes for the
  downloads and `gh`),
  `tests/yldot/test_tolerances.py` `tolerances.toml` against `sigma.h5` and a live evaluation per family,
  `tests/yldot/test_mutations_unit.py` the mutation set (headers, single-line diffs, `git apply --check` against the
  tree, so a change to a mutated line fails until its patch is refreshed; the composition) and `run_mutations.py`'s
  verdicts and gates (no build, about 2 s).

## Serial old-vs-new bitwise check (required for Fortran, `.v` and `ppp/` changes)

Every PR that touches Fortran (`*.m`, `*.F90`, hand-written `*.f`), a `.v` file or `ppp/` must show that serial
results are **bitwise** unchanged against `v9-develop`, in the `--serial` build and in the default OpenMP build with
`ppp.OMPParallelJac = ppp.OMPParallelPandf1 = 0`. The pytests suite (`rtol=1e-5`) cannot show this.

```bash
python tests/deterministic_omp/harness/serial_check.py \
    --base-python BASE_SERIAL/bin/python --new-python NEW_SERIAL/bin/python \
    --base-omp-python BASE_OMP/bin/python --new-omp-python NEW_OMP/bin/python --jobs 4 --out DIR
```

Four venvs: base and change, each built `--serial` and default, from clean committed trees (the tool does not
build). It runs reproducer presets and pytests cases (D_only, D+C, D_mols, a 16x8 fulltest, drifts, slab and 20
one-switch unit variants; `--list`) once per build in fresh processes. Cases ending in `-itN` run N Newton iterations,
so `psetnk`, the ILU preconditioner, Krylov and the line search are covered. It compares every Jacobian, `sfscal`,
`suscal`, `yldot` and the `fnrm` sequence bit for bit.
- Exit 0: identical over the complete gate (both pairs, two different builds from clean committed trees with
  known sources, base on `origin/v9-develop`, `--cases all`).
- Exit 1: mismatch (the summary names the case and the first differing entry).
- Exit 2: harness error (a wrong build kind; same build, tree or clean commit; a record not on the serial path; an
  `-itN` case that did not iterate) or an incomplete gate (`RESULT: INCOMPLETE`; `--partial-ok` for a quick look).

Needs the pytests checkout (below). Paste the build lines and the `RESULT` line into the PR. Details:
`tests/deterministic_omp/README.md`.

## Fast iteration: subset while working, full matrix once

Builds and test matrices were the longest waits of epic AIUE-8 (one ticket 5.7 h, a cost study 2.1 h). While working:

- **Iterate on a subset**: one case (the reproducer preset or the one pytests case the change touches) at **two
  thread counts** (e.g. 1 and 4 for OpenMP work), and the one suite the change can affect.
- **Run the full matrix once**, at the end (`validate`, the serial bitwise check, the OpenMP flow), not after every
  edit. A failure there sends you back to the subset with the failing case added.
- **Prefer CI for heavy matrices**: push the branch and let `build-test-omp.yml` run its PR set (about 12 min on
  native `ubuntu-latest`) instead of an emulated or many-thread local matrix; quote its result.
- **Reuse builds**: one base venv per build kind (`--serial`, default OpenMP) per branch point, built once from a clean
  committed `origin/v9-develop` tree and shared by the tickets based on it (read-only: never reinstall into it); each
  ticket worktree keeps its own venv for its own build and rebuilds only when its sources changed. Name base venvs by
  their commit, `uedge-wt/venvs/base-{serial,omp}-<sha>`, so a stale one is visible; build a new pair when
  `v9-develop` moves past it.
- **Compared builds use one install mode.** Builds whose results or logs are compared (base vs ticket venvs, the
  serial bitwise check, a build-log diff) must differ only in the source tree:
  - the same interpreter: create the venv with the Python named in the base venv's `pyvenv.cfg` (`home`/`version`;
    pyenv 3.13.12 so far), not whatever `python` resolves to;
  - the same build dependencies, installed in the venv (`forthon`, `numpy`, `setuptools`, `h5py`, at the versions
    `pip list` shows in the base venv), and `pip install -v --no-build-isolation .` (plus `-C
    "--build-option=--serial"` for the serial kind). Without `--no-build-isolation`, pip builds in an isolated
    environment with unpinned Forthon, numpy and setuptools. Put the venv's `bin` first on `PATH` (activate it, or
    `export PATH=<venv>/bin:$PATH` in the build script) even when calling `<venv>/bin/pip` directly: the build runs
    `Forthon3` from `PATH` (`Makefile.Forthon:8`), and otherwise picks up another Python's (seen: a pyenv 3.14 shim,
    `No module named 'setuptools'`);
  - the same `CC` (and `CFLAGS`) as the base venv was built with. On macOS the OpenMP build needs an OpenMP-capable
    compiler: a libomp clang (`CC=$(brew --prefix llvm)/bin/clang`) or `CC=gcc-15 CFLAGS="-std=gnu17
    -Wno-error=incompatible-pointer-types"`, which built `base-omp-0480272`. Record the one used next to the base
    venv. The serial build has not needed a `CC` since AIUE-109 (62ac2b1).
- **Probing initialisation without a solve** (grid-change interpolation, `ueinit` checks): after the restore and the
  input changes, `bbb.ifexmain = 1; bbb.allocate(); bbb.ifexmain = 0; bbb.ueinit()`. A Python `allocate()`
  (`ifexmain = 0`) sets `nxold`/`nyold` to the current size, reallocates `Interp` and sets `isimesh = 1`
  (`bbb/odesetup.m:523-528`, AIUE-141). The next `ueinit` then copies the saved state as it is: a restore after the
  allocate is used for the current mesh, and the last `gridseq`'s old-mesh data are dropped. To interpolate after a
  same-mesh allocate (e.g. one made to set wall arrays), set `bbb.isimesh = 0` after it (owner, 2026-10-21). Without
  that, a mesh change with no restore stops with `variable nis=0, no saved solution for interp` (probed through
  `exmain`, nonog 8x4 → 16x8, AIUE-141; before AIUE-141 the recipe above stopped with `ERROR: ni <= 0`, d3dHsm
  8x4 → 16x8 in base-a8446eb-serial).
  Going through `exmain` instead runs the Newton solve (`itermx = 0` means nksol's default of 200 iterations,
  `svr/nksol.m:973`), and after a converged solve `gridseq` overwrites the `Interp` meshes.
- Raw outputs (logs, per-case tables, `.npz`/`.hdf5` dumps) go to `.claude/work/<KEY>/` or a scratch directory and
  are summarised on the ticket page; they are never committed.
- **The OpenMP flow's output directory**: `tests/deterministic_omp/ci/run_omp_ci.sh` writes `./omp-ci-out/` (ignored by
  `.gitignore`) and refuses to start if it exists. Set `OMP_CI_OUT` to a new path in `.claude/work/<KEY>/` for each run,
  e.g. one for the base and one for the ticket build.

### Bisecting old commits on macOS

Every commit before AIUE-109 (62ac2b1) passes `-fopenmp` to the C compiler, even with `--serial` (which `setup.py` has
had since d32c88b, 2025-01), so Apple clang fails the link. With `CC=gcc-15`, gcc 15's C23 default makes the pointer
assignments in `bbb/exmain.c:71,117` hard errors. Build each bisect step with

```bash
CC=gcc-15 CFLAGS="-std=gnu17 -Wno-error=incompatible-pointer-types" OMP_NUM_THREADS=1 \
    pip install -v --no-build-isolation .     # add -C "--build-option=--serial" from d32c88b on
```

(as a script file: the permission check refuses `VAR=… cmd` prefixes, `CLAUDE.md` → Gotchas). Mark a step whose build
fails `git bisect skip`; without these flags a whole range is skipped and the bisect stalls at "N revisions left".

## Suite structure (`pytests` branch)

```
pytests/fulltests/<case>/{input.py, conftest.py, test_<case>.py, gridue, *.h5 reference}
pytests/unittests/{D+C, D_mols, D_only, slab_D_only}/<case>/<variant>/{input.py, conftest.py, test_*.py, ...}
MakeTests.py              # regenerates whole test directories (re-perturbs every case)
tools/rereference.py      # origin/pytests only: regenerates one case's reference, keeping its stored state
V9_REFERENCE_CHANGES.md   # origin/pytests only: every reference that differs from LLNL's, and why
```

Each test (`TestClass.test_reference`):
1. Silences output (`com.iprint = 0`), executes `input.py` to set up the case.
2. Sets `bbb.issfon=1`, `bbb.ftol=1e20` (evaluate only, no convergence) and runs `bbb.exmain()` from a stored,
   deliberately **perturbed** solution. The perturbation (`perturb_solution`, ±1 % random on
   `nis/ups/tes/tis/ngs/tgs/phis`) was applied to `solution.h5` by `write_data` when the reference was made; the test
   itself never calls it, so a test run is deterministic.
3. Cycles the equation switches (`isnion … isphion`) one at a time and compares the residual `fnrm` and
   case-setup variables against the reference with `rtol=1e-5`. A failure prints which equation/species diverged.
   This makes the suite a sensitive check of the **RHS residual (`pandf`)**, not of converged physics.

`conftest.py` chdirs into the case dir (same fixture as `pyexamples/input_example/conftest.py`).
`pytest --isolate` (pytest-isolate) is required: each test needs a fresh process because Forthon module state is global.

## Running locally

```bash
pip install . -C "--build-option=--serial"     # mirror CI
pip install pytest pytest-isolate
git fetch origin pytests
git worktree add --detach ../uedge-pytests origin/pytests   # an existing checkout: git -C ../uedge-pytests checkout --detach origin/pytests
cd ../uedge-pytests
pytest --isolate --tb=long pytests/unittests/D_only -s        # fastest
pytest --isolate --tb=long pytests/fulltests -s
```

Pick the suite that exercises your change (impurities → `D+C`, molecules → `D_mols`, slab geometry →
`slab_D_only`). Physics-neutral changes must pass **all** suites unchanged. On LLNL's `upstream/pytests` the cases
listed in `V9_REFERENCE_CHANGES.md` fail for v9 by design; don't use it for v9 work.

## Known failures on `v9-develop`

`validate` marks a failure listed here ⚠️ pre-existing without a base re-run; anything else is the change's until a
base run shows otherwise. Remove an entry when its fix merges. Before scoping a ticket about a failing test, run
**every** suite on a base venv of the branch point and record here what is red there.

Last full run: all suites on a serial build of the AIUE-132 change (same-mesh restart copies, on `v9-develop` c82a515)
against `origin/pytests` f695acd (2026-10-21): 157 passed (D_only 125, D+C 1, D_mols 27, slab_D_only 1, fulltests 3).
- **Failures:** none.
- **Passes with a warning:** none. The D_only `nonog/icnucx` warning seen before ("Fnrms outside of tolerances, but
  similar") came from the second exmain interpolating onto the same mesh, fixed by AIUE-132.

## When results change intentionally

New physics should be off by default, so references stay valid. If a reference must change (a bug fix, or an owner
decision on a physics default), regenerate that case with `tools/rereference.py <case dir>` on `origin/pytests`, in a
separate PR to that branch, add the case to `V9_REFERENCE_CHANGES.md` (old and new `fnrm`, the change that moved it,
who decided it), and explain the diff in the main PR. Not `MakeTests.py`: it rebuilds the whole directory and
re-perturbs every case with unseeded random numbers, so every reference in it would move.

## CI facts / quirks

- `build-test-wheel.yml` builds with `--serial`, Python 3.11, `numpy==1.26.4`; it does not exercise OpenMP.
- `.github/workflows/build-test-omp.yml` (AIUE-57) tests the OpenMP paths: it builds the default OpenMP build
  (`pip install -v .`, Python 3.11, `numpy==1.26.4`; no `LDFLAGS` since AIUE-64) and runs
  `tests/deterministic_omp/ci/run_omp_ci.sh`: harness and CI unit tests, a smoke test, the common-block check
  (`tests/deterministic_omp/ci/common_check.py`), the OpenMP test flow, the C1 bound
  (`tests/deterministic_omp/ci/jac_bound.py`) and `tests/deterministic_omp/ci/report.py`
  (`tests/deterministic_omp/README.md`, "CI"). Triggers: `pull_request`, `push` to `v9-develop`/`main` only, and a
  nightly `schedule` (default branch only). PR set: `tebox1` (2, 4 threads, K=3, `jac`, one evaluation),
  `tebox` (2, 4 threads, K=5, both arms, `--itermx 3`), both Te-box flows with `OMPJacMinChunkLen=1` (25 chunks),
  `up1` (4 threads, K=3, `jac`, one evaluation) and `full` (2, 4 threads, K=2, `jac`, `--itermx 3`); nightly:
  `--all` one evaluation K=2, Te box 25 chunks at 2/4/8 threads, and `--all` `--itermx 3` K=3. Gate: the `jac` arm,
  bitwise, plus the C1 bound on the scaled `post_exmain` Jacobian and the common-block check; `jacrhs` is
  report-only (epic AIUE-70). `OMP_CI_JAC_TOLERANCE` (≤ 1e-6, empty in the workflow) is a tolerance mode for macOS
  replays. Merges with or after `bugfix/v9-openmp-determinism-fix`, once its first native PR run is green within
  20 min. Same steps locally: `PYTHON=<omp venv python> tests/deterministic_omp/ci/run_omp_ci.sh pr`; in the Ubuntu
  image: `tests/deterministic_omp/linux/run_ci_replay.sh`.
- In `build-test-wheel.yml` the "Install pip dependencies" step runs `pip install forthon>=0.10.7 ...` unquoted: the
  shell redirects to a file named `=0.10.7`, so Forthon is installed unpinned. (`build-test-omp.yml` quotes it.)
- Non-`master` branches check out `pytests-develop`, which upstream does not have (only `pytests`) → test step fails on checkout.
- `@notest`/`@nowheel` commit tags are inert (no job `outputs:` on `check-requests`; `wheel` vs `wheels` mismatch).
  The tags are read only from message lines that start with `#` (`#@notest @nowheel`), so a squash title's `(#N)` and
  its `Co-Authored-By` addresses are not tags (AIUE-175). Tags apply to push runs only: a `pull_request` run checks out
  GitHub's merge commit (depth 1, so `--no-merges` keeps it) and reads its "Merge … into …" message.
- There is no BASIS CI. `build-basis.yml` was removed (AIUE-178, owner 2026-10-23): its `fusionbillm/basisuedge` image
  built LLNL/UEDGE's branch of the same name, never the fork (LLNL `master` for a branch upstream lacks; on
  `v9-develop`, LLNL's `v9-develop`, which fails in BASIS make on `bbb.pack`). A `#@nobasis` tag has no effect.
- `claude-review.yml` runs `/code-review` on PR open or `@claude-review` comment.
