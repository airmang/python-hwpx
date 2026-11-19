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
    from ..model import Paragraph


def _offset(self: Any) -> "int | None":
    """Where it stands in its paragraph's text: the number of characters before it, counted as
    ``paragraph.text`` counts (``None`` when it is in no run of a paragraph). It takes no character, so it
    stands after character ``offset - 1`` and before character ``offset``."""

    from ..oxml.text_offsets import placed_offset

    return placed_offset(self)


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

    offset = property(_offset)

    @property
    def start(self) -> "int | None":
        """Where the field begins in its paragraph's text (``paragraph.text``'s count) -- :attr:`offset`, the
        characters before its begin; ``None`` when it is in no run of a paragraph."""

        return _offset(self)

    @property
    def end(self) -> "int | None":
        """Where the field ends: the characters before its ``fieldEnd`` in the paragraph holding it -- the
        begin's unless the field runs over paragraphs (:attr:`end_location` says which). ``None`` without an
        end. For a field within one paragraph, ``paragraph.text[start:end]`` is its text."""

        from ..oxml.text_offsets import offset_of

        paragraph = getattr(self._paragraph, "element", None)
        found = None
        if paragraph is not None:
            found = next((node for node in paragraph.iter() if node.tag.rsplit("}", 1)[-1] == "fieldEnd"
                          and node.get("beginIDRef") == self._element.get("id")), None)
        if found is None:
            found = _end_elsewhere(getattr(self._paragraph, "section", None), self._element)
        return None if found is None else offset_of(found)

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
        "_paragraph",
        "_end_location",
        "_text_elements",
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
        paragraph: "Paragraph | None" = None,
        end_location: FieldLocation | None = None,
        text_elements: "tuple[ET.Element, ...]" = (),
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
        self._paragraph = paragraph
        self._end_location = end_location
        self._text_elements = text_elements

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
        entered yet) shows the new one. One holding a tab or a line break is refused
        (``field-text-control-unsupported``), as ``add_form_field(prompt=)`` refuses it."""

        return self._prompt

    @prompt.setter
    def prompt(self, value: str) -> None:
        self._refresh(prompt=value)

    @property
    def memo(self) -> str:
        """The field's memo (도움말, ``HelpState``). Assigning it changes the memo; a tab or a line
        break in it is refused (``field-text-control-unsupported``)."""

        return self._memo

    @memo.setter
    def memo(self, value: str) -> None:
        self._refresh(memo=value)

    @property
    def editable(self) -> bool:
        """Whether the field may be filled in a form-protected document (양식 모드에서 편집 가능,
        ``hp:fieldBegin/@editable``). A field that does not say reads ``True``, the OWPML schema's
        default (7.0; 6.x read ``False``); Hancom writes the attribute on every field it saves.
        Assigning it writes ``"1"`` or ``"0"``."""

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
    def filled(self) -> bool:
        """Whether Hancom marks the field as filled in (``hp:fieldBegin/@dirty``): something was typed
        or filled into it, so it shows its content rather than its 안내문 (:attr:`prompt`).

        Read from the file as it is now. In the repository's Hancom-saved fixtures the 33 누름틀 holding
        entered text are ``"1"`` and the 16 showing their 안내문 or nothing are ``"0"``; a fill
        (``value = ...``, ``doc.fields.fill``) turns it on, and a field made around existing text
        (``add_form_field(start=, end=)``) is written with it on. A field that does not say reads ``False``,
        the OWPML schema's default."""

        return (self._element.get("dirty") or "").strip().lower() in ("1", "true")

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

    @property
    def paragraph(self) -> "Paragraph | None":
        """The paragraph holding the field's begin (a :class:`hwpx.model.Paragraph`): one of
        the body, a table cell, a text box or a header, where :attr:`location` points."""

        return self._paragraph

    @property
    def end_location(self) -> FieldLocation | None:
        """Where the field's ``<hp:fieldEnd>`` sits, located as :attr:`location` locates the
        begin; ``None`` when the field has no end (:attr:`has_end` is ``False``).

        Its paragraph is the begin's unless the field's text runs over paragraphs: then it is
        the later paragraph beside it that holds the end (compare ``paragraph_index``). The
        run holding the end is ``paragraph.runs[end_location.run_index]`` when it is the
        begin's paragraph. A snapshot, like :attr:`location`."""

        return self._end_location

    @property
    def text_elements(self) -> "tuple[ET.Element, ...]":
        """The ``<hp:t>`` elements holding the field's text, what :attr:`value` reads, in
        document order -- the escape hatch, like :attr:`element`, for code that locates or
        edits that text in the XML itself (after such an edit, call
        ``field.paragraph.clear_layout_cache()``). For a field running over paragraphs, those
        of the later paragraphs follow. Empty when the field holds no text. A snapshot: a
        fill (``value = ...``) writes new elements; read the field again for them."""

        return self._text_elements

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

        from ..oxml._paragraph_text_edit import live_holder

        # the section the box is in now (moved with its paragraph: that one), so the change is saved
        self._section = live_holder(self._draw_text, self._section)
        set_text_box_text(self._draw_text, self._section, value)

    @property
    def element(self) -> Any:
        return self._draw_text

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "text": self.text}

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"TextBoxField(name={self.name!r}, text={self.text!r})"


