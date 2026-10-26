"""Unit tests of the reference store, the manifest and the data-release tools (AIUE-84; PRD sections 7.3, 7.4, 7.6):
round trips of both stores, the sketch comparator and its known-answer vector, the SHA-256 checks at open and at
read, fetch_data.py (verify, download, link, refuse) and release_data.py (its refusals and the dry run). Pure Python
on the synthetic index data of test_compare_unit.py; no uedge import, no child process, no network (gh and git are
replaced by fakes).
"""
import hashlib
import json
import os
import sys
from pathlib import Path

import h5py
import numpy as np
import pytest

from yldot.harness import manifest as mf
from yldot.harness import store
from yldot.harness.compare import index_map
from yldot.test_compare_unit import SPEC, make_data

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))

import fetch_data  # noqa: E402
import release_data  # noqa: E402

DATA = make_data()
IMAP = index_map(DATA, SPEC)
N = IMAP.neq
LABELS, ROWS, _ = store.blocks(IMAP)
RNG = np.random.default_rng(84)
Y = RNG.standard_normal(N)
YJ = Y.copy()
YJ[[0, 7]] += [1.0, -2.0]
SIGMA = np.full(N, 1e-13)
DIAG = {"resco": np.arange(6.0).reshape(3, 2), "fnix": np.ones(4)}
TOL = np.full(N, 1e-8)
YV = Y.copy()
YV[[5, 40]] *= 2.0
YJV = YV.copy()
YJV[9] += 3.0
TAG = "yldot-data-v3"


LOC = {"column": np.array([3, 0, 3]), "row": np.array([5, 2, 1]), "mismatch": np.array([2e-6, -1e-7, 3e-5]),
       "dfull": np.array([1e-3, 4e-4, 2e-2])}


def build(suite, kind, variants=(("bbb.cfvisx", YV, YJV),), family="fam", release=None, locality=None, tol=TOL,
          columns=None, loc_variants=()):
    """A reference file and its manifest in a scratch suite; returns the manifest. locality: (delta, entries); tol:
    the tolerance a sketch store's weights are 1 / of; columns: the locality's perturbed columns; loc_variants:
    (config, id, added, dropped) locality differences (an id not in variants is an INERT variable)."""
    ref = Path(suite) / "references"
    ref.mkdir(parents=True, exist_ok=True)
    w = store.create(ref / "{}.h5".format(family), kind, family, DATA, IMAP)
    for config in mf.CONFIG_NAMES:
        w.write_default(config, Y, YJ, SIGMA, DIAG)
        if kind == "sketch":  # weights 1/tol, required (AIUE-174)
            w.write_sketch_thresholds(config, tol)
    if locality is not None:
        w.write_locality("steady", *locality, columns=columns)
    for vid, yv, yjv in variants:
        w.write_variant("steady", vid, yv, yjv)
    for config, vid, added, dropped in loc_variants:
        w.write_locality_variant(config, vid, added, dropped)
    out = w.finish()
    guarded, unguarded = mf.summarize(out["datasets"])
    variables = {vid: {"class": "SENSITIVE", "reason": "", "applied": None, "d": None, "phase": "PRE",
                       "config": "steady", "sha256": mf.variant_sha(out["datasets"], "steady", vid),
                       "block_l2": store.block_l2(yv - Y, LABELS, ROWS),
                       "jflag_block_l2": store.block_l2((yjv - yv) - (YJ - Y), LABELS, ROWS)}
                 for vid, yv, yjv in variants}
    for config, vid, _, _ in loc_variants:
        variables.setdefault(vid, {"class": "INERT", "reason": "", "applied": None, "d": None, "phase": "PRE",
                                   "config": config, "sha256": None, "block_l2": {}, "jflag_block_l2": {}})
    m = {"schema": 1, "family": family, "store": kind, "release": release,
         "external": {mf.reference_path(family): {"sha256": out["sha256"], "bytes": out["bytes"]}},
         "datasets": out["datasets"], "guarded": guarded, "unguarded": unguarded,
         "provenance": mf.provenance("0" * 40, "gfortran 15", "-O3", "local"), "variables": variables}
    if kind == "sketch":
        m["sketch"] = {"k": store.K, "seed": store.SEED}
    if out["locality_variants"]:
        m["locality_variants"] = out["locality_variants"]
    mf.dump(m, mf.path(family, suite))
    return m


def reseal(suite, family="fam"):
    """Update the manifest's file SHA-256 and size to the file as it is now (a consistent tamper)."""
    m = mf.load(family, suite)
    p = Path(suite) / mf.reference_path(family)
    m["external"][mf.reference_path(family)] = {"sha256": store.file_sha256(p), "bytes": p.stat().st_size}
    mf.dump(m, mf.path(family, suite))
    return m


# ---------------------------------------------------------------- stores


def test_full_round_trip(tmp_path):
    build(tmp_path, "full", variants=(("bbb.cfvisx", YV, YJV), ("bbb.same", Y, YJ)))
    with store.open_store("fam", tmp_path, regions=SPEC) as s:
        assert isinstance(s, store.FullVectorStore)
        for config in mf.CONFIG_NAMES:
            assert s.default(config).tobytes() == Y.tobytes()
            assert s.sigma(config).tobytes() == SIGMA.tobytes()
            assert np.array_equal(s.jflag(config), YJ - Y)
            assert set(s.diagnostics(config)) == set(DIAG)
        assert s.variants("steady") == ["bbb.cfvisx", "bbb.same"] and s.variants("timestep") == []
        v, vj = s.variant("steady", "bbb.cfvisx")
        assert v.tobytes() == YV.tobytes() and np.array_equal(vj, YJV - YV)
        assert s.read("/steady/variants/bbb.cfvisx/yldot/index").tolist() == [5, 40]
        assert s.read("/steady/variants/bbb.same/yldot/index").size == 0  # bitwise equal: nothing stored
        assert s.variant("steady", "bbb.same")[0].tobytes() == Y.tobytes()
        again = index_map(s.index_data(), SPEC)
        assert all(np.array_equal(getattr(again, a), getattr(IMAP, a)) for a in ("eq", "species", "ix", "iy",
                                                                                   "region"))
        assert s.check("steady", None, Y, YJ, TOL, IMAP).ok
        assert s.check("steady", "bbb.cfvisx", YV, YJV, TOL, IMAP).ok
        c = s.check("steady", "bbb.cfvisx", Y, YJV, TOL, IMAP)
        assert not c.ok and "row 6" in c.report and "row 41" in c.report


def test_full_default_failure_names_entry_and_diagnostic(tmp_path):
    build(tmp_path, "full")
    with store.open_store("fam", tmp_path, regions=SPEC) as s:
        new = Y.copy()
        new[12] += 1.0
        diag = dict(DIAG, resco=DIAG["resco"] + 1.0)
        c = s.check("steady", None, new, YJ + (new - Y), TOL, IMAP, diagnostics=diag)
        assert not c.ok
        assert IMAP.label(12) in c.report and "first differing intermediate: resco" in c.report


def test_bitwise_difference():
    a = np.array([0.0, 1.0, np.nan])
    b = np.array([-0.0, 1.0, np.nan])
    assert store.differs(a, b).tolist() == [True, False, False]
    i, v = store.sparse_diff(b, a)
    assert i.dtype == np.int32 and i.tolist() == [0] and np.signbit(v[0])


def test_same_bytes_when_written_twice(tmp_path):
    for kind in mf.STORES:
        a, b = build(tmp_path / "a", kind), build(tmp_path / "b", kind)
        assert a["external"] == b["external"] and a["datasets"] == b["datasets"]


def test_file_format_is_hdf5_1_10(tmp_path):
    """Superblock version 3 is the 1.10 format (the default libver writes version 0); a reopened file's libver
    reports the open's bounds, not the format."""
    assert store.LIBVER == ("v110", "latest")  # owner, 2026-10-22 (AIUE-94 D3)
    build(tmp_path, "full")
    with h5py.File(tmp_path / "references" / "fam.h5", "r") as f:
        assert f.id.get_create_plist().get_version()[0] == 3


@pytest.mark.parametrize("kind", mf.STORES)
def test_copy_variant_is_verbatim(tmp_path, kind):
    """A file whose variants are all copied from a store has the bytes of a fresh write (make_references --only)."""
    variants = (("bbb.cfvisx", YV, YJV), ("bbb.same", Y, YJ))
    m = build(tmp_path / "src", kind, variants=variants)
    with store.open_store("fam", tmp_path / "src", regions=SPEC) as s:
        p = tmp_path / "copy.h5"
        w = store.create(p, kind, "fam", DATA, IMAP)
        for config in mf.CONFIG_NAMES:
            w.write_default(config, Y, YJ, SIGMA, DIAG)
            if kind == "sketch":
                w.write_sketch_thresholds(config, TOL)
        for vid, _, _ in variants:
            w.copy_variant("steady", vid, s)
        with pytest.raises(store.StoreError, match="already written"):
            w.copy_variant("steady", "bbb.cfvisx", s)
        with pytest.raises(store.StoreError, match="no stored variant"):
            w.copy_variant("steady", "bbb.other", s)
        out = w.finish()
    assert out["datasets"] == m["datasets"]
    assert out["sha256"] == m["external"][mf.reference_path("fam")]["sha256"]


