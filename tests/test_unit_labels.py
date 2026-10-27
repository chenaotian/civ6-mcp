"""Unit labels enrich already-authorized choices, never their target scope."""
import pytest

from civ6_fair_mcp.extensions.units import COMMANDS, ORDERS
from test_extension_units import engine


LABELS = r'''
local words={LOC_SLEEP="休眠",LOC_UPGRADE="升级单位",LOC_ACTIVATE="激活伟人",
    LOC_RANGE="远程攻击",LOC_TRANSFER="转移所属城市",LOC_FORM_CORPS="组建军团",
    LOC_FORM_ARMY="组建集团军",LOC_ESCORT="与{1}组成护送编队",
    LOC_PROMOTION_NAME="齐射",LOC_PROMOTION_EFFECT="攻击陆地单位时远程战斗力提高。",
    LOC_FARM="农场",LOC_FARM_EFFECT="提高地块粮食产出。",LOC_SCOUT="侦察兵",
    LOC_SCOUT_EFFECT="行动迅速的远古时代侦察单位。",LOC_ARCHER="弓箭手",
    LOC_PERSON="希帕蒂娅",LOC_PERSON_ACTION="建立图书馆",
    LOC_PERSON_EFFECT="立即建造一座图书馆。",LOC_PERSON_BONUS="所有图书馆提供额外科学值。",
    LOC_CHOP="移除地貌",LOC_HARVEST_EFFECT="获得 36 点生产力。",
    LOC_UNITCOMMAND_FORM_FLEET_DESCRIPTION="组建舰队",
    LOC_UNITCOMMAND_FORM_ARMADA_DESCRIPTION="组建无敌舰队",
    LOC_OPTIONS_HOTKEY_UNIT_ATTACK="攻击",LOC_OPTIONS_HOTKEY_UNIT_ATTACK_HELP="使用所选单位进行攻击。",
    LOC_ESPIONAGE_ESCAPE_CHOICE_1="乘飞机",LOC_ESPIONAGE_ESCAPE_CHOICE_2="乘船",
    LOC_ESPIONAGE_ESCAPE_CHOICE_3="乘车",LOC_ESPIONAGE_ESCAPE_CHOICE_4="步行",
}
Locale.Lookup=function(key,...)
    local args={...}
    if key=="LOC_UNITOPERATION_UPGRADE_INFO" then return "升级为"..(words[args[1]] or args[1]).."："..args[2].."金币" end
    if key=="LOC_ESPIONAGE_ESCAPE_TURNS" then return args[1].."回合" end
    if key=="LOC_ESCORT" and args[1] then return "与"..(words[args[1]] or args[1]).."组成护送编队" end
    return words[key] or key
end
function label_operation(name,key)
    GameInfo.UnitOperations["UNITOPERATION_"..name]={VisibleInUI=true,Hash=UnitOperationTypes[name],Description=key}
end
function label_command(name,key)
    GameInfo.UnitCommands["UNITCOMMAND_"..name]={VisibleInUI=true,Hash=UnitCommandTypes[name],Description=key}
end
label_operation("SLEEP","LOC_SLEEP")
label_operation("RANGE_ATTACK","LOC_RANGE")
label_operation("TELEPORT_TO_CITY","LOC_TRANSFER")
label_operation("REMOVE_FEATURE","LOC_CHOP")
label_command("UPGRADE","LOC_UPGRADE")
label_command("ACTIVATE_GREAT_PERSON","LOC_ACTIVATE")
label_command("FORM_CORPS","LOC_FORM_CORPS")
label_command("FORM_ARMY","LOC_FORM_ARMY")
label_command("ENTER_FORMATION","LOC_ESCORT")
GameInfo.UnitPromotions[7].Name="LOC_PROMOTION_NAME"
GameInfo.UnitPromotions[7].Description="LOC_PROMOTION_EFFECT"
GameInfo.UnitPromotions.PROMOTION_TEST=GameInfo.UnitPromotions[7]
local farm={ImprovementType="IMPROVEMENT_FARM",Hash=333,Buildable=true,Name="LOC_FARM",Description="LOC_FARM_EFFECT"}
GameInfo.Improvements=setmetatable({IMPROVEMENT_FARM=farm},{__call=function()
    local done=false;return function() if not done then done=true;return farm end end end})
unit.GetName=function() return "自有侦察兵" end
other.GetName=function() return "护送伙伴" end
other.GetUnitType=function() return 1 end
GameInfo.Units[1].UnitType="UNIT_SCOUT"
GameInfo.Units[1].Name="LOC_SCOUT"
GameInfo.Units[1].Description="LOC_SCOUT_EFFECT"
'''


