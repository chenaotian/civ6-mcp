"""Fixed stock screens reached by automatic moments and the showcase button."""
import pytest

from civ6_fair_mcp.extensions.base import lua
from civ6_fair_mcp.extensions.popups import MANIFEST, POPUP_PATHS, discovery_lua
from civ6_fair_mcp.lua_common import wrap
from civ6_fair_mcp.ui_policy import public_popup
from test_popups import engine


SCREENS = (
    ("historic_moments", "HistoricMoments", "Close", "OnClose", "HistoricMoments_Opened"),
    ("great_works_overview", "GreatWorksOverview", "ModalScreenClose", "OnHideScreen", "GreatWorks_OpenGreatWorks"),
)


def install_screen(vm, key, context, control, callback, *, suffix=""):
    vm.execute(f'''
        settings.context={lua(context + suffix)}
        ExposedMembers.Civ6FairState.session="screen_test_session"
        Controls={{}}
        ContextPtr.children={{title,hidden}}
        title.text={lua("新历史时刻：首次环游世界，时代得分 +5" if key == "historic_moments" else "巨作总览：艺术博物馆，展位 3")}
        install({lua(control)},"关闭",{lua(callback)})
        {callback}=function()
            table.insert(calls,{lua(callback)})
            ContextPtr.visible=false
        end
        history_reads=0
        Game.GetHistoryManager=function()
            history_reads=history_reads+1
            error("HISTORY_DATABASE_MUST_NOT_BE_READ")
        end
        m_kQueuedPopups=setmetatable({{}},{{__index=function()
            history_reads=history_reads+1
            error("QUEUED_MOMENT_MUST_NOT_BE_READ")
        end}})
    ''')


@pytest.mark.parametrize("key,context,control,callback,event", SCREENS)
@pytest.mark.parametrize("prefix", ("/InGame/Screens", "/InGame/AdditionalUserInterfaces"))
@pytest.mark.parametrize("suffix", ("", ".xml"))
def test_fixed_screen_paths_discover_visible_context_without_reading_text(
    engine, key, context, control, callback, event, prefix, suffix
):
    vm, _, _, run = engine
    path = f"{prefix}/{context}{suffix}"
    assert path in POPUP_PATHS[key]
    vm.execute(f'paths[{lua(path)}]=ContextPtr')
    result = run(wrap(discovery_lua(), "screen_discovery", shared_context=True))
    assert result["popup_keys"] == [key]
    assert vm.globals().reads.text == vm.globals().reads.children == vm.globals().reads.hidden == 0


@pytest.mark.parametrize("key,context,control,callback,event", SCREENS)
@pytest.mark.parametrize("suffix", ("", ".xml"))
def test_already_open_screen_reads_displayed_controls_and_uses_normal_close(
    engine, key, context, control, callback, event, suffix
):
    vm, read, act, _ = engine
    install_screen(vm, key, context, control, callback, suffix=suffix)
    raw = read(key)
    popup = public_popup(raw, key)
    assert raw["active_turn"] is False
    assert popup["visible"] is True and popup["interactive"] is True
    assert popup["content"] == [vm.globals().title.text, "关闭"]
    assert [b["label"] for b in popup["buttons"]] == ["关闭"]
    assert vm.globals().history_reads == vm.globals().reads.hidden == 0
    assert act(popup["buttons"][0]["action"])["accepted"] is True
    assert list(vm.globals().calls.values()) == [callback]
    assert read(key, nonce="after_close")["popup"]["visible"] is False


@pytest.mark.parametrize("key,context,control,callback,event", SCREENS)
def test_hidden_screen_is_not_discovered_and_reads_no_old_content(
    engine, key, context, control, callback, event
):
    vm, read, _, run = engine
    install_screen(vm, key, context, control, callback)
    vm.execute(f'paths[{lua(POPUP_PATHS[key][0])}]=ContextPtr; ContextPtr.visible=false')
    discovered = run(wrap(discovery_lua(), "hidden_screen", shared_context=True))
    assert key not in discovered["popup_keys"]
    assert read(key)["popup"] == {"id": key, "visible": False, "content": [], "buttons": []}
    assert vm.globals().reads.text == vm.globals().reads.children == vm.globals().history_reads == 0


