# SPDX-License-Identifier: Apache-2.0
"""A table cell reports and sets the inner margins Hancom lays it out with."""

from __future__ import annotations

import dataclasses
import io

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.objects import CellMargins
from hwpx.oxml.namespaces import HP


def _cell():
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    return doc, table, table.cell(0, 0)


def _set_box(element, left: int, right: int, top: int, bottom: int) -> None:
    for name, value in (("left", left), ("right", right), ("top", top), ("bottom", bottom)):
        element.set(name, str(value))


def test_a_new_table_cell_reports_the_hancom_default_margins() -> None:
    _, _, cell = _cell()

    assert cell.margins == CellMargins(left=510, right=510, top=141, bottom=141)


def test_a_cell_without_its_own_margin_uses_the_table_margin() -> None:
    _, table, cell = _cell()
    _set_box(table.element.find(f"{HP}inMargin"), 100, 200, 300, 400)
    _set_box(cell.element.find(f"{HP}cellMargin"), 1, 2, 3, 4)

    cell.element.set("hasMargin", "0")
    assert cell.margins == CellMargins(100, 200, 300, 400)
    del cell.element.attrib["hasMargin"]
    assert cell.margins == CellMargins(100, 200, 300, 400)


@pytest.mark.parametrize("flag", ["1", "true"])
def test_a_cell_with_its_own_margin_uses_it(flag: str) -> None:
    _, table, cell = _cell()
    _set_box(table.element.find(f"{HP}inMargin"), 100, 200, 300, 400)
    _set_box(cell.element.find(f"{HP}cellMargin"), 1, 2, 3, 4)
    cell.element.set("hasMargin", flag)

    assert cell.margins == CellMargins(1, 2, 3, 4)


def test_margins_fall_back_to_the_cell_margin_then_to_zero() -> None:
    _, table, cell = _cell()
    table.element.remove(table.element.find(f"{HP}inMargin"))
    _set_box(cell.element.find(f"{HP}cellMargin"), 1, 2, 3, 4)
    assert cell.margins == CellMargins(1, 2, 3, 4)

    cell.element.remove(cell.element.find(f"{HP}cellMargin"))
    assert cell.margins == CellMargins(0, 0, 0, 0)


def test_set_margins_overrides_the_given_sides_of_the_effective_margins() -> None:
    doc, table, cell = _cell()
    _set_box(table.element.find(f"{HP}inMargin"), 100, 200, 300, 400)
    doc.sections[0].reset_dirty()

    result = cell.set_margins(left=0, bottom=50)

    assert result == CellMargins(0, 200, 300, 50)
    assert cell.margins == result
    assert cell.element.get("hasMargin") == "1"
    own = cell.element.find(f"{HP}cellMargin")
    assert {k: own.get(k) for k in ("left", "right", "top", "bottom")} == {
        "left": "0",
        "right": "200",
        "top": "300",
        "bottom": "50",
    }
    assert doc.sections[0].dirty


def test_set_margins_without_arguments_changes_nothing() -> None:
    doc, _, cell = _cell()
    before = doc.to_bytes()
    doc.sections[0].reset_dirty()

    assert cell.set_margins() == CellMargins(510, 510, 141, 141)

    assert cell.element.get("hasMargin") == "0"
    assert not doc.sections[0].dirty
    assert doc.to_bytes() == before


def test_set_margins_creates_the_cell_margin_in_schema_order() -> None:
    _, _, cell = _cell()
    cell.element.remove(cell.element.find(f"{HP}cellMargin"))

    cell.set_margins(top=10)

    names = [child.tag.rsplit("}", 1)[-1] for child in cell.element]
    assert names == ["subList", "cellAddr", "cellSpan", "cellSz", "cellMargin"]
    assert cell.margins == CellMargins(510, 510, 10, 141)


@pytest.mark.parametrize("value", [True, False, -1, 2**31, 1.5, "10"])
def test_set_margins_refuses_a_bad_value_before_changing_anything(value: object) -> None:
    doc, _, cell = _cell()
    before = doc.to_bytes()

    with pytest.raises(HwpxValueError) as caught:
        cell.set_margins(left=10, right=value)  # type: ignore[arg-type]

    assert isinstance(caught.value, ValueError)
    assert caught.value.code == "cell-margin-value"
    assert caught.value.context["side"] == "right"
    assert cell.margins == CellMargins(510, 510, 141, 141)
    assert doc.to_bytes() == before