def field_parameters(field_begin: Any) -> tuple[FieldParameter, ...]:
    """The parameters a ``<hp:fieldBegin>`` carries (its ``hp:parameters``), in file order: each
    ``hp:*Param`` with its ``name`` and text. A field without them gives ``()``."""

    return tuple(
        FieldParameter(name=param.get("name", ""), value="".join(param.itertext()))
        for holder in field_begin
        if isinstance(holder.tag, str) and holder.tag.rsplit("}", 1)[-1] == "parameters"
        for param in holder.iter()
        if param is not holder and isinstance(param.tag, str) and param.tag.rsplit("}", 1)[-1].endswith("Param")
    )


@dataclass(frozen=True)
class FieldControl:
    """A field's start (``<hp:fieldBegin>``) read as written, whatever its kind (``run.content``).

    ``field_type`` is its ``type`` (``CLICK_HERE``, ``FORMULA``, ``DATE``, ``CROSSREF``, ``MAILMERGE``,
    ``MEMO``, ...), ``field_id`` its ``id``, ``name`` its ``name`` and ``parameters``
    the :class:`FieldParameter` entries of its ``hp:parameters``. ``element`` is the
    ``<hp:fieldBegin>``, the escape hatch. A snapshot: it does not follow later edits. A hyperlink
    comes as :class:`Hyperlink` and a memo held in its field as the memo instead; both read
    ``parameters`` too.
    """

    field_type: str
    field_id: str
    name: str
    parameters: tuple[FieldParameter, ...]
    element: Any = field(repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fieldType": self.field_type,
            "fieldId": self.field_id,
            "name": self.name,
            "parameters": [parameter.to_dict() for parameter in self.parameters],
        }


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

    offset = property(_offset)

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
        held = _live_section(self.element, self._section)
        # The name the bookmark has now: another object of the same bookmark may have renamed it since
        # this one was taken, and the links point at that name.
        old_name = self.element.get("name") or self.name
        if self.kind == "field":
            old_name = old_name.strip()  # as a field bookmark's name is read; a point's is read as written
        self.element.set("name", new_name)
        if held is None or not _in_document(self.element, held):
            # Removed from the document: the name is its own, and no hyperlink of the document points
            # at a bookmark that is not there (re-pointing them changed a document the bookmark left).
            return Bookmark(new_name, self.kind, self.text, self.location, self.element, held)
        held.mark_dirty()  # a section, or the master page holding the bookmark
        for holder in _document_holders(held):
            changed = False
            for begin in holder.element.iter(self.element.tag.rsplit("}", 1)[0] + "}fieldBegin"):
                if begin.get("type") == "HYPERLINK" and hyperlink_target(begin) == f"#{old_name}":
                    set_hyperlink_target(begin, f"#{new_name}")
                    changed = True
            if changed:
                holder.mark_dirty()
        return Bookmark(new_name, self.kind, self.text, self.location, self.element, held)

    def remove(self) -> None:
        """Remove the bookmark. A bookmark spanning text (``kind="field"``) loses its two
        marks and its text stays. The paragraph is laid out again."""

        from ..oxml._document_primitives import _clear_paragraph_layout_cache
        from ..oxml.hyperlink_form import field_end_in_paragraph, remove_mark

        held = _live_section(self.element, self._section)  # before the marks leave the tree
        attached = held is not None and _in_document(self.element, held)
        paragraphs = []
        if self.kind == "field":
            host = _host_paragraph(self.element)
            end = field_end_in_paragraph(host, self.element) if host is not None else None
            if end is None and attached:
                # In the begin's section, or where a move left the end (another section).
                for holder in [held, *(other for other in _document_holders(held) if other is not held)]:
                    end = _end_elsewhere(holder, self.element)
                    if end is not None:
                        holder.mark_dirty()
                        break
            elif end is None:
                # Taken out of the document: its end is in the piece taken out with it, if anywhere. An
                # end of the same id in the document belongs to a bookmark that is there (the one this
                # was copied from), and is not this one's to remove.
                end = _end_in_own_tree(self.element)
            if end is not None:
                paragraphs.append(remove_mark(end))
        paragraphs.append(remove_mark(self.element))
        for paragraph in paragraphs:
            if paragraph is not None:
                _clear_paragraph_layout_cache(paragraph)
        if attached and held is not None:  # one taken out leaves every section as it was
            held.mark_dirty()


