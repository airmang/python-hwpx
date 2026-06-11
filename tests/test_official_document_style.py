from __future__ import annotations

from hwpx import (
    approval_box,
    create_document_from_plan,
    inspect_official_document_style,
    validate_document_plan,
)
from hwpx.builder import Document, Paragraph, Section
from hwpx.document import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety


def test_official_document_lint_accepts_core_conventions() -> None:
    report = inspect_official_document_style(
        [
            "1. 추진 개요",
            "가. 기본 방향",
            "1) 세부 추진",
            "가) 운영 방식",
            "(1) 세부 항목",
            "(가) 확인 사항",
            "일시: 2026. 6. 11.",
            "붙임 1. 세부계획서 1부.",
            "끝.",
        ]
    )

    assert report["pass"] is True
    assert report["violations"] == []


def test_official_document_lint_reports_repair_suggestions() -> None:
    report = inspect_official_document_style(
        [
            "1. 추진 개요",
            "1) 세부 추진",
            "일시 : 2026-06-11",
            "예산 1000000원",
            "붙임: 세부계획서",
            "본문 끝.",
        ]
    )

    assert report["pass"] is False
    rules = {violation["rule"] for violation in report["violations"]}
    assert {
        "item-marker-hierarchy",
        "date-notation",
        "amount-notation",
        "attachment-notation",
        "colon-question-spacing",
        "end-marker",
    }.issubset(rules)
    assert all(violation["suggestion"] for violation in report["violations"])
    assert all(
        violation["source"]["document"] == "hwpx-skill/references/official-document-rules.md"
        for violation in report["violations"]
    )


def test_official_document_lint_reads_hwpx_files(tmp_path) -> None:
    target = tmp_path / "official.hwpx"
    doc = HwpxDocument.new()
    doc.add_paragraph("1. 추진 개요")
    doc.add_paragraph("가. 기본 방향")
    doc.add_paragraph("일시: 2026. 6. 11.")
    doc.add_paragraph("끝.")
    doc.save_to_path(target)
    doc.close()

    report = inspect_official_document_style(target)

    assert report["pass"] is True
    assert report["summary"]["paragraph_count"] >= 4


def test_builder_approval_box_is_merged_and_open_safe(tmp_path) -> None:
    target = tmp_path / "approval-builder.hwpx"
    report = Document(
        preset="government_report",
        sections=[
            Section(
                children=[
                    Paragraph(text="결재란"),
                    approval_box(labels=("기안", "검토", "결재"), delegated="전결"),
                ]
            )
        ],
    ).save_to_path(target)

    assert report.hard_gates["editor_open_safety"] == "pass"
    assert validate_editor_open_safety(target).ok is True
    reopened = HwpxDocument.open(target)
    try:
        text = reopened.export_text()
        table = next(table for paragraph in reopened.paragraphs for table in paragraph.tables)
        assert "기안" in text
        assert "전결" in text
        assert table.cell(1, 0).span == (2, 1)
    finally:
        reopened.close()


def test_plan_v2_approval_box_generates_open_safe_document(tmp_path) -> None:
    target = tmp_path / "approval-plan.hwpx"
    plan = {
        "schemaVersion": "hwpx.document_plan.v2",
        "preset": "government_report",
        "sections": [
            {
                "blocks": [
                    {"type": "paragraph", "text": "결재란"},
                    {
                        "type": "approval_box",
                        "labels": ["기안", "검토", "결재"],
                        "delegated": "전결",
                    },
                    {"type": "paragraph", "text": "끝."},
                ]
            }
        ],
    }

    assert validate_document_plan(plan).ok is True
    document = create_document_from_plan(plan)
    try:
        document.save_to_path(target)
    finally:
        document.close()

    assert validate_editor_open_safety(target).ok is True
    report = inspect_official_document_style(target)
    assert report["pass"] is True
