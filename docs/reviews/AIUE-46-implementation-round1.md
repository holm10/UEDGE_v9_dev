# AIUE-46 — Commit the OpenMP reproducer case — implementation review, round 1

Branch `feature/v9-AIUE-46-omp-reproducer-case` (a61a145, 483d57a), base `origin/v9-develop` 3865c79.
Reference: the ticket's acceptance criteria and `.claude/plans/AIUE-46-omp-reproducer-case.md` (no physics spec).

## Verdict

**APPROVE**. There are no BLOCKER or MAJOR findings. The eight MINOR findings below are optional.

## Summary

The branch commits the owner's deck, grid, `mist.dat` and scripts byte-for-byte. Only the rate-directory lines of the
deck changed. `b0p1.hdf5` and `save_input_mod4.h5` are trimmed to exactly the datasets that the deck and
`hdf5_restore` read, and every kept dataset is byte-identical to the original. I reproduced the bitwise-equality claim
myself, comparing the owner's *untouched* deck with the original data (rate files read from cwd, the way the owner ran
it) against the committed deck with the trimmed data, in a fresh clone. All six configurations matched, on both the
`--serial` and the OpenMP build. The rate-file deviation from the PRD is sound: the repository copies are byte-identical
to the owner's, and results do not depend on where the files are read from. No product code, skill, agent or hook
changed, the code-facts edits are accurate, and `check_context_refs.py` is clean. The remaining issues are README and
validation-record accuracy: one claim (SIGBUS without `OMP_STACKSIZE`) did not reproduce, and the default rate path
fails in checkouts deeper than the 120-character limit allows.

## Findings

### BLOCKER

None.

### MAJOR

None.

### MINOR

**I1-m1 — README: the SIGBUS claim did not reproduce.** `tests/deterministic_omp/README.md`, Environment table,
row `OMP_STACKSIZE=512M` ("Without it the OpenMP Jacobian crashes with SIGBUS on this case").
*Evidence:* on `venvs/base-omp`, with `OMP_STACKSIZE` unset (`ulimit -s` 8176 KB), every run below exited 0 with no
SIGBUS:
- Te box with `--omp-jac` and 4 threads;
- full problem with `--omp-jac` and 4 threads;
- full problem with `--omp-jac` and 8 threads;
- full problem with `--omp-jac` plus `ppp.OMPParallelPandf1=1` and 4 threads (iteration-0 `fnrm` 1.535419111648367
  and 1.535419111648429).

The claim comes from PRD §6.3 (planning run, possibly the April beta build). Setting the variable is harmless, and the
top-level `README.md:103` recommends 2G.
*Resolve:* reword the row, for example "set it; a SIGBUS at the default stack was seen during planning (PRD §6.3),
not reproduced at `0fac655` with 4 or 8 threads". Alternatively, reproduce the crash and name the configuration.

**I1-m2 — The default rate path fails in deep checkouts.** `case/input_mod4.py:8-15`. The default is an absolute path,
so the 120-character check rejects any checkout whose `…/builder/test/Forthon_cases/Forthon_case5` is longer than 120
characters.
*Evidence:* a clean clone under the session scratchpad (168 characters) fails at import with "Rate directory path
longer than 120 characters". The error is loud and correct, but the in-tree default then doesn't work. Typical paths
(the worktrees, GitHub runners) are about 66–90 characters, so it only bites deep checkouts.
*Resolve (either):*
- fall back to `os.path.relpath(_rates_dir)` when it is shorter. Fortran opens relative to cwd, and the deck must be
  run from the case directory anyway;
- or say in the README that a relative `UEDGE_OMP_RATES_DIR` (for example `../../../builder/test/Forthon_cases/Forthon_case5`)
  works around the limit.

While there, note in the README that the case depends on the legacy `builder/test/Forthon_cases/Forthon_case5/`, so a
future `builder/` clean-up knows about the dependency.

**I1-m3 — `fingerprint.py`: the `yldot` digest is not the `exmain` residual.** `tools/fingerprint.py:47-57`. The dict
literal evaluates `bbb.get_fnrm(bbb.dtreal)` before `digest(bbb.yldot[:neq])`. `get_fnrm` (`bbb/ext_neutrals.m:1169-1191`)
calls the serial `pandf(-1,-1,…)`, which overwrites `yldot`, and it also leaves `dtuse` changed. The hashed `yldot` is
therefore the serial `pandf` residual at the final state, and `--omp-jac` cannot reveal parallel-RHS differences in
it. Note the 3/3 identical `yldot` digests in the OpenMP runs of the validation record; I reproduced the same digest
`7e6456…`. This is harmless for the trim proof, but the docstring and README describe it as the evaluation's `yldot`.
*Resolve:* hash `yldot` before calling `get_fnrm`, or document what is hashed. Carry the point into AIUE-49's harness
design.

