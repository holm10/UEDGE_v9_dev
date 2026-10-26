"""The locality check of the yldot suite (AIUE-100; PRD section 7.5, story 6): per family with a stored locality pattern,
one fresh steady evaluation with the jac_calc protocol over every column (harness/locality.py, state.py step 8c),
compared with the stored pattern (locality.compare_pattern).

Each live run must also reproduce, besides the pattern:
    f00 (the full evaluation with the Jacobian flag) within the per-entry tolerance of the stored default plus its
    Jacobian-flag difference (PRD 7.5 step 1, a cross-check between the two checks);
    every column's restored full evaluation f00 bit for bit (no stale column);
    the reference's delta, which must be family.toml's [locality].delta_loc.
The pure-Python cases below pin compare_pattern's band rules on synthetic entries.
"""
import math
import sys
import tomllib
import warnings
from pathlib import Path

import numpy as np
import pytest

from yldot.harness import FAMILIES, build, compare, open_store, variants
from yldot.harness import locality as L
from yldot.harness import manifest as mf
from yldot.harness.compare import listed
from yldot.harness.process import family_dir

SUITE = Path(__file__).resolve().parent
sys.path.insert(0, str(SUITE / "tools"))

import make_references as mr  # noqa: E402
import variant_tolerances as vt  # noqa: E402

FAMILY_NAMES = sorted(p.name for p in FAMILIES.iterdir() if (p / "input.py").is_file())
CONFIGURED = [f for f in FAMILY_NAMES if L.load_config(FAMILIES / f) is not None]
# the five small families (AIUE-88): with sigma.h5 and not owner families, whose sigma.h5 is a release asset (AIUE-92)
SMALL = sorted(p.parent.name for p in FAMILIES.glob("*/sigma.h5") if not mf.owner_family(p.parent.name))
# the owner families' default locality runs in the nightly tier (PRD 7.5 "Columns and tiers"; AIUE-101)
FAMILY_PARAMS = [pytest.param(f, marks=[pytest.mark.nightly] if mf.owner_family(f) else []) for f in CONFIGURED]
# every stored variant pattern (manifest locality_variants), nightly (AIUE-101)
VARIANT_PARAMS = [pytest.param(f, vid, id="{}-{}".format(f, vid), marks=[pytest.mark.nightly])
                  for f in CONFIGURED if mf.path(f).is_file()
                  for vid in sorted(mf.load(f).get("locality_variants", {}))]


@pytest.fixture(scope="module")
def tol():
    with open(SUITE / "tolerances.toml", "rb") as f:
        return tomllib.load(f)


def test_locality_configured():
    """Every small family runs the locality check in the PR tier (PRD 7.5): [locality] in family.toml and a stored,
    guarded pattern in its reference."""
    missing = [f for f in SMALL if f not in CONFIGURED]
    assert not missing, "small families without [locality] in family.toml: {}".format(missing)
    unguarded = [f for f in SMALL if "locality/steady" not in mf.load(f).get("guarded", {})]
    assert not unguarded, "small families whose reference stores no locality pattern: {}".format(unguarded)


def test_locality_everywhere():
    """AIUE-101: every family runs the locality check (the owner families in the nightly tier), and each stores the
    patterns of exactly its variant_scope (family.toml [locality].variants and .excluded)."""
    missing = [f for f in FAMILY_NAMES if f not in CONFIGURED]
    assert not missing, "families without [locality] in family.toml: {}".format(missing)
    for f in CONFIGURED:
        m = mf.load(f)
        want = set(L.variant_scope(L.load_config(FAMILIES / f), m["variables"]))
        got = set(m.get("locality_variants", {}))
        assert got == want, "{}: variant patterns not in scope {}, in scope without a pattern {}".format(
            f, listed(sorted(got - want)), listed(sorted(want - got)))


