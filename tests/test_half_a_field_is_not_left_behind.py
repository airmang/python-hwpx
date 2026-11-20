# SPDX-License-Identifier: Apache-2.0
"""A deletion does not leave one end of a field alone in another paragraph.

A field's ``hp:fieldBegin`` and ``hp:fieldEnd`` may stand in different paragraphs
(``form_fields_spanning_before.hwpx``, saved by Hancom: field ``658590940`` begins in paragraph 2 and ends
in paragraph 5, field ``209565389`` begins in paragraph 7 and ends in paragraph 8;
``seoul_sihaengmun.hwpx``: the body field begins in the paragraph that starts the section). Deleting the
paragraph holding one end left the other end alone (7.0.0): an ``hp:fieldEnd`` naming no begin, or a begin
that never ends. ``paragraph.delete_range`` refuses a range holding one end of a field
(``paragraph-range-splits-field``); deleting the paragraph, its run, or its content is refused the same
way, before anything changes.

Only the end left in *another* paragraph is refused. A field that begins and ends in one paragraph (a
hyperlink) is taken apart run by run as before: the end left for a moment stands in the paragraph being
edited. An end's paragraph is the nearest ``hp:p`` above it, so a table cell's paragraph is a paragraph of
its own and the paragraph holding the table is another.
"""

from __future__ import annotations

import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pytest

from hwpx import HwpxDocument, validate_package
from hwpx.errors import HwpxValueError

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures"
#: Field 658590940 begins in paragraph 2 and ends in paragraph 5; field 209565389 begins in paragraph 7
#: and ends in paragraph 8; paragraphs 6 and 9 hold whole fields.
SPANNING_FIELD = FIXTURES / "hancom_saved" / "form_fields_spanning_before.hwpx"
SPANNING_ID = "658590940"
#: The body field begins in paragraph 0, which also holds the section's settings, and ends in paragraph 4.
SEOUL = FIXTURES / "m3_gongmun_gold" / "seoul_sihaengmun.hwpx"
#: A table of contents Hancom made: one ``TABLEOFCONTENTS`` field from paragraph 0 to the last entry.
TABLE_OF_CONTENTS = FIXTURES / "m7_toc_gold" / "hancom-native-toc-A.hwpx"
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _open(path: Path) -> HwpxDocument:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return HwpxDocument.open(path)


def _field_marks(document: HwpxDocument) -> tuple[list[str], list[str]]:
    body = document.sections[0].element
    return ([str(node.get("id")) for node in body.iter(f"{HP}fieldBegin")],
            [str(node.get("beginIDRef")) for node in body.iter(f"{HP}fieldEnd")])


def _run_holding_the_mark(paragraph: Any) -> Any:
    return next(run for run in paragraph.runs if run.element.find(f"{HP}ctrl/{HP}fieldBegin") is not None
                or run.element.find(f"{HP}ctrl/{HP}fieldEnd") is not None)


# -- the paragraph holding one end ---------------------------------------------------------------------


def _remove(document: HwpxDocument, paragraph: Any) -> None:
    paragraph.remove()


def _section_remove(document: HwpxDocument, paragraph: Any) -> None:
    document.sections[0].remove_paragraph(paragraph)


def _section_remove_by_index(document: HwpxDocument, paragraph: Any) -> None:
    section = document.sections[0]
    section.remove_paragraph(next(i for i, other in enumerate(section.paragraphs) if other == paragraph))


def _model_remove(document: HwpxDocument, paragraph: Any) -> None:
    document.oxml.remove_paragraph(paragraph)


def _run_remove(document: HwpxDocument, paragraph: Any) -> None:
    _run_holding_the_mark(paragraph).remove()


def _clear_content(document: HwpxDocument, paragraph: Any) -> None:
    paragraph.clear_content()


PARAGRAPH_REMOVALS = [_remove, _section_remove, _section_remove_by_index, _model_remove]
DELETIONS = [*PARAGRAPH_REMOVALS, _run_remove, _clear_content]


