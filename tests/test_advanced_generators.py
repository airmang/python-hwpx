from __future__ import annotations

import base64

from hwpx import (
    build_image_grid,
    build_meeting_nameplates,
    build_organization_chart,
    create_document_from_plan,
    validate_document_plan,
)
from hwpx.document import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/axwAqkAAAAASUVORK5CYII="
)


def test_image_grid_plan_v2_generates_open_safe_photo_sheet(tmp_path) -> None:
    image_a = tmp_path / "site-a.png"
    image_b = tmp_path / "site-b.png"
    image_a.write_bytes(PNG_1X1)
    image_b.write_bytes(PNG_1X1)
    target = tmp_path / "photo-sheet.hwpx"
    plan = {
        "schemaVersion": "hwpx.document_plan.v2",
        "sections": [
            {
                "blocks": [
                    {"type": "heading", "level": 1, "text": "사진대지"},
                    build_image_grid(
                        [
                            {"path": str(image_a), "caption": "현장 전경"},
                            {"path": str(image_b), "caption": "설치 완료"},
                        ],
                        columns=2,
                        image_width_mm=20,
                    ),
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
    reopened = HwpxDocument.open(target)
    try:
        text = reopened.export_text()
        assert "사진 1" in text
        assert "현장 전경" in text
        assert "설치 완료" in text
        assert len(reopened.picture_references()) == 2
    finally:
        reopened.close()


def test_image_grid_validation_requires_images() -> None:
    report = validate_document_plan(
        {
            "schemaVersion": "hwpx.document_plan.v2",
            "sections": [{"blocks": [{"type": "image_grid", "images": []}]}],
        }
    )

    assert report.ok is False
    assert any(issue.code == "missing_image_grid_images" for issue in report.issues)


def test_meeting_nameplates_generator_returns_table_block() -> None:
    block = build_meeting_nameplates(["김하나", "이두리", "박세진"], columns=2)

    assert block["type"] == "table"
    assert block["header"] == ["명패 1", "명패 2"]
    assert block["rows"] == [["김하나", "이두리"], ["박세진", ""]]


def test_organization_chart_generator_supports_three_levels_and_open_safety(tmp_path) -> None:
    target = tmp_path / "org-chart.hwpx"
    chart = build_organization_chart(
        {
            "name": "위원장",
            "children": [
                {
                    "name": "기획팀",
                    "children": [{"name": "교육과정"}, {"name": "예산"}],
                },
                {
                    "name": "운영팀",
                    "children": [{"name": "시설"}, {"name": "홍보"}],
                },
            ],
        },
        max_depth=3,
    )
    plan = {
        "schemaVersion": "hwpx.document_plan.v2",
        "sections": [{"blocks": [{"type": "heading", "level": 1, "text": "조직도"}, chart]}],
    }

    assert chart["header"] == ["1단계", "2단계", "3단계"]
    assert ["위원장", "기획팀", "교육과정"] in chart["rows"]
    assert validate_document_plan(plan).ok is True
    document = create_document_from_plan(plan)
    try:
        document.save_to_path(target)
    finally:
        document.close()

    assert validate_editor_open_safety(target).ok is True
