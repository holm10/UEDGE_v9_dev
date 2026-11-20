---
name: spec
description: Slice an epic into PIV-sized tickets with a dependency graph. Turns a large strategic doc into the discrete units of work that the PIV loop consumes. Accepts a tracker epic T<E> (its epic.md, published by create-prd, is the source) or a local PRD/epic doc path (optionally followed by T<E>). Writes the breakdown as a local working copy (never committed to the public repo) and commits it as docs/T<E>-<slug>/breakdown.md in the private tracker named by .claude/tracker.toml, its lasting home. With an epic it files each ticket as a sub-issue of the epic (type, label, Project Tier and Status, "blocked by" relations), skipping any that already exist, and creates each ticket's record (ticket-page create), kept for its whole lifecycle. --records-only creates the missing records of an epic that is already sliced.
argument-hint: "[T<E> | local-doc-path [T<E>]] [--records-only] [--no-tracker] [--tracker-dry-run] [--tracker-dir <dir>]"
---

# /spec — Slice an Epic into PIV-Sized Tickets

The bridge between a strategic doc and the PIV loop. The epic doc is the destination; the PIV loop is the unit of motion; **tickets are the bridge.** `/spec` does the slicing.

The PRD comes from `/create-prd`, best in an earlier session: it publishes `epic.md`, which is the source of truth
here; this skill does not re-draft it.

## Configuration

| Setting | Value |
|---|---|
| Tracker | `.claude/tracker.toml` in the main checkout: `owner`, `repo`, `project`. Below, `<o>/<r>` is owner/repo and `<P>` the Project number; never write them out in this skill |
| Tracker checkout `<T>` | `<parent of the main checkout>/<repo>`, as `ticket-page` uses it (the main checkout is the parent of `git rev-parse --path-format=absolute --git-common-dir`). `--tracker-dir <dir>` overrides it and is passed on to every helper call |
| Epic directory | `docs/T<E>-<slug>/` in `<T>`: the existing `docs/T<E>-*/`, else `<slug>` from the epic title as `ticket-page` makes it (lower case, every run of other characters one `-`, at most 40 characters) |
| Epic documents | `epic.md` (the source), `breakdown.md` and `progress.md` in the epic directory, in the shape of the tracker's templates (`templates` directory of `<T>`) |
| Ticket records | `ticket-page` (`uv run .claude/skills/ticket-page/ticket_page.py --caller spec [--tracker-dir <dir>] <command> T<N>`): `docs/T<E>-<slug>/T<N>-<slug>/record.md` |
| Local working copy | `.claude/work/T<E>/breakdown.md` in the current checkout (`.claude/work/<epic-slug>/` without an epic); gitignored, never committed to the public repo |

**Tracker writes** (Step 5 and Step 6.8; the same rule as `ticket-page`): before writing, `git -C <T> status
--porcelain --untracked-files=no` must be empty and `git -C <T> symbolic-ref --short HEAD` the default branch
(`main`); otherwise write nothing and report the files or the branch. Then `git -C <T> pull --rebase -q` (a conflict:
`git -C <T> rebase --abort`, write nothing, report; an unreachable remote: write locally and say the push is pending),
write the files, `git -C <T> add -- <paths>`, `git -C <T> commit -q -m "T<E> spec: <what>" -- <paths>` and `git -C <T>
push -q` (a failed push is reported; the next write pushes it). One commit per milestone. A `ticket-page` call that
runs in this checkout between the write and the commit is refused (exit 2, uncommitted changes) and is simply re-run;
if these checks find a file another call is writing, wait a few seconds and check again.

**Project fields.** Read once per run: the Project id (`gh project view <P> --owner <o> --format json --jq .id`) and
the field and option ids of Status (To Do) and Tier (S, M, L) (`gh project field-list <P> --owner <o> --format
json`). An issue goes on the Project with `gh project item-add <P> --owner <o> --url <issue URL> --format json --jq
.id` (the item id; adding an issue already there returns its item), and a field is set with `gh project item-edit --id
<item id> --project-id <project id> --field-id <field id> --single-select-option-id <option id>`. Right after `gh issue
create --parent`, the Project's auto-add of the sub-issue can race the item-add, which then fails with `Content already
exists in this project`: the issue is on the Project, so read `gh project item-list` again, up to 5 times 2 s apart (it
lags), and use that item's id (T30; T6's import hit it twice, its `item_for()` in `git show
4abf92e2:.claude/skills/ticket-page/jira_import.py`).

## Input

- `$1` — one of:
  - a **tracker epic** `T<E>` (also `t<E>` or `#<E>`; normalise to `T<E>`). Its `epic.md` is the source.
  - a **local file path** to the epic doc, next-epic doc (brownfield), or PRD (greenfield), optionally followed by
    `T<E>`: the epic to file the tickets under (the doc is then the source, the epic issue context).

