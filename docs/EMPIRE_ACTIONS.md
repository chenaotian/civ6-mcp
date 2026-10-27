# 帝国内政与城市操作（0.3）

`city_production` 的诊断扩展返回普通建筑和既有区域的 `:production_available`、`:repair` 以及固定白名单失败原因；不可生产的条目没有动作。`:failure_explanation_available=false` 表示没有提供具体原因，不能解释为没有限制。新区域和新奇观的复杂选址禁用状态未扩展。`district:<plotIndex>` 条目及 `:x`、`:y`、`:complete`、`:pillaged` 给出当前本城可见区域状态，不查询邻格或加成。第 66 回合已验证首都全部区域状态；占位原因仍需后续合适实机场景验收。

实现位于 `src/civ6_fair_mcp/extensions/empire.py`；城市实际成本与购买资格辅助函数位于 `extensions/city_costs.py`，总督城邦派驻菜单位于 `extensions/governor_destinations.py`，政体公开效果预览位于 `extensions/government_preview.py`。这些接口调用当前玩家原版 UI 使用的正常请求，继承会话、回合、令牌、所有权检查；不提供调试改值。

## 操作与发现

| 功能 | 动作 | `inspect_game` 类别 |
| --- | --- | --- |
| 总督与秘密结社 | `governor_appoint`、`governor_promote`、`governor_assign`、`governor_defer` | `governors` |
| 总督派驻城邦菜单 | `governor_assign_city_state` | `governor_city_state_destinations` |
| 伟人招募 | `great_person_recruit`、`great_person_pass`、`great_person_patronize` | `great_people` |
| 政体政策 | `change_government`、`government_keep`、`unlock_policies`、`set_policies` | `government` |
| 时代献力 | `choose_dedications` | `dedications` |
| 万神殿与创教 | `found_pantheon`、`found_religion`、`add_belief` | `religion` |
| 生产与购买 | `city_build`、`city_build_at`、`city_purchase`、`city_purchase_at` | `city_production`、`city_placement` |
| 人口、专家、地块 | `city_purchase_plot`、`city_manage_citizen`、`city_swap_tile`、`city_set_focus` | `city_tiles` |
| 生产队列 | `city_queue_remove`、`city_queue_move` | `city_queue` |
| 忠诚度归附选择 | `city_loyalty_choice` | `loyalty_choices` |
| 城市名称 | `city_rename` | 使用自有城市 ID 与自选名称 |

`empire.py` 提供 27 个动作、10 个查询类别，`governor_destinations.py` 另提供 1 个动作和 1 个查询类别。参数的完整机器可读定义由 `get_rules` 返回。`city_production`、`city_tiles`、`city_queue` 需要自己的 `city_id`；`city_placement` 还需要已知的 `BUILDING_*` 或 `DISTRICT_*` 类型。

## 行为细节

