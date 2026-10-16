# Response to AIUE-49 implementation round 2 (APPROVE, 0/0/5 minor)

These are code changes after APPROVE, so a round-3 delta review follows (end-to-end-feature loop, step 3).

| Finding | Response |
|---|---|
| I2-m1 `exit_code([])` returns 0 | Fixed: an empty report list is exit 2 ("nothing to judge"). Test `test_exit_code_of_nothing_is_an_error`. |
| I2-m2 permuted section prints made-up coordinates | Fixed: no map is applied; entries are reported as `position N`. Test `test_permuted_section_has_no_cell_coordinates`. |
| I2-m3 CSR row pointer unchecked | Fixed: `csr_entries` checks rowptr[0]==1, non-decreasing, rowptr[-1]-1 == len(values) == len(cols); violations are harness errors. Test `test_inconsistent_csr_is_an_error`. |
| I2-m4 provenance details | Fixed: `premeth` decoded to a plain string (`_text`); docstring and README say HEAD/dirty are read at run time and that the compiler string is available only on ELF builds (empty on macOS). |
| I2-m5 ForceSerialCheck wording | Fixed in `openmp-jacobian.md`: a separate serial-vs-serial reproducibility check, not part of `CheckJac`. |
