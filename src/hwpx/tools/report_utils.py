# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any


_DATE_RE = re.compile(r"^\s*(\d{4})[./-]\s*(\d{1,2})[./-]\s*(\d{1,2})\.?\s*$")
_DIGITS = ("", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구")
_SMALL_UNITS = ("", "십", "백", "천")
_LARGE_UNITS = ("", "만", "억", "조", "경")


def _decimal_value(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid numeric value: {value!r}") from exc


def _format_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return f"{int(normalized):,}"
    text = format(normalized, "f").rstrip("0").rstrip(".")
    integer, fraction = text.split(".", 1)
    return f"{int(integer):,}.{fraction}"


def format_number_commas(value: Any) -> str:
    """Return a decimal value with Korean report-style thousands separators."""

    return _format_decimal(_decimal_value(value))


def _hangul_under_10000(value: int) -> str:
    if value <= 0 or value >= 10_000:
        raise ValueError("value must be between 1 and 9999")
    parts: list[str] = []
    for index, unit in enumerate(_SMALL_UNITS):
        digit = value % 10
        value //= 10
        if not digit:
            continue
        if digit == 1 and unit:
            parts.append(unit)
        else:
            parts.append(f"{_DIGITS[digit]}{unit}")
    return "".join(reversed(parts))


def format_krw_hangul(value: Any) -> str:
    """Format a won amount in Hangul large units."""

    amount = _decimal_value(value)
    if amount != amount.to_integral():
        raise ValueError("KRW amount must be an integer")
    integer = int(amount)
    if integer == 0:
        return "0원"
    sign = "마이너스 " if integer < 0 else ""
    integer = abs(integer)
    parts: list[str] = []
    unit_index = 0
    while integer:
        chunk = integer % 10_000
        integer //= 10_000
        if chunk:
            unit = _LARGE_UNITS[unit_index] if unit_index < len(_LARGE_UNITS) else f"10^{unit_index * 4}"
            parts.append(f"{_hangul_under_10000(chunk)}{unit}")
        unit_index += 1
    return f"{sign}{' '.join(reversed(parts))}원"


def normalize_korean_date(value: Any) -> str:
    """Normalize common Korean date spellings to ISO ``YYYY-MM-DD``."""

    if isinstance(value, date):
        return value.isoformat()
    match = _DATE_RE.match(str(value))
    if not match:
        raise ValueError(f"unsupported date value: {value!r}")
    year, month, day = (int(group) for group in match.groups())
    return date(year, month, day).isoformat()


def calculate_age(birth_date: Any, *, today: date | None = None) -> int:
    """Return full age as of ``today``."""

    current = today or date.today()
    born = date.fromisoformat(normalize_korean_date(birth_date))
    age = current.year - born.year
    if (current.month, current.day) < (born.month, born.day):
        age -= 1
    return age


def format_delta(value: Any, *, negative_prefix: str = "△") -> str:
    """Format a signed absolute delta, using △ for negatives by default."""

    delta = _decimal_value(value)
    if delta == 0:
        return "0"
    if delta < 0:
        return f"{negative_prefix}{_format_decimal(abs(delta))}"
    return f"+{_format_decimal(delta)}"


def calculate_ratios(numerator: Any, denominator: Any, *, digits: int = 1) -> float:
    """Return numerator/denominator as a percentage."""

    denominator_value = _decimal_value(denominator)
    if denominator_value == 0:
        raise ValueError("denominator must not be zero")
    ratio = (_decimal_value(numerator) / denominator_value) * Decimal("100")
    return float(round(ratio, digits))


def format_delta_percent(current: Any, previous: Any, *, digits: int = 1) -> str:
    """Format percentage change from previous to current."""

    previous_value = _decimal_value(previous)
    if previous_value == 0:
        raise ValueError("previous value must not be zero")
    delta = ((_decimal_value(current) - previous_value) / previous_value) * Decimal("100")
    rounded = round(delta, digits)
    if rounded == 0:
        return f"{0:.{digits}f}%"
    prefix = "△" if rounded < 0 else "+"
    return f"{prefix}{abs(float(rounded)):.{digits}f}%"
