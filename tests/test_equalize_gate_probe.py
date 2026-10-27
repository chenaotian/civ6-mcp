"""The live diagnostic itself is only executed against local Lua doubles."""
import importlib.util
import json
from pathlib import Path

import pytest

from test_deal_equalize import vm
from test_service import raw


spec = importlib.util.spec_from_file_location("equalize_gate_probe", Path(__file__).parents[1] / "scripts/live_equalize_gate_check.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def execute(extra=""):
    runtime = vm(extra + '''
DealManager.GetWorkingDeal=function() error('RAW DEAL FORBIDDEN') end
DealManager.SendWorkingDeal=function() error('ACTION FORBIDDEN') end
equalize_button.GetText=function() error('CAPTION FORBIDDEN') end
''')
    result = runtime.execute("out={}\n" + probe.probe_body(1) + "\nreturn out")
    return {"probe_stage": result["probe_stage"], "probe_checks": dict(result["probe_checks"].items())}


@pytest.mark.parametrize("hidden", [False, True])
def test_probe_reports_ui_and_public_phase_without_deal_or_caption_reads(hidden):
    data = execute(f"flags.visible={str(not hidden).lower()}\n")
    result = probe.project(raw(**data))
    assert result["stage"] == "complete"
    assert result["checks"]["ran"] is True
    assert result["checks"]["button_visible"] is not hidden
    assert result["checks"]["button_parent_matches"] is True
    assert result["checks"]["phase_present"] is True


def test_probe_returns_fixed_stage_after_native_error_only():
    data = execute("equalize_button.IsVisible=function() error('SECRET') end")
    result = probe.project(raw(**data))
    assert result["checks"]["ran"] is False
    assert "SECRET" not in json.dumps(result)


@pytest.mark.parametrize("checks", [{"private": True}, {"phase_present": 1}, {"button_visible": "true"}])
def test_probe_rejects_unknown_fields_or_non_boolean_output(checks):
    with pytest.raises(ValueError):
        probe.project(raw(probe_stage="complete", probe_checks=checks))


@pytest.mark.parametrize("target", [-1, 64, True, "1"])
def test_target_is_strictly_bounded(target):
    with pytest.raises(ValueError):
        probe.probe_body(target)
