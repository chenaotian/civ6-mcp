"""Offline preparation uses synthetic static assets; never starts the game."""

from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_civilopedia.py"
SPEC = importlib.util.spec_from_file_location("civilopedia_preparation", SCRIPT)
preparation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = preparation
SPEC.loader.exec_module(preparation)

KEY = "LOC_PEDIA_CONCEPTS_PAGE_POWER_CHAPTER_CONTENT"
SOURCE = "Base/Assets/Text/Vanilla_zh_Hans_CN.xml"


def xml(*operations):
    return ET.fromstring("<GameData><LocalizedText>" + "".join(operations) + "</LocalizedText></GameData>")


def row(tag, text, operation="Replace", language="zh_Hans_CN"):
    element = ET.Element(operation, Tag=tag, Language=language)
    ET.SubElement(element, "Text").text = text
    return ET.tostring(element, encoding="unicode")


def records(values):
    return {tag: preparation.TextRecord(text, SOURCE) for tag, text in values.items()}


@pytest.fixture
def installation(tmp_path):
    root = tmp_path / "install"
    for relative, *_ in preparation.SOURCE_PLAN:
        if relative.endswith("Expansion2_Translations_Major_Text.xml"):
            continue
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<GameData><LocalizedText/></GameData>", encoding="utf-8")
    for expansion in ("Expansion1", "Expansion2"):
        modinfo = ET.Element("Mod")
        actions = ET.SubElement(modinfo, "InGameActions")
        for component in sorted({item[2] for item in preparation.SOURCE_PLAN if item[1] == expansion}):
            action = ET.SubElement(actions, "UpdateText", id=component)
            for relative, member, identifier, _ in preparation.SOURCE_PLAN:
                if member == expansion and identifier == component:
                    ET.SubElement(action, "File").text = relative.split(f"DLC/{expansion}/", 1)[1]
        if expansion == "Expansion2":
            action = ET.SubElement(actions, "UpdateDatabase", id="Expansion2Core")
            ET.SubElement(action, "File", Priority="1").text = "Data/Expansion2_RemoveData.xml"
        (root / f"DLC/{expansion}/{expansion}.modinfo").write_bytes(ET.tostring(modinfo))
    removal = root / preparation.PAGE_REMOVALS
    removal.parent.mkdir(parents=True, exist_ok=True)
    removal.write_text('<GameInfo><CivilopediaPages><Delete PageId="COMBAT_11"/></CivilopediaPages></GameInfo>', encoding="utf-8")
    (root / SOURCE).write_bytes(ET.tostring(xml(row(KEY + "_TITLE", "电力"), row(KEY + "_PARA_1", "本体内容"))))
    gs = root / "DLC/Expansion2/Text/Expansion2_Translations_Text.xml"
    gs.write_bytes(ET.tostring(xml(row(KEY + "_PARA_1", "风云变幻电力内容"))))
    return root


def test_only_simplified_chinese_is_loaded_and_replace_overrides():
    table = {}
    preparation.apply_localization(table, xml(row("LOC_TEST", "本体", "Row"), row("LOC_TEST", "English", language="en_US")), "base.xml")
    preparation.apply_localization(table, xml(row("LOC_TEST", "修订")), "gs.xml")
    assert table == {"LOC_TEST": preparation.TextRecord("修订", "gs.xml")}


def test_duplicate_row_is_not_silently_replaced():
    with pytest.raises(ValueError, match="Duplicate"):
        preparation.apply_localization({}, xml(row("LOC_TEST", "一", "Row"), row("LOC_TEST", "二", "Row")), SOURCE)


def test_opaque_source_key_is_preserved_without_repair_or_indexing():
    table = {}
    preparation.apply_localization(table, xml(row("LOC_RANDOM_EVENT_BAD]", "未索引通知"), row(KEY + "_PARA_1", "公开文本")), SOURCE)
    assert "LOC_RANDOM_EVENT_BAD]" in table and "LOC_RANDOM_EVENT_BAD" not in table
    assert len(preparation.build_entries(table)) == 1


