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

import math
import re
from dataclasses import dataclass
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from ..errors import HwpxValueError
from ._document_primitives import _HC, _HP
from .color import normalize_color

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET

    from ..objects.results import CellMargins, ObjectPosition
    from .objects import HwpxOxmlShape
    from .paragraph import HwpxOxmlParagraph

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


def validate_picture_align(align: object) -> str | None:
    """A new picture's *align* as its ``hp:pos@horzAlign``, any case (``"left"`` is ``LEFT``); ``None`` when it is
    not given. Hancom reads a value outside :data:`POS_HORZ_ALIGN` as ``LEFT``, so one is refused."""

    if align is None or align == "":
        return None
    return _require_member(align.upper() if isinstance(align, str) else align, POS_HORZ_ALIGN, argument="align",
                           code="shape-position-frame")


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


def validate_draw_text_vert_align(vert_align: str | None) -> str | None:
    """Check ``set_draw_text``'s *vert_align* (``hp:subList/@vertAlign``)."""

    if vert_align is None:
        return None
    return _require_member(
        vert_align, SUBLIST_VERT_ALIGN, argument="vert_align", code="shape-draw-text-vert-align"
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
    horz_rel_to: str | None = None,
    vert_rel_to: str | None = None,
    horz_align: str | None = None,
    vert_align: str | None = None,
) -> None:
    """Place an object (equation, picture, OLE, text art...): as a character in the line or
    floating, how the text goes around it, and where it floats.

    *treat_as_char* writes ``hp:pos/@treatAsChar`` (``True``: one character in the line;
    ``False``: floating). *text_wrap* writes the object's ``textWrap``, one of
    :data:`TEXT_WRAPS` (``TOP_AND_BOTTOM``: text above and below only; ``SQUARE``: around its
    box; ``BEHIND_TEXT``/``IN_FRONT_OF_TEXT``: under or over the text). The offsets (HWP units,
    signed 32-bit) and the reference frames and alignment take the values
    :meth:`HwpxOxmlShape.set_position` takes. ``None`` leaves a setting as it is. Offsets are
    only for a floating object: given while it stays a character they are refused
    (``shape-position-unsupported``). Everything is checked before anything changes; the
    paragraph loses its line layout cache.
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
        ("vert_rel_to", "vertRelTo", vert_rel_to, POS_VERT_REL_TO),
        ("horz_rel_to", "horzRelTo", horz_rel_to, POS_HORZ_REL_TO),
        ("vert_align", "vertAlign", vert_align, POS_VERT_ALIGN),
        ("horz_align", "horzAlign", horz_align, POS_HORZ_ALIGN),
    ):
        if requested is not None:
            frames[attribute] = _require_member(requested, allowed, argument=argument, code="shape-position-frame")
    if treat_as_char is not None:
        frames["treatAsChar"] = "1" if treat_as_char else "0"
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
    frames of the shapes it joins. The object then meets what moving one into such a box asks
    (:func:`_stays_in_box`).
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


_Placed = TypeVar("_Placed", bound="ObjectPlacement")


class ObjectPlacement:
    """Reads and edits every placed object shares: pictures, equations, charts, OLE and drawing shapes.

    Mixed into ``model.InlineObject`` and ``model.Shape``. The reads take the names the writes take:
    ``position`` answers ``set_position``, ``z_order`` ``set_z_order``, ``rotation`` ``set_rotation``
    and ``description`` ``set_description``.
    """

    element: Any
    paragraph: Any

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
            horz_rel_to=attrs.get("horzRelTo"),
            vert_rel_to=attrs.get("vertRelTo"),
            horz_align=attrs.get("horzAlign"),
            vert_align=attrs.get("vertAlign"),
            horizontal_offset=_signed_offset(attrs.get("horzOffset")),
            vertical_offset=_signed_offset(attrs.get("vertOffset")),
            flow_with_text=flag("flowWithText"),
            allow_overlap=flag("allowOverlap"),
        )

    @property
    def z_order(self) -> int:
        """The object's ``zOrder``: objects with a higher one are drawn over those with a lower one."""

        return _number(self.element.get("zOrder")) or 0

    @property
    def locked(self) -> bool:
        """Whether the object is locked (``lock``, Hancom's 개체 보호하기): it cannot be selected,
        moved or resized in Hancom. Read only."""

        return (self.element.get("lock") or "").strip() not in _FALSE_FLAGS | {""}

    @property
    def numbering_type(self) -> str:
        """Which caption numbering the object counts in (``numberingType``): ``"PICTURE"``,
        ``"TABLE"``, ``"EQUATION"`` or ``"NONE"`` (the schema default, also when not given). Read only."""

        return self.element.get("numberingType") or "NONE"

    def set_z_order(self, z_order: int) -> None:
        """Set ``zOrder`` (a signed 32-bit int; a higher one is drawn over a lower one)."""

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
            raise _group_member_refused("given outer margins")
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
        """The angle the object is turned by, in degrees clockwise (``hp:rotationInfo/@angle``); 0 when it has none."""

        info = self.element.find(f"{_HP}rotationInfo")
        return (_number(info.get("angle")) or 0) if info is not None else 0

    def set_rotation(self, angle: int) -> None:
        """Turn the object *angle* degrees clockwise (0..359) about its middle, as Hancom saves a turned object.

        The object keeps its own size (``hp:orgSz``) and the size it is drawn at (``hc:scaMatrix``,
        ``hp:curSz``: a picture after ``resize`` is drawn smaller or larger); its box (``hp:sz``) becomes the
        box around the turned object, the object as drawn is turned about its own middle (``hc:rotMatrix``)
        and moved into that box (``hp:offset``, ``hc:transMatrix``), and ``hp:rotationInfo`` holds the angle
        and the middle of the box -- the relation the turned objects of Hancom-saved documents show,
        stretched or not (see :func:`rotation_base_size`). Refused with ``shape-rotation-unsupported``:
        a shape holding text -- Hancom draws the text level, laid out across the box around the turned
        shape (it saves ``drawText/@lastWidth`` as that box's width and breaks the lines in it), so the
        text sticks out of the turned shape; no public Hancom document holds a turned shape with text in
        another form. A group -- Hancom draws each member from its own matrices, so turning a group means
        turning every member in them, which one public Hancom group (turned 180 degrees inside another)
        cannot settle for other angles. A flipped object, and an object without ``hp:rotationInfo`` (an
        equation or chart). A member of a group is refused with ``shape-group-member-unsupported``, an
        angle outside 0..359 with ``shape-rotation-value``. 0 turns it back. The paragraph loses its line
        layout cache.
        """

        if isinstance(angle, bool) or not isinstance(angle, int) or not 0 <= angle <= 359:
            raise HwpxValueError(
                f"angle must be an int from 0 to 359 (degrees); got {angle!r}",
                code="shape-rotation-value",
                context={"value": repr(angle)},
                suggestion="Pass the angle in whole degrees clockwise, 0 to 359.",
            )
        if _in_group(self.element, self.paragraph.element):
            raise _group_member_refused("turned")
        width, height = rotation_base_size(self.element)  # refuses what is not known to turn this way
        draw_text = self.element.find(f"{_HP}drawText")
        if angle and draw_text is not None and any((t.text or "").strip() for t in draw_text.iter(f"{_HP}t")):
            # Hancom lays the text out level in the box around the turned shape, not turned with it: text
            # boxes turned 30-270 degrees, opened and saved again by Hancom, came back with lastWidth set to
            # that box's width and the text drawn across it, outside the shape. No public Hancom document
            # (1,338 .hwpx, 304 .hwp) holds a turned shape with text to show another form.
            raise _rotation_refused(self.element, "it holds text, which Hancom does not turn with it")
        apply_rotation(self.element, angle, width, height)
        from ._document_primitives import _clear_paragraph_layout_cache

        _clear_paragraph_layout_cache(self.paragraph.element)
        self.paragraph.section.mark_dirty()

    @property
    def description(self) -> str:
        """The object's description (``hp:shapeComment``), the text Hancom gives as its alternative text;
        ``""`` when it has none."""

        comment = self.element.find(f"{_HP}shapeComment")
        return (comment.text or "") if comment is not None else ""

    def set_description(self, text: str) -> None:
        """Set the object's description (``hp:shapeComment``), its alternative text. ``""`` empties it.
        A member of a group carries none and is refused (``shape-group-member-unsupported``)."""

        if not isinstance(text, str):
            raise HwpxValueError(
                f"description must be a str; got {type(text).__name__}",
                code="shape-description-value",
                context={"type": type(text).__name__},
                suggestion="Pass the description as text; '' empties it.",
            )
        if _in_group(self.element, self.paragraph.element):
            raise _group_member_refused("described")
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
        refused (``shape-group-member-unsupported``, with ``context["reason"]``) for a group's only member
        and where a group or a member of one is turned, flipped or stretched otherwise than so. A second
        call does nothing; the object should not be used after it.
        """

        element = self.element
        paragraph = self.paragraph.element
        parent = _parent_of(element, paragraph)
        if parent is None or not any(child is element for child in parent):
            return
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
        images = binary_references(element) if remove_orphaned else set()
        _detach_object(element, parent, paragraph, self.paragraph.section)
        if groups:  # the groups fit the members left, so only after it went
            from .container import fit_groups_after_removal

            fit_groups_after_removal(groups)
        remove_orphaned_images(self.paragraph.section, images)

    def move_to(self, paragraph: "int | HwpxOxmlParagraph", *, offset: int | None = None) -> None:
        """Move this object into *paragraph* at character *offset* (``None``: the end), as cutting
        and pasting it in Hancom does.

        *paragraph* is a paragraph of the same document -- in the body, a table cell, a text box,
        a note, a header or a footer -- or its index in ``doc.paragraphs``. *offset* counts as
        ``paragraph.text`` does (a tab or a line break is one, an object none); the object goes in
        front of the character there, after the controls and objects already at that place. The
        object keeps its ids, its caption and what it holds; this wrapper then belongs to
        *paragraph*. Where it left, its place is cleaned up as :meth:`remove` does (a run left
        empty goes, a connector attached to it lets go of it), and the paragraphs on both sides
        lose their line layout caches, with the paragraphs holding their cells and captions.

        A floating object keeps its frames and offsets as they are written; nothing is changed
        for it. Measured from its paragraph (``PARA``, ``COLUMN``) it goes with its new paragraph.
        Measured from the page or paper (``PAGE``, ``PAPER``) it stays where it is on the page:
        only the page it is drawn on follows its new paragraph, so moved within one page it does
        not move at all -- ``set_position`` puts it elsewhere. Where Hancom documents never hold
        such an object the move is refused with ``shape-move-place-unsupported``: into a table
        cell, a text box or a note, a floating object that is not measured down from its
        paragraph and kept in the page area (``vertRelTo="PARA"`` and either ``flowWithText="1"``
        or ``horzRelTo="PARA"``; Hancom draws another one over the cells above it), so a page-
        or paper-measured one never; a page-measured object into a section whose paper or margins
        differ; any floating object into a caption, and any object into a memo or a master page.
        Change the placement first with ``set_position(vert_rel_to="PARA", horz_rel_to="PARA")``
        or ``treat_as_char=True``. Moving an object into itself (a paragraph of its own text box
        or caption) is ``shape-move-into-itself``, a member of a group alone
        ``shape-group-member-unsupported``, a removed object ``shape-not-in-document``. Everything
        is checked before anything changes.
        """

        place_object(self, paragraph, offset, copy=False)

    def copy_to(self: _Placed, paragraph: "int | HwpxOxmlParagraph", *, offset: int | None = None) -> _Placed:
        """Put a copy of this object into *paragraph* at *offset* (``None``: the end) and return it.

        The place is chosen and checked as :meth:`move_to` does, and a copy may go inside the
        object it copies (a copy of a text box into its own text). The copy has fresh ids (its
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
        suggestion="Unscaled, unflipped pictures, drawing shapes and OLE objects outside a group turn; "
                   "turn a stretched picture back to its own size first, or turn it in Hancom.",
    )


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
        raise _rotation_refused(element, "turning a group is not verified against a Hancom-saved group")
    matrices = [str(child.tag).rsplit("}", 1)[-1] for child in rendering]
    if matrices != ["transMatrix", "scaMatrix", "rotMatrix"]:
        raise _rotation_refused(element, "its rendering matrices are not one trans/sca/rot set")
    scale_x, scale_y = _drawn_scale(rendering[1])
    if scale_x <= 0 or scale_y <= 0:
        raise _rotation_refused(element, "its hc:scaMatrix does more than scale it")
    flip = element.find(f"{_HP}flip")
    if flip is not None and (flip.get("horizontal", "0") not in _FALSE_FLAGS
                             or flip.get("vertical", "0") not in _FALSE_FLAGS):
        raise _rotation_refused(element, "it is flipped")
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

    radians = math.radians(angle)
    cos, sin = math.cos(radians), math.sin(radians)
    box_width = abs(width * cos) + abs(height * sin)
    box_height = abs(width * sin) + abs(height * cos)
    if angle % 90 == 0:  # no float noise on the right angles
        box_width, box_height = (width, height) if angle % 180 == 0 else (height, width)
    rendering = element.find(f"{_HP}renderingInfo")
    trans, scale, rot = rendering[0], rendering[1], rendering[2]
    # The object as drawn starts where its scaMatrix moves it (0, 0 unless Hancom moved it there).
    cx, cy = _fraction(scale.get("e3"), 0.0) + width / 2, _fraction(scale.get("e6"), 0.0) + height / 2
    shift_x, shift_y = box_width / 2 - cx, box_height / 2 - cy
    for key, value in (("e1", 1.0), ("e2", 0.0), ("e3", shift_x), ("e4", 0.0), ("e5", 1.0), ("e6", shift_y)):
        trans.set(key, _matrix_number(value))
    for key, value in (("e1", cos), ("e2", -sin), ("e3", cx * (1 - cos) + cy * sin),
                       ("e4", sin), ("e5", cos), ("e6", cy * (1 - cos) - cx * sin)):
        rot.set(key, _matrix_number(round(value, 6)))
    offset = element.find(f"{_HP}offset")
    if offset is not None:
        offset.set("x", str(round(shift_x) & 0xFFFFFFFF))  # a negative one as Hancom writes it: unsigned 32-bit
        offset.set("y", str(round(shift_y) & 0xFFFFFFFF))
    info = element.find(f"{_HP}rotationInfo")
    info.set("angle", str(angle))
    info.set("centerX", str(round(box_width / 2)))
    info.set("centerY", str(round(box_height / 2)))
    size = element.find(f"{_HP}sz")
    if size is not None:
        if size.get("widthRelTo", "ABSOLUTE") == "ABSOLUTE":
            size.set("width", str(round(box_width)))
        if size.get("heightRelTo", "ABSOLUTE") == "ABSOLUTE":
            size.set("height", str(round(box_height)))


