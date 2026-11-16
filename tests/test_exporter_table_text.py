"""The plain-text exporter writes each table once and only body text."""

from __future__ import annotations

import io
from zipfile import ZipFile

from hwpx.document import HwpxDocument
from hwpx.tools.exporter import export_text

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


def test_a_nested_table_made_with_the_api_is_written_once() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(1, 2)
    table.cell(0, 0).text = "outer"
    table.cell(0, 1).add_table(1, 1).cell(0, 0).text = "inner"

    assert doc.text.plain().count("inner") == 1


def test_note_and_memo_text_stays_out_of_cell_text() -> None:
    memo = "<hp:ctrl><hp:fieldBegin id='7' type='MEMO'>" + _sub_list(_p(_t("memo body"))) + "</hp:fieldBegin></hp:ctrl>"
    memo_end = "<hp:ctrl><hp:fieldEnd beginIDRef='7'/></hp:ctrl>"
    footnote = "<hp:ctrl><hp:footNote>" + _sub_list(_p(_t("note body"))) + "</hp:footNote></hp:ctrl>"
    endnote = "<hp:ctrl><hp:endNote>" + _sub_list(_p(_t("end body"))) + "</hp:endNote></hp:ctrl>"
    cell_paragraph = _p(memo, _t("cell text"), memo_end, footnote, endnote)
    body_paragraph = _p(memo, _t("body text"), memo_end, footnote, endnote)
    payload = _payload(body_paragraph + _p(_table([_cell(cell_paragraph)])))

    assert export_text(payload) == "body text\ncell text"


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


def test_a_table_in_a_text_box_is_still_written() -> None:
    text_box = "<hp:rect><hp:drawText>" + _sub_list(_p(_table([_cell(_p(_t("boxed cell")))]))) + "</hp:drawText></hp:rect>"
    payload = _payload(_p(_t("body"), text_box))

    assert export_text(payload) == "body\nboxed cell"
