"""The opt-in build options leave the default flags unchanged (PRD section 8; AIUE-85, AIUE-105, AIUE-125), and every
build records them (AIUE-181).

--noopt and --coverage are results-neutral and opt-in: neither may change the flags of the default, --serial,
--debug or --checkbounds builds, and --coverage changes only its own build. tools/build_flags.py evaluates
setup.py's flag assembly per option set on Linux and macOS without building; EXPECTED is that table on v9-develop
(7c02d8d), checked against setup.py and, for darwin:serial, against a real pip install -v log. An intended flag
change updates EXPECTED, with the reason in the PR. Each case also holds the build record setup.py writes into
the installed package (uedge/_build_info.json, AIUE-181): its options, the same flags, and the tool's fixed compiler
and git answers. The negative control edits a copy of setup.py nine ways (seven flag changes, the record dropped,
the record without its platform) and requires the check to see each edit; an unedited copy must show none, and a
source tree without .git records no commit. test_installed_record checks the record of the UEDGE installed in this
interpreter against its own options.
"""
import json
import os
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


# The build record's fields that come from the tool's stubs (tools/build_flags.py: FakeFCompiler, GIT)
FAKE_RECORD = {"forthon_fopt": "-fake-fopt", "fcompiler": "fake-gfortran", "fcompiler_version": "fake-gfortran 1.0",
               "machine": "<machine>"}
FAKE_GIT = {"git_sha": "0" * 40, "git_branch": "fake-branch", "git_commit_date_iso": "2026-01-01T00:00:00+00:00",
            "git_dirty": False}
NO_GIT = {"git_sha": None, "git_branch": None, "git_commit_date_iso": None, "git_dirty": None}
OPTIONS = ("checkbounds", "coverage", "debug", "noclean", "noopt", "serial")


def with_info(name, record):
    """record with the build record setup.py writes for case name (AIUE-181): the options of the name (a coverage
    build is serial), the flags of the same record and the tool's fixed answers. A refused case writes none."""
    if "exit" in record:
        return record
    platform, rest = name.split(":", 1)
    chosen = set(rest.split("@")[0].split("+")) - {"default"}
    options = {o: o in chosen for o in OPTIONS}
    options["serial"] = options["serial"] or options["coverage"]
    info = {"schema": 1, "options": options, "fargs": record["fargs"], "cargs": record["cargs"],
            "ompflags": record["ompflags"], "ldflags": record["ldflags"], "platform": platform, **FAKE_RECORD,
            **FAKE_GIT}
    return {**record, "build_info": info}


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
EXPECTED = {name: with_info(name, record) for name, record in {
    **platform_table("linux", "-fopenmp", "--coverage"),
    **platform_table("darwin", None, "<libgcov.a>"),
    "linux:default@-L/preset": omp(BASE + " -fopenmp -O3", "-L/preset -fopenmp"),
    "linux:default@-fopenmp -L/preset": omp(BASE + " -fopenmp -O3", "-fopenmp -L/preset"),
    "linux:coverage@-L/preset": serial(BASE + " -O0 --coverage", "-L/preset --coverage"),
}.items()}


def flag_table(setup_path, cwd, *extra):
    """The tool's table for setup_path, from a child interpreter (it swaps process-wide state while it runs)."""
    proc = subprocess.run([sys.executable, "-I", str(TOOL), "--setup", str(setup_path), "--json", *extra], cwd=cwd,
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
        assert {k: v for k, v in cov.items() if k not in ("fargs", "ldflags", "build_info")} == \
            {k: v for k, v in ser.items() if k not in ("fargs", "ldflags", "build_info")}


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
    "build record dropped": (
        "        # Record how this build was compiled, for the installed package (AIUE-181; read by _provenance.py and "
        "AIUE-96)\n"
        "        infopath = os.path.join(self.build_lib, 'uedge', '_build_info.json')\n"
        "        with open(infopath, 'w') as f:\n"
        "            json.dump(build_info(makeenv), f, indent=1, sort_keys=True)\n", "", "linux:default"),
    "record drops platform": ("        'platform': platform,\n", "", "darwin:serial"),
}


