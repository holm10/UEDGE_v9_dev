"""The family states are round-trip fixed points (AIUE-140): one exmain at reference_state.h5 or base_state.h5
changes no saved entry.

exmain builds yl from the saved state and pandf converts it back; that round trip is not exact, and after a
converged call gridseq re-saves its result. From a state that has not been through it, a second exmain starts from
slightly different saved arrays and its yldot can differ by an ulp (dnull_imp2: 2 Ti rows). make_base_state.py make
writes only fixed points; this test checks the committed states with its check command, which runs every
evaluation in a fresh child.
"""
import subprocess
import sys
from pathlib import Path

import pytest

from yldot.harness import FAMILIES

TOOL = Path(__file__).resolve().parent / "tools" / "make_base_state.py"
FAMILY_NAMES = sorted(p.name for p in FAMILIES.iterdir() if (p / "input.py").is_file())


@pytest.mark.parametrize("state", ["reference_state.h5", "base_state.h5"])
@pytest.mark.parametrize("family", FAMILY_NAMES)
def test_state_is_roundtrip_fixed_point(family, state):
    proc = subprocess.run([sys.executable, str(TOOL), "check", family, "--state", state],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    line = proc.stdout.strip().splitlines()[-1]
    assert "fixed_point=true" in line, line
