# SPDX-License-Identifier: Apache-2.0
"""Memo domain owner behind the :class:`HwpxDocument` facade."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from ..errors import HwpxValueError

from ..oxml._document_primitives import _clear_paragraph_layout_cache, _object_id, current_time
from ..oxml.namespaces import HP

if TYPE_CHECKING:
    from hwpx.document import HwpxDocument
    from ..oxml import HwpxOxmlMemo, HwpxOxmlParagraph, HwpxOxmlSection

_HP = HP

#: Hancom writes a memo's ``CreateDateTime`` as UTC ISO 8601 ("2024-03-14T22:38:25Z").
_HANCOM_MEMO_TIME = "%Y-%m-%dT%H:%M:%SZ"


def _memo_create_time(value: "datetime | str | None") -> str:
    """Format a memo timestamp the way Hancom reads it.

    The Hancom engine cannot read "2024-12-02 09:00:00": opening such a file
    turns the memo's creation time into a 1601 FILETIME, and saving keeps the
    broken value. Naive values are local time, as ``datetime.now()`` gives, and
    are converted to UTC. A string that is not a timestamp is kept as given.
    """

    if value is None:
        moment = current_time()
    elif isinstance(value, datetime):
        moment = value
    else:
        text = str(value).strip()
        try:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
    return moment.astimezone(timezone.utc).strftime(_HANCOM_MEMO_TIME)


#: The ``fieldid`` Hancom gives every memo field: the control id ``%%me`` as a number.
MEMO_FIELD_ID = str(int.from_bytes(b"%%me", "big"))


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
    memo_shape_id_ref: str | int | None = None,
    memo_id: str | None = None,
    char_pr_id_ref: str | int | None = None,
    attributes: dict[str, str] | None = None,
) -> "HwpxOxmlMemo":
    """Create a memo entry inside *section* (or the last section by default)."""

    if section is None:
        if not doc._root.sections:
            raise HwpxValueError(
            "document does not contain any sections",
            code="section-missing",
            suggestion="Call doc.add_section() first.",
        )
        section = doc._root.sections[-1]
    return section.add_memo(
        text,
        memo_shape_id_ref=memo_shape_id_ref,
        memo_id=memo_id,
        char_pr_id_ref=char_pr_id_ref,
        attributes=attributes,
    )


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
) -> "HwpxOxmlMemo":
    """Attach a MEMO field control to *paragraph* so Hangul shows *memo*.

    The field spans the whole paragraph, or with *match* only the first occurrence
    of that text (it must lie in one run, between no other marks): the memo is then
    on those characters, as Hancom anchors a memo put on a selection.

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
    if match is not None and _find_segment(paragraph.element, match) is None:
        raise HwpxValueError(
            "the text to put the memo on is not in one run of the paragraph",
            code="note-match-not-found",
            context={"match": match, "paragraphText": paragraph.text},
            suggestion="Pass text that appears in the paragraph within one run (paragraph.runs).",
        )

    field_value = field_id or _object_id()
    order = _next_memo_zorder(doc)
    author_value = author or memo.attributes.get("author") or ""

    created_value = _memo_create_time(
        created if created is not None else memo.attributes.get("createDateTime")
    )

    memo_shape_id = memo.memo_shape_id_ref or ""

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

    # ``cnt`` as in Hancom's own fields (and every other python-hwpx field
    # writer); Hancom rewrites ``count`` to ``cnt`` when it saves.
    parameters = _append_element(field_begin, f"{_HP}parameters", {"cnt": "5", "name": ""})
    _append_element(parameters, f"{_HP}stringParam", {"name": "ID"}).text = memo.id or ""
    _append_element(parameters, f"{_HP}integerParam", {"name": "Number"}).text = (
        order if number is None else str(max(1, number))
    )
    _append_element(parameters, f"{_HP}stringParam", {"name": "CreateDateTime"}).text = created_value
    _append_element(parameters, f"{_HP}stringParam", {"name": "Author"}).text = author_value
    # Hancom's own files use ``MemoShapeIDRef`` (65535 = the built-in default memo
    # shape) — an empty/absent ref leaves the memo box unlinked.
    _append_element(parameters, f"{_HP}stringParam", {"name": "MemoShapeIDRef"}).text = (
        memo_shape_id or "65535"
    )

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
        paragraph.element.insert(0, run_begin)
        paragraph.element.append(run_end)
    else:
        middle = _split_out(paragraph.element, match)
        holder = middle.getparent()
        holder.insert(holder.index(middle), ctrl_begin)
        holder.insert(holder.index(middle) + 1, ctrl_end)
    _clear_paragraph_layout_cache(paragraph.element)  # the field's controls move its text: laid out again
    paragraph.section.mark_dirty()

    return memo


def _find_segment(paragraph: Any, match: str) -> tuple[Any, int, int] | None:
    """Where *match* first lies whole in one stretch of text of *paragraph*'s own runs:
    the ``hp:t``, the stretch (``-1`` its leading text, ``k`` the text after its child
    ``k``) and the offset in it."""

    if not match:
        return None
    for run in paragraph.findall(f"{_HP}run"):
        for node in run.findall(f"{_HP}t"):
            stretches = [node.text, *(child.tail for child in node)]
            for index, text in enumerate(stretches):
                if text and match in text:
                    return node, index - 1, text.index(match)
    return None


def _split_out(paragraph: Any, match: str) -> Any:
    """Split the ``hp:t`` holding *match* (see :func:`_find_segment`) so that the match is a
    ``hp:t`` of its own, between the text before and after it in the same run; return it."""

    found = _find_segment(paragraph, match)
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


def add_memo_with_anchor(
    doc: "HwpxDocument",
    text: str = "",
    *,
    paragraph: "HwpxOxmlParagraph | None" = None,
    section: "HwpxOxmlSection | None" = None,
    paragraph_text: str | None = None,
    memo_shape_id_ref: str | int | None = None,
    memo_id: str | None = None,
    char_pr_id_ref: str | int | None = None,
    attributes: dict[str, str] | None = None,
    field_id: str | None = None,
    author: str | None = None,
    created: "datetime | str | None" = None,
    number: int | None = None,
    paragraph_char_pr_id_ref: str | int | None = None,
    match: str | None = None,
) -> "HwpxOxmlMemo":
    """Create a memo and ensure it is visible by anchoring a MEMO field.

    Returns the anchored :class:`~hwpx.oxml.memo.HwpxOxmlMemo` — its
    ``.paragraph``/``.field_id`` properties (``oxml/memo.py``) replace the
    second and third elements of the 3-tuple 5.x returned. With *match* the
    memo is on that text of the paragraph only (see :func:`attach_memo_field`).
    *paragraph_char_pr_id_ref* is the character shape of the MEMO field's runs.
    """

    if match is not None:
        probe = paragraph_text if paragraph_text is not None else (paragraph.text if paragraph is not None else "")
        if match == "" or match not in probe:
            raise HwpxValueError(
                "the text to put the memo on is not in the paragraph",
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
        memo_shape_id_ref=memo_shape_id_ref,
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
        target_paragraph = doc.add_paragraph(
            paragraph_value,
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
        )
    except HwpxValueError:
        memo.remove()  # no memo left behind without its anchor
        raise

    return memo
