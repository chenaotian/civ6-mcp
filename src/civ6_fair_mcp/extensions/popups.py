"""Read displayed UI controls and invoke only their existing normal callbacks.

No screenshots, private popup queues, debug upvalues, arbitrary context names,
caller-supplied control paths, callback names, or UI code are accepted.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .base import ActionSpec, lua
from ..lua_common import wrap


@dataclass(frozen=True)
class PopupSpec:
    context: str
    # (control ID, exact stock callback expression, fallback label, input kind)
    buttons: tuple[tuple[str, str, str, str], ...] = ()
    generic: bool = False
    decision_hint: str = ""
    events: tuple[tuple[str, str], ...] = ()


def button(control: str, callback: str, label: str = "关闭") -> tuple[str, str, str, str]:
    return control, callback, label, "button"


MANIFEST = {
    "boost": PopupSpec("BoostUnlockedPopup", (button("ContinueButton", "OnClose", "继续"),)),
    "research_completed": PopupSpec("TechCivicCompletedPopup", (
        button("CloseButton", "OnClose"),
        button("ChangeGovernmentButton", "government_callback()", "政体／政策"),)),
    "natural_wonder": PopupSpec("NaturalWonderPopup", (button("Close", "OnClose"),)),
    "wonder_built": PopupSpec("WonderBuiltPopup", (button("Close", "OnClose"),)),
    "project_built": PopupSpec("ProjectBuiltPopup", (button("Close", "OnClose"),)),
    "era_complete": PopupSpec("EraCompletePopup", (("", "OnClose", "关闭（Esc）", "escape"),)),
    "era_review": PopupSpec("EraReviewPopup", (button("Close", "OnClose"), button("Continue", "OnContinue", "继续"))),
    "natural_disaster": PopupSpec("NaturalDisasterPopup", (button("Close", "OnClose"),)),
    "secret_society": PopupSpec("SecretSocietyPopup", (
        button("ContinueButton", "OnContinueButton", "继续"),
        button("OpenGovernorsButton", "OnOpenGovernorsButton", "打开总督界面")),
        decision_hint="Joining or promoting a society uses governors/secret-society gameplay choices after this message."),
    "world_crisis": PopupSpec("WorldCrisisPopup", (
        button("JoinButton", "OnJoinClicked", "加入"), button("RejectButton", "OnRejectClicked", "拒绝"),
        button("OKButton", "OnClose", "确认"), button("CloseButton", "OnClose"))),
    "rock_band": PopupSpec("RockBandPopup", (button("CloseButton", "OnClose"),)),
    "rock_band_movie": PopupSpec("RockBandMoviePopup", (button("Close", "OnClose"),)),
    "great_work": PopupSpec("GreatWorkShowcase", (
        button("ModalScreenClose", "OnHideScreen"), button("NextGreatWork", "OnNextGreatWork", "下一件巨作"),
        button("PreviousGreatWork", "OnPreviousGreatWork", "上一件巨作"), button("ViewGreatWorks", "OnViewGreatWorks", "查看巨作"))),
    "great_works_overview": PopupSpec("GreatWorksOverview", (button("ModalScreenClose", "OnHideScreen"),),
        decision_hint="巨作总览已打开；调配巨作仍使用 great_works 查询和 move_great_work 操作。",
        events=(("LuaEvents", "GreatWorks_OpenGreatWorks"), ("LuaEvents", "GreatWorks_CloseGreatWorks"))),
    "historic_moments": PopupSpec("HistoricMoments", (button("Close", "OnClose"),),
        decision_hint="当前历史时刻界面；只读取已显示控件，关闭使用原版回调，不读取历史数据库或待显示队列。",
        events=(("LuaEvents", "HistoricMoments_Opened"), ("LuaEvents", "HistoricMoments_Closed"))),
    "world_rankings": PopupSpec("WorldRankings", (button("CloseButton", "Close"),),
        decision_hint="世界排名侧栏已打开；此观察只识别标题和正常关闭，不读取排行列表。公开文明数据仍使用 get_diplomacy。",
        events=(("LuaEvents", "PartialScreenHooks_OpenWorldRankings"),
                ("LuaEvents", "PartialScreenHooks_OpenWorldRankingsCulture"),
                ("LuaEvents", "PartialScreenHooks_ToggleWorldRankings"), ("LuaEvents", "WorldRankings_Close"))),
    "generic": PopupSpec("InGamePopup", generic=True),
    "diplomacy": PopupSpec("DiplomacyActionView", (button("CloseButton", "OnClose"),),
        decision_hint="当前可见的外交回应可直接使用对应按钮，包括首次见面的访问／交换信息选择；关闭按钮在领袖动画期间可能只跳过动画，操作后请重新观察。交易使用过滤后的 deal_state 查询。",
        events=(("Events", "DiplomacyStatement"), ("Events", "DiplomacySessionClosed"))),
    "deal": PopupSpec("DiplomacyDealView", (
        button("ResumeGame", "OnResumeGame", "返回游戏"), button("RefuseDeal", "OnRefuseDeal", "拒绝／退出交易")),
        decision_hint='先调用 inspect_game("diplomacy_sessions", {}) 获取已遇见且会话仍打开的对方编号；再调用 inspect_game("deal_state", {"target_player": 对方编号}) 获取经过权限过滤的报价与响应选项。此快照不读取原始交易正文。',
        events=(("LuaEvents", "DiploPopup_ShowMakeDeal"), ("LuaEvents", "DiploPopup_ShowMakeDemand"),
                ("LuaEvents", "DiploPopup_HideDeal"), ("LuaEvents", "DiploPopup_DealUpdated"),
                ("Events", "DiplomacyIncomingDeal"))),
    "world_congress": PopupSpec("WorldCongressPopup", (
        button("AcceptButton", "OnAccept", "提交"), button("ReturnButton", "OnClose", "返回"),
        button("PassButton", "OnPass", "放弃"), button("NextButton", "OnNext", "下一页"),
        button("PrevButton", "OnPrev", "上一页"), button("HideButton", "OnClose")),
        decision_hint="Configure votes through world-congress actions; this snapshot displays the currently visible page and buttons."),
    "congress_between_turns": PopupSpec("WorldCongressBetweenTurns", (button("HideButton", "OnHide", "隐藏"),)),
    "congress_intro": PopupSpec("WorldCongressIntro", (button("AcceptButton", "OnClose", "确认"),)),
    "dedication": PopupSpec("DedicationPopup", (button("CloseButton", "OnClose"), button("Confirm", "OnConfirm", "确认")),
        decision_hint="Select dedication choices using the dedication action; Confirm applies the UI's current selection only."),
    "captured_city": PopupSpec("RazeCity", (
        button("Button1", "OnButton1", "解放"), button("Button2", "OnButton2", "归还"),
        button("Button3", "OnButton3", "保留"), button("Button4", "OnButton4", "夷平"), button("CloseButton", "OnClose"))),
    "disloyal_city": PopupSpec("DisloyalCityChooser", (
        button("KeepButton", "OnKeepButton", "接纳"), button("RejectButton", "OnRejectButton", "拒绝"),
        button("ModalScreenClose", "OnClose")), events=(("LuaEvents", "NotificationPanel_OpenDisloyalCityChooser"),)),
    "pantheon": PopupSpec("PantheonChooser", (
        button("Header_CloseButton", "Close"), button("ConfirmPantheonButton", "ConfirmPantheon", "确认"),
        button("CancelButton", "ClearBeliefSelection", "取消选择")),
        decision_hint="Choose a pantheon with the pantheon action; Confirm applies the UI's current selection only."),
    "religion": PopupSpec("ReligionScreen", (button("ModalScreenClose", "OnClose"),),
        decision_hint="Religion identities and beliefs use the religion gameplay actions."),
    "government": PopupSpec("GovernmentScreen", (
        button("ModalScreenClose", "OnClose"), button("ConfirmPolicies", "OnConfirmPolicies", "确认政策")),
        decision_hint="Government/policy gameplay actions configure choices; confirmation applies only the current UI selection."),
    "governors": PopupSpec("GovernorPanel", (button("ModalScreenClose", "PlayerRequestClose"),),
        decision_hint="Appoint/promote/assign using governor actions. Secret societies use the same governor system when enabled."),
    "governor_assignment": PopupSpec("GovernorAssignmentChooser", (
        button("Header_CloseButton", "PlayerRequestClose"), button("CancelButton", "OnCancel", "取消派驻")),
        decision_hint='先关闭或取消派驻界面，再通过 governors 查询和 governor_assign 选择派驻目标。当前页面的外国城市列表不读取；外部派驻目标仍须已遇见且当前可见。',
        events=(("LuaEvents", "GovernorAssignmentChooser_RequestAssignment"), ("LuaEvents", "GovernorAssignmentChooser_Close"))),
    "artifact": PopupSpec("ChooseArtifact", (
        button("Button1", "OnButton1", "来源一"), button("Button2", "OnButton2", "来源二")),
        decision_hint="Choose the displayed artifact origin. Unmet civilization identities remain anonymous under P05.",
        events=(("LuaEvents", "NotificationPanel_OpenArtifactPanel"),)),
    "spy_escape": PopupSpec("EspionageEscape", (
        button("Button1", "OnButton1", "飞机"), button("Button2", "OnButton2", "海路"),
        button("Button3", "OnButton3", "车辆"), button("Button4", "OnButton4", "步行"),
        ("", "OnClose", "关闭（Esc）", "escape")), events=(("LuaEvents", "NotificationPanel_OpenEspionageEscape"),)),
    "unit_promotion": PopupSpec("UnitPromotionPopup", (button("CloseButton", "OnClose"),),
        decision_hint="Choose an available promotion using unit_promotions and unit_promote."),
    "spy_mission": PopupSpec("EspionagePopup", (
        button("AcceptButton", "OnAccept", "接受"), button("AbortButton", "OnAbort", "中止"),
        button("CancelButton", "OnCancel", "取消"), button("MissionSucceedButton", "OnMissionSucceedButton", "确认"),
        button("MissionFailureButton", "OnMissionFailureButton", "确认"), button("RenewButton", "@click", "继续任务"),
        ("", "Close", "关闭（Esc）", "escape")),
        events=(("LuaEvents", "EspionageChooser_ShowMissionBriefing"), ("LuaEvents", "UnitPanel_CancelMission"),
                ("LuaEvents", "EspionagePopup_MissionBriefingClosed"),
                ("Events", "SpyMissionCompleted"))),
    "great_people": PopupSpec("GreatPeoplePopup", (button("ModalScreenClose", "OnClose"),),
        decision_hint="Recruit, patronize, or pass through great_people options and their offered gameplay actions."),
    "declare_war": PopupSpec("DeclareWarPopup", (
        button("No", "OnClose", "取消"), button("Yes", "@click", "确认宣战")),
        events=tuple(("LuaEvents", name) for name in ("DiplomacyActionView_ConfirmWarDialog", "CityStates_ConfirmWarDialog",
                    "Civ6Common_ConfirmWarDialog", "WorldInput_ConfirmWarDialog"))),
    "event": PopupSpec("EventPopup", (button("Continue", "OnClose", "继续"),
        button("ChoiceA", "@click", "选项 A"), button("ChoiceB", "@click", "选项 B")),
        decision_hint="A/B events require their actual visible button; closing cannot bypass the required choice.",
        events=(("Events", "EventPopupRequest"), ("LuaEvents", "EventPopupRequest"))),
    "advisor": PopupSpec("AdvisorPopup", decision_hint="Respond through an offered visible advisor button; Escape opens options and cannot dismiss advice.",
        events=(("LuaEvents", "TutorialUIRoot_AdvisorRaise"), ("LuaEvents", "TutorialUIRoot_AdvisorLower"))),
    "expansion_intro": PopupSpec("ExpansionIntro", (
        button("Close", "OnClose"), button("Next", "OnNext", "下一页"), button("Previous", "OnPrevious", "上一页"))),
}

POPUP_CONTEXTS = {key: spec.context for key, spec in MANIFEST.items()}
# Exact containers from Expansion2/UI/Replacements/InGame.xml. Add-ins have a
# second name variant because LoadNewContext derives the ID from the file name.
_CONTAINERS = {
    "WorldPopups": ("boost", "research_completed", "natural_wonder", "wonder_built", "project_built", "era_complete",
                    "natural_disaster", "rock_band", "rock_band_movie", "captured_city", "unit_promotion", "spy_mission", "event"),
    "FakePopups": ("generic", "artifact", "spy_escape"),
    "Diplomacy": ("diplomacy", "deal", "world_congress", "congress_between_turns", "congress_intro", "declare_war"),
    "Screens": ("great_work", "great_works_overview", "historic_moments", "religion", "government", "great_people", "governors"),
    "PartialScreens": ("world_rankings",),
    "TopLevelHUD": ("pantheon",),
}
POPUP_PATHS = {
    key: tuple(f"{prefix}/{spec.context}{suffix}" for prefix in (
        *[f"/InGame/{container}" for container, keys in _CONTAINERS.items() if key in keys],
        *(["/TutorialUIRoot"] if key == "advisor" else []), "/InGame", "/InGame/AdditionalUserInterfaces")
               for suffix in ("", ".xml"))
    for key, spec in MANIFEST.items()
}


def discovery_lua() -> str:
    """InGame-only discovery: inspect fixed context visibility, no text/queues."""
    chunks = ['''out.popup_keys=array({})
if not ContextPtr or type(ContextPtr.LookUpControl)~="function" then error("unavailable") end
out.native_modal_keys=array({})
out.native_modal_present=false
out.unknown_modal_present=false
out.modal_monitor_available=false
local native_modals,mapped_modals={},{}
if UIManager and type(UIManager.GetModalContexts)=="function" then
    local ok,contexts=pcall(UIManager.GetModalContexts,UIManager)
    if ok and type(contexts)=="table" then
        out.modal_monitor_available=true
        local count=0
        for _,context in pairs(contexts) do
            count=count+1
            if count>64 or (type(context)~="table" and type(context)~="userdata") then
                out.modal_monitor_available=false;break
            end
            native_modals[#native_modals+1]=context
            out.native_modal_present=true
        end
    end
end
''']
    for key, spec in MANIFEST.items():
        paths = POPUP_PATHS[key]
        if spec.generic:
            paths = tuple(path + "/PopupRoot" for path in paths)
        displayed = '''
        -- The stock side panel is rendered by SlideAnim. Context existence
        -- alone must not expose a collapsed panel or cached ranking content.
        local slide=ContextPtr:LookUpControl(path.."/SlideAnim")
        if control and type(control.IsVisible)=="function" and control:IsVisible()==true
            and slide and type(slide.IsVisible)=="function" and slide:IsVisible()==true then found=true; break end
''' if key == "world_rankings" else '''
        if control and type(control.IsVisible)=="function" and control:IsVisible()==true then found=true; break end
'''
        modal_context_fallback = f'''
    -- PopupDialog.xml is a MakeInstance: its PopupRoot may be absent from
    -- cross-context LookUpControl even while InGamePopup is a native modal.
    -- Only inspect this fixed context's modality/visibility here; the actual
    -- dialog Controls and callbacks are read later in its own Lua context.
    if not found and UIManager and type(UIManager.IsModal)=="function" then
        for _,path in ipairs({lua(list(POPUP_PATHS[key]))}) do
            local control=ContextPtr:LookUpControl(path)
            if control and type(control.IsVisible)=="function" and control:IsVisible()==true then
                local ok,modal=pcall(UIManager.IsModal,UIManager,control)
                if ok and modal==true then found=true; break end
            end
        end
    end
''' if spec.generic else ""
        chunks.append(f'''
do
    local found=false
    local visible_native=false
    for _,path in ipairs({lua(list(POPUP_PATHS[key]))}) do
        local context=ContextPtr:LookUpControl(path)
        if context then
            -- Native controls can be distinct userdata wrappers whose __eq
            -- compares equal. Table-key lookup uses raw identity instead;
            -- match with == and track only the numeric modal entry index.
            for index,native in ipairs(native_modals) do
                if context==native then
                    mapped_modals[index]=true
                    if type(context.IsVisible)=="function" and context:IsVisible()==true then visible_native=true end
                end
            end
        end
    end
    if visible_native then table.insert(out.native_modal_keys,{lua(key)}) end
    for _,path in ipairs({lua(list(paths))}) do
        local control=ContextPtr:LookUpControl(path)
        {displayed}
    end
    {modal_context_fallback}
    if found then table.insert(out.popup_keys,{lua(key)}) end
end
''')
    chunks.append('''
-- Only compare opaque modal objects with fixed known contexts. Unknown
-- contexts' names, text, children, callbacks and event data are never read.
for index in ipairs(native_modals) do
    if not mapped_modals[index] then out.unknown_modal_present=true;break end
end
''')
    return "".join(chunks)


_READ_HELPERS = r'''
local redacted={}
local function shown(control)
    local current,seen,depth=control,{},0
    while current do
        if type(current.IsVisible)~="function" or current:IsVisible()~=true then return false end
        if seen[current] or depth>32 then return false end
        seen[current]=true; depth=depth+1
        -- Forge renders an active queued popup or native modal independently of its logical
        -- parent (the stock WorldPopups container remains hidden). Only the
        -- current visible context may be this root; hidden descendants and
        -- queued-but-hidden contexts must still fail the checks above.
        if current==ContextPtr and UIManager then
            for _,method in ipairs({"IsInPopupQueue","IsModal"}) do
                if type(UIManager[method])=="function" then
                    local ok,standalone=pcall(UIManager[method],UIManager,ContextPtr)
                    if ok and standalone==true then return true end
                end
            end
        end
        if type(current.GetParent)~="function" then return true end
        current=current:GetParent()
    end
    return control~=nil
end
local function text_of(control, fallback)
    if not shown(control) then return nil end
    if redacted[control] then return redacted[control] end
    local text=nil
    if type(control.GetText)=="function" then
        local ok,value=pcall(control.GetText,control)
        if ok and type(value)=="string" and value~="" then text=value end
    end
    text=text or fallback or ""
    if #text>8192 then error("unavailable") end
    return text
end
local function enabled(control)
    return shown(control) and type(control.IsDisabled)=="function" and control:IsDisabled()==false
end
local function government_callback()
    local control=Controls and Controls.ChangeGovernmentButton
    if not shown(control) then return nil end
    local label=text_of(control)
    if Locale and type(Locale.Lookup)=="function" then
        if label==Locale.Lookup("LOC_GOVT_GOVERNMENT_UNLOCKED") then return OnChangeGovernment end
        if label==Locale.Lookup("LOC_GOVT_CHANGE_POLICIES") then return OnChangePolicy end
    end
    return nil
end
local function visible_texts(root)
    local content,seen,visited={}, {}, {}
    local count,bytes=0,0
    local function visit(control,depth)
        if not shown(control) or visited[control] then return end
        if depth>20 then error("unavailable") end
        visited[control]=true
        count=count+1
        if count>4096 then error("unavailable") end
        local text=text_of(control)
        if text and text~="" and not seen[text] then
            bytes=bytes+#text
            if bytes>65536 or #content>=512 then error("unavailable") end
            seen[text]=true; content[#content+1]=text
        end
        if type(control.GetChildren)=="function" then
            if redacted[control] then return end
            local children=control:GetChildren()
            if type(children)~="table" then error("unavailable") end
            for _,child in ipairs(children) do visit(child,depth+1) end
        end
    end
    visit(root,0)
    return content
end
local function signature_of(popup)
    local parts={popup.id, popup.visible and "1" or "0"}
    for _,text in ipairs(popup.content) do parts[#parts+1]=tostring(#text)..":"..text end
    for _,entry in ipairs(popup.buttons) do
        parts[#parts+1]=entry.id..":"..tostring(#entry.label)..":"..entry.label..":"..tostring(entry.enabled)..":"..tostring(entry.supported)..":"..entry.input
    end
    return table.concat(parts,"|")
end
'''


def _event_hooks(key: str) -> str:
    events = MANIFEST[key].events
    body = '''
_CIV6FAIR_POPUP_EVENTS=_CIV6FAIR_POPUP_EVENTS or {}
_CIV6FAIR_POPUP_GENERATION=_CIV6FAIR_POPUP_GENERATION or 0
local has_event_guards=true
'''
    for owner, name in events:
        body += f'''
do
    local event={owner} and {owner}[{lua(name)}]
    local hook_key={lua(owner+'.'+name)}
    if not event or type(event.Add)~="function" then has_event_guards=false
    elseif not _CIV6FAIR_POPUP_EVENTS[hook_key] then
        local ok=pcall(event.Add,function()
            _CIV6FAIR_POPUP_GENERATION=_CIV6FAIR_POPUP_GENERATION+1
            _CIV6FAIR_POPUP_SNAPSHOT=nil
        end)
        if ok then _CIV6FAIR_POPUP_EVENTS[hook_key]=true else has_event_guards=false end
    end
end
'''
    return body


_ARTIFACT_REDACTION = '''
    local units=Players[me]:GetUnits()
    if not units or type(units.GetNextExtractingArchaeologist)~="function" then error("unavailable") end
    local archaeologist=units:GetNextExtractingArchaeologist()
    if not archaeologist then resolved=true else
    if archaeologist:GetOwner()~=me then error("unavailable") end
    local archaeology=archaeologist:GetArchaeology()
    if not archaeology or type(Game.GetArtifactByIndex)~="function" then error("unavailable") end
    local artifact_index=archaeology:GetArtifactIndex()
    local artifact=Game.GetArtifactByIndex(artifact_index)
    if not artifact or artifact.ActingPlayerID~=g_ActingPlayerID or artifact.TargetPlayerID~=g_TargetPlayerID then error("unavailable") end
    refs.identity=archaeologist
    refs.identity_key=tostring(artifact_index)..":"..tostring(g_ActingPlayerID)..":"..tostring(g_TargetPlayerID)
    local diplomacy=Players[me]:GetDiplomacy()
    local function known(id)
        return id==me or (type(id)=="number" and id>=0 and diplomacy and type(diplomacy.HasMet)=="function" and diplomacy:HasMet(id)==true)
    end
    local acting_known=known(g_ActingPlayerID)
    local target_known=not shown(Controls.Button2) or known(g_TargetPlayerID)
    if not acting_known or not target_known then
        for _,name in ipairs({"Explanation","ChoiceHeader"}) do
            if Controls[name] then redacted[Controls[name]]="考古事件涉及未遇见文明；身份按 P05 隐去" end
        end
    end
    if not acting_known and Controls.Button1 then redacted[Controls.Button1]="未遇见文明（来源一）" end
    if not target_known and Controls.Button2 then redacted[Controls.Button2]="未遇见文明（来源二）" end
    end
'''

_SPY_ESCAPE_PENDING = '''
    local diplomacy=Players[me]:GetDiplomacy()
    if not diplomacy or type(diplomacy.GetNextEscapingSpyID)~="function" then error("unavailable") end
    local id=diplomacy:GetNextEscapingSpyID()
    if id==nil or (type(id)=="number" and id<0) then resolved=true
    elseif type(id)~="number" or id~=math.floor(id) then error("unavailable")
    else refs.identity_key=tostring(id) end
'''

_RESOLVED_DIALOG = '''
    if resolved then
        popup.content=array({"此决定已处理；关闭残留窗口。"})
        popup.decision_hint="The own-player pending decision is absent. This closes only the stale UI; it sends no gameplay request."
        local supported=popup.interactive and type(ContextPtr.SetHide)=="function"
        if not _CIV6FAIR_RESOLVED_CLOSE then
            _CIV6FAIR_RESOLVED_CLOSE=function() ContextPtr:SetHide(true) end
        end
        refs.identity_key="resolved"
        refs[1]={control=ContextPtr,callback=_CIV6FAIR_RESOLVED_CLOSE}
        popup.buttons=array({{id=1,label="关闭已处理窗口",enabled=true,supported=supported,input="button"}})
        return popup,refs
    end
'''

_CONGRESS_REDACTION = '''
    if not dialog then
        for _,name in ipairs({"ResolutionStack","ReviewProposalStack"}) do
            local control=Controls and Controls[name]
            if control then redacted[control]="提案可能包含未遇见文明身份；请使用 world_congress 查询中的匿名选项" end
        end
    end
'''


_DEAL_CONTENT = '''
    -- Deal inventories can contain unrevealed resources or identity-bearing
    -- names. Never traverse the context tree or read its dialogue/inventories.
    -- These two fixed headings are static strings in the shipped XML.
    if dialog then
        popup.content=array(visible_texts(root))
    else
        popup.content=array({"外交交易界面已打开；报价内容通过过滤后的 deal_state 查询获取。"})
        for _,name in ipairs({"MyOfferLabel","TheirOfferLabel"}) do
            local text=text_of(Controls and Controls[name])
            if text and text~="" then table.insert(popup.content,text) end
        end
    end
'''

_GOVERNOR_ASSIGNMENT_CONTENT = '''
    -- The selector can list foreign cities beyond our map projection policy.
    -- Never walk this context or its nested confirmation. Expose only the
    -- fixed, normal close/cancel controls below, with no assignment callback.
    popup.content=array({"总督派驻界面已打开；目标城市请通过经过权限过滤的 governors 查询选择。"})
'''

_WORLD_RANKINGS_CONTENT = '''
    -- This is an exit route for the fixed visible sidebar, not a new ranking
    -- query. Never traverse SlideAnim, tab lists or cached civilization rows.
    popup.content=array({"世界排名侧栏已打开。"})
    local title=text_of(Controls and Controls.Title)
    if title and title~="" then table.insert(popup.content,title) end
'''


def _modal_gate(key: str) -> str:
    paths = [path + "/PopupRoot" for path in POPUP_PATHS["generic"]]
    return f'''
    popup.modal=dialog~=nil
    popup.interactive=true
    if {lua(key)}~="generic" and ContextPtr and type(ContextPtr.LookUpControl)=="function" then
        for _,path in ipairs({lua(paths)}) do
            if shown(ContextPtr:LookUpControl(path)) then popup.interactive=false; break end
        end
    end
    if UIManager and type(UIManager.IsModal)=="function" then
        local ok,is_modal=pcall(UIManager.IsModal,UIManager,ContextPtr)
        if not ok then error("unavailable") end
        popup.modal=popup.modal or is_modal==true
        if type(UIManager.GetModalContexts)=="function" then
            local ok,contexts=pcall(UIManager.GetModalContexts,UIManager)
            if not ok then error("unavailable") end
            if type(contexts)=="table" and next(contexts)~=nil and is_modal~=true then popup.interactive=false end
        end
    end
'''


def _collector(key: str) -> str:
    spec = MANIFEST[key]
    root = '''local dialog_root=PopupDialog and PopupDialog.Controls and PopupDialog.Controls.PopupRoot
    local dialog=shown(dialog_root) and PopupDialog or nil
    local root=dialog and dialog_root or ''' + ('nil\n' if spec.generic else 'ContextPtr\n')
    if key == "world_rankings":
        root = '''local dialog=nil
    local root=Controls and Controls.SlideAnim
'''
    body = _READ_HELPERS + _event_hooks(key) + f'''
if not ContextPtr or type(ContextPtr.GetID)~="function" then error("unavailable") end
local actual_context=ContextPtr:GetID()
if actual_context~={lua(spec.context)} and actual_context~={lua(spec.context+'.xml')} then error("unavailable") end
local function collect_popup()
    local popup={{id={lua(key)},visible=false,content=array({{}}),buttons=array({{}})}}
    local refs={{}}
    {root}
    if not shown(ContextPtr) or not shown(root) then return popup,refs end
    popup.visible=true
    refs.root=root
    refs.generation=_CIV6FAIR_POPUP_GENERATION
    local resolved=false
    {_modal_gate(key)}
    {_ARTIFACT_REDACTION if key == 'artifact' else ''}
    {_SPY_ESCAPE_PENDING if key == 'spy_escape' else ''}
    {_RESOLVED_DIALOG if key in ('artifact','spy_escape') else ''}
    {_CONGRESS_REDACTION if key == 'world_congress' else ''}
    {_DEAL_CONTENT if key == 'deal' else _GOVERNOR_ASSIGNMENT_CONTENT if key == 'governor_assignment' else _WORLD_RANKINGS_CONTENT if key == 'world_rankings' else 'popup.content=array(visible_texts(root))'}
    popup.decision_hint={lua(spec.decision_hint)}
    local function offer(control,callback,fallback,input,id,direct,known_label)
        if input~="escape" and not shown(control) then return end
        if #popup.buttons>=128 then error("unavailable") end
        local is_enabled=input=="escape" or enabled(control)
        if direct then callback=control.DoLeftClick end
        local supported=type(callback)=="function" and (not direct or has_event_guards) and popup.interactive
        local label=known_label or (input=="escape" and fallback or text_of(control,fallback))
        popup.buttons[#popup.buttons+1]={{id=id,label=label,enabled=is_enabled,supported=supported,input=input}}
        refs[id]={{control=control,callback=callback,receiver=direct and control or nil}}
    end
'''
    body += '''
    if dialog then
        -- No generic confirmation dispatch for the assignment selector.
        -- Its underlying close/cancel controls must not bypass a modal.
    else
''' if key == 'governor_assignment' else '''
    if dialog then
    if type(dialog.PopupControls)~="table" then error("unavailable") end
    for index,entry in ipairs(dialog.PopupControls) do
        if index>512 then error("unavailable") end
        if entry.Type=="Button" and shown(entry.Control) then
            offer(entry.Control,entry.Callback,"选择","button",index)
        end
    end
    else
'''
    if not spec.generic:
        for index, (control, callback, label, input_kind) in enumerate(spec.buttons, 1):
            expr = f'Controls and Controls[{lua(control)}]' if control else "root"
            body += f'    offer({expr},{"nil" if callback == "@click" else callback},{lua(label)},{lua(input_kind)},{index},{lua(callback == "@click")})\n'
    if key == "advisor":
        body += '''
    for stack_index,name in ipairs({"ButtonStack","MetaButtonStack"}) do
        local stack=Controls and Controls[name]
        if shown(stack) and type(stack.GetChildren)=="function" then
            local children=stack:GetChildren()
            if type(children)~="table" or #children>64 then error("unavailable") end
            for index,control in ipairs(children) do
                offer(control,nil,"继续","button",stack_index*1000+index,true)
            end
        end
    end
'''
    if key == "diplomacy":
        body += '''
    -- The stock instance root is SelectionButton; its caption is a separate
    -- SelectionText label, not the GridButton's own GetText value.
    local stack=Controls and Controls.ConversationSelectionStack
    if shown(stack) and type(stack.GetChildren)=="function" then
        local children=stack:GetChildren()
        if type(children)~="table" or #children>64 then error("unavailable") end
        for index,control in ipairs(children) do
            if shown(control) and type(control.GetID)=="function" and control:GetID()=="SelectionButton" then
                local caption=nil
                if type(control.GetChildren)=="function" then
                    local labels=control:GetChildren()
                    if type(labels)~="table" or #labels>16 then error("unavailable") end
                    for _,candidate in ipairs(labels) do
                        if shown(candidate) and type(candidate.GetID)=="function" and candidate:GetID()=="SelectionText" then
                            if caption~=nil then error("unavailable") end
                            caption=text_of(candidate)
                        end
                    end
                end
                if caption and caption~="" then
                    offer(control,nil,caption,"button",1000+index,true,caption)
                else
                    offer(control,nil,"回应文字不可用","button",1000+index,false,"回应文字不可用")
                end
            end
        end
    end
'''
    body += '    end\n'
    if key == "captured_city":
        body += '    refs.identity=g_pSelectedCity\n'
    body += '''
    return popup,refs
end
'''
    return body


def build_popup_query(nonce: str, key: str) -> str:
    if key not in MANIFEST or type(nonce) is not str or not re.fullmatch(r"[A-Za-z0-9_]{1,96}", nonce):
        raise ValueError("invalid popup query")
    body = _collector(key) + f'''
local popup,refs=collect_popup()
out.popup=popup
if not popup.visible then _CIV6FAIR_POPUP_SNAPSHOT=nil; return out end
local counter=(_CIV6FAIR_POPUP_COUNTER or 0)+1
if counter>1000000000 then counter=1 end
_CIV6FAIR_POPUP_COUNTER=counter
local revision={lua('POPUP_'+nonce.upper()+'_')}..tostring(counter)
local signature=signature_of(popup)
_CIV6FAIR_POPUP_SNAPSHOT={{session=session,player=me,turn=turn,id={lua(key)},signature=signature,refs=refs,revision=revision}}
popup.revision=revision
for _,entry in ipairs(popup.buttons) do
    if entry.enabled and entry.supported then entry.action={{type="popup_action",popup={lua(key)},button_id=entry.id,revision=revision}} end
end
'''
    return wrap(body, nonce, shared_context=True)


def popup_action_body(a: dict) -> str:
    key = a["popup"]
    return _collector(key) + f'''
local previous=_CIV6FAIR_POPUP_SNAPSHOT
if not previous or previous.session~=session or previous.player~=me or previous.turn~=turn
    or previous.id~={lua(key)} or previous.revision~={lua(a['revision'])} then return end
local popup,refs=collect_popup()
if not popup.visible or previous.signature~=signature_of(popup)
    or not popup.interactive or previous.refs.generation~=refs.generation
    or previous.refs.identity_key~=refs.identity_key
    or previous.refs.identity~=refs.identity or previous.refs.root~=refs.root then return end
for id,reference in pairs(refs) do
    if type(id)=="number" then
        local old=previous.refs[id]
        if not old or old.control~=reference.control or old.callback~=reference.callback then return end
    end
end
local chosen=nil
for _,entry in ipairs(popup.buttons) do
    if entry.id=={a['button_id']} and entry.enabled and entry.supported then chosen=refs[entry.id]; break end
end
if not chosen or type(chosen.callback)~="function" then return end
_CIV6FAIR_POPUP_SNAPSHOT=nil
if chosen.receiver then attempt(chosen.callback,chosen.receiver) else attempt(chosen.callback) end
'''


ACTIONS = {
    "popup_action": ActionSpec({"popup":"enum:"+"|".join(MANIFEST),"button_id":"id","revision":"identifier:POPUP_"},
        popup_action_body,"Respond to a currently displayed popup using its offered, content-bound button action.",turn_mode="ui"),
}
QUERIES = {}
