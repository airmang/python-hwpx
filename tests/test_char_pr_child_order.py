# SPDX-License-Identifier: Apache-2.0
"""``hh:charPr`` children follow the OWPML schema order.

``CharShapeType`` is a sequence -- fontRef, ratio, spacing, relSz, offset,
italic, bold, underline, strikeout, outline, shadow, emboss, engrave,
supscript, subscript -- and Hancom writes it in that order. ``ensure_run``
used to append bold, italic and underline after outline and shadow.
"""
from __future__ import annotations

import io
import zipfile

import pytest
from lxml import etree

from hwpx import HwpxDocument

ORDER = (
    "fontRef", "ratio", "spacing", "relSz", "offset", "italic", "bold", "underline",
    "strikeout", "outline", "shadow", "emboss", "engrave", "supscript", "subscript",
)
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"


def _saved_char_pr_children(doc: HwpxDocument, char_pr_id: str) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(doc.to_bytes())) as archive:
        header = etree.fromstring(archive.read("Contents/header.xml"))
    (char_pr,) = [node for node in header.iter(f"{HH}charPr") if node.get("id") == str(char_pr_id)]
    return [etree.QName(child).localname for child in char_pr]


def _in_schema_order(names: list[str]) -> bool:
    ranks = [ORDER.index(name) for name in names]
    return ranks == sorted(ranks)


@pytest.mark.parametrize(
    "style",
    [
        {"bold": True},
        {"italic": True, "underline": True},
        {"bold": True, "italic": True, "underline": True, "strike": True},
        {"underline": True, "script": "sub"},
        {"bold": True, "shadow": "#808080", "outline": "SOLID", "emboss": True, "script": "sup"},
    ],
)
def test_ensure_run_writes_char_pr_children_in_schema_order(style: dict) -> None:
    doc = HwpxDocument.new()
    char_pr_id = doc.styles.ensure_run(**style)
    names = _saved_char_pr_children(doc, char_pr_id)
    assert _in_schema_order(names), names


def test_italic_comes_before_bold() -> None:
    doc = HwpxDocument.new()
    names = _saved_char_pr_children(doc, doc.styles.ensure_run(bold=True, italic=True))
    assert names.index("italic") < names.index("bold")


def test_the_same_style_still_resolves_to_the_same_char_pr() -> None:
    doc = HwpxDocument.new()
    first = doc.styles.ensure_run(bold=True, underline=True)
    assert doc.styles.ensure_run(bold=True, underline=True) == first
