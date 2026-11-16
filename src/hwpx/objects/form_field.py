# SPDX-License-Identifier: Apache-2.0
"""``FormField`` — a live view over one 누름틀(click-here) form field control.

Replaces the 20-key dict ``add_form_field``/``fill_form_field``/
``list_form_fields`` returned in 5.x (design §2.3/§2.4 #2). The three id
aliases (``field_id``/``id``/``fieldid``) collapse to :attr:`FormField.field_id`,
the two prompt aliases (``prompt``/``instruction``) collapse to
:attr:`FormField.prompt`, the two type aliases (``field_type``/``control_type``)
collapse to :attr:`FormField.field_type`, and the five index keys
(``section_index``/``paragraph_index``/``paragraph_index_in_section``/
``run_index``/``child_index``) collapse to :class:`FieldLocation`.

The read-only snapshots of the other fields Hancom saves, located the same
way, live here too: :class:`FormulaField` (table formulas) and
:class:`Bookmark`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET

    from ..document import HwpxDocument


@dataclass(frozen=True)
class FieldLocation:
    """Where a :class:`FormField` sits in the document — 5 index keys, one type."""

    section_index: int
    paragraph_index: int
    paragraph_index_in_section: int
    run_index: int
    child_index: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "sectionIndex": self.section_index,
            "paragraphIndex": self.paragraph_index,
            "paragraphIndexInSection": self.paragraph_index_in_section,
            "runIndex": self.run_index,
            "childIndex": self.child_index,
        }


@dataclass(frozen=True)
class FieldParameter:
    """One ``<hp:...Param>`` entry carried on a field's ``<hp:fieldBegin>``."""

    name: str
    value: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "value": self.value}


