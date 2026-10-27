"""Execute backup Lua in an isolated VM; never connect to a running game."""

import hashlib
import json

from lupa import LuaRuntime
import pytest

from civ6_fair_mcp.fallback_lua import (
    MAX_CODE_BYTES, build_preflight, build_script, parse_result, validate_request,
)
from civ6_fair_mcp.policy import PolicyError
from civ6_fair_mcp.transport import _validate_script
from test_actions import BOOTSTRAP


SESSION = "f" * 32
IDENTITY = (SESSION, 0, 7, True)


def case_id(value):
    """Keep PYTEST_CURRENT_TEST below Windows' environment-value limit."""
    if isinstance(value, str) and len(value) > 48:
        digest = hashlib.sha256(value.encode("utf-8", errors="backslashreplace")).hexdigest()[:8]
        return f"text-{len(value)}-{digest}"
    return None


@pytest.fixture
def fallback_engine():
    vm = LuaRuntime(unpack_returned_tuples=True)
    output = []
    vm.globals().print = lambda *values: output.append("\t".join(map(str, values)))
    vm.execute(BOOTSTRAP)
    vm.execute("Game.GetWinningTeam=function() return -1 end; ExposedMembers={}; original_print=print")

    def run(script):
        output.clear()
        vm.execute(script)
        return "\n".join(output)

    assert json.loads(run(build_preflight(SESSION)).splitlines()[0].split(":", 1)[1])["fallback_eligible"]
    return vm, run, output


def execute(fixture, code):
    return parse_result(fixture[1](build_script(code, IDENTITY)))


def test_scalar_return_and_multiline_utf8_output_are_collected(fallback_engine):
    result = execute(fallback_engine, 'print("中文", true, nil, 42); print("甲\\n乙\\r\\n丙"); return "完成"')
    assert result == {"phase": "completed", "lines": ["中文\ttrue\tnil\t42", "甲", "乙", "丙"],
                      "truncated": False, "return_type": "string", "return_value": "完成"}


@pytest.mark.parametrize("code,kind,value", [
    ("return true", "boolean", True), ("return false", "boolean", False),
    ("return 123.25", "number", 123.25), ("return -5", "number", -5),
    ("return 1e200", "number", 1e200),
])
def test_scalar_types_are_preserved(fallback_engine, code, kind, value):
    result = execute(fallback_engine, code)
    assert result["return_type"] == kind and result["return_value"] == value


def test_returning_composite_never_traverses_or_calls_tostring(fallback_engine):
    result = execute(fallback_engine, '''
        local object=setmetatable({}, {__tostring=function() error('must not stringify') end,
            __pairs=function() error('must not traverse') end, __index=function() error('must not inspect') end})
        print(object)
        return object
    ''')
    assert result["phase"] == "completed" and result["lines"] == ["[table]"]
    assert result["return_type"] == "table" and result["return_omitted"] is True
    assert "return_value" not in result


@pytest.mark.parametrize("value,kind", [("function() end", "function"),
    ("coroutine.create(function() end)", "thread"), ("0/0", "number"), ("math.huge", "number")])
def test_unsupported_return_values_are_explicitly_omitted(fallback_engine, value, kind):
    result = execute(fallback_engine, "return " + value)
    assert result["phase"] == "completed" and result["return_type"] == kind
    assert result["return_omitted"] is True and "return_value" not in result


def test_only_first_return_value_is_retained(fallback_engine):
    result = execute(fallback_engine, 'return nil, "not returned", {secret="not traversed"}')
    assert result["return_type"] == "nil" and "return_value" not in result


def test_global_print_and_other_functions_are_not_intercepted(fallback_engine):
    vm, _, output = fallback_engine
    vm.execute('function native_callback() print("native log") end')
    result = execute(fallback_engine, 'native_callback(); _G.print("global log"); print("local output")')
    assert result["lines"] == ["local output"]
    assert output[:2] == ["native log", "global log"]
    assert vm.eval("print == original_print") is True


