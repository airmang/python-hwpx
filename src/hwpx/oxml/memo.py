# SPDX-License-Identifier: Apache-2.0
"""Memo and note OXML wrappers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional
import xml.etree.ElementTree as ET

from ._document_primitives import (
    _require_text,
    SameElement,
    paragraph_attributes,
    _HP,
    _append_child,
    _clear_paragraph_layout_cache,
    _create_paragraph_element,
    _default_sublist_attributes,
    _element_local_name,
    _memo_id,
    _text_element_content,
)
from ._paragraph_text_edit import live_holder, live_paragraph, set_text_with_tabs

if TYPE_CHECKING:
    from ..objects.form_field import FieldParameter, Hyperlink
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
        memo_id: str | None = None,
        char_pr_id_ref: str | int | None = None,
        attributes: Optional[dict[str, str]] = None,
    ) -> "HwpxOxmlMemo":
        """Add a memo not anchored yet (``doc.notes.attach`` anchors it, moving it into its MEMO field).
        A memo's shape is its section's: ``section.properties.memo_shape_id_ref``."""

        if text is not None:
            _require_text(text)  # not text: refused before the memo is made (it stayed, unanchored)
        memo_attrs = dict(attributes or {})
        memo_attrs.setdefault("id", memo_id or _memo_id(self.section._ids))
        memo_element = _append_child(self.element, f"{_HP}memo", memo_attrs)
        _note_session_memo(self.section, memo_element)
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


class HwpxOxmlMemo(SameElement):
    """Represents a memo entry contained within a memo group.

    Hancom 2024 keeps a memo only in its MEMO field (the field's ``hp:subList``) and writes no
    ``hp:memogroup``. A memo-group memo is one not anchored yet (made by ``doc.notes.add_memo``
    without ``paragraph=``, or a copy), or one of a document python-hwpx 6.x wrote, which kept the
    memo in both places. Anchoring the first (``doc.notes.attach``) or changing the second moves it
    into its field and drops the memo-group copy, and this object then is that field's memo
    (:class:`HwpxOxmlFieldMemo`), so the two copies never disagree.
    """

    def __init__(self, element: ET.Element, group: HwpxOxmlMemoGroup):
        self.element = element
        self.group = group

    def _folded(self) -> bool:
        """Move this memo-group memo into the MEMO field anchoring it, if one does (see the class);
        True when it moved (this object is then a :class:`HwpxOxmlFieldMemo`)."""

        return type(self) is HwpxOxmlMemo and (_follow_folded(self) or fold_into_field(self))

    def _follow(self) -> bool:
        """True when this object wrapped a memo-group entry that has since been folded into its MEMO
        field -- by another object of the same memo (``doc.notes.attach``), or when its text moved to
        another section -- and now is that field's memo (:func:`_follow_folded`). The readers and
        ``remove`` ask first, so a second object of one memo reads and removes the memo that is saved."""

        return type(self) is HwpxOxmlMemo and _follow_folded(self)

    @property
    def id(self) -> str | None:
        if self._follow():
            return self.id
        return self.element.get("id")

    @id.setter
    def id(self, value: str | None) -> None:
        if self._folded():
            self.set_attribute("ID", value)
            return
        if value is None:
            if "id" in self.element.attrib:
                del self.element.attrib["id"]
                self.group.section.mark_dirty()
            return
        new_value = str(value)
        if self.element.get("id") != new_value:
            self.element.set("id", new_value)
            self.group.section.mark_dirty()

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "memo_shape_id_ref":  # 6.x per-memo shape: refused with its new place (7.0)
            from .._removed_names import removed_name_error

            error = removed_name_error("Memo", name)
            if error is not None:
                raise error
        object.__setattr__(self, name, value)

    @property
    def attributes(self) -> dict[str, str]:
        if self._follow():
            return self.attributes
        return dict(self.element.attrib)

    def set_attribute(self, name: str, value: str | int | None) -> None:
        if self._folded():  # the field's parameter of that meaning
            self.set_attribute(_FIELD_PARAMS.get(name, name), value)
            return
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

        if self._follow():
            return self._anchor_field()
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

        if self._follow():
            return self.paragraph
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
        if self._follow():
            return self.paragraphs
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
        if value is not None:
            _require_text(value)  # not text: refused before anything is written
        if self._folded():
            self.set_text(value, char_pr_id_ref=char_pr_id_ref)
            return
        desired = value or ""
        existing_char = char_pr_id_ref or self._infer_char_pr_id_ref()
        for child in list(self.element):
            if _element_local_name(child) in {"paraList", "p"}:
                self.element.remove(child)
        para_list = _append_child(self.element, f"{_HP}paraList", {})
        paragraph = _create_paragraph_element(
            desired,
            ids=self.group.section._ids,
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

        if self._follow():
            self.remove()
            return
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

        self._follow()
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

        self._follow()  # folded into its field through another object: that memo is the one copied
        target = _resolve_memo_section(self, section, caller="copy_to")
        others = _group_memos(target)
        position = _memo_index(index, len(others), caller="copy_to")
        if isinstance(self, HwpxOxmlFieldMemo):
            clone = self.element.makeelement(f"{_HP}memo", {})
            para_list = clone.makeelement(f"{_HP}paraList", {})
            clone.append(para_list)
            sub_list = self._sub_list()
            for node in (sub_list.findall(f"{_HP}p") if sub_list is not None else []):
                para_list.append(deepcopy(node))
        else:
            clone = deepcopy(self.element)
            clone.tail = None
            clone.attrib.pop(_FOLDED_INTO, None)
        clone.set("id", _memo_id(target._ids))
        _refresh_copied_paragraph_subtree_ids(clone, ids=target._ids)
        for node in clone.iter(f"{_HP}p"):
            _clear_paragraph_layout_cache(node)
        group = _ensure_memo_group(target)
        _insert_memo_element(group, clone, others, position)
        _note_session_memo(target, clone)  # not anchored yet: the save refuses it until attached
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


#: A memo-group memo's attribute -> the MEMO field parameter of the same meaning.
_FIELD_PARAMS = {"id": "ID", "memoShapeIDRef": "MemoShapeIDRef", "author": "Author", "createDateTime": "CreateDateTime"}


def _note_session_memo(section: "HwpxOxmlSection", memo: ET.Element) -> None:
    """Remember a memo-group memo made in this session (not read from the file): the save refuses it
    while no MEMO field anchors it, since Hancom keeps no memo outside its field."""

    document = getattr(section, "document", None)
    if document is None:
        return
    made = getattr(document, "_session_memo_ids", None)
    if made is None:
        made = set()
        document._session_memo_ids = made
    if memo.get("id"):
        made.add(str(memo.get("id")))


def _fill_field_from_entry(field: ET.Element, entry: ET.Element) -> None:
    """Make the MEMO field *field* hold the memo-group memo *entry* as Hancom keeps a memo: the field's
    ``hp:subList`` holds the memo's paragraphs. Its parameters stay as they are: a memo's shape is its
    section's, and Hancom writes ``MemoShapeIDRef=65535`` in every memo field."""

    from copy import deepcopy

    sub_list = field.find(f"{_HP}subList")
    if sub_list is None:
        sub_list = _append_child(field, f"{_HP}subList", {**_default_sublist_attributes(), "vertAlign": "TOP"})
    paragraphs = entry.findall(f".//{_HP}p")
    if paragraphs:
        for node in sub_list.findall(f"{_HP}p"):
            sub_list.remove(node)
        for node in paragraphs:
            copied = deepcopy(node)
            copied.tail = None
            copied.set("id", "0")  # Hancom numbers a memo field's paragraphs 0
            _clear_paragraph_layout_cache(copied)
            sub_list.append(copied)


def _in_one_of(element: ET.Element, roots: "list[ET.Element]") -> bool:
    """True while *element* hangs in one of *roots* (the document's sections as they are now)."""

    if not hasattr(element, "getparent"):
        return True  # a plain ElementTree element cannot say: it is kept
    top: Any = element
    while (parent := top.getparent()) is not None:
        top = parent
    return any(top is root for root in roots)


def _note_folded(entry: ET.Element, field: ET.Element, section: "HwpxOxmlSection") -> None:
    """Note, as the memo-group entry *entry* leaves its group, which field took it: an object still
    wrapping the entry finds the memo again. The field is remembered itself (on the document, under a
    token written on the entry), not by an id: a memo removed later and another one given its memo id or
    its field id is another field, and the old object must not write into it. The entry is out of the
    document from here on, so the token is never saved."""

    from uuid import uuid4

    owner = section.document if section.document is not None else section
    taken = owner.__dict__.setdefault("_folded_memo_fields", {})
    # A token no other document has: an entry folded into a field of another document (a memo of one
    # document anchored through another) must not find, under the same small number, a field of its own
    # document. Fields that have left the document are forgotten here, so the record does not grow with
    # every memo that is added and removed.
    live = [part.element for part in getattr(owner, "sections", [owner])]
    for token in [token for token, kept in taken.items() if not _in_one_of(kept, live)]:
        del taken[token]
    token = uuid4().hex
    taken[token] = field
    entry.set(_FOLDED_INTO, token)


def fold_into_field(
    memo: "HwpxOxmlMemo", field: ET.Element | None = None, section: "HwpxOxmlSection | None" = None
) -> bool:
    """Move the memo-group memo *memo* into the MEMO field anchoring it (*field* in *section*, or the
    one of its own section that names it) and drop its memo-group entry (a group left empty goes);
    *memo* becomes that field's :class:`HwpxOxmlFieldMemo`. False (nothing changes) when no field
    anchors it."""

    if not any(child is memo.element for child in memo.group.element):
        # Not an entry of its group any more (folded through another object, or removed): what it
        # holds is not the memo's text now, and writing it into a field put an old text back.
        return False
    if field is None:
        field = memo._anchor_field()
        section = memo.group.section
    if field is None or section is None:
        return False
    _fill_field_from_entry(field, memo.element)
    group = memo.group
    try:
        group.element.remove(memo.element)
    except ValueError:  # pragma: no cover - defensive branch
        return False
    _note_folded(memo.element, field, section)
    group.section.mark_dirty()
    group._cleanup()
    memo.__class__ = HwpxOxmlFieldMemo
    memo.element = field
    memo.group = _FieldMemoHost(section, field)  # type: ignore[assignment]
    section.mark_dirty()
    return True


#: On a memo-group entry that was folded into a MEMO field: the token its field is remembered under
#: (see :func:`_note_folded`). The entry is out of the document by then; the mark is never saved.
_FOLDED_INTO = "hwpx-folded-into-field"


def _follow_folded(memo: "HwpxOxmlMemo") -> bool:
    """Make the memo-group memo *memo* the memo of the field its entry was folded into: through another
    object of the same memo (``doc.notes.attach``), or when its text moved to another section and took
    the memo along (:func:`carry_memos`). An object taken before still wrapped the entry, so reading
    through it gave the old text and ``memo.text = ...`` changed nothing that is saved. False when the
    entry was not folded (still in its group, or removed), or its field is gone."""

    token = memo.element.get(_FOLDED_INTO)
    if not token:
        return False
    own = memo.group.section
    document = own.document
    field = (document if document is not None else own).__dict__.get("_folded_memo_fields", {}).get(token)
    if field is None:
        return False
    for section in (document.sections if document is not None else [own]):
        if any(node is field for node in section.element.iter(field.tag)):  # still in the document
            memo.__class__ = HwpxOxmlFieldMemo
            memo.element = field
            memo.group = _FieldMemoHost(section, field)  # type: ignore[assignment]
            return True
    return False


def carry_memos(root: ET.Element, sections: "list[HwpxOxmlSection]", target: "HwpxOxmlSection") -> int:
    """Fold the memo-group memos the MEMO fields under *root* anchor into those fields: content that moved
    to *target* takes its memos along inside its fields, as Hancom keeps them (no ``hp:memogroup`` is
    written). Returns how many were folded; a group left empty goes."""

    fields = {memo_field_id(field): field for field in memo_fields_in(root)}
    fields.pop(None, None)
    fields.pop("", None)
    if not fields:
        return 0
    moved = 0
    for section in sections:
        group = section.element.find(f"{_HP}memogroup")
        if group is None:
            continue
        for memo in [memo for memo in group.findall(f"{_HP}memo") if memo.get("id") in fields]:
            _fill_field_from_entry(fields[str(memo.get("id"))], memo)
            group.remove(memo)
            _note_folded(memo, fields[str(memo.get("id"))], target)
            moved += 1
            section.mark_dirty()
            target.mark_dirty()
        HwpxOxmlMemoGroup(group, section)._cleanup()
    return moved


def renew_copied_memos(root: ET.Element, sections: "list[HwpxOxmlSection]", target: "HwpxOxmlSection") -> int:
    """Give each MEMO field in the copied content *root* (not in the document yet) a memo of its own:
    the next memo number (its ``Number`` and ``zorder``, as ``doc.notes.attach`` numbers a memo -- Hancom
    takes memos of one number for one memo), and, when it names a memo of a memo group, that memo's text
    in the copied field under a new id (as Hancom keeps a memo: no ``hp:memogroup`` entry is written).
    Returns how many fields were renewed."""

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
        for param in field.iter(f"{_HP}stringParam"):  # "MEMO/<shape>/<number>/...": the number there too
            parts = (param.text or "").split("/")
            if param.get("name") == "Command" and len(parts) > 2 and parts[0] == "MEMO":
                parts[2] = str(highest)
                param.text = "/".join(parts)
        source = entries.get(memo_field_id(field) or "")
        if source is not None:
            _fill_field_from_entry(field, source)
        if memo_field_id(field) is not None:  # the copy is a memo of its own: its own id
            _set_memo_param(field, "stringParam", "ID", _memo_id(target._ids))
        target.mark_dirty()
    return len(fields)


def _memo_order(field: ET.Element) -> int:
    """The highest number the memo field carries: its ``zorder`` or its ``Number`` (a memo given a
    number of its own may have a lower ``zorder``, and the next memo was given that number again)."""

    values = [field.get("zorder", "0")]
    values += [param.text or "0" for param in field.iter(f"{_HP}integerParam") if param.get("name") == "Number"]
    highest = 0
    for value in values:
        try:
            highest = max(highest, int(value))
        except ValueError:
            continue
    return highest


def _set_memo_param(field: ET.Element, kind: str, name: str, value: str) -> None:
    for param in field.iter(f"{_HP}{kind}"):
        if param.get("name") == name:
            param.text = value


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

    def __init__(self, section: "HwpxOxmlSection", field_begin: ET.Element | None = None) -> None:
        self._section = section
        self._field_begin = field_begin

    @property
    def section(self) -> "HwpxOxmlSection":
        """The section holding the field now: the paragraph holding it may have moved to another one."""

        if self._field_begin is not None:
            self._section = live_holder(self._field_begin, self._section)
        return self._section

    @section.setter
    def section(self, value: "HwpxOxmlSection") -> None:
        self._section = value

    def _cleanup(self) -> None:
        return None


class HwpxOxmlFieldMemo(HwpxOxmlMemo):
    """A memo kept only in its MEMO field, as Hancom saves memos (and as HWP files converted to HWPX
    hold them): its text is the ``hp:fieldBegin``'s own ``hp:subList`` and its id, number, author and
    time are the field's parameters. There is no ``hp:memogroup`` entry. :attr:`element` is the
    ``hp:fieldBegin``."""

    def __init__(self, field_begin: ET.Element, section: "HwpxOxmlSection") -> None:
        super().__init__(field_begin, _FieldMemoHost(section, field_begin))  # type: ignore[arg-type]

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
    def parameters(self) -> "tuple[FieldParameter, ...]":
        """The field's parameters as written, in order (:class:`hwpx.objects.FieldParameter`), as
        :class:`hwpx.objects.FieldControl` reads every other field's; :attr:`attributes` gives them by name."""

        from ..objects.form_field import field_parameters

        return field_parameters(self.element)

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

        if value is not None:
            _require_text(value)  # not text: refused before anything is written
        sub_list = self._sub_list()
        if sub_list is None:
            sub_list = _append_child(self.element, f"{_HP}subList", _default_sublist_attributes())
        existing_char = char_pr_id_ref or self._infer_char_pr_id_ref()
        paragraphs = sub_list.findall(f"{_HP}p")
        attrs = dict(paragraphs[0].attrib) if paragraphs else None
        from .note_authoring import note_kinds_in_all, renumber_note_kinds

        owner = self.group.section
        note_kinds = note_kinds_in_all(owner, paragraphs)  # notes in the text that goes: the rest count again
        for paragraph in paragraphs:
            sub_list.remove(paragraph)
        renumber_note_kinds(owner, note_kinds)
        paragraph = _create_paragraph_element(
            value or "",
            ids=self.group.section._ids,
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

        from .note_authoring import note_kinds_in_document, renumber_note_kinds

        owner = self.group.section
        note_kinds = note_kinds_in_document(owner, self.element)  # notes in the memo's text go with it
        _remove_field(owner.element, self.element)
        owner.mark_dirty()
        renumber_note_kinds(owner, note_kinds)


def _offset(self: Any) -> "int | None":
    """Where it stands in its paragraph's text: the number of characters before it, counted as
    ``paragraph.text`` counts (``None`` when it is in no run of a paragraph). It takes no character, so it
    stands after character ``offset - 1`` and before character ``offset``; ``move_to(paragraph,
    offset=obj.offset)`` puts it back where it is."""

    from .text_offsets import placed_offset

    return placed_offset(self)


class HwpxOxmlNote(SameElement):
    """Wraps a ``<hp:footNote>`` or ``<hp:endNote>`` element."""

    if TYPE_CHECKING:
        paragraph: "HwpxOxmlParagraph"
    else:
        paragraph = live_paragraph  # the paragraph holding it now, also after a move

    def __init__(self, element: ET.Element, paragraph: "HwpxOxmlParagraph"):
        self.element = element
        self.paragraph = paragraph

    offset = property(_offset)

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
        _require_text(value)  # not text: refused before anything is written
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
            else paragraph_attributes("0")
        )
        first_run = template.find(f"{_HP}run") if template is not None else None
        run_attrs = dict(first_run.attrib) if first_run is not None else {"charPrIDRef": "0"}
        auto_num = (
            first_run.find(f"{_HP}ctrl") if first_run is not None else None
        )
        from .note_authoring import note_kinds_in_all, renumber_note_kinds

        holder = self.paragraph.section
        inner_kinds = note_kinds_in_all(holder, paragraphs)  # notes in the text that goes: the rest count again
        for p in paragraphs:
            sublist.remove(p)
        renumber_note_kinds(holder, inner_kinds)
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

        _require_text(text)  # not text: refused before anything is written
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
        p_attrs = dict(template.attrib) if template is not None else paragraph_attributes("0")
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

    def move_to(self, paragraph: "HwpxOxmlParagraph", *, offset: int | None = None) -> None:
        """Move the note's mark to character *offset* of *paragraph* (``None``: its end), a paragraph of the same
        document: after the controls already there, before the character, as :meth:`add_footnote` puts one.
        The note takes no character, so *offset* counts the same before and after the move, also within its
        own paragraph -- as an object's ``move_to(offset=)``. Notes of its kind are numbered again. Refused into a note, a header, a footer or a memo
        (``paragraph-move-place-unsupported``), into its own text -- a cell or a text box inside the note
        (``note-move-into-itself``; ``copy_to`` puts a copy there) -- or another document
        (``note-other-document-unsupported``). Everything is checked before anything changes."""

        from .text_ranges import move_note

        move_note(self, paragraph, offset)

    def copy_to(self, paragraph: "HwpxOxmlParagraph", *, offset: int | None = None) -> "HwpxOxmlNote":
        """Put a copy of the note (a new ``instId``) at character *offset* of *paragraph*, as :meth:`move_to`
        moves one, and return it."""

        from .text_ranges import copy_note

        return copy_note(self, paragraph, offset)
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
        _require_text(text)  # not text: refused before anything is written
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
        field_char_pr_id_ref: str | int | None = None,
    ) -> "Hyperlink":
        """Append a hyperlink to the note body paragraph and return it, as ``paragraph.hyperlinks``
        reads it (``body_paragraph.add_hyperlink``, which gives the link since 7.0).
        """
        return self.body_paragraph.add_hyperlink(url, display_text, char_pr_id_ref=char_pr_id_ref,
                                                 field_char_pr_id_ref=field_char_pr_id_ref)

__all__ = ["HwpxOxmlMemo", "HwpxOxmlMemoGroup", "HwpxOxmlNote"]