class FormField:
    """A live view over one 누름틀(click-here) ``<hp:fieldBegin>`` control.

    ``value`` is settable: assigning it fills the field through the same
    style-preserving, placeholder-aware path as ``doc.fields.fill`` (it is a
    thin wrapper around :func:`hwpx._document.fields.fill_form_field`), not a
    raw text overwrite. Every other attribute is a snapshot taken when this
    object was built — the same snapshot semantics 5.x's dict already had, so
    nothing gets *less* fresh than before; re-read via ``doc.fields.all`` /
    ``doc.fields.fill`` for the current state.
    """

    __slots__ = (
        "_doc",
        "_element",
        "_field_id",
        "_name",
        "_prompt",
        "_memo",
        "_editable",
        "_value",
        "_field_type",
        "_is_placeholder",
        "_location",
        "_parameters",
        "_has_end",
    )

    def __init__(
        self,
        doc: "HwpxDocument",
        element: "ET.Element",
        *,
        field_id: str,
        name: str,
        prompt: str,
        memo: str,
        editable: bool,
        value: str,
        field_type: str,
        is_placeholder: bool,
        location: FieldLocation,
        parameters: tuple[FieldParameter, ...],
        has_end: bool,
    ) -> None:
        self._doc = doc
        self._element = element
        self._field_id = field_id
        self._name = name
        self._prompt = prompt
        self._memo = memo
        self._editable = editable
        self._value = value
        self._field_type = field_type
        self._is_placeholder = is_placeholder
        self._location = location
        self._parameters = parameters
        self._has_end = has_end

    @property
    def element(self) -> "ET.Element":
        """The wrapped ``<hp:fieldBegin>`` element — the escape hatch."""

        return self._element

    @property
    def field_id(self) -> str:
        return self._field_id

    @property
    def name(self) -> str:
        """The field's name, by which ``doc.fields.fill`` finds it. Assigning renames it."""

        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._refresh(name=value)

    @property
    def prompt(self) -> str:
        """안내문 shown while the field is empty (absorbs the old ``instruction`` alias).

        Assigning it changes the 안내문; a field still showing its old one (nothing
        entered yet) shows the new one."""

        return self._prompt

    @prompt.setter
    def prompt(self, value: str) -> None:
        self._refresh(prompt=value)

    @property
    def memo(self) -> str:
        """The field's memo (도움말, ``HelpState``). Assigning it changes the memo."""

        return self._memo

    @memo.setter
    def memo(self, value: str) -> None:
        self._refresh(memo=value)

    @property
    def editable(self) -> bool:
        """Whether the field may be filled in a form-protected document (양식 모드에서 편집 가능)."""

        return self._editable

    @editable.setter
    def editable(self, value: bool) -> None:
        self._refresh(editable=bool(value))

    def _refresh(self, **changes: Any) -> None:
        from .._document.fields import update_form_field

        fresh = update_form_field(self._doc, self._element, **changes)
        for slot in self.__slots__:
            if slot not in ("_doc", "_element"):
                setattr(self, slot, getattr(fresh, slot))

    def remove(self, *, keep_text: bool = True) -> None:
        """Remove the field (누름틀 지우기).

        Its begin and end controls go. With ``keep_text`` (the default) what the
        field holds stays as plain text; with ``keep_text=False`` it goes too. A
        field running over paragraphs loses those paragraphs with its content.
        The paragraphs are laid out again.
        """

        from .._document.fields import remove_form_field

        remove_form_field(self._doc, self._element, keep_text=keep_text)

    @property
    def value(self) -> str:
        """The field's current text content (replaces the old ``current_value`` key).

        A field whose content runs over paragraphs reads as their texts, one
        paragraph per line."""

        return self._value

    @value.setter
    def value(self, new_value: str) -> None:
        # Deferred import: hwpx._document.fields builds FormField instances at
        # module scope, so importing it back at module scope here would cycle.
        # By the time this setter actually runs both modules are fully loaded.
        from .._document.fields import fill_form_field

        result = fill_form_field(self._doc, str(new_value), field_id=self._field_id)
        self._value = result.after
        self._is_placeholder = result.field.is_placeholder

    @property
    def field_type(self) -> str:
        """The field's OWPML type (absorbs the old ``control_type`` alias)."""

        return self._field_type

    @property
    def is_placeholder(self) -> bool:
        return self._is_placeholder

    @property
    def location(self) -> FieldLocation:
        return self._location

    @property
    def parameters(self) -> tuple[FieldParameter, ...]:
        return self._parameters

    @property
    def has_end(self) -> bool:
        """Whether a matching ``<hp:fieldEnd>`` was found for this field, in its
        paragraph or in a later paragraph beside it."""

        return self._has_end

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"FormField(field_id={self._field_id!r}, name={self._name!r}, "
            f"value={self._value!r}, is_placeholder={self._is_placeholder!r})"
        )




class CellField:
    """A live view over one named table cell -- Hancom's cell field (``hp:tc@name``).

    ``text`` reads the cell's text and, when assigned, replaces the text of the
    cell's own paragraphs (the cell's character and paragraph shapes are kept);
    a table or object inside the cell keeps its text.
    ``cell`` is the table cell itself (:class:`hwpx.model.TableCell`) for anything else.
    """

    __slots__ = ("_cell",)

    def __init__(self, cell: Any) -> None:
        self._cell = cell

    @property
    def name(self) -> str:
        return str(self._cell.field_name)

    @property
    def text(self) -> str:
        return str(self._cell.text)

    @text.setter
    def text(self, value: str) -> None:
        self._cell.set_text(value)

    @property
    def cell(self) -> Any:
        return self._cell

    def to_dict(self) -> dict[str, Any]:
        row, col = self._cell.address
        return {"name": self.name, "text": self.text, "row": row, "column": col}

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"CellField(name={self.name!r}, text={self.text!r})"


