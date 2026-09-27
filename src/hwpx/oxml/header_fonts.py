# SPDX-License-Identifier: Apache-2.0
"""Font table and border-fill reads over ``Contents/header.xml``, plus the
one font-table rewrite they make safe: replacing a font face everywhere.

``doc.styles`` could declare fonts (``ensure_font``) and border fills
(``ensure_border_fill``) but not read them back as values: ``border_fill()``
returns a ``GenericElement`` and there was no font-table read at all. A
caller converting HWPX to another format (a typesetting engine's DOCX
export, for one) had to walk the raw XML to learn which face a
``hh:charPr`` uses or what a cell border looks like. This module answers
those questions from the live in-memory header, so the answers follow
``ensure_font``/``ensure_border_fill`` edits without a save.

Font ids are per language: every ``hh:fontface`` block numbers its own
``hh:font`` list, and ``hh:fontRef/@hangul`` indexes the HANGUL block,
``@latin`` the LATIN block, and so on. ``replace_font`` therefore works
block by block and renumbers each block it touches, remapping every
``hh:fontRef`` so that no other reference changes the face it names.

Why this lives outside ``header_part.py``: ``HwpxOxmlHeader``'s owner file
sits at 1598/1600 lines. Same free-function pattern as ``header_compat.py``:
the functions take the header object and use its public surface
(``.element``, ``.mark_dirty()``, ``.document``).
"""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Iterable

from ..errors import HwpxValueError
from ..objects.results import BorderFillInfo, BorderLine, FontReplaceReport
from ._document_primitives import (
    _FONT_FACE_LANG_TO_REF,
    _HC,
    _HH,
    _element_local_name,
    _normalize_font_langs,
    _validate_font_type,
)
from .header import Font, parse_font

if TYPE_CHECKING:
    from .header_part import HwpxOxmlHeader

__all__ = ["border_fill_info", "font_face", "fonts", "replace_font"]

#: ``hh:borderFill`` side children, in ``BorderFillInfo`` field order.
_BORDER_SIDES = ("leftBorder", "rightBorder", "topBorder", "bottomBorder", "diagonal")


def _single_lang(lang: str) -> str:
    """Validate one ``hh:fontface/@lang`` value (``style-font-lang-invalid``)."""

    return _normalize_font_langs(lang)[0]


def _fontfaces(header: "HwpxOxmlHeader | None") -> list[ET.Element]:
    if header is None:
        return []
    return list(header.element.iter(f"{_HH}fontface"))


def _fontface_block(header: "HwpxOxmlHeader | None", lang: str) -> ET.Element | None:
    for fontface in _fontfaces(header):
        if fontface.get("lang") == lang:
            return fontface
    return None


def _find_by_id(elements: Iterable[ET.Element], id_ref: int | str | None) -> ET.Element | None:
    """The element whose ``id`` is *id_ref*: exact text first, then the same
    integer (``"01"`` finds ``id="1"``) — ``char_property()``'s lookup rule."""

    if id_ref is None:
        return None
    key = str(id_ref).strip()
    if not key:
        return None
    candidates = list(elements)
    for element in candidates:
        if element.get("id") == key:
            return element
    try:
        wanted = int(key)
    except ValueError:
        return None
    for element in candidates:
        try:
            if int(element.get("id") or "") == wanted:
                return element
        except ValueError:
            continue
    return None


def fonts(header: "HwpxOxmlHeader | None", lang: str = "HANGUL") -> dict[str, Font]:
    """The ``hh:font`` entries of the *lang* block, keyed by raw ``id``."""

    from .header_part import HwpxOxmlHeader

    fontface = _fontface_block(header, _single_lang(lang))
    if fontface is None:
        return {}
    result: dict[str, Font] = {}
    for font in fontface.findall(f"{_HH}font"):
        font_id = font.get("id")
        if font_id is not None and font_id not in result:
            result[font_id] = parse_font(HwpxOxmlHeader._convert_to_lxml(font))
    return result