**I1-m4 — Validation record: not reproducible as written, and the size block is wrong.**
`docs/reviews/AIUE-46-validation.txt`.
- The command line names `/private/tmp/claude-501/…/scratchpad/trimcheck.sh`, which nobody else has.
- The "Sizes" block is an `ls` of a scratch directory. It lists `__pycache__` (not committed) and omits `mist.dat`
  (committed), although its "4.5M total" includes it.
- The strongest evidence, byte equality of every kept dataset, is not recorded.

*Measured:* `git ls-files tests` totals 4 697 611 bytes (4.48 MiB). The branch adds 4 718 172 bytes of blobs, 1 737 151
compressed on disk. 21 of 21 datasets in `b0p1.hdf5` and 7 of 7 in `save_input_mod4.h5` are byte-equal to the
originals.
*Resolve:* inline the loop (or describe it), report the committed size from `git`, and add the dataset-level check.

**I1-m5 — README: the grid size is stated with guard cells.** README, "The case": "72×44 grid". The saved state has
`com.nx=70`, `com.ny=42`; 72×44 is the array shape including guard cells (`neq = 14·72·44 = 44352`). UEDGE users read
"nx×ny" as 70×42.
*Resolve:* write "70×42 (72×44 with guard cells)".

**I1-m6 — README: say which build each command needs.** `--omp-jac`, `testscript*.py` and `comp*.sh` set
`ppp.OMPParallelJac=1`. On a `--serial` build that stops with `xerrab("UEDGE was not compiled with OpenMP…")`
(`ppp/omp_parallel.F90:290-292`).
*Resolve:* one sentence in "Running it".

**I1-m7 — Provenance of the trimmed data is not recorded.** The trim drops the original root and group attributes:
UEDGE `8.1.2-beta.0` wrote the state, UETOOLS 1.3.3rc3, `casename`, `ctime`. Dropping the user, host and path
attributes is reasonable. Nothing in the tree records the SHA-256 of the two original files, so nobody can later
re-verify the trim against the owner's originals.
*Resolve:* add the original SHA-256 values and the writing UEDGE version to the README or the docstring of
`trim_case_data.py`.

**I1-m8 — `trim_case_data.py`: the docstring misstates how `hdf5_restore` treats `tipers`.** The docstring says
"tipers only if bbb has it and the file has it". `hdf5_restore` (`src/uedge/hdf5.py:35-38,72-76`) appends `tipers`
whenever `bbb` has it, and then *raises* if the file lacks it. This is moot today: v9 `bbb` has no `tipers`, and the
original save file has none.
*Resolve:* correct the sentence.

## Status of previous findings

Not applicable (round 1).

## Assessment of the rate-file deviation (as requested)

The deviation is sound.

- **Byte-identical.** `cmp` shows both `builder/test/Forthon_cases/Forthon_case5/ehr2.dat` and `C_rates.adas` are
  identical to `/Users/holma/Documents/uedge/rates/{aph/ehr2.dat,api/C_rates.adas}`. All six tracked copies of
  `ehr2.dat` in `builder/` are identical too.
- **Only these files are needed.** `istabon=10` reads only `ehr2.dat` (`aph/aphread.m` 9/10 branch, through
  `findFile`, which falls back to `data_directory` and then cwd). `ismctab=2` reads `TRIM(apidir)//'/'//mcfilename`
  (`api/fimp.m:296-298`). `mist.dat` is opened as `coronalimpfname` relative to cwd (`api/apip93.m`,
  `com/com.v:322`), which is not affected by `apidir`.
- **Results don't depend on the location.** The owner's untouched deck (`aphdir` commented out, `apidir="."`, rate
  files in cwd) gives fingerprints bitwise equal to the committed deck reading `Forthon_case5`.
- **Path length.** `aphdir` and `apidir` are `character*120`. The `> 120` check is correct, since exactly 120 fits.
  Internally `basfilex` expands into 500-character buffers, and `readmc` concatenates inline in the `open`. See I1-m2
  for deep checkouts.
- **Deck copied out of tree.** Without the variable it fails loudly ("Rate file ehr2.dat not found in …"). A bad
  variable, or a directory missing one file, also fails loudly; I tested all three. The README tells users to set the
  variable when copying.

## What was checked and how

- **Diff and scope.** `git diff origin/v9-develop...HEAD`: 18 files, all under `tests/deterministic_omp/`,
  `docs/reviews/`, `.claude/plans/`, `.claude/context/testing.md` and `CLAUDE.md`. No Fortran, `.v` or `src/uedge`
  file changed. No skill, agent, hook or settings file changed. `.claude/plans/` is an artifact per `branching.md:13`.
  The code-facts commit carries `AI-layer: code-facts`.
