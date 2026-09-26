"""markdown(rich=True) keeps the text of a paragraph that holds shapes, and every shape paragraph."""

from __future__ import annotations

from lxml import etree

from hwpx.document import HwpxDocument
from hwpx.tools import markdown_export

_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"


def _text_box(*texts: str) -> str:
    paragraphs = "".join(
        f'<hp:p id="0" paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>{text}</hp:t></hp:run></hp:p>'
        for text in texts
    )
    return (
        '<hp:rect id="1" zOrder="0"><hp:drawText lastWidth="1000" name="" editable="0">'
        f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="TOP">{paragraphs}</hp:subList>'
        "</hp:drawText></hp:rect>"
    )


def _paragraph(own: str, *boxes: str) -> etree._Element:
    return etree.fromstring(
        f'<hp:p xmlns:hp="{_HP}" id="0" paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0">'
        f"<hp:t>{own}</hp:t>{''.join(boxes)}</hp:run></hp:p>"
    )


def _doc_with(paragraph: etree._Element) -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.sections[0].element.append(paragraph)
    return doc


def test_a_paragraph_keeps_its_own_text_beside_its_text_boxes() -> None:
    doc = _doc_with(_paragraph("body text", _text_box("first box", "second box"), _text_box("other box")))

    md = doc.text.markdown(rich=True)

    assert md.split("\n\n") == ["body text", "first box", "second box", "other box"]


def test_text_that_repeats_the_text_box_is_written_once() -> None:
    doc = _doc_with(_paragraph("same words", _text_box("same words")))

    assert doc.text.markdown(rich=True) == "same words"


def test_shape_paragraphs_do_not_depend_on_object_ids(monkeypatch) -> None:
    # lxml proxies are freed between loops, so id() values repeat; a repeat must
    # not make a new shape paragraph look already written
    monkeypatch.setattr(markdown_export, "id", lambda _obj: 1, raising=False)
    doc = _doc_with(_paragraph("", _text_box("first box"), _text_box("second box")))

    md = doc.text.markdown(rich=True)

    assert "first box" in md and "second box" in md


def test_text_boxes_in_a_cell_do_not_depend_on_object_ids(monkeypatch) -> None:
    monkeypatch.setattr(markdown_export, "id", lambda _obj: 1, raising=False)
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    cell_paragraph = table.cell(0, 0).paragraphs[0].element
    run = etree.fromstring(
        f'<hp:run xmlns:hp="{_HP}" charPrIDRef="0">{_text_box("first box")}{_text_box("second box")}</hp:run>'
    )
    cell_paragraph.append(run)

    md = doc.text.markdown(rich=True)

    assert "first box" in md and "second box" in md
