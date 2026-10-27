"""The diagnostic only compares fixed UI/observer state; never runs live."""
import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

from test_district_preview import vm, invoke

PATH = Path(__file__).resolve().parents[1] / 'scripts/live_adjacency_state_check.py'
spec = importlib.util.spec_from_file_location('adjacency_state_check', PATH)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def read(v):
    output=[];v.globals().print=output.append
    v.execute(probe.build_probe())
    return probe.project('\n'.join(output))


def test_diagnostic_reads_booleans_only_without_labels_map_or_ui_mutations():
    v=vm();invoke(v,'begin')
    v.execute('Map.GetPlot=forbidden;Map.GetPlotByIndex=forbidden;UI.SelectCity=forbidden;UI.SetInterfaceMode=forbidden;GetInstanceAt=forbidden')
    result=read(v)
    assert result['ok'] and result['checks']['observer_exists'] is True
    assert result['checks']['mode_placement'] is True and result['checks']['get_wrapper_intact'] is False
    assert v.globals().calls.text == 0 and 'SECRET' not in json.dumps(result)
    assert all(value is None or type(value) is bool for value in result['checks'].values())


def test_foreign_selected_city_id_is_not_read_and_unknown_getters_are_null():
    v=vm();v.execute('selected.GetOwner=function() return 1 end;selected.GetID=forbidden;UILens.IsLayerOn=forbidden')
    result=read(v)
    assert result['checks']['selected_expected_own_city'] is False
    assert result['checks']['adjacency_layer_on'] is None and 'SECRET' not in str(result)


@pytest.mark.parametrize('mutation', ['ContextPtr.GetID=function() return "Other" end',
    'Game.GetLocalObserver=function() return -1 end','Players[0].IsHuman=function() return false end'])
def test_wrong_context_or_controller_is_rejected(mutation):
    v=vm();v.execute(mutation)
    assert read(v)=={'ok':False,'error':'preview_state_unavailable'}


def test_projection_rejects_unexpected_keys_and_values():
    result=read(vm());result['checks']['arming']='SECRET'
    with pytest.raises(ValueError): probe.project('CIV6FAIR_JSON:'+json.dumps(result))
    result=read(vm());result['checks']['secret']=True
    with pytest.raises(ValueError): probe.project('CIV6FAIR_JSON:'+json.dumps(result))


@pytest.mark.parametrize('fail',[False,True])
def test_runner_makes_one_fixed_read_closes_and_redacts_errors(monkeypatch,fail):
    result=read(vm());calls=[]
    class Fake:
        async def execute(self,source,context):
            calls.append('read');assert context==probe.CONTEXT and source==probe.build_probe()
            if fail: raise RuntimeError('SECRET')
            return 'CIV6FAIR_JSON:'+json.dumps(result)
        async def close(self): calls.append('close')
    monkeypatch.setattr(probe,'FireTunerTransport',Fake)
    answer=asyncio.run(probe.run())
    assert answer['ok'] is not fail and calls==['read','close'] and 'SECRET' not in str(answer)
