"""Variants of the yldot suite (PRD section 7.2): which value each input takes, in which phase and configuration,
and its application inside the child.

    plan()           every variant of the inventory (tagged inputs and the overrides.toml additions), in a stable
                     order: id, rule, phase, configuration, EXCLUDED and reason; then the combination sets
    load_sets()      the combination sets of combinations.toml (AIUE-257, owner D1 2026-11-11), checked
    rule_value()     the value rules (owner, 2026-10-20: elementwise on arrays; bounded next index; owner, 2026-10-23,
                     AIUE-161: charge, d+1 on the positive slots below a live count)
    set_value()      one key's value in a set: a number (elementwise), or {value | scale | cycle, at}
    apply()          in the child: read d live, compute (or replay) the value, assign it, read it back, record both
    encode/decode    exact JSON form of d and the applied value; a replay uses the recorded value, never the rules

The family value d is read from the Forthon variable at the moment of application (PRE: after input.py; POST: after
input.py, allocate and the state restore), never from the .v default. uedge is imported only inside apply().

A combination set (rule "set", id "set:<name>") assigns several keys at once. Its apply record holds "keys" and dicts
{key: encode form} as d and applied; a replay is such a dict. A set with a base is classified against the base set's
result instead of the family default (make_references.py), which shows a parameter acting while its branch is on.
"""
import importlib
import re
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from . import inputs

OVERRIDES = Path(__file__).resolve().parent.parent / "overrides.toml"
SETS = Path(__file__).resolve().parent.parent / "combinations.toml"
FAMILIES = Path(__file__).resolve().parent.parent / "families"
SMALL_FAMILIES = ("d_only", "d_mols", "d_c", "ortho", "slab_phi")  # a set's default families (owner D3, AIUE-257)
SET_FIELDS = {"assign", "phase", "config", "families", "base", "reason", "issues"}
SET_ID = re.compile(r"^set:[a-z0-9][a-z0-9_.-]*$")
ISSUE = re.compile(r"^AIUE-[0-9]+$")
IX_DIM = "0:nx+1"
# The per-cell wall arrays that setwallbcarrays (bbb/odesetup.m:548) overwrites from their scalars while their switch
# is 0: a set that assigns one must set the switch to 1 too, or the assignment is a no-op by construction. The ly*ix
# arrays hold both walls: the first index 0 (Fortran 1) is the PF wall, 1 (Fortran 2) the outer wall.
PF_ARRAYS = ("iphibcwiix", "istepfcix", "istipfcix", "isnwconiix", "isupwiix", "istgpfcix")
WO_ARRAYS = ("iphibcwoix", "istewcix", "istiwcix", "isnwconoix", "isupwoix", "istgwcix")
LY_ARRAYS = ("lyteix", "lytiix", "lyphiix", "lyniix", "lyupix")
PF_SWITCH, WO_SWITCH = "bbb.ispfbcvsix", "bbb.iswobcvsix"
CONFIGS = ("steady", "timestep")
PHASES = ("PRE", "POST")
FIELDS = {"reason", "add", "exclude", "values", "others", "bound", "charge", "phase", "config", "families",
          "rest_exclude"}
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
    id: str  # the key; key=value for an explicit value; key=other for the EXCLUDED rest of an explicit list; set:<name>
    key: str  # a set: its id
    rule: str  # default, value, bounded, charge, set
    value: object = None  # rule value
    bound: str = None  # rule bounded: the key of the bound; rule charge: the key of the slot count
    phase: str = "PRE"
    config: str = "steady"
    excluded: bool = False
    reason: str = ""
    # rule set only: ((key, kind, x, at), ...) in combinations.toml order (kind value/scale/cycle, x a number or a
    # tuple for cycle, at a tuple of numpy indices); the base set's id or None; the families; the AIUE-259 issues
    assign: tuple = None
    base: str = None
    families: tuple = None
    issues: tuple = None

    @property
    def package(self):
        return self.key.partition(".")[0]

    @property
    def name(self):
        return self.key.partition(".")[2]

    def runs_in(self, family):
        """Whether this variant belongs to the family's inventory (families None: every family)."""
        return self.families is None or family in self.families

    @property
    def keys(self):
        return tuple(a[0] for a in self.assign) if self.assign else (self.key,)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        d = dict(d)
        if d.get("assign") is not None:  # JSON turns the tuples into lists
            d["assign"] = tuple((k, kind, tuple(x) if isinstance(x, (list, tuple)) else x, tuple(at))
                                for k, kind, x, at in d["assign"])
        for f in ("families", "issues"):
            if d.get(f) is not None:
                d[f] = tuple(d[f])
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
        if "charge" in o:
            if {"values", "bound", "exclude"} & set(o):
                raise bad("charge together with values, bound or exclude")
            n = allvars.get(o["charge"])
            if n is None or n.type != "integer" or n.dims or n.dynamic:
                raise bad("charge {!r} is not an integer scalar".format(o["charge"]))
            if var.type != "real" or not var.dims or "," in var.dims:
                raise bad("charge on a variable that is not a real 1-D array")
        if "values" in o:
            if not isinstance(o["values"], list) or not o["values"]:
                raise bad("values must be a non-empty list")
            if any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in o["values"]):
                raise bad("values must be integers or floats")
        if o.get("exclude") and {"values", "others", "bound", "phase"} & set(o):
            raise bad("exclude together with values, others, bound or phase")
        if "families" in o:
            fams = o["families"]
            if "values" not in o or {"bound", "charge"} & set(o):
                raise bad("families only with values (the other families keep the default rule)")
            if not isinstance(fams, list) or not fams or len(set(fams)) != len(fams):
                raise bad("families must be a non-empty list without repeats")
            for fam in fams:
                if family_store(fam) is None:
                    raise bad("no family {!r}".format(fam))
        if "rest_exclude" in o:
            if "families" not in o:
                raise bad("rest_exclude without families")
            if not str(o["rest_exclude"]).strip():
                raise bad("rest_exclude needs a reason")
        if var.type == "character" and ("values" in o or "bound" in o):
            raise bad("values or bound on a character variable")
    return raw


