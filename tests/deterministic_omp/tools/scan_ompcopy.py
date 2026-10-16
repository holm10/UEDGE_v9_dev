"""Coverage of the OmpCopy* copy of +threadprivate state before the OpenMP Jacobian loop (AIUE-50).

Static scan. For every `+threadprivate` variable declared in a `.v` file it reports

* where it is declared (`<pkg>/<pkg>.v:<line>`, group, Forthon type, dynamic or fixed),
* whether the generated Forthon module carries `!$omp threadprivate(<name>)`,
* whether the generated `OmpCopy<pkg>` module copies it (`OmpCopyPointer<name>` called from
  `OmpCopyPointer<pkg>`, or an assignment in `OmpCopyScalar<pkg>`), and the size guard that can skip the copy,
* whether `OMPJacBuilder` (`ppp/omp_parallel.F90`) calls that package's `OmpCopy*` routines at all, and whether
  the variable is also in the parallel loop's `copyin` clause.

The `OmpCopy*` modules are generated at build time by Forthon `--omp` into `build/temp.*/<pkg>_p.F90`, so the scan
needs a built OpenMP source tree.

Usage:
    python -I scan_ompcopy.py --src <tree> [--build <tree>/build/temp.*] [--md out.md] [--csv out.csv]
                              [--emit-checker out.F90]

    --src    source tree holding <pkg>/<pkg>.v and ppp/omp_parallel.F90 (e.g. the AIUE-50 worktree)
    --build  directory holding the generated <pkg>_p.F90 (default: the first <src>/build/temp.* found)
    --emit-checker  also write a free-form Fortran file with `subroutine OMPCheckThreadprivateCopy(tag)`, which
             compares every worker thread's copy of every threadprivate variable bit for bit with the master's
             copy and prints the mismatches. It is meant for scratch builds only (procedure: "How to reproduce" in
             the AIUE-8 RCA, Confluence "RCA AIUE-8 (5/5): Shared-state scan (AIUE-50)"): append it to
             ppp/omp_parallel.F90 in a scratch tree and call it from OMPJacBuilder.

Exit status 0. The table goes to stdout unless --md is given.
"""
import argparse
import csv
import glob
import os
import re
import sys

PKGS = ["bbb", "com", "api", "aph", "ppp", "flx", "grd", "svr", "wdf", "ncl"]
NAME_RE = re.compile(r"^([A-Za-z_]\w*)")


def parse_v(path, pkg):
    """Return list of dicts for +threadprivate variables in a .v file."""
    out = []
    group = None
    with open(path, errors="replace") as f:
        for lineno, line in enumerate(f, 1):
            if line.startswith("*****"):
                m = re.match(r"\*+\s*(\w+)", line)
                group = m.group(1) if m else None
                continue
            code = line.split("#", 1)[0]
            if "+threadprivate" not in code:
                continue
            m = NAME_RE.match(code)
            if not m:
                continue
            name = m.group(1)
            rest = code[m.end():]
            dims = ""
            if rest.startswith("("):
                depth = 0
                for i, ch in enumerate(rest):
                    depth += ch == "("
                    depth -= ch == ")"
                    if depth == 0:
                        dims = rest[: i + 1]
                        rest = rest[i + 1:]
                        break
            toks = rest.split()
            vtype = toks[0] if toks else "?"
            out.append({
                "pkg": pkg, "group": group, "name": name, "vline": f"{pkg}/{pkg}.v:{lineno}",
                "vtype": vtype, "dynamic": vtype.startswith("_"), "dims": dims,
            })
    return out