def indexed(result):
    return {item["id"]: item for item in result["items"]}


def choices(result):
    return {item["id"]: item.get("action") for item in result["items"]}


def test_operation_command_improvement_labels_preserve_original_choice_payloads(engine):
    vm, run = engine
    vm.execute(LABELS)
    before = run("unit_actions", {"unit_id": 10}, True)
    rows = indexed(before)
    assert rows["sleep"]["name"] == "休眠"
    assert rows["upgrade"]["name"] == "升级单位"
    assert rows["IMPROVEMENT_FARM"]["name"] == "农场"
    assert rows["IMPROVEMENT_FARM"]["description"] == "提高地块粮食产出。"
    vm.execute("Locale.Lookup=nil")
    after = run("unit_actions", {"unit_id": 10}, True)
    assert choices(before) == choices(after)
    assert indexed(after)["sleep"]["name"] == "sleep"
    assert len(vm.globals().calls) == 0


def test_available_and_earned_promotions_have_same_name_and_effect(engine):
    vm, run = engine
    vm.execute(LABELS + '''
        unit.GetExperience=function() return {GetPromotions=function() return {7} end} end
    ''')
    offered = indexed(run("unit_promotions", {"unit_id": 10}, True))["PROMOTION_TEST"]
    earned = indexed(run("unit_details", {"unit_id": 10}, True))["promotion:PROMOTION_TEST"]
    for row in (offered, earned):
        assert row["name"] == "齐射" and row["description"] == "攻击陆地单位时远程战斗力提高。"
    assert offered["action"] == {"type": "unit_promote", "unit_id": 10, "promotion": "PROMOTION_TEST"}
    assert earned["value"] == "PROMOTION_TEST" and "action" not in earned


def test_only_engine_offered_promotions_are_labeled(engine):
    vm, run = engine
    vm.execute(LABELS + "\nsettings.promotion=99")
    assert run("unit_promotions", {"unit_id": 10}, True)["items"] == []


def test_own_unit_and_great_person_identity_and_passive_text(engine):
    vm, run = engine
    vm.execute(LABELS + '''
        GameInfo.GreatPersonIndividuals={[5]={GreatPersonIndividualType="GREAT_PERSON_INDIVIDUAL_HYPATIA",Name="LOC_PERSON"}}
        unit.GetGreatPerson=function() return {GetIndividual=function() return 5 end,
            GetActionCharges=function() return 1 end,HasPassiveEffect=function() return true end,
            GetPassiveNameText=function() return "学院支持" end,
            GetPassiveEffectText=function() return "公开的伟人被动效果。" end} end
        Game.GetGreatPeople=forbidden
    ''')
    rows = indexed(run("unit_details", {"unit_id": 10}, True))
    assert rows["unit_type"]["name"] == "侦察兵"
    assert rows["unit_type"]["description"] == "行动迅速的远古时代侦察单位。"
    assert rows["great_person"]["name"] == "希帕蒂娅"
    assert rows["great_person_passive"]["description"] == "公开的伟人被动效果。"
    assert rows["great_person_charges"]["value"] == 1
    vm.globals().settings.owner = 1
    assert run("unit_details", {"unit_id": 10}, True)["items"] == []


def test_absent_great_person_passive_does_not_probe_effect(engine):
    vm, run = engine
    vm.execute(LABELS + '''unit.GetGreatPerson=function() return {
        HasPassiveEffect=function() return false end,
        GetPassiveNameText=forbidden,GetPassiveEffectText=forbidden} end''')
    assert "great_person_passive" not in indexed(run("unit_details", {"unit_id": 10}, True))


