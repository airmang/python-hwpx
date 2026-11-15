# SPDX-License-Identifier: Apache-2.0
r"""A label holding ``>`` gets a path (written ``\>``) that fills its blank; non-str paths are refused."""

from __future__ import annotations

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxTypeError
from hwpx.tools.table_navigation import _escape_path_label, _split_path


@pytest.mark.parametrize(
    "label",
    ["< 보 기 >", "수입 > 지출", "a\\>b", "a\\\\b", "C:\\temp", "끝\\", ">>"],
)
def test_an_escaped_label_reads_back_as_itself(label: str) -> None:
    assert _split_path(f"{_escape_path_label(label)} > right") == [f"{label} ", " right"]


def test_a_backslash_before_other_text_reads_as_before() -> None:
    assert _split_path("C:\\temp > right") == ["C:\\temp ", " right"]


def test_form_slots_gives_labels_with_gt_a_path_that_fills_the_blank() -> None:
    document = HwpxDocument.new()
    table = document.add_table(2, 2)
    table.cell(0, 0).text = "< 보 기 >"
    table.cell(1, 0).text = "수입 > 지출"

    slots = document.tables.form_slots()["slots"]
    paths = [slot["path"] for slot in slots]
    assert paths == ["< 보 기 \\> > right", "수입 \\> 지출 > right"]

    result = document.tables.fill_by_path({path: f"값{n}" for n, path in enumerate(paths)})

    assert result["failed"] == []
    assert table.cell(0, 1).text == "값0"
    assert table.cell(1, 1).text == "값1"


def test_repeated_label_with_gt_is_numbered_after_escaping() -> None:
    document = HwpxDocument.new()
    for _ in range(2):
        document.add_table(1, 2).cell(0, 0).text = "가>나"

    paths = [slot["path"] for slot in document.tables.form_slots()["slots"]]

    assert paths == ["가\\>나[1] > right", "가\\>나[2] > right"]
    assert document.tables.fill_by_path({paths[1]: "둘째"})["failed"] == []


@pytest.mark.parametrize("bad", [None, 3, ("성명", "right")])
def test_a_path_that_is_not_str_is_refused_before_writing(bad: object) -> None:
    document = HwpxDocument.new()
    table = document.add_table(1, 2)
    table.cell(0, 0).text = "성명"

    with pytest.raises(HwpxTypeError) as excinfo:
        document.tables.fill_by_path({"성명 > right": "홍길동", bad: "x"})  # type: ignore[dict-item]

    assert excinfo.value.code == "table-path-invalid-type"
    assert excinfo.value.suggestion
    assert isinstance(excinfo.value, TypeError)
    assert table.cell(0, 1).text == ""


def test_a_mapping_that_is_not_one_is_refused() -> None:
    document = HwpxDocument.new()
    with pytest.raises(HwpxTypeError):
        document.tables.fill_by_path(["성명 > right"])  # type: ignore[arg-type]
