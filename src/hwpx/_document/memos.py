# SPDX-License-Identifier: Apache-2.0
"""Memo domain owner behind the :class:`HwpxDocument` facade."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from ..errors import HwpxValueError
from ._resolve import home_paragraph, refused_leaves_no_paragraph

from ..oxml._document_primitives import _clear_paragraph_layout_cache, _object_id, current_time
from ..oxml.namespaces import HP

if TYPE_CHECKING:
    from ..oxml._document_primitives import IdSource
    from hwpx.document import HwpxDocument
    from ..oxml import HwpxOxmlMemo, HwpxOxmlParagraph, HwpxOxmlSection

_HP = HP

#: The form of a memo's ``CreateDateTime`` ("2024-03-14T22:38:25Z").
_HANCOM_MEMO_TIME = "%Y-%m-%dT%H:%M:%SZ"
_FILETIME_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)


def _memo_moment(value: "datetime | str | None", ids: "IdSource | None") -> "datetime | str":
    """The memo's creation moment (aware), or the string given when it is not a timestamp. Naive
    values are local time, as ``datetime.now()`` gives; ``…Z`` strings are UTC. ``None`` is now, or
    the ``now=`` of the memo's document (its source *ids*)."""

    if value is None:
        moment = current_time(ids)
    elif isinstance(value, datetime):
        moment = value
    else:
        text = str(value).strip()
        try:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
    return moment.astimezone()  # naive -> local; aware -> the same moment in local time


def _memo_create_time(value: "datetime | str | None", ids: "IdSource | None") -> str:
    """A memo's ``CreateDateTime`` as Hancom writes it: the local wall time, written ``…T…Z``.

    Hangul writes the moment twice: ``CreateDateTime`` as local time (with a ``Z`` all the same)
    and the UTC FILETIME in ``Command`` -- in every memo it saved, the two differ by the writer's
    UTC offset (9 hours: ``hwpxlib_corpus/error__20251107__test``, ``tests/fixtures/hancom_saved``).
    Hancom cannot read "2024-12-02 09:00:00" (it makes a 1601 FILETIME of it). A string that is not
    a timestamp is kept as given.
    """

    moment = _memo_moment(value, ids)
    if isinstance(moment, str):
        return moment
    return moment.strftime(_HANCOM_MEMO_TIME)


def _memo_filetime(value: "datetime | str | None", ids: "IdSource | None") -> tuple[int, int]:
    """The memo's moment as Windows FILETIME (100 ns since 1601, UTC), low and high 32 bits, as the
    ``Command`` parameter holds it. A string that is not a timestamp counts as now."""

    moment = _memo_moment(value, ids)
    if isinstance(moment, str):
        moment = _memo_moment(None, ids)
    assert isinstance(moment, datetime)
    delta = moment.astimezone(timezone.utc) - _FILETIME_EPOCH
    ticks = (delta.days * 86_400 + delta.seconds) * 10_000_000  # whole seconds, as CreateDateTime holds
    return ticks & 0xFFFFFFFF, ticks >> 32


#: The ``fieldid`` Hancom gives every memo field: the control id ``%%me`` as a number.
MEMO_FIELD_ID = str(int.from_bytes(b"%%me", "big"))
#: The ``MemoShapeIDRef`` Hancom writes in every MEMO field (the memo's shape is its section's).
_MEMO_SHAPE_NONE = "65535"


def _next_memo_zorder(doc: "HwpxDocument") -> str:
    """Return a z-order above every MEMO field already in *doc*.

    Hancom gives each memo field its own positive ``zorder``. Without one (or
    with the ``-1`` other field kinds use) Hancom drops the memo's
    ``hp:fieldEnd`` when it saves the document, so the memo loses the end of
    its range.
    """

    highest = 0
    for section in doc.sections:
        for node in section.element.iter(f"{_HP}fieldBegin"):
            if node.get("type") != "MEMO":
                continue
            try:
                highest = max(highest, int(node.get("zorder", "0")))
            except ValueError:
                continue
    return str(highest + 1)


