"""Unit tests for ci/jac_bound.py (no UEDGE build needed): python -m pytest tests/deterministic_omp/ci"""
import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import jac_bound  # noqa: E402

# A 3x3 matrix; rows 0 and 1 are Te (eq code 2), row 2 is ni (0).
EQ = np.array([2, 2, 0])
PTR = np.array([1, 3, 5, 6])          # CSR row pointer, 1-based
COLS = np.array([1, 2, 1, 2, 3])      # 1-based columns
VALS = np.array([100.0, 1.0, 2.0, 50.0, 7.0])


def _write(d, vals=VALS, cols=COLS, ptr=PTR, captured=None, permuted=False, frm="sfsetnk"):
    os.makedirs(d, exist_ok=True)
    arrays = {"jac_post": vals, "jacj_post": cols, "jaci_post": ptr, "eq": EQ}
    cap = {"hook": captured is not None, "count": 0}
    if captured is not None:
        for k, (cv, cc, cp) in enumerate(captured):
            arrays["capjac_{}".format(k)] = cv
            arrays["capjacj_{}".format(k)] = cc
            arrays["capjaci_{}".format(k)] = cp
        cap["count"] = len(captured)
    np.savez(os.path.join(d, "record.npz"), **arrays)
    with open(os.path.join(d, "record.json"), "w") as f:
        json.dump({"neq": 3, "capture": cap, "post_exmain_permuted": permuted, "post_exmain_from": frm}, f)


def _raw(drop=False):
    """Raw (unscaled) capture: row 0 has a huge entry; dropping the col-2 entry of row 0 to 0 is a deviation of
    1.98e-4 x the raw row max (the merge-validation picture: present in serial, exactly 0 in OpenMP)."""
    v = np.array([7.92e5, 156.8, 2.0, 50.0, 7.0])
    if drop:
        v = v.copy()
        v[1] = 0.0
    return v, COLS, PTR


def _flow(tmp, run_vals, cfg="tebox", group="jac_t2", captured=None, run_captured=None, permuted=False,
          frm="sfsetnk"):
    flow = tmp / "flow"
    _write(str(flow / cfg / "serial"), captured=captured, permuted=permuted, frm=frm)
    _write(str(flow / cfg / group / "run0"), vals=run_vals, captured=run_captured, permuted=permuted, frm=frm)
    return str(flow)


def test_a_raw_capture_differs_but_scaled_post_exmain_within_bound_passes(tmp_path, capsys):
    run = VALS.copy()
    run[0] *= 1 + 4.6e-9
    flow = _flow(tmp_path, run, captured=[_raw()], run_captured=[_raw(drop=True)])
    assert jac_bound.main(["--flow", flow]) == 0
    out = capsys.readouterr().out
    assert "PASS" in out and "captured[0]: raw (unscaled), not judged" in out
    res = json.load(open(os.path.join(flow, "bound.json")))
    r = res["groups"]["tebox/jac_t2"]["runs"]["run0"]
    assert r["pass"] is True and 4e-9 < r["worst_dev"] < 5e-9
    assert 1.9e-4 < r["raw"][0]["worst_dev"] < 2.0e-4  # raw deviation is reported, not judged
    assert res["exit_code"] == 0 and res["matrix"] == "post_exmain"


def test_b_post_exmain_over_the_bound_fails(tmp_path):
    run = VALS.copy()
    run[0] *= 1 + 2e-6
    flow = _flow(tmp_path, run)
    assert jac_bound.main(["--flow", flow]) == 1
    r = json.load(open(os.path.join(flow, "bound.json")))["groups"]["tebox/jac_t2"]["runs"]["run0"]
    assert r["pass"] is False and r["over"] == 1


def test_tol_argument_changes_the_bound(tmp_path):
    run = VALS.copy()
    run[0] *= 1 + 2e-6
    flow = _flow(tmp_path, run)
    assert jac_bound.main(["--flow", flow, "--tol", "1e-5"]) == 0


def test_c_te_row_magnitude_over_ten_times_fails(tmp_path):
    run = VALS.copy()
    run[0] = 1100.0  # Te row max 100 -> 1100 (x11)
    flow = _flow(tmp_path, run)
    assert jac_bound.main(["--flow", flow, "--tol", "1e3"]) == 1
    r = json.load(open(os.path.join(flow, "bound.json")))["groups"]["tebox/jac_t2"]["runs"]["run0"]
    assert any("max|J|" in p for p in r["problems"])


