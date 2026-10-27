"""Normal unit requests from shipped UnitPanel/WorldInput/chooser scripts.

Operation names are a reviewed whitelist, never arbitrary engine enums. Target
inspection uses visibility or audited stock menu eligibility; no raw path list is exposed.
"""
from __future__ import annotations

from .base import ActionSpec, QuerySpec, lua, own_city, own_unit
from . import trade_menus, spy_menus
from .unit_labels import UNIT_LABEL_HELPERS
from .queued_destination import QUEUED_DESTINATION_OBSERVATION


# Operations without an interface mode use no parameters in UnitPanel.
ORDERS = {
    "sleep": "SLEEP", "skip": "SKIP_TURN", "heal": "HEAL",
    "rest_repair": "REST_REPAIR", "alert": "ALERT",
    "explore": "AUTOMATE_EXPLORE", "pillage": "PILLAGE",
    "pillage_route": "PILLAGE_ROUTE", "chop": "REMOVE_FEATURE",
    "harvest": "HARVEST_RESOURCE", "repair": "REPAIR",
    "repair_route": "REPAIR_ROUTE", "build_route": "BUILD_ROUTE",
    "remove_improvement": "REMOVE_IMPROVEMENT", "plant_forest": "PLANT_FOREST",
    "clear_contamination": "CLEAR_CONTAMINATION", "excavate": "EXCAVATE",
    "national_park": "DESIGNATE_PARK", "rock_concert": "TOURISM_BOMB",
    "spread_religion": "SPREAD_RELIGION", "remove_heresy": "REMOVE_HERESY",
    "launch_inquisition": "LAUNCH_INQUISITION", "religious_heal": "RELIGIOUS_HEAL",
    "convert_barbarians": "CONVERT_BARBARIANS", "retrain": "RETRAIN",
    "activate_prophet": "FOUND_RELIGION", "evangelize_belief": "EVANGELIZE_BELIEF",
    "upgrade_operation": "UPGRADE",
}
COMMANDS = {
    "wake": "WAKE", "cancel": "CANCEL", "stop_automation": "STOP_AUTOMATION",
    "upgrade": "UPGRADE", "delete": "DELETE", "gift": "GIFT", "exit_formation": "EXIT_FORMATION",
    "activate_great_person": "ACTIVATE_GREAT_PERSON",
    "district_production": "DISTRICT_PRODUCTION", "building_production": "BUILDING_PRODUCTION",
    "wonder_production": "WONDER_PRODUCTION", "project_production": "PROJECT_PRODUCTION",
    "harvest_wonder": "HARVEST_WONDER", "spread_dissent": "SPREAD_DISSENT",
    "condemn_heretic": "CONDEMN_HERETIC", "plunder_trade_route": "PLUNDER_TRADE_ROUTE",
    "pet_dog": "PET_THE_DOG",
}
TARGETS = {
    "ranged_attack": ("operation", "RANGE_ATTACK"),
    "air_attack": ("operation", "AIR_ATTACK"),
    "air_deploy": ("operation", "DEPLOY"),
    "air_rebase": ("operation", "REBASE"),
    "coastal_raid": ("operation", "COASTAL_RAID"),
    "airlift": ("command", "AIRLIFT"),
    "paradrop": ("command", "PARADROP"),
    "priority_attack": ("command", "PRIORITY_TARGET"),
    "move_jump": ("command", "MOVE_JUMP"),
}
SPY_MISSIONS = (
    "SPY_COUNTERSPY", "SPY_DISRUPT_ROCKETRY", "SPY_GAIN_SOURCES",
    "SPY_GREAT_WORK_HEIST", "SPY_LISTENING_POST", "SPY_RECRUIT_PARTISANS",
    "SPY_SABOTAGE_PRODUCTION", "SPY_SIPHON_FUNDS", "SPY_STEAL_TECH_BOOST",
    "SPY_FABRICATE_SCANDAL", "SPY_FOMENT_UNREST", "SPY_NEUTRALIZE_GOVERNOR",
    "SPY_BREACH_DAM",
)
ESCAPES = ("DISTRICT_AERODROME", "DISTRICT_HARBOR", "DISTRICT_COMMERCIAL_HUB", "DISTRICT_CITY_CENTER")


