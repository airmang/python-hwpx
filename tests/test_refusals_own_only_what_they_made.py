"""What the review of the first fix round found (exec7/rv4).

The first round undid a refused call by taking out whatever had been appended while the call ran, and
followed a memo by its id. Both reached too far: an argument that edits the document while it is read
lost that edit, a successful call paid for counting every section, and a removed memo's object wrote
into a new memo that was given the same id. This file pins the narrower rules and the paths the first
round left open.

* A refused call takes out the paragraph or the run it made itself, and nothing else.
* A memo object follows the fold of its own entry into a field (noted on the entry), not an id.
* A stream is said to be put back only when reading it back shows it is; a stream that seeks to a
  position and not to its end still saves.
* Text, content, places and counts are checked before anything is tidied or written: a memo's
  ``match`` in the new paragraph text, a header's content before a second header for the same pages
  goes, ``page.setup(columns=256)``, a table's height, another document's section.
* Note numbers after a caption or a text box's text goes, a header's content or a note's text is
  replaced, a note with notes in it is copied, the numbering of a section changes, a section that
  started the count again is removed; and in the sections in front of one numbered per page.
* A note does not move into a master page; a memo in a copied note is a memo of its own; a field
  spanning copied paragraphs gets one new id pair.
"""

from __future__ import annotations

import warnings
from io import BytesIO, UnsupportedOperation
from pathlib import Path
from typing import Any

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxError

FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"


def _saved(document: HwpxDocument) -> HwpxDocument:
    return HwpxDocument.open(document.to_bytes())


def _state(document: HwpxDocument) -> list[bytes]:
    parts = [*document.oxml.sections, *document.oxml.headers, *document.oxml.master_pages]
    return [etree.tostring(part.element) for part in parts]


def _code(call: Any) -> str:
    with pytest.raises(Exception) as caught:  # noqa: PT011 - the kind is each case's own
        call()
    return str(getattr(caught.value, "code", None) or type(caught.value).__name__)


# -- only what the call made ----------------------------------------------------------------------


def test_a_refused_add_keeps_what_its_argument_did_meanwhile() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("host")
    document.add_section()
    document = _saved(document)
    host, other = document.sections[0].paragraphs[-1], document.sections[1].paragraphs[0]

    class Points(list):  # type: ignore[type-arg]
        def __iter__(self) -> Any:
            other.text = "edited"
            document.add_paragraph("completed", section=1)
            return super().__iter__()

    assert _code(lambda: document.shapes.add_polygon(Points([(0, 0)]), paragraph=host)) == "shape-polygon-too-few-points"

    assert [item.text for item in _saved(document).sections[1].paragraphs] == ["edited", "completed"]


def test_a_refused_run_keeps_a_run_its_argument_added_meanwhile() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("host")

    class Widths(list):  # type: ignore[type-arg]
        def __iter__(self) -> Any:
            paragraph.add_run(" kept")
            return super().__iter__()

    assert _code(lambda: paragraph.add_run("\t", tab_widths=Widths([-1]))) == "paragraph-tab-widths"

    assert _saved(document).paragraphs[-1].text == "host kept"


def test_a_refused_add_into_another_section_leaves_no_paragraph_there() -> None:
    document = HwpxDocument.new()
    document.add_section()
    document = _saved(document)
    before = _state(document)

    assert _code(lambda: document.shapes.add_line(line_color="nope", section=0)) == "style-color-invalid"

    assert _state(document) == before


def test_a_control_refused_by_a_warning_made_an_error_leaves_a_document_that_saves() -> None:
    document = HwpxDocument.new()
    paragraph = document.paragraphs[0]

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(UserWarning):
            paragraph.add_control()
    document.add_paragraph("later")

    assert not any(len(control) == 0 for control in paragraph.element.iterfind(".//{*}ctrl"))
    document.to_bytes()


def test_a_refused_control_gives_the_paragraph_its_line_cache_back() -> None:
    document = HwpxDocument.open(FIXTURES / "pages_tab_stops_one_size.hwpx")
    paragraph = next(item for item in document.paragraphs if item.line_segments)
    runs = len(paragraph.runs)

    with pytest.raises(TypeError):
        paragraph.add_control({"type": 42})  # type: ignore[arg-type]
    document.add_paragraph("later edit")

    reopened = _saved(document).paragraphs[0]
    assert len(reopened.runs) == runs and reopened.line_segments


