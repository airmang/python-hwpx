# SPDX-License-Identifier: Apache-2.0
"""Tracked-change authoring owner behind the :class:`HwpxDocument` facade."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from ..errors import HwpxValueError
from ..objects.tracked import TrackedChange, TrackedReplacement

if TYPE_CHECKING:
    from hwpx.document import HwpxDocument
    from ..oxml import HwpxOxmlParagraph

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
_TRACKED_TEXT_ILLEGAL = re.compile(r"[\x00-\x08\x09\x0b\x0c\x0d\x0e-\x1f\ufffe\uffff]")

#: Tracked character and paragraph shape changes (OWPML ``hc:TrackChangeType``). The schema
#: ties one to text through ``hp:run@charTcId``/``hp:p@paraTcId`` and keeps a shape id in
#: ``hh:trackChange@charShapeID``/``paraShapeID``, but no Hangul-saved HWPX of the public corpus
#: (1,304 files) tracks a format change, and Hancom does not take that form: Hangul 2024 saving a
#: document written so kept its insertion but dropped the CharShape/ParaShape entries and the
#: ``charTcId``/``paraTcId`` links (and saving the public HWP sample with 62 format changes as
#: HWPX kept no tracked change at all). So python-hwpx writes none, rejects none, and accepts one
#: only when no text points at it (accepting keeps the text as it looks: only the header entry goes).
FORMAT_CHANGE_TYPES = frozenset({"charshape", "parashape"})


def _is_format_change(change_type: object) -> bool:
    return str(change_type or "").strip().lower().replace("_", "").replace("-", "") in FORMAT_CHANGE_TYPES


def _format_change_links(doc: "HwpxDocument") -> dict[str, int]:
    """How many runs (``charTcId``) and paragraphs (``paraTcId``) point at each change id."""

    links: dict[str, int] = {}
    for section in doc.oxml.sections:
        for tag, attribute in ((f"{_HP}run", "charTcId"), (f"{_HP}p", "paraTcId")):
            for element in section.element.iter(tag):
                value = element.get(attribute)
                if value is not None:
                    links[value.strip()] = links.get(value.strip(), 0) + 1
    return links


def _sanitize_tracked_text(value: str) -> str:
    if not isinstance(value, str):
        from ..errors import argument_type_error

        raise argument_type_error("text", value, "str", suggestion="Pass the tracked text as a str.")
    return _TRACKED_TEXT_ILLEGAL.sub("", value)


def add_track_change(
    doc: "HwpxDocument",
    change_type: str,
    *,
    author: str = "AI Agent",
    date: str | None = None,
) -> TrackedChange:
    """Add tracked-change header metadata and return it as a live result.

    This is the low-level primitive: it only registers header metadata, so
    the returned :class:`TrackedChange` has no ``paragraph`` yet \u2014 nothing
    anchors it to body text until :func:`add_tracked_insert`/
    :func:`add_tracked_delete` do that.

    A character or paragraph shape change (``CharShape``/``ParaShape``) is refused: Hancom
    drops the schema's form of one when it saves (see :data:`FORMAT_CHANGE_TYPES`).
    """

    if _is_format_change(change_type):
        raise HwpxValueError(
            f"tracking a {change_type!r} change is not written",
            code="track-format-change-unconfirmed",
            context={"change_type": change_type},
            suggestion="Track insertions and deletions (doc.tracking.insert/delete/replace). Hangul 2024 "
            "drops a CharShape/ParaShape change and its charTcId/paraTcId links when it saves the document.",
        )
    change_id = doc._root.add_track_change(
        change_type,
        author_name=author,
        date=date,
    )
    return TrackedChange(
        change_id=change_id,
        kind=change_type.upper(),
        author=author,
        date=date,
    )


def _enclosing_paragraph_element(element: Any) -> Any:
    node = element.getparent()
    while node is not None and node.tag != f"{_HP}p":
        node = node.getparent()
    return node


def list_tracked_changes(doc: "HwpxDocument") -> tuple[TrackedChange, ...]:
    """Every tracked change, in document order: those the text marks in the order their first mark
    comes, each with the paragraph holding that mark; then those only the header lists (registered
    with ``doc.tracking.add_change``), in the header's order, with no paragraph."""

    from ..oxml import HwpxOxmlParagraph

    header_changes = doc.oxml.track_changes
    first: dict[str, tuple[str, Any, Any]] = {}  # change id -> (kind of mark, paragraph element, section)
    begins = (f"{_HP}insertBegin", f"{_HP}deleteBegin")
    for section in doc.oxml.sections:
        for element in section.element.iter():
            if element.tag not in begins:
                continue
            change_id = (element.get("TcId") or "").strip()
            if change_id and change_id not in first:
                first[change_id] = (_MARKS[element.tag][0], _enclosing_paragraph_element(element), section)
    order = list(first) + [change_id for change_id in header_changes if change_id not in first]
    found: list[TrackedChange] = []
    for change_id in order:
        entry = header_changes.get(change_id)
        mark_kind, paragraph_element, section = first.get(change_id, ("", None, None))
        kind = (getattr(entry, "change_type", None) or mark_kind).upper()
        found.append(
            TrackedChange(
                change_id=int(change_id) if change_id.isdigit() else -1,
                kind=kind,
                author=_resolved_author_name(doc, entry.author_id) if entry is not None else "",
                date=entry.date if entry is not None else None,
                paragraph=(
                    HwpxOxmlParagraph(paragraph_element, section) if paragraph_element is not None else None
                ),
            )
        )
    return tuple(found)


