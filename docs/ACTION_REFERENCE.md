# 常规动作参考（0.4.3）

以下 84 种动作通过同一个 MCP 方法提交：

```text
act(observation_token=最近一次观察返回的令牌, action={"type": 动作名, ...该动作的参数})
```

这些动作类型不是 84 个独立 MCP 方法。先用 `get_rules()` 查看当前版本的动作参数，再用 `list_options`、`inspect_game` 或 `get_pending_decisions` 取得当前合法选项；优先直接使用返回的 `action` 对象。参数表与 0.4.3 定义一致，具体 ID、标识符、坐标、索引及可选值均应来自当前公开观察或游戏菜单，不应猜测。

每次 `act` 使用并消耗最新观察令牌。`submitted` 只表示请求已提交，不表示移动、购买、战斗或其他效果已完成；调用后重新观察。发生超时或结果未知时，先确认当前状态，不直接重发。

参数约定：`id`／`integer` 为整数 ID 或索引，`coord` 为整数坐标，`bool` 为布尔值，`text` 为文本，`identifier:前缀` 为指定前缀的游戏标识符，`enum:a|b` 为枚举。列表和对象按表中结构填写；除 `type` 外所列字段按当前工具契约提供。无参动作的 `action` 仍需 `type`。

单位晋升、宗教单位操作等是否可用取决于当前规则、单位资格和正常菜单。下表列的是已提供的请求能力，不表示所有场景均已实机验证。

## 回合与科研

| `action.type` | 参数 | 功能 |
| --- | --- | --- |
| `set_research` | `{"technology": "TECH_* from list_options(research)"}` | 选择当前可研究的科技。 |
| `set_civic` | `{"civic": "CIVIC_* from list_options(civic)"}` | 选择当前可研究的市政。 |
| `end_turn` | `无` | 在普通结束回合条件满足时请求结束当前回合，不跳过必选决策。 |

## 单位、战斗与建设

| `action.type` | 参数 | 功能 |
| --- | --- | --- |
| `move` | `{"unit_id": "integer", "x": "integer", "y": "integer; adjacent tile only"}` | 将本方单位移动到相邻地块。 |
| `queue_move` | `{"unit_id": "id", "x": "coord", "y": "coord"}` | 向已探索地块下达一个普通远程移动目标；提交后查看单位位置与排队目的地，不保证立即到达。 |
| `fortify` | `{"unit_id": "integer"}` | 让符合条件的本方单位驻扎。 |
| `found_city` | `{"unit_id": "integer"}` | 让开拓者在当前位置建立城市。 |
| `build_improvement` | `{"unit_id": "integer", "improvement": "IMPROVEMENT_*"}` | 让单位在当前位置建造指定改良设施。 |
| `build_adjacent_improvement` | `{"unit_id": "id", "improvement": "identifier:IMPROVEMENT_", "x": "coord", "y": "coord"}` | 让单位在合法的相邻位置建造指定改良设施。 |
| `unit_order` | `{"unit_id": "id", "order": "enum:sleep\|skip\|heal\|rest_repair\|alert\|explore\|pillage\|pillage_route\|chop\|harvest\|repair\|repair_route\|build_route\|remove_improvement\|plant_forest\|clear_contamination\|excavate\|national_park\|rock_concert\|spread_religion\|remove_heresy\|launch_inquisition\|religious_heal\|convert_barbarians\|retrain\|activate_prophet\|evangelize_belief\|upgrade_operation"}` | 执行当前位置的单位指令：休眠、跳过、治疗、警戒、探索、掠夺、砍伐、收获、修复、修路／铁路、植树、清理污染、考古、国家公园、摇滚演出或宗教操作等；使用菜单实际提供的 order。 |
| `unit_command` | `{"unit_id": "id", "command": "enum:wake\|cancel\|stop_automation\|upgrade\|delete\|gift\|exit_formation\|activate_great_person\|district_production\|building_production\|wonder_production\|project_production\|harvest_wonder\|spread_dissent\|condemn_heretic\|plunder_trade_route\|pet_dog"}` | 执行唤醒、取消、停止自动化、升级、解散、赠送、解除编队、激活伟人、贡献生产力等单位命令；delete 会解散单位，伟人激活可能消耗次数。 |
| `unit_promote` | `{"unit_id": "id", "promotion": "identifier:PROMOTION_"}` | 为本方单位选择当前可用的晋升。 |
| `unit_rename` | `{"unit_id": "id", "name": "text"}` | 为符合命名条件的本方单位改名。 |
| `unit_form` | `{"unit_id": "id", "other_unit_id": "id", "formation": "enum:corps\|army\|escort"}` | 将两支符合条件的本方单位组成军团、集团军或护送编队。 |
| `unit_swap` | `{"unit_id": "id", "other_unit_id": "id"}` | 交换两支相邻本方单位的位置。 |
| `unit_target` | `{"unit_id": "id", "mission": "enum:ranged_attack\|air_attack\|air_deploy\|air_rebase\|coastal_raid\|airlift\|paradrop\|priority_attack\|move_jump", "x": "coord", "y": "coord"}` | 对指定地块执行远程攻击、空袭、空军部署／转场、海岸袭击、空运、空降或其他菜单提供的目标任务。 |
| `melee_attack` | `{"unit_id": "id", "x": "coord", "y": "coord"}` | 攻击相邻且当前可见、已探测的目标，也用于神学战斗；不会隐式宣战。 |
| `city_attack` | `{"city_id": "id", "x": "coord", "y": "coord"}` | 使用本方城市的远程攻击轰击目标。 |
| `district_attack` | `{"city_id": "id", "district_id": "id", "x": "coord", "y": "coord"}` | 使用本方城市所属区域的远程攻击轰击目标。 |
| `wmd_strike` | `{"unit_id": "id", "weapon": "identifier:WMD_", "x": "coord", "y": "coord"}` | 使用单位发射当前可用的核武器或热核武器，目标须符合可见与操作条件；可能导致宣战。 |
| `icbm_strike` | `{"city_id": "id", "source_x": "coord", "source_y": "coord", "weapon": "identifier:WMD_", "x": "coord", "y": "coord"}` | 从本方城市所属导弹发射井对合法可见目标发动核打击；可能导致宣战。 |

