# SPDX-License-Identifier: Apache-2.0
"""Byte fills never confuse a table's own cell metadata with nested cells."""
from __future__ import annotations

import io
from pathlib import Path
from zipfile import ZipFile

import pytest
from lxml import etree

from hwpx.document import HwpxDocument
from hwpx.table_patch import build_grid, fill_cells, iter_table_spans, section_parts

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _source(*, prefix="hp", merged=False, metadata_first=False, depth=2):
    document = HwpxDocument.new()
    outer = document.add_table(3, 3)
    for row in range(3):
        for col in range(3):
            outer.cell(row, col).text = f"outer:{row}:{col}"
    if merged:
        area = {"horizontal": "B2:C2", "vertical": "B2:B3", "both": "B2:C3"}.get(merged, "B2:C2")
        document.tables.merge_cells(outer, area)
    parent = outer.cell(1, 1)
    inner = parent.paragraphs[0].add_table(2, 2)
    for row in range(2):
        for col in range(2):
            inner.cell(row, col).text = f"inner:{row}:{col}"
    if depth == 3:
        deepest = inner.cell(1, 1).paragraphs[0].add_table(1, 1)
        deepest.cell(0, 0).text = "deepest"
    if metadata_first:
        for name in ("cellSpan", "cellAddr"):
            element = parent.element.find(HP + name)
            parent.element.remove(element)
            parent.element.insert(0, element)
    data = document.to_bytes()
    if prefix == "hp":
        return data
    result = io.BytesIO()
    with ZipFile(io.BytesIO(data)) as source, ZipFile(result, "w") as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename.endswith((".xml", ".hpf")):
                payload = payload.replace(b"hp:", prefix.encode() + b":").replace(b"xmlns:hp=", b"xmlns:" + prefix.encode() + b"=")
            target.writestr(info, payload)
    return result.getvalue()


def _tables(data):
    section = section_parts(data)["Contents/section0.xml"]
    return [section[start:end] for start, end in iter_table_spans(section)]


def _fill(source, table, row, col, text="replacement", **kwargs):
    return fill_cells(source, [{"table_index": table, "row": row, "col": col, "text": text}], **kwargs)


@pytest.mark.parametrize("prefix", ["hp", "q"])
@pytest.mark.parametrize("merged", [False, "horizontal", "vertical", "both"])
@pytest.mark.parametrize("metadata_first", [False, True])
def test_outer_coordinates_and_spans_belong_to_the_outer_cell(prefix, merged, metadata_first):
    source = _source(prefix=prefix, merged=merged, metadata_first=metadata_first)
    grid, report = build_grid(_tables(source)[0])
    assert report.ok, report.issues
    assert (grid[1, 1].row, grid[1, 1].col) == (1, 1)
    assert grid[1, 1].col_span == (2 if merged in ("horizontal", "both") else 1)
    assert grid[1, 1].row_span == (2 if merged in ("vertical", "both") else 1)
    result = _fill(source, 0, 0, 0)
    assert len(result.applied) == 1 and not result.skipped
    assert result.applied[0].original_text == "outer:0:0"
    with HwpxDocument.open(result.data) as after:
        assert after.tables[0].cell(0, 0).text == "replacement"
    assert _tables(result.data)[1:] == _tables(source)[1:]


def _nested_spans(data):
    """Every table except the outermost one, as bytes (the parts a parent fill must keep)."""
    return _tables(data)[1:]


@pytest.mark.parametrize("text", ["replacement", "", "x" * 200, "two\nlines"])
@pytest.mark.parametrize("fit_max_lines", [None, 1])
def test_nested_parent_fill_replaces_own_text_and_keeps_nested_table_bytes(text, fit_max_lines):
    source = _source(metadata_first=True)
    result = _fill(source, 0, 1, 1, text, fit_max_lines=fit_max_lines)
    assert len(result.applied) == 1 and not result.skipped
    assert result.applied[0].original_text == "outer:1:1"
    assert _nested_spans(result.data) == _nested_spans(source)
    with HwpxDocument.open(result.data) as after:
        parent = after.tables[0].cell(1, 1)
        assert parent.text == text
        inner = parent.paragraphs[0].tables[0]
        assert [inner.cell(r, c).text for r in range(2) for c in range(2)] == [f"inner:{r}:{c}" for r in range(2) for c in range(2)]
        assert after.tables[0].cell(0, 0).text == "outer:0:0"


def test_nested_parent_fill_with_its_current_text_changes_nothing():
    source = _source()
    result = _fill(source, 0, 1, 1, "outer:1:1")
    assert result.data == source and not result.changed_parts


