# AIUE-47 Raw-Jacobian capture hook: implementation review, round 2

Reviewer: uedge-reviewer (independent). Branch `feature/v9-AIUE-47-raw-jacobian-capture` at f7f6e8b. The Fortran
under review is 3625b48: `bbb/oderhs.m` `jac_capture` and the `bbb/bbb.v` text. No `.m`, `.v`, `.F90` or build
file changes after it. Round-1 report: `docs/reviews/AIUE-47-implementation-round1.md`. Response:
`docs/reviews/AIUE-47-implementation-round1-response.md`.

## Verdict

**APPROVE**: no BLOCKER or MAJOR findings are open. Two optional MINOR findings concern new text and new tool code.

## Summary

The round-1 MAJOR (L-M1, all `jaccapture` slots allocated up front) is fixed. The slot dimension now grows by
doubling, capped at `jaccapture`, and only when the slot being filled does not exist yet. I checked the
growth rule by reading the code, by reading Forthon's `gchange`, and with my own script. That script makes nine
captures on D_only and alternates `neq` between 300 and 420. At capture 2 the leading dimensions (nnz, neq+1)
and the slot dimension all grow in one `gchange`. Every earlier slot stayed bitwise intact through every growth
(1→2→4→8→16). I reran default-off AC1 myself on four cases (full reproducer `ftol=1e20` and D_only 3 Newton
iterations, each on the serial and the OpenMP build). All four match `v9-develop` bit for bit. The AC2 identity
holds on serial `jac_calc` (D_only, every slot) and on `jac_calc_parallel` (Te box). The memory figure of
16·nnz + 8·(neq+1) bytes per slot is correct: integers are 8 bytes in this build. The three round-1 MINORs are
fixed.

## Findings

### BLOCKER

None.

### MAJOR

None.

### MINOR

**R2-m1: The `jaccapnslot` description claims a bound that does not always hold.**
- Location: `bbb/bbb.v:4247`, `jaccapnslot ... # No. of allocated slots (>= jaccapn, <= jaccapture)`.
- Problem: `jaccapnslot` never shrinks, and `gfree` does not reset it. It can therefore exceed `jaccapture` in two
  cases: when the user lowers the cap after slots were allocated, and after a counter restart. In my script,
  step F (`jaccapture=6` after 8 slots were allocated) gave `nslot 8`. Step G (restart with `jaccapture=3`)
  also gave `nslot 8`. After `gfree` the next capture reallocates all `jaccapnslot` slots, not one (step H:
  shape (8197, 8)). This is harmless, but the stated upper bound is wrong.
- Acceptance: say "<= the largest `jaccapture` in effect when it grew; not reset by `gfree`", or drop the upper
  bound.

**R2-m2: The tool's `alloc_slots_bounded` check assumes a single fresh capture sequence.**
- Location: `tests/deterministic_omp/tools/capture_check.py` `child()`, the check
  `nstored <= nslot <= min(jaccapture, max(1, 2*nstored))`.
- Problem: the check is correct for the tool's own use (one deck, one `exmain`, fresh process). A later ticket
  that reuses the child with more than one `exmain` and a counter restart would get a false FAIL, because
  `jaccapnslot` is kept from the earlier sequence (see R2-m1).
- Acceptance: add a comment that the check is valid only for a fresh process with one capture sequence. No code
  change is needed for this ticket.

## Status of previous findings

| Round-1 finding | Status | Evidence (my own) |
|---|---|---|
| **L-M1** (MAJOR) eager allocation | **Resolved** | See the analysis below. |
| **I-m1** (minor) tool passes when nothing was captured or checked | **Resolved** | See the analysis below. |
| **I-m2** (minor) "raw d(yldot)/d(yl)" overstated | **Resolved** | See the analysis below. |
| **I-m3** (minor) behaviour after `gfree` undocumented | **Resolved** | See the analysis below. |

**L-M1, resolved.**
- **Code.** `bbb/oderhs.m:4775-4777`: `if (islot .gt. jaccapnslot) jaccapnslot = min(jaccapture, max(islot, 2*jaccapnslot))`.
  `islot <= jaccapture` is guaranteed by the earlier return, so the new value is always `>= islot`: no
  out-of-bounds write is possible. When the slot already exists, the value is unchanged.
