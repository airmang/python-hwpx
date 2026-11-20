"""The paths left open after #803 (exec7/rv4).

* A header or footer object taken before the paragraph holding its control moved to another section
  saves what is written through it.
* So does a memo of a 6.x document (kept in ``hp:memogroup``), whose entry the move folds into its
  MEMO field.
* The notes left after ``remove_section`` are written with the numbers they are read with.
* A footnote on a master page is refused with a code (it raised ``AttributeError``), and a table of a
  master page that was read from a file takes rows and columns (the edit raised ``AttributeError``
  after it had changed the table).
* A radio button on a master page goes off when another button of its group is checked.
* A failed save puts a stream back to where it ended, also when the stream stood past its end, and
  says so on the error when it could not put the stream back.
"""

from __future__ import annotations

import copy
import io
import re
import zipfile
from typing import Any

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxError

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _saved(document: HwpxDocument) -> HwpxDocument:
    return HwpxDocument.open(document.to_bytes())


def _xml(document: HwpxDocument) -> str:
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        return "".join(archive.read(name).decode("utf-8") for name in archive.namelist() if name.endswith(".xml"))


# -- a header whose paragraph moved ---------------------------------------------------------------


@pytest.mark.parametrize("kind", ["header", "footer"])
def test_a_story_taken_before_its_paragraph_moved_saves_its_text(kind: str) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("stays")
    host = document.add_paragraph("holds the control")
    getattr(document.page, f"set_{kind}")(text="original")
    story = getattr(document.page, f"{kind}s")(section=0)[0]
    control = story.element.getparent()
    run = host.element.makeelement(control.getparent().tag, dict(control.getparent().attrib))
    host.element.append(run)
    run.append(control)  # the control in a body paragraph, as Hancom writes one for a later page
    document.sections[0].mark_dirty()
    story = getattr(document.page, f"{kind}s")(section=0)[0]
    destination = document.add_section().paragraphs[0]
    host.move_after(destination)
    document.to_bytes()  # nothing is pending when the edit comes

    story.text = "changed"

    reopened = _saved(document)
    texts = [item.text for index in range(len(reopened.sections)) for item in getattr(reopened.page, f"{kind}s")(section=index)]
    assert texts == ["changed"]


# -- a 6.x memo whose paragraph moved -------------------------------------------------------------


def _with_a_memo_group_memo() -> tuple[HwpxDocument, Any]:
    from hwpx.oxml.memo import memo_field_id

    document = HwpxDocument.new()
    document.add_paragraph("stays")
    document.notes.add_memo("old text", paragraph=document.add_paragraph("annotated text"))
    section = document.sections[0]
    field = next(node for node in section.element.iter(f"{_HP}fieldBegin") if node.get("type") == "MEMO")
    group = section.element.makeelement(f"{_HP}memogroup", {})
    entry = group.makeelement(f"{_HP}memo", {"id": str(memo_field_id(field))})
    paragraphs = entry.makeelement(f"{_HP}paraList", {})
    paragraphs.append(copy.deepcopy(field.find(f"{_HP}subList").find(f"{_HP}p")))
    paragraphs.find(f".//{_HP}t").text = "6.x memo-group text"
    entry.append(paragraphs)
    group.append(entry)
    section.element.append(group)  # a 6.x document: the memo in its group and its field
    section.mark_dirty()
    document = _saved(document)
    return document, next(item for item in document.paragraphs if item.text.startswith("annotated"))


def test_a_memo_group_memo_taken_before_its_paragraph_moved_saves_its_text() -> None:
    document, paragraph = _with_a_memo_group_memo()
    memo = document.notes.memos[0]
    assert memo.text == "6.x memo-group text"
    paragraph.move_after(document.add_section().paragraphs[0])
    document.to_bytes()

    memo.text = "changed"

    assert [item.text for item in _saved(document).notes.memos] == ["changed"]


def test_a_memo_group_memo_that_did_not_move_is_written_as_before() -> None:
    document, _ = _with_a_memo_group_memo()
    memo = document.notes.memos[0]

    memo.text = "changed in place"

    assert [item.text for item in _saved(document).notes.memos] == ["changed in place"]


# -- note numbers after a section goes ------------------------------------------------------------


