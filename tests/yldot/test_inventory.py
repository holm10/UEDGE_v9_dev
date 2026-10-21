"""Inventory tests of the yldot families (PRD section 6; AIUE-83 adds index truth, AIUE-93 adds the input inventory).

Per family, from a live evaluation (intake configuration): the idx* inverse is a bijection onto 1..neq that agrees
with igyl, the owner-confirmed [regions] of family.toml fit the live grid and give their recorded cell counts, and
a deliberately permuted map is rejected. Every diagnostic array is placed for the first-difference report.
"""
import numpy as np
import pytest

from yldot.harness import FAMILIES, INTAKE
from yldot.harness.compare import (PANDF_ORDER, REGIONS, UNORDERED, IndexTruthError, index_map, load_regions,
                                   region_cells)

FAMILY_NAMES = sorted(p.name for p in FAMILIES.iterdir() if (p / "input.py").is_file())


@pytest.fixture(scope="module")
def intake(runner):
    cache = {}

    def get(family):
        if family not in cache:
            res = runner.evaluate(family, config=INTAKE)
            assert res.ok, "{}: {} {}\n{}".format(family, res.status, res.message, res.log_tail)
            cache[family] = res.data
        return cache[family]
    return get


@pytest.mark.parametrize("family", FAMILY_NAMES)
def test_index_truth(intake, family):
    data = intake(family)
    regions = load_regions(family)
    imap = index_map(data, regions)
    assert imap.neq == data["neq"]
    counts = region_cells(regions)
    assert counts == {r: int(regions["cells"].get(r, 0)) for r in REGIONS}
    rows_per_region = {r: int((imap.region == r).sum()) for r in REGIONS}
    assert sum(rows_per_region.values()) == imap.neq
    for r in REGIONS:
        assert (rows_per_region[r] > 0) == (counts[r] > 0), (family, r)


@pytest.mark.parametrize("family", FAMILY_NAMES)
def test_permuted_map_rejected(intake, family):
    """Two active rows of different cells exchanged in the live idx* arrays (the deliberately permuted map)."""
    data = dict(intake(family))
    idxte = np.array(data["idxte"]).copy()
    cells = np.argwhere(idxte > 0)
    (a, b), (c, d) = cells[0], cells[-1]
    idxte[a, b], idxte[c, d] = idxte[c, d], idxte[a, b]
    data["idxte"] = idxte
    with pytest.raises(IndexTruthError, match="igyl disagrees"):
        index_map(data)


@pytest.mark.parametrize("family", ["d_only", "d_c"])
def test_diagnostics_are_placed(runner, family):
    res = runner.evaluate(family, config="steady", diagnostics=True)
    assert res.ok, "{}: {} {}".format(family, res.status, res.message)
    names = set(res.data["diagnostics"])
    unplaced = sorted(names - set(PANDF_ORDER) - set(UNORDERED))
    assert not unplaced, "diagnostic arrays in neither PANDF_ORDER nor UNORDERED (compare.py): {}".format(unplaced)
