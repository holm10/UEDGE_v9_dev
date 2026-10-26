"""The compiler and link flags setup.py assembles for each build option, evaluated without building (AIUE-125).

Usage (from anywhere):
    python -I build_flags.py [--setup PATH] [--json] [--no-git]
    python -I build_flags.py [--setup PATH] --conversion

--conversion instead runs setup.py's MPPL conversion (mppl2f90, not stubbed) on two scratch trees with the working
directory and $PWD differing and prints where it converted and where it left the process, as JSON (AIUE-163:
setup.py must follow the working directory, not $PWD).

PRD section 8: the opt-in, results-neutral build options (--noopt, AIUE-85; --coverage, AIUE-105) may not change
the default flags. This tool runs setup.py (default: the one in this checkout) once per case in CASES, with the
build's side effects stubbed: Forthon's FCompiler is a fixed fake (the real Forthon is never imported: its import
parses sys.argv), setuptools.setup only records its arguments, os.system (the readline probe) returns 1, and in
uedgeBuild.run the make calls, mppl2f90, check_output and build.run are replaced. check_output answers only the
commands setup.py is known to run (the macOS libgcov lookup, the Linux finclude lookup (AIUE-211), the compiler's
--version, the git probes of the build record; anything else raises), and SRCDIR, where setup.py runs them, is a scratch directory with an empty .git file
(--no-git: without it), so a record does not depend on where the evaluated setup.py lies.
sys.argv has the shape pip gives setup.py for -C "--build-option=--<opt>": [setup.py, bdist_wheel, --dist-dir,
<dir>, --<opt>...]. platform, read by uedgeBuild.run at call time, is set per case, so both the Linux and the macOS
branches are evaluated on any host.

Each case records what reaches the build: the --fargs and --cargs strings and OMPFLAGS passed to make, the LDFLAGS
of make's environment (None: make inherits the caller's environment), the OMP environment variable, every other
variable of make's environment that differs from the caller's (PATH excepted: setup.py appends the host's
user-site bin directory), the uedgeC link and compile arguments (the compiler's own shown as <fcompiler>) and
macros, the number of make calls (clean, then the build), and the build record uedgeBuild.run writes into
<build_lib>/uedge/_build_info.json (AIUE-181; build_lib is a scratch directory): the parsed JSON, its machine shown as
<machine> and the libgcov path in its ldflags as <libgcov.a>; the finclude directory is shown as <finclude> in
both fargs; None if no record was written, "<unreadable: ...>" if
it does not parse. A refused combination records the SystemExit message instead. The comparison with the flags on
v9-develop lives in tests/yldot/test_build_flags.py.

Not covered: what setup.py passes to Forthon's real FCompiler (machine, debug, fcompname, omp) and the flags that
compiler adds, which depend on the host's compiler: the record's forthon_fopt is the fake's fixed value, so the real
one is checked only on real builds; the -g, -t and -F short options; --noclean (the tool expects
make clean, so it raises), --parallel and PETSc.

Run it in its own interpreter: every case swaps sys.argv, os.environ, setuptools.setup, os.system and
sys.modules['Forthon*'] and restores them afterwards, but setup.py is executed in this process. It needs
setuptools, which a venv of Python >= 3.12 does not have until it is installed (pip builds UEDGE in an isolated
environment of its own), and numpy (setup.py imports it).
Exit codes: 0 ok, 2 usage error, 3 setuptools missing.
"""
import argparse
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import types
from pathlib import Path

try:
    import setuptools
except ImportError:
    sys.stderr.write("build_flags.py needs setuptools in this environment: pip install setuptools\n")
    sys.exit(3)

SETUP = Path(__file__).resolve().parents[3] / "setup.py"
PLATFORMS = ["linux", "darwin"]
OPTION_SETS = [(), ("serial",), ("debug",), ("checkbounds",), ("noopt",), ("coverage",), ("serial", "debug"),
               ("serial", "checkbounds"), ("serial", "noopt"), ("noopt", "checkbounds"), ("noopt", "debug"),
               ("coverage", "debug")]
