# SPDX-License-Identifier: Apache-2.0
"""Section-related OpenXML wrappers."""

from __future__ import annotations

import logging
from ._document_impl import HwpxOxmlSection, HwpxOxmlSectionHeaderFooter, HwpxOxmlSectionProperties

__all__ = ["HwpxOxmlSection", "HwpxOxmlSectionHeaderFooter", "HwpxOxmlSectionProperties"]

logger = logging.getLogger(__name__)
