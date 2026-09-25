# SPDX-License-Identifier: Apache-2.0
"""Drawing objects of an HWP 5.0 section as OWPML shape elements.

The reading half of :mod:`hwpx.hwp5.shapes`: rectangles, ellipses, arcs,
polygons, lines, curves, connectors, containers, pictures and OLE objects
with their placement, matrices, line, fill and shadow, text boxes, captions
and parameter sets. A Hancom chart, an OLE object whose storage holds the
chart part, becomes the chart with the OLE object as its fallback. Kinds
this module does not convert are reported, never dropped.
"""

from __future__ import annotations

import copy
import dataclasses
import struct

from lxml import etree  # type: ignore[reportAttributeAccessIssue]

from . import bodytext as bt
from . import controls as ct
from . import records as rec
from . import shapes as sh
from .errors import Hwp5Error, damaged
from .header_xml import fill_brush
from .owpml import NS, color, flag, image_effect, q, sub, token, xml_text
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
)
#: The HWP code of each arrow name. Hancom reads FILLED_DIAMOND, FILLED_CIRCLE
#: and FILLED_BOX as NORMAL (its filled arrows are EMPTY_* with headfill or
#: tailfill), and leaves the codes past EMPTY_BOX out of OWPML.
ARROW_CODES: dict[str, int] = {
    **{name: code for code, name in enumerate(ARROW)},
    "FILLED_DIAMOND": 0,
    "FILLED_CIRCLE": 0,
    "FILLED_BOX": 0,
}
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
CURVE_SEGMENT = ("LINE", "CURVE")
CONNECT_TYPE = (
    "STRAIGHT_NOARROW",
    "STRAIGHT_ONEWAY",
    "STRAIGHT_BOTH",
    "STROKE_NOARROW",
    "STROKE_ONEWAY",
    "STROKE_BOTH",
    "ARC_NOARROW",
    "ARC_ONEWAY",
    "ARC_BOTH",
)
#: Text art: the font types by code, and the shapes and alignments in the
#: order of their codes. The text keeps a line break as a visible symbol.
TEXTART_FONT_TYPE = {1: "TTF", 2: "HTF"}
TEXTART_SHAPE = (
    "PARALLELOGRAM",
    "INVERTED_PARALLELOGRAM",
    "INVERTED_UPWARD_CASCADE",
    "INVERTED_DOWNWARD_CASCADE",
    "UPWARD_CASCADE",
    "DOWNWARD_CASCADE",
    "REDUCE_RIGHT",
    "REDUCE_LEFT",
    "ISOSCELES_TRAPEZOID",
    "INVERTED_ISOSCELES_TRAPEZOID",
    "TOP_RIBBON_RECTANGLE",
    "BOTTOM_RIBBON_RECTANGLE",
    "CHEVRON_DOWN",
    "CHEVRON",
    "BOW_TIE",
    "HEXAGON",
    "WAVE1",
    "WAVE2",
    "WAVE3",
    "WAVE4",
    "LEFT_TILT_CYLINDER",
    "RIGHT_TILT_CYLINDER",
    "BOTTOM_WIDE_CYLINDER",
    "TOP_WIDE_CYLINDER",
    "THIN_CURVE_UP1",
    "THIN_CURVE_UP2",
    "THIN_CURVE_DOWN1",
    "THIN_CURVE_DOWN2",
    "INVERSED_FINGERNAIL",
    "FINGERNAIL",
    "GINKO_LEAF1",
    "GINKO_LEAF2",
    "INFLATE_RIGHT",
    "INFLATE_LEFT",
    "INFLATE_UP_CONVEX",
    "INFLATE_BOTTOM_CONVEX",
    "DEFLATE_TOP",
    "DEFLATE_BOTTOM",
    "DEFLATE",
    "INFLATE",
    "INFLATE_TOP",
    "INFLATE_BOTTOM",
    "RECTANGLE",
    "LEFT_CYLINDER",
    "CYLINDER",
    "RIGHT_CYLINDER",
    "CIRCLE",
    "CURVE_DOWN",
    "ARCH_UP",
    "ARCH_DOWN",
    "SINGLE_LINE_CIRCLE1",
    "SINGLE_LINE_CIRCLE2",
    "TRIPLE_LINE_CIRCLE1",
    "TRIPLE_LINE_CIRCLE2",
    "DOUBLE_LINE_CIRCLE",
)
TEXTART_ALIGN = ("LEFT", "RIGHT", "CENTER", "FULL", "TABLE")
TEXTART_BREAKS = {"\r": "\u240d", "\n": "\u240a"}
#: Videos: a file or a web page's tag.
VIDEO_TYPE = ("Local", "Web")
#: OLE objects: the object type (bits 16-21 of the properties) and the draw
#: aspect (bits 0-7) by code; Hancom calls every chart UNKNOWN.
OLE_TYPE = ("UNKNOWN", "EMBEDDED", "LINK", "STATIC", "EQUATION")
DRAW_ASPECT = {1: "CONTENT"}
#: What a chart shares with the OLE object it falls back to.
CHART_ATTRS = ("id", "zOrder", "numberingType", "textWrap", "textFlow", "lock", "dropcapstyle")
CHART_PARTS = ("sz", "pos", "outMargin")
DROPCAP = ("None", "DoubleLine", "TripleLine", "Margin")
#: Item paths in a shape's parameter sets: the first-letter decoration kind
#: (object header) and the hyperlink (shape component).
DROPCAP_PATH = (0x3003, 0x7001)
HYPERLINK_PATH = (0x026F, 0x0265)
ELLIPSE_POINTS = ("center", "ax1", "ax2", "start1", "end1", "start2", "end2")
#: Flags bit of a shape component that becomes ``rotateimage``.
ROTATE_IMAGE = 1 << 19
#: Picture effects: shadow styles, align styles, colour types (Hancom keeps
#: no CMYK) and colour effects by code (Hancom keeps no others).
SHADOW_STYLE = ("OUTSIDE", "INSIDE")
EFFECT_ALIGN = ("TOP_LEFT", "TOP", "TOP_RIGHT", "LEFT", "CENTER", "RIGHT", "BOTTOM_LEFT", "BOTTOM", "BOTTOM_RIGHT")
EFFECT_COLOR_TYPE = {0: "RGB", 2: "SCHEME", 3: "SYSTEM"}
COLOR_EFFECTS = {
    503 + index: name
    for index, name in enumerate(
        (
            "RED", "RED_MOD", "RED_OFF", "GREEN", "GREEN_MOD", "GREEN_OFF", "BLUE", "BLUE_MOD", "BLUE_OFF",
            "HUE", "HUE_MOD", "HUE_OFF", "SAT", "SAT_MOD", "SAT_OFF", "LUM", "LUM_MOD", "LUM_OFF", "SHADE", "TINT",
        )
    )
}


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


