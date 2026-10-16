# AIUE-61 implementation review, round 3 (final)

Reviewer: uedge-reviewer (independent). Branch `bugfix/v9-AIUE-61-omp-static-partition`, tip `35bd907` (round 2
reviewed `4c3d095`; gated product `b717734`; base AIUE-60 `f8db593`). Reference: the approved plan
`.claude/plans/AIUE-61-omp-static-partition.md` (as amended) and the AIUE-61 acceptance criteria it maps. Inputs:
the round-2 report and response, commits `89a83b2`, `14bae93`, `35bd907`, and the run outputs in
`uedge-wt/scratch-AIUE-61/final/{i2m1b,i2m1_lldb,i2m1_chk,r4_donly2}/`.

## Verdict

**APPROVE.** There are no open BLOCKER or MAJOR findings.

## Summary

I2-M1 is resolved:
- The false "on the combined tree it passes" sentence is gone.
- The 5+5 repeat runs, the 7 lldb runs and the 2 bounds-checked runs are quoted correctly from their outputs.
- The root cause is real. I reproduced the trap myself: `MakeXptChunks` writes into a zero-extent `ylimsxpt` at
  `ppp/omp_parallel.F90:175`. That code is pre-existing: it is byte-identical in `f8db593`, present on
  `origin/v9-develop`, and dates from `fedca33`. AIUE-61's diff doesn't touch it.
- That code is reached only when `OMPParallelPandf1>0`. No Jacobian code path reads the X-point chunk arrays, and no
  Jacobian gate's driver turns the parallel RHS on, so the corruption cannot have affected any Jacobian gate.

I2-m1 and I2-m2 are resolved. The D_only ratios (×2.9 at 4 threads, ×3.4 at 8) recompute from the stored logs.

The only product change after the gates is description text for `OMPJacMinChunkLen` in `ppp/ppp.v`, with the default
`/300/` unchanged. The probe build shows the new text. Both hooks are clean.

There is one optional minor on the PR wording, and one observation for the owner about a separate pre-existing
bounds error that I found on D_only.

## Findings

### BLOCKER
None.

### MAJOR
None.

### MINOR

**I3-m1 (optional). The PR line describes the AIUE-70 defect more narrowly than the hand-off does.**
- **Where:** the plan's PR list (`.claude/plans/AIUE-61-omp-static-partition.md:461-463`) and the PR-line quote in
  `AIUE-61-validation.txt`.
- **What is narrow:** the line says "the parallel-RHS *self-check* on small grids is affected". In fact the
  out-of-bounds write happens in `InitOMPPandf1` → `Make2DChunks` → `MakeXptChunks` for **any** run with
  `OMPParallelPandf1=1` where `MAXVAL(Nxptchunks)=0`. That is the default whenever `iysptrx1 < 5`, and also when
  `iysptrx1 = 1` whatever the user sets, because of `MIN(Nxptchunks, iysptrx1-1)`. The self-check is not required.
- **Other writes:** lines 189-190 also write at index `Nxptchunks(ixpt)=0`, below the lower bound. `dyxpt` is `0/0`.
- **Accuracy elsewhere:** the AIUE-70 hand-off bullet in the record already states the general case correctly.
- **Resolve (optional):** say "parallel-RHS runs (`OMPParallelPandf1=1`) on grids with `iysptrx1 < 5`".

### Observation for the owner (not a finding against AIUE-61)

My second allowed run used the bounds-checked build in `jac` mode (`OMPParallelPandf1=0`) on D_only. It stopped
before any Jacobian, inside the **serial** `pandf`:

```
At line 603 of file ../../bbb/pandf_plasma_energy.F
Fortran runtime error: Index '2' of dimension 3 of array 'ng' above upper bound of 1
```

- **Where it comes from:** `bbb/pandf_plasma_energy.m:603` (also lines 697 and 701) reads `ishymol*ismolcrm*ng(ix,iy,2)`
  when `ngsp=1`. This is an out-of-bounds read multiplied by a zero flag.
