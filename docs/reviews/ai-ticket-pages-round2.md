# Review: ai-ticket-pages (AI-layer change), implementation round 2

Branch `feature/v9-ai-ticket-pages`, worktree `/Users/holma/Documents/uedge/src/uedge-wt/ai-ticket-pages`, base
`4faed39`, tip `cbe4e7b` (round 1 reviewed `88a6560`). Reference: the owner's request and its amendment, the design
defaults, and the main-session decisions on the round-1 majors:
- M1: refuse on missing sections, accept wrapped forms, keep a local append-only sent log;
- M2: full page only on publish, milestone-only flushes, a stated cost, a read-back hash check;
- M3: implement-fix publishes the RCA (otherwise the Jira fallback);
- M4: milestone-only Jira comments, about 8 at most, 1500 characters at most;
- M5: the agent marker on every template;
- all minors, and one corrective update of the live AIUE-61 page.

## Verdict

**REVISE**

## Summary

The revision fixes all five round-1 majors in substance:
- The round-1 wipe case now refuses or parses correctly in every input form.
- Flushes happen only at milestones, and `verify` catches transcription errors.
- `implement-fix` has a route for the RCA.
- The Jira fallback is capped.
- Every template carries the agent marker.

The live AIUE-61 page correction (version 4) is byte-identical to the rendered body, and its Q2 entry now matches
Jira comment 10021. One new BLOCKER came with the M1 fix. The new "Page missing" flow creates a one-line stub and then
renders with `page_id` set. `render` then refuses in every way the skill allows: there is no `--current`, the stub has
no log headings, and `--local` has no last body. So the first ticket page under any epic PRD can never get past "Plan
page for <KEY>; content follows." Seven minors remain; none blocks approval once the BLOCKER is fixed.

## Findings

### BLOCKER

**I2-B1. The new-page path can't render: the stub page trips the M1 safety check** (`ticket-page/SKILL.md:131-134`
"Page missing", `:98-100,116-118`; `ticket_page.py:261-263,277-283`)
- **What's wrong.** Step 4 "Page missing" now does three things in order:
  1. creates the page with a one-line stub body;
  2. commits the `**Ticket page**` line;
  3. renders "from that commit".

  At that point the page id is known. Step 3.2 puts `page_id`/`page_url` into `meta.json` "once known", and step 3
  says "Never work around it by dropping `page_id`". With `page_id` set, `render` needs `--current` or `--local`:
  - with no `--current`: exit 2;
  - `--current` set to the stub: exit 2, "no log section headings";
  - `--local`: exit 2, because `<KEY>.last-body.md` doesn't exist before the first update.

  The skill gives no other route. Under "Failures" the call is reported and the entries stay queued. Every later
  flush takes the same path, because `state.version` is unset, so the page is read, it is still the stub, and the
  render refuses. The ticket ends up with a stub page that the plan's committed `**Ticket page**` line points at, and
  a record that never fills. This is the main path for every ticket under an epic with a PRD page. The round-1 live
  test didn't exercise it, because it created the page with the full body, and the version-4 correction was an update.
- **Evidence.** Throwaway repo `/tmp/rev2tp/g`, `meta.json` with `page_id`:
  - `render` with no `--current`: exit 2, "the page exists (meta has page_id): pass --current … or --local";
  - `--current stub.md` ("Plan page for AIUE-99; content follows."): exit 2, "no log section headings …";
  - the same stub in MCP-wrapped form: exit 2;
  - `--local`: exit 2, "…/AIUE-99.last-body.md doesn't exist".

  Only dropping `page_id`, which the skill forbids, renders it (exit 0, header "This page: not yet created").
- **What would resolve it.** An explicit first-render mode that the skill's "Page missing" step names. For example,
  `render --new-page` (or state `created=<id>` set right after the create) that:
  - accepts a `--current` that is exactly the stub text, or has version 1;
  - keeps every other refusal;
  - is refused once the state file records a written version.

  Acceptance: a helper test sequence (stub create, then render, then `state --save-body`, then a second render with
  `--local`) passes, and no other path weakens the M1 checks.

### MINOR

**I2-m1. `render` accepts a `--current` with only some of the four headings and silently drops the rest**
(`ticket_page.py:216-232,281-283`)
- **What's wrong.** The guard refuses only when `seen == 0`, but `render` always writes all four headings. Two inputs
  get past it:
  - **A truncated `--current`.** The skill tells the agent to "save the part before `## Plan`" by hand when the tool
    result isn't a file. A cut-off copy is accepted, and the missing sections lose every entry that isn't in this
    worktree's sent log. Example: AIUE-61's backfilled Reviews and Owner entries, which are in no sent log.
  - **A heading-like line inside an entry.** Confluence drops continuation indents, so a line starting with `#` ends
    the section early.
