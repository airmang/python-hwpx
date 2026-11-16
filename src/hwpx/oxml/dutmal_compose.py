# SPDX-License-Identifier: Apache-2.0
"""Authoring surface for ``hp:dutmal``(덧말)/``hp:compose``(글자 겹치기),
cycle 6.9 train 34, and (7.0) their reading, changing and removing behind the
live views :class:`hwpx.objects.Ruby` / :class:`hwpx.objects.ComposedCharacter`
(``paragraph.rubies``, ``doc.shapes.rubies`` …).

Every change that alters what a paragraph shows (the texts, the frame, the
position, removal) drops the line layout cache of that paragraph and of the
paragraphs holding it (a cell's table's paragraph), as the other edits do.

``paragraph.py``'s owner file sits at its 1600-line modularization cap
(the same situation ``header_compat.py``'s own docstring documents for
``header_part.py``) -- these two ``add_*`` methods are attached to
``HwpxOxmlParagraph`` as plain class-attribute assignments in
``paragraph.py``, matching the pattern ``objects.py`` already uses for
``add_line``/``add_polygon``/etc (``paragraph.py`` hit this same wall once
before and ``objects.py`` absorbed the shape-authoring overflow then --
this module is the same escape valve, used again because ``objects.py``
itself had no headroom left either, 1526/1600 measured before this module
existed).

Both build their element through the same read-model round-trip path
(``hwpx.oxml.body.ComposedCharacter``/``Dutmal`` + their ``_*_to_xml``
serializers) that parses real documents, so authored output and parsed
output share one code path -- see ``body.py``'s own docstrings for the
corpus evidence each is built against (``ComposedCharacter``:
``SimpleCompose.hwpx``, commit ``6f88e2e``; ``Dutmal``:
``SimpleDutmal.hwpx``, DEV-041, this train).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence, cast
import xml.etree.ElementTree as ET

from lxml import etree as LET  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

from . import body
from ._document_primitives import _HP
from .objects import HwpxOxmlInlineObject

if TYPE_CHECKING:
    from ..objects.highlight import ComposedCharacter, Ruby
    from ..objects.results import Alignment
    from .paragraph import HwpxOxmlParagraph

#: Hancom's ``hp:compose``: ten ``hp:charPr`` slots, the unused ones pointing nowhere.
COMPOSE_SLOTS = 10
EMPTY_COMPOSE_SLOT = 4294967295


def _paragraph_add_composed_character(
    self: "HwpxOxmlParagraph",
    compose_text: str,
    char_pr_id_refs: Sequence[str | int] | None = None,
    *,
    circle_type: str | None = None,
    char_sz: int | None = None,
    compose_type: str | None = None,
    run_attributes: dict[str, str] | None = None,
    char_pr_id_ref: str | int | None = None,
) -> HwpxOxmlInlineObject:
    """Insert ``<hp:compose>`` -- 글자 겹치기(원문자·합자).

    *char_pr_id_refs* is the (usually zero- or one-item) list of
    ``hh:charPr`` ids ``hp:compose/hp:charPr`` slots reference (ParaList
    XML schema.xml:538-543) -- distinct from *char_pr_id_ref*, which is
    the *run's own* ``charPrIDRef`` (the run this element sits inside,
    matching every other ``add_*`` inline-object method's own contract).

    Written as Hancom writes it: ten slots (the unused ones ``4294967295``)
    and, where not given, the values Hancom gives a new one --
    ``circleType="SHAPE_CIRCLE"``, ``charSz="-4"``, ``composeType="SPREAD"``.
    """

    refs = [int(ref) for ref in (char_pr_id_refs or ())]
    refs += [EMPTY_COMPOSE_SLOT] * (COMPOSE_SLOTS - len(refs))
    slots = [body.ComposedCharacterSlot(pr_id_ref=ref) for ref in refs]
    composed = body.ComposedCharacter(
        tag=f"{_HP}compose",
        circle_type=circle_type or "SHAPE_CIRCLE",
        char_sz=-4 if char_sz is None else char_sz,
        compose_type=compose_type or "SPREAD",
        char_pr_cnt=len(slots),
        compose_text=compose_text,
        slots=slots,
    )
    run = self._create_run_for_object(run_attributes, char_pr_id_ref=char_pr_id_ref)
    element = body._composed_character_to_xml(composed)
    if type(element) is not type(run):
        element = LET.fromstring(ET.tostring(element, encoding="utf-8"))
    run.append(element)
    self.section.mark_dirty()
    return HwpxOxmlInlineObject(element, self)


def _paragraph_add_dutmal(
    self: "HwpxOxmlParagraph",
    main_text: str,
    sub_text: str,
    *,
    pos_type: str = "TOP",
    align: str = "CENTER",
    sz_ratio: int | None = 0,
    option: int | None = 0,
    style_id_ref: str | int | None = None,
    run_attributes: dict[str, str] | None = None,
    char_pr_id_ref: str | int | None = None,
) -> HwpxOxmlInlineObject:
    """Insert ``<hp:dutmal>`` -- 덧말(루비형 주석 텍스트).

    Low-confidence axis, honestly flagged: inferred from a
    *single* real-corpus sample (``reader_writer__SimpleDutmal.hwpx``),
    confirmed a first-class Hancom editor menu item by the macOS menu scan
    (editor surface inventory, cycle 6.8 train 29) but otherwise
    unobserved elsewhere in this project's corpora. *sz_ratio*/*option*
    default to that sample's own observed values (``0``/``0``) rather
    than the schema's stated ``xs:positiveInteger``/``fixed="4"`` -- real
    output already contradicts both schema claims once (DEV-041,
    ``docs/owpml-deviations.md``), so this module does not enforce them as
    validation rules; pass an explicit value to override. Without
    *style_id_ref* the 덧말 takes style ``0``, as in that sample: Hancom
    writes ``styleIDRef`` on every 덧말.
    """

    dutmal = body.Dutmal(
        tag=f"{_HP}dutmal",
        pos_type=pos_type,
        sz_ratio=sz_ratio,
        option=option,
        style_id_ref=int(style_id_ref) if style_id_ref is not None else 0,
        align=align,
        main_text=main_text,
        sub_text=sub_text,
    )
    run = self._create_run_for_object(run_attributes, char_pr_id_ref=char_pr_id_ref)
    element = body._dutmal_to_xml(dutmal)
    if type(element) is not type(run):
        element = LET.fromstring(ET.tostring(element, encoding="utf-8"))
    run.append(element)
    self.section.mark_dirty()
    return HwpxOxmlInlineObject(element, self)


# ---------------------------------------------------------------------------
# reading, changing and removing a 덧말 or a 글자 겹치기 (hwpx.objects.Ruby /
# hwpx.objects.ComposedCharacter are the live views; the element logic is here)
# ---------------------------------------------------------------------------

#: ``hp:dutmal/@posType``: the small text over (``TOP``) or under (``BOTTOM``) the text.
RUBY_POSITIONS = ("TOP", "BOTTOM")
#: ``hp:compose/@circleType`` as the schema lists it (``SHAPE_REVERSAL_TIRANGLE`` is its spelling).
COMPOSE_FRAMES = (
    "CHAR",
    "SHAPE_CIRCLE",
    "SHAPE_REVERSAL_CIRCLE",
    "SHAPE_RECTANGLE",
    "SHAPE_REVERSAL_RECTANGLE",
    "SHAPE_TRIANGLE",
    "SHAPE_REVERSAL_TIRANGLE",
    "SHAPE_LIGHT",
    "SHAPE_RHOMBUS",
    "SHAPE_REVERSAL_RHOMBUS",
    "SHAPE_ROUNDED_RECTANGLE",
    "SHAPE_EMPTY_CIRCULATE_TRIANGLE",
    "SHAPE_THIN_CIRCULATE_TRIANGLE",
    "SHAPE_THICK_CIRCULATE_TRIANGLE",
)
#: ``hp:compose/@composeType``: spread inside the frame, or drawn over each other.
COMPOSE_ARRANGEMENTS = ("SPREAD", "OVERLAP")


def _local(node: Any) -> str:
    tag = getattr(node, "tag", None)
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _namespace(element: Any) -> str:
    tag = element.tag
    return tag.rsplit("}", 1)[0] + "}" if isinstance(tag, str) and "}" in tag else ""


def _refuse(message: str, code: str, suggestion: str, **context: Any) -> Exception:
    from ..errors import HwpxValueError

    return HwpxValueError(message, code=code, context=context or None, suggestion=suggestion)


def paragraph_run_marks(paragraph: "HwpxOxmlParagraph", local_name: str) -> list[Any]:
    """The ``hp:<local_name>`` elements the paragraph's own runs hold, in order (not those of
    paragraphs in its tables or objects)."""

    return [
        child
        for run in paragraph.element
        if _local(run) == "run"
        for child in run
        if _local(child) == local_name
    ]


def paragraph_rubies(paragraph: "HwpxOxmlParagraph") -> "tuple[Ruby, ...]":
    """The 덧말 of the paragraph's own runs, as :class:`hwpx.objects.Ruby` views."""

    from ..objects.highlight import Ruby

    return tuple(Ruby(element, paragraph) for element in paragraph_run_marks(paragraph, "dutmal"))


