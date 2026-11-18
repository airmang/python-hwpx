# SPDX-License-Identifier: Apache-2.0
"""Highlight (``hp:markpenBegin``/``markpenEnd``) authoring and reading owner
behind the :class:`HwpxDocument` facade.

Real-corpus reversal (``hwpxlib_corpus/error__20251107__test*.hwpx``, the only
fixtures carrying this pair) plus the OWPML schema (``ParaList XML
schema.xml``) agree on the shape: both marks live inside a single ``hp:t``,
``markpenBegin`` carries an optional ``color``, ``markpenEnd`` carries no
attributes at all — pairing is positional (innermost open begin closes first),
not by id. :mod:`hwpx.tools.text_extractor` already reads this shape with a
per-``hp:t`` stack; :func:`list_highlights` exposes the same reading as a
public model instead of inline text markers.

Authoring is scoped to one run's text the same way ``doc.tracking.delete``
scopes tracked deletes: a match that only exists once inline markup pieces
are concatenated crosses a boundary this module refuses to split.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from ..errors import HwpxValueError
from ..objects.highlight import Highlight

if TYPE_CHECKING:
    from hwpx.document import HwpxDocument
    from ..oxml import HwpxOxmlParagraph
    from ..oxml.body import TextSpan

#: OWPML ``hc:RGBColorType`` — ``#`` followed by exactly six hex digits.
_COLOR_RE = re.compile(r"#[0-9A-Fa-f]{6}")

#: Matches the real-corpus fixtures' brightest observed value; any
#: schema-valid hex is otherwise accepted.
DEFAULT_COLOR = "#FFFF00"


def _validate_color(color: str) -> str:
    if not isinstance(color, str) or not _COLOR_RE.fullmatch(color):
        raise HwpxValueError(
            f"highlight color must be a 6-digit hex value like '#FFFF00', got {color!r}",
            code="text-highlight-color-invalid",
            context={"color": color},
            suggestion="Pass a colour matching #RRGGBB (hex digits, either case).",
        )
    return color


def _paragraph_has_highlightable_text(paragraph: "HwpxOxmlParagraph", match: str) -> bool:
    """Return whether *match* lives inside one contiguous inline text piece.

    Mirrors ``hwpx._document.tracked._paragraph_has_replaceable_text``: a
    match that is only present after concatenating text across inline
    markup (an existing highlight, a tracked-change mark, …) is real but
    cannot be wrapped safely, so that case raises here instead of falling
    through to a generic "not found".
    """

    crosses_inline_markup = False
    for run in paragraph.runs:
        model = run.to_model()
        for span in model.text_spans:
            if match not in span.text:
                continue
            if match in span.leading_text or any(
                match in markup.trailing_text for markup in span.marks
            ):
                return True
            crosses_inline_markup = True

    if crosses_inline_markup:
        raise HwpxValueError(
            "match text crosses inline markup and cannot be wrapped safely",
            code="text-highlight-match-crosses-markup",
            context={"match": match},
            suggestion="Target a substring that lives inside a single run.",
        )
    return False


def add_highlight(
    doc: "HwpxDocument",
    paragraph: "HwpxOxmlParagraph",
    match: str | None = None,
    *,
    color: str = DEFAULT_COLOR,
    start: int | None = None,
    end: int | None = None,
) -> Highlight:
    """Wrap the first occurrence of *match* in *paragraph* in markpen marks, or characters ``[start, end)``."""

    if start is not None or end is not None:
        if match is not None:
            from ..errors import HwpxValueError as _ValueError

            raise _ValueError("pass match or start and end, not both", code="paragraph-range-invalid",
                              context={"match": match, "start": repr(start), "end": repr(end)},
                              suggestion="Highlight a substring with match=, or a range of characters with start=, end=.")
        from ..oxml.text_ranges import highlight_range

        validated = _validate_color(color)
        if start is None or end is None:
            from ..errors import HwpxValueError as _ValueError

            raise _ValueError("a highlight's range needs both start and end", code="paragraph-range-invalid",
                              suggestion="Pass start and end (positions count as paragraph.text does).")
        highlight_range(paragraph, start, end, validated)
        return Highlight(text=paragraph.text[start:end], color=validated, paragraph=paragraph)
    if not isinstance(match, str):
        from ..errors import argument_type_error

        raise argument_type_error("match", match, "str", suggestion="Pass the substring to highlight as a str.")
    if not match:
        raise HwpxValueError(
            "match text must be a non-empty string",
            code="text-highlight-match-empty",
            suggestion="Pass the substring to highlight.",
        )
    validated_color = _validate_color(color)

    if not _paragraph_has_highlightable_text(paragraph, match):
        raise HwpxValueError(
            "match text was not found in the paragraph",
            code="text-highlight-match-not-found",
            context={"match": match, "paragraphText": paragraph.text},
            suggestion="Inspect paragraph.text for the actual string.",
        )

    paragraph.add_highlight(color=validated_color, match=match)
    return Highlight(text=match, color=validated_color, paragraph=paragraph)


def _span_highlights(span: "TextSpan") -> list[tuple[str, "str | None"]]:
    """Yield (text, color) for every markpen pair closed within *span*.

    A LIFO stack, same as ``text_extractor._render_text_element``'s
    ``highlight_stack`` — nested ``markpenBegin`` opens a new frame, the next
    ``markpenEnd`` closes the innermost one. A begin left open at the end of
    the span (no matching end inside this ``hp:t``) is still reported, same
    as that reader closing it defensively at ``hp:t`` end; an end with
    nothing open is silently dropped rather than fabricated.
    """

    results: list[tuple[str, "str | None"]] = []
    stack: list[tuple["str | None", list[str]]] = []

    for markup in span.marks:
        element = markup.element
        name = getattr(element, "name", None)
        if name == "markpenBegin":
            attributes = getattr(element, "attributes", None) or {}
            stack.append((attributes.get("color"), []))
            if markup.trailing_text:
                stack[-1][1].append(markup.trailing_text)
            continue
        if name == "markpenEnd":
            if stack:
                mark_color, buffer = stack.pop()
                results.append(("".join(buffer), mark_color))
                if stack and markup.trailing_text:
                    stack[-1][1].append(markup.trailing_text)
            continue
        if stack and markup.trailing_text:
            stack[-1][1].append(markup.trailing_text)

    while stack:
        mark_color, buffer = stack.pop()
        results.append(("".join(buffer), mark_color))
    return results


def list_highlights(doc: "HwpxDocument") -> tuple[Highlight, ...]:
    """Return every markpen highlight in the document, in document order: in the body and in table
    cells, text boxes, captions, headers, footers, notes, memos and master pages
    (``doc.text.iter_paragraphs()``'s paragraphs)."""

    from .text_blocks import iter_paragraph_places

    results: list[Highlight] = []
    for paragraph in (place.paragraph for place in iter_paragraph_places(doc, None)):
        crossing = _crossing_highlights(paragraph)
        if crossing is not None:
            results.extend(crossing)
            continue
        for run in paragraph.runs:
            model = run.to_model()
            for span in model.text_spans:
                for text, color in _span_highlights(span):
                    results.append(Highlight(text=text, color=color, paragraph=paragraph))
    return tuple(results)


def _crossing_highlights(paragraph: "HwpxOxmlParagraph") -> "list[Highlight] | None":
    """The highlights of *paragraph* when one of them crosses from one ``hp:t`` into another -- Hancom's form
    for a highlight over two runs (``highlight_across_runs``) -- read as the characters between its two marks;
    ``None`` when every highlight opens and closes in one ``hp:t`` and holds no tab or line break (read span by
    span, as before); a tab or line break under a highlight is read as ``paragraph.text`` reads it."""

    from ..oxml.text_ranges import _units

    pairs: "list[tuple[Any, Any]]" = []
    open_: "list[Any]" = []
    holds_characters = False  # a tab or line break under a highlight: the span reader sees no text there
    for unit in _units(paragraph.element):  # the reader's rule: the innermost open begin closes first
        name = unit.element.tag.rsplit("}", 1)[-1] if unit.kind == "mark" else ""
        if name == "markpenBegin":
            open_.append(unit)
        elif name == "markpenEnd" and open_:
            pairs.append((open_.pop(), unit))
        elif open_ and unit.kind in ("atom", "tab"):
            holds_characters = True
    pairs += [(begin, None) for begin in open_]
    if not holds_characters and all(finish is not None and finish.text is begin.text for begin, finish in pairs):
        return None
    text = paragraph.text
    return [Highlight(text=text[begin.start:finish.start if finish is not None else len(text)],
                      color=begin.element.get("color"), paragraph=paragraph)
            for begin, finish in sorted(pairs, key=lambda pair: pair[0].start)]


__all__ = ["DEFAULT_COLOR", "add_highlight", "list_highlights"]
