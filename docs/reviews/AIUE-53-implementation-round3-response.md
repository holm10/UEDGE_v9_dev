# Response to AIUE-53 implementation round 3 (APPROVE, 0/0/1 minor)

| Finding | Response |
|---|---|
| I3-m1 `is_stale` compares only the HEAD commit time (misses a tree moved back after the build; flags docs-only commits) | Deferred, not changed after APPROVE: the case needs the documented "don't touch the tree until the check is done" rule to be broken, and the docs-only flag is conservative (never a false AGREE). Suggested follow-up: compare the newest mtime of tracked build inputs (`*.m`, `*.v`, `*.F90`, `setup.py`, `Makefile.Forthon`) with `extensions_mtime`. |