def _reshape_parent(data, layout):
    """Move the parent's own text out of the table paragraph: above/below it, or drop it."""
    output = io.BytesIO()
    with ZipFile(io.BytesIO(data)) as original, ZipFile(output, "w") as target:
        for info in original.infolist():
            payload = original.read(info.filename)
            if info.filename == "Contents/section0.xml":
                section = etree.fromstring(payload)
                outer = next(section.iter(HP + "tbl"))
                parent = outer.findall(HP + "tr")[1].findall(HP + "tc")[1]
                sub = parent.find(HP + "subList")
                holder = sub.find(HP + "p")
                own = [t for t in holder.iter(HP + "t") if next(t.iterancestors(HP + "tbl")) is outer]
                if layout in ("above", "below", "both"):
                    for position in (("above",) if layout == "above" else ("below",) if layout == "below" else ("above", "below")):
                        text_para = etree.fromstring(etree.tostring(holder))
                        for run in text_para.findall(HP + "run"):
                            for child in list(run):
                                if child.tag != HP + "t":
                                    run.remove(child)
                        for t in text_para.iter(HP + "t"):
                            t.text = f"{position} text"
                        sub.insert(list(sub).index(holder) + (position == "below"), text_para)
                for t in own:
                    t.text = None
                payload = etree.tostring(section)
            target.writestr(info, payload)
    return output.getvalue()


@pytest.mark.parametrize("layout", ["above", "below", "both", "table-only"])
@pytest.mark.parametrize("text", ["new", "line1\nline2\nline3"])
def test_nested_parent_fill_layouts(layout, text):
    source = _reshape_parent(_source(), layout)
    before = section_parts(source)["Contents/section0.xml"]
    result = _fill(source, 0, 1, 1, text)
    assert len(result.applied) == 1 and not result.skipped
    assert _nested_spans(result.data) == _nested_spans(source)
    with HwpxDocument.open(result.data) as after:
        parent = after.tables[0].cell(1, 1)
        own = [p.text for p in parent.paragraphs if not p.tables or p.text]
        assert "\n".join(own).rstrip("\n") == text  # emptied paragraphs stay, as in flat cells
        holder = next(p for p in parent.paragraphs if p.tables)
        assert holder.tables[0].cell(1, 1).text == "inner:1:1"
    after_section = section_parts(result.data)["Contents/section0.xml"]
    added = after_section.count(b"<hp:p ") - before.count(b"<hp:p ")
    assert added == (1 if layout == "table-only" else 0)


def test_table_only_parent_fill_puts_the_text_above_the_table_in_the_holder_shape():
    source = _reshape_parent(_source(), "table-only")
    result = _fill(source, 0, 1, 1, "heading")
    with HwpxDocument.open(result.data) as after:
        paragraphs = after.tables[0].cell(1, 1).paragraphs
        assert [p.text for p in paragraphs][0] == "heading" and paragraphs[1].tables
        assert paragraphs[0].element.get("paraPrIDRef") == paragraphs[1].element.get("paraPrIDRef")
    assert _fill(source, 0, 1, 1, "").data == source


def test_parent_inner_and_outer_fills_combine_at_three_levels():
    source = _source(depth=3)
    result = fill_cells(source, [
        {"table_index": 0, "row": 1, "col": 1, "text": "parent new"},
        {"table_index": 0, "row": 2, "col": 2, "text": "outer safe"},
        {"table_index": 1, "row": 0, "col": 0, "text": "inner safe"},
        {"table_index": 1, "row": 1, "col": 1, "text": "inner parent"},
    ])
    assert len(result.applied) == 4 and not result.skipped
    with HwpxDocument.open(result.data) as after:
        parent = after.tables[0].cell(1, 1)
        assert parent.text == "parent new"
        assert after.tables[0].cell(2, 2).text == "outer safe"
        inner = parent.paragraphs[0].tables[0]
        assert inner.cell(0, 0).text == "inner safe"
        assert inner.cell(1, 1).text == "inner parent"
        assert inner.cell(0, 1).text == "inner:0:1"
    assert _tables(result.data)[2] == _tables(source)[2]


def test_lines_beyond_the_cell_paragraphs_become_line_breaks():
    document = HwpxDocument.new()
    document.add_table(1, 1).cell(0, 0).text = "x"
    result = _fill(document.to_bytes(), 0, 0, 0, "a\nb\nc")
    assert len(result.applied) == 1
    with HwpxDocument.open(result.data) as after:
        assert after.tables[0].cell(0, 0).text == "a\nb\nc"
    assert b"<hp:lineBreak/>" in section_parts(result.data)["Contents/section0.xml"]


@pytest.mark.parametrize("kind", ["overlap", "incomplete", "missing-metadata"])
def test_invalid_grid_never_reports_a_successful_fill(kind):
    output = io.BytesIO()
    with ZipFile(io.BytesIO(_source())) as original, ZipFile(output, "w") as target:
        for info in original.infolist():
            payload = original.read(info.filename)
            if info.filename == "Contents/section0.xml":
                section = etree.fromstring(payload)
                outer = next(section.iter(HP + "tbl"))
                if kind == "overlap":
                    outer.findall(HP + "tr")[0].findall(HP + "tc")[1].find(HP + "cellAddr").set("colAddr", "0")
                elif kind == "incomplete":
                    outer.set("colCnt", "4")
                else:
                    parent = outer.findall(HP + "tr")[1].findall(HP + "tc")[1]
                    parent.remove(parent.find(HP + "cellAddr"))
                payload = etree.tostring(section)
            target.writestr(info, payload)
    source = output.getvalue()
    assert not build_grid(_tables(source)[0])[1].ok
    result = _fill(source, 0, 0, 0)
    assert result.data == source and not result.applied and len(result.skipped) == 1
    assert "grid is invalid" in result.skipped[0].reason


