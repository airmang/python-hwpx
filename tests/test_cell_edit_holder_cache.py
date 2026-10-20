# SPDX-License-Identifier: Apache-2.0
"""Editing a table cell drops the layout cache of the paragraph holding the table.

The line of the paragraph holding a table is as tall as the table (``hp:lineseg@vertsize``), and
the table grows or shrinks with its cells' lines. So a cell edit that drops the cell paragraph's
cache drops the holding paragraph's cache too, and so on outwards through tables in cells. An
object's caption counts like a cell: the holding line holds the caption as well.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from lxml import etree

from hwpx.document import HwpxDocument

HANCOM_SAVED = Path(__file__).parent / "fixtures" / "hancom_saved"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
LONG = "칸에 넣는 긴 글이 여러 줄로 접혀 칸이 커지고 표도 함께 커지는지 보는 문장입니다. " * 3


def _cached(paragraph) -> bool:
    return paragraph.find(f"{HP}linesegarray") is not None


def _own_text(paragraph) -> str:
    return "".join(t.text or "" for run in paragraph.findall(f"{HP}run") for t in run.findall(f"{HP}t"))


def _saved_paragraphs(doc: HwpxDocument) -> list:
    with zipfile.ZipFile(io.BytesIO(doc.to_bytes())) as archive:
        return list(etree.fromstring(archive.read("Contents/section0.xml")).iter(f"{HP}p"))


def _holders(paragraphs) -> list:
    return [p for p in paragraphs if p.find(f"{HP}run/{HP}tbl") is not None]


def _plain(paragraphs) -> list:
    return [p for p in paragraphs if p.find(f"{HP}run/{HP}tbl") is None]


def test_filling_a_cell_drops_the_cache_of_the_paragraph_holding_the_table() -> None:
    doc = HwpxDocument.open(HANCOM_SAVED / "auto_grow_cell_saved.hwpx")
    table = doc.tables[0]
    table.cell(0, 0).text = LONG

    saved = _saved_paragraphs(doc)
    assert [_cached(p) for p in _holders(saved)] == [False]
    # the cell itself is laid out again, every paragraph outside the table keeps its cache
    assert [(_own_text(p), _cached(p)) for p in _plain(saved)] == [
        ("", True), ("표 앞", True), (LONG, False), ("표 뒤", True)]


def test_formatting_a_cell_paragraph_drops_the_cache_of_the_paragraph_holding_the_table() -> None:
    doc = HwpxDocument.open(HANCOM_SAVED / "auto_grow_cell_saved.hwpx")
    cell_paragraph = doc.tables[0].cell(0, 0).paragraphs[0]
    doc.styles.apply_paragraph_format(paragraphs=[cell_paragraph], line_spacing_percent=200)

    saved = _saved_paragraphs(doc)
    assert [_cached(p) for p in _holders(saved)] == [False]
    assert [_cached(p) for p in _plain(saved)] == [True, True, False, True]


def test_replacing_text_in_a_cell_drops_the_cache_of_the_paragraph_holding_the_table() -> None:
    doc = HwpxDocument.open(HANCOM_SAVED / "auto_grow_cell_saved.hwpx")
    assert doc.text.replace("짧은 값", LONG, everywhere=True) == 1

    saved = _saved_paragraphs(doc)
    assert [_cached(p) for p in _holders(saved)] == [False]
    assert [_cached(p) for p in _plain(saved)] == [True, True, False, True]


def test_editing_a_cell_of_a_table_in_a_cell_drops_both_holding_paragraphs_caches() -> None:
    doc = HwpxDocument.open(HANCOM_SAVED / "pages_table_cell_holding_a_table_then_a_space.hwpx")
    inner = doc.tables[0].cell(0, 0).paragraphs[0].tables[0]
    inner.cell(1, 0).text = LONG

    saved = _saved_paragraphs(doc)
    assert [_cached(p) for p in _holders(saved)] == [False, False]
    assert [(_own_text(p), _cached(p)) for p in _plain(saved) if not _cached(p)] == [(LONG, False)]


def test_replacing_a_caption_drops_the_cache_of_the_paragraph_holding_the_table() -> None:
    doc = HwpxDocument.open(HANCOM_SAVED / "caption_gap_wrapped.hwpx")
    assert doc.text.replace("캡션 글", LONG, everywhere=True) == 1

    saved = _saved_paragraphs(doc)
    assert [_cached(p) for p in _holders(saved)] == [False]
    assert [_own_text(p) for p in _plain(saved) if not _cached(p)] == [f"표 1. {LONG}"]


def test_editing_a_paragraph_outside_the_table_keeps_the_table_caches() -> None:
    doc = HwpxDocument.open(HANCOM_SAVED / "auto_grow_cell_saved.hwpx")
    assert doc.text.replace("표 뒤", LONG, everywhere=True) == 1

    saved = _saved_paragraphs(doc)
    assert [_cached(p) for p in _holders(saved)] == [True]
    assert [_cached(p) for p in _plain(saved)] == [True, True, True, False]
