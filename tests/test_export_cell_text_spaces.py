"""A table cell's text keeps the spaces it holds in plain-text export (Hancom's preview text
keeps them too, e.g. ``<협조자   >``); only the blank lines at the cell's ends go."""

from __future__ import annotations

from hwpx.document import HwpxDocument
from hwpx.tools.exporter import export_text


def _row(document: HwpxDocument) -> str:
    return next(line for line in export_text(document).splitlines() if "\t" in line)


def test_leading_and_trailing_spaces_in_a_cell_stay() -> None:
    document = HwpxDocument.new()
    table = document.add_table(1, 2)
    table.cell(0, 0).text = "  용  역  명 : 행사"
    table.cell(0, 1).text = "협조자   "

    assert _row(document) == "  용  역  명 : 행사\t협조자   "


def test_blank_paragraphs_at_the_ends_of_a_cell_still_go() -> None:
    document = HwpxDocument.new()
    table = document.add_table(1, 2)
    table.cell(0, 0).set_text("\n가운데\n", split_paragraphs=True)
    table.cell(0, 1).text = "옆"

    assert _row(document) == "가운데\t옆"
