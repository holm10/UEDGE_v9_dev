# Process tiers and session SOP: size the process to the ticket

The PIV loop (plan, execute, validate, review) is the same for every ticket; **how much** of it a ticket pays is not.
Epic AIUE-8 showed where the cost goes: 73% of 22.6M subagent tokens went to 12 long agents resumed again and again
(each resume re-reads the whole history), 23% to adversarial review rounds (many triggered only by minors), and the
longest waits were build and test matrices. This module sets the budget. Rigour is kept where it pays: high-risk code
still gets every gate.

## Tiers

`spec` assigns a tier to every ticket (breakdown line `Tier:`); without one, the planner assigns it in the plan's
Summary. Decide by **what the change touches**, not by effort. When in doubt, take the higher tier.

| Tier | Typical tickets | Plan | Plan review | Implementation review | Validation |
|---|---|---|---|---|---|
| **S** | investigation, characterisation, doc/tooling, AI-layer changes, small fixes outside the high-risk areas and the Fortran sources | ≤150 lines, written straight to the ticket page (`ticket-page publish`) | none | one round (round 2 only for an open BLOCKER/MAJOR) | `validate` with the suites the change can affect |
| **M** | Python layer, CI, refactors outside the high-risk areas, bug fixes with a clear RCA; **any Fortran source outside the L list** (at least M) | ≤300 lines | only if high-risk (below) | as below; on Opus for a Fortran source | `validate`; serial bitwise check for a Fortran source |
| **L** | the `pandf` tree, Jacobian/preconditioner and the Newton-Krylov solver (the whole files `bbb/oderhs.m`, `bbb/odesetup.m`, `svr/nksol.m`, `svr/svrut1.m`, `svr/svrut3.m`, `svr/svrut4.m`), `ppp/`, `.v` files, the build (`setup.py`, `pyproject.toml`, `Makefile.Forthon`), new physics | ≤300 lines (up to 500 with a one-line reason in the plan) | **required** | as below | full `validate`, OpenMP check, serial bitwise check |

**High-risk** = the L list. A plan review runs only for high-risk changes; low-risk S and M tickets skip it.
**Other Fortran** = any Fortran source outside the L list: `.m` (`bbb/griddubl.m`, `bbb/geometry.m`, `svr/daspk.m`,
…), `.F90` and hand-written `.f` (`com/*.f`, `ncl/*.f`, `svr/daux1.f`, `svr/petsc-uedge.F90`): at
least M, from planning on. It needs no plan review, but its implementation review runs in full on Opus and its
validation includes the serial bitwise check (`validate` step 5: bitwise unchanged, or for a fix meant to change
results only the cases the plan names move). Owner decisions 2026-10-21 (AIUE-137; `.F90`/`.f` included after review).

