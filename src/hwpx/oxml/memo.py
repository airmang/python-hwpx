# SPDX-License-Identifier: Apache-2.0
"""Memo and note OXML wrappers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional
import xml.etree.ElementTree as ET

from ._document_primitives import (
    _DEFAULT_PARAGRAPH_ATTRS,
    _HP,
    _append_child,
    _clear_paragraph_layout_cache,
    _create_paragraph_element,
    _default_sublist_attributes,
    _element_local_name,
    _memo_id,
    _text_element_content,
)
from ._paragraph_text_edit import set_text_with_tabs

if TYPE_CHECKING:
    from ..objects.form_field import Hyperlink
    from .header import Style
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
    def memos(self) -> tuple["HwpxOxmlMemo", ...]:
        """The memos of this ``hp:memogroup``, in order."""
        return tuple(
            HwpxOxmlMemo(child, self)
            for child in self.element.findall(f"{_HP}memo")
        )

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
    def paragraphs(self) -> tuple["HwpxOxmlParagraph", ...]:
        """The memo's paragraphs (its text), in order."""
        return tuple(_wrap_paragraph(node, self.group.section) for node in self.element.findall(f".//{_HP}p"))

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

    def move_to(self, section: "int | HwpxOxmlSection", *, index: int | None = None) -> None:
        """Move this memo into the memo group of *section* (a section of the same document or its
        index), to be its memo number *index* there (``0 <= index <=`` the memos it already has;
        ``None``: the last). The group is made when the section has none, and a group left empty goes.

        A memo belongs in the section of its anchor (the MEMO field Hancom shows it at), and moves
        with it: moving the paragraph that holds the anchor (``paragraph.move_after``, ``obj.move_to``)
        carries the memo along. So this moves a memo that is not anchored, or puts one in its anchor's
        section or in another place in it; a memo anchored in another section is refused
        (``note-memo-anchor-elsewhere``), as is a memo Hancom keeps in its field (it is where its text
        is). This wrapper then belongs to the new group.
        """

        target = _resolve_memo_section(self, section, caller="move_to")
        anchor = _anchor_section(self)
        if isinstance(self, HwpxOxmlFieldMemo) or (anchor is not None and anchor.element is not target.element):
            raise _anchored_elsewhere(self, target)
        others = [memo for memo in _group_memos(target) if memo is not self.element]
        position = _memo_index(index, len(others), caller="move_to")
        source_group = self.group
        self.group.element.remove(self.element)
        group = _ensure_memo_group(target)
        _insert_memo_element(group, self.element, others, position)
        source_group.section.mark_dirty()
        target.mark_dirty()
        if source_group.element is not group:
            source_group._cleanup()
        self.group = HwpxOxmlMemoGroup(group, target)

    def copy_to(self, section: "int | HwpxOxmlSection", *, index: int | None = None) -> "HwpxOxmlMemo":
        """Put a copy of this memo into the memo group of *section* (a section of the same document or
        its index) as its memo number *index* (``None``: the last) and return it.

        The copy has a new id and fresh paragraph ids, the same text, shape and attributes, and no
        anchor yet: Hancom shows it once ``doc.notes.attach(paragraph, memo)`` anchors it. A memo
        Hancom keeps in its MEMO field is copied as a memo-group memo holding its text and shape.
        """

        from copy import deepcopy

        from ._document_primitives import _refresh_copied_paragraph_subtree_ids

        target = _resolve_memo_section(self, section, caller="copy_to")
        others = _group_memos(target)
        position = _memo_index(index, len(others), caller="copy_to")
        if isinstance(self, HwpxOxmlFieldMemo):
            clone = self.element.makeelement(f"{_HP}memo", {})
            shape = self.memo_shape_id_ref
            if shape:
                clone.set("memoShapeIDRef", shape)
            para_list = clone.makeelement(f"{_HP}paraList", {})
            clone.append(para_list)
            sub_list = self._sub_list()
            for node in (sub_list.findall(f"{_HP}p") if sub_list is not None else []):
                para_list.append(deepcopy(node))
        else:
            clone = deepcopy(self.element)
            clone.tail = None
        clone.set("id", _memo_id())
        _refresh_copied_paragraph_subtree_ids(clone)
        for node in clone.iter(f"{_HP}p"):
            _clear_paragraph_layout_cache(node)
        group = _ensure_memo_group(target)
        _insert_memo_element(group, clone, others, position)
        target.mark_dirty()
        return HwpxOxmlMemo(clone, HwpxOxmlMemoGroup(group, target))