def paragraph_composed_characters(paragraph: "HwpxOxmlParagraph") -> "tuple[ComposedCharacter, ...]":
    """The 글자 겹치기 of the paragraph's own runs, as :class:`hwpx.objects.ComposedCharacter` views."""

    from ..objects.highlight import ComposedCharacter

    return tuple(ComposedCharacter(element, paragraph) for element in paragraph_run_marks(paragraph, "compose"))


def _check_text(value: object, *, code: str, what: str) -> str:
    """*value* as the text of a 덧말 or a 글자 겹치기: a non-empty str without control characters."""

    if not isinstance(value, str) or not value or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise _refuse(
            f"{what} must be a non-empty str without line breaks, tabs or control characters; got {value!r}",
            code,
            "Pass the text as one line. To take the mark away, call remove().",
            requested=repr(value),
        )
    return value


def _changed(view: Any) -> None:
    """The paragraph of *view* shows something else now: Hancom lays it out again."""

    from ._document_primitives import _clear_paragraph_layout_cache

    paragraph = view.paragraph
    _clear_paragraph_layout_cache(paragraph.element)
    paragraph.section.mark_dirty()


def ruby_part_text(element: Any, part: str) -> str:
    """The text of the 덧말 *element*'s ``hp:mainText`` or ``hp:subText`` (*part*)."""

    node = next((child for child in element if _local(child) == part), None)
    return "".join(node.itertext()) if node is not None else ""


