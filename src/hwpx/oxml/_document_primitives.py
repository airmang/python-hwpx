# SPDX-License-Identifier: Apache-2.0
"""Shared XML/identity primitives for cohesive HWPX OXML owners."""

from __future__ import annotations

import re as _re
from copy import deepcopy
from typing import Iterable, Mapping, Optional, TypeVar
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

        # 스키마·실한컴 산출물의 속성명은 소문자 "instid"다. 과거 이 코드가
        # 방출한 "instId"(카멜케이스)를 실은 파일도 재발급 대상에 남긴다 —
        # 속성명 자체는 보존(바이트 보수), 값만 재발급.
        for inst_attr in ("instid", "instId"):
            if inst_attr in node.attrib:
                node.set(inst_attr, _object_id())


def _clone_paragraph_element(paragraph: ET.Element) -> ET.Element:
    """Return a deep-copied paragraph element with refreshed local ids.

    Cached line layout (``hp:linesegarray``) is dropped from the clone and
    every nested paragraph (table cells, drawing text): a clone is always
    new content at a new position, so the source's absolute layout never
    holds for it. Hancom re-lays-out cache-less paragraphs cleanly
    (render-verified), while a carried cache is a latent glyph-overlap
    hazard the save-time stale sweep cannot judge once the text and cache
    disagree through a non-clearing edit path.
    """

    cloned = deepcopy(paragraph)
    _refresh_copied_paragraph_subtree_ids(cloned)
    for node in cloned.iter():
        if _element_local_name(node) == "p":
            _clear_paragraph_layout_cache(node)
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


def _reposition_child_before_any(
    parent: ET.Element,
    child: ET.Element,
    before_local_names: "Iterable[str]",
) -> None:
    """Move *child* (assumed just appended, i.e. currently ``parent``'s last
    child) to just before the first *other* sibling whose local name is in
    *before_local_names* — or leave it at the end if none is present.

    Shared by object-caption/shape-drawText authoring: both need to land a
    freshly created element at a schema-anchored position without depending
    on any one optional sibling being present (실코퍼스 실측 — Hancom's own
    child order sometimes disagrees with the XSD's declared sequence, so
    this anchors on whatever real neighbour is actually there instead of
    assuming one). Callers create the element via :func:`_append_child`
    first — element construction and repositioning are kept as two calls so
    the tag literal stays directly next to ``_append_child`` (원장 write
    분류기가 태그 리터럴을 그 인접 관용구로만 인식한다).
    """

    before = set(before_local_names)
    target_index: int | None = None
    for index, existing in enumerate(parent):
        if existing is child:
            continue
        if tag_local_name(existing.tag) in before:
            target_index = index
            break
    if target_index is None:
        return
    parent.remove(child)
    parent.insert(target_index, child)


def _reposition_child_after_any(
    parent: ET.Element,
    child: ET.Element,
    after_local_names: "Iterable[str]",
) -> None:
    """Move *child* (assumed just appended) to just after the *last* existing
    sibling whose local name is in *after_local_names* — or leave it at the
    end if none is present (which, since ``child`` was just appended, is
    already where it is).

    ``hp:caption`` uses this anchored on ``outMargin``: 실코퍼스 실측(표·
    도형 둘 다) — 캡션은 항상 outMargin 바로 다음에 온다, 반면 그 뒤에
    무엇이 오는지(표는 inMargin, 도형은 shapeComment, 그림은 아예 없음)는
    호스트 종류마다 다르다. "이름 X 앞"이 아니라 "이름 X 뒤"로 고정하면
    호스트 종류에 기대지 않는다.
    """

    after = set(after_local_names)
    target_index: int | None = None
    for index, existing in enumerate(parent):
        if existing is child:
            continue
        if tag_local_name(existing.tag) in after:
            target_index = index
    if target_index is None:
        return
    parent.remove(child)
    insert_at = target_index + 1
    # child 제거로 target_index 이후 원소가 한 칸씩 당겨졌을 수 있는데,
    # target_index 자체는 child보다 앞이었으므로(방금 찾은 마지막 일치가
    # child가 아니었다) 영향받지 않는다.
    parent.insert(insert_at, child)


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


#: "\n" -> hp:lineBreak, " " (NO-BREAK SPACE) -> hp:nbSpace, "　"
#: (IDEOGRAPHIC SPACE) -> hp:fwSpace. Real corpus (error__20230818__test.hwpx,
#: error__20251107__test.hwpx, error__20250808__...hwpx) confirms all three
#: sit nested inside a single hp:t via mixed content
#: (<hp:t>before<hp:lineBreak/>after</hp:t>) -- unlike hp:tab, which
#: _append_text_with_tabs above represents as a sibling of hp:t within
#: hp:run instead (also schema-legal -- RunType's own choice group lists
#: tab/lineBreak/nbSpace/fwSpace identically -- but not the shape any real
#: sample of these three uses). Tab is intentionally not handled here: it
#: already has an established, presumably Hancom-verified representation
#: via _append_text_with_tabs, and retrofitting it risks behavior no
#: existing caller asked to change.
_RUN_CHOICE_ATOM_MARKERS: dict[str, str] = {
    "\n": "lineBreak",
    " ": "nbSpace",
    "　": "fwSpace",
}
_RUN_CHOICE_ATOM_SPLIT_RE = _re.compile(
    "([" + "".join(_RUN_CHOICE_ATOM_MARKERS) + "])"
)