- **Evidence.**
  - A `--current` cut after `## Progress` (only `## Progress` and `## Validation` kept) gave `Reviews: 1, Findings and
    decisions: 0` (from 4 and 6), exit 0.
  - An entry with the line `# ran: pytest -k D_only` came back after a simulated round trip without that line: 3215
    chars became 3189, entry count unchanged, exit 0.
- **What would resolve it.** Refuse (exit 2) unless all four headings are present, which matches the decision
  "refuse on missing sections". Optionally also refuse when a section's entry count goes down compared with the sent
  log or the last body.

**I2-m2. The `--local` guard is only a step in the skill; the helper can't check it** (`SKILL.md:93-96`;
`ticket_page.py:275-278`)
- **What's wrong.** `--local` is safe only when the page's version equals `state.version`. The helper never sees the
  version, so a skipped or misread version check silently drops entries a person or another worktree added. This is
  the same "no check behind the agent" pattern as round-1 M1.
- **What would resolve it.** `render --local --page-version N` that refuses when N differs from `state.version`, with
  the skill passing the number from the CQL check.

**I2-m3. The stated cost counts only half of each flush, and narrows the decided milestone list without saying so**
(`SKILL.md:39,45-50`)
- **What's left out of the cost.** To emit the 48.5 KB body, the model must also have it in context: it reads
  `body.md`, or relies on an earlier read. That is about 14k input tokens per flush, and the session's context grows
  by about 28k per flush. Five flushes in one `end-to-end-feature` session add roughly 140k tokens of context. The
  text says the page is read (about 50 KB in) "only when someone else wrote", which suggests no large read otherwise.
  The version-4 update (log line 6665) was emitted with no read of `body.md` in between, from context gathered earlier
  in the session. `verify` proved it faithful, but that is exactly the context load in question.
- **The milestone change.** The decision listed "each validate" as a milestone. The skill flushes `validate` only
  when it runs on its own; otherwise its entry goes out at the next milestone. That is a sensible cost cut, but the
  response doesn't flag it as a deviation.
- **What would resolve it.** State the input and context cost alongside the output cost, and record the `validate`
  narrowing as a deliberate deviation for the main session to confirm.

**I2-m4. `validate` misses the ticket record on `implement-fix` branches and under a tracker dry run**
(`validate/SKILL.md:4,102-106`; `implement-fix/SKILL.md:63-64`; `end-to-end-feature/SKILL.md:25`)
- **No key on `implement-fix` branches.** `validate` takes the Jira key "from the branch name". `implement-fix`
  branches are `bugfix/v9-issue-<N>-<slug>`, so they have no Jira key, yet `implement-fix` says "`validate` queues its
  result". The Validation section of an RCA ticket page stays empty.
- **No `--tracker-dry-run`.** `validate` doesn't accept it, although `end-to-end-feature` passes it "to every skill".
  A tracker dry run therefore still queues `validate` entries in the local store. The next real flush sends them,
  contrary to "nothing is written to … the local store".
- **What would resolve it.** Let callers pass the key (for example `validate … --ticket <KEY>`), and add
  `--tracker-dry-run` to `validate`.

**I2-m5. The in-place running summary can't tell an update from a new comment, and the fallback diverges from
close-epic** (`SKILL.md:182-186`)
- **What's wrong.** The `commentId` update path has never been run. The installed schema documents `commentId` as
  "ID of an existing comment to update" (close-epic session, log line 4276). A community report says updating a
  public comment fails (log lines 4119, 4174). The skill has two gaps:
  - it doesn't check that the returned comment id equals `state.fallback_summary_id`, which is the only sign that a
    new comment was posted instead of the old one being updated;
  - on failure it posts nothing more, so later milestones, including "Committed", never reach Jira. `close-epic` falls
    back to a "Supersedes comment <id>" comment instead.
- **What would resolve it.** Check the returned id; and either justify the different fallback or align it with
  `close-epic`. Whether the update path works is listed under "Not independently verified".

**I2-m6. `verify` after a failed update, and the retry** (`SKILL.md:137-146`; `ticket_page.py:395-422`)
- **What's wrong.** The hook log records only `PostToolUse` events: all 6,703 lines are that event, and
  `post_tool_use.py` logs nothing else. A failed update is therefore not logged, and `verify` compares the new body
  with the previous flush's update, giving a "MISMATCH". The skill then says "update again" with no bound. A
  successful retry returns version N+2, which step 4's "Another writer" rule reads as a concurrent overwrite. That
  queues a false "Possible lost entries" entry and triggers one more flush.
- **What would resolve it.**
  - On a mismatch, check that the update call returned a version before retrying.
  - Allow one retry.
  - Compare the returned version with the version after this worktree's own retries.

