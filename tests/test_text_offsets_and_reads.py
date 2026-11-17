# SPDX-License-Identifier: Apache-2.0
"""asks10a reads: where things stand in a paragraph's text (``offset``), a run's text elements, cells written
without ``hp:subList`` and a run's ``hp:switch``.

One count for every place: ``paragraph.text``'s -- a character, a tab, a line break, a special space one;
a control or an object none, standing after character ``offset - 1`` and before character ``offset``."""

from __future__ import annotations

import io
import warnings
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.objects import SwitchChoice

FIXTURES = Path(__file__).parent / "fixtures"
HANCOM = FIXTURES / "hancom_saved"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _doc_with_marks() -> tuple[HwpxDocument, object]:
    doc = HwpxDocument.new()
    doc.add_paragraph("첫 문단")
    paragraph = doc.add_paragraph("가나\t다라")
    return doc, paragraph


def test_an_object_reads_the_offset_move_to_takes() -> None:
    doc, paragraph = _doc_with_marks()
    with doc:
        shape = paragraph.add_rectangle(width=1000, height=1000)
        assert shape.offset == len(paragraph.text) == 5
        shape.move_to(paragraph, offset=3)  # after the tab
        assert shape.offset == 3
        table = paragraph.add_table(1, 1)
        assert table.offset == 5
        places = {place.object.element: place.offset for place in doc.text.iter_objects()}
        assert places[shape.element] == 3 and places[table.element] == 5


def test_notes_fields_and_bookmarks_read_their_offset() -> None:
    doc, paragraph = _doc_with_marks()
    with doc:
        doc.notes.add_footnote("각주", paragraph=paragraph)
        bookmark = paragraph.add_bookmark("자리")
        field = paragraph.add_form_field("칸")
        assert paragraph.footnotes[-1].offset == 5
        assert bookmark.offset == 5
        assert field.offset == 5


def test_run_content_pieces_carry_their_offset() -> None:
    doc, paragraph = _doc_with_marks()
    with doc:
        paragraph.add_run("마")
        shape = paragraph.add_rectangle(width=1000, height=1000)
        shape.move_to(paragraph, offset=1)
        pieces = [piece for run in paragraph.runs for piece in run.content]
        text_pieces = [(piece.kind, piece.text, piece.offset) for piece in pieces if piece.container == "t"]
        assert ("text", "가", 0) in text_pieces and ("text", "마", 5) in text_pieces
        assert next(piece.offset for piece in pieces if piece.kind == "shape") == 1
        # every piece's offset is the place of its first character in paragraph.text
        for piece in pieces:
            if piece.text:
                assert paragraph.text[piece.offset:piece.offset + len(piece.text)] == piece.text


def test_hancom_files_read_offsets_that_match_their_text() -> None:
    # Hancom puts a note at the end of its paragraph (pages_footnotes_6): the note stands there.
    with HwpxDocument.open(HANCOM / "pages_footnotes_6.hwpx") as doc:
        for paragraph in doc.paragraphs:
            for note in paragraph.footnotes:
                assert 0 <= note.offset <= len(paragraph.text)


def test_a_run_tells_an_empty_text_element_and_plain_text() -> None:
    doc, paragraph = _doc_with_marks()
    with doc:
        run = paragraph.runs[-1]
        assert run.has_text_element and run.is_plain_text
        paragraph.add_rectangle(width=1000, height=1000)
        shape_run = paragraph.runs[-1]
        assert not shape_run.is_plain_text
        empty = doc.add_paragraph("")
        assert empty.runs[-1].has_text_element  # Hancom's empty <hp:t/>
        assert empty.runs[-1].content == ()  # which gives no piece


@pytest.fixture
def no_sublist() -> HwpxDocument:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        doc = HwpxDocument.open(FIXTURES / "reader_robustness" / "irb_form_filled.hwpx")
    yield doc
    doc.close()


def test_a_cell_without_sub_list_is_read_and_not_written(no_sublist: HwpxDocument) -> None:
    tables = [place.object for place in no_sublist.text.iter_objects(kinds="table")]
    cell = tables[0].rows[0].cells[0]  # no hp:cellAddr: the grid cannot be built, the rows can be read
    assert not cell.has_sub_list
    assert [paragraph.text for paragraph in cell.paragraphs] == [cell.text] and cell.text
    assert not cell.address_written
    with pytest.raises(HwpxValueError) as caught:
        cell.text = "새 글"
    assert caught.value.code == "table-cell-no-sublist"


def test_hancom_cells_have_their_sub_list_and_address() -> None:
    with HwpxDocument.open(HANCOM / "auto_grow_row_filled_two.hwpx") as doc:
        tables = [place.object for place in doc.text.iter_objects(kinds="table")]
        for row in tables[0].rows:
            for cell in row.cells:
                assert cell.has_sub_list and cell.address_written


def test_a_switch_in_a_run_reads_its_case_and_default() -> None:
    with HwpxDocument.open(HANCOM / "pages_chart_case_wider_than_its_default.hwpx") as doc:
        pieces = [piece for p in doc.paragraphs for run in p.runs for piece in run.content if piece.kind == "switch"]
        assert pieces
        choice = pieces[0].object
        assert isinstance(choice, SwitchChoice)
        assert choice.required_namespace == "http://www.hancom.co.kr/hwpml/2016/ooxmlchart"
        assert [obj.element.tag for obj in choice.case] == [f"{HP}chart"]
        assert [obj.element.tag for obj in choice.default] == [f"{HP}ole"]


def test_reading_these_changes_nothing() -> None:
    data = (HANCOM / "pages_chart_case_wider_than_its_default.hwpx").read_bytes()
    with HwpxDocument.open(data) as doc:
        before = [etree.tostring(section.element) for section in doc.sections]
        for paragraph in doc.paragraphs:
            for run in paragraph.runs:
                _ = (run.content, run.has_text_element, run.is_plain_text, run.text)
        for place in doc.text.iter_objects():
            _ = place.offset
        assert [etree.tostring(section.element) for section in doc.sections] == before
        assert not any(section.dirty for section in doc.sections)
    with zipfile.ZipFile(io.BytesIO(data)):
        pass
