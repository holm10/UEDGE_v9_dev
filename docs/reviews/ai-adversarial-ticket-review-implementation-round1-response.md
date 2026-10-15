# Response to ai-adversarial-ticket-review implementation round 1 (REVISE)

Fixed in commit 4e191a7 on `feature/v9-ai-adversarial-ticket-review`.

| Finding | Response |
|---|---|
| I1-M1 commit rule contradicts other skills / the run | Fixed. Step 3b now defines "done" as a fresh reviewer's APPROVE on the final `<base>...HEAD` diff; commit-as-you-go (code, then code-facts) is allowed and matches `execute`/`commit`. The `WIP:` prefix is removed (escalated work stays on the branch, ticket kept In Progress). Final Summary has a "Ticket Escalated" variant; push/PR only when approved and the user asks. |
| I1-M2 no fallback when the agent can't spawn a reviewer | Fixed. "Who reviews" paragraph: never self-review; if no reviewer can be spawned, stop after validation and return the work state, validation output and a ready reviewer prompt to the caller, who runs the loop and decides who applies fixes (itself or the resumed implementer); the fixer re-validates. |
| I1-M3 no run budget / unreproducible criteria | Fixed. The prompt must carry a run budget (venvs, scratch builds, time limit) and the list of criteria not reproducible in the reviewer's environment. `uedge-reviewer.md` replaces "tell the main session before long runs" with "stay within the budget", and adds a "Not independently verified (environment)" category and report section; those criteria go to the PR/ticket for the owner. |
| I1-M4 edits after APPROVE unreviewed | Fixed. Loop step 3: only typo/documentation-level fixes after APPROVE skip a round; any code, test, data or behaviour change needs a new round on the changed diff. |
| I1-M5 implement-fix / manual path ungated | Fixed. `implement-fix` gains §4c (implementation round, plus a plan round for `pandf`/`ppp`/Jacobian/`.v` fixes); `execute` gains step 6; `plan-feature` gains an "Adversarial plan review" section; CLAUDE.md's refactor and bug rows name the gates. All reference one loop in `end-to-end-feature/SKILL.md`. |
| I1-m1 relative report path | Fixed: absolute `<worktree>/docs/reviews/...` path in the prompt; reviewer agent writes to the path given. |
| I1-m2 no response files | Fixed: `docs/reviews/<KEY>-<stage>-round<N>-response.md` (this file follows that convention). |
| I1-m3 P prefix clash | Fixed: `L` for plan rounds, `I` for implementation rounds, documented in the agent's ID examples. |
| I1-m4 trigger list / re-validate at plan stage / plan flaw found later | Fixed: Step 2b and CLAUDE.md list the same triggers; plan stage says there is no re-validation; loop step 4 covers implementation findings that show the plan is wrong. |
| I1-m5 stacking on a parent in review | Fixed: "Stacking" paragraph (allowed; rebase and re-validate the child when the parent changes). |
| I1-m6 argument-hint / where acceptance criteria come from | Fixed: `[ticket-key or feature-description]`; "Ticket input" paragraph (Jira issue, or `git show feature/v9-<EPIC>-planning:docs/specs/<file>`). |
| I1-m7 docs/reviews blocked on AI branch | Acknowledged: the round reports and this response are kept on `feature/v9-AIUE-8-planning` (`docs/reviews/`), the epic whose unattended run prompted the change. |