@pytest.mark.parametrize("code", ["local =", "end; side_effect=true; return function(print)"])
def test_syntax_error_does_not_execute_prefix_or_escape_chunk(fallback_engine, code):
    vm, _, _ = fallback_engine
    result = execute(fallback_engine, "side_effect=true; " + code)
    assert result["phase"] == "compile_error" and result["error_text"]
    assert vm.globals().side_effect is None


def test_runtime_error_preserves_prior_output_and_may_follow_side_effect(fallback_engine):
    vm, _, _ = fallback_engine
    result = execute(fallback_engine, 'side_effect=true; print("request submitted"); error("later failure")')
    assert vm.globals().side_effect is True
    assert result["phase"] == "runtime_error" and result["lines"] == ["request submitted"]
    assert "later failure" in result["error_text"]


def test_error_object_is_not_traversed_or_stringified(fallback_engine):
    result = execute(fallback_engine, 'error(setmetatable({}, {__tostring=function() error("do not call") end}))')
    assert result["phase"] == "runtime_error" and result["error_text"] == "[table]"


def test_oversize_error_is_omitted_without_cutting_utf8(fallback_engine):
    result = execute(fallback_engine, 'error(string.rep("汉",2000))')
    assert result["phase"] == "runtime_error" and result["truncated"] is True
    assert result["error_text"] == "[diagnostic omitted: too long]"


def test_line_count_is_bounded_for_many_prints(fallback_engine):
    result = execute(fallback_engine, 'for i=1,200 do print(i) end')
    assert result["phase"] == "completed" and result["truncated"] is True
    assert len(result["lines"]) == 128 and result["lines"][-1] == "128"


def test_byte_budget_is_bounded_for_many_maximum_lines(fallback_engine):
    result = execute(fallback_engine, 'for i=1,30 do print(string.rep("a",4096)) end')
    assert result["truncated"] is True and len(result["lines"]) == 16
    assert sum(len(line.encode("utf-8")) for line in result["lines"]) == 65536


def test_long_utf8_print_is_omitted_as_a_whole(fallback_engine):
    result = execute(fallback_engine, 'print(string.rep("汉",1365)); print(string.rep("汉",1366)); print("tail")')
    assert result["truncated"] is True
    assert result["lines"] == ["汉" * 1365, "tail"]


def test_print_argument_count_is_bounded(fallback_engine):
    code = 'print(' + ','.join(['"x"'] * 65) + '); print("tail")'
    result = execute(fallback_engine, code)
    assert result["truncated"] is True and result["lines"] == ["tail"]


def test_oversize_scalar_return_is_marked_omitted(fallback_engine):
    result = execute(fallback_engine, 'return string.rep("汉",1366)')
    assert result["return_type"] == "string" and result["return_omitted"] is True
    assert "return_value" not in result


def test_text_load_branch_is_used_without_loadstring(fallback_engine):
    vm, _, _ = fallback_engine
    vm.execute('''saved_load=load; loadstring=nil
        load=function(source,name,mode,environment)
            assert(mode=="t" and environment==_G); used_text_loader=true
            return saved_load(source,name,mode,environment)
        end''')
    assert execute(fallback_engine, 'print("text"); return 2')["return_value"] == 2
    assert vm.globals().used_text_loader is True


def test_native_loadstring_branch_has_priority(fallback_engine):
    vm, _, _ = fallback_engine
    vm.execute('''saved_load=load
        loadstring=function(source,name) used_loadstring=true; return saved_load(source,name,"t",_G) end
        load=function() error("must not use fallback load") end''')
    assert execute(fallback_engine, 'print("native"); return 3')["return_value"] == 3
    assert vm.globals().used_loadstring is True


def test_missing_compiler_never_executes_user_code(fallback_engine):
    vm, _, _ = fallback_engine
    vm.execute("load=nil; loadstring=nil")
    result = execute(fallback_engine, "side_effect=true")
    assert result["phase"] == "compiler_unavailable" and vm.globals().side_effect is None


