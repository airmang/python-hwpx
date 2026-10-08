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
from dataclasses import dataclass
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Callable

from ..errors import HwpxValueError
from ._document_primitives import _HC, _HP
from .color import normalize_color

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET

    from .objects import HwpxOxmlShape

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


def _shape_set_position(
    self: "HwpxOxmlShape",
    *,
    horizontal_offset: int,
    vertical_offset: int,
    horz_rel_to: str | None = None,
    vert_rel_to: str | None = None,
    horz_align: str | None = None,
    vert_align: str | None = None,
) -> None:
    """Set an existing floating shape's offsets, in HWP units, and optionally
    its reference frames and alignment.

    *horz_rel_to*/*vert_rel_to*/*horz_align*/*vert_align* write ``hp:pos``'s
    ``horzRelTo``/``vertRelTo``/``horzAlign``/``vertAlign``. Each takes an
    OWPML value exactly as the schema spells it (uppercase): ``horz_rel_to``
    one of ``PAPER``/``PAGE``/``COLUMN``/``PARA``, ``vert_rel_to`` one of
    ``PAPER``/``PAGE``/``PARA``, ``horz_align`` one of ``LEFT``/``CENTER``/
    ``RIGHT``/``INSIDE``/``OUTSIDE``, ``vert_align`` one of ``TOP``/
    ``CENTER``/``BOTTOM``/``INSIDE``/``OUTSIDE``. ``PAPER`` anchors to the
    sheet edge, so a stamp can sit in the page margin. ``None`` leaves that
    attribute as it is, so the default call only moves the offsets.

    Anchor, geometry and size are preserved. Every argument is checked before
    anything changes: inline shapes and missing positioning metadata refuse
    with ``shape-position-unsupported`` (changing their offsets would not move
    the drawing), bad offsets with ``shape-position-value``, and a frame or
    alignment outside the schema with ``shape-position-frame``. Check the real
    placement in Hancom.
    """

    for value in (horizontal_offset, vertical_offset):
        if isinstance(value, bool) or not isinstance(value, int) or not -(2**31) <= value < 2**31:
            raise HwpxValueError(
                "shape offsets must be signed 32-bit integer HWP units",
                code="shape-position-value",
                suggestion="Pass integer offsets in the shape's existing reference frame.",
            )
    frames: dict[str, str] = {}
    for argument, attribute, requested, allowed in (
        ("vert_rel_to", "vertRelTo", vert_rel_to, POS_VERT_REL_TO),
        ("horz_rel_to", "horzRelTo", horz_rel_to, POS_HORZ_REL_TO),
        ("vert_align", "vertAlign", vert_align, POS_VERT_ALIGN),
        ("horz_align", "horzAlign", horz_align, POS_HORZ_ALIGN),
    ):
        if requested is not None:
            frames[attribute] = _require_member(
                requested, allowed, argument=argument, code="shape-position-frame"
            )
    position = self.element.find(f"{_HP}pos")
    if position is None or position.get("treatAsChar") not in {"0", "false", "False"}:
        raise HwpxValueError(
            "position editing requires an existing floating shape",
            code="shape-position-unsupported",
            suggestion="Inspect the anchor; inline placement is controlled by paragraph flow.",
        )
    for attribute, frame in frames.items():
        position.set(attribute, frame)
    position.set("horzOffset", str(horizontal_offset & 0xFFFFFFFF))  # a negative one as Hancom writes it:
    position.set("vertOffset", str(vertical_offset & 0xFFFFFFFF))  # its unsigned 32-bit form
    self.paragraph.section.mark_dirty()


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