@pytest.mark.parametrize("delete", DELETIONS)
@pytest.mark.parametrize(("paragraph", "holds"), [(2, "begin"), (5, "end")])
def test_deleting_what_holds_one_end_of_a_field_is_refused_and_changes_nothing(
    delete: Callable[..., None], paragraph: int, holds: str
) -> None:
    document = _open(SPANNING_FIELD)
    before = document.to_bytes()

    with pytest.raises(HwpxValueError) as refused:
        delete(document, document.paragraphs[paragraph])

    assert refused.value.code == "paragraph-range-splits-field"
    assert refused.value.context["field"] == SPANNING_ID and refused.value.context["holds"] == holds
    assert refused.value.context["type"] == "CLICK_HERE"
    assert refused.value.context["what"] == ("run" if delete is _run_remove else "paragraph")
    assert refused.value.suggestion
    assert document.to_bytes() == before  # nothing changed
    begins, ends = _field_marks(document)
    assert begins.count(SPANNING_ID) == ends.count(SPANNING_ID) == 1


@pytest.mark.parametrize("paragraph", [2, 5])
def test_it_is_the_refusal_deleting_the_paragraphs_characters_gives(paragraph: int) -> None:
    document = _open(SPANNING_FIELD)
    target = document.paragraphs[paragraph]

    with pytest.raises(HwpxValueError) as by_range:
        target.delete_range(0, len(target.text), objects="remove")
    with pytest.raises(HwpxValueError) as by_paragraph:
        target.remove()

    assert by_paragraph.value.code == by_range.value.code == "paragraph-range-splits-field"
    assert by_paragraph.value.context["field"] == by_range.value.context["field"] == SPANNING_ID


@pytest.mark.parametrize("delete", DELETIONS)
@pytest.mark.parametrize("paragraph", [2, 5])
def test_the_same_deletions_work_once_the_field_is_removed(delete: Callable[..., None], paragraph: int) -> None:
    document = _open(SPANNING_FIELD)
    target = document.paragraphs[paragraph]
    words = "".join(other.text for other in document.paragraphs)
    count = len(document.paragraphs)
    next(field for field in document.fields.all if field.field_id == SPANNING_ID).remove()
    assert "".join(other.text for other in document.paragraphs) == words  # its text stays

    if delete is _run_remove:
        target.runs[-1].remove()
    else:
        delete(document, target)

    begins, ends = _field_marks(document)
    assert SPANNING_ID not in begins + ends and sorted(begins) == sorted(ends)
    assert len(document.paragraphs) == (count - 1 if delete in PARAGRAPH_REMOVALS else count)
    assert validate_package(document.to_bytes()).ok


def test_the_paragraphs_between_a_fields_ends_and_whole_fields_are_deleted() -> None:
    document = _open(SPANNING_FIELD)
    paragraphs = document.paragraphs
    marks = _field_marks(document)

    for paragraph in (paragraphs[4], paragraphs[3]):  # between the begin and the end
        paragraph.remove()
    assert _field_marks(document) == marks

    for paragraph in (paragraphs[9], paragraphs[6]):  # each holds a field's begin and its end
        paragraph.remove()
    begins, ends = _field_marks(document)
    assert sorted(begins) == sorted(ends) and SPANNING_ID in begins and len(begins) == len(marks[0]) - 2
    assert validate_package(document.to_bytes()).ok
    reopened = HwpxDocument.open(document.to_bytes())
    assert [field.has_end for field in reopened.fields.all if field.field_id == SPANNING_ID] == [True]


def test_the_content_of_a_paragraph_holding_a_whole_field_is_cleared() -> None:
    document = _open(SPANNING_FIELD)
    marks = _field_marks(document)

    document.paragraphs[9].clear_content()

    begins, ends = _field_marks(document)
    assert sorted(begins) == sorted(ends) and len(begins) == len(marks[0]) - 1
    assert document.paragraphs[9].text == ""


