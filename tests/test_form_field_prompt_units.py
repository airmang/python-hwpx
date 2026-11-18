"""A new form field writes its prompt's length in UTF-16 units (a character outside the BMP is two), the rule
its prompt and memo setters read and write -- so changing the prompt later changes Command too."""
from __future__ import annotations

from hwpx import HwpxDocument

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _command(field) -> str:
    return next(p.text for p in field.element.iter(f"{_HP}stringParam") if p.get("name") == "Command")


def test_a_prompt_outside_the_bmp_is_counted_in_utf16_units_and_can_be_changed() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("abc")
    paragraph.add_form_field("F", start=1, end=2, prompt="\U0001F600x")
    field = HwpxDocument.open(document.to_bytes()).fields.all[0]
    assert "Direction:wstring:3:\U0001F600x " in _command(field)
    field.prompt = "Q"
    assert "Direction:wstring:1:Q " in _command(field)
    assert field.prompt == "Q"
