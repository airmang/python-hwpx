"""A part the engine writes again keeps the form it was read in: its XML declaration and its root's namespace
declarations, byte for byte; a part the engine makes gets Hangul's declaration (exec7/xmldecl)."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from hwpx import HwpxDocument
from hwpx.opc.xml_utils import HANCOM_XML_DECLARATION, keep_source_form

HANCOM = Path(__file__).resolve().parent / "fixtures" / "hancom_saved"
_SOURCE = HANCOM / "formfit_auto_spacing_letter_spacing.hwpx"


def _parts(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def _head(data: bytes, root: bytes) -> bytes:
    """Everything up to the end of the root's start tag."""

    start = data.index(b"<" + root)
    return data[: data.index(b">", start) + 1]


def test_an_edited_section_keeps_hangul_declaration_and_namespaces() -> None:
    source = _SOURCE.read_bytes()
    document = HwpxDocument.open(source)
    next(p for p in document.paragraphs if p.text.strip()).text = "고친 문단"
    before, after = _parts(source), _parts(document.to_bytes())
    assert after["Contents/section0.xml"] != before["Contents/section0.xml"]
    assert _head(after["Contents/section0.xml"], b"hs:sec") == _head(before["Contents/section0.xml"], b"hs:sec")


def test_adding_a_section_changes_content_hpf_only_by_the_new_entries() -> None:
    source = _SOURCE.read_bytes()
    document = HwpxDocument.open(source)
    document.add_section()
    before, after = _parts(source), _parts(document.to_bytes())
    added = after["Contents/content.hpf"]
    for entry in (
        b'<opf:item id="section1" href="Contents/section1.xml" media-type="application/xml"/>',
        b'<opf:itemref idref="section1" linear="yes"/>',
    ):
        assert added.count(entry) == 1
        added = added.replace(entry, b"")
    assert added == before["Contents/content.hpf"]
    assert after["Contents/section1.xml"].startswith(HANCOM_XML_DECLARATION + b"<hs:sec ")


def test_a_part_another_tool_wrote_keeps_its_own_declaration() -> None:
    source = b"<?xml version='1.0' encoding='utf-8'?>\n<a:root xmlns:a=\"urn:a\" xmlns:b=\"urn:b\" k=\"v\"><a:x/></a:root>"
    written = b"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\" ?><a:root xmlns:a=\"urn:a\" k=\"v\"><a:y/></a:root>"
    assert keep_source_form(source, written) == (
        b"<?xml version='1.0' encoding='utf-8'?>\n<a:root xmlns:a=\"urn:a\" xmlns:b=\"urn:b\" k=\"v\"><a:y/></a:root>"
    )
    assert keep_source_form(None, b"<?xml version='1.0'?>\n<r/>") == HANCOM_XML_DECLARATION + b"<r/>"
    assert keep_source_form(b"<r/>", b"<?xml version='1.0'?>\n<r><c/></r>") == b"<r><c/></r>"


def test_an_unedited_save_is_the_source_file() -> None:
    source = _SOURCE.read_bytes()
    assert HwpxDocument.open(source).to_bytes() == source
