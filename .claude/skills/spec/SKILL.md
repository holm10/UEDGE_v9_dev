---
name: spec
description: Slice an epic or next-epic doc into PIV-sized tickets with a dependency graph. Turns a large strategic doc into the discrete units of work that the PIV loop consumes. Accepts a Confluence page id, a local PRD/epic doc path, OR just a Jira epic key (the PRD page published by create-prd is looked up automatically); optionally cross-references a Jira epic key. Writes the breakdown to docs/specs/ and, when the input was a Confluence page, publishes it back as a child page of the PRD. When a Jira epic key is passed, it also creates the tickets as issues under that epic, skipping any that already exist, and creates each ticket's page (its PIV record for the whole lifecycle) under "Ticket plans <EPIC>" below the PRD, or a short "PIV record" Jira comment when the epic has no PRD page. --pages-only creates the missing pages for an epic that is already sliced.
argument-hint: "[jira-epic-key OR confluence-page-id OR local-doc-path] [optional-jira-epic-key] [--pages-only] [--no-tracker] [--tracker-dry-run]"
---

# /spec — Slice an Epic into PIV-Sized Tickets

The bridge between a strategic doc and the PIV loop. The epic doc is the destination; the PIV loop is the unit of motion; **tickets are the bridge.** `/spec` does the slicing.

## Recommended two-session PM flow

**Session 1 — Draft the PRD.**
The PM works with the agent to write or refine the PRD: goals, user stories, acceptance criteria, out-of-scope. At the end of the session, run `/create-prd <EPIC-KEY>`. It publishes the PRD to Confluence as `PRD: <EPIC-KEY> - <summary>`, links it from the epic, and prints the page id to use here. Keeping this separate from slicing avoids a bloated context window and lets the PRD stabilize before it is decomposed.

**Session 2 — Run `/spec`.**
With a primed session, run `/spec <EPIC-KEY>` (or pass the Confluence page id or a local file path) to decompose the PRD into tickets. The PRD is the source of truth; the agent does not re-draft it here.

> **Why two sessions?** PRD drafting and ticket decomposition are cognitively different tasks. Mixing them in one long session inflates the context window, often causes the agent to start slicing before requirements are settled, and makes it harder to review the PRD independently. The boundary also mirrors a real PM workflow.

## Input

- `$1` — one of:
  - a **Jira epic key** (e.g. `AIUE-5`). The PRD page that `/create-prd` published for it is looked up in Confluence.
  - a **Confluence page id** (numeric, e.g. `123456`).
  - a **local file path** to the epic doc, next-epic doc (brownfield), or PRD (greenfield).
- `$2` *(optional)* — a **Jira epic key** (e.g. `PROJ-42`) to cross-reference. If provided, fetch the epic and include its summary, description, and child issues as additional context alongside the PRD.

Detect `$1` in this order:

1. All digits → Confluence page id.
2. An existing file → local file path.
3. Matches `^[A-Za-z][A-Za-z0-9]*-?[0-9]+$` → Jira epic key. Normalize it to upper case with a hyphen before
   the number (`AIUE5` → `AIUE-5`). This key is also the epic key for Steps 1 and 6. If `$2` is also given and
   differs, stop and ask which one is meant.
4. Anything else → treat as a local file path. If it does not exist, stop and say so.

Below, **the epic key** means the key from `$1` (case 3) or `$2`, whichever was given.

Flags (anywhere in the arguments):
- `--pages-only`: the epic is already sliced and filed. Skip Steps 2-5 and the issue creation in Step 6; read the
  committed breakdown on the planning branch and run Step 6b (ticket pages) for every child of the epic. Use it to
  give an existing epic's tickets their pages, or after a run whose page step failed partway. Here an epic with no
  PRD page is not a stop (Step 1): Step 6b uses the Jira fallback. Without a committed breakdown, each ticket's scope
  comes from its Jira description.
- `--no-tracker`: no ticket pages and no `PIV record` comments (Step 6b is skipped; say so).
- `--tracker-dry-run`: Step 6b only reads and prints what it would create (`ticket-page --dry-run`); the breakdown,
  the issues and everything else run as usual unless `--pages-only` is also given, which makes the whole run
  read-only.