@pytest.mark.parametrize("family", FAMILY_PARAMS)
def test_locality(tol, runner, family):
    cfg = L.load_config(FAMILIES / family)
    r = runner.evaluate(family, locality=cfg["delta_loc"], columns=mr.locality_columns(cfg))
    assert r.ok, (r.status, r.message, r.log_tail)
    run = r.data["locality"]
    with open_store(family) as s:
        stored = s.locality("steady")
        assert stored is not None, "{}: the reference stores no locality pattern".format(family)
        delta, ref = stored
        assert delta == cfg["delta_loc"] == run["delta"], (
            "{}: the reference's delta {} differs from family.toml delta_loc {}: regenerate".format(
                family, delta, cfg["delta_loc"]))
        cols = s.locality_columns("steady")
        assert (cols is None and run["columns"] is None) or (
            cols is not None and run["columns"] is not None and np.array_equal(cols, run["columns"])), (
            "{}: the stored locality columns differ from family.toml's selection: regenerate".format(family))
        imap = compare.index_map(r.data, compare.load_regions(family))
        t = compare.tolerances(s.default("steady"), s.sigma("steady"), tol["rtol"], tol["rule"]["k"], imap).tol
        c = compare.compare(run["f00"], s.default("steady") + s.jflag("steady"), t, imap, worst=3)
        assert c.ok, "{} locality: f00 differs from the stored default + Jacobian-flag difference\n{}".format(
            family, c.report())
        assert not run["stale"].size, "{} locality: {} stale columns, rows {}".format(
            family, run["stale"].size, listed(run["stale"] + 1))
        new = L.Entries.of(run["entries"])
        cmp = L.compare_pattern(ref, new, t, L.rtol_rows(tol["rtol"], imap), float(cfg["m_loc"]), imap, family)
        if not cmp.ok:
            pytest.fail(cmp.report(), pytrace=False)


@pytest.fixture(scope="module")
def plan():
    return {v.id: v for v in variants.plan()}


@pytest.mark.parametrize("family, vid", VARIANT_PARAMS)
def test_locality_variant(tol, runner, plan, family, vid):
    """AIUE-101: a variant's locality pattern (stored as its difference from the default's, Store.locality_pattern),
    with its applied value replayed, over the family's columns (a column set: the special cells only). The run's
    f00 = yldot_J is checked in the child; besides: a SENSITIVE variant's result through variant_tolerances.check_result
    (macOS FMA builds report, AIUE-96 D1), an INERT one's f00 against the stored default + Jacobian-flag difference
    of its configuration, a MARGINAL one's by the child's check only. The pattern is scored with the tolerance
    generation used (make_references.locality_tolerance)."""
    cfg = L.load_config(FAMILIES / family)
    with open_store(family) as s:
        e = s.manifest["variables"][vid]
        config = e["config"]
        r = runner.evaluate(family, variant=plan[vid], replay=e["applied"], locality=cfg["delta_loc"],
                            columns=mr.locality_columns(cfg, variant=True))
        assert r.ok, (r.status, r.message, r.log_tail)
        run = r.data["locality"]
        assert not run["stale"].size, "{}-{} locality: {} stale columns, rows {}".format(
            family, vid, run["stale"].size, listed(run["stale"] + 1))
        fdir = family_dir(family)
        imap = compare.index_map(r.data, compare.load_regions(fdir))
        if e["class"] == "SENSITIVE":
            row = vt.check_result(family, s, plan[vid], e, r)
            if not row["ok"]:
                what = "{}-{} locality: the run differs from the stored variant, largest ratio {:.3g}\n{}".format(
                    family, vid, row["ratio"], row.get("report", ""))
                record = build.info()
                if record is not None and build.fma_contraction(record) and math.isfinite(row["ratio"]):
                    warnings.warn(build.BuildLimitWarning("{}, on a macOS FMA-contracting build (owner D1, AIUE-96): "
                                                          "{}".format(build.REPORTED, what.splitlines()[0])))
                else:
                    pytest.fail(what, pytrace=False)
        elif e["class"] == "INERT":
            t = compare.tolerances(s.default(config), s.sigma(config), tol["rtol"], tol["rule"]["k"], imap).tol
            c = compare.compare(run["f00"], s.default(config) + s.jflag(config), t, imap, worst=3)
            assert c.ok, "{}-{} locality: f00 differs from the stored default + Jacobian-flag difference\n{}".format(
                family, vid, c.report())
        ref_v = s.variant(config, vid)[0] if s.kind == "full" and e["class"] == "SENSITIVE" else None
        tv = mr.locality_tolerance(fdir, s.kind, e, r.data["yldot"], s.default(config), ref_v, imap=imap)
        ref = s.locality_pattern(config, vid)
        cmp = L.compare_pattern(ref, L.Entries.of(run["entries"]), tv, L.rtol_rows(tol["rtol"], imap),
                                float(cfg["m_loc"]), imap, "{}-{}".format(family, vid))
        if not cmp.ok:
            pytest.fail(cmp.report(), pytrace=False)


