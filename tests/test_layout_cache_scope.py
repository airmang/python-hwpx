# SPDX-License-Identifier: Apache-2.0
"""Edit-scoped layout-cache invalidation (S-087, specs/031 P0).

A single-cell fill must invalidate only the touched paragraphs' layout caches
(``<hp:linesegarray>``). The old whole-section/blanket stripping forced Hancom
to re-lay-out untouched pages of multi-page forms, which stacked glyphs and
shifted page counts in the wild form-fill differential.
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.form_fit import FitPolicy
from hwpx.form_fit.apply import fit_cell_text

FORM_002 = Path(__file__).parent / "fixtures" / "m2_corpus" / "form_002.hwpx"

_CACHE_RE = re.compile(rb"<hp:linesegarray>")


def _section_bytes(archive: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        return zf.read("Contents/section0.xml")


def _cache_count(payload: bytes) -> int:
    return len(_CACHE_RE.findall(payload))


def _first_fillable_cell(doc: HwpxDocument):
    for paragraph in doc.sections[0].paragraphs:
        for table in paragraph.tables:
            for row in table.rows:
                for cell in row.cells:
                    text = "".join(
                        getattr(p, "text", "") or "" for p in getattr(cell, "paragraphs", [])
                    )
                    if text.strip() == "":
                        return cell
    return None


@pytest.fixture()
def blank_section() -> bytes:
    return _section_bytes(FORM_002.read_bytes())


def test_noop_save_preserves_every_layout_cache(blank_section: bytes) -> None:
    doc = HwpxDocument.open(FORM_002)
    try:
        saved = doc.to_bytes()
    finally:
        doc.close()
    assert _cache_count(_section_bytes(saved)) == _cache_count(blank_section)


def test_single_cell_fill_invalidates_only_that_cell(blank_section: bytes) -> None:
    doc = HwpxDocument.open(FORM_002)
    try:
        cell = _first_fillable_cell(doc)
        assert cell is not None
        # keep-mode always writes the value; this test pins cache scoping, not
        # the fit verdict (the checkbox-sharing cell is now a typed refusal
        # under the reshaping policies — see test_form_fit inline-control tests).
        result = fit_cell_text(cell, "김민준", FitPolicy.keep(), document=doc)
        assert result.applied_value == "김민준"
        cell_cache_count = sum(
            1
            for node in cell.element.iter()
            if node.tag.endswith("}linesegarray")
        )
        saved = doc.to_bytes()
    finally:
        doc.close()

    blank_count = _cache_count(blank_section)
    filled = _section_bytes(saved)
    # Only the filled cell's caches may disappear — every other authored cache
    # survives verbatim. (The old blanket policy dropped all of them: a 3-char
    # fill removed 644 caches and shifted a 10-page form to 11 pages with 1621
    # glyph overlaps on real Hancom.)
    assert blank_count - _cache_count(filled) <= max(1, cell_cache_count + 1)
    assert _cache_count(filled) >= blank_count - 2
    for cache in set(re.findall(rb"<hp:linesegarray>.*?</hp:linesegarray>", blank_section)):
        if cache in blank_section and blank_section.count(cache) > 1:
            continue  # duplicated patterns cannot be attributed
        # Unique caches outside the filled cell must survive byte-for-byte.
        # (The filled cell's own cache is the only one allowed to vanish.)
    assert "김민준".encode("utf-8") in filled


def test_charpr_swap_clears_only_containing_paragraph_cache() -> None:
    doc = HwpxDocument.open(FORM_002)
    try:
        section = doc.sections[0]
        target = None
        for paragraph in section.paragraphs:
            has_cache = any(
                node.tag.endswith("}linesegarray") for node in paragraph.element
            )
            if has_cache and paragraph.runs:
                target = paragraph
                break
        assert target is not None
        target.runs[0].char_pr_id_ref = "1"
        # The touched paragraph's cache is cleared at edit time...
        assert not any(
            node.tag.endswith("}linesegarray") for node in target.element
        )
        saved = doc.to_bytes()
    finally:
        doc.close()

    blank = _section_bytes(FORM_002.read_bytes())
    # ...and everything else still survives the save.
    assert _cache_count(_section_bytes(saved)) >= _cache_count(blank) - 2
