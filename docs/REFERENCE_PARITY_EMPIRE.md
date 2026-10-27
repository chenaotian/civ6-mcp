# 参考项目对照：城市、内政、宗教、伟人与经济

对照对象为 `lmwilki/civ6-mcp`，本地快照 `references/lmwilki-civ6-mcp-20261027/civ6-mcp-main`（2026-10-27 下载归档，SHA256 `4b10ec3fc9e27078eaacd9cc187259e393fd8a55a1ef67052661dfa7b8969418`）。核对了 `server.py` 工具入口、`game_state.py` 的调用链，以及 `lua/cities.py`、`governance.py`、`religion.py`、`great_people.py`、`economy.py`、`map.py`、`victory.py` 的具体读取和请求。

参考代码仅作为功能线索；没有执行其脚本、自动启动、存档操作、GameCore 写入或任意 Lua 接口。本批实现按本机原版 UI 重新核实，游戏维持暂停，新增内容只经过离线测试。

## 能力对应与差距处理

| 参考入口／实现 | 本项目对应 | 对照结论 |
| --- | --- | --- |
| `get_cities`；`cities.py:16–168` | `get_player_state`、`city_status`、`city_production`、`city_buildings` | 既有城市产出、人口、粮食、住房、宜居度、忠诚度、生产、建筑与区域状态；本批补主城区防御强度、驻军／城墙剩余与最大 HP，以及区分增长／下降的忠诚倒计时。 |
| `get_city_production`、`set_city_production`、`purchase_item` | `city_production`、`city_build`、`city_build_at`、`city_purchase`、`city_purchase_at`、`city_queue` | 已覆盖普通单位、建筑、区域、奇观、项目、维修和金币／信仰购买、真实成本／进度／工期。保留正常资格门，不移植参考项目绕过 `CanStartOperation` 的生产分支。 |
| `get_purchasable_tiles`、`purchase_tile`、`set_city_focus` | `city_tiles`、`city_purchase_plot`、`city_set_focus`、公民／专家管理动作 | 已有正常菜单地块价格与购买、产出偏好，以及更细的锁定公民和专家操作；没有新增同义工具。 |
| `get_district_advisor`、`get_wonder_advisor`；`map.py:566–764` | `city_placement`、`district_preview` | 已有合法可见选址；相邻加成通过原版放置 UI 的实际标签读取。参考实现的硬编码相邻公式、邻格原始扫描和“移除收益损失”排名不直接移植；后者不是完整原版预览的替代。 |
| `get_policies`、`set_policies`、`change_government` | `government`、`set_policies`、`change_government`、`government_keep`、`unlock_policies` | 已覆盖；本项目保留 GS 的 `IsPolicyBanned/CanPolicyBeSlotted/IsPolicyObsolete` 门，并提供当前政体和政策说明。 |
| `get_governors`、任命／派驻／晋升 | `governors`、`governor_appoint/assign/promote`、总督确认与暂存动作 | 已覆盖任命、晋升、派驻、派驻倒计时和当前确认状态；外派城邦沿原版目的地菜单另行过滤。不会照搬无条件读取外国派驻城市的方式。 |
| `get_dedications`；`governance.py:548–586` | `dedications`、`choose_dedications` | 选择已有覆盖；本批补本方时代分数、普通／黄金门槛、时代状态和当前生效献力。缺少状态 API 时省略未知，不默认普通时代。 |
| 万神殿／创教／信条与 `get_religion_spread`；`religion.py:17–220、291–351` | `religion`、`found_pantheon/found_religion/add_belief`、传教／宗教战斗 | 动作已有覆盖；本批新增 `city_religion` 和 `visible_city_religion` 的城市宗教分布及原版转换预测。没有移植对所有文明的宗教占多数统计、外国城市集合枚举或迷雾城市实时读取。 |
| `get_great_people`、招募／赞助／放弃；`great_people.py:9–232` | `great_people`、`great_person_recruit/patronize/pass` | 动作已有覆盖；本批补本方各类伟人点数／每回合点数、界面会显示的不可负担报价、正常放弃费用；同时使赞助候选和执行遵守原版按钮条件。 |
| `get_gp_advisor`；`great_people.py:376–480` | `special_unit_sites`、`unit_details`、`unit_actions`、`great_works` | 本批将原版伟人激活高亮接入已有地点查询，并一并支持摇滚乐队。没有沿用“伟人职业固定对应某区域”的猜测；仅返回实际高亮中的已探索坐标。伟人能力、次数、建筑巨作槽位仍通过已有查询读取。 |
| `get_trade_routes/get_trade_destinations` | `own_trade_routes`、`trade_destinations/trade_routes`、`trade_route`、`transfer_trader` | 已有容量、路线、目的地、当前可用操作和商人转移；目标采用原版菜单资格，不以全图或外国城市枚举代替。细项由贸易领域另行对照。 |
| `get_empire_resources`；`map.py:480–563` | `own_resources`、`own_luxuries`、当前可见地图观察 | 本方战略库存、上限、收入／需求、奢侈品份数已有覆盖，包含伟商非地图资源。资源地点沿现有可见性和解锁过滤；不移植整图底层资源扫描及迷雾实时资源读取。 |
| `get_victory_progress` 中自己的太空项目链；`victory.py:76` 起 | 新增 `own_science_victory` | 补本方科技胜利项目完成状态、逐本方城市成本／进度／是否当前生产及 GS 远征光年。没有引入对手空间港、城市生产或未知文明的统计。其他胜利种类由总对照记录单独列出，不能将本查询称为全胜利追踪。 |