def parse_generated(path):
    """Parse a generated <pkg>_p.F90: threadprivate directives, OmpCopy routines, declarations."""
    txt = open(path, errors="replace").read()
    lines = txt.splitlines()
    tp = set(m.lower() for m in re.findall(r"^!\$omp threadprivate\((\w+)\)", txt, re.M | re.I))
    # declarations inside modules: module <Group> ... end module
    decl = {}
    mod = None
    for ln in lines:
        mm = re.match(r"^\s*module\s+(\w+)\s*$", ln, re.I)
        if mm:
            mod = mm.group(1)
            continue
        if re.match(r"^\s*end\s+module", ln, re.I) or re.match(r"^\s*contains", ln, re.I):
            mod = None
            continue
        if mod and "::" in ln and not ln.lstrip().startswith("!"):
            typ, names = ln.split("::", 1)
            for nm in re.findall(r"(\w+)\s*(\([^)]*\))?\s*(?:=[^,]*)?(?:,|$)", names):
                if nm[0]:
                    decl.setdefault(nm[0].lower(), {"module": mod, "decl": ln.strip(), "pointer": "pointer" in typ.lower()})
    # OmpCopy module
    copy_ptr = {}
    m = re.search(r"^module OmpCopy(\w+)\s*$(.*?)^end module OmpCopy\1", txt, re.M | re.S)
    called = set()
    scalars = {}
    if m:
        body = m.group(2)
        for sm in re.finditer(r"^subroutine OmpCopyPointer(\w+)\s*$(.*?)^end subroutine OmpCopyPointer\1", body, re.M | re.S):
            name, sub = sm.group(1), sm.group(2)
            if name == m.group(1):
                called = set(c.lower() for c in re.findall(r"^call OmpCopyPointer(\w+)", sub, re.M))
                continue
            # only the size guard (".le.size(var)"); fixed-size arrays have none, and "if (tid.gt.0) then" is not one
            guard = re.search(r"^if \((.*\.le\.size\(\w+\))\) then\s*$", sub, re.M)
            dtype = re.search(r"^\s*(\w+\(kind=\d+\))::\w+copy(\([^)]*\))", sub, re.M)
            uses = re.findall(r"^\s*use (\w+)", sub, re.M)
            copy_ptr[name.lower()] = {
                "guard": guard.group(1) if guard else "",
                "ftype": dtype.group(1) if dtype else "?",
                "cdims": dtype.group(2) if dtype else "",
                "uses": uses,
            }
        sc = re.search(r"^subroutine OmpCopyScalar\w+\s*$(.*?)^end subroutine", body, re.M | re.S)
        if sc:
            sub = sc.group(1)
            uses = re.findall(r"^\s*use (\w+)", sub, re.M)
            types = dict((n.lower(), t) for t, n in re.findall(r"^\s*(\w+\(kind=\d+\))::(\w+)copy\s*$", sub, re.M))
            for n in re.findall(r"^(\w+)=\1copy\s*$", sub, re.M):
                scalars[n.lower()] = {"ftype": types.get(n.lower(), "?"), "uses": uses}
    return {"tp": tp, "decl": decl, "copy_ptr": copy_ptr, "called": called, "scalars": scalars}


def parse_builder(src):
    path = os.path.join(src, "ppp", "omp_parallel.F90")
    txt = open(path).read()
    m = re.search(r"SUBROUTINE OMPJacBuilder(.*?)END SUBROUTINE OMPJacBuilder", txt, re.S)
    body = m.group(1) if m else ""
    calls = re.findall(r"call (OmpCopy(?:Pointer|Scalar)(\w+))", body)
    copied_pkgs = {"pointer": set(), "scalar": set()}
    for full, pkg in calls:
        copied_pkgs["pointer" if "Pointer" in full else "scalar"].add(pkg.lower())
    cin = set()
    for c in re.findall(r"copyin\(([^)]*)\)", body, re.I):
        cin |= set(x.strip().lower() for x in c.split(","))
    start = txt[: m.start()].count("\n") + 1 if m else 0
    return copied_pkgs, cin, start


