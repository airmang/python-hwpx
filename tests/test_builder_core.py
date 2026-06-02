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
