# 可见地块的悬崖标记

地图查询提供三个独立、可选的布尔字段，名称保留原版 API 的方向语义：

| 字段 | 原版 API |
| --- | --- |
| `is_nw_of_cliff` | `plot:IsNWOfCliff()` |
| `is_w_of_cliff` | `plot:IsWOfCliff()` |
| `is_ne_of_cliff` | `plot:IsNEOfCliff()` |

来源为本机 Steam 安装的 `Base/Assets/UI/ToolTips/PlotToolTip.lua:673–675`；原版在该文件 `342–344` 判断任一标记为真时显示悬崖文字。风云变幻 `DLC/Expansion2/UI/Replacements/PlotTooltip_Expansion2.lua:207–208` 沿用同样判断。没有把 `IsNWOfCliff` 改称“该地块西北侧的悬崖”：这里保留的是引擎原始方向约定。

三个 getter 都在 `revealed == true` 且 `visible == true` 后才调用。未探索或已探索但在迷雾中的格子不调用、不返回这些字段；重新进入迷雾也不保留上次读数。每个 API 缺失、抛错或返回非布尔值时，只省略对应字段，不把未知当作 `false`。Python 投影再次检查可见性与严格布尔类型。

此查询不读取邻格来补齐其他边、不返回隐藏地形，也不改变移动操作的资格判定。悬崖标记只能辅助解释当前可见地形；它本身不能证明某次历史移动绕路的原因。已完成离线 Lua 与投影边界测试，尚未把此前实机绕路归因于悬崖。
