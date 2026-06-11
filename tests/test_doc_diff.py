from __future__ import annotations

from hwpx import (
    build_comparison_table_plan,
    create_document_from_plan,
    diff_paragraphs,
    doc_diff,
    inspect_reference_consistency,
    validate_document_plan,
)
from hwpx.document import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety


def test_diff_paragraphs_classifies_equal_added_removed_changed() -> None:
    changes = diff_paragraphs(
        ["제1조 목적", "제2조 예산", "제3조 시행"],
        ["제1조 목적", "제2조 예산 변경", "제2조의2 추가", "제3조 시행"],
    )

    assert [change["tag"] for change in changes] == ["equal", "changed", "added", "equal"]
    assert changes[1]["old_text"] == "제2조 예산"
    assert changes[1]["new_text"] == "제2조 예산 변경"


def test_diff_paragraphs_handles_removal_boundary() -> None:
    changes = diff_paragraphs(["A", "B", "C"], ["A", "C"])

    assert [change["tag"] for change in changes] == ["equal", "removed", "equal"]
    assert changes[1]["old_index"] == 1
    assert changes[1]["new_index"] is None


def test_doc_diff_accepts_text_sources() -> None:
    report = doc_diff("A\nB\nC", "A\nB2\nC")

    assert report["report_version"] == "doc-diff-v1"
    assert report["summary"]["counts"] == {
        "equal": 2,
        "added": 0,
        "removed": 0,
        "changed": 1,
    }


def test_comparison_table_plan_generates_open_safe_document(tmp_path) -> None:
    target = tmp_path / "comparison.hwpx"
    plan = build_comparison_table_plan(
        ["제1조 목적", "제2조 예산"],
        ["제1조 목적", "제2조 예산 변경", "제3조 시행"],
        include_equal=False,
    )

    assert validate_document_plan(plan).ok is True
    document = create_document_from_plan(plan)
    try:
        document.save_to_path(target)
    finally:
        document.close()

    assert validate_editor_open_safety(target).ok is True
    reopened = HwpxDocument.open(target)
    try:
        text = reopened.export_text()
        assert "신구대조표" in text
        assert "변경" in text
        assert "추가" in text
    finally:
        reopened.close()


def test_reference_consistency_passes_matching_references() -> None:
    report = inspect_reference_consistency(
        [
            "붙임 1 참조",
            "표 1. 예산 현황",
            "그림 1. 조직도",
            "붙임 1. 세부계획서 1부.",
        ]
    )

    assert report["pass"] is True
    assert report["violations"] == []


def test_reference_consistency_detects_attachment_and_numbering_gaps() -> None:
    report = inspect_reference_consistency(
        [
            "붙임 2 참조",
            "표 1. 예산 현황",
            "표 3. 세부 현황",
            "그림 2. 조직도",
            "붙임 1. 세부계획서 1부.",
        ]
    )

    assert report["pass"] is False
    rules = {violation["rule"] for violation in report["violations"]}
    assert "attachment-reference" in rules
    assert "table-numbering" in rules
    assert "figure-numbering" in rules
    assert all(violation["suggestion"] for violation in report["violations"])