def family_store(name, families=FAMILIES):
    """The store kind ("full" or "sketch") of family.toml [family], or None if the family does not exist."""
    f = Path(families) / name / "family.toml"
    if not f.is_file():
        return None
    with open(f, "rb") as fh:
        return tomllib.load(fh)["family"]["store"]


def all_families(families=FAMILIES):
    """Every family of the suite (a directory with a family.toml), sorted."""
    return tuple(sorted(p.parent.name for p in Path(families).glob("*/family.toml")))


def _is_number(x):
    return not isinstance(x, bool) and isinstance(x, (int, float))


def _set_entry(key, var, val, bad):
    """One assign entry of a set as (key, kind, x, at), checked against the variable's type and dimensions."""
    if var.type not in ("integer", "real"):
        raise bad("{}: a {} variable takes no set value".format(key, var.type))
    dims = var.dims.strip("()").split(",") if var.dims else []
    if _is_number(val):
        kind, x, at = "value", val, ()
    elif isinstance(val, dict):
        unknown = set(val) - {"value", "scale", "cycle", "at"}
        if unknown:
            raise bad("{}: unknown fields {}".format(key, sorted(unknown)))
        kinds = [k for k in ("value", "scale", "cycle") if k in val]
        if len(kinds) != 1:
            raise bad("{}: exactly one of value, scale, cycle".format(key))
        kind, x = kinds[0], val[kinds[0]]
        at = val.get("at", [])
        if not isinstance(at, list) or any(isinstance(i, bool) or not isinstance(i, int) or i < 0 for i in at):
            raise bad("{}: at must be a list of numpy indices >= 0".format(key))
        at = tuple(at)
        if len(at) > len(dims):
            raise bad("{}: at {} has more indices than the {} dimensions".format(key, list(at), len(dims)))
        if kind == "cycle":
            if not isinstance(x, list) or not x or not all(_is_number(e) for e in x):
                raise bad("{}: cycle must be a non-empty list of numbers".format(key))
            if len(at) >= len(dims) or dims[len(at)] != IX_DIM:
                raise bad("{}: cycle runs along the {} axis, which must follow at {} (dimensions {})"
                          .format(key, IX_DIM, list(at), var.dims))
            x = tuple(x)
        elif not _is_number(x):
            raise bad("{}: {} must be a number".format(key, kind))
        if kind == "scale" and var.type != "real":
            raise bad("{}: scale on a {} variable".format(key, var.type))
    else:
        raise bad("{}: a number or a table {{value | scale | cycle, at}}".format(key))
    if var.type == "integer":
        for e in (x if isinstance(x, tuple) else (x,)):
            if kind != "scale" and e != int(e):
                raise bad("{}: {} is not an integer".format(key, e))
    return key, kind, x, at


