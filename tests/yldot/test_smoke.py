"""Smoke test of the yldot harness (AIUE-82): every family in both configurations and both flags, in forkserver and
spawn mode; .uedgerc.py isolation; classified failures; collection separation (decision 15). An owner family's
release assets, when present, are the files its manifest names (references/<family>.manifest.json); while they are
all absent, conftest.py skips the family's tests (tools/fetch_data.py fetches them).

Hooks for the failure tests are module-level functions here, passed as 'yldot.test_smoke:<name>' and imported by
the child. Planted .uedgerc.py files live only under tmp_path, never in ~, the repo or the real family directories.
"""
import os
import shutil
import signal
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import numpy as np
import pytest

from yldot.harness import CONFIGS, FAMILIES, FamilyError, load_evaluation
from yldot.harness import manifest as mf
from yldot.harness.store import file_sha256

SUITE = Path(__file__).resolve().parent
REPO = SUITE.parent.parent
FAMILY_NAMES = sorted(p.name for p in FAMILIES.iterdir() if (p / "input.py").is_file())
HOOKS = "yldot.test_smoke:"

UEDGERC = 'open({marker!r}, "w").write("executed")\nbbb.cfvisx = 0.5\n'
HELPER = '''import sys

import numpy as np


def main():
    sys.path.insert(0, sys.argv[1])
    from yldot.harness import Runner
    x = Runner().evaluate(sys.argv[2])
    if not x.ok:
        raise SystemExit("{}: {}".format(x.status, x.message))
    np.save(sys.argv[3], x.data["yldot"])


if __name__ == "__main__":
    main()
'''


def _pre_xerrab(bbb, com):
    # com.xerrab is Python-callable (com/com.v:684): the Fortran error path itself, independent of any physics
    # model (isimpon=3,4 also stop in xerrab, but they are disabled and slated for removal, owner 2026-10-19)
    com.xerrab("*** yldot smoke test: deliberate xerrab ***")


def _pre_sleep(bbb, com):
    time.sleep(60)


def _pre_kill(bbb, com):
    os.kill(os.getpid(), signal.SIGKILL)


def family_neq(family):
    with open(FAMILIES / family / "family.toml", "rb") as f:
        return tomllib.load(f)["family"]["neq"]


def first_difference(a, b):
    d = np.flatnonzero(a.view(np.uint64) != b.view(np.uint64))
    return "first differing row {} of {}: {!r} vs {!r}".format(d[0], d.size, a[d[0]], b[d[0]]) if d.size else ""


def describe(res):
    return "{} {} {}: {}: {}\n{}".format(res.family, res.config, res.mode, res.status, res.message, res.log_tail)


def copy_family(tmp_path, family="d_only"):
    """A copy of a family that still finds the shared rate files (relative ../../data paths in input.py)."""
    target = tmp_path / "families" / family
    shutil.copytree(FAMILIES / family, target)
    (tmp_path / "data").symlink_to(SUITE / "data", target_is_directory=True)
    return target


# ---------------------------------------------------------------- acceptance 1: both modes, bitwise


@pytest.mark.parametrize("family", [f for f in FAMILY_NAMES if mf.path(f).is_file()])
def test_external_files(family):
    """A family's files under families/<family>/ in its manifest's external table are present with the manifest's
    size and SHA-256. conftest.py fetches absent ones at the start of the session and fails this test at setup if any
    is still absent (AIUE-156); different fails here (owner, 2026-10-19)."""
    prefix = "families/{}/".format(family)
    files = {p: e for p, e in mf.load(family)["external"].items() if p.startswith(prefix)}
    missing = [p for p in files if not (SUITE / p).is_file()]
    assert not missing, "{}: release assets missing: {}".format(family, missing)
    differ = ["{} ({} bytes)".format(p, (SUITE / p).stat().st_size) for p, e in files.items()
              if (SUITE / p).stat().st_size != e["bytes"] or file_sha256(SUITE / p) != e["sha256"]]
    assert not differ, "{}: size or SHA-256 differs from {} for {}".format(family, mf.path(family).name, differ)


@pytest.mark.parametrize("config", CONFIGS)
@pytest.mark.parametrize("family", FAMILY_NAMES)
def test_modes_bitwise(runners, family, config):
    res = {mode: r.evaluate(family, config=config) for mode, r in runners.items()}
    for x in res.values():
        assert x.ok, describe(x)
    fs, sp = res["forkserver"].data, res["spawn"].data
    neq = family_neq(family)
    for key in ("yldot", "yldot_J"):
        for data in (fs, sp):
            assert data["neq"] == neq and data[key].shape == (neq,)
            assert np.isfinite(data[key]).all(), "{} {}: non-finite {}".format(family, config, key)
        assert fs[key].tobytes() == sp[key].tobytes(), "{} {} {}: forkserver != spawn, {}".format(
            family, config, key, first_difference(fs[key], sp[key]))
    for key in ("idxn", "idxu", "idxte", "idxti", "idxg", "idxtg", "idxphi", "igyl"):
        assert np.array_equal(fs[key], sp[key]), key
    if config == "timestep":
        assert fs["dtreal"] == load_evaluation(family)["dt_timestep_s"]
        assert (fs["yldot"] != fs["yldot_J"]).any(), (
            "{}: yldot == yldot_J in the timestep configuration, so add_timestep did not act under the -1 flag "
            "(bbb/pandf.m:735-741). Irregular: ask the epic owner (decision 23).".format(family))
    else:
        assert fs["dtreal"] == 1e20