def test_source_strings_and_placeholders_remain_literal(fallback_engine):
    code = 'print("__PLAYER__ __SESSION__ __TURN__ __CODE__"); return "\\\"; end; injected=true --"'
    vm, _, _ = fallback_engine
    result = execute(fallback_engine, code)
    assert result["phase"] == "completed"
    assert result["lines"] == ["__PLAYER__ __SESSION__ __TURN__ __CODE__"]
    assert result["return_value"] == '\"; end; injected=true --' and vm.globals().injected is None


@pytest.mark.parametrize("change", [
    "controls.active=false; controls.complete=false; controls.busy=true",
    "PlayersVisibility=nil; UI=nil; Players[0].IsTurnActive=nil; Players[0].IsTurnActiveComplete=nil",
    "ContextPtr={LookUpControl=function() error('unknown popup must not be scanned') end}",
])
def test_preflight_does_not_depend_on_active_turn_visibility_or_popup_scan(fallback_engine, change):
    vm, run, _ = fallback_engine
    vm.execute(change)
    response = json.loads(run(build_preflight(SESSION)).splitlines()[0].split(":", 1)[1])
    assert response["ok"] is True and response["fallback_eligible"] is True
    assert response["session"] == SESSION and response["player_id"] == 0
    assert "observation_token" not in response and "ui" not in response


@pytest.mark.parametrize("change", [
    "GameConfiguration.IsAnyMultiplayer=function() return true end",
    "GameConfiguration.IsHotseat=function() return true end",
    "GameConfiguration.IsWorldBuilderEditor=function() return true end",
    "Automation.IsActive=function() return true end",
    "Players[0].IsAlive=function() return false end",
    "Players[0].IsHuman=function() return false end",
    "Game.GetLocalObserver=function() return 3 end",
    "Game.GetWinningTeam=function() return 0 end",
    "Game.GetWinningTeam=nil",
])
def test_preflight_rejects_nonplayer_or_terminal_states(fallback_engine, change):
    vm, run, _ = fallback_engine
    vm.execute(change)
    response = json.loads(run(build_preflight(SESSION)).splitlines()[0].split(":", 1)[1])
    assert response == {"ok": False, "error": "unavailable"}


@pytest.mark.parametrize("change", [
    "controls.player=1", "controls.turn=8", "_CIV6FAIR_V1.session='different_session'",
    "load_event()", "player_event()", "Game.GetLocalObserver=function() return 3 end",
    "GameConfiguration.IsAnyMultiplayer=function() return true end",
    "GameConfiguration.IsHotseat=function() return true end",
    "Automation.IsActive=function() return true end",
    "Players[0].IsAlive=function() return false end",
    "Players[0].IsHuman=function() return false end",
    "Game.GetWinningTeam=function() return 0 end",
    "_CIV6FAIR_V1=nil; ExposedMembers=nil",
])
def test_identity_is_rechecked_immediately_before_user_code(fallback_engine, change):
    vm, _, _ = fallback_engine
    vm.execute(change)
    result = execute(fallback_engine, 'side_effect=true; print("must not run")')
    assert result["phase"] == "identity_rejected" and result["lines"] == []
    assert vm.globals().side_effect is None


@pytest.mark.parametrize("change", ["Game.GetLocalPlayer=nil", "Game.GetLocalObserver=nil", "Players=nil"])
def test_missing_target_context_identity_capability_never_executes(fallback_engine, change):
    vm, _, _ = fallback_engine
    vm.execute(change)
    result = execute(fallback_engine, "side_effect=true")
    assert result["phase"] in {"identity_rejected", "outcome_unknown"}
    assert vm.globals().side_effect is None


def test_ui_context_can_use_the_explicit_shared_session(fallback_engine):
    vm, _, _ = fallback_engine
    vm.execute("_CIV6FAIR_V1=nil")
    assert execute(fallback_engine, 'return "shared"')["return_value"] == "shared"


