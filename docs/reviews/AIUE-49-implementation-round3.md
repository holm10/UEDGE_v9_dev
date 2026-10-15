# AIUE-49 implementation review, round 3 (delta after APPROVE)

Ticket: AIUE-49 "Harness core: fresh-process runner, capture, bitwise compare, localise" (epic AIUE-8).
Branch `feature/v9-AIUE-49-omp-harness-core`. Delta reviewed: `git diff 71b0e3b..HEAD` (f46f7a4 fixes the round-2
minors, cf23ddf corrects the AI-layer wording). Inputs: the round-2 report and `AIUE-49-implementation-round2-response.md`.

## Verdict

**APPROVE**

## Summary

The delta fixes I2-m1, I2-m2 and I2-m3 in full. I checked each fix in code, in the new unit tests, and in live runs.
The new CSR consistency check does not reject real UEDGE Jacobians. I ran it on post-`exmain` matrices (Te box and the
full problem) and on captured hook matrices (OpenMP and serial, `--itermx 3`), and none gave an "inconsistent CSR" error.
I2-m4 and I2-m5 are only partly resolved. The new `ForceSerialCheck` sentence swaps which serial evaluation replaces the
solver's Jacobian. The README still says in "Limits" that the compiler is not recorded, while the provenance bullet now
says it is recorded on ELF. Both are documentation slips with no effect on what the harness computes. I found no
regression and no new BLOCKER or MAJOR problem.

## Findings

### BLOCKER

None.

### MAJOR

None.

### MINOR (optional)

**I3-m1: the new `ForceSerialCheck` wording gets the order of the two evaluations backwards.** Location:
`.claude/context/openmp-jacobian.md:45-47` (cf23ddf).
- The text says: "two serial evaluations of the Jacobian, the second replacing the solver's".
- In `ppp/parallel.F90:84-89` the *first* `jac_calc` writes into `jac`, which is the solver's array (the dummy argument).
  The second writes into the local `jaccopy`. The code then compares the two and calls `xerrab` on a difference
  greater than 1e-14.
- What the sentence implies is still right: the solver ends up with a serial Jacobian. Only the clause naming which
  evaluation is wrong. The harness never sets this switch.
- Acceptance: "the first one replacing the solver's", or simply "the solver then uses a serial Jacobian".

**I3-m2: the README contradicts itself on compiler provenance, and the binding identity is not stated.** Location:
`tests/deterministic_omp/README.md:124` and `:133-134`.
- Line 124 (new) says the provenance records "the compiler string where the binaries keep one — Linux/ELF; empty on
  macOS".
- "Limits" (line 133) still says the compiler and its flags "are not recorded".
- I2-m4 also asked the README to say that `extensions_sha256` is the binding identity. The README now says HEAD/dirty
  are "read at run time" but does not name the hash as binding. Only the `build_identity` docstring says that.
- Acceptance: one consistent statement (flags never recorded; compiler string recorded on ELF only), and one clause that
  `extensions_sha256` identifies the binary.

**I3-m3 (note, no action needed): the CSR check does not compare `len(rowptr)` with `neq+1`.** Location:
`compare.py:41-50`.
- `csr_entries` has no `neq` argument, and `matrix_mismatch` checks only that `rows.max() < neq`. I2-m3 listed this
  invariant, and the response does not claim it.
- When can it happen? The worker slices `jaci[:neq+1]`, and the capture slices `jaccapi[:jaccapneq[k]+1]`. A short
  pointer arises only if the hook records a `jaccapneq[k]` different from `neq`.
- What happens then? The missing rows appear as "only in a/b" entries. The result is a MISMATCH, not AGREE, so the
  failure is in the safe direction.
- A 0-d `rowptr` raises `TypeError` from the message formatting rather than `IndexError`. It still ends as exit 2
  through the unexpected-exception path.

## Status of previous findings

