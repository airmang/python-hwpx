# SPDX-License-Identifier: Apache-2.0
"""List, outline, note and page number formats are the ones Hancom reads.

Hancom numbers in plain digits when a number format is one it does not know, so
``number_format="decimal"`` came out as ``1. 2. 3.``. A format outside ``hc:NumberType2`` and
the short names ``page.set_page_number`` already took is now refused, everywhere a number format
is written.
"""
from __future__ import annotations

import io
import re
import zipfile

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.oxml.numbering_kinds import NUMBER_FORMAT_ALIASES, NUMBER_FORMATS, number_format

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"


def _section_xml(document: HwpxDocument) -> str:
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        return archive.read("Contents/section0.xml").decode("utf-8")


def _list_format(document: HwpxDocument, index: int) -> str | None:
    """``numFormat`` of level 1 of the numbering the paragraph at *index* points to."""
    paragraph = document.sections[0].paragraphs[index]
    heading = document.oxml.paragraph_property(paragraph.para_pr_id_ref).heading
    assert heading is not None
    header = document.parts.headers[0].element
    numbering = next(n for n in header.iter(f"{HH}numbering") if n.get("id") == str(heading.id_ref))
    return next(h for h in numbering.iter(f"{HH}paraHead") if h.get("level") == "1").get("numFormat")


def _document_with_item() -> tuple[HwpxDocument, int]:
    document = HwpxDocument.new()
    document.add_paragraph("항목")
    return document, len(document.paragraphs) - 1


@pytest.mark.parametrize("value", ["decimal", "lower_roman", "upper-alpha", "romans", "XYZ"])
def test_a_list_format_hancom_does_not_know_is_refused(value: str) -> None:
    document, index = _document_with_item()
    with pytest.raises(HwpxValueError) as caught:
        document.styles.apply_list_format(kind="number", number_format=value, paragraph_indexes=[index])
    assert caught.value.code == "style-number-format-invalid"


@pytest.mark.parametrize(
    ("value", "written"),
    [("roman_small", "ROMAN_SMALL"), ("ROMAN_CAPITAL", "ROMAN_CAPITAL"), ("DECAGON_CIRCLE", "DECAGON_CIRCLE"),
     ("SYMBOL", "SYMBOL"), ("roman", "ROMAN_CAPITAL"), ("roman_lower", "ROMAN_SMALL"), ("alpha_lower", "LATIN_SMALL"),
     ("hangul", "HANGUL_SYLLABLE")],
)
def test_a_list_format_is_written_as_hancom_spells_it(value: str, written: str) -> None:
    document, index = _document_with_item()
    document.styles.apply_list_format(kind="number", number_format=value, paragraph_indexes=[index])
    assert _list_format(document, index) == written


def test_numbering_levels_are_checked_for_numbers_and_outlines() -> None:
    document = HwpxDocument.new()
    with pytest.raises(HwpxValueError, match="unsupported number format"):
        document.styles.ensure_numbering(kind="number", levels=[{"format": "decimal"}])
    with pytest.raises(HwpxValueError, match="unsupported number format"):
        document.styles.ensure_numbering(kind="outline", levels=[{"numFormat": "decimal"}])


def test_a_note_number_format_is_checked_and_written_as_hancom_spells_it() -> None:
    document = HwpxDocument.new()
    properties = document.sections[0].properties
    with pytest.raises(HwpxValueError, match="unsupported number format"):
        properties.set_footnote_auto_num_format(type="decimal")

    properties.set_footnote_auto_num_format(type="roman_lower")

    note = re.search(r"<hp:footNotePr>.*?</hp:footNotePr>", _section_xml(document), re.S)
    assert note is not None and '<hp:autoNumFormat type="ROMAN_SMALL"' in note.group(0)


def test_a_page_number_format_is_checked() -> None:
    document = HwpxDocument.new()
    with pytest.raises(HwpxValueError, match="unsupported number format"):
        document.page.set_page_number(format_type="decimal")


def test_a_refused_page_number_format_leaves_the_footer_as_it_was() -> None:
    document = HwpxDocument.new()
    document.page.set_footer(text="기존 꼬리말")

    with pytest.raises(HwpxValueError):
        document.page.set_page_number(format_type="decimal", prefix="- ")

    assert document.oxml.sections[0].properties.get_footer().text == "기존 꼬리말"
    section = _section_xml(document)
    assert section.count("기존 꼬리말") == 2 and ">- <" not in section


def test_every_hancom_format_and_short_name_reads_as_a_hancom_format() -> None:
    assert {number_format(value.lower()) for value in NUMBER_FORMATS} == NUMBER_FORMATS
    assert {number_format(name.lower()) for name in NUMBER_FORMAT_ALIASES} <= NUMBER_FORMATS