@pytest.mark.parametrize("context,expected", [("ingame", "InGame"), ("gamecore", "GameCore_Tuner"),
    ("NewPopup.xml", "NewPopup.xml")])
def test_request_context_aliases_and_digest(context, expected):
    result = validate_request("print('你好')", "  Normal popup interface unavailable.  ", ["get_pending_decisions"], context)
    assert result["context"] == expected and result["reason"] == "Normal popup interface unavailable."
    assert result["code_sha256"] == hashlib.sha256("print('你好')".encode()).hexdigest()


@pytest.mark.parametrize("field,value", [
    ("code", None), ("code", ""), ("code", " \n"), ("code", "\x00"), ("code", "\x1bLua"),
    ("code", "\ud800"), ("code", "汉" * 10923), ("code", "x" * (MAX_CODE_BYTES+1)),
    ("reason", None), ("reason", ""), ("reason", " \n"), ("reason", "\ud800"), ("reason", "x" * 2001),
    ("attempted_tools", []), ("attempted_tools", "act"), ("attempted_tools", ["run_lua"]),
    ("attempted_tools", ["get_rules"]), ("attempted_tools", ["query_manual"]),
    ("attempted_tools", ["act", "act"]), ("attempted_tools", [True]),
    ("context", None), ("context", "InGame\n"), ("context", "../InGame"),
    ("context", "InGame;print(1)"), ("context", "汉"), ("context", "a" * 129),
], ids=case_id)
def test_invalid_requests_are_rejected_before_generation(field, value):
    arguments = {"code": "return 1", "reason": "Normal interface unavailable", "attempted_tools": ["act"], "context": "InGame"}
    arguments[field] = value
    with pytest.raises(ValueError):
        validate_request(**arguments)


@pytest.mark.parametrize("code", [
    "--" + "汉" * 10922, "--" + "\\" * (MAX_CODE_BYTES-2),
    "--" + "\t" * (MAX_CODE_BYTES-2), "\n" * (MAX_CODE_BYTES-8) + "return 1",
], ids=case_id)
def test_valid_near_limit_source_still_fits_transport(code):
    request = validate_request(code, "Normal interface unavailable", ["act"], "InGame")
    _validate_script(build_script(request["code"], IDENTITY))


def packet(**changes):
    return "CIV6FAIR_JSON:" + json.dumps({"phase": "completed", "lines": [], "truncated": False, **changes}) + "\n---END---"


@pytest.mark.parametrize("text", [
    None, False, 1, "", "\ud800", "x" * (512 * 1024 + 1),
    "CIV6FAIR_JSON:[]", "CIV6FAIR_JSON:{bad}",
    "CIV6FAIR_JSON:{\"phase\":\"completed\",\"phase\":\"runtime_error\",\"lines\":[],\"truncated\":false}",
    packet() + "\n" + packet(), packet(phase="made_up"), packet(lines="not a list"),
    packet(truncated=1), packet(lines=["x"] * 129), packet(lines=[True]),
    packet(lines=["汉" * 1366]), packet(lines=["x" * 4096] * 17),
    packet(error_text="x" * 4097), packet(return_value={}), packet(return_value=float("nan")),
    packet(phase=[]), packet(phase={}), packet(return_type=[]),
    packet(lines=["\ud800"]), packet(error_text="\ud800"), packet(return_type="string", return_value="\ud800"),
    packet(return_type="number", return_value=10**400), packet(return_type="number", return_value="1"),
    packet(return_type="boolean", return_value=1), packet(return_value=True),
    packet(return_type="made_up"), packet(return_omitted=1),
], ids=case_id)
def test_invalid_wire_responses_fail_closed(text):
    with pytest.raises(PolicyError):
        parse_result(text)


def test_unknown_wire_fields_are_not_forwarded():
    assert parse_result(packet(hidden="must not forward")) == {"phase": "completed", "lines": [], "truncated": False}