def test_update_and_delete_follow_explicit_locale_and_tag():
    table = records({"LOC_TEST": "初始", "LOC_DELETE": "删除"})
    preparation.apply_localization(table, xml(
        '<Update><Where Tag="LOC_TEST" Language="en_US"/><Set Text="English"/></Update>',
        '<Update><Where Tag="LOC_TEST"/><Set><Text>修订</Text></Set></Update>',
        '<Delete Tag="LOC_TEST" Language="en_US"/>', '<Delete Tag="LOC_DELETE"/>'), "patch.xml")
    assert table == {"LOC_TEST": preparation.TextRecord("修订", "patch.xml")}
    preparation.apply_localization(table, xml('<Delete Tag="LOC_TEST" Language="zh_Hans_CN"/>'), "patch.xml")
    assert not table


@pytest.mark.parametrize("operation", [
    "<Unsupported/>", "<Delete/>", '<Delete Text="值"/>',
    '<Update><Where Text="值"/><Set Text="值"/></Update>',
    '<Update><Where Tag="LOC_TEST"/><Set Tag="LOC_OTHER"/></Update>',
    '<Update><Where Tag="LOC_TEST"/><Set Text="值"/><Set Text="另一值"/></Update>',
    '<Replace Tag="LOC_TEST" Language="zh_Hans_CN" Unexpected="1"><Text>值</Text></Replace>',
    '<Replace Tag="LOC_TEST" Language="zh_Hans_CN"><Text>一</Text><Text>二</Text></Replace>',
])
def test_unrecognized_xml_operations_fail_instead_of_guessing(operation):
    with pytest.raises(ValueError):
        preparation.apply_localization({}, xml(operation), SOURCE)


@pytest.mark.parametrize("content", ["<Unexpected/>", "<GameData><UnlistedTable/></GameData>"])
def test_unknown_document_schema_fails(content):
    with pytest.raises(ValueError):
        preparation.apply_localization({}, ET.fromstring(content), SOURCE)


def test_chapters_group_paragraphs_numerically_and_track_all_sources():
    table = records({KEY + "_TITLE": "电力", KEY + "_PARA_10": "第十段", KEY + "_PARA_2": "第二段"})
    table[KEY + "_PARA_1"] = preparation.TextRecord("第一段", "DLC/Expansion2/Text/Expansion2_Translations_Text.xml")
    entry, = preparation.build_entries(table)
    assert entry["id"] == KEY and entry["title"] == "电力"
    assert entry["text"] == "第一段\n\n第二段\n\n第十段"
    assert set(entry["tags"]) == set(table) and len(entry["sources"]) == 2


def test_only_pedia_backed_entities_get_name_and_description():
    key = "LOC_PEDIA_UNITS_PAGE_UNIT_TEST_CHAPTER_HISTORY"
    table = records({key + "_PARA_1": "历史", "LOC_UNIT_TEST_NAME": "测试单位", "LOC_UNIT_TEST_DESCRIPTION": "公开能力",
                     "LOC_UNIT_OTHER_NAME": "未证实页面", "LOC_UNIT_OTHER_DESCRIPTION": "不应收录",
                     "LOC_NOTIFICATION_TEST": "不应收录", "LOC_GOSSIP_TEST": "不应收录"})
    entries = preparation.build_entries(table)
    assert {entry["id"] for entry in entries} == {key, "ENTITY_UNIT_TEST"}
    assert next(entry for entry in entries if entry["id"] == key)["title"] == "测试单位 · 历史背景"
    assert all("不应收录" not in entry["text"] for entry in entries)


def test_intro_and_names_without_name_suffix_use_official_chinese():
    table = records({"LOC_PEDIA_RELIGIONS_TITLE": "宗教", "LOC_PEDIA_RELIGIONS_PAGE_INTRO_CHAPTER_CONTENT_PARA_1": "介绍内容",
                     "LOC_PEDIA_RELIGIONS_PAGE_RELIGION_TEST_CHAPTER_HISTORY_PARA_1": "历史内容", "LOC_RELIGION_TEST": "测试宗教"})
    entries = preparation.build_entries(table)
    assert {entry["title"] for entry in entries} == {"宗教 · 简介", "测试宗教 · 历史背景"}


def test_references_are_expanded_but_dynamic_values_remain_explicit():
    table = records({KEY: "[COLOR_RED]{LOC_NAME}[ENDCOLOR][NEWLINE][ICON_Science]{1_Num}", "LOC_NAME": "电力"})
    text, tags, unresolved = preparation.rendered(KEY, table)
    assert text == "电力\n【科技】{1_Num}" and tags == {KEY, "LOC_NAME"}
    assert unresolved == {"{1_Num}"}


