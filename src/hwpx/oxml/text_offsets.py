# SPDX-License-Identifier: Apache-2.0
"""Where something stands in its paragraph's text: the ``offset`` reads.

One rule for every place in a paragraph, the one ``paragraph.text``, ``replace_range``, ``format_range``,
``split_run`` and an object's ``move_to(offset=)`` count by: a character of ``hp:t`` (a Python code point),
a tab, a line break, a no-break or fixed-width space and a hyphen are one each; a control (field start and
end, note, bookmark, auto number ...), an object (table, picture, shape ...), a highlight's or a tracked
change's mark, 덧말 and 글자 겹치기 are none. A thing that takes no character stands at the number of
characters before it -- its ``offset`` -- so it sits "after character ``offset - 1``, before character
``offset``". Hancom counts otherwise in a paragraph's saved lines (``LineSegment.text_position``: a tab or a
control eight, a character past the Basic Multilingual Plane two); no public value uses that count but those.
"""

from __future__ import annotations

from typing import Any, Iterator


def _local(node: Any) -> str:
    tag = node.tag
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def paragraph_runs(paragraph_element: Any) -> Iterator[Any]:
    """The runs of the paragraph element, in order (the ones ``paragraph.text`` reads)."""

    return (child for child in paragraph_element if _local(child) == "run")


def run_start(paragraph_element: Any, run_element: Any) -> int:
    """The number of characters of *paragraph_element* before its run *run_element*."""

    from .formatting import _run_length

    position = 0
    for run in paragraph_runs(paragraph_element):
        if run is run_element:
            return position
        position += _run_length(run)
    return position


def _holding_paragraph(element: Any) -> Any:
    """The ``hp:p`` whose run holds *element* (an lxml element), or ``None``."""

    node = element
    getparent = getattr(node, "getparent", None)
    while getparent is not None:
        parent = node.getparent()
        if parent is None:
            return None
        if _local(parent) == "run":
            paragraph = parent.getparent()
            return paragraph if paragraph is not None and _local(paragraph) == "p" else None
        node = parent
    return None


def offset_of(element: Any, paragraph_element: Any = None) -> int | None:
    """The ``offset`` of *element* -- an object, a control or anything else written in a run of
    *paragraph_element* (by default the paragraph whose run holds it) -- in that paragraph's text; ``None``
    when it is in none of the paragraph's runs."""

    from .formatting import _unit_length

    if paragraph_element is None:
        paragraph_element = _holding_paragraph(element)
        if paragraph_element is None:
            return None
    position = 0
    for run in paragraph_runs(paragraph_element):
        for child in run:
            if child is element:
                return position
            if any(node is element for node in child.iter()):
                return position + (_inside_text(child, element) if _local(child) == "t" else 0)
            position += _unit_length(child)
    return None


def placed_offset(obj: Any) -> int | None:
    """``obj.offset`` of a model object that has an ``element`` (and a ``paragraph``, when it knows it)."""

    paragraph = getattr(obj, "paragraph", None)
    holder = getattr(paragraph, "element", None)
    return offset_of(obj.element, holder if holder is not None and _local(holder) == "p" else None)


def _inside_text(text: Any, element: Any) -> int:
    """The characters of the ``hp:t`` *text* before *element* (a mark or glyph written in it)."""

    from ._document_primitives import _TEXT_INLINE_ATOMS

    count = len(text.text or "")
    for child in text:
        if child is element:
            return count
        name = _local(child)
        count += len(_TEXT_INLINE_ATOMS[name]) if name in _TEXT_INLINE_ATOMS else len("".join(child.itertext()))
        count += len(child.tail or "")
    return count


__all__ = ["offset_of", "paragraph_runs", "placed_offset", "run_start"]
