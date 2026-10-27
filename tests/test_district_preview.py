"""Offline stock-refresh simulation; no game connection or adjacency calculation."""
import json

import pytest
from lupa import LuaRuntime, LuaError

from civ6_fair_mcp.extensions import registries
from civ6_fair_mcp.extensions.base import LUA_HELPERS
from civ6_fair_mcp.extensions import district_preview as dp
from civ6_fair_mcp.policy import parse_response
from civ6_fair_mcp.inspection_policy import public_inspection
from civ6_fair_mcp.service import FairGameService


CLIENT = 'a' * 32 + ':1'
PARAMS = {'city_id': 7, 'item': 'DISTRICT_CAMPUS'}
BOOT = r'''
flags={visible=true,legal=true,placed=false,owned=true,canproduce=true,layer=false,mode=0,
    turn=88,owner=0,selected=7,render=true,fail=false,label='+2[ICON_Science]',zero=false}
calls={select=0,mode=0,render=0,get=0,text=0,hidden=0,request=0,close=0}
function forbidden() error('SECRET_ADJACENCY') end
function event()
    local e={listeners={}}
    e.Add=function(f) table.insert(e.listeners,f) end
    e.emit=function(...) for _,f in ipairs(e.listeners) do f(...) end end
    return e
end
Events={}
for _,n in ipairs({'InterfaceModeChanged','CitySelectionChanged','CityMadePurchase',
    'LensLayerOff','LoadGameViewStateDone','LocalPlayerChanged'}) do Events[n]=event() end
Game={GetLocalPlayer=function() return flags.owner end,GetLocalObserver=function() return flags.owner end,
    GetCurrentGameTurn=function() return flags.turn end,IsAllowStrategicCommands=function() return true end}
GameConfiguration={IsAnyMultiplayer=function() return false end,IsHotseat=function() return false end,
    IsWorldBuilderEditor=function() return false end}
Automation={IsActive=function() return false end}
ExposedMembers={Civ6FairState={session=string.rep('b',32),player_id=0,last_turn=88,hooks=true}}
function control(parent)
    return {hidden=false,parent=parent,IsVisible=function(self) return not self.hidden end,
        GetParent=function(self) return self.parent end}
end
ContextPtr=control(nil)
ContextPtr.GetID=function() return 'DistrictPlotIconManager' end
ContextPtr.LookUpControl=function() return nil end
Controls={PlotBonusContainer=control(ContextPtr)}
UIManager={GetModalContexts=function() return {} end}
instances={}
function make_instance(id)
    local anchor=control(Controls.PlotBonusContainer)
    local bonus=control(anchor)
    local text=control(bonus)
    text.GetText=function(self)
        calls.text=calls.text+1
        if id>=3 then calls.hidden=calls.hidden+1;error('SECRET_HIDDEN_LABEL') end
        return self.text
    end
    text.GetToolTipString=forbidden
    return {Anchor=anchor,PlotBonus=bonus,BonusText=text}
end
GetInstanceAt=function(id,...)
    calls.get=calls.get+1
    if not instances[id] then instances[id]=make_instance(id) end
    return instances[id],nil,'get-tail'
end
ClearEveything=function(...) return 9,nil,'clear-tail' end
Realize2dArtForCityDistricts=function(city,...)
    calls.render=calls.render+1
    for _,id in ipairs({1,2,3,4}) do
        local instance=GetInstanceAt(id)
        if flags.fail then error('ORIGINAL_RENDER_ERROR') end
        instance.BonusText.text=flags.label..':'..id
        instance.PlotBonus.hidden=flags.zero
    end
    return 5,nil,'realize-tail'
end
original_get=GetInstanceAt;original_realize=Realize2dArtForCityDistricts;original_clear=ClearEveything
row={DistrictType='DISTRICT_CAMPUS',Index=1,Hash=42,RequiresPlacement=true}
GameInfo={Districts={DISTRICT_CAMPUS=row,[42]=row},Buildings={}}
queue={CanProduce=function(self,hash,visible) assert(hash==42 and visible==true);return flags.canproduce end,
    HasBeenPlaced=function() return flags.placed end}
districts={HasDistrict=function() return flags.placed end}
city={GetOwner=function() return flags.owned and 0 or 1 end,GetID=function() return 7 end,
    GetBuildQueue=function() return queue end,GetDistricts=function() return districts end}
selected={GetOwner=function() return flags.owner end,GetID=function() return flags.selected end}
player={GetCities=function() return {Members=function()
    local done=false;return function() if not done then done=true;return 1,city end end
end} end,IsAlive=function() return true end,IsHuman=function() return true end,
    IsTurnActive=function() return true end,IsTurnActiveComplete=function() return true end}
Players={[0]=player}
vis={IsRevealed=function(self,x,y) return x<3 and flags.visible end,
    IsVisible=function(self,x,y) return x<3 and flags.visible end}
PlayersVisibility={[0]=vis}
plots={}
for id=1,4 do
    plots[id]={GetX=function() return id end,GetY=function() return 10 end,
        GetOwner=function() if id>=3 then calls.hidden=calls.hidden+1;error('SECRET_PLOT') end;return 0 end,
        GetAdjacencyYield=forbidden,GetResourceType=forbidden,GetYield=forbidden}
end
Map={GetGridSize=function() return 100,100 end,
    GetCityPlots=function() return {GetPurchasedPlots=function(self,c) assert(c==city);return {1,2,3} end} end,
    GetPlotByIndex=function(id) if id==4 then error('UNPURCHASED_GEOMETRY') end;return plots[id] end,
    GetPlot=function(x,y) assert(y==10 and x<3);return plots[x] end}
CityOperationTypes={BUILD=1,PARAM_DISTRICT_TYPE=2,PARAM_BUILDING_TYPE=3,PARAM_X=4,PARAM_Y=5,
    PARAM_INSERT_MODE=6,VALUE_REPLACE_AT=7,PARAM_QUEUE_DESTINATION_LOCATION=8}
CityOperationResults={PLOTS=1,BLOCKED_PLOTS=2}
CityManager={GetOperationTargets=function(c,op,p) assert(c==city and op==1 and p[2]==42);return {[1]={1,2,3,4},[2]={99}} end,
    CanStartOperation=function(c,op,p,visible)
        assert(c==city and op==1 and p[2]==42 and p[7]==nil and visible==false)
        assert(p[4]<3);return flags.legal or p[4]==1
    end,RequestOperation=forbidden,RequestCommand=forbidden}
InterfaceModeTypes={SELECTION=0,DISTRICT_PLACEMENT=5}
UILens={CreateLensLayerHash=function(s) assert(s=='Adjacency_Bonus_Districts' or s=='Empire_Details');return s=='Empire_Details' and 13 or 12 end,
    IsLayerOn=function(n) assert(n==12);return flags.layer end}
UI={GetHeadSelectedCity=function() return selected end,
    GetInterfaceMode=function() return flags.mode end,
    GetInterfaceModeParameter=function(key) if key==2 then return flags.hash end end,
    IsProcessingMessages=function() return false end,
    SelectCity=function(c)
        assert(c==city);calls.select=calls.select+1;flags.selected=7
        if not flags.defer_selection then Events.CitySelectionChanged.emit(0,7,0,0,0,true,true) end
    end,
    SetInterfaceMode=function(mode,p)
        local old=flags.mode
        calls.mode=calls.mode+1;flags.mode=mode;flags.hash=p and p[2];flags.layer=mode==5
        Events.InterfaceModeChanged.emit(old,mode)
    end}
-- Stock handlers were installed before the observer and reference the global
-- rendering functions dynamically, just like the shipped UI sources.
local function refresh()
    ClearEveything()
    if flags.mode==5 and flags.layer and flags.render then Realize2dArtForCityDistricts(city) end
end
Events.CitySelectionChanged.Add(refresh)
-- CityPanel's normal selection callback resets interface mode. It may be
-- delivered after SelectCity has already changed the selected-city getter.
Events.CitySelectionChanged.Add(function(owner,id,i,j,k,is_selected)
    if owner==0 and is_selected==true then UI.SetInterfaceMode(0) end
end)
Events.InterfaceModeChanged.Add(refresh)
Events.CityMadePurchase.Add(refresh)
LuaEvents={CityPanel_ProductionClose=setmetatable({}, {__call=function() calls.close=calls.close+1 end})}
me=0;turn=88;active_turn=true;session=string.rep('b',32)
preview_client=string.rep('a',32)..':1';preview_nonce='initial-nonce'
'''