## 贸易路线

| `action.type` | 参数 | 功能 |
| --- | --- | --- |
| `trade_route` | `{"unit_id": "id", "x": "coord", "y": "coord"}` | 让商人向正常贸易菜单提供的目的地建立商路。 |
| `transfer_trader` | `{"unit_id": "id", "city_id": "id"}` | 将商人转移到另一座本方城市，改变商路出发城市。 |

## 间谍

| `action.type` | 参数 | 功能 |
| --- | --- | --- |
| `spy_travel` | `{"unit_id": "id", "x": "coord", "y": "coord"}` | 将间谍派往正常目的地菜单提供的城市。 |
| `spy_mission` | `{"unit_id": "id", "mission": "enum:SPY_COUNTERSPY\|SPY_DISRUPT_ROCKETRY\|SPY_GAIN_SOURCES\|SPY_GREAT_WORK_HEIST\|SPY_LISTENING_POST\|SPY_RECRUIT_PARTISANS\|SPY_SABOTAGE_PRODUCTION\|SPY_SIPHON_FUNDS\|SPY_STEAL_TECH_BOOST\|SPY_FABRICATE_SCANDAL\|SPY_FOMENT_UNREST\|SPY_NEUTRALIZE_GOVERNOR\|SPY_BREACH_DAM", "x": "coord", "y": "coord"}` | 执行当前驻城菜单提供的间谍任务，包括建立情报网、监听、反间谍、窃取科技、抽取资金、破坏等；目标地块按菜单填写。 |
| `spy_escape` | `{"district": "enum:DISTRICT_AERODROME\|DISTRICT_HARBOR\|DISTRICT_COMMERCIAL_HUB\|DISTRICT_CITY_CENTER"}` | 处理当前间谍逃跑选择，选择正常界面提供的逃跑路线。 |

## 总督与秘密结社

| `action.type` | 参数 | 功能 |
| --- | --- | --- |
| `governor_appoint` | `{"governor": "identifier:GOVERNOR_"}` | 任命可用总督，或加入当前已发现且可加入的秘密结社。 |
| `governor_promote` | `{"governor": "identifier:GOVERNOR_", "promotion": "identifier:GOVERNOR_PROMOTION_"}` | 购买当前合法的总督或秘密结社晋升。 |
| `governor_assign` | `{"governor": "identifier:GOVERNOR_", "city_id": "id", "x": "coord", "y": "coord", "owner_id": "id"}` | 将总督派驻或调动到菜单允许的本方城市，或当前可见且已遇见的外国城市。 |
| `governor_assign_city_state` | `{"governor": "identifier:GOVERNOR_", "owner_id": "id", "city_id": "id"}` | 将已任命的城邦总督派驻到当前正常菜单提供的已遇见城邦城市。 |
| `governor_defer` | `无` | 确认已考虑总督头衔选择，保留未分配头衔；不自动处理仍存在的派驻阻塞。 |

