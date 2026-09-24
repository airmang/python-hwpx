"""The plain-text, HTML and Markdown exporters write each table once and only body text."""

from __future__ import annotations

import io
from zipfile import ZipFile

from hwpx.document import HwpxDocument
from hwpx.tools.exporter import export_html, export_markdown, export_text

_SEC_OPEN = (
    "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
    "<hs:sec xmlns:hp='http://www.hancom.co.kr/hwpml/2011/paragraph'"
    " xmlns:hs='http://www.hancom.co.kr/hwpml/2011/section'>"
)


def _payload(body: str) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("Contents/section0.xml", _SEC_OPEN + body + "</hs:sec>")
    return buffer.getvalue()


def _p(*items: str) -> str:
    return "<hp:p><hp:run>" + "".join(items) + "</hp:run></hp:p>"


def _t(text: str) -> str:
    return f"<hp:t>{text}</hp:t>"


def _cell(*paragraphs: str) -> str:
    return "<hp:tc><hp:subList>" + "".join(paragraphs) + "</hp:subList></hp:tc>"


def _table(*rows: list[str]) -> str:
    return "<hp:tbl>" + "".join("<hp:tr>" + "".join(row) + "</hp:tr>" for row in rows) + "</hp:tbl>"


def _sub_list(*paragraphs: str) -> str:
    return "<hp:subList>" + "".join(paragraphs) + "</hp:subList>"


def test_a_nested_table_is_written_once() -> None:
    inner = _table([_cell(_p(_t("inner")))])
    payload = _payload(_p(_table([_cell(_p(_t("outer"))), _cell(_p(inner))])))

    assert export_text(payload) == "outer\tinner"
    assert export_html(payload, full_document=False).count("inner") == 1
    assert export_markdown(payload).count("inner") == 1


def test_a_nested_table_made_with_the_api_is_written_once() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(1, 2)
    table.cell(0, 0).text = "outer"
    table.cell(0, 1).add_table(1, 1).cell(0, 0).text = "inner"

    assert doc.text.plain().count("inner") == 1
    assert doc.text.markdown().count("inner") == 1
    assert doc.text.html(full_document=False).count("inner") == 1


def test_note_and_memo_text_stays_out_of_cell_text() -> None:
    memo = "<hp:ctrl><hp:fieldBegin id='7' type='MEMO'>" + _sub_list(_p(_t("memo body"))) + "</hp:fieldBegin></hp:ctrl>"
    memo_end = "<hp:ctrl><hp:fieldEnd beginIDRef='7'/></hp:ctrl>"
    footnote = "<hp:ctrl><hp:footNote>" + _sub_list(_p(_t("note body"))) + "</hp:footNote></hp:ctrl>"
    endnote = "<hp:ctrl><hp:endNote>" + _sub_list(_p(_t("end body"))) + "</hp:endNote></hp:ctrl>"
    cell_paragraph = _p(memo, _t("cell text"), memo_end, footnote, endnote)
    body_paragraph = _p(memo, _t("body text"), memo_end, footnote, endnote)
    payload = _payload(body_paragraph + _p(_table([_cell(cell_paragraph)])))

    assert export_text(payload) == "body text\ncell text"
    for exported in (export_html(payload, full_document=False), export_markdown(payload)):
        assert "memo body" not in exported
        assert "note body" not in exported
        assert "end body" not in exported


def test_notes_and_memos_made_with_the_api_stay_out_of_cell_text() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    table.cell(0, 0).text = "cell text"
    paragraph = table.cell(0, 0).paragraphs[0]
    doc.notes.add_footnote("note body", paragraph=paragraph)
    doc.notes.add_memo("memo body", anchor=paragraph)

    text = doc.text.plain()
    assert "cell text" in text
    assert "note body" not in text
    assert "memo body" not in text


def test_header_and_footer_tables_are_not_body_text() -> None:
    header = "<hp:ctrl><hp:header id='1'>" + _sub_list(_p(_table([_cell(_p(_t("header cell")))]))) + "</hp:header></hp:ctrl>"
    footer = "<hp:ctrl><hp:footer id='2'>" + _sub_list(_p(_table([_cell(_p(_t("footer cell")))]))) + "</hp:footer></hp:ctrl>"
    payload = _payload(_p(header, footer, _t("body")))

    assert export_text(payload) == "body"
    assert "header cell" not in export_html(payload, full_document=False)
    assert "footer cell" not in export_markdown(payload)


def test_a_table_in_a_text_box_is_still_written() -> None:
    text_box = "<hp:rect><hp:drawText>" + _sub_list(_p(_table([_cell(_p(_t("boxed cell")))]))) + "</hp:drawText></hp:rect>"
    payload = _payload(_p(_t("body"), text_box))

    assert export_text(payload) == "body\nboxed cell"


def test_markdown_table_cells_stay_on_one_line() -> None:
    payload = _payload(_p(_table(
        [_cell(_p(_t("head"))), _cell(_p(_t("a|b")))],
        [_cell(_p(_t("first")), _p(_t("second"))), _cell(_p(_t("x")))],
    )))

    lines = export_markdown(payload).splitlines()

    assert lines == [
        "| head | a\\|b |",
        "| --- | --- |",
        "| first<br>second | x |",
    ]
    assert export_text(payload) == "head\ta|b\nfirst\nsecond\tx"


def test_markdown_keeps_every_cell_under_a_merged_first_row() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(3, 3)
    for row in range(3):
        for col in range(3):
            table.cell(row, col).text = f"r{row}c{col}"
    doc.tables.merge_cells(table, "A1:C1")

    lines = doc.text.markdown().splitlines()[-4:]

    assert lines == [
        "| r0c0 |  |  |",
        "| --- | --- | --- |",
        "| r1c0 | r1c1 | r1c2 |",
        "| r2c0 | r2c1 | r2c2 |",
    ]


def test_markdown_places_cells_at_their_grid_address() -> None:
    def addressed(row: int, col: int, text: str, col_span: int = 1) -> str:
        return (
            "<hp:tc><hp:subList>" + _p(_t(text)) + "</hp:subList>"
            f"<hp:cellAddr colAddr='{col}' rowAddr='{row}'/>"
            f"<hp:cellSpan colSpan='{col_span}' rowSpan='1'/></hp:tc>"
        )

    payload = _payload(_p(_table(
        [addressed(0, 0, "a"), addressed(0, 1, "b"), addressed(0, 2, "c")],
        [addressed(1, 0, "wide", col_span=2), addressed(1, 2, "right")],
    )))

    assert export_markdown(payload).splitlines() == [
        "| a | b | c |",
        "| --- | --- | --- |",
        "| wide |  | right |",
    ]
