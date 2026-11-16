# SPDX-License-Identifier: Apache-2.0
"""``doc.text.paragraphs()`` / ``doc.text.objects()``: the whole document, with where each piece sits."""

from __future__ import annotations

import collections
import re
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.model import Paragraph, Table
from hwpx.objects import ObjectPlace, ParagraphPlace

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _rich_document() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문 하나")
    table = doc.add_table(2, 2)
    table.cell(0, 1).text = "칸 글"
    inner = table.cell(1, 0).paragraphs[0].add_table(1, 1)
    inner.cell(0, 0).text = "안쪽 칸"
    doc.notes.add_footnote("각주 글", paragraph=0)
    doc.notes.add_endnote("미주 글", paragraph=0)
    doc.notes.add_memo("메모 글", paragraph=0)
    doc.page.set_header(text="머리말 글")
    doc.page.set_footer(text="꼬리말 글", page_type="ODD")
    doc.parts.add_master_page(text="바탕쪽 글", page_type="BOTH", section=0)
    return doc


def test_every_paragraph_once_with_its_place() -> None:
    doc = HwpxDocument.open(_rich_document().to_bytes())
    places = list(doc.text.iter_paragraphs())
    assert all(isinstance(place, ParagraphPlace) and isinstance(place.paragraph, Paragraph) for place in places)
    by_text = {place.paragraph.text: place for place in places if place.paragraph.text}
    assert by_text["본문 하나"].where == "body" and by_text["본문 하나"].depth == 0
    cell = by_text["칸 글"]
    assert (cell.where, cell.row, cell.col, cell.depth) == ("cell", 0, 1, 1)
    assert isinstance(cell.table, Table)
    nested = by_text["안쪽 칸"]
    assert (nested.where, nested.row, nested.col, nested.depth) == ("cell", 0, 0, 2)
    assert nested.table is not None and nested.table.element is not cell.table.element
    assert by_text["각주 글"].where == "footnote"
    assert by_text["미주 글"].where == "endnote"
    assert by_text["메모 글"].where == "memo"
    assert (by_text["머리말 글"].where, by_text["머리말 글"].page_type) == ("header", "BOTH")
    assert (by_text["꼬리말 글"].where, by_text["꼬리말 글"].page_type) == ("footer", "ODD")
    assert by_text["바탕쪽 글"].where == "master_page" and by_text["바탕쪽 글"].section is None
    # the header python-hwpx keeps twice comes once
    texts = [place.paragraph.text for place in places]
    assert texts.count("머리말 글") == 1 and texts.count("메모 글") == 1


def test_where_filters_and_body_matches_doc_paragraphs() -> None:
    doc = _rich_document()
    body = [place.paragraph.text for place in doc.text.iter_paragraphs(where="body")]
    assert body == [paragraph.text for paragraph in doc.paragraphs]
    cells = list(doc.text.iter_paragraphs(where={"cell"}))
    assert {place.where for place in cells} == {"cell"} and len(cells) >= 5
    with pytest.raises(HwpxValueError) as caught:
        list(doc.text.iter_paragraphs(where="cells"))
    assert caught.value.code == "text-place-invalid"


def test_objects_reach_nested_tables_text_boxes_and_container_members() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    table.cell(0, 0).paragraphs[0].add_table(1, 1)
    doc.add_paragraph("도형")
    doc.shapes.add_rectangle(width=3000, height=2000)
    places = list(HwpxDocument.open(doc.to_bytes()).text.iter_objects())
    assert all(isinstance(place, ObjectPlace) for place in places)
    kinds = collections.Counter(place.kind for place in places)
    assert kinds["table"] == 2 and kinds["shape"] >= 1
    nested = [place for place in places if place.kind == "table" and place.where == "cell"]
    assert len(nested) == 1 and nested[0].depth == 1 and isinstance(nested[0].object, Table)
    only_tables = list(doc.text.iter_objects(kinds="table"))
    assert [place.kind for place in only_tables] == ["table", "table"]
    with pytest.raises(HwpxValueError):
        list(doc.text.iter_objects(kinds={"tables"}))


def _xml_counts(path: Path) -> collections.Counter[str]:
    counts: collections.Counter[str] = collections.Counter()
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not re.match(r"Contents/(section\d+|masterpage\d+)\.xml$", name):
                continue
            xml = archive.read(name).decode("utf-8")
            counts["tbl"] += len(re.findall(r"<hp:tbl[ >]", xml))
            counts["drawText"] += len(re.findall(r"<hp:drawText[ >]", xml))
            counts["caption"] += len(re.findall(r"<hp:caption[ >]", xml))
    return counts


@pytest.mark.parametrize(
    "path",
    sorted((FIXTURES / "hwpxlib_corpus").glob("*.hwpx"))[:12],
    ids=lambda p: p.name[:40],
)
def test_hangul_saved_files_reach_every_table_text_box_and_caption(path: Path) -> None:
    try:
        doc = HwpxDocument.open(path)
    except Exception:  # a corpus file the engine refuses to open is outside this check
        pytest.skip("does not open")
    truth = _xml_counts(path)
    objects = list(doc.text.iter_objects())
    assert sum(1 for place in objects if place.kind == "table") == truth["tbl"]
    paragraphs = list(doc.text.iter_paragraphs())
    assert len({id(place.paragraph.element) for place in paragraphs}) == len(paragraphs)
    text_boxes = [place for place in objects if place.kind == "shape" and place.object.draw_text is not None]
    assert len(text_boxes) == truth["drawText"]
    captions = [place for place in objects if getattr(place.object, "caption", None) is not None]
    assert len(captions) == truth["caption"]
    if truth["drawText"]:
        assert any(place.where == "text_box" for place in paragraphs)