def copy_order(src):
    """Line number of each OmpCopyPointer<pkg>/OmpCopyScalar<pkg> call inside OMPJacBuilder."""
    txt = open(os.path.join(src, "ppp", "omp_parallel.F90")).read()
    m = re.search(r"SUBROUTINE OMPJacBuilder(.*?)END SUBROUTINE OMPJacBuilder", txt, re.S)
    order = {}
    for i, ln in enumerate((m.group(1) if m else "").splitlines()):
        c = re.match(r"\s*call OmpCopy(Pointer|Scalar)(\w+)", ln)
        if c:
            order.setdefault((c.group(1).lower(), c.group(2).lower()), i)
    return order


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--build")
    ap.add_argument("--md")
    ap.add_argument("--csv")
    ap.add_argument("--emit-checker")
    a = ap.parse_args(argv)
    build = a.build or (sorted(glob.glob(os.path.join(a.src, "build", "temp.*"))) or [None])[0]
    if not build:
        sys.exit("no build/temp.* directory; pass --build")
    copied_pkgs, cin, bline = parse_builder(a.src)
    rows = []
    gen = {}
    for pkg in PKGS:
        v = os.path.join(a.src, pkg, f"{pkg}.v")
        if not os.path.exists(v):
            continue
        g = os.path.join(build, f"{pkg}_p.F90")
        gen[pkg] = parse_generated(g) if os.path.exists(g) else None
        for var in parse_v(v, pkg):
            G = gen[pkg]
            n = var["name"].lower()
            directive = bool(G and n in G["tp"])
            if G and n in G["copy_ptr"]:
                how = "OmpCopyPointer"
                inlist = n in G["called"]
                guard = G["copy_ptr"][n]["guard"]
            elif G and n in G["scalars"]:
                how, inlist, guard = "OmpCopyScalar", True, ""
            else:
                how, inlist, guard = "none", False, ""
            kind = "scalar" if how == "OmpCopyScalar" else ("dynamic array" if var["dynamic"] else "fixed array")
            if how == "none":
                kind = "dynamic array" if var["dynamic"] else ("array" if var["dims"] else "scalar")
            pkg_called = pkg in (copied_pkgs["pointer"] if how == "OmpCopyPointer" else copied_pkgs["scalar"])
            copied = how != "none" and inlist and pkg_called
            rows.append(dict(var, kind=kind, directive=directive, how=how, guard=guard,
                             pkg_called=pkg_called, copied=copied, copyin=n in cin))
    # order hazard: an array copy whose section bounds use threadprivate scalars. OmpCopyPointer<var> evaluates the
    # bounds on the master to fill the buffer, but on each worker with the WORKER's copy of those scalars. If
    # OmpCopyPointer<pkg> runs before OmpCopyScalar<pkg> (as in OMPJacBuilder), a worker still holding the DATA
    # default of a dimension scalar copies only part of the array.
    tp_scalars = {}
    for r in rows:
        if r["how"] == "OmpCopyScalar":
            tp_scalars.setdefault(r["pkg"], set()).add(r["name"].lower())
    order = copy_order(a.src)
    for r in rows:
        r["hazard"] = ""
        if r["how"] == "OmpCopyPointer" and gen.get(r["pkg"]):
            ids = set(re.findall(r"[a-z_]\w*", gen[r["pkg"]]["copy_ptr"][r["name"].lower()]["cdims"].lower()))
            used = sorted(ids & tp_scalars.get(r["pkg"], set()))
            if used:
                late = order.get(("scalar", r["pkg"]), 1e9) > order.get(("pointer", r["pkg"]), -1)
                r["hazard"] = ("ORDER HAZARD: " if late else "bounds use ") + ",".join(used)
    nh = sum(r["hazard"].startswith("ORDER") for r in rows)
    # report
    hdr = ["variable", "declared", "group", "kind", "threadprivate directive", "copy routine",
           "package copy called in OMPJacBuilder", "copied", "size guard", "copyin", "copy-order hazard"]
    table = [[r["name"], r["vline"], r["group"], r["kind"], "yes" if r["directive"] else "NO", r["how"],
              "yes" if r["pkg_called"] else "NO", "yes" if r["copied"] else "NO", r["guard"],
              "yes" if r["copyin"] else "", r["hazard"]] for r in rows]
    summary = []
    for pkg in PKGS:
        pr = [r for r in rows if r["pkg"] == pkg]
        if pr:
            summary.append(f"{pkg}: {len(pr)} threadprivate, {sum(r['copied'] for r in pr)} copied, "
                           f"{sum(not r['copied'] for r in pr)} NOT copied, "
                           f"{sum(not r['directive'] for r in pr)} without directive, "
                           f"{sum(bool(r['guard']) for r in pr)} behind a size guard")
    summary.append(f"{nh} array copies whose section bounds use threadprivate scalars that are copied only AFTER "
                   f"the arrays (OmpCopyPointer<pkg> called before OmpCopyScalar<pkg>): "
                   f"{', '.join(r['pkg'] + '.' + r['name'] for r in rows if r['hazard'].startswith('ORDER'))}")
    summary.append(f"OMPJacBuilder (ppp/omp_parallel.F90:{bline}) calls OmpCopyPointer for "
                   f"{sorted(copied_pkgs['pointer'])} and OmpCopyScalar for {sorted(copied_pkgs['scalar'])}; "
                   f"copyin({', '.join(sorted(cin))})")
    md = ["# OmpCopy coverage", "", f"Source: `{a.src}`, generated code: `{build}`", ""]
    md += [f"- {s}" for s in summary] + [""]
    md.append("| " + " | ".join(hdr) + " |")
    md.append("|" + "---|" * len(hdr))
    md += ["| " + " | ".join(str(c).replace("|", "\\|") for c in row) + " |" for row in table]
    text = "\n".join(md) + "\n"
    if a.md:
        open(a.md, "w").write(text)
        print("\n".join(summary))
    else:
        print(text)
    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(hdr)
            w.writerows(table)
    if a.emit_checker:
        emit_checker(a.emit_checker, rows, gen)