def picture_effects(parent: etree._Element, effects: sh.PictureEffects) -> bool:
    """The children of ``hp:effects``; False, with nothing written, when a
    code has no known name."""

    colors = [effect.color for effect in (effects.shadow, effects.glow) if effect is not None]
    aligns = [effect.align for effect in (effects.shadow, effects.reflection) if effect is not None]
    if not all(c.kind in EFFECT_COLOR_TYPE and all(code in COLOR_EFFECTS for code, _ in c.effects) for c in colors):
        return False
    if not all(0 <= align < len(EFFECT_ALIGN) for align in aligns):
        return False
    if effects.shadow is not None and effects.shadow.style >= len(SHADOW_STYLE):
        return False
    n = matrix_number
    if effects.shadow is not None:
        s = effects.shadow
        element = sub(
            parent,
            "hp:shadow",
            (
                ("style", SHADOW_STYLE[s.style]),
                ("alpha", n(s.alpha)),
                ("radius", n(s.radius)),
                ("direction", n(s.direction)),
                ("distance", n(s.distance)),
                ("alignStyle", EFFECT_ALIGN[s.align]),
                ("rotationStyle", s.rotation),
            ),
        )
        sub(element, "hp:skew", (("x", n(s.skew[0])), ("y", n(s.skew[1]))))
        sub(element, "hp:scale", (("x", n(s.scale[0])), ("y", n(s.scale[1]))))
        _effect_color(element, s.color)
    if effects.glow is not None:
        element = sub(parent, "hp:glow", (("alpha", n(effects.glow.alpha)), ("radius", n(effects.glow.radius))))
        _effect_color(element, effects.glow.color)
    if effects.soft_edge is not None:
        sub(parent, "hp:softEdge", (("radius", n(effects.soft_edge)),))
    if effects.reflection is not None:
        r = effects.reflection
        element = sub(
            parent,
            "hp:reflection",
            (
                ("alignStyle", EFFECT_ALIGN[r.align]),
                ("radius", n(r.radius)),
                ("direction", n(r.direction)),
                ("distance", n(r.distance)),
                ("rotationStyle", r.rotation),
                ("fadeDirection", n(r.fade)),
            ),
        )
        sub(element, "hp:skew", (("x", n(r.skew[0])), ("y", n(r.skew[1]))))
        sub(element, "hp:scale", (("x", n(r.scale[0])), ("y", n(r.scale[1]))))
        sub(element, "hp:alpha", (("start", n(r.start[0])), ("end", n(r.end[0]))))
        sub(element, "hp:pos", (("start", n(r.start[1])), ("end", n(r.end[1]))))
    return True