PRESET = "-L/preset"
# (platform, options, LDFLAGS in the caller's environment; None: unset)
CASES = ([(p, o, None) for p in PLATFORMS for o in OPTION_SETS]
         + [("linux", (), PRESET), ("linux", (), "-fopenmp " + PRESET), ("linux", ("coverage",), PRESET)])
LIBGCOV = "<libgcov.a>"  # stands for the path check_output returns on macOS
FINCLUDE = "<finclude>"  # stands for the intrinsic module directory check_output returns on Linux (AIUE-211)
FCOMPILER = "<fcompiler>"  # stands for an argument of the compiler's own (FakeFCompiler's) in the uedgeC lists
MACHINE = "<machine>"  # stands for the host's os.uname().machine in the build record
FAKE_VERSION = "fake-gfortran 1.0\nCopyright\n"  # what the fake compiler's --version prints
# The git probes of the build record and their fixed answers
GIT = {("rev-parse", "HEAD"): "0" * 40, ("rev-parse", "--abbrev-ref", "HEAD"): "fake-branch",
       ("show", "-s", "--format=%cI", "HEAD"): "2026-01-01T00:00:00+00:00",
       ("status", "--porcelain", "--untracked-files=no"): ""}


class FakeFCompiler:
    """Forthon.compilers.FCompiler with fixed attributes: the real one's depend on the host's compiler."""
    libdirs = ["/fake/lib"]
    libs = ["fakefortran"]
    extra_link_args = ["-fake-fc-link"]
    extra_compile_args = ["-fake-fc-compile"]
    fcompexec = "fake-gfortran"
    fopt = "-fake-fopt"

    def __init__(self, machine=None, debug=0, fcompname=None, omp=False):
        pass


def case_name(platform, options, ldflags):
    name = "{}:{}".format(platform, "+".join(options) or "default")
    return name if ldflags is None else "{}@{}".format(name, ldflags)


@contextlib.contextmanager
def stubs():
    """Forthon (a fake FCompiler), setuptools.setup (records its arguments in the dict yielded) and os.system
    (returns 1) replaced while setup.py is executed; restored afterwards."""
    saved_modules = {k: sys.modules.get(k) for k in ("Forthon", "Forthon.compilers")}
    saved_setup, saved_system = setuptools.setup, os.system
    captured = {}
    try:
        fake = types.ModuleType("Forthon.compilers")
        fake.FCompiler = FakeFCompiler
        sys.modules["Forthon"] = types.ModuleType("Forthon")
        sys.modules["Forthon.compilers"] = fake
        setuptools.setup = lambda **kw: captured.update(kw)
        os.system = lambda command: 1
        yield captured
    finally:
        setuptools.setup, os.system = saved_setup, saved_system
        for k, v in saved_modules.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def fake_check_output(libgcov, finclude):
    """subprocess.check_output for setup.py: the answers to the commands it is known to run, else RuntimeError."""
    def check_output(command, **kw):
        if command == [FakeFCompiler.fcompexec, "-print-file-name=libgcov.a"]:
            return libgcov + "\n"
        if command == [FakeFCompiler.fcompexec, "-print-file-name=finclude"]:
            return finclude + "\n"
        if command == [FakeFCompiler.fcompexec, "--version"]:
            return FAKE_VERSION
        if command[0] == "git" and tuple(command[1:]) in GIT:
            return GIT[tuple(command[1:])] + "\n"
        raise RuntimeError("build_flags.py has no answer for {}: add it deliberately".format(command))
    return check_output