def object_size(element: Any) -> tuple[int, int]:
    """An object's ``hp:sz`` width and height (0 when missing)."""

    size = element.find(f"{_HP}sz")
    if size is None:
        return 0, 0
    return _number(size.get("width")) or 0, _number(size.get("height")) or 0


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
    A turned object is resized as drawn before turning and turned again (see :func:`rotation_base_size`):
    its ``hp:sz`` is the box around it turned at the new size."""

    element = obj.element
    info = element.find(f"{_HP}rotationInfo")
    angle = (_number(info.get("angle")) or 0) % 360 if info is not None else 0
    width, height = keep_ratio(rotation_base_size(element) if angle else object_size(element), width, height)
    if not angle:
        _set_size(element, "sz", width, height)
    original = element.find(f"{_HP}orgSz")
    if original is not None:
        org_width, org_height = _number(original.get("width")) or 0, _number(original.get("height")) or 0
        _set_size(element, "curSz", width, height)
        scale = element.find(f"{_HP}renderingInfo/{_HC}scaMatrix")
        if scale is not None and org_width > 0 and org_height > 0:
            scale.set("e1", _matrix_number(width / org_width))
            scale.set("e5", _matrix_number(height / org_height))
        rotation = element.find(f"{_HP}rotationInfo")
        if rotation is not None:
            rotation.set("centerX", str(width // 2))
            rotation.set("centerY", str(height // 2))
    if angle:
        apply_rotation(element, angle, width, height)
    from ._document_primitives import _clear_paragraph_layout_cache

    _clear_paragraph_layout_cache(obj.paragraph.element)
    obj.paragraph.section.mark_dirty()


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


def set_equation_base_unit(obj: Any, base_unit: int) -> None:
    """Give an equation the base font size *base_unit* (1/100 pt) and the box ``add_equation`` measures for its
    script at that size: ``hp:sz`` and ``baseLine`` follow, and the line it sits on is laid out again."""

    validate_equation_base_unit(base_unit)
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

        size = _append_child(element, f"{_HP}sz", {"widthRelTo": "ABSOLUTE", "heightRelTo": "ABSOLUTE",
                                                   "protect": "0"})
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
    """An equation's *base_unit* (1/100 pt), checked to be an int in ``1 <= base_unit < 2**31``."""

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
    Offsets, rotation centres and the members' own matrices stay. ``False``,
    with nothing changed, for a group without an original size.
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
#: (:func:`_stays_in_box`).
OBJECT_PLACES: dict[str, frozenset[str]] = {
    "char": frozenset({"body", "cell", "text_box", "note", "header_footer", "caption"}),
    "paragraph": frozenset({"body", "cell", "text_box", "note", "header_footer"}),
    "page": frozenset({"body", "header_footer"}),
}

