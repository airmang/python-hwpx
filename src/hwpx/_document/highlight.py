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
from typing import TYPE_CHECKING

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
    match: str,
    *,
    color: str = DEFAULT_COLOR,
) -> Highlight:
    """Wrap the first occurrence of *match* in *paragraph* in markpen marks."""

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
    """Return every markpen highlight in the document, in document order."""

    results: list[Highlight] = []
    for paragraph in doc.paragraphs:
        for run in paragraph.runs:
            model = run.to_model()
            for span in model.text_spans:
                for text, color in _span_highlights(span):
                    results.append(Highlight(text=text, color=color, paragraph=paragraph))
    return tuple(results)


__all__ = ["DEFAULT_COLOR", "add_highlight", "list_highlights"]