HELPERS = UNIT_LABEL_HELPERS + r'''
local function tactical()
    return type(Game.IsAllowTacticalCommands) == "function" and Game.IsAllowTacticalCommands(me) == true
end
local function unit_here(unit)
    return visible_plot(unit:GetX(), unit:GetY())
end
local function melee_capable(unit)
    -- UnitPanel excludes units with neither military nor religious strength.
    -- These are own-unit fields; no target or hidden occupancy is inspected.
    if type(unit.GetCombat) ~= "function" or type(unit.GetReligiousStrength) ~= "function" then return false end
    local combat,religious=unit:GetCombat(),unit:GetReligiousStrength()
    if type(religious)=="number" and religious>0 then return true end
    if type(combat)~="number" or combat<=0 or type(unit.GetUnitType)~="function"
        or type(unit.GetRangedCombat)~="function" or type(unit.GetBombardCombat)~="function" then return false end
    local row=GameInfo.Units and GameInfo.Units[unit:GetUnitType()]
    if not row or (row.Domain~="DOMAIN_LAND" and row.Domain~="DOMAIN_SEA") then return false end
    -- Civ6Common.RequestMoveOperation (137-149) routes stronger ranged/bombard
    -- weapons to RANGE_ATTACK; a ranged unit's GetCombat is also its defense.
    -- Never infer melee just because RANGE_ATTACK is unavailable this instant.
    -- Dual attackers such as GDR (130/120) and Immortal (35/25) remain allowed.
    local ranged,bombard=unit:GetRangedCombat(),unit:GetBombardCombat()
    return type(ranged)=="number" and type(bombard)=="number"
        and ranged<=combat and bombard<=combat
end
local function operation(name)
    if not UnitOperationTypes or not GameInfo.UnitOperations then return nil end
    local row = GameInfo.UnitOperations["UNITOPERATION_" .. name]
    local hash = row and row.Hash
    if type(hash) ~= "number" or not row or row.VisibleInUI ~= true then return nil end
    return hash
end
local function command(name)
    if not UnitCommandTypes or not GameInfo.UnitCommands then return nil end
    local row = GameInfo.UnitCommands["UNITCOMMAND_" .. name]
    local hash = row and row.Hash
    if type(hash) ~= "number" or not row or row.VisibleInUI ~= true then return nil end
    return hash
end
local function can_operation(unit, hash, params, plot)
    return hash ~= nil and UnitManager and type(UnitManager.CanStartOperation) == "function"
        and UnitManager.CanStartOperation(unit, hash, plot, params or false, false) == true
end
local function can_command(unit, hash, params)
    return hash ~= nil and UnitManager and type(UnitManager.CanStartCommand) == "function"
        and UnitManager.CanStartCommand(unit, hash, params or false, false) == true
end
local function own_spy(unit)
    if not unit or type(unit.GetOwner)~="function" or unit:GetOwner()~=me
        or type(unit.GetUnitType)~="function" or not GameInfo.Units then return false end
    local row=GameInfo.Units[unit:GetUnitType()]
    return row~=nil and row.Spy==true
end
local function spy_cancel_allowed(unit, hash)
    -- UnitPanel.lua:459-464 checks this own actor, not map visibility.
    -- EspionagePopup.lua:481-486 submits CANCEL without coordinates.
    if not own_spy(unit) or not tactical() or hash==nil or not UnitManager
        or type(UnitManager.CanStartCommand)~="function" then return false end
    if UnitManager.CanStartCommand(unit,hash,true)~=true then return false end
    return UnitManager.CanStartCommand(unit,hash,false,true)==true
end
local function xy_params(enums, x, y)
    if not enums or enums.PARAM_X == nil or enums.PARAM_Y == nil then return nil end
    return {[enums.PARAM_X]=x, [enums.PARAM_Y]=y}
end
local function public_city(x, y)
    if not visible_plot(x, y) or not CityManager or type(CityManager.GetCityAt) ~= "function" then return nil end
    local city = CityManager.GetCityAt(x, y)
    if city and city:GetX() == x and city:GetY() == y then return city end
end
-- A lit tile does not disclose an invisible unit. Detect BEFORE any getter.
local function perceived_target(x, y)
    if not visible_plot(x, y) then return false end
    local city = public_city(x, y)
    if city and city:GetOwner() ~= me then return true end
    if type(vis.IsUnitVisible) ~= "function" or not Units
        or type(Units.GetUnitsInPlotLayerID) ~= "function" or not MapLayers then return false end
    local targets = Units.GetUnitsInPlotLayerID(x, y, MapLayers.ANY)
    if type(targets) ~= "table" then return false end
    for _, target in ipairs(targets) do
        if vis:IsUnitVisible(target) == true and target:GetOwner() ~= me
            and target:GetX() == x and target:GetY() == y then return true end
    end
    return false
end
local function no_new_war(unit, x, y)
    if not CombatManager or type(CombatManager.IsAttackChangeWarState) ~= "function"
        or type(unit.GetComponentID) ~= "function" then return false end
    local wars = CombatManager.IsAttackChangeWarState(unit:GetComponentID(), x, y)
    return wars == nil or (type(wars) == "table" and next(wars) == nil)
end
local function unit_item(id,action,row,extra)
    local name,description=unit_row_text(row)
    local item={id=id,name=name or id,description=description,scope="self",owner_id=me,action=action}
    if extra then
        if extra.name~=nil then item.name=extra.name end
        if extra.description~=nil then item.description=extra.description end
        if extra.value~=nil then item.value=extra.value end
    end
    add_item(item)
    return item
end
'''


def _unit(a: dict) -> str:
    return HELPERS + own_unit(a["unit_id"])


def _order_body(a: dict, *, query: bool = False) -> str:
    op = ORDERS[a["order"]]
    # No request on an unseen current tile. All source-local specialist checks
    # are the same as the ordinary UnitPanel button.
    return _unit(a) + f'''
if not tactical() or not unit_here(unit) then return end
local hash = operation({lua(op)})
if not can_operation(unit, hash) then return end
if type(UnitManager.RequestOperation) ~= "function" then return end
attempt(UnitManager.RequestOperation, unit, hash)
'''


def _command_body(a: dict) -> str:
    cmd = COMMANDS[a["command"]]
    if cmd == "CANCEL":
        return _unit(a) + '''
if not tactical() then return end
local hash=command("CANCEL")
if own_spy(unit) then
    if not spy_cancel_allowed(unit,hash) then return end
elseif not unit_here(unit) or not can_command(unit,hash) then return end
if type(UnitManager.RequestCommand)~="function" then return end
attempt(UnitManager.RequestCommand,unit,hash)
'''
    guard = ""
    if cmd in {"CONDEMN_HERETIC", "PLUNDER_TRADE_ROUTE"}:
        guard = 'if not perceived_target(unit:GetX(), unit:GetY()) then return end\n'
    return _unit(a) + f'''
if not tactical() or not unit_here(unit) then return end
{guard}
local hash = command({lua(cmd)})
if not can_command(unit, hash) or type(UnitManager.RequestCommand) ~= "function" then return end
attempt(UnitManager.RequestCommand, unit, hash)
'''


def _promotion_body(a: dict) -> str:
    return _unit(a) + f'''
if not tactical() then return end
local hash = command("PROMOTE")
local row = GameInfo.UnitPromotions and GameInfo.UnitPromotions[{lua(a['promotion'])}]
if not hash or not row or type(row.Index) ~= "number" or not UnitCommandResults
    or UnitCommandResults.PROMOTIONS == nil then return end
local allowed, results = UnitManager.CanStartCommand(unit, hash, true, true)
if allowed ~= true or type(results) ~= "table" then return end
local choices = results[UnitCommandResults.PROMOTIONS]
if type(choices) ~= "table" then return end
local found = false
for _, index in ipairs(choices) do if index == row.Index then found = true end end
if not found or UnitCommandTypes.PARAM_PROMOTION_TYPE == nil then return end
local params = {{[UnitCommandTypes.PARAM_PROMOTION_TYPE]=row.Index}}
if not can_command(unit, hash, params) or type(UnitManager.RequestCommand) ~= "function" then return end
attempt(UnitManager.RequestCommand, unit, hash, params)
'''


