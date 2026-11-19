"""An edit aimed at, or taken from, a paragraph, note or table no longer in the document -- one of a table,
note or text box taken out -- is refused before anything changes; before, it reported success and the
change went with the piece taken out."""
from __future__ import annotations

from typing import Any, Callable

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError

_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c63f8cfc0f01f0005000201a5f6c2d40000000049454e44ae426082"
)


def _taken_out(kind: str) -> tuple[HwpxDocument, Any, Any, Any]:
    document = HwpxDocument.new()
    live = document.add_paragraph("1234")
    if kind == "cell":
        holder = document.add_table(1, 1)
        gone = holder.cell(0, 0).paragraphs[0]
    elif kind == "note":
        holder = document.notes.add_footnote("n", paragraph=live, offset=4)
        gone = holder.body_paragraph
    else:
        holder = live.add_rectangle(1000, 1000)
        gone = holder.set_draw_text("x").paragraphs[0]
    gone.text = "ab"
    holder.remove()
    return document, live, gone, holder


_CASES: dict[str, Callable[[HwpxDocument, Any, Any], object]] = {
    "copy_range into": lambda d, live, gone: live.copy_range(1, 3, to=gone),
    "move_range into": lambda d, live, gone: live.move_range(1, 3, to=gone),
    "move_range from": lambda d, live, gone: gone.move_range(0, 1, to=live),
    "copy_range from": lambda d, live, gone: gone.copy_range(0, 1, to=live),
    "insert_text with a format": lambda d, live, gone: gone.insert_text(1, "x", bold=True),
    "add_run with a format": lambda d, live, gone: gone.add_run("y", bold=True),
    "format_range": lambda d, live, gone: gone.format_range(0, 1, bold=True),
    "alignment": lambda d, live, gone: setattr(gone, "alignment", "CENTER"),
    "run bold": lambda d, live, gone: setattr(gone.runs[0], "bold", True),
    "insert_before": lambda d, live, gone: gone.insert_before("z"),
    "insert_after": lambda d, live, gone: gone.insert_after("z"),
    "insert_after (a copy)": lambda d, live, gone: gone.insert_after(),
    "add_highlight match": lambda d, live, gone: gone.add_highlight(color="#FFFF00", match="a"),
    "add_highlight span": lambda d, live, gone: gone.add_highlight(color="#FFFF00", start=0, end=1),
    "add_table": lambda d, live, gone: gone.add_table(1, 1),
    "add_rectangle": lambda d, live, gone: gone.add_rectangle(500, 500),
    "add_equation": lambda d, live, gone: gone.add_equation("x"),
    "add_number_restart": lambda d, live, gone: gone.add_number_restart(),
    "add_page_hiding": lambda d, live, gone: gone.add_page_hiding(header=True),
    "add_footnote": lambda d, live, gone: gone.add_footnote("n"),
    "add_footnote at an offset": lambda d, live, gone: gone.add_footnote("n", offset=1),
    "add_bookmark at an offset": lambda d, live, gone: gone.add_bookmark("b", offset=1),
    "add_form_field": lambda d, live, gone: gone.add_form_field("F", start=0, end=1),
    "highlight": lambda d, live, gone: d.text.highlight(gone, start=0, end=1),
    "note.move_to": lambda d, live, gone: live.add_footnote("m", offset=1).move_to(gone),
    "note.copy_to": lambda d, live, gone: live.add_footnote("m", offset=1).copy_to(gone),
    "shape.move_to": lambda d, live, gone: live.add_rectangle(1000, 1000).move_to(gone),
    "table.copy_to": lambda d, live, gone: d.add_table(1, 1).copy_to(gone),
    "paragraph.copy_to": lambda d, live, gone: live.copy_to(gone),
    "add_picture": lambda d, live, gone: gone.add_picture(_PNG, width=100, height=100),
    "add_bookmark": lambda d, live, gone: gone.add_bookmark("b"),
    "add_hyperlink": lambda d, live, gone: gone.add_hyperlink("https://example.invalid/", "x"),
    "add_check_box": lambda d, live, gone: gone.add_check_box("c"),
    "add_connector": lambda d, live, gone: gone.add_connector(
        live.add_rectangle(1000, 1000), live.add_rectangle(1000, 1000)
    ),
}


@pytest.mark.parametrize("kind", ["cell", "note", "box"])
def test_edits_that_stay_in_the_paragraph_still_work(kind: str) -> None:
    """Its text and runs, with no shape to register: nothing is written on the document's side."""

    document, _live, gone, _holder = _taken_out(kind)
    before = document.to_bytes()
    gone.add_run("y")
    gone.add_run("w", char_pr_id_ref="0")
    gone.insert_text(0, "x")
    gone.delete_range(0, 1)
    gone.replace_range(0, 1, "q")
    gone.split_run(1)
    gone.text = "ab"
    gone.set_text_preserving_runs("zz")
    gone.runs[0].text = "z"
    gone.clear_text()
    gone.text = "z"
    assert gone.text == "z"
    assert document.to_bytes() == before


