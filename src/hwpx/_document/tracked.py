# SPDX-License-Identifier: Apache-2.0
"""Tracked-change authoring owner behind the :class:`HwpxDocument` facade."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..errors import HwpxValueError
from ..objects.tracked import TrackedChange, TrackedReplacement

if TYPE_CHECKING:
    from hwpx.document import HwpxDocument
    from ..oxml import HwpxOxmlParagraph

_TRACKED_TEXT_ILLEGAL = re.compile(r"[\x00-\x08\x09\x0b\x0c\x0d\x0e-\x1f\ufffe\uffff]")


def _sanitize_tracked_text(value: str) -> str:
    return _TRACKED_TEXT_ILLEGAL.sub("", value)


def add_track_change(
    doc: "HwpxDocument",
    change_type: str,
    *,
    author_name: str = "AI Agent",
    date: str | None = None,
) -> TrackedChange:
    """Add tracked-change header metadata and return it as a live result.

    This is the low-level primitive: it only registers header metadata, so
    the returned :class:`TrackedChange` has no ``paragraph`` yet \u2014 nothing
    anchors it to body text until :func:`add_tracked_insert`/
    :func:`add_tracked_delete` do that.
    """

    change_id = doc._root.add_track_change(
        change_type,
        author_name=author_name,
        date=date,
    )
    return TrackedChange(
        change_id=change_id,
        kind=change_type.upper(),
        author=author_name,
        date=date,
    )


def _paragraph_has_deletable_text(
    paragraph: "HwpxOxmlParagraph",
    match: str | None,
) -> bool:
    for run in paragraph.runs:
        model = run.to_model()
        run_text = "".join(span.text for span in model.text_spans)
        if match is None:
            if run_text:
                return True
        elif match in run_text:
            return True
    return False


def _paragraph_has_replaceable_text(
    paragraph: "HwpxOxmlParagraph",
    match: str,
) -> bool:
    """Return whether *match* can be wrapped inside one inline text segment.

    A match that only exists after concatenating text across inline markup is
    present but cannot be rewritten safely.  Detect that before allocating
    tracked-change header IDs so a rejected replacement leaves no orphan
    metadata behind.
    """

    crosses_inline_markup = False
    for run in paragraph.runs:
        model = run.to_model()
        run_text = "".join(span.text for span in model.text_spans)
        if match not in run_text:
            continue
        for span in model.text_spans:
            if match in span.leading_text or any(
                match in markup.trailing_text for markup in span.marks
            ):
                return True
        crosses_inline_markup = True

    if crosses_inline_markup:
        raise HwpxValueError(
            "match crosses inline markup and cannot be wrapped safely",
            code="track-match-crosses-markup",
            suggestion="Target a substring that lives inside a single run.",
        )
    return False


def add_tracked_insert(
    doc: "HwpxDocument",
    paragraph: "HwpxOxmlParagraph",
    text: str,
    *,
    author: str = "AI Agent",
    date: str | None = None,
    char_pr_id_ref: str | int | None = None,
) -> TrackedChange:
    """Append tracked inserted *text* to *paragraph* and return the change."""

    sanitized = _sanitize_tracked_text(text)
    if not sanitized:
        raise HwpxValueError(
            "tracked insert text must be non-empty",
            code="track-text-empty",
            suggestion="Pass the text to insert.",
        )
    # Call the local primitive directly rather than `doc.add_track_change` —
    # that facade name moved in 6.0 (design table row 39), and going through
    # it would fire its DeprecationWarning on every insert even when this
    # function is reached via the new `doc.tracking.insert` namespace path.
    change = add_track_change(doc, "Insert", author_name=author, date=date)
    mark_id = doc._root.next_track_change_mark_id()
    paragraph.add_tracked_insert(
        sanitized,
        change_id=change.change_id,
        mark_id=mark_id,
        char_pr_id_ref=char_pr_id_ref,
    )
    return TrackedChange(
        change_id=change.change_id,
        kind=change.kind,
        author=change.author,
        date=change.date,
        paragraph=paragraph,
    )


def add_tracked_delete(
    doc: "HwpxDocument",
    paragraph: "HwpxOxmlParagraph",
    *,
    match: str | None = None,
    author: str = "AI Agent",
    date: str | None = None,
) -> TrackedChange:
    """Wrap paragraph text or the first matching substring in delete marks."""

    if match == "":
        raise HwpxValueError(
            "match must be a non-empty string",
            code="track-match-empty",
            suggestion="Pass the substring to delete.",
        )
    if not _paragraph_has_deletable_text(paragraph, match):
        if match is None:
            raise HwpxValueError(
                "paragraph contains no text to delete",
                code="track-paragraph-empty",
                suggestion="Target a paragraph that has text.",
            )
        raise HwpxValueError(
            "match text was not found in the paragraph",
            code="track-match-not-found",
            context={"match": match, "paragraphText": paragraph.text},
            suggestion="Inspect paragraph.text for the actual string.",
        )

    change = add_track_change(doc, "Delete", author_name=author, date=date)
    mark_id = doc._root.next_track_change_mark_id()
    paragraph.add_tracked_delete(
        change_id=change.change_id,
        first_mark_id=mark_id,
        match=match,
    )
    return TrackedChange(
        change_id=change.change_id,
        kind=change.kind,
        author=change.author,
        date=change.date,
        paragraph=paragraph,
    )


def add_tracked_replace(
    doc: "HwpxDocument",
    paragraph: "HwpxOxmlParagraph",
    old: str,
    new: str,
    *,
    author: str = "AI Agent",
    date: str | None = None,
) -> TrackedReplacement:
    """Represent a replacement as tracked delete of *old* plus tracked insert of *new*."""

    if old == "":
        raise HwpxValueError(
            "match must be a non-empty string",
            code="track-match-empty",
            suggestion="Pass the substring to delete.",
        )
    if not _paragraph_has_replaceable_text(paragraph, old):
        raise HwpxValueError(
            "match text was not found in the paragraph",
            code="track-match-not-found",
            context={"match": old, "paragraphText": paragraph.text},
            suggestion="Inspect paragraph.text for the actual string.",
        )
    sanitized = _sanitize_tracked_text(new)
    if not sanitized:
        raise HwpxValueError(
            "tracked insert text must be non-empty",
            code="track-text-empty",
            suggestion="Pass the text to insert.",
        )

    delete_change = add_track_change(doc, "Delete", author_name=author, date=date)
    insert_change = add_track_change(doc, "Insert", author_name=author, date=date)
    first_mark_id = doc._root.next_track_change_mark_id()
    paragraph._add_tracked_replace(
        old,
        sanitized,
        delete_change_id=delete_change.change_id,
        insert_change_id=insert_change.change_id,
        first_mark_id=first_mark_id,
    )
    return TrackedReplacement(
        delete=TrackedChange(
            change_id=delete_change.change_id,
            kind=delete_change.kind,
            author=delete_change.author,
            date=delete_change.date,
            paragraph=paragraph,
        ),
        insert=TrackedChange(
            change_id=insert_change.change_id,
            kind=insert_change.kind,
            author=insert_change.author,
            date=insert_change.date,
            paragraph=paragraph,
        ),
    )