Detect `$1` in this order:

1. Matches `^[Tt#]?[0-9]+$` → the epic. If a second `T<E>` is also given and differs, stop and ask which one is meant.
2. An existing file → local file path.
3. Anything else → stop and say so.

Below, **the epic** means `T<E>` from `$1` or the token after a local path, whichever was given.

Flags (anywhere in the arguments):
- `--records-only`: the epic is already sliced and filed. Skip Steps 2-5 and the filing in Step 6 (6.1, the creates
  of 6.3, 6.4-6.6 and 6.8); run 6.2, the Project check of existing sub-issues in 6.3, and Step 6b for every sub-issue
  of the epic. Use it to give an existing epic's tickets their records, or after a
  run whose record step failed partway. Here an epic without `epic.md` is not a stop (Step 1): each record's Ticket
  section is its issue's body, as always. It never rewrites `breakdown.md`.
- `--no-tracker`: no ticket records (Step 6b is skipped; say so). The breakdown and the issues are written as usual.
- `--tracker-dry-run`: nothing is written to the tracker. Every write (the tracker commits of Steps 5 and 6.8, the
  `gh` writes: issue create and edit, Project item-add and item-edit, and the `ticket-page` calls) is printed as the
  exact command it would run, with the file it would write saved under the session scratchpad; reads run as usual.
  The local working copy is still written. Issue numbers that don't exist yet are shown as `#<new-1>`, `#<new-2>`, ….
- `--tracker-dir <dir>`: the tracker checkout to use (Configuration), for example a throwaway clone for a rehearsal.
- A primed session — `/prime` should already have loaded the relevant codebase surface.

## Process

### Step 1 — Load the PRD (source of truth)

The PRD is the source of truth for this entire decomposition. Load it before doing anything else.

**If an epic is known:**

1. `gh issue view <E> -R <o>/<r> --json number,title,body,state,issueType,labels,comments`. If it does not exist,
   stop. If its type is not `Epic`, tell the user and ask whether to continue.
2. Its sub-issues: `gh api repos/<o>/<r>/issues/<E>/sub_issues --paginate` (number, title, state, type, labels).
3. Bring `<T>` up to date (the checks and the pull of **Tracker writes**; nothing is written) and find the epic
   directory. If the checks fail (uncommitted changes, another branch), stop and report the files or the branch:
   Step 5 could not write either.

**If `$1` is the epic:** the PRD is `docs/T<E>-*/epic.md` in `<T>`. Say which file you are using. **No `epic.md`:**
stop (unless `--records-only`). Tell the user to run `/create-prd T<E>` first, or to pass a local doc path followed by
`T<E>`. Do not slice the bare issue body, because it is not a PRD.

**If `$1` is a file path:** read the file directly and use its contents as the PRD. With an epic, treat the issue
(body, comments, sub-issues) as supplementary context; if it and the doc conflict, the doc wins. If that epic has no
`epic.md`, the doc would be kept nowhere and `close-epic` would have no success criteria to judge against: recommend
publishing it first with `/create-prd T<E>` and continue only if the user says so.

Read the loaded PRD fully: the goal, user stories, architectural impact, acceptance criteria, out-of-scope.

### Step 2 — Decompose into PIV-sized slices

Break the epic into tickets. A well-sized ticket:

- Maps to **one plan** within its tier's budget (`.claude/context/process-tiers.md`): S ≤150 lines, M ≤300, L ≤300
  (up to 500 with a reason).
- Is one coherent unit — a vertical slice of behavior, not a horizontal layer.
- Has clear acceptance criteria of its own.
- Is small enough to execute in a single PIV loop (roughly 20-60 minutes of execute time).

If a slice would need a longer plan, split it. **Don't over-slice:** every ticket pays a fixed process cost (branch,
worktree, venv, plan, record, review, PR), so merge small investigation, characterisation and doc/tooling slices that
touch the same area into one S ticket instead of filing several tiny ones.

**Assign a tier to every ticket** (S, M or L, as defined in `.claude/context/process-tiers.md`) from what it touches,
not from its estimated effort: anything in the `pandf` tree, Jacobian/preconditioner code, `ppp/`, a `.v` file, the
build, or new physics is L.

### Step 3 — Slice for parallelizability