def test_real_hancom_nested_table_keeps_all_non_target_table_bytes():
    path = Path(__file__).parent / "fixtures/hancom_saved/pages_nested_table_rows_a_cut_above_the_page_foot.hwpx"
    source = path.read_bytes()
    result = _fill(source, 0, 0, 0, "external safe")
    assert len(result.applied) == 1 and not result.skipped
    with HwpxDocument.open(result.data) as after:
        assert after.tables[0].cell(0, 0).text == "external safe"
    assert _tables(result.data)[1:] == _tables(source)[1:]
    with ZipFile(io.BytesIO(source)) as before, ZipFile(io.BytesIO(result.data)) as after:
        assert all(before.read(name) == after.read(name) for name in before.namelist() if name != "Contents/section0.xml")


def test_real_hancom_parent_cell_keeps_nested_bytes_and_caches():
    path = Path(__file__).parent / "fixtures/hancom_saved/pages_nested_table_rows_a_cut_above_the_page_foot.hwpx"
    source = path.read_bytes()
    result = _fill(source, 0, 0, 1, "filled parent", fit_max_lines=1)
    assert len(result.applied) == 1 and not result.skipped
    before, after = _tables(source), _tables(result.data)
    assert after[1:] == before[1:]
    assert after[0].count(b"linesegarray") < before[0].count(b"linesegarray")
    nested = before[1]
    assert nested in after[0]
    with HwpxDocument.open(result.data) as document:
        assert document.tables[0].cell(0, 1).text.rstrip("\n") == "filled parent"
    with ZipFile(io.BytesIO(source)) as old, ZipFile(io.BytesIO(result.data)) as new:
        changed = {name for name in old.namelist() if old.read(name) != new.read(name)}
    assert changed <= {"Contents/section0.xml", "Contents/header.xml"}


_OBJECT_BODY = (
    '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="TOP">'
    '<hp:p paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0" id="77">'
    '<hp:run charPrIDRef="0"><hp:t>object text</hp:t></hp:run></hp:p></hp:subList>'
)
_OBJECTS = {
    "footnote": f'<hp:ctrl><hp:footNote number="1" instId="77">{_OBJECT_BODY}</hp:footNote></hp:ctrl>',
    "text-box": f'<hp:rect id="78"><hp:drawText lastWidth="1000" name="" editable="0">{_OBJECT_BODY}</hp:drawText></hp:rect>',
}


def _object_source(kind, *, plain_paragraph_first):
    document = HwpxDocument.new()
    table = document.add_table(1, 2)
    table.cell(0, 0).text = "before"
    table.cell(0, 1).text = "other"
    data = document.to_bytes()
    holder = f"<hp:t>before</hp:t>{_OBJECTS[kind]}<hp:t>after</hp:t></hp:run></hp:p>"
    if plain_paragraph_first:
        holder = (
            '<hp:t>first</hp:t></hp:run></hp:p>'
            '<hp:p paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0" id="76">'
            '<hp:run charPrIDRef="0">' + holder
        )
    result = io.BytesIO()
    with ZipFile(io.BytesIO(data)) as source, ZipFile(result, "w") as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "Contents/section0.xml":
                payload = payload.replace(b"<hp:t>before</hp:t></hp:run></hp:p>", holder.encode(), 1)
            target.writestr(info, payload)
    return result.getvalue()


def _own_texts(data):
    section = etree.fromstring(section_parts(data)["Contents/section0.xml"])
    cell = next(iter(section.iter(HP + "tc")))
    return ["".join(t.itertext()) for p in cell.find(HP + "subList").findall(HP + "p") for run in p.findall(HP + "run")
            for t in run.findall(HP + "t")]


@pytest.mark.parametrize("kind", sorted(_OBJECTS))
@pytest.mark.parametrize("plain_paragraph_first", [False, True])
@pytest.mark.parametrize("text", ["replacement", "two\nlines"])
def test_an_object_with_its_own_paragraphs_keeps_them_and_its_cell_text_is_replaced(kind, plain_paragraph_first, text):
    # The object's own </hp:p> must not end the holding paragraph early: text
    # after the object is the cell's own and goes; the object's text stays.
    source = _object_source(kind, plain_paragraph_first=plain_paragraph_first)
    result = _fill(source, 0, 0, 0, text)
    assert len(result.applied) == 1 and not result.skipped
    assert _OBJECT_BODY.encode() in section_parts(result.data)["Contents/section0.xml"]
    assert "".join(_own_texts(result.data)) == text.replace("\n", "")
