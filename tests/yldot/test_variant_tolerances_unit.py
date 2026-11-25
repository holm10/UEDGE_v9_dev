"""tools/variant_tolerances.py (AIUE-94 D2 and D8; PRD section 7.4): check on synthetic sides (a pass, a ratio above
1, a NaN in one term, index arrays that differ, a missing side), and collect on d_only, whose replay on the same
build reproduces the sample bit for bit (every ratio 0); replay of every SENSITIVE variant under
make_references.variant_tolerance (a pass, an entry off by 2 x tol_i(variant), a NaN, a failed evaluation, another
commit) and the installed references; replay of a sketch store (large_dd2c, two variants, built without its
locality pass, AIUE-291) through the sketch comparator under the new run's tol_i (AIUE-99 Q2); the tolerance of
an EQSET variant (T24) on synthetic maps, and its three checks on d_only and large_dd2c (eqset_result). collect and replay need the built uedge (in the Runner's children).
"""
import json
import sys
import tomllib
from pathlib import Path

import h5py
import numpy as np
import pytest

from yldot.harness import compare, locality, variants
from yldot.harness.process import family_dir
from yldot.harness.state import INDEX_ARRAYS
from yldot.test_compare_unit import SPEC, make_data, other_set

SUITE = Path(__file__).resolve().parent
sys.path.insert(0, str(SUITE / "tools"))

import make_references as mr  # noqa: E402
import variant_tolerances as vt  # noqa: E402

SHA = "0123456789abcdef0123456789abcdef01234567"
N = 6
IDS = ["bbb.a", "bbb.b"]
TOL = np.full(N, 1e-6)


def side(path, offset=0.0, index=None):
    rng = np.random.default_rng(1)
    y = rng.standard_normal((len(IDS), N))
    out = {"ids": np.array(IDS), "yldot": y + offset, "yldot_J": y.copy()}
    out.update({n: np.arange(N) if index is None else index for n in INDEX_ARRAYS})
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, **out)


def refs(tmp_path, offset=0.0):
    r = tmp_path / "refs"
    side(r / "samples" / "fam.npz")
    with np.load(r / "samples" / "fam.npz") as z:
        d = {k: z[k] for k in z.files}
    np.savez(r / "samples" / "fam.npz", configs=np.array(["steady", "timestep"]), tol_steady=TOL, tol_timestep=TOL,
             **d)
    side(tmp_path / "coll" / "mac-serial" / "fam.npz", offset)
    side(tmp_path / "coll" / "mac-noopt" / "fam.npz", offset)
    return r, tmp_path / "coll"


def test_check_passes_within_tol(tmp_path, capsys):
    r, coll = refs(tmp_path, offset=0.5e-6)
    assert vt.main(["vt", "check", str(r), str(coll), "--report", str(tmp_path / "rep.md")]) == 0
    out = capsys.readouterr().out
    assert "fam: 2 variants, largest ratio mac_vs_linux 0.5 (bbb.a), o0_vs_o3 0 (bbb.a)" in out
    assert "| fam | mac_vs_linux | 2 | 0.5 | bbb.a |" in (tmp_path / "rep.md").read_text()


def test_check_fails_above_tol(tmp_path, capsys):
    r, coll = refs(tmp_path, offset=3e-6)
    assert vt.main(["vt", "check", str(r), str(coll)]) == 3
    assert "over 1: ['bbb.a', 'bbb.b']" in capsys.readouterr().out


def test_check_refuses_other_index_arrays_and_a_missing_side(tmp_path, capsys):
    r, coll = refs(tmp_path)
    side(coll / "mac-noopt" / "fam.npz", index=np.arange(N)[::-1].copy())
    assert vt.main(["vt", "check", str(r), str(coll)]) == 3
    assert "differs between the builds" in capsys.readouterr().err
    (coll / "mac-noopt" / "fam.npz").unlink()
    assert vt.main(["vt", "check", str(r), str(coll)]) == 2