Map dependencies between tickets. **Independent tickets** — ones that don't touch the same files or rely on each other's output — can run in **parallel** (separate branches/worktrees, each with its own Python env since UEDGE installs compiled modules). Mark which tickets are independent and which form a dependency chain. Slicing along package and equation boundaries (`bbb/pandf_*` files, `.v` groups, `src/uedge/` modules) maximizes independence; tickets that both touch `bbb/bbb.v` or the `pandf` tree usually conflict. So do tickets that extend the same shared entry point in test or tooling code (a harness's runner and its configuration list, e.g. `tests/yldot/harness/process.py` and `state.py`) or rewrite the same paragraph of a context module: list such modified files under each ticket's Files touched, not only the new ones, and if those tickets still share a wave, give the wave a merge order (the second to merge rebases and re-runs its tests). Parallel is a means, not a goal: a wave runs in parallel only where that shortens the critical path, with at most about 3 tickets (background agents) at once (`.claude/context/process-tiers.md` → Session SOP).

### Step 4 — Write the ticket breakdown

Write the working copy to `.claude/work/T<E>/breakdown.md` in the current checkout (`.claude/work/<epic-slug>/`
without an epic), in the shape of the tracker's breakdown template plus the slicing sections:

```
# T<E>: <epic title>, ticket breakdown

The source is `epic.md` | `<local doc path>` (local, not in the tracker). Each ticket is a sub-issue of #<E>. Dependencies are also set as "blocked by" relations on
the issues.

## Epic summary
<goal in 2-3 lines>

## Rules every ticket of T<E> carries
<the PRD's rules every ticket must carry (e.g. an owner rule such as AIUE-9's decision 23), verbatim, each with its
PRD source; omit the section when the PRD sets none (T50)>

## TICKET-1: <title>                         (heading becomes `## T<N>: <title>` after Step 6)
- **Issue:** #<N> (after Step 6) · **Type:** Feature | Task | Bug · **Tier:** S | M | L (why, in a few words)
- **Branch:** `feature/v9-T<N>-<slug>` (`bugfix/v9-T<N>-<slug>` for a bug; AI-layer: `feature/v9-ai-<slug>`, label
  `ai-layer`) · base: `v9-develop` | `<parent ticket branch>` (stacked)
- **Depends on:** none | TICKET-x (T<M> after Step 6)
- **Scope:** <1-3 sentences>
- **Acceptance:** <checkable criteria>
- **Files touched:** <estimate: new and modified files, including shared harness files and the context-module
  paragraph it updates>
- **Record:** `T<N>-<slug>/record.md` (after Step 6b)

## TICKET-2: ...

## Dependency graph
   <text or mermaid graph showing the order + parallel groups>
## Suggested execution order
   Wave 1 (parallel): TICKET-1, TICKET-3
   Wave 2: TICKET-2 (after TICKET-1)
## Integration
   Ticket PRs target `v9-develop` | `feature/v9-T<E>-integration` (only if tickets can't land one by one; say why)
```

Branches follow `.claude/context/branching.md`: **one branch and worktree per ticket**, never one branch for a whole
epic by default. If a ticket would need AI-layer process changes (skills, agents, hooks), split those into a separate
`feature/v9-ai-<slug>` ticket with the label `ai-layer`. Updates that keep `CLAUDE.md`/`.claude/context/` factually
correct stay inside the ticket that changes those facts. Tickets that run in parallel (a wave above) each get their
own **explicit** worktree (`git worktree add -b <branch> ../uedge-wt/T<N> <base>`), also when subagents run them;
never the Agent tool's `isolation: "worktree"`, which is removed automatically with the ticket's working folder
(`branching.md` → Worktrees).

The working copy is gitignored and never committed to the public repo, on any branch (there is no planning branch,
`.claude/context/branching.md`). Its lasting home is `breakdown.md` in the tracker (Step 5), which later skills read.

### Step 5 — Commit the breakdown to the tracker

With an epic, `breakdown.md` in the epic directory is the breakdown's only lasting copy (the local file is a working
copy). As **Tracker writes** says, one commit `T<E> spec: breakdown.md (<n> tickets)` of:

1. `breakdown.md`: the working copy as written in Step 4. If one exists already (a re-run), it is replaced by the
   new working copy, which must keep every ticket the old one lists that is already filed (its `#<N>`, Branch and
   Record lines as they were); say in the commit message what changed.
2. `progress.md`, the epic's progress log, if it does not exist yet: the tracker's progress template with the epic's
   title. Later skills append one line per ticket milestone to it through `ticket-page progress`; whoever records an
   owner decision for the epic appends it the same way; `close-epic` reads it.

Record the commit: Step 6.8 checks against it. With `--tracker-dry-run`, print the files and the commands instead.

Without an epic, **skip this step** and say so: the breakdown then exists only as the local working copy and is not
kept. Tell the user to run `/create-prd new` (or pass `T<E>`) to file it.

### Step 6 — File the tickets as sub-issues

**With an epic this step is REQUIRED.** A breakdown nobody can assign is only half the job. Create the tickets for
real:

1. **Check for existing sub-issues first.** Compare every ticket in the breakdown with the sub-issues from Step 1
   (title, and scope where titles differ).
   - If a sub-issue already covers that slice, **skip it** and report it as already existing (with its number).
   - Only create the slices that are genuinely missing. Never create a near-duplicate of an existing sub-issue.
2. Read the Project ids once (**Project fields**) and the Project's items (the listing of Step 6b.1, with each
   item's Status and Tier).
3. **Create the missing ones in dependency order** (a ticket after the tickets it depends on, so their numbers are
   known). Per ticket, a body file `<scratch>/T<E>-ticket-<i>.md` in the tracker's Ticket form shape: `## Scope`
   (the scope, the files likely touched, and `Source: breakdown of T<E> (docs/T<E>-<slug>/breakdown.md)`), `##
   Acceptance criteria`, and the lines `Tier: <S|M|L> (<why>)`, `Branch: <branch> (base <base>)` and `Depends on:
   #<M>, … | none` (`plan-feature` reads Tier and Branch there first). When the breakdown has a `## Rules every
   ticket of T<E> carries` section, the body ends with it, verbatim (a ticket filed later copies it the same way,
   `.claude/context/branching.md` → Filing a ticket under an epic). Then

   ```bash
   gh issue create -R <o>/<r> --type <Feature|Task|Bug> --title "<title>" --body-file <scratch>/T<E>-ticket-<i>.md \
     --parent <E> [--label ai-layer]
   ```

   The URL it prints gives `<N>`. Then put it on the Project and set Tier and Status To Do (**Project fields**: one
   item-add and two item-edits).

   **Existing sub-issues** get the same Project check, so a partial run (an item-add or item-edit that failed) or the
   Project's auto-add of sub-issues (which sets no Status) leaves no gap: from the listing of 6.2, one
   not on the Project gets the item-add, an empty Tier is set from its breakdown entry (none there: report it), and
   an empty Status is set to To Do. Report each repair.
4. **Blocked by.** For every ticket with dependencies (created now or existing):
   `gh issue edit <N> -R <o>/<r> --add-blocked-by <M>[,<M2>…]`, only for the relations not already there
   (`gh api repos/<o>/<r>/issues/<N>/dependencies/blocked_by --jq '.[].number'`).
5. **After the batch,** list the sub-issues once more and report any title that now appears twice (a concurrent run);
   a person resolves it.
6. **Put the numbers into the working copy:** each heading `## T<N>: <title>` and its `Issue`, `Branch` and `Depends
   on` lines. Step 6b adds the `Record` lines.
7. Run **Step 6b** for every ticket created here and every existing sub-issue that has no record yet.
8. **Commit the breakdown once more** (**Tracker writes**, `T<E> spec: breakdown.md issue numbers`) with the
   numbers and Record lines. First check that it hasn't moved: after the pull, `git -C <T> log -1 --format=%h --
   <breakdown.md path>` must be Step 5's commit. Otherwise someone edited it; don't overwrite it, report it.
   Skipped with `--records-only`.
9. Report a table of the tickets: `#<N>`, title, URL, type, tier, created or already present, blocked by, and the
   record (created, already present, skipped with why), plus anything that failed.

Without an epic, skip this step and tell the user which epic to pass to file the tickets.

### Step 6b — Create each ticket's record

Every ticket gets **one** record for its whole life, created here, and every later skill writes to it: `plan-feature`
(or `implement-fix`) publishes the plan (or RCA) next to it, `execute`, `validate` and the review gates log to it, the
commit closes it (`.claude/skills/ticket-page/SKILL.md`). `--tracker-dry-run` prints the calls; `--no-tracker` skips
the step.

**Which tickets.** Every ticket created in Step 6, and every existing sub-issue of the epic whose Project Status is
**To Do or In Progress** (an empty Status, which 6.3 repairs, counts as To Do) that has no record yet. Sub-issues in **In Review, Done** (or closed) are skipped and listed
in the report as "skipped (status <s>)": their work is largely recorded elsewhere, and a record made now could only
say so (owner decision, 2026-10-16). A record for an existing sub-issue is a **backfill**: it claims nothing about the
ticket's past.

1. **Statuses** come from the Project: `gh project item-list <P> --owner <o> --format json --limit 1000`, the items
   whose `content.repository` is `<o>/<r>` and whose `content.number` is a sub-issue, with their `status` and `tier`
   (`null` when empty).
2. **Existing records:** after the pull, `docs/*/T<N>-*/record.md` in `<T>`. One → the ticket has a record (from an
   earlier `spec` run or from another skill that found none): leave it as it is and report it; add its `Record` line
   to the working copy if it is missing (not with `--records-only`). Two → report the ticket and write nothing for it
   (`ticket-page` refuses it too, exit 2, until a person merges them).
3. **Create:** `uv run .claude/skills/ticket-page/ticket_page.py --caller spec create T<N>` (with `--tracker-dir
   <dir>` when one was given; the caller name is `spec --records-only` for that mode). The Ticket section is the
   issue's body, the header has the issue type, the Project's Tier and status `Planned`, and the record sits under the
   epic directory. It is one commit in `<T>`, pushed. Put the path it prints, relative to the epic directory, in the
   ticket's `Record` line of the working copy.
4. **A backfill** of a **To Do** sub-issue then runs `status T<N> Backfilled "Ticket section: the issue body as read
   on <date>, not as filed"` (it hasn't started; the Project Status stays To Do). An **In Progress** sub-issue gets no
   status call, because `Backfilled` would move its Project Status back to To Do: it gets one `log T<N> Progress
   "record backfilled by spec: the ticket was In Progress, so its Project Status is left as it is and the header Status
   still reads Planned; the Ticket section is the issue body as read on <date>, not as filed"` instead. (`create`
   writes "as filed" and `Planned` for every record; a backfill corrects both through these entries.)
5. A failure (GitHub down, a refused write, a dirty tracker checkout) never stops the run: report the ticket and the
   error verbatim; a re-run (or `--records-only`) creates only what is still missing.

**Cost and prompts.** Per new ticket: one issue create, one item-add and two item-edits, one blocked-by edit when it
has dependencies, and one `ticket-page create` (a tracker commit and push); each `gh` write can be a permission prompt.
Per batch: the Project field listing, the sub-issue listing before and after, and two breakdown commits.

> Order matters: write the breakdown working copy first (Step 4), commit it to the tracker (Step 5), then create the
> issues, then their records (Step 6b), then commit the breakdown with the numbers (Step 6.8). If issue or record
> creation fails partway, the breakdown still exists and the run is re-runnable: Step 6.1 and Step 6b.2 skip what
> already exists, so a re-run never adds a second issue or record, and 6.3 completes the Project fields of what
> exists. Two runs at the same time can still create two
> issues for one ticket; the listing after the batch detects it, and it is reported for a person to resolve.

## Output

1. A ticket breakdown working copy at `.claude/work/T<E>/breakdown.md` (always; local, never committed to the public
   repo).
2. `breakdown.md` in the epic directory of the tracker, its lasting home, and `progress.md` if it was missing (with an
   epic), with the commits.
3. Sub-issues of the epic, each on the Project with Tier and Status To Do and its "blocked by" relations (Step 6).
   Existing sub-issues are never duplicated.
4. One record per ticket (`ticket-page create`; Step 6b), for new tickets and for existing To Do / In Progress
   sub-issues; a table of what was created, already present, and skipped (with why).
5. With `--tracker-dry-run`: the commands a real run would have run, in order, and the files it would have written.

Each ticket then enters its own PIV loop starting at `/prime` → `/plan-feature`, which publishes the plan next to that
same record through the `ticket-page` skill; `execute`, `validate` and the review gates log to it. When the tickets are
done, `/close-epic T<E>` writes the close-out record and closes the epic (`--dry-run` for a read-only draft first).

## Notes

- Issues live in the tracker: GitHub Issues (the epic and its sub-issues) and the Project (Status, Tier). The slicing
  logic does not depend on where they live.
- The epic's progress log is `progress.md` in the epic directory (Step 5 creates it; dated, append-only lines; owner
  decisions attributed as in `close-epic`), never a file in the public repo (`branching.md`). `execute`, `validate`,
  the review loop, `end-to-end-feature` and `implement-fix` append to it through `ticket-page progress`; `close-epic`
  reads it.
- Greenfield: the same slicing applies to MVP phases instead of epic tickets.
