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
import tomllib
from pathlib import Path

import numpy as np
import pytest

from yldot.harness import FAMILIES, compare, open_store
from yldot.harness import locality as L
from yldot.harness import manifest as mf
from yldot.harness.compare import listed

SUITE = Path(__file__).resolve().parent
FAMILY_NAMES = sorted(p.name for p in FAMILIES.iterdir() if (p / "input.py").is_file())
CONFIGURED = [f for f in FAMILY_NAMES if L.load_config(FAMILIES / f) is not None]
SMALL = sorted(p.parent.name for p in FAMILIES.glob("*/sigma.h5"))  # the five small families (AIUE-88)


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


@pytest.mark.parametrize("family", CONFIGURED)
def test_locality(tol, runner, family):
    cfg = L.load_config(FAMILIES / family)
    r = runner.evaluate(family, locality=cfg["delta_loc"])
    assert r.ok, (r.status, r.message, r.log_tail)
    run = r.data["locality"]
    with open_store(family) as s:
        stored = s.locality("steady")
        assert stored is not None, "{}: the reference stores no locality pattern".format(family)
        delta, ref = stored
        assert delta == cfg["delta_loc"] == run["delta"], (
            "{}: the reference's delta {} differs from family.toml delta_loc {}: regenerate".format(
                family, delta, cfg["delta_loc"]))
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
])
def test_load_config_refuses(tmp_path, edit, error):
    t = {"delta_loc": 1e-5, "m_loc": 100.0, "calibration": "x", "causes": {}}
    t.update(edit)
    lines = ["[locality]"] + ["{} = {}".format(k, "{}" if v == {} else repr(v) if isinstance(v, str)
                                               else str(v).lower() if isinstance(v, bool) else v)
                              for k, v in t.items()]
    (tmp_path / "family.toml").write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match=error):
        L.load_config(tmp_path)
