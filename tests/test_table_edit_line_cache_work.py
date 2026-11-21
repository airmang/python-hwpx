# SPDX-License-Identifier: Apache-2.0
"""What a table's structure edit spends on judging the section's line caches, counted (not timed).

As ``test_big_table_work_bounds.py``. 7.0.0 judged every ``hp:linesegarray`` of the section twice for
each ``insert_rows``/``insert_columns``/``delete_rows``/``delete_columns``/``split_cell``, with a digest
of each cached paragraph each time (a paragraph holding a table serialised once for itself and once more
for every cell paragraph in it), and digested every paragraph of the part as read at the first of them.
The judgement still looks at every cache of the section each time -- what it leaves is held to 7.0.0's
in ``test_table_edit_judges_every_line_cache.py`` -- but a body paragraph whose bytes did not change is
serialised once and not digested paragraph by paragraph, and the judgement after the rebuild looks at
the rebuilt table's block alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import hwpx.opc.xml_utils as xml_utils
from hwpx import HwpxDocument
from hwpx.oxml import _line_caches as line_caches

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"
SMALL = "formfit_glyph_cells.hwpx"  # 24 one-cell tables, each between cached body paragraphs
LARGE = "formfit_hft_faces_cells.hwpx"  # 224 of the same


class _Work:
    """What the line-cache judgements asked for since the last ``taken()``."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, section_bytes: int) -> None:
        self.digests = self.blocks = self.parses = 0
        digest, whole, parse = line_caches._content_digest, line_caches._whole_bytes, xml_utils.parse_xml

        def counted_digest(paragraph):
            self.digests += 1
            return digest(paragraph)

        def counted_whole(block):
            self.blocks += 1
            return whole(block)

        def counted_parse(data):
            self.parses += len(data) == section_bytes  # the section's part, not another
            return parse(data)

        monkeypatch.setattr(line_caches, "_content_digest", counted_digest)
        monkeypatch.setattr(line_caches, "_whole_bytes", counted_whole)
        monkeypatch.setattr(xml_utils, "parse_xml", counted_parse)

    def taken(self) -> tuple[int, int, int]:
        seen = (self.digests, self.blocks, self.parses)
        self.digests = self.blocks = self.parses = 0
        return seen


def _opened(name: str, monkeypatch: pytest.MonkeyPatch) -> tuple[HwpxDocument, _Work, int, int]:
    """The document, the counter, and how many caches and cached body paragraphs its section has."""

    doc = HwpxDocument.open(FIXTURES / name)
    tracker = doc.sections[0]._tracked_caches
    assert tracker is not None and tracker._source_xml is not None
    work = _Work(monkeypatch, len(tracker._source_xml))
    root = doc.sections[0].element
    caches = len(line_caches.cache_elements(root))
    blocks = sum(1 for block in root if line_caches.cache_elements(block))
    return doc, work, caches, blocks