def _wall_switches(key, at):
    """The setwallbcarrays switch(es) a per-cell wall array needs at 1, by its at index."""
    name = key.partition(".")[2]
    if name in PF_ARRAYS:
        return {PF_SWITCH}
    if name in WO_ARRAYS:
        return {WO_SWITCH}
    if name in LY_ARRAYS:
        return {PF_SWITCH} if at[:1] == (0,) else {WO_SWITCH} if at[:1] == (1,) else {PF_SWITCH, WO_SWITCH}
    return set()


def load_sets(path=SETS, repo=inputs.REPO, overrides=None, families=FAMILIES):
    """combinations.toml as Variants (rule "set"), checked against the inventory and overrides.toml. ValueError names
    the set at fault. A key may be any integer or real variable of the inventory, tagged or not (a per-cell wall array
    such as bbb.istepfcix is not tagged), but not one overrides.toml EXCLUDES."""
    path = Path(path)
    if not path.is_file():
        return []
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    ov = load_overrides(repo=repo) if overrides is None else overrides
    allvars = inputs.parse(repo)
    out = {}
    for sid, s in raw.items():
        def bad(msg):
            return ValueError("{}: {}: {}".format(path, sid, msg))
        if not SET_ID.match(sid):
            raise bad("a set id is set:<name>, lower case letters, digits, '_', '-', '.'")
        if not isinstance(s, dict):
            raise bad("not a table")
        unknown = set(s) - SET_FIELDS
        if unknown:
            raise bad("unknown fields {}".format(sorted(unknown)))
        if not str(s.get("reason", "")).strip():
            raise bad("no reason")
        assign = s.get("assign")
        if not isinstance(assign, dict) or not assign:
            raise bad("assign must be a non-empty table")
        entries = []
        for key, val in assign.items():
            var = allvars.get(key)
            if var is None:
                raise bad("{}: no such variable in any .v file".format(key))
            if ov.get(key, {}).get("exclude"):
                raise bad("{}: EXCLUDED in overrides.toml ({})".format(key, ov[key]["reason"]))
            entries.append(_set_entry(key, var, val, bad))
        values = {k: x for k, kind, x, at in entries if kind == "value" and not at}
        for k, kind, x, at in entries:
            for sw in _wall_switches(k, at):
                if values.get(sw) != 1:
                    raise bad("{}: setwallbcarrays overwrites it unless the set assigns {} = 1 "
                              "(bbb/odesetup.m:548)".format(k, sw))
        dynamic = any(allvars[k].dynamic for k, *_ in entries)
        phase = s.get("phase", "POST" if dynamic else "PRE")
        if phase not in PHASES:
            raise bad("phase {!r}, expected one of {}".format(phase, PHASES))
        if phase == "PRE" and dynamic:
            raise bad("phase PRE with a dynamic array: allocate has not run yet")
        config = s.get("config", "steady")
        if config not in CONFIGS:
            raise bad("config {!r}, expected one of {}".format(config, CONFIGS))
        fams = s.get("families", list(SMALL_FAMILIES))
        if not isinstance(fams, list) or not fams or len(set(fams)) != len(fams):
            raise bad("families must be a non-empty list without repeats")
        for fam in fams:
            if family_store(fam, families) is None:
                raise bad("no family {!r}".format(fam))
        issues = s.get("issues", [])
        if not isinstance(issues, list) or not all(isinstance(i, str) and ISSUE.match(i) for i in issues):
            raise bad("issues must be a list of Jira keys (AIUE-<n>)")
        out[sid] = Variant(id=sid, key=sid, rule="set", phase=phase, config=config, reason=str(s["reason"]),
                           assign=tuple(entries), base=s.get("base"), families=tuple(fams),
                           issues=tuple(issues) or None)
    for sid, v in out.items():
        if v.base is None:
            continue
        def bad(msg):
            return ValueError("{}: {}: {}".format(path, sid, msg))
        b = out.get(v.base)
        if b is None:
            raise bad("base {!r} is not a set of this file".format(v.base))
        if b.base is not None:
            raise bad("base {!r} has a base itself".format(v.base))
        if b.config != v.config:
            raise bad("base {!r} runs in {}, this set in {}".format(v.base, b.config, v.config))
        missing = set(v.families) - set(b.families)
        if missing:
            raise bad("families {} are not among the base's".format(sorted(missing)))
        lost = [k for k in b.keys if k not in v.keys]
        if lost:  # the base's branch stays set: the set assigns every key of its base (the varied one may differ)
            raise bad("does not assign the base's keys {}".format(lost))
        sketch = [f for f in v.families if family_store(f, families) != "full"]
        if sketch:
            raise bad("a based set needs a full store (yldot kept); {} keep a sketch".format(sketch))
    return list(out.values())


