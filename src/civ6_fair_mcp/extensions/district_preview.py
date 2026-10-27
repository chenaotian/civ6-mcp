"""Observe literal stock district-placement labels in one fixed UI context.

The observer never requests a refresh, calls an adjacency getter, inspects an
upvalue, or reads a tooltip. Only naturally completed stock rendering batches
can publish bindings. UI mutations are restricted to explicit begin/cancel.
"""
from __future__ import annotations

from .base import ActionSpec, QuerySpec, LUA_HELPERS, lua, validate
from ..lua_common import wrap

CONTEXT = "DistrictPlotIconManager"
CATEGORY = "district_preview"
FIELDS = {"city_id": "id", "item": "identifier:DISTRICT_"}


HELPERS = r'''
local function dp_integer(v, maximum)
    return type(v)=='number' and v==v and v>=0 and v<=maximum and v%1==0
end
local function dp_flag(v) return v==true or v==1 end
local function dp_false(v) return v==nil or v==false or v==0 end
local function dp_context()
    if not ContextPtr or type(ContextPtr.GetID)~='function' then return false end
    local id=ContextPtr:GetID()
    return id=='DistrictPlotIconManager' or id=='DistrictPlotIconManager.xml'
end
local function dp_selected(city_id)
    if not UI or type(UI.GetHeadSelectedCity)~='function' then return false end
    local city=UI.GetHeadSelectedCity()
    return city~=nil and city:GetOwner()==me and city:GetID()==city_id
end
local function dp_selection_pending(s,city_id)
    local p=s and s.selection
    return p and p.client==preview_client and p.session==session and p.player==me
        and p.turn==turn and p.city_id==city_id and p.seen~=true
end
local function dp_current_ui(city_id,item)
    if not dp_context() or not UI or type(UI.GetHeadSelectedCity)~='function'
        or type(UI.GetInterfaceMode)~='function' or type(UI.GetInterfaceModeParameter)~='function'
        or type(UI.SetInterfaceMode)~='function' or not InterfaceModeTypes
        or type(InterfaceModeTypes.DISTRICT_PLACEMENT)~='number'
        or type(InterfaceModeTypes.SELECTION)~='number' or not CityOperationTypes
        or CityOperationTypes.PARAM_DISTRICT_TYPE==nil or CityOperationTypes.PARAM_BUILDING_TYPE==nil
        or not UILens or type(UILens.IsLayerOn)~='function' or type(UILens.CreateLensLayerHash)~='function'
        or not GameInfo or not GameInfo.Districts or not GameInfo.Buildings
        or UI.GetInterfaceMode()~=InterfaceModeTypes.DISTRICT_PLACEMENT then return false end
    local row=GameInfo.Districts[item]
    if not row or row.DistrictType~=item or not dp_flag(row.RequiresPlacement)
        or type(row.Hash)~='number'
        or UI.GetInterfaceModeParameter(CityOperationTypes.PARAM_DISTRICT_TYPE)~=row.Hash then return false end
    local building=UI.GetInterfaceModeParameter(CityOperationTypes.PARAM_BUILDING_TYPE)
    if building~=nil and GameInfo.Buildings[building]~=nil then return false end
    local selected=UI.GetHeadSelectedCity()
    if not selected or selected:GetOwner()~=me or selected:GetID()~=city_id
        or not find_owned('Cities',city_id) then return false end
    local layer=UILens.CreateLensLayerHash('Adjacency_Bonus_Districts')
    return type(layer)=='number' and UILens.IsLayerOn(layer)==true
end
local function dp_capabilities()
    if not dp_context() or type(GetInstanceAt)~='function'
        or type(Realize2dArtForCityDistricts)~='function' or type(ClearEveything)~='function'
        or not UI or type(UI.GetHeadSelectedCity)~='function'
        or type(UI.GetInterfaceMode)~='function' or type(UI.GetInterfaceModeParameter)~='function'
        or type(UI.SelectCity)~='function' or type(UI.SetInterfaceMode)~='function'
        or not UILens or type(UILens.CreateLensLayerHash)~='function' or type(UILens.IsLayerOn)~='function'
        or not Controls or not Controls.PlotBonusContainer
        or type(ContextPtr.IsVisible)~='function' or type(ContextPtr.GetParent)~='function'
        or type(Controls.PlotBonusContainer.IsVisible)~='function'
        or type(Controls.PlotBonusContainer.GetParent)~='function'
        or not InterfaceModeTypes or type(InterfaceModeTypes.DISTRICT_PLACEMENT)~='number'
        or type(InterfaceModeTypes.SELECTION)~='number'
        or not CityOperationTypes or not CityOperationResults
        or CityOperationTypes.PARAM_DISTRICT_TYPE==nil or CityOperationTypes.PARAM_BUILDING_TYPE==nil
        or CityOperationTypes.PARAM_X==nil or CityOperationTypes.PARAM_Y==nil
        or CityOperationTypes.PARAM_INSERT_MODE==nil or CityOperationTypes.VALUE_REPLACE_AT==nil
        or CityOperationTypes.PARAM_QUEUE_DESTINATION_LOCATION==nil
        or CityOperationResults.PLOTS==nil or type(CityOperationTypes.BUILD)~='number'
        or not CityManager or type(CityManager.GetOperationTargets)~='function'
        or type(CityManager.CanStartOperation)~='function'
        or not Map or type(Map.GetCityPlots)~='function' or type(Map.GetPlotByIndex)~='function'
        or not GameInfo or not GameInfo.Districts or not GameInfo.Buildings then return false end
    for _, name in ipairs({'InterfaceModeChanged','CitySelectionChanged','CityMadePurchase',
        'LensLayerOff','LoadGameViewStateDone','LocalPlayerChanged'}) do
        if not Events or not Events[name] or type(Events[name].Add)~='function' then return false end
    end
    return true
end
local function dp_candidates(city_id, item)
    local city=find_owned('Cities',city_id)
    if not city then return nil end
    local row=GameInfo.Districts[item]
    if not row or row.DistrictType~=item or not dp_integer(row.Index,2147483647)
        or type(row.Hash)~='number' or row.Hash~=row.Hash or row.Hash%1~=0
        or not dp_flag(row.RequiresPlacement) or not dp_false(row.InternalOnly)
        or not dp_false(row.MustPurchase) then return nil end
    local queue=city:GetBuildQueue()
    local districts=city:GetDistricts()
    if not queue or type(queue.CanProduce)~='function' or type(queue.HasBeenPlaced)~='function'
        or not districts or type(districts.HasDistrict)~='function'
        or queue:CanProduce(row.Hash,true)~=true or queue:HasBeenPlaced(row.Hash)~=false
        or districts:HasDistrict(row.Index)~=false then return nil end
    local target_params={[CityOperationTypes.PARAM_DISTRICT_TYPE]=row.Hash}
    local targets=CityManager.GetOperationTargets(city,CityOperationTypes.BUILD,target_params)
    local candidates=targets and targets[CityOperationResults.PLOTS]
    local city_plots=Map.GetCityPlots()
    if type(candidates)~='table' or not city_plots or type(city_plots.GetPurchasedPlots)~='function' then return nil end
    local purchased=city_plots:GetPurchasedPlots(city)
    if type(purchased)~='table' then return nil end
    local owned, allowed={},{}
    local n=0
    for _, id in pairs(purchased) do
        n=n+1;if n>4096 or not dp_integer(id,2147483647) then return nil end
        owned[id]=true
    end
    n=0
    for _, id in pairs(candidates) do
        n=n+1;if n>4096 or not dp_integer(id,2147483647) then return nil end
        if owned[id] then
            -- Geometry is from this city's own purchased-plot list. All other
            -- target getters and current-constraint checks follow visibility.
            local geometry=Map.GetPlotByIndex(id)
            if geometry then
                local x,y=geometry:GetX(),geometry:GetY()
                if dp_integer(x,4095) and dp_integer(y,4095) then
                    local plot=visible_plot(x,y)
                    if plot and plot:GetOwner()==me then
                        local p={[CityOperationTypes.PARAM_DISTRICT_TYPE]=row.Hash,
                            [CityOperationTypes.PARAM_INSERT_MODE]=CityOperationTypes.VALUE_REPLACE_AT,
                            [CityOperationTypes.PARAM_QUEUE_DESTINATION_LOCATION]=0,
                            [CityOperationTypes.PARAM_X]=x,[CityOperationTypes.PARAM_Y]=y}
                        if CityManager.CanStartOperation(city,CityOperationTypes.BUILD,p,false)==true then
                            allowed[math.floor(id)]={x=math.floor(x),y=math.floor(y)}
                        end
                    end
                end
            end
        end
    end
    return city,row,allowed
end
local function dp_identity(s, require_lens)
    local a=s and s.active
    if not a or not ExposedMembers or not ExposedMembers.Civ6FairState
        or ExposedMembers.Civ6FairState.session~=a.session
        or Game.GetLocalPlayer()~=a.player or Game.GetLocalObserver()~=a.player
        or Game.GetCurrentGameTurn()~=a.turn
        or UI.GetInterfaceMode()~=InterfaceModeTypes.DISTRICT_PLACEMENT
        or UI.GetInterfaceModeParameter(CityOperationTypes.PARAM_DISTRICT_TYPE)~=a.hash then return false end
    local building=UI.GetInterfaceModeParameter(CityOperationTypes.PARAM_BUILDING_TYPE)
    if building~=nil and GameInfo.Buildings and GameInfo.Buildings[building]~=nil then return false end
    local selected=UI.GetHeadSelectedCity()
    if not selected or selected:GetOwner()~=a.player or selected:GetID()~=a.city_id then return false end
    return not require_lens or UILens.IsLayerOn(s.layer)==true
end
local function dp_clear(s)
    s.pending=nil;s.published=nil;s.serial=s.serial+1
end
local function dp_stop(s)
    if s then dp_clear(s);s.active=nil end
end
local function dp_install()
    local s=_CIV6FAIR_DISTRICT_PREVIEW
    local original_get=GetInstanceAt
    local original_realize=Realize2dArtForCityDistricts
    local original_clear=ClearEveything
    local legacy_shim=false
    if s~=nil then
        if type(s)~='table' or GetInstanceAt~=s.get_wrapper
            or Realize2dArtForCityDistricts~=s.realize_wrapper
            or ClearEveything~=s.clear_wrapper then return nil end
        if s.version==2 then return s end
        if s.version~=1 or s.active~=nil or s.pending~=nil then return nil end
        -- The shipped v1 kept native originals only in its Lua closures. Do
        -- not inspect upvalues/reload UI scripts to recover them. Retire its
        -- exact, recognized wrapper triplet as one inert forwarding layer.
        -- Original functions still run exactly once. From v2 onward explicit
        -- base references permit later upgrades without more wrapper layers.
        if type(s.original_get)=='function' and type(s.original_realize)=='function'
            and type(s.original_clear)=='function' then
            original_get=s.original_get;original_realize=s.original_realize;original_clear=s.original_clear
            legacy_shim=s.legacy_shim==true
        else legacy_shim=true end
        s.active=nil;s.pending=nil;s.published=nil;s.selection=nil;s.retired=true
    end
    s={version=2,serial=0,layer=UILens.CreateLensLayerHash('Adjacency_Bonus_Districts'),
        empire_layer=UILens.CreateLensLayerHash('Empire_Details'),legacy_shim=legacy_shim,
        original_get=original_get,original_realize=original_realize,original_clear=original_clear}
    if type(s.layer)~='number' or type(s.empire_layer)~='number' then return nil end
    local function capture(instance, plot_id)
        local b=s.pending
        if not b or not s.active or b.active~=s.active or not dp_identity(s,true) then return end
        if not dp_integer(plot_id,2147483647) or not s.active.allowed[plot_id] then return end
        if not instance or not instance.BonusText or not instance.PlotBonus or not instance.Anchor then
            b.invalid=true;return
        end
        -- Pool reuse must never bind the same current instance to two plots.
        if b.instances[instance] and b.instances[instance]~=plot_id then b.invalid=true;return end
        b.instances[instance]=plot_id;b.bindings[math.floor(plot_id)]=instance
    end
    s.get_wrapper=function(plot_id,...)
        local function after(...)
            local instance=(...)
            local ok=pcall(capture,instance,plot_id)
            if not ok then dp_clear(s) end
            return ...
        end
        return after(original_get(plot_id,...))
    end
    s.realize_wrapper=function(city,...)
        -- Invalidate BEFORE calling the renderer: a stock error cannot leave
        -- the previous text available. Original errors and nil return holes
        -- propagate unchanged; no pack/unpack/debug/rawget dependency.
        dp_clear(s)
        local b=nil
        local ok, matches=pcall(function()
            return dp_identity(s,true) and city and city:GetOwner()==s.active.player
                and city:GetID()==s.active.city_id
        end)
        if ok and matches then
            b={active=s.active,serial=s.serial,bindings={},instances={}}
            s.pending=b
        end
        local function after(...)
            local success=pcall(function()
                if b and s.pending==b and not b.invalid and s.active==b.active
                    and s.serial==b.serial and dp_identity(s,true) then s.published=b end
                s.pending=nil
            end)
            if not success then dp_clear(s) end
            return ...
        end
        return after(original_realize(city,...))
    end
    s.clear_wrapper=function(...)
        dp_clear(s)
        return original_clear(...)
    end
    -- Retain inert wrappers after cancellation; never replace the stock
    -- shutdown handler or restore over a later third-party function wrapper.
    -- These listeners have no UI effects and hold no active data after stop.
    local function stop() dp_stop(s) end
    local function changed()
        local ok, matches=pcall(dp_identity,s,false)
        if not ok or not matches then
            if s.arming then dp_clear(s) else dp_stop(s) end
        end
    end
    local function declared_exit()
        if s.arming then dp_clear(s) else dp_stop(s) end
    end
    local function mode_changed(old_mode,new_mode)
        -- Events may announce a change before selection/mode getters update.
        if type(new_mode)=='number' and new_mode~=InterfaceModeTypes.DISTRICT_PLACEMENT then
            declared_exit();return
        end
        changed()
    end
    local function city_changed(owner,id,i,j,k,is_selected,is_editable)
        local a=s.active
        if a and ((is_selected==false and owner==a.player and id==a.city_id)
            or (is_selected==true and (owner~=a.player or id~=a.city_id))) then
            declared_exit();return
        end
        changed()
    end
    local function lens_off(layer)
        -- Stock OnLensLayerOff releases this same pool for either layer.
        if layer==s.layer or layer==s.empire_layer then declared_exit() end
    end
    -- Stock selection/purchase handlers call ClearEveything before their
    -- refresh; our wrapper invalidates synchronously there. A listener that
    -- runs after that successful refresh must not erase its new batch.
    Events.InterfaceModeChanged.Add(mode_changed)
    Events.CitySelectionChanged.Add(city_changed)
    Events.CityMadePurchase.Add(changed)
    Events.LensLayerOff.Add(lens_off)
    Events.LoadGameViewStateDone.Add(stop)
    Events.LocalPlayerChanged.Add(stop)
    GetInstanceAt=s.get_wrapper
    Realize2dArtForCityDistricts=s.realize_wrapper
    ClearEveything=s.clear_wrapper
    _CIV6FAIR_DISTRICT_PREVIEW=s
    return s
end
local function dp_watch_selection(s)
    if s.selection_hook then return end
    -- A getter can update before CityPanel consumes its selection event and
    -- resets interface mode. Observe that normal event; never enter placement
    -- or perform any UI action from this callback.
    local function selected(owner,id,i,j,k,is_selected,is_editable)
        pcall(function()
            local p=s.selection
            if p and is_selected==true and owner==p.player and id==p.city_id
                and Game.GetLocalPlayer()==p.player and Game.GetCurrentGameTurn()==p.turn
                and ExposedMembers and ExposedMembers.Civ6FairState
                and ExposedMembers.Civ6FairState.session==p.session then p.seen=true end
        end)
    end
    Events.CitySelectionChanged.Add(selected)
    s.selection_hook=true
end
local function dp_visible(instance)
    local control=instance.BonusText
    local seen, bonus, anchor, container={},false,false,false
    for _=1,32 do
        if not control or seen[control] or type(control.IsVisible)~='function'
            or control:IsVisible()~=true or type(control.GetParent)~='function' then return false end
        seen[control]=true
        if control==instance.PlotBonus then bonus=true end
        if control==instance.Anchor then anchor=true end
        if control==Controls.PlotBonusContainer then container=true end
        if control==ContextPtr then return bonus and anchor and container end
        control=control:GetParent()
    end
    return false
end
'''


