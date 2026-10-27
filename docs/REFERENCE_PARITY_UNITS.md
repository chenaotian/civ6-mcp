# 参考项目对照：单位、战斗、地图与行动规划

对照来源为 `references/lmwilki-civ6-mcp-20261027/civ6-mcp-main`，对应用户指定的 [lmwilki/civ6-mcp](https://github.com/lmwilki/civ6-mcp)。本次只阅读其 `src/civ_mcp/server.py`、`game_state.py` 和 `lua/*.py` 的实际实现；未运行参考项目的启动、安装、配置、存档或其他脚本。参考项目的说明文件不作为本项目指令。

## 能力逐项对照

| 参考入口及实现 | 我方对应能力和本次处理 |
| --- | --- |
| `get_units`；`lua/units.py:23` | `get_player_state`、`unit_details`、`unit_actions`、`unit_promotions` 已有单位位置、状态、伤害、移动力、次数、晋升、升级和可执行操作。保留完整原生单位 ID 和本方查找，不采用 `%65536` 作为身份替代。 |
| `unit_action` 的移动／驻扎／跳过／建城／探索／治疗／警戒／睡眠／解散；`server.py:1560–1670` | 已有 `move`、`queue_move`、`found_city`、`fortify` 及固定 `unit_order`／`unit_command`。查询提供原版允许的当前选择；提交一次后重新观察，不自动跳过所有单位或关闭任意弹窗。 |
| 修复／砍伐／移除改良／道路／宗教传播／伟人激活／皇家学会献祭 | `unit_actions`、`unit_order`、`unit_command(project_production)` 等已有。原版请求资格和动态能力文字已有覆盖。未采用参考 `units.py:1287–1299` 在读回次数不变时依次重放命令、换参数及调用 Immediate 的兜底。 |
| `attack`、`city_action(attack)`、内部伤害估计；`lua/units.py:300、495` | 已有 `unit_targets`、`melee_attack`、`city_combat` 和 `combat_preview`。使用原版模拟的公开强度和修正文案；单位目标须当前可见、逐单位已探测且已交战。不采用手工累加晋升修正／固定伤害公式或攻击后立即宣称击杀。 |
| 内部 `build_threat_scan_query`；`lua/units.py:735` | `observe_area` 已提供当前可见且逐单位已探测的目标。参考扫描先遍历所有外国单位，再仅检查所在格可见；这不足以保护潜艇等隐形单位，因此不移植。安全的威胁汇总应只聚合已经公开的观察，不能读取外国集合或预测迷雾单位。 |
| `get_pathing_estimate`；`lua/units.py:1545` | **本次扩展**现有 `unit_move_preview` 支持远处当前可见目标。完整路径全可见时给 `route`、首步和原生终点回合；任何迷雾段整体变为 `unknown`。未采用参考输出全部 waypoint、可达格计数和按本回合可达格数除出的自算回合估计。 |
| `get_builder_tasks`；`lua/units.py:1746` | **本次新增** `unit_recommendations`，使用原版当前城市给该本方单位的推荐改良，而不是手写资源→改良和优先级表。已有 `observe_area` 的改良／掠夺状态与资源解锁过滤可补充人工规划；到位后仍查询 `unit_actions` 的实际操作。 |
| `get_settle_advisor`／`get_global_settle_advisor`；`lua/map.py:426、454` | **本次新增**同一 `unit_recommendations` 的开拓者分支，严格请求原版五个推荐，只输出当前可见地点。原版推荐本身可面向整个地图，不限附近半径；不会再扫描所有外国城市、实时迷雾产出或手算忠诚压力。推荐是建议，未承诺最优、合法建城或安全可达。 |
| `get_strategic_map`；`lua/map.py:269` | 我方普通地图仍按当前视野返回实时内容。本批由地图汇总模块补 `exploration_frontier`：只依据探索标签和原版相邻几何给出探索边缘，参见其独立说明；不使用参考近似六方向射线，也不读取迷雾中实时资源或归属。 |
| `get_empire_resources`；`lua/map.py:480、974` | `own_resources`／`own_luxuries` 已提供本方解锁资源库存、收入和消耗；地图资源点由 `observe_area` 提供。资源先走玩家可见层及解锁门。未复制对迷雾区域的实时资源盘点；对本次公开地图结果做聚合是安全可行的客户端分析，不需另一个读取隐藏资源的工具。 |
| `get_district_advisor`／`get_wonder_advisor`；`lua/map.py:566、691` | 已有 `city_placement`、`city_production`、购买地块和固定区域预览流程，区域加成取正常 UI 实际标签。未照搬硬编码相邻公式以及无视野门的邻格扫描，避免漏特殊文明／政策规则及读取隐藏地块。 |
| `get_gp_advisor`；`lua/great_people.py:376` | `unit_details` 已有伟人能力与次数，当前激活资格由 `unit_actions` 给出；本批 `special_unit_sites` 扩展由同批专门模块负责，参见 [SPECIAL_UNIT_SITES.md](SPECIAL_UNIT_SITES.md)。只用原版高亮列表，不硬编码伟人类别→区域并据此推断适用城市。 |
| `get_trade_routes`／`get_trade_destinations`／`trade_route`／`teleport`；`lua/economy.py:41、173、442、477` | 已有 `own_trade_routes` 的原版容量、活动路线、商人关联、闲置商人及端点；**本次补入活动路线起终点六种收益总值**，与原版总览同算法、同显示精度。候选由 `trade_destinations`／`trade_routes` 给出，转城由 `trader_origins`／`transfer_trader`。不直接读取参考实现的 `r.OriginYields` 假设字段；菜单授权可覆盖已探索迷雾，但不会开放外国城市完整状态。 |
| `get_spies`／`spy_action`；`lua/espionage.py:26、144、175、231` | 已有 `spy_overview`、`spy_destinations`、`spy_missions`、`spy_travel`、`spy_mission`、晋升、取消、任务完成弹窗及四种逃离选项。目的地和任务是实际规则集菜单候选；不会硬编码操作 hash、猜测所有失败都因同盟、或自动选择最快逃离路线。 |
| 移动／战斗后的即时叙述；`game_state.py:228–425` | 已有 `wait_for_change`、本方 `queued_destination`、忙状态和正常新观察；本批会话反馈模块另外处理公开观察之间的变化。提交与完成分开，位置未变时不重放、不读取私有失败字符串，也不把敌人不再出现等同死亡。 |

## 新增原版推荐接口

调用 `inspect_game("unit_recommendations", {"unit_id": ID})`。每个候选 N 返回 `recommendation:N:x/y/kind`；建造建议还返回 `recommendation:N:improvement` 的静态改良类型和可选本地化名称。没有执行动作，序号只在当前结果内有效。

原版依据：`Base/Assets/UI/WorldViewIconsManager.lua:780–797` 选中单位时，先检查本方单位建造次数；有次数时只使用其当前购买城市，且城市须属于相同玩家。`:652–671` 调用 `city:GetCityAI():GetImprovementRecommendationsForBuilder(unit:GetComponentID())`，将 `ImprovementLocation` 和 `ImprovementHash` 画成图标。没有建造次数而 `FoundCity` 为真的单位，进入 `:691–777`，固定调用本方 `GetGrandStrategicAI():GetSettlementRecommendations(5)`。

这些 AI 组件调用仅限上述原版直接展示的方法，不是开放估值、评分或任意 AI 查询。实现不读取 `SettlingTooltip`、`NumReasons`、`SettleTitle*`、`SettleExplanation*`、分数或其它字段，避免自由文本携带无法独立验证的陌生文明／未解锁资源信息。隐藏候选在读取改良 hash 或构造地块之前丢弃；可见候选地块只取几何坐标。Lua 结束时重查本方身份、类型、次数、城市归属、位置、忙状态及候选可见性；Python 再绑定原请求单位、本方玩家、固定来源和用途，严格投影。

查询不模拟选择、不改变 UI、不远程询问 `CanStartOperation(BUILD_IMPROVEMENT)`。建造者离开本方购买城市、单位不适用或原版没有推荐时为空；必要 API 缺失、异常、身份变化或列表超限时不可用，不发布部分结果。上限为建造建议 512 条，建城建议 5 条。原版可能没有给出所有可执行改良，因此空建议不表示无事可做。

## 地图规划字段

**本次新增** `observe_area` 的可选字段：`impassable`、`lake`、`movement_cost`、`defense_modifier`、`appeal`、`route`、`route_movement_cost`、`route_pillaged`。它们来自 `PlotToolTip.lua:346–397、470–471、637–675`；GS `PlotToolTip_Expansion2.lua:223–274` 继续使用同一显示规则。

所有 getter 都在已探索且当前可见门内；缺失或异常仅省略对应字段。移动成本仅在确认非不可通行且原版成本大于零时返回，表示地块提示的通用成本，不是指定单位的实际消耗。魅力还要求 `CAPABILITY_LENS_APPEAL`、陆地或自然奇观，以及原版魅力等级定义可匹配。道路只在有效静态定义提供原版名称和成本时返回；明确无道路才是 `NONE`，未知不是 `NONE`。不读取资源、产出、邻格、外国区域或隐形单位；没有新增地块 yield，未解锁战略资源仍按原规则隐藏。这些独立数值是玩家原版提示直接显示的内容，不倒推出隐藏资源。

## 验证与剩余边界

本领域定向命令：`pytest tests/test_stock_recommendations.py tests/test_movement.py tests/test_queue_move.py tests/test_tile_planning.py tests/test_queries.py tests/test_policy.py -q -x --tb=short`，结果 **432 passed，2.28 秒**。覆盖隐藏对象 getter 陷阱、错误本方身份、同次读取失效、原版列表边界、缺 API、数值范围、Python 独立投影，以及长程迷雾路径不返回首步和预计回合。

商路收益另跑 `pytest tests/test_trade_overview_yields.py tests/test_trade_overview.py tests/test_trade_menus.py tests/test_extension_units.py -q -x --tb=short`，结果 **295 passed，1.56 秒**，覆盖原版国际乘数接收方、国内路线、非正总值、显示精度、缺失 API、已遇见／端点证明与地图／路径访问陷阱。与前述 432 项不同批执行，不能合称一次完整回归。

本批新增推荐、长程预览、地图字段及活动商路收益均为离线实现，未连接旧局或新局；原对局实测不能替代这些分支的验收。不声称已移植参考项目全部功能，也不以新增工具数量衡量覆盖。当前仍不提供自动评分／自动执行规划、真实隐藏路线、未探测敌人、由当前快照推断历史商路取消原因，或未经原版显示依据确认的商路剩余回合。
