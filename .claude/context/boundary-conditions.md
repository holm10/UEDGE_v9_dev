# Boundary conditions: options, models and known issues

The agent copy of the Confluence page `UEDGE boundary conditions: options, models and known issues` (SD space, page
25067521), which is the copy for people. The two name each other: a change to either updates the other (owner,
2026-11-11, AIUE-257 D-doc2; story AIUE-258). Compiled from code reading at `v9-develop` 4ff060d and **not yet reviewed
by the owner**: an issue marked *bug candidate* is unconfirmed. Before fixing one, or relying on what an option
means, ask the owner (CLAUDE.md, decision 23). Whether the yldot suite takes each branch is on the page, and AIUE-257
updates it as its coverage lands.

## Dispatch and guard cells

- `bouncon` (`bbb/pandf_boundary.m:4`) calls:
  - `iwall_boundary` (`bbb/pandf_boundary.m:1302`, iy = 0: the core where `isixcore(ix)=1`, the PF wall elsewhere);
  - `owall_boundary` (`bbb/pandf_boundary.m:2391`, iy = ny+1);
  - `left_boundary` (`bbb/pandf_boundary.m:2975`) and `right_boundary` (`bbb/pandf_boundary.m:3691`): the plates `ixlb(jx)` and `ixrb(jx)+1`;
  - `dnull_patch` (`bbb/pandf_boundary.m:4425`: `isudsym=1` or `dnXtarget`), `limiter_patch` (`bbb/pandf_boundary.m:4566`: `islimon`), `igas_patch`
    (`bbb/pandf_boundary.m:5140`: `igas=1`).
- `idalg` (`bbb/pandf_boundary.m:49`) marks the guard-cell equations algebraic.
- Each option writes the guard row of `yldot`, as `nurlx*·(target − value)/norm` or as a flux balance.
- In a Jacobian evaluation a wall row is built only when the window reaches it: `j3`/`isextr*`, `j7`, and
  `xcnearlb`/`xcnearrb`/`openbox`.
- The set-up routines run once, from `bbb/odesetup.m:1360-1366`:
  - `walsor` (`bbb/pandf_boundary.m:363`): wall gas sources `igasi`/`igaso`, albedos `albdsi`, material walls `matwsi`;
  - `pltsor` (`bbb/pandf_boundary.m:716`): plate sources and evaporation;
  - `recyprof` (`bbb/pandf_boundary.m:886`): recycling and albedo profiles, `sputtr`, tabulated `ndatlb`.

## Per-cell wall options (the trap)

`setwallbcarrays` (`bbb/odesetup.m:548`), called by `allocate` (`bbb/odesetup.m:319`), copies the scalar PF and
outer-wall selectors into their per-cell arrays:
- PF: `istepfcix`, `istipfcix`, `isnwconiix`, `isupwiix`, `istgpfcix`, `iphibcwiix`, `lyteix(1,)`, `lytiix`,
  `lyphiix`, `lyniix`, `lyupix`;
- outer wall: the `o`/`(2,)` forms.

It copies them whenever `ispfbcvsix = 0` (PF) or `iswobcvsix = 0` (outer), which are the defaults. So:
- Setting an `*ix` array does nothing unless its switch is 1.
- With the switch at 1, `gchange` zero-fills the arrays, and every entry the user leaves unset is option 0.
- `lyupix` is never read (`isupwi`/`isupwo = 3` use the scalar `lyup`, `bbb/pandf_boundary.m:1633,2559`).

## Values outside an option list

Most selectors have no `else`. A value the code does not handle writes no equation for those guard rows. The run
stops at the first Jacobian with `*** Error: Jacobian row = 0 for eqn iv = N`, which names no input.

Probe on d_only, AIUE-257 (unwritten rows):

| Input | Unwritten rows |
|---|---|
| `istepfc=7` | 4 |
| `isnwconi=9` | 4 |
| `istewc=9` | 8 |
| `iphibcwo=2` | 10 |
| `ibctepl=3` | 4 |
| `isupwi=7` (falls to up = 0) | 0 |
| `isngcore=7` with inertial atoms (falls to zero gradient) | 0 |

The selectors with no `else` are listed under issue #14 below.

## Options (value: model). Lines are `bbb/pandf_boundary.m`

**Core (iy = 0, `isixcore=1`)**

