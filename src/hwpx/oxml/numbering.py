# SPDX-License-Identifier: Apache-2.0
"""Document numbering value objects."""

from __future__ import annotations

from dataclasses import dataclass

@dataclass(slots=True)
class DocumentNumbering:
    """Document-wide numbering initial values defined in ``<hh:beginNum>``."""

    page: int = 1
    footnote: int = 1
    endnote: int = 1
    picture: int = 1
    table: int = 1
    equation: int = 1

__all__ = ["DocumentNumbering"]
