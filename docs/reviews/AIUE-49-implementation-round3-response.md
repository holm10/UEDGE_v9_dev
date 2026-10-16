# Response to AIUE-49 implementation round 3 (APPROVE, 0/0/3 minor)

Documentation-only fixes after APPROVE (no further round needed under the loop rule).

| Finding | Response |
|---|---|
| I3-m1 ForceSerialCheck order backwards | Fixed in `openmp-jacobian.md`: the first serial evaluation goes into the solver's `jac`, the second into a local copy. |
| I3-m2 README compiler contradiction; build hash not named | Fixed: "Limits" now says the compiler string is recorded on ELF builds only and that `provenance.build.extensions_sha256` identifies the binary. |
| I3-m3 rowptr length vs neq+1 (note) | Not changed: a short pointer is already a MISMATCH (fails safe), and a 0-d rowptr still exits 2. |
