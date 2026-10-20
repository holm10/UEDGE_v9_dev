"""Variant application and replay in the evaluation child (AIUE-93, PRD section 7.2): one variant per phase on
d_only (a PRE scalar and a POST dynamic array, steady), plus a POST array in the timestep configuration, where the
variant is applied in both passes. Each one changes yldot, and replaying the recorded value reproduces yldot and
yldot_J bit for bit in a new child."""
import numpy as np
import pytest

from yldot.harness import variants

FAMILY = "d_only"
CASES = [  # variable, phase, config
    ("bbb.kye", "PRE", "steady"),
    ("bbb.nwallo", "POST", "steady"),  # set by d_only's input.py after its own allocate (input.py:56-58)
    ("bbb.fdtnixy", "POST", "timestep"),
]


def describe(res):
    return "{} {}: {}: {}\n{}".format(res.family, res.config, res.status, res.message, res.log_tail)


@pytest.fixture(scope="module")
def plan():
    return {v.id: v for v in variants.plan()}


@pytest.mark.parametrize("key, phase, config", CASES)
def test_apply_and_replay(runner, plan, key, phase, config):
    v = plan[key]
    assert (v.phase, v.config, v.rule) == (phase, config, "default")
    default = runner.evaluate(FAMILY, config=config)
    gen = runner.evaluate(FAMILY, variant=v)
    assert default.ok and gen.ok, describe(default if not default.ok else gen)
    assert gen.config == config
    rec = gen.data["variant"][phase]
    other = gen.data["variant"]["POST" if phase == "PRE" else "PRE"]
    assert other is None
    assert rec["status"] == "applied", rec["status"]
    d, applied = variants.decode(rec["d"]), variants.decode(rec["applied"])
    assert np.isfinite(d).all()
    expected = variants.rule_value(d, "default")
    assert applied.tobytes() == expected.tobytes()
    if config == "timestep":
        assert rec["second_pass"] in ("kept", "reset")
    assert (gen.data["yldot"] != default.data["yldot"]).any(), (
        "{}: variant {} leaves yldot unchanged in {}; pick another variable of the same kind and record why on the "
        "ticket page".format(FAMILY, key, config))

    rep = runner.evaluate(FAMILY, variant=v, replay=rec["applied"])
    assert rep.ok, describe(rep)
    assert rep.data["variant"][phase]["applied"] == rec["applied"]
    for k in ("yldot", "yldot_J"):
        assert rep.data[k].tobytes() == gen.data[k].tobytes(), "{} {}: replay differs".format(key, k)


def test_replay_wrong_shape(runner, plan):
    v = plan["bbb.nwallo"]
    x = runner.evaluate(FAMILY, variant=v, replay=variants.encode(np.ones(3)))
    assert x.status == "error", describe(x)
    assert "does not fit" in x.message


def test_excluded_never_applied(runner, plan):
    x = runner.evaluate(FAMILY, variant=plan["bbb.restart"])
    assert x.status == "error", describe(x)
    assert "EXCLUDED" in x.message
