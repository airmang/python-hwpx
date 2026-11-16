"""``doc.styles.char_property(id)`` reads the header as it is now.

A character shape added, removed or changed through the XML (``.element``) is seen by the next read,
with no cache to invalidate by hand (6.x kept the first parse until a save).
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from hwpx import HwpxDocument

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
FIXTURES = Path(__file__).parent / "fixtures"


def _char_box(doc: HwpxDocument):
    return doc.oxml.headers[0].element.find(f"{HH}refList/{HH}charProperties")


def _add_copy(doc: HwpxDocument, *, height: str) -> str:
    box = _char_box(doc)
    copy = deepcopy(box.find(f"{HH}charPr"))
    new_id = str(max(int(c.get("id")) for c in box) + 1)
    copy.set("id", new_id)
    copy.set("height", height)
    box.append(copy)
    box.set("itemCnt", str(len(box)))
    return new_id


def test_a_shape_added_through_the_xml_is_read() -> None:
    doc = HwpxDocument.new()
    assert doc.styles.char_property("0") is not None  # parsed once before the edit
    count = len(doc.styles.char_properties)

    new_id = _add_copy(doc, height="2000")

    style = doc.styles.char_property(new_id)
    assert style is not None and style.size == 20.0
    assert doc.styles.char_property(int(new_id)) == style
    assert len(doc.styles.char_properties) == count + 1


def test_a_shape_changed_in_place_reads_its_new_values() -> None:
    doc = HwpxDocument.new()
    assert doc.styles.char_property("0").size == 10.0

    _char_box(doc).find(f"{HH}charPr[@id='0']").set("height", "3000")
    assert doc.styles.char_property("0").size == 30.0
    assert doc.styles.char_properties["0"].size == 30.0


def test_a_shape_removed_through_the_xml_is_gone() -> None:
    doc = HwpxDocument.new()
    new_id = _add_copy(doc, height="1500")
    assert doc.styles.char_property(new_id) is not None

    box = _char_box(doc)
    box.remove(box.find(f"{HH}charPr[@id='{new_id}']"))
    assert doc.styles.char_property(new_id) is None


def test_runs_read_the_shape_added_through_the_xml() -> None:
    doc = HwpxDocument.new()
    run = doc.add_paragraph("").add_run("가")
    assert run.size == 10.0

    new_id = _add_copy(doc, height="2400")
    run.element.set("charPrIDRef", new_id)
    assert run.size == 24.0


def test_hancom_saved_header_reads_the_same_as_before_and_after_an_edit() -> None:
    doc = HwpxDocument.open(FIXTURES / "hancom_saved" / "memos_in_fields.hwpx")
    before = {key: style.size for key, style in doc.styles.char_properties.items()}
    assert before  # a Hancom-saved header has shapes

    new_id = _add_copy(doc, height="1300")
    after = {key: style.size for key, style in doc.styles.char_properties.items()}
    assert after[new_id] == 13.0
    assert {key: size for key, size in after.items() if key != new_id} == before
