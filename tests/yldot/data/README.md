# Synthetic rate files: NOT ACTUAL DATA

**Every file in this directory is synthetic. None of them holds actual atomic data. Do not use them for physics.**

The numbers come from closed formulas invented for software tests (`../tools/make_rate_files.py`), written in the layouts
that UEDGE's readers expect. The tool reads no table, and no value was taken from, fitted to or scaled to a real one. They
exist so that the tests can run every rate option without distributing real rate tables, which are not publicly shareable.

- Each file says so on its first or second line and on its last line.
- Regenerate them with `python tests/yldot/tools/make_rate_files.py write`; `check` compares the directory byte for byte.
  `tests/yldot/test_rate_files.py` runs that check, looks for the notices, refuses the known real tables anywhere in the
  repository, and reads every file back through UEDGE.
- Never put a real table here, and never fit a formula or a grid to one.
- A case run with these files need not converge. The yldot suite and the OpenMP reproducer compare one build with another;
  neither needs a converged state.

`aphread` fixes the names of the hydrogen files in the Fortran, so those keep the names of the real ones; `b2frates` and
`carbmc.dat` keep UEDGE's default names (`com.hdfilename`, `api.inelmc`). The other files, whose names the input deck chooses,
end in `.synthetic`.
