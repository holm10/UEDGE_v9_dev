# MPPL Fortran — writing `.m` source that survives conversion

`.m` files are fixed-form Fortran with MPPL extensions. They are **converted by text substitution**
(`M2F.subrules`, `setup.py:648-674`) into `.F`, then preprocessed with `-cpp`. Understand the rules — they
are not a parser.

## File skeleton (copy from `bbb/pandf_plasma_continuity.m:1-21`)

```fortran
c!include "bbb.h"
c!include "../com/com.h"
c!include "../mppl.h"
c!include "../sptodp.h"

      SUBROUTINE my_routine(xc, yc)
      IMPLICIT NONE
      integer xc, yc, ix, iy, ifld
      real tmp
      Use(Dim)          # nx, ny, nisp ...
      Use(Compla)       # ni, up, te, ti ...
      Use(Selec)        # i1..i8, j1..j8 loop ranges

c     Full-line comment: 'c' in column 1
      do iy = j2, j5
         do ix = i2, i5
            tmp = ni(ixp1(ix,iy),iy,1)   # inline comment with '#'
         enddo
      enddo
      END SUBROUTINE my_routine
```

- `Use(Group)` → `use Group` (`Use2use`, `setup.py:174`). Groups are defined in `.v` files.
- Declarations may be written before or after `Use(...)`; `MoveDecs` (`setup.py:231`) reorders them.
- Continuation: non-blank char (convention `.`) in column 6 (`bbb/pandf.m:573-575`).
- Preprocessor: `c!ifdef`/`c!else`/`c!endif`/`c!include` → `#ifdef`/… (`setup.py:651,657,658,667`).
- Conditional lines: `c!omp …` enabled only when building with OpenMP (`Omp`, `setup.py:223-229`);
  `cpetsc`/`cunipetsc` for PETSc; `c!nopdb` when no PACT.

## Substitution hazards (`setup.py:648-674`)

| Written | Becomes | Consequence |
|---|---|---|
| `#` anywhere | `!` | `#` inside a string literal or format is corrupted |
| `float`, `dfloat` (substring) | `real` | An identifier like `floatx` becomes `realx` |
| ` break ` / ` break\n` | ` exit ` | MPPL loop exit |
| `while (` / `endwhile` | `do while (` / `end do` | |
| `elseif (...)` without `then` | `then` appended (`Elseifthen`) | Still write `then` explicitly |
| `call allot("x", n)` | `allocate(x(n))` | Legacy — prefer `gchange` |
| `(Size4)` | `(kind=4)::` | |

## Errors and output

- Fatal: `call xerrab('Error in subroutine <name>: <text>')` (`Error in function <name>:` in a function), which
  returns control to the Python/BASIS prompt; do not `stop`. A number or file name that identifies the cause is
  composed in, through a plain local `character*256` buffer or a concatenated argument (`api/fimp.m:166-168`
  `mcrates`; AIUE-239, owner D3). An element of a Forthon string array (`Filename`, e.g. `mcfilename`) set from
  Python is NUL-padded, which `trim` keeps and which ends the message: cut it at `index(s//char(0), char(0)) - 1`
  first (`api/fimp.m` `readmc`; scalars are blank-padded, probed; the Python side is in `uedge-gotchas.md` → Running
  UEDGE from Python). Older stops read `'*** message ***'` (`bbb/pandf_plasma_continuity.m:29`); new
  ones use the form above.
- Never a bare `call xerrab("")`: the message is the Python `RuntimeError`'s text (Forthon `kaboom`) and a yldot
  INVALID reason. `tests/yldot/test_inventory.py` refuses a bare one outside `grd/` and `flx/`.
- Message: `call remark('...')` (`bbb/convert.m:345`). Gate chatty output on `com.iprint` (`com/com.v:709`).
- Interrupt points already exist in `pandf` (`check_kaboom`, `ruthere`, `bbb/pandf.m:548-552`); do not add more.

## Numerics conventions

- `real` is 8-byte (Forthon `--realsize 8`, gfortran `-fdefault-real-8`). Write `real`, never `real*8`/`double precision`.
- Literals: `1.`, `0.5`, `1.e-10` (no `d0` needed). `Pi` macro from `mppl.h`.
- `-fimplicit-none` and `-Wconversion` are on (`setup.py:80-87`): declare everything, watch int↔real mixing.
- Grid neighbours: `ixm1(ix,iy)` / `ixp1(ix,iy)` (handles cuts & X-points); radial neighbours `iy±1`.
- Guard cells: arrays span `0:nx+1, 0:ny+1`; interior is `1:nx, 1:ny`.

## Hand-written free-form sources

`ppp/*.F90`, `svr/petsc-uedge.F90`, `com/petscMod.F90` are free-form F90 and are **not** run through `M2F`
— use standard `USE Group, ONLY: …`, `!` comments, `&` continuation (`ppp/omp_parallel.F90:957-985`).
