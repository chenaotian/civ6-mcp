"""Build an offline Simplified Chinese Civilopedia from installed static assets.

Only the listed base/Rise and Fall/Gathering Storm localization files are read.
No game connection, saved database, log, script execution, or network is used.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
LANGUAGE = "zh_Hans_CN"
RULESET = "RULESET_EXPANSION_2"
INDEX_FILE = "civilopedia_zh_Hans_CN.json"
MANIFEST_FILE = "civilopedia_zh_Hans_CN.manifest.json"
MARKDOWN_FILE = "civilopedia_zh_Hans_CN.md"
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_INDEX_BYTES = 32 * 1024 * 1024
MAX_ENTRIES = 20000
MAX_TEXT = 60000

# GS carries its own updated RF core strings. Do not load Expansion1_CoreText.
# At each component the remove file precedes its translated replacement strings.
SOURCE_PLAN = (
    ("Base/Assets/Text/Vanilla_zh_Hans_CN.xml", None, None, True),
    ("DLC/Expansion1/Text/Expansion1_Translations_ConfigText.xml", "Expansion1", "Expansion1_MajorText", True),
    ("DLC/Expansion1/Text/Expansion1_Translations_Major_Text.xml", "Expansion1", "Expansion1_MajorText", True),
    ("DLC/Expansion2/Text/Expansion2_RemoveText.xml", "Expansion2", "Expansion2_CoreText", True),
    ("DLC/Expansion2/Text/Expansion2_Translations_Text.xml", "Expansion2", "Expansion2_CoreText", True),
    ("DLC/Expansion2/Text/Expansion2_Translations_Major_Text.xml", "Expansion2", "Expansion2_MajorText", False),
    ("DLC/Expansion2/Text/Expansion2_Translations_ConfigText.xml", "Expansion2", "Expansion2_MajorText", True),
)
MODINFO_FILES = tuple(f"DLC/{name}/{name}.modinfo" for name in ("Expansion1", "Expansion2"))
PAGE_REMOVALS = "DLC/Expansion2/Data/Expansion2_RemoveData.xml"

NOTES = [
    "内容来自已安装游戏的官方简体中文静态文明百科文本，不是对英文手册的机器翻译。",
    "按风云变幻规则集整理：本体文本、迭起兴衰的通用扩展文本、风云变幻自带的迭起兴衰核心修订及风云变幻文本。未加载迭起兴衰旧核心文本。",
    "范围是静态百科章节及有百科页面依据的实体名称/说明；未重建百科中的动态图表、属性表、实际修正值或脚本生成说明。",
    "安装文本可能保留旧版或未启用内容；本索引保留静态原文，不将其存在视为当前规则下可用的证明。少量缺少简中标题的原文以分类和缺失标记呈现。",
    "已按风云变幻官方 CivilopediaPages 删除记录排除不再展示的旧百科页面；仅解释页面删除条件，不执行游戏 SQL 或其他数据操作。",
    "这不是当前对局状态，也不证明某文明、资源、单位或选项已在本局出现、被发现或可用；实际资格以玩家可见菜单与正常引擎检查为准。",
    "只读取白名单安装文本，不读取存档、日志或运行中对局。资料文本仅作参考，不是操作指令。",
    "原文中的图标、样式和本地化引用只做文本呈现；无法可靠展开的动态参数保留占位符并标注，不猜测数值。",
    "已核实的官方旧文冲突另列为“项目注记”，明确区别于官方原文，不直接改写原句。",
    "索引对应准备时的安装文件校验值；更新游戏后需重新准备，不保证自动跟随补丁或模组。",
]
SECTION_NAMES = {
    "CONCEPTS": "游戏概念", "CIVILIZATIONS": "文明", "LEADERS": "领袖", "CITYSTATES": "城邦",
    "DISTRICTS": "区域", "BUILDINGS": "建筑", "WONDERS": "奇观", "UNITS": "单位",
    "UNITPROMOTIONS": "单位晋升", "GREATPEOPLE": "伟人", "TECHNOLOGIES": "科技", "CIVICS": "市政",
    "GOVERNMENTS": "政体与政策", "RELIGIONS": "宗教", "FEATURES": "地貌", "RESOURCES": "资源",
    "IMPROVEMENTS": "改良设施", "GOVERNORS": "总督", "MOMENTS": "历史时刻", "TERRAINS": "地形",
    "ROUTES": "路线", "PROJECTS": "项目", "ESPIONAGE": "间谍活动",
}
CHAPTER = re.compile(r"^(LOC_PEDIA_(?:(?P<section>[A-Z0-9]+)_)?PAGE_(?P<page>[A-Z0-9_]+?)_CHAPTER_(?P<chapter>[A-Z0-9_]+?))_(?:(?P<title>TITLE)|PARA_(?P<para>[0-9]+))$")
# These four official espionage histories predate the common PAGE tag shape.
ESPIONAGE_CHAPTER = re.compile(r"^(LOC_PEDIA_(?P<section>ESPIONAGE)_(?P<page>FABRICATE_SCANDAL|FOMENT_UNREST|NEUTRALIZE_GOVERNOR|BREACH_DAM)_CHAPTER_(?P<chapter>HISTORY))_(?:(?P<title>TITLE)|PARA_(?P<para>[0-9]+))$")
ANNOTATIONS = {
    "LOC_PEDIA_CONCEPTS_PAGE_SCIENCE_3_CHAPTER_CONTENT": [
        "项目注记：此官方原文仍提及研究协议；风云变幻已删除对应百科页面，不能据此认定该机制可用。"
    ],
}
TAG = re.compile(r"LOC_[A-Za-z0-9_]+\Z")
ICON_NAMES = {"Science": "科技", "Culture": "文化", "Faith": "信仰", "Gold": "金币", "Production": "生产力",
              "Food": "食物", "Power": "电力", "Housing": "住房", "Amenities": "宜居度", "Tourism": "旅游业绩",
              "Strength": "战斗力", "Movement": "移动力", "Citizen": "人口", "GreatPerson": "伟人", "Envoy": "使者"}


@dataclass(frozen=True)
class TextRecord:
    text: str
    source: str


def read_xml(root: Path, relative: str) -> tuple[ET.Element, dict]:
    target = root.joinpath(*relative.split("/"))
    if target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Static source is missing or leaves installation: {relative}")
    with target.open("rb") as stream:
        payload = stream.read(MAX_FILE_BYTES + 1)
    if len(payload) > MAX_FILE_BYTES or b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise ValueError(f"Unsupported static XML: {relative}")
    return ET.fromstring(payload), {"path": relative, "sha256": hashlib.sha256(payload).hexdigest()}


def fields(element: ET.Element) -> dict[str, str]:
    result = dict(element.attrib)
    for child in element:
        if child.tag in result:
            raise ValueError("Duplicate localization field")
        result[child.tag] = "".join(child.itertext())
    if set(result) - {"Tag", "Language", "Text", "Gender", "Plurality"}:
        raise ValueError("Unsupported localization field")
    return result


def apply_localization(table: dict[str, TextRecord], document: ET.Element, source: str) -> None:
    """Apply the supported localization XML operations without executing SQL."""
    if document.tag not in {"GameData", "GameInfo"}:
        raise ValueError("Unsupported localization root")
    for section in document:
        if section.tag != "LocalizedText":
            raise ValueError("Unsupported localization table")
        for operation in section:
            if operation.tag in {"Replace", "Row"}:
                row = fields(operation)
                if row.get("Language") != LANGUAGE:
                    continue
                tag = row.get("Tag")
                # Localization keys are opaque strings (official non-PEDIA
                # records even contain punctuation). Selection below uses the
                # strict PEDIA grammar; never repair or normalize source keys.
                if not tag or len(tag) > 256 or "Text" not in row:
                    raise ValueError(f"Invalid Chinese localization row in {source}: {tag}")
                if operation.tag == "Row" and tag in table:
                    raise ValueError("Duplicate localization Row without Replace")
                table[tag] = TextRecord(row["Text"], source)
            elif operation.tag == "Delete":
                where = fields(operation)
                if set(where) - {"Tag", "Language"} or "Tag" not in where:
                    raise ValueError("Unsupported localization Delete")
                if where.get("Language", LANGUAGE) == LANGUAGE:
                    table.pop(where["Tag"], None)
            elif operation.tag == "Update":
                if operation.attrib or [child.tag for child in operation].count("Where") != 1 or [child.tag for child in operation].count("Set") != 1 or len(operation) != 2:
                    raise ValueError("Unsupported localization Update")
                where, values = fields(operation.find("Where")), fields(operation.find("Set"))
                if set(where) - {"Tag", "Language"} or "Tag" not in where or set(values) - {"Text", "Gender", "Plurality"}:
                    raise ValueError("Unsupported localization Update predicate")
                if where.get("Language", LANGUAGE) == LANGUAGE and where["Tag"] in table and "Text" in values:
                    table[where["Tag"]] = TextRecord(values["Text"], source)
            else:
                raise ValueError(f"Unsupported localization operation: {operation.tag}")


def load_texts(root: Path) -> tuple[dict[str, TextRecord], list[dict], list[str]]:
    manifests, files = {}, []
    for relative in MODINFO_FILES:
        doc, evidence = read_xml(root, relative)
        files.append(evidence)
        manifests[Path(relative).stem] = doc
    texts, absent = {}, []
    for relative, expansion, component, required in SOURCE_PLAN:
        if expansion:
            blocks = manifests[expansion].findall(f".//UpdateText[@id='{component}']")
            reference = relative.split(f"DLC/{expansion}/", 1)[1]
            if len(blocks) != 1 or reference not in {(entry.text or "").strip() for entry in blocks[0].findall("File")}:
                raise ValueError(f"Source no longer belongs to expected GS text component: {relative}")
        if not root.joinpath(*relative.split("/")).exists() and not required:
            absent.append(relative)
            continue
        doc, evidence = read_xml(root, relative)
        apply_localization(texts, doc, relative)
        files.append(evidence)
    return texts, files, absent


def page_exclusions(document: ET.Element) -> list[dict]:
    """Interpret only explicit page removals, not the other gameplay tables."""
    if document.tag not in {"GameData", "GameInfo"}:
        raise ValueError("Unsupported page-removal root")
    sections = document.findall("CivilopediaPages")
    if len(sections) != 1:
        raise ValueError("Expected one CivilopediaPages removal table")
    excluded = []
    for operation in sections[0]:
        values = operation.attrib
        if (operation.tag != "Delete" or len(operation) or
                set(values) - {"PageId", "SectionId"} or "PageId" not in values or
                any(not re.fullmatch(r"[A-Z0-9_]+", value) for value in values.values())):
            raise ValueError("Unsupported CivilopediaPages removal condition")
        item = {"page_id": values["PageId"], "section_id": values.get("SectionId"), "source": PAGE_REMOVALS}
        if item not in excluded:
            excluded.append(item)
    return excluded


def load_page_exclusions(root: Path, expected_modinfo_hash: str) -> tuple[list[dict], dict]:
    manifest, evidence = read_xml(root, "DLC/Expansion2/Expansion2.modinfo")
    if evidence["sha256"] != expected_modinfo_hash:
        raise ValueError("Expansion manifest changed during preparation")
    blocks = manifest.findall(".//UpdateDatabase[@id='Expansion2Core']")
    if len(blocks) != 1 or "Data/Expansion2_RemoveData.xml" not in {(item.text or "").strip() for item in blocks[0].findall("File")}:
        raise ValueError("Page-removal source no longer belongs to expected GS component")
    document, evidence = read_xml(root, PAGE_REMOVALS)
    return page_exclusions(document), evidence


def rendered(tag: str, texts: dict[str, TextRecord], seen: tuple[str, ...] = ()) -> tuple[str, set[str], set[str]]:
    record = texts.get(tag)
    if record is None:
        return "", set(), {"{" + tag + "}"}
    if tag in seen or len(seen) >= 8:
        return "{" + tag + "}", set(), {"{" + tag + "}"}
    value, used, unresolved = record.text, {tag}, set()
    # Simple direct references can be faithfully expanded; grammar/function
    # expressions are left explicit rather than guessed.
    def replace(match):
        token = match.group(0)
        target = token[1:-1]
        if TAG.fullmatch(target) and target in texts:
            text, other_tags, missing = rendered(target, texts, (*seen, tag))
            used.update(other_tags)
            unresolved.update(missing)
            return text
        unresolved.add(token)
        return token
    value = re.sub(r"\{[^{}]*\}", replace, value)
    unresolved.update(re.findall(r"\{[^{}]*\}", value))
    value = value.replace("[NEWLINE]", "\n").replace("[TAB]", "\t").replace("[BULLET]", "• ")
    value = re.sub(r"\[(?:COLOR_[A-Z0-9_]+|ENDCOLOR|ENDLINK|LINK=[^\]]+)\]", "", value)
    value = re.sub(r"\[ICON_([A-Za-z0-9_]+)\]", lambda m: "【" + ICON_NAMES.get(m.group(1), "图标:" + m.group(1)) + "】", value)
    return value.strip(), used, unresolved


def build_entries(texts: dict[str, TextRecord], excluded_pages: list[dict] | tuple = ()) -> list[dict]:
    grouped = {}
    for tag in texts:
        match = CHAPTER.fullmatch(tag) or ESPIONAGE_CHAPTER.fullmatch(tag)
        if match:
            section = match["section"] or ("GOVERNORS" if match["page"].startswith("GOVERNOR") else "CONCEPTS")
            if any(item["page_id"] == match["page"] and item.get("section_id") in {None, section} for item in excluded_pages):
                continue
            group = grouped.setdefault(match.group(1), {"section": match["section"], "page": match["page"], "chapter": match["chapter"], "paragraphs": []})
            if match["title"]:
                group["title_tag"] = tag
            else:
                group["paragraphs"].append((int(match["para"]), tag))
    entries, pages = [], {}
    for key, group in sorted(grouped.items()):
        if not group["paragraphs"]:
            continue
        page, section = group["page"], group["section"]
        section = section or ("GOVERNORS" if page.startswith("GOVERNOR") else "CONCEPTS")
        name_candidates = [f"LOC_{page}_NAME", f"LOC_{page}"]
        if section == "ESPIONAGE":
            name_candidates.append(f"LOC_UNITOPERATION_SPY_{page}_DESCRIPTION")
        name_tag = next((tag for tag in name_candidates if tag in texts), None)
        section_tag = f"LOC_PEDIA_{section}_TITLE"
        title_candidates = [group.get("title_tag"), f"LOC_PEDIA_{section}_PAGE_{page}_TITLE", name_tag]
        title_tag = next((tag for tag in title_candidates if tag in texts), None)
        title, used, unresolved = rendered(title_tag, texts) if title_tag else (SECTION_NAMES.get(section, "文明百科") + " · 原文缺少简中标题", set(), set())
        if page == "INTRO":
            section_title, section_used, section_unresolved = rendered(section_tag, texts) if section_tag in texts else (SECTION_NAMES.get(section, "文明百科"), set(), set())
            title = section_title + " · " + (title if title_tag else "简介")
            used.update(section_used)
            unresolved.update(section_unresolved)
        if group["chapter"] == "HISTORY" and name_tag:
            entity_title, entity_used, entity_unresolved = rendered(name_tag, texts)
            title, used, unresolved = entity_title + " · 历史背景", used | entity_used, unresolved | entity_unresolved
        # A generic chapter heading such as 'history' is not the article name.
        paragraphs = []
        for _, tag in sorted(group["paragraphs"]):
            paragraph, paragraph_used, paragraph_unresolved = rendered(tag, texts)
            if paragraph:
                paragraphs.append(paragraph)
                used.update(paragraph_used)
                unresolved.update(paragraph_unresolved)
        body = "\n\n".join(paragraphs)
        if not body:
            continue
        if len(body) > MAX_TEXT:
            raise ValueError("Civilopedia chapter exceeds text bound")
        entries.append({"id": key, "title": title, "section": SECTION_NAMES.get(section, "文明百科"),
                        "text": body, "tags": sorted(used), "sources": sorted({texts[tag].source for tag in used}),
                        "unresolved": sorted(unresolved), **({"annotations": ANNOTATIONS[key]} if key in ANNOTATIONS else {})})
        pages[page] = section
    # Names/descriptions are included only when a corresponding PEDIA page
    # supplies evidence that this is a public encyclopedia subject.
    for page, section in sorted(pages.items()):
        name = next((tag for tag in (f"LOC_{page}_NAME", f"LOC_{page}") if tag in texts), None)
        description = f"LOC_{page}_DESCRIPTION"
        if not name or description not in texts:
            continue
        title, name_tags, name_unresolved = rendered(name, texts)
        body, description_tags, description_unresolved = rendered(description, texts)
        used = name_tags | description_tags
        if not body:
            continue
        if len(body) > MAX_TEXT:
            raise ValueError("Civilopedia entity description exceeds text bound")
        entries.append({"id": "ENTITY_" + page, "title": title + " · 游戏说明",
                        "section": SECTION_NAMES.get(section, "文明百科"), "text": body,
                        "tags": sorted(used), "sources": sorted({texts[tag].source for tag in used}),
                        "unresolved": sorted(name_unresolved | description_unresolved)})
    if not 1 <= len(entries) <= MAX_ENTRIES or len({item["id"] for item in entries}) != len(entries):
        raise ValueError("Invalid Civilopedia entry count or duplicate IDs")
    return sorted(entries, key=lambda item: (item["section"], item["id"]))


def atomic_write(directory: Path, name: str, payload: bytes) -> Path:
    target = directory / name
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise ValueError("Output path is not a regular file")
    with tempfile.NamedTemporaryFile(mode="wb", prefix="civilopedia-", suffix=".pending", dir=directory, delete=False) as stream:
        stream.write(payload)
        temporary = Path(stream.name)
    temporary.replace(target)
    return target


def prepare(game_root: Path, directory: Path) -> dict:
    game_root, directory = game_root.resolve(), directory.resolve()
    if directory.is_relative_to(game_root):
        raise ValueError("Do not write index into game installation")
    texts, files, absent = load_texts(game_root)
    modinfo_hash = next(item["sha256"] for item in files if item["path"] == "DLC/Expansion2/Expansion2.modinfo")
    excluded_pages, exclusion_evidence = load_page_exclusions(game_root, modinfo_hash)
    files.append(exclusion_evidence)
    entries = build_entries(texts, excluded_pages)
    stamp = datetime.now(timezone.utc).isoformat()
    index = {"schema_version": 1, "source_id": "civilopedia", "language": "zh-Hans-CN", "ruleset": RULESET,
             "generated_at": stamp, "files": files, "entries": entries, "notes": NOTES,
             "optional_sources_absent": absent, "excluded_pages": excluded_pages, "scope": "static_civilopedia_text"}
    encoded = json.dumps(index, ensure_ascii=False, indent=2).encode("utf-8")
    if len(encoded) > MAX_INDEX_BYTES:
        raise ValueError("Civilopedia index exceeds size bound")
    manifest = {"schema_version": 1, "source_id": "civilopedia", "language": "zh-Hans-CN", "ruleset": RULESET,
                "generated_at": stamp, "index_file": INDEX_FILE, "index_sha256": hashlib.sha256(encoded).hexdigest(),
                "entry_count": len(entries), "excluded_page_count": len(excluded_pages), "files": files}
    markdown = ["# 官方简中文明百科 · 风云变幻规则集", "", "本文从本机已安装游戏的官方静态中文文本整理，原文版权归相应权利人。", ""]
    markdown.extend("- " + note for note in NOTES)
    markdown.extend(["", "## 条目目录", ""])
    for item in entries:
        markdown.append(f"- [{item['title']}](#{item['id'].lower()})（{item['section']}）")
    for item in entries:
        markdown.extend(["", f"<a id=\"{item['id'].lower()}\"></a>", f"## {item['title']}", "",
                         f"分类：{item['section']}；条目 ID：`{item['id']}`", "", item["text"], "",
                         "来源：" + "、".join(f"`{value}`" for value in item["sources"]),
                         "原文标签：" + "、".join(f"`{value}`" for value in item["tags"])])
        if item["unresolved"]:
            markdown.extend(["", "未展开的原文占位符：" + "、".join(f"`{value}`" for value in item["unresolved"])])
        if item.get("annotations"):
            markdown.extend(["", *["> " + note for note in item["annotations"]]])
    directory.mkdir(parents=True, exist_ok=True)
    atomic_write(directory, INDEX_FILE, encoded)
    atomic_write(directory, MARKDOWN_FILE, "\n".join(markdown).encode("utf-8"))
    atomic_write(directory, MANIFEST_FILE, json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
    return {"entries": len(entries), "index_sha256": manifest["index_sha256"], "index": str(directory / INDEX_FILE),
            "manifest": str(directory / MANIFEST_FILE), "markdown": str(directory / MARKDOWN_FILE),
            "source_files": len(files), "excluded_pages": len(excluded_pages),
            "unresolved_entries": sum(bool(item["unresolved"]) for item in entries)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path, required=True, help="Installed Civ VI directory; read-only")
    parser.add_argument("--directory", type=Path, default=ROOT / "manuals")
    args = parser.parse_args()
    print(json.dumps(prepare(args.game_root, args.directory), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
