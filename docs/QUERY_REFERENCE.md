# 分类查询参考

`inspect_game(category, params=None)` 提供下列 **51 类查询**。本文按当前注册表列出全部类别、参数和用途；运行中的 `get_rules()` 也会返回类别及参数定义。

```text
inspect_game(category="unit_actions", params={"unit_id": 123})
inspect_game(category="city_status", params={"city_id": 456})
inspect_game(category="governors")
```

示例 ID 仅说明格式，实际值必须来自当前公开观察。表中的参数全部必填；写“无”的类别可省略 `params` 或传 `{}`。不得增加未列出的参数。

## 参数与结果约定

| 标记 | 含义 |
| --- | --- |
| `id` | 0～2147483647 的整数。通常表示本方单位、城市或已知目标的 ID；具体归属仍按查询要求检查。 |
| `coord` | 0～4095 的整数坐标；还需位于实际地图范围内，并满足对应查询的可见或已探索条件。 |
| `offset` | 非负整数分页游标，从 0 开始，随后使用返回的 `next_offset`；`-1` 表示结束，不要将其继续传入。 |
| `BUILDING_*`、`DISTRICT_*`、`GOVERNOR_*` | 游戏返回的类型标识，不能用中文名称代替。 |

查询通常返回 `category`、`supported`、`items`，并附带当前观察信息和可见 UI；部分专用类别还返回结构化预览或分页字段。`items` 可能包含说明、数值、不可用选项及可直接提交的 `action`。优先把实际返回的完整动作与最新 `observation_token` 一起传给 `act`；其他动作须按 `get_rules()` 的定义填写，并满足当前操作资格。查询本身不会代替玩家做出选择。

`supported=false` 表示当前环境缺少必要能力，不等于“没有选项”。可选字段缺失表示未知，不当作 0、否或不存在。推荐地点、价格和预览都不保证动作合法或已经完成。游戏观察会替换旧令牌；操作后应再次观察。

## 单位、战斗与地点

| `category` | `params` | 功能 |
| --- | --- | --- |
| `unit_details` | `unit_id: id` | 查询本方单位战斗力、特殊次数、经验、已获晋升、伟人身份，以及可取得的间谍剩余回合等详情。 |
| `unit_actions` | `unit_id: id` | 查询单位在当前地块可执行的正常动作和改良操作，包括符合条件的建造、修复、收获、升级或特殊能力等。以返回选项为准。 |
| `unit_promotions` | `unit_id: id` | 查询引擎当前提供的晋升选项，包含普通单位、使徒、间谍和摇滚乐队等。 |
| `unit_formations` | `unit_id: id` | 查询能与该单位组成军团、集团军或护送编队的本方单位及对应动作。 |
| `unit_swaps` | `unit_id: id` | 查询可以与该单位交换位置的相邻本方单位。 |
| `unit_targets` | `unit_id: id, x: coord, y: coord` | 针对一个当前可见地块，查询本方单位可用的攻击、空军或其他目标动作；不会扩大到未知目标。 |
| `unit_neighbors` | `unit_id: id` | 返回本方单位六角邻格坐标及普通移动动作，允许包含未探索邻格。只表示几何相邻，不提供地块内容，也不保证能移动到达。 |
| `unit_move_preview` | `unit_id: id, x: coord, y: coord` | 预览本方单位移动到当前可见目标的正常路线状态。可报告直达、绕行、有路线、无路径或未知；仅在允许时给出首步和抵达回合，不返回完整路径，也不更改移动命令。 |
| `unit_recommendations` | `unit_id: id` | 查询建造者或开拓者的原版推荐地点，仅返回当前可见坐标。不给出隐藏评分或地块内容，不承诺推荐最优或当前可执行。 |
| `special_unit_sites` | `unit_id: id` | 查询考古学家、可建国家公园的单位、伟人、摇滚乐队的原版高亮地点。最多 512 处，可含已探索雾中坐标；不含未探索位置、当前地块详情、完整公园范围或激活动作。 |
| `combat_preview` | `attacker_kind, attacker_id: id, target_owner_id: id, target_unit_id: id, x: coord, y: coord` | 针对一个当前可见且已探测的敌方单位，查询合法攻击的战斗力和修正说明。`attacker_kind` 为 `unit_melee`、`unit_ranged`、`city` 或 `district`。不预测精确伤害，不自动选择防守单位。 |
| `city_combat` | `city_id: id, x: coord, y: coord` | 查询本方城市及其区域对指定已感知目标的正常轰击选项。 |

