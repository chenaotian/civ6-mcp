# 外国单位可见性与潜行判定

实现文件：`src/civ6_fair_mcp/visible_units.py`，导出固定 Lua 片段 `UNIT_HELPERS`。片段定义 `visible_units_at(plot, index)`，供已经通过地块可见性检查的地图查询调用。适用目标为本机原版《文明 VI》、风云变幻及迭起兴衰，无游戏规则模组。

## 实际采用的权限门

使用游戏自身逐单位检测 API：

```lua
PlayersVisibility[me]:IsUnitVisible(unit)
```

本机原版 `Base/Assets/UI/Popups/MapSearchPanel.lua:467` 先确认地块当前可见，再调用 `Units.GetUnitsInPlotLayerID(x, y, MapLayers.ANY)`；`:475` 对每个对象调用 `IsUnitVisible`，随后才读取单位类型、名称和拥有者。`Base/Assets/UI/WorldInput.lua:1041` 同样同时检查地块可见与单位可见。这是玩家正常地图搜索和移动目标界面使用的引擎判断。

因此，地图被照亮不等于上面的所有单位已被发现。本 MCP 不按“单位名包含潜艇”、固定距离、是否有驱逐舰或单位旗帜缓存猜测。隐蔽能力、晋升、相邻敌方单位、侦隐能力和其他有效规则均交给当前玩家的引擎检测结果处理。`IsUnitVisible` 的原生 C++ 内部实现未在本项目审计；这里采用的是原版 UI 的实际权限门。

单位旗帜未作为备用授权依据：`UnitFlagManager.lua:1117` 接收单位可见性事件，但 `:1778` 的刷新分支还会按地块可见性更新旗帜，不能据此替代逐单位检测。

## 规则资料与为什么不用手工距离判定

官方提供了[原版英文游戏手册](https://cdn.akamai.steamstatic.com/steam/apps/289070/manuals/CIV_VI_25TH_ONLINE_MANUAL_ENG.pdf)。它适合查整体规则；完整的风云变幻规则及单位例外应结合安装版本的文明百科文字和规则数据库。下面均核验于本机随游戏发行的原始文件，路径以安装目录为基准：

| 规则 | 本机第一手证据 | 实现含义 |
| --- | --- | --- |
| 潜行单位通常对超过一格距离的普通单位保持隐藏 | `Base/Assets/Text/en_US/Unit_Abilities_Text.xml:232`，`ABILITY_STEALTH` 说明 | 仅有格子视野不能放行。 |
| 侦隐能力可在视野范围内发现潜行单位 | 同文件 `:235`，`ABILITY_SEE_HIDDEN` 说明 | 不能将“只有相邻才可见”硬编码为全部规则。 |
| 潜艇、核潜艇、私掠船能被海军袭击者发现，且具有相应侦隐能力 | `Base/Assets/Text/en_US/Units_Text.xml:316`、`:319`、`:322` | 不对某几个潜艇型号写特殊白名单。 |
| 驱逐舰能在视野内发现海军袭击者 | 同文件 `:337`；`Base/Assets/Gameplay/Data/Units.xml:641` 的 `CLASS_REVEAL_STEALTH` 标签 | 以引擎当前实际探测结果为准。 |
| 侦察兵也有侦隐规则标签 | `Base/Assets/Gameplay/Data/Units.xml:590` | 可见性规则比“潜艇与驱逐舰”更广。 |
| 侦察单位的“伪装”晋升可赋予隐蔽 | `Base/Assets/Text/en_US/Promotions_Text.xml:427`；`Base/Assets/Gameplay/Data/UnitPromotions.xml:1043`、`:1659` | 普通单位类型也可能由于晋升而隐藏。 |
| 奥斯曼海盗具有潜行及侦隐标签 | `DLC/Expansion2/Data/Expansion2_Units_Major.xml:46`、`:47` | 扩展包新增单位无需改动检测代码。 |
| 间谍采用特殊可见性 | `Base/Assets/Gameplay/Data/Units.xml:769` 的 `Spy="true"`、`TeamVisibility="true"`；百科说明在 `Base/Assets/Text/en_US/Units_Text.xml:160` | 仍先调用 `IsUnitVisible`；不读取未被检测的间谍位置、任务、拥有者或存在数量。 |

这些公开文字用于解释规则和建立测试场景，不用于重新实现引擎中的探测算法。真实对局中具体能否看见某个潜行单位，始终由该玩家的 `IsUnitVisible` 决定。

本次核验的本机安装目录：`F:\SteamLibrary\steamapps\common\Sid Meier's Civilization VI`。以上行号对应开发时安装版本，游戏更新后需重新核对。

## 输出与失败方式

`visible_units_at` 再次验证 `IsRevealed(index) == true` 和 `IsVisible(index) == true`。获得单位容器后，在调用任何单位 getter 之前，要求 `IsUnitVisible(unit) == true`。包括拥有者和 ID 在内，未检测对象的所有属性都不读取。

返回记录的必需字段是 `id`、`owner_id`、`x`、`y` 和内部证明标记 `detected=true`。可选字段仅有 `type`、`name`、`damage`、`max_damage`、`combat`、`ranged_combat`。可见目标的血量与战斗数值取法可在 `Base/Assets/UI/Panels/UnitPanel.lua:3419` 的 `ReadTargetData_Unit` 中核验。字段缺失、类型异常或超限时省略该可选字段。

不返回外国单位剩余移动力、建造次数、传教次数、间谍任务、能力列表、晋升列表或其他内部状态。本方单位由本方观测接口处理，此列表仅保留外国单位。

- 单位检测 API 或容器 API 缺失、容器调用失败、地块门未通过时返回 `nil`，调用方应省略 `units` 字段，表示本次无法可靠提供该信息。
- 容器可检查，但没有通过检测且可输出的外国单位时返回空数组。它只表达“没有可以公开的单位记录”，不推断该格物理上没有单位。
- 单个单位检测返回假、非布尔值或抛错时跳过该单位，不返回错误详情、隐藏计数或过滤计数。
- 记录按公开拥有者 ID 和单位 ID 排序并去重，最多输出 256 个检测记录。隐藏对象不影响排序、截断或任何公开总数。
- 不维护单位检测缓存；每次请求重新询问引擎。单位失去探测后立即退出当前输出。

## 已验证与实机验收

`tests/test_visible_units.py` 在真实 Lua VM 中运行生成片段：隐藏单位的任何属性访问都会触发陷阱。测试覆盖普通隐藏单位、潜艇、伪装侦察单位、间谍、可见性变化、缺失 API、引擎异常、非法字段、重复对象、公开输出上限，以及加入 1000 个隐藏对象后公开结果不变。

这些测试证明适配器遵守引擎返回的检测门，并不冒充已在运行中的游戏里验证所有探测规则。实机验收仍应包括：可见海域的未发现潜艇、相邻后发现、海军袭击者/驱逐舰视野内发现、侦测者移开后消失、伪装晋升、间谍，以及同回合读档。验收时对照原版 UI；没有可信结果就继续省略单位，不启用距离猜测。

开发时读取上述程序和规则文件属于 API 核验。实际公平对局中的 AI 应仅获得本 MCP 工具权限，不能同时拥有任意 FireTuner、操作系统或存档访问权限；MCP 无法限制另一个具有这些权限的客户端。
