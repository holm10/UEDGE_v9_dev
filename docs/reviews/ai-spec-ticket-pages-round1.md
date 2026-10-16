# Review: ai-spec-ticket-pages, implementation (AI-layer change), round 1

Branch `feature/v9-ai-spec-ticket-pages`, worktree `/Users/holma/Documents/uedge/src/uedge-wt/ai-spec-ticket-pages`,
base `origin/v9-develop` `e52a44d`, tip `21edb76` (`6f457ac`, `21edb76`). Reference: the owner's request (one
Confluence page per open ticket under its epic, written by `spec` and every later planning/execution skill) and the
author's design claims in the review prompt.

## Verdict

**REVISE**: 0 BLOCKER, 2 MAJOR, 5 MINOR.

## Summary

The core mechanism works as claimed for the main path. `spec` builds a small skeleton with the helper, a fresh ticket
worktree finds that page through the link comment or the CQL listing, the first `publish` is an ordinary `--current`
render that keeps the Ticket section, and the I1-M1 safety properties still hold, now with a refusal when the Ticket
section is lost. I re-ran the selftest (104/104) and both hook checks, and extracted all 43 keyed entries from the two
real breakdowns (AIUE-5 and AIUE-8) without a false match. Two problems remain:

- **Backfill writes false records.** The backfill step (`--pages-only`, or Step 6b on any re-run) creates "Planned"
  skeleton pages that say the branch is "planned, not created yet" and the plan "not written yet". It would do this
  for about 12 AIUE-8 tickets that are In Review, and the new `close-epic` rule then reads those pages as "never
  planned".
- **`find` can give the "create" answer on missing evidence.** It returns exit 3 when it was given no listing or
  could not parse the comments. In the Jira fallback nothing else guards against a second comment, so the
  "re-runnable, never a second page/comment" claim is not yet safe.

Both are fixable without changing the design.

## Findings

### MAJOR

**I1-M1. The backfill creates records that are false for tickets already in progress, and `close-epic` would misread them.**
Location: `spec/SKILL.md:180,199-211` (Step 6.5, 6b.2-3), `ticket_page.py:447-457` (skeleton header),
`ticket-page/SKILL.md` "Jira fallback" `create` template, `close-epic/SKILL.md:133-137`.

- Step 6b runs for "every existing child that has no page yet" and skips only status category Done. In Review
  counts as "In Progress", so it is not skipped. The author's own dry-run input (`/tmp/dry-aiue8/keys.tsv`) lists 17
  children that would get a page. 12 of them are In Review: AIUE-46, 47, 49, 50, 52, 53, 54, 55, 56, 60, 62, 64.
- The skeleton header is hard-coded, whatever the ticket's state: ``**Branch:** `<branch>` (planned, not created
  yet) · **Plan:** not written yet`` and "This page is the ticket's PIV record, created when the ticket was filed"
  (`ticket_page.py:450,454`). For an In Review ticket all three are false: the branch exists (often merged), the plan
  is committed, and the page was made weeks after filing. The `status_note` ("page created after the ticket; Jira
  status In Review") contradicts the header in the same block instead of correcting it.
- The Ticket section's source line says "Scope as filed". For a backfill it is the breakdown as of today
  (`ed33738`), not as filed.
- These tickets will usually never flush again: their `commit` step has already run. So the skeleton stays
  permanently. `close-epic` now says (lines 135-137): "a page whose Plan section is still the placeholder (status
  `Planned`) belongs to a ticket that was never planned". The close-out record would draw that false conclusion for
  every backfilled In Review ticket. That is exactly the kind of wrong claim the close-out reviewer must class as
  MAJOR or BLOCKER.