- **Pre-existing:** the same lines are on `origin/v9-develop`, and `git diff f8db593..HEAD -- bbb` is empty.
- **Why it matters:** with checkbounds, D_only cannot be used as a test case until this is fixed. In normal builds it
  reads a deterministic neighbouring value times 0. If that value is ever Inf or NaN, the product is NaN.
- **What to do:** the owner may want a separate bug ticket. It does not touch AIUE-61's gates: G10 ran its
  checkbounds cases on tebox and the full problem.

## Status of previous findings

| Finding | Status | Evidence (checked myself) |
|---|---|---|
| **I2-M1** `CheckPandf1` claim did not reproduce; exit-133 crash unexplained | **Resolved** | See below. |
| **I2-m1** R4: D_only time missing; stand-in caveat | **Resolved** | See below. |
| **I2-m2** ompcheck docstring inverted | **Resolved** | See below. |

**I2-M1: what I checked.**
1. **The corrected record.** `AIUE-61-validation.txt` G9a no longer claims a pass for `CheckPandf1`. It labels the old
   sample "CORRECTED ... does NOT reproduce".
2. **The repeat runs.** I compared the record line by line with `final/i2m1b/summary.txt`. Both say:
   - AIUE-61-omp `pandf1`: exit 133 for runs 1, 4 and 5; runs 2 and 3 exit 0 with `CHECK FAILED pandf1 RuntimeError
     diff in rhsnk | NchunksJac 1`.
   - AIUE-60-omp `pandf1`: runs 1 and 3 exit 0 FAILED; run 2 exits 139 after the FAILED line; runs 4 and 5 exit 133.
   - Every FAILED run shows `>>>> 76 2032.0288514119870 2032.0288330644739 9.0291597447081350E-009`.
   - `jac`: 5/5 `CHECK OK jac iterm 4` on each build (NchunksJac 1 vs 420).
3. **Where the crashes happened.** The record says "two runs before any solver output, others after the first
   exmain". The logs agree:
   - AIUE-61 run 1 and AIUE-60 run 5 end at "Reading grid from file:gridue", with 0 `iter=` lines.
   - The other 133 runs end at "Interpolants created" after "Serial and parallel pandf are identical for nfe = 1".
4. **The lldb runs.** `i2m1_lldb/try1-7` all print `CHECK FAILED pandf1 ... NchunksJac 1`. Tries 1, 3 and 4 then stop
   with `EXC_BAD_ACCESS` in `H5FL_garbage_coll` ← `H5FL_term_package` ← `H5_term_library` ← `exit`. Tries 2 and 5-7
   exit with status 0. This matches the record.
5. **The bounds-checked build.** `i2m1_chk/AIUE-61-chk_{1,2}/run.log` both show `At line 175 of file
   ../../ppp/omp_parallel.F90 / Fortran runtime error: Index '1' of dimension 3 of array 'ylimsxpt' above upper bound
   of 0`. I **reproduced** this with the round-3 run 1: `AIUE-61-ompcheck_rep.sh /tmp/aiue61-r3 AIUE-61-chk pandf1 1`
   gave exit 2 and the same two lines verbatim.
6. **The out-of-bounds write is real.** I read the code:
   - `InitOMPPandf1` (`ppp/omp_parallel.F90:415-418`) sets `Nxptchunks = int(iysptrx1/5)` when it is 0.
   - The D_only `gridue` header is `8 4 2 6 1`, so `iysptrx1 = 1` and `Nxptchunks = 0`.
   - `MakeXptChunks` clips it to `MIN(0, 0) = 0` and allocates `ylimsxpt(nxpt,2,0,2)` (lines 150-152).
   - It then writes unconditionally to `ylimsxpt(ixpt,1:2,1,1:2)` at lines 175-176, and to `(...,0,2)` at lines
     189-190.
