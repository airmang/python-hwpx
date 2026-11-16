"""``FormField.editable`` reads ``hp:fieldBegin/@editable`` as written and, when the file leaves it out, the OWPML
schema's default for it (``true``, ``owpml-paralist.xsd``). Hancom writes the attribute on every field it saves
(703 fields in the public documents); 6.x read a missing one as ``False``."""

from __future__ import annotations

from pathlib import Path

import pytest

from hwpx import HwpxDocument

HANCOM = Path(__file__).parent / "fixtures" / "hancom_saved"


def test_a_hancom_saved_field_reads_editable_as_written() -> None:
    doc = HwpxDocument.open(HANCOM / "form_field_line_break.hwpx")
    (field,) = doc.fields.all
    assert field.element.get("editable") == "1" and field.editable is True


@pytest.mark.parametrize(("written", "expected"), [(None, True), ("1", True), ("true", True), ("0", False),
                                                    ("false", False)])
def test_editable_reads_the_attribute_and_the_schema_default_when_it_is_left_out(
    written: str | None, expected: bool
) -> None:
    source = HwpxDocument.open(HANCOM / "form_field_line_break.hwpx")
    (field,) = source.fields.all
    if written is None:
        del field.element.attrib["editable"]
    else:
        field.element.set("editable", written)
    source.sections[0].mark_dirty()
    doc = HwpxDocument.open(source.to_bytes())
    (field,) = doc.fields.all
    assert field.element.get("editable") == written
    assert field.editable is expected


def test_setting_editable_writes_hancoms_zero_or_one() -> None:
    doc = HwpxDocument.open(HANCOM / "form_field_line_break.hwpx")
    (field,) = doc.fields.all
    del field.element.attrib["editable"]
    field.editable = False
    assert field.element.get("editable") == "0" and field.editable is False
    again = HwpxDocument.open(doc.to_bytes())
    assert not again.validate().issues
    assert again.fields.all[0].editable is False
