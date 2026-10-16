# Review: ai-ticket-pages (AI-layer change), implementation round 3

Branch `feature/v9-ai-ticket-pages`, worktree `/Users/holma/Documents/uedge/src/uedge-wt/ai-ticket-pages`, base
`4faed39`, tip `ec1b75b`. Round 2 reviewed `cbe4e7b`. Reference: the owner's request and its amendment, the design
defaults, the main-session decisions on the round-1 majors, and the round-2 report and its response.

Main-session decisions for this round:
- The `validate` batching deviation is accepted. This review checks only that it is stated consistently.
- The live `commentId` update stays untested. This review checks that its fallback is safe.

## Verdict

**APPROVE**

## Summary

The round-2 BLOCKER is fixed:
- `render --new-page` fills a page just created with the stub.
- It accepts only the stub for the page's own key, in any of the accepted forms.
- It is refused once a version is recorded, and every other refusal still applies.

I checked this with the new selftest (41/41, and every refusal fails for its intended reason, not an argparse error),
with my round-2 inputs, and with 11 further attempts to break it. The minors are all resolved except I2-m5, which is
partly resolved. Its fallback is safe in the failure mode that has been reported.

`render --local --page-version 4` for AIUE-61 rebuilds a body equal to the version-4 body in the hook log, byte for
byte. The `validate` batching is described the same way in all six places that mention it.

I found no new BLOCKER or MAJOR. There are three new minors, all optional:
- the retry path and the recreated-page path aren't routed to `--new-page`;
- the second-failure bound of the running summary isn't enforced;
- bare root tokens are masked.

## Findings

### BLOCKER

None.

### MAJOR

None.

### MINOR

**I3-m1. A stub or recreated page that needs `--new-page` isn't routed to it** (`ticket_page.py` `cmd_render`;
`SKILL.md:100-108,112-118,148-158`)
- **Retry after a failed first fill.** "Page missing" step 4 says the next flush "repeats step 3". The general flow
  (step 3.1) says something else: read the page and pass `--current`. If the agent follows step 3.1, the stub is
  refused with "--current lacks the log section heading(s) … (a truncated copy?)". That message doesn't mention
  `--new-page`. It writes nothing, so it is safe, but an agent that follows step 3 literally keeps the entries queued
  at every flush (the I2-B1 symptom, now only on the retry path).
- **Recreated page.** A page deleted and created again under a new id is refused for good, with "this worktree
  already wrote version 3". `state.version` belongs to the old page, and nothing ties it to `state.page_id`. In my
  test the only way out, `state --set version=`, isn't documented.
- **Small wording slip.** The render command in step 3.3 shows `(--local | --current <file>)` without `--page-version`
  or `--new-page`. The helper refuses with a clear message.
- **What would resolve it.** Either:
  - when `--current` is exactly the stub and no version is recorded, have the helper's refusal say "use
    `--new-page`", and have step 3.1 say so; and
  - clear `version` when `page_id` changes, or compare `state.page_id` with `meta.page_id`.

**I3-m2. The running-summary bound of 9 isn't enforced when an update posts a new comment instead** (`SKILL.md:213-221`)
- **Safe case: the update fails with an error.** This is the reported failure: community post, log line 4174. The
  skill:
  - posts one "Supersedes comment <id>." comment (the 9th);
  - after a second failure, posts nothing more.

  Later milestones only make failing calls, so the bound of 9 holds and nothing already sent is lost. Later
  milestones don't reach Jira, and that is reported. This is safe.
- **Case not covered: the update returns another id**, meaning the call created a comment.
  - The skill posts the Supersedes comment as well, so the summary appears twice.
  - `fallback_superseded=1` doesn't stop later calls. In the same mode, each later milestone's update attempt adds
    another comment before the skill can "post nothing more".
  - The count can therefore pass 9, by at most one short comment per remaining milestone.
- **What would resolve it.**
  - When a different id comes back, adopt that comment as the new summary instead of posting another.
  - After the second failure, set a flag that stops further update calls.

**I3-m3. The new short roots also mask bare words** (`ticket_page.py:76-78`)
- **What happens.** The look-ahead `(?=/|\b)` and the optional tail let a lone `/p`, `/g`, `/global`, `/data-set`,
  `/project-x` or `/p.value` match. Each becomes `{local}` (for example "the /p option" → "the {local} option"). The
  sanitiser also runs on the plan mirror, so such words would differ from the repo file.
