# SPDX-License-Identifier: Apache-2.0
"""Memo-related OpenXML wrappers."""

from __future__ import annotations

import logging
from ._document_impl import HwpxOxmlMemo, HwpxOxmlMemoGroup, HwpxOxmlNote

__all__ = ["HwpxOxmlMemo", "HwpxOxmlMemoGroup", "HwpxOxmlNote"]

logger = logging.getLogger(__name__)