@pytest.fixture(scope="module")
def sampled(tmp_path_factory):
    d = tmp_path_factory.mktemp("sampled")
    (d / "build.json").write_text(json.dumps({"commit": SHA, "compiler": "gfortran (test)", "runner_image": "t"}))
    mr.child(["d_only"], d / "references", d / "build.json", sweep=["bbb.cfvisx", "bbb.isbcwdt", "bbb.xlinc"])
    return d


def test_collect_replays_the_sample_bit_for_bit(tmp_path, sampled, capsys):
    refs_dir = sampled / "references"
    for label in ("mac-serial", "mac-noopt"):
        vt.collect(refs_dir, label, tmp_path / "coll", sampled / "build.json", [])
    with np.load(tmp_path / "coll" / "mac-serial" / "d_only.npz") as z:
        assert z["ids"].tolist() == ["bbb.isbcwdt", "bbb.cfvisx"]  # the SENSITIVE ones, plan order
    assert vt.check(refs_dir, tmp_path / "coll", []) == 0.0


def test_collect_refuses_another_commit(tmp_path, sampled):
    (tmp_path / "other.json").write_text(json.dumps({"commit": "f" * 40}))
    with pytest.raises(vt.Stop, match="the references are of"):
        vt.collect(sampled / "references", "mac-serial", tmp_path / "coll", tmp_path / "other.json", [])


def test_a_nan_in_either_term_fails(tmp_path, capsys):
    """Review I1-m3: max(0.5, nan) is 0.5; a NaN in yldot_J must fail although yldot's ratio is finite."""
    assert vt.worst(np.array([0.5e-6, np.nan]), np.full(2, 1e-6)) == float("inf")
    assert vt.worst(np.array([0.5e-6, 0.0]), np.full(2, 1e-6)) == 0.5
    r, coll = refs(tmp_path)
    with np.load(coll / "mac-serial" / "fam.npz") as z:
        d = {k: z[k] for k in z.files}
    d["yldot_J"][0, 3] = np.nan
    np.savez(coll / "mac-serial" / "fam.npz", **d)
    assert vt.main(["vt", "check", str(r), str(coll)]) == 3
    assert "over 1: ['bbb.a']" in capsys.readouterr().out


# ---------------------------------------------------------------- replay (review I1-B1, owner D8)


def test_variant_tolerance_is_the_prd_rule_with_the_variants_reference(sampled):
    """D8: tol_i(variant) = max(rtol_eq*|ref_i(variant)|, k*sigma_i), sigma the default's; for the default's own yldot
    it is the default's tol_i."""
    fdir = family_dir("d_only")
    with open(SUITE / "tolerances.toml", "rb") as f:
        t = tomllib.load(f)
    with vt.reference_stores(sampled / "references", []) as stores:
        s = stores["d_only"]
        for config, vid in (("steady", "bbb.cfvisx"), ("timestep", "bbb.isbcwdt")):
            ref, _ = s.variant(config, vid)
            tv = mr.variant_tolerance(fdir, ref, config, s.imap)
            assert np.array_equal(tv, compare.tolerances(ref, s.sigma(config), t["rtol"], t["rule"]["k"],
                                                         s.imap).tol)
            assert (tv >= t["rule"]["k"] * s.sigma(config)).all()
            assert not np.array_equal(tv, mr.tolerance(fdir, s.default(config), config, s.imap))
            assert np.array_equal(mr.variant_tolerance(fdir, s.default(config), config, s.imap),
                                  mr.tolerance(fdir, s.default(config), config, s.imap))


RTOL = {"ni": 1e-8, "up": 2e-8, "te": 3e-8, "ti": 4e-8, "ng": 5e-8, "tg": 6e-8, "phi": 7e-8}


