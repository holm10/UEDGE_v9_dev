# Physics model index — what is implemented, where, and how it is switched

Load this module before planning, specifying, implementing or reviewing anything that touches an equation. It is
the map from **a model** to **its switches, its code and its spec**. A new agent uses it to find out what already
exists before proposing something new.

## How this index stays true

- **`uedge-implementer`** adds or updates a row in the same ticket that lands a model or changes its switches,
  defaults or location (commit trailer `AI-layer: code-facts`, see `branching.md`).
- **`uedge-physics`** checks this index first, and states in the spec which row it adds or changes.
- **`uedge-reviewer`** (implementation stage) fails the review if a landed model has no row, or if a row is wrong.
- Every `path:line` reference here is guarded by the drift check (`.claude/hooks/check_context_refs.py`).
- Rows marked *pre-spec* describe physics that predates `docs/physics_specs/`. When a ticket touches one, it writes
  the spec link it has, or leaves *pre-spec*.

## Equations (the residuals `pandf` assembles)

| Equation | Switch (`bbb/bbb.v`) | Default | Transport / sources | Residual |
|---|---|---|---|---|
| Ion continuity | `isnion` `bbb/bbb.v:217` | on | `calc_plasma_transport` `bbb/pandf_plasma_continuity.m:1082`, `calc_volumetric_sources` `bbb/pandf_plasma_continuity.m:143` | `calc_plasma_particle_residuals` `bbb/pandf_plasma_continuity.m:1009` |
| Parallel ion momentum | `isupon` `bbb/bbb.v:218` | on | `calc_plasma_momentum` `bbb/pandf_plasma_momentum.m:153`, `calc_friction` `bbb/pandf_plasma_momentum.m:564`, `calc_plasma_viscosities` `bbb/pandf_plasma_momentum.m:1422` | `calc_plasma_momentum_residuals` `bbb/pandf_plasma_momentum.m:366` |
| Electron energy | `isteon` `bbb/bbb.v:222` | on | `calc_plasma_energy` `bbb/pandf_plasma_energy.m:7`, `calc_plasma_heatconductivities` `bbb/pandf_plasma_energy.m:1239` | `calc_plasma_energy_residuals` `bbb/pandf_plasma_energy.m:964` |
| Ion energy | `istion` `bbb/bbb.v:223` | on | as electron energy, plus `calc_plasma_equipartition` `bbb/pandf_plasma_energy.m:1539` | `calc_plasma_energy_residuals` |
| Neutral gas density | `isngon` `bbb/bbb.v:224` | on | `neudif` `bbb/pandf_gas_continuity.m:19`, `neudifpg` `bbb/pandf_gas_continuity.m:493` | `calc_gas_continuity_residuals` `bbb/pandf_gas_continuity.m:1012` |
| Neutral gas energy | `istgon` `bbb/bbb.v:225` | off | `calc_gas_energy` `bbb/pandf_gas_energy.m:556`, `engbalg` `bbb/pandf_gas_energy.m:11` | `calc_gas_energy_residuals` `bbb/pandf_gas_energy.m:315` |
| Potential | `isphion` `bbb/bbb.v:226` | off | `calc_currents` `bbb/pandf_potencur.m:39`, `calc_fqp` `bbb/pandf_potencur.m:313` | `calc_potential_residuals` `bbb/pandf_potencur.m:650` |

Boundary conditions for all equations: `bouncon` `bbb/pandf_boundary.m:4`, which dispatches to
`iwall_boundary`, `owall_boundary`, `left_boundary` and `right_boundary` (`bbb/pandf_boundary.m:1302`).

## Models

