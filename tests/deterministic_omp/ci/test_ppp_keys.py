"""Unit tests for ci/ppp_keys.py (no UEDGE build needed; ppp is faked)."""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ppp_keys  # noqa: E402

FLOWS = ('tebox1|tebox|2,4|3|jac|none|{"OMPJacMinChunkLen": 1, "OMPJacVerbose": 1};'
         'up1|up|4|3|jac|none|;full|full|2,4|2|jac|3|')


def test_keys_present():
    ppp = types.SimpleNamespace(OMPJacMinChunkLen=300, OMPJacVerbose=0)
    assert ppp_keys.missing(FLOWS, ppp) == []
    assert ppp_keys.flow_ppp(FLOWS) == [("tebox1", {"OMPJacMinChunkLen": 1, "OMPJacVerbose": 1})]


def test_missing_key_is_named():
    ppp = types.SimpleNamespace(OMPJacVerbose=0)  # a pre-AIUE-61 build: no OMPJacMinChunkLen
    assert ppp_keys.missing(FLOWS, ppp) == ["flow tebox1: ppp.OMPJacMinChunkLen"]


def test_main_exit_codes(monkeypatch, capsys):
    fake = types.ModuleType("uedge")
    fake.ppp = types.SimpleNamespace(OMPJacVerbose=0)
    monkeypatch.setitem(sys.modules, "uedge", fake)
    assert ppp_keys.main([FLOWS]) == 2
    assert "no such ppp variable: flow tebox1: ppp.OMPJacMinChunkLen" in capsys.readouterr().out
    fake.ppp.OMPJacMinChunkLen = 300
    assert ppp_keys.main([FLOWS]) == 0
    assert ppp_keys.main(["a|b|2|1|jac|none|"]) == 0          # no flow sets ppp: no import needed
    assert ppp_keys.main(["a|b|2|1|jac|none|{bad"]) == 2       # not JSON
    assert ppp_keys.main(["a|b|2|1|jac|none|[1]"]) == 2        # not an object