# ---------------------------------------------------------------- compare_pattern on synthetic entries


class Imap:
    """The four fields compare_pattern reads, for rows 0..n-1 (all ti[1], cell (row, 1))."""

    def __init__(self, n):
        self.neq = n
        self.eq = np.array(["ti"] * n)
        self.species = np.ones(n, dtype=int)
        self.ix, self.iy = np.arange(n), np.ones(n, dtype=int)

    def label(self, i):
        return "ti[1] ix={} iy=1 (row {})".format(self.ix[i], i + 1)


N = 8
TOL = np.full(N, 1e-10)
RT = np.full(N, 1e-8)
M = 100.0


def entries(*items):
    """Entries of (column, row, score) with dfull = 0, so the score is |mismatch| / tol."""
    c, r, s = (np.array(v) for v in zip(*items)) if items else (np.zeros(0, int),) * 3
    return L.Entries.of({"column": c, "row": r, "mismatch": np.asarray(s, float) * 1e-10, "dfull": np.zeros(len(c))})


REF = entries((0, 2, 500.0), (1, 3, 50.0))  # one P entry (> M) and one band entry


@pytest.mark.parametrize("new, ok, part", [
    (entries((0, 2, 500.0), (1, 3, 50.0)), True, None),
    (entries((0, 2, 500.4), (1, 3, 50.0)), True, None),  # within tolerance: |d_new - d_ref| <= tol_r
    (entries((0, 2, 500.0)), True, None),  # a band entry may vanish
    (entries((0, 2, 500.0), (1, 3, 99.0), (4, 5, 99.0)), True, None),  # band entries move freely up to M
    (entries((0, 2, 500.0), (4, 5, 101.0)), False, "new_rows"),  # outside P above M
    (entries((0, 2, 500.0), (1, 3, 150.0)), False, "new_rows"),  # a band entry rising above M is new
    (entries((1, 3, 50.0)), False, "lost"),  # a P entry vanished
    (entries((0, 2, 0.5)), False, "lost"),  # a P entry at score <= 1
    (entries((0, 2, 520.0)), False, "magnitude"),  # a P entry still > M but its d moved
    (entries((0, 2, 50.0)), False, "magnitude"),  # a P entry falling into the band is still asserted
])
def test_compare_pattern_band(new, ok, part):
    c = L.compare_pattern(REF, new, TOL, RT, M, Imap(N), "fam")
    assert c.ok == ok, c.report()
    if part:
        assert getattr(c, part) and c.n_fail == len(c.new_rows) + len(c.lost) + len(c.magnitude)
        assert c.fired == {"ti[1]": [(r, 1) for _, r, _ in c.new_rows + c.lost + c.magnitude]}


def raw(*items):
    """Entries of (column, row, mismatch, dfull), unscaled."""
    c, r, m, f = (np.array(v) for v in zip(*items))
    return L.Entries.of({"column": c, "row": r, "mismatch": m.astype(float), "dfull": f.astype(float)})


