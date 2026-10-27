"""Empire decisions using the shipped player UI requests, never debug setters.

See docs/EMPIRE_ACTIONS.md for exact source paths and important constraints.
Query records contain only own state, public rule definitions, or a currently
visible city selected by the caller. Unsupported game APIs fail closed.
"""

from .base import ActionSpec, QuerySpec, lua, own_city
from .government_preview import GOVERNMENT_PREVIEW
from .city_costs import CITY_COST_HELPERS, CITY_PURCHASE_HELPERS, CITY_PRODUCTION_DIAGNOSTICS
from .city_districts import CITY_DISTRICT_HELPERS
from .great_person_details import GP_MENU_HELPERS, GP_POINT_OBSERVATION
from .era_details import ERA_OBSERVATION


_STRATEGIC = """
if type(Game.IsAllowStrategicCommands) ~= 'function'
    or Game.IsAllowStrategicCommands(me) ~= true then return end
"""

_QUERY_HELPERS = """
out.supported = false
local function label(s)
    if type(s) ~= 'string' then return nil end
    if Locale and type(Locale.Lookup) == 'function' then return Locale.Lookup(s) end
    return s
end
local function add(id, name, description, value, action)
    if #out.items >= 2048 then error('unavailable') end
    table.insert(out.items, {id=tostring(id), name=label(name), description=label(description),
        value=value, action=action, scope='self', owner_id=me})
end
"""

_GOVERNORS = """
if type(player.GetGovernors) ~= 'function' or not GameInfo.Governors then return end
local governors = player:GetGovernors()
if not governors then return end
"""

_GOVERNOR_CONSIDERATION = """
local function governor_title_considered()
    if type(governors.HasTitleBeenConsidered) ~= 'function' then return nil end
    local ok, value = pcall(governors.HasTitleBeenConsidered, governors)
    if ok and type(value) == 'boolean' then return value end
    return nil
end
"""

# GS replaces IsPolicyAvailable, not merely the policy card renderer:
# Expansion2.modinfo:426-431 -> GovernmentScreen_Expansion2.lua:8-13.
# Its CanPolicyBeSlotted includes age/era eligibility that IsPolicyUnlocked
# alone does not establish. Base GovernmentScreen.lua:2224-2228 is inherited
# unchanged by Expansion1. Both discovery and submission use the active rule.
_POLICY_MENU = """
local function policy_menu(culture)
    if not culture or not GameConfiguration or type(GameConfiguration.GetValue) ~= 'function'
        or type(culture.IsPolicyObsolete) ~= 'function' then
        out.supported=false; return nil
    end
    local rules = GameConfiguration.GetValue('RULESET')
    if rules == 'RULESET_EXPANSION_2' then
        if type(culture.IsPolicyBanned) ~= 'function' or type(culture.CanPolicyBeSlotted) ~= 'function' then
            out.supported=false; return nil
        end
        return function(hash)
            return culture:IsPolicyBanned(hash) == false
                and culture:CanPolicyBeSlotted(hash) == true
                and culture:IsPolicyObsolete(hash) == false
        end
    elseif rules == 'RULESET_STANDARD' or rules == 'RULESET_EXPANSION_1' then
        if type(culture.IsPolicyUnlocked) ~= 'function' then out.supported=false; return nil end
        return function(hash)
            return culture:IsPolicyUnlocked(hash) == true and culture:IsPolicyObsolete(hash) == false
        end
    end
    out.supported=false; return nil
end
"""


def _player_request(operation, params):
    entries = "\n".join(f"p[PlayerOperations.{key}] = {value}" for key, value in params.items())
    checks = " or ".join(f"PlayerOperations.{key} == nil" for key in params)
    return f"""
if not PlayerOperations or type(PlayerOperations.{operation}) ~= 'number'
    or type(UI.RequestPlayerOperation) ~= 'function' then return end
if {checks or 'false'} then return end
local p = {{}}
{entries}
attempt(UI.RequestPlayerOperation, me, PlayerOperations.{operation}, p)
"""


def _governor(a):
    return _STRATEGIC + _GOVERNORS + f"""
local row = GameInfo.Governors[{lua(a['governor'])}]
if not row or type(row.Hash) ~= 'number' or type(row.Index) ~= 'number' then return end
"""


def _appoint(a):
    return _governor(a) + """
if governors:HasGovernor(row.Hash) or governors:CanEverAppointGovernor(row.Hash) ~= true
    or governors:CanAppoint() ~= true then return end
""" + _player_request("APPOINT_GOVERNOR", {"PARAM_GOVERNOR_TYPE": "row.Index"})


def _promote(a):
    return _governor(a) + f"""
if governors:HasGovernor(row.Hash) ~= true then return end
local promotion = GameInfo.GovernorPromotions[{lua(a['promotion'])}]
if not promotion or type(promotion.Index) ~= 'number' then return end
if governors:CanEarnPromotion(row.Hash, promotion.Hash) ~= true then return end
local belongs = false
for link in GameInfo.GovernorPromotionSets() do
    if link.GovernorType == row.GovernorType and link.GovernorPromotion == promotion.GovernorPromotionType then belongs = true; break end
end
if not belongs then return end
""" + _player_request("PROMOTE_GOVERNOR", {"PARAM_GOVERNOR_TYPE": "row.Index", "PARAM_GOVERNOR_PROMOTION_TYPE": "promotion.Index"})


def _assign(a):
    return _governor(a) + f"""
if governors:HasGovernor(row.Hash) ~= true then return end
if GameInfo.GovernorsCannotAssign then
    for restriction in GameInfo.GovernorsCannotAssign() do
        if restriction.GovernorType == row.GovernorType and restriction.CannotAssign then return end
    end
end
local city
if {a['owner_id']} == me then
    city = find_owned('Cities', {a['city_id']})
else
    if not known_player({a['owner_id']}) or not visible_plot({a['x']}, {a['y']}) then return end
    city = CityManager.GetCityAt({a['x']}, {a['y']})
end
if not city or city:GetOwner() ~= {a['owner_id']} or city:GetID() ~= {a['city_id']}
    or city:GetX() ~= {a['x']} or city:GetY() ~= {a['y']} then return end
if governors:CanAssignGovernor(row.Hash, city, true) ~= true then return end
""" + _player_request("ASSIGN_GOVERNOR", {"PARAM_GOVERNOR_TYPE": "row.Index", "PARAM_PLAYER_ONE": str(a["owner_id"]), "PARAM_CITY_DEST": str(a["city_id"])})