def vm():
    result = LuaRuntime(unpack_returned_tuples=True)
    result.execute(BOOT)
    return result


def invoke(v, kind='read'):
    if kind == 'read':
        body = dp.QUERIES[dp.CATEGORY].body(PARAMS)
    else:
        a = {'type': 'district_preview_' + kind, **(PARAMS if kind in ('begin', 'exit_current') else {})}
        if kind=='select_city': a['city_id']=PARAMS['city_id']
        body = dp.ACTIONS[a['type']].body(a)
    return v.execute('out={accepted=false,supported=false,items={}}\n' + LUA_HELPERS
        + '\nlocal function operation()\n' + body + '\nend\noperation()\nreturn out')


def items(result):
    return {r['id']: {k: value for k, value in r.items()} for _, r in result['items'].items()}


def test_begin_read_cancel_observes_only_completed_stock_labels():
    v = vm()
    initial = invoke(v)
    assert initial['supported'] and 'begin' in items(initial)
    assert v.globals().calls.render == 0
    assert invoke(v, 'begin')['accepted']
    result = invoke(v)
    assert result['supported'] and items(result)['plot:1:10']['value'] == '+2[ICON_Science]:1'
    assert items(result)['plot:2:10:x']['value'] == 2
    assert set(items(result)) == {'preview_status', 'cancel', 'plot:1:10', 'plot:1:10:x', 'plot:1:10:y',
                                  'plot:2:10', 'plot:2:10:x', 'plot:2:10:y'}
    assert v.globals().calls.hidden == 0 and v.globals().calls.render == 1
    assert v.globals().calls.get == 4 and v.globals().calls.close == 1
    assert v.globals().calls.select == 0
    assert invoke(v, 'cancel')['accepted']
    assert v.globals().flags.mode == 0
    assert 'plot:1:10' not in items(invoke(v))


