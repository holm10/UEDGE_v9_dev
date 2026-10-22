"""tolerances.toml and families/<f>/sigma.h5 (AIUE-87; PRD sections 7.4 and 7.7): every value cites its measurement,
the files agree with each other, and the tolerance rule has a floor for every entry of the live evaluation. The file
is written by tools/measure_roundoff.py analyze --write; nothing here re-measures.
"""
import hashlib
import tomllib
from pathlib import Path

import numpy as np
import pytest

from yldot.harness import CONFIGS, FAMILIES, compare

SUITE = Path(__file__).resolve().parent
SMALL = ("d_c", "d_mols", "d_only", "ortho", "slab_phi")  # measured by AIUE-87; the owner families are AIUE-92's


@pytest.fixture(scope="module")
def tol():
    with open(SUITE / "tolerances.toml", "rb") as f:
        return tomllib.load(f)


def serial_pairs(tol):
    return sorted((p for p, v in tol["pairs"].items() if v["serial"]), key=lambda p: tol["pairs"][p]["code"])


def sigma_file(tol, family):
    import h5py

    path = SUITE / tol["sigma"][family]["file"]
    out = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    with h5py.File(path, "r") as f:
        out["pairs"] = [p.decode() if isinstance(p, bytes) else str(p) for p in f.attrs["pairs"]]
        out["schema"] = int(f.attrs["schema"])
        for config in CONFIGS:
            out[config] = (f[config]["sigma"][()], f[config]["source"][()])
    return out


def test_rule(tol):
    r = tol["rule"]
    assert (r["k"], r["rtol_factor"], r["rtol_floor"], r["floor_limit"]) == (100.0, 100.0, 1e-14, 0.1)


def test_every_rtol_cites_its_measurement(tol):
    serial = set(serial_pairs(tol))
    for eq, value in tol["rtol"].items():
        s = [raw[eq]["s"] for f in tol["raw"].values() for c in f.values() for p, raw in c.items()
             if p in serial and eq in raw]
        assert s, eq
        assert value == max(tol["rule"]["rtol_factor"] * max(s), tol["rule"]["rtol_floor"]), eq
        # "<family> <config> <pair>", or "floor (largest s <s>, <family> <config> <pair>)"
        family, config, pair = tol["rtol_source"][eq].rstrip(")").split()[-3:]
        assert tol["raw"][family][config][pair][eq]["s"] == max(s), eq


def test_pairs_cite_builds(tol):
    for name, p in tol["pairs"].items():
        for side in (p["first"], p["second"]):
            label, _, run = side.partition(" run ")
            assert label in tol["builds"] and run in ("1", "2"), (name, side)
    assert set(serial_pairs(tol)) >= {"o0_vs_o3", "mac_vs_linux", "same_build:mac-serial", "same_build:linux-serial"}
    assert not tol["pairs"]["debug_vs_o3"]["serial"]
    assert [tol["pairs"][p]["code"] for p in serial_pairs(tol)] == list(range(len(serial_pairs(tol))))


def test_build_records(tol):
    for label, b in tol["builds"].items():
        for key in ("commit", "options", "compiler", "platform"):
            assert b.get(key), (label, key)
    linux = tol["builds"]["linux-serial"]
    assert linux["image"].startswith("ubuntu:24.04@sha256:") and linux["image_id"].startswith("sha256:")
    assert "13.3.0-6ubuntu2~24.04.1" in linux["compiler"]


def test_same_build_spread_is_zero(tol):
    assert tol["findings"]["same_build_zero"] and all(tol["findings"]["same_build_zero"].values())


def test_owner_answers_cover_the_items_raised(tol):
    """Decision 23: every item analyze sent to the owner is answered; a run that raises other items needs new answers."""
    assert tol["owner"]["items_raised"] == tol["owner"]["items_answered"]
    assert tol["owner"]["answers"]
    assert sum(n for f in tol["floor"]["over_limit"].values() for n in f.values()) <= tol["owner"]["items_raised"]


@pytest.mark.parametrize("family", SMALL)
def test_sigma_matches_the_raw_spreads(tol, family):
    """sigma.h5 against the raw spreads in tolerances.toml: per configuration, the largest sigma_i is the largest
    max_abs over the serial pairs, and every serial pair's max_abs is at most that."""
    s = sigma_file(tol, family)
    serial = set(serial_pairs(tol))
    for config in CONFIGS:
        raw = [r["max_abs"] for p, eqs in tol["raw"][family][config].items() if p in serial for r in eqs.values()]
        assert float(s[config][0].max()) == max(raw)


@pytest.mark.parametrize("family", SMALL)
def test_sigma_file(tol, family):
    entry = tol["sigma"][family]
    s = sigma_file(tol, family)
    assert s["sha256"] == entry["sha256"]
    assert s["schema"] == 1 and s["pairs"] == serial_pairs(tol)
    with open(FAMILIES / family / "family.toml", "rb") as f:
        neq = tomllib.load(f)["family"]["neq"]
    for config in CONFIGS:
        sigma, source = s[config]
        assert sigma.shape == source.shape == (neq,)
        assert np.isfinite(sigma).all() and (sigma >= 0).all()
        assert ((source == -1) == (sigma == 0)).all()
        assert source.max() < len(s["pairs"])
        assert entry[config] == {"entries": neq, "zero": int(np.count_nonzero(sigma == 0)), "max": float(sigma.max())}


@pytest.mark.parametrize("family", SMALL)
def test_every_entry_has_a_tolerance(tol, runner, family):
    """compare.tolerances on the live evaluation: no ToleranceEscalation, every tol_i > 0 and finite."""
    s = sigma_file(tol, family)
    regions = compare.load_regions(family)
    for config in CONFIGS:
        r = runner.evaluate(family, config=config)
        assert r.ok, (r.status, r.message, r.log_tail)
        imap = compare.index_map(r.data, regions)
        t = compare.tolerances(r.data["yldot"], s[config][0], tol["rtol"], tol["rule"]["k"], imap)
        assert np.isfinite(t.tol).all() and (t.tol > 0).all()
