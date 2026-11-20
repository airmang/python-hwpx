# SPDX-License-Identifier: Apache-2.0
"""Floating-shape reference frames, shape-text vertical alignment, a new
shape's original size (``hp:orgSz``) apart from its current size, and a
group resized the way Hancom resizes one.

``HwpxOxmlShape.set_position`` is attached to the class in ``objects.py`` as a
plain class attribute, the same escape valve ``dutmal_compose.py`` uses:
``objects.py``'s owner file sits at its 1600-line modularization cap (1583
before this module existed).

The vocabularies are the OWPML enumerations in the bundled schema,
``DevDoc/OWPML SCHEMA/ParaList XML schema.xml``: the ``pos`` element of
``AbstractShapeObjectType`` (``vertRelTo``/``horzRelTo``/``vertAlign``/
``horzAlign``) and ``ParaListType/@vertAlign`` for ``hp:subList``. Note the
schema gives ``vertRelTo`` no ``COLUMN`` — only ``horzRelTo`` has one.

A shape Hancom has resized keeps its geometry in ``orgSz`` space and scales
it with ``hc:scaMatrix``: in the corpus (``error__20240305__2022.hwpx``,
``error__20250808__…_분석_및_전망.hwpx``) a rect's ``pt2`` and an ellipse's
``ax2`` sit at ``orgSz``, ``curSz`` equals ``sz``, ``scaMatrix`` ``e1``/``e5``
are ``curSz/orgSz`` per axis, and ``rotationInfo``'s centre is half of
``curSz``. :func:`build_at_original_size` writes that same layout.

A group (``hp:container``) is drawn at its ``sz`` whatever its members hold;
:func:`resize_group` writes the rest of it as Hancom saves a resized group.

A new picture's checks live here too, with its effects (``hp:effects``): Hancom saves a shadow or glow ``alpha``
past 0..1 as the bound, a shadow ``direction`` as itself modulo 360 and an unknown shadow ``style`` as ``OUTSIDE``,
and draws a negative radius as 0, so those values are refused. The direction runs clockwise on the page from the
right (0 right, 90 below, 180 left, 270 above). An effect takes room: Hancom lays a picture out as large as it and
its outer shadow or glow together (a glow ``radius`` on each side; an outer shadow offset by ``distance`` in its
direction and spread by ``blur``), so a picture set as a character makes its line that much taller. A soft edge
takes no room; a reflection about its ``size`` of the picture's height and its ``distance`` below it.
"""

from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from ..errors import HwpxValueError
from ._document_primitives import _HC, _HP
from .color import normalize_color

if TYPE_CHECKING:
    from ._document_primitives import IdSource
    import xml.etree.ElementTree as ET

    from ..objects.results import CellMargins, ObjectPosition
    from .objects import HwpxOxmlShape
    from .paragraph import HwpxOxmlParagraph
    from .section import HwpxOxmlSection

POS_VERT_REL_TO = ("PAPER", "PAGE", "PARA")
POS_HORZ_REL_TO = ("PAPER", "PAGE", "COLUMN", "PARA")
POS_VERT_ALIGN = ("TOP", "CENTER", "BOTTOM", "INSIDE", "OUTSIDE")
POS_HORZ_ALIGN = ("LEFT", "CENTER", "RIGHT", "INSIDE", "OUTSIDE")
SUBLIST_VERT_ALIGN = ("TOP", "CENTER", "BOTTOM")
#: ``hp:caption/@side`` 어휘(스키마 기본값은 LEFT). 실코퍼스 15건 전수는
#: TOP 14 · BOTTOM 1 — LEFT/RIGHT 관측 0(테두리 옆 캡션은 실무에서 안 쓴다).
CAPTION_SIDES = frozenset({"LEFT", "RIGHT", "TOP", "BOTTOM"})
#: ``hc:img/@effect`` values Hancom keeps and draws (as they are, in grey, in black and white); it saves any other
#: value as ``REAL_PIC``.
PICTURE_EFFECTS = ("REAL_PIC", "GRAY_SCALE", "BLACK_WHITE")
#: ``numberingType`` values (the schema's four; the 250 Hancom 2024 conversions write each of them).
NUMBERING_TYPES = ("NONE", "PICTURE", "TABLE", "EQUATION")


def _require_member(
    value: object, allowed: tuple[str, ...], *, argument: str, code: str
) -> str:
    """Return *value* if it is exactly one of *allowed*, else refuse."""

    if isinstance(value, str) and value in allowed:
        return value
    raise HwpxValueError(
        f"{argument} must be one of {', '.join(allowed)}; got {value!r}",
        code=code,
        context={"argument": argument, "requested": value, "allowed": list(allowed)},
        suggestion=f"{argument} 는 {list(allowed)} 중 하나여야 합니다(대문자, 정확히 일치).",
    )


def validate_picture_align(alignment: object) -> str | None:
    """A new picture's *alignment* (a str or an :class:`~hwpx.objects.Alignment`) as its ``hp:pos@horzAlign``, any
    case (``"left"`` is ``LEFT``); ``None`` when it is not given. Hancom reads a value outside
    :data:`POS_HORZ_ALIGN` as ``LEFT``, so one is refused."""

    if alignment is None or alignment == "":
        return None
    return _require_member(str(alignment).upper() if isinstance(alignment, str) else alignment, POS_HORZ_ALIGN,
                           argument="alignment", code="shape-position-frame")


def validate_picture_image(brightness: object, contrast: object, effect: object,
                           alpha: object) -> tuple[int, int, str, int]:
    """A new picture's image adjustments as ``hc:img``'s ``bright``, ``contrast``, ``effect`` and ``alpha``.

    Hancom draws *brightness* and *contrast* from -100 to 100: it keeps a value past them as written but draws a
    brightness past them as at the bound and a contrast past them with its colours turned over or grey. *effect*
    is one of :data:`PICTURE_EFFECTS`, any case. *alpha* is the picture's transparency, from 0 (opaque) to 255
    (not drawn); Hancom saves 256 as 0."""

    for argument, value, low, high in (("brightness", brightness, -100, 100), ("contrast", contrast, -100, 100),
                                       ("alpha", alpha, 0, 255)):
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise HwpxValueError(
                f"{argument} must be an int in {low} <= {argument} <= {high}; got {value!r}",
                code="shape-picture-image-value",
                context={"argument": argument, "value": repr(value)},
                suggestion=f"Pass {argument} from {low} to {high}.",
            )
    name = _require_member(effect.upper() if isinstance(effect, str) else effect, PICTURE_EFFECTS,
                           argument="effect", code="shape-picture-image-value")
    return brightness, contrast, name, alpha  # type: ignore[return-value]


def validate_picture_border(line_width: object) -> int:
    """A new picture's border width (``hp:lineShape/@width``, HWPUNIT): an int in ``0 <= value < 2**31``."""

    if isinstance(line_width, bool) or not isinstance(line_width, int) or not 0 <= line_width < 2**31:
        raise HwpxValueError(
            f"line_width must be an int in 0 <= line_width < 2**31 (HWPUNIT); got {line_width!r}",
            code="shape-picture-border-value",
            context={"argument": "line_width", "value": repr(line_width)},
            suggestion="Pass the border width in HWP units (33 is about 0.12 mm).",
        )
    return line_width


def validate_picture_crop(crop: object, width: int, height: int) -> tuple[int, int, int, int]:
    """A new picture's *crop* as how much to cut from its left, top, right and bottom (HWPUNIT, on the picture
    *width* x *height* before cutting); ``None`` cuts nothing. Ints from 0, leaving some of the picture in each
    direction."""

    if crop is None:
        return 0, 0, 0, 0
    sides = tuple(crop) if isinstance(crop, (tuple, list)) else ()
    if (len(sides) != 4 or any(isinstance(side, bool) or not isinstance(side, int) or side < 0 for side in sides)
            or sides[0] + sides[2] >= width or sides[1] + sides[3] >= height):
        raise HwpxValueError(
            f"crop must be four ints (left, top, right, bottom) from 0 that leave some of the {width} x {height} "
            f"picture; got {crop!r}",
            code="shape-picture-crop-value",
            context={"argument": "crop", "value": repr(crop), "width": width, "height": height},
            suggestion="Pass how much to cut from each side in HWP units, less in all than the picture's width and "
                       "height.",
        )
    return sides  # type: ignore[return-value]


def validate_draw_text_vert_align(vertical_alignment: str | None, *, argument: str = "vertical_alignment") -> str | None:
    """Check ``set_draw_text``'s *vertical_alignment* (``hp:subList/@vertAlign``)."""

    if vertical_alignment is None:
        return None
    return _require_member(
        vertical_alignment, SUBLIST_VERT_ALIGN, argument=argument, code="shape-draw-text-vert-align"
    )


def validate_caption_side(side: str) -> str:
    """A caption's *side* as ``hp:caption/@side``: any case, surrounding spaces dropped."""

    normalized_side = side.strip().upper()
    if normalized_side not in CAPTION_SIDES:
        raise HwpxValueError(
            f"unsupported caption side {side!r}",
            code="shape-caption-side-invalid",
            context={"requested": side, "available": sorted(CAPTION_SIDES)},
            suggestion=f"side 는 {sorted(CAPTION_SIDES)} 중 하나여야 합니다.",
        )
    return normalized_side


def validate_caption_gap(gap: object) -> int:
    """A caption's *gap* from its object (HWPUNIT), checked to be an int in ``-32768 <= gap <= 32767``: Hancom
    keeps it as a signed 16-bit number, reading 32768 as -32768 and 65536 as 0."""

    if isinstance(gap, bool) or not isinstance(gap, int) or not -(2**15) <= gap < 2**15:
        raise HwpxValueError(
            f"gap must be an int in -32768 <= gap <= 32767 (HWPUNIT); got {gap!r}",
            code="shape-caption-gap-value",
            context={"value": repr(gap)},
            suggestion="Pass the caption's distance from its object in HWP units, e.g. 850 (3 mm).",
        )
    return gap


#: ``textWrap`` of an object (``AbstractShapeObjectType``): how the body text goes around it.
TEXT_WRAPS = ("SQUARE", "TIGHT", "THROUGH", "TOP_AND_BOTTOM", "BEHIND_TEXT", "IN_FRONT_OF_TEXT")


def _object_set_position(
    self: Any,
    *,
    treat_as_char: bool | None = None,
    text_wrap: str | None = None,
    horizontal_offset: int | None = None,
    vertical_offset: int | None = None,
    horizontal_relative_to: str | None = None,
    vertical_relative_to: str | None = None,
    horizontal_alignment: str | None = None,
    vertical_alignment: str | None = None,
    flow_with_text: bool | None = None,
    allow_overlap: bool | None = None,
) -> None:
    """Place an object (equation, picture, OLE, text art...): as a character in the line or
    floating, how the text goes around it, and where it floats.

    *treat_as_char* writes ``hp:pos/@treatAsChar`` (``True``: one character in the line;
    ``False``: floating). *text_wrap* writes the object's ``textWrap``, one of
    :data:`TEXT_WRAPS` (``TOP_AND_BOTTOM``: text above and below only; ``SQUARE``: around its
    box; ``BEHIND_TEXT``/``IN_FRONT_OF_TEXT``: under or over the text). The offsets (HWP units,
    signed 32-bit) count from the frames: *horizontal_relative_to* (``hp:pos/@horzRelTo``) is one
    of :data:`POS_HORZ_REL_TO` and *vertical_relative_to* (``vertRelTo``) one of
    :data:`POS_VERT_REL_TO`; *horizontal_alignment* (``horzAlign``) is one of
    :data:`POS_HORZ_ALIGN` and *vertical_alignment* (``vertAlign``) one of :data:`POS_VERT_ALIGN`,
    the alignment in the frame. *flow_with_text* writes ``hp:pos/@flowWithText`` (``True``: kept inside
    the page body, Hancom's 쪽 영역 안으로 제한) and *allow_overlap* ``hp:pos/@allowOverlap`` (``True``: it
    may overlap other objects, 서로 겹침 허용), each ``"1"`` or ``"0"`` as Hancom writes them; Hancom's
    saved documents hold both settings in every combination (of the floating objects placed from a
    paragraph and column in its body, 21 kept in the page and overlapping, 173 kept in it and not).
    ``None`` leaves a setting as it is. Offsets are only for a floating
    object: given while it stays a character they are refused (``shape-position-unsupported``); a
    value outside its vocabulary is ``shape-position-frame``. Everything is checked before anything
    changes; the paragraph loses its line layout cache.
    """

    position = self.element.find(f"{_HP}pos")
    if position is None:
        raise HwpxValueError(
            "the object has no hp:pos to place it by (position editing needs a floating or inline object with one)",
            code="shape-position-unsupported",
            suggestion="Only objects that carry hp:pos (equations, pictures, shapes, OLE) can be placed.",
        )
    for value in (horizontal_offset, vertical_offset):
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)
                                  or not -(2**31) <= value < 2**31):
            raise HwpxValueError(
                "object offsets must be signed 32-bit integer HWP units",
                code="shape-position-value",
                suggestion="Pass integer offsets in HWP units (1 mm = 283.465).",
            )
    floating = position.get("treatAsChar") in {"0", "false", "False"} if treat_as_char is None else not treat_as_char
    if not floating and (horizontal_offset is not None or vertical_offset is not None):
        raise HwpxValueError(
            "an object set as a character has no offsets: only a floating object takes them",
            code="shape-position-unsupported",
            suggestion="Pass treat_as_char=False to float it, then its offsets apply.",
        )
    attributes: dict[str, str] = {}
    if text_wrap is not None:
        attributes["textWrap"] = _require_member(text_wrap, TEXT_WRAPS, argument="text_wrap",
                                                 code="shape-position-frame")
    frames: dict[str, str] = {}
    for argument, attribute, requested, allowed in (
        ("vertical_relative_to", "vertRelTo", vertical_relative_to, POS_VERT_REL_TO),
        ("horizontal_relative_to", "horzRelTo", horizontal_relative_to, POS_HORZ_REL_TO),
        ("vertical_alignment", "vertAlign", vertical_alignment, POS_VERT_ALIGN),
        ("horizontal_alignment", "horzAlign", horizontal_alignment, POS_HORZ_ALIGN),
    ):
        if requested is not None:
            frames[attribute] = _require_member(requested, allowed, argument=argument, code="shape-position-frame")
    if treat_as_char is not None:
        frames["treatAsChar"] = "1" if treat_as_char else "0"
    for argument, attribute, flag in (("flow_with_text", "flowWithText", flow_with_text),
                                      ("allow_overlap", "allowOverlap", allow_overlap)):
        if flag is not None:
            if not isinstance(flag, bool):
                raise HwpxValueError(
                    f"{argument} must be True or False (None leaves it as it is); got {flag!r}",
                    code="shape-position-value",
                    context={"argument": argument, "value": repr(flag)},
                    suggestion=f"Pass {argument}=True or {argument}=False.",
                )
            frames[attribute] = "1" if flag else "0"
    for name, offset in (("horzOffset", horizontal_offset), ("vertOffset", vertical_offset)):
        if offset is not None:
            frames[name] = str(offset & 0xFFFFFFFF)  # a negative one in its unsigned 32-bit form, as Hancom writes it
    for name, setting in attributes.items():
        self.element.set(name, setting)
    for name, setting in frames.items():
        position.set(name, setting)
    if attributes or frames:
        from ._document_primitives import _clear_paragraph_layout_cache

        _clear_paragraph_layout_cache(self.paragraph.element)
        self.paragraph.section.mark_dirty()


_FALSE_FLAGS = frozenset({"0", "false", "False"})

#: The boxes (:func:`paragraph_box`) whose new floating objects :func:`fit_new_floating_object` places as
#: Hancom documents place floating objects there.
_FITTED_BOXES = frozenset({"cell", "text_box", "note", "header_footer"})


def fit_new_floating_object(element: Any, paragraph: Any) -> None:
    """Give a floating object just made with the default placement the placement Hancom documents give a
    floating object in a table cell, a text box, a note or a header or footer, when *paragraph* is in one.

    The default (``vertRelTo="PARA"``, ``horzRelTo="COLUMN"``, ``flowWithText="0"``, ``allowOverlap="1"``)
    is the body's; Hancom draws such a picture in a cell outside the table, at the body's top left, and
    pushes the table aside. In the public documents (1,304) the floating objects in cells, text boxes and
    notes are measured from their paragraph and kept in its area: of 634 in cells 343 are PARA/PARA with
    ``flowWithText="1"``, 257 PARA/COLUMN/1, 33 PARA/PARA/0, 1 PARA/COLUMN/0; all 40 in notes and both in
    text boxes keep ``flowWithText="1"``; most with ``allowOverlap="0"``. So the object becomes measured
    across from its paragraph too (``horzRelTo="PARA"``, the most common in cells, shapes there nearly
    always), kept in the area (``flowWithText="1"``) and not overlapping (``allowOverlap="0"``). An object
    as a character, one in the body, or one measured from the page or paper (its caller placed it so: a
    connector between shapes, a picture with ``pos_overrides``) is left as it is; a connector keeps the
    frames of the shapes it joins. This is how such an object is *made* there; moving or copying one into
    a box follows what Hancom does when it pastes one (:func:`pasted_placement`), and the placement made
    here is left as it is by that.
    """

    position = element.find(f"{_HP}pos")
    if position is None or position.get("treatAsChar") not in _FALSE_FLAGS:
        return
    if position.get("vertRelTo") != "PARA" or position.get("horzRelTo") not in ("PARA", "COLUMN"):
        return
    if paragraph_box(paragraph.element, paragraph.section.element) not in _FITTED_BOXES:
        return
    if str(element.tag).rsplit("}", 1)[-1] != "connectLine":
        position.set("horzRelTo", "PARA")
    position.set("flowWithText", "1")
    position.set("allowOverlap", "0")


#: Object kinds a paragraph's runs hold, by local name. Drawing shapes (``model.Shape``) carry line and
#: fill; the rest are placed objects (``model.InlineObject``). Form controls carry ``hp:pos`` too.
DRAWING_SHAPE_NAMES = frozenset({
    "line", "rect", "ellipse", "arc", "polygon", "curve", "connectLine", "container", "textart",
})
PLACED_OBJECT_NAMES = frozenset({
    "pic", "equation", "chart", "ole", "video", "btn", "radioBtn", "checkBtn", "comboBox", "edit",
    "listBox", "scrollBar",
})