def read_record(path, libgcov, finclude):
    """The build record at path as the case records it (see the module docstring)."""
    if not path.exists():
        return None
    try:
        record = json.loads(path.read_text())
    except ValueError as e:
        return "<unreadable: {}>".format(e)
    if isinstance(record, dict):
        if isinstance(record.get("machine"), str) and record["machine"]:
            record["machine"] = MACHINE
        if isinstance(record.get("ldflags"), str):
            record["ldflags"] = record["ldflags"].replace(libgcov, LIBGCOV)
        if isinstance(record.get("fargs"), str):
            record["fargs"] = record["fargs"].replace(finclude, FINCLUDE)
    return record


def evaluate(setup_path, options, platform, ldflags, libgcov, finclude, git=True):
    """Run setup_path for one case and return its record (see the module docstring)."""
    saved_argv, saved_env = list(sys.argv), dict(os.environ)
    calls = []
    try:
        with stubs() as captured, tempfile.TemporaryDirectory() as tmp:
            srcdir, build_lib = Path(tmp, "src"), Path(tmp, "build_lib")
            srcdir.mkdir()
            if git:
                (srcdir / ".git").touch()
            (build_lib / "uedge").mkdir(parents=True)
            os.environ.pop("LDFLAGS", None)
            if ldflags is not None:
                os.environ["LDFLAGS"] = ldflags
            os.environ.pop("OMP", None)
            caller_env = dict(os.environ)
            sys.argv = [str(setup_path), "bdist_wheel", "--dist-dir", "dist"] + ["--" + o for o in options]

            def fake_call(command, env=None):
                seen = dict(os.environ if env is None else env)
                other = {k: seen.get(k) for k in set(seen) | set(caller_env)
                         if seen.get(k) != caller_env.get(k) and k not in ("PATH", "LDFLAGS", "OMP")}
                calls.append((command, None if env is None else env.get("LDFLAGS"), other))
                return 0

            ns = {"__name__": "__main__", "__file__": str(setup_path)}
            with contextlib.redirect_stdout(io.StringIO()):
                try:
                    exec(compile(Path(setup_path).read_text(), str(setup_path), "exec"), ns)
                    ns.update(platform=platform, call=fake_call, mppl2f90=lambda *a, **k: None,
                              check_output=fake_check_output(libgcov, finclude), SRCDIR=str(srcdir),
                              build=types.SimpleNamespace(run=lambda self: None))
                    captured["cmdclass"]["build"].run(types.SimpleNamespace(build_lib=str(build_lib)))
                except SystemExit as e:
                    return {"exit": str(e)}
            omp_env = os.environ.get("OMP")
            build_info = read_record(build_lib / "uedge" / "_build_info.json", libgcov, finclude)
    finally:
        sys.argv = saved_argv
        os.environ.clear()
        os.environ.update(saved_env)

    if len(calls) != 2 or calls[0][0] != ["make", "-f", "Makefile.Forthon", "clean"]:
        raise RuntimeError("expected make clean, then the build; got {}".format(calls))
    command, make_ldflags, make_env = calls[-1]
    if command[0] != "make" or command[-2:] != ["-f", "Makefile.Forthon"] or len(command) != 5:
        raise RuntimeError("unexpected build call {}".format(command))
    compileflags, ompflags = command[1], command[2]
    fargs = re.fullmatch(r'DEBUG = -v --fargs "([^"]*)"(?: --cargs="([^"]*)")?', compileflags)
    if fargs is None or not ompflags.startswith("OMPFLAGS = "):
        raise RuntimeError("unexpected make arguments {!r} {!r}".format(compileflags, ompflags))
    uedgec = captured["ext_modules"][0]
    fake_args = FakeFCompiler.extra_link_args + FakeFCompiler.extra_compile_args
    if make_ldflags is not None:
        make_ldflags = make_ldflags.replace(libgcov, LIBGCOV)
    return {"fargs": fargs.group(1).replace(finclude, FINCLUDE), "cargs": fargs.group(2), "ompflags": ompflags[len("OMPFLAGS = "):],
            "ldflags": make_ldflags, "omp_env": omp_env, "make_env": dict(sorted(make_env.items())),
            "uedgec_link": [FCOMPILER if a in fake_args else a for a in uedgec.extra_link_args],
            "uedgec_compile": [FCOMPILER if a in fake_args else a for a in uedgec.extra_compile_args],
            "uedgec_macros": [list(m) for m in uedgec.define_macros], "make_calls": len(calls),
            "build_info": build_info}


