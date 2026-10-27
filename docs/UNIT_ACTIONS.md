# 单位操作扩展

v0.3 的操作来自本机 Steam 安装的原版 UI：`Base/Assets/UI/Panels/UnitPanel.lua`、`WorldInput.lua`、`Civ6Common.lua`、`Choosers/TradeRouteChooser.lua`、`TradeOriginChooser.lua`、`EspionageChooser.lua`、`Popups/EspionageEscape.lua`，以及两个资料片的 `WorldInput` 替换文件和 UnitCommands/UnitOperations 数据。没有开放任意枚举、脚本执行或调试接口。

实机只读验证发现 `UnitOperationTypes` 不包含 `SLEEP`、`SKIP_TURN` 等所有正常操作。因此固定允许列表通过原版 `GameInfo` 数据行的 `Hash` 解析，与 `UnitPanel` 的循环一致；继续要求 `VisibleInUI=true` 和引擎合法性检查，不把缺少常量误判成不支持。`unit_actions` 也返回可执行的基础建城、驻扎选项。已在开局开拓者与勇士上只读验证选项，未执行任何移动、建城或其他动作。

| 接口 | 覆盖内容 |
| --- | --- |
| `unit_neighbors` 查询 | 原生几何接口返回本方单位周围的坐标与 `move` 请求；包含未探索邻格，但不读取其内容，不保证通行、可达或安全。 |
| `special_unit_sites` 查询 | 本方考古／国家公园／伟人／摇滚乐队的原版高亮候选，仅已探索坐标（可含迷雾）和固定用途；不读取地块实时内容或代替当前位置的执行资格检查。[接口与证据](SPECIAL_UNIT_SITES.md)。 |
| `unit_move_preview` 查询 | 对当前可见目标读取原版移动预览；全程可见时，相邻目标判断直接进入／绕路，远处目标返回路线摘要，并提供首步坐标及可用的预计回合。 |
| `queue_move` | 给自有可移动陆地／海军单位下达一个已探索目标的原版长程移动请求；不要求相邻，不读取隐藏路径或目标实时内容。 |
| `unit_order` | 睡眠、跳过、驻守治疗、休整、警戒、自动探索、掠夺、道路掠夺、砍伐、收获、修复改良/路线、建造道路/铁路、拆改良、植树、清核污染、考古挖掘、国家公园、摇滚演出、传教、清异教、审判、宗教治疗、转化蛮族、先知创教触发、使徒福音传播。 |
| `unit_command` | 唤醒、取消、停自动、升级、解散、赠送、解除编队、激活伟人、区域/建筑/奇观/项目加速、谴责异教徒、抢商路、传播不满、抚摸侦察兵的狗。 |
| `unit_promote` | 战斗单位、使徒、间谍、摇滚乐队等的实际可选晋升；重新验证引擎提供的候选项。 |
| `unit_form` | 自己单位之间的军团、集团军、舰队、无敌舰队与护送编队。 |
| `unit_swap` / `unit_rename` | 两个自有相邻单位换位；符合命名资格的自有单位重命名。 |
| `unit_target` / `melee_attack` | 近战、宗教战斗、远程、空袭、空军部署/转场、海岸突袭、空运、伞降、优先攻击、巨型死亡机器人跳跃。 |
| `city_attack` / `district_attack` | 自有城市、军营等区域的正常轰击请求。 |
| `combat_preview` 查询 | 本方近战／远程单位、城市或非市中心区域，对明确可见且已侦测单位的原版攻防强度与修正文案；不提交攻击。 |
| `trade_route` / `transfer_trader` | 建立商路、将商人转移到自己的城市。 |
| `spy_travel` / `spy_mission` / `spy_escape` | 派遣、资料片全部 13 种任务/反间谍、当前被追捕间谍的逃跑路线。 |
| `build_adjacent_improvement` | 军事工程师山脉隧道等邻格改良。 |
| `wmd_strike` / `icbm_strike` | 单位或自有城市地块上的导弹发射井发射核装置/热核装置；目标必须当前可见。 |