def _number(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _signed_offset(value: str | None) -> int | None:
    """An offset as Hancom stores it (a negative one in its unsigned 32-bit form) back to signed."""

    number = _number(value)
    if number is None:
        return None
    return number - 2**32 if 2**31 <= number < 2**32 else number


def _parent_of(element: Any, scope: Any) -> Any:
    """*element*'s parent: lxml knows it; a plain ElementTree element is looked for under *scope*."""

    getparent = getattr(element, "getparent", None)
    if getparent is not None:
        return getparent()
    for node in scope.iter():
        if any(child is element for child in node):
            return node
    return None


def _group_member_refused(action: str, why: str | None = None) -> HwpxValueError:
    return HwpxValueError(
        f"an object inside a group (hp:container) cannot be {action} on its own" + (f": {why}" if why else ""),
        code="shape-group-member-unsupported",
        context={"action": action, **({"reason": why} if why else {})},
        suggestion="묶음(hp:container) 전체를 다루세요: 묶음의 Shape 에서 remove()·set_position() 등을 부릅니다.",
    )


def _in_group(element: Any, scope: Any) -> bool:
    parent = _parent_of(element, scope)
    return parent is not None and str(parent.tag).rsplit("}", 1)[-1] == "container"


def binary_references(element: Any) -> set[str]:
    """Every binary item reference (``binaryItemIDRef`` and the like) in *element* and below."""

    from ..opc.relationships import BINARY_ITEM_REF_ATTRS

    return {value for node in element.iter() for attribute in BINARY_ITEM_REF_ATTRS
            if (value := node.get(attribute))}


def remove_orphaned_images(section: Any, references: set[str]) -> None:
    """Remove from the package the binary items *references* name that nothing in *section*'s document points
    at any more (see ``hwpx._document.media.remove_orphaned_items``)."""

    if references and section.document is not None:
        from .._document.media import remove_orphaned_items

        remove_orphaned_items(section.document, references)


def object_section(obj: Any) -> "HwpxOxmlSection | None":
    """The section (``hwpx.model.Section``) whose part holds *obj* -- a picture, equation, shape or table, also one
    in a table cell, a text box, a header or footer, a footnote or a memo, all of which the section part holds.
    Its number is ``doc.sections.index(obj.section)``. ``None`` for an object on a master page: that is a part of
    its own, not a section's (which sections use it is ``section.properties``' to say)."""

    from .section import HwpxOxmlSection

    holder = getattr(getattr(obj, "paragraph", None), "section", None)
    return holder if isinstance(holder, HwpxOxmlSection) else None


_Placed = TypeVar("_Placed", bound="ObjectPlacement")


def _offset(self: Any) -> "int | None":
    """Where it stands in its paragraph's text: the number of characters before it, counted as
    ``paragraph.text`` counts (``None`` when it is in no run of a paragraph). It takes no character, so it
    stands after character ``offset - 1`` and before character ``offset``; ``move_to(paragraph,
    offset=obj.offset)`` puts it back where it is."""

    from .text_offsets import placed_offset

    return placed_offset(self)


class ObjectPlacement:
    """Reads and edits every placed object shares: pictures, equations, charts, OLE and drawing shapes.

    Mixed into ``model.InlineObject`` and ``model.Shape``. One value is a property that reads and
    writes (``z_order``, ``rotation``, ``description``); several at once take a ``set_`` method, and
    the read takes the names the method takes (``position`` answers ``set_position``,
    ``out_margins`` ``set_out_margins``).
    """

    element: Any
    paragraph: Any

    section = property(object_section)
    offset = property(_offset)

    @property
    def position(self) -> "ObjectPosition":
        """Where the object sits (:class:`~hwpx.objects.ObjectPosition`): as a character or floating,
        how text goes around it, its frames, alignment and offsets."""

        from ..objects.results import ObjectPosition

        pos = self.element.find(f"{_HP}pos")
        attrs: dict[str, str] = dict(pos.attrib) if pos is not None else {}
        flag = (lambda name: None if name not in attrs else attrs[name] not in _FALSE_FLAGS)
        return ObjectPosition(
            treat_as_char=bool(flag("treatAsChar")),
            text_wrap=self.element.get("textWrap"),
            text_flow=self.element.get("textFlow"),
            horizontal_relative_to=attrs.get("horzRelTo"),
            vertical_relative_to=attrs.get("vertRelTo"),
            horizontal_alignment=attrs.get("horzAlign"),
            vertical_alignment=attrs.get("vertAlign"),
            horizontal_offset=_signed_offset(attrs.get("horzOffset")),
            vertical_offset=_signed_offset(attrs.get("vertOffset")),
            flow_with_text=flag("flowWithText"),
            allow_overlap=flag("allowOverlap"),
            has_position=pos is not None,
            treat_as_char_written="treatAsChar" in attrs,
        )

    @property
    def z_order(self) -> int:
        """The object's ``zOrder``: objects with a higher one are drawn over those with a lower one.

        Setting it takes a signed 32-bit int (``shape-z-order-value``)."""

        return _number(self.element.get("zOrder")) or 0

    @z_order.setter
    def z_order(self, z_order: int) -> None:
        if isinstance(z_order, bool) or not isinstance(z_order, int) or not -(2**31) <= z_order < 2**31:
            raise HwpxValueError(
                f"z_order must be a signed 32-bit int; got {z_order!r}",
                code="shape-z-order-value",
                context={"value": repr(z_order)},
                suggestion="Pass an int: a higher z_order is drawn over a lower one.",
            )
        if self.element.get("zOrder") != str(z_order):
            self.element.set("zOrder", str(z_order))
            self.paragraph.section.mark_dirty()

    @property
    def locked(self) -> bool:
        """Whether the object is locked (``lock``, Hancom's 개체 보호하기): it cannot be selected,
        moved or resized in Hancom. Read only."""

        return (self.element.get("lock") or "").strip() not in _FALSE_FLAGS | {""}

    @property
    def numbering_type(self) -> str:
        """Which caption numbering the object counts in (``numberingType``): ``"PICTURE"``,
        ``"TABLE"``, ``"EQUATION"`` or ``"NONE"`` (the schema default, also when not given).

        Setting it takes one of the four, exactly (else ``shape-numbering-type-value``) and writes
        it as given; Hancom writes any of them on any kind of object (a rectangle counted as a
        picture, a table not counted). The paragraph holding the object loses its line layout cache.
        """

        return self.element.get("numberingType") or "NONE"

    @numbering_type.setter
    def numbering_type(self, value: str) -> None:
        wanted = _require_member(value, NUMBERING_TYPES, argument="numbering_type", code="shape-numbering-type-value")
        if self.element.get("numberingType") != wanted:
            from ._document_primitives import _clear_paragraph_layout_cache

            self.element.set("numberingType", wanted)
            _clear_paragraph_layout_cache(self.paragraph.element)
            self.paragraph.section.mark_dirty()

    @property
    def out_margins(self) -> "CellMargins":
        """The room kept between the object and the text around it (``hp:outMargin``), in HWPUNIT, as
        :class:`~hwpx.objects.CellMargins` (``table.out_margins``'s type); zeros when it has none."""

        from ..objects.results import CellMargins

        own = self.element.find(f"{_HP}outMargin")
        return CellMargins(*((_number(own.get(side)) or 0) if own is not None else 0
                             for side in ("left", "right", "top", "bottom")))

    def set_out_margins(self, *, left: int | None = None, right: int | None = None, top: int | None = None,
                        bottom: int | None = None) -> "CellMargins":
        """Set the object's outer margins (``hp:outMargin``) and return them, as ``table.set_out_margins``
        sets a table's.

        Sides left as ``None`` keep their value. Values are ints in ``0 <= value < 2**31`` (HWPUNIT),
        checked before anything changes (``shape-out-margin-value``). An object set as a character takes
        that much more room in its line, a floating one keeps the text that much further away, so the
        paragraph (and the paragraphs holding it) lose their line layout cache when they change. A member
        of a group has none (``shape-group-member-unsupported``). With no arguments nothing changes.
        """

        from dataclasses import replace

        given = {side: value for side, value in (("left", left), ("right", right), ("top", top),
                                                 ("bottom", bottom)) if value is not None}
        for side, value in given.items():
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 2**31:
                raise HwpxValueError(
                    f"outer margin {side} must be an int in 0 <= value < 2**31 (HWPUNIT); got {value!r}",
                    code="shape-out-margin-value",
                    context={"side": side, "value": repr(value)},
                    suggestion="Pass a non-negative int in HWPUNIT (1 mm = 283.465 HWPUNIT).",
                )
        before = self.out_margins
        if not given:
            return before
        if self.element.find(f"{_HP}pos") is None:
            raise _group_member_refused("given outer margins", "a group member has no place for it: Hancom keeps it on the group (none of 2,068 public members holds one)")
        margins = replace(before, **given)
        own = self.element.find(f"{_HP}outMargin")
        if own is None:
            from ._document_primitives import _append_child, _reposition_child_after_any

            own = _append_child(self.element, f"{_HP}outMargin", {})
            _reposition_child_after_any(self.element, own, ("pos",))
        elif margins == before:
            return before
        for side in ("left", "right", "top", "bottom"):
            own.set(side, str(getattr(margins, side)))
        from ._document_primitives import _clear_paragraph_layout_cache

        _clear_paragraph_layout_cache(self.paragraph.element)
        self.paragraph.section.mark_dirty()
        return margins

    @property
    def rotation(self) -> int:
        """The angle the object is turned by, in degrees clockwise (``hp:rotationInfo/@angle``); 0 when it has none.

        Setting it turns the object that many degrees clockwise about its middle, as Hancom saves a turned
        object. The angle is kept as Hancom keeps it, from 0 to 359 (-30 is 330, 390 is 30). It is the angle from
        the object's unturned form, not added to the angle it has: an object turned 30 degrees and set to 45
        is written as one turned 45 from the start, as Hancom's object dialog writes it. The object keeps its own size (``hp:orgSz``) and the size it is drawn at (``hc:scaMatrix``,
        ``hp:curSz``: a picture after ``resize`` is drawn smaller or larger); its box (``hp:sz``) becomes the
        box around the turned object, the object as drawn is turned about its own middle (``hc:rotMatrix``)
        and moved into that box (``hp:offset``, ``hc:transMatrix``), and ``hp:rotationInfo`` holds the angle
        and the middle of the box -- the relation the turned objects of Hancom-saved documents show,
        stretched or not (see :func:`rotation_base_size`). Hancom computes with the cosine and sine as it
        writes them (six decimals) and moves the box by whole units; so does this. The placement
        (``hp:pos``) stays: the box keeps its top left corner, where Hancom's own turn commands also move
        the object so its middle stays on the page.

        A shape holding text (a text box) turns the same way; Hancom does not turn the text with it but
        lays it out level across the box around the turned shape, so ``hp:drawText/@lastWidth`` becomes
        that box's width and the text's line layout caches go (rectangles and ellipses with text turned
        90 and 30 degrees by Hancom 2024 and saved hold exactly this).

        A group (``hp:container``) turns as a whole, as Hancom turns one: every member is drawn from its
        own matrices, so each member takes the group's turn about the group's middle (its ``hc:rotMatrix``,
        expressed from its own place) and the group's move (``hc:transMatrix`` and ``hp:offset``: its place
        plus the group's), and keeps ``rotationInfo/@angle`` 0; the group's box is the box around its turned
        members (the shapes of a group inside included, not that group's own box) and its ``rotationInfo``
        centre the turned middle. The turn is about the middle of the group's own size (``hp:orgSz``) even
        when the group is resized, in the space its members are drawn in. A shape's ``rotationInfo`` centre
        becomes the middle of its own turned box as drawn (a group inside keeps its centre) and a shape's
        text is laid out across that box's width -- what Hancom 2024's object dialog wrote for groups of
        rectangles, an ellipse, a text box, a line and a polygon, resized or not, with a group inside, turned
        30, 45, 90, 180, 270 and 330 degrees and turned again from 30 to 45. (Its 90-degree command leaves
        the members' centres as they are; the dialog's form is written.)

        A floating object is moved in its frame so the centre it turns about stays where it was on the page, as
        Hancom moves it (:func:`keep_turn_anchor`: placed from the left and top or centred, from a paragraph,
        column, page or the paper; the offset may become negative); turned back to 0 it is back where it was. The
        paragraph it hangs on does not change: Hancom's own turn hangs an object moved up on the paragraph at that
        height (its page layout: ``hancom18`` fc-30, fn-30), which python-hwpx, laying out no pages, does not do.
        Hangul draws an object kept in the page area whose top would be above the line it hangs on from that line's
        top (``hancom16`` ha-30, rotate12 check15 case 4). An object set as a character keeps its place.

        A flipped rectangle, ellipse, polygon, line or group (:attr:`flip_horizontal`, :attr:`flip_vertical`)
        turns too: its ``hc:rotMatrix`` mirrors, then turns it, as Hancom writes a flipped text box turned 45
        degrees and a flipped ellipse, polygon, line or group turned 30; its box is the box around it so.

        Refused with ``shape-rotation-unsupported`` (``context["reason"]`` says why), because no Hancom-saved
        document shows how Hancom writes them: a line drawn 0 high or wide flipped, turned and flipped again;
        another kind of object
        flipped, or one whose ``hp:flip`` its matrices do not follow; an object Hancom's object properties skewed (a
        turned object's box resized there); a group holding a turned or flipped member; and an object without
        ``hp:rotationInfo`` (an equation or chart). A group flipped and then resized turns about the centre it holds,
        and one resized, turned and flipped turns again by what the angle changes about that centre, as Hancom turns
        them (rotate8). One member of a
        group alone is refused with ``shape-group-member-unsupported`` (turn the group), an angle that is not
        an int with ``shape-rotation-value``. 0 turns an object back, a group too. The paragraph loses its line
        layout cache.
        """

        info = self.element.find(f"{_HP}rotationInfo")
        return (_number(info.get("angle")) or 0) if info is not None else 0

    @rotation.setter
    def rotation(self, angle: int) -> None:
        if isinstance(angle, bool) or not isinstance(angle, int):
            raise HwpxValueError(
                f"angle must be an int (whole degrees); got {angle!r}",
                code="shape-rotation-value",
                context={"value": repr(angle)},
                suggestion="Pass the angle in whole degrees clockwise; -30 is 330.",
            )
        angle %= 360  # as Hancom keeps it: turned by -30 degrees it saves 330
        if _in_group(self.element, self.paragraph.element):
            raise _group_member_refused("turned", "a member turns only with its whole group: turn the group "
                                                  "(group.rotation = angle)")
        if _local(self.element) in ("equation", "chart") and angle % 360:
            # Hancom 2024 refuses its 90-degree turn on an equation or a chart and keeps no angle its object
            # dialog is given (objlim evidence eqturn, eqangle, chartturn, chartangle): not a Hancom feature.
            raise _rotation_refused(self.element, "Hancom does not turn an equation or a chart")
        if angle == self.rotation % 360 and self.element.find(f"{_HP}rotationInfo") is not None:
            # Already at that angle: nothing turns. Turning "again" re-derived the place of an object Hancom
            # had saved turned and flipped, and moved it (a flipped group at 330 degrees, by 866 down).
            return
        before = turn_anchor(self.element)
        if str(self.element.tag).rsplit("}", 1)[-1] == "container":
            from .container import turn_group

            turn_group(self.element, angle)  # refuses a group this does not know Hancom's form for
        else:
            flat = flat_line(self.element) or flat_flip_form(self.element)
            if flat is not None:
                turn_flat_line(self.element, angle, flat)
            else:
                width, height = rotation_base_size(self.element)  # refuses what is not known to turn this way
                apply_rotation(self.element, angle, width, height)
        keep_turn_anchor(self.element, before)
        from ._document_primitives import _clear_paragraph_layout_cache

        _clear_paragraph_layout_cache(self.paragraph.element)
        self.paragraph.section.mark_dirty()

    @property
    def flip_horizontal(self) -> bool:
        """Whether the object is flipped left-right (``hp:flip/@horizontal``, Hancom's 좌우 대칭).

        Setting it flips a rectangle (a text box too), an ellipse, a polygon, a line, an arc, a curve, a picture or a
        whole group as
        Hancom 2024 does (``ShapeObjHorzFlip``, saved): ``hp:flip`` takes the flag and ``hc:rotMatrix`` mirrors the
        object about its middle (``-1, 0, width``); its box, place and text stay (the text is not mirrored). A
        flipped picture, rectangle, ellipse or polygon resizes (``resize``) as Hancom resizes one: its mirror stays
        about the middle of its own size and its ``hc:scaMatrix`` moves it by what it lost on the flipped axis;
        turned or flipped afterwards it turns about where it holds its middle (Hancom's numbers). A resized object
        flips about the middle it is drawn at -- of odd own size, about the rounded middle of its own size drawn,
        staying in place unturned and turning about the middle it holds (a 11339 x 5669 polygon drawn 18000 x 6000:
        mirror at 8999, turn about 9000; rotate8). A turned flipped object resizes to its own size (see ``resize``). A
        turned object is mirrored as it is drawn: it is written turned the other way (30 becomes 330) and
        flipped, its box and place unchanged; a group resized and then turned is mirrored about the middle of the
        box around its own rectangle as drawn, its centre the middle of its box (Hancom's g-S-30-f/v). A flipped
        object turns (``rotation``): the matrix flips, then turns it.
        ``False`` flips it back the same way; an object whose ``hp:flip`` its matrices do not follow (an arc
        ``add_arc`` drew at a corner) is mirrored as drawn and written with the flags and angle that mirror is, as
        Hancom does (flagged both ways, ``flip_horizontal = False``: flags 0, 1 and angle 180). A group flips
        (either way or both, turned or not, resized or not) in place about the middle of the size it is drawn at --
        a turned group keeps its move, box and centre, as Hancom keeps them, and a group holding a group flips too
        (the group inside marked as a member);
        its members keep their own ``hp:flip`` 0 and take the mirror in their ``hc:rotMatrix`` from their own place,
        marked turned by (180 left-right, 0 up-down) less their own and the group's angle (Hancom's marks: 180, 150
        for a group turned 30, 330 up-down turned 30), kept as the group turns. A group flipped one way and
        unturned resizes (``resize``): every ``hc:scaMatrix`` moves by what the group gained or lost on the flipped
        axis (flipped up-down, Hancom also puts the members' centres at their drawn middles).

        Refused with ``shape-flip-unsupported`` (``context["reason"]``) where no Hancom-saved document shows the
        form: an OLE object, equation or other object; a line drawn 0 high or wide turned and then flipped; a
        sloping flipped line resized (Hancom drops its mirror); a flipped picture cut. A line drawn 0 high or wide
        flips as Hancom flips one: nothing drawn changes (an arrow at its end stays there), and Hancom writes the
        flags with an angle 180 more for a flip left-right -- so it reads ``flip_horizontal`` True and ``rotation``
        180 -- its matrices plain (:func:`flip_flat_line`); turned afterwards, it is drawn turned the angle less
        180 (:func:`turn_flat_line`). ``shape-rotation-unsupported``:
        an object Hancom's object properties skewed, flipped. A member of a group alone is
        ``shape-group-member-unsupported``, a value that is not a bool ``shape-flip-value``. The paragraph loses
        its line layout cache.
        """

        return flip_signs(self.element)[0] == -1

    @flip_horizontal.setter
    def flip_horizontal(self, flipped: bool) -> None:
        set_flip(self, 0, flipped)

    @property
    def flip_vertical(self) -> bool:
        """Whether the object is flipped up-down (``hp:flip/@vertical``, Hancom's 상하 대칭).

        Setting it works as :attr:`flip_horizontal` does, mirroring the object about its middle up-down
        (``hc:rotMatrix`` ``1, 0, 0, 0, -1, height``); a flipped group's members keep ``rotationInfo/@angle`` 0
        (Hancom's form, ``ShapeObjVertFlip``). The same refusals apply."""

        return flip_signs(self.element)[1] == -1

    @flip_vertical.setter
    def flip_vertical(self, flipped: bool) -> None:
        set_flip(self, 1, flipped)

    @property
    def description(self) -> str:
        """The object's description (``hp:shapeComment``), the text Hancom gives as its alternative text;
        ``""`` when it has none.

        Setting it takes a str (``shape-description-value``); ``""`` empties it. A member of a group
        carries none and is refused (``shape-group-member-unsupported``)."""

        comment = self.element.find(f"{_HP}shapeComment")
        return (comment.text or "") if comment is not None else ""

    @description.setter
    def description(self, text: str) -> None:
        if not isinstance(text, str):
            raise HwpxValueError(
                f"description must be a str; got {type(text).__name__}",
                code="shape-description-value",
                context={"type": type(text).__name__},
                suggestion="Pass the description as text; '' empties it.",
            )
        if _in_group(self.element, self.paragraph.element):
            raise _group_member_refused("described", "a group member has no place for it: Hancom keeps it on the group (none of 2,068 public members holds one)")
        from ._document_primitives import _append_child, _reposition_child_after_any

        comment = self.element.find(f"{_HP}shapeComment")
        if comment is None:
            comment = _append_child(self.element, f"{_HP}shapeComment", {})
            _reposition_child_after_any(self.element, comment, ("outMargin", "caption"))
        if (comment.text or "") != text:
            comment.text = text
            self.paragraph.section.mark_dirty()

    def remove(self, *, remove_orphaned: bool = True) -> None:
        """Take this object out of its paragraph, as Hancom deletes it, the way ``table.remove()`` does.

        Its caption and anything inside it go with it. The paragraph stays (an empty line when it held
        nothing else) and loses its line layout cache, as do the paragraphs holding it when it sits in a
        table cell or a text box; a run left empty goes. A connector attached to it (or to a member of it)
        keeps its drawn ends and lets go of it (``subjectIDRef="0"``). The images it showed (a picture's,
        a picture's in a group, an image fill) leave the package with it when nothing else in the document
        points at them, as Hancom drops unused images when it saves (*remove_orphaned*, as
        ``doc.media.replace_picture`` takes it); ``remove_orphaned=False`` keeps them, and
        ``doc.media.remove_unused_images()`` removes every such image later.

        A member of a group leaves it and the groups fit what is left, as Hancom-saved groups hold their
        members: a group is the box around its members, so a group inside takes the box around the members
        left in it, and the outermost group moves every shape in it so that box starts at its origin, takes
        its size (drawn at the size Hancom or ``resize`` gave it) and, floating from the left and top of its
        frame, moves on the page by as much, so the members left stay where they were drawn. That is
        refused (``shape-group-member-unsupported``, with ``context["reason"]``) where a group or a member
        of one is turned, flipped or stretched otherwise than so. A group's only member takes the group with
        it (a group inside a group so, the group that held it fitting what is left). A second
        call does nothing; the object should not be used after it.
        """

        element = self.element
        paragraph = self.paragraph.element
        parent = _parent_of(element, paragraph)
        if parent is None or not any(child is element for child in parent):
            return
        from .container import _shapes_inside

        # A group's only member taken out takes the group with it: no Hancom-saved document holds an empty
        # group, nor a group of one (773 public groups have two or more members).
        while _local(parent) == "container" and len(_shapes_inside(parent)) < 2:
            element, parent = parent, _parent_of(parent, paragraph)
        groups = []
        node = parent
        while node is not None and str(node.tag).rsplit("}", 1)[-1] == "container":
            groups.append(node)
            node = _parent_of(node, paragraph)
        if groups:
            from .container import member_removal_refusal

            why = member_removal_refusal(element, groups)
            if why is not None:
                raise _group_member_refused("removed", why)
        from .note_authoring import note_kinds_in_document, renumber_note_kinds

        images = binary_references(element) if remove_orphaned else set()
        section = self.paragraph.section
        note_kinds = note_kinds_in_document(section, element)
        _detach_object(element, parent, paragraph, section)
        if groups:  # the groups fit the members left, so only after it went
            from .container import fit_groups_after_removal

            fit_groups_after_removal(groups)
        remove_orphaned_images(section, images)
        renumber_note_kinds(section, note_kinds)  # the notes after the ones in its text or caption

    def move_to(self, paragraph: "int | HwpxOxmlParagraph", *, offset: int | None = None,
                keep_order: bool = False) -> None:
        """Move this object into *paragraph* at character *offset* (``None``: the end), as cutting
        and pasting it in Hancom does.

        *paragraph* is a paragraph -- in the body, a table cell, a text box, a note, a caption, a
        header or a footer -- or its index in ``doc.paragraphs``. A paragraph of another document
        takes the object as Hancom 2024 pastes one cut from another document: a copy with fresh ids
        and the images and charts it shows goes there, and the original is removed. Refused there
        (``shape-copy-document-unsupported``): an object holding text (a text box, a caption, a
        table: Hancom could not open such a document again) and a connector (it would let go of its
        shapes, and Hancom draws such a connector nowhere). *offset* counts as
        ``paragraph.text`` does (a tab or a line break is one, an object none); the object goes in
        front of the character there, after the controls and objects already at that place. The
        object keeps its ids, its caption and what it holds; this wrapper then belongs to
        *paragraph*. Where it left, its place is cleaned up as :meth:`remove` does (a run left
        empty goes, a connector attached to it lets go of it), and the paragraphs on both sides
        lose their line layout caches, with the paragraphs holding their cells and captions.

        As Hancom pastes an object, it goes over the others (its ``zOrder`` one more than the
        highest in the document of *paragraph*, whose sections Hancom numbers as one). With ``keep_order=True`` it keeps the ``zOrder`` it
        had, so shapes drawn over and under one another stay in that order when they are moved
        (into another section the number is kept as it is, even where an object there has the
        same one). In the body, a header or a footer a floating object
        keeps its frames and offsets as they are written. Measured from its paragraph (``PARA``,
        ``COLUMN``) it goes with its new paragraph; measured from the page or paper (``PAGE``,
        ``PAPER``) it stays where it is on the page, also in a section with other paper -- only
        the page it is drawn on follows its new paragraph, so moved within one page it does not
        move at all (``set_position`` puts it elsewhere). Into a table cell, a text box, a note or
        a caption a floating object takes the placement Hancom 2024 gives one pasted there
        (:func:`pasted_placement`; read it back from ``position``): one not measured down from its
        paragraph, or not kept in the page area, is measured from its paragraph at offset 0, kept
        in the area and not let overlap; one measured across from the page or paper is measured
        from the column at offset 0. Refused with ``shape-move-place-unsupported``: a floating table
        into a cell, text box, note or caption unless it is
        measured down from its paragraph and kept in the page area, and any object into a memo or a
        master page (no Hancom-saved document shows how Hancom puts one there). Moving an object
        into itself (a paragraph of its own text box or caption) is ``shape-move-into-itself``, a
        member of a group alone ``shape-group-member-unsupported``, a removed object
        ``shape-not-in-document``. Everything is checked before anything changes.
        """

        place_object(self, paragraph, offset, copy=False, keep_order=keep_order)

    def copy_to(self: _Placed, paragraph: "int | HwpxOxmlParagraph", *, offset: int | None = None) -> _Placed:
        """Put a copy of this object into *paragraph* at *offset* (``None``: the end) and return it.

        The place is chosen and checked as :meth:`move_to` does (another document's paragraph too,
        the images and charts carried there), and a copy may go inside the object it copies (a copy
        of a text box into its own text). The copy has fresh ids (its
        objects, tables, paragraphs and fields; a connector in it follows the copied objects it
        was attached to and lets go of the others), no line layout caches, and the same images
        (a picture's copy shows the same ``BinData`` item). A memo anchored in it becomes a memo
        of its own with the next memo number. The original stays as it was. A copy of an object
        floating at a place on the page or paper (``PAGE``, ``PAPER``) has the same place: on the
        same page it is drawn exactly over the original until ``set_position`` moves it.
        """

        return place_object(self, paragraph, offset, copy=True)  # type: ignore[no-any-return]


_IDENTITY = ("1", "0", "0", "0", "1", "0")


def _rotation_refused(element: Any, why: str) -> HwpxValueError:
    return HwpxValueError(
        f"hp:{str(element.tag).rsplit('}', 1)[-1]} cannot be turned: {why}",
        code="shape-rotation-unsupported",
        context={"reason": why},
        suggestion="Pictures, drawing shapes (with or without text) and OLE objects turn, stretched or not, and "
                   "so does a whole group, resized or not, with groups inside, turned or not, and a rectangle, "
                   "ellipse, polygon, line or group flipped as Hancom flips them, resized or not; an object Hancom's "
                   "object properties skewed, a group holding a member turned or flipped on its own, an equation or "
                   "chart do not.",
    )


def turn_anchor(element: Any) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """Where a floating object holds the centre it turns about, in its box (``rotationInfo`` centre), and its box
    (``hp:sz``) -- before a turn, for :func:`keep_turn_anchor`; ``None`` for an object set as a character."""

    position, info = element.find(f"{_HP}pos"), element.find(f"{_HP}rotationInfo")
    if position is None or info is None or (position.get("treatAsChar") or "0") not in _FALSE_FLAGS:
        return None
    return ((_number(info.get("centerX")) or 0, _number(info.get("centerY")) or 0), object_size(element))


def keep_turn_anchor(element: Any, before: tuple[tuple[int, int], tuple[int, int]] | None) -> None:
    """After a turn, move the floating object *element* in its frame so the centre it turns about stays where it was
    on the page, as Hancom 2024 does (rotate9 ``want-float1``, a picture, a rectangle and a group placed from a
    paragraph and column, from the paper, and centred): placed from the left (top), its offset gains the old centre
    less the new one (a group turned 30 degrees: 428 left, 3598 up -- its ``transMatrix`` move taken back); centred,
    the old centre's distance from the middle of the old box less the new one's (a group turned 30, 12330 high with
    its centre at 6598: 433 up; a picture, whose centre is the middle of its box, does not move). Placed from the
    right, bottom, inside or outside it is left: no Hancom-saved document shows one turned. A flip and a resize do
    not move it (Hancom's neither)."""

    if before is None:
        return
    position, info = element.find(f"{_HP}pos"), element.find(f"{_HP}rotationInfo")
    if position is None or info is None:
        return
    (old_x, old_y), (old_w, old_h) = before
    new_x, new_y = _number(info.get("centerX")) or 0, _number(info.get("centerY")) or 0
    new_w, new_h = object_size(element)
    for key, align, old_centre, new_centre, old_size, new_size, start in (
            ("horzOffset", position.get("horzAlign", "LEFT"), old_x, new_x, old_w, new_w, "LEFT"),
            ("vertOffset", position.get("vertAlign", "TOP"), old_y, new_y, old_h, new_h, "TOP")):
        if align == start:
            moved = old_centre - new_centre
        elif align == "CENTER":
            moved = (old_centre - old_size // 2) - (new_centre - new_size // 2)  # 14849 high: 7424 (g-center-45)
        else:
            continue
        if moved:
            position.set(key, str((_signed_offset(position.get(key)) or 0) + moved & 0xFFFFFFFF))


def rotation_base_size(element: Any) -> tuple[int, int]:
    """The object's own (unturned) size as drawn, when it is one this package knows how Hancom turns; else refuse.

    Known: an object outside a group, not flipped and not a group itself, with one trans/sca/rot set of
    rendering matrices whose ``hc:scaMatrix`` only scales (and moves): its size as drawn is its original
    size (``hp:orgSz``) through that matrix, as its ``hp:curSz`` holds it. Hancom-saved turned objects
    hold one relation then -- the object as drawn (``scaMatrix``) is turned about its middle
    (``rotMatrix``) and moved so the box around it starts at its origin (``transMatrix``), and that box
    is ``hp:sz`` with ``hp:rotationInfo``'s centre in its middle -- unstretched (the public
    ``SimplePolygon``) and stretched alike (``ta-pic-001-r.hwp``, a picture drawn at 0.2768 of its size
    and turned 34 degrees: its ``sz`` 18425 x 18160 and centre (9212, 9080) follow from it; nine polygons
    of a public handbook drawn at 0.36 x 0.16 and turned 35, 90, 180 and 325 degrees, their ``sz`` too).
    A turned group, a member of a group (their matrices carry the groups' too) and a flipped object are
    not known, so they are not written.
    """

    info = element.find(f"{_HP}rotationInfo")
    rendering = element.find(f"{_HP}renderingInfo")
    if info is None or rendering is None:
        raise _rotation_refused(element, "it has no hp:rotationInfo")
    if str(element.tag).rsplit("}", 1)[-1] == "container":
        # A group turns as a whole (container.turn_group); a turned group is not resized or cut.
        raise _rotation_refused(element, "a turned group is not resized: no Hancom-saved document shows one; "
                                         "turn it back to 0 first")
    matrices = [str(child.tag).rsplit("}", 1)[-1] for child in rendering]
    if matrices != ["transMatrix", "scaMatrix", "rotMatrix"]:
        raise _rotation_refused(element, "its rendering matrices are not one trans/sca/rot set")
    scale_x, scale_y = _drawn_scale(rendering[1])
    if (scale_x == 0) != (scale_y == 0) and min(scale_x, scale_y) == 0 and abs(_fraction(rendering[1].get("e2"), 0.0)) \
            <= 1e-3 and abs(_fraction(rendering[1].get("e4"), 0.0)) <= 1e-3:
        # a line drawn 0 high (or wide): Hancom flips one by writing it turned 180 (rotate8 h-S1-f), turns unknown
        raise _rotation_refused(element, "it is drawn 0 high or wide: Hancom writes its flip as a half turn")
    if scale_x <= 0 or scale_y <= 0:
        raise _rotation_refused(element, "its hc:scaMatrix does more than scale it")
    flips = flip_signs(element)
    if flips != (1, 1):
        why = flip_form_refusal(element)
        if why is None and not flipped_form_matches(rendering[2], (_number(info.get("angle")) or 0) % 360, flips):
            why = "its hc:rotMatrix does not flip it as Hancom writes a flipped object"
        if why is not None:
            raise _rotation_refused(element, f"it is flipped: {why}")
    original = element.find(f"{_HP}orgSz")
    own_width, own_height = (_number(original.get("width")) or 0, _number(original.get("height")) or 0) \
        if original is not None else (0, 0)
    width, height = round(own_width * scale_x), round(own_height * scale_y)
    current = element.find(f"{_HP}curSz")
    if current is not None:
        for side, drawn in (("width", width), ("height", height)):
            value = _number(current.get(side)) or 0
            if value != 0 and abs(value - drawn) > 2:  # Hancom rounds it a unit off (13424 for 13425)
                raise _rotation_refused(element, "its current size is not its original size through its scaMatrix")
    if width <= 0 or height <= 0:
        raise _rotation_refused(element, "it has no original size")
    return width, height


def _drawn_scale(scale: Any) -> tuple[float, float]:
    """The factors a ``hc:scaMatrix`` draws an object at on each axis; ``(0, 0)`` when it does more than scale
    and move (a skew). Hancom writes an unstretched one with float noise (1.000037, -0.000023)."""

    e2, e4 = _fraction(scale.get("e2"), 0.0), _fraction(scale.get("e4"), 0.0)
    if abs(e2) > 1e-3 or abs(e4) > 1e-3:
        return 0.0, 0.0
    sx, sy = _fraction(scale.get("e1"), 1.0), _fraction(scale.get("e5"), 1.0)
    return (1.0 if abs(sx - 1) <= 1e-3 else sx), (1.0 if abs(sy - 1) <= 1e-3 else sy)


def apply_rotation(element: Any, angle: int, width: int, height: int) -> None:
    """Write *element* (drawn *width* x *height* through its ``hc:scaMatrix``) turned *angle* degrees clockwise:
    ``hc:rotMatrix`` turns it about its middle as drawn, ``hp:offset``/``hc:transMatrix`` move the box around
    it to its origin, ``hp:sz`` is that box and ``hp:rotationInfo`` the angle and the middle of the box."""

    cos, sin = turn_cos_sin(angle)
    flips = flip_signs(element)
    scale = element.find(f"{_HP}renderingInfo")[1]
    # The object as drawn starts where its scaMatrix moves it (0, 0 unless Hancom moved it there).
    left, top = _fraction(scale.get("e3"), 0.0), _fraction(scale.get("e6"), 0.0)
    middle = (left + width / 2, top + height / 2)
    corners = ((left, top), (left + width, top), (left + width, top + height), (left, top + height))
    held = held_pivot(element, middle)
    mirror_at = _stretched_mirror_middle(element, middle, flips)
    if held is None and angle and mirror_at != middle:
        # flipped where it is stretched, the mirror is about the rounded middle of its own size drawn and the turn
        # about the middle it holds: a 11339 x 5669 polygon drawn 18000 x 6000, flipped and turned 30, mirrors at
        # 8999 and turns about (9000, 3000) (rotate8 y-S1-f-30)
        pivot = _whole_middle(element, middle)
        mirror = tuple(2 * mirror_at[i] if flips[i] == -1 else 0.0 for i in (0, 1))
        held = (pivot, (pivot[0] + flips[0] * (mirror[0] - pivot[0]), pivot[1] + flips[1] * (mirror[1] - pivot[1])))
    if held is None:
        middle = _whole_middle(element, mirror_at)
        shift, box = turned_frame(cos, sin, middle, corners, flips)
        if not angle and flips != (1, 1) and _drawn_scale(scale) != (1.0, 1.0):
            # a stretched object flipped unturned stays in place, its box kept, though its mirror is about the
            # rounded middle of its own size drawn (a 11339 x 5669 polygon drawn 18000 x 6000: mirror at 8999, move
            # 0, box 18000 x 6000; unstretched, its mirror at 5669 moves it 1 -- rotate8 y-S1-f, y-f-S1)
            shift, box = (0, 0), (_half_up(width), _half_up(height))
        set_turn(element, cos, sin, middle, shift, flips)
    elif not angle and flips == (1, 1):  # unflipped and unturned again: the move goes back into its scaMatrix
        pivot, base = held
        scale.set("e3", _matrix_number(left + base[0]))
        scale.set("e6", _matrix_number(top + base[1]))
        left, top = left + base[0], top + base[1]
        middle = (left + width / 2, top + height / 2)
        corners = ((left, top), (left + width, top), (left + width, top + height), (left, top + height))
        shift, box = turned_frame(cos, sin, middle, corners, flips)
        set_turn(element, cos, sin, middle, shift, flips)
    else:  # a flipped picture resized after its flip: Hancom turns it about where it holds its middle
        pivot, base = held
        middle = pivot
        shift, box = _write_turn_about_held(element, turn_linear(cos, sin, flips), pivot, base, corners)
    info = element.find(f"{_HP}rotationInfo")
    info.set("angle", str(angle))
    if angle:
        info.set("centerX", str(_half_up(middle[0] + shift[0])))
        info.set("centerY", str(_half_up(middle[1] + shift[1])))
    else:  # back to its own size: the centre a new object has
        info.set("centerX", str(width // 2))
        info.set("centerY", str(height // 2))
    size = element.find(f"{_HP}sz")
    if size is not None:
        if size.get("widthRelTo", "ABSOLUTE") == "ABSOLUTE":
            size.set("width", str(box[0]))
        if size.get("heightRelTo", "ABSOLUTE") == "ABSOLUTE":
            size.set("height", str(box[1]))
    set_text_width(element, box[0])


def _half_up(value: float) -> int:
    return math.floor(value + 0.5)


def _stretched_mirror_middle(element: Any, middle: tuple[float, float],
                             flips: tuple[int, int]) -> tuple[float, float]:
    """*middle*, or on each flipped axis where the object is drawn stretched, where Hancom mirrors it: the whole-unit
    middle of its own size (``orgSz // 2``) drawn at its scale and rounded -- a 11339 x 5669 polygon drawn at 18000 x
    6000 flipped left-right holds ``rotMatrix`` e3 17998 (5669 x 1.587442 = 8999.2), up-down e6 5998; at 8000 x
    12000, 8000 and 11998 (rotate8 y-S-f, y-S-v)."""

    original, scale = element.find(f"{_HP}orgSz"), element.find(f"{_HP}renderingInfo")[1]
    if original is None or flips == (1, 1):
        return middle
    factors = (_fraction(scale.get("e1"), 1.0), _fraction(scale.get("e5"), 1.0))
    own = ((_number(original.get("width")) or 0) // 2, (_number(original.get("height")) or 0) // 2)
    starts = (_fraction(scale.get("e3"), 0.0), _fraction(scale.get("e6"), 0.0))
    out = []
    for axis in (0, 1):
        stretched = abs(factors[axis] - 1) > 1e-3 and factors[axis] > 0
        held = starts[axis] + round(own[axis] * factors[axis])
        # a horizontal line (orgSz height 1) drawn 3000 high mirrors at 0 x 3000 = 0 (rotate8 h-S2-v)
        out.append(held if flips[axis] == -1 and stretched else middle[axis])
    return out[0], out[1]


def _whole_middle(element: Any, middle: tuple[float, float]) -> tuple[float, float]:
    """*middle*, or the whole-unit centre the object holds (``rotationInfo`` centre less its move) where they are half a
    unit apart: an object of odd size turns about the centre it holds -- a 17008 x 5669 curve flipped and turned 30
    degrees holds ``rotMatrix`` e6 4631.68515, the turn about y 2834, not 2834.5."""

    info, rendering = element.find(f"{_HP}rotationInfo"), element.find(f"{_HP}renderingInfo")
    if info is None or rendering is None:
        return middle
    trans = rendering[0]
    held = ((_number(info.get("centerX")) or 0) - _fraction(trans.get("e3"), 0.0),
            (_number(info.get("centerY")) or 0) - _fraction(trans.get("e6"), 0.0))
    return tuple(h if abs(h - m) <= 0.5 + 1e-6 else m for h, m in zip(held, middle))  # type: ignore[return-value]


def held_pivot(element: Any, middle: tuple[float, float]) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Where a picture flipped and then resized holds its middle, and the move its ``hc:rotMatrix`` makes before
    flipping and turning it -- ``None`` for every other object (it turns about its *middle* as drawn).

    Hancom resizes a flipped picture keeping its mirror about the middle of its own size and moving it in its
    ``hc:scaMatrix`` (rotate5), and turns or flips it afterwards about its ``rotationInfo`` centre (less its move),
    composing with that mirror: a 12000 x 6000 picture flipped, resized to 6000 x 6000 and turned 30 degrees holds
    ``rotMatrix`` e3 12294.225, e6 4901.925 -- the turn about (3000, 3000) after a move of -6000."""

    rendering = element.find(f"{_HP}renderingInfo")
    scale = rendering[1]
    # held only where resize_object moved a flipped picture in its scaMatrix (a flip leaves that move behind)
    if abs(_fraction(scale.get("e3"), 0.0)) < 0.5 and abs(_fraction(scale.get("e6"), 0.0)) < 0.5:
        return None
    info = element.find(f"{_HP}rotationInfo")
    trans, rot = rendering[0], rendering[2]
    pivot = ((_number(info.get("centerX")) or 0) - _fraction(trans.get("e3"), 0.0),
             (_number(info.get("centerY")) or 0) - _fraction(trans.get("e6"), 0.0))
    if abs(pivot[0] - middle[0]) <= 1 and abs(pivot[1] - middle[1]) <= 1:
        return None
    a, b, c, d = (_fraction(rot.get(key), 0.0) for key in ("e1", "e2", "e4", "e5"))
    det = a * d - b * c
    if abs(det) < 1e-9:
        return None
    # rot = L about pivot after a move: t = L.base + pivot - L.pivot, so base = L^-1 (t - pivot + L.pivot)
    rest = (_fraction(rot.get("e3"), 0.0) - pivot[0] + a * pivot[0] + b * pivot[1],
            _fraction(rot.get("e6"), 0.0) - pivot[1] + c * pivot[0] + d * pivot[1])
    return pivot, ((d * rest[0] - b * rest[1]) / det, (-c * rest[0] + a * rest[1]) / det)


def _write_turn_about_held(element: Any, linear: tuple[float, float, float, float], pivot: tuple[float, float],
                           base: tuple[float, float], corners: Any) -> tuple[tuple[int, int], tuple[int, int]]:
    """Write *element*'s ``hc:rotMatrix`` as *linear* about *pivot* after the move *base* (see :func:`held_pivot`),
    its ``hc:transMatrix``/``hp:offset`` moving the box around it to its origin; return that move and the box."""

    a, b, c, d = linear
    move = (a * (base[0] - pivot[0]) + b * (base[1] - pivot[1]) + pivot[0],
            c * (base[0] - pivot[0]) + d * (base[1] - pivot[1]) + pivot[1])
    xs = [a * x + b * y + move[0] for x, y in corners]
    ys = [c * x + d * y + move[1] for x, y in corners]
    shift = (_half_up(-min(xs)), _half_up(-min(ys)))
    box = (_half_up(max(xs) + shift[0]), _half_up(max(ys) + shift[1]))
    rendering = element.find(f"{_HP}renderingInfo")
    for key, value in (("e1", 1.0), ("e2", 0.0), ("e3", shift[0]), ("e4", 0.0), ("e5", 1.0), ("e6", shift[1])):
        rendering[0].set(key, _matrix_number(value))
    for key, value in zip(("e1", "e2", "e3", "e4", "e5", "e6"), (a, b, move[0], c, d, move[1])):
        rendering[2].set(key, _matrix_number(round(value, 6)))
    offset = element.find(f"{_HP}offset")
    if offset is not None:
        offset.set("x", str(shift[0] & 0xFFFFFFFF))
        offset.set("y", str(shift[1] & 0xFFFFFFFF))
    return shift, box


def flip_signs(element: Any) -> tuple[int, int]:
    """-1 on each axis *element*'s ``hp:flip`` mirrors (``horizontal``: left-right, ``vertical``: up-down), else 1."""

    flip = element.find(f"{_HP}flip")
    flags = [flip is not None and (flip.get(side) or "0").strip() not in _FALSE_FLAGS
             for side in ("horizontal", "vertical")]
    return (-1 if flags[0] else 1), (-1 if flags[1] else 1)


#: Drawing shapes Hancom 2024 was seen flipping (and turning flipped, and flipping turned): rectangles (text boxes
#: included), ellipses, polygons, lines and groups.
FLIPPED_KINDS = frozenset({"rect", "ellipse", "polygon", "line", "arc", "curve", "pic", "container"})

def _flip_refused(element: Any, why: str) -> HwpxValueError:
    return HwpxValueError(
        f"hp:{str(element.tag).rsplit('}', 1)[-1]} cannot be flipped: {why}",
        code="shape-flip-unsupported",
        context={"reason": why},
        suggestion="Rectangles, text boxes, ellipses, polygons, lines, arcs, curves, pictures and whole groups flip "
                   "either way or both, turned or not, resized or not; a line drawn 0 high or wide flips unturned.",
    )


def flip_form_refusal(element: Any) -> str | None:
    """Why *element*'s flip (``hp:flip``) is not one this package knows Hancom's form of, or ``None``: none, or one
    on a rectangle, ellipse, polygon, line (either way or both) or group (one way), whose ``hc:rotMatrix`` must
    then flip (then turn) it as Hancom writes."""

    flips = flip_signs(element)
    if flips == (1, 1):
        return None
    kind = str(element.tag).rsplit("}", 1)[-1]
    if kind not in FLIPPED_KINDS:
        return f"a flipped {kind} is not shown by a Hancom-saved document"
    if flips == (-1, -1) and kind == "container":
        return "it is flipped both ways: no Hancom-saved document shows how Hancom holds a group so"
    return None


def set_flip(obj: Any, axis: int, flipped: object) -> None:
    """Flip *obj* on *axis* (0 left-right, 1 up-down) or flip it back (see ``ObjectPlacement.flip_horizontal``).
    Everything is checked before anything changes."""

    element = obj.element
    if not isinstance(flipped, bool):
        raise HwpxValueError(
            f"a flip is True or False; got {flipped!r}",
            code="shape-flip-value",
            context={"value": repr(flipped)},
            suggestion="Pass True to flip the object, False to flip it back.",
        )
    flips = flip_signs(element)
    if (flips[axis] == -1) == flipped:
        return
    if _in_group(element, obj.paragraph.element):
        raise _group_member_refused("flipped", "a member flips only with its whole group: flip the group")
    kind = str(element.tag).rsplit("}", 1)[-1]
    flip = element.find(f"{_HP}flip")
    if kind not in FLIPPED_KINDS or flip is None:
        raise _flip_refused(element, f"no Hancom-saved document shows how Hancom flips a {kind}")
    sides = [-1 if (i == axis and flipped) or (i != axis and flips[i] == -1) else 1 for i in (0, 1)]
    wanted = (sides[0], sides[1])
    info = element.find(f"{_HP}rotationInfo")
    turned = (_number(info.get("angle")) or 0) % 360 if info is not None else 0
    # Flipping a turned object mirrors it as it is drawn: Hancom writes it turned the other way (30 -> 330) and
    # flipped -- a text box turned 30 degrees and flipped left-right, up-down or both, a group left-right.
    angle = (-turned) % 360
    if kind == "container":
        from .container import turn_group

        # Hancom marks each member as turned by what its own and the group's angle mirror to: flipped left-right
        # 180 less the two (180 for a group flipped unturned, 150 turned 30), up-down 0 less the two (330 turned
        # 30; 180 stays 180 when a group flipped left-right is flipped up-down too), and leaves the marks as the
        # group turns afterwards. A group flipped back to neither way gets its members' 0 back.
        turn_group(element, angle, flips=wanted, member_flip=(axis, turned))
    else:
        flat = flat_line(element)
        if flat is not None:
            flip_flat_line(element, wanted, flat)
            from ._document_primitives import _clear_paragraph_layout_cache

            _clear_paragraph_layout_cache(obj.paragraph.element)
            obj.paragraph.section.mark_dirty()
            return
        flagged_only = _flagged_only(element, flips, turned)
        if flagged_only is not None:
            # hp:flip set but matrices left plain (add_arc's corner arcs): Hancom's flip mirrors the object as it is
            # drawn -- its rotMatrix the mirror about its middle -- and writes the flags and the angle the mirror
            # then is (a corner arc flagged both ways, flipped left-right: flags 0,1, angle 180; rotate7 ac-f, ac-v)
            mirror = (-1, 1) if axis == 0 else (1, -1)
            r00, r10 = mirror[0] * wanted[0], 0.0  # R(angle) = mirror . diag(wanted)
            angle = round(math.degrees(math.atan2(r10, r00))) % 360
            flip.set("horizontal", "1" if wanted[0] == -1 else "0")
            flip.set("vertical", "1" if wanted[1] == -1 else "0")
            apply_rotation(element, angle, *flagged_only)
            from ._document_primitives import _clear_paragraph_layout_cache

            _clear_paragraph_layout_cache(obj.paragraph.element)
            obj.paragraph.section.mark_dirty()
            return
        try:
            width, height = rotation_base_size(element)
        except HwpxValueError as refused:
            raise _flip_refused(element, str(refused.context.get("reason") or refused)) from None
        # resized (drawn at another size) it mirrors about the middle it is drawn at -- pictures (rotate6), arcs and
        # curves (rotate7), rectangles, ellipses, polygons and lines (rotate8; see _stretched_mirror_middle)
        flip.set("horizontal", "1" if wanted[0] == -1 else "0")
        flip.set("vertical", "1" if wanted[1] == -1 else "0")
        apply_rotation(element, angle, width, height)
    from ._document_primitives import _clear_paragraph_layout_cache

    _clear_paragraph_layout_cache(obj.paragraph.element)
    obj.paragraph.section.mark_dirty()


def flat_line(element: Any) -> tuple[int, int] | None:
    """The size a line drawn 0 high or 0 wide (a horizontal or vertical line) is drawn at, as Hancom writes it --
    its ``orgSz`` through its ``scaMatrix``, the 1 it keeps on the flat axis drawn 0 -- or ``None`` for any other
    object."""

    if str(element.tag).rsplit("}", 1)[-1] != "line":
        return None
    original, rendering = element.find(f"{_HP}orgSz"), element.find(f"{_HP}renderingInfo")
    if original is None or rendering is None or len(rendering) != 3:
        return None
    scale = _matrix_values(rendering[1])
    if abs(scale[1]) > 1e-3 or abs(scale[3]) > 1e-3:
        return None
    width = (_number(original.get("width")) or 0) * scale[0]
    height = (_number(original.get("height")) or 0) * scale[4]
    size = object_size(element)
    flat_across = abs(scale[0]) < 1e-9 or (size[0] == 0 and abs(width) <= 1 + 1e-6)
    flat_down = abs(scale[4]) < 1e-9 or (size[1] == 0 and abs(height) <= 1 + 1e-6)
    if flat_across == flat_down:  # a sloping line, or a point
        return None
    return (0 if flat_across else _half_up(width)), (0 if flat_down else _half_up(height))


def flat_flip_form(element: Any) -> tuple[int, int] | None:
    """The size a line is drawn at when it holds the form Hancom writes for a flat line flipped and then resized off
    flat (flags set, ``rotMatrix`` plain, angle 180 flipped left-right or 0 up-down; rotate8 ``h-f-S2``), or
    ``None``: it turns as a flat line does (:func:`turn_flat_line`; rotate8 ``h-f-S2-30``)."""

    if str(element.tag).rsplit("}", 1)[-1] != "line" or flip_signs(element) == (1, 1):
        return None
    rendering, original = element.find(f"{_HP}renderingInfo"), element.find(f"{_HP}orgSz")
    if rendering is None or original is None or len(rendering) != 3:
        return None
    if any(abs(a - b) > 1e-6 for a, b in zip(_matrix_values(rendering[2]), (1, 0, 0, 0, 1, 0))):
        return None
    if _flat_drawn_angle(element):
        return None
    scale = _matrix_values(rendering[1])
    return (_half_up((_number(original.get("width")) or 0) * scale[0]),
            _half_up((_number(original.get("height")) or 0) * scale[4]))


def _flat_drawn_angle(element: Any) -> int:
    """The angle a flat line is drawn turned: Hancom writes it flipped left-right as turned 180 more (rotate11)."""

    info = element.find(f"{_HP}rotationInfo")
    angle = (_number(info.get("angle")) or 0) % 360 if info is not None else 0
    return (angle - (180 if flip_signs(element)[0] == -1 else 0)) % 360


def _mirrored(element: Any) -> bool:
    """Whether *element*'s ``hc:rotMatrix`` mirrors it (its 2 x 2 part turns the page over)."""

    rot = _matrix_values(element.find(f"{_HP}renderingInfo")[2])
    return rot[0] * rot[4] - rot[1] * rot[3] < 0


def _flatten(element: Any, size: tuple[int, int], turned: bool) -> None:
    """Write a flat line as Hancom does once it has changed it: the flat axis drawn at 0 (``scaMatrix`` 0 there) and,
    turned, its box at least 1 across that way (turned 90 degrees: 1 x 12000; rotate11 ``ha-90``)."""

    scale = element.find(f"{_HP}renderingInfo")[1]
    for key, flat in (("e1", size[0] == 0), ("e5", size[1] == 0)):
        if flat:
            scale.set(key, "0")
    box = element.find(f"{_HP}sz")
    if turned and box is not None:
        for side in ("width", "height"):
            if box.get(side) == "0":
                box.set(side, "1")


def flip_flat_line(element: Any, wanted: tuple[int, int], size: tuple[int, int]) -> None:
    """Flip a line drawn 0 high or wide (:func:`flat_line`) as Hancom 2024 flips one (rotate11 ``want-flip7``: a
    horizontal line, a vertical line and a horizontal line with an arrow at its end, flipped left-right, up-down and
    both ways): flipping it unturned changes nothing drawn -- the arrow stays at its end -- and Hancom writes the
    flags, an angle 180 more for a flip left-right (``rotationInfo`` 180 flipped left-right or both ways, 0 up-down),
    its matrices plain and the flat axis drawn at 0 (``scaMatrix`` 0 there). Turned, it is flipped as any turned
    object is -- mirrored as drawn and written turned the other way (30 becomes 330; rotate11 ``ha-30-f``). Refused
    (``shape-flip-unsupported``) for one flipped, turned and flipped again: no Hancom-saved document shows it."""

    drawn = _flat_drawn_angle(element)
    flip = element.find(f"{_HP}flip")
    info = element.find(f"{_HP}rotationInfo")
    if drawn:
        if flip_signs(element) != (1, 1) or _mirrored(element):
            raise _flip_refused(element, "it is a line drawn 0 high or wide, flipped and turned: no Hancom-saved "
                                         "document shows one flipped again")
        turned = (_number(info.get("angle")) or 0) % 360 if info is not None else 0
        flip.set("horizontal", "1" if wanted[0] == -1 else "0")
        flip.set("vertical", "1" if wanted[1] == -1 else "0")
        apply_rotation(element, (-turned) % 360, *size)
        _flatten(element, size, True)
        return
    flip.set("horizontal", "1" if wanted[0] == -1 else "0")
    flip.set("vertical", "1" if wanted[1] == -1 else "0")
    _flatten(element, size, False)
    if info is not None:
        info.set("angle", str(180 if wanted[0] == -1 else 0))


def turn_flat_line(element: Any, angle: int, size: tuple[int, int]) -> None:
    """Turn a line drawn 0 high or wide (:func:`flat_line`) *angle* degrees as Hancom 2024 turns one: about its
    middle, its box the box around it so, the flat axis drawn at 0 (rotate11 ``h-30``, ``w-30``, ``ha-30``,
    ``ha-90``); flipped left-right first, drawn turned the angle less 180 (a turn of 210 for 30, no mirror;
    ``h-f-30``, ``w-f-30``, ``ha-f-30``); ``rotationInfo`` the angle given. Turned and then flipped (mirrored as
    drawn, ``ha-30-f``), it turns again as any flipped object does, the mirror kept (``ha-30-f-0``, ``ha-30-f-60``)."""

    if _mirrored(element):
        # turned and then flipped, it is mirrored as drawn like any flipped object: turned again (back to 0 too) the
        # mirror stays and the turn is the angle given (rotate12 ha-30-f-0, ha-30-f-60)
        apply_rotation(element, angle % 360, *size)
        _flatten(element, size, True)
        return
    flip = element.find(f"{_HP}flip")
    flags = (flip.get("horizontal"), flip.get("vertical")) if flip is not None else None
    drawn = (angle - (180 if flip_signs(element)[0] == -1 else 0)) % 360
    if flip is not None:  # drawn unmirrored: a flip of a flat line is the half turn above
        flip.set("horizontal", "0")
        flip.set("vertical", "0")
    try:
        apply_rotation(element, drawn, *size)
    finally:
        if flip is not None and flags is not None:
            flip.set("horizontal", flags[0] or "0")
            flip.set("vertical", flags[1] or "0")
    # once Hancom has turned it -- back to 0 too -- its box is at least 1 across the flat way (ha-30-0: 12000 x 1)
    _flatten(element, size, True)
    info = element.find(f"{_HP}rotationInfo")
    if info is not None:
        info.set("angle", str(angle % 360))


def _flagged_only(element: Any, flips: tuple[int, int], turned: int) -> tuple[int, int] | None:
    """The drawn size of an unturned object whose ``hp:flip`` is set while its matrices are plain (its rotMatrix
    does not mirror it), or ``None``."""

    if flips == (1, 1) or turned:
        return None
    rendering = element.find(f"{_HP}renderingInfo")
    if rendering is None or [str(child.tag).rsplit("}", 1)[-1] for child in rendering] != [
            "transMatrix", "scaMatrix", "rotMatrix"]:
        return None
    if any(abs(value - plain) > 1e-3 for value, plain in zip(_matrix_values(rendering[2]), (1, 0, 0, 0, 1, 0))):
        return None
    scale_x, scale_y = _drawn_scale(rendering[1])
    original = element.find(f"{_HP}orgSz")
    if original is None or scale_x <= 0 or scale_y <= 0:
        return None
    width = round((_number(original.get("width")) or 0) * scale_x)
    height = round((_number(original.get("height")) or 0) * scale_y)
    return (width, height) if width > 0 and height > 0 else None


def refuse_resizing_flipped(element: Any, *, cutting: bool = False) -> None:
    """Refuse (``shape-flip-unsupported``) to resize (or, *cutting*, to crop) a flipped object where no Hancom-saved
    document shows a form that keeps it flipped: a flipped picture, rectangle, ellipse, polygon and group (one holding
    a group too) resize, turned or not (a turned one as :func:`resize_turned_as_own` does). A flipped line does not:
    Hancom resizing one drops its mirror (``rotMatrix`` back to plain, its flags and an angle of 180 left; rotate8
    l-f-S, l-v-S), drawing it unflipped while it reads flipped. A flipped picture is not cut."""

    flips = flip_signs(element)
    if flips == (1, 1):
        return
    kind = str(element.tag).rsplit("}", 1)[-1]
    if not cutting and kind in ("pic", "rect", "ellipse", "polygon", "container"):
        return  # resize_object / resize_shape / resize_group write Hancom's form
    if not cutting and flat_line(element) is not None and not _flat_drawn_angle(element):
        return  # a flat line's flip mirrors nothing: Hancom resizes it keeping its flags and angle (rotate8 h-f-S)
    if cutting:
        why = "it is flipped: no Hancom-saved document shows it cut so; flip it back first"
    elif kind == "line":
        why = ("it is flipped: Hancom resizing a flipped line draws it unflipped (it drops the mirror and keeps "
               "the flags); flip it back first")
    else:
        why = "it is flipped: no Hancom-saved document shows it resized so; flip it back first"
    raise HwpxValueError(
        f"hp:{kind} cannot be {'cut' if cutting else 'resized'}: {why}",
        code="shape-flip-unsupported",
        context={"reason": why},
        suggestion="A flipped picture, rectangle, ellipse, polygon and group resize, turned or not; flip a line back "
                   "before resizing it, and a picture before cutting it.",
    )


def resize_turned_as_own(obj: Any, width: int | None, height: int | None,
                         resize_unturned: Callable[[int | None, int | None], None], *, unflip: bool = False) -> None:
    """Resize the turned object *obj* (flipped or not) to its own size *width* x *height* -- the size it has before
    it is turned, as ``resize`` means for every object -- the way Hancom writes an object resized before it is
    turned: turned back to 0 (its flip kept), resized as an unturned one (*resize_unturned*, one size alone keeping
    the aspect ratio of its own size) and turned again to its angle. With *unflip* (a group) it is flipped back
    first and flipped again last, as Hancom writes a group resized, turned and then flipped. Hancom-saved documents
    of objects resized and then turned (a picture flipped, resized and turned 30 degrees; a group resized and
    turned, and then flipped) are what that writes.

    The size Hancom's object properties take for a turned object is the box around it, and Hancom stretches the
    object along the page to fit it, skewing it into a parallelogram; ``resize`` does not do that. Everything is
    checked before anything changes: refused, the object is left as it was."""

    element = obj.element
    kept = copy.deepcopy(element)
    flips = flip_signs(element) if unflip else (1, 1)
    try:
        if flips[1] == -1:
            obj.flip_vertical = False
        if flips[0] == -1:
            obj.flip_horizontal = False
        info = element.find(f"{_HP}rotationInfo")
        angle = (_number(info.get("angle")) or 0) % 360 if info is not None else 0
        obj.rotation = 0
        resize_unturned(width, height)
        obj.rotation = angle
        if flips[0] == -1:
            obj.flip_horizontal = True
        if flips[1] == -1:
            obj.flip_vertical = True
    except Exception:
        element.clear()
        element.attrib.update(kept.attrib)
        element.text, element.tail = kept.text, kept.tail
        element.extend(list(kept))
        raise


def scale_member_text_widths(group: Any, factor: float) -> None:
    """After a turned group is stretched along the page by *factor* across: each member's text is laid out across
    its turned box that much wider, as Hancom writes it (a text box member 10294 wide: 15105 at 1.46735, 10070 at
    0.97823 -- rotate7 g-f-30-S, g-v-30-S, g-30-f-S2)."""

    for member, _ in _group_members(group, 1):
        draw_text = member.find(f"{_HP}drawText")
        if draw_text is not None:
            set_text_width(member, _half_up((_number(draw_text.get("lastWidth")) or 0) * factor))


def shift_flipped_group(element: Any, sizes: tuple[int, int], width: int, height: int) -> None:
    """After ``resize_group`` drew the group *element* (own size *sizes*) at *width* x *height*: a group flipped
    left-right keeps its mirror about the middle of its own size, and Hancom moves the group and every member by what
    it gained or lost (``scaMatrix`` e3 + own width - new width): a 12000 x 6000 group flipped and resized to
    18000 x 9000 holds e3 -6000, a member placed at 7000 e3 3500 - 6000."""

    flips = flip_signs(element)
    if flips == (1, 1):
        return
    # a group holding a group flipped up-down and resized keeps every member's own centre (rotate8 n-v-S1, n-v-S2)
    nested = any(str(child.tag).rsplit("}", 1)[-1] == "container" for child in element)
    moves = [(key, gained) for key, gained, flipped in (("e3", sizes[0] - width, flips[0] == -1),
                                                        ("e6", sizes[1] - height, flips[1] == -1)) if flipped]
    for node in [element, *(member for member, _ in _group_members(element, 1))]:
        scales = node.findall(f"{_HP}renderingInfo/{_HC}scaMatrix")
        for key, gained in moves if scales else ():
            scales[0].set(key, _matrix_number(_fraction(scales[0].get(key), 0.0) + gained))
        if flips == (1, -1) and node is not element and not nested:
            # flipped up-down, Hancom also puts each member's centre in the middle of the size it is drawn at (a
            # 6000 x 6000 member drawn 9000 x 9000: 4500); flipped left-right it leaves them (group-f-S vs group-v-S)
            own, scale = node.find(f"{_HP}orgSz"), _matrix_values(scales[0]) if scales else None
            info = node.find(f"{_HP}rotationInfo")
            if own is not None and info is not None and scale is not None:
                info.set("centerX", str(int((_number(own.get("width")) or 0) * scale[0] + 1e-6) // 2))
                info.set("centerY", str(int((_number(own.get("height")) or 0) * scale[4] + 1e-6) // 2))


def flipped_form_matches(rot: Any, angle: int, flips: tuple[int, int]) -> bool:
    """Whether *rot* (a ``hc:rotMatrix``) holds the 2 x 2 part of the flip and turn *angle* (Hancom's own turn
    back to 0 leaves noise: -1.000001)."""

    cos, sin = turn_cos_sin(angle)
    have = [_fraction(rot.get(key), 0.0) for key in ("e1", "e2", "e4", "e5")]
    return all(abs(x - y) <= 1e-3 for x, y in zip(have, turn_linear(cos, sin, flips)))


def turn_cos_sin(angle: int) -> tuple[float, float]:
    """The cosine and sine of *angle* degrees as Hancom writes them in ``hc:rotMatrix`` (six decimals) -- and
    computes the rest of a turn with: a rectangle turned 30 degrees holds ``e3="2764.62"`` (7200 x 0.133975 +
    3600 x 0.5), not 2764.617."""

    radians = math.radians(angle)
    return round(math.cos(radians), 6) + 0.0, round(math.sin(radians), 6) + 0.0


def turn_linear(cos: float, sin: float, flips: tuple[int, int] = (1, 1)) -> tuple[float, float, float, float]:
    """The 2 x 2 part (e1, e2, e4, e5) of a ``hc:rotMatrix`` that flips an object (*flips*: -1 on an axis Hancom's
    flip-left-right / flip-up-down mirrors, 1 elsewhere) and then turns it (*cos*, *sin*): Hancom turns a flipped
    object so (a text box flipped left-right and turned 45 degrees holds -0.707107, -0.707107, -0.707107,
    0.707107; flipped up-down, 0.707107, 0.707107, 0.707107, -0.707107)."""

    fx, fy = flips
    return cos * fx + 0.0, -sin * fy + 0.0, sin * fx + 0.0, cos * fy + 0.0


def turned_frame(cos: float, sin: float, middle: tuple[float, float],
                 points: "tuple[tuple[float, float], ...] | list[tuple[float, float]]",
                 flips: tuple[int, int] = (1, 1)) -> tuple[tuple[int, int], tuple[int, int]]:
    """*points* flipped (*flips*) and turned (*cos*, *sin*) about *middle*: how far, in whole units, to move them so
    the box around them starts at the origin, and that box's size -- Hancom's ``transMatrix`` move and ``hp:sz`` of
    a turned object or group (a 14400 x 7200 rectangle turned 30 degrees: moved by 835, 3118 into a 16070 x 13436
    box)."""

    a, b, c, d = turn_linear(cos, sin, flips)
    mx, my = middle
    xs = [(x - mx) * a + (y - my) * b for x, y in points]
    ys = [(x - mx) * c + (y - my) * d for x, y in points]
    shift = (_half_up(-(mx + min(xs))), _half_up(-(my + min(ys))))
    return shift, (_half_up(mx + max(xs) + shift[0]), _half_up(my + max(ys) + shift[1]))


def turn_entries(cos: float, sin: float, about: tuple[float, float],
                 flips: tuple[int, int] = (1, 1)) -> list[float]:
    """The six entries of a ``hc:rotMatrix`` flipping (*flips*) and turning (*cos*, *sin*) about *about*."""

    a, b, c, d = turn_linear(cos, sin, flips)
    ax, ay = about
    if flips == (1, 1):  # the form Hancom's numbers follow to the last digit (2764.62 at 30 degrees)
        return [a, b, ax * (1 - cos) + ay * sin, c, d, ay * (1 - cos) - ax * sin]
    return [a, b, ax - (a * ax + b * ay), c, d, ay - (c * ax + d * ay)]


def set_turn(element: Any, cos: float, sin: float, about: tuple[float, float], move: tuple[float, float],
             flips: tuple[int, int] = (1, 1)) -> None:
    """Write *element*'s ``hc:rotMatrix`` flipping (*flips*) and turning (*cos*, *sin*) about *about* (in its own
    space) and its ``hc:transMatrix`` and ``hp:offset`` moving it by *move* (whole units)."""

    rendering = element.find(f"{_HP}renderingInfo")
    trans, rot = rendering[0], rendering[2]
    for key, value in (("e1", 1.0), ("e2", 0.0), ("e3", move[0]), ("e4", 0.0), ("e5", 1.0), ("e6", move[1])):
        trans.set(key, _matrix_number(value))
    for key, value in zip(("e1", "e2", "e3", "e4", "e5", "e6"), turn_entries(cos, sin, about, flips)):
        rot.set(key, _matrix_number(round(value, 6)))
    offset = element.find(f"{_HP}offset")
    if offset is not None:
        offset.set("x", str(round(move[0]) & 0xFFFFFFFF))  # a negative one as Hancom writes it: unsigned 32-bit
        offset.set("y", str(round(move[1]) & 0xFFFFFFFF))


def set_text_width(element: Any, width: int) -> None:
    """The width a shape's text is laid out across (``hp:drawText/@lastWidth``) after a turn; its paragraphs lose
    their line layout caches, so Hancom breaks the lines again (it lays a turned shape's text level across the box
    around it). Nothing for a shape without text."""

    draw_text = element.find(f"{_HP}drawText")
    if draw_text is None:
        return
    draw_text.set("lastWidth", str(width))
    from ._document_primitives import _LAYOUT_CACHE_ELEMENT_NAMES

    for paragraph in draw_text.iter(f"{_HP}p"):
        for child in [c for c in paragraph if str(c.tag).rsplit("}", 1)[-1].lower() in _LAYOUT_CACHE_ELEMENT_NAMES]:
            paragraph.remove(child)


def object_size(element: Any) -> tuple[int, int]:
    """An object's ``hp:sz`` width and height (0 when missing)."""

    size = element.find(f"{_HP}sz")
    if size is None:
        return 0, 0
    return _number(size.get("width")) or 0, _number(size.get("height")) or 0


def own_size(element: Any) -> tuple[int, int]:
    """An object's own size as drawn, before it is turned -- what ``width``/``height`` read and ``resize`` takes.

    Unturned, its box (``hp:sz``). Turned, the size Hancom writes it drawn at: ``hp:curSz``, on an axis where that
    is 0 (Hancom writes 0 on an axis a resize left alone) its ``hp:orgSz``, and its ``hp:sz`` where neither is
    written -- as written, also for an object Hancom's object properties skewed (its box stretched along the page),
    which this only reads."""

    box = object_size(element)
    info = element.find(f"{_HP}rotationInfo")
    if info is None or not (_number(info.get("angle")) or 0) % 360:
        return box
    current, original = element.find(f"{_HP}curSz"), element.find(f"{_HP}orgSz")
    sides = []
    for index, side in enumerate(("width", "height")):
        value = _number(current.get(side)) if current is not None else None
        if not value and original is not None:
            value = _number(original.get(side))
        sides.append(value or box[index])
    return sides[0], sides[1]


def keep_ratio(current: tuple[int, int], width: int | None, height: int | None) -> tuple[int, int]:
    """*width* x *height*, the one left ``None`` taken at *current*'s aspect ratio."""

    if width is None and height is None:
        raise HwpxValueError(
            "resize needs a width, a height or both",
            code="shape-size-value",
            suggestion="Pass width= and/or height= in HWP units; one alone keeps the aspect ratio.",
        )
    if width is not None and height is not None:
        return validate_shape_size(width, height)
    given = width if width is not None else height
    validate_shape_size(given, given)
    old_width, old_height = current
    if old_width <= 0 or old_height <= 0:
        raise HwpxValueError(
            "the object has no size to keep the aspect ratio of",
            code="shape-size-value",
            context={"current": list(current)},
            suggestion="Pass both width and height.",
        )
    if width is not None:
        return width, max(1, round(old_height * width / old_width))
    assert height is not None
    return max(1, round(old_width * height / old_height)), height


def resize_object(obj: Any, width: int | None, height: int | None) -> None:
    """Resize a placed object (picture, OLE, chart, equation) to *width* x *height* (one alone keeps the
    aspect ratio), as Hancom stores a resized one: ``hp:sz`` and ``hp:curSz`` take the new size, the
    original size (``hp:orgSz``) and the geometry in it stay, and ``hc:scaMatrix`` scales between them.
    *width* x *height* is the object's own size, turned or not: a turned object is turned back, resized and turned
    again (:func:`resize_turned_as_own`). A flipped picture keeps its mirror about the middle of its own size, its
    ``hc:scaMatrix`` moving it by what it lost on the flipped axis, as Hancom resizes one; any other flipped object
    is refused (``shape-flip-unsupported``)."""

    element = obj.element
    if _local(element) == "equation":
        raise HwpxValueError(
            "an equation's box follows its script: Hancom 2024 measures it again whatever size it is given "
            "(objlim evidence psizeeq, eqsize)",
            code="shape-equation-resize-unsupported",
            context={"width": repr(width), "height": repr(height)},
            suggestion="수식 상자 크기는 스크립트와 글자 크기로 정해집니다. equation.font_size 나 equation.script 를 "
                       "바꾸세요.",
        )
    info = element.find(f"{_HP}rotationInfo")
    angle = (_number(info.get("angle")) or 0) % 360 if info is not None else 0
    flips = flip_signs(element)
    if flips != (1, 1):
        refuse_resizing_flipped(element)  # a flipped picture: below, as Hancom resizes one
    if angle:  # its own size: turned back, resized and turned again
        resize_turned_as_own(obj, width, height, lambda w, h: resize_object(obj, w, h))
        return
    width, height = keep_ratio(object_size(element), width, height)
    _set_size(element, "sz", width, height)
    original = element.find(f"{_HP}orgSz")
    if original is not None:
        org_width, org_height = _number(original.get("width")) or 0, _number(original.get("height")) or 0
        _set_size(element, "curSz", width, height)
        scale = element.find(f"{_HP}renderingInfo/{_HC}scaMatrix")
        if scale is not None and org_width > 0 and org_height > 0:
            scale.set("e1", _matrix_number(width / org_width))
            scale.set("e5", _matrix_number(height / org_height))
            # A flipped picture keeps its mirror about the middle of its own size: Hancom moves it, drawn at the
            # new size, by what it lost on the flipped axis (12000 wide flipped left-right, resized to 6000:
            # scaMatrix e3 6000), so the mirror lands it at the origin.
            if flips != (1, 1):
                scale.set("e3", _matrix_number(org_width - width if flips[0] == -1 else 0))
                scale.set("e6", _matrix_number(org_height - height if flips[1] == -1 else 0))
        rotation = element.find(f"{_HP}rotationInfo")
        if rotation is not None:
            rotation.set("centerX", str(width // 2))
            rotation.set("centerY", str(height // 2))
    from ._document_primitives import _clear_paragraph_layout_cache

    _clear_paragraph_layout_cache(obj.paragraph.element)
    obj.paragraph.section.mark_dirty()


def resize_shape(obj: Any, width: int | None, height: int | None) -> None:
    """Resize a drawing shape (not a group) to *width* x *height* (one alone keeps the aspect ratio) as Hancom
    2024 resizes one: its geometry and original size (``hp:orgSz``) stay and ``hc:scaMatrix`` draws it at the
    new size -- ``hp:sz`` the new size, ``hp:curSz`` the new size on an axis that differs from ``orgSz`` and 0
    on one that does not, the scale the new size over ``orgSz``, the rotation centre the middle of the new
    size (objlim evidence psizerect 8000x5000 -> 12000x5000: curSz 12000x0, e1 1.5; psizerect2 -> 4000x10000;
    psizerect3 twice, the scale over ``orgSz``; psizeline a horizontal line 14400x0 -> 14400x2000: orgSz
    14400x1 kept, e5 2000, and 7200x3000). *width* x *height* is the shape's own size, turned or not: a turned
    shape is turned back, resized and turned again (:func:`resize_turned_as_own`)."""

    element = obj.element
    info = element.find(f"{_HP}rotationInfo")
    angle = (_number(info.get("angle")) or 0) % 360 if info is not None else 0
    flat = flat_line(element) is not None
    if flat:  # a flat line flipped left-right is written turned 180 more, drawn unturned
        angle = _flat_drawn_angle(element)
    if angle:  # its own size: turned back, resized and turned again
        resize_turned_as_own(obj, width, height, lambda w, h: resize_shape(obj, w, h))
        return
    width, height = keep_ratio(object_size(element), width, height)
    _set_size(element, "sz", width, height)
    original = element.find(f"{_HP}orgSz")
    org = (_number(original.get("width")) or 0, _number(original.get("height")) or 0) \
        if original is not None else (0, 0)
    if min(org) > 0:
        _set_size(element, "curSz", width if width != org[0] else 0, height if height != org[1] else 0)
        scale = element.find(f"{_HP}renderingInfo/{_HC}scaMatrix")
        if scale is not None:
            scale.set("e1", _matrix_number(width / org[0]))
            scale.set("e5", _matrix_number(height / org[1]))
            flips = flip_signs(element) if not flat else (1, 1)  # a flat line's flip mirrors nothing
            if flips != (1, 1):
                # as a flipped picture: its mirror stays about the middle of its own size and Hancom moves it by
                # what it lost on the flipped axis (a 12000 x 6000 rectangle flipped, drawn 18000 wide: e3 -6000)
                scale.set("e3", _matrix_number(org[0] - width if flips[0] == -1 else 0))
                scale.set("e6", _matrix_number(org[1] - height if flips[1] == -1 else 0))
    else:  # no original size to draw from: the box alone
        _set_size(element, "curSz", width, height)
    if info is not None:
        info.set("centerX", str(width // 2))
        info.set("centerY", str(height // 2))
    draw_text = element.find(f"{_HP}drawText")
    if draw_text is not None and draw_text.get("lastWidth") != str(width):
        # its text laid out across the width it is drawn at, as Hancom writes a text box drawn at another width in
        # a group, turned, and turned back (no Hancom-saved document shows a lone text box resized unturned)
        set_text_width(element, width)
    from ._document_primitives import _clear_paragraph_layout_cache

    _clear_paragraph_layout_cache(obj.paragraph.element)
    obj.paragraph.section.mark_dirty()


def _matrix_values(matrix: Any) -> list[float]:
    return [_fraction(matrix.get(key), 1.0 if key in ("e1", "e5") else 0.0)
            for key in ("e1", "e2", "e3", "e4", "e5", "e6")]


def stretch_along_page(node: Any, factors: tuple[float, float],
                       linear: tuple[float, float, float, float] | None = None) -> None:
    """Stretch the drawn shape *node* by *factors* along the page's axes, keeping its turn and move, as Hancom
    2024 resizes a turned group: with ``L`` the 2x2 part of what turns it (``linear``; by default its
    ``hc:rotMatrix``'s, which may also mirror it), ``D`` the factors and ``t`` the move of its ``transMatrix`` and
    ``rotMatrix`` (e3/e6), its ``hc:scaMatrix`` becomes ``L^-1 D L`` moved by ``L^-1 (D - I) t``, and its
    ``hp:curSz`` its ``orgSz`` times the diagonal of that (rounded down)."""

    trans = _matrix_values(node.find(f"{_HP}renderingInfo/{_HC}transMatrix"))
    rot = _matrix_values(node.find(f"{_HP}renderingInfo/{_HC}rotMatrix"))
    l11, l12, l21, l22 = linear if linear is not None else (rot[0], rot[1], rot[3], rot[4])
    det = l11 * l22 - l12 * l21
    i11, i12, i21, i22 = l22 / det, -l12 / det, -l21 / det, l11 / det  # L^-1
    dx, dy = factors
    # L^-1 D L
    a11 = i11 * dx * l11 + i12 * dy * l21
    a12 = i11 * dx * l12 + i12 * dy * l22
    a21 = i21 * dx * l11 + i22 * dy * l21
    a22 = i21 * dx * l12 + i22 * dy * l22
    move = (trans[2] + rot[2], trans[5] + rot[5])
    stretched = ((dx - 1) * move[0], (dy - 1) * move[1])  # (D - I) t
    offset = (i11 * stretched[0] + i12 * stretched[1], i21 * stretched[0] + i22 * stretched[1])
    scale = node.find(f"{_HP}renderingInfo/{_HC}scaMatrix")
    for key, value in zip(("e1", "e2", "e3", "e4", "e5", "e6"), (a11, a12, offset[0], a21, a22, offset[1])):
        scale.set(key, _matrix_number(value))
    original = node.find(f"{_HP}orgSz")
    if original is not None:
        _set_size(node, "curSz", int((_number(original.get("width")) or 0) * a11 + 1e-6),
                  int((_number(original.get("height")) or 0) * a22 + 1e-6))


def resize_turned_group(shape: Any, width: int, height: int, *,
                        linear: "Callable[[Any], tuple[float, float, float, float]] | None" = None) -> None:
    """Stretch the turned group *shape* so the box around it (``hp:sz``) is *width* x *height*, as Hancom 2024's
    object properties resize one -- not what ``resize`` does (it takes a turned object's own size, see
    :func:`resize_turned_as_own`); kept as the record of the skewed form Hancom writes so. The turn and the move
    stay (``rotMatrix``, ``transMatrix``, ``hp:offset``, ``rotationInfo``)
    and it is stretched along the page's axes. With ``R`` the turn, ``D`` the box's new size over its old one
    on each axis and ``t`` the move of the shape's own turn and move (``transMatrix`` and ``rotMatrix`` e3/e6),
    the group and every member take ``scaMatrix`` = ``R^-1 D R`` moved by ``R^-1 (D - I) t``, and ``curSz`` its
    ``orgSz`` times the diagonal of that (rounded down). Hancom wrote exactly this for a group turned 30 and 45
    degrees and resized (objlim evidence psizegrpturn, psizegrpturn45; the form rotate5 worked out, within
    0.02). *linear* gives each shape's ``L`` (:func:`stretch_along_page`); by default its ``rotMatrix``'s 2x2 part,
    so a branch for flipped shapes can pass the mirror along. Refused (``shape-rotation-unsupported``) for a group already stretched or holding a group: no
    Hancom-saved document shows those resized."""

    element = shape.element
    size = element.find(f"{_HP}sz")
    old = (_number(size.get("width")) or 0, _number(size.get("height")) or 0) if size is not None else (0, 0)
    shapes = [element] + [child for child in element if child.find(f"{_HP}renderingInfo") is not None]
    for node in shapes:
        sets = [_local(child) for child in node.find(f"{_HP}renderingInfo")]
        scale = node.find(f"{_HP}renderingInfo/{_HC}scaMatrix")
        if node is not element and _local(node) == "container":
            raise _rotation_refused(element, "it holds a group: no Hancom-saved document shows one resized turned")
        if sets != ["transMatrix", "scaMatrix", "rotMatrix"] or scale is None or any(
                abs(value - plain) > 1e-3 for value, plain in zip(_matrix_values(scale), (1, 0, 0, 0, 1, 0))):
            raise _rotation_refused(element, "it is stretched: no Hancom-saved document shows a stretched turned "
                                             "group resized")
    if min(old) <= 0:
        raise _rotation_refused(element, "it has no size")
    factors = (width / old[0], height / old[1])
    for node in shapes:
        stretch_along_page(node, factors, linear(node) if linear is not None else None)
    _set_size(element, "sz", width, height)
    scale_member_text_widths(element, factors[0])
    from ._document_primitives import _clear_paragraph_layout_cache

    _clear_paragraph_layout_cache(shape.paragraph.element)
    shape.paragraph.section.mark_dirty()


def picture_crop(element: Any) -> tuple[int, int, int, int]:
    """How much of the image a picture cuts from its left, top, right and bottom, in the units of its
    ``hp:imgDim`` (the whole image); all 0 when it cuts nothing."""

    clip = element.find(f"{_HP}imgClip")
    dim = picture_original_size(element)
    if clip is None or dim is None:
        return 0, 0, 0, 0
    left, right = _number(clip.get("left")) or 0, _number(clip.get("right")) or 0
    top, bottom = _number(clip.get("top")) or 0, _number(clip.get("bottom")) or 0
    if right <= left or bottom <= top:
        return 0, 0, 0, 0
    return left, top, max(0, dim[0] - right), max(0, dim[1] - bottom)


def picture_original_size(element: Any) -> tuple[int, int] | None:
    """The whole image's size a picture's crop counts in (``hp:imgDim``), or ``None``."""

    dim = element.find(f"{_HP}imgDim")
    if dim is None:
        return None
    width, height = _number(dim.get("dimwidth")) or 0, _number(dim.get("dimheight")) or 0
    return (width, height) if width > 0 and height > 0 else None


def set_picture_crop(obj: Any, crop: tuple[int, int, int, int] | None) -> None:
    """Cut *crop* (left, top, right, bottom, in ``original_size`` units) from a picture's image, ``None`` for
    none, keeping the scale it is drawn at: the picture grows or shrinks by what it shows more or less."""

    element = obj.element
    whole = picture_original_size(element)
    if whole is None:
        raise HwpxValueError(
            "the picture has no hp:imgDim to measure a crop on",
            code="shape-picture-crop-value",
            suggestion="Only a picture that records its whole image size (hp:imgDim) can be cropped.",
        )
    left, top, right, bottom = validate_picture_crop(crop, *whole)
    refuse_resizing_flipped(element, cutting=True)
    info = element.find(f"{_HP}rotationInfo")
    angle = (_number(info.get("angle")) or 0) % 360 if info is not None else 0
    if angle:
        rotation_base_size(element)  # a turned picture is cut as drawn and turned again: refuses what it cannot
    old = picture_crop(element)
    old_kept = (whole[0] - old[0] - old[2], whole[1] - old[1] - old[3])
    new_kept = (whole[0] - left - right, whole[1] - top - bottom)
    factors = (new_kept[0] / old_kept[0], new_kept[1] / old_kept[1])
    for name in ("orgSz", "curSz") + (() if angle else ("sz",)):
        size = element.find(f"{_HP}{name}")
        if size is not None:
            for side, factor in (("width", factors[0]), ("height", factors[1])):
                value = _number(size.get(side)) or 0
                if value:
                    size.set(side, str(max(1, round(value * factor))))
    rect = element.find(f"{_HP}imgRect")
    for point in rect if rect is not None else ():
        for axis, factor in (("x", factors[0]), ("y", factors[1])):
            if point.get(axis) is not None:
                point.set(axis, str(round((_number(point.get(axis)) or 0) * factor)))
    width, height = object_size(element)
    rotation = element.find(f"{_HP}rotationInfo")
    if rotation is not None:
        rotation.set("centerX", str(width // 2))
        rotation.set("centerY", str(height // 2))
    clip = element.find(f"{_HP}imgClip")
    if clip is None:
        from ._document_primitives import _append_child, _reposition_child_after_any

        clip = _append_child(element, f"{_HP}imgClip", {})
        _reposition_child_after_any(element, clip, ("imgRect",))
    for name, value in (("left", left), ("right", whole[0] - right), ("top", top), ("bottom", whole[1] - bottom)):
        clip.set(name, str(value))
    if angle:
        apply_rotation(element, angle, *rotation_base_size(element))
    from ._document_primitives import _clear_paragraph_layout_cache

    _clear_paragraph_layout_cache(obj.paragraph.element)
    obj.paragraph.section.mark_dirty()


def picture_image_value(element: Any, name: str) -> Any:
    """A picture's image adjustment (``hc:img``): ``bright``/``contrast``/``alpha`` as ints (0 when not
    given), ``effect`` as its name (``REAL_PIC`` when not given)."""

    image = element.find(f"{_HC}img")
    value = image.get(name) if image is not None else None
    if name == "effect":
        return value or "REAL_PIC"
    return _number(value) or 0


def line_width_of(element: Any) -> int | None:
    """The border or line width (``hp:lineShape/@width``, HWPUNIT), ``None`` when the object has no line."""

    line = element.find(f"{_HP}lineShape")
    return _number(line.get("width")) if line is not None else None


#: HWPUNIT a millimetre of line width counts as (stable, 7.0): Hancom writes the widths it offers so (0.12 mm 33,
#: 0.5 mm 141). A picture's or drawing shape's ``hp:lineShape/@width`` is this many HWPUNIT per mm, cut to a whole unit.
LINE_WIDTH_UNITS_PER_MM = 283


def line_width_units(line_width_mm: object) -> int:
    """A picture's or drawing shape's line width in mm (``line_width_mm``) as the HWPUNIT ``hp:lineShape/@width``
    holds: counted at :data:`LINE_WIDTH_UNITS_PER_MM` per mm and cut to a whole unit, as Hancom writes the widths
    it offers, so the default 0.12 mm is the 33 6.x wrote and a Hancom-saved picture's 0.5 mm border is 141.
    0 draws no line. A width that is not a finite number of mm from 0 is refused (``shape-picture-border-value``).
    (Stable, 7.0.)"""

    if (isinstance(line_width_mm, bool) or not isinstance(line_width_mm, (int, float))
            or not math.isfinite(line_width_mm) or not 0 <= line_width_mm * LINE_WIDTH_UNITS_PER_MM < 2**31):
        raise HwpxValueError(
            f"line_width_mm must be a width in mm of 0 or more, got {line_width_mm!r}",
            code="shape-picture-border-value",
            context={"argument": "line_width_mm", "value": repr(line_width_mm)},
            suggestion="Pass the line width in mm, e.g. line_width_mm=0.12 (0 draws no line).",
        )
    return int(line_width_mm * LINE_WIDTH_UNITS_PER_MM)


def line_width_mm_of(element: Any) -> float | None:
    """The border or line width (``hp:lineShape/@width``) in mm, to a hundredth -- the widths Hancom offers read
    as offered (33 is 0.12, 141 is 0.5) and give the same HWPUNIT back through :func:`line_width_units`;
    ``None`` when the object has no line."""

    units = line_width_of(element)
    return None if units is None else round(units / LINE_WIDTH_UNITS_PER_MM, 2)


def line_width_mm_for_units(units: object) -> float:
    """The mm that :func:`line_width_units` turns back into exactly *units* (HWPUNIT, an int or a string of
    one): ``(units + 0.5) / 283``, so ``line_width_units(line_width_mm_for_units(n)) == n`` for every *n* -- for a
    caller that holds a HWPUNIT width (a 6.x ``line_width=``, an ``hp:lineShape/@width`` it read) and gives it to a
    ``line_width_mm=`` argument. ``shape-picture-border-value`` when it is not an int from 0. (Stable, 7.0.)"""

    try:
        whole = int(str(units).strip()) if not isinstance(units, bool) else -1
    except ValueError:
        whole = -1
    if not 0 <= whole < 2**31:
        raise HwpxValueError(
            f"a line width in HWPUNIT must be an int from 0, got {units!r}",
            code="shape-picture-border-value",
            context={"argument": "line_width", "value": repr(units)},
            suggestion="Pass the line width in mm as line_width_mm=0.12 (0 draws no line).",
        )
    return (whole + 0.5) / LINE_WIDTH_UNITS_PER_MM


def fill_color_of(element: Any) -> str | None:
    """The solid fill colour (``hc:fillBrush/hc:winBrush/@faceColor``), ``None`` when not filled."""

    brush = element.find(f"{_HC}fillBrush/{_HC}winBrush")
    if brush is None:
        brush = element.find(f"{_HP}fillBrush/{_HC}winBrush")
    color = brush.get("faceColor") if brush is not None else None
    return None if color in (None, "", "none") else color


def _effect_rgb(effect: Any) -> str:
    rgb = effect.find(f"{_HP}effectsColor/{_HP}rgb")
    if rgb is None:
        return "#000000"
    return "#" + "".join(f"{(_number(rgb.get(c)) or 0) & 0xFF:02X}" for c in ("r", "g", "b"))


def _fraction(value: str | None, default: float) -> float:
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default


def picture_shadow(element: Any) -> PictureShadow | None:
    """A picture's shadow (``hp:effects/hp:shadow``) as the :class:`PictureShadow` ``add_picture`` takes."""

    shadow = element.find(f"{_HP}effects/{_HP}shadow")
    if shadow is None:
        return None
    return PictureShadow(
        color=_effect_rgb(shadow), alpha=_fraction(shadow.get("alpha"), 0.0), blur=_number(shadow.get("radius")) or 0,
        direction=_number(shadow.get("direction")) or 0, distance=_number(shadow.get("distance")) or 0,
        inside=shadow.get("style") == "INSIDE",
    )


def picture_glow(element: Any) -> PictureGlow | None:
    """A picture's glow (``hp:effects/hp:glow``) as the :class:`PictureGlow` ``add_picture`` takes."""

    glow = element.find(f"{_HP}effects/{_HP}glow")
    if glow is None:
        return None
    return PictureGlow(color=_effect_rgb(glow), alpha=_fraction(glow.get("alpha"), 0.0),
                       radius=_number(glow.get("radius")) or 0)


def set_equation_script(obj: Any, script: str) -> None:
    """Give an equation the new *script* and the box ``add_equation`` measures for it at the equation's own
    ``baseUnit``: ``hp:sz`` and ``baseLine`` follow the script, so the line it sits on is laid out again."""

    from ..equation.eqedit import MAX_SOURCE_LENGTH

    text = script.strip() if isinstance(script, str) else ""
    if not text:
        raise HwpxValueError(
            "equation script must be a non-empty string",
            code="shape-equation-script-empty",
            suggestion="Pass an equation script in Hancom's language, e.g. '{a} over {b}'.",
        )
    if len(text) > MAX_SOURCE_LENGTH:
        raise HwpxValueError(
            "equation script exceeds size limit",
            code="shape-equation-script-too-large",
            context={"length": len(text), "limit": MAX_SOURCE_LENGTH},
            suggestion="Split the equation.",
        )
    validate_equation_script(text)
    _measure_equation_again(obj, text)


def equation_font_size(element: Any) -> float:
    """An equation's font size in points: its ``baseUnit`` (1/100 pt) / 100; 10.0 (the schema's 1000) when not
    given."""

    value = element.get("baseUnit")
    return (int(value) if value is not None and value.isdigit() else 1000) / 100


def equation_base_unit(font_size: object) -> int:
    """An equation's *font_size* (pt) as the ``baseUnit`` Hancom keeps (1/100 pt, a whole number): a finite
    number of points that comes to at least 0.01 pt, else ``shape-equation-base-unit-value``."""

    if (isinstance(font_size, bool) or not isinstance(font_size, (int, float)) or not math.isfinite(font_size)
            or not 0 < round(font_size * 100) < 2**31):
        raise HwpxValueError(
            f"font_size must be a positive number of points; got {font_size!r}",
            code="shape-equation-base-unit-value",
            context={"argument": "font_size", "value": repr(font_size)},
            suggestion="Pass the equation's font size in points, e.g. font_size=10.0.",
        )
    return round(font_size * 100)


def set_equation_font_size(obj: Any, font_size: float) -> None:
    """Give an equation the font size *font_size* (pt) and the box ``add_equation`` measures for its script at
    that size: ``hp:sz`` and ``baseLine`` follow, and the line it sits on is laid out again."""

    base_unit = equation_base_unit(font_size)
    if obj.element.get("baseUnit") == str(base_unit):
        return
    obj.element.set("baseUnit", str(base_unit))
    node = obj.element.find(f"{_HP}script")
    _measure_equation_again(obj, (node.text or "") if node is not None else "", script=False)


def set_equation_font(obj: Any, font: str) -> None:
    """Give an equation the font *font* (a non-empty font name, e.g. ``HancomEQN`` or ``HYhwpEQ``). Its box stays:
    ``add_equation`` measures one box for either font. The paragraph loses its line layout cache, as Hancom draws
    the script in the new font."""

    name = validate_equation_font(font)
    if obj.element.get("font") == name:
        return
    obj.element.set("font", name)
    from ._document_primitives import _clear_paragraph_layout_cache

    _clear_paragraph_layout_cache(obj.paragraph.element)
    obj.paragraph.section.mark_dirty()


def _measure_equation_again(obj: Any, text: str, *, script: bool = True) -> None:
    """Measure the box and base line of *text* at the equation's ``baseUnit`` and write them, and *text* as its
    script unless *script* is false."""

    from ..equation.measure import measure_equation

    element = obj.element
    base_unit = _number(element.get("baseUnit"))
    measured = measure_equation(text, base_unit=base_unit if base_unit and base_unit > 0 else 1000)
    size = element.find(f"{_HP}sz")
    if size is None:
        from ._document_primitives import _append_child, _reposition_child_before_any

        size = _append_child(element, f"{_HP}sz", {"width": "0", "widthRelTo": "ABSOLUTE", "height": "0",
                                                   "heightRelTo": "ABSOLUTE", "protect": "0"})  # Hancom's order
        _reposition_child_before_any(element, size, ("pos", "outMargin", "shapeComment", "script"))
    size.set("width", str(measured.width))
    size.set("height", str(measured.height))
    element.set("baseLine", str(measured.base_line))
    node = element.find(f"{_HP}script")
    if node is None and script:
        from ._document_primitives import _append_child

        node = _append_child(element, f"{_HP}script", {})
    if script and node is not None:
        node.text = text
    from ._document_primitives import _clear_paragraph_layout_cache

    _clear_paragraph_layout_cache(obj.paragraph.element)
    obj.paragraph.section.mark_dirty()


def _matrix_number(value: float) -> str:
    """A matrix entry as Hancom prints it: six decimals, no trailing zeros."""

    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def validate_shape_size(width: object, height: object) -> tuple[int, int]:
    """*width* and *height* of a shape, picture or equation, checked to be ints in ``0 <= value < 2**31``
    (HWPUNIT): Hancom reads a negative size as 0, and the original size and rotation centre written from it."""

    for argument, value in (("width", width), ("height", height)):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 2**31:
            raise HwpxValueError(
                f"{argument} must be an int in 0 <= {argument} < 2**31 (HWPUNIT); got {value!r}",
                code="shape-size-value",
                context={"argument": argument, "value": repr(value)},
                suggestion="Pass a size from 0 to 2**31 - 1 HWP units (an equation's is measured at its base_unit).",
            )
    return width, height  # type: ignore[return-value]


def validate_box_size(size: object, *, kind: str) -> tuple[int, int]:
    """*size* of an equation or chart: a ``(width, height)`` pair of ints in ``0 < value < 2**31``
    (HWPUNIT). Unlike a line, such a box drawn 0 wide or 0 high shows nothing, so 0 is refused too;
    so is a size that is not a pair (``size=5``)."""

    if isinstance(size, (str, bytes)) or not isinstance(size, (tuple, list)) or len(size) != 2:
        raise HwpxValueError(
            f"{kind} size must be a (width, height) pair of HWP units; got {size!r}",
            code="shape-size-value",
            context={"argument": "size", "value": repr(size)},
            suggestion="Pass size=(width, height), both positive ints in HWP units, or leave it out.",
        )
    width, height = validate_shape_size(size[0], size[1])
    if width == 0 or height == 0:
        raise HwpxValueError(
            f"{kind} size must be positive; got {size!r}",
            code="shape-size-value",
            context={"argument": "size", "value": repr(size)},
            suggestion=f"Leave size out to have the {kind} measured, or pass two positive HWP units.",
        )
    return width, height


def validate_rect_ratio(ratio: object) -> int:
    """A rectangle's corner *ratio* (per cent), checked to be an int in ``0 <= ratio < 2**31``: Hancom reads a
    negative one as 0."""

    if isinstance(ratio, bool) or not isinstance(ratio, int) or not 0 <= ratio < 2**31:
        raise HwpxValueError(
            f"ratio must be an int in 0 <= ratio < 2**31 (per cent); got {ratio!r}",
            code="shape-rect-ratio-value",
            context={"value": repr(ratio)},
            suggestion="Pass the corner roundness in per cent: 0 sharp, 50 a semicircle.",
        )
    return ratio


def validate_equation_base_unit(base_unit: object) -> int:
    """An equation's *base_unit* (1/100 pt), checked to be an int in ``1 <= base_unit < 2**31`` (the 6.x
    ``doc.shapes.add_equation(base_unit=)``; the model takes ``font_size`` in pt, :func:`equation_base_unit`)."""

    if isinstance(base_unit, bool) or not isinstance(base_unit, int) or not 0 < base_unit < 2**31:
        raise HwpxValueError(
            f"base_unit must be positive: an int in 1 <= base_unit < 2**31 (1/100 pt); got {base_unit!r}",
            code="shape-equation-base-unit-value",
            context={"value": repr(base_unit)},
            suggestion="Pass the equation's base font size in 1/100 pt, e.g. 1000 for 10 pt.",
        )
    return base_unit


_LATEX_COMMAND = re.compile(r"\\[A-Za-z]+")


def validate_equation_script(text: str) -> str:
    """Refuse an equation script Hancom would show as typed rather than as an equation.

    A LaTeX command (``\\frac``) is not Hancom's equation language: Hancom's own scripts write
    no backslash (none in 175 equations of Hancom-saved documents), so the backslash and the
    word after it would be drawn as they are (``shape-equation-script-latex``). Braces group in
    Hancom's language too, and a script whose braces do not pair is refused
    (``shape-equation-script-unbalanced``).
    """

    latex = _LATEX_COMMAND.search(text)
    if latex is not None:
        raise HwpxValueError(
            f"equation script holds the LaTeX command {latex.group(0)!r}; it takes Hancom's equation language",
            code="shape-equation-script-latex",
            context={"command": latex.group(0)},
            suggestion="LaTeX 는 hwpx.equation.latex_to_eqedit(r\"\\frac{1}{2}\") 로 바꿔 넘기세요"
            "(한/글 수식: {1} over {2}).",
        )
    depth, closed_early = 0, None
    for position, char in enumerate(text):
        depth += 1 if char == "{" else -1 if char == "}" else 0
        if depth < 0:
            closed_early = position
            break
    if depth != 0:
        raise HwpxValueError(
            "equation script braces do not pair: "
            + (f"the '}}' at {closed_early} closes nothing" if closed_early is not None else f"{depth} '{{' left open"),
            code="shape-equation-script-unbalanced",
            context={"closedEarlyAt": closed_early, "open": max(depth, 0)},
            suggestion="여는 { 와 닫는 } 의 짝을 맞추세요.",
        )
    return text


def validate_equation_font(font: object) -> str:
    """An equation's *font*, checked to be a non-empty font name."""

    if not isinstance(font, str) or not font.strip():
        raise HwpxValueError(
            f"equation font must be a non-empty font name; got {font!r}",
            code="shape-equation-font-empty",
            context={"value": repr(font)},
            suggestion="Leave font out for HancomEQN, or pass a font name such as 'HYhwpEQ'.",
        )
    return font.strip()


def validate_original_size(original_size: object) -> tuple[int, int] | None:
    """Check *original_size* is ``None`` or two positive integers."""

    if original_size is None:
        return None
    try:
        org_width, org_height = original_size  # type: ignore[misc]
    except (TypeError, ValueError):
        org_width = org_height = None
    if not all(
        isinstance(value, int) and not isinstance(value, bool) and value > 0
        for value in (org_width, org_height)
    ):
        raise HwpxValueError(
            f"original_size must be two positive integer HWP units; got {original_size!r}",
            code="shape-original-size-invalid",
            context={"requested": repr(original_size)},
            suggestion="Pass original_size=(width, height), both positive integers.",
        )
    return org_width, org_height  # type: ignore[return-value]


def build_at_original_size(
    factory: "Callable[..., ET.Element]",
    width: int,
    height: int,
    original_size: "tuple[int, int] | None",
    **options: Any,
) -> "ET.Element":
    """Build a shape with *factory* and give it *original_size* as ``orgSz``.

    With *original_size* ``None`` this is ``factory(width, height, **options)``
    unchanged (``orgSz`` equals ``curSz``). Otherwise the shape and its
    geometry are built at the original size, then ``curSz``/``sz`` and the
    rotation centre are set to *width* x *height* and ``scaMatrix`` scales
    between the two. A size that is not two positive integers refuses with
    ``shape-original-size-invalid`` before anything is built.
    """

    checked = validate_original_size(original_size)
    validate_shape_size(width, height)
    if checked is None:
        return factory(width, height, **options)
    org_width, org_height = checked
    element = factory(org_width, org_height, **options)
    for tag in ("curSz", "sz"):
        child = element.find(f"{_HP}{tag}")
        if child is not None:
            child.set("width", str(width))
            child.set("height", str(height))
    rotation = element.find(f"{_HP}rotationInfo")
    if rotation is not None:
        rotation.set("centerX", str(width // 2))
        rotation.set("centerY", str(height // 2))
    scale = element.find(f"{_HP}renderingInfo/{_HC}scaMatrix")
    if scale is not None:
        scale.set("e1", _matrix_number(width / org_width))
        scale.set("e5", _matrix_number(height / org_height))
    return element


def resize_group(shape: "HwpxOxmlShape", width: int, height: int) -> bool:
    """Resize the group *shape* (``hp:container``) the way Hancom does.

    The group keeps ``orgSz``: ``sz`` and ``curSz`` take *width* x *height*
    (``curSz`` 0 on an axis left at ``orgSz``) and the group's ``scaMatrix``
    the factors new over original. Every member, members of groups in it
    included, takes the factors in its first ``scaMatrix``, moved by its
    offset (its ``transMatrix``) times the factor less 1, so the group grows
    from its origin, and takes ``curSz`` = its ``orgSz`` times the factors
    of the groups it is in (rounded down, 0 on an axis they leave alone).
    Offsets, rotation centres and the members' own matrices stay; a member's text is laid out across the width it
    is drawn at (``drawText/@lastWidth``, its line caches dropped), as Hancom writes it. (Hancom's members' centres
    follow no one rule -- kept or moved to the middles drawn at, differently when the same document is saved again
    -- and draw nothing while they are unturned; a turn writes them again.) ``False``, with nothing changed, for a
    group without an original size.
    """

    element = shape.element
    original = element.find(f"{_HP}orgSz")
    sizes = (0, 0) if original is None else (int(original.get("width", "0")), int(original.get("height", "0")))
    if min(sizes) <= 0:
        return False
    factors = (width / sizes[0], height / sizes[1])
    _set_size(element, "sz", width, height)
    _set_size(element, "curSz", width if factors[0] != 1 else 0, height if factors[1] != 1 else 0)
    scale = element.find(f"{_HP}renderingInfo/{_HC}scaMatrix")
    if scale is not None:
        _set_scale(scale, factors, (0.0, 0.0))
    for member, depth in _group_members(element, 1):
        scales = member.findall(f"{_HP}renderingInfo/{_HC}scaMatrix")
        if not scales:
            continue
        trans = member.find(f"{_HP}renderingInfo/{_HC}transMatrix")
        offset = (0.0, 0.0) if trans is None else (float(trans.get("e3", "0")), float(trans.get("e6", "0")))
        _set_scale(scales[0], factors, offset)
        own = member.find(f"{_HP}orgSz")
        if own is None:
            continue
        grown = [factor * math.prod(float(matrix.get(key, "1")) for matrix in scales[1:depth])
                 for factor, key in zip(factors, ("e1", "e5"))]
        _set_size(member, "curSz", *(int(int(own.get(side, "0")) * factor + 1e-6) if factor != 1 else 0
                                      for side, factor in zip(("width", "height"), grown)))
        # a member's text is laid out across the width it is drawn at, as Hancom writes it after resizing the
        # group: flipped or not, set as a character or floating, centred or not, and saved again (a 9000 wide text
        # box drawn at 1.5: 13500; at 1 across: 9000 -- rotate9 g-*-S, rotate7 g-fv-S, rotate10 tc/tf/tm-S, -R)
        draw_text, laid = member.find(f"{_HP}drawText"), _half_up(int(own.get("width", "0")) * grown[0])
        if draw_text is not None and draw_text.get("lastWidth") != str(laid):
            set_text_width(member, laid)  # its lines laid out again (their caches dropped)
    shift_flipped_group(element, sizes, width, height)
    shape.paragraph.section.mark_dirty()
    return True


def _group_members(group: "ET.Element", depth: int) -> "Iterator[tuple[ET.Element, int]]":
    """Each member of *group* at *depth*, then the members of a group among them one deeper."""

    for child in group:
        if child.find(f"{_HP}renderingInfo") is not None:
            yield child, depth
            if child.tag == f"{_HP}container":
                yield from _group_members(child, depth + 1)


def _set_size(element: "ET.Element", tag: str, width: int, height: int) -> None:
    child = element.find(f"{_HP}{tag}")
    if child is not None:
        child.set("width", str(width))
        child.set("height", str(height))


def _set_scale(matrix: "ET.Element", factors: tuple[float, float], offset: tuple[float, float]) -> None:
    """*matrix* scaling by *factors* from the origin of a member at *offset*."""

    for key, value in (("e1", factors[0]), ("e2", 0.0), ("e3", offset[0] * (factors[0] - 1)),
                       ("e4", 0.0), ("e5", factors[1]), ("e6", offset[1] * (factors[1] - 1))):
        matrix.set(key, _matrix_number(value))


__all__ = [
    "CAPTION_SIDES",
    "POS_HORZ_ALIGN",
    "POS_HORZ_REL_TO",
    "POS_VERT_ALIGN",
    "POS_VERT_REL_TO",
    "SUBLIST_VERT_ALIGN",
    "build_at_original_size",
    "resize_group",
    "validate_caption_gap",
    "validate_caption_side",
    "validate_draw_text_vert_align",
    "validate_equation_base_unit",
    "validate_original_size",
    "validate_rect_ratio",
    "validate_shape_size",
    "validate_box_size",
]


@dataclass(frozen=True)
class PictureShadow:
    """A picture's shadow: *color* (``#RRGGBB``), *alpha* (transparency, 0 opaque to 1 not drawn), *blur* (how far
    its edge spreads, HWPUNIT), *direction* (degrees clockwise from the right, 0..359), *distance* (how far it falls
    from the picture, HWPUNIT) and *inside* (drawn inside the picture's edge instead of behind it)."""

    color: str = "#000000"
    alpha: float = 0.5
    blur: int = 600
    direction: int = 45
    distance: int = 600
    inside: bool = False


@dataclass(frozen=True)
class PictureGlow:
    """A glow around a picture: *color* (``#RRGGBB``), *alpha* (transparency, 0 opaque to 1 not drawn) and *radius*
    (how far it reaches out from the picture's edge, HWPUNIT)."""

    color: str = "#FFC000"
    alpha: float = 0.5
    radius: int = 500


@dataclass(frozen=True)
class PictureReflection:
    """A picture's reflection below it: *size* (how much of the picture it shows, over 0 to 1 of its height),
    *distance* (the gap below the picture, HWPUNIT), *alpha_start* and *alpha_end* (its transparency where it
    starts and where it ends, each 0 opaque to 1 not drawn) and *blur* (HWPUNIT)."""

    size: float = 0.5
    distance: int = 0
    alpha_start: float = 0.5
    alpha_end: float = 0.997
    blur: int = 50


def _refuse(argument: str, value: object, rule: str) -> HwpxValueError:
    return HwpxValueError(
        f"{argument} must be {rule}; got {value!r}",
        code="shape-picture-effect-value",
        context={"argument": argument, "value": repr(value)},
        suggestion=f"Pass {argument} as {rule}.",
    )


def _alpha(argument: str, value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise _refuse(argument, value, "a number from 0 to 1")
    return f"{float(value):g}"


def _length(argument: str, value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 2**31:
        raise _refuse(argument, value, "an int from 0 (HWPUNIT)")
    return str(value)


def _rgb(argument: str, value: object) -> tuple[int, int, int]:
    try:
        color = normalize_color(value) if isinstance(value, str) else None
    except HwpxValueError:
        color = None
    if color is None or len(color) != 7:
        raise _refuse(argument, value, "a #RRGGBB colour")
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def validate_picture_effects(shadow: object, glow: object, soft_edge: object = None,
                             reflection: object = None) -> None:
    """Check *shadow* (a :class:`PictureShadow` or ``None``), *glow* (a :class:`PictureGlow` or ``None``),
    *soft_edge* (how far in from its edge the picture fades, HWPUNIT, or ``None``) and *reflection* (a
    :class:`PictureReflection` or ``None``)."""

    if shadow is not None:
        if not isinstance(shadow, PictureShadow):
            raise _refuse("shadow", shadow, "a PictureShadow or None")
        _rgb("shadow.color", shadow.color)
        _alpha("shadow.alpha", shadow.alpha)
        _length("shadow.blur", shadow.blur)
        _length("shadow.distance", shadow.distance)
        direction = shadow.direction
        if isinstance(direction, bool) or not isinstance(direction, int) or not 0 <= direction <= 359:
            raise _refuse("shadow.direction", direction, "an int from 0 to 359 (degrees)")
        if not isinstance(shadow.inside, bool):
            raise _refuse("shadow.inside", shadow.inside, "a bool")
    if glow is not None:
        if not isinstance(glow, PictureGlow):
            raise _refuse("glow", glow, "a PictureGlow or None")
        _rgb("glow.color", glow.color)
        _alpha("glow.alpha", glow.alpha)
        _length("glow.radius", glow.radius)
    if soft_edge is not None:
        _length("soft_edge", soft_edge)
    if reflection is not None:
        if not isinstance(reflection, PictureReflection):
            raise _refuse("reflection", reflection, "a PictureReflection or None")
        size = reflection.size
        if isinstance(size, bool) or not isinstance(size, (int, float)) or not 0 < size <= 1:
            raise _refuse("reflection.size", size, "a number over 0 up to 1")
        _length("reflection.distance", reflection.distance)
        _alpha("reflection.alpha_start", reflection.alpha_start)
        _alpha("reflection.alpha_end", reflection.alpha_end)
        _length("reflection.blur", reflection.blur)


def _append_color(parent: "ET.Element", rgb: tuple[int, int, int]) -> None:
    color = parent.makeelement(f"{_HP}effectsColor", {"type": "RGB", "schemeIdx": "-1", "systemIdx": "-1",
                                                       "presetIdx": "-1"})
    parent.append(color)
    color.append(color.makeelement(f"{_HP}rgb", {"r": str(rgb[0]), "g": str(rgb[1]), "b": str(rgb[2])}))


def append_picture_effects(effects: "ET.Element", shadow: PictureShadow | None, glow: PictureGlow | None,
                           soft_edge: int | None = None, reflection: PictureReflection | None = None) -> None:
    """Write *shadow*, *glow*, *soft_edge* and *reflection* into a picture's ``hp:effects``, in the schema's order
    (shadow, glow, softEdge, reflection), as a Hancom document holds them."""

    validate_picture_effects(shadow, glow, soft_edge, reflection)
    if shadow is not None:
        element = effects.makeelement(f"{_HP}shadow", {
            "style": "INSIDE" if shadow.inside else "OUTSIDE",
            "alpha": _alpha("shadow.alpha", shadow.alpha),
            "radius": _length("shadow.blur", shadow.blur),
            "direction": str(shadow.direction),
            "distance": _length("shadow.distance", shadow.distance),
            "alignStyle": "CENTER",
            "rotationStyle": "0",
        })
        effects.append(element)
        element.append(element.makeelement(f"{_HP}skew", {"x": "0", "y": "0"}))
        element.append(element.makeelement(f"{_HP}scale", {"x": "1", "y": "1"}))
        _append_color(element, _rgb("shadow.color", shadow.color))
    if glow is not None:
        element = effects.makeelement(f"{_HP}glow", {"alpha": _alpha("glow.alpha", glow.alpha),
                                                     "radius": _length("glow.radius", glow.radius)})
        effects.append(element)
        _append_color(element, _rgb("glow.color", glow.color))
    if soft_edge is not None:
        effects.append(effects.makeelement(f"{_HP}softEdge", {"radius": _length("soft_edge", soft_edge)}))
    if reflection is not None:
        element = effects.makeelement(f"{_HP}reflection", {
            "alignStyle": "BOTTOM_LEFT",
            "radius": _length("reflection.blur", reflection.blur),
            "direction": "90",
            "distance": _length("reflection.distance", reflection.distance),
            "rotationStyle": "0",
            "fadeDirection": "90",
        })
        effects.append(element)
        element.append(element.makeelement(f"{_HP}skew", {"x": "0", "y": "0"}))
        element.append(element.makeelement(f"{_HP}scale", {"x": "1", "y": "-1"}))
        element.append(element.makeelement(f"{_HP}alpha", {
            "start": _alpha("reflection.alpha_start", reflection.alpha_start),
            "end": _alpha("reflection.alpha_end", reflection.alpha_end)}))
        element.append(element.makeelement(f"{_HP}pos", {"start": "0", "end": f"{float(reflection.size):g}"}))


# --------------------------------------------------------------------------
# Moving and copying an object to another paragraph (``move_to``/``copy_to`` of objects and tables)


def _local(node: Any) -> str:
    return node.tag.rsplit("}", 1)[-1] if isinstance(node.tag, str) else ""


#: What a ``hp:subList`` belongs to, named as the box its paragraphs sit in.
_SUBLIST_BOXES = {
    "tc": "cell", "drawText": "text_box", "footNote": "note", "endNote": "note", "header": "header_footer",
    "footer": "header_footer", "caption": "caption", "fieldBegin": "memo",
}

#: The boxes Hancom documents hold objects in, by how the object is placed: ``char`` (as a character),
#: ``paragraph`` (floating, measured from its paragraph: ``PARA``/``COLUMN``) and ``page`` (floating,
#: measured from the page or paper on either axis). Counted over the 1,304 public documents (rhwp
#: samples, kordoc fixtures, the repository's fixtures): floating objects sit in table cells 634 times,
#: in notes 40, in text boxes 2 -- every one of them measured from its paragraph -- and in headers and
#: footers 7 (from the paragraph or the paper); none sits in a caption. In a cell, a text box or a note
#: the object must also be kept in the page area or measured across from its paragraph
#: (:func:`_stays_in_box`). This is what a *table* moved or copied there must meet (no Hancom paste of
#: one has been seen); a picture, equation, chart, OLE or drawing object is placed there as Hancom pastes
#: it instead (:func:`pasted_placement`).
OBJECT_PLACES: dict[str, frozenset[str]] = {
    "char": frozenset({"body", "cell", "text_box", "note", "header_footer", "caption"}),
    "paragraph": frozenset({"body", "cell", "text_box", "note", "header_footer"}),
    "page": frozenset({"body", "header_footer"}),
}

def paragraph_box(paragraph: Any, root: Any) -> str:
    """The box the paragraph element *paragraph* sits in under *root* (its section element): ``body``,
    ``cell``, ``text_box``, ``note``, ``header_footer``, ``caption``, ``memo`` or ``other``."""

    parent = _parent_of(paragraph, root)
    if parent is None:
        return "other"
    if parent is root:
        return "body"
    name = _local(parent)
    if name == "subList":
        owner = _parent_of(parent, root)
        return _SUBLIST_BOXES.get(_local(owner) if owner is not None else "", "other")
    return "memo" if name == "paraList" else "other"


def placement_kind(element: Any) -> str:
    """How an object is placed: ``char`` (as a character, or without ``hp:pos``), ``page`` (floating and
    measured from the page or paper on either axis) or ``paragraph`` (floating, from its paragraph)."""

    position = element.find(f"{_HP}pos")
    if position is None or position.get("treatAsChar") not in (*_FALSE_FLAGS, None):
        return "char"
    frames = (position.get("vertRelTo"), position.get("horzRelTo"))
    return "page" if any(frame in ("PAGE", "PAPER") for frame in frames) else "paragraph"


def _page_settings(section: Any) -> tuple[dict[str, str], dict[str, str]]:
    """The section's paper (``hp:pagePr``: width, height, landscape) and margins (``hp:margin``)."""

    page = section.element.find(f".//{_HP}secPr/{_HP}pagePr")
    margin = page.find(f"{_HP}margin") if page is not None else None
    return (dict(page.attrib) if page is not None else {}), (dict(margin.attrib) if margin is not None else {})


def _place_refused(element: Any, box: str, why: str) -> HwpxValueError:
    position = element.find(f"{_HP}pos")
    frames = {name: position.get(name) for name in ("vertRelTo", "horzRelTo", "flowWithText")}         if position is not None else {}
    return HwpxValueError(
        f"hp:{_local(element)} cannot go there: {why}",
        code="shape-move-place-unsupported",
        context={"box": box, "placement": placement_kind(element), "reason": why, **frames},
        suggestion="글자처럼 취급하는 개체는 본문·표 칸·글상자·각주·머리말·꼬리말 어디로든 옮길 수 있습니다. "
                   "떠 있는 개체를 칸·글상자·각주로 옮기려면 먼저 set_position(vertical_relative_to='PARA', "
                   "horizontal_relative_to='PARA')으로 문단 기준·쪽 영역 안으로 바꾼 뒤(또는 treat_as_char=True) 옮기세요. "
                   "값을 몰래 바꾸지 않으므로 바꾸기 전에는 거부합니다.",
    )


#: The boxes whose floating objects Hancom keeps inside the page area of their paragraph.
_BOXED = frozenset({"cell", "text_box", "note"})


def _stays_in_box(element: Any) -> bool:
    """Whether a floating object Hancom documents hold in a table cell, text box or note is placed so:
    measured down from its paragraph (``vertRelTo="PARA"``) and either kept in the page area
    (``flowWithText="1"``) or measured across from its paragraph too (``horzRelTo="PARA"``). In the public
    documents (1,304): of 634 floating objects in cells, 343 are PARA/PARA/1, 257 PARA/COLUMN/1, 33
    PARA/PARA/0 and 1 PARA/COLUMN/0; all 40 in notes and both in text boxes are kept in the page area.
    A PARA/COLUMN/0 picture moved into a cell, Hancom draws over the cells above it."""

    position = element.find(f"{_HP}pos")
    if position is None:
        return True
    return position.get("vertRelTo") == "PARA" and (
        position.get("flowWithText") in ("1", "true") or position.get("horzRelTo") == "PARA")


def _nearest_paragraph(node: Any) -> Any:
    """The innermost ``hp:p`` holding *node* (lxml only), or ``None``."""

    getparent = getattr(node, "getparent", None)
    current = getparent() if getparent is not None else None
    while current is not None and _local(current) != "p":
        current = current.getparent()
    return current


def _detach_object(element: Any, parent: Any, paragraph: Any, section: Any) -> None:
    """Take *element* (an object) out of *parent* in the paragraph element *paragraph*, as ``remove()``
    does: a run left empty goes (not the last), a connector attached to it lets go, the paragraph and
    the paragraphs holding it lose their line layout caches."""

    from ._document_primitives import _clear_paragraph_layout_cache

    ids = {node.get("instid") for node in element.iter() if node.get("instid") not in (None, "", "0")}
    parent.remove(element)
    if (_local(parent) == "run" and len(parent) == 0
            and len(paragraph.findall(f"{_HP}run")) > 1 and any(child is parent for child in paragraph)):
        paragraph.remove(parent)
    if ids:
        for connector in section.element.iter(f"{_HP}connectLine"):
            for end in connector:
                if _local(end) in ("startPt", "endPt") and end.get("subjectIDRef") in ids:
                    end.set("subjectIDRef", "0")
    _clear_paragraph_layout_cache(paragraph)
    section.mark_dirty()


def _let_go_of_outside(element: Any, kept: dict[str, str]) -> None:
    """Point the connector ends inside *element* at the objects they follow (*kept*: old instid to the
    one it now has); an end attached to an object outside *element* lets go (``subjectIDRef="0"``)."""

    for connector in element.iter(f"{_HP}connectLine"):
        for end in connector:
            subject = end.get("subjectIDRef")
            if _local(end) in ("startPt", "endPt") and subject not in (None, "", "0"):
                end.set("subjectIDRef", kept.get(subject, "0"))


def fresh_copy(element: Any, *, ids: "IdSource | None") -> Any:
    """A copy of the object *element* with fresh ids (objects, tables, paragraphs, fields), no line
    layout caches and its connectors following the copied objects."""

    from copy import deepcopy

    from ._document_primitives import _clear_paragraph_layout_cache, _refresh_copied_paragraph_subtree_ids
    from ._paragraph_text_edit import renumber_copied_fields

    copy = deepcopy(element)
    copy.tail = None
    before = [(node, node.get("instid")) for node in copy.iter() if node.get("instid") not in (None, "", "0")]
    members = [node for node in copy.iter() if _local(node) != "p" and node.get("id") == "0"]
    _refresh_copied_paragraph_subtree_ids(copy, ids=ids)  # every object's id, as for a paragraph's copy
    for node in members:  # a group member's id="0", as Hancom writes members, stays
        node.set("id", "0")
    _let_go_of_outside(copy, {old: str(node.get("instid")) for node, old in before})
    renumber_copied_fields(copy, ids=ids)
    for node in copy.iter():
        if _local(node) == "p":
            _clear_paragraph_layout_cache(node)
    return copy


def insert_at_offset(paragraph: Any, element: Any, offset: int | None, char_pr_id_ref: str | None = None) -> None:
    """Put *element* into the runs of the paragraph element *paragraph* in front of character *offset*
    (``None``: at the end), counted as ``paragraph.text`` counts.

    Controls and objects already at that place stay in front of it. Inside a text node the node is
    divided and *element* goes between its halves in the same run, as Hancom keeps an object among the
    text of a run; at a run boundary it goes at the end of the run before. At the end of the paragraph
    it goes in front of a trailing empty ``hp:t`` of the last run, Hancom's own form. A paragraph with
    no run gets one (*char_pr_id_ref*, else ``"0"``).
    """

    from .formatting import _split_text_element, _unit_length

    runs = [child for child in paragraph if _local(child) == "run"]
    if not runs:
        run = paragraph.makeelement(f"{_HP}run", {"charPrIDRef": char_pr_id_ref or "0"})
        caches = [index for index, child in enumerate(paragraph) if _local(child).lower() == "linesegarray"]
        paragraph.insert(caches[0] if caches else len(paragraph), run)
        run.append(element)
        return
    if offset is not None:
        position = 0
        for run_index, run in enumerate(runs):
            for index, child in enumerate(list(run)):
                length = _unit_length(child)
                if not length:
                    continue
                if position >= offset:
                    if index or not run_index:
                        run.insert(index, element)
                    else:
                        runs[run_index - 1].append(element)
                    return
                if offset < position + length:
                    right = _split_text_element(child, offset - position)
                    run.insert(index + 1, element)
                    run.insert(index + 2, right)
                    return
                position += length
    last = runs[-1]
    tail = last[-1] if len(last) else None
    if tail is not None and _local(tail) == "t" and not (tail.text or "") and not len(tail):
        # Hancom keeps a run's trailing empty ``hp:t`` last and puts objects in front of it
        # (``[obj][t/]``), as its own saved files do; an object after it would be a different shape.
        last.insert(len(last) - 1, element)
        return
    last.append(element)


#: The boxes Hancom fits a pasted floating object into (:func:`pasted_placement`).
_PASTE_FITTED = frozenset({"cell", "text_box", "note", "caption"})


def pasted_placement(element: Any) -> dict[str, str]:
    """The ``hp:pos`` attributes Hancom 2024 changes when it pastes the floating object *element* into a table
    cell, a text box, a note or a caption (``{}`` when it changes none), each axis on its own:

    - down: an object not measured from its paragraph (``vertRelTo`` PAGE or PAPER) or not kept in the page
      area (``flowWithText="0"``) is measured from its paragraph at offset 0, kept in the area and not let
      overlap: ``vertRelTo="PARA"``, ``vertOffset="0"``, ``flowWithText="1"``, ``allowOverlap="0"``;
    - across: one measured from the page or paper (``horzRelTo`` PAGE or PAPER) is measured from the column
      at offset 0: ``horzRelTo="COLUMN"``, ``horzOffset="0"``; this leaves ``allowOverlap`` as it is.

    An object measured from its paragraph and kept in the area keeps everything (its offsets too). Hancom
    2024 pasted nine placements into text boxes, cells, notes and captions and wrote exactly this (objlim
    evidence o01/o10: PAGE/PAGE, PAPER/PAPER, PAGE/COLUMN, PARA/PAGE, PARA/COLUMN with flowWithText 0 and
    allowOverlap 1 or 0, PARA/PARA with flowWithText 0; PARA/COLUMN and PARA/PARA kept in the area stayed). The
    cell ones opened again in Hancom 2024 (cl0, cl1d, cl2, cl5; cl1s, cl1b, cl1c opened by hand).
    """

    position = element.find(f"{_HP}pos")
    if position is None or position.get("treatAsChar") not in _FALSE_FLAGS:
        return {}
    changes: dict[str, str] = {}
    if position.get("vertRelTo") != "PARA" or position.get("flowWithText") in _FALSE_FLAGS:
        changes.update(vertRelTo="PARA", vertOffset="0", flowWithText="1", allowOverlap="0")
    if position.get("horzRelTo") in ("PAGE", "PAPER"):
        changes.update(horzRelTo="COLUMN", horzOffset="0")
    return {name: value for name, value in changes.items() if position.get(name) != value}


def _top_z_order(section: Any, *, skip: Any = None) -> str:
    """One more than the highest ``zOrder`` in the document of *section* (its sections; *section*'s part alone
    when it has no document), *skip* (an element) left out: Hancom gives a pasted or a new object the top one.

    Hancom numbers objects across the document, not per section: in its documents with objects in several
    sections a later section's numbers go on from the earlier ones' (hwpxlib_corpus ``error__20251107__test``:
    0-4 then 5-30; ``error__20250808__…``: 0-554 then 557)."""

    document = getattr(section, "document", None)
    parts = list(document.sections) if document is not None else [section]
    if not any(part is section or part.element is section.element for part in parts):
        parts.append(section)
    highest = -1
    # it and its members; the set holds them, so lxml hands out the same proxies below
    inside = set(skip.iter()) if skip is not None else set()
    for part in parts:
        root = part.element
        nodes = root.iter(*_Z_ORDERED) if hasattr(root, "getparent") else (
            node for node in root.iter() if node.tag in _Z_ORDERED_SET)  # a stdlib tree's iter takes one tag
        for node in nodes:
            if node in inside:
                continue
            order = _number(node.get("zOrder"))
            if order is not None and order > highest:
                highest = order
    return str(highest + 1)


#: The elements that carry a ``zOrder`` (OWPML AbstractShapeObjectType and its kinds).
_Z_ORDERED = tuple(f"{_HP}{name}" for name in (
    "tbl", "pic", "equation", "rect", "ellipse", "line", "arc", "polygon", "curve", "connectLine", "container",
    "ole", "chart", "textart", "video",
))
_Z_ORDERED_SET = frozenset(_Z_ORDERED)


def stack_new_object(element: Any, section: Any) -> None:
    """Give the new object *element* (already in *section*) the next ``zOrder`` of the document, as Hancom
    numbers the objects it makes: each one over those made before it (hancom_saved: in the documents whose
    objects Hancom made, tables and objects placed like characters take their numbers too, and a group the
    number after its members'). A member of a group is not given one (Hancom saves members with 0). Its id
    (and those of the objects inside it) is one no other object of the document has
    (:func:`unique_object_ids`)."""

    unique_object_ids(section, (element,))
    parent = element.getparent() if hasattr(element, "getparent") else None
    if parent is not None and _local(parent) == "container":
        return
    element.set("zOrder", _top_z_order(section, skip=element))


def unique_object_ids(section: Any, roots: "Iterable[Any]") -> int:
    """Give each object in *roots* (elements just made or copied into the document of *section*) whose
    ``id`` another object of the document already has -- outside *roots*, or earlier in them -- a fresh one,
    and return how many changed. Hancom keeps object ids unique: in the 1,017 Hancom-saved fixtures with
    objects no two outside a group share one (members are written ``id="0"``, left alone here). An
    ``instid`` equal to the old id follows it. The fresh ids come from the source of *section*'s document
    (``HwpxDocument.new(seed=)`` stays repeatable; another document's seed is never used)."""

    from ._document_primitives import _object_id

    roots = tuple(roots)
    inside = {node for root in roots for node in root.iter()}
    document = getattr(section, "document", None)
    parts = list(document.sections) if document is not None else [section]
    if not any(part is section or part.element is section.element for part in parts):
        parts.append(section)
    taken: set[str] = set()
    for part in parts:
        for node in _object_nodes(part.element):
            if node not in inside and node.get("id") not in (None, "", "0"):
                taken.add(str(node.get("id")))
    changed = 0
    for root in roots:
        for node in _object_nodes(root, include_root=True):
            old = node.get("id")
            if old in (None, "", "0"):
                continue
            if old in taken:
                ids = section._ids  # the source of the document the objects are in
                fresh = _object_id(ids)
                while fresh in taken:
                    fresh = _object_id(ids)
                node.set("id", fresh)
                if node.get("instid") == old:
                    node.set("instid", fresh)
                changed += 1
            taken.add(str(node.get("id")))
    return changed


def _object_nodes(root: Any, *, include_root: bool = False) -> "Iterator[Any]":
    """The objects (:data:`_Z_ORDERED`) under *root*, in document order (*root* too with *include_root*)."""

    if hasattr(root, "getparent"):
        for node in root.iter(*_Z_ORDERED):
            if include_root or node is not root:
                yield node
        return
    for node in root.iter():
        if node.tag in _Z_ORDERED_SET and (include_root or node is not root):
            yield node


def _check_place(element: Any, source: Any, target: Any) -> dict[str, str]:
    """Refuse a place *target* (a paragraph) where the object *element*, coming from the paragraph *source*,
    is not put the way Hancom puts it, and return the ``hp:pos`` changes it takes there
    (:func:`pasted_placement`; tables meet :data:`OBJECT_PLACES` and take none)."""

    box = paragraph_box(target.element, target.section.element)
    kind = placement_kind(element)
    if _local(element) != "tbl" and box not in ("memo", "other"):
        changes = pasted_placement(element) if kind != "char" and box in _PASTE_FITTED else {}
        return changes
    if box not in OBJECT_PLACES.get(kind, frozenset()):
        if box in ("memo", "other"):
            why = "objects go into the body, a cell, a text box, a note, a header or a footer"
        elif kind == "paragraph":
            why = f"Hancom documents hold no floating object in a {box.replace('_', ' ')}"
        else:
            why = f"Hancom measures an object in a {box.replace('_', ' ')} from its paragraph, not from the page"
        raise _place_refused(element, box, why)
    if kind == "paragraph" and box in _BOXED and not _stays_in_box(element):
        raise _place_refused(element, box, f"Hancom draws a floating object in a {box.replace('_', ' ')} where it "
                                           "belongs only when it is measured from its paragraph and kept in the "
                                           "page area (vertRelTo PARA, and flowWithText 1 or horzRelTo PARA)")
    if kind == "page" and target.section.element is not source.section.element             and _page_settings(target.section) != _page_settings(source.section):
        raise _place_refused(element, box, "it is measured from the page, and that section's paper or margins differ")
    return {}


def _place_in_other_document(obj: Any, parent: Any, source: Any, target: Any, offset: int | None, *,
                             copy: bool, keep_order: bool = False) -> Any:
    """``copy_to``/``move_to`` of *obj* into the paragraph *target* of another document, as Hancom 2024 pastes
    an object copied (or cut) from another document: a copy with fresh ids, the images and charts it shows
    carried into that document (``media.carry_object_parts``; objlim evidence xpic, xeq, xchart, xpic2, xchart2),
    placed there as in the same document (:func:`_check_place`). A move removes the original after that, as
    cutting does. A connector (or an object holding one) is refused: pasted into another document it lets go of
    its shapes, and Hancom 2024 draws it nowhere (xconn, and the engine's copy opened in Hancom, objlim-xdoc).

    An object holding text -- a text box, a caption, a table -- is refused (``shape-copy-document-unsupported``):
    Hancom 2024 stopped on the document it pasted a text box into from another document (xbox2, xbox2b), and
    text brings paragraph and character shapes; ``hwpx.tools.document_merge.insert_document`` carries those."""

    from .._document.media import carry_object_parts
    from ._document_primitives import _clear_paragraph_layout_cache
    from .formatting import _check_offset

    element = obj.element
    if _local(element) == "connectLine" or element.find(f".//{_HP}connectLine") is not None:
        raise HwpxValueError(
            "a connector is not copied into another document: it lets go of its shapes there, and Hancom 2024 "
            "draws such a connector nowhere (objlim evidence xconn, objlim-xdoc)",
            code="shape-copy-document-unsupported",
            context={"caller": "copy_to" if copy else "move_to", "object": _local(element)},
            suggestion="연결선은 이은 도형과 함께 문서 끼워 넣기(insert_document)로 가져오세요(연결이 이어진 채 옵니다).",
        )
    if element.find(f".//{_HP}subList") is not None or _local(element) == "tbl":
        raise HwpxValueError(
            "an object holding text (a text box, a caption, a table) is not copied into another document",
            code="shape-copy-document-unsupported",
            context={"caller": "copy_to" if copy else "move_to", "object": _local(element)},
            suggestion="글이 든 개체는 문서 끼워 넣기(hwpx.tools.document_merge.insert_document)로 가져오세요. "
                       "한/글 2024는 다른 문서에서 붙인 글상자가 든 문서를 다시 열지 못했습니다.",
        )
    changes = _check_place(element, source, target)
    if offset is not None:
        _check_offset("offset", offset, 0, len(target.text))
    placed = fresh_copy(element, ids=target.section._ids)
    carry_object_parts(placed, source.section.document, target.section.document)
    position = placed.find(f"{_HP}pos")
    if position is not None:
        for name, value in changes.items():
            position.set(name, value)
    if placed.get("zOrder") is not None and not keep_order:
        placed.set("zOrder", _top_z_order(target.section))
    insert_at_offset(target.element, placed, offset, target.char_pr_id_ref)
    unique_object_ids(target.section, (placed,))
    _clear_paragraph_layout_cache(target.element)
    target.section.mark_dirty()
    from .objects import wrap_object

    if copy:
        return wrap_object(placed, target)
    images = binary_references(element)
    _detach_object(element, parent, source.element, source.section)
    remove_orphaned_images(source.section, images)
    obj.element = placed
    obj.paragraph = target
    return None


def _sections_of(*paragraphs: Any) -> list[Any]:
    """The sections of the document the paragraphs belong to (theirs alone without a document)."""

    document = paragraphs[0].section.document
    if document is not None:
        return list(document.sections)
    return list({id(p.section): p.section for p in paragraphs}.values())


def place_object(obj: Any, paragraph: Any, offset: int | None, *, copy: bool, keep_order: bool = False) -> Any:
    """``move_to``/``copy_to`` of an object or table *obj*: check everything, then move it (or put a
    copy) into *paragraph* at *offset*. Returns the copy's model object, or ``None`` for a move.
    *keep_order* leaves the object's ``zOrder`` as it is instead of putting it over the others."""

    from ._document_primitives import _clear_paragraph_layout_cache
    from ._paragraph_text_edit import resolve_paragraph_in
    from .formatting import _check_offset
    from .memo import carry_memos, renew_copied_memos

    caller = "copy_to" if copy else "move_to"
    element = obj.element
    source = obj.paragraph
    parent = _parent_of(element, source.element)
    holder = _nearest_paragraph(parent) if parent is not None and hasattr(parent, "getparent") else source.element
    if parent is None or holder is None or not any(child is element for child in parent):
        raise HwpxValueError(
            "the object is no longer in a paragraph (it was removed)",
            code="shape-not-in-document",
            context={"caller": caller},
            suggestion="Take the object again from paragraph.objects of the document.",
        )
    if _local(parent) == "container":
        raise _group_member_refused("copied" if copy else "moved")
    source = resolve_paragraph_in(source, source.__class__(holder, source.section), caller=caller)
    other = getattr(getattr(paragraph, "section", None), "document", None)
    if other is not None and source.section.document is not None and other is not source.section.document:
        return _place_in_other_document(obj, parent, source, resolve_paragraph_in(paragraph, paragraph, caller=caller),
                                        offset, copy=copy, keep_order=keep_order)
    target = resolve_paragraph_in(source, paragraph, caller=caller)
    if not copy and any(node is target.element for node in element.iter()):
        raise HwpxValueError(
            "an object cannot move into one of its own paragraphs (its text box, cell or caption)",
            code="shape-move-into-itself",
            context={"caller": caller},
            suggestion="Pick a paragraph outside the object, or copy it there with copy_to().",
        )
    changes = _check_place(element, source, target)
    if offset is not None:
        _check_offset("offset", offset, 0, len(target.text))
    if copy:
        placed = fresh_copy(element, ids=target.section._ids)
        renew_copied_memos(placed, _sections_of(source), target.section)
    else:
        _detach_object(element, parent, source.element, source.section)
        inside = {node.get("instid") for node in element.iter() if node.get("instid") not in (None, "", "0")}
        _let_go_of_outside(element, {value: value for value in inside if value})
        placed = element
    position = placed.find(f"{_HP}pos")
    if position is not None:
        for name, value in changes.items():
            position.set(name, value)
    if (copy or _local(placed) != "tbl") and placed.get("zOrder") is not None and not keep_order:
        placed.set("zOrder", _top_z_order(target.section))  # Hancom puts a pasted object (a copied table too) on top
    insert_at_offset(target.element, placed, offset, target.char_pr_id_ref)
    if copy:
        unique_object_ids(target.section, (placed,))
    _clear_paragraph_layout_cache(target.element)
    if not copy and target.section.element is not source.section.element:
        carry_memos(placed, _sections_of(source, target), target.section)
    from .note_authoring import renumber_notes_holding

    renumber_notes_holding(target.section, (placed,))  # a copy repeats its notes' numbers; a move reorders
    target.section.mark_dirty()
    if copy:
        from .objects import wrap_object

        return wrap_object(placed, target)
    obj.paragraph = target
    return None
