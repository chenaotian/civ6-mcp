"""Interactive test client for the project's real MCP server.

Each input line names one public tool and its JSON arguments. There is no Lua
or debug execution endpoint. Actions use the most recent observation token.
Public results are journaled with capabilities removed; game strings are data.
"""
import asyncio
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if k != "observation_token"}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


async def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-name", default="overnight-test")
    args = parser.parse_args()
    if not args.run_name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in args.run_name):
        parser.error("run-name must contain only letters, digits, hyphens and underscores")
    directory = root / "artifacts" / args.run_name
    directory.mkdir(parents=True, exist_ok=True)
    params = StdioServerParameters(command=sys.executable,
        args=["-m", "civ6_fair_mcp"], cwd=str(root))
    latest = None
    with (directory / "client-stderr.log").open("a", encoding="utf-8") as errors:
        async with stdio_client(params, errlog=errors) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                tools = {t.name for t in (await client.list_tools()).tools}
                rules = (await client.call_tool("get_rules", {})).structuredContent
                print(json.dumps({"ready": True, "version": rules["version"],
                    "tools": sorted(tools)}, ensure_ascii=False), flush=True)
                async def call(tool, args):
                    nonlocal latest
                    if tool not in tools:
                        raise ValueError("Unknown public tool")
                    args = dict(args)
                    if tool == "act":
                        args.setdefault("observation_token", latest or "")
                        latest = None
                    result = await client.call_tool(tool, args)
                    value = result.structuredContent
                    if value is None:
                        value = {"mcp_error": result.isError,
                                 "content": [c.text for c in result.content if c.type == "text"]}
                    if tool != "get_rules":
                        latest = value.get("observation_token")
                    public = clean(value)
                    record = {"time": datetime.now(timezone.utc).isoformat(),
                              "tool": tool, "args": clean(args), "result": public}
                    with (directory / "journal.jsonl").open("a", encoding="utf-8") as journal:
                        journal.write(json.dumps(record, ensure_ascii=False) + "\n")
                    (directory / "latest.json").write_text(
                        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
                    return public

                async def advance(count):
                    if type(count) is not int or not 1 <= count <= 10:
                        raise ValueError("Advance count must be 1..10")
                    completed = 0
                    for _ in range(count):
                        state = await call("get_player_state", {})
                        if not state.get("ok") or state.get("ui", {}).get("status") != "ready":
                            return {"advanced": completed, "stopped": "attention", "state": state}
                        turn = state["turn"]
                        outcome = await call("act", {"action": {"type": "end_turn"}})
                        if not outcome.get("accepted"):
                            return {"advanced": completed, "stopped": "end_turn_rejected", "outcome": outcome}
                        for _ in range(20):
                            await asyncio.sleep(0.5)
                            state = await call("get_player_state", {})
                            if not state.get("ok") or state.get("ui", {}).get("status") in {"popup", "decision", "partial", "unavailable"}:
                                return {"advanced": completed, "stopped": "attention", "state": state}
                            if state.get("turn", turn) > turn and state.get("active_turn"):
                                completed += 1
                                break
                        else:
                            return {"advanced": completed, "stopped": "waiting", "state": state}
                    return {"advanced": completed, "state": state}

                async def close_information():
                    # A bounded test-client convenience, not a new MCP action.
                    # Read and journal each visible informational popup before
                    # using its exact offered Close/Continue action. Decisions,
                    # generic dialogs and unknown popups always stop the loop.
                    allowed = {"boost", "research_completed", "natural_wonder",
                               "wonder_built", "project_built", "natural_disaster",
                               "historic_moments", "great_work", "great_works_overview",
                               "world_rankings"}
                    closed = []
                    for _ in range(12):
                        state = await call("get_pending_decisions", {})
                        popups = state.get("ui", {}).get("popups", [])
                        if not state.get("ok") or len(popups) != 1:
                            return {"closed": closed, "state": state}
                        popup = popups[0]
                        if popup.get("id") not in allowed:
                            return {"closed": closed, "state": state}
                        buttons = [b for b in popup.get("buttons", [])
                                   if b.get("id") == 1 and b.get("enabled") is True
                                   and b.get("supported") is True and b.get("action")]
                        if len(buttons) != 1:
                            return {"closed": closed, "state": state}
                        outcome = await call("act", {"action": buttons[0]["action"]})
                        if not outcome.get("accepted"):
                            return {"closed": closed, "outcome": outcome}
                        closed.append({"id": popup["id"], "content": popup.get("content", []),
                                       "submitted": True})
                        await asyncio.sleep(0.2)
                    return {"closed": closed, "stopped": "limit", "state": await call("get_pending_decisions", {})}

                while True:
                    line = await asyncio.to_thread(sys.stdin.readline)
                    if not line or line.strip() == "quit":
                        break
                    if not line.strip():
                        continue
                    try:
                        request = json.loads(line)
                        if request.get("close_information") is True:
                            public = await close_information()
                        elif "advance" in request:
                            public = await advance(request["advance"])
                        else:
                            public = await call(request["tool"], request.get("args", {}))
                        if request.get("brief") and "items" in public:
                            public = {**public, "items": [{k: v for k, v in item.items() if k != "description"} for item in public["items"]]}
                        # Console-only filtering; the journal always retains the
                        # complete public response and the next token is unchanged.
                        prefixes = request.get("item_prefixes")
                        if prefixes is not None and "items" in public:
                            if type(prefixes) is not list or any(type(p) is not str for p in prefixes):
                                raise ValueError("item_prefixes must contain strings")
                            public = {**public, "items": [item for item in public["items"]
                                if item.get("id", "").startswith(tuple(prefixes))]}
                        unit_ids = request.get("unit_ids")
                        if unit_ids is not None and "units" in public:
                            public = {**public, "units": [unit for unit in public["units"] if unit["id"] in unit_ids]}
                        fields = request.get("fields")
                        if fields is not None:
                            public = {k: v for k, v in public.items() if k in fields}
                        if request.get("compact") is True:
                            # Display only: the full public response was already
                            # journaled above. Fixed columns avoid verbose PTY rows.
                            for collection, columns in (
                                ("units", ("id", "type", "x", "y", "moves", "damage", "build_charges")),
                                ("cities", ("id", "name", "population", "production", "production_turns")),
                            ):
                                if collection in public:
                                    public = {**public, collection + "_columns": columns,
                                        collection: [[row.get(key) for key in columns]
                                                     for row in public[collection]]}
                        print(json.dumps(public, ensure_ascii=False), flush=True)
                    except Exception as error:
                        print(json.dumps({"client_error": type(error).__name__,
                                          "message": str(error)[:160]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
    asyncio.run(main())