def _append_element(
    parent: Any,
    tag: str,
    attributes: dict[str, str] | None = None,
) -> Any:
    """Create and append a child element that matches *parent*'s element type."""

    child = parent.makeelement(tag, attributes or {})
    parent.append(child)
    return child


def add_memo(
    doc: "HwpxDocument",
    text: str = "",
    *,
    section: "HwpxOxmlSection | None" = None,
    memo_id: str | None = None,
    char_pr_id_ref: str | int | None = None,
    attributes: dict[str, str] | None = None,
) -> "HwpxOxmlMemo":
    """Create a memo entry inside *section* (or the last section by default). A *memo_id* given is
    the memo's ``ID`` (Hancom's own memos are ``memo<number>``, which is used otherwise)."""

    if section is None:
        if not doc._root.sections:
            raise HwpxValueError(
            "document does not contain any sections",
            code="section-missing",
            suggestion="Call doc.add_section() first.",
        )
        section = doc._root.sections[-1]
    memo = section.add_memo(
        text,
        memo_id=memo_id,
        char_pr_id_ref=char_pr_id_ref,
        attributes=attributes,
    )
    if memo_id:  # an id the caller named stays the field's ID (others become memo<Number>, as Hangul's)
        document: Any = section.document
        if document is not None:
            named: set[str] | None = getattr(document, "_named_memo_ids", None)
            if named is None:
                named = set()
                document._named_memo_ids = named
            named.add(str(memo_id))
    return memo


def remove_memo(doc: "HwpxDocument", memo: "HwpxOxmlMemo") -> None:
    """Remove *memo* from the section it belongs to."""

    memo.remove()


