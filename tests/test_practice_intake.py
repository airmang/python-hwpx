from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from hwpx.practice import (
    ReviewDecision,
    apply_review_decision,
    intake_discovery_rows,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _row(path: Path, **updates: object) -> dict[str, object]:
    result: dict[str, object] = {
        "relative_path": path.name,
        "sha256": _sha(path),
        "size_bytes": path.stat().st_size,
        "family": "form",
        "state": "clean",
        "complexity": "medium",
        "privacy_risk": "none_detected",
        "practice_suitability": "candidate_template",
        "open_safety_ok": True,
        "x_group": "",
        "t_group": "",
        "near_group": "",
    }
    result.update(updates)
    return result


def test_intake_is_deterministic_read_only_and_redacted(tmp_path: Path) -> None:
    source = tmp_path / "source"
    work = tmp_path / "work"
    source.mkdir()
    document = source / "민감한 이름.hwpx"
    document.write_bytes(b"test-package")
    before = document.read_bytes()

    first = intake_discovery_rows(
        source_root=source,
        work_root=work,
        rows=[_row(document)],
        id_key=b"i" * 32,
        storage_key_id="local-test",
    )
    second = intake_discovery_rows(
        source_root=source,
        work_root=work,
        rows=[_row(document)],
        id_key=b"i" * 32,
        storage_key_id="local-test",
    )

    assert first.private_records == second.private_records
    assert first.redacted_records == second.redacted_records
    assert first.source_integrity["unchanged"] is True
    assert document.read_bytes() == before
    assert not work.exists()
    assert "민감한 이름" not in repr(first.redacted_records)
    assert first.redacted_records[0]["practiceEligibility"] == "ineligible"


def test_intake_builds_transitive_lineage_from_discovery_groups(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    paths = []
    for index in range(3):
        path = source / f"d{index}.hwpx"
        path.write_bytes(f"document-{index}".encode())
        paths.append(path)
    rows = [
        _row(paths[0], x_group="x1"),
        _row(paths[1], x_group="x1", near_group="n1"),
        _row(paths[2], near_group="n1"),
    ]
    result = intake_discovery_rows(
        source_root=source,
        work_root=tmp_path / "work",
        rows=rows,
        id_key=b"i" * 32,
        storage_key_id="test",
    )

    assert len(set(result.lineage_groups.values())) == 1
    assert len(result.lineage_edges) == 2


def test_intake_retains_byte_identical_occurrences_in_one_lineage(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    first = source / "copy-a.hwpx"
    second = source / "copy-b.hwpx"
    first.write_bytes(b"same-document")
    second.write_bytes(b"same-document")
    result = intake_discovery_rows(
        source_root=source,
        work_root=tmp_path / "work",
        rows=[_row(first, x_group="duplicate"), _row(second, x_group="duplicate")],
        id_key=b"i" * 32,
        storage_key_id="test",
    )

    assert len(result.private_records) == 2
    assert len({record["documentId"] for record in result.private_records}) == 2
    assert len(set(result.lineage_groups.values())) == 1


@pytest.mark.parametrize(
    ("recommendation", "expected"),
    [
        ("quarantine_privacy", "quarantine"),
        ("hold_repair_required", "repair_negative"),
        ("exclude_exact_duplicate", "excluded_duplicate"),
        ("candidate_template", "unreviewed"),
    ],
)
def test_intake_maps_fail_closed_dispositions(
    tmp_path: Path, recommendation: str, expected: str
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    path = source / "d.hwpx"
    path.write_bytes(b"document")
    result = intake_discovery_rows(
        source_root=source,
        work_root=tmp_path / "work",
        rows=[_row(path, practice_suitability=recommendation)],
        id_key=b"i" * 32,
        storage_key_id="test",
    )
    assert result.private_records[0]["privacy"]["decision"] == expected


def test_review_requires_scan_content_review_and_provenance(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    path = source / "d.hwpx"
    path.write_bytes(b"document")
    record = intake_discovery_rows(
        source_root=source,
        work_root=tmp_path / "work",
        rows=[_row(path)],
        id_key=b"i" * 32,
        storage_key_id="test",
    ).private_records[0]

    with pytest.raises(ValueError, match="local_pii_scan"):
        apply_review_decision(
            record,
            ReviewDecision("approved_local_only", "owner", "now", ("content_review",)),
        )
    approved = apply_review_decision(
        record,
        ReviewDecision(
            "approved_local_only",
            "owner:local-review",
            "2026-07-13T12:00:00+09:00",
            ("content_review", "local_pii_scan"),
        ),
    )
    assert approved["privacy"]["decision"] == "approved_local_only"


def test_sanitized_promotion_requires_reviewed_derivative(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    path = source / "d.hwpx"
    path.write_bytes(b"document")
    record = intake_discovery_rows(
        source_root=source,
        work_root=tmp_path / "work",
        rows=[_row(path)],
        id_key=b"i" * 32,
        storage_key_id="test",
    ).private_records[0]
    decision = ReviewDecision(
        "approved_sanitized",
        "owner:local-review",
        "2026-07-13T12:00:00+09:00",
        ("content_review", "local_pii_scan"),
    )
    with pytest.raises(ValueError, match="reviewed derivative"):
        apply_review_decision(record, decision)


def test_intake_rejects_source_mismatch_and_overlapping_roots(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    path = source / "d.hwpx"
    path.write_bytes(b"document")
    bad = _row(path, sha256="0" * 64)
    with pytest.raises(ValueError, match="does not match"):
        intake_discovery_rows(
            source_root=source,
            work_root=tmp_path / "work",
            rows=[bad],
            id_key=b"i" * 32,
            storage_key_id="test",
        )
    with pytest.raises(ValueError, match="disjoint"):
        intake_discovery_rows(
            source_root=source,
            work_root=source / "work",
            rows=[_row(path)],
            id_key=b"i" * 32,
            storage_key_id="test",
        )
