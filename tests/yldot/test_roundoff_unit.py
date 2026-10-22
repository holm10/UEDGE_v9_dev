"""Unit tests of tools/measure_roundoff.py analyze (AIUE-87): sigma, its source pair, rtol_eq, the floor report and
the exit codes (PRD sections 7.4 and 7.7), on synthetic collections. The index arrays come from test_compare_unit's
make_data (built the way bbb/convert.m builds them); no uedge import, analyze runs as a child process as it does
from the command line.
"""
import pickle
import subprocess
import sys
import tomllib
from pathlib import Path

import numpy as np
import pytest

from yldot.harness.compare import index_map
from yldot.test_compare_unit import SPEC, make_data

TOOL = Path(__file__).resolve().parent / "tools" / "measure_roundoff.py"
FAMILY = "fam"
REGIONS = """[regions]
guard = "ix in {0, nx+1} or iy in {0, ny+1}"
nx = 3
ny = 2
ix_inner_leg = [1, 1]
ix_core = [2, 2]
ix_outer_leg = [3, 3]
iy_closed = [1, 1]
iy_open = [2, 2]
source = { ixpt1 = 1, ixpt2 = 2, iysptrx = 1 }
cells = { guard = 14, core = 1, pf = 2, inner_leg = 1, sol = 1, outer_leg = 1 }
"""
SERIAL = ("mac-serial", "mac-noopt", "linux-serial", "mac-omp")


def base():
    data = make_data()
    neq = data["neq"]
    rng = np.random.default_rng(87)
    ref = rng.uniform(1.0, 2.0, neq) * rng.choice([-1.0, 1.0], neq)
    return data, ref


def write_run(root, label, config, run, data, yldot, yldot_j=None, status="ok", **extra):
    r = dict(data, yldot=yldot, yldot_J=yldot if yldot_j is None else yldot_j, status=status, exitcode=0,
             label=label, family=FAMILY, config=config, run=run,
             build={"commit": "0" * 40, "options": label, "compiler": "gfortran", "platform": "test"}, **extra)
    d = root / "collections" / label
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "{}.{}.{}.pkl".format(FAMILY, config, run), "wb") as f:
        pickle.dump(r, f)


def collections(root, data, ref, noise=None, linux=None, debug=None):
    """Two runs of every label and both configurations; noise / linux / debug: offsets added to ref."""
    neq = data["neq"]
    noise = np.full(neq, 1e-12) if noise is None else noise
    linux = np.zeros(neq) if linux is None else linux
    debug = np.zeros(neq) if debug is None else debug
    for config in ("steady", "timestep"):
        for run in ("1", "2"):
            write_run(root, "mac-serial", config, run, data, ref.copy())
            write_run(root, "mac-omp", config, run, data, ref.copy())
            write_run(root, "mac-noopt", config, run, data, ref + noise)
            write_run(root, "linux-serial", config, run, data, ref + linux)
            write_run(root, "mac-debug", config, run, data, ref + debug)
    fam = root / "families" / FAMILY
    fam.mkdir(parents=True, exist_ok=True)
    (fam / "input.py").write_text("")
    (fam / "family.toml").write_text(REGIONS)


def analyze(root, *extra):
    proc = subprocess.run([sys.executable, str(TOOL), "analyze", str(root / "collections"), "--families",
                           str(root / "families"), "--toml", str(root / "tolerances.toml"), *extra],
                          capture_output=True, text=True, timeout=120)
    return proc


def sigma_of(root, config="steady"):
    import h5py

    with h5py.File(root / "families" / FAMILY / "sigma.h5", "r") as f:
        return f[config]["sigma"][()], f[config]["source"][()], [p.decode() if isinstance(p, bytes) else p
                                                                for p in f.attrs["pairs"]]


def test_clean_measurement_writes_sigma_and_rtol(tmp_path):
    data, ref = base()
    neq = data["neq"]
    noise = np.abs(ref) * 3e-13
    linux = np.zeros(neq)
    linux[5] = 1e-9  # the largest spread of its equation, from mac_vs_linux
    debug = np.full(neq, 1.0)  # report only: must not reach sigma or rtol
    collections(tmp_path, data, ref, noise=noise, linux=linux, debug=debug)
    proc = analyze(tmp_path, "--write")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    sigma, source, pairs = sigma_of(tmp_path)
    expected = np.maximum(np.abs((ref + noise) - ref), np.abs((ref + linux) - ref))
    np.testing.assert_array_equal(sigma, expected)
    assert pairs[source[5]] == "mac_vs_linux"
    assert all(pairs[s] == "o0_vs_o3" for i, s in enumerate(source) if i != 5)
    assert "debug_vs_o3" not in pairs and "same_build:mac-debug" not in pairs
    t = tomllib.loads((tmp_path / "tolerances.toml").read_text())
    imap, want = index_map(data), {}
    for eq in set(imap.eq):
        rows = np.flatnonzero(imap.eq == eq)
        s = expected[rows].max() / np.abs(ref[rows]).max()
        want[eq] = max(100 * s, 1e-14)
    for eq, v in want.items():
        assert t["rtol"][eq] == pytest.approx(v, rel=1e-12)
    assert t["rule"]["k"] == 100.0 and t["pairs"]["debug_vs_o3"]["serial"] is False
    assert all(t["findings"]["same_build_zero"].values())


