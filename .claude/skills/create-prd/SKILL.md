---
name: create-prd
description: Generates a comprehensive Product Requirements Document from the current conversation context and, optionally, a tracker epic. Given an epic issue (T<E>) or "new" (it then creates the epic issue once the owner confirms the title), it reads the epic, has the PRD adversarially reviewed by the uedge-reviewer agent until it is approved, publishes it as the epic document docs/T<E>-<slug>/epic.md in the private tracker named by .claude/tracker.toml (review rounds in its Reviews section), links it from the epic issue, and hands over to /spec T<E>. Use when requirements have been discussed and you need to formalize them into a professional PRD before planning.
argument-hint: "[T<E> | new] [optional-output-filename] [--tracker-dir <dir>]"
---

# Create PRD: Generate Product Requirements Document

## Overview

Generate a comprehensive Product Requirements Document (PRD) based on the current conversation context and requirements discussed. Use the structure and sections defined below to create a thorough, professional PRD.

With an epic (`T<E>` or `new`), the approved PRD becomes the epic document `docs/T<E>-<slug>/epic.md` in the tracker,
so that `/spec T<E>` can slice it into tickets in a later session.

**Nothing reaches the tracker's `docs/` without passing an adversarial review.** Before `epic.md` is written or
changed, an independent `uedge-reviewer` agent must have reviewed the PRD and returned **APPROVE** (Step 5). This
applies to new PRDs and to revisions of an existing `epic.md`. (The epic issue itself is not gated: like the epic a
person files, it is only the epic's identity.)

## Configuration

| Setting | Value |
|---|---|
| Tracker | `.claude/tracker.toml` in the main checkout: `owner`, `repo`, `project`. Below, `<o>/<r>` is owner/repo and `<P>` the Project number; never write them out in this skill |
| Tracker checkout `<T>` | `<parent of the main checkout>/<repo>`, as `ticket-page` uses it (the main checkout is the parent of `git rev-parse --path-format=absolute --git-common-dir`); `gh repo clone <o>/<r> <T>` if missing. `--tracker-dir <dir>` overrides it (a throwaway clone for a rehearsal) |
| Epic directory | `docs/T<E>-<slug>/` in `<T>`: an existing `docs/T<E>-*/` if there is one, else `<slug>` from the epic title as `ticket-page` makes it (lower case, every run of other characters one `-`, at most 40 characters) |
| Epic document | `epic.md` in the epic directory, in the shape of the tracker's epic.md template (`templates` directory of `<T>`): header table, Goal, Scope, Success criteria, Decisions, Reviews |
| Local working copy | `.claude/work/T<E>/prd-v<N>.md` in the current checkout (gitignored, never committed): `v1` for a new PRD, one more than the last for a revision. Once published, `epic.md` is the PRD |
| Review reports | `.claude/work/T<E>/reviews/T<E>-prd-round<N>.md` and `-response.md` (local, never committed); their lasting record is `epic.md`'s `## Reviews` |
| Max review rounds before escalating to the user | 3 |

**Tracker writes** (Step 6; the same rule as `ticket-page`): before writing, `git -C <T> status --porcelain
--untracked-files=no` must be empty and `git -C <T> symbolic-ref --short HEAD` the default branch (`main`);
otherwise write nothing and report the files or the branch. Then `git -C <T> pull --rebase -q` (a conflict: `git -C
<T> rebase --abort`, write nothing, report; an unreachable remote: write locally and say the push is pending), write
the files, `git -C <T> add -- <paths>`, `git -C <T> commit -q -m "T<E> create-prd: <what>" -- <paths>` and `git -C
<T> push -q` (a failed push is reported; the next write pushes it). One commit per publish. A `ticket-page` call that
runs in this checkout between the write and the commit is refused (exit 2, uncommitted changes) and is simply re-run;
if these checks find a file another call is writing, wait a few seconds and check again.

## Input

Parse `$ARGUMENTS` as up to two whitespace-separated tokens, in either order, plus `--tracker-dir <dir>`:

- **Epic.** `T<E>` (also `t<E>` or `#<E>`; normalise to `T<E>`) names an existing epic issue. `new` asks for a new
  epic issue (Step 0).
- **Output filename.** Any other token. It overrides the local copy path.

Without an epic, this skill writes the PRD to the output filename (default `.claude/work/prd/<slug>.md`, local and
gitignored) and skips Steps 0, 6 and 7 below. Nothing then reaches the tracker: say that the file is the only copy
and is not committed. The adversarial review (Step 5) is optional then: offer it in one line, and run it if the user
says yes.

## Output File

- With an epic, write the local working copy to the output filename if one was given, otherwise to
  `.claude/work/T<E>/prd-v<N>.md`. Then get it approved by the adversarial review (Step 5) and publish it to the
  tracker (Step 6), which makes `epic.md` the PRD. A later revision starts from `epic.md` as read from `<T>` after a
  pull, not from an old local copy.
- Without an epic, write it to the output filename (default: `.claude/work/prd/<slug>.md`, `<slug>` the topic in
  kebab case, cut to about 50 characters).

## PRD Structure

Create a well-structured PRD with the following sections. Adapt depth and detail based on available information:

### Required Sections

**1. Executive Summary**
- Concise product overview (2-3 paragraphs)
- Core value proposition
- MVP goal statement

**2. Mission**
- Product mission statement
- Core principles (3-5 key principles)

**3. Target Users**
- Primary user personas
- Technical comfort level
- Key user needs and pain points

**4. MVP Scope**
- **In Scope:** Core functionality for MVP (use ✅ checkboxes)
- **Out of Scope:** Features deferred to future phases (use ❌ checkboxes)
- Group by categories (Core Functionality, Technical, Integration, Deployment)

**5. User Stories**
- Primary user stories (5-8 stories) in format: "As a [user], I want to [action], so that [benefit]"
- Include concrete examples for each story
- Add technical user stories if relevant

**6. Core Architecture & Patterns**
- High-level architecture approach
- Directory structure (if applicable)
- Key design patterns and principles
- Technology-specific patterns

**7. Tools/Features**
- Detailed feature specifications
- If building an agent: Tool designs with purpose, operations, and key features
- If building an app: Core feature breakdown

**8. Code Basis**
- Packages, files and routines affected (`bbb/pandf_*`, `.v` groups, `ppp/`, `svr/`, `src/uedge/`)
- Build impact (new `.m` files, `Makefile.Forthon`/`Package` registration, Forthon/compiler requirements)
- Dependencies (Python packages, rate/data files) and platform constraints (macOS/Linux, OpenMP)

**9. Physics & Numerics Impact**
- Equations and terms affected; whether new physics needs a spec in `docs/physics_specs/`
- **Default-results impact:** refactor (must be unchanged) vs intended physics/numerics change (which defaults
  change, which reference cases move)
- Solver/Jacobian/OpenMP implications (stencil, threadprivate state, convergence)

**10. User-Facing Interface** (if applicable)
- New/changed input variables and switches (`.v` declarations, defaults, units)
- Python API changes (`uedge.*` modules, `rundt`, save/restore formats) and backward compatibility of input
  decks and save files

**11. Success Criteria**
- MVP success definition
- Functional requirements (use ✅ checkboxes)
- Quality indicators
- User experience goals

**12. Implementation Phases**
- Break down into 3-4 phases
- Each phase includes: Goal, Deliverables (✅ checkboxes), Validation criteria
- Realistic timeline estimates

**13. Future Considerations**
- Post-MVP enhancements
- Integration opportunities
- Advanced features for later phases

**14. Risks & Mitigations**
- 3-5 key risks with specific mitigation strategies

**15. Appendix** (if applicable)
- Related documents
- Key dependencies with links
- Repository/project structure

## Instructions

### 0. Load the epic (only with an epic)

**`T<E>`:**

1. `gh issue view <E> -R <o>/<r> --json number,title,body,state,issueType,labels,comments`.
   - If the issue does not exist, stop and report this.
   - If its type is not `Epic`, tell the user and ask whether to continue.
2. Its sub-issues: `gh api repos/<o>/<r>/issues/<E>/sub_issues --paginate` (number, title, state).
3. Look for an existing epic document. Bring `<T>` up to date (the checks and the pull of **Tracker writes**; nothing
   is written), then look for `docs/T<E>-*/epic.md`. If the checks fail (uncommitted changes, another branch), don't
   pull: `git -C <T> fetch -q`, read with `git -C <T> show origin/main:<path>` (list with `git -C <T> ls-tree
   --name-only origin/main docs/ | grep "^docs/T<E>-"`), and tell the user that Step 6 can't write until the checkout
   is fixed.
   - If one exists (written by an earlier run, or by hand), read it. Treat this run as a **revision** of it, not a
     new PRD: keep what is still valid and change only what the conversation changed.

**`new`:**

1. If the conversation has not discussed the requirements, ask the key questions first (below).
2. Propose an epic title from the conversation and ask the owner to confirm or change it. Create nothing before the
   owner confirms.
3. Look for it first (an earlier run may have created it and stopped): `gh issue list -R <o>/<r> --state open
   --search '<title> in:title' --json number,title,issueType`. An Epic with that exact title → it is `<E>`: say so,
   add only what an earlier run left undone (the Records line, step 4), and continue as with `T<E>` above. Otherwise
   create the issue: `gh issue create -R <o>/<r> --type Epic --title "<title>" --body-file <scratch>/epic-body.md`
   (add `--label ai-layer` for AI-layer work). The body has the tracker's Epic form shape: `## Goal` (two or three
   lines from the conversation), `## Scope` and `## Success criteria` ("in `epic.md` once the PRD is approved"). The
   URL it prints gives `<E>`. Then add the line `Records: docs/T<E>-<slug>/` to the body (`gh issue edit <E> -R
   <o>/<r> --body-file …`).
