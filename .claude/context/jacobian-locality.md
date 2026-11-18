# Jacobian locality: couplings outside the Jacobian window

A catalogue of the places where UEDGE's residual depends on cells **outside the window** that the Jacobian's local
evaluation recomputes, so the finite-difference Jacobian misses or misstates that coupling. It belongs to no ticket:
add an entry whenever a locality check, a probe or a review finds a new one (what is missed, where, when active, the
evidence, whether it was investigated and what was decided, with who decided it). This module is the only live copy.
It was moved here from the Confluence page `Non-local stencils: couplings outside the Jacobian window` (SD space, page
17661953, started 2026-10-26 from the locality data of AIUE-100 and AIUE-101), which is a frozen archive copy as of
2026-11-18 (owner, tracker #5). Code citations re-checked at f09c7888.

## How the window works

- **Building the Jacobian.** `jac_calc` builds it column by column (`bbb/oderhs.m:1095-1226`): it perturbs one
  variable of cell (xc, yc) by `dyl = del·(|y| + dylconst/suscal)` (`bbb/oderhs.m:1156`) and calls
  `pandf(xc, yc, ...)`, which evaluates the residual only on a window around the cell.
- **Window bounds.** `initialize_ranges` (`bbb/pandf.m:31-248`) sets them (`bbb/pandf.m:67-77`): poloidal
  `xc − xlinc` .. `xc + xrinc`, radial `yc ± yinc`; defaults `xlinc = 2`, `xrinc = 1`, `yinc = 2`
  (`bbb/bbb.v:1111-1113`).
- **Near the core boundary.** With `isjaccorall = 1` (default, `bbb/bbb.v:1114`), a column with `yc − yinc ≤ 0` uses
  the **whole** ix range (`bbb/pandf.m:53-66`), because the integrated core-flux boundary condition couples every ix
  there.
- **What can go wrong.** Any term whose stencil reaches beyond the window misses part of the coupling, and so does any
  term computed over a narrower range than the window inside `pandf`. Newton still converges if the miss is small, but
  the Jacobian is not exact there.

## How a missed coupling is found: the locality check

- For a perturbed column, the full evaluation's change Δfull is compared with the windowed one's Δlocal; the mismatch
  d = Δfull − Δlocal scores |d| / (tol_r + rtol·|Δfull|), its size in units of that row's round-off tolerance. A real
  missed coupling's score grows in proportion to δ.
- At δ = 1e-6 (the suite's setting), entries above M_loc = 100 form the asserted pattern; 1-100 is an unasserted band.
  The planted range mutations score 1.2e4 to 2e7.
- Code: `tests/yldot/harness/locality.py`; per-family causes in `tests/yldot/families/<family>/family.toml` under
  `[locality.causes]`; the stored patterns from `yldot-data-v4` on, every variant's from v13 (`Store.locality_pattern`;
  `testing.md`).

Labels: `ti[1](2,3)` = equation, Fortran species, cell (ix, iy); "dix +2" = the affected row is 2 cells right of the
perturbed cell.

## Catalogue

1. **`isnonog = 1`: neutral heat-conductivity 4-point average in `feixy` (ti two cells right).** The `ti` residual at
   dix +2 (diy −1..+1) responds to `ni` (ion and inertial-atom slots) and `ti` at the perturbed cell. Where:
   `bbb/pandf_plasma_energy.m:476-477`, `cftiexclg*cfneut*cfneutsor_ei*0.25*(hcyn(ix,iy)+hcyn(ix,iy1)+hcyn(ix2,iy)+hcyn(ix4,iy1))`:
   the `hcyn(ix4,iy1)` corner reaches ix − 1, so `feix(ix)` depends on ix − 1 and `resei(ix+1)`
   (`bbb/pandf_plasma_energy.m:1034-1036`) on a cell one beyond `xrinc`; the code says so
   (`bbb/pandf_plasma_energy.m:458-459`). Active with `com.isnonog = 1` and `cfneutsor_ei`, `cftiexclg` nonzero.
   Largest score at δ = 1e-6: d_only, d_mols, d_c 15 (all in the band); large_dd2c 87; dnull_imp2 5.5e3 (136 above
   M_loc); imp7 2.4e3 (41). Every entry above M_loc in the owner families has this signature (AIUE-101); ortho and
   slab_phi (`isnonog = 0`) show none. Investigated (AIUE-100 D2: probe chain `feixy` → `feix` → `resei`; with
   `cfneutsor_ei = 0` or `cftiexclg = 0` every column is bit-identical). **By design** (owner, 2026-10-22, AIUE-100
   D2): stored and asserted as the expected pattern; entries near M_loc are accepted as this signature (owner,
   2026-10-25, AIUE-101).
2. **te one cell away, inside the window (large_dd2c, imp7).** `te` rows at dix ±1 (or diy ±1 from `phi`) respond to
   `te`, `ni` or `phi`. These cells are inside the window, so some part of the te path is computed over a narrower
   range than the window. large_dd2c: `te[1](2,1) → te[1](1,1)` scores 38 at δ = 1e-6; 13 of 44 asserted entries at
   δ = 1e-5; about 18 % of the 887 entries above 1 on the full grid at δ = 1e-6. imp7: 3-17 entries from δ = 1e-5.
   **Not investigated**; recorded as unattributed (`te_ix_minus_1` in `tests/yldot/families/large_dd2c/family.toml:109`; owner, 2026-10-25,
   AIUE-101).
3. **`isjaccorall = 0`: the core-boundary rows couple across all ix.** With the switch off: d_c `ni` rows at dix +1,
   diy −1, −2 from `ni`/`up` (82 above M_loc); slab_phi `ti`/`te` rows 3-4 cells right at iy 0 (20). Covered **by
   design** by the default 1 (`bbb/pandf.m:53-66`); the variant documents why the default matters (AIUE-101 variant
   patterns, Linux-image preview of f6122cb).
4. **`difgx4order ≠ 0`: 4th-order poloidal gas diffusion.** `ng` rows at dix −2 (diy −2..0) respond to `ni`/`up`.
   Where: `bbb/pandf_gas_continuity.m:940-954` (`fngx4ord` from `d3ndx3`, wider than the 2nd-order flux). Active with
   `difgx4order(igsp) ≠ 0` and `isngon(igsp) = 1` (default 0). d_mols with `difgx4order = 1`: 2008 new entries, 1584
   above M_loc (AIUE-101 preview). **Not investigated**; open: widen the window when it is on, as `isjaccorall` does?
5. **`ispsorave > 0`: 5-point average of the particle sources.** `ni` rows at diy −1, dix −1..+1 respond to
   `ni`/`up`, inside the window, so the averaged source apparently uses values the local evaluation does not
   recompute. Where: `bbb/pandf_plasma_continuity.m:347-398` (`psorg`, `psor` averaged over the neighbours;
   `bbb/bbb.v:182`). With `ispsorave = 1`: d_mols 14,042 new entries, 14,016 above M_loc; ortho 8 above; d_only 37
   new, none above. **Not investigated**.
6. **Minor: `ishosor = 1`, `ineudif = 3`, `dif_use`.** 1-2 new entries each in d_only and d_mols, all below M_loc at
   δ = 1e-6. `ishosor` is documented as full RHS only (`bbb/bbb.v:180`), so a local miss is expected. Not
   investigated; low priority.
7. **The window inputs themselves.** `xrinc = 0` misses the ix+1 couplings everywhere (above M_loc: d_only 133, d_mols
   111, ortho 131, d_c 1355, slab_phi 7735): expected, it confirms the check works. `xlinc = 3` on slab_phi: 28
   **new** entries above M_loc, `up` rows three cells left and two rows down, at the new window edge; a wider window
   should only remove misses. **Not investigated**; possibly an edge cell recomputed with stale neighbour data.
   `yinc = 3`: no change.

**Not a stencil issue, but it blocks the check:** `isupgon(1)` 1 → 0 after the restore makes `pandf` not repeatable
(the `up[2]` residual grows on every call), so no locality comparison is possible; left out of the 8x4 families'
locality scope (owner, 2026-10-25). Bug AIUE-208 (Jira archive).

## Open items (no ticket yet)

| # | Item | Suggested next step |
|---|---|---|
| 2 | te one cell away inside the window (large_dd2c, imp7) | Compare every intermediate array full vs local on one column (the AIUE-100 method); find the narrower loop range |
| 4 | `difgx4order` stencil beyond the window | Decide: widen the window when on, or document as a known approximation |
| 5 | `ispsorave` misses inside the window | Probe the averaging range in the local evaluation |
| 7 | `xlinc = 3` creates new misses at the window edge | Probe an edge cell; check the `i1`/`i2p` bounds (`bbb/pandf.m:67-77`) |

Data: the probes, tables and scripts are in `../uedge-wt/data/AIUE-100/` and `../uedge-wt/data/AIUE-101/calibrate/`
(`d3_table.txt`, `near_attr.txt`, `coupling_geometry.txt`, the Linux-image preview `linux-small/`).
