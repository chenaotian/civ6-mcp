"""Language selection must be explicit; unavailable Chinese is not English."""

import pytest

from civ6_fair_mcp.reference_library import ReferenceLibrary


class StubLibrary:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def query(self, **kwargs):
        self.calls.append(kwargs)
        return dict(self.result)


@pytest.fixture
def library(tmp_path):
    lib = ReferenceLibrary(tmp_path)
    lib.civilopedia = StubLibrary({"ok": True, "mode": "search", "sources": [
        {"id": "civilopedia", "language": "zh-Hans-CN", "status": "ready"}],
        "results": [{"source_id": "civilopedia", "entry_id": "CONCEPTS:POWER", "text": "电力"}],
        "total_matches": 2})
    lib.pdf = StubLibrary({"ok": True, "mode": "search", "sources": [
        {"id": "base", "language": "zh-Hant", "status": "ready"}],
        "results": [{"source_id": "base", "pdf_page": 20}], "total_matches": 3})
    return lib


def test_default_search_only_consults_chinese(library):
    result = library.query(query="电力")
    assert result["preferred_source"] == "civilopedia"
    assert result["results"][0]["text"] == "电力"
    assert len(library.civilopedia.calls) == 1 and not library.pdf.calls


def test_missing_chinese_never_implicitly_uses_pdfs(library):
    library.civilopedia.result = {"ok": False, "mode": "search", "error": "manual_unavailable", "results": []}
    result = library.query(query="电力")
    assert result["error"] == "manual_unavailable" and not library.pdf.calls


def test_catalog_lists_original_pdf_references(library):
    library.civilopedia.result["mode"] = "catalog"
    result = library.query()
    assert [s["id"] for s in result["sources"]] == ["civilopedia", "base"]
    assert result["preferred_source"] == "civilopedia"


def test_exact_entry_and_offset_are_routed_only_to_chinese(library):
    library.query(entry_id="CONCEPTS:POWER", offset=6000)
    assert library.civilopedia.calls == [{"query": "", "entry_id": "CONCEPTS:POWER", "limit": 5, "offset": 6000}]
    assert not library.pdf.calls


def test_explicit_pdf_still_uses_physical_page(library):
    library.query(source="gathering_storm", page=6)
    assert library.pdf.calls == [{"query": "", "source": "gathering_storm", "page": 6, "limit": 5}]
    assert not library.civilopedia.calls


def test_explicit_all_prioritizes_chinese_and_reports_remaining_hits(library):
    result = library.query(query="电力", source="all", limit=1)
    assert result["ordering"] == "civilopedia_first"
    assert len(result["results"]) == 1 and result["results"][0]["source_id"] == "civilopedia"
    assert result["total_matches"] == 5 and result["has_more"] is True
    assert len(library.pdf.calls) == len(library.civilopedia.calls) == 1


@pytest.mark.parametrize("kwargs", [
    {"source": "../../Saves"}, {"limit": True}, {"limit": 9}, {"offset": True}, {"offset": -1},
    {"query": "x" * 201}, {"source": "civilopedia", "page": 1},
    {"source": "all", "entry_id": "CONCEPTS:POWER"}, {"source": "base", "offset": 6000},
    {"source": "base", "entry_id": "CONCEPTS:POWER"}, {"source": "all", "page": 1},
])
def test_invalid_or_ambiguous_inputs_do_not_read_any_source(library, kwargs):
    assert library.query(**kwargs)["error"] == "invalid_input"
    assert not library.pdf.calls and not library.civilopedia.calls
