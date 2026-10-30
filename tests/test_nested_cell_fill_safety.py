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


@pytest.mark.parametrize("text", ["replacement", "", "outer:1:1", "x" * 200])
@pytest.mark.parametrize("fit_max_lines", [None, 1])
def test_nested_parent_refuses_before_any_text_cache_or_font_edit(text, fit_max_lines):
    source = _source(metadata_first=True)
    result = _fill(source, 0, 1, 1, text, fit_max_lines=fit_max_lines)
    assert result.data == source and result.byte_identical and not result.changed_parts
    assert not result.applied and len(result.skipped) == 1
    assert "nested table" in result.skipped[0].reason


def test_explicit_inner_table_and_unrelated_outer_cell_still_work_at_three_levels():
    source = _source(depth=3)
    result = fill_cells(source, [
        {"table_index": 0, "row": 1, "col": 1, "text": "unsafe parent"},
        {"table_index": 0, "row": 2, "col": 2, "text": "outer safe"},
        {"table_index": 1, "row": 0, "col": 0, "text": "inner safe"},
    ])
    assert len(result.applied) == 2 and len(result.skipped) == 1
    with HwpxDocument.open(result.data) as after:
        assert after.tables[0].cell(2, 2).text == "outer safe"
        inner = after.tables[0].cell(1, 1).paragraphs[0].tables[0]
        assert inner.cell(0, 0).text == "inner safe"
    assert _tables(result.data)[2] == _tables(source)[2]


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