def _cached(paragraph) -> None:
    paragraph.append(paragraph.makeelement(f"{HP}linesegarray", {}))


def test_set_margins_drops_the_line_layout_of_this_cells_own_paragraphs() -> None:
    _, _, cell = _cell()
    cell.add_paragraph("둘째")
    inner = cell.add_table(1, 1).cell(0, 0)
    own = [p.element for p in cell.paragraphs]
    nested = inner.paragraphs[0].element
    for paragraph in [*own, nested]:
        _cached(paragraph)

    cell.set_margins(left=0)

    assert all(p.find(f"{HP}linesegarray") is None for p in own)
    assert nested.find(f"{HP}linesegarray") is not None


def test_set_margins_keeps_the_line_layout_when_the_margins_stay_the_same() -> None:
    _, _, cell = _cell()
    paragraph = cell.paragraphs[0].element
    _cached(paragraph)

    cell.set_margins()
    cell.set_margins(left=510, top=141)

    assert cell.element.get("hasMargin") == "1"
    assert paragraph.find(f"{HP}linesegarray") is not None


def test_set_margins_survives_save_and_reopen() -> None:
    doc, _, cell = _cell()
    cell.set_margins(left=0, right=0, top=0, bottom=0)

    reopened = HwpxDocument.open(io.BytesIO(doc.to_bytes()))

    assert reopened.tables.all[0].cell(0, 0).margins == CellMargins(0, 0, 0, 0)


def test_cell_margins_is_a_frozen_payload() -> None:
    margins = CellMargins(left=1, right=2, top=3, bottom=4)

    assert margins.to_dict() == {"left": 1, "right": 2, "top": 3, "bottom": 4}
    with pytest.raises(dataclasses.FrozenInstanceError):
        margins.left = 5  # type: ignore[misc]


# --------------------------------------------------------------------------
# Every reader of a cell's inner margins follows the rule ``cell.margins`` does.

_TABLE_MARGIN = (100, 200, 300, 400)
_CELL_MARGIN = (1, 2, 3, 4)


def _cell_with_two_margins(has_margin: str | None):
    doc, table, cell = _cell()
    _set_box(table.element.find(f"{HP}inMargin"), *_TABLE_MARGIN)
    _set_box(cell.element.find(f"{HP}cellMargin"), *_CELL_MARGIN)
    if has_margin is None:
        cell.element.attrib.pop("hasMargin", None)
    else:
        cell.element.set("hasMargin", has_margin)
    return doc, table, cell


_RULE_CASES = [("0", _TABLE_MARGIN), (None, _TABLE_MARGIN), ("1", _CELL_MARGIN)]


@pytest.mark.parametrize(("has_margin", "expected"), _RULE_CASES)
def test_form_fit_reads_the_same_margins_as_cell_margins(has_margin, expected) -> None:
    from hwpx.form_fit.measure import MIN_LINE_WIDTH, resolve_slot_metrics

    doc, _, cell = _cell_with_two_margins(has_margin)
    assert tuple(dataclasses.astuple(cell.margins)) == expected

    slot = resolve_slot_metrics(cell, doc, safety=1.0)
    left, right, top, bottom = expected
    assert slot.available_width == max(cell.width - left - right, MIN_LINE_WIDTH)


@pytest.mark.parametrize(("has_margin", "expected"), _RULE_CASES)
def test_a_nested_table_default_width_uses_the_effective_margins(has_margin, expected) -> None:
    _, _, cell = _cell_with_two_margins(has_margin)
    left, right, _, _ = expected

    assert cell.paragraphs[0]._context_table_width() == cell.width - left - right