def _begin(a: dict) -> str:
    return HELPERS + f'''
if type(preview_client)~='string' or type(preview_nonce)~='string' or not dp_capabilities() then return end
if UI.GetInterfaceMode()~=InterfaceModeTypes.SELECTION then return end
if not dp_selected({a['city_id']}) or dp_selection_pending(_CIV6FAIR_DISTRICT_PREVIEW,{a['city_id']}) then return end
if type(Game.IsAllowStrategicCommands)~='function' or Game.IsAllowStrategicCommands(me)~=true then return end
if not LuaEvents or (type(LuaEvents.CityPanel_ProductionClose)~='table'
    and type(LuaEvents.CityPanel_ProductionClose)~='function') then return end
local city,row,allowed=dp_candidates({a['city_id']},{lua(a['item'])})
if not city or next(allowed)==nil then return end
local s=dp_install()
if not s then return end
dp_stop(s)
s.selection=nil
s.active={{client=preview_client,nonce=preview_nonce,session=session,player=me,turn=turn,
    city_id={a['city_id']},item={lua(a['item'])},hash=row.Hash,allowed=allowed}}
s.begin_trace={{player=me,turn=turn,mode_started=false,mode_returned=false,
    close_started=false,close_returned=false,completed=false}}
local p={{[CityOperationTypes.PARAM_DISTRICT_TYPE]=row.Hash,
    [CityOperationTypes.PARAM_INSERT_MODE]=CityOperationTypes.VALUE_REPLACE_AT,
    [CityOperationTypes.PARAM_QUEUE_DESTINATION_LOCATION]=0}}
-- Normal stock UI entry, never RequestOperation/RequestCommand or a direct
-- call to any rendering function. A partial UI failure is never retried.
out.accepted=true
s.arming=true
local ok=pcall(function()
    s.begin_trace.mode_started=true
    UI.SetInterfaceMode(InterfaceModeTypes.DISTRICT_PLACEMENT,p)
    s.begin_trace.mode_returned=true
    s.begin_trace.close_started=true
    LuaEvents.CityPanel_ProductionClose()
    s.begin_trace.close_returned=true
end)
s.begin_trace.completed=ok
s.arming=false
if not ok then dp_stop(s) end
'''