可选项通过 `inspect_game` 的 `unit_actions`、`unit_promotions`、`unit_formations`、`unit_targets`、`city_combat`、`trade_routes`、`spy_missions`、`spy_escape_routes` 获取。`trade_destinations` / `spy_destinations` 自动发现原版菜单合格目的地，包括菜单提供的雾中城市。参数含 `unit_id` 和 `offset`，从 0 开始，每页最多 64 个菜单合格项，按 `next_offset` 继续，-1 表示最后一页；分页不暴露被过滤的城市数量。`trader_origins` 列出可转移的自有城市。参数细节以 `get_rules` 为准。

`city_combat` 用本方 `city:GetDistrictID()` 识别市中心，保留 `city_attack` 并去除同一市中心的 `district_attack` 副本；真实军营等其他区域仍按原生轰击资格列出。该识别接口缺失、异常或返回无效 ID 时，保留合法的城市轰击选项，省略区域候选，避免猜测市中心身份。此项只调整选项发现，不改变已有攻击动作。第 117 回合查询城市 `131073` 对 `(16,21)` 的正常攻击时，实机仅返回一项 `city_attack`，已验证市中心候选去重（`artifacts/continuous-035-2026-10-27/journal.jsonl` L3002）。

`combat_preview` 参数为 `attacker_kind`（`unit_melee`、`unit_ranged`、`city`、`district`）、`attacker_id`、`target_owner_id`、`target_unit_id`、`x`、`y`。目标 ID 和坐标应来自本次可见地图观察。它先确认自有攻击者、当前活动回合／核心不忙、地块已探索且当前可见，再对格内候选逐一调用 `IsUnitVisible`；确认检测前不读取任何候选属性，不按输入 ID 查找外国单位。随后检查普通攻击资格和不会隐式宣战；单位分支还先检查 `CanAttackTarget`，再调用原版 `SimulateAttackVersus`。城市／区域分支要求本方与这个已检测目标的所属玩家明确处于交战状态，按正常城市／区域对象检查 `CanStartCommand(RANGE_ATTACK)`，然后以同一个已验证本方区域作显式目标模拟和后置 `CanAttackTarget` 检查；只接受模拟实际返回的 `RANGED`／`BOMBARD` 类型。双方身份及可见性在发布前再次核对。近战限相邻陆地／海军军事单位，并沿用近战数值不低于远程／轰炸值的保守限制；远程采用原版武器类型选择。城市预览用自己的市中心区域，`district` 不重复接受市中心。

返回 `attacker_strength`、`defender_strength`（原版总强度，最低为 0）、`combat_type`，以及 `attacker_modifier:<序号>`／`defender_modifier:<序号>` 的本地化文案。修正只读取原版显示的伤势、地形、对手、通用修正、协同、晋升、防御和资源这八类文字，不枚举修正背后的隐藏单位、地块或资源。Python 再按原始请求核对攻击者归属、目标身份／位置及可见性证据，仅允许这些固定字段；未知 API／异常结构返回 `supported=false`，不合格或失效的目标没有预览条目。

依据为 `Base/Assets/UI/Panels/UnitPanel.lua:3282–3353` 的明确单位目标模拟、`3594–3598` 的目标兼容检查、`1748–1767` 的强度标签、`1967–1974、1991–2028` 的修正文案；普通资格来自 `UnitFlagManager.lua:291–298` 和 `WorldInput.lua:851、2553–2556、2624–2627`。资料片 `UnitPanel_Expansion2.lua` 继承这些函数。首版不提供城市／区域作为防守目标、宗教／空军／拦截／核打击或自动选择目标的预览。原版 `DAMAGE_TO` 在 `UnitPanel.lua:1772–1778、1233–1236` 驱动预计血条，目前没有证实逐项显示精确伤害数字，因此该值、原始战斗结果和必杀断言均不返回；损伤展示留作后续优化。此查询已通过定向离线测试，近战、普通远程与城市 `ranged` 分支另有以下实机验收；独立军营及 `bombard` 分支尚未实机验证。

