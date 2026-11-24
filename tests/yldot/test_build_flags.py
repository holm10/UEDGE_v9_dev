"""The opt-in build options leave the default flags unchanged (PRD section 8; AIUE-85, AIUE-105, AIUE-125), and every
build records them (AIUE-181).

--noopt and --coverage are results-neutral and opt-in: neither may change the flags of the default, --serial,
--debug or --checkbounds builds, and --coverage changes only its own build. tools/build_flags.py evaluates
setup.py's flag assembly per option set on Linux and macOS without building; EXPECTED is that table on v9-develop
(7c02d8d), checked against setup.py and, for darwin:serial, against a real pip install -v log, plus AIUE-211's
Linux flags. An intended flag change updates EXPECTED, with the reason in the PR. Each case also holds the build record setup.py writes into
the installed package (uedge/_build_info.json, AIUE-181): its options, the same flags, and the tool's fixed compiler
and git answers. The negative control edits a copy of setup.py ten ways (eight flag changes, the record dropped,
the record without its platform) and requires the check to see each edit; an unedited copy must show none, and a
source tree without .git records no commit. NOCLEAN_EXPECTED is what each --noclean build must do in a tree that an
earlier build left (T27: clean if its objects are another build's), with STAMP_EDITS as its negative control.
test_installed_record checks the record of the UEDGE installed in this
interpreter against its own options, and test_installed_no_vector_math its Linux extensions for libmvec calls
(AIUE-211).
"""
import importlib.util
import json
import os
import shutil
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
# Every Linux build keeps exp, log, pow, sin and cos scalar: no glibc math-vector-fortran.h pre-include, so no
# libmvec calls, whose results depend on the CPU vendor (AIUE-211). <finclude>: the tool's stand-in for the
# compiler's intrinsic module directory
LINUX = " -nostdinc -fintrinsic-modules-path <finclude>"
# The same in every build: make's environment otherwise differs from the caller's only in NOCLEAN, and setup.py
# adds nothing to the compiler's own uedgeC compile arguments (no readline macro: the tool's readline probe fails).
COMMON = {"make_env": {"NOCLEAN": "FALSE"}, "uedgec_compile": ["<fcompiler>"],
          "uedgec_macros": [["WITH_NUMERIC", "0"], ["FORTHON_PKGNAME", '"uedgeC"'], ["FORTHON", "1"]],
          "make_calls": 2, "clean_noclean": "FALSE"}


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
    tail = LINUX if platform == "linux" else ""
    cases = {
        "default": omp(BASE + " -fopenmp -O3" + tail, omp_ldflags),
        # A fresh tree, so it cleans: make clean sees NOCLEAN=FALSE, make still TRUE (T27)
        "noclean": {**omp(BASE + " -fopenmp -O3" + tail, omp_ldflags), "make_env": {"NOCLEAN": "TRUE"}},
        "serial": serial(BASE + " -O3" + tail),
        "debug": omp(BASE + " -fopenmp " + DEBUG + tail, omp_ldflags),
        "checkbounds": omp(BASE + " -fopenmp -O3 " + BOUNDS + tail, omp_ldflags),
        "noopt": omp(BASE + " -fopenmp -O0" + tail, omp_ldflags),
        "coverage": serial(BASE + " -O0 --coverage" + tail, coverage_ldflags),
        "serial+debug": serial(BASE + " " + DEBUG + tail),
        "serial+checkbounds": serial(BASE + " -O3 " + BOUNDS + tail),
        "serial+noopt": serial(BASE + " -O0" + tail),
        "noopt+checkbounds": omp(BASE + " -fopenmp -O0 " + BOUNDS + tail, omp_ldflags),
        **REFUSED,
    }
    return {"{}:{}".format(platform, name): record for name, record in cases.items()}