@pytest.mark.parametrize("paragraph", [0, 4])
@pytest.mark.parametrize("take_out", [lambda paragraph: paragraph.remove(), lambda paragraph: paragraph.clear_content()],
                         ids=["remove", "clear_content"])
def test_the_paragraph_that_starts_a_section_keeps_its_settings_when_its_field_refuses(
    paragraph: int, take_out: Callable[[Any], None]
) -> None:
    document = _open(SEOUL)
    before = document.to_bytes()
    assert document.sections[0].paragraphs[0].element.find(f"{HP}run/{HP}secPr") is not None

    with pytest.raises(HwpxValueError) as refused:
        take_out(document.sections[0].paragraphs[paragraph])

    assert refused.value.code == "paragraph-range-splits-field"
    assert document.to_bytes() == before  # the section's settings did not move either


def test_the_first_paragraph_of_a_table_of_contents_goes_once_the_table_is_removed() -> None:
    """Hancom's table of contents is one field from its first paragraph to its last."""

    document = _open(TABLE_OF_CONTENTS)
    before = document.to_bytes()

    with pytest.raises(HwpxValueError) as refused:
        document.sections[0].paragraphs[0].remove()

    assert refused.value.code == "paragraph-range-splits-field"
    assert refused.value.context["type"] == "TABLEOFCONTENTS" and refused.value.context["holds"] == "begin"
    assert "tables_of_contents" in (refused.value.suggestion or "")
    assert document.to_bytes() == before

    document.sections[0].paragraphs[2].remove()  # an entry between the two ends goes as before
    for table in document.refs.tables_of_contents:
        table.remove()
    document.sections[0].paragraphs[0].remove()

    begins, ends = _field_marks(document)
    assert refused.value.context["field"] not in begins + ends and sorted(begins) == sorted(ends)
    assert validate_package(document.to_bytes()).ok


def test_an_end_left_alone_before_can_be_deleted() -> None:
    document = _open(SPANNING_FIELD)
    paragraphs = document.paragraphs
    begin_holder = paragraphs[2].element
    begin_holder.getparent().remove(begin_holder)  # a file an earlier version wrote: the end stands alone
    assert _field_marks(document)[1].count(SPANNING_ID) == 1 and SPANNING_ID not in _field_marks(document)[0]

    paragraphs[5].remove()  # takes the lone end out: nothing of the field is left behind

    begins, ends = _field_marks(document)
    assert SPANNING_ID not in begins + ends


def test_the_refusals_a_paragraph_already_had_come_first() -> None:
    """The last paragraph of a cell is refused as the last paragraph, with the code 7.0.0 gave, also when
    it holds one end of a field."""

    document = HwpxDocument.new()
    host = document.sections[0].add_paragraph("host")
    cell = host.add_table(1, 1).cell(0, 0)
    only = cell.paragraphs[0]
    only.add_hyperlink("https://example.org", "link")
    after = document.sections[0].add_paragraph("after")
    after.element.append(only.runs[-1].element)  # the link's end now stands in a body paragraph
    document.sections[0].mark_dirty()

    with pytest.raises(HwpxValueError) as refused:
        only.remove()

    assert refused.value.code == "paragraph-remove-last"


# -- a field in one paragraph: as before ---------------------------------------------------------------


def _link_document() -> tuple[HwpxDocument, Any]:
    document = HwpxDocument.new(seed=7, now=NOW)
    paragraph = document.sections[0].add_paragraph("keep")
    paragraph.add_hyperlink("https://example.org", "link")
    return document, paragraph


@pytest.mark.parametrize("order", [lambda runs: runs, lambda runs: runs[::-1]], ids=["begin first", "end first"])
def test_the_runs_of_a_hyperlink_are_removed_one_by_one(order: Callable[[list[Any]], list[Any]]) -> None:
    """Each ``run.remove()`` leaves one end of the link for a moment, in the paragraph being edited: that
    is not half a field in another paragraph and goes as it did in 7.0.0."""

    document, paragraph = _link_document()
    by_hand, other = _link_document()
    assert document.to_bytes() == by_hand.to_bytes()  # the same document twice

    for run in order(list(paragraph.runs[-3:])):  # the begin, the label, the end
        run.remove()
    for run in order(list(other.runs[-3:])):  # what run.remove() did to the tree in 7.0.0
        other.element.remove(run.element)
    other.section.mark_dirty()

    assert paragraph.text == "keep"
    assert _field_marks(document) == ([], [])
    data = document.to_bytes()
    assert validate_package(data).ok
    assert data == by_hand.to_bytes()


