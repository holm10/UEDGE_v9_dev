"""Variants of the yldot suite (PRD section 7.2): which value each input takes, in which phase and configuration,
and its application inside the child.

    plan()           every variant of the inventory (tagged inputs and the overrides.toml additions), in a stable
                     order: id, rule, phase, configuration, EXCLUDED and reason
    rule_value()     the value rules (owner, 2026-10-20: elementwise on arrays; bounded next index)
    apply()          in the child: read d live, compute (or replay) the value, assign it, read it back, record both
    encode/decode    exact JSON form of d and the applied value; a replay uses the recorded value, never the rules

The family value d is read from the Forthon variable at the moment of application (PRE: after input.py; POST: after
input.py, allocate and the state restore), never from the .v default. uedge is imported only inside apply().
"""
import importlib
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from . import inputs

OVERRIDES = Path(__file__).resolve().parent.parent / "overrides.toml"
CONFIGS = ("steady", "timestep")
PHASES = ("PRE", "POST")
FIELDS = {"reason", "add", "exclude", "values", "others", "bound", "phase", "config"}
# the allowed values of the differencing methods (bbb/bbb.v:33-41); api.methimp is never read, so it has none
METH_VALUES = {
    "bbb.methn": (22, 33),
    "bbb.methu": (22, 33, 44, 55),
    "bbb.methe": (22, 33, 44, 55),
    "bbb.methi": (22, 33, 44, 55),
    "bbb.methp": (22, 33, 44, 55),
    "bbb.methg": (22, 33, 44, 55, 66, 77),
}


class Mismatch(Exception):
    """d differs between the two POST applications of the timestep configuration: irregular, for the epic owner."""


@dataclass(frozen=True)
class Variant:
    id: str  # the key; key=value for an explicit value; key=other for the EXCLUDED rest of an explicit list
    key: str
    rule: str  # default, value, bounded
    value: object = None  # rule value
    bound: str = None  # rule bounded: the key of the bound
    phase: str = "PRE"
    config: str = "steady"
    excluded: bool = False
    reason: str = ""

    @property
    def package(self):
        return self.key.partition(".")[0]

    @property
    def name(self):
        return self.key.partition(".")[2]

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


def load_overrides(path=OVERRIDES, repo=inputs.REPO):
    """overrides.toml, checked against the inventory. ValueError names the key at fault."""
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    allvars = inputs.parse(repo)
    for key, o in raw.items():
        def bad(msg):
            return ValueError("{}: {}: {}".format(path, key, msg))
        if not isinstance(o, dict):
            raise bad("not a table")
        if key not in allvars:
            raise bad("no such variable in any .v file")
        var = allvars[key]
        unknown = set(o) - FIELDS
        if unknown:
            raise bad("unknown fields {}".format(sorted(unknown)))
        if not str(o.get("reason", "")).strip():
            raise bad("no reason")
        if o.get("add") and var.tagged:
            raise bad("add = true on a tagged variable")
        if not o.get("add") and not var.tagged:
            raise bad("not tagged +input/+maybeinput: needs add = true")
        if "phase" in o and o["phase"] not in PHASES:
            raise bad("phase {!r}, expected one of {}".format(o["phase"], PHASES))
        if "config" in o and o["config"] not in CONFIGS:
            raise bad("config {!r}, expected one of {}".format(o["config"], CONFIGS))
        if "others" in o and "values" not in o:
            raise bad("others without values")
        if "bound" in o:
            if "values" in o:
                raise bad("values and bound together")
            b = allvars.get(o["bound"])
            if b is None or b.type != "integer" or b.dims or b.dynamic:
                raise bad("bound {!r} is not an integer scalar".format(o["bound"]))
            if var.type != "integer":
                raise bad("bound on a {} variable".format(var.type))
        if "values" in o:
            if not isinstance(o["values"], list) or not o["values"]:
                raise bad("values must be a non-empty list")
            if any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in o["values"]):
                raise bad("values must be integers or floats")
        if o.get("exclude") and {"values", "others", "bound", "phase"} & set(o):
            raise bad("exclude together with values, others, bound or phase")
        if var.type == "character" and ("values" in o or "bound" in o):
            raise bad("values or bound on a character variable")
    return raw


def plan(repo=inputs.REPO, overrides=None):
    """Every variant of the inventory, in inventory order (then the listed values in their order)."""
    ov = load_overrides(repo=repo) if overrides is None else overrides
    out = []
    for key, var in inputs.parse(repo).items():
        o = ov.get(key, {})
        if not (var.tagged or o.get("add")):
            continue
        phase = o.get("phase", "POST" if var.dynamic else "PRE")
        config = o.get("config", "steady")
        common = dict(key=key, phase=phase, config=config)
        if o.get("exclude"):
            out.append(Variant(id=key, rule="default", excluded=True, reason=o["reason"], **common))
        elif var.type == "character":
            out.append(Variant(id=key, rule="default", excluded=True, reason="character/filename input", **common))
        elif "values" in o or key in METH_VALUES:
            values = o["values"] if "values" in o else METH_VALUES[key]
            reason = o["reason"] if "values" in o else "allowed values (bbb/bbb.v:33-41)"
            for v in values:
                out.append(Variant(id="{}={}".format(key, v), rule="value", value=v, reason=reason, **common))
            if "others" in o:
                out.append(Variant(id=key + "=other", rule="value", excluded=True,
                                   reason="values other than {}: {}".format(list(values), o["others"]), **common))
        elif "bound" in o:
            out.append(Variant(id=key, rule="bounded", bound=o["bound"], reason=o["reason"], **common))
        else:
            out.append(Variant(id=key, rule="default", reason=o.get("reason", ""), **common))
    ids = [v.id for v in out]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate variant ids")
    return out