def _select_city(a: dict) -> str:
    return HELPERS + f'''
if type(preview_client)~='string' or not dp_capabilities()
    or UI.GetInterfaceMode()~=InterfaceModeTypes.SELECTION then return end
local city=find_owned('Cities',{a['city_id']})
if not city or dp_selected({a['city_id']}) then return end
local s=dp_install()
if not s then return end
dp_stop(s)
dp_watch_selection(s)
s.selection={{client=preview_client,session=session,player=me,turn=turn,city_id={a['city_id']},seen=false}}
out.accepted=true
local ok=pcall(UI.SelectCity,city)
if not ok then s.selection=nil end
'''


def _cancel(a: dict) -> str:
    return HELPERS + '''
if not dp_context() then return end
local s=_CIV6FAIR_DISTRICT_PREVIEW
if not s then return end
local pending=s.selection and s.selection.client==preview_client
if pending then s.selection=nil end
if not s.active or s.active.client~=preview_client then
    if pending then out.accepted=true end
    return
end
local ok, matches=pcall(dp_identity,s,true)
dp_stop(s)
-- A player may already have opened an unrelated interface. Disarm only;
-- never close it or reset its selection on behalf of the old preview.
if ok and matches then
    out.accepted=true
    pcall(UI.SetInterfaceMode,InterfaceModeTypes.SELECTION)
else out.accepted=true end
'''


