"""Unit tests of serial_check.py that need no UEDGE build:  python -m pytest tests/deterministic_omp/harness"""
import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import serial_check as sc  # noqa: E402
from harness.runner import HarnessError  # noqa: E402
from harness.test_harness import FakeRecord, csr  # noqa: E402


def build(sha, openmp, name="py"):
    return {"python_arg": "/venv/{}/bin/python".format(name), "uedge_file": "/venv/{}/uedge/__init__.py".format(name),
            "extensions_sha256": sha * 16, "openmp_build": openmp}


# ---------------------------------------------------------------- cases
def test_case_tables():
    assert set(sc.QUICK) <= set(sc.ALL) and sorted(sc.ALL + list(sc.EXCLUDED)) == sorted(sc.CASES)
    for preset in ("full", "tebox", "te", "ti", "ni", "up", "ng", "full_note"):
        assert sc.CASES["repro-" + preset] == {"kind": "repro", "preset": preset}
    kinds = {sc.CASES[n]["kind"] for n in sc.QUICK}
    assert kinds == {"repro", "pytests"}
    assert sc.resolve_cases("quick") == sc.QUICK
    assert sc.resolve_cases("repro-te, pytests-D_only") == ["repro-te", "pytests-D_only"]
    assert sc.resolve_cases("repro-full_note") == ["repro-full_note"]  # excluded from "all", runnable by name
    with pytest.raises(HarnessError):
        sc.resolve_cases("repro-nope")


def test_add_files_exist_in_repo():
    for case in sc.CASES.values():
        for rel in case.get("add_files", []):
            assert os.path.isfile(os.path.join(sc.REPO_DIR, rel)), rel


def test_find_pytests_dir(tmp_path):
    (tmp_path / "pt" / "pytests" / "unittests").mkdir(parents=True)
    assert sc.find_pytests_dir(str(tmp_path / "pt")) == str(tmp_path / "pt" / "pytests")
    assert sc.find_pytests_dir(str(tmp_path / "pt" / "pytests")) == str(tmp_path / "pt" / "pytests")
    with pytest.raises(HarnessError):
        sc.find_pytests_dir(str(tmp_path / "missing"))


# ---------------------------------------------------------------- build guard
def test_check_pair():
    assert sc.check_pair("serial", build("a", False), build("b", False), False, False) == []
    same = sc.check_pair("serial", build("a", False), build("a", False), False, False)
    assert len(same) == 1 and "same build" in same[0]
    assert sc.check_pair("serial", build("a", False), build("a", False), False, True) == []
    wrong = sc.check_pair("omp0", build("a", True), build("b", False), True, False)
    assert len(wrong) == 1 and "new" in wrong[0] and "OpenMP" in wrong[0]
    wrong = sc.check_pair("serial", build("a", True), build("b", False), False, False)
    assert len(wrong) == 1 and "base" in wrong[0]


# ---------------------------------------------------------------- comparison
def captured(rec, n):
    """Give a FakeRecord n raw captured Jacobians equal to its post-exmain one."""
    rec.meta["capture"] = {"hook": True, "count": n}
    for k in range(n):
        rec.arrays["capjac_{}".format(k)] = rec.arrays["jac_post"]
        rec.arrays["capjacj_{}".format(k)] = rec.arrays["jacj_post"]
        rec.arrays["capjaci_{}".format(k)] = rec.arrays["jaci_post"]
    return rec


def test_compare_pair_hook_in_one_build_only():
    m = csr([[1.0, None], [None, 2.0]])
    base = FakeRecord("a", m, [1.0, 2.0])
    new = captured(FakeRecord("b", m, [1.0, 2.0]), 2)
    rep = sc.compare_pair("case", base, new)
    assert rep["agree"] and rep["notes"] and "jacobian:post_exmain" in rep["sections"]
    assert not any(k.startswith("jacobian:captured") for k in rep["sections"])
    rep = sc.compare_pair("case", captured(FakeRecord("a", m, [1.0, 2.0]), 1), new)
    assert rep["agree"] and "jacobian:captured[0]" in rep["sections"]
    assert new.meta["capture"]["count"] == 2  # the record itself is untouched