- 总督任命先用当前玩家 `CanEverAppointGovernor`，所以未发现的秘密结社不会返回名称、ID 或候选项。晋升返回自己已获得和当前可获得的项目，`value` 分别为 `true`/`false`；隐藏的未来结社晋升不返回。安装资料中虽然存在结社 UI 代码，但仅风云变幻/迭起兴衰并不等于已启用秘密结社模式。
- `governors` 同时报告自己的已派驻标记、到任状态、剩余到任回合、被排除回合，以及允许读取的当前派驻城市名称、ID、拥有者。外国派驻城市的明细仍需当前可见且已遇见；对应可选 getter 缺失时不伪造其状态。
- `governor_assign` 支持自有城市，以及当前可见、已遇见的外部城市（例如阿玛妮派驻城邦）。必须给出目标城市的拥有者、ID、坐标，外部城市在检查视野前不会查询。`governors` 自动列出自有派驻目标；外部目标使用此前合法观察的坐标和 ID。
- `governor_city_state_destinations({"governor":"GOVERNOR_THE_AMBASSADOR"})` 提供原版城邦派驻菜单。仅限本方已任命、`IsGovernCityState()` 为真的总督；目标必须在存活小文明列表中、已遇见且能够接收影响力。已遇见检查早于目标组件和城市的读取。原版此菜单没有当前视野门槛，所以符合菜单条件的雾中城邦可以返回城市名、到任所需回合及派驻操作；不会返回坐标、地图内容、人口、产出或隐藏的忠诚压力，也不扩展到其他文明城市。
- 城邦目标条目 `id=city_state:<owner>:<city>`，`value` 表示当前可派驻，`:establish_turns` 条目给出原版显示的到任时长。战争等原因导致 `CanAssignGovernor(...,true)=false` 时保留菜单城市名但不给动作；总督被排除、战略命令不可用或世界议会期间同样不提供动作。该总督当前已派驻的城市按原版排除可选动作。选择返回的 `governor_assign_city_state` 动作即可，无需手工提供坐标；动作提交前重新核对本方总督、当前菜单成员身份和合法性。该专用路径不放宽旧 `governor_assign` 的外部城市视野要求。
- 当前已派驻城邦通过相同存活、影响力接收资格和已遇见检查后，新查询还返回只读的 `current_assignment:city`（`name` 为城市名，`value` 为城市 ID）和 `current_assignment:owner_id`（`value` 为拥有者 ID）。信息来自本方总督的正常派驻状态，与原版总督面板显示当前城市一致；即使城市在雾中也可确认派驻目的地。该摘要不附派驻动作，不读取位置或其他城市属性；若目标已不符合此专用城邦范围，不以其他 scope 绕过过滤。第 79 回合已实测新派驻动作可将阿玛妮派往雾中那烂陀；第 81 回合已读到当前摘要中的那烂陀、城市 ID 65536 和拥有者 ID 8，没有重复派驻动作。
- 城邦派驻菜单使用独立 `menu` 权限，Python 投影再次绑定本方、总督标识和目标拥有者／城市 ID，只允许对应的固定派驻动作。授权元数据不返回给调用方；伪造的 `self`／`met`／`visible`／`public` 记录不能混入此菜单。最多返回 2048 条记录；超过上限或必需接口不可用时返回 `supported=false`，不将截断结果冒充完整列表。可选到任时长取不到时省略，不伪造零。
- `governor_defer` 确认已查看本轮总督选择，并保留尚未花费的头衔；它对应原版总督面板显式关闭按钮设置的“已考虑”标记。仅在该标记尚未设置时提供，不要求仍有可用头衔，也不会派驻总督或保证解除任意 `ENDTURN_BLOCKING_GOVERNOR_IDLE`。操作后须重新读取待处理决策。`government_keep` 对应保留现政体的“已考虑”标记；这些操作不替代必填政策卡或其他强制选择。
- `governors` 的可选 `title_considered` 布尔值直接来自本方 `HasTitleBeenConsidered()`；接口缺失、异常或非布尔结果时省略，不将未知当作 `false`。只有明确 `false` 且原版设置接口可用时，才提供中文“确认已查看总督选择”动作；提交前重新检查，过期选项不会重复设置。该标记与各总督的派驻、建立状态分别读取。
- 若总督已显示派驻城市和到任倒计时，但仍有待派驻通知，可激活该通知、查看总督面板，再使用返回的正常关闭按钮；也可在 `governors` 确实返回 `governor_defer` 时选择该动作。第 70 回合梁派驻后，已实测前一种流程解除残留阻塞。派驻请求本身不自动设置“已考虑”，且不以强制删除通知替代正常流程。
- 伟人操作从当前公开招募时间线重新确认该人确实在列表中，并使用时间线提供的实际标识；不假定索引等于哈希，也不返回时间线中的外国招募者身份。0.3.3 修复了本玩家已获得、尚待认领的伟人被遗漏的问题：当前时间线中的 `Claimant=本玩家` 仍应保留在菜单中，不能将所有非空 `Claimant` 都视为已结束。查询与提交同时保留此类候选，并重新检查 `CanRecruitPerson`、`CanRejectPerson` 或 `CanPatronizePerson`；不读取历史时间线，也不查询招募者文明配置。伟人能力激活属于单位模块。
- `set_policies` 一次提交全部槽位。槽位从 0 开始，政策不能重复，槽位类型必须匹配。查询与配置共用当前规则集的菜单资格：风云变幻要求 `IsPolicyBanned=false`、`CanPolicyBeSlotted=true`、`IsPolicyObsolete=false`；基础版/迭起兴衰使用其原版已解锁且未过时判定。黑暗时代政策不能仅凭 `IsPolicyUnlocked` 放行，也不自行猜测时代限制。规则集或必需 API 不明时不可用。`unlock_policies` 支付正常费用，并检查当前玩家资金。政体切换遵守 UI 的本回合市政完成/初始政体、尚未切换和战略指令权限条件。
- 献力一次提供完整选择列表，数量必须恰好符合当前时代要求；沿用 UI 的逐项 `COMMEMORATE` 请求。英雄时代也适用。
- 创教先由单位操作激活先知；创教选择以已获得信条数量为资格，**不要求已消耗的先知仍在场**。`found_religion` 提供宗教类型、名称、全部初始信条，列表第 1 条必须是 `BELIEF_CLASS_FOLLOWER`，与原版选择顺序一致。`add_belief` 用于已创立宗教的剩余信条选择；中断恢复时若尚未配置任何信条，也只能先选信徒信条。查询用 `first_belief_class` 明示这个要求。可用信条池只在玩家有对应选择资格时查询。外部宗教的信条、城市、信徒和创立者身份不返回。
- `city_build` 可选择普通生产、已有选址项目、区域/建筑修复、特殊工程项目；`append` 控制追加或替换当前生产，单位的 `formation` 可为 `STANDARD`、`CORPS`、`ARMY`。具体项目是否存在、是否可生产，由运行中的规则库及普通引擎检查决定。
- `append=false` 按当前原版 UI 使用 `VALUE_REPLACE_AT` 替换队列第 0 项，保留后续已排队项目；`append=true` 追加。不会用 `VALUE_EXCLUSIVE` 清空后续队列冒充替换当前生产。
- 生产和购买都经过原版的两阶段资格检查：先测试 UI 的排除/显示条件，再测试当前执行条件或指定地块。实机发现单独调用 `CanProduce(...,false,...)` 会误报尚未解锁的建筑；现在查询与动作都补上 `CanProduce(...,true)`，购买同样先检查 `CanStartCommand(...,true,...)`。不通过自行拼凑科技条件替代引擎规则。
- 物品购买还强制使用原版外层的 `PurchaseYield`／信仰购买解锁门槛，并检查对应货币来源的 `CanAfford(cityID, itemHash[, formation])`：金币使用玩家国库，信仰使用玩家宗教对象；普通单位/建筑/区域不添加编队实参，军团/集团军传对应编队。查询与提交都检查，不能因 `CanStartCommand` 返回真而跳过菜单门槛；方法缺失或不能明确确认支付资格时不提供购买动作。区域原版没有单位/建筑的购买货币外层门槛，仍使用正常命令与支付检查。购地则比较该城市实际地块报价与当前国库余额，并保留正常命令合法性检查。
- `city_production` 的军团/集团军候选同时检查原版 `CAN_TRAIN_CORPS` / `CAN_TRAIN_ARMY` 结果标记与对应编队的普通生产/购买资格；不再只列 `STANDARD`，也不会凭客户端枚举存在就假定已解锁编队。
- 只能购买的建筑在遭到掠夺后仍能按原版 UI 使用生产修复。已建成的奇观、区域修复不要求重新选址；查询依据自有建筑/区域的实际存在状态判断。
- 区域和奇观选址只检查当前可见的自有城市地块，支持地图横向环绕；不读取雾中地块内容。购买与选址都使用正常 `CanStartCommand` / `CanStartOperation` 和请求，不修改金币、信仰或地块拥有者。
- `city_manage_citizen` 与原版点击地块相同，是人口/专家/锁定状态的循环操作。调用后重新查询 `city_tiles` 的 `CITIZENS`、`MAX_CITIZENS`、`LOCKED_CITIZENS` 记录确认结果。接口没有伪造独立的“设置专家数量”引擎函数。
- `city_set_focus` 显式设置某项产出为 `favored`、`disfavored`、`neutral`。粮食设为非偏好对应 UI 的粮食忽略；没有将其冒充为“强制停止增长”功能。
- `city_loyalty_choice` 只处理当前玩家 `GetNextRebelledCity` 返回的下一座待决定城市，提供 `keep`/`reject`。不允许任意放弃普通自有城市。征服后的保留/夷平/解放由决策模块处理。

