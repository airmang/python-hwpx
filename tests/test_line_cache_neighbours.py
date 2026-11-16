# SPDX-License-Identifier: Apache-2.0
"""Line caches around an edit (7.0 coverage check B5), on Hancom-saved documents.

The rule is ``_clear_paragraph_layout_cache``'s: a paragraph whose text or size changes loses its
``hp:linesegarray``, and so do the paragraphs holding its table cell (their line is as tall as the
table). Hancom trusts a cache's line starts and line count; a stale one makes it draw text over text.

- Filling a click-here field in a table cell dropped the field paragraph's cache only.
- A paragraph put into a table cell (``insert_after``/``insert_before``) dropped nothing.
- A paragraph put before the first paragraph of a section takes the section settings; the
  paragraph they left kept its cache though the controls (8 positions each in ``textpos``) went.
Paragraphs not touched keep their caches.
"""

from __future__ import annotations

from pathlib import Path

from hwpx import HwpxDocument
from hwpx.oxml.namespaces import HP

FIXTURES = Path(__file__).parent / "fixtures"


def _cached(element) -> bool:
    return element.find(f"{HP}linesegarray") is not None


def _holder(element):
    cell = next(node for node in element.iterancestors() if node.tag == f"{HP}tc")
    return next(node for node in cell.iterancestors() if node.tag == f"{HP}p")


def test_filling_a_field_in_a_cell_drops_the_cache_of_the_paragraph_holding_the_table() -> None:
    document = HwpxDocument.open(FIXTURES / "hancom_saved" / "form_fields_spanning_after.hwpx")
    index, field = next((i, f) for i, f in enumerate(document.fields.all)
                        if any(node.tag == f"{HP}tc" for node in f.element.iterancestors()))
    holder = _holder(field.element)
    others = [p.element for p in document.paragraphs if p.element is not holder and _cached(p.element)]
    assert _cached(holder)

    document.fields.fill("한 줄에 다 들어가지 않는 긴 값 " * 6, index=index)

    assert not _cached(holder)
    assert all(_cached(element) for element in others)  # the rest keep theirs
    HwpxDocument.open(document.to_bytes()).validate()


def test_a_paragraph_put_into_a_cell_drops_the_cache_of_the_paragraph_holding_the_table() -> None:
    document = HwpxDocument.open(
        FIXTURES / "hancom_saved" / "pages_table_caption_below_a_spare_last_row_moved_row_by_row.hwpx"
    )
    host = next(p for p in document.paragraphs if p.tables)
    cell_paragraph = host.tables[0].cell(0, 0).paragraphs[-1]
    neighbours = [p.element for p in document.paragraphs if p.element is not host.element and _cached(p.element)]
    assert _cached(host.element) and _cached(cell_paragraph.element)

    cell_paragraph.insert_after("칸에 새로 넣은 문단")

    assert not _cached(host.element)
    assert _cached(cell_paragraph.element)  # its own text did not change
    assert all(_cached(element) for element in neighbours)

    host_again = next(p for p in HwpxDocument.open(
        FIXTURES / "hancom_saved" / "pages_table_caption_below_a_spare_last_row_moved_row_by_row.hwpx"
    ).paragraphs if p.tables)
    host_again.tables[0].cell(0, 0).paragraphs[0].insert_before("앞에")
    assert not _cached(host_again.element)


def test_a_body_paragraph_put_between_two_leaves_their_caches() -> None:
    document = HwpxDocument.open(FIXTURES / "hancom_saved" / "pages_square_picture_on_paper_lines_on_both_sides.hwpx")
    before, after = document.paragraphs[3], document.paragraphs[4]
    assert _cached(before.element) and _cached(after.element)

    before.insert_after("사이에 넣은 문단")

    assert _cached(before.element) and _cached(after.element)


def test_the_paragraph_the_section_settings_leave_drops_its_cache() -> None:
    document = HwpxDocument.open(FIXTURES / "hwpxlib_corpus" / "error__20230809__test.hwpx")
    first = document.sections[0].paragraphs[0]
    second = document.sections[0].paragraphs[1]
    second_cached = _cached(second.element)
    assert _cached(first.element) and len(first.element.findall(f"{HP}linesegarray/{HP}lineseg")) == 3

    new = first.insert_before("앞에 넣은 문단")

    assert document.sections[0].paragraphs[0].element is new.element
    assert new.element.find(f".//{HP}secPr") is not None
    assert first.element.find(f".//{HP}secPr") is None
    assert not _cached(first.element)  # its line starts counted the controls that left
    assert _cached(second.element) == second_cached  # untouched
    HwpxDocument.open(document.to_bytes()).validate()
