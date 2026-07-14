# SPDX-License-Identifier: Apache-2.0
"""Versioned, hash-verified page-only fixture corpus loader."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .qa_contracts import TAXONOMY_VERSION, DefectCategory, FindingSeverity, NormalizedBBox


FIXTURE_MANIFEST_SCHEMA = "hwpx.visual-fixture-manifest/v1"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class FixtureAnnotation:
    page: int
    category: DefectCategory
    severity: FindingSeverity
    bbox: NormalizedBBox
    labelers: tuple[str, ...]
    label_status: str


@dataclass(frozen=True)
class FixturePage:
    page: int
    path: Path
    sha256: str


@dataclass(frozen=True)
class FixtureCase:
    case_id: str
    classification: str
    pages: tuple[FixturePage, ...]
    annotations: tuple[FixtureAnnotation, ...]
    provenance: dict[str, Any]


@dataclass(frozen=True)
class FixtureCorpus:
    root: Path
    schema: str
    taxonomy_version: str
    assurance: str
    cases: tuple[FixtureCase, ...]

    def receipt(self, case: FixtureCase) -> dict[str, Any]:
        """Return honest fixture evidence; it cannot claim a Hancom render."""

        return {
            "receiptVersion": "hwpx.fixture-render-receipt/v1",
            "renderSource": "deterministic_fixture",
            "assurance": "fixture",
            "renderChecked": False,
            "realHancom": False,
            "caseId": case.case_id,
            "pages": [
                {"page": page.page, "sha256": page.sha256, "path": page.path.name}
                for page in case.pages
            ],
        }


def load_fixture_manifest(path: str | Path, *, verify_hashes: bool = True) -> FixtureCorpus:
    manifest_path = Path(path).resolve()
    root = manifest_path.parent
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if raw.get("schema") != FIXTURE_MANIFEST_SCHEMA:
        raise ValueError(f"unsupported fixture manifest schema: {raw.get('schema')!r}")
    if raw.get("assurance") != "fixture":
        raise ValueError("fixture manifest assurance must be exactly 'fixture'")
    if raw.get("taxonomyVersion") != TAXONOMY_VERSION:
        raise ValueError(f"unsupported taxonomy version: {raw.get('taxonomyVersion')!r}")
    cases: list[FixtureCase] = []
    seen: set[str] = set()
    for item in raw.get("cases", []):
        case_id = str(item["id"])
        if case_id in seen:
            raise ValueError(f"duplicate fixture case id: {case_id}")
        seen.add(case_id)
        classification = str(item["classification"])
        if classification not in {"clean", "natural", "injected"}:
            raise ValueError(f"unsupported fixture classification: {classification}")
        pages: list[FixturePage] = []
        page_numbers: set[int] = set()
        for page_raw in item.get("pages", []):
            page_no = int(page_raw["page"])
            if page_no in page_numbers:
                raise ValueError(f"duplicate page {page_no} in {case_id}")
            page_numbers.add(page_no)
            page_path = (root / str(page_raw["path"])).resolve()
            if not page_path.is_relative_to(root) or page_path.suffix.lower() != ".png":
                raise ValueError("fixture pages must be PNG files inside the corpus root")
            expected_hash = str(page_raw["sha256"])
            if verify_hashes and sha256_file(page_path) != expected_hash:
                raise ValueError(f"fixture page hash mismatch: {page_path.name}")
            pages.append(FixturePage(page_no, page_path, expected_hash))
        if not pages:
            raise ValueError(f"fixture case has no pages: {case_id}")
        annotations: list[FixtureAnnotation] = []
        for ann in item.get("annotations", []):
            page_no = int(ann["page"])
            if page_no not in page_numbers:
                raise ValueError(f"annotation references missing page {page_no} in {case_id}")
            bbox = ann["bbox"]
            labelers = tuple(str(value) for value in ann.get("labelers", []))
            label_status = str(ann.get("labelStatus", "pending"))
            if label_status not in {"pending", "disagreement", "adjudicated"}:
                raise ValueError("unsupported annotation label status")
            if label_status == "adjudicated" and len(set(labelers)) < 2:
                raise ValueError("adjudicated ground truth requires two independent labelers")
            annotations.append(
                FixtureAnnotation(
                    page_no,
                    DefectCategory(str(ann["category"])),
                    FindingSeverity(str(ann["severity"])),
                    NormalizedBBox(*map(float, bbox)),
                    labelers,
                    label_status,
                )
            )
        if classification == "clean" and annotations:
            raise ValueError("clean fixture cannot contain defect annotations")
        if classification != "clean" and not annotations:
            raise ValueError("defect fixture must contain ground-truth annotations")
        provenance = dict(item.get("provenance", {}))
        source_document = provenance.get("sourceDocument")
        source_hash = provenance.get("sourceSha256")
        if source_document or source_hash:
            if not isinstance(source_document, str) or not isinstance(source_hash, str):
                raise ValueError("historical provenance requires sourceDocument and sourceSha256")
            source_path = (root / source_document).resolve()
            if verify_hashes and sha256_file(source_path) != source_hash:
                raise ValueError(f"historical source hash mismatch: {source_path.name}")
        cases.append(
            FixtureCase(
                case_id,
                classification,
                tuple(sorted(pages, key=lambda page: page.page)),
                tuple(annotations),
                provenance,
            )
        )
    if not cases:
        raise ValueError("fixture manifest contains no cases")
    return FixtureCorpus(
        root=root,
        schema=FIXTURE_MANIFEST_SCHEMA,
        taxonomy_version=str(raw["taxonomyVersion"]),
        assurance="fixture",
        cases=tuple(cases),
    )


__all__ = [
    "FIXTURE_MANIFEST_SCHEMA",
    "FixtureAnnotation",
    "FixturePage",
    "FixtureCase",
    "FixtureCorpus",
    "load_fixture_manifest",
    "sha256_file",
]
