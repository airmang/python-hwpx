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
    "insert_text": lambda d, live, gone: gone.insert_text(1, "x"),
    "delete_range": lambda d, live, gone: gone.delete_range(0, 1),
    "set_text_preserving_runs": lambda d, live, gone: gone.set_text_preserving_runs("zz"),
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


def test_edits_that_stay_in_the_paragraph_still_work() -> None:
    document, _live, gone, _holder = _taken_out("cell")
    gone.add_run("y")
    gone.text = "z"
    assert gone.text == "z"


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
    gone = document.add_table(1, 1)
    gone.remove()
    live = document.add_table(1, 1)
    for call in (
        lambda: live.copy_rows(0, to=1, source=gone),
        lambda: gone.copy_rows(0, to=1),
        lambda: gone.move_rows(0, to=1),
    ):
        with pytest.raises(HwpxValueError) as refused:
            call()
        assert refused.value.code == "table-not-in-document"


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