城市／区域对象与顺序另有 `UnitPanel.lua:3382–3400` 的正常瞄准路径直接依据：市中心／区域参与模拟，再用该区域和模拟返回的类型检查目标兼容性。因而该分支不预先假定固定 `RANGED`，也不沿用 `WorldInput.lua:2246` 的城市核打击宣战检查。额外的精确交战状态来自本方 `GetDiplomacy():IsAtWarWith(targetOwner)`，原版公开用例见 `PartialScreens/CityStates.lua:1508`、`EspionageOverview.lua:793`；缺失／非真时不模拟，发布前还会复查。第 117 回合旧实现曾在合法城市轰击候选下返回空预览（L3003）；本次按上述源码对齐并通过定向离线回归，第 119 回合调整后的城市预览已返回正常样例。旧空结果具体停在哪一道检查仍未证明。

第 116 回合，本方步兵 `4390932` 位于 `(14,19)`、移动力为 2；公开地图观察确认玩家 2 的线列步兵 `5898285` 位于当前可见的 `(15,18)`。`unit_targets` 先提供正常 `melee_attack`，随后 `combat_preview` 返回 `attacker_strength=72`，修正为战嚎 `+7`、石油资源不足 `-20`；`defender_strength=68`，修正为受损 `-6`、理想地形 `+3`、难度 `+4`、支援 `+2`，`combat_type=melee`。证据为 `artifacts/continuous-035-2026-10-27/journal.jsonl` 的 L2941、L2945、L2948–2949。这验证了近战的真实预览读取与投影，不表示已经执行攻击或造成预计伤害。

同为第 116 回合，本方野战加农炮 `4784151` 移动至 `(15,21)` 后剩余移动力为 1（L2957）；`unit_targets` 对 `(17,20)` 提供 `ranged_attack`（L2958）。对玩家 2 的明确目标单位 `6291496` 查询后，预览返回 `attacker_strength=60`、`defender_strength=74`，防守方修正为受损 `-6`、不利地形 `-2`、强化防御 `+3`、难度 `+4`，`combat_type=ranged`（L2959）。此项验证普通远程的攻击前预览；后续实际开炮及伤害回读是独立事件，不以这条预览推定。

第 119 回合，姆平达城市 `131073` 对 `(16,20)` 的 `city_combat` 只返回一个 `city_attack`（L3166）。随后以 `attacker_kind=city`、目标玩家 2、目标单位 `4915219` 查询 `combat_preview`，返回 `supported=true`、`attacker_strength=70`、`defender_strength=72`、防守方不利地形 `-2` 与难度 `+4`，`combat_type=ranged`（L3167）。这是修后城市源预览的实机成功样例，未据此声称独立区域／`bombard` 已验收，也未预先记录随后的攻击结果。

第 115 回合此前的两次查询返回 `supported=true`、空条目（L2895、L2898），同阶段本方状态确认该步兵移动力为 0（L2897）；这是预览的移动力前置检查，不能记成接口失败。下一回合恢复移动力并使用目标的新位置后，上述预览正常返回。

`queue_move(unit_id,x,y)` 与原有相邻 `move` 分开。它只接收地图边界内、`IsRevealed(x,y)==true` 且不同于单位当前格的坐标；迷雾中只使用调用方记忆的目标坐标和公开探索标签，不构造目标地块、不读地形、单位、城市或资源，不调用目标合法性或寻路接口。单位必须属于本方、剩余移动力大于零、为陆地／海军且静态 `IgnoreMoves` 未启用；沿用当前会话／回合／模态检查，并要求游戏核心不忙。商人、间谍和空军仍使用各自专用操作。

