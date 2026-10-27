"""Hermetic tests for prepared Chinese static-reference search, no game access."""

from hashlib import sha256
import json

import pytest

from civ6_fair_mcp import civilopedia
from civ6_fair_mcp.civilopedia import CivilopediaLibrary, INDEX_FILE, MANIFEST_FILE


SOURCE_PATH = "Base/Assets/Text/Vanilla_zh_Hans_CN.xml"


def make_entry(key, title, text):
    return {"id": key, "title": title, "section": "游戏概念", "text": text,
            "tags": ["LOC_PEDIA_TEST_TITLE", "LOC_PEDIA_TEST_PARA_1"], "sources": [SOURCE_PATH]}


def write_index(directory, data):
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    (directory / INDEX_FILE).write_bytes(payload)
    manifest = {"schema_version": 1, "source_id": "civilopedia", "index_file": INDEX_FILE,
                "index_sha256": sha256(payload).hexdigest(), "entry_count": len(data["entries"]),
                "files": data["files"], "language": "zh-Hans-CN", "ruleset": "RULESET_EXPANSION_2"}
    (directory / MANIFEST_FILE).write_text(json.dumps(manifest), encoding="utf-8")


@pytest.fixture
def library(tmp_path):
    data = {"schema_version": 1, "source_id": "civilopedia", "language": "zh-Hans-CN",
            "ruleset": "RULESET_EXPANSION_2", "files": [{"path": SOURCE_PATH, "sha256": "a" * 64}],
            "entries": [make_entry("LOC_PEDIA_GOVERNOR", "总督", "总督可以任命和晋升；忠诚度属于城市概念。"),
                        make_entry("LOC_PEDIA_LOYALTY", "忠诚度", "城市忠诚度的静态说明。"),
                        make_entry("LOC_PEDIA_POWER", "电力", "电力供应与发电。电力规则。"),
                        make_entry("LOC_PEDIA_CONGRESS", "世界议会", "世界议会可以投票。"),
                        make_entry("LOC_PEDIA_OTHER", "其他机制", "世界议会投票与外交支持。电力" * 20)],
            "notes": ["测试来源是虚构文本，不包含真实游戏内容。"], "generated_at": "2026-10-27T13:00:00+00:00"}
    write_index(tmp_path, data)
    return CivilopediaLibrary(tmp_path), data


def test_catalog_is_chinese_static_reference_with_provenance(library):
    reader, _ = library
    result = reader.query()
    assert result["ok"] and result["mode"] == "catalog"
    assert result["scope"] == "static_reference" and result["results"] == []
    source = result["sources"][0]
    assert source["id"] == "civilopedia" and source["language"] == "zh-Hans-CN"
    assert source["status"] == "ready" and source["entry_count"] == 5
    assert source["official_localization"] is True and source["complete_dynamic_civilopedia"] is False
    assert "observation_token" not in result


def test_missing_index_catalog_and_search_are_explicit_without_english_fallback(tmp_path):
    reader = CivilopediaLibrary(tmp_path)
    assert reader.query()["sources"][0]["status"] == "not_installed"
    result = reader.query("总督")
    assert result["error"] == "civilopedia_unavailable" and result["results"] == []
    assert "不会自动回退" in result["hint"]


def test_default_directory_is_manuals_under_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert CivilopediaLibrary().directory == tmp_path / "manuals"


@pytest.mark.parametrize("query,title", [("电力", "电力"), ("供电", "电力"), ("忠诚", "忠诚度"),
    ("总督", "总督"), ("WORLD CONGRESS", "世界议会"), ("  电力  ", "电力")])
def test_exact_or_alias_title_ranks_before_frequent_body_mentions(library, query, title):
    reader, _ = library
    result = reader.query(query)
    assert result["ok"] and result["results"][0]["title"] == title
    assert result["results"][0]["language"] == "zh-Hans-CN"
    assert all(item["sources"] == [SOURCE_PATH] for item in result["results"])


def test_multiple_terms_require_all_and_results_are_bounded(library):
    reader, _ = library
    assert reader.query("世界议会 投票")["total_matches"] == 2
    assert reader.query("世界议会 忠诚度")["total_matches"] == 0
    result = reader.query("世界议会", limit=1)
    assert len(result["results"]) == 1 and result["has_more"] is True
    assert len(result["results"][0]["excerpt"]) <= 400