| ID | Status | Evidence (re-checked myself) |
|---|---|---|
| I2-m1 `exit_code([])` returns 0 | **Resolved** | See below the table. |
| I2-m2 permuted section prints made-up coordinates | **Resolved** | See below the table. |
| I2-m3 CSR row pointer unchecked | **Resolved** | See below the table. |
| I2-m4 provenance details | **Partially resolved** | See below the table. |
| I2-m5 `ForceSerialCheck` wording | **Partially resolved** | See below the table. |

**I2-m1 (resolved):**
- `cli.py:44-49` now has `if not reports or any(...)`, which returns 2.
- Test `test_exit_code_of_nothing_is_an_error` covers it.

**I2-m2 (resolved):**
- `describe_iv` returns `position N` when `igyl is None`, and the permuted branch now passes `None`.
- Live output (AIUE-47-omp, Te box, `jacrhs`, `--itermx 3`): `post_exmain (permuted indices): ... first value row
  position 1 col position 1`.
- Test `test_permuted_section_has_no_cell_coordinates` asserts `ix=` is absent.

**I2-m3 (resolved):**
- `csr_entries` now checks four invariants: `rowptr[0]==1`, non-decreasing, `rowptr[-1]-1 == len(values)`, and
  `len(values) == len(cols)`.
- It raises `IndexError`, which `compare_records` turns into an `errors` entry (exit 2).
- Test `test_inconsistent_csr_is_an_error` covers it.
- No false positives on real records: every live run below completed with `errors: []`.
- The `neq+1` length invariant is not checked: see I3-m3. It is harmless.

**I2-m4 (partially resolved):**
- `premeth` is now plain text: `"premeth": "ilut"` in every live record (`_text` handles the ndarray).
- The docstring explains the ELF/Mach-O difference and the run-time reading of HEAD.
- The README is not yet consistent and does not name the binding hash: see I3-m2.

**I2-m5 (partially resolved):**
- The sentence is now separate and gives the purpose (serial-vs-serial reproducibility).
- It swaps first and second: see I3-m1.

## What was checked and how

- **Diff:** read `git diff 71b0e3b..HEAD` in full (cli.py, compare.py, worker.py, test_harness.py, README,
  openmp-jacobian.md, validation log).
- **Source:** `ppp/parallel.F90:44-155` and `ppp/ppp.v:26-28`, to check the `ForceSerialCheck` wording.
- **Unit tests:** `python -m pytest -q tests/deterministic_omp/harness` gave `32 passed` on each of `base-omp`,
  `base-serial` and `AIUE-47-serial`.
- **AI-layer check:**
  - `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` printed `OK`. It also listed the advisory
    "re-read" list.
  - The only `.claude/` change in the delta is cf23ddf, with the trailer `AI-layer: code-facts`.
  - f46f7a4 touches no `.claude/` file. The delta changes no skill, agent or hook.
- **Live runs** (output in
  `/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev49r3/`).
  None of them gave an "inconsistent CSR" error.

  | Build | Preset / arm | Options | Exit | Notes |
  |---|---|---|---|---|
  | base-omp | tebox `jac`, 4 threads | `--repeats 1` | 1 | Expected MISMATCH, te/te; `errors: []` |
  | AIUE-47-omp (hook) | tebox `jacrhs`, 4 threads | `--repeats 1 --itermx 3` | 1 | `captured[0]`, `captured[1]` and the permuted post-exmain matrix all compared; `errors: []` |
  | base-serial | full `serial` | `--repeats 1` | 0 | AGREE; full-size post-exmain CSR accepted (5.5 min) |
  | AIUE-47-serial (hook) | tebox `serial` | `--repeats 1 --itermx 3` | 0 | AGREE, including both captured matrices |

- **Break script:** `rev49r3/break3.py` covers a short and a long `rowptr` (both give exit 2 through the
  neq/map checks on fake records) and a 0-d `rowptr` (`TypeError`, so exit 2).
- **Provenance:** `premeth` is `"ilut"` and `compiler` is `[]` on macOS in the live records.