def _great_person(a, verb):
    check, operation = {"recruit": ("CanRecruitPerson", "RECRUIT_GREAT_PERSON"), "pass": ("CanRejectPerson", "REJECT_GREAT_PERSON"), "patronize": ("CanPatronizePerson", "PATRONIZE_GREAT_PERSON")}[verb]
    yield_arg = f", YieldTypes.{a['yield']}" if verb == "patronize" else ""
    body = _STRATEGIC + GP_MENU_HELPERS + f"""
local row = GameInfo.GreatPersonIndividuals[{lua(a['individual'])}]
if not row or type(row.Index) ~= 'number' or type(Game.GetGreatPeople) ~= 'function' then return end
local people = Game.GetGreatPeople()
if not people or type(people.GetTimeline) ~= 'function' then return end
local timeline = people:GetTimeline()
if type(timeline) ~= 'table' then return end
local individual,recruit_cost
for _, entry in ipairs(timeline) do
    local offered = GameInfo.GreatPersonIndividuals[entry.Individual]
    -- A pending own claim remains on the current board with Claimant=me.
    -- GreatPeoplePopup.PopulateData (710-739) keeps it eligible for CanRecruit.
    if (entry.Claimant == nil or entry.Claimant == me) and offered
        and offered.GreatPersonIndividualType == row.GreatPersonIndividualType then
        individual = entry.Individual; recruit_cost=entry.Cost; break
    end
end
if individual == nil or people:{check}(me, individual{yield_arg}) ~= true then return end
"""
    params = {"PARAM_GREAT_PERSON_INDIVIDUAL_TYPE": "individual"}
    if verb == "patronize":
        body += f"local price,allowed=gp_patronage(people,individual,{lua(a['yield'])})\nif not allowed then return end\n"
        params["PARAM_YIELD_TYPE"] = f"YieldTypes.{a['yield']}"
    else:
        capability = "RECRUIT" if verb == "recruit" else "REJECT"
        body += f"if not gp_capability('CAPABILITY_GREAT_PEOPLE_CAN_{capability}') then return end\n"
        cost = "recruit_cost" if verb == "recruit" else "gp_read(people,'GetRejectCost',me,individual)"
        body += f"if not gp_number({cost}) then return end\n"
    return body + _player_request(operation, params)


def _government(a):
    return _STRATEGIC + f"""
local culture = player:GetCulture()
local row = GameInfo.Governments[{lua(a['government'])}]
if not row or culture:CanChangeGovernmentAtAll() ~= true
    or culture:IsGovernmentUnlocked(row.Hash) ~= true
    or culture:GovernmentChangeMade() ~= false then return end
local current = GameInfo.Governments[culture:GetCurrentGovernment()]
if current and culture:CivicCompletedThisTurn() ~= true then return end
attempt(culture.RequestChangeGovernment, culture, row.Hash)
"""


def _government_keep(_):
    return _STRATEGIC + """
local culture = player:GetCulture()
if type(culture.SetGovernmentChangeConsidered) ~= 'function'
    or culture:GovernmentChangeConsidered() ~= false then return end
attempt(culture.SetGovernmentChangeConsidered, culture, true)
"""


def _governor_defer(_):
    return _STRATEGIC + _GOVERNORS + _GOVERNOR_CONSIDERATION + """
if type(governors.SetTitleConsidered) ~= 'function'
    or governor_title_considered() ~= false then return end
attempt(governors.SetTitleConsidered, governors, true)
"""


def _policies(a):
    return _STRATEGIC + _POLICY_MENU + f"""
local culture = player:GetCulture()
local policy_available = policy_menu(culture)
if not policy_available then return end
if culture:PolicyChangeMade() ~= false or culture:GetCostToUnlockPolicies() ~= 0 then return end
local selections = {lua(a['slots'])}
local count = culture:GetNumPolicySlots()
if #selections ~= count or count > 128 then return end
local clear, add, seen = {{}}, {{}}, {{}}
for index, selection in ipairs(selections) do
    if selection.slot < 0 or selection.slot >= count or add[selection.slot] ~= nil then return end
    local row = GameInfo.Policies[selection.policy]
    if not row or seen[row.Hash] or policy_available(row.Hash) ~= true then return end
    local slot = GameInfo.GovernmentSlots[culture:GetSlotType(selection.slot)]
    if not slot or (slot.GovernmentSlotType ~= 'SLOT_WILDCARD' and slot.GovernmentSlotType ~= row.GovernmentSlotType) then return end
    seen[row.Hash] = true
    clear[#clear + 1] = selection.slot
    add[selection.slot] = row.Hash
end
attempt(culture.RequestPolicyChanges, culture, clear, add)
"""


def _unlock(_):
    return _STRATEGIC + """
local culture = player:GetCulture()
if culture:PolicyChangeMade() ~= false or culture:GetCostToUnlockPolicies() <= 0 then return end
local cost = culture:GetCostToUnlockPolicies()
if not GlobalParameters or type(GlobalParameters.GOVERNMENT_UNLOCK_WITH_FAITH) ~= 'number' then return end
if GlobalParameters.GOVERNMENT_UNLOCK_WITH_FAITH ~= 0 then
    if player:GetReligion():GetFaithBalance() < cost then return end
elseif player:GetTreasury():GetGoldBalance() < cost then return end
""" + _player_request("UNLOCK_POLICIES", {})


def _dedications(a):
    return _STRATEGIC + f"""
if type(Game.GetEras) ~= 'function' then return end
local eras = Game.GetEras()
local selected = {lua(a['dedications'])}
local allowed = eras:GetPlayerNumAllowedCommemorations(me)
if allowed < 1 or #selected ~= allowed then return end
local choices, selected_rows, seen = eras:GetPlayerCommemorateChoices(me), {{}}, {{}}
for _, id in ipairs(selected) do
    local row = GameInfo.CommemorationTypes[id]
    if not row or seen[row.Index] then return end
    local found = false
    for _, index in ipairs(choices) do if index == row.Index then found = true; break end end
    if not found then return end
    selected_rows[#selected_rows + 1] = row.Index
    seen[row.Index] = true
end
if not PlayerOperations or type(PlayerOperations.COMMEMORATE) ~= 'number'
    or PlayerOperations.PARAM_COMMEMORATION_TYPE == nil then return end
for _, index in ipairs(selected_rows) do
    local p = {{[PlayerOperations.PARAM_COMMEMORATION_TYPE]=index}}
    attempt(UI.RequestPlayerOperation, me, PlayerOperations.COMMEMORATE, p)
end
"""

_RELIGION = """
local religion = player:GetReligion()
local religions = Game.GetReligion()
if not religion or not religions then return end
local equipped = 0
if religion:GetReligionTypeCreated() >= 0 then
    -- Match only our founder id before inspecting the beliefs field. Foreign
    -- religion identities, followers, cities and counts are never projected.
    for _, info in ipairs(religions:GetReligions()) do
        if info.Founder == me then
            for _ in pairs(info.Beliefs) do equipped = equipped + 1 end
            break
        end
    end
end
local remaining_beliefs = religion:GetNumBeliefsEarned() - equipped
local function belief_available(row, pantheon)
    return row and ((row.BeliefClassType == 'BELIEF_CLASS_PANTHEON') == pantheon)
        and not religions:IsInSomePantheon(row.Index)
        and not religions:IsInSomeReligion(row.Index)
        and not religions:IsTooManyForReligion(row.Index, religion:GetReligionTypeCreated())
end
"""


def _belief(a, pantheon):
    eligibility = ("if religion:CanCreatePantheon() ~= true then return end\n" if pantheon else
                   "if religion:GetReligionTypeCreated() < 0 or remaining_beliefs <= 0 then return end\n")
    return _STRATEGIC + _RELIGION + eligibility + f"""
local row = GameInfo.Beliefs[{lua(a['belief'])}]
if not belief_available(row, {lua(pantheon)}) then return end
if {lua(not pantheon)} and equipped == 0 and row.BeliefClassType ~= 'BELIEF_CLASS_FOLLOWER' then return end
""" + _player_request("FOUND_PANTHEON" if pantheon else "ADD_BELIEF", {"PARAM_BELIEF_TYPE": "row.Hash", "PARAM_INSERT_MODE": "PlayerOperations.VALUE_EXCLUSIVE"})


