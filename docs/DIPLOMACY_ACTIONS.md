# 外交、议会与文化操作（0.3）

本模块使用本机 Steam 游戏原始 UI 的正常请求接口；没有读取 AI 计划、强制签订协议或自动通过投票。静态 Lua 模拟验证与实机验证是不同阶段；下述签名已对照安装文件，但还需实际存档确认异步流程。

## 操作与发现入口

| 查询分类 | 提供的操作 |
| --- | --- |
| `diplomacy_actions(target_player)` | 正常宣战及各类宣战理由、和平谈判、使团、大使馆、友谊、谴责、开放边境、停止传教/间谍/考古/邻近定居的交涉。 |
| `diplomacy_sessions()` | 查找本地玩家与已遇见对手的开放会话，返回捕获到的当前公开对话和实际选项；`diplomacy_respond`、`diplomacy_close`。 |
| `city_states()` | 已遇城邦的稳定条目、使者投入与匿名竞争、宗主、类型与奖励、本方任务、战争状态和操作资格；派遣使者、征召、宣战、议和。 |
| `deal_options(target_player, side, kind)` | 交易面板中的金币、每回合金币、外交支持、资源、协议、城市、巨作、俘虏。`side` 为 give/receive。 |
| `deal_state(target_player)` | 当前自己的往来谈判条款与精确报价的接受/拒绝动作。 |
| `deal_negotiation(target_player)` | 当前原版“公平报价”按钮的 `deal_equalize` 请求，绑定会话与安全草案签名；不会接受交易。 |
| `war_deal_options(target_player, side, agreement)` | 联合作战与第三方宣战条款；只返回已遇见的战争目标。 |
| `great_works(city_id)` | 自己城市的巨作槽位、作品及可移动状态；`move_great_work` 按源/目标城市、建筑、槽位移动或互换。 |
| `archaeology()` | 考古学家的待选文物来源；`choose_artifact` 选择 1 或 2。 |
| `world_congress()` | 当前决议、A/B 效果、零起始的目标序号、讨论序号、投票费用；议会外的可提案紧急事件。 |
| `emergencies()` | 本地玩家收到的紧急事件加入、拒绝或信息确认；`emergency_respond`。 |

精确参数均由 `get_rules` 返回。查询产生的 `action` 是已按服务器结构校验的候选动作；提交后必须再次观察。复杂议会投票用 `congress_ballot` 一次提交完整选择，不能把某一个决议的选择视为完整选票。

## 交涉与报价

1. 先检查本地玩家 `HasMet`，之后才读取对手对象、身份或会话。会话 ID 还必须通过 `FindOpenSessionID`、`IsSessionIDOpen` 与 `GetSessionInfo` 的本地双方校验。
2. 首次调用任意 InGame 查询会安装玩家对话事件监听。只保存实际发给本地玩家的 `StatementType`、`StatementSubType`、公开情绪、发起者与本地生成的递增版本；不保存完整事件表、AI 原因 ID 或内部修正。
3. 当前对话的候选项按原游戏 `DiplomacyStatementSupport` 的数据库回退次序取得，再检查 `IsDiplomaticActionValid`。动作绑定 `STATEMENT_*` 版本，只允许当前实际存在的选项；提交后消费该版本。
4. 如果桥接器是在一个对话已经打开之后才首次连接，不能凭空补造错过的事件。查询返回 `prompt_unavailable`，不默认给出“接受/拒绝/忽略”三个选项。可通过 UI 弹窗接口查看当前显示文本；未捕获的会话需要由经过验证的 UI 回调处理，或关闭后重新发起。正常启动后监听能覆盖后续对话。
5. 和平谈判采用 UI 的方式建立锁定 `MAKE_PEACE` 条款，验证双方和平依赖，再发起 `MAKE_DEAL`。
6. 草案编辑仅允许开放的本地谈判会话；不能编辑对方的礼物/索取要求。`deal_send` 对收到的报价发送 `ADJUSTED`，对新报价发送 `PROPOSED`。原版实际显示的“公平报价”按钮可通过独立 `deal_negotiation`／`deal_equalize` 请求使用；不读取 AI 私有估值，不自动接受或重试，详见[公平报价接口](DEAL_EQUALIZE.md)。
7. 接受报价必须携带本次观察返回的 `DEAL_*` 指纹。指纹涵盖条款、数额、期限、双方、协议以及战争类型；若报价改变则拒绝。对未解锁资源或未遇见第三方的条款，不返回接受能力或基于该条款生成的指纹。
8. 资源在交易面板也检查当前玩家 `IsResourceVisible`，遵守用户 P04；不能借贸易读取尚未解锁的战略资源。交易城市/巨作/俘虏只用正常 `GetPossibleDealItems` 给玩家显示的条目，不展开它们的雾中坐标或私人状态。

