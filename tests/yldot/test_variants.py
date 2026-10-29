"""The variant tests of the yldot suite (AIUE-96; PRD sections 4, 7.2 and 7.4; decision 27): every stored variant of
class SENSITIVE, INERT or INVALID of every family whose manifest classifies variants, one fresh evaluation each.

SENSITIVE  its recorded applied value replayed and checked against its stored reference, yldot and the Jacobian-flag
           difference yldot_J - yldot, under tol_i(variant) (AIUE-94 D8) through Store.check
           (variant_tolerances.check_sensitive); in a sketch store (the owner families), which keeps no dense
           reference, the replayed run's yldot takes the reference's place in D8's rule and the sketch comparator
           decides (owner, 2026-10-24, AIUE-99 Q2). On a macOS build that may contract into FMA instructions (the build
           record, harness/build.py) a mismatch is reported as a BuildLimitWarning, not failed (owner, 2026-10-23,
           AIUE-96 D1); without a build record it fails, naming that (D4).
INERT      its recorded applied value replayed: yldot and yldot_J equal the live default of its configuration within
           the default's tol_i (PRD 7.3).
INVALID    evaluated with the rules (no applied value is recorded): make_references.classify still gives INVALID, for
           the same kind of reason (error, crash, timeout, neq, equation layout, non-finite); a different text is
           printed, not failed. A bounds-check entry (the --checkbounds audit's runtime error, reproducible only in
           that build) pins the serial build's outcome instead: the serial run must give the class and, for INVALID,
           the kind of reason its reason ends with 'serial build: ...' (owner, 2026-10-28, AIUE-95 D5).
MARGINAL and EXCLUDED variants are never run (PRD 7.2); test_inventory.py checks their reasons. The test ids are
<family>-<variant id>, so -k "d_c and (cfvisx or methe)" selects by family and variable. An owner family's variants
(AIUE-99) are marked nightly (PRD section 4).
"""
import math
import re
import sys
import warnings
from contextlib import ExitStack
from pathlib import Path

import pytest

from yldot.harness import FAMILIES, build, compare, open_store, variants
from yldot.harness import manifest as mf
from yldot.harness.process import family_dir

SUITE = Path(__file__).resolve().parent
sys.path.insert(0, str(SUITE / "tools"))

import make_references as mr  # noqa: E402
import variant_tolerances as vt  # noqa: E402

FAMILY_NAMES = sorted(p.name for p in FAMILIES.iterdir() if (p / "input.py").is_file())
MANIFESTS = {f: m for f in FAMILY_NAMES if mf.path(f).is_file() for m in [mf.load(f)] if m.get("variables")}
OWNER = {f for f in MANIFESTS if mf.owner_family(f)}


def params(cls):
    return [pytest.param(f, vid, id="{}-{}".format(f, vid), marks=[pytest.mark.nightly] if f in OWNER else [])
            for f, m in MANIFESTS.items() for vid, e in m["variables"].items() if e["class"] == cls]


def describe(res):
    return "{} {}: {}: {}\n{}".format(res.family, res.config, res.status, res.message, res.log_tail)


def kind(reason):
    """The kind of an INVALID reason: its first word (error, crash, timeout, neq, equation, non-finite)."""
    return re.match(r"[^:\s]*", reason).group()


@pytest.fixture(scope="module")
def plan():
    return {v.id: v for v in variants.plan()}


@pytest.fixture(scope="module")
def stores():
    with ExitStack() as stack:
        cache = {}

        def get(family):
            if family not in cache:
                cache[family] = stack.enter_context(open_store(family))
            return cache[family]
        yield get


@pytest.fixture(scope="module")
def default(runner):
    """The live default evaluation of (family, config), once per module."""
    cache = {}

    def get(family, config):
        if (family, config) not in cache:
            res = runner.evaluate(family, config=config)
            assert res.ok, describe(res)
            cache[family, config] = res.data
        return cache[family, config]
    return get


@pytest.fixture(scope="module")
def record():
    return build.info()


@pytest.mark.parametrize("family, vid", params("SENSITIVE"))
def test_sensitive(runner, plan, stores, record, family, vid):
    s = stores(family)
    e = s.manifest["variables"][vid]
    row = vt.check_sensitive(family, s, runner, plan[vid], e, None)
    if row["ok"]:
        return
    if "status" in row:
        pytest.fail("{}-{}: {}".format(family, vid, row["message"]), pytrace=False)
    what = "{}-{}: largest {} = {:.3g}\n{}".format(
        family, vid, "sketch |dP| / bound" if s.kind == "sketch" else "|d_i| / tol_i(variant)", row["ratio"],
        row.get("report", ""))
    if record is None:
        pytest.fail("{}\n{}".format(build.MISSING, what), pytrace=False)
    if build.fma_contraction(record) and math.isfinite(row["ratio"]):  # a non-finite entry is never round-off
        warnings.warn(build.BuildLimitWarning("{}, on a macOS FMA-contracting build (owner D1, AIUE-96): {}".format(
            build.REPORTED, what.splitlines()[0])))
        return
    pytest.fail(what, pytrace=False)