# Linux links the Forthon extensions with LDFLAGS=-fopenmp (AIUE-64) and a coverage build with --coverage; macOS
# leaves LDFLAGS alone except for GCC's libgcov.a in a coverage build (AIUE-105).
EXPECTED = {name: with_info(name, record) for name, record in {
    **platform_table("linux", "-fopenmp", "--coverage"),
    **platform_table("darwin", None, "<libgcov.a>"),
    "linux:default@-L/preset": omp(BASE + " -fopenmp -O3" + LINUX, "-L/preset -fopenmp"),
    "linux:default@-fopenmp -L/preset": omp(BASE + " -fopenmp -O3" + LINUX, "-fopenmp -L/preset"),
    "linux:coverage@-L/preset": serial(BASE + " -O0 --coverage" + LINUX, "-L/preset --coverage"),
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
    assert len(EXPECTED) == 29
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
    "Linux math calls vectorized again": (
        "            FLAGS['FARGS'] = FLAGS['FARGS'] + ['-nostdinc', '-fintrinsic-modules-path ' + finclude]\n", "",
        "linux:serial"),
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


@pytest.mark.parametrize("answer", ["finclude", "/no/such/finclude", "with space", None])
def test_finclude_refusal(answer, tmp_path):
    """A Linux build stops with AIUE-211's message when the compiler gives no usable intrinsic module directory (a
    relative path, a missing directory, a path with a space, or a failing lookup: a compiler that is not GCC's
    driver); macOS builds don't ask and are unchanged."""
    if answer == "with space":
        answer = str(tmp_path / "a b")
        Path(answer).mkdir()
    extra = ("--finclude-fails",) if answer is None else ("--finclude", answer)
    table = flag_table(SETUP, tmp_path, *extra)
    for name, record in table.items():
        if name.startswith("darwin:"):
            assert record == EXPECTED[name], name
        elif name.split(":", 1)[1] in REFUSED:
            assert record == EXPECTED[name], name
        else:
            assert "AIUE-211" in record.get("exit", ""), (name, record)


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
    # Linux only: the math calls stay scalar (AIUE-211)
    assert ("-nostdinc" in fargs) == record["platform"].startswith("linux"), (record["platform"], record["fargs"])


def test_installed_no_vector_math():
    """No extension of the installed UEDGE calls glibc's vector math library libmvec (_ZGV* symbols): its 2-lane log
    uses rcpps, whose bits differ between Intel and AMD, so the results would follow the CPU vendor (AIUE-210,
    AIUE-211). Forthon still names -lmvec on the link line, and only --as-needed drops it, so the symbols are
    counted, not the libraries. Runs on every platform, as the suite never skips (PRD section 7.6): libmvec is glibc's,
    so off Linux the count is 0 by construction, read with that platform's nm (-u: Mach-O has no dynamic table to
    ask for); a missing nm fails."""
    nm = shutil.which("nm")
    assert nm, "nm is needed to check the installed UEDGE for libmvec calls"
    undefined = ["-D", "--undefined-only"] if sys.platform.startswith("linux") else ["-u"]
    spec = importlib.util.find_spec("uedge")  # found without importing uedge
    assert spec is not None and spec.submodule_search_locations, "uedge is not installed"
    pkg = Path(spec.submodule_search_locations[0])
    extensions = sorted(set(pkg.glob("*.so")) | set(pkg.parent.glob("uedge*.so")))
    assert extensions, "no extension modules next to {}".format(pkg)
    found = {}
    for so in extensions:
        proc = subprocess.run([nm, *undefined, str(so)], capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stderr
        symbols = sorted({line.split()[-1] for line in proc.stdout.splitlines() if "_ZGV" in line})
        if symbols:
            found[so.name] = symbols
    assert not found, "the installed UEDGE calls libmvec (rebuild with AIUE-211's setup.py): {}".format(found)


@pytest.mark.parametrize("edit", list(EDITS))
def test_detects_flag_changes(edit, tmp_path):
    old, new, case = EDITS[edit]
    source = SETUP.read_text()
    assert source.count(old) == 1, "edit {!r} no longer matches setup.py exactly once; update EDITS".format(edit)
    edited = tmp_path / "setup.py"
    edited.write_text(source.replace(old, new))
    lines = differences(flag_table(edited, tmp_path))
    assert any(line.startswith(case + " ") for line in lines), "edit {!r} not detected in {}".format(edit, case)


# ---- --noclean (T27)

NO_RECORD = "no usable record of the previous build (build/.uedge_build_stamp.json)"
# The environment variables a --noclean build must compare, apart from OMP (uedgeBuild.run sets it from --serial) and
# CC (it names the C compiler too): the test's own list, not the tool's or setup.py's
VARIABLES = ["CPP", "CFLAGS", "CPPFLAGS", "LDFLAGS", "LDSHARED", "AR", "ARFLAGS", "RANLIB", "ARCHFLAGS", "MACHTYPE",
             "MACOSX_DEPLOYMENT_TARGET", "SDKROOT", "DEVELOPER_DIR", "CPATH", "C_INCLUDE_PATH", "LIBRARY_PATH",
             "GCC_EXEC_PREFIX", "COMPILER_PATH", "FCOMP", "READLINE", "PACT_DIR", "PETSC_DIR", "PARALLEL"]


def normal(**changes):
    """The step record of a build without --noclean: it cleans, says nothing, and leaves a stamp."""
    return {"cleaned": True, "header": False, "notes": [], "noclean": {"clean": "FALSE", "make": "FALSE"},
            "stamp": True, "built": True, "exit": None, **changes}


def reused(**changes):
    """A --noclean build that keeps the tree: no make clean, no note."""
    return {**normal(), "cleaned": False, "noclean": {"make": "TRUE"}, **changes}


def forced(*notes, **changes):
    """A --noclean build that cleans, naming why: make clean gets NOCLEAN=FALSE, make the build's own TRUE."""
    return {**normal(), "header": True, "notes": list(notes), "noclean": {"clean": "FALSE", "make": "TRUE"}, **changes}


STOPPED = {"noclean": {"clean": "FALSE"}, "stamp": None, "built": False, "exit": "Pre-UEDGE build clean failure"}
FAILED = {"built": False, "exit": "UEDGE build failure"}


def noclean_expected(platform):
    # A change between a serial (or coverage) and an OpenMP build; on Linux the LDFLAGS that make gets change too
    parallel = ["OMP", "cargs", "fargs", "ompflags"]
    serial_switch = (["LDFLAGS"] if platform == "linux" else []) + parallel
    expected = {
        "fresh tree": [forced(NO_RECORD), reused()],
        "normal build first": [normal(), reused()],
        "normal build with other options": [normal(), normal()],
        "variable outside the list": [normal(), reused()],
        "OMP alone": [normal(), reused()],
        "serial to OpenMP": [normal(), forced(*serial_switch), forced(*serial_switch)],
        # Linux: make gets -fopenmp in LDFLAGS either way
        "LDFLAGS=-fopenmp": [normal(), reused() if platform == "linux" else forced("LDFLAGS")],
        "Fortran compiler version": [normal(), forced("fcompiler_version")],
        "C compiler version": [normal(), forced("ccompiler_version")],
        "CC": [normal(), forced("CC", "ccompiler", "ccompiler_version"), reused(), forced("ccompiler_version")],
        "C compiler with arguments": [normal(), forced("CC", "ccompiler"), reused(), forced("ccompiler_version")],
        "Forthon's flags": [normal(), forced("forthon_fopt")],
        "Fortran compiler": [normal(), forced("fcompiler")],
        # The objects a failed or interrupted make leaves are its stamp's
        "other options fail, then the first": [normal(), forced("fargs", **FAILED), forced("fargs")],
        "other options fail, then again": [normal(), forced("fargs", **FAILED), reused()],
        "same options fail, then again": [normal(), reused(**FAILED), reused()],
        "make interrupted, then again": [normal(), reused(built=False, exit="interrupted"), reused()],
        "build.run fails, then again": [normal(), reused(exit="build.run failure"), reused()],
        # ... but the .F file of an interrupted conversion may be half written
        "a .v file edited while make runs": [normal(), reused(), forced("bbb/x.v"), reused()],
        "conversion interrupted, then again": [
            normal(), reused(noclean={}, stamp=None, built=False, exit="interrupted"), forced("bbb/x.F")],
        "converted, then again": [normal(), reused(), reused()],
        # A forced clean that does not clean stops the build and leaves no stamp
        "clean leaves build/": [normal(), forced("fargs", **STOPPED), forced(NO_RECORD)],
        "clean leaves a .F file": [normal(), forced("fargs", **STOPPED), forced(NO_RECORD)],
        "clean leaves another package's .F file": [normal(), forced("fargs", **STOPPED), forced(NO_RECORD)],
        "clean leaves a file deep in build/": [normal(), forced("fargs", **STOPPED), forced(NO_RECORD)],
        "clean fails": [normal(), forced("fargs", cleaned=False, **STOPPED), forced(NO_RECORD)],
        "clean removes all and fails": [normal(), forced("fargs", **STOPPED), forced(NO_RECORD)],
        "clean interrupted": [normal(), forced("fargs", cleaned=False, **{**STOPPED, "exit": "interrupted"}),
                              forced(NO_RECORD)],
        "clean leaves an empty build/": [normal(), forced("fargs"), reused()],
        # A normal build goes on over what its clean left, as it always has; a later --noclean build doesn't trust it
        "normal build, clean leaves build/": [normal(), normal(stamp=False), forced(NO_RECORD)],
        "normal build, clean leaves a .F file": [normal(), normal(stamp=False), forced(NO_RECORD)],
        "normal build, clean leaves the stamp": [normal(), normal(), forced("bbb/x.F")],
        "normal build, clean leaves an empty build/": [normal(), normal(), reused()],
        "normal build, clean leaves a file deep in build/": [normal(), normal(stamp=False), forced(NO_RECORD)],
        # A normal build removes the stamp before its clean too
        "normal build, clean fails": [normal(), normal(cleaned=False, **STOPPED), forced(NO_RECORD)],
        "normal build, clean interrupted": [normal(), normal(cleaned=False, **{**STOPPED, "exit": "interrupted"}),
                                            forced(NO_RECORD)],
        "--noopt": [normal(), forced("fargs")],
        "--checkbounds": [normal(), forced("fargs")],
        "--debug": [normal(), forced("fargs")],
        "--serial": [normal(), forced(*serial_switch)],
        "--coverage": [normal(), forced("LDFLAGS", *parallel)],
        # Outputs newer than the end of the last build are another build's
        "before: an object": [normal(), forced("build/temp/bbb/oderhs.o"), reused()],
        "before: an extension": [normal(), forced("build/lib/uedge/bbbpy.so"), reused()],
        "before: a .F file": [normal(), forced("bbb/x.F"), reused()],
        "before: an object of the stamp's time": [normal(), reused(), reused()],
        "before: another file": [normal(), reused(), reused()],
        "before: a .F90 file": [normal(), reused(), reused()],
        # The .v and .h files count by content (an edit here keeps the size): make recompiles no Fortran for them
        "before: a .v file edited": [normal(), forced("bbb/x.v"), reused()],
        "before: a .v file added": [normal(), forced("bbb/new.v"), reused()],
        "before: a .v file removed": [normal(), forced("bbb/x.v"), reused()],
        "before: a .h file edited": [normal(), forced("bbb/x.h"), reused()],
        "before: a top-level .h file edited": [normal(), forced("x.h"), reused()],
        "before: a .v file touched": [normal(), reused(), reused()],
        "before: another source edited": [normal(), reused(), reused()],
        "before: another package's .v file edited": [normal(), forced("com/x.v"), reused()],
        "before: another package's .h file edited": [normal(), forced("com/x.h"), reused()],
        "before: another package's .F file": [normal(), forced("com/x.F"), reused()],
        "before: a .h file added": [normal(), forced("com/new.h"), reused()],
        # ... and so do the .inc files
        "before: an .inc file edited": [normal(), forced("ncl/pamx_mi.inc"), reused()],
        "before: another package's .inc file edited": [normal(), forced("bbb/x.inc"), reused()],
        "before: an .inc file added": [normal(), forced("ncl/new.inc"), reused()],
        "before: an .inc file removed": [normal(), forced("ncl/pamx_mi.inc"), reused()],
        "before: an .inc file touched": [normal(), reused(), reused()],
        # One that cannot be opened counts as absent, and the hashing does not stop the build
        "before: a dangling .h link": [normal(), reused(), reused()],
        "before: a .v directory": [normal(), reused(), reused()],
        "before: a looping .inc link": [normal(), reused(), reused()],
        "before: a .h file made a dangling link": [normal(), forced("bbb/x.h"), reused()],
        "normal build, a dangling .h link": [normal(), reused()],
        "normal build, a .v directory": [normal(), reused()],
        "normal build, a looping .inc link": [normal(), reused()],
        "a dangling .h link gets its target": [normal(), forced("com/new.h"), reused()],
    }
    for name in VARIABLES:
        expected["variable " + name] = [normal(), forced(name)]
    for stamp in ("deleted", "empty", "not JSON", "a list", "without env", "without files"):
        expected["before: stamp " + stamp] = [normal(), forced(NO_RECORD), reused()]
    return expected


NOCLEAN_EXPECTED = {platform: noclean_expected(platform) for platform in ("linux", "darwin")}


def noclean_table(setup_path, cwd):
    """The tool's --noclean records for setup_path, from a child interpreter. A run that fails or lacks a scenario is an
    error: two crashes would compare equal."""
    proc = subprocess.run([sys.executable, "-I", str(TOOL), "--setup", str(setup_path), "--noclean"], cwd=cwd,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    table = json.loads(proc.stdout)
    assert {p: sorted(t) for p, t in table.items()} == {p: sorted(t) for p, t in NOCLEAN_EXPECTED.items()}
    for platform, expected in NOCLEAN_EXPECTED.items():
        assert {n: len(t) for n, t in table[platform].items()} == {n: len(t) for n, t in expected.items()}
    return table


def noclean_differences(table):
    """(platform, scenario, the differing step and its fields) for each scenario that differs from NOCLEAN_EXPECTED."""
    found = []
    for platform, expected in NOCLEAN_EXPECTED.items():
        for name, steps in expected.items():
            lines = ["step {} {}: {!r} -> {!r}".format(i, field, want.get(field), got.get(field))
                     for i, (want, got) in enumerate(zip(steps, table[platform][name]))
                     for field in sorted(set(want) | set(got)) if want.get(field) != got.get(field)]
            if lines:
                found.append((platform, name, "; ".join(lines)))
    return found


def test_noclean_scenarios(tmp_path):
    """A --noclean build cleans, naming why, if the tree's objects are not this build's: built with other options,
    compilers or environment, from other .v, .h or .inc files, by an older setup.py, by make alone or by an interrupted
    build, or of unknown origin. Otherwise it keeps them. A normal build cleans as it always has (T27)."""
    found = noclean_differences(noclean_table(SETUP, tmp_path))
    assert not found, "\n".join("{} {}: {}".format(*f) for f in found)


TOUCH = "        finally:\n            if stamped:\n                os.utime(STAMP)"
STOP = "if status != 0 or (left and changes):"
UNREADABLE = "except OSError:  # a dangling link, a directory, unreadable"
BUILD_RUN = "            build.run(self)\n        finally:\n"
# (text in setup.py, occurring exactly once; what replaces it; a scenario it must change, and on linux only for "linux")
STAMP_EDITS = {
    "the clean inherits NOCLEAN": ("env={**os.environ, 'NOCLEAN': 'FALSE'}", "env=dict(os.environ)", "fresh tree"),
    "stamp not removed before the clean": ("                remove(STAMP)\n", "                pass\n", "clean fails"),
    "empty stamp written": ("json.dump(stamp, f", "json.dump({}, f", "fresh tree"),
    "stamp never touched": ("                os.utime(STAMP)", "                pass", "fresh tree"),
    "stamp touched only after a success": (
        TOUCH, "        except ZeroDivisionError:\n            pass\n        else:\n            if stamped:\n"
        "                os.utime(STAMP)", "same options fail, then again"),
    "stamp touched after an interrupted conversion": (
        "        mppl2f90()\n", "        try:\n            mppl2f90()\n        finally:\n            if stamped:\n"
        "                os.utime(STAMP)\n", "conversion interrupted, then again"),
    "stamp touched if it exists": (TOUCH, TOUCH.replace("if stamped:", "if os.path.exists(STAMP):"),
                                   "normal build, clean leaves the stamp"),
    "stamp touched before build.run": (BUILD_RUN, "            if stamped:\n                os.utime(STAMP)\n"
                                     "                stamped = False\n" + BUILD_RUN, "fresh tree"),
    "build.run dropped": (BUILD_RUN, "        finally:\n", "fresh tree"),
    "file times ignored": ("    if later:\n", "    if False:\n", "before: an object"),
    "objects ignored": ("('*.o', '*.so')", "('*.so',)", "before: an object"),
    "extensions ignored": ("('*.o', '*.so')", "('*.o',)", "before: an extension"),
    ".F files ignored": ("return sorted(objects + [f for f in converted if os.path.exists(f)])",
                         "return sorted(objects)", "before: a .F file"),
    "equal times count as newer": ("st_mtime_ns > end", "st_mtime_ns >= end", "before: an object of the stamp's time"),
    "nothing compared": ("stamp_changes(stamp) if arglist['noclean'] else []", "[]", "--noopt"),
    "note in a normal build": ("stamp_changes(stamp) if arglist['noclean'] else []", "stamp_changes(stamp)",
                               "normal build first"),
    "note's header dropped": (
        '            print("--noclean: cleaning anyway, the build tree does not match this build:")\n', "", "--noopt"),
    "SDKROOT dropped": ("'SDKROOT', ", "", "variable SDKROOT"),
    "missing stamp accepted": ("        return ['no usable record of the previous build ({})'.format(STAMP)]",
                               "        return []", "before: stamp deleted"),
    "Linux make environment ignored": ("stamp = build_stamp(makeenv)", "stamp = build_stamp(None)", "linux"),
    "Forthon's flags dropped": ("'ompflags', 'forthon_fopt', ", "'ompflags', ", "Forthon's flags"),
    "Fortran compiler dropped": ("'fcompiler', 'fcompiler_version')}", "'fcompiler_version')}", "Fortran compiler"),
    "Fortran compiler version dropped": ("'fcompiler', 'fcompiler_version')}", "'fcompiler')}",
                                         "Fortran compiler version"),
    "C compiler version dropped": ("stamp['ccompiler_version'] = version.splitlines()[0] if version else None",
                                   "stamp['ccompiler_version'] = None", "C compiler version"),
    ".v files dropped": (" + glob(os.path.join('*', '*.v')):", ":", "before: a .v file edited"),
    "package headers dropped": (" + glob(os.path.join('*', '*.h'))", "", "before: a .h file edited"),
    "top-level headers dropped": ("= glob('*.h') + ", "= ", "before: a top-level .h file edited"),
    ".inc files dropped": (" + glob(os.path.join('*', '*.inc'))", "", "before: an .inc file edited"),
    ".inc files of bbb/ only": ("os.path.join('*', '*.inc')", "os.path.join('bbb', '*.inc')",
                                "before: an .inc file edited"),
    ".inc files of ncl/ only": ("os.path.join('*', '*.inc')", "os.path.join('ncl', '*.inc')",
                                "before: another package's .inc file edited"),
    ".v files of bbb/ only": ("os.path.join('*', '*.v')", "os.path.join('bbb', '*.v')",
                              "before: another package's .v file edited"),
    "headers of bbb/ only": ("os.path.join('*', '*.h')", "os.path.join('bbb', '*.h')",
                             "before: another package's .h file edited"),
    ".F files of bbb/ only": ("os.path.join('*', '*.m')", "os.path.join('bbb', '*.m')",
                              "before: another package's .F file"),
    "first line hashed only": ("sha256(source.read())", "sha256(source.readline())", "before: a .v file edited"),
    "size instead of hash": ("sha256(source.read()).hexdigest()", "len(source.read())", "before: a .v file edited"),
    "dangling link stops the build": (UNREADABLE, UNREADABLE.replace("OSError", "IsADirectoryError"),
                                      "normal build, a dangling .h link"),
    "directory stops the build": (UNREADABLE, UNREADABLE.replace("OSError", "FileNotFoundError"),
                                  "normal build, a .v directory"),
    "other unreadable file stops the build": (
        UNREADABLE, UNREADABLE.replace("OSError", "(FileNotFoundError, IsADirectoryError)"),
        "normal build, a looping .inc link"),
    "unreadable file cleans at every build": ("stamp['files'][f] = None", "stamp['files'][f] = os.urandom(8).hex()",
                                              "normal build, a dangling .h link"),
    "CC not split": ("split(stamp['ccompiler']) + ", "[stamp['ccompiler']] + ", "C compiler with arguments"),
    "stamp removed only before a forced clean": (
        "                remove(STAMP)\n", "                if changes:\n                    remove(STAMP)\n",
        "normal build, clean interrupted"),
    "files not compared": ("**s['files'], ", "", "before: a .v file edited"),
    "stamp without env accepted": ("isinstance(old.get(k), dict) for k in",
                                   "isinstance(old.setdefault(k, {}), dict) for k in", "before: stamp without env"),
    "stamp without files accepted": ("isinstance(old.get(k), dict) for k in",
                                     "isinstance(old.setdefault(k, {}), dict) for k in", "before: stamp without files"),
    "clean's leftovers ignored": (STOP, "if status != 0:", "clean leaves build/"),
    "clean's status ignored": (STOP, "if left and changes:", "clean removes all and fails"),
    "leftovers stop a normal build": (STOP, "if status != 0 or left:", "normal build, clean leaves build/"),
    "stamp over leftovers": ("stamped = not left", "stamped = True", "normal build, clean leaves build/"),
    "files left in build/ accepted": ("for d, _, names in os.walk('build') for f in names]",
                                      "for d, _, names in [] for f in names]", "clean leaves build/"),
    "files left deep in build/ accepted": ("in os.walk('build') for", "in list(os.walk('build'))[:1] for",
                                           "clean leaves a file deep in build/"),
    ".F files left outside bbb/ accepted": ("if f.endswith('.F')])", "if f == 'bbb/x.F'])",
                                            "clean leaves another package's .F file"),
    ".F files left accepted": ("sorted(files + [f for f in build_outputs() if f.endswith('.F')])", "sorted(files)",
                               "clean leaves a .F file"),
}


@pytest.mark.parametrize("edit", list(STAMP_EDITS))
def test_detects_stamp_changes(edit, tmp_path):
    """Negative control of test_noclean_scenarios: each wrong version of setup.py changes the scenario it should, on
    both platforms (Linux only for make's own environment, which macOS builds don't have)."""
    old, new, scenario = STAMP_EDITS[edit]
    source = SETUP.read_text()
    assert source.count(old) == 1, "edit {!r} no longer matches setup.py exactly once; update STAMP_EDITS".format(edit)
    edited = tmp_path / "setup.py"
    edited.write_text(source.replace(old, new))
    found = {(platform, name) for platform, name, _ in noclean_differences(noclean_table(edited, tmp_path))}
    if scenario == "linux":
        wanted = {("linux", "LDFLAGS=-fopenmp"), ("linux", "serial to OpenMP")}
    else:
        wanted = {(platform, scenario) for platform in NOCLEAN_EXPECTED}
    assert wanted <= found, "edit {!r} not detected in {}".format(edit, sorted(wanted - found))


def test_stamp_edits_of_an_unedited_copy(tmp_path):
    """The copies test_detects_stamp_changes evaluates differ only by their edit."""
    copy = tmp_path / "setup.py"
    copy.write_text(SETUP.read_text())
    assert noclean_differences(noclean_table(copy, tmp_path)) == []


def test_tool_leaves_cwd_alone(tmp_path, table):
    """The tool neither writes into the caller's directory nor reads it: a build/ there, with a stamp, changes nothing
    (setup.py keeps its stamp in build/ of the working directory, T27)."""
    planted = {"build/.uedge_build_stamp.json": "{}", "build/x.o": "x", "bbb/x.m": "", "bbb/x.F": "x"}
    for name, text in planted.items():
        (tmp_path / name).parent.mkdir(exist_ok=True)
        (tmp_path / name).write_text(text)
    assert flag_table(SETUP, tmp_path) == table
    assert noclean_differences(noclean_table(SETUP, tmp_path)) == []
    left = {str(f.relative_to(tmp_path)): f.read_text() for f in tmp_path.rglob("*") if f.is_file()}
    assert left == planted
