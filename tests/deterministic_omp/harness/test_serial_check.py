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


def build(sha, openmp, name="py", src=None, head=None, dirty=False, on_base=True):
    source = {"dir": src or "/src/" + sha, "head": head or (sha * 40)[:40], "dirty": dirty, "on_base_ref": on_base,
              "url": "file://" + (src or "/src/" + sha)}
    return {"python_arg": "/venv/{}/bin/python".format(name), "uedge_file": "/venv/{}/uedge/__init__.py".format(name),
            "extensions_sha256": sha * 16, "openmp_build": openmp, "source": source}


# ---------------------------------------------------------------- cases
def test_case_tables():
    assert set(sc.QUICK) <= set(sc.ALL) and sorted(sc.ALL + list(sc.EXCLUDED)) == sorted(sc.CASES)
    for preset in ("full", "tebox", "te", "ti", "ni", "up", "ng", "te_phi"):
        assert sc.CASES["repro-" + preset] == {"kind": "repro", "preset": preset}
    kinds = {sc.CASES[n]["kind"] for n in sc.QUICK}
    assert kinds == {"repro", "yldot"}
    assert sc.resolve_cases("quick") == sc.QUICK
    assert sc.resolve_cases("repro-te, yldot-d_only") == ["repro-te", "yldot-d_only"]
    assert any(sc.CASES[n].get("itermx") for n in sc.QUICK)  # the solver path is in quick and all
    assert sum(1 for n in sc.ALL if sc.CASES[n].get("itermx")) >= 5
    assert sc.CASES["repro-full-it3"]["itermx"] == 3 and "repro-full-it3" in sc.ALL
    names = sc.resolve_cases("repro:te@it2,yldot:d_mols+tg_mol_istgpfc4@it4,yldot:imp7")
    assert sc.CASES[names[0]] == {"kind": "repro", "preset": "te", "itermx": 2}
    assert sc.CASES[names[1]] == {"kind": "yldot", "family": "d_mols", "settings": "tg_mol_istgpfc4", "itermx": 4}
    assert sc.CASES[names[2]] == {"kind": "yldot", "family": "imp7", "settings": None}  # by name only
    for bad in ("repro:nope@it2", "repro-nope", "yldot:nope", "yldot:d_only+nope", "repro:te+istewc3"):
        with pytest.raises(HarnessError):
            sc.resolve_cases(bad)


def test_case_files_exist():
    """Every case's family and settings file exist, every case of "all" has its state in the repository, and
    every settings file is used by a case."""
    used = set()
    for name, case in sc.CASES.items():
        if case["kind"] != "yldot":
            continue
        family, settings = sc.family_files(case)
        assert os.path.isfile(os.path.join(family, "input.py")), name
        if name in sc.ALL:
            assert os.path.isfile(os.path.join(family, sc.STATE)), name
        if settings:
            assert os.path.isfile(settings), name
            used.add(os.path.relpath(settings, sc.SETTINGS))
    files = {os.path.join(f, n) for f in os.listdir(sc.SETTINGS) for n in os.listdir(os.path.join(sc.SETTINGS, f))
             if n.endswith(".py")}
    assert files == used


def test_mapping():
    """The coverage of the upstream-suite cases it replaces (AIUE-106, owner 2026-10-24)."""
    settings = [n for n in sc.ALL if sc.CASES[n].get("settings")]
    assert sum(sc.CASES[n]["family"] == "d_only" for n in settings) == 19
    assert sum(sc.CASES[n]["family"] == "d_mols" for n in settings) == 2
    for f in sc.SMALL:
        assert "yldot-" + f in sc.ALL
    for f in ("d_only", "d_c", "d_mols", "slab_phi"):
        assert sc.CASES["yldot-{}-it5".format(f)]["itermx"] == 5 and "yldot-{}-it5".format(f) in sc.ALL
    assert not set(sc.BY_NAME) & {sc.CASES[n].get("family") for n in sc.ALL}
    assert len(sc.ALL) == 41