7. **It is pre-existing.**
   - `git show f8db593:ppp/omp_parallel.F90 | sed -n 133,214p` is identical to the tip.
   - `git diff origin/v9-develop..HEAD -- ppp/omp_parallel.F90 | grep -c 'ylimsxpt|Nxptchunks|MakeXpt'` gives 0.
   - The same statement exists in `fedca33` ("Adds working X-point chunking"), which is an ancestor of `f8db593`.
   - AIUE-61's hunks in this file are in `InitOMPJac` (line 312) and in the Jacobian driver (lines 513-807).
8. **It is reached only on the parallel-RHS path.** `InitOMPPandf1` is called only from `ppp/parallel.F90:37`, inside
   `if (OMPParallelPandf1.gt.0)`, and from `OMPPandf1Rhs` (line 1045). `OMPPandf1Rhs` is reached only through
   `PandfRHS_interface` when `ParallelPandf1>0` (`bbb/pandf.m:19-21`). The default is `OMPParallelPandf1 /0/`
   (`ppp/ppp.v:6`, unchanged).
9. **The record's other claims hold.** The one-chunk hypothesis is withdrawn with evidence: 9 completed AIUE-61 runs
   all fail identically to AIUE-60. That is a fair reading, and an earlier batch `final/i2m1/` shows the same thing.
   The AIUE-70 hand-off and the PR line are present. Round 2's suggested PR line about run-to-run variance with
   `NchunksJac < Nthreads` is rightly replaced, because the hypothesis behind it was refuted.

**Could the corruption have affected a Jacobian gate? No.**
- **No shared arrays.** `grep` for `InitOMPPandf1|Make2DChunks|OMPPandf_XPT|rangexptchunk` finds uses only in
  `ppp/omp_parallel.F90`, in the chunk module and in `OMPPandf1Rhs`. None is in `InitOMPJac`, `jac_calc_parallel` or
  the OMPJac builder.
- **No gate driver turns the parallel RHS on.** Among the gate drivers, only `AIUE-61-ompcheck.py` in `pandf1` mode
  sets `OMPParallelPandf1=1`. `AIUE-61-pytests_omp.py:28` sets it to 0. `jworker`, `timing`, `shared-full`,
  `state_probe` and `conv_worker` never set it, so the default of 0 applies. No pytests `input.py` mentions it.
- **No carry-over between runs.** Every gate run is a fresh process (`env -i`, empty `HOME`), so heap corruption in a
  `pandf1` run cannot carry into a Jacobian run.

**I2-m1.**
- `final/r4_donly2/*/run.log` give the following first-Jacobian `ttjstor` values:

  | Threads | NEW (s) | OLD (s) | Ratio of medians |
  |---|---|---|---|
  | 4 | 0.0467, 0.0468, 0.0468 | 0.0152, 0.0161, 0.0163 | 0.0468 / 0.0161 = ×2.91 |
  | 8 | 0.0508, 0.0536, 0.0550 | 0.0146, 0.0156, 0.0161 | 0.0536 / 0.0156 = ×3.44 |

  These match the record's ×2.9 and ×3.4, with NchunksJac 1 for NEW and 420 for OLD.
- The stand-in caveat sentence is present and says what I asked for.
- The `ppp.v` text ("up to neq~5000 at 8 threads ... ~2x (neq<600: 1 chunk, ~3x) ... lower it or use 0") is consistent
  with R4's ×1.43/×2.12 and the D_only ×2.9/×3.4.
- `openmp-jacobian.md:56-59` and the plan's PR list say the same. Default `OMPJacMinChunkLen` stays `/300/`, as the
  owner directed.

**I2-m2.** `docs/reviews/AIUE-61-ompcheck.py:1-11` now says `jac` is GATING and `pandf1` is REPORT ONLY. The new
`AIUE-61-ompcheck_rep.sh` records `exit=$rc` per run.

