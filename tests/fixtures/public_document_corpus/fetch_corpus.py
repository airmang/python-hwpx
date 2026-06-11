#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


_DOC_LINK_RE = re.compile(
    r"""href=["'](?P<href>[^"']+\.(?:hwpx|hwp)(?:\?[^"']*)?)["']""",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CorpusEntry:
    source_page: str
    document_url: str
    filename: str
    sha256: str | None
    bytes: int | None
    public_license_hint: str | None


def _read_url(url: str, *, timeout: int) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": "python-hwpx-public-corpus-collector/1.0",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def _discover_document_urls(page_url: str, html_bytes: bytes) -> list[str]:
    html_text = html_bytes.decode("utf-8", "replace")
    urls: list[str] = []
    seen: set[str] = set()
    for match in _DOC_LINK_RE.finditer(html_text):
        href = unescape(match.group("href"))
        absolute = urljoin(page_url, href)
        if absolute in seen:
            continue
        seen.add(absolute)
        urls.append(absolute)
    return urls


def _filename_for_url(url: str) -> str:
    parsed = urlparse(url)
    name = Path(parsed.path).name or hashlib.sha256(url.encode()).hexdigest()[:16] + ".hwpx"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


def _license_hint(page_url: str) -> str | None:
    host = urlparse(page_url).netloc.lower()
    if "korea.kr" in host:
        return "Korea.kr public-sector page; verify Open Government License marker on source page."
    if "opengov.seoul.go.kr" in host:
        return "Seoul OpenGov page; verify public access/license marker on source page."
    return None


def collect(
    page_urls: Iterable[str],
    *,
    download_dir: Path | None,
    timeout: int,
) -> list[CorpusEntry]:
    entries: list[CorpusEntry] = []
    for page_url in page_urls:
        page = _read_url(page_url, timeout=timeout)
        for document_url in _discover_document_urls(page_url, page):
            filename = _filename_for_url(document_url)
            digest: str | None = None
            size: int | None = None
            if download_dir is not None:
                payload = _read_url(document_url, timeout=timeout)
                digest = hashlib.sha256(payload).hexdigest()
                size = len(payload)
                download_dir.mkdir(parents=True, exist_ok=True)
                (download_dir / filename).write_bytes(payload)
            entries.append(
                CorpusEntry(
                    source_page=page_url,
                    document_url=document_url,
                    filename=filename,
                    sha256=digest,
                    bytes=size,
                    public_license_hint=_license_hint(page_url),
                )
            )
    return entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Collect public HWPX/HWP corpus manifest entries from seed pages."
    )
    parser.add_argument("--url", action="append", default=[], help="Seed korea.kr/opengov page URL.")
    parser.add_argument("--urls-file", type=Path, help="Newline-delimited seed URL file.")
    parser.add_argument("--manifest", type=Path, required=True, help="Manifest JSON output path.")
    parser.add_argument("--download-dir", type=Path, help="Optional local download directory.")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--force", action="store_true", help="Allow overwriting an existing manifest.")
    args = parser.parse_args(argv)

    urls = list(args.url)
    if args.urls_file:
        urls.extend(
            line.strip()
            for line in args.urls_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    if not urls:
        parser.error("at least one --url or --urls-file entry is required")

    if args.manifest.exists() and not args.force:
        print(
            f"refusing to overwrite existing manifest: {args.manifest} (pass --force)",
            file=sys.stderr,
        )
        return 2

    entries = collect(urls, download_dir=args.download_dir, timeout=args.timeout)
    payload = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "seedUrls": urls,
        "downloaded": args.download_dir is not None,
        "entries": [asdict(entry) for entry in entries],
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(entries)} entries to {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
