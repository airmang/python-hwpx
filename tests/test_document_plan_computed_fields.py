from __future__ import annotations

from pathlib import Path

from hwpx import (
    DOCUMENT_PLAN_SCHEMA_VERSION,
    create_document_from_plan,
    validate_document_plan,
)
from hwpx.builder import Bullet, Document, Heading, Paragraph, Run, Section, Table
from hwpx.document import HwpxDocument

DOCUMENT_PLAN_V2_SCHEMA_VERSION = "hwpx.document_plan.v2"


def _table_texts(document: HwpxDocument) -> list[str]:
    values: list[str] = []
    for paragraph in document.paragraphs:
        for table in paragraph.tables:
            for row in table.rows:
                values.extend(cell.text for cell in row.cells)
    return values


def test_v1_plan_replaces_computed_fields_in_paragraphs_and_table_cells() -> None:
    plan = {
        "schemaVersion": DOCUMENT_PLAN_SCHEMA_VERSION,
        "title": "계산 보고서",
        "blocks": [
            {
                "type": "paragraph",
                "text": "예산 {{ krw_hangul(5000000) }} / {{ commas(1234567) }}",
            },
            {
                "type": "table",
                "columns": [
                    {"key": "item", "label": "항목"},
                    {"key": "amount", "label": "금액"},
                    {"key": "ratio", "label": "비율"},
                ],
                "rows": [
                    {
                        "item": "운영비",
                        "amount": "{{ krw_hangul(5000000) }}",
                        "ratio": "{{ ratio(25, 100) }}%",
                    }
                ],
            },
        ],
    }

    report = validate_document_plan(plan)
    assert report.ok is True

    document = create_document_from_plan(plan)
    try:
        assert "{{" not in document.export_text()
        assert "예산 오백만원 / 1,234,567" in document.export_text()
        assert "오백만원" in _table_texts(document)
        assert "25.0%" in _table_texts(document)
    finally:
        document.close()


def test_plan_v2_and_builder_text_replace_computed_fields(tmp_path: Path) -> None:
    builder_path = tmp_path / "builder-computed.hwpx"
    builder_report = Document(
        sections=(
            Section(
                children=(
                    Heading(level=1, text="보고일 {{ date('2026. 6. 2.') }}"),
                    Paragraph(children=(Run("금액 {{ krw_hangul(5000000) }}"),)),
                    Bullet(items=("증감 {{ delta(-5) }}",)),
                )
            ),
        )
    ).save_to_path(builder_path)
    assert builder_report.reopened.ok is True

    reopened = HwpxDocument.open(builder_path)
    try:
        text = reopened.export_text()
        assert "보고일 2026-06-02" in text
        assert "금액 오백만원" in text
        assert "증감 △5" in text
        assert "{{" not in text
    finally:
        reopened.close()

    plan = {
        "schemaVersion": DOCUMENT_PLAN_V2_SCHEMA_VERSION,
        "sections": [
            {
                "blocks": [
                    {"type": "paragraph", "text": "쉼표 {{ commas(1234567) }}"},
                    {
                        "type": "table",
                        "header": ["항목", "일자"],
                        "rows": [["보고", "{{ date('2026/06/02') }}"]],
                    },
                ]
            }
        ],
    }
    assert validate_document_plan(plan).ok is True
    document = create_document_from_plan(plan)
    try:
        assert "쉼표 1,234,567" in document.export_text()
        assert "2026-06-02" in _table_texts(document)
    finally:
        document.close()


def test_unknown_or_malformed_computed_field_is_validation_error() -> None:
    unknown = {
        "schemaVersion": DOCUMENT_PLAN_SCHEMA_VERSION,
        "title": "Invalid",
        "blocks": [{"type": "paragraph", "text": "{{ unknown(1) }}"}],
    }
    report = validate_document_plan(unknown)
    assert report.ok is False
    assert any(issue.code == "unknown_computed_field" for issue in report.issues)

    malformed = {
        "schemaVersion": DOCUMENT_PLAN_SCHEMA_VERSION,
        "title": "Invalid",
        "blocks": [{"type": "paragraph", "text": "{{ commas(123)"}],
    }
    report = validate_document_plan(malformed)
    assert report.ok is False
    assert any(issue.code == "invalid_computed_field" for issue in report.issues)


def test_computed_field_parser_does_not_use_eval_or_exec() -> None:
    source = Path("src/hwpx/authoring.py").read_text(encoding="utf-8")
    assert "eval(" not in source
    assert "exec(" not in source
