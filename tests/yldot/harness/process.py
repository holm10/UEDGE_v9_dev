"""Parent side of the yldot harness: isolated children, timeouts and classified results (PRD section 6).

    Use:  r = Runner();  res = r.evaluate("d_only", config="timestep")
          res.status in {"ok", "error", "crash", "timeout"}; res.data["yldot"], res.data["yldot_J"]
          r.evaluate("d_only", variant=v)  (v from variants.plan(); res.data["variant"] holds d and the applied
          value), r.evaluate("d_only", variant=v, replay=rec["applied"]) applies a recorded value again

Every evaluation runs in a new child process (Forthon state is global). Children come from a multiprocessing
forkserver that preloads uedge and numpy, or, where forkserver is unavailable or YLDOT_START_METHOD=spawn, from
spawn. Both start with HOME and the working directory in one empty directory, so import uedge cannot execute a
.uedgerc.py (src/uedge/__init__.py:58-67): the forkserver inherits them when it starts, and spawn's prepare() moves
the child to the parent's cwd at start(). UEDGE_BANNER=0 keeps imports off the network; one thread for OpenMP and
BLAS. A family defect (.uedgerc.py in its directory, svrpkg/ifixpsor not as asserted) raises FamilyError; a
crash, timeout or exception inside the child is a classified Result and the run goes on.

Both start methods re-run the parent's __main__ script in each child as __mp_main__ (Python 3.13 forkserver too):
a script that uses the Runner needs an `if __name__ == "__main__":` guard.
"""
import atexit
import contextlib
import multiprocessing
import os
import shutil
import sys
import tempfile
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import state, variants
from .variants import CONFIGS

FAMILIES = Path(__file__).resolve().parent.parent / "families"
INTAKE = "intake"  # the intake residual check (PRD section 7.1), not a reference configuration
START_METHODS = ("forkserver", "spawn")
# family.toml [evaluation] fallbacks for a family not measured yet (placeholders, owner, 2026-10-19): AIUE-86
# measured W and P of the five small families (tools/measure_history.py), AIUE-92 measures the owner families
EVALUATION_DEFAULTS = {"w": 2, "p": 2, "timeout_s": 120.0, "dt_timestep_s": 1e-6}
START_ENV = {"UEDGE_BANNER": "0", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
             "GFORTRAN_UNBUFFERED_PRECONNECTED": "y"}  # the last one: Fortran output reaches the log before a crash
EXIT_GRACE_S = 30.0

_isolation_dir = None


class HarnessError(Exception):
    """The harness itself failed (e.g. the forkserver preload)."""


class FamilyError(HarnessError):
    """The family is not usable as it is: the epic owner has to look at it."""


@dataclass
class Result:
    status: str  # ok, error (exception or xerrab in the child), crash, timeout
    family: str
    config: str
    mode: str
    data: dict = None
    message: str = ""
    log_tail: str = ""
    exitcode: int = None
    wall_s: float = 0.0

    @property
    def ok(self):
        return self.status == "ok"


def isolation_dir():
    """One empty directory per parent process, HOME and cwd of every child at import time. It lives as long as
    the process, because the forkserver (one per process) keeps it as its cwd."""
    global _isolation_dir
    if _isolation_dir is None:
        _isolation_dir = tempfile.mkdtemp(prefix="yldot-home-")
        atexit.register(shutil.rmtree, _isolation_dir, True)
    return _isolation_dir


@contextlib.contextmanager
def isolated():
    """The parent's HOME, cwd and START_ENV switched to the isolation directory while a child starts. sys.path is
    made absolute meanwhile: the child receives it (spawn, and forkserver at server start) but runs in another cwd."""
    home = isolation_dir()
    keys = ("HOME",) + tuple(START_ENV)
    saved = {k: os.environ.get(k) for k in keys}
    cwd = os.getcwd()
    path = list(sys.path)
    sys.path[:] = [os.path.abspath(p) for p in path]
    os.environ.update(START_ENV, HOME=home)
    os.chdir(home)
    try:
        yield
    finally:
        os.chdir(cwd)
        sys.path[:] = path
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def family_dir(family):
    """A family name (a directory in FAMILIES) or a path to a family directory."""
    p = Path(family)
    if len(p.parts) == 1 and not p.is_absolute():
        p = FAMILIES / p
    p = p.resolve()
    if not (p / "input.py").is_file():
        raise FamilyError("{}: no input.py".format(p))
    return p


