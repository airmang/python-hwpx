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
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Callable

from ..errors import HwpxValueError
from ._document_primitives import _HC, _HP

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
    position.set("horzOffset", str(horizontal_offset))
    position.set("vertOffset", str(vertical_offset))
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