def test_the_warning_of_a_raw_shape_names_the_caller() -> None:
    paragraph = HwpxDocument.new().add_paragraph("x")

    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        paragraph.add_shape("rect")

    assert Path(seen[0].filename).name == Path(__file__).name
    assert paragraph.add_number_restart.__name__ == "add_number_restart"


def test_an_add_into_a_given_paragraph_does_not_count_the_other_sections() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("target")
    calls = 0

    class Counted(type(document.oxml.sections[0].element)):  # type: ignore[misc]
        pass

    real_len = type(document.oxml.sections[0].element).__len__

    def counting(self: Any) -> int:
        nonlocal calls
        calls += 1
        return real_len(self)

    # the rule itself: nothing in the path of a successful add asks a section how many children it has
    import hwpx._document._resolve as resolve

    source = Path(resolve.__file__).read_text(encoding="utf-8")
    wrapper = source[source.index("def refused_leaves_no_paragraph"):source.index("def home_paragraph")]
    assert "len(" not in wrapper and "_dirty" not in wrapper
    document.shapes.add_ruby("x", "y", paragraph=paragraph).remove()
    del Counted, counting


# -- a memo follows its own fold ------------------------------------------------------------------


def test_a_removed_memo_does_not_write_into_a_memo_given_its_id() -> None:
    document = HwpxDocument.new()
    old = document.notes.add_memo("draft", memo_id="stable")
    old.remove()
    document.notes.add_memo("replacement", memo_id="stable", paragraph=document.add_section().paragraphs[0])

    old.text = "stale write"

    assert [memo.text for memo in _saved(document).notes.memos] == ["replacement"]


def test_a_second_object_of_a_memo_reads_and_removes_the_memo_that_is_saved() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("stays")
    paragraph = document.add_paragraph("anchor")
    memo = document.notes.add_memo("first", memo_id="memo1")
    held = document.notes.memos[0]
    document.notes.attach(paragraph, memo)
    paragraph.move_after(document.add_section().paragraphs[0])
    memo.text = "second"

    assert held.text == "second" and held.paragraph is not None
    held.remove()

    assert _saved(document).notes.memos == ()


def test_a_second_object_of_a_memo_does_not_put_its_old_text_back() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("anchor")
    memo = document.notes.add_memo("first", memo_id="test")
    held = document.notes.memos[0]
    document.notes.attach(paragraph, memo)
    memo.text = "updated"

    held.set_attribute("author", "A")

    saved = _saved(document).notes.memos[0]
    assert saved.text == "updated" and saved.attributes.get("Author") == "A"


@pytest.mark.parametrize("kind", ["ruby", "composed"])
def test_a_mark_moved_into_a_cell_of_its_own_paragraph_is_in_that_cell(kind: str) -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("a")
    mark = (document.shapes.add_ruby("b", "annotation", paragraph=paragraph) if kind == "ruby"
            else document.shapes.add_composed_character("b", paragraph=paragraph))
    paragraph.add_run("z")
    cell = paragraph.add_table(1, 1).cell(0, 0).paragraphs[0]

    paragraph.move_range(0, 2, to=cell)

    assert mark.paragraph == cell and mark.paragraph != paragraph


# -- a stream put back, and one that only seeks to a position -------------------------------------


def test_a_stream_is_not_said_to_be_put_back_when_it_was_not() -> None:
    class Interrupted(BytesIO):
        calls = 0

        def write(self, data: Any) -> Any:
            self.calls += 1
            if self.calls == 1:
                super().write(bytes(data[:2]))
                raise OSError("interrupted")
            return None  # takes nothing, and says nothing

    stream = Interrupted(b"abcdef")
    with pytest.raises(OSError, match="interrupted") as caught:
        HwpxDocument.new().save(stream, format="hwpx")

    assert stream.getvalue() != b"abcdef"
    assert caught.value.stream_restored is False  # type: ignore[attr-defined]


