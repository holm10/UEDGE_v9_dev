# Adding physics — spec → implement → review

New physics (transport terms, atomic/molecular processes, BCs, sources, closures, neutral/impurity models) follows
a fixed agent pipeline defined in `.claude/agents/`:

1. **`uedge-physics`** — researches literature, derives the equations in UEDGE's formulation/units, writes
   `docs/physics_specs/<feature>.md`. Does not touch Fortran.
2. **`uedge-reviewer`** — adversarial review of the spec → APPROVE / REVISE / REJECT.
3. **`uedge-implementer`** — implements the approved spec in `.m`/`.v`, builds, runs tests. Does not change the
   physics; returns questions instead.
4. **`uedge-reviewer`** — reviews the implementation, including the model's row in `physics-models.md`.

The spec is the one ticket document that is committed: `docs/physics_specs/<feature>.md` goes on the ticket branch
with the physics change it specifies. The review reports and the implementer's responses are working documents in
`.claude/work/<KEY>/reviews/` (never committed); each round's verdict, counts, one line per finding and the
response go to the ticket page (`branching.md`). **Physics without a ticket record** (no Jira key, or
`--no-tracker`): there is no page, so the main session puts that same review summary, for the spec rounds and the
implementation rounds, into the PR description; it is the only lasting copy of the implementation reviews (the spec
keeps its own "Response to review round N" sections).

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
- Validate: regression suites unchanged with feature off, the pytests suites and the yldot suite (or the changes explained, if defaults moved on purpose); with feature on, check `checkbal()` (`src/uedge/balance.py`)
  for particle/power balance, and run the AIUE-8 OpenMP test flow (`validate` step 4).

## A new switch in the yldot suite

The yldot suite's input inventory is read from the `.v` files (`tests/yldot/harness/inputs.py`), so a new `+input`
switch is a new variant key (`<pkg>.<name>`) at once, and `test_manifest_inventory` fails with `missing:` in every
family whose manifest classifies variants (`tests/yldot/test_inventory.py`). Give it its variant on the ticket branch:

1. With the switch off by default, regenerate only its key from the committed tree:
   `python tests/yldot/tools/make_references.py generate --from-commit <sha> --only <pkg>.<name> --release
   yldot-data-v<N> --write` (the Linux image, the only release-grade path). The run must reproduce the stored
   defaults bit for bit (exit 3 otherwise: the default moved). The new entries are an addition, which needs no PR
   declaration.
2. Reserve `N` on the ticket page once the owner agrees, and have the owner publish the release with
   `release_data.py` (`.claude/context/testing.md` → Tools).
3. If the generic value rules don't fit the switch (an index, a cell range, an enumerated selector), it needs an
   `overrides.toml` entry with a reason, which needs `Test criteria: changed`. Ask the epic owner before adding it
   (AIUE-9 decision 23).
