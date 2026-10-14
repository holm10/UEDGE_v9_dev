# Response to review round 5: AIUE-5 PRD (APPROVE)

PRD revision 7. Every round-5 point is a clarification; no design change.

| ID | Status | Where |
|---|---|---|
| P5-m1 | Fixed. The FORMAT check treats tabs as insignificant whitespace outside character/Hollerith data. The owner decision's wording now says "insignificant whitespace (blanks or tabs)", which applies the decision as intended (tabs don't affect runtime output). The owner is told about this explicitly | Decisions, §7.2 |
| P5-m2 | Fixed. The 13 unused FORMATs are compared at source level (independent extractor vs `.F90`, same whitespace rule). §11 reworded. The OpenMP-branch fact is recorded, and the check fails if a FORMAT/WRITE ever lands in an `#ifdef _OPENMP` branch | §7.2, §11 |
| P5-m3 | Fixed. The guard runs after `clean` and `mppl2f90()`, before `make`, and only fires on an `x.F` next to a tracked `x.F90`. It doesn't fire on `mppl2f90()` output for unconverted packages, normal or `--noclean` | §4, §11 |
| P4-m1 wording | Fixed. The length limit applies to the code part, excluding trailing comments | §4, §11 |
| P4-m2 wording | Fixed. Out-of-scope now allows for the uniform indentation | §4 |