`deal_state` 的条款 `name` 现在包含给出／收到方向、公开名称、数量和期限；`description` 保留原有类别、`value`、`amount`、`turns`、`subtype` 等原始值，战争条款还保留原战争类型。名称只在 `safe_deal_item` 过滤通过后读取：协议优先采用原版 `GetSubTypeNameID()`，其次使用 `GameInfo.DiplomaticActions[subtype].Name`，都不可用时保留已允许的符号类型；资源再次检查解锁资格后读取规则名称。联盟和科研协议可附带对应的公开规则名称，战争目标仅使用已遇见文明的名称。金币与每回合金币分别标注，外交支持也有本地化类别名。

巨作名称来自当前安全交易项的 `GetValueTypeNameID()`，与 GS `DiplomacyDealView.lua:2505–2510` 的标题一致；接口缺失或无有效标题时仅显示通用 `GREATWORK`。`GetSubType()` 对应原版图标定义，不能用其静态名称替代当前报价实例的标题：第 114、117 回合两份不同实例的报价均返回 subtype 0，旧实现因此错误地显示同一作品名。修复不读取巨作提示文本、创作者或外国城市。城市和俘虏暂仅显示类别，不展开外国城市、单位、坐标、库存或综合提示文本。显示名称不参与报价指纹，也不改变接受／拒绝的授权条件。第 41 回合收到的真实报价暴露了旧版协议只有数值哈希、难以理解的问题；该报价已正常拒绝。

`deal_state` 另返回固定 `incoming_response_status`：`ready` 表示完整报价通过现有响应条件；`invalid_offer` 表示原版有效性检查未通过或没有条款；`session_unavailable`、`signature_unavailable`、`no_incoming_offer` 分别表示会话、条款绑定或收到的报价不可用。若存在按当前玩家信息权限过滤的条款，优先返回 `filtered_terms`，明确所见内容不完整，但不透露过滤条款的类别、数量、身份、数值或指纹，也不提供该报价的接受／拒绝动作。此时仍可使用当前原版弹窗实际提供的正常拒绝按钮。不能从可见的部分报价推断全部条款；接受提交时的完整性、当前会话、精确签名和原版有效性门槛保持不变。和平协议的 8 回合期限本身没有被额外禁止。

第 118 回合暴露的草案角色问题已在工作区修正，尚待重新加载实测：`INCOMING` 工作副本存在，不再等于收到可接受的报价。独立 v2 观察器只捕获原版 `ShowMakeDeal/ShowMakeDemand`、`DealUpdated` 和当前已观察交易的 `DiplomacyIncomingDeal`，绑定整局会话、外交会话 ID、本方、对方和发起者；不读取对话文字或 AI 评估原因。旧版本按对手缓存的事件不作为证据，热加载也不复用旧监听闭包。普通问候／谴责会话即使残留交易副本也不能回应。

新增状态 `outgoing_draft`（本方初始草案）、`response_unavailable`（当前并非可响应报价阶段）、`pending`（等待原版处理）、`conversation_closed`（已退出／回应）和 `phase_unavailable`（错过当前面板事件）。最后一种情况可正常关闭后重开面板；不凭发起者补造报价。仅原版 `ACCEPTED/PROPOSED/ADJUSTED` 阶段允许精确条款响应，接受时复制报价后再次核对会话阶段和指纹；关闭、会话结束及响应提交都会使旧资格失效。普通 AI 拒绝按原版发起者使用 `NEGATIVE` 或关闭会话，本方不可接受条目的特殊分支使用原版 `REJECTED_PERMANENT`。`deal_send` 只提出／调整草案，绝不把发送隐式转换成接受。原版创建和平草案并不设置期限，因此两个锁定和平项的 `turns=0` 不是构造失败的证据。