**Check the tier against the diff.** Before choosing the implementation reviewer, run
`uv run .claude/hooks/change_kind.py --range origin/v9-develop...HEAD` and read its `HIGH-RISK:` and `FORTRAN:` lines
(patterns `HIGH_RISK` and `FORTRAN` in that file: the L list above, and every other Fortran source).
- `HIGH-RISK: yes` on an S or M ticket: **re-tier to L**. Run the plan review if it did not run, review the
  implementation in full on Opus, and add one Findings-and-decisions entry to the ticket page ("re-tiered S/M -> L:
  diff touches <paths>").
- `FORTRAN: yes` (and `HIGH-RISK: no`): an S ticket is **re-tiered to M**, with the same entry ("re-tiered S -> M:
  diff touches <paths>"). On S or M, the implementation review runs in full on Opus and the serial bitwise check
  runs. No plan review.
- A verification round whose fix diff (`--range <reviewed sha>...HEAD`) says `yes` on either line also runs on Opus.

## Review rounds scale with the findings

- **Minors never trigger a round.** The author fixes them (or declines them in a line), lists each in the response,
  and the next gate (or the PR) checks them.
- **Round 2+ is a verification round**: the reviewer gets the earlier findings, the response and the fix diff
  (`git diff <reviewed sha>..HEAD`), and checks each fix against its finding with a short checklist. No fresh full
  review, unless the fix diff is large (more than about 200 changed lines or a new design), which the coordinator
  says in the prompt. New BLOCKER/MAJOR issues it sees in the fix diff are still findings.
- **AI-layer changes**: one review round plus their tests; round 2 only for an open BLOCKER/MAJOR.
- The 3-round cap, REJECT and the escalation rules stay as in `end-to-end-feature` → Adversarial review loop.

## Fresh fixer, not resume

Resuming a long agent (`SendMessage`) re-reads its whole transcript: in AIUE-8 one resume with 6 tool calls cost 720k
tokens. So:

1. Every implementing agent writes `<worktree>/.claude/work/<KEY>/handoff.md` before it returns (≤60 lines): state
   (what works, what is red), branch and tip sha, what is done, open items, how to verify (the exact commands and the
   build/venv to use). It is a working document: never committed.
2. **Plain minors**: the coordinator fixes them itself.
3. **BLOCKER/MAJOR fixes**: a **fresh, small** agent (`model` from the table below) gets only the review findings,
   the diff range, the handoff note and the worktree path. It updates the handoff note before it returns.
4. `SendMessage` to a running or finished agent is the exception: a quick question with a short answer. Never a fix
   round. The `session_guard.py` hook warns when a resume targets a large transcript.

## Session SOP (coordinator)

- **Parallel only when it shortens the critical path.** At most about 3 background agents at once; `session_guard.py`
  warns at a launch when 3 were already launched in the last 45 minutes. Serialise tickets that share files, builds or the machine's cores.
- **A fresh coordinating session per wave or epic phase.** Hand over through the epic's `Progress: <EPIC>` page and
  each ticket's `handoff.md`; don't carry a session past a few compactions (the hook warns above ~15 MB or after 2
  compactions).
- **Size every ticket** with its tier before starting it; don't run the full ceremony on an S ticket.
- **Builds and test matrices**: iterate on one case and two thread counts, run the full matrix once at the end, and
  prefer CI for heavy matrices (`.claude/context/testing.md` → Fast iteration).
- **Pick the model** for each agent from the table below.

## Model mix

Agent frontmatter fixes the model where an agent is always one kind of work (`uedge-physics`, `uedge-implementer`,
`uedge-reviewer`: opus; `research-agent`, `system-reviewer`: sonnet). Otherwise the coordinator passes `model`:

| Work | `model` |
|---|---|
| RCA, design and planning of L tickets, physics, implementation of L tickets | `opus` (default) |
| Review of the `pandf` tree, Jacobian, `ppp/`, `.v`, build, physics (plan or implementation, round 1), and the implementation review of any other Fortran source | `opus` (the reviewer's default) |
| Review of an AI-layer change, of S/M tickets outside the high-risk areas and the Fortran sources, and verification rounds whose fix diff stays outside both | `sonnet` |
| Mechanical work: merging or rebasing branches, moving or consolidating documents, backfilling records, applying a listed set of minor fixes | `sonnet` |

## Report caps

- Review report ≤150 lines; each finding is one line plus an evidence pointer (`file:line`, command, output line).
- Review response: one line per finding (fixed where / rebutted why / declined).
- Validation entry on the ticket page: the verdict lines and failures verbatim; no logs, no tables of passing cases.
- Execution report ≤100 lines; handoff note ≤60 lines.
- Raw run data (logs, `.npz`/`.hdf5`, JSON records, per-case tables) stays in `.claude/work/<KEY>/` or a scratch
  directory and is summarised, never committed. `change_kind.py --range` warns when a branch exceeds the PR size
  budget (`branching.md` → Checking).

## Simplicity budget for AI-layer tooling

Prefer conventions and short skill text over new code paths. An AI-layer change that adds more than 300 lines of
tooling code or more than 40 test cases states a one-line justification in its PR description. A helper keeps only
what must be mechanical (a guarantee a model can't be trusted to keep by hand); the rest is a sentence in the skill.