所有 `submitted` 只表示已尝试提交正常请求，不保证引擎最终完成。多个请求组成的操作（政策焦点、创教、献力）与原版 UI 流程一致，连接中断后可能部分完成；应重新观察，不能盲目重发。

## 政体效果与基础槽位预览

`government` 在确认本方已解锁某政体后，才为该政体补充 `description`。说明取自当前运行规则表中的 `InherentBonusDesc` 和 `AccumulatedBonusDesc`（缺失时尝试短说明），因此沿用当前规则集文字，不硬编码商人共和国等政体的效果。影响力与使者说明采用原版政府界面使用的三个规则字段；风云变幻另读取对应 `Governments_XP2.Favor`。这些是政体公开规则预览，不表示当前玩家所有加成合计，也不重建旧版政府界面的静态修改器计算。

附加数值仍使用现有 `id`、`name`、`description`、`value` 格式，以政体类型为前缀，例如 `GOVERNMENT_MERCHANT_REPUBLIC:base_slots:total`：

| 后缀 | `value` 含义 |
| --- | --- |
| `:influence_points_per_turn` | 政体每回合基础影响力点数 |
| `:influence_points_threshold` | 获得使者所需影响力点数 |
| `:influence_tokens_per_threshold` | 每次达到门槛获得的使者数 |
| `:favor_per_turn` | 风云变幻政体每回合基础外交支持 |
| `:base_slots:SLOT_MILITARY`、`:base_slots:SLOT_ECONOMIC`、`:base_slots:SLOT_DIPLOMATIC`、`:base_slots:SLOT_WILDCARD` | 各类基础政策槽位数 |
| `:base_slots:total` | 基础政策槽位合计 |