def test_exact_entity_subject_and_gameplay_rank_before_similar_entities(library):
    reader, data = library
    data["entries"] = [
        make_entry("LOC_A_NUCLEAR_HISTORY", "核潜艇 · 历史背景", "核潜艇和潜艇的历史。" * 30),
        make_entry("LOC_B_HISTORY", "潜艇 · 历史背景", "潜艇的历史。" * 30),
        make_entry("LOC_C_NUCLEAR_GAMEPLAY", "核潜艇 · 游戏说明", "潜艇和核潜艇的说明。" * 30),
        make_entry("LOC_D_GAMEPLAY", "潜艇 · 游戏说明", "单位的说明。"),
    ]
    write_index(reader.directory, data)
    result = reader.query("潜艇", limit=4)
    assert [item["title"] for item in result["results"]] == [
        "潜艇 · 游戏说明", "潜艇 · 历史背景", "核潜艇 · 游戏说明", "核潜艇 · 历史背景",
    ]


def test_explicit_history_query_prefers_history_for_exact_entity(library):
    reader, data = library
    data["entries"] = [
        make_entry("LOC_A_GAMEPLAY", "潜艇 · 游戏说明", "潜艇的说明及历史。" * 30),
        make_entry("LOC_B_NUCLEAR_HISTORY", "核潜艇 · 历史背景", "潜艇的历史。" * 30),
        make_entry("LOC_C_HISTORY", "潜艇 · 历史背景", "单位的背景说明。"),
    ]
    write_index(reader.directory, data)
    result = reader.query("潜艇 历史", limit=3)
    assert result["total_matches"] == 3
    assert result["results"][0]["title"] == "潜艇 · 历史背景"


def test_entry_retains_raw_text_and_paginates_without_repeating(library):
    reader, data = library
    text = "中文🙂\n" * 2100
    data["entries"][0]["text"] = text
    write_index(reader.directory, data)
    first = reader.query(entry_id="LOC_PEDIA_GOVERNOR")["results"][0]
    assert len(first["text"]) == 6000 and first["next_offset"] == 6000
    assert first["has_more"] and first["truncated"] and first["total_characters"] == len(text)
    second = reader.query(entry_id="LOC_PEDIA_GOVERNOR", offset=first["next_offset"])["results"][0]
    assert first["text"] + second["text"] == text
    assert second["next_offset"] is None and not second["has_more"]
    assert reader.query(entry_id="LOC_PEDIA_GOVERNOR", offset=len(text))["error"] == "offset_out_of_range"
    assert reader.query(entry_id="LOC_UNKNOWN")["error"] == "entry_not_found"


def test_no_hit_does_not_claim_mechanic_absent(library):
    result = library[0].query("无法命中的词")
    assert result["ok"] and result["total_matches"] == 0
    assert "不代表" in result["hint"]


@pytest.mark.parametrize("kwargs", [
    {"query": None}, {"query": True}, {"query": "x" * 201}, {"query": "\ud800"},
    {"query": "\x00"}, {"query": "?!"}, {"entry_id": []}, {"entry_id": "../Saves"},
    {"entry_id": "C:\\secret"}, {"entry_id": "lower_case"}, {"entry_id": "X" * 257},
    {"entry_id": "LOC_PEDIA_GOVERNOR", "query": "总督"}, {"offset": 1}, {"offset": True},
    {"offset": -1}, {"entry_id": "LOC_PEDIA_GOVERNOR", "offset": 60001},
    {"limit": 0}, {"limit": 9}, {"limit": True}, {"limit": "2"}, {"limit": 1.5},
])
def test_invalid_input_never_reads_index(library, monkeypatch, kwargs):
    reader, _ = library
    monkeypatch.setattr(reader, "_read", lambda *_: pytest.fail("invalid input read a file"))
    assert reader.query(**kwargs) == {"ok": False, "error": "invalid_input"}