原版 `WorldInput.lua:791–808` 将目标坐标交给 `Civ6Common.lua:102–163`；其 `MOVE_TO` 分支没有相邻距离限制或目标 `CanStartOperation(MOVE_TO)` 前置。新动作固定使用既有非攻击策略 `NONE + MOVE_IGNORE_UNEXPLORED_DESTINATION`，只调用一次正常 `RequestOperation`，不追加攻击、自动取消、强制移动或重试。`submitted` 不证明成功入队、可达或已经到达；原生返回值和错误不会披露。请求可能按正常规则更新原有移动计划，路线可能绕行或跨回合执行，应回读自有位置与 `queued_destination`，不要因当下位置不变就重复提交。此动作已通过定向离线测试，尚未实机验收；原有相邻 `move` 与只读预览行为未变。

`unit_move_preview(unit_id,x,y)` 只读自己的单位，目标必须当前可见。它采用 `WorldInput.lua:884、961、1001–1009、1052–1058、1124–1141` 的 `UI.IsGameCoreBusy()`、`UnitManager.GetMoveToPathEx(unit,plotIndex)` 以及 `plots` / `turns` / `entrancePortals` / `exitPortals` 字段。`plots` 必须是有界、连续的地块编号数组；不猜坐标数组或其它返回格式。相邻目标返回 `direct`、`detour`、`no_path` 或 `unknown`；远处目标在完整路线当前可见时返回 `route`，空路线、只有起点或未到目标的局部路线均为 `unknown`，不据此推断迷雾内的可达性。只有整条路线当前可见、起终点正确且没有传送门转换时，才可能返回 `first_step_x/y` 和 `arrival_turn`。`arrival_turn` 使用原版终点的回合编号，1 表示本回合，缺少有效估计时省略。

路径包含任意不可见格时，只返回 `unknown`，不读取该格对象、地形、单位或资源，不返回首步、路线总长度或预计回合。按 `WorldInput.lua:897–900`，商人、间谍、空军等静态定义带 `IgnoreMoves` 的单位不调用路径 API，返回 `unknown`。传送门路线、游戏核心忙、同格或不可见目标同样不提供路线结论；缺少必要 API、异常或无法确认的原生结构返回 `supported=false`。接口不返回原始路径和可执行动作，不改变命令、自动探索或原有 `move` 行为。`move` 的“相邻”约束指请求的目的地，而不是强制引擎走直邻一步；原版寻路可能绕行，`submitted` 也不代表已到达。预览不检查或声明敌军分布，不保证安全，之后仍应回读实际位置。长程摘要是本次离线新增分支，尚未实机验收。

`unit_recommendations(unit_id)` 提供原版单位选中界面的规划建议：有建造次数的本方单位仅查询其当前所属本方城市的改良建议，开拓者读取原版固定五个建城推荐。只返回当前可见且已探索的候选坐标；改良另有静态类型和本地化名称。不会读取私人 AI 评分、自由文本建城理由、外国城市或目标格资源，不把推荐当成当前可执行动作。完整参考对照、原版来源及限制见 [REFERENCE_PARITY_UNITS.md](REFERENCE_PARITY_UNITS.md)。

`unit_details` 补充自己的单位面板信息：战斗力、经验与已选晋升、宗教/通用/伟人次数、编队信息、升级费用及间谍任务剩余回合。`trade_routes` 对已通过菜单资格的目的地提供菜单路线产出合计，按原版 `TradeSupport` 的路线、路径、修正及收益接收方国际贸易倍率计算；不返回原始路径或外国城市完整产出。

单位菜单的 `id` 和 `action` 保持原有格式，`name` / `description` 取游戏当前语言的原版文本。`unit_actions` 使用 `UnitCommands` / `UnitOperations` 的 `Description`（这些定义通常没有 `Name`）；改良和晋升使用各自定义的 `Name` / `Description`。`unit_promotions` 仍只列引擎实际提供的晋升，`unit_details` 已获得的晋升补同样的名称和效果。可选的本地化或描述 API 缺失、异常时保留原有选择和标识符，不编造翻译。