@pytest.mark.parametrize("new", [
    raw((0, 2, 5e-8, 0.0), (4, 5, np.nan, 0.0)),  # NaN outside P
    raw((0, 2, 5e-8, 0.0), (4, 5, np.inf, 0.0)),  # Inf outside P
    raw((0, 2, np.nan, 0.0), (1, 3, 5e-9, 0.0)),  # a P entry whose live mismatch is NaN
    raw((0, 2, 5e-8, np.nan), (1, 3, 5e-9, 0.0)),  # a P entry whose dfull is NaN
    raw((0, 2, 5e-8, 0.0), (4, 5, 1e-12, -np.inf)),  # an otherwise quiet entry with Inf dfull
])
def test_compare_pattern_fails_on_nonfinite(new):
    c = L.compare_pattern(REF, new, TOL, RT, M, Imap(N), "fam")
    assert not c.ok and len(c.nonfinite) == 1 and c.n_fail == 1 and c.max_ratio == np.inf, c.report()
    col, row, _ = c.nonfinite[0]
    assert c.fired == {"ti[1]": [(row, 1)]}
    assert c.headline() == "fam locality: column ti[1]({},1): non-finite mismatch or dfull in rows ti[1]({},1)".format(
        col, row)
    assert "non-finite live entries" in c.report()


def test_entries_refuse_duplicate_keys():
    with pytest.raises(ValueError, match="repeat"):
        L.Entries.of({"column": [0, 0], "row": [2, 2], "mismatch": [1.0, 2.0], "dfull": [0.0, 0.0]})


def test_compare_pattern_headline_names_column_and_rows():
    c = L.compare_pattern(REF, entries((0, 2, 500.0), (6, 7, 300.0), (6, 5, 200.0)), TOL, RT, M, Imap(N), "fam")
    assert c.headline() == "fam locality: column ti[1](6,1): new mismatch rows ti[1](7,1), ti[1](5,1) not in " \
                           "reference pattern"
    assert c.max_ratio == pytest.approx(3.0)


def test_compare_pattern_scores_use_rtol_eq():
    """|Delta_full| raises the denominator: the same mismatch scores lower where the full response is large."""
    e = L.Entries.of({"column": [0, 0], "row": [1, 2], "mismatch": [2e-8, 2e-8], "dfull": [0.0, 1.0]})
    s = L.scores(e, TOL, RT)
    assert s[0] == pytest.approx(200.0) and s[1] == pytest.approx(2e-8 / (1e-10 + 1e-8))


def test_compare_pattern_refuses_bad_m_loc():
    with pytest.raises(ValueError, match="M_loc"):
        L.compare_pattern(REF, REF, TOL, RT, 1.0, Imap(N))


@pytest.mark.parametrize("edit, error", [
    ({"delta_loc": 0}, "delta_loc"), ({"m_loc": 1}, "m_loc"), ({"m_loc": True}, "m_loc"),
    ({"extra": 1}, "exactly the keys"), ({"causes": "none"}, "causes"),
    ({"columns": "some"}, "columns"), ({"variants": "few"}, "variants"),
    ({"sample": 3}, "exactly the keys"),  # sample and seed only with columns = "special"
    ({"columns": "special"}, "exactly the keys"),
    ({"columns": "special", "sample": -1, "seed": 0}, "sample"),
    ({"columns": "special", "sample": 3, "seed": True}, "seed"),
])
def test_load_config_refuses(tmp_path, edit, error):
    t = {"delta_loc": 1e-5, "m_loc": 100.0, "calibration": "x", "causes": {}, "columns": "all", "variants": "all"}
    t.update(edit)
    lines = ["[locality]"] + ["{} = {}".format(k, "{}" if v == {} else repr(v) if isinstance(v, str)
                                               else str(v).lower() if isinstance(v, bool) else v)
                              for k, v in t.items()]
    (tmp_path / "family.toml").write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match=error):
        L.load_config(tmp_path)


# ---------------------------------------------------------------- columns, variants and pattern differences (AIUE-101)


def index_data(family):
    with open_store(family) as s:
        return s.index_data()


@pytest.mark.parametrize("family, n", [("d_only", 378), ("large_dd2c", 7936)])
def test_special_columns_count(family, n):
    """The owner's rule (AIUE-101 Q1) on the stored grids; the counts are the planning probe's (live com arrays)."""
    cols = L.special_columns(index_data(family))
    assert cols.size == n and (np.diff(cols) > 0).all()


