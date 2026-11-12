"""Input inventory, overrides.toml and value rules of the yldot suite (AIUE-93, PRD section 7.2). No evaluation
children here, except the cross-check against the built module, which runs in a subprocess with its own HOME."""
import json
import os
import subprocess
import sys

import numpy as np
import pytest

from yldot.harness import inputs, variants

CHARACTER = {"bbb.svrpkg", "bbb.petscoptfile", "bbb.petscopts", "bbb.GridFileName", "com.geometry",
             "com.mcfilename", "com.coronalimpfname"}  # PRD section 7.2
LAYOUT = {"com.nhsp", "com.nzsp", "com.nisp", "com.nusp", "com.nfsp", "com.ngsp", "com.nhgsp"}  # owner, 2026-10-20
ADDITIONS = {"bbb.isflxvar", "bbb.isrscalf", "bbb.xlinc", "bbb.xrinc", "bbb.yinc", "bbb.isjaccorall",
             "bbb.isbcwdt", "bbb.ismcnon"}  # owner confirmed 2026-10-20
TIMESTEP = {"bbb.fdtnixy", "bbb.fdtupxy", "bbb.fdttexy", "bbb.fdttixy", "bbb.fdtngxy", "bbb.fdttgxy",
            "bbb.fdtphixy", "bbb.cfqydt", "bbb.isbcwdt"}

RUNTIME = '''import json, sys
import uedge
out = {}
for m in sys.argv[1:]:
    p = getattr(uedge, m)
    out[m] = sorted(v for v in p.varlist() if {"input", "maybeinput"} & set(p.getvarattr(v).split()))
print(json.dumps(out))
'''


def bitwise(a, b):
    a, b = np.asarray(a), np.asarray(b)
    return a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()


# ---------------------------------------------------------------- inventory


def test_summary():
    s = inputs.summary()
    print("\ninput inventory:", s)  # 968 on v9-develop at AIUE-93 (bbb 947, com 19, aph 1, api 1)
    assert s["tagged"] == sum(s["by_package"].values())
    assert s["character"] == len(CHARACTER)