def _append_text_with_run_choice_atoms(run: ET.Element, value: str) -> None:
    """Insert *value* as a single ``hp:t``, expanding embedded markers to
    the real-corpus ``hp:lineBreak``/``hp:nbSpace``/``hp:fwSpace`` element
    form (see :data:`_RUN_CHOICE_ATOM_MARKERS`) instead of leaving them as
    literal characters in the text node."""

    text_tag = _child_tag_like(run, "t", _HP_NS)
    text_element = run.makeelement(text_tag, {})
    run.append(text_element)

    parts = _RUN_CHOICE_ATOM_SPLIT_RE.split(_sanitize_text(value))
    last_element: ET.Element | None = None
    pending: list[str] = []

    def _flush() -> None:
        joined = "".join(pending) or None
        if last_element is None:
            text_element.text = joined
        else:
            last_element.tail = joined
        pending.clear()

    for part in parts:
        marker_name = _RUN_CHOICE_ATOM_MARKERS.get(part)
        if marker_name is None:
            pending.append(part)
            continue
        _flush()
        marker_tag = _child_tag_like(run, marker_name, _HP_NS)
        marker_element = text_element.makeelement(marker_tag, {})
        text_element.append(marker_element)
        last_element = marker_element
    _flush()


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


#: ``hc:imgBrush/@mode`` vocabulary (Core XML schema.xml:813-884). Real corpus
#: (hwpxlib_corpus, 5 files) observes only ``TOTAL``; the rest are schema-legal
#: but unattested.
FILL_IMAGE_MODES = frozenset({
    "TILE", "TILE_HORZ_TOP", "TILE_HORZ_BOTTOM", "TILE_VERT_LEFT", "TILE_VERT_RIGHT",
    "TOTAL", "CENTER", "CENTER_TOP", "CENTER_BOTTOM", "LEFT_CENTER", "RIGHT_BOTTOM", "ZOOM",
})

#: ``hc:img/@effect`` vocabulary (Core XML schema.xml:602-624).
FILL_IMAGE_EFFECTS = frozenset({"REAL_PIC", "GRAY_SCALE", "BLACK_WHITE"})

#: ``hc:gradation/@type`` vocabulary (Core XML schema.xml:726-753). Real
#: corpus (hwpxlib_corpus, 2 files) observes only ``LINEAR``.
FILL_GRADIENT_TYPES = frozenset({"LINEAR", "RADIAL", "CONICAL", "SQUARE"})


def _normalize_enum_attr(value: str, allowed: frozenset[str], *, label: str) -> str:
    normalized = str(value or "").upper()
    if normalized not in allowed:
        raise ValueError(
            f"unsupported {label} {value!r}; expected one of " + ", ".join(sorted(allowed))
        )
    return normalized


def _normalize_border_type(border_type: str, allowed: frozenset[str]) -> str:
    return _normalize_enum_attr(border_type or "SOLID", allowed, label="border_type")