@pytest.mark.parametrize(("has_margin", "expected"), _RULE_CASES)
def test_the_table_height_bound_uses_the_effective_margins(has_margin, expected) -> None:
    from hwpx._document.layout import _table_min_height

    doc, table, cell = _cell_with_two_margins(has_margin)
    cell.element.find(f"{HP}cellSz").set("height", "1")
    _, _, top, bottom = expected

    assert _table_min_height(doc, table.element) == 1000 + top + bottom


@pytest.mark.parametrize(("has_margin", "expected"), _RULE_CASES)
def test_the_template_analyzer_reports_the_effective_margins(
    has_margin, expected, tmp_path
) -> None:
    from hwpx.tools.template_analyzer import analyze_template

    doc, _, _ = _cell_with_two_margins(has_margin)
    path = tmp_path / "margins.hwpx"
    doc.save_to_path(path)

    (table,) = analyze_template(path).table_summaries
    assert table.cells[0].margin == dict(zip(("left", "right", "top", "bottom"), expected))


@pytest.mark.parametrize(("has_margin", "expected"), _RULE_CASES)
def test_the_layout_preview_pads_cells_with_the_effective_margins(has_margin, expected) -> None:
    from hwpx.tools.layout_preview import _fmt_mm, _hwp_to_mm, render_layout_preview

    doc, _, _ = _cell_with_two_margins(has_margin)
    buffer = io.BytesIO()
    doc.save_to_stream(buffer)

    left, right, top, bottom = (_fmt_mm(_hwp_to_mm(value)) for value in expected)
    assert f"padding:{top} {right} {bottom} {left}" in render_layout_preview(
        buffer.getvalue()
    ).html.replace(": ", ":")


@pytest.mark.parametrize(("has_margin", "expected"), _RULE_CASES)
def test_the_byte_patch_font_fit_uses_the_effective_margins(has_margin, expected) -> None:
    from hwpx.table_patch import _cell_inner_width, _direct_cells, _iter_table_spans

    doc, _, cell = _cell_with_two_margins(has_margin)
    buffer = io.BytesIO()
    doc.save_to_stream(buffer)
    import zipfile

    section = zipfile.ZipFile(buffer).read("Contents/section0.xml")
    (span,) = _iter_table_spans(section)
    table = section[span[0]:span[1]]
    (only,) = _direct_cells(table)
    left, right, _, _ = expected

    assert _cell_inner_width(table, table[only.start:only.end]) == cell.width - left - right


def _cells(tables):
    for table in tables:
        for row in table.rows:
            for cell in row.cells:
                yield cell
                for paragraph in cell.paragraphs:
                    yield from _cells(paragraph.tables)


def test_hancom_lays_out_hasmargin_off_cells_with_the_table_margin() -> None:
    """Hancom's own line layout of a real document agrees with ``cell.margins``.

    ``seoul_sihaengmun.hwpx`` is a public document saved by Hancom Office
    Hangul 11 (its ``version.xml``), line layout included. Its cells turn ``hasMargin`` off while carrying an ``hp:cellMargin`` different
    from the table's ``hp:inMargin``. The line width Hancom recorded
    (``lineseg@horzsize``) is the cell width minus the table margin, not
    minus the cell's own one.
    """
    from pathlib import Path

    path = Path(__file__).parent / "fixtures" / "m3_gongmun_gold" / "seoul_sihaengmun.hwpx"
    doc = HwpxDocument.open(path)
    checked = 0
    for section in doc.oxml.sections:
        for paragraph in section.paragraphs:
            for cell in _cells(paragraph.tables):
                own = cell.element.find(f"{HP}cellMargin")
                inherited = cell.table.element.find(f"{HP}inMargin")
                if cell.element.get("hasMargin") != "0" or own is None or inherited is None:
                    continue
                if int(own.get("left")) + int(own.get("right")) == int(
                    inherited.get("left")
                ) + int(inherited.get("right")):
                    continue
                segment = cell.element.find(f"{HP}subList/{HP}p/{HP}linesegarray/{HP}lineseg")
                if segment is None or int(segment.get("horzsize")) <= 1440:
                    continue  # Hancom's minimum line width, not the margin, decides
                margins = cell.margins
                assert abs(
                    cell.width - margins.left - margins.right - int(segment.get("horzsize"))
                ) <= 4
                checked += 1
    assert checked >= 40
