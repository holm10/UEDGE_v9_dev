# Review: ai-adversarial-ticket-review — implementation, round 2

Branch `feature/v9-ai-adversarial-ticket-review` @ `4e191a7` (on top of round 1's `3b99e75`; merge base with
`origin/v9-develop` = `3865c79`). Files: `.claude/skills/{end-to-end-feature,execute,implement-fix,plan-feature}/SKILL.md`,
`.claude/agents/uedge-reviewer.md`, `CLAUDE.md`.
Reference: the user's request ("Use adversarial checks on every ticket to finish up ... update [the ticket-execution
skill] with the adversarial check for the ai-layer"), for unattended work on AIUE-8, plus the repo's AI-layer rules.

## Verdict

**APPROVE**

## Summary

All 5 round-1 MAJOR findings are resolved, and I checked each fix in the files.
- "Done" now means a fresh reviewer's APPROVE on the final diff, not whether a commit exists. This agrees with
  `execute`/`commit`, and the `WIP:` prefix is gone.
- An agent that can't spawn a reviewer now has a defined hand-off, and must never review its own work.
- The reviewer gets a run budget and has a "not independently verified (environment)" category.
- Edits after APPROVE need a new round.
- `implement-fix`, `execute` and `plan-feature` all point to the single loop.

All 7 round-1 MINORs are resolved or acknowledged. Both hook checks are clean. I found no new BLOCKER or MAJOR. Three
new MINORs on the new text concern ordering and duplication. They would cost an unattended run time, not correctness.

## Findings

### BLOCKER

None.

### MAJOR

None.

### MINOR

- **I2-m1 — Leftover "before they are committed" in the reviewer description** (`.claude/agents/uedge-reviewer.md:3`).
  The description still says the reviewer is required by end-to-end-feature "on ticket plans and implementations
  before they are committed". Since I1-M1 the gate is defined by status (commit as you go, done only after APPROVE).
  The description is what a main session reads when it routes work, so it should say the same. It also doesn't
  mention `implement-fix`. *Resolve:* reword it to something like "before a ticket counts as done (end-to-end-feature,
  execute, implement-fix)".
- **I2-m2 — `implement-fix` asks for a plan round "before writing code" at a step that comes after the code is
  written** (`.claude/skills/implement-fix/SKILL.md:56-61`). §4c comes after §3 Implement and §4 Verify. An agent
  following the steps in order (unattended, as for AIUE-56/59 in `ppp/`) reaches the plan-round instruction with the
  fix already written. It then skips the plan round or runs it after the fact. The implementation round still gates
  the fix, so the hard check is in place, but the intended design check on the highest-risk bug tickets is lost.
  *Resolve:* move the plan-round sentence into §1/§3 (before Implement), or add a pointer there.
- **I2-m3 — Each gate can run twice inside `end-to-end-feature`, and the hand-off leaves Steps 4–5 unassigned.**
  - `plan-feature` §"Adversarial plan review" (`plan-feature/SKILL.md:156-159`) and `end-to-end-feature` Step 2b both
    run the plan loop.
  - `execute` step 6 (`execute/SKILL.md:96-100`) and `end-to-end-feature` Step 3b both run the implementation loop.
  - The parenthetical "(`end-to-end-feature` does this as its Step 3b)" can be read either as "skip here" or as "this
    is the same thing". An agent that takes it literally spends an extra reviewer round (about 20 minutes) per gate. It
    may also restart the round count at 1, which blurs the 3-round cap.
  - When a ticket subagent hands off because it can't spawn a reviewer ("Who reviews", `end-to-end-feature/SKILL.md:96-101`),
    the text doesn't say that the caller then also owns Step 4 (committing the reports and responses in the ticket
    worktree), Step 5 (`execution-report`/`system-review`) and the Final Summary.

  *Resolve:* add one line each: "inside `end-to-end-feature`, Step 2b/3b is that run; don't repeat it", and "the
  caller that runs the loop also finishes Steps 4–5".

## Status of previous findings

