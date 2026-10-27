# 世界排名侧栏的识别与退出

文化主导、文化胜利临近等通知可经现有 `activate_notification` 打开世界排名的文化页。本批增加固定 `world_rankings` 界面观察和一个正常关闭按钮，使该通知打开的侧栏有明确退出通路。

发现阶段同时要求固定上下文和其 `SlideAnim` 控件严格可见，路径为 `/InGame/PartialScreens/WorldRankings`（保留 `.xml` 变体及已有固定加载位置回退）。进入自身上下文后，再检查 `Controls.SlideAnim`、上下文及父链的实际可见性。上下文存在本身不代表侧栏展开；缺少或无法确认 SlideAnim 时不提供旧内容和按钮。

本批只返回“世界排名侧栏已打开”的状态文案、可见的固定标题 `Controls.Title` 和 `CloseButton`。不遍历排名控件树、其他标签页或缓存的文明条目，不调用原始排名／胜利数据 API，不读取未展示的其他文明统计。既有 `get_diplomacy` 公共数据范围不变。

唯一动作使用原版 `CloseButton` → `Close`，保留收起动画、关闭通知及镜头恢复；不通过强制隐藏上下文退出。打开／关闭事件只用于废弃旧按钮，不读取事件参数。其他模态窗口仍可阻止底层关闭操作。

原版在收起动画结束时才隐藏上下文，因此关闭请求接受后可能短暂仍显示该侧栏。调用者应重新观察，不把提交当作已经关闭，不自动重试旧按钮；本批也不把可见性当作动画完成证明。

## 原版依据与验证边界

本机安装目录：`F:/SteamLibrary/steamapps/common/Sid Meier's Civilization VI`。

- `Base/Assets/UI/Panels/NotificationPanel.lua:224–227,1356–1358,1691–1700`：相关通知和正常激活调用链。
- `Base/Assets/UI/PartialScreens/WorldRankings.lua:2410–2437,2537–2540,2593–2610,2620–2623`：原版侧栏显示／关闭、文化页入口、动画控制器、静态标题和关闭按钮绑定。
- `Base/Assets/UI/AnimSidePanelSupport.lua:37–44,50–59,79–83`：显示时取消上下文隐藏，关闭时反向动画，结束后隐藏上下文；不读取其私有 `m_state`。
- `DLC/Expansion2/UI/Replacements/InGame.xml:51–56`：PartialScreens 固定上下文路径。
- `DLC/Expansion2/UI/Replacements/WorldRankings.xml:6,32` 和 `Base/Assets/UI/Civ6_styles.xml:1850–1858`：SlideAnim、CloseButton、标题及侧栏层级。

本批使用模拟 UI 的 Lua VM 定向检查显示门、隐藏缓存不读、唯一原版关闭、旧按钮与模态保护、关闭动画期间的再次观察。没有连接游戏；尚未触发真实文化通知→排名侧栏→关闭流程，也没有重建现有 0.3.6 发布归档。

2026-10-27 定向回归为 **238 passed**，范围为 `test_world_rankings_ui.py`、`test_history_and_great_work_ui.py`、`test_popups.py`、`test_popup_sequences.py`、`test_ui_monitoring.py` 和 `test_waiting.py`。该数为本次指定测试文件的总数，不与先前 218 项或全套结果相加，不代表实机验收。