@pytest.mark.parametrize('mutation', [
    'flags.owned=false', 'flags.canproduce=false', 'flags.placed=true', 'flags.visible=false',
    'flags.mode=6', 'flags.selected=8', 'row.MustPurchase=true', 'row.InternalOnly=1', 'row.RequiresPlacement=false',
    'row.MustPurchase="unknown"', 'row.InternalOnly="unknown"',
    'CityManager.GetOperationTargets=nil', 'Events.LensLayerOff.Add=nil',
    'GetInstanceAt=nil', 'ContextPtr.GetID=function() return "OtherContext" end',
])
def test_begin_fails_closed_without_ui_mutation(mutation):
    v=vm();v.execute(mutation)
    assert not invoke(v, 'begin')['accepted']
    assert v.globals().calls.select == 0 and v.globals().calls.mode == 0


def test_no_natural_refresh_means_no_cached_or_synthetic_label():
    v=vm();v.execute('flags.render=false;instances[1]=make_instance(1);instances[1].BonusText.text="OLD"')
    assert invoke(v,'begin')['accepted']
    result=invoke(v)
    assert not result['supported'] and items(result)['preview_status']['value']=='awaiting_refresh'
    assert v.globals().calls.get == 0 and v.globals().calls.text == 0
    v.execute('Realize2dArtForCityDistricts(city)')
    assert invoke(v)['supported']


