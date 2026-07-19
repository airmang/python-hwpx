# SPDX-License-Identifier: Apache-2.0
"""Tracked-change authoring owner behind the :class:`HwpxDocument` facade (S-084)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

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
) -> int:
    """Add tracked-change header metadata and return the new change id."""

    return doc._root.add_track_change(
        change_type,
        author_name=author_name,
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


def add_tracked_insert(
    doc: "HwpxDocument",
    paragraph: "HwpxOxmlParagraph",
    text: str,
    *,
    author: str = "AI Agent",
    date: str | None = None,
    char_pr_id_ref: str | int | None = None,
) -> int:
    """Append tracked inserted *text* to *paragraph* and return its change id."""

    sanitized = _sanitize_tracked_text(text)
    if not sanitized:
        raise ValueError("tracked insert text must be non-empty")
    change_id = doc.add_track_change("Insert", author_name=author, date=date)
    mark_id = doc._root.next_track_change_mark_id()
    paragraph.add_tracked_insert(
        sanitized,
        change_id=change_id,
        mark_id=mark_id,
        char_pr_id_ref=char_pr_id_ref,
    )
    return change_id


def add_tracked_delete(
    doc: "HwpxDocument",
    paragraph: "HwpxOxmlParagraph",
    *,
    match: str | None = None,
    author: str = "AI Agent",
    date: str | None = None,
) -> int:
    """Wrap paragraph text or the first matching substring in delete marks."""

    if match == "":
        raise ValueError("match must be a non-empty string")
    if not _paragraph_has_deletable_text(paragraph, match):
        if match is None:
            raise ValueError("paragraph contains no text to delete")
        raise ValueError("match text was not found in the paragraph")

    change_id = doc.add_track_change("Delete", author_name=author, date=date)
    mark_id = doc._root.next_track_change_mark_id()
    paragraph.add_tracked_delete(
        change_id=change_id,
        first_mark_id=mark_id,
        match=match,
    )
    return change_id


def add_tracked_replace(
    doc: "HwpxDocument",
    paragraph: "HwpxOxmlParagraph",
    old: str,
    new: str,
    *,
    author: str = "AI Agent",
    date: str | None = None,
) -> tuple[int, int]:
    """Represent a replacement as tracked delete of *old* plus tracked insert of *new*."""

    delete_change_id = doc.add_tracked_delete(
        paragraph,
        match=old,
        author=author,
        date=date,
    )
    insert_change_id = doc.add_tracked_insert(
        paragraph,
        new,
        author=author,
        date=date,
    )
    return delete_change_id, insert_change_id
