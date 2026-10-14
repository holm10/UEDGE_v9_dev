# Python layer (`src/uedge/`)

## Conventions observed

- Access Fortran state through package objects: `from uedge import bbb, com` (`src/uedge/hdf5.py:2`).
  Generic var lookup uses Forthon: `from Forthon import package, packageobject` (`src/uedge/hdf5.py:11`).
- Classes are `Ue<Thing>` (`UeRun`, `src/uedge/rundt.py:17`; `UeBalance`, `src/uedge/balance.py:5`) with a thin
  function wrapper (`rundt(**kwargs)`, `:1300`; `checkbal()`, `:1363`).
- User messages via `print`; failures via `raise Exception("...")` (`src/uedge/hdf5.py:27,70`). No logging module.
- Imports frequently local to functions (heavy optional deps like matplotlib/scipy are in the `ueplot` extra,
  `pyproject.toml` `[project.optional-dependencies]`).
- Version is single-sourced from `src/uedge/VERSION` (`pyproject.toml` `[tool.setuptools.dynamic]`,
  `src/uedge/__init__.py:54-56`).
- No type hints, no formatter. Match the surrounding file.

## Save/restore

`hdf5_save(file, varlist=[...])` / `hdf5_restore(file)` (`src/uedge/hdf5.py:82,14`) handle three formats:
flat old-style, UETOOLS-style, and `uedge.hdf5` groups. Restored values land in the `*s` arrays (`nis`, `tes`, …).

## Packaging

`pyproject.toml` maps `uedge` → `src/uedge`, `uedge.rates` → `rates/`; package data `*.dat`. CLI scripts:
`pyscripts/pdb2hdf5`, `bas2py`, `hdf52pdb`.