def _resolve_memo_section(memo: "HwpxOxmlMemo", section: Any, *, caller: str) -> "HwpxOxmlSection":
    """*section* (a section or its index) as a section of the memo's document."""

    from ..errors import HwpxLookupError, HwpxTypeError, HwpxValueError
    from .section import HwpxOxmlSection

    own = memo.group.section
    document = own.document
    sections = list(document.sections) if document is not None else [own]
    if isinstance(section, int) and not isinstance(section, bool):
        if not -len(sections) <= section < len(sections):
            raise HwpxLookupError(
                f"section index {section} is out of range ({len(sections)} sections)",
                code="section-not-found",
                context={"caller": caller, "requested": section, "count": len(sections)},
                suggestion=f"Pass an index in 0..{len(sections) - 1}, or the section itself.",
            )
        return sections[section]
    if not isinstance(section, HwpxOxmlSection):
        raise HwpxTypeError(
            f"section must be a section or its index; got {type(section).__name__}",
            code="section-invalid-type",
            context={"caller": caller, "type": type(section).__name__},
            suggestion="Pass doc.sections[i] or an index.",
        )
    found = next((candidate for candidate in sections if candidate.element is section.element), None)
    if found is None:
        raise HwpxValueError(
            "the section is not in this memo's document",
            code="section-not-found",
            context={"caller": caller},
            suggestion="Pass a section of the document that holds the memo.",
        )
    return found


def _anchor_section(memo: "HwpxOxmlMemo") -> "HwpxOxmlSection | None":
    """The section of the memo's document holding a MEMO field that names the memo, or ``None``."""

    if isinstance(memo, HwpxOxmlFieldMemo):
        return memo.group.section
    memo_id = memo.id
    own = memo.group.section
    sections = list(own.document.sections) if own.document is not None else [own]
    if not memo_id:
        return None
    for section in sections:
        for field in section.element.iter(f"{_HP}fieldBegin"):
            if field.get("type") == "MEMO" and memo_field_id(field) == memo_id:
                return section
    return None


def _anchored_elsewhere(memo: "HwpxOxmlMemo", target: "HwpxOxmlSection") -> Exception:
    from ..errors import HwpxValueError

    kept_in_field = isinstance(memo, HwpxOxmlFieldMemo)
    return HwpxValueError(
        "a memo Hancom keeps in its MEMO field is where that field is" if kept_in_field
        else "the memo is anchored in another section: it stays in the section of its anchor",
        code="note-memo-anchor-elsewhere",
        context={"memoId": memo.id, "keptInField": kept_in_field},
        suggestion="메모는 고리(MEMO 누름틀)가 있는 구역에 둡니다. 고리를 담은 문단을 옮기면(paragraph.move_after) "
                   "메모도 따라갑니다. 다른 구역에 같은 메모가 필요하면 memo.copy_to(section)로 복사합니다.",
    )


def _group_memos(section: "HwpxOxmlSection") -> list[ET.Element]:
    group = section.element.find(f"{_HP}memogroup")
    return [] if group is None else group.findall(f"{_HP}memo")


def _memo_index(index: object, count: int, *, caller: str) -> int:
    from ..errors import HwpxLookupError, HwpxTypeError

    if index is None:
        return count
    if isinstance(index, bool) or not isinstance(index, int):
        raise HwpxTypeError(
            f"index must be an int or None; got {type(index).__name__}",
            code="note-memo-index-value",
            context={"caller": caller, "requested": repr(index)},
            suggestion="Pass the memo's place in the group from 0, or None for the last.",
        )
    if not 0 <= index <= count:
        raise HwpxLookupError(
            f"index {index} is outside 0..{count} (the memos the group holds)",
            code="note-memo-index-value",
            context={"caller": caller, "requested": index, "count": count},
            suggestion=f"Pass an index from 0 to {count}, or None for the last.",
        )
    return index


