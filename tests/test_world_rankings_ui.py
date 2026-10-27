"""A visible rankings sidebar has an exit, without exposing its cached data."""
import pytest

from civ6_fair_mcp.extensions.base import lua
from civ6_fair_mcp.extensions.popups import MANIFEST, POPUP_PATHS, discovery_lua
from civ6_fair_mcp.lua_common import wrap
from civ6_fair_mcp.ui_policy import public_popup
from test_popups import engine


def install_rankings(vm, suffix=""):
    vm.execute(f'''
        settings.context={lua("WorldRankings" + suffix)}
        ExposedMembers.Civ6FairState.session="rankings_test_session"
        Controls={{}}
        ContextPtr.children={{}}
        ContextPtr.GetText=function() error("CONTEXT_TEXT_MUST_NOT_BE_READ") end
        ContextPtr.GetChildren=function() error("RANKING_CONTEXT_MUST_NOT_BE_TRAVERSED") end
        slide=node("CACHED_RANKING_STATISTICS",true,{{}},false,true)
        slide.GetParent=function() return ContextPtr end
        Controls.SlideAnim=slide
        Controls.Title=node("世界排名",true,{{}})
        Controls.Title.GetParent=function() return slide end
        Controls.CloseButton=node("关闭",true,{{}})
        Controls.CloseButton.GetParent=function() return slide end
        unseen=node("UNMET_CIVILIZATION_STATS",true,{{}},false,true)
        Controls.CultureView=node("",false,{{unseen}})
        Controls.OverallView=node("",true,{{unseen}})
        slide.children={{Controls.Title,Controls.CloseButton,Controls.OverallView,Controls.CultureView}}
        raw_reads=0
        Game.GetHistoryManager=function() raw_reads=raw_reads+1; error("NO_HISTORY") end
        Game.GetVictoryProgressForTeam=function() raw_reads=raw_reads+1; error("NO_RANKING_API") end
        Close=function()
            table.insert(calls,"Close")
            ContextPtr.visible=false
        end
    ''')
    path = f"/InGame/PartialScreens/WorldRankings{suffix}"
    vm.execute(f'paths[{lua(path)}]=ContextPtr; paths[{lua(path + "/SlideAnim")}]=slide')
    return path


@pytest.mark.parametrize("suffix", ("", ".xml"))
def test_visible_sidebar_is_discovered_and_closed_without_traversing_rankings(engine, suffix):
    vm, read, act, run = engine
    path = install_rankings(vm, suffix)
    assert path in POPUP_PATHS["world_rankings"]
    discovered = run(wrap(discovery_lua(), "rankings_discovery", shared_context=True))
    assert discovered["popup_keys"] == ["world_rankings"]
    assert vm.globals().reads.text == vm.globals().reads.children == vm.globals().reads.hidden == 0
    raw = read("world_rankings")
    popup = public_popup(raw, "world_rankings")
    assert popup["content"] == ["世界排名侧栏已打开。", "世界排名"]
    assert [b["label"] for b in popup["buttons"]] == ["关闭"]
    assert act(popup["buttons"][0]["action"])["accepted"] is True
    assert list(vm.globals().calls.values()) == ["Close"]
    assert read("world_rankings", nonce="closed")["popup"]["visible"] is False
    assert vm.globals().reads.children == vm.globals().reads.hidden == vm.globals().raw_reads == 0


@pytest.mark.parametrize("mutation", (
    "ContextPtr.visible=false", "slide.visible=false", "slide.IsVisible=nil",
    "slide.IsVisible=function() return 1 end",
))
def test_hidden_or_unproven_slide_never_reads_cached_title_or_rankings(engine, mutation):
    vm, read, _, run = engine
    install_rankings(vm)
    vm.execute(mutation)
    discovered = run(wrap(discovery_lua(), "collapsed_rankings", shared_context=True))
    assert discovered["popup_keys"] == []
    assert read("world_rankings")["popup"] == {
        "id": "world_rankings", "visible": False, "content": [], "buttons": []
    }
    assert vm.globals().reads.text == vm.globals().reads.children == vm.globals().reads.hidden == 0


