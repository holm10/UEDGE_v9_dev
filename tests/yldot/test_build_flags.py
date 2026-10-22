"""The opt-in build options leave the default flags unchanged (PRD section 8; AIUE-85, AIUE-105, AIUE-125).

--noopt and --coverage are results-neutral and opt-in: neither may change the flags of the default, --serial,
--debug or --checkbounds builds, and --coverage changes only its own build. tools/build_flags.py evaluates
setup.py's flag assembly per option set on Linux and macOS without building; EXPECTED is that table on v9-develop
(7c02d8d), checked against setup.py and, for darwin:serial, against a real pip install -v log. An intended flag
change updates EXPECTED, with the reason in the PR. The negative control edits a copy of setup.py seven ways and
requires the check to see each edit.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parent / "tools" / "build_flags.py"
SETUP = Path(__file__).resolve().parents[2] / "setup.py"

BASE = "-g -fmax-errors=15 -DFORTHON -cpp -Wconversion -fimplicit-none"
DEBUG = ("-fbacktrace -ffree-line-length-0 -fcheck=all -fbounds-check -ffpe-trap=invalid,overflow,underflow "
         "-finit-real=snan -Og")
BOUNDS = "-fbounds-check -fcheck=all"
# The same in every build: make's environment otherwise differs from the caller's only in NOCLEAN, and setup.py
# adds nothing to the compiler's own uedgeC compile arguments (no readline macro: the tool's readline probe fails).
COMMON = {"make_env": {"NOCLEAN": "FALSE"}, "uedgec_compile": ["<fcompiler>"],
          "uedgec_macros": [["WITH_NUMERIC", "0"], ["FORTHON_PKGNAME", '"uedgeC"'], ["FORTHON", "1"]],
          "make_calls": 2}


def omp(fargs, ldflags):
    """An OpenMP build: -fopenmp on the Fortran and C compiles and the uedgeC link, Forthon's --omp."""
    return {"fargs": fargs, "cargs": "-fopenmp", "ompflags": "--omp", "ldflags": ldflags, "omp_env": "TRUE",
            "uedgec_link": ["-fopenmp", "-g", "-DFORTHON", "<fcompiler>"], **COMMON}


def serial(fargs, ldflags=None):
    """A serial build: no OpenMP flag anywhere (AIUE-109)."""
    return {"fargs": fargs, "cargs": None, "ompflags": "", "ldflags": ldflags, "omp_env": "FALSE",
            "uedgec_link": ["-g", "-DFORTHON", "<fcompiler>"], **COMMON}


REFUSED = {"noopt+debug": {"exit": "--noopt cannot be combined with --debug"},
           "coverage+debug": {"exit": "--coverage cannot be combined with --debug"}}


def platform_table(platform, omp_ldflags, coverage_ldflags):
    cases = {
        "default": omp(BASE + " -fopenmp -O3", omp_ldflags),
        "serial": serial(BASE + " -O3"),
        "debug": omp(BASE + " -fopenmp " + DEBUG, omp_ldflags),
        "checkbounds": omp(BASE + " -fopenmp -O3 " + BOUNDS, omp_ldflags),
        "noopt": omp(BASE + " -fopenmp -O0", omp_ldflags),
        "coverage": serial(BASE + " -O0 --coverage", coverage_ldflags),
        "serial+debug": serial(BASE + " " + DEBUG),
        "serial+checkbounds": serial(BASE + " -O3 " + BOUNDS),
        "serial+noopt": serial(BASE + " -O0"),
        "noopt+checkbounds": omp(BASE + " -fopenmp -O0 " + BOUNDS, omp_ldflags),
        **REFUSED,
    }
    return {"{}:{}".format(platform, name): record for name, record in cases.items()}