def test_a_run_holding_a_whole_field_is_removed() -> None:
    document = _open(SPANNING_FIELD)
    marks = _field_marks(document)

    _run_holding_the_mark(document.paragraphs[9]).remove()

    begins, ends = _field_marks(document)
    assert sorted(begins) == sorted(ends) and len(begins) == len(marks[0]) - 1


def test_a_field_in_one_paragraph_is_not_asked_about_a_copy_with_its_id() -> None:
    """Two paragraphs each holding a whole field with one id (a copy an earlier version made kept the id):
    the end in the paragraph being edited is the one that counts."""

    from copy import deepcopy

    document, paragraph = _link_document()
    paragraph.element.addnext(deepcopy(paragraph.element))
    document.sections[0].mark_dirty()
    begins, ends = _field_marks(document)
    assert len(begins) == len(ends) == 2 and len(set(begins + ends)) == 1

    for run in paragraph.runs[-3:]:
        run.remove()

    assert paragraph.text == "keep"
    assert _field_marks(document) == (begins[:1], ends[:1])  # the copy's field is whole


def test_a_field_across_paragraphs_is_refused_also_when_its_id_repeats() -> None:
    from copy import deepcopy

    document = _open(SPANNING_FIELD)
    paragraphs = document.paragraphs
    for paragraph in paragraphs[2:6][::-1]:  # the field from paragraph 2 to 5 once more, after paragraph 5
        paragraphs[5].element.addnext(deepcopy(paragraph.element))
    document.sections[0].mark_dirty()
    begins, ends = _field_marks(document)
    assert begins.count(SPANNING_ID) == ends.count(SPANNING_ID) == 2
    before = document.to_bytes()

    for index in (2, 5, 6, 9):
        with pytest.raises(HwpxValueError) as refused:
            document.paragraphs[index].remove()
        assert refused.value.code == "paragraph-range-splits-field"
    assert document.to_bytes() == before


# -- which paragraph an end is in: the nearest one ----------------------------------------------------


def _cell_document() -> tuple[HwpxDocument, Any, Any]:
    """A body paragraph holding a 1x1 table whose cell holds two paragraphs: a hyperlink in the first."""

    document = HwpxDocument.new()
    host = document.sections[0].add_paragraph("host")
    cell = host.add_table(1, 1).cell(0, 0)
    first = cell.paragraphs[0]
    first.text = "in the cell"
    first.add_hyperlink("https://example.org", "link")
    cell.add_paragraph("second")
    return document, host, cell


def test_a_field_in_a_cells_paragraph_is_in_that_paragraph() -> None:
    document, host, cell = _cell_document()
    first = cell.paragraphs[0]

    for run in first.runs[-3:]:  # both ends in the cell's paragraph: as in a body paragraph
        run.remove()

    assert first.text == "in the cell" and _field_marks(document) == ([], [])
    assert validate_package(document.to_bytes()).ok


def test_a_paragraph_holding_a_table_goes_with_the_fields_in_its_cells() -> None:
    document, host, cell = _cell_document()
    second = cell.paragraphs[1]
    second.element.append(cell.paragraphs[0].runs[-1].element)  # the link now ends in the cell's second paragraph
    document.sections[0].mark_dirty()

    host.remove()  # both ends go

    assert _field_marks(document) == ([], [])
    assert validate_package(document.to_bytes()).ok


