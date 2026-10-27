# 自有资源

## 战略资源

`inspect_game(category="own_resources", params={})` 返回本玩家已经解锁的战略资源，以及可读取的公开余额和每回合收入／需求。它不接收玩家 ID、资源 ID、函数名或地图范围，不提供动作。

先筛选静态 `GameInfo.Resources` 的 `RESOURCECLASS_STRATEGIC`，再调用本玩家 `GetResources():IsResourceVisible(row.Hash)`。只有明确为 `true` 时才读取资源标识、名称和数值；未知资源不返回名称、数量、占位符或被过滤数量。用户已确认的 P04 允许返回已解锁资源的零库存。没有扫描地块、城市或外国资源来源，也没有推断地图上的矿藏。

返回格式沿用 `items`：资源本身的 `id` 为 `RESOURCE_IRON`，`name` 是游戏本地化名称；数值记录为 `RESOURCE_IRON:amount` 等，`value` 是数值，`description` 说明含义。所有记录都是己方权限，原始作用域字段由 Python 输出边界验证后移除。

| 后缀 | 含义与来源 |
| --- | --- |
| `amount` | `GetResourceAmount(ResourceType)`，己方可用数量；风云变幻中是当前可用库存。 |
| `stockpile_cap` | `GetResourceStockpileCap`，库存上限。 |
| `reserved` | `GetReservedResourceAmount`，已预留数量。 |
| `stockpile_total` | 原版顶部栏合计：`min(amount + reserved, stockpile_cap)`。 |
| `accumulation_per_turn` | `GetResourceAccumulationPerTurn`，每回合采集量。 |
| `import_per_turn` | `GetResourceImportPerTurn`，原版称来自城邦的每回合输入。 |
| `bonus_per_turn` | `GetBonusResourcePerTurn`，每回合其他奖励。 |
| `income_per_turn` | 采集、城邦输入与奖励的合计。 |
| `unit_demand_per_turn` | `GetUnitResourceDemandPerTurn`，每回合单位需求。 |
| `power_demand_per_turn` | `GetPowerResourceDemandPerTurn`，每回合发电需求。 |
| `demand_per_turn` | 单位和发电需求之和。 |
| `net_per_turn` | 收入减需求，尚未计库存上限和资源短缺，不保证下回合实际库存变化。 |

仅 `GameConfiguration.GetValue("RULESET")` 明确为 `RULESET_EXPANSION_2` 时读取库存上限、预留和累计／需求字段。原版、迭起兴衰或未知规则集只返回可用数量，避免将原版的资源数量误称为风云变幻的累计库存。资源可见性接口缺失、异常或返回值不明确时，查询关闭并返回 `supported=false`；数值字段的可选 getter 缺失、异常或返回无效值时仅省略该字段及依赖它的合计，不填零。

依据本机官方源码：

- `Base/Assets/UI/TopPanel.lua:318–320`：己方战略资源数量。
- `DLC/Expansion2/UI/Replacements/TopPanel_Expansion2.lua:43–64、75–104`：库存、预留、收入、需求及合计算法。
- `DLC/Expansion2/UI/Replacements/ReportScreen_Expansion2.lua:29–35、83–85`：己方资源报告的数值接口。
- `DLC/Expansion2/UI/Replacements/PlotTooltip_Expansion2.lua:167`：使用资源 Hash 的玩家可见性检查；本接口在所有资源数值读取之前执行这个门槛，遵守用户的未解锁过滤规则。

新增访问陷阱测试覆盖未解锁资源名称／数量、外国与地图访问、规则集差异、零库存、负净变化、缺失接口、异常返回、迭代上限和合计依赖。第 49 回合已实机返回马 25/25、采集量 2，铁 0/25、采集量 0；只列出当前已解锁的马与铁。首次查询发现游戏 Lua 不提供 `table.unpack`，改为直接传参后实机恢复，并增加缺少该函数的回归。后期资源、发电需求等尚未在这局触发。

## 奢侈品库存

`inspect_game(category="own_luxuries", params={})` 返回原版资源总览中本方当前持有的正数量奢侈品。它不接收玩家、资源或函数名参数。每种资源有 `RESOURCE_*` 名称条目及 `RESOURCE_*:amount` 数量条目；`amount` 是**资源总览的本方持有份数，不是对特定文明可交易的上限**，也不表示本地产量或未出口数量。它不返回资源来源、交易对象、进口/出口明细或地块。

实现只遍历静态 `RESOURCECLASS_LUXURY` 定义，调用本玩家 `GetResources():GetResourceAmount(row.Index)`，明确大于零后才读取标识和本地化名称。它不按地图生成频率、地块存在性或可交易资格过滤，因此玩具、牛仔裤、香水、化妆品这类 `Frequency=0` 的伟商资源也能出现；这不改变战略资源的解锁门槛。有限整数余额小于等于零时按原版省略；缺失接口、异常或无法解释的数量使整个库存查询 `supported=false`，不返回伪装完整的部分清单。仅名称翻译失败时退回公开资源标识。

原版依据：`Base/Assets/UI/Screens/GlobalResourcePopup.lua:113–129` 明确区分持有量与交易量，并直接枚举本方数量；`:185–200` 以本方持有作为报告可见条件。`Base/Assets/Gameplay/Data/Resources.xml:207–210` 将上述四种伟商物品定义为奢侈品。`ReportScreen.lua:485–500` 与 GS `ReportScreen_Expansion2.lua:93–117` 也通过本方资源数量补入其他玩法奖励。

定向测试使用不可访问字段陷阱，覆盖非战略资源专用路径、伟商资源、零/负余额、浮点形式整数、完整性失败与名称回退。新增查询尚待本局实机验收。