def test_selection_and_begin_are_explicit_separate_actions_with_fresh_event_confirmation():
    v=vm();v.execute('flags.selected=8;flags.defer_selection=true')
    first=items(invoke(v))
    assert 'select_city' in first and 'begin' not in first
    assert invoke(v,'select_city')['accepted']
    assert v.globals().calls.select == 1 and v.globals().calls.mode == 0
    pending=items(invoke(v))
    assert pending['preview_status']['value']=='selection_pending' and 'begin' not in pending
    assert not invoke(v,'begin')['accepted']
    # Delayed CityPanel selection processing restores SELECTION, then the
    # observer only marks completion; it never enters placement itself.
    v.execute('Events.CitySelectionChanged.emit(0,7,0,0,0,true,true)')
    assert v.globals().flags.mode == 0 and v.globals().calls.select == 1
    assert 'begin' in items(invoke(v))
    assert invoke(v,'begin')['accepted'] and invoke(v)['supported']
    assert v.globals().flags.mode == 5 and v.globals().calls.select == 1


def test_select_city_does_not_restart_a_selection_already_current():
    v=vm()
    assert not invoke(v,'select_city')['accepted'] and v.globals().calls.select == 0


def test_pending_selection_can_be_disarmed_without_ui_actions():
    v=vm();v.execute('flags.selected=8;flags.defer_selection=true');invoke(v,'select_city')
    assert invoke(v,'cancel')['accepted']
    assert v.eval('_CIV6FAIR_DISTRICT_PREVIEW.selection==nil')
    assert v.globals().calls.mode == 0 and v.globals().calls.select == 1


def test_late_normal_selection_reset_after_begin_invalidates_without_auto_reopen():
    v=vm();invoke(v,'begin')
    v.execute('Events.CitySelectionChanged.emit(0,7,0,0,0,true,true)')
    assert v.globals().flags.mode == 0 and v.eval('_CIV6FAIR_DISTRICT_PREVIEW.active==nil')
    assert 'plot:1:10' not in items(invoke(v)) and v.globals().calls.select == 0


def test_select_listener_is_added_once_and_reused_with_existing_observer():
    v=vm();invoke(v,'begin');invoke(v,'cancel');v.execute('flags.selected=8')
    assert invoke(v,'select_city')['accepted']
    assert 'begin' in items(invoke(v))
    v.execute('flags.selected=8');assert invoke(v,'select_city')['accepted']
    assert len(v.globals().Events.CitySelectionChanged.listeners)==4


LEGACY_IDLE = r'''
-- The deployed v1 retained originals only in closure locals. Its public
-- contract is a known wrapper triplet and an inactive observer table; no
-- debug/upvalue API is available for migration.
legacy={version=1,serial=0,layer=12,empire_layer=13,events=0}
local native_get,native_realize,native_clear=GetInstanceAt,Realize2dArtForCityDistricts,ClearEveything
legacy.get_wrapper=function(...)
    if legacy.active then error('RETIRED_OBSERVER_CAPTURE') end
    return native_get(...)
end
legacy.realize_wrapper=function(...)
    legacy.pending=nil;legacy.published=nil;legacy.serial=legacy.serial+1
    return native_realize(...)
end
legacy.clear_wrapper=function(...)
    legacy.pending=nil;legacy.published=nil;legacy.serial=legacy.serial+1
    return native_clear(...)
end
Events.CitySelectionChanged.Add(function()
    legacy.events=legacy.events+1;legacy.pending=nil;legacy.published=nil
end)
GetInstanceAt=legacy.get_wrapper;Realize2dArtForCityDistricts=legacy.realize_wrapper;ClearEveything=legacy.clear_wrapper
_CIV6FAIR_DISTRICT_PREVIEW=legacy
'''


def test_same_lua_state_migrates_idle_v1_to_v2_without_replaying_or_double_rendering():
    v=vm();v.execute(LEGACY_IDLE+'\n_G=nil;debug=nil;rawget=nil;unpack=nil;flags.selected=8')
    assert invoke(v,'select_city')['accepted']
    assert v.eval('legacy.retired==true and legacy.active==nil and _CIV6FAIR_DISTRICT_PREVIEW~=legacy')
    assert v.eval('_CIV6FAIR_DISTRICT_PREVIEW.version==2 and _CIV6FAIR_DISTRICT_PREVIEW.legacy_shim==true')
    assert v.eval('_CIV6FAIR_DISTRICT_PREVIEW.original_get==legacy.get_wrapper')
    assert 'begin' in items(invoke(v)) and invoke(v,'begin')['accepted']
    assert invoke(v)['supported'] and v.globals().calls.render == 1 and v.globals().calls.get == 4
    v.execute('saved_v2=GetInstanceAt');invoke(v,'cancel');invoke(v,'begin')
    assert v.eval('saved_v2==GetInstanceAt') and v.globals().calls.render == 2
    assert v.execute('return Realize2dArtForCityDistricts(city)') == (5,None,'realize-tail')


