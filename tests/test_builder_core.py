from __future__ import annotations

import base64
import json

from hwpx.document import HwpxDocument

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
HC = "{http://www.hancom.co.kr/hwpml/2011/core}"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/axwAqkAAAAASUVORK5CYII="
)


def test_builder_public_nodes_and_basic_save_report(tmp_path) -> None:
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

    assert all(
        node is not None
        for node in (
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
    )

    path = tmp_path / "builder-basic.hwpx"
    report = Document(
        sections=[
            Section(
                children=[
                    Paragraph(text="hello"),
                    PageBreak(),
                    Paragraph(text="after"),
                ]
            )
        ]
    ).save_to_path(path)

    assert report.path == path
    assert report.validate_package.ok
    assert report.validate_document.ok
    assert report.reopened.ok
    assert report.reopened.document is not None

    reopened = HwpxDocument.open(path)
    assert "hello" in reopened.export_text()
    assert "after" in reopened.export_text()


def test_document_facade_sets_page_size_and_margins() -> None:
    document = HwpxDocument.new()

    document.set_page_size(width=59528, height=84188, orientation="PORTRAIT", section_index=0)
    document.set_page_margins(
        top=5668,
        right=5668,
        bottom=5668,
        left=5668,
        header=2835,
        footer=2835,
        gutter=0,
        section_index=0,
    )

    section = document.sections[0]
    assert section.properties.page_size.width == 59528
    assert section.properties.page_size.height == 84188
    assert section.properties.page_margins.top == 5668
    assert section.properties.page_margins.left == 5668


def test_builder_lowers_section_page_setup_and_metadata(tmp_path) -> None:
    from hwpx.builder import Document, Margins, Metadata, PageSize, Paragraph, Section

    path = tmp_path / "builder-page-metadata.hwpx"
    report = Document(
        metadata=Metadata(
            title="2026 AI 교육 운영계획",
            author="AI교육팀",
            organization="OO학교",
        ),
        sections=[
            Section(
                page=PageSize.A4,
                margins=Margins(
                    top_mm=20,
                    right_mm=20,
                    bottom_mm=20,
                    left_mm=20,
                    header_mm=10,
                    footer_mm=10,
                ),
                children=[Paragraph(text="본문")],
            )
        ],
    ).save_to_path(path)

    assert report.metadata == {
        "title": "2026 AI 교육 운영계획",
        "author": "AI교육팀",
        "organization": "OO학교",
    }

    reopened = HwpxDocument.open(path)
    text = reopened.export_text()
    assert "제목: 2026 AI 교육 운영계획" in text
    assert "작성자: AI교육팀" in text
    assert "기관: OO학교" in text
    assert "본문" in text

    size = reopened.sections[0].properties.page_size
    margins = reopened.sections[0].properties.page_margins
    assert (size.width, size.height, size.orientation) == (59528, 84188, "PORTRAIT")
    assert (margins.top, margins.right, margins.bottom, margins.left) == (
        5669,
        5669,
        5669,
        5669,
    )
    assert (margins.header, margins.footer) == (2835, 2835)


def test_document_ensure_run_style_supports_rich_char_properties() -> None:
    document = HwpxDocument.new()

    # Corpus observation (sample data only):
    # - error__20251107__test.hwpx charPr@id=46 uses textColor="#FF0000",
    #   height="1000", child hh:fontRef with per-script ids, and
    #   hh:strikeout shape="NONE" color="#000000".
    # - error__20230728__test.hwpx charPr@id=259 uses shadeColor="#FFFF00".
    # - strike samples also show hh:strikeout shape="SOLID" color="#000000".
    style_id = document.ensure_run_style(
        bold=True,
        italic=True,
        underline=True,
        color="C00000",
        font="함초롬바탕",
        size=12,
        highlight="FFFF00",
        strike=True,
    )

    style = document.char_property(style_id)
    assert style is not None
    assert style.attributes["textColor"] == "#C00000"
    assert style.attributes["height"] == "1200"
    assert style.attributes["shadeColor"] == "#FFFF00"
    assert "bold" in style.child_attributes
    assert "italic" in style.child_attributes
    assert style.child_attributes["underline"]["type"] == "SOLID"
    assert style.child_attributes["strikeout"] == {
        "shape": "SOLID",
        "color": "#000000",
    }
    assert style.child_attributes["fontRef"] == {
        "hangul": "1",
        "latin": "1",
        "hanja": "1",
        "japanese": "1",
        "other": "1",
        "symbol": "1",
        "user": "1",
    }


def test_builder_lowers_rich_runs_and_reopen_preserves_style(tmp_path) -> None:
    from hwpx.builder import Document, Paragraph, Run, Section

    path = tmp_path / "builder-rich-run.hwpx"
    Document(
        sections=[
            Section(
                children=[
                    Paragraph(
                        children=[
                            Run("일반 "),
                            Run(
                                "강조",
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
                    )
                ]
            )
        ]
    ).save_to_path(path)

    reopened = HwpxDocument.open(path)
    rich_run = next(run for run in reopened.iter_runs() if run.text == "강조")
    assert rich_run.char_pr_id_ref is not None

    style = rich_run.style
    assert style is not None
    assert style.attributes["textColor"] == "#C00000"
    assert style.attributes["height"] == "1200"
    assert style.attributes["shadeColor"] == "#FFFF00"
    assert "bold" in style.child_attributes
    assert "italic" in style.child_attributes
    assert style.child_attributes["underline"]["type"] == "SOLID"
    assert style.child_attributes["strikeout"]["shape"] == "SOLID"


def test_ensure_run_style_supports_rich_char_properties() -> None:
    # SPIKE pin from hwpxlib corpus output only:
    # - error__20230728__test.hwpx charPr id=259 has height/textColor/shadeColor attrs,
    #   hh:fontRef child, and hh:strikeout shape="NONE".
    # - error__20230818__test.hwpx charPr id=63 uses active strikeout shape="SOLID".
    # - skeleton/header fontfaces map face "함초롬바탕" to font id "1" for each language.
    document = HwpxDocument.new()

    char_id = document.ensure_run_style(
        bold=True,
        italic=True,
        underline=True,
        color="C00000",
        font="함초롬바탕",
        size=12,
        highlight="FFFF00",
        strike=True,
    )

    style = document.char_property(char_id)
    assert style is not None
    assert style.attributes["textColor"] == "#C00000"
    assert style.attributes["shadeColor"] == "#FFFF00"
    assert style.attributes["height"] == "1200"
    assert style.child_attributes["fontRef"] == {
        "hangul": "1",
        "latin": "1",
        "hanja": "1",
        "japanese": "1",
        "other": "1",
        "symbol": "1",
        "user": "1",
    }
    assert "bold" in style.child_attributes
    assert "italic" in style.child_attributes
    assert style.child_attributes["underline"]["type"] == "SOLID"
    assert style.child_attributes["strikeout"]["shape"] == "SOLID"


def test_builder_lowers_rich_runs_and_reopen_preserves_style(tmp_path) -> None:
    from hwpx.builder import Document, Paragraph, Run, Section

    path = tmp_path / "builder-rich-runs.hwpx"
    report = Document(
        sections=[
            Section(
                children=[
                    Paragraph(
                        children=[
                            Run("plain "),
                            Run(
                                "rich",
                                bold=True,
                                color="C00000",
                                font="함초롬바탕",
                                size=12,
                                highlight="FFFF00",
                                strike=True,
                            ),
                            Run(" done"),
                        ]
                    )
                ]
            )
        ]
    ).save_to_path(path)

    assert report.reopened.ok
    reopened = HwpxDocument.open(path)
    rich_run = next(run for paragraph in reopened.paragraphs for run in paragraph.runs if run.text == "rich")
    assert rich_run.char_pr_id_ref is not None
    assert rich_run.style is not None
    assert rich_run.style.attributes["textColor"] == "#C00000"
    assert rich_run.style.attributes["shadeColor"] == "#FFFF00"
    assert rich_run.style.child_attributes["strikeout"]["shape"] == "SOLID"


def test_builder_lowers_headings_with_level_aware_styles(tmp_path) -> None:
    from hwpx.builder import Document, Heading, Paragraph, Section

    path = tmp_path / "builder-headings.hwpx"
    Document(
        sections=[
            Section(
                children=[
                    Heading(level=1, text="추진 개요"),
                    Heading(level=2, text="세부 목표"),
                    Paragraph(text="본문"),
                ]
            )
        ]
    ).save_to_path(path)

    reopened = HwpxDocument.open(path)
    paragraphs = [paragraph for paragraph in reopened.paragraphs if paragraph.text in {"추진 개요", "세부 목표", "본문"}]
    assert [paragraph.text for paragraph in paragraphs] == ["추진 개요", "세부 목표", "본문"]

    heading_1_run = paragraphs[0].runs[0]
    heading_2_run = paragraphs[1].runs[0]
    assert heading_1_run.char_pr_id_ref != heading_2_run.char_pr_id_ref
    assert heading_1_run.style is not None
    assert heading_2_run.style is not None
    assert int(heading_1_run.style.attributes["height"]) > int(heading_2_run.style.attributes["height"])


def test_ensure_numbering_creates_sample_shaped_refs() -> None:
    # SPIKE pin from tests/fixtures/hwpxlib_corpus/tool__textextractor__ParaHead.hwpx:
    # - header has hh:bullets/hh:bullet id char useImage="0" with child hh:paraHead.
    # - header has hh:numberings/hh:numbering id start with level-specific hh:paraHead.
    # - paragraph properties have hh:heading type="BULLET|NUMBER" idRef="<bullet|numbering id>" level="0|1".
    # - body paragraphs consume those properties via hp:p@paraPrIDRef.
    document = HwpxDocument.new()

    bullet_refs = document.ensure_numbering(
        kind="bullet",
        levels=[{"char": "-"}, {"char": "○"}],
    )
    number_refs = document.ensure_numbering(
        kind="number",
        levels=[{}, {}],
    )

    assert len(bullet_refs) == 2
    assert len(number_refs) == 2

    bullet_heading_0 = document.paragraph_property(bullet_refs[0]).heading
    bullet_heading_1 = document.paragraph_property(bullet_refs[1]).heading
    number_heading_0 = document.paragraph_property(number_refs[0]).heading
    number_heading_1 = document.paragraph_property(number_refs[1]).heading

    assert bullet_heading_0.type == "BULLET"
    assert bullet_heading_0.level == 0
    assert bullet_heading_1.type == "BULLET"
    assert bullet_heading_1.level == 1
    assert document.bullet(bullet_heading_0.id_ref).char == "-"
    assert document.bullet(bullet_heading_1.id_ref).char == "○"
    assert number_heading_0.type == "NUMBER"
    assert number_heading_0.level == 0
    assert number_heading_1.type == "NUMBER"
    assert number_heading_1.level == 1

    header = document.oxml.headers[0].element
    assert header.find(f".//{HH}bullets/{HH}bullet[@char='-']/{HH}paraHead") is not None
    numbering = header.find(f".//{HH}numberings/{HH}numbering[@id='{number_heading_0.id_ref}']")
    assert numbering is not None
    assert len(numbering.findall(f"{HH}paraHead")) >= 2


def test_builder_lowers_multilevel_bullets_and_numbered_lists(tmp_path) -> None:
    from hwpx.builder import Bullet, Document, NumberedList, Section

    path = tmp_path / "builder-lists.hwpx"
    Document(
        sections=[
            Section(
                children=[
                    Bullet(items=["목표 설정", "예산 편성"], level=0),
                    Bullet(items=["세부 목표"], level=1),
                    NumberedList(items=["1단계", "2단계"], level=0),
                    NumberedList(items=["세부 단계"], level=1),
                ]
            )
        ]
    ).save_to_path(path)

    reopened = HwpxDocument.open(path)
    text = reopened.export_text()
    for expected in ["목표 설정", "예산 편성", "세부 목표", "1단계", "2단계", "세부 단계"]:
        assert expected in text

    refs_by_text = {
        paragraph.text: paragraph.para_pr_id_ref
        for paragraph in reopened.paragraphs
        if paragraph.text in {"목표 설정", "세부 목표", "1단계", "세부 단계"}
    }
    assert reopened.paragraph_property(refs_by_text["목표 설정"]).heading.level == 0
    assert reopened.paragraph_property(refs_by_text["세부 목표"]).heading.level == 1
    assert reopened.paragraph_property(refs_by_text["1단계"]).heading.type == "NUMBER"
    assert reopened.paragraph_property(refs_by_text["세부 단계"]).heading.level == 1


def test_table_merge_cell_range_wrapper_uses_sample_span_shape(tmp_path) -> None:
    # SPIKE pin from reader_writer__SimpleTable.hwpx:
    # - merged anchor cell keeps hp:cellAddr and uses hp:cellSpan colSpan/rowSpan.
    # - covered physical cells remain in rows with hp:cellSpan 1x1 and hp:cellSz width/height 0.
    # - logical readers map covered positions back to the anchor cell.
    document = HwpxDocument.new()
    table = document.add_table(3, 3)
    table.cell(0, 0).text = "merged"
    table.cell(0, 1).text = "covered"
    table.cell(0, 2).text = "covered2"

    merged = document.merge_table_cells(table, "A1:C1")

    assert merged.span == (1, 3)
    assert table.cell(0, 0).text == "merged"
    assert table.cell(0, 1).element is merged.element
    assert table.cell(0, 2).element is merged.element

    physical = {cell.address: cell for row in table.rows for cell in row.cells}
    assert physical[(0, 1)].span == (1, 1)
    assert physical[(0, 1)].width == 0
    assert physical[(0, 1)].text == ""
    assert physical[(0, 2)].span == (1, 1)
    assert physical[(0, 2)].width == 0
    assert physical[(0, 2)].text == ""

    path = tmp_path / "builder-table-merge.hwpx"
    document.save_to_path(path)
    reopened = HwpxDocument.open(path)
    reopened_table = next(table for paragraph in reopened.paragraphs for table in paragraph.tables)
    assert reopened_table.cell(0, 0).span == (1, 3)
    assert reopened_table.cell(0, 1).text == "merged"


def test_table_merge_cells_accepts_spreadsheet_ranges(tmp_path) -> None:
    # SPIKE pin from reader_writer__SimpleTable.hwpx:
    # - merged cell keeps hp:cellAddr at the top-left anchor.
    # - merge span is hp:cellSpan colSpan/rowSpan.
    # - merged size is accumulated in hp:cellSz width/height; covered cells are removed or deactivated.
    document = HwpxDocument.new()
    table = document.add_table(3, 3)
    table.cell(0, 0).text = "A1"
    table.cell(1, 0).text = "A2"
    table.cell(2, 0).text = "A3"

    merged = table.merge_cells("A2:A3")
    assert merged.address == (1, 0)
    assert merged.span == (2, 1)
    assert merged.text == "A2"

    path = tmp_path / "table-merge-range.hwpx"
    document.save_to_path(path)
    reopened = HwpxDocument.open(path)
    reopened_table = reopened.paragraphs[-1].tables[0]
    assert reopened_table.cell(1, 0).span == (2, 1)
    assert reopened_table.cell(1, 0).text == "A2"


def test_builder_table_lowers_merge_ranges(tmp_path) -> None:
    from hwpx.builder import Document, Section, Table

    path = tmp_path / "builder-table-merge.hwpx"
    Document(
        sections=[
            Section(
                children=[
                    Table(
                        header=["구분", "내용", "기한"],
                        rows=[
                            ["단계", "통합", "3월"],
                            ["후속", "검증", "4월"],
                        ],
                        merges=["A1:C1"],
                    )
                ]
            )
        ]
    ).save_to_path(path)

    reopened = HwpxDocument.open(path)
    table = reopened.paragraphs[-1].tables[0]
    assert table.cell(0, 0).span == (1, 3)
    assert table.cell(0, 0).text == "구분"
    assert table.cell(1, 0).text == "단계"


def test_table_set_cell_shading_creates_fill_brush() -> None:
    # SPIKE pin from reader_writer__SimpleTable.hwpx:
    # - shaded/filled borderFill uses hc:fillBrush/hc:winBrush.
    # - winBrush carries faceColor, hatchColor, alpha attributes.
    document = HwpxDocument.new()
    table = document.add_table(2, 2)

    table.set_cell_shading(0, 0, "EAF1FB")

    border_fill_id = table.cell(0, 0).element.get("borderFillIDRef")
    assert border_fill_id is not None
    border_fill = document.oxml.headers[0].element.find(f".//{HH}borderFill[@id='{border_fill_id}']")
    assert border_fill is not None
    win_brush = border_fill.find(f"{HC}fillBrush/{HC}winBrush")
    assert win_brush is not None
    assert win_brush.get("faceColor") == "#EAF1FB"
    assert win_brush.get("hatchColor") == "#FF000000"
    assert win_brush.get("alpha") == "0"


def test_builder_table_lowers_header_shading(tmp_path) -> None:
    from hwpx.builder import Document, Section, Table

    path = tmp_path / "builder-table-shading.hwpx"
    Document(
        sections=[
            Section(
                children=[
                    Table(
                        header=["구분", "내용"],
                        rows=[["1단계", "기반 구축"]],
                        header_shading="EAF1FB",
                    )
                ]
            )
        ]
    ).save_to_path(path)

    reopened = HwpxDocument.open(path)
    table = reopened.paragraphs[-1].tables[0]
    for col_index in range(2):
        border_fill_id = table.cell(0, col_index).element.get("borderFillIDRef")
        border_fill = reopened.oxml.headers[0].element.find(f".//{HH}borderFill[@id='{border_fill_id}']")
        assert border_fill is not None
        win_brush = border_fill.find(f"{HC}fillBrush/{HC}winBrush")
        assert win_brush is not None
        assert win_brush.get("faceColor") == "#EAF1FB"


def test_table_set_column_widths_applies_weighted_cell_sizes() -> None:
    document = HwpxDocument.new()
    table = document.add_table(2, 3)

    table.set_column_widths([2, 3, 1])

    widths = [table.cell(0, col_index).width for col_index in range(3)]
    assert widths == [7200, 10800, 3600]
    assert [table.cell(1, col_index).width for col_index in range(3)] == widths


def test_builder_table_integrates_widths_shading_and_merges(tmp_path) -> None:
    from hwpx.builder import Document, Section, Table

    path = tmp_path / "builder-table-integrated.hwpx"
    Document(
        sections=[
            Section(
                children=[
                    Table(
                        header=["구분", "내용", "기한"],
                        rows=[
                            ["1단계", "기반 구축", "3월"],
                            ["2단계", "운영", "4월"],
                        ],
                        column_widths=[2, 3, 1],
                        header_shading="EAF1FB",
                        merges=["A2:A3"],
                    )
                ]
            )
        ]
    ).save_to_path(path)

    reopened = HwpxDocument.open(path)
    table = reopened.paragraphs[-1].tables[0]
    assert table.cell(1, 0).span == (2, 1)
    assert table.cell(1, 0).text == "1단계"
    assert table.cell(2, 0).element is table.cell(1, 0).element
    assert table.cell(0, 1).width > table.cell(0, 0).width > table.cell(0, 2).width
    assert [table.cell(0, col_index).text for col_index in range(3)] == ["구분", "내용", "기한"]
    border_fill_id = table.cell(0, 0).element.get("borderFillIDRef")
    border_fill = reopened.oxml.headers[0].element.find(f".//{HH}borderFill[@id='{border_fill_id}']")
    assert border_fill is not None
    assert border_fill.find(f"{HC}fillBrush/{HC}winBrush") is not None


def test_table_set_column_widths_updates_cell_sizes(tmp_path) -> None:
    # SPIKE pin from reader_writer__SimpleTable.hwpx:
    # - hp:tbl/hp:sz stores table width.
    # - each hp:tc has hp:cellSz width/height; merged anchors use summed width/height.
    document = HwpxDocument.new()
    table = document.add_table(2, 3)

    table.set_column_widths([2, 3, 1])

    assert [table.cell(0, col).width for col in range(3)] == [7200, 10800, 3600]
    path = tmp_path / "table-column-widths.hwpx"
    document.save_to_path(path)
    reopened = HwpxDocument.open(path)
    reopened_table = reopened.paragraphs[-1].tables[0]
    assert [reopened_table.cell(1, col).width for col in range(3)] == [7200, 10800, 3600]


def test_builder_table_integrates_widths_shading_and_merges(tmp_path) -> None:
    from hwpx.builder import Document, Section, Table

    path = tmp_path / "builder-table-integrated.hwpx"
    Document(
        sections=[
            Section(
                children=[
                    Table(
                        header=["구분", "내용", "기한"],
                        rows=[
                            ["1단계", "기반 구축", "3월"],
                            ["2단계", "운영", "4월"],
                        ],
                        column_widths=[2, 3, 1],
                        header_shading="EAF1FB",
                        merges=["A1:C1"],
                    )
                ]
            )
        ]
    ).save_to_path(path)

    reopened = HwpxDocument.open(path)
    table = reopened.paragraphs[-1].tables[0]
    assert table.cell(0, 0).span == (1, 3)
    assert table.cell(1, 0).text == "1단계"
    assert [table.cell(1, col).width for col in range(3)] == [7200, 10800, 3600]
    border_fill_id = table.cell(0, 0).element.get("borderFillIDRef")
    border_fill = reopened.oxml.headers[0].element.find(f".//{HH}borderFill[@id='{border_fill_id}']")
    assert border_fill.find(f"{HC}fillBrush/{HC}winBrush").get("faceColor") == "#EAF1FB"


def test_add_picture_registers_binary_and_places_body_pic(tmp_path) -> None:
    # SPIKE pin from reader_writer__SimplePicture.hwpx:
    # - body picture is hp:p/hp:run/hp:pic with child hc:img@binaryItemIDRef.
    # - hp:pic also carries hp:sz, hp:pos, hp:imgRect, hp:curSz/orgSz.
    document = HwpxDocument.new()

    pic = document.add_picture(PNG_1X1, "png", width_mm=30)

    img = pic.element.find(f"{HC}img")
    assert img is not None
    binary_ref = img.get("binaryItemIDRef")
    assert binary_ref is not None
    assert pic.element.find(f"{HP}sz") is not None
    assert pic.element.find(f"{HP}pos") is not None
    assert pic.element.find(f"{HP}imgRect") is not None
    assert pic.element.find(f"{HP}curSz") is not None
    assert document.package.has_part(f"BinData/{binary_ref}.png")
    assert any(item.get("BinData") == f"{binary_ref}.png" for item in document.list_images())

    path = tmp_path / "builder-picture.hwpx"
    document.save_to_path(path)
    reopened = HwpxDocument.open(path)
    assert reopened.oxml.sections[0].element.find(f".//{HP}pic/{HC}img") is not None


def test_builder_image_places_picture_and_caption(tmp_path) -> None:
    from hwpx.builder import Document, Image, Section

    image_path = tmp_path / "pixel.png"
    image_path.write_bytes(PNG_1X1)
    path = tmp_path / "builder-image.hwpx"

    Document(
        sections=[
            Section(
                children=[
                    Image(image_path, width_mm=30, align="center", caption="학교 로고"),
                ]
            )
        ]
    ).save_to_path(path)

    reopened = HwpxDocument.open(path)
    assert reopened.oxml.sections[0].element.find(f".//{HP}pic/{HC}img") is not None
    assert "학교 로고" in reopened.export_text()


def test_header_footer_content_and_page_number_use_sample_shapes(tmp_path) -> None:
    # SPIKE pin from reader_writer__HeaderFooter.hwpx:
    # - hp:header/hp:subList@vertAlign="TOP"/hp:p/hp:run/hp:t holds rich header text.
    # - hp:footer/hp:subList@vertAlign="BOTTOM"/hp:p/hp:run/hp:t holds footer text.
    # SPIKE pin from reader_writer__PageFunctions.hwpx:
    # - automatic page number token is hp:run/hp:ctrl/hp:pageNum
    #   with pos="BOTTOM_CENTER", formatType="DIGIT", sideChar="-".
    document = HwpxDocument.new()

    header = document.set_header_text("학교 ")
    page_number = header.add_page_number_field(format="page")
    footer = document.set_footer_content(
        [
            {
                "align": "center",
                "children": [
                    {"type": "run", "text": "쪽 "},
                    {"type": "page_number", "format": "page/total"},
                ],
            }
        ]
    )

    assert page_number.tag == f"{HP}pageNum"
    assert page_number.get("pos") == "BOTTOM_CENTER"
    assert page_number.get("formatType") == "DIGIT"
    assert page_number.get("sideChar") == "-"
    assert header.element.find(f"{HP}subList").get("vertAlign") == "TOP"
    assert footer.element.find(f"{HP}subList").get("vertAlign") == "BOTTOM"
    assert len(footer.element.findall(f".//{HP}ctrl/{HP}pageNum")) >= 1
    assert "/" in footer.text

    path = tmp_path / "header-footer-page-number.hwpx"
    document.save_to_path(path)
    reopened = HwpxDocument.open(path)
    reopened_header = reopened.sections[0].properties.get_header()
    reopened_footer = reopened.sections[0].properties.get_footer()
    assert reopened_header is not None
    assert reopened_footer is not None
    assert reopened_header.element.find(f".//{HP}ctrl/{HP}pageNum") is not None
    assert reopened_footer.element.find(f".//{HP}ctrl/{HP}pageNum") is not None


def test_builder_lowers_rich_header_footer_page_numbers(tmp_path) -> None:
    from hwpx.builder import Document, Footer, Header, PageNumber, Paragraph, Run, Section

    path = tmp_path / "builder-header-footer-page-number.hwpx"
    Document(
        sections=[
            Section(
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
                        Paragraph(
                            align="center",
                            children=[
                                PageNumber(format="page/total"),
                            ],
                        )
                    ]
                ),
                children=[Paragraph(text="본문")],
            )
        ]
    ).save_to_path(path)

    reopened = HwpxDocument.open(path)
    header = reopened.sections[0].properties.get_header()
    footer = reopened.sections[0].properties.get_footer()
    assert header is not None
    assert footer is not None
    assert "OO학교" in header.text
    assert "/" in footer.text
    assert header.element.find(f".//{HP}ctrl/{HP}pageNum") is not None
    assert footer.element.find(f".//{HP}ctrl/{HP}pageNum") is not None
    rich_text = header.element.find(f".//{HP}t[.='OO학교  -  ']")
    assert rich_text is not None
    rich_run = rich_text.getparent()
    rich_style = reopened.char_property(rich_run.get("charPrIDRef"))
    assert rich_style is not None
    assert rich_style.attributes["textColor"] == "#C00000"
    assert "bold" in rich_style.child_attributes


def test_header_footer_page_number_and_rich_content_facades(tmp_path) -> None:
    # SPIKE pin from reader_writer__HeaderFooter.hwpx:
    # - hp:header/footer contains hp:subList with vertAlign TOP/BOTTOM.
    # - subList contains hp:p > hp:run(charPrIDRef) > hp:t for text content.
    # SPIKE pin from reader_writer__PageFunctions.hwpx:
    # - section page-number control is hp:ctrl > hp:pageNum(pos, formatType, sideChar).
    # Header/footer PageNumber uses the observed hp:ctrl > hp:pageNum token.
    document = HwpxDocument.new()

    raw_header = document.sections[0].properties.set_header_text("raw")
    raw_page_num = raw_header.add_page_number_field()
    assert raw_page_num.tag == f"{HP}pageNum"
    assert raw_page_num.get("formatType") == "DIGIT"

    header = document.set_header_content(
        [
            {
                "align": "right",
                "runs": [
                    {"text": "OO학교  -  ", "bold": True},
                    {"page_number": "page"},
                ],
            }
        ]
    )
    footer = document.set_footer_content(
        [
            {
                "align": "center",
                "runs": [{"page_number": "page/total"}],
            }
        ]
    )

    assert header.text == "OO학교  -  "
    assert header.element.find(f"{HP}subList/{HP}p/{HP}run/{HP}t") is not None
    assert header.element.find(f".//{HP}ctrl/{HP}pageNum").get("formatType") == "DIGIT"
    assert footer.element.find(f"{HP}subList").get("vertAlign") == "BOTTOM"
    assert footer.element.find(f".//{HP}ctrl/{HP}pageNum").get("formatType") == "DIGIT"

    path = tmp_path / "builder-header-footer-facade.hwpx"
    document.save_to_path(path)
    reopened = HwpxDocument.open(path)
    reopened_header = reopened.sections[0].properties.get_header()
    reopened_footer = reopened.sections[0].properties.get_footer()
    assert reopened_header is not None
    assert reopened_footer is not None
    assert reopened_header.text == "OO학교  -  "
    assert reopened_header.element.find(f".//{HP}ctrl/{HP}pageNum") is not None
    assert reopened_footer.element.find(f".//{HP}ctrl/{HP}pageNum") is not None


def test_builder_lowers_header_footer_page_numbers(tmp_path) -> None:
    from hwpx.builder import Document, Footer, Header, PageNumber, Paragraph, Run, Section

    path = tmp_path / "builder-header-footer.hwpx"
    Document(
        sections=[
            Section(
                header=Header(
                    children=[
                        Paragraph(
                            align="right",
                            children=[Run("OO학교  -  "), PageNumber()],
                        )
                    ]
                ),
                footer=Footer(
                    children=[
                        Paragraph(align="center", children=[PageNumber(format="page/total")]),
                    ]
                ),
                children=[Paragraph(text="본문")],
            )
        ]
    ).save_to_path(path)

    reopened = HwpxDocument.open(path)
    header = reopened.sections[0].properties.get_header()
    footer = reopened.sections[0].properties.get_footer()
    assert header is not None
    assert footer is not None
    assert header.text == "OO학교  -  "
    assert header.element.find(f".//{HP}ctrl/{HP}pageNum") is not None
    assert footer.element.find(f".//{HP}ctrl/{HP}pageNum") is not None
    assert "본문" in reopened.export_text()


def test_builder_save_report_hard_gates_visual_review_and_to_dict(tmp_path) -> None:
    from hwpx.builder import Document, PageBreak, Paragraph, Section, Table

    path = tmp_path / "builder-save-report.hwpx"
    report = Document(
        sections=[
            Section(
                children=[
                    Paragraph(text="보고서"),
                    PageBreak(),
                    Table(header=["구분", "내용"], rows=[["1", "점검"]]),
                ]
            )
        ]
    ).save_to_path(path)

    assert report.path == path
    assert report.validate_package.ok
    assert report.validate_document.ok
    assert isinstance(report.validate_document.warnings, tuple)
    assert report.reopened.ok
    assert report.hard_gates["package_validation"] == "pass"
    assert report.hard_gates["document_errors"] == "pass"
    assert report.hard_gates["schema_lint"] in {"pass", "warning"}
    assert report.hard_gates["reopen"] == "pass"
    assert report.hard_gates["id_integrity"] == "pass"
    assert report.visual_review_required is True
    assert report.feature_flags["table"] is True
    assert report.feature_flags["page_break"] is True

    payload = report.to_dict()
    json.dumps(payload, ensure_ascii=False)
    assert payload["visual_review_required"] is True
    assert payload["hard_gates"]["id_integrity"] == "pass"
    assert isinstance(payload["validate_document"]["warnings"], list)


def test_builder_save_report_explicit_visual_review_and_save_contract(tmp_path) -> None:
    from hwpx.builder import Document, Paragraph, Section

    builder_path = tmp_path / "builder-explicit-visual.hwpx"
    report = Document(
        sections=[Section(children=[Paragraph(text="본문")])],
        visual_review_required=True,
    ).save_to_path(builder_path)
    assert report.visual_review_required is True
    assert report.feature_flags["layout_sensitive"] is False

    document = HwpxDocument.new()
    document.add_paragraph("기존 저장 계약")
    document_path = tmp_path / "document-save-contract.hwpx"
    assert document.save_to_path(document_path) == document_path
