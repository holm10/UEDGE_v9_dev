---
name: end-to-end-feature
description: Autonomously develops a complete feature or Jira ticket from priming through planning, execution, an adversarial uedge-reviewer gate, and commit by chaining the core PIV-loop skills. Use when you want a full hands-off feature build from a single description or ticket key.
argument-hint: [ticket-key or feature-description] [--no-tracker] [--tracker-dry-run]
---

# End-to-End Feature Development

**Feature Description**: $ARGUMENTS

This skill chains the core PIV-loop skills for autonomous feature development, with an independent adversarial
review (`uedge-reviewer`) that a ticket must pass before it counts as done. Never run it on
`v9-develop`/`v9-main`, and never on an AI-layer branch (`feature/v9-ai-*`, `v9-agentic`). It runs on the
ticket's own branch and worktree, which `plan-feature` creates in its Phase 0b (`.claude/context/branching.md`).
After Step 1, `cd` into that worktree and stay there for every later step.

**Ticket input.** For a Jira key, take the scope and acceptance criteria from the Jira issue, or from the Ticket
section of its page (the ticket's entry on the epic's breakdown page on Confluence, as filed by `spec`). The
acceptance criteria are what the reviewer checks against, so quote them verbatim.

**Working documents.** The plan, the review reports and responses, validation records, the execution report and
the system review are written to the ticket's working folder `<worktree>/.claude/work/<KEY>/` and never committed
(`.claude/context/branching.md`). What must last goes to the ticket page at the milestones below. The folder and the
`ticket-page` outbox go with the worktree: flush (nothing queued) before a worktree is removed.

**Worktrees and subagents.** The ticket's worktree is always an explicit one (`git worktree add … ../uedge-wt/<KEY>`,
`plan-feature` Phase 0b), never the Agent tool's `isolation: "worktree"`, which is removed automatically and takes the
working folder and the unsent entries with it (`branching.md` → Worktrees). When this skill runs as a subagent (one
per ticket, tickets in parallel), the caller creates the worktree and passes its path. Before it returns, the
subagent flushes the ticket page and checks that `queue --list` and `queue --epic --list` print nothing; if a flush
fails, its report says so with the worktree path, so the caller flushes later.

**No ticket record** (no Jira key, or `--no-tracker`): nothing reaches a page, so the PR description is the lasting
record. Collect for it what the page would get: the plan's summary, each review round's verdict, counts, one line per
finding and the response, the validate report block, and the criteria not independently verified.

**Ticket record.** For a Jira key, the run keeps the ticket's hosted record through the `ticket-page` skill, on the
one page `spec` created when it filed the ticket (`Ticket plans: <EPIC>` → `Plan: <KEY> - …` under the epic's PRD; or
short `PIV record` Jira comments when there is no epic PRD page): `plan-feature` fills its Plan section (creating the
page only if the ticket has none), and entries are sent only at milestones: each closed review
round, the end of `execute`, an escalation or owner decision, the commit (`ticket-page` → "When to flush"). Pass
`--no-tracker` or `--tracker-dry-run` on to every skill, to every sub-agent's prompt, and to whoever takes over a
review loop, and run `validate` with `--ticket <KEY>`. Atlassian failures never stop a step; the entries stay queued for the next flush.

**Stacking.** A ticket may start on a parent ticket's branch while the parent is still in review. When the parent
changes (review fixes, rebase), rebase the child onto it and re-run the child's validation before its review.

---

## Step 0: Route

If the request is **new physics** (new transport term, atomic/molecular process, BC, source, closure, neutral or
impurity model) and there is no approved spec in `docs/physics_specs/`, **stop**: tell the user it must go
through `uedge-physics` → `uedge-reviewer` → `uedge-implementer` (`.claude/context/physics-workflow.md`).
This skill handles refactors, numerics/parallel work, Python/build changes, and implementing approved specs.
Bug fixes from an RCA follow `implement-fix`, which uses the same review loop.

---

## Step 1: Prime - Load Codebase Context

Execute the priming workflow to understand the codebase.

Run the `prime` skill (`.claude/skills/prime/SKILL.md`).

---

## Step 2: Planning - Create Implementation Plan

Create a detailed implementation plan for the feature.

Run the `plan-feature` skill (`.claude/skills/plan-feature/SKILL.md`) with the feature description: **$ARGUMENTS**.

**IMPORTANT**: Note the feature name (and plan file path) that the planning step creates. You'll need it for the next step.

---

## Step 2b: Adversarial plan review (required for high-risk plans)

**Required** when the plan touches the `pandf` tree (`bbb/pandf*.m` and what they call), `ppp/`, Jacobian or
preconditioner code, a `.v` file, or the build (`setup.py`, `Makefile.Forthon`). Optional otherwise. A wrong design
costs more to fix after execution than before.