- A primed session — `/prime` should already have loaded the relevant codebase surface.

## Process

### Step 1 — Load the PRD (source of truth)

The PRD is the source of truth for this entire decomposition. Load it before doing anything else.

**If `$1` is numeric (Confluence page id):**

1. Call `mcp__atlassian__getAccessibleAtlassianResources` to obtain the `cloudId`.
2. Call `mcp__atlassian__getConfluencePage` with that `cloudId`, the page id, and `contentFormat: "markdown"`.
3. Use the returned page content as the PRD.

**If `$1` is a Jira epic key:** find the PRD page, then load it as for a page id.

1. Obtain the `cloudId` via `mcp__atlassian__getAccessibleAtlassianResources`.
2. Search Confluence with `mcp__atlassian__searchConfluenceUsingCql` for
   `type = page AND title ~ "PRD: <EPIC-KEY>"`. Keep only pages whose title is exactly `PRD: <EPIC-KEY>` or
   starts with `PRD: <EPIC-KEY> - `, so that `AIUE-5` does not match `AIUE-50`.
3. If no page matches, read the epic's comments (`mcp__atlassian__getJiraIssue` with `fields: ["comment"]`).
   Look for the `PRD: ... (Confluence page id ...)` comment that `/create-prd` posts, and use that page id.
4. Then:
   - **One page found:** say which page you are using (title, id, URL) and continue with it as the page id.
   - **Several pages found:** list them and ask the user which one to use.
   - **No page found:** stop. Tell the user to run `/create-prd <EPIC-KEY>` first, or to pass a page id or a
     file path. Do not slice the bare Jira epic, because its description is not a PRD.

**If `$1` is a file path:**

Read the file directly. Use its contents as the PRD.

**If an epic key is known (from `$1` or `$2`):**

1. Obtain the `cloudId` via `mcp__atlassian__getAccessibleAtlassianResources` if not already fetched.
2. Call `mcp__atlassian__getJiraIssue` with that `cloudId`, the epic key, and `responseContentFormat: "markdown"`.
3. Treat the returned issue (summary, description, child issues) as supplementary context. If the Jira epic and the PRD conflict, the PRD wins.

Read the loaded PRD fully: the goal, user stories, architectural impact, acceptance criteria, out-of-scope.

### Step 2 — Decompose into PIV-sized slices

Break the epic into tickets. A well-sized ticket:

- Maps to **one structured plan** of 500-700 lines.
- Is one coherent unit — a vertical slice of behavior, not a horizontal layer.
- Has clear acceptance criteria of its own.
- Is small enough to execute in a single PIV loop (roughly 20-60 minutes of execute time).

If a slice would produce a plan longer than ~700 lines, split it further.

### Step 3 — Slice for parallelizability

Map dependencies between tickets. **Independent tickets** — ones that don't touch the same files or rely on each other's output — can run in **parallel** (separate branches/worktrees, each with its own Python env since UEDGE installs compiled modules). Mark which tickets are independent and which form a dependency chain. Slicing along package and equation boundaries (`bbb/pandf_*` files, `.v` groups, `src/uedge/` modules) maximizes independence; tickets that both touch `bbb/bbb.v` or the `pandf` tree usually conflict.

### Step 4 — Write the ticket breakdown

Write to `docs/specs/<epic-slug>.md`:

```
# Spec: <epic name>

## Epic summary — goal in 2-3 lines
## Tickets
   ### TICKET-1 — <title> · `<KEY>` (fill in the key after Step 6)
   - Scope / acceptance criteria
   - Files touched (estimate)
   - Depends on: <none / TICKET-x>
   - Branch: `feature/v9-<KEY>-<slug>` (fill in the key after Step 6) · base: `v9-develop` | `<parent ticket branch>` (stacked)
   - Ticket page: Confluence page <id> (<url>) (filled in by Step 6b) | none (no epic PRD page); PIV record in Jira comments on <KEY>
   ### TICKET-2 — ...
## Dependency graph
   <text or mermaid graph showing the order + parallel groups>
## Suggested execution order
   Wave 1 (parallel): TICKET-1, TICKET-3
   Wave 2: TICKET-2 (after TICKET-1)
## Integration
   Ticket PRs target `v9-develop` | `feature/v9-<EPIC>-integration` (only if tickets can't land one by one; say why)
```

