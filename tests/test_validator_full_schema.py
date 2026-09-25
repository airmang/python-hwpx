"""``validate_document`` checks sections and headers against the full OWPML schema.

Violations that documents Hancom opens also carry are left out; the rest come back as warnings,
so ``ok`` keeps reporting hard errors only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.oxml.namespaces import HP
from hwpx.tools.validator import validate_document

FIXTURES = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"


def _owpml_warnings(report) -> list[str]:
    return [issue.message for issue in report.issues if issue.message.startswith("OWPML schema")]


@pytest.mark.parametrize(
    "name",
    ["reader_writer__SimpleTable.hwpx", "tool__textextractor__Table.hwpx", "reader_writer__SimpleRectangle.hwpx"],
)
def test_documents_hancom_wrote_have_no_full_schema_warnings(name: str) -> None:
    report = validate_document(FIXTURES / name)

    assert _owpml_warnings(report) == []


def test_a_new_document_has_no_full_schema_warnings() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("본문")
    document.add_table(2, 2).cell(0, 0).text = "칸"

    assert _owpml_warnings(validate_document(document.to_bytes())) == []


def test_a_value_outside_the_schema_is_a_warning_and_ok_stays_true() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("본문")
    page = next(document.oxml.sections[0].element.iter(f"{HP}pagePr"))
    page.set("landscape", "PORTRAIT")
    document.oxml.sections[0].mark_dirty()

    report = validate_document(document.to_bytes())

    assert report.ok
    assert "OWPML schema: paragraph:pagePr@landscape: value not allowed" in _owpml_warnings(report)
    warning = next(issue for issue in report.warnings if "pagePr@landscape" in issue.message)
    assert warning.part_name == "Contents/section0.xml" and warning.line is not None


def test_a_header_missing_required_attributes_is_reported() -> None:
    document = HwpxDocument.new()
    header = document.oxml.headers[0]
    for name in ("version", "secCnt"):
        header.element.attrib.pop(name, None)
    header.mark_dirty()

    warnings = _owpml_warnings(validate_document(document.to_bytes()))

    assert "OWPML schema: head:head: required attribute missing: 'version'" in warnings
    assert "OWPML schema: head:head: required attribute missing: 'secCnt'" in warnings


def test_a_control_with_attributes_it_does_not_take_is_reported_once_per_kind() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("본문")
    controls = list(document.oxml.sections[0].element.iter(f"{HP}ctrl"))
    for control in controls:
        control.set("id", "1")
    document.oxml.sections[0].mark_dirty()

    warnings = _owpml_warnings(validate_document(document.to_bytes()))

    matching = [message for message in warnings if "paragraph:ctrl@id: attribute not allowed" in message]
    assert len(matching) == 1
    if len(controls) > 1:
        assert matching[0].endswith(f"({len(controls)} times)")


def test_the_full_schema_check_can_be_turned_off() -> None:
    document = HwpxDocument.new()
    page = next(document.oxml.sections[0].element.iter(f"{HP}pagePr"))
    page.set("landscape", "PORTRAIT")
    document.oxml.sections[0].mark_dirty()

    assert _owpml_warnings(validate_document(document.to_bytes(), full_schema=False)) == []