- **Fidelity to the owner's files.** `diff` against `/Users/holma/Documents/uedge/src/UEDGE_v9_dev/tests/deterministic_omp/`:
  `testscript{,1,2}.py`, `comp{,_jac}.sh`, `mist.dat` and `gridue.hdf5` are identical. `input_mod4.py` differs only
  in `import os` and the rate-directory block that replaces the two commented-out `/Users/rognlien1/…` lines. The
  physics settings are unchanged. No user-specific paths are left in the committed files; I grepped for
  `Users/`, `/home/`, `rognlien` and `holm10` and inspected the HDF5 attributes.
- **Excluded files.** `git check-ignore` covers `to_tom/`, `testjac.hdf5`, `firstjac*`/`secondjac*`, `run*.txt`,
  `log.txt`, `__pycache__/` and `fingerprint.json` (local `.gitignore`), plus `*.swp` and `.DS_Store` (root
  `.gitignore`). None of them is tracked.
- **Trim completeness.**
  - Walked both original HDF5 files with h5py.
  - The deck reads `restore/bbb/{ngs,nis,phis,tes,tgs,tis,ups}`, which exists in both originals, so the `bbb/`
    fallback is never taken. It also reads nine optional `diffusivities/bbb/*` keys; the whole `diffusivities/` group
    is kept.
  - `hdf5_restore` takes the `bbb/` branch, since the original `save_input_mod4.h5` has no `restore` key. It reads
    `tes,tis,ups,nis,phis,ngs` plus `tgs`, and `tipers` only if `bbb` has it, which v9 doesn't (grepped `bbb/bbb.v`).
  - Every kept dataset is byte-equal to the original (dtype, shape, `tobytes()`): 21/21 and 7/7.
  - Re-running `tools/trim_case_data.py` on the originals reproduces both committed files byte for byte.
- **Clean checkout.** `git clone --depth 1 --branch feature/v9-AIUE-46-omp-reproducer-case`, once into the scratchpad
  and once to a short path (a symlink doesn't help, because `getcwd` resolves it). I ran the Te box in-tree with
  `env -u UEDGE_OMP_RATES_DIR -u PYTHONPATH OMP_NUM_THREADS=1 HOME=<empty dir> python -I ../tools/fingerprint.py --tebox`.
  It exited 0, its fingerprint equals the validation record's Te-box line, and `git status --ignored` shows only the
  ignored `__pycache__/` and `fingerprint.json`.
- **Independent bitwise proof** (my own script, fresh `python -I` process per run, `OMP_NUM_THREADS=1`, empty
  `HOME`). A = the owner's untouched deck + original data + rate files in cwd. B = the committed deck + trimmed data
  from the clean clone + `UEDGE_OMP_RATES_DIR`.

  | Build | Configuration | Fingerprint | Printed `iter=` lines |
  |---|---|---|---|
  | `--serial` | full problem (`ftol=1e20`) | identical | identical |
  | `--serial` | Te box | identical | identical |
  | `--serial` | `itermx=3` | identical | identical |
  | OpenMP, `OMPParallelJac=0` | full problem | identical | identical |
  | OpenMP, `OMPParallelJac=0` | Te box | identical | identical |

  The values also equal the validation record and the README reference table: `fnrm` `0x1.eb37d428ec4f0p+0`,
  `0x1.49db83f93d961p-2` and `0x1.c32f8166a1af7p+0`, `neq`/`nnz` 44352/3190290 and 25/169, and the four `itermx=3`
  `fnrm` values.
- **Reproducer still reproduces.** OpenMP build, Te box, `--omp-jac`, 4 threads: `nnz` 179 and 181 and `fnrm`
  0x1.69…p-3 and 0x1.29…p-3, against serial 169 and 0x1.49…p-2. Full problem: iteration-0 `fnrm` 1.535419111648367
  against serial 1.918820629111277. This matches PRD §6.3.
- **README claims.**
  - `Nthreads` clamp: `ppp/omp_parallel.F90:296-303`.
  - `-I` drops the script directory (Python 3.13, `-I` implies `-P`).
  - The `int_handler()` prototype in `bbb/exmain.c:33,71,117` is consistent with the C23 incompatible
    function-pointer failure.
  - `/opt/homebrew/opt/llvm/lib/libomp.dylib` exists.
  - The file sizes match.
  - `h5py` is a declared dependency (`pyproject.toml:18`).
  - `.gitattributes` has no eol or filter rules affecting `mist.dat` or the HDF5 files.
  - The `OMP_STACKSIZE` claim did not reproduce (I1-m1).
- **AI layer.** `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` (from the worktree) prints
  the informational list and then `OK`, exit 0. The `testing.md` lines 3 and 7-8 and the `CLAUDE.md:38` edits are
  accurate. No other `CLAUDE.md` or `.claude/` text says the repository has no tests; I grepped for "no tests", "not
  in this repo" and `tests/`.
- **Cleanup.** I removed the short-path clone I made in `/tmp`. The scratch runs are under
  `/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev/`.
