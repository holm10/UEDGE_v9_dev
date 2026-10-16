# AIUE-49 implementation review, round 2

Ticket: AIUE-49 "Harness core: fresh-process runner, capture, bitwise compare, localise" (epic AIUE-8).
Branch `feature/v9-AIUE-49-omp-harness-core`. New commits since round 1: `git diff e1f5808..HEAD` (8fddd95 fixes,
71b0e3b code facts). Inputs: the round-1 report, the authors' response, and validation part 3.

## Verdict

**APPROVE**

## Summary

The one blocker and all five majors from round 1 are resolved. I re-ran my round-1 attacks and live runs against the new
code; none of them reproduces. A serial build, or `--repeats 0`, now gives exit 2. The ±0 rule covers the exmain `yldot`.
The permuted post-`exmain` Jacobian is labelled and is not mapped to cells. Duplicates, one-sided quantities, differing
maps or specs, and out-of-range indices are no longer AGREE. Unexpected exceptions and corrupt files give exit 2.

The provenance now identifies the build under test (source tree, HEAD, extension SHA-256, OpenMP runtime). The stated
deviation, that compiler and flags are not recorded, is technically justified: I found no compiler string or flags in the
Mach-O extensions. The extension hash binds a record to the exact binary. The owner should still acknowledge the deviation
in the PR.

Five new MINOR points on the new code. The one that matters for the sibling tools: `cli.exit_code([])` returns 0.

## Findings

### BLOCKER

None.

### MAJOR

None.

### MINOR (new code only; optional)

**I2-m1: `cli.exit_code([])` returns 0 (AGREE).** Location: `cli.py:44-48`.
- `all([])` is True, so an empty report list counts as agreement. This is the same vacuous-truth pattern as I1-B1.
- `cmd_check` cannot reach it now, because `--repeats >= 1` is enforced.
- But AIUE-52 (flow) and AIUE-53 (serial check) will call `exit_code` on lists they build themselves.
- Acceptance: an empty list returns 2, with a unit test.

**I2-m2: the permuted post-`exmain` section prints made-up cell coordinates.** Location: `compare.py`, the `loc=False`
branch (`np.stack([ident, ident])` passed as `igyl`).
- Live output (Te box, `jacrhs`, `--itermx 3`): `first value row ?(ix=0,iy=0) col ?(ix=5,iy=5)`.
- The `note` says the indices are not cells, but the formatted line reads like a cell (5,5).
- Acceptance: print the permuted position (e.g. `perm-iv 6`), not `ix=,iy=`.

**I2-m3: the CSR row pointer is not validated.** Location: `compare.py` `csr_entries`/`matrix_mismatch`.
- Only column and row ranges are checked.
- Several inconsistencies are not caught: `len(rowptr) != neq+1`, `rowptr[0] != 1`, a decreasing pointer, and
  `rowptr[-1]-1 != len(values) != len(cols)`.
- My example: b has `jaci=[1,2,2]` with two values. `np.repeat` gives one row, which broadcasts against two columns, and the
  result is a MISMATCH built on wrong keys. In other shapes the same fault raises `ValueError` from `compare_records`.
- Worker records are consistent by construction, so this only matters if the capture hook stores a bad `jaccapnnz`.
- Acceptance: check these invariants, and report a violation as an `errors` entry.

**I2-m4: provenance details.** Location: `worker.py` `build_identity` and the provenance dict.
- `premeth` is recorded as the string `"[b'ilut    ']"`, because `bbb.premeth` is an ndarray, not bytes.
- `source_head`/`source_dirty` are the source tree's state *when the run happens*, not when the build was made. Another
  agent can commit to or rebuild the AIUE-47 tree between install and run. The README should say that
  `extensions_sha256` is the binding identity.
- The `build_identity` docstring says it records the compiler "from the .comment strings". The README says the compiler is
  not recorded. In fact the field is `[]` on macOS and would be filled on Linux ELF, so the two texts disagree.
- Optional: record the linked runtime libraries (`otool -L`/`ldd`). This gives a partial compiler identity, e.g.
  `/opt/homebrew/opt/gcc/lib/gcc/current/libgfortran.5.dylib`.

