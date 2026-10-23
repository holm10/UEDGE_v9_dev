"""Unit tests of the harness that need no UEDGE build:  python -m pytest tests/deterministic_omp/harness"""
import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import cli  # noqa: E402
from harness.compare import (compare_records, describe_iv, matrix_mismatch, summarize_matrix,  # noqa: E402
                             vector_mismatch)
from harness.config import NEWTON_FTOL, NEWTON_STPTOL, PRESETS, RunSpec, apply_preset, force_newton  # noqa: E402
from harness.runner import HarnessError, parse_iterations, prepare_rundir  # noqa: E402


# ---------------------------------------------------------------- vectors
def test_vector_equal():
    a = np.array([1.0, -2.5, 0.0, 3e300])
    assert len(vector_mismatch(a, a.copy())) == 0


def test_vector_last_bit():
    a = np.array([1.0, 2.0])
    b = a.copy()
    b[1] = np.nextafter(2.0, 3.0)
    assert list(vector_mismatch(a, b)) == [1]


def test_signed_zero_differs_by_default():
    a = np.array([0.0, 1.0])
    b = np.array([-0.0, 1.0])
    assert list(vector_mismatch(a, b)) == [0]
    assert len(vector_mismatch(a, b, signed_zero_equal=True)) == 0


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_nonfinite_always_fails(bad):
    a = np.array([1.0, bad])
    assert list(vector_mismatch(a, a.copy())) == [1]
    assert list(vector_mismatch(a, a.copy(), signed_zero_equal=True)) == [1]


# ---------------------------------------------------------------- matrices
def csr(dense):
    """1-based CSR (values, cols, rowptr) of a dense matrix, keeping explicit zeros out."""
    vals, cols, ptr = [], [], [1]
    for row in dense:
        for j, v in enumerate(row):
            if v is not None:
                vals.append(v)
                cols.append(j + 1)
        ptr.append(len(vals) + 1)
    return np.array(vals, dtype=float), np.array(cols), np.array(ptr)


def test_matrix_equal():
    m = csr([[1.0, None], [2.0, 3.0]])
    mm = matrix_mismatch(m, m, 2)
    assert all(len(mm[k][0]) == 0 for k in ("value", "only_a", "only_b"))


def test_matrix_value_and_pattern():
    a = csr([[1.0, None], [2.0, 3.0]])
    b = csr([[1.0, 5.0], [2.0, -3.0]])
    mm = matrix_mismatch(a, b, 2)
    assert list(zip(*mm["value"])) == [(1, 1)]
    assert list(zip(*mm["only_b"])) == [(0, 1)]
    assert len(mm["only_a"][0]) == 0


def test_matrix_signed_zero_and_nan():
    a = csr([[0.0, np.nan]])
    b = csr([[-0.0, np.nan]])
    mm = matrix_mismatch(a, b, 2)
    assert sorted(zip(*mm["value"])) == [(0, 0), (0, 1)]
    assert mm["nonfinite_a"] == 1 and mm["nonfinite_b"] == 1


def test_matrix_same_values_permuted_storage():
    # same entries, different order within a row: still equal
    a = (np.array([1.0, 2.0]), np.array([1, 2]), np.array([1, 3]))
    b = (np.array([2.0, 1.0]), np.array([2, 1]), np.array([1, 3]))
    mm = matrix_mismatch(a, b, 2)
    assert all(len(mm[k][0]) == 0 for k in ("value", "only_a", "only_b"))


# ---------------------------------------------------------------- localisation
def test_describe_and_summarize():
    eq = np.array([2, 2, 0, 0])  # te, te, ni, ni
    species = np.array([-1, -1, 0, 1])
    igyl = np.array([[3, 18], [4, 18], [3, 18], [3, 18]])
    assert describe_iv(0, eq, species, igyl) == "te(ix=3,iy=18)"
    assert describe_iv(3, eq, species, igyl) == "ni[1](ix=3,iy=18)"
    a = csr([[1.0, None, None, None], [None, 1.0, None, None], [None, None, 1.0, None], [None, None, None, 1.0]])
    b = csr([[9.0, None, None, None], [None, 1.0, None, None], [None, None, 1.0, 4.0], [None, None, None, 1.0]])
    s = summarize_matrix(matrix_mismatch(a, b, 4), eq, species, igyl)
    assert s["mismatches"] == 2
    assert s["by_equation_pair"]["te/te"]["value"] == 1
    assert s["by_equation_pair"]["ni/ni"]["only_b"] == 1
    assert s["first"][0]["row"] == "te(ix=3,iy=18)" and s["first"][0]["b"] == "9.0"