def test_d_permuted_post_exmain_uses_the_global_max(tmp_path):
    # row 2 (max 7) changes by 0.5: 0.07 of its row max, but 0.005 of the global max 100
    run = VALS.copy()
    run[4] += 0.5
    flow = _flow(tmp_path, run, permuted=True, frm="psetnk")
    assert jac_bound.main(["--flow", flow, "--tol", "0.01"]) == 0
    r = json.load(open(os.path.join(flow, "bound.json")))["groups"]["tebox/jac_t2"]["runs"]["run0"]
    assert r["permuted"] is True and abs(r["worst_dev"] - 0.005) < 1e-12
    flow2 = _flow(tmp_path / "natural", run)
    assert jac_bound.main(["--flow", flow2, "--tol", "0.01"]) == 1  # natural order: row max 7 -> 0.071


def test_e_missing_serial_record_is_exit_2(tmp_path):
    flow = _flow(tmp_path, VALS.copy())
    os.remove(os.path.join(flow, "tebox", "serial", "record.npz"))
    assert jac_bound.main(["--flow", flow]) == 2
    res = json.load(open(os.path.join(flow, "bound.json")))
    assert res["groups"]["tebox/jac_t2"]["error"] and res["exit_code"] == 2


def test_permuted_disagreement_is_exit_2(tmp_path):
    flow = tmp_path / "flow"
    _write(str(flow / "tebox" / "serial"), permuted=False)
    _write(str(flow / "tebox" / "jac_t2" / "run0"), permuted=True, frm="psetnk")
    assert jac_bound.main(["--flow", str(flow)]) == 2
    r = json.load(open(str(flow / "bound.json")))["groups"]["tebox/jac_t2"]["runs"]["run0"]
    assert "disagree" in r["error"]


def test_flow_layout_keys_and_ignored_arms(tmp_path):
    flow = tmp_path / "flow"
    _write(str(flow / "full" / "serial"))
    for g in ("jac_t2", "jac_t4"):
        for k in range(2):
            _write(str(flow / "full" / g / "run{}".format(k)))
    _write(str(flow / "full" / "jacrhs_t2" / "run0"), vals=VALS * 2)  # ignored: not the jac arm
    os.makedirs(str(flow / "full" / "jac_t4" / "run2"))                # a crashed run: no record
    assert jac_bound.main(["--flow", str(flow)]) == 0
    res = json.load(open(str(flow / "bound.json")))
    assert sorted(res["groups"]) == ["full/jac_t2", "full/jac_t4"]
    assert sorted(res["groups"]["full/jac_t4"]["runs"]) == ["run0", "run1", "run2"]
    assert "skipped" in res["groups"]["full/jac_t4"]["runs"]["run2"]


def test_no_flow_directory_is_exit_2(tmp_path):
    assert jac_bound.main(["--flow", str(tmp_path / "missing"), "--json", str(tmp_path / "b.json")]) == 2
    assert json.load(open(str(tmp_path / "b.json")))["exit_code"] == 2


def test_check_dir_mode_accepts_harness_and_judges_post_exmain(tmp_path, capsys):
    d = tmp_path / "chk"
    _write(str(d / "serial"), captured=[_raw()])
    run = VALS.copy()
    run[0] *= 1 + 4.6e-9
    _write(str(d / "run0"), vals=run, captured=[_raw(drop=True)])
    # default harness (the one next to ci/): synthetic records have no provenance, so check_arm objects
    assert jac_bound.main([str(d)]) == 1
    with pytest.raises(SystemExit):
        jac_bound.main([])
    capsys.readouterr()
    harness = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # tests/deterministic_omp
    code = jac_bound.main(["--harness", harness, str(d)])
    out = capsys.readouterr().out
    assert "captured[0]: raw (unscaled), not judged" in out
    assert code == 1 and "check_arm" in out  # synthetic records have no provenance: check_arm objects


def test_nothing_to_judge_is_exit_2(tmp_path):
    flow = tmp_path / "flow"
    _write(str(flow / "tebox" / "serial"))
    os.makedirs(str(flow / "tebox" / "jac_t2"))  # a group without run directories
    assert jac_bound.main(["--flow", str(flow)]) == 2
    assert "no run directories" in json.load(open(str(flow / "bound.json")))["groups"]["tebox/jac_t2"]["error"]
    d = tmp_path / "chk"
    _write(str(d / "serial"))  # a check directory with only the serial reference
    assert jac_bound.main([str(d)]) == 2


def test_no_te_rows_prints_na_not_zero(tmp_path, capsys):
    eq = EQ.copy()
    try:
        EQ[:] = 0  # no Te rows (e.g. the up configuration)
        flow = _flow(tmp_path, VALS.copy(), cfg="up", group="jac_t4")
    finally:
        EQ[:] = eq
    assert jac_bound.main(["--flow", flow]) == 0
    assert "worst magnitude ratio n/a (no Te rows)" in capsys.readouterr().out
    r = json.load(open(os.path.join(flow, "bound.json")))["groups"]["up/jac_t4"]["runs"]["run0"]
    assert r["worst_ratio"] is None
