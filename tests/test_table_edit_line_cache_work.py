# SPDX-License-Identifier: Apache-2.0
"""A table's structure edit judges the line caches of that table, not of the whole section.

Counted, not timed (as ``test_big_table_work_bounds.py``). 7.0.0 ran the section-wide sweep of
``hp:linesegarray`` caches twice for each ``insert_rows``/``insert_columns``/``delete_rows``/
``delete_columns``/``split_cell`` and parsed the whole part again for the first of them, so one row
put into a three-cell table cost as much as the section was long: 82 -> 374 ms on a 4 MB section
against 6.12.0. The edit now reads the part only as far as the table reaches and digests the
paragraphs of the table and of the paragraphs it sits in; the save still judges every cache.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from lxml import etree

import hwpx.opc.xml_utils as xml_utils
from hwpx import HwpxDocument
from hwpx.opc.xml_utils import parse_xml
from hwpx.oxml import _line_caches as line_caches
from hwpx.table_patch import TableStructureError

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"
SMALL = "formfit_glyph_cells.hwpx"  # 24 one-cell tables, each between cached body paragraphs
LARGE = "formfit_hft_faces_cells.hwpx"  # 224 of the same


class _Work:
    """What one edit asked of the line-cache net."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.digests = 0
        self.short_reads = 0
        self.whole_parses = 0
        digest, short_read, whole = line_caches._content_digest, line_caches._content_as_read, xml_utils.parse_xml

        def counted_digest(paragraph):
            self.digests += 1
            return digest(paragraph)

        def counted_short_read(source_xml, places):
            self.short_reads += 1
            return short_read(source_xml, places)

        def counted_whole(data):
            self.whole_parses += 1
            return whole(data)

        monkeypatch.setattr(line_caches, "_content_digest", counted_digest)
        monkeypatch.setattr(line_caches, "_content_as_read", counted_short_read)
        monkeypatch.setattr(xml_utils, "parse_xml", counted_whole)

    def taken(self) -> tuple[int, int, int]:
        seen = (self.digests, self.short_reads, self.whole_parses)
        self.digests = self.short_reads = self.whole_parses = 0
        return seen


def _section_caches(doc: HwpxDocument) -> int:
    return sum(len(line_caches.cache_elements(section.element)) for section in doc.sections)


def _same_length_edit(paragraph) -> str:
    """Change *paragraph*'s first text in the tree, cache left on: same length, other characters, so
    that only the comparison with the part as read can tell."""

    node = next(t for t in paragraph.iter(f"{HP}t") if t.text and len(t) == 0)
    node.text = ("X" if node.text[0] != "X" else "Y") + node.text[1:]
    return node.text


def _body_paragraphs_with_a_cache(doc: HwpxDocument) -> list:
    return [
        paragraph
        for paragraph in doc.sections[0].element.findall(f"{HP}p")
        if paragraph.find(f"{HP}linesegarray") is not None
        and paragraph.find(f"{HP}run/{HP}t") is not None
        and (paragraph.find(f"{HP}run/{HP}t").text or "")
        and next(paragraph.iter(f"{HP}tbl"), None) is None
    ]


def test_a_row_insert_digests_the_table_however_long_the_section_is(monkeypatch: pytest.MonkeyPatch) -> None:
    work = _Work(monkeypatch)
    seen = {}
    for name in (SMALL, LARGE):
        doc = HwpxDocument.open(FIXTURES / name)
        caches = _section_caches(doc)
        work.taken()
        doc.tables[0].insert_rows(0)
        seen[name] = (*work.taken(), caches)

    small, large = seen[SMALL], seen[LARGE]
    assert large[3] > 5 * small[3] > 100  # the long section holds several times the caches
    assert small[:3] == large[:3]  # and the edit asked the same of both
    digests, short_reads, whole_parses = large[:3]
    assert 0 < digests <= 6  # the table's one cell paragraph and the paragraph holding the table
    assert (short_reads, whole_parses) == (1, 0)  # the part read as far as the table, never parsed whole