# ---------------------------------------------------------------- records
def provenance(arm="serial", threads=1, **over):
    omp = arm != "serial"
    prov = {"OMPParallelJac": int(omp), "OMPParallelPandf1": int(arm == "jacrhs"), "ParallelJac": int(omp),
            "ParallelPandf1": int(arm == "jacrhs"), "Nthreads": threads, "OMP_NUM_THREADS": str(threads),
            "CheckJac": 0, "CheckPandf1": 0, "ForceSerialCheck": 0, "openmp_build": True}
    prov.update(over)
    return prov


class FakeRecord:
    def __init__(self, label, jac, yldot, fnrm="0x1p+0", iters=(("0", "1.0"),), parallel=False, arm=None,
                 threads=None):
        vals, cols, ptr = jac
        n = len(ptr) - 1
        arm = arm or ("jacrhs" if parallel else "serial")
        threads = threads or (4 if arm != "serial" else 1)
        self.label = label
        self.meta = {"neq": n, "fnrm_final_hex": fnrm, "rhs_probe_parallel": parallel,
                     "spec": {"preset": "tebox", "arm": arm, "threads": threads, "itermx": None},
                     "provenance": provenance(arm, threads),
                     "iterations": [{"iter": int(i), "fnrm_printed": f} for i, f in iters]}
        self.arrays = {"jac_post": vals, "jacj_post": cols, "jaci_post": ptr, "yldot": np.array(yldot, float),
                       "sfscal": np.ones(n), "suscal": np.ones(n), "yldot_probe": np.array(yldot, float),
                       "eq": np.full(n, 2), "species": np.full(n, -1), "igyl": np.zeros((n, 2), int)}


def test_compare_records_agree_and_fnrm():
    m = csr([[1.0, None], [None, 2.0]])
    assert compare_records(FakeRecord("a", m, [0.0, 1.0]), FakeRecord("b", m, [0.0, 1.0]))["agree"]
    r = compare_records(FakeRecord("a", m, [0.0, 1.0]), FakeRecord("b", m, [0.0, 1.0], iters=(("0", "1.1"),)))
    assert not r["agree"] and r["sections"]["fnrm_printed"]["mismatches"] == 1


def test_compare_records_rhs_signed_zero_auto():
    m = csr([[1.0, None], [None, 2.0]])
    a = FakeRecord("a", m, [-0.0, 1.0])
    b = FakeRecord("b", m, [0.0, 1.0], parallel=True)
    r = compare_records(a, b)
    # a parallel RHS produced b's yldot and probe: +-0 equal in both, counted separately
    for vec in ("yldot", "yldot_probe"):
        assert r["sections"][vec]["mismatches"] == 0 and r["sections"][vec]["signed_zero_equal"]
        assert r["sections"][vec]["signed_zero_differences"] == 1
    assert r["agree"]
    # serial vs serial: the sign of zero counts
    r = compare_records(FakeRecord("a", m, [-0.0, 1.0]), FakeRecord("b", m, [0.0, 1.0]))
    assert r["sections"]["yldot"]["mismatches"] == 1 and not r["agree"]
    # a real difference is never hidden by the rule
    r = compare_records(a, FakeRecord("b", m, [0.0, 1.5], parallel=True))
    assert r["sections"]["yldot"]["mismatches"] == 1


# ---------------------------------------------------------------- iterations, specs, errors
def test_parse_iterations_takes_callers_block():
    log = (" iter=   0 fnrm=      271985200.1005400     nfe=      1\n junk\n"
           " iter=   0 fnrm=      1.918820629111277     nfe=      1\n"
           " OMP iter=   1 fnrm=      1.836097068513709     nfe=     62\n")
    its = parse_iterations(log)
    assert [(i["iter"], i["fnrm_printed"], i["omp"]) for i in its] == [
        (0, "1.918820629111277", False), (1, "1.836097068513709", True)]


