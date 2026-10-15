# Review: close-epic skill (AI-layer change), round 2 — and close-out stage test, round 2

Branch `feature/v9-ai-close-epic`, worktree `/Users/holma/Documents/uedge/src/uedge-wt/ai-close-epic`, tip `9660c36`
(round 1 reviewed `2a87c61`), base `origin/v9-develop` `3865c79`. Gathered 2026-10-15T17:58Z.

This file is under the session scratchpad, not `docs/reviews/`. It was not committed anywhere.

---

# Job A — stage: implementation (AI-layer change), round 2

## Verdict

**REVISE** (0 BLOCKER, 1 MAJOR, 3 MINOR)

## Summary

`9660c36` fixes both round-1 blockers.

- **I1-B1.** I re-ran the merged-ticket recipe on `feature/v9-ai-layer` and it now gives PR #1's real 6 commits and
  44 files / +4910.
- **I1-B2.** It follows the main-session direction. The reviewer's `tools:` line is unchanged, a sources snapshot is
  defined, and the close-out stage checks Jira and Confluence claims against that snapshot.
- **Other round-1 findings.** The majors on final status and attribution, and minors 1-6, are fixed as described.
  Minor 7 (the merge conflict) is correctly left for merge time.

One new MAJOR comes from the new status table. A gating criterion that is Not met, Partly met or No evidence is not
an "open item". So an epic whose children are all Done can end as "Closed by the owner … 0 accepted-open" without the
owner ever answering for the unmet criterion. Three minors are edge cases of the new merge recipe and a freshness
check the reviewer can't perform. Both hooks are clean.

## Findings

### MAJOR

**I2-M1. An unmet gating criterion never becomes an owner question, so "Closed by the owner" can hide it.**
Locations: `SKILL.md:236-252`, `:263-270`, `:345-352`; `uedge-reviewer.md:105-108`.

*Problem.*

- Step 3 says the epic is complete only if every gating criterion is Met or Superseded *and* the not-done lists are
  empty. But the not-done list (l.238-249) has no entry for "gating criterion not Met/Superseded".
- Step 6 asks the owner "for each open item" (l.345). Question 4 (Done) is offered when every open item is answered
  (l.350).
- So take an epic whose children are all Done and merged, but where one gating criterion is Not met or No evidence
  (for example, CI never shown green). It has zero open items:
  - its status line becomes `Close-out draft - epic not complete (0 open items)`;
  - Done is offered vacuously;
  - the permanent record then reads `Closed by the owner on <date> - 0 accepted-open, 0 deferred`.
- The owner never answered for the criterion. Reviewer check 7 accepts that status, because it also keys on "every
  open item".
- This breaks the skill's first rule (l.19-21: "When something is not done, the owner chooses per item"). It also
  reopens the gap I1-M1 asked to close.

*Evidence.* Read the skill at l.236-252, 263-270 and 340-354, and reviewer check 7. In the AIUE-8 r2 draft the unmet
criteria (1, 6, 8) happen to be covered by other items (decision 9, AIUE-61, the AIUE-57 merge condition). That is
luck, not the rule.

*Acceptance.*

- The not-done list includes "each gating criterion not Met or Superseded (class and the missing part)".
- Step 6 question 1 covers those items.
- The `Closed by the owner` status and reviewer check 7 require an owner answer for each one.
- `Close-out draft (0 open items)` can't occur while the epic is not complete.

### MINOR

**I2-m1. Stacked tickets merged in one PR resolve to the same merge commit, so one range covers both tickets**
(`SKILL.md:155-156`, `:168`).

- For a branch tip that is an ancestor of `origin/v9-develop`, `rev-list --first-parent --merges --ancestry-path
  <tip>..origin/v9-develop | tail -1` returns the first first-parent merge that contains the tip.
- If a stack is merged through its top PR, or the parent was squash-merged before the child's merge, two or more
  children map to the same `M`.
- `M^1..M^2` then gives each child the whole stack's commits, records and default-results statement. For example,
  AIUE-54 and AIUE-55 would each show both tickets' RCA and data.
- This epic is a deep stack (46 ← 49 ← 52 ← 57, …), so this is a likely ending.
- *Acceptance:* if two children resolve to the same `M`, or `M^1..M^2` contains another child's tip, take each
  child's range from the actual-base rule (`<parent-tip>..<tip>`) and note the shared merge.

**I2-m2. Without `gh`, squash or rebase merges are found only by subject** (`SKILL.md:147-151`).