@pytest.mark.parametrize("displayed", (True, False))
def test_moment_popup_queue_does_not_expose_hidden_context_or_hidden_logical_parent(engine, displayed):
    vm, read, act, _ = engine
    install_screen(vm, *SCREENS[0][:4])
    vm.execute('''
        hidden_parent=node("SECRET_HIDDEN_POPUP",false,{},false,true)
        ContextPtr.GetParent=function() return hidden_parent end
        for _,child in ipairs(ContextPtr.children) do
            child.GetParent=function() return ContextPtr end
        end
        UIManager={IsInPopupQueue=function(self,context) return context==ContextPtr end}
    ''')
    vm.globals().ContextPtr.visible = displayed
    popup = read("historic_moments")["popup"]
    assert popup["visible"] is displayed
    if displayed:
        assert "首次环游世界" in popup["content"][0]
        assert act(popup["buttons"][0]["action"])["accepted"] is True
    else:
        assert popup["content"] == popup["buttons"] == []
    assert vm.globals().reads.hidden == vm.globals().history_reads == 0


@pytest.mark.parametrize("key,context,control,callback,event", SCREENS)
@pytest.mark.parametrize("mutation", ("hidden", "disabled", "new_text", "callback", "reopened"))
def test_screen_close_rejects_stale_or_unavailable_controls(
    engine, key, context, control, callback, event, mutation
):
    vm, read, act, _ = engine
    install_screen(vm, key, context, control, callback)
    action = read(key)["popup"]["buttons"][0]["action"]
    changes = {
        "hidden": f'Controls[{lua(control)}].visible=false',
        "disabled": f'Controls[{lua(control)}].disabled=true',
        "new_text": 'title.text="另一个已显示事件"',
        "callback": f'{callback}=function() table.insert(calls,"wrong") end',
        "reopened": f'event_callbacks[{lua("LuaEvents." + event)}]()',
    }
    vm.execute(changes[mutation])
    assert act(action)["accepted"] is False
    assert list(vm.globals().calls.values()) == []


@pytest.mark.parametrize("key,context,control,callback,event", SCREENS)
def test_another_native_modal_disables_underlying_screen_close(
    engine, key, context, control, callback, event
):
    vm, read, _, _ = engine
    install_screen(vm, key, context, control, callback)
    vm.execute('''
        other={}
        UIManager={IsModal=function() return false end,GetModalContexts=function() return {other} end}
    ''')
    popup = read(key)["popup"]
    assert popup["visible"] is True and popup["interactive"] is False
    assert len(popup["buttons"]) == 1 and "action" not in popup["buttons"][0]


def test_showcase_view_button_can_transition_to_observable_closable_overview(engine):
    vm, read, act, run = engine
    vm.execute('''
        settings.context="GreatWorkShowcase"
        Controls={}
        ContextPtr.children={}
        install("ViewGreatWorks","查看巨作","OnViewGreatWorks")
        showcase=ContextPtr
        overview=node("巨作总览",false,{})
        overview.GetID=function() return "GreatWorksOverview" end
        overview.LookUpControl=function(self,path) return paths[path] end
        OnViewGreatWorks=function()
            table.insert(calls,"OnViewGreatWorks")
            showcase.visible=false
            overview.visible=true
            ContextPtr=overview
            settings.context="GreatWorksOverview"
            Controls={}
            install("ModalScreenClose","关闭","OnHideScreen")
            OnHideScreen=function()
                table.insert(calls,"OnHideScreen")
                overview.visible=false
            end
        end
    ''')
    vm.execute(f'paths[{lua(POPUP_PATHS["great_work"][0])}]=showcase')
    vm.execute(f'paths[{lua(POPUP_PATHS["great_works_overview"][0])}]=overview')
    first = read("great_work")["popup"]
    assert act(first["buttons"][0]["action"])["accepted"] is True
    discovered = run(wrap(discovery_lua(), "after_showcase", shared_context=True))
    assert discovered["popup_keys"] == ["great_works_overview"]
    second = read("great_works_overview", nonce="overview")["popup"]
    assert "巨作总览" in second["content"]
    assert act(second["buttons"][0]["action"])["accepted"] is True
    discovered = run(wrap(discovery_lua(), "after_overview", shared_context=True))
    assert discovered["popup_keys"] == []
    assert list(vm.globals().calls.values()) == ["OnViewGreatWorks", "OnHideScreen"]


def test_new_screens_offer_only_the_stock_close_not_history_or_great_work_operations():
    for key, _, control, callback, _ in SCREENS:
        assert MANIFEST[key].buttons == ((control, callback, "关闭", "button"),)