def test_active_ability_uses_only_public_unitpanel_result_fields(engine):
    vm, run = engine
    vm.execute(LABELS + '''
        UnitOperationResults={ACTION_NAME="action_name",ADDITIONAL_DESCRIPTION="description",FAILURE_REASONS="failure"}
        local previous=UnitManager.CanStartCommand
        UnitManager.CanStartCommand=function(u,hash,params,results)
            if hash==UnitCommandTypes.ACTIVATE_GREAT_PERSON and results==true then
                assert(u==unit and params==false)
                return true,setmetatable({action_name="LOC_PERSON_ACTION",description={"LOC_PERSON_EFFECT","LOC_PERSON_BONUS"}},
                    {__index=function(_,key) error("SECRET_NON_UI_RESULT_"..key) end})
            end
            return previous(u,hash,params,results)
        end
    ''')
    row = indexed(run("unit_actions", {"unit_id": 10}, True))["activate_great_person"]
    assert row["name"] == "建立图书馆"
    assert row["description"] == "建立图书馆[NEWLINE]立即建造一座图书馆。[NEWLINE]所有图书馆提供额外科学值。"
    assert row["action"] == {"type": "unit_command", "unit_id": 10, "command": "activate_great_person"}
    assert len(vm.globals().calls) == 0


@pytest.mark.parametrize("available", [True, False])
def test_great_person_details_describe_ui_visible_ability_even_when_not_usable_here(engine, available):
    vm, run = engine
    vm.execute(LABELS + '''
        unit.GetGreatPerson=function() return {} end
        UnitOperationResults={ACTION_NAME="action_name",ADDITIONAL_DESCRIPTION="description",FAILURE_REASONS="failure"}
        local previous=UnitManager.CanStartCommand
        UnitManager.CanStartCommand=function(u,hash,params,results)
            if hash==UnitCommandTypes.ACTIVATE_GREAT_PERSON then
                assert(u==unit)
                if params==true then assert(results==nil);return true end
                if results~=true then return settings.gp_available end
                return settings.gp_available,setmetatable({action_name="LOC_PERSON_ACTION",description={"LOC_PERSON_EFFECT","LOC_PERSON_BONUS"}},
                    {__index=function(_,key) error("SECRET_NON_UI_RESULT_"..key) end})
            end
            return previous(u,hash,params,results)
        end
    ''')
    vm.globals().settings.gp_available = available
    row = indexed(run("unit_details", {"unit_id": 10}, True))["great_person_action"]
    assert row["name"] == "建立图书馆"
    assert "立即建造一座图书馆" in row["description"] and "所有图书馆" in row["description"]
    assert row["value"] is available and "action" not in row
    assert ("activate_great_person" in indexed(run("unit_actions", {"unit_id": 10}, True))) is available
    assert len(vm.globals().calls) == 0


def test_great_person_details_require_normal_ui_display_gate(engine):
    vm, run = engine
    vm.execute(LABELS + '''
        unit.GetGreatPerson=function() return {} end
        UnitManager.CanStartCommand=function(u,hash,params,results)
            assert(u==unit and hash==UnitCommandTypes.ACTIVATE_GREAT_PERSON)
            assert(params==true and results==nil,"must not read hidden command result")
            return false
        end
    ''')
    assert "great_person_action" not in indexed(run("unit_details", {"unit_id": 10}, True))


@pytest.mark.parametrize("result", ['nil,{}', '0,{}', '"false",{}', 'error("SECRET_UNAVAILABLE")'])
def test_missing_great_person_current_availability_is_not_fabricated_as_false(engine, result):
    vm, run = engine
    vm.execute(LABELS + '''
        unit.GetGreatPerson=function() return {} end
        UnitManager.CanStartCommand=function(u,hash,params,results)
            if params==true then return true end
            return ''' + result + '''
        end
    ''')
    rows = indexed(run("unit_details", {"unit_id": 10}, True))
    assert rows["great_person_action"]["name"] == "激活伟人"
    assert "value" not in rows["great_person_action"] and "action" not in rows["great_person_action"]
    assert rows["unit_type"]["value"] == "UNIT_SCOUT"