def _found_religion(a):
    return _STRATEGIC + _RELIGION + f"""
if religion:GetReligionTypeCreated() >= 0 or remaining_beliefs <= 0 then return end
local row = GameInfo.Religions[{lua(a['religion'])}]
if not row or row.Pantheon or religions:HasBeenFounded(row.Index) then return end
local chosen, selected, classes = {lua(a['beliefs'])}, {{}}, {{}}
if #chosen < 1 or #chosen ~= religion:GetNumBeliefsEarned() then return end
for _, id in ipairs(chosen) do
    local belief = GameInfo.Beliefs[id]
    if not belief_available(belief, false)
        or (#selected == 0 and belief.BeliefClassType ~= 'BELIEF_CLASS_FOLLOWER')
        or classes[belief.BeliefClassType] then return end
    classes[belief.BeliefClassType] = true
    selected[#selected + 1] = belief.Hash
end
if not PlayerOperations or type(PlayerOperations.FOUND_RELIGION) ~= 'number'
    or type(PlayerOperations.ADD_BELIEF) ~= 'number' then return end
local p = {{}}
p[PlayerOperations.PARAM_INSERT_MODE] = PlayerOperations.VALUE_EXCLUSIVE
p[PlayerOperations.PARAM_RELIGION_TYPE] = row.Hash
if row.RequiresCustomName then p[PlayerOperations.PARAM_RELIGION_CUSTOM_NAME] = {lua(a['name'])} end
attempt(UI.RequestPlayerOperation, me, PlayerOperations.FOUND_RELIGION, p)
for _, hash in ipairs(selected) do
    local b = {{[PlayerOperations.PARAM_INSERT_MODE]=PlayerOperations.VALUE_EXCLUSIVE,
        [PlayerOperations.PARAM_BELIEF_TYPE]=hash}}
    attempt(UI.RequestPlayerOperation, me, PlayerOperations.ADD_BELIEF, b)
end
"""

_ITEM_TABLES = {"UNIT": ("Units", "UNIT"), "BUILDING": ("Buildings", "BUILDING"), "DISTRICT": ("Districts", "DISTRICT"), "PROJECT": ("Projects", "PROJECT")}

_PRODUCTION_ELIGIBILITY = """
local function can_show_build(row, kind, formation)
    local build = row.Hash
    if kind == 'Units' then
        build = {UnitType=row.Hash, MilitaryFormationType=formation}
    end
    -- The stock production UI performs this exclusion/visibility stage before
    -- its separate current-constraints check. false alone permits future techs.
    if city:GetBuildQueue():CanProduce(build,true) == true then return true end
    -- The stock district panel also includes existing districts for repairs.
    return kind == 'Districts' and city:GetDistricts():HasDistrict(row.Index) == true
end
"""


def _item(a, namespace):
    table, parameter = _ITEM_TABLES[a["item"].split("_", 1)[0]]
    return f"""
local row = GameInfo.{table}[{lua(a['item'])}]
if not row or row.InternalOnly or type(row.Hash) ~= 'number' then return end
local p = {{}}
p[{namespace}.PARAM_{parameter}_TYPE] = row.Hash
"""


def _build(a):
    table, _ = _ITEM_TABLES[a["item"].split("_", 1)[0]]
    body = _STRATEGIC + own_city(a["city_id"]) + _PRODUCTION_ELIGIBILITY + _item(a, "CityOperationTypes")
    body += f"if not can_show_build(row,{lua(table)},MilitaryFormationTypes.{a['formation']}_MILITARY_FORMATION) then return end\n"
    if a["item"].startswith("BUILDING_"):
        body += "if row.MustPurchase and city:GetBuildings():IsPillaged(row.Hash) ~= true then return end\n"
    else:
        body += "if row.MustPurchase then return end\n"
    body += f"""
p[CityOperationTypes.PARAM_INSERT_MODE] = CityOperationTypes.{'VALUE_APPEND' if a['append'] else 'VALUE_REPLACE_AT'}
"""
    if not a['append']:
        body += "p[CityOperationTypes.PARAM_QUEUE_DESTINATION_LOCATION] = 0\n"
    if a["type"] == "city_build_at":
        body += f"""
local plot = visible_plot({a['x']}, {a['y']})
if not plot or plot:GetOwner() ~= me then return end
p[CityOperationTypes.PARAM_X] = {a['x']}
p[CityOperationTypes.PARAM_Y] = {a['y']}
"""
    else:
        body += "local placed = not row.RequiresPlacement or city:GetBuildQueue():HasBeenPlaced(row.Hash) == true\n"
        if a["item"].startswith("BUILDING_"):
            body += "if not placed then placed = city:GetBuildings():HasBuilding(row.Hash) == true end\n"
        elif a["item"].startswith("DISTRICT_"):
            body += "if not placed then placed = city:GetDistricts():HasDistrict(row.Index) == true end\n"
        body += "if not placed then return end\n"
    if a["item"].startswith("UNIT_"):
        body += f"p[CityOperationTypes.MILITARY_FORMATION_TYPE] = MilitaryFormationTypes.{a['formation']}_MILITARY_FORMATION\n"
    elif a["formation"] != "STANDARD":
        body += "if true then return end\n"
    return body + """
if CityManager.CanStartOperation(city, CityOperationTypes.BUILD, p, false) ~= true then return end
attempt(CityManager.RequestOperation, city, CityOperationTypes.BUILD, p)
"""


def _purchase(a):
    table, _ = _ITEM_TABLES[a["item"].split("_", 1)[0]]
    body = _STRATEGIC + own_city(a["city_id"]) + CITY_PURCHASE_HELPERS + _item(a, "CityCommandTypes")
    body += f"if not city_purchase_in_menu(row,{lua(table)},{lua(a['yield'])}) then return end\n"
    body += f"p[CityCommandTypes.PARAM_YIELD_TYPE] = GameInfo.Yields['YIELD_{a['yield']}'].Index\n"
    if a["item"].startswith("UNIT_"):
        body += f"p[CityCommandTypes.PARAM_MILITARY_FORMATION_TYPE] = MilitaryFormationTypes.{a['formation']}_MILITARY_FORMATION\n"
    elif a["formation"] != "STANDARD":
        body += "if true then return end\n"
    if a["type"] == "city_purchase_at":
        body += f"""
if not visible_plot({a['x']}, {a['y']}) then return end
p[CityCommandTypes.PARAM_X] = {a['x']}
p[CityCommandTypes.PARAM_Y] = {a['y']}
"""
    else:
        body += "if row.RequiresPlacement and city:GetBuildQueue():HasBeenPlaced(row.Hash) ~= true then return end\n"
    return body + """
if CityManager.CanStartCommand(city, CityCommandTypes.PURCHASE, true, p, false) ~= true
    or CityManager.CanStartCommand(city, CityCommandTypes.PURCHASE, false, p, false) ~= true then return end
""" + f"if not city_can_afford(row,{lua(a['yield'])},{lua(a['formation'])}) then return end\n" + """
attempt(CityManager.RequestCommand, city, CityCommandTypes.PURCHASE, p)
"""


