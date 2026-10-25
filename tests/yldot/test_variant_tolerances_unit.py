"""tools/variant_tolerances.py (AIUE-94 D2 and D8; PRD section 7.4): check on synthetic sides (a pass, a ratio above
1, a NaN in one term, index arrays that differ, a missing side), and collect on d_only, whose replay on the same
build reproduces the sample bit for bit (every ratio 0); replay of every SENSITIVE variant under
make_references.variant_tolerance (a pass, an entry off by 2 x tol_i(variant), a NaN, a failed evaluation, another
commit) and the installed references; replay of a sketch store (large_dd2c, two variants) through the sketch
comparator under the new run's tol_i (AIUE-99 Q2). collect and replay need the built uedge (in the Runner's children).
"""
import json
import sys
import tomllib
from pathlib import Path

import numpy as np
import pytest

from yldot.harness import compare, variants
from yldot.harness.process import family_dir
from yldot.harness.state import INDEX_ARRAYS

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
    """A two-variant sweep of the owner family large_dd2c (a sketch store; one steady, one timestep variant)."""
    d = tmp_path_factory.mktemp("sketched")
    (d / "build.json").write_text(json.dumps({"commit": SHA, "compiler": "gfortran (test)", "runner_image": "t"}))
    mr.child(["large_dd2c"], d / "references", d / "build.json", sweep=["bbb.cfvisx", "bbb.fdtnixy"])
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


def test_replay_opens_the_installed_references():
    with vt.reference_stores(vt.INSTALLED, ["d_only"]) as stores:
        s = stores["d_only"]
        assert s.manifest["release"] is not None and s.variants("steady")
