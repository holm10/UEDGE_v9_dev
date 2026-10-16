# AIUE-49 implementation review, round 1

Ticket: AIUE-49 "Harness core: fresh-process runner, capture, bitwise compare, localise" (epic AIUE-8).
Branch `feature/v9-AIUE-49-omp-harness-core`, diff `483d57a..HEAD` (fbe0adf, 72fc76d, e1f5808).
Reference: the ticket's scope and acceptance criteria (no physics spec).

## Verdict

**REVISE**

## Summary

The harness is a well-built start. Runner isolation is real (I checked the child environment). The localiser is correct for
unpermuted matrices: a live round trip over all 44352 full-problem equations and the 25 Te-box equations found no errors.
The four acceptance runs reproduce (exit 0, 1, 2 as specified, Te rows named). But the tool can report AGREE when it measured
nothing. A serial build, or `--repeats 0`, gives `CHECK ... AGREE`, exit 0, for the `jac`/`jacrhs` arms although no OpenMP
code ran. The ticket requires a check that the parallel branch ran; this is not done. Several other paths give a wrong
answer:
- the ±0 rule is not applied to the exmain `yldot` on the RHS arm, so a correct fix would still exit 1;
- the post-`exmain` Jacobian is RCM-permuted after `psetnk`, but it is localised as if it were not;
- duplicate CSR entries, and sections present in only one record, are silently accepted;
- unexpected exceptions exit 1 ("mismatch") instead of 2;
- the provenance records the harness commit, not the build under test, and has no compiler or flags.

## Findings

### BLOCKER

**I1-B1: AGREE (exit 0) when no OpenMP code ran.** Location: `worker.py:148-174`, `compare.py:135-181`,
`cli.py:53-75`.
- **What is wrong:** for the `jac`/`jacrhs` arms the harness records `ParallelJac`, `ParallelPandf1` and
  `rhs_probe_parallel`, but never acts on them.
- **Evidence:**
  - With the serial build, `cli.py check --preset tebox --arm jacrhs --threads 4 --repeats 2 --python venvs/base-serial/bin/python`
    printed `CHECK tebox_jacrhs_t4_it0: AGREE`, exit 0.
  - The record says `ParallelJac: 0, ParallelPandf1: 0`, `rhs_probe_parallel: False`, and the log has only `iter=` lines.
    Every section was "equal" because serial was compared with serial.
  - `--repeats 0` gives `runs = []`, then `agree = all([]) = True`, so it prints AGREE with only the serial reference run
    (`cli.py:56-69`).
  - With the hook, nothing checks that captured Jacobians came from `jac_calc_parallel`.
- **Why it matters:** the ticket asks for "a check that the parallel branch ran (`ijactot>0`, §6.1)". A harness whose job is
  to certify "OpenMP equals serial" must not pass a run in which OpenMP never ran. Pointing `--python` at the wrong venv is
  an easy mistake when the venvs are called `base-serial` and `base-omp`.
- **Acceptance:**
  - On non-serial arms, a run is a harness error (exit 2) unless `ParallelJac == 1`.
  - On `jacrhs`, it also needs `ParallelPandf1 == 1` and `rhs_probe_parallel` true.
  - With the hook, every captured `source` must be `jac_calc_parallel`.
  - `--repeats >= 1`.
  - Unit tests cover these paths, e.g. a FakeRecord with `ParallelJac: 0` on the `jac` arm must exit 2.

### MAJOR

**I1-M1: the ±0 rule is not applied to the RHS-arm `yldot` from `exmain`, so a correct fix would still fail.**
Location: `compare.py:163-165`; `test_harness.py:125-132` asserts the current behaviour.
- **Evidence:** I ran the full problem, serial vs `jacrhs` at 4 threads, it0 (base-omp).
  - The `yldot` section shows 2935 bitwise mismatches. 345 of them are pure ±0 (serial −0.0, parallel +0.0): all of the
    ni 255, ti 36, phi 14 and up 4 entries, plus 36 Te.
  - The serial record has exactly 345 negative zeros. No non-Te mismatch is anything other than ±0.
  - With ±0-equal, the probe drops from 2543 to 2198 mismatches, exactly the same 345 (`--rhs-signed-zero-equal no` vs
    `auto`). So `bbb.yldot` after `exmain` on this arm comes from the `REDUCTION(+)` path (`ppp/omp_parallel.F90:947-975`).
- **Why it matters:** this is the RHS-arm `yldot` that the ticket's P3-m2 exception exists for. Once the Te-row race is
  fixed, `serial` vs `jacrhs` will still exit 1 because of the `yldot` section.
