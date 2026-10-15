# Review: close-epic skill (AI-layer change), round 3 — and close-out stage test, round 3

Branch `feature/v9-ai-close-epic`, worktree `/Users/holma/Documents/uedge/src/uedge-wt/ai-close-epic`, tip `c9fa77a`
(round 2 reviewed `9660c36`), base `origin/v9-develop` `3865c79`. Read-only; no Atlassian calls, no commits, no UEDGE
runs. Gathered 2026-10-15 ~18:15Z.

---

# Job A — stage: implementation (AI-layer change), round 3

## Verdict

**APPROVE** (0 BLOCKER, 0 MAJOR, 4 MINOR)

## Summary

`c9fa77a` resolves I2-M1. An unmet gating criterion is now the first open item in Step 3. Step 3 says the
completion verdict depends on that list. The `Close-out draft` status needs n ≥ 1. The `Closed by the owner` status
and reviewer check 7 both need an owner answer for every unmet criterion, with a + d = n. I tried five routes to
"Closed by the owner" over an unanswered unmet criterion, and the skill text blocks every one. The only residual is
enforcement: on a first close, nobody reviews the Step 6 status change (I3-m1). The new **requested fix** class can't
be used to wave through code, test or behaviour changes: "even when a finding asked for it" puts those in
*unreviewed change*, which matches the `end-to-end-feature` rule on the sibling branch. Its edges (claim-changing
comments in source files, author-produced numbers) are MINOR. I2-m1, I2-m2 and I2-m3 are resolved. Both hooks are
clean, and the close-out stage uses exactly "Not independently verified (environment)".

## Findings

### MINOR

**I3-m1. Step 5, Step 6 and Step 7 disagree on whether recording the owner's answers needs a new review round. So on
a first close, no reviewer ever sees the `Closed by the owner` line.**

*Locations:* `SKILL.md:370-371`, `:386-387` and `:395`.

*The three rules:*
- **Step 5:** "any change to a claim, a class, a status or an item [needs a new round]".
- **Step 6:** "A change beyond recording the answers goes back through Step 5". Read literally, recording the
  answers (status line, section 8, the "who" column) does not go back.
- **Step 7:** its precondition needs APPROVE "for the text being published".

*Why it matters.* Under the Step 6 reading, reviewer check 7's `Closed` clause only takes effect on a re-run.

