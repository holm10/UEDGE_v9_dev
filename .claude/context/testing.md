# Testing — what actually exists

**The yldot suite (`tests/yldot/`) is the regression suite.** The old one, on the fork's `origin/pytests` branch, is
retired (AIUE-107): the yldot PR and nightly tiers take more `bbb/pandf*.F` branches than it did (Coverage, below),
and its last state is kept in "Retired suite" below. CI runs the yldot PR tier (`build-test-wheel.yml`, AIUE-103, CI
facts below). There are no unit tests of individual Fortran routines.

The repository holds two test trees. `tests/deterministic_omp/` is the OpenMP Jacobian reproducer of AIUE-8 (deck, trimmed
data, `tests/deterministic_omp/tools/fingerprint.py`; see `tests/deterministic_omp/README.md`), with the bitwise
harness in `tests/deterministic_omp/harness/` (OpenMP vs serial: `cli.py`, with the test flow `cli.py flow`, see
`openmp-jacobian.md`; serial old vs new: `serial_check.py`). No CI job runs them yet. Each run directory's
`run.log` is in time order (`GFORTRAN_UNBUFFERED_PRECONNECTED` and the workers' line-buffered stdout, AIUE-239,
probed), so a failed run's reason (`flow.failure_reason`, `serial_check.error_cause`) takes the log's tail of whole
lines (`runner.log_tail`) when the exception has no text or the run crashed without writing its record.

`tests/yldot/` is the yldot suite (epic AIUE-9). Run it as `pytest tests/yldot` (never `pytest tests/`). In a
background or batch run whose log is read later, pass `-rf --tb=short`, so each failure's id and text survive the
session's fetch summary (AIUE-198: with `-q` the summary hid the FAILURES section, AIUE-99). One bullet
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
  release assets of the release their manifest names (`yldot-data-v13` since AIUE-101; owner, 2026-10-22, D6),
  gitignored, with their SHA-256s only in `references/<f>.manifest.json` (owner, 2026-10-21); a manifest naming
  release assets under `families/<f>/` is what makes an owner family (`manifest.owner_family`). `conftest.py` fetches every manifest's release assets at the start of the session
  (`fetch_data.fetch`: download if absent, SHA-256 check, link; decision 23, owner 2026-10-22, AIUE-156); nothing
  under `tests/yldot/` skips. If the fetch is impossible or `--yldot-no-fetch` is given, a test parametrised over a
  family with absent `families/<f>/` assets fails at setup naming the cause, except those marked `toml_only`;
  different files fail (`test_smoke.py::test_external_files`). The marker `nightly` (AIUE-96) is the nightly tier
  (PRD §4): the PR tier runs `-m "not nightly"`; the owner families' variant tests (AIUE-99), their default
  locality tests and every variant locality test (`test_locality_variant`, about 2,900 with the small families';
  AIUE-101) carry it.
  `--yldot-shard NAME` (repeatable; AIUE-103) keeps one CI shard: a family's tests (by their `family` parameter) or
  `common` (the rest); `tests/yldot/tools/shards.py` defines the shards, so a test is in exactly one. A test that uses a family's
  files takes the family as its `family` parameter, or it lands in `common` (`test_thresholds.py`'s comparator tests
  were re-parametrised for this, AIUE-103). The test dependencies are the `test` extra (`pip install ".[test]"`).
  Every family holds `sigma.h5`, the measured round-off spread σ_i per configuration (see Tolerances). The
  reference files `references/<f>.h5` are release assets of the release their manifest names, gitignored, named by
  `references/<f>.manifest.json`; `fetch_data.py` fetches them. Every family's holds the defaults and the
  SENSITIVE variants and its manifest classifies every variant (since AIUE-99, which swept the owner families'
  sketch stores and made `bbb.isfixrb` family-level; AIUE-88, AIUE-94); `yldot-data-v13` (AIUE-101, `locality-only`
  on Intel) keeps every v9 default and variant bit for bit and adds the locality data. `yldot-data-v14` (seven
  families) and `v15` (imp7) are full sweeps with the scalar-math Linux build (AIUE-211), the same on any x86 CPU.
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
  Linux-built references; the scaled one stays below 3.5e-10 unmutated (owner, 2026-10-22, AIUE-89). Only residual
  entries that reach yldot count (owner, 2026-11-11, AIUE-176): with diagnostics on (and no locality), the child
  repeats step 8b's `pandf` with `isrscalf = 0` and marks a `res*` entry live where its yldot row equals `calc_rhs`'s
  copy bit for bit (`state.live_residuals`, `r.data["live"]`), and `Store.diagnostic_pair` zeroes the others on both
  sides (`compare.mask_dead`). Unmasked, dnull_imp2 on macOS `-O3` named `resmo` at its plate face (Fortran
  (36,34,2), algebraic, 1.9e-6 by FMA) and had NaN in `resei`/`reseg` at the cut guard ix = 37 from its round-off
  `dxnog`, until AIUE-253 made that face orthogonal in `nphygeo` (older references still store it, dead); masked, all 8 families x 2 configurations name none (largest 3.0e-10). For a sketch store
  `Store.diagnostic_pair` also cuts the new run's diagnostics to the stored `res*` names.
- **Variants** (PRD §7.2): `tests/yldot/harness/inputs.py` is the input inventory, read with Forthon's own `.v` parser
  (968 `+input`/`+maybeinput` variables; a line grep overcounts); `tests/yldot/harness/variants.py` holds the value
  rules, `plan()` and `apply()` (in the child: `d` read live, the applied value recorded exactly and replayable
  through `Runner.evaluate(..., variant=, replay=)`); `tests/yldot/overrides.toml` holds the additions, exclusions,
  explicit values, bounds, phase and configuration, each with a reason. Switches that pick the geometry, the topology
  or the species model (`isudsym`, `islimon`, `isfixlb`, `isnonog`, `mhdgeo`, `gengrid`, `ishymol`, and `isfixrb`
  since AIUE-99) are EXCLUDED as family-level and are covered only by families of their own (owner, 2026-10-23,
  AIUE-159). `isoutwall`, `isch_sput` and `ipsputt_s` are EXCLUDED until their build-dependent results are fixed
  (bug AIUE-195; owner, 2026-10-24, AIUE-99). `bbb.ziin` (the ion
  charge, integers only: `chkziin` in `allocate` and `ueinit` refuses any other) takes the `charge` rule, d+1 on the
  hydrogenic ion slots (`ziin > 0` among the first `com.nhsp`, read live), atoms and impurity charge states
  unchanged (owner, 2026-10-23, AIUE-161).