基础槽位来自原版政体卡片的 `Government_SlotCounts`，并与原版一致将 `SLOT_GREAT_PERSON` 归入通配槽。它不包括文明、奇观或其他额外槽位；实际当前槽位继续由原有 `slot:*` 条目给出。未解锁政体不返回效果和数值。缺失、异常、未翻译的可选文字或数字会省略；槽位表不完整或异常时省略整组基础槽位，避免将局部结果冒充合计。预览不会改变更换政体的资格，无法切换时仍不附动作。

`tests/test_government_preview.py` 覆盖上述文字与数值来源、规则集隔离、缺失字段容错、基础与实际槽位区分，并通过会报错的隐藏字段 getter 验证未解锁政体不被读取。本轮与既有帝国查询、Python 投影合并定向回归共 262 项通过；新增预览尚待实机读取确认。

## 城市成本、进度和报价

`city_production` 为生产候选提供当前城市的实际成本、已投入生产力和预计工期；购买候选提供实际金币或信仰价格，以及原版购买提示中的生产成本/进度。数据来自当前城市的队列和金币组件，**不使用规则表的基础 `Cost` 替代，也不按固定倍数推算价格或工期**。军团、集团军分别调用各自成本和工期接口，共用该单位类型已有的生产进度，与原版界面一致。区域/建筑修复也读取当前队列给出的实际值。