@pytest.mark.parametrize("family, vid", params("INERT"))
def test_inert(runner, plan, default, family, vid):
    e = MANIFESTS[family]["variables"][vid]
    r = runner.evaluate(family, variant=plan[vid], replay=e["applied"])
    assert r.ok, describe(r)
    base = default(family, e["config"])
    assert mr.same_index(r.data, base), "{}-{}: the equation layout differs from the default's".format(family, vid)
    fdir = family_dir(family)
    tol = mr.tolerance(fdir, base["yldot"], e["config"], compare.index_map(base, compare.load_regions(fdir)))
    ratio = max(vt.worst(r.data["yldot"] - base["yldot"], tol), vt.worst(r.data["yldot_J"] - base["yldot_J"], tol))
    assert ratio <= 1, "{}-{}: INERT variant differs from the default: largest |d_i| / tol_i = {:.3g}".format(
        family, vid, ratio)


def invalid_problem(stored, cls, reason):
    """Why the serial run (class cls, INVALID reason) does not match the stored INVALID reason; None if it does. A
    reason with a 'serial build: ...' suffix (a bounds-check entry) pins that class and kind (owner, 2026-10-28,
    AIUE-95 D5); any other needs INVALID with the stored kind."""
    pinned = mr.serial_outcome(stored)
    want_class, want_kind = pinned if pinned is not None else ("INVALID", kind(stored))
    if cls != want_class:
        return "stored {!r}: the serial build now gives {}{}".format(stored, cls, " " + reason if reason else "")
    if want_class == "INVALID" and kind(reason) != want_kind:
        return "stored reason {!r}, now {!r}".format(stored, reason)
    return None


@pytest.mark.parametrize("stored, cls, reason, ok", [
    ("bounds-check: api/sputt.F:245: Index (serial build: INERT)", "INERT", "", True),
    ("bounds-check: api/sputt.F:245: Index (serial build: INERT)", "SENSITIVE", "", False),
    ("bounds-check: bbb/x.F:1: Index (serial build: neq 420 -> 360)", "INVALID", "neq 420 -> 360", True),
    ("bounds-check: bbb/x.F:1: Index (serial build: neq 420 -> 360)", "INVALID", "error: boom", False),
    ("bounds-check: bbb/x.F:1: Index (serial build: error: x (y))", "INVALID", "error: other", True),
    ("neq 420 -> 360", "INVALID", "neq 420 -> 300", True),
    ("neq 420 -> 360", "INVALID", "error: boom", False),
    ("neq 420 -> 360", "INERT", "", False),
])
def test_invalid_problem(stored, cls, reason, ok):
    assert (invalid_problem(stored, cls, reason) is None) == ok


@pytest.mark.parametrize("family, vid", params("INVALID"))
def test_invalid(runner, plan, default, family, vid):
    e = MANIFESTS[family]["variables"][vid]
    r = runner.evaluate(family, variant=plan[vid])
    base = default(family, e["config"])
    fdir = family_dir(family)
    tol = mr.tolerance(fdir, base["yldot"], e["config"], compare.index_map(base, compare.load_regions(fdir)))
    cls, reason, finding = mr.classify(r, base, tol)
    problem = invalid_problem(e["reason"], cls, reason or finding)
    assert problem is None, "{}-{}: {}".format(family, vid, problem)
    if reason != e["reason"]:
        print("{}-{}: stored reason {!r}, now {!r}".format(family, vid, e["reason"], reason))


@pytest.mark.parametrize("rec, expected", [
    ({"platform": "darwin", "forthon_fopt": "-O3 -ftree-vectorize", "fargs": "-g -O3"}, True),
    ({"platform": "darwin", "forthon_fopt": "-O3", "fargs": "-g -O2"}, True),
    ({"platform": "darwin", "forthon_fopt": "-O3", "fargs": "-g -O3 -ffp-contract=off"}, False),
    ({"platform": "darwin", "forthon_fopt": "-O3", "fargs": "-g -O0"}, False),
    ({"platform": "darwin", "forthon_fopt": "-O3", "fargs": "-g -Og"}, False),
    ({"platform": "linux", "forthon_fopt": "-O3", "fargs": "-g -O3"}, False),
    (None, False),
])
def test_fma_contraction(rec, expected):
    """The last -O level of Forthon's flags and --fargs decides; -ffp-contract=off turns contraction off."""
    assert build.fma_contraction(rec) is expected


def test_build_info_found(record):
    """build.info() finds the children's build record (D4): AIUE-181's schema with the fields fma_contraction reads
    (test_build_flags.py's test_installed_record checks its values)."""
    assert record is not None, build.MISSING
    assert record["schema"] == 1 and {"platform", "forthon_fopt", "fargs"} <= set(record)
