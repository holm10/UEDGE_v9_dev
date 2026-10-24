"""pytest setup of the yldot suite (epic AIUE-9). The environment is pinned in tests/yldot/__init__.py, which pytest
imports before this file; the harness (yldot.harness) starts every evaluation in an isolated child process.

The release assets (the external files of every manifest: the reference files, the owner families' grids, inputs and
states) are fetched at the start of the session with tools/fetch_data.py's fetch: downloaded if absent, checked
against their SHA-256 and linked (decision 23, owner 2026-10-22, AIUE-156). Nothing is skipped: if the fetch is
impossible (offline, the release unreachable) or --yldot-no-fetch is given, a test that needs a family's absent
files under families/<family>/ fails at setup, naming the cause, unless it is marked toml_only (it reads family.toml
only); an absent reference file fails through open_store. Different files fail as before (test_smoke.py's
test_external_files, open_store).
"""
import re
import sys
from pathlib import Path

import pytest

from yldot.harness import FAMILIES, Runner
from yldot.harness import manifest as mf

SUITE = Path(__file__).resolve().parent
FAMILY_NAMES = sorted(p.name for p in FAMILIES.iterdir() if (p / "input.py").is_file())

sys.path.insert(0, str(SUITE / "tools"))

import fetch_data  # noqa: E402

FETCH_ERRORS = pytest.StashKey[list]()
FAMILY_ERROR = re.compile(r"^error: [A-Za-z0-9_]+: ")


def family_files(family):
    """The family's release assets from its manifest: {path relative to tests/yldot: entry}; {} without a manifest."""
    if not mf.path(family).is_file():
        return {}
    prefix = "families/{}/".format(family)
    return {p: e for p, e in mf.load(family)["external"].items() if p.startswith(prefix)}


def absent_files(family):
    """The family's release assets not present as files (a dangling link counts as absent)."""
    return [p for p in family_files(family) if not (SUITE / p).is_file()]


def pytest_addoption(parser):
    parser.addoption("--yldot-no-fetch", action="store_true",
                     help="yldot: never download release assets; tests that need absent ones fail")


def pytest_configure(config):
    config.addinivalue_line("markers", "toml_only: reads family.toml only, runs without the family's release assets")
    config.addinivalue_line("markers", "nightly: the nightly tier (PRD section 4), deselected in the PR tier with "
                                       "-m \"not nightly\"")


def pytest_sessionstart(session):
    """Fetch every manifest's release assets once, on the controller only (an xdist worker has workerinput)."""
    config = session.config
    if config.getoption("yldot_no_fetch"):
        config.stash[FETCH_ERRORS] = ["--yldot-no-fetch given"]
        return
    if config.option.collectonly or hasattr(config, "workerinput"):
        return
    lines = []
    try:
        fetch_data.fetch(SUITE, out=lines.append)
    except Exception as e:  # e.g. a PermissionError on .data/: the tests that need the files fail, the session runs
        lines.append("error: fetch failed: {!r}".format(e))
    report = config.pluginmanager.get_plugin("terminalreporter")
    for line in lines:
        if report is not None and ("downloaded" in line or line.startswith("error:")):
            report.write_line("yldot fetch: " + line)
    config.stash[FETCH_ERRORS] = [line for line in lines if line.startswith("error:")]


def pytest_collection_modifyitems(config, items):
    """Decision 15: this suite collects nothing outside tests/yldot (run it as `pytest tests/yldot`)."""
    outside = [item.nodeid for item in items if SUITE not in Path(str(item.path)).resolve().parents]
    if outside:
        raise pytest.UsageError("tests/yldot collected tests outside its directory (run `pytest tests/yldot`, "
                                "never `pytest tests/`): {}".format(outside[:5]))


def pytest_runtest_setup(item):
    """A test parametrised over a family whose release assets are absent fails here, except toml_only ones."""
    family = getattr(getattr(item, "callspec", None), "params", {}).get("family")
    if not isinstance(family, str) or item.get_closest_marker("toml_only"):
        return
    absent = absent_files(family)
    if absent:
        errors = item.config.stash.get(FETCH_ERRORS, None)
        if errors is None:
            cause = ["not fetched in this process (an xdist worker: the controller fetches; or --collect-only)"]
        else:  # this family's lines and those of no family (fetch's own lines are "error: <family>: ...")
            cause = [e for e in errors if e.startswith("error: {}: ".format(family)) or not FAMILY_ERROR.match(e)] \
                or ["the fetch reported no error for {}".format(family)]
        pytest.fail("{}: release assets not present: {} ({}); run python tests/yldot/tools/fetch_data.py {}".format(
            family, ", ".join(Path(p).name for p in absent), "; ".join(cause), family), pytrace=False)


def pytest_terminal_summary(terminalreporter, config):
    errors = [e for e in config.stash.get(FETCH_ERRORS, []) if e.startswith("error:")]
    if errors:
        terminalreporter.section("yldot release assets")
        for line in errors:
            terminalreporter.write_line(line)


@pytest.fixture(scope="session")
def runner():
    """The default start method: forkserver where available (YLDOT_START_METHOD overrides)."""
    return Runner()


@pytest.fixture(scope="session")
def runners():
    """Both start methods, for the forkserver-vs-spawn comparison."""
    return {"forkserver": Runner("forkserver"), "spawn": Runner("spawn")}
