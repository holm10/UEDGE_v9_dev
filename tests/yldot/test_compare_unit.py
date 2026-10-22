"""Unit tests of harness/compare.py (AIUE-83): index truth, regions, the per-entry tolerance rule with its floor and
fallbacks (PRD section 7.4, safeguard (a)) and the comparator. Pure Python on synthetic index arrays built the way
bbb/convert.m builds them; no uedge import, no child process.
"""
import tomllib

import numpy as np
import pytest

from yldot.harness import FAMILIES
from yldot.harness.compare import (PANDF_ORDER, REGIONS, RULE_FAMILY, RULE_OWN, RULE_REGION, UNORDERED,
                                   IndexTruthError, ToleranceEscalation, check_regions, compare, first_difference,
                                   index_map, region_cells, region_of, tolerances)

NX, NY, NISP, NUSP, NGSP = 3, 2, 2, 1, 1
SPEC = {"nx": NX, "ny": NY, "ix_inner_leg": [1, 1], "ix_core": [2, 2], "ix_outer_leg": [3, 3], "iy_closed": [1, 1],
        "iy_open": [2, 2], "source": {"ixpt1": 1, "ixpt2": 2, "iysptrx": 1},
        "cells": {"guard": 14, "core": 1, "pf": 2, "inner_leg": 1, "sol": 1, "outer_leg": 1}}


def make_data(bcl=(1, 1, 1, 1), phi_off=((0, 0), (4, 3))):
    """A result dict as state.py returns it: masks, then idx*/igyl filled in convert.m's loop order (iy outer, ix
    inner; per cell ni, up, te, ti, ng, tg, phi). isuponxy has nisp slices, as in bbb/bbb.v:237; ng and tg are off;
    phi is off at phi_off."""
    shape = (NX + 2, NY + 2)
    masks = {"isnionxy": np.ones(shape + (NISP,), int), "isuponxy": np.ones(shape + (NISP,), int),
             "isteonxy": np.ones(shape, int), "istionxy": np.ones(shape, int),
             "isngonxy": np.zeros(shape + (NGSP,), int), "istgonxy": np.zeros(shape + (NGSP,), int),
             "isphionxy": np.ones(shape, int)}
    for c in phi_off:
        masks["isphionxy"][c] = 0
    idx = {"idxn": np.zeros(shape + (NISP,), int), "idxu": np.zeros(shape + (NUSP,), int),
           "idxte": np.zeros(shape, int), "idxti": np.zeros(shape, int), "idxg": np.zeros(shape + (NGSP,), int),
           "idxtg": np.zeros(shape + (NGSP,), int), "idxphi": np.zeros(shape, int)}
    igyl = np.zeros((200, 2), int)
    iv = 0
    ixmn, ixmx, iymn, iymx = bcl
    for iy in range(1 - iymn, NY + iymx + 1):
        for ix in range(1 - ixmn, NX + ixmx + 1):
            slots = [("idxn", "isnionxy", s) for s in range(NISP)] + [("idxu", "isuponxy", s) for s in range(NUSP)]
            slots += [("idxte", "isteonxy", None), ("idxti", "istionxy", None)]
            slots += [("idxg", "isngonxy", s) for s in range(NGSP)] + [("idxtg", "istgonxy", s) for s in range(NGSP)]
            slots += [("idxphi", "isphionxy", None)]
            for name, mask, s in slots:
                cell = (ix, iy) if s is None else (ix, iy, s)
                if masks[mask][cell] == 1:
                    iv += 1
                    idx[name][cell] = iv
                    igyl[iv - 1] = (ix, iy)
    grid = {"nx": np.array(NX), "ny": np.array(NY), "ixmnbcl": np.array(ixmn), "ixmxbcl": np.array(ixmx),
            "iymnbcl": np.array(iymn), "iymxbcl": np.array(iymx), "mhdgeo": np.array(1), "nxpt": np.array(1),
            "iysptrx": np.array(1), "ixpt1": np.array([1]), "ixpt2": np.array([2]), "ixlb": np.array([0]),
            "ixrb": np.array([NX]), "nxcore": np.zeros((30, 2), int), "nxleg": np.zeros((30, 2), int),
            "nycore": np.zeros(30, int), "nysol": np.zeros(30, int), "geometry": "snull"}
    return dict(idx, neq=iv, igyl=igyl, masks=masks, grid=grid)