def attach_memo_field(
    doc: "HwpxDocument",
    paragraph: "HwpxOxmlParagraph",
    memo: "HwpxOxmlMemo",
    *,
    field_id: str | None = None,
    author: str | None = None,
    created: "datetime | str | None" = None,
    number: int | None = None,
    char_pr_id_ref: str | int | None = None,
    match: str | None = None,
    index: int = 0,
) -> "HwpxOxmlMemo":
    """Attach a MEMO field control to *paragraph* so Hangul shows *memo*.

    The field spans the whole paragraph, or with *match* only the *index*-th (from 0)
    place of that text (it must lie in one run, between no other marks; only such places
    count): the memo is then on those characters, as Hancom anchors a memo put on a selection.

    Returns *memo* itself: once the field exists, ``memo.field_id`` and
    ``memo.paragraph`` (``oxml/memo.py``) resolve it live by searching the
    section, so there is nothing left for a separate return value to carry —
    this replaces the ``str`` field id 5.x returned directly.

    *number* is the memo's number (its ``Number`` parameter). Left out, the
    memo takes the next number in the document, the value its ``zorder``
    gets too, as Hancom numbers its memos. Hancom takes memos with the same
    number for one memo: saving the document again, it drops the range end
    of all but the first.
    """

    if paragraph.section is None:
        raise HwpxValueError(
            "paragraph must belong to a section before anchoring a memo",
            code="note-anchor-detached",
            suggestion="Pass a paragraph obtained from doc.paragraphs.",
        )
    if memo.group.section is None:
        raise HwpxValueError(
            "memo is not attached to a section",
            code="note-memo-detached",
            suggestion="Pass a memo created by doc.notes.add_memo().",
        )
    index = _check_match_index(index)
    if match is None and index:
        raise HwpxValueError(
            "index picks a place of match; there is no match",
            code="note-argument-conflict",
            context={"caller": "attach_memo_field", "index": index},
            suggestion="Pass match= with index=, or leave index out.",
        )
    if match is not None and _find_segment(paragraph.element, match, index) is None:
        raise HwpxValueError(
            "the text to put the memo on is not in one run of the paragraph"
            + (f" {index + 1} times" if index else ""),
            code="note-match-not-found",
            context={"match": match, "index": index, "paragraphText": paragraph.text},
            suggestion="Pass text that appears in the paragraph within one run (paragraph.runs)"
                       + (", and an index below the number of its places (from 0)." if index else "."),
        )

    ids = paragraph.section._ids  # the source of the document the memo goes into
    field_value = field_id or _object_id(ids)
    order = _next_memo_zorder(doc)
    author_value = author or memo.attributes.get("author") or ""

    created_value = _memo_create_time(
        created if created is not None else memo.attributes.get("createDateTime"), ids
    )

    char_ref = char_pr_id_ref
    if char_ref is None:
        char_ref = paragraph.char_pr_id_ref
    if char_ref is None:
        char_ref = memo._infer_char_pr_id_ref()
    if char_ref is None:
        char_ref = "0"
    char_ref = str(char_ref)

    paragraph_element = paragraph.element
    run_begin = paragraph_element.makeelement(f"{_HP}run", {"charPrIDRef": char_ref})
    ctrl_begin = _append_element(run_begin, f"{_HP}ctrl")
    field_begin = _append_element(
        ctrl_begin,
        f"{_HP}fieldBegin",
        {
            "id": field_value,
            "type": "MEMO",
            "name": "",
            "editable": "1",
            "dirty": "0",
            "zorder": order,
            "fieldid": MEMO_FIELD_ID,
            "metaTag": "",
        },
    )

    # The seven parameters, in the order and form Hangul 2024 writes them in every memo it saves
    # (tests/fixtures/hancom_saved memo files, hwpxlib_corpus/error__20251107__test, and its saves
    # of python-hwpx memos): Prop 0; Command "MEMO/<shape>/<number>/<FILETIME low>/<FILETIME high>/
    # <author>/\;;"; ID "memo<number>"; Number; Author (empty when none); MemoShapeIDRef 65535 -- a
    # memo's shape is its section's (SectionProperties.memo_shape_id_ref) -- and CreateDateTime.
    number_value = order if number is None else str(max(1, number))
    named: set[str] = getattr(memo.group.section.document, "_named_memo_ids", None) or set()
    id_value = memo.id if memo.id and memo.id in named else f"memo{number_value}"
    created_source = created if created is not None else memo.attributes.get("createDateTime")
    low, high = _memo_filetime(created_source, ids)
    parameters = _append_element(field_begin, f"{_HP}parameters", {"cnt": "7", "name": ""})
    _append_element(parameters, f"{_HP}integerParam", {"name": "Prop"}).text = "0"
    _append_element(parameters, f"{_HP}stringParam", {"name": "Command"}).text = (
        f"MEMO/{_MEMO_SHAPE_NONE}/{number_value}/{low}/{high}/{author_value}/\\;;"
    )
    _append_element(parameters, f"{_HP}stringParam", {"name": "ID"}).text = id_value
    _append_element(parameters, f"{_HP}integerParam", {"name": "Number"}).text = number_value
    author_param = _append_element(parameters, f"{_HP}stringParam", {"name": "Author"})
    if author_value:
        author_param.text = author_value
    _append_element(parameters, f"{_HP}stringParam", {"name": "MemoShapeIDRef"}).text = _MEMO_SHAPE_NONE
    _append_element(parameters, f"{_HP}stringParam", {"name": "CreateDateTime"}).text = created_value

    sub_list = _append_element(
        field_begin,
        f"{_HP}subList",
        {
            "id": "",
            "textDirection": "HORIZONTAL",
            "lineWrap": "BREAK",
            "vertAlign": "TOP",
            "linkListIDRef": "0",
            "linkListNextIDRef": "0",
            "textWidth": "0",
            "textHeight": "0",
            "hasTextRef": "0",
            "hasNumRef": "0",
        },
    )
    sub_para = _append_element(
        sub_list,
        f"{_HP}p",
        {
            "id": "0",
            "paraPrIDRef": "0",
            "styleIDRef": "0",
            "pageBreak": "0",
            "columnBreak": "0",
            "merged": "0",
        },
    )
    sub_run = _append_element(sub_para, f"{_HP}run", {"charPrIDRef": char_ref})
    # The MEMO field's subList holds the comment TEXT — this is what Hancom shows
    # in the margin memo box. (Previously this emitted ``memo.id``, so Hancom
    # rendered the numeric id instead of the comment.)
    _append_element(sub_run, f"{_HP}t").text = memo.text or ""

    run_end = paragraph_element.makeelement(f"{_HP}run", {"charPrIDRef": char_ref})
    ctrl_end = _append_element(run_end, f"{_HP}ctrl")
    _append_element(ctrl_end, f"{_HP}fieldEnd", {"beginIDRef": field_value, "fieldid": MEMO_FIELD_ID})

    if match is None:
        # after the run holding the section's setup (hp:secPr), as Hancom places a memo on a section's
        # first paragraph -- never before it
        children = list(paragraph.element)
        start = 0
        while start < len(children) and children[start].find(f"{_HP}secPr") is not None:
            start += 1
        paragraph.element.insert(start, run_begin)
        paragraph.element.append(run_end)
    else:
        middle = _split_out(paragraph.element, match, index)
        holder = middle.getparent()
        holder.insert(holder.index(middle), ctrl_begin)
        holder.insert(holder.index(middle) + 1, ctrl_end)
    _clear_paragraph_layout_cache(paragraph.element)  # the field's controls move its text: laid out again
    paragraph.section.mark_dirty()

    # Hancom keeps a memo only in its MEMO field (no hp:memogroup, Hangul 2024): a memo-group memo
    # moves into the field just made and *memo* becomes that field's memo (same object).
    from ..oxml.memo import HwpxOxmlMemo as _GroupMemo, fold_into_field

    if type(memo) is _GroupMemo:
        fold_into_field(memo, field_begin, paragraph.section)
    return memo