- The Jira fallback has the same problem. AIUE-58 (In Review; its comments include "Done. Implementation review
  APPROVE (round 2)") would get a `PIV record: ticket filed` comment with "Branch … (planned)" (`/tmp/dry-aiue70/run.sh`).

Which children get a backfilled page is an **owner decision** (the request says "each ticket that's open"; whether In
Review is "open" is the author's own open point). Whichever way it is decided, the content has to be true.

To resolve:
- Get the owner's decision on which statuses are backfilled, and record it.
- For any child that is not To Do, nothing rendered or posted may contradict its state. Either skip it, or use a
  backfill variant with no "planned, not created yet", no "created when the ticket was filed", and the Ticket source
  line naming the revision it was read at, not "as filed".
- Change `close-epic`'s rule so it does not infer "never planned" from a backfilled page (key it on the status note
  or a distinct status).
- Add a selftest case that renders a backfilled In Review skeleton and checks those strings are absent.

**I1-M2. `find` gives the "create" answer (exit 3) on missing evidence. In the fallback, a re-run duplicates the `ticket filed` comment.**
Location: `ticket_page.py:745-792` (`cmd_find`), `spec/SKILL.md:199-205,218-223`, `ticket-page/SKILL.md` step 2.6.

- The callers treat exit 3 as "no page, create it" (ticket-page step 2.6 → "Page missing"; spec 6b.2 "none → create
  it"). But `find` returns 3 whenever it found nothing, including when nothing was given. I ran
  `find --key T-1` with no inputs: `"candidates": {}`, rc=3.
- It also returns 3 when the comments are not markdown strings. I fed it a comment list in ADF form containing both
  a `Ticket page: … Confluence page id 300` link and a bold `PIV record: ticket filed` comment. Result: rc=3 and
  `piv_record_comments: 0`, because `json.dumps(body)` never matches the anchored regexes (`ticket_page.py:765-768`).
- Spec 6b.2 tells the agent to read each ticket's comments with `getJiraIssue` `fields: ["comment", "status"]` but,
  unlike ticket-page step 2.2, does not pin `responseContentFormat: "markdown"`.
- In the Confluence route the "search once more" before the create (ticket-page Create step 4) is a second guard,
  though an agent-run one. In the fallback route there is no second guard. Spec line 218-219 recommends a re-run
  after a partial failure, and that re-run would post a second `PIV record: ticket filed` comment (it counts against
  the 8-comment cap).
- The author's fallback dry run used comment JSON written by hand in `run.sh`, and the AIUE-61 issue JSON was edited
  ("other comments trimmed"). So the real response format was never exercised.

To resolve:
- `find` exits 3 only when it was given what is needed to conclude "none": a container listing for the Confluence
  route, or a parsed comment list for the fallback. Otherwise it exits with a distinct "can't tell" code that the
  callers treat as "stop and report".
- Comment bodies in ADF are flattened to text (or refused, with a message).
- Spec 6b.2 pins `responseContentFormat: "markdown"`.
- Add a selftest case for each of these.

### MINOR

**I1-m1. The `ticket` command's Branch-line tier doesn't work as documented, and its exit 2 is unhandled.**
Location: `ticket_page.py:704-706`.

- ticket-page "Create" step 1 says an entry is found "by `` `<KEY>` `` in its heading or `v9-<KEY>-` in its Branch
  line". The Branch-line tier matches the body of every heading at level ≥ 3. For a phase heading (`### Phase 1`)
  that body includes all of its child entries.
- In a test breakdown with the key only in a bold Branch line under a phase, I got: `several breakdown entries match
  AIUE-46: Phase 1; T1 — First thing` (exit 2).
- The regex needs `**Branch:**`, so it never matches the plain `- Branch:` form in spec's own template
  (`spec/SKILL.md:118`). It also misses `feature/v9-ai-<KEY>-…` branches (AIUE-17).
- Neither caller says what to do on exit 2 (they handle only exit 3), and no selftest covers this tier.
- Impact today is small: every real entry has the key in its heading. I extracted 29/29 keys from the AIUE-5
  breakdown and 14/14 from AIUE-8. AIUE-9, AIUE-21, AIUE-5, AIUE-4 and AIUE-8 were correctly not matched, and AIUE-48
  gets T14.
- To resolve: restrict the Branch tier to headings with no sub-headings (or to the nearest enclosing heading), accept
  the plain form, document exit 2 in the callers, and add a test.

**I1-m2. A stale link comment makes `find` stop on every later run; tickets moved between epics are unhandled.**

- After a page is deleted and created again, the ticket has two link comments. I tested this with comments for ids
  100 and 200 and a listing with only 200: rc=2 with the note "recorded id(s) 100 not among the listed pages". The
  note is computed but doesn't change the outcome, so spec (and any flush that resolves again) stops for that ticket
  every time.
- A ticket moved to another epic (AIUE-58/59 → AIUE-70 happened this week) is "found" through its old link comment
  and kept under the old epic's container. The new epic's `close-epic` lists only its own container, so it misses
  the page.
- To resolve: say what to do in both cases (for example, ignore a listed-absent id once `CQL id = <id>` confirms it is
  gone; for a move, keep the page and say so, or move it).

**I1-m3. The cost and the batch side effects of `spec` are understated.**

- ticket-page "Cost" says `create` costs "about twice the skeleton per ticket … plus one search". Per ticket, the
  procedure actually does:
  - a `getJiraIssue` with all comments (large on long-running tickets such as AIUE-61);
  - a re-search before the create and another after it;
  - the create, the verify, and a link comment.
  That is two writes per ticket, each through a permission prompt.
- For the AIUE-8 backfill that is 17 creates plus 17 comments (34 prompts) and more than 34 searches.
- In `--pages-only` it is unclear whether Step 6.6 (republish the breakdown page from the repo copy) runs: Steps 2-5
  are "skipped" but 6.6 is part of Step 6. If it does run, it overwrites the Confluence copy, which `close-epic`
  notes "can be newer than the repo copy".
- To resolve: state the per-ticket call and prompt count. Consider one container listing before the batch and one
  after it instead of two per ticket. Say whether `--pages-only` republishes the breakdown.

**I1-m4. Wording inconsistencies.**

- The breakdown line is `- Ticket page: …` in the template (`spec/SKILL.md:119`) but `- **Ticket page:** …` in 6b.4
  and ticket-page.
- `plan-feature` says "exact-title search". It is a `~` search plus a prefix filter, which is what keeps finding the
  page after a rename.
- Spec line 223, "a ticket never gets a second … page", is stronger than the design delivers: a race leaves two
  pages, detected and reported.
- Selftest J14 is labelled "spec fills a legacy stub with the skeleton", but spec 6b.2 leaves any existing page as it
  is.
- A plan whose line reads `**Ticket page**: none (no epic PRD page)` is not updated when its epic later gains a page
  created by `spec`. ticket-page step 2.8 covers only a missing line.

**I1-m5. Selftest gaps.**

- Section J does exercise the main lifecycle claims. I read it line by line:
  - skeleton, refusals, verified create;
  - lookup by CQL, link comment and plan line;
  - several → 2, none → 3;
  - first fill with `--current`;
  - `--local` and round-trip flushes;
  - lost-Ticket refusal with its two escapes;
  - legacy page, legacy stub.
- Not covered:
  - the legacy `Plan page:` link comment (only the author's dry run covers it);
  - `piv_record_comments`;
  - the Branch-line tier;
  - a recorded-but-unlisted id;
  - `verify --created` with a wrong `--parent-id`.
- J15 ("ticket filed comment within the cap") checks only that `sanitize` passes the 1500-character cap, not the
  8-comment cap.

## Status of previous findings

Round 1; none. (The earlier ticket-page reviews, rounds 1-3, are separate. Their I1-M1 property, no silent wipe of
the log, still holds; see below.)

## Not independently verified (environment)

- **No Atlassian access in this review.** I could not check any of the following against the live MCP server:
  - the tool and parameter names (`createConfluencePage` `body`/`parentId`/`title`; `getJiraIssue`
    `responseContentFormat`);
  - the shape of `tool_response` in the PostToolUse log, which `verify --created` uses to recover the new page id;
  - the default comment format of `getJiraIssue`;
  - CQL `title ~ "Plan: <KEY>"` matching.

  The tool names agree with the other skills (`implement-fix` `allowed-tools`) and with the existing update-verify
  path that ran live for AIUE-61.
- **The author's dry runs** (`/tmp/dry-aiue8/`, `/tmp/dry-aiue70/`) show the helper's logic on partly hand-written
  inputs:
  - `AIUE-61-issue.json` was edited ("other comments trimmed");
  - the AIUE-58/59/74 comment JSON is written by `run.sh`;
  - `keys.tsv`'s Jira statuses are the author's.

  The results agree with what the helper does on those inputs. That is not evidence that the live reads look like
  them.

## What was checked and how

- `git diff e52a44d..HEAD`: all 11 files read in full (helper, selftest, ticket-page, spec, plan-feature,
  implement-fix, end-to-end-feature, prime, close-epic, CLAUDE.md, branching.md). No product code changed.
- `bash .claude/skills/ticket-page/selftest.sh` → `RESULT: 104 passed, 0 failed` (18 s).
- `uv run .claude/hooks/change_kind.py --range e52a44d..HEAD` → every file is `process` on an `ai` branch, `OK`.
  `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` → `OK` (advisory list only).
  `origin/v9-develop` = `e52a44d`.
- **`ticket` extraction.** On the real AIUE-8 breakdown (`AIUE-8-planning`, last change `ed33738`) I ran AIUE-46,
  47, 48, 50, 51, 56, 57, 58 and 59 (rc 0, each its own entry, AIUE-48 → T14). AIUE-5, 9, 21, 4, 60, 61 and 8 gave
  rc 3. In a bash loop over every backticked key, AIUE-5 gave 29/29 and AIUE-8 gave 14/14. The synthetic
  Branch-line-only breakdown is described in I1-m1.
- **`find`.** No inputs → 3. ADF comments → 3 with `piv_record_comments` 0. Stale plus recreated link comments → 2,
  with the note. A markdown `**PIV record` comment → count 1.
- **Safety, read in the code and in the selftest.**
  - The skeleton refuses `--local` and any `page_id` without `--new-page` (`ticket_page.py:347-349`).
  - `--new-page` still requires the exact stub.
  - Missing log headings are still refused.
  - The lost-Ticket check applies only with `--current` on the same page with a last body (`:434-436`).
  - Legacy pages (last body without a Ticket section) are never refused, and no Ticket section is invented for them
    (J13).
  - The first fill of a page `spec` made has no last body, so it is a plain `--current` render (J7).
- **Orders I traced.**
  - `spec` then `plan-feature`: link comment or CQL, then step 2.8 adds the plan line, then `--current`.
  - `plan-feature` then `spec` re-run: the link comment from "Page missing", or CQL.
  - Two racing specs: the post-create re-search detects them and stops; two pages remain.
  - Summary renamed: the `Plan: <KEY> - ` prefix is unchanged, and the update renames the title.
  - Ticket moved between epics: see I1-m2.
- **`Plan page:` → `Ticket page:`.** Handled in `find` (`(?:Ticket|Plan) page:`), `prime`, and ticket-page step 2.6
  and step 5. `close-epic` doesn't parse link comments. No other skill mentions either heading.
- **"Posted by an agent" marker.** Present on the skeleton header, the container body, the link comment, and the
  fallback `ticket filed` template.
- **Path roots.** The documented masked roots match `PATH_ROOTS`/`SHORT_ROOTS` (`ticket_page.py:93-95`) exactly
  (L1-m8 closed).
- **Branching.** The planning branch is a ticket-kind branch for `change_kind.py`, so committing `docs/specs/` there
  is `artifact` and allowed. The `branching.md` row now names the Ticket-page lines.
- **The 8-comment cap with the `ticket filed` comment.** It relies on the agent checking `state.fallback_count`
  against the ticket's comments (documented). `spec` keeps no state, so the ticket worktree starts at 0 and must
  count the comment; the helper's `summary` bookkeeping does not do this by itself.