第 **43 回合**实机再次读取残留的 working deal 条款，已显示中文“给出外交支持 8”“收到开放边界，期限 20 回合”“收到金币 23”，并保留各自原始数值。此次没有接受／拒绝按钮。证据为[续局日志](../artifacts/continuation-2026-10-27/journal.jsonl) **L457**：这验证了真实条款的名称解析，不表示有新的待处理报价，也不表示交易成立。

名称回归覆盖负数协议哈希、原版标题与规则名称回退、数量和期限保留、金币／每回合金币、解锁资源名称、联盟／科研参数、未知战争目标及外国对象 getter 陷阱。新增 17 项后，本模块共 **112 项测试通过**；交易名称修复阶段的项目全量回归为 **1143 项通过，另有 19 项子测试通过，0 失败**。

交易草案允许编辑后暂时不完整（例如尚未加入对价）；发送时必须通过 `deal:IsValid()`。城市条款使用 UI 的五参 `AddItemOfType` 生成关联条款；巨作附带公开的作品类型；联盟与科研协议取对应子菜单实际提供的值。战争交易只能选择实际提供且本地已遇见的第三方，最终发送/接受可能正常宣战。

## 城邦身份与战争状态

`city_states` 查询和 `city_state_envoy`、`city_state_levy`、`city_state_war`、`city_state_peace` 四种动作共用城邦身份检查。先通过本地 `HasMet`，再确认对象存活、不是主要文明或蛮族；如果当前规则集提供 `IsFreeCities`，其结果必须为 false。最后必须通过目标的 `GetInfluence():CanReceiveInfluence()`，这是原版城邦面板区分可接收影响力对象的条件。不能假设 `GetAliveMinors()` 已经排除了自由城市，也不以固定玩家 ID 判断身份。检查失败时不会读取其名称或生成操作。

宣战与议和复用原版按钮的二选一逻辑：`IsAtWarWith(target)==false` 且 `CanDeclareWarOn(target)==true` 才提供宣战；`IsAtWarWith(target)==true` 且 `CanMakePeaceWith(target)==true` 才提供议和。缺少战争状态或对应许可能力时不提供该操作。两种 `Can...` 都返回 true，不能越过当前战争状态检查。执行时重新验证，防止使用战争状态改变前的旧选项。

宣战、议和及征召军队还要求原版界面的 `CAPABILITY_MILITARY`。使者操作独立检查可派遣使者、剩余数量及目标可接收条件，不受军事能力开关影响。请求仍走正常 `RequestPlayerOperation`，不会强制成功。

**2026-10-27 同局复查：** 第 37 回合旧查询同时提供四座城邦的宣战、议和，并错误列出自由城市玩家 62 的议和。修复后第 38 回合只提供已遇见的撒马尔罕（4）、卡霍基亚（6）、那烂陀（8）、奥克兰（12）的宣战候选，没有议和或自由城市条目；剩余使者为 0。证据为[续局日志](../artifacts/continuation-2026-10-27/journal.jsonl) L218 与 L274。本次只核对查询结果，没有实际向城邦宣战或议和，因此不能将这两种请求记为实机执行通过。

对应 Lua 回归覆盖两个许可 API 同时返回 true、战争状态切换后旧动作拒绝、自由城市 62、主要文明／蛮族／死亡对象、未知对象 getter 陷阱、缺少影响力资格能力及军事能力开关。城邦修复当时该模块 95 项通过、项目完整回归 **1093 项通过，另有 19 项子测试通过，0 失败**；后续交易名称等改动后的最终回归数字见上文。测试数字来自开发验证记录，不能代替实际存档覆盖。

### 城邦详情与使者决策

上述信息缺口现已补入 `city_states()`。每座通过共同身份检查的城邦都保留 `city_state_<id>` 基础条目，不再因为当前没有可执行动作而消失。详情沿用检查通过的城邦作为 `met` 授权对象；输出边界只保留已有的 `id/name/value/description/action` 字段，不将授权元数据交给调用者。

下表中的字段后缀均接在 `city_state_<id>:` 后面，征召价格保留已有 ID `levy_cost_<id>`。

