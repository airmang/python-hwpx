#!/usr/bin/env python3
"""Validate editor-authored HWPX fixtures against the shared matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from zipfile import ZipFile

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from hwpx import ObjectFinder, TextExtractor  # type: ignore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate HWPX fixture matrix")
    parser.add_argument("--fixture-root", required=True)
    parser.add_argument("--matrix", required=True)
    return parser.parse_args()


def load_matrix(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["fixtures"]


def main() -> int:
    args = parse_args()
    fixture_root = Path(args.fixture_root).resolve()
    matrix_path = Path(args.matrix).resolve()
    fixtures = load_matrix(matrix_path)

    failures: list[str] = []

    for item in fixtures:
        rel = Path(str(item["relative_path"]))
        path = fixture_root / rel
        if not path.exists():
            failures.append(f"missing fixture: {rel}")
            continue

        with TextExtractor(str(path)) as extractor:
            text = extractor.extract_text(include_nested=True)
        paragraphs = len(ObjectFinder(str(path)).find_all(tag="p"))
        tables = len(ObjectFinder(str(path)).find_all(tag="tbl"))

        with ZipFile(path) as archive:
            preview = archive.read("Preview/PrvText.txt").decode("utf-8", "ignore") if "Preview/PrvText.txt" in archive.namelist() else ""
            xml_blob = "\n".join(
                archive.read(name).decode("utf-8", "ignore")
                for name in archive.namelist()
                if name.endswith((".xml", ".hpf", ".rels"))
            )

        print(f"[FIXTURE] {item['id']} -> {rel}")
        print(f"  text_chars={len(text)} paragraphs={paragraphs} tables={tables}")

        if len(text) != int(item["text_chars"]):
            failures.append(f"{rel}: text_chars expected {item['text_chars']} got {len(text)}")
        if paragraphs != int(item["paragraphs"]):
            failures.append(f"{rel}: paragraphs expected {item['paragraphs']} got {paragraphs}")
        if tables != int(item["tables"]):
            failures.append(f"{rel}: tables expected {item['tables']} got {tables}")

        for token in item.get("preview_tokens", []):
            if str(token) not in preview:
                failures.append(f"{rel}: preview token missing: {token}")

        for tag in item.get("required_xml_tags", []):
            if f"<{tag}" not in xml_blob and f":{tag}" not in xml_blob:
                failures.append(f"{rel}: xml tag missing: {tag}")

    if failures:
        print("[FAIL] fixture smoke matrix")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("[OK] fixture smoke matrix passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