4. Put it on the Project as To Do: `gh project item-add <P> --owner <o> --url <issue URL> --format json` (the item
   id), then `gh project item-edit --id <item id> --project-id <project id> --field-id <Status field id>
   --single-select-option-id <To Do option id>`, with the ids from `gh project view <P> --owner <o> --format json` and
   `gh project field-list <P> --owner <o> --format json`.

Use the epic's body, comments and sub-issues as input alongside the conversation. If the epic and the conversation
conflict, the conversation wins, because it is more recent. Say in the PRD which one you followed.

**If the epic has no description and the conversation has not discussed its requirements, do not invent a
PRD.** Ask the user the key questions first: the goal, what is in and out of scope, the success criteria, and
whether default results may change. Generate the PRD only after they answer.

### 1. Extract Requirements
- Review the entire conversation history
- Identify explicit requirements and implicit needs
- Note technical constraints and preferences
- Capture user goals and success criteria

### 2. Synthesize Information
- Organize requirements into appropriate sections
- Fill in reasonable assumptions where details are missing
- Maintain consistency across sections
- Ensure technical feasibility

### 3. Write the PRD
- Use clear, professional language
- Include concrete examples and specifics
- Use markdown formatting (headings, lists, code blocks, checkboxes)
- Add code snippets for technical sections where helpful
- Keep Executive Summary concise but comprehensive

