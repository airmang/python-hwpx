# SPDX-License-Identifier: Apache-2.0
"""Master pages: read and edit their paragraphs, unlink them from a section, then remove them."""

from __future__ import annotations

from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.model import Paragraph

FIXTURES = Path(__file__).resolve().parent / "fixtures"
HANCOM_MASTER = next((FIXTURES / "hwpxlib_corpus").glob("error__20250808__*.hwpx"))


def test_master_page_paragraphs_read_edit_and_save() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    master_id = doc.parts.add_master_page(text="바탕쪽 글", page_type="BOTH", section=0)
    (master,) = doc.parts.master_pages
    assert master.id == master_id and master.page_type == "BOTH"
    assert [p.text for p in master.paragraphs] == ["바탕쪽 글"]
    assert all(isinstance(p, Paragraph) for p in master.paragraphs)

    master.paragraphs[0].text = "고친 바탕쪽"
    added = master.add_paragraph("둘째 줄")
    added.add_table(1, 2)
    reopened = HwpxDocument.open(doc.to_bytes())
    assert reopened.validate().ok
    (again,) = reopened.parts.master_pages
    assert again.text == "고친 바탕쪽\n둘째 줄"
    assert len(again.paragraphs[1].tables) == 1


def test_unlink_then_remove_a_master_page() -> None:
    doc = HwpxDocument.new()
    master_id = doc.parts.add_master_page(text="바탕쪽", page_type="BOTH", section=0)
    with pytest.raises(HwpxValueError) as caught:
        doc.parts.remove_master_page(master_id)
    assert caught.value.code == "master-page-in-use"

    assert doc.page.remove_master_page(master_id, section=0) is True
    assert doc.page.master_page_refs(section=0) == ()
    assert doc.sections[0].properties.element.get("masterPageCnt") == "0"
    assert doc.page.remove_master_page(master_id, section=0) is False
    doc.parts.remove_master_page(master_id)
    reopened = HwpxDocument.open(doc.to_bytes())
    assert reopened.validate().ok and reopened.parts.master_pages == ()


def test_unlink_from_every_section() -> None:
    doc = HwpxDocument.new()
    doc.add_section()
    master_id = doc.parts.add_master_page(text="바탕쪽", page_type="BOTH")
    doc.page.set_master_page(master_id, section="all")
    assert all(doc.page.master_page_refs(section=i) == (master_id,) for i in range(2))
    assert doc.page.remove_master_page(master_id, section="all") is True
    assert all(doc.page.master_page_refs(section=i) == () for i in range(2))


def test_a_hangul_saved_master_page_reads_as_paragraphs() -> None:
    doc = HwpxDocument.open(HANCOM_MASTER)
    masters = doc.parts.master_pages
    assert masters
    master = masters[0]
    assert master.paragraphs and master.text == "\n".join(master.to_model().paragraph_texts)
    refs = [ref for i in range(len(doc.sections)) for ref in doc.page.master_page_refs(section=i)]
    assert master.id in refs
