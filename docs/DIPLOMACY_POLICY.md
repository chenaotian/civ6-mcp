# 外交和胜利情报的公开范围

用户已确认 P05/P06/P07：公开参赛文明总数；仅在接触后公开身份；允许普通玩家界面中的对手统计、已揭示议程和胜利进度。目标环境为 Steam 原版、迭起兴衰、风云变幻，无模组。

实现为 `src/civ6_fair_mcp/diplomacy.py` 的固定只读 Lua 模板。以下依据均来自本机安装目录 `F:\SteamLibrary\steamapps\common\Sid Meier's Civilization VI`，于 2026-10-22 核对；未从调试面板推定玩家权限。

## 身份和总数

`PlayerManager.GetWasEverAliveMajors()` 的用法见 `DLC/Expansion2/UI/Additions/ClimateScreen.lua:812`。返回列表的长度作为 `civilization_count`，包含自己和已被消灭的参赛大文明，不统计城邦。这里只输出总数，不输出未接触槽位、未知领袖、未知文明的存活状态或分类统计。

每个对象只先调用 `GetID()`，用本地玩家的 `GetDiplomacy():HasMet(id)` 建立接触权限，然后才读取该对象的配置和公开字段。自己直接获得权限。未接触对象没有身份占位记录，也不访问其 `PlayerConfigurations`、经济、科技、议程、城市或单位。已接触的灭亡文明仅保留身份、存活和对本方战争关系，省略其经济和胜利数据。

身份依据：`Base/Assets/UI/DiplomacyRibbon.lua:65`、`DiplomacyActionView.lua:226`；`WorldRankings.lua:485` 使用 `GetPlayerName()`。返回的显示名称属于不可信游戏文本。

## 统计和议程

`Base/Assets/UI/DiplomacyRibbon.lua:180–185,513–536` 同时给出能力/胜利模式开关和统计读取方法。金币余额向下取整；科技、文化、军力和分数使用界面整数精度，避免把内部小数作为额外情报。没有权限开关或方法不可用时省略该字段。

对手每回合净金币暂不返回。本机 `GetGoldYield() - GetTotalMaintenance()` 的展示代码位于本地玩家的顶栏和交易面板顶栏，并不足以证明该精确数值公开给对手。交易可提供的每回合金币也不等同于净收入。自己的 `gold_per_turn` 正常提供。

风云变幻议程规则来自 `DLC/Expansion2/UI/Replacements/DiplomacyActionView_Expansion2.lua:42–64`：调用 `GetAgendasAndVisibilities()` 后，逐项要求 `entry.Visibility <= 本地外交:GetVisibilityOn(id)`，通过后才读取议程标识和静态定义。未通过的议程名称、类型、数量和阈值均不输出；不降级使用会暴露全部议程的 `GetAgendaTypes()`。人类玩家返回空议程列表。无法确认权限时省略议程字段。

## 胜利进度

每项要求对应胜利模式启用，仅对已接触且存活的文明调用。只使用普通界面中的总量，不复制界面内部的全世界城市/区域扫描。

| 字段 | 本机界面依据 | 限制 |
|---|---|---|
| `science_techs_researched` | `Base/Assets/UI/PartialScreens/WorldRankings.lua:54–57` | 科技完成数量，不返回具体秘密研究列表 |
| 四个 `science_*_completed` 布尔值 | `DLC/Expansion2/UI/Replacements/WorldRankings_Expansion2.lua:21–31,461–513` | `GetNumProjectsAdvanced` 查询四个固定太空项目；不读城市生产进度 |
| `science_light_years`, `science_light_years_per_turn` | 同文件 `:585–598` | 仅已完成系外行星发射后；路程按界面总目标截断 |
| `culture_domestic_tourists`, `culture_visiting_tourists` | `Base/Assets/UI/PartialScreens/WorldRankings.lua:1674–1675,1741–1751` | 仅两个公开总量，不返回游客来源目标 |
| `religion_cities_following`, `religion_faith_per_turn` | 同文件 `:41–48,732–733` | 宗教城市数量和信仰产出；信仰按界面 `Round(value, 1)` 保留一位小数，不返回城市、位置或目标文明 |
| `diplomatic_points`, `diplomatic_points_required` | `DLC/Expansion2/UI/Replacements/WorldRankings_Expansion2.lua:62–78` | 公开胜利点和静态门槛，不返回得分来源/未来投票 |

本版省略：征服胜利首都明细和精确首都计数、宗教胜利已转化文明明细和精确文明计数、胜利目标/需求树、文化胜利全世界游客门槛、外国城市中的太空项目在建百分比。这些路径会要求访问未公开对象或全世界城市，尚未实现不暴露目标信息的替代来源。省略不表示数值为零。

游客数、已完成科技数量、外交胜利点、信教城市数量均为计数字段。Lua 数值若以 `8.0` 等形式返回，会验证其确为非负整数后规范为整数 JSON；不会把意外的小数直接截断成公开计数。太空旅程沿用界面里的总目标截断与原始路程/速度显示，不增加推导出来的精度。

## 错误处理与信任边界

字段读取各用固定回调执行 `pcall`。缺失能力、缺失方法、错误和无效数值只省略相应字段，不输出引擎错误或诊断。身份门控失败时不读取对手明细。整个查询仍使用通用的本地人类玩家、单人、非编辑器、非观察者权限检查。

这份实现依据已安装 UI 源码，并有实际执行生成 Lua 的对抗性模拟测试。它尚未代替真实游戏中的联调验证；只证明这些固定数据路径的筛选行为。MCP 不能限制另一个拥有操作系统、存档或 FireTuner 直接访问权限的客户端。
