# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import base64
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

from hwpx.document import HwpxDocument

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
HC = "{http://www.hancom.co.kr/hwpml/2011/core}"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/axwAqkAAAAASUVORK5CYII="
)

CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"


def _sample_section(name: str) -> ET.Element:
    with ZipFile(CORPUS / name) as package:
        return ET.fromstring(package.read("Contents/section0.xml"))


def test_builder_vertical_slice_hard_gates_and_sample_structures(tmp_path) -> None:
    from hwpx.builder import (
        Bullet,
        Document,
        Footer,
        Header,
        Heading,
        Image,
        Margins,
        Metadata,
        PageBreak,
        PageNumber,
        PageSize,
        Paragraph,
        Run,
        Section,
        Table,
    )

    image_path = tmp_path / "pixel.png"
    image_path.write_bytes(PNG_1X1)
    path = tmp_path / "builder-vertical-slice.hwpx"

    report = Document(
        metadata=Metadata(
            title="2026 AI 교육 운영계획",
            author="AI교육팀",
            organization="OO학교",
        ),
        sections=[
            Section(
                page=PageSize.A4,
                margins=Margins(top_mm=20, right_mm=20, bottom_mm=20, left_mm=20),
                header=Header(
                    children=[
                        Paragraph(
                            align="right",
                            children=[
                                Run("OO학교  -  ", bold=True, color="C00000"),
                                PageNumber(),
                            ],
                        )
                    ]
                ),
                footer=Footer(
                    children=[
                        Paragraph(align="center", children=[PageNumber(format="page/total")]),
                    ]
                ),
                children=[
                    Heading(level=1, text="추진 개요"),
                    Heading(level=2, text="세부 목표"),
                    Paragraph(
                        children=[
                            Run("AI 활용 수업을 "),
                            Run("전 학년", bold=True, color="1F5FBF", font="함초롬바탕", size=12),
                            Run("으로 확산한다."),
                        ]
                    ),
                    Bullet(items=["교원 연수", "수업 공개"], level=0),
                    Bullet(items=["교과별 실천 사례"], level=1),
                    Table(
                        header=["구분", "내용", "기한"],
                        rows=[
                            ["준비", "환경 점검", "3월"],
                            ["운영", "수업 적용", "4월"],
                        ],
                        column_widths=[2, 3, 1],
                        header_shading="EAF1FB",
                        merges=["A2:A3"],
                    ),
                    Image(image_path, width_mm=18, align="center", caption="학교 로고"),
                    PageBreak(),
                    Paragraph(text="다음 페이지 점검"),
                ],
            )
        ],
    ).save_to_path(path)

    assert report.hard_gates["package_validation"] == "pass"
    assert report.hard_gates["document_errors"] == "pass"
    assert report.hard_gates["reopen"] == "pass"
    assert report.hard_gates["id_integrity"] == "unavailable"
    assert report.visual_review_required is True
    for feature in (
        "metadata",
        "page_setup",
        "header_footer",
        "page_number",
        "heading",
        "rich_run",
        "list",
        "table",
        "page_break",
    ):
        assert report.feature_flags[feature] is True

    reopened = HwpxDocument.open(path)
    text = reopened.export_text()
    for expected in [
        "제목: 2026 AI 교육 운영계획",
        "추진 개요",
        "세부 목표",
        "전 학년",
        "교원 연수",
        "교과별 실천 사례",
        "학교 로고",
        "다음 페이지 점검",
    ]:
        assert expected in text
    assert "□□" not in text

    section = reopened.sections[0]
    header = section.properties.get_header()
    footer = section.properties.get_footer()
    assert header is not None
    assert footer is not None
    assert header.element.find(f"{HP}subList/{HP}p/{HP}run/{HP}t") is not None
    assert header.element.find(f".//{HP}ctrl/{HP}pageNum") is not None
    assert footer.element.find(f".//{HP}ctrl/{HP}pageNum") is not None
    assert "/" in footer.text

    sample_header_footer = _sample_section("reader_writer__HeaderFooter.hwpx")
    assert sample_header_footer.find(f".//{HP}header/{HP}subList/{HP}p/{HP}run/{HP}t") is not None
    assert sample_header_footer.find(f".//{HP}footer/{HP}subList/{HP}p/{HP}run/{HP}t") is not None

    sample_page_functions = _sample_section("reader_writer__PageFunctions.hwpx")
    assert sample_page_functions.find(f".//{HP}ctrl/{HP}pageNum") is not None

    sample_table = _sample_section("reader_writer__SimpleTable.hwpx")
    assert sample_table.find(f".//{HP}tc/{HP}cellSpan") is not None
    table = next(table for paragraph in reopened.paragraphs for table in paragraph.tables)
    assert table.cell(1, 0).span == (2, 1)
    assert table.cell(1, 0).text == "준비"
    assert table.cell(2, 0).element is table.cell(1, 0).element
    assert [table.cell(0, col).width for col in range(3)] == [7200, 10800, 3600]
    border_fill_id = table.cell(0, 0).element.get("borderFillIDRef")
    border_fill = reopened.oxml.headers[0].element.find(f".//{HH}borderFill[@id='{border_fill_id}']")
    assert border_fill.find(f"{HC}fillBrush/{HC}winBrush").get("faceColor") == "#EAF1FB"
