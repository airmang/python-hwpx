# SPDX-License-Identifier: Apache-2.0
"""Drawing objects of an HWP 5.0 section as OWPML shape elements.

The reading half of :mod:`hwpx.hwp5.shapes`: rectangles, ellipses, arcs,
polygons, lines, containers and pictures with their placement, matrices,
line, fill and shadow, text boxes, captions and parameter sets. Kinds this
module does not convert are reported, never dropped.
"""

from __future__ import annotations

import struct

from lxml import etree  # type: ignore[reportAttributeAccessIssue]

from . import bodytext as bt
from . import controls as ct
from . import records as rec
from . import shapes as sh
from .errors import Hwp5Error, damaged
from .header_xml import IMAGE_EFFECT, fill_brush
from .owpml import color, flag, sub, token, xml_text
from .section_common import ConversionReport, _bits, _u32, list_attrs, lists, object_attrs, object_layout

LINE_STYLE = (
    "NONE",
    "SOLID",
    "DOT",
    "DASH",
    "DASH_DOT",
    "DASH_DOT_DOT",
    "LONG_DASH",
    "CIRCLE",
    "DOUBLE_SLIM",
    "SLIM_THICK",
    "THICK_SLIM",
    "SLIM_THICK_SLIM",
)
END_CAP = ("ROUND", "FLAT")
ARROW = (
    "NORMAL",
    "ARROW",
    "SPEAR",
    "CONCAVE_ARROW",
    "EMPTY_DIAMOND",
    "EMPTY_CIRCLE",
    "EMPTY_BOX",
    "FILLED_DIAMOND",
    "FILLED_CIRCLE",
    "FILLED_BOX",
)
ARROW_SIZE = (
    "SMALL_SMALL",
    "SMALL_MEDIUM",
    "SMALL_LARGE",
    "MEDIUM_SMALL",
    "MEDIUM_MEDIUM",
    "MEDIUM_LARGE",
    "LARGE_SMALL",
    "LARGE_MEDIUM",
    "LARGE_LARGE",
)
OUTLINE_STYLE = ("NORMAL", "OUTER", "INNER")
#: Shadow kinds, spelled as Hancom writes them.
SHADOW = (
    "NONE",
    "PARELLEL_LEFTTOP",
    "PARELLEL_RIGHTTOP",
    "PARELLEL_LEFTBOTTOM",
    "PARELLEL_RIGHTBOTTOM",
    "SHEAR_LEFTTOP",
    "SHEAR_RIGHTTOP",
    "SHEAR_LEFTBOTTOM",
    "SHEAR_RIGHTBOTTOM",
    "PERS_LEFTTOP",
    "PERS_RIGHTTOP",
    "PERS_LEFTBOTTOM",
    "PERS_RIGHTBOTTOM",
    "SCALE_NARROW",
    "SCALE_ENLARGE",
)
ARC_TYPE = ("NORMAL", "PIE", "CHORD")
DROPCAP = ("None", "DoubleLine", "TripleLine", "Margin")
#: Item paths in a shape's parameter sets: the first-letter decoration kind
#: (object header) and the hyperlink (shape component).
DROPCAP_PATH = (0x3003, 0x7001)
HYPERLINK_PATH = (0x026F, 0x0265)
ELLIPSE_POINTS = ("center", "ax1", "ax2", "start1", "end1", "start2", "end2")
#: Flags bit of a shape component that becomes ``rotateimage``.
ROTATE_IMAGE = 1 << 19


def matrix_number(value: float) -> str:
    """A matrix entry the way Hancom prints it: six decimals without trailing
    zeros, ``0`` for negative zero and ``-nan(ind)`` for NaN."""

    if value != value:
        return "-nan(ind)"
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _unescape(text: str) -> str:
    """Drop the backslashes that escape characters in a hyperlink command."""

    out: list[str] = []
    escaped = False
    for char in text:
        if char == "\\" and not escaped:
            escaped = True
            continue
        out.append(char)
        escaped = False
    return "".join(out)


def parameter_set(parent: etree._Element, ps: ct.ParameterSet) -> etree._Element:
    """``hp:parameterset`` with its items; a nested set is an ``hp:listParam``."""

    element = sub(parent, "hp:parameterset", (("cnt", len(ps.items)), ("name", ps.set_id)))
    _parameter_items(element, ps.items)
    return element


