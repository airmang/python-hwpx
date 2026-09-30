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
    _text_element_content,
)
from ._paragraph_text_edit import set_text_with_tabs

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


def _paragraph_containing(root: ET.Element, target: ET.Element) -> ET.Element | None:
    """Return the innermost ``<hp:p>`` ancestor of *target* within *root*.

    Walks down from *root* rather than up from *target* via ``getparent()``:
    live documents are lxml, which supports that, but several test suites
    (e.g. ``tests/test_memo_and_style_editing.py``) hand-build fixtures with
    the standard-library ``xml.etree.ElementTree``, which does not.
    ``for child in node`` and identity comparison work the same on both.
    """

    def _walk(node: ET.Element, nearest: ET.Element | None) -> ET.Element | None:
        if _element_local_name(node) == "p":
            nearest = node
        if node is target:
            return nearest
        for child in node:
            found = _walk(child, nearest)
            if found is not None:
                return found
        return None

    return _walk(root, None)


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

    def _anchor_field(self) -> ET.Element | None:
        """Return the ``<hp:fieldBegin type="MEMO">`` anchoring this memo, if any.

        A memo is only visible in Hancom once a MEMO field control in the body
        references this memo's ``id`` through its ``ID`` string parameter (see
        ``hwpx._document.memos.attach_memo_field``). This searches the memo's
        own section for that anchor — a memo created by
        :meth:`HwpxOxmlMemoGroup.add_memo` alone has none yet, so both
        :attr:`paragraph` and :attr:`field_id` are ``None`` until a field
        attaches it.
        """

        memo_id = self.id
        if not memo_id:
            return None
        section_element = self.group.section.element
        for field_begin in section_element.iter(f"{_HP}fieldBegin"):
            if field_begin.get("type") != "MEMO":
                continue
            for string_param in field_begin.iter(f"{_HP}stringParam"):
                if string_param.get("name") == "ID" and (string_param.text or "") == memo_id:
                    return field_begin
        return None

    @property
    def field_id(self) -> str | None:
        """The id of the MEMO field anchoring this memo, once attached.

        ``None`` until a field control created by
        ``hwpx._document.memos.attach_memo_field``/``add_memo_with_anchor``
        references this memo — replaces the ``str`` those two functions used
        to return directly (6.0 return contract, design §2.3/§2.6).
        """

        field = self._anchor_field()
        return field.get("id") if field is not None else None

    @property
    def paragraph(self) -> "HwpxOxmlParagraph | None":
        """The paragraph hosting this memo's anchor field, once attached.

        ``None`` until the memo is anchored (see :attr:`field_id`) — replaces
        the second element of the ``add_memo_with_anchor`` 3-tuple.
        """

        field = self._anchor_field()
        if field is None:
            return None
        node = _paragraph_containing(self.group.section.element, field)
        if node is None:
            return None
        return _wrap_paragraph(node, self.group.section)

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
        """Remove the memo and the MEMO field anchoring it (the field's two controls; the text it spans
        stays). The field holds what Hancom shows of the memo, so a memo left anchored would stay."""

        field = self._anchor_field()
        try:
            self.group.element.remove(self.element)
        except ValueError:  # pragma: no cover - defensive branch
            return
        if field is not None:
            _remove_field(self.group.section.element, field)
        self.group.section.mark_dirty()
        self.group._cleanup()


def _remove_field(root: ET.Element, field_begin: ET.Element) -> None:
    """Remove the controls of a field: the ``hp:ctrl`` holding *field_begin* and the one holding its
    ``hp:fieldEnd``, and a run left empty by either. The text between them stays."""

    begin_id = field_begin.get("id")
    ends = [
        end for end in root.iter(f"{_HP}fieldEnd")
        if begin_id is not None and end.get("beginIDRef") == begin_id
    ]
    for marker in [field_begin, *ends]:
        ctrl, run = _parent_of(root, marker), None
        if ctrl is not None and _element_local_name(ctrl) == "ctrl":
            run = _parent_of(root, ctrl)
        else:
            ctrl = None
        holder = ctrl if ctrl is not None else _parent_of(root, marker)
        target = ctrl if ctrl is not None else marker
        if holder is None:
            continue
        if ctrl is not None and run is not None:
            run.remove(ctrl)
            if not list(run) and _element_local_name(run) == "run":
                paragraph = _parent_of(root, run)
                if paragraph is not None and len(paragraph.findall(f"{_HP}run")) > 1:
                    paragraph.remove(run)
        else:
            holder.remove(target)


def _parent_of(root: ET.Element, target: ET.Element) -> ET.Element | None:
    """*target*'s parent within *root* (works on ``xml.etree`` trees too, which have no ``getparent``)."""

    getparent = getattr(target, "getparent", None)
    if getparent is not None:
        return getparent()
    for node in root.iter():
        for child in node:
            if child is target:
                return node
    return None


def memo_field_id(field_begin: ET.Element) -> str | None:
    """The memo id a MEMO field carries (its ``ID`` string parameter)."""

    for param in field_begin.iter(f"{_HP}stringParam"):
        if param.get("name") == "ID":
            return param.text or ""
    return None


class _FieldMemoHost:
    """What a memo kept in its field needs of a memo group: the section (there is no group)."""

    element = None

    def __init__(self, section: "HwpxOxmlSection"):
        self.section = section

    def _cleanup(self) -> None:
        return None