Branches follow `.claude/context/branching.md`: **one branch and worktree per ticket**, never one branch for a whole
epic by default. If a ticket would need AI-layer process changes (skills, agents, hooks), split those into a separate
`feature/v9-ai-<slug>` ticket. Updates that keep `CLAUDE.md`/`.claude/context/` factually correct stay inside the ticket
that changes those facts.

Write the breakdown on the epic's planning branch `feature/v9-<EPIC>-planning` (create it if needed). It sits next to
the PRD copy and its review reports.

### Step 5 — Publish the breakdown back to Confluence

The breakdown is a PM artifact, so it belongs where the PM works, not only in the repo. If the PRD came from
Confluence (i.e. `$1` was a page id, or an epic key that resolved to a PRD page), publish the breakdown as a
**child page of the PRD**:

1. Obtain the `cloudId` via `mcp__atlassian__getAccessibleAtlassianResources` if not already fetched.
2. Look for an existing page titled `Spec: <epic name> - Ticket Breakdown` in the same space
   (`mcp__atlassian__searchConfluenceUsingCql`, scoped to the space key).
3. If none exists, call `mcp__atlassian__createConfluencePage` with:
   - `cloudId`, the PRD's `spaceId`
   - `parentId` = the PRD page id (so it nests under the PRD)
   - `title` = `Spec: <epic name> - Ticket Breakdown`
   - `body` = the same markdown you wrote in Step 4
   If one already exists, call `mcp__atlassian__updateConfluencePage` instead, incrementing its version.
4. Report the resulting page id and URL back to the user.

If `$1` was a local file path rather than a Confluence page id, **skip this step** and say so. Do not invent a
space to publish into.

> Publishing is additive. The repo copy at `docs/specs/<epic-slug>.md` stays the source the PIV loop reads;
> the Confluence page is the shareable view for people who do not live in the repo.

### Step 6 — File the tickets in Jira

**If an epic key is known (from `$1` or `$2`), this step is REQUIRED.** A breakdown nobody can assign is only half
the job. Create the tickets for real:

1. Get the `cloudId` via `mcp__atlassian__getAccessibleAtlassianResources` if not already fetched.
2. Read the epic with `mcp__atlassian__getJiraIssue` to learn its `project` key and confirm it exists.
3. **Check for existing children first.** Run `mcp__atlassian__searchJiraIssuesUsingJql` with
   `parent = <epic-key>`. For every ticket in your breakdown, compare against those summaries.
   - If a child already covers that slice, **skip it** and report it as already existing.
   - Only create the slices that are genuinely missing. Never create a near-duplicate of an existing child.
4. For each missing slice call `mcp__atlassian__createJiraIssue` with:
   - `cloudId`, `projectKey` (from step 2), `issueTypeName: "Story"` (or `"Task"` for pure chores)
   - `parent_epic`/`parent` = the epic key
   - `summary` = the ticket title from your breakdown
   - `description` = scope, acceptance criteria, files likely touched, the `Depends on:` line, and the `Branch:`
     line with the real key filled in (`feature/v9-<NEW-KEY>-<slug>`)
   After creating the issues, put the real keys into `docs/specs/<epic-slug>.md` (each ticket heading's
   `` `<KEY>` `` and its `Branch:` line) and commit it on the planning branch, so Step 6b can find each entry by key.
5. Run **Step 6b** for every ticket created here and every existing child that has no page yet.
6. Update the breakdown's Confluence page (Step 5) **once**, with the keys and the `Ticket page:` lines.
7. Report a table of the tickets: key, summary, URL, created or already present, and the ticket page (created,
   already present, or the Jira `PIV record` comment), plus anything that failed.

If no epic key is known, skip this step and tell the user which epic key to pass to file the tickets.

### Step 6b — Create each ticket's page (its PIV record)

Every ticket gets **one** record for its whole life, created here, and every later skill writes to it: `plan-feature`
(or `implement-fix`) mirrors the plan (or RCA) into it, `execute`, `validate` and the review gates log to it, the
commit closes it (`.claude/skills/ticket-page/SKILL.md`). Run `ticket-page <KEY> create` for each ticket, with these
inputs (pass `--dry-run` for `--tracker-dry-run`; `--no-tracker` skips the step):

