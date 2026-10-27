from hashlib import sha256
import json
from pathlib import Path

import pytest

from civ6_fair_mcp import manual
from civ6_fair_mcp.manual import ManualLibrary

ORIGINAL_CATALOG = manual._catalog


@pytest.fixture
def library(tmp_path, monkeypatch):
    sources = []
    for source_id in manual.SOURCE_IDS:
        pdf = b"%PDF-1.7\nTest fixture " + source_id.encode()
        entry = {"id": source_id, "title": source_id, "language": "test", "url": "https://example.test/" + source_id,
            "pdf_file": source_id + ".pdf", "index_file": source_id + ".json",
            "sha256": sha256(pdf).hexdigest(), "edition_note": "Fixture, not current game rules."}
        sources.append(entry)
        (tmp_path / entry["pdf_file"]).write_bytes(pdf)
        (tmp_path / entry["index_file"]).write_text(json.dumps({"schema_version": 1,
            "source_id": source_id, "url": entry["url"], "pdf_sha256": entry["sha256"],
            "pages": [{"page": 1, "text": "Fixture overview."},
                      {"page": 2, "text": "世\n界 議會 投票\n世界議會資料。" if source_id != "rise_and_fall"
                       else "Loyalty, governors, and the World\nCongress. Infor-\nmation."}]}), encoding="utf-8")
    monkeypatch.setattr(manual, "_catalog", lambda: sources)
    return ManualLibrary(tmp_path), sources


def test_catalog_reports_each_source_and_missing_library_without_network(library, tmp_path):
    reader, sources = library
    result = reader.query()
    assert result["ok"] and result["mode"] == "catalog" and result["scope"] == "static_reference"
    assert len(result["sources"]) == 3 and all(item["status"] == "ready" for item in result["sources"])
    assert all(item["page_count"] == 2 for item in result["sources"])
    missing = ManualLibrary(tmp_path / "missing").query()
    assert missing["ok"] and all(item["status"] == "not_installed" for item in missing["sources"])
    assert "observation_token" not in result


def test_query_filters_source_and_expands_explicit_chinese_glossary(library):
    reader, _ = library
    result = reader.query("世界议会", source="gathering_storm")
    assert result["ok"] and result["total_matches"] == 1
    entry = result["results"][0]
    assert entry["pdf_page"] == 2 and entry["source_id"] == "gathering_storm"
    assert "世界議會" in entry["matched_terms"] and entry["excerpt_normalized"] is True
    assert entry["url"] == "https://example.test/gathering_storm"
    english = reader.query("忠诚度", source="rise_and_fall")
    assert english["results"][0]["matched_terms"] == ["loyalty"]
    assert reader.query("WORLD CONGRESS", source="rise_and_fall")["total_matches"] == 1
    assert reader.query("information", source="rise_and_fall")["total_matches"] == 1


def test_multiple_keywords_require_each_concept_and_rank_literal_before_alias(library):
    reader, _ = library
    result = reader.query("世界议会 投票")
    assert result["total_matches"] == 2
    assert all(item["source_id"] != "rise_and_fall" for item in result["results"])
    literal = reader.query("world congress", limit=1)
    assert literal["results"][0]["source_id"] == "rise_and_fall" and literal["has_more"]
    assert reader.query("世界议会 火山")["total_matches"] == 0


def test_page_is_raw_text_with_physical_page_and_not_current_state(library):
    reader, _ = library
    result = reader.query(source="base", page=2)
    assert result["mode"] == "page" and result["results"][0]["text"].startswith("世\n界")
    assert result["results"][0]["truncated"] is False
    assert reader.query(source="base", page=3)["error"] == "page_out_of_range"


@pytest.mark.parametrize("kwargs", [
    {"query": None}, {"query": True}, {"query": "x" * 201}, {"query": "\ud800"}, {"query": "?!"},
    {"source": "../../secret"}, {"source": True}, {"source": []},
    {"limit": 0}, {"limit": 9}, {"limit": True}, {"limit": 1.5},
    {"page": True, "source": "base"}, {"page": 0, "source": "base"}, {"page": 1001, "source": "base"},
    {"page": 1}, {"page": 1, "source": "base", "query": "climate"},
])
def test_invalid_inputs_do_not_even_load_catalog(library, monkeypatch, kwargs):
    reader, _ = library
    monkeypatch.setattr(manual, "_catalog", lambda: pytest.fail("invalid input must not read catalog"))
    assert reader.query(**kwargs) == {"ok": False, "error": "invalid_input"}


