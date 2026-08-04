# SPDX-License-Identifier: Apache-2.0
"""Inline-object, shape, picture, and drawing OXML wrappers."""

from __future__ import annotations

from typing import TYPE_CHECKING
import warnings
import xml.etree.ElementTree as ET

from ._document_primitives import (
    _DEFAULT_PARAGRAPH_ATTRS,
    _HC,
    _HP,
    _append_child,
    _append_text_with_tabs,
    _default_sublist_attributes,
    _element_local_name,
    _object_id,
    _reposition_child_after_any,
    _reposition_child_before_any,
    _paragraph_id,
)

if TYPE_CHECKING:
    from .paragraph import HwpxOxmlParagraph
    from .section import HwpxOxmlSection


class HwpxOxmlInlineObject:
    """Wrapper providing attribute helpers for inline objects."""

    def __init__(self, element: ET.Element, paragraph: "HwpxOxmlParagraph"):
        self.element = element
        self.paragraph = paragraph

    @property
    def tag(self) -> str:
        """Return the fully qualified XML tag for the inline object."""

        return self.element.tag

    @property
    def attributes(self) -> dict[str, str]:
        """Return a copy of the element attributes."""

        return dict(self.element.attrib)

    def get_attribute(self, name: str) -> str | None:
        """Return the value of attribute *name* if present."""

        return self.element.get(name)

    def set_attribute(self, name: str, value: str | int | None) -> None:
        """Update or remove attribute *name* and mark the paragraph dirty."""

        if value is None:
            if name in self.element.attrib:
                del self.element.attrib[name]
                self.paragraph.section.mark_dirty()
            return

        new_value = str(value)
        if self.element.get(name) != new_value:
            self.element.set(name, new_value)
            self.paragraph.section.mark_dirty()

    # --- caption (hp:caption — table/picture/OLE/equation may carry one) ---

    @property
    def caption(self) -> "Caption | None":
        """This object's ``hp:caption``, or ``None`` if it doesn't have one."""

        return _read_caption(self.element, self.paragraph.section)

    def set_caption(
        self,
        text: str,
        *,
        side: str = "TOP",
        full_sz: bool = False,
        width: int | None = None,
        gap: int = 850,
        char_pr_id_ref: str | int | None = None,
    ) -> "Caption":
        """Create (or replace the text of) this object's ``hp:caption``.

        *side*/*full_sz*/*gap* default to the real-corpus majority
        convention (15-sample: side=TOP 14/15, fullSz=false 15/15,
        gap=850 11/15) — the schema's own default (``side="LEFT"``) is
        essentially unobserved in practice.
        """

        return _write_caption(
            self.element, text, section=self.paragraph.section,
            side=side, full_sz=full_sz, width=width, gap=gap,
            char_pr_id_ref=char_pr_id_ref,
        )

    def remove_caption(self) -> bool:
        """Remove this object's ``hp:caption`` if present. Returns whether one was removed."""

        return _remove_caption(self.element, self.paragraph.section)


# ------------------------------------------------------------------
# Drawing shape helpers
# ------------------------------------------------------------------

_IDENTITY_MATRIX = {
    "e1": "1", "e2": "0", "e3": "0",
    "e4": "0", "e5": "1", "e6": "0",
}

# Geometry children carrying a single ``x``/``y`` coordinate, keyed by local
# name because the namespace differs per shape type in real Hancom output:
# ``hp:line`` writes ``hc:startPt`` while ``hp:connectLine`` writes
# ``hp:startPt`` (both observed in the corpus fixtures).
_SHAPE_POINT_LOCAL_NAMES = frozenset({
    "pt0", "pt1", "pt2", "pt3",  # rect corners
    "pt",                        # polygon vertices
    "startPt", "endPt",          # line / connectLine endpoints
    "center", "ax1", "ax2",      # ellipse / arc axes
    "start1", "end1", "start2", "end2",  # ellipse / arc sweep
})

# ``<hp:seg>`` (curve) carries two coordinate pairs instead of one.
_SHAPE_SEGMENT_ATTR_PAIRS: tuple[tuple[str, str], ...] = (("x1", "y1"), ("x2", "y2"))

_SHAPE_POINT_ATTR_PAIRS: tuple[tuple[str, str], ...] = (("x", "y"),)

# Children every drawing shape needs before Hancom will open the document.
_REQUIRED_SHAPE_CHILD_NAMES = ("offset", "orgSz", "curSz", "sz", "pos")

