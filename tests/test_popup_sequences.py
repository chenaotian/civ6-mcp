"""Exercise a queued notification lifecycle without exposing undisplayed items."""
from test_popups import engine


def test_each_boost_requires_observation_of_its_own_text_and_button(engine):
    vm, read, act, _ = engine
    vm.execute('''
        local queued = {"鼓舞！政治哲学已获提升", "尤里卡！造船术已获提升"}
        local current = 1
        title.text = queued[current]
        OnClose = function()
            table.insert(calls, "OnClose")
            current = current + 1
            if queued[current] then title.text = queued[current]
            else ContextPtr.visible = false end
        end
    ''')
    first = read()["popup"]
    assert "鼓舞！政治哲学已获提升" in first["content"]
    assert all("造船术" not in text for text in first["content"])
    first_action = first["buttons"][0]["action"]
    assert act(first_action)["accepted"] is True
    assert act(first_action)["accepted"] is False
    second = read(nonce="next_boost")["popup"]
    assert "尤里卡！造船术已获提升" in second["content"]
    assert second["revision"] != first["revision"]
    assert act(second["buttons"][0]["action"])["accepted"] is True
    assert read(nonce="after_queue")["popup"]["visible"] is False
    assert list(vm.globals().calls.values()) == ["OnClose", "OnClose"]