- `gh` is not installed here (`which gh` → not found).
- Take a squash-merged child whose squash subject doesn't contain the key. GitHub's default PR title for a
  multi-commit branch is the humanised branch name, e.g. "Feature/v9 AIUE 55 …", which the `<KEY>([^0-9]|$)`
  regex does not match.
  - If the branch still exists, the child is reported "local, not merged".
  - If the branch was deleted, the child is listed with its Jira state only.
- The skill has no git-only fallback.
- *Acceptance:* without `gh`, either compare patch ids (`git cherry origin/v9-develop <branch>`, or the patch id of
  the branch diff against candidate squash commits), or treat "Jira Done, no merge found" as an open item, "merge not
  located". Also state the limitation in section 10.

**I2-m3. Reviewer check 2 asks for a Jira freshness comparison the reviewer can't make**
(`uedge-reviewer.md:85-87`).

- Check 2 says to compare "Jira `updated`" with the current repository. The reviewer has no Atlassian access, so it
  can only compare git.
- *Acceptance:* the check says Jira and Confluence freshness is the author's Step 7 re-check. The reviewer lists it
  under "Not independently verified", along with the fact that snapshot files are the author's copies: checking
  against them proves consistency, not authenticity.

## Status of previous findings

| Finding | Status | Evidence |
|---|---|---|
| I1-B1 merged / deleted / squashed branches | **Resolved** (squash and rebase rows untested; see I2-m1, I2-m2) | Re-ran on `feature/v9-ai-layer`. The first-parent subject grep finds `0fac655 Merge pull request #1 from holm10/feature/v9-ai-layer`. The tip `a420824` is an ancestor. `rev-list --first-parent --merges --ancestry-path a420824..origin/v9-develop \| tail -1` gives `0fac655`. `M^1..M^2` gives 6 commits (`2a45d3f`…`a420824`). `git diff --shortstat 0fac655^1 0fac655` gives `44 files changed, 4910 insertions(+)`, and dirstat is all `.claude/`. The records filter gives none. The inverted default-results filter flags no path, so "no change to built or run-time code" is correct. |
| I1-B2 reviewer can't read Atlassian | **Resolved as directed** | `uedge-reviewer.md:4` is still `tools: Read, Grep, Glob, Bash, Write, WebSearch, WebFetch`, i.e. not widened. The snapshot is defined at `SKILL.md:77-91`. The stage text at reviewer l.73-78 checks against `jira-*` / `confluence-*` and lists what it can't check. A Step 7 re-check is at l.362-364. Residual: I2-m3. |
| I1-M1 status for an epic closed with accepted-open items | **Resolved** (new related MAJOR I2-M1) | Four-value table at `SKILL.md:261-270`; reviewer check 7. |
| I1-M2 attribution | **Resolved** | Table at l.107-117; Step 6 q2 at l.347-348; reviewer check 5. |
| I1-m1 PRD local-copy shortcut | Resolved | l.125-126: always read the page and diff it. |
| I1-m2 worktree / branch patterns | Resolved | `--porcelain` with last-component filter. Re-run: matches `uedge-wt/AIUE-47`, `AIUE-47-serial`, `AIUE-47-serial2`. One tip per branch (l.154). |
| I1-m3 default-results filter | Resolved | Inverted allowlist at l.197-202. |
| I1-m4 epic-comment update | Resolved | Fallback "Supersedes comment <id>" at l.382-383. |
| I1-m5 unmerged presented as delivered | Resolved | Class at l.226; template at l.287-288; reviewer check 3. |
| I1-m6 procedural gaps | Resolved | Q4 conditional (l.350-352); no parent (l.357); "This page" field (l.275); `closeout/` fallback (l.36); counts (l.278). |
| I1-m7 conflict with `feature/v9-ai-adversarial-ticket-review` | Deferred to merge time, accepted | `git merge-tree --write-tree --name-only HEAD feature/v9-ai-adversarial-ticket-review` still reports content conflicts in `.claude/agents/uedge-reviewer.md` and `CLAUDE.md` only. The resolution in the response is the one round 1 gave. |

## What was checked and how (Job A)

- `git diff 2a87c61..9660c36`: 3 files (`SKILL.md`, `uedge-reviewer.md`, `branching.md`). I read the whole revised
  `SKILL.md` and reviewer stage, and the `branching.md` row.
- Merged-path walk-through as in the table above. `which gh`: not found.
- `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`: lists docs citing changed files, then
  `OK`, exit 0.
- `uv run .claude/hooks/change_kind.py --range origin/v9-develop..HEAD`: branch `ai`, 5 process paths, `OK`,
  exit 0. The worktree is clean.
