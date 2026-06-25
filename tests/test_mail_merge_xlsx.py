# SPDX-License-Identifier: Apache-2.0
"""Excel(.xlsx)/명부 ingestion for batch fill (M2 P4 / FR-004)."""
from __future__ import annotations

import pytest

from hwpx.tools.mail_merge import load_mail_merge_rows

openpyxl = pytest.importorskip("openpyxl")


def _write_xlsx(path, header, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(header)
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_load_rows_from_xlsx_uses_header_as_keys(tmp_path):
    path = tmp_path / "roster.xlsx"
    _write_xlsx(path, ["name", "class"], [["홍길동", "3-1"], ["김영수", "3-2"]])

    rows = load_mail_merge_rows(path)

    assert rows == [
        {"name": "홍길동", "class": "3-1"},
        {"name": "김영수", "class": "3-2"},
    ]


def test_load_rows_from_xlsx_coerces_cells_to_str_and_skips_blank_rows(tmp_path):
    path = tmp_path / "roster2.xlsx"
    _write_xlsx(path, ["name", "no"], [["홍길동", 7], [None, None], ["김영수", 12]])

    rows = load_mail_merge_rows(path)

    # numbers become strings; the fully-empty row is dropped
    assert rows == [{"name": "홍길동", "no": "7"}, {"name": "김영수", "no": "12"}]