def family_regions(name):
    with open(FAMILIES / name / "family.toml", "rb") as f:
        return tomllib.load(f)["regions"]


# ---------------------------------------------------------------- index truth


def test_bijection_accepted():
    d = make_data()
    imap = index_map(d, SPEC)
    assert imap.neq == d["neq"] == 5 * 4 * (NISP + NUSP + 3) - 2  # ni x2, up, te, ti, phi; phi off at 2 cells
    for name, eq, sp in (("idxn", "ni", 2), ("idxu", "up", 1), ("idxte", "te", 1), ("idxphi", "phi", 1)):
        a = d[name] if d[name].ndim == 3 else d[name][..., None]
        for (ix, iy) in [(0, 0), (2, 1), (4, 3)]:
            row = a[ix, iy, sp - 1]
            if row:
                i = row - 1
                assert (imap.eq[i], imap.species[i], imap.ix[i], imap.iy[i]) == (eq, sp, ix, iy)
                assert imap.region[i] == region_of(ix, iy, SPEC)
    assert set(imap.blocks()) == {("ni", 1), ("ni", 2), ("up", 1), ("te", 1), ("ti", 1), ("phi", 1)}
    assert sum(r.size for r in imap.groups().values()) == imap.neq
    assert imap.label(int(d["idxte"][2, 1]) - 1) == "te[1] ix=2 iy=1 core (row {})".format(d["idxte"][2, 1])


def reject(d, *words):
    with pytest.raises(IndexTruthError) as e:
        index_map(d)
    msg = str(e.value)
    assert "ask the epic owner" in msg
    for w in words:
        assert w in msg, msg
    return msg


@pytest.mark.parametrize("a,b", [(("idxn", (1, 1, 0)), ("idxn", (2, 1, 0))),
                                 (("idxte", (1, 1)), ("idxn", (3, 2, 1))),
                                 (("idxphi", (0, 1)), ("idxu", (4, 3, 0))),
                                 (("idxte", (1, 1)), ("idxte", (1, 2)))])  # same ix: only igyl's iy can catch it
def test_permuted_map_rejected(a, b):
    """The deliberately permuted map: two rows exchanged between cells keep a bijection, igyl catches them."""
    d = make_data()
    (na, ca), (nb, cb) = a, b
    d[na][ca], d[nb][cb] = d[nb][cb], d[na][ca]
    reject(d, "igyl disagrees")


def test_duplicate_and_missing_rejected():
    d = make_data()
    d["idxti"][1, 1] = d["idxte"][1, 1]
    reject(d, "claimed more than once", "claimed by no active cell")


@pytest.mark.parametrize("value,word", [(0, "outside 1.."), (-3, "outside 1.."), (10 ** 6, "outside 1..")])
def test_row_out_of_range_rejected(value, word):
    d = make_data()
    d["idxn"][2, 2, 1] = value
    reject(d, word, "claimed by no active cell")


def test_stale_index_at_inactive_cell_rejected():
    d = make_data()
    d["idxg"][2, 2, 0] = 7  # ng is off everywhere
    reject(d, "idxg[1] holds a row number at 1 inactive cells")
    d = make_data()
    d["idxphi"][0, 0] = 9  # phi is off at (0, 0)
    reject(d, "idxphi[1] holds a row number")


@pytest.mark.parametrize("delta", [-1, 1])
def test_wrong_neq_rejected(delta):
    d = make_data()
    d["neq"] += delta
    reject(d, "outside 1.." if delta < 0 else "claimed by no active cell")


def test_igyl_too_short_rejected():
    d = make_data()
    d["igyl"] = d["igyl"][:10]
    reject(d, "igyl has shape")


def test_mask_slices_past_the_idx_bound_ignored():
    """isuponxy has nisp slices, idxu nusp: convert.m reads only 1..nusp (d_c: nisp 8, nusp 2)."""
    d = make_data()
    d["masks"]["isuponxy"][..., 1] = 0  # never read
    assert index_map(d).neq == d["neq"]
    d["masks"]["isuponxy"] = d["masks"]["isuponxy"][..., :0]  # fewer slices than idxu: does not fit
    reject(d, "do not fit")


def test_loop_range_from_bcl():
    """ixmnbcl = 0: convert.m starts at ix = 1, so ix = 0 is inactive whatever the mask says."""
    d = make_data(bcl=(0, 1, 1, 1))
    imap = index_map(d)
    assert imap.ix.min() == 1
    d["idxte"][0, 1] = 1
    reject(d, "idxte[1] holds a row number")