- `git merge-tree` against `feature/v9-ai-adversarial-ticket-review`, as in the table.

---

# Job B — stage: closeout, round 2 (test of the revised stage on `AIUE-8-closeout-draft-r2.md`)

Applied the stage exactly as written in `ai-close-epic/.claude/agents/uedge-reviewer.md:69-113`.

- **Jira and Confluence claims** were checked against
  `scratchpad/closeout/AIUE-8-closeout-sources/` (snapshot 2026-10-15T17:47:08Z).
- **Git claims** were checked against the live repository at 17:58Z.

## Verdict

**REVISE** (0 BLOCKER, 2 MAJOR, 4 MINOR)

## Summary

The r2 draft is much better than r1, and every round-1 stage finding is addressed. Of the 20 claims I traced, 18 are
right, including all bases, tips, commit counts and diffstats, the decision attributions, and the numbers in results
and criteria. The status line and the dry-run appendix match the snapshot.

Two open items that the stage's check 4 requires are missed:

- the `AIUE-50-scratch` worktree holds three commits that are on no branch (the snapshot says it is "not named in a
  record", but two records name it);
- AIUE-56's `35974c9` commits the approving report together with new residual figures, and the draft doesn't list
  it.

The freshness check found movement after 17:47Z. None of it changes a class, an item or a decision. No BLOCKER: no
criterion is claimed met against its record, and no unsourced owner credit.

## Findings

### MAJOR

**C2-M1. Commits on no branch in `uedge-wt/AIUE-50-scratch` are missed, and the snapshot misdescribes the worktree.**
Locations: draft §8 and §3 "Children with no branch"; `snapshot.md` prototype table.

*Evidence.*

- `git branch -a --contains 14abb0d` is empty.
- `3865c79..14abb0d` holds three commits found nowhere else:
  - `de2d327` "scratch: threadprivate copy checker";
  - `c9d2872` "scratch: copy scalars before arrays";
  - `14abb0d` "scratch: -ffp-contract=off" (`setup.py`).
- The snapshot says "not named in a record read", but two records name it:
  - `feature/v9-AIUE-55-omp-jacobian-rca:docs/reviews/AIUE-55-implementation-round1.md:166-169` names it as the tree
    behind the C1 confirmation and the no-FMA build that the RCA's option A rests on;
  - `AIUE-57-validation.txt:44` names "AIUE-50-swap … source tree since reused".
- The draft flags the analogous AIUE-61-replay commits but omits these.
- Check 4: "commits on no branch … Any open item the record misses is MAJOR".

*Acceptance.* The snapshot and §8 list `AIUE-50-scratch` with its three commits on no branch and what they are,
citing the AIUE-55 r1 report, plus the owner's choice: keep, push to a branch, or discard.

**C2-M2. AIUE-56's post-APPROVE commit `35974c9` isn't listed or classified, and it adds new claims.**
Location: draft §3 AIUE-56, "Post-APPROVE `1553e75` … text only".

*Evidence.*

- `35974c9` ("Fixes the AIUE-56 round-3 review minors"; body "Includes the round-3 report (APPROVE)") commits the
  approving report together with a change to `docs/reviews/AIUE-56-validation.txt`. The change:
  - replaces the residual size "about one ulp … (median 1; Te box 0.5)" with "Te box 1.0; full problem median 2,
    p90 18, max 167 (… a factor 2 low)";
  - adds "93% (60 of 71 distinct cells) are in the divertor legs";
  - adds "an icntnunk=1 run was not tested".
- The skill (l.192-196) and check 4 say a commit "committed *together with*" the approving report that adds "new
  results or claims in a document" is an unreviewed post-APPROVE change.
- AIUE-55's `3bf736c` (approval plus RCA edits) is a lighter case. It narrows "R = ubw 0 for 4, 8 and 16 chunks" to
  "0 for 8 and 16 (4 chunks not emulated …)". It isn't listed either.
- Round 1 called `35974c9` text only, under the old, unwritten rule. The revised rule reclassifies it.

*Acceptance.* §3 lists every commit that adds or follows each approving report, `35974c9` and `3bf736c` included,
each with its class. `35974c9` goes to §8 as an unreviewed post-APPROVE change, or carries a stated reason it is text
only.

### MINOR

**C2-m1. Freshness (check 2): sources moved after 17:47Z. Nothing moved changes a class, item or decision.**

- Planning tip `82b5be8` → `55648d2` (10:55 PDT). It adds `docs/reviews/ai-close-epic-round1{,-response}.md`.
  §9 could cite these as it does for the other AI-layer branch.
- `feature/v9-ai-close-epic` `2a87c61` → `9660c36` (the draft quotes no tip).
- A new worktree, `uedge-wt/ai-consolidate` (`feature/v9-ai-consolidate`, `a9696d1`), appeared at ~10:59. No source
  read links it to the epic.
- All 11 ticket tips and all prototype HEADs and dirty counts are unchanged.
- Agents are still writing in the session scratchpad (`cost/single/` 11:00, `linux/docker/build_uedge_fma.sh`
  10:59). That is outside every source the skill reads. The draft correctly shows the cost study and AIUE-62 as in
  progress.
- Jira `updated` can't be re-checked here.

**C2-m2. The open owner-item count is inconsistent.** §1 says "decision 9 and four other owner items are open". §5
lists items 1, 3, 4 and 5 as open (2 answered), which is decision 9 plus three. *Fix:* make the count match the
list.

**C2-m3. Snapshot slips.**

- `snapshot.md` gives the cost study as `ppp/omp_parallel.F90 +82/−12`. `git -C AIUE-61-cost diff --numstat` gives
  `70 12`; 82 is the changed-line total.
- `jira-children.json` lacks the `resolution` and `created` fields the skill's table requires (l.83).
- Read times are given as "17:5xZ".

**C2-m4. The "Met (on unmerged branches)" class on row 2 rests on two branches never tested together.** The draft
says so explicitly, as check 3 asks. But the stage doesn't say whether such a criterion may still be "Met (on
unmerged branches)" or must be "Partly met". *Fix:* the author states the choice, or the stage settles it.

