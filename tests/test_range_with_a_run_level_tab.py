"""A tab written straight under the run (``hp:run/hp:tab``, not ``hp:t/hp:tab``) moves as one character: the
character after it stays. No Hancom-saved file writes a tab there, but the engine reads the form."""
from __future__ import annotations

import pytest

from hwpx import HwpxDocument

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _with_run_tab() -> tuple[HwpxDocument, object, object]:
    document = HwpxDocument.new()
    first = document.add_paragraph("A")
    first.add_run("B")
    document.add_paragraph("X")
    run = first.runs[-1].element
    run.insert(0, run.makeelement(_HP + "tab", {}))
    again = HwpxDocument.open(document.to_bytes())
    first, second = again.paragraphs
    assert first.text == "A\tB"
    return again, first, second


@pytest.mark.parametrize("operation", ["move_range", "copy_range"])
@pytest.mark.parametrize(("start", "end"), [(1, 2), (0, 2), (1, 3), (0, 3)])
def test_a_run_level_tab_moves_and_copies_as_one_character(operation: str, start: int, end: int) -> None:
    document, first, second = _with_run_tab()
    getattr(first, operation)(start, end, to=second)
    expected_left = "A\tB" if operation == "copy_range" else "A\tB"[:start] + "A\tB"[end:]
    assert first.text == expected_left
    assert second.text == "X" + "A\tB"[start:end]
    saved = HwpxDocument.open(document.to_bytes())
    assert [p.text for p in saved.paragraphs] == [expected_left, "X" + "A\tB"[start:end]]


def test_deleting_a_run_level_tab_takes_one_character() -> None:
    document, first, _second = _with_run_tab()
    first.delete_range(1, 2)
    assert first.text == "AB"