- **How much it matters.** Comparing the old and new helpers on 609 real plans, RCAs, reviews and docs, only 4 files
  change. Every change is an intended path (`file:///Users/…`, `/work/venv-fix/…`, and the round-2 response's own
  examples). There are no false positives. URLs, repo-relative paths, `s/x/y/g`, `1/g`, `and/or`, `refs/heads/…`,
  `/usr/local/…`, `/etc/…` and `/dev/null` are all left alone.
- **What would resolve it.** For the generic roots (`p`, `g`, `data`, `work`, `global`, `project(s)`, `nfs`), require
  a following `/segment`.

## Status of previous findings

| Finding | Status | Evidence (checked myself) |
|---|---|---|
| **I2-B1** stub page can't be filled | **Resolved** | See the "I2-B1 evidence" list below the table. |
| **I2-m1** partial headings; `#` lines | **Resolved** | See the "I2-m1 evidence" list below the table. |
| **I2-m2** `--local` unchecked | **Resolved** | Selftest B1 and B2 fail for the right reasons: "--local needs --page-version N" and "page is at version 3, but this worktree last wrote version 2". On the AIUE-61 store, `--page-version 3` → exit 2 and `--page-version 4` → exit 0. |
| **I2-m3** cost; `validate` milestone | **Resolved** | The cost text (`SKILL.md:51-58`) counts output and input, about 28k of context per flush and 140k per 5-flush session, plus the read-back. The deviation is stated in `SKILL.md:45-49` and accepted by the main session. It is described consistently in the milestone row (`:39`), the end-of-execute row (`:38`), `validate/SKILL.md:103-108`, `execute/SKILL.md:57-60`, `implement-fix/SKILL.md:63-65` and `end-to-end-feature/SKILL.md:22-26`. None of them still says "each validate" flushes. |
| **I2-m4** `validate` key; dry run | **Resolved** | `validate` takes `--ticket <KEY>`, then the branch name, then the plan or RCA. `execute`, `implement-fix` and `end-to-end-feature` pass `--ticket`. `validate` accepts `--tracker-dry-run`, passed on as `--dry-run`, so nothing is queued. |
| **I2-m5** running-summary update | **Partially resolved** | The returned-id check and the single "Supersedes" fallback were added. Safe when the update errors, as reported. The case where an update posts a new comment remains: see I3-m2 (minor). The `commentId` path itself is still unexercised (see below). |
| **I2-m6** verify after a failed update; retry | **Resolved** | See the "I2-m6 evidence" list below the table. |
| **I2-m7** cluster paths, `file://` | **Resolved** | Masked: `/scratch`, `/p/lustre1`, `/gpfs/u`, `/global/homes`, `/g/g19`, `/usr/workspace`, `/usr/WS1` and `file:///Users/…`. `file:///etc/x` is left alone, as the skill now says. New over-match: see I3-m3 (minor, no real hits). |

**I2-B1 evidence.**
- Selftest:
  - A2: a stub without `--new-page` is refused (lacks headings).
  - A3: a non-stub page with `--new-page` is refused.
  - A4: the wrapped stub with `--new-page` gives exit 0, and the header cites the commit that added the
    `**Ticket page**` line.
  - A5: verify with `--after-version 1` passes.
  - A6: `--new-page` is refused after `version=2` is recorded.
- My round-2 inputs (copy of `/tmp/rev2tp`):
  - the stub, plain and MCP-wrapped (with `"version":{"number":1}`), with `--new-page` → exit 0;
  - the stub with extra blank lines and spaces, and the stub in italics → exit 0, the same body (sha
    `fa772dbbb39d0067`).
- Refused:
  - the stub plus an injected `## Progress` entry;
  - the stub of another key (AIUE-98);
  - an HTML-wrapped stub;
  - an empty page;
  - the full v2 page with `--new-page`;
  - `--new-page` without `page_id`;
  - `--new-page --local` (version mismatch).

**I2-m1 evidence.**
- Refused (exit 2), each naming the missing headings: `b1_partial.md`, `noheads.md`, `err.json`, and selftest B6.
- `h1_rt.md` keeps `# ran: pytest -k D_only` (exit 0, counts 4/7 unchanged).
- New entries escape the line as `\#` (B3).
- The fewer-entries check is B9: refused, then accepted with `--allow-fewer`.