@pytest.mark.parametrize("available", ["nil", "0", '"false"'])
def test_unknown_availability_keeps_normal_ui_ability_description(engine, available):
    vm, run = engine
    vm.execute(LABELS + '''
        unit.GetGreatPerson=function() return {} end
        UnitOperationResults={ACTION_NAME="action_name",ADDITIONAL_DESCRIPTION="description",FAILURE_REASONS="failure"}
        UnitManager.CanStartCommand=function(u,hash,params,results)
            if params==true then return true end
            return ''' + available + ''',setmetatable({action_name="LOC_PERSON_ACTION",description={"LOC_PERSON_EFFECT"}},
                {__index=function(_,key) error("SECRET_NON_UI_RESULT_"..key) end})
        end
    ''')
    row = indexed(run("unit_details", {"unit_id": 10}, True))["great_person_action"]
    assert row["name"] == "建立图书馆" and "立即建造一座图书馆" in row["description"]
    assert "value" not in row and "action" not in row
    assert len(vm.globals().calls) == 0


@pytest.mark.parametrize("shown", ["nil", "0", '"true"'])
def test_unknown_ui_display_permission_still_blocks_ability_details(engine, shown):
    vm, run = engine
    vm.execute(LABELS + '''
        unit.GetGreatPerson=function() return {} end
        UnitManager.CanStartCommand=function(u,hash,params,results)
            assert(params==true and results==nil,"current result must not be read before display permission")
            return ''' + shown + '''
        end
    ''')
    assert "great_person_action" not in indexed(run("unit_details", {"unit_id": 10}, True))


def test_great_person_optional_effect_failure_keeps_verified_boolean_only(engine):
    vm, run = engine
    vm.execute(LABELS + '''
        unit.GetGreatPerson=function() return {} end
        UnitOperationResults={ACTION_NAME="action_name",ADDITIONAL_DESCRIPTION="description"}
        UnitManager.CanStartCommand=function(u,hash,params,results)
            if params==true then return true end
            return false,setmetatable({}, {__index=forbidden})
        end
    ''')
    row = indexed(run("unit_details", {"unit_id": 10}, True))["great_person_action"]
    assert row["value"] is False and row["name"] == "激活伟人"
    assert "action" not in row


def test_foreign_great_person_details_never_probe_identity_or_command(engine):
    vm, run = engine
    vm.execute(LABELS + '''
        settings.owner=1
        unit.GetGreatPerson=forbidden
        UnitManager.CanStartCommand=forbidden
    ''')
    assert run("unit_details", {"unit_id": 10}, True)["items"] == []


def test_harvest_effects_request_no_targets_result_mode(engine):
    vm, run = engine
    vm.execute(LABELS + '''
        UnitOperationResults={ACTION_NAME="action_name",ADDITIONAL_DESCRIPTION="description"}
        OperationResultsTypes={NO_TARGETS=55}
        local previous=UnitManager.CanStartOperation
        UnitManager.CanStartOperation=function(u,hash,plot,params,results)
            if hash==UnitOperationTypes.REMOVE_FEATURE and results~=false then
                assert(u==unit and plot==nil and params==false and results==55)
                return true,setmetatable({action_name="LOC_CHOP",description={"LOC_HARVEST_EFFECT"}},
                    {__index=function(_,key) error("SECRET_TARGET_RESULT_"..key) end})
            end
            return previous(u,hash,plot,params,results)
        end
    ''')
    row = indexed(run("unit_actions", {"unit_id": 10}, True))["chop"]
    assert "36 点生产力" in row["description"]


def test_successful_upgrade_menu_displays_engine_target_and_own_gold_cost(engine):
    vm, run = engine
    vm.execute(LABELS + '''
        UnitOperationResults={ACTION_NAME="action_name",ADDITIONAL_DESCRIPTION="description"}
        UnitCommandResults.UNIT_TYPE="unit_type"
        GameInfo.Units[8]={UnitType="UNIT_ARCHER",Name="LOC_ARCHER"}
        unit.GetUpgradeCost=function() return 80 end
        local previous=UnitManager.CanStartCommand
        UnitManager.CanStartCommand=function(u,hash,params,results)
            if hash==UnitCommandTypes.UPGRADE and results==true then
                return true,{unit_type=8}
            end
            return previous(u,hash,params,results)
        end
    ''')
    row = indexed(run("unit_actions", {"unit_id": 10}, True))["upgrade"]
    assert row["value"] == 80 and "弓箭手" in row["description"] and "80金币" in row["description"]


