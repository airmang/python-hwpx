# SPDX-License-Identifier: Apache-2.0
"""Shared XML/identity primitives for cohesive HWPX OXML owners."""

from __future__ import annotations

import re as _re
from copy import deepcopy
from typing import Iterable, Optional, TypeVar
from uuid import uuid4
import xml.etree.ElementTree as ET

from lxml import etree as LET  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

from .namespaces import (
    HWPML_COMPAT_ROOT_NAMESPACES,
    HC,
    HC_NS,
    HH,
    HH_NS,
    HP,
    HP_NS,
    HS,
    HS_NS,
    register_owpml_namespaces,
    tag_local_name,
    tag_namespace,
)

register_owpml_namespaces(ET.register_namespace)

_HP_NS = HP_NS
_HP = HP
_HS_NS = HS_NS
_HS = HS
_HH_NS = HH_NS
_HH = HH
_HC_NS = HC_NS
_HC = HC

_DEFAULT_PARAGRAPH_ATTRS = {
    "paraPrIDRef": "0",
    "styleIDRef": "0",
    "pageBreak": "0",
    "columnBreak": "0",
    "merged": "0",
}

_DEFAULT_CELL_WIDTH = 7200
_DEFAULT_CELL_HEIGHT = 3600

_BASIC_BORDER_FILL_ATTRIBUTES = {
    "threeD": "0",
    "shadow": "0",
    "centerLine": "NONE",
    "breakCellSeparateLine": "0",
}

_BASIC_BORDER_CHILDREN: tuple[tuple[str, dict[str, str]], ...] = (
    ("slash", {"type": "NONE", "Crooked": "0", "isCounter": "0"}),
    ("backSlash", {"type": "NONE", "Crooked": "0", "isCounter": "0"}),
    ("leftBorder", {"type": "SOLID", "width": "0.12 mm", "color": "#000000"}),
    ("rightBorder", {"type": "SOLID", "width": "0.12 mm", "color": "#000000"}),
    ("topBorder", {"type": "SOLID", "width": "0.12 mm", "color": "#000000"}),
    ("bottomBorder", {"type": "SOLID", "width": "0.12 mm", "color": "#000000"}),
    ("diagonal", {"type": "SOLID", "width": "0.1 mm", "color": "#000000"}),
)

_BORDER_SIDE_ELEMENTS = {
    "left": "leftBorder",
    "right": "rightBorder",
    "top": "topBorder",
    "bottom": "bottomBorder",
}

T = TypeVar("T")

# Characters forbidden inside XML 1.0 text nodes (XML spec §2.2).
# Tab (U+0009) is legal XML but illegal inside <hp:t>; it must be
# represented as a <hp:ctrl id="tab"/> element instead.
_ILLEGAL_XML_CHARS = _re.compile(
    r"[\x00-\x08\x09\x0b\x0c\x0d\x0e-\x1f\ufffe\uffff]"
)


def _sanitize_text(value: str) -> str:
    """Strip characters that are illegal inside an HWPML ``<hp:t>`` node.

    Tab (``\\t`` / U+0009) is stripped because HWPML requires it to be
    represented as a dedicated ``<hp:ctrl>`` element, not as raw text.
    Carriage return (``\\r`` / U+000D) is stripped; newline (``\\n`` / U+000A)
    is preserved for multiline cells.
    """
    return _ILLEGAL_XML_CHARS.sub("", value)


def _child_tag_like(parent: ET.Element, local_name: str, fallback_namespace: str) -> str:
    namespace = tag_namespace(parent.tag) or fallback_namespace
    return f"{{{namespace}}}{local_name}"


def _children_by_local(parent: ET.Element, local_name: str) -> list[ET.Element]:
    return [child for child in list(parent) if tag_local_name(child.tag) == local_name]


def _first_child_by_local(parent: ET.Element, local_name: str) -> ET.Element | None:
    for child in parent:
        if tag_local_name(child.tag) == local_name:
            return child
    return None


_FONT_REF_ATTRIBUTES = ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user")
_FONT_FACE_LANG_TO_REF = {
    "HANGUL": "hangul",
    "LATIN": "latin",
    "HANJA": "hanja",
    "JAPANESE": "japanese",
    "OTHER": "other",
    "SYMBOL": "symbol",
    "USER": "user",
}