def test_special_columns_double_null():
    """dnull_imp2 (nxpt = 2): the inner plates ixrb(1), ixrb(1)+1, ixlb(2), ixlb(2)+1 = 36..39 and both separatrix
    rows (iysptrx 16 and 30) are special; each cut stops at its own separatrix."""
    data = index_data("dnull_imp2")
    cols = L.special_columns(data)
    ix, iy = (data["igyl"][cols, k] for k in (0, 1))
    assert set(range(36, 40)) <= set(ix.tolist())
    assert {16, 17, 30, 31} <= set(iy.tolist())
    special = set(zip(ix.tolist(), iy.tolist()))
    assert (50, 16) in special and (50, 20) not in special  # ixpt1(2) = 50 pairs with iysptrx1(2) = 16
    assert (10, 25) in special  # ixpt1(1) = 10 pairs with iysptrx1(1) = 30


def test_select_columns_sample():
    data = index_data("d_c")
    special = L.special_columns(data)
    cfg = {"columns": "special", "sample": 50, "seed": 7}
    cols = L.select_columns(cfg, data)
    assert cols.size == special.size + 50 and set(special.tolist()) <= set(cols.tolist())
    assert np.array_equal(cols, L.select_columns(cfg, data))  # deterministic
    assert not np.array_equal(cols, L.select_columns(dict(cfg, seed=8), data))
    assert np.array_equal(L.select_columns(cfg, data, sample=False), special)
    assert L.select_columns({"columns": "all"}, data) is None


def test_variant_scope():
    v = {"bbb.methe=22": {"class": "SENSITIVE"}, "bbb.methe=33": {"class": "EXCLUDED"},
         "bbb.methp=44": {"class": "INERT"}, "bbb.xrinc": {"class": "INERT"}, "bbb.isnewpot": {"class": "SENSITIVE"},
         "bbb.yinc": {"class": "INVALID"}, "bbb.ncore": {"class": "MARGINAL"}, "api.methimp": {"class": "INERT"}}
    assert L.variant_scope({"variants": "all"}, v) == ["api.methimp", "bbb.isnewpot", "bbb.methe=22", "bbb.methp=44",
                                                       "bbb.ncore", "bbb.xrinc"]
    assert L.variant_scope({"variants": "listed"}, v) == ["bbb.methe=22", "bbb.methp=44", "bbb.xrinc"]
    assert L.variant_scope({"variants": "meth"}, v) == ["bbb.methe=22", "bbb.methp=44"]
    assert L.variant_scope({"variants": "listed", "excluded": {"bbb.xrinc": "why"}}, v) == ["bbb.methe=22",
                                                                                              "bbb.methp=44"]


def test_excluded_needs_reasons(tmp_path):
    (tmp_path / "family.toml").write_text('[locality]\ndelta_loc = 1e-6\nm_loc = 100.0\ncalibration = "x"\n'
                                          'columns = "all"\nvariants = "all"\n[locality.causes]\n'
                                          '[locality.excluded]\n"bbb.a" = ""\n')
    with pytest.raises(ValueError, match="excluded"):
        L.load_config(tmp_path)
    assert L.load_config(FAMILIES / "d_only")["excluded"].keys() == {"bbb.isupgon"}


def test_diff_apply_round_trip():
    a = raw((0, 2, 5e-8, 0.0), (1, 3, 5e-9, 1.0), (4, 5, 1e-9, 0.0))
    b = raw((0, 2, 5e-8, 0.0), (1, 3, 6e-9, 1.0), (2, 1, 1e-9, 0.0))  # same, changed, new; (4, 5) dropped
    added, dropped = L.diff(a, b)
    assert sorted(zip(added.column.tolist(), added.row.tolist())) == [(1, 3), (2, 1)]
    assert dropped["column"].tolist() == [4] and dropped["row"].tolist() == [5]
    back = L.apply(a, added, dropped)
    assert all(getattr(back, k).tobytes() == getattr(b.sorted(), k).tobytes() for k in L.FIELDS)
    added, dropped = L.diff(a, a)  # an unchanged variant stores nothing
    assert len(added) == 0 and dropped["column"].size == 0
    assert all(getattr(L.apply(a, added, dropped), k).tobytes() == getattr(a, k).tobytes() for k in L.FIELDS)


def test_diff_detects_dfull_only_change():
    added, _ = L.diff(raw((0, 2, 5e-8, 0.0)), raw((0, 2, 5e-8, 1e-300)))
    assert len(added) == 1
