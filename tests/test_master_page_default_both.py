"""A master page added without a page type goes on every page (``BOTH``)."""

from __future__ import annotations

import io
import re
import zipfile

from hwpx.document import HwpxDocument


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
