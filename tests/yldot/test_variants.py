"""The variant tests of the yldot suite (AIUE-96; PRD sections 4, 7.2 and 7.4; decision 27): every stored variant of
class SENSITIVE, EQSET, INERT or INVALID of every family whose manifest classifies variants, one fresh evaluation each.

SENSITIVE  its recorded applied value replayed and checked against its stored reference, yldot and the Jacobian-flag
           difference yldot_J - yldot, under tol_i(variant) (AIUE-94 D8) through Store.check
           (variant_tolerances.check_sensitive); in a sketch store (the owner families), which keeps no dense
           reference, the replayed run's yldot takes the reference's place in D8's rule and the sketch comparator
           decides (owner, 2026-10-24, AIUE-99 Q2). On a macOS build that may contract into FMA instructions (the build
           record, harness/build.py) a mismatch is reported as a BuildLimitWarning, not failed (owner, 2026-10-23,
           AIUE-96 D1); without a build record it fails, naming that (D4).
EQSET      (another neq or equation layout, T24; owner, 2026-11-24) its recorded applied value replayed and checked by
           variant_tolerances.eqset_result: its index truth, row order, masks and stored layout; its stored reference
           under make_references.eqset_tolerance; and the blocks it left unmoved at generation against the live default
           within its tol_i. A finite value out of tolerance against the stored reference alone is reported on an FMA
           macOS build as for SENSITIVE; everything else fails.
INERT      its recorded applied value replayed: yldot and yldot_J equal the live default of its configuration within
           the default's tol_i (PRD 7.3).
INVALID    evaluated with the rules (no applied value is recorded): make_references.classify still gives INVALID, for
           the same kind of reason (error, crash, timeout, neq (0 only, T196), non-finite); a different text is
           printed, not failed. A bounds-check entry (the --checkbounds audit's runtime error, reproducible only in
           that build) pins the serial build's outcome instead: the serial run must give the class and, for INVALID,
           the kind of reason its reason ends with 'serial build: ...' (owner, 2026-10-28, AIUE-95 D5). An entry in
           NOT_REPRODUCIBLE, whose serial outcome follows the heap layout, accepts each outcome listed there instead
           (owner, 2026-11-27, T192).
A combination set (AIUE-257) is run like a variant, its recorded {key: value} replayed; a set with a base compares
with its base set's live result (the base's stored applied value replayed) instead of the default, for INERT and
INVALID alike, as make_references classified it.
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
    """The kind of an INVALID reason: its first word (error, crash, timeout, neq, non-finite); neq only "neq N -> 0"."""
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


@pytest.mark.parametrize("family, vid", params("EQSET"))
def test_eqset(runner, plan, stores, default, record, family, vid):
    s = stores(family)
    e = s.manifest["variables"][vid]
    row = vt.check_eqset(family, s, runner, plan[vid], e, None, default(family, e["config"]))
    if row["ok"]:
        return
    if "status" in row:
        pytest.fail("{}-{}: {}".format(family, vid, row["message"]), pytrace=False)
    what = "{}-{}: largest {} = {:.3g}\n{}".format(
        family, vid, "ratio (sketch |dP| / bound, added rows |d_i| / tol_i)" if s.kind == "sketch"
        else "|d_i| / tol_i(variant)", row["ratio"], row["report"])
    if row.get("hard"):  # the layout, an unmoved block or a non-finite entry: not a limit of the build
        pytest.fail(what, pytrace=False)
    if record is None:
        pytest.fail("{}\n{}".format(build.MISSING, what), pytrace=False)
    if build.fma_contraction(record) and math.isfinite(row["ratio"]):
        warnings.warn(build.BuildLimitWarning("{}, on a macOS FMA-contracting build (owner D1, AIUE-96): {}".format(
            build.REPORTED, what.splitlines()[0])))
        return
    pytest.fail(what, pytrace=False)


OFF = {"ok": False, "ratio": 3.0, "report": "off"}
MAC, LINUX = ({"platform": p, "forthon_fopt": "-O3", "fargs": "-g -O3"} for p in ("darwin", "linux"))


@pytest.mark.parametrize("row, rec, outcome", [
    ({"ok": True, "ratio": 0.5}, LINUX, "pass"),
    ({"ok": True, "ratio": 0.5}, None, "pass"),
    (OFF, LINUX, "fail"),
    (OFF, None, "fail"),
    (OFF, MAC, "report"),
    (dict(OFF, hard=True), MAC, "fail"),  # the layout, the masks or an unmoved block: never a limit of the build
    (dict(OFF, ratio=float("inf")), MAC, "fail"),
    ({"ok": False, "ratio": float("inf"), "status": "error", "message": "error: boom"}, MAC, "fail"),
])
def test_eqset_outcome(monkeypatch, row, rec, outcome):
    """test_eqset's rule on every kind of row of check_eqset, which gets the live default of the entry's configuration."""
    from types import SimpleNamespace

    seen = []
    monkeypatch.setattr(vt, "check_eqset", lambda *a: seen.append(a) or row)
    s = SimpleNamespace(kind="full", manifest={"variables": {"v": {"config": "timestep"}}})

    def check():
        test_eqset("runner", {"v": "plan v"}, lambda f: s, lambda f, config: (f, config), rec, "fam", "v")

    if outcome == "fail":
        with pytest.raises(pytest.fail.Exception, match="fam-v"):
            check()
    elif outcome == "report":
        with pytest.warns(build.BuildLimitWarning, match=build.REPORTED):
            check()
    else:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            check()
    assert seen == [("fam", s, "runner", "plan v", {"config": "timestep"}, None, ("fam", "timestep"))]


def comparison_base(runner, plan, default, family, e):
    """What a variant is compared with: the live default of its configuration, or for a set with a base (AIUE-257)
    the base set's live result, its stored applied value replayed."""
    if not e.get("base"):
        return default(family, e["config"])
    b = MANIFESTS[family]["variables"][e["base"]]
    rb = runner.evaluate(family, variant=plan[e["base"]], replay=b["applied"])
    assert rb.ok, "base set {}: {}".format(e["base"], describe(rb))
    return rb.data