_DEFAULT_LINE_SHAPE_ATTRS: dict[str, str] = {
    "color": "#000000",
    "width": "283",
    "style": "SOLID",
    "endCap": "FLAT",
    "headStyle": "NORMAL",
    "tailStyle": "NORMAL",
    "headfill": "1",
    "tailfill": "1",
    "headSz": "SMALL_SMALL",
    "tailSz": "SMALL_SMALL",
    "outlineStyle": "NORMAL",
    "alpha": "0",
}


def _build_shape_common_children(
    parent: ET.Element,
    width: int,
    height: int,
    *,
    treat_as_char: bool = True,
    inst_id: str | None = None,
) -> None:
    """Append the common AbstractShapeComponent + AbstractShapeObject children.

    These are shared by LINE, RECT, ELLIPSE, and other drawing objects.
    The child order follows the **real HWPX output** produced by Hancom Word
    rather than the strict XSD inheritance sequence:

    AbstractShapeComponentType children (first):
        offset, orgSz, curSz, flip, rotationInfo, renderingInfo

    (Callers insert AbstractDrawingObjectType + type-specific children here.)

    AbstractShapeObjectType children (last, via ``_build_shape_base_children``):
        sz, pos, outMargin
    """
    w = str(width)
    h = str(height)
    the_id = inst_id or _object_id()

    parent.set("id", the_id)
    parent.set("zOrder", "0")
    parent.set("numberingType", "NONE")
    parent.set("lock", "0")
    parent.set("dropcapstyle", "None")
    parent.set("href", "")
    parent.set("groupLevel", "0")
    parent.set("instid", the_id)

    # --- AbstractShapeComponentType children (come first in real files) ---
    _append_child(parent, f"{_HP}offset", {"x": "0", "y": "0"})
    _append_child(parent, f"{_HP}orgSz", {"width": w, "height": h})
    _append_child(parent, f"{_HP}curSz", {"width": w, "height": h})
    _append_child(parent, f"{_HP}flip", {
        "horizontal": "0", "vertical": "0",
    })
    cx = str(width // 2)
    cy = str(height // 2)
    _append_child(parent, f"{_HP}rotationInfo", {
        "angle": "0", "centerX": cx, "centerY": cy, "rotateimage": "1",
    })

    ri = _append_child(parent, f"{_HP}renderingInfo", {})
    _append_child(ri, f"{_HC}transMatrix", dict(_IDENTITY_MATRIX))
    _append_child(ri, f"{_HC}scaMatrix", dict(_IDENTITY_MATRIX))
    _append_child(ri, f"{_HC}rotMatrix", dict(_IDENTITY_MATRIX))

    # Store treat_as_char for _build_shape_base_children
    parent.set("_treatAsChar", "1" if treat_as_char else "0")


def _build_shape_base_children(
    parent: ET.Element,
    width: int,
    height: int,
) -> None:
    """Append AbstractShapeObjectType children (sz, pos, outMargin).

    These come **last** in real HWPX output, after type-specific children.
    """
    w = str(width)
    h = str(height)
    treat_as_char = parent.get("_treatAsChar", "1") == "1"
    # Remove the temporary marker attribute
    if "_treatAsChar" in parent.attrib:
        del parent.attrib["_treatAsChar"]

    _append_child(parent, f"{_HP}sz", {
        "width": w, "height": h,
        "widthRelTo": "ABSOLUTE", "heightRelTo": "ABSOLUTE",
        "protect": "0",
    })
    pos_attrs: dict[str, str] = {
        "treatAsChar": "1" if treat_as_char else "0",
        "affectLSpacing": "0",
    }
    if not treat_as_char:
        pos_attrs.update({
            "flowWithText": "0", "allowOverlap": "1",
            "holdAnchorAndSO": "0",
            "vertRelTo": "PARA", "vertAlign": "TOP",
            "horzRelTo": "COLUMN", "horzAlign": "LEFT",
            "vertOffset": "0", "horzOffset": "0",
        })
    else:
        pos_attrs.update({
            "flowWithText": "1", "allowOverlap": "0",
            "holdAnchorAndSO": "0",
            "vertRelTo": "PARA", "horzRelTo": "COLUMN",
            "vertAlign": "TOP", "horzAlign": "LEFT",
            "vertOffset": "0", "horzOffset": "0",
        })
    _append_child(parent, f"{_HP}pos", pos_attrs)
    _append_child(parent, f"{_HP}outMargin", {
        "left": "0", "right": "0", "top": "0", "bottom": "0",
    })


def _build_drawing_object_children(
    parent: ET.Element,
    *,
    line_color: str = "#000000",
    line_width: str = "283",
    line_style: str = "SOLID",
    fill_color: str | None = None,
) -> None:
    """Append AbstractDrawingObjectType children: lineShape, fillBrush, shadow."""
    ls_attrs = dict(_DEFAULT_LINE_SHAPE_ATTRS)
    ls_attrs["color"] = line_color
    ls_attrs["width"] = line_width
    ls_attrs["style"] = line_style
    _append_child(parent, f"{_HP}lineShape", ls_attrs)

    if fill_color is not None:
        # Hancom reads the fill from the core namespace; an ``hp:fillBrush`` is
        # accepted by the parser but silently rendered unfilled.
        fb = _append_child(parent, f"{_HC}fillBrush", {})
        _append_child(fb, f"{_HC}winBrush", {
            "faceColor": fill_color, "hatchColor": "#FFFFFF",
        })

    _append_child(parent, f"{_HP}shadow", {
        "type": "NONE", "color": "#B2B2B2",
        "offsetX": "0", "offsetY": "0", "alpha": "0",
    })


def _create_line_element(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    *,
    line_color: str = "#000000",
    line_width: str = "283",
    treat_as_char: bool = True,
) -> ET.Element:
    """Build a complete ``<hp:line>`` element matching real HWPX output."""

    # Hancom stores the *bounding box* of the two endpoints, not the segment
    # length: the corpus SimpleLine has endPt (22478, 8447) with the matching
    # orgSz 22478x8447.  A diagonal recorded at its hypotenuse (and height 0)
    # contradicts its own endPt.
    w = abs(end_x - start_x)
    h = abs(end_y - start_y)

    el = ET.Element(f"{_HP}line", {"isReverseHV": "0"})
    # 1) AbstractShapeComponentType children (offset, orgSz, … renderingInfo)
    _build_shape_common_children(el, w, h, treat_as_char=treat_as_char)
    # 2) AbstractDrawingObjectType children (lineShape, shadow)
    _build_drawing_object_children(
        el, line_color=line_color, line_width=line_width,
    )
    # 3) LineType-specific children
    _append_child(el, f"{_HC}startPt", {"x": str(start_x), "y": str(start_y)})
    _append_child(el, f"{_HC}endPt", {"x": str(end_x), "y": str(end_y)})
    # 4) AbstractShapeObjectType children last (sz, pos, outMargin)
    _build_shape_base_children(el, w, h)
    return el


def _create_rectangle_element(
    width: int,
    height: int,
    *,
    ratio: int = 0,
    line_color: str = "#000000",
    line_width: str = "283",
    fill_color: str | None = None,
    treat_as_char: bool = True,
) -> ET.Element:
    """Build a complete ``<hp:rect>`` element matching real HWPX output."""
    el = ET.Element(f"{_HP}rect", {"ratio": str(ratio)})
    _build_shape_common_children(el, width, height, treat_as_char=treat_as_char)
    _build_drawing_object_children(
        el, line_color=line_color, line_width=line_width,
        fill_color=fill_color,
    )
    _append_child(el, f"{_HC}pt0", {"x": "0", "y": "0"})
    _append_child(el, f"{_HC}pt1", {"x": str(width), "y": "0"})
    _append_child(el, f"{_HC}pt2", {"x": str(width), "y": str(height)})
    _append_child(el, f"{_HC}pt3", {"x": "0", "y": str(height)})
    _build_shape_base_children(el, width, height)
    return el


def _create_ellipse_element(
    width: int,
    height: int,
    *,
    line_color: str = "#000000",
    line_width: str = "283",
    fill_color: str | None = None,
    treat_as_char: bool = True,
) -> ET.Element:
    """Build a complete ``<hp:ellipse>`` element matching real HWPX output."""
    el = ET.Element(f"{_HP}ellipse", {
        "intervalDirty": "0",
        "hasArcPr": "0",
        "arcType": "NORMAL",
    })
    _build_shape_common_children(el, width, height, treat_as_char=treat_as_char)
    _build_drawing_object_children(
        el, line_color=line_color, line_width=line_width,
        fill_color=fill_color,
    )
    cx = str(width // 2)
    cy = str(height // 2)
    _append_child(el, f"{_HC}center", {"x": cx, "y": cy})
    _append_child(el, f"{_HC}ax1", {"x": str(width), "y": cy})
    _append_child(el, f"{_HC}ax2", {"x": cx, "y": str(height)})
    _append_child(el, f"{_HC}start1", {"x": str(width), "y": cy})
    _append_child(el, f"{_HC}end1", {"x": str(width), "y": cy})
    _append_child(el, f"{_HC}start2", {"x": str(width), "y": cy})
    _append_child(el, f"{_HC}end2", {"x": str(width), "y": cy})
    _build_shape_base_children(el, width, height)
    return el


def _create_picture_element(
    binary_item_id_ref: str,
    width: int,
    height: int,
    *,
    align: str | None = None,
    treat_as_char: bool = True,
    pos_overrides: dict[str, str | int] | None = None,
    text_wrap: str | None = None,
) -> ET.Element:
    """Build a ``<hp:pic>`` element using the corpus-observed picture shape."""

    el = ET.Element(f"{_HP}pic", {
        "textWrap": text_wrap or "SQUARE",
        "textFlow": "BOTH_SIDES",
        "reverse": "0",
    })
    _build_shape_common_children(el, width, height, treat_as_char=treat_as_char)
    el.set("numberingType", "PICTURE")

    rect = _append_child(el, f"{_HP}imgRect", {})
    _append_child(rect, f"{_HC}pt0", {"x": "0", "y": "0"})
    _append_child(rect, f"{_HC}pt1", {"x": str(width), "y": "0"})
    _append_child(rect, f"{_HC}pt2", {"x": str(width), "y": str(height)})
    _append_child(rect, f"{_HC}pt3", {"x": "0", "y": str(height)})
    _append_child(el, f"{_HP}imgClip", {
        "left": "0",
        "right": str(width),
        "top": "0",
        "bottom": str(height),
    })
    _append_child(el, f"{_HP}inMargin", {
        "left": "0",
        "right": "0",
        "top": "0",
        "bottom": "0",
    })
    _append_child(el, f"{_HP}imgDim", {
        "dimwidth": str(width),
        "dimheight": str(height),
    })
    _append_child(el, f"{_HC}img", {
        "binaryItemIDRef": binary_item_id_ref,
        "bright": "0",
        "contrast": "0",
        "effect": "REAL_PIC",
        "alpha": "0",
    })
    _append_child(el, f"{_HP}effects", {})
    _build_shape_base_children(el, width, height)

    if align:
        pos = el.find(f"{_HP}pos")
        if pos is not None:
            pos.set("horzAlign", align.upper())
    if pos_overrides:
        pos = el.find(f"{_HP}pos")
        if pos is not None:
            # Floating placement: relTo / align / offset onto the <hp:pos> built by
            # _build_shape_base_children (its treat_as_char=False branch).
            for key, value in pos_overrides.items():
                if value is None:
                    continue
                if key in ("horzOffset", "vertOffset"):
                    # schema: xs:nonNegativeInteger — coerce/clamp so a stray negative
                    # or fractional offset can never produce an invalid HWPX.
                    value = max(0, round(float(value)))
                pos.set(key, str(value))
    _append_child(el, f"{_HP}shapeComment", {})
    return el


def _scale_coordinates(
    element: ET.Element,
    attr_pairs: tuple[tuple[str, str], ...],
    x_ratio: float,
    y_ratio: float,
) -> None:
    """Multiply the named coordinate attributes in place."""

    for x_name, y_name in attr_pairs:
        for name, ratio in ((x_name, x_ratio), (y_name, y_ratio)):
            raw = element.get(name)
            if raw is None:
                continue
            try:
                value = int(raw)
            except ValueError:
                continue
            element.set(name, str(round(value * ratio)))


def _missing_shape_children(element: ET.Element) -> list[str]:
    """Return the OWPML children *element* needs before Hancom will open it."""

    present = {_element_local_name(child) for child in element}
    return [name for name in _REQUIRED_SHAPE_CHILD_NAMES if name not in present]


# ------------------------------------------------------------------
# Caption (hp:caption) and shape text (hp:drawText) — shared content
# ------------------------------------------------------------------
#
# Both live on any ``AbstractShapeObjectType``/``AbstractDrawingObjectType``
# host (table/picture/OLE/equation/line/rect/ellipse/…, per ``ParaList XML
# schema.xml``) as an ``hp:subList`` of real paragraphs — the same construct
# table cells already use. ``Caption``/``DrawText`` below are thin live views
# reused by ``HwpxOxmlTable`` (table.py), ``HwpxOxmlShape``, and
# ``HwpxOxmlInlineObject`` (this module) rather than duplicated per host.

#: ``hp:caption/@side`` 어휘(스키마 기본값은 LEFT). 실코퍼스 15건 전수는
#: TOP 14 · BOTTOM 1 — LEFT/RIGHT 관측 0(테두리 옆 캡션은 실무에서 안 쓴다).
_CAPTION_SIDES = frozenset({"LEFT", "RIGHT", "TOP", "BOTTOM"})

#: 실코퍼스 15건 전수: fullSz="0"(전부) · width="8504"(전부, 호스트 크기와
#: 무관한 고정값) · gap="850"(11) 또는 "566"(4, 스키마 기본은 850).
_CAPTION_DEFAULT_WIDTH = "8504"
_CAPTION_DEFAULT_GAP = "850"

#: 캡션은 outMargin 바로 다음에 온다(실코퍼스 실측 — 표: outMargin, caption,
#: inMargin, tr; 도형: outMargin, caption, shapeComment). 그 뒤에 무엇이
#: 오는지는 호스트 종류마다 다르므로(표/도형/그림이 서로 다른 이름을 쓴다),
#: "X 앞"이 아니라 "outMargin 뒤"로 고정해야 호스트 종류에 기대지 않는다.
_CAPTION_AFTER_NAMES = ("outMargin",)

#: 실코퍼스 90건 전수: drawText/hp:textMargin left/right/top/bottom은
#: 283(≈0.1cm, Hancom UI 기본값)이 다수(각 축 60~66%), 다음은 0.
_DRAW_TEXT_DEFAULT_MARGIN = {"left": "283", "right": "283", "top": "283", "bottom": "283"}

#: drawText는 AbstractDrawingObjectType 자신의 시퀀스(lineShape/fillBrush/
#: shadow) 다음, 도형별 지오메트리(pt0류) 앞에 온다 — 실코퍼스: 스키마가
#: 선언한 lineShape/fillBrush/drawText/shadow 순서와 실제로 다르다(shadow가
#: drawText보다 먼저 나온다). 지오메트리 이름 중 가장 먼저 나오는 것(없으면
#: sz) 앞에 꽂으면 도형 종류와 무관하게 정확한 위치가 된다.
_DRAW_TEXT_BEFORE_NAMES = ("pt0", "pt", "startPt", "center", "seg", "sz")


def _wrap_paragraph(element: ET.Element, section: "HwpxOxmlSection") -> "HwpxOxmlParagraph":
    from .paragraph import HwpxOxmlParagraph

    return HwpxOxmlParagraph(element, section)


def _sublist_paragraphs(
    container: ET.Element, section: "HwpxOxmlSection"
) -> list["HwpxOxmlParagraph"]:
    sublist = container.find(f"{_HP}subList")
    if sublist is None:
        return []
    return [_wrap_paragraph(p, section) for p in sublist.findall(f"{_HP}p")]


def _ensure_sublist(
    container: ET.Element, *, vert_align: str = "CENTER"
) -> ET.Element:
    sublist = container.find(f"{_HP}subList")
    if sublist is None:
        attrs = _default_sublist_attributes()
        attrs["vertAlign"] = vert_align
        sublist = _append_child(container, f"{_HP}subList", attrs)
    return sublist


def _add_sublist_paragraph(
    container: ET.Element,
    text: str,
    *,
    section: "HwpxOxmlSection",
    vert_align: str,
    char_pr_id_ref: str | int | None,
) -> "HwpxOxmlParagraph":
    sublist = _ensure_sublist(container, vert_align=vert_align)
    attrs = {"id": _paragraph_id(), **_DEFAULT_PARAGRAPH_ATTRS}
    paragraph = _append_child(sublist, f"{_HP}p", attrs)
    run_attrs = {"charPrIDRef": str(char_pr_id_ref) if char_pr_id_ref is not None else "0"}
    run = _append_child(paragraph, f"{_HP}run", run_attrs)
    _append_text_with_tabs(run, text)
    return _wrap_paragraph(paragraph, section)


def _replace_sublist_text(
    container: ET.Element,
    text: str,
    *,
    section: "HwpxOxmlSection",
    vert_align: str,
    char_pr_id_ref: str | int | None,
) -> "HwpxOxmlParagraph":
    """Clear any existing paragraphs and author a single fresh one."""

    sublist = container.find(f"{_HP}subList")
    if sublist is not None:
        for existing in list(sublist.findall(f"{_HP}p")):
            sublist.remove(existing)
    return _add_sublist_paragraph(
        container, text, section=section, vert_align=vert_align, char_pr_id_ref=char_pr_id_ref
    )


class Caption:
    """Live view of an object's ``hp:caption`` — table/figure caption text."""

    def __init__(self, element: ET.Element, section: "HwpxOxmlSection"):
        self.element = element
        self.section = section

    @property
    def side(self) -> str:
        return self.element.get("side", "LEFT")

    @property
    def full_sz(self) -> bool:
        return self.element.get("fullSz", "0") not in ("0", "false", "False")

    @property
    def width(self) -> int | None:
        value = self.element.get("width")
        return int(value) if value is not None else None

    @property
    def gap(self) -> int:
        return int(self.element.get("gap", _CAPTION_DEFAULT_GAP))

    @property
    def paragraphs(self) -> list["HwpxOxmlParagraph"]:
        return _sublist_paragraphs(self.element, self.section)

    @property
    def text(self) -> str:
        return "\n".join(paragraph.text or "" for paragraph in self.paragraphs)

    def add_paragraph(
        self, text: str = "", *, char_pr_id_ref: str | int | None = None
    ) -> "HwpxOxmlParagraph":
        paragraph = _add_sublist_paragraph(
            self.element, text, section=self.section, vert_align="TOP",
            char_pr_id_ref=char_pr_id_ref,
        )
        self.section.mark_dirty()
        return paragraph

    def __repr__(self) -> str:
        return f"<Caption side={self.side!r} text={self.text!r}>"


class DrawText:
    """Live view of a shape's ``hp:drawText`` — text drawn inside the shape."""

    def __init__(self, element: ET.Element, section: "HwpxOxmlSection"):
        self.element = element
        self.section = section

    @property
    def name(self) -> str:
        """Hancom's auto-generated shape-tree object name (not a caption)."""

        return self.element.get("name", "")

    @property
    def editable(self) -> bool:
        return self.element.get("editable", "0") not in ("0", "false", "False")

    @property
    def text_margin(self) -> dict[str, int] | None:
        margin = self.element.find(f"{_HP}textMargin")
        if margin is None:
            return None
        return {side: int(margin.get(side, "0")) for side in ("left", "right", "top", "bottom")}

    @property
    def paragraphs(self) -> list["HwpxOxmlParagraph"]:
        return _sublist_paragraphs(self.element, self.section)

    @property
    def text(self) -> str:
        return "\n".join(paragraph.text or "" for paragraph in self.paragraphs)

    def add_paragraph(
        self, text: str = "", *, char_pr_id_ref: str | int | None = None
    ) -> "HwpxOxmlParagraph":
        paragraph = _add_sublist_paragraph(
            self.element, text, section=self.section, vert_align="CENTER",
            char_pr_id_ref=char_pr_id_ref,
        )
        self.section.mark_dirty()
        return paragraph

    def __repr__(self) -> str:
        return f"<DrawText name={self.name!r} text={self.text!r}>"


def _read_caption(host: ET.Element, section: "HwpxOxmlSection") -> Caption | None:
    element = host.find(f"{_HP}caption")
    if element is None:
        return None
    return Caption(element, section)


def _write_caption(
    host: ET.Element,
    text: str,
    *,
    section: "HwpxOxmlSection",
    side: str,
    full_sz: bool,
    width: int | None,
    gap: int,
    char_pr_id_ref: str | int | None,
) -> Caption:
    normalized_side = side.strip().upper()
    if normalized_side not in _CAPTION_SIDES:
        from ..errors import HwpxValueError

        raise HwpxValueError(
            f"unsupported caption side {side!r}",
            code="shape-caption-side-invalid",
            context={"requested": side, "available": sorted(_CAPTION_SIDES)},
            suggestion=f"side 는 {sorted(_CAPTION_SIDES)} 중 하나여야 합니다.",
        )

    element = host.find(f"{_HP}caption")
    if element is None:
        element = _append_child(host, f"{_HP}caption", {})
        _reposition_child_after_any(host, element, _CAPTION_AFTER_NAMES)

    element.set("side", normalized_side)
    element.set("fullSz", "1" if full_sz else "0")
    element.set("width", str(width) if width is not None else _CAPTION_DEFAULT_WIDTH)
    element.set("gap", str(gap))
    sz = host.find(f"{_HP}sz")
    if sz is not None and sz.get("width"):
        element.set("lastWidth", sz.get("width", ""))

    _replace_sublist_text(
        element, text, section=section, vert_align="TOP", char_pr_id_ref=char_pr_id_ref
    )
    section.mark_dirty()
    return Caption(element, section)


def _remove_caption(host: ET.Element, section: "HwpxOxmlSection") -> bool:
    element = host.find(f"{_HP}caption")
    if element is None:
        return False
    host.remove(element)
    section.mark_dirty()
    return True


def _read_draw_text(host: ET.Element, section: "HwpxOxmlSection") -> DrawText | None:
    element = host.find(f"{_HP}drawText")
    if element is None:
        return None
    return DrawText(element, section)


def _write_draw_text(
    host: ET.Element,
    text: str,
    *,
    section: "HwpxOxmlSection",
    name: str,
    editable: bool,
    margin: dict[str, int] | None,
    char_pr_id_ref: str | int | None,
) -> DrawText:
    element = host.find(f"{_HP}drawText")
    if element is None:
        element = _append_child(host, f"{_HP}drawText", {})
        _reposition_child_before_any(host, element, _DRAW_TEXT_BEFORE_NAMES)

    element.set("name", name)
    element.set("editable", "1" if editable else "0")
    sz = host.find(f"{_HP}sz")
    if sz is not None and sz.get("width"):
        element.set("lastWidth", sz.get("width", ""))

    _replace_sublist_text(
        element, text, section=section, vert_align="CENTER", char_pr_id_ref=char_pr_id_ref
    )

    margin_element = element.find(f"{_HP}textMargin")
    resolved_margin = margin or _DRAW_TEXT_DEFAULT_MARGIN
    if margin_element is None:
        margin_element = _append_child(element, f"{_HP}textMargin", {})
    for side in ("left", "right", "top", "bottom"):
        margin_element.set(side, str(resolved_margin.get(side, _DRAW_TEXT_DEFAULT_MARGIN[side])))

    section.mark_dirty()
    return DrawText(element, section)


def _remove_draw_text(host: ET.Element, section: "HwpxOxmlSection") -> bool:
    element = host.find(f"{_HP}drawText")
    if element is None:
        return False
    host.remove(element)
    section.mark_dirty()
    return True


class HwpxOxmlShape:
    """Wrapper for a drawing shape element (``<hp:line>``, ``<hp:rect>``, ``<hp:ellipse>``, etc.)."""

    def __init__(self, element: ET.Element, paragraph: "HwpxOxmlParagraph"):
        self.element = element
        self.paragraph = paragraph

    # --- basic properties --------------------------------------------------

    @property
    def shape_type(self) -> str:
        """Return the local tag name (e.g. ``'line'``, ``'rect'``, ``'ellipse'``)."""
        return _element_local_name(self.element)

    @property
    def inst_id(self) -> str | None:
        return self.element.get("instid") or self.element.get("id")

    @property
    def attributes(self) -> dict[str, str]:
        return dict(self.element.attrib)

    # --- size access -------------------------------------------------------

    @property
    def width(self) -> int:
        sz = self.element.find(f"{_HP}sz")
        if sz is not None:
            return int(sz.get("width", "0"))
        return 0

    @property
    def height(self) -> int:
        sz = self.element.find(f"{_HP}sz")
        if sz is not None:
            return int(sz.get("height", "0"))
        return 0

    def resize(self, width: int, height: int) -> None:
        """Resize the shape, including the geometry Hancom actually draws.

        Hancom renders a drawing object from its type-specific geometry
        (``pt0``–``pt3`` for a rectangle, ``center``/``ax1``/``ax2`` for an
        ellipse, ``startPt``/``endPt`` for a line) scaled by ``scaMatrix`` —
        not from ``sz``.  Updating the size elements alone reports a new size
        while the document keeps drawing the old one, so the geometry is
        scaled by the same per-axis ratio and ``scaMatrix`` is reset to
        identity.

        An axis with no current extent — the height of a perfectly horizontal
        line — has no geometry to scale.  Its coordinates are left alone and a
        :class:`UserWarning` is raised, because the drawn shape cannot follow
        the requested size.
        """
        old_width, old_height = self._geometry_size()
        w, h = str(width), str(height)
        for tag in ("sz", "orgSz", "curSz"):
            child = self.element.find(f"{_HP}{tag}")
            if child is not None:
                child.set("width", w)
                child.set("height", h)
        rot = self.element.find(f"{_HP}rotationInfo")
        if rot is not None:
            rot.set("centerX", str(width // 2))
            rot.set("centerY", str(height // 2))
        self._scale_geometry(old_width, old_height, width, height)
        self.paragraph.section.mark_dirty()

    def _geometry_size(self) -> tuple[int, int]:
        """Return the size the type-specific geometry is expressed in.

        That is ``orgSz``: in the corpus fixtures a shape's geometry always
        matches ``orgSz`` even when ``sz`` differs because ``scaMatrix``
        scales it.
        """
        for tag in ("orgSz", "sz"):
            child = self.element.find(f"{_HP}{tag}")
            if child is None:
                continue
            try:
                return int(child.get("width", "0")), int(child.get("height", "0"))
            except ValueError:
                return 0, 0
        return 0, 0

    def _scale_geometry(
        self,
        old_width: int,
        old_height: int,
        width: int,
        height: int,
    ) -> None:
        flat_axes = [
            name
            for name, old, new in (
                ("width", old_width, width), ("height", old_height, height),
            )
            if old <= 0 < new
        ]
        if flat_axes:
            warnings.warn(
                f"{self.shape_type} has no {' or '.join(flat_axes)} to scale; "
                "its geometry keeps the old coordinates and the shape will "
                "not be drawn at the requested size",
                UserWarning,
                stacklevel=3,
            )

        x_ratio = width / old_width if old_width > 0 else 1.0
        y_ratio = height / old_height if old_height > 0 else 1.0
        for child in self.element:
            local = _element_local_name(child)
            if local in _SHAPE_POINT_LOCAL_NAMES:
                pairs = _SHAPE_POINT_ATTR_PAIRS
            elif local == "seg":
                pairs = _SHAPE_SEGMENT_ATTR_PAIRS
            else:
                continue
            _scale_coordinates(child, pairs, x_ratio, y_ratio)

        rendering = self.element.find(f"{_HP}renderingInfo")
        if rendering is not None:
            sca = rendering.find(f"{_HC}scaMatrix")
            if sca is not None:
                for key, value in _IDENTITY_MATRIX.items():
                    sca.set(key, value)

    # --- line shape access -------------------------------------------------

    @property
    def line_color(self) -> str | None:
        ls = self.element.find(f"{_HP}lineShape")
        return ls.get("color") if ls is not None else None

    @line_color.setter
    def line_color(self, value: str) -> None:
        ls = self.element.find(f"{_HP}lineShape")
        if ls is not None:
            ls.set("color", value)
            self.paragraph.section.mark_dirty()

    @property
    def line_style(self) -> str | None:
        ls = self.element.find(f"{_HP}lineShape")
        return ls.get("style") if ls is not None else None

    @line_style.setter
    def line_style(self, value: str) -> None:
        ls = self.element.find(f"{_HP}lineShape")
        if ls is not None:
            ls.set("style", value)
            self.paragraph.section.mark_dirty()

    # --- generic attribute access ------------------------------------------

    def get_attribute(self, name: str) -> str | None:
        return self.element.get(name)

    def set_attribute(self, name: str, value: str | int | None) -> None:
        if value is None:
            if name in self.element.attrib:
                del self.element.attrib[name]
                self.paragraph.section.mark_dirty()
            return
        new_value = str(value)
        if self.element.get(name) != new_value:
            self.element.set(name, new_value)
            self.paragraph.section.mark_dirty()

    # --- caption (hp:caption — every shape kind may carry one) -------------

    @property
    def caption(self) -> "Caption | None":
        """This shape's ``hp:caption``, or ``None`` if it doesn't have one."""

        return _read_caption(self.element, self.paragraph.section)

    def set_caption(
        self,
        text: str,
        *,
        side: str = "TOP",
        full_sz: bool = False,
        width: int | None = None,
        gap: int = 850,
        char_pr_id_ref: str | int | None = None,
    ) -> "Caption":
        """Create (or replace the text of) this shape's ``hp:caption``.

        See :meth:`HwpxOxmlInlineObject.set_caption` for the real-corpus
        default rationale (*side*/*full_sz*/*gap*).
        """

        return _write_caption(
            self.element, text, section=self.paragraph.section,
            side=side, full_sz=full_sz, width=width, gap=gap,
            char_pr_id_ref=char_pr_id_ref,
        )

    def remove_caption(self) -> bool:
        """Remove this shape's ``hp:caption`` if present. Returns whether one was removed."""

        return _remove_caption(self.element, self.paragraph.section)

    # --- shape text (hp:drawText — only drawing shapes, never pic/tbl/ole) -

    @property
    def draw_text(self) -> "DrawText | None":
        """Text drawn inside this shape (a text box), or ``None`` if none."""

        return _read_draw_text(self.element, self.paragraph.section)

    def set_draw_text(
        self,
        text: str,
        *,
        name: str = "",
        editable: bool = False,
        margin: dict[str, int] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> "DrawText":
        """Create (or replace the text of) this shape's ``hp:drawText``.

        *margin* overrides ``hp:textMargin`` (``left``/``right``/``top``/
        ``bottom``, HWPUNIT); defaults to the real-corpus majority value
        (0.1cm/283 all four sides, 90-sample). *name* is Hancom's
        auto-generated shape-tree object label, not a caption — leave it
        empty unless reproducing a specific gold file.
        """

        return _write_draw_text(
            self.element, text, section=self.paragraph.section,
            name=name, editable=editable, margin=margin,
            char_pr_id_ref=char_pr_id_ref,
        )

    def remove_draw_text(self) -> bool:
        """Remove this shape's ``hp:drawText`` if present. Returns whether one was removed."""

        return _remove_draw_text(self.element, self.paragraph.section)

    def __repr__(self) -> str:
        return f"<HwpxOxmlShape type={self.shape_type!r} id={self.inst_id!r}>"

__all__ = ["Caption", "DrawText", "HwpxOxmlInlineObject", "HwpxOxmlShape"]