@pytest.mark.parametrize('mutation', ['legacy.version=99','legacy.active={}', 'legacy.pending={}',
    'GetInstanceAt=function() return nil end'])
def test_migration_refuses_unknown_active_or_replaced_observer_without_overwriting(mutation):
    v=vm();v.execute(LEGACY_IDLE+'\n'+mutation+'\nbefore_get=GetInstanceAt')
    assert not invoke(v,'begin')['accepted']
    assert v.eval('GetInstanceAt==before_get and legacy.retired==nil') and v.globals().calls.mode == 0


def test_legacy_active_observer_can_be_explicitly_recovered_then_upgraded():
    v=vm();v.execute(LEGACY_IDLE+'\nlegacy.active={};legacy.pending={};flags.mode=5;flags.hash=42;flags.layer=true')
    assert invoke(v,'exit_current')['accepted']
    assert invoke(v,'begin')['accepted'] and v.eval('_CIV6FAIR_DISTRICT_PREVIEW.version==2')


@pytest.mark.parametrize('stage',['mode','close'])
def test_begin_stage_trace_contains_only_fixed_booleans_and_never_error_text(stage):
    v=vm()
    v.execute('UI.SetInterfaceMode=forbidden' if stage=='mode'
              else 'LuaEvents.CityPanel_ProductionClose=forbidden')
    assert invoke(v,'begin')['accepted']
    trace=v.globals()._CIV6FAIR_DISTRICT_PREVIEW.begin_trace
    assert trace.completed is False and trace.mode_started is True
    assert trace.mode_returned is (stage=='close')
    assert trace.close_started is (stage=='close') and trace.close_returned is False
    assert v.eval('_CIV6FAIR_DISTRICT_PREVIEW.active==nil') and v.globals().calls.select == 0


@pytest.mark.parametrize('mutation', [
    'instances[1].PlotBonus.hidden=true', 'instances[1].Anchor.hidden=true',
    'Controls.PlotBonusContainer.hidden=true', 'ContextPtr.hidden=true',
    'instances[1].BonusText.parent=nil', 'instances[1].PlotBonus.GetParent=nil',
    'instances[1].Anchor.parent=instances[1].BonusText',
])
def test_hidden_or_unprovable_ancestor_never_reads_text(mutation):
    v=vm();invoke(v,'begin');v.execute(mutation)
    result=invoke(v)
    assert 'plot:1:10' not in items(result)
    assert v.globals().calls.text <= 1


@pytest.mark.parametrize('mutation', [
    'flags.turn=89', 'flags.selected=8', 'flags.owner=1', 'flags.mode=0', 'flags.hash=43',
    'flags.layer=false', 'preview_client=string.rep("c",32)..":1"',
    'preview_client=string.rep("a",32)..":2"', 'ExposedMembers.Civ6FairState.session="new-session"',
    'GetInstanceAt=function() error("REPLACED") end',
])
def test_changed_identity_drops_old_labels_before_reading_text(mutation):
    v=vm();invoke(v,'begin');v.execute(mutation)
    assert 'plot:1:10' not in items(invoke(v))
    assert v.globals().calls.text == 0


@pytest.mark.parametrize('event', ['LensLayerOff.emit(12)', 'LensLayerOff.emit(13)', 'LoadGameViewStateDone.emit()', 'LocalPlayerChanged.emit()'])
def test_invalidation_events_remove_even_same_text_batches(event):
    v=vm();invoke(v,'begin');v.execute('Events.'+event)
    assert 'plot:1:10' not in items(invoke(v))
    assert v.globals().calls.text == 0