## 伟人

| `action.type` | 参数 | 功能 |
| --- | --- | --- |
| `great_person_recruit` | `{"individual": "identifier:GREAT_PERSON_INDIVIDUAL_"}` | 招募当前可认领的伟人。 |
| `great_person_pass` | `{"individual": "identifier:GREAT_PERSON_INDIVIDUAL_"}` | 放弃当前可认领的伟人。 |
| `great_person_patronize` | `{"individual": "identifier:GREAT_PERSON_INDIVIDUAL_", "yield": "enum:GOLD\|FAITH"}` | 使用金币或信仰赞助当前可赞助的伟人。 |

## 政体、政策与时代

| `action.type` | 参数 | 功能 |
| --- | --- | --- |
| `change_government` | `{"government": "identifier:GOVERNMENT_"}` | 更换为已解锁且可选择的政体，遵守正常无政府状态等规则。 |
| `government_keep` | `无` | 保留当前政体，并确认已考虑普通政体更换提示。 |
| `set_policies` | `{"slots": [{"slot": "id", "policy": "identifier:POLICY_"}]}` | 提交完整政策槽位配置，所有要求的槽位均须填满。 |
| `unlock_policies` | `无` | 支付正常费用，解锁本次政策更换。 |
| `choose_dedications` | `{"dedications": ["identifier:COMMEMORATION_"]}` | 选择当前时代要求数量的献力。 |

## 宗教选择

| `action.type` | 参数 | 功能 |
| --- | --- | --- |
| `found_pantheon` | `{"belief": "identifier:BELIEF_"}` | 选择当前可用的万神殿信条。 |
| `found_religion` | `{"religion": "identifier:RELIGION_", "name": "text", "beliefs": ["identifier:BELIEF_"]}` | 使用可选宗教名称／标志与信条创立宗教；信徒信条须在列表第一项，自定义名称用于自定义标志。 |
| `add_belief` | `{"belief": "identifier:BELIEF_"}` | 选择当前已获得资格的新增宗教信条，包括强化宗教。 |

## 城市经营与归属

| `action.type` | 参数 | 功能 |
| --- | --- | --- |
| `set_production` | `{"city_id": "integer", "item": "UNIT_*/BUILDING_*/PROJECT_* from options"}` | 设置本方城市的基础生产项目：单位、建筑或项目。 |
| `city_build` | `{"city_id": "id", "item": "identifier:UNIT_\|BUILDING_\|DISTRICT_\|PROJECT_", "append": "bool", "formation": "enum:STANDARD\|CORPS\|ARMY"}` | 生产或修复已有选址的项目，可替换当前生产或追加队列，并支持合法的军团／集团军生产。 |
| `city_build_at` | `{"city_id": "id", "item": "identifier:UNIT_\|BUILDING_\|DISTRICT_\|PROJECT_", "append": "bool", "formation": "enum:STANDARD\|CORPS\|ARMY", "x": "coord", "y": "coord"}` | 为区域或奇观指定合法地块，并提交正常生产请求。 |
| `city_purchase` | `{"city_id": "id", "item": "identifier:UNIT_\|BUILDING_\|DISTRICT_", "yield": "enum:GOLD\|FAITH", "formation": "enum:STANDARD\|CORPS\|ARMY"}` | 使用金币或信仰购买当前可购买的单位／建筑，按菜单选择单位编制。 |
| `city_purchase_at` | `{"city_id": "id", "item": "identifier:UNIT_\|BUILDING_\|DISTRICT_", "yield": "enum:GOLD\|FAITH", "formation": "enum:STANDARD\|CORPS\|ARMY", "x": "coord", "y": "coord"}` | 使用金币或信仰在指定合法地块购买区域。 |
| `city_purchase_plot` | `{"city_id": "id", "x": "coord", "y": "coord"}` | 购买本方城市正常购地菜单提供的可见地块。 |
| `city_manage_citizen` | `{"city_id": "id", "x": "coord", "y": "coord"}` | 按普通城市界面点击地块的方式切换人口工作、锁定或专家分配状态；操作后重新读取锁定状态与人数。 |
| `city_swap_tile` | `{"city_id": "id", "x": "coord", "y": "coord"}` | 把本方已拥有的地块划归另一座符合条件的本方城市。 |
| `city_set_focus` | `{"city_id": "id", "yield": "identifier:YIELD_", "focus": "enum:favored\|disfavored\|neutral"}` | 明确设置某类城市产出的偏好、避免或中立状态。 |
| `city_rename` | `{"city_id": "id", "name": "text"}` | 给本方城市改名。 |
| `city_queue_remove` | `{"city_id": "id", "index": "id"}` | 删除生产队列中指定索引的条目。 |
| `city_queue_move` | `{"city_id": "id", "index": "id", "destination": "id"}` | 将生产队列条目移动到另一个队列位置。 |
| `city_loyalty_choice` | `{"city_id": "id", "choice": "enum:keep\|reject"}` | 接受或拒绝当前向本方提出加入的忠诚度转化城市。 |
| `city_fate` | `{"city_id": "id", "choice": "enum:keep\|raze\|liberate_founder\|liberate_previous"}` | 处理当前被占领城市的保留、夷平或解放决定。 |

