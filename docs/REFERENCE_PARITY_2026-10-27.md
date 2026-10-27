# civ6-mcp 功能对照与本批交付

本报告记录 **0.4.0 的历史交付与验证**。后续用户明确要求引入 `run_lua` 备用接口，当前设计草案记录于 [备用 Lua 接口](FALLBACK_LUA.md)，尚未完成实现和验证；它拟仅用于常规接口无法解决的游戏问题，不能继承普通字段投影的自动公平保证。下表原有“未纳入”结论及 0.4.0 测试数字保留为当时记录，不包含备用接口的后续工作。

对照日期：2026-10-27。参考仓库：[lmwilki/civ6-mcp](https://github.com/lmwilki/civ6-mcp/tree/dd2019056371b92ea4854e879ddf05a8cad95e8a)，固定提交 `dd2019056371b92ea4854e879ddf05a8cad95e8a`。ZIP 自带提交标识；文件 SHA256 为 `4b10ec3fc9e27078eaacd9cc187259e393fd8a55a1ef67052661dfa7b8969418`。只读取源码，没有执行参考项目。

从 `server.py` 的 MCP 装饰器提取 **76 项工具**，以下逐项覆盖；比较实际能力，不用公开工具数量衡量实现多少。本项目以少量固定工具加分类查询和动作提供对应能力。表中的“等价”表示接口能力对应，不表示所有场景均已实机验证；本批不继续当前游戏。

- 领域依据和新增内容：[单位／规划](REFERENCE_PARITY_UNITS.md)、[内政／宗教／伟人](REFERENCE_PARITY_EMPIRE.md)、[外交／探索](REFERENCE_PARITY_DIPLOMACY.md)、[回合／终局／历史](REFERENCE_PARITY_INTERACTION.md)。
- 可机读清单：[reference-parity-2026-10-27.json](../artifacts/reference-parity-2026-10-27.json)。
- 既有实机记录继续保留，最后停在第128回合；本批新功能只做离线验证，等待用户创建新局。

## 逐项对照

| 上游工具 | 对照结果 | 本项目入口 | 说明 |
| --- | --- | --- | --- |
| `get_game_overview` | 等价+补充 | get_player_state / get_game_status / dedications / governors | 分类查询本方概况；本批补时代阈值、终局诊断。 |
| `get_units` | 等价 | get_player_state / unit_details / unit_neighbors / own_trade_routes | 自身单位、状态、检测通过的邻近单位、商人总览。 |
| `get_spies` | 等价 | spy_overview / spy_destinations / spy_missions；spy_travel / spy_mission / spy_escape | 原版菜单准入，雾中菜单目标不额外披露实时城市。 |
| `spy_action` | 等价 | spy_overview / spy_destinations / spy_missions；spy_travel / spy_mission / spy_escape | 原版菜单准入，雾中菜单目标不额外披露实时城市。 |
| `get_cities` | 等价+补充 | get_player_state / city_status | 本批补城防血量和忠诚变化方向、倒计时。 |
| `get_city_production` | 等价 | list_options(production) / city_production / city_queue | 正常生产资格、报价、进度和队列。 |
| `get_map_area` | 等价+补充 | observe_area | 本批补公开移动成本、道路、魅力、防御；继续过滤迷雾与隐藏资源。 |
| `get_settle_advisor` | 玩家权限替代 | unit_recommendations / exploration_frontier / observe_area | 新增原版开拓者推荐和探索边缘，不复制全世界城市距离、雾中实时评分；规划判断交给AI。 |
| `get_pathing_estimate` | 玩家权限替代 | unit_move_preview / unit_neighbors / queue_move | 本批补受限的当前可见路径摘要；不能预告隐蔽阻挡或把排队移动当作抵达。 |
| `get_global_settle_advisor` | 玩家权限替代 | unit_recommendations / exploration_frontier / observe_area | 新增原版开拓者推荐和探索边缘，不复制全世界城市距离、雾中实时评分；规划判断交给AI。 |
| `get_builder_tasks` | 玩家权限替代 | unit_recommendations / unit_actions / observe_area | 新增原版建造者推荐改良位置；不硬编码自动评分。行动仍重新验证规则。 |
| `get_empire_resources` | 玩家权限替代 | own_resources / own_luxuries / observe_area | 库存、上限、收支和可见已解锁资源；不扫fog实时位置或原始未解锁资源。 |
| `get_strategic_map` | 玩家权限替代 | exploration_frontier / observe_area | 新增有界分页探索边缘与原版地图信息；不返回隐藏地形或未知身份。 |
| `get_diplomacy` | 等价+补充 | get_diplomacy / diplomacy_actions | 本批补公开关系、情报等级、不满、协定、同盟类型等级点数等。 |
| `get_tech_civics` | 等价 | get_player_state / list_options(research,civic) | 本方当前研究、可研究科技/市政、成本、进度、提升条件。 |
| `get_pending_trades` | 等价 | diplomacy_sessions / deal_state | 签名绑定当前完整来价；不把缓存草稿当新报价。 |
| `get_policies` | 等价 | government；set_policies / change_government / unlock_policies | 配置全部卡槽，正常可选政体与政策校验。 |
| `get_notifications` | 等价 | get_pending_decisions | 只读未忽略通知；激活/关闭需重查。 |
| `get_pending_diplomacy` | 等价 | diplomacy_sessions；diplomacy_respond / diplomacy_close | 真实捕获本地对话，可选回答及当前会话签名。 |
| `get_governors` | 等价 | governors / governor_city_state_destinations；governor_appoint / governor_assign / governor_promote | 普通总督及可用结社，含城邦派驻。 |
| `appoint_governor` | 等价 | governors / governor_city_state_destinations；governor_appoint / governor_assign / governor_promote | 普通总督及可用结社，含城邦派驻。 |
| `assign_governor` | 等价 | governors / governor_city_state_destinations；governor_appoint / governor_assign / governor_promote | 普通总督及可用结社，含城邦派驻。 |
| `promote_governor` | 等价 | governors / governor_city_state_destinations；governor_appoint / governor_assign / governor_promote | 普通总督及可用结社，含城邦派驻。 |
| `get_unit_promotions` | 等价 | unit_promotions；unit_promote | 普通晋升选项和请求。 |
| `promote_unit` | 等价 | unit_promotions；unit_promote | 普通晋升选项和请求。 |
| `get_city_states` | 等价 | city_states；city_state_envoy | 使者、匿名未知竞争者、奖励、本方任务、宗主；另支持征召。 |
| `send_envoy` | 等价 | city_states；city_state_envoy | 使者、匿名未知竞争者、奖励、本方任务、宗主；另支持征召。 |
| `get_pantheon_beliefs` | 等价 | religion；found_pantheon / found_religion / add_belief | 正常万神殿/宗教/信条选择和可用资格。 |
| `choose_pantheon` | 等价 | religion；found_pantheon / found_religion / add_belief | 正常万神殿/宗教/信条选择和可用资格。 |
| `get_religion_beliefs` | 等价 | religion；found_pantheon / found_religion / add_belief | 正常万神殿/宗教/信条选择和可用资格。 |
| `found_religion` | 等价 | religion；found_pantheon / found_religion / add_belief | 正常万神殿/宗教/信条选择和可用资格。 |
| `upgrade_unit` | 等价 | unit_actions / unit_command | 正常单位升级按钮，报价与能力由原版规则校验。 |
| `get_dedications` | 等价+补充 | dedications；choose_dedications | 本批补时代分数、黄金/黑暗阈值、当前献力。 |
| `choose_dedication` | 等价+补充 | dedications；choose_dedications | 本批补时代分数、黄金/黑暗阈值、当前献力。 |
| `get_trade_options` | 等价 | deal_options / deal_state / deal_negotiation / war_deal_options；deal_* / diplomacy_statement | 分步编辑/平衡/发送/明确接受完整报价，含和平、同盟与联合战争。无隐藏AI估值。 |
| `respond_to_trade` | 等价 | deal_options / deal_state / deal_negotiation / war_deal_options；deal_* / diplomacy_statement | 分步编辑/平衡/发送/明确接受完整报价，含和平、同盟与联合战争。无隐藏AI估值。 |
| `propose_trade` | 等价 | deal_options / deal_state / deal_negotiation / war_deal_options；deal_* / diplomacy_statement | 分步编辑/平衡/发送/明确接受完整报价，含和平、同盟与联合战争。无隐藏AI估值。 |
| `propose_peace` | 等价 | deal_options / deal_state / deal_negotiation / war_deal_options；deal_* / diplomacy_statement | 分步编辑/平衡/发送/明确接受完整报价，含和平、同盟与联合战争。无隐藏AI估值。 |
| `set_policies` | 等价 | government；set_policies / change_government / unlock_policies | 配置全部卡槽，正常可选政体与政策校验。 |
| `respond_to_diplomacy` | 等价 | diplomacy_sessions；diplomacy_respond / diplomacy_close | 真实捕获本地对话，可选回答及当前会话签名。 |
| `send_diplomatic_action` | 等价 | diplomacy_actions；diplomacy_statement | 原版选项授权的主动外交。 |
| `form_alliance` | 等价 | deal_options / deal_state / deal_negotiation / war_deal_options；deal_* / diplomacy_statement | 分步编辑/平衡/发送/明确接受完整报价，含和平、同盟与联合战争。无隐藏AI估值。 |
| `city_action` | 等价 | city_combat / city_tiles / city_queue；city_attack / city_manage_citizen / city_set_focus / city_fate | 按领域行动接口，无通用引擎调用。 |
| `unit_action` | 等价 | unit_actions / unit_targets / unit_formations；unit_order / unit_target / melee_attack / unit_command | 常规及特殊单位任务、工程建造、军队、空军等均需正常引擎资格。 |
| `skip_remaining_units` | 等价（逐单位） | get_player_state / unit_actions；unit_order | 对每个本方就绪单位使用原版跳过；不强制结束回合。 |
| `set_city_production` | 等价 | city_production / city_placement；city_build / city_build_at | 区域、奇观选址及普通生产。 |
| `purchase_item` | 等价 | city_production；city_purchase / city_purchase_at | 金币/信仰购买及需要位置的项目。 |
| `set_research` | 等价 | list_options；set_research / set_civic | 当前可选科技/市政，提交后再观察。 |
| `end_turn` | 等价+补充 | get_pending_decisions；end_turn；wait_for_change | 本批补有界公开变化摘要、阻塞下一步提示、终局察觉。无后台无限等待。 |
| `get_diary` | 有界会话替代 | get_session_history | 本批新增64条内存观察/提交摘要，无token；重连/读档清空，非跨游戏永久日记。 |
| `get_trade_routes` | 等价+补充 | own_trade_routes | 当前本方容量、运行路线、空闲商人、端点；本批补正常收益明细。 |
| `get_trade_destinations` | 等价 | trade_destinations / trade_routes；trade_route / transfer_trader | 原版菜单显示的雾中目的地允许返回，收益与行动重新校验。 |
| `get_district_advisor` | 玩家权限替代 | city_placement / district_preview | 原版合法选址和当前预览相邻加成；不读雾中邻格/隐藏资源或评分。 |
| `get_wonder_advisor` | 玩家权限替代 | city_placement / observe_area | 正常奇观选址，已有可见设施/资源信息可供AI权衡。未复制手工替换代价评分。 |
| `get_purchasable_tiles` | 等价 | city_tiles；city_purchase_plot | 本方正常购地菜单及价格。 |
| `purchase_tile` | 等价 | city_tiles；city_purchase_plot | 本方正常购地菜单及价格。 |
| `change_government` | 等价 | government；set_policies / change_government / unlock_policies | 配置全部卡槽，正常可选政体与政策校验。 |
| `get_great_people` | 等价+补充 | great_people | 本批补本方类别点数/增长、未能支付也显示的原版赞助报价。 |
| `get_gp_advisor` | 玩家权限替代 | special_unit_sites / unit_actions | 本批补原版伟人激活地点高亮，另有摇滚演出地点；不硬编码城市评分。 |
| `recruit_great_person` | 等价+修正 | great_person_recruit / great_person_patronize / great_person_pass | 本批按原版互斥按钮条件修正已可招募/放弃时的赞助权限。 |
| `patronize_great_person` | 等价+修正 | great_person_recruit / great_person_patronize / great_person_pass | 本批按原版互斥按钮条件修正已可招募/放弃时的赞助权限。 |
| `reject_great_person` | 等价+修正 | great_person_recruit / great_person_patronize / great_person_pass | 本批按原版互斥按钮条件修正已可招募/放弃时的赞助权限。 |
| `get_world_congress` | 等价 | world_congress；congress_ballot / congress_propose / congress_acknowledge | 完整选票和支持成本先校验再提交；紧急事件另有emergencies。 |
| `queue_wc_votes` | 等价 | world_congress；congress_ballot / congress_propose / congress_acknowledge | 完整选票和支持成本先校验再提交；紧急事件另有emergencies。 |
| `get_victory_progress` | 玩家权限替代+补充 | get_diplomacy / own_science_victory | 本批补本方项目完成/在建/成本/进度。对手仅已证实公开汇总，不全图统计。 |
| `get_religion_spread` | 玩家权限替代+补充 | city_religion / visible_city_religion | 本批新增本方及当前可见已遇见城市的信徒分布/转换预测；不扫fog。 |
| `set_city_focus` | 等价 | city_set_focus | 本方城市正常产出侧重与避免增长。 |
| `dismiss_popup` | 等价（更细） | get_pending_decisions / ui；popup_action | 读真实可见正文和按钮，对精确当前弹窗响应；不盲按ESC跳过选择。 |
| `run_lua` | 不纳入玩家接口 | 无 | 任意Lua会绕过玩家信息过滤，与公平游戏目标冲突。 |
| `list_saves` | 不纳入本批 | 用户从游戏菜单开新局；MCP连接已运行对局 | 宿主生命周期/存档管理及OCR，不是缺少游戏内行动；不自动杀进程、读档改局、删存档或改电脑环境。 |
| `load_save` | 不纳入本批 | 用户从游戏菜单开新局；MCP连接已运行对局 | 宿主生命周期/存档管理及OCR，不是缺少游戏内行动；不自动杀进程、读档改局、删存档或改电脑环境。 |
| `load_game_save` | 不纳入本批 | 用户从游戏菜单开新局；MCP连接已运行对局 | 宿主生命周期/存档管理及OCR，不是缺少游戏内行动；不自动杀进程、读档改局、删存档或改电脑环境。 |
| `kill_game` | 不纳入本批 | 用户从游戏菜单开新局；MCP连接已运行对局 | 宿主生命周期/存档管理及OCR，不是缺少游戏内行动；不自动杀进程、读档改局、删存档或改电脑环境。 |
| `launch_game` | 不纳入本批 | 用户从游戏菜单开新局；MCP连接已运行对局 | 宿主生命周期/存档管理及OCR，不是缺少游戏内行动；不自动杀进程、读档改局、删存档或改电脑环境。 |
| `load_save_from_menu` | 不纳入本批 | 用户从游戏菜单开新局；MCP连接已运行对局 | 宿主生命周期/存档管理及OCR，不是缺少游戏内行动；不自动杀进程、读档改局、删存档或改电脑环境。 |
| `restart_and_load` | 不纳入本批 | 用户从游戏菜单开新局；MCP连接已运行对局 | 宿主生命周期/存档管理及OCR，不是缺少游戏内行动；不自动杀进程、读档改局、删存档或改电脑环境。 |

## 有意保留的区别

上游全局顾问、路径与胜利统计的输出并非全部符合本项目的玩家视角。例如 revealed 城市实时状态、未知文明枚举、全世界城市距离和隐蔽战略资源信息不能因上游能读就直接开放。已用原版菜单推荐、合法选址预览、可见地图、公开胜利汇总和探索边缘提供可用替代。AI 可以据此规划，不额外获得游戏未给玩家的信息。

保留一个动作一次提交与新观察再确认；`submitted` 从不当成已经成功。不同于上游的一键恢复流程，本批不提供任意Lua、自动结束进程、OCR导航或自动覆盖/载入存档。这些排除项已在表中逐项列明。

## 验证

最终完整离线回归：**3211 passed，19 subtests passed，26.05 秒，退出码 0**。记录：[完整验证与源码摘要](../artifacts/reference-full-validation-0.4.0-2026-10-27.json)。包含真实生成 Lua 的执行、权限投影、服务状态机、临时回环 TCP 分片／异常／取消、真实 MCP SDK stdio 客户端握手和新工具调用。分项数字不与整套相加。

整批运行定位并修正了两处旧 TCP 测试夹具的调度不稳定：分片测试原 0.5 秒预算接近 Windows 实测 0.48 秒；动作超时测试原 0.06 秒预算包含建连，可能尚未发送动作便超时。现在分片测试给足调度余量，动作超时测试先完成正常观察建连，再在有界超时内验证只提交一次。**生产连接超时和不重放语义未改。**

当前提供 **11 个 MCP 工具、51 个分类查询、84 种动作类型**；数量只是组织方式，不代表已触发所有游戏场景。发布版本 **0.4.0**，重新生成 wheel 和源码包；最终包校验记录：[发布校验](../artifacts/release-validation-0.4.0-2026-10-27.json)。包内保留参考项目 MIT 授权，不打入下载参考仓库、对局记录、虚拟环境或临时测试产物。

本批没有连接、推进、重新加载或关闭游戏，也没有修改系统设置或删除文件。新局仍需实测：推荐与长程路径、宗教变化、伟人／摇滚地点、活动商路收益、复杂外交以及最终胜负界面。已有弹窗流程的历史实机记录仍有效，但不能用它证明这批新增分支已实机通过。