def _rename_body(a: dict) -> str:
    # UnitPanel.OnConfirmVeteranName: a fixed name command, not arbitrary data.
    return _unit(a) + f'''
if not tactical() or not unit_here(unit) then return end
if not GameCapabilities or type(GameCapabilities.HasCapability) ~= "function"
    or GameCapabilities.HasCapability("CAPABILITY_RENAME") ~= true then return end
local hash = command("NAME_UNIT")
if not hash or UnitCommandTypes.PARAM_NAME == nil then return end
local params = {{[UnitCommandTypes.PARAM_NAME]={lua(a['name'])}}}
if not can_command(unit, hash, params) or type(UnitManager.RequestCommand) ~= "function" then return end
attempt(UnitManager.RequestCommand, unit, hash, params)
'''


def _formation_body(a: dict) -> str:
    op = {"corps": "FORM_CORPS", "army": "FORM_ARMY", "escort": "ENTER_FORMATION"}[a["formation"]]
    return _unit(a) + f'''
if not tactical() then return end
local other = find_owned("Units", {a['other_unit_id']})
if not other or other:GetID() == unit:GetID() then return end
local hash = command({lua(op)})
if not hash or UnitCommandTypes.PARAM_UNIT_PLAYER == nil or UnitCommandTypes.PARAM_UNIT_ID == nil then return end
local params = {{[UnitCommandTypes.PARAM_UNIT_PLAYER]=me, [UnitCommandTypes.PARAM_UNIT_ID]=other:GetID()}}
if not can_command(unit, hash, params) or type(UnitManager.RequestCommand) ~= "function" then return end
attempt(UnitManager.RequestCommand, unit, hash, params)
'''


def _swap_body(a: dict) -> str:
    # Explicit stock right-click movement exception to VisibleInUI filtering.
    # Civ6Common.RequestMoveOperation uses SWAP_UNITS before MOVE_TO.
    return _unit(a) + f'''
if not tactical() or not unit_here(unit) then return end
local other = find_owned("Units", {a['other_unit_id']})
if not other or other:GetID() == unit:GetID() or not unit_here(other) then return end
local x,y = other:GetX(),other:GetY()
if Map.GetPlotDistance(unit:GetX(),unit:GetY(),x,y) ~= 1 then return end
if not UnitOperationTypes or type(UnitOperationTypes.SWAP_UNITS) ~= "number" then return end
local params = xy_params(UnitOperationTypes,x,y)
if not params or not can_operation(unit,UnitOperationTypes.SWAP_UNITS,params)
    or type(UnitManager.RequestOperation) ~= "function" then return end
attempt(UnitManager.RequestOperation,unit,UnitOperationTypes.SWAP_UNITS,params)
'''


def _swap_options(a: dict) -> str:
    return _unit(a) + f'''
if not UnitOperationTypes or type(UnitOperationTypes.SWAP_UNITS) ~= "number"
    or not UnitManager or type(UnitManager.CanStartOperation) ~= "function" then out.supported=false; return end
if not unit_here(unit) then return end
local count=0
for _, other in player:GetUnits():Members() do
    count=count+1; if count>4096 then error("unavailable") end
    if other:GetOwner()==me and other:GetID()~=unit:GetID() and unit_here(other) then
        local x,y=other:GetX(),other:GetY()
        if Map.GetPlotDistance(unit:GetX(),unit:GetY(),x,y)==1 then
            local params=xy_params(UnitOperationTypes,x,y)
            if params and can_operation(unit,UnitOperationTypes.SWAP_UNITS,params) then
                unit_item("swap:"..other:GetID(),{{type="unit_swap",unit_id={a['unit_id']},other_unit_id=other:GetID()}},
                    unit_action_row("operation","SWAP_UNITS"),
                    {{name=unit_localize(unit_safe_read(other,"GetName"),1024)}})
            end
        end
    end
end
'''


def _target_checks(name: str, x: int, y: int) -> str:
    check = f'if not visible_plot({x}, {y}) then return end\n'
    if name == "ranged_attack":
        # WorldInput: CanStartOperation can say yes with zero remaining moves.
        # Keep this rule local to ordinary ranged attacks, not air/special ops.
        check += 'if type(unit.GetMovesRemaining)~="function" or unit:GetMovesRemaining()<=0 then return end\n'
    elif name == "melee_attack":
        check += 'if not melee_capable(unit) then return end\n'
    if name in {"ranged_attack", "air_attack", "priority_attack", "melee_attack"}:
        check += f'if not perceived_target({x}, {y}) or not no_new_war(unit, {x}, {y}) then return end\n'
    elif name == "coastal_raid":
        check += f'if not no_new_war(unit, {x}, {y}) then return end\n'
    return check


def _target_body(a: dict) -> str:
    interface, op = TARGETS[a["mission"]]
    enums = "UnitOperationTypes" if interface == "operation" else "UnitCommandTypes"
    return _unit(a) + f'''
if not tactical() then return end
{_target_checks(a['mission'], a['x'], a['y'])}
local hash = {interface}({lua(op)})
local params = xy_params({enums}, {a['x']}, {a['y']})
if not params or not can_{interface}(unit, hash, params) then return end
if type(UnitManager.Request{interface.title()}) ~= "function" then return end
attempt(UnitManager.Request{interface.title()}, unit, hash, params)
'''


def _melee_body(a: dict) -> str:
    return _unit(a) + f'''
if not tactical() then return end
{_target_checks('melee_attack', a['x'], a['y'])}
if Map.GetPlotDistance(unit:GetX(), unit:GetY(), {a['x']}, {a['y']}) ~= 1 then return end
local params = xy_params(UnitOperationTypes, {a['x']}, {a['y']})
if not params or not UnitOperationMoveModifiers or type(UnitOperationMoveModifiers.ATTACK) ~= "number"
    or UnitOperationTypes.PARAM_MODIFIERS == nil then return end
params[UnitOperationTypes.PARAM_MODIFIERS] = UnitOperationMoveModifiers.ATTACK
local hash = operation("MOVE_TO")
if not hash or type(UnitManager.RequestOperation) ~= "function" then return end
-- Do not query hidden occupancy or path costs to report a validity result.
attempt(UnitManager.RequestOperation, unit, hash, params)
'''


