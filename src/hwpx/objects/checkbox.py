# SPDX-License-Identifier: Apache-2.0
"""``CheckBox`` — a live view over one ``<hp:checkBtn>`` form object.

Replaces the 6-key dict ``add_check_box``/``set_check_box``/``list_check_boxes``
returned in 5.x (design §2.4 #1/#4, §2.5). ``checked`` is settable — writing it
mutates the underlying element and marks the owning section dirty, which is why
``set_check_box`` stops being a separate verb once the namespace wires
``doc.fields.check_boxes[i].checked = False`` (design table row 81).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET

    from ..model import Paragraph, Section
    from ..oxml import HwpxOxmlSection


def _offset(self: Any) -> "int | None":
    """Where it stands in its paragraph's text: the number of characters before it, counted as
    ``paragraph.text`` counts (``None`` when it is in no run of a paragraph). It takes no character, so it
    stands after character ``offset - 1`` and before character ``offset``."""

    from ..oxml.text_offsets import placed_offset

    return placed_offset(self)


class CheckBox:
    """A live view over one ``<hp:checkBtn>`` element.

    Thin wrapper — it does not copy the element's state. Reading ``.checked``
    (or ``.name``/``.caption``/``.value``) always reflects the document as it
    is *right now*; writing ``.checked`` writes straight back to the XML.
    """

    offset = property(_offset)

    __slots__ = ("_element", "_section", "_paragraph", "_index")

    def __init__(
        self,
        element: "ET.Element",
        section: "HwpxOxmlSection",
        paragraph: "Paragraph | None",
        *,
        index: int,
    ) -> None:
        self._element = element
        self._section = section
        self._paragraph = paragraph
        self._index = index

    def _live_section(self) -> "HwpxOxmlSection":
        """The section holding the control now: once its paragraph (or the table, text box or note
        around it) moved to another section, that one. An edit through an object taken before the
        move used to mark the section it was taken from, so the change was reported and not saved."""

        from ..oxml._paragraph_text_edit import live_holder

        self._section = live_holder(self._element, self._section)
        return self._section

    def _mark_changed(self) -> None:
        """Mark the control's section as changed -- when the control is in the document. One taken out
        (its paragraph removed) keeps its own new value and leaves every section as it was."""

        from ..oxml._paragraph_text_edit import in_document

        held = self._live_section()
        if in_document(self._element, held):
            held.mark_dirty()

    @property
    def element(self) -> "ET.Element":
        """The wrapped ``<hp:checkBtn>`` element — the escape hatch."""

        return self._element

    @property
    def index(self) -> int:
        """This check box's position among every check box in the document."""

        return self._index

    @property
    def section(self) -> "Section":
        """The section this check box lives in (its number: ``doc.sections.index(cb.section)``)."""

        return self._live_section()

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
            self._mark_changed()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"CheckBox(name={self.name!r}, caption={self.caption!r}, "
            f"checked={self.checked!r}, index={self._index})"
        )


class RadioButton(CheckBox):
    """A live view over one ``<hp:radioBtn>`` (라디오 단추) element.

    Hancom saves it as it saves a check box (``caption``, ``value`` =
    ``CHECKED``/``UNCHECKED``) with the name of its group in ``radioGroupName``.
    Checking one button of a named group unchecks the others of that group in
    the document, as Hancom does when it is clicked.
    """

    __slots__ = ()

    @property
    def group(self) -> str:
        """The button's group (``radioGroupName``); empty when it has none."""

        return self._element.get("radioGroupName", "")

    @property
    def checked(self) -> bool:
        return self._element.get("value", "").upper() == "CHECKED"

    @checked.setter
    def checked(self, value: bool) -> None:
        CheckBox.checked.fset(self, value)  # type: ignore[attr-defined]
        if value and self.group:
            from ..oxml._paragraph_text_edit import in_document

            held = self._live_section()
            if not in_document(self._element, held):
                # Taken out of the document (its paragraph removed): it is not one of the group's
                # buttons any more, so checking it changes its own value and no button of the document.
                return
            document = held.document
            # the sections, and the master pages: a button of the group drawn on every page stayed on
            sections = [*document.sections, *getattr(document, "master_pages", ())] if document is not None else [held]
            for section in sections:
                for other in section.element.iter(self._element.tag):
                    if other is not self._element and other.get("radioGroupName") == self.group \
                            and other.get("value") != "UNCHECKED":
                        other.set("value", "UNCHECKED")
                        section.mark_dirty()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"RadioButton(name={self.name!r}, caption={self.caption!r}, checked={self.checked!r})"


class _FormControl:
    """What the form objects without a check state share: a live view over the element."""

    __slots__ = ("_element", "_section", "_paragraph", "_index")

    def __init__(
        self,
        element: "ET.Element",
        section: "HwpxOxmlSection",
        paragraph: "Paragraph | None",
        *,
        index: int,
    ) -> None:
        self._element = element
        self._section = section
        self._paragraph = paragraph
        self._index = index

    def _live_section(self) -> "HwpxOxmlSection":
        """The section holding the control now: once its paragraph (or the table, text box or note
        around it) moved to another section, that one. An edit through an object taken before the
        move used to mark the section it was taken from, so the change was reported and not saved."""

        from ..oxml._paragraph_text_edit import live_holder

        self._section = live_holder(self._element, self._section)
        return self._section

    def _mark_changed(self) -> None:
        """Mark the control's section as changed -- when the control is in the document. One taken out
        (its paragraph removed) keeps its own new value and leaves every section as it was."""

        from ..oxml._paragraph_text_edit import in_document

        held = self._live_section()
        if in_document(self._element, held):
            held.mark_dirty()

    @property
    def element(self) -> "ET.Element":
        """The wrapped form object element — the escape hatch."""

        return self._element

    @property
    def index(self) -> int:
        """This object's position among the document's objects of its kind."""

        return self._index

    @property
    def section(self) -> "Section":
        """The section this object lives in (its number: ``doc.sections.index(obj.section)``)."""

        return self._live_section()

    @property
    def paragraph(self) -> "Paragraph | None":
        """The paragraph hosting this object, when it could be located."""

        return self._paragraph

    @property
    def name(self) -> str:
        return self._element.get("name", "")