class TextBoxField:
    """A live view over one named text box -- a field for Hancom (``hp:drawText@name``).

    Hancom lists a text box that has a name among its fields and fills it by that
    name. ``text`` reads the box's paragraphs, a line each, and, when assigned,
    replaces them with one paragraph holding the value, as Hancom fills the box:
    the box's first paragraph and its first run keep their shapes.
    ``element`` is the ``hp:drawText`` itself.
    """

    __slots__ = ("_draw_text", "_section")

    def __init__(self, draw_text: Any, section: Any) -> None:
        self._draw_text = draw_text
        self._section = section

    @property
    def name(self) -> str:
        return str(self._draw_text.get("name") or "")

    @property
    def text(self) -> str:
        from .._document.fields import text_box_text

        return text_box_text(self._draw_text)

    @text.setter
    def text(self, value: str) -> None:
        from .._document.fields import set_text_box_text

        set_text_box_text(self._draw_text, self._section, value)

    @property
    def element(self) -> Any:
        return self._draw_text

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "text": self.text}

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"TextBoxField(name={self.name!r}, text={self.text!r})"


@dataclass(frozen=True)
class FormulaField:
    """One table formula Hancom saved (``<hp:fieldBegin type="FORMULA">``), read as written.

    The values are Hancom's own parameters, not recomputed: ``formula`` keeps
    Hancom's notation as written (``=SUM(A1:A3)``, ``=SUM(?1:?3)``),
    ``last_result`` is the value Hancom last
    computed and ``value`` is the text the document shows. ``cell_address`` is
    the ``(row, column)`` of the table cell holding the formula, ``None`` when it
    sits in an ordinary paragraph. ``element`` is the ``<hp:fieldBegin>``.
    """

    field_id: str
    formula: str
    result_format: str
    last_result: str
    command: str
    value: str
    location: FieldLocation
    cell_address: tuple[int, int] | None
    parameters: tuple[FieldParameter, ...]
    element: Any = field(repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fieldId": self.field_id,
            "formula": self.formula,
            "resultFormat": self.result_format,
            "lastResult": self.last_result,
            "command": self.command,
            "value": self.value,
            "location": self.location.to_dict(),
            "cellAddress": list(self.cell_address) if self.cell_address is not None else None,
            "parameters": [parameter.to_dict() for parameter in self.parameters],
        }


@dataclass(frozen=True)
class Bookmark:
    """A bookmark and where it starts.

    Hancom saves a bookmark in one of two forms, and ``kind`` names the form:
    ``"point"`` is ``<hp:ctrl><hp:bookmark name=".."/></hp:ctrl>`` and ``"field"``
    is a ``<hp:fieldBegin type="BOOKMARK" name="..">`` paired with its
    ``<hp:fieldEnd>``. ``text`` is the text between that begin and end, one line
    per paragraph when they are paragraphs apart; Hancom often writes the pair
    with nothing between, and a point bookmark has no text. ``element`` is the
    ``<hp:bookmark>`` or ``<hp:fieldBegin>``.
    """

    name: str
    kind: Literal["point", "field"]
    text: str
    location: FieldLocation
    element: Any = field(repr=False, compare=False)
    _section: Any = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "text": self.text,
            "location": self.location.to_dict(),
        }

    def rename(self, name: str) -> "Bookmark":
        """Give the bookmark the name *name* and return it so named.

        The document's hyperlinks to the bookmark (``#old``) are pointed at the new
        name, so they keep reaching it.
        """

        from ..errors import HwpxValueError
        from ..oxml.hyperlink_form import hyperlink_target, set_hyperlink_target

        new_name = str(name).strip()
        if not new_name:
            raise HwpxValueError(
                "a bookmark name must not be empty",
                code="ref-bookmark-name-empty",
                suggestion="Pass the new name.",
            )
        self.element.set("name", new_name)
        for section in _document_sections(self._section):
            changed = False
            for begin in section.element.iter(self.element.tag.rsplit("}", 1)[0] + "}fieldBegin"):
                if begin.get("type") == "HYPERLINK" and hyperlink_target(begin) == f"#{self.name}":
                    set_hyperlink_target(begin, f"#{new_name}")
                    changed = True
            if changed or section is self._section:
                section.mark_dirty()
        return Bookmark(new_name, self.kind, self.text, self.location, self.element, self._section)

    def remove(self) -> None:
        """Remove the bookmark. A bookmark spanning text (``kind="field"``) loses its two
        marks and its text stays. The paragraph is laid out again."""

        from ..oxml._document_primitives import _clear_paragraph_layout_cache
        from ..oxml.hyperlink_form import field_end_in_paragraph, remove_mark

        paragraphs = []
        if self.kind == "field":
            host = _host_paragraph(self.element)
            end = field_end_in_paragraph(host, self.element) if host is not None else None
            if end is None:
                end = _end_elsewhere(self._section, self.element)
            if end is not None:
                paragraphs.append(remove_mark(end))
        paragraphs.append(remove_mark(self.element))
        for paragraph in paragraphs:
            if paragraph is not None:
                _clear_paragraph_layout_cache(paragraph)
        if self._section is not None:
            self._section.mark_dirty()


