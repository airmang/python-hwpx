# SPDX-License-Identifier: Apache-2.0
"""Memo and note OXML wrappers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional
import xml.etree.ElementTree as ET

from ._document_primitives import (
    _DEFAULT_PARAGRAPH_ATTRS,
    _HP,
    _append_child,
    _create_paragraph_element,
    _default_sublist_attributes,
    _element_local_name,
    _memo_id,
    _paragraph_id,
    _sanitize_text,
)

if TYPE_CHECKING:
    from .objects import HwpxOxmlInlineObject
    from .paragraph import HwpxOxmlParagraph
    from .run import HwpxOxmlRun
    from .section import HwpxOxmlSection


def _wrap_paragraph(
    element: ET.Element,
    section: "HwpxOxmlSection",
) -> "HwpxOxmlParagraph":
    from .paragraph import HwpxOxmlParagraph

    return HwpxOxmlParagraph(element, section)

class HwpxOxmlMemoGroup:
    """Wrapper providing access to ``<hp:memogroup>`` containers."""

    def __init__(self, element: ET.Element, section: "HwpxOxmlSection"):
        self.element = element
        self.section = section

    @property
    def memos(self) -> list["HwpxOxmlMemo"]:
        return [
            HwpxOxmlMemo(child, self)
            for child in self.element.findall(f"{_HP}memo")
        ]

    def add_memo(
        self,
        text: str = "",
        *,
        memo_shape_id_ref: str | int | None = None,
        memo_id: str | None = None,
        char_pr_id_ref: str | int | None = None,
        attributes: Optional[dict[str, str]] = None,
    ) -> "HwpxOxmlMemo":
        memo_attrs = dict(attributes or {})
        memo_attrs.setdefault("id", memo_id or _memo_id())
        if memo_shape_id_ref is not None:
            memo_attrs.setdefault("memoShapeIDRef", str(memo_shape_id_ref))
        memo_element = _append_child(self.element, f"{_HP}memo", memo_attrs)
        memo = HwpxOxmlMemo(memo_element, self)
        memo.set_text(text, char_pr_id_ref=char_pr_id_ref)
        self.section.mark_dirty()
        return memo

    def _cleanup(self) -> None:
        if list(self.element):
            return
        try:
            self.section.element.remove(self.element)
        except ValueError:  # pragma: no cover - defensive branch
            return
        self.section.mark_dirty()


class HwpxOxmlMemo:
    """Represents a memo entry contained within a memo group."""

    def __init__(self, element: ET.Element, group: HwpxOxmlMemoGroup):
        self.element = element
        self.group = group

    @property
    def id(self) -> str | None:
        return self.element.get("id")

    @id.setter
    def id(self, value: str | None) -> None:
        if value is None:
            if "id" in self.element.attrib:
                del self.element.attrib["id"]
                self.group.section.mark_dirty()
            return
        new_value = str(value)
        if self.element.get("id") != new_value:
            self.element.set("id", new_value)
            self.group.section.mark_dirty()

    @property
    def memo_shape_id_ref(self) -> str | None:
        return self.element.get("memoShapeIDRef")

    @memo_shape_id_ref.setter
    def memo_shape_id_ref(self, value: str | int | None) -> None:
        if value is None:
            if "memoShapeIDRef" in self.element.attrib:
                del self.element.attrib["memoShapeIDRef"]
                self.group.section.mark_dirty()
            return
        new_value = str(value)
        if self.element.get("memoShapeIDRef") != new_value:
            self.element.set("memoShapeIDRef", new_value)
            self.group.section.mark_dirty()

    @property
    def attributes(self) -> dict[str, str]:
        return dict(self.element.attrib)

    def set_attribute(self, name: str, value: str | int | None) -> None:
        if value is None:
            if name in self.element.attrib:
                del self.element.attrib[name]
                self.group.section.mark_dirty()
            return
        new_value = str(value)
        if self.element.get(name) != new_value:
            self.element.set(name, new_value)
            self.group.section.mark_dirty()

    def _infer_char_pr_id_ref(self) -> str | None:
        for paragraph in self.paragraphs:
            for run in paragraph.runs:
                if run.char_pr_id_ref:
                    return run.char_pr_id_ref
        return None

    @property
    def paragraphs(self) -> list["HwpxOxmlParagraph"]:
        paragraphs: list[HwpxOxmlParagraph] = []
        for node in self.element.findall(f".//{_HP}p"):
            paragraphs.append(_wrap_paragraph(node, self.group.section))
        return paragraphs

    @property
    def text(self) -> str:
        parts: list[str] = []
        for paragraph in self.paragraphs:
            value = paragraph.text
            if value:
                parts.append(value)
        return "\n".join(parts)

    def set_text(
        self,
        value: str,
        *,
        char_pr_id_ref: str | int | None = None,
    ) -> None:
        desired = value or ""
        existing_char = char_pr_id_ref or self._infer_char_pr_id_ref()
        for child in list(self.element):
            if _element_local_name(child) in {"paraList", "p"}:
                self.element.remove(child)
        para_list = _append_child(self.element, f"{_HP}paraList", {})
        paragraph = _create_paragraph_element(
            desired,
            char_pr_id_ref=existing_char if existing_char is not None else "0",
            parent=para_list,
        )
        para_list.append(paragraph)
        self.group.section.mark_dirty()

    @text.setter  # type: ignore[no-redef, attr-defined]  # mypy property-order limitation
    def text(self, value: str) -> None:
        self.set_text(value)

    def remove(self) -> None:
        try:
            self.group.element.remove(self.element)
        except ValueError:  # pragma: no cover - defensive branch
            return
        self.group.section.mark_dirty()
        self.group._cleanup()


class HwpxOxmlNote:
    """Wraps a ``<hp:footNote>`` or ``<hp:endNote>`` element."""

    def __init__(self, element: ET.Element, paragraph: "HwpxOxmlParagraph"):
        self.element = element
        self.paragraph = paragraph

    @property
    def kind(self) -> str:
        """Return ``'footNote'`` or ``'endNote'``."""
        return _element_local_name(self.element)

    @property
    def inst_id(self) -> str | None:
        return self.element.get("instId")

    @property
    def text(self) -> str:
        """Return the note body text."""
        texts: list[str] = []
        for t in self.element.findall(f".//{_HP}t"):
            if t.text:
                texts.append(t.text)
        return "".join(texts)

    @text.setter
    def text(self, value: str) -> None:
        """Replace the note body text."""
        sublist = self.element.find(f"{_HP}subList")
        if sublist is None:
            sublist = _append_child(self.element, f"{_HP}subList", _default_sublist_attributes())
        for p in sublist.findall(f"{_HP}p"):
            sublist.remove(p)
        paragraph = _append_child(sublist, f"{_HP}p", {"id": _paragraph_id(), **_DEFAULT_PARAGRAPH_ATTRS})
        run = _append_child(paragraph, f"{_HP}run", {"charPrIDRef": "0"})
        t = _append_child(run, f"{_HP}t", {})
        t.text = _sanitize_text(value)
        self.paragraph.section.mark_dirty()

    @property
    def body_paragraph(self) -> "HwpxOxmlParagraph":
        """Return the note's body ``<hp:p>`` wrapped as :class:`HwpxOxmlParagraph`.

        The body lives inside ``<hp:subList>`` and is distinct from
        :attr:`paragraph`, which is the *hosting* paragraph (where the note
        marker is inserted). Use this to add runs with mixed formatting
        directly into the note body:

        >>> note = para.add_footnote("기본 ")
        >>> note.add_run("청색", char_pr_id_ref=5)
        """
        p = self.element.find(f".//{_HP}p")
        if p is None:
            raise ValueError("note has no body paragraph element")
        return _wrap_paragraph(p, self.paragraph.section)

    def add_run(
        self,
        text: str = "",
        *,
        char_pr_id_ref: str | int | None = None,
        bold: bool = False,
        italic: bool = False,
        underline: bool = False,
        color: str | None = None,
        font: str | None = None,
        size: int | float | None = None,
        highlight: str | None = None,
        strike: bool | None = None,
        attributes: dict[str, str] | None = None,
    ) -> "HwpxOxmlRun":
        """Append a run to the note body paragraph (delegates to body_paragraph.add_run)."""
        return self.body_paragraph.add_run(
            text,
            char_pr_id_ref=char_pr_id_ref,
            bold=bold,
            italic=italic,
            underline=underline,
            color=color,
            font=font,
            size=size,
            highlight=highlight,
            strike=strike,
            attributes=attributes,
        )

    def add_hyperlink(
        self,
        url: str,
        display_text: str,
        *,
        char_pr_id_ref: str | int | None = None,
    ) -> "HwpxOxmlInlineObject":
        """Append a hyperlink to the note body paragraph.

        Convenience wrapper around ``body_paragraph.add_hyperlink``.
        """
        return self.body_paragraph.add_hyperlink(
            url, display_text, char_pr_id_ref=char_pr_id_ref
        )

__all__ = ["HwpxOxmlMemo", "HwpxOxmlMemoGroup", "HwpxOxmlNote"]