@pytest.mark.parametrize("failure", ['error("SECRET_FORMATTER")', 'false,{action_name="LOC_PERSON_ACTION"}', 'true,false'])
def test_optional_dynamic_description_failure_cannot_remove_existing_action(engine, failure):
    vm, run = engine
    vm.execute(LABELS + '''
        UnitOperationResults={ACTION_NAME="action_name",ADDITIONAL_DESCRIPTION="description"}
        local previous=UnitManager.CanStartCommand
        UnitManager.CanStartCommand=function(u,hash,params,results)
            if hash==UnitCommandTypes.ACTIVATE_GREAT_PERSON and results==true then
                return ''' + failure + '''
            end
            return previous(u,hash,params,results)
        end
    ''')
    row = indexed(run("unit_actions", {"unit_id": 10}, True))["activate_great_person"]
    assert row["name"] == "激活伟人" and row["action"]["command"] == "activate_great_person"


@pytest.mark.parametrize("setup", ["Locale=nil", "Locale.Lookup=forbidden", 'Locale.Lookup=function() return "bad\\0text" end'])
def test_missing_or_malformed_localization_preserves_menu_ids_and_actions(engine, setup):
    vm, run = engine
    vm.execute(LABELS)
    before = choices(run("unit_promotions", {"unit_id": 10}, True))
    vm.execute(setup)
    after = run("unit_promotions", {"unit_id": 10}, True)
    assert choices(after) == before
    assert after["items"][0]["name"] == "PROMOTION_TEST"
    assert "description" not in after["items"][0]


def test_trader_origin_name_is_actual_owned_city_after_native_gate(engine):
    vm, run = engine
    vm.execute(LABELS)
    row = run("trader_origins", {"unit_id": 10}, True)["items"][0]
    assert row["name"] == "Own city" and row["description"] == "转移所属城市"
    assert row["action"]["city_id"] == 20
    vm.execute("settings.can=false;city.GetName=forbidden")
    assert run("trader_origins", {"unit_id": 10}, True)["items"] == []


def test_formation_partner_name_and_naval_variant_come_from_own_ui_data(engine):
    vm, run = engine
    vm.execute(LABELS + '\nGameInfo.Units[1].Domain="DOMAIN_SEA"')
    rows = indexed(run("unit_formations", {"unit_id": 10}, True))
    assert rows["corps:11"]["name"] == "组建舰队 · 护送伙伴"
    assert rows["army:11"]["description"] == "组建无敌舰队"
    assert rows["escort:11"]["description"] == "与侦察兵组成护送编队"


def test_foreign_formation_partner_name_never_read(engine):
    vm, run = engine
    vm.execute(LABELS + "\nother.GetOwner=function() return 1 end;other.GetName=forbidden;other.GetUnitType=forbidden")
    assert run("unit_formations", {"unit_id": 10}, True)["items"] == []


def test_visible_target_labels_do_not_request_dynamic_target_results_or_enemy_names(engine):
    vm, run = engine
    vm.execute(LABELS + '''
        UnitOperationResults={ACTION_NAME="action_name",ADDITIONAL_DESCRIPTION="description"}
        OperationResultsTypes={NO_TARGETS=55}
        local previous=UnitManager.CanStartOperation
        UnitManager.CanStartOperation=function(u,hash,plot,params,results)
            assert(results==false,"target detail probe is not allowed")
            return previous(u,hash,plot,params,results)
        end
    ''')
    rows = indexed(run("unit_targets", {"unit_id": 10, "x": 3, "y": 2}, True))
    assert rows["ranged_attack"]["name"] == "远程攻击"
    assert rows["melee_attack"]["name"] == "攻击"
    vm.globals().settings.visible = False
    assert run("unit_targets", {"unit_id": 10, "x": 3, "y": 2}, True)["items"] == []
    assert vm.globals().reads.hidden == 0