def load_evaluation(family):
    """The [evaluation] section of family.toml over EVALUATION_DEFAULTS."""
    ev = dict(EVALUATION_DEFAULTS)
    toml = family_dir(family) / "family.toml"
    if toml.is_file():
        with open(toml, "rb") as f:
            ev.update(tomllib.load(f).get("evaluation", {}))
    return ev


def log_tail(path, n=state.LOG_TAIL):
    try:
        lines = Path(path).read_text(errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-n:])


class Runner:
    """Starts one isolated child per evaluation. mode: 'forkserver' or 'spawn'; None takes YLDOT_START_METHOD,
    else forkserver where the platform has it, else spawn."""

    def __init__(self, mode=None):
        if mode is None:
            mode = os.environ.get("YLDOT_START_METHOD") or (
                "forkserver" if "forkserver" in multiprocessing.get_all_start_methods() else "spawn")
        if mode not in START_METHODS:
            raise ValueError("start method {!r}, expected one of {}".format(mode, START_METHODS))
        self.mode = mode
        self.ctx = multiprocessing.get_context(mode)
        if mode == "forkserver":
            # The server is one per process and starts on the first start(); a later call has no effect then.
            self.ctx.set_forkserver_preload(["uedge", "numpy"])

    def evaluate(self, family, config=None, diagnostics=False, pre=None, post=None, timeout=None, variant=None,
                 replay=None, locality=None):
        """One evaluation of the family. config: steady, timestep or intake (the unperturbed reference_state.h5,
        never with a variant); None takes the variant's configuration, else steady. pre/post: 'module:function'
        hooks called as f(bbb, com) in the PRE and POST phases, before the variant. variant: a variants.Variant (or
        its dict), applied in its phase with d read live; replay: a recorded applied value (variants.encode form)
        used instead of the rules. timeout: seconds, default from family.toml. locality: delta_loc, which adds the
        locality protocol (PRD 7.5, state.py step 8c) to a steady evaluation without a variant."""
        spec = None
        if variant is not None:
            v = variant if isinstance(variant, variants.Variant) else variants.Variant.from_dict(variant)
            spec = {"variant": v.to_dict(), "replay": replay}
            if config is None:
                config = v.config
        elif replay is not None:
            raise ValueError("replay without a variant")
        if config is None:
            config = "steady"
        if config not in CONFIGS + (INTAKE,):
            raise ValueError("config {!r}, expected one of {}".format(config, CONFIGS + (INTAKE,)))
        if config == INTAKE and spec is not None:
            raise ValueError("the intake configuration takes no variant")
        if locality is not None and (config != "steady" or spec is not None):
            raise ValueError("the locality check runs in the steady configuration without a variant")
        fdir = family_dir(family)
        ev = load_evaluation(fdir)
        timeout = float(ev["timeout_s"] if timeout is None else timeout)
        with tempfile.TemporaryDirectory(prefix="yldot-child-") as tmp:
            job = {"family": str(fdir), "config": config, "mode": self.mode, "w": int(ev["w"]), "p": int(ev["p"]),
                   "dt": float(ev["dt_timestep_s"]), "diagnostics": bool(diagnostics), "pre": pre, "post": post,
                   "variant": spec, "log": os.path.join(tmp, "child.log"),
                   "locality": None if locality is None else float(locality)}
            recv, send = self.ctx.Pipe(duplex=False)
            proc = self.ctx.Process(target=state.run, args=(send, job), name="yldot-{}-{}".format(fdir.name, config))
            t0 = time.monotonic()
            with isolated():
                proc.start()
            send.close()
            status, msg = None, None
            try:
                # poll before join: a large result would otherwise block the child on a full pipe
                if recv.poll(timeout):
                    msg = recv.recv()
                else:
                    status = "timeout"
            except EOFError:
                status = "crash"
            finally:
                # also on any other exception (unpickling, KeyboardInterrupt): never leave the child running
                recv.close()
                if msg is None and proc.is_alive():
                    proc.kill()
                proc.join(EXIT_GRACE_S)
                if proc.is_alive():
                    proc.kill()
                    proc.join()
            exitcode = proc.exitcode
            proc.close()
            wall = time.monotonic() - t0
            tail = log_tail(job["log"])

        data, message = None, ""
        if status == "timeout":
            message = "no result after {:g} s; child killed".format(timeout)
        elif status == "crash":
            message = "child exited with code {} without a result".format(exitcode)
        else:
            status, data, message = msg
        if status == "refused" or status == "owner":
            raise FamilyError(message)
        if status == "harness":
            raise HarnessError("{}\n{}".format(message, tail))
        return Result(status=status, family=fdir.name, config=config, mode=self.mode, data=data, message=message,
                      log_tail=tail, exitcode=exitcode, wall_s=wall)