沿用现有 `id`、`name`、`description`、`value` 格式，不增加通用输出字段。每项数值以候选 ID 加后缀关联，例如 `UNIT_WARRIOR:build:production_cost`、`UNIT_WARRIOR:buy:GOLD:purchase_cost`；说明文字标明单位。

| 后缀 | `value` 含义 |
| --- | --- |
| `:production_cost` | 当前城市实际生产成本，单位为生产力点 |
| `:production_progress` | 已投入的生产力点，不是完成比例 |
| `:production_turns` | 当前条件下的预计生产回合数；购买条目不伪造“0 回合生产” |
| `:production_indefinite` | `true` 表示原版 `GetTurnsLeft=-1`，即当前无法完成/界面显示 `999+`；同时省略回合数 |
| `:purchase_cost` | 当前城市的实际报价；物品由候选 ID 的 `GOLD`/`FAITH` 区分，购地为金币 |
| `:purchase_available` | 当前执行和支付条件是否通过；需要选址的物品仍须检查具体位置 |

候选条目自身的 `value=true` **仍只表示需要选址**，不表示可以买得起；不要把它与附加的 `purchase_available` 混用。通过原版显示资格、但当前买不起或暂不可购买的物品，可以返回价格预览和 `purchase_available=false`，**不附动作**。这些预览还遵守原版的购买货币及信仰购买解锁门槛；被排除阶段隐藏的未来物品没有报价。没有取得可靠价格时不凭空生成新的禁用预览。

`city_placement` 在当前可见且合法的位置后附同类生产估算或购买价格，例如 `build:15:21:production_cost`、`buy:GOLD:15:21:purchase_cost`。报价仍来自城市组件，不假装存在“每个地块的独立生产成本”接口。`city_tiles` 给正常菜单中的可见购地目标附 `city_purchase_plot:14:23:purchase_cost`；资金或命令资格不满足时保留报价，移除动作。雾中位置不读报价。

每个可选数字单独读取并校验；缺少 getter、调用异常、负成本、非数值或不合理值只省略相应数字，不把未知写成零，也不破坏其余有效选项。真实零成本、零进度保留。工期可能随产出、政策、编队或其他条件改变；提交动作仍重新检查当时的普通资格。

## 城市供电状态

`city_status` 在规则集明确为风云变幻时，额外读取本方城市的 `GetPower()` 组件。沿用现有 `id`/`value` 条目，不需要新动作或切换城市界面。

| 条目 | 含义与原版接口 |
| --- | --- |
| `power_required` | 电力需求；`GetRequiredPower()` |
| `power_free` | 本地可再生来源供电；`GetFreePower()` |
| `power_temporary` | 本回合消耗资源提供的电力；`GetTemporaryPower()` |
| `power_fully_powered` | `IsFullyPowered()` 明确返回的布尔值，不由供需数字推断 |
| `power_from_active_project` | 完全供电时的 `IsFullyPoweredByActiveProject()`；未知或不适用时省略 |
| `power_status` | 原版分支：`not_required`、`fully_powered` 或 `underpowered` |
| `power_usable` | 原版面板显示的可用电力，包含当前项目完全供电的特殊分支 |

所有电力点数按原版电力面板保留一位小数。状态判断与合计先使用原始数字，再舍入显示；需求虽显示为 `0.0`，并不把一个实际正数误判成无需供电。需求为零优先得到 `not_required`；需求大于零且引擎确认完全供电、当前项目供电为真时，`power_usable=power_required`，否则采用已知来源合计。任一必要字段未知时省略依赖它的状态或合计，绝不填零或假定 `false`；其他城市字段仍可使用。