class HwpxOxmlFieldMemo(HwpxOxmlMemo):
    """A memo kept only in its MEMO field, as Hancom saves memos (and as HWP files converted to HWPX
    hold them): its text is the ``hp:fieldBegin``'s own ``hp:subList`` and its id, number, author and
    time are the field's parameters. There is no ``hp:memogroup`` entry. :attr:`element` is the
    ``hp:fieldBegin``."""

    def __init__(self, field_begin: ET.Element, section: "HwpxOxmlSection"):
        super().__init__(field_begin, _FieldMemoHost(section))  # type: ignore[arg-type]

    def _param(self, name: str) -> ET.Element | None:
        for param in self.element.iter():
            if _element_local_name(param).endswith("Param") and param.get("name") == name:
                return param
        return None

    @property
    def id(self) -> str | None:  # type: ignore[override]
        return memo_field_id(self.element)

    @property
    def memo_shape_id_ref(self) -> str | None:  # type: ignore[override]
        param = self._param("MemoShapeIDRef")
        return None if param is None else (param.text or None)

    @property
    def attributes(self) -> dict[str, str]:
        """The field's parameters by name (``ID``, ``Number``, ``Author``, ``CreateDateTime``, ...)."""

        return {
            param.get("name", ""): param.text or ""
            for param in self.element.iter()
            if _element_local_name(param).endswith("Param") and param.get("name")
        }

    def set_attribute(self, name: str, value: str | int | None) -> None:
        param = self._param(name)
        if param is None or value is None:
            raise KeyError(name)
        if param.text != str(value):
            param.text = str(value)
            self.group.section.mark_dirty()

    def _anchor_field(self) -> ET.Element | None:
        return self.element

    def _sub_list(self) -> ET.Element | None:
        return self.element.find(f"{_HP}subList")

    @property
    def paragraphs(self) -> list["HwpxOxmlParagraph"]:
        sub_list = self._sub_list()
        if sub_list is None:
            return []
        return [_wrap_paragraph(node, self.group.section) for node in sub_list.findall(f"{_HP}p")]

    def set_text(self, value: str, *, char_pr_id_ref: str | int | None = None) -> None:
        """Replace the memo's text: one paragraph shaped like the field's first one."""

        sub_list = self._sub_list()
        if sub_list is None:
            sub_list = _append_child(self.element, f"{_HP}subList", _default_sublist_attributes())
        existing_char = char_pr_id_ref or self._infer_char_pr_id_ref()
        paragraphs = sub_list.findall(f"{_HP}p")
        attrs = dict(paragraphs[0].attrib) if paragraphs else None
        for paragraph in paragraphs:
            sub_list.remove(paragraph)
        paragraph = _create_paragraph_element(
            value or "",
            char_pr_id_ref=existing_char if existing_char is not None else "0",
            parent=sub_list,
        )
        if attrs:
            for key, item in attrs.items():
                paragraph.set(key, item)
        sub_list.append(paragraph)
        self.group.section.mark_dirty()

    @HwpxOxmlMemo.text.setter  # type: ignore[attr-defined, misc]
    def text(self, value: str) -> None:
        self.set_text(value)

    def remove(self) -> None:
        """Remove the memo: its field's two controls and the memo text they hold. The text the
        field spans stays."""

        _remove_field(self.group.section.element, self.element)
        self.group.section.mark_dirty()


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
        # 각주·미주의 속성명은 "instId"(스키마 NoteType·한/글). "instid"는
        # 6.6 이하 python-hwpx가 각주·미주에 쓰던 철자라 읽기만 한다.
        return self.element.get("instId") or self.element.get("instid")

    @property
    def text(self) -> str:
        """Return the note body text."""
        return "".join(_text_element_content(t) for t in self.element.findall(f".//{_HP}t"))

    @text.setter
    def text(self, value: str) -> None:
        """Replace the note body text.

        The gold-shaped body (각주/미주 style paragraph with the leading
        ``<hp:autoNum>`` control real Hancom requires to render the note) is
        preserved: only text content is replaced.
        """
        sublist = self.element.find(f"{_HP}subList")
        if sublist is None:
            attrs = _default_sublist_attributes()
            attrs["vertAlign"] = "TOP"
            sublist = _append_child(self.element, f"{_HP}subList", attrs)
        paragraphs = sublist.findall(f"{_HP}p")
        template = paragraphs[0] if paragraphs else None
        p_attrs = (
            dict(template.attrib)
            if template is not None
            else {"id": "0", **_DEFAULT_PARAGRAPH_ATTRS}
        )
        first_run = template.find(f"{_HP}run") if template is not None else None
        run_attrs = dict(first_run.attrib) if first_run is not None else {"charPrIDRef": "0"}
        auto_num = (
            first_run.find(f"{_HP}ctrl") if first_run is not None else None
        )
        for p in paragraphs:
            sublist.remove(p)
        paragraph = _append_child(sublist, f"{_HP}p", p_attrs)
        run = _append_child(paragraph, f"{_HP}run", run_attrs)
        if auto_num is not None:
            run.append(auto_num)
        set_text_with_tabs(_append_child(run, f"{_HP}t", {}), value)
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
