# SPDX-License-Identifier: Apache-2.0
"""Paragraph-related OpenXML wrappers."""

from __future__ import annotations

import logging
from ._document_impl import HwpxOxmlParagraph

__all__ = ["HwpxOxmlParagraph"]

logger = logging.getLogger(__name__)