def test_parse_iterations_needs_two_blocks():
    with pytest.raises(HarnessError):
        parse_iterations(" iter=   0 fnrm=      1.0     nfe=      1\n")


def test_spec_validation_and_label():
    s = RunSpec(preset="tebox", arm="jac", threads=4).validate()
    assert s.label() == "tebox_jac_t4_it0"
    assert RunSpec.from_json(s.to_json()) == s
    with pytest.raises(ValueError):
        RunSpec(preset="nope").validate()
    with pytest.raises(ValueError):
        RunSpec(arm="serial", threads=4).validate()


def test_apply_preset_tebox():
    class Bbb:
        # Forthon packages broadcast a scalar assigned to an array variable
        def __setattr__(self, name, value):
            current = self.__dict__.get(name)
            if isinstance(current, np.ndarray) and np.isscalar(value):
                current[...] = value
            else:
                self.__dict__[name] = value

    bbb = Bbb()
    for eq in ["isnion", "isupon", "isteon", "istion", "isngon", "isphion"]:
        setattr(bbb, eq, 1)
    bbb.isteoffxy = np.zeros((10, 30), int)
    apply_preset(bbb, "tebox")
    assert bbb.isteon == 1 and bbb.istion == 0 and bbb.isphiofft == 1
    assert bbb.isteoffxy.sum() == 10 * 30 - 25 and bbb.isteoffxy[3:8, 18:23].sum() == 0
    assert set(PRESETS) >= {"full", "tebox", "te", "ti", "ni", "up", "ng", "te_phi"}


def test_force_newton_sets_itermx_and_both_tolerances():
    class Bbb:
        itermx, ftol, stptol = 30, 1e-8, 3.67e-11  # the deck's values after an exmain

    bbb = Bbb()
    force_newton(bbb, 3)
    assert bbb.itermx == 3 and bbb.ftol == NEWTON_FTOL and bbb.stptol == NEWTON_STPTOL
    # positive (0 selects nksol's defaults) and far below the fnrm and step noise floor
    assert 0 < NEWTON_FTOL < 1e-15 and 0 < NEWTON_STPTOL < 1e-15


def test_missing_case_file_is_harness_error(tmp_path, monkeypatch):
    from harness import runner

    monkeypatch.setattr(runner, "CASE_DIR", str(tmp_path / "nocase"))
    with pytest.raises(HarnessError):
        prepare_rundir(str(tmp_path / "run"))


def test_cli_exit_code_2_on_harness_error(tmp_path, monkeypatch, capsys):
    from harness import runner

    monkeypatch.setattr(runner, "CASE_DIR", str(tmp_path / "nocase"))
    code = cli.main(["run", "--preset", "tebox", "--arm", "serial", "--out", str(tmp_path / "run")])
    assert code == 2 and "HARNESS ERROR" in capsys.readouterr().err


def test_cli_compare_exit_codes(tmp_path):
    def write(d, yldot):
        os.makedirs(d)
        m = csr([[1.0, None], [None, 2.0]])
        rec = FakeRecord("x", m, yldot)
        np.savez(os.path.join(d, "record.npz"), **rec.arrays)
        with open(os.path.join(d, "record.json"), "w") as f:
            json.dump(rec.meta, f)

    write(str(tmp_path / "a"), [1.0, 2.0])
    write(str(tmp_path / "b"), [1.0, 2.0])
    write(str(tmp_path / "c"), [1.0, 2.5])
    assert cli.main(["compare", str(tmp_path / "a"), str(tmp_path / "b")]) == 0
    assert cli.main(["compare", str(tmp_path / "a"), str(tmp_path / "c")]) == 1
    assert cli.main(["compare", str(tmp_path / "a"), str(tmp_path / "missing")]) == 2


