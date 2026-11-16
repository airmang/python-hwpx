"""A master page made and never linked to a section is refused at save (``master-page-unlinked``).

Hangul 2024 drops a master page part no section's ``hp:masterPage`` points at: opened and saved again,
``masterpage0.xml`` and its text are gone (measured on documents made with ``doc.parts.add_master_page``
without ``section=``, out/metrics7 ``page-00``·``03``·``06``). The 6.x flow -- make it, then link it --
keeps working, and a master page the document was read with is left as it was read.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError

FIXTURES = Path(__file__).parent / "fixtures"


def _new() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    return doc


@pytest.mark.parametrize("how", ["to_bytes", "save"])
def test_an_unlinked_new_master_page_is_refused(how: str, tmp_path: Path) -> None:
    doc = _new()
    master_page = doc.parts.add_master_page(text="바탕쪽", page_type="BOTH")
    target = tmp_path / "out.hwpx"
    with pytest.raises(HwpxValueError) as caught:
        doc.to_bytes() if how == "to_bytes" else doc.save(target)
    assert caught.value.code == "master-page-unlinked"
    assert caught.value.context["master_pages"] == [master_page.id]
    assert "set_master_page" in caught.value.suggestion
    assert not target.exists()


def _linked_parts(data: bytes) -> tuple[list[str], str]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = [n for n in archive.namelist() if "masterpage" in n.lower()]
        section = archive.read("Contents/section0.xml").decode("utf-8")
    return names, section


def test_linking_after_making_it_saves_as_before() -> None:
    doc = _new()
    master_page = doc.parts.add_master_page(text="바탕쪽", page_type="BOTH")
    doc.page.set_master_page(master_page, section=0)  # the 6.x flow: make, then link
    names, section = _linked_parts(doc.to_bytes())
    assert names == ["Contents/masterpage0.xml"]
    assert f'idRef="{master_page.id}"' in section and 'masterPageCnt="1"' in section


def test_making_it_linked_saves() -> None:
    doc = _new()
    doc.parts.add_master_page(text="바탕쪽", page_type="BOTH", section=0)
    names, _section = _linked_parts(doc.to_bytes())
    assert names == ["Contents/masterpage0.xml"]


def test_removing_the_unlinked_one_saves() -> None:
    doc = _new()
    master_page = doc.parts.add_master_page(text="바탕쪽")
    doc.parts.remove_master_page(master_page)
    names, _section = _linked_parts(doc.to_bytes())
    assert names == []


def test_unlinking_a_new_one_before_saving_is_refused() -> None:
    doc = _new()
    master_page = doc.parts.add_master_page(text="바탕쪽", page_type="BOTH", section=0)
    doc.page.remove_master_page_reference(master_page, section=0)
    with pytest.raises(HwpxValueError) as caught:
        doc.to_bytes()
    assert caught.value.code == "master-page-unlinked"


def test_a_master_page_the_document_was_read_with_is_left_alone() -> None:
    doc = _new()
    doc.parts.add_master_page(text="바탕쪽", page_type="BOTH", section=0)
    saved = doc.to_bytes()
    again = HwpxDocument.open(saved)
    [master_page] = again.parts.master_pages
    again.page.remove_master_page_reference(master_page, section=0)  # read, then unlinked by the caller
    again.to_bytes()  # not one this session made: written as the caller left it
