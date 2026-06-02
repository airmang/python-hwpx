from __future__ import annotations

from hwpx.document import HwpxDocument


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

