"""Independent regressions derived from stock UI modality, not callback mocks.

Base/Assets/UI/Popups/InGamePopup.lua:44 pushes a modal without hiding the
underlying contexts. Its InputHandler consumes all input while open (:74).
A visible button behind it is therefore not an available player action.
"""

from test_popups import engine  # noqa: F401 -- shared Lua-runtime fixture

from civ6_fair_mcp.extensions.base import lua
from civ6_fair_mcp.extensions.popups import POPUP_PATHS


def show_generic_modal(vm):
    vm.execute('external_modal=node("Current blocking confirmation",true,{})')
    for path in POPUP_PATHS["generic"]:
        vm.execute(f'paths[{lua(path + "/PopupRoot")}]=external_modal')


def test_visible_underlying_dialog_is_readable_but_not_actionable(engine):
    vm, read, _, _ = engine
    show_generic_modal(vm)
    popup = read()["popup"]
    assert popup["visible"] is True
    assert "尤里卡！航海术研究获得提升" in popup["content"]
    assert popup["buttons"]
    assert all("action" not in button for button in popup["buttons"])


def test_modal_opened_after_snapshot_rejects_underlying_old_button(engine):
    vm, read, act, _ = engine
    action = read()["popup"]["buttons"][0]["action"]
    show_generic_modal(vm)
    assert act(action)["accepted"] is False
    assert len(vm.globals().calls) == 0


def test_hidden_generic_modal_does_not_block_current_visible_dialog(engine):
    vm, read, act, _ = engine
    show_generic_modal(vm)
    vm.execute('external_modal.visible=false')
    action = read()["popup"]["buttons"][0]["action"]
    assert act(action)["accepted"] is True
    assert list(vm.globals().calls.values()) == ["OnClose"]