def test_stock_failure_invalidates_previous_batch_and_propagates():
    v=vm();invoke(v,'begin');v.execute('flags.fail=true')
    with pytest.raises(LuaError, match='ORIGINAL_RENDER_ERROR'):
        v.execute('Realize2dArtForCityDistricts(city)')
    assert 'plot:1:10' not in items(invoke(v))
    assert v.globals().calls.text == 0


def test_wrapper_preserves_nil_holes_and_original_returns_without_global_helpers():
    v=vm();v.execute('_G=nil;rawget=nil;unpack=nil;debug=nil');invoke(v,'begin')
    assert v.execute('return GetInstanceAt(1)')[1:] == (None, 'get-tail')
    assert v.execute('return Realize2dArtForCityDistricts(city)') == (5, None, 'realize-tail')
    assert v.execute('return ClearEveything()') == (9, None, 'clear-tail')


def test_cancel_does_not_close_replacement_interface_and_old_client_cannot_cancel():
    v=vm();invoke(v,'begin');v.execute('flags.mode=999')
    assert invoke(v,'cancel')['accepted']
    assert v.globals().flags.mode == 999 and v.globals().calls.mode == 1
    v=vm();invoke(v,'begin');v.execute('preview_client=string.rep("c",32)..":1"')
    assert not invoke(v,'cancel')['accepted']
    assert v.globals().flags.mode == 5


def test_leave_and_manually_reenter_same_preview_does_not_revive_old_intent():
    v=vm();invoke(v,'begin')
    v.execute('UI.SetInterfaceMode(0);UI.SetInterfaceMode(5,{[2]=42})')
    assert v.eval('_CIV6FAIR_DISTRICT_PREVIEW.active==nil')
    assert 'plot:1:10' not in items(invoke(v)) and v.globals().calls.text == 0


@pytest.mark.parametrize('event', [
    'InterfaceModeChanged.emit(5,0)', 'CitySelectionChanged.emit(0,7,0,0,0,false,true)',
    'CitySelectionChanged.emit(0,8,0,0,0,true,true)', 'CitySelectionChanged.emit(1,7,0,0,0,true,false)',
])
def test_event_declared_exit_beats_stale_getters_and_cannot_revive_on_reentry(event):
    v=vm();invoke(v,'begin')
    # The source event says selection/mode has ended, while its getters retain
    # the previous values until the event dispatch finishes.
    v.execute('Events.'+event)
    assert v.eval('_CIV6FAIR_DISTRICT_PREVIEW.active==nil')
    v.execute('Events.InterfaceModeChanged.emit(0,5);Realize2dArtForCityDistricts(city)')
    assert 'plot:1:10' not in items(invoke(v)) and v.globals().calls.text == 0


def test_new_connection_can_explicitly_exit_orphan_without_reading_old_labels():
    v=vm();invoke(v,'begin');v.execute('preview_client=string.rep("c",32)..":2"')
    result=invoke(v)
    assert 'exit_current' in items(result) and 'plot:1:10' not in items(result)
    assert v.globals().calls.text == 0
    assert invoke(v,'exit_current')['accepted']
    assert v.globals().flags.mode == 0 and v.eval('_CIV6FAIR_DISTRICT_PREVIEW.active==nil')


def test_recovery_does_not_require_observer_or_production_apis():
    v=vm();v.execute('flags.mode=5;flags.hash=42;flags.layer=true;GetInstanceAt=nil;CityManager.GetOperationTargets=nil')
    assert 'exit_current' in items(invoke(v))
    assert invoke(v,'exit_current')['accepted']
    assert v.globals().calls.render == 0 and v.globals().calls.text == 0


@pytest.mark.parametrize('mutation', ['flags.mode=9','flags.owner=1','flags.selected=8','flags.hash=43','flags.layer=false'])
def test_recovery_cannot_escape_other_modes_players_cities_or_districts(mutation):
    v=vm();invoke(v,'begin');v.execute(mutation)
    assert not invoke(v,'exit_current')['accepted']
    assert v.globals().calls.mode == 1