- **Acceptance:**
  - Apply the same ±0 rule (auto, recorded in the section) to every `yldot` that the parallel RHS may have produced,
    including `yldot` on a `jacrhs` record, or stop comparing it on that arm and say so.
  - Fix the unit test, which currently enshrines the opposite.

**I1-M2: the post-`exmain` Jacobian is RCM-permuted after `psetnk`, but it is compared and localised as if it were not.**
Location: `worker.py:124-145`, `compare.py:123-132,161`.
- **The code path:** the deck uses `premeth="ilut"` and `ireorder` defaults to 1 (`bbb/bbb.v:2975`). In that case
  `jac_lu_decomp` calls `jac_reorder`, which permutes `jac/jacj/jaci` in place with `dperm` (`bbb/oderhs.m:1307-1308,
  1402-1428`).
- **Evidence:** in my `jacrhs` Te-box it0 run (`run0`), `captured[1]` (raw psetnk) and `post_exmain` both have nnz 169, but
  their (row, col) position sets differ. The row lengths are permuted: `[4,6,6,6,4,6,9,9,9,...]` vs `[4,6,6,6,4,6,6,6,4,9,...]`.
- **Effects:**
  - For every run with a `psetnk` (all `--itermx` runs, and it0 runs that iterate, see I1-m2), the localiser maps
    permuted indices through `igyl`, so the cell/equation names for `jacobian:post_exmain` are wrong.
  - Two runs with different patterns (the OpenMP arm has "only-b" entries) can get different RCM orders. Their entries are
    then not compared like for like.
  - The meta string "ftol=1e20: no psetnk row normalisation or reordering" is also false for such runs: `jacrhs` it0 on the
    Te box did 2 Jacobians (`sfsetnk`, `psetnk`).
- **Acceptance:** either un-permute with `bbb.perm`/`qperm` (group `Jacreorder`) before saving, or do not localise or
  compare the permuted matrix as cells (label it). The description must come from what happened (e.g. the captured callers
  or the `ijactot` count), not from `itermx`.

**I1-M3: the comparator returns AGREE on inputs that differ.** Location: `compare.py:49-74,141-181`.
- **Evidence:** my script `scratchpad/rev49/scripts/break_compare.py` uses the author's FakeRecord.
  - **Duplicates:** b has a duplicate (0,0) entry with value 7.0 next to the matching 1.0. Result: AGREE.
    `duplicates = 1` is counted but `add()` ignores it, and `intersect1d` keeps only one copy.
  - **One-sided probe:** `yldot_probe` missing from a, garbage in b. Result: AGREE, because the section is skipped
    (`compare.py:166`).
  - **Missing iterations:** `iterations` absent from both records. Result: AGREE ([] == []). This happens if `run_spec`
    raised in `parse_iterations` after the worker had written `record.json`.
  - **Different maps or specs:** a different `eq`/`igyl` map or a different `spec` (preset, itermx) gives AGREE. Only a's
    map is used for localisation.
- **Why it matters:** duplicated or overlapping entries are exactly the kind of fault a chunked parallel CSR assembly can
  produce.
- **Acceptance:**
  - Duplicates are a mismatch.
  - A quantity present in one record only is a mismatch or a harness error.
  - Missing or empty `iterations` is a harness error.
  - Differing `eq`/`species`/`igyl` are a harness error (or a mismatch). Spec differences other than arm, threads and ppp
    are reported.
  - Each case has a unit test.

**I1-M4: the exit-code contract is broken. Unanticipated failures exit 1 ("mismatch"), and truncation is not 2.**
Location: `cli.py:102-106`, `compare.py:152-154`.
- **Uncaught exceptions:** `main` catches only `HarnessError, ValueError, OSError, KeyError`. Anything else escapes, and
  Python exits 1, the same code as a real mismatch. Demonstrated:
  - a truncated `record.npz` raises `zipfile.BadZipFile`, which is uncaught;
  - a column index out of range raises `IndexError` in `_eqname`, uncaught. Worse, the `r*neq + c` key aliases an
    out-of-range column onto the next row before the crash;
  - an `igyl` with the wrong shape raises `IndexError`.
- **Truncation:** the README says capture-slot truncation is "a harness error, never a silent truncation". But it is added
  as a section with `error`, which makes `agree` false and gives exit **1**.
- **Acceptance:**
  - Any unexpected exception in `run`/`compare`/`check` gives exit 2 with the traceback.
  - Truncation gives 2.
  - Column indices are validated to 1..neq (or the key uses stride `neq+1`).
  - A test plants a non-`HarnessError` failure.