**I2-m6 evidence.**
- Selftest:
  - C1: no logged update after version 3 → exit 3 "not logged as successful", not a mismatch;
  - C2: the mismatch is detected;
  - C3: the retry is verified with `--after-version` 4 → version 5.
- The skill (`:161-177`) allows one retry and stops after a second mismatch. Its "another writer" count includes this
  flush's own retry.

## Not independently verified (environment)

- **The live `commentId` in-place update.** It has never been run. All I checked is that the fallback is safe in the
  reported failure mode (I3-m2). What would verify it: one `addCommentToJiraIssue` call with `commentId` on a test
  comment, before relying on the running summary.
- **Live Atlassian state.** I have no Atlassian MCP. I checked AIUE-61 version 4 only against the update call logged
  at `logs/post_tool_use.jsonl` line 6665. That shows what was sent and returned then, not what is stored now.
- **The Confluence markdown round trip of `\#` and of entries with several lines.** The selftest simulates it. The
  logged page reads (lines 4058, 4238, 6454) show that nested list items come back indented by 4 spaces. So the
  helper's own pessimistic model (indents dropped) is stricter than what was seen. Under that model, an entry with
  sub-bullets would be duplicated on every flush (my test `t2.sh`). That code didn't change this round, and real
  exports don't drop nested-list indents, so I don't raise it as a finding.
- **The first fill against a real stub page** (create → read → `--new-page` → update). It is exercised only with a
  simulated read and log.

## What was checked and how

- **Diff.** I read `git diff cbe4e7b..ec1b75b` in full: `ticket_page.py`, the ticket-page `SKILL.md`, the new
  `selftest.sh`, `validate`, `execute`, `implement-fix`, `end-to-end-feature` and `CLAUDE.md`. I also re-read the
  whole current SKILL.md, plus `cmd_verify`, `parse_sections`, `entry_blocks`, `load_current` and the sanitiser.
- **Selftest.**
  - `selftest.sh /tmp/rev3tp/st1`: 41 passed, 0 failed.
  - A copy with `2>/dev/null` changed to `2>&1`: every expected exit 2 or 3 carries the intended helper message, and
    none is an argparse usage error.
  - `selftest.sh` and `ticket_page.py` are committed with mode 100755.
- **Breaking `--new-page`** (`/tmp/rev3tp/t1.sh`): the 11 variants above, plus the round-2 refusal inputs (partial,
  no headings, storage, `err.json`, no body, the full v2 page, `h1_rt`).
- **Recreated page** (`t6.sh`): `--new-page` is refused while `version` belongs to the old page id. It works only
  after `state --set version=` (I3-m1).
- **AIUE-61 version 4** (`t3.sh`): on a copy of the author's store in `$TMPDIR/ticket-page/AIUE-61-fix/store`
  (`version` "4"), `render --repo <AIUE-61 worktree> --plan-rev ad5819b --local --page-version 4` gave 49,028 chars.
  This is exactly equal (`==`, and `==` after `rstrip`) to the `body` of the `updateConfluencePage` call at log line
  6665, which returned version 4. `--page-version 3` → exit 2.
- **Sanitiser.**
  - 33 handcrafted cases (`t4.py`).
  - Old (`cbe4e7b`) and new helpers compared on 609 real documents (`t5.py`): only 4 changed, all intended.
- **Fallback for `commentId`.** I read `SKILL.md:213-221` against the community report (log line 4174: the reported
  failure is an error caused by required visibility, not a silent new comment) and the schema description quoted at
  line 4276.
- **Branch checks, from the worktree.**
  - `uv run .claude/hooks/change_kind.py --range 4faed39..HEAD`: 12 files, all `process` on an `ai` branch, "OK",
    exit 0.
  - `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`: lists the cross-references, "OK",
    exit 0.
  - The worktree is clean, the tip is `ec1b75b` and `origin/v9-develop` is `4faed39`.
- **What I didn't touch.** No Atlassian calls, no commits and no UEDGE runs. All helper runs used scratch under
  `/tmp/rev3tp`, with `--outbox` there; I didn't write to any real worktree's store.