| 字段 | 含义与来源 |
| --- | --- |
| `envoys`、`most_envoys` | 本方已投入使者数、面板显示的最多使者数；来自目标城邦影响力组件。自己的剩余使者仍在全局 `envoys` 条目。 |
| `suzerain`、`is_suzerain` | `none/self/known/unknown` 宗主状态，以及本方是否为宗主；只有已遇见的非本方宗主才另有 `suzerain_player`。 |
| `suzerain_target_envoys` | 原版面板显示的宗主使者总数目标，不能当作还需额外派遣的数量；同额竞争不会新产生宗主。 |
| `influence:self`、`influence:<known_id>`、`influence_unknown:<ordinal>` | 原版“影响力”列表中各方的正数使者贡献。已遇文明有公开名称；未遇见者只保留匿名数量，并按数量排序。匿名序号不是玩家 ID，不能跨查询据此识别文明；零贡献者不产生条目。 |
| `type`、`bonus:1/3/6` | 城邦类型、各档使者门槛和当前本地化奖励正文。 |
| `unique_bonus:<trait>`、`suzerain_rules` | 已遇城邦对应的独有宗主奖励及通用宗主外交规则；风云变幻接口可用时另有 `unique_bonus_disabled`。 |
| `quest:<type>`、`quest_count` | 本方当前任务的菜单名称、目标说明和奖励；只有任务激活检查通过后才读取正文。 |
| `at_war`、`military_available`、`can_send_envoy/can_levy/can_declare_war/can_make_peace` | 公开战争状态、军事能力和与候选操作一致的当前资格。明确的“已经交战／尚未交战”原因会返回，其他禁用情况只标注正常按钮不可用，不推测隐藏原因。 |
| `levy_duration`、`levy_active`、`levy_cost_<id>` | 正常征召按钮的期限、军队是否已被征召及价格。价格由本方影响力接口取得，期限由目标城邦影响力接口取得；军事能力关闭时不读这些字段。 |
| `details_status` | `complete/partial`。部分详情 API 不可用时保留基础条目和仍可用的操作，省略未知字段；省略不等于 0 或 false。 |

本机原版 `CityStates.lua` 自己将使者奖励门槛写为 **1／3／6**、宗主最低使者数写为 **3**，并注明尚缺引擎门槛 getter。本实现复刻这组原版菜单显示规则；所有奖励正文仍通过当前规则集的 `Locale.Lookup` 取得，没有自写奖励数值。不能将这些门槛声称为已验证适用于额外模组的通用规则。

隐私边界保持原要求：在 `HasMet` 和城邦资格通过前不读取其身份或详情；未知宗主与竞争者不读取 `Players`／`PlayerConfigurations`，不输出其 ID、文明名或存活清单。独有奖励只读取该城邦匹配的 `LeaderTraits → Traits.Description`，不调用原版综合宗主提示中附带的外国资源库存扫描，避免泄露尚未解锁资源。也不查询外国城市、单位、地图位置或外交 AI 内部数值。

任务严格使用 `HasActiveQuestFromPlayer(me, city_state, quest_index)` 和相同本方参数的名称／说明／奖励 getter。覆盖安装文件中的八种普通任务：改宗首都、建立商路、清除蛮族营地、训练单位、建造区域、触发尤里卡、触发鼓舞、招募伟人；不读取其他玩家任务，不另查目标位置。遇到额外任务类型或任务接口不可用时标记 `partial`，不会把未读取任务误报为 0。

本次新增 **41 项 Lua 回归**，连同外交模块和输出过滤测试共 **254 项通过**。覆盖无动作时稳定条目、未知身份 getter 陷阱、匿名贡献排序、宗主与平局、六种城邦和三档奖励、任务参数与激活门槛、缺 API、征召接口所属对象，以及正常战争资格与动作一致性。0.3.4 第 45 回合已实机读取 4 个已知城邦完整详情：撒马尔罕双方各 3 使者、无宗主，目标总数 4；卡霍基亚大商人任务、那烂陀军营任务、奥克兰商路任务均有正文。第 47 回合已再次读取竞争变化并正常派遣使者。未触发的征召及未知宗主分支仍以模拟测试为限。

