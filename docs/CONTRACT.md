# Internal implementation contract

This is an independent MCP implementation, not a wrapper exposing the upstream server.
Python >=3.10. Normal tools enforce player-information boundaries using authored templates:
game logic uses InGame; visible popup inspection/response uses fixed audited UI contexts.
The explicitly requested `run_lua` fallback is a separate trusted-caller
capability, only for an actual in-game problem that existing normal tools cannot resolve.
The user explicitly accepted the inability to automatically filter arbitrary Lua on
2026-10-27. Arbitrary scripts cannot inherit the normal tools' automatic fairness
projection. The 0.4.2 integration passed offline validation; live validation is pending. See FALLBACK_LUA.md.

## Transport
`transport.py`: `FireTunerTransport(host='127.0.0.1', port=4318)` with
`async execute(script: str, context: str = 'InGame') -> str` and `async close()`.
Only loopback hosts. Serialized, bounded reads/timeouts; never retry a submitted action.
Normal-tool exceptions must be opaque at the MCP boundary. The fallback uses a
separate transport path and may return bounded script diagnostics; it does not expand
the normal execute context allowlist or automatically retry either kind of request.
Protocol adaptation can use MIT upstream with attribution and vendored license.

## Explicit fallback execution

The authorization is the user's explicit informed approval, not the caller's description
of a problem. The server validates parameter and identity gates; it does not certify that
the declared normal-tool attempts occurred or that arbitrary code obeys the usage policy.

`run_lua(code, reason, attempted_tools, context="InGame")` is a last-resort game tool,
not the default gameplay path. Require a nonempty reason (at most 2000 characters), and
at least one unique gameplay-tool name in the caller-supplied attempted_tools list.
Only get_game_status, get_player_state, get_diplomacy, observe_area, list_options,
inspect_game, get_pending_decisions, wait_for_change and act qualify. These declarations do
not verify prior calls, script fairness, or the absence of side effects.

Before execution, make a fresh minimal status query establishing an ongoing single-player
game with an alive local human and matching local observer. Reject unsupported or unknown
identity/mode status. Bind execution to that connection generation. Do not require a
normal action token, successful popup discovery, or a ready ordinary active turn: the
fallback must remain usable for a real UI blocker that prevents normal token issuance.
This does not authorize bypassing normal game-stage or operation eligibility rules.
Recheck identity, player, observer, turn, ongoing status and matching shared session
inside the target-context wrapper before running user code. Missing target capabilities
or a changed same-connection session must not admit the script.

Accept the default InGame, ingame/gamecore aliases, and contexts actually discovered
by FireTuner, without adding them to the normal authored-template context allowlist.
Discovery alone does not establish eligibility: contexts must also supply the identity
APIs and shared session required above. GameCore may therefore be unavailable; it is
not a read-only or player-view sandbox. Compile the code from a quoted Lua
string using native loadstring, with text-mode load as a compatibility fallback. Supply
a local print collector; never replace global print. Preserve ordinary context globals
and explicitly document that this is not a sandbox. Do not claim a string blacklist can
prove arbitrary code safe or fair.

Collect bounded explicit prints and the supported first scalar return only, without
automatically traversing returned tables/userdata or invoking their tostring metamethod.
Limit UTF-8 source to 32 KiB. A print accepts at most 64 arguments and 4096 bytes after
joining; omit an oversized print rather than cutting UTF-8. Retain at most 128 output
lines and 64 KiB of line text, with truncation signaled. Bound string returns and
compile/runtime diagnostics to 4096 bytes. Keep output isolated to the current request/context.

Execute at most once, with no automatic retry on error, timeout, disconnect or cancellation.
A runtime error may follow partial side effects; completed Lua is not proof that an
asynchronous game request completed. Invalidate normal tokens, observation baseline,
session history and preview authorization after fallback attempts, including failures
and cancellations; require fresh observations
before normal actions. A client timeout cannot guarantee stopping Lua inside the engine.
Only short bounded snippets are appropriate; no unbounded loops or busy waiting.

For validated requests, returning responses include a receipt with a random request ID,
normalized context, code SHA-256, reason, declared attempts, attempts_verified=false and
retention=response_only. Do not write code or receipts to disk or add a history-query tool.
Invalid inputs do not require a receipt; cancellation may prevent a response. An execution
receipt is not proof of game-operation completion or of policy compliance.

The caller must still respect normal player knowledge and legal operations. No hidden
world data, cheat setters, forced turn completion, OS commands, files/logs/saves, networking,
configuration changes or process termination. These are usage constraints, not technical
proof that an arbitrary script is harmless. Strongly isolated fair-play deployments must
remove fallback execution from the player's tool surface and block alternate debug access.

## Lua common / observation builder (queries.py owns common)
`lua_common.py`: `wrap(body: str, nonce: str) -> str`. Wrap body in pcall, emit exactly
one JSON line `CIV6FAIR_JSON:` plus result and `---END---`. Generic errors only.
Locals `me`, `player`, `vis`, `turn`, `session` are validated and available to body.
Session is an in-memory InGame global initialized with nonce, local player must be >=0,
alive, human; multiplayer/hotseat unsupported and must fail closed when verifiable.
Use JSON serializer implemented in Lua, with correct escapes; `out` is result table.