### 4. Quality Checks
- ✅ All required sections present
- ✅ User stories have clear benefits
- ✅ MVP scope is realistic and well-defined
- ✅ Default-results impact and physics-spec needs are stated
- ✅ Implementation phases are actionable
- ✅ Success criteria are measurable
- ✅ Consistent terminology throughout
- ✅ With an epic: the binding decisions are listed, ready for `epic.md`'s Decisions (Step 6)

Write the local working copy now, before the review, so the PRD survives anything that fails later in this session.
It goes in the working folder of the current checkout, on whatever branch it is: nothing is committed to the public
repo, so no branch is needed (there is no planning branch, `.claude/context/branching.md`). The PRD and its review
reports are working documents until `epic.md` is published; never commit them to the public repo.

### 5. Adversarial review (required before any write to `epic.md`)

The author of the PRD (this session) can't review it independently. Spawn a **fresh** `uedge-reviewer` agent
(Agent tool, `subagent_type: "uedge-reviewer"`). Never use a fork or a reused agent that saw the drafting. The
reviewer can't see this conversation, so its prompt must be self-contained:

- `stage: prd`, the round number, the epic (`T<E>`), the absolute path of the local PRD copy, and the absolute report
  path `<checkout>/.claude/work/T<E>/reviews/T<E>-prd-round<N>.md`;