**I2-m7. Residual path leaks in the sanitiser** (`ticket_page.py:72-73`)
- **Not replaced:** cluster-style roots (`/scratch/holma/run`, `/gpfs/u/holma/x`, `/homes/holma/x`, and by the same
  rule `/global/homes/…`, `/p/lustre…`, `/g/g19/…`, `/usr/workspace/…`) and `file:///Users/holma/x.html`.
- **Why it matters.** UEDGE runs on such clusters, and the skill's text ("Local paths become …") reads as complete.
- **What would resolve it.** Add these roots and handle `file://` URLs, or narrow the claim.

## Status of previous findings

| Finding | Status | Evidence (checked here) |
|---|---|---|
| I1-M1 log wipe | **Resolved** (but see I2-B1, I2-m1) | My round-1 inputs, taken from the logged version-2 page (log line 6454): plain JSON → 3 Reviews and 6 Findings kept; **MCP-wrapped → 3/6 kept** (was 0/0); storage body → exit 2 "read it again with contentFormat markdown"; no `--current` with `page_id` → exit 2; no headings, an empty file, wrapped error text → exit 2; JSON without `body` → exit 2. Sent log: `queue --mark-sent` appends to `<KEY>.sent.jsonl` and removes only the outbox; a page that lost a sent entry → "1 restored from the sent log". |
| I1-M2 per-log full resend | **Resolved** (cost wording: I2-m3) | `log` only queues; the "When to flush" table (`SKILL.md:32-43`) agrees with `end-to-end-feature` (lines 21-26, loop steps 2-4, escalation, Step 4), `execute` 2d, `validate`, `plan-feature`, `implement-fix` and CLAUDE.md. "5 flushes for one plan and one implementation round" matches publish, plan verdict, end of `execute`, implementation verdict, commit. The mirror moves only on `publish` (`--plan-rev`). `verify` is a check of the sent body against the rendered file, not a read-back from Confluence. I accept it as meeting the decision's intent, the transcription risk, at no read cost; it does not check what Confluence stored. Synthetic logs: match → 0 (trailing whitespace ignored), mismatch → 1 with offset, other page id only → 3; no log or no repo → 3 "unverified"; a nonexistent `--log` → 2. Real log: the v4 body verifies, "(49028 chars); version 4". |
| I1-M3 implement-fix route | **Resolved** (I2-m4 residual) | `publish --rca` → `render --plan-title RCA`; the `**Ticket page**` line goes in the RCA header; the fallback summarises the RCA; step 5b flushes after the commit; 4c runs the review loop, which flushes. |
| I1-M4 fallback volume | **Resolved** (I2-m5 residual) | Milestone comments only, one per flush, `sanitize --max-chars` defaults to 1500, at most 8, the 8th a running summary. A typical run has 5-7 milestones, so the cap fits the decision. |
| I1-M5 agent marker | **Resolved** | Container body (`SKILL.md:127-128`), link comment (`:155`), fallback `publish` (`:168`), other fallback flushes (`:180`) and the page header (`ticket_page.py:307-309`) all carry it. The running summary uses the "other flushes" header. |
| I1-m1 sanitiser | **Resolved** (I2-m7 residual) | `/private/tmp/claude-501/-Users-holma-…/body.md` → `{local}/body.md`; `/tmp`, `/Volumes`, `/opt`, `/var/folders`, `/private/var` → `{local}/<name>`; `{home}/.claude/projects/-Users-{user}-…`; `AIUE-61-serial/x` → `{worktrees}/AIUE-61-serial/x`; `AIUE-61/bbb/pandf.m:513` → `{worktree}/bbb/pandf.m:513`; trailing `.` handled; `https://example.com/home/user/page` and `http://host/Users/x` unchanged; relative paths unchanged. |
| I1-m2 secrets | **Resolved** | All 16 secret cases exit 1, including every round-1 miss (`github_pat_`, `AKIA`, `aws_secret_access_key =`, JWT/Bearer, `glpat-`, `AIza`, `JIRA_API_TOKEN=`, `export ATLASSIAN_TOKEN=`, `token:`, `user:pass@`). Refusals print only pattern names (`grep -c ATATT3` on the output gives 0). Benign "token count was 12 and key: value" passes. False positives (`max_key = 1234567890`) are acceptable: a scan of 601 existing plans, RCAs and reviews in all worktrees found 0 hits apart from a test string in my round-1 report. |
| I1-m3 multi-line dedup | **Resolved** | A two-line entry with a fence, queued twice → 1 copy; after a simulated round trip (indents dropped, `-` → `*`) → "0 new, 0 restored". |
| I1-m4 version-jump recovery | **Resolved** | The skill now claims only what the sent log can restore and queues "Possible lost entries" otherwise (but see I2-m6 for a false trigger). |
| I1-m5 container race, paging | **Resolved** | CQL by parent and exact title; the search is repeated after a create; two containers → stop or report. The logged `content.version` expand returns the version object (log line 6662), while plain `version` returns null (6661), as the skill says. |
| I1-m6 flag wording | **Partially resolved** | `--tracker-dry-run` is used in `execute`, `plan-feature`, `implement-fix` and `end-to-end-feature`, with propagation to sub-agents and loop takers, and unattended "report, write nothing". `validate` lacks it (I2-m4). |
| I1-m7 stale plan commit; lost fallback plan | **Resolved in the design, blocked by I2-B1** | Stub, then commit the line, then render from that commit; the fallback line is committed regardless and `<KEY>.fallback-plan.md` is posted first at the next flush. |
| I1-m8 consistency | **Resolved** | `implement-fix` `allowed-tools` adds `Bash(uv:*)` and four Atlassian reads (it no longer needs descendants); a missing meta key → "meta.json is missing …", exit 2; one escalation comment in the fallback; the CLAUDE.md row is accurate. |
| I1-m9 live AIUE-61 page | **Resolved** | Log line 6665: `updateConfluencePage` on 2293761 → version 4. Its `body` equals `AIUE-61-fix/body.md` (49,028 chars after `rstrip`), which was rendered at line 6664 from `corrected.md` (built from the version-3 body). `verify` on the extracted body gives "version 4". Q2 now reads "user-editable through a documented `ppp` variable (the wording of comment 10021; the progress log says only …)". Comment 10021 (`addCommentToJiraIssue` at line 5276) says exactly "default **64** chunks, user-editable through a documented `ppp` variable". Hash map: all seven new hashes are on the AIUE-61 tip; six of seven patch-ids match. `386a2b5` → `c564653` differs only by the rebase (same subject, hunk offsets, and `refs.lock.json` dropped in the rebase), so the mapping is right and "patch-ids match" is slightly overstated. The plan at `ad5819b`, at `604a667` and at the tip is byte-identical. |

