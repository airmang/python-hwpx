# SPDX-License-Identifier: Apache-2.0
"""Small helpers for editing the text inside ``hp:t``."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from ..errors import HwpxValueError
from ._document_primitives import _HP_NS, _child_tag_like, _is_tab_control_element, _sanitize_text
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

    Each tab becomes an ``hp:tab`` inside it, the way Hancom writes one.
    Elements already inside it (line breaks, tabs, spaces, marks) go, with the
    text after them: they belong to the old value.
    """

    tab_tag = _child_tag_like(text_element, "tab", _HP_NS)
    for child in list(text_element):
        text_element.remove(child)
    segments = value.split("\t")
    text_element.text = _sanitize_text(segments[0])
    for segment in segments[1:]:
        tab_element = text_element.makeelement(tab_tag, {})
        tab_element.tail = _sanitize_text(segment)
        text_element.append(tab_element)


def clear_text_element(text_element: ET.Element) -> None:
    """Empty an ``hp:t``: its text, and the elements inside it with the text after them."""

    for child in list(text_element):
        text_element.remove(child)
    if text_element.text:
        text_element.text = ""