只读本方已核对所有权的城市，不读取地图、外国城市、输电来源城市或发电范围。API 依据为 GS `UI/Additions/CityPanelPower.lua:36–59`，城市横幅 `UI/CityBanners/CityBannerManager.lua:1441–1455` 也显示同一组来源与项目状态；舍入对照 `Base/Assets/UI/SupportFunctions.lua:473–475`。定向测试覆盖无需供电、供电不足、完全供电、项目供电、舍入边界及缺失接口；新增字段尚待本局实机验收。

## 已派驻总督仍提示待处理

派驻后以 `governors` 回读的 `:assigned`、`:assigned_city` 和建立回合为准；仍存在 `GOVERNOR_IDLE` 提示不等于派驻失败，不应直接重复派驻。先处理对应公开通知并查看原版总督面板，再使用当前面板提供的正常关闭按钮，随后重新读取待办。若新鲜的 `governors` 查询给出 `governor_defer`，也可显式采用该动作确认已查看当前选择。

这不是新增的派驻操作：GS `GovernorPanel.lua:461–470` 的 `PlayerRequestClose` 在需要时调用 `SetTitleConsidered(true)`；普通 `Close`（`:474–485`）明确不做这项确认。派驻确认本身（`GovernorAssignmentChooser.lua:397–408`）只有正常 `ASSIGN_GOVERNOR` 请求与普通关闭。本接口已有公开按钮及 `governor_defer` 对应这条确认路径，不会在派驻后自动附加确认。第 108 回合瑞娜已派驻且仍有通知时，通过“激活该通知→公开关闭按钮→重新读取状态”消除了阻塞；当时没有记录确认标记的前后值，故不把具体原生阻塞原因写成已证实。

## 已核对的原始 UI 依据

安装根目录：`F:/SteamLibrary/steamapps/common/Sid Meier's Civilization VI`。

