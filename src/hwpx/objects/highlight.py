# SPDX-License-Identifier: Apache-2.0
"""Marks set on text in a run: ``Highlight`` (형광펜), ``Ruby`` (덧말) and
``ComposedCharacter`` (글자 겹치기).

``Highlight`` is a pure result payload (design table style: frozen dataclass +
``to_dict()``, ``TrackedChange``'s shape) rather than a live view — a highlight
is a text range, not a standalone element with its own settable property the
way ``CheckBox.checked`` is.

``Ruby`` and ``ComposedCharacter`` are live views over one element each
(``hp:dutmal``, ``hp:compose``), as ``Hyperlink`` is over its field: reading a
property reads the document as it is now, and assigning one writes the element
back. A change of what they show makes the paragraph holding them (and the
paragraph holding its table, for one in a cell) lose its line layout cache, so
Hancom lays it out again. The element logic lives in
:mod:`hwpx.oxml.dutmal_compose`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..model import Paragraph
    from .results import Alignment


@dataclass(frozen=True)
class Highlight:
    """One highlighted text range.

    ``color`` is the raw ``#RRGGBB`` OWPML value read from ``markpenBegin``,
    or ``None`` when the mark carries no ``color`` attribute — the schema
    (``ParaList XML schema.xml``) makes it optional, and real Hancom output
    has been observed dropping it on a re-save.

    ``paragraph`` is always set — unlike :class:`TrackedChange`, there is no
    low-level primitive that mints a ``Highlight`` without anchoring it to
    body text.
    """

    text: str
    color: str | None
    paragraph: "Paragraph | None" = None

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "color": self.color}


class _RunMark:
    """What :class:`Ruby` and :class:`ComposedCharacter` share: the element and its paragraph."""

    __slots__ = ("_element", "_paragraph")

    def __init__(self, element: Any, paragraph: "Paragraph") -> None:
        self._element = element
        self._paragraph = paragraph

    @property
    def element(self) -> Any:
        """The wrapped element — the escape hatch."""

        return self._element

    @property
    def paragraph(self) -> "Paragraph":
        """The paragraph holding it now (a table cell's, a text box's, a note's or a header's own
        paragraph when it sits there). Moved out of the paragraph it was taken from -- a range moved
        to another paragraph or section -- it is the paragraph it went to, so an edit through this
        object marks the section that is saved; it marked the one it was taken from before, and the
        change was reported and not saved."""

        held, element = self._paragraph, self._element
        if held is None or not hasattr(element, "getparent"):
            return held
        nearest = element.getparent()
        while nearest is not None and nearest.tag.rsplit("}", 1)[-1] != "p":
            nearest = nearest.getparent()
        if nearest is None or nearest is held.element:
            return held  # where it was taken from (or taken out with no paragraph around it)
        # the paragraph it is in now: another one, or a cell's paragraph inside the one it was taken from
        self._paragraph = type(held)(nearest, held.section)
        return self._paragraph

    def __eq__(self, other: object) -> bool:
        return type(other) is type(self) and other._element is self._element  # type: ignore[attr-defined]

    def __hash__(self) -> int:
        return id(self._element)


class Ruby(_RunMark):
    """A live view over one 덧말 (``hp:dutmal``): text with a smaller text set over or under it.

    ``text`` is the text (본말) and ``ruby_text`` the small text (덧말); both are
    settable. ``position`` is where the small text goes (``"TOP"`` over the
    text, ``"BOTTOM"`` under it) and ``alignment`` how it lines up with the
    text (:class:`~hwpx.objects.Alignment`); both are settable. ``size_ratio``
    is the small text's size in per cent of the text's, as Hancom wrote it
    (``0``: Hancom's default size). ``remove()`` takes the 덧말 away and leaves
    the text. Add one with ``doc.shapes.add_ruby``.
    """

    __slots__ = ()

    @property
    def text(self) -> str:
        """The text the 덧말 is set over or under (본말, ``hp:mainText``)."""

        from ..oxml.dutmal_compose import ruby_part_text

        return ruby_part_text(self._element, "mainText")

    @text.setter
    def text(self, value: str) -> None:
        from ..oxml.dutmal_compose import set_ruby_part_text

        set_ruby_part_text(self, "mainText", value)

    @property
    def ruby_text(self) -> str:
        """The small text (덧말, ``hp:subText``)."""

        from ..oxml.dutmal_compose import ruby_part_text

        return ruby_part_text(self._element, "subText")

    @ruby_text.setter
    def ruby_text(self, value: str) -> None:
        from ..oxml.dutmal_compose import set_ruby_part_text

        set_ruby_part_text(self, "subText", value)

    @property
    def position(self) -> str:
        """``"TOP"`` (the small text over the text) or ``"BOTTOM"`` (under it), ``posType``;
        ``"TOP"``, the schema default, when the file does not say."""

        return str(self._element.get("posType") or "TOP")

    @position.setter
    def position(self, value: str) -> None:
        from ..oxml.dutmal_compose import set_ruby_position

        set_ruby_position(self, value)

    @property
    def alignment(self) -> "Alignment":
        """How the small text lines up with the text (``align``): an
        :class:`~hwpx.objects.Alignment`, ``CENTER`` (the schema default) when the file does
        not say. Assign one, or its name (``"LEFT"``, ``"DISTRIBUTE"`` ...)."""

        from ..oxml.dutmal_compose import ruby_alignment

        return ruby_alignment(self._element)

    @alignment.setter
    def alignment(self, value: "Alignment | str") -> None:
        from ..oxml.dutmal_compose import set_ruby_alignment

        set_ruby_alignment(self, value)

    @property
    def size_ratio(self) -> int:
        """The small text's size in per cent of the text's (``szRatio``); 0 is Hancom's default."""

        value = (self._element.get("szRatio") or "0").strip()
        return int(value) if value.lstrip("-").isdigit() else 0

    def remove(self, *, keep_text: bool = True) -> None:
        """Take the 덧말 away. Its text stays where it was as plain text in the run's character
        shape; ``keep_text=False`` takes the text away too. The paragraph is laid out again."""

        from ..oxml.dutmal_compose import remove_run_mark

        remove_run_mark(self, self.text if keep_text else "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "rubyText": self.ruby_text,
            "position": self.position,
            "alignment": str(self.alignment),
            "sizeRatio": self.size_ratio,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Ruby(text={self.text!r}, ruby_text={self.ruby_text!r}, position={self.position!r})"


class ComposedCharacter(_RunMark):
    """A live view over one 글자 겹치기 (``hp:compose``): characters set over each other, in a frame
    or without one (원문자 ①, 합자).

    ``text`` is the characters (``composeText``), ``frame`` the frame drawn around them
    (``circleType``: ``"CHAR"`` for none, ``"SHAPE_CIRCLE"``, ``"SHAPE_RECTANGLE"`` ...) and
    ``arrangement`` whether they are spread inside the frame (``"SPREAD"``) or drawn over each
    other (``"OVERLAP"``); these three are settable. ``inner_size`` is the size step Hancom
    gives the characters inside the frame, as written (``charSz``: 0 their size, below 0
    smaller), and ``char_pr_id_refs`` the character shapes of its places that name one.
    ``remove()`` takes it away and leaves its characters as plain text. Add one with
    ``doc.shapes.add_composed_character``.
    """

    __slots__ = ()

    @property
    def text(self) -> str:
        """The characters set over each other (``composeText``)."""

        return str(self._element.get("composeText") or "")

    @text.setter
    def text(self, value: str) -> None:
        from ..oxml.dutmal_compose import set_compose_text

        set_compose_text(self, value)

    @property
    def frame(self) -> str:
        """The frame drawn around the characters (``circleType``); ``"SHAPE_CIRCLE"``, the
        schema default, when the file does not say. ``"CHAR"`` draws none."""

        return str(self._element.get("circleType") or "SHAPE_CIRCLE")

    @frame.setter
    def frame(self, value: str) -> None:
        from ..oxml.dutmal_compose import set_compose_frame

        set_compose_frame(self, value)

    @property
    def arrangement(self) -> str:
        """``"SPREAD"`` (the characters spread inside the frame) or ``"OVERLAP"`` (drawn over each
        other), ``composeType``; ``"SPREAD"`` when the file does not say."""

        return str(self._element.get("composeType") or "SPREAD")

    @arrangement.setter
    def arrangement(self, value: str) -> None:
        from ..oxml.dutmal_compose import set_compose_arrangement

        set_compose_arrangement(self, value)

    @property
    def inner_size(self) -> int:
        """The size step of the characters inside the frame, as Hancom wrote it (``charSz``)."""

        value = (self._element.get("charSz") or "0").strip()
        return int(value) if value.lstrip("-").isdigit() else 0

    @property
    def char_pr_id_refs(self) -> tuple[str, ...]:
        """The character shapes its places name (``hp:charPr/@prIDRef``), in order; the places
        Hancom leaves pointing nowhere (``4294967295``) are left out."""

        from ..oxml.dutmal_compose import compose_char_pr_id_refs

        return compose_char_pr_id_refs(self._element)

    def remove(self, *, keep_text: bool = True) -> None:
        """Take it away. Its characters stay where it was as plain text in the run's character
        shape; ``keep_text=False`` takes them away too. The paragraph is laid out again."""

        from ..oxml.dutmal_compose import remove_run_mark

        remove_run_mark(self, self.text if keep_text else "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "frame": self.frame,
            "arrangement": self.arrangement,
            "innerSize": self.inner_size,
            "charPrIDRefs": list(self.char_pr_id_refs),
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ComposedCharacter(text={self.text!r}, frame={self.frame!r}, arrangement={self.arrangement!r})"


__all__ = ["ComposedCharacter", "Highlight", "Ruby"]