def _parameter_items(parent: etree._Element, items: list[ct.ParameterItem]) -> None:
    for item in items:
        if isinstance(item.value, ct.ParameterSet):
            nested = sub(parent, "hp:listParam", (("cnt", len(item.value.items)), ("name", item.item_id)))
            _parameter_items(nested, item.value.items)
        elif isinstance(item.value, str):
            sub(parent, "hp:stringParam", (("name", item.item_id),)).text = xml_text(item.value)
        elif item.kind in ct.PIT_UNSIGNED:
            sub(parent, "hp:unsignedintegerParam", (("name", item.item_id),)).text = str(item.value)
        else:
            sub(parent, "hp:integerParam", (("name", item.item_id),)).text = str(item.value)


class ShapeReader:
    """Converts drawing objects; mixed into the section writer, which supplies
    the report, paragraph lists and captions."""

    report: ConversionReport

    def paragraphs(self, parent: etree._Element, records: list[rec.Record]) -> None:
        raise NotImplementedError

    def caption(self, parent: etree._Element, header: rec.Record, paragraphs: list[rec.Record]) -> None:
        raise NotImplementedError

    def drawing(self, run: etree._Element, ctrl: rec.Record) -> etree._Element | None:
        """A drawing object; shapes this module does not convert are reported."""

        component = next((c for c in ctrl.children if c.tag == rec.SHAPE_COMPONENT), None)
        if component is None or len(component.payload) < 4:
            self.report.skip("control-gso")
            return None
        kind = bt.ctrl_id(struct.unpack_from("<I", component.payload)[0])
        if kind not in sh.SHAPE_ELEMENTS:
            self.report.skip(f"shape-{kind.strip('$') or kind}")
            return None
        sets: list[ct.ParameterSet] = []
        for child in ctrl.children:
            if child.tag == rec.CTRL_DATA:
                ps = ct.ParameterSet.decode(child.payload)
                if ps is None:
                    self.report.skip("shape-data")
                else:
                    sets.append(ps)
        # Build detached so a damaged component leaves nothing half written.
        holder = etree.Element("holder")
        try:
            element = self.shape(holder, component, ct.ObjectCommon.decode(ctrl.payload))
            for ps in sets:
                dropcap = ps.find(*DROPCAP_PATH)
                if isinstance(dropcap, int):
                    element.set("dropcapstyle", token(DROPCAP, dropcap))
            # A caption is the paragraph list of the object header itself.
            for header, paragraphs in lists(ctrl)[:1]:
                self.caption(element, header, paragraphs)
            for ps in sets:
                parameter_set(element, ps)
        except Hwp5Error:
            self.report.skip(f"shape-{kind.strip('$')}-damaged")
            return None
        run.append(element)
        return element

    def shape(self, parent: etree._Element, record: rec.Record, common: ct.ObjectCommon | None) -> etree._Element:
        """One shape from its component record: ``common`` is the object header
        of a top-level shape and None for a shape inside a container."""

        sc = sh.ShapeComponent.decode(record.payload, top=common is not None)
        name = sh.SHAPE_ELEMENTS.get(sc.kind)
        if name is None:
            raise damaged(f"unexpected shape kind {sc.kind!r}")
        if common is not None:
            attrs = object_attrs(common)
        else:
            attrs = [
                ("id", 0),
                ("zOrder", 0),
                ("numberingType", "NONE"),
                ("textWrap", "TOP_AND_BOTTOM"),
                ("textFlow", "BOTH_SIDES"),
                ("lock", 0),
                ("dropcapstyle", "None"),
            ]
        tag = sh.GEOMETRY_TAGS.get(sc.kind)
        geometry = next((c for c in record.children if c.tag == tag), None)
        href = ""
        for child in record.children:
            if child.tag == rec.CTRL_DATA:
                ps = ct.ParameterSet.decode(child.payload)
                link = ps.find(*HYPERLINK_PATH) if ps is not None else None
                if isinstance(link, str):
                    href = _unescape(link)
                else:
                    self.report.skip("shape-data")
        style: sh.DrawingStyle | None = None
        picture: sh.Picture | None = None
        if sc.kind == "$con":
            instance_id = sh.ContainerChildren.decode(sc.rest).instance_id
        elif sc.kind == "$pic":
            picture = sh.Picture.decode(geometry.payload) if geometry is not None else sh.Picture()
            instance_id = picture.instance_id or 0
        else:
            style = sh.DrawingStyle.decode(sc.rest)
            instance_id = style.instance_id
        attrs += [("href", href), ("groupLevel", sc.group_level), ("instid", instance_id)]
        attrs += self.shape_attrs(sc.kind, geometry)
        element = sub(parent, f"hp:{name}", attrs)
        self.shape_placement(element, sc)
        if picture is not None:
            self.picture(element, picture)
        if sc.kind == "$con":
            for child in record.children:
                if child.tag != rec.SHAPE_COMPONENT or len(child.payload) < 4:
                    continue
                child_kind = bt.ctrl_id(struct.unpack_from("<I", child.payload)[0])
                if child_kind in sh.SHAPE_ELEMENTS:
                    self.shape(element, child, None)
                else:
                    self.report.skip(f"shape-{child_kind.strip('$') or child_kind}")
        elif style is not None:
            self.shape_style(element, style)
            for header, paragraphs in lists(record)[:1]:
                self.text_box(element, header, paragraphs)
            self.shape_geometry(element, sc.kind, geometry)
        if common is not None:
            object_layout(element, common)
            if common.description:
                sub(element, "hp:shapeComment").text = xml_text(common.description)
        return element

    @staticmethod
    def shape_attrs(kind: str, geometry: rec.Record | None) -> list[tuple[str, object]]:
        if geometry is None:
            return []
        if kind == "$rec":
            return [("ratio", sh.Rectangle.decode(geometry.payload).ratio)]
        if kind == "$ell":
            props = sh.Ellipse.decode(geometry.payload).props
            return [
                ("intervalDirty", flag(props & 0x1)),
                ("hasArcPr", flag(props & 0x2)),
                ("arcType", token(ARC_TYPE, _bits(props, 2, 8))),
            ]
        if kind == "$arc":
            return [("type", token(ARC_TYPE, sh.Arc.decode(geometry.payload).kind))]
        if kind == "$lin":
            return [("isReverseHV", flag(sh.Line.decode(geometry.payload).reverse))]
        if kind == "$pic":
            return [("reverse", 0)]
        return []

    @staticmethod
    def shape_placement(element: etree._Element, sc: sh.ShapeComponent) -> None:
        """Offset in the group, sizes, flip, rotation and the transformation matrices."""

        sub(element, "hp:offset", (("x", _u32(sc.x)), ("y", _u32(sc.y))))
        sub(element, "hp:orgSz", (("width", sc.org_width), ("height", sc.org_height)))
        # Hancom writes 0 for a current size that equals the original one.
        width = 0 if sc.cur_width == sc.org_width else sc.cur_width
        height = 0 if sc.cur_height == sc.org_height else sc.cur_height
        sub(element, "hp:curSz", (("width", width), ("height", height)))
        sub(element, "hp:flip", (("horizontal", flag(sc.flags & 0x1)), ("vertical", flag(sc.flags & 0x2))))
        sub(
            element,
            "hp:rotationInfo",
            (
                ("angle", sc.angle),
                ("centerX", sc.center_x),
                ("centerY", sc.center_y),
                ("rotateimage", flag(sc.flags & ROTATE_IMAGE)),
            ),
        )
        info = sub(element, "hp:renderingInfo")
        for index, matrix in enumerate(sc.matrices):
            name = "hc:transMatrix" if index == 0 else ("hc:scaMatrix" if index % 2 else "hc:rotMatrix")
            sub(info, name, [(f"e{i + 1}", matrix_number(v)) for i, v in enumerate(matrix)])

    @staticmethod
    def line_shape(element: etree._Element, line_color: int, width: int, props: int, outline: int, alpha: int) -> None:
        sub(
            element,
            "hp:lineShape",
            (
                ("color", color(line_color)),
                ("width", _u32(width)),
                ("style", token(LINE_STYLE, _bits(props, 0, 6))),
                ("endCap", token(END_CAP, _bits(props, 6, 4))),
                ("headStyle", token(ARROW, _bits(props, 10, 6))),
                ("tailStyle", token(ARROW, _bits(props, 16, 6))),
                ("headfill", flag(props & (1 << 30))),
                ("tailfill", flag(props & (1 << 31))),
                ("headSz", token(ARROW_SIZE, _bits(props, 22, 4))),
                ("tailSz", token(ARROW_SIZE, _bits(props, 26, 4))),
                ("outlineStyle", token(OUTLINE_STYLE, outline)),
                ("alpha", alpha),
            ),
        )

    def picture(self, element: etree._Element, pic: sh.Picture) -> None:
        """The image, its border (when it has one), corners, crop box, margins and size."""

        sub(
            element,
            "hc:img",
            (
                ("binaryItemIDRef", f"image{pic.bin_id}" if pic.bin_id else ""),
                ("bright", pic.bright),
                ("contrast", pic.contrast),
                ("effect", token(IMAGE_EFFECT, pic.effect)),
                ("alpha", pic.alpha or 0),
            ),
        )
        if _bits(pic.line_props, 0, 6):
            self.line_shape(element, pic.line_color, pic.line_width, pic.line_props, 0, 0)
        corners = sub(element, "hp:imgRect")
        for index, (x, y) in enumerate(pic.corners):
            sub(corners, f"hc:pt{index}", (("x", x), ("y", y)))
        left, top, right, bottom = pic.crop
        sub(element, "hp:imgClip", (("left", left), ("right", right), ("top", top), ("bottom", bottom)))
        left, right, top, bottom = pic.margins
        sub(element, "hp:inMargin", (("left", left), ("right", right), ("top", top), ("bottom", bottom)))
        width, height = pic.dim or (0, 0)
        sub(element, "hp:imgDim", (("dimwidth", width), ("dimheight", height)))
        sub(element, "hp:effects")
        if pic.effects:
            self.report.skip("picture-effects")

    def shape_style(self, element: etree._Element, style: sh.DrawingStyle) -> None:
        self.line_shape(element, style.line_color, style.line_width, style.line_props, style.outline, style.line_alpha)
        fill_brush(element, style.fill)
        sub(
            element,
            "hp:shadow",
            (
                ("type", token(SHADOW, style.shadow_type)),
                ("color", color(style.shadow_color)),
                ("offsetX", style.shadow_x),
                ("offsetY", style.shadow_y),
                ("alpha", style.shadow_alpha),
            ),
        )

    def text_box(self, element: etree._Element, header: rec.Record, paragraphs: list[rec.Record]) -> None:
        box = sh.TextBox.decode(header.payload)
        draw_text = sub(
            element,
            "hp:drawText",
            (("lastWidth", box.last_width), ("name", box.name or ""), ("editable", flag((box.editable or 0) & 0x1))),
        )
        sub_list = sub(draw_text, "hp:subList", list_attrs(box.props))
        self.paragraphs(sub_list, paragraphs)
        left, right, top, bottom = box.margins
        sub(draw_text, "hp:textMargin", (("left", left), ("right", right), ("top", top), ("bottom", bottom)))

    @staticmethod
    def shape_geometry(element: etree._Element, kind: str, geometry: rec.Record | None) -> None:
        if geometry is None:
            return
        points: list[tuple[str, tuple[int, int]]] = []
        if kind == "$rec":
            points = [(f"hc:pt{i}", p) for i, p in enumerate(sh.Rectangle.decode(geometry.payload).corners)]
        elif kind == "$ell":
            points = [(f"hc:{n}", p) for n, p in zip(ELLIPSE_POINTS, sh.Ellipse.decode(geometry.payload).points)]
        elif kind == "$arc":
            points = [(f"hc:{n}", p) for n, p in zip(ELLIPSE_POINTS, sh.Arc.decode(geometry.payload).points)]
        elif kind == "$pol":
            points = [("hc:pt", p) for p in sh.Polygon.decode(geometry.payload).points]
        elif kind == "$lin":
            line = sh.Line.decode(geometry.payload)
            points = [("hc:startPt", line.start), ("hc:endPt", line.end)]
        for name, (x, y) in points:
            sub(element, name, (("x", x), ("y", y)))
