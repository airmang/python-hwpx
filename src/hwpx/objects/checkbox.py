# SPDX-License-Identifier: Apache-2.0
"""``CheckBox`` — a live view over one ``<hp:checkBtn>`` form object.

Replaces the 6-key dict ``add_check_box``/``set_check_box``/``list_check_boxes``
returned in 5.x (design §2.4 #1/#4, §2.5). ``checked`` is settable — writing it
mutates the underlying element and marks the owning section dirty, which is why
``set_check_box`` stops being a separate verb once the namespace wires
``doc.fields.check_box(...).checked = False`` (design table row 81).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET

    from ..model import Paragraph
    from ..oxml import HwpxOxmlSection


class CheckBox:
    """A live view over one ``<hp:checkBtn>`` element.

    Thin wrapper — it does not copy the element's state. Reading ``.checked``
    (or ``.name``/``.caption``/``.value``) always reflects the document as it
    is *right now*; writing ``.checked`` writes straight back to the XML.
    """

    __slots__ = ("_element", "_section", "_paragraph", "_index", "_section_index")

    def __init__(
        self,
        element: "ET.Element",
        section: "HwpxOxmlSection",
        paragraph: "Paragraph | None",
        *,
        index: int,
        section_index: int,
    ) -> None:
        self._element = element
        self._section = section
        self._paragraph = paragraph
        self._index = index
        self._section_index = section_index

    @property
    def element(self) -> "ET.Element":
        """The wrapped ``<hp:checkBtn>`` element — the escape hatch."""

        return self._element

    @property
    def index(self) -> int:
        """This check box's position among every check box in the document."""

        return self._index

    @property
    def section_index(self) -> int:
        """Index of the section this check box lives in."""

        return self._section_index

    @property
    def paragraph(self) -> "Paragraph | None":
        """The paragraph hosting this check box, when it could be located."""

        return self._paragraph

    @property
    def name(self) -> str:
        return self._element.get("name", "")

    @property
    def caption(self) -> str:
        return self._element.get("caption", "")

    @property
    def value(self) -> str:
        """The raw OWPML value token (``"CHECKED"`` / ``"UNCHECKED"``)."""

        return self._element.get("value", "")

    @property
    def checked(self) -> bool:
        return self._element.get("value", "").upper() == "CHECKED"

    @checked.setter
    def checked(self, value: bool) -> None:
        new_value = "CHECKED" if value else "UNCHECKED"
        if self._element.get("value") != new_value:
            self._element.set("value", new_value)
            self._section.mark_dirty()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"CheckBox(name={self.name!r}, caption={self.caption!r}, "
            f"checked={self.checked!r}, index={self._index})"
        )


__all__ = ["CheckBox"]