def test_escape_route_uses_actual_choice_text_and_turns_without_city_identity(engine):
    vm, run = engine
    vm.execute(LABELS + "\nsettings.escape=10;settings.visible=false;city.GetName=forbidden")
    rows = indexed(run("spy_escape_routes", {}, True))
    assert rows["DISTRICT_AERODROME"]["name"] == "乘飞机"
    assert rows["DISTRICT_CITY_CENTER"]["name"] == "步行"
    assert rows["DISTRICT_CITY_CENTER"]["description"] == "4回合"
    assert vm.globals().reads.foreign == 0


def test_action_registry_cannot_expand_from_new_metadata_rows(engine):
    vm, run = engine
    vm.execute(LABELS + '''
        settings.target_x=2
        GameInfo.UnitCommands.UNITCOMMAND_EXECUTE_SCRIPT={VisibleInUI=true,Hash=999,Description="LOC_PERSON_EFFECT"}
        GameInfo.UnitOperations.UNITOPERATION_CHEAT={VisibleInUI=true,Hash=998,Description="LOC_PERSON_EFFECT"}
    ''')
    rows = indexed(run("unit_actions", {"unit_id": 10}, True))
    assert set(rows) == set(ORDERS) | set(COMMANDS) | {"found_city", "fortify", "IMPROVEMENT_FARM"}
    assert all(item.get("action", {}).get("command") != "EXECUTE_SCRIPT" for item in rows.values())
    assert len(vm.globals().calls) == 0


OWN_ABILITY = r'''
ability_row={GreatPersonIndividualType="GREAT_PERSON_INDIVIDUAL_OWN",Name="LOC_PERSON",
    GreatPersonClassType="GREAT_PERSON_CLASS_MERCHANT",ActionCharges=3}
GameInfo.GreatPersonIndividuals={[5]=ability_row}
unit.GetGreatPerson=function() return {GetIndividual=function() return 5 end,
    GetActionCharges=function() return 2 end} end
Game.GetGreatPeople=forbidden
UnitManager.CanStartCommand=function() return false end
GameInfo.GreatPersonIndividualActionModifiers=function()
    local rows={
        setmetatable({GreatPersonIndividualType="GREAT_PERSON_INDIVIDUAL_OTHER"},{__index=forbidden}),
        {GreatPersonIndividualType="GREAT_PERSON_INDIVIDUAL_OWN",ModifierId="MOD_OWN_PLOT"},
        {GreatPersonIndividualType="GREAT_PERSON_INDIVIDUAL_OWN",ModifierId="MOD_OWN_GOLD"}}
    local i=0;return function() i=i+1;return rows[i] end
end
GameInfo.ModifierArguments=forbidden
GameInfo.Modifiers=forbidden
GameEffects={
    GetModifierTextKey=function(id,context)
        assert((id=="MOD_OWN_PLOT" or id=="MOD_OWN_GOLD") and context=="Summary")
        return "LOC_"..id
    end,
    GetModifierText=function(id,key)
        assert(key=="LOC_"..id)
        if id=="MOD_OWN_PLOT" then return "获得当前地块。" end
        if id=="MOD_OWN_GOLD" then return "获得40金币。" end
        return forbidden()
    end,
    GetModifiers=forbidden
}
local lookup=Locale.Lookup
Locale.Lookup=function(key,...)
    local args={...}
    if key=="LOC_UI_PEDIA_GREATPERSON_ACTION" then
        local name=args[1]=="LOC_GREATPERSON_ACTION_NAME_DEFAULT" and "激活" or lookup(args[1])
        return name.."（"..args[2].."次）"
    end
    if key=="LOC_GREATPERSON_ACTION_USAGE_FOUND_RELIGION" then return "创建宗教。" end
    assert(key~="获得当前地块。" and key~="获得40金币。","formatted Summary must not be re-localized")
    return lookup(key,...)
end
'''


