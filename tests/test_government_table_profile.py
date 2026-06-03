from hwpx import (
    DOCUMENT_PLAN_SCHEMA_VERSION,
    HwpxDocument,
    create_document_from_plan,
    normalize_document_plan,
    validate_document_plan,
)
from hwpx import authoring


def _table_plan() -> dict:
    return {
        "schemaVersion": DOCUMENT_PLAN_SCHEMA_VERSION,
        "title": "테이블 메타 보존",
        "blocks": [
            {
                "type": "table",
                "tableProfile": "government",
                "caption": "인원 현황",
                "unit": "단위: 명",
                "columns": [
                    {"key": "name", "label": " 구분 "},
                    {"key": "count", "label": " 인원\n수 "},
                    {"key": "note", "label": "비고"},
                ],
                "rows": [
                    {
                        "name": "  합계  ",
                        "count": "  10\n명  ",
                        "note": {"text": "  원문\n  유지  ", "preserveWhitespace": True},
                    }
                ],
            }
        ],
    }


def test_validate_document_plan_warns_on_unknown_table_profile() -> None:
    plan = _table_plan()
    plan["blocks"][0]["tableProfile"] = "mystery"

    report = validate_document_plan(plan)

    assert report.ok is True
    assert any(issue.code == "unknown_table_profile" for issue in report.issues)


def test_table_profile_caption_unit_and_cell_whitespace_survive_reopen(tmp_path) -> None:
    plan = _table_plan()
    normalized = normalize_document_plan(plan)
    table = normalized.blocks[0].data

    assert table["tableProfile"] == "government"
    assert table["unit"] == "단위: 명"
    assert table["columns"][1]["label"] == "인원 수"
    assert table["rows"][0]["name"] == "합계"
    assert table["rows"][0]["count"] == "10 명"
    assert table["rows"][0]["note"] == "  원문\n  유지  "

    output = tmp_path / "government-table.hwpx"
    document = create_document_from_plan(normalized)
    try:
        document.save_to_path(output)
    finally:
        document.close()

    reopened = HwpxDocument.open(output)
    try:
        text = reopened.export_text()
        assert "인원 현황" in text
        assert "단위: 명" in text
        assert "10 명" in text

        table_blocks = authoring._document_table_blocks(reopened)
        assert table_blocks[0]["caption"] == "인원 현황"
        assert table_blocks[0]["caption"] != "단위: 명"
    finally:
        reopened.close()