def _tile(a, mode):
    command, flag = {"purchase": ("PURCHASE", "PARAM_PLOT_PURCHASE"), "citizen": ("MANAGE", "PARAM_MANAGE_CITIZEN"), "swap": ("SWAP_TILE_OWNER", "PARAM_SWAP_TILE_OWNER")}[mode]
    body = _STRATEGIC + own_city(a["city_id"]) + CITY_PURCHASE_HELPERS + f"""
local plot = visible_plot({a['x']}, {a['y']})
if not plot then return end
if {lua(mode != 'purchase')} and plot:GetOwner() ~= me then return end
if type(UI.GetInterfaceModeParameter) ~= 'function' then return end
local p = {{[CityCommandTypes.{flag}]=UI.GetInterfaceModeParameter(CityCommandTypes.{flag}),
    [CityCommandTypes.PARAM_X]={a['x']}, [CityCommandTypes.PARAM_Y]={a['y']}}}
if CityManager.CanStartCommand(city, CityCommandTypes.{command}, false, p, false) ~= true then return end
"""
    if mode == 'purchase':
        body += "if type(plot.GetIndex) ~= 'function' or not city_can_afford_plot(plot:GetIndex()) then return end\n"
    return body + f"attempt(CityManager.RequestCommand, city, CityCommandTypes.{command}, p)\n"


def _focus(a):
    return _STRATEGIC + own_city(a["city_id"]) + f"""
local row = GameInfo.Yields[{lua(a['yield'])}]
if not row then return end
local p = {{[CityCommandTypes.PARAM_YIELD_TYPE]=row.Index}}
-- Both switches are explicit, avoiding the UI's toggle state ambiguity.
p[CityCommandTypes.PARAM_FLAGS] = 0
p[CityCommandTypes.PARAM_DATA0] = {1 if a['focus'] == 'favored' else 0}
attempt(CityManager.RequestCommand, city, CityCommandTypes.SET_FOCUS, p)
local q = {{[CityCommandTypes.PARAM_YIELD_TYPE]=row.Index,
    [CityCommandTypes.PARAM_FLAGS]=1,
    [CityCommandTypes.PARAM_DATA0]={1 if a['focus'] == 'disfavored' else 0}}}
attempt(CityManager.RequestCommand, city, CityCommandTypes.SET_FOCUS, q)
"""


def _rename_city(a):
    return _STRATEGIC + own_city(a["city_id"]) + f"""
if not GameCapabilities or type(GameCapabilities.HasCapability) ~= 'function'
    or GameCapabilities.HasCapability('CAPABILITY_RENAME') ~= true then return end
if not CityCommandTypes or type(CityCommandTypes.NAME_CITY) ~= 'number'
    or CityCommandTypes.PARAM_NAME == nil or type(CityManager.RequestCommand) ~= 'function' then return end
local p = {{[CityCommandTypes.PARAM_NAME]={lua(a['name'])}}}
attempt(CityManager.RequestCommand, city, CityCommandTypes.NAME_CITY, p)
"""


def _queue(a):
    body = _STRATEGIC + own_city(a["city_id"]) + f"""
local count = city:GetBuildQueue():GetSize()
if {a['index']} >= count then return end
local p = {{}}
"""
    if a["type"] == "city_queue_remove":
        body += f"p[CityOperationTypes.PARAM_INSERT_MODE] = CityOperationTypes.VALUE_REMOVE_AT\np[CityOperationTypes.PARAM_QUEUE_LOCATION] = {a['index']}\n"
    else:
        body += f"""
if {a['destination']} >= count then return end
p[CityOperationTypes.PARAM_INSERT_MODE] = CityOperationTypes.VALUE_MOVE_TO
p[CityOperationTypes.PARAM_QUEUE_SOURCE_LOCATION] = {a['index']}
p[CityOperationTypes.PARAM_QUEUE_DESTINATION_LOCATION] = {a['destination']}
"""
    return body + "attempt(CityManager.RequestOperation, city, CityOperationTypes.BUILD, p)\n"


def _loyalty_choice(a):
    return _STRATEGIC + own_city(a["city_id"]) + f"""
local cities = player:GetCities()
if type(cities.GetNextRebelledCity) ~= 'function' then return end
local pending = cities:GetNextRebelledCity()
if not pending or pending:GetOwner() ~= me or pending:GetID() ~= city:GetID() then return end
local p = {{[UnitOperationTypes.PARAM_FLAGS]=CityDestroyDirectives.{a['choice'].upper()}}}
if CityManager.CanStartCommand(city,CityCommandTypes.DESTROY,p) ~= true then return end
attempt(CityManager.RequestCommand,city,CityCommandTypes.DESTROY,p)
"""


def _loyalty_query(_):
    return _QUERY_HELPERS + """
local cities = player:GetCities()
if type(cities.GetNextRebelledCity) ~= 'function' then return end
out.supported = true
local city = cities:GetNextRebelledCity()
if not city or city:GetOwner() ~= me then return end
for _, choice in ipairs({'KEEP','REJECT'}) do
    local p = {[UnitOperationTypes.PARAM_FLAGS]=CityDestroyDirectives[choice]}
    if CityManager.CanStartCommand(city,CityCommandTypes.DESTROY,p) then
        add('loyalty:'..choice..':'..city:GetID(),city:GetName(),nil,nil,
            {type='city_loyalty_choice',city_id=city:GetID(),choice=string.lower(choice)})
    end
end
"""