def test_captured_jacobians_compared_and_truncation_is_error():
    m = csr([[1.0, None], [None, 2.0]])
    m2 = csr([[1.0, None], [None, 2.5]])
    a = FakeRecord("a", m, [0.0, 1.0])
    b = FakeRecord("b", m, [0.0, 1.0])
    for rec, cap in ((a, m), (b, m2)):
        rec.meta["capture"] = {"hook": True, "count": 1, "slots": 1}
        rec.arrays.update({"capjac_0": cap[0], "capjacj_0": cap[1], "capjaci_0": cap[2]})
    r = compare_records(a, b)
    assert r["sections"]["jacobian:captured[0]"]["value"] == 1 and r["sections"]["jacobian:post_exmain"]["mismatches"] == 0
    b.arrays["capjac_0"] = m[0]
    assert compare_records(a, b)["agree"]
    b.meta["capture"]["truncated"] = True
    r = compare_records(a, b)
    assert not r["agree"] and any("capture slots" in e for e in r["errors"])


# ---------------------------------------------------------------- review round 1 (I1-B1, M1-M4, m3)
M = None


def _m():
    return csr([[1.0, None], [None, 2.0]])


def test_arm_that_did_not_run_is_an_error():
    a = FakeRecord("serial", _m(), [0.0, 1.0])
    b = FakeRecord("omp", _m(), [0.0, 1.0], arm="jac", threads=4)
    assert compare_records(a, b)["agree"]
    b.meta["provenance"]["ParallelJac"] = 0  # a serial build: the OpenMP switch had no effect
    r = compare_records(a, b)
    assert not r["agree"] and any("ParallelJac=0" in e for e in r["errors"])
    b.meta["provenance"].update(ParallelJac=1, Nthreads=1)  # clamped thread count
    assert any("Nthreads=1" in e for e in compare_records(a, b)["errors"])
    a.meta["provenance"]["OMPParallelJac"] = 1  # serial reference with a switch on
    assert any("serial arm" in e for e in compare_records(a, b)["errors"])


def test_jacrhs_needs_parallel_probe_and_diagnostics_off():
    a = FakeRecord("serial", _m(), [0.0, 1.0])
    b = FakeRecord("rhs", _m(), [0.0, 1.0], parallel=True)
    assert compare_records(a, b)["agree"]
    b.meta["rhs_probe_parallel"] = False
    assert any("parallel branch" in e for e in compare_records(a, b)["errors"])
    b.meta["rhs_probe_parallel"] = True
    b.meta["provenance"]["CheckJac"] = 1
    assert any("CheckJac" in e for e in compare_records(a, b)["errors"])


def test_captured_source_must_match_arm():
    a = FakeRecord("serial", _m(), [0.0, 1.0])
    b = FakeRecord("omp", _m(), [0.0, 1.0], arm="jac")
    for rec, src in ((a, "jac_calc"), (b, "jac_calc")):
        rec.meta["capture"] = {"hook": True, "count": 1, "slots": 4, "source": [src]}
        rec.arrays.update({"capjac_0": _m()[0], "capjacj_0": _m()[1], "capjaci_0": _m()[2]})
    assert any("captured Jacobians from" in e for e in compare_records(a, b)["errors"])


def test_duplicates_one_sided_and_missing_are_not_agree():
    a = FakeRecord("a", _m(), [0.0, 1.0])
    # duplicate (0,0) entry next to the matching one
    dup = (np.array([1.0, 7.0, 2.0]), np.array([1, 1, 2]), np.array([1, 3, 4]))
    r = compare_records(a, FakeRecord("b", dup, [0.0, 1.0]))
    assert not r["agree"] and r["sections"]["jacobian:post_exmain"]["duplicates"] == 1
    b = FakeRecord("b", _m(), [0.0, 1.0])
    del b.arrays["yldot_probe"]
    r = compare_records(a, b)
    assert not r["agree"] and r["sections"]["yldot_probe"]["mismatches"] == 1
    b = FakeRecord("b", _m(), [0.0, 1.0])
    del b.arrays["yldot"]
    assert compare_records(a, b)["errors"]
    b = FakeRecord("b", _m(), [0.0, 1.0])
    b.meta["iterations"] = []
    assert any("iterations" in e for e in compare_records(a, b)["errors"])
    b = FakeRecord("b", _m(), [0.0, 1.0])
    b.arrays["igyl"] = np.ones((2, 2), int)
    assert any("igyl" in e for e in compare_records(a, b)["errors"])
    b = FakeRecord("b", _m(), [0.0, 1.0])
    b.meta["spec"]["preset"] = "full"
    assert any("preset" in e for e in compare_records(a, b)["errors"])


