# SPDX-License-Identifier: Apache-2.0
"""덧말(``hp:dutmal``)과 글자 겹치기(``hp:compose``)를 읽고, 고치고, 지운다.

``doc.shapes.rubies`` / ``doc.shapes.composed_characters`` read the whole document (cells,
headers, notes, master pages), ``paragraph.rubies`` / ``paragraph.composed_characters`` one
paragraph. The views are live: assigning writes the element, clears the line layout cache of
the paragraph (and of the paragraph holding its table) and marks the part dirty. Each edit is
checked on Hangul-saved documents, saved, reopened and validated; other parts keep their bytes.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxError
from hwpx.objects import Alignment, ComposedCharacter, Ruby

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures"
RUBY_TEXT = FIXTURES / "hancom_saved" / "pages_ruby_text.hwpx"
RUBY_IN_CELL = FIXTURES / "hancom_saved" / "pages_ruby_below_in_a_cell.hwpx"
RUBY_RATIO = FIXTURES / "hancom_saved" / "pages_ruby_above_10_5pt_ratio_30.hwpx"
SIMPLE_DUTMAL = FIXTURES / "hwpxlib_corpus" / "reader_writer__SimpleDutmal.hwpx"
SIMPLE_COMPOSE = FIXTURES / "hwpxlib_corpus" / "reader_writer__SimpleCompose.hwpx"
COMPOSED = FIXTURES / "hancom_saved" / "pages_composed_characters.hwpx"
COMPOSE_IN_CELL = FIXTURES / "hancom_saved" / "pages_compose_in_a_cell.hwpx"


def _reopen(document: HwpxDocument) -> HwpxDocument:
    reopened = HwpxDocument.open(document.to_bytes())
    assert not reopened.validate().issues
    return reopened


def _parts(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _changed_parts(before: bytes, after: bytes) -> set[str]:
    old, new = _parts(before), _parts(after)
    return {name for name in old.keys() | new.keys() if old.get(name) != new.get(name)}


def _has_cache(paragraph_element) -> bool:
    return paragraph_element.find(f"{HP}linesegarray") is not None


def _holder(paragraph_element):
    node = paragraph_element.getparent()
    while node is not None and node.tag != f"{HP}tbl":
        node = node.getparent()
    while node is not None and node.tag != f"{HP}p":
        node = node.getparent()
    return node


# -- reading -------------------------------------------------------------------------------------


def test_rubies_read_text_ruby_text_position_and_alignment_from_hangul_saved_files() -> None:
    rubies = HwpxDocument.open(RUBY_TEXT).shapes.rubies
    assert rubies and all(isinstance(ruby, Ruby) for ruby in rubies)
    assert {(r.text, r.ruby_text, r.position, r.alignment, r.size_ratio) for r in rubies} == {
        ("본말", "덧말", "TOP", Alignment.CENTER, 0)
    }
    assert rubies[0].alignment == "CENTER"
    below = HwpxDocument.open(RUBY_IN_CELL).shapes.rubies
    assert [(r.position, r.size_ratio) for r in below] == [("BOTTOM", 50)] * 3
    assert {r.size_ratio for r in HwpxDocument.open(RUBY_RATIO).shapes.rubies} == {30}
    (sample,) = HwpxDocument.open(SIMPLE_DUTMAL).shapes.rubies
    assert sample.to_dict() == {
        "text": "테스트_본말", "rubyText": "테스트_닷말", "position": "TOP", "alignment": "CENTER", "sizeRatio": 0,
    }


def test_rubies_are_found_in_table_cells_and_paragraph_reads_only_its_own_runs() -> None:
    document = HwpxDocument.open(RUBY_IN_CELL)
    rubies = document.shapes.rubies
    cell_paragraph = rubies[0].paragraph
    assert _holder(cell_paragraph.element) is not None  # it sits in a cell
    assert cell_paragraph.rubies == rubies  # the three are in that one cell paragraph
    holder = document.paragraphs[[p.element for p in document.paragraphs].index(_holder(cell_paragraph.element))]
    assert holder.rubies == ()  # the cell's 덧말 are not the holding paragraph's


def test_rubies_are_read_in_document_order_from_cells_and_notes() -> None:
    document = HwpxDocument.new()
    body = document.add_paragraph("본문 ")
    document.shapes.add_dutmal("한자", "かんじ", paragraph=body)
    table = document.add_table(1, 1)
    cell_paragraph = table.cell(0, 0).paragraphs[0]
    cell_paragraph.add_dutmal("칸", "덧", pos_type="BOTTOM")
    note = document.notes.add_footnote("각주 글", paragraph=body)
    note.paragraphs[0].add_dutmal("각주", "주")
    texts = [ruby.text for ruby in document.shapes.rubies]
    assert texts == ["한자", "각주", "칸"]  # the note sits in the body paragraph, before the table's
    assert [r.position for r in document.shapes.rubies] == ["TOP", "TOP", "BOTTOM"]
    _reopen(document)


def test_composed_characters_read_frame_arrangement_size_and_slots() -> None:
    marks = HwpxDocument.open(SIMPLE_COMPOSE).shapes.composed_characters
    assert all(isinstance(mark, ComposedCharacter) for mark in marks)
    assert [(m.text, m.frame, m.arrangement, m.inner_size, m.char_pr_id_refs) for m in marks] == [
        ("12", "SHAPE_REVERSAL_TIRANGLE", "SPREAD", -3, ("7",)),
        ("AO", "CHAR", "OVERLAP", -3, ("7",)),
    ]
    framed = HwpxDocument.open(COMPOSED).shapes.composed_characters
    assert {(m.frame, m.arrangement, m.inner_size, m.char_pr_id_refs) for m in framed} == {
        ("SHAPE_CIRCLE", "SPREAD", -4, ())
    }
    assert [m.text for m in framed] == [str(n) for n in range(1, len(framed) + 1)]
    in_cell = HwpxDocument.open(COMPOSE_IN_CELL).shapes.composed_characters
    assert in_cell and {m.text for m in in_cell} == {"가나"}


def test_reading_writes_nothing() -> None:
    document = HwpxDocument.open(RUBY_IN_CELL)
    before = document.to_bytes()
    for ruby in document.shapes.rubies:
        ruby.to_dict()
    for mark in HwpxDocument.open(COMPOSE_IN_CELL).shapes.composed_characters:
        mark.to_dict()
    assert document.to_bytes() == before


# -- changing ------------------------------------------------------------------------------------


def test_editing_a_ruby_in_a_cell_clears_its_line_caches_and_touches_only_the_section() -> None:
    document = HwpxDocument.open(RUBY_IN_CELL)
    before = document.to_bytes()
    ruby = document.shapes.rubies[0]
    paragraph = ruby.paragraph.element
    holder = _holder(paragraph)
    assert _has_cache(paragraph) and _has_cache(holder)
    ruby.text = "바뀐본말"
    ruby.ruby_text = "바뀐덧말"
    assert not _has_cache(paragraph) and not _has_cache(holder)
    ruby.position = "TOP"
    ruby.alignment = Alignment.DISTRIBUTE
    ruby.alignment = "left"
    reopened = _reopen(document)
    assert reopened.shapes.rubies[0].to_dict() == {
        "text": "바뀐본말", "rubyText": "바뀐덧말", "position": "TOP", "alignment": "LEFT", "sizeRatio": 50,
    }
    assert [r.text for r in reopened.shapes.rubies[1:]] == ["본문", "본문"]
    assert _changed_parts(before, document.to_bytes()) == {"Contents/section0.xml"}


def test_writing_the_same_value_changes_nothing() -> None:
    document = HwpxDocument.open(RUBY_TEXT)
    before = document.to_bytes()
    ruby = document.shapes.rubies[0]
    ruby.text = ruby.text
    ruby.position = ruby.position
    assert document.to_bytes() == before


@pytest.mark.parametrize(
    ("attribute", "value", "code"),
    [
        ("text", "", "shape-ruby-text-value"),
        ("text", "두\n줄", "shape-ruby-text-value"),
        ("ruby_text", 3, "shape-ruby-text-value"),
        ("position", "LEFT", "shape-ruby-position-value"),
        ("alignment", "TOP", "shape-ruby-alignment-value"),
    ],
)
def test_bad_ruby_values_are_refused_before_anything_changes(attribute, value, code) -> None:
    document = HwpxDocument.open(RUBY_TEXT)
    before = document.to_bytes()
    with pytest.raises(HwpxError) as excinfo:
        setattr(document.shapes.rubies[0], attribute, value)
    assert excinfo.value.code == code and excinfo.value.suggestion
    assert document.to_bytes() == before


def test_editing_composed_characters_on_a_hangul_saved_document() -> None:
    document = HwpxDocument.open(COMPOSE_IN_CELL)
    before = document.to_bytes()
    mark = document.shapes.composed_characters[0]
    holder = _holder(mark.paragraph.element)
    mark.text = "다"
    mark.frame = "SHAPE_RECTANGLE"
    mark.arrangement = "OVERLAP"
    assert not _has_cache(mark.paragraph.element) and not _has_cache(holder)
    again = _reopen(document).shapes.composed_characters[0]
    assert (again.text, again.frame, again.arrangement, again.inner_size) == ("다", "SHAPE_RECTANGLE", "OVERLAP", 0)
    assert _changed_parts(before, document.to_bytes()) == {"Contents/section0.xml"}


@pytest.mark.parametrize(
    ("attribute", "value", "code"),
    [
        ("text", "", "shape-compose-text-value"),
        ("text", "가\t나", "shape-compose-text-value"),
        ("frame", "CIRCLE", "shape-compose-frame-value"),
        ("arrangement", "STACK", "shape-compose-arrangement-value"),
    ],
)
def test_bad_compose_values_are_refused(attribute, value, code) -> None:
    document = HwpxDocument.open(SIMPLE_COMPOSE)
    with pytest.raises(HwpxError) as excinfo:
        setattr(document.shapes.composed_characters[0], attribute, value)
    assert excinfo.value.code == code


# -- removing ------------------------------------------------------------------------------------


def test_removing_a_ruby_leaves_its_text_in_the_run() -> None:
    document = HwpxDocument.open(RUBY_TEXT)
    ruby = document.shapes.rubies[0]
    paragraph = ruby.paragraph
    run = ruby.element.getparent()
    assert "본말" not in paragraph.text
    ruby.remove()
    assert paragraph.rubies == ()
    assert "본말" in paragraph.text and "덧말" not in paragraph.text
    assert run.find(f"{HP}dutmal") is None and not _has_cache(paragraph.element)
    reopened = _reopen(document)
    assert len(reopened.shapes.rubies) == len(HwpxDocument.open(RUBY_TEXT).shapes.rubies) - 1


def test_removing_with_keep_text_false_takes_the_text_too() -> None:
    document = HwpxDocument.open(RUBY_TEXT)
    ruby = document.shapes.rubies[0]
    paragraph = ruby.paragraph
    text_before = paragraph.text
    ruby.remove(keep_text=False)
    assert paragraph.text == text_before
    mark = HwpxDocument.open(SIMPLE_COMPOSE).shapes.composed_characters[0]
    host = mark.paragraph
    mark.remove(keep_text=False)
    assert "12" not in host.text and len(host.composed_characters) == 1


def test_removing_a_composed_character_leaves_its_characters() -> None:
    document = HwpxDocument.open(COMPOSED)
    mark = document.shapes.composed_characters[0]
    paragraph = mark.paragraph
    mark.remove()
    assert paragraph.composed_characters == ()
    assert "겹친 글자 앞 글 0. 1 뒤 글." in paragraph.text
    _reopen(document)


def test_a_created_ruby_and_composed_character_read_back_and_edit() -> None:
    document = HwpxDocument.new()
    document.shapes.add_dutmal("漢字", "한자")
    document.shapes.add_composed_character("3")
    (ruby,) = document.shapes.rubies
    (mark,) = document.shapes.composed_characters
    assert (ruby.text, ruby.ruby_text, mark.text, mark.frame, mark.arrangement) == ("漢字", "한자", "3", "SHAPE_CIRCLE", "SPREAD")
    ruby.ruby_text = "かんじ"
    mark.frame = "CHAR"
    reopened = _reopen(document)
    assert reopened.shapes.rubies[0].ruby_text == "かんじ"
    assert reopened.shapes.composed_characters[0].frame == "CHAR"
    assert ruby == document.shapes.rubies[0] and hash(ruby) == hash(document.shapes.rubies[0])
