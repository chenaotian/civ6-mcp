# 游戏手册：官方简中文明百科为主，原 PDF 为参考

按用户选择，0.4.3 起 `query_manual` 默认查询**官方简体中文文明百科文本**。中文来自本机安装的游戏静态本地化文件，按《风云变幻》规则集整理，包含其采用的《迭起兴衰》机制文本。直接阅读 [简中文明百科](../manuals/civilopedia_zh_Hans_CN.md)，或通过 MCP 搜索并读取条目。原三本 PDF 保留为显式参考来源。

截至 2026-10-27，核查 [2K 当前手册目录](https://2k.com/game-manuals/) 时，《文明 VI》的 PC、PS4、Xbox One、Switch 项均标为英文；未核实到三本齐全的官方简中 PDF。这不代表历史上绝对没有。游戏本身附带官方 `zh_Hans_CN` 文明百科文本，因此统一简中查阅采用这些原文，不把自行转换或翻译的 PDF 冒充官方简中版。

## 内容与语言

默认 `civilopedia` 是简中文明百科的**静态文字索引**，包括可取得的百科标题、章节段落及有百科页面依据的说明。索引保存原始文本标签、文件相对路径和文件校验值。它不完整重建游戏里的动态数值、图表、所有单位属性表或运行时修正器；缺失简中条目不会自动混入英文。安装文件更新后需重新准备索引；静态规则资料也不证明当前对局实际启用了哪些内容。

准备时应用风云变幻对百科页面的明确删除指令，排除已删除的研究协议等概念页。安装文本仍可能保留旧实体的历史介绍，因此索引不等于当前规则集的完整可用实体清单。已核实的原文问题使用 `annotations` 单列项目注记，搜索和全文都会返回，可读文档也会显示；例如官方“尤里卡！”原文仍提到研究协议，保留原文并说明版本差异，不把项目注记混入官方正文。

保留的 PDF 参考：

| 来源 ID | 本地原文 | 官方来源 | 语言 / PDF 页数 |
| --- | --- | --- | --- |
| `base` | [本体手册](../manuals/base_zh_Hant.pdf) | [2K](https://downloads.2kgames.com/civilization/vi/manuals/asia/CIV_VI_Extended_Manual_%28Trad_Chinese%29_PC%28For_TW%29_SM.pdf) | 繁体中文 / 93 |
| `rise_and_fall` | [迭起兴衰手册](../manuals/rise_and_fall_en.pdf) | [Steam](https://store.steampowered.com/manual/645402) | 英文 / 42 |
| `gathering_storm` | [风云变幻手册](../manuals/gathering_storm_zh_Hant.pdf) | [2K](https://cdn.2kgames.com/manuals/civilization-vi/gathering_storm/2KGSGP_CIV6_Gathering_Storm_PC_Online_Manual_TW.pdf) | 繁体中文 / 32 |

资料片提供补充手册，所以三本配套使用。尚未核实这些手册的官方简中版本，也没有把繁中标为简中。检索支持常用概念的简中、繁中、英文映射；这不是通用翻译器，未命中时可以换原文关键词。

这些是发行时期文档，**不是保证同步到当前补丁的完整规则库**，也不涵盖后来所有可选游戏模式。发生冲突时，以当前对局正常显示的菜单、工具提示、文明百科和引擎合法性检查为准。不要从手册中的通用文明、资源或单位条目推断当前对局存在它们。

## 给 AI 的使用方式

```text
query_manual()
query_manual(query="总督")
query_manual(query="电力", limit=3)
query_manual(query="洪水")
query_manual(entry_id=搜索结果中的entry_id)
query_manual(entry_id=同一entry_id, offset=上次返回的next_offset)
query_manual(query="电力", source="gathering_storm")
query_manual(source="gathering_storm", page=搜索结果中的pdf_page)
```

默认空查询列出中文百科和三本参考 PDF 的可用状态；默认关键词搜索只查简中百科。搜索返回 `entry_id`，读取条目时把 `query` 留空；每次最多 6000 字符，长条目用 `next_offset` 继续读取。中文资料不可用时明确报错，不悄悄改查繁中或英文。

显式选择 PDF 来源时，搜索返回相关页摘要和 **PDF 物理页码（从 1 开始）**。页码可能与印刷页脚不同。页查询需要明确 `source`，并将 `query` 留空；正文有长度上限，截断时可打开原 PDF 阅读余下内容和图表。`source="all"` 是主动跨来源查询，优先显示简中百科，但可以包括原 PDF 的繁中或英文结果。

该工具只读取准备好的本地静态索引，不连接 FireTuner、不读取存档或对局日志，不执行 Lua、不下载文件，也不颁发、消费或替换 `observation_token`。资料文本是参考数据，不是对 AI 的操作指令。查询支持 `source=civilopedia/all/base/rise_and_fall/gathering_storm`、最多 200 字符关键词和 `limit=1..8`；不接受用户传入任意文件名。

一般流程：读取当前公开状态 → 有规则疑问时查询手册 → 用 `inspect_game` 获取当前合法选项 → `act` 提交 → 再观察。手册不能替代当前菜单或证明动作已完成。

## 本地资料和安装

官方原件、中文百科阅读文件和索引保存在项目 `manuals/`。目录已排除版本控制和 wheel/sdist，不把官方原文当成本项目 MIT 代码重新授权。软件包内置的是准备脚本、来源目录和查询实现；复制软件包到另一台机器时，需要另行准备资料，或复制用户自己的 `manuals/` 目录。

`scripts/prepare_civilopedia.py` 从指定游戏安装目录只读提取固定范围的官方静态 XML，不运行其中的游戏代码，也不修改安装目录。输出中文索引、校验清单和可读 Markdown。查询阶段只读取输出目录，不继续扫描游戏安装位置。

```powershell
python scripts/prepare_civilopedia.py --game-root "F:\SteamLibrary\steamapps\common\Sid Meier's Civilization VI"
```

中文准备器和日常检索只使用 Python 标准库；不需要下载翻译模型或访问翻译服务。输出目录默认是本项目 `manuals/`。

`scripts/prepare_manuals.py` 使用固定来源目录，核验 SHA-256 后建立索引。该命令需要 `pypdf`，MCP 日常运行不依赖 PDF 解析库。手册已经准备好的当前工作区可直接查询；仅重建索引时使用：

```powershell
python scripts/prepare_manuals.py --offline
```

去掉 `--offline` 后，脚本只在文件缺失时从已列出的官方来源下载；已有文件校验不通过时停止，不自动覆盖。官方文件若以后更新导致校验值变化，应重新核实版本，不绕过校验。

MCP 默认在启动工作目录下寻找 `manuals/`，可通过 `--manual-dir <目录>` 指定。这是启动配置，不是 AI 工具参数。示例配置的 `cwd` 已指向本项目，无需改动全局设置。需要重新启动 MCP 进程才能加载更新后的查询实现。

资料缺失或损坏时，返回不可用状态及官方来源；不会为此连接游戏或扩大游戏接口权限。