Run the **Adversarial review loop** below with `stage: plan`. The reviewer checks the plan against the ticket's
acceptance criteria and the code it cites. Revise the plan, not the code, until it is approved. Nothing is built
or run at this stage, so there is no re-validation between rounds.

---

## Step 3: Execute - Implement the Feature

Implement the feature from the plan document.

Run the `execute` skill (`.claude/skills/execute/SKILL.md`) with the plan file path: `.claude/work/<KEY>/plan.md`.

Do not continue unless the `validate` gate is green (or the only moved cases are the ones the plan documents for an
intended physics/numerics change).

(Use the feature name from Step 2.)

---

## Step 3b: Adversarial implementation review (always required)

Run the **Adversarial review loop** below with `stage: implementation`, on the ticket's whole diff against its base
(committed and uncommitted). The reference is the approved physics spec if there is one, otherwise the ticket's
acceptance criteria and the plan.

**Committing and "done".** You may commit as you go (the code, then the code-facts commit, as `execute` and `commit`
describe), and the reviewer reviews `<base>...HEAD`. What makes a ticket **done** is a fresh reviewer's APPROVE on
the final diff, not the existence of a commit. Until then, don't report the ticket as complete, don't move its Jira
issue past In Progress, and don't open a PR for it.

---

## Adversarial review loop

Used by Step 2b and Step 3b here, and by `plan-feature`, `execute` and `implement-fix`. Inside this skill, Steps 2b
and 3b **are** those skills' review gates: run each loop once, not again from `plan-feature` or `execute`, so the
3-round cap counts one loop.

**Who reviews.** Never review your own plan or code, and never use a fork or an agent that saw the drafting. Spawn a
**fresh** `uedge-reviewer` agent for every round (Agent tool, `subagent_type: "uedge-reviewer"`). If you can't spawn
one (no Agent tool, nesting limit reached, running as a subagent without it), **stop after validation** and return
to your caller: the work state, the validation output, and the ready-to-use reviewer prompt below. The caller then
runs the loop. Whoever runs the loop also decides who applies the fixes: itself, or the implementing agent (resumed
with the findings). The one applying fixes re-validates before the next round. After a hand-off, the caller also
owns the rest of this skill for that ticket: Step 4 (commit), Step 5 (Learn) and the Final Summary.
Whoever runs the loop also records it on the ticket record (steps 3, 4 and the escalation).

1. **Prompt.** The reviewer can't see this conversation, so its prompt must be self-contained:
   - `stage` (`plan` or `implementation`), round number, ticket key (or feature name), branch and worktree path;
   - the reference: the spec path, or the ticket's acceptance criteria quoted verbatim, plus the plan path (the
     local working copy `<worktree>/.claude/work/<KEY>/plan.md`; the ticket page's Plan section is its published
     copy);
   - for `implementation`: the diff range (`git diff <base>...HEAD` plus uncommitted changes) and the validation
     output you got;
   - the **run budget**: which builds/venvs it may use (never to be reinstalled), what it may build in a scratch
     worktree, and a time limit; and which acceptance criteria can't be reproduced in its environment (another OS,
     CI, many-run statistics), so it records those as *not independently verified* instead of failing or trusting
     them;
   - the binding decisions and constraints (`CLAUDE.md` hard rules, epic decisions), so the reviewer checks against
     them instead of re-opening them;
   - the **absolute** report path in the working folder: `<worktree>/.claude/work/<KEY>/reviews/<KEY>-<stage>-round<N>.md`
     (a relative path can land in another checkout); the report is a local working file, never committed;
   - on rounds 2+: the previous report path and the response file (step 4). If they are not in this worktree (the
     earlier round ran in another worktree or session), give the reviewer the page's Reviews entries for that round
     instead (read the page; they hold the verdict, every finding in a line and the response).
2. Wait for the completion notification, then read the report. Queue its lasting content (the report itself is not
   kept): `ticket-page <KEY> log Reviews "Reviewer: <stage> round <N> <VERDICT> (<B> BLOCKER / <M> MAJOR / <m>
   MINOR), reviewed <the diff range, e.g. <base>...<sha>, or the plan's sha256>. <ID> <one line>; <ID> <one line>; …
   Not independently verified: <criteria or none>."`, one line per finding, every severity (round 1 also `status
   Plan review` or `status Implementation review`).
3. **APPROVE** → done with this stage; `ticket-page <KEY> flush` (implementation stage: `status Approved` and
   `ticket-page <KEY> progress "<stage> approved, round <N>"` first). MINOR findings may be fixed: typo-level and
   documentation-only fixes need
   only the validation they touch; any other change after APPROVE (code, tests, data, behaviour) needs a new round
   with a fresh reviewer on the changed diff. List deferred MINORs in the execution report.
