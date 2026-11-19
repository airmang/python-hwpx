"""A click-here field's 안내문 (``prompt``) or memo holding a tab or a line break is refused the same way when the
field is made and when it is changed (``field-text-control-unsupported``), before anything is written. Hancom-saved
click-here fields hold no such prompt. Before, making the field dropped a tab without a word while changing the
prompt afterwards kept it."""
from __future__ import annotations

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError

_TEXTS = ["a\tb", "a\nb", "a\rb", "\t"]


@pytest.mark.parametrize("argument", ["prompt", "memo"])
@pytest.mark.parametrize("text", _TEXTS)
def test_making_a_field_with_a_tab_or_line_break_is_refused(text: str, argument: str) -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("12")
    before = document.to_bytes()
    with pytest.raises(HwpxValueError) as refused:
        paragraph.add_form_field("F", start=1, end=1, **{argument: text})
    assert refused.value.code == "field-text-control-unsupported"
    assert refused.value.context["argument"] == argument
    assert document.to_bytes() == before


@pytest.mark.parametrize("argument", ["prompt", "memo"])
@pytest.mark.parametrize("text", _TEXTS)
def test_changing_a_field_to_a_tab_or_line_break_is_refused(text: str, argument: str) -> None:
    document = HwpxDocument.new()
    field = document.add_paragraph("12").add_form_field("F", prompt="ab", memo="m", start=1, end=1)
    before = document.to_bytes()
    with pytest.raises(HwpxValueError) as refused:
        setattr(field, argument, text)
    assert refused.value.code == "field-text-control-unsupported"
    assert document.to_bytes() == before


def test_a_prompt_without_them_is_written_the_same_either_way() -> None:
    made = HwpxDocument.new()
    made.add_paragraph("12").add_form_field("F", prompt="a b", start=1, end=1)
    changed = HwpxDocument.new()
    field = changed.add_paragraph("12").add_form_field("F", prompt="xyz", start=1, end=1)
    field.prompt = "a b"
    first, second = (HwpxDocument.open(d.to_bytes()) for d in (made, changed))
    assert first.fields.all[0].prompt == second.fields.all[0].prompt == "a b"
    assert first.paragraphs[0].text == second.paragraphs[0].text
