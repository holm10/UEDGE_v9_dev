"""Input inventory of the yldot suite (PRD section 7.2): every variable of every */*.v interface file, with its
package, type, shape, group and dynamic flag, and whether it is tagged +input or +maybeinput.

The files are read with Forthon's own parser (Forthon.interfaceparser.processfile), the one the build uses, so the
inventory cannot disagree with what Forthon builds. A line grep can: '#' and '$' start comments that run to the end
of the line, and a '+attr' on a continuation line attaches to the variable named last (bbb/bbb.v:384 and :1430).

Keys are package-qualified ('bbb.isphion', 'com.iprint'). uedge is never imported here.
"""
import functools
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PACKAGES = ("com", "aph", "bbb", "api", "flx", "grd", "svr", "wdf", "ppp", "ncl")  # DIRLIST, Makefile.Forthon:6
MACROS = {"bbb": ["com"], "ppp": ["com", "bbb"], "svr": ["bbb"]}  # the --macros of Makefile.Forthon:28,32,44
INPUT_TAGS = ("input", "maybeinput")


@dataclass(frozen=True)
class Var:
    key: str
    package: str
    name: str
    type: str  # real, integer, character, ...
    dims: str  # the dimension string as written, spaces removed; '' for a scalar
    dynamic: bool  # _real/_integer: allocated by gchange
    group: str
    attrs: tuple
    tagged: bool  # +input or +maybeinput


def _parser():
    """Forthon.interfaceparser, imported with a harmless argv: importing Forthon parses sys.argv and, with a single
    entry, prints its usage and exits (Forthon_options.py:112-123)."""
    argv = sys.argv
    sys.argv = ["yldot-inputs", "dummypkg"]
    try:
        from Forthon import interfaceparser
    finally:
        sys.argv = argv
    return interfaceparser


@functools.lru_cache(maxsize=None)
def parse(repo=REPO):
    """{key: Var} for every variable of every package, hidden ones included."""
    repo = Path(repo)
    ip = _parser()
    out = {}
    for pkg in PACKAGES:
        vfile = repo / pkg / "{}.v".format(pkg)
        if not vfile.is_file():
            continue
        macros = [str(repo / m / "{}.v".format(m)) for m in MACROS.get(pkg, [])]
        vlist, hidden, _ = ip.processfile(pkg, str(vfile), macros, 0)
        for v in vlist + hidden:
            key = "{}.{}".format(pkg, v.name)
            if key in out:
                raise ValueError("{}: declared twice in {}".format(key, vfile))
            attrs = tuple(v.attr.split())
            out[key] = Var(key=key, package=pkg, name=v.name, type=v.type, dims=v.dimstring.replace(" ", ""),
                           dynamic=bool(v.dynamic), group=v.group, attrs=attrs,
                           tagged=any(t in attrs for t in INPUT_TAGS))
    return out


def tagged(repo=REPO):
    """{key: Var} of the +input/+maybeinput variables."""
    return {k: v for k, v in parse(repo).items() if v.tagged}


def summary(repo=REPO):
    t = tagged(repo).values()
    by_package = {}
    for v in t:
        by_package[v.package] = by_package.get(v.package, 0) + 1
    return {"tagged": len(t), "by_package": by_package, "dynamic": sum(v.dynamic for v in t),
            "character": sum(v.type == "character" for v in t)}