def _normalize_color(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if normalized.lower() == "none":
        return "none"
    return "#" + normalized.lstrip("#").upper()


def _char_height_from_points(value: int | float | None) -> str | None:
    if value is None:
        return None
    return str(max(round(float(value) * 100), 0))


def _serialize_xml(element: ET.Element) -> bytes:
    """Return a UTF-8 encoded XML document for *element*."""
    xml_bytes = ET.tostring(element, encoding="utf-8", xml_declaration=False)
    if element.tag in {_HS + "sec", _HH + "head"}:
        root = LET.fromstring(xml_bytes)
        wrapped = LET.Element(root.tag, nsmap=HWPML_COMPAT_ROOT_NAMESPACES)
        wrapped.attrib.update(root.attrib)
        wrapped.text = root.text
        wrapped.tail = root.tail
        for child in root:
            wrapped.append(child)
        return LET.tostring(
            wrapped,
            encoding="UTF-8",
            xml_declaration=True,
            standalone=True,
        )
    return ET.tostring(element, encoding="utf-8", xml_declaration=True)


def _paragraph_id() -> str:
    """Generate an identifier for a new paragraph element."""
    return str(uuid4().int & 0x7FFFFFFF)


def _object_id() -> str:
    """Generate an identifier suitable for table and shape objects."""
    return str(uuid4().int & 0x7FFFFFFF)


def _memo_id() -> str:
    """Generate a lightweight identifier for memo elements."""
    return str(uuid4().int & 0x7FFFFFFF)


def _refresh_copied_paragraph_subtree_ids(paragraph: ET.Element) -> None:
    """Assign fresh local identifiers inside a copied paragraph subtree.

    This is intentionally narrow: it refreshes paragraph ids for the copied
    paragraph and any nested paragraphs (for example inside table cells), plus
    common object identifiers used by tables/shapes/notes. Reference-style
    attributes such as ``borderFillIDRef`` are left untouched.
    """

    for node in paragraph.iter():
        if node.tag == f"{_HP}p":
            node.set("id", _paragraph_id())
            continue

        if "id" in node.attrib and node.tag in {
            f"{_HP}tbl",
            f"{_HP}pic",
            f"{_HP}container",
            f"{_HP}ole",
            f"{_HP}equation",
            f"{_HP}textart",
            f"{_HP}video",
            f"{_HP}header",
            f"{_HP}footer",
        }:
            node.set("id", _object_id())

        if "instId" in node.attrib:
            node.set("instId", _object_id())


def _clone_paragraph_element(paragraph: ET.Element) -> ET.Element:
    """Return a deep-copied paragraph element with refreshed local ids."""

    cloned = deepcopy(paragraph)
    _refresh_copied_paragraph_subtree_ids(cloned)
    return cloned


def _create_paragraph_element(
    text: str,
    *,
    char_pr_id_ref: str | int | None = None,
    para_pr_id_ref: str | int | None = None,
    style_id_ref: str | int | None = None,
    paragraph_attributes: Optional[dict[str, str]] = None,
    run_attributes: Optional[dict[str, str]] = None,
    parent: ET.Element | None = None,
) -> ET.Element:
    """Return a paragraph element populated with a single run and text node."""

    attrs = {"id": _paragraph_id(), **_DEFAULT_PARAGRAPH_ATTRS}
    attrs.update(paragraph_attributes or {})

    if para_pr_id_ref is not None:
        attrs["paraPrIDRef"] = str(para_pr_id_ref)
    if style_id_ref is not None:
        attrs["styleIDRef"] = str(style_id_ref)

    if parent is None:
        paragraph = ET.Element(f"{_HP}p", attrs)
    else:
        paragraph = parent.makeelement(_child_tag_like(parent, "p", _HP_NS), attrs)

    run_attrs: dict[str, str] = dict(run_attributes or {})
    if char_pr_id_ref is not None:
        run_attrs.setdefault("charPrIDRef", str(char_pr_id_ref))
    else:
        run_attrs.setdefault("charPrIDRef", "0")

    run = paragraph.makeelement(_child_tag_like(paragraph, "run", _HP_NS), run_attrs)
    paragraph.append(run)
    _append_text_with_tabs(run, text)
    return paragraph


_LAYOUT_CACHE_ELEMENT_NAMES = {"linesegarray"}


def _clear_paragraph_layout_cache(paragraph: ET.Element) -> int:
    """Remove cached layout metadata such as ``<hp:lineSegArray>``."""

    removed = 0
    for child in list(paragraph):
        if _element_local_name(child).lower() in _LAYOUT_CACHE_ELEMENT_NAMES:
            paragraph.remove(child)
            removed += 1
    return removed


def _simple_paragraph_text_length(paragraph: ET.Element) -> int | None:
    total = 0
    for child in paragraph:
        child_name = _element_local_name(child).lower()
        if child_name in _LAYOUT_CACHE_ELEMENT_NAMES:
            continue
        if child_name != "run":
            return None
        for run_child in child:
            run_child_name = _element_local_name(run_child).lower()
            if run_child_name == "t":
                total += len("".join(run_child.itertext()))
            elif run_child_name in {
                "tab",
                "linebreak",
                "hyphen",
                "nbspace",
            } or _is_tab_control_element(run_child):
                total += 1
            else:
                return None
    return total


def _remove_stale_paragraph_layout_cache(paragraph: ET.Element) -> bool:
    text_length = _simple_paragraph_text_length(paragraph)
    if text_length is None:
        return False

    stale = False
    for child in paragraph:
        if _element_local_name(child).lower() not in _LAYOUT_CACHE_ELEMENT_NAMES:
            continue
        for line_seg in child:
            if _element_local_name(line_seg).lower() != "lineseg":
                continue
            textpos = line_seg.get("textpos")
            if textpos is None:
                continue
            try:
                if int(textpos) > text_length:
                    stale = True
                    break
            except ValueError:
                stale = True
                break
        if stale:
            break

    if stale:
        _clear_paragraph_layout_cache(paragraph)
    return stale


def _element_local_name(node: ET.Element) -> str:
    # Delegates to ``tag_local_name`` so comment / PI nodes (whose ``tag`` is a
    # callable such as ``etree.Comment``, not a string) yield ``""`` instead of
    # raising; ``""`` never matches a real OWPML tag, so such nodes are skipped.
    return tag_local_name(node.tag)


def _append_child(
    parent: ET.Element,
    tag: str,
    attrib: dict[str, str] | None = None,
) -> ET.Element:
    """Create and append a child element compatible with both lxml and stdlib.

    Uses ``parent.makeelement()`` so the child type matches the parent.
    """
    child = parent.makeelement(tag, attrib or {})
    parent.append(child)
    return child


def _is_tab_control_element(node: ET.Element) -> bool:
    return tag_local_name(node.tag) == "ctrl" and (node.get("id") or "").lower() == "tab"


def _append_text_with_tabs(run: ET.Element, value: str) -> None:
    segments = value.split("\t")
    text_tag = _child_tag_like(run, "t", _HP_NS)
    tab_tag = _child_tag_like(run, "tab", _HP_NS)
    for index, segment in enumerate(segments):
        text_element = run.makeelement(text_tag, {})
        text_element.text = _sanitize_text(segment)
        run.append(text_element)
        if index < len(segments) - 1:
            run.append(run.makeelement(tab_tag, {}))


def _normalize_length(value: str | None) -> str:
    if value is None:
        return ""
    return value.replace(" ", "").lower()


def _is_integer_literal(value: str | None) -> bool:
    if value is None:
        return False
    try:
        int(value.strip())
    except (TypeError, ValueError):
        return False
    return True


def _border_fill_is_basic_solid_line(element: ET.Element) -> bool:
    if _element_local_name(element) != "borderFill":
        return False

    for attr, expected in _BASIC_BORDER_FILL_ATTRIBUTES.items():
        actual = element.get(attr)
        if attr == "centerLine":
            if (actual or "").upper() != expected:
                return False
        else:
            if actual != expected:
                return False

    for child_name, child_attrs in _BASIC_BORDER_CHILDREN:
        child = element.find(f"{_HH}{child_name}")
        if child is None:
            return False
        for attr, expected in child_attrs.items():
            actual = child.get(attr)
            if attr == "type":
                if (actual or "").upper() != expected:
                    return False
            elif attr == "width":
                if _normalize_length(actual) != _normalize_length(expected):
                    return False
            elif attr == "color":
                if (actual or "").upper() != expected.upper():
                    return False
            else:
                if actual != expected:
                    return False

    for child in element:
        if _element_local_name(child) == "fillBrush":
            return False

    return True


def _create_basic_border_fill_element(border_id: str) -> ET.Element:
    attrs = {"id": border_id, **_BASIC_BORDER_FILL_ATTRIBUTES}
    element = ET.Element(f"{_HH}borderFill", attrs)
    for child_name, child_attrs in _BASIC_BORDER_CHILDREN:
        ET.SubElement(element, f"{_HH}{child_name}", dict(child_attrs))
    return element


def _border_fill_child_attrs(
    *,
    active: bool,
    color: str,
    width: str,
) -> dict[str, str]:
    return {
        "type": "SOLID" if active else "NONE",
        "width": width,
        "color": color,
    }


def _normalize_border_side_names(active_borders: Iterable[str] | None) -> set[str]:
    if active_borders is None:
        return set(_BORDER_SIDE_ELEMENTS)
    normalized: set[str] = set()
    for side in active_borders:
        key = str(side).strip().lower()
        if key not in _BORDER_SIDE_ELEMENTS:
            raise ValueError(f"unsupported border side: {side!r}")
        normalized.add(key)
    return normalized


def _border_fill_fill_color(element: ET.Element) -> str | None:
    fill_brush = next(
        (child for child in element if _element_local_name(child) == "fillBrush"),
        None,
    )
    if fill_brush is None:
        return None
    win_brush = next(
        (child for child in fill_brush if _element_local_name(child) == "winBrush"),
        None,
    )
    if win_brush is None:
        return None
    return win_brush.get("faceColor")


def _border_fill_matches(
    element: ET.Element,
    *,
    border_color: str,
    border_width: str,
    fill_color: str | None,
    active_borders: set[str],
) -> bool:
    if _element_local_name(element) != "borderFill":
        return False
    for attr, expected in _BASIC_BORDER_FILL_ATTRIBUTES.items():
        actual = element.get(attr)
        if attr == "centerLine":
            if (actual or "").upper() != expected:
                return False
        elif actual != expected:
            return False

    expected_fill = _normalize_color(fill_color)
    if _border_fill_fill_color(element) != expected_fill:
        return False

    for side, child_name in _BORDER_SIDE_ELEMENTS.items():
        child = element.find(f"{_HH}{child_name}")
        if child is None:
            return False
        expected_type = "SOLID" if side in active_borders else "NONE"
        if (child.get("type") or "").upper() != expected_type:
            return False
        if _normalize_length(child.get("width")) != _normalize_length(border_width):
            return False
        if (child.get("color") or "").upper() != border_color.upper():
            return False

    for child_name in ("slash", "backSlash", "diagonal"):
        child = element.find(f"{_HH}{child_name}")
        if child is None:
            return False
        if (child.get("type") or "").upper() != "NONE":
            return False

    return True


def _create_border_fill_element(
    border_id: str,
    *,
    border_color: str,
    border_width: str,
    fill_color: str | None,
    active_borders: set[str],
) -> ET.Element:
    element = ET.Element(f"{_HH}borderFill", {"id": border_id, **_BASIC_BORDER_FILL_ATTRIBUTES})
    ET.SubElement(element, f"{_HH}slash", {"type": "NONE", "Crooked": "0", "isCounter": "0"})
    ET.SubElement(element, f"{_HH}backSlash", {"type": "NONE", "Crooked": "0", "isCounter": "0"})
    for side, child_name in _BORDER_SIDE_ELEMENTS.items():
        ET.SubElement(
            element,
            f"{_HH}{child_name}",
            _border_fill_child_attrs(
                active=side in active_borders,
                color=border_color,
                width=border_width,
            ),
        )
    ET.SubElement(
        element,
        f"{_HH}diagonal",
        _border_fill_child_attrs(active=False, color=border_color, width=border_width),
    )
    normalized_fill = _normalize_color(fill_color)
    if normalized_fill is not None:
        fill_brush = ET.SubElement(element, f"{_HC}fillBrush")
        ET.SubElement(
            fill_brush,
            f"{_HC}winBrush",
            {"faceColor": normalized_fill, "hatchColor": "#FF000000", "alpha": "0"},
        )
    return element


def _distribute_size(total: int, parts: int) -> list[int]:
    """Return *parts* integers that sum to *total* and are as even as possible."""

    if parts <= 0:
        return []

    base = total // parts
    remainder = total - (base * parts)
    sizes: list[int] = []
    for index in range(parts):
        value = base
        if remainder > 0:
            value += 1
            remainder -= 1
        sizes.append(max(value, 0))
    return sizes


def _default_cell_attributes(border_fill_id_ref: str) -> dict[str, str]:
    return {
        "name": "",
        "header": "0",
        "hasMargin": "0",
        "protect": "0",
        "editable": "0",
        "dirty": "0",
        "borderFillIDRef": border_fill_id_ref,
    }


def _default_cell_paragraph_attributes() -> dict[str, str]:
    attrs = dict(_DEFAULT_PARAGRAPH_ATTRS)
    attrs["id"] = _paragraph_id()
    return attrs


def _default_cell_margin_attributes() -> dict[str, str]:
    return {"left": "0", "right": "0", "top": "0", "bottom": "0"}


def _get_int_attr(element: ET.Element, name: str, default: int = 0) -> int:
    """Return *name* attribute of *element* as an integer."""

    value = element.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default
def _default_sublist_attributes() -> dict[str, str]:
    """Return standard attributes for a ``<hp:subList>`` element.

    Matches real HWPX output and the OWPML ParaListType schema.
    ``vertAlign`` defaults to "CENTER" for table cells; callers can
    override as needed.
    """
    return {
        "id": "",
        "textDirection": "HORIZONTAL",
        "lineWrap": "BREAK",
        "vertAlign": "CENTER",
        "linkListIDRef": "0",
        "linkListNextIDRef": "0",
        "textWidth": "0",
        "textHeight": "0",
        "hasTextRef": "0",
        "hasNumRef": "0",
    }
