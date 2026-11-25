# SPDX-License-Identifier: Apache-2.0
"""Inline-object, shape, picture, and drawing OXML wrappers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence, cast
import xml.etree.ElementTree as ET

from lxml import etree as LET  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

from ._document_primitives import (
    _require_text,
    SameElement,
    attributes_in_order,
    paragraph_attributes,
    _HC,
    _HP,
    _normalize_color,
    _append_child,
    _append_text_with_tabs,
    _clear_paragraph_layout_cache,
    _default_sublist_attributes,
    _element_local_name,
    _object_id,
    _reposition_child_after_any,
    _reposition_child_before_any,
    _paragraph_id,
)
from ._paragraph_text_edit import live_holder, live_paragraph
from .shape_position import (
    DRAWING_SHAPE_NAMES, PLACED_OBJECT_NAMES, ObjectPlacement, equation_font_size, fill_color_of, keep_ratio,
    line_width_mm_of, line_width_units, object_size, own_size,
    picture_crop, picture_glow, picture_image_value, picture_original_size, picture_shadow,
    resize_object, resize_shape, resize_turned_as_own, _group_member_refused, _in_group,
    set_equation_font, set_equation_font_size, set_equation_script, set_picture_crop,
    PictureGlow, PictureReflection, PictureShadow, append_picture_effects, validate_picture_effects,
    _object_set_position, build_at_original_size, fit_new_floating_object, refuse_resizing_flipped, resize_group,
    stack_new_object, validate_draw_text_vert_align, validate_picture_align,
    validate_caption_gap, validate_caption_side, validate_picture_border, validate_picture_crop, validate_picture_image,
    validate_rect_ratio,
    validate_shape_size,
)

if TYPE_CHECKING:
    from ._document_primitives import IdSource
    from typing import Union

    from ..objects.binary_item import BinaryItem
    from typing import Iterable, Iterator

    from ..objects.results import Alignment, ParagraphPlace
    from .header import Style
    from .paragraph import HwpxOxmlParagraph
    from .section import HwpxOxmlSection
    from .table import HwpxOxmlTable

    #: What ``paragraph.objects`` holds.
    ParagraphObject = Union["HwpxOxmlTable", "HwpxOxmlInlineObject", "HwpxOxmlShape"]


class HwpxOxmlInlineObject(SameElement, ObjectPlacement):
    """A placed object in a paragraph (picture, equation, chart, OLE, form control...): its attributes,
    placement (:class:`~hwpx.oxml.shape_position.ObjectPlacement`), size and caption."""

    if TYPE_CHECKING:
        paragraph: "HwpxOxmlParagraph"
    else:
        paragraph = live_paragraph  # the paragraph holding it now, also after a move

    def __init__(self, element: ET.Element, paragraph: "HwpxOxmlParagraph"):
        self.element = element
        self.paragraph = paragraph

    @property
    def tag(self) -> str:
        """Return the fully qualified XML tag for the inline object."""

        return self.element.tag

    @property
    def attributes(self) -> dict[str, str]:
        """Return a copy of the element attributes (one of them: ``obj.attributes.get(name)``)."""

        return dict(self.element.attrib)

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

    # Lives in ``oxml/shape_position.py`` (this owner file is at its line cap).
    set_position = _object_set_position

    @property
    def width(self) -> int:
        """The object's own width as drawn, before it is turned (HWPUNIT) -- the size ``resize`` takes, see
        ``shape_position.own_size``; unturned, the width of ``hp:sz`` (:attr:`box_width`)."""

        return own_size(self.element)[0]

    @property
    def height(self) -> int:
        """The object's own height as drawn, before it is turned (HWPUNIT); see :attr:`width`."""

        return own_size(self.element)[1]

    @property
    def box_width(self) -> int:
        """The width of the box the object takes in its paragraph (``hp:sz``, HWPUNIT; read only): a turned
        object's box is the box around it as turned. Unturned, it is :attr:`width`."""

        return object_size(self.element)[0]

    @property
    def box_height(self) -> int:
        """The height of the box the object takes in its paragraph (``hp:sz``, HWPUNIT; read only)."""

        return object_size(self.element)[1]

    def resize(self, width: int | None = None, height: int | None = None) -> None:
        """Draw the object *width* x *height* (HWPUNIT, its own size -- :attr:`width`, :attr:`height`); give one
        alone to keep the aspect ratio. Its own size again changes nothing.

        ``hp:sz`` and ``hp:curSz`` take the new size and ``hc:scaMatrix`` scales the original size
        (``hp:orgSz``) to it, as Hancom saves a resized picture. A size that is not an int in
        ``0 <= value < 2**31`` is refused with ``shape-size-value``. The paragraph loses its line
        layout cache. An equation is refused (``shape-equation-resize-unsupported``): its box follows its
        script and font size, and Hancom 2024 measures it again whatever size it is given -- change
        ``equation.script`` or ``equation.font_size`` instead.
        """

        if keep_ratio(own_size(self.element), width, height) == own_size(self.element):
            return
        resize_object(self, width, height)

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
        full_size: bool = False,
        width: int | None = None,
        gap: int = 850,
        char_pr_id_ref: str | int | None = None,
    ) -> "Caption":
        """Create (or replace the text of) this object's ``hp:caption``.

        *side*/*full_size* (``fullSz``)/*gap* default to the real-corpus majority
        convention (15-sample: side=TOP 14/15, fullSz=false 15/15,
        gap=850 11/15) — the schema's own default (``side="LEFT"``) is
        essentially unobserved in practice.
        """

        _require_text(text)  # not text: refused before anything is written
        return _write_caption(
            self.element, text, section=self.paragraph.section,
            side=side, full_sz=full_size, width=width, gap=gap,
            char_pr_id_ref=char_pr_id_ref,
        )

    def remove_caption(self) -> bool:
        """Remove this object's ``hp:caption`` if present. Returns whether one was removed."""

        return _remove_caption(self.element, self.paragraph.section)


