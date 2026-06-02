# SPDX-License-Identifier: Apache-2.0
"""Vendor hwpxlib sample .hwpx files (Apache-2.0) for use as test oracle fixtures.

Run ONCE to populate this directory, then commit the result. Tests never fetch.
Usage: python tests/fixtures/hwpxlib_corpus/fetch_corpus.py --ref <commit-sha>
Pin --ref to a specific hwpxlib commit SHA (not a moving branch) and record it in manifest.json.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import tarfile
import urllib.request
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent
TARBALL = "https://github.com/neolord0/hwpxlib/archive/{ref}.tar.gz"

# Feature label inferred from the reader_writer file stem; error/ files are regression inputs.
FEATURE_HINTS = {
    "HeaderFooter": "header_footer",
    "PageFunctions": "page_number",
    "PageSize_Margin": "page_size_margin",
    "MultiColumn": "multi_column",
    "SimpleTable": "table",
    "SimplePicture": "image",
    "SimpleEquation": "equation",
    "ChangeTrack": "track_change",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", required=True, help="hwpxlib commit SHA to pin")
    args = parser.parse_args(argv)

    url = TARBALL.format(ref=args.ref)
    print(f"downloading {url}")
    data = urllib.request.urlopen(url).read()  # noqa: S310 - pinned github url, one-time tool

    entries: list[dict[str, str]] = []
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile() or "/testFile/" not in member.name:
                continue
            if not member.name.endswith(".hwpx"):
                continue
            rel = member.name.split("/testFile/", 1)[1]
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            payload = extracted.read()
            out_name = rel.replace("/", "__")
            (CORPUS_DIR / out_name).write_bytes(payload)
            stem = Path(rel).stem
            entries.append(
                {
                    "file": out_name,
                    "source_path": f"testFile/{rel}",
                    "feature": FEATURE_HINTS.get(
                        stem,
                        "regression" if rel.startswith("error/") else "other",
                    ),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )

    entries.sort(key=lambda e: e["file"])
    manifest = {
        "source_repo": "https://github.com/neolord0/hwpxlib",
        "license": "Apache-2.0",
        "pinned_ref": args.ref,
        "count": len(entries),
        "samples": entries,
    }
    (CORPUS_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"vendored {len(entries)} samples -> {CORPUS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
