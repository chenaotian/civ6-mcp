"""Fixed UI/phase-only Equalize diagnostic; close the MCP client first.

No working-deal, item, caption, inventory, private valuation, or operation call.
Output contains only fixed stage names and booleans. Root owns live execution.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import secrets

from civ6_fair_mcp.extensions.base import LUA_HELPERS, validate
from civ6_fair_mcp.extensions.deal_equalize import CONTEXT
from civ6_fair_mcp.extensions.diplomacy_actions import _target, _DEAL_HELPERS
from civ6_fair_mcp.extensions.popups import _READ_HELPERS
from civ6_fair_mcp.lua_common import wrap
from civ6_fair_mcp.policy import envelope, parse_response
from civ6_fair_mcp.transport import FireTunerTransport

STAGES = frozenset({"start", "known_counterpart", "context", "button", "identity",
                    "phase", "complete"})
CHECKS = frozenset({"ran", "context_matches", "context_shown", "button_exists",
    "button_visible", "button_enabled", "button_shown", "button_parent_matches",
    "button_parent_api_valid", "panel_local_matches", "panel_other_matches",
    "modal_api_valid", "modal_blocks", "inline_dialog_shown", "session_present",
    "phase_present", "phase_active", "phase_demand", "phase_updated",
    "phase_pending", "phase_accepted", "phase_proposed", "phase_adjusted",
    "phase_rejected", "phase_equalize_failed", "phase_inspect", "phase_closed",
    "phase_rejected_permanent", "phase_demanded", "native_pending", "waiting_same_phase"})


def probe_body(target: int) -> str:
    validate(target, "id")
    if target > 63:
        raise ValueError("invalid target")
    return '''
local probe_stage="start";local checks={}
local ran=pcall(function()
local _CIV6FAIR_V1=state
''' + LUA_HELPERS + _target(target) + _DEAL_HELPERS + _READ_HELPERS + '''
probe_stage="known_counterpart"
if not ContextPtr or type(ContextPtr.GetID)~="function" then return end
local id=ContextPtr:GetID()
checks.context_matches=id=="DiplomacyDealView" or id=="DiplomacyDealView.xml"
if not checks.context_matches then return end
probe_stage="context"
checks.context_shown=shown(ContextPtr)==true
local button=Controls and Controls.EqualizeDeal
checks.button_exists=button~=nil
if button then
    probe_stage="button"
    if type(button.IsVisible)=="function" then
        local value=button:IsVisible()
        if type(value)=="boolean" then checks.button_visible=value end
    end
    if type(button.IsDisabled)=="function" then
        local value=button:IsDisabled()
        if type(value)=="boolean" then checks.button_enabled=not value end
    end
    checks.button_shown=shown(button)==true
    local current,depth,valid=button,0,true
    while current and current~=ContextPtr do
        depth=depth+1
        if depth>32 or type(current.GetParent)~="function" then valid=false;break end
        current=current:GetParent()
    end
    checks.button_parent_api_valid=valid
    checks.button_parent_matches=valid and current==ContextPtr
end
probe_stage="identity"
if g_LocalPlayer and type(g_LocalPlayer.GetID)=="function" then checks.panel_local_matches=g_LocalPlayer:GetID()==me end
if g_OtherPlayer and type(g_OtherPlayer.GetID)=="function" then checks.panel_other_matches=g_OtherPlayer:GetID()==target end
if checks.panel_local_matches~=true or checks.panel_other_matches~=true then return end
if UIManager and type(UIManager.GetModalContexts)=="function" then
    local modals=UIManager:GetModalContexts()
    checks.modal_api_valid=type(modals)=="table"
    if checks.modal_api_valid then
        local ancestors,current,depth={},ContextPtr,0
        while current do
            depth=depth+1
            if depth>32 or type(current.GetParent)~="function" then checks.modal_api_valid=false;break end
            ancestors[#ancestors+1]=current;current=current:GetParent()
        end
        if checks.modal_api_valid then
            local blocked,count=false,0
            for _,modal in pairs(modals) do
                count=count+1
                if count>64 then checks.modal_api_valid=false;break end
                local found=false
                for _,ancestor in ipairs(ancestors) do if modal==ancestor then found=true;break end end
                if not found then blocked=true end
            end
            if checks.modal_api_valid then checks.modal_blocks=blocked end
        end
    end
end
local dialog_root=PopupDialog and PopupDialog.Controls and PopupDialog.Controls.PopupRoot
checks.inline_dialog_shown=dialog_root~=nil and shown(dialog_root)==true
probe_stage="phase"
local sid=session_for(target)
checks.session_present=sid~=nil
if not sid then return end
local phase=deal_phase(target,sid)
checks.phase_present=phase~=nil
if phase then
    checks.phase_active=phase.active==true
    checks.phase_demand=phase.demand==true
    checks.phase_updated=phase.updated==true
    for _,name in ipairs({"PENDING","ACCEPTED","PROPOSED","ADJUSTED","REJECTED",
        "EQUALIZE_FAILED","INSPECT","CLOSED","REJECTED_PERMANENT","DEMANDED"}) do
        checks["phase_"..string.lower(name)]=proposal_is(phase.action,name)==true
    end
    local waiting=state.equalize_waiting_v1
    checks.waiting_same_phase=waiting~=nil and waiting.session==session and waiting.sid==sid
        and waiting.player==me and waiting.other==target and waiting.phase==phase
end
if DealManager and type(DealManager.HasPendingDeal)=="function" then
    local pending=DealManager.HasPendingDeal(me,target)
    if type(pending)=="boolean" then checks.native_pending=pending end
end
probe_stage="complete"
end)
checks.ran=ran
out.items=nil;out.probe_stage=probe_stage;out.probe_checks=checks
'''


def project(raw: dict) -> dict:
    envelope(raw)
    stage, checks = raw.get("probe_stage"), raw.get("probe_checks")
    if (type(stage) is not str or stage not in STAGES or type(checks) is not dict
            or checks.keys() - CHECKS or any(type(v) is not bool for v in checks.values())):
        raise ValueError("invalid fixed diagnostic")
    return {"ok": True, "stage": stage, "checks": checks}


async def run(target: int) -> dict:
    body = probe_body(target)
    client = FireTunerTransport()
    try:
        baseline = parse_response(await client.execute(wrap("", secrets.token_hex(16))))
        generation = client.connection_generation
        result = parse_response(await client.execute(wrap(body, secrets.token_hex(16), shared_context=True),
            context=CONTEXT, expected_generation=generation))
        if envelope(result)[:3] != envelope(baseline)[:3] or client.connection_generation != generation:
            raise ValueError("stale diagnostic")
        return project(result)
    except Exception:
        return {"ok": False, "error": "equalize_gate_unavailable"}
    finally:
        try:
            await client.close()
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-player", type=int, required=True)
    args = parser.parse_args()
    try:
        value = asyncio.run(run(args.target_player))
    except Exception:
        value = {"ok": False, "error": "equalize_gate_unavailable"}
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    raise SystemExit(0 if value["ok"] else 1)
