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
    [(0.12, "1", 0.12), (0.5, "7", 0.5), (1, "10", 1.0), (5, "15", 5.0), (0.1, "0", 0.1)],
)
def test_ensure_memo_shape_takes_millimetres(mm: float, written: str, read: float) -> None:
    doc = HwpxDocument.new()
    shape_id = doc.styles.ensure_memo_shape(line_width_mm=mm)
    shape = doc.styles.memo_shape(shape_id)
    assert shape is not None and shape.line_width == written and shape.line_width_mm == read


@pytest.mark.parametrize("mm", [0.45, 9])
def test_a_width_off_hancoms_list_is_refused_not_moved_to_the_nearest(mm: float) -> None:
    # 7.0: the engine does not write another width than the one it was given (as for borders).
    doc = HwpxDocument.new()
    before = doc.to_bytes()
    with pytest.raises(HwpxValueError) as caught:
        doc.styles.ensure_memo_shape(line_width_mm=mm)
    assert caught.value.code == "style-line-width-invalid" and "0.12" in caught.value.suggestion
    assert doc.to_bytes() == before


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
    assert doc.styles.memo_shape(doc.styles.ensure_memo_shape(line_width_mm=0.2)).line_width == "3"


@pytest.mark.parametrize("value", [0, -0.5, "0.5", True, float("nan")])
def test_a_width_that_is_no_length_is_refused(value: object) -> None:
    doc = HwpxDocument.new()
    with pytest.raises(HwpxValueError) as caught:
        doc.styles.ensure_memo_shape(line_width_mm=value)  # type: ignore[arg-type]
    assert caught.value.code == "style-line-width-invalid"


@pytest.mark.parametrize("owner", ["doc.styles", "Document", "HeaderPart"])
def test_the_6x_raw_line_width_argument_names_line_width_mm(owner: str) -> None:
    from hwpx.errors import HwpxTypeError

    doc = HwpxDocument.new()
    call = {
        "doc.styles": doc.styles.ensure_memo_shape,
        "Document": doc.oxml.ensure_memo_shape,
        "HeaderPart": doc.oxml.headers[0].ensure_memo_shape,
    }[owner]
    with pytest.raises(HwpxTypeError) as caught:
        call(line_width=1)
    assert caught.value.code == "hwpx-argument-removed"
    assert caught.value.context["replacement"] == "line_width_mm"


@pytest.mark.parametrize(
    ("written", "read"),
    # Hangul 2024 re-saves these as 0, 0, 27, 1 (observed): a string is 0, a number is one byte.
    [("0.6mm", 0.1), ("0.4 mm", 0.1), ("283", None), ("257", 0.12), ("16", None), ("15", 5.0)],
)
def test_a_line_width_reads_as_hangul_reads_it(written: str, read: float | None) -> None:
    from hwpx.oxml.header import MemoShape

    shape = MemoShape(id=0, width=15591, line_width=written, line_type="SOLID", line_color=None, fill_color=None,
                      active_color=None, memo_type="NOMAL")
    assert shape.line_width_mm == read