def plan(repo=inputs.REPO, overrides=None, sets=None, family=None):
    """Every variant of the inventory, in inventory order (then the listed values in their order), then the
    combination sets in file order (sets: a load_sets() list, default combinations.toml). A value list with
    `families` runs in those families, and the key keeps its default-rule id in the others; family: only the
    variants and sets that run in that family (Variant.runs_in), None: all of them."""
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
            fams = tuple(o["families"]) if "families" in o else None
            for v in values:
                out.append(Variant(id="{}={}".format(key, v), rule="value", value=v, reason=reason, families=fams,
                                   **common))
            if "others" in o:
                out.append(Variant(id=key + "=other", rule="value", excluded=True, families=fams,
                                   reason="values other than {}: {}".format(list(values), o["others"]), **common))
            rest = tuple(f for f in all_families() if f not in fams) if fams else ()
            if rest and "rest_exclude" in o:  # EXCLUDED in the families the list does not run in
                out.append(Variant(id=key, rule="default", excluded=True, reason=o["rest_exclude"], families=rest,
                                   **common))
            elif rest:  # the families the list does not run in keep the default rule (AIUE-257, owner 2026-11-12)
                out.append(Variant(id=key, rule="default", families=rest, **common))
        elif "bound" in o:
            out.append(Variant(id=key, rule="bounded", bound=o["bound"], reason=o["reason"], **common))
        elif "charge" in o:
            out.append(Variant(id=key, rule="charge", bound=o["charge"], reason=o["reason"], **common))
        else:
            out.append(Variant(id=key, rule="default", reason=o.get("reason", ""), **common))
    out.extend(load_sets(repo=repo, overrides=ov) if sets is None else sets)
    if family is not None:
        out = [v for v in out if v.runs_in(family)]
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
    if rule == "charge":
        # an integer ion charge (bbb.ziin): d+1 on the positive slots among the first `bound` (the hydrogenic ions,
        # com.nhsp); the atoms (0) and the slots above `bound` (impurity charge states) keep d
        if kind != "f" or d.ndim != 1:
            raise TypeError("charge rule on dtype {} with {} dimensions".format(d.dtype, d.ndim))
        v = d.copy()
        h = v[:bound]
        v[:bound] = np.where(h > 0, h + 1, h)
        return v
    if rule != "default":
        raise ValueError("rule {!r}".format(rule))
    if kind == "i":
        return np.where((d == 0) | (d == 1), 1 - d, d + 1).astype(d.dtype)
    return np.where(d == 0, 1.0, d * 1.1).astype(d.dtype)