def test_input_problems():
    """A record must show the SHA-256 of exactly the case's input.py, settings file and state."""
    family, settings = sc.family_files(sc.CASES["yldot-d_only-istewc3"])
    good = {"input.py": sc._sha256(os.path.join(family, "input.py")),
            "state": sc._sha256(os.path.realpath(os.path.join(family, sc.STATE))),
            "settings": sc._sha256(settings)}
    assert sc.input_problems({"inputs": good}, family, settings) == []
    skipped = {k: v for k, v in good.items() if k != "settings"}  # a worker that skipped the settings file
    assert sc.input_problems({"inputs": skipped}, family, settings) == ["settings not read"]
    assert sc.input_problems({"inputs": dict(good, settings="0" * 64)}, family, settings) == [
        "settings differs from the case's file"]
    assert sc.input_problems({"inputs": good}, family, None) == ["settings differs from the case's file"]
    assert sc.input_problems({}, family, None) == ["input.py not read", "state not read"]


# ---------------------------------------------------------------- build guard
def test_check_pair_kind_and_same():
    assert sc.check_pair("serial", build("a", False), build("b", False), False, False) == ([], [], [], False)
    errs, _, _, same = sc.check_pair("serial", build("a", False), build("a", False), False, False)
    assert same and len(errs) == 1 and "same build" in errs[0] and "same source tree" in errs[0]
    assert sc.check_pair("serial", build("a", False), build("a", False), False, True)[0] == []
    errs = sc.check_pair("omp0", build("a", True), build("b", False), True, False)[0]
    assert len(errs) == 1 and "new" in errs[0] and "OpenMP" in errs[0]
    errs = sc.check_pair("serial", build("a", True), build("b", False), False, False)[0]
    assert len(errs) == 1 and "base" in errs[0]


def test_check_pair_sources():
    # two trees at the same clean commit: the change is compared with itself
    errs, _, _, same = sc.check_pair("serial", build("a", False, src="/t1", head="c" * 40),
                                     build("b", False, src="/t2", head="c" * 40), False, False)
    assert same and "same clean commit" in errs[0]
    # same commit, new tree dirty: not an error, but not the gate (dirty tree)
    errs, warns, gate, same = sc.check_pair("serial", build("a", False, src="/t1", head="c" * 40),
                                            build("b", False, src="/t2", head="c" * 40, dirty=True), False, False)
    assert not errs and not same and any("uncommitted" in w for w in warns)
    assert any("uncommitted changes" in g for g in gate)
    # base not on origin/v9-develop, or the check failed: not the gate
    errs, _, gate, _ = sc.check_pair("serial", build("a", False, on_base=False), build("b", False), False, False)
    assert not errs and any("is not origin/v9-develop" in g for g in gate)
    gate = sc.check_pair("serial", build("a", False, on_base=None), build("b", False), False, False)[2]
    assert any("check failed" in g for g in gate)
    # unknown source: not the gate
    b = build("b", False)
    b["source"] = {"url": "file:///x/uedge.whl", "dir": None, "head": None}
    assert any("source unknown" in g for g in sc.check_pair("serial", build("a", False), b, False, False)[2])


def test_stale_build():
    b = build("b", False)
    b["source"]["head_time"], b["extensions_mtime"] = 2000, 1000.0  # committed after it was built
    assert sc.is_stale(b)
    gate = sc.check_pair("serial", build("a", False), b, False, False)[2]
    assert any("committed after the build" in g for g in gate)
    b["extensions_mtime"] = 3000.0
    assert not sc.is_stale(b) and sc.check_pair("serial", build("a", False), b, False, False)[2] == []


def test_iteration_problems():
    m = csr([[1.0, None], [None, 2.0]])
    a = FakeRecord("a", m, [1.0, 2.0], iters=(("0", "1.0"), ("1", "0.5")))
    b = FakeRecord("b", m, [1.0, 2.0], iters=(("0", "1.0"), ("1", "0.5")))
    for rec in (a, b):
        rec.meta["post_exmain_from"] = "psetnk"
    assert sc.iteration_problems("repro-tebox-it5", a, b) == []
    b.meta["iterations"] = b.meta["iterations"][:1]
    assert len(sc.iteration_problems("repro-tebox-it5", a, b)) == 1
    a.meta["post_exmain_from"] = "sfsetnk"
    assert len(sc.iteration_problems("repro-tebox-it5", a, b)) == 2
    assert sc.iteration_problems("repro-tebox", a, b) == []  # evaluation cases are not checked


