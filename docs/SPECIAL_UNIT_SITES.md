# 专业单位的原版高亮候选地点

`inspect_game("special_unit_sites", {"unit_id": ID})` 查询本方单位在原版选中单位图层中高亮的候选地点。每个地点 N 返回三个固定标量条目：`site:N:x`、`site:N:y`、`site:N:purpose`；用途为 `excavate`、`national_park`、`great_person` 或 `rock_concert`。序号只用于组织本次结果，不是持久地点 ID。

考古和国家公园分支只接受本方考古能力单位或拥有国家公园使用次数的单位。自然学家等单位必须同时满足静态 `ParkCharges > 0` 和本方 `GetParkCharges() > 0`；`unit_details` 新增可选 `park_charges`，正常零次返回 0，接口缺失、异常或值无效时省略。考古学家原版没有在此图层中读取数值挖掘次数，本实现不虚构次数，使用正常单位面板的宽松 `EXCAVATE` 能力检查和该考古学家本身的候选列表。

参考项目对照后，同一查询也支持本方伟人和摇滚乐队。伟人必须由本方 `GetGreatPerson():IsGreatPerson()` 确认、仍有次数，且该人物静态 `ActionEffectTileHighlighting` 为真；只读取 `GetActivationHighlightPlots()`，不读取被动作用范围、不按职业猜区域。先知使用正常 `FOUND_RELIGION` 能力门；其他伟人使用正常激活 command 门。摇滚乐队要求精确 `UNIT_ROCK_BAND`、正常演出能力和该乐队 `GetRockBand():GetActivationHighlightPlots()`。列表只说明原版高亮，不提供城市私有信息或未公开的演出结果。

候选可位于**已探索但当前有迷雾**的地块，仅返回原版高亮的坐标和固定用途。未探索坐标不返回；无论是否有迷雾，都不读取地块资源、文物来源、单位、归属、地形、产出或魅力。不扫描整张地图、不自行计算选址、不改变选中单位或打开图层。国家公园列表只传本方玩家 ID；坐标不包含四格公园的分组或边界推断。

这些候选不是移动许可，也不表示单位现在就能使用能力。正常移动到目标后，重新查询 `unit_actions({unit_id})`，只提交当次返回的挖掘、建园、伟人激活／先知创教或摇滚演出动作。文物来源通过 `archaeology({})` 查询；若来源弹窗已显示，则使用当次公开 `popup_action`。未遇见文明身份仍按 P05 隐去。

结果在 Lua 和 Python 两层检查：原请求单位 ID、本方身份、固定图层来源、单位资格、原版候选成员和已探索状态。候选读取结束后重查单位身份、国家公园次数、核心忙碌状态及已探索状态。坐标按 y、x 排序、去重；最多返回 512 个地点，异常或超限不发布部分结果。缺少所需 API 时返回 `supported=false`。没有候选、单位类型不适用或能力已耗尽时返回受支持的空列表。

## 本机原版依据

- `DLC/Expansion2/UI/Replacements/SelectedUnit_Expansion2.lua:19–21、47–64`：只在核心不忙且单位属于本地玩家时，将考古学家的 `GetArchaeology():GetActivationHighlightPlots()` 或 `Game.GetNationalParks():GetPossibleParkTiles(playerID)` 送入 `Great_People` 高亮；国家公园分支同时检查静态和剩余公园次数。
- 同文件 `30–46、65–74`：伟人激活图层与摇滚乐队候选同样使用 `Great_People`；伟人的被动范围另有 `GetAreaHighlightPlots()`，本接口不读取。
- `Base/ArtDefs/Overlay.artdef:18984–19052`：`Great_People` 的 `GreatPeopleBorder` 设置 `FOWStateAlpha_Hidden=0`、`FOWStateAlpha_Revealed=1`、`FOWStateAlpha_Visible=1`（19028–19038）。因此已探索迷雾中的候选边框属于正常可见高亮，不能据此开放地块实时详情。
- `Base/Assets/UI/Panels/UnitPanel.lua:669–677`：普通动作先做 `CanStartOperation(unit, hash, nil, true)` 宽松 UI 能力检查，再单独检查当前位置能否实际执行。地点查询只使用前者，不因单位尚未站在遗址／公园候选地而丢失所有候选。
- `DLC/Expansion2/UI/Replacements/UnitPanel_Expansion2.lua:138–143`：只有静态 `ParkCharges > 0` 的单位才展示 `GetParkCharges()`。
- `Base/Assets/UI/Popups/ChooseArtifact.lua:11–65、78–87`：只读取本方待提取文物的考古学家，按事件类型提供一或两个来源按钮，使用 `CHOOSE_ARTIFACT_PLAYER` 正常提交。

考古／公园首批使用真实 Lua VM、生产 JSON 编码器和 Python 投影做离线回归，覆盖已探索迷雾、未探索过滤、非本方单位、错误类型、耗尽次数、缺 API、异常、同次读取失效及请求身份绑定。该阶段三组测试合计 **261 项通过**（2026-10-27，3.22 秒）。伟人／摇滚扩展及关联内政测试最新合计 **352 项通过**，见 [领域对照与验证](REFERENCE_PARITY_EMPIRE.md)。独立只读复核已确认图层绑定、迷雾边界及请求身份绑定；新查询尚未进行实机验收。