#: Drawing objects whose ``id`` a copy renews besides those ``_refresh_copied_paragraph_subtree_ids``
#: renews. An ``id="0"`` stays: Hancom writes group members so (pictures, lines, rectangles, groups).
_COPY_RENEWED_IDS = frozenset({"line", "rect", "ellipse", "arc", "polygon", "curve", "connectLine", "chart"})


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
                   "떠 있는 개체를 칸·글상자·각주로 옮기려면 먼저 set_position(vert_rel_to='PARA', "
                   "horz_rel_to='PARA')으로 문단 기준·쪽 영역 안으로 바꾼 뒤(또는 treat_as_char=True) 옮기세요. "
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


def fresh_copy(element: Any) -> Any:
    """A copy of the object *element* with fresh ids (objects, tables, paragraphs, fields), no line
    layout caches and its connectors following the copied objects."""

    from copy import deepcopy

    from ._document_primitives import _clear_paragraph_layout_cache, _object_id, _refresh_copied_paragraph_subtree_ids
    from ._paragraph_text_edit import renumber_copied_fields

    copy = deepcopy(element)
    copy.tail = None
    before = [(node, node.get("instid")) for node in copy.iter() if node.get("instid") not in (None, "", "0")]
    members = [node for node in copy.iter() if _local(node) != "p" and node.get("id") == "0"]
    _refresh_copied_paragraph_subtree_ids(copy)
    for node in copy.iter():
        if _local(node) in _COPY_RENEWED_IDS and node.get("id") not in (None, "", "0"):
            node.set("id", _object_id())
    for node in members:  # a group member's id="0", as Hancom writes members, stays
        node.set("id", "0")
    _let_go_of_outside(copy, {old: str(node.get("instid")) for node, old in before})
    renumber_copied_fields(copy)
    for node in copy.iter():
        if _local(node) == "p":
            _clear_paragraph_layout_cache(node)
    return copy