## 议会与紧急事件

- 只在 `TURNSEG_WORLDCONGRESS_1/2`、本地存活人类主要文明、游戏未暂停时开放议会投票权限。其他回合操作不能借该权限执行。
- `GetResolutions(me)`、`GetProposals(me)`、`GetVotesandFavorCost(me)` 是本地玩家的选项来源。可用的紧急事件提案从 `GetEmergencies(me)` 读取；不会混用投票中的提案和议会外可发起提案。
- 未遇见文明仅显示“Unknown civilization”和本次菜单的选择序号，不返回其玩家 ID、名称、存活状态或统计。文物来源选择也遵守这一限制，即使原 UI 某些文本可能直接显示来源文明。
- 完整选票先检查所有决议、目标序号、讨论、方向限制、`MaxVotes` 与总外交支持费用；任何一项无效，均不提交前面的局部选择。验证后才发送标准投票、`WORLD_CONGRESS_SUBMIT_TURN` 及该议会阶段的正常结束请求。
- `congress_acknowledge` 仅处理 `ENDTURN_BLOCKING_WORLD_CONGRESS_LOOK`，发送正常的 `WORLD_CONGRESS_LOOKED_AT_AVAILABLE`，不能跳过议会投票。
- `emergencies` 与 `emergency_respond` 只读取 `GetEmergencyInfoTable(me)`，与原版活动跟踪器和弹窗使用相同的本方菜单来源。GS `WorldCrisisSupport.lua:33–50` 明确将 `inputRequired` 定义为 `not HasBegun`；仅原生布尔 false 提供加入／拒绝，true 提供信息确认，缺值或其他类型不产生动作。不会另从参与者或分数推测本方是否受邀。
- 活动名称来自原版 `GameInfo.EmergencyAlliances` 的静态规则，已替换第 121 回合首次援助活动暴露的错误 `GameInfo.Emergencies` 表访问。`emergency_<序号>` 的值为 `decision_required/in_progress/completed/unknown`；可用的非负整数 `TurnsLeft` 另以 `:turns_left` 返回，完成标记不暴露负数回合数。缺少规则或合法目标参数时不生成条目。此修复为工作区增量，第 126 回合已完成正常查询实测。
- 活动动作仅返回当前菜单的零起始序号与 `join/reject/acknowledge`，不含真实目标 ID。执行时重新读取本方菜单，将其目标 ID（无目标竞赛可为 -1）仅用于原版操作参数；不查询该文明身份。未读取 `MemberIDs`、`ScoresTables`、目标城市名称／位置、他人投票或排名，普通地图及未遇见文明规则不变。
- 公开序号由桥接器按合法菜单条目的遍历顺序独立从 0 计数，查询和执行共用此遍历；不把原生迭代键减 1，也不使用 `emergencies[序号+1]`。这与原版只使用迭代所得条目、忽略键的用法一致。第 122 回合探针的 `public_action_integer_encoding=false` 仅证明不符合非负整数文本，负整数或其他表示均可能触发，不能单凭它断言实机返回了小数。第 124 回合完整分段探针定位到 `collect_failed`、尚无条目；独立序号修正已覆盖 0 起始、不连续、浮点键的 Lua→JSON→Python 投影及同条目动作定位。

**第 126 回合实机查询验收：** 普通 `inspect_game("emergencies", {})` 返回 `supported=true`，读到“世界博览会”进行中、剩余 **4 回合**，以及“请求援助”进行中、剩余 **14 回合**；两项确认候选分别使用公开序号 **0、1**。证据为[公开日志](../artifacts/continuous-035-2026-10-27/journal.jsonl) **L3667**，无需额外诊断。此次只验证查询、状态、期限与候选动作的序列化，**未执行 acknowledge/join/reject**，不能据此声称这三类动作已完成实机验收。该批离线完整回归为 **2752 项通过、19 项子测试通过、0 失败**，耗时 18.14 秒，见[合批验证记录](../artifacts/batch-validation-t126-2026-10-27.json)；测试通过与实机动作后效分开记录。

## 巨作与考古