## 城市经营与宗教分布

| `category` | `params` | 功能 |
| --- | --- | --- |
| `city_status` | `city_id: id` | 查询本方城市住房、宜居度、粮食、增长或饥饿、忠诚方向及倒计时、城防，以及风云变幻电力状态。缺失估计不当作零回合，不读取外国忠诚压力来源。 |
| `city_production` | `city_id: id` | 查询本方城市建造、修复和购买菜单，以及可取得的成本、进度、工期、金币或信仰报价。需要选址的项目需继续查 `city_placement`；不可购买的报价不会附购买动作。 |
| `city_placement` | `city_id: id, item: BUILDING_* 或 DISTRICT_*` | 查询该城市可见地块中合法的区域、奇观等建造或购买位置，并附可取得的工期或价格。 |
| `city_tiles` | `city_id: id` | 查询城市可见地块的人口、专家、锁定状态，以及购地、地块归属调换和产出侧重选项；购地可附金币价格。 |
| `city_queue` | `city_id: id` | 查询本方城市生产队列、从 0 开始的队列索引，以及可用的移除动作。 |
| `district_preview` | `city_id: id, item: DISTRICT_*` | 读取本客户端明确打开的原版区域选址预览标签。必要时按返回动作先选择城市，观察后开启预览，再读取标签；不涵盖未购买地块或奇观，未显示的标签不视为零收益。 |
| `city_religion` | `city_id: id` | 查询本方城市多数宗教、各宗教信徒及可取得的原版宗教转换预测，不提供创立者身份或压力来源。 |
| `visible_city_religion` | `x: coord, y: coord` | 查询一个已遇见玩家的当前可见城市的宗教透镜信息，不提供雾中城市的实时状态。 |

## 内政、总督与资源

| `category` | `params` | 功能 |
| --- | --- | --- |
| `governors` | 无 | 查询本方总督头衔、已发现总督或结社、派驻和到任状态、已获及可选晋升，以及本方城市派驻目的地。 |
| `governor_city_state_destinations` | `governor: GOVERNOR_*` | 查询已任命总督的正常城邦派驻菜单，可含已遇见的雾中城邦；提供是否可派驻、正常到任时间及可取得的当前派驻信息，不提供隐藏城市详情。 |
| `great_people` | 无 | 查询公开伟人招募面板及本方可用的招募、赞助、放弃选择；伟人已上地图后的能力通过单位查询获得。 |
| `government` | 无 | 查询已解锁政体、可取得的效果和基础政策槽预览、可用政策、实际槽位索引及当前配置。 |
| `dedications` | 无 | 查询本时代的献力选项和必须选择的准确数量。 |
| `religion` | 无 | 查询本方宗教、已获得信条，以及宗教选择界面当前提供的选择。 |
| `own_resources` | 无 | 查询本方已解锁战略资源数量，以及可取得的风云变幻库存上限、收入与需求。不返回未解锁资源名称、地图位置或外国来源。 |
| `own_luxuries` | 无 | 查询本方持有数量大于零的奢侈资源，包括大商人提供的特殊商品。数量是持有份数，不代表可交易上限，不提供资源位置或来源分布。 |
| `own_science_victory` | 无 | 查询本方科学胜利项目的完成状态、相关城市生产成本和进度，以及风云变幻远征光年进度；不提供对手数据。 |
| `loyalty_choices` | 无 | 查询下一座因忠诚转向而向本方提出加入请求的城市的接受或拒绝选择。 |

## 贸易路线

| `category` | `params` | 功能 |
| --- | --- | --- |
| `trade_destinations` | `unit_id: id, offset` | 分页查询该商人的原版贸易菜单目的地，可包含已探索的雾中城市。每页最多 64 个合法菜单目的地。 |
| `trade_routes` | `unit_id: id, x: coord, y: coord` | 查询该商人前往指定菜单目的地的商路选项及收益，不返回完整路线经过的地块。 |
| `trader_origins` | `unit_id: id` | 查询该商人可以转移所属城市的本方目的地。 |
| `own_trade_routes` | 无 | 查询本方运行商路、使用量和容量、关联商人、闲置商人，以及可取得的起点和终点收益。不提供剩余回合或完整路径；闲置本身不能解释商路结束原因。 |