**I2-m5: the new `ForceSerialCheck` wording in `openmp-jacobian.md` is incomplete.** Location:
`.claude/context/openmp-jacobian.md:45-47`.
- What `ForceSerialCheck` actually does (`ppp/ppp.v:26-28`, `ppp/parallel.F90:84-110`): after the OpenMP Jacobian, it
  computes the *serial* Jacobian twice, into `jac` and into `jaccopy`. It compares the two (a serial reproducibility check)
  and aborts on a difference.
- The new text puts it in a parenthesis inside the `CheckJac` sentence, as "replaces the solver's Jacobian with the serial
  one". The side effect is described correctly, but the purpose is missing, and the placement suggests it is part of
  `CheckJac`.
- Acceptance: one sentence giving its own purpose.

## Status of previous findings

| ID | Status | Evidence (re-checked myself) |
|---|---|---|
| I1-B1 AGREE when no OpenMP ran | **Resolved** | See below the table. |
| I1-M1 ±0 rule missing on RHS-arm `yldot` | **Resolved** | See below the table. |
| I1-M2 permuted post-exmain Jacobian | **Resolved** | See below the table. |
| I1-M3 comparator AGREEs on differing inputs | **Resolved** | See below the table. |
| I1-M4 exit-code contract | **Resolved** | See below the table. |
| I1-M5 provenance | **Resolved (deviation accepted on technical grounds)** | See below the table. |
| I1-m1 `fnrm_final`, probe order | Resolved | The probe now runs before `get_fnrm`. The README "Limits" describe `fnrm_final` correctly. |
| I1-m2 default is one evaluation | Resolved (documented) | The README names `--itermx 3` as the ticket's measurement. The records carry `ijactot` and the caller list. I confirmed the `--itermx 3` record holds 4 iterations and 2 Jacobians. |
| I1-m3 diagnostics | Resolved | `RunSpec.validate` rejects them. The worker sets them to 0 and records them. `check_arm` enforces them. A test covers this. |
| I1-m4 probe buffer | Resolved | `yl[:neq+2]` and an `neq+2` output buffer (`worker.py:203-210`). The live probe ran. |
| I1-m5 docs | Partially resolved | The `runner.py` comment, the `CheckPandf1` description and the validation exit codes are fixed. The new `ForceSerialCheck` wording is incomplete (I2-m5). |
| I1-m6 probe in Limits | Resolved | README "Limits". |

**I1-B1 (resolved):**
- `base-serial` on the `jac` and `jacrhs` arms gave `CHECK ...: ERROR` and exit 2. The reasons were printed:
  `ParallelJac=0`, `ParallelPandf1=0`, probe not parallel, no OpenMP runtime.
- `--repeats 0` gave `HARNESS ERROR: --repeats must be >= 1` and exit 2.
- `ParallelJac=1` together with an OpenMP runtime is sufficient: the dispatch at `bbb/oderhs.m:4696` is unconditional on
  `ParallelJac`.
- On the hook build, the `jacrhs` sources were `['jac_calc_parallel', ...]` and the serial sources were `['jac_calc', ...]`.
- The `Nthreads` check is meaningful, because `ppp/omp_parallel.F90:298-302` clamps `Nthreads` to the available threads.

**I1-M1 (resolved):**
- The auto rule now covers `yldot` and `yldot_probe` whenever either record has `ParallelPandf1>0`, and counts
  `signed_zero_differences`.
- `sfscal` with ±0 on `jacrhs` is still a mismatch (my break2 script). That is correct: the rule is limited to RHS vectors.
- Serial vs serial still counts the sign of zero (unit test).

**I1-M2 (resolved):**
- In the live Te box `jacrhs --itermx 3` run (AIUE-47-omp), the record has `post_exmain_from=psetnk` and
  `post_exmain_permuted=True`.
- The section is named `post_exmain (permuted indices)` and is not mapped to cells. The captured matrices (natural order)
  are localised `te/te`.
- The run with ijactot=1 is labelled `sfsetnk`, unpermuted.
- The false "no psetnk" meta string is gone. Cosmetic issue: I2-m2.

**I1-M3 (resolved):**
- Results of `rev49/scripts/break_compare.py` against the new code:
  - duplicate: MISMATCH (1 and 1b);
  - one-sided probe: MISMATCH;
  - differing eq/igyl: error;
  - no iterations: error;
  - differing spec: error;
  - hook vs no hook: error;
  - column > neq: error, exit 2 (`break2.py`).