def _governors_query(_):
    return _QUERY_HELPERS + _GOVERNORS + _GOVERNOR_CONSIDERATION + """
out.supported = true
add('titles', nil, nil, governors:GetGovernorPoints()-governors:GetGovernorPointsSpent())
local considered = governor_title_considered()
if type(considered) == 'boolean' then
    add('title_considered','已考虑本轮总督选择','原版总督面板显式关闭时设置的确认标记；派驻状态请查看各总督的 assigned 字段。',considered)
end
if considered == false and type(governors.SetTitleConsidered) == 'function' then
    add('governor_defer','确认已查看总督选择','相当于显式关闭原版总督面板，确认已查看本轮选择；保留未花费头衔。之后请重新读取待办，其他待派驻原因仍可能存在。',nil,{type='governor_defer'})
end
for row in GameInfo.Governors() do
    local has = governors:HasGovernor(row.Hash)
    -- CanEverAppointGovernor controls secret society discovery too.
    if has or governors:CanEverAppointGovernor(row.Hash) == true then
        add(row.GovernorType, row.Name, row.Description, has)
        if not has and governors:CanAppoint() then
            add(row.GovernorType..':appoint', row.Name, nil, nil,
                {type='governor_appoint', governor=row.GovernorType})
        end
        if has then
            local appointed = governors:GetGovernor(row.Hash)
            if appointed then
                if type(appointed.IsEstablished) == 'function' then
                    add(row.GovernorType..':established',nil,nil,appointed:IsEstablished())
                end
                if type(appointed.GetTurnsToEstablish) == 'function' and type(appointed.GetTurnsOnSite) == 'function' then
                    add(row.GovernorType..':turns_until_established',nil,nil,
                        math.max(0,appointed:GetTurnsToEstablish()-appointed:GetTurnsOnSite()))
                end
                if type(appointed.GetNeutralizedTurns) == 'function' then
                    add(row.GovernorType..':neutralized_turns',nil,nil,appointed:GetNeutralizedTurns())
                end
                if type(appointed.GetAssignedCity) == 'function' then
                    local assigned = appointed:GetAssignedCity()
                    add(row.GovernorType..':assigned',nil,nil,assigned ~= nil)
                    if assigned then
                        local owner = assigned:GetOwner()
                        if owner == me or (known_player(owner) and visible_plot(assigned:GetX(),assigned:GetY())) then
                            add(row.GovernorType..':assigned_city',assigned:GetName(),nil,assigned:GetID())
                            add(row.GovernorType..':assigned_city_owner',nil,nil,owner)
                        end
                    end
                end
            end
            for link in GameInfo.GovernorPromotionSets() do
                if link.GovernorType == row.GovernorType then
                    local promotion = GameInfo.GovernorPromotions[link.GovernorPromotion]
                    local earned = promotion and appointed and type(appointed.HasPromotion) == 'function'
                        and appointed:HasPromotion(promotion.Hash) == true
                    if earned then
                        add(row.GovernorType..':'..promotion.GovernorPromotionType,promotion.Name,promotion.Description,true)
                    elseif promotion and governors:CanEarnPromotion(row.Hash, promotion.Hash) then
                        -- Own earned or currently earnable promotions only: hidden future society levels never exposed.
                        add(row.GovernorType..':'..promotion.GovernorPromotionType, promotion.Name,
                            promotion.Description, false, {type='governor_promote', governor=row.GovernorType,
                            promotion=promotion.GovernorPromotionType})
                    end
                end
            end
            for _, city in player:GetCities():Members() do
                if city:GetOwner() == me and governors:CanAssignGovernor(row.Hash, city, true) then
                    add(row.GovernorType..':city:'..tostring(city:GetID()), city:GetName(), nil, nil,
                        {type='governor_assign', governor=row.GovernorType, owner_id=me, city_id=city:GetID(), x=city:GetX(), y=city:GetY()})
                end
            end
        end
    end
end
"""


def _great_people_query(_):
    return _QUERY_HELPERS + GP_MENU_HELPERS + """
if type(Game.GetGreatPeople) ~= 'function' then return end
local people = Game.GetGreatPeople()
if not people or type(people.GetTimeline) ~= 'function' then return end
local timeline = people:GetTimeline()
if type(timeline) ~= 'table' then return end
out.supported = true
for _, entry in ipairs(timeline) do
    -- Claimant is also set while our earned person awaits recruit/pass. The
    -- stock CURRENT tab retains it (GreatPeoplePopup:710-739); only its PAST
    -- tab has a claimant filter. Keep this own pending choice without reading
    -- or returning any claimant civilization identity or historical timeline.
    if entry.Claimant == nil or entry.Claimant == me then
        local row = GameInfo.GreatPersonIndividuals[entry.Individual]
        if row then
            add(row.GreatPersonIndividualType, row.Name, entry.ActionEffectText, gp_number(entry.Cost) and entry.Cost or nil)
            if gp_capability('CAPABILITY_GREAT_PEOPLE_CAN_RECRUIT') and people:CanRecruitPerson(me, entry.Individual)==true
                and gp_number(entry.Cost) then
                add(row.GreatPersonIndividualType..':recruit', row.Name, nil, nil,
                    {type='great_person_recruit',individual=row.GreatPersonIndividualType})
            end
            if gp_capability('CAPABILITY_GREAT_PEOPLE_CAN_REJECT') and people:CanRejectPerson(me, entry.Individual)==true then
                local reject_cost=gp_read(people,'GetRejectCost',me,entry.Individual)
                if gp_number(reject_cost) then
                    add(row.GreatPersonIndividualType..':pass', row.Name, nil, nil,
                        {type='great_person_pass',individual=row.GreatPersonIndividualType})
                    add(row.GreatPersonIndividualType..':pass_cost',row.Name,'正常放弃费用',reject_cost)
                end
            end
            for _, yield in ipairs({'GOLD','FAITH'}) do
                local cost,allowed=gp_patronage(people,entry.Individual,yield)
                if cost~=nil then
                    local action
                    if allowed then action={type='great_person_patronize',individual=row.GreatPersonIndividualType,yield=yield} end
                    add(row.GreatPersonIndividualType..':'..yield,row.Name,'正常界面报价；无 action 表示目前不能赞助',cost,action)
                end
            end
        end
    end
end
""" + GP_POINT_OBSERVATION


def _government_query(_):
    return _QUERY_HELPERS + _POLICY_MENU + GOVERNMENT_PREVIEW + """
local culture = player:GetCulture()
if not culture then return end
local policy_available = policy_menu(culture)
if not policy_available then return end
out.supported = true
local current = GameInfo.Governments[culture:GetCurrentGovernment()]
add('current_government', nil, nil, current and current.GovernmentType or 'NONE')
add('policy_unlock_cost', nil, nil, culture:GetCostToUnlockPolicies())
add('policy_change_made', nil, nil, culture:PolicyChangeMade())
if type(culture.GovernmentChangeConsidered) == 'function' and culture:GovernmentChangeConsidered() == false then
    add('government_keep',nil,'Keep the present government and acknowledge the normal UI reminder.',nil,{type='government_keep'})
end
if culture:GetCostToUnlockPolicies() > 0 and not culture:PolicyChangeMade() then
    add('unlock_policies', nil, nil, nil, {type='unlock_policies'})
end
for row in GameInfo.Governments() do
    if culture:IsGovernmentUnlocked(row.Hash) == true then
        local action
        if culture:CanChangeGovernmentAtAll() and not culture:GovernmentChangeMade()
            and (not current or culture:CivicCompletedThisTurn()) then
            action={type='change_government',government=row.GovernmentType}
        end
        add(row.GovernmentType, row.Name, nil, nil, action)
        government_preview(row,out.items[#out.items])
    end
end
for row in GameInfo.Policies() do
    if policy_available(row.Hash) then
        add(row.PolicyType, row.Name, row.Description, row.GovernmentSlotType)
    end
end
local n = culture:GetNumPolicySlots()
if n > 128 then error('unavailable') end
for index=0,n-1 do
    local slot = GameInfo.GovernmentSlots[culture:GetSlotType(index)]
    local policy = GameInfo.Policies[culture:GetSlotPolicy(index)]
    add('slot:'..index, nil, policy and policy.PolicyType or 'NONE', slot.GovernmentSlotType)
end
"""


