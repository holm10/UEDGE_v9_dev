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
    # phi alone fails in serial ("Jacobian row = 0"); the full problem without Te includes phi
    "full_note": {"keep": ["isnion", "isupon", "istion", "isngon", "isphion"], "set": []},
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


@dataclass
class RunSpec:
    preset: str = "tebox"
    arm: str = "serial"
    threads: int = 1
    # None: one evaluation (ftol=1e20: one Jacobian and the iteration-0 residual).
    # N > 0: N Newton iterations (itermx=N) at the deck's ftol.
    itermx: int = None
    omp_stacksize: str = "512M"
    # extra ppp settings, e.g. {"OMPJacNchunks": -1, "OMPAutoBalance": 0}
    ppp: dict = field(default_factory=dict)
    # also evaluate the RHS once more after exmain through ffun (the solver's RHS path),
    # to capture yldot from the parallel RHS on the jacrhs arm
    rhs_probe: bool = True

    def validate(self):
        if self.preset not in PRESETS:
            raise ValueError("unknown preset {!r}; known: {}".format(self.preset, sorted(PRESETS)))
        if self.arm not in ARMS:
            raise ValueError("unknown arm {!r}; known: {}".format(self.arm, sorted(ARMS)))
        if self.arm == "serial" and self.threads != 1:
            raise ValueError("the serial arm runs with threads=1")
        if self.threads < 1:
            raise ValueError("threads must be >= 1")
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
