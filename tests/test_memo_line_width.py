# SPDX-License-Identifier: Apache-2.0
"""The line width of a memo shape in millimetres (``hh:memoPr@lineWidth``).

``lineWidth`` holds no length but the one-byte line width of the HWP 5.0 memo shape record, the
index into Hancom's sixteen line widths that borders use too (0.1, 0.12, 0.15, 0.2 ... 5.0 mm). The
public corpus has ``1`` (36 memo shapes) and ``3`` (5). ``line_width_mm`` reads and writes it in mm.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.mark.parametrize(
    ("name", "line_width", "mm"),
    [
        ("hwpxlib_corpus/error__20230818__test.hwpx", "1", 0.12),
        ("gui_probes/version_history.hwpx", "1", 0.12),
        ("hwpxlib_corpus/error__20251107__test.hwpx", "3", 0.2),
    ],
)
def test_hangul_saved_memo_shapes_read_in_millimetres(name: str, line_width: str, mm: float) -> None:
    doc = HwpxDocument.open(FIXTURES / name)
    shapes = list(doc.styles.memo_shapes.values())
    assert shapes and {shape.line_width for shape in shapes} == {line_width}
    assert {shape.line_width_mm for shape in shapes} == {mm}


@pytest.mark.parametrize(
    ("mm", "written", "read"),
    [(0.12, "1", 0.12), (0.5, "7", 0.5), (0.45, "7", 0.5), (1, "10", 1.0), (9, "15", 5.0), (0.1, "0", 0.1)],
)
def test_ensure_memo_shape_takes_millimetres(mm: float, written: str, read: float) -> None:
    doc = HwpxDocument.new()
    shape_id = doc.styles.ensure_memo_shape(line_width_mm=mm)
    shape = doc.styles.memo_shape(shape_id)
    assert shape is not None and shape.line_width == written and shape.line_width_mm == read


def test_a_memo_with_a_thick_line_saves_and_reopens() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("메모를 단 문단")
    shape_id = doc.styles.ensure_memo_shape(line_width_mm=0.5, line_color="#C00000")
    doc.notes.add_memo("굵은 선", paragraph=paragraph, memo_shape_id_ref=shape_id)
    data = doc.to_bytes()

    reopened = HwpxDocument.open(data)
    assert reopened.validate().ok
    assert reopened.styles.memo_shape(shape_id).line_width_mm == 0.5
    with zipfile.ZipFile(__import__("io").BytesIO(data)) as archive:
        assert 'lineWidth="7"' in archive.read("Contents/header.xml").decode("utf-8")


def test_the_default_is_still_lineWidth_1() -> None:
    doc = HwpxDocument.new()
    shape = doc.styles.memo_shape(doc.styles.ensure_memo_shape())
    assert shape.line_width == "1" and shape.line_width_mm == 0.12
    assert doc.styles.memo_shape(doc.styles.ensure_memo_shape(line_width=3)).line_width_mm == 0.2


@pytest.mark.parametrize("value", [0, -0.5, "0.5", True, float("nan")])
def test_a_width_that_is_no_length_is_refused(value: object) -> None:
    doc = HwpxDocument.new()
    with pytest.raises(HwpxValueError) as caught:
        doc.styles.ensure_memo_shape(line_width_mm=value)  # type: ignore[arg-type]
    assert caught.value.code == "style-line-width-invalid"


def test_both_widths_are_refused() -> None:
    doc = HwpxDocument.new()
    with pytest.raises(HwpxValueError) as caught:
        doc.styles.ensure_memo_shape(line_width=1, line_width_mm=0.12)
    assert caught.value.code == "style-memo-shape-line-width-conflict"


def test_a_line_width_that_is_no_index_reads_none() -> None:
    doc = HwpxDocument.new()
    assert doc.styles.memo_shape(doc.styles.ensure_memo_shape(line_width="0.12 mm")).line_width_mm is None
    assert doc.styles.memo_shape(doc.styles.ensure_memo_shape(line_width=16)).line_width_mm is None
