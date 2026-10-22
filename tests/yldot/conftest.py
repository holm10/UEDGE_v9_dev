"""pytest setup of the yldot suite (epic AIUE-9). The environment is pinned in tests/yldot/__init__.py, which pytest
imports before this file; the harness (yldot.harness) starts every evaluation in an isolated child process.

A family whose release assets (the families/<family>/ files of its manifest's external table) are all absent skips
every test parametrised over it, naming them, unless the test is marked toml_only (it reads family.toml only). Partly
present or different files are never skipped: the evaluating tests and test_smoke.py's test_external_files fail on
them (owner, 2026-10-19)."""
from pathlib import Path

import pytest

from yldot.harness import FAMILIES, Runner
from yldot.harness import manifest as mf

SUITE = Path(__file__).resolve().parent
FAMILY_NAMES = sorted(p.name for p in FAMILIES.iterdir() if (p / "input.py").is_file())


def family_files(family):
    """The family's release assets from its manifest: {path relative to tests/yldot: entry}; {} without a manifest."""
    if not mf.path(family).is_file():
        return {}
    prefix = "families/{}/".format(family)
    return {p: e for p, e in mf.load(family)["external"].items() if p.startswith(prefix)}


def absent_files(family):
    """The family's release assets not present as files (a dangling link counts as absent)."""
    return [p for p in family_files(family) if not (SUITE / p).is_file()]


def pytest_configure(config):
    config.addinivalue_line("markers", "toml_only: reads family.toml only, runs without the family's release assets")


def pytest_collection_modifyitems(config, items):
    """Decision 15: this suite collects nothing outside tests/yldot (run it as `pytest tests/yldot`). A family whose
    release assets are all absent: skip its items, except toml_only ones."""
    outside = [item.nodeid for item in items if SUITE not in Path(str(item.path)).resolve().parents]
    if outside:
        raise pytest.UsageError("tests/yldot collected tests outside its directory (run `pytest tests/yldot`, "
                                "never `pytest tests/`): {}".format(outside[:5]))
    skips = {}
    for item in items:
        family = getattr(getattr(item, "callspec", None), "params", {}).get("family")
        if not isinstance(family, str) or item.get_closest_marker("toml_only"):
            continue
        if family not in skips:
            files, absent = family_files(family), absent_files(family)
            skips[family] = files and len(absent) == len(files) and pytest.mark.skip(
                reason="{}: release assets not present: {} (run tests/yldot/tools/fetch_data.py)".format(
                    family, ", ".join(Path(p).name for p in absent)))
        if skips[family]:
            item.add_marker(skips[family])


@pytest.fixture(scope="session")
def runner():
    """The default start method: forkserver where available (YLDOT_START_METHOD overrides)."""
    return Runner()


@pytest.fixture(scope="session")
def runners():
    """Both start methods, for the forkserver-vs-spawn comparison."""
    return {"forkserver": Runner("forkserver"), "spawn": Runner("spawn")}