def test_recovery_offer_and_execution_require_no_modal():
    v=vm();invoke(v,'begin');v.execute('preview_client=string.rep("c",32)..":2";UIManager.GetModalContexts=function() return {"NEW"} end')
    assert 'exit_current' not in items(invoke(v))
    output=[];v.globals().print=output.append
    v.execute(dp.build_action('f'*32,{'type':'district_preview_exit_current',**PARAMS},CLIENT,'b'*32,0,88))
    assert not parse_response('\n'.join(output))['accepted'] and v.globals().calls.mode == 1


def test_repeat_begin_is_not_a_wrapper_chain_and_cancel_leaves_inert_hooks():
    v=vm();invoke(v,'begin');wrapper=v.eval('GetInstanceAt');invoke(v,'cancel')
    v.execute('saved_wrapper=GetInstanceAt')
    assert invoke(v,'begin')['accepted'] and v.eval('saved_wrapper==GetInstanceAt')
    invoke(v,'cancel');v.execute('Realize2dArtForCityDistricts(city)')
    assert v.eval('_CIV6FAIR_DISTRICT_PREVIEW.published==nil')
    assert len(v.globals().Events.InterfaceModeChanged.listeners) == 2


def test_candidate_revalidation_filters_new_fog_or_illegal_target_and_zero_is_unknown():
    v=vm();invoke(v,'begin');v.execute('flags.legal=false')
    assert 'plot:2:10' not in items(invoke(v))
    v.execute('flags.visible=false')
    assert 'plot:1:10' not in items(invoke(v))
    v=vm();v.execute('flags.zero=true');invoke(v,'begin')
    assert set(items(invoke(v))) == {'preview_status','cancel'}
    assert v.globals().calls.text == 0


def test_pooled_instance_duplicate_binding_rejects_entire_batch():
    v=vm();v.execute('instances[1]=make_instance(1);instances[2]=instances[1]');invoke(v,'begin')
    assert not invoke(v)['supported'] and v.globals().calls.text == 0


def test_purchase_refresh_after_listener_order_keeps_only_new_batch():
    v=vm();invoke(v,'begin');v.execute('flags.label="+7";Events.CityMadePurchase.emit()')
    assert items(invoke(v))['plot:1:10']['value'] == '+7:1'


def test_native_float_geometry_and_ids_are_normalized_to_integer_output():
    v=vm();v.execute('plots[1].GetX=function() return 1.0 end;plots[1].GetY=function() return 10.0 end')
    invoke(v,'begin');result=items(invoke(v))
    assert type(result['plot:1:10:x']['value']) is int


def test_full_wrapped_action_read_and_cleanup_restore_only_the_owned_preview():
    v=vm();output=[];v.globals().print=output.append
    script=dp.build_action('f'*32,{'type':'district_preview_begin',**PARAMS},CLIENT,'b'*32,0,88)
    v.execute(script)
    assert parse_response('\n'.join(output))['accepted']
    output.clear();v.execute(dp.build_read('e'*32,PARAMS,CLIENT))
    raw=parse_response('\n'.join(output));public=public_inspection(raw,dp.CATEGORY)
    assert public['supported'] and any(i['id']=='plot:1:10' for i in public['items'])
    output.clear();v.execute(dp.build_cleanup('d'*32,CLIENT))
    assert v.eval('_CIV6FAIR_DISTRICT_PREVIEW.active==nil') and v.globals().calls.mode == 2
    assert v.globals().flags.mode == 0


@pytest.mark.parametrize('mutation', [
    'flags.mode=99', 'flags.turn=89', 'flags.selected=8', 'flags.hash=43',
    'UIManager.GetModalContexts=function() return {"NEW_MODAL"} end',
    'UI.IsProcessingMessages=function() return true end',
])
def test_cleanup_disarms_but_does_not_change_new_or_unready_ui(mutation):
    v=vm();invoke(v,'begin');v.execute(mutation);v.globals().print=lambda *_:None
    v.execute(dp.build_cleanup('d'*32,CLIENT))
    assert v.eval('_CIV6FAIR_DISTRICT_PREVIEW.active==nil') and v.globals().calls.mode == 1