自有单位当前可执行的普通命令、原地操作及改良还读取原版 `UnitPanel.lua:466–530、574–704` 的 `ACTION_NAME` 和 `ADDITIONAL_DESCRIPTION`，补充伟人能力、砍伐／收获等公开动态效果。普通无目标操作使用原版 `OperationResultsTypes.NO_TARGETS`；可见目标菜单只加静态操作文字，不查询动态目标结果。返回成功升级选项时，按 `UnitPanel.lua:478–487` 使用 `UNIT_TYPE`、自有单位 `GetUpgradeCost()` 和原版升级说明，`value` 为金币费用。不会读取失败原因、隐藏目标列表或扩展允许的操作枚举。

`unit_details` 增加自有单位类型、伟人名称、被动能力说明，以及 `great_person_action` 只读记录。后者依照 `UnitPanel.lua:466–530` 先检查 `CanStartCommand(..., true)` 的正常界面显示资格，再用 `CanStartCommand(..., false, true)` 获取能力文字及当前可用状态；`value` 仅在引擎明确返回布尔值时提供。第二次调用没有提供布尔值时，仍保留已通过界面显示资格的公开文字，省略未知状态；显示资格本身缺失或不明确时仍不读取当前能力结果。即使站位不适合激活，也可查看原版显示的能力；这条记录没有 `action`，实际激活仍以 `unit_actions` 的当前合法选项及提交复查为准。被动能力使用 `UnitPanel.lua:2278–2280` 的 `HasPassiveEffect`、`GetPassiveNameText`、`GetPassiveEffectText`，不读取其他玩家的伟人。

实机确认部分伟人在不适用的站位或状态下连正常激活按钮的显示资格也不通过，因此另提供 `great_person_ability` 静态百科说明。它只使用已经确认自有单位的 `GetIndividual()` 对应定义，按 `CivilopediaPage_GreatPerson.lua:27–35、137–154` 获取主动能力：优先本地化 `ActionEffectTextOverride`，否则只对该伟人关联的静态 `GreatPersonIndividualActionModifiers`，调用 `GameEffectsText.lua:11–15` 的 `GameEffects.GetModifierTextKey(id,"Summary")` / `GameEffects.GetModifierText(id,key)`。文本由引擎按规则生成，不手工估计效果或游戏速度倍率。标题遵循原版 `ActionNameTextOverride` 和百科次数格式，其中次数是定义的初始次数；当前剩余次数仍看 `great_person_charges`。先知使用百科的创立宗教说明。

`great_person_ability` 只有名称／说明，没有 `value` 或 `action`，不代表当前位置可激活，也不绕过动态按钮门槛。不读取其他玩家、当前／历史招募时间线、运行时修正实例或外国状态。缺少正式文本接口、异常或扫描超限时省略这条可选说明，保留伟人身份和已有字段；不猜测不存在的 `GetActionEffectText` 接口。

`trader_origins` 的合格选项显示自有目的城市名称，来源同 `TradeOriginChooser.lua:58`；编队／换位候选显示已通过资格的自有伙伴名称，舰队／无敌舰队使用原版对应文案。`spy_escape_routes` 使用 `EspionageEscape.lua` 的四类逃离方式和所需回合文本，不读取敌城身份。0.3.4 已实机读取战嚎晋升、矿山和远程攻击说明，以及护送开拓者候选；护送后两单位共同移动。第 50 回合科学家与商人的正常激活选项均有具体能力文字；第 51 回合克拉苏已站在自有地块、不能再次原地激活时，`great_person_ability` 仍返回领土获取和金币说明，没有动作或可用性值。百科标题的 3 次是初始总次数；当前剩余 1 次由 `great_person_charges` 单独给出。第 87 回合的逃跑弹窗实测范围见下。