- Unit test: `test_duplicates_one_sided_and_missing_are_not_agree`.
- Still AGREE: NaN `fnrm_final` hex on both sides. This is unchanged material, and in practice the non-finite check on
  the vectors catches it, so I raise no finding.

**I1-M4 (resolved):**
- A truncated `record.npz` gives `HarnessError` and exit 2.
- A record without provenance gives exit 2.
- A planted `ZeroDivisionError` gives exit 2 (unit test).
- Truncation is in `errors`, so it exits 2.
- Out-of-range columns are validated before keys are built. The old aliasing bug is gone.

**I1-M5 (resolved, deviation accepted on technical grounds):**
- Recorded: `build.source_dir` (`.../uedge-wt/AIUE-47` for the AIUE-47 venv, `.../base-omp` for base-omp), `source_head`,
  `source_dirty`, `extensions_sha256` over 11 modules, `openmp_build`, plus `harness_commit` and `harness_dirty` separately.
- On the deviation: `strings` on `bbbpy...darwin.so` finds no GCC or clang version string and no flags, and `otool -L`
  shows only the linked libraries.
- The README "Limits" states the deviation. The owner should acknowledge it in the PR. Details: I2-m4.

## What was checked and how

- **Diff:** read `git diff e1f5808..HEAD` in full (cli, compare, config, runner, worker, tests, README, context file,
  validation log).
- **AI-layer check:** the only AI-layer change since round 1 is `.claude/context/openmp-jacobian.md`, in 71b0e3b with the
  trailer `AI-layer: code-facts`. 8fddd95 touches no `.claude/` file. There are no skill, agent or hook changes.
  `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` printed `OK`.
- **Unit tests:** `venvs/base-omp/bin/python -m pytest -q tests/deterministic_omp/harness` gives `29 passed`. I read
  every new test and judged them sensitive to the round-1 bugs: each planted condition asserts a specific error string or
  section count.
- **Round-1 break script:** `rev49/scripts/break_compare.py` re-run. Results are under I1-M3 and I1-M4 above.
- **New break script:** `rev49r2/scripts/break2.py` covers the column > neq exit code, an inconsistent row pointer, a
  missing `openmp_build`, `exit_code([])`, ±0 on `sfscal`, and the one-sided probe.
- **Live Te-box runs**, output under
  `/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev49r2/`:

  | Build | Arm | Options | Exit |
  |---|---|---|---|
  | base-omp | serial | `--repeats 2` | 0 |
  | base-omp | jac, 4 threads | `--repeats 2` | 1 |
  | base-serial | jac | | 2 |
  | base-serial | jacrhs | | 2 |
  | base-omp | jac | `--repeats 0` | 2 |
  | AIUE-47-omp | jacrhs, 4 threads | | 1 (te/te rows named, sources `jac_calc_parallel`) |
  | AIUE-47-omp | jacrhs | `--itermx 3` | 1 (permuted labelling checked) |
  | AIUE-47-serial | serial | `--itermx 3` | 0 (permuted post-exmain equal serial vs serial) |

  Both AIUE-47 venvs imported with the hook present. No full-problem run was needed: the Te box with `--itermx 3` exercises
  `psetnk` and the reorder.
- **Source checks:**
  - `bbb/oderhs.m:4694-4702` (dispatch on `ParallelJac`);
  - `ppp/parallel.F90:4-43`, `:44-150` (`jac_calc_parallel`, `ForceSerialCheck`, `CheckJac`), `:348-365` (`Compare`);
  - `ppp/omp_parallel.F90:290-310` (the `Nthreads` clamp);
  - `ppp/ppp.v:26-28`.
- **Binary check:** `otool -L` and `strings` on `venvs/base-omp/.../uedge/bbbpy.cpython-313-darwin.so`, for the compiler
  deviation.
- **Not verified:** the README claim that phi with ni+up, with ni+up+ti, and the full problem without Te all fail in serial
  (heavy runs, outside the budget). The `te_phi` serial run in validation part 3 (neq 6336) is consistent with the
  preset working.
