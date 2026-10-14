# Variables & Forthon `.v` files

Every Fortran module variable and every Python-callable routine is declared in `<pkg>/<pkg>.v`. Forthon generates
the Fortran modules (one per `***** Group:`) and the Python bindings (`bbb.<var>`, `bbb.<routine>()`).

## File structure (`bbb/bbb.v`)

```
bbb                                  # package name, line 1
{                                    # compile-time parameters (also #define'd in bbb/bbb.h — keep in sync)
nispmx = 31  # maximum number of ion species
}
***** UEpar:                         # group → Fortran module UEpar, used as Use(UEpar)
#  free comment lines
name   type  [units]  /default/  +attrs  # doc string (shown in Python help)
```

`com.v`'s dims (`nx`, `ny`, `nisp`, `ngsp`, `nxpt` …) are available to `bbb.v` via `--macros com/com.v`
(`Makefile.Forthon:28`).

## Declaration forms (real examples)

| Kind | Example | Ref |
|---|---|---|
| Scalar input w/ default | `isteon integer /1/ +input #user:turns on (=1) electron energy eqn.` | `bbb/bbb.v:222` |
| Fixed-size array | `isnion(nispmx) integer /nispmx*1/ +input #...` | `bbb/bbb.v:217` |
| Coefficient | `cfneut real /1./ +input #Coef for fluid neutrals contrib's to resid's` | `bbb/bbb.v:279` |
| Dynamic array (note `_`) | `ni(0:nx+1,0:ny+1,1:nisp) _real [m^-3] +threadprivate #ion density...` | `bbb/bbb.v:1628` |
| Dynamic, computed | `isnionxy(0:nx+1,0:ny+1,nisp) _integer #calc:=1 for ni eqn on` | `bbb/bbb.v:236` |
| Subroutine | `convsr_vo(i,j,yl:real) subroutine` (+ `# in i` arg doc lines) | `bbb/bbb.v:3362` |
| Function | `ebindz(za:integer, zn:integer) real function` | `bbb/bbb.v:3568` |

Routines live in `***** Subs:` (`bbb/bbb.v:3353`). Untyped args default to integer; annotate reals `x:real`.

## Attributes in use (count in `bbb.v`)

`+input` (843) user-settable switch/parameter · `+threadprivate` (522) per-thread copy for OpenMP ·
`+maybeinput` (108) · `+mcinput` (33) MC-neutrals inputs · `+work`, `+hyd`, `+solver`, `+neut`, `+setup` (rare).
Extra words in a group header become an attribute on every variable in that group (Forthon `interfaceparser.py`; only `hidden` is special-cased).
Seven `bbb` groups carry `restart`: `Model_choice`, `Coefeq`, `Bcond`, `Err_msg_out`, `Comtra`, `Variable_perturbation`, `Jacobian_clipping` (`bbb/bbb.v:268,272,419,1126,1325,3300,3307`).
Nothing in UEDGE's Python or in Forthon reads this attribute (Forthon's `pydump` selects on `dump`), so it is inert in the Python build. Put new input variables in these groups as usual; the tag has no effect.

## Adding a variable — checklist

1. Put it in the group whose routines use it (search `Use(Group)` sites). New group only for a coherent new model.
2. Units in `[...]`, default in `/.../`, doc after `#`. Mark switches `+input`.
3. Pick a default that reproduces existing behaviour (e.g. `cf* = 0.` for a new term, `is*on = 0` for a new model), unless the change is an intended physics change to the defaults. In that case, document it in the PR (see CLAUDE.md hard rules).
4. If it is written anywhere inside the `pandf` call tree → `+threadprivate` (see `openmp-jacobian.md`).
5. Dynamic arrays (`_real`) are allocated by `call gchange("Group",0)` — make sure the group is (re)allocated in
   `odesetup.m` after dims are known (`bbb/odesetup.m:87` pattern).
6. If it must be saved/restored, add to the save list in `src/uedge/hdf5.py` (`hdf5_save` `varlist`, `:82`).
7. Parameters in `{}` must be mirrored in `<pkg>.h` `#define`s (`bbb/bbb.h`).