| Model | Switches (`bbb/bbb.v`) | Default | Main code | Spec |
|---|---|---|---|---|
| Inertial (parallel-momentum) neutrals | `isupgon` `bbb/bbb.v:221` (most code tests only `isupgon(1)`); the atoms become ion species `iigsp` (`bbb/odesetup.m:918-919`), evolved under `isnion(iigsp)` and `isupon(iigsp)`, with `ng(,,1)` a copy of `ni(,,iigsp)` (`bbb/convert.m:282-284`); atom temperature `tg(,,1)` evolved if `istgon(1) = 1` (`bbb/bbb.v:225`), else set from `ti` (owner, 2026-10-22; `uedge-gotchas.md` → Model layout) | off | `bbb/pandf_gas_continuity.m`, `bbb/pandf_plasma_momentum.m` | pre-spec |
| Molecular hydrogen | `ishymol` `bbb/bbb.v:152` (needs `nhgsp=2`); CRUMPET rates `ismolcrm` `bbb/bbb.v:257` | off; CRUMPET on | `bbb/pandf_gas_*.m`, `bbb/pandf_plasma_energy.m`, `bbb/oderhs.m` | pre-spec |
| Impurities (fixed fraction / multi-charge-state) | `isimpon` `bbb/bbb.v:3877` | off | `api/` (rates, sputtering, `fmombal`), `bbb/pandf_plasma_momentum.m`, `bbb/pandf_plasma_energy.m` | pre-spec |
| Volume recombination | `isrecmon` `bbb/bbb.v:62`, `cfrecom` `bbb/bbb.v:65` | off | `bbb/pandf_plasma_continuity.m`, `bbb/pandf_plasma_energy.m` | pre-spec |
| Drifts: E×B, ∇B, diamagnetic, B×∇T | `cf2ef` `bbb/bbb.v:354`, `cfyef` `bbb/bbb.v:355`, `cftef` `bbb/bbb.v:356`, `cf2bf` `bbb/bbb.v:357`, `cfydd` `bbb/bbb.v:368`, `cfbgt` `bbb/bbb.v:350` | off (0.) | `calc_driftterms` `bbb/pandf_potencur.m:1254` | pre-spec |
| Potential from toroidal momentum balance | `isnewpot` `bbb/bbb.v:233` | off | `bbb/pandf_potencur.m`, `bbb/pandf_boundary.m` | pre-spec |
| Sheath energy transmission | `bcee` `bbb/bbb.v:2042`, `bcei` `bbb/bbb.v:2044` | 4.0 / 2.5 | `bbb/pandf_boundary.m` | pre-spec |
| Parallel heat-flux limits | `flalfe` `bbb/bbb.v:1363`, `flalfi` `bbb/bbb.v:1364` | 0.21 | `calc_plasma_heatconductivities` | pre-spec |
| Anomalous radial transport | `kye` `bbb/bbb.v:1387`, `kyi` `bbb/bbb.v:1394`, `dif_use` `bbb/bbb.v:2180`, `isbohmcalc` `bbb/bbb.v:1351` | constant | `calc_plasma_diffusivities` `bbb/pandf_plasma_momentum.m:1203` | pre-spec |
| Turbulence-based transport | `isturbnloc` `bbb/bbb.v:1544` (group `Turbulence`) | 1, only used when the turbulence model is active | `turbdif` `bbb/turbulence.m:306` | pre-spec |
| Interspecies friction / thermal force | `isofric` `bbb/bbb.v:210`, `cfgti` `bbb/bbb.v:2108` | new form / 1.0 | `calc_friction`, `mombal` `bbb/pandf_plasma_momentum.m:867` | pre-spec |
| Viscosity | `cfvisx` `bbb/bbb.v:331`, `cfvisy` `bbb/bbb.v:332` | 1.0 | `calc_plasma_viscosities` | pre-spec |
| Monte-Carlo neutral coupling | `ismcnon` `bbb/bbb.v:2337` | off | `bbb/ext_neutrals.m`, `initialize_ismcnon` `bbb/pandf_plasma_continuity.m:7` | pre-spec |
| Neoclassical transport (NCLASS) | `ncl/ncl.v` | off | `ncl/ncl_driver.m` | pre-spec |

## Adding a row

```
| <Model> | `<switch>` `bbb/bbb.v:<line>` | <default> | `<routine>` `<file>:<line>` | `docs/physics_specs/<x>.md` |
```

- Cite the `.v` line of each switch and the first line of each routine. Then run
  `uv run .claude/hooks/check_context_refs.py` and lock the new references with `--update` after checking them.
- A model that changes defaults also notes the moved reference cases in its spec. This table states only the new default.