def _find_segment(paragraph: Any, match: str, index: int = 0) -> tuple[Any, int, int] | None:
    """Where the *index*-th (from 0) place of *match* lying whole in one stretch of text of
    *paragraph*'s own runs is, in document order and not overlapping: the ``hp:t``, the stretch
    (``-1`` its leading text, ``k`` the text after its child ``k``) and the offset in it."""

    if not match or index < 0:
        return None
    seen = 0
    for run in paragraph.findall(f"{_HP}run"):
        for node in run.findall(f"{_HP}t"):
            stretches = [node.text, *(child.tail for child in node)]
            for stretch, text in enumerate(stretches):
                at = text.find(match) if text else -1
                while at >= 0:
                    if seen == index:
                        return node, stretch - 1, at
                    seen += 1
                    at = text.find(match, at + len(match))
    return None


def _check_match_index(index: object) -> int:
    if isinstance(index, bool) or not isinstance(index, int):
        from ..errors import argument_type_error

        raise argument_type_error("index", index, "int", suggestion="match 가 몇 번째(0부터) 나오는 곳인지 정수로 주세요.")
    return index


def _split_out(paragraph: Any, match: str, index: int = 0) -> Any:
    """Split the ``hp:t`` holding *match* (see :func:`_find_segment`) so that the match is a
    ``hp:t`` of its own, between the text before and after it in the same run; return it."""

    found = _find_segment(paragraph, match, index)
    assert found is not None
    node, stretch, offset = found
    run = node.getparent()
    children = list(node)
    text = node.text if stretch < 0 else children[stretch].tail
    before, after = text[:offset], text[offset + len(match):]
    middle = node.makeelement(node.tag, dict(node.attrib))
    middle.text = match
    rest = node.makeelement(node.tag, dict(node.attrib))
    rest.text = after
    for child in children[stretch + 1:]:
        rest.append(child)  # moves the child (and its tail) out of node
    if stretch < 0:
        node.text = before
    else:
        children[stretch].tail = before
    position = run.index(node)
    run.insert(position + 1, middle)
    if rest.text or len(rest):
        run.insert(position + 2, rest)
    if not node.text and not len(node):
        run.remove(node)
    return middle