def eqset_case(tmp_path, rtol=RTOL):
    """A scratch suite with a sigma.h5 and tolerances.toml for the synthetic default (make_data) and its other_set
    variant: (family directory, default map, variant map, sigma, (i0, i1, added))."""
    base, imap = (compare.index_map(d, SPEC) for d in (make_data(), make_data(edit=other_set)))
    sig = np.linspace(1e-13, 2e-13, base.neq)
    sig[base.eq == "up"] = 0.0
    sig[np.flatnonzero(base.eq == "up")[:2]] = (3e-12, 5e-12)
    with h5py.File(tmp_path / "sigma.h5", "w") as f:
        for config in ("steady", "timestep"):
            f["{}/sigma".format(config)] = sig * (1 if config == "steady" else 2)
    lines = ["[rule]", "k = 100.0", "[rtol]"] + ["{} = {!r}".format(e, v) for e, v in rtol.items()]
    (tmp_path / "tolerances.toml").write_text("\n".join(lines) + "\n")
    return tmp_path, base, imap, sig, compare.mapping(base, imap)


def test_eqset_tolerance_of_the_shared_rows_is_the_default_rule(tmp_path):
    """Owner, T24: the variant's values under compare.tolerances on the default's map, sigma and floors, cut to the
    shared rows; the rows the variant lacks (te) keep their say in the default's floors and nothing escalates."""
    fdir, base, imap, sig, (i0, i1, added) = eqset_case(tmp_path)
    ref = np.random.default_rng(24).standard_normal(imap.neq) * 1e3
    for config, f in (("steady", 1), ("timestep", 2)):
        tol = mr.eqset_tolerance(fdir, ref, config, base, imap, suite=tmp_path)
        placed = np.random.default_rng(1).standard_normal(base.neq)  # what the missing rows hold does not matter
        placed[i0] = ref[i1]
        assert np.array_equal(tol[i1], compare.tolerances(placed, sig * f, RTOL, 100.0, base).tol[i0])
        assert (tol > 0).all()
    # by hand: a ti row, rtol_ti * |ref| against 100 sigma_i of the default's row of the same equation and cell
    k = int(np.flatnonzero(imap.eq[i1] == "ti")[0])
    tol = mr.eqset_tolerance(fdir, ref, "steady", base, imap, suite=tmp_path)
    assert tol[i1[k]] == max(4e-8 * abs(ref[i1[k]]), 100.0 * sig[i0[k]])


def test_eqset_tolerance_of_the_added_rows(tmp_path):
    """D2, by hand: rtol_eq * max(|ref_i|, the largest |ref| of the added rows of the block); a block of zeros takes
    the smallest block maximum > 0 of its equation and species."""
    fdir, base, imap, _, (i0, i1, added) = eqset_case(tmp_path)
    ref = np.zeros(imap.neq)
    ng = added[imap.eq[added] == "ng"]
    guard, core, pf = (ng[imap.region[ng] == r] for r in ("guard", "core", "pf"))
    ref[guard] = np.linspace(-7.0, 3.0, guard.size)  # largest |ref| 7
    ref[pf] = 0.5
    ref[added[imap.eq[added] == "tg"]] = 100.0
    ref[i1] = 1e9  # the shared rows have no say
    tol = mr.eqset_tolerance(fdir, ref, "steady", base, imap, suite=tmp_path)
    assert guard.size == 14 and core.size == 1 and pf.size == 2
    assert np.array_equal(tol[guard], np.full(guard.size, 5e-8 * 7.0))
    assert np.array_equal(tol[pf], np.full(2, 5e-8 * 0.5))
    assert np.array_equal(tol[core], [5e-8 * 0.5])  # a block of zeros: the smallest maximum > 0, pf's
    assert np.array_equal(tol[imap.eq == "tg"], np.full(int((imap.eq == "tg").sum()), 6e-8 * 100.0))


def test_eqset_tolerance_refuses(tmp_path):
    fdir, base, imap, _, (i0, i1, added) = eqset_case(tmp_path)
    ref = np.ones(imap.neq)
    ref[imap.eq == "tg"] = 0.0
    with pytest.raises(compare.ToleranceEscalation, match=r"tg\[1\]: the 19 rows the default lacks are 0 everywhere"):
        mr.eqset_tolerance(fdir, ref, "steady", base, imap, suite=tmp_path)
    ref[imap.eq == "tg"] = np.nan
    with pytest.raises(ValueError, match="finite"):
        mr.eqset_tolerance(fdir, ref, "steady", base, imap, suite=tmp_path)
    with pytest.raises(ValueError, match="shape"):
        mr.eqset_tolerance(fdir, np.ones(base.neq), "steady", base, imap, suite=tmp_path)
    (tmp_path / "b").mkdir()
    fdir, base, imap, *_ = eqset_case(tmp_path / "b", {e: v for e, v in RTOL.items() if e != "tg"})
    with pytest.raises(ValueError, match=r"no value for equations \['tg'\]"):
        mr.eqset_tolerance(fdir, np.ones(imap.neq), "steady", base, imap, suite=tmp_path / "b")