- the requirement **decisions** taken in this session (the user's answers, mid-session additions), each marked as
  binding, so the reviewer checks the PRD against them instead of second-guessing them;
- for a revision of an existing `epic.md`: what changed and why, and the path of a local copy of the previous
  `epic.md`;
- on rounds 2+: the previous review report path and your response to each finding (fixed where, or rebutted why).

Then loop:

1. Wait for the reviewer's completion notification. Don't read or summarize its result before then.
2. Read `.claude/work/T<E>/reviews/T<E>-prd-round<N>.md`.
3. **APPROVE** → go to Step 6.
4. **REVISE** → fix every BLOCKER and MAJOR finding in the local copy (or write a specific rebuttal when the
   finding is wrong), and write the response to `.claude/work/T<E>/reviews/T<E>-prd-round<N>-response.md`
   (finding → fixed where / rebutted why). Apply cheap MINOR fixes. Fixes must not contradict a binding user decision. If a finding *does*
   challenge one, ask the user rather than silently changing scope. Start round N+1 with a fresh reviewer as a
   **verification round** (the previous findings, the response and a diff of the revised PRD;
   `.claude/context/process-tiers.md` → Review rounds; `model: sonnet` unless the revision redesigns the approach).
   MINORs alone never start a round.
5. **REJECT** → stop. Show the user the reviewer's reasoning and ask how to proceed. Don't publish.
6. If round 3 ends without APPROVE, stop and escalate. List the open BLOCKER/MAJOR findings and ask the user
   whether to keep revising or to publish anyway.
   - Publish anyway **only** on an explicit user instruction. In that case set the header's Status to
     `Draft - review open (N findings)` and add a "## Open review findings" section after Success criteria that
     lists them.

The review reports and responses stay local and are never committed to the public repo; Step 6 puts their content in
`epic.md`'s `## Reviews`, one entry per round.

### 6. Publish `epic.md` (only with an epic)

**Precondition:** Step 5 returned APPROVE for the exact text being published, or the user explicitly overrode it as
described in Step 5.6. If you edited the PRD after the approving round (beyond typo-level fixes), run one more
round first.

1. **The document.** `epic.md` in the epic directory (Configuration), in the template's shape:
   - `# T<E>: <epic title>`, then the header table: Issue `#<E> (type Epic)`; Status `Approved` (or the Step 5.6
     draft status); Breakdown `breakdown.md` and Progress `progress.md`
     (`spec` writes both); Adversarial review `<VERDICT> (round <N>, <B> blocker / <M> major / <m> minor raised in total)`;
     Last update `<date>`.
   - `## Goal`: the Executive Summary and the Mission (sections 1-2).
   - `## Scope`: the MVP Scope (section 4), in and out of scope.
   - `## Success criteria`: section 11, as written. `close-epic` judges the epic against this section.
   - Every other PRD section (3, 5-10, 12-15) as its own `## <section name>` after Success criteria, in PRD order and
     in full: nothing of the PRD is dropped. `spec` and `close-epic` find them by name (for example
     `## Physics & Numerics Impact` for the default-results statement).
   - `## Decisions` (append-only): one entry per binding requirement decision, `- YYYY-MM-DD Owner: <decision>
     (<source>: an issue comment, or the session's date)`, and `Agent:` entries for the agent's own choices (which of
     epic and conversation it followed). Mark Owner only when the owner said it (`ticket-page` → Attribution).
   - `## Reviews` (append-only): per round, `- YYYY-MM-DD (create-prd): Reviewer: PRD round <N> <VERDICT> (<B>
     BLOCKER / <M> MAJOR / <m> MINOR). <ID> <the finding in one line>; …` and `- YYYY-MM-DD (create-prd): Agent:
     round <N> response: <ID> fixed (<where>) | rebutted (<why, in a line>) | deferred; … Binding decisions given to
     the reviewer: <list>. Not independently verified: <items or none>.` Size caps as `process-tiers.md` → Report
     caps.
   - **A revision** replaces the sections above Decisions with the revised text and keeps every existing Decisions
     and Reviews entry as it is, appending the new ones. Sections the template doesn't have that a person added
     (such as a `## Closing` note) are kept unless the revision changes them.
