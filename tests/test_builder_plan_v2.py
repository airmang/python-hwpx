from __future__ import annotations

import base64

from hwpx import create_document_from_plan, validate_document_plan
from hwpx.builder import (
    Bullet,
    Document,
    Footer,
    Header,
    Heading,
    Image,
    Margins,
    Metadata,
    NumberedList,
    PageBreak,
    PageNumber,
    PageSize,
    Paragraph,
    Run,
    Section,
    Table,
)
from hwpx.document import HwpxDocument

HC = "{http://www.hancom.co.kr/hwpml/2011/core}"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

PLAN_V2_SCHEMA_VERSION = "hwpx.document_plan.v2"
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/axwAqkAAAAASUVORK5CYII="
)


def _builder_document(image_path) -> Document:
    return Document(
        metadata=Metadata(
            title="Plan v2 parity",
            author="AI Education Team",
            organization="Sample School",
        ),
        visual_review_required=True,
        sections=[
            Section(
                page=PageSize.A4,
                margins=Margins(top_mm=18, right_mm=16, bottom_mm=18, left_mm=16),
                header=Header(
                    children=[
                        Paragraph(
                            align="right",
                            children=[
                                Run("Sample School  -  ", bold=True, color="C00000"),
                                PageNumber(),
                            ],
                        )
                    ]
                ),
                footer=Footer(
                    children=[
                        Paragraph(
                            align="center",
                            children=[PageNumber(format="page/total")],
                        )
                    ]
                ),
                children=[
                    Heading(level=1, text="추진 개요"),
                    Paragraph(
                        children=[
                            Run("plain "),
                            Run(
                                "rich",
                                bold=True,
                                italic=True,
                                underline=True,
                                color="C00000",
                                font="함초롬바탕",
                                size=12,
                                highlight="FFFF00",
                                strike=True,
                            ),
                        ]
                    ),
                    Bullet(items=["목표 설정", "예산 편성"], level=0),
                    Bullet(items=["세부 목표"], level=1),
                    NumberedList(items=["1단계", "2단계"], level=0),
                    NumberedList(items=["세부 단계"], level=1),
                    Table(
                        header=["구분", "내용", "기한"],
                        rows=[
                            ["1단계", "기반 구축", "3월"],
                            ["2단계", "운영", "4월"],
                        ],
                        merges=["A1:C1"],
                        header_shading="EAF1FB",
                        column_widths=[2, 3, 1],
                    ),
                    Image(image_path, width_mm=18, align="center", caption="학교 로고"),
                    PageBreak(),
                    Paragraph(text="다음 쪽"),
                ],
            )
        ],
    )


def _plan_v2(image_path) -> dict:
    return {
        "schemaVersion": PLAN_V2_SCHEMA_VERSION,
        "metadata": {
            "title": "Plan v2 parity",
            "author": "AI Education Team",
            "organization": "Sample School",
        },
        "visualReviewRequired": True,
        "sections": [
            {
                "page": {"preset": "A4"},
                "margins": {"topMm": 18, "rightMm": 16, "bottomMm": 18, "leftMm": 16},
                "header": {
                    "children": [
                        {
                            "type": "paragraph",
                            "align": "right",
                            "children": [
                                {
                                    "type": "run",
                                    "text": "Sample School  -  ",
                                    "bold": True,
                                    "color": "C00000",
                                },
                                {"type": "page_number"},
                            ],
                        }
                    ]
                },
                "footer": {
                    "children": [
                        {
                            "type": "paragraph",
                            "align": "center",
                            "children": [{"type": "page_number", "format": "page/total"}],
                        }
                    ]
                },
                "blocks": [
                    {"type": "heading", "level": 1, "text": "추진 개요"},
                    {
                        "type": "paragraph",
                        "children": [
                            {"type": "run", "text": "plain "},
                            {
                                "type": "run",
                                "text": "rich",
                                "bold": True,
                                "italic": True,
                                "underline": True,
                                "color": "C00000",
                                "font": "함초롬바탕",
                                "size": 12,
                                "highlight": "FFFF00",
                                "strike": True,
                            },
                        ],
                    },
                    {"type": "bullets", "level": 0, "items": ["목표 설정", "예산 편성"]},
                    {"type": "bullets", "level": 1, "items": ["세부 목표"]},
                    {"type": "numbered_list", "level": 0, "items": ["1단계", "2단계"]},
                    {"type": "numbered_list", "level": 1, "items": ["세부 단계"]},
                    {
                        "type": "table",
                        "header": ["구분", "내용", "기한"],
                        "rows": [
                            ["1단계", "기반 구축", "3월"],
                            ["2단계", "운영", "4월"],
                        ],
                        "merges": ["A1:C1"],
                        "headerShading": "EAF1FB",
                        "columnWidths": [2, 3, 1],
                    },
                    {
                        "type": "image",
                        "path": str(image_path),
                        "widthMm": 18,
                        "align": "center",
                        "caption": "학교 로고",
                    },
                    {"type": "page_break"},
                    {"type": "paragraph", "text": "다음 쪽"},
                ],
            }
        ],
    }


def _signature(path) -> dict:
    document = HwpxDocument.open(path)
    try:
        text = document.export_text()
        header = document.sections[0].properties.get_header()
        footer = document.sections[0].properties.get_footer()
        rich_run = next(run for run in document.iter_runs() if run.text == "rich")
        table = next(table for paragraph in document.paragraphs for table in paragraph.tables)
        border_fill_id = table.cell(0, 0).element.get("borderFillIDRef")
        border_fill = document.oxml.headers[0].element.find(f".//{{http://www.hancom.co.kr/hwpml/2011/head}}borderFill[@id='{border_fill_id}']")
        refs_by_text = {
            paragraph.text: paragraph.para_pr_id_ref
            for paragraph in document.paragraphs
            if paragraph.text in {"목표 설정", "세부 목표", "1단계", "세부 단계"}
        }
        return {
            "text": text,
            "header_text": header.text if header is not None else "",
            "header_page_number": header is not None and header.element.find(f".//{HP}ctrl/{HP}pageNum") is not None,
            "footer_page_number": footer is not None and footer.element.find(f".//{HP}ctrl/{HP}pageNum") is not None,
            "rich_color": rich_run.style.attributes["textColor"],
            "rich_highlight": rich_run.style.attributes["shadeColor"],
            "rich_strike": rich_run.style.child_attributes["strikeout"]["shape"],
            "bullet_level": document.paragraph_property(refs_by_text["세부 목표"]).heading.level,
            "number_level": document.paragraph_property(refs_by_text["세부 단계"]).heading.level,
            "table_span": table.cell(0, 0).span,
            "table_widths": [table.cell(1, col).width for col in range(3)],
            "table_shading": border_fill.find(f"{HC}fillBrush/{HC}winBrush").get("faceColor"),
            "has_image": document.oxml.sections[0].element.find(f".//{HP}pic/{HC}img") is not None,
        }
    finally:
        document.close()


def test_plan_v2_expresses_builder_surface_and_matches_builder_output(tmp_path) -> None:
    image_path = tmp_path / "pixel.png"
    image_path.write_bytes(PNG_1X1)
    builder_path = tmp_path / "builder.hwpx"
    plan_path = tmp_path / "plan-v2.hwpx"

    _builder_document(image_path).save_to_path(builder_path)
    report = validate_document_plan(_plan_v2(image_path))
    assert report.ok is True

    document = create_document_from_plan(_plan_v2(image_path))
    try:
        document.save_to_path(plan_path)
    finally:
        document.close()

    assert _signature(plan_path) == _signature(builder_path)
