"""pytest setup of the yldot suite (epic AIUE-9). The environment is pinned in tests/yldot/__init__.py, which pytest
imports before this file; the harness (yldot.harness) starts every evaluation in an isolated child process."""
from pathlib import Path

import pytest

from yldot.harness import FAMILIES, Runner

SUITE = Path(__file__).resolve().parent
FAMILY_NAMES = sorted(p.name for p in FAMILIES.iterdir() if (p / "input.py").is_file())


def pytest_collection_modifyitems(config, items):
    """Decision 15: this suite collects nothing outside tests/yldot (run it as `pytest tests/yldot`)."""
    outside = [item.nodeid for item in items if SUITE not in Path(str(item.path)).resolve().parents]
    if outside:
        raise pytest.UsageError("tests/yldot collected tests outside its directory (run `pytest tests/yldot`, "
                                "never `pytest tests/`): {}".format(outside[:5]))


@pytest.fixture(scope="session")
def runner():
    """The default start method: forkserver where available (YLDOT_START_METHOD overrides)."""
    return Runner()


@pytest.fixture(scope="session")
def runners():
    """Both start methods, for the forkserver-vs-spawn comparison."""
    return {"forkserver": Runner("forkserver"), "spawn": Runner("spawn")}
