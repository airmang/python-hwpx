# SPDX-License-Identifier: Apache-2.0
"""Renderer-neutral block split geometry.

This module deliberately knows nothing about Hancom discovery, subprocesses,
GUI automation, MCP, or form-fill policy.  Callers provide glyph-like objects
with ``page``, ``x0`` and ``x1`` attributes and explicit column boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class PositionedGlyph(Protocol):
    """Minimum geometry consumed by :func:`detect_block_splits`."""

    page: int
    x0: float
    x1: float


@dataclass
class Block:
    """One logical render block and its positioned glyphs."""

    id: str
    glyphs: list


@dataclass
class BlockSplit:
    """A block that straddles a column or page boundary."""

    block_id: str
    kind: str


def _column_index(x_center: float, column_x_bounds: list[tuple[float, float]]) -> int:
    for index, (x0, x1) in enumerate(column_x_bounds):
        if x0 <= x_center <= x1:
            return index
    return -1


def detect_block_splits(
    blocks: list,
    column_x_bounds: list,
    page_height: float,
) -> list:
    """Return blocks whose glyphs span more than one page or column.

    ``page_height`` remains accepted for compatibility with the established
    contract.  Page membership comes from each glyph's explicit ``page`` field.
    """

    del page_height
    splits: list[BlockSplit] = []
    for block in blocks:
        if not block.glyphs:
            continue
        pages = {glyph.page for glyph in block.glyphs}
        if len(pages) > 1:
            splits.append(BlockSplit(block_id=block.id, kind="page"))
            continue
        columns = {
            _column_index((glyph.x0 + glyph.x1) / 2.0, column_x_bounds)
            for glyph in block.glyphs
        }
        columns.discard(-1)
        if len(columns) > 1:
            splits.append(BlockSplit(block_id=block.id, kind="column"))
    return splits


__all__ = ["Block", "BlockSplit", "PositionedGlyph", "detect_block_splits"]