def _live_section(element: Any, held: Any) -> Any:
    """The section holding *element* now (see ``hwpx.oxml._paragraph_text_edit.live_holder``): a
    bookmark taken before its paragraph, table, text box or note moved to another section is saved
    with the section it is in, not the one it was taken from."""

    from ..oxml._paragraph_text_edit import live_holder

    return live_holder(element, held)


def _in_document(element: Any, held: Any) -> bool:
    from ..oxml._paragraph_text_edit import in_document

    return in_document(element, held)


def _document_holders(held: Any) -> list[Any]:
    """The sections and master pages of the document *held* (one of them) belongs to."""

    document = getattr(held, "document", None)
    if document is None:
        return [held]
    return [*document.sections, *getattr(document, "master_pages", ())]


def _host_paragraph(element: Any) -> Any:
    node = element.getparent()
    while node is not None and node.tag.rsplit("}", 1)[-1] != "p":
        node = node.getparent()
    return node


def _end_in_own_tree(begin: Any) -> Any:
    """The ``fieldEnd`` naming *begin* in the tree *begin* hangs in (a piece taken out of a document)."""

    if not hasattr(begin, "getparent") or not begin.get("id"):
        return None
    top = begin
    while (parent := top.getparent()) is not None:
        top = parent
    namespace = begin.tag.rsplit("}", 1)[0] + "}"
    return next((end for end in top.iter(f"{namespace}fieldEnd") if end.get("beginIDRef") == begin.get("id")), None)


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

    offset = property(_offset)

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
        """The paragraph holding the link's start now: after a range holding the link moved to another
        paragraph (``move_range``), that one -- a change through a link taken before the move marked the
        paragraph it was taken from, and was not saved."""

        host = _host_paragraph(self._element) if hasattr(self._element, "getparent") else None
        if host is not None and host is not self._paragraph.element:
            self._paragraph = type(self._paragraph)(host, _live_section(host, self._paragraph.section))
        return self._paragraph

    @property
    def field_id(self) -> str:
        return self._element.get("id", "")

    @property
    def parameters(self) -> tuple[FieldParameter, ...]:
        """The link's field parameters as written (``Command``, ``Path`` ...), as
        :class:`FieldControl` reads every other field's."""

        return field_parameters(self._element)

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
        self.paragraph.section.mark_dirty()

    def _end(self) -> Any:
        from ..errors import HwpxValueError
        from ..oxml.hyperlink_form import field_end_in_paragraph

        end = field_end_in_paragraph(self.paragraph.element, self._element)
        if end is None:
            raise HwpxValueError(
                "the hyperlink does not end in its paragraph",
                code="ref-link-end-missing",
                suggestion="Edit a link that runs over paragraphs in the XML (link.element).",
            )
        return end

    def _text_nodes(self) -> list[Any]:
        from ..oxml.hyperlink_form import between_marks

        return [child for _run, child in between_marks(self.paragraph.element, self._element, self._end())
                if child.tag.rsplit("}", 1)[-1] == "t"]

    @property
    def text(self) -> str:
        from ..oxml._document_primitives import _text_element_content
        from ..oxml.hyperlink_form import field_end_in_paragraph

        if field_end_in_paragraph(self.paragraph.element, self._element) is None:
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
        _clear_paragraph_layout_cache(self.paragraph.element)
        self.paragraph.section.mark_dirty()

    def remove(self, *, keep_text: bool = True) -> None:
        """Take the link out: its two controls go and its text stays as plain text in the
        link's character shape (``keep_text=False`` removes the text too). The paragraph
        is laid out again."""

        from ..oxml._document_primitives import _clear_paragraph_layout_cache
        from ..oxml.hyperlink_form import between_marks, field_end_in_paragraph, remove_mark

        end = field_end_in_paragraph(self.paragraph.element, self._element)
        if end is not None and not keep_text:
            for run, child in between_marks(self.paragraph.element, self._element, end):
                run.remove(child)
        if end is not None:
            remove_mark(end)
        remove_mark(self._element)
        _clear_paragraph_layout_cache(self.paragraph.element)
        self.paragraph.section.mark_dirty()

    def to_dict(self) -> dict[str, Any]:
        """``id``, ``url`` and ``type``, the dict ``paragraph.hyperlinks`` gave before 7.0, and ``text``."""

        return {"id": self.field_id, "url": self.url, "type": self._element.get("type", ""), "text": self.text}

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Hyperlink) and other._element is self._element

    def __hash__(self) -> int:
        return id(self._element)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Hyperlink(url={self.url!r}, text={self.text!r})"