def test_replay_reproduces_every_sensitive_variant(tmp_path, sampled, capsys):
    out = tmp_path / "replay.json"
    assert vt.main(["vt", "replay", str(sampled / "references"), "--build", str(sampled / "build.json"),
                    "--json", str(out)]) == 0
    assert "d_only: 2 SENSITIVE replayed, 0 fail, largest ratio 0 (" in capsys.readouterr().out
    rows = json.loads(out.read_text())["families"]["d_only"]
    assert rows == {"bbb.isbcwdt": {"ok": True, "ratio": 0.0}, "bbb.cfvisx": {"ok": True, "ratio": 0.0}}


@pytest.mark.parametrize("kind", ["offset", "nan", "error"])
def test_replay_fails_what_does_not_reproduce(tmp_path, sampled, monkeypatch, capsys, kind):
    """Exit 3: an entry 2 x tol_i(variant) off (in the flag difference only), a NaN, a failed evaluation."""
    from yldot.harness import Result
    from yldot.harness.process import Runner

    with vt.reference_stores(sampled / "references", []) as stores:
        s = stores["d_only"]
        tol = mr.variant_tolerance(family_dir("d_only"), s.variant("steady", "bbb.cfvisx")[0], "steady", s.imap)
    real = Runner.evaluate

    def changed(self, family, **kw):
        r = real(self, family, **kw)
        if kw["variant"].id != "bbb.cfvisx":
            return r
        if kind == "error":
            return Result(status="error", family=family, config="steady", mode="spawn",
                          message="Traceback\nRuntimeError\n", log_tail="*** boom")
        r.data["yldot_J"][5] += 2 * tol[5] if kind == "offset" else np.nan
        return r

    monkeypatch.setattr(Runner, "evaluate", changed)
    out = tmp_path / "replay.json"
    assert vt.main(["vt", "replay", str(sampled / "references"), "--json", str(out)]) == 3
    text = capsys.readouterr()
    rows = json.loads(out.read_text())["families"]["d_only"]
    assert rows["bbb.isbcwdt"] == {"ok": True, "ratio": 0.0} and not rows["bbb.cfvisx"]["ok"]
    if kind == "offset":
        assert rows["bbb.cfvisx"]["ratio"] == pytest.approx(2.0)
    else:
        assert rows["bbb.cfvisx"]["ratio"] == float("inf")
    if kind == "error":
        assert rows["bbb.cfvisx"]["message"] == "error: RuntimeError (log: *** boom)"
    assert "d_only: 2 SENSITIVE replayed, 1 fail" in text.out and "the epic owner decides" in text.err


def test_replay_refuses_another_commit_and_missing_families(tmp_path, sampled):
    (tmp_path / "other.json").write_text(json.dumps({"commit": "f" * 40}))
    with pytest.raises(vt.Stop, match="the references are of"):
        vt.replay(sampled / "references", [], tmp_path / "other.json")
    with pytest.raises(vt.Stop, match="no references with classified variants for"):
        vt.replay(sampled / "references", ["ortho"])


