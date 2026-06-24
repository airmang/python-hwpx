# SPDX-License-Identifier: Apache-2.0
"""Shared XML helpers for the design composer/harvester (lxml element surgery).

Kept tiny and dependency-free so both :mod:`hwpx.design.harvest` (build the
skeleton + fragments once) and :mod:`hwpx.design.composer` (lower a plan) share
exactly one implementation of the delicate bits: ``secPr`` preservation, body
replacement, and lineseg-cache stripping.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Iterable

from lxml import etree

HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"


def ln(tag: object) -> str:
    return str(tag).rsplit("}", 1)[-1]


def hp(element: etree._Element, name: str) -> str:
    """Namespaced tag for *name* using the element's own paragraph namespace."""

    ns = element.tag.rsplit("}", 1)[0].lstrip("{") if "}" in element.tag else HP_NS
    return f"{{{ns}}}{name}"


def iter_local(element: etree._Element, name: str) -> Iterable[etree._Element]:
    for child in element.iter():
        if ln(child.tag) == name:
            yield child


def children_local(element: etree._Element, name: str) -> list[etree._Element]:
    return [c for c in element if ln(c.tag) == name]


def first_run(paragraph: etree._Element) -> etree._Element | None:
    for child in paragraph:
        if ln(child.tag) == "run":
            return child
    return None


def find_secpr(section_element: etree._Element) -> etree._Element | None:
    for el in section_element.iter():
        if ln(el.tag) == "secPr":
            return el
    return None


def strip_lineseg(element: etree._Element) -> None:
    """Remove every ``<hp:linesegarray>`` under *element* (edited → recompute)."""

    for cache in list(iter_local(element, "linesegarray")):
        parent = cache.getparent()
        if parent is not None:
            parent.remove(cache)


def set_paragraph_text(paragraph: etree._Element, text: str) -> None:
    """Put *text* in the paragraph's first ``<hp:t>``, clear the rest, drop cache.

    Preserves the run's ``charPrIDRef`` (the harvested style) — only the text
    content changes.
    """

    t_nodes = [t for t in iter_local(paragraph, "t") if not _under_table(paragraph, t)]
    if t_nodes:
        primary = t_nodes[0]
        primary.text = text
        for child in list(primary):  # drop inline children that held fragments
            primary.remove(child)
        for node in t_nodes[1:]:
            node.text = ""
            for child in list(node):
                node.remove(child)
    else:
        run = first_run(paragraph)
        if run is not None:
            t = etree.SubElement(run, hp(paragraph, "t"))
            t.text = text
    strip_lineseg(paragraph)


def _under_table(paragraph: etree._Element, node: etree._Element) -> bool:
    parent = node.getparent()
    while parent is not None and parent is not paragraph:
        if ln(parent.tag) in ("tbl", "tc", "subList"):
            return True
        parent = parent.getparent()
    return False


def move_secpr_into(first_paragraph: etree._Element, secpr: etree._Element) -> None:
    """Make *first_paragraph*'s first run carry *secpr* (page setup preserved).

    HWPX requires ``secPr`` on the first paragraph's first run; the composer drops
    the skeleton's empty carrier paragraph, so the secPr rides into the first real
    fragment instead.
    """

    run = first_run(first_paragraph)
    if run is None:
        run = etree.SubElement(first_paragraph, hp(first_paragraph, "run"), {"charPrIDRef": "0"})
        first_paragraph.insert(0, run)
    # Remove any secPr already present, then insert the captured one first.
    for existing in list(children_local(run, "secPr")):
        run.remove(existing)
    run.insert(0, deepcopy(secpr))


def replace_section_body(
    section_element: etree._Element, paragraphs: list[etree._Element]
) -> None:
    """Replace the section's ``<hp:p>`` children with *paragraphs* (in order)."""

    insert_at = None
    for index, child in enumerate(list(section_element)):
        if ln(child.tag) == "p":
            if insert_at is None:
                insert_at = index
            section_element.remove(child)
    if insert_at is None:
        insert_at = len(list(section_element))
    for offset, paragraph in enumerate(paragraphs):
        section_element.insert(insert_at + offset, paragraph)


__all__ = [
    "HP_NS",
    "ln",
    "hp",
    "iter_local",
    "children_local",
    "first_run",
    "find_secpr",
    "strip_lineseg",
    "set_paragraph_text",
    "move_secpr_into",
    "replace_section_body",
]