def _border_fill_image_gradient(
    element: ET.Element,
) -> "tuple[dict[str, str] | None, dict[str, object] | None]":
    """Return ``(image, gradient)`` observed in *element*'s ``fillBrush``.

    At most one is non-``None`` — the schema's ``fillBrush`` choice (Core XML
    schema.xml:650) allows exactly one of winBrush/gradation/imgBrush. Real
    corpus never violates this for ``hh:borderFill`` specifically (the shape
    ``fillBrush`` in ``reader_writer__SimplePolygon.hwpx`` does carry both a
    winBrush and an imgBrush sibling, but that is a *different* fillBrush use
    site — see ``objects.py``'s shape authoring, out of this function's
    scope). Defensively, a ``hh:borderFill`` that did carry more than one
    sibling would report whichever is found first in document order rather
    than fabricating a merge.
    """

    fill_brush = next(
        (child for child in element if _element_local_name(child) == "fillBrush"),
        None,
    )
    if fill_brush is None:
        return None, None
    for child in fill_brush:
        name = _element_local_name(child)
        if name == "imgBrush":
            img = next((c for c in child if _element_local_name(c) == "img"), None)
            if img is None:
                continue
            return {
                "binaryItemIDRef": img.get("binaryItemIDRef") or "",
                "mode": child.get("mode") or "TILE",
                "bright": img.get("bright") or "0",
                "contrast": img.get("contrast") or "0",
                "effect": img.get("effect") or "REAL_PIC",
                "alpha": img.get("alpha") or "0",
            }, None
        if name == "gradation":
            colors = [c.get("value") for c in child if _element_local_name(c) == "color"]
            return None, {
                "type": child.get("type") or "LINEAR",
                "angle": child.get("angle") or "90",
                "centerX": child.get("centerX") or "0",
                "centerY": child.get("centerY") or "0",
                "step": child.get("step") or "255",
                "colorNum": child.get("colorNum") or str(len(colors)),
                "stepCenter": child.get("stepCenter") or "50",
                "alpha": child.get("alpha") or "0",
                "colors": colors,
            }
    return None, None


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
    border_type: str = "SOLID",
) -> dict[str, str]:
    return {
        "type": border_type if active else "NONE",
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


def _border_fill_matches_fill(
    element: ET.Element,
    *,
    fill_color: str | None,
    fill_image: "Mapping[str, str] | None",
    fill_gradient: "Mapping[str, object] | None",
) -> bool:
    """The fill-only half of :func:`_border_fill_matches` — split out to keep
    that function's own branch count inside the C901 ratchet."""

    if fill_image is not None or fill_gradient is not None:
        existing_image, existing_gradient = _border_fill_image_gradient(element)
        if existing_image != (dict(fill_image) if fill_image is not None else None):
            return False
        if existing_gradient != (dict(fill_gradient) if fill_gradient is not None else None):
            return False
        return True

    expected_fill = _normalize_color(fill_color)
    if _border_fill_fill_color(element) != expected_fill:
        return False
    return not any(_border_fill_image_gradient(element))


def _border_fill_matches(
    element: ET.Element,
    *,
    border_color: str,
    border_width: str,
    fill_color: str | None,
    fill_image: "Mapping[str, str] | None" = None,
    fill_gradient: "Mapping[str, object] | None" = None,
    active_borders: set[str],
    border_type: str = "SOLID",
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

    if not _border_fill_matches_fill(
        element, fill_color=fill_color, fill_image=fill_image, fill_gradient=fill_gradient,
    ):
        return False

    for side, child_name in _BORDER_SIDE_ELEMENTS.items():
        child = element.find(f"{_HH}{child_name}")
        if child is None:
            return False
        expected_type = border_type if side in active_borders else "NONE"
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


def _attach_new_child(parent: ET.Element, new_child: ET.Element) -> None:
    """Append *new_child* (built via plain ``ET.Element``) to *parent*,
    converting it to lxml first when *parent* is an lxml tree. The
    ``isinstance``+``fromstring`` dance every ``ensure_*`` creator in
    header_part.py repeats — one shared copy instead of one per call site.
    """

    if isinstance(parent, LET._Element) and not isinstance(new_child, LET._Element):
        new_child = LET.fromstring(ET.tostring(new_child, encoding="utf-8"))
    parent.append(new_child)


def _update_item_count(element: ET.Element, child_local_name: str) -> None:
    element.set("itemCnt", str(len(element.findall(f"{_HH}{child_local_name}"))))


def _append_fill_brush(
    parent: ET.Element,
    *,
    fill_color: str | None,
    fill_image: "Mapping[str, str] | None" = None,
    fill_gradient: "Mapping[str, object] | None" = None,
) -> None:
    """Append ``hc:fillBrush`` (winBrush/imgBrush/gradation) to *parent* if any
    fill was requested — the schema's fillBrush choice (Core XML
    schema.xml:650), so at most one branch fires. Shared by
    :func:`_create_border_fill_element` and
    ``HwpxOxmlHeader.ensure_shading_border_fill``.
    """

    if fill_image is not None:
        fill_brush = _append_child(parent, f"{_HC}fillBrush")
        img_brush = _append_child(fill_brush, f"{_HC}imgBrush", {"mode": fill_image["mode"]})
        _append_child(
            img_brush,
            f"{_HC}img",
            {
                "binaryItemIDRef": fill_image["binaryItemIDRef"],
                "bright": fill_image["bright"],
                "contrast": fill_image["contrast"],
                "effect": fill_image["effect"],
                "alpha": fill_image["alpha"],
            },
        )
    elif fill_gradient is not None:
        fill_brush = _append_child(parent, f"{_HC}fillBrush")
        gradation = _append_child(
            fill_brush,
            f"{_HC}gradation",
            {
                "type": str(fill_gradient["type"]),
                "angle": str(fill_gradient["angle"]),
                "centerX": str(fill_gradient["centerX"]),
                "centerY": str(fill_gradient["centerY"]),
                "step": str(fill_gradient["step"]),
                "colorNum": str(fill_gradient["colorNum"]),
                "stepCenter": str(fill_gradient["stepCenter"]),
                "alpha": str(fill_gradient["alpha"]),
            },
        )
        colors = fill_gradient["colors"]
        assert isinstance(colors, Iterable)
        for color in colors:
            _append_child(gradation, f"{_HC}color", {"value": str(color)})
    else:
        normalized_fill = _normalize_color(fill_color)
        if normalized_fill is not None:
            fill_brush = _append_child(parent, f"{_HC}fillBrush")
            _append_child(
                fill_brush,
                f"{_HC}winBrush",
                {"faceColor": normalized_fill, "hatchColor": "#FF000000", "alpha": "0"},
            )


def _find_shading_border_fill_id(
    element: ET.Element,
    *,
    face_color: str | None,
    fill_image: "Mapping[str, str] | None" = None,
    fill_gradient: "Mapping[str, object] | None" = None,
) -> str | None:
    """Return the id of an existing ``hh:borderFill`` whose fill already
    matches — the dedupe half of ``HwpxOxmlHeader.ensure_shading_border_fill``,
    extracted so that caller stays inside header_part.py's line-count ratchet.
    """

    for border_fill in element.findall(f"{_HH}borderFill"):
        if fill_image is not None or fill_gradient is not None:
            image, gradient = _border_fill_image_gradient(border_fill)
            if image != (dict(fill_image) if fill_image is not None else None):
                continue
            if gradient != (dict(fill_gradient) if fill_gradient is not None else None):
                continue
        elif _border_fill_fill_color(border_fill) != face_color:
            continue
        border_id = border_fill.get("id")
        if border_id:
            return border_id
    return None


def _create_border_fill_element(
    border_id: str,
    *,
    border_color: str,
    border_width: str,
    fill_color: str | None,
    fill_image: "Mapping[str, str] | None" = None,
    fill_gradient: "Mapping[str, object] | None" = None,
    active_borders: set[str],
    border_type: str = "SOLID",
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
                border_type=border_type,
            ),
        )
    ET.SubElement(
        element,
        f"{_HH}diagonal",
        _border_fill_child_attrs(active=False, color=border_color, width=border_width),
    )
    _append_fill_brush(element, fill_color=fill_color, fill_image=fill_image, fill_gradient=fill_gradient)
    return element


#: ``hh:memoPr`` attribute keys compared/emitted verbatim by
#: :func:`_memo_shape_matches`/:func:`_create_memo_shape_element` — every
#: schema attribute except ``id`` (Header XML schema.xml:1705-1753).
_MEMO_SHAPE_ATTRS = (
    "width", "lineWidth", "lineType", "lineColor", "fillColor", "activeColor", "memoType",
)


def _allocate_memo_shape_id(element: ET.Element) -> str:
    """Return the next ``hh:memoPr/@id`` — real corpus (6 files) starts at
    ``1``, never ``0`` (unlike ``hh:borderFill``), so this mirrors
    ``HwpxOxmlHeader._allocate_border_fill_id`` with that one difference.
    """

    existing: set[str] = {
        child.get("id") or "" for child in element.findall(f"{_HH}memoPr")
    }
    existing.discard("")
    numeric_ids: list[int] = []
    for value in existing:
        try:
            numeric_ids.append(int(value))
        except ValueError:
            continue
    next_id = 1 if not numeric_ids else max(numeric_ids) + 1
    candidate = str(next_id)
    while candidate in existing:
        next_id += 1
        candidate = str(next_id)
    return candidate


def _memo_shape_matches(element: ET.Element, spec: "Mapping[str, str]") -> bool:
    if _element_local_name(element) != "memoPr":
        return False
    return all(element.get(attr) == spec[attr] for attr in _MEMO_SHAPE_ATTRS)


def _create_memo_shape_element(shape_id: str, spec: "Mapping[str, str]") -> ET.Element:
    attrs = {"id": shape_id, **{attr: spec[attr] for attr in _MEMO_SHAPE_ATTRS}}
    return ET.Element(f"{_HH}memoPr", attrs)


def _normalize_memo_shape_spec(
    *,
    width: int,
    line_width: "int | str",
    line_type: str,
    line_color: str,
    fill_color: str,
    active_color: str,
    memo_type: str,
) -> dict[str, str]:
    """Validate/normalize ``ensure_memo_shape(...)`` into the plain attribute
    dict ``hh:memoPr`` needs (Header XML schema.xml:1705-1753). Defaults
    mirror the modal real-corpus profile (hwpxlib_corpus, 6 files: width
    15591, lineWidth 1, lineType SOLID, memoType NOMAL — the schema's own
    spelling, not a typo here) rather than the schema (which requires
    lineType/lineColor/fillColor/activeColor with no defaults at all).
    """

    return {
        "width": str(int(width)),
        "lineWidth": str(line_width),
        "lineType": _normalize_enum_attr(line_type, LINE_TYPE2_VALUES, label="line_type"),
        "lineColor": _normalize_color(line_color) or "#000000",
        "fillColor": _normalize_color(fill_color) or "#CCFF99",
        "activeColor": _normalize_color(active_color) or "#FFFF99",
        "memoType": _normalize_enum_attr(memo_type, MEMO_TYPE_VALUES, label="memo_type"),
    }


def _ensure_memo_shape(
    element: ET.Element, spec: "Mapping[str, str]"
) -> "tuple[str, ET.Element | None]":
    """Find-or-prepare one ``hh:memoPr`` matching *spec* inside *element*
    (``hh:memoProperties``). Returns ``(id, None)`` if an existing shape
    already matches, else ``(new_id, new_unattached_element)`` — the caller
    (``HwpxOxmlHeader.ensure_memo_shape``) owns attaching it via
    :func:`_attach_new_child` plus ``itemCnt``/``mark_dirty`` bookkeeping,
    the same split :func:`_find_shading_border_fill_id` uses.
    """

    for memo_pr in element.findall(f"{_HH}memoPr"):
        if _memo_shape_matches(memo_pr, spec):
            existing_id = memo_pr.get("id")
            if existing_id:
                return existing_id, None
    new_id = _allocate_memo_shape_id(element)
    return new_id, _create_memo_shape_element(new_id, spec)


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


def _default_cell_inner_margin_attributes() -> dict[str, str]:
    """Hancom's new-table cell padding: 1.8 mm left/right, 0.5 mm top/bottom.

    Measured from real Hancom-authored gold documents
    (specs/056-authoring-fidelity-audit — the audit found our former 0
    padding makes text hug the borders, visibly unlike a Hancom table).
    """

    return {"left": "510", "right": "510", "top": "141", "bottom": "141"}


def _get_int_attr(element: ET.Element, name: str, default: int = 0) -> int:
    """Return *name* attribute of *element* as an integer."""

    value = element.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _optional_int_attr(element: ET.Element, name: str) -> int | None:
    """Return *name* as an int, or ``None`` if absent/unparseable.

    Unlike :func:`_get_int_attr`, this distinguishes "attribute omitted"
    (schema-legal for e.g. ``lineNumberShape``'s attributes, all optional
    with no declared default) from "present and zero".
    """

    value = element.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _get_bool_attr(element: ET.Element, name: str, default: bool = False) -> bool:
    """Return *name* attribute of *element* as a boolean.

    OWPML xs:boolean allows both "0"/"1" and "true"/"false" lexical forms,
    and this schema mixes them (``wonggojiFormat`` defaults "0",
    ``hideFirstHeader`` defaults "false") — both are accepted here.
    """

    value = element.get(name)
    if value is None:
        return default
    return value not in ("0", "false", "False", "FALSE")


def _bool_str(value: bool) -> str:
    """Serialize a boolean as the OWPML ``"true"``/``"false"`` literal."""

    return "true" if value else "false"


def _apply_optional_attrs(element: ET.Element, pairs: Iterable[tuple[str, str | None]]) -> bool:
    """Set each non-``None`` ``(name, value)`` pair on *element* if it differs.

    Shared "partial update" primitive: every ``set_*``/``ensure_*`` helper
    that only touches attributes a caller actually passed (leaving the rest
    of an existing element alone) can reuse this instead of repeating the
    same ``for``/``if`` loop. Returns whether anything actually changed.
    """

    changed = False
    for name, value in pairs:
        if value is not None and element.get(name) != value:
            element.set(name, value)
            changed = True
    return changed


def _apply_optional_bool_attrs(element: ET.Element, pairs: Iterable[tuple[str, bool | None]]) -> bool:
    """Boolean-valued sibling of :func:`_apply_optional_attrs`.

    Compares via :func:`_get_bool_attr` (accepts "0"/"1" and "true"/"false")
    rather than raw string equality, and serializes with :func:`_bool_str`.
    """

    changed = False
    for name, value in pairs:
        if value is not None and _get_bool_attr(element, name, False) != value:
            element.set(name, _bool_str(value))
            changed = True
    return changed


#: ``hh:font/@type``·``hh:substFont/@type`` 어휘(OWPML ``FontType``). 실코퍼스
#: 176파일 6741건 전수는 TTF/HFT 둘뿐이지만(REP 관측 0), 스키마가 REP를
#: 정의하므로 거부하지 않는다 — 편차 레지스트리 원칙(실문서가 이기되, 스키마가
#: 허용하는 값을 미리 막지는 않는다).
_FONT_TYPES = frozenset({"REP", "TTF", "HFT"})


def _zero_one_bool_str(value: bool) -> str:
    # 일부 OWPML 불리언 속성은 "true"/"false"(``_bool_str``)가 아니라 "0"/"1"을
    # 쓴다 — 실측 확인된 자리: hh:font/hh:substFont의 isEmbedded(6741건 전수
    # "0"/"1"만) 및 hh:tabPr의 autoTabLeft/autoTabRight(142건 전수 동일).
    return "1" if value else "0"


def _normalize_font_langs(lang: "str | Iterable[str] | None") -> tuple[str, ...]:
    """``ensure_font`` 의 *lang* 인자를 검증·정규화한다.

    생략(``None``)이면 실코퍼스 다수 관행대로 7개 lang 전부
    (:data:`~.canonical_defaults.FONTFACE_LANGS`)를 돌려준다.
    """

    from ..errors import HwpxValueError
    from .canonical_defaults import FONTFACE_LANGS

    if lang is None:
        return FONTFACE_LANGS
    candidates: tuple[object, ...] = (lang,) if isinstance(lang, str) else tuple(lang)
    normalized: list[str] = []
    for value in candidates:
        upper = str(value).strip().upper()
        if upper not in FONTFACE_LANGS:
            raise HwpxValueError(
                f"unsupported font lang {value!r}",
                code="style-font-lang-invalid",
                context={"requested": value, "available": list(FONTFACE_LANGS)},
                suggestion=f"lang 은 {', '.join(FONTFACE_LANGS)} 중 하나(또는 그 조합)여야 합니다.",
            )
        if upper not in normalized:
            normalized.append(upper)
    if not normalized:
        raise HwpxValueError(
            "lang must not be empty",
            code="style-font-lang-invalid",
            suggestion=f"lang 은 {', '.join(FONTFACE_LANGS)} 중 하나(또는 그 조합)여야 합니다.",
        )
    return tuple(normalized)


def _validate_font_type(value: str | None, *, param_name: str) -> str:
    normalized = str(value or "TTF").strip().upper()
    if normalized not in _FONT_TYPES:
        from ..errors import HwpxValueError

        raise HwpxValueError(
            f"unsupported {param_name} {value!r}",
            code="style-font-type-invalid",
            context={"requested": value, "available": sorted(_FONT_TYPES)},
            suggestion=f"{param_name} 은 {sorted(_FONT_TYPES)} 중 하나여야 합니다.",
        )
    return normalized


def _fontface_insert_index(fontfaces: ET.Element, lang: str) -> int:
    """정규 순서(:data:`FONTFACE_LANGS`)를 지키는 새 ``hh:fontface`` 삽입 위치."""

    from .canonical_defaults import FONTFACE_LANGS

    target_rank = FONTFACE_LANGS.index(lang)
    insert_at = 0
    for index, child in enumerate(list(fontfaces)):
        child_lang = child.get("lang")
        if child_lang in FONTFACE_LANGS and FONTFACE_LANGS.index(child_lang) <= target_rank:
            insert_at = index + 1
    return insert_at


def _find_font_id(fontface: ET.Element, face: str) -> str | None:
    for font in fontface.findall(f"{_HH}font"):
        if font.get("face") == face:
            font_id = font.get("id")
            if font_id:
                return font_id
    return None


def _allocate_font_id(fontface: ET.Element) -> str:
    existing: set[str] = {child.get("id") or "" for child in fontface.findall(f"{_HH}font")}
    existing.discard("")
    numeric_ids: list[int] = []
    for value in existing:
        try:
            numeric_ids.append(int(value))
        except ValueError:
            continue
    next_id = 0 if not numeric_ids else max(numeric_ids) + 1
    candidate = str(next_id)
    while candidate in existing:
        next_id += 1
        candidate = str(next_id)
    return candidate


def _resolve_font_substitute(
    subst_face: str | None, subst_type: str | None
) -> tuple[str | None, str | None]:
    """Validate ``ensure_font``'s *subst_face*/*subst_type* pair.

    ``subst_type`` alone is incomplete (schema requires ``substFont/@face``);
    ``subst_face`` alone is enough (``subst_type`` defaults to ``"TTF"``).
    """

    from ..errors import HwpxValueError

    if subst_face is None:
        if subst_type is not None:
            raise HwpxValueError(
                "subst_type requires subst_face",
                code="style-font-substitute-incomplete",
                suggestion="대체 글꼴을 지정하려면 subst_face 도 함께 주세요.",
            )
        return None, None

    normalized_face = subst_face.strip()
    if not normalized_face:
        raise HwpxValueError(
            "subst_face must not be empty when a substitute font is given",
            code="style-font-substitute-incomplete",
        )
    return normalized_face, _validate_font_type(subst_type, param_name="subst_type")


def _build_font_element(
    *,
    font_id: str,
    face: str,
    font_type: str,
    is_embedded: bool,
    binary_item_id_ref: str | None,
    subst_face: str | None,
    subst_type: str | None,
    subst_is_embedded: bool,
    subst_binary_item_id_ref: str | None,
) -> ET.Element:
    attrs = {
        "id": font_id,
        "face": face,
        "type": font_type,
        "isEmbedded": _zero_one_bool_str(is_embedded),
    }
    # 실코퍼스 관행: 비-임베드 폰트는 binaryItemIDRef 속성 자체가 없다(1682/1682)
    # — substFont 쪽과 달리 빈 문자열로도 안 남는다.
    if binary_item_id_ref:
        attrs["binaryItemIDRef"] = binary_item_id_ref
    element = ET.Element(f"{_HH}font", attrs)
    if subst_face is not None:
        # 스키마 시퀀스: substFont 는 typeInfo 보다 앞선다(font 자식 중 첫째).
        ET.SubElement(
            element,
            f"{_HH}substFont",
            {
                "face": subst_face,
                "type": subst_type or "TTF",
                "isEmbedded": _zero_one_bool_str(subst_is_embedded),
                # 실코퍼스 관행: substFont 는 binaryItemIDRef 를 항상 갖되 값이
                # 없으면 빈 문자열로 남긴다(284/284) — font 와 반대다.
                "binaryItemIDRef": subst_binary_item_id_ref or "",
            },
        )
    return element


#: ``hh:tabItem/@type`` 어휘(OWPML ``TabPosType``). 실코퍼스 246건 전수는 LEFT만
#: 관측했지만(다중-tabItem 문서 4건), 스키마가 4종을 선언하므로 나머지도 받는다.
_TAB_STOP_TYPES = frozenset({"LEFT", "RIGHT", "CENTER", "DECIMAL"})

#: ``hc:LineType2`` 도메인(border 계열과 다른, 3D/WAVE가 없는 12값) — 스키마상
#: ``hh:tabItem/@leader``와 ``hh:memoPr/@lineType`` 둘 다 이 타입을 쓴다.
#: ``hh:tabItem`` 실코퍼스는 NONE만, ``hh:memoPr`` 실코퍼스(6파일)는 SOLID만 관측했다.
LINE_TYPE2_VALUES = frozenset({
    "NONE", "SOLID", "DOT", "DASH", "DASH_DOT", "DASH_DOT_DOT", "LONG_DASH",
    "CIRCLE", "DOUBLE_SLIM", "SLIM_THICK", "THICK_SLIM", "SLIM_THICK_SLIM",
})
_TAB_LEADER_TYPES = LINE_TYPE2_VALUES

#: ``hh:memoPr/@memoType`` 어휘(Header XML schema.xml:1740-1752). 실코퍼스
#: 6파일 전량 ``NOMAL``("NORMAL"의 스키마 원본 오타, 그대로 보존) — 추적 상태
#: 3종(USER_INSERT/DELETE/UPDATE)은 미관측이나 스키마가 선언하므로 받는다.
MEMO_TYPE_VALUES = frozenset({"NOMAL", "USER_INSERT", "USER_DELETE", "USER_UPDATE"})

#: ``hp:AutoNumNewNumType/@numType`` 어휘(ParaList XML schema.xml:2746-2757) —
#: ``hp:autoNum``과 ``hp:newNum``이 공유하는 타입. 실코퍼스(hwpxlib_corpus,
#: newNum 7+파일)는 ``PAGE``만 관측했다.
NEW_NUM_KINDS = frozenset({
    "PAGE", "FOOTNOTE", "ENDNOTE", "PICTURE", "TABLE", "EQUATION", "TOTAL_PAGE",
})


def _normalize_tab_stops(
    tab_stops: "Iterable[Mapping[str, object]] | None",
) -> tuple[tuple[int, str, str], ...]:
    """Validate/normalize ``ensure_tab_definition``'s *tab_stops* into
    ``(pos, type, leader)`` triples, in call order.

    Order is meaningful: real multi-stop documents list ``hh:tabItem``
    position-ascending, and dedupe (:func:`_tab_definition_matches`) treats
    the sequence as ordered.
    """

    if tab_stops is None:
        return ()

    from ..errors import HwpxValueError

    normalized: list[tuple[int, str, str]] = []
    for index, spec in enumerate(tab_stops):
        if "pos" not in spec or spec["pos"] is None:
            raise HwpxValueError(
                f"tab_stops[{index}] is missing 'pos'",
                code="paragraph-tab-pos-invalid",
                context={"index": index},
                suggestion="각 tab stop은 'pos'(HWPUNIT, 0 이상)가 필요합니다.",
            )
        try:
            pos = int(spec["pos"])  # type: ignore[call-overload]
        except (TypeError, ValueError):
            raise HwpxValueError(
                f"tab_stops[{index}]['pos'] must be an integer",
                code="paragraph-tab-pos-invalid",
                context={"index": index, "requested": spec["pos"]},
            ) from None
        if pos < 0:
            raise HwpxValueError(
                f"tab_stops[{index}]['pos'] must not be negative",
                code="paragraph-tab-pos-invalid",
                context={"index": index, "requested": pos},
            )
        tab_type = str(spec.get("type") or "LEFT").strip().upper()
        if tab_type not in _TAB_STOP_TYPES:
            raise HwpxValueError(
                f"unsupported tab stop type {spec.get('type')!r}",
                code="paragraph-tab-type-invalid",
                context={
                    "index": index,
                    "requested": spec.get("type"),
                    "available": sorted(_TAB_STOP_TYPES),
                },
                suggestion=f"type 은 {sorted(_TAB_STOP_TYPES)} 중 하나여야 합니다.",
            )
        leader = str(spec.get("leader") or "NONE").strip().upper()
        if leader not in _TAB_LEADER_TYPES:
            raise HwpxValueError(
                f"unsupported tab leader {spec.get('leader')!r}",
                code="paragraph-tab-leader-invalid",
                context={
                    "index": index,
                    "requested": spec.get("leader"),
                    "available": sorted(_TAB_LEADER_TYPES),
                },
                suggestion=f"leader 는 {sorted(_TAB_LEADER_TYPES)} 중 하나여야 합니다.",
            )
        normalized.append((pos, tab_type, leader))
    return tuple(normalized)


def _tab_stop_tuple_from(container: ET.Element) -> tuple[tuple[int, str, str], ...]:
    return tuple(
        (
            int(child.get("pos") or 0),
            child.get("type") or "LEFT",
            child.get("leader") or "NONE",
        )
        for child in container.findall(f"{_HH}tabItem")
    )


def _tab_definition_matches(
    element: ET.Element,
    *,
    auto_tab_left: bool,
    auto_tab_right: bool,
    tab_stops: tuple[tuple[int, str, str], ...],
) -> bool:
    if _get_bool_attr(element, "autoTabLeft", False) != auto_tab_left:
        return False
    if _get_bool_attr(element, "autoTabRight", False) != auto_tab_right:
        return False
    existing = _tab_stop_tuple_from(element)
    if not existing:
        # 실코퍼스 449/449 hp:switch로 감싼 hh:tabPr은 직속 hh:tabItem이
        # 없다(DEV-022) -- 그럴 때만 hp:default 분기를 본다(hp:case가
        # 아니다: hp:case의 pos는 hp:default의 정확히 절반, 실측 확인 —
        # header.py의 parse_tab_definition과 같은 선택). 이 폴백이 없으면
        # 이미 존재하는 switch-감싼 tabPr과 동등한 사양이 "불일치"로 오판돼
        # ensure_tab_definition이 중복 tabPr을 만든다.
        switch = next(
            (child for child in element if _element_local_name(child) == "switch"), None
        )
        if switch is not None:
            default_branch = next(
                (child for child in switch if _element_local_name(child) == "default"), None
            )
            if default_branch is not None:
                existing = _tab_stop_tuple_from(default_branch)
    return existing == tab_stops


def _allocate_tab_id(element: ET.Element) -> str:
    existing: set[str] = {child.get("id") or "" for child in element.findall(f"{_HH}tabPr")}
    existing.discard("")
    numeric_ids: list[int] = []
    for value in existing:
        try:
            numeric_ids.append(int(value))
        except ValueError:
            continue
    next_id = 0 if not numeric_ids else max(numeric_ids) + 1
    candidate = str(next_id)
    while candidate in existing:
        next_id += 1
        candidate = str(next_id)
    return candidate


def _build_tab_definition_element(
    tab_id: str,
    *,
    auto_tab_left: bool,
    auto_tab_right: bool,
    tab_stops: tuple[tuple[int, str, str], ...],
) -> ET.Element:
    element = ET.Element(
        f"{_HH}tabPr",
        {
            "id": tab_id,
            # 실코퍼스 142건 전수: autoTabLeft/autoTabRight는 "0"/"1"만 쓴다.
            "autoTabLeft": _zero_one_bool_str(auto_tab_left),
            "autoTabRight": _zero_one_bool_str(auto_tab_right),
        },
    )
    for pos, tab_type, leader in tab_stops:
        ET.SubElement(
            element,
            f"{_HH}tabItem",
            {"pos": str(pos), "type": tab_type, "leader": leader},
        )
    return element


def _elements_structurally_equal(
    a: ET.Element, b: ET.Element, *, ignore_attrs: frozenset[str] = frozenset()
) -> bool:
    """Recursive tag/attrib/children equality, ignoring *ignore_attrs* at
    every level (typically ``{"id"}`` -- an allocated identity, not a
    structural property). Element text/tail are not compared -- every
    caller of this helper (``ensure_paragraph_format``'s dedupe) deals
    with attribute-only leaf families (paraPr/align/heading/margin/
    lineSpacing/breakSetting/border), never mixed text content, matching
    ``_tab_definition_matches``'s own attribute-based comparison one level
    up (a general recursive form of the same idea, needed here because
    paraPr's shape is too varied for a hand-enumerated field list).
    """

    a_tag = a.tag if isinstance(a.tag, str) else None
    b_tag = b.tag if isinstance(b.tag, str) else None
    if a_tag != b_tag:
        return False
    a_attrib = {k: v for k, v in a.attrib.items() if k not in ignore_attrs}
    b_attrib = {k: v for k, v in b.attrib.items() if k not in ignore_attrs}
    if a_attrib != b_attrib:
        return False
    a_children = list(a)
    b_children = list(b)
    if len(a_children) != len(b_children):
        return False
    return all(
        _elements_structurally_equal(ac, bc, ignore_attrs=ignore_attrs)
        for ac, bc in zip(a_children, b_children)
    )


def _find_matching_para_pr(para_properties: ET.Element, built: ET.Element) -> str | None:
    """Return an existing ``hh:paraPr`` id whose content matches *built*
    (ignoring ``id``), or ``None`` if none does. Split out of
    ``ensure_paragraph_format`` (kept as a separate function rather than
    inlined) purely to keep that function's own cyclomatic complexity
    under the C901 ratchet -- the loop itself has nothing paraPr-specific
    beyond calling :func:`_elements_structurally_equal`.
    """

    for candidate in para_properties.findall(f"{_HH}paraPr"):
        if _elements_structurally_equal(candidate, built, ignore_attrs=frozenset({"id"})):
            existing_id = candidate.get("id")
            if existing_id:
                return existing_id
    return None


def _ensure_tab_definition_element(
    container: ET.Element,
    *,
    tab_stops: "Iterable[Mapping[str, object]] | None",
    auto_tab_left: bool,
    auto_tab_right: bool,
) -> tuple[str, bool]:
    """Find-or-create the ``hh:tabPr`` matching this spec inside *container*
    (the ``hh:tabProperties`` element). Returns ``(tab_id, created)`` so the
    caller only marks the header dirty when something actually changed.
    """

    normalized_stops = _normalize_tab_stops(tab_stops)
    for tab_pr in container.findall(f"{_HH}tabPr"):
        if _tab_definition_matches(
            tab_pr,
            auto_tab_left=auto_tab_left,
            auto_tab_right=auto_tab_right,
            tab_stops=normalized_stops,
        ):
            tab_id = tab_pr.get("id")
            if tab_id:
                return tab_id, False

    new_id = _allocate_tab_id(container)
    new_tab_pr = _build_tab_definition_element(
        new_id,
        auto_tab_left=auto_tab_left,
        auto_tab_right=auto_tab_right,
        tab_stops=normalized_stops,
    )
    if isinstance(container, LET._Element):
        new_tab_pr = LET.fromstring(ET.tostring(new_tab_pr, encoding="utf-8"))
    container.append(new_tab_pr)
    container.set("itemCnt", str(len(container.findall(f"{_HH}tabPr"))))
    return new_id, True


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