# ---------------------------------------------------------------- regions


@pytest.mark.toml_only
@pytest.mark.parametrize("family", ["d_only", "d_mols", "ortho", "d_c", "slab_phi", "large_dd2c", "dnull_imp2",
                                    "imp7"])
def test_family_regions_counts(family):
    spec = family_regions(family)
    check_regions(spec)
    assert region_cells(spec) == {r: int(spec["cells"].get(r, 0)) for r in REGIONS}


def test_region_of_synthetic():
    assert [region_of(ix, 1, SPEC) for ix in range(5)] == ["guard", "pf", "core", "pf", "guard"]
    assert [region_of(ix, 2, SPEC) for ix in range(5)] == ["guard", "inner_leg", "sol", "outer_leg", "guard"]
    assert region_of(2, 0, SPEC) == region_of(2, 3, SPEC) == "guard"
    assert region_cells(SPEC) == {r: SPEC["cells"].get(r, 0) for r in REGIONS}


# An upper-primary double null, nx = 14, ny = 6: half 1 is ix 0..7 (guard 7 = ixrb(1)+1), half 2 ix 8..15 (guard
# 8 = ixlb(2)); upper separatrix iy = 2, lower iy = 4 (owner, 2026-10-21)
DNULL = {"nx": 14, "ny": 6, "ix_lower_inner_leg": [1, 2], "ix_inner_core": [3, 4], "ix_upper_inner_leg": [5, 6],
         "ix_upper_outer_leg": [9, 10], "ix_outer_core": [11, 12], "ix_lower_outer_leg": [13, 14],
         "iy_closed": [1, 2], "iy_between": [3, 4], "iy_open": [5, 6],
         "source": {"ixlb": [0, 8], "ixrb": [6, 14], "ixpt1": [2, 10], "ixpt2": [4, 12], "iysptrx1": [4, 2],
                    "iysptrx2": [2, 4]},
         "cells": {"guard": 56, "core": 8, "pf_upper": 8, "pf_lower": 16, "sol_between": 16, "sol": 8,
                   "lower_inner_leg": 4, "upper_inner_leg": 4, "upper_outer_leg": 4, "lower_outer_leg": 4}}


def dnull_grid(spec=DNULL):
    g = {"nx": np.array(spec["nx"]), "ny": np.array(spec["ny"]), "mhdgeo": np.array(1), "nxpt": np.array(2)}
    g.update({k: np.array(v) for k, v in spec["source"].items()})
    return g


def test_dnull_region_of_synthetic():
    g, pl, pu, c, sb = "guard", "pf_lower", "pf_upper", "core", "sol_between"
    closed = [g, pl, pl, c, c, pu, pu, g, g, pu, pu, c, c, pl, pl, g]
    between = [g, pl, pl, sb, sb, sb, sb, g, g, sb, sb, sb, sb, pl, pl, g]
    li, ui, uo, lo = "lower_inner_leg", "upper_inner_leg", "upper_outer_leg", "lower_outer_leg"
    open_ = [g, li, li, "sol", "sol", ui, ui, g, g, uo, uo, "sol", "sol", lo, lo, g]
    for iy, want in ((1, closed), (2, closed), (3, between), (4, between), (5, open_), (6, open_)):
        assert [region_of(ix, iy, DNULL) for ix in range(16)] == want, iy
    assert {region_of(ix, iy, DNULL) for ix in range(16) for iy in (0, 7)} == {"guard"}
    assert region_cells(DNULL) == {r: DNULL["cells"].get(r, 0) for r in REGIONS}
    check_regions(DNULL)
    check_regions(DNULL, dnull_grid())


def test_dnull_connected_has_no_band():
    src = dict(DNULL["source"], iysptrx1=[3, 3], iysptrx2=[3, 3])
    spec = dict(DNULL, source=src, iy_closed=[1, 3], iy_between=[], iy_open=[4, 6],
                cells={"guard": 56, "core": 12, "pf_upper": 12, "pf_lower": 12, "sol": 12, "lower_inner_leg": 6,
                       "upper_inner_leg": 6, "upper_outer_leg": 6, "lower_outer_leg": 6})
    check_regions(spec, dnull_grid(spec))
    assert region_cells(spec)["sol_between"] == 0