def test_first_mismatch_names_entry():
    m = csr([[1.0, None], [None, 2.0]])
    m2 = csr([[1.0, None], [None, 2.5]])
    rep = sc.compare_pair("case", FakeRecord("a", m, [1.0, 2.0]), FakeRecord("b", m2, [1.0, 2.0]))
    line = sc.first_mismatch(rep)
    assert line.startswith("jacobian:post_exmain (1 entries): first value at row te(ix=0,iy=0)")
    assert "base 2.0 new 2.5" in line
    rep = sc.compare_pair("case", FakeRecord("a", m, [1.0, 2.0]), FakeRecord("b", m, [1.0, -2.0]))
    assert sc.first_mismatch(rep).startswith("yldot (1 entries): first at te(ix=0,iy=0) (iv 2)")
    rep = sc.compare_pair("case", FakeRecord("a", m, [-0.0, 2.0]), FakeRecord("b", m, [0.0, 2.0]))
    assert not rep["agree"]  # serial vs serial: the signed zero counts
    assert sc.first_mismatch(sc.compare_pair("c", FakeRecord("a", m, [1.0]), FakeRecord("b", m, [1.0]))) is None


# ---------------------------------------------------------------- the whole command, with fake runs
@pytest.fixture
def fake(monkeypatch):
    """serial_check with probe_build and run_case replaced: new build differs in `diff_case`."""
    state = {"diff_case": None, "fail_case": None, "same": False}

    def probe(python, workdir):
        os.makedirs(workdir)
        role = "base" if "base" in python else "new"
        sha = "a" if (role == "base" or state["same"]) else "b"
        return build(sha + ("o" if "omp" in python else "s"), "omp" in python, python)

    def run(name, rundir, python, pytests_dir, timeout):
        os.makedirs(rundir)
        if name == state["fail_case"] and "new" in python:
            raise HarnessError("run in {} exited with 2".format(rundir))
        val = 2.5 if (name == state["diff_case"] and "new" in python) else 2.0
        rec = FakeRecord(name, csr([[1.0, None], [None, val]]), [1.0, 2.0])
        rec.rundir = rundir
        rec.meta["elapsed_s"] = 0.1
        np.savez(os.path.join(rundir, "record.npz"), **rec.arrays)
        return rec

    monkeypatch.setattr(sc, "probe_build", probe)
    monkeypatch.setattr(sc, "run_case", run)
    monkeypatch.setattr(sc, "find_pytests_dir", lambda arg=None: "/pytests")
    return state


def argv(tmp_path, *extra):
    return ["--base-python", "/base/python", "--new-python", "/new/python", "--base-omp-python",
            "/base-omp/python", "--new-omp-python", "/new-omp/python", "--out", str(tmp_path / "out")] + list(extra)


def test_main_agree(tmp_path, fake, capsys):
    assert sc.main(argv(tmp_path)) == 0
    res = json.load(open(tmp_path / "out" / "serial_check.json"))
    assert res["exit_code"] == 0 and set(res["results"]) == {"serial", "omp0"}
    assert set(res["results"]["serial"]) == set(sc.QUICK)
    assert not os.path.exists(tmp_path / "out" / "serial" / "base" / "repro-tebox" / "record.npz")  # pruned
    assert "RESULT: AGREE" in capsys.readouterr().out


def test_main_mismatch_names_case_and_entry(tmp_path, fake, capsys):
    fake["diff_case"] = "pytests-D+C"
    assert sc.main(argv(tmp_path)) == 1
    text = open(tmp_path / "out" / "summary.txt").read()
    assert "[serial] pytests-D+C" in text and "MISMATCH" in text
    assert "first mismatch: jacobian:post_exmain (1 entries): first value at row" in text
    assert os.path.exists(tmp_path / "out" / "serial" / "base" / "pytests-D+C" / "record.npz")  # kept


def test_main_harness_errors(tmp_path, fake, capsys):
    fake["fail_case"] = "pytests-D_only"
    fake["diff_case"] = "pytests-D+C"
    assert sc.main(argv(tmp_path)) == 2  # an error wins over a mismatch
    fake["fail_case"] = None
    fake["same"] = True
    assert sc.main(argv(tmp_path / "x")) == 2
    assert "same build" in capsys.readouterr().err
    assert sc.main(argv(tmp_path / "y", "--allow-same-build")) == 1  # pytests-D+C still differs
    assert sc.main(["--base-python", "/base/python", "--out", str(tmp_path / "z")]) == 2


def test_main_wrong_build_kind(tmp_path, fake, capsys):
    bad = argv(tmp_path)
    bad[bad.index("/new-omp/python")] = "/new/python"  # a serial build in the OpenMP pair
    assert sc.main(bad) == 2 and "not an OpenMP build" in capsys.readouterr().err