## Status of round-1 stage-test findings (`AIUE-8-closeout-review-round1.md`)

| Finding | Status | Evidence |
|---|---|---|
| C1-M1 stale vs planning tip | **Resolved** | r2 is gathered at `82b5be8`. It records the AIUE-62 approval, the cost study, the close-epic request, the RHS probe and `AIUE-61-cost`. New movement is in C2-m1. |
| C1-M2 phi item, AIUE-50 I1-m6 | **Resolved** | §5 item 4; §8 rows; AIUE-50 response l.14 verified verbatim. |
| C1-M3 AIUE-46 `f5fee63` | **Resolved** | §3/§8. `git show --stat f5fee63`: report plus `input_mod4.py`, `fingerprint.py`, `trim_case_data.py`. Related new gap: C2-M2. |
| C1-M4 clang attribution | **Resolved** | "Attribution unverified". `ed33738` (00:03:12) contains "(owner, 2026-10-15)" (diff l.378). |
| C1-m1 … m6 | **Resolved** | Row 2 cites AIUE-53 R2-1 l.317/l.419; `460aa5f..e71fafc` changes `bbb/` only in a `bbb.v` `#` description. Row 3 and UX use the unmerged class. AIUE-62 has a default-results line. §7 has the "who agreed" column. Per-ticket bases are given. Docker is unverified. |

## Claims traced (20)

