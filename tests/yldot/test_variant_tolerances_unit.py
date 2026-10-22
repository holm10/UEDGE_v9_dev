"""tools/variant_tolerances.py (AIUE-94 D2; PRD section 7.4): check on synthetic sides (a pass, a ratio above 1, index
arrays that differ, a missing side), and collect on d_only, whose replay on the same build reproduces the sample
bit for bit (every ratio 0). collect needs the built uedge (in the Runner's children).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

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