def test_bad_column_index_is_an_error():
    a = FakeRecord("a", _m(), [0.0, 1.0])
    bad = (np.array([1.0, 2.0]), np.array([1, 3]), np.array([1, 2, 3]))  # column 3 > neq=2
    assert any("outside" in e for e in compare_records(a, FakeRecord("b", bad, [0.0, 1.0]))["errors"])


def test_permuted_post_exmain_is_compared_but_not_localised():
    a = FakeRecord("a", _m(), [0.0, 1.0])
    b = FakeRecord("b", csr([[1.5, None], [None, 2.0]]), [0.0, 1.0])
    for rec in (a, b):
        rec.meta["post_exmain_permuted"] = True
    r = compare_records(a, b)
    sec = r["sections"]["jacobian:post_exmain (permuted indices)"]
    assert sec["value"] == 1 and "permuted" in sec["note"] and not r["agree"]


def test_cli_exit_2_on_errors_unexpected_and_truncated(tmp_path, monkeypatch):
    def write(d, rec):
        os.makedirs(d)
        np.savez(os.path.join(d, "record.npz"), **rec.arrays)
        with open(os.path.join(d, "record.json"), "w") as f:
            json.dump(rec.meta, f)

    write(str(tmp_path / "a"), FakeRecord("a", _m(), [0.0, 1.0]))
    noomp = FakeRecord("b", _m(), [0.0, 1.0], arm="jac")
    noomp.meta["provenance"]["ParallelJac"] = 0
    write(str(tmp_path / "b"), noomp)
    assert cli.main(["compare", str(tmp_path / "a"), str(tmp_path / "b")]) == 2
    write(str(tmp_path / "c"), FakeRecord("c", _m(), [0.0, 1.0]))
    with open(str(tmp_path / "c" / "record.npz"), "r+b") as f:
        f.truncate(20)
    assert cli.main(["compare", str(tmp_path / "a"), str(tmp_path / "c")]) == 2
    from harness import compare as cmp

    def boom(*args, **kwargs):
        raise ZeroDivisionError("planted")

    monkeypatch.setattr(cli, "compare_records", boom)
    write(str(tmp_path / "d"), FakeRecord("d", _m(), [0.0, 1.0]))
    assert cli.main(["compare", str(tmp_path / "a"), str(tmp_path / "d")]) == 2
    assert cmp is not None


def test_spec_rejects_diagnostics_and_repeats_zero(tmp_path):
    with pytest.raises(ValueError):
        RunSpec(arm="jac", threads=4, ppp={"CheckJac": 1}).validate()
    with pytest.raises(ValueError):
        RunSpec(arm="jac", threads=4, ppp={"Nthreads": 8}).validate()
    assert cli.main(["check", "--preset", "tebox", "--arm", "jac", "--repeats", "0",
                     "--out", str(tmp_path / "x")]) == 2


# ---------------------------------------------------------------- review round 2 (I2-m1..m3)
def test_exit_code_of_nothing_is_an_error():
    assert cli.exit_code([]) == 2


def test_inconsistent_csr_is_an_error():
    a = FakeRecord("a", _m(), [0.0, 1.0])
    bad = (np.array([1.0]), np.array([1]), np.array([1, 2, 3]))  # rowptr says 2 entries, 1 value given
    assert any("inconsistent CSR" in e for e in compare_records(a, FakeRecord("b", bad, [0.0, 1.0]))["errors"])


def test_permuted_section_has_no_cell_coordinates():
    a = FakeRecord("a", _m(), [0.0, 1.0])
    b = FakeRecord("b", csr([[1.5, None], [None, 2.0]]), [0.0, 1.0])
    for rec in (a, b):
        rec.meta["post_exmain_permuted"] = True
    sec = compare_records(a, b)["sections"]["jacobian:post_exmain (permuted indices)"]
    assert sec["first"][0]["row"] == "position 1" and "ix=" not in sec["first"][0]["col"]