| # | Claim (draft location) | Source checked | Result |
|---|---|---|---|
| 1 | Status `Dry run - not reviewed, not published` (l.4) | check 7 | OK |
| 2 | 17 children, 0 Done; AIUE-54/62 In Progress, rest In Review or To Do (§1, §3) | `jira-children.json` | OK |
| 3 | Bases: 49←46, 50←46, 52←49, 53←49, 54←50 (not 52), 55←54, 57←52, 62←55; 47, 56 on `origin/v9-develop` (§3) | `merge-base --is-ancestor` | OK (all 10) |
| 4 | Tips, commit counts, shortstats for all 11 tickets (§3) | `rev-list --count`, `diff --shortstat` | OK (e.g. 54: 4 commits, 255 files +15714/−1; 56: 9, 19 files +1669/−16) |
| 5 | Default results: only 47 (`bbb.v`, `oderhs.m`) and 56 (`omp_parallel.F90`) touch built code (§3) | inverted filter on each range | OK |
| 6 | AIUE-46 `f5fee63` is an unreviewed post-APPROVE change with 3 files (§3) | `git show --stat` | OK |
| 7 | AIUE-55 r4 APPROVE in `3bf736c`; `01e2d8e` adds addendum results (§3) | report verdict line; stat (+31 RCA) | OK |
| 8 | AIUE-56 post-APPROVE only `1553e75`, text only (§3) | `log` after the r3 report | **Missed `35974c9`** (C2-M2) |
| 9 | Verdicts: 46 r1, 52 r3, 53 r3, 57 r2 APPROVE; 54 r2 REVISE (§3) | `grep -m1` on each report | OK |
| 10 | AIUE-56-validation l.6 AGREE 42 cases; l.9-20 gate PASS; worst 4.59e-9 / 7.15e-9; pre-fix 6.871e38; Te box 1/30, full 0/30; ratio 0.995 l.81; l.128 "not run as specified" (§2, §4) | the file at the tip | OK |
| 11 | AIUE-57-validation l.42 "NOT the AIUE-56 fix", l.119 "NOT SHOWN", l.237 `te(ix=5,iy=18)` (§2 row 8) | the file | OK |
| 12 | Contradiction: Jira 10009 says "C1-fixed build (AIUE-56) still red" vs the validation's swap proxy (§10) | `jira-comments.md`; validation l.42 | OK |
| 13 | Pre-fix rates: Te box 0/20, 20 distinct, 0.1357–0.1786 vs 0.3221; full 16 distinct, nnz 3,632,025–3,677,607 vs 3,190,290, max\|J\| 5.98e43 vs 1.7e14 (§4) | RCA l.303, 306, 313 | OK |
| 14 | Option A: serial fnrm 3.4e-9 relative; 1e-6 "a margin over that" (§2, §4) | RCA l.70, 153, 156 | OK |
| 15 | Replay cost +18 % to +70 % (§4) | progress log 05:00–05:45 | OK |
| 16 | Owner approved AIUE-62; owner asked for cost study and close-epic (§5, Owner) | progress log "Owner follow-up 2" | OK, sourced as Owner per the attribution table |
| 17 | Owner authorised round 4 (§5, Owner); Docker passive → unverified | progress log "Owner follow-up" | OK |
| 18 | "Run parallel waves: Agent, after the owner asked" (§5) | progress log 00:20 "User asked about parallel delegation" | OK |
| 19 | Jira comments quote pre-restack tips `de57d59`, `45a9aa1`, `35974c9` (§10) | `jira-comments.md` 10004, 10010, 10011 | OK |
| 20 | Appendix: space 196612, parent 1540097, no close-out page, no close-epic comment, Done = transition 41 | `confluence-pages.json`, `jira-epic.json`, `jira-transitions.json` | OK |

Also checked:

- PRD blob `99f0181d` (`git rev-parse HEAD:docs/prds/…`) matches the snapshot.
- §11 coverage: criteria 1-9, B1, B2, Q and UX are all present.
- Prototype worktrees via `--porcelain` plus `branch -a --contains`: AIUE-47-serial and AIUE-56-serial HEADs are on
  branches; AIUE-50-scratch and AIUE-61-* are not.

**Not independently verified:**

- Every Jira and Confluence fact beyond agreement with the snapshot: the snapshot's fidelity to Atlassian, current
  Jira `updated`, and the PRD page-vs-copy comparison (done "by reading").
- Whether `feature/v9-ai-consolidate` relates to the epic.
- Scratchpad work in progress.

## Is the revised stage usable? (Job B assessment)

- **Yes, for a git-heavy epic.** Checks 1, 3, 5, 6, 7 and 8 map one-to-one onto the template, and each could be run
  mechanically. The snapshot made every Jira and Confluence claim in this draft checkable, and the severity rule
  (number errors that change the meaning are MAJOR, rounding slips MINOR) let me rank without contortion.
- **Freshness (check 2) works for git and is sensible about scope.** Planning tip, ticket tips and worktree state can
  be diffed against `snapshot.md` in a minute.
  - The Jira half is unworkable for the reviewer (I2-m3).
  - Agent scratch work outside the repo is invisible to both author and reviewer. Treating it as "in progress, not a
    source" is the right call, but the stage should say so explicitly.
- **Check 4's text-only line is now strict enough to bite.** It reclassified a commit round 1 had called text only
  (C2-M2).
  - Nearly every "fix the approving round's minors" commit edits a validation record or RCA, so authors will need a
    tie-breaker. One option: a third class, "post-APPROVE fix of the approving reviewer's own minors, not re-reviewed".
    It would be listed but treated as low risk.
- **Prototype discovery needs the record grep, not just `git status`.** The miss (C2-M1) came from labelling a
  worktree "not named in a record" without grepping the records for its path or HEAD. The stage could require
  `git grep -n '<worktree name>\|<HEAD short sha>'` over the epic's ranges before accepting that label.
- **The status logic still depends on I2-M1.** Check 7 can't catch "Closed by the owner" over an unmet criterion
  until unmet gating criteria count as open items.
