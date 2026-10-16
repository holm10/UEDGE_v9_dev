"""Unit tests for ci/common_check.py (no UEDGE build needed; `nm` is faked)."""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common_check  # noqa: E402

INIT = """import ctypes
from .uedgeC import *
from .compy import com
from .grdpy import grd
from .bbbpy import bbb
from .apipy import api
from .ppppy import ppp
"""
MODS = ["uedgeC", "compy", "grdpy", "bbbpy", "apipy", "ppppy"]


def _gen(path, pkg, names_kinds):
    """A generated <pkg>_p.F90 with a common statement over two lines (`&` continuation)."""
    decl = "\n".join("  {}(kind={})::{}".format("real" if k == 8 else "integer", k, n) for n, k in names_kinds)
    names = [n for n, _ in names_kinds]
    half = max(1, len(names) // 2)
    common = "common /ompcommonscalarcopy/ " + ",".join(names[:half])
    if names[half:]:
        common += ",&\n" + ",".join(names[half:])
    with open(os.path.join(path, pkg + "_p.F90"), "w") as f:
        f.write("subroutine OmpCopyScalar{}\n{}\n{}\nend\n".format(pkg, decl, common))


def _setup(tmp_path, definers, sizes):
    pkgdir = tmp_path / "uedge"
    gen = tmp_path / "gen"
    pkgdir.mkdir()
    gen.mkdir()
    (pkgdir / "__init__.py").write_text(INIT)
    for m in MODS:
        (pkgdir / (m + ".cpython-311-x86_64-linux-gnu.so")).write_text("")
    for pkg, n in sizes.items():
        _gen(str(gen), pkg, [("v{}_{}".format(pkg, i), 8) for i in range(n)])
    return str(pkgdir), str(gen), set(definers)


def _fake_nm(definers, platform, fail=None):
    def run(cmd, capture_output=True, text=True):
        so = os.path.basename(cmd[-1])
        mod = so.split(".")[0]
        if fail == mod:
            return subprocess.CompletedProcess(cmd, 1, "", "nm: boom")
        lines = ["                 U PyFloat_Type"] if platform != "darwin" else ["(undefined) external _PyFloat_Type"]
        if mod in definers:
            if platform == "darwin":
                lines.append("0000000000001000 (__DATA,__common) external _ompcommonscalarcopy_")
            else:
                lines.append("0000000000123456 00000000000002d8 B ompcommonscalarcopy_")
        elif platform == "darwin":
            lines.append("                 (undefined) external _ompcommonscalarcopy_")
        else:
            lines.append("                 U ompcommonscalarcopy_")
        return subprocess.CompletedProcess(cmd, 0, "\n".join(lines) + "\n", "")
    return run


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_pass_bbb_first_and_largest(tmp_path, monkeypatch, capsys, platform):
    pkgdir, gen, definers = _setup(tmp_path, ["bbbpy", "apipy"], {"bbb": 91, "api": 12})
    monkeypatch.setattr(common_check.sys, "platform", platform)
    monkeypatch.setattr(common_check.subprocess, "run", _fake_nm(definers, platform))
    assert common_check.main(["--pkgdir", pkgdir, "--gen", gen]) == 0
    out = capsys.readouterr().out
    assert "RESULT: PASS (first definer bbbpy 728 B; others apipy 96 B)" in out


def test_fail_first_definer_not_bbb(tmp_path, monkeypatch, capsys):
    pkgdir, gen, definers = _setup(tmp_path, ["compy", "bbbpy"], {"com": 10, "bbb": 91})
    monkeypatch.setattr(common_check.sys, "platform", "linux")
    monkeypatch.setattr(common_check.subprocess, "run", _fake_nm(definers, "linux"))
    assert common_check.main(["--pkgdir", pkgdir, "--gen", gen]) == 1
    assert "first definer is compy (80 B), not bbbpy" in capsys.readouterr().out


def test_fail_later_block_larger(tmp_path, monkeypatch, capsys):
    pkgdir, gen, definers = _setup(tmp_path, ["bbbpy", "apipy"], {"bbb": 5, "api": 12})
    monkeypatch.setattr(common_check.sys, "platform", "linux")
    monkeypatch.setattr(common_check.subprocess, "run", _fake_nm(definers, "linux"))
    assert common_check.main(["--pkgdir", pkgdir, "--gen", gen]) == 1
    assert "apipy block 96 B > first definer bbbpy 40 B" in capsys.readouterr().out


def test_error_nm_fails(tmp_path, monkeypatch):
    pkgdir, gen, definers = _setup(tmp_path, ["bbbpy"], {"bbb": 91})
    monkeypatch.setattr(common_check.sys, "platform", "linux")
    monkeypatch.setattr(common_check.subprocess, "run", _fake_nm(definers, "linux", fail="grdpy"))
    assert common_check.main(["--pkgdir", pkgdir, "--gen", gen]) == 2


def test_error_no_definer(tmp_path, monkeypatch, capsys):
    pkgdir, gen, _ = _setup(tmp_path, [], {"bbb": 91})
    monkeypatch.setattr(common_check.sys, "platform", "linux")
    monkeypatch.setattr(common_check.subprocess, "run", _fake_nm(set(), "linux"))
    assert common_check.main(["--pkgdir", pkgdir, "--gen", gen]) == 2
    assert "RESULT: ERROR (no package defines the block" in capsys.readouterr().out


def test_error_size_unknown(tmp_path, monkeypatch):
    pkgdir, gen, definers = _setup(tmp_path, ["bbbpy", "apipy"], {"bbb": 91})  # no api_p.F90
    monkeypatch.setattr(common_check.sys, "platform", "linux")
    monkeypatch.setattr(common_check.subprocess, "run", _fake_nm(definers, "linux"))
    assert common_check.main(["--pkgdir", pkgdir, "--gen", gen]) == 2


def test_error_bad_inputs(tmp_path):
    assert common_check.main(["--pkgdir", str(tmp_path / "nope"), "--gen", str(tmp_path)]) == 2
    pkgdir = tmp_path / "uedge"
    pkgdir.mkdir()
    (pkgdir / "__init__.py").write_text(INIT)
    assert common_check.main(["--pkgdir", str(pkgdir), "--gen", str(tmp_path / "nogen")]) == 2


def test_import_order_and_elf_regex():
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(INIT)
    assert common_check.import_order(f.name) == MODS
    os.unlink(f.name)