def _host_paragraph(element: Any) -> Any:
    node = element.getparent()
    while node is not None and node.tag.rsplit("}", 1)[-1] != "p":
        node = node.getparent()
    return node


def _end_elsewhere(section: Any, begin: Any) -> Any:
    """The ``fieldEnd`` naming *begin* anywhere in its section (an end in a later paragraph)."""

    if section is None or not begin.get("id"):
        return None
    namespace = begin.tag.rsplit("}", 1)[0] + "}"
    for end in section.element.iter(f"{namespace}fieldEnd"):
        if end.get("beginIDRef") == begin.get("id"):
            return end
    return None


def _document_sections(section: Any) -> list[Any]:
    if section is None:
        return []
    document = getattr(section, "document", None)
    return list(document.sections) if document is not None else [section]


class Hyperlink:
    """A live view over one hyperlink (``<hp:fieldBegin type="HYPERLINK">``) and its text.

    ``url`` is where it points, read as :meth:`hwpx.model.Paragraph.add_hyperlink`
    takes it (a web address, a ``mailto:`` address, or ``#name`` for the bookmark
    ``name``); ``text`` is the text the link spans. Both are settable: the target
    is written in Hancom's form, the text in the link's own character shape.
    ``remove()`` takes the link out and leaves its text. ``paragraph`` is the
    paragraph holding the link's start (a table cell's, a text box's or a note's
    own paragraph when it sits there).

    Before 7.0 ``paragraph.hyperlinks`` gave dicts; read ``link.url`` /
    ``link.field_id`` (or ``link.to_dict()``) instead of ``link["url"]`` / ``link["id"]``.
    """

    __slots__ = ("_element", "_paragraph")

    def __init__(self, element: Any, paragraph: Any) -> None:
        self._element = element
        self._paragraph = paragraph

    @property
    def element(self) -> Any:
        """The ``<hp:fieldBegin>`` — the escape hatch."""

        return self._element

    @property
    def paragraph(self) -> Any:
        return self._paragraph

    @property
    def field_id(self) -> str:
        return self._element.get("id", "")

    @property
    def url(self) -> str:
        from ..oxml.hyperlink_form import hyperlink_target

        return hyperlink_target(self._element)

    @url.setter
    def url(self, value: str) -> None:
        from ..errors import HwpxValueError
        from ..oxml.hyperlink_form import set_hyperlink_target

        target = str(value).strip()
        if not target:
            raise HwpxValueError(
                "a hyperlink target must not be empty",
                code="ref-link-target-empty",
                suggestion="Pass a web address, a mailto: address or #bookmark.",
            )
        set_hyperlink_target(self._element, target)
        self._paragraph.section.mark_dirty()

    def _end(self) -> Any:
        from ..errors import HwpxValueError
        from ..oxml.hyperlink_form import field_end_in_paragraph

        end = field_end_in_paragraph(self._paragraph.element, self._element)
        if end is None:
            raise HwpxValueError(
                "the hyperlink does not end in its paragraph",
                code="ref-link-end-missing",
                suggestion="Edit a link that runs over paragraphs in the XML (link.element).",
            )
        return end

    def _text_nodes(self) -> list[Any]:
        from ..oxml.hyperlink_form import between_marks

        return [child for _run, child in between_marks(self._paragraph.element, self._element, self._end())
                if child.tag.rsplit("}", 1)[-1] == "t"]

    @property
    def text(self) -> str:
        from ..oxml._document_primitives import _text_element_content
        from ..oxml.hyperlink_form import field_end_in_paragraph

        if field_end_in_paragraph(self._paragraph.element, self._element) is None:
            return ""
        return "".join(_text_element_content(node) for node in self._text_nodes())

    @text.setter
    def text(self, value: str) -> None:
        from ..oxml._document_primitives import _clear_paragraph_layout_cache, _sanitize_text
        from ..oxml._paragraph_text_edit import set_text_with_tabs

        nodes = self._text_nodes()
        if not nodes:
            end_ctrl = self._end().getparent()
            run = end_ctrl.getparent()
            node = run.makeelement(end_ctrl.tag.rsplit("}", 1)[0] + "}t", {})
            run.insert(list(run).index(end_ctrl), node)
            nodes = [node]
        for node in nodes:
            for child in list(node):
                node.remove(child)
            node.text = ""
        set_text_with_tabs(nodes[0], _sanitize_text(str(value)))
        _clear_paragraph_layout_cache(self._paragraph.element)
        self._paragraph.section.mark_dirty()

    def remove(self, *, keep_text: bool = True) -> None:
        """Take the link out: its two controls go and its text stays as plain text in the
        link's character shape (``keep_text=False`` removes the text too). The paragraph
        is laid out again."""

        from ..oxml._document_primitives import _clear_paragraph_layout_cache
        from ..oxml.hyperlink_form import between_marks, field_end_in_paragraph, remove_mark

        end = field_end_in_paragraph(self._paragraph.element, self._element)
        if end is not None and not keep_text:
            for run, child in between_marks(self._paragraph.element, self._element, end):
                run.remove(child)
        if end is not None:
            remove_mark(end)
        remove_mark(self._element)
        _clear_paragraph_layout_cache(self._paragraph.element)
        self._paragraph.section.mark_dirty()

    def to_dict(self) -> dict[str, Any]:
        """``id``, ``url`` and ``type``, the dict ``paragraph.hyperlinks`` gave before 7.0, and ``text``."""

        return {"id": self.field_id, "url": self.url, "type": self._element.get("type", ""), "text": self.text}

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Hyperlink) and other._element is self._element

    def __hash__(self) -> int:
        return id(self._element)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Hyperlink(url={self.url!r}, text={self.text!r})"