MPPL_SOURCE = "      subroutine x\n      real y\n      y = float(1)\n      end\n"


def conversion_check(setup_path=SETUP):
    """Where setup.py's MPPL conversion (mppl2f90) converts, and where it leaves the process, when the working
    directory and $PWD differ (AIUE-163): two trees A and B, each with bbb/x.m, the process in A and PWD naming B, as
    for a build launched with subprocess cwd=A or for `pip install A` run from B. Returns {"cwd_after": "A", "B" or
    "other", "converted_in": the trees that got bbb/x.F}. Correct: A and ["A"]; before AIUE-163 setup.py returned to
    $PWD: B and ["B"]."""
    saved_argv, saved_env, saved_cwd = list(sys.argv), dict(os.environ), os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        trees = {name: Path(tmp, name) for name in ("A", "B")}
        for tree in trees.values():
            (tree / "bbb").mkdir(parents=True)
            (tree / "bbb" / "x.m").write_text(MPPL_SOURCE)
        try:
            with stubs():
                sys.argv = [str(setup_path), "bdist_wheel", "--dist-dir", "dist"]
                ns = {"__name__": "__main__", "__file__": str(setup_path)}
                with contextlib.redirect_stdout(io.StringIO()):
                    exec(compile(Path(setup_path).read_text(), str(setup_path), "exec"), ns)
                    os.chdir(trees["A"])
                    os.environ["PWD"] = str(trees["B"])
                    ns["mppl2f90"](dirlist=["bbb"])
                here = os.getcwd()  # samefile: on macOS getcwd() gives /private/var/... for tempfile's /var/...
                cwd_after = next((n for n, tree in trees.items() if os.path.samefile(here, tree)), "other")
        finally:
            os.chdir(saved_cwd)
            sys.argv = saved_argv
            os.environ.clear()
            os.environ.update(saved_env)
        return {"cwd_after": cwd_after,
                "converted_in": sorted(n for n, tree in trees.items() if (tree / "bbb" / "x.F").is_file())}


def table(setup_path=SETUP, git=True):
    """Every case of CASES, by name (git=False: the source tree has no .git)."""
    with tempfile.TemporaryDirectory() as tmp:
        libgcov = os.path.join(tmp, "libgcov.a")  # setup.py checks that the path exists
        Path(libgcov).touch()
        finclude = os.path.join(tmp, "finclude")  # and that this one is a directory (AIUE-211)
        Path(finclude).mkdir()
        return {case_name(p, o, ld): evaluate(setup_path, o, p, ld, libgcov, finclude, git) for p, o, ld in CASES}


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--setup", type=Path, default=SETUP, help="the setup.py to evaluate (default: %(default)s)")
    parser.add_argument("--json", action="store_true", help="print one JSON object instead of a table")
    parser.add_argument("--conversion", action="store_true",
                        help="check where the MPPL conversion runs when cwd and $PWD differ (JSON)")
    parser.add_argument("--no-git", action="store_true", help="evaluate as for a source tree without .git")
    args = parser.parse_args(argv[1:])
    if not args.setup.is_file():
        parser.error("no such file: {}".format(args.setup))
    if args.conversion:
        print(json.dumps(conversion_check(args.setup.resolve())))
        return 0
    result = table(args.setup.resolve(), git=not args.no_git)
    if args.json:
        print(json.dumps(result, indent=1))
    else:
        for name, record in result.items():
            print(name)
            for field, value in record.items():
                print("  {:12s} {!r}".format(field, value))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