@pytest.mark.parametrize("removed", [0, 1, 2])
def test_the_notes_left_after_a_section_is_removed_are_numbered_as_read(removed: int) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("a").add_footnote("one")
    document.add_section()
    document.add_paragraph("b", section=1).add_footnote("two")
    document.add_section()
    document.add_paragraph("c", section=2).add_footnote("three")

    document.remove_section(removed)

    notes = _saved(document).notes.footnotes
    written = [(note.element.get("number"), note.element.find(".//{*}autoNum").get("num")) for note in notes]
    assert [note.number for note in notes] == [1, 2]
    assert written == [("1", "1"), ("2", "2")]


# -- master pages ---------------------------------------------------------------------------------


def test_a_footnote_on_a_master_page_is_refused_with_a_code() -> None:
    from lxml import etree

    document = HwpxDocument.new()
    page = document.parts.add_master_page(text="master", page_type="BOTH", section=0)
    before = etree.tostring(page.element)

    with pytest.raises(HwpxError) as caught:
        page.paragraphs[0].add_footnote("note")

    assert caught.value.code == "paragraph-move-place-unsupported"
    assert etree.tostring(page.element) == before


def test_a_table_of_a_master_page_read_from_a_file_takes_rows() -> None:
    document = HwpxDocument.new()
    page = document.parts.add_master_page(text="master", page_type="BOTH", section=0)
    page.paragraphs[0].add_table(2, 2).set_cell_text(0, 0, "a")
    document = _saved(document)
    table = document.parts.master_pages[0].paragraphs[0].tables[0]

    document.tables.insert_rows(table, 0, copy_content=True)

    reopened = _saved(document).parts.master_pages[0].paragraphs[0].tables[0]
    assert len(reopened.rows) == 3
    assert reopened.cell(0, 0).text == reopened.cell(1, 0).text == "a"


def test_a_radio_button_on_a_master_page_goes_off_with_its_group() -> None:
    document = HwpxDocument.new()
    page = document.parts.add_master_page(text="master", page_type="BOTH", section=0)
    first = document.fields.add_radio_button("a", group="g", checked=True, paragraph=document.add_paragraph("first"))
    second = document.fields.add_radio_button("b", group="g", checked=False, paragraph=document.add_paragraph("second"))
    run = first.element.getparent()
    page.paragraphs[0].element.append(run)  # the first button on the master page, as a form drawn on every page
    document.sections[0].mark_dirty()
    page.mark_dirty()
    del second
    document = _saved(document)

    document.fields.radio_buttons[-1].checked = True

    values = dict(re.findall(r'<hp:radioBtn caption="(\w)"[^>]*?value="(\w+)"', _xml(document)))
    assert values == {"a": "UNCHECKED", "b": "CHECKED"}


# -- a stream put back ----------------------------------------------------------------------------


class _Failing(io.BytesIO):
    """A stream whose next long write takes a few bytes and fails (once: what puts the stream back
    writes too); *stuck* makes it refuse the cut that would put it back."""

    armed = False
    stuck = False

    def write(self, data: Any) -> int:
        if self.armed and len(data) > 3:
            self.armed = False
            super().write(bytes(data[:5]))
            raise OSError("disk full")
        return super().write(data)

    def truncate(self, size: int | None = None) -> int:
        if self.stuck:
            raise OSError("cannot cut")
        return super().truncate(size)


@pytest.mark.parametrize(("held", "position"), [(b"abc", 6), (b"abc", 3), (b"abcdef", 2), (b"", 0), (b"", 4)])
def test_a_failed_stream_save_leaves_the_stream_as_long_as_it_was(held: bytes, position: int) -> None:
    document = HwpxDocument.new()
    stream = _Failing(held)
    stream.seek(position)
    stream.armed = True

    with pytest.raises(OSError, match="disk full") as caught:
        document.save(stream, format="hwpx")

    assert stream.getvalue() == held  # standing past its end, it came back three zero bytes longer
    assert stream.tell() == position
    assert getattr(caught.value, "stream_restored", None) is True


def test_a_stream_that_cannot_be_put_back_says_so_on_the_error() -> None:
    document = HwpxDocument.new()
    stream = _Failing(b"abc")
    stream.seek(3)
    stream.armed = stream.stuck = True

    with pytest.raises(OSError, match="disk full") as caught:
        document.save(stream, format="hwpx")

    assert getattr(caught.value, "stream_restored", None) is False
    notes = getattr(caught.value, "__notes__", None)
    if notes is not None:  # Python 3.11+
        assert any("could not be put back" in note for note in notes)