class CrossReference:
    """A live view over one cross reference (``<hp:fieldBegin type="CROSSREF">``, 상호 참조).

    ``ref_type`` says what kind of thing it points at (``RefType``: ``TARGET_OUTLINE``,
    ``TARGET_BOOKMARK``, ``TARGET_TABLE`` ...) and ``content_type`` what it shows of
    it (``RefContentType``: ``OBJECT_TYPE_PAGE`` for the page number, ``OBJECT_TYPE_NUMBER``,
    ``OBJECT_TYPE_CONTENTS``, ``OBJECT_TYPE_UPDOWNPOS``). ``target`` is the target from
    ``RefPath`` without its ``?`` and ``;``: an outline paragraph is ``#<paragraph id>``, a
    table ``#<table id>``, a bookmark its name. ``text`` is what the document shows now
    (Hancom computes it again when it lays the page out), ``hyperlink`` whether
    clicking jumps to the target. ``element`` is the ``<hp:fieldBegin>``.

    ``content_type`` and ``hyperlink`` are settable and :meth:`set_target` points it
    elsewhere; ``remove()`` takes it out and leaves its text. When what it shows changes,
    its text is emptied: Hancom fills it in when it lays the page out, and python-hwpx
    writes no number it cannot know.
    """

    offset = property(_offset)

    __slots__ = ("_doc", "_element", "_location")

    def __init__(self, doc: "HwpxDocument", element: Any, location: FieldLocation) -> None:
        self._doc = doc
        self._element = element
        self._location = location

    def _parameter(self, name: str) -> str:
        for holder in self._element:
            if holder.tag.rsplit("}", 1)[-1] != "parameters":
                continue
            for param in holder:
                if param.get("name") == name:
                    return param.text or ""
        return ""

    @property
    def element(self) -> Any:
        return self._element

    @property
    def ref_type(self) -> str:
        return self._parameter("RefType")

    @property
    def content_type(self) -> str:
        return self._parameter("RefContentType")

    @content_type.setter
    def content_type(self, value: str) -> None:
        from .._document.fields import set_cross_reference

        set_cross_reference(self, content_type=value)

    @property
    def target(self) -> str:
        path = self._parameter("RefPath")
        target = path[1:] if path.startswith("?") else path
        return target[:-1] if target.endswith(";") else target

    def set_target(self, target: Any) -> None:
        """Point the cross reference at *target*: an outline paragraph (개요, ``TARGET_OUTLINE``),
        a bookmark (a :class:`Bookmark` or its name, ``TARGET_BOOKMARK``) or a table
        (``TARGET_TABLE``) of this document, written as Hancom writes each. Its text is emptied
        for Hancom to fill in. Other targets are refused (``ref-cross-reference-target-unsupported``):
        python-hwpx has seen no Hancom file pointing at them."""

        from .._document.fields import set_cross_reference

        set_cross_reference(self, target=target)

    @property
    def text(self) -> str:
        from .._document.fields import cross_reference_text

        return cross_reference_text(self._doc, self._element)

    @property
    def hyperlink(self) -> bool:
        return self._parameter("RefHyperLink").strip().lower() in ("1", "true")

    @hyperlink.setter
    def hyperlink(self, value: bool) -> None:
        from .._document.fields import set_cross_reference

        set_cross_reference(self, hyperlink=value)

    @property
    def location(self) -> FieldLocation:
        """Where the cross reference was when it was read."""

        return self._location

    @property
    def parameters(self) -> tuple[FieldParameter, ...]:
        return tuple(
            FieldParameter(name=param.get("name", ""), value=param.text or "")
            for holder in self._element
            if holder.tag.rsplit("}", 1)[-1] == "parameters"
            for param in holder
        )

    def remove(self, *, keep_text: bool = True) -> None:
        """Take the cross reference out (its begin and end): the text it shows stays as plain
        text, or goes too with ``keep_text=False``. The paragraph is laid out again."""

        from .._document.fields import remove_form_field

        remove_form_field(self._doc, self._element, keep_text=keep_text)

    def to_dict(self) -> dict[str, Any]:
        return {
            "refType": self.ref_type,
            "contentType": self.content_type,
            "target": self.target,
            "text": self.text,
            "hyperlink": self.hyperlink,
            "location": self.location.to_dict(),
        }

    def __eq__(self, other: object) -> bool:
        return isinstance(other, CrossReference) and other._element is self._element

    def __hash__(self) -> int:
        return id(self._element)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"CrossReference(ref_type={self.ref_type!r}, target={self.target!r}, text={self.text!r})"