def _city_attack_body(a: dict) -> str:
    source = own_city(a["city_id"])
    entity = "city"
    if "district_id" in a:
        source += f'''
local district = nil
for _, candidate in city:GetDistricts():Members() do
    if candidate:GetOwner() == me and candidate:GetID() == {a['district_id']} then district=candidate; break end
end
if not district then return end
'''
        entity = "district"
    return HELPERS + source + f'''
if not tactical() or not perceived_target({a['x']}, {a['y']}) then return end
if not CityManager or not CityCommandTypes or type(CityCommandTypes.RANGE_ATTACK) ~= "number"
    or type(CityManager.CanStartCommand) ~= "function" or type(CityManager.RequestCommand) ~= "function" then return end
local params = xy_params(UnitOperationTypes, {a['x']}, {a['y']})
if not params or CityManager.CanStartCommand({entity}, CityCommandTypes.RANGE_ATTACK, params) ~= true then return end
attempt(CityManager.RequestCommand, {entity}, CityCommandTypes.RANGE_ATTACK, params)
'''


def _trade_body(a: dict) -> str:
    return _unit(a) + trade_menus.trade_body(a)


def _transfer_body(a: dict) -> str:
    return _unit(a) + own_city(a["city_id"]) + '''
if not tactical() then return end
local row = GameInfo.Units[unit:GetUnitType()]
if not row or row.MakeTradeRoute ~= true then return end
local hash = operation("TELEPORT_TO_CITY")
local params = xy_params(UnitOperationTypes, city:GetX(), city:GetY())
if not params or not can_operation(unit, hash, params) or type(UnitManager.RequestOperation) ~= "function" then return end
attempt(UnitManager.RequestOperation, unit, hash, params)
'''


def _spy_travel_body(a: dict) -> str:
    return _unit(a) + spy_menus.spy_travel_body(a)


def _spy_body(a: dict) -> str:
    return _unit(a) + spy_menus.spy_body(a)


def _escape_setup() -> str:
    # Own active escape exposes these routes in the stock popup even when the
    # spy's city would otherwise be fogged. Only the pending actor is inspected.
    return '''
local dip = player:GetDiplomacy()
if not dip or type(dip.GetNextEscapingSpyID) ~= "function" then out.supported=false; return end
local spy_id = dip:GetNextEscapingSpyID()
if type(spy_id) ~= "number" or spy_id < 0 then return end
local unit = find_owned("Units", spy_id)
if not unit then return end
if not Cities or type(Cities.GetPlotPurchaseCity) ~= "function" then out.supported=false; return end
local city = Cities.GetPlotPurchaseCity(unit:GetX(), unit:GetY())
if not city then return end
'''


def _escape_body(a: dict) -> str:
    return _escape_setup() + f'''
local row = GameInfo.Districts[{lua(a['district'])}]
if not row or type(row.Index) ~= "number" then return end
if {lua(a['district'])} ~= "DISTRICT_CITY_CENTER"
    and city:GetDistricts():HasDistrict(row.Index, true, true) ~= true then return end
if not PlayerOperations or type(PlayerOperations.SET_ESCAPE_ROUTE) ~= "number"
    or PlayerOperations.PARAM_DISTRICT_TYPE == nil or type(UI.RequestPlayerOperation) ~= "function" then return end
local params = {{[PlayerOperations.PARAM_DISTRICT_TYPE]=row.Index}}
attempt(UI.RequestPlayerOperation, me, PlayerOperations.SET_ESCAPE_ROUTE, params)
'''


def _adjacent_body(a: dict) -> str:
    return _unit(a) + f'''
if not tactical() or not visible_plot({a['x']}, {a['y']}) then return end
local row = GameInfo.Improvements[{lua(a['improvement'])}]
local hash = operation("BUILD_IMPROVEMENT_ADJACENT")
if not row or row.Buildable ~= true or type(row.Hash) ~= "number" then return end
local params = xy_params(UnitOperationTypes, {a['x']}, {a['y']})
if not params or UnitOperationTypes.PARAM_IMPROVEMENT_TYPE == nil then return end
params[UnitOperationTypes.PARAM_IMPROVEMENT_TYPE] = row.Hash
if not can_operation(unit, hash, params) or type(UnitManager.RequestOperation) ~= "function" then return end
attempt(UnitManager.RequestOperation, unit, hash, params)
'''


def _wmd_body(a: dict) -> str:
    return _unit(a) + f'''
if not tactical() or not visible_plot({a['x']}, {a['y']}) then return end
local row = GameInfo.WMDs and GameInfo.WMDs[{lua(a['weapon'])}]
local hash = operation("WMD_STRIKE")
if not row or type(row.Index) ~= "number" then return end
local params = xy_params(UnitOperationTypes, {a['x']}, {a['y']})
if not params or UnitOperationTypes.PARAM_WMD_TYPE == nil then return end
params[UnitOperationTypes.PARAM_WMD_TYPE] = row.Index
if not can_operation(unit, hash, params) or type(UnitManager.RequestOperation) ~= "function" then return end
attempt(UnitManager.RequestOperation, unit, hash, params)
'''


def _icbm_body(a: dict) -> str:
    return HELPERS + own_city(a["city_id"]) + f'''
if not tactical() or not visible_plot({a['x']}, {a['y']}) then return end
local source = visible_plot({a['source_x']}, {a['source_y']})
if not source or source:GetOwner() ~= me or not Cities
    or type(Cities.GetPlotPurchaseCity) ~= "function" then return end
local owning_city = Cities.GetPlotPurchaseCity(source)
if not owning_city or owning_city:GetOwner() ~= me or owning_city:GetID() ~= city:GetID() then return end
local row = GameInfo.WMDs and GameInfo.WMDs[{lua(a['weapon'])}]
if not row or type(row.Index) ~= "number" or not CityCommandTypes
    or type(CityCommandTypes.WMD_STRIKE) ~= "number" then return end
for _, key in ipairs({{"PARAM_X0","PARAM_Y0","PARAM_X1","PARAM_Y1","PARAM_WMD_TYPE"}}) do
    if CityCommandTypes[key] == nil then return end
end
local params = {{[CityCommandTypes.PARAM_X0]={a['source_x']}, [CityCommandTypes.PARAM_Y0]={a['source_y']},
    [CityCommandTypes.PARAM_X1]={a['x']}, [CityCommandTypes.PARAM_Y1]={a['y']}, [CityCommandTypes.PARAM_WMD_TYPE]=row.Index}}
if type(CityManager.CanStartCommand) ~= "function" or type(CityManager.RequestCommand) ~= "function"
    or CityManager.CanStartCommand(city, CityCommandTypes.WMD_STRIKE, params) ~= true then return end
attempt(CityManager.RequestCommand, city, CityCommandTypes.WMD_STRIKE, params)
'''