`queries.py`: `build_player_query(nonce)`, `build_map_query(nonce,x,y,radius)`.
Envelope: `{ok:true, session:<opaque>, player_id:int, turn:int, active_turn:bool,
  player:{...}, units:[...], cities:[...]}` OR same envelope with `tiles:[...]`.
Each own unit/city must include `owner_id`, `id`, `x`, `y`.
Own-city production estimates are optional: a valid finite estimate is a nonnegative
integer `production_turns`. The stock queue's `GetTurnsLeft() == -1` instead produces
`production_indefinite: true` with no `production_turns` (currently will not complete,
shown as `999+` by the normal UI). Missing/failed/unknown estimates omit both fields;
an empty queue does not query its estimate. Python rejects negative turns and the
combination of `production_indefinite: true` with `production_turns`. This sentinel
must not invalidate the whole otherwise valid own-player observation.
Tile: `{x,y,revealed:bool,visible:bool}`. ONLY if visible add `terrain`, `feature`,
`hills`, `river`, `water`, `owner_id`, `resource` (only when explicit player-specific
resource visibility proves it is unlocked). Never read live details in fog, even revealed.
The optional `district` field is this visible tile's `DISTRICT_*` type, or `NONE`
only after the tile getter confirms no district. Missing/invalid getters omit it;
do not enumerate another tile or the owning city's district collection for it.
No tile yields (can leak hidden strategic resources). `visible_units.py` supplies
UNIT_HELPERS / visible_units_at(plot,index), using vis:IsUnitVisible BEFORE any unit
getter. Only detected foreign units return, with detected=true internal attestation.
`visible_cities.py` supplies CITY_HELPERS / visible_city_at(plot,index), requiring a
currently visible exact city center; P02 user-approved details only, no remote coordinates.
Both helpers repeat visibility checks; unavailable capabilities omit the field.
Static GameInfo definitions are allowed, all player-state reads limited to Players[me].
Exception: diplomacy.py uses GetWasEverAliveMajors to count initial major participants,
then gets only each ID needed for local HasMet; no unknown player identity or details.
Only known civilization public UI stats, visible agendas and allowlisted aggregate
victory data return. Public_diplomacy applies a second allowlist/proof projection.
No world dump, random seeds, map-generation metadata or raw engine errors.
Audited trade/spy chooser exceptions may internally enumerate cities solely to
reproduce stock menu membership. Only approved menu fields return, using a separate
menu proof; rejected candidates' names, coordinates, counts and attributes do not.
See MENU_PERMISSIONS.md for the native operation/path and diplomacy/reveal gates.
City-state menu membership additionally requires an alive, met influence receiver;
exclude majors, barbarians and Free Cities. War/peace choices are mutually exclusive
under the current IsAtWarWith result and recheck the matching normal eligibility API.

## Action builder (actions.py)
`inspect_game("own_resources", {})` returns only own unlocked strategic-resource
amounts. Gathering Storm additionally supplies stockpile, income and demand
fields from stock TopPanel APIs. Unlock is checked before identity/name/amount
reads. No map or foreign-source enumeration. Missing optional values are unknown;
net_per_turn is income minus demand before stockpile caps or shortage handling.

`inspect_game("own_luxuries", {})` returns positive own luxury holdings using
the stock resource overview's `GetResourceAmount(row.Index)`. Include non-map
Great Merchant goods; do not filter by map frequency or tradeability. These are
held copies, not a trade offer limit. No foreign player, source, map or strategic
resource reads. Nonpositive balances are omitted as in the normal menu; unknown
core quantities fail the whole inventory closed instead of returning partial
holdings. Optional localization falls back to the public resource identifier.

`inspect_game("city_status", {"city_id": own_id})` reads only an owned city's
stock growth/overview aggregates: population, food, housing, amenities, growth
and starvation estimates, happiness and aggregate loyalty. Growth multipliers
use 1 for 100%; growth_threshold is the total food threshold. `*_active=false`
means the engine returned -1 for that estimate; no numeric turns field follows.
Missing optional APIs or invalid values omit individual fields, never invent
zero or false. No foreign loyalty-pressure sources or foreign city lookup.
For explicit GS rules, optional `power_*` fields read this own city's power
component. Use the stock panel's required/free/temporary/fully-powered status,
including the active-project override of usable power. Branch and sum on raw
values, then round displayed power to one decimal. Do not infer missing booleans
or source quantities, and do not enumerate power-source cities or map coverage.

`ALLOWED_ACTIONS` constant and `build_action_query(nonce, action:dict, expected_session:str,
 expected_player:int, expected_turn:int) -> str` using common.wrap.
