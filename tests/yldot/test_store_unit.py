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


def build(suite, kind, variants=(("bbb.cfvisx", YV, YJV),), family="fam", release=None):
    """A reference file and its manifest in a scratch suite; returns the manifest."""
    ref = Path(suite) / "references"
    ref.mkdir(parents=True, exist_ok=True)
    w = store.create(ref / "{}.h5".format(family), kind, family, DATA, IMAP)
    for config in mf.CONFIG_NAMES:
        w.write_default(config, Y, YJ, SIGMA, DIAG)
    for vid, yv, yjv in variants:
        w.write_variant("steady", vid, yv, yjv)
    out = w.finish()
    guarded, unguarded = mf.summarize(out["datasets"])
    variables = {vid: {"class": "SENSITIVE", "reason": "", "applied": None, "d": None, "phase": "PRE",
                       "config": "steady", "sha256": mf.variant_sha(out["datasets"], "steady", vid),
                       "block_l2": store.block_l2(yv - Y, LABELS, ROWS),
                       "jflag_block_l2": store.block_l2((yjv - yv) - (YJ - Y), LABELS, ROWS)}
                 for vid, yv, yjv in variants}
    m = {"schema": 1, "family": family, "store": kind, "release": release,
         "external": {mf.reference_path(family): {"sha256": out["sha256"], "bytes": out["bytes"]}},
         "datasets": out["datasets"], "guarded": guarded, "unguarded": unguarded,
         "provenance": mf.provenance("0" * 40, "gfortran 15", "-O3", "local"), "variables": variables}
    if kind == "sketch":
        m["sketch"] = {"k": store.K, "seed": store.SEED}
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
        for stored, x in ((ref, YV), (ref_j, YJV - YV)):
            again = store.sketch(x, LABELS, ROWS)
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


def test_locality_keys_of_guarded_are_ignored(tmp_path):
    m = build(tmp_path, "full")
    m["guarded"]["locality/steady"] = "a" * 64
    mf.dump(m, mf.path("fam", tmp_path))
    store.open_store("fam", tmp_path, regions=SPEC).close()


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
    assert text == mf.dumps(m) and text.endswith("}\n") and mf.load("fam", tmp_path) == json.loads(text)
    assert set(m["guarded"]) == {"steady/default", "timestep/default", "steady/sigma", "timestep/sigma"}
    assert set(m["unguarded"]) == {"diagnostics"}
    assert mf.asset_name("families/large_dd2c/base_state.h5") == "families--large_dd2c--base_state.h5"


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
                 tree_diff=0):
        self.existing, self.view, self.ancestor, self.pr_heads, self.create = existing, view, ancestor, pr_heads, create
        self.remote_tag, self.tree_diff = remote_tag, tree_diff
        self.calls = []

    def __call__(self, cmd):
        self.calls.append(cmd)
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
        raise AssertionError(cmd)


def release_suite(tmp_path, tag=TAG):
    suite = data_suite(tmp_path, release=tag)
    for p, b in FILES.items():
        (suite / p).write_bytes(b)
    return suite


def creates(gh):
    return [c for c in gh.calls if c[:3] == ["gh", "release", "create"]]


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
    assert len(creates(gh)) == 1 and "--latest=false" in creates(gh)[0]
    bad = served()
    bad["references--fam.h5"] = b"other"
    lines = []
    assert release_data.release(TAG, "HEAD", suite, publish=True, run=FakeGh(), download=FakeRelease(bad),
                                out=lines.append) == 1
    assert "do not verify" in lines[-1]
