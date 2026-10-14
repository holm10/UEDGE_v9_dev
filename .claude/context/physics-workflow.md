# Adding physics — spec → implement → review

New physics (transport terms, atomic/molecular processes, BCs, sources, closures, neutral/impurity models) follows
a fixed agent pipeline defined in `.claude/agents/`:

1. **`uedge-physics`** — researches literature, derives the equations in UEDGE's formulation/units, writes
   `docs/physics_specs/<feature>.md`. Does not touch Fortran.
2. **`uedge-reviewer`** — adversarial review of the spec → APPROVE / REVISE / REJECT.
3. **`uedge-implementer`** — implements the approved spec in `.m`/`.v`, builds, runs tests. Does not change the
   physics; returns questions instead.
4. **`uedge-reviewer`** — reviews the implementation, including the model's row in `physics-models.md`.

`.claude/context/physics-models.md` is the index of implemented models. Read it before specifying anything. The
implementer updates it on the same branch as the code (trailer `AI-layer: code-facts`).

## Where things go

| Change | Location |
|---|---|
| Ion continuity sources/fluxes | `bbb/pandf_plasma_continuity.m` |
| Parallel momentum, friction, viscosity | `bbb/pandf_plasma_momentum.m` |
| Te/Ti equations, heat fluxes, equipartition, radiation | `bbb/pandf_plasma_energy.m` |
| Neutral gas density/energy | `bbb/pandf_gas_continuity.m`, `bbb/pandf_gas_energy.m` |
| Potential, currents, drifts | `bbb/pandf_potencur.m`, `calc_driftterms` |
| Boundary conditions | `bbb/pandf_boundary.m` (`bouncon`) |
| Anomalous transport models | `bbb/turbulence.m`, `calc_plasma_diffusivities` |
| Hydrogenic rates | `aph/`; impurity rates/sputtering → `api/` |
| New switches/coefficients | `bbb/bbb.v` in the matching group (`UEpar`, `Coefeq`, `Bcond`, …) |

## Implementation conventions

- Gate with a switch (`is<name>on`) or multiplier (`cf<name>`). Default it to **off / old behaviour** unless changing the default model is part of the spec. Then the spec and the PR must state which defaults change and which reference cases move.
- Respect existing switch semantics (`isnion`, `isupon`, `isteon`, `istion`, `isngon`, `istgon`, `isphion`) and
  `meth*` differencing choices.
- SI units except temperatures, which are stored in **Joules** internally (`te`, `ti` in J; `ev` conversion factor).
  Check neighbours before assuming.
- Read `openmp-jacobian.md` before writing anything inside the `pandf` tree.
- Validate: regression suites unchanged with feature off (or the changes explained, if defaults moved on purpose); with feature on, check `checkbal()` (`src/uedge/balance.py`)
  for particle/power balance, and `ppp.CheckPandf1 = 1` with threads.
