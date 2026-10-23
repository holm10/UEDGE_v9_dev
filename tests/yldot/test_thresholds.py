"""The synthetic threshold test of the yldot suite (AIUE-89; PRD section 7.11 (b), decision 26): on each family's stored
defaults, the comparators fail at 10 times their threshold and pass at 0.1 times it, per block, and fail on NaN and
+-Inf, naming the entry or block. It catches a comparator bug that would pass everything: the wrong axis or block, an
off-by-one block, NaN compared as equal, a vector compared with itself, a tolerance mis-scaled by orders.

Three comparators: the full-vector compare (yldot), the Jacobian-flag difference through Store.check (decision 27)
and the sketch comparator, its sketches built from the stored default. Pure Python: no evaluation, and only the
yldot harness's comparator and store modules, which never import uedge at module level;
it reads the reference files (fetch them with tools/fetch_data.py; an absent one fails, AIUE-156). For a sketch store
also the single-entry check (PRD 7.11 b and d; AIUE-92): its stored sketch thresholds are those of its default, sigma,
tolerances.toml and stored weights, one entry moved by 10 times its threshold fails that block alone, by 0.1 times
passes, and every entry of every block is seen within R_max = 2*c*sqrt(N_block) of its own tolerances (AIUE-174).
The locality comparator is AIUE-100's.

Rows per block (the guard rows are their own region blocks): the first and last, the largest and smallest |ref_i|,
and two from a seeded generator (the seed only selects rows).
"""
import math
import re
import tomllib
from pathlib import Path

import numpy as np
import pytest

from yldot.harness import CONFIGS, FAMILIES, compare, open_store, store
from yldot.harness import manifest as mf

SUITE = Path(__file__).resolve().parent
FAMILY_NAMES = sorted(p.name for p in FAMILIES.iterdir() if (p / "input.py").is_file())
REFERENCED = [f for f in FAMILY_NAMES if mf.path(f).is_file() and mf.reference_path(f) in mf.load(f)["external"]]
SEED_PICKS = 89
FAIL, PASS = 10.0, 0.1
BAD = (np.nan, np.inf, -np.inf)
WORST = re.compile(r"worst \|dP\|/bound (\S+);")


@pytest.fixture(scope="module")
def tol():
    with open(SUITE / "tolerances.toml", "rb") as f:
        return tomllib.load(f)


@pytest.fixture(params=[(f, c) for f in REFERENCED for c in CONFIGS], ids=lambda p: "{}-{}".format(*p))
def case(request, tol):
    """(store, config, ref, per-entry tol, sketch weights: a sketch store's stored ones, else None)."""
    family, config = request.param
    with open_store(family) as s:
        ref = np.array(s.default(config))
        t = compare.tolerances(ref, s.sigma(config), tol["rtol"], tol["rule"]["k"], s.imap).tol
        yield s, config, ref, t, (np.array(s.weights(config)) if s.kind == "sketch" else None)


def picks(s, ref):
    """{block label: sorted 0-based rows} per block."""
    out = {}
    for b, (label, rows) in enumerate(zip(s.labels, s.rows)):
        a = np.abs(ref[rows])
        chosen = {rows[0], rows[-1], rows[int(np.argmax(a))], rows[int(np.argmin(a))]}
        chosen.update(np.random.default_rng([SEED_PICKS, b]).choice(rows, size=min(2, len(rows)), replace=False))
        out[label] = sorted(int(i) for i in chosen)
    return out


def names_only(chk, label):
    """A failed sketch_compare that names exactly one block, label."""
    return not chk.ok and len(chk.lines) == 2 and chk.lines[1].strip().startswith(label + " ")


def worst_ratio(chk):
    """The worst |dP|/bound sketch_compare reports for its first failing block (printed to 3 digits)."""
    m = WORST.search(chk.lines[1]) if len(chk.lines) > 1 else None
    return float(m.group(1)) if m else float("nan")