class HwpxOxmlPicture(HwpxOxmlInlineObject):
    """A picture (``hp:pic``): the image it shows, how much of it is cut away, and its size and placement."""

    @property
    def item_id(self) -> str | None:
        """The binary item the picture shows (``hc:img/@binaryItemIDRef``), as ``doc.media.images`` names it."""

        image = self.element.find(f"{_HC}img")
        return image.get("binaryItemIDRef") if image is not None else None

    @property
    def original_size(self) -> tuple[int, int] | None:
        """The whole image's size (``hp:imgDim``) the crop counts in; ``None`` when the picture has none."""

        return picture_original_size(self.element)

    @property
    def crop(self) -> tuple[int, int, int, int]:
        """How much is cut from the image's left, top, right and bottom (``hp:imgClip``), in
        ``original_size`` units; ``(0, 0, 0, 0)`` when nothing is.

        Setting it cuts that ``(left, top, right, bottom)`` from the image; ``None`` (or all 0) shows
        all of it. The picture keeps the scale it is drawn at, so it grows or shrinks by what it shows
        more or less. Ints from 0 leaving some of the image, else ``shape-picture-crop-value``."""

        return picture_crop(self.element)

    @crop.setter
    def crop(self, crop: tuple[int, int, int, int] | None) -> None:
        set_picture_crop(self, crop)

    # The reads of what ``add_picture`` writes (``hc:img``, ``hp:lineShape``, ``hp:effects``).
    @property
    def brightness(self) -> int:
        """Brightness the image is drawn with, -100..100 (``hc:img/@bright``)."""

        return int(picture_image_value(self.element, "bright"))

    @property
    def contrast(self) -> int:
        """Contrast the image is drawn with, -100..100 (``hc:img/@contrast``)."""

        return int(picture_image_value(self.element, "contrast"))

    @property
    def effect(self) -> str:
        """``REAL_PIC``, ``GRAY_SCALE`` or ``BLACK_WHITE`` (``hc:img/@effect``)."""

        return str(picture_image_value(self.element, "effect"))

    @property
    def alpha(self) -> int:
        """Transparency, 0 opaque to 255 not drawn (``hc:img/@alpha``)."""

        return int(picture_image_value(self.element, "alpha"))

    @property
    def line_width_mm(self) -> float | None:
        """Border width in mm (``hp:lineShape/@width``, read to a hundredth: 33 HWPUNIT is 0.12);
        ``None`` without a border."""

        return line_width_mm_of(self.element)

    @property
    def shadow(self) -> PictureShadow | None:
        """The shadow as a :class:`PictureShadow`, or ``None``."""

        return picture_shadow(self.element)

    @property
    def glow(self) -> PictureGlow | None:
        """The glow as a :class:`PictureGlow`, or ``None``."""

        return picture_glow(self.element)

    @property
    def line_color(self) -> str | None:
        """Border colour (``hp:lineShape/@color``); ``None`` without a border."""

        line = self.element.find(f"{_HP}lineShape")
        return line.get("color") if line is not None else None


class HwpxOxmlEquation(HwpxOxmlInlineObject):
    """An equation (``hp:equation``): its script in Hancom's equation language and the box it is drawn in."""

    @property
    def script(self) -> str:
        """The equation's script (``hp:script``), e.g. ``{a} over {b}``.

        Setting it replaces the script and measures the box again as ``add_equation`` does, at this
        equation's ``font_size``: ``hp:sz`` and ``baseLine`` follow the new script and the paragraph (and
        the paragraphs holding it) lose their line layout cache. An empty script, a LaTeX command or braces
        that do not pair are refused before anything changes."""

        node = self.element.find(f"{_HP}script")
        return (node.text or "") if node is not None else ""

    @script.setter
    def script(self, script: str) -> None:
        set_equation_script(self, script)

    @property
    def font(self) -> str | None:
        """The equation font (``font``), e.g. ``HancomEQN``. Setting it takes a non-empty font name
        (``shape-equation-font-empty``); the box stays and the paragraph loses its line layout cache."""

        return self.element.get("font")

    @font.setter
    def font(self, font: str) -> None:
        set_equation_font(self, font)

    @property
    def font_size(self) -> float:
        """The equation's font size in points (``baseUnit`` / 100); 10.0 (the schema's) when not given.
        Setting it (a number of points from 0.01, ``shape-equation-base-unit-value``) measures the box again
        as ``add_equation`` does at that size; the paragraph and the paragraphs holding it lose their line
        layout cache."""

        return equation_font_size(self.element)

    @font_size.setter
    def font_size(self, font_size: float) -> None:
        set_equation_font_size(self, font_size)

    @property
    def base_line(self) -> int | None:
        """Where the base line sits, in per cent of the height from the top (``baseLine``)."""

        value = self.element.get("baseLine")
        return int(value) if value is not None and value.lstrip("-").isdigit() else None


def wrap_object(element: ET.Element, paragraph: "HwpxOxmlParagraph") -> "ParagraphObject":
    """The model object for *element*, an object in *paragraph*: a table, picture, equation, drawing
    shape or other placed object."""

    name = _element_local_name(element)
    if name == "tbl":
        from .table import HwpxOxmlTable

        return HwpxOxmlTable(element, paragraph)
    if name == "pic":
        return HwpxOxmlPicture(element, paragraph)
    if name == "equation":
        return HwpxOxmlEquation(element, paragraph)
    if name in DRAWING_SHAPE_NAMES:
        return HwpxOxmlShape(element, paragraph)
    return HwpxOxmlInlineObject(element, paragraph)


def _paragraph_objects(self: "HwpxOxmlParagraph") -> "tuple[ParagraphObject, ...]":
    """Every object this paragraph's runs hold, in order: tables, pictures, equations, drawing shapes,
    charts, OLE objects and form controls. Objects inside them (a table's cells, a text box, a
    group's members) belong to their own paragraphs or to ``Shape.members``."""

    names = DRAWING_SHAPE_NAMES | PLACED_OBJECT_NAMES | {"tbl"}
    return tuple(
        wrap_object(child, self) for run in self._run_elements() for child in run
        if _element_local_name(child) in names
    )


def _paragraph_pictures(self: "HwpxOxmlParagraph") -> "tuple[HwpxOxmlPicture, ...]":
    """The pictures this paragraph's runs hold, in order (pictures in a group: ``Shape.members``)."""

    return tuple(obj for obj in _paragraph_objects(self) if isinstance(obj, HwpxOxmlPicture))


def _paragraph_equations(self: "HwpxOxmlParagraph") -> "tuple[HwpxOxmlEquation, ...]":
    """The equations this paragraph's runs hold, in order."""

    return tuple(obj for obj in _paragraph_objects(self) if isinstance(obj, HwpxOxmlEquation))


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
    "width": "33",
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


#: The attributes every drawing object starts with, in the order Hancom writes them.
_SHAPE_ATTRIBUTE_ORDER = (
    "id", "zOrder", "numberingType", "textWrap", "textFlow", "lock", "dropcapstyle", "href", "groupLevel", "instid",
)


