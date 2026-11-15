# SPDX-License-Identifier: Apache-2.0
"""``table.cell(r, c).remove()`` is refused: it left a hole in the grid that save and validate passed."""
from __future__ import annotations

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def test_removing_one_cell_is_refused_and_the_grid_stays_whole() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(2, 2)
    with pytest.raises(ValueError) as excinfo:  # a 6.x ``except ValueError`` still catches it
        table.cell(0, 1).remove()
    error = excinfo.value
    assert isinstance(error, HwpxValueError)
    assert error.code == "table-cell-remove-unsupported"
    assert "delete_rows" in error.suggestion and "merge_cells" in error.suggestion
    assert len(table.element.findall(f"{HP}tr/{HP}tc")) == 4