@pytest.mark.parametrize("family, vid", params("INERT"))
def test_inert(runner, plan, default, family, vid):
    e = MANIFESTS[family]["variables"][vid]
    r = runner.evaluate(family, variant=plan[vid], replay=e["applied"])
    assert r.ok, describe(r)
    base = comparison_base(runner, plan, default, family, e)
    assert mr.same_index(r.data, base), "{}-{}: the equation layout differs from the default's".format(family, vid)
    fdir = family_dir(family)
    tol = mr.tolerance(fdir, base["yldot"], e["config"], compare.index_map(base, compare.load_regions(fdir)))
    ratio = max(vt.worst(r.data["yldot"] - base["yldot"], tol), vt.worst(r.data["yldot_J"] - base["yldot_J"], tol))
    assert ratio <= 1, "{}-{}: INERT variant differs from the default: largest |d_i| / tol_i = {:.3g}".format(
        family, vid, ratio)


# Bounds-check entries whose serial outcome is not reproducible, with the outcomes test_invalid accepts for them,
# (class, kind of an INVALID reason, else None), instead of their pin (owner, 2026-11-27, T192). d_mols' read of
# ni(..., nisp + 1) past the end of ni (bbb/pandf_boundary.m:3473-3475, T109) gives SENSITIVE when the chunk after ni
# varies with yl (logni) and INVALID 'error: ... jac_lu_decomp ... ierr = -5' (a zero Jacobian row) when it does not;
# which follows the child's heap layout, which follows the environment's size (T192's CI probe, run 45867784394: 8 of
# 1101 runs). test_not_reproducible fails once an entry no longer pins one of its outcomes: remove it with T109's fix.
NOT_REPRODUCIBLE = {
    ("d_mols", "set:plate-mol-zerograd"): (("SENSITIVE", None), ("INVALID", "error")),
}


def invalid_problem(stored, cls, reason, accept=None):
    """Why the serial run (class cls, INVALID reason) does not match the stored INVALID reason; None if it does. A
    reason with a 'serial build: ...' suffix (a bounds-check entry) pins that class and kind (owner, 2026-10-28,
    AIUE-95 D5); any other needs INVALID with the stored kind. accept: the outcomes of a NOT_REPRODUCIBLE entry,
    which replace its pin (T192)."""
    if accept is not None:
        got = (cls, kind(reason) if cls == "INVALID" else None)
        if got in accept:
            return None
        return "stored {!r}, not reproducible: accepts {}, the serial build now gives {}{}".format(
            stored, " or ".join(c + (" " + k if k else "") for c, k in accept), cls, " " + reason if reason else "")
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
    ("neq 420 -> 0", "EQSET", "neq 420 -> 360", False),
    ("bounds-check: bbb/x.F:1: Index (serial build: EQSET)", "EQSET", "neq 420 -> 360", True),
    ("bounds-check: bbb/x.F:1: Index (serial build: EQSET)", "INVALID", "error: boom", False),
])
def test_invalid_problem(stored, cls, reason, ok):
    assert (invalid_problem(stored, cls, reason) is None) == ok


PINNED = "bounds-check: bbb/x.F:1: Index (serial build: SENSITIVE)"
BOTH = (("SENSITIVE", None), ("INVALID", "error"))


@pytest.mark.parametrize("cls, reason, accept, ok", [
    ("SENSITIVE", "max |diff|/tol = 3.9e+07", BOTH, True),
    ("INVALID", "error: RuntimeError: Error in subroutine jac_lu_decomp: ierr = -5", BOTH, True),
    ("INVALID", "error: RuntimeError: Error in subroutine jac_lu_decomp: ierr = -5", None, False),  # the pin alone
    ("INVALID", "non-finite yldot or yldot_J at rows [1]", BOTH, False),  # another kind
    ("INVALID", "crash: exit code -11", BOTH, False),
    ("INERT", "", BOTH, False),  # another class
    ("MARGINAL", "max |diff|/tol = 0.5", BOTH, False),
    ("SENSITIVE", "max |diff|/tol = 3.9e+07", (("INVALID", "error"),), False),
])
def test_invalid_problem_accept(cls, reason, accept, ok):
    """A NOT_REPRODUCIBLE entry's accepted outcomes replace its pin: each passes, any other class or kind fails."""
    assert (invalid_problem(PINNED, cls, reason, accept) is None) == ok