@pytest.mark.parametrize("kind", ["cell", "note", "box"])
@pytest.mark.parametrize("case", sorted(_CASES))
def test_an_edit_with_a_paragraph_taken_out_is_refused(case: str, kind: str) -> None:
    document, live, gone, _holder = _taken_out(kind)
    before = document.to_bytes()
    with pytest.raises(HwpxValueError) as refused:
        _CASES[case](document, live, gone)
    assert refused.value.code == "paragraph-not-in-document"
    assert live.text == "1234"
    # nothing reached the document (the add_footnote/add_rectangle/add_table calls above build in it first,
    # so compare what the paragraph that stayed holds, saved)
    saved = HwpxDocument.open(document.to_bytes())
    assert saved.paragraphs[0].text.startswith("1234")
    assert before  # the document saved before the edit too


def test_a_note_taken_out_is_not_moved_back() -> None:
    document = HwpxDocument.new()
    live = document.add_paragraph("12")
    note = live.add_footnote("n", offset=1)
    note.remove()
    with pytest.raises(HwpxValueError) as refused:
        note.move_to(live, offset=0)
    assert refused.value.code == "paragraph-not-in-document"


def test_rows_from_or_into_a_table_taken_out_are_refused() -> None:
    document = HwpxDocument.new()
    gone = document.add_table(2, 2)
    gone.remove()
    live = document.add_table(1, 1)
    before = document.to_bytes()
    piece = gone.element
    from lxml import etree

    piece_before = etree.tostring(piece)
    for call in (
        lambda: live.copy_rows(0, to=1, source=gone),
        lambda: gone.copy_rows(0, to=1),
        lambda: gone.move_rows(0, to=1),
        lambda: gone.insert_rows(0),
        lambda: gone.delete_rows(0),
        lambda: gone.insert_columns(0),
        lambda: gone.delete_columns(0),
        lambda: gone.merge_cells("A1:B1"),
        lambda: gone.split_cell(0, 0, rows=2),
        lambda: gone.copy_after(),
        lambda: gone.set_borders(color="#FF0000"),
        lambda: gone.set_cell_shading(0, 0, "#FF0000"),
        lambda: setattr(gone, "alignment", "CENTER"),
        lambda: gone.cell(0, 0).add_paragraph("z"),
        lambda: gone.cell(0, 0).add_table(1, 1),
    ):
        with pytest.raises(HwpxValueError) as refused:
            call()
        assert refused.value.code == "table-not-in-document"
    assert document.to_bytes() == before
    assert etree.tostring(piece) == piece_before


def test_a_table_taken_out_takes_edits_of_its_own_values() -> None:
    document = HwpxDocument.new()
    gone = document.add_table(2, 2)
    gone.remove()
    before = document.to_bytes()
    gone.cell(0, 0).text = "z"
    gone.set_cell_text(1, 1, "w")
    gone.set_width(20000)
    gone.set_row_height(0, 2000)
    gone.cell(0, 1).vertical_alignment = "TOP"
    gone.rows[0].height = 3000
    assert gone.cell(0, 0).text == "z"
    assert document.to_bytes() == before


def test_a_note_text_box_or_caption_taken_out_takes_no_new_paragraph() -> None:
    document = HwpxDocument.new()
    live = document.add_paragraph("12")
    note = live.add_footnote("n", offset=1)
    box = live.add_rectangle(1000, 1000)
    draw_text = box.set_draw_text("x")
    table = document.add_table(1, 1)
    caption = table.set_caption("c")
    note.remove()
    box.remove()
    table.remove()
    for call, code in (
        (lambda: note.add_paragraph("z"), "paragraph-not-in-document"),
        (lambda: note.add_run("z", bold=True), "paragraph-not-in-document"),
        (lambda: draw_text.add_paragraph("z"), "shape-not-in-document"),
        (lambda: caption.add_paragraph("z"), "shape-not-in-document"),
    ):
        with pytest.raises(HwpxValueError) as refused:
            call()
        assert refused.value.code == code
    note.add_run("z")  # no shape to register: stays in the note
    note.text = "w"
    assert note.text == "w"


def test_the_case_from_the_report_keeps_the_text() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("1234")
    table = document.add_table(1, 1)
    target = table.cell(0, 0).paragraphs[0]
    table.remove()
    with pytest.raises(HwpxValueError):
        paragraph.move_range(1, 3, to=target)
    saved = HwpxDocument.open(document.to_bytes())
    assert [p.text for p in saved.paragraphs if p.text] == ["1234"]