@dataclass(frozen=True)
class CrossReference:
    """One cross reference Hancom saved (``<hp:fieldBegin type="CROSSREF">``, 상호 참조), read as written.

    ``ref_type`` says what kind of thing it points at (``RefType``: ``TARGET_OUTLINE``,
    ``TARGET_BOOKMARK``, ``TARGET_TABLE`` ...) and ``content_type`` what it shows of
    it (``RefContentType``: ``OBJECT_TYPE_PAGE`` for the page number ...).
    ``target`` is the target from ``RefPath`` without its ``?`` and ``;``: a
    paragraph is ``#<paragraph id>``. ``text`` is what the document shows now
    (Hancom computes it again when it lays the page out), ``hyperlink`` whether
    clicking jumps to the target. ``element`` is the ``<hp:fieldBegin>``.
    """

    ref_type: str
    content_type: str
    target: str
    text: str
    hyperlink: bool
    location: FieldLocation
    parameters: tuple[FieldParameter, ...]
    element: Any = field(repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "refType": self.ref_type,
            "contentType": self.content_type,
            "target": self.target,
            "text": self.text,
            "hyperlink": self.hyperlink,
            "location": self.location.to_dict(),
        }



__all__ = [
    "Bookmark",
    "CellField",
    "CrossReference",
    "FieldLocation",
    "FieldParameter",
    "FormField",
    "FormulaField",
    "Hyperlink",
    "TextBoxField",
]
