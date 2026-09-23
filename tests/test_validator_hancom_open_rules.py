# SPDX-License-Identifier: Apache-2.0
"""A document Hancom cannot open is an editor-open-safety error.

Each case removes (or garbles) one attribute or element from an otherwise
valid python-hwpx document. Without it Hancom refuses to open the document,
crashes on it, or never finishes laying it out, so ``validate_package``
reports an error and the public save paths refuse to write it.
"""
from __future__ import annotations

import io
import zipfile
from collections.abc import Callable

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_package

SECTION = "Contents/section0.xml"
Change = Callable[[etree._Element], None]


def _png() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (40, 120, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture(scope="module")
def valid_bytes() -> bytes:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("링크 문단")
    doc.refs.add_hyperlink("https://example.com", "링크", paragraph=paragraph)
    doc.add_table(2, 2).set_cell_text(0, 0, "셀")
    doc.shapes.add_rectangle(4000, 2000)
    doc.add_picture(_png(), "png")
    return doc.to_bytes()


def _mutate(data: bytes, part: str, change: Change) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == part:
                root = etree.fromstring(payload)
                change(root)
                payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            method = zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED
            target.writestr(info, payload, compress_type=method)
    return out.getvalue()


def _named(root: etree._Element, tag: str) -> list[etree._Element]:
    return [el for el in root.iter() if isinstance(el.tag, str) and etree.QName(el).localname == tag]


def drop_attribute(tag: str, attribute: str) -> Change:
    def change(root: etree._Element) -> None:
        for element in _named(root, tag):
            element.attrib.pop(attribute, None)
    return change


def drop_element(tag: str) -> Change:
    def change(root: etree._Element) -> None:
        for element in _named(root, tag):
            parent = element.getparent()
            if parent is not None:
                parent.remove(element)
    return change


def set_attributes(tag: str, **values: str) -> Change:
    def change(root: etree._Element) -> None:
        for element in _named(root, tag):
            for attribute, value in values.items():
                element.set(attribute, value)
    return change


CASES = [
    ("rootfile-media-type", "META-INF/container.xml", drop_attribute("rootfile", "media-type"), "rootfile missing media-type"),
    ("item-media-type", "Contents/content.hpf", drop_attribute("item", "media-type"), "opf:item missing media-type"),
    ("item-id", "Contents/content.hpf", drop_attribute("item", "id"), "opf:item missing id"),
    ("itemref-idref", "Contents/content.hpf", drop_attribute("itemref", "idref"), "opf:itemref missing idref"),
    ("meta-name", "Contents/content.hpf", drop_attribute("meta", "name"), "opf:meta missing name"),
    ("head-secCnt", "Contents/header.xml", drop_attribute("head", "secCnt"), "secCnt is missing"),
    ("version-tagetApplication", "version.xml", drop_attribute("HCFVersion", "tagetApplication"), "tagetApplication"),
    ("tbl-rowCnt", SECTION, drop_attribute("tbl", "rowCnt"), "hp:tbl missing rowCnt"),
    ("tbl-colCnt", SECTION, drop_attribute("tbl", "colCnt"), "hp:tbl missing colCnt"),
    ("tbl-cells", SECTION, drop_element("tc"), "hp:tr or hp:tc"),
    ("cellAddr-rowAddr", SECTION, drop_attribute("cellAddr", "rowAddr"), "hp:cellAddr missing rowAddr"),
    ("cellSpan-colSpan", SECTION, drop_attribute("cellSpan", "colSpan"), "hp:cellSpan missing colSpan"),
    ("secPr-startNum", SECTION, drop_element("startNum"), "hp:secPr missing hp:startNum"),
    ("secPr-visibility", SECTION, drop_element("visibility"), "hp:secPr missing hp:visibility"),
    ("lineseg-textpos", SECTION, drop_attribute("lineseg", "textpos"), "hp:lineseg missing textpos"),
    ("fieldBegin-id", SECTION, drop_attribute("fieldBegin", "id"), "hp:fieldBegin missing id"),
    ("fieldEnd-beginIDRef", SECTION, drop_attribute("fieldEnd", "beginIDRef"), "hp:fieldEnd missing beginIDRef"),
    ("fieldEnd-unpaired", SECTION, set_attributes("fieldEnd", beginIDRef="999999"), "names no hp:fieldBegin"),
    ("field-type-unknown", SECTION, set_attributes("fieldBegin", type="ClickHere", fieldid="field-x"), "not a Hancom field type"),
    ("renderingInfo", SECTION, drop_element("renderingInfo"), "hp:renderingInfo matrices"),
    ("rect-corner", SECTION, drop_element("pt0"), "corner point"),
    ("pic-img", SECTION, drop_element("img"), "hp:pic missing hc:img"),
]


def test_the_unchanged_document_passes(valid_bytes: bytes) -> None:
    assert validate_package(valid_bytes).ok


@pytest.mark.parametrize(("part", "change", "expected"), [case[1:] for case in CASES], ids=[case[0] for case in CASES])
def test_a_document_hancom_cannot_open_is_an_error(
    valid_bytes: bytes, part: str, change: Change, expected: str
) -> None:
    report = validate_package(_mutate(valid_bytes, part, change))

    assert not report.ok
    assert any(expected in issue.message for issue in report.errors), [issue.message for issue in report.errors]


def test_a_known_field_type_or_a_known_field_id_is_enough(valid_bytes: bytes) -> None:
    # Hancom opens a field when either its type or its fieldid is one it knows.
    for values in ({"type": "ClickHere"}, {"fieldid": "field-x"}):
        report = validate_package(_mutate(valid_bytes, SECTION, set_attributes("fieldBegin", **values)))
        assert not any("not a Hancom field type" in issue.message for issue in report.errors)