@pytest.fixture(scope="module")
def sketched(tmp_path_factory):
    """A two-variant sweep of the owner family large_dd2c (a sketch store; one steady, one timestep variant), without
    its locality pass: replay never reads locality data, and the pass is 228 of the sweep's 230 s on macOS (up to
    720 s per build on the CI runner, where each xdist worker builds this fixture; AIUE-291)."""
    d = tmp_path_factory.mktemp("sketched")
    (d / "build.json").write_text(json.dumps({"commit": SHA, "compiler": "gfortran (test)", "runner_image": "t"}))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(locality, "load_config", lambda fdir: None)
        mr.child(["large_dd2c"], d / "references", d / "build.json", sweep=["bbb.cfvisx", "bbb.fdtnixy"])
    m = json.loads((d / "references" / "large_dd2c.json").read_text())
    stored = [k for k in m["datasets"] if "/locality" in k]
    assert not stored and not m.get("locality_variants"), (
        "the sketch store holds locality data {}: make_references.child no longer reads [locality] through "
        "locality.load_config, so this fixture runs the locality pass again (AIUE-291)".format(stored[:3]))
    return d


def test_replay_of_a_sketch_store(tmp_path, sketched, capsys):
    """AIUE-99 Q2: a sketch store's SENSITIVE variants replay through the sketch comparator, ratio |dP| / bound."""
    out = tmp_path / "replay.json"
    assert vt.main(["vt", "replay", str(sketched / "references"), "--build", str(sketched / "build.json"),
                    "--json", str(out)]) == 0
    assert "large_dd2c: 2 SENSITIVE replayed, 0 fail, largest ratio 0 (" in capsys.readouterr().out
    rows = json.loads(out.read_text())["families"]["large_dd2c"]
    assert rows == {"bbb.cfvisx": {"ok": True, "ratio": 0.0}, "bbb.fdtnixy": {"ok": True, "ratio": 0.0}}


@pytest.mark.parametrize("kind", ["offset", "nan", "error"])
def test_replay_of_a_sketch_store_fails_what_does_not_reproduce(tmp_path, sketched, monkeypatch, capsys, kind):
    """In a sketch store: a flag-difference entry 1e6 x its tol_i off fails with a finite ratio above 1 and the
    failing block in the report; a NaN fails with inf; a failed evaluation keeps its status."""
    from yldot.harness import Result
    from yldot.harness.process import Runner

    real = Runner.evaluate

    def changed(self, family, **kw):
        r = real(self, family, **kw)
        if kw["variant"].id != "bbb.cfvisx":
            return r
        if kind == "error":
            return Result(status="error", family=family, config="steady", mode="spawn",
                          message="Traceback\nRuntimeError\n", log_tail="*** boom")
        fdir = family_dir(family)
        tol = mr.tolerance(fdir, r.data["yldot"], "steady", compare.index_map(r.data, compare.load_regions(fdir)))
        r.data["yldot_J"][5] += 1e6 * tol[5] if kind == "offset" else np.nan
        return r

    monkeypatch.setattr(Runner, "evaluate", changed)
    with vt.reference_stores(sketched / "references", []) as stores:
        s = stores["large_dd2c"]
        plan = {v.id: v for v in variants.plan()}
        row = vt.check_sensitive("large_dd2c", s, Runner(), plan["bbb.cfvisx"],
                                 s.manifest["variables"]["bbb.cfvisx"], None)
    assert not row["ok"]
    if kind == "offset":
        assert 1 < row["ratio"] < float("inf") and "flag difference FAIL" in row["report"]
        assert "yldot PASS" in row["report"]
    elif kind == "nan":
        assert row["ratio"] == float("inf") and "flag difference FAIL" in row["report"]
    else:
        assert row["ratio"] == float("inf") and row["status"] == "error"


# ---------------------------------------------------------------- EQSET variants (T24)


@pytest.fixture(scope="module")
def eqsets(tmp_path_factory):
    """A d_only sweep: te off (rows removed, nothing else moves), phi off (the te rows move), tg on (rows added), and a
    SENSITIVE variant."""
    d = tmp_path_factory.mktemp("eqsets")
    (d / "build.json").write_text(json.dumps({"commit": SHA, "compiler": "gfortran (test)", "runner_image": "t"}))
    mr.child(["d_only"], d / "references", d / "build.json",
             sweep=["bbb.isteon", "bbb.isphion", "bbb.istgon", "bbb.cfvisx"])
    return d