| Selector | Values |
|---|---|
| `isnicore` (ions; `bbb/pandf_boundary.m:1465`) | 1 `ncore`; 0 flux `curcore`; 2 as 0 + `ncore` on `ixfixnc..+incixc`; 3 const ni + integral `curcore − recycc·fngy`; 5 `lynicore`/`ncoremin`; 4 impurity-only `fnzysi`, refused when the impurities are ion species (#25); else `xerrab` (hydrogen) or no equation (impurities) |
| `isngcore` (inertial atoms `bbb/pandf_boundary.m:1380`; diffusive gas `bbb/pandf_boundary.m:1910`) | 0 albedo `albedoc`; 1 `ngcore`; 2 refused by `allocate` for every gas (#13; the diffusive gradient-length code is unreachable); 3 limited extrapolation; 4 zero gradient (diffusive); else zero gradient (inertial) or no equation (diffusive) |
| `isupcore` (`bbb/pandf_boundary.m:1575`) | 0 `upcore`; 1 dup/dy = 0; 2 d²up/dy² = 0; 3 `fmiy` = 0; 4 `lzflux`; 5 `utorave`; else `xerrab` |
| `iflcore` (`bbb/pandf_boundary.m:1787`) | 0 `tcoree`/`tcorei`; 1 `pcoree`/`pcorei`; −1 zero gradient |
| `istgcore` (`bbb/pandf_boundary.m:2037`) | 0 ti·`cftgticore`; 1 `tgcore`; 2 `cfalbedo` flux; else zero gradient |
| phi (`bbb/pandf_boundary.m:2121`, `bbb/pandf_boundary.m:2254`) | `lyphi(1)` scale length for every `isnewpot`; `isnewpot` −1 (`bbb/pandf_boundary.m:2124`), −2 (`bbb/pandf_boundary.m:2135`); `isnewpot*isphion=1`: `iphibcc` 1-3 + midplane `icoreelec`/`eycore`; `isphicore0=1` sends core cells to `iphibcwi` |

**PF wall (iy = 0)**

| Selector | Values |
|---|---|
| `isnwconiix` (`bbb/pandf_boundary.m:1517`) | 0 zero flux (`ifluxni`) or zero gradient (impurities: `fnzysi`); 1 `nwalli`; 2 extrapolation; 3 `lyniix` + `nwimin` |
| `isupwiix` (`bbb/pandf_boundary.m:1624`) | 1 `fmiy` = 0; 2 dup/dy = 0; 3 `lyup(1)`; else up = 0 |
| `istepfcix`/`istipfcix` (`bbb/pandf_boundary.m:1808`, `bbb/pandf_boundary.m:1861`) | 0 zero flux; 1 `tewalli`/`tiwalli`; 2 extrapolation ≥ `tbmin`; 3 `lyteix`/`lytiix`; 4 `bceew`/`bceiw` sheath-like (Ti: ion flux + `bcenw`, `cgengw`) |
| `istgpfcix` (`bbb/pandf_boundary.m:2061`) | 0 `tgwall`; 1 extrapolation; 2 `lytg(1,)`; 3 Maxwellian `cgengmw`; 4 half-Maxwellian; 5 `cftgtipfc` (tests the scalar, #10) |
| `iphibcwiix` (`bbb/pandf_boundary.m:2368`) | **only when `isnewpot=1`**: 0 dphi/dy = 0; 1 `phintewi`·Te; 3 `lyphi` (≡ 0 at 1e20); 4 `phiwi` |
| gas (`bbb/pandf_boundary.m:1895`) | albedo `albedoi`; chemical sputtering `isch_sput`/`chemsputi`; ion sputtering `isi_sputpf`; `matwalli` + `recycwit` > 0 recycling, < −1 `ngbackg`, ≤ 0 albedo; a puff without a material wall replaces the equation |

**Outer wall (iy = ny+1).** Mirrors the PF wall: `isnwconoix` `bbb/pandf_boundary.m:2495`, `isupwoix` `bbb/pandf_boundary.m:2550`, `istewcix`/`istiwcix`
`bbb/pandf_boundary.m:2630`/`bbb/pandf_boundary.m:2653`, `istgwcix` `bbb/pandf_boundary.m:2786`, `iphibcwoix` `bbb/pandf_boundary.m:2845`. The differences:
- `istiwc=4` uses the electron flux ne·vey;
- `iphibcwo` is read for every `isnewpot`, and a value outside 0, 1, 3, 4 leaves the row unwritten;
- with R ≤ 0, the atom albedo uses ni(ny+1), not the harmonic mean.

**Plates**

| Selector | Values |
|---|---|
| `isextrnp` (`bbb/pandf_boundary.m:3197`) | 0 zero gradient; 1 extrapolation |
| `recylb`/`recyrb` (atoms `bbb/pandf_boundary.m:3163`, gas `bbb/pandf_boundary.m:3444`) | > 0 recycling; [−1, 0] albedo; (−2, −1) `nglfix`/`ngrfix`; ≤ −2 zero gradient. Also `is1D_gbx` and `isnglf`/`isngrf` |
| `isbohmms`/`isupss` (`bbb/pandf_boundary.m:3258`) | Bohm or multispecies Bohm; `isupss` 1 supersonic, −1 slip, −2 extrapolation, −3 modified Bohm |
| `recycmlb` (`bbb/pandf_boundary.m:3238`) | > −9.9 up = −Rm·up(ion); (−10.1, −9.9] zero gradient; < −10.1 thermal flux |
| sheath (`bbb/pandf_boundary.m:3292`) | `ikapmod` 0 log κ / 1 `kappa()`; `isphilbc=1` phi = `phi0l`, else phi0 + κ·Te (`bctype`); `isnewpot=100` skips iy = 1, ny |
| `ibctepl`/`ibctipl` (and `r`) (`bbb/pandf_boundary.m:3362`, `bbb/pandf_boundary.m:3393`) | 1 sheath transmission; 0 `tepltl`/`tipltl`; 2 zero gradient; else no equation |
| `isph_sput`/`sputtlb` (`bbb/pandf_boundary.m:3505`, `bbb/pandf_boundary.m:3540`) | 1 physical, 2 + chemical from ions, 3 + chemical from H neutrals; sputt ≥ 0 flux balance, [−9.9, 0) albedo, < −9.9 `ngplatlb`; the last two only with `isph_sput = 0` (#26) |
| `istglb`/`istgrb` (`bbb/pandf_boundary.m:3570`, `bbb/pandf_boundary.m:4303`) | 0 `tgwall`; 1 extrapolation; 2 `xerrab`; 3 Maxwellian; 4 half-Maxwellian (needs `isupgon`); 5 `cftgtipltl` (`+threadprivate`, not `+input`) |
| `isfixlb`/`isfixrb` (`bbb/pandf_boundary.m:3019`, `bbb/pandf_boundary.m:3733`) | 1 fixed profiles, 2 symmetry point. Family-level: AIUE-173 |

## Known issues (page §7)

Each is filed under the epic AIUE-259 (2026-11-12); the key follows the number. Lines are
`bbb/pandf_boundary.m`.

1. AIUE-260: `bbb/pandf_boundary.m:3474` left plate, gas `recylb ≤ −2` writes `yldot(iv1)` (the Te row) with an ion-density difference; the gas
   row is unwritten. The right plate (`bbb/pandf_boundary.m:4208`) is correct. The stale `ifld` is 3 in d_mols (`nisp = 2`):
   the `--checkbounds` audit stops there (AIUE-257, run 43355786083; AIUE-260 comment 10364).
2. AIUE-261: `bbb/pandf_boundary.m:1671` impurity core `isnicore=3` writes the stale `yldot(iv1)`, with the opposite sign to the hydrogen version.
3. AIUE-262: `bbb/pandf_boundary.m:1688` impurity core `isnicore=5` writes the stale `iv1`, normalised by `n0(ifld)` (wrong index).
4. AIUE-263: `bbb/pandf_boundary.m:2472` outer wall, `ishymol` atoms: `sy(ix,0)` where `sy(ix,ny)` is meant.
5. AIUE-264: `bbb/pandf_boundary.m:2473` `recycwot(ix,1)` where the PF wall uses `recycwit(ix,2,1)`.
6. AIUE-265: `bbb/pandf_boundary.m:1994` the molecular `nharmave` uses `ng(ix,0,1)` twice.
7. AIUE-266: `bbb/pandf_boundary.m:2790` outer Tg extrapolation `gyf(ix,ny)/gyf(ix,ny)`; every other outer-wall extrapolation uses
   `gyf(ix,ny-1)/gyf(ix,ny)` (Te `bbb/pandf_boundary.m:2636`).
8. AIUE-267: `bbb/pandf_boundary.m:3574` left Tg extrapolation uses the radial `gyf`; the right plate uses `gxf` (`bbb/pandf_boundary.m:4307`).
9. AIUE-268: `bbb/pandf_boundary.m:3551`, `bbb/pandf_boundary.m:4284`, `bbb/pandf_boundary.m:5004`, `bbb/pandf_boundary.m:5087` impurity gas normalised by `n0(igsp)` instead of `n0g`.
10. AIUE-269: `bbb/pandf_boundary.m:2103`, `bbb/pandf_boundary.m:2827` option 5 of `istgpfc`/`istgwc` tests the scalar, not the per-cell array.
11. AIUE-270: `lyupix` and `isulyupx` are never read.
12. AIUE-271: `bbb/pandf_boundary.m:2275` `iphibcc` outside 1-3 stops with `xerrab`, so `dphi_iy1` and `isutcore` (`bbb/pandf_boundary.m:2340-2351`) are unreachable.
13. AIUE-272: `bbb/pandf_boundary.m:1392` inertial `isngcore=2` stops with `xerrab`. The diffusive-gas code for 2
    (`bbb/pandf_boundary.m:1910`) is unreachable too: `allocate` refuses `isngcore=2` for every gas (`bbb/odesetup.m:195`;
    corrected 2026-11-12, AIUE-272 comment 10361), so `.v`'s "not available" holds for both.
14. AIUE-273: No input check: the selectors with no `else` are `isnwconi`/`o`, impurity `isnicore`, `istepfc`/`istipfc`/
    `istewc`/`istiwc`, `iphibcwo`, `ibctep*`/`ibctip*`, diffusive `isngcore`, `istgpfc`/`istgwc` < 0, `istglb=4`
    without `isupgon`, and `ikapmod`.
15. AIUE-274: Asymmetry: `iphibcwi` needs `isnewpot=1`, `iphibcwo` does not. This explains why `iphibcwi=1/4` are INERT in the
    `isnewpot=0` families.
16. AIUE-275: Asymmetry: `isupss=−3` has `rrv` only on the right (`bbb/pandf_boundary.m:3274` vs `bbb/pandf_boundary.m:3998`).
17. AIUE-276: Asymmetry: Ti option 4 uses the ion flux on the PF wall (`bbb/pandf_boundary.m:1878`) and the electron flux on the outer wall
    (`bbb/pandf_boundary.m:2670`).
18. AIUE-277: Asymmetry: the outer-wall atom albedo (`bbb/pandf_boundary.m:2485`) does not use the harmonic mean.
19. AIUE-278: Relaxation factors: `isupcore=4/5` and Ti `iflcore=−1` use `nurlxe` (`bbb/pandf_boundary.m:1589`, `bbb/pandf_boundary.m:1853`); diffusive
    `isngcore=2` uses `nurlxn` (`bbb/pandf_boundary.m:1924`); PF Tg extrapolation uses `nurlxi` (`bbb/pandf_boundary.m:2068`).
20. AIUE-279: `bbb/pandf_boundary.m:2231`, `bbb/pandf_boundary.m:2239` the PF corner checks `ixrb` but writes `ixrb+1`.
21. AIUE-280: Question: a wall puff without a material wall replaces the whole equation (`bbb/pandf_boundary.m:2021`, `bbb/pandf_boundary.m:2776`).
22. AIUE-282: Question: `bcel` weights by `isphion+isphiofft`, which can be 2 (`bbb/pandf_boundary.m:3342`).
23. AIUE-285: `.v` documentation errors: `istgcore` label, `isngcore` "anything else", `isupss` values, `tepltr`/`tipltr`
    names, `iphibcwi` needing `isnewpot`, `isphicore0`.
24. AIUE-286: Dead code: `fluxsurfav2`/`fluxsurfav1` (`bbb/pandf_boundary.m:1038`, `bbb/pandf_boundary.m:1096`); the `isnewpot*isphion=1000` block (`bbb/pandf_boundary.m:2955`);
    the duplicate `isupwiix` loop in `setwallbcarrays`.
25. AIUE-292: Impurity core `isnicore=4` is refused when the impurities are ion species (`isimpon` 6, 7): the first
    core-ni loop runs over every ion (`bbb/pandf_boundary.m:1369`) and stops on 4 (`bbb/pandf_boundary.m:1515`), before the impurity loop
    (`bbb/pandf_boundary.m:1646`) that codes it (`bbb/pandf_boundary.m:1684`); for the shared options the impurity loop writes the rows
    again. Seen in d_c (AIUE-257 prototype, a62f121).
26. AIUE-295: Plate impurity gas: the flux-balance test `sputtlb >= 0 .or. abs(sputflxlb) > 0` (`bbb/pandf_boundary.m:3540`, right
    `bbb/pandf_boundary.m:4273`) is always true with physical sputtering on (`isph_sput >= 1`), so a negative `sputtr` never reaches the
    albedo (`bbb/pandf_boundary.m:3552`) or fixed-density (`bbb/pandf_boundary.m:3558`) branch and acts as a negative sputtering
    coefficient. Shown in d_c (AIUE-257 preview, 30c420d).
27. AIUE-298: PF-wall Ti option 4 reads `tg(ix,0,iigsp)` (`bbb/pandf_boundary.m:1881`): `iigsp` is an ion index (`bbb/bbb.v:160`),
    `tg` is indexed by gas, and the outer wall uses gas 1 (`bbb/pandf_boundary.m:2673`). With one gas the read is out of bounds
    (`--checkbounds` stops; d_only, ortho, slab_phi); with two it takes gas 2's temperature (d_mols, d_c). AIUE-257 run 43355786083.
