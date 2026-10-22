---
name: spec
description: Slice an epic or next-epic doc into PIV-sized tickets with a dependency graph. Turns a large strategic doc into the discrete units of work that the PIV loop consumes. Accepts a Confluence page id, a local PRD/epic doc path, OR just a Jira epic key (the PRD page published by create-prd is looked up automatically); optionally cross-references a Jira epic key. Writes the breakdown as a local working copy (never committed) and publishes it as a child page of the PRD, which is its lasting home. When a Jira epic key is passed, it also creates the tickets as issues under that epic, skipping any that already exist, and creates each ticket's page (its PIV record for the whole lifecycle) under "Ticket plans <EPIC>" below the PRD, or a short "PIV record" Jira comment when the epic has no PRD page. --pages-only creates the missing pages for an epic that is already sliced.
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
  breakdown page (`Spec: <epic name> - Ticket Breakdown` under the PRD, `getConfluencePage` in markdown, saved) and
  run Step 6b (ticket pages) for every child of the epic. Use it to give an existing epic's tickets their pages, or
  after a run whose page step failed partway. Here an epic with no PRD page is not a stop (Step 1): Step 6b uses the
  Jira fallback. Without a breakdown page, each ticket's scope comes from its Jira description. It never republishes
  the breakdown page (Step 6.6 is skipped): the page ids are recorded in the Jira link comments only, which is where
  `ticket-page` finds them.
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

- Maps to **one plan** within its tier's budget (`.claude/context/process-tiers.md`): S ≤150 lines, M ≤300, L ≤300
  (up to 500 with a reason).
- Is one coherent unit — a vertical slice of behavior, not a horizontal layer.
- Has clear acceptance criteria of its own.
- Is small enough to execute in a single PIV loop (roughly 20-60 minutes of execute time).

If a slice would need a longer plan, split it. **Don't over-slice:** every ticket pays a fixed process cost (branch,
worktree, venv, plan, page, review, PR), so merge small investigation, characterisation and doc/tooling slices that
touch the same area into one S ticket instead of filing several tiny ones.

**Assign a tier to every ticket** (S, M or L, as defined in `.claude/context/process-tiers.md`) from what it touches,
not from its estimated effort: anything in the `pandf` tree, Jacobian/preconditioner code, `ppp/`, a `.v` file, the
build, or new physics is L.

### Step 3 — Slice for parallelizability