@pytest.fixture(scope="module")
def eqsets_sketched(tmp_path_factory):
    """A sketch store's: large_dd2c without its locality pass (as sketched): tg swapped (rows removed and added)."""
    d = tmp_path_factory.mktemp("eqsets_sketched")
    (d / "build.json").write_text(json.dumps({"commit": SHA, "compiler": "gfortran (test)", "runner_image": "t"}))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(locality, "load_config", lambda fdir: None)
        mr.child(["large_dd2c"], d / "references", d / "build.json", sweep=["bbb.istgon"])
    return d


def test_replay_reproduces_every_eqset_variant(tmp_path, eqsets, capsys):
    out = tmp_path / "replay.json"
    assert vt.main(["vt", "replay", str(eqsets / "references"), "--build", str(eqsets / "build.json"),
                    "--json", str(out)]) == 0
    assert "d_only: 1 SENSITIVE and 3 EQSET replayed, 0 fail, largest ratio 0 (" in capsys.readouterr().out
    rows = json.loads(out.read_text())["families"]["d_only"]
    assert set(rows) == {"bbb.isteon", "bbb.isphion", "bbb.istgon", "bbb.cfvisx"}
    assert all(r == {"ok": True, "ratio": 0.0} for r in rows.values())


def eqset_rows(refs, change, default=lambda d: None):
    """{id: check_eqset's row} with change(id, data, store) applied to every variant's data and default to the live
    default's."""
    from yldot.harness import Runner

    plan = {v.id: v for v in variants.plan()}
    runner, out = Runner(), {}
    with vt.reference_stores(refs / "references", []) as stores:
        for name, s in stores.items():
            base = runner.evaluate(name).data
            default(base)
            for vid, e in s.manifest["variables"].items():
                if e["class"] != "EQSET":
                    continue
                r = runner.evaluate(name, variant=plan[vid], replay=e["applied"])
                change(vid, r.data, s)
                out[vid] = vt.eqset_result(name, s, plan[vid], e, r, base)
    return out


def row_of(d, eq, name, k=0):
    """The k-th row of equation eq in the first cell that has a row of it."""
    imap = compare.index_map(d, compare.load_regions(family_dir(name)))
    return int(np.flatnonzero(imap.eq == eq)[k])


def test_eqset_values_off_are_not_hard(eqsets):
    """A value out of tolerance in a block that moved, or in an added row, fails check 2 alone: finite, not hard."""
    def change(vid, d, s):
        if vid == "bbb.isphion":  # the te rows moved at generation
            imap = compare.index_map(d, compare.load_regions(family_dir("d_only")))
            i = int(np.flatnonzero((imap.eq == "te") & (imap.region == "core"))[0])
            d["yldot"][i] *= 1 + 1e-5
            d["yldot_J"][i] *= 1 + 1e-5
        if vid == "bbb.istgon":
            d["yldot_J"][row_of(d, "tg", "d_only")] += 1e6 * np.abs(d["yldot"]).max()
    rows = eqset_rows(eqsets, change)
    assert rows["bbb.isteon"] == {"ok": True, "ratio": 0.0}
    for vid, label in (("bbb.isphion", "te[1]"), ("bbb.istgon", "tg[1]")):
        row = rows[vid]
        assert not row["ok"] and 1 < row["ratio"] < np.inf and "hard" not in row and label in row["report"], row


def test_eqset_unmoved_block_is_compared_with_the_live_default(eqsets):
    """Check 3: the variant equals its stored reference, the live default differs from it in rows the variant left
    unmoved: every variant with that block unmoved fails, whatever the build."""
    def default(d):
        i = row_of(d, "ti", "d_only", 3)
        d["yldot_J"][i] += 1e-3 * np.abs(d["yldot"]).max()
    rows = eqset_rows(eqsets, lambda vid, d, s: None, default)
    for vid in ("bbb.isteon", "bbb.istgon", "bbb.isphion"):
        assert not rows[vid]["ok"] and rows[vid]["hard"] and rows[vid]["ratio"] == 0.0
        assert "blocks unmoved at generation differ from the live default: ti[1]" in rows[vid]["report"]