def _ensure_memo_group(section: "HwpxOxmlSection") -> ET.Element:
    group = section.element.find(f"{_HP}memogroup")
    if group is None:
        group = _append_child(section.element, f"{_HP}memogroup", {})
    return group


def _insert_memo_element(group: ET.Element, memo: ET.Element, others: list[ET.Element], position: int) -> None:
    """Put *memo* in *group* so that it comes at *position* among the memos *others* (the group's)."""

    if position < len(others):
        group.insert(list(group).index(others[position]), memo)
    else:
        group.append(memo)


def memo_fields_in(root: ET.Element) -> list[ET.Element]:
    """The MEMO fields (``hp:fieldBegin type="MEMO"``) at or under *root*."""

    return [node for node in root.iter(f"{_HP}fieldBegin") if node.get("type") == "MEMO"]


def carry_memos(root: ET.Element, sections: "list[HwpxOxmlSection]", target: "HwpxOxmlSection") -> int:
    """Move the memo-group memos the MEMO fields under *root* anchor into *target*'s memo group: content
    that moved to *target* takes its memos along, so each memo stays in the section of its anchor.
    Returns how many moved; a group left empty goes."""

    wanted = {memo_field_id(field) for field in memo_fields_in(root)} - {None, ""}
    if not wanted:
        return 0
    moved = 0
    for section in sections:
        if section.element is target.element:
            continue
        group = section.element.find(f"{_HP}memogroup")
        if group is None:
            continue
        for memo in [memo for memo in group.findall(f"{_HP}memo") if memo.get("id") in wanted]:
            group.remove(memo)
            _ensure_memo_group(target).append(memo)
            moved += 1
            section.mark_dirty()
            target.mark_dirty()
        HwpxOxmlMemoGroup(group, section)._cleanup()
    return moved


def renew_copied_memos(root: ET.Element, sections: "list[HwpxOxmlSection]", target: "HwpxOxmlSection") -> int:
    """Give each MEMO field in the copied content *root* (not in the document yet) a memo of its own:
    the next memo number (its ``Number`` and ``zorder``, as ``doc.notes.attach`` numbers a memo -- Hancom
    takes memos of one number for one memo), and, when it names a memo of a memo group, a copy of that
    memo under a new id in *target*'s memo group. Returns how many fields were renewed."""

    fields = memo_fields_in(root)
    if not fields:
        return 0
    highest = max((_memo_order(field) for section in sections for field in memo_fields_in(section.element)),
                  default=0)
    entries: dict[str, ET.Element] = {}
    for section in sections:
        for memo in section.element.findall(f"{_HP}memogroup/{_HP}memo"):
            if memo.get("id"):
                entries.setdefault(str(memo.get("id")), memo)
    for field in fields:
        highest += 1
        _set_memo_param(field, "integerParam", "Number", str(highest))
        field.set("zorder", str(highest))
        source = entries.get(memo_field_id(field) or "")
        if source is not None:
            _set_memo_param(field, "stringParam", "ID", _copy_memo_entry(source, target))
    return len(fields)


def _memo_order(field: ET.Element) -> int:
    try:
        return int(field.get("zorder", "0"))
    except ValueError:
        return 0


def _set_memo_param(field: ET.Element, kind: str, name: str, value: str) -> None:
    for param in field.iter(f"{_HP}{kind}"):
        if param.get("name") == name:
            param.text = value