def test_owned_great_person_static_ability_survives_ineligible_location(engine):
    vm, run = engine
    vm.execute(LABELS + OWN_ABILITY)
    rows = indexed(run("unit_details", {"unit_id": 10}, True))
    ability = rows["great_person_ability"]
    assert ability["name"] == "激活（3次）"
    assert ability["description"] == "获得当前地块。[NEWLINE]获得40金币。"
    assert "value" not in ability and "action" not in ability
    assert rows["great_person_charges"]["value"] == 2  # remaining differs from original ability uses
    assert "great_person_action" not in rows
    assert len(vm.globals().calls) == 0


def test_owned_great_person_effect_override_precedes_modifier_text(engine):
    vm, run = engine
    vm.execute(LABELS + OWN_ABILITY + '''
ability_row.ActionNameTextOverride="LOC_PERSON_ACTION"
ability_row.ActionEffectTextOverride="LOC_PERSON_EFFECT"
GameInfo.GreatPersonIndividualActionModifiers=forbidden
GameEffects.GetModifierTextKey=forbidden
GameEffects.GetModifierText=forbidden
''')
    row = indexed(run("unit_details", {"unit_id": 10}, True))["great_person_ability"]
    assert row["name"] == "建立图书馆（3次）"
    assert row["description"] == "立即建造一座图书馆。"


@pytest.mark.parametrize("change", [
    "GameEffects=nil",
    "GameEffects.GetModifierTextKey=nil",
    "GameEffects.GetModifierText=nil",
    "GameEffects.GetModifierTextKey=function() error('SECRET_TEXT_ERROR') end",
    "GameEffects.GetModifierText=function() return {} end",
    "GameEffects.GetModifierText=function() return 'bad\\0text' end",
])
def test_optional_static_ability_failure_preserves_owned_identity_without_fabricating_effect(engine, change):
    vm, run = engine
    vm.execute(LABELS + OWN_ABILITY + change)
    rows = indexed(run("unit_details", {"unit_id": 10}, True))
    assert rows["great_person"]["name"] == "希帕蒂娅"
    assert rows["great_person_charges"]["value"] == 2
    assert "great_person_ability" not in rows


def test_ability_scan_has_a_bound_and_does_not_expose_partial_text(engine):
    vm, run = engine
    vm.execute(LABELS + OWN_ABILITY + '''
GameInfo.GreatPersonIndividualActionModifiers=function()
    return function() return {GreatPersonIndividualType="GREAT_PERSON_INDIVIDUAL_OTHER"} end
end
''')
    rows = indexed(run("unit_details", {"unit_id": 10}, True))
    assert "great_person_ability" not in rows and "great_person" in rows


def test_foreign_unit_cannot_trigger_static_ability_or_timeline_reads(engine):
    vm, run = engine
    vm.execute(LABELS + OWN_ABILITY + '''
settings.owner=1
unit.GetGreatPerson=forbidden
GameInfo.GreatPersonIndividuals=setmetatable({},{__index=forbidden})
GameInfo.GreatPersonIndividualActionModifiers=forbidden
GameEffects.GetModifierTextKey=forbidden
''')
    assert run("unit_details", {"unit_id": 10}, True)["items"] == []


def test_no_active_charges_definition_does_not_probe_modifier_summaries(engine):
    vm, run = engine
    vm.execute(LABELS + OWN_ABILITY + '''
ability_row.ActionCharges=0
GameInfo.GreatPersonIndividualActionModifiers=forbidden
''')
    assert "great_person_ability" not in indexed(run("unit_details", {"unit_id": 10}, True))


def test_prophet_ability_uses_exact_civilopedia_special_case(engine):
    vm, run = engine
    vm.execute(LABELS + OWN_ABILITY + '''
ability_row.GreatPersonClassType="GREAT_PERSON_CLASS_PROPHET"
ability_row.ActionCharges=0
GameInfo.GreatPersonIndividualActionModifiers=forbidden
''')
    row = indexed(run("unit_details", {"unit_id": 10}, True))["great_person_ability"]
    assert row["description"] == "创建宗教。" and "value" not in row and "action" not in row