`build_options_query(nonce, kind:str, entity_id:int|None) -> str` for research/civic/
production options that are available to current player (bounded; type identifiers).
Research/civic options retain `id` and `kind` and may add `name`, `description`,
`boost_description` (strings), `cost`, `progress` (nonnegative finite numbers),
`turns` (nonnegative integer), and `boosted` (boolean). Read these only after the
own-player CanResearch/CanProgress gate. Optional getter failures omit individual
fields. Description is optional database text, not a synthesized complete unlock
list; missing does not mean zero, false, or no effect. Production options do not
inherit these additional fields. Python applies the same field/type allowlist.
Normal actions accept only exact validated enum names/ints, no arbitrary Lua or arbitrary engine operation.
Actions check session/player/turn+active human turn in same Lua block as request;
then entity ownership BEFORE reading fields; x/y target must be visible except normal
move to an adjacent unknown tile may be allowed without inspecting contents/path.
The separate `queue_move(unit_id,x,y)` action accepts a revealed long-range goal
for an owned movable land/naval unit with movement remaining. It reads only
map bounds and the target's public revelation flag, never target contents,
pathfinding or target legality. It rejects the current plot, uses the fixed
non-ATTACK MOVE_TO request once, and hides native return values/errors. Submitted
does not guarantee acceptance into the queue or arrival; normal engine behavior
may replace an earlier movement plan. No automatic cancellation or replay occurs.
Trade and spy actions instead recheck their exact stock chooser eligibility in
the action call. Remote spy mission previews never authorize execution; the spy
must currently occupy the mission city and the target must be offered there.
Only authored normal UI request paths and stock UI callbacks. UI-local bookkeeping
may use the same setters as the stock UI (for example the considered-government flag).
No game-state cheat setters, force-end-turn, FinishMoves or global/autoplay actions.
The `can_end_turn` decision uses the shared normal end-turn guards: active/ready
turn, no message processing or modal blocker, UI.CanEndTurn, required request APIs,
and no end-turn-blocking notification. Missing readiness capabilities produce false.
It describes the observation instant; end_turn rechecks before submitting.
For Gathering Storm, both policy discovery and set_policies use the stock
IsPolicyBanned=false / CanPolicyBeSlotted=true / IsPolicyObsolete=false predicate.
Base/Rise and Fall use their stock unlocked/non-obsolete predicate. Unknown rulesets
or missing predicate APIs fail closed; do not guess dark-age or era eligibility.
Combat requires visible/detected targets; no arbitrary purchase/target foreign IDs.
Only return accepted/rejected, no internal failure reasons; accepted != completed.

## Python policy/service (root)
For normal tools, the server strictly projects allowlisted fields AGAIN independent of Lua guards.
Visible+revealed required for tile content. Own entity `owner_id==bound player`.
No cross-game/fog memory (avoids stale-state contamination).
Observation response issues opaque action token bound to session/player/turn/connection.
Token consumed before action dispatch, invalidated on errors/actions/reconnection.
Normal tools expose no raw transport/debug/error output. stdin/stdout MCP only. Document
the separate fallback trust boundary: arbitrary scripts bypass fixed-field projection,
as can another client with unrestricted OS or FireTuner access.

Normal MCP tools: get_rules, query_manual, get_game_status, get_player_state, get_diplomacy, observe_area,
list_options, inspect_game, get_pending_decisions, wait_for_change, get_session_history, act.
Separate fallback tool: run_lua (0.4.2, offline validated; live validation pending).
User-confirmed rules are recorded in PLAYER_CONFIRMATIONS.md (2026-10-22 and 2026-10-27).

## Gameplay extensions and UI

extensions/base.py defines exact bounded schemas, authored ActionSpec/QuerySpec and safe
Lua literals. Registry collisions and unknown permission modes are rejected. Every
inspection record passes a second allowlist in inspection_policy.py before returning.
Normal actions require the active turn. Diplomacy/congress modes require an actual
local conversation/voting segment. Visible-popup actions can resolve event locks
outside the normal active turn, but cannot submit arbitrary gameplay actions.

Every real-transport observation automatically discovers visible fixed popup contexts,
reads their displayed text/buttons, and returns ui. Hidden subtrees/queued events are
never read. Context replies must match session/player/turn and connection generation.
Popup responses recheck content, visibility, enabled state, exact callback and control
identity; invoke stock callbacks. A resolved artifact/spy-escape dialog can be hidden
only after rechecking that the own-player pending decision is absent, matching its
stock UI cleanup. get_pending_decisions
combines this with own notifications/blockers. A failed world getter falls back to a
minimal UI read so that a blocking prompt remains actionable. Terminal status queries
may identify own defeat without entering any map/entity/diplomacy body or issuing tokens.

Notification queries establish the local owner, then require `IsDismissed() == false`
before reading text or offering actions: `FindType` may retain a dismissed core object.
A missing/failed/unknown dismissal check omits only that notification. Activate/dismiss
actions recheck the state; dismissal additionally requires `CanUserDismiss()` and no
end-turn blocker, then uses the stock `NotificationManager.Dismiss(playerID, id)` call.

Ephemeral shared ExposedMembers.Civ6FairState contains only authorization and bounded
own observed conversation/UI bookkeeping. Reset events invalidate it. No save/fog cache.