def conversion(setup_path, cwd):
    """The tool's --conversion record for setup_path, from a child interpreter."""
    proc = subprocess.run([sys.executable, "-I", str(TOOL), "--setup", str(setup_path), "--conversion"], cwd=cwd,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


# setup.py before AIUE-163: the conversion returned to $PWD, not to the working directory
OLD_CONVERSION = (("        from os import getcwd, mkdir, chdir\n", "        from os import getenv, mkdir, chdir\n"),
                  ("        curpath = getcwd()\n", '        curpath = getenv("PWD")\n'))


def test_conversion_follows_the_working_directory(tmp_path):
    """With the working directory A and $PWD naming B (a build launched with subprocess cwd=A, or `pip install A` run
    from B), setup.py converts A's sources and stays in A (AIUE-163)."""
    assert conversion(SETUP, tmp_path) == {"cwd_after": "A", "converted_in": ["A"]}


def test_conversion_check_detects_the_old_code(tmp_path):
    """Negative control: the same check on setup.py with the pre-AIUE-163 lines restored sees B."""
    source = SETUP.read_text()
    for new, old in OLD_CONVERSION:
        assert source.count(new) == 1, "{!r} no longer matches setup.py exactly once; update OLD_CONVERSION".format(new)
        source = source.replace(new, old)
    edited = tmp_path / "setup.py"
    edited.write_text(source)
    assert conversion(edited, tmp_path) == {"cwd_after": "B", "converted_in": ["B"]}


def test_copy_location_does_not_matter(tmp_path):
    """The negative control below evaluates copies of setup.py in tmp_path, outside any repository: an unedited copy
    gives the table unchanged (the tool's SRCDIR, not the copy's directory, decides the record's git fields), so each
    edit's difference comes from the edit."""
    copy = tmp_path / "setup.py"
    copy.write_text(SETUP.read_text())
    assert differences(flag_table(copy, tmp_path)) == []


def test_record_without_git(tmp_path):
    """A source tree without .git (a git archive) records no commit, and nothing else changes (AIUE-181)."""
    table = flag_table(SETUP, tmp_path, "--no-git")
    record = table["linux:default"]["build_info"]
    assert {k: record[k] for k in NO_GIT} == NO_GIT
    assert {k: v for k, v in record.items() if k not in NO_GIT} == \
        {k: v for k, v in EXPECTED["linux:default"]["build_info"].items() if k not in NO_GIT}


# Run in a child from a scratch directory: the build record and _provenance.py of the UEDGE installed in this
# interpreter, found without importing uedge (no Forthon extensions, ~/.uedgerc.py or banner)
INSTALLED = r"""
import importlib.util, json, sys
from pathlib import Path
spec = importlib.util.find_spec("uedge")
if spec is None:
    print(json.dumps({"missing": "uedge (not installed)"}))
    sys.exit(0)
pkg = Path(spec.submodule_search_locations[0])
path = pkg / "_build_info.json"
if not path.is_file():
    print(json.dumps({"missing": str(pkg)}))
    sys.exit(0)
prov_spec = importlib.util.spec_from_file_location("uedge_provenance", pkg / "_provenance.py")
prov = importlib.util.module_from_spec(prov_spec)
sys.modules["uedge_provenance"] = prov  # dataclasses looks the module up while it makes the class
prov_spec.loader.exec_module(prov)
print(json.dumps({"record": json.loads(path.read_text()), "git_commit": prov.get_uedge_provenance().git_commit}))
"""


def test_installed_record(tmp_path):
    """The installed UEDGE records its build (AIUE-181), and the record agrees with its own options: the last -O of
    the Fortran flags, -fopenmp exactly in an OpenMP build (in fargs and in Forthon's own flags, which are never the
    debug -g: make never passes Forthon -g), this platform and machine, and the commit _provenance.py reports. A
    UEDGE built before AIUE-181 fails here, naming the cause (no skip)."""
    proc = subprocess.run([sys.executable, "-I", "-c", INSTALLED], cwd=tmp_path, capture_output=True, text=True,
                          timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert "missing" not in out, "no _build_info.json in {}: the installed UEDGE was built before AIUE-181".format(
        out.get("missing"))
    record = out["record"]
    options, fargs = record["options"], record["fargs"].split()
    assert record["schema"] == 1
    levels = [a for a in fargs if a.startswith("-O")]
    want = "-O0" if options["noopt"] or options["coverage"] else "-Og" if options["debug"] else "-O3"
    assert levels and levels[-1] == want, (options, record["fargs"])
    assert ("-fopenmp" in fargs) == (not options["serial"]), (options, record["fargs"])
    fopt = (record["forthon_fopt"] or "").split()
    assert any(a.startswith("-O") for a in fopt) and "-g" not in fopt, record["forthon_fopt"]
    assert ("-fopenmp" in fopt) == (not options["serial"]), (options, record["forthon_fopt"])
    assert record["fcompiler"]
    assert record["platform"] == sys.platform
    assert record["machine"] == os.uname().machine
    assert out["git_commit"] == record["git_sha"]


@pytest.mark.parametrize("edit", list(EDITS))
def test_detects_flag_changes(edit, tmp_path):
    old, new, case = EDITS[edit]
    source = SETUP.read_text()
    assert source.count(old) == 1, "edit {!r} no longer matches setup.py exactly once; update EDITS".format(edit)
    edited = tmp_path / "setup.py"
    edited.write_text(source.replace(old, new))
    lines = differences(flag_table(edited, tmp_path))
    assert any(line.startswith(case + " ") for line in lines), "edit {!r} not detected in {}".format(edit, case)