| 原文件 | 对照内容 |
| --- | --- |
| `DLC/Expansion2/UI/Additions/GovernorPanel.lua:54` | 当前玩家总督、头衔、已发现结社和候选条件 |
| `DLC/Expansion2/UI/Additions/GovernorPanel.lua:461`、`:476`、`:760` | 显式关闭按钮设置 `SetTitleConsidered(true)`；普通程序关闭不设置该标记 |
| `DLC/Expansion2/UI/Additions/GovernorDetailsPanel.lua:337` | 任命与晋升请求，参数使用 Index |
| `DLC/Expansion2/UI/Additions/GovernorAssignmentChooser.lua:398` | 派驻请求及城市拥有者参数 |
| `DLC/Expansion2/UI/Additions/GovernorAssignmentChooser.lua:166`、`:228`、`:298`、`:307`、`:312` | 城邦名单使用存活小文明、可接收影响力、已遇见和普通派驻资格；排除当前已派驻城市；外部忠诚压力控件隐藏；菜单显示到任时长，按钮关联拥有者／城市 ID |
| `DLC/Expansion2/UI/Additions/GovernorPanel.lua:418`、`:722` | 被排除总督和世界议会期间的派驻禁用状态 |
| `DLC/Expansion2/UI/Additions/GovernorSupport.lua:110` | 不可派驻结社、隐藏晋升规则 |
| `DLC/Expansion2/UI/Additions/GovernorSupport.lua:12`、`:72` | 当前派驻、到任与被排除状态 |
| `DLC/Expansion2/UI/Additions/GovernorSupport.lua:12`、`:79` | 本方总督面板读取当前派驻城市名，不以当前地图视野过滤；本接口摘要仍额外限制为已遇见、符合城邦菜单范围的目标 |
| `Base/Assets/UI/Popups/GreatPeoplePopup.lua:701`、`:710`、`:728` | 当前页使用 `GetTimeline`，不排除本玩家待认领者；对当前候选检查可招募/赞助/放弃与价格 |
| `Base/Assets/UI/Popups/GreatPeoplePopup.lua:885` | 正常伟人请求 |
| `Base/Assets/UI/Screens/GovernmentScreen.lua:629` | 保留现政体的已考虑标记 |
| `Base/Assets/UI/Screens/GovernmentScreen.lua:858` | 政体切换完整 UI 资格 |
| `Base/Assets/UI/Screens/GovernmentScreen.lua:1537` | 原子政策槽清单及付费解锁 |
| `Base/Assets/UI/Screens/GovernmentScreen.lua:2427`、`:2441` | 政体卡片基础槽位及当前规则表的固有／积累效果文案；伟人槽归入通配槽 |
| `Base/Assets/UI/Screens/GovernmentScreen.lua:2284` | 当前玩家实际政策槽位，与政体卡片基础槽位分开读取 |
| `DLC/Expansion2/UI/Replacements/GovernmentScreen_Expansion2.lua:8` | 风云变幻覆盖基础版的政策可用性判断，检查禁用、可插槽和过时状态 |
| `DLC/Expansion2/UI/Replacements/GovernmentScreen_Expansion2.lua:36` | 政体外交支持，以及影响力点数／门槛／使者数量的原版提示 |
| `DLC/Expansion2/UI/Additions/DedicationPopup.lua:54` | 当前献力选项、数量与时代效果 |
| `DLC/Expansion2/UI/Additions/DedicationPopup.lua:205` | 献力逐项提交 |
| `Base/Assets/UI/ReligionScreen.lua:116` | 自有宗教、已获/已选信条 |
| `Base/Assets/UI/ReligionScreen.lua:308` | 选择万神殿/创教/增加信条的 UI 阶段 |
| `Base/Assets/UI/ReligionScreen.lua:446` | 可用信条列表规则 |
| `Base/Assets/UI/ReligionScreen.lua:590` | 万神殿请求 |
| `Base/Assets/UI/ReligionScreen.lua:901` | 创教及新增信条请求 |
| `Base/Assets/UI/ReligionScreen.lua:831` | 第一条宗教信条仅从信徒类别选择 |
| `Base/Assets/UI/Panels/ProductionPanel.lua:293` | 普通、军团/集团军生产与购买 |
| `Base/Assets/UI/Panels/ProductionPanel.lua:1961`、`:2052`、`:2126`、`:2221` | 区域、建筑、单位、项目按 `row.Index` 读取城市队列实际成本和进度 |
| `Base/Assets/UI/Panels/ProductionPanel.lua:1994`、`:2073`、`:2138`、`:2231` | 区域/项目工期传类型字符串，建筑/单位工期传哈希 |
| `Base/Assets/UI/Panels/ProductionPanel.lua:2164`、`:2176` | 军团/集团军分别用 `GetUnitCorpsCost`、`GetUnitArmyCost`，工期带编队参数 |
| `Base/Assets/UI/Panels/ProductionPanel.lua:1639`、`:1673`、`:1688`、`:1704`、`:1770`、`:1820` | 原版禁用购买条目仍可显示；两种货币均经 `city:GetGold():GetPurchaseCost(yieldIndex,itemHash[,formation])` 取价 |
| `Base/Assets/UI/Panels/ProductionPanel.lua:1653`、`:1690`、`:1706`、`:1756`、`:1792` | 国库/宗教 `CanAfford` 独立检查当前支付资格 |
| `Base/Assets/UI/Panels/ProductionPanel.lua:2084`、`:2195` | 单位/建筑购买预览还受购买货币与信仰购买解锁门槛约束 |
| `Base/Assets/UI/Panels/ProductionPanel.lua:817`、`:961`、`:1048` | `-1` 工期对应 `999+`，不能作为负回合输出 |
| `Base/Assets/UI/StrategicView_MapPlacement.lua:44` | 奇观及区域选址请求 |
| `Base/Assets/UI/ProductionHelper.lua:195` | 队列移除与移动 |
| `Base/Assets/UI/WorldView/PlotInfo.lua:55` | 人口点击、城市地块购买与交换 |
| `Base/Assets/UI/WorldView/PlotInfo.lua:356` | 人口/专家/锁定数的命令目标列表 |
| `Base/Assets/UI/WorldView/PlotInfo.lua:274`、`:298` | 购地目标来自正常命令菜单，`GetPlotPurchaseCost(plotIndex)` 取价，并按国库余额禁用按钮 |
| `Base/Assets/UI/Panels/CityPanel.lua:443` | 产出偏好参数 |
| `DLC/Expansion2/UI/Additions/DisloyalCityChooser.lua:5` | 忠诚度归附的保留/拒绝 |

