# SPDX-License-Identifier: Apache-2.0
"""Simple package-part OXML wrappers."""

from __future__ import annotations

from typing import TYPE_CHECKING
import xml.etree.ElementTree as ET

from ._document_primitives import _serialize_xml

if TYPE_CHECKING:
    from .document_parts import HwpxOxmlDocument


class _HwpxOxmlSimplePart:
    """Common base for standalone XML parts that are not sections or headers."""

    def __init__(
        self,
        part_name: str,
        element: ET.Element,
        document: "HwpxOxmlDocument" | None = None,  # type: ignore[reportGeneralTypeIssues]  # frozen public annotation
    ):
        self.part_name = part_name
        self._element = element
        self._document = document
        self._dirty = False

    @property
    def element(self) -> ET.Element:
        return self._element

    @property
    def document(self) -> "HwpxOxmlDocument" | None:  # type: ignore[reportGeneralTypeIssues]  # frozen public annotation
        return self._document

    def attach_document(self, document: "HwpxOxmlDocument") -> None:
        self._document = document

    @property
    def dirty(self) -> bool:
        return self._dirty

    def mark_dirty(self) -> None:
        self._dirty = True

    def reset_dirty(self) -> None:
        self._dirty = False

    def replace_element(self, element: ET.Element) -> None:
        self._element = element
        self.mark_dirty()

    def to_bytes(self) -> bytes:
        return _serialize_xml(self._element)


class HwpxOxmlMasterPage(_HwpxOxmlSimplePart):
    """Represents a master page part in the package."""


class HwpxOxmlHistory(_HwpxOxmlSimplePart):
    """Represents a document history part."""


class HwpxOxmlVersion(_HwpxOxmlSimplePart):
    """Represents the ``version.xml`` part."""

__all__ = ["HwpxOxmlHistory", "HwpxOxmlMasterPage", "HwpxOxmlVersion"]