## 间谍

| `category` | `params` | 功能 |
| --- | --- | --- |
| `spy_overview` | 无 | 查询本方旅行中及驻城间谍的名字、等级、剩余回合、目的地或当前城市、可取得的任务区域与效果，以及间谍容量。旅行记录索引不是单位 ID；驻城记录可提供本方单位 ID。 |
| `spy_destinations` | `unit_id: id, offset` | 分页查询原版间谍菜单提供的目的地，可包含已探索的雾中城市。每页最多 64 个合法菜单目的地。 |
| `spy_missions` | `unit_id: id, x: coord, y: coord` | 查询已知城市或菜单提供区域的间谍任务。远处城市任务仅用于预览，实际执行要求间谍处于对应当前城市。 |
| `spy_escape_routes` | 无 | 查询本方当前待处理的间谍逃跑路线选择。 |

## 外交、城邦与交易

| `category` | `params` | 功能 |
| --- | --- | --- |
| `diplomacy_sessions` | 无 | 查询与已遇见文明当前打开的本地外交会话、公开提示正文和可用回应。 |
| `diplomacy_actions` | `target_player: id` | 查询与指定已遇见文明可进行的正常外交动作和已确认会话选项。 |
| `city_states` | 无 | 查询已遇见城邦的使者、竞争贡献、宗主、奖励、本方任务、战争状态和合法操作；不披露未遇见竞争者身份。 |
| `deal_options` | `target_player: id, side, kind` | 查询正常交易界面提供的可交易项目。`side` 为 `give` 或 `receive`；`kind` 为 `gold`、`favor`、`resource`、`agreement`、`city`、`great_work` 或 `captive`。未解锁资源仍被过滤。 |
| `war_deal_options` | `target_player: id, side, agreement` | 查询联合战争或对第三方开战条款。`side` 为 `give` 或 `receive`；`agreement` 为 `JOINT_WAR` 或 `THIRD_PARTY_WAR`。不披露未知敌人的 ID 或身份。 |
| `deal_state` | `target_player: id` | 查询本方与指定对方的发出或收到的交易谈判，以及针对当前确切报价可用的回应选项。 |
| `deal_negotiation` | `target_player: id` | 查询当前可见交易面板可用的正常“平衡交易”请求，针对当前本方草案提供动作。 |

## 文化、世界议会与紧急事件

| `category` | `params` | 功能 |
| --- | --- | --- |
| `great_works` | `city_id: id` | 查询本方城市的建筑巨作槽及巨作当前能否移动。 |
| `archaeology` | 无 | 查询当前待处理的考古文物来源选择，未遇见文明的身份保持匿名。 |
| `world_congress` | 无 | 查询玩家可见的议案、目标和提案序号、投票成本及外交支持，用于提交正常投票。 |
| `emergencies` | 无 | 查询本方紧急事件的加入、拒绝或确认选项，不额外提供其他参与者身份或不可见城市位置。 |

## 阻塞与探索

| `category` | `params` | 功能 |
| --- | --- | --- |
| `pending_decisions` | 无 | 查询当前回合阻塞、本方通知、占领城市归属选择和可见弹窗正文、按钮及动作；也可直接调用 `get_pending_decisions()`。 |
| `exploration_frontier` | `offset` | 分页查询与未探索六角格相邻的已探索边缘坐标。每页最多扫描 512 个地图格，不等于返回 512 个边缘点；只提供可见性标签，不预测隐藏内容、路线或安全。 |

## 常见使用顺序

1. 用 `get_pending_decisions()` 查看阻塞，优先处理实际返回的弹窗或必选决策。
2. 用对应类别读取当前选项；若结果包含 `action`，保留其完整参数。
3. 使用本次观察的 `observation_token` 调用 `act` 一次。
4. 再观察结果，或在已有普通观察基线时调用 `wait_for_change`。请求已提交不等于已完成。

动作名称及作用见 [动作参考](ACTION_REFERENCE.md)。当前查询不能保证覆盖所有模组、剧本或可选模式；缺少必要能力时按返回状态处理。