def _update_index(reader, source, change):
    path = reader.directory / source["index_file"]
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.parametrize("change", [
    lambda data: data.update(source_id="other"),
    lambda data: data.update(url="https://different.test/"),
    lambda data: data.update(pdf_sha256="0" * 64),
    lambda data: data.update(schema_version=True),
    lambda data: data.update(pages=[]),
    lambda data: data["pages"][1].update(page=1),
    lambda data: data["pages"][0].update(page=True),
    lambda data: data["pages"][0].update(text="\ud800"),
    lambda data: data["pages"][0].update(text="x" * 60001),
])
def test_invalid_index_is_isolated_from_other_manuals(library, change):
    reader, sources = library
    _update_index(reader, sources[0], change)
    result = reader.query("世界议会")
    assert result["ok"] and result["sources"][0]["status"] == "invalid_index"
    assert result["total_matches"] == 2
    assert reader.query("世界议会", source="base")["error"] == "manual_unavailable"


def test_modified_pdf_cannot_be_used_with_old_index_or_changed_local_digest(library):
    reader, sources = library
    (reader.directory / sources[0]["pdf_file"]).write_bytes(b"%PDF-1.7\nAltered")
    assert reader.query()["sources"][0]["status"] == "pdf_mismatch"
    digest = sha256(b"%PDF-1.7\nAltered").hexdigest()
    _update_index(reader, sources[0], lambda data: data.update(pdf_sha256=digest))
    assert reader.query()["sources"][0]["status"] == "invalid_index"


def test_corrupt_and_oversized_files_are_bounded(library, monkeypatch):
    reader, sources = library
    (reader.directory / sources[0]["index_file"]).write_text('{"schema_version": 1,"schema_version": 1}')
    assert reader.query()["sources"][0]["status"] == "unreadable_or_invalid"
    monkeypatch.setattr(manual, "MAX_PDF_BYTES", 4)
    assert reader.query()["sources"][1]["status"] == "unreadable_or_invalid"
    monkeypatch.setattr(manual, "MAX_INDEX_BYTES", 4)
    assert all(item["status"] == "unreadable_or_invalid" for item in reader.query()["sources"])


def test_page_and_excerpt_outputs_are_bounded_and_flagged(library):
    reader, sources = library
    _update_index(reader, sources[0], lambda data: data["pages"][1].update(text="Prefix " * 1000 + "World Congress " * 200))
    page = reader.query(source="base", page=2)["results"][0]
    assert page["truncated"] and len(page["text"]) == 6000 and page["total_characters"] > 6000
    result = reader.query("world congress", source="base")["results"][0]
    assert len(result["excerpt"]) <= 400 and result["truncated"]
    assert "world congress" in result["excerpt"]


def test_external_symlink_is_rejected_without_reading_target(library, tmp_path):
    reader, _ = library
    outside = tmp_path.parent / (tmp_path.name + "_outside.pdf")
    outside.write_bytes(b"%PDF-1.7\nUnrelated")
    link = reader.directory / "escape.pdf"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValueError, match="leaves manual directory"):
        reader._read("escape.pdf", 100)


def test_missing_packaged_catalog_is_clear_error(library, monkeypatch):
    reader, _ = library
    def unavailable():
        raise FileNotFoundError("not packaged")
    monkeypatch.setattr(manual, "_catalog", unavailable)
    result = reader.query()
    assert result["error"] == "catalog_unavailable" and not result["ok"]


def test_default_directory_tracks_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert ManualLibrary().directory == Path.cwd() / "manuals"


def test_english_keywords_do_not_match_inside_unrelated_words(library):
    reader, sources = library
    _update_index(reader, sources[0], lambda data: data["pages"][1].update(text="damage to governors"))
    assert reader.query("dam", source="base")["total_matches"] == 0


def test_repeated_body_keywords_rank_before_brief_table_of_contents(library):
    reader, sources = library
    _update_index(reader, sources[0], lambda data: data.update(pages=[
        {"page": 1, "text": "Contents: World Congress."},
        {"page": 2, "text": "World Congress. Rules of the World Congress. Other World Congress details."}]))
    assert reader.query("world congress", source="base", limit=1)["results"][0]["pdf_page"] == 2


@pytest.mark.parametrize("mutation", [
    lambda entries: entries[0].update(pdf_file="../secret.pdf"),
    lambda entries: entries[0].update(index_file="F:\\private.json"),
    lambda entries: entries[0].update(sha256="invalid"),
    lambda entries: entries[0].update(id="gathering_storm"),
    lambda entries: entries[0].update(url="file:///private.pdf"),
])
def test_catalog_rejects_invalid_paths_and_unpinned_sources(library, tmp_path, monkeypatch, mutation):
    _, sources = library
    mutation(sources)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "manual_sources.json").write_text(json.dumps({"schema_version": 1, "sources": sources}), encoding="utf-8")
    monkeypatch.setattr(manual.resources, "files", lambda _: tmp_path)
    with pytest.raises(ValueError):
        ORIGINAL_CATALOG()


def test_catalog_accepts_exactly_the_three_pinned_sources(library, tmp_path, monkeypatch):
    _, sources = library
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "manual_sources.json").write_text(json.dumps({"schema_version": 1, "sources": sources}), encoding="utf-8")
    monkeypatch.setattr(manual.resources, "files", lambda _: tmp_path)
    assert ORIGINAL_CATALOG() == sources
