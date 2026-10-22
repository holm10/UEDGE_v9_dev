"""The compiler and link flags setup.py assembles for each build option, evaluated without building (AIUE-125).

Usage (from anywhere):
    python -I build_flags.py [--setup PATH] [--json]

PRD section 8: the opt-in, results-neutral build options (--noopt, AIUE-85; --coverage, AIUE-105) may not change
the default flags. This tool runs setup.py (default: the one in this checkout) once per case in CASES, with the
build's side effects stubbed: Forthon's FCompiler is a fixed fake (the real Forthon is never imported: its import
parses sys.argv), setuptools.setup only records its arguments, os.system (the readline probe) returns 1, and in
uedgeBuild.run the make calls, mppl2f90, check_output (the macOS libgcov lookup) and build.run are replaced.
sys.argv has the shape pip gives setup.py for -C "--build-option=--<opt>": [setup.py, bdist_wheel, --dist-dir,
<dir>, --<opt>...]. platform, read by uedgeBuild.run at call time, is set per case, so both the Linux and the macOS
branches are evaluated on any host.

Each case records what reaches the build: the --fargs and --cargs strings and OMPFLAGS passed to make, the LDFLAGS
of make's environment (None: make inherits the caller's environment), the OMP environment variable, every other
variable of make's environment that differs from the caller's (PATH excepted: setup.py appends the host's
user-site bin directory), the uedgeC link and compile arguments (the compiler's own shown as <fcompiler>) and
macros, and the number of make calls (clean, then the build). A refused combination records the SystemExit message
instead. The comparison with the flags on v9-develop lives in tests/yldot/test_build_flags.py.

Not covered: what setup.py passes to Forthon's real FCompiler (machine, debug, fcompname) and the flags that
compiler adds, which depend on the host's compiler; the -g, -t and -F short options; --noclean (the tool expects
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
FCOMPILER = "<fcompiler>"  # stands for an argument of the compiler's own (FakeFCompiler's) in the uedgeC lists


class FakeFCompiler:
    """Forthon.compilers.FCompiler with fixed attributes: the real one's depend on the host's compiler."""
    libdirs = ["/fake/lib"]
    libs = ["fakefortran"]
    extra_link_args = ["-fake-fc-link"]
    extra_compile_args = ["-fake-fc-compile"]
    fcompexec = "fake-gfortran"

    def __init__(self, machine=None, debug=0, fcompname=None):
        pass


def case_name(platform, options, ldflags):
    name = "{}:{}".format(platform, "+".join(options) or "default")
    return name if ldflags is None else "{}@{}".format(name, ldflags)


def evaluate(setup_path, options, platform, ldflags, libgcov):
    """Run setup_path for one case and return its record (see the module docstring)."""
    saved_argv, saved_env = list(sys.argv), dict(os.environ)
    saved_modules = {k: sys.modules.get(k) for k in ("Forthon", "Forthon.compilers")}
    saved_setup, saved_system = setuptools.setup, os.system
    captured, calls = {}, []
    try:
        fake = types.ModuleType("Forthon.compilers")
        fake.FCompiler = FakeFCompiler
        sys.modules["Forthon"] = types.ModuleType("Forthon")
        sys.modules["Forthon.compilers"] = fake
        setuptools.setup = lambda **kw: captured.update(kw)
        os.system = lambda command: 1
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
                          check_output=lambda *a, **k: libgcov + "\n",
                          build=types.SimpleNamespace(run=lambda self: None))
                captured["cmdclass"]["build"].run(None)
            except SystemExit as e:
                return {"exit": str(e)}
        omp_env = os.environ.get("OMP")
    finally:
        sys.argv = saved_argv
        os.environ.clear()
        os.environ.update(saved_env)
        setuptools.setup, os.system = saved_setup, saved_system
        for k, v in saved_modules.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

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
    return {"fargs": fargs.group(1), "cargs": fargs.group(2), "ompflags": ompflags[len("OMPFLAGS = "):],
            "ldflags": make_ldflags, "omp_env": omp_env, "make_env": dict(sorted(make_env.items())),
            "uedgec_link": [FCOMPILER if a in fake_args else a for a in uedgec.extra_link_args],
            "uedgec_compile": [FCOMPILER if a in fake_args else a for a in uedgec.extra_compile_args],
            "uedgec_macros": [list(m) for m in uedgec.define_macros], "make_calls": len(calls)}


def table(setup_path=SETUP):
    """Every case of CASES, by name."""
    with tempfile.TemporaryDirectory() as tmp:
        libgcov = os.path.join(tmp, "libgcov.a")  # setup.py checks that the path exists
        Path(libgcov).touch()
        return {case_name(p, o, ld): evaluate(setup_path, o, p, ld, libgcov) for p, o, ld in CASES}


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--setup", type=Path, default=SETUP, help="the setup.py to evaluate (default: %(default)s)")
    parser.add_argument("--json", action="store_true", help="print one JSON object instead of a table")
    args = parser.parse_args(argv[1:])
    if not args.setup.is_file():
        parser.error("no such file: {}".format(args.setup))
    result = table(args.setup.resolve())
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