## Not independently verified (environment)

- **Live Atlassian state.** I have no Atlassian MCP. Page 2293761 version 4, the container, and comments 10021/10031
  were checked only from the agent's own logged calls in `UEDGE_v9_dev/logs/post_tool_use.jsonl`. These show what
  was sent and returned then, not what is stored now.
- **Running-summary update.** Whether `addCommentToJiraIssue` with `commentId` updates a comment in place on this
  site. It was never exercised. The schema documents it; a community report says public-comment updates fail.
- **Confluence markdown round trip.** How headings or `#` lines inside list items come back in a markdown read. My
  I2-m1 test simulated the dropped indents.
- **Failed MCP calls and hooks.** Whether Claude Code fires `PostToolUse` for a failed MCP call. The log contains
  only `PostToolUse` events, and the hook logs nothing else.

## What was checked and how

- **Diff.** I read `git diff 88a6560..cbe4e7b` in full: `ticket-page` SKILL.md and `ticket_page.py`, and the wiring
  in `close-epic`, `end-to-end-feature`, `execute`, `implement-fix`, `plan-feature`, `validate` and CLAUDE.md. I also
  read the full current SKILL.md and helper.
- **Branch checks, from the worktree.**
  - `uv run .claude/hooks/change_kind.py --range 4faed39..HEAD`: 11 files, all `process` on an `ai` branch, "OK";
  - `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`: "OK", exit 0;
  - the tip is `cbe4e7b`, the worktree is clean, and `origin/v9-develop` = `4faed39` (the base).
- **Helper runs.** All in the scratch directory `/tmp/rev2tp`, with a throwaway repo `/tmp/rev2tp/g` and `--outbox`
  in scratch. No write to any real worktree's git directory, to Atlassian, or to the repo.
  - `render` on 10 `--current` forms, including the round-1 inputs from log line 6454;
  - the stub new-page sequence (I2-B1);
  - sent-log restore, partial headings, and multi-line and heading-line round trips;
  - a missing meta key;
  - `queue --add/--list/--mark-sent/--sent`;
  - `verify` on 3 synthetic logs, the real log, no log, and a bad `--log`;
  - `sanitize` on 18 path cases and 24 secret or benign cases;
  - a false-positive scan of 601 existing documents with the helper's own patterns.
- **Log evidence.** From `post_tool_use.jsonl`:
  - lines 6418-6489: the round-1 calls;
  - 6660-6666: the correction build, the CQL version checks, the version-4 update and `verify`;
  - 5276: comment 10021;
  - 4119, 4174, 4276: the `commentId` schema and the community report.

  I also read the `post_tool_use.py` hook and `.claude/settings.json`.
- **AIUE-61 worktree.** `git log`, `git merge-base --is-ancestor` and `git patch-id --stable` for the 14 old and new
  hashes; `cmp` of the plan at `604a667`, `ad5819b` and HEAD.