def test_matches_built_module(tmp_path):
    """The parser's tagged set equals the input/maybeinput attributes of the built and installed packages."""
    env = dict(os.environ, HOME=str(tmp_path), UEDGE_BANNER="0")
    proc = subprocess.run([sys.executable, "-c", RUNTIME] + list(inputs.PACKAGES), cwd=tmp_path, env=env,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    built = {"{}.{}".format(m, v) for m, names in json.loads(proc.stdout.splitlines()[-1]).items() for v in names}
    parsed = set(inputs.tagged())
    assert inputs.summary()["tagged"] == len(built)
    assert parsed == built, "only parsed: {}; only built: {}".format(
        sorted(parsed - built)[:10], sorted(built - parsed)[:10])


def test_forthon_comment_rules():
    p = inputs.parse()
    # tags inside '#' comments (bbb/bbb.v:558,2073,2076) and a '$' private remark (:384) do not count
    for key in ("bbb.istepfcix", "bbb.bctype", "bbb.capx"):
        assert not p[key].tagged, key
    assert "bbb.cfw" not in p
    # a tag on a continuation line attaches to the variable before it (:1429-1430); a doubled tag counts once
    assert p["bbb.rcxighg"].tagged and p["bbb.flalftmx"].tagged


def test_keys_and_types():
    t = inputs.tagged()
    for key, v in t.items():
        assert key == "{}.{}".format(v.package, v.name) and v.package in inputs.PACKAGES
        if v.dynamic:
            assert v.type in ("real", "integer"), key
    assert {k for k, v in t.items() if v.type == "character"} == CHARACTER


# ---------------------------------------------------------------- overrides.toml


def test_overrides_valid():
    ov = variants.load_overrides()
    assert all(o["reason"].strip() for o in ov.values())
    assert {k for k, o in ov.items() if o.get("add")} == ADDITIONS


@pytest.mark.parametrize("text, match", [
    ('["bbb.nosuchvar"]\nreason = "x"\n', "no such variable"),
    ('["bbb.kye"]\nreason = " "\n', "no reason"),
    ('["bbb.kye"]\nadd = true\nreason = "x"\n', "add = true on a tagged"),
    ('["bbb.isflxvar"]\nreason = "x"\n', "needs add = true"),
    ('["bbb.kye"]\nconfig = "transient"\nreason = "x"\n', "config"),
    ('["bbb.kye"]\nexclude = true\nwhy = "x"\nreason = "x"\n', "unknown fields"),
    ('["bbb.jxsori"]\nbound = "com.nxpt"\nvalues = [2]\nreason = "x"\n', "values and bound"),
    ('["bbb.kye"]\nbound = "com.nxpt"\nreason = "x"\n', "bound on a real"),
    ('["bbb.kye"]\nexclude = true\nvalues = [1.0]\nreason = "x"\n', "exclude together with"),
    ('["bbb.kye"]\nexclude = true\nphase = "PRE"\nreason = "x"\n', "exclude together with"),
    ('["bbb.jxsori"]\nexclude = true\nbound = "com.nxpt"\nreason = "x"\n', "exclude together with"),
    ('["bbb.svrpkg"]\nvalues = [1]\nreason = "x"\n', "character variable"),
    ('["bbb.svrpkg"]\nbound = "com.nxpt"\nreason = "x"\n', "bound on a character"),
    ('["bbb.methn"]\nvalues = ["a"]\nreason = "x"\n', "integers or floats"),
    ('["bbb.methn"]\nvalues = [true]\nreason = "x"\n', "integers or floats"),
    ('["bbb.ziin"]\ncharge = "com.nhsp"\nvalues = [1.0]\nreason = "x"\n', "charge together with"),
    ('["bbb.isupgon"]\ncharge = "com.nhsp"\nreason = "x"\n', "not a real 1-D array"),
    ('["bbb.kye"]\ncharge = "com.nhsp"\nreason = "x"\n', "not a real 1-D array"),
    ('["bbb.ziin"]\ncharge = "bbb.kye"\nreason = "x"\n', "is not an integer scalar"),
])
def test_overrides_refused(tmp_path, text, match):
    f = tmp_path / "overrides.toml"
    f.write_text(text)
    with pytest.raises(ValueError, match=match):
        variants.load_overrides(f)


# ---------------------------------------------------------------- the plan


@pytest.fixture(scope="module")
def plan():
    return variants.plan()


def test_plan_covers_inventory(plan):
    ids = [v.id for v in plan]
    assert len(ids) == len(set(ids))
    assert {v.key for v in plan if v.rule != "set"} == set(inputs.tagged()) | ADDITIONS
    sets = [v for v in plan if v.rule == "set"]
    assert [v.id for v in sets] == [v.id for v in variants.load_sets()]  # after the variants, in file order
    assert plan[-len(sets):] == sets if sets else True


def test_plan_exclusions(plan):
    excluded = {v.id: v.reason for v in plan if v.excluded}
    for key in CHARACTER | LAYOUT | {"bbb.restart", "bbb.ismcnon", "bbb.isimpon=other"}:
        assert excluded.get(key, "").strip(), key
    assert "AIUE-10" in excluded["bbb.isimpon=other"]


CELL_INDEX = ["bbb.ixfixnc", "bbb.incixc", "bbb.ixbpmin", "bbb.ix_sjcsor", "bbb.ix_ejcsor", "bbb.iy_sjcsor",
              "bbb.iy_ejcsor", "bbb.ixgb"]  # owner decision 5
PHI_BC = ["bbb.iphibcwi", "bbb.iphibcwo", "bbb.iphibcwiix", "bbb.iphibcwoix"]  # owner decision 6


def test_plan_cell_index_and_phi_bc(plan):
    by_id = {v.id: v for v in plan}
    for key in CELL_INDEX:
        assert by_id[key].rule == "default" and not by_id[key].excluded and by_id[key].reason.strip(), key
    for key in PHI_BC:
        assert key not in by_id
        for val in (0, 1, 3, 4):
            v = by_id["{}={}".format(key, val)]
            assert v.rule == "value" and v.value == val and not v.excluded, v.id


def test_plan_values_phases_configs(plan):
    by_key = {}
    for v in plan:
        by_key.setdefault(v.key, []).append(v)
    assert [v.id for v in by_key["bbb.isimpon"] if not v.excluded] == ["bbb.isimpon=2", "bbb.isimpon=6",
                                                                       "bbb.isimpon=7"]
    assert [v.value for v in by_key["bbb.methg"]] == [22, 33, 44, 55, 66, 77]
    assert [v.value for v in by_key["bbb.methn"]] == [22, 33]
    for key in ("bbb.jxsori", "bbb.jxsoro"):
        assert by_key[key][0].rule == "bounded" and by_key[key][0].bound == "com.nxpt"
    for key in ("bbb.igspsori", "bbb.igspsoro", "bbb.igspsorlb", "bbb.igspsorrb"):
        assert by_key[key][0].rule == "bounded" and by_key[key][0].bound == "com.ngsp"
    assert [(v.rule, v.bound, v.excluded) for v in by_key["bbb.ziin"]] == [("charge", "com.nhsp", False)]
    allvars = inputs.parse()
    for v in plan:
        if v.rule == "set":
            continue
        assert v.config == ("timestep" if v.key in TIMESTEP else "steady"), v.id
        assert v.phase == ("POST" if allvars[v.key].dynamic else "PRE"), v.id


def test_variant_dict_roundtrip(plan):
    for v in plan:
        assert variants.Variant.from_dict(json.loads(json.dumps(v.to_dict()))) == v


# ---------------------------------------------------------------- value rules (owner, 2026-10-20: elementwise)


def test_rule_default():
    i = np.array([0, 1, 5, -2], dtype=np.int64)
    assert bitwise(variants.rule_value(i, "default"), np.array([1, 0, 6, -1], dtype=np.int64))
    r = np.array([0.0, 2.5, -0.0, 1e-30])
    assert bitwise(variants.rule_value(r, "default"), np.array([1.0, 2.5 * 1.1, 1.0, 1e-30 * 1.1]))
    assert bitwise(variants.rule_value(np.float64(3.0), "default"), np.float64(3.0 * 1.1))
    assert bitwise(variants.rule_value(np.int64(1), "default"), np.int64(0))


def test_rule_value_and_bounded():
    assert bitwise(variants.rule_value(np.int64(33), "value", 22), np.int64(22))
    with pytest.raises(ValueError, match="not representable"):
        variants.rule_value(np.int64(0), "value", 2.5)
    d = np.array([1, 1], dtype=np.int64)
    assert bitwise(variants.rule_value(d, "bounded", bound=1), d)
    assert bitwise(variants.rule_value(np.array([1, 2]), "bounded", bound=2), np.array([2, 1]))
    assert bitwise(variants.rule_value(np.array([2]), "bounded", bound=3), np.array([3]))
    with pytest.raises(TypeError):
        variants.rule_value(np.array([1.0]), "bounded", bound=2)


def test_rule_charge():
    # owner 2026-10-23 (AIUE-161): d+1 on the hydrogenic ion slots only; atoms and impurity charge states keep d
    d = np.array([1, 0, 1, 2, 3, 4, 5, 6], dtype=np.float64)
    assert bitwise(variants.rule_value(d, "charge", bound=2), np.array([2, 0, 1, 2, 3, 4, 5, 6], dtype=np.float64))
    assert bitwise(variants.rule_value(np.zeros(2), "charge", bound=2), np.zeros(2))
    assert bitwise(d, np.array([1, 0, 1, 2, 3, 4, 5, 6], dtype=np.float64))  # d itself is not changed
    with pytest.raises(TypeError):
        variants.rule_value(np.array([1, 0]), "charge", bound=2)
    with pytest.raises(TypeError):
        variants.rule_value(np.ones((2, 2)), "charge", bound=2)


def test_encode_roundtrip():
    for x in (np.float64(1.1), np.array([[-0.0, 1e-300], [2.0 / 3.0, 1e18]]), np.array([[1, -2], [3, 4]]),
              np.int64(7), np.array([], dtype=np.float64)):
        assert bitwise(variants.decode(json.loads(json.dumps(variants.encode(x)))), x)
    with pytest.raises(ValueError, match="non-finite"):
        variants.encode(np.array([np.nan]))


# ---------------------------------------------------------------- combination sets (AIUE-257, owner D1 2026-11-11)

GOOD_SETS = '''
["set:pfte1"]
assign = { "bbb.istepfc" = 1, "bbb.tewalli" = { scale = 1.5 } }
reason = "istepfc = 1 with tewalli"

["set:pfte1-ly"]
assign = { "bbb.istepfc" = 1, "bbb.tewalli" = { scale = 1.5 }, "bbb.lyte" = { value = 0.05, at = [0] } }
base = "set:pfte1"
families = ["d_only", "d_c"]
issues = ["AIUE-269"]
reason = "based"

["set:pfvsix"]
assign = { "bbb.ispfbcvsix" = 1, "bbb.istepfcix" = { cycle = [0, 1, 3] }, "bbb.lyteix" = { cycle = [0.02, 0.05], at = [0] } }
families = ["d_only"]
reason = "per-cell PF arrays"
'''


def load_sets_text(tmp_path, text):
    f = tmp_path / "combinations.toml"
    f.write_text(text)
    return variants.load_sets(f)


def test_sets_load(tmp_path):
    sets = {v.id: v for v in load_sets_text(tmp_path, GOOD_SETS)}
    assert list(sets) == ["set:pfte1", "set:pfte1-ly", "set:pfvsix"]
    a, b, c = sets.values()
    assert (a.rule, a.key, a.phase, a.config, a.base, a.families, a.issues) == (
        "set", "set:pfte1", "POST", "steady", None, variants.SMALL_FAMILIES, None)  # tewalli is dynamic
    assert a.assign == (("bbb.istepfc", "value", 1, ()), ("bbb.tewalli", "scale", 1.5, ()))
    assert a.keys == ("bbb.istepfc", "bbb.tewalli")
    assert (b.phase, b.base, b.families, b.issues) == ("POST", "set:pfte1", ("d_only", "d_c"), ("AIUE-269",))
    assert c.assign[1] == ("bbb.istepfcix", "cycle", (0, 1, 3), ())
    assert c.assign[2] == ("bbb.lyteix", "cycle", (0.02, 0.05), (0,))
    for v in sets.values():
        assert variants.Variant.from_dict(json.loads(json.dumps(v.to_dict()))) == v
    plan = variants.plan(sets=list(sets.values()), family="d_c")
    assert [v.id for v in plan if v.rule == "set"] == ["set:pfte1", "set:pfte1-ly"]
    assert [v.id for v in variants.plan(sets=list(sets.values())) if v.rule == "set"] == list(sets)


def test_value_list_families():
    """A value list limited to some families (AIUE-257, owner 2026-11-12): its =N and =other ids run there, and the
    other families keep the key's default-rule id."""
    small = set(variants.SMALL_FAMILIES)
    plan = variants.plan()
    by_id = {v.id: v for v in plan}
    assert set(by_id["bbb.istepfc=1"].families) == small and by_id["bbb.istepfc=other"].excluded
    fallback = by_id["bbb.istepfc"]
    assert fallback.rule == "default" and set(fallback.families) == set(variants.all_families()) - small
    for fam in variants.all_families():
        ids = {v.id for v in variants.plan(family=fam)}
        assert ("bbb.istepfc=1" in ids) == (fam in small) and ("bbb.istepfc" in ids) == (fam not in small), fam
    assert by_id["bbb.iphibcwi=1"].families is None  # an entry without families runs everywhere
    # rest_exclude: isch_sput runs 0-7 in the small families and keeps the AIUE-195 exclusion in the others
    ch = by_id["bbb.isch_sput"]
    assert ch.excluded and "AIUE-195" in ch.reason and set(ch.families) == set(variants.all_families()) - small
    assert not by_id["bbb.isch_sput=7"].excluded and set(by_id["bbb.isch_sput=7"].families) == small


@pytest.mark.parametrize("text, match", [
    ('["bbb.istepfc"]\nfamilies = ["d_only"]\nreason = "x"\n', "families only with values"),
    ('["bbb.istepfc"]\nvalues = [0]\nfamilies = []\nreason = "x"\n', "non-empty list"),
    ('["bbb.istepfc"]\nvalues = [0]\nfamilies = ["nosuch"]\nreason = "x"\n', "no family"),
    ('["bbb.istepfc"]\nvalues = [0]\nrest_exclude = "y"\nreason = "x"\n', "rest_exclude without families"),
    ('["bbb.istepfc"]\nvalues = [0]\nfamilies = ["d_only"]\nrest_exclude = " "\nreason = "x"\n', "needs a reason"),
])
def test_value_list_families_refused(tmp_path, text, match):
    f = tmp_path / "overrides.toml"
    f.write_text(text)
    with pytest.raises(ValueError, match=match):
        variants.load_overrides(f)


@pytest.mark.parametrize("text, match", [
    ('["pfte1"]\nassign = { "bbb.istepfc" = 1 }\nreason = "x"\n', "set:<name>"),
    ('["set:a"]\nassign = { "bbb.istepfc" = 1 }\nreason = " "\n', "no reason"),
    ('["set:a"]\nassign = {}\nreason = "x"\n', "non-empty table"),
    ('["set:a"]\nassign = { "bbb.istepfc" = 1 }\nwhy = "x"\nreason = "x"\n', "unknown fields"),
    ('["set:a"]\nassign = { "bbb.nosuchvar" = 1 }\nreason = "x"\n', "no such variable"),
    ('["set:a"]\nassign = { "bbb.restart" = 1 }\nreason = "x"\n', "EXCLUDED in overrides.toml"),
    ('["set:a"]\nassign = { "bbb.petscoptfile" = 1 }\nreason = "x"\n', "character variable"),
    ('["set:a"]\nassign = { "bbb.istepfc" = 1.5 }\nreason = "x"\n', "not an integer"),
    ('["set:a"]\nassign = { "bbb.istepfc" = { scale = 2 } }\nreason = "x"\n', "scale on a integer"),
    ('["set:a"]\nassign = { "bbb.lyte" = { value = 1.0, scale = 2.0 } }\nreason = "x"\n', "exactly one of"),
    ('["set:a"]\nassign = { "bbb.lyte" = { value = 1.0, at = [0, 1] } }\nreason = "x"\n', "more indices"),
    ('["set:a"]\nassign = { "bbb.lyte" = { cycle = [1.0] } }\nreason = "x"\n', "cycle runs along"),
    ('["set:a"]\nassign = { "bbb.ispfbcvsix" = 1, "bbb.lyteix" = { cycle = [1.0] } }\nreason = "x"\n',
     "cycle runs along"),
    ('["set:a"]\nassign = { "bbb.istepfcix" = { cycle = [0, 1] } }\nreason = "x"\n', "bbb.ispfbcvsix = 1"),
    ('["set:a"]\nassign = { "bbb.iswobcvsix" = 1, "bbb.lyteix" = { cycle = [1.0], at = [0] } }\nreason = "x"\n',
     "bbb.ispfbcvsix = 1"),
    ('["set:a"]\nassign = { "bbb.ispfbcvsix" = 1, "bbb.lyniix" = 0.1 }\nreason = "x"\n', "bbb.iswobcvsix = 1"),
    ('["set:a"]\nassign = { "bbb.tewalli" = 1.0 }\nphase = "PRE"\nreason = "x"\n', "phase PRE with a dynamic"),
    ('["set:a"]\nassign = { "bbb.istepfc" = 1 }\nconfig = "transient"\nreason = "x"\n', "config"),
    ('["set:a"]\nassign = { "bbb.istepfc" = 1 }\nfamilies = ["nosuch"]\nreason = "x"\n', "no family"),
    ('["set:a"]\nassign = { "bbb.istepfc" = 1 }\nissues = ["#1"]\nreason = "x"\n', "Jira keys"),
    ('["set:a"]\nassign = { "bbb.istepfc" = 1 }\nbase = "set:b"\nreason = "x"\n', "not a set of this file"),
    ('["set:a"]\nassign = { "bbb.istepfc" = 1 }\nreason = "x"\n["set:b"]\n'
     'assign = { "bbb.istepfc" = 1, "bbb.istipfc" = 1 }\nbase = "set:a"\nreason = "x"\n["set:c"]\n'
     'assign = { "bbb.istewc" = 1 }\nbase = "set:b"\nreason = "x"\n', "has a base itself"),
    ('["set:a"]\nassign = { "bbb.istepfc" = 1 }\nfamilies = ["d_only"]\nreason = "x"\n["set:b"]\n'
     'assign = { "bbb.istepfc" = 1, "bbb.istipfc" = 1 }\nbase = "set:a"\nfamilies = ["d_c"]\nreason = "x"\n',
     "not among the base's"),
    ('["set:a"]\nassign = { "bbb.istepfc" = 1 }\nfamilies = ["imp7"]\nreason = "x"\n["set:b"]\n'
     'assign = { "bbb.istepfc" = 1, "bbb.istipfc" = 1 }\nbase = "set:a"\nfamilies = ["imp7"]\nreason = "x"\n',
     "needs a full store"),
    ('["set:a"]\nassign = { "bbb.istepfc" = 1 }\nreason = "x"\n["set:b"]\n'
     'assign = { "bbb.istepfc" = 1, "bbb.istipfc" = 1 }\nbase = "set:a"\nconfig = "timestep"\nreason = "x"\n',
     "runs in steady"),
    ('["set:a"]\nassign = { "bbb.istepfc" = 1 }\nreason = "x"\n["set:b"]\nassign = { "bbb.istipfc" = 3 }\n'
     'base = "set:a"\nreason = "x"\n', "does not assign the base's keys"),
])
def test_sets_refused(tmp_path, text, match):
    with pytest.raises(ValueError, match=match):
        load_sets_text(tmp_path, text)


def test_sets_file_valid():
    """The repository's combinations.toml loads, and no set id collides with a variant id."""
    sets = variants.load_sets()
    ids = [v.id for v in variants.plan()]
    assert len(ids) == len(set(ids)) and all(v.id in ids for v in sets)


def test_set_value():
    d = np.array([[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0]])
    assert bitwise(variants.set_value(d, "value", 0.5), np.full((2, 4), 0.5))
    assert bitwise(variants.set_value(d, "value", 0.5, (1, 2)), np.array([[1, 2, 3, 4], [5, 6, 0.5, 8.0]]))
    assert bitwise(variants.set_value(d, "scale", 2.0, (0,)), np.array([[2, 4, 6, 8], [5, 6, 7, 8.0]]))
    assert bitwise(variants.set_value(d, "cycle", (0.1, 0.2), (1,)), np.array([[1, 2, 3, 4], [.1, .2, .1, .2]]))
    assert bitwise(d, np.array([[1, 2, 3, 4], [5, 6, 7, 8.0]]))  # d itself is not changed
    i = np.zeros((5, 3), dtype=np.int64)  # an (0:nx+1, nisp) array: the cycle runs along ix, every species
    assert bitwise(variants.set_value(i, "cycle", (0, 1, 3)), np.array([[0] * 3, [1] * 3, [3] * 3, [0] * 3, [1] * 3]))
    assert bitwise(variants.set_value(np.int64(0), "value", 4), np.int64(4))
    with pytest.raises(ValueError, match="not representable"):
        variants.set_value(i, "cycle", (0, 1.5))
    with pytest.raises(TypeError):
        variants.set_value(i, "scale", 2.0)
    with pytest.raises(ValueError, match="needs an axis"):
        variants.set_value(d, "cycle", (1.0,), (0, 1))