- **Store** (PRD §7.3): `tests/yldot/harness/store.py` writes and reads one HDF5 reference file per family
  (`create`, `open_store`): `FullVectorStore` (full default, variants as the rows that differ bitwise) or
  `SketchStore` (full default, per (equation, species, region) block k = 8 projections of the weighted vector x·w
  onto Rademacher signs from `PCG64.random_raw`, summed with `math.fsum`; `sketch_compare` with c = 6.5 and the
  bound c·sqrt(Σ(tol·w)²), AIUE-174), both with the sparse Jacobian-flag
  difference; files written with `track_times=False` so the bytes are reproducible, in the HDF5 1.10 format
  (`LIBVER`, superblock version 3: smaller group headers keep the variant groups within the caps; owner,
  2026-10-22, AIUE-94); `Writer.copy_variant` copies a stored variant verbatim. `tests/yldot/harness/manifest.py`
  is the schema of `references/<f>.manifest.json`, the only record of the external files' SHA-256s (owner,
  2026-10-21); `dumps` writes it indented and sorted, each encoded value's `data` list on one line (owner,
  2026-10-22, AIUE-94), as `runs` (`[[value, count], ...]`) when they are fewer, and `loads` expands them, so read
  manifest text with `load`/`loads`, never `json.loads` (owner, 2026-10-25, AIUE-190: `tests/yldot` 29.19 → 14.56 MB
  in git). `open_store` checks the file SHA-256, the dataset set, the blocks and that the manifest's
  `guarded`, `unguarded` and variant SHA-256s and its variant set follow from the datasets; every read recomputes
  the dataset's SHA-256 (`StoreIntegrityError`). A family with `[locality]` also stores
  `/steady/locality/{delta, column, row, mismatch, dfull}` (the entries with score > 1), guarded as `locality/steady`
  and derived from the datasets like the defaults (AIUE-100), plus `/steady/locality/columns` only for a column set,
  and its variants' patterns packed in `/<config>/locality_variants/{ids, offsets, column, row, mismatch, dfull,
  dropped_offsets, dropped_column, dropped_row}` as differences from the default pattern (`locality.diff`/`apply`),
  guarded as `locality_variants/<config>`, each slice's SHA-256 in the manifest's `locality_variants` and checked at
  open (`Store.locality_variant`, `locality_pattern`; one HDF5 group per variant would break the 8x4 caps; AIUE-101). A sketch store also stores, per configuration, its
  weights `/<config>/default/sketch_weight` (w_i = 1/tol_i of the default at generation; required in every sketch
  store, `open_store` and `Writer.finish` refuse one without and a full store with any; owner, 2026-10-23, AIUE-174),
  guarded as `<config>/sketch_weight`, and
  `/<config>/default/sketch_threshold/{block, cell_ix, cell_iy, cell_m, cell_block}` (`store.sketch_thresholds` of
  the default's tol_i and the weights: per block δ_b = c·sqrt(Σ(tol·w)²), so the smallest detectable single-entry
  change is δ_b/w_i; per cell the smallest multiple of its tolerances; PRD §7.11 d), guarded as
  `<config>/sketch_threshold` (AIUE-92). With the weights every entry is seen at R_i = δ_b/(tol_i·w_i) = c·sqrt(N)
  of its own tolerances while tol is the generation tol (unweighted, the owner families' guard rows needed up to
  1e13), within the owner's R_max = 2·c·sqrt(N_block) (AIUE-92 D3). `make_references.py --only` keeps the stored
  weights, so the copied variant sketches stay valid.
- **Locality** (PRD §7.5; AIUE-100) `tests/yldot/harness/locality.py`: `jac_calc`'s protocol (`bbb/oderhs.m:1095-1226`)
  in the child after step 8b (`Runner.evaluate(family, locality=delta)`; the PR tier: steady, no variant): flag +1, `f00` (must
  equal `yldot_J` bitwise), then per column reset to `f00`, perturb by `delta·(|y|+dylconst/suscal)`, local `pandf`,
  full evaluation, restore, local again, full again (must equal `f00`: no stale column). Score per entry
  `|Δ_full−Δ_local| / (tol_r + rtol_eq·|Δ_full|)`; the pattern P is the stored entries above `M_loc`, (1, M_loc] is the
  unasserted band (owner, 2026-10-22, D3). `family.toml` `[locality]`: `delta_loc = 1e-6`, `m_loc = 100` (the only
  grid δ with no stored entry within 3× of M_loc), the calibration record and the causes. The isnonog = 1 families
  (d_only, d_mols, d_c) have a by-design default pattern, all in the band at 1e-6: the neutral-conductivity
  4-point average in `feixy` (`bbb/pandf_plasma_energy.m:458-459,476-477`) reaches ix−1, one cell beyond `xrinc`
  (owner, D2); ortho and slab_phi are bit-identical on every column. Every column of the five takes about 12 s.
  Nightly tier (PRD §7.5 "Columns and tiers"; AIUE-101): `Runner.evaluate(..., locality=δ, columns=...)` also runs
  with a variant and in the timestep configuration. `[locality]` adds `columns` (`"all"`, or `"special"` with
  `sample` and `seed`: `special_columns`, the owner's rule for any `nxpt` from the live grid, plates
  `ixlb/ixrb(jx)` and +1, radial rows 0, 1, ny, ny+1, separatrix rows `s, s+1` of every `iysptrx1/2(jx)`, cuts
  `ixptK(jx)`, +1 for iy ≤ `iysptrxK(jx)`, plus `sample` interior columns by `PCG64(seed).random_raw`; variants use
  the special cells only), `variants` (`"all"` SENSITIVE/INERT/MARGINAL, `"listed"` `bbb.meth*` and
  `WINDOW_INPUTS`, `"meth"`), optional `excluded` (owner exclusions with their cause: `bbb.isupgon` in the 8x4
  families, `pandf` not repeatable after it, AIUE-208) and `near_margin` (the owner's acceptance of default entries
  within 3× of M_loc). The owner families run δ = 1e-6 on the special cells plus 300 seeded columns (8236 / 8252 /
  9036): D3 qualified no δ, their near-margin entries are the nonog signature (owner, 2026-10-25); the 3× rule
  calibrates δ on the default pattern only, variant patterns are stored and asserted as they are.
- **Mutations** (PRD §7.8, decision 25) `tests/yldot/mutations/*.patch`: 27 patches (AIUE-89, AIUE-90), a sign
  flip, a factor 2 and a dropped term per equation, the X-point off-by-one, a wrong `cf*` multiplier, two range and
  two flag-gating mutations. A `Key: value` header (`Mutation`, `Kind`, `Equation`, `Fault`, `Check`, `Configs`,
  `Blocks` per family, optional `Cells`, `Intermediate`, `Families` with the inner-loop family first, optional
  `Pending`, optional `Variant`, `Source`, `Description`; a line starting with a space continues the previous key's value, e.g. one
  `Blocks` line per family as `<family>: primary <blocks>; coupled <blocks>`; the keys are documented in
  `run_mutations.py`), a blank line, then a single-line `git diff`; `git apply` skips the header. Applied only in a
  scratch worktree, never to a source on a branch. None is `Pending` since AIUE-96: `ishosor_flag_gating` (the
  `ishosor` integration, which no default runs) names `Variant: bbb.ishosor` and is checked through d_only's stored
  `bbb.ishosor` variant, its primary blocks those of the variant's stored flag difference (owner, 2026-10-23,
  AIUE-96 D7); the gas-energy ones fire in large_dd2c's `tg[2]` since AIUE-92, which added
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
  `shards.py` (the CI shards, standard library only: no arguments prints them as JSON, `common` then the families,
  for `build-test-wheel.yml`'s matrix; `shard_of` is the rule `--yldot-shard` applies; `--check NAME…`; AIUE-103);
  `release_data.py` (the release command: checks the files, the tag number (no remote git tag either) and the
  target, prints `gh release create`; publishes only with `--publish`, which the owner runs or approves; it takes
  only N = highest published + 1, so a hand publish (no `--renumber`) reserves its N on its ticket page once the
  owner agrees; a publish through `regenerate-references.yml` (`--renumber`, below) reserves none and records the N
  it got; planning reads the in-flight tickets' pages for both, `plan-feature` Phase 2 step 6 (AIUE-207). Every
  publish first creates the tag
  through the git refs API (an existing tag fails the call) and then runs `gh release create --verify-tag`; a tag whose
  release then fails has used up its N. `--generated`: the manifests naming the tag come from a generation of
  `--target` and are not committed (`tests/yldot` outside `references/` must be `--target`'s, and each manifest's
  provenance commit `--target`); `--renumber` (with it) takes the highest release or remote tag + 1, rewriting the
  manifests' `release` (a dry run only reports the N), and moves on after a collision, at most `ATTEMPTS` = 3;
  `--note`; `--gate` checks only `--target`; a successful run ends with `tag=<tag>`. `regenerate-references.yml` runs it, below, AIUE-98);
  `measure_roundoff.py` (`collect`, run with each build's own python or in the Linux image: per family and
  configuration two fresh processes, pickled `yldot`/`yldot_J` and index arrays with the build record; `--omp N` adds
  the `ffun` RHS with the `ppp` OpenMP flags set in the `post` hook; `analyze`: the pairs `same_build:<label>`,
  `o0_vs_o3`, `mac_vs_linux` (serial, they feed σ and rtol), `debug_vs_o3` and the OpenMP rows (report only), the
  floor report, the AIUE-81 re-check; `--write` writes the files below; exit 4 = a nonzero same-build spread, 3 = owner);
  `make_references.py` (`generate --from-commit SHA`: builds SHA `--serial` and writes each family's steady and
  `timestep` defaults, Jacobian-flag difference, diagnostics and σ_i with the manifest's provenance, and for a family
  with `[locality]` the steady locality pattern (AIUE-100) over its column set and, after the sweep, every
  `variant_scope` variant's pattern replayed and scored with the tolerance its test uses (`locality_tolerance`;
  stale columns, failed runs and default entries within 3× of M_loc without `near_margin` are findings, the
  near-margin counts go to `<family>.locality.json`; AIUE-101); `--locality-only` copies every entry of the
  installed reference and computes only the locality data, every guarded SHA-256 kept (exit 3 otherwise; a macOS
  build cannot reproduce Linux defaults, so preview it in the Linux image); `_child --jobs N` runs one process per
  family, largest first (default the CPU count); `--platform
  linux` (default) in the pinned image through `linux/generate.sh`, the only release-grade path, run by
  `regenerate-references.yml` on native amd64 (owner, 2026-10-25, AIUE-98; locally a preview), `--platform host` a
  temporary worktree and venv, built with `PWD` set to it (for commits before AIUE-163), a preview with `release:
  null` (owner, 2026-10-22, AIUE-88); default families: the small ones
  (with `sigma.h5`, not owner families); an owner family only when named (swept like the others since AIUE-99, or
  `--defaults-only`), its `families/<f>/` assets checked against its manifest and carried into the new one with its
  `sigma.h5` (AIUE-92); `CAPS_MB` 13 MB for each owner family (owner, 2026-10-24, AIUE-99);
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
  for bit; in a sketch store its stored weights are kept and the thresholds recomputed from them, so `--only` does
  not notice a changed `tolerances.toml` rule, only the guard's changed `sketch_threshold` keys do: regenerate in
  full after one, AIUE-99 review; it takes every following word (`nargs="+"`,
  `tests/yldot/tools/make_references.py:1298`), so name the families first: `generate … d_only ortho --only
  bbb.isfixrb`, AIUE-198; the copied entries keep their `reason` text, so an `--only` release's provenance commit is
  where only the regenerated entries were computed, AIUE-98, AIUE-206)
  and `--full` (dense vectors for localization). `--prune` and `--rename OLD=NEW…` (AIUE-95; owner, 2026-10-28, D1;
  `--rename` takes every following word too) run the `--only` path: prune drops the manifest entries no longer in the
  inventory (SENSITIVE ones too, then the guard needs `Default results: changed`), rename classifies each NEW again
  and drops OLD; every kept entry is copied with its stored data and its locality pattern
  (`Writer.copy_locality_variant`, never re-run), every other guarded SHA-256 must come out the same (exit 3), and
  NEW must reproduce OLD, the applied value first (exit 1 "applied value differs", then the guard's
  `rename_differences`); plain `--only` with stale entries names them. The `--checkbounds` audit (PRD §4; AIUE-95,
  owner D2, D3): a sweep, `--only` and `--rename` first build SHA `--serial --checkbounds` (`-fbounds-check
  -fcheck=all`, `AUDIT_FLAGS`) and evaluate every variant they classify and both defaults there once (`_child
  --audit-only`, `--jobs` shards per family, merged into `<f>.audit.json`); a variant whose audit run ends in a
  Fortran runtime error is INVALID with the reason `bounds-check: <dir/file.F:line>: <message> (serial build: <class or
  serial reason>)` (the generated `.F`'s line; `runtime_error`; the serial build's own outcome appended by
  `audit_invalid_reason`, owner D5), nothing stored; an audit run that fails otherwise while the serial build classifies
  the variant other than INVALID, a runtime error on a no-op variant and a default that fails there are findings
  (exit 3). A bounds abort reaches the harness as status `crash`, exit code 2, the message only in the log tail
  (probed, AIUE-95). `--no-audit` is for previews (refused with `--release`); `--defaults-only`, `--locality-only`
  and `--prune` never audit. On the five small families the macOS audit at c8431d5 took 70-91 s per family and
  found seven bounds errors (AIUE-95 ticket page). Per family it prints the summary line (PRD §5 story 3, with
  marginal) and the cost, and writes the tolerance-inheritance sample `samples/<f>.npz`. An INVALID reason holds the
  exception's text; Fortran stops outside `grd/` and `flx/` pass their message to `xerrab` (AIUE-239, owner D1). For
  a bare `RuntimeError` (an `xerrab("")`) it holds the tail of the child's log, which is line-buffered and so in time
  order (`tests/yldot/harness/state.py` `run`): whole lines from the end up to the 300-character cap, NULs stripped,
  ending at the stop (`make_references.logged_error`; AIUE-239, owner D2′). The second SENSITIVE run is forked from the same forkserver: it shows run-to-run
  nondeterminism only, not build or memory-layout dependence. Two Linux runs from one
  commit gave the same SHA-256s on one host (x86 emulation on Apple silicon), and so did two native amd64 runs
  (`regenerate-references.yml` on `ubuntu-24.04`, runs 40220476594 and 40234117547, full sweep at `bfca6180`). Native
  and emulated runs of one commit and image differ in three variant vectors, `d_only:bbb.ineudif`, `d_c:bbb.ineudif`
  and `d_c:bbb.rtg2ti`, with everything else bit-identical and every class the same; those native runs are presumed
  to have landed on AMD runners (their CPU was not logged), with the cause below; neither the AMD attribution nor the
  shared cause is probed. References up to `yldot-data-v9` were made emulated. Native CI is the reference platform (owner,
  2026-10-25, AIUE-98): references come only from the workflow, local runs are previews. The `ubuntu-24.04` pool
  mixes CPUs, and results follow the CPU, not the run (AIUE-101): the full sweep at `333af1e` (run 40273278698)
  reproduced every v9 dataset of all eight families, those three entries included. dnull_imp2's defaults reproduce
  v9 on an Intel Xeon 8573C but differ on AMD EPYC 7763, 9V45 and 9V74 (80 `yldot` rows, max |diff| 1.2e-7), the
  same rows on every AMD run. The cause is glibc's vector math library (AIUE-210): gfortran `-O3` vectorizes loops
  that call `exp`, `log`, `pow`, `sin` or `cos` into libmvec's 2-lane `_ZGVbN2v_*` (e.g. `fd2tra`'s log interpolation,
  `bbb/oderhs.m:468-484`, used with `methg = 66`), and libmvec's SSE4.1 `log` kernel uses `rcpps`, whose bits differ
  between Intel and AMD; Rosetta (x86 emulation on Apple silicon) gives Intel's, shown for dnull_imp2's base. With `GLIBC_TUNABLES=glibc.cpu.hwcaps=-SSE4_1`
  libmvec falls back to scalar libm and Intel and AMD agree bit for bit, but every owner family then moves by thousands
  of rows from v9. A bitwise check (`--only`, `--locality-only`, `expect_ref`) of references made before AIUE-211
  passes only on a matching CPU (Intel, owner 2026-10-26, AIUE-101; Xeon 8573C, Platinum 8370C and 6973P-C all
  reproduce v9, and v13 came from a 6973P-C). Since AIUE-211 the Linux build keeps those math calls scalar, and Intel
  and AMD runners and x86 emulation give bit-identical full sweeps of all eight families (probe runs 40412437619,
  40450670163), so the workflow's `cpu` input defaults to empty, any runner (owner, 2026-10-27); every case that
  reached a vectorized call moved by round-off, and v14 and v15 replace the earlier references (1816 entries of all
  eight families, PR #75). A variant is checked with `make_references.variant_tolerance`: the PRD §7.4 rule with the
  variant's own reference in the `rtol_eq` term and the default's σ_i (owner, 2026-10-22, AIUE-94: the default's
  absolute `tol_i` is too small for variants that scale `yldot`; classification still uses the default's). A sketch
  store keeps no dense variant reference: its SENSITIVE variant is checked under the same rule with the replayed
  run's `yldot` in the `rtol_eq` term, through the sketch comparator with the stored weights, ratio the largest
  |dP| / bound (owner, 2026-10-24, AIUE-99 Q2); `run_mutations.py` refuses a `Variant` in a sketch-store family.
  `variant_tolerances.py` (PRD §7.4, AIUE-94): `replay REFS|installed` replays every SENSITIVE variant with a build's
  own python and checks it under that rule (exit 3 = owner; `check_sensitive`, one variant's check, is also
  `test_variants.py`'s); on the yldot-data-v3 references mac-noopt passes every
  family (largest 0.006 × tol_i) and mac-serial (`-O3`) fails three variants by 1.7–3.1 × (d_c `bbb.mvolcur`, ortho
  `com.isnonog`, slab_phi `bbb.icnucx`; a recorded macOS `-O3` limit, owner, 2026-10-22, for AIUE-96's test
  design); on yldot-data-v5, where `com.isnonog` is EXCLUDED as family-level (AIUE-159), mac-serial fails the other
  two (d_c `bbb.mvolcur` 1.74 ×, slab_phi `bbb.icnucx` 3.07 ×), and the same two on yldot-data-v8, where the integer
  `bbb.ziin` variant replays within 0.017 × tol_i on mac-serial and 4e-4 × on mac-noopt in all five families
  (AIUE-161); `collect` and `check` do the same on the seeded sample against the serial pairs. In
  `test_variants.py` such a macOS mismatch is reported, not failed (owner, 2026-10-23, AIUE-96 D1), when the build
  record says so: `tests/yldot/harness/build.py` reads the installed `<site-packages>/uedge/_build_info.json` (AIUE-181) without
  importing `uedge`; FMA contraction = darwin, the last `-O` of `forthon_fopt` then `fargs` at `-O2` or above, no
  `-ffp-contract=off`; no record fails, naming it (D4).
  `run_mutations.py` (`list`: checks the mutation set; `run --out DIR`: one scratch worktree and venv for the run, a
  baseline build that must pass, then per mutation apply, build `--serial`, evaluate the inner-loop family first (a
  miss there stops the mutation) and then every other referenced family, cross-check with `test_default.py`, revert;
  a mutation with `Variant` runs that stored variant in its `Families` instead of the defaults (`_child --variant`:
  its applied value replayed, Store.check under tol_i(variant), that configuration only) with `test_variants.py`'s
  `test_sensitive` as the cross-check there, a `BuildLimitWarning` counting as a failure (selected by its message,
  `build.REPORTED`: pytest's `-W` cannot import `yldot`);
  a range mutation (Check `locality`) also gets the steady part `locality` (`_child --locality`) and
  `test_locality.py`'s `test_locality[<family>]` cases as its cross-check (by node id, `locality_cases`: a `-k`
  expression also selects every `test_locality_variant`, AIUE-101), the others never (owner, 2026-10-22, AIUE-100 D4), and only in families
  with `[locality]` (owner, 2026-10-23, AIUE-92), over the family's column set; every family has one since AIUE-101,
  and both range mutations list the owner families; writes the coverage matrix `matrix.json`/`matrix.md` (a working
  document, not committed) and its four gates (PRD §7.11 c; a run of named mutations evaluates G1 and G2 only);
  `gates DIR`; exit 3 = owner; run at the end of every phase, about 3 min per mutation; a range mutation about
  30 min, its locality runs on the owner families' column sets, macOS arm64, 2026-10-26, AIUE-101).
  `sketch_sensitivity.py` (PRD §7.11 d, AIUE-92): `run <family>... --from-collection DIR | --from-store` per
  sketch-store block the weighted single-entry threshold δ_b/w_i (bisection-checked), R_i = δ_b/(tol_i·w_i) against
  R_max = 2·c·sqrt(N) (a block over it is an owner finding), the worst cell's multiple per region and, with
  `--collections`, the round-off pairs against the bound; `--from-store` uses the stored weights and checks the
  stored thresholds, `--from-collection` weights by 1/tol (exit 2 = harness, 3 = owner).
- **Tolerances** (PRD §7.4, §7.7; AIUE-87): `tests/yldot/tolerances.toml`, generated by `measure_roundoff.py analyze
  --write`: `k`, `rtol_eq` per equation (100 × the largest block-normalised spread over the serial pairs, floored at
  1e-14) with its source, the build records, the pairs, the raw spreads, the floor-report counts, the owner's answers
  and the findings; `families/<f>/sigma.h5` (`/<config>/sigma`, `/<config>/source` = the serial pair that set σ_i, -1
  where σ_i = 0). The Linux side is `tests/yldot/linux/` (Ubuntu 24.04 amd64 by digest, exact apt and pip pins;
  `collect.sh` builds a `git archive` of one commit; `generate.sh`, run from the mounted `tests/`, does the same for
  `make_references.py`, and refuses (exit 2) a build whose extensions call libmvec, AIUE-211). macOS `-O3` is the outlier the serial pairs measure. Since AIUE-92 it covers all eight
  families: `tg` gets its first `rtol` (from large_dd2c) and `up` 1.589e-8 (dnull_imp2's atoms on its wall ring);
  imp7 sets none (`com.redopltvtag = 1`, AIUE-170). Its collections are kept in `../uedge-wt/data/AIUE-92/`.
- **Coverage** (PRD §7.10, AIUE-107) `tests/yldot/tools/coverage.sh` and `coverage_compare.py`: line and branch
  coverage of `bbb/pandf*.F` under the yldot suite. Needs a coverage build of the checkout (`pip install . -C
  "--build-option=--coverage"`, AIUE-105: serial, `-O0 --coverage`; it refuses any other build by its record) and
  gcovr in the venv. `coverage.sh new OUTDIR [--jobs N] [-- PYTEST ARGS]` runs the PR tier, then the nightly tier
  (or only the given arguments) and writes `new.json` (gcovr), `new.txt`, `new.meta` and the JUnit XML;
  `coverage.sh report OUTDIR [--base FILE]` compares it with another run (`coverage_compare.py`: branches taken at
  least once, gcov's "branches executed", the branches only one run takes, mapped to `.m` lines). Facts it relies on
  (AIUE-107 probes, macOS arm64, gcov 15): harness children keep counts only under `YLDOT_START_METHOD=spawn`, which
  it sets (forkserver children leave none); concurrent processes merge `.gcda` counts exactly; it passes no pytest
  `--timeout`, but a harness child timeout still kills a child, which then writes no counts (listed, exit 1);
  locality runs exceed gcovr's 2^32-hit guard with genuine counts (`--gcov-suspicious-hits-threshold 0`); 95.9 % of
  the instrumented `.F` lines map to a `.m` line. Gate result (run `coverage-0745776`, kept in
  `../uedge-wt/data/AIUE-107/`): branches taken, yldot PR + nightly tiers 3081/4580 (67.27 %) against the old suite's
  2665/4580 (58.19 %); the 220 branches only the old suite took (selector values other than one step from a family
  default, and the non-`+input` `ifixsrc`) are AIUE-245. The full run takes about 2.3 h at 10 workers on an M4 Pro.
- **Build flags** (PRD §8) `tests/yldot/tools/build_flags.py`: runs `setup.py` per option set on `linux` and `darwin`
  without building (Forthon's `FCompiler`, `setup()`, `os.system`, the `make` calls, `mppl2f90`, `check_output` and
  `build.run` stubbed; `argv` as pip passes `-C "--build-option=--<opt>"`) and records the `--fargs`/`--cargs` strings,
  `OMPFLAGS`, make's `LDFLAGS`, `OMP` and other changed environment variables, the uedgeC link and compile
  arguments and macros, and the build record `uedgeBuild.run` writes into a scratch `build_lib`
  (`<build_lib>/uedge/_build_info.json`, AIUE-181; `machine` shown as `<machine>`). Its `check_output` answers only the known
  commands (libgcov lookup, the Linux `finclude` lookup (AIUE-211; the directory shown as `<finclude>`;
  `--finclude ANSWER` / `--finclude-fails` give a bad answer), the compiler's `--version`, the record's git
  probes; anything else raises), and `SRCDIR`
  is a scratch tree with an empty `.git` (`--no-git`: without), so a record does not depend on where the evaluated
  `setup.py` lies. It needs setuptools, which a venv of Python >= 3.12 lacks until installed. Not covered: what
  reaches Forthon's real `FCompiler` and its own flags (the record's `forthon_fopt` is the fake's fixed value),
  `-g`/`-t`/`-F`, `--noclean`, `--parallel`, PETSc.
  `tests/yldot/test_build_flags.py` pins that table (27 cases: the default, `--serial`, `--debug`, `--checkbounds`,
  `--noopt`, `--coverage`, combinations, the two refusals, a preset `LDFLAGS`), each with its build record, to
  `v9-develop`'s plus AIUE-211's Linux `-nostdinc -fintrinsic-modules-path <finclude>`, checks that `--coverage`
  changes only its own build, and edits a copy of `setup.py` ten ways (eight flag changes, among them the Linux
  flags dropped, the record dropped, the record without `platform`) to show each is caught;
  `test_finclude_refusal` gives setup.py a relative, missing, spaced and failing `finclude` and requires every
  Linux build to stop with AIUE-211's message and every macOS one to be unchanged; an unedited copy
  must show no difference and `--no-git` must null only the git fields. `test_installed_record` checks the record of
  the UEDGE installed in the running interpreter against its own options (last `-O`, `-fopenmp`, `-nostdinc` exactly
  on Linux, platform, the commit `_provenance.py` reports, loaded by path without importing `uedge`); a UEDGE built
  before AIUE-181 fails it, naming the cause. `test_installed_no_vector_math` counts the `_ZGV` (libmvec)
  symbols of the installed extensions with `nm -D --undefined-only` (`nm -u` off Linux, where the count is 0 by
  construction) and requires none (AIUE-211; Forthon names `-lmvec` on every link, so the symbols are counted, not
  the libraries); it runs on every platform (no skips, `test_inventory.py::test_no_skips`) and fails without `nm`. An intended flag change updates its `EXPECTED`, with the reason in the PR. `build_flags.py --conversion` runs the real
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
  loosening, as a changed σ, since a manifest cannot show it smaller, AIUE-92; a changed or removed
  `<config>/sketch_weight` key is `Default results: changed`, since it changes what every stored variant sketch
  means, AIUE-174; AIUE-101: a narrower `columns`/`variants`, a smaller `sample`, an added `excluded` entry or a
  set `near_margin` loosens, a wider scope or another `seed` is a change; a variant's new locality pattern is a
  change, a changed one `Default results: changed` as `<family>:<id>`, a removed one a loosening, except one that goes
  with its variant's prune or rename with an identical slice, which needs no declaration, AIUE-95 D1; a rename needs
  every compared field, the stored datasets and the locality slice to agree, `rename_differences`; the variant fields,
  the rename check and `overrides.toml` compare values by their canonical JSON text, `same()` as `manifest.runs`:
  -0.0 ≠ 0.0, 1 ≠ 1.0, NaN = NaN, a TOML date by its repr, while `tolerances.toml` and `family.toml` keep `==`,
  owner, 2026-11-10, AIUE-199); it downloads the
  release assets a
  changed manifest names and checks file and dataset SHA-256s. `history` reports the data releases (limit 200 MB), the
  in-git size of `tests/yldot/` (cap 30 MB) and orphan releases. Exit 1 = a declaration missing or a check failed,
  2 = usage. `.github/workflows/reference-guard.yml` (AIUE-104) runs it on every pull request, job `reference guard`
  (CI facts below).
- **Tests** (the whole suite, `-m "not nightly"`: about 5,840 tests, none skipped once the data release stores the
  variant locality patterns (before it, `test_locality_variant` has no parameters), about 17 min, serial build, Darwin
  arm64, 2026-10-24 (AIUE-99; AIUE-101); `-m nightly`: the owner families' variant tests, about 2,880, about 37 min on
  that build, plus since AIUE-101 the owner families' default locality and about 2,900 variant locality tests
  (runtime per shard: the ticket's Validation record)
  and 47 min on `--noopt`, one process; update these figures only when a ticket moves the count or the runtime by more than
  about 10 %, the exact count goes in the ticket's Validation record; about 7 min of the runtime are
  `test_variants.py`, about 250 s the three owner families' `test_states`, `test_index_truth` and `test_history` runs;
  with `-n 8`: 325 s wall on that machine, 2026-10-25, AIUE-103):
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
  synthetic entries (AIUE-100); the owner families' `test_locality` over their column set and
  `test_locality_variant[<family>-<id>]` for every stored variant pattern are `nightly`, and
  `test_locality_everywhere` requires `[locality]` in every family and a pattern for exactly its `variant_scope`
  (AIUE-101);
  `tests/yldot/test_variants.py` every stored SENSITIVE, INERT and INVALID variant of every family whose manifest
  classifies variants, one fresh child each, ids `<family>-<id>` (AIUE-96; PRD §7.2): SENSITIVE replayed against
  its stored reference (`variant_tolerances.check_sensitive`), INERT replayed against the live default within the
  default's tol_i, INVALID re-run with the rules and still INVALID for the same kind of reason (`classify`; a `bounds-check:` entry instead pins its `serial build:` outcome, the class and for INVALID the reason kind, `invalid_problem`, owner D5); an owner
  family's are `nightly` (the variant locality tests are `nightly` for every family, `test_locality.py`); plus `tests/yldot/harness/build.py`'s FMA rule and the installed record (about 4,820 tests in
  the PR tier, about 7 min; on macOS `-O3` two `BuildLimitWarning`s, d_c `bbb.mvolcur` and slab_phi `bbb.icnucx`, and
  in the nightly tier one, dnull_imp2 `bbb.thetar`; none on `--noopt`, AIUE-99);
  `tests/yldot/test_smoke.py` the smoke test, `tests/yldot/test_compare_unit.py` the
  comparator's unit tests, `tests/yldot/test_inventory.py` index truth per family and, from the git-tracked files
  (AIUE-96): every manifest holds exactly `variants.plan()`'s ids with its EXCLUDED ones (an owner family's too,
  since AIUE-99 ended D6's "or none"), a reason on every EXCLUDED, MARGINAL and INVALID entry, every manifest in
  `dumps`'s canonical text (AIUE-190), every tagged input `tests/yldot/harness/state.py` assigns
  EXCLUDED, every `input.py` in normal form (no `restart`, `hdf5_restore`, `exmain`) no skip or xfail under
  `tests/yldot/` (through import aliases too) and no `xerrab` with an empty message in a tracked Fortran source outside
  `grd/` and `flx/` (`git ls-files`; AIUE-239, owner D1), each shown failing on a planted defect, `tests/yldot/test_inputs.py` the
  input inventory, overrides and value rules, `tests/yldot/test_variant_apply.py` variant application and replay,
  `tests/yldot/test_states.py` both states of every family are round-trip fixed points, `tests/yldot/test_history.py`
  `measure_history.py check` per family (about 3 s each) and the `[evaluation]` keys (measured, or the W = P = 2
  placeholders), `tests/yldot/test_store_unit.py` the store, manifest, `fetch_data.py` and `release_data.py` (sketch
  known-answer vector; fakes for `gh` and `git`), `tests/yldot/test_fetch_unit.py` `fetch_data.py`'s HTTPS download
  and `gh` fallback (fakes, no network), `tests/yldot/test_shards_unit.py` the shards (`shards.py`'s list and rule,
  two `--collect-only` shards disjoint with every family test carrying its family, unknown names refused; ~5 s),
  `tests/yldot/test_build_flags.py` the build options' flags and build record (about 5 s, no build; needs a UEDGE built from AIUE-181 on),
  `tests/yldot/test_roundoff_unit.py` `measure_roundoff.py analyze` on synthetic collections,
  `tests/yldot/test_sketch_sensitivity_unit.py` `sketch_sensitivity.py`'s thresholds, bisection, cell multiple,
  round-off ratio and stored-threshold check on synthetic data,
  `tests/yldot/test_make_references_unit.py` `make_references.py` (its child on `d_only` twice, the same bytes; a
  ten-variant sweep with every class as probed, `--only` reproducing the file bit for bit, a nondeterministic second
  run; `--prune` and `--rename` reproducing the expected manifests with the guard needing no declaration, a rename
  with another applied value refused, the audit's override, findings and shards with synthetic audit files and a fake
  runner; `classify` on synthetic results; its refusals, caps and the git/docker commands with fakes; the manifests that
  hold data), `tests/yldot/test_variant_tolerances_unit.py` `variant_tolerances.py` (synthetic sides; a collect and
  a `replay` on `d_only`, `replay` failing on an offset, a NaN and an error),
  `tests/yldot/test_guard_unit.py` the reference guard on scratch git repositories (about 20 s; fakes for the
  downloads and `gh`),
  `tests/yldot/test_tolerances.py` `tolerances.toml` against `sigma.h5` and a live evaluation per family,
  `tests/yldot/test_mutations_unit.py` the mutation set (headers, single-line diffs, `git apply --check` against the
  tree, so a change to a mutated line fails until its patch is refreshed; the composition), the `Variant` key's
  checks and `run_mutations.py`'s verdicts and gates (no build, about 2 s).

## Serial old-vs-new bitwise check (required for Fortran, `.v` and `ppp/` changes)

Every PR that touches Fortran (`*.m`, `*.F90`, hand-written `*.f`), a `.v` file or `ppp/` must show that serial
results are **bitwise** unchanged against `v9-develop`, in the `--serial` build and in the default OpenMP build with
`ppp.OMPParallelJac = ppp.OMPParallelPandf1 = 0`. A suite that compares within tolerances cannot show this.

```bash
python tests/deterministic_omp/harness/serial_check.py \
    --base-python BASE_SERIAL/bin/python --new-python NEW_SERIAL/bin/python \
    --base-omp-python BASE_OMP/bin/python --new-omp-python NEW_OMP/bin/python --jobs 4 --out DIR
```

Four venvs: base and change, each built `--serial` and default, from clean committed trees (the tool does not
build). It runs reproducer presets and yldot family cases (`d_only`, `d_c`, `d_mols`, `ortho`, `slab_phi` and 21
settings variants of `d_only`/`d_mols`, the two drift decks among them; `--list`; AIUE-106) once per build in fresh
processes. Cases ending in `-itN` run N Newton iterations,
so `psetnk`, the ILU preconditioner, Krylov and the line search are covered. It compares every Jacobian, `sfscal`,
`suscal`, `yldot` and the `fnrm` sequence bit for bit.
- Exit 0: identical over the complete gate (both pairs, two different builds from clean committed trees with
  known sources, base on `origin/v9-develop`, `--cases all`).
- Exit 1: mismatch (the summary names the case and the first differing entry).
- Exit 2: harness error (a wrong build kind; same build, tree or clean commit; a record not on the serial path; an
  `-itN` case that did not iterate) or an incomplete gate (`RESULT: INCOMPLETE`; `--partial-ok` for a quick look).

The owner families (`large_dd2c`, `dnull_imp2`, `imp7`) run by name only, after
`fetch_data.py`. Paste the build lines and the `RESULT` line into the PR. Details:
`tests/deterministic_omp/README.md`.

## Fast iteration: subset while working, full matrix once

Builds and test matrices were the longest waits of epic AIUE-8 (one ticket 5.7 h, a cost study 2.1 h). While working:

- **Iterate on a subset**: one case (the reproducer preset or the one family case the change touches) at **two
  thread counts** (e.g. 1 and 4 for OpenMP work), and the one suite the change can affect.
- **Run the full matrix once**, at the end (`validate`, the serial bitwise check, the OpenMP flow), not after every
  edit. A failure there sends you back to the subset with the failing case added.
- **Prefer CI for heavy matrices**: push the branch and let `build-test-omp.yml` run its PR set (about 12 min on
  native `ubuntu-24.04`) instead of an emulated or many-thread local matrix; quote its result.
- **Reuse builds**: one base venv per build kind (`--serial`, default OpenMP) per branch point, built once from a clean
  committed `origin/v9-develop` tree and shared by the tickets based on it (read-only: never reinstall into it); each
  ticket worktree keeps its own venv for its own build and rebuilds only when its sources changed. Name base venvs by
  their commit, `uedge-wt/venvs/base-{serial,omp}-<sha>`, so a stale one is visible; build a new pair when
  `v9-develop` moves past it. Base worktrees `uedge-wt/base-<sha>` and their venvs are shared across sessions:
  closing a ticket never removes them; they go once `v9-develop` has moved on and no worktree is based on them.
  Before building a base, look for its `BUILD.txt` and for a build still running in it (`ps`), so two sessions
  never build the same base at once (AIUE-161 and AIUE-181 built `base-1c3010e` together, and AIUE-161's close-out
  removed it while AIUE-181's `BUILD.txt` still named it).
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
    compiler: a libomp clang (`CC=$(brew --prefix llvm)/bin/clang`) or `CC=gcc-15` (before AIUE-212 it also needs
    `CFLAGS="-std=gnu17 -Wno-error=incompatible-pointer-types"`, which built `base-omp-0480272`). Record the one used
    next to the base venv. The serial build has not needed a `CC` since AIUE-109 (62ac2b1).
- **Probing initialisation without a solve** (grid-change interpolation, `ueinit` checks): after the restore and the
  input changes, `bbb.ifexmain = 1; bbb.allocate(); bbb.ifexmain = 0; bbb.ueinit()`. A Python `allocate()`
  (`ifexmain = 0`) sets `nxold`/`nyold` to the current size, reallocates `Interp` and sets `isimesh = 1`
  (`bbb/odesetup.m:531-536`, AIUE-141). The next `ueinit` then copies the saved state as it is: a restore after the
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
assignments in `bbb/exmain.c:71,117` hard errors on every commit before AIUE-212. Build each bisect step with

```bash
CC=gcc-15 CFLAGS="-std=gnu17 -Wno-error=incompatible-pointer-types" OMP_NUM_THREADS=1 \
    pip install -v --no-build-isolation .     # add -C "--build-option=--serial" from d32c88b on
```

(as a script file: the permission check refuses `VAR=… cmd` prefixes, `CLAUDE.md` → Gotchas). Mark a step whose build
fails `git bisect skip`; without these flags a whole range is skipped and the bisect stalls at "N revisions left".

## Retired suite (`pytests` branch)

The old regression suite lives on the fork's `origin/pytests` branch (last commit f695acd; v9's references and their
reasons in `V9_REFERENCE_CHANGES.md` there). It evaluated 157 cases from a stored, perturbed state and compared the
residual `fnrm` per equation against references at `rtol=1e-5`. Nothing in this repository runs it, and no skill or
agent names it since AIUE-108. Its last full run (serial build of `v9-develop` c82a515, 2026-10-21) gave 157 passed
(D_only 125, D+C 1, D_mols 27, slab_D_only 1, fulltests 3); AIUE-107 ran it once more, for the coverage comparison
(`-O0 --coverage`, 0745776, 2026-11-10; Coverage, below), also 157 passed, and retired it.

## CI facts / quirks

- **An AI-layer-only change runs no tests** (owner, 2026-10-28): `build-test-wheel.yml` and `build-test-omp.yml` have
  `paths-ignore` on `push` and `pull_request` with the process paths of `.claude/hooks/change_kind.py` (`PROCESS`:
  `CLAUDE.md`, `.mcp.json`, `.claude/**`, `.githooks/**`, `.github/workflows/claude-*.yml`), and `nightly-tests.yml`
  has them on `pull_request` together with `docs/**`, `doc/**` and `**/*.md` (AIUE-104); keep the four lists in
  step. One product file in the change runs everything; tag pushes, the nightly schedule and dispatches are
  unaffected. Such a PR still gets `claude-context-drift.yml`, `claude-review.yml` and the reference guard. A required
  check whose workflow a path filter skips stays pending and blocks the merge, so the one workflow meant to be
  required, `reference-guard.yml`, has no path filter.
- **The reference guard in CI** (AIUE-104, ticket page 5111855): `.github/workflows/reference-guard.yml`, on
  `pull_request_target` (opened, synchronize, reopened, edited; any base branch), job name `reference guard` (the
  required-check context: rename it only together with the ruleset). GitHub takes a `pull_request_target` workflow
  and its checkout from the default branch (since 2025-12-08, GitHub changelog 2025-11-07), so `v9-develop`'s copy of
  the guard judges every PR, a stacked one too, and a PR that changes the guard or this workflow is judged by the
  old copy (its own change first runs on the next PR). It fetches `refs/pull/<n>/head` as data (never checked out),
  passes the description as `PR_BODY` and `GH_TOKEN` through `env:` only, caps files at 200 MiB (`ulimit -f`), and
  runs `check --base <base sha> --head <head sha>`; its check run lands on the PR head commit. `[skip ci]` does not
  skip it (it skips `push`/`pull_request` only). `.github/CODEOWNERS` names the owner for `tests/yldot/`,
  `.github/workflows/` and itself. Owner decision D1 (2026-10-28), applied 2026-11-10: two rulesets on `v9-develop`.
  A (`v9-develop guard`) requires the `reference guard` check, with no bypass. B (`v9-develop code owners`) requires
  one approving review and code-owner review, and lets the admin role bypass it on a pull request. Every PR the owner
  opens, including those Claude opens through `gh`, merges only through that bypass, which GitHub records. B first had
  0 required approvals and then demanded nothing on the owner's own PRs (test PR #86: `CLEAN`, `reviewDecision`
  null), hence 1 (owner, 2026-11-10).
- **The yldot nightly tier** (AIUE-104): `.github/workflows/nightly-tests.yml` on `schedule` (04:43 UTC, default
  branch), `pull_request` (path filter above) and `workflow_dispatch`. It builds the serial wheel as
  `build-test-wheel.yml` does and runs `pytest tests/yldot -n auto --dist worksteal -m nightly --yldot-shard <shard>
  --timeout 1800` per shard; large_dd2c and dnull_imp2 run as two legs with complementary `-k` expressions
  (`locality-gip`: 11 locality tests; `rest`: the other 970 and 967), imp7 as five (`locality-g` 5, `locality-ip` 6,
  `locality-u` 4, `locality-en` 5 incl. the base test, `rest` 961), 15 legs in all. `common` has
  no nightly test, and its exit 5 is accepted (a family shard's is not). `--dist worksteal` is needed: xdist's
  default schedule first hands each worker a run of consecutive tests, which put all 20 imp7 locality tests (6-7 min
  each) on one worker (imp7 shard, macOS arm64 `-n 4`, 2026-10-28: 7303 s with `load`, 2314 s with `worksteal`).
  Budget: ≤ 60 min wall (PRD §7.9). A locality test's time on the 4-core runner varies with the runner's hardware:
  large_dd2c 740 s then 450 s, dnull_imp2 490 s then 600 s, imp7 850-900 s then 1255-1267 s (runs 42718886354 and
  42739703331, 2026-11-09/10: 72 min with large_dd2c as one leg, 63.7 min with imp7 as two legs of 3 rounds each),
  hence the splits. With 15 legs the run took 41.7 min (run 42747608872, slowest leg imp7/locality-ip 39.6 min).
  Each leg logs its runner's CPU model: that run drew six (AMD EPYC 7763, 9V74, 9V45; Intel Xeon 8370C, 8573C,
  6973P-C), and the slowest test, imp7 `methi=44` at 1488 s on a Xeon 8370C, is only 1.2× under `--timeout 1800`
  (owner: keep 1800, 2026-11-10; a timeout goes back to the owner).
- `build-test-wheel.yml` runs the yldot PR tier (AIUE-103; owner, 2026-10-25, ticket page 5308442): `build-serial`
  builds the `--serial` wheel once (`pip wheel`, Python 3.11, `numpy==1.26.4`, `runs-on: ubuntu-24.04`, not the
  AIUE-98 image: D1) and lists the shards with `tests/yldot/tools/shards.py`; nine `yldot-pr-tier` legs (one per family plus
  `common`, 4 vCPU each) install the wheel with the `test` extra, restore `tests/yldot/.data` from `actions/cache`
  keyed by the manifests, run `tests/yldot/tools/fetch_data.py` (D2: it re-hashes every cached file) and
  `pytest tests/yldot -n auto -m "not nightly" --yldot-shard <shard>` (D3). The references are built in the pinned Linux
  image (`tests/yldot/linux/`), so the tier passes by tolerance, not bit for bit. It does not exercise
  OpenMP. The wheel jobs need the tier and run only on pushes to `v9-develop`, `main` and tags (D5; their matrix
  still names the retired `macos-13`); `gather_wheels` takes only the `cibw-*` artifacts.
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
- `.github/workflows/regenerate-references.yml` (AIUE-98) makes the yldot data releases: `workflow_dispatch` only
  (inputs `from_commit`, `families`, `mode` sweep/only/locality-only/prune/rename/defaults-only (prune and rename,
  AIUE-95; sweep, only and rename run the audit, so `generate.sh` builds twice), `only`, `rename` (OLD=NEW pairs),
  `publish`, `expect_ref`,
  `note`, `cpu`: a case-insensitive `grep -E` pattern, default empty, any CPU (`intel` before AIUE-211); `generate`'s first
  step logs the runner's CPU model and stops unless it matches; imp7's full sweep, a single process, takes about
  3.3-4 h on an AMD 9V45 or Intel 6973P-C runner and an estimated 6-7 h on a 7763, 9V74 or 8370C, past the job's
  350-minute limit, so it is dispatched alone with `cpu: "9V45|6973P"` and dispatched again after a refusal,
  AIUE-211; an `--only` dispatch is not cheap either: it re-runs each owner family's default and its stored variant
  locality patterns (only `--prune` and `--rename` copy them, `tests/yldot/tools/make_references.py:601`), so run
  42760918518 (`--only bbb.newapi` on d_c, large_dd2c and imp7, AMD EPYC 7763) spent 9315 s in large_dd2c's children
  and 18549 s in imp7's (22 evaluations each) and took 316 of the 350 minutes: dispatch imp7 alone when another owner
  family shares the job, AIUE-242), three
  jobs on `ubuntu-24.04`. `gate` refuses a publish unless the dispatched commit is the head of an open PR into
  `v9-develop` or in it, tip or earlier (`release_data.py --gate`; PRD §7.3's "v9-develop itself" read as its
  history), and `from_commit` is empty or that commit. A dispatch runs the dispatched branch's own copy of the
  workflow and of `release_data.py`, so the gate catches mistakes, not a branch that edits it: the owner's approval in
  `yldot-data` is the control, and the approver reads the run's diff of `.github/` and `tests/yldot/tools/` first. `generate` (350 min) runs
  `make_references.py generate` in `yldot-linux:24.04`, pulled from `ghcr.io/holm10/yldot-linux` by its digest
  `sha256:2f833938…` with Docker's containerd image store, so `.Id` is the digest the manifests' `runner_image`
  records, and fails on any other id (owner D1: never rebuilt in CI, a rebuild on 2026-10-25 gave another id and a
  drifted unpinned `zlib1g`); with publish `--release <provisional> --write`, with `expect_ref` it compares each
  `references/<f>.h5`'s SHA-256 with that ref's manifests (a reproduction check). `publish` runs in the environment
  `yldot-data` (required reviewer the epic owner, self-review allowed, branches `v9-develop`, `feature/v9-*`,
  `bugfix/v9-*`) and the concurrency group `yldot-data-release` (one running and one pending: a third queued publish
  cancels the pending one; N follows the order in which publish jobs enter the group, not the dispatch order: in
  AIUE-98's A4 the second dispatch generated first and got v11, the first was renumbered to v12), runs `release_data.py --generated --renumber --publish` and uploads the renumbered
  manifests as the artifact `yldot-manifests-<tag>`, which the developer commits as a data-only commit (owner D2: the
  workflow never pushes; a `GITHUB_TOKEN` push runs no CI). The only `contents: write` in `.github/workflows/`.
- `@notest`/`@nowheel` commit tags are inert (no job `outputs:` on `check-requests`; `wheel` vs `wheels` mismatch).
  The tags are read only from message lines that start with `#` (`#@notest @nowheel`), so a squash title's `(#N)` and
  its `Co-Authored-By` addresses are not tags (AIUE-175). Tags apply to push runs only: a `pull_request` run checks out
  GitHub's merge commit (depth 1, so `--no-merges` keeps it) and reads its "Merge … into …" message.
- There is no BASIS CI. `build-basis.yml` was removed (AIUE-178, owner 2026-10-23): its `fusionbillm/basisuedge` image
  built LLNL/UEDGE's branch of the same name, never the fork (LLNL `master` for a branch upstream lacks; on
  `v9-develop`, LLNL's `v9-develop`, which fails in BASIS make on `bbb.pack`). A `#@nobasis` tag has no effect.
- `claude-review.yml` runs `/code-review` on PR open or `@claude-review` comment.