def test_source_info_reads_git(tmp_path):
    import subprocess

    repo = tmp_path / "src"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "f.m").write_text("x\n")
    subprocess.run(["git", "-C", str(repo), "add", "f.m"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c"],
                   check=True)
    info = sc.source_info({"direct_url": {"url": "file://" + str(repo), "dir_info": {}}})
    assert info["dir"] == os.path.realpath(str(repo)) and len(info["head"]) == 40 and info["dirty"] is False
    (repo / "f.m").write_text("y\n")
    assert sc.source_info({"direct_url": {"url": "file://" + str(repo)}})["dirty"] is True
    assert sc.source_info({"direct_url": None})["head"] is None


# ---------------------------------------------------------------- comparison
def captured(rec, n):
    """Give a FakeRecord n raw captured Jacobians equal to its post-exmain one."""
    rec.meta["capture"] = {"hook": True, "count": n}
    for k in range(n):
        rec.arrays["capjac_{}".format(k)] = rec.arrays["jac_post"]
        rec.arrays["capjacj_{}".format(k)] = rec.arrays["jacj_post"]
        rec.arrays["capjaci_{}".format(k)] = rec.arrays["jaci_post"]
    return rec


def test_compare_pair_captures():
    m = csr([[1.0, None], [None, 2.0]])
    new = captured(FakeRecord("b", m, [1.0, 2.0]), 2)
    rep, status = sc.compare_pair("case", FakeRecord("a", m, [1.0, 2.0]), new)
    assert status == "ERROR"  # hook in one build only: serial_check runs such a pair with capture=0
    rep, status = sc.compare_pair("case", captured(FakeRecord("a", m, [1.0, 2.0]), 2), new)
    assert status == "AGREE" and "jacobian:captured[1]" in rep["sections"] and rep["captured_compared"] == 2
    rep, status = sc.compare_pair("case", captured(FakeRecord("a", m, [1.0, 2.0]), 1), new)
    assert status == "MISMATCH" and "jacobian_count" in rep["sections"]  # a different number of Jacobians


def test_compare_pair_checks_serial_path():
    m = csr([[1.0, None], [None, 2.0]])
    bad = FakeRecord("b", m, [1.0, 2.0])
    bad.meta["provenance"]["OMPParallelJac"] = 1
    rep, status = sc.compare_pair("case", FakeRecord("a", m, [1.0, 2.0]), bad)
    assert status == "ERROR" and any("OMPParallelJac" in e for e in rep["errors"])
    bad = FakeRecord("b", m, [1.0, 2.0])
    bad.meta["provenance"]["OMP_NUM_THREADS"] = "4"
    assert sc.compare_pair("case", FakeRecord("a", m, [1.0, 2.0]), bad)[1] == "ERROR"


def test_error_cause(tmp_path):
    (tmp_path / "run.log").write_bytes(b" iter= 0\x00\n *** Error: Jacobian row = 0 for eqn iv = 1092\n")
    msg = "run in X failed:\nTraceback (most recent call last):\n  File x\nRuntimeError\n"
    cause = sc.error_cause(msg, str(tmp_path))
    assert cause.startswith("RuntimeError") and "Jacobian row = 0" in cause


def test_first_mismatch_names_entry():
    m = csr([[1.0, None], [None, 2.0]])
    m2 = csr([[1.0, None], [None, 2.5]])
    rep, _ = sc.compare_pair("case", FakeRecord("a", m, [1.0, 2.0]), FakeRecord("b", m2, [1.0, 2.0]))
    line = sc.first_mismatch(rep)
    assert line.startswith("jacobian:post_exmain (1 entries): first value at row te(ix=0,iy=0)")
    assert "base 2.0 new 2.5" in line
    rep, _ = sc.compare_pair("case", FakeRecord("a", m, [1.0, 2.0]), FakeRecord("b", m, [1.0, -2.0]))
    assert sc.first_mismatch(rep).startswith("yldot (1 entries): first at te(ix=0,iy=0) (iv 2)")
    rep, status = sc.compare_pair("case", FakeRecord("a", m, [-0.0, 2.0]), FakeRecord("b", m, [0.0, 2.0]))
    assert status == "MISMATCH"  # serial vs serial: the signed zero counts
    assert sc.first_mismatch(sc.compare_pair("c", FakeRecord("a", m, [1.0, 2.0]),
                                             FakeRecord("b", m, [1.0, 2.0]))[0]) is None


# ---------------------------------------------------------------- the whole command, with fake runs
@pytest.fixture
def fake(monkeypatch):
    """serial_check with probe_build, source_info and run_case replaced: new differs in `diff_case`."""
    state = {"diff_case": None, "fail_case": None, "same": False, "crash": False}

    def probe(python, workdir):
        os.makedirs(workdir)
        role = "base" if "base" in python else "new"
        sha = "a" if (role == "base" or state["same"]) else "b"
        return build(sha + ("o" if "omp" in python else "s"), "omp" in python, python)

    def run(name, rundir, python, timeout, capture=0, identity=None):
        os.makedirs(rundir)
        if name == state["fail_case"] and "new" in python:
            raise HarnessError("run in {} failed:\nTraceback\nRuntimeError: boom".format(rundir))
        if name == state["fail_case"] and state["crash"]:
            raise ZeroDivisionError("unexpected")
        val = 2.5 if (name == state["diff_case"] and "new" in python) else 2.0
        rec = FakeRecord(name, csr([[1.0, None], [None, val]]), [1.0, 2.0])
        rec.rundir = rundir
        rec.meta["elapsed_s"] = 0.1
        if sc.CASES[name].get("itermx") and not state.get("no_iter"):
            rec.meta["iterations"] = [{"iter": 0, "fnrm_printed": "1.0"}, {"iter": 1, "fnrm_printed": "0.5"}]
            rec.meta["post_exmain_from"] = "psetnk"
        np.savez(os.path.join(rundir, "record.npz"), **rec.arrays)
        return rec

    monkeypatch.setattr(sc, "probe_build", probe)
    monkeypatch.setattr(sc, "source_info", lambda probe: probe["source"])
    monkeypatch.setattr(sc, "run_case", run)
    return state


def argv(tmp_path, *extra):
    return ["--base-python", "/base/python", "--new-python", "/new/python", "--base-omp-python",
            "/base-omp/python", "--new-omp-python", "/new-omp/python", "--out", str(tmp_path / "out")] + list(extra)


def test_main_complete_gate_agrees(tmp_path, fake, capsys):
    assert sc.main(argv(tmp_path)) == 0  # default --cases all
    res = json.load(open(tmp_path / "out" / "serial_check.json"))
    assert res["exit_code"] == 0 and res["gate_complete"] and set(res["results"]) == {"serial", "omp0"}
    assert set(res["results"]["serial"]) == set(sc.ALL)
    assert not os.path.exists(tmp_path / "out" / "serial" / "base" / "repro-tebox" / "record.npz")  # pruned
    out = capsys.readouterr().out
    assert "RESULT: AGREE (bitwise identical; complete gate)  [pairs serial+omp0, cases all" in out


def test_main_incomplete_is_not_the_gate(tmp_path, fake, capsys):
    assert sc.main(argv(tmp_path, "--cases", "quick")) == 2
    out = capsys.readouterr().out
    assert "RESULT: INCOMPLETE" in out and "NOT THE GATE" in out and "cases partial" in out
    assert sc.main(argv(tmp_path / "p", "--cases", "quick", "--partial-ok")) == 0
    assert "AGREE, PARTIAL" in capsys.readouterr().out
    one = ["--base-python", "/base/python", "--new-python", "/new/python", "--out", str(tmp_path / "one")]
    assert sc.main(one) == 2
    res = json.load(open(tmp_path / "one" / "serial_check.json"))
    assert res["skipped_pairs"] == ["omp0"] and "pair omp0 not checked" in res["incomplete"]
    fake["same"] = True
    assert sc.main(argv(tmp_path / "s", "--allow-same-build")) == 2
    res = json.load(open(tmp_path / "s" / "out" / "serial_check.json"))
    assert any("same build" in i for i in res["incomplete"])


def test_main_mismatch_names_case_and_entry(tmp_path, fake, capsys):
    fake["diff_case"] = "yldot-d_c"
    assert sc.main(argv(tmp_path, "--cases", "quick")) == 1  # a mismatch is a mismatch, complete or not
    text = open(tmp_path / "out" / "summary.txt").read()
    assert "[serial] yldot-d_c" in text and "MISMATCH" in text
    assert "first mismatch: jacobian:post_exmain (1 entries): first value at row" in text
    assert os.path.exists(tmp_path / "out" / "serial" / "base" / "yldot-d_c" / "record.npz")  # kept


def test_main_harness_errors(tmp_path, fake, capsys):
    fake["fail_case"] = "yldot-d_only"
    fake["diff_case"] = "yldot-d_c"
    assert sc.main(argv(tmp_path)) == 2  # an error wins over a mismatch
    text = open(tmp_path / "out" / "summary.txt").read()
    assert "ERROR    new: RuntimeError: boom" in text
    fake["fail_case"] = None
    fake["same"] = True
    assert sc.main(argv(tmp_path / "x")) == 2
    assert "same build" in capsys.readouterr().err
    assert sc.main(argv(tmp_path / "y", "--allow-same-build")) == 1  # yldot-d_c still differs
    assert sc.main(["--base-python", "/base/python", "--out", str(tmp_path / "z")]) == 2


def test_main_unexpected_exception_is_exit_2(tmp_path, fake, monkeypatch, capsys):
    fake["fail_case"] = "repro-te"
    fake["crash"] = True  # an unexpected exception inside a run
    assert sc.main(argv(tmp_path)) == 2
    assert "ZeroDivisionError" in open(tmp_path / "out" / "summary.txt").read()

    def boom(args):
        raise ValueError("bad npz")  # an unexpected exception outside the runs

    monkeypatch.setattr(sc, "serial_check", boom)
    assert sc.main(argv(tmp_path / "b")) == 2 and "unexpected" in capsys.readouterr().err


def test_main_wrong_build_kind(tmp_path, fake, capsys):
    bad = argv(tmp_path)
    bad[bad.index("/new-omp/python")] = "/new/python"  # a serial build in the OpenMP pair
    assert sc.main(bad) == 2 and "not an OpenMP build" in capsys.readouterr().err


# the reviewer's round-2 probes (scratchpad/rev53r2/fakes/test_guards.py): none of these may be the gate
@pytest.mark.parametrize("label,mutate,reason", [
    ("both sources unknown (wheel installs)",
     lambda r, b: b.update(source={"url": "file:///x/uedge.whl", "dir": None, "head": None}), "source unknown"),
    ("base not on v9-develop", lambda r, b: b["source"].update(on_base_ref=False) if r == "base" else None,
     "base not on origin/v9-develop"),
    ("base on_base_ref unknown", lambda r, b: b["source"].update(on_base_ref=None) if r == "base" else None,
     "base not on origin/v9-develop"),
    ("same head, new dirty", lambda r, b: b["source"].update(head="c" * 40, dirty=(r == "new")), "dirty tree"),
    ("same head, both dirty", lambda r, b: b["source"].update(head="c" * 40, dirty=True), "dirty tree"),
    ("new built before its HEAD", lambda r, b: (b["source"].update(head_time=2000), b.update(extensions_mtime=1000.0))
     if r == "new" else None, "build older than HEAD"),
])
def test_source_guard_states_are_not_the_gate(label, mutate, reason, monkeypatch, fake, tmp_path, capsys):
    probe = sc.probe_build

    def mutated(python, workdir):
        b = probe(python, workdir)
        mutate("base" if "base" in python else "new", b)
        return b

    monkeypatch.setattr(sc, "probe_build", mutated)
    assert sc.main(argv(tmp_path)) == 2, label
    res = json.load(open(tmp_path / "out" / "serial_check.json"))
    assert not res["gate_complete"] and res["incomplete"]
    line = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("RESULT")][0]
    assert line.startswith("RESULT: INCOMPLETE") and reason in line
    assert sc.main(argv(tmp_path / "p", "--partial-ok")) == 0
    line = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("RESULT")][0]
    assert "AGREE, PARTIAL" in line and reason in line


def test_main_case_that_did_not_iterate_is_error(tmp_path, fake, capsys):
    fake["no_iter"] = True
    assert sc.main(argv(tmp_path)) == 2
    text = open(tmp_path / "out" / "summary.txt").read()
    assert "repro-tebox-it5" in text and "did not iterate" in text