为诊断“单位需要命令”，`unit_details` 还返回 `ready_to_move`（`IsReadyToMove`）、`ready_to_select`（`IsReadyToSelect`）、`activity_type`、已知枚举的 `activity`、`fortify_turns`，以及当前单位是否是自有集合 `GetFirstReadyUnit()` 返回对象的 `first_ready`。原版 `ActionPanel.lua:431–439` 用 `GetFirstReadyUnit` 判断待处理单位；`UnitFlagManager.lua:376–380` 用 `IsReadyToSelect` 灰显旗帜；`UnitPanel.lua:4054–4069` 使用活动类型及 `IsReadyToMove` 绘制状态。没有把剩余移动力大于零推断成 `needs_orders`：治疗、睡眠或自动操作可能保留移动力。缺少相应 API 时省略字段，不伪造 `false`；没有读取第三方单位或改变当前 UI 选中项。

`unit_details` 的可选 `queued_destination` 观测只反映本方单位排队移动的目标，值为 `visible`、`hidden` 或 `unknown`。仅 `visible` 同时返回 `queued_destination_x` / `queued_destination_y`；`hidden` 表示已确认有效目的地但不披露坐标。原版 `WorldInput.lua:813–823、905–915、1157–1166` 使用 `UnitManager.GetQueuedDestination(unit)` 和 `Map.IsPlot` 恢复玩家选中单位的排队路径；本接口沿用其忙状态及 `IgnoreMoves` 门槛，只读取单一目的地，不读取路径、路线长度、到达回合或地块内容。目的地必须先通过当前可见／已探索检查，才构造地块并仅调用 `GetX` / `GetY`。

原版源码没有明确无目标返回值的契约，因此 `nil`、`false`、负数、无效目标、忙状态、能力缺失及调用异常均为 `unknown`，不声称没有队列；其他单位详情仍可返回。`ACTIVITY_OPERATION`、存在排队目标或可用的 `STOP_AUTOMATION` / `CANCEL` 按钮都不被解释为“正在自动探索”，也不会自动取消或重放命令。目标坐标不保证移动直达、可达或安全，仍须按需查询 `unit_move_preview` 并回读实际位置。该补充已做离线访问边界测试。

第 98 回合轻快帆船首次实测为 `queued_destination=unknown`，没有返回坐标。第 101 回合达尔文（自有单位 ID 3538958）向 (11,21) 提交普通移动后，状态仍在 (12,21)，详情明确返回 `queued_destination=visible`、`queued_destination_x=11`、`queued_destination_y=21`。这次验收仅确认当前可见的排队目标，不能解释为到达成功，也不能替代隐藏目的地、无队列或其他单位类型的实机验证；没有读取原始路径或改变自动操作。公开证据见持续对局日志第 2111～2113 行。

`get_pending_decisions()` 的 `can_end_turn` 与普通结束回合共用就绪、消息处理、模态界面、`UI.CanEndTurn` 和通知阻塞检查；必要检查 API 不可用时返回 `false`。它不是强制跳过单位命令的入口，值为 `true` 也只对应本次观察，提交 `end_turn` 时仍会重查。

“建造路线”由引擎按当前单位和解锁规则选择道路/铁路，不允许伪造路线等级。伟人激活使用 `UNITCOMMAND_ACTIVATE_GREAT_PERSON`，不是普通移动。考古挖掘后可能产生文物归属必选项，由决策模块处理。

宗教操作有两个阶段：`unit_order(order="activate_prophet")` 对应先知 `FOUND_RELIGION`，`unit_order(order="evangelize_belief")` 对应使徒 `EVANGELIZE_BELIEF`；能力触发后用 `religion` 查询，再提交 `found_religion` 或 `add_belief`。单位换位由 `unit_swaps` 查询发现，仅对自有相邻单位调用原版右键路径的 `SWAP_UNITS`；它虽不单独显示为按钮，仍是正常 UI 操作。没有因此开放其它隐藏枚举。