def test_absent_slide_has_no_context_only_discovery_fallback(engine):
    vm, read, _, run = engine
    path = install_rankings(vm)
    vm.execute(f'paths[{lua(path + "/SlideAnim")}]=nil; Controls.SlideAnim=nil')
    assert run(wrap(discovery_lua(), "missing_slide", shared_context=True))["popup_keys"] == []
    assert read("world_rankings")["popup"]["visible"] is False
    assert vm.globals().reads.text == vm.globals().reads.children == 0


def test_collector_rechecks_slide_parent_visibility(engine):
    vm, read, _, _ = engine
    install_rankings(vm)
    vm.execute('''
        parent=node("HIDDEN_PARENT",false,{},false,true)
        slide.GetParent=function() return parent end
    ''')
    assert read("world_rankings")["popup"]["visible"] is False
    assert vm.globals().reads.text == vm.globals().reads.hidden == 0


@pytest.mark.parametrize("change", (
    'slide.visible=false',
    'Controls.CloseButton.visible=false',
    'Controls.CloseButton.disabled=true',
    'Controls.Title.text="另一页标题"',
    'Close=function() table.insert(calls,"wrong_callback") end',
    'event_callbacks["LuaEvents.PartialScreenHooks_OpenWorldRankingsCulture"]()',
    'event_callbacks["LuaEvents.WorldRankings_Close"]()',
))
def test_sidebar_exit_rechecks_current_display_button_and_lifecycle(engine, change):
    vm, read, act, _ = engine
    install_rankings(vm)
    action = read("world_rankings")["popup"]["buttons"][0]["action"]
    vm.execute(change)
    assert act(action)["accepted"] is False
    assert list(vm.globals().calls.values()) == []


def test_hidden_title_is_not_read_but_visible_close_remains_usable(engine):
    vm, read, act, _ = engine
    install_rankings(vm)
    vm.execute('Controls.Title=node("HIDDEN_TITLE",false,{},false,true)')
    popup = read("world_rankings")["popup"]
    assert popup["content"] == ["世界排名侧栏已打开。"]
    assert act(popup["buttons"][0]["action"])["accepted"] is True
    assert vm.globals().reads.hidden == 0


def test_native_modal_blocks_sidebar_exit(engine):
    vm, read, _, _ = engine
    install_rankings(vm)
    vm.execute('''
        other={}
        UIManager={IsModal=function() return false end,GetModalContexts=function() return {other} end}
    ''')
    popup = read("world_rankings")["popup"]
    assert popup["interactive"] is False
    assert "action" not in popup["buttons"][0]


def test_sidebar_does_not_dispatch_a_cached_popup_dialog_or_arbitrary_tab_callbacks(engine):
    vm, read, act, _ = engine
    install_rankings(vm)
    vm.execute('''
        PopupDialog=setmetatable({}, {__index=function() error("CACHED_DIALOG_MUST_NOT_BE_READ") end})
        Controls.ExpandExtraTabs=node("更多排名",true,{})
        ToggleExtraTabs=function() table.insert(calls,"wrong_tab") end
    ''')
    popup = read("world_rankings")["popup"]
    assert len(popup["buttons"]) == 1
    assert act(popup["buttons"][0]["action"])["accepted"] is True
    assert list(vm.globals().calls.values()) == ["Close"]
    assert MANIFEST["world_rankings"].buttons == (("CloseButton", "Close", "关闭", "button"),)


def test_normal_close_animation_can_remain_visible_until_native_completion(engine):
    vm, read, act, _ = engine
    install_rankings(vm)
    vm.execute('''
        Close=function()
            table.insert(calls,"Close")
            settings.closing=true
        end
    ''')
    action = read("world_rankings")["popup"]["buttons"][0]["action"]
    assert act(action)["accepted"] is True
    assert vm.globals().settings.closing is True
    assert read("world_rankings", nonce="animating_out")["popup"]["visible"] is True
    vm.execute("ContextPtr.visible=false")
    assert read("world_rankings", nonce="animation_done")["popup"]["visible"] is False
    assert list(vm.globals().calls.values()) == ["Close"]
