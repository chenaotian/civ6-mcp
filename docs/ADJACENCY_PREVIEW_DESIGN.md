# 区域相邻加成预览：实现与验证边界

固定 context 和必要 API 的能力检查已在同局 T88 通过。T94 首次开启请求虽被提交，后续仍返回 `not_active`，未取得标签；没有阻塞正常游戏。v2 按原版流程拆分选城与选址后，**T98 已完成奎拉学院的选城、开启、读取两处标签及正常取消实测**。返回内容仅限玩家正常选址界面已经显示的标签，避免直接开放可能包含未解锁资源或迷雾影响的底层地块产出。普通地图过滤保持不变。

## 使用方式

`inspect_game("district_preview", {"city_id": 7, "item": "DISTRICT_CAMPUS"})` 在尚未选中目标城时只提供 `district_preview_select_city`；该动作会改变当前选城。之后重新观察，确认原版选城事件完成、目标城已选且处于普通选择模式，才提供 `district_preview_begin`。开启动作不再重新选城。再次查询，仅返回此次自然刷新中可确认的可见标签。`plot:x:y` 的 `value` 是原版文本，另有 `:x`、`:y` 坐标条目。`district_preview_cancel` 可结束预览或清除待定选城意图；实际建造仍使用既有 `city_build_at`。

`supported=false`、`awaiting_refresh` 或缺失标签表示未取得可靠标签，不能视为零。只读查询不装观察器、不打开界面、不触发刷新，也不补算任何原始相邻产出。第一版不提供未购地块、购买选址、奇观或已有区域镜头的标签。异常断连后，新服务可在同一查询中提供 `district_preview_exit_current`；它只按新观察确认的本方城市、区域 Hash、选址模式、镜头层及无模态条件正常取消，不读取或继承旧标签。

## 源码依据

以下路径均相对于 Civ VI 安装目录。

| 源码 | 已确认行为 |
| --- | --- |
| `Base/Assets/UI/Panels/ProductionPanel.lua:377–397` | 普通区域按钮设置 `DISTRICT_PLACEMENT` 模式及区域 Hash，然后关闭生产面板；此分支不提交建造。 |
| `Base/Assets/UI/WorldView/CityBannerManager.lua:998–1000` | 本方城市选择使用 `UI.SelectCity(city)`。 |
| `Base/Assets/UI/StrategicView_MapPlacement.lua:272–348` | 进入选址模式后原版生成合法候选，并开启 `DistrictPlacement` 镜头层。 |
| `Base/Assets/UI/AdjacencyBonusSupport.lua:279–326` | 候选来自正常 `GetOperationTargets(BUILD).PLOTS`，另加符合条件的购地候选；明确不使用 `BLOCKED_PLOTS`。 |
| `Base/Assets/UI/WorldView/DistrictPlotIconManager.lua:49–57,124–154` | 原版以 `plotIndex` 获取实例，再设置 `BonusText`，私有 `m_MapIcons` 保存位置绑定。 |
| `Base/Assets/UI/InstanceManager.lua:189–203` | 回收实例只隐藏控件，旧属性仍保留；非空文字不证明属于当前预览。 |
| `Base/Assets/UI/StrategicView_MapPlacement.lua:350–356` | 离开选址恢复生产面板，不提交建造。 |

`AdjacencyBonusSupport.lua:177–218` 将 `plot:GetAdjacencyYield(localPlayer, cityID, district.Index, yield.Index)` 的正数结果直接显示。Lua 层没有邻格视野或资源解锁过滤；随游戏安装的源码不足以证明 native 是否过滤。GS 工业区规则明确包含战略资源类别（`DLC/Expansion2/Data/Expansion2_Districts.xml:69,89`），所以六邻格可见也不能证明资源已解锁。

完整辅助函数还会读取魅力并计算住房（`AdjacencyBonusSupport.lua:225–247`）。`GetAdjacencyBonusType` 带资源或类别 subtype，不等同于地图上通用图标。上述原始值、tooltip 和原始地块产出均不直接开放。奇观分支主动隐藏并清空加成标签（`DistrictPlotIconManager.lua:159–179`），不补造奇观相邻加成。

## 实现约束

1. **显式分步开启。** 单独选择本方城市并观察选城完成。开启时重新验证本城已选、当前可建造且尚未放置的区域，仅使用正常 `UI.SetInterfaceMode(DISTRICT_PLACEMENT, parameters)`，再通过 `LuaEvents.CityPanel_ProductionClose()` 关闭生产面板（`ProductionPanel.lua:2319–2322,2981`）。这些均为显式可撤销界面动作，不藏在只读查询或事件回调中，也不调用 `RequestOperation`。原版 `CityPanel.lua:604–637` 的选城回调、`ProductionPanel.lua:593–605` 的打开流程都会恢复选择模式；它们是 T94 现象的候选来源，但日志不足以确认具体时序。
2. **仅观察原版生成的绑定。** 在固定 `DistrictPlotIconManager` UI context 内包装全局 `GetInstanceAt`，只记录原版自然调用返回的控件与 `plotIndex`，不主动调用此函数。它缺失实例时会创建控件，不能当作只读 lookup。
3. **完成刷新后才发布。** 同时观察 `Realize2dArtForCityDistricts`，在原函数正常返回后发布本次完整绑定。`GetInstanceAt` 返回时原版尚未执行 `SetText`，提前读取可能拿到池化旧文字。包装器不得改变原函数返回值、错误行为或渲染流程；观察器自身失败仅停用预览。
4. **后续查询只读可见标签。** 核对本次刷新代号、回合、连接、选中城市、区域 Hash、选址模式及镜头层。只读当前绑定、从标签到 context 全祖先均可见的 `BonusText:GetText()`，返回有长度限制的原版标签文字及已验证坐标。不得返回控件对象、tooltip、资源 subtype 或未显示值；缺失标签不等于零。
5. **及时失效和取消。** 换城、换区域、离开模式、换回合、断连、刷新失败均废弃快照；实例重复绑定或新旧代号不符时拒绝返回。取消仅使用正常 `UI.SetInterfaceMode(SELECTION)`，不请求建造或购买。

