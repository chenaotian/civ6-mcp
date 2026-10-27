"""Unlocked government cards use current-rule texts and stock base slot counts."""
import pytest

from test_extension_empire import engine


GOV = "GOVERNMENT_MERCHANT_REPUBLIC"
SETUP = r'''
merchant={GovernmentType='GOVERNMENT_MERCHANT_REPUBLIC',Hash=700,Index=7,Name='LOC_MERCHANT_NAME',
    InherentBonusDesc='LOC_MERCHANT_INHERENT_XP1',AccumulatedBonusDesc='LOC_MERCHANT_BONUS_XP1',
    AccumulatedBonusShortDesc='LOC_MERCHANT_BONUS_SHORT',
    InfluencePointsPerTurn=5,InfluencePointsThreshold=150,InfluenceTokensPerThreshold=2}
locked=setmetatable({GovernmentType='GOVERNMENT_LOCKED',Hash=900,Index=9},{__index=forbid})
GameInfo.Governments=defs('GovernmentType',{GameInfo.Governments[0],merchant,locked})
culture.IsGovernmentUnlocked=function(self,hash) return hash~=900 end
GameInfo.Government_SlotCounts=defs('GovernmentType',{
    {GovernmentType='GOVERNMENT_MERCHANT_REPUBLIC',GovernmentSlotType='SLOT_MILITARY',NumSlots=1},
    {GovernmentType='GOVERNMENT_MERCHANT_REPUBLIC',GovernmentSlotType='SLOT_ECONOMIC',NumSlots=2},
    {GovernmentType='GOVERNMENT_MERCHANT_REPUBLIC',GovernmentSlotType='SLOT_DIPLOMATIC',NumSlots=2},
    {GovernmentType='GOVERNMENT_MERCHANT_REPUBLIC',GovernmentSlotType='SLOT_WILDCARD',NumSlots=1},
    setmetatable({GovernmentType='GOVERNMENT_LOCKED',Index=false,Hash=false},{__index=forbid})})
GameInfo.Governments_XP2=defs('GovernmentType',{
    setmetatable({GovernmentType='GOVERNMENT_LOCKED',Index=false,Hash=false},{__index=forbid}),
    {GovernmentType='GOVERNMENT_MERCHANT_REPUBLIC',Favor=2}})
GameInfo.GovernmentSlots.SLOT_MILITARY.Name='Military slots'
GameInfo.GovernmentSlots.SLOT_ECONOMIC.Name='Economic slots'
GameInfo.GovernmentSlots.SLOT_DIPLOMATIC={GovernmentSlotType='SLOT_DIPLOMATIC',Name='Diplomatic slots'}
GameInfo.GovernmentSlots.SLOT_WILDCARD={GovernmentSlotType='SLOT_WILDCARD',Name='Wildcard slots'}
translations={LOC_MERCHANT_NAME='商人共和国',LOC_MERCHANT_INHERENT_XP1='固有效果来自当前规则',
    LOC_MERCHANT_BONUS_XP1='本规则集区域生产加成',LOC_MERCHANT_BONUS_SHORT='附加效果简述'}
Locale={Lookup=function(key,...)
    if key=='LOC_GOVT_INFLUENCE_POINTS_TOWARDS_ENVOYS' then
        local a,b,c=...;return 'Influence '..a..' per turn; '..b..' grants '..c
    elseif key=='LOC_GOVT_FAVOR_PER_TURN' then local favor=...;return 'Favor '..favor..' per turn' end
    return translations[key] or key
end}
GameInfo.GovernmentModifiers=setmetatable({},{__call=forbid,__index=forbid})
GameInfo.ModifierArguments=setmetatable({},{__call=forbid,__index=forbid})
culture.GetFlatBonus=forbid;culture.GetIncrementingBonus=forbid
'''


def rows(run):
    out = run("government", {}, True)
    assert out["supported"] is True
    return {item["id"]: item for item in out["items"].values()}


def test_unlocked_government_has_current_rules_text_stats_and_base_slot_preview(engine):
    vm, run = engine
    vm.execute(SETUP)
    items = rows(run)
    candidate = items[GOV]
    assert candidate["name"] == "商人共和国"
    assert "固有效果来自当前规则" in candidate["description"]
    assert "本规则集区域生产加成" in candidate["description"]
    assert "Influence 5 per turn; 150 grants 2" in candidate["description"]
    assert "Favor 2 per turn" in candidate["description"]
    assert "不含额外槽位" in candidate["description"]
    assert candidate["action"]["government"] == GOV
    for slot, count in (("MILITARY", 1), ("ECONOMIC", 2), ("DIPLOMATIC", 2), ("WILDCARD", 1)):
        assert items[f"{GOV}:base_slots:SLOT_{slot}"]["value"] == count
    assert items[f"{GOV}:base_slots:total"]["value"] == 6
    assert items[f"{GOV}:favor_per_turn"]["value"] == 2
    assert items[f"{GOV}:influence_points_threshold"]["value"] == 150
    assert not any("LOCKED" in key for key in items)
    # Actual current slots are independently supplied by culture, not overwritten.
    assert items["slot:0"]["value"] == "SLOT_MILITARY"
    assert items["slot:1"]["value"] == "SLOT_ECONOMIC"
    assert "slot:2" not in items
    assert len(vm.globals().calls) == 0


