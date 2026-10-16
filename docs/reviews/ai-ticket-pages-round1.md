# Review: ai-ticket-pages (AI-layer change), implementation round 1

Branch `feature/v9-ai-ticket-pages`, worktree `/Users/holma/Documents/uedge/src/uedge-wt/ai-ticket-pages`, base
`4faed39`, tip `88a6560` (`525c9b2` skill and helper; `88a6560` wiring). Reference: the owner's request and its
amendment, plus the design defaults, as given in the review prompt.

## Verdict

**REVISE**

## Summary

The design covers the owner's request: one container per epic under the PRD, one page per ticket, a link from Jira, a
Jira-comment fallback for tickets with no epic PRD page, an outbox so a failure never blocks, `--dry-run` and
`--no-tracker`. It also does not overreach: no transitions, no description edits, no edits to other pages. The branch
checks are clean and the live test worked: the plan mirror on the page is byte-identical to the demoted and sanitised
plan, and the page has no local paths. Five MAJOR findings remain:
1. The helper silently erases a page's whole log when the current page body comes in a form it doesn't recognise.
2. Every `log` call makes the model read and re-emit the whole 48–52 KB page, which is a large cost and a transcription
   risk.
3. `implement-fix` has no defined way to create a Confluence page.
4. The Jira fallback has no real limit on comment count, which conflicts with "kept short".
5. Two of the three Jira comment templates don't say the comment was posted by an agent.

## Findings

### MAJOR

**I1-M1. `render` silently erases the page's log when `--current` is missing or in a form it doesn't parse**
(`ticket_page.py:155-162`, SKILL.md step 3)
- **What's wrong.** Once `queue --clear` has run, the page is the only store of past entries. `render` rebuilds all
  four log sections from `--current`. Three cases give an empty log and still exit 0:
  - `--current` is left out. It is optional, even when `meta.json` has a `page_id`.
  - The file holds the MCP content-array form, `[{"type":"text","text":"{...}"}]`. That is the form the tool response
    takes in `logs/post_tool_use.jsonl`.
  - The page was read without `contentFormat: "markdown"`, so `body` is a `{"storage": ...}` dict.

  In all three cases the next `updateConfluencePage` wipes every earlier entry. The "append-only" promise depends on
  the agent getting this step right with no check behind it. The test also shows that, for a page below the tool's
  save-to-file threshold, the agent has to retype the log sections into `current.md` by hand (`Write` at log line
  6458), which is another unchecked chance to change past entries.
- **Evidence.** I took the logged `getConfluencePage` v2 response (3 Reviews and 6 Findings entries) and ran `render`
  with the same entry against three inputs:
  - plain JSON: `Reviews: 3, Findings and decisions: 6`;
  - the same JSON wrapped as a content array: `Reviews: 0, Findings and decisions: 0`, exit 0;
  - `body` as a storage dict: `0 / 0`, exit 0.
- **What would resolve it.**
  - When `meta.page_id` is set, `render` refuses (exit 2, with a message) if `--current` is missing or contains none of
    the four section headings.
  - `render` accepts the content-array wrapper.
  - Better still: `render` refuses whenever the number of earlier entries would go down, for example by checking
    against a local "sent" log that `queue --clear` appends to instead of deleting.

**I1-M2. Every `log` call re-sends the full page through the model** (SKILL.md steps 3-4; callers in `execute`,
`validate`, `end-to-end-feature`)
- **What's wrong.** An MCP `body` argument can only be produced by the model. So every `log` means:
  - reading the current page (about 50 KB) into context;
  - emitting the whole rendered body (48–52 KB, about 12–15k output tokens) as the `updateConfluencePage` argument.

  `execute` logs once per task or commit, `validate` once per run, and the review loop once per round plus once per
  response. AIUE-60/61-sized plans are 45–50 KB, so a ticket's 15–25 calls cost about 0.3–0.6 M tokens, mostly slow
  output generation. Inside one `execute` session this can fill the context. Nothing checks that the re-emitted body
  matches the rendered file: the test happened to be faithful, but that is unverified for a 50 KB transcription.
  `close-epic` (every ticket page in full) and `prime` add 50 KB reads on top. The design never acknowledges this
  cost. "Never blocks the code workflow" holds only in the narrow sense that the calls don't stop the workflow, not in
  what they cost it.
- **Evidence.** In the tool log, the update inputs were 48,387 chars (v2) and 48,527 chars (v3). `cmp` shows they are
  identical to `body2.md`/`body4.md` and `body3.md`. Line 6443 reads all of `body.md` into context before the create.
  The `getConfluencePage` response was 50,637 chars inline.
