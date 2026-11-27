# SPDX-License-Identifier: Apache-2.0
"""``control=False`` writes a header/footer page number as Hangul does: the automatic number alone.

7.x writes a page-number control (``hp:pageNum``) after the automatic number (``hp:autoNum``) by
default; Hangul puts only the automatic number in a header or footer. 8.0 is to make this the default.
"""

from __future__ import annotations

import io
import zipfile

from lxml import etree

from hwpx.document import HwpxDocument

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _section(document: HwpxDocument):
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        return etree.fromstring(archive.read("Contents/section0.xml"))


def _footer_pieces(document: HwpxDocument) -> list[tuple[str, str | None]]:
    """(local name, numType) of the page pieces of the section's first footer, in order."""

    footer = next(_section(document).iter(f"{HP}footer"))
    return [(node.tag.split("}")[1], node.get("numType"))
            for node in footer.iter(f"{HP}autoNum", f"{HP}pageNum")]


def test_the_default_still_writes_the_control() -> None:
    document = HwpxDocument.new()

    document.page.set_page_number()

    assert _footer_pieces(document) == [("autoNum", "PAGE"), ("pageNum", None)]


def test_without_the_control_only_the_automatic_number_is_written() -> None:
    document = HwpxDocument.new()

    footer = document.page.set_page_number(control=False)

    assert _footer_pieces(document) == [("autoNum", "PAGE")]
    assert footer.text == ""
    assert [number.kind for number in document.page.auto_numbers()] == ["PAGE"]
    assert document.page.page_number_controls() == ()


def test_page_over_total_without_the_control_keeps_the_number_format() -> None:
    document = HwpxDocument.new()

    document.page.set_page_number(format="page/total", format_type="ROMAN_SMALL", control=False)

    assert _footer_pieces(document) == [("autoNum", "PAGE"), ("autoNum", "TOTAL_PAGE")]
    assert {number.format_type for number in document.page.auto_numbers()} == {"ROMAN_SMALL"}


def test_prefix_and_suffix_stay_around_the_number() -> None:
    document = HwpxDocument.new()

    footer = document.page.set_page_number(prefix="- ", suffix=" -", control=False)

    assert footer.text == "-  -"
    assert _footer_pieces(document) == [("autoNum", "PAGE")]


def test_the_field_call_returns_the_automatic_number_without_the_control() -> None:
    document = HwpxDocument.new()
    footer = document.page.set_footer(text="")

    number = footer.add_page_number_field(control=False)

    assert number.element.tag == f"{HP}autoNum"
    assert number.element.get("numType") == "PAGE"


def test_set_content_takes_the_choice_per_page_number() -> None:
    document = HwpxDocument.new()
    footer = document.page.set_footer(text="")

    footer.set_content([{"children": [{"page_number": "page", "control": False}]}])

    assert _footer_pieces(document) == [("autoNum", "PAGE")]


def test_the_document_reopens_with_the_page_number() -> None:
    document = HwpxDocument.new()
    document.page.set_page_number(control=False)

    reopened = HwpxDocument.open(io.BytesIO(document.to_bytes()))

    assert [number.kind for number in reopened.page.auto_numbers()] == ["PAGE"]
    assert reopened.page.page_number_controls() == ()
