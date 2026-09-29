"""Named text boxes are fields, as Hancom takes them: ``doc.fields.text_boxes`` and ``fill_text_box()``.

Hancom saved ``text_box_fields_before.hwpx``: a click-here field 누름, a cell 칸, the text boxes 상자
(one paragraph) and 상자2 (two paragraphs), an unnamed text box and two text boxes named 같은. Its
field list held 누름, 칸, 상자, 상자2, 같은, 같은: the named text boxes in document order, the unnamed
one left out. It then filled 상자, 상자2 and 같은 by name and saved ``text_box_fields_after.hwpx``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HANCOM_SAVED = Path(__file__).parent / "fixtures" / "hancom_saved"
BEFORE = HANCOM_SAVED / "text_box_fields_before.hwpx"
AFTER = HANCOM_SAVED / "text_box_fields_after.hwpx"
VALUES = {"상자": "새 값", "상자2": "둘째 값", "같은": "같은 값"}


def _boxes(document: HwpxDocument) -> list[tuple[str | None, list[str], list[list[str | None]]]]:
    boxes = []
    for draw_text in document.sections[0].element.iter(f"{HP}drawText"):
        paragraphs = draw_text.findall(f"{HP}subList/{HP}p")
        boxes.append((
            draw_text.get("name"),
            ["".join(t.text or "" for t in paragraph.iter(f"{HP}t")) for paragraph in paragraphs],
            [[run.get("charPrIDRef") for run in paragraph.findall(f"{HP}run")] for paragraph in paragraphs],
        ))
    return boxes


def test_named_text_boxes_are_listed_in_document_order() -> None:
    document = HwpxDocument.open(BEFORE.read_bytes())

    fields = document.fields.text_boxes

    assert [field.name for field in fields] == ["상자", "상자2", "같은", "같은"]
    assert [field.text for field in fields] == ["원래 글", "첫 줄\n둘째 줄", "같은 하나", "같은 둘"]


def test_filling_text_boxes_leaves_them_as_hancom_filled_them() -> None:
    document = HwpxDocument.open(BEFORE.read_bytes())

    for name, value in VALUES.items():
        document.fields.fill_text_box(value, name=name)

    assert _boxes(document) == _boxes(HwpxDocument.open(AFTER.read_bytes()))
    assert [field.text for field in document.fields.text_boxes] == ["새 값", "둘째 값", "같은 값", "같은 값"]


def test_an_index_fills_one_text_box_of_a_name() -> None:
    document = HwpxDocument.open(BEFORE.read_bytes())

    filled = document.fields.fill_text_box("둘째만", name="같은", index=1)

    assert [field.text for field in filled] == ["둘째만"]
    assert [field.text for field in document.fields.text_boxes if field.name == "같은"] == ["같은 하나", "둘째만"]


def test_an_unknown_text_box_name_is_refused() -> None:
    document = HwpxDocument.open(BEFORE.read_bytes())
    before = _boxes(document)

    with pytest.raises(HwpxValueError) as raised:
        document.fields.fill_text_box("값", name="없는 상자")

    assert raised.value.code == "field-text-box-not-found"
    assert _boxes(document) == before


def test_a_text_box_named_here_is_a_field() -> None:
    document = HwpxDocument.new()
    shape = document.shapes.add_rectangle(width=8000, height=3000)
    shape.set_draw_text("글", name="상자")
    document.shapes.add_rectangle(width=8000, height=3000).set_draw_text("이름 없음")

    [field] = document.fields.text_boxes
    field.text = "새 글\n둘째 줄"

    assert (field.name, field.text) == ("상자", "새 글\n둘째 줄")
    [paragraph] = field.element.findall(f"{HP}subList/{HP}p")
    assert len(paragraph.findall(f"{HP}run/{HP}t/{HP}lineBreak")) == 1