@pytest.mark.parametrize("family", FAMILY_NAMES)
def test_timestep_state(runner, family):
    """Steps 6b and 6c took effect at the pandf calls: ylodt is the reference state's y_c (not the base state's yl),
    and the saved arrays hold reference_state.h5 as stored (read here with h5py, independently of UEDGE)."""
    import h5py
    x = runner.evaluate(family, config="timestep")
    assert x.ok, describe(x)
    ts = x.data["timestep_state"]
    assert ts["ylodt"].tobytes() == ts["y_c"].tobytes(), "{}: ylodt != y_c (step 6b)".format(family)
    assert (ts["ylodt"] != ts["yl"]).any(), "{}: ylodt == yl, the base state (step 6b)".format(family)
    with h5py.File(FAMILIES / family / "reference_state.h5", "r") as hf:
        for v, a in ts["saved"].items():
            assert np.array_equal(a, hf["bbb"][v][()]), "{}: {} != reference_state.h5 (step 6c)".format(family, v)


def test_diagnostics_do_not_change_result(runner):
    plain = runner.evaluate("d_only")
    diag = runner.evaluate("d_only", diagnostics=True)
    assert plain.ok and diag.ok, describe(plain if not plain.ok else diag)
    assert "diagnostics" not in plain.data
    assert plain.data["yldot"].tobytes() == diag.data["yldot"].tobytes()
    assert plain.data["yldot_J"].tobytes() == diag.data["yldot_J"].tobytes()
    names = diag.data["diagnostics"]
    assert {"resco", "resee", "fnix", "psor"} <= set(names), sorted(names)


# ---------------------------------------------------------------- acceptance 2: .uedgerc.py


@pytest.mark.parametrize("where", ["cwd", "home"])
def test_uedgerc_in_home_or_cwd_ignored(runner, tmp_path, where):
    home, cwd = tmp_path / "home", tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()
    marker = tmp_path / "uedgerc-executed"
    ((home if where == "home" else cwd) / ".uedgerc.py").write_text(UEDGERC.format(marker=str(marker)))
    env = dict(os.environ, HOME=str(home))

    # Control: a plain import in this environment does execute the planted file.
    subprocess.run([sys.executable, "-c", "import uedge"], cwd=cwd, env=env, check=True, capture_output=True)
    assert marker.exists(), "control failed: the planted .uedgerc.py is not executed by import uedge"
    marker.unlink()

    helper = tmp_path / "helper.py"
    helper.write_text(HELPER)
    out = tmp_path / "yldot.npy"
    proc = subprocess.run([sys.executable, str(helper), str(SUITE.parent), "d_only", str(out)], cwd=cwd, env=env,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not marker.exists(), "the harness executed a .uedgerc.py from {}".format(where)
    reference = runner.evaluate("d_only")
    assert reference.ok, describe(reference)
    assert np.load(out).tobytes() == reference.data["yldot"].tobytes()


def test_uedgerc_in_family_dir_fails(runner, tmp_path):
    family = copy_family(tmp_path)
    control = runner.evaluate(family)
    assert control.ok, describe(control)
    (family / ".uedgerc.py").write_text("bbb.cfvisx = 0.5\n")
    with pytest.raises(FamilyError, match=r"\.uedgerc\.py"):
        runner.evaluate(family)


def test_solver_assertion(runner, tmp_path):
    family = copy_family(tmp_path)
    with open(family / "input.py", "a") as f:
        f.write("\nbbb.ifixpsor = 1\n")
    with pytest.raises(FamilyError, match="ifixpsor=1"):
        runner.evaluate(family)


# ---------------------------------------------------------------- acceptance 3: classified failures


def test_xerrab_classified(runner):
    x = runner.evaluate("d_only", pre=HOOKS + "_pre_xerrab")
    assert x.status == "error", describe(x)
    assert "RuntimeError: *** yldot smoke test: deliberate xerrab ***" in x.message, describe(x)
    assert runner.evaluate("d_only").ok


def test_timeout_classified(runner):
    x = runner.evaluate("d_only", pre=HOOKS + "_pre_sleep", timeout=3)
    assert x.status == "timeout", describe(x)
    assert x.wall_s < 15
    assert runner.evaluate("d_only").ok


def test_crash_classified(runner):
    x = runner.evaluate("d_only", pre=HOOKS + "_pre_kill")
    assert x.status == "crash", describe(x)
    assert x.exitcode == -signal.SIGKILL
    assert runner.evaluate("d_only").ok


# ---------------------------------------------------------------- decision 15


def collected(path):
    proc = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", path],
                          cwd=REPO, capture_output=True, text=True)
    return [line for line in proc.stdout.splitlines() if "::" in line], proc


def test_collection_separation():
    ours, proc = collected("tests/yldot")
    assert ours, proc.stdout + proc.stderr
    assert not [n for n in ours if "deterministic_omp" in n]
    theirs, _ = collected("tests/deterministic_omp")  # collection errors there are not this suite's concern
    assert not [n for n in theirs if "yldot" in n]
