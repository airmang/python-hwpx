# SPDX-License-Identifier: Apache-2.0
"""asks4: public reads and writes the automation package did through ``.element``.

- wrapper equality: two wrappers of the same XML element are equal and hash alike;
- ``TableCell.border_fill_id_ref`` is settable (checked id, only that cell's reference changes);
- ``Table.repeat_header`` is settable (only ``repeatHeader``; the title cells stay);
- ``FormField.filled`` reads Hancom's ``dirty`` mark.

Each write is checked against the repository's Hancom-saved fixtures: the part it edits differs from
the input only where the written attribute is, every other part keeps its bytes.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxError

HANCOM = Path(__file__).parent / "fixtures" / "hancom_saved"
_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _parts(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _changed_parts(before: bytes, after: bytes) -> set[str]:
    old, new = _parts(before), _parts(after)
    return {name for name in old.keys() | new.keys() if old.get(name) != new.get(name)}


# -- wrapper equality ----------------------------------------------------------------------------


def test_wrappers_of_one_element_are_equal_and_hash_alike() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("가")
    table = doc.add_table(2, 2)
    doc.notes.add_footnote("각주", paragraph=paragraph)
    memo = doc.notes.add_memo("메모", paragraph=paragraph)
    shape = doc.paragraphs[-1].add_rectangle(width=2000, height=1000)

    holder = table.paragraph
    again = doc.paragraphs[doc.paragraphs.index(holder)]
    pairs = [
        (paragraph, doc.paragraphs[doc.paragraphs.index(paragraph)]),
        (paragraph.runs[0], paragraph.runs[0]),
        (table, again.tables[0]),
        (table.cell(0, 1), table.cell(0, 1)),
        (table.rows[1], table.rows[1]),
        (paragraph.footnotes[0], paragraph.footnotes[0]),
        (memo, doc.notes.memos[0]),
        (shape, doc.paragraphs[-1].shapes[0]),
    ]
    for one, other in pairs:
        assert one is not other or isinstance(one, type(other))
        assert one == other and hash(one) == hash(other), type(one).__name__
        assert {one: 1}[other] == 1
        assert len({one, other}) == 1


def test_wrappers_of_different_elements_differ() -> None:
    doc = HwpxDocument.new()
    first, second = doc.add_paragraph("가"), doc.add_paragraph("가")
    table = doc.add_table(2, 2)
    assert first != second and len({first, second}) == 2
    assert table.cell(0, 0) != table.cell(0, 1)
    assert first != first.element and first != "가" and first != None  # noqa: E711
    assert doc.paragraphs.index(second) == doc.paragraphs.index(first) + 1


def test_a_paragraph_index_and_dict_key_without_element() -> None:
    """What ops_services/memo_style.py built from ``id(paragraph.element)``."""

    doc = HwpxDocument.open(HANCOM / "memos_in_fields.hwpx")
    index_of = {paragraph: index for index, paragraph in enumerate(doc.paragraphs)}
    runs = doc.text.find_runs()
    assert runs and all(index_of[run.paragraph] == doc.paragraphs.index(run.paragraph) for run in runs
                        if run.paragraph in index_of)


def test_paragraph_id_reads_the_written_id() -> None:
    doc = HwpxDocument.open(HANCOM / "memos_in_fields.hwpx")
    for paragraph in doc.paragraphs:
        assert paragraph.id == paragraph.element.get("id")
    with pytest.raises(AttributeError):
        doc.paragraphs[0].id = "1"  # type: ignore[misc]


@pytest.mark.parametrize("name", ["page_break", "column_break"])
def test_a_break_before_a_paragraph_drops_its_line_cache(name: str) -> None:
    doc = HwpxDocument.open(HANCOM / "pages_anchor_lines_past_a_moved_table.hwpx")
    cached = [p for p in doc.paragraphs if p.text.strip() and not p.tables
              and p.element.find(f"{_HP}linesegarray") is not None]
    target, other = cached[3], cached[4]
    before = doc.to_bytes()
    setattr(target, name, False)  # unchanged: nothing is written
    assert doc.to_bytes() == before
    setattr(target, name, True)
    assert getattr(target, name) is True
    assert target.element.find(f"{_HP}linesegarray") is None
    assert other.element.find(f"{_HP}linesegarray") is not None


# -- TableCell.border_fill_id_ref ----------------------------------------------------------------


def test_cell_border_fill_id_ref_writes_only_that_cell() -> None:
    source = (HANCOM / "cell_border_2x3_base.hwpx").read_bytes()
    doc = HwpxDocument.open(source)
    table = doc.tables[0]
    before = doc.to_bytes()
    fill = doc.styles.ensure_border_fill(border_color="#000000", fill_color="#FFF2CC")
    header_after_ensure = _parts(doc.to_bytes())["Contents/header.xml"]
    old = table.cell(1, 2).border_fill_id_ref
    others = {(r, c): table.cell(r, c).border_fill_id_ref for r in range(2) for c in range(3)}

    table.cell(1, 2).border_fill_id_ref = fill

    after = doc.to_bytes()
    assert table.cell(1, 2).border_fill_id_ref == str(fill) != old
    assert {key: table.cell(*key).border_fill_id_ref for key in others if key != (1, 2)} == {
        key: value for key, value in others.items() if key != (1, 2)}
    assert _changed_parts(before, after) <= {"Contents/section0.xml", "Contents/header.xml"}
    assert _parts(after)["Contents/header.xml"] == header_after_ensure
    # The cells keep their line caches. The paragraph holding the table loses its own at the save, as
    # after any change inside a table read from a file (the save's guard against a cache whose
    # paragraph changed since it was read); Hancom lays that one line out again.
    reopened = HwpxDocument.open(after)
    cell_caches = [p.element.find(f"{_HP}linesegarray") is not None
                   for row in reopened.tables[0].rows for cell in row.cells for p in cell.paragraphs]
    assert all(cell_caches)
    old_xml = _parts(before)["Contents/section0.xml"].decode()
    new_xml = _parts(after)["Contents/section0.xml"].decode()
    assert new_xml.count(f'borderFillIDRef="{fill}"') == old_xml.count(f'borderFillIDRef="{fill}"') + 1


def test_cell_border_fill_id_ref_refuses_an_unknown_id_before_changing_anything() -> None:
    doc = HwpxDocument.open(HANCOM / "cell_border_2x3_base.hwpx")
    before = doc.to_bytes()
    cell = doc.tables[0].cell(0, 0)
    for value in ("999", 999, True, None, 1.0):
        with pytest.raises(HwpxError) as refused:
            cell.border_fill_id_ref = value  # type: ignore[assignment]
        assert refused.value.code == "table-border-fill-not-found"
    assert doc.to_bytes() == before


def test_cell_border_fill_id_ref_takes_an_int_and_survives_a_save() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(2, 2)
    fill = doc.styles.ensure_border_fill(border_color="#FF0000")
    table.cell(0, 0).border_fill_id_ref = int(fill)
    again = HwpxDocument.open(doc.to_bytes())
    assert again.tables[0].cell(0, 0).border_fill_id_ref == str(fill)
    assert again.tables[0].cell(0, 0).border_fill is not None
    assert again.tables[0].cell(0, 1).border_fill_id_ref != str(fill)


# -- Table.repeat_header -------------------------------------------------------------------------


def test_repeat_header_writes_only_the_flag_in_hancoms_form() -> None:
    source = (HANCOM / "pages_table_flow_repeat_header.hwpx").read_bytes()
    doc = HwpxDocument.open(source)
    table = doc.tables[0]
    assert table.repeat_header is True
    headers = [cell.is_header for row in table.rows for cell in row.cells]
    before = doc.to_bytes()

    table.repeat_header = False
    off = doc.to_bytes()
    assert table.repeat_header is False
    assert [cell.is_header for row in table.rows for cell in row.cells] == headers
    assert _changed_parts(before, off) == {"Contents/section0.xml"}
    old_xml = _parts(before)["Contents/section0.xml"].decode()
    new_xml = _parts(off)["Contents/section0.xml"].decode()
    assert 'repeatHeader="0"' in new_xml and old_xml.count('repeatHeader="1"') == new_xml.count('repeatHeader="1"') + 1

    table.repeat_header = True  # back to what Hancom wrote: the same "1"
    assert 'repeatHeader="1"' in _parts(doc.to_bytes())["Contents/section0.xml"].decode()


def test_repeat_header_drops_the_holding_paragraphs_cache_only_when_it_changes() -> None:
    doc = HwpxDocument.open(HANCOM / "cell_border_2x3_base.hwpx")
    table = doc.tables[0]
    holder = table.paragraph
    assert holder.element.find("{http://www.hancom.co.kr/hwpml/2011/paragraph}linesegarray") is not None
    before = doc.to_bytes()
    table.repeat_header = True  # already on: nothing changes
    assert doc.to_bytes() == before
    table.repeat_header = False
    assert holder.element.find("{http://www.hancom.co.kr/hwpml/2011/paragraph}linesegarray") is None
    cells_cached = [p.element.find("{http://www.hancom.co.kr/hwpml/2011/paragraph}linesegarray") is not None
                    for row in table.rows for cell in row.cells for p in cell.paragraphs]
    assert all(cells_cached)  # the cells' own lines do not change


def test_repeat_header_keeps_title_cells_unlike_set_header_rows() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(3, 2)
    table.cell(0, 0).is_header = True
    table.repeat_header = True
    assert table.repeat_header and table.cell(0, 0).is_header
    assert table.cell(0, 1).element.get("header") in (None, "0")  # not rewritten
    with pytest.raises(HwpxError) as refused:
        table.repeat_header = "yes"  # type: ignore[assignment]
    assert refused.value.code == "table-header-rows-value"


# -- FormField.filled ----------------------------------------------------------------------------


def test_form_field_filled_reads_hancoms_dirty_mark() -> None:
    saved = HwpxDocument.open(HANCOM / "field_value_shape_saved.hwpx")
    filled = HwpxDocument.open(HANCOM / "field_value_shape_filled.hwpx")
    showing_prompt = [f for f in saved.fields.all if f.field_type == "CLICK_HERE" and f.is_placeholder]
    assert showing_prompt and not any(field.filled for field in showing_prompt)
    assert {field.filled for field in filled.fields.all if field.field_type == "CLICK_HERE"} == {True}
    for field in [*saved.fields.all, *filled.fields.all]:
        assert field.filled == (field.element.get("dirty") == "1")


def test_form_field_filled_turns_on_with_a_fill() -> None:
    doc = HwpxDocument.open(HANCOM / "field_value_shape_saved.hwpx")
    field = next(f for f in doc.fields.all if f.field_type == "CLICK_HERE" and not f.filled)
    assert field.filled is False
    field.value = "채운 값"
    assert field.filled is True
    assert re.search(r'dirty="1"', _parts(doc.to_bytes())["Contents/section0.xml"].decode())
