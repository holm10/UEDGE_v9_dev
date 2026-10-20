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

The shapes of some stored diagnostic variables follow the build used. In v9, `conx`, `cony`, `flox` and `floy` are
indexed by species, `(nx, ny, nisp)` instead of `(nx, ny)`. These variables are compared only in the failure diagnostics of
`test_reference`, not in the `fnrm` check that decides pass or fail. A v9 reference read by LLNL UEDGE, or the reverse,
can therefore stop with a shape error in those diagnostics after the `fnrm` check has already failed.

## Changes

### `pytests/unittests/D_only/nonog/tg_atom_cftiexclg0p5` (2026-10-19, Jira AIUE-116)

- **fnrm**: 1.593087301907699 (LLNL, `3adf4c9`) → 1.5884862764139387 (v9), relative change -2.888e-3.
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

### `pytests/unittests/D_mols/nonog_mols`, all 27 cases (2026-10-19, Jira AIUE-116)

- **Why**: the v9 molecular CRM work. `f5bd464` (2025-02-03) added `ismolcrm` with default 0. `174ce09` (2025-04-09,
  "Implements new molecular BCs") made 1 the default, i.e. CRUMPET molecular rates. The same commit changed the
  molecular boundary conditions and the albedo coupling of the atom BCs, and set `tha2molfrac` (fraction of thermal
  atoms converted into molecules) to 1. Every D_mols case runs with `ishymol = 1`, so all of them switched model. That
  is most of the change: with `ismolcrm = 0` set by hand, v9 comes back to within |relerr| 1.1e-4 to 3.9e-2 of the old
  references (median 1.7e-3; `default` 1.7e-3). The remainder probably comes from the other changes in `174ce09` and
  from the Feb-2025 CRM rewrite, which also changed the old-model path; it was not bisected. LLNL UEDGE 8.1.2.post1
  reproduces all 27 old references to 1.3e-4 or better.
- **Decision**: the code owner decided on 2026-10-19 that the molecular model is experimental, and that the
  references are regenerated to pin the current v9 results, so that any further drift shows up (AIUE-116).
- **Regenerated with**: the same build and tool as above, one case per process:
  `python tools/rereference.py pytests/unittests/D_mols/nonog_mols/<case>`. The stored perturbed states are
  unchanged. The new values equal those of `origin/v9-develop` `0480272` without the AIUE-116 fix, which does not
  touch these cases.
- **Consolidation**: take these references into LLNL `pytests` only together with the CRM changes and `174ce09`
  (the `ismolcrm = 1` and `tha2molfrac = 1` defaults and the molecular BCs).

| Case | Old fnrm (LLNL, `53243de`) | New fnrm (v9) | Relative change |
|---|---|---|---|
| `default` | 0.9956834885777706 | 2.4165856501082246 | 1.427e+00 |
| `tg_mol` | 1.4371343141840676 | 2.655413635618425 | 8.477e-01 |
| `tg_mol_atoms` | 1.796947602990362 | 2.851112085691976 | 5.866e-01 |
| `tg_mol_atoms_drift` | 2.4771906307996976 | 3.326002119527775 | 3.427e-01 |
| `tg_mol_drift` | 2.071165003613655 | 3.039708834005094 | 4.676e-01 |
| `tg_mol_istgcore0` | 0.7356807042789251 | 2.322505810954956 | 2.157e+00 |
| `tg_mol_istgcore1` | 1.2288837648858524 | 2.53955192681687 | 1.067e+00 |
| `tg_mol_istgcore3` | 0.7830601105640581 | 2.3585059106845847 | 2.012e+00 |
| `tg_mol_istglb1` | 1.0542137655625046 | 2.5025415218989298 | 1.374e+00 |
| `tg_mol_istglb3` | 1.2190588909416398 | 2.521786713339314 | 1.069e+00 |
| `tg_mol_istglb4` | 1.4366641885636462 | 2.646568348423765 | 8.422e-01 |
| `tg_mol_istglb5` | 0.7374728277156534 | 2.3522852410900557 | 2.190e+00 |
| `tg_mol_istgpfc1` | 0.7690034562493293 | 2.3476513116072724 | 2.053e+00 |
| `tg_mol_istgpfc2` | 1.217455441234412 | 2.5131903496637467 | 1.064e+00 |
| `tg_mol_istgpfc3` | 0.7352299984721656 | 2.347125463130269 | 2.192e+00 |
| `tg_mol_istgpfc4` | 0.979919179982161 | 2.4168479496420243 | 1.466e+00 |
| `tg_mol_istgpfc5` | 0.9881789393183934 | 2.435321744077122 | 1.464e+00 |
| `tg_mol_istgrb1` | 0.9838675167983466 | 2.3973244187222726 | 1.437e+00 |
| `tg_mol_istgrb3` | 1.2341800201690731 | 2.5447160316104633 | 1.062e+00 |
| `tg_mol_istgrb4` | 0.1612960153315849 | 2.2138327195259 | 1.273e+01 |
| `tg_mol_istgrb5` | 1.0003868169016361 | 2.4588476138394557 | 1.458e+00 |
| `tg_mol_istgwc1` | 0.9894915582694082 | 2.422731327431701 | 1.448e+00 |
| `tg_mol_istgwc2` | 0.7803826255469875 | 2.3537342401864225 | 2.016e+00 |
| `tg_mol_istgwc3` | 0.6417354005651661 | 2.3159088744928997 | 2.609e+00 |
| `tg_mol_istgwc4` | 0.9845501419058125 | 2.445572286063181 | 1.484e+00 |
| `tg_mol_istgwc5` | 0.7692761805445423 | 2.3350962110629947 | 2.035e+00 |
| `tg_mol_tgwall1` | 0.7783203177204563 | 2.3434847559456973 | 2.011e+00 |

### Not changed: four cases that failed on v9 because of code bugs (AIUE-116)

`concap`, `ineudif0`, `ineudif1` and `ineudif3` in `D_only/nonog` also failed on v9. The cause was in the code, not in
the references, so their references are unchanged. The fix is on the v9 branch named above:

- `logte`/`logti`/`logng`/`logtg` (nonorthogonal precompute, v9 `6335b06`, `7d8a56c`, `dc263a4`) were refreshed only
  where the variable is evolved.
- `tiave` was read uninitialised under `concap = 1` (a latent bug, also in LLNL).