@pytest.mark.parametrize("key,value,word", [
    ("ix_outer_core", [11, 13], "the owner's rule gives"),
    ("iy_between", [3, 5], "the owner's rule gives"),
    ("cells", dict(DNULL["cells"], guard=55), "differ from the recorded cells"),
    ("source", dict(DNULL["source"], iysptrx1=[2, 4], iysptrx2=[4, 2]), "upper X-point primary"),
    ("source", dict(DNULL["source"], iysptrx1=[4, 3]), "upper X-point primary"),
    ("source", dict(DNULL["source"], ixlb=[1, 8]), "upper X-point primary")])
def test_bad_dnull_regions_rejected(key, value, word):
    with pytest.raises(IndexTruthError, match=word):
        check_regions(dict(DNULL, **{key: value}))


def test_dnull_regions_against_live_grid():
    with pytest.raises(IndexTruthError, match="differ from the live grid"):
        check_regions(DNULL, dict(dnull_grid(), ixlb=np.array([0, 9])))
    with pytest.raises(IndexTruthError, match="mhdgeo = 1, nxpt = 1 but"):
        check_regions(DNULL, dict(dnull_grid(), nxpt=np.array(1), iysptrx=np.array(2)))
    with pytest.raises(IndexTruthError, match="mhdgeo = 1, nxpt = 2 but"):
        check_regions(SPEC, dict(make_data()["grid"], nxpt=np.array(2), iysptrx1=np.array([1, 1]),
                                 iysptrx2=np.array([1, 1])))


@pytest.mark.parametrize("key,value,word", [("ix_core", [2, 3], "the owner's rule gives"),
                                            ("ix_outer_leg", [3, 4], "the owner's rule gives"),
                                            ("iy_open", [3, 3], "the owner's rule gives"),
                                            ("cells", {"guard": 13}, "differ from the recorded cells"),
                                            ("source", {"ixpt1": 1, "ixpt2": 3, "iysptrx": 1}, "the owner's rule gives")])
def test_bad_regions_rejected(key, value, word):
    spec = dict(SPEC, **{key: value})
    with pytest.raises(IndexTruthError, match=word):
        check_regions(spec)


def test_regions_against_live_grid():
    d = make_data()
    check_regions(SPEC, d["grid"])
    g = dict(d["grid"], ixpt2=np.array([3]))
    with pytest.raises(IndexTruthError, match="differ from the live grid"):
        check_regions(SPEC, g)
    with pytest.raises(IndexTruthError, match="mhdgeo = -1"):
        check_regions(SPEC, dict(d["grid"], mhdgeo=np.array(-1)))


def test_slab_regions_need_the_half_mesh():
    spec = family_regions("slab_phi")
    nxcore, nxleg, nycore = np.zeros((30, 2), int), np.zeros((30, 2), int), np.zeros(30, int)
    nxcore[0, 1], nxleg[0, 1], nycore[0] = 8, 24, 1
    grid = {"nx": 32, "ny": 17, "mhdgeo": np.array(-1), "nxcore": nxcore, "nxleg": nxleg, "nycore": nycore}
    check_regions(spec, grid)
    nxleg = nxleg.copy()
    nxleg[0, 0] = 2
    with pytest.raises(IndexTruthError, match="half-mesh rule"):
        check_regions(spec, dict(grid, nxleg=nxleg))


# ---------------------------------------------------------------- tolerances


@pytest.fixture
def imap():
    return index_map(make_data(), SPEC)


RTOL = {"ni": 1e-10, "up": 1e-9, "te": 1e-10, "ti": 1e-10, "phi": 1e-8}
K = 100.0


def rows_of(imap, eq, sp, region):
    return imap.groups()[(eq, sp, region)]


def test_tolerance_both_branches(imap):
    ref = np.full(imap.neq, 1.0)
    sigma = np.full(imap.neq, 1e-15)
    sigma[0] = 1e-6  # k*sigma wins
    t = tolerances(ref, sigma, RTOL, K, imap)
    assert t.tol[0] == K * 1e-6
    i = 5
    assert t.tol[i] == RTOL[imap.eq[i]] * 1.0  # rtol*|ref| wins
    assert (t.rule == RULE_OWN).all()