def font_face(
    header: "HwpxOxmlHeader | None",
    char_pr_id_ref: int | str | None,
    lang: str = "HANGUL",
) -> str | None:
    """The face a ``hh:charPr``'s ``hh:fontRef`` names in the *lang* block."""

    normalized = _single_lang(lang)
    if header is None:
        return None
    char_pr = _find_by_id(header.element.iter(f"{_HH}charPr"), char_pr_id_ref)
    if char_pr is None:
        return None
    font_ref = char_pr.find(f"{_HH}fontRef")
    if font_ref is None:
        return None
    font_id = font_ref.get(_FONT_FACE_LANG_TO_REF[normalized])
    fontface = _fontface_block(header, normalized)
    if font_id is None or fontface is None:
        return None
    for font in fontface.findall(f"{_HH}font"):
        if font.get("id") == font_id:
            return font.get("face")
    return None


def _border_line(border_fill: ET.Element, side: str, fill_id: str) -> BorderLine:
    element = None
    for child in border_fill:
        if _element_local_name(child) == side:
            element = child
            break
    if element is None:
        return BorderLine("NONE", 0.0, "#000000")
    width = element.get("width", "0 mm")
    try:
        width_mm = float(width.split()[0])
    except (IndexError, ValueError):
        raise HwpxValueError(
            f"borderFill {fill_id} {side} width {width!r} is not '<number> mm'",
            code="style-border-fill-width-invalid",
            context={"id": fill_id, "side": side, "width": width},
            suggestion="Border widths are stored as '<number> mm', e.g. '0.12 mm'.",
        ) from None
    return BorderLine(element.get("type", "NONE"), width_mm, element.get("color", "#000000"))


def border_fill_info(
    header: "HwpxOxmlHeader | None", border_fill_id_ref: int | str | None
) -> BorderFillInfo | None:
    """A typed read of one ``hh:borderFill``; ``None`` for an unknown id."""

    if header is None:
        return None
    border_fill = _find_by_id(header.element.iter(f"{_HH}borderFill"), border_fill_id_ref)
    if border_fill is None:
        return None
    fill_id = border_fill.get("id", "")
    left, right, top, bottom, diagonal = (
        _border_line(border_fill, side, fill_id) for side in _BORDER_SIDES
    )
    fill: str | None = None
    brush = next(border_fill.iter(f"{_HC}winBrush"), None)
    if brush is not None:
        face_color = brush.get("faceColor")
        if face_color is not None and face_color.lower() != "none":
            fill = face_color
    return BorderFillInfo(
        id=fill_id, left=left, right=right, top=top, bottom=bottom, diagonal=diagonal, fill=fill
    )


