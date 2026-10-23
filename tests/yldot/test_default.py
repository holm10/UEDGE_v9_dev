"""The default tests of the yldot suite (AIUE-89; PRD sections 6, 7.3, 7.4 and story 1; decision 27): per family with a
reference file and per configuration, one fresh evaluation compared entry by entry with the stored default, and its
Jacobian-flag difference yldot_J - yldot under the same per-entry tolerance, through Store.check.

open_store checks the reference file against its manifest at test time (the file's SHA-256, its datasets and the
manifest's derived fields) and every dataset read recomputes its SHA-256. An absent reference file fails with the
fetch command (owner, 2026-10-22; the policy for absent external data is AIUE-156). A failure starts with one line in
the story 1 format: family::default[config], the part (yldot or flag difference), the worst entry, its relative
difference and tolerance, and the first differing intermediate (array-scaled, as in Store.check's report).
"""
import tomllib
from pathlib import Path

import numpy as np
import pytest

from yldot.harness import CONFIGS, FAMILIES, compare, open_store
from yldot.harness import manifest as mf
from yldot.harness.compare import DIAG_SCALED_RTOL, first_difference, listed
from yldot.harness.store import differs

SUITE = Path(__file__).resolve().parent
FAMILY_NAMES = sorted(p.name for p in FAMILIES.iterdir() if (p / "input.py").is_file())
# the families whose manifest names a reference file: the five small ones (AIUE-88); the owner families join with
# their references (AIUE-92)
REFERENCED = [f for f in FAMILY_NAMES if mf.path(f).is_file() and mf.reference_path(f) in mf.load(f)["external"]]


@pytest.fixture(scope="module")
def tol():
    with open(SUITE / "tolerances.toml", "rb") as f:
        return tomllib.load(f)


def sigma_h5(family, config):
    import h5py

    with h5py.File(FAMILIES / family / "sigma.h5", "r") as f:
        return f[config]["sigma"][()]


def tolerance(s, config, tol, imap):
    """The per-entry tolerance of the stored default (PRD section 7.4)."""
    return compare.tolerances(s.default(config), s.sigma(config), tol["rtol"], tol["rule"]["k"], imap).tol


def headline(family, config, part, new, ref, t, imap, diag=None):
    """The story 1 line for the worst entry of one part; formatting only (Store.check decides)."""
    c = compare.compare(new, ref, t, imap, worst=1)
    if c.ok:
        return "{}::default[{}]: {} within tolerance".format(family, config, part)
    w = c.worst[0]
    if w["ref"] != 0:
        diff = "rel diff {:.2e} > tol {:.2e}".format(abs(w["diff"]) / abs(w["ref"]), w["tol"] / abs(w["ref"]))
    else:
        diff = "abs diff {:.2e} > tol {:.2e} (ref 0)".format(abs(w["diff"]), w["tol"])
    first = first_difference(*diag, rtol=DIAG_SCALED_RTOL, scaled=True) if diag is not None else "n/a"
    return "{}::default[{}]: {} {} {}; first differing intermediate: {}".format(
        family, config, part, w["label"], diff, first if first is not None else "none")


@pytest.mark.parametrize("config", CONFIGS)
@pytest.mark.parametrize("family", REFERENCED)
def test_default(tol, runner, family, config):
    """The live default against the stored one: yldot and the Jacobian-flag difference, entry by entry (decision 27)."""
    r = runner.evaluate(family, config=config, diagnostics=True)
    assert r.ok, (r.status, r.message, r.log_tail)
    with open_store(family) as s:
        bad = np.flatnonzero(differs(s.sigma(config), sigma_h5(family, config)))
        assert not bad.size, "{}: the reference's {} sigma differs from families/{}/sigma.h5 at rows {}".format(
            family, config, family, listed(bad + 1))
        imap = compare.index_map(r.data, compare.load_regions(family))
        t = tolerance(s, config, tol, imap)
        yldot, yldot_j = r.data["yldot"], r.data["yldot_J"]
        chk = s.check(config, None, yldot, yldot_j, t, imap, r.data["diagnostics"])
        if not chk.ok:
            ref = s.default(config)
            lines = [headline(family, config, "yldot", yldot, ref, t, imap,
                              s.diagnostic_pair(config, r.data["diagnostics"])),
                     headline(family, config, "flag difference", np.asarray(yldot_j) - np.asarray(yldot),
                              s.jflag(config), t, imap)]
            pytest.fail("\n".join(lines + [chk.report]), pytrace=False)


@pytest.mark.parametrize("family", REFERENCED)
def test_timestep_exercised(tol, family):
    """The stored timestep default is the steady one plus the time-step term, exactly: add_timestep acts under the -1
    flag only (bbb/pandf.m:735-742) and is the only difference between the configurations, so the timestep run's +1
    evaluation equals the steady default and timestep - steady is minus the stored timestep flag difference bit for
    bit (IEEE subtraction is antisymmetric, fl(a - b) = -fl(b - a)). The defaults then differ beyond tolerance exactly
    where that term exceeds tol_i. A time-step term below tol_i is possible where the base state's perturbation draw
    is near zero (owner, 2026-10-23, AIUE-92: dnull_imp2 ni[2] at (65,23), 1.9e-7 relative, 0.04 x tol_i)."""
    with open_store(family) as s:
        steady, timestep = s.default("steady"), s.default("timestep")
        t = tolerance(s, "steady", tol, s.imap)
        jflag = s.jflag("timestep")
        c = compare.compare(timestep, steady, t, s.imap)
        assert not c.ok, "{}: the timestep default is within tolerance of the steady one".format(family)
        off = np.flatnonzero((timestep - steady) != -jflag)
        assert not off.size, ("{}: timestep - steady is not minus the timestep flag difference at {} rows (first {}): "
                              "something besides add_timestep differs between the configurations".format(
                                  family, off.size, listed(off[:20] + 1)))
        where = np.flatnonzero(c.fail_mask)
        over = np.flatnonzero(np.abs(jflag) > t)
        per_block = ", ".join("{}[{}] {}".format(e, sp, n) for (e, sp), n in c.per_block.items() if n)
        assert np.array_equal(where, over), (
            "{}: timestep differs from steady at {} rows ({}), the time-step term exceeds tol_i at {}; rows only in "
            "the first {}, only in the second {}".format(
                family, where.size, per_block, over.size, listed(np.setdiff1d(where, over) + 1),
                listed(np.setdiff1d(over, where) + 1)))