def test_a_stream_that_closes_when_it_fails_raises_the_failure_itself() -> None:
    class Disconnected(BytesIO):
        def write(self, data: Any) -> int:
            self.close()
            raise OSError("connection lost")

    with pytest.raises(OSError, match="connection lost") as caught:
        HwpxDocument.new().save(Disconnected(b"abcdef"), format="hwpx")

    assert caught.value.stream_restored is False  # type: ignore[attr-defined]


def test_a_stream_that_seeks_to_a_position_only_still_saves() -> None:
    class AbsoluteOnly(BytesIO):
        def seek(self, offset: int, whence: int = 0) -> int:
            if whence:
                raise UnsupportedOperation("absolute seeks only")
            return super().seek(offset)

    stream = AbsoluteOnly(b"old")
    HwpxDocument.new().save(stream, format="hwpx")

    assert HwpxDocument.open(stream.getvalue()).paragraphs is not None


# -- checked before anything is tidied or written -------------------------------------------------


def test_a_memo_place_that_is_not_in_the_new_text_leaves_the_old_text() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("original")
    before = _state(document)

    code = _code(lambda: document.notes.add_memo("review", paragraph=paragraph, paragraph_text="new", match="new", index=1))

    assert code == "note-match-not-found" and _state(document) == before


def test_a_memo_on_the_second_place_of_the_new_text_is_put_there() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("original")

    document.notes.add_memo("review", paragraph=paragraph, paragraph_text="new and new", match="new", index=1)

    saved = _saved(document)
    assert saved.paragraphs[-1].text == "new and new" and len(saved.notes.memos) == 1


@pytest.mark.parametrize("bad", [{"content": [{"children": [{"type": "unknown"}]}]}, {"text": 5}])
def test_a_refused_header_write_keeps_a_second_header_for_the_same_pages(bad: dict[str, Any]) -> None:
    document = HwpxDocument.new()
    document.page.set_header(text="keep", page_type="BOTH")
    document.page.set_header(text="specific", page_type="ODD").page_type = "BOTH"
    before = _state(document)

    with pytest.raises(HwpxError):
        document.page.set_header(**bad)

    assert _state(document) == before
    assert [story.text for story in _saved(document).page.headers()] == ["keep", "specific"]


@pytest.mark.parametrize("columns", [256, 10**6, 0, -1])
def test_page_setup_refuses_a_column_count_for_every_section_before_it_writes(columns: int) -> None:
    document = HwpxDocument.new()
    document.add_section()
    before = _state(document)

    assert _code(lambda: document.page.setup(paper_size="A5", columns=columns, section="all")) == "page-columns-invalid"

    assert _state(document) == before


@pytest.mark.parametrize("height", ["bad", -1, 2.5, True])
def test_a_table_height_that_is_not_one_is_refused_before_a_border_is_declared(height: Any) -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("outer")
    cell = paragraph.add_table(1, 1, border_fill_id_ref="1").cell(0, 0)
    before = _state(document)

    assert _code(lambda: cell.add_table(2, 2, height=height)) == "table-height-value"
    assert _code(lambda: paragraph.add_table(2, 2, height=height)) == "table-height-value"
    assert _code(lambda: document.add_table(2, 2, height=height)) == "table-height-value"

    assert _state(document) == before


def test_another_documents_section_is_refused() -> None:
    png = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
    mine, other = HwpxDocument.new(), HwpxDocument.new()
    other.add_paragraph("foreign")
    before = _state(mine), _state(other)

    assert _code(lambda: mine.add_picture(png, "svg", section=other.sections[0])) == "section-not-found"
    assert _code(lambda: mine.notes.add_footnote("note", section=other.sections[0])) == "section-not-found"
    assert _code(lambda: mine.add_paragraph("text", section=other.sections[0])) == "section-not-found"

    assert (_state(mine), _state(other)) == before
    assert len(mine.media.images) == 0


# -- note numbers ---------------------------------------------------------------------------------


def _numbers(document: HwpxDocument) -> list[tuple[int, str | None, str | None]]:
    return [(note.number, note.element.get("number"), note.element.find(".//{*}autoNum").get("num"))
            for note in _saved(document).notes.footnotes]


