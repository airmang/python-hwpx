# SPDX-License-Identifier: Apache-2.0
"""Authoring surface for ``hp:dutmal``(덧말)/``hp:compose``(글자 겹치기),
cycle 6.9 train 34.

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

from typing import TYPE_CHECKING, Sequence
import xml.etree.ElementTree as ET

from lxml import etree as LET  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

from . import body
from ._document_primitives import _HP
from .objects import HwpxOxmlInlineObject

if TYPE_CHECKING:
    from .paragraph import HwpxOxmlParagraph


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
    """

    slots = [
        body.ComposedCharacterSlot(pr_id_ref=int(ref))
        for ref in (char_pr_id_refs or ())
    ]
    composed = body.ComposedCharacter(
        tag=f"{_HP}compose",
        circle_type=circle_type,
        char_sz=char_sz,
        compose_type=compose_type,
        char_pr_cnt=len(slots) or None,
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

    Low-confidence axis, honestly flagged: reverse-engineered from a
    *single* real-corpus sample (``reader_writer__SimpleDutmal.hwpx``),
    confirmed a first-class Hancom editor menu item by the macOS menu scan
    (editor surface inventory, cycle 6.8 train 29) but otherwise
    unobserved elsewhere in this project's corpora. *sz_ratio*/*option*
    default to that sample's own observed values (``0``/``0``) rather
    than the schema's stated ``xs:positiveInteger``/``fixed="4"`` -- real
    output already contradicts both schema claims once (DEV-041,
    ``docs/owpml-deviations.md``), so this module does not enforce them as
    validation rules; pass an explicit value to override.
    """

    dutmal = body.Dutmal(
        tag=f"{_HP}dutmal",
        pos_type=pos_type,
        sz_ratio=sz_ratio,
        option=option,
        style_id_ref=int(style_id_ref) if style_id_ref is not None else None,
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