def _exit_current(a: dict) -> str:
    return HELPERS + f'''
-- Independent recovery: fresh normal UI identity, not a stale observer nonce.
-- No label reads, renderer calls, or adoption of the previous connection's data.
if not dp_current_ui({a['city_id']},{lua(a['item'])}) then return end
local s=_CIV6FAIR_DISTRICT_PREVIEW
if type(s)=='table' and (s.version==1 or s.version==2) then dp_stop(s) end
out.accepted=true
pcall(UI.SetInterfaceMode,InterfaceModeTypes.SELECTION)
'''


def _read(a: dict) -> str:
    from ..actions import _TURN_GUARD, _non_ui_modal_guard
    recovery = '''local function can_exit_current()
if not UIManager or type(UIManager.GetModalContexts)~='function' then return end
''' + _TURN_GUARD + _non_ui_modal_guard('district_preview_exit_current', require_capabilities=True)
    recovery += f"return dp_current_ui({a['city_id']},{lua(a['item'])})\nend\n"
    return HELPERS + recovery + f'''
out.supported=false
if type(preview_client)~='string' or not dp_context() then return end
local function status(value)
    add_item({{id='preview_status',value=value,scope='self',owner_id=me}})
end
local s=_CIV6FAIR_DISTRICT_PREVIEW
local a=s and s.active
local ours=a and a.client==preview_client and a.session==session and a.player==me and a.turn==turn
    and a.city_id=={a['city_id']} and a.item=={lua(a['item'])}
if not ours and can_exit_current()==true then
    add_item({{id='exit_current',description='正常取消当前本方区域选址；不读取或继承旧预览标签。',
        scope='self',owner_id=me,action={lua({'type':'district_preview_exit_current',**a})}}})
end
if not dp_capabilities() then return end
local city,row,allowed=dp_candidates({a['city_id']},{lua(a['item'])})
if not city then return end
if not a or a.client~=preview_client or a.session~=session or a.player~=me or a.turn~=turn
    or a.city_id~={a['city_id']} or a.item~={lua(a['item'])} then
    out.supported=true
    if dp_selection_pending(s,{a['city_id']}) then
        status('selection_pending')
        add_item({{id='cancel',scope='self',owner_id=me,action={{type='district_preview_cancel'}}}})
        return
    end
    status('not_active')
    if active_turn and type(Game.IsAllowStrategicCommands)=='function' and Game.IsAllowStrategicCommands(me)==true
        and UI.GetInterfaceMode()==InterfaceModeTypes.SELECTION and next(allowed)~=nil then
        if dp_selected({a['city_id']}) then
            add_item({{id='begin',description='为当前已选城市显式打开原版区域选址；不重新选城或提交建造。',scope='self',owner_id=me,
                action={lua({'type':'district_preview_begin',**a})}}})
        else
            add_item({{id='select_city',description='正常选择本方目标城市；会改变当前选城。观察选城完成后再单独开启预览。',scope='self',owner_id=me,
                action={lua({'type':'district_preview_select_city','city_id':a['city_id']})}}})
        end
    end
    return
end
if not dp_identity(s,true) or GetInstanceAt~=s.get_wrapper
    or Realize2dArtForCityDistricts~=s.realize_wrapper or ClearEveything~=s.clear_wrapper then
    status('unavailable');return
end
add_item({{id='cancel',scope='self',owner_id=me,action={{type='district_preview_cancel'}}}})
local b=s.published
if not b or b.active~=a or b.serial~=s.serial then status('awaiting_refresh');return end
-- Stage the complete result. Any uncertain ancestry/read invalidates this
-- response instead of returning a partial mixture of generations.
local rows={{}}
for id, instance in pairs(b.bindings) do
    local p=allowed[id]
    local initial=a.allowed[id]
    if p and initial and p.x==initial.x and p.y==initial.y then
        local ok, shown=pcall(dp_visible,instance)
        if not ok then return end
        if shown then
            if type(instance.BonusText.GetText)~='function' then return end
            local text_ok,text=pcall(instance.BonusText.GetText,instance.BonusText)
            if not text_ok or type(text)~='string' or #text>2048 or text:find('%z') then return end
            if text~='' then table.insert(rows,{{id='plot:'..p.x..':'..p.y,value=text,
                description='原版当前可见相邻加成标签；缺失标签不代表零。',scope='visible',
                x=p.x,y=p.y,visible=true}}) end
        end
    end
end
if s.published~=b or s.active~=a or not dp_identity(s,true) then return end
out.supported=true;status('visible_labels')
for _, row in ipairs(rows) do
    add_item(row)
    add_item({{id=row.id..':x',value=row.x,scope='visible',x=row.x,y=row.y,visible=true}})
    add_item({{id=row.id..':y',value=row.y,scope='visible',x=row.x,y=row.y,visible=true}})
end
'''