巨作移动只在两个自有城市之间进行；校验实际源作品、目的槽位范围和 `GreatWork_ValidSubTypes` 的双向兼容性。艺术品遵守 `GREATWORK_ART_LOCK_TIME`；文物只能在已满的博物馆之间互换。没有忽略冷却或瞬间复制作品的入口。

考古选择绑定自己当前的 `GetNextExtractingArchaeologist()`；不能向任意玩家提交一个来源 ID。AI 选择的是面板上的第 1/2 项，真实来源参数只在可信服务内用于正常请求。

## 本机源码依据

`city_state_defer_envoys` 是无目标的本方操作；`city_states` 在有可派使者且尚未确认考虑派遣时提供它。它只调用原版 `CityStates.Close` 使用的 `SetGivingTokensConsidered(true)`，保留使者、解除提醒，不派遣使者或强行关闭界面。第 57 回合已实机确认提醒消失且使者仍为 1。

根目录：`F:\SteamLibrary\steamapps\common\Sid Meier's Civilization VI`。

| 安装文件 | 使用的证据 |
| --- | --- |
| `Base/Assets/UI/DiplomacyActionView.lua` 407–551、565–620、2745–2828 | 请求会话、和平草案、回应映射、公开对话事件与选项渲染。 |
| `Base/Assets/UI/DiplomacyStatementSupport.lua` 48–175 | 静态对话/选项查询回退及外交合法性门槛。 |
| `Base/Assets/UI/PartialScreens/CityStates.lua` 744–839、1119–1165、1440–1467、1496–1508 | 使者和征召请求；军事能力、按当前战争状态二选一、影响力资格及对应宣战／议和许可。 |
| `Base/Assets/UI/PartialScreens/CityStates.lua` 24–27、128–188、197–228、255–274、1330–1352、1452–1485、1518–1552、1593–1620 | 原版固定显示门槛、类型与奖励、独有宗主描述、本方任务、匿名竞争者、宗主目标和征召期限的对象签名。资源库存拼接部分不采用。 |
| `Base/Assets/Gameplay/Data/Quests.xml` | 八种普通城邦任务的允许列表。 |
| `DLC/Expansion2/UI/Replacements/CityStates_Expansion2.lua` 1；同目录 `CityStates_Expansion1.lua` 9、20、43–44 | 风云变幻城邦面板继承基础列表和战争／和平按钮逻辑。 |
| `DLC/Expansion2/UI/Replacements/CityStates_Expansion2.lua` 14–44 | 当前城邦独有宗主奖励说明及禁用状态。 |
| `DLC/Expansion2/UI/Replacements/DiplomacyDealView.lua` 523–583、1280–1505、1540–1605、1708–2055、2800–2820 | 草案、报价、子菜单、城市和巨作交易的签名，以及收到报价时的 UI 行为。 |
| `DLC/Expansion2/UI/Replacements/DiplomacyDealView.lua` 2290–2310、2380–2395、2495 | 资源规则名称、协议子类型标题与联盟名称，以及静态巨作定义的来源。 |
| `DLC/Expansion2/UI/Replacements/DiplomacyDealView_Expansion2.lua` 20–80、190–275 | 战略资源一次性交付、外交支持交易。 |
| `DLC/Expansion2/UI/Additions/WorldCongressPopup.lua` 20–21、80–85、574–575、838–958、983–1000、1230–1310、1365–1490、1766、2237–2301、2402 | 议会阶段、玩家选项、零起始目标索引、费用、投票/提案/已读请求。 |
| `DLC/Expansion2/UI/Additions/WorldCrisisPopup.lua` 45–68、288–330；`WorldCrisisSupport.lua` 33–53 | 本地紧急事件列表、HasBegun 与加入/拒绝/确认。 |
| `Base/Assets/UI/GreatWorksOverview.lua` 116–209、764–863、902–914 | 自有槽位、冷却、文物互换、相容性和移动参数。 |
| `Base/Assets/UI/Popups/ChooseArtifact.lua` 12–86 | 当前考古学家、文物来源选项和选择请求。 |

模拟测试覆盖未遇见实体 getter 陷阱、潜藏交易资源、报价变更、会话及陈述过期、未提供的回应、议会预算/方向/完整性、未知议会目标、文物匿名来源、巨作冷却与槽位限制。真实弹窗与异步状态推进仍应在运行中的游戏中验证。