def test_eqset_moved_block_is_not_compared_with_the_live_default(eqsets):
    """The te rows of phi off are in layout.moved: a live default that differs there is no failure; te off has no te."""
    def default(d):
        imap = compare.index_map(d, compare.load_regions(family_dir("d_only")))
        i = int(np.flatnonzero((imap.eq == "te") & (imap.region == "core"))[0])
        d["yldot"][i] += 1e-3 * np.abs(d["yldot"]).max()
    rows = eqset_rows(eqsets, lambda vid, d, s: None, default)
    assert rows["bbb.isphion"]["ok"] and rows["bbb.isteon"]["ok"] and rows["bbb.istgon"].get("hard")


@pytest.mark.parametrize("kind, message", [
    ("nan", "non-finite yldot or yldot_J"), ("order", "row order: "), ("switch", "equation masks: "),
    ("idx", "index truth: "), ("layout", "the layout has neq"), ("sha", "rows of the layout differ")])
def test_eqset_layout_and_non_finite_failures_are_hard(eqsets, kind, message):
    """Check 1 and a non-finite entry: no build's round-off explains them (test_variants never reports them only)."""
    def change(vid, d, s):
        if kind == "nan":
            d["yldot_J"][11] = np.nan
        elif kind == "order":  # two species' rows swapped within one cell: the bijection and igyl hold
            d["idxn"][3, 3] = d["idxn"][3, 3][::-1].copy()
        elif kind == "switch":
            d["switches"]["istioffxy"][2, 2] = 1
        elif kind == "idx":
            d["idxti"][2, 2] = 0
        else:
            lay = s.manifest["variables"][vid]["layout"]
            lay.update(neq=lay["neq"] + 1) if kind == "layout" else lay.update(sha256="a" * 64)
    for vid, row in eqset_rows(eqsets, change).items():
        assert not row["ok"] and row["hard"] and row["ratio"] == np.inf and message in row["report"], (vid, row)


def test_eqset_of_a_sketch_store(eqsets_sketched):
    """large_dd2c, tg swapped: the shared rows through the sketches, the added rows one by one, unmoved blocks live."""
    ok = eqset_rows(eqsets_sketched, lambda vid, d, s: None)
    assert ok == {"bbb.istgon": {"ok": True, "ratio": 0.0}}

    def added(vid, d, s):
        imap = compare.index_map(d, compare.load_regions(family_dir("large_dd2c")))
        i = int(compare.mapping(s.imap, imap)[2][5])
        d["yldot"][i] *= 1 + 1e-4
        d["yldot_J"][i] *= 1 + 1e-4

    def shared(vid, d, s):
        i = row_of(d, "ti", "large_dd2c", 100)
        d["yldot_J"][i] += np.abs(d["yldot"]).max()

    row = eqset_rows(eqsets_sketched, added)["bbb.istgon"]
    assert not row["ok"] and 1 < row["ratio"] < np.inf and "added rows: yldot FAIL" in row["report"]
    assert "hard" not in row
    row = eqset_rows(eqsets_sketched, shared)["bbb.istgon"]
    assert not row["ok"] and "flag difference FAIL" in row["report"] and row.get("hard")  # ti is unmoved


def test_a_failed_eqset_evaluation_keeps_its_status(eqsets, monkeypatch):
    from yldot.harness import Result, Runner

    real = Runner.evaluate

    def fails(self, family, **kw):
        if "variant" not in kw:
            return real(self, family, **kw)
        return Result(status="error", family=family, config="steady", mode="spawn", message="Traceback\nRuntimeError: x\n",
                      log_tail="")

    monkeypatch.setattr(Runner, "evaluate", fails)
    plan = {v.id: v for v in variants.plan()}
    with vt.reference_stores(eqsets / "references", []) as stores:
        rows = vt.replay_family("d_only", stores["d_only"], Runner(), plan, None)
    assert rows["bbb.isteon"] == {"ok": False, "ratio": float("inf"), "status": "error", "message": "error: RuntimeError: x"}


def test_replay_opens_the_installed_references():
    with vt.reference_stores(vt.INSTALLED, ["d_only"]) as stores:
        s = stores["d_only"]
        assert s.manifest["release"] is not None and s.variants("steady")