Lua 模拟测试涵盖全部查询的可执行动作载荷、未发现结社隔离、外国城市视野检查顺序、精确伟人标识、政策槽位、收费、先知消耗后创教、雾中人口数据不返回、选址先可见再合法性检查、生产队列及忠诚度待处理身份。

`tests/test_city_costs.py` 进一步用真实 Lua VM 检查不同种类的 Index/Hash/类型字符串签名、军团与集团军、两种购买货币、修复成本、缺失/异常数值、不可负担的只读报价、购买货币解锁门槛、支付资格重查、可见购地价格、外国城市零读取，以及现有 Python 字段投影。0.3.4 同局第 45～48 回合已实测生产报价、水渠/学院选址报价、不可购买价格预览及金币购买：建造者显示 130 金币，第 48 回合正常购买后国库从 163.3203125 减为 33.3203125，并出现新建造者。军团、信仰购买等未触发分支仍不能据此称已实机验收。

## 实机验收重点

参考项目对照后的城市防御／忠诚方向、城市宗教分布、科技胜利自身进度、伟人点数与完整报价、时代当前状态见 [城市与内政领域对照](REFERENCE_PARITY_EMPIRE.md)。新增查询均保留正常菜单资格和玩家可见范围；其离线验证与下述历史实机记录分开记载。

尚未把模拟测试视为本机游戏已验证。需要在游戏中逐项确认新接口确实改变状态，尤其是：城市人口点击效果、区域/奇观覆盖改良的确认、创教/献力的多请求队列，以及不同规则版本的可选 API。遇到缺失 API 或不符参数时停止该能力并返回不可用，不切换为高权限修改。

当前试玩的刚果对局不能创立宗教，因此“先知触发→创教→按顺序配置信条”的功能仅有原版源码对照与本地回归，尚未实机验证；不能用这场试玩声称已验收创教。

0.3.3 续局第 43 回合已实机验证伟人待认领修复：`great_people` 返回希帕蒂娅的能力说明、招募与放弃动作；正常招募后出现对应科学家单位，`ENDTURN_BLOCKING_CLAIM_GREAT_PERSON` 阻塞消失。此项验证覆盖本玩家待认领与招募流程，未据此声称所有伟人能力、赞助或放弃均已实机验证。过程见 [2026-10-27 续局记录](LIVE_TEST_CONTINUATION_2026-10-27.md)。

2026-10-27 对当前第 1 回合、0 城市的游戏执行了仅只读诊断，脚本 `scripts/live_empire_api_check.py`，结果 `artifacts/live-empire-api-check.json`：当时纳入检查的 73 个固定枚举/参数均为数值，24 个检查到的自有玩家与城市管理 API 均存在；规则布尔列实际为布尔值，表中没有的列为 `nil`。三种城市地块模式的 `UI.GetInterfaceModeParameter` 在当前默认模式下返回对应数值 flag，未出现 `nil`。没有执行任何游戏动作，故这些结果不能代替城市操作或后期玩法的实机验收。静态 API 签名复核另修正了军团/集团军候选发现遗漏，依据 `ProductionPanel.lua:1679`、`:2157`。随后实际建城发现的生产误报按照 `ProductionPanel.lua:1911,2026,2038,2124,2214` 的两阶段检查修复；替换队列首项依据同文件 `GetBuildInsertMode():2888`，后续实机结果由主测试记录记载。