## 区域选址预览

| `action.type` | 参数 | 功能 |
| --- | --- | --- |
| `district_preview_select_city` | `{"city_id": "id"}` | 选择要查看区域选址的本方城市；这一步不打开选址、不开始建造。 |
| `district_preview_begin` | `{"city_id": "id", "item": "identifier:DISTRICT_"}` | 打开指定区域的原版选址预览，供查询自然显示的相邻加成标签；不会建造区域。 |
| `district_preview_cancel` | `无` | 退出本客户端开启且仍匹配的区域选址预览。 |
| `district_preview_exit_current` | `{"city_id": "id", "item": "identifier:DISTRICT_"}` | 在预览连接中断后，退出当前本方城市仍匹配的区域选址界面；不会恢复旧预览结果。 |

## 文明外交

| `action.type` | 参数 | 功能 |
| --- | --- | --- |
| `diplomacy_statement` | `{"target_player": "id", "statement": "enum:surprise_war\|formal_war\|holy_war\|liberation_war\|reconquest_war\|protectorate_war\|colonial_war\|territorial_war\|golden_age_war\|retribution_war\|ideological_war\|delegation\|embassy\|friendship\|denounce\|open_borders\|stop_spying\|stop_settling\|stop_converting\|stop_digging\|trade\|peace"}` | 向已遇见文明发起菜单允许的宣战、使团、大使馆、友谊、谴责、边界或行为请求、交易及和平交涉。 |
| `diplomacy_respond` | `{"target_player": "id", "session_id": "id", "signature": "identifier:STATEMENT_", "response": "identifier:CHOICE_"}` | 选择当前外交会话实际提供的回应，必须使用该次观察返回的会话与签名。 |
| `diplomacy_close` | `{"target_player": "id", "session_id": "id", "signature": "identifier:STATEMENT_"}` | 退出当前观察到的外交对话。 |

## 城邦

| `action.type` | 参数 | 功能 |
| --- | --- | --- |
| `city_state_envoy` | `{"target_player": "id"}` | 向已遇见且允许派遣的城邦派遣使者。 |
| `city_state_levy` | `{"target_player": "id"}` | 在当前资格与费用允许时征召城邦军队。 |
| `city_state_war` | `{"target_player": "id"}` | 按普通城邦菜单向可宣战的城邦宣战。 |
| `city_state_peace` | `{"target_player": "id"}` | 按普通城邦菜单与可议和的城邦议和。 |
| `city_state_defer_envoys` | `无` | 保留尚未分配的使者并确认已考虑派遣；不消耗使者。 |

## 外交交易

| `action.type` | 参数 | 功能 |
| --- | --- | --- |
| `deal_clear` | `{"target_player": "id"}` | 清空本方正在编辑的外发交易草案，不操作收到或已提交的报价。 |
| `deal_add_item` | `{"target_player": "id", "side": "enum:give\|receive", "kind": "enum:gold\|favor\|resource\|agreement\|city\|great_work\|captive", "value": "id", "amount": "id", "duration": "id", "agreement": "enum:NONE\|OPEN_BORDERS\|MAKE_PEACE\|ALLIANCE\|DEFENSIVE_PACT\|RESEARCH_AGREEMENT"}` | 向外发草案添加给出或索取的金币、外交支持、资源、协议、城市、巨作或俘虏；数量、期限和种类取自 deal_options。 |
| `deal_remove_item` | `{"target_player": "id", "item_id": "id"}` | 从外发草案中移除可编辑的交易条目。 |
| `deal_add_war` | `{"target_player": "id", "side": "enum:give\|receive", "agreement": "enum:JOINT_WAR\|THIRD_PARTY_WAR", "enemy": "id", "war": "text_identifier", "duration": "id"}` | 向草案添加菜单实际提供的联合战争或第三方战争条款；发送或接受此交易可能宣战。 |
| `deal_equalize` | `{"target_player": "id", "session_id": "id", "signature": "identifier:DEAL_"}` | 使用当前可见交易界面的平衡交易按钮调整匹配的外发草案，不自动接受交易。 |
| `deal_send` | `{"target_player": "id"}` | 发送当前外发草案作为提案或还价，包括正常和平与同盟协议。 |
| `deal_respond` | `{"target_player": "id", "session_id": "id", "signature": "identifier:DEAL_", "accept": "bool"}` | 接受或拒绝当前观察到的收到报价；会话、签名与条款必须仍然一致。 |

