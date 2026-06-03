# SPDX-License-Identifier: Apache-2.0
"""Inventory body elements still represented by ``GenericElement``."""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import is_dataclass
from pathlib import Path
from typing import Any, Iterable

from hwpx.document import HwpxDocument
from hwpx.oxml import GenericElement, parse_section_xml


def _manifest_samples(corpus_dir: Path) -> list[str]:
    manifest_path = corpus_dir / "manifest.json"
    if manifest_path.exists():
        payload = json.loads(manifest_path.read_text("utf-8"))
        return [sample["file"] for sample in payload["samples"]]
    return sorted(path.name for path in corpus_dir.glob("*.hwpx"))


def _model_sections(source: str | Path | bytes) -> Iterable[Any]:
    with HwpxDocument.open(source) as document:
        for section in document.oxml.sections:
            yield parse_section_xml(ET.tostring(section.element, encoding="utf-8"))


def _walk_model(value: Any) -> Iterable[GenericElement]:
    if isinstance(value, GenericElement):
        yield value
        for child in value.children:
            yield from _walk_model(child)
        return

    if isinstance(value, (str, bytes, bytearray, dict)) or value is None:
        return

    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk_model(item)
        return

    if is_dataclass(value):
        for field in getattr(value, "__dataclass_fields__", {}):
            yield from _walk_model(getattr(value, field))


def scan_file(path: str | Path) -> Counter[str]:
    """Return GenericElement counts for one HWPX body."""

    counts: Counter[str] = Counter()
    for section in _model_sections(path):
        for element in _walk_model(section):
            counts[element.name] += 1
    return counts


def scan_corpus(corpus_dir: str | Path) -> dict[str, dict[str, Any]]:
    """Return GenericElement counts and document coverage by local tag name."""

    root = Path(corpus_dir)
    counts: Counter[str] = Counter()
    samples_by_tag: dict[str, set[str]] = defaultdict(set)

    for sample in _manifest_samples(root):
        path = root / sample
        sample_counts = scan_file(path)
        counts.update(sample_counts)
        for tag in sample_counts:
            samples_by_tag[tag].add(sample)

    return {
        tag: {
            "count": count,
            "documents": len(samples_by_tag[tag]),
            "samples": sorted(samples_by_tag[tag]),
        }
        for tag, count in counts.items()
    }


def top_entries(inventory: dict[str, dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    """Return inventory rows sorted by frequency, then document coverage."""

    rows = [
        {
            "tag": tag,
            "count": entry["count"],
            "documents": entry["documents"],
            "samples": entry["samples"],
        }
        for tag, entry in inventory.items()
    ]
    rows.sort(key=lambda row: (-row["count"], -row["documents"], row["tag"]))
    return rows[:limit]


def write_inventory(corpus_dir: str | Path, output: str | Path, *, limit: int = 20) -> dict[str, Any]:
    """Scan *corpus_dir* and write a JSON report to *output*."""

    root = Path(corpus_dir)
    inventory = scan_corpus(root)
    payload = {
        "corpus_dir": str(root),
        "sample_count": len(_manifest_samples(root)),
        "top": top_entries(inventory, limit=limit),
        "inventory": {
            tag: inventory[tag]
            for tag in sorted(
                inventory,
                key=lambda name: (
                    -inventory[name]["count"],
                    -inventory[name]["documents"],
                    name,
                ),
            )
        },
    }
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus_dir", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("work/s025-coverage/generic_inventory.json"),
    )
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)

    payload = write_inventory(args.corpus_dir, args.output, limit=args.limit)
    for row in payload["top"]:
        print(f"{row['tag']}\t{row['count']}\t{row['documents']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
