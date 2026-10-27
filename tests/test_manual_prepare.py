"""Preparation validates pinned official documents without ever calling the game."""

from hashlib import sha256
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.request import Request

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_manuals.py"
SPEC = importlib.util.spec_from_file_location("manual_preparation", SCRIPT)
preparation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preparation)


@pytest.fixture
def prepared_environment(tmp_path, monkeypatch):
    payload = b"%PDF-1.7\nOfficial manual fixture."
    source = {"id": "base", "url": "https://downloads.2kgames.com/test.pdf",
              "pdf_file": "base.pdf", "index_file": "base.json", "sha256": sha256(payload).hexdigest()}
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"sources": [source]}), encoding="utf-8")
    monkeypatch.setattr(preparation, "CATALOG", catalog)
    cache = tmp_path / "manuals"
    cache.mkdir()
    parsed_bytes = []

    def pdf_reader(stream):
        assert isinstance(stream, io.BytesIO)
        parsed_bytes.append(stream.getvalue())
        return SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: "Fixture body."),
                                      SimpleNamespace(extract_text=lambda: None)])

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=pdf_reader))
    network = []

    class Opener:
        def open(self, url, timeout):
            network.append((url, timeout))
            return io.BytesIO(payload)

    monkeypatch.setattr(preparation.urllib.request, "build_opener", lambda *args: Opener())
    return cache, catalog, source, payload, parsed_bytes, network


def write_catalog(catalog, source):
    catalog.write_text(json.dumps({"sources": [source]}), encoding="utf-8")


def test_prepare_downloads_only_pinned_payload_and_offline_reuses_pdf(prepared_environment):
    cache, catalog, source, payload, parsed, network = prepared_environment
    report = preparation.prepare(cache)
    assert (cache / "base.pdf").read_bytes() == payload
    assert parsed == [payload]
    assert network == [(source["url"], 45)]
    index = json.loads((cache / "base.json").read_text(encoding="utf-8"))
    assert index["pdf_sha256"] == report[0]["sha256"] == source["sha256"]
    assert index["pages"] == [{"page": 1, "text": "Fixture body."}, {"page": 2, "text": ""}]
    # An unrelated staging path must not be overwritten by preparation.
    (cache / "base.json.pending").write_text("Keep this file.", encoding="utf-8")
    preparation.prepare(cache, offline=True)
    assert len(network) == 1
    assert (cache / "base.json.pending").read_text(encoding="utf-8") == "Keep this file."


def test_wrong_digest_never_writes_pdf_or_index(prepared_environment):
    cache, catalog, source, payload, parsed, network = prepared_environment
    source["sha256"] = "0" * 64
    write_catalog(catalog, source)
    with pytest.raises(ValueError, match="verified edition"):
        preparation.prepare(cache)
    assert list(cache.iterdir()) == [] and parsed == []


def test_wrong_existing_pdf_is_preserved_and_not_refetched(prepared_environment):
    cache, catalog, source, payload, parsed, network = prepared_environment
    (cache / "base.pdf").write_bytes(b"User file must remain intact.")
    with pytest.raises(ValueError, match="verified edition"):
        preparation.prepare(cache)
    assert (cache / "base.pdf").read_bytes() == b"User file must remain intact."
    assert network == [] and parsed == []


@pytest.mark.parametrize("field,name", [
    ("pdf_file", "../outside.pdf"), ("pdf_file", "..\\outside.pdf"),
    ("pdf_file", "C:\\outside.pdf"), ("pdf_file", "base.pdf:stream"),
    ("pdf_file", "CON.pdf"), ("pdf_file", "base.PDF"),
    ("index_file", "../outside.json"), ("index_file", "LPT1.json"),
])
def test_catalog_rejects_unsafe_names_before_network(prepared_environment, field, name):
    cache, catalog, source, payload, parsed, network = prepared_environment
    source[field] = name
    write_catalog(catalog, source)
    with pytest.raises(ValueError, match="catalog filename"):
        preparation.prepare(cache)
    assert network == [] and list(cache.iterdir()) == []


@pytest.mark.parametrize("url", [
    "http://downloads.2kgames.com/test.pdf", "https://downloads.2kgames.com.evil.test/a.pdf",
    "https://user:password@downloads.2kgames.com/a.pdf", "https://downloads.2kgames.com:8080/a.pdf",
    "file:///C:/private.pdf", "https://downloads.2kgames.com:wrong/a.pdf", "https://[invalid",
])
def test_invalid_source_urls_and_redirects_are_rejected(url):
    assert not preparation.official_url(url)
    with pytest.raises(ValueError, match="outside official"):
        preparation.OfficialRedirects().redirect_request(
            Request("https://downloads.2kgames.com/a.pdf"), None, 302, "Found", {}, url)


def test_official_https_redirect_is_allowed():
    target = "https://cdn.2kgames.com/manuals/test.pdf"
    assert preparation.official_url(target)
    redirected = preparation.OfficialRedirects().redirect_request(
        Request("https://downloads.2kgames.com/test.pdf"), None, 302, "Found", {}, target)
    assert redirected.full_url == target


def test_offline_missing_pdf_never_downloads(prepared_environment):
    cache, catalog, source, payload, parsed, network = prepared_environment
    with pytest.raises(FileNotFoundError, match="Missing local manual"):
        preparation.prepare(cache, offline=True)
    assert network == []


def test_oversized_download_never_parses_or_writes(prepared_environment, monkeypatch):
    cache, catalog, source, payload, parsed, network = prepared_environment
    monkeypatch.setattr(preparation, "MAX_PDF_BYTES", len(payload) - 1)
    with pytest.raises(ValueError, match="size limit"):
        preparation.prepare(cache)
    assert parsed == [] and list(cache.iterdir()) == []