def insert_at_offset(paragraph: Any, element: Any, offset: int | None, char_pr_id_ref: str | None = None) -> None:
    """Put *element* into the runs of the paragraph element *paragraph* in front of character *offset*
    (``None``: at the end), counted as ``paragraph.text`` counts.

    Controls and objects already at that place stay in front of it. Inside a text node the node is
    divided and *element* goes between its halves in the same run, as Hancom keeps an object among the
    text of a run; at a run boundary it goes at the end of the run before. A paragraph with no run gets
    one (*char_pr_id_ref*, else ``"0"``).
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
    runs[-1].append(element)


def _check_place(element: Any, source: Any, target: Any) -> None:
    """Refuse a place *target* (a paragraph) where Hancom documents never hold the object *element* in the
    way it is placed, coming from the paragraph *source* (see :data:`OBJECT_PLACES`)."""

    box = paragraph_box(target.element, target.section.element)
    kind = placement_kind(element)
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


def _sections_of(*paragraphs: Any) -> list[Any]:
    """The sections of the document the paragraphs belong to (theirs alone without a document)."""

    document = paragraphs[0].section.document
    if document is not None:
        return list(document.sections)
    return list({id(p.section): p.section for p in paragraphs}.values())


def place_object(obj: Any, paragraph: Any, offset: int | None, *, copy: bool) -> Any:
    """``move_to``/``copy_to`` of an object or table *obj*: check everything, then move it (or put a
    copy) into *paragraph* at *offset*. Returns the copy's model object, or ``None`` for a move."""

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
    target = resolve_paragraph_in(source, paragraph, caller=caller)
    if not copy and any(node is target.element for node in element.iter()):
        raise HwpxValueError(
            "an object cannot move into one of its own paragraphs (its text box, cell or caption)",
            code="shape-move-into-itself",
            context={"caller": caller},
            suggestion="Pick a paragraph outside the object, or copy it there with copy_to().",
        )
    _check_place(element, source, target)
    if offset is not None:
        _check_offset("offset", offset, 0, len(target.text))
    if copy:
        placed = fresh_copy(element)
        renew_copied_memos(placed, _sections_of(source), target.section)
    else:
        _detach_object(element, parent, source.element, source.section)
        inside = {node.get("instid") for node in element.iter() if node.get("instid") not in (None, "", "0")}
        _let_go_of_outside(element, {value: value for value in inside if value})
        placed = element
    insert_at_offset(target.element, placed, offset, target.char_pr_id_ref)
    _clear_paragraph_layout_cache(target.element)
    if not copy and target.section.element is not source.section.element:
        carry_memos(placed, _sections_of(source, target), target.section)
    target.section.mark_dirty()
    if copy:
        from .objects import wrap_object

        return wrap_object(placed, target)
    obj.paragraph = target
    return None