def test_a_second_edit_of_the_table_reads_nothing_of_the_part(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = HwpxDocument.open(FIXTURES / LARGE)
    table = doc.tables[0]
    table.insert_rows(0)
    work = _Work(monkeypatch)

    table.insert_rows(0)
    table.insert_columns(0)

    digests, short_reads, whole_parses = work.taken()
    assert (short_reads, whole_parses) == (0, 0)
    assert digests <= 12


def test_another_table_parses_the_part_once_and_no_edit_or_save_after_it_does(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = HwpxDocument.open(FIXTURES / LARGE)
    section_bytes = len(doc.sections[0]._tracked_caches._source_xml)
    whole = xml_utils.parse_xml
    parsed: list[int] = []
    monkeypatch.setattr(xml_utils, "parse_xml", lambda data: parsed.append(len(data)) or whole(data))

    doc.tables[0].insert_rows(0)
    assert section_bytes not in parsed  # the first table: a short read
    doc.tables[5].insert_rows(0)
    assert parsed.count(section_bytes) == 1  # the second: everything that is left, once
    doc.tables[9].insert_rows(0)
    doc.tables[9].split_cell(0, 0, cols=2)
    doc.to_bytes()
    assert parsed.count(section_bytes) == 1
    assert doc.sections[0]._tracked_caches._source_xml is None  # the bytes are let go


@pytest.mark.parametrize("mark_dirty", [True, False])
def test_a_paragraph_outside_the_table_edited_directly_loses_its_cache_at_the_save(mark_dirty: bool) -> None:
    # The structure edit no longer looks at the rest of the section; the save does, as it did.
    doc = HwpxDocument.open(FIXTURES / SMALL)
    edited_paragraph, kept_paragraph = _body_paragraphs_with_a_cache(doc)[1:3]
    edited = _same_length_edit(edited_paragraph)
    kept = kept_paragraph.find(f"{HP}run/{HP}t").text
    if mark_dirty:
        doc.sections[0].mark_dirty()

    doc.tables[0].insert_rows(0)
    doc.tables[3].insert_columns(0)

    again = HwpxDocument.open(doc.to_bytes())
    by_text = {
        (paragraph.find(f"{HP}run/{HP}t").text or ""): paragraph
        for paragraph in again.sections[0].element.findall(f"{HP}p")
        if paragraph.find(f"{HP}run/{HP}t") is not None
    }
    assert by_text[edited].find(f"{HP}linesegarray") is None
    assert by_text[kept].find(f"{HP}linesegarray") is not None


def test_a_refused_edit_still_judges_the_whole_section() -> None:
    # 7.0.0 judged the section before it knew the edit would be refused; a refusal still does (it is
    # rare, so it may cost what the section holds): the stale cache goes and the section is saved.
    doc = HwpxDocument.open(FIXTURES / SMALL)
    edited = _same_length_edit(_body_paragraphs_with_a_cache(doc)[1])
    assert not doc.sections[0].dirty

    with pytest.raises(TableStructureError):
        doc.tables[0].insert_rows(10_000)

    again = HwpxDocument.open(doc.to_bytes())
    holders = [
        paragraph
        for paragraph in again.sections[0].element.findall(f"{HP}p")
        if (found := paragraph.find(f"{HP}run/{HP}t")) is not None and found.text == edited
    ]
    assert holders and all(paragraph.find(f"{HP}linesegarray") is None for paragraph in holders)


def test_the_caches_of_a_table_nobody_touched_stay_through_another_tables_edit() -> None:
    doc = HwpxDocument.open(FIXTURES / SMALL)
    before = _section_caches(doc)
    in_table = len(line_caches.cache_elements(doc.tables[0].element))

    doc.tables[0].delete_rows(0) if doc.tables[0].row_count > 1 else doc.tables[0].insert_rows(0)

    again = HwpxDocument.open(doc.to_bytes())
    # the table's host paragraph loses its line (it held the table as it was); nothing else does
    assert _section_caches(again) >= before - in_table - 1
    assert len(line_caches.cache_elements(again.tables[1].element)) == len(line_caches.cache_elements(doc.tables[1].element))


@pytest.mark.parametrize("name", [SMALL, "line_cache_table_cells.hwpx", "merge_3x3_a1c2.hwpx"])
def test_the_short_read_answers_what_the_whole_parse_answers(name: str) -> None:
    with zipfile.ZipFile(FIXTURES / name) as archive:
        source = archive.read("Contents/section0.xml")
    originals = line_caches.cache_elements(parse_xml(source))
    expected = {
        place: (line_caches._content_digest(cache.getparent()), etree.tostring(cache, with_tail=False))
        for place, cache in enumerate(originals)
    }
    assert expected
    last = len(expected) - 1

    assert line_caches._content_as_read(source, set(expected)) == expected
    for places in ({0}, {last}, {0, last}, {last // 2}):
        assert line_caches._content_as_read(source, places) == {place: expected[place] for place in places}
    assert line_caches._content_as_read(source, {last + 1}) is None  # the part has no such cache


def test_bytes_that_do_not_line_up_with_the_caches_judge_nothing() -> None:
    # As before the change: without the part as read, no cache is dropped.
    doc = HwpxDocument.open(FIXTURES / SMALL)
    section = doc.sections[0]
    with zipfile.ZipFile(FIXTURES / "merge_3x3_a1c2.hwpx") as archive:
        other = archive.read("Contents/section0.xml")
    caches = line_caches.cache_elements(section.element)
    section._tracked_caches = line_caches.TrackedCaches(caches, other)
    _same_length_edit(_body_paragraphs_with_a_cache(doc)[1])
    section.mark_dirty()

    assert section._remove_outlived_layout_caches() == 0
    assert section._remove_outlived_layout_caches(force=True, within=doc.tables[0].element) == 0
    assert line_caches.cache_elements(section.element) == caches


def test_a_new_documents_table_reads_no_part(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(2, 2)
    work = _Work(monkeypatch)

    table.insert_rows(0)

    assert work.taken()[1:] == (0, 0)