class ComboBox(_FormControl):
    """A live view over one ``<hp:comboBox>`` (콤보 상자) element.

    ``items`` are its list entries as ``(display text, value)`` pairs, read from
    its ``hp:listItem`` children. ``value`` is the chosen value
    (``selectedValue``); assigning it writes that attribute. A box whose
    ``editable_text`` is true (``editEnable``) takes a value outside its items
    too, as Hancom lets one type it. ``text`` is the text the box shows, which
    Hancom keeps as the value of its one list item.
    """

    __slots__ = ()

    @property
    def items(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (item.get("displayText", ""), item.get("value", ""))
            for item in self._element
            if isinstance(item.tag, str) and item.tag.rsplit("}", 1)[-1] == "listItem"
        )

    @property
    def editable_text(self) -> bool:
        return self._element.get("editEnable", "0") in ("1", "true")

    @property
    def text(self) -> str:
        """The text the box shows. Hancom keeps no list of choices in the file (its .hwp form
        object has none): it writes the box's text as the value of the box's one list item
        (``hp:listItem/@value``), with ``displayText`` and ``selectedValue`` empty. Assigning
        it writes that value, as Hancom does."""

        item = self._first_item()
        return item.get("value", "") if item is not None else ""

    @text.setter
    def text(self, value: str) -> None:
        new_value = str(value)
        item = self._first_item()
        if item is None:
            namespace = self._element.tag.rsplit("}", 1)[0] + "}" if "}" in self._element.tag else ""
            item = self._element.makeelement(f"{namespace}listItem", {"displayText": "", "value": ""})
            after = [i for i, child in enumerate(self._element)
                     if isinstance(child.tag, str) and child.tag.rsplit("}", 1)[-1] == "formCharPr"]
            self._element.insert(after[-1] + 1 if after else 0, item)
        if item.get("value") != new_value:
            item.set("value", new_value)  # the box keeps its size: the line does not change
            self._mark_changed()

    def _first_item(self) -> "ET.Element | None":
        return next(
            (item for item in self._element
             if isinstance(item.tag, str) and item.tag.rsplit("}", 1)[-1] == "listItem"),
            None,
        )

    @property
    def value(self) -> str:
        return self._element.get("selectedValue", "")

    @value.setter
    def value(self, value: str) -> None:
        from ..errors import HwpxValueError

        new_value = str(value)
        known = {entry for pair in self.items for entry in pair}
        if not self.editable_text and new_value and new_value not in known:
            raise HwpxValueError(
                f"the combo box {self.name!r} has no item {new_value!r}",
                code="field-choice-unknown",
                context={"name": self.name, "items": [pair[1] or pair[0] for pair in self.items][:50]},
                suggestion="Pick one of the box's items (combo_box.items).",
            )
        if self._element.get("selectedValue") != new_value:
            self._element.set("selectedValue", new_value)
            self._mark_changed()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ComboBox(name={self.name!r}, value={self.value!r}, items={len(self.items)})"


class EditBox(_FormControl):
    """A live view over one ``<hp:edit>`` (입력 상자) element.

    ``text`` is what the box holds, its ``hp:text`` child; assigning it writes
    there. ``multi_line`` and ``read_only`` are its ``multiLine`` and ``readOnly``
    settings as saved.
    """

    __slots__ = ()

    def _text_element(self) -> "ET.Element | None":
        for child in self._element:
            if isinstance(child.tag, str) and child.tag.rsplit("}", 1)[-1] == "text":
                return child
        return None

    @property
    def text(self) -> str:
        element = self._text_element()
        return (element.text or "") if element is not None else ""

    @text.setter
    def text(self, value: str) -> None:
        element = self._text_element()
        if element is None:
            namespace = self._element.tag.rsplit("}", 1)[0] + "}" if "}" in self._element.tag else ""
            element = self._element.makeelement(f"{namespace}text", {})
            self._element.append(element)
        new_value = str(value)
        if not self.multi_line:
            new_value = new_value.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        if element.text != new_value:
            element.text = new_value
            self._mark_changed()

    @property
    def multi_line(self) -> bool:
        return self._element.get("multiLine", "0") in ("1", "true")

    @property
    def read_only(self) -> bool:
        return self._element.get("readOnly", "0") in ("1", "true")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"EditBox(name={self.name!r}, text={self.text!r})"


class Button(_FormControl):
    """A live view over one ``<hp:btn>`` (명령 단추) element.

    ``caption`` is the label on the button, as Hancom saves it (``hp:btn/@caption``, the
    Hancom-saved ``reader_writer__SimpleButtons`` sample). The engine makes no buttons: a button
    runs a command in Hancom, which a document written here cannot give it.
    """

    __slots__ = ()

    @property
    def caption(self) -> str:
        return self._element.get("caption", "")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Button(name={self.name!r}, caption={self.caption!r})"


__all__ = ["Button", "CheckBox", "ComboBox", "EditBox", "RadioButton"]