def _destinations(a: dict, kind: str) -> str:
    body = trade_menus.trade_destinations if kind == "trade" else spy_menus.spy_destinations
    return _unit(a) + body(a)


def _transfer_options(a: dict) -> str:
    return _unit(a) + f'''
if not UnitManager or type(UnitManager.CanStartOperation) ~= "function" then out.supported=false; return end
local row=GameInfo.Units[unit:GetUnitType()]
if not row or row.MakeTradeRoute~=true then return end
local hash=operation("TELEPORT_TO_CITY")
if not hash then out.supported=false; return end
local n=0
for _,city in player:GetCities():Members() do
    n=n+1; if n>4096 then error("unavailable") end
    if city:GetOwner()==me then
        local params=xy_params(UnitOperationTypes,city:GetX(),city:GetY())
        if params and can_operation(unit,hash,params) then
            unit_item("transfer:" .. tostring(city:GetID()),{{type="transfer_trader",unit_id={a['unit_id']},city_id=math.floor(city:GetID())}},
                unit_action_row("operation","TELEPORT_TO_CITY"),
                {{name=unit_localize(unit_safe_read(city,"GetName"),1024)}})
        end
    end
end
'''


def _city_combat(a: dict) -> str:
    return HELPERS + own_city(a["city_id"]) + f'''
if not CityManager or type(CityManager.CanStartCommand) ~= "function" or not CityCommandTypes
    or type(CityCommandTypes.RANGE_ATTACK) ~= "number" then out.supported=false; return end
if not perceived_target({a['x']},{a['y']}) then return end
local params=xy_params(UnitOperationTypes,{a['x']},{a['y']})
if not params then out.supported=false; return end
if CityManager.CanStartCommand(city,CityCommandTypes.RANGE_ATTACK,params)==true then
    unit_item("city_attack",{{type="city_attack",city_id={a['city_id']},x={a['x']},y={a['y']}}},
        unit_action_row("operation","RANGE_ATTACK"))
end
-- Stock CityBannerManager uses city:GetDistrictID() for its city-center
-- strike button. Keep the City entry canonical; a center district is not
-- a second strike. Unknown center identity must not erase the City entry.
local function read_district_id(object,method)
    local ok,id=pcall(function()
        local getter=object[method]
        if type(getter)~="function" then return nil end
        return getter(object)
    end)
    if ok and type(id)=="number" and id%1==0 and id>=0 and id<=2147483647 then
        return math.floor(id)
    end
end
local center_id=read_district_id(city,"GetDistrictID")
if center_id==nil then return end
local n=0
for _,district in city:GetDistricts():Members() do
    n=n+1; if n>256 then error("unavailable") end
    if district:GetOwner()==me then
        local district_id=read_district_id(district,"GetID")
        if district_id~=nil and district_id~=center_id
            and CityManager.CanStartCommand(district,CityCommandTypes.RANGE_ATTACK,params)==true then
            unit_item("district_attack:" .. tostring(district_id),
                {{type="district_attack",city_id={a['city_id']},district_id=district_id,x={a['x']},y={a['y']}}},
                unit_action_row("operation","RANGE_ATTACK"))
        end
    end
end
'''


def _unit_actions(a: dict) -> str:
    orders, commands = lua(ORDERS), lua(COMMANDS)
    return _unit(a) + f'''
if not UnitManager or type(UnitManager.CanStartOperation) ~= "function"
    or type(UnitManager.CanStartCommand) ~= "function" then out.supported=false; return end
local is_spy=own_spy(unit)
if is_spy and spy_cancel_allowed(unit,command("CANCEL")) then
    unit_item("cancel",{{type="unit_command",unit_id={a['unit_id']},command="cancel"}},
        unit_action_row("command","CANCEL"),
        {{description=unit_localize("LOC_UNITPANEL_ESPIONAGE_CANCEL_MISSION",8192)}})
end
if not unit_here(unit) then return end
if can_operation(unit,operation("FOUND_CITY")) then
    unit_item("found_city", {{type="found_city",unit_id={a['unit_id']}}},unit_action_row("operation","FOUND_CITY"))
end
if can_operation(unit,operation("FORTIFY")) then
    unit_item("fortify", {{type="fortify",unit_id={a['unit_id']}}},unit_action_row("operation","FORTIFY"))
end
for name, op in pairs({orders}) do
    if can_operation(unit, operation(op)) then
        local item=unit_item(name, {{type="unit_order", unit_id={a['unit_id']}, order=name}},unit_action_row("operation",op))
        unit_result_labels(item,unit,"operation",operation(op))
    end
end
for name, cmd in pairs({commands}) do
    local safe = true
    if cmd == "CONDEMN_HERETIC" or cmd == "PLUNDER_TRADE_ROUTE" then
        safe = perceived_target(unit:GetX(), unit:GetY())
    end
    if safe and not (is_spy and cmd=="CANCEL") and can_command(unit, command(cmd)) then
        local item=unit_item(name, {{type="unit_command", unit_id={a['unit_id']}, command=name}},unit_action_row("command",cmd))
        unit_result_labels(item,unit,"command",command(cmd))
    end
end
if GameCapabilities and type(GameCapabilities.HasCapability)=="function"
    and GameCapabilities.HasCapability("CAPABILITY_RENAME")==true
    and can_command(unit,command("NAME_UNIT")) then
    unit_item("unit_rename",nil,unit_action_row("command","NAME_UNIT"))
end
local hash = operation("BUILD_IMPROVEMENT")
if hash and GameInfo.Improvements and UnitOperationTypes.PARAM_IMPROVEMENT_TYPE ~= nil then
    local checked = 0
    for row in GameInfo.Improvements() do
        checked=checked+1; if checked>1024 then error("unavailable") end
        if row.Buildable == true and type(row.Hash) == "number" then
            local params=xy_params(UnitOperationTypes, unit:GetX(), unit:GetY())
            if params then
                params[UnitOperationTypes.PARAM_IMPROVEMENT_TYPE]=row.Hash
                if can_operation(unit, hash, params) then
                    local item=unit_item(row.ImprovementType, {{type="build_improvement", unit_id={a['unit_id']}, improvement=row.ImprovementType}},row)
                    unit_result_labels(item,unit,"operation",hash,params)
                end
            end
        end
    end
end
'''


