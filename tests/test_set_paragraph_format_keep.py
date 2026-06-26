"""Task 1 (S-056 Plan 3): keep-together on HwpxDocument.set_paragraph_format.

The high-level paragraph-format API must forward keep-together to the Plan-1
engine primitive (ensure_paragraph_format(break_setting=...)), minting a new
paraPr (lossless) and leaving the guard for "no options" intact.
"""
import io
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.oxml.namespaces import HH

FIXTURE = Path(__file__).parent / "fixtures" / "glyph_overlap" / "slot_clean.hwpx"


def _reopen(document: HwpxDocument) -> HwpxDocument:
    return HwpxDocument.open(io.BytesIO(document.to_bytes()))


def _para_pr_ids(document: HwpxDocument) -> set[str]:
    header = document.oxml.headers[0]
    return {el.get("id") for el in header.element.findall(f".//{HH}paraPr")}


def test_set_paragraph_format_applies_keep_together():
    document = HwpxDocument.open(FIXTURE)
    before_ids = _para_pr_ids(document)

    result = document.set_paragraph_format(
        paragraph_index=0,
        keep_with_next=True,
        keep_lines=True,
    )
    assert result["formatted"] == 1

    para = document.sections[0].paragraphs[0]
    new_id = para.para_pr_id_ref
    # A new paraPr was minted; the existing ones are untouched (lossless).
    assert new_id not in before_ids
    assert before_ids <= _para_pr_ids(document)

    header = document.oxml.headers[0]
    break_setting = header.element.find(f".//{HH}paraPr[@id='{new_id}']/{HH}breakSetting")
    assert break_setting is not None
    assert break_setting.get("keepWithNext") == "1"
    assert break_setting.get("keepLines") == "1"

    # Lossless: survives a save/reopen round-trip.
    reopened = _reopen(document)
    rt_id = reopened.sections[0].paragraphs[0].para_pr_id_ref
    rt_break = reopened.oxml.headers[0].element.find(
        f".//{HH}paraPr[@id='{rt_id}']/{HH}breakSetting"
    )
    assert rt_break.get("keepWithNext") == "1"


def test_set_paragraph_format_page_break_before():
    document = HwpxDocument.open(FIXTURE)
    document.set_paragraph_format(paragraph_index=0, page_break_before=True)
    para = document.sections[0].paragraphs[0]
    break_setting = document.oxml.headers[0].element.find(
        f".//{HH}paraPr[@id='{para.para_pr_id_ref}']/{HH}breakSetting"
    )
    assert break_setting is not None
    assert break_setting.get("pageBreakBefore") == "1"


def test_set_paragraph_format_requires_an_option_still_fires():
    document = HwpxDocument.open(FIXTURE)
    with pytest.raises(ValueError):
        document.set_paragraph_format(paragraph_index=0)
