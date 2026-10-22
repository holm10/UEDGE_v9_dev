"""History of the evaluation protocol (AIUE-86, PRD section 7.7): per family, family.toml's W and P reproduce at
W+1 and P+1 in both configurations, one more pandf at -1 and at +1 after step 8b reproduces yldot and yldot_J, and
steady +1 and -1 differ only in rows that ishosor = 0 removes. measure_history.py check runs every evaluation in a
fresh child; exit 4 is a defect (file a bugfix/v9-* ticket, never absorb it), exit 3 goes to the epic owner.

A measured family (one with a [history] table) also records the owner's decision of 2026-10-21: no child reuse.
"""
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from yldot.harness import FAMILIES

TOOL = Path(__file__).resolve().parent / "tools" / "measure_history.py"
FAMILY_NAMES = sorted(p.name for p in FAMILIES.iterdir() if (p / "input.py").is_file())


@pytest.mark.parametrize("family", FAMILY_NAMES)
def test_history(family):
    proc = subprocess.run([sys.executable, str(TOOL), "check", family], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.parametrize("family", FAMILY_NAMES)
def test_evaluation_keys(family):
    with open(FAMILIES / family / "family.toml", "rb") as f:
        toml = tomllib.load(f)
    if "history" not in toml:
        pytest.skip("{}: W and P not measured yet (placeholders)".format(family))
    ev = toml["evaluation"]
    assert isinstance(ev["w"], int) and ev["w"] >= 1, ev
    assert isinstance(ev["p"], int) and ev["p"] >= 1, ev
    assert ev["child_reuse"] is False, ev