def _unit_details(a: dict) -> str:
    return _unit(a) + QUEUED_DESTINATION_OBSERVATION + r'''
local function value(id, number)
    if type(number)=="number" and number==number and number~=math.huge and number~=-math.huge then
        add_item({id=id,scope="self",owner_id=me,value=number})
    end
end
local function read(object, method, id)
    if object and type(object[method])=="function" then
        local ok,result=pcall(object[method],object)
        if ok then value(id,result) end
    end
end
-- These are the same own-unit signals used for flag dimming, unit-list
-- readiness/status, and the ActionPanel's next-ready-unit check. Remaining
-- movement alone does not mean a sleeping/healing/automated unit needs orders.
for id,method in pairs({ready_to_move="IsReadyToMove",ready_to_select="IsReadyToSelect"}) do
    if type(unit[method])=="function" then
        local ok,result=pcall(unit[method],unit)
        if ok and type(result)=="boolean" then add_item({id=id,scope="self",owner_id=me,value=result}) end
    end
end
if UnitManager and type(UnitManager.GetActivityType)=="function" then
    local ok,activity=pcall(UnitManager.GetActivityType,unit)
    if ok and type(activity)=="number" then
        value("activity_type",activity)
        for _,name in ipairs({"ACTIVITY_AWAKE","ACTIVITY_HOLD","ACTIVITY_SLEEP","ACTIVITY_HEAL",
            "ACTIVITY_SENTRY","ACTIVITY_INTERCEPT","ACTIVITY_OPERATION","NO_ACTIVITY"}) do
            if ActivityTypes and type(ActivityTypes[name])=="number" and ActivityTypes[name]==activity then
                add_item({id="activity",scope="self",owner_id=me,value=name}); break
            end
        end
    end
end
local units=player:GetUnits()
if units and type(units.GetFirstReadyUnit)=="function" then
    local ok,first=pcall(units.GetFirstReadyUnit,units)
    if ok and first==nil then
        add_item({id="first_ready",scope="self",owner_id=me,value=false})
    elseif ok and first and type(first.GetOwner)=="function" and first:GetOwner()==me
        and type(first.GetID)=="function" then
        add_item({id="first_ready",scope="self",owner_id=me,value=first:GetID()==unit:GetID()})
    end
end
for id,method in pairs({
    combat="GetCombat",ranged_combat="GetRangedCombat",bombard_combat="GetBombardCombat",
    anti_air_combat="GetAntiAirCombat",range="GetRange",build_charges="GetBuildCharges",
    spread_charges="GetSpreadCharges",religious_heal_charges="GetReligiousHealCharges",
    action_charges="GetActionCharges",religious_strength="GetReligiousStrength",
    military_formation="GetMilitaryFormation",formation_count="GetFormationUnitCount",
    formation_moves="GetFormationMovesRemaining",fortify_turns="GetFortifyTurns",upgrade_cost="GetUpgradeCost"}) do
    read(unit,method,id)
end
-- GS UnitPanel_Expansion2.lua:141-142 shows this stat only for park-capable
-- units. Missing/throwing getters remain unknown, not a synthetic zero.
local park_ok,park_charges=pcall(function()
    if not GameInfo or not GameInfo.Units or type(unit.GetUnitType)~="function" then return nil end
    local row=GameInfo.Units[unit:GetUnitType()]
    if not row or type(row.ParkCharges)~="number" or row.ParkCharges<=0
        or type(unit.GetParkCharges)~="function" then return nil end
    return unit:GetParkCharges()
end)
if park_ok and type(park_charges)=="number" and park_charges==park_charges
    and park_charges%1==0 and park_charges>=0 and park_charges<=2147483647 then
    value("park_charges",math.floor(park_charges))
end
if type(unit.GetExperience)=="function" then
    local experience=unit:GetExperience()
    read(experience,"GetExperiencePoints","experience")
    read(experience,"GetExperienceForNextLevel","next_level_experience")
    read(experience,"GetLevel","level")
    if experience and type(experience.GetPromotions)=="function" then
        local promotions=experience:GetPromotions()
        if type(promotions)=="table" then
            for _,index in ipairs(promotions) do
                local row=GameInfo.UnitPromotions and GameInfo.UnitPromotions[index]
                if row and type(row.UnitPromotionType)=="string" then
                    local name,description=unit_row_text(row)
                    add_item({id="promotion:"..row.UnitPromotionType,scope="self",owner_id=me,
                        value=row.UnitPromotionType,name=name,description=description})
                end
            end
        end
    end
end
if type(unit.GetGreatPerson)=="function" then
    local person=unit:GetGreatPerson()
    read(person,"GetActionCharges","great_person_charges")
    if person and type(person.GetIndividual)=="function" and GameInfo.GreatPersonIndividuals then
        local row=GameInfo.GreatPersonIndividuals[person:GetIndividual()]
        if row and type(row.GreatPersonIndividualType)=="string" then
            local name,description=unit_row_text(row)
            add_item({id="great_person",scope="self",owner_id=me,value=row.GreatPersonIndividualType,
                name=name,description=description})
            local ability=unit_great_person_ability(row)
            if ability then
                add_item({id="great_person_ability",scope="self",owner_id=me,
                    name=ability.name,description=ability.description})
            end
        end
    end
    -- Own passive text uses exactly ReadUnitData's great-person API, without
    -- looking up the public/past recruitment timeline or another unit.
    if unit_safe_read(person,"HasPassiveEffect")==true then
        local name=unit_text(unit_safe_read(person,"GetPassiveNameText"),1024)
        local description=unit_text(unit_safe_read(person,"GetPassiveEffectText"),8192)
        if name or description then
            add_item({id="great_person_passive",scope="self",owner_id=me,name=name,description=description})
        end
    end
    if person then
        local info=unit_great_person_action(unit,command("ACTIVATE_GREAT_PERSON"))
        if info then
            add_item({id="great_person_action",scope="self",owner_id=me,name=info.name,
                description=info.description,value=info.value})
        end
    end
end
local row=GameInfo.Units[unit:GetUnitType()]
if row and type(row.UnitType)=="string" then
    local name,description=unit_row_text(row)
    add_item({id="unit_type",scope="self",owner_id=me,value=row.UnitType,name=name,description=description})
end
if row and row.Spy==true and type(unit.GetSpyOperation)=="function" then
    local op=unit:GetSpyOperation()
    if op>=0 and GameInfo.UnitOperations[op] then
        local operation_row=GameInfo.UnitOperations[op]
        if type(operation_row.OperationType)=="string" then
            local name,description=unit_row_text(operation_row)
            add_item({id="spy_operation",scope="self",owner_id=me,value=operation_row.OperationType,
                name=name,description=description})
        end
        if type(unit.GetSpyOperationEndTurn)=="function" then
            value("spy_turns_remaining",math.max(0,unit:GetSpyOperationEndTurn()-turn))
        end
    elseif op==-1 then add_item({id="spy_operation",scope="self",owner_id=me,value="NONE"}) end
end
'''