def test_rtol_floor(tmp_path):
    data, ref = base()
    collections(tmp_path, data, ref, noise=np.zeros(data["neq"]))  # every build identical: s = 0
    proc = analyze(tmp_path, "--write")
    assert proc.returncode == 3, proc.stdout + proc.stderr  # sigma = 0 everywhere: no floor, ToleranceEscalation
    assert "no floor" in proc.stdout
    t = tomllib.loads((tmp_path / "tolerances.toml").read_text())
    assert set(t["rtol"].values()) == {1e-14}
    assert all(src.startswith("floor") for src in t["rtol_source"].values())


def test_same_build_spread_is_a_defect(tmp_path):
    data, ref = base()
    collections(tmp_path, data, ref)
    other = ref.copy()
    other[0] += 1e-15
    write_run(tmp_path, "mac-serial", "steady", "2", data, other)
    proc = analyze(tmp_path)
    assert proc.returncode == 4, proc.stdout + proc.stderr
    assert "DEFECT: fam steady same_build:mac-serial: 1 entries differ" in proc.stderr


def test_zero_sigma_group_over_ten_percent_goes_to_the_owner(tmp_path):
    data, ref = base()
    noise = np.full(data["neq"], 1e-12)
    imap = index_map(data, SPEC)
    guard = imap.groups()[("ni", 1, "guard")]
    noise[guard[:3]] = 0.0  # 3 of 14 entries: 21 %
    collections(tmp_path, data, ref, noise=noise)
    proc = analyze(tmp_path)
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert "fam steady ni[1] guard: sigma = 0 in 3 of 14 entries" in proc.stderr
    assert "**> 10 %**" in proc.stdout


def test_failed_debug_run_is_a_finding_failed_serial_run_an_error(tmp_path):
    data, ref = base()
    collections(tmp_path, data, ref)
    write_run(tmp_path, "mac-debug", "steady", "1", {}, None, status="error",
              log_tail="At line 603 of file ../../bbb/pandf_plasma_energy.F")
    proc = analyze(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "mac-debug fam steady 1: error (exit 0): At line 603" in proc.stdout
    write_run(tmp_path, "mac-noopt", "steady", "1", {}, None, status="crash", log_tail="SIGSEGV")
    assert analyze(tmp_path).returncode == 2


def test_openmp_rows_are_report_only(tmp_path):
    data, ref = base()
    collections(tmp_path, data, ref)
    bad = ref + 1.0
    write_run(tmp_path, "mac-omp", "steady", "omp4", data, ref.copy(), ffun=bad, pandf=ref.copy(), nthreads=4,
              parallel_pandf1=1)
    write_run(tmp_path, "mac-omp", "timestep", "omp4", data, ref.copy(), ffun=ref[:2].copy(), pandf=ref.copy(),
              nthreads=4, parallel_pandf1=1)
    proc = analyze(tmp_path, "--write")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    sigma, _, _ = sigma_of(tmp_path)
    np.testing.assert_array_equal(sigma, np.abs((ref + 1e-12) - ref))  # the noopt noise only
    t = tomllib.loads((tmp_path / "tolerances.toml").read_text())
    assert t["openmp"]["fam.steady.n4"]["vs_pandf"]["rows"] == data["neq"]
    assert t["openmp"]["fam.timestep.n4"]["status"] == "corrupt"
    write_run(tmp_path, "mac-omp", "steady", "omp4", data, ref.copy(), ffun=ref.copy(), pandf=ref.copy(),
              nthreads=1, parallel_pandf1=1)
    proc = analyze(tmp_path)
    assert proc.returncode == 3 and "effective Nthreads = 1 for N = 4" in proc.stderr


def test_write_twice_gives_identical_bytes(tmp_path):
    data, ref = base()
    collections(tmp_path, data, ref, noise=np.abs(ref) * 1e-13)
    files = [tmp_path / "tolerances.toml", tmp_path / "families" / FAMILY / "sigma.h5"]
    assert analyze(tmp_path, "--write").returncode == 0
    first = [f.read_bytes() for f in files]
    assert analyze(tmp_path, "--write").returncode == 0
    assert [f.read_bytes() for f in files] == first


def test_index_arrays_that_differ_between_builds_go_to_the_owner(tmp_path):
    data, ref = base()
    collections(tmp_path, data, ref)
    other = dict(data, igyl=data["igyl"].copy())
    other["igyl"][0] = (9, 9)
    write_run(tmp_path, "linux-serial", "steady", "1", other, ref.copy())
    proc = analyze(tmp_path)
    assert proc.returncode == 3 and "the index arrays differ between linux-serial and mac-serial" in proc.stderr