ACTIONS = {
    "district_preview_select_city": ActionSpec({"city_id":"id"}, _select_city, "Explicitly select the own city first. Observe its normal selection event before a separate begin; never opens placement automatically."),
    "district_preview_begin": ActionSpec(FIELDS, _begin, "Explicitly open stock district placement and observe naturally drawn labels. Own visible purchased build candidates only; does not construct anything."),
    "district_preview_cancel": ActionSpec({}, _cancel, "Disarm this client's preview; return to selection only if its exact city/district/mode/lens is still active."),
    "district_preview_exit_current": ActionSpec(FIELDS, _exit_current, "Explicit recovery after a disconnected preview: cancel only the currently selected own city's matching district placement, with no modal. Never reads or revives old labels."),
}
QUERIES = {CATEGORY: QuerySpec(FIELDS, _read, "Stock visible placement labels for this client's explicit preview. Use select_city if offered, observe selection completion, then submit begin and read again. Missing/hidden labels are unknown, never zero. Excludes unpurchased plots and wonders.")}


def _client(value: str) -> str:
    # Internal unguessable service identity plus connection generation.
    import re
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{32}:[0-9]{1,16}", value):
        raise ValueError("invalid internal preview identity")
    return lua(value)


def build_read(nonce: str, params: dict, client: str) -> str:
    params = validate(params, FIELDS)
    return wrap(f'local preview_client={_client(client)}\nout.category={lua(CATEGORY)}\n'
                'out.supported=false\nout.items=array({})\n' + LUA_HELPERS
                + '\nlocal function collect()\n' + _read(params) + '\nend\ncollect()\n',
                nonce, shared_context=True)


