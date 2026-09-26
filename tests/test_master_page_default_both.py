"""A master page added without a page type goes on every page (``BOTH``)."""

from __future__ import annotations

import io
import re
import zipfile

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError


def _master_page_root(document: HwpxDocument) -> str:
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        xml = archive.read("Contents/masterpage0.xml").decode("utf-8")
    return re.search(r"<(?:\w+:)?masterPage\b[^>]*>", xml).group(0)


def test_the_default_page_type_is_both() -> None:
    document = HwpxDocument.new()
    master_page_id = document.parts.add_master_page(text="모든 쪽")

    assert document.parts.master_pages[0].to_model().type == "BOTH"
    assert 'type="BOTH"' in _master_page_root(document)
    assert master_page_id == "masterpage0"


def test_the_low_level_default_matches() -> None:
    document = HwpxDocument.new()
    document.oxml.add_master_page(text="모든 쪽")

    assert document.parts.master_pages[0].to_model().type == "BOTH"


def test_a_master_page_for_all_pages_has_no_page_number() -> None:
    document = HwpxDocument.new()
    document.parts.add_master_page(text="모든 쪽")

    assert 'pageNumber="0"' in _master_page_root(document)


def test_a_second_master_page_for_the_same_pages_is_refused() -> None:
    document = HwpxDocument.new()
    props = document.oxml.sections[0].properties
    props.add_master_page_reference(document.parts.add_master_page(text="모든 쪽", page_type="BOTH"))
    second = document.parts.add_master_page(text="기본 종류")

    with pytest.raises(HwpxValueError) as caught:
        props.add_master_page_reference(second)

    assert caught.value.code == "master-page-pages-taken"
    assert props.master_page_refs == ("masterpage0",)
    assert document.to_bytes(format="hwp")


def test_the_page_namespace_refuses_it_too() -> None:
    document = HwpxDocument.new()
    document.page.set_master_page(document.parts.add_master_page(text="모든 쪽"))

    with pytest.raises(HwpxValueError):
        document.page.set_master_page(document.parts.add_master_page(text="또 모든 쪽"))


def test_master_pages_for_different_pages_go_together() -> None:
    document = HwpxDocument.new()
    props = document.oxml.sections[0].properties
    for kind, number in (("BOTH", None), ("ODD", None), ("EVEN", None), ("LAST_PAGE", None),
                         ("OPTIONAL_PAGE", 2), ("OPTIONAL_PAGE", 3)):
        page_id = document.parts.add_master_page(text=kind, page_type=kind, page_number=number)
        props.add_master_page_reference(page_id)

    assert len(props.master_page_refs) == 6
    assert document.to_bytes(format="hwp")


def test_the_same_single_page_twice_is_refused() -> None:
    document = HwpxDocument.new()
    props = document.oxml.sections[0].properties
    props.add_master_page_reference(document.parts.add_master_page(text="셋째", page_type="OPTIONAL_PAGE", page_number=3))

    with pytest.raises(HwpxValueError):
        props.add_master_page_reference(
            document.parts.add_master_page(text="또 셋째", page_type="OPTIONAL_PAGE", page_number=3))


def test_a_single_page_master_page_is_still_available() -> None:
    document = HwpxDocument.new()
    document.parts.add_master_page(text="셋째 쪽", page_type="OPTIONAL_PAGE", page_number=3)

    root = _master_page_root(document)
    assert 'type="OPTIONAL_PAGE"' in root
    assert 'pageNumber="3"' in root