def test_floor_is_the_smallest_nonzero_sigma_of_the_region(imap):
    ref = np.zeros(imap.neq)
    sigma = np.full(imap.neq, 1e-12)
    guard = rows_of(imap, "te", 1, "guard")
    pf = rows_of(imap, "te", 1, "pf")
    sigma[guard] = np.linspace(3e-13, 9e-13, guard.size)
    sigma[guard[:3]] = 0.0
    sigma[pf] = 1e-16  # smaller, but another region: must not be used
    t = tolerances(ref, sigma, RTOL, K, imap)
    nonzero = sigma[guard][sigma[guard] > 0]
    assert np.all(t.tol[guard[:3]] == K * nonzero.min())
    assert np.all(t.rule[guard[:3]] == RULE_REGION)
    assert nonzero.min() < nonzero.max()  # the smallest, not the largest


def test_floor_is_at_least_rtol_ref(imap):
    ref = np.full(imap.neq, 1e3)
    sigma = np.full(imap.neq, 1e-15)
    rows = rows_of(imap, "ni", 2, "sol")
    sigma[rows] = 0.0
    t = tolerances(ref, sigma, RTOL, K, imap)
    assert np.all(t.tol[rows] == RTOL["ni"] * 1e3)  # max(rtol*|ref|, k*sigma_min,r): 1e-7 > 1e-13


def test_region_all_zero_falls_back_to_equation_and_species(imap):
    ref = np.zeros(imap.neq)
    sigma = np.full(imap.neq, 1e-12)
    block = imap.blocks()[("ti", 1)]
    sigma[block] = np.linspace(2e-12, 8e-12, block.size)
    core = rows_of(imap, "ti", 1, "core")
    sigma[core] = 0.0
    sigma[rows_of(imap, "te", 1, "pf")] = 1e-20  # another equation: must not be used
    t = tolerances(ref, sigma, RTOL, K, imap)
    family_min = sigma[block][sigma[block] > 0].min()
    assert np.all(t.tol[core] == K * family_min)
    assert np.all(t.rule[core] == RULE_FAMILY)


def test_equation_and_species_all_zero_escalates(imap):
    sigma = np.full(imap.neq, 1e-12)
    sigma[imap.blocks()[("up", 1)]] = 0.0
    with pytest.raises(ToleranceEscalation, match=r"up\[1\].*ask the epic owner"):
        tolerances(np.ones(imap.neq), sigma, RTOL, K, imap)


@pytest.mark.parametrize("bad", ["rtol", "negative", "nan", "k", "shape", "no regions", "ref nan"])
def test_tolerance_input_errors(imap, bad):
    ref, sigma, rtol, k, m = np.ones(imap.neq), np.full(imap.neq, 1e-12), dict(RTOL), K, imap
    if bad == "rtol":
        del rtol["te"]
    elif bad == "negative":
        sigma[3] = -1e-12
    elif bad == "nan":
        sigma[3] = np.nan
    elif bad == "k":
        k = 0.0
    elif bad == "shape":
        sigma = sigma[:-1]
    elif bad == "no regions":
        m = index_map(make_data())
    elif bad == "ref nan":
        ref[2] = np.nan
    with pytest.raises(ValueError):
        tolerances(ref, sigma, rtol, k, m)


# ---------------------------------------------------------------- comparison


@pytest.fixture
def case(imap):
    rng = np.random.default_rng(83)
    ref = rng.normal(size=imap.neq) * 10.0 ** rng.integers(-8, 3, imap.neq)
    sigma = np.abs(ref) * 1e-14
    sigma[::7] = 0.0
    t = tolerances(ref, sigma, RTOL, K, imap)
    return ref, t.tol


def probe_rows(imap, ref):
    """Per block: the first and last row, the largest and smallest |ref|, and a guard row (safeguard (b))."""
    out = set()
    for rows in imap.blocks().values():
        a = np.abs(ref[rows])
        out.update(int(r) for r in (rows[0], rows[-1], rows[np.argmax(a)], rows[np.argmin(a)]))
        guard = rows[imap.region[rows] == "guard"]
        out.add(int(guard[0]))
    return sorted(out)


def test_ten_tol_fails_and_names_the_entry(imap, case):
    ref, tol = case
    for i in probe_rows(imap, ref):
        for sign in (1, -1):
            new = ref.copy()
            new[i] += sign * 10 * tol[i]
            c = compare(new, ref, tol, imap)
            assert not c.ok and c.n_fail == 1
            w = c.worst[0]
            assert w["row"] == i + 1 and w["label"] == imap.label(i)
            assert "{}[{}] ix={} iy={}".format(imap.eq[i], imap.species[i], imap.ix[i], imap.iy[i]) in c.report()
            assert c.per_block[(imap.eq[i], int(imap.species[i]))] == 1


