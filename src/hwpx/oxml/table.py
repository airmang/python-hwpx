# SPDX-License-Identifier: Apache-2.0
"""Table-related OpenXML wrappers."""

from __future__ import annotations

import logging
from ._document_impl import HwpxOxmlTable, HwpxOxmlTableCell, HwpxOxmlTableRow, HwpxTableGridPosition

__all__ = ["HwpxOxmlTable", "HwpxOxmlTableCell", "HwpxOxmlTableRow", "HwpxTableGridPosition"]

logger = logging.getLogger(__name__)