可见性规则：先验证地块，再读取目标；攻击单位必须通过 `IsUnitVisible`，只亮格子不能攻击尚未探测的潜艇。近战、远程/空袭等不会隐式宣战，应先用外交接口宣战；核打击具有其正常游戏后果。探测失败时，不查询目标是否合法，不返回引擎原因。未知枚举及缺失能力均拒绝。

攻击选项和执行阶段都检查己方能力：原版 `UnitPanel.lua:3261` 排除军事战斗力与宗教战斗力均为零的单位，因此建造者、开拓者不会被列为可近战；宗教战斗力非零的单位仍保留宗教攻击路径。原版 `WorldInput.lua:968–971` 说明引擎合法性检查可能对零移动力的远程单位仍返回可攻击，因此普通 `ranged_attack` 另要求剩余移动力大于零，并在提交时重查。这个额外移动力规则仅用于普通远程攻击，不替代空军、转场等特殊操作自己的引擎规则。

实机弓箭手曾因拥有防御用 `GetCombat()` 而被误列近战。现按 `Civ6Common.lua:137–149` 的普通右键武器优先级保守过滤：军事单位必须属于陆地或海洋，且近战数值不低于远程／轰炸数值，才提供及提交近战；宗教路径保留。原版分流还检查 `CanStartOperation(RANGE_ATTACK)`，这里不把远程操作暂时不可用当成近战许可，因此不是声称完整复刻该分流，也没有假设存在 `CanMelee` API。保留侦察兵、双攻击巨型死亡机器人（原版 130/120）及长生军（35/25）；未用“远程数值非零”或 `UNITTYPE_MELEE` AI 标签一刀切。查询和执行都会重查，缺少能力字段则不放行。

商路和间谍菜单按用户 P08/P09 确认采用独立权限，普通地图查询仍严格过滤迷雾。商路的起点必须是商人所在的市中心，目的地同时通过原版 `CanStartOperation` 与 `GetTradeRoutePath` 非空判定；查询及提交动作共用检查，路径内容不会返回。间谍城市按当前规则集的原版外交状态、队伍、自由城市和已探索条件筛选，不能只用 `HasMet` 或 `CanStartOperation` 代替菜单资格。

`spy_missions(unit_id,x,y)` 输入菜单城市中心时列出该城可预览的任务及菜单提供的具体目标。只有间谍当前驻城的任务提供可执行 `spy_mission`；远城预览不提供任务动作，须先派遣并等旅行／建立网络完成。执行时再次确认当前城市与菜单目标；进攻任务使用原版无参数请求，反间谍使用已经过本城区域匹配的坐标。源码与字段边界见 [菜单权限说明](MENU_PERMISSIONS.md)。

当前驻城确实可打开任务菜单时，`spy_missions` 还提供可选 `sources_turns_remaining`，来自 `EspionageChooser.lua:107–121` 的本方 `GetSourceTurnsRemaining(currentCity)`；0 表示没有生效的“获取来源”加成。远城预览、派遣列表或当前无法打开任务菜单时不读取这个字段，API 缺失或异常则省略。可选任务效果文本异常时仍保留已验证的任务选项，不编造效果。

`spy_overview` 无参数，补充旅行期间暂时不在普通单位集合中的本方间谍。它沿原版 `Base/Assets/UI/PartialScreens/EspionageOverview.lua:128–146、734–757` 读取本方 `GetNumSpiesOffMap()` / `GetNthOffMapSpy(me,index)`，排除 `ReturnTurn == -1` 的条目，返回姓名、原版等级称谓、旅行剩余回合及可用的目的城市名称；另有 `travelling_count` 和可选的本方 `capacity`。风云变幻的概览替换文件继承这些函数。`travelling:<index>` 只是本次快照的序号，不是 `unit_id`，不能据此操作单位；抵达后重新获取正常自有单位。核心列表接口缺失或快照不一致时 `supported=false`，目的地／容量字段缺失表示未知。

