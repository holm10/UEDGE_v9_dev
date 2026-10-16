---
name: create-prd
description: Generates a comprehensive Product Requirements Document from the current conversation context and, optionally, a Jira epic. When given a Jira epic key (e.g. AIUE-5), it reads the epic, has the PRD adversarially reviewed by the uedge-reviewer agent until it is approved, publishes it as a Confluence page linked to that epic, and returns the page id to feed into /spec. Use when requirements have been discussed and you need to formalize them into a professional PRD before planning.
argument-hint: "[optional-jira-epic-key] [optional-output-filename]"
---

# Create PRD: Generate Product Requirements Document

## Overview

Generate a comprehensive Product Requirements Document (PRD) based on the current conversation context and requirements discussed. Use the structure and sections defined below to create a thorough, professional PRD.

When a Jira epic key is given, the PRD is also published to Confluence, so that `/spec <page-id> <epic-key>` can
slice it into tickets in a later session (see the two-session flow in the `spec` skill).

**Nothing reaches Confluence without passing an adversarial review.** Before any create or update of a Confluence page,
an independent `uedge-reviewer` agent must have reviewed the PRD and returned **APPROVE** (Step 5). This applies to
new PRDs and to revisions of an existing PRD page.

## Configuration

| Setting | Value |
|---|---|
| Confluence space for PRDs | `SD` (Software Development) |
| Parent page for PRDs | `Product Requirements` (created in that space if missing) |
| PRD page title | `PRD: <EPIC-KEY> - <epic summary without trailing period>` |
| Local working copy | `.claude/work/<EPIC-KEY>/prd.md` in the current checkout (gitignored, never committed; once published, the Confluence page is the PRD) |
| Review reports | `.claude/work/<EPIC-KEY>/reviews/<EPIC-KEY>-prd-round<N>.md` and `-response.md` (local, never committed) |
| Review summaries | child page of the PRD, title `PRD reviews: <EPIC-KEY>` (Step 6b): the lasting record of the review |
| Max review rounds before escalating to the user | 3 |

If the user names a different space or parent page, use that instead.

## Input

Parse `$ARGUMENTS` as up to two whitespace-separated tokens, in either order:

- **Jira epic key.** A token matching `^[A-Za-z][A-Za-z0-9]*-?[0-9]+$`. Normalize it to upper case with a hyphen
  before the number, so `AIUE5`, `aiue5` and `AIUE-5` all become `AIUE-5`.
- **Output filename.** Any other token. It overrides the local copy path.

Without an epic key, this skill writes the PRD to the output filename (default `.claude/work/prd/<slug>.md`, local
and gitignored) and skips Steps 0, 6, 6b and 7 below. Nothing then reaches Confluence: say that the file is the only
copy and is not committed. The adversarial review (Step 5) is optional then: offer it in one line, and run it if the
user says yes.

## Output File

- With an epic key, write the local working copy to the output filename if one was given, otherwise to
  `.claude/work/<EPIC-KEY>/prd.md`. Then get it approved by the adversarial review (Step 5) and publish it to
  Confluence (Step 6), which makes the page the PRD. A later revision starts from the page as read
  (`getConfluencePage`, markdown), not from an old local copy.
