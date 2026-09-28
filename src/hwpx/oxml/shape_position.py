# SPDX-License-Identifier: Apache-2.0
"""Floating-shape reference frames, shape-text vertical alignment, and a
new shape's original size (``hp:orgSz``) apart from its current size.

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
"""

from __future__ import annotations

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


def validate_draw_text_vert_align(vert_align: str | None) -> str | None:
    """Check ``set_draw_text``'s *vert_align* (``hp:subList/@vertAlign``)."""

    if vert_align is None:
        return None
    return _require_member(
        vert_align, SUBLIST_VERT_ALIGN, argument="vert_align", code="shape-draw-text-vert-align"
    )


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


__all__ = [
    "POS_HORZ_ALIGN",
    "POS_HORZ_REL_TO",
    "POS_VERT_ALIGN",
    "POS_VERT_REL_TO",
    "SUBLIST_VERT_ALIGN",
    "build_at_original_size",
    "validate_draw_text_vert_align",
    "validate_original_size",
]