def _build_shape_common_children(
    parent: ET.Element,
    width: int,
    height: int,
    *,
    ids: "IdSource | None",
    treat_as_char: bool = True,
    inst_id: str | None = None,
    flip_horizontal: bool = False,
    flip_vertical: bool = False,
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
    w, h = map(str, validate_shape_size(width, height))  # Hancom reads a negative size as 0
    the_id = inst_id or _object_id(ids)

    parent.set("id", the_id)
    parent.set("zOrder", "0")
    parent.set("numberingType", "NONE")
    # Hancom writes both on every shape and reads a shape without them as these;
    # a value the caller set (a picture's text_wrap) stays.
    if parent.get("textWrap") is None:
        parent.set("textWrap", "SQUARE")
    if parent.get("textFlow") is None:
        parent.set("textFlow", "BOTH_SIDES")
    parent.set("lock", "0")
    parent.set("dropcapstyle", "None")
    parent.set("href", "")
    parent.set("groupLevel", "0")
    parent.set("instid", the_id)
    # Hancom writes these first and the kind's own attributes (ratio, arcType, isReverseHV ...) after them
    # (every rect, ellipse, line, arc and picture of tests/fixtures/hancom_saved); a builder sets those first
    attributes_in_order(parent, _SHAPE_ATTRIBUTE_ORDER)

    # --- AbstractShapeComponentType children (come first in real files) ---
    _append_child(parent, f"{_HP}offset", {"x": "0", "y": "0"})
    _append_child(parent, f"{_HP}orgSz", {"width": w, "height": h})
    _append_child(parent, f"{_HP}curSz", {"width": w, "height": h})
    _append_child(parent, f"{_HP}flip", {
        "horizontal": "1" if flip_horizontal else "0",
        "vertical": "1" if flip_vertical else "0",
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

    _append_child(parent, f"{_HP}sz", {  # Hancom's order (6,055 of the hp:sz in tests/fixtures/hancom_saved)
        "width": w, "widthRelTo": "ABSOLUTE",
        "height": h, "heightRelTo": "ABSOLUTE",
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
            "vertRelTo": "PARA", "horzRelTo": "COLUMN",  # Hancom's order, as below (6,055 hp:pos in hancom_saved)
            "vertAlign": "TOP", "horzAlign": "LEFT",
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
    line_width: str = "33",
    line_style: str = "SOLID",
    fill_color: str | None = None,
) -> None:
    """Append AbstractDrawingObjectType children: lineShape, fillBrush, shadow."""
    ls_attrs = dict(_DEFAULT_LINE_SHAPE_ATTRS)
    ls_attrs["color"] = _normalize_color(line_color) or "#000000"
    ls_attrs["width"] = line_width
    ls_attrs["style"] = line_style
    _append_child(parent, f"{_HP}lineShape", ls_attrs)

    face_color = _normalize_color(fill_color)
    if face_color is not None:
        # Hancom reads the fill from the core namespace; an ``hp:fillBrush`` is
        # accepted by the parser but silently rendered unfilled.
        fb = _append_child(parent, f"{_HC}fillBrush", {})
        _append_child(fb, f"{_HC}winBrush", {
            "faceColor": face_color, "hatchColor": "#FFFFFF", "alpha": "0",
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
    ids: "IdSource | None",
    line_color: str = "#000000",
    line_width: str = "33",
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
    # 1) AbstractShapeComponentType children (offset, orgSz, … renderingInfo).
    # orgSz/curSz keep at least 1 on each side, as Hancom writes a horizontal
    # line (w x 1): with a 0 side Hancom does not draw the line at all.
    _build_shape_common_children(el, max(w, 1), max(h, 1), ids=ids, treat_as_char=treat_as_char)
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
    ids: "IdSource | None",
    ratio: int = 0,
    line_color: str = "#000000",
    line_width: str = "33",
    fill_color: str | None = None,
    treat_as_char: bool = True,
) -> ET.Element:
    """Build a complete ``<hp:rect>`` element matching real HWPX output."""
    el = ET.Element(f"{_HP}rect", {"ratio": str(validate_rect_ratio(ratio))})
    _build_shape_common_children(el, width, height, ids=ids, treat_as_char=treat_as_char)
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
    ids: "IdSource | None",
    line_color: str = "#000000",
    line_width: str = "33",
    fill_color: str | None = None,
    treat_as_char: bool = True,
) -> ET.Element:
    """Build a complete ``<hp:ellipse>`` element matching real HWPX output."""
    el = ET.Element(f"{_HP}ellipse", {
        "intervalDirty": "0",
        "hasArcPr": "0",
        "arcType": "NORMAL",
    })
    _build_shape_common_children(el, width, height, ids=ids, treat_as_char=treat_as_char)
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


#: Schema enum for ``hp:arc/@type`` (ParaList XML schema.xml ``ArcType``).
_ARC_TYPES = frozenset({"NORMAL", "PIE", "CHORD"})

#: The four canonical quadrant placements :func:`_create_arc_element` draws,
#: reusing Hancom's own ``hp:flip`` mirroring instead of re-deriving new
#: point math — only ``TOP_LEFT`` is corpus-verified point-for-point
#: (``SimpleArc.hwpx``: center sits at the bbox corner, ``ax1`` straight
#: down from it, ``ax2`` straight right from it — the schema gives an arc
#: only those 3 points and no angle fields at all, so that pairing *is* the
#: whole geometry). The other three corners flip that same verified
#: pattern — the identical mechanism line/rect/ellipse/polygon already use
#: to mirror geometry here — rather than inventing new arc-specific point
#: math for angles this package has never seen Hancom actually produce.
_ARC_CORNER_FLIPS: dict[str, tuple[bool, bool]] = {
    "TOP_LEFT": (False, False),
    "TOP_RIGHT": (True, False),
    "BOTTOM_LEFT": (False, True),
    "BOTTOM_RIGHT": (True, True),
}


def _create_arc_element(
    width: int,
    height: int,
    *,
    ids: "IdSource | None",
    corner: str = "TOP_LEFT",
    arc_type: str = "NORMAL",
    line_color: str = "#000000",
    line_width: str = "33",
    fill_color: str | None = None,
    treat_as_char: bool = True,
) -> ET.Element:
    """Build a complete ``<hp:arc>`` element matching real HWPX output.

    Only a quarter-ellipse is corpus-verified (see ``_ARC_CORNER_FLIPS``) —
    *corner* picks which of the bounding box's four corners the pivot sits
    at, and *arc_type* is the schema's own ``NORMAL``/``PIE``/``CHORD``
    passthrough (open arc / pie wedge / chord-closed segment).
    """
    if corner not in _ARC_CORNER_FLIPS or arc_type not in _ARC_TYPES:
        from ..errors import HwpxValueError

        if corner not in _ARC_CORNER_FLIPS:
            raise HwpxValueError(
                f"corner must be one of {sorted(_ARC_CORNER_FLIPS)}, got {corner!r}",
                code="shape-arc-corner-invalid",
                context={"corner": corner, "allowed": sorted(_ARC_CORNER_FLIPS)},
            )
        raise HwpxValueError(
            f"arc_type must be one of {sorted(_ARC_TYPES)}, got {arc_type!r}",
            code="shape-arc-type-invalid",
            context={"arc_type": arc_type, "allowed": sorted(_ARC_TYPES)},
        )
    flip_horizontal, flip_vertical = _ARC_CORNER_FLIPS[corner]

    el = ET.Element(f"{_HP}arc", {"type": arc_type})
    _build_shape_common_children(
        el, width, height, ids=ids, treat_as_char=treat_as_char,
        flip_horizontal=flip_horizontal, flip_vertical=flip_vertical,
    )
    _build_drawing_object_children(
        el, line_color=line_color, line_width=line_width, fill_color=fill_color,
    )
    _append_child(el, f"{_HC}center", {"x": "0", "y": "0"})
    _append_child(el, f"{_HC}ax1", {"x": "0", "y": str(height)})
    _append_child(el, f"{_HC}ax2", {"x": str(width), "y": "0"})
    _build_shape_base_children(el, width, height)
    return el


def _create_polygon_element(
    points: Sequence[tuple[int, int]],
    *,
    ids: "IdSource | None",
    line_color: str = "#000000",
    line_width: str = "33",
    fill_color: str | None = None,
    treat_as_char: bool = True,
) -> ET.Element:
    """Build a complete ``<hp:polygon>`` element matching real HWPX output.

    Hancom stores a polygon's vertices as ``hc:pt`` children in the shape's
    own top-left-anchored local coordinate space — the corpus
    ``SimplePolygon`` fixture's 8 vertices span exactly (0, 0)-(17925, 13425),
    matching its own ``orgSz`` to the unit. That is the same convention
    ``hp:rect``'s four corners use (``pt0``-``pt3`` always run 0..width,
    0..height), so *points* are translated here to put the polygon's own
    bounding box at that local origin — *offset*/*pos* (added by
    ``_build_shape_base_children``) place the shape on the page, not the
    vertex coordinates themselves.
    """
    xs = [x for x, _y in points]
    ys = [y for _x, y in points]
    min_x, min_y = min(xs), min(ys)
    width = max(xs) - min_x
    height = max(ys) - min_y

    el = ET.Element(f"{_HP}polygon")
    _build_shape_common_children(el, width, height, ids=ids, treat_as_char=treat_as_char)
    _build_drawing_object_children(
        el, line_color=line_color, line_width=line_width, fill_color=fill_color,
    )
    for x, y in points:
        _append_child(el, f"{_HC}pt", {"x": str(x - min_x), "y": str(y - min_y)})
    _build_shape_base_children(el, width, height)
    return el


def _closed_points(points: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """Repeat the first vertex at the end unless it is already there.

    That is how Hancom closes a polygon; without it Hancom draws the vertices
    as an open line and leaves the last side out.
    """

    closed = [(x, y) for x, y in points]
    if closed and closed[0] != closed[-1]:
        closed.append(closed[0])
    return closed


def _create_picture_element(
    binary_item_id_ref: str,
    width: int,
    height: int,
    *,
    ids: "IdSource | None",
    alignment: str | None = None,
    treat_as_char: bool = True,
    pos_overrides: dict[str, str | int] | None = None,
    text_wrap: str | None = None,
    brightness: int = 0,
    contrast: int = 0,
    effect: str = "REAL_PIC",
    alpha: int = 0,
    line_color: str | None = None,
    line_width: int = 33,
    crop: tuple[int, int, int, int] | None = None,
    shadow: PictureShadow | None = None,
    glow: PictureGlow | None = None,
    soft_edge: int | None = None,
    reflection: PictureReflection | None = None,
) -> ET.Element:
    """Build a ``<hp:pic>`` element using the corpus-observed picture shape: the image *width* x *height* with
    *crop* (left, top, right, bottom, HWPUNIT) cut from its sides at the same scale, as Hancom crops a picture
    (``hp:imgDim`` the whole picture, ``hp:imgClip`` the part kept in it, the picture drawn as large as that part),
    adjusted by *brightness*,
    *contrast*, *effect* and *alpha* (see :func:`~hwpx.oxml.shape_position.validate_picture_image`), and with a
    solid border *line_width* wide when *line_color* is given (``hp:lineShape`` right before ``hp:imgRect``, where
    the schema's PictureType has it and where it stands in Hancom's pictures whichever of their two child orders they
    use; Hancom draws the border and saves it there wherever it is read)."""

    brightness, contrast, effect, alpha = validate_picture_image(brightness, contrast, effect, alpha)
    validate_picture_border(line_width)  # given or not: a bad width is not dropped quietly
    validate_shape_size(width, height)
    left, top, right, bottom = validate_picture_crop(crop, width, height)
    validate_picture_effects(shadow, glow, soft_edge, reflection)
    whole_width, whole_height = width, height
    width, height = width - left - right, height - top - bottom  # as drawn
    border = None
    if line_color is not None:
        border = dict(_DEFAULT_LINE_SHAPE_ATTRS, color=_normalize_color(line_color) or "#000000",
                      width=str(line_width))
    el = ET.Element(f"{_HP}pic", {
        "textWrap": text_wrap or "SQUARE",
        "textFlow": "BOTH_SIDES",
        "reverse": "0",
    })
    _build_shape_common_children(el, width, height, ids=ids, treat_as_char=treat_as_char)
    el.set("numberingType", "PICTURE")

    if border is not None:
        _append_child(el, f"{_HP}lineShape", border)
    rect = _append_child(el, f"{_HP}imgRect", {})
    _append_child(rect, f"{_HC}pt0", {"x": "0", "y": "0"})
    _append_child(rect, f"{_HC}pt1", {"x": str(width), "y": "0"})
    _append_child(rect, f"{_HC}pt2", {"x": str(width), "y": str(height)})
    _append_child(rect, f"{_HC}pt3", {"x": "0", "y": str(height)})
    _append_child(el, f"{_HP}imgClip", {
        "left": str(left),
        "right": str(whole_width - right),
        "top": str(top),
        "bottom": str(whole_height - bottom),
    })
    _append_child(el, f"{_HP}inMargin", {
        "left": "0",
        "right": "0",
        "top": "0",
        "bottom": "0",
    })
    _append_child(el, f"{_HP}imgDim", {
        "dimwidth": str(whole_width),
        "dimheight": str(whole_height),
    })
    _append_child(el, f"{_HC}img", {
        "binaryItemIDRef": binary_item_id_ref,
        "bright": str(brightness),
        "contrast": str(contrast),
        "effect": effect,
        "alpha": str(alpha),
    })
    append_picture_effects(_append_child(el, f"{_HP}effects", {}), shadow, glow, soft_edge, reflection)
    _build_shape_base_children(el, width, height)

    if alignment:
        pos = el.find(f"{_HP}pos")
        if pos is not None:
            pos.set("horzAlign", validate_picture_align(alignment) or "LEFT")
    if pos_overrides:
        pos = el.find(f"{_HP}pos")
        if pos is not None:
            # Floating placement: relTo / align / offset onto the <hp:pos> built by
            # _build_shape_base_children (its treat_as_char=False branch).
            for key, value in pos_overrides.items():
                if value is None:
                    continue
                if key in ("horzOffset", "vertOffset"):
                    value = _picture_offset(key, value)
                pos.set(key, str(value))
    _append_child(el, f"{_HP}shapeComment", {})
    return el


def _picture_offset(name: str, value: object) -> int:
    """A ``pos_overrides`` offset as ``hp:pos`` stores it: whole HWP units, a negative one (left of or
    above its frame) in its unsigned 32-bit form, as Hancom writes one (the pictures, shapes and text
    boxes Hangul saved in ``tests/fixtures/hancom_saved/flip_*.hwpx`` say ``vertOffset="4294966298"`` for
    -998). Negative offsets were clamped to 0 up to 7.0.2, which moved the picture."""

    from ..errors import HwpxValueError

    try:
        number = round(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        number = None
    if number is None or isinstance(value, bool) or number < -(2**31):
        raise HwpxValueError(
            f"{name} must be a number of HWP units from -2147483648 up; got {value!r}",
            code="shape-position-value",
            context={"argument": name, "value": repr(value)},
            suggestion="Pass the offset in HWP units (1 mm = 283.465); a negative one goes left or up.",
        )
    return number & 0xFFFFFFFF if number < 0 else number


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
# HwpxOxmlParagraph shape-authoring methods
# ------------------------------------------------------------------
#
# Defined here — not in ``oxml/paragraph.py`` — and attached onto
# ``HwpxOxmlParagraph`` below as plain class-attribute assignments (a
# function assigned as a class attribute is a method like any other).  That
# owner module sits at the modularization line cap
# (``tests/test_oxml_modularization.py``), and this shape-authoring surface
# is naturally cohesive with the ``_create_*_element`` builders already in
# this file, so it lives here instead of growing ``paragraph.py`` past the
# cap.  ``paragraph.add_rectangle(...)`` etc. keep working exactly as before
# — only where the code lives changed.


def _paragraph_insert_shape_element(
    self: "HwpxOxmlParagraph",
    element: ET.Element,
    *,
    run_attributes: dict[str, str] | None = None,
    char_pr_id_ref: str | int | None = None,
) -> "HwpxOxmlShape":
    """Attach a pre-built shape element into a new run and return a wrapper."""
    run = self._create_run_for_object(
        run_attributes,
        char_pr_id_ref=char_pr_id_ref,
    )
    # Ensure element type matches the run type (lxml vs stdlib ET)
    if type(element) is not type(run):
        element = LET.fromstring(ET.tostring(element, encoding="utf-8"))
    run.append(element)
    stack_new_object(element, self.section)  # over the objects made before it, as Hancom numbers them
    fit_new_floating_object(element, self)  # in a cell, text box, note or header: placed as Hancom does there
    self.section.mark_dirty()
    return HwpxOxmlShape(element, self)


def _paragraph_add_picture(
    self: "HwpxOxmlParagraph",
    item_id: "str | BinaryItem",
    *,
    width: int = 14400,
    height: int = 14400,
    alignment: "Alignment | str | None" = None,
    treat_as_char: bool = True,
    pos_overrides: dict[str, str | int] | None = None,
    text_wrap: str | None = None,
    brightness: int = 0,
    contrast: int = 0,
    effect: str = "REAL_PIC",
    alpha: int = 0,
    line_color: str | None = None,
    line_width_mm: float = 0.12,
    crop: tuple[int, int, int, int] | None = None,
    shadow: PictureShadow | None = None,
    glow: PictureGlow | None = None,
    soft_edge: int | None = None,
    reflection: PictureReflection | None = None,
    run_attributes: dict[str, str] | None = None,
    char_pr_id_ref: str | int | None = None,
) -> HwpxOxmlPicture:
    """Insert a corpus-shaped ``<hp:pic>`` showing the embedded image *item_id* (the
    :class:`~hwpx.objects.BinaryItem` ``doc.media.add_image`` returns, or its id).

    *alignment* (``LEFT``, ``CENTER``, ``RIGHT``, ``INSIDE``, ``OUTSIDE``, any case) is the picture's
    ``hp:pos/@horzAlign``. With ``treat_as_char=False`` and ``pos_overrides`` the picture is placed as a
    **floating** object: ``pos_overrides`` sets ``horz/vertRelTo`` (e.g. ``PAPER``),
    ``horz/vertAlign`` and ``horz/vertOffset`` (HWPUNIT; a negative one left of or above the frame) on the
    ``<hp:pos>`` so the image lands at a fixed page position (used by 직인 placement).
    ``text_wrap`` overrides the pic's ``textWrap`` (e.g. ``IN_FRONT_OF_TEXT`` so a
    seal stamped over a line does not reflow the text it overlaps).

    *brightness* and *contrast* (-100 to 100), *effect* (``REAL_PIC``, ``GRAY_SCALE`` or ``BLACK_WHITE``) and
    *alpha* (transparency, 0 opaque to 255 not drawn) adjust the image as Hancom draws it; *line_color* (with
    *line_width_mm*, mm: 0.12 is the 33 HWPUNIT Hancom writes) gives the picture a solid border.
    *crop* ``(left, top, right, bottom)`` cuts that much
    (HWPUNIT) from the sides of the *width* x *height* picture at the same scale: the picture is drawn
    ``width - left - right`` by ``height - top - bottom``. A value Hancom does not draw is refused
    *shadow* (:class:`~hwpx.oxml.PictureShadow`) and *glow*
    (:class:`~hwpx.oxml.PictureGlow`) draw a shadow and a glow, the picture taking as much more room; *soft_edge*
    (HWPUNIT) fades its edge and *reflection* (:class:`~hwpx.oxml.PictureReflection`) reflects it below.
    (``shape-picture-image-value``, ``shape-picture-border-value``, ``shape-picture-crop-value``,
    ``shape-picture-effect-value``) before anything
    is added.
    """

    from ._paragraph_text_edit import require_in_document

    require_in_document(self, caller="add_picture")  # before the image goes into the package
    if pos_overrides and treat_as_char:
        from ..errors import HwpxValueError

        raise HwpxValueError(
            "pos_overrides is for floating placement; pass treat_as_char=False "
            "(a PAPER-relative <hp:pos> on an inline pic is contradictory)",
            code="shape-position-unsupported",
            context={"pos_overrides": sorted(pos_overrides)},
            suggestion="Pass treat_as_char=False with pos_overrides, or drop pos_overrides.",
        )

    element = _create_picture_element(  # checked before its run is added
        str(item_id),
        width,
        height,
        ids=self.section._ids,
        alignment=alignment,
        treat_as_char=treat_as_char,
        pos_overrides=pos_overrides,
        text_wrap=text_wrap,
        brightness=brightness,
        contrast=contrast,
        effect=effect,
        alpha=alpha,
        line_color=line_color,
        line_width=line_width_units(line_width_mm),
        crop=crop,
        shadow=shadow,
        glow=glow,
        soft_edge=soft_edge,
        reflection=reflection,
    )
    run = self._create_run_for_object(
        run_attributes,
        char_pr_id_ref=char_pr_id_ref,
    )
    if type(element) is not type(run):
        element = LET.fromstring(ET.tostring(element, encoding="utf-8"))
    run.append(element)
    stack_new_object(element, self.section)
    if not pos_overrides:  # placed by its caller otherwise
        fit_new_floating_object(element, self)
    self.section.mark_dirty()
    return HwpxOxmlPicture(element, self)


def _paragraph_add_line(
    self: "HwpxOxmlParagraph",
    start_x: int = 0,
    start_y: int = 0,
    end_x: int = 14400,
    end_y: int = 0,
    *,
    line_color: str = "#000000",
    line_width_mm: float = 0.12,
    treat_as_char: bool = True,
    run_attributes: dict[str, str] | None = None,
    char_pr_id_ref: str | int | None = None,
) -> "HwpxOxmlShape":
    """Insert a spec-compliant ``<hp:line>`` drawing shape.

    Coordinates are in HWPUNIT (7200 per inch); *line_width_mm* is the line's width in mm (0.12 is the
    33 HWPUNIT Hancom writes, 0 draws none; ``shape-picture-border-value`` for a negative one).
    """
    el = _create_line_element(
        start_x, start_y, end_x, end_y,
        ids=self.section._ids,
        line_color=line_color,
        line_width=str(line_width_units(line_width_mm)),
        treat_as_char=treat_as_char,
    )
    return self._insert_shape_element(
        el, run_attributes=run_attributes, char_pr_id_ref=char_pr_id_ref,
    )


def _paragraph_add_rectangle(
    self: "HwpxOxmlParagraph",
    width: int = 14400,
    height: int = 7200,
    *,
    ratio: int = 0,
    line_color: str = "#000000",
    line_width_mm: float = 0.12,
    fill_color: str | None = None,
    treat_as_char: bool = True,
    run_attributes: dict[str, str] | None = None,
    char_pr_id_ref: str | int | None = None,
    original_size: tuple[int, int] | None = None,
) -> "HwpxOxmlShape":
    """Insert a spec-compliant ``<hp:rect>`` drawing shape.

    Dimensions are in HWPUNIT, *line_width_mm* in mm (as for ``add_line``).  *ratio* controls corner
    roundness (0 = sharp, 50 = semicircle).  *original_size* ``(w, h)`` sets ``orgSz``
    apart from the drawn size (see ``shape_position.build_at_original_size``).
    """
    el = build_at_original_size(
        _create_rectangle_element, width, height, original_size,
        ids=self.section._ids,
        ratio=ratio,
        line_color=line_color,
        line_width=str(line_width_units(line_width_mm)),
        fill_color=fill_color,
        treat_as_char=treat_as_char,
    )
    return self._insert_shape_element(
        el, run_attributes=run_attributes, char_pr_id_ref=char_pr_id_ref,
    )


def _paragraph_add_ellipse(
    self: "HwpxOxmlParagraph",
    width: int = 14400,
    height: int = 7200,
    *,
    line_color: str = "#000000",
    line_width_mm: float = 0.12,
    fill_color: str | None = None,
    treat_as_char: bool = True,
    run_attributes: dict[str, str] | None = None,
    char_pr_id_ref: str | int | None = None,
    original_size: tuple[int, int] | None = None,
) -> "HwpxOxmlShape":
    """Insert a spec-compliant ``<hp:ellipse>`` drawing shape.

    Dimensions are in HWPUNIT, *line_width_mm* in mm.  *original_size* is as for ``add_rectangle``.
    """
    el = build_at_original_size(
        _create_ellipse_element, width, height, original_size,
        ids=self.section._ids,
        line_color=line_color,
        line_width=str(line_width_units(line_width_mm)),
        fill_color=fill_color,
        treat_as_char=treat_as_char,
    )
    return self._insert_shape_element(
        el, run_attributes=run_attributes, char_pr_id_ref=char_pr_id_ref,
    )


def _paragraph_add_polygon(
    self: "HwpxOxmlParagraph",
    points: Sequence[tuple[int, int]],
    *,
    line_color: str = "#000000",
    line_width_mm: float = 0.12,
    fill_color: str | None = None,
    treat_as_char: bool = True,
    run_attributes: dict[str, str] | None = None,
    char_pr_id_ref: str | int | None = None,
) -> "HwpxOxmlShape":
    """Insert a spec-compliant ``<hp:polygon>`` drawing shape.

    *points* are HWPUNIT vertex coordinates (3 or more), *line_width_mm* the line's width in mm — see
    :func:`_create_polygon_element` for the local-coordinate-space
    convention Hancom's own output uses.
    """
    el = _create_polygon_element(
        points,
        ids=self.section._ids,
        line_color=line_color,
        line_width=str(line_width_units(line_width_mm)),
        fill_color=fill_color,
        treat_as_char=treat_as_char,
    )
    return self._insert_shape_element(
        el, run_attributes=run_attributes, char_pr_id_ref=char_pr_id_ref,
    )


def _paragraph_add_arc(
    self: "HwpxOxmlParagraph",
    width: int = 14400,
    height: int = 14400,
    *,
    corner: str = "TOP_LEFT",
    arc_type: str = "NORMAL",
    line_color: str = "#000000",
    line_width_mm: float = 0.12,
    fill_color: str | None = None,
    treat_as_char: bool = True,
    run_attributes: dict[str, str] | None = None,
    char_pr_id_ref: str | int | None = None,
) -> "HwpxOxmlShape":
    """Insert a spec-compliant ``<hp:arc>`` drawing shape (quarter-ellipse).

    Dimensions are in HWPUNIT, *line_width_mm* in mm. See :func:`_create_arc_element` for the
    *corner*/*arc_type* contract.
    """
    el = _create_arc_element(
        width, height,
        ids=self.section._ids,
        corner=corner,
        arc_type=arc_type,
        line_color=line_color,
        line_width=str(line_width_units(line_width_mm)),
        fill_color=fill_color,
        treat_as_char=treat_as_char,
    )
    return self._insert_shape_element(
        el, run_attributes=run_attributes, char_pr_id_ref=char_pr_id_ref,
    )


def _paragraph_add_container(
    self: "HwpxOxmlParagraph",
    members: Sequence["ContainerMember"],
    *,
    treat_as_char: bool = True,
    run_attributes: dict[str, str] | None = None,
    char_pr_id_ref: str | int | None = None,
) -> "HwpxOxmlShape":
    """Insert a spec-compliant ``<hp:container>`` grouping *members*.

    Each member keeps the local (x, y) position given to its
    :class:`ContainerMember` constructor — see
    :func:`_create_container_element` for the real-corpus contract
    (member envelope, ``groupLevel``, shared ``id`` convention).
    """
    el = _create_container_element(members, ids=self.section._ids, treat_as_char=treat_as_char)
    shape = self._insert_shape_element(
        el, run_attributes=run_attributes, char_pr_id_ref=char_pr_id_ref,
    )
    _write_member_texts(members, shape.element, self.section)  # in the section now: paragraph ids unique there
    return shape


def _paragraph_shapes(self: "HwpxOxmlParagraph") -> tuple["HwpxOxmlShape", ...]:
    """The drawing shapes embedded in this paragraph, in order."""
    shape_tags = {f"{_HP}line", f"{_HP}rect", f"{_HP}ellipse",
                  f"{_HP}arc", f"{_HP}polygon", f"{_HP}curve",
                  f"{_HP}connectLine", f"{_HP}container"}
    return tuple(
        HwpxOxmlShape(child, self) for run in self._run_elements() for child in run if child.tag in shape_tags
    )


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
) -> tuple["HwpxOxmlParagraph", ...]:
    sublist = container.find(f"{_HP}subList")
    if sublist is None:
        return ()
    return tuple(_wrap_paragraph(p, section) for p in sublist.findall(f"{_HP}p"))


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
    para_pr_id_ref: str | int | None = None,
    style: "int | str | Style | None" = None,
) -> "HwpxOxmlParagraph":
    style_id_ref: str | int | None = None
    if style is not None:  # the style's paragraph and character shapes, unless given
        from .section import style_shape_refs

        style_id_ref, para_pr_id_ref, char_pr_id_ref = style_shape_refs(
            section.document, style, para_pr_id_ref, char_pr_id_ref
        )
    sublist = _ensure_sublist(container, vert_align=vert_align)
    attrs = paragraph_attributes(_paragraph_id(section._ids))
    if para_pr_id_ref is not None:
        attrs["paraPrIDRef"] = str(para_pr_id_ref)
    if style_id_ref is not None:
        attrs["styleIDRef"] = str(style_id_ref)
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
    para_pr_id_ref: str | int | None = None,
) -> "HwpxOxmlParagraph":
    """Clear any existing paragraphs and author a single fresh one."""

    sublist = container.find(f"{_HP}subList")
    if sublist is not None:
        from .note_authoring import note_kinds_in_all, renumber_note_kinds

        gone = list(sublist.findall(f"{_HP}p"))
        note_kinds = note_kinds_in_all(section, gone)  # notes in the text that goes: the rest count again
        for existing in gone:
            sublist.remove(existing)
        renumber_note_kinds(section, note_kinds)
    return _add_sublist_paragraph(
        container, text, section=section, vert_align=vert_align,
        char_pr_id_ref=char_pr_id_ref, para_pr_id_ref=para_pr_id_ref,
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
    def full_size(self) -> bool:
        """Whether the caption spans the object and its margins (``fullSz``)."""

        return self.element.get("fullSz", "0") not in ("0", "false", "False")

    @property
    def width(self) -> int | None:
        value = self.element.get("width")
        return int(value) if value is not None else None

    @property
    def gap(self) -> int:
        return int(self.element.get("gap", _CAPTION_DEFAULT_GAP))

    @property
    def paragraphs(self) -> tuple["HwpxOxmlParagraph", ...]:
        return _sublist_paragraphs(self.element, self.section)

    @property
    def text(self) -> str:
        return "\n".join(paragraph.text or "" for paragraph in self.paragraphs)

    def add_paragraph(
        self,
        text: str = "",
        *,
        style: "int | str | Style | None" = None,
        para_pr_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> "HwpxOxmlParagraph":
        """Append a paragraph holding *text* to the caption and return it. *style* (a name, an id or a
        ``Style``) also gives it that style's paragraph and character shapes unless they are passed."""

        _require_text(text)  # not text: refused before anything is written
        self.section = live_holder(self.element, self.section)  # moved to another section: that one
        paragraph = _add_sublist_paragraph(
            self.element, text, section=self.section, vert_align="TOP",
            char_pr_id_ref=char_pr_id_ref, para_pr_id_ref=para_pr_id_ref, style=style,
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
        """The text box's name. Hancom takes a named text box for a field (``doc.fields.text_boxes``)."""

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
    def paragraphs(self) -> tuple["HwpxOxmlParagraph", ...]:
        return _sublist_paragraphs(self.element, self.section)

    @property
    def text(self) -> str:
        return "\n".join(paragraph.text or "" for paragraph in self.paragraphs)

    def add_paragraph(
        self,
        text: str = "",
        *,
        style: "int | str | Style | None" = None,
        para_pr_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> "HwpxOxmlParagraph":
        """Append a paragraph holding *text* to the text box and return it. *style* (a name, an id or a
        ``Style``) also gives it that style's paragraph and character shapes unless they are passed."""

        _require_text(text)  # not text: refused before anything is written
        self.section = live_holder(self.element, self.section)  # moved to another section: that one
        paragraph = _add_sublist_paragraph(
            self.element, text, section=self.section, vert_align="CENTER",
            char_pr_id_ref=char_pr_id_ref, para_pr_id_ref=para_pr_id_ref, style=style,
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
    normalized_side = validate_caption_side(side)
    gap = validate_caption_gap(gap)  # before anything changes: Hancom keeps a signed 16-bit gap

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
    from .note_authoring import note_kinds_in_document, renumber_note_kinds

    note_kinds = note_kinds_in_document(section, element)  # notes in the caption: the rest count again
    host.remove(element)
    renumber_note_kinds(section, note_kinds)
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
    para_pr_id_ref: str | int | None = None,
    vert_align: str | None = None,
) -> DrawText:
    vert_align = validate_draw_text_vert_align(vert_align)
    element = host.find(f"{_HP}drawText")
    if element is None:
        element = _append_child(host, f"{_HP}drawText", {})
        _reposition_child_before_any(host, element, _DRAW_TEXT_BEFORE_NAMES)

    element.set("name", name)
    element.set("editable", "1" if editable else "0")
    sz = host.find(f"{_HP}sz")
    if sz is not None and sz.get("width"):
        element.set("lastWidth", sz.get("width", ""))
    attributes_in_order(element, ("lastWidth", "name", "editable"))  # as Hancom writes hp:drawText

    _replace_sublist_text(
        element, text, section=section, vert_align=vert_align or "CENTER",
        char_pr_id_ref=char_pr_id_ref, para_pr_id_ref=para_pr_id_ref,
    )
    sublist = element.find(f"{_HP}subList")
    if vert_align is not None and sublist is not None:  # else an existing one keeps its own
        sublist.set("vertAlign", vert_align)

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
    from .note_authoring import note_kinds_in_document, renumber_note_kinds

    note_kinds = note_kinds_in_document(section, element)  # notes in the text that goes: the rest count again
    host.remove(element)
    renumber_note_kinds(section, note_kinds)
    section.mark_dirty()
    return True


class HwpxOxmlShape(SameElement, ObjectPlacement):
    """Wrapper for a drawing shape element (``<hp:line>``, ``<hp:rect>``, ``<hp:ellipse>``, etc.)."""

    if TYPE_CHECKING:
        paragraph: "HwpxOxmlParagraph"
    else:
        paragraph = live_paragraph  # the paragraph holding it now, also after a move

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

    # Lives in ``oxml/shape_position.py``; the same call as ``InlineObject.set_position``.
    set_position = _object_set_position

    @property
    def members(self) -> "tuple[HwpxOxmlShape | HwpxOxmlInlineObject, ...]":
        """A group's (``hp:container``) members in order -- drawing shapes, pictures and groups in it,
        each a model object (a text box's text: ``member.draw_text``); ``()`` for any other shape."""

        if self.shape_type != "container":
            return ()
        names = DRAWING_SHAPE_NAMES | {"pic"}
        return tuple(
            cast("HwpxOxmlShape | HwpxOxmlInlineObject", wrap_object(child, self.paragraph))
            for child in self.element if _element_local_name(child) in names
        )

    def ungroup(self) -> "tuple[HwpxOxmlShape | HwpxOxmlInlineObject, ...]":
        """Take this group (``hp:container``) apart as Hancom does and return its members, now objects of their
        own in this paragraph, in the order they stand there (the last member first, as Hancom puts them).

        Each is drawn where it was in the group: its own matrices are kept (the group's turn and stretch with
        them), its box (``hp:sz``) is the box it is drawn in, and it is placed from the group's frames at the
        group's offsets plus where it starts in the group (centred, by its middle), with the group's text
        wrapping and outer margins, a new ``id`` and the group's place in the drawing order (the first member
        the group's ``zOrder``, the last on top, the objects above moved up). Turned members keep the group's
        angle; members of a flipped group take its flags (their matrices already mirror them). A group inside
        comes out whole, its
        shapes measured from it a level up. This is what Hancom 2024 wrote for groups ungrouped plain,
        stretched, turned 30 and 90 degrees, flipped left-right or up-down (turned 30 too) and holding a group;
        Hancom also hangs a member on the paragraph at whose height it starts, here it stays in this paragraph
        at the same spot.

        Refused with ``shape-ungroup-unsupported`` (``context["reason"]``) before anything changes: a shape
        that is not a group, a group set as a character or placed from the right, bottom, inside or outside, a
        group turned and then stretched (skewed), and one with a
        member turned or flipped on its own. The paragraph
        loses its line layout cache; this group object should not be used after it.
        """

        from .container import _ungroup_refused, ungroup_elements, ungroup_refusal

        if self.shape_type != "container":
            raise _ungroup_refused("it is not a group")
        if _in_group(self.element, self.paragraph.element):
            raise _ungroup_refused("it is a group inside a group: ungroup the outer group first")
        why = ungroup_refusal(self.element)
        if why is not None:
            raise _ungroup_refused(why)
        freed = ungroup_elements(self.element, ids=self.paragraph.section._ids)
        _clear_paragraph_layout_cache(self.paragraph.element)
        self.paragraph.section.mark_dirty()
        return tuple(cast("HwpxOxmlShape | HwpxOxmlInlineObject", wrap_object(element, self.paragraph))
                     for element in freed)

    @property
    def width(self) -> int:
        """The shape's own width as drawn, before it is turned (HWPUNIT) -- the size ``resize`` takes, see
        ``shape_position.own_size``; unturned, the width of ``hp:sz`` (:attr:`box_width`)."""

        return own_size(self.element)[0]

    @property
    def height(self) -> int:
        """The shape's own height as drawn, before it is turned (HWPUNIT); see :attr:`width`."""

        return own_size(self.element)[1]

    @property
    def box_width(self) -> int:
        """The width of the box the shape takes in its paragraph (``hp:sz``, HWPUNIT; read only): a turned
        shape's box is the box around it as turned. Unturned, it is :attr:`width`."""

        return object_size(self.element)[0]

    @property
    def box_height(self) -> int:
        """The height of the box the shape takes in its paragraph (``hp:sz``, HWPUNIT; read only)."""

        return object_size(self.element)[1]

    def resize(self, width: int | None = None, height: int | None = None) -> None:
        """Draw the shape *width* x *height* (HWPUNIT); give one alone to keep the aspect ratio.

        As Hancom 2024 resizes a drawing object: its geometry (``pt0``-``pt3``, ``center``/``ax1``/``ax2``,
        ``startPt``/``endPt`` ...) and original size (``hp:orgSz``) stay, and ``hc:scaMatrix`` draws it at
        the new size (``hp:sz``; ``hp:curSz`` the new size on an axis that differs from ``orgSz``, 0 on one
        that does not). A horizontal or vertical line takes a height or width that way too (its ``orgSz``
        keeps 1 there). A group's members are stretched with it (see ``shape_position.resize_group``).
        *width* x *height* is always the shape's own size: a turned shape or group (flipped or not) is
        turned back, resized and turned again (``shape_position.resize_turned_as_own``), so it stays the
        same shape turned -- not stretched along the page into a parallelogram as Hancom's object
        properties stretch the box around it. A flipped shape or group keeps its mirror about the middle of its
        own size, its ``scaMatrix`` moved by what it gained on the flipped axis, as Hancom resizes one. Refused: a
        flipped line (``shape-flip-unsupported``: Hancom drops its mirror), an object skewed by Hancom's resize of a
        turned one (``shape-rotation-unsupported``), and a member of a group alone
        (``shape-group-member-unsupported``: a member is resized with its group). A size that is not an int
        in ``0 <= value < 2**31`` is ``shape-size-value``. The paragraph loses its line layout cache. Its own
        size again (:attr:`width`, :attr:`height`) changes nothing.
        """
        if keep_ratio(own_size(self.element), width, height) == own_size(self.element):
            return
        refuse_resizing_flipped(self.element)
        if _in_group(self.element, self.paragraph.element):
            raise _group_member_refused("resized", "a member is resized with its whole group: no Hancom-saved "
                                                   "document shows one resized alone")
        angle = self.rotation % 360
        if self.shape_type == "container":
            if angle:
                resize_turned_as_own(self, width, height, lambda w, h: self.resize(w, h), unflip=True)
                return
            width, height = keep_ratio((self.width, self.height), width, height)
            _clear_paragraph_layout_cache(self.paragraph.element)  # its line is as tall as the shape set as a character
            if resize_group(self, width, height):
                return  # a group is drawn at its sz: see shape_position.resize_group
        resize_shape(self, width, height)

    @property
    def line_color(self) -> str | None:
        """The line colour (``hp:lineShape/@color``); ``None`` without one. Setting it changes a line the
        shape has."""

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

    @property
    def line_width_mm(self) -> float | None:
        """The width the shape's line is drawn with, in mm (``hp:lineShape/@width``, read to a hundredth: 33
        HWPUNIT is 0.12); ``None`` without a line. Setting it takes mm as ``add_line(line_width_mm=)`` does
        (0 draws none, ``shape-picture-border-value`` for a negative one) and changes a line the shape has."""

        return line_width_mm_of(self.element)

    @line_width_mm.setter
    def line_width_mm(self, value: float) -> None:
        units = str(line_width_units(value))
        ls = self.element.find(f"{_HP}lineShape")
        if ls is not None and ls.get("width") != units:
            ls.set("width", units)
            self.paragraph.section.mark_dirty()

    @property
    def fill_color(self) -> str | None:
        """Solid fill colour (``hc:winBrush/@faceColor``); ``None`` when the shape is not filled."""

        return fill_color_of(self.element)

    # --- generic attribute access ------------------------------------------

    def set_attribute(self, name: str, value: str | int | None) -> None:
        """Update or remove attribute *name* (read one: ``shape.attributes.get(name)``)."""

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
        full_size: bool = False,
        width: int | None = None,
        gap: int = 850,
        char_pr_id_ref: str | int | None = None,
    ) -> "Caption":
        """Create (or replace the text of) this shape's ``hp:caption``.

        See :meth:`HwpxOxmlInlineObject.set_caption` for the real-corpus
        default rationale (*side*/*full_size*/*gap*).
        """

        _require_text(text)  # not text: refused before anything is written
        return _write_caption(
            self.element, text, section=self.paragraph.section,
            side=side, full_sz=full_size, width=width, gap=gap,
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

    def iter_paragraphs(self, *, where: "Iterable[str] | str | None" = None) -> "Iterator[ParagraphPlace]":
        """Every paragraph inside this shape, in document order, with where it sits: its text box's
        (``"text_box"``), its caption's (``"caption"``), those of a group's members and of tables
        inside (``"cell"``), at any depth. *where* and the :class:`~hwpx.objects.ParagraphPlace`
        values are those of ``doc.text.iter_paragraphs()``."""

        from .._document.text_blocks import object_paragraph_places

        return object_paragraph_places(self, where)

    def set_draw_text(
        self,
        text: str,
        *,
        name: str = "",
        editable: bool = False,
        margin: dict[str, int] | None = None,
        char_pr_id_ref: str | int | None = None,
        para_pr_id_ref: str | int | None = None,
        vertical_alignment: str | None = None,
    ) -> "DrawText":
        """Create (or replace the text of) this shape's ``hp:drawText``.

        *margin* overrides ``hp:textMargin`` (``left``/``right``/``top``/
        ``bottom``, HWPUNIT); defaults to the real-corpus majority value
        (0.1cm/283 all four sides, 90-sample). *name* makes the text box a
        field: Hancom lists a named text box among its fields and fills it
        by name (``doc.fields.text_boxes``, ``doc.fields.fill_text_box()``);
        leave it empty for a plain text box. *para_pr_id_ref* sets
        the text paragraph's ``paraPrIDRef`` (e.g. a centred paraPr), default
        ``0``. *vertical_alignment* sets ``hp:subList/@vertAlign`` (``TOP``/``CENTER``/
        ``BOTTOM``, as a table cell's ``vertical_alignment``); ``None`` gives a new text ``CENTER`` and
        leaves existing text's alignment alone. A bad value refuses before any change with
        ``shape-draw-text-vert-align``.
        """

        _require_text(text)  # not text: refused before anything is written
        return _write_draw_text(
            self.element, text, section=self.paragraph.section,
            name=name, editable=editable, margin=margin,
            char_pr_id_ref=char_pr_id_ref, para_pr_id_ref=para_pr_id_ref,
            vert_align=vertical_alignment,
        )

    def remove_draw_text(self) -> bool:
        """Remove this shape's ``hp:drawText`` if present. Returns whether one was removed."""

        return _remove_draw_text(self.element, self.paragraph.section)

    def __repr__(self) -> str:
        return f"<HwpxOxmlShape type={self.shape_type!r} id={self.inst_id!r}>"

__all__ = [
    "Caption", "ContainerMember", "DrawText", "HwpxOxmlEquation", "HwpxOxmlInlineObject", "HwpxOxmlPicture",
    "HwpxOxmlShape",
]


# Groups live in their own module (this owner file's 1,600-line cap); re-exported for existing imports.
from .container import ContainerMember, _create_container_element, _write_member_texts  # noqa: E402
