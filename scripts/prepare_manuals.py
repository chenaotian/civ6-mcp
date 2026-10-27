"""Prepare local official PDF manuals and page indexes; never contacts the game.

Run with a Python environment containing pypdf. Only catalogued official sources
can be fetched. PDFs and derived indexes stay outside the distributable package.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "src" / "civ6_fair_mcp" / "data" / "manual_sources.json"
MAX_PDF_BYTES = 64 * 1024 * 1024
ALLOWED_HOSTS = {"cdn.2kgames.com", "downloads.2kgames.com", "assets.2k.com",
                 "steamcdn-a.akamaihd.net", "cdn.akamai.steamstatic.com",
                 "shared.akamai.steamstatic.com"}


def official_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(url)
        return (parsed.scheme == "https" and parsed.hostname in ALLOWED_HOSTS
                and parsed.username is None and parsed.password is None
                and parsed.port in (None, 443))
    except (ValueError, TypeError):
        return False


def catalog_path(directory: Path, name: str, suffix: str) -> Path:
    """Keep catalog filenames portable, and never follow a pre-existing link."""
    if (not isinstance(name, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*" + re.escape(suffix), name) is None
            or name.split(".")[0].upper() in {
                "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10))}):
        raise ValueError("Invalid catalog filename")
    path = directory / name
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("Manual cache path is not a regular file")
    return path


class OfficialRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        if not official_url(new_url):
            raise ValueError("Redirect outside official manual hosts")
        return super().redirect_request(request, fp, code, message, headers, new_url)


def prepare(directory: Path, *, offline: bool = False) -> list[dict]:
    # Optional preparation dependency: the MCP runtime uses only the JSON index.
    from pypdf import PdfReader

    sources = json.loads(CATALOG.read_text(encoding="utf-8"))["sources"]
    directory.mkdir(parents=True, exist_ok=True)
    report = []
    opener = urllib.request.build_opener(OfficialRedirects())
    for source in sources:
        pdf_path = catalog_path(directory, source["pdf_file"], ".pdf")
        index_path = catalog_path(directory, source["index_file"], ".json")
        expected_hash = source["sha256"]
        if not isinstance(expected_hash, str) or re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None:
            raise ValueError("Invalid verified manual digest")
        if not official_url(source["url"]):
            raise ValueError("Invalid official source URL")
        if pdf_path.exists():
            if pdf_path.stat().st_size > MAX_PDF_BYTES:
                raise ValueError(f"Oversized local manual: {source['id']}")
            with pdf_path.open("rb") as stream:
                payload = stream.read(MAX_PDF_BYTES + 1)
        else:
            if offline:
                raise FileNotFoundError(f"Missing local manual: {source['id']}")
            with opener.open(source["url"], timeout=45) as response:
                payload = response.read(MAX_PDF_BYTES + 1)
        if len(payload) > MAX_PDF_BYTES:
            raise ValueError("Official manual exceeds size limit")
        digest = hashlib.sha256(payload).hexdigest()
        if not payload.startswith(b"%PDF-") or digest != expected_hash:
            raise ValueError(f"Manual does not match the verified edition: {source['id']}")
        if not pdf_path.exists():
            # Exclusive creation avoids replacing an existing user document.
            with pdf_path.open("xb") as stream:
                stream.write(payload)
        # Parse exactly the bytes whose hash was verified, even if the path changes.
        reader = PdfReader(io.BytesIO(payload))
        if not 1 <= len(reader.pages) <= 1000:
            raise ValueError("Invalid manual page count")
        pages = [{"page": number, "text": page.extract_text() or ""}
                 for number, page in enumerate(reader.pages, 1)]
        index = {"schema_version": 1, "source_id": source["id"],
                 "url": source["url"], "pdf_sha256": digest,
                 "indexed_at": datetime.now(timezone.utc).isoformat(),
                 "extractor": "pypdf", "pages": pages}
        encoded = json.dumps(index, ensure_ascii=False, indent=2).encode("utf-8")
        if len(encoded) > 8 * 1024 * 1024:
            raise ValueError("Manual index exceeds size limit")
        # Exclusive, random staging file cannot overwrite a stale or linked file.
        with tempfile.NamedTemporaryFile(mode="wb", prefix="manual-index-", suffix=".pending",
                                         dir=directory, delete=False) as stream:
            stream.write(encoded)
            pending = Path(stream.name)
        pending.replace(index_path)
        report.append({"id": source["id"], "pages": len(pages), "sha256": digest,
                       "pdf": str(pdf_path), "index": str(index_path)})
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "manuals")
    parser.add_argument("--offline", action="store_true", help="Index existing PDFs only")
    args = parser.parse_args()
    print(json.dumps(prepare(args.directory, offline=args.offline), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