def test_locked_government_is_filtered_before_names_descriptions_or_detail_rows(engine):
    vm, run = engine
    vm.execute(SETUP + "\nculture.IsGovernmentUnlocked=function(self,hash) return hash==104 end")
    vm.execute("setmetatable(merchant,{__index=forbid});merchant.InherentBonusDesc=nil;merchant.AccumulatedBonusDesc=nil")
    assert not any(key.startswith(GOV) for key in rows(run))


def test_effects_follow_runtime_replacement_text_without_hardcoded_government_values(engine):
    vm, run = engine
    vm.execute(SETUP + "\nmerchant.InherentBonusDesc='自定义当前公开效果';merchant.AccumulatedBonusDesc='已加载规则替换效果'")
    description = rows(run)[GOV]["description"]
    assert "自定义当前公开效果" in description and "已加载规则替换效果" in description
    assert "固有效果来自当前规则" not in description


@pytest.mark.parametrize("mutation", [
    "GameInfo.Government_SlotCounts=nil",
    "GameInfo.Government_SlotCounts=setmetatable({},{__call=function() error('optional slots unavailable') end})",
    "GameInfo.Government_SlotCounts=defs('GovernmentType',{})",
    "GameInfo.Government_SlotCounts=defs('GovernmentType',{{GovernmentType='GOVERNMENT_MERCHANT_REPUBLIC',GovernmentSlotType='SLOT_ECONOMIC',NumSlots=-1}})",
    "GameInfo.Government_SlotCounts=defs('GovernmentType',{{GovernmentType='GOVERNMENT_MERCHANT_REPUBLIC',GovernmentSlotType='SLOT_ECONOMIC',NumSlots=1.5}})",
    "GameInfo.Government_SlotCounts=defs('GovernmentType',{{GovernmentType='GOVERNMENT_MERCHANT_REPUBLIC',GovernmentSlotType='SLOT_UNKNOWN',NumSlots=2}})",
])
def test_missing_or_incomplete_slot_data_omits_counts_without_losing_effects_or_action(engine, mutation):
    vm, run = engine
    vm.execute(SETUP + "\n" + mutation)
    items = rows(run)
    assert items[GOV]["action"] is not None and "本规则集区域生产加成" in items[GOV]["description"]
    assert not any(key.startswith(GOV + ":base_slots:") for key in items)


def test_stock_great_person_slot_is_counted_as_wildcard_with_real_zero_counts(engine):
    vm, run = engine
    vm.execute(SETUP + """
GameInfo.Government_SlotCounts=defs('GovernmentType',{
    {GovernmentType='GOVERNMENT_MERCHANT_REPUBLIC',GovernmentSlotType='SLOT_GREAT_PERSON',NumSlots=1}})
""")
    items = rows(run)
    assert items[GOV + ":base_slots:SLOT_WILDCARD"]["value"] == 1
    assert items[GOV + ":base_slots:SLOT_ECONOMIC"]["value"] == 0
    assert items[GOV + ":base_slots:total"]["value"] == 1


@pytest.mark.parametrize("mutation", [
    "GameInfo.Governments_XP2=nil",
    "GameInfo.Governments_XP2=setmetatable({},{__call=function() error('optional favor unavailable') end})",
    "GameInfo.Governments_XP2=defs('GovernmentType',{{GovernmentType='GOVERNMENT_MERCHANT_REPUBLIC',Favor=-1}})",
])
def test_optional_gs_favor_is_not_invented(engine, mutation):
    vm, run = engine
    vm.execute(SETUP + "\n" + mutation)
    items = rows(run)
    assert GOV + ":favor_per_turn" not in items
    assert items[GOV]["action"] is not None and items[GOV + ":base_slots:total"]["value"] == 6


@pytest.mark.parametrize("rule", ["RULESET_STANDARD", "RULESET_EXPANSION_1"])
def test_non_gs_rules_do_not_read_gs_favor_table(engine, rule):
    vm, run = engine
    vm.execute(SETUP + f"\ncontrols.rules='{rule}';GameInfo.Governments_XP2=setmetatable({{}},{{__call=forbid}})")
    assert GOV + ":favor_per_turn" not in rows(run)


def test_missing_effect_or_localization_omits_only_optional_text(engine):
    vm, run = engine
    vm.execute(SETUP + """
merchant.InherentBonusDesc=nil
merchant.AccumulatedBonusDesc='LOC_UNRESOLVED'
merchant.AccumulatedBonusShortDesc=nil
""")
    item = rows(run)[GOV]
    assert "固有效果" not in item["description"] and "规则集效果" not in item["description"]
    assert "LOC_UNRESOLVED" not in item["description"] and item["action"] is not None


def test_effect_localization_failure_uses_short_description_without_failing_government_query(engine):
    vm, run = engine
    vm.execute(SETUP + """
local old=Locale.Lookup
Locale.Lookup=function(key,...) if key=='LOC_MERCHANT_BONUS_XP1' then error('missing text') end;return old(key,...) end
""")
    assert "附加效果简述" in rows(run)[GOV]["description"]


def test_government_preview_does_not_open_a_closed_change_window(engine):
    vm, run = engine
    vm.execute(SETUP + "\ncontrols.government_changed=true")
    item = rows(run)[GOV]
    assert item["action"] is None and "本规则集区域生产加成" in item["description"]