def test_full_comparator(case):
    s, config, ref, t, _ = case
    imap, problems = s.imap, []
    for label, rows in picks(s, ref).items():
        for i in rows:
            at = "{} {}: {}".format(s.family, config, imap.label(i))
            key = (imap.eq[i], int(imap.species[i]))
            for sign in (1, -1):
                new = ref.copy()
                new[i] += sign * FAIL * t[i]
                c = compare.compare(new, ref, t, imap)
                if c.ok or c.n_fail != 1 or c.worst[0]["row"] != i + 1 or c.worst[0]["label"] != imap.label(i) \
                        or c.per_block[key] != 1:
                    problems.append("{} [{}]: {:+g} tol not failed at this entry alone".format(at, label, sign * FAIL))
                new[i] = ref[i] + sign * PASS * t[i]
                if not compare.compare(new, ref, t, imap).ok:
                    problems.append("{} [{}]: {:+g} tol failed".format(at, label, sign * PASS))
            for bad in BAD:
                new = ref.copy()
                new[i] = bad
                c = compare.compare(new, ref, t, imap)
                if c.ok or c.n_fail != 1 or c.worst[0]["row"] != i + 1:
                    problems.append("{} [{}]: {} not failed at this entry alone".format(at, label, bad))
    assert not problems, "\n".join(problems[:20])


def test_flag_comparator(case):
    """The Jacobian-flag difference yldot_J - yldot against the stored one, through Store.check: yldot itself is the
    stored default, so only the flag part may fail."""
    s, config, ref, t, _ = case
    imap, jf, problems = s.imap, s.jflag(config), []
    ref_j = ref + jf
    for label, rows in picks(s, ref).items():
        for i in rows:
            at = "{} {}: {}".format(s.family, config, imap.label(i))
            for sign in (1, -1):
                yj = ref_j.copy()
                yj[i] += sign * FAIL * t[i]
                chk = s.check(config, None, ref, yj, t, imap)
                if chk.ok or not chk.lines[0].startswith("yldot PASS") \
                        or not any(imap.label(i) in line for line in chk.lines):
                    problems.append("{} [{}]: flag difference {:+g} tol not failed and named".format(
                        at, label, sign * FAIL))
                yj[i] = ref_j[i] + sign * PASS * t[i]
                if not s.check(config, None, ref, yj, t, imap).ok:
                    problems.append("{} [{}]: flag difference {:+g} tol failed".format(at, label, sign * PASS))
            for bad in BAD:
                yj = ref_j.copy()
                yj[i] = bad
                chk = s.check(config, None, ref, yj, t, imap)
                if chk.ok or not any(imap.label(i) in line for line in chk.lines):
                    problems.append("{} [{}]: yldot_J = {} not failed and named".format(at, label, bad))
    assert not problems, "\n".join(problems[:20])


def test_sketch_comparator(case):
    """Per block, a perturbation along one weighted projection j of size M * c * sqrt(sum (tol_i w_i)^2) over the
    block (w the store's weights, 1 for a full store; its weighted projection on r_j is exactly that, on the others at
    most that): M = 10 fails that block alone with a worst |dP|/bound of 10, which only projection j reaches (so a
    projection left out of the comparison is seen); M = 0.1 passes; a NaN in the block fails it."""
    s, config, ref, t, w = case
    imap, labels, rows = s.imap, s.labels, s.rows
    ww = np.ones(imap.neq) if w is None else w
    refsk = store.sketch(ref, labels, rows, w=w)
    problems = []
    for b, (label, r) in enumerate(zip(labels, rows)):
        n, j = len(r), b % store.K
        bound = store.C * math.sqrt(store.fsum((t[r] * ww[r]) ** 2))
        sgn = store.signs(store.SEED, label, n, store.K)[j]
        for m, ok in ((FAIL, False), (PASS, True)):
            x = ref.copy()
            x[r] += m * bound / n * sgn / ww[r]
            chk = store.sketch_compare(refsk, store.sketch(x, labels, rows, w=w), t, labels, rows, imap, w=w)
            caught = names_only(chk, label) and worst_ratio(chk) == pytest.approx(m, rel=1e-2)
            if chk.ok != ok or (not ok and not caught):
                problems.append("{} {}: block {} at {:g} x the bound: ok {}, want {}\n{}".format(
                    s.family, config, label, m, chk.ok, ok, chk.report))
        x = ref.copy()
        x[r[0]] = np.nan
        chk = store.sketch_compare(refsk, store.sketch(x, labels, rows, w=w), t, labels, rows, imap, w=w)
        if not names_only(chk, label):
            problems.append("{} {}: a NaN in block {} not failed in that block alone".format(s.family, config, label))
    assert not problems, "\n".join(problems[:20])


