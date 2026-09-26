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


HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def append_to(tag: str, xml: str) -> Change:
    def change(root: etree._Element) -> None:
        for element in _named(root, tag):
            element.append(etree.fromstring(xml))
    return change


def rewrite_hrefs(prefix: str, rewrite: Callable[[str], str]) -> Change:
    def change(root: etree._Element) -> None:
        for element in _named(root, "item"):
            href = element.get("href", "")
            if href.startswith(prefix):
                element.set("href", rewrite(href))
    return change


_BOOLEAN_SET = (
    f'<hp:parameterset xmlns:hp="{HP[1:-1]}" cnt="1" name="539"><hp:listParam cnt="1" name="537">'
    '<hp:booleanParam name="16400">1</hp:booleanParam></hp:listParam></hp:parameterset>'
)


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
    ("parameterset-boolean", SECTION, append_to("secPr", _BOOLEAN_SET), "hp:booleanParam inside hp:parameterset"),
    ("masterPage-without-part", SECTION, append_to("secPr", f'<hp:masterPage xmlns:hp="{HP[1:-1]}" idRef="masterpage9"/>'),
     "a master page the package does not have"),
    ("href-from-manifest-folder", "Contents/content.hpf", rewrite_hrefs("Contents/", lambda href: href[len("Contents/"):]),
     "reads hrefs from the package root"),
    ("href-leading-slash", "Contents/content.hpf", rewrite_hrefs("Contents/", lambda href: "/" + href),
     "reads hrefs from the package root"),
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


def test_a_boolean_field_parameter_is_fine(valid_bytes: bytes) -> None:
    # Fields keep boolean parameters in hp:parameters, and Hancom opens them.
    boolean = f'<hp:booleanParam xmlns:hp="{HP[1:-1]}" name="Flag">1</hp:booleanParam>'
    report = validate_package(_mutate(valid_bytes, SECTION, append_to("parameters", boolean)))
    assert not any("booleanParam" in issue.message for issue in report.errors)


def test_a_master_page_the_package_has_is_fine() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("바탕쪽을 쓰는 문서")
    doc.page.set_master_page(doc.parts.add_master_page(text="바탕쪽"))
    report = validate_package(doc.to_bytes())
    assert not any("master page" in issue.message for issue in report.errors), [i.message for i in report.errors]


def test_a_picture_href_from_the_manifest_folder_is_a_warning(valid_bytes: bytes) -> None:
    # Hancom opens the document but leaves the picture out.
    changed = _mutate(valid_bytes, "Contents/content.hpf", rewrite_hrefs("BinData/", lambda href: "../" + href))
    report = validate_package(changed)
    assert report.ok
    assert any("leaves the picture out" in issue.message for issue in report.warnings)


def test_a_manifest_outside_contents_with_hrefs_from_the_root_is_fine() -> None:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(HwpxDocument.new().to_bytes())) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            name = "Alt/content.hpf" if info.filename == "Contents/content.hpf" else info.filename
            if name == "META-INF/container.xml":
                payload = payload.replace(b"Contents/content.hpf", b"Alt/content.hpf")
            method = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
            target.writestr(name, payload, compress_type=method)

    report = validate_package(out.getvalue())

    assert not any("package root" in issue.message for issue in report.issues), [i.message for i in report.issues]


def _drop_footer_paragraphs(under: str) -> Change:
    def change(root: etree._Element) -> None:
        for holder in _named(root, under):
            for story in _named(holder, "footer"):
                for sublist in _named(story, "subList"):
                    story.remove(sublist)
    return change


def _footer_bytes() -> bytes:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    doc.page.set_footer(text="꼬리말")
    return doc.to_bytes()


def test_a_control_footer_without_paragraphs_is_an_error() -> None:
    report = validate_package(_mutate(_footer_bytes(), SECTION, _drop_footer_paragraphs("ctrl")))
    assert any("hp:footer without hp:subList" in issue.message for issue in report.errors)


def test_an_empty_footer_copy_under_section_properties_is_fine() -> None:
    # Hancom reads the control copy only.
    report = validate_package(_mutate(_footer_bytes(), SECTION, _drop_footer_paragraphs("secPr")))
    assert not any("without hp:subList" in issue.message for issue in report.errors)


def _drop_cell_paragraphs(root: etree._Element) -> None:
    for sublist in _named(root, "subList"):
        if sublist.getparent() is not None and etree.QName(sublist.getparent()).localname == "tc":
            for paragraph in _named(sublist, "p"):
                if paragraph.getparent() is sublist:
                    sublist.remove(paragraph)
            return


def test_a_cell_without_paragraphs_is_an_error(valid_bytes: bytes) -> None:
    report = validate_package(_mutate(valid_bytes, SECTION, _drop_cell_paragraphs))
    assert any("hp:subList without hp:p" in issue.message for issue in report.errors)