def _promotions(a: dict) -> str:
    return _unit(a) + f'''
local hash = command("PROMOTE")
if not hash or not UnitCommandResults or not UnitCommandResults.PROMOTIONS
    or type(UnitManager.CanStartCommand) ~= "function" then out.supported=false; return end
local allowed, results = UnitManager.CanStartCommand(unit, hash, true, true)
if allowed ~= true or type(results) ~= "table" then return end
local choices = results[UnitCommandResults.PROMOTIONS]
if type(choices) ~= "table" then return end
for _, index in ipairs(choices) do
    local row = GameInfo.UnitPromotions[index]
    if row and type(row.UnitPromotionType) == "string" then
        unit_item(row.UnitPromotionType, {{type="unit_promote", unit_id={a['unit_id']}, promotion=row.UnitPromotionType}},row)
    end
end
'''


def _formations(a: dict) -> str:
    return _unit(a) + f'''
if not UnitManager or type(UnitManager.CanStartCommand) ~= "function"
    or not UnitCommandTypes or UnitCommandTypes.PARAM_UNIT_PLAYER == nil
    or UnitCommandTypes.PARAM_UNIT_ID == nil then out.supported=false; return end
local n=0
for _, other in player:GetUnits():Members() do
    n=n+1; if n>4096 then error("unavailable") end
    if other:GetOwner()==me and other:GetID()~=unit:GetID() then
        local params={{[UnitCommandTypes.PARAM_UNIT_PLAYER]=me, [UnitCommandTypes.PARAM_UNIT_ID]=other:GetID()}}
        for name, cmd in pairs({{corps="FORM_CORPS",army="FORM_ARMY",escort="ENTER_FORMATION"}}) do
            if can_command(unit, command(cmd), params) then
                local row=unit_action_row("command",cmd)
                local action_name,description=unit_row_text(row)
                local unit_row=GameInfo.Units[unit:GetUnitType()]
                if unit_row and unit_row.Domain=="DOMAIN_SEA" and (cmd=="FORM_CORPS" or cmd=="FORM_ARMY") then
                    local key=cmd=="FORM_CORPS" and "LOC_UNITCOMMAND_FORM_FLEET_DESCRIPTION" or "LOC_UNITCOMMAND_FORM_ARMADA_DESCRIPTION"
                    description=unit_localize(key,8192)
                    action_name=unit_text(description,1024) or action_name
                elseif cmd=="ENTER_FORMATION" and row then
                    local other_type=unit_safe_read(other,"GetUnitType")
                    local other_row=other_type and GameInfo.Units[other_type]
                    if other_row then
                        description=unit_localize(row.Description,8192,other_row.Name)
                        action_name=unit_text(description,1024) or action_name
                    end
                end
                local partner=unit_localize(unit_safe_read(other,"GetName"),1024)
                if partner then action_name=action_name and unit_text(action_name.." · "..partner,1024) or partner end
                unit_item(name .. ":" .. tostring(other:GetID()), {{type="unit_form",unit_id={a['unit_id']},
                    other_unit_id=math.floor(other:GetID()),formation=name}},row,{{name=action_name,description=description}})
            end
        end
    end
end
'''


def _unit_targets(a: dict) -> str:
    body = _unit(a) + f'''
if not UnitManager or type(UnitManager.CanStartOperation) ~= "function" then out.supported=false; return end
if not visible_plot({a['x']}, {a['y']}) then return end
'''
    for name, (interface, op) in TARGETS.items():
        enums = "UnitOperationTypes" if interface == "operation" else "UnitCommandTypes"
        body += f'''
do local function candidate()
{_target_checks(name, a['x'], a['y'])}
local params=xy_params({enums}, {a['x']}, {a['y']})
if params and can_{interface}(unit, {interface}({lua(op)}), params) then
    unit_item({lua(name)}, {{type="unit_target",unit_id={a['unit_id']},mission={lua(name)},x={a['x']},y={a['y']}}},
        unit_action_row({lua(interface)},{lua(op)}))
end
end; candidate(); end
'''
    body += f'''
if melee_capable(unit) and perceived_target({a['x']}, {a['y']}) and no_new_war(unit, {a['x']}, {a['y']})
    and Map.GetPlotDistance(unit:GetX(), unit:GetY(), {a['x']}, {a['y']})==1 then
    unit_item("melee_attack", {{type="melee_attack",unit_id={a['unit_id']},x={a['x']},y={a['y']}}},
        {{Name="LOC_OPTIONS_HOTKEY_UNIT_ATTACK",Description="LOC_OPTIONS_HOTKEY_UNIT_ATTACK_HELP"}})
end
'''
    return body


