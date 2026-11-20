# SPDX-License-Identifier: Apache-2.0
"""Where Hangul puts the caret when it opens a document: ``settings.xml``'s ``ha:CaretPosition``.

``listIDRef`` names a paragraph list -- ``0`` is the body, every section's paragraphs counted on in one row
(``paraIDRef`` 20 in a three-section document of ``tests/fixtures/hancom_saved``) -- and ``pos`` counts as
Hangul counts a paragraph's text: a character one (two past the Basic Multilingual Plane), a tab eight, a
control or an object eight for each thing it holds. The body's first paragraph starts with its section's
settings and columns, so its text starts at ``pos="16"``, where a new document's caret stands.

What Hangul 2024 does with a caret that points at nothing (observed 2026-11): a list
or paragraph that is not there, or no ``ha:CaretPosition`` at all, opens at the body's first paragraph's text
start; a ``pos`` past its paragraph's end, at that end; a cell that is still there, in that cell. The lists
other than the body are numbered in an order the saved documents do not settle (cells, text boxes, notes),
so the engine sets and checks the caret in the body only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..errors import HwpxValueError

if TYPE_CHECKING:
    from .settings import CaretPosition

_HA = "{http://www.hancom.co.kr/hwpml/2011/app}"
_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _caret_element(document: Any) -> Any:
    settings = document.settings
    if settings is None:
        return None
    return settings.element.find(f"{_HA}CaretPosition")


def body_paragraphs(document: Any) -> list[Any]:
    """The paragraph elements of list 0: every section's own paragraphs, in order. Read from the section
    elements directly (any namespace prefix), not through ``section.paragraphs``: appending a paragraph reads
    only the last one, and a save checks the caret without wrapping the body."""

    return [child for section in document.sections for child in section.element
            if isinstance(child.tag, str) and child.tag.rsplit("}", 1)[-1] == "p"]


def hancom_position(paragraph: Any, offset: int) -> int | None:
    """Hangul's count of what stands in the paragraph element *paragraph* before character *offset* of its
    ``paragraph.text`` -- the controls and objects at *offset* included, as text put there goes after them --
    or ``None`` when it holds something whose count is not known (a tab outside ``hp:t``, a tracked change)."""

    from ._paragraph_text_edit import _hancom_positions

    pieces = _hancom_positions(paragraph)
    if pieces is None:
        return None
    characters = [position for position, piece in pieces if piece]
    if offset < len(characters):
        return characters[offset]
    return _hancom_end(paragraph)


def _hancom_end(paragraph: Any) -> int:
    from ._paragraph_text_edit import _LINE_TEXT_MARKS, _local

    position = 0
    for run in paragraph:
        if _local(run) != "run":
            continue
        for child in run:
            kind = _local(child)
            if kind == "t":
                for text in [child.text or ""] + [mark.tail or "" for mark in child]:
                    position += sum(2 if ord(character) > 0xFFFF else 1 for character in text)
                position += sum(_LINE_TEXT_MARKS.get(_local(mark), ("", 0))[1] for mark in child)
            elif kind:
                position += 8 * max(1, len(child)) if kind == "ctrl" else 8
    return position


def read_caret(document: Any) -> "CaretPosition | None":
    from .settings import parse_caret_position

    element = _caret_element(document)
    return None if element is None else parse_caret_position(element)


def _write(document: Any, list_id: int, paragraph: int, position: int) -> "CaretPosition":
    from .settings import parse_caret_position

    element = _caret_element(document)
    if element is None:
        settings = document.settings
        if settings is None:
            raise HwpxValueError(
                "the document has no settings.xml to hold the caret",
                code="document-caret-place-unsupported",
                suggestion="Hangul opens such a document at the body's start; nothing needs setting.",
            )
        element = settings.element.makeelement(f"{_HA}CaretPosition", {})
        settings.element.insert(0, element)
    values = {"listIDRef": str(list_id), "paraIDRef": str(paragraph), "pos": str(position)}
    if any(element.get(key) != value for key, value in values.items()):
        element.attrib.clear()  # Hangul's order: listIDRef, paraIDRef, pos
        for key, value in values.items():
            element.set(key, value)
        document.settings.mark_dirty()
    return parse_caret_position(element)


def body_start(document: Any) -> tuple[int, int, int]:
    """Where Hangul opens a document whose caret points at nothing: list 0, paragraph 0, the first paragraph's
    text start."""

    paragraphs = body_paragraphs(document)
    position = hancom_position(paragraphs[0], 0) if paragraphs else 0
    return (0, 0, position or 0)


def reset_caret(document: Any) -> "CaretPosition":
    return _write(document, *body_start(document))


def set_caret(document: Any, paragraph: Any, offset: int) -> "CaretPosition":
    from .formatting import _check_offset

    element = getattr(paragraph, "element", None)
    paragraphs = body_paragraphs(document)
    index = next((number for number, node in enumerate(paragraphs) if node is element), None)
    if index is None:
        raise HwpxValueError(
            "the caret is set in a paragraph of the body; a cell's, a text box's or a note's list number is not "
            "settled by the documents Hangul saved",
            code="document-caret-place-unsupported",
            suggestion="Pass a paragraph of doc.paragraphs (a section's own paragraphs).",
        )
    offset = _check_offset("offset", offset, 0, len(paragraph.text))
    position = hancom_position(element, offset)
    if position is None:
        raise HwpxValueError(
            "the paragraph holds something whose count in Hangul's positions is not known (a tab written beside "
            "the text, a tracked change)",
            code="document-caret-place-unsupported",
            context={"paragraph": index},
            suggestion="Put the caret in another paragraph, or call reset_caret().",
        )
    return _write(document, 0, index, position)


def fix_caret_before_saving(document: Any) -> bool:
    """Put a caret that points at a body paragraph the document no longer has at the body's start, as
    Hangul opens it; anything else stays as written. Returns whether it changed."""

    element = _caret_element(document)
    if element is None or element.get("listIDRef") != "0":
        return False
    try:
        paragraph = int(element.get("paraIDRef") or "0")
    except ValueError:
        paragraph = -1
    paragraphs = body_paragraphs(document)
    if not paragraphs or 0 <= paragraph < len(paragraphs):
        return False  # in place, or a body without paragraphs: left as written
    before = dict(element.attrib)
    reset_caret(document)
    return dict(element.attrib) != before


__all__ = ["body_paragraphs", "body_start", "fix_caret_before_saving", "hancom_position", "read_caret",
           "reset_caret", "set_caret"]
