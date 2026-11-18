"""clear_content keeps the column layout (hp:colPr) of a section's first paragraph also when it shares its
hp:ctrl with a field begin (some Hancom files write that) -- exec7/rv-ranges."""
from __future__ import annotations

from hwpx import HwpxDocument

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def test_a_column_layout_sharing_its_control_with_a_field_stays() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("12")
    field = paragraph.add_form_field("B", start=0, end=2)
    columns = paragraph.element.find(f".//{_HP}colPr")
    shared = columns.getparent()
    shared.append(field.element)
    empty = [ctrl for ctrl in paragraph.element.iter(f"{_HP}ctrl") if len(ctrl) == 0][0]
    empty.getparent().remove(empty)
    again = HwpxDocument.open(document.to_bytes())
    first = again.paragraphs[0]
    first.clear_content()
    assert len(list(first.element.iter(f"{_HP}colPr"))) == 1
    saved = HwpxDocument.open(again.to_bytes())
    assert len(list(saved.paragraphs[0].element.iter(f"{_HP}colPr"))) == 1
