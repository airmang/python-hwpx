# SPDX-License-Identifier: Apache-2.0
"""Small helpers for editing the text inside ``hp:t`` and for taking a paragraph out of its list."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from ..errors import HwpxValueError
from ._document_primitives import (
    _HP_NS,
    _TEXT_MARK_SPLIT_RE,
    _child_tag_like,
    _fill_text_element,
    _is_tab_control_element,
    _sanitize_text,
)
from .namespaces import tag_local_name


def plain_text_nodes_for_edit(runs: list[ET.Element]) -> list[ET.Element]:
    nodes: list[ET.Element] = []
    for run in runs:
        for child in run:
            if tag_local_name(child.tag) == "t":
                if len(child):
                    raise HwpxValueError(
                        "mixed text markup cannot be edited safely",
                        code="paragraph-mixed-text-unsupported",
                    )
                nodes.append(child)
            elif tag_local_name(child.tag) == "tab" or _is_tab_control_element(child):
                raise HwpxValueError(
                    "tab controls require an explicit run target",
                    code="paragraph-tab-target-required",
                )
    return nodes


def edit_node_candidates(
    nodes: list[ET.Element], prefix: int, end: int
) -> list[tuple[ET.Element, int]]:
    offset = 0
    candidates: list[tuple[ET.Element, int]] = []
    for node in nodes:
        length = len(node.text or "")
        if offset <= prefix and end <= offset + length:
            candidates.append((node, offset))
        offset += length
    return candidates


def sanitize_keeping_tabs(value: str) -> str:
    """``_sanitize_text``, but keep tabs for :func:`set_text_with_tabs`."""

    return "\t".join(_sanitize_text(part) for part in value.split("\t"))


def set_text_with_tabs(text_element: ET.Element, value: str) -> None:
    """Make *value* the whole content of the ``hp:t`` *text_element*.

    Each tab becomes an ``hp:tab`` and each line break an ``hp:lineBreak`` inside it, the way Hancom writes
    them. Elements already inside it (line breaks, tabs, spaces, marks) go, with the text after them: they
    belong to the old value.
    """

    for child in list(text_element):
        text_element.remove(child)
    _fill_text_element(text_element, value)


def text_marks_as_elements(text_element: ET.Element) -> bool:
    """Write each tab or line-break character left in the ``hp:t`` *text_element* as the element
    Hancom writes for it (``hp:tab``, ``hp:lineBreak``), the way :func:`set_text_with_tabs` does.

    For edits that put characters into the text already there (find and replace, a model applied
    back) instead of filling the element: the rest of the element stays as it is. Returns whether
    anything changed.
    """

    tab_tag = _child_tag_like(text_element, "tab", _HP_NS)
    break_tag = _child_tag_like(text_element, "lineBreak", _HP_NS)
    changed = False
    position = 0  # where the elements for the text in front of the next child go
    for holder in (None, *list(text_element)):
        if holder is not None:
            position += 1
        value = (text_element.text if holder is None else holder.tail) or ""
        parts = _TEXT_MARK_SPLIT_RE.split(value)
        if len(parts) == 1:
            continue
        changed = True
        if holder is None:
            text_element.text = parts[0]
        else:
            holder.tail = parts[0]
        for mark, segment in zip(parts[1::2], parts[2::2]):
            element = text_element.makeelement(tab_tag if mark == "\t" else break_tag, {})
            element.tail = segment
            text_element.insert(position, element)
            position += 1
    return changed


def text_marks_as_elements_in(root: ET.Element) -> bool:
    """:func:`text_marks_as_elements` for every ``hp:t`` at or under *root*."""

    changed = False
    for node in list(root.iter()):
        if isinstance(node.tag, str) and tag_local_name(node.tag) == "t":
            changed = text_marks_as_elements(node) or changed
    return changed


def clear_text_element(text_element: ET.Element) -> None:
    """Empty an ``hp:t``: its text, and the elements inside it with the text after them."""

    for child in list(text_element):
        text_element.remove(child)
    if text_element.text:
        text_element.text = ""


def paragraph_container(element: ET.Element, section_element: ET.Element) -> ET.Element | None:
    """The element that directly holds the paragraph *element*: its section or a ``hp:subList``."""

    if hasattr(element, "getparent"):
        return element.getparent()
    return next((node for node in section_element.iter() if any(child is element for child in node)), None)


#: What holds a ``hp:subList`` paragraph list, as a refusal names it.
_SUBLIST_OWNERS = {"tc": "cell", "header": "header", "footer": "footer"}


def remove_paragraph_element(element: ET.Element, section_element: ET.Element) -> bool:
    """Take the paragraph *element* out of the section or ``hp:subList`` holding it.

    Returns ``False`` when it is already gone. The last paragraph of its list
    stays: HWPX needs one ``<hp:p>`` per section, and Hancom cannot open a cell,
    header or footer whose paragraph list is empty.
    """

    parent = paragraph_container(element, section_element)
    if parent is None:
        return False
    if len(parent.findall(f"{{{_HP_NS}}}p")) <= 1:
        if parent is section_element:
            container = "section"
        else:
            owner = paragraph_container(parent, section_element)
            name = tag_local_name(owner.tag) if owner is not None else "subList"
            container = _SUBLIST_OWNERS.get(name, name)
        raise HwpxValueError(
            "섹션과 셀·머리말·꼬리말에는 최소 하나의 단락이 필요합니다. "
            "마지막 단락은 삭제할 수 없습니다.",
            code="paragraph-remove-last",
            context={"container": container},
            suggestion='마지막 단락은 지우지 말고 글을 비우세요(paragraph.text = "").',
        )
    parent.remove(element)
    return True


def own_text_nodes(sublist: ET.Element) -> list[ET.Element]:
    """The ``hp:t`` nodes of a cell's own paragraphs (not those of a table or
    object inside them)."""

    hp_p, hp_run, hp_t = (_child_tag_like(sublist, name, _HP_NS) for name in ("p", "run", "t"))
    return [node for paragraph in sublist.findall(hp_p) for node in paragraph.findall(f"{hp_run}/{hp_t}")]


def new_own_text_node(sublist: ET.Element, char_pr_id_ref: str) -> ET.Element:
    """A text node for a cell whose own paragraphs hold none: in an empty run
    of the first paragraph (Hancom's empty cell is one), or in a new run in
    front of the objects the paragraph holds."""

    hp_p, hp_run, hp_t = (_child_tag_like(sublist, name, _HP_NS) for name in ("p", "run", "t"))
    first = sublist.find(hp_p)
    if first is None:
        first = sublist.makeelement(hp_p, {})
        sublist.append(first)
    run = next((run for run in first.findall(hp_run) if len(run) == 0), None)
    if run is None:
        run = first.makeelement(hp_run, {"charPrIDRef": char_pr_id_ref})
        first.insert(next((i for i, child in enumerate(first) if tag_local_name(child.tag) == "run"), len(first)), run)
    node = run.makeelement(hp_t, {})
    run.append(node)
    return node
