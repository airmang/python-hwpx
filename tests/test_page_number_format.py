# SPDX-License-Identifier: Apache-2.0
"""Page-number fields carry their number format on the counter itself.

Hancom draws a header/footer page number from ``hp:autoNum`` and reads its
shape from the ``hp:autoNumFormat`` child; without one it draws plain digits,
whatever ``hp:pageNum@formatType`` next to it says.
"""
from __future__ import annotations

import io
import zipfile

from hwpx.document import HwpxDocument

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HANCOM_FORMAT_ATTRS = {"userChar": "", "prefixChar": "", "suffixChar": "", "supscript": "0"}


def _auto_numbers(doc: HwpxDocument) -> set[tuple[str, tuple[tuple[str, str], ...] | None]]:
    """Distinct (numType, autoNumFormat attributes) of every counter in section 0.

    python-hwpx writes a header/footer twice (the story and its mirror), so
    the same counter shows up once per copy.
    """
    from lxml import etree

    data = doc.to_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = etree.fromstring(archive.read("Contents/section0.xml"))
    found = []
    for auto in root.iter(f"{HP}autoNum"):
        fmt = auto.find(f"{HP}autoNumFormat")
        found.append((auto.get("numType"), tuple(sorted(fmt.attrib.items())) if fmt is not None else None))
    assert found, "no page-number counter written"
    return set(found)


def _fmt(kind: str) -> tuple[tuple[str, str], ...]:
    return tuple(sorted({"type": kind, **HANCOM_FORMAT_ATTRS}.items()))


def test_page_number_counter_carries_the_requested_format() -> None:
    doc = HwpxDocument.new()
    doc.page.set_page_number(format_type="ROMAN_SMALL")
    assert _auto_numbers(doc) == {("PAGE", _fmt("ROMAN_SMALL"))}


def test_default_page_number_counter_says_digit() -> None:
    doc = HwpxDocument.new()
    doc.page.set_page_number()
    assert _auto_numbers(doc) == {("PAGE", _fmt("DIGIT"))}


def test_format_aliases_reach_the_counter() -> None:
    doc = HwpxDocument.new()
    doc.page.set_page_number(format_type="CIRCLED_DIGIT")
    assert _auto_numbers(doc) == {("PAGE", _fmt("CIRCLED_DIGIT"))}
    doc = HwpxDocument.new()
    doc.page.set_page_number(format_type="roman_lower")
    assert _auto_numbers(doc) == {("PAGE", _fmt("ROMAN_SMALL"))}


def test_page_and_total_counters_share_the_format() -> None:
    doc = HwpxDocument.new()
    doc.page.set_page_number(format="page/total", format_type="ROMAN_SMALL")
    assert _auto_numbers(doc) == {("PAGE", _fmt("ROMAN_SMALL")), ("TOTAL_PAGE", _fmt("ROMAN_SMALL"))}


def test_counter_format_survives_a_reopen() -> None:
    doc = HwpxDocument.new()
    doc.page.set_page_number(format_type="ROMAN_CAPITAL")
    reopened = HwpxDocument.open(doc.to_bytes())
    assert _auto_numbers(reopened) == {("PAGE", _fmt("ROMAN_CAPITAL"))}
