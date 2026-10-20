# Reference changes for UEDGE v9

This branch is the `pytests` branch of the v9 fork (`holm10/UEDGE_v9_dev`). It started from LLNL's `pytests` at
`b535508`. This file lists every stored reference that differs from LLNL's, so the changes can be merged into
LLNL's `pytests` branch once the v9 code they depend on is merged into LLNL UEDGE. Until then LLNL UEDGE reproduces
the old references, not these.

Each entry gives the case, the old and new `fnrm` of `pytests/default`, the code change that moved it, who decided it
is intended, and how it was regenerated.

## How references are regenerated

`tools/rereference.py <case dir>` regenerates the reference of one existing case. It does what
`MakeTests.execute_case` does but keeps the stored solution. Two `MakeTests` behaviours make the full regeneration
unsuitable for one case:

- `MakeTests.make_unittests` deletes and rebuilds the whole test directory.
- `write_data` perturbs `solution.h5` again with unseeded random numbers.

`rereference.py` replaces `TestClass.perturb_solution` with a no-op, rebuilds only the `pytests` group and compacts the
file. It exits with status 1 if anything outside `pytests` changed: the perturbed state `bbb`, `com` and every other
group and attribute stay identical.

Method check: run with LLNL UEDGE 8.1.2.post1 (PyPI) on a copy of `tg_atom_cftiexclg0p5`, it reproduces the old
reference to -1.7e-9. Run with v9 on `default`, it reproduces what the test computes there.

The shapes of some stored diagnostic variables follow the build used. In v9, `conx` is indexed by species,
`(nx, ny, nisp)` instead of `(nx, ny)`. These variables are compared only in the failure diagnostics of
`test_reference`, not in the `fnrm` check that decides pass or fail. A v9 reference read by LLNL UEDGE, or the reverse,
can therefore stop with a shape error in those diagnostics after the `fnrm` check has already failed.

## Changes

### `pytests/unittests/D_only/nonog/tg_atom_cftiexclg0p5` (2026-10-19, Jira AIUE-116)

- **fnrm**: 1.593087301907699 (LLNL, `53243de`) → 1.5884862764139387 (v9), relative change -2.888e-3.
- **Why**: the molecular CRM rewrite of the v9 fork (2025-02-03/04, between `47d7423` and `412b0cd`; candidates
  `f5bd464` "Adds CRM and fixed-fraction structures to bbb" through `412b0cd` "Fixes CRM mol.-related bugs"). There
  `psordis` became species-indexed, `psordis(ix,iy,ifld)`, and the dissociation drift-heating term
  (`cfnidhdis`) moved from the ion energy equation to the gas energy equation (`bbb/pandf_gas_energy.m`). This case
  is the one D_only case that sets `cfnidhdis = cfnidhmol = cfnidhgy = cfnidhg2 = 1`, `cfdiss = 1`, `cftiexclg = 0.5`
  and `istgon(1) = 1`.
- **Decision**: the code owner confirmed on 2026-10-19 that the rewrite is the intended physics (AIUE-116).
- **Regenerated with**: the v9 serial build (`--serial`) of `origin/v9-develop` `0480272` plus the AIUE-116 fix
  (`d4e53db` on branch `bugfix/v9-AIUE-116-dnonly-nonog-refs`), on macOS arm64, Python 3.13, Forthon 0.10.10, numpy 2.5.4:
  `python tools/rereference.py pytests/unittests/D_only/nonog/tg_atom_cftiexclg0p5`.
- **Consolidation**: take this reference into LLNL `pytests` together with the CRM changes. Without them, keep LLNL's.

### Not changed: four cases that failed on v9 because of code bugs (AIUE-116)

`concap`, `ineudif0`, `ineudif1` and `ineudif3` in `D_only/nonog` also failed on v9. The cause was in the code, not in
the references, so their references are unchanged. The fix is on the v9 branch named above:

- `logte`/`logti`/`logng`/`logtg` (nonorthogonal precompute, v9 `6335b06`, `7d8a56c`, `dc263a4`) were refreshed only
  where the variable is evolved.
- `tiave` was read uninitialised under `concap = 1` (a latent bug, also in LLNL).
