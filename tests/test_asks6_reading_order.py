# SPDX-License-Identifier: Apache-2.0
"""Reading content in the order the file writes it (asks6).

``run.content`` (each piece of a run: characters, glyphs, marks, controls, objects),
``paragraph.iter_objects()`` (objects inside a paragraph, at any depth),
``shape.iter_paragraphs()`` (paragraphs inside a drawing shape) and ``section.blocks``
(paragraphs and tables placed right in a section). All are reads: they leave the
document as it was, and the same file gives the same answer.

The tests read fixture files and assert structure; the text they write is their own.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxError
from hwpx.objects import Hyperlink, InlineItem, ObjectPlace, ParagraphPlace
from hwpx.oxml.namespaces import tag_local_name
from hwpx.tools.exporter import ListLabels, table_grid_text

FIXTURES = Path(__file__).parent / "fixtures"
SAVED = FIXTURES / "hancom_saved"
CORPUS = FIXTURES / "hwpxlib_corpus"

#: Hancom-saved files that between them hold every kind of piece the corpus has.
READ_FIXTURES = [
    SAVED / "pages_fixed_width_spaces.hwpx",
    SAVED / "pages_no_break_spaces.hwpx",
    SAVED / "tab_bare_right_saved.hwpx",
    SAVED / "form_field_line_break.hwpx",
    SAVED / "notes_inst_id.hwpx",
    SAVED / "pages_composed_characters.hwpx",
    SAVED / "pages_ruby_below_9pt.hwpx",
    SAVED / "line_cache_fields.hwpx",
    SAVED / "pages_title_marks_in_runs_of_other_sizes.hwpx",
    SAVED / "pages_page_number_control_then_a_table_wider_than_the_line.hwpx",
    SAVED / "pages_page_hiding_run_taller_than_the_text.hwpx",
    SAVED / "new_page_number_smallest_kept.hwpx",
    SAVED / "pages_bookmark_around_a_table_wider_than_the_line.hwpx",
    SAVED / "header_before_field_saved.hwpx",
    SAVED / "pages_index_mark_then_a_table_wider_than_the_line.hwpx",
    SAVED / "unused_chart_saved.hwpx",
    SAVED / "pages_table_cell_holding_a_header_with_a_table.hwpx",
    SAVED / "memos_in_fields.hwpx",
]


def _local(node: object) -> str:
    return tag_local_name(getattr(node, "tag", ""))


def _written(run_element: object) -> list[tuple[str, object]]:
    """What the run holds, straight from its XML: ``("text", str)`` and ``("el", element)``."""

    found: list[tuple[str, object]] = []
    for child in run_element:  # type: ignore[attr-defined]
        name = _local(child)
        if not name:
            continue
        if name == "t":
            if child.text:
                found.append(("text", child.text))
            for inner in child:
                if _local(inner):
                    found.append(("el", inner))
                if inner.tail:
                    found.append(("text", inner.tail))
        elif name == "ctrl":
            found.extend(("el", control) for control in child if _local(control))
        else:
            found.append(("el", child))
    joined: list[tuple[str, object]] = []
    for kind, value in found:
        if kind == "text" and joined and joined[-1][0] == "text":
            joined[-1] = ("text", str(joined[-1][1]) + str(value))
        else:
            joined.append((kind, value))
    return joined


@pytest.mark.parametrize("path", READ_FIXTURES, ids=lambda path: path.stem)
def test_run_content_gives_every_piece_in_file_order(path: Path) -> None:
    doc = HwpxDocument.open(path)
    runs = 0
    for place in doc.text.iter_paragraphs():
        for run in place.paragraph.runs:
            runs += 1
            items = run.content
            read = [("text", item.text) if item.element is None else ("el", item.element) for item in items]
            expected = _written(run.element)
            assert len(read) == len(expected)
            for (kind, value), (want_kind, want) in zip(read, expected):
                assert kind == want_kind
                assert value is want if kind == "el" else value == want
            assert "".join(item.text for item in items if item.container == "t") == run.text
            assert all(item.kind != "unknown" for item in items)
            for item in items:
                assert item.element is None or item.name == _local(item.element)
                assert item.element is None or dict(item.attributes) == dict(item.element.attrib)
    assert runs


@pytest.mark.parametrize(
    ("path", "kind", "char"),
    [
        (SAVED / "pages_fixed_width_spaces.hwpx", "fw_space", "　"),
        (SAVED / "pages_no_break_spaces.hwpx", "nb_space", " "),
    ],
    ids=["fw_space", "nb_space"],
)
def test_run_content_keeps_the_glyphs_to_model_drops(path: Path, kind: str, char: str) -> None:
    doc = HwpxDocument.open(path)
    runs = [run for place in doc.text.iter_paragraphs() for run in place.paragraph.runs]
    holding = [run for run in runs if any(item.kind == kind for item in run.content)]
    assert holding
    for run in holding:
        glyphs = [item for item in run.content if item.kind == kind]
        assert all(item.text == char and item.container == "t" for item in glyphs)
        assert char in run.text
        assert char not in "".join(span.text for span in run.to_model().text_spans)


def test_run_content_kinds_and_objects() -> None:
    doc = HwpxDocument.open(SAVED / "notes_inst_id.hwpx")
    items = [item for place in doc.text.iter_paragraphs() for run in place.paragraph.runs for item in run.content]
    notes = [item for item in items if item.kind in ("footnote", "endnote")]
    assert notes and all(item.container == "ctrl" and item.object.paragraphs for item in notes)
    numbers = [item for item in items if item.kind == "auto_number"]
    assert numbers and all(item.object.kind == item.attribute("numType") for item in numbers)
    settings = [item for item in items if item.kind == "column_definition"]
    assert settings and all(item.object.count >= 1 for item in settings)

    doc = HwpxDocument.open(SAVED / "pages_ruby_below_9pt.hwpx")
    rubies = [item for p in doc.paragraphs for run in p.runs for item in run.content if item.kind == "ruby"]
    assert rubies and all(item.container == "run" and item.object.ruby_text for item in rubies)


def test_run_content_of_a_link_and_a_note_made_here() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("앞")
    paragraph.add_hyperlink("https://example.com/a", "고리 글")
    paragraph.add_footnote("각주 글")
    items = [item for run in paragraph.runs for item in run.content]
    kinds = [item.kind for item in items]
    begin = kinds.index("field_begin")
    end = kinds.index("field_end")
    assert begin < end < kinds.index("footnote")
    link = items[begin]
    assert isinstance(link.object, Hyperlink) and link.object.url == "https://example.com/a"
    assert link.attribute("type") == "HYPERLINK"
    assert items[end].attribute("beginIDRef") == link.attribute("id")
    assert "".join(item.text for item in items[begin:end] if item.container == "t") == "고리 글"
    note = items[kinds.index("footnote")]
    assert [p.text for p in note.object.paragraphs] == ["각주 글"]


def test_unknown_pieces_come_with_their_name_and_text() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("가나")
    run = next(run for run in paragraph.runs if run.text == "가나")
    text = next(child for child in run.element if _local(child) == "t")
    namespace = text.tag.rsplit("}", 1)[0] + "}"
    inside = text.makeelement(f"{namespace}futureMark", {"x": "1"})
    inside.text = "다"
    inside.tail = "라"
    text.append(inside)
    run.element.append(run.element.makeelement(f"{namespace}futureObject", {}))
    items = run.content
    assert [(item.kind, item.name, item.container, item.text) for item in items] == [
        ("text", "", "t", "가나"),
        ("unknown", "futureMark", "t", "다"),
        ("text", "", "t", "라"),
        ("unknown", "futureObject", "run", ""),
    ]
    assert items[1].attribute("x") == "1" and items[1].attribute("y") is None
    assert "".join(item.text for item in items if item.container == "t") == run.text


def test_inline_items_are_frozen_values_and_the_same_file_reads_the_same() -> None:
    path = SAVED / "notes_inst_id.hwpx"

    def read() -> list[tuple[InlineItem, ...]]:
        doc = HwpxDocument.open(path)
        return [run.content for place in doc.text.iter_paragraphs() for run in place.paragraph.runs]

    first, second = read(), read()
    assert first == second
    item = first[0][0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.kind = "x"  # type: ignore[misc]
    assert isinstance(item.attributes, tuple) and hash(item) == hash(second[0][0])
    assert item.to_dict()["kind"] == item.kind


#: Files with objects in cells, text boxes, groups, captions, notes and headers.
OBJECT_FIXTURES = [
    SAVED / "pages_table_cell_holding_a_header_with_a_table.hwpx",
    SAVED / "notes_inst_id.hwpx",
    SAVED / "unused_chart_saved.hwpx",
    CORPUS / "reader_writer__SimpleContainer.hwpx",
    CORPUS / "reader_writer__SimpleRectangle.hwpx",
    CORPUS / "reader_writer__SimpleTable.hwpx",
    CORPUS / "reader_writer__SimplePicture.hwpx",
]


def _object_rows(places: object) -> list[tuple[object, ...]]:
    return [(p.object.element, p.kind, p.where, p.depth, p.row, p.col) for p in places]  # type: ignore[attr-defined]


@pytest.mark.parametrize("path", [p for p in OBJECT_FIXTURES if p.exists()], ids=lambda path: path.stem)
def test_paragraph_iter_objects_is_the_document_walk_narrowed(path: Path) -> None:
    doc = HwpxDocument.open(path)
    whole = _object_rows(doc.text.iter_objects())
    mine: list[tuple[object, ...]] = []
    for part in [*doc.sections, *doc.oxml.master_pages]:
        for paragraph in part.paragraphs:
            places = list(paragraph.iter_objects())
            assert all(isinstance(place, ObjectPlace) for place in places)
            mine.extend(_object_rows(places))
    assert len(mine) == len(whole)
    for got, want in zip(mine, whole):
        assert got[0] is want[0] and got[1:] == want[1:]


def test_paragraph_iter_objects_reaches_into_cells_where_pictures_does_not() -> None:
    doc = HwpxDocument.new()
    host = doc.add_paragraph("")
    table = host.add_table(1, 2)
    table.cell(0, 0).paragraphs[0].add_equation("x+1")
    assert host.equations == ()
    found = list(host.iter_objects(kinds="equation"))
    assert [place.where for place in found] == ["cell"]
    assert found[0].table == table and (found[0].row, found[0].col) == (0, 0)
    assert list(host.iter_objects(kinds="equation", where="body")) == []
    with pytest.raises(HwpxError) as caught:
        host.iter_objects(kinds="photo")
    assert caught.value.code == "text-place-invalid"


@pytest.mark.parametrize("path", [p for p in OBJECT_FIXTURES if p.exists()], ids=lambda path: path.stem)
def test_shape_iter_paragraphs_gives_the_paragraphs_inside_the_shape(path: Path) -> None:
    doc = HwpxDocument.open(path)
    places = list(doc.text.iter_paragraphs())
    for shape_place in doc.text.iter_objects(kinds="shape"):
        shape = shape_place.object
        inner = list(shape.iter_paragraphs())
        assert all(isinstance(place, ParagraphPlace) for place in inner)

        def inside(element: object, shape_element: object = shape.element) -> bool:
            node = element.getparent()  # type: ignore[attr-defined]
            while node is not None and node is not shape_element:
                node = node.getparent()
            return node is not None

        want = [p for p in places if inside(p.paragraph.element)]
        assert [p.paragraph.element for p in inner] == [p.paragraph.element for p in want]
        assert [(p.where, p.depth, p.row, p.col) for p in inner] == [(p.where, p.depth, p.row, p.col) for p in want]


def test_shape_iter_paragraphs_of_a_text_box_made_here() -> None:
    doc = HwpxDocument.new()
    shape = doc.add_paragraph("").add_rectangle(width=8000, height=4000)
    shape.set_draw_text("상자 글")
    inner = list(shape.iter_paragraphs())
    assert [(p.where, p.paragraph.text, p.depth) for p in inner] == [("text_box", "상자 글", 1)]
    assert inner[0].owner == shape
    assert list(shape.iter_paragraphs(where="cell")) == []


def test_section_blocks_keep_tables_placed_right_in_the_section() -> None:
    path = FIXTURES / "reader_robustness" / "irb_form_filled.hwpx"
    doc = HwpxDocument.open(path)
    section = doc.sections[0]
    before = etree.tostring(section.element)
    blocks = section.blocks
    written = [_local(child) for child in section.element if _local(child) in ("p", "tbl")]
    assert ["tbl" if getattr(block, "paragraph", 1) is None else "p" for block in blocks] == written
    assert "tbl" in written
    tables = [block for block in blocks if getattr(block, "paragraph", 1) is None]
    for table in tables:
        assert table_grid_text(table) == table_grid_text(table.element)
        assert table.caption is None or isinstance(table.caption.text, str)
    # This file (another program's) does not pass the save gate, so the section's XML is compared.
    assert etree.tostring(section.element) == before


def test_section_blocks_of_a_hancom_file_are_its_paragraphs() -> None:
    doc = HwpxDocument.open(SAVED / "notes_inst_id.hwpx")
    for section in doc.sections:
        assert section.blocks == section.paragraphs


@pytest.mark.parametrize("path", READ_FIXTURES[:6] + [p for p in OBJECT_FIXTURES if p.exists()], ids=lambda p: p.stem)
def test_reading_leaves_the_document_as_it_was(path: Path) -> None:
    doc = HwpxDocument.open(path)
    before = doc.to_bytes()
    for place in doc.text.iter_paragraphs():
        for run in place.paragraph.runs:
            for item in run.content:
                item.to_dict()
        for object_place in place.paragraph.iter_objects():
            if hasattr(object_place.object, "iter_paragraphs"):
                list(object_place.object.iter_paragraphs())
    assert all(section.blocks for section in doc.sections)
    assert doc.to_bytes() == before


def test_list_labels_take_the_paragraph_object() -> None:
    # Candidate 5 is already public: ListLabels takes a paragraph object as well as its element.
    doc = HwpxDocument.open(SAVED / "list_number_level1.hwpx")
    labels = ListLabels(doc)
    for paragraph in doc.paragraphs:
        assert labels.label(paragraph) == labels.label(paragraph.element)
        assert labels.kind(paragraph) == labels.kind(paragraph.element)
    assert any(labels.label(paragraph) for paragraph in doc.paragraphs)