- **What would resolve it.** A design that keeps per-entry calls small, or a justified cost estimate the owner
  accepts. Options include:
  - the plan on its own child page, re-sent only on `publish`;
  - log entries queued and flushed at milestones (end of `execute`, after `validate`, after each review verdict);
  - a read-back check, comparing a normalised hash of the stored log sections with the rendered ones.

**I1-M3. `implement-fix` has no defined Confluence route** (`implement-fix/SKILL.md:15-17,59`; `ticket_page.py`
`render --plan` required)
- **What's wrong.** `implement-fix` runs `ticket-page` "as `execute` and `validate` do", which means `log` calls only.
  When the Jira key's epic has a PRD page and no ticket page exists yet, step 4 ("Page missing") needs `render --plan`.
  A bug-fix branch has no `.claude/plans/` file whose `**Branch / worktree**` line names it; it has an RCA document,
  and nothing calls `publish`. As a result:
  - every call fails;
  - the entries pile up in the outbox;
  - the outbox is deleted with the worktree (`git worktree remove`, `branching.md:66`).

  The Jira-fallback route works, because comments need no plan.
- **What would resolve it.** State which document `implement-fix` mirrors, for example
  `render --plan docs/rca/issue-<N>.md`, and where its `**Ticket page**` line goes. Make `implement-fix` call
  `publish` once, after the RCA or fix plan is committed. Alternatively, send `implement-fix` to the Jira fallback,
  and say so.

**I1-M4. The Jira fallback has no real cap on volume** (SKILL.md "Jira fallback")
- **What's wrong.** The owner's amendment asks for a brief record, "kept short". The fallback posts one comment per
  `log` call, and `execute` logs once per task or commit. A typical ticket (8–10 tasks, 2–4 validate runs, 2–4 review
  rounds plus responses) therefore reaches about 15–25 comments, each sending watcher notifications. The roughly
  1500-character cap limits each comment, not the record. The note after about ten comments is only a suggestion to
  re-parent the ticket.
- **What would resolve it.** In the fallback, post only at milestones: the plan, each review verdict, the final
  validate result, escalations or owner decisions, and the commit. Fold the per-task Progress entries into one
  comment, for example at the end of `execute`. Alternatively, give a firm cap and say what happens past it. Either
  way, or a justification the owner accepts.

**I1-M5. Two of the three Jira comment templates don't say the comment was posted by an agent** (SKILL.md step 5;
"Jira fallback" `log` template)
- **What's wrong.** The link comment template (step 5) and the fallback `log` template
  (`**PIV record: <Section>** (<date>, <caller>)`) carry no "posted by an agent" marker. Only the fallback `publish`
  template has one.
- **Why it matters.** These comments appear under the owner's account. The fallback comments carry `Owner:` decisions
  and review verdicts. Under `close-epic`'s rules, an unmarked comment cannot be told apart from the owner's own words.
- **Evidence.** The author's real comment 10031 ends "(Posted by an agent, ticket-page skill.)" (tool log line 6451),
  and the AIUE-58 dry-run `log-reviews.md` has "; posted by an agent". The templates a future run will follow don't.
- **What would resolve it.** Add the marker to both templates.

### MINOR

**I1-m1. Path sanitising has gaps and makes misleading replacements** (`ticket_page.py:56-66`). Tested with
`sanitize --repo …/AIUE-61`:
- **Left as they are:**
  - `/private/tmp/claude-501/-Users-holma-Documents-…`, the session scratchpad the skill recommends, which leaks the
    encoded user name;
  - `/tmp/…`;
  - `/Volumes/…`;
  - `/opt/…`.
- **Partly replaced:** `{home}/.claude/projects/-Users-holma-…` keeps the encoded user name.
- **Wrong:**
  - `…/uedge-wt/AIUE-61-serial/x` becomes `{worktree}-serial/x`, because there is no path-boundary check and sibling
    worktrees like `AIUE-56-serial` exist;
  - `https://example.com/home/user/page` becomes `https://example.com{local}/page`, which breaks the URL;
  - a repo passed as `/tmp/…` resolves to `/private/tmp/…`, so text that uses `/tmp/…` is not replaced.

The docstring's "Any other user or temp path" is not true. **To resolve:** replace on path boundaries only, skip
URLs, and cover `/tmp`, `/private/tmp`, `/Volumes` and encoded `-Users-<name>-` segments, or narrow the claim.

