"""Run configurations for the OpenMP determinism harness.

A run is fully described by a RunSpec: which equations are on (a preset), which arm
(serial, OpenMP Jacobian only, OpenMP Jacobian + RHS), the thread count, and how far
the solver runs. RunSpecs are plain JSON so the worker can read them in a fresh process.
"""
import json
from dataclasses import asdict, dataclass, field

# Arms (PRD §6.1): OMPParallelPandf1=1 forces OMPParallelJac=1, so there are only two
# OpenMP arms, plus the serial reference.
ARMS = {
    "serial": {"OMPParallelJac": 0, "OMPParallelPandf1": 0},
    "jac": {"OMPParallelJac": 1, "OMPParallelPandf1": 0},
    "jacrhs": {"OMPParallelJac": 1, "OMPParallelPandf1": 1},
}

# Never on in a measured run (they change solver state or abort): RunSpec.validate rejects them
DIAGNOSTIC_SWITCHES = ["CheckJac", "CheckPandf1", "ForceSerialCheck"]

EQUATIONS = ["isnion", "isupon", "isteon", "istion", "isngon", "isphion"]

# Equation presets, applied after the deck. "keep" lists the equation switches left at the
# deck's values; every other switch in EQUATIONS is set to 0 (and isphiofft=1 when the
# potential is off, as in the owner's testscript.py). "set" holds extra assignments as
# [variable, index, value], where index is None (whole variable) or a list of
# [start, stop] pairs (numpy slice order).
PRESETS = {
    # all equations as the deck leaves them (neq = 44352)
    "full": {"keep": EQUATIONS, "set": []},
    # the owner's Te box: Te only, and only in cells ix 3..7, iy 18..22 (25 equations)
    "tebox": {"keep": ["isteon"],
              "set": [["isteoffxy", None, 1], ["isteoffxy", [[3, 8], [18, 23]], 0]]},
    # one equation group alone on the whole grid
    "te": {"keep": ["isteon"], "set": []},
    "ti": {"keep": ["istion"], "set": []},
    "ni": {"keep": ["isnion"], "set": []},
    "up": {"keep": ["isupon"], "set": []},
    "ng": {"keep": ["isngon"], "set": []},
    # phi alone fails in serial ("Jacobian row = 0"), and so do phi with ni+up, phi with
    # ni+up+ti, and the full problem without Te; phi runs in serial only together with Te
    "te_phi": {"keep": ["isteon", "isphion"], "set": []},
}


def apply_preset(bbb, name):
    """Apply an equation preset to a live bbb package (call after the deck ran)."""
    preset = PRESETS[name]
    for eq in EQUATIONS:
        if eq not in preset["keep"]:
            setattr(bbb, eq, 0)
    if "isphion" not in preset["keep"]:
        bbb.isphiofft = 1
    for var, index, value in preset["set"]:
        if index is None:
            setattr(bbb, var, value)
        else:
            getattr(bbb, var)[tuple(slice(a, b) for a, b in index)] = value


# Forced Newton iterations (AIUE-169): a run that asks for N iterations makes exactly N, whatever
# state the solution is in. At the deck's tolerances a converged start makes none (the nightly ni/ng
# isolations start at fnrm ~1e-11), and how converged a state is depends on platform round-off.
# Both nksol tolerances must be tiny and positive (0 selects nksol's default, svr/nksol.m:976,983):
# - ftol: maxnorm(sf*f) <= ftol stops with iterm=1;
# - stptol: a scaled step <= stptol stops with iterm=2 (default epsmch**(2/3) ~ 3.7e-11), or, with a
#   stale preconditioner, forces a new one and skips the itermx test, so the run overshoots N
#   (nkstop, svr/nksol.m:1255-1262). stptol also sets the line search's minimum lambda
#   (rlmin = stptol/rlngth, svr/nksol.m:3281) and inexct's minimum constrained step (:3924), so a
#   failing line search backtracks further before it gives up.
NEWTON_FTOL = 1e-19
NEWTON_STPTOL = 1e-30


def force_newton(bbb, itermx):
    """Make the next exmain run exactly itermx Newton iterations (unless nksol fails first)."""
    bbb.itermx = itermx
    bbb.ftol = NEWTON_FTOL
    bbb.stptol = NEWTON_STPTOL


@dataclass
class RunSpec:
    preset: str = "tebox"
    arm: str = "serial"
    threads: int = 1
    # None: one evaluation (ftol=1e20: one Jacobian and the iteration-0 residual).
    # N > 0: exactly N Newton iterations (force_newton: itermx=N, ftol and stptol far below the noise floor).
    itermx: int = None
    omp_stacksize: str = "512M"
    # extra ppp settings, e.g. {"OMPJacNchunks": -1, "OMPAutoBalance": 0}
    ppp: dict = field(default_factory=dict)
    # also evaluate the RHS once more after exmain through ffun (the solver's RHS path),
    # to capture yldot from the parallel RHS on the jacrhs arm
    rhs_probe: bool = True
    # number of raw Jacobians to keep with the AIUE-47 capture hook (builds without the hook
    # ignore it); every Jacobian of a run fits for itermx up to capture-1
    capture: int = 16

    def validate(self):
        if self.preset not in PRESETS:
            raise ValueError("unknown preset {!r}; known: {}".format(self.preset, sorted(PRESETS)))
        if self.arm not in ARMS:
            raise ValueError("unknown arm {!r}; known: {}".format(self.arm, sorted(ARMS)))
        if self.arm == "serial" and self.threads != 1:
            raise ValueError("the serial arm runs with threads=1")
        if self.threads < 1:
            raise ValueError("threads must be >= 1")
        bad = [k for k in self.ppp if k in DIAGNOSTIC_SWITCHES or k in ("OMPParallelJac", "OMPParallelPandf1",
                                                                         "Nthreads")]
        if bad:
            raise ValueError("ppp settings {} are set by the arm/threads or are diagnostics; not allowed".format(bad))
        if self.capture < 0:
            raise ValueError("capture must be >= 0")
        return self

    def label(self):
        it = "it0" if self.itermx is None else "it{}".format(self.itermx)
        extra = "".join("_{}{}".format(k, v) for k, v in sorted(self.ppp.items()))
        return "{}_{}_t{}_{}{}".format(self.preset, self.arm, self.threads, it, extra)

    def to_json(self):
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_json(cls, text):
        return cls(**json.loads(text)).validate()