- **Forthon.** `gchange` in `Forthon/Forthon.h` (`ForthonPackage_gchange`) takes the minimum of each dimension
  separately, then calls `PyArray_CopyInto`. The overlap is therefore kept when both dimensions grow at once.
- **Own script, `edge3.py`, serial build, D_only.** Nine `ftol=1e20` captures with `isupon` = 0,1,1,0,1,0,1,1,0.
  `nslot` went 1,2,4,4,8,8,8,8,16. At capture 2, `nnzmx` went 5335→8197 and `neqp1` 301→421 while `nslot` went
  1→2. "All prior preserved" was True after every capture: the SHA-256 of each slot's v/j/i, recorded when the
  slot was stored, matched again after each later growth.
- **`jaccapture=1000`, one Jacobian.** One slot is allocated: D_only 87768 B (`edge2.py` step A), and the Te box
  on the OpenMP build with the parallel Jacobian gives shape (180, 1).
- **Docs.** The `.v` text, the plan and `openmp-jacobian.md` all document the cost.

**I-m1, resolved.**
- **Negative test (rerun).** D_only, `issfon=0`, `--capture 4` exits 1 with `captured_at_least_one = False` and
  `identity_evaluated = False`.
- **Code reading.** A lost caller tag sets `identity_evaluated=False` in ftol mode. A pattern mismatch sets
  `check_pattern_equal_bbb_jacj_jaci=False`, which also fails the run.

**I-m2, resolved.** I checked each statement in the new `.v` text against the source:
- `-1/dtuse` is subtracted at `bbb/oderhs.m:1173` and `ppp/parallel.F90:270`.
- `-1/dtphi` is subtracted at `bbb/oderhs.m:1177-1178` and `ppp/parallel.F90:274-275`.
- `-nufak` is subtracted at `bbb/oderhs.m:1183-1185` and `ppp/parallel.F90:280-281`.
- The row/column statement is correct. In both routines `iv` is the perturbed variable (the matrix column) and
  `ii` is the equation (the row). Serial `jac_calc` clips with `sfscal(ii)` (`bbb/oderhs.m:1187`), which is the
  row. `LocalJacBuilder` clips with `sfscal(iv)` (`ppp/parallel.F90:292`), which is the column.

**I-m3, resolved.**
- **Docs.** The `.v` group header, the `jac_capture` comment and `openmp-jacobian.md` state that the slots are
  lost and that the counters must be reset.
- **Own script.** In `edge2.py` step H, a `gfree` followed by a counter reset and a capture gives a valid slot 1
  that passes the identity check. There was no crash. The remaining nuance is in R2-m1.

## Other checks of the new code (no finding)

- **Memory figure.** `bbb.jaccapj.itemsize = bbb.jaccapi.itemsize = 8` and `jacj` is int64 (`edge2.py`), so
  integers are 8 bytes. The formula 16·nnz + 8·(neq+1) gives:
  - D_only: 16·8194 + 8·421 = 134472 B. This matches the logged `bytes`.
  - Reproducer, serial: 16·3190290 + 8·44353 = 51399464 B (≈51 MB).
  - Reproducer, parallel: nnz 3672306, 59111720 B.
- **Peak during a growth.** Forthon allocates the new array before it frees the old one. The peak is therefore
  about old + new, at most 3× the slots filled. "Briefly holds old and new arrays" is accurate.