**I1-m2. The secret patterns miss common forms** (`ticket_page.py:42-49`)
- **Not refused (all exit 0):**
  - `github_pat_…`;
  - `AKIA…`;
  - `aws_secret_access_key = …`, because `\b` fails after `_`;
  - JWTs and `Authorization: Bearer eyJ…`;
  - `glpat-…`;
  - `AIza…`;
  - `JIRA_API_TOKEN=…`, `export ATLASSIAN_TOKEN="…"` and `token: …`;
  - `https://user:pass@host`.
- **Refused correctly:** `ATATT…`, `ghp_…`, `sk-ant-…`, `password: …`, `xoxb-…` and OpenSSH private-key headers.
- **Partial leak:** the refusal message prints the first 12 characters of the secret (`ATATT3xFfGF0...`).

**To resolve:** add these patterns and print only the pattern name.

**I1-m3. Duplicate check fails for multi-line entries** (`ticket_page.py:144-146,170-173`). `entry_line` joins a
multi-line entry with `"\n  "` and compares it as one string, but `parse_sections` returns the page line by line, so
the comparison never matches. Rendering the same two-line Validation entry twice gave two copies (`Validation: 3`
lines in `m2.md`). `validate` asks for multi-line entries (the report block, verbatim failures). The version-jump
re-render in step 4 is exactly the path where this happens. **To resolve:** compare whole entries (a bullet plus its
continuation lines) after normalisation.

**I1-m4. The version-jump "recovery" doesn't recover anything** (SKILL.md step 4).
- **Why.** When the version comes back more than one higher, the other writer's entries were overwritten by this
  write:
  - re-reading the page returns this agent's own body;
  - the other writer has already cleared its outbox.

  The prescribed re-read, render and update therefore restores nothing. The entries survive only in Confluence's page
  history.
- **To resolve:** read the overwritten version, if the MCP tool allows it, or log a "possible lost entries,
  versions N..M" Findings entry for a person to check. Don't claim a recovery that doesn't happen.

**I1-m5. Two parallel sibling tickets can create two containers, and the lookups don't page** (SKILL.md step 2.5 and
step 4)
- **Duplicate containers.** Two sibling tickets in `plan-feature` at the same time can both find no
  `Ticket plans: <EPIC>` and both create one. There is a rule for two ticket pages but not for two containers.
- **Paging.** `getConfluencePageDescendants` is used with no paging. If an epic's container has more children than
  the tool returns per call (default not verified), the lookup by title can miss an existing page.
- **To resolve:** re-check after creating, add a two-containers rule (stop and report), and follow paging or use an
  exact-title CQL search.

**I1-m6. Flag wording**
- `execute` and `plan-feature` add `--dry-run` to their argument hints but their bodies never say it applies only to
  the ticket record. For `execute`, it reads like "don't write code".
- `implement-fix`'s argument-hint doesn't mention `--no-tracker`.
- `end-to-end-feature` doesn't say to pass `--no-tracker` to a handed-off loop runner or to sub-agents.
- "Stop and ask" in step 2 has no rule for unattended runs. Suggested: report and skip.

**I1-m7. The plan commit on a new page is stale from the start, and a failed fallback `publish` is never retried**
(SKILL.md step 6; "Jira fallback")
- **The page lags.** `publish` renders the page from commit X, then step 6 commits the `**Ticket page**` line (commit
  Y). The header keeps citing X until the next `publish`. For a ticket with no later revision, `close-epic`'s "matches
  the branch's plan" check will flag a difference that is only that line.
- **The fallback plan comment can be lost.** If the fallback `publish` fails, the `**Ticket page**: none` line is
  never written. Later `log` calls post their comments, but nothing re-posts the plan comment, so the "retried by the
  next step's call" promise doesn't hold for the fallback.

**I1-m8. Smaller consistency points**
- `implement-fix`'s `allowed-tools` doesn't pre-approve `Bash(uv:*)` or `mcp__atlassian__*`. This is not blocking
  under `defaultMode: auto`.
- `render` with a `meta.json` missing a key crashes with a traceback and exit 1, which clashes with the documented
  "1 = refused".
- An unattended escalation in the fallback posts two Jira comments: the existing one and the new PIV one.
- CLAUDE.md's "each step updates its record" overstates: standalone `code-review` and `commit` don't log.

**I1-m9. The live AIUE-61 page carries test leftovers and one embellished Owner entry.** This is page content, not a
defect on the branch.
- **Test leftovers.** Version 3 has the Progress entry "Page created by the ticket-pages skill test…", "Last updated
  … by ticket-page (skill test)", and status "Implementation review" set by the test.
