"""Unit tests of the CI shards (tools/shards.py, conftest.py's --yldot-shard; AIUE-103): the shard list, the rule that
puts a test in its family's shard by its "family" parameter, and two real collections that must be disjoint, with
every test of a family shard carrying that family (a -k substring match would not: -k d_only also selects tests of
other shards). Pure Python apart from the collections (pytest --collect-only in a subprocess, no evaluation).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from yldot.harness import FAMILIES

SUITE = Path(__file__).resolve().parent
sys.path.insert(0, str(SUITE / "tools"))

import shards  # noqa: E402

TOOL = SUITE / "tools" / "shards.py"


def test_names():
    """One shard per family (conftest.py's FAMILY_NAMES rule), common first."""
    assert shards.families() == sorted(p.name for p in FAMILIES.iterdir() if (p / "input.py").is_file())
    assert shards.names() == ["common"] + shards.families()
    assert len(shards.families()) == len(set(shards.families())) >= 1


def test_shard_of():
    for family in shards.families():
        assert shards.shard_of({"family": family}) == family
        assert shards.shard_of({"family": family, "config": "steady"}, shards.families()) == family
    for params in ({}, {"family": "nonesuch"}, {"family": 3}, {"family": None}, {"x": "d_only"},
                   {"case": ("d_only", "steady")}):
        assert shards.shard_of(params) == shards.COMMON, params


def collect(name):
    """The PR tier's node ids in one shard."""
    proc = subprocess.run([sys.executable, "-m", "pytest", str(SUITE), "-m", "not nightly", "--collect-only", "-q",
                           "-p", "no:cacheprovider", "--yldot-shard", name], cwd=SUITE.parents[1],
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    return {line.strip() for line in proc.stdout.splitlines() if "::" in line}


def test_collection_partition():
    """d_only and common are disjoint and non-empty; every d_only test has d_only among its parameter ids; the
    synthetic threshold test is in the family's shard (PRD 4: in every shard)."""
    family, common = collect("d_only"), collect(shards.COMMON)
    assert family and common and not family & common, sorted(family & common)[:5]
    bad = [n for n in family if "[" not in n or "d_only" not in n[n.index("[") + 1:-1].split("-")]
    assert not bad, bad[:5]
    assert any("test_thresholds.py::test_full_comparator[d_only-" in n for n in family)
    assert not any("test_thresholds.py" in n for n in common)


def test_cli():
    proc = subprocess.run([sys.executable, "-I", str(TOOL)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0 and json.loads(proc.stdout) == shards.names(), proc.stdout + proc.stderr
    proc = subprocess.run([sys.executable, "-I", str(TOOL), "--check", shards.COMMON, "nonesuch"],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 2 and "nonesuch" in proc.stderr, proc.stdout + proc.stderr
    assert shards.main(["shards.py", "--check", *shards.names()]) == 0


@pytest.mark.parametrize("name", ["nonesuch", "Common"])
def test_unknown_shard_refused(name):
    proc = subprocess.run([sys.executable, "-m", "pytest", str(SUITE), "--collect-only", "-q", "-p",
                           "no:cacheprovider", "--yldot-shard", name], cwd=SUITE.parents[1], capture_output=True,
                          text=True, timeout=300)
    assert proc.returncode == 4 and "unknown shard" in proc.stdout + proc.stderr, proc.stdout[-1000:]
