"""The Forthon --omp common block /ompcommonscalarcopy/ must be defined first by bbb, and no other package's
definition may be larger (AIUE-57 CI step; a port of AIUE-60's G-common check script
`AIUE-60-common-check.py`, kept in the tag archive/AIUE-8-docs).

  python3 -I common_check.py --pkgdir SITE-PACKAGES/uedge --gen BUILD/temp.<plat>-cpython-<ver>

Forthon's OpenMP generator gives every package's OmpCopyScalar<pkg> the same `common /ompcommonscalarcopy/`. The
extensions are imported RTLD_GLOBAL in the order of src/uedge/__init__.py, so the first loaded definition of
_ompcommonscalarcopy_ serves every package; a later package with a larger block writes past its end (AIUE-60 I1-B1).

For every extension, in the import order parsed from the installed uedge/__init__.py:
  definer   does the .so define _ompcommonscalarcopy_ (macOS `nm -m`: "(__DATA,__common) external"; ELF `nm -D -S`,
            the dynamic symbol table, which a stripped .so keeps)
  size      bytes of that package's block, from GEN/<pkg>_p.F90 (the generated sources of THE SAME build): the variables
            of its `common /ompcommonscalarcopy/` statement (joined over `&` continuations), each sized from its
            declaration `<type>(kind=K)::<name>` in the same routine
PASS: the first definer is bbb, and every other definer's size <= bbb's. FAIL otherwise. A definer whose size can't be
determined, a missing .so, an `nm` failure, no definer at all (an OpenMP build always has bbb as one), a --pkgdir
without __init__.py or a --gen without bbb_p.F90 is an ERROR (fail closed). Exit 0 PASS, 1 FAIL, 2 ERROR.
Differences from the AIUE-60 script: --pkgdir (the package directory; setup-python is not a venv) instead of --venv,
and the two input checks above. The logic is unchanged.
"""
import argparse
import glob
import os
import re
import subprocess
import sys


def import_order(init_py):
    order = []
    for line in open(init_py):
        m = re.match(r"\s*from\s+\.(\w+)\s+import", line) or re.match(r"\s*from\s+\.\s+import\s+(\w+)", line)
        if m and m.group(1) not in order and (m.group(1).endswith("py") or m.group(1) == "uedgeC"):
            order.append(m.group(1))
    return order


def defines_block(so, platform=None):
    platform = platform or sys.platform
    cmd = ["nm", "-m", so] if platform == "darwin" else ["nm", "-D", "-S", so]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not res.stdout.strip():
        raise RuntimeError("{} failed or listed no symbols (exit {}): {}".format(" ".join(cmd), res.returncode,
                                                                                 res.stderr.strip()[:200]))
    if platform == "darwin":
        return any(l.endswith("_ompcommonscalarcopy_") and "external" in l and "(undefined)" not in l
                   for l in res.stdout.splitlines())
    return any(re.search(r"\s[BCDVbcdv]\s+ompcommonscalarcopy_$", l) for l in res.stdout.splitlines())


def block_size(gen_file):
    """Bytes of the package's /ompcommonscalarcopy/ statement, or None if the file has none."""
    lines = open(gen_file).read().split("\n")
    for i, line in enumerate(lines):
        if line.startswith("common /ompcommonscalarcopy/"):
            text = line[len("common /ompcommonscalarcopy/"):]
            while text.rstrip().endswith("&"):
                i += 1
                text = text.rstrip()[:-1] + lines[i]
            names = [x.strip().lower() for x in text.split(",") if x.strip()]
            src = "\n".join(lines).lower()
            total = 0
            for n in names:
                m = re.search(r"^\s*(?:real|integer|logical)\(kind=(\d+)\)\s*::\s*" + re.escape(n) + r"\s*$", src, re.M)
                if not m:
                    raise ValueError("no declaration with a kind for {} in {}".format(n, gen_file))
                total += int(m.group(1))
            return total, len(names)
    return None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pkgdir", required=True, help="the installed uedge package directory")
    p.add_argument("--gen", required=True, help="directory with the generated <pkg>_p.F90 of the same build")
    a = p.parse_args(argv)
    pkgdir = a.pkgdir
    if not os.path.isfile(os.path.join(pkgdir, "__init__.py")):
        print("ERROR: no uedge package (__init__.py) in", pkgdir)
        return 2
    if not os.path.isfile(os.path.join(a.gen, "bbb_p.F90")):
        print("ERROR: no generated bbb_p.F90 in", a.gen)
        return 2
    order = import_order(os.path.join(pkgdir, "__init__.py"))
    print("import order:", " ".join(order))
    definers, code = [], 0
    for mod in order:
        so = glob.glob(os.path.join(pkgdir, mod + ".*so"))
        if not so:
            print("ERROR: {}: no extension module".format(mod))
            return 2
        try:
            defined = defines_block(so[0])
        except RuntimeError as err:
            print("ERROR:", err)
            return 2
        if not defined:
            print("  {:<8} -".format(mod))
            continue
        pkg = mod[:-2] if mod.endswith("py") else mod
        gen = os.path.join(a.gen, pkg + "_p.F90")
        try:
            size = block_size(gen) if os.path.exists(gen) else None
        except ValueError as err:
            print("ERROR:", err)
            return 2
        if size is None:
            print("ERROR: {} defines _ompcommonscalarcopy_ but {} has no common statement (size unknown)".format(mod, gen))
            return 2
        print("  {:<8} defines the block: {} variables, {} B".format(mod, size[1], size[0]))
        definers.append((mod, size[0]))
    if not definers:
        print("RESULT: ERROR (no package defines the block: not an OpenMP build, or the symbols were not found)")
        return 2
    first, first_size = definers[0]
    problems = []
    if first != "bbbpy":
        problems.append("first definer is {} ({} B), not bbbpy".format(first, first_size))
    for mod, size in definers[1:]:
        if size > first_size:
            problems.append("{} block {} B > first definer {} {} B".format(mod, size, first, first_size))
    if problems:
        print("RESULT: FAIL: " + "; ".join(problems))
        return 1
    print("RESULT: PASS (first definer {} {} B; others {})".format(first, first_size,
                                                                ", ".join("{} {} B".format(m, s) for m, s in definers[1:]) or "none"))
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:  # fail closed: a traceback is an ERROR, never a FAIL or a PASS
        import traceback
        traceback.print_exc()
        sys.exit(2)
