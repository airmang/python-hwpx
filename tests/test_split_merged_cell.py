"""Regression tests for split_merged_cell – ET / lxml mixing fix.

The root cause of the original crash (TypeError: append() argument 1
must be xml.etree.ElementTree.Element, not lxml.etree._Element) was that
``split_merged_cell`` created new cell elements with stdlib
``ET.Element()`` while the existing document tree consisted of lxml
elements (parsed via ``lxml.etree.fromstring``).  The fix uses
``row_element.makeelement()`` so that new cells always match the XML
engine of the surrounding tree.

Choice A was applied: *all runtime element creation inside
``split_merged_cell`` is now engine-agnostic* by delegating to
``makeelement`` / ``SubElement`` (which itself delegates to
``makeelement``), so the code works identically with both stdlib ET
and lxml trees.
"""

from __future__ import annotations

import io

import pytest

from hwpx.document import HwpxDocument


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _new_doc_with_table(rows: int = 3, cols: int = 3) -> tuple[HwpxDocument, object]:
    """Return (document, table) backed by lxml (via HwpxDocument.new())."""
    doc = HwpxDocument.new()
    table = doc.add_table(rows, cols)
    return doc, table


# --------------------------------------------------------------------------- #
# Scenario 1 – horizontal merge then split
# --------------------------------------------------------------------------- #


def test_split_horizontal_merge_no_type_error() -> None:
    """Splitting a horizontally merged cell must not raise TypeError.

    This is the exact code-path that triggered the original crash when
    an lxml-backed table was modified with stdlib ET elements.
    """
    doc, table = _new_doc_with_table(3, 3)

    # Merge (0,0)–(0,1) horizontally
    table.merge_cells(0, 0, 0, 1)
    merged = table.cell(0, 0)
    assert merged.span == (1, 2), "pre-condition: cell should be merged"

    # Split – this used to crash with TypeError
    result = table.split_merged_cell(0, 0)
    assert result is not None

    # Master cell span reset to (1, 1)
    assert table.cell(0, 0).span == (1, 1)
    # Restored cell exists and is independent
    assert table.cell(0, 1).span == (1, 1)
    assert table.cell(0, 0).element is not table.cell(0, 1).element


# --------------------------------------------------------------------------- #
# Scenario 2 – vertical merge then split
# --------------------------------------------------------------------------- #


def test_split_vertical_merge_no_type_error() -> None:
    """Splitting a vertically merged cell must not raise TypeError."""
    doc, table = _new_doc_with_table(3, 3)

    # Merge (0,0)–(1,0) vertically
    table.merge_cells(0, 0, 1, 0)
    assert table.cell(0, 0).span == (2, 1)

    result = table.split_merged_cell(0, 0)
    assert result is not None

    assert table.cell(0, 0).span == (1, 1)
    assert table.cell(1, 0).span == (1, 1)
    assert table.cell(0, 0).element is not table.cell(1, 0).element


# --------------------------------------------------------------------------- #
# Scenario 3 – 2×2 block merge then split
# --------------------------------------------------------------------------- #


def test_split_block_merge_restores_all_cells() -> None:
    """A 2×2 block merge should produce 4 independent cells after split."""
    doc, table = _new_doc_with_table(3, 3)

    table.merge_cells(0, 0, 1, 1)
    assert table.cell(0, 0).span == (2, 2)

    table.split_merged_cell(0, 0)

    for r in range(2):
        for c in range(2):
            cell = table.cell(r, c)
            assert cell.span == (1, 1), f"cell ({r},{c}) span should be (1,1)"


# --------------------------------------------------------------------------- #
# Scenario 4 – save → reopen round-trip after split
# --------------------------------------------------------------------------- #


def test_split_then_save_reopen_roundtrip(tmp_path) -> None:
    """After splitting, the document must survive save → reopen."""
    doc, table = _new_doc_with_table(3, 3)

    # Write identifiable text before merge
    table.set_cell_text(0, 0, "A")
    table.set_cell_text(0, 1, "B")
    table.set_cell_text(0, 2, "C")

    # Merge (0,0)–(0,1) then split
    table.merge_cells(0, 0, 0, 1)
    table.split_merged_cell(0, 0)

    # Set text in the restored cell
    table.cell(0, 1).text = "B-restored"

    # Save to bytes and reopen
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    reopened = HwpxDocument.open(buf.getvalue())
    # Collect tables from all paragraphs
    rt_tables = [
        t
        for para in reopened.paragraphs
        for t in para.tables
    ]
    assert len(rt_tables) >= 1

    rt_table = rt_tables[0]
    assert rt_table.cell(0, 0).span == (1, 1)
    assert rt_table.cell(0, 1).span == (1, 1)
    # Master cell kept its original text
    assert rt_table.cell(0, 0).text == "A"
    # Restored cell has the text we set
    assert rt_table.cell(0, 1).text == "B-restored"
    # Untouched cell is intact
    assert rt_table.cell(0, 2).text == "C"


# --------------------------------------------------------------------------- #
# Scenario 5 – split via set_cell_text logical API
# --------------------------------------------------------------------------- #


def test_set_cell_text_split_merged_flag() -> None:
    """``set_cell_text(split_merged=True)`` must trigger split correctly."""
    doc, table = _new_doc_with_table(3, 3)

    table.merge_cells(0, 0, 0, 1)
    # Write to the covered column with split_merged=True
    table.set_cell_text(0, 1, "Split-Write", logical=True, split_merged=True)

    assert table.cell(0, 0).span == (1, 1)
    assert table.cell(0, 1).text == "Split-Write"
    assert table.cell(0, 1).span == (1, 1)


# --------------------------------------------------------------------------- #
# Scenario 6 – splitting an already-unmerged cell is a no-op
# --------------------------------------------------------------------------- #


def test_split_unmerged_cell_is_noop() -> None:
    """Splitting a cell that is not merged should return it unchanged."""
    doc, table = _new_doc_with_table(2, 2)

    cell_before = table.cell(0, 0)
    cell_after = table.split_merged_cell(0, 0)
    assert cell_before.element is cell_after.element
    assert cell_after.span == (1, 1)