SKETCHED = [(f, c) for f in REFERENCED if mf.load(f)["store"] == "sketch" for c in CONFIGS]


@pytest.mark.parametrize("family, config", SKETCHED, ids=lambda p: str(p))
def test_sketch_single_entry(family, config, tol):
    """PRD 7.11 (b) and (d), AIUE-92, AIUE-174: the stored sketch thresholds equal store.sketch_thresholds of the
    stored default's tolerances and the stored weights w; every entry i of every block is seen within
    R_max = 2*c*sqrt(N_block) of its own tolerances (R_i = delta_b / (tol_i w_i), owner 2026-10-23, AIUE-92 D3); at
    the picked rows of each block, one entry moved by FAIL * delta_b / w_i fails that block alone with a worst
    |dP|/bound of FAIL, and by PASS * delta_b / w_i passes. One entry moves only its block's projections, so the moved
    sketch is the default's with that block recomputed, compared over every block."""
    with open_store(family) as s:
        ref = np.array(s.default(config))
        t = compare.tolerances(ref, s.sigma(config), tol["rtol"], tol["rule"]["k"], s.imap).tol
        stored, w = s.sketch_thresholds(config), np.array(s.weights(config))
        imap, labels, rows = s.imap, s.labels, s.rows
        chosen = picks(s, ref)
    assert stored is not None, "{} {}: the reference stores no sketch thresholds".format(family, config)
    delta, cell = store.sketch_thresholds(t, labels, rows, imap, w=w)
    want, got = store.threshold_arrays(delta, cell), store.threshold_arrays(*stored)
    assert all(want[k].tobytes() == got[k].tobytes() for k in store.THRESHOLD_KEYS), \
        "{} {}: the stored sketch thresholds differ from those of the stored default".format(family, config)
    over = []
    for b, (label, r) in enumerate(zip(labels, rows)):
        ratio = delta[b] / (t[r] * w[r])
        if not ratio.max() <= 2.0 * store.C * math.sqrt(len(r)):
            over.append("{} {}: block {} R up to {:.3g} at {}, over 2*c*sqrt(N) = {:.3g}".format(
                family, config, label, float(ratio.max()), imap.label(int(r[int(np.argmax(ratio))])),
                2.0 * store.C * math.sqrt(len(r))))
    assert not over, "\n".join(over[:20])
    refsk = store.sketch(ref, labels, rows, w=w)
    problems = []
    for b, (label, r) in enumerate(zip(labels, rows)):
        for i in chosen[label]:
            for m, ok in ((FAIL, False), (PASS, True)):
                x = ref.copy()
                x[i] += m * delta[b] / w[i]
                new = {k: v.copy() for k, v in refsk.items()}
                one = store.sketch(x, [label], [r], w=w)
                for k in new:
                    new[k][b] = one[k][0]
                chk = store.sketch_compare(refsk, new, t, labels, rows, imap, w=w)
                caught = names_only(chk, label) and worst_ratio(chk) == pytest.approx(m, rel=1e-2)
                if chk.ok != ok or (not ok and not caught):
                    problems.append("{} {}: {} moved by {:g} x delta_b / w_i of {}: ok {}, want {}\n{}".format(
                        family, config, imap.label(i), m, label, chk.ok, ok, chk.report))
    assert not problems, "\n".join(problems[:20])