- **Embellished entry.** The Q2 entry says "user-editable through a documented `ppp` variable". The cited source
  (`6abd6b4:docs/specs/AIUE-8-progress.md:185-189`) says only "Q2 default 64 chunks, user-editable". An entry marked
  Owner should not add to its source.
- **To resolve:** fix or annotate the entry at the next update.

## Status of previous findings

Round 1: none.

## Not independently verified (environment)

- **Live page and comment content.** I have no Atlassian MCP in this session, so I couldn't read page 2293761
  (version 3), container 2260993 or Jira comment 10031 as stored. What I checked instead, from
  `UEDGE_v9_dev/logs/post_tool_use.jsonl`:
  - the logged `getConfluencePage` response for version 2 (line 6454): header, five `##` sections, attribution line,
    no `/Users`, `/private`, `/tmp`, `/var/folders` or user name, placeholders only;
  - the version 3 update input and response (line 6489: version 3, one Progress entry added) and the input equal to
    `body3.md`;
  - the create (lines 6442/6446) and descendants (line 6453: exactly one `Plan: AIUE-61 - ` child) responses;
  - the `addCommentToJiraIssue` request and response (line 6451, id 10031).

  These are the agent's own logged calls. They show what was sent and returned then, not the current stored state.
- **Confluence API behaviour.** The default page size of `getConfluencePageDescendants`, whether Confluence Cloud
  refuses duplicate titles in a space, and the largest `body` `updateConfluencePage` accepts (48.5 KB worked) were not
  checked. A web lookup was unavailable.
- **AIUE-58 fallback dry run.** I checked it only from its saved texts (`${TMPDIR}/ticket-page/AIUE-58/`); no
  Atlassian reads were possible.

## What was checked and how

- **Diff and checks.** I read the whole diff (`git diff 4faed39..HEAD`): the new `ticket-page` SKILL.md and
  `ticket_page.py`, and the wiring in eight skills and CLAUDE.md. Branch checks:
  - `uv run .claude/hooks/change_kind.py --range 4faed39..HEAD`: all 11 files are `process` on an `ai` branch, "OK";
  - `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` (and `--changed 4faed39`): "OK", exit 0;
  - no cross-reference to `close-epic` step numbers or `plan-feature` phase numbers is broken by the renumbering.
- **MCP tool names.** Every name the skill uses (`getAccessibleAtlassianResources`, `getJiraIssue`,
  `searchConfluenceUsingCql`, `getConfluencePageDescendants`, `getConfluencePage`, `createConfluencePage`,
  `updateConfluencePage`, `addCommentToJiraIssue`, `getConfluencePageFooterComments`/`InlineComments`) appears as an
  `mcp__atlassian__*` call in this environment's tool log.
- **Overreach.** There is no `transitionJiraIssue` or `editJiraIssue` and no description edit in `ticket-page`. The
  only repo write is the plan's `**Ticket page**` line. `.claude/plans/` is `artifact` in `change_kind.py:45`, so that
  commit is allowed on a ticket branch.
- **Helper, run on test inputs** (scratch `/tmp/revtp`, an empty `--outbox`; no writes to any real worktree's git
  directory or to Atlassian):
  - `sanitize` on 15 path cases and 20 secret cases (results above);
  - `render` against the logged version 2 page:
    - the same entries on the same date add no duplicates (`Reviews: 3, Findings: 6`);
    - a different date does add them;
    - multi-line entries are duplicated;
    - a fenced `## Plan` inside an entry is handled;
    - the content-array and storage-body `--current` forms each erased the log, with exit 0;
  - error paths: a missing plan path gives exit 2; a missing meta key gives a traceback.
- **Outbox** (`queue`, tested in a throwaway repo `/tmp/revtp/g2` with a linked worktree):
  - entries go to `.git/worktrees/<wt>/ticket-page-outbox/` and `.git/ticket-page-outbox/`, one per worktree;
  - `git status` stays clean, so the outbox can't be committed;
  - `git worktree remove` deletes it.
- **Plan mirror.** I compared the plan section of the version 3 update with
  `sanitize(demote(git show 604a667:.claude/plans/AIUE-61-omp-static-partition.md))`: identical, 44,958 characters.
- **Owner source.** I checked the D1–Q6 Owner entries against `git show 6abd6b4:docs/specs/AIUE-8-progress.md` lines
  183-190 (supported, except the Q2 wording, I1-m9).
- **Plan sizes.** Across the ticket worktrees, plans are up to 49.7 KB (`wc -c`).