def find_tracked_change(doc: "HwpxDocument", change_id_ref: "int | str | None") -> TrackedChange | None:
    """The tracked change :func:`list_tracked_changes` lists under *change_id_ref* (``7`` or ``"7"``)."""

    if change_id_ref is None or isinstance(change_id_ref, bool):
        return None
    wanted = str(change_id_ref).strip()
    for change in list_tracked_changes(doc):
        if str(change.change_id) == wanted:
            return change
    return None


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
            if match in span.text:
                # The replace writer takes the first text element that holds the match and stops
                # there: one that holds it only across its marks is where the writer failed, after
                # the header had been given both changes.
                crosses_inline_markup = True
                break
        else:
            crosses_inline_markup = True  # only across the run's text elements: the writer goes on
            continue
        break

    if crosses_inline_markup:
        raise HwpxValueError(
            "match crosses inline markup and cannot be wrapped safely",
            code="track-match-crosses-markup",
            suggestion="Target a substring that lives inside a single run.",
        )
    return False


def _paragraph_has_deletable_match(paragraph: "HwpxOxmlParagraph", match: str) -> bool:
    """Whether a tracked delete of *match* can be written: the delete writer takes the first run whose
    text holds the match and stops there, so a match that crosses markup in that run is refused here
    (``track-match-crosses-markup``) even when a later run holds it whole. Found by the writer instead,
    it failed after the header had been given the change."""

    for run in paragraph.runs:
        model = run.to_model()
        if match not in "".join(span.text for span in model.text_spans):
            continue
        if any(
            match in span.leading_text or any(match in markup.trailing_text for markup in span.marks)
            for span in model.text_spans
        ):
            return True
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
    change = add_track_change(doc, "Insert", author=author, date=date)
    mark_id = doc._root.next_track_change_mark_id()
    paragraph._add_tracked_insert(
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
    # A match that only exists across inline markup is refused here (``track-match-crosses-markup``),
    # before the change is added to the header: found later, it left a change nobody made.
    found = (
        _paragraph_has_deletable_text(paragraph, None)
        if match is None
        else _paragraph_has_deletable_match(paragraph, match)
    )
    if not found:
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

    change = add_track_change(doc, "Delete", author=author, date=date)
    mark_id = doc._root.next_track_change_mark_id()
    paragraph._add_tracked_delete(
        change_id=change.change_id,
        first_mark_id=mark_id,
        match=match,
    )
    if match is None:
        _delete_paragraph_break(paragraph, change.change_id)
    return TrackedChange(
        change_id=change.change_id,
        kind=change.kind,
        author=change.author,
        date=change.date,
        paragraph=paragraph,
    )


def _delete_paragraph_break(paragraph: "HwpxOxmlParagraph", change_id: int) -> None:
    """Mark the break of a wholly deleted plain paragraph deleted as well.

    Hancom shows a deleted paragraph whose break is kept as an empty line.
    It reads ``paraend="1"`` on the last delete mark as the break deleted too,
    so when another paragraph follows in the same list, that mark gets it.
    A paragraph holding anything but text runs (section setup, controls,
    objects) keeps its break.
    """

    element = paragraph.element
    following = _next_sibling(paragraph.section.element, element)
    if following is None or following.tag != f"{_HP}p":
        return
    for run in element.findall(f"{_HP}run"):
        if any(child.tag != f"{_HP}t" for child in run):
            return
    ends = [
        end
        for end in element.findall(f"{_HP}run/{_HP}t/{_HP}deleteEnd")
        if end.get("TcId") == str(change_id)
    ]
    if ends:
        ends[-1].set("paraend", "1")
        paragraph.section.mark_dirty()


def _next_sibling(root: Any, element: Any) -> Any:
    """The element after *element* under its parent, found from *root* down.

    Walks down rather than using lxml's ``getnext()``, so hand-built
    ``xml.etree.ElementTree`` trees work too.
    """

    stack = [root]
    while stack:
        node = stack.pop()
        children = list(node)
        for index, child in enumerate(children):
            if child is element:
                return children[index + 1] if index + 1 < len(children) else None
            stack.append(child)
    return None


_MARKS = {
    f"{_HP}insertBegin": ("insert", True),
    f"{_HP}insertEnd": ("insert", False),
    f"{_HP}deleteBegin": ("delete", True),
    f"{_HP}deleteEnd": ("delete", False),
}


def _change_key(value: Any) -> str:
    if isinstance(value, TrackedChange):
        return str(value.change_id)
    return str(value).strip()


def _drop_keeping_tail(element: Any) -> None:
    """Remove *element* from its parent; the text after it stays where it was."""

    parent = element.getparent()
    if parent is None:
        return
    tail = element.tail or ""
    previous = element.getprevious()
    if tail:
        if previous is not None:
            previous.tail = (previous.tail or "") + tail
        else:
            parent.text = (parent.text or "") + tail
    parent.remove(element)


#: Run children a resolved deletion leaves in place: what sets up the section or its
#: columns is no text that can be deleted.
_KEPT_IN_A_DELETION = {"secPr", "colPr"}


def _is_setup(child: Any) -> bool:
    name = child.tag.rsplit("}", 1)[-1] if isinstance(child.tag, str) else ""
    if name in _KEPT_IN_A_DELETION:
        return True
    return name == "ctrl" and any(
        isinstance(grand.tag, str) and grand.tag.rsplit("}", 1)[-1] in _KEPT_IN_A_DELETION for grand in child
    )


def _cut_between(paragraph: Any, begin: Any, end: Any) -> None:
    """Remove the text and inline content of *paragraph* between the marks *begin* and *end*."""

    inside = False
    for run in [child for child in paragraph if child.tag == f"{_HP}run"]:
        for child in list(run):
            if child.tag != f"{_HP}t":
                if child is begin:
                    inside = True
                elif child is end:
                    inside = False
                elif inside and not _is_setup(child):
                    run.remove(child)
                continue
            if inside:
                child.text = ""
            for grand in list(child):
                if grand is begin:
                    inside = True
                    grand.tail = ""
                elif grand is end:
                    inside = False
                elif inside:
                    child.remove(grand)
            # a deleted text node left with nothing goes too
            if inside and not len(child) and not child.text and child is not begin and child is not end:
                run.remove(child)


def _merge_with_next(paragraph: Any) -> bool:
    """Join the paragraph after *paragraph* into it, as removing the break between them
    does: *paragraph* keeps its own shape. A paragraph left with no content gives way
    to the next instead. Returns whether a paragraph went."""

    following = paragraph.getnext()
    while following is not None and following.tag != f"{_HP}p":
        following = following.getnext()
    if following is None:
        return False
    runs = [child for child in paragraph if child.tag == f"{_HP}run"]
    empty = all(
        all(child.tag == f"{_HP}t" and not (child.text or "") and not len(child) for child in run) for run in runs
    )
    if empty and not paragraph.findall(f".//{_HP}secPr"):
        paragraph.getparent().remove(paragraph)
        return True
    for cache in [c for c in paragraph if c.tag.rsplit("}", 1)[-1].lower() == "linesegarray"]:
        paragraph.remove(cache)
    for run in [child for child in following if child.tag == f"{_HP}run"]:
        paragraph.append(run)
    following.getparent().remove(following)
    return True


def _resolved_author_name(doc: "HwpxDocument", author_id: Any) -> str:
    authors = doc.oxml.track_change_authors
    author = doc.oxml.track_change_author(author_id)
    if author is None and len(authors) == 1:
        # Hancom may number the author differently from the change's authorID; one author is that one.
        author = next(iter(authors.values()))
    return (getattr(author, "name", None) or "") if author is not None else ""


def resolve_tracked_changes(
    doc: "HwpxDocument",
    *,
    accept: bool,
    change: Any = None,
    author: str | None = None,
) -> tuple[TrackedChange, ...]:
    """Accept or reject tracked changes and return those resolved.

    Accepting keeps inserted text without its marks and removes deleted text; rejecting
    does the reverse. A change whose end carries ``paraend="1"`` covers its paragraph's
    break too: removing that text joins the next paragraph in. Exactly one of the whole
    document (no selector), one change (*change*: its id or a :class:`TrackedChange`) or
    one author's changes (*author*: the author's name) is resolved. The header's change
    and author lists keep only what the text still uses. Every paragraph touched is laid
    out again.
    """

    from ..oxml._document_primitives import _clear_paragraph_layout_cache

    if change is not None and author is not None:
        raise HwpxValueError(
            "pass change= or author=, not both",
            code="track-selector-conflict",
            suggestion="Resolve one change, one author's changes, or (with neither) all of them.",
        )
    header_changes = doc.oxml.track_changes
    sections = doc.oxml.sections
    marked: dict[str, str] = {}
    for section in sections:
        for element in section.element.iter(*_MARKS):
            kind, opens = _MARKS[element.tag]
            if opens and element.get("TcId") is not None:
                marked.setdefault(element.get("TcId") or "", kind)
    known = set(header_changes) | set(marked)
    # Resolving takes changes out of the header, and the next change made would take the freed number:
    # the object still held for the resolved change would then name, and resolve, somebody else's
    # change. So an id is not given twice while the document is open (HwpxOxmlDocument.add_track_change
    # starts above this floor).
    doc._root._track_change_id_floor = max(
        [getattr(doc._root, "_track_change_id_floor", 0), *(int(key) for key in known if key.isdigit())]
    )
    if change is not None:
        wanted = {_change_key(change)}
        if not wanted <= known:
            raise HwpxValueError(
                f"tracked change {_change_key(change)!r} is not in the document",
                code="track-change-not-found",
                context={"requested": _change_key(change), "changes": sorted(known)[:50]},
                suggestion="List doc.tracking.changes to see the change ids.",
            )
    elif author is not None:
        wanted = {
            change_id
            for change_id in known
            if change_id in header_changes
            and _resolved_author_name(doc, header_changes[change_id].author_id) == author
        }
    else:
        wanted = known

    # Character and paragraph shape changes: see FORMAT_CHANGE_TYPES. Refused before anything changes.
    formats = sorted(
        change_id for change_id in wanted
        if change_id in header_changes and _is_format_change(header_changes[change_id].change_type)
    )
    linked = _format_change_links(doc) if formats else {}
    blocked = formats if not accept else [change_id for change_id in formats if linked.get(change_id)]
    if blocked:
        raise HwpxValueError(
            f"tracked format changes {blocked} cannot be {'accepted' if accept else 'rejected'} yet",
            code="track-format-change-unconfirmed",
            context={"changes": blocked, "accept": accept},
            suggestion="Resolve the insertions and deletions one by one (change=<id>). The old shape of a "
            "character or paragraph shape change is not known: Hangul 2024 drops such changes and their "
            "charTcId/paraTcId links when it saves.",
        )

    resolved: list[TrackedChange] = []
    for section in sections:
        touched: list[Any] = []
        begins: list[Any] = [
            element for element in section.element.iter()
            if element.tag in (f"{_HP}insertBegin", f"{_HP}deleteBegin") and (element.get("TcId") or "") in wanted
        ]
        for begin in begins:
            kind = _MARKS[begin.tag][0]
            paragraph = begin.getparent()
            while paragraph is not None and paragraph.tag != f"{_HP}p":
                paragraph = paragraph.getparent()
            if paragraph is None:
                continue
            end_tag = f"{_HP}{kind}End"
            ends = [e for e in paragraph.iter(end_tag) if e.get("TcId") == begin.get("TcId")]
            end = next((e for e in ends if e.get("Id") == begin.get("Id")), ends[0] if ends else None)
            remove_content = (kind == "delete") == accept
            if end is not None and remove_content:
                _cut_between(paragraph, begin, end)
            joins = end is not None and end.get("paraend") == "1" and remove_content
            for mark in (begin, end):
                if mark is not None:
                    _drop_keeping_tail(mark)
            if joins:
                following = paragraph.getnext()
                if _merge_with_next(paragraph) and paragraph.getparent() is None:
                    paragraph = following
            touched.append(paragraph)
        for paragraph in touched:
            if paragraph is not None and paragraph.getparent() is not None:
                _clear_paragraph_layout_cache(paragraph)
        if begins:
            section.mark_dirty()

    for change_id in sorted(wanted, key=lambda value: (len(value), value)):
        entry = header_changes.get(change_id)
        kind = (getattr(entry, "change_type", None) or marked.get(change_id, "")).upper()
        date = getattr(entry, "date", None) if entry is not None else None
        resolved.append(
            TrackedChange(
                change_id=int(change_id) if change_id.isdigit() else -1,
                kind=kind,
                author=_resolved_author_name(doc, entry.author_id) if entry is not None else "",
                date=date,
            )
        )
    _prune_track_header(doc, wanted)
    return tuple(resolved)


def _prune_track_header(doc: "HwpxDocument", resolved: set[str]) -> None:
    """Drop the header's entries for the *resolved* changes the text no longer marks, and
    the authors no change names any more."""

    still = {
        element.get("TcId") or ""
        for section in doc.oxml.sections
        for element in section.element.iter(*_MARKS)
    }
    for header in doc.oxml.headers:
        changes = header._track_changes_element()
        if changes is None:
            continue
        removed = False
        for entry in list(changes):
            if entry.get("id") in resolved and entry.get("id") not in still:
                changes.remove(entry)
                removed = True
        if not removed:
            continue
        changes.set("itemCnt", str(len(changes)))
        authors = header._track_change_authors_element()
        if authors is not None:
            named = {entry.get("authorID") for entry in changes}
            ids = {author.get("id") for author in authors}
            if not len(changes):
                for author_element in list(authors):
                    authors.remove(author_element)
            elif named <= ids:  # only when the changes name the authors by their ids
                for author_element in list(authors):
                    if author_element.get("id") not in named:
                        authors.remove(author_element)
            authors.set("itemCnt", str(len(authors)))
        header.mark_dirty()


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

    delete_change = add_track_change(doc, "Delete", author=author, date=date)
    insert_change = add_track_change(doc, "Insert", author=author, date=date)
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