2. **Write it** as **Tracker writes** says, one commit of `epic.md`: `T<E> create-prd: epic.md (new | revised:
   <what changed>), review <VERDICT> round <N>`. Record the commit.

If a tracker write fails (dirty checkout, rebase conflict), report the error verbatim. Point the user to the local
copy and stop: it is not committed and is the only copy until the publish succeeds, so it must stay where it is.

### 7. Link `epic.md` from the epic issue (only with an epic)

1. Check the issue comments from Step 0. If one already links this `epic.md`, skip this step (a revision is recorded
   by its commit and its Reviews entries).
2. Otherwise post one line: `gh issue comment <E> -R <o>/<r> --body "PRD: docs/T<E>-<slug>/epic.md (<commit>),
   adversarial review <VERDICT> round <N>. Slice it into tickets with /spec T<E>."`

Do not overwrite the issue's body (the only body edit is the Records line of a `new` epic, Step 0).

## Style Guidelines

- **Tone:** Professional, clear, action-oriented
- **Format:** Use markdown extensively (headings, lists, code blocks, tables)
- **Checkboxes:** Use ✅ for in-scope items, ❌ for out-of-scope
- **Specificity:** Prefer concrete examples over abstract descriptions
- **Length:** Comprehensive but scannable (typically 30-60 sections worth of content)

## Output Confirmation

After creating the PRD:
1. Confirm the local working copy's path (not committed; with an epic, `epic.md` is the PRD)
2. Give the review outcome: the final verdict, the number of rounds, the findings fixed or rebutted per round, the
   local report paths and the Reviews entries. If the review was skipped (no epic, user declined) or overridden, say
   so plainly
3. With an epic, also give the epic issue (`#<E>`, created now or existing), the path of `epic.md` in the tracker
   and its commit, say whether it was created or revised and pushed, and say whether the issue comment was added
4. Provide a brief summary of the PRD contents
5. Highlight any assumptions made due to missing information
6. Suggest next steps. With an epic, give the exact command for the next session: `/spec T<E>`. Review `epic.md`
   first and edit it in the tracker if needed (a commit with a Decisions entry saying what changed), because `/spec`
   treats `epic.md` as the source of truth.

## Notes

- If critical information is missing, ask clarifying questions before generating
- Adapt section depth based on available details
- For highly technical products, emphasize architecture and technical stack
- For user-facing products, emphasize user stories and experience
- This skill contains the complete PRD template structure - no external references needed
- Re-running with the same epic is safe. It revises the existing `epic.md` and does not duplicate the issue comment.
  Every rerun that changes `epic.md` goes through Step 5 again.
- Never write `epic.md` before Step 5 has passed.
