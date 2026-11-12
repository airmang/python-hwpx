"""The save gate does each piece of its work once.

The open-safety check used to open the saved document twice (once for the
document check, once as the reopen proof), and the stale-cache sweep read the
headers again for every section. Both are the same answer each time, so they
are asked once; what the gate reports does not change.
"""

from __future__ import annotations

import io
import zipfile

import pytest

import hwpx.tools.package_validator as package_validator
from hwpx import HwpxDocument
from hwpx.opc.security import HwpxSecurityError, guard_xml_depth, parse_xml_stdlib
from hwpx.opc.xml_utils import parse_xml
from hwpx.tools.package_validator import validate_editor_open_safety
from hwpx.tools.validator import validate_document


def _document_bytes() -> bytes:
    doc = HwpxDocument.new()
    doc.add_paragraph("첫 문단")
    doc.add_paragraph("둘째 문단")
    return doc.to_bytes()


def _count_opens(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    opened: list[object] = []
    original = HwpxDocument.open.__func__

    def counting(cls, source, *args, **kwargs):
        opened.append(source)
        return original(cls, source, *args, **kwargs)

    monkeypatch.setattr(HwpxDocument, "open", classmethod(counting))
    return opened


def test_the_gate_opens_the_saved_document_once(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _document_bytes()
    opened = _count_opens(monkeypatch)

    report = validate_editor_open_safety(data)

    assert report.ok
    assert report.reopen_ok
    assert report.validate_document is not None
    assert len(opened) == 1


def test_a_file_that_does_not_open_fails_both_the_reopen_and_the_document_check() -> None:
    report = validate_editor_open_safety(b"not a zip archive")

    assert not report.ok
    assert not report.reopen_ok
    assert report.reopen_error
    # The document check opens the file first, so it stops on that same error.
    assert report.document_validation_error == report.reopen_error


def test_an_open_document_is_checked_without_being_opened_again(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _document_bytes()
    from_bytes = validate_document(data)
    document = HwpxDocument.open(data)
    opened = _count_opens(monkeypatch)

    from_document = validate_document(document)

    assert opened == []
    assert from_document.validated_parts == from_bytes.validated_parts
    assert [str(issue) for issue in from_document.issues] == [str(issue) for issue in from_bytes.issues]


def test_a_save_reads_the_header_shapes_once_for_all_sections(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("첫 구역")
    doc.add_section()
    doc.add_section()
    assert len(doc.sections) == 3
    calls = {"squeezed": 0, "narrowed": 0}
    squeezed = package_validator.squeezed_paragraph_shapes
    narrowed = package_validator.narrowed_char_shapes

    def count_squeezed(root):
        calls["squeezed"] += 1
        return squeezed(root)

    def count_narrowed(root):
        calls["narrowed"] += 1
        return narrowed(root)

    monkeypatch.setattr(package_validator, "squeezed_paragraph_shapes", count_squeezed)
    monkeypatch.setattr(package_validator, "narrowed_char_shapes", count_narrowed)

    doc.oxml.serialize()

    headers = len(doc.oxml.headers)
    assert calls == {"squeezed": headers, "narrowed": headers}


def test_a_section_swept_on_its_own_still_reads_the_headers() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("문단")

    assert doc.sections[0].remove_stale_layout_caches() == 0


@pytest.mark.parametrize("parse", [parse_xml, parse_xml_stdlib], ids=["lxml", "stdlib"])
def test_the_depth_limit_is_where_it_was(parse) -> None:
    def chain(depth: int) -> bytes:
        return ("<a>" * depth + "</a>" * depth).encode()

    with pytest.raises(HwpxSecurityError, match=r"exceeds XML depth limit: 11 > 10"):
        guard_xml_depth(parse(chain(11)), max_depth=10)
    guard_xml_depth(parse(chain(10)), max_depth=10)


def test_the_depth_limit_counts_the_deepest_branch_of_a_wide_tree() -> None:
    xml = b"<r>" + b"<a/>" * 50 + b"<a><b><c><d/></c></b></a>" + b"<a/>" * 50 + b"</r>"
    root = parse_xml(xml)

    guard_xml_depth(root, max_depth=5)
    with pytest.raises(HwpxSecurityError, match=r"exceeds XML depth limit: 5 > 4"):
        guard_xml_depth(root, max_depth=4)


def test_a_comment_has_no_local_name_and_a_name_is_read_the_same_twice() -> None:
    root = parse_xml(b'<h:p xmlns:h="urn:x"><!-- note --><h:run/><plain/></h:p>')
    children = list(root)

    for _ in range(2):  # the second pass reads the remembered names
        assert package_validator._local_name(root) == "p"
        assert [package_validator._local_name(child) for child in children] == ["", "run", "plain"]


def test_a_saved_document_passes_the_gate_and_reopens() -> None:
    doc = HwpxDocument.open(_document_bytes())
    doc.add_paragraph("저장 뒤 다시 여는 문단")
    buffer = io.BytesIO()

    doc.save_to_stream(buffer)

    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as archive:
        assert archive.testzip() is None
    assert "저장 뒤 다시 여는 문단" in HwpxDocument.open(buffer.getvalue()).text.plain()