def test_missing_reference_cycle_and_nested_grammar_do_not_invent_translation():
    table = records({KEY: "{LOC_MISSING} {LOC_CYCLE} {1?{LOC_NAME}:其他}", "LOC_CYCLE": "{LOC_CYCLE}", "LOC_NAME": "官方中文"})
    text, tags, unresolved = preparation.rendered(KEY, table)
    assert "{LOC_MISSING}" in text and "{LOC_CYCLE}" in text
    assert "{1?官方中文:其他}" in text and "{1?官方中文:其他}" in unresolved
    assert "{LOC_MISSING}" in unresolved and "LOC_MISSING" not in tags


def test_missing_chinese_title_is_marked_without_english_fallback():
    entry, = preparation.build_entries(records({KEY + "_PARA_1": "仅有正文"}))
    assert entry["title"] == "游戏概念 · 原文缺少简中标题"


def test_explicit_espionage_history_shape_is_supported_without_broad_tag_dump():
    key = "LOC_PEDIA_ESPIONAGE_BREACH_DAM_CHAPTER_HISTORY"
    table = records({key + "_PARA_1": "公开历史", "LOC_UNITOPERATION_SPY_BREACH_DAM_DESCRIPTION": "破坏堤坝",
                     "LOC_ESPIONAGE_BREACH_DAM_REWARD": "不应混入", "LOC_PEDIA_ESPIONAGE_UNKNOWN_CHAPTER_HISTORY_PARA_1": "不应猜测新结构"})
    entry, = preparation.build_entries(table)
    assert entry["id"] == key and entry["title"] == "破坏堤坝 · 历史背景"
    assert entry["text"] == "公开历史" and entry["section"] == "间谍活动"


def test_verified_legacy_conflict_is_annotated_separately_from_official_text():
    key = "LOC_PEDIA_CONCEPTS_PAGE_SCIENCE_3_CHAPTER_CONTENT"
    entry, = preparation.build_entries(records({key + "_PARA_1": "原文中的研究协议"}))
    assert entry["text"] == "原文中的研究协议"
    assert len(entry["annotations"]) == 1 and entry["annotations"][0].startswith("项目注记：")


def test_selected_sources_apply_gs_last_and_fingerprint_exact_bytes(installation):
    table, evidence, absent = preparation.load_texts(installation)
    assert table[KEY + "_PARA_1"].text == "风云变幻电力内容"
    assert len(evidence) == 8 and absent == ["DLC/Expansion2/Text/Expansion2_Translations_Major_Text.xml"]
    assert all(item["sha256"] == sha256((installation / item["path"]).read_bytes()).hexdigest() for item in evidence)
    assert not any("Expansion1_CoreText" == component for _, _, component, _ in preparation.SOURCE_PLAN)


def test_source_no_longer_in_expected_modinfo_is_rejected(installation):
    path = installation / "DLC/Expansion2/Expansion2.modinfo"
    content = path.read_text(encoding="utf-8").replace("Text/Expansion2_Translations_Text.xml", "Text/Unexpected.xml")
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="expected GS text component"):
        preparation.load_texts(installation)


def test_gs_removed_pages_are_excluded_but_grievances_are_kept():
    old = "LOC_PEDIA_CONCEPTS_PAGE_COMBAT_11_CHAPTER_CONTENT"
    current = "LOC_PEDIA_CONCEPTS_PAGE_GRIEVANCES_CHAPTER_CONTENT"
    table = records({old + "_TITLE": "好战程度", old + "_PARA_1": "旧规则",
                     current + "_TITLE": "怨恨", current + "_PARA_1": "新规则",
                     "LOC_COMBAT_11_NAME": "旧规则", "LOC_COMBAT_11_DESCRIPTION": "也应排除"})
    excluded = preparation.page_exclusions(ET.fromstring('<GameInfo><CivilopediaPages><Delete PageId="COMBAT_11"/></CivilopediaPages></GameInfo>'))
    entries = preparation.build_entries(table, excluded)
    assert [entry["id"] for entry in entries] == [current]


def test_section_qualified_page_removal_does_not_exclude_other_sections():
    table = records({"LOC_PEDIA_CONCEPTS_PAGE_TEST_CHAPTER_CONTENT_PARA_1": "概念",
                     "LOC_PEDIA_UNITS_PAGE_TEST_CHAPTER_CONTENT_PARA_1": "单位"})
    excluded = preparation.page_exclusions(ET.fromstring('<GameInfo><CivilopediaPages><Delete PageId="TEST" SectionId="CONCEPTS"/></CivilopediaPages></GameInfo>'))
    entries = preparation.build_entries(table, excluded)
    assert len(entries) == 1 and entries[0]["section"] == "单位"


