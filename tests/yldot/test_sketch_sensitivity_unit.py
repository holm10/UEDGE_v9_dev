"""Unit tests of tools/sketch_sensitivity.py (AIUE-92, PRD section 7.11 (d)): the single-entry threshold of a sketch
block, its ratio to tol_i, the single-cell multiple (owner, 2026-10-22, D5), the bisection that confirms the analytic
threshold and the round-off re-check of c, on the synthetic index data of test_compare_unit.py; no uedge import.
"""
import math

import numpy as np
import pytest

from yldot.harness import store
from yldot.harness.compare import index_map
from yldot.test_compare_unit import SPEC, make_data

import sketch_sensitivity as ss  # tests/yldot/tools, on sys.path through conftest.py


@pytest.fixture(scope="module")
def setup():
    data = make_data()
    imap = index_map(data, SPEC)
    labels, rows, _ = store.blocks(imap)
    rng = np.random.default_rng(92)
    ref = rng.uniform(1.0, 2.0, imap.neq) * rng.choice([-1.0, 1.0], imap.neq)
    return data, imap, labels, rows, ref


def test_uniform_tolerance_gives_c_sqrt_n(setup):
    _, imap, labels, rows, _ = setup
    delta, _ = ss.sketch_thresholds(np.full(imap.neq, 1e-6), labels, rows, imap)
    for b, r in enumerate(rows):
        assert delta[b] / 1e-6 == pytest.approx(store.C * math.sqrt(len(r)), rel=1e-12)


def test_one_small_entry_has_a_large_ratio(setup):
    _, imap, labels, rows, _ = setup
    b = max(range(len(rows)), key=lambda n: len(rows[n]))
    i = int(rows[b][1])
    tol = np.full(imap.neq, 1.0)
    tol[i] = 1e-9
    delta, _ = ss.sketch_thresholds(tol, labels, rows, imap)
    ratio = delta[b] / tol[rows[b]]
    assert int(rows[b][int(np.argmax(ratio))]) == i
    assert ratio.max() == pytest.approx(store.C * math.sqrt(len(rows[b]) - 1 + 1e-18) / 1e-9, rel=1e-9)
    other = [n for n in range(len(rows)) if n != b]
    assert all(delta[n] == pytest.approx(store.C * math.sqrt(len(rows[n]))) for n in other)


def test_bisection_equals_the_analytic_threshold(setup):
    _, imap, labels, rows, ref = setup
    tol = 1e-8 * np.abs(ref) + 1e-12
    delta, _ = ss.sketch_thresholds(tol, labels, rows, imap)
    for label, chosen in ss.picks(labels, rows, ref).items():
        b = labels.index(label)
        for i in chosen:
            measured = ss.bisect_threshold(ref, i, b, tol, labels, rows, imap, delta[b])
            assert measured == pytest.approx(delta[b], rel=2 * ss.BISECT_RTOL)


def cell_rows(imap, ix, iy):
    return np.flatnonzero((imap.ix == ix) & (imap.iy == iy))


def test_cell_multiple_across_blocks(setup):
    """A cell's entries sit in different blocks (one per equation and species): m is the smallest delta_b / tol_e,
    and moving every entry by just over m of its tol fails exactly that block, just under passes."""
    _, imap, labels, rows, ref = setup
    tol = 1e-8 * np.abs(ref) + 1e-12
    e = cell_rows(imap, 0, 1)  # a guard cell: its blocks hold 14 cells each
    tol[e[1]] *= 50.0  # its block now fires at about c tol_e, the others at about c sqrt(14) tol_e
    delta, cell = ss.sketch_thresholds(tol, labels, rows, imap)
    block_of = store.blocks(imap)[2]
    assert len({int(block_of[i]) for i in e}) == len(e) > 1
    want = min((delta[block_of[i]] / tol[i], int(block_of[i])) for i in e)
    m, b = cell[(0, 1)]
    assert (m, b) == pytest.approx(want)
    assert int(block_of[e[1]]) == b
    refsk = store.sketch(ref, labels, rows)
    for factor, ok in ((1.01, False), (0.99, True)):
        x = ref.copy()
        x[e] += factor * m * tol[e]
        chk = store.sketch_compare(refsk, store.sketch(x, labels, rows), tol, labels, rows, imap)
        assert chk.ok == ok
        if not ok:
            assert len(chk.lines) == 2 and chk.lines[1].strip().startswith(labels[b] + " ")


def test_cell_multiple_with_two_entries_in_one_block(setup):
    """The general case (two entries of a cell in one block): m = delta_b / max_j |sum_e r_j,e tol_e|."""
    _, imap, labels, rows, _ = setup
    tol = np.ones(imap.neq)
    one = type(imap)(imap.neq, imap.eq, imap.species, imap.ix.copy(), imap.iy.copy(), imap.region)
    b = max(range(len(rows)), key=lambda n: len(rows[n]))
    r = rows[b]
    one.ix[r[1]], one.iy[r[1]] = one.ix[r[0]], one.iy[r[0]]
    delta, cell = ss.sketch_thresholds(tol, labels, rows, one)
    s = store.signs(store.SEED, labels[b], len(r), store.K)
    moved = np.abs(s[:, 0] + s[:, 1]).max()
    m, _ = cell[(int(one.ix[r[0]]), int(one.iy[r[0]]))]
    assert m <= delta[b] / moved + 1e-12


def test_roundoff_ratio(setup):
    """d along one projection j of size x * delta_b: ratio x; analyze sends a ratio >= 1 to the owner."""
    data, imap, labels, rows, ref = setup
    sigma = 1e-14 * np.abs(ref)
    toml = {"rtol": {e: 1e-8 for e in set(imap.eq)}, "rule": {"k": 100.0}}
    from yldot.harness import compare

    t = compare.tolerances(ref, sigma, toml["rtol"], toml["rule"]["k"], imap).tol
    delta, _ = ss.sketch_thresholds(t, labels, rows, imap)
    b = max(range(len(rows)), key=lambda n: len(rows[n]))
    r, j = rows[b], 3
    sgn = store.signs(store.SEED, labels[b], len(r), store.K)[j]
    a = dict(data, yldot=ref, yldot_J=ref, status="ok")
    for x, owner in ((0.5, False), (2.0, True)):
        y = ref.copy()
        y[r] += x * delta[b] / len(r) * sgn
        ratios = ss.roundoff_ratios(dict(a, yldot=y, yldot_J=y), a, delta, labels, rows)
        assert ratios["yldot"][b] == pytest.approx(x, rel=1e-6)  # y - ref rounds at 1e-16 |ref|
        assert ratios["flag difference"].max() == 0.0
        coll = {(label, run): a for label in ss.SERIAL_LABELS for run in ("1", "2")}
        coll[("linux-serial", "1")] = dict(a, yldot=y, yldot_J=y)
        out = ss.analyze("fam", "steady", ref, sigma, imap, toml, coll)
        assert not out["errors"]
        assert bool(out["owner"]) == owner
        assert out["roundoff"]["mac_vs_linux"]["yldot"]["block"] == labels[b]