def rule_value(d, rule, value=None, bound=None):
    """The variant value for the family value d, elementwise on arrays (owner, 2026-10-20); d's dtype is kept."""
    d = np.asarray(d)
    kind = d.dtype.kind
    if kind not in "if":
        raise TypeError("no rule for dtype {}".format(d.dtype))
    if rule == "value":
        v = np.full(d.shape, value, dtype=d.dtype)
        if (v != value).any():
            raise ValueError("value {!r} is not representable as {}".format(value, d.dtype))
        return v
    if rule == "bounded":
        if kind != "i":
            raise TypeError("bounded rule on dtype {}".format(d.dtype))
        return np.where(d + 1 <= bound, d + 1, np.where(d - 1 >= 1, d - 1, d)).astype(d.dtype)
    if rule != "default":
        raise ValueError("rule {!r}".format(rule))
    if kind == "i":
        return np.where((d == 0) | (d == 1), 1 - d, d + 1).astype(d.dtype)
    return np.where(d == 0, 1.0, d * 1.1).astype(d.dtype)


def encode(x):
    """The exact JSON form of a scalar or an array (JSON floats round-trip through repr)."""
    a = np.asarray(x)
    if a.dtype.kind == "f" and not np.isfinite(a).all():
        raise ValueError("non-finite value")
    return {"dtype": str(a.dtype), "shape": list(a.shape), "data": a.ravel().tolist()}


def decode(e):
    return np.array(e["data"], dtype=e["dtype"]).reshape(e["shape"])


def apply(spec, phase, previous=None):
    """Apply the variant of spec ({"variant": Variant.to_dict(), "replay": None or encode(value)}) if it belongs to
    this phase, in the child. previous: this variant's record from the first POST of the timestep configuration; its
    applied value is applied again and d must not have changed. Returns the record, or None if not this phase.
    An unallocated dynamic array (the read raises "unallocated", or it has size 0) gives status "unallocated" with
    d = None and applied = None: there is nothing to apply, with or without a replay or previous."""
    if not spec:
        return None
    v = Variant.from_dict(spec["variant"])
    if v.phase != phase:
        return None
    if v.excluded:
        raise ValueError("{}: EXCLUDED ({}), never applied".format(v.id, v.reason))
    uedge = importlib.import_module("uedge")
    pkg = getattr(uedge, v.package)
    try:
        live = getattr(pkg, v.name)
    except Exception as e:
        if "unallocated" not in str(e):
            raise
        return {"id": v.id, "key": v.key, "phase": v.phase, "config": v.config, "d": None, "status": "unallocated",
                "applied": None}
    d = np.array(live)
    record = {"id": v.id, "key": v.key, "phase": v.phase, "config": v.config, "d": encode(d)}
    if isinstance(live, np.ndarray) and live.size == 0:
        record.update(d=None, status="unallocated", applied=None)
        return record
    if previous is not None:
        # the second POST of the timestep configuration: the first application either survived allocate and the
        # restore ("kept") or was reset to d ("reset"); anything else is irregular
        same = {k: decode(previous[k]) for k in ("d", "applied")}
        found = [k for k, a in same.items() if a.shape == d.shape and a.tobytes() == d.tobytes()]
        if not found:
            raise Mismatch("{}: the live value at the second timestep pass is neither d nor the applied value of "
                           "the first".format(v.id))
        record["d"] = previous["d"]
        record["second_pass"] = "reset" if "d" in found else "kept"
        d = same["d"]
    bound = None
    if spec.get("replay") is not None:
        applied = decode(spec["replay"])
        if applied.shape != d.shape or applied.dtype != d.dtype:
            raise ValueError("{}: replay value {} {} does not fit the variable's {} {}"
                             .format(v.id, applied.dtype, applied.shape, d.dtype, d.shape))
    elif previous is not None:
        applied = decode(previous["applied"])
    else:
        if v.rule == "bounded":
            bpkg, _, bname = v.bound.partition(".")
            bound = int(getattr(getattr(uedge, bpkg), bname))
        applied = rule_value(d, v.rule, v.value, bound)
    if isinstance(live, np.ndarray):
        live[...] = applied
    else:
        setattr(pkg, v.name, applied.item())
    back = np.array(getattr(pkg, v.name))
    if back.dtype != applied.dtype or back.tobytes() != applied.tobytes():
        raise RuntimeError("{}: not stored as applied".format(v.id))
    if applied.tobytes() != d.tobytes():
        status = "applied"
    else:
        status = "no-valid-index" if v.rule == "bounded" else "equal-to-d"
    record.update(status=status, applied=encode(applied))
    if bound is not None:
        record["bound"] = bound
    return record
