"""Unit tests of fetch_data.py's downloads (AIUE-156, decision 23): plain HTTPS first, gh release download as the
fallback, and fetch's default going through both. Pure Python: urllib's urlopen, shutil.which and the gh download are
replaced by fakes, so there is no network. fetch's verify, link and refuse paths are tested in test_store_unit.py.
"""
import hashlib
import inspect
import io
import sys
import urllib.error
from pathlib import Path

import pytest

from yldot.harness import manifest as mf

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))

import fetch_data  # noqa: E402

TAG = "yldot-data-v9"
FILES = {"families/fam/base_state.h5": b"base state bytes", "references/fam.h5": b"reference bytes"}
ASSETS = {mf.asset_name(p): b for p, b in FILES.items()}


class FakeURL:
    """A urlopen stand-in serving {url: bytes}; any other URL is a 404, an exception instance is raised."""

    def __init__(self, served):
        self.served, self.calls = served, []

    def __call__(self, url, timeout=None):
        self.calls.append((url, timeout))
        got = self.served.get(url)
        if isinstance(got, Exception):
            raise got
        if got is None:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return io.BytesIO(got)


def url(asset, repo=fetch_data.REPO):
    return "https://github.com/{}/releases/download/{}/{}".format(repo, TAG, asset)


def test_https_downloads_each_asset(monkeypatch, tmp_path):
    fake = FakeURL({url(a): b for a, b in ASSETS.items()})
    monkeypatch.setattr(fetch_data.urllib.request, "urlopen", fake)
    fetch_data.download_https(TAG, sorted(ASSETS), tmp_path)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == ASSETS
    assert fake.calls == [(url(a), fetch_data.TIMEOUT_S) for a in sorted(ASSETS)]


@pytest.mark.parametrize("error", ["404", "unreachable"])
def test_https_failure_raises_and_leaves_nothing(monkeypatch, tmp_path, error):
    served = {url("references--fam.h5"): ASSETS["references--fam.h5"]}
    if error == "unreachable":
        served[url("families--fam--base_state.h5")] = urllib.error.URLError("no route to host")
    monkeypatch.setattr(fetch_data.urllib.request, "urlopen", FakeURL(served))
    with pytest.raises(fetch_data.FetchError, match="404" if error == "404" else "no route to host"):
        fetch_data.download_https(TAG, sorted(ASSETS), tmp_path)
    assert not list(tmp_path.glob("*.part"))


def test_gh_is_the_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch_data.urllib.request, "urlopen", FakeURL({}))
    monkeypatch.setattr(fetch_data.shutil, "which", lambda name: "/usr/bin/gh")
    calls = []
    monkeypatch.setattr(fetch_data, "download", lambda *args: calls.append(args))
    fetch_data.download_any(TAG, ["a.h5"], tmp_path, "o/r")
    assert calls == [(TAG, ["a.h5"], tmp_path, "o/r")]

    def gh_fails(*args):
        raise fetch_data.FetchError("gh release download failed (1): release not found")

    monkeypatch.setattr(fetch_data, "download", gh_fails)
    with pytest.raises(fetch_data.FetchError, match="404.*; then gh release download failed"):
        fetch_data.download_any(TAG, ["a.h5"], tmp_path, "o/r")
    monkeypatch.setattr(fetch_data.shutil, "which", lambda name: None)
    with pytest.raises(fetch_data.FetchError, match="gh, the fallback, is not on PATH"):
        fetch_data.download_any(TAG, ["a.h5"], tmp_path, "o/r")


def test_https_success_never_calls_gh(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch_data.urllib.request, "urlopen", FakeURL({url("a.h5"): b"a"}))
    monkeypatch.setattr(fetch_data, "download", lambda *args: pytest.fail("gh called after HTTPS succeeded"))
    fetch_data.download_any(TAG, ["a.h5"], tmp_path)
    assert (tmp_path / "a.h5").read_bytes() == b"a"


def test_fetch_default_downloads_over_https(monkeypatch, tmp_path):
    assert inspect.signature(fetch_data.fetch).parameters["download"].default is fetch_data.download_any
    (tmp_path / "families" / "fam").mkdir(parents=True)
    (tmp_path / "references").mkdir()
    mf.dump({"schema": 1, "family": "fam", "store": "full", "release": TAG,
             "external": {p: {"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)} for p, b in FILES.items()}},
            mf.path("fam", tmp_path))
    monkeypatch.setattr(fetch_data.urllib.request, "urlopen", FakeURL({url(a): b for a, b in ASSETS.items()}))
    assert fetch_data.fetch(tmp_path, out=lambda s: None) == 0
    assert {p: (tmp_path / p).read_bytes() for p in FILES} == FILES
    assert all((tmp_path / p).is_symlink() for p in FILES)