## 巨作与考古

| `action.type` | 参数 | 功能 |
| --- | --- | --- |
| `move_great_work` | `{"source_city": "id", "destination_city": "id", "source_building": "identifier:BUILDING_", "destination_building": "identifier:BUILDING_", "source_slot": "id", "destination_slot": "id"}` | 在本方建筑槽位之间移动或交换巨作，遵守槽位类型、美术品锁定和考古博物馆规则。 |
| `choose_artifact` | `{"unit_id": "id", "choice": "id"}` | 选择当前考古界面显示的文物来源选项 1 或 2；不揭示尚未遇见文明的身份。 |

## 世界议会与紧急事件

| `action.type` | 参数 | 功能 |
| --- | --- | --- |
| `congress_ballot` | `{"resolutions": [{"resolution": "identifier:WC_RES_\|RESOLUTION_", "choice": "id", "selection": "id", "votes": "id"}], "discussions": [{"proposal": "id", "direction": "signed_id", "votes": "id"}]}` | 一次性提交本次议会的全部决议与讨论投票，包括选项、目标和票数；外交支持须足够。 |
| `congress_propose` | `{"proposal": "id"}` | 在非投票阶段提出当前可用的紧急事件提案。 |
| `congress_acknowledge` | `无` | 确认已查看当前议会提案，不跳过正在进行的投票。 |
| `emergency_respond` | `{"emergency": "id", "choice": "enum:join\|reject\|acknowledge"}` | 加入、拒绝当前玩家可见的紧急事件，或确认事件开始／结束的信息。 |

## 通知与弹窗

| `action.type` | 参数 | 功能 |
| --- | --- | --- |
| `dismiss_notification` | `{"notification_id": "id"}` | 关闭本方允许手动关闭、且不属于必选阻塞的通知。 |
| `activate_notification` | `{"notification_id": "id"}` | 打开本方通知对应的正常游戏界面。 |
| `popup_action` | `{"popup": "enum:boost\|research_completed\|natural_wonder\|wonder_built\|project_built\|era_complete\|era_review\|natural_disaster\|secret_society\|world_crisis\|rock_band\|rock_band_movie\|great_work\|great_works_overview\|historic_moments\|world_rankings\|generic\|diplomacy\|deal\|world_congress\|congress_between_turns\|congress_intro\|dedication\|captured_city\|disloyal_city\|pantheon\|religion\|government\|governors\|governor_assignment\|artifact\|spy_escape\|unit_promotion\|spy_mission\|great_people\|declare_war\|event\|advisor\|expansion_intro", "button_id": "id", "revision": "identifier:POPUP_"}` | 点击当前可见弹窗实际提供的按钮，绑定其正文版本；用于继续、确认、关闭或进入相应选择。 |

## 补充说明

- 伟人单位能力通过 `unit_command(command="activate_great_person")` 等当前菜单动作使用；招募伟人不等于激活能力。
- `unit_order(order="build_route")` 建造当前已解锁的道路或铁路；国家公园和摇滚演出也使用对应单位菜单返回的动作。
- `unit_promote` 同时用于有晋升资格的军事、宗教、间谍等单位，具体晋升由查询结果给出。
- 世界议会 `resolutions` 中 `choice` 为 1／2，`selection` 为从 0 开始的选项索引；`discussions` 的 `direction` 为 1／-1。直接使用本次议会查询提供的选项更稳妥。
- 对话、交易、弹窗的 `signature`／`revision` 是当前观察返回的标记，不能复用旧内容的标记。
- 备用任意 Lua 执行不属于 `act` 动作类型，见 [备用接口约定](FALLBACK_LUA.md)。