**I1-M5: the provenance identifies the wrong code and omits compiler and flags.** Location: `worker.py:28-33,157-174`.
- **Wrong commit:** `git -C HERE rev-parse HEAD` is the commit of the harness source tree, not of the build passed with
  `--python`. Every run I made with `venvs/AIUE-47-omp` recorded `commit e1f5808...` (AIUE-49 HEAD), but that build was
  installed from `/Users/holma/Documents/uedge/src/uedge-wt/AIUE-47` (its `uedge-8.1.2b0.dist-info/direct_url.json`).
  `uedge_ver` ("8.1.2-beta.0") does not tell builds apart. Dirty state is not recorded.
- **Missing fields:** the ticket's Record item explicitly lists "compiler and flags", and the author states the omission.
- **Acceptance:**
  - Record the build identity: the source dir from `direct_url.json` plus its HEAD and dirty flag, and/or a hash of the
    `uedge/*.so`.
  - Record the harness commit separately, with its dirty flag.
  - Record the compiler version and build options. At minimum, record OpenMP vs serial as observed in-process; it is also
    needed for I1-B1.
  - If any field cannot be obtained without product changes, the ticket owner must accept the deviation in writing. The
    README "Limits" must say so.

### MINOR

**I1-m1: no float64 `fnrm` per iteration, and `fnrm_final` is not the solver's value on the RHS arm.**
- `get_fnrm` calls the serial `pandf` and multiplies by `sfscal` (`bbb/ext_neutrals.m:1183-1189`).
- On full `jacrhs` it0, `fnrm_final` = 1.5354191116483673 (equal to the `jac` arm's printed value) while nksol printed
  1.535419111648431. So it fingerprints the state, not the parallel-RHS norm.
- It also overwrites `bbb.yldot` and `dtuse` (never restored) before the probe runs.
- Acceptable as a documented deviation, because the captured Jacobians and the final state are compared bitwise. Doing so
  needs the README to describe `fnrm_final` accurately and the probe to run before `get_fnrm`. Per-iteration float64 values
  could be had Python-only from `itermx=k` prefix runs, if wanted.

**I1-m2: the default measured run is one evaluation, and "it0" can silently iterate.**
- The ticket asks for the `fnrm` sequence over at least 3 Newton iterations. The default `check` runs `itermx=None`, and
  nothing checks that the requested number of iterations happened.
- On the Te box `jacrhs` arm, the iteration-0 `fnrm` was 7.29e+31, above ftol=1e20, so nksol took a step and a second
  Jacobian. The label still says `it0`.
- Acceptance: either default to `--itermx 3` for `check` (or state in the README that the ticket's run is `--itermx 3`), and
  record and report the actual number of iterations and Jacobians.

**I1-m3: diagnostic switches are not enforced or recorded.** `--ppp '{"CheckJac": 1}'` is accepted. `CheckJac`,
`CheckPandf1` and `ForceSerialCheck` are not asserted to be 0 before `exmain` and are not in the provenance, so a record
cannot prove the ticket's "never on in a measured run". Acceptance: reject them in `RunSpec.validate`, assert 0, record them.

**I1-m4: the RHS probe passes a length-`neq` buffer.** `bbb.ffun(neq, 0.0, yl[:neq], out)` is called, but `pandf` and
`OMPPandf1Rhs` read `yl(neq+1)` (the nksol/Jacobian flag: `bbb/pandf.m:570,574,739`, `pandf_plasma_continuity.m:714`;
`real yl(neq+1)` / `ylcopy = yl` in `omp_parallel.F90`). That read is out of bounds. It is inert with this deck
(dtreal=1e20, ishosor=0, ismcnon=0) but becomes live for time-dependent presets. Acceptance: pass a copy of
`bbb.yl[:neq+2]`.

**I1-m5: some documentation statements are inaccurate.**
- `runner.py:24` says `"OMP iter="` marks the parallel RHS. The tag is set whenever `ParallelPandf1>0`, even when
  `OMPPandf1Rhs` falls back to the serial `pandf` because `ijactot==0` (`bbb/pandf.m:17-20`,
  `ppp/omp_parallel.F90:989-991`).
- `openmp-jacobian.md` says `CheckJac`/`CheckPandf1` use "an absolute tolerance of 1e-14, abort on the first mismatch". That
  holds for the Jacobian checks (`ppp/parallel.F90:92,106`). `CheckPandf1`'s `Compare` applies an absolute and then a
  relative 1e-14 test and aborts after scanning all entries (`parallel.F90:348-365`).
- When the hook is absent, the report does not say so; only the section names reveal it.
- The validation log shows agreement but no exit codes.

**I1-m6: one RHS probe stands in for "every measured parallel evaluation".** The single post-`exmain` probe does exercise
`OMPPandf1Rhs` (confirmed: `rhs_probe_parallel` true, `ijactot=1`, ±0 effect visible). I accept it as a justified
Python-only approximation, but the README "Limits" should list it explicitly.

### Observations for the main session (product behaviour, not harness defects)

- **Te box, `jacrhs`, 4 threads:** the iteration-0 `fnrm` is 7.29e+31 / 6.58e+31, against 0.32 serial and 0.17 on the `jac`
  arm. The iteration-0 residual comes from the serial fallback (`ijactot==0`), so the difference must be in
  `sfscal`/Jacobian. The `jac` and `jacrhs` arms therefore produce very different Jacobians on the Te box.
- **Full problem, `jacrhs`:** `bbb.yldot` after `exmain` and the probe at the same `yl` differ in 1032 Te entries, with
  maximum relative difference 3.8e+33. The serial build gives 0 differences. Only a serial `get_fnrm` ran in between. The
  parallel RHS Te rows look history-dependent or racy, which is consistent with AIUE-8.

## What was checked and how

- **Diff:** read `git diff 483d57a..HEAD` in full (7 harness modules, README section, `openmp-jacobian.md`, validation log).
  The only `.claude/` change is `context/openmp-jacobian.md`, in commit 72fc76d with the trailer `AI-layer: code-facts`.
  No skill, agent or hook changes. `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` printed `OK`.
- **Unit tests:** `venvs/base-omp/bin/python -m pytest -q tests/deterministic_omp/harness` gives 21 passed.
- **Acceptance runs (Te box, mine):**
  - serial `check` on base-omp: exit 0;
  - `jac` at 4 threads: `CHECK ... MISMATCH`, `compare serial run0` exit 1, `te/te` rows and columns named;
  - harness copy with `case/mist.dat` removed: `HARNESS ERROR: case file missing`, exit 2;
  - `jacrhs` at 4 threads on AIUE-47-omp (hook): exit 1, 2 captures from `jac_calc_parallel`;
  - `jacrhs` on base-serial: AGREE, exit 0 (I1-B1).
- **Full problem (my one heavy run):** `run --preset full --arm serial` (36 s) and `--arm jacrhs --threads 4` (13 s) on
  base-omp. Then `compare` with `--rhs-signed-zero-equal auto` and `no`, and a numpy classification of the mismatches
  (I1-M1, observations).
- **Localiser, live:** `scripts/livemap.py` ran `worker.equation_map` on the full deck state (neq 44352, numvar 14) and on
  the Te box (neq 25).
  - All indices were assigned exactly once.
  - Each `idx*` entry round-trips through `igyl` to its own (ix, iy).
  - The within-cell order is ni[0..7], up[0..1], te, ti, ng, phi; e.g. te(1,1) = iv 1033.
  - Switched-off tables hold no stale in-range indices after the preset is applied.
- **Comparator attacks:** `scripts/break_compare.py` (I1-M3, I1-M4), all reproduced as stated.
- **Runner isolation:** I replaced the interpreter with a script that dumps the environment and set `OMP_PROC_BIND`,
  `OMP_SCHEDULE`, `OMP_DYNAMIC`, `GOMP_SPINCOUNT`, `KMP_AFFINITY`, `PYTHONPATH` and `PYTHONSTARTUP` in the parent. In the
  child only `OMP_NUM_THREADS=3`, `OMP_STACKSIZE=512M`, an empty `HOME`, `UEDGE_OMP_RATES_DIR`, `-I`, and cwd = the fresh
  run directory remained. A missing `record.json` gives exit 2.
- **Source checks:**
  - `ffun` → `rhsnk`/`pandfrhs_interface` → `OMPPandf1Rhs` when `ParallelPandf1>0`; the parallel branch only when
    `ijactot>0` (`bbb/oderhs.m:922-1008`, `bbb/pandf.m:7-28`, `ppp/omp_parallel.F90:902-996`);
  - `InitParallel` (`ppp/parallel.F90:4-43`);
  - `get_fnrm` (`bbb/ext_neutrals.m:1169-1191`);
  - `jac_reorder` (`bbb/oderhs.m:1307,1370-1428`);
  - the `ijactot` reset (`bbb/odesetup.m:6799`);
  - the `idx*`/`igyl` declarations (`bbb/bbb.v:2002-2010`);
  - the AIUE-47 `Jacobian_capture` group (`uedge-wt/AIUE-47/bbb/bbb.v:4221-4250`), consistent with `collect_capture`;
  - the venv `direct_url.json`.

Scratch outputs are in
`/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev49/`.
