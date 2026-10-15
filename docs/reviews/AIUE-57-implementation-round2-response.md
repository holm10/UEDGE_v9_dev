# Response to AIUE-57 implementation round 2 (APPROVE, 0/0/2 minor)

README wording only after APPROVE.

| Finding | Response |
|---|---|
| R2-m1 budget upper end understated; nightly omits `all1` | Fixed: "about 13–21 min (central ~17)" for the PR job; nightly about 90–110 min within the 150-min timeout. |
| R2-m2 `FIRST MISMATCH` not always printed | Fixed: README says when it is left out and that the job is still red. |