| ID | Status | Evidence |
|---|---|---|
| I1-M1 commit semantics | **Resolved** (leftover wording in I2-m1) | `end-to-end-feature:85-88` defines "done" as APPROVE on the final `<base>...HEAD` diff. Commit-as-you-go matches `execute` 3b item 4 and `commit`. No `WIP:` prefix remains (`grep WIP` finds nothing in the skill). Escalation (`:132-136`) leaves the commits as they are and keeps Jira In Progress. The Final Summary has a "Ticket Escalated" variant and ✅/❌ for the review, and the push/PR next step applies only to approved work and only "when the user asks" (`:159,169,183-185`). |
| I1-M2 no fallback when no reviewer can be spawned | **Resolved** | "Who reviews" (`:96-101`): never review your own work and never use a fork. If no reviewer can be spawned, stop after validation and return the work state, the validation output and the prompt. The caller runs the loop and decides who applies the fixes, and the fixer re-validates. `execute` step 6 and the execute report (`:124`) carry the same hand-off. |
| I1-M3 run budget / unreproducible criteria | **Resolved** | Prompt bullet `:108-111` (venvs never reinstalled, scratch worktree builds, time limit, list of criteria that can't be reproduced). `uedge-reviewer.md` replaces "tell the main session" with the budget rule and adds the "Not independently verified (environment)" category, which neither fails a criterion nor accepts it on trust, while an unchecked criterion that *could* be checked is still a finding. The Output section and the Final Summary (`:178`) carry it, and loop item 7 routes it to the PR/ticket. |
| I1-M4 edits after APPROVE | **Resolved** | Loop item 3 (`:118-120`): only typo- or doc-level fixes skip a round. Any code, test, data or behaviour change needs a new round on the changed diff. This matches `create-prd` Step 6's precondition. |
| I1-M5 `implement-fix` / manual path ungated | **Resolved** (ordering in I2-m2) | `implement-fix` §4c adds the implementation gate (reference: RCA plus Jira acceptance criteria) and a conditional plan round. §6 now reads "approved and committed". `execute` step 6 and `plan-feature` §"Adversarial plan review" reference the loop. The `CLAUDE.md` rows name the gates, so the claim is now backed by the skills on each path. |
| I1-m1 relative report path | Resolved | Prompt bullet `:114-115`, and `uedge-reviewer.md` Output: "absolute path the prompt gives". |
| I1-m2 response files | Resolved | Loop item 4: `...-round<N>-response.md`. Item 7 commits them. The round-1 response follows this convention. |
| I1-m3 ID prefix clash | Resolved | `uedge-reviewer.md` ID examples: `L1-M2` (plan), `I1-m4` (implementation). |
| I1-m4 triggers / re-validate / plan flaw | Resolved | Step 2b, `plan-feature:158-159` and the `CLAUDE.md` row list the same triggers. The plan stage says there is no re-validation (`:61-62`). Loop item 4 handles an implementation finding that shows the plan is wrong (`:124-125`). |
| I1-m5 stacking | Resolved | "Stacking" paragraph (`:21-22`). |
| I1-m6 argument-hint / acceptance source | Resolved | `argument-hint: [ticket-key or feature-description]`. "Ticket input" (`:17-19`). I checked that `git show feature/v9-AIUE-8-planning:docs/specs/` lists `AIUE-8-investigate-non-deterministic-openmp-jacobian.md`, and that the `feature/v9-<EPIC>-planning` naming matches `branching.md:39` and `spec/SKILL.md:123`. |
| I1-m7 `docs/reviews` blocked on the AI branch | Acknowledged (correct) | The reports live on `feature/v9-AIUE-8-planning`. Housekeeping: the AI worktree still has an untracked copy, `docs/reviews/ai-adversarial-ticket-review-implementation-round1.md`. Don't commit it there (`change_kind` would block it); delete it or leave it untracked. |

## Not independently verified (environment)

None. Everything in this review could be checked by reading files and running the two hook commands.

## What was checked and how

- Diffs: `git diff 3b99e75..4e191a7` (the round-2 changes) and `git diff --stat origin/v9-develop...HEAD`
  (6 files, +156/−24). Merge base = `origin/v9-develop` = `3865c79`.
- Hooks, run from the worktree:
  - `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` gives `OK`, exit 0. It prints only the
    advisory list of docs that cite the changed files.
  - `uv run .claude/hooks/change_kind.py --range origin/v9-develop..HEAD` reports 6 `process` files on an `ai` branch,
    `OK`, exit 0.
- Checked in Python that `change_kind.violations` gives `[]` for `docs/reviews/*-round1.md`, `*-round1-response.md`
  and `.claude/plans/*` on `bugfix/v9-issue-12-x`, `bugfix/v9-AIUE-56-...` and `feature/v9-AIUE-46-...`. Committing
  reports and responses therefore works on every ticket-branch shape the loop is used on, including `implement-fix`
  bug branches.
- Read in full: the new `end-to-end-feature`, `implement-fix`, `execute` and `commit` skills, and `uedge-reviewer.md`.
  Read the `plan-feature` gate section and its Phase 0 bug routing (`:26`).
- Grepped for Jira status rules ("In Review", "In Progress", "transition") across skills, agents and context. No other
  skill moves a ticket past In Progress, so the new rule conflicts with nothing.
- Checked `implement-fix`'s `allowed-tools`, which lacks `Agent`, against the Claude Code docs
  (code.claude.com/docs/en/skills). The docs say `allowed-tools` "does not restrict which tools are available: every
  tool remains callable". §4c can therefore spawn the reviewer, and this is not a finding.
- Not raised (unchanged material, MINOR at most): `uedge-reviewer.md` "If anything is missing, ask for it before
  reviewing", and the PRD-stage "Tell the main session before you do". A spawned reviewer can't ask and wait. The
  loop's self-contained prompt makes the first one unlikely to bite, but the owner may want to turn both into "state
  what was missing and review what you can" in a later AI-layer change.
- No builds or test suites were run (none needed).
