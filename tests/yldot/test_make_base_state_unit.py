"""Unit tests of make_base_state.py's ratio rule and its --accept-ratio exceptions (tracker T22; owner, 2026-11-24).

A block meets the rule when RMS(yldot at base) is at least RATIO_MIN times RMS(at reference). Every block must, except
the ones named with --accept-ratio; each rule has a positive and a negative case. No build: the evaluations, the
round trip and the saved states are fakes around make_states.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))

import make_base_state as mb  # noqa: E402


def ratios(**kw):
    """[(label, rows, rms_ref, rms_base, ratio)] for {label: ratio}; a label's brackets are written as __."""
    return [(k.replace("__", "[").replace("_E", "]"), 60, 1.0, v, v) for k, v in kw.items()]


def test_every_block_meets_the_rule():
    assert mb.judge(ratios(idxn=10.0, idxtg__0_E=12.0), [])


def test_a_miss_is_refused():
    assert not mb.judge(ratios(idxn=10.0, idxtg__0_E=9.99), [])


def test_an_accepted_miss_is_taken():
    assert mb.judge(ratios(idxn=10.0, idxtg__0_E=1.02), ["idxtg[0]"])


def test_an_unnamed_miss_stays_refused():
    """Accepting one block accepts no other."""
    assert not mb.judge(ratios(idxn=9.99, idxtg__0_E=1.02), ["idxtg[0]"])
    assert not mb.judge(ratios(idxtg__0_E=1.02, idxtg__1_E=1.02), ["idxtg[0]"])


def test_a_needless_acceptance_is_refused():
    with pytest.raises(mb.Stop, match="idxtg\\[0\\]: meets the rule") as e:
        mb.judge(ratios(idxn=10.0, idxtg__0_E=10.0), ["idxtg[0]"])
    assert e.value.code == 2


def test_a_needless_acceptance_waits_for_a_taken_sigma():
    """At a sigma that some other block refuses, the acceptance is not judged yet: the next sigma may need it."""
    assert not mb.judge(ratios(idxn=5.0, idxtg__0_E=10.0), ["idxtg[0]"])


def test_unknown_block():
    mb.check_accepted(["idxn[0]", "idxtg[0]"], ["idxtg[0]"])
    with pytest.raises(mb.Stop, match="idxtg\\[2\\]: no such block") as e:
        mb.check_accepted(["idxn[0]", "idxtg[0]"], ["idxtg[0]", "idxtg[2]"])
    assert e.value.code == 2


# ---------------------------------------------------------------- make_states with fakes


class Fake:
    """The two block ratios per sigma, seen through make_states: block idxn[0] (rows 1-2) and idxtg[0] (rows 3-4)."""

    def __init__(self, monkeypatch, tmp_path, by_sigma):
        self.dir = tmp_path

        def run_child(family_dir, job, log):
            name = Path(job["state"]).name
            if name == "reference_state.h5":
                return {"yldot": np.ones(4), "neq": 4}
            n, t = by_sigma[self.sigma]
            return dict(yldot=np.array([n, n, t, t], float), neq=4)

        def perturb(ref, sigma, seed):
            self.sigma = sigma
            return {"nis": np.zeros(1)}

        patch = lambda name, f: monkeypatch.setattr(mb, name, f)  # noqa: E731
        patch("run_child", run_child)
        patch("blocks", lambda res: [("idxn[0]", np.array([0, 1])), ("idxtg[0]", np.array([2, 3]))])
        patch("roundtrip", lambda *a, **k: {"nis": np.zeros(1)})
        patch("check_roundoff", lambda *a: None)
        patch("changes", lambda res: {"nis": 0})
        patch("read_back", lambda *a: None)
        patch("require_fixed_point", lambda *a: None)
        patch("perturb", perturb)
        patch("guards", lambda ref, new: {})
        patch("write_state", lambda *a: None)
        patch("limiter_count", lambda res: None)
        patch("sha256", lambda p: "s")
        patch("data_sha256", lambda p: "d")

    def make(self, sigmas, accept):
        args = SimpleNamespace(family="fam", sigmas=sigmas, seed=1, accept_ratio=accept)
        base = self.dir / "base_state.h5"
        base.write_text("x")
        return mb.make_states(args, None, self.dir, self.dir / "s.h5", self.dir / "reference_state.h5", base,
                              self.dir / "raw.h5")


