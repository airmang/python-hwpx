# SPDX-License-Identifier: Apache-2.0
"""Common mistakes raise ``HwpxError`` with a code and a next step, still caught by 6.x ``except``s."""
from __future__ import annotations

import pytest

from hwpx import HwpxDocument
from hwpx.errors import ERROR_CODES, HwpxError

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 40


def _doc() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    doc.add_table(2, 2)
    return doc


CASES = [
    ("add_table(0, 0)", lambda d: d.add_table(0, 0), ValueError, "table-size-invalid"),
    ("add_table('2', 2)", lambda d: d.add_table("2", 2), TypeError, "table-size-invalid"),
    ("add_paragraph(123)", lambda d: d.add_paragraph(123), TypeError, "paragraph-text-invalid-type"),
    ("cell(9, 9)", lambda d: d.tables[0].cell(9, 9), IndexError, "table-cell-not-found"),
    ("cell(-1, 0)", lambda d: d.tables[0].cell(-1, 0), IndexError, "table-cell-not-found"),
    ("tables[99]", lambda d: d.tables[99], IndexError, "table-not-found"),
    ("set_cell_text(99, 0)", lambda d: d.tables[0].set_cell_text(99, 0, "x"), IndexError, "table-cell-not-found"),
    ("apply_paragraph_format(99)", lambda d: d.styles.apply_paragraph_format(paragraph_index=99, alignment="CENTER"),
     IndexError, "paragraph-not-found"),
    ("replace_picture(9)", lambda d: d.media.replace_picture(PNG, "png", picture_index=9), IndexError,
     "media-picture-not-found"),
    ("merge_cells out of bounds", lambda d: d.tables[0].merge_cells(0, 0, 5, 5), IndexError,
     "table-merge-range-invalid"),
    ("merge_cells reversed", lambda d: d.tables[0].merge_cells(1, 1, 0, 0), ValueError, "table-merge-range-invalid"),
    ("merge_cells bad range", lambda d: d.tables[0].merge_cells("A1-B2"), ValueError, "table-merge-range-invalid"),
    ("remove_section(5)", lambda d: d.remove_section(5), IndexError, "section-not-found"),
    ("remove_section(0) of one", lambda d: d.remove_section(0), ValueError, "section-remove-last"),
    ("apply_list_format(star)", lambda d: d.styles.apply_list_format(kind="star"), ValueError,
     "style-list-kind-invalid"),
]


@pytest.mark.parametrize(("name", "call", "builtin", "code"), CASES, ids=[case[0] for case in CASES])
def test_a_common_mistake_is_a_typed_error_the_old_except_still_catches(name, call, builtin, code) -> None:
    doc = _doc()
    with pytest.raises(builtin) as excinfo:
        call(doc)
    error = excinfo.value
    assert isinstance(error, HwpxError), type(error)
    assert error.code == code
    assert code in ERROR_CODES
    assert error.suggestion


def test_add_table_with_bad_sizes_adds_nothing() -> None:
    doc = _doc()
    before = len(doc.paragraphs)
    with pytest.raises(ValueError):
        doc.add_table(0, 3)
    assert len(doc.paragraphs) == before


def test_table_structure_refusals_name_public_calls() -> None:
    doc = _doc()
    with pytest.raises(HwpxError) as excinfo:
        doc.tables[0].delete_rows([0, 1])
    assert "table.remove()" in str(excinfo.value)
    assert "table.remove()" in excinfo.value.suggestion


def test_table_remove_takes_the_table_out_and_keeps_the_line() -> None:
    doc = _doc()
    table = doc.tables[0]
    count = len(doc.paragraphs)
    table.remove()
    table.remove()  # a second call does nothing
    assert len(doc.tables) == 0
    assert len(doc.paragraphs) == count
    import io

    buffer = io.BytesIO()
    doc.save_to_stream(buffer)
    assert HwpxDocument.open(buffer.getvalue()).validate().ok