- **Bookkeeping (author's log, checked by eye).** In the serial Te box run, nnz grows 169→170 at slot 3 at the
  same time as `nslot` grows 2→4. The slot-1 and slot-2 hashes of `--capture 1000` equal those of the
  `--skip 0`/`--skip 1` runs (`7fa63967…`). This agrees with my D_only result.
- **Default-off cost.** The disabled path is unchanged: it is still a single `if (jaccapture .gt. 0)` in
  `jac_calc_interface`.
- **Provenance.**
  - The serial venv is from `AIUE-47-serial2` at 460aa5f. That tree's `bbb/oderhs.m` and `bbb/bbb.v` are
    identical to HEAD.
  - The OpenMP venv is from the `AIUE-47` worktree (clean, HEAD f7f6e8b).
  - Both generated `oderhs.F` files contain the new growth line (line 4777). They differ only in the `c!omp`
    lines.
  - Both `.so` files were built after the `.F` generation (01:25 → 01:29/01:30).
- **AI layer.**
  - `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` prints `OK` (exit 0).
  - The cited lines are correct: `bbb/bbb.v:4221`, 4260 and 4263, and `bbb/oderhs.m:4676`, 4716 and 4738.
  - The `.claude/context` commits b085978 and 460aa5f carry `AI-layer: code-facts`.
  - No skill, agent, hook or settings file changed.
  - `.claude/plans/` is an artifact path.
  - This is not a physics model, so no `physics-models.md` row is needed.

## What was checked and how

Output directory: `/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev47r2/`.

- **AC1, default off, full reproducer (44352 eq.), `ftol=1e20`, serial.**
  - Command: `capture_check.py compare`, base-serial against AIUE-47-serial.
  - Result: PASS. Every field is EQUAL, including `jac` b974ef0b…, `yldot` 64e38678… and
    `fnrm 0x1.eb37d428ec4f0p+0` (`ac1_serial_full.txt`, 11.5 min).
- **AC1, full reproducer, OpenMP build.**
  - Settings: `OMPParallelJac=OMPParallelPandf1=0`, 4 threads.
  - Result: PASS, the same hashes as serial (`ac1_omp_full.txt`).
- **AC1, D_only, 3 Newton iterations, serial.**
  - Result: PASS, fnrm sequence n=4 equal, `ijactot=2` (`ac1_serial_donly_newton.txt`).
- **AC1, D_only, 3 Newton iterations, OpenMP build.**
  - Settings: OMP switches 0, 4 threads, `incpset=1`.
  - Result: PASS, `ijactot=4` (`ac1_omp_donly_newton.txt`).
- **D_only regression suite, serial.**
  - Method: each of the 125 test files run in its own process, because `pytest-isolate` is not installed in the
    venvs. Run on base-serial and on AIUE-47-serial.
  - Result: identical outcomes. 116 pass. The same 9 fail or produce no output in both builds, so the failures
    are environmental and existed before this change (`pytest_donly_perfile*.txt`).
- **AC2, `jac_calc_parallel` (Te box, OpenMP build).**
  - Settings: `OMPParallelJac=1`, `--capture 1000`.
  - Result: `raw_times_inv_suscal_bitwise_eq_bbb_jac = True`, `jaccapnslot=1` (`ac2_omp_tebox.txt`).
- **AC2, serial `jac_calc` (D_only).** The identity holds for all nine captures in `edge3.py`. It is not vacuous:
  `suscal` is not all 1 and the raw values differ from `bbb.jac` (`edge2.py` step A).
- **Lazy growth and edge cases.** Covered by `ds/edge2.py` (steps A-H: growth, lowered cap, restart, `gfree`) and
  `ds/edge3.py` (per-slot preservation across growth). Output is in `edge2_serial.txt` and `edge3_serial.txt`.
- **I-m1 negative test.** Output in `im1_neg.txt` (exit 1).
- **Source reading.**
  - `jac_capture` and `jac_calc_interface` (`bbb/oderhs.m:4676-4803`).
  - `jac_calc` (`bbb/oderhs.m:1120-1200`) and `LocalJacBuilder` (`ppp/parallel.F90:230-300`).
  - The `Forthon.h` `gchange` copy logic.
  - The diff `d4c2fb9..HEAD` of `bbb/`, `.claude/` and `tests/`.
  - The ROUND 2 driver and its results in `docs/reviews/AIUE-47-validation.txt`.

Not independently verified: the `--debug`/`--checkbounds` builds, Linux/CI wheels, and MPI/PETSc. PETSc does
not reach `jac_calc_interface`, as established in round 1.
