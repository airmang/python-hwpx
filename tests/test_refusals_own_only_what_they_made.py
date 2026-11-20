"""What the review of the first fix round found (exec7/rv4).

The first round undid a refused call by taking out whatever had been appended while the call ran, and
followed a memo by its id. Both reached too far: an argument that edits the document while it is read
lost that edit, a successful call paid for counting every section, and a removed memo's object wrote
into a new memo that was given the same id. This file pins the narrower rules and the paths the first
round left open.

* A refused call takes out the paragraph or the run it made itself, and nothing else.
* A memo object follows the fold of its own entry into a field (the field itself is remembered under
  a token only that entry carries), not an id.
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


# -- the third look: ids that are used again, one paragraph copied twice, streams, numbers ---------


def test_a_removed_memo_does_not_write_into_a_memo_given_its_field_id() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("anchor")
    memo = document.notes.add_memo("old", memo_id="first")
    held = document.notes.memos[0]
    document.notes.attach(paragraph, memo, field_id="77")
    memo.remove()
    document.notes.add_memo("replacement", paragraph=paragraph, memo_id="second", field_id="77")

    held.text = "stale write"

    assert [item.text for item in _saved(document).notes.memos] == ["replacement"]


def test_a_copy_through_a_second_object_of_a_memo_can_be_anchored_and_saved() -> None:
    document = HwpxDocument.new()
    memo = document.notes.add_memo("comment")
    held = document.notes.memos[0]
    document.notes.attach(document.add_paragraph("a"), memo)

    copied = held.copy_to(0)
    document.notes.attach(document.add_paragraph("b"), copied)

    assert [item.text for item in _saved(document).notes.memos] == ["comment", "comment"]


@pytest.mark.parametrize("copies", [2, 3])
def test_one_form_paragraph_copied_more_than_once_gives_each_copy_its_own_pair(copies: int) -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("row")
    paragraph.add_form_field("F", prompt="fill")

    paragraph.section.insert_paragraphs(1, [paragraph] * copies)

    document = _saved(document)
    pairs = [(item.element.find(".//{*}fieldBegin").get("id"), item.element.find(".//{*}fieldEnd").get("beginIDRef"))
             for item in document.paragraphs if item.element.find(".//{*}fieldBegin") is not None]
    assert len(pairs) == copies + 1 and all(begin == end for begin, end in pairs)
    assert len({begin for begin, _ in pairs}) == copies + 1
    for field in document.fields.all:
        document.fields.fill("x", field_id=field.field_id)  # was field-ambiguous for two of three


def test_a_spanning_field_copied_twice_in_one_call_pairs_within_each_copy() -> None:
    document = HwpxDocument.open(FIXTURES / "form_fields_spanning_before.hwpx")
    section = document.sections[0]
    group = list(section.paragraphs[2:6])

    section.insert_paragraphs(len(section.paragraphs), group + group)

    ids = [field.field_id for field in _saved(document).fields.all if field.name == "본문"]
    assert len(ids) == len(set(ids)) == 3


def test_a_copied_memo_names_its_number_in_its_command_too() -> None:
    document = HwpxDocument.new()
    note = document.add_paragraph("body").add_endnote("outer")
    document.notes.add_memo("comment", paragraph=note.add_paragraph("inside"))

    note.copy_to(document.add_paragraph("copy"))

    for memo in _saved(document).notes.memos:
        command = next(param.text for param in memo.element.iter("{*}stringParam") if param.get("name") == "Command")
        assert command.split("/")[2] == memo.attributes.get("Number")


def test_a_restore_that_cannot_be_read_back_and_was_not_counted_is_not_called_done() -> None:
    class DisconnectRead(BytesIO):
        attempted = False

        def read(self, *args: Any) -> bytes:
            if self.attempted:
                raise OSError("read unavailable")
            return super().read(*args)

        def write(self, data: Any) -> Any:
            if self.attempted:
                return None
            self.attempted = True
            super().write(bytes(data[:2]))
            raise OSError("interrupted")

    stream = DisconnectRead(b"abcdef")
    with pytest.raises(OSError, match="interrupted") as caught:
        HwpxDocument.new().save(stream, format="hwpx")

    assert caught.value.stream_restored is False  # type: ignore[attr-defined]


@pytest.mark.parametrize("arguments", [{"paragraph_text": 42}, {"paragraph_text": "new", "match": "new", "index": -1}])
def test_a_refused_memo_leaves_no_memo_and_the_paragraph_as_it_was(arguments: dict[str, Any]) -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("original")
    before = _state(document)

    with pytest.raises(HwpxError):
        document.notes.add_memo("review", paragraph=paragraph, **arguments)

    assert _state(document) == before and document.notes.memos == ()
    document.to_bytes()  # a memo left without its anchor kept the document from being saved


def test_a_table_refused_for_its_style_declares_no_border() -> None:
    document = HwpxDocument.new()
    before = _state(document)

    assert _code(lambda: document.add_table(1, 1, style="missing style")) == "style-not-found"

    assert _state(document) == before


def test_the_document_view_refuses_another_documents_section_too() -> None:
    mine, other = HwpxDocument.new(), HwpxDocument.new()
    before = _state(other)

    assert _code(lambda: mine.oxml.add_paragraph("foreign", section=other.sections[0])) == "section-not-found"

    assert _state(other) == before


def test_a_refused_run_does_not_bring_back_a_line_cache_for_a_paragraph_that_changed() -> None:
    document = HwpxDocument.open(FIXTURES / "pages_tab_stops_one_size.hwpx")
    paragraph = next(item for item in document.paragraphs if item.line_segments and item.runs)

    class Widths(list):  # type: ignore[type-arg]
        def __iter__(self) -> Any:
            paragraph.runs[0].text = "edited while the call ran"
            return super().__iter__()

    assert _code(lambda: paragraph.add_run("\t", tab_widths=Widths([-1]))) == "paragraph-tab-widths"

    assert not paragraph.line_segments  # the lines it was read with are not this text's any more


def test_a_run_whose_attributes_cannot_be_written_is_not_put_into_the_paragraph() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("x")
    before = _state(document)

    with pytest.raises(TypeError):
        paragraph.add_run("t", attributes={"a": 1})  # type: ignore[dict-item]

    assert _state(document) == before


def test_removing_a_note_counts_the_notes_in_its_text_out() -> None:
    document = HwpxDocument.new()
    note = document.add_paragraph("outer").add_endnote("outer")
    note.add_paragraph("inner").add_footnote("nested")
    document.add_paragraph("last").add_footnote("remaining")

    note.remove()

    assert _numbers(document) == [(1, "1", "1")]


def test_a_header_tidied_away_takes_its_notes_out_of_the_count() -> None:
    document = HwpxDocument.new()
    document.page.set_header(text="one")
    other = document.page.set_header(text="two", page_type="ODD")
    other.paragraphs[0].add_footnote("header")
    other.page_type = "BOTH"
    document.add_paragraph("body").add_footnote("body")

    document.page.set_header(text="new")

    assert _numbers(document) == [(1, "1", "1")]


def test_header_content_that_fails_while_it_is_written_gives_the_notes_their_numbers_back() -> None:
    document = HwpxDocument.new()
    header = document.page.set_header(text="one")
    header.paragraphs[0].add_footnote("header")
    document.add_paragraph("body").add_footnote("body")

    with pytest.raises(Exception):  # noqa: B017, PT011 - lxml refuses the NUL in the font name
        header.set_content([{"runs": [{"size": 37, "text": "x"}, {"font": "bad\x00name", "text": "y"}]}])

    assert _numbers(document) == [(1, "1", "1"), (2, "2", "2")]


def test_a_section_that_starts_the_count_again_is_numbered_after_one_numbered_per_page() -> None:
    document = HwpxDocument.new()
    first = document.add_paragraph("a").add_footnote("first")
    page = document.add_section()
    page.properties.set_footnote_numbering(type="ON_PAGE")
    page.paragraphs[0].add_footnote("page")
    running = document.add_section()
    running.properties.set_footnote_numbering(type="CONTINUOUS")
    running.paragraphs[0].add_footnote("continuous")
    last = document.add_section()
    last.properties.set_footnote_numbering(type="ON_SECTION", new_num=8)
    last.paragraphs[0].add_footnote("restart")

    first.remove()

    numbers = _numbers(document)
    assert numbers[-1] == (8, "8", "8")  # known without laying a page out
    assert numbers[0][1:] == ("2", "2") and numbers[1][1:] == ("3", "3")  # per page, and running on: as written


def test_a_document_without_notes_is_not_walked_to_number_them() -> None:
    import hwpx.oxml.note_authoring as authoring

    document = HwpxDocument.new()
    document.add_section()
    calls: list[int] = []
    real = authoring.note_numbers
    authoring.note_numbers = lambda sections: calls.append(1) or real(sections)  # type: ignore[assignment]
    try:
        document.sections[0].properties.set_footnote_numbering(type="ON_SECTION", new_num=2)
        document.remove_section(1)
    finally:
        authoring.note_numbers = real

    assert calls == []


# -- the fourth look: what the third round's own additions broke, taken back ------------------------


@pytest.mark.parametrize(("position", "restored", "held"), [(0, True, b""), (6, False, None)])
def test_a_stream_without_a_seek_to_its_end_is_said_put_back_only_when_its_end_is_known(
    position: int, restored: bool, held: bytes | None,
) -> None:
    class AbsolutePartial(BytesIO):
        def seek(self, offset: int, whence: int = 0) -> int:
            if whence:
                raise UnsupportedOperation("absolute only")
            return super().seek(offset)

        def read(self, size: Any = -1) -> Any:
            if size == 1:
                return None  # nothing yet: must not be taken for the end of the stream
            return super().read(size)

        def write(self, data: Any) -> int:
            super().write(bytes(data[:2]))
            raise OSError("partial")

    stream = AbsolutePartial(b"" if position == 0 else b"abcdef")
    stream.seek(position)
    with pytest.raises(OSError, match="partial") as caught:
        HwpxDocument.new().save(stream, format="hwpx")

    assert caught.value.stream_restored is restored  # type: ignore[attr-defined]
    if held is not None:
        assert stream.getvalue() == held
    else:
        assert stream.getvalue().startswith(b"abcdef")  # what it held is still there


def test_a_restore_that_cannot_seek_back_is_not_called_done() -> None:
    class FinalSeek(BytesIO):
        phase = 0

        def write(self, data: Any) -> int:
            if self.phase == 0:
                self.phase = 1
                super().write(bytes(data[:2]))
                raise OSError("interrupted")
            return super().write(data)

        def read(self, *args: Any) -> bytes:
            data = super().read(*args)
            if self.phase == 1:
                self.phase = 2
            return data

        def seek(self, *args: Any) -> int:
            if self.phase == 2:
                raise OSError("seek lost")
            return super().seek(*args)

    stream = FinalSeek(b"abcdef")
    stream.seek(1)
    with pytest.raises(OSError, match="interrupted") as caught:
        HwpxDocument.new().save(stream, format="hwpx")

    assert caught.value.stream_restored is False  # type: ignore[attr-defined]


@pytest.mark.parametrize("inside", ["table", "footnote"])
def test_a_memo_holding_a_table_or_a_note_is_anchored_and_saved(inside: str) -> None:
    document = HwpxDocument.new()
    memo = document.notes.add_memo("draft")
    if inside == "table":
        memo.paragraphs[0].add_table(1, 1).cell(0, 0).text = "A1"
    else:
        memo.paragraphs[0].add_footnote("cited source")

    document.notes.attach(document.paragraphs[0], memo)

    assert len(_saved(document).notes.memos) == 1  # the cell's (the note's) own paragraph stayed in it


def test_a_memo_anchored_through_another_document_does_not_reach_a_memo_of_its_own_document() -> None:
    mine, other = HwpxDocument.new(), HwpxDocument.new()
    mine.notes.add_memo("A own", paragraph=mine.paragraphs[0])
    memo = mine.notes.add_memo("draft")
    held = next(item for item in mine.notes.memos if item.text == "draft")
    other.notes.attach(other.paragraphs[0], memo)
    memo.text = "B own"

    held.text = "held edit"

    assert [item.text for item in _saved(mine).notes.memos] == ["A own"]
    assert [item.text for item in _saved(other).notes.memos] == ["B own"]


def test_a_paragraph_copied_from_another_opening_keeps_the_memo_text_it_has() -> None:
    legacy = Path(__file__).parent / "fixtures" / "fuzz_regressions" / "seed-000000-baseline.hwpx"
    source, target = HwpxDocument.open(legacy), HwpxDocument.open(legacy)
    memo = source.notes.memos[0]
    memo.text = "corrected in revision B"
    section = target.sections[0]

    copy = section.insert_paragraphs(len(section.paragraphs), [memo.paragraph])[0]

    saved = next(item for item in _saved(target).paragraphs if item.element.get("id") == copy.element.get("id"))
    field = next(node for node in saved.element.iter("{*}fieldBegin") if node.get("type") == "MEMO")
    assert "corrected in revision B" in "".join(field.find("{*}subList").itertext())


def test_the_record_of_folded_memos_does_not_grow_with_memos_that_are_gone() -> None:
    document = HwpxDocument.new()
    for _ in range(10):
        document.notes.add_memo("x" * 64, paragraph=document.paragraphs[0]).remove()

    assert len(getattr(document.oxml, "_folded_memo_fields", {})) <= 1


def test_a_merged_file_with_one_field_id_used_twice_pairs_each_end_with_its_begin() -> None:
    from hwpx.tools.document_merge import append_document

    source = HwpxDocument.open(FIXTURES / "pages_click_here_field_around_a_table_wider_than_the_line.hwpx")
    target = HwpxDocument.new()

    append_document(target, source)

    section = _saved(target).sections[0].element
    begins = [node.get("id") for node in section.iter("{*}fieldBegin")]
    ends = [node.get("beginIDRef") for node in section.iter("{*}fieldEnd")]
    assert len(set(begins)) == len(begins) == 2
    assert [begins.index(end) for end in ends] == [0, 1]  # was [1, 1]: both ends on the second field


def test_a_merge_refused_for_its_place_brings_nothing_of_the_source() -> None:
    from hwpx.tools.document_merge import insert_document

    from tests.test_refused_calls_sweep import PNG

    target, source = HwpxDocument.new(), HwpxDocument.new()
    source.add_picture(PNG, "png")
    source.add_paragraph("content", char_pr_id_ref=source.styles.ensure_run(size=37))
    before = _state(target)

    assert _code(lambda: insert_document(target, source, after_paragraph_index=99)) == "document-merge-index-out-of-range"

    assert _state(target) == before and len(target.media.images) == 0


@pytest.mark.parametrize("kind", ["footnote", "endnote"])
@pytest.mark.parametrize("edit", ["story.text", "remove_header", "memo.text", "memo.remove"])
def test_notes_that_go_with_a_header_or_a_memo_leave_the_count(kind: str, edit: str) -> None:
    document = HwpxDocument.new()
    if edit.startswith("memo"):
        owner: Any = document.notes.add_memo("draft", paragraph=document.paragraphs[0])
    else:
        owner = document.page.set_header(text="header")
    getattr(owner.paragraphs[0], f"add_{kind}")("old")
    getattr(document.add_paragraph("body"), f"add_{kind}")("body")

    if edit == "story.text":
        owner.text = "new"
    elif edit == "remove_header":
        document.page.remove_header()
    elif edit == "memo.text":
        owner.text = "replaced"
    else:
        owner.remove()

    notes = getattr(_saved(document).notes, f"{kind}s")
    assert [(note.number, note.element.get("number"), note.element.find(".//{*}autoNum").get("num"))
            for note in notes] == [(1, "1", "1")]