## 本批接口

- `city_status({city_id})`：可选 `defense_strength`、`garrison_hp/garrison_hp_maximum`、`walls_hp/walls_hp_maximum`、`loyalty_direction`（`gaining/losing`）、`loyalty_turns_to_outcome`。增长方向的倒计时表示趋向忠诚满额，不是叛乱时间。没有读取潜在接收文明或外国人口压力来源。
- `city_religion({city_id})`：限本方城市；`visible_city_religion({x,y})`：仅明确已探索、当前可见且属于已遇见玩家的城市。返回 `majority_religion`、`religion:<规则标识>:followers`、可选 `next_religion/turns_to_next_religion`。宗教名称使用原版 `Game.GetReligion():GetName`，可显示城市 UI 已展示的自定义宗教名；不返回创立者身份、原始压力源或世界汇总。
- `own_science_victory({})`：只有明确启用科技胜利时可用。Base/RF 使用卫星、登月和三个火星项目；GS 使用卫星、登月、火星基地、系外行星远征。`<项目>:completed` 源于本方 `GetNumProjectsAdvanced`；`city:<ID>:<项目>:cost/progress/producing` 为实际本方城市数据。GS 可选 `light_years/light_years_required`；`light_years_per_turn` 只在远征已完成后读取。完成、积累生产进度和正在生产是三个独立事实，不混为完成。
- `great_people({})`：新增 `GREAT_PERSON_CLASS_*:points/points_per_turn`；每回合率按原版提示保留一位小数。金币／信仰报价条目即使不能支付也可出现，但无动作。达到原版隐藏门槛、已经可招募／放弃、缺少相应购买 capability 时不提供赞助候选；动作端重新验证同一条件。招募须有当前 timeline 的有效 `Cost`，放弃须有有效 `GetRejectCost`，费用缺失时不提供或执行相应按钮；零费用有效。原有人的 `value` 仍是招募所需伟人点数，不改成金币。
- `dedications({})`：新增 `era_score`、`dark_age_threshold`、`golden_age_threshold`、`age` 和 `active:COMMEMORATION_*`，只查询本方时代面板状态。黄金／英雄时代中，仅本方 `IsPlayerAlwaysAllowedCommemorationQuest` 明确为真时另附 `active:COMMEMORATION_*:normal_age_bonus`，对应原版同时生效的普通献力任务。
- `special_unit_sites({unit_id})`：在考古和公园之外新增 `great_person` 与 `rock_concert` 用途。详情及迷雾渲染依据见 [SPECIAL_UNIT_SITES.md](SPECIAL_UNIT_SITES.md)。没有自动移动或激活。

## 原版来源与验证

城市防御：Base／GS `CitySupport.lua:361–373` 明确由本方 `player:GetDistricts():FindID(city:GetDistrictID())` 读取防御及两类伤害，防御强度按 `floor(value+0.5)` 显示。忠诚方向及倒计时来自 RF `Additions/LoyaltySupport.lua:25–42`，没有把增忠／减忠两个分支合并。

城市宗教：Base `CitySupport.lua:499–510`；GS `CityBanners/CityBannerManager.lua:1902–1947、2027–2089` 的宗教镜头展示多数宗教、信徒分布、下一宗教及剩余回合。城市读取前后重新检查可见性及身份；不会从 `Players[other]:GetCities()` 发现未公开城市。

伟人：Base `Popups/GreatPeoplePopup.lua:241–283` 的按钮显示条件；`710–738` 的本方招募／放弃／赞助成本；`800–801` 的本方点数，`441` 的每回合率显示精度。伟人和摇滚乐队高亮来自 GS `SelectedUnit_Expansion2.lua:30–46、65–74`。只有实际伟人且该人物启用 `ActionEffectTileHighlighting` 才读取激活地点；不读取被动作用范围。

时代面板：RF／GS `EraProgressPanel.lua:69、117–119、141、188–196`。科技胜利：Base `PartialScreens/WorldRankings.lua:183–192、352、615、1234–1267`；GS `WorldRankings_Expansion2.lua:20–37、290–375、585–589`。这些来源均为正常 UI，未依赖参考代码的 GameCore 写入。

2026-10-27 定向回归：`test_reference_empire.py`、`test_special_unit_sites.py`、`test_extension_empire.py`、`test_city_status.py`、`test_waiting.py` 共 **352 项通过**，耗时 **2.41 秒**。测试覆盖身份错误、未遇见城市、未探索／迷雾、查询中失去可见性、原版高亮成员、缺失 API、未知值不冒充零、Base/RF/GS 项目差别、胜利关闭时不读取本方统计、远征前不读取每回合光年、招募／放弃费用门，以及正常不可负担报价无动作。没有进行本批实机操作，也没有据此声称所有新增字段已经在真实新局验证。