# Linux links the Forthon extensions with LDFLAGS=-fopenmp (AIUE-64) and a coverage build with --coverage; macOS
# leaves LDFLAGS alone except for GCC's libgcov.a in a coverage build (AIUE-105).
EXPECTED = {
    **platform_table("linux", "-fopenmp", "--coverage"),
    **platform_table("darwin", None, "<libgcov.a>"),
    "linux:default@-L/preset": omp(BASE + " -fopenmp -O3", "-L/preset -fopenmp"),
    "linux:default@-fopenmp -L/preset": omp(BASE + " -fopenmp -O3", "-fopenmp -L/preset"),
    "linux:coverage@-L/preset": serial(BASE + " -O0 --coverage", "-L/preset --coverage"),
}


def flag_table(setup_path, cwd):
    """The tool's table for setup_path, from a child interpreter (it swaps process-wide state while it runs)."""
    proc = subprocess.run([sys.executable, "-I", str(TOOL), "--setup", str(setup_path), "--json"], cwd=cwd,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def differences(table):
    lines = []
    for name in sorted(set(EXPECTED) | set(table)):
        want, got = EXPECTED.get(name), table.get(name)
        if want is None or got is None:
            lines.append("{}: {}".format(name, "not expected" if want is None else "missing"))
            continue
        for field in sorted(set(want) | set(got)):
            if want.get(field) != got.get(field):
                lines.append("{} {}: {!r} -> {!r}".format(name, field, want.get(field), got.get(field)))
    return lines


@pytest.fixture(scope="module")
def table(tmp_path_factory):
    return flag_table(SETUP, tmp_path_factory.mktemp("build_flags"))


def test_flags_unchanged(table):
    assert len(EXPECTED) == 27
    lines = differences(table)
    assert not lines, ("setup.py's build flags changed (an intended change updates EXPECTED in this file, with the "
                       "reason in the PR):\n" + "\n".join(lines))


def test_coverage_only_its_own_build(table):
    for name, record in table.items():
        if "coverage" not in name.split(":")[1]:
            text = json.dumps(record)
            assert "--coverage" not in text and "libgcov" not in text, name
    for platform in ("linux", "darwin"):
        cov, ser = table[platform + ":coverage"], table[platform + ":serial"]
        assert cov["fargs"] == ser["fargs"].replace(" -O3", " -O0 --coverage")
        assert {k: v for k, v in cov.items() if k not in ("fargs", "ldflags")} == \
            {k: v for k, v in ser.items() if k not in ("fargs", "ldflags")}


# (edit to setup.py, a case it must change); each edit's text must occur exactly once
EDITS = {
    "default -O3": ("'FARGSOPT': ['-O3'],", "'FARGSOPT': ['-O2'],", "linux:default"),
    "-Wconversion": ("        '-Wconversion',\n", "", "darwin:serial"),
    "Linux OpenMP LDFLAGS": ("ldflags = (ldflags + ' -fopenmp').strip()", "ldflags = (ldflags + ' -lgomp').strip()",
                             "linux:default"),
    "--noopt flags": ("FLAGS['FARGSOPT'] = ['-O0']\n", "FLAGS['FARGSOPT'] = ['-O0', '-g3']\n", "linux:noopt"),
    "--coverage on by default": ("'coverage': False,", "'coverage': True,", "darwin:default"),
    "make environment": ('            os.environ["OMP"] = "TRUE"\n',
                         '            os.environ["OMP"] = "TRUE"\n            os.environ["FFLAGS"] = "-O0"\n',
                         "linux:default"),
    "uedgeC compile": ("extra_compile_args=fcompiler.extra_compile_args",
                       "extra_compile_args=fcompiler.extra_compile_args + ['-O0']", "darwin:serial"),
}


@pytest.mark.parametrize("edit", list(EDITS))
def test_detects_flag_changes(edit, tmp_path):
    old, new, case = EDITS[edit]
    source = SETUP.read_text()
    assert source.count(old) == 1, "edit {!r} no longer matches setup.py exactly once; update EDITS".format(edit)
    edited = tmp_path / "setup.py"
    edited.write_text(source.replace(old, new))
    lines = differences(flag_table(edited, tmp_path))
    assert any(line.startswith(case + " ") for line in lines), "edit {!r} not detected in {}".format(edit, case)