def emit_checker(path, rows, gen):
    """Write OMPCheckThreadprivateCopy: bitwise worker-vs-master comparison of every threadprivate variable."""
    subs = []
    calls = []
    for r in rows:
        if r["how"] == "none" or gen.get(r["pkg"]) is None:
            continue
        G = gen[r["pkg"]]
        n = r["name"]
        if r["how"] == "OmpCopyPointer":
            info = G["copy_ptr"][n.lower()]
            uses = info["uses"]
            ftype = info["ftype"]
            ptr = G["decl"].get(n.lower(), {}).get("pointer", False)
        else:
            info = G["scalars"][n.lower()]
            ftype = info["ftype"]
            uses = info["uses"]
            ptr = False
        base = ftype.split("(")[0].lower()
        if base not in ("real", "integer", "logical"):
            continue
        sname = f"tpchk_{r['pkg']}_{n}"[:63]
        is_array = r["how"] == "OmpCopyPointer"
        assoc = f"associated({n})" if ptr else ".true."
        sz = f"size({n})" if is_array else "1"
        cp = "tpchk_bits" if is_array else "tpchk_bits1"
        sub = f"""subroutine {sname}(tag, ntot)
{chr(10).join('  use ' + u for u in uses)}
  use omp_lib
  implicit none
  character(len=*), intent(in) :: tag
  integer, intent(inout) :: ntot
  integer(kind=8), allocatable :: mb(:), wb(:)
  integer :: n, tid, nb, ifirst, i
  logical :: masc
  n = -1
  masc = {assoc}
  if (masc) n = {sz}
  if (n > 0) then
    allocate(mb(n))
    call {cp}_{base}({n}, n, mb)
  endif
!$omp parallel default(shared) private(tid, nb, ifirst, i, wb)
  tid = omp_get_thread_num()
  if (tid > 0) then
    if (masc .neqv. ({assoc})) then
!$omp critical (tpchk_out)
      write(*,'(a,a,a,i3,a,l2)') 'TPCHK ', tag, ' {r['pkg']}.{n} tid=', tid, ' association differs, worker associated=', .not.masc
      ntot = ntot + 1
!$omp end critical (tpchk_out)
    elseif (n > 0) then
      if ({sz} .ne. n) then
!$omp critical (tpchk_out)
        write(*,'(a,a,a,i3,a,i10,a,i10)') 'TPCHK ', tag, ' {r['pkg']}.{n} tid=', tid, ' size worker=', {sz}, ' master=', n
        ntot = ntot + 1
!$omp end critical (tpchk_out)
      else
        allocate(wb(n))
        call {cp}_{base}({n}, n, wb)
        nb = 0
        ifirst = 0
        do i = 1, n
          if (wb(i) .ne. mb(i)) then
            nb = nb + 1
            if (ifirst == 0) ifirst = i
          endif
        enddo
        if (nb > 0) then
!$omp critical (tpchk_out)
          write(*,'(a,a,a,i3,a,i10,a,i10,a,i10,a,z17,a,z17)') 'TPCHK ', tag, ' {r['pkg']}.{n} tid=', tid, &
               ' nbad=', nb, ' of ', n, ' first=', ifirst, ' worker=', wb(ifirst), ' master=', mb(ifirst)
          ntot = ntot + 1
!$omp end critical (tpchk_out)
        endif
        deallocate(wb)
      endif
    endif
  endif
!$omp end parallel
  if (allocated(mb)) deallocate(mb)
end subroutine {sname}
"""
        subs.append(sub)
        calls.append(f"  call {sname}(tag, ntot)")
    helpers = ""
    for base, ft in (("real", "real(kind=8)"), ("integer", "integer(kind=8)"), ("logical", "logical(kind=8)")):
        helpers += f"""subroutine tpchk_bits_{base}(a, n, b)
  implicit none
  integer, intent(in) :: n
  {ft}, intent(in) :: a(n)
  integer(kind=8), intent(out) :: b(n)
  b = transfer(a, b)
end subroutine tpchk_bits_{base}
subroutine tpchk_bits1_{base}(a, n, b)
  implicit none
  integer, intent(in) :: n
  {ft}, intent(in) :: a
  integer(kind=8), intent(out) :: b(n)
  b(1) = transfer(a, b(1))
end subroutine tpchk_bits1_{base}
"""
    driver = f"""subroutine OMPCheckThreadprivateCopy(tag)
  implicit none
  character(len=*), intent(in) :: tag
  integer :: ntot
  ntot = 0
{chr(10).join(calls)}
  write(*,'(a,a,a,i6,a,i6,a)') 'TPCHK ', tag, ' done: ', ntot, ' mismatching (variable,thread) pairs over ', {len(calls)}, ' variables'
end subroutine OMPCheckThreadprivateCopy
"""
    with open(path, "w") as f:
        f.write("! Generated by tests/deterministic_omp/tools/scan_ompcopy.py --emit-checker. Scratch builds only.\n")
        f.write(helpers + "\n".join(subs) + driver)
    print(f"wrote {path}: {len(calls)} variables")


if __name__ == "__main__":
    main(sys.argv[1:])