@dataclass(frozen=True)
class TocEntry:
    """One entry of a table of contents (차례), read as written.

    ``text`` is what the entry shows before its tab (the heading's number and text, ``1. 개요``),
    ``page`` what it shows after it (the page number Hancom last wrote; empty while python-hwpx
    leaves it for Hancom to fill in), ``level`` the level of its 차례 N style (``None`` when its
    style is no 차례 N) and ``target`` where it links (``#<paragraph id>``; empty for an entry that
    does not link). ``paragraph`` is the entry's paragraph.
    """

    text: str
    level: int | None
    page: str
    target: str
    paragraph: Any = field(repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "level": self.level, "page": self.page, "target": self.target}


class TableOfContents:
    """A live view over one table of contents (``<hp:fieldBegin type="TABLEOFCONTENTS">``, 차례).

    ``title`` is the text after the field's start (``<제목 차례>``), ``entries`` its entries
    (:class:`TocEntry`), ``levels`` how many outline levels it collects (``ContentsLevel``),
    ``hyperlink`` whether its entries link to their headings and ``leader`` the tab leader before
    the page numbers. ``refresh_on_open`` is the field's ``dirty`` mark: while it is on, Hancom
    builds the table again -- entries, styles and page numbers -- the next time it opens the
    document; it is settable. :meth:`rebuild` rewrites the heading entries from the outline as it is
    now, page numbers left for Hancom; :meth:`remove` takes the table out. ``element`` is the
    ``<hp:fieldBegin>``.
    """

    __slots__ = ("_doc", "_element")

    def __init__(self, doc: "HwpxDocument", element: Any) -> None:
        self._doc = doc
        self._element = element

    @property
    def element(self) -> Any:
        return self._element

    def _values(self) -> dict[str, str]:
        from ..tools.toc_author import _param_text, toc_command_values

        return toc_command_values(_param_text(self._element, "Command"))

    @property
    def paragraph(self) -> Any:
        """The paragraph holding the table's start (and its title)."""

        from ..tools.toc_author import _region

        return _region(self._doc, self._element)[0]

    @property
    def title(self) -> str:
        from ..tools.toc_author import toc_title

        return toc_title(self._doc, self._element)

    @property
    def entries(self) -> tuple[TocEntry, ...]:
        from ..tools.toc_author import toc_entries

        return toc_entries(self._doc, self._element)

    @property
    def levels(self) -> int | None:
        """How many outline levels it collects (``ContentsLevel``); ``None`` when it does not say."""

        value = self._values().get("ContentsLevel", "")
        return int(value) if value.isdigit() else None

    @property
    def hyperlink(self) -> bool:
        return self._values().get("ContentsHyperlink", "1") not in ("0", "false")

    @property
    def leader(self) -> str:
        """The tab leader before the page numbers (``"DASH"``, Hancom's dotted one, ``"NONE"`` …)."""

        from ..tools.toc_author import _TAB_LEADER_NAMES

        value = self._values().get("ContentsLeader", "3")
        return _TAB_LEADER_NAMES[int(value)] if value.isdigit() and int(value) < len(_TAB_LEADER_NAMES) else value

    @property
    def refresh_on_open(self) -> bool:
        """Whether Hancom builds the table again when it next opens the document (``dirty``)."""

        return (self._element.get("dirty") or "0").strip().lower() in ("1", "true")

    @refresh_on_open.setter
    def refresh_on_open(self, value: bool) -> None:
        from ..errors import HwpxValueError

        if not isinstance(value, bool):
            raise HwpxValueError(
                f"refresh_on_open must be True or False; got {value!r}",
                code="toc-refresh-value",
                suggestion="Pass True for Hancom to build the table again when it opens the document.",
            )
        wanted = "1" if value else "0"
        if self._element.get("dirty") != wanted:
            self._element.set("dirty", wanted)
            self.paragraph.section.mark_dirty()

    def rebuild(self) -> None:
        """Rewrite the heading entries from the outline paragraphs as they are now.

        One entry per outline paragraph of level 1 to :attr:`levels` (not marked 차례 숨기기), in
        document order: its number and text, its level's 차례 N style and the look of the entries
        the table had, linked to the heading when :attr:`hyperlink`. Page numbers are left empty
        and :attr:`refresh_on_open` is turned on, so Hancom fills them in (python-hwpx lays out no
        pages). Blocks after the heading entries ("<표 차례>" …) stay as they are."""

        from ..tools.toc_author import rebuild_toc

        rebuild_toc(self._doc, self._element)

    def remove(self) -> None:
        """Take the table out: its title, entries and blocks go; what follows its end in that
        paragraph joins the paragraph it began in. That paragraph is laid out again."""

        from ..tools.toc_author import remove_toc

        remove_toc(self._doc, self._element)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "levels": self.levels,
            "hyperlink": self.hyperlink,
            "leader": self.leader,
            "refreshOnOpen": self.refresh_on_open,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    def __eq__(self, other: object) -> bool:
        return isinstance(other, TableOfContents) and other._element is self._element

    def __hash__(self) -> int:
        return id(self._element)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"TableOfContents(title={self.title!r}, entries={len(self.entries)})"



__all__ = [
    "Bookmark",
    "CellField",
    "CrossReference",
    "FieldLocation",
    "FieldParameter",
    "FormField",
    "FormulaField",
    "Hyperlink",
    "TableOfContents",
    "TextBoxField",
    "TocEntry",
]