def _trade_options(a: dict) -> str:
    return _unit(a) + trade_menus.trade_options(a)


def _spy_options(a: dict) -> str:
    return _unit(a) + spy_menus.spy_options(a)


def _escape_options(a: dict) -> str:
    return UNIT_LABEL_HELPERS + _escape_setup() + f'''
for index, name in ipairs({lua(list(ESCAPES))}) do
    local row=GameInfo.Districts[name]
    if row and (name=="DISTRICT_CITY_CENTER" or city:GetDistricts():HasDistrict(row.Index,true,true)==true) then
        add_item({{id=name,name=unit_localize("LOC_ESPIONAGE_ESCAPE_CHOICE_"..index,1024) or name,
            description=unit_localize("LOC_ESPIONAGE_ESCAPE_TURNS",8192,row.TravelTime),
            scope="self",owner_id=me,value=row.TravelTime,
            action={{type="spy_escape",district=name}}}})
    end
end
'''


ACTIONS = {
    "unit_order": ActionSpec({"unit_id": "id", "order": "enum:" + "|".join(ORDERS)}, _order_body,
        "A normal source-tile unit order; build_route builds the currently unlocked road/railroad."),
    "unit_command": ActionSpec({"unit_id": "id", "command": "enum:" + "|".join(COMMANDS)}, _command_body,
        "Normal unit command; great-person activation consumes a charge, delete disbands the unit."),
    "unit_promote": ActionSpec({"unit_id": "id", "promotion": "identifier:PROMOTION_"}, _promotion_body),
    "unit_rename": ActionSpec({"unit_id":"id","name":"text"},_rename_body,"Rename an eligible own veteran unit using the normal name command."),
    "unit_form": ActionSpec({"unit_id": "id", "other_unit_id": "id", "formation": "enum:corps|army|escort"}, _formation_body),
    "unit_swap": ActionSpec({"unit_id":"id","other_unit_id":"id"},_swap_body,"Swap two own adjacent units using normal right-click movement semantics."),
    "unit_target": ActionSpec({"unit_id": "id", "mission": "enum:" + "|".join(TARGETS), "x": "coord", "y": "coord"}, _target_body),
    "melee_attack": ActionSpec({"unit_id": "id", "x": "coord", "y": "coord"}, _melee_body,
        "Adjacent visible detected target; also theological combat. Does not implicitly declare war."),
    "city_attack": ActionSpec({"city_id": "id", "x": "coord", "y": "coord"}, _city_attack_body),
    "district_attack": ActionSpec({"city_id": "id", "district_id": "id", "x": "coord", "y": "coord"}, _city_attack_body),
    "trade_route": ActionSpec({"unit_id": "id", "x": "coord", "y": "coord"}, _trade_body),
    "transfer_trader": ActionSpec({"unit_id": "id", "city_id": "id"}, _transfer_body),
    "spy_travel": ActionSpec({"unit_id": "id", "x": "coord", "y": "coord"}, _spy_travel_body),
    "spy_mission": ActionSpec({"unit_id": "id", "mission": "enum:" + "|".join(SPY_MISSIONS), "x": "coord", "y": "coord"}, _spy_body),
    "spy_escape": ActionSpec({"district": "enum:" + "|".join(ESCAPES)}, _escape_body),
    "build_adjacent_improvement": ActionSpec({"unit_id": "id", "improvement": "identifier:IMPROVEMENT_", "x": "coord", "y": "coord"}, _adjacent_body),
    "wmd_strike": ActionSpec({"unit_id": "id", "weapon": "identifier:WMD_", "x": "coord", "y": "coord"}, _wmd_body,
        "Normal unit-launched nuclear/thermonuclear strike at a visible tile; may cause war."),
    "icbm_strike": ActionSpec({"city_id": "id", "source_x": "coord", "source_y": "coord", "weapon": "identifier:WMD_", "x": "coord", "y": "coord"}, _icbm_body,
        "Normal missile-silo strike. Source belongs to own city; target visible. May cause war."),
}

QUERIES = {
    "unit_details": QuerySpec({"unit_id":"id"},_unit_details,"Own strength, specialist charges, experience, promotions, great-person identity and spy remaining turns."),
    "unit_actions": QuerySpec({"unit_id": "id"}, _unit_actions, "Source-tile unit actions and improvements."),
    "unit_promotions": QuerySpec({"unit_id": "id"}, _promotions, "Actual engine-offered promotions, including apostles/spies/rock bands."),
    "unit_formations": QuerySpec({"unit_id": "id"}, _formations, "Own units that can form corps/army/escort."),
    "unit_swaps": QuerySpec({"unit_id":"id"},_swap_options,"Own adjacent units eligible for a position swap."),
    "unit_targets": QuerySpec({"unit_id": "id", "x": "coord", "y": "coord"}, _unit_targets, "Normal target actions for one currently visible tile."),
    "trade_routes": QuerySpec({"unit_id": "id", "x": "coord", "y": "coord"}, _trade_options, "Stock trade-menu destination and route yields; rechecks operation and nonempty route. No raw paths."),
    "spy_missions": QuerySpec({"unit_id": "id", "x": "coord", "y": "coord"}, _spy_options, "Stock spy-menu missions at a known city or offered district. Remote missions are previews; execution requires current spy city."),
    "spy_escape_routes": QuerySpec({}, _escape_options, "The local player's pending escape choices only."),
    "trade_destinations": QuerySpec({"unit_id":"id","offset":"id"},lambda a:_destinations(a,"trade"),
        "Stock-menu trade destinations including fog; 64 eligible entries/page. Start offset=0; next_offset=-1 ends."),
    "spy_destinations": QuerySpec({"unit_id":"id","offset":"id"},lambda a:_destinations(a,"spy"),
        "Stock-menu spy destinations including revealed fog cities; 64 eligible entries/page. Start offset=0; next_offset=-1 ends."),
    "trader_origins": QuerySpec({"unit_id":"id"},_transfer_options,"Own cities the trader can transfer to."),
    "city_combat": QuerySpec({"city_id":"id","x":"coord","y":"coord"},_city_combat,"Own city/district strikes against one perceived target."),
}
