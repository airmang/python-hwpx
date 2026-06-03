"""Pure table cleanup helpers for pasted report data."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Sequence

_INTERNAL_NEWLINE_RE = re.compile(r"[ \t]*\r?\n[ \t]*")


def normalize_cell_text(value: Any) -> str:
    """Strip cell edges and collapse embedded line breaks to spaces."""

    if value is None:
        return ""
    return _INTERNAL_NEWLINE_RE.sub(" ", str(value).strip())


def normalize_table_rows(rows: Sequence[Sequence[Any]]) -> list[list[str]]:
    """Return normalized table rows without mutating the input."""

    return [[normalize_cell_text(cell) for cell in row] for row in rows]


def add_sequence_column(rows: Sequence[Sequence[Any]], *, start: int = 1) -> list[list[Any]]:
    """Prepend a 1-based sequence column to each row."""

    return [[str(start + index), *list(row)] for index, row in enumerate(rows)]


def add_reverse_sum(rows: Sequence[Sequence[Any]]) -> list[list[Any]]:
    """Append a row-wise numeric sum, ignoring non-numeric cells."""

    result: list[list[Any]] = []
    for row in rows:
        total = Decimal("0")
        for cell in row:
            number = _parse_decimal(cell)
            if number is not None:
                total += number
        result.append([*list(row), _format_decimal(total)])
    return result


def _parse_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _format_decimal(value: Decimal) -> str:
    if value == value.to_integral_value():
        return str(value.quantize(Decimal("1")))
    return format(value.normalize(), "f")
