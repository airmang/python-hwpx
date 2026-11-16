# SPDX-License-Identifier: Apache-2.0
"""Public line-cache policy.

``section.clear_layout_cache()`` / ``doc.oxml.clear_layout_cache()`` empty the caches
(``hp:linesegarray``) of a section or the whole document, ``stale_only=True`` only
the ones that cannot match their paragraph. The contract tested last: the public
editing calls remove the cache of the paragraph they change (and of the paragraph
holding its table) and leave every other cache alone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest

from hwpx import HwpxDocument

FIXTURES = Path(__file__).resolve().parent / "fixtures"
HANCOM = FIXTURES / "hancom_saved" / "pages_controls_after_a_wide_table.hwpx"


def _caches(doc: HwpxDocument) -> int:
    return sum(
        1
        for section in doc.sections
        for node in section.element.iter()
        if str(node.tag).endswith("}linesegarray")
    )


def _has_cache(paragraph: Any) -> bool:
    return any(str(child.tag).endswith("}linesegarray") for child in paragraph.element)


def test_section_and_document_clear_every_cache() -> None:
    doc = HwpxDocument.open(HANCOM)
    in_first = sum(1 for node in doc.sections[0].element.iter() if str(node.tag).endswith("}linesegarray"))
    assert in_first > 0
    assert doc.sections[0].clear_layout_cache() == in_first
    rest = _caches(doc)
    assert doc.oxml.clear_layout_cache() == rest
    assert _caches(doc) == 0
    reopened = HwpxDocument.open(doc.to_bytes())
    assert reopened.validate().ok and _caches(reopened) == 0


def test_the_document_count_is_the_number_removed() -> None:
    doc = HwpxDocument.open(HANCOM)
    before = _caches(doc)
    assert doc.oxml.clear_layout_cache() == before
    assert doc.oxml.clear_layout_cache() == 0


def test_stale_only_keeps_the_caches_of_an_untouched_hangul_file() -> None:
    doc = HwpxDocument.open(HANCOM)
    before = _caches(doc)
    assert doc.oxml.clear_layout_cache(stale_only=True) == 0
    assert _caches(doc) == before


def test_stale_only_removes_a_cache_left_on_changed_text() -> None:
    doc = HwpxDocument.open(HANCOM)
    paragraph = next(p for p in doc.paragraphs if p.text and _has_cache(p))
    # change the text behind the engine's back, as code editing the XML would
    text = paragraph.element.find(".//{*}t")
    assert text is not None
    text.text = (text.text or "") + "글자를 많이 더해서 캐시의 줄 수가 모자라게 한다 " * 20
    doc.sections[0].mark_dirty()
    assert doc.sections[0].clear_layout_cache(stale_only=True) >= 1
    assert not _has_cache(paragraph)


EDITS: dict[str, Callable[[HwpxDocument, Any], None]] = {
    "paragraph.text": lambda doc, p: setattr(p, "text", "바꾼 글"),
    "paragraph.add_run": lambda doc, p: p.add_run(" 덧붙인 글"),
    "text.replace": lambda doc, p: doc.text.replace(p.text[:2], "바꿈", limit=1),
    "text.apply_changes": lambda doc, p: doc.text.apply_changes(
        {next(b.id for b in doc.text.iter_blocks() if b.paragraph.element is p.element): "새 글"}
    ),
}


@pytest.mark.parametrize("name", sorted(EDITS))
def test_public_edits_clear_only_the_cache_of_what_they_change(name: str) -> None:
    doc = HwpxDocument.open(HANCOM)
    candidates = [p for p in doc.paragraphs if len(p.text) >= 2 and _has_cache(p)]
    assert len(candidates) >= 2
    target, other = candidates[0], candidates[-1]
    before = _caches(doc)
    EDITS[name](doc, target)
    assert not _has_cache(target)
    assert _has_cache(other)
    assert _caches(doc) < before


def test_editing_a_cell_clears_the_cell_and_the_paragraph_holding_the_table() -> None:
    doc = HwpxDocument.open(HANCOM)
    holder = next(p for p in doc.paragraphs if p.tables and _has_cache(p))
    cell = holder.tables[0].cell(0, 0)
    cell.text = "칸을 고침"
    assert not _has_cache(holder)
    assert not any(_has_cache(p) for p in cell.paragraphs)
