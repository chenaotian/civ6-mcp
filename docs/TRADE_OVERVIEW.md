# 本方活动商路总览

`inspect_game(category="own_trade_routes", params={})` 读取原版“我的路线”当前清单，没有玩家、城市或坐标选择参数，不提交操作。它与 `trade_destinations` / `trade_routes` 的可选目的地菜单分开：忙碌商人也能出现在活动清单中。

| 返回记录的 `id` | 含义 |
| --- | --- |
| `active_count`、`capacity` | 原版当前本方活动商路数与容量；活动数超过容量仍保留真实数值。 |
| `idle_trader_count` | 本方当前贸易单位中，没有关联活动商路的数量。 |
| `trader:<unit_id>:status` | `active` 或 `idle`，仅针对本次本方单位集合中存在且静态定义可建立商路的单位。 |
| `route:<trader_id>:trader_unit_id` | 活动路线记录引用的 `TraderUnitID`；不是对该单位仍存在于本方集合的额外保证。 |
| `route:<trader_id>:origin_city_id`、`origin_name`、`origin_x/y` | 本方出发城市的标识符与可选名称、坐标。 |
| `route:<trader_id>:destination_owner_id`、`destination_name`、`destination_x/y` | 原版当前路线目的地。所有者须为自己或已遇见；坐标还须已探索。缺失项为未知。 |
| `route:<trader_id>:origin_yield:YIELD_*`、`destination_yield:YIELD_*` | 可选的起点／终点每回合收益总值，六种标准产出，按原版总览显示保留一位小数。缺失不表示零。 |

`idle` 仅表示当前完整清单未关联该商人，不等于“刚完成”“被取消”“被掠夺”或已准备接受新路线。必须另看当前单位状态及目的地菜单。路线引用仍存在但商人暂时不在本方单位集合中时，保留路线引用，不生成该单位的 `trader:*:status`。查询不推断历史结束原因，也不把一次 `trade_route submitted` 当作活动路线已建立。

源码依据为安装的 `Base/Assets/UI/TradeOverview.lua:51–78`：本方 `GetTrade():GetNumOutgoingRoutes()` / `GetOutgoingRouteCapacity()`，以及逐个本方城市 `GetTrade():GetOutgoingRoutes()`。同文件 `:318–333` 通过路线的起终点玩家／城市 ID 查找并显示名称；`TradeSupport.lua:2–27` 使用 `TraderUnitID` 与本方贸易单位匹配来识别闲置商人。`UnitPanel.lua:2172–2185` 也用同一记录显示当前商路名称。风云变幻 `InGame.xml:57` 仍加载该 TradeOverview 实现。

每条路线先验证原点属于当前玩家且与枚举到的自有城市相同，之后才读取其余身份字段。本方城市／单位集合和路线数组都有上限、重复及结构检查；路线总数必须等于原版活动数量，读取结束时再次核对数量、容量和核心忙状态。必要接口缺失、结构不完整、数量变化或超限时返回 `supported=false, items=[]`，不返回部分计数或闲置结论。名称、坐标等可选字段缺失不抹掉已确认的本方路线。

外国端点仅在已有本方活动路线中按精确玩家／城市 ID 查找，且先检查 `HasMet`。不会枚举外国城市、来往本方城市的全部外国商路或全图；只允许城市的 owner、ID、名称及坐标 getter。坐标经 `IsRevealed` 后才输出，不要求当前照亮；不构造地块对象，不读取外国城市人口、产出、区域、资源或单位。未知文明身份不输出。Python 再按固定字段和路线菜单证明过滤；不能伪装成 `self` / `public` 绕过目的地权限，不返回动作、原始对象或证明字段。

没有提供剩余回合、完成日期或原始路径。原版 `TradeOverview.lua:435–437` 的 `RouteDistance` 实际来自 `Map.GetPlotDistance`，不能解释为剩余回合；`TradeOverview.xml:142–144` 的独立 Duration 标签隐藏且没有相应动态赋值。本接口不猜测不存在的计时 getter，不用路线长度手算完成时间。

本次参考项目对照补入活动路线收益。`TradeOverview.lua:339–359` 对“我的收益／对方收益”调用 `TradeSupport.GetYieldsForRoute`；该 helper `:62–146` 分别累加起点或终点的 `Calculate*YieldsFromPotentialRoute`、`FromPath`、`FromModifiers`，国际路线再对正总值应用收益接收方 `GetInternationalYieldModifier`。这里复用与候选商路相同的数值 helper，只在现有本方路线且目的地身份已遇见、精确城市核验成功后调用。只返回总值，金额按总览的 `Round(value,1)` 显示精度；不返回来源分量、原始路径、宗教或外国城市状态。不直接相信路线记录中的 `OriginYields`／`DestinationYields` 字段。收益 API 缺失、异常、数组不完整或超出有限范围时省略对应一侧，不抹掉已确认路线，也不将未知乘数当作 1。当前菜单收益不是过去已到账的账本。该新增分支仅离线验证，尚未新局实测。

定向离线验证覆盖原点归属、完整清单与活动数一致性、闲置关联、已遇见目的地精确查询、雾内菜单名称、未探索坐标过滤、未知身份访问陷阱、暂缺商人、缺失接口及 Python 权限证明。

第 115 回合首次实机验收返回 `supported=true`、`active_count=6`、`capacity=5`、`idle_trader_count=0`，六名商人的状态均为 `active`。公开日志 `artifacts/continuous-035-2026-10-27/journal.jsonl` 第 2888 行完整给出以下关联：

| 商人 ID | 出发城市与坐标 | 目的地与坐标 |
| --- | --- | --- |
| 524290 | 姆巴巴 (10,28) | 奥克兰 (12,12) |
| 1966089 | 金沙萨 (19,26) | 撒马尔罕 (12,18) |
| 2097156 | 姆班赞刚果 (15,26) | 奥克兰 (12,12) |
| 3276812 | 金沙萨 (19,26) | 姆班赞刚果 (15,26) |
| 3735558 | 奎拉 (11,24) | 奥克兰 (12,12) |
| 3932165 | 金沙萨 (19,26) | 那烂陀 (18,12) |

本次确认活动数大于容量时仍可读取真实清单、单位关联以及国内／外国端点；没有把 6 条截成容量 5。闲置商人存在、缺失端点等其他分支仍以离线测试为证。此快照不解释此前卡霍基亚路线结束或取消的原因，也没有返回剩余回合。功能为原 0.3.6 发布包之后的工作区增量，本次未重新打包；后续实测见 [持续记录](LIVE_TEST_035_2026-10-27.md)。