def set_ruby_part_text(view: Any, part: str, value: object) -> None:
    """Write *value* into the ``hp:mainText`` or ``hp:subText`` (*part*) of the 덧말 *view*."""

    what = "the ruby's text" if part == "mainText" else "the ruby text"
    text = _check_text(value, code="shape-ruby-text-value", what=what)
    element = view.element
    node = next((child for child in element if _local(child) == part), None)
    if node is None:
        node = element.makeelement(f"{_namespace(element)}{part}", {})
        if part == "mainText":
            element.insert(0, node)
        else:
            element.append(node)
    if node.text == text and not len(node):
        return
    for child in list(node):
        node.remove(child)
    node.text = text
    _changed(view)


def set_ruby_position(view: Any, value: object) -> None:
    if not isinstance(value, str) or value not in RUBY_POSITIONS:
        raise _refuse(
            f"position must be one of {', '.join(RUBY_POSITIONS)}; got {value!r}",
            "shape-ruby-position-value",
            "Pass 'TOP' (over the text) or 'BOTTOM' (under it).",
            requested=repr(value),
        )
    if view.element.get("posType") != value:
        view.element.set("posType", value)
        _changed(view)


def ruby_alignment(element: Any) -> "Alignment":
    from ..objects.results import Alignment

    token = (element.get("align") or "CENTER").strip().upper()
    try:
        return Alignment(token)
    except ValueError:  # a token outside the schema's list reads as written
        return cast("Alignment", token)


def set_ruby_alignment(view: Any, value: object) -> None:
    from ..errors import HwpxValueError
    from ..objects.results import Alignment
    from .formatting import normalize_alignment

    try:
        token = normalize_alignment(value)
    except HwpxValueError:
        raise _refuse(
            f"alignment must be one of {', '.join(item.value for item in Alignment)}; got {value!r}",
            "shape-ruby-alignment-value",
            "Pass an Alignment, or its name such as 'CENTER' or 'DISTRIBUTE'.",
            requested=repr(value),
        ) from None
    if view.element.get("align") != token:
        view.element.set("align", token)
        _changed(view)


def set_compose_text(view: Any, value: object) -> None:
    text = _check_text(value, code="shape-compose-text-value", what="the composed characters")
    if view.element.get("composeText") != text:
        view.element.set("composeText", text)
        _changed(view)


def set_compose_frame(view: Any, value: object) -> None:
    if not isinstance(value, str) or value not in COMPOSE_FRAMES:
        raise _refuse(
            f"frame must be one of {', '.join(COMPOSE_FRAMES)}; got {value!r}",
            "shape-compose-frame-value",
            "Pass 'CHAR' for no frame, or a frame such as 'SHAPE_CIRCLE' or 'SHAPE_RECTANGLE'.",
            requested=repr(value),
        )
    if view.element.get("circleType") != value:
        view.element.set("circleType", value)
        _changed(view)


def set_compose_arrangement(view: Any, value: object) -> None:
    if not isinstance(value, str) or value not in COMPOSE_ARRANGEMENTS:
        raise _refuse(
            f"arrangement must be one of {', '.join(COMPOSE_ARRANGEMENTS)}; got {value!r}",
            "shape-compose-arrangement-value",
            "Pass 'SPREAD' (spread inside the frame) or 'OVERLAP' (drawn over each other).",
            requested=repr(value),
        )
    if view.element.get("composeType") != value:
        view.element.set("composeType", value)
        _changed(view)


def compose_char_pr_id_refs(element: Any) -> tuple[str, ...]:
    return tuple(
        reference
        for child in element
        if _local(child) == "charPr"
        and (reference := (child.get("prIDRef") or "").strip())
        and reference != str(EMPTY_COMPOSE_SLOT)
    )


def remove_run_mark(view: Any, text: str) -> None:
    """Take the 덧말 or 글자 겹치기 *view* out of its run; *text*, when not empty, takes its place
    as an ``hp:t`` in the same run (the run's character shape). A run left empty goes when its
    paragraph keeps another run, as Hancom leaves none behind."""

    element = view.element
    run = element.getparent()
    if run is None:
        return  # already taken out
    paragraph = view.paragraph.element
    if text:
        node = run.makeelement(f"{_namespace(element)}t", {})
        node.text = text
        run.insert(list(run).index(element), node)
    run.remove(element)
    runs = [child for child in paragraph if _local(child) == "run"]
    if not len(run) and len(runs) > 1 and run.getparent() is paragraph:
        paragraph.remove(run)
    _changed(view)