4. **REVISE** → fix every BLOCKER and MAJOR, or rebut it with evidence. Write the response to
   `<worktree>/.claude/work/<KEY>/reviews/<KEY>-<stage>-round<N>-response.md` (finding → fixed where / rebutted why).
   Re-validate (implementation stage). Record the response: `log Reviews "Agent: round <N> response: <ID> fixed
   (<where>); <ID> rebutted (<why, in a line>); …"`, then flush (`ticket-page <KEY> flush`; for a revised plan,
   `publish` as `plan-feature` says is the flush). Start round N+1 with a fresh reviewer.
   An implementation finding that shows the **plan** is wrong: revise the plan first, and for a high-risk plan
   (Step 2b list) re-run a plan round before changing the code.
5. **REJECT** → stop and escalate (below).
6. **Round 3 without APPROVE** → stop and escalate.
7. Never commit the review reports or responses: they are working documents (gitignored; the hook refuses them).
   Their content is on the ticket page (steps 2-4). Criteria the reviewer marked *not independently verified* go into
   the PR description and the ticket page (a Findings and decisions entry), for the owner. **Without a ticket record**
   (no Jira key, `--no-tracker`), the same content as steps 2-4 (each round's verdict, counts, one line per finding,
   the response) goes into the PR description instead: it is the only place it survives the worktree.

**Escalation.** Record it first: `ticket-page <KEY> status Escalated`, `progress "escalated: <one line>"` and `log
"Findings and decisions" "Escalated: <open findings or the decision needed>" --flush`; the owner's answer, when it comes, is recorded the same way as an
Owner entry with its source. For a ticket on the Jira fallback that `PIV record` comment is the escalation comment
below: don't post a second one. When a person is available, show them the open BLOCKER/MAJOR findings and ask how to proceed. When
running **unattended** (the user said they can't give feedback): leave the commits on the ticket branch as they are,
record the open findings in the execution report and on the ticket (Jira comment, if a key is known), keep the ticket
In Progress, and move on only to tickets that don't depend on it. Do the same for any decision the PRD or ticket
reserves for the owner: prepare the evidence and the options, and stop at the decision.

---

## Step 4: Commit - Save Changes

Commit what is not yet committed (any last fixes; never the working documents in `.claude/work/`) with the `commit`
skill (`.claude/skills/commit/SKILL.md`). Then `ticket-page <KEY> status Committed`, `progress "committed <sha>"` and
`log Progress "Committed <sha>: <subject>" --flush`. Check that nothing is left queued (`ticket_page.py queue --repo
<worktree> --key <KEY> --list`, and with `--epic`): the worktree must not be removed while anything is.

---

## Step 5: Learn - Feed process lessons back

Run the `execution-report` skill and then the `system-review` skill on the plan and the report (both local, in
`.claude/work/<KEY>/`). Each puts its findings on the ticket page (a flushed Findings and decisions entry), and
`system-review` files each recommendation as an `ai-layer` issue. Nothing in `.claude/skills`, `.claude/agents` or
`.claude/hooks` changes on this branch.

---

## Final Summary

After completing all steps, provide:

### Feature Implementation Complete | Ticket Escalated

**Original Request**: $ARGUMENTS

**Feature Name**: [feature-name from planning step]

**Steps Executed:**
1. ✅ Prime - Codebase context loaded
2. ✅ Planning - Plan created at `.claude/work/<KEY>/plan.md` (local) and published to the ticket page
3. ✅ Execute - Feature implemented and validated
   ✅/❌ Adversarial review - plan: [verdict, rounds or "not required"]; implementation: [verdict, rounds]
4. ✅ Commit - Changes committed to git
5. ✅ Learn - Execution report + system review; ai-layer issues filed: [keys]

**Outputs:**
- Plan document: `.claude/work/<KEY>/plan.md` (local working copy, not committed; published copy on the page)
- Ticket record: [page URL / Jira PIV comments / skipped, why; entries still queued, if any — flush before the
  worktree is removed]
- Files created/modified: [list]
- Validate result: [report block]
- Review reports: local in `.claude/work/<KEY>/reviews/` (not committed; verdicts and findings on the ticket page,
  or, without a ticket record, in the PR description), findings fixed / rebutted / deferred
- Not independently verified (for the owner): [criteria, or "none"]
- Default results: [unchanged / changed as documented]
- Commit hash: [hash]

**Next Steps:**
- Approved: push and open a PR when the user asks for it (`commit`/branching rules apply).
- Escalated: the open BLOCKER/MAJOR findings or the owner decision needed, and which tickets are blocked by it.
- Continue with the next independent ticket.