@pytest.mark.parametrize("family, vid, outcome, ok", [
    ("d_mols", "set:plate-mol-zerograd", ("INVALID", "error: RuntimeError: jac_lu_decomp ierr = -5"), True),
    ("d_mols", "set:plate-mol-zerograd", ("SENSITIVE", "max |diff|/tol = 3.9e+07"), True),
    ("fam", "pinned", ("INVALID", "error: RuntimeError: jac_lu_decomp ierr = -5"), False),  # no exception: the pin
    ("fam", "pinned", ("SENSITIVE", "max |diff|/tol = 3.9e+07"), True),
])
def test_invalid_accepts(monkeypatch, family, vid, outcome, ok):
    """test_invalid hands a NOT_REPRODUCIBLE entry's outcomes to invalid_problem, and only that entry's."""
    from types import SimpleNamespace

    monkeypatch.setitem(MANIFESTS, "fam", {"variables": {"pinned": {"class": "INVALID", "reason": PINNED,
                                                                    "config": "steady"}}})
    monkeypatch.setattr(mr, "classify", lambda r, base, tol: (outcome[0], outcome[1], None))
    monkeypatch.setattr(mr, "tolerance", lambda *a: None)
    monkeypatch.setattr(compare, "index_map", lambda *a: None)
    monkeypatch.setattr(compare, "load_regions", lambda *a: None)
    monkeypatch.setattr(sys.modules[__name__], "family_dir", Path)
    runner = SimpleNamespace(evaluate=lambda *a, **k: None)
    base = {"yldot": None}

    def check():
        test_invalid(runner, {vid: "plan"}, lambda f, config: base, family, vid)

    if ok:
        check()
    else:
        with pytest.raises(AssertionError, match="serial build now gives INVALID"):
            check()


def stale_exceptions(table, manifests):
    """The entries of a NOT_REPRODUCIBLE table that are not a stored INVALID bounds-check entry of their family whose
    pinned outcome is one of their accepted outcomes."""
    stale = []
    for (family, vid), accept in table.items():
        e = (manifests.get(family) or {}).get("variables", {}).get(vid)
        pinned = mr.serial_outcome(e["reason"]) if e and e["class"] == "INVALID" else None
        if pinned is None or not str(e["reason"]).startswith("bounds-check:") or pinned not in accept:
            stale.append("{}-{}: {}".format(family, vid, "absent" if e is None else (e["class"], e["reason"])))
    return stale


@pytest.mark.parametrize("entry, ok", [
    ({"class": "INVALID", "reason": PINNED}, True),
    (None, False),  # removed by a regeneration
    ({"class": "SENSITIVE", "reason": "max |diff|/tol = 3.9e+07"}, False),  # fixed: no longer INVALID
    ({"class": "SENSITIVE", "reason": PINNED}, False),  # not INVALID, whatever its reason says
    ({"class": "INVALID", "reason": "error: RuntimeError: boom"}, False),  # INVALID without a pin
    ({"class": "INVALID", "reason": "bounds-check: bbb/x.F:1: Index (serial build: INERT)"}, False),  # another pin
    ({"class": "INVALID", "reason": "neq 420 -> 0 (serial build: SENSITIVE)"}, False),  # not a bounds-check entry
])
def test_stale_exceptions(entry, ok):
    manifests = {"fam": {"variables": {} if entry is None else {"v": entry}}}
    assert (stale_exceptions({("fam", "v"): BOTH}, manifests) == []) == ok


def test_not_reproducible():
    """Every NOT_REPRODUCIBLE entry still pins one of its accepted outcomes; once a fix and a regeneration change it
    (T109 for d_mols), the exception has to go."""
    stale = stale_exceptions(NOT_REPRODUCIBLE, MANIFESTS)
    assert not stale, "NOT_REPRODUCIBLE entries that no longer pin an accepted outcome: {}".format(stale)


@pytest.mark.parametrize("family, vid", params("INVALID"))
def test_invalid(runner, plan, default, family, vid):
    e = MANIFESTS[family]["variables"][vid]
    r = runner.evaluate(family, variant=plan[vid])
    base = comparison_base(runner, plan, default, family, e)
    fdir = family_dir(family)
    tol = mr.tolerance(fdir, base["yldot"], e["config"], compare.index_map(base, compare.load_regions(fdir)))
    cls, reason, finding = mr.classify(r, base, tol)
    problem = invalid_problem(e["reason"], cls, reason or finding, NOT_REPRODUCIBLE.get((family, vid)))
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