MISS = {0.02: (20.0, 1.0), 0.05: (30.0, 1.5)}  # idxtg[0] never meets 10, idxn[0] always does


def test_make_refuses_a_miss(monkeypatch, tmp_path):
    with pytest.raises(mb.Stop, match="no sigma in") as e:
        Fake(monkeypatch, tmp_path, MISS).make("0.02,0.05", [])
    assert e.value.code == 5
    assert not (tmp_path / "base_state.h5").exists()  # a failed make leaves no base state


def test_make_takes_an_accepted_miss(monkeypatch, tmp_path, capsys):
    assert Fake(monkeypatch, tmp_path, MISS).make("0.02,0.05", ["idxtg[0]"]) == 0
    out = capsys.readouterr().out
    assert "sigma = 0.02" in out  # the smallest
    assert 'accepted_ratio = { "idxtg[0]" = 1 }' in out
    assert "min_block_ratio = 20  # over the blocks not accepted" in out


def test_make_without_acceptance_prints_no_exception(monkeypatch, tmp_path, capsys):
    assert Fake(monkeypatch, tmp_path, {0.02: (20.0, 11.0)}).make("0.02", []) == 0
    out = capsys.readouterr().out
    assert "accepted_ratio" not in out and "min_block_ratio = 11\n" in out


def test_make_refuses_an_unknown_name_before_any_sigma(monkeypatch, tmp_path):
    f = Fake(monkeypatch, tmp_path, MISS)
    with pytest.raises(mb.Stop, match="no such block") as e:
        f.make("0.02", ["idxtg[9]"])
    assert e.value.code == 2 and not hasattr(f, "sigma")


def test_make_refuses_a_needless_acceptance(monkeypatch, tmp_path):
    with pytest.raises(mb.Stop, match="drop it") as e:
        Fake(monkeypatch, tmp_path, {0.02: (20.0, 10.0)}).make("0.02", ["idxtg[0]"])
    assert e.value.code == 2


def test_make_prints_nan_when_every_block_is_accepted(monkeypatch, tmp_path, capsys):
    assert Fake(monkeypatch, tmp_path, {0.02: (1.0, 1.0)}).make("0.02", ["idxn[0]", "idxtg[0]"]) == 0
    assert "min_block_ratio = nan  # over the blocks not accepted" in capsys.readouterr().out


def test_a_repeated_name_counts_once(monkeypatch, tmp_path, capsys):
    assert Fake(monkeypatch, tmp_path, MISS).make("0.02", ["idxtg[0]", "idxtg[0]"]) == 0
    assert capsys.readouterr().out.count('"idxtg[0]" =') == 1


def test_cmd_make_leaves_no_base_state_on_a_refusal(monkeypatch, tmp_path):
    """The needless-acceptance Stop is raised after base_state.h5 is written: cmd_make removes it (and the raw one)."""
    fam = tmp_path / "fam"
    fam.mkdir()
    monkeypatch.setattr(mb, "FAMILIES", tmp_path)
    base, raw = fam / "base_state.h5", fam / "base_state.raw.h5"

    def make_states(args, log, family_dir, source, reference, b, r):
        b.write_text("x")
        r.write_text("x")
        raise mb.Stop(2, "needless")

    monkeypatch.setattr(mb, "make_states", make_states)
    with pytest.raises(mb.Stop) as e:
        mb.cmd_make(SimpleNamespace(family="fam", source="s.h5"), None)
    assert e.value.code == 2 and not base.exists() and not raw.exists()


def test_make_keeps_the_rule_for_the_others(monkeypatch, tmp_path):
    with pytest.raises(mb.Stop) as e:
        Fake(monkeypatch, tmp_path, {0.02: (9.0, 1.0)}).make("0.02", ["idxtg[0]"])
    assert e.value.code == 5