@pytest.mark.parametrize("operation", ['<Delete/>', '<Delete PageId="TEST" Filter="1"/>', '<Update PageId="TEST"/>', '<Delete><Where PageId="TEST"/></Delete>'])
def test_unknown_page_removal_conditions_fail_closed(operation):
    with pytest.raises(ValueError, match="removal condition"):
        preparation.page_exclusions(ET.fromstring("<GameInfo><CivilopediaPages>" + operation + "</CivilopediaPages></GameInfo>"))


def test_unlisted_assets_are_never_opened(installation, monkeypatch):
    allowed = set(preparation.MODINFO_FILES) | {entry[0] for entry in preparation.SOURCE_PLAN}
    original = preparation.read_xml
    opened = []
    def guarded(root, relative):
        assert relative in allowed
        opened.append(relative)
        return original(root, relative)
    monkeypatch.setattr(preparation, "read_xml", guarded)
    preparation.load_texts(installation)
    assert len(opened) == 8


def test_read_xml_rejects_dtd_entities_oversize_and_escape(tmp_path, monkeypatch):
    source = tmp_path / "source.xml"
    source.write_text('<!DOCTYPE a [<!ENTITY b "test">]><GameData/>', encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported"):
        preparation.read_xml(tmp_path, "source.xml")
    source.write_text("<GameData/>", encoding="utf-8")
    monkeypatch.setattr(preparation, "MAX_FILE_BYTES", 1)
    with pytest.raises(ValueError, match="Unsupported"):
        preparation.read_xml(tmp_path, "source.xml")
    child = tmp_path / "child"
    child.mkdir()
    with pytest.raises(ValueError, match="leaves installation"):
        preparation.read_xml(child, "../source.xml")


def test_prepare_writes_matching_manifest_and_readable_markdown(installation, tmp_path):
    output = tmp_path / "manuals"
    result = preparation.prepare(installation, output)
    payload = (output / preparation.INDEX_FILE).read_bytes()
    index = json.loads(payload)
    manifest = json.loads((output / preparation.MANIFEST_FILE).read_bytes())
    assert manifest["index_sha256"] == sha256(payload).hexdigest() == result["index_sha256"]
    assert manifest["files"] == index["files"] and manifest["entry_count"] == 1
    assert len(index["files"]) == 9 and manifest["excluded_page_count"] == 1
    assert index["excluded_pages"][0]["page_id"] == "COMBAT_11"
    assert index["language"] == "zh-Hans-CN" and index["ruleset"] == "RULESET_EXPANSION_2"
    markdown = (output / preparation.MARKDOWN_FILE).read_text(encoding="utf-8")
    assert "风云变幻电力内容" in markdown and KEY in markdown and "原文标签" in markdown
    assert not list(output.glob("*.pending"))


def test_prepare_refuses_output_in_game_directory_before_reading(installation, monkeypatch):
    monkeypatch.setattr(preparation, "load_texts", lambda root: pytest.fail("should reject before reading"))
    with pytest.raises(ValueError, match="game installation"):
        preparation.prepare(installation, installation / "manuals")


def test_preparation_enforces_entry_text_and_index_bounds(installation, tmp_path, monkeypatch):
    monkeypatch.setattr(preparation, "MAX_TEXT", 2)
    with pytest.raises(ValueError, match="text bound"):
        preparation.build_entries(records({KEY + "_PARA_1": "过长的正文"}))
    monkeypatch.setattr(preparation, "MAX_TEXT", 60000)
    monkeypatch.setattr(preparation, "MAX_INDEX_BYTES", 1)
    output = tmp_path / "manuals"
    with pytest.raises(ValueError, match="size bound"):
        preparation.prepare(installation, output)
    assert not output.exists()


def test_atomic_output_rejects_nonfile_without_touching_it(tmp_path):
    (tmp_path / preparation.INDEX_FILE).mkdir()
    with pytest.raises(ValueError, match="regular file"):
        preparation.atomic_write(tmp_path, preparation.INDEX_FILE, b"test")
    assert (tmp_path / preparation.INDEX_FILE).is_dir()
