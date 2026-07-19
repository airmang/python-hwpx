# SPDX-License-Identifier: Apache-2.0
"""Memo domain owner behind the :class:`HwpxDocument` facade (S-084)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..oxml.namespaces import HP

if TYPE_CHECKING:
    from hwpx.document import HwpxDocument
    from ..oxml import HwpxOxmlMemo, HwpxOxmlParagraph, HwpxOxmlSection

_HP = HP


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
    section_index: int | None = None,
    memo_shape_id_ref: str | int | None = None,
    memo_id: str | None = None,
    char_pr_id_ref: str | int | None = None,
    attributes: dict[str, str] | None = None,
) -> "HwpxOxmlMemo":
    """Create a memo entry inside *section* (or the last section by default)."""

    if section is None and section_index is not None:
        section = doc._root.sections[section_index]
    if section is None:
        if not doc._root.sections:
            raise ValueError("document does not contain any sections")
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
    number: int = 1,
    char_pr_id_ref: str | int | None = None,
) -> str:
    """Attach a MEMO field control to *paragraph* so Hangul shows *memo*."""

    if paragraph.section is None:
        raise ValueError("paragraph must belong to a section before anchoring a memo")
    if memo.group.section is None:
        raise ValueError("memo is not attached to a section")

    field_value = field_id or uuid.uuid4().hex
    author_value = author or memo.attributes.get("author") or ""

    created_value = created if created is not None else memo.attributes.get("createDateTime")
    if isinstance(created_value, datetime):
        created_value = created_value.strftime("%Y-%m-%d %H:%M:%S")
    elif created_value is None:
        created_value = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    else:
        created_value = str(created_value)

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
            "editable": "true",
            "dirty": "false",
            "fieldid": field_value,
        },
    )

    parameters = _append_element(field_begin, f"{_HP}parameters", {"count": "5", "name": ""})
    _append_element(parameters, f"{_HP}stringParam", {"name": "ID"}).text = memo.id or ""
    _append_element(parameters, f"{_HP}integerParam", {"name": "Number"}).text = str(max(1, number))
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
            "id": f"memo-field-{memo.id or field_value}",
            "textDirection": "HORIZONTAL",
            "lineWrap": "BREAK",
            "vertAlign": "TOP",
        },
    )
    sub_para = _append_element(
        sub_list,
        f"{_HP}p",
        {
            "id": f"memo-field-{(memo.id or field_value)}-p",
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
    _append_element(ctrl_end, f"{_HP}fieldEnd", {"beginIDRef": field_value, "fieldid": field_value})

    paragraph.element.insert(0, run_begin)
    paragraph.element.append(run_end)
    paragraph.section.mark_dirty()

    return field_value


def add_memo_with_anchor(
    doc: "HwpxDocument",
    text: str = "",
    *,
    paragraph: "HwpxOxmlParagraph | None" = None,
    section: "HwpxOxmlSection | None" = None,
    section_index: int | None = None,
    paragraph_text: str | None = None,
    memo_shape_id_ref: str | int | None = None,
    memo_id: str | None = None,
    char_pr_id_ref: str | int | None = None,
    attributes: dict[str, str] | None = None,
    field_id: str | None = None,
    author: str | None = None,
    created: "datetime | str | None" = None,
    number: int = 1,
    anchor_char_pr_id_ref: str | int | None = None,
) -> "tuple[HwpxOxmlMemo, HwpxOxmlParagraph, str]":
    """Create a memo and ensure it is visible by anchoring a MEMO field."""

    memo = doc.add_memo(
        text,
        section=section,
        section_index=section_index,
        memo_shape_id_ref=memo_shape_id_ref,
        memo_id=memo_id,
        char_pr_id_ref=char_pr_id_ref,
        attributes=attributes,
    )

    target_paragraph = paragraph
    if target_paragraph is None:
        memo_section = memo.group.section
        if memo_section is None:
            raise ValueError("memo must belong to a section")
        paragraph_value = "" if paragraph_text is None else paragraph_text
        anchor_char = anchor_char_pr_id_ref or char_pr_id_ref
        target_paragraph = doc.add_paragraph(
            paragraph_value,
            section=memo_section,
            char_pr_id_ref=anchor_char,
        )
    elif paragraph_text is not None:
        target_paragraph.text = paragraph_text

    field_value = doc.attach_memo_field(
        target_paragraph,
        memo,
        field_id=field_id,
        author=author,
        created=created,
        number=number,
        char_pr_id_ref=anchor_char_pr_id_ref,
    )

    return memo, target_paragraph, field_value