观察器仅在显式选城准备或开启时安装。它在原版刷新入口先清旧批次，成功返回后才发布；保留原函数的所有返回值、空位和异常。固定事件处理负责失效，取消后包装器保持惰性，不覆盖原版关闭处理或其他后来安装的函数。客户端身份与连接代号参与读取校验；正常服务关闭清除自己的观察数据，只有身份、城市、区域、模式、镜头层和普通回合状态仍匹配且没有弹窗时恢复选择模式。若玩家已经打开其他界面，取消只清观察意图，不关闭玩家的新界面。异常断连不会自动重试 UI 动作；使用新观察提供的显式恢复动作退出后才重新开启，旧标签不能跨连接读取。原版选城/购买事件先调用 `ClearEveything` 再刷新，因此后执行的观察事件不会清掉同一事件刚完成的新批次；直接释放实例的 `LensLayerOff` 则单独失效。

v2 可在同一局中退役精确匹配且空闲的自有 v1 观察器。v1 未公开保存原函数，只能保留其闭包为一层惰性转发，旧观察数据清空，原版函数仍只调用一次；不读取 upvalue 或重载 UI。v2 显式保留原引用，重复开启不会继续叠层。遇到仍活动的旧观察器先显式取消，遇到非匹配函数拒绝升级。固定只读诊断脚本只输出阶段 bool/null，不返回异常文本、标签或世界数据。

第一版严格限制为：**本方城市已购、当前可见、属于正常 `GetOperationTargets(BUILD).PLOTS` 且通过既有 `city_placement` 可建造检查的区域候选**。暂不扩展未购地块、购买选址、奇观、已有区域镜头或第三方模组。相邻地块不直接读取；即使底层计算包含不可见因素，返回内容也仅限原版当前实际显示的标签。

失效同时参考原版事件参数：本城取消选中、选中另一城或另一玩家、离开 `DISTRICT_PLACEMENT` 即撤销意图，即使 getter 暂时仍返回旧值也不能复用。`Adjacency_Bonus_Districts` 和 `Empire_Details` 的关闭事件都会清理同一个实例池，因此两者均失效（`DistrictPlotIconManager.lua:256–295`）。

## 已实测与待验证范围

- 固定 `DistrictPlotIconManager` context 已通过 T88 能力探针，传输只新增这一个固定 context。探针仅验证类型和身份，未读取标签，也不能代替完整流程验证。
- 升级前的固定只读状态探针确认 v1 空闲、自有包装函数仍匹配、当前处于 `SELECTION`，未读取标签。T98 在同一局加载 v2 后，显式 `select_city(393221)` 提交成功，重新查询得到 `begin`；单独开启后返回 `visible_labels`。
- 本次奎拉学院返回两个坐标绑定：`(10,24)` 的原版文字为 `[ICON_Science][COLOR:ResScienceLabelCS]+4[ENDCOLOR]`，`(11,23)` 为 `[ICON_Science][COLOR:ResScienceLabelCS]+2[ENDCOLOR]`。这确认本次正常刷新及可见父链检查通过，未绕过观察器补算数值。
- 正常 `cancel` 提交后，重新查询为 `not_active` 且只提供重新开启，旧 `plot:*` 标签消失。预览前后金币均为 `360.546875`，奎拉仍生产 `UNIT_TRADER`、剩余 `6` 回合；本次没有提交区域建造。公开日志依据为 `artifacts/continuous-035-2026-10-27/journal.jsonl` 第 1967、1969～1977 行，亦见[持续对局记录](LIVE_TEST_035_2026-10-27.md)。
- 尚未完成实机覆盖：断连恢复、切城与换区域、零标签、实例复用、其他区域及不同地形，尤其临近迷雾或未解锁资源的情形。这些边界保留既有过滤和离线回归，不能由本次学院成功推定全部通过。

能力缺失或无法确认绑定时仍返回不支持，不自动退回原始 `GetAdjacencyYield`。T94 首次失败的具体事件时序仍未确证；T98 成功不构成对该原因的反向证明。

本机 Lua 未找到可据以实现的 WorldAnchor 位置 getter 或跨 context `Call` 先例。控件 XML 没有地块编号，相关 manager 也不设置 Void 编号，因此不能按控件遍历顺序、候选表 `pairs` 顺序或默认 Void 值推断坐标。

不引入上述观察器时，可依据已有公平地图数据提供公开山脉、雨林等规则分项，但必须标为不完整估计；尚未证明能覆盖文明、政策及其他修正的完整静态子集，不能将其称为总预览或下界。