def set_value(d, kind, x, at=()):
    """One key's value in a combination set, from the family value d (d's dtype is kept; d is not changed).
    value: x at every element of d[at] (all of d without at); scale: d[at] * x (real only); cycle: along the first
    axis of d[at] (the 0:nx+1 axis, checked by load_sets), element i takes x[i % len(x)], broadcast over the rest."""
    d = np.asarray(d)
    if d.dtype.kind not in "if":
        raise TypeError("no set value for dtype {}".format(d.dtype))
    at = tuple(at)
    if len(at) > d.ndim:
        raise ValueError("at {} on an array of {} dimensions".format(list(at), d.ndim))
    v = d.copy()
    idx = at if at else Ellipsis
    if kind == "value":
        new = np.asarray(x).astype(d.dtype)
        if new != x:
            raise ValueError("value {!r} is not representable as {}".format(x, d.dtype))
        v[idx] = new
    elif kind == "scale":
        if d.dtype.kind != "f":
            raise TypeError("scale on dtype {}".format(d.dtype))
        v[idx] = v[idx] * x
    elif kind == "cycle":
        sub = v[at] if at else v
        if not isinstance(sub, np.ndarray) or sub.ndim < 1:
            raise ValueError("cycle needs an axis after at {}".format(list(at)))
        n = sub.shape[0]
        new = np.array([x[i % len(x)] for i in range(n)]).astype(d.dtype)
        if (new != np.array([x[i % len(x)] for i in range(n)])).any():
            raise ValueError("cycle {!r} is not representable as {}".format(list(x), d.dtype))
        sub[...] = new.reshape((n,) + (1,) * (sub.ndim - 1))
    else:
        raise ValueError("kind {!r}".format(kind))
    return v


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
    if v.rule == "set":
        return _apply_set(v, spec, previous, uedge)
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
        if v.rule in ("bounded", "charge"):
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


def _apply_set(v, spec, previous, uedge):
    """apply() for a combination set: read d of every key before any assignment, compute (or replay) each value,
    assign them in file order, then read every key back. d and applied are dicts {key: encode form}. Every key
    unallocated gives status "unallocated"; some of them is an error (the set's families are wrong)."""
    keys = list(v.keys)
    live, d, missing = {}, {}, []
    for k in keys:
        pkg_name, _, name = k.partition(".")
        pkg = getattr(uedge, pkg_name)
        try:
            x = getattr(pkg, name)
        except Exception as e:
            if "unallocated" not in str(e):
                raise
            missing.append(k)
            continue
        if isinstance(x, np.ndarray) and x.size == 0:
            missing.append(k)
            continue
        live[k] = (pkg, name, x)
        d[k] = np.array(x)
    record = {"id": v.id, "key": v.key, "keys": keys, "phase": v.phase, "config": v.config}
    if missing:
        if len(missing) == len(keys):
            record.update(d=None, status="unallocated", applied=None)
            return record
        raise ValueError("{}: {} unallocated while {} are allocated: limit the set's families"
                         .format(v.id, missing, sorted(set(keys) - set(missing))))
    record["d"] = {k: encode(d[k]) for k in keys}
    if previous is not None:
        # the second POST of the timestep configuration, key by key as in apply()
        second = {}
        for k in keys:
            same = {f: decode(previous[f][k]) for f in ("d", "applied")}
            found = [f for f, a in same.items() if a.shape == d[k].shape and a.tobytes() == d[k].tobytes()]
            if not found:
                raise Mismatch("{}: {}: the live value at the second timestep pass is neither d nor the applied "
                               "value of the first".format(v.id, k))
            second[k] = "reset" if "d" in found else "kept"
            d[k] = same["d"]
        record["d"] = previous["d"]
        record["second_pass"] = second
    replay = spec.get("replay")
    if replay is not None:
        if not isinstance(replay, dict) or sorted(replay) != sorted(keys):
            raise ValueError("{}: a set's replay is a dict over its keys {}".format(v.id, keys))
        applied = {k: decode(replay[k]) for k in keys}
        for k in keys:
            if applied[k].shape != d[k].shape or applied[k].dtype != d[k].dtype:
                raise ValueError("{}: {}: replay value {} {} does not fit the variable's {} {}".format(
                    v.id, k, applied[k].dtype, applied[k].shape, d[k].dtype, d[k].shape))
    elif previous is not None:
        applied = {k: decode(previous["applied"][k]) for k in keys}
    else:
        applied = {k: set_value(d[k], kind, x, at) for k, kind, x, at in v.assign}
    for k in keys:
        pkg, name, x = live[k]
        if isinstance(x, np.ndarray):
            x[...] = applied[k]
        else:
            setattr(pkg, name, applied[k].item())
    for k in keys:
        pkg, name, _ = live[k]
        back = np.array(getattr(pkg, name))
        if back.dtype != applied[k].dtype or back.tobytes() != applied[k].tobytes():
            raise RuntimeError("{}: {}: not stored as applied".format(v.id, k))
    changed = any(applied[k].tobytes() != d[k].tobytes() for k in keys)
    record.update(status="applied" if changed else "equal-to-d", applied={k: encode(applied[k]) for k in keys})
    return record