@refused_leaves_no_paragraph
def add_memo_with_anchor(
    doc: "HwpxDocument",
    text: str = "",
    *,
    paragraph: "HwpxOxmlParagraph | None" = None,
    section: "HwpxOxmlSection | None" = None,
    paragraph_text: str | None = None,
    memo_id: str | None = None,
    char_pr_id_ref: str | int | None = None,
    attributes: dict[str, str] | None = None,
    field_id: str | None = None,
    author: str | None = None,
    created: "datetime | str | None" = None,
    number: int | None = None,
    paragraph_char_pr_id_ref: str | int | None = None,
    match: str | None = None,
    index: int = 0,
) -> "HwpxOxmlMemo":
    """Create a memo and ensure it is visible by anchoring a MEMO field.

    Returns the anchored :class:`~hwpx.oxml.memo.HwpxOxmlMemo` — its
    ``.paragraph``/``.field_id`` properties (``oxml/memo.py``) replace the
    second and third elements of the 3-tuple 5.x returned. With *match* the
    memo is on that text of the paragraph only (see :func:`attach_memo_field`).
    *paragraph_char_pr_id_ref* is the character shape of the MEMO field's runs.
    """

    if paragraph_text is not None:
        # not text: refused before the memo is made (it was made first, and stayed without its anchor:
        # the document could not be saved)
        from ..oxml._document_primitives import _require_text

        _require_text(paragraph_text)
    index = _check_match_index(index)
    if match is None and index:
        raise HwpxValueError(
            "index picks a place of match; there is no match",
            code="note-argument-conflict",
            context={"caller": "doc.notes.add_memo", "index": index},
            suggestion="Pass match= with index=, or leave index out.",
        )
    if match is not None:
        probe = paragraph_text if paragraph_text is not None else (paragraph.text if paragraph is not None else "")
        # With paragraph_text the paragraph is written before the memo is anchored, so the place asked
        # for (the index-th match) is counted in the new text first: a place that is not there was
        # refused after the paragraph's text had been replaced.
        # It is counted in the text as it will be written: characters XML cannot hold are dropped, and a
        # tab or a line break (a carriage return too) ends a stretch of text (a match does not reach
        # across one).
        import re

        from ..oxml._document_primitives import _ILLEGAL_XML_CHARS

        if paragraph_text is not None and (not match or match not in _ILLEGAL_XML_CHARS.sub("", probe)):
            missing = True  # nowhere in the text, whatever breaks it
        elif paragraph_text is not None:
            pieces = [_ILLEGAL_XML_CHARS.sub("", piece) for piece in re.split(r"\r\n|[\t\n\r]", probe)]
            places = sum(piece.count(match) for piece in pieces)
            missing = places <= index
        else:
            missing = match not in probe
        if match == "" or index < 0 or missing:
            raise HwpxValueError(
                "the text to put the memo on is not in the paragraph"
                + (f" {index + 1} times" if index else ""),
                code="note-match-not-found",
                context={"match": match, "paragraphText": probe},
                suggestion="Pass text that appears in the paragraph within one run (paragraph.runs).",
            )

    # Call the local primitives directly rather than `doc.add_memo`/
    # `doc.attach_memo_field` — both names moved in 6.0 (design table rows
    # 35/43), and going through the facade would fire a DeprecationWarning on
    # every call even when this function is reached via the new
    # `doc.notes.add_memo(paragraph=...)` namespace path.
    memo = add_memo(
        doc,
        text,
        section=section,
        memo_id=memo_id,
        char_pr_id_ref=char_pr_id_ref,
        attributes=attributes,
    )

    target_paragraph = paragraph
    if target_paragraph is None:
        memo_section = memo.group.section
        if memo_section is None:
            raise HwpxValueError(
            "memo is not attached to a section",
            code="note-memo-detached",
            suggestion="Pass a memo created by doc.notes.add_memo().",
        )
        paragraph_value = "" if paragraph_text is None else paragraph_text
        anchor_char = paragraph_char_pr_id_ref or char_pr_id_ref
        target_paragraph = home_paragraph(
            doc, paragraph_value,
            section=memo_section,
            char_pr_id_ref=anchor_char,
        )
    elif paragraph_text is not None:
        target_paragraph.text = paragraph_text

    try:
        attach_memo_field(
            doc,
            target_paragraph,
            memo,
            field_id=field_id,
            author=author,
            created=created,
            number=number,
            char_pr_id_ref=paragraph_char_pr_id_ref,
            match=match,
            index=index,
        )
    except HwpxValueError:
        memo.remove()  # no memo left behind without its anchor
        raise

    return memo
