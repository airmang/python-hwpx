from __future__ import annotations

from datetime import date

import pytest

from hwpx.tools.report_utils import (
    calculate_age,
    calculate_ratios,
    format_delta,
    format_delta_percent,
    format_krw_hangul,
    format_number_commas,
    normalize_korean_date,
)


def test_format_krw_hangul_zero_and_large_units() -> None:
    assert format_krw_hangul(0) == "0원"
    assert format_krw_hangul(5_000_000) == "오백만원"
    assert format_krw_hangul(123_456_789) == "일억 이천삼백사십오만 육천칠백팔십구원"


def test_format_number_commas_preserves_decimal_text() -> None:
    assert format_number_commas(1_234_567) == "1,234,567"
    assert format_number_commas(-1234.5) == "-1,234.5"


def test_calculate_age_uses_korean_full_age() -> None:
    assert calculate_age("2000-06-03", today=date(2026, 6, 3)) == 26
    assert calculate_age("2000. 6. 4.", today=date(2026, 6, 3)) == 25


def test_format_delta_negative_uses_triangle_by_default() -> None:
    assert format_delta(-5) == "△5"
    assert format_delta(5) == "+5"
    assert format_delta(0) == "0"


def test_format_delta_percent_uses_previous_value() -> None:
    assert format_delta_percent(110, 100) == "+10.0%"
    assert format_delta_percent(95, 100) == "△5.0%"
    with pytest.raises(ValueError, match="previous"):
        format_delta_percent(1, 0)


def test_calculate_ratios_zero_division_is_explicit_error() -> None:
    assert calculate_ratios(25, 100) == 25.0
    assert calculate_ratios(1, 3, digits=1) == 33.3
    with pytest.raises(ValueError, match="denominator"):
        calculate_ratios(1, 0)


def test_normalize_korean_date_accepts_common_forms() -> None:
    for value in ("2026. 6. 2.", "2026-06-02", "2026/06/02"):
        assert normalize_korean_date(value) == "2026-06-02"