- Without an epic key, write it to the output filename (default: `.claude/work/prd/<slug>.md`, `<slug>` the topic in
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

### 0. Load the Jira Epic (only with an epic key)

1. Call `mcp__atlassian__getAccessibleAtlassianResources` and take the `cloudId` of the site that has Jira
   scopes. Reuse it for every later Atlassian call.
2. Call `mcp__atlassian__getJiraIssue` with the epic key, `responseContentFormat: "markdown"`, and
   `fields: ["summary", "description", "issuetype", "project", "status", "comment"]`.
   - If the issue does not exist, stop and report this.
   - If its type is not `Epic`, tell the user and ask whether to continue.
3. Call `mcp__atlassian__searchJiraIssuesUsingJql` with `parent = <EPIC-KEY>` to list existing child issues.
4. Look for an existing PRD. Search Confluence with `mcp__atlassian__searchConfluenceUsingCql` for
   `type = page AND title ~ "PRD: <EPIC-KEY>"`. Keep only exact title-prefix matches, so that `AIUE-5` does
   not match `AIUE-50`.
   - If a PRD already exists, read it with `mcp__atlassian__getConfluencePage` (`contentFormat: "markdown"`).
     Treat this run as a **revision** of that page, not a new PRD: keep what is still valid and change only
     what the conversation changed.

Use the epic summary, description, comments and child issues as input alongside the conversation. If the
epic and the conversation conflict, the conversation wins, because it is more recent. Say in the PRD which
one you followed.

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
- ✅ With an epic key: the PRD starts with a metadata line linking the epic (see Step 6)

Write the local working copy now, before the review, so the PRD survives anything that fails later in this session.
It goes in the working folder of the current checkout, on whatever branch it is: nothing is committed, so no branch
is needed (there is no planning branch, `.claude/context/branching.md`). The PRD and its review reports are working
documents until the page is published; never commit them.

### 5. Adversarial review (required before any Confluence write)

The author of the PRD (this session) can't review it independently. Spawn a **fresh** `uedge-reviewer` agent
(Agent tool, `subagent_type: "uedge-reviewer"`). Never use a fork or a reused agent that saw the drafting. The
reviewer can't see this conversation, so its prompt must be self-contained:

- `stage: prd`, the round number, the epic key, the absolute path of the local PRD copy, and the absolute report
  path `<checkout>/.claude/work/<EPIC-KEY>/reviews/<EPIC-KEY>-prd-round<N>.md`;
- the requirement **decisions** taken in this session (the user's answers, mid-session additions), each marked as
  binding, so the reviewer checks the PRD against them instead of second-guessing them;
- for a revision of an existing Confluence PRD: what changed and why, and the path of a local copy of the previous
  page body;
- on rounds 2+: the previous review report path and your response to each finding (fixed where, or rebutted why).

Then loop:

1. Wait for the reviewer's completion notification. Don't read or summarize its result before then.
2. Read `.claude/work/<EPIC-KEY>/reviews/<EPIC-KEY>-prd-round<N>.md`.
3. **APPROVE** → go to Step 6.
4. **REVISE** → fix every BLOCKER and MAJOR finding in the local copy (or write a specific rebuttal when the
   finding is wrong), and write the response to `.claude/work/<EPIC-KEY>/reviews/<EPIC-KEY>-prd-round<N>-response.md`
   (finding → fixed where / rebutted why). Apply cheap MINOR fixes. Fixes must not contradict a binding user decision. If a finding *does*
   challenge one, ask the user rather than silently changing scope. Start round N+1 with a fresh reviewer.
5. **REJECT** → stop. Show the user the reviewer's reasoning and ask how to proceed. Don't publish.
6. If round 3 ends without APPROVE, stop and escalate. List the open BLOCKER/MAJOR findings and ask the user
   whether to keep revising or to publish anyway.
   - Publish anyway **only** on an explicit user instruction. In that case set the metadata status to
     `Draft - review open (N findings)` and add a "## Open review findings" section at the end of the PRD that lists them.

Record each round in the PRD's appendix as a "Review history" table (round, verdict, BLOCKER/MAJOR/MINOR counts).
The review reports and responses stay local and are never committed; Step 6b puts their content on Confluence.

### 6. Publish to Confluence (only with an epic key)

**Precondition:** Step 5 returned APPROVE for the exact text being published, or the user explicitly overrode it as
described in Step 5.6. If you edited the PRD after the approving round (beyond typo-level fixes), run one more
round first.

1. **Find the space.** Call `mcp__atlassian__getConfluenceSpaces` with `keys: ["SD"]` (or the space the user
   named) to get the numeric `spaceId`.
2. **Find or create the parent page.** Search with CQL for
   `space = "SD" AND type = page AND title = "Product Requirements"`. If no such page exists, create it with
   `mcp__atlassian__createConfluencePage`, giving it a one-line body: "PRDs for Jira epics. Each child page is
   created by the create-prd skill and sliced into tickets by the spec skill."
3. **Prepare the body.** Start with the same markdown as the local copy, then put this metadata block directly
   under the H1 title:

   ```markdown
   > **Jira epic:** [<EPIC-KEY>](https://<site>/browse/<EPIC-KEY>) - <epic summary>
   > **Status:** Draft · **Generated by:** create-prd · **Next step:** `/spec <this-page-id> <EPIC-KEY>`
   > **Adversarial review:** <VERDICT> (round <N>, <B> blocker / <M> major / <m> minor raised in total) · [PRD reviews: <EPIC-KEY>](<reviews page URL>)
   ```

   The page id is unknown until the page exists. On a new page, publish with `<page-id>` and `<reviews page URL>` as
   placeholders, then, after Step 6b, update the page once with the real id and link. Do not use Mermaid diagrams, because Confluence's markdown
   import does not render them. Use tables or indented lists instead.
4. **Create or update the page.**
   - If Step 0 found no PRD, call `mcp__atlassian__createConfluencePage` with `cloudId`, `spaceId`,
     `parentId` set to the "Product Requirements" page id, `title` set to `PRD: <EPIC-KEY> - <summary>`,
     `contentFormat: "markdown"`, and `body`.
   - If Step 0 found a PRD, call `mcp__atlassian__updateConfluencePage` on that page id with
     `contentFormat: "markdown"` and a `versionMessage` that says what changed. Never create a second PRD page
     for the same epic.
5. Record the page id and its web URL.

If any Confluence call fails, report the error verbatim. Point the user to the local copy and stop: it is not
committed and is the only copy until the publish succeeds, so it must stay where it is. Do not retry into a different
space.

### 6b. Publish the review summaries (only with an epic key)

The review reports are not kept, so their content goes to Confluence, on a child page of the PRD titled `PRD reviews:
<EPIC-KEY>` (no review gate of its own: it only records the reviews). Body, one section per round, newest last:

```markdown
> Review rounds of [PRD: <EPIC-KEY> - <summary>](<PRD URL>), written by the create-prd skill (posted by an agent
> through the owner's account). The full reports were local working files and are not kept.

## Round <N> - <VERDICT> (<B> BLOCKER / <M> MAJOR / <m> MINOR), <date>
Binding decisions given to the reviewer: <list>.
- <ID> (<severity>): <the finding in one line>. Response: fixed (<where>) | rebutted (<why, in a line>) | deferred.
Not independently verified: <items or none>.
```

Find it first (CQL `type = page AND parent = <PRD id> AND title = "PRD reviews: <EPIC-KEY>"`). None →
`createConfluencePage` (PRD's `spaceId`, `parentId` = PRD id, `contentFormat: "markdown"`). Found (a rerun) →
read it and `updateConfluencePage` with the new rounds appended and every earlier section kept. Never a second page.
A failure here is reported and retried on the next run; it doesn't undo the PRD publish.

### 7. Link the PRD back to the Jira epic (only with an epic key)

The epic and the PRD should each point to the other:

1. Check the epic comments from Step 0. If one already contains this page id, skip this step.
2. Otherwise call `mcp__atlassian__addCommentToJiraIssue` on the epic with `contentFormat: "markdown"`:

   ```markdown
   PRD: [<page title>](<page URL>) (Confluence page id `<page-id>`).
   Slice into tickets with `/spec <page-id> <EPIC-KEY>`.
   ```

Do not overwrite the epic's description.

## Style Guidelines

- **Tone:** Professional, clear, action-oriented
- **Format:** Use markdown extensively (headings, lists, code blocks, tables)
- **Checkboxes:** Use ✅ for in-scope items, ❌ for out-of-scope
- **Specificity:** Prefer concrete examples over abstract descriptions
- **Length:** Comprehensive but scannable (typically 30-60 sections worth of content)

## Output Confirmation

After creating the PRD:
1. Confirm the local working copy's path (not committed; with an epic key, the Confluence page is the PRD)
2. Give the review outcome: the final verdict, the number of rounds, the findings fixed or rebutted per round, the
   local report paths and the `PRD reviews` page. If the review was skipped (no epic key, user declined) or
   overridden, say so plainly
3. With an epic key, also give the Confluence page title, page id and URL, say whether the page was created
   or updated, and say whether the epic comment was added
4. Provide a brief summary of the PRD contents
5. Highlight any assumptions made due to missing information
6. Suggest next steps. With an epic key, give the exact command for the next session: `/spec <EPIC-KEY>`.
   It finds this page by its title. `/spec <page-id> <EPIC-KEY>` is equivalent. Review the PRD first and edit it in Confluence if needed, because `/spec`
   treats the Confluence page as the source of truth.

## Notes

- If critical information is missing, ask clarifying questions before generating
- Adapt section depth based on available details
- For highly technical products, emphasize architecture and technical stack
- For user-facing products, emphasize user stories and experience
- This skill contains the complete PRD template structure - no external references needed
- Re-running with the same epic key is safe. It updates the existing page and does not duplicate the epic
  comment. Every rerun that changes the page goes through Step 5 again.
- Never call `createConfluencePage` or `updateConfluencePage` for a PRD before Step 5 has passed. The exceptions are
  creating the empty "Product Requirements" parent page and the `PRD reviews` page (Step 6b), which runs after it.

