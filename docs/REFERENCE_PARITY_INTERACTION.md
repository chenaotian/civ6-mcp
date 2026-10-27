# 参考项目交互、回合与终局对照

参考 [lmwilki/civ6-mcp](https://github.com/lmwilki/civ6-mcp) 的本地快照 `references/lmwilki-civ6-mcp-20261027/civ6-mcp-main`。本批仅读源码、开发并离线测试，没有连接游戏、启动进程、重载存档或运行参考项目的 AGENTS 指令。以下是功能对应关系，不表示两套工具参数兼容，也不把上游描述直接当作公平性保证。

| 参考能力／入口 | 当前对应与本批增量 | 有意保留的边界 |
| --- | --- | --- |
| `end_turn`：检查阻塞、等待并汇报 | `act({type:"end_turn"})` 单次提交；`get_pending_decisions`、自动 UI 采集、`wait_for_change` 继续观察。新增 `ui.next_steps` 查询建议 | 不自动跳过决策、不重发结束回合、不把 `submitted` 等同完成 |
| 回合前后快照与差分 | 新增 `wait.changes`，对相同查询的前后公开观察给最多 64 条差异 | 只存本方字段及少量 UI 元数据；不存地图／外国对象。消失原因不明，生产或研究切换不代表完成 |
| 回合处理中的外交或弹窗 | 既有固定 UI 与正常菜单在每次观察中返回当前可见正文及按钮；新建议不生成动作 | 不自动关闭宣战、强制退外交会话或跳过必选决策 |
| `dismiss_popup` | 已有 `popup_action` 使用当前观察返回的固定按钮和正常回调，覆盖历史、巨作、世界排名等 | 不使用通用 `SetHide`、任意 Lua、扫描未知上下文或补发关闭事件“清锁” |
| `get_game_overview` 内终局检查、`check_game_over` | `get_game_status` 和普通观察均加入固定本方终局证据；等待同样可返回终局 | 不枚举赢家身份、未遇文明或胜利统计；不猜胜利类型；终局不授动作令牌或观察者权限 |
| `GameOverWatchdog` | 在已请求的观察／等待中检测，不增加后台任务 | 不在用户暂停后持续轮询、不连接外部遥测或远程日志 |
| `get_diary` | 新增 `get_session_history(limit=20)`，最近 64 条会话内公开摘要，支持 1～64 的返回条数 | 非永久日志，不按种子或文明名读写文件，不存秘密身份、令牌、签名、按钮版本或动作参数；不保存上游的战略反思字段 |
| `list_saves` | 未引入 | 本轮用户负责开新局；不枚举电脑上的存档作为正常对局能力 |
| `load_save`、`load_game_save` | 未引入；既有观察会识别会话变化并废弃旧能力 | 不自动读档或回滚对局，尤其不使用截图／OCR 菜单兜底 |
| `kill_game`、`launch_game`、`load_save_from_menu`、`restart_and_load` | 未引入 | 不更改用户电脑环境、操作游戏进程或开启游戏外服务 |
| `run_lua` | 不对游戏 AI 提供 | 使用固定审计过的查询和动作，保留公平权限过滤 |
| 自动存档清理与完整回合日志上传 | 未引入 | 不删除文件、不开放公网监听、不向外发送对局数据 |

## 新增结果反馈

`ui.next_steps` 是只读建议数组。研究／市政指向 `list_options`，单位／生产指向本方状态，总督、宗教、伟人、使者、考古、间谍逃跑、世界议会和紧急事件指向相应 `inspect_game` 类别。不能确认的阻塞保留原名并指向 `get_pending_decisions`。可见弹窗仅提示使用本次提供的按钮，没有按钮时要求刷新；未知或不可读原生模态仍不授底层动作权限。忙碌提示指向有界等待，`idle` 不代表操作已完成。

`wait.changes` 使用已经过 Python 投影的字段。仅相同查询描述（含参数）、会话、玩家和连接代次可比较；新的普通查询替换基线，跨档或重连不输出差分。即使 Lua 会话标志未变，Python 检测到回合倒退也按 `session_changed` 清空历史和比较基线、移除能力，不跨档比较。只比较完整观察，世界读取失败转为 UI 恢复时不报“所有城市／单位消失”。字段缺失使用 `before_known`／`after_known`，不会补零。单位 ID 替换可能来自升级、合编、消耗或阵亡，因此只返回 `no_longer_observed`／`now_observed` 和 `cause=unknown`。研究、城市生产只报告字段变化，没有“完成”推断。具体协议见 [等待说明](WAITING.md)。

新增 `get_session_history` 在本服务内存中记录：读取类别、回合、活动标志、本方单位／城市数量、已投影的金币／信仰／当前研究和市政，以及 UI 状态、忙碌状态、阻塞名和弹窗 ID；动作只记公开 `type`、接受与提交／拒绝状态，明确 `completion=not_asserted`。连续相同摘要合并，最多保留 64 条，返回副本。该工具不访问游戏，也不产生、消耗或替换已有动作令牌。

历史在服务关闭、读取不可用、已知连接代次变化时清空；新观察确认读档／换玩家／回合倒退时先清空再记录。**纯内存读取无法主动发现尚未观察到的外部读档**，因此返回范围明确为 `current_observed_session_memory` 并标记 `history_only_take_fresh_observation_before_acting`。服务重启后历史为空；它不是持久日记、事实事件总账或恢复旧能力的机制。

## GameOver 修正

原实现把 `Game.GetWinningTeam()` 的任何非 nil 返回都视为有胜者，因而将正常的 `-1` 误判为结束。本批仅接受整数 0～63 为确认的胜利队伍；`-1`／nil 为未报告胜者，非法返回失败关闭。只将其与本方队伍比较，保留现有公共枚举：本方胜利 `victorious`、他方胜利 `finished`、本方淘汰 `defeated`。不返回赢家身份或胜利类型。

若没有确认胜者但固定 `/InGame/EndGameMenu` 严格可见，则保守返回 `finished`，原因 `end_game_screen_visible`；不把它解释为本方获胜，也不读赢家列表、排名、图表或回放。不会仅因达到配置回合上限就推定结束。结束页不可读、隐藏或返回非布尔值均不能成为该分支的证据。

专用终局读取不再要求视野对象或活动回合 UI 仍存在；缺失活动信息只会使 `active_turn=false`，不会授予能力。单人、本方控制器、非观察者、非自动代打与会话事件门仍保留。普通观察 envelope 提供同一终局证据，服务检测后仅返回终局状态，不继续公开业务数据或弹窗动作；区域预览和询价这两条多上下文读取也在第一段观察确认终局时停止，不再访问第二业务上下文。该增量没有新增传输调用；淘汰后的普通查询仍通过既有失败恢复进入专用终局读取。

可选 `status_reason` 只允许 `local_player_eliminated`、`winning_team_confirmed`、`end_game_screen_visible`。最终结果仍需以观察得到的状态为准；动作回执维持原来的 `submitted`／`rejected`。

## 源码依据与测试

参考项目位置：`src/civ_mcp/end_turn.py:492,1112,1437,1454`；`game_state.py:125,1424,1467`；`game_lifecycle.py:13`；`game_over_watchdog.py`；`lua/overview.py:179,239`；`server.py:2218,2691,2702,2730–2820`。特别没有照搬其差分中“单位缺失即被杀”“研究切换即完成”的因果推断，也没有照搬终局启发式的全玩家扫描和回合上限推断。

本机官方源码依据：`Base/Assets/UI/ActionPanel.lua:99–115` 的阻塞枚举；`DLC/Expansion2/UI/Replacements/ActionPanel_Expansion1.lua:23–28`、`ActionPanel_Expansion2.lua:19–20` 的资料片阻塞；`DLC/Expansion2/UI/Replacements/InGame.xml:131` 的固定结束页；`Base/Assets/UI/EndGame/EndGameMenu.lua:1035–1055,1066–1087` 的胜利事件与结束页展示；`:462,1074` 的胜利队伍读取。新增代码独立实现，没有执行参考项目脚本。

2026-10-27 定向离线结果：**501 passed，4.80 秒，退出码 0**。范围见 [交互增量验证记录](../artifacts/reference-interaction-validation-2026-10-27.json)。包含实际生成 Lua → Python service 的结束回合提交、等待、终局与历史记录链，严格终局值、缺失视野／UI、控制器门、无隐藏数据差分、跨档重连、同会话回合倒退、终局多上下文短路、摘要上限、动作令牌、弹窗及等待回归。不是新的全套结果，也没有与此前测试数字相加。本批尚未做新局实机验证，本领域完成时未单独重建发布包；整合后的 0.4.0 发布结果以总报告为准。