def _effect_color(parent: etree._Element, color: sh.EffectColor) -> None:
    kind = EFFECT_COLOR_TYPE[color.kind]
    element = sub(
        parent,
        "hp:effectsColor",
        (
            ("type", kind),
            ("schemeIdx", color.value if kind == "SCHEME" else -1),
            ("systemIdx", color.value if kind == "SYSTEM" else -1),
            ("presetIdx", -1),
        ),
    )
    if kind == "RGB":
        sub(element, "hp:rgb", (("r", color.value >> 16 & 0xFF), ("g", color.value >> 8 & 0xFF), ("b", color.value & 0xFF)))
    for code, amount in color.effects:
        sub(element, "hp:effect", (("type", COLOR_EFFECTS[code]), ("value", matrix_number(amount))))


def chart_switch(ole: etree._Element, path: str) -> etree._Element:
    """A chart as Hancom writes it: the chart (its part at *path*) for an
    application that reads charts, else the OLE object *ole*."""

    switch = etree.Element(q("hp:switch"))
    case = sub(switch, "hp:case", (("hp:required-namespace", NS["ooxmlchart"]),))
    chart = sub(case, "hp:chart", [(name, ole.get(name, "")) for name in CHART_ATTRS] + [("chartIDRef", path)])
    for name in CHART_PARTS:
        part = ole.find(q(f"hp:{name}"))
        if part is not None:
            chart.append(copy.deepcopy(part))
    sub(switch, "hp:default").append(ole)
    return switch


