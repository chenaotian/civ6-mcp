"""Offline checks for the fixed capability-only diagnostic; never connect."""
import asyncio
import importlib.util
from pathlib import Path

import pytest
from lupa import LuaRuntime


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "live_adjacency_capability_check.py"
spec = importlib.util.spec_from_file_location("adjacency_capability_check", SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def execute(mutation=""):
    vm = LuaRuntime()
    vm.execute(r'''
calls=0
function forbidden() calls=calls+1;error('SECRET_UI_OR_WORLD_CONTENT') end
GameConfiguration={IsAnyMultiplayer=function() return false end,IsHotseat=function() return false end,
    IsWorldBuilderEditor=function() return false end}
Automation={IsActive=function() return false end}
Game={GetLocalPlayer=function() return 0 end,GetLocalObserver=function() return 0 end}
Players={[0]={IsAlive=function() return true end,IsHuman=function() return true end}}
ContextPtr={GetID=function() return 'DistrictPlotIconManager' end,IsVisible=forbidden,GetParent=forbidden}
Controls={PlotBonusContainer={GetChildren=forbidden,GetParent=forbidden,IsVisible=forbidden}}
GetInstanceAt=forbidden;Realize2dArtForCityDistricts=forbidden;ClearEveything=forbidden
UI={GetHeadSelectedCity=forbidden,GetInterfaceMode=forbidden,GetInterfaceModeParameter=forbidden,
    SelectCity=forbidden,SetInterfaceMode=forbidden}
UILens={CreateLensLayerHash=forbidden,IsLayerOn=forbidden}
CityOperationTypes={PARAM_DISTRICT_TYPE=31}
InterfaceModeTypes={DISTRICT_PLACEMENT=4,SELECTION=0}
Events={InterfaceModeChanged={Add=forbidden},CitySelectionChanged={Add=forbidden},
    LensLayerOff={Add=forbidden},LoadGameViewStateDone={Add=forbidden},LocalPlayerChanged={Add=forbidden}}
LuaEvents={CityPanel_ProductionClose=forbidden}
ExposedMembers={Civ6FairState={secret='SECRET_STATE'}}
Map={GetPlot=forbidden,GetPlotByIndex=forbidden}
'''+mutation)
    output = []
    vm.globals().print = output.append
    vm.execute(probe.build_probe())
    return vm, probe.project("\n".join(output))


def test_probe_reads_only_types_and_fixed_context_equality_without_invoking_capabilities():
    vm, result = execute("_G=nil;rawget=nil;debug=nil")
    assert result["ok"] is True and result["context_verified"] is True
    assert result["types"]["GetInstanceAt"] == "function"
    assert result["types"]["ExposedMembers.Civ6FairState"] == "table"
    assert vm.globals().calls == 0 and "SECRET" not in str(result)


@pytest.mark.parametrize("mutation", [
    "ContextPtr.GetID=function() return 'DistrictPlotIconManager.xml' end",
    "GetInstanceAt=nil;Realize2dArtForCityDistricts=nil;ExposedMembers=nil",
    "Controls.PlotBonusContainer=setmetatable({},{__index=function() error('SECRET_ERROR') end})",
])
def test_missing_or_inaccessible_capabilities_remain_types_not_error_text(mutation):
    _, result = execute(mutation)
    assert result["ok"] is True
    assert "SECRET" not in str(result)


@pytest.mark.parametrize("mutation", [
    "ContextPtr.GetID=function() return 'GameCore_Tuner' end",
    "GameConfiguration.IsAnyMultiplayer=function() return true end",
    "Game.GetLocalObserver=function() return -1 end",
    "Players[0].IsHuman=function() return false end",
])
def test_probe_rejects_wrong_context_or_controller(mutation):
    vm, result = execute(mutation)
    assert result["ok"] is False and vm.globals().calls == 0


def test_python_projection_rejects_raw_values_in_capability_types():
    import json
    _, result = execute()
    result["types"]["GetInstanceAt"] = "SECRET_VALUE"
    with pytest.raises(ValueError):
        probe.project("CIV6FAIR_JSON:" + json.dumps(result))


@pytest.mark.parametrize("fail", [False, True])
def test_local_whitelist_adds_only_fixed_context_and_restores_after_success_or_error(monkeypatch, fail):
    _, result = execute()
    import json
    module = probe.transport_module
    original = module._CONTEXTS
    calls = []

    class FakeTransport:
        async def execute(self, source, context):
            assert module._CONTEXTS == original | {"DistrictPlotIconManager"}
            assert context == "DistrictPlotIconManager" and source == probe.build_probe()
            calls.append("execute")
            if fail:
                raise RuntimeError("SECRET_CONNECTION_ERROR")
            return "CIV6FAIR_JSON:" + json.dumps(result)

        async def close(self):
            calls.append("close")

    monkeypatch.setattr(module, "FireTunerTransport", FakeTransport)
    output = asyncio.run(probe.run())
    assert output["ok"] is not fail and "SECRET" not in str(output)
    assert calls == ["execute", "close"] and module._CONTEXTS is original