该概览同时按 `EspionageOverview.lua:630–714` 提供 `stationed:<unit_id>` 本方地图间谍及可选的等级、驻城、当前任务、剩余／总工期、任务区域和效果。它不要求间谍有移动力；正在执行任务也可以查看。当前区域只读这个自有间谍所在格的 `GetDistrictType()`，效果则按 `EspionageSupport.lua:2–23` 使用驻城中心，二者不混用。反间谍效果仅使用该区域名称，不读取进攻任务详情或概率；闲置间谍没有任务区域／效果字段。身份、位置或集合读取失败时省略整份地图间谍子列表及 `stationed_count`，不把未知报成零；其余可选字段缺失不影响已确认身份。查询不枚举外国单位、外国旅行列表或城市区域，不读取俘虏、产出或邻格，也不改变普通地图迷雾过滤。新增观察分支已通过离线 Lua 回归，尚未实机验收。

逃跑路线是独立例外：只有自己的当前被追捕间谍存在时，读取原版逃跑弹窗明确提供的四类路线是否可选，不返回敌城身份或其它属性。原版 `UnitCaptured.lua` 只有确认消息，没有归还平民的选择接口；赠送使用普通 `UNITCOMMAND_GIFT`，由引擎控制适用对象。没有单独的“巡逻/拦截”命令枚举，空军部署由 `DEPLOY` 执行，后续拦截由游戏规则处理。

第 87 回合实测抽取资金后，待处理查询自动发现 `SPY_CHOOSE_ESCAPE_ROUTE` 和通知 630。激活通知后，`spy_escape` 返回完整警察追捕、战利品与路线正文：没有机场／港口，飞机和海路禁用；车辆需 3 回合，步行需 4 回合。提交当前步行按钮后，回读确认阻塞清除，`spy_overview` 显示马可巴离图返回首都、剩余 4 回合。此前任务预览为 468 金，逃跑面板战利品为 572 金，不能把预览金额当作最终结算。此验证覆盖通知激活、可见逃跑按钮响应和旅行状态。

第 89 回合关闭大型洪水提示后，`EspionagePopup` 的 `spy_mission` 结果自然显示：任务成功、伊斯坦布尔获得 572 金币、升级至探员及可选晋升的文字。当前按钮 4 确认后该弹窗消失，随后血色契约发现提示（已加入夜鹰）也可读取，并用当前按钮 1 正常继续。该次验收覆盖任务结果和后续弹窗队列；尚未验证任务简报接受或续派分支。回读 `spy_overview` 仍为旅行剩余 2 回合、等级 1，需抵达后再选择晋升，不能仅凭结果文案推断当前等级已经改变。

第 91 回合马可巴返回首都，`travelling_count=0`，重新获取的自有单位 ID 为 3080207。`unit_promotions` 返回语言学家、王牌驾驶员和杀戮执照；提交当前语言学家选项后，`spy_overview` 确认为等级 2（探员）。由此验证了逃跑返程后的单位重新发现及正常晋升闭环，不能复用此前离图前的单位 ID。

本方间谍的 `unit_actions` / `unit_command.cancel` 按原版 UnitPanel 的两项 `CanStartCommand` 检查提供取消任务，不要求驻城地块当前可见。提交只使用自有间谍和固定 CANCEL 命令，不读坐标、外国城市或隐藏地图；非间谍取消与其余操作保留原视野门。专属回归 20 项，连同单位、间谍菜单和弹窗检查共 344 项通过；取消动作尚未实机提交。

`submitted` 仅代表发出了正常请求，不能当作成功。所有操作仍须最新一次性观察令牌、当前玩家及活动回合。Lua 模拟测试验证权限/参数/过滤；实机反馈与动画时序尚需联调。
