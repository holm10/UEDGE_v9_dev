# Response to AIUE-58 implementation round 2 (APPROVE, 0/0/3)

Applied by the main session as requested text fixes:
- I2-m1: the post-`ueinit` residual is stated as values observed at given states (5.5e-9, 8.1e-9), not a fixed bound;
  the reviewer's round-2 run (block moved, 2194 rows; final `ueinit` 791 rows ≤ 8.1e-9) is added to the evidence
  table; a note says the `reexmain` control includes the column loop, so AIUE-59 must show the refresh alone removes
  the residual.
- I2-m2: option B marked superseded.
- I2-m3: the two trial folders stay uncommitted.