def _copy_memo_entry(source: ET.Element, target: "HwpxOxmlSection") -> str:
    """Append a copy of the memo-group memo *source* to *target*'s group under a new id; return the id."""

    from copy import deepcopy

    from ._document_primitives import _refresh_copied_paragraph_subtree_ids

    clone = deepcopy(source)
    clone.tail = None
    clone.set("id", _memo_id())
    _refresh_copied_paragraph_subtree_ids(clone)
    _ensure_memo_group(target).append(clone)
    target.mark_dirty()
    return str(clone.get("id"))


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
            paragraph = _parent_of(root, run)
            if paragraph is not None:  # the control's room goes: the cache's line starts would be past it
                _clear_paragraph_layout_cache(paragraph)
            if not list(run) and _element_local_name(run) == "run":
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

    def __init__(self, section: "HwpxOxmlSection") -> None:
        self.section = section

    def _cleanup(self) -> None:
        return None


class HwpxOxmlFieldMemo(HwpxOxmlMemo):
    """A memo kept only in its MEMO field, as Hancom saves memos (and as HWP files converted to HWPX
    hold them): its text is the ``hp:fieldBegin``'s own ``hp:subList`` and its id, number, author and
    time are the field's parameters. There is no ``hp:memogroup`` entry. :attr:`element` is the
    ``hp:fieldBegin``."""

    def __init__(self, field_begin: ET.Element, section: "HwpxOxmlSection") -> None:
        super().__init__(field_begin, _FieldMemoHost(section))  # type: ignore[arg-type]

    def _param(self, name: str) -> ET.Element | None:
        for param in self.element.iter():
            if _element_local_name(param).endswith("Param") and param.get("name") == name:
                return param
        return None

    @property
    def id(self) -> str | None:
        return memo_field_id(self.element)

    @id.setter
    def id(self, value: str | None) -> None:
        self.set_attribute("ID", value)

    @property
    def memo_shape_id_ref(self) -> str | None:
        param = self._param("MemoShapeIDRef")
        return None if param is None else (param.text or None)

    @memo_shape_id_ref.setter
    def memo_shape_id_ref(self, value: str | int | None) -> None:
        self.set_attribute("MemoShapeIDRef", value)

    @property
    def attributes(self) -> dict[str, str]:
        """The field's parameters by name (``ID``, ``Number``, ``Author``, ``CreateDateTime``, ...)."""

        return {
            param.get("name", ""): param.text or ""
            for param in self.element.iter()
            if _element_local_name(param).endswith("Param") and param.get("name")
        }

    def set_attribute(self, name: str, value: str | int | None) -> None:
        """Set the field's parameter *name* (a new one is a string parameter), or remove it with ``None``."""

        param = self._param(name)
        parameters = self.element.find(f"{_HP}parameters")
        if value is None:
            if param is not None and parameters is not None and param in list(parameters):
                parameters.remove(param)
                parameters.set("cnt", str(len(parameters)))
                self.group.section.mark_dirty()
            return
        if param is None:
            if parameters is None:
                parameters = _append_child(self.element, f"{_HP}parameters", {"cnt": "0", "name": ""})
            param = _append_child(parameters, f"{_HP}stringParam", {"name": name})
            parameters.set("cnt", str(len(parameters)))
        if param.text != str(value):
            param.text = str(value)
            self.group.section.mark_dirty()

    def _anchor_field(self) -> ET.Element | None:
        return self.element

    def _sub_list(self) -> ET.Element | None:
        return self.element.find(f"{_HP}subList")

    @property
    def paragraphs(self) -> tuple["HwpxOxmlParagraph", ...]:
        """The memo's paragraphs (the text the field holds), in order."""
        sub_list = self._sub_list()
        if sub_list is None:
            return ()
        return tuple(_wrap_paragraph(node, self.group.section) for node in sub_list.findall(f"{_HP}p"))

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
        """Return the note body text, one line per paragraph of the note."""
        sub_list = self.element.find(f"{_HP}subList")
        paragraphs = sub_list.findall(f"{_HP}p") if sub_list is not None else []
        if not paragraphs:
            return "".join(_text_element_content(t) for t in self.element.findall(f".//{_HP}t"))
        return "\n".join(
            "".join(_text_element_content(t) for t in paragraph.iter(f"{_HP}t")) for paragraph in paragraphs
        )

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
    def number(self) -> int:
        """The note's number as Hancom counts it: each kind on its own, from 1, in
        document order, restarting where a section or an ``hp:newNum`` control says.

        In a section that numbers notes ``ON_PAGE`` (again on every page) the number
        depends on a page layout this engine does not make: it is the ``number`` the
        file holds, which Hancom sets to the per-page number when it saves (Hangul 2024)."""

        from .note_authoring import note_numbers

        section = self.paragraph.section
        document = section.document
        sections = [owner.element for owner in document.sections] if document is not None else [section.element]
        return note_numbers(sections).get(self.element, 0)

    @property
    def paragraphs(self) -> tuple["HwpxOxmlParagraph", ...]:
        """The note's own paragraphs, its text (the first starts with the note's number)."""

        sub_list = self.element.find(f"{_HP}subList")
        if sub_list is None:
            return ()
        return tuple(_wrap_paragraph(node, self.paragraph.section) for node in sub_list.findall(f"{_HP}p"))

    def add_paragraph(
        self,
        text: str = "",
        *,
        char_pr_id_ref: str | int | None = None,
        style: "int | str | Style | None" = None,
        para_pr_id_ref: str | int | None = None,
    ) -> "HwpxOxmlParagraph":
        """Add a paragraph holding *text* at the end of the note and return it.

        It takes the style, paragraph and character shape of the note's first paragraph
        (the 각주/미주 style) unless they are given: ``style`` (a name, a numeric id or a
        ``Style``, with its shapes unless those are passed), ``para_pr_id_ref``,
        ``char_pr_id_ref``, as every ``add_paragraph`` takes them. Hancom numbers only the
        first paragraph.
        """

        from .section import style_shape_refs

        style_id_ref, para_pr_id_ref, char_pr_id_ref = style_shape_refs(
            self.paragraph.section.document, style, para_pr_id_ref, char_pr_id_ref
        )
        sublist = self.element.find(f"{_HP}subList")
        if sublist is None:
            attrs = _default_sublist_attributes()
            attrs["vertAlign"] = "TOP"
            sublist = _append_child(self.element, f"{_HP}subList", attrs)
        paragraphs = sublist.findall(f"{_HP}p")
        template = paragraphs[0] if paragraphs else None
        p_attrs = dict(template.attrib) if template is not None else {"id": "0", **_DEFAULT_PARAGRAPH_ATTRS}
        first_run = template.find(f"{_HP}run") if template is not None else None
        run_attrs = dict(first_run.attrib) if first_run is not None else {"charPrIDRef": "0"}
        if char_pr_id_ref is not None:
            run_attrs["charPrIDRef"] = str(char_pr_id_ref)
        if para_pr_id_ref is not None:
            p_attrs["paraPrIDRef"] = str(para_pr_id_ref)
        if style_id_ref is not None:
            p_attrs["styleIDRef"] = str(style_id_ref)
        paragraph = _append_child(sublist, f"{_HP}p", p_attrs)
        run = _append_child(paragraph, f"{_HP}run", run_attrs)
        set_text_with_tabs(_append_child(run, f"{_HP}t", {}), text)
        self.paragraph.section.mark_dirty()
        return _wrap_paragraph(paragraph, self.paragraph.section)

    def remove(self) -> None:
        """Remove the note: its mark in the text and its content go together.

        The paragraph holding the mark is laid out again, and the notes of the
        same kind after it are numbered again (``number`` and the number their
        text starts with), as Hancom numbers them.
        """

        from .note_authoring import remove_note

        remove_note(self)

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
    ) -> "Hyperlink":
        """Append a hyperlink to the note body paragraph and return it, as ``paragraph.hyperlinks``
        reads it (``body_paragraph.add_hyperlink``).
        """
        body = self.body_paragraph
        body.add_hyperlink(url, display_text, char_pr_id_ref=char_pr_id_ref)
        return body.hyperlinks[-1]  # the link just appended is the paragraph's last

__all__ = ["HwpxOxmlMemo", "HwpxOxmlMemoGroup", "HwpxOxmlNote"]