*Constructed path.* The owner answers 4 of 5 items and replies "yes, Done". The author ignores l.385 ("don't offer
Done") and writes `Closed by the owner … 4 accepted-open, 0 deferred`. No review runs, and Step 7 transitions the
epic, because "the owner said yes in Step 6". This needs the author to break an explicit rule, so it is MINOR, not
a hole in the rule itself.

*Acceptance.* Make the three steps agree. Either:
- (a) recording answers that changes the status or section 8 gets a review round limited to that delta; or
- (b) Step 7's precondition adds a mechanical self-check before any transition: every open item, including each
  unmet criterion, has an owner answer, and a + d = n.

**I3-m2. The Step 4 template still names only two post-APPROVE classes.**

*Location:* `SKILL.md:321`, which reads "post-APPROVE commits (text only, or unreviewed change)".

*Problem.* The new third class, *requested fix* (l.220), is missing. An author following the template may put a
requested fix under one of the other two.

*Acceptance.* l.321 lists all three classes.

**I3-m3. Claim-changing comments in source files fit no class cleanly.**

*Locations:* `SKILL.md:219-221`; `uedge-reviewer.md:103-107`.

*The three classes:*
- *Text only* covers "comments … that add or change no claim".
- *Requested fix* is "a change to a document or record".
- *Unreviewed change* is "any change to code".

*Real case.* AIUE-47 `63370bd` changes only comments: a `bbb/bbb.v` `#` description and a comment in
`tests/deterministic_omp/tools/capture_check.py`. Both change a claim, and review findings asked for both. So it is
not text only. A literal reader calls it an unreviewed change; the r3 draft reasonably calls it a requested fix.

*Related edge.* A requested fix can add a number the author measured (not one the reviewer gave) and still be "not
open". In AIUE-56 `35974c9` the reviewer had computed the values itself, but the rule doesn't require that.

*Acceptance.* State that a diff touching only comment or `#` description lines in a source file counts as a document
change (and how to check it is comment-only). Also state that a requested fix whose new number the approving reviewer
did not give is checked against its source, or else counts as an unreviewed change.

**I3-m4. The git-only squash-title grep loses the commit hash when the match is in the body.**

*Location:* `SKILL.md:153-154`.

*Problem.* `git log --first-parent --format='%H %s%n%b' origin/v9-develop | grep -E …` prints body lines on their
own, without the hash. Demonstrated on PR #1: the humanised title "Feature/v9 ai layer" is the merge body. Its line
matches as line 4, alone, with no `%H`.

*Acceptance.* Use a form that keeps the hash, for example
`git log --first-parent -E --grep='<PROJ>[- ]<N>([^0-9]|$)' --format='%H %s' origin/v9-develop`.

## Status of previous findings

| Finding | Status | Evidence |
|---|---|---|
| **I2-M1** Unmet criterion never an owner question | **Resolved** | First not-done bullet: "each gating criterion whose class is not Met or Superseded" (l.267). Completion rule (l.282-284): "only if the list above is empty… A close-out draft always has at least one open item". Status table (l.299-300): n ≥ 1, and "every open item, including every unmet gating criterion… a + d equals the number of open items". Step 6 q1 (l.378-379) includes criteria. q4 and l.385 are conditional. Reviewer check 4 (l.107: "Every unmet gating criterion is an open item too") and check 7 (l.115-120: BLOCKER for 0-item drafts and for Closed over an unanswered criterion). Paths tried: see below. |
| I2-m1 Stacked tickets share `M` | Resolved (untested, as stated) | l.189-193: same `M`, or `M^1..M^2` containing another child's tip, falls back to `<parent-tip>..<tip>`, notes the shared merge, and attributes nothing if the tips are unrecoverable. |
| I2-m2 No git-only squash fallback | Resolved (recipe defect: I3-m4) | l.152-162: key in title or body, `git cherry`, `patch-id --stable`, "undeterminable", "merge not located" as an open item (also l.277), and the limitation in section 10. |
| I2-m3 Reviewer can't check Jira freshness | Resolved | Check 2 is now "Freshness (git only)" (l.86-92), with an internal-consistency check of `updated` against the read time. Step 7 is "the only freshness check on Jira and Confluence" (l.395-399). The stage says the snapshot files are the author's copies, which proves consistency, not authenticity (l.78-79). |
| C2-M1 (stage text) Record grep before "not named" | Resolved | Skill l.172-175 and check 4 l.101-102: `git grep -n -e '<name>' -e '<sha7>' <rev> -- docs .claude/plans`, plus listing commits on no branch (l.171-172). |
| C2-M2 (stage text) Post-APPROVE commits with the report | Resolved (edges: I3-m3) | Three-class table at l.214-221: code, tests, data or behaviour are unreviewed "even when a finding asked for it", and every changed claim must trace to a finding. Check 4 l.103-107 says the same. |
| C2-m1 (stage text) Scratch work | Resolved | "in progress, not a source" at skill l.177-178 and check 2 l.91-92. |
| C2-m4 (stage text) Unmerged tickets never tested together | Resolved | "at best Partly met" at skill l.231-233 and check 3 l.96-97. |
| Consolidation heading | Resolved | The exact string "Not independently verified (environment)" is at reviewer l.78, l.91 and l.171, and at skill l.361. No bare "Not independently verified" remains in either file. The output section list (l.171) is in the same order as `feature/v9-ai-adversarial-ticket-review:…/uedge-reviewer.md:141` and `feature/v9-ai-consolidate:…:187`. |

**I2-M1: routes I tried to "Closed by the owner" over an unanswered unmet criterion.**

1. *All children Done, one criterion No evidence.* Blocked. The criterion is an open item, so n ≥ 1 and the record
   is a `Close-out draft`. Done is not offered until the owner answers.
2. *Criterion classed "Met (on unmerged branches)".* Blocked. It is literally not "Met", so it is an open item, and
   the unmerged work is a separate open item anyway.
3. *Criterion marked Superseded on an agent's or unattributed decision.* Blocked. Superseded means "the owner changed
   or dropped the criterion; cite the decision". Crediting it to the owner without a source is a check 5 BLOCKER.
4. *Author reclassifies a gating criterion as non-gating.* Blocked. The PRD decides what is gating, and check 3
   covers it.
5. *Owner answers some items in one message and says Done.* Blocked by l.385. The only residual is that no reviewer
   sees the result (I3-m1).

**Can "requested fix" pass code, test, data or behaviour changes? No.**
- Code, tests, data and behaviour changes are unreviewed even when requested.
- This matches `end-to-end-feature` Step 3 on `feature/v9-ai-adversarial-ticket-review` (l.121-123): "any other
  change after APPROVE (code, tests, data, behaviour) needs a new round".
- That rule exists only on the sibling branch, so this branch's reference "the `end-to-end-feature` rule" (l.220)
  depends on the planned consolidation. This is a merge-order note, not a finding.

## Not independently verified (environment)

- **Untested recipes.** The squash, rebase and shared-merge recipes ran on no real case. The repo has no such merge,
  and `gh` is not installed. I checked them only against git semantics.
- **Behaviour of the revised skill end to end on a real (non-dry) close.** I couldn't run it read-only.

## What was checked and how (Job A)

- **Diff.** `git diff 9660c36..c9fa77a`: one commit, 2 files. I read the whole of `SKILL.md` Steps 1-7 and the
  close-out stage of `uedge-reviewer.md` (l.69-125, l.168-171).
- **Hooks.** The worktree is clean (`git status --short` = 0).
  - `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`: it lists the citing docs, then `OK`,
    exit 0.
  - `uv run .claude/hooks/change_kind.py --range origin/v9-develop..HEAD`: branch `ai`, 5 process paths, `OK`,
    exit 0.
- **Sibling branches.** `git show feature/v9-ai-adversarial-ticket-review:.claude/skills/end-to-end-feature/SKILL.md`
  (l.112-128), and `grep` for the heading and the output line on both sibling branches.
- **I3-m4.** `git log --first-parent --format='%H %s%n%b' origin/v9-develop | grep -nE 'Feature/v9 ai'` gives `4:Feature/v9 ai layer`, with no hash.

---

# Job B — stage: closeout, round 3 (light; test of the revised stage on `AIUE-8-closeout-draft-r3.md`)

I applied the stage as written in `ai-close-epic/.claude/agents/uedge-reviewer.md:69-125`. I checked Jira and
Confluence claims against `scratchpad/closeout/AIUE-8-closeout-sources/` (git 18:07:54Z, Jira 18:07:14Z) and git
claims against the live repository at ~18:15Z.

## Verdict

**APPROVE** (0 BLOCKER, 0 MAJOR, 1 MINOR)

## Summary

C2-M1 and C2-M2 are fixed in the r3 draft and its snapshot, and so are the four Job B minors.
- **C2-M1.** `AIUE-50-scratch` and its three commits on no branch are in section 8, with the right record and the
  owner's choice.
- **C2-M2.** Every commit added with or after an approving report now has a class. `35974c9` and `3bf736c` trace
  finding by finding to the approving reviews.

I checked eight new or changed claims and all are correct. Every open item the stage asks for is in section 8,
including the unmet gating criteria. One freshness MINOR: the planning branch moved three minutes after the snapshot.

## Findings

### MINOR

**C3-m1. Freshness (check 2): the planning tip moved to `2e96bff` after the snapshot, and §9 already cites what that
commit adds.**
- The snapshot has `55648d2`. `2e96bff` (2026-10-15T18:10:50Z, after the git read at 18:07:54Z) adds
  `docs/reviews/ai-close-epic-round2{,-response}.md`.
- §9 cites "`docs/reviews/ai-close-epic-round{1,2}.md` on the planning branch". At the snapshot tip the round-2
  report is absent (`git cat-file -e 55648d2:docs/reviews/ai-close-epic-round2.md` fails).
- This changes no class, item or decision.
- The 11 ticket tips, the prototype HEADs and the checked dirty counts are unchanged.
- *Fix:* re-gather the planning tip, or cite round 2 as "committed after the snapshot".

## Status of previous findings (Job B round 2)

| Finding | Status | Evidence |
|---|---|---|
| **C2-M1** `AIUE-50-scratch` | **Resolved** | Snapshot row and §8 row. `git -C AIUE-50-scratch log --oneline 3865c79..HEAD` gives `14abb0d`, `c9d2872`, `de2d327`. Merge-base `0fac655`. `git branch -a --contains 14abb0d` is empty. `AIUE-55-implementation-round1.md` l.166-169 says what the snapshot says (the tree behind the nofma and swap venvs). |
| **C2-M2** `35974c9` and `3bf736c` unlisted | **Resolved** | §3 AIUE-56 and AIUE-55. See spot checks 1 and 2. `01e2d8e` stays an unreviewed change. |
| C2-m1 Freshness | Resolved (new movement: C3-m1) | Snapshot at `55648d2`. `ai-consolidate` and the scratchpad studies are under "Not sources". |
| C2-m2 Owner-item count | Resolved | §1: "decision 9 and three other owner items". §5 items 1, 3, 4 and 5 are open; 2 is struck. |
| C2-m3 Snapshot slips | Resolved | `git -C AIUE-61-cost diff --numstat` gives `70 12 ppp/omp_parallel.F90` and `2 0 ppp/ppp.v`. `jira-children.json` has `resolution` and `created` on all 17 issues; the epic's `created` is present. Read times are per file. |
| C2-m4 Row 2 class | Resolved | Row 2 is Partly met, with "missing: the two together". |

## Spot checks of new or changed claims (8)

| # | Claim (draft location) | Source checked | Result |
|---|---|---|---|
| 1 | AIUE-56 `35974c9` (with the r3 report) is a requested fix for I3-m1, I3-m2 and I3-m3 (§3) | `git show 35974c9`; the r3 report l.56-118 | OK. The I3-m1 table gives "Te box 1.0, median 2, p90 18, max 167". I3-m2 gives "60 of 71 distinct cells" in the legs and asks for the leg fraction. I3-m3 asks for "not tested with icntnunk=1". Every changed claim traces to a finding. |
| 2 | AIUE-55 `3bf736c` (with the r4 report) is a requested fix for I4-m1 and I4-m2 (§3) | `git show --stat`; the r4 report l.37-58; the r4 response | OK. RCA +11/−5, both fixes as asked. |
| 3 | AIUE-47 `63370bd` was committed with the r2 report and is a requested fix (§3) | `git show 63370bd` | OK. Only comment and `#` description lines change, in `bbb/bbb.v` and `capture_check.py`, as the r2 minors asked. (The class edge is I3-m3 in Job A.) |
| 4 | AIUE-49 `6ddbf70` (with the r3 report, README) and `c02dd42` (I3-m1) are requested fixes (§3) | `git show --stat`; the r3 report l.33 and the response | OK. |
| 5 | `32ac1af` and `8ee189d` were each committed with their r2 report (§3) | `git show --stat` | OK. |
| 6 | Snapshot: "every [worktree] is named somewhere", including AIUE-47-serial and AIUE-56-serial | `git grep -n -w` over the ticket tips | OK. `AIUE-47-implementation-round1.md` l.4 and l.108; `AIUE-56-omp-jacobian-fix.md` plan l.80 and l.89. `branch -a --contains` gives the AIUE-47 and AIUE-56 branches respectively. |
| 7 | AIUE-61 prototype commits are on no branch and are cited as RCA evidence at l.75 and l.95 (§3, §8) | `branch -a --contains db6a8ea` (empty); the RCA on the AIUE-55 tip, l.75 and l.95 | OK. |
| 8 | §1 and §8: criteria 1, 6 and 8 Not met; 2, 4, 5, 7 and 9 Partly met; 3 Met on unmerged branches. Open items include the unmet gating criteria | the §2 table rows | OK. The rows match exactly, and §8 has the new row the revised Step 3 requires. |

The snapshot is internally consistent (check 2):
- `jira-children.json` has 17 issues. The latest `updated` is AIUE-62 at 10:17:28-0700, before `read_at`
  18:07:14Z.
- The epic is To Do with no resolution, as §1 and the appendix say.
- The status line is `Dry run - not reviewed, not published`.

## Not independently verified (environment)

- **Jira and Confluence beyond the snapshot.** The snapshot files are the author's copies. Agreeing with them shows
  the draft is consistent with what was read, not that the reads were faithful. Current Jira `updated` and page
  versions can't be checked here (the author's Step 7 does that).
- **Scratchpad studies.** The cost study and AIUE-62's Docker builds are in progress and outside the repo. The draft
  correctly doesn't cite them as evidence.

## What was checked and how (Job B)

- **Draft and snapshot.** `diff` of the r2 and r3 drafts; I read `snapshot.md` and parsed `jira-children.json` and
  `jira-epic.json` with Python.
- **Freshness.** `git rev-parse` on all 11 ticket branches. `git worktree list --porcelain` HEADs for all prototype
  worktrees. `git status --short` counts for AIUE-50-scratch, 61-cost, 61-replay, 53-neg and 57-race-swap. The
  planning-branch log.
- **Spot checks.** The `git show`, `git grep` and `branch --contains` commands in the table above.
