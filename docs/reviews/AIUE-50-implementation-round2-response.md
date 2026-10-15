# Response to AIUE-50 implementation round 2 (APPROVE, 0/0/2 minor)

Text-only fixes after APPROVE.

| Finding | Response |
|---|---|
| I2-m1 `com.ttimpfe` in F6 is a false positive | Fixed: removed from the F6 list, with a note that it is written only for `xc<0` and appeared through the scan's own reset call. The script's artefact is now documented in the RCA row (the script itself is unchanged). |
| I2-m2 "consecutive serial exmain" sentence conflicts with AIUE-55 | Fixed: reworded as a state change, not a history test, with a pointer to AIUE-55 P3-m3. |
| (note) five variables not sentinel-tested | Recorded here: `bbb.ishymol`, `bbb.znucl`, `com.isnonog`, `com.nhsp`, `com.nzsp` (input switches/dimensions: `pandf` aborts on a changed value; covered by the diff test). |