def test_index_hash_mismatch_is_not_returned(library):
    reader, _ = library
    with (reader.directory / INDEX_FILE).open("ab") as stream:
        stream.write(b" ")
    result = reader.query("总督")
    assert result["sources"][0]["status"] == "index_mismatch"
    assert result["error"] == "civilopedia_unavailable" and not result["results"]


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(schema_version=True), lambda d: d.update(source_id="other"),
    lambda d: d.update(language="en"), lambda d: d.update(ruleset="RULESET_STANDARD"),
    lambda d: d.update(entries=[]), lambda d: d["entries"].append(d["entries"][0]),
    lambda d: d["entries"][0].update(text=""), lambda d: d["entries"][0].update(title=""),
    lambda d: d["entries"][0].update(text="x" * 60001), lambda d: d["entries"][0].update(sources=["../secret"]),
    lambda d: d["entries"][0].update(sources=[SOURCE_PATH, SOURCE_PATH]),
    lambda d: d["entries"][0].update(tags=["OTHER"]), lambda d: d["entries"][0].update(unresolved="invalid"),
    lambda d: d["entries"][0].update(unresolved=["x" * 1025]),
    lambda d: d["entries"][0].update(annotations="invalid"),
    lambda d: d["entries"][0].update(annotations=[""]),
    lambda d: d["entries"][0].update(annotations=["x" * 2001]),
    lambda d: d["entries"][0].update(annotations=["note"] * 9),
    lambda d: d["entries"][0].update(annotations=["\x00"]),
    lambda d: d["files"][0].update(path="C:/secrets"), lambda d: d["files"][0].update(path="Base/Assets/../secret"),
    lambda d: d["files"][0].update(path="Saves/current.Civ6Save"),
    lambda d: d["files"][0].update(sha256="broken"), lambda d: d["files"].append(d["files"][0]),
    lambda d: d.update(notes="invalid"), lambda d: d.update(generated_at=123),
])
def test_rehashed_but_invalid_index_is_rejected(library, mutate):
    reader, data = library
    mutate(data)
    write_index(reader.directory, data)
    result = reader.query("总督")
    assert result["error"] == "civilopedia_unavailable" and result["sources"][0]["status"] == "invalid_index"


@pytest.mark.parametrize("change", [
    {"index_file": "../secret"}, {"index_sha256": "wrong"}, {"schema_version": True},
    {"source_id": "other"}, {"entry_count": True}, {"entry_count": 999}, {"language": "en"},
    {"files": []}, {"ruleset": "RULESET_STANDARD"},
])
def test_manifest_inconsistency_is_rejected(library, change):
    reader, _ = library
    path = reader.directory / MANIFEST_FILE
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(change)
    path.write_text(json.dumps(data), encoding="utf-8")
    assert reader.query("总督")["sources"][0]["status"] == "invalid_manifest"


def test_bounded_files_and_duplicate_json_keys_fail_closed(library, monkeypatch):
    reader, _ = library
    monkeypatch.setattr(civilopedia, "MAX_INDEX_BYTES", 4)
    assert reader.query("总督")["sources"][0]["status"] == "unreadable_or_invalid"
    monkeypatch.undo()
    path = reader.directory / MANIFEST_FILE
    path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    assert reader.query("总督")["sources"][0]["status"] == "unreadable_or_invalid"


def test_only_fixed_cache_files_are_opened_never_provenance_paths(library, monkeypatch):
    reader, _ = library
    opened = []
    original = reader._read
    def recorded(name, maximum):
        opened.append(name)
        return original(name, maximum)
    monkeypatch.setattr(reader, "_read", recorded)
    assert reader.query("总督")["ok"]
    assert opened == [MANIFEST_FILE, INDEX_FILE]


def test_unresolved_placeholders_and_provenance_are_reported_not_executed(library):
    reader, data = library
    data["entries"][0]["text"] = "文本里的 {1_Num} 保留为占位符。"
    data["entries"][0]["unresolved"] = ["{1_Num}"]
    write_index(reader.directory, data)
    result = reader.query(entry_id="LOC_PEDIA_GOVERNOR")["results"][0]
    assert result["text"] == data["entries"][0]["text"]
    assert result["unresolved"] == ["{1_Num}"] and result["unresolved_count"] == 1


def test_project_annotations_returned_in_search_and_entry_separate_from_original(library):
    reader, data = library
    original = data["entries"][0]["text"]
    note = "项目注记：这是一条已核实的版本差异提示，不是官方原文。"
    data["entries"][0]["annotations"] = [note]
    write_index(reader.directory, data)
    search = reader.query("总督")["results"][0]
    entry = reader.query(entry_id=search["entry_id"])["results"][0]
    assert search["annotations"] == entry["annotations"] == [note]
    assert entry["text"] == original and note not in search["excerpt"]