def test_copy_variant_refuses_another_store_kind(tmp_path):
    build(tmp_path / "src", "full")
    with store.open_store("fam", tmp_path / "src", regions=SPEC) as s:
        w = store.create(tmp_path / "copy.h5", "sketch", "fam", DATA, IMAP)
        w.write_default("steady", Y, YJ, SIGMA, DIAG)
        with pytest.raises(store.StoreError, match="full store into a sketch"):
            w.copy_variant("steady", "bbb.cfvisx", s)
        w.f.close()


def test_sketch_round_trip_and_thresholds(tmp_path):
    build(tmp_path, "sketch")
    with store.open_store("fam", tmp_path, regions=SPEC) as s:
        assert isinstance(s, store.SketchStore) and (s.k, s.seed) == (store.K, store.SEED)
        assert s.default("steady").tobytes() == Y.tobytes()  # the default stays a full vector
        assert set(s.diagnostics("steady")) == {"resco"}  # res* only
        ref, ref_j = s.variant("steady", "bbb.cfvisx")
        assert s.weights("steady").tobytes() == (1.0 / TOL).tobytes()
        for stored, x in ((ref, YV), (ref_j, YJV - YV)):
            again = store.sketch(x, LABELS, ROWS, w=1.0 / TOL)
            assert all(stored[k].tobytes() == again[k].tobytes() for k in again)
        assert s.check("steady", "bbb.cfvisx", YV, YJV, TOL, IMAP).ok
        noise = 0.1 * TOL * np.where(RNG.random(N) < 0.5, -1.0, 1.0)
        assert s.check("steady", "bbb.cfvisx", YV + noise, YJV + noise, TOL, IMAP).ok
        for b, (label, rows) in enumerate(zip(LABELS, ROWS)):
            i = int(rows[len(rows) // 2])
            bad = YV.copy()
            bad[i] += 10 * store.C * np.sqrt(len(rows)) * TOL[i]
            c = s.check("steady", "bbb.cfvisx", bad, YJV + (bad - YV), TOL, IMAP)
            assert not c.ok and c.report.count(label + " ") == 1, (label, c.report)
        nan = YV.copy()
        nan[3] = np.nan
        assert not s.check("steady", "bbb.cfvisx", nan, YJV, TOL, IMAP).ok


@pytest.mark.parametrize("kind", mf.STORES)
def test_failing_default_names_the_stored_intermediate(tmp_path, kind):
    """AIUE-92: a sketch store keeps res* only, so the new run's other diagnostics (fnix here) are not compared; the
    first difference is the changed resco, never "fnix missing in reference". A full store compares every array."""
    from yldot.harness.compare import DIAG_SCALED_RTOL, first_difference

    build(tmp_path, kind)
    new = {"resco": DIAG["resco"] + 1.0, "fnix": DIAG["fnix"] + 1.0, "extra": np.zeros(2)}
    with store.open_store("fam", tmp_path, regions=SPEC) as s:
        ref, cut = s.diagnostic_pair("steady", new)
        d = first_difference(ref, cut, rtol=DIAG_SCALED_RTOL, scaled=True)
        bad = Y.copy()
        bad[0] += 1.0
        report = s.check("steady", None, bad, YJ + (bad - Y), TOL, IMAP, new).report
    if kind == "sketch":
        assert set(cut) == {"resco"} and d.name == "resco" and d.kind == "values"
        assert "resco" in report and "missing" not in report
    else:
        assert cut is new and d.name == "fnix"  # fnix comes first in PANDF_ORDER; every array is compared


THR_TOL = np.linspace(1e-9, 1e-7, N)


def build_thresholds(suite):
    """A sketch reference whose defaults carry sketch thresholds of THR_TOL; returns the manifest."""
    ref = Path(suite) / "references"
    ref.mkdir(parents=True, exist_ok=True)
    w = store.create(ref / "fam.h5", "sketch", "fam", DATA, IMAP)
    for config in mf.CONFIG_NAMES:
        w.write_default(config, Y, YJ, SIGMA, DIAG)
        w.write_sketch_thresholds(config, THR_TOL)
    out = w.finish()
    guarded, unguarded = mf.summarize(out["datasets"])
    m = {"schema": 1, "family": "fam", "store": "sketch", "release": None,
         "external": {mf.reference_path("fam"): {"sha256": out["sha256"], "bytes": out["bytes"]}},
         "datasets": out["datasets"], "guarded": guarded, "unguarded": unguarded,
         "provenance": mf.provenance("0" * 40, "gfortran 15", "-O3", "local"), "variables": {},
         "sketch": {"k": store.K, "seed": store.SEED}}
    mf.dump(m, mf.path("fam", suite))
    return m


def test_sketch_thresholds_round_trip(tmp_path):
    """AIUE-92 (PRD 7.11 d), AIUE-174: the stored weights are 1 / tol and the stored thresholds
    store.sketch_thresholds of the tol given with them, both guarded per configuration."""
    m = build_thresholds(tmp_path)
    assert {"steady/sketch_threshold", "timestep/sketch_threshold", "steady/sketch_weight",
            "timestep/sketch_weight"} <= set(m["guarded"])
    delta, cell = store.sketch_thresholds(THR_TOL, LABELS, ROWS, IMAP, w=1.0 / THR_TOL)
    with store.open_store("fam", tmp_path, regions=SPEC) as s:
        for config in mf.CONFIG_NAMES:
            assert s.weights(config).tobytes() == (1.0 / THR_TOL).tobytes()
            got_delta, got_cell = s.sketch_thresholds(config)
            assert got_delta.tobytes() == delta.tobytes() and got_cell == cell


def test_given_weights_are_stored(tmp_path):
    """make_references.py --only passes the stored weights on, so they are kept, not 1 / the new tol."""
    keep = np.linspace(2.0, 3.0, N)
    w = store.create(tmp_path / "s.h5", "sketch", "fam", DATA, IMAP)
    for config in mf.CONFIG_NAMES:
        w.write_default(config, Y, YJ, SIGMA, DIAG)
        w.write_sketch_thresholds(config, THR_TOL, keep)
    w.finish()
    with h5py.File(tmp_path / "s.h5", "r") as f:
        assert f["steady/default/sketch_weight"][()].tobytes() == keep.tobytes()
        delta, _ = store.sketch_thresholds(THR_TOL, LABELS, ROWS, IMAP, w=keep)
        assert f["steady/default/sketch_threshold/block"][()].tobytes() == delta.tobytes()


def test_write_sketch_thresholds_refuses(tmp_path):
    w = store.create(tmp_path / "full.h5", "full", "fam", DATA, IMAP)
    try:
        w.write_default("steady", Y, YJ, SIGMA, DIAG)
        with pytest.raises(store.StoreError, match="sketch store, not a full"):
            w.write_sketch_thresholds("steady", THR_TOL)
    finally:
        w.f.close()
    w = store.create(tmp_path / "sketch.h5", "sketch", "fam", DATA, IMAP)
    try:
        with pytest.raises(store.StoreError, match="write the default before"):
            w.write_sketch_thresholds("steady", THR_TOL)
        w.write_default("steady", Y, YJ, SIGMA, DIAG)
        with pytest.raises(ValueError, match="finite and > 0"):
            w.write_sketch_thresholds("steady", np.zeros(N))
        for bad in (np.zeros(N), np.full(N, np.nan), -np.ones(N), np.ones(N - 1)):
            with pytest.raises(ValueError, match="weights must have shape"):
                w.write_sketch_thresholds("steady", THR_TOL, bad)
        with pytest.raises(ValueError, match="1 / tol"):
            w.write_sketch_thresholds("steady", np.full(N, 1e-320))  # 1 / tol overflows
        with pytest.raises(store.StoreError, match="sketch weights .* before its variants"):
            w.write_variant("steady", "bbb.cfvisx", YV, YJV)
        w.write_sketch_thresholds("steady", THR_TOL)
        with pytest.raises(store.StoreError, match="already written"):
            w.write_sketch_thresholds("steady", THR_TOL)
    finally:
        w.f.close()


def test_consistent_tamper_of_the_sketch_thresholds_refused(tmp_path):
    """A raised threshold written into the file with its dataset SHA and the file SHA updated, guarded left: refused
    at open (check_derived), so a loosened threshold cannot hide behind an unchanged guarded key."""
    m = build_thresholds(tmp_path)
    name = "/steady/default/sketch_threshold/block"
    p = tmp_path / mf.reference_path("fam")
    with h5py.File(p, "a") as f:
        f[name][0] = 10 * f[name][0]
        m["datasets"][name] = store.dataset_sha256(f[name][()])
    mf.dump(m, mf.path("fam", tmp_path))
    reseal(tmp_path)
    with pytest.raises(store.StoreIntegrityError, match="guarded"):
        store.open_store("fam", tmp_path, regions=SPEC)


def test_consistent_tamper_of_the_sketch_weights_refused(tmp_path):
    m = build_thresholds(tmp_path)
    name = "/steady/default/sketch_weight"
    with h5py.File(tmp_path / mf.reference_path("fam"), "a") as f:
        f[name][0] = 0.5 * f[name][0]
        m["datasets"][name] = store.dataset_sha256(f[name][()])
    mf.dump(m, mf.path("fam", tmp_path))
    reseal(tmp_path)
    with pytest.raises(store.StoreIntegrityError, match=r"guarded \['steady/sketch_weight'\]"):
        store.open_store("fam", tmp_path, regions=SPEC)


def drop_or_add_weights(suite, add):
    """Remove the steady weights from a sketch file, or add some to a full one, with a consistent manifest."""
    m = mf.load("fam", suite)
    name = "/steady/default/sketch_weight"
    with h5py.File(Path(suite) / mf.reference_path("fam"), "a") as f:
        if add:
            f.create_dataset(name[1:], data=np.ones(N), track_times=False)
            m["datasets"][name] = store.dataset_sha256(np.ones(N))
        else:
            del f[name[1:]]
            del m["datasets"][name]
    m["guarded"], m["unguarded"] = mf.summarize(m["datasets"])
    mf.dump(m, mf.path("fam", suite))
    reseal(suite)


def test_weights_required_in_a_sketch_store_only(tmp_path):
    """Owner, 2026-10-23 (AIUE-174): a sketch store without weights is refused at open and at finish; a full store
    never has any."""
    build(tmp_path / "s", "sketch")
    drop_or_add_weights(tmp_path / "s", add=False)
    with pytest.raises(store.StoreIntegrityError, match=r"without sketch weights for \['steady'\]"):
        store.open_store("fam", tmp_path / "s", regions=SPEC)
    build(tmp_path / "f", "full")
    drop_or_add_weights(tmp_path / "f", add=True)
    with pytest.raises(store.StoreIntegrityError, match="full store with sketch weights"):
        store.open_store("fam", tmp_path / "f", regions=SPEC)
    w = store.create(tmp_path / "x.h5", "sketch", "fam", DATA, IMAP)
    w.write_default("steady", Y, YJ, SIGMA, DIAG)
    with pytest.raises(store.StoreError, match=r"needs its weights.*\['steady'\]"):
        w.finish()


def test_copy_variant_refuses_other_weights(tmp_path):
    """Copied variant sketches are in the source's weights: a file with other weights cannot take them."""
    build(tmp_path / "src", "sketch")
    with store.open_store("fam", tmp_path / "src", regions=SPEC) as s:
        w = store.create(tmp_path / "copy.h5", "sketch", "fam", DATA, IMAP)
        w.write_default("steady", Y, YJ, SIGMA, DIAG)
        with pytest.raises(store.StoreError, match="sketch weights .* before its variants"):
            w.copy_variant("steady", "bbb.cfvisx", s)
        w.write_sketch_thresholds("steady", TOL, 2.0 / TOL)
        with pytest.raises(store.StoreError, match="weights of .* differ"):
            w.copy_variant("steady", "bbb.cfvisx", s)
        w.f.close()


def test_sketch_bound_is_root_sum_square():
    x = np.zeros(N)
    ref = store.sketch(x, LABELS, ROWS)
    tol = np.linspace(1.0, 2.0, N)
    r = ROWS[0]
    bound = store.C * np.sqrt(np.sum(tol[r] ** 2))
    for scale, ok in ((0.999, True), (1.001, False)):
        y = x.copy()
        y[r] = scale * bound / len(r) * store.signs(store.SEED, LABELS[0], len(r), store.K)[0]
        assert store.sketch_compare(ref, store.sketch(y, LABELS, ROWS), tol, LABELS, ROWS, IMAP).ok is ok


def test_sketch_known_answer():
    """Committed known-answer vector (acceptance): the same bits and projections under numpy 2.5.4 and 1.26.4."""
    s = store.signs(store.SEED, "ni[1] core", 100, 2)
    bits = ["".join("1" if v > 0 else "0" for v in row) for row in s]
    assert bits == [
        "1100000110110110101011000101000110111100000101011111111100010101000110110100011011110100010000101100",
        "1010100010001100110110011010111110111101110100001101100110011110011111110111000010010101111010011011"]
    x = np.arange(100.0) * 0.1 + 1e-3
    assert [store.fsum(np.where(s[j] > 0, x, -x)).hex() for j in range(2)] == ["-0x1.7333333333332p+3",
                                                                                "0x1.8da9fbe76c8b5p+6"]
    assert store.signs(store.SEED, "x", 0, 3).shape == (3, 0)
    assert set(np.unique(store.signs(store.SEED, "x", 65, 3))) == {-1, 1}


def test_sketch_compare_refuses_bad_tolerances():
    z = store.sketch(np.zeros(N), LABELS, ROWS)
    for tol in (np.zeros(N), np.full(N, np.nan), np.ones(N - 1)):
        with pytest.raises(ValueError, match="tol"):
            store.sketch_compare(z, z, tol, LABELS, ROWS, IMAP)
    for w in (np.zeros(N), np.full(N, np.inf), np.ones(N - 1)):
        with pytest.raises(ValueError, match="w must"):
            store.sketch_compare(z, z, TOL, LABELS, ROWS, IMAP, w=w)
        with pytest.raises(ValueError, match="w must"):
            store.sketch(np.zeros(N), LABELS, ROWS, w=w)


# ---------------------------------------------------------------- weighted sketches (AIUE-174)

SPREAD = np.logspace(-12, -3, N)  # per-entry tolerances over nine decades, as in the owner families' blocks


def test_uniform_weights_reproduce_the_unweighted_sketch():
    """w = 1 everywhere gives the unweighted projections, verdicts, reports and thresholds bit for bit."""
    x = RNG.standard_normal(N)
    a, b = store.sketch(x, LABELS, ROWS), store.sketch(x, LABELS, ROWS, w=np.ones(N))
    assert all(a[k].tobytes() == b[k].tobytes() for k in a)
    for scale in (0.0, 1e-9, 1e-3):
        y = x + scale * RNG.standard_normal(N)
        sy = store.sketch(y, LABELS, ROWS)
        plain = store.sketch_compare(a, sy, SPREAD, LABELS, ROWS, IMAP)
        ones = store.sketch_compare(a, store.sketch(y, LABELS, ROWS, w=np.ones(N)), SPREAD, LABELS, ROWS, IMAP,
                                    w=np.ones(N))
        assert plain.ok == ones.ok and plain.lines[1:] == ones.lines[1:]
    d0, c0 = store.sketch_thresholds(SPREAD, LABELS, ROWS, IMAP)
    d1, c1 = store.sketch_thresholds(SPREAD, LABELS, ROWS, IMAP, w=np.ones(N))
    assert d0.tobytes() == d1.tobytes() and c0 == c1


def test_weights_see_a_small_tolerance_entry_at_c_sqrt_n():
    """One entry with tol_i 1e-6 times its block's others: with w = 1/tol it fails at 1.01 * c*sqrt(N) * tol_i and
    passes at 0.99 *; unweighted, 1000 times that still passes (the dilution AIUE-174 removes)."""
    r = ROWS[0]
    i = int(r[1])
    tol = np.full(N, 1e-3)
    tol[i] = 1e-9
    w = 1.0 / tol
    x = np.zeros(N)
    at = store.C * np.sqrt(len(r)) * tol[i]
    for m, ok in ((0.99, True), (1.01, False)):
        y = x.copy()
        y[i] += m * at
        c = store.sketch_compare(store.sketch(x, LABELS, ROWS, w=w), store.sketch(y, LABELS, ROWS, w=w), tol, LABELS,
                                 ROWS, IMAP, w=w)
        assert c.ok is ok, c.report
        if not ok:
            assert len(c.lines) == 2 and c.lines[1].strip().startswith(LABELS[0] + " ")
    y = x.copy()
    y[i] += 1e3 * at
    assert store.sketch_compare(store.sketch(x, LABELS, ROWS), store.sketch(y, LABELS, ROWS), tol, LABELS, ROWS,
                                IMAP).ok
    delta, _ = store.sketch_thresholds(tol, LABELS, ROWS, IMAP, w=w)
    ratio = delta[0] / (tol[r] * w[r])
    assert np.allclose(ratio, store.C * np.sqrt(len(r)), rtol=1e-12)


def test_store_check_uses_the_stored_weights(tmp_path):
    """Review I1-m2: a variant check through SketchStore.check on a store with non-uniform weights 1/SPREAD sees a
    small-tol entry at c*sqrt(N) of its own tolerance (1.01 x fails that block alone, 0.99 x passes), which the
    unweighted bound would dilute far beyond."""
    build(tmp_path, "sketch", tol=SPREAD)
    r = ROWS[0]
    i = int(r[int(np.argmin(SPREAD[r]))])
    at = store.C * np.sqrt(len(r)) * SPREAD[i]
    with store.open_store("fam", tmp_path, regions=SPEC) as s:
        assert s.weights("steady").tobytes() == (1.0 / SPREAD).tobytes()
        assert s.check("steady", "bbb.cfvisx", YV, YJV, SPREAD, IMAP).ok
        for m, ok in ((0.99, True), (1.01, False)):
            bad = YV.copy()
            bad[i] += m * at
            c = s.check("steady", "bbb.cfvisx", bad, YJV + (bad - YV), SPREAD, IMAP)
            assert c.ok is ok, c.report
            if not ok:
                assert c.report.count(LABELS[0] + " ") == 1 and "flag difference PASS" in c.report


def test_weighted_roundoff_half_the_bound_passes_twice_fails():
    """Round-off |e_i| <= tol_i passes every block (Hoeffding, unchanged by the weights); scaled so the largest
    weighted projection is 0.5 x the bound it passes, at 2 x it fails that block alone."""
    w = 1.0 / SPREAD
    e = SPREAD * RNG.uniform(-1.0, 1.0, N)
    zero = store.sketch(np.zeros(N), LABELS, ROWS, w=w)
    assert store.sketch_compare(zero, store.sketch(e, LABELS, ROWS, w=w), SPREAD, LABELS, ROWS, IMAP, w=w).ok
    for b, (label, r) in enumerate(zip(LABELS, ROWS)):
        eb = np.zeros(N)
        eb[r] = e[r]
        top = np.abs(store.sketch(eb, LABELS, ROWS, w=w)["proj"][b]).max()
        bound = store.C * np.sqrt(store.fsum((SPREAD[r] * w[r]) ** 2))
        for m, ok in ((0.5, True), (2.0, False)):
            c = store.sketch_compare(zero, store.sketch(eb * (m * bound / top), LABELS, ROWS, w=w), SPREAD, LABELS,
                                     ROWS, IMAP, w=w)
            assert c.ok is ok and (ok or c.lines[1].strip().startswith(label + " ")), (label, m, c.report)


def test_sketch_ratio_is_the_largest_projection_over_its_bound(tmp_path):
    """AIUE-99: one entry moved by m * c * sqrt(N_block) * tol_i (w = 1/tol) gives the ratio m, passing (0.5) or
    failing (2); a NaN gives inf; Store.check carries the largest of its two parts', a full store's None."""
    r = ROWS[0]
    i = int(r[0])
    w = 1.0 / SPREAD
    x = np.zeros(N)
    ref = store.sketch(x, LABELS, ROWS, w=w)
    assert store.sketch_compare(ref, ref, SPREAD, LABELS, ROWS, IMAP, w=w).ratio == 0.0
    for m, ok in ((0.5, True), (2.0, False)):
        y = x.copy()
        y[i] = m * store.C * np.sqrt(len(r)) * SPREAD[i]
        c = store.sketch_compare(ref, store.sketch(y, LABELS, ROWS, w=w), SPREAD, LABELS, ROWS, IMAP, w=w)
        assert c.ok is ok and c.ratio == pytest.approx(m, rel=1e-12)
    y = x.copy()
    y[i] = np.nan
    c = store.sketch_compare(ref, store.sketch(y, LABELS, ROWS, w=w), SPREAD, LABELS, ROWS, IMAP, w=w)
    assert not c.ok and c.ratio == np.inf
    build(tmp_path / "s", "sketch", tol=SPREAD)
    with store.open_store("fam", tmp_path / "s", regions=SPEC) as s:
        bad = YJV.copy()
        bad[i] += 2.0 * store.C * np.sqrt(len(r)) * SPREAD[i]
        c = s.check("steady", "bbb.cfvisx", YV, bad, SPREAD, IMAP)
        assert not c.ok and c.ratio == pytest.approx(2.0, rel=1e-6) and "yldot PASS" in c.report  # YJV's rounding
    build(tmp_path / "f", "full")
    with store.open_store("fam", tmp_path / "f", regions=SPEC) as s:
        assert s.check("steady", "bbb.cfvisx", YV, YJV, TOL, IMAP).ratio is None


def test_reads_are_read_only(tmp_path):
    build(tmp_path, "full")
    with store.open_store("fam", tmp_path, regions=SPEC) as s:
        with pytest.raises(ValueError, match="read-only"):
            s.default("steady")[0] += 1.0
        v, _ = s.variant("steady", "bbb.cfvisx")
        v[0] = 0.0  # a reconstructed vector is the caller's own copy
        assert s.default("steady").tobytes() == Y.tobytes()


def test_block_l2_omits_zero_blocks():
    d = np.zeros(N)
    d[ROWS[2]] = 3.0
    assert store.block_l2(d, LABELS, ROWS) == {LABELS[2]: pytest.approx(3.0 * np.sqrt(len(ROWS[2])))}


# ---------------------------------------------------------------- integrity


def test_changed_file_fails_at_open_and_at_read(tmp_path):
    build(tmp_path, "full")
    p = tmp_path / mf.reference_path("fam")
    with h5py.File(p, "r+") as f:
        f["steady/default/yldot"][4] += 1e-12
    with pytest.raises(store.StoreIntegrityError, match="SHA-256"):
        store.open_store("fam", tmp_path, regions=SPEC)
    reseal(tmp_path)  # the file SHA no longer catches it: the dataset SHA must
    with store.open_store("fam", tmp_path, regions=SPEC) as s:
        with pytest.raises(store.StoreIntegrityError, match="/steady/default/yldot"):
            s.default("steady")
        s.default("timestep")


@pytest.mark.parametrize("change", ["extra", "missing"])
def test_dataset_set_must_match(tmp_path, change):
    build(tmp_path, "full")
    with h5py.File(tmp_path / mf.reference_path("fam"), "r+") as f:
        if change == "extra":
            f.create_dataset("steady/default/added", data=np.ones(3))
        else:
            del f["timestep/default/sigma"]
    reseal(tmp_path)
    with pytest.raises(store.StoreIntegrityError, match="datasets"):
        store.open_store("fam", tmp_path, regions=SPEC)


def test_changed_blocks_refused(tmp_path):
    build(tmp_path, "full")
    with h5py.File(tmp_path / mf.reference_path("fam"), "r+") as f:
        block = f["index/block"][()]
        j = int(np.flatnonzero(block != block[0])[0])
        block[[0, j]] = block[[j, 0]]  # two rows trade blocks
        f["index/block"][...] = block
    m = reseal(tmp_path)
    with h5py.File(tmp_path / mf.reference_path("fam"), "r") as f:
        m["datasets"]["/index/block"] = store.dataset_sha256(f["index/block"][()])
    mf.dump(m, mf.path("fam", tmp_path))
    with pytest.raises(store.StoreError, match="blocks"):
        store.open_store("fam", tmp_path, regions=SPEC)


def tamper_default(tmp_path):
    """A consistent tamper: the default yldot changed in the file, datasets and external updated, guarded left."""
    with h5py.File(tmp_path / mf.reference_path("fam"), "r+") as f:
        f["steady/default/yldot"][4] += 1e-12
        sha = store.dataset_sha256(f["steady/default/yldot"][()])
    m = reseal(tmp_path)
    m["datasets"]["/steady/default/yldot"] = sha
    mf.dump(m, mf.path("fam", tmp_path))
    return m


def test_consistent_tamper_of_the_default_refused(tmp_path):
    build(tmp_path, "full")
    tamper_default(tmp_path)
    with pytest.raises(store.StoreIntegrityError, match=r"guarded \['steady/default'\]"):
        store.open_store("fam", tmp_path, regions=SPEC)


@pytest.mark.parametrize("kind", ["full", "sketch"])
def test_locality_round_trip(tmp_path, kind):
    m = build(tmp_path, kind, locality=(1e-4, LOC))
    assert sorted(n for n in m["datasets"] if "/locality/" in n) == [
        "/steady/locality/" + k for k in ("column", "delta", "dfull", "mismatch", "row")]
    assert "locality/steady" in m["guarded"] and "locality/timestep" not in m["guarded"]
    with store.open_store("fam", tmp_path, regions=SPEC) as s:
        delta, e = s.locality("steady")
        assert delta == 1e-4 and s.locality("timestep") is None
        order = np.lexsort((LOC["row"], LOC["column"]))  # stored sorted by column, then row
        for k in LOC:
            assert np.array_equal(getattr(e, k), LOC[k][order])


def test_no_locality_stored_reads_none(tmp_path):
    m = build(tmp_path, "full")
    assert not any(k.startswith("locality/") for k in m["guarded"])
    with store.open_store("fam", tmp_path, regions=SPEC) as s:
        assert s.locality("steady") is None


def test_locality_key_must_follow_the_datasets(tmp_path):
    m = build(tmp_path, "full")
    m["guarded"]["locality/steady"] = "a" * 64  # a key without datasets: no longer ignored (AIUE-100)
    mf.dump(m, mf.path("fam", tmp_path))
    with pytest.raises(store.StoreIntegrityError, match=r"guarded \['locality/steady'\]"):
        store.open_store("fam", tmp_path, regions=SPEC)


def test_consistent_tamper_of_the_locality_refused(tmp_path):
    build(tmp_path, "full", locality=(1e-4, LOC))
    with h5py.File(tmp_path / mf.reference_path("fam"), "r+") as f:
        f["steady/locality/mismatch"][0] *= 2
    m = reseal(tmp_path)
    m["datasets"]["/steady/locality/mismatch"] = store.dataset_sha256(
        h5py.File(tmp_path / mf.reference_path("fam"), "r")["steady/locality/mismatch"][()])
    mf.dump(m, mf.path("fam", tmp_path))
    with pytest.raises(store.StoreIntegrityError, match=r"guarded \['locality/steady'\]"):
        store.open_store("fam", tmp_path, regions=SPEC)


@pytest.mark.parametrize("config, delta, edit, error", [
    ("timestep", 1e-4, {}, "steady configuration only"),
    ("steady", 0.0, {}, "finite delta > 0"),
    ("steady", 1e-4, {"row": np.array([5, 2, N])}, "outside"),
    ("steady", 1e-4, {"dfull": np.array([1.0, np.nan, 1.0])}, "finite"),
    ("steady", 1e-4, {"row": np.array([5, 2])}, "unequal lengths"),
])
def test_write_locality_refuses(tmp_path, config, delta, edit, error):
    w = store.create(tmp_path / "x.h5", "full", "fam", DATA, IMAP)
    w.write_default("steady", Y, YJ, SIGMA)
    w.write_default("timestep", Y, YJ, SIGMA)
    with pytest.raises(ValueError, match=error):
        w.write_locality(config, delta, {**LOC, **edit})
    w.finish()


def test_write_locality_needs_the_default_and_runs_once(tmp_path):
    w = store.create(tmp_path / "x.h5", "full", "fam", DATA, IMAP)
    with pytest.raises(store.StoreError, match="default before"):
        w.write_locality("steady", 1e-4, LOC)
    w.write_default("steady", Y, YJ, SIGMA)
    w.write_locality("steady", 1e-4, LOC)
    with pytest.raises(store.StoreError, match="already written"):
        w.write_locality("steady", 1e-4, LOC)
    w.finish()


# ---------------------------------------------------------------- column sets and variant patterns (AIUE-101)

ADDED = {"column": np.array([3, 7]), "row": np.array([1, 4]), "mismatch": np.array([4e-5, 1e-6]),
         "dfull": np.array([2e-2, 0.0])}  # (3, 1) changed, (7, 4) new
DROPPED = {"column": np.array([0]), "row": np.array([2])}
EMPTY = {k: np.zeros(0, dtype=np.int64 if k in ("column", "row") else float) for k in LOC}
NONE = {"column": np.zeros(0, int), "row": np.zeros(0, int)}
LOC_VARIANTS = (("steady", "bbb.methe=22", ADDED, DROPPED), ("steady", "bbb.xlinc", EMPTY, NONE),
                ("timestep", "bbb.isbcwdt", ADDED, NONE))


def test_locality_columns_round_trip(tmp_path):
    m = build(tmp_path, "full", locality=(1e-4, LOC), columns=[0, 3, 8])
    assert "/steady/locality/columns" in m["datasets"]
    with store.open_store("fam", tmp_path, regions=SPEC) as s:
        assert s.locality_columns("steady").tolist() == [0, 3, 8]
    build(tmp_path, "full", locality=(1e-4, LOC))
    with store.open_store("fam", tmp_path, regions=SPEC) as s:
        assert s.locality_columns("steady") is None


def test_locality_columns_without_columns_keep_the_sha(tmp_path):
    """A family perturbing every column stores no columns dataset: its locality/steady SHA stays the AIUE-100 one."""
    a = build(tmp_path / "a", "full", locality=(1e-4, LOC))
    b = build(tmp_path / "b", "full", locality=(1e-4, LOC), columns=[0, 3])
    assert a["guarded"]["locality/steady"] != b["guarded"]["locality/steady"]
    assert a["guarded"]["locality/steady"] == mf.combined_sha(
        {n: s for n, s in a["datasets"].items() if n.startswith("/steady/locality/")})


@pytest.mark.parametrize("columns, error", [([3, 0], "increasing"), ([0, N], "below"), ([0], "not perturbed")])
def test_write_locality_columns_refused(tmp_path, columns, error):
    w = store.create(tmp_path / "x.h5", "full", "fam", DATA, IMAP)
    w.write_default("steady", Y, YJ, SIGMA)
    with pytest.raises(ValueError, match=error):
        w.write_locality("steady", 1e-4, LOC, columns=columns)
    w.finish()


@pytest.mark.parametrize("kind", ["full", "sketch"])
def test_locality_variants_round_trip(tmp_path, kind):
    from yldot.harness import locality as L

    m = build(tmp_path, kind, locality=(1e-4, LOC), loc_variants=LOC_VARIANTS)
    assert set(m["locality_variants"]) == {"bbb.methe=22", "bbb.xlinc", "bbb.isbcwdt"}
    assert m["locality_variants"]["bbb.methe=22"]["added"] == 2 and m["locality_variants"]["bbb.xlinc"] == {
        "config": "steady", "sha256": m["locality_variants"]["bbb.xlinc"]["sha256"], "added": 0, "dropped": 0}
    assert {"locality_variants/steady", "locality_variants/timestep"} <= set(m["guarded"])
    assert m["guarded"]["locality/steady"] == build(tmp_path / "plain", kind, locality=(1e-4, LOC))["guarded"][
        "locality/steady"]  # the packed group is not folded into the default's pattern
    with store.open_store("fam", tmp_path, regions=SPEC) as s:
        assert s.locality_variants("steady") == ["bbb.methe=22", "bbb.xlinc"]
        assert s.locality_variants("timestep") == ["bbb.isbcwdt"]
        added, dropped = s.locality_variant("steady", "bbb.methe=22")
        assert added.column.tolist() == [3, 7] and dropped["column"].tolist() == [0]
        _, default = s.locality("steady")
        want = L.apply(default, L.Entries.of(ADDED), DROPPED)
        got = s.locality_pattern("steady", "bbb.methe=22")
        assert all(getattr(got, k).tobytes() == getattr(want, k).tobytes() for k in L.FIELDS)
        empty = s.locality_pattern("steady", "bbb.xlinc")
        assert all(getattr(empty, k).tobytes() == getattr(default, k).tobytes() for k in L.FIELDS)
        with pytest.raises(store.StoreError, match="no stored locality"):
            s.locality_variant("timestep", "bbb.xlinc")


def test_locality_pattern_with_a_column_set_uses_the_special_columns(tmp_path, monkeypatch):
    """With stored columns (a column-set family) a variant's pattern is applied to the default's entries in the
    special cells' columns only (locality.variant_base), as generation diffs it (make_references.child)."""
    from yldot.harness import locality as L

    build(tmp_path, "full", locality=(1e-4, LOC), columns=[0, 3, 7], loc_variants=(("steady", "bbb.a", EMPTY, NONE),))
    monkeypatch.setattr(L, "special_columns", lambda data: np.array([3]))
    with store.open_store("fam", tmp_path, regions=SPEC) as s:
        got = s.locality_pattern("steady", "bbb.a")
        _, default = s.locality("steady")
    want = L.variant_base(default, np.array([3]))
    assert got.column.tolist() == [3, 3] and all(getattr(got, k).tobytes() == getattr(want, k).tobytes()
                                                  for k in L.FIELDS)


def test_locality_pattern_without_a_steady_pattern_refused(tmp_path):
    build(tmp_path, "full")
    with store.open_store("fam", tmp_path, regions=SPEC) as s:
        with pytest.raises(store.StoreError, match="no steady locality pattern"):
            s.locality_pattern("steady", "bbb.cfvisx")


def test_tampered_locality_variant_slice_refused(tmp_path):
    """A consistent tamper of the file and its dataset SHAs (guarded re-summarized too) still fails: the slice SHA in
    locality_variants no longer matches."""
    build(tmp_path, "full", locality=(1e-4, LOC), loc_variants=LOC_VARIANTS)
    p = tmp_path / mf.reference_path("fam")
    with h5py.File(p, "r+") as f:
        f["steady/locality_variants/mismatch"][0] *= 2
    m = reseal(tmp_path)
    with h5py.File(p, "r") as f:
        m["datasets"]["/steady/locality_variants/mismatch"] = store.dataset_sha256(
            f["steady/locality_variants/mismatch"][()])
    m["guarded"], m["unguarded"] = mf.summarize(m["datasets"])
    mf.dump(m, mf.path("fam", tmp_path))
    with pytest.raises(store.StoreIntegrityError, match="bbb.methe=22.*locality_variants"):
        store.open_store("fam", tmp_path, regions=SPEC)


def test_locality_variants_must_match_the_manifest(tmp_path):
    m = build(tmp_path, "full", locality=(1e-4, LOC), loc_variants=LOC_VARIANTS)
    del m["locality_variants"]["bbb.isbcwdt"]
    mf.dump(m, mf.path("fam", tmp_path))
    with pytest.raises(store.StoreIntegrityError, match="locality_variants groups"):
        store.open_store("fam", tmp_path, regions=SPEC)
    m["locality_variants"]["bbb.isbcwdt"] = dict(m["locality_variants"]["bbb.xlinc"], config="timestep")
    del m["locality_variants"]["bbb.xlinc"]
    mf.dump(m, mf.path("fam", tmp_path))
    with pytest.raises(store.StoreIntegrityError, match="differ from the manifest"):
        store.open_store("fam", tmp_path, regions=SPEC)


@pytest.mark.parametrize("edit, error", [
    ({"config": "intake"}, "not a SENSITIVE"), ({"sha256": "x"}, "64 hex"), ({"added": -1}, "integers"),
    ({"extra": 1}, "exactly the keys"),
])
def test_manifest_locality_variants_validated(tmp_path, edit, error):
    m = build(tmp_path, "full", locality=(1e-4, LOC), loc_variants=LOC_VARIANTS)
    m["locality_variants"]["bbb.xlinc"].update(edit)
    with pytest.raises(mf.ManifestError, match=error):
        mf.validate(m)


def test_write_locality_variant_refuses(tmp_path):
    w = store.create(tmp_path / "x.h5", "full", "fam", DATA, IMAP)
    w.write_default("steady", Y, YJ, SIGMA)
    with pytest.raises(store.StoreError, match="steady locality pattern before"):
        w.write_locality_variant("steady", "bbb.a", ADDED, NONE)
    w.write_locality("steady", 1e-4, LOC)
    w.write_locality_variant("steady", "bbb.a", ADDED, NONE)
    with pytest.raises(store.StoreError, match="already written"):
        w.write_locality_variant("steady", "bbb.a", ADDED, NONE)
    with pytest.raises(store.StoreError, match="another configuration"):
        w.write_locality_variant("timestep", "bbb.a", ADDED, NONE)
    with pytest.raises(ValueError, match="finite"):
        w.write_locality_variant("steady", "bbb.b", {**ADDED, "dfull": np.array([np.inf, 0.0])}, NONE)
    w.finish()


def test_variant_removed_but_still_sensitive_refused(tmp_path):
    build(tmp_path, "full")
    with h5py.File(tmp_path / mf.reference_path("fam"), "r+") as f:
        del f["steady/variants/bbb.cfvisx"]
    m = reseal(tmp_path)
    m["datasets"] = {n: s for n, s in m["datasets"].items() if "/variants/" not in n}
    mf.dump(m, mf.path("fam", tmp_path))
    with pytest.raises(store.StoreIntegrityError, match="SENSITIVE variables not stored"):
        store.open_store("fam", tmp_path, regions=SPEC)


def test_stored_variant_missing_from_variables_refused(tmp_path):
    m = build(tmp_path, "full")
    del m["variables"]["bbb.cfvisx"]
    mf.dump(m, mf.path("fam", tmp_path))
    with pytest.raises(store.StoreIntegrityError, match="stored variants not SENSITIVE"):
        store.open_store("fam", tmp_path, regions=SPEC)


def test_variable_sha_must_follow_the_datasets(tmp_path):
    m = build(tmp_path, "full")
    m["variables"]["bbb.cfvisx"]["sha256"] = "0" * 64
    mf.dump(m, mf.path("fam", tmp_path))
    with pytest.raises(store.StoreIntegrityError, match="sha256 of the variables"):
        store.open_store("fam", tmp_path, regions=SPEC)


@pytest.mark.parametrize("key", ["block_l2", "jflag_block_l2"])
def test_unknown_block_label_refused(tmp_path, key):
    m = build(tmp_path, "full")
    m["variables"]["bbb.cfvisx"][key]["ni[9] nowhere"] = 1.0
    mf.dump(m, mf.path("fam", tmp_path))
    with pytest.raises(store.StoreIntegrityError, match="not blocks of the store"):
        store.open_store("fam", tmp_path, regions=SPEC)


def test_other_index_map_refused(tmp_path):
    build(tmp_path, "full")
    other = index_map(make_data(phi_off=((0, 0),)), SPEC)
    with store.open_store("fam", tmp_path, regions=SPEC) as s:
        with pytest.raises(store.StoreError, match="index map"):
            s.check("steady", None, np.zeros(other.neq), np.zeros(other.neq), np.ones(other.neq), other)


def test_missing_file_names_fetch(tmp_path):
    build(tmp_path, "full")
    (tmp_path / mf.reference_path("fam")).unlink()
    with pytest.raises(store.StoreError, match="fetch_data.py fam"):
        store.open_store("fam", tmp_path, regions=SPEC)


def test_writer_refuses_bad_input(tmp_path):
    w = store.create(tmp_path / "x.h5", "full", "x", DATA, IMAP)
    with pytest.raises(store.StoreError, match="default"):
        w.write_variant("steady", "v", Y, YJ)
    bad = Y.copy()
    bad[0] = np.inf
    with pytest.raises(ValueError, match="non-finite"):
        w.write_default("steady", bad, YJ, SIGMA)
    with pytest.raises(ValueError, match="config"):
        w.write_default("hot", Y, YJ, SIGMA)
    w.write_default("steady", Y, YJ, SIGMA)
    with pytest.raises(ValueError, match="'/'"):
        w.write_variant("steady", "a/b", Y, YJ)
    w.finish()


# ---------------------------------------------------------------- manifest


def test_manifest_round_trip(tmp_path):
    m = build(tmp_path, "sketch")
    text = mf.path("fam", tmp_path).read_text()
    assert text == mf.dumps(m) and text.endswith("}\n") and mf.load("fam", tmp_path) == mf.loads(text)
    assert set(m["guarded"]) == {"{}/{}".format(c, k) for c in mf.CONFIG_NAMES
                                 for k in ("default", "sigma", "sketch_threshold", "sketch_weight")}
    assert set(m["unguarded"]) == {"diagnostics"}
    assert mf.asset_name("families/large_dd2c/base_state.h5") == "families--large_dd2c--base_state.h5"


def test_manifest_puts_encoded_data_on_one_line(tmp_path):
    """Owner, 2026-10-22 (AIUE-94 D9): each encoded value's data list on one line, the rest indented and sorted;
    mf.loads gives the manifest back."""
    m = build(tmp_path, "full")
    e = m["variables"]["bbb.cfvisx"]
    e["applied"] = {"dtype": "float64", "shape": [3, 100], "data": [0.1 * i for i in range(300)]}
    e["d"] = {"dtype": "int64", "shape": [], "data": [7]}
    text = mf.dumps(m)
    assert mf.loads(text) == m and '"runs"' not in text  # no repeated neighbours: data lists as before
    plain = json.dumps(m, indent=2, sort_keys=True) + "\n"
    assert plain.count("\n") - text.count("\n") == (300 + 1) + (1 + 1)  # the line breaks inside both data lists
    lines = text.splitlines()
    data = [s for s in lines if s.lstrip().startswith('"data": ')]
    assert data == ['        "data": {},'.format(json.dumps(e["applied"]["data"])), '        "data": [7],']
    assert '          3,' in lines and '          100' in lines  # shape stays one element per line
    assert len(text) < 0.8 * len(plain)
    mf.dump(m, mf.path("fam", tmp_path))
    assert mf.load("fam", tmp_path) == m
    # without encoded values it is json.dumps(indent=2, sort_keys=True), empty containers and odd strings included
    other = {"b": [], "a": {}, "c": [{"z": None, "y": [1.5, True, "\x00é\"x"]}], "d": {"data": [1, 2]}}
    assert mf.dumps(other) == json.dumps(other, indent=2, sort_keys=True) + "\n"


def test_manifest_writes_runs(tmp_path):
    """Owner, 2026-10-25 (AIUE-190): an encoded value with repeated neighbours is written as [value, count] runs when
    they are fewer than its data; mf.loads expands them bit for bit (-0.0 stays apart from 0.0, 1 from 1.0)."""
    m = build(tmp_path, "full")
    vs = m["variables"]
    vs["bbb.cfvisx"].update(applied={"dtype": "float64", "shape": [2, 50], "data": [2.86] * 97 + [0.0, -0.0, 0.0]},
                            d={"dtype": "int64", "shape": [6], "data": [1, 1, 1, 0, 0, 2]})
    vs["bbb.other"] = dict(vs["bbb.cfvisx"], applied={"dtype": "float64", "shape": [3], "data": [1.0, 2.0, 1.0]},
                           d={"dtype": "float64", "shape": [], "data": [1.0]})  # no repeats, one value: data lists
    text = mf.dumps(m)
    lines = [s.strip() for s in text.splitlines()]
    assert '"runs": [[2.86, 97], [0.0, 1], [-0.0, 1], [0.0, 1]],' in lines
    assert '"runs": [[1, 3], [0, 2], [2, 1]],' in lines
    assert '"data": [1.0, 2.0, 1.0],' in lines and '"data": [1.0],' in lines and text.count('"runs"') == 2
    back = mf.loads(text)
    assert back == m and json.dumps(back, sort_keys=True) == json.dumps(m, sort_keys=True)  # types and -0.0 kept
    assert mf.dumps(back) == text
    mf.dump(m, mf.path("fam", tmp_path))
    assert mf.load("fam", tmp_path) == m
    assert mf.runs([]) == [] and mf.runs([1, 1.0, 1]) == [[1, 1], [1.0, 1], [1, 1]]


@pytest.mark.parametrize("runs, shape, message", [
    ([[2.0, 3]], [4], "runs hold 3 values, shape \\[4\\] needs 4"),
    ([[0.0, 10 ** 12]], [10 ** 6, 10 ** 6], "more than 10000000"),
    ([[2.0, 1.5]], [1], "int count"),
    ([[2.0, 0]], [0], "int count"),
    ([[2.0, True]], [1], "int count"),
    ([2.0, 1], [2], "int count"),
    ([[2.0, 2]], [-2], "shape must be")])
def test_manifest_refuses_bad_runs(tmp_path, runs, shape, message):
    m = build(tmp_path, "full")
    m["variables"]["bbb.cfvisx"]["applied"] = {"dtype": "float64", "shape": [2], "data": [2.0, 2.0]}
    raw = json.loads(mf.dumps(m))  # the text's own form: applied as runs
    assert raw["variables"]["bbb.cfvisx"]["applied"] == {"dtype": "float64", "shape": [2], "runs": [[2.0, 2]]}
    raw["variables"]["bbb.cfvisx"]["applied"].update(runs=runs, shape=shape)
    with pytest.raises(mf.ManifestError, match=message):
        mf.loads(json.dumps(raw))


def test_validate_refuses_an_unexpanded_runs_form(tmp_path):
    m = build(tmp_path, "full")
    m["variables"]["bbb.cfvisx"]["applied"] = {"dtype": "float64", "shape": [2], "runs": [[2.0, 2]]}
    with pytest.raises(mf.ManifestError, match="applied and d must be null or variants.encode values"):
        mf.validate(m)


def test_external_only_manifest_is_valid():
    mf.validate({"schema": 1, "family": "imp7", "store": "sketch", "release": TAG,
                 "external": {"families/imp7/gridue.hdf5": {"sha256": "a" * 64, "bytes": 10}}})


@pytest.mark.parametrize("edit, message", [
    (lambda m: m.update(release="yldot-data-v0"), "release"),
    (lambda m: m.update(store="dense"), "store"),
    (lambda m: m["external"].update({"families/../x.h5": {"sha256": "a" * 64, "bytes": 1}}), "external path"),
    (lambda m: m["external"].update({"families/f/*.h5": {"sha256": "a" * 64, "bytes": 1}}), "external path"),
    (lambda m: m["external"].update({"references/y.h5": {"sha256": "XYZ", "bytes": 1}}), "64 hex"),
    (lambda m: m["variables"]["bbb.cfvisx"].update({"class": "BOGUS"}), "class"),
    (lambda m: m["variables"]["bbb.cfvisx"].update({"sha256": None}), "SENSITIVE"),
    (lambda m: m["provenance"].pop("commit"), "provenance"),
    (lambda m: m.pop("sketch"), "sketch"),
    (lambda m: m.pop("guarded"), "also needs"),
    (lambda m: m["external"]["references/fam.h5"].update(bytes=True), "bytes"),
    (lambda m: m["sketch"].update(k=True), "sketch"),
    (lambda m: m["sketch"].update(seed=True), "sketch"),
    (lambda m: m["variables"]["bbb.cfvisx"]["block_l2"].update({"ni[1] core": float("inf")}), "finite"),
    (lambda m: m["variables"]["bbb.cfvisx"]["jflag_block_l2"].update({"ni[1] core": float("nan")}), "finite"),
])
def test_manifest_validate_rejects(tmp_path, edit, message):
    m = build(tmp_path, "sketch")
    edit(m)
    with pytest.raises(mf.ManifestError, match=message):
        mf.validate(m)


# ---------------------------------------------------------------- fetch_data.py

FILES = {"families/fam/base_state.h5": b"base state bytes", "references/fam.h5": b"reference bytes"}


def data_suite(tmp_path, release=TAG, files=FILES):
    (tmp_path / "families" / "fam").mkdir(parents=True)
    (tmp_path / "references").mkdir()
    m = {"schema": 1, "family": "fam", "store": "full", "release": release,
         "external": {p: {"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)}
                      for p, b in files.items()}}
    mf.dump(m, mf.path("fam", tmp_path))
    return tmp_path


class FakeRelease:
    """A download() stand-in serving {asset: bytes}."""

    def __init__(self, served):
        self.served, self.calls = served, []

    def __call__(self, tag, assets, dest, repo):
        self.calls.append((tag, sorted(assets), repo))
        for a in assets:
            if a in self.served:
                (Path(dest) / a).write_bytes(self.served[a])


def served(files=FILES):
    return {mf.asset_name(p): b for p, b in files.items()}


def test_fetch_downloads_verifies_and_links(tmp_path):
    suite = data_suite(tmp_path)
    dl = FakeRelease(served())
    assert fetch_data.fetch(suite, download=dl, out=lambda s: None) == 0
    assert dl.calls == [(TAG, sorted(served()), fetch_data.REPO)]
    link = suite / "families/fam/base_state.h5"
    assert link.is_symlink() and os.readlink(link) == "../../.data/{}/families--fam--base_state.h5".format(TAG)
    assert link.read_bytes() == FILES["families/fam/base_state.h5"]
    assert os.readlink(suite / "references/fam.h5") == "../.data/{}/references--fam.h5".format(TAG)
    assert fetch_data.fetch(suite, check=True, download=dl, out=lambda s: None) == 0
    assert fetch_data.fetch(suite, download=dl, out=lambda s: None) == 0 and len(dl.calls) == 1  # cached
    assert not [p for p in (suite / ".data").iterdir() if p.name.startswith(".")]  # no temporary directory left


def test_fetch_refuses_a_wrong_download(tmp_path):
    suite = data_suite(tmp_path)
    bad = served()
    bad["families--fam--base_state.h5"] = b"tampered bytes!!"  # same size, other SHA-256
    lines = []
    assert fetch_data.fetch(suite, download=FakeRelease(bad), out=lines.append) == 1
    assert not (suite / ".data" / TAG / "families--fam--base_state.h5").exists()
    assert not (suite / "families/fam/base_state.h5").is_symlink()
    assert any("refused" in s and "SHA-256" in s for s in lines)
    assert not [p for p in (suite / ".data").iterdir() if p.name.startswith(".")]


def test_fetch_refuses_a_changed_cache(tmp_path):
    suite = data_suite(tmp_path)
    assert fetch_data.fetch(suite, download=FakeRelease(served()), out=lambda s: None) == 0
    cached = suite / ".data" / TAG / "references--fam.h5"
    cached.write_bytes(b"other")
    dl = FakeRelease(served())
    assert fetch_data.fetch(suite, download=dl, out=lambda s: None) == 1
    assert cached.read_bytes() == b"other" and dl.calls == []  # never overwritten
    assert fetch_data.fetch(suite, check=True, download=dl, out=lambda s: None) == 1


def test_fetch_regular_file_and_relink(tmp_path):
    suite = data_suite(tmp_path)
    regular = suite / "families/fam/base_state.h5"
    regular.write_bytes(FILES["families/fam/base_state.h5"])
    os.symlink("elsewhere", suite / "references/fam.h5")
    assert fetch_data.fetch(suite, download=FakeRelease(served()), out=lambda s: None) == 0
    assert not regular.is_symlink()
    assert os.readlink(suite / "references/fam.h5") == "../.data/{}/references--fam.h5".format(TAG)
    regular.write_bytes(b"wrong")
    assert fetch_data.fetch(suite, download=FakeRelease(served()), out=lambda s: None) == 1


def test_fetch_check_never_downloads(tmp_path):
    suite = data_suite(tmp_path)
    dl = FakeRelease(served())
    assert fetch_data.fetch(suite, check=True, download=dl, out=lambda s: None) == 1 and dl.calls == []


def test_fetch_usage_and_preview(tmp_path):
    suite = data_suite(tmp_path, release=None)
    assert fetch_data.fetch(suite, families=["nope"], out=lambda s: None) == 2
    lines = []
    assert fetch_data.fetch(suite, out=lines.append) == 0 and "local preview" in lines[0]


def test_download_command(monkeypatch, tmp_path):
    seen = []

    class Done:
        returncode, stderr = 0, ""

    monkeypatch.setattr(fetch_data.shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(fetch_data.subprocess, "run", lambda cmd, **kw: seen.append(cmd) or Done())
    fetch_data.download(TAG, ["a.h5", "b.h5"], tmp_path, "o/r")
    assert seen == [["gh", "release", "download", TAG, "-R", "o/r", "-D", str(tmp_path), "-p", "a.h5", "-p", "b.h5"]]
    monkeypatch.setattr(fetch_data.shutil, "which", lambda name: None)
    with pytest.raises(fetch_data.FetchError, match="gh"):
        fetch_data.download(TAG, ["a.h5"], tmp_path, "o/r")


# ---------------------------------------------------------------- release_data.py

SHA = "c" * 40


class FakeGh:
    """run() stand-in for git and gh."""

    def __init__(self, existing=("yldot-data-v2", "v8.1.0"), view=1, ancestor=0, pr_heads=(), create=0, remote_tag="",
                 tree_diff=0, refs=(), remote_tags=()):
        self.existing, self.view, self.ancestor, self.pr_heads, self.create = existing, view, ancestor, pr_heads, create
        self.remote_tag, self.tree_diff, self.remote_tags = remote_tag, tree_diff, remote_tags
        self.refs = list(refs)  # (rc, stderr) of each tag creation in turn; then (0, "")
        self.calls = []

    def __call__(self, cmd):
        self.calls.append(cmd)
        if cmd[:3] == ["git", "ls-remote", "--tags"] and cmd[-1].endswith("*"):  # release_data.existing
            return 0, "".join("{}\trefs/tags/{}\n".format("a" * 40, t) for t in self.remote_tags), ""
        if cmd[:3] == ["git", "ls-remote", "--tags"]:
            return 0, self.remote_tag, ""
        if cmd[:2] == ["git", "-C"] and cmd[3:5] == ["diff", "--quiet"]:
            return self.tree_diff, "", ""
        if cmd[:3] == ["gh", "release", "view"]:
            return self.view, "", ""
        if cmd[:3] == ["gh", "release", "list"]:
            return 0, json.dumps([{"tagName": t} for t in self.existing]), ""
        if cmd[:2] == ["git", "rev-parse"]:
            return 0, SHA + "\n", ""
        if cmd[:3] == ["git", "merge-base", "--is-ancestor"]:
            return self.ancestor, "", ""
        if cmd[:3] == ["gh", "pr", "list"]:
            return 0, json.dumps([{"headRefOid": h} for h in self.pr_heads]), ""
        if cmd[:3] == ["gh", "release", "create"]:
            return self.create, "https://github.com/o/r/releases/tag/x", ""
        if cmd[:4] == ["gh", "api", "-X", "POST"] and cmd[4].endswith("/git/refs"):
            rc, err = self.refs.pop(0) if self.refs else (0, "")
            return rc, "", err
        raise AssertionError(cmd)


def release_suite(tmp_path, tag=TAG):
    suite = data_suite(tmp_path, release=tag)
    for p, b in FILES.items():
        (suite / p).write_bytes(b)
    return suite


def creates(gh):
    return [c for c in gh.calls if c[:3] == ["gh", "release", "create"]]


def tags(gh):
    return [c for c in gh.calls if c[:2] == ["gh", "api"]]


def test_release_dry_run_prints_and_publishes_nothing(tmp_path):
    suite, gh, lines = release_suite(tmp_path), FakeGh(), []
    assert release_data.release(TAG, "HEAD", suite, run=gh, out=lines.append) == 0
    assert creates(gh) == [] and "gh release create {}".format(TAG) in lines[0]
    assert "--target {}".format(SHA) in lines[0] and "families--fam--base_state.h5" in lines[0]


@pytest.mark.parametrize("gh, tag, message", [
    (FakeGh(view=0), TAG, "already exists"),
    (FakeGh(existing=("yldot-data-v1",)), TAG, "next data release is yldot-data-v2"),
    (FakeGh(ancestor=1), TAG, "neither"),
    (FakeGh(), "yldot-data-v4", "no manifest names"),
    (FakeGh(remote_tag="abc\trefs/tags/yldot-data-v3\n"), TAG, "exists without a release"),
    (FakeGh(tree_diff=1), TAG, "differs from --target"),
])
def test_release_refusals(tmp_path, gh, tag, message):
    lines = []
    assert release_data.release(tag, "HEAD", release_suite(tmp_path), run=gh, out=lines.append) == 1
    assert message in lines[-1] and creates(gh) == []


def test_release_refuses_a_changed_file(tmp_path):
    suite, gh, lines = release_suite(tmp_path), FakeGh(), []
    (suite / "references/fam.h5").write_bytes(b"reference byteZ")
    assert release_data.release(TAG, "HEAD", suite, run=gh, out=lines.append) == 1
    assert "references/fam.h5" in lines[-1] and creates(gh) == []


def test_release_accepts_an_open_pr_head(tmp_path):
    gh = FakeGh(ancestor=1, pr_heads=(SHA,))
    assert release_data.release(TAG, "HEAD", release_suite(tmp_path), run=gh, out=lambda s: None) == 0


def test_release_publish_verifies_the_download(tmp_path):
    suite = release_suite(tmp_path)
    gh = FakeGh()
    assert release_data.release(TAG, "HEAD", suite, publish=True, run=gh, download=FakeRelease(served()),
                                out=lambda s: None) == 0
    assert len(creates(gh)) == 1 and "--latest=false" in creates(gh)[0] and "--verify-tag" in creates(gh)[0]
    assert gh.calls.index(tags(gh)[0]) < gh.calls.index(creates(gh)[0])  # the tag first, atomically
    assert "ref=refs/tags/{}".format(TAG) in tags(gh)[0] and "sha={}".format(SHA) in tags(gh)[0]
    bad = served()
    bad["references--fam.h5"] = b"other"
    lines = []
    assert release_data.release(TAG, "HEAD", suite, publish=True, run=FakeGh(), download=FakeRelease(bad),
                                out=lines.append) == 1
    assert "do not verify" in lines[-1]


def generated_suite(tmp_path, tag=TAG, commit=SHA):
    """release_suite with a manifest as make_references writes it: provenance names the commit it was built from."""
    suite = release_suite(tmp_path, tag)
    m = mf.load("fam", suite)
    m.update({"datasets": {"/default/yldot": "0" * 64}, "guarded": {}, "unguarded": {}, "variables": {},
              "provenance": dict({k: "x" for k in mf.PROVENANCE}, commit=commit)})
    mf.dump(m, mf.path("fam", suite))
    return suite


def test_release_generated_skips_the_committed_manifests_check(tmp_path):
    gh, lines = FakeGh(tree_diff=1), []  # --generated compares tests/yldot outside references/, not the references
    assert release_data.release(TAG, "HEAD", generated_suite(tmp_path), run=gh, out=lines.append, generated=True) == 1
    assert "outside references/" in lines[-1]
    gh, lines = FakeGh(), []
    assert release_data.release(TAG, "HEAD", generated_suite(tmp_path / "b"), run=gh, out=lines.append,
                                generated=True, note="AIUE-98 acceptance test") == 0
    diff = [c for c in gh.calls if c[3:5] == ["diff", "--quiet"]][0]
    assert diff[-2:] == ["tests/yldot", ":(exclude)tests/yldot/references"]
    assert "AIUE-98 acceptance test" in lines[0] and "generated from {}".format(SHA) in lines[0]
    assert lines[-1] == "tag={}".format(TAG) and creates(gh) == [] and tags(gh) == []


def test_release_generated_refuses_another_provenance(tmp_path):
    lines = []
    assert release_data.release(TAG, "HEAD", generated_suite(tmp_path, commit="d" * 40), run=FakeGh(),
                                out=lines.append, generated=True) == 1
    assert "generated from {}".format("d" * 40) in lines[-1] and "not from --target" in lines[-1]


def test_release_renumbers_a_stale_tag(tmp_path):
    suite, lines = generated_suite(tmp_path, tag="yldot-data-v2"), []
    gh = FakeGh(existing=("yldot-data-v1",), remote_tags=("yldot-data-v1", "yldot-data-v2"))  # v2: a tag, no release
    assert release_data.release("yldot-data-v2", "HEAD", suite, run=gh, out=lines.append, generated=True,
                                renumber=True) == 0  # a dry run: reports the N, leaves the manifests as they are
    assert lines[0] == "renumbered (dry run, manifests unchanged): yldot-data-v2 -> yldot-data-v3"
    assert mf.load("fam", suite)["release"] == "yldot-data-v2" and lines[-1] == "tag={}".format(TAG)
    assert "gh release create {}".format(TAG) in lines[1]
    lines = []
    assert release_data.release("yldot-data-v2", "HEAD", suite, publish=True, run=gh, download=FakeRelease(served()),
                                out=lines.append, generated=True, renumber=True) == 0
    assert lines[0] == "renumbered: yldot-data-v2 -> yldot-data-v3 (fam)"
    assert mf.load("fam", suite)["release"] == TAG and lines[-1] == "tag={}".format(TAG)
    assert creates(gh)[0][3] == TAG and "ref=refs/tags/{}".format(TAG) in tags(gh)[0]


def test_release_renumber_needs_generated(tmp_path):
    assert release_data.release(TAG, "HEAD", release_suite(tmp_path), run=FakeGh(), out=lambda s: None,
                                renumber=True) == 2


def test_release_collision_moves_to_the_next_n(tmp_path):
    suite, lines = generated_suite(tmp_path), []
    gh = FakeGh(refs=[(1, "gh: Reference already exists (HTTP 422)")])
    assert release_data.release(TAG, "HEAD", suite, publish=True, run=gh, download=FakeRelease(served()),
                                out=lines.append, generated=True, renumber=True) == 0
    assert [c[6] for c in tags(gh)] == ["ref=refs/tags/yldot-data-v3", "ref=refs/tags/yldot-data-v4"]
    assert creates(gh)[0][3] == "yldot-data-v4" and mf.load("fam", suite)["release"] == "yldot-data-v4"
    assert lines[-1] == "tag=yldot-data-v4"


@pytest.mark.parametrize("renumber, attempts", [(True, release_data.ATTEMPTS), (False, 1)])
def test_release_refuses_after_the_last_collision(tmp_path, renumber, attempts):
    gh, lines = FakeGh(refs=[(1, "Reference already exists")] * 5), []
    assert release_data.release(TAG, "HEAD", generated_suite(tmp_path), publish=True, run=gh, out=lines.append,
                                generated=True, renumber=renumber) == 1
    assert len(tags(gh)) == attempts and creates(gh) == [] and "created meanwhile" in lines[-1]


def test_release_refuses_a_failed_tag_creation(tmp_path):
    gh, lines = FakeGh(refs=[(1, "HTTP 403: Resource not accessible by integration")]), []
    assert release_data.release(TAG, "HEAD", release_suite(tmp_path), publish=True, run=gh, out=lines.append) == 1
    assert "creating tag" in lines[-1] and "403" in lines[-1] and creates(gh) == []


def test_release_reports_a_used_up_tag(tmp_path):
    lines = []
    assert release_data.release(TAG, "HEAD", release_suite(tmp_path), publish=True, run=FakeGh(create=1),
                                out=lines.append) == 1
    assert "exists without a release" in lines[-1]


@pytest.mark.parametrize("gh, rc", [(FakeGh(), 0), (FakeGh(ancestor=1, pr_heads=(SHA,)), 0), (FakeGh(ancestor=1), 1)])
def test_gate(gh, rc):
    lines = []
    assert release_data.gate("HEAD", run=gh, out=lines.append) == rc
    assert ("may publish" if rc == 0 else "neither") in lines[-1]