class ShapeReader:
    """Converts drawing objects; mixed into the section writer, which supplies
    the report, paragraph lists and captions, and the chart part of each OLE
    item that holds a chart."""

    report: ConversionReport
    charts: dict[str, str]

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
                if ps is None or not ps.plain():
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
        chart = self.charts.get(element.get("binaryItemIDRef", "")) if kind == "$ole" else None
        if chart is not None:
            element = chart_switch(element, chart)
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
        ole: sh.OleObject | None = None
        art: sh.TextArt | None = None
        if sc.kind == "$con":
            instance_id = sh.ContainerChildren.decode(sc.rest).instance_id
        elif sc.kind == "$pic":
            picture = sh.Picture.decode(geometry.payload) if geometry is not None else sh.Picture()
            instance_id = picture.instance_id or 0
        elif sc.kind == "$ole":
            if geometry is None:
                raise damaged("OLE object without its record")
            ole = sh.OleObject.decode(geometry.payload)
            instance_id = ole.instance_id or 0
        elif sc.kind == "$vid":
            if geometry is None:
                raise damaged("video without its record")
            # HWP keeps no instance id for a video; Hancom makes one up.
            instance_id = 0
        else:
            style = sh.DrawingStyle.decode(sc.rest)
            instance_id = style.instance_id
        if sc.kind == "$tat":
            if geometry is None:
                raise damaged("text art without its record")
            art = sh.TextArt.decode(geometry.payload)
        attrs += [("href", href), ("groupLevel", sc.group_level), ("instid", instance_id)]
        attrs += self.shape_attrs(sc.kind, geometry) if ole is None else self.ole_attrs(ole)
        if art is not None:
            attrs.append(("text", "".join(TEXTART_BREAKS.get(char, char) for char in art.text)))
        element = sub(parent, f"hp:{name}", attrs)
        self.shape_placement(element, sc)
        if picture is not None:
            self.picture(element, picture)
        if ole is not None:
            sub(element, "hc:extent", (("x", ole.extent[0]), ("y", ole.extent[1])))
            self.line_shape(element, ole.line_color, ole.line_width, ole.line_props, 0, 0)
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
            if art is not None:
                self.text_art(element, art)
        if common is not None:
            if style is not None:
                extra = sh.shadow_margins(
                    style.shadow_type, style.shadow_x, style.shadow_y, common.width, common.height
                )
                margins = tuple(margin - add for margin, add in zip(common.margins, extra))
                common = dataclasses.replace(common, margins=margins)  # type: ignore[arg-type]
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
        if kind == "$col":
            return [("type", token(CONNECT_TYPE, sh.ConnectLine.decode(geometry.payload).kind))]
        if kind == "$pic":
            return [("reverse", 0)]
        if kind == "$vid":
            video = sh.Video.decode(geometry.payload)
            return [
                ("videotype", token(VIDEO_TYPE, video.kind)),
                ("fileIDRef", f"video{video.file}" if video.file else ""),
                ("imageIDRef", f"image{video.image}" if video.image else ""),
                ("tag", video.tag),
            ]
        return []

    def ole_attrs(self, ole: sh.OleObject) -> list[tuple[str, object]]:
        item = f"ole{ole.bin_id}"
        kind, aspect = _bits(ole.props, 16, 6), DRAW_ASPECT.get(_bits(ole.props, 0, 8))
        if kind >= len(OLE_TYPE):
            self.report.skip("ole-object-type")
        if aspect is None:
            self.report.skip("ole-draw-aspect")
        return [
            ("objectType", "UNKNOWN" if item in self.charts else token(OLE_TYPE, kind)),
            ("binaryItemIDRef", item),
            ("hasMoniker", flag(ole.props & 0x100)),
            ("drawAspect", aspect or "CONTENT"),
            ("eqBaseLine", _bits(ole.props, 9, 7)),
        ]

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
        # An end cap or an arrow with no OWPML name is left out, as Hancom leaves it out.
        cap = _bits(props, 6, 4)
        head, tail = _bits(props, 10, 6), _bits(props, 16, 6)
        sub(
            element,
            "hp:lineShape",
            (
                ("color", color(line_color)),
                ("width", _u32(width)),
                ("style", token(LINE_STYLE, _bits(props, 0, 6))),
                *((("endCap", END_CAP[cap]),) if cap < len(END_CAP) else ()),
                *((("headStyle", ARROW[head]),) if head < len(ARROW) else ()),
                *((("tailStyle", ARROW[tail]),) if tail < len(ARROW) else ()),
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
                *image_effect(pic.effect),
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
        effects = sub(element, "hp:effects")
        if pic.effects and (pic.effect_list is None or not picture_effects(effects, pic.effect_list)):
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

    def text_art(self, element: etree._Element, art: sh.TextArt) -> None:
        """The corners of a text art object, then its font, shape, spacing,
        alignment, the text's shadow (HWP keeps no alpha for it) and outline.
        A code with no OWPML name is reported and written as the default."""

        for index, (x, y) in enumerate(art.corners):
            sub(element, f"hc:pt{index}", (("x", x), ("y", y)))
        font_type = TEXTART_FONT_TYPE.get(art.font_type)
        if font_type is None or art.shape >= len(TEXTART_SHAPE) or art.align >= len(TEXTART_ALIGN) or art.shadow_type >= len(SHADOW):
            self.report.skip("textart-code")
        props = sub(
            element,
            "hp:textartPr",
            (
                ("fontName", art.font_name),
                ("fontStyle", art.font_style),
                ("fontType", font_type or "TTF"),
                ("textShape", token(TEXTART_SHAPE, art.shape)),
                ("lineSpacing", art.line_spacing),
                ("charSpacing", art.char_spacing),
                ("align", token(TEXTART_ALIGN, art.align)),
            ),
        )
        sub(
            props,
            "hp:shadow",
            (
                ("type", token(SHADOW, art.shadow_type)),
                ("color", color(art.shadow_color)),
                ("offsetX", art.shadow_x),
                ("offsetY", art.shadow_y),
                ("alpha", 0),
            ),
        )
        if art.outline:
            outline = sub(element, "hp:outline", (("cnt", len(art.outline)),))
            for x, y in art.outline:
                sub(outline, "hc:pt", (("x", x), ("y", y)))

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
        elif kind == "$cur":
            curve = sh.Curve.decode(geometry.payload)
            for segment, (x1, y1), (x2, y2) in zip(curve.segments, curve.points, curve.points[1:]):
                sub(element, "hp:seg", (("type", token(CURVE_SEGMENT, segment)), ("x1", x1), ("y1", y1), ("x2", x2), ("y2", y2)))
        elif kind == "$col":
            connect = sh.ConnectLine.decode(geometry.payload)
            for name, (x, y), subject, index in (
                ("hp:startPt", connect.start, connect.start_subject, connect.start_index),
                ("hp:endPt", connect.end, connect.end_subject, connect.end_index),
            ):
                sub(element, name, (("x", x), ("y", y), ("subjectIDRef", subject), ("subjectIdx", index)))
            if connect.control_points:
                control = sub(element, "hp:controlPoints")
                for x, y, point_kind in connect.control_points:
                    sub(control, "hp:point", (("x", x), ("y", y), ("type", point_kind)))
        for name, (x, y) in points:
            sub(element, name, (("x", x), ("y", y)))