@pytest.mark.parametrize("take_out", [
    lambda first, second: first.remove(),
    lambda first, second: second.remove(),
    lambda first, second: _run_holding_the_mark(first).remove(),
    lambda first, second: _run_holding_the_mark(second).remove(),
    lambda first, second: first.clear_content(),
    lambda first, second: second.clear_content(),
], ids=["remove begin", "remove end", "run of begin", "run of end", "clear begin", "clear end"])
def test_two_paragraphs_of_one_cell_are_different_paragraphs(take_out: Callable[[Any, Any], None]) -> None:
    """Both ends stand under the paragraph holding the table, and each in a paragraph of its own: taking
    one cell paragraph out would leave the other end alone in the other."""

    document, host, cell = _cell_document()
    first, second = cell.paragraphs
    second.element.append(first.runs[-1].element)  # the link now ends in the cell's second paragraph
    document.sections[0].mark_dirty()
    marks = _field_marks(document)
    before = document.to_bytes()

    with pytest.raises(HwpxValueError) as refused:
        take_out(first, second)

    assert refused.value.code == "paragraph-range-splits-field"
    assert _field_marks(document) == marks and document.to_bytes() == before


def test_a_cells_paragraph_and_the_paragraph_holding_the_table_are_different_paragraphs() -> None:
    """A field beginning in the paragraph that holds a table and ending in a paragraph of its cell: the
    run of the begin alone is refused, the paragraph (begin, table and end) goes whole."""

    document = HwpxDocument.new()
    host = document.sections[0].add_paragraph("host")
    host.add_hyperlink("https://example.org", "link")
    end_run = host.runs[-1].element
    cell = host.add_table(1, 1).cell(0, 0)
    cell.paragraphs[0].element.append(end_run)  # the link begun in host now ends in the cell
    document.sections[0].mark_dirty()
    marks = _field_marks(document)
    assert len(marks[0]) == len(marks[1]) == 1
    before = document.to_bytes()

    for take_out in (lambda: _run_holding_the_mark(host).remove(), lambda: cell.paragraphs[0].clear_content()):
        with pytest.raises(HwpxValueError) as refused:
            take_out()
        assert refused.value.code == "paragraph-range-splits-field"
        assert document.to_bytes() == before

    host.clear_content()  # the begin and the table holding the end go together

    assert _field_marks(document) == ([], [])
    assert validate_package(document.to_bytes()).ok


# -- a model section over xml.etree elements -----------------------------------------------------------


def _plain_section() -> tuple[Any, list[Any]]:
    """Three paragraphs over ``xml.etree`` elements (no way up the tree): a field that begins in the
    first and ends in the second, and a whole field in the third."""

    import xml.etree.ElementTree as ET

    from hwpx.model import Section
    from hwpx.oxml.namespaces import HS

    root = ET.Element(HS + "sec")
    for marks in ([("fieldBegin", "id", "1")], [("fieldEnd", "beginIDRef", "1")],
                  [("fieldBegin", "id", "2"), ("fieldEnd", "beginIDRef", "2")]):
        paragraph = ET.SubElement(root, HP + "p")
        for name, attribute, value in marks:
            ET.SubElement(ET.SubElement(ET.SubElement(paragraph, HP + "run"), HP + "ctrl"), HP + name, {attribute: value})
        ET.SubElement(ET.SubElement(paragraph, HP + "run"), HP + "t").text = "text"
    section = Section("section0.xml", root)
    return section, list(root)


def test_a_plain_elementtree_section_refuses_the_same_way() -> None:
    section, elements = _plain_section()

    for paragraph in section.paragraphs[:2]:
        with pytest.raises(HwpxValueError) as refused:
            paragraph.remove()
        assert refused.value.code == "paragraph-range-splits-field" and refused.value.context["field"] == "1"
        with pytest.raises(HwpxValueError) as refused:
            paragraph.runs[0].remove()
        assert refused.value.code == "paragraph-range-splits-field"
    assert list(section.element) == elements and not section.dirty

    whole = section.paragraphs[2]
    whole.runs[0].remove()  # the begin of a field ending in this paragraph
    whole.remove()

    assert list(section.element) == elements[:2]
