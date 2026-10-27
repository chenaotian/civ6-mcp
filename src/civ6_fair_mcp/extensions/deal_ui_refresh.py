"""Complete normal draft editing in the fixed stock diplomacy UI context.

GS resource/agreement/remove callbacks call UpdateDealPanel then
UpdateProposedWorkingDeal. The latter decides whether to request native INSPECT;
this adapter never forces button visibility or accesses private UI locals.
"""
from __future__ import annotations

from .diplomacy_actions import _target, _DEAL_HELPERS
from .popups import _READ_HELPERS

CONTEXT = "DiplomacyDealView"
DRAFT_ACTIONS = frozenset({"deal_clear", "deal_remove_item", "deal_add_item", "deal_add_war"})


_UI_READY = r'''
local function draft_ui_ready()
    if not ContextPtr or type(ContextPtr.GetID)~="function" then return false end
    local id=ContextPtr:GetID()
    if id~="DiplomacyDealView" and id~="DiplomacyDealView.xml" then return false end
    if not shown(ContextPtr) then return false end
    if not g_LocalPlayer or type(g_LocalPlayer.GetID)~="function" or g_LocalPlayer:GetID()~=me
        or not g_OtherPlayer or type(g_OtherPlayer.GetID)~="function" or g_OtherPlayer:GetID()~=target then return false end
    if type(UpdateDealPanel)~="function" or type(UpdateProposedWorkingDeal)~="function"
        or not UIManager or type(UIManager.GetModalContexts)~="function" then return false end
    local ancestry,current,depth={},ContextPtr,0
    while current do
        depth=depth+1
        if depth>32 or type(current.GetParent)~="function" then return false end
        ancestry[#ancestry+1]=current;current=current:GetParent()
    end
    local modals=UIManager:GetModalContexts()
    if type(modals)~="table" then return false end
    local count=0
    for _,modal in pairs(modals) do
        count=count+1
        if count>64 then return false end
        local found=false
        for _,ancestor in ipairs(ancestry) do if modal==ancestor then found=true;break end end
        if not found then return false end
    end
    local dialog_root=PopupDialog and PopupDialog.Controls and PopupDialog.Controls.PopupRoot
    if dialog_root and shown(dialog_root) then return false end
    return true
end
'''


def wrap_draft_edit(action: dict, body: str) -> str:
    """Preserve the audited edit body and all ordinary action-envelope guards."""
    if action["type"] not in DRAFT_ACTIONS:
        raise ValueError("invalid draft edit")
    return ("local _CIV6FAIR_V1=state\n" + _target(action["target_player"])
            + _DEAL_HELPERS + _READ_HELPERS + _UI_READY + r'''
local edit_session=session_for(target)
if not edit_session then return end
local ready_ok,ready=pcall(draft_ui_ready)
if not ready_ok or ready~=true then return end
local function edit_draft()
''' + body + r'''
end
edit_draft()
if out.accepted==true and session_for(target)==edit_session then
    local still_ok,still_ready=pcall(draft_ui_ready)
    if still_ok and still_ready==true then
        -- Suppress only responses to the previous cached offer. Do not mark
        -- it inactive: the existing event listener must receive the reply.
        state.deal_edited_wait_v1={session=session,sid=edit_session,player=me,
            other=target,phase=deal_phase(target,edit_session)}
        -- These are the actual stock functions, including their own PENDING
        -- reset, menu refresh, validity checks and optional normal INSPECT.
        -- No manual role update, automatic acceptance, or request replay.
        pcall(function()
            UpdateDealPanel(g_LocalPlayer)
            UpdateProposedWorkingDeal()
        end)
    end
end
''')