@pytest.mark.parametrize("edit", ["caption", "box", "header", "note", "copy", "numbering", "per-page"])
def test_the_number_written_is_the_number_read_after(edit: str) -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("a")
    owner: Any = None
    if edit == "caption":
        owner = paragraph.add_table(1, 1)
        inner = owner.set_caption("cap").paragraphs[0]
    elif edit == "box":
        owner = document.shapes.add_rectangle(paragraph=paragraph)
        inner = owner.set_draw_text("box").paragraphs[0]
    elif edit == "header":
        owner = document.page.set_header(text="head")
        inner = owner.paragraphs[0]
    elif edit in ("note", "copy"):
        owner = paragraph.add_endnote("outer")
        inner = owner.add_paragraph("inner")
    else:
        inner = paragraph
    inner.add_footnote("one")
    last = document.add_paragraph("b")
    last.add_footnote("two")

    if edit == "caption":
        owner.remove_caption()
    elif edit == "box":
        owner.set_draw_text("new")
    elif edit == "header":
        owner.set_content([{"text": "new"}])
    elif edit == "note":
        owner.text = "new"
    elif edit == "copy":
        owner.copy_to(last)
    elif edit == "numbering":
        paragraph.section.properties.set_footnote_numbering(type="ON_SECTION", new_num=7)
    else:
        document.add_section().properties.set_footnote_numbering(type="ON_PAGE")
        paragraph.clear_content()

    numbers = _numbers(document)
    assert numbers and all(str(read) == number == auto for read, number, auto in numbers), numbers


def test_removing_a_section_that_started_the_count_again_numbers_the_notes_after_it() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("a").add_footnote("first")
    middle = document.add_section()
    last = document.add_section()
    middle.properties.set_footnote_numbering(type="ON_SECTION", new_num=9)
    last.properties.set_footnote_numbering(type="CONTINUOUS")
    last.paragraphs[0].add_footnote("last")

    document.remove_section(1)

    assert _numbers(document) == [(1, "1", "1"), (2, "2", "2")]


# -- places and copies ----------------------------------------------------------------------------


@pytest.mark.parametrize("how", ["move_to", "copy_to"])
def test_a_note_does_not_go_into_a_cell_of_a_master_page(how: str) -> None:
    document = HwpxDocument.new()
    note = document.add_paragraph("body").add_footnote("keep")
    page = document.parts.add_master_page(text="master", section=0)
    cell = page.paragraphs[0].add_table(1, 1).cell(0, 0)
    before = _state(document)

    assert _code(lambda: getattr(note, how)(cell.paragraphs[0])) == "paragraph-move-place-unsupported"

    assert _state(document) == before
    assert len(_saved(document).notes.footnotes) == 1


def test_a_memo_in_a_copied_note_is_a_memo_of_its_own() -> None:
    document = HwpxDocument.new()
    note = document.add_paragraph("body").add_endnote("outer")
    document.notes.add_memo("comment", paragraph=note.add_paragraph("inside"))

    note.copy_to(document.add_paragraph("copy"))

    memos = _saved(document).notes.memos
    assert len({memo.id for memo in memos}) == len({memo.attributes.get("Number") for memo in memos}) == 2
    assert len({memo.field_id for memo in memos}) == 2


def test_a_field_spanning_the_copied_paragraphs_gets_one_new_id_pair() -> None:
    document = HwpxDocument.open(FIXTURES / "form_fields_spanning_before.hwpx")
    section = document.sections[0]

    section.insert_paragraphs(len(section.paragraphs), section.paragraphs[2:6])

    document = _saved(document)
    ids = [field.field_id for field in document.fields.all if field.name == "본문"]
    assert len(ids) == len(set(ids)) == 2
    document.fields.fill("replacement", field_id=ids[0])  # was field-ambiguous


# -- tracking flags -------------------------------------------------------------------------------


def test_a_tracking_element_without_flags_is_set_to_show_the_change() -> None:
    from hwpx.tools.redline import inspect_redline_structure

    document = HwpxDocument.new()
    header = document.parts.headers[0]
    del header.element.find("{*}trackchageConfig").attrib["flags"]
    header.mark_dirty()

    document.tracking.insert(document.add_paragraph("body"), " edit", author="A")

    data = document.to_bytes()
    assert HwpxDocument.open(data).parts.headers[0].element.find("{*}trackchageConfig").get("flags") == "56"
    assert inspect_redline_structure(data)["displayEnabled"] is True
