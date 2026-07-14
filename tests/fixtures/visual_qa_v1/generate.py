#!/usr/bin/env python3
"""Reproduce the S-069 v1 page-only visual QA corpus.

The historical-natural case preserves the measured geometry of the committed
``glyph_overlap/slot_overprint.hwpx`` failure.  It is intentionally a page PNG,
not a claimed Hancom render.  Running this script deterministically rewrites the
PNG files and their sha256 values in ``manifest.json``.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent
SIZE = (1200, 1600)


def _base_page() -> Image.Image:
    image = Image.new("RGB", SIZE, "white")
    draw = ImageDraw.Draw(image)
    # Heading and paragraph strokes, deliberately away from every page edge.
    draw.rectangle((150, 130, 720, 146), fill="black")
    for y, width in ((220, 760), (260, 820), (300, 690), (390, 780), (430, 620)):
        draw.rectangle((150, y, 150 + width, y + 6), fill="black")
    # A regular 3x3 table. Thin long rules must not look like a dense text band.
    for y in (580, 680, 780, 880):
        draw.rectangle((150, y, 1030, y + 2), fill="black")
    for x in (150, 445, 740, 1030):
        draw.rectangle((x, 580, x + 2, 882), fill="black")
    for y in (1010, 1050, 1090, 1190, 1230):
        draw.rectangle((150, y, 820, y + 6), fill="black")
    draw.rectangle((560, 1500, 640, 1506), fill="black")
    return image


def _save(name: str, image: Image.Image) -> str:
    path = ROOT / name
    image.save(path, format="PNG", optimize=False, compress_level=9)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    hashes: dict[str, str] = {}
    hashes["clean_page.png"] = _save("clean_page.png", _base_page())

    natural = _base_page()
    draw = ImageDraw.Draw(natural)
    # Preserved overprint morphology: several line boxes collapse into one
    # abnormally tall, dense band in the middle of the page.
    draw.rectangle((180, 940, 910, 1000), fill="black")
    for y in range(944, 998, 9):
        draw.rectangle((140, y, 980, y + 3), fill="black")
    hashes["natural_overprint_page.png"] = _save("natural_overprint_page.png", natural)

    clipped = _base_page()
    draw = ImageDraw.Draw(clipped)
    draw.rectangle((930, 920, 1199, 930), fill="black")
    hashes["injected_edge_clip_page.png"] = _save("injected_edge_clip_page.png", clipped)

    hashes["injected_blank_page.png"] = _save(
        "injected_blank_page.png", Image.new("RGB", SIZE, "white")
    )

    manifest = {
        "schema": "hwpx.visual-fixture-manifest/v1",
        "taxonomyVersion": "hwpx-visual-defects/1.0",
        "assurance": "fixture",
        "generator": {"path": "generate.py", "version": "1.0.0"},
        "cases": [
            {
                "id": "clean-layout-001",
                "classification": "clean",
                "pages": [{"page": 0, "path": "clean_page.png", "sha256": hashes["clean_page.png"]}],
                "annotations": [],
                "provenance": {"kind": "generated-clean", "generator": "generate.py"},
            },
            {
                "id": "natural-overprint-001",
                "classification": "natural",
                "pages": [{"page": 0, "path": "natural_overprint_page.png", "sha256": hashes["natural_overprint_page.png"]}],
                "annotations": [{
                    "page": 0,
                    "category": "text_clipping_overlap",
                    "severity": "critical",
                    "bbox": [0.1167, 0.587, 0.818, 0.638],
                    "labelStatus": "adjudicated",
                    "labelers": ["reviewer-a", "reviewer-b"],
                }],
                "provenance": {
                    "kind": "preserved-historical-failure-morphology",
                    "sourceDocument": "../glyph_overlap/slot_overprint.hwpx",
                    "sourceSha256": "55a971129d13627353c469a9af52619f0526aefe2b577c5852dfc8f84b29abf3",
                    "claim": "deterministic fixture, not a Hancom render",
                },
            },
            {
                "id": "injected-edge-clip-001",
                "classification": "injected",
                "pages": [{"page": 0, "path": "injected_edge_clip_page.png", "sha256": hashes["injected_edge_clip_page.png"]}],
                "annotations": [{
                    "page": 0,
                    "category": "text_clipping_overlap",
                    "severity": "critical",
                    "bbox": [0.775, 0.573, 1.0, 0.584],
                    "labelStatus": "adjudicated",
                    "labelers": ["reviewer-a", "reviewer-b"],
                }],
                "provenance": {"kind": "injected", "operation": "ink-to-right-page-edge"},
            },
            {
                "id": "injected-blank-001",
                "classification": "injected",
                "pages": [{"page": 0, "path": "injected_blank_page.png", "sha256": hashes["injected_blank_page.png"]}],
                "annotations": [{
                    "page": 0,
                    "category": "unexpected_blank_page",
                    "severity": "critical",
                    "bbox": [0.0, 0.0, 1.0, 1.0],
                    "labelStatus": "adjudicated",
                    "labelers": ["reviewer-a", "reviewer-b"],
                }],
                "provenance": {"kind": "injected", "operation": "remove-all-page-ink"},
            },
        ],
    }
    (ROOT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