**Product change after the gates.**
- `git diff b717734..35bd907 -- ppp bbb api com aph wdf grd flx svr ncl setup.py Makefile.Forthon src` shows only
  `ppp/ppp.v`. Three description lines changed, the line count is the same, and `/300/` is unchanged.
- The commit with the change, `89a83b2`, is at 20:44:22. The probe's `ppppy.so` was built at 20:43.
  `ppp.getvardoc('OMPJacMinChunkLen')` from `venvs/AIUE-61-probe` prints the new three-line text, which I checked
  myself.
- Since the change is text after `#` in a `.v` description, it cannot change compiled behaviour.
- I did not find the 20:43 build log: `build_probe.log` is from 13:48. So "no warnings in ppp/*" and the hash
  `8761cd9e36658ee1` on the probe rest on the record. See the next section.

**AI-layer.**
- `14bae93` touches `.claude/context/openmp-jacobian.md` only and carries `AI-layer: code-facts`.
- `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` prints its advisory list and `OK` (rc 0).
- `uv run .claude/hooks/change_kind.py --range f8db593..HEAD` reports a ticket branch with product files `ppp/{omp_parallel,parallel}.F90` and `ppp/ppp.v`, and
  `OK` (rc 0). There are no changes to skills, agents or hooks.

## Not independently verified (environment)

- **The probe build log and the description-change hash.** The 20:43 probe build log is not in the scratch directory,
  and I did not re-run the full problem: it is outside the 2-run budget, and the change is comment text. What I
  checked: the diff is description-only, the probe library postdates nothing relevant and shows the new docstring,
  and the default value is unchanged.
- **The quiet rule for the D_only timing** (`r4_donly2`): no load record is stored with these runs. The spread is
  tight (NEW at T=4 is 0.0467-0.0468), and the item is report-only.
- **The AIUE-70 hand-off and the owner's AIUE-73 follow-up** exist in the record and the plan. I have no Jira
  access, so I could not confirm that they were filed.
- **No gating run was repeated** apart from the two runs below. Everything else is as accepted in round 2.

## What was checked and how

- **Branch and commits:**
  - `git log f8db593..HEAD`, `git diff 4c3d095..35bd907 --stat`, and `git diff b717734..35bd907 -- <product dirs>`.
  - `git show` of `89a83b2`, `14bae93` and `35bd907`: trailers and files.
- **Code:**
  - `ppp/omp_parallel.F90:1-25` (`Make2DChunks`), `133-214` (`MakeXptChunks`), `342-443` (`InitOMPPandf1`) and
    `957-1051` (`OMPPandf1Rhs`).
  - `ppp/parallel.F90:20-43` and `bbb/pandf.m:7-26`.
  - `git diff f8db593..HEAD -- ppp/omp_parallel.F90` (hunk locations).
  - `git show fedca33:` and `origin/v9-develop:` greps.
  - The D_only `gridue` header.
- **Run outputs:**
  - `final/i2m1b/summary.txt` and the run-log tails of every exit-133/139 run.
  - `final/i2m1/summary.txt`.
  - `final/i2m1_lldb/try1-7/lldb.log` (stop reasons and frames).
  - `final/i2m1_chk/*/run.log`.
  - `final/r4_donly2/*/run.log`.
- **My runs (2, at 4 threads, on D_only):**
  1. `AIUE-61-ompcheck_rep.sh /tmp/aiue61-r3 AIUE-61-chk pandf1 1` → exit 2, trap at `omp_parallel.F90:175`
     (`ylimsxpt` dim 3 upper bound 0).
  2. `... AIUE-61-chk jac 1` → exit 2, a pre-existing serial trap at `pandf_plasma_energy.F:603` (`ng` dim 3 index 2 > 1),
     before any Jacobian (see the Observation).
- **Import-only check:** `ppp.getvardoc('OMPJacMinChunkLen')` in `venvs/AIUE-61-probe`.
- **Hooks:** `check_context_refs.py --changed origin/v9-develop` (OK) and `change_kind.py --range f8db593..HEAD` (OK).
