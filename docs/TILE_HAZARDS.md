# 当前可见地块的风暴与旱灾

`observe_area` 的可选地块字段：

| 字段 | 含义 |
| --- | --- |
| `storm_type` / `storm_name` | 当前覆盖该格的风暴类型 `RANDOM_EVENT_*` 与原版本地化名称 |
| `drought_type` / `drought_name` | 当前覆盖该格的旱灾类型与原版本地化名称 |
| `drought_turns` | 原版提示中的旱灾剩余回合，非负整数 |

只有原生类型接口明确返回 `-1` 才输出 `*_type: "NONE"`。缺少接口、接口异常、类型缺少有效静态定义时省略相应字段，不能把缺字段理解为没有灾害。名称和剩余回合也可以分别缺失；无活动旱灾时不读取剩余回合。

读取位于现有 `IsRevealed && IsVisible` 判断之内。已探索但当前在战争迷雾中的格子不读取或返回灾害信息，也不缓存之前的灾害状态。区域结果仅代表此次实际可见的格子，不代表灾害完整范围。实现不查询全局灾害列表、真实中心、未见覆盖范围、移动方向、预计路径、受影响城市或伤亡来源。

原版依据为 `DLC/Expansion2/UI/Replacements/PlotTooltip_Expansion2.lua:23–25` 的 `GameClimate.GetActiveStormTypeAtPlot(plot)`、`GetActiveDroughtTypeAtPlot(plot)`、`GetDroughtTurnsAtPlot(plot)`；同文件 `:215–220` 使用 `GameInfo.RandomEvents[type].Name` 显示标题。`Expansion2_InGameText.xml:584–585` 与中文翻译 `Expansion2_Translations_Text.xml:204608–204609` 明确说明旱灾回合值为剩余回合。项目的当前可见门槛继续严于原版工具提示的已探索门槛。

Lua 层验证静态类型、可选标题与回合数；Python 再执行字段白名单、类型与长度检查。定向回归覆盖不可见格访问陷阱、可见有效值、明确无灾害、接口缺失或异常、缺定义、可选字段失败及输出过滤。本批为离线实现，尚待实机出现当前可见风暴／旱灾时验收；不据此追认任何历史单位损失原因。
