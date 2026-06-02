from __future__ import annotations

from hwpx.document import HwpxDocument

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"


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
