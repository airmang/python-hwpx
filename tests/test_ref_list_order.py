"""A new ``hh:refList`` collection goes where the schema and Hancom's saves put it.

``doc.styles.apply_list_format(kind="bullet")`` and ``doc.styles.ensure_bullet()`` appended
``hh:bullets`` after ``hh:styles``, so the document failed the engine's own schema check
(``head:bullets: element not expected``). Hancom saves it after ``hh:numberings`` and before
``hh:paraProperties`` (every Hangul-saved fixture holding bullets), as ``owpml-header.xsd`` orders it.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.oxml.header_part import _REF_LIST_ORDER

FIXTURES = Path(__file__).parent / "fixtures"


def _order(data: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        header = archive.read("Contents/header.xml").decode("utf-8")
    ref_list = re.search(r"<hh:refList>(.*)</hh:refList>", header, re.S)
    assert ref_list is not None
    return re.findall(r"<hh:(\w+)\b[^>]*\bitemCnt=", ref_list.group(1))


def _hancom_orders() -> set[tuple[str, ...]]:
    orders = set()
    for path in sorted((FIXTURES / "hancom_saved").glob("*.hwpx")):
        data = path.read_bytes()
        if b"<hh:bullets" in zipfile.ZipFile(io.BytesIO(data)).read("Contents/header.xml"):
            orders.add(tuple(_order(data)))
    return orders


def _in_schema_order(order: list[str]) -> bool:
    known = [name for name in order if name in _REF_LIST_ORDER]
    return known == sorted(known, key=_REF_LIST_ORDER.index)


def test_hancom_saves_bullets_after_numberings() -> None:
    orders = _hancom_orders()
    assert orders
    for order in orders:
        assert _in_schema_order(list(order))
        assert order.index("bullets") == order.index("numberings") + 1


@pytest.mark.parametrize(
    "make",
    [
        lambda d: d.styles.apply_list_format(paragraph=d.add_paragraph("항목"), kind="bullet"),
        lambda d: d.styles.ensure_bullet("■"),
        lambda d: (d.notes.add_memo("메모", paragraph=d.add_paragraph("글")), d.styles.ensure_bullet("●")),
        lambda d: (d.tracking.insert(d.add_paragraph("글"), " 더함"), d.styles.ensure_bullet("●"),
                   d.styles.apply_list_format(paragraph=d.add_paragraph("번호"), kind="number")),
    ],
    ids=["apply_list_format", "ensure_bullet", "with-memo", "with-tracking-and-numbering"],
)
def test_a_new_collection_keeps_the_schema_order(make) -> None:
    doc = HwpxDocument.new()
    make(doc)
    data = doc.to_bytes()
    order = _order(data)
    assert "bullets" in order and _in_schema_order(order), order
    assert not HwpxDocument.open(data).validate().issues


def test_a_bullet_added_to_a_hancom_document_goes_where_hancom_puts_it() -> None:
    source = next(p for p in sorted((FIXTURES / "hancom_saved").glob("*.hwpx"))
                  if b"<hh:bullets" not in zipfile.ZipFile(p).read("Contents/header.xml")
                  and b"<hh:numberings" in zipfile.ZipFile(p).read("Contents/header.xml"))
    doc = HwpxDocument.open(source)
    doc.styles.ensure_bullet("■")
    order = _order(doc.to_bytes())
    assert order.index("bullets") == order.index("numberings") + 1
    assert _in_schema_order(order)
