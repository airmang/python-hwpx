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
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

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
        return self._name

    @property
    def prompt(self) -> str:
        """안내문 shown while the field is empty (absorbs the old ``instruction`` alias)."""

        return self._prompt

    @property
    def memo(self) -> str:
        return self._memo

    @property
    def editable(self) -> bool:
        return self._editable

    @property
    def value(self) -> str:
        """The field's current text content (replaces the old ``current_value`` key)."""

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
        """Whether a matching ``<hp:fieldEnd>`` was found for this field."""

        return self._has_end

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"FormField(field_id={self._field_id!r}, name={self._name!r}, "
            f"value={self._value!r}, is_placeholder={self._is_placeholder!r})"
        )


__all__ = ["FieldLocation", "FieldParameter", "FormField"]