def _dedications_query(_):
    return _QUERY_HELPERS + """
if type(Game.GetEras) ~= 'function' then return end
local eras = Game.GetEras()
out.supported = true
add('selections_required', nil, nil, eras:GetPlayerNumAllowedCommemorations(me))
for _, index in ipairs(eras:GetPlayerCommemorateChoices(me)) do
    local row = GameInfo.CommemorationTypes[index]
    if row then
        local bonus = row.NormalAgeBonusDescription
        if eras:HasGoldenAge(me) then bonus = row.GoldenAgeBonusDescription
        elseif eras:HasDarkAge(me) then bonus = row.DarkAgeBonusDescription end
        add(row.CommemorationType, row.CategoryDescription, bonus)
    end
end
""" + ERA_OBSERVATION


def _religion_query(_):
    return _QUERY_HELPERS + _RELIGION + """
out.supported = true
add('can_found_pantheon', nil, nil, religion:CanCreatePantheon())
add('beliefs_earned', nil, nil, religion:GetNumBeliefsEarned())
add('beliefs_remaining', nil, nil, remaining_beliefs)
add('has_founding_unit', nil, nil, religion:HasReligiousFoundingUnit())
local current = GameInfo.Religions[religion:GetReligionTypeCreated()]
add('founded_religion', nil, nil, current and current.ReligionType or 'NONE')
if remaining_beliefs > 0 and equipped == 0 then
    add('first_belief_class',nil,'The first religion belief must be a follower belief.','BELIEF_CLASS_FOLLOWER')
end
local pantheon = GameInfo.Beliefs[religion:GetPantheon()]
add('pantheon', nil, nil, pantheon and pantheon.BeliefType or 'NONE')
for row in GameInfo.Beliefs() do
    local is_pantheon = row.BeliefClassType == 'BELIEF_CLASS_PANTHEON'
    local choosing = (is_pantheon and religion:CanCreatePantheon()) or (not is_pantheon and remaining_beliefs > 0)
    local first_belief_allowed = is_pantheon or not current or equipped > 0 or row.BeliefClassType == 'BELIEF_CLASS_FOLLOWER'
    if choosing and first_belief_allowed and belief_available(row, is_pantheon) then
        local action
        if is_pantheon and religion:CanCreatePantheon() then
            action={type='found_pantheon',belief=row.BeliefType}
        elseif not is_pantheon and current then action={type='add_belief',belief=row.BeliefType} end
        add(row.BeliefType, row.Name, row.Description, row.BeliefClassType, action)
    end
end
if not current and remaining_beliefs > 0 then
    for row in GameInfo.Religions() do
        if not row.Pantheon and not religions:HasBeenFounded(row.Index) then
            add(row.ReligionType, row.Name, nil, row.RequiresCustomName == true)
        end
    end
end
"""


def _production_query(a):
    return (_QUERY_HELPERS + own_city(a["city_id"]) + _PRODUCTION_ELIGIBILITY
            + CITY_PURCHASE_HELPERS + CITY_COST_HELPERS + CITY_PRODUCTION_DIAGNOSTICS
            + CITY_DISTRICT_HELPERS + """
out.supported = true
local queue = city:GetBuildQueue()
for _, table_name in ipairs({'Units','Buildings','Districts','Projects'}) do
    local column = ({Units='UnitType',Buildings='BuildingType',Districts='DistrictType',Projects='ProjectType'})[table_name]
    local param = ({Units='PARAM_UNIT_TYPE',Buildings='PARAM_BUILDING_TYPE',Districts='PARAM_DISTRICT_TYPE',Projects='PARAM_PROJECT_TYPE'})[table_name]
    for row in GameInfo[table_name]() do
        if not row.InternalOnly then
            local can, formation_results
            local build_menu = can_show_build(row,table_name,MilitaryFormationTypes.STANDARD_MILITARY_FORMATION)
            if build_menu then
                if table_name == 'Units' then
                    can, formation_results = queue:CanProduce({UnitType=row.Hash,MilitaryFormationType=MilitaryFormationTypes.STANDARD_MILITARY_FORMATION},false,true)
                else can, formation_results = queue:CanProduce(row.Hash,false,true) end
            end
            local placed = not row.RequiresPlacement or queue:HasBeenPlaced(row.Hash)
            if not placed and table_name == 'Buildings' then placed = city:GetBuildings():HasBuilding(row.Hash) == true end
            if not placed and table_name == 'Districts' then placed = city:GetDistricts():HasDistrict(row.Index) == true end
            local repair_purchase_only = table_name == 'Buildings' and row.MustPurchase and city:GetBuildings():IsPillaged(row.Hash) == true
            local diagnostic = build_menu and can == false and production_diagnostic_allowed(row,table_name,placed)
            if (can == true or diagnostic) and (not row.MustPurchase or repair_purchase_only) then
                local action
                if can == true and placed then action={type='city_build',city_id=city:GetID(),item=row[column],append=false,formation='STANDARD'} end
                local description = row.Description
                if diagnostic then description = (label(description) or '')..' 当前直接生产检查未通过；仅提供原版可见项目的信息。部分失败原因可能未提供。' end
                local id = row[column]..':build'
                add(id, row.Name, description, not placed, action)
                production_quote(id,row,table_name,'STANDARD')
                production_condition_quote(id,row,table_name,can == true,formation_results)
            end
            if table_name == 'Units' and not row.MustPurchase and formation_results and CityOperationResults then
                for _, formation in ipairs({'CORPS','ARMY'}) do
                    local flag = CityOperationResults['CAN_TRAIN_'..formation]
                    local formation_type = MilitaryFormationTypes[formation..'_MILITARY_FORMATION']
                    if flag ~= nil and formation_results[flag] and formation_type ~= nil
                        and can_show_build(row,table_name,formation_type)
                        and queue:CanProduce({UnitType=row.Hash,MilitaryFormationType=formation_type},false,false) then
                        add(row.UnitType..':build:'..formation,row.Name,row.Description,false,
                            {type='city_build',city_id=city:GetID(),item=row.UnitType,append=false,formation=formation})
                        production_quote(row.UnitType..':build:'..formation,row,table_name,formation)
                    end
                end
            end
            if table_name ~= 'Projects' then
                for _, yield in ipairs({'GOLD','FAITH'}) do
                    local p = {[CityCommandTypes[param]]=row.Hash,[CityCommandTypes.PARAM_YIELD_TYPE]=GameInfo.Yields['YIELD_'..yield].Index}
                    local can_purchase, purchase_results
                    local menu_purchase = city_purchase_in_menu(row,table_name,yield)
                        and CityManager.CanStartCommand(city, CityCommandTypes.PURCHASE, true, p, false) == true
                    if menu_purchase then
                        can_purchase, purchase_results = CityManager.CanStartCommand(city, CityCommandTypes.PURCHASE, false, p, table_name == 'Units')
                    end
                    can_purchase = can_purchase == true and city_can_afford(row,yield,'STANDARD')
                    local price
                    if menu_purchase then
                        price = purchase_quote_value(row,table_name,yield,'STANDARD')
                    end
                    if can_purchase or price ~= nil then
                        local action
                        if can_purchase and placed then action={type='city_purchase',city_id=city:GetID(),item=row[column],yield=yield,formation='STANDARD'} end
                        local description = row.Description
                        if not can_purchase then description = (label(description) or '')..' 当前不可购买；仅提供原版菜单报价。' end
                        local id = row[column]..':buy:'..yield
                        add(id, row.Name, description, not placed, action)
                        purchase_quote(id,price,yield,can_purchase)
                        production_quote(id,row,table_name,'STANDARD',false)
                    end
                    if table_name == 'Units' and purchase_results and CityOperationResults then
                        for _, formation in ipairs({'CORPS','ARMY'}) do
                            local flag = CityOperationResults['CAN_TRAIN_'..formation]
                            local formation_type = MilitaryFormationTypes[formation..'_MILITARY_FORMATION']
                            if flag ~= nil and purchase_results[flag] and formation_type ~= nil then
                                p[CityCommandTypes.PARAM_MILITARY_FORMATION_TYPE] = formation_type
                                local offered = CityManager.CanStartCommand(city, CityCommandTypes.PURCHASE, true, p, false) == true
                                local allowed = offered and CityManager.CanStartCommand(city, CityCommandTypes.PURCHASE, false, p, false) == true
                                    and city_can_afford(row,yield,formation)
                                local formation_price
                                if offered then
                                    formation_price = purchase_quote_value(row,table_name,yield,formation)
                                end
                                if allowed or formation_price ~= nil then
                                    local action, description = nil,row.Description
                                    if allowed then action={type='city_purchase',city_id=city:GetID(),item=row.UnitType,yield=yield,formation=formation}
                                    else description=(label(description) or '')..' 当前不可购买；仅提供原版菜单报价。' end
                                    local id=row.UnitType..':buy:'..yield..':'..formation
                                    add(id,row.Name,description,false,action)
                                    purchase_quote(id,formation_price,yield,allowed)
                                    production_quote(id,row,table_name,formation,false)
                                end
                            end
                        end
                    end
                end
            end
        end
    end
end
add_city_district_conditions()
""")