def test_tenth_tol_passes(imap, case):
    ref, tol = case
    rows = probe_rows(imap, ref)
    for sign in (1, -1):
        new = ref.copy()
        new[rows] += sign * 0.1 * tol[rows]
        assert compare(new, ref, tol, imap).ok


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_non_finite_fails(imap, case, value):
    ref, tol = case
    new = ref.copy()
    new[4] = value
    c = compare(new, ref, tol, imap)
    assert not c.ok and c.worst[0]["row"] == 5 and c.worst[0]["ratio"] == np.inf


def test_identical_passes(imap, case):
    ref, tol = case
    c = compare(ref.copy(), ref, tol, imap)
    assert c.ok and c.n_fail == 0 and c.report().startswith("PASS")


def test_worst_ordering_and_counts(imap, case):
    ref, tol = case
    new = ref.copy()
    picks = {3: 5.0, 40: 50.0, 77: 2.0}
    for i, f in picks.items():
        new[i] += f * tol[i]
    new[90] = np.nan
    c = compare(new, ref, tol, imap, worst=3)
    assert c.n_fail == 4 and len(c.worst) == 3
    assert [w["row"] for w in c.worst] == [91, 41, 4]
    assert sum(c.per_block.values()) == 4


@pytest.mark.parametrize("bad", ["shape", "tol zero", "tol nan", "ref nan"])
def test_compare_input_errors(imap, case, bad):
    ref, tol = case
    new, tol, ref = ref.copy(), tol.copy(), ref.copy()
    if bad == "shape":
        new = new[:-1]
    elif bad == "tol zero":
        tol[0] = 0.0
    elif bad == "tol nan":
        tol[0] = np.nan
    elif bad == "ref nan":
        ref[0] = np.nan
    with pytest.raises(ValueError):
        compare(new, ref, tol, imap)


# ---------------------------------------------------------------- first differing intermediate


def diag(**changes):
    d = {n: np.arange(6.0).reshape(2, 3) for n in ("fqp", "fnix", "resco", "fmix", "qgpar")}
    d.update(changes)
    return d


def test_pandf_order_lists_are_disjoint():
    assert not set(PANDF_ORDER) & set(UNORDERED)
    assert len(set(PANDF_ORDER)) == len(PANDF_ORDER) and len(set(UNORDERED)) == len(UNORDERED)
    assert PANDF_ORDER.index("fqp") < PANDF_ORDER.index("fnix") < PANDF_ORDER.index("resco")


def test_first_difference_follows_pandf_order():
    ref = diag()
    new = diag(resco=ref["resco"] + 1, fnix=ref["fnix"] * (1 + 1e-9), fmix=ref["fmix"] + 5)
    d = first_difference(ref, new)
    assert d.name == "fnix" and d.ordered and d.kind == "values" and d.max_rel == pytest.approx(1e-9, rel=1e-3)
    assert first_difference(ref, new, rtol=1e-6).name == "resco"
    assert first_difference(ref, diag()) is None


def test_first_difference_unordered_after_ordered():
    ref = diag()
    d = first_difference(ref, diag(qgpar=ref["qgpar"] + 1, fmix=ref["fmix"] + 1))
    assert d.name == "fmix" and not d.ordered and "unordered" in str(d)


def test_first_difference_structure_and_nan():
    ref = diag()
    new = diag()
    del new["fnix"]
    assert first_difference(ref, new).kind == "missing in new"
    assert first_difference(ref, diag(fqp=np.zeros(4))).kind == "shape"
    both = diag(fqp=np.array([np.nan, 1.0]))
    assert first_difference(both, diag(fqp=np.array([np.nan, 1.0]))) is None
    d = first_difference(diag(fqp=np.array([1.0, 1.0])), diag(fqp=np.array([np.nan, 1.0])))
    assert d.name == "fqp" and d.max_rel == np.inf and d.index == (0,)


def test_report_names_the_first_difference(imap, case):
    ref, tol = case
    new = ref.copy()
    new[0] += 10 * tol[0]
    text = compare(new, ref, tol, imap).report(diag(), diag(fnix=diag()["fnix"] + 1))
    assert "first differing intermediate: fnix (pandf order)" in text