def replace_font(
    header: "HwpxOxmlHeader | None",
    src_face: str,
    dst_face: str,
    *,
    langs: Iterable[str] | str | None = None,
    font_type: str | None = None,
) -> FontReplaceReport:
    """Replace *src_face* with *dst_face* in every selected fontface block.

    Per block, in document order: skip it when no ``hh:font`` has
    *src_face*; take the id of the ``hh:font`` with *dst_face*, or append
    a new *dst_face* font with id ``len(fonts)``; point every ``hh:fontRef`` that named *src_face* at *dst_face*; remove
    the *src_face* font, renumber the rest 0..N-1 by position, set
    ``fontCnt`` to N and remap every ``hh:fontRef`` through the old → new
    ids (values that name no font are left as they are).

    On a well-formed block (ids 0..N-1, every reference naming a font) the
    result is byte-identical to doing those steps literally. Two malformed
    inputs are handled deliberately: the appended font's placeholder id is
    kept out of the old -> new map, so in a block whose ids are not 0..N-1 a
    placeholder equal to an existing id cannot pull that font's references
    onto *dst_face*; and a reference that named no font (for example one
    equal to the placeholder) stays dangling instead of starting to name
    *dst_face*.

    The appended font is a copy of the first ``hh:font`` that already
    declares *dst_face* in any fontface block (document order, looked up
    before anything changes), so its ``type``, ``isEmbedded`` and child
    elements match the face's existing declaration. When no block declares
    *dst_face* it is ``<hh:font id=… face=dst type="TTF" isEmbedded="0"/>``.
    *font_type* (``REP``/``TTF``/``HFT``), when given, sets the ``type`` of
    every font this call appends; fonts that already exist are not changed.
    """

    src = (src_face or "").strip()
    dst = (dst_face or "").strip()
    if not src or not dst:
        raise HwpxValueError(
            "src_face and dst_face must not be empty",
            code="style-font-face-empty",
            context={"src_face": src_face, "dst_face": dst_face},
        )
    if src == dst:
        raise HwpxValueError(
            f"src_face and dst_face are the same face {src!r}",
            code="style-font-replace-same-face",
            context={"face": src},
            suggestion="Pass two different faces; replacing a face with itself changes nothing.",
        )
    wanted = set(_normalize_font_langs(langs))
    normalized_type = (
        _validate_font_type(font_type, param_name="font_type") if font_type is not None else None
    )
    # An existing declaration of dst in any block is the template for the fonts
    # this call appends, so one face is not declared as two font types.
    template = next(
        (
            font
            for fontface in _fontfaces(header)
            for font in fontface.findall(f"{_HH}font")
            if font.get("face") == dst
        ),
        None,
    )

    changed: list[str] = []
    declared: list[str] = []
    repointed = 0
    font_refs = (
        [ref for ref in (c.find(f"{_HH}fontRef") for c in header.element.iter(f"{_HH}charPr"))
         if ref is not None]
        if header is not None
        else []
    )
    for fontface in _fontfaces(header):
        lang = fontface.get("lang", "")
        attr = _FONT_FACE_LANG_TO_REF.get(lang)
        if attr is None or lang not in wanted:
            continue
        fonts_in_block = fontface.findall(f"{_HH}font")
        # Hancom-saved blocks often list one face more than once; every copy goes.
        src_fonts = [f for f in fonts_in_block if f.get("face") == src]
        if not src_fonts:
            continue
        src_ids = {f.get("id") for f in src_fonts}
        remaining = [f for f in fonts_in_block if all(f is not s for s in src_fonts)]
        # old id -> new id of the fonts that were already declared. The new
        # dst font stays out of it: its id is only a placeholder, and in a
        # block whose ids are not 0..N-1 it can equal an existing id.
        new_ids = {f.get("id"): str(index) for index, f in enumerate(remaining)}
        dst_font = next((f for f in fonts_in_block if f.get("face") == dst), None)
        if dst_font is None:
            if template is not None:
                dst_font = copy.deepcopy(template)
                dst_font.tail = None
                dst_font.set("id", str(len(fonts_in_block)))
            else:
                dst_font = fontface.makeelement(
                    f"{_HH}font",
                    {"id": str(len(fonts_in_block)), "face": dst, "type": "TTF", "isEmbedded": "0"},
                )
            if normalized_type is not None:
                dst_font.set("type", normalized_type)
            fontface.append(dst_font)
            remaining.append(dst_font)
            declared.append(lang)
        # A reference to src moves straight to dst's final position.
        dst_new_id = str(remaining.index(dst_font))
        for font_ref in font_refs:
            value = font_ref.get(attr)
            if value is None:
                continue
            if value in src_ids:
                font_ref.set(attr, dst_new_id)
                repointed += 1
            elif value in new_ids:
                font_ref.set(attr, new_ids[value])
        for src_font in src_fonts:
            fontface.remove(src_font)
        for index, font in enumerate(remaining):
            font.set("id", str(index))
        fontface.set("fontCnt", str(len(remaining)))
        changed.append(lang)

    if changed and header is not None:
        header.mark_dirty()
        document = header.document
        if document is not None:
            document.invalidate_char_property_cache()
    return FontReplaceReport(
        src_face=src,
        dst_face=dst,
        langs=tuple(changed),
        repointed=repointed,
        declared=tuple(declared),
    )