def build_action(nonce: str, action: dict, client: str, session: str, player: int, turn: int) -> str:
    from ..actions import _TURN_GUARD, _non_ui_modal_guard, validate_action
    action = validate_action(action)
    spec = ACTIONS.get(action['type'])
    if spec is None:
        raise ValueError('invalid preview action')
    validate(player, 'id'); validate(turn, 'id')
    if type(session) is not str or not 1 <= len(session) <= 256:
        raise ValueError('invalid session')
    body = f'''local preview_client={_client(client)}
local preview_nonce={lua(nonce)}
out.accepted=false
local function perform()
if session~={lua(session)} or me~={player} or turn~={turn} then return end
if not UIManager or type(UIManager.GetModalContexts)~='function' then return end
''' + _TURN_GUARD + _non_ui_modal_guard(action['type'], require_capabilities=True)
    return wrap(body + LUA_HELPERS + spec.body(action) + '\nend\nperform()\n', nonce,
                shared_context=True, observation_activity=False)


def build_cleanup(nonce: str, client: str) -> str:
    # Normal shutdown may undo exactly the UI preview this connection opened.
    # Unknown/out-of-date outcome paths never call this or retry a UI mutation.
    from ..actions import _TURN_GUARD, _non_ui_modal_guard
    body = f'local preview_client={_client(client)}\n' + HELPERS + '''
local function cleanup()
    if not dp_context() then return end
    local s=_CIV6FAIR_DISTRICT_PREVIEW
    if type(s)~='table' or (s.version~=1 and s.version~=2) then return end
    if s.selection and s.selection.client==preview_client then s.selection=nil end
    if not s.active or s.active.client~=preview_client then return end
    local ok,matches=pcall(dp_identity,s,true)
    dp_stop(s)
    if not ok or not matches then return end
    if not UIManager or type(UIManager.GetModalContexts)~='function' then return end
''' + _TURN_GUARD + _non_ui_modal_guard('district_preview_cancel', require_capabilities=True) + '''
    pcall(UI.SetInterfaceMode,InterfaceModeTypes.SELECTION)
end
cleanup()
'''
    return wrap(body, nonce, shared_context=True, observation_activity=False)