Map dependencies between tickets. **Independent tickets** — ones that don't touch the same files or rely on each other's output — can run in **parallel** (separate branches/worktrees, each with its own Python env since UEDGE installs compiled modules). Mark which tickets are independent and which form a dependency chain. Slicing along package and equation boundaries (`bbb/pandf_*` files, `.v` groups, `src/uedge/` modules) maximizes independence; tickets that both touch `bbb/bbb.v` or the `pandf` tree usually conflict. So do tickets that extend the same shared entry point in test or tooling code (a harness's runner and its configuration list, e.g. `tests/yldot/harness/process.py` and `state.py`) or rewrite the same paragraph of a context module: list such modified files under each ticket's Files touched, not only the new ones, and if those tickets still share a wave, give the wave a merge order (the second to merge rebases and re-runs its tests). Parallel is a means, not a goal: a wave runs in parallel only where that shortens the critical path, with at most about 3 tickets (background agents) at once (`.claude/context/process-tiers.md` → Session SOP).

### Step 4 — Write the ticket breakdown

Write the working copy to `.claude/work/<EPIC>/breakdown.md` in the current checkout (`.claude/work/<epic-slug>/`
without an epic key):

```
# Spec: <epic name>

## Epic summary — goal in 2-3 lines
## Tickets
   ### TICKET-1 — <title> · `<KEY>` (fill in the key after Step 6)
   - Tier: S | M | L (why, in a few words)
   - Scope / acceptance criteria
   - Files touched (estimate: new and modified files, including shared harness files and the context-module paragraph it updates)
   - Depends on: <none / TICKET-x>
   - Branch: `feature/v9-<KEY>-<slug>` (fill in the key after Step 6) · base: `v9-develop` | `<parent ticket branch>` (stacked)
   - **Ticket page:** Confluence page <id> (<url>) (filled in by Step 6b) | none (no epic PRD page); PIV record in Jira comments on <KEY>
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
that changes those facts. Tickets that run in parallel (a wave above) each get their own **explicit** worktree
(`git worktree add -b <branch> ../uedge-wt/<KEY> <base>`), also when subagents run them; never the Agent tool's
`isolation: "worktree"`, which is removed automatically with the ticket's working folder and unsent record
(`branching.md` → Worktrees). Each such subagent flushes its ticket page before it returns.

The working copy is gitignored and never committed, on any branch (there is no planning branch,
`.claude/context/branching.md`). Its lasting home is the breakdown page (Step 5), which later skills read.

### Step 5 — Publish the breakdown back to Confluence

The breakdown page is the breakdown's only lasting copy (the local file is a working copy). If the PRD came from
Confluence (i.e. `$1` was a page id, or an epic key that resolved to a PRD page), or `$2` names an epic whose PRD page
is found as in Step 1, publish the breakdown as a **child page of the PRD**:

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
5. **The epic's progress page.** If the PRD has no child `Progress: <EPIC>` yet (CQL `type = page AND parent = <PRD
   id> AND title = "Progress: <EPIC>"`), create it: `ticket_page.py progress --new --meta <scratch>/meta.json --repo
   <checkout> --out <scratch>/progress.md` (meta: `epic`, `epic_url`, `prd_title`, `prd_url`), then
   `createConfluencePage` (PRD's `spaceId`, `parentId` = PRD id, that title, `contentFormat: "markdown"`) with the
   body exactly as rendered. Later skills append one line per ticket milestone to it through `ticket-page progress`;
   `close-epic` reads it. Skipped with `--tracker-dry-run` (shown instead) and `--no-tracker`.

If there is no PRD page, **skip this step** and say so: the breakdown then exists only as the local working copy and
is not kept (the tickets filed in Step 6 carry their scope in their Jira descriptions). Do not invent a space to
publish into.

> The page is the source the PIV loop reads (through each ticket page's Ticket section, and `plan-feature`); the
> local working copy is only a draft of what was published.

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
   After creating the issues, put the real keys into the working copy (each ticket heading's `` `<KEY>` `` and its
   `Branch:` line), so Step 6b can find each entry by key; Step 6.6 publishes them.
5. Run **Step 6b** for every ticket created here and every existing child that has no page yet.
6. Update the breakdown's Confluence page (Step 5) **once**, with the keys and the `Ticket page:` lines. First check
   that it hasn't moved: its `lastModified` in `getConfluencePageDescendants` of the PRD (`depth: 1`) must equal the
   `version.createdAt` Step 5's create or update returned (the CQL version check is unreliable; see `ticket-page`
   step 3.1). Otherwise someone edited it there; don't overwrite it, report it. Skipped with
   `--pages-only`.
7. Report a table of the tickets: key, summary, URL, created or already present, and the ticket page (created,
   already present, or the Jira `PIV record` comment), plus anything that failed.

If no epic key is known, skip this step and tell the user which epic key to pass to file the tickets.

### Step 6b — Create each ticket's page (its PIV record)

Every ticket gets **one** record for its whole life, created here, and every later skill writes to it: `plan-feature`
(or `implement-fix`) mirrors the plan (or RCA) into it, `execute`, `validate` and the review gates log to it, the
commit closes it (`.claude/skills/ticket-page/SKILL.md`). Run `ticket-page <KEY> create` for each ticket, with these
inputs (pass `--dry-run` for `--tracker-dry-run`; `--no-tracker` skips the step).

**Which tickets.** Every ticket created in Step 6, and every existing child of the epic whose Jira status is **To Do
or In Progress** that has no page yet. Children in **In Review, Done** or any other status are skipped and listed in
the report as "skipped (status <s>)": their work is largely recorded elsewhere, and a page made now could only say
so. (Owner decision (2026-10-16); it applies to the Jira fallback too.) A page for an
existing child is a **backfill**: it is marked as one and claims nothing about the ticket's past (step 3).

1. **Where.** The PRD page from Step 1 (an epic key or page id), else look it up as in Step 1 (a local file plus
   `$2`). The container is `Ticket plans: <EPIC>` under the PRD (CQL `type = page AND parent = <PRD id> AND title =
   "Ticket plans: <EPIC>"`); create it once if missing (`ticket-page` → "Container missing"). **No PRD page** → the
   Jira fallback: one short `PIV record` comment per ticket (`ticket-page` → "Jira fallback", `create`): `ticket
   filed` for a ticket created in this run, `record started` for a backfill.
2. **Existing records first.** List the container's children **once before the batch** (CQL `type = page AND parent =
   <container id>`, following `next`; save every page of the result). Statuses come from the children listing
   (`parent = <EPIC>`, `fields: ["summary", "status"]`). For each ticket the status rule keeps, read **all** its
   comments: `getJiraIssue` with `fields: ["comment", "status"]` and `responseContentFormat: "markdown"`, saved
   as it comes back (the helper also reads ADF bodies; a paged comment list means fetching the rest). Then
   `ticket_page.py find --key <KEY> --comments <issue.json> --search <children.json> [--search <next page>…]`:
   - exit 0: the ticket has a page (from an earlier `spec` run or from `plan-feature`; same title rule). Leave its
     body as it is and report it, but complete its records: `missing_link_comment: true` (a run that failed after the
     create, or a page `plan-feature` made before the link step) → post the link comment (`ticket-page` step 5);
     an entry in the breakdown working copy without its `**Ticket page:**` line → add it (step 4; not with
     `--pages-only`). If the output says
     `not_listed` (the page is recorded but not under this container, as for a ticket moved from another epic),
     confirm it with CQL `id = <id>`: if it exists, report "page kept under <its container>"; if it is gone, run
     `find` again with `--gone <id>`. `stale_records` follow the one rule in `ticket-page` step 2.6: the listed page
     wins; confirm each stale id once; gone → fine; still exists → two existing pages, report and write nothing.
   - exit 3: no page → create it (step 3).
   - exit 2: several pages, or `find` can't tell (no listing, an incomplete listing, comments it can't read). Report
     the ticket with the reason and create nothing for it.
   In the fallback, `find --fallback --comments <issue.json>` instead: exit 0 (a `PIV record` comment exists) →
   post nothing, but add the working copy's `**Ticket page:** none (…)` line if it is missing; 3 → post; 2 → report and
   post nothing. The status rule above applies to these repairs too.
3. **The page.**
   - Ticket section from the breakdown: `ticket_page.py ticket --repo <checkout> --key <KEY> --breakdown
     <.claude/work/<EPIC>/breakdown.md, or with --pages-only the saved breakdown page> --source "the epic breakdown
     page \`<title>\` (Confluence page <id>, <as published by this spec run | version <N> as read>)" [--backfill]
     --out <scratch>/<KEY>.md` (the working copy carries the keys Step 6.6 publishes, so name no version for it).
     Exit 3 (no entry for the key, or no breakdown page) → the Jira
     description (`--text`, `--source "the Jira description of <KEY>"`); exit 2 (several entries match) → the Jira
     description too, and report it.
   - meta: status `Planned` for a ticket created in this run; for a backfill status `Backfilled`, `backfilled` =
     today, `jira_status` = its status, `skill` `spec --pages-only` (or `spec`), and `ticket --backfill`, so the
     Ticket section says "as read on <date>", not "as filed". The skeleton then says the plan is "not mirrored here",
     not "not written yet", and carries a `**Backfilled:**` header field that `close-epic` reads.
   - Create, verify and post the link comment exactly as `ticket-page` → "Create" says, using the listing from step 2
     as its "search once more"; after the batch, list the container **once more** and report any ticket that now has
     two pages (a concurrent run).
4. **Record the id** where later skills find it without a worktree: the ticket's Jira link comment (`Ticket page:
   … (Confluence page id <id>)`, posted by `create`) and the ticket's entry in the breakdown working copy (`-
   **Ticket page:** Confluence page <id> (<url>)`, or the fallback line), which Step 6.6 publishes to the breakdown
   page (not with `--pages-only`: the link comment is then the record). Nothing is committed. `plan-feature` later
   finds the page from the link comment, else by the title search under
   the container (`title ~ "Plan: <KEY>"` filtered on the `Plan: <KEY> - ` prefix, so a renamed summary still
   matches), and fills it; nothing is recorded in a ticket worktree here (none exists yet).
5. A failure (Atlassian down, a refused render) never stops the run: report the ticket and the error; a re-run (or
   `--pages-only`) creates only what is still missing.

**Cost and prompts.** Per ticket: one `getJiraIssue` with all comments (large on a long-running ticket), the
skeleton render (local), **two writes**: the `createConfluencePage` and the link comment (`addCommentToJiraIssue`),
each through its own permission prompt, and the local verify. Per batch: the container listing before and after,
and the breakdown page update (Step 6.6). In the fallback, one write per ticket (the comment). Example: backfilling AIUE-8 with the
default status rule creates pages for its five To Do children (AIUE-48, 51, 67, 69, 71): 10 writes and prompts,
5 issue reads; the 14 In Review children are skipped (12 of them have no page). Without the rule it would have been 17 pages, 34 prompts.

> Order matters: write the breakdown document first (Step 4), publish to Confluence (Step 5), then create
> issues, then their pages (Step 6b). If issue or page creation fails partway, the breakdown still exists and the run
> is re-runnable: step 3 and Step 6b.2 skip what already exists, so a re-run never adds a second issue or page. Two
> runs at the same time can still create two pages for one ticket; the listing after the batch detects it, and it is
> reported for a person to resolve.

## Output

1. A ticket breakdown working copy at `.claude/work/<EPIC>/breakdown.md` (always; local, never committed).
2. The breakdown's Confluence child page under the PRD, its lasting home (whenever a PRD page is known).
3. Real Jira issues under the epic, when an epic key was known (Step 6). Existing children are never duplicated.
4. One ticket page per ticket under `Ticket plans: <EPIC>` (a child of the PRD), linked from the ticket and recorded
   in the breakdown, or a `PIV record` Jira comment when there is no PRD page (Step 6b), for new tickets and for
   existing To Do / In Progress children; a table of what was created, already present, and skipped (with why).

Each ticket then enters its own PIV loop starting at `/prime` → `/plan-feature`, which fills that same page with the
plan through the `ticket-page` skill; `execute`, `validate` and the review gates log to it. When the tickets are done,
`/close-epic <EPIC-KEY>` writes the close-out record and closes the epic (`--dry-run` for a read-only draft first).

## Notes

- Issue management: the course standardizes on Jira (via Atlassian MCP); GitHub Issues, Asana, and Archon's task system are equivalent — the slicing logic is the same.
- The epic's progress log is the Confluence child page `Progress: <EPIC>` (Step 5.5 creates it; dated, append-only
  lines; owner decisions attributed as in `close-epic`), never a repo file (`branching.md`). `execute`, `validate`,
  the review loop, `end-to-end-feature` and `implement-fix` append to it through `ticket-page progress`; whoever
  records an owner decision for the epic appends it the same way; `close-epic` reads it.
- Greenfield: the same slicing applies to MVP phases instead of epic tickets.