@pytest.mark.parametrize('client', ['x','a'*32, 'a'*32+':-1', 'a'*32+':1;evil()'])
def test_internal_identity_is_not_a_lua_escape_hatch(client):
    with pytest.raises(ValueError): dp.build_read('e'*32,PARAMS,client)


def raw(**extra):
    return {'ok':True,'session':'b'*32,'player_id':0,'turn':88,'active_turn':True,**extra}


class Transport:
    connection_generation=1
    def __init__(self,*responses): self.responses=list(responses);self.calls=[];self.closed=False
    async def execute(self,script,context='InGame',*,expected_generation=None):
        assert expected_generation is None or expected_generation==self.connection_generation
        self.calls.append((context,script))
        value=self.responses.pop(0)
        if isinstance(value,Exception): raise value
        return 'CIV6FAIR_JSON:'+json.dumps(value)+'\n---END---'
    async def close(self): self.closed=True;self.connection_generation+=1


async def test_service_routes_preview_and_binds_ui_envelope_before_issuing_action_token():
    transport=Transport(raw(),raw(category=dp.CATEGORY,supported=True,items=[]),raw(accepted=True),raw())
    service=FairGameService(transport)
    result=await service.inspect_game(dp.CATEGORY,PARAMS)
    assert result['supported'] and result['observation_token']
    response=await service.act(result['observation_token'],{'type':'district_preview_begin',**PARAMS})
    assert response['accepted']
    assert [c[0] for c in transport.calls]==['InGame',dp.CONTEXT,dp.CONTEXT]
    key=service._preview_identity(1)
    assert key in transport.calls[1][1] and key in transport.calls[2][1]
    await service.close()
    assert transport.calls[-1][0]==dp.CONTEXT and transport.closed
    assert 'local function cleanup()' in transport.calls[-1][1]


async def test_service_rejects_cross_turn_fixed_context_result():
    transport=Transport(raw(),raw(turn=89,category=dp.CATEGORY,supported=True,items=[]))
    service=FairGameService(transport)
    assert (await service.inspect_game(dp.CATEGORY,PARAMS))['ok'] is False
    assert transport.closed and service._observation is None


async def test_service_uses_ingame_popup_metadata_not_fixed_context_metadata():
    base=raw(popup_keys=[],native_modal_keys=[],native_modal_present=False,
             unknown_modal_present=False,modal_monitor_available=True,ui_monitor_available=True,turn_blockers=[])
    transport=Transport(base,raw(category=dp.CATEGORY,supported=False,items=[]))
    transport.supports_ui_contexts=True
    result=await FairGameService(transport).inspect_game(dp.CATEGORY,PARAMS)
    assert result['ok'] and result['ui']['status']=='ready' and result['observation_token']
    assert len(transport.calls)==2


async def test_wait_repeats_fixed_context_read_without_opening_or_refreshing_ui():
    first=raw(category=dp.CATEGORY,supported=False,items=[])
    changed=raw(category=dp.CATEGORY,supported=True,items=[{'id':'preview_status',
        'value':'visible_labels','scope':'self','owner_id':0}])
    transport=Transport(raw(),first,raw(),changed)
    service=FairGameService(transport)
    await service.inspect_game(dp.CATEGORY,PARAMS)
    result=await service.wait_for_change(1000)
    assert result['supported'] and result['observation_token']
    assert [context for context,_ in transport.calls]==['InGame',dp.CONTEXT,'InGame',dp.CONTEXT]
    assert all('UI.SelectCity(city)' not in source for _,source in transport.calls)


def test_registry_and_transport_allow_only_fixed_context():
    from civ6_fair_mcp.transport import _CONTEXTS
    actions,queries=registries()
    assert dp.CONTEXT in _CONTEXTS
    assert actions['district_preview_begin'].fields==dp.FIELDS
    assert queries[dp.CATEGORY].fields==dp.FIELDS
