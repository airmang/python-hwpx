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


def test_a_field_wrapped_around_text_is_written_as_filled_and_an_empty_one_is_not() -> None:
    # Hancom saves a click-here field that holds text with dirty="1": a document written with "0" comes
    # back "1" after Hancom saves it again (made-up documents, Hancom Office 2024).
    document = HwpxDocument.new()
    wrapped = document.add_paragraph("abc").add_form_field("F", start=1, end=2, prompt="p")
    empty_range = document.add_paragraph("abc").add_form_field("G", start=1, end=1, prompt="p")
    appended = document.add_paragraph("abc").add_form_field("H", prompt="p")
    assert wrapped.element.get("dirty") == "1"
    assert empty_range.element.get("dirty") == "0"
    assert appended.element.get("dirty") == "0"
    by_name = {field.name: field for field in HwpxDocument.open(document.to_bytes()).fields.all}
    assert by_name["F"].filled is True
    assert by_name["G"].filled is False
    assert by_name["H"].filled is False
