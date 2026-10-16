# Response to AIUE-61 implementation round 3 (APPROVE, 0/0/1)

- I3-m1: the PR line now says any `OMPParallelPandf1=1` run on a grid with `iysptrx1<5` hits the pre-existing out-of-bounds write in `MakeXptChunks` (filed as AIUE-74 under AIUE-70), in the plan and the validation record.
- Observation (serial `pandf` reads `ng(ix,iy,2)` with one gas species, `bbb/pandf_plasma_energy.m:603/697/701`): pre-existing on v9-develop, not AIUE-61; filed as a separate bug by the main session.