1. **Where.** The PRD page from Step 1 (an epic key or page id), else look it up as in Step 1 (a local file plus
   `$2`). The container is `Ticket plans: <EPIC>` under the PRD (CQL `type = page AND parent = <PRD id> AND title =
   "Ticket plans: <EPIC>"`); create it once if missing (`ticket-page` → "Container missing"). **No PRD page** → the
   Jira fallback: one short `**PIV record: ticket filed**` comment per ticket, with the ticket's scope, acceptance,
   dependencies, planned branch and the breakdown path (`ticket-page` → "Jira fallback", `create`).
2. **Existing pages first.** List the container's children once (CQL `type = page AND parent = <container id>`,
   following `next`) and save the result; read each ticket's comments (`getJiraIssue` with `fields: ["comment",
   "status"]`, saved). `ticket_page.py find --key <KEY> --comments <issue.json> --search <children.json>` then says,
   per ticket: one page (created by an earlier `spec` run or by `plan-feature`, same title rule) → leave it as it is
   and report it; several → report them and create nothing for that ticket; none → create it. In the fallback, a
   ticket that already has a `**PIV record` comment (`piv_record_comments` > 0) is left as it is. A child whose
   status category is Done is reported and skipped.
3. **The page.** Ticket section from the committed breakdown: `ticket_page.py ticket --repo <planning worktree>
   --key <KEY> --breakdown docs/specs/<epic-slug>.md --branch feature/v9-<EPIC>-planning --out <scratch>/<KEY>.md`;
   exit 3 (a child the breakdown doesn't list) → its Jira description (`--text`, `--source "the Jira description of
   <KEY>"`). Then the skeleton: header (ticket, epic, PRD, planned branch, status `Planned`; a child filed before this
   step: status note "page created after the ticket; Jira status <status>, earlier history in the Jira comments"),
   `## Ticket`, the empty Progress, Validation, Reviews and Findings and decisions sections, and a Plan placeholder.
   Create, verify, re-check for duplicates and post the link comment exactly as `ticket-page` → "Create" says.
4. **Record the id** where later skills find it without a worktree: the ticket's Jira link comment (`Ticket page:
   … (Confluence page id <id>)`, posted by `create`) and the ticket's entry in the breakdown (`- **Ticket page:**
   Confluence page <id> (<url>)`, or the fallback line). Commit the breakdown on the planning branch ("Records the
   <EPIC> ticket pages"). `plan-feature` later finds the page from the link comment, else by the exact-title search
   under the container, and fills it; nothing is recorded in a ticket worktree here (none exists yet).
5. A failure (Atlassian down, a refused render) never stops the run: report the ticket and the error; a re-run (or
   `--pages-only`) creates only what is still missing.

> Order matters: write the breakdown document first (Step 4), publish to Confluence (Step 5), then create
> issues, then their pages (Step 6b). If issue or page creation fails partway, the breakdown still exists and the run
> is re-runnable, because step 3 and Step 6b.2 make creation idempotent: a ticket never gets a second issue or page.

## Output

1. A ticket breakdown at `docs/specs/<epic-slug>.md` (always).
2. A Confluence child page under the PRD (when the PRD came from Confluence, either by page id or by epic key).
3. Real Jira issues under the epic, when an epic key was known (Step 6). Existing children are never duplicated.
4. One ticket page per ticket under `Ticket plans: <EPIC>` (a child of the PRD), linked from the ticket and recorded
   in the breakdown, or a `PIV record: ticket filed` Jira comment when there is no PRD page (Step 6b).

Each ticket then enters its own PIV loop starting at `/prime` → `/plan-feature`, which fills that same page with the
plan through the `ticket-page` skill; `execute`, `validate` and the review gates log to it. When the tickets are done,
`/close-epic <EPIC-KEY>` writes the close-out record and closes the epic (`--dry-run` for a read-only draft first).

## Notes

- Issue management: the course standardizes on Jira (via Atlassian MCP); GitHub Issues, Asana, and Archon's task system are equivalent — the slicing logic is the same.
- Greenfield: the same slicing applies to MVP phases instead of epic tickets.