def _placement_query(a):
    table, parameter = _ITEM_TABLES[a["item"].split("_", 1)[0]]
    return _QUERY_HELPERS + own_city(a["city_id"]) + _PRODUCTION_ELIGIBILITY + CITY_PURCHASE_HELPERS + CITY_COST_HELPERS + f"""
local row = GameInfo.{table}[{lua(a['item'])}]
if not row or row.InternalOnly then return end
out.supported = true
local plots = Map.GetCityPlots():GetPurchasedPlots(city)
if type(plots) ~= 'table' or #plots > 4096 then error('unavailable') end
for _, plot_id in ipairs(plots) do
    local geometry = Map.GetPlotByIndex(plot_id)
    local x, y = geometry:GetX(), geometry:GetY()
    local plot = visible_plot(x,y)
    if plot and plot:GetOwner() == me then
        local p = {{[CityOperationTypes.PARAM_{parameter}_TYPE]=row.Hash,
            [CityOperationTypes.PARAM_INSERT_MODE]=CityOperationTypes.VALUE_REPLACE_AT,
            [CityOperationTypes.PARAM_QUEUE_DESTINATION_LOCATION]=0,
            [CityOperationTypes.PARAM_X]=x,[CityOperationTypes.PARAM_Y]=y}}
        if not row.MustPurchase and can_show_build(row,{lua(table)},nil)
            and CityManager.CanStartOperation(city,CityOperationTypes.BUILD,p,false) then
            add('build:'..x..':'..y, nil, nil, nil,
                {{type='city_build_at',city_id=city:GetID(),item={lua(a['item'])},x=x,y=y,append=false,formation='STANDARD'}})
            production_quote('build:'..x..':'..y,row,{lua(table)},'STANDARD')
        end
        for _, yield in ipairs({{'GOLD','FAITH'}}) do
            local q = {{[CityCommandTypes.PARAM_{parameter}_TYPE]=row.Hash,
                [CityCommandTypes.PARAM_X]=x,[CityCommandTypes.PARAM_Y]=y,
                [CityCommandTypes.PARAM_YIELD_TYPE]=GameInfo.Yields['YIELD_'..yield].Index}}
            if city_purchase_in_menu(row,{lua(table)},yield)
                and CityManager.CanStartCommand(city,CityCommandTypes.PURCHASE,true,q,false) == true
                and CityManager.CanStartCommand(city,CityCommandTypes.PURCHASE,false,q,false) == true
                and city_can_afford(row,yield,'STANDARD') then
                add('buy:'..yield..':'..x..':'..y,nil,nil,nil,
                    {{type='city_purchase_at',city_id=city:GetID(),item={lua(a['item'])},x=x,y=y,yield=yield,formation='STANDARD'}})
                purchase_quote('buy:'..yield..':'..x..':'..y,
                    purchase_quote_value(row,{lua(table)},yield,'STANDARD'),yield,true)
            end
        end
    end
end
"""


def _tiles_query(a):
    return _QUERY_HELPERS + own_city(a["city_id"]) + CITY_PURCHASE_HELPERS + CITY_COST_HELPERS + """
if not CityManager.GetCommandTargets or type(UI.GetInterfaceModeParameter) ~= 'function' then return end
out.supported = true
local modes = {
    {'MANAGE','PARAM_MANAGE_CITIZEN','city_manage_citizen'},
    {'PURCHASE','PARAM_PLOT_PURCHASE','city_purchase_plot'},
    {'SWAP_TILE_OWNER','PARAM_SWAP_TILE_OWNER','city_swap_tile'}}
for _, mode in ipairs(modes) do
    local flag = CityCommandTypes[mode[2]]
    local result = CityManager.GetCommandTargets(city,CityCommandTypes[mode[1]],{[flag]=UI.GetInterfaceModeParameter(flag)})
    local plots = result and result[CityCommandResults.PLOTS]
    if plots then
        for index, plot_id in pairs(plots) do
            local plot = Map.GetPlotByIndex(plot_id)
            if plot and visible_plot(plot:GetX(),plot:GetY()) then
                local x,y = plot:GetX(),plot:GetY()
                local id = mode[3]..':'..x..':'..y
                local action = {type=mode[3],city_id=city:GetID(),x=x,y=y}
                local description
                if mode[1] == 'PURCHASE' then
                    local p = {[flag]=UI.GetInterfaceModeParameter(flag),[CityCommandTypes.PARAM_X]=x,[CityCommandTypes.PARAM_Y]=y}
                    local available = CityManager.CanStartCommand(city,CityCommandTypes.PURCHASE,false,p,false) == true
                        and city_can_afford_plot(plot_id)
                    if not available then action=nil;description='当前不可购买；仅提供可见目标的原版菜单报价。' end
                    add(id,nil,description,nil,action)
                    plot_purchase_quote(id,plot_id)
                    purchase_quote(id,nil,'GOLD',available)
                else add(id,nil,nil,nil,action) end
                if mode[1] == 'MANAGE' then
                    for _, key in ipairs({'CITIZENS','MAX_CITIZENS','LOCKED_CITIZENS'}) do
                        local values = result[CityCommandResults[key]]
                        if values then add(key..':'..x..':'..y,nil,nil,values[index]) end
                    end
                end
            end
        end
    end
end
for row in GameInfo.Yields() do
    add(row.YieldType, row.Name, nil,
        city:GetCitizens():IsFavoredYield(row.Index) and 'favored' or
        (city:GetCitizens():IsDisfavoredYield(row.Index) and 'disfavored' or 'neutral'))
end
"""


