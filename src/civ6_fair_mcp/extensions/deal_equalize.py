"""The visible stock EqualizeDeal button, not an AI valuation interface.

GS DiplomacyDealView.lua:163-165,343,518-520 sends a single normal EQUALIZE
request. Qualification is witnessed in that fixed Lua context using its actual
visible/enabled control; no reconstructed button state or private UI upvalues.
"""
from __future__ import annotations

from .base import ActionSpec, QuerySpec, lua
from .diplomacy_actions import _target, _DEAL_HELPERS
from .popups import _READ_HELPERS

CONTEXT = "DiplomacyDealView"
CATEGORY = "deal_negotiation"


_EQUALIZE_HELPERS = r'''
local function equalize_candidate()
    -- g_LocalPlayer/g_OtherPlayer are the stock panel's public globals,
    -- assigned in OnShow (GS:3024-3025). Read IDs only, never their inventories.
    if not ContextPtr or type(ContextPtr.GetID)~="function" or not Controls then return end
    local context_id=ContextPtr:GetID()
    if context_id~="DiplomacyDealView" and context_id~="DiplomacyDealView.xml" then return end
    local button=Controls.EqualizeDeal
    if not button or type(button.IsVisible)~="function" or type(button.IsDisabled)~="function"
        or type(button.GetParent)~="function" or type(ContextPtr.IsVisible)~="function" then return end
    if not g_LocalPlayer or type(g_LocalPlayer.GetID)~="function"
        or not g_OtherPlayer or type(g_OtherPlayer.GetID)~="function" then return end
    if not UIManager or type(UIManager.GetModalContexts)~="function" then return end
    if type(other.IsHuman)~="function" or type(other.IsMajor)~="function"
        or type(other.IsAlive)~="function" then return end
    if not DealManager or type(DealManager.HasPendingDeal)~="function"
        or type(DealManager.SendWorkingDeal)~="function" or not DealDirection
        or not DealProposalAction or not int(DealProposalAction.EQUALIZE) then return end
    out.supported=true
    if not shown(ContextPtr) or not enabled(button) then return end
    -- Do not treat a missing parent API as a complete visibility proof. The
    -- fixed button must actually lead back to this panel through visible
    -- controls; no sibling traversal or control-name inspection is needed.
    local button_parent, button_depth=button,0
    while button_parent~=ContextPtr do
        button_depth=button_depth+1
        if not button_parent or button_depth>32 then return end
        if type(button_parent.GetParent)~="function"
            or type(button_parent.IsVisible)~="function" then out.supported=false;return end
        if button_parent:IsVisible()~=true then return end
        button_parent=button_parent:GetParent()
    end
    if g_LocalPlayer:GetID()~=me or g_OtherPlayer:GetID()~=target then return end
    if other:IsHuman()~=false or other:IsMajor()~=true or other:IsAlive()~=true then return end
    -- Any separate modal can cover this button. A modal ancestor of this
    -- fixed panel is allowed; a child confirmation or unrelated modal is not.
    local ancestry, current, depth={},ContextPtr,0
    while current do
        depth=depth+1
        if depth>32 then return end
        ancestry[#ancestry+1]=current
        if type(current.GetParent)~="function" then out.supported=false;return end
        current=current:GetParent()
    end
    local modals=UIManager:GetModalContexts()
    if type(modals)~="table" then out.supported=false;return end
    local modal_count=0
    for _,modal in pairs(modals) do
        modal_count=modal_count+1
        if modal_count>64 then out.supported=false;return end
        local is_ancestor=false
        for _,ancestor in ipairs(ancestry) do if ancestor==modal then is_ancestor=true;break end end
        if not is_ancestor then return end
    end
    local dialog_root=PopupDialog and PopupDialog.Controls and PopupDialog.Controls.PopupRoot
    if dialog_root and shown(dialog_root) then return end
    local sid=session_for(target)
    if not sid then return end
    out.decision_mode="diplomacy"
    local phase=deal_phase(target,sid)
    if not phase or phase.active~=true or phase.demand==true
        or proposal_is(phase.action,"DEMANDED") or proposal_is(phase.action,"EQUALIZE_FAILED") then return end
    if DealManager.HasPendingDeal(me,target)~=false then return end
    local waiting=state.equalize_waiting_v1
    if waiting and waiting.session==session and waiting.sid==sid and waiting.player==me
        and waiting.other==target and waiting.phase==phase then return end
    local draft=working(target,DealDirection.OUTGOING)
    if not draft or type(draft.IsValid)~="function" or type(draft.GetItemCount)~="function"
        or type(draft.HasUnacceptableItems)~="function" or type(draft.Items)~="function" then
        out.supported=false;return
    end
    local count=draft:GetItemCount()
    if not int(count) or count<1 or count>128 or draft:IsValid()~=true
        or draft:HasUnacceptableItems()~=false then return end
    -- Do not hash or expose anything about a partially filtered draft.
    local seen=0
    for item in draft:Items() do
        seen=seen+1
        if seen>128 or not safe_deal_item(item,target) then return end
    end
    if seen~=count then return end
    local signature=terms_signature(draft)
    if not signature then out.supported=false;return end
    return {sid=sid,phase=phase,signature=signature,button=button}
end
'''


def _body(a: dict) -> str:
    # Shared-context wrap supplies state from ExposedMembers.Civ6FairState.
    # The existing diplomacy helpers intentionally reference the same lexical
    # alias here; do not install or duplicate their InGame event listeners.
    return ("local _CIV6FAIR_V1=state\n" + _target(a["target_player"])
            + _DEAL_HELPERS + _READ_HELPERS + _EQUALIZE_HELPERS)


def negotiation(a: dict) -> str:
    return _body(a) + r'''
local ok,candidate=pcall(equalize_candidate)
if not ok then out.supported=false;return end
if not candidate then return end
local name="请求公平报价"
-- Only this already-visible stock button's caption is read, never deal text.
if type(candidate.button.GetText)=="function" then
    local text_ok,text=pcall(candidate.button.GetText,candidate.button)
    if text_ok and type(text)=="string" and #text>0 and #text<=512
        and not text:find('[%z\1-\31]') then name=text end
end
add_item({id="equalize",name=name,
    description="请求对方按当前草案提出报价；不会接受交易。完成后重新读取经过权限过滤的 deal_state。",
    scope="self",owner_id=me,action={type="deal_equalize",target_player=math.floor(target),
        session_id=math.floor(candidate.sid),signature=candidate.signature}})
'''


def equalize(a: dict) -> str:
    return _body(a) + f'''
local ok,candidate=pcall(equalize_candidate)
if not ok or not candidate or candidate.sid~={a['session_id']}
    or candidate.signature~={lua(a['signature'])} then return end
-- Preserve active phase: normal DealUpdated/Incoming must remain observable.
-- A new public event replaces the phase object, naturally releasing this
-- one-shot wait even when SendWorkingDeal dispatches the event synchronously.
state.equalize_waiting_v1={{session=session,sid=candidate.sid,player=me,
    other=target,phase=candidate.phase}}
attempt(DealManager.SendWorkingDeal,DealProposalAction.EQUALIZE,me,target)
'''


ACTIONS = {
    "deal_equalize": ActionSpec({"target_player": "id", "session_id": "id", "signature": "identifier:DEAL_"},
        equalize, "Use the actual visible EqualizeDeal button for this exact safe outgoing draft; never accepts or retries.",
        turn_mode="diplomacy"),
}
QUERIES = {
    CATEGORY: QuerySpec({"target_player": "id"}, negotiation,
        "The currently visible normal equalization request, bound to the local deal panel and safe outgoing draft."),
}