def test_a_first_edit_digests_its_tables_block_however_long_the_section_is(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = {}
    for name in (SMALL, LARGE):
        with monkeypatch.context() as patch:
            doc, work, caches, blocks = _opened(name, patch)
            doc.tables[0].insert_rows(0)
            seen[name] = (*work.taken(), caches, blocks)

    (small_digests, _, small_parses, small_caches, _), (digests, serialised, parses, caches, blocks) = seen[SMALL], seen[LARGE]
    assert caches > 5 * small_caches > 100  # the long section holds several times the caches
    assert digests == small_digests <= 6  # the cell paragraph and the paragraph holding the table
    assert parses == small_parses == 1  # the part as read, once (7.0.0 parsed it once too)
    # each block once as it is and once as it was read, and the rebuilt one once more
    assert serialised <= 2 * blocks + 1
    assert digests < caches / 50  # 7.0.0: three digests of every cached paragraph here


def test_a_later_edit_serialises_each_block_once_and_parses_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    doc, work, caches, blocks = _opened(LARGE, monkeypatch)
    table = doc.tables[0]
    table.insert_rows(0)
    work.taken()

    table.insert_rows(0)
    again = work.taken()
    doc.tables[7].insert_columns(0)  # another table, in a block nothing changed since it was read
    other = work.taken()

    for digests, serialised, parses in (again, other):
        assert parses == 0
        assert serialised <= blocks + 1  # one look at the section, and the rebuilt block once more
        assert digests <= 6  # 7.0.0: two digests of every cached paragraph
    assert caches > 400


def test_the_save_after_an_edit_judges_without_digests_or_a_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    doc, work, _caches, blocks = _opened(LARGE, monkeypatch)
    doc.tables[0].insert_rows(0)
    work.taken()

    doc.sections[0]._remove_outlived_layout_caches()  # the judgement a save starts with

    assert work.taken() == (0, blocks, 0)


def test_a_block_changed_since_it_was_read_costs_one_more_parse_and_no_later_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc, work, caches, _blocks = _opened(LARGE, monkeypatch)
    doc.tables[0].insert_rows(0)  # the first judgement: every other block stays as read
    work.taken()
    tracker = doc.sections[0]._tracked_caches
    assert tracker is not None and tracker._source_xml is not None

    edited = next(  # a body paragraph changed in the tree, its cache left on
        paragraph
        for paragraph in doc.sections[0].element.findall(f"{HP}p")[3:]
        if paragraph.find(f"{HP}linesegarray") is not None and (paragraph.findtext(f"{HP}run/{HP}t") or "")
    )
    node = edited.find(f"{HP}run/{HP}t")
    node.text = ("X" if node.text[0] != "X" else "Y") + node.text[1:]
    doc.tables[9].insert_rows(0)

    digests, _serialised, parses = work.taken()
    assert edited.find(f"{HP}linesegarray") is None
    assert parses == 1  # what the part held for the changed block; with it, for all that were left
    assert digests <= caches + 12  # each of those once, as 7.0.0 digested them at its first judgement
    assert tracker._source_xml is None  # the part's bytes are let go
    node.text = "changed again"
    doc.tables[13].split_cell(0, 0, cols=2)
    doc.to_bytes()
    assert work.taken()[2] == 0


def test_filling_the_rows_between_edits_of_a_table_in_a_cell_never_asks_for_the_part_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A table in a cell shares its block with the outer table's other cells. The block is watched with
    # digests from the first edit on, so when an API fills cells there (which changes the block) the
    # other cells' caches are judged against those digests, not against the part as read.
    doc = HwpxDocument.open(FIXTURES / "pages_nested_table_rows_holding_tables_split.hwpx")
    tracker = doc.sections[0]._tracked_caches
    assert tracker is not None and tracker._source_xml is not None
    work = _Work(monkeypatch, len(tracker._source_xml))
    table = next(
        table for table in doc.tables.with_nested if next(table.element.iterancestors(f"{HP}tbl"), None) is not None
    )
    outer = list(table.element.iterancestors(f"{HP}tbl"))[-1]
    assert len(line_caches.cache_elements(outer)) > len(line_caches.cache_elements(table.element)) + 2

    for row in range(3):
        table.insert_rows(row)
        table.set_cell_text(row + 1, 0, f"row {row}")
    doc.to_bytes()

    assert work.taken()[2] == 1  # the first judgement's, and no other


def test_the_caches_of_a_table_nobody_touched_stay_through_another_tables_edit() -> None:
    doc = HwpxDocument.open(FIXTURES / SMALL)
    before = len(line_caches.cache_elements(doc.sections[0].element))
    in_table = len(line_caches.cache_elements(doc.tables[0].element))

    doc.tables[0].insert_rows(0)

    # the table's holding paragraph loses its line (it held the table as it was); nothing else does
    assert len(line_caches.cache_elements(doc.sections[0].element)) == before - 1
    assert len(line_caches.cache_elements(doc.tables[0].element)) == in_table
    again = HwpxDocument.open(doc.to_bytes())
    assert len(line_caches.cache_elements(again.sections[0].element)) == before - 1