def _queue_query(a):
    return _QUERY_HELPERS + own_city(a["city_id"]) + """
local queue = city:GetBuildQueue()
local size = queue:GetSize()
if size > 128 then error('unavailable') end
out.supported = true
for index=0,size-1 do
    local entry = queue:GetAt(index)
    if entry then
        local row, id
        for _, kind in ipairs({'Unit','Building','District','Project'}) do
            if entry[kind..'Type'] ~= nil then
                row = GameInfo[kind..'s'][entry[kind..'Type']]
                if row then id = row[kind..'Type']; break end
            end
        end
        add('queue:'..index, row and row.Name, id, index,
            {type='city_queue_remove',city_id=city:GetID(),index=index})
    end
end
"""


_GOV = {"governor": "identifier:GOVERNOR_"}
_PERSON = {"individual": "identifier:GREAT_PERSON_INDIVIDUAL_"}
_BUILD = {"city_id": "id", "item": "identifier:UNIT_|BUILDING_|DISTRICT_|PROJECT_", "append": "bool", "formation": "enum:STANDARD|CORPS|ARMY"}
_BUY = {"city_id": "id", "item": "identifier:UNIT_|BUILDING_|DISTRICT_", "yield": "enum:GOLD|FAITH", "formation": "enum:STANDARD|CORPS|ARMY"}
_TILE = {"city_id": "id", "x": "coord", "y": "coord"}

ACTIONS = {
    "governor_appoint": ActionSpec(_GOV, _appoint, "Appoint a governor or join a discovered secret society."),
    "governor_defer": ActionSpec({},_governor_defer,"确认已查看本轮总督选择，相当于显式关闭原版总督面板，并保留未花费头衔。仅在 title_considered 为 false 时执行；派驻状态保持不变，之后请重新读取待办，其他待派驻原因仍可能存在。"),
    "governor_promote": ActionSpec({**_GOV,"promotion":"identifier:GOVERNOR_PROMOTION_"}, _promote, "Earn a legal governor or society promotion."),
    "governor_assign": ActionSpec({**_GOV,**_TILE,"owner_id":"id"}, _assign, "Assign/reassign to an own city or a currently visible, met foreign city."),
    "great_person_recruit": ActionSpec(_PERSON, lambda a:_great_person(a,"recruit"), "Recruit an offered great person."),
    "great_person_pass": ActionSpec(_PERSON, lambda a:_great_person(a,"pass"), "Pass an offered great person."),
    "great_person_patronize": ActionSpec({**_PERSON,"yield":"enum:GOLD|FAITH"}, lambda a:_great_person(a,"patronize"), "Patronize with gold or faith."),
    "change_government": ActionSpec({"government":"identifier:GOVERNMENT_"}, _government, "Change to an unlocked government; normal anarchy rules apply."),
    "government_keep": ActionSpec({},_government_keep,"Keep current government and acknowledge that its ordinary change prompt was considered."),
    "set_policies": ActionSpec({"slots":[{"slot":"id","policy":"identifier:POLICY_"}]}, _policies, "Provide the complete slot-to-policy assignment, all slots filled."),
    "unlock_policies": ActionSpec({}, _unlock, "Pay the normal policy-change fee."),
    "choose_dedications": ActionSpec({"dedications":["identifier:COMMEMORATION_"]}, _dedications, "Select exactly the required number of age dedications."),
    "found_pantheon": ActionSpec({"belief":"identifier:BELIEF_"},lambda a:_belief(a,True),"Choose a currently available pantheon."),
    "add_belief": ActionSpec({"belief":"identifier:BELIEF_"},lambda a:_belief(a,False),"Add an earned religion belief, including evangelization."),
    "found_religion": ActionSpec({"religion":"identifier:RELIGION_","name":"text","beliefs":["identifier:BELIEF_"]},_found_religion,"Found religion with available beliefs, follower belief first; name used for custom symbols."),
    "city_build": ActionSpec(_BUILD,_build,"Build/repair or queue an item already placed; supports corps/armies."),
    "city_build_at": ActionSpec({**_BUILD,"x":"coord","y":"coord"},_build,"Place a district or wonder using ordinary production request."),
    "city_purchase": ActionSpec(_BUY,_purchase,"Buy an available unit/building with gold/faith."),
    "city_purchase_at": ActionSpec({**_BUY,"x":"coord","y":"coord"},_purchase,"Purchase a district at a visible permitted position."),
    "city_purchase_plot": ActionSpec(_TILE,lambda a:_tile(a,"purchase"),"Buy a visible city tile."),
    "city_manage_citizen": ActionSpec(_TILE,lambda a:_tile(a,"citizen"),"Same citizen/specialist cycle as clicking the city tile; reobserve lock/count."),
    "city_swap_tile": ActionSpec(_TILE,lambda a:_tile(a,"swap"),"Move an owned tile to another own city."),
    "city_set_focus": ActionSpec({"city_id":"id","yield":"identifier:YIELD_","focus":"enum:favored|disfavored|neutral"},_focus,"Set a yield focus explicitly."),
    "city_rename": ActionSpec({"city_id":"id","name":"text"},_rename_city,"Rename an own city using the normal city overview command."),
    "city_queue_remove": ActionSpec({"city_id":"id","index":"id"},_queue,"Remove a production queue entry."),
    "city_queue_move": ActionSpec({"city_id":"id","index":"id","destination":"id"},_queue,"Move a queue entry to another queue index."),
    "city_loyalty_choice": ActionSpec({"city_id":"id","choice":"enum:keep|reject"},_loyalty_choice,"Accept or reject only the next loyalty-converted city offered to the player."),
}

QUERIES = {
    "governors": QuerySpec({},_governors_query,"Own titles, discovered governors, assignment/establishment status, earned/earnable promotions and own assignment destinations."),
    "great_people": QuerySpec({},_great_people_query,"Public recruitment board and own available recruitment/patronage/pass actions."),
    "government": QuerySpec({},_government_query,"Unlocked governments with optional current-rules effects and base policy-slot previews; available policies, actual slot indices and current assignments."),
    "dedications": QuerySpec({},_dedications_query,"Current era dedication choices and exact required selection count."),
    "religion": QuerySpec({},_religion_query,"Own religion, earned beliefs and choices shown on the religion selection screen."),
    "city_production": QuerySpec({"city_id":"id"},_production_query,"Build/repair/purchase menu with actual production cost/progress/turns and currency prices; optional scalar entries suffix the option id. Disabled purchase quotes have no action; option value true still means placement required."),
    "city_placement": QuerySpec({"city_id":"id","item":"identifier:BUILDING_|DISTRICT_"},_placement_query,"Visible legal production/purchase destinations among own city's plots, with actual production estimates or currency prices, including wrapped maps."),
    "city_tiles": QuerySpec({"city_id":"id"},_tiles_query,"Visible citizen/specialist counts and locks, tile purchase/swap actions and focus. Purchase targets include optional gold cost; currently unavailable purchases have no action."),
    "city_queue": QuerySpec({"city_id":"id"},_queue_query,"Own production queue, zero-based indices and removal actions."),
    "loyalty_choices": QuerySpec({},_loyalty_query,"Accept/reject choices for the next offered loyalty-converted city."),
}
