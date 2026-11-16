# SPDX-License-Identifier: Apache-2.0
"""Groups (``<hp:container>``): member shapes assembled into one drawing object, at any depth.

Moved out of :mod:`hwpx.oxml.objects` (its 1,600-line owner-file cap) when groups learned pictures, text
boxes, lines and groups inside groups; ``objects`` re-exports :class:`ContainerMember` and
:func:`_create_container_element`. The shape builders stay in ``objects`` and are imported where they are
called, so either module can be imported first.

In the groups Hancom saves, a member is a complete shape without the
``sz``/``pos``/``outMargin``/``shapeComment`` tail, with ``id="0"``, ``zOrder="0"``,
``numberingType="NONE"``, ``textWrap="TOP_AND_BOTTOM"`` and ``groupLevel`` its depth (1 directly in the
group, 2 in a group inside it, ...). A group inside a group is such a member too: its own envelope and
members, no tail; every shape at every depth is placed in the outermost group's space (Hancom draws each one
at its own transMatrix there). Only the outermost group carries the tail and ``numberingType="PICTURE"``.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Sequence
import xml.etree.ElementTree as ET

from ._document_primitives import _HC, _HP, _append_child
from .shape_position import line_width_units, validate_draw_text_vert_align, validate_shape_size

if TYPE_CHECKING:
    from .section import HwpxOxmlSection

#: The ``AbstractShapeObjectType`` tail only the outermost group keeps.
_MEMBER_DROPPED_TAIL = ("sz", "pos", "outMargin", "shapeComment")
#: Elements a group holds as members.
_MEMBER_TAGS = frozenset({"rect", "ellipse", "polygon", "line", "arc", "curve", "connectLine", "pic", "container"})


@dataclass(frozen=True)
class _MemberText:
    """Text a text-box member gets once its group is in a section (paragraph ids are section-wide)."""

    text: str
    name: str
    editable: bool
    margin: dict[str, int] | None
    char_pr_id_ref: str | int | None
    para_pr_id_ref: str | int | None
    vert_align: str | None


@dataclass(frozen=True)
class ContainerMember:
    """One shape inside a group (``<hp:container>``), placed at (*x*, *y*)
    in the group's own top-left-anchored local coordinate space (HWPUNIT —
    the same convention :func:`_create_polygon_element` uses for its own
    vertices). Construct via :meth:`rect`, :meth:`ellipse`, :meth:`polygon`,
    :meth:`line`, :meth:`text_box`, :meth:`picture` or :meth:`group` — not
    the bare constructor, which expects an already-built element. Their line
    width is *line_width_mm* (mm, as for ``doc.shapes.add_rectangle``; the
    default 0.12 mm is 33 HWPUNIT, 0 draws no line).

    A member is a complete, standalone shape element — the same
    ``offset``/``orgSz``/``curSz``/``flip``/``rotationInfo``/
    ``renderingInfo`` envelope plus type geometry a freestanding shape
    would have — except it drops the ``AbstractShapeObjectType`` tail
    (``sz``/``pos``/``outMargin``/``shapeComment``; the *group* carries
    that, not the member) and its ``groupLevel`` is its depth instead of
    ``"0"``. :func:`_create_container_element` applies both when it
    assembles the members passed here into the group.
    """

    element: ET.Element
    x: int
    y: int
    text: _MemberText | None = None
    members: tuple["ContainerMember", ...] = ()

    @classmethod
    def rect(
        cls,
        x: int,
        y: int,
        width: int,
        height: int,
        *,
        ratio: int = 0,
        line_color: str = "#000000",
        line_width_mm: float = 0.12,
        fill_color: str | None = None,
    ) -> "ContainerMember":
        """A rectangle member — see :func:`_create_rectangle_element`."""

        from .objects import _create_rectangle_element

        element = _create_rectangle_element(
            width, height, ratio=ratio, line_color=line_color,
            line_width=str(line_width_units(line_width_mm)), fill_color=fill_color,
        )
        return cls(element, x, y)

    @classmethod
    def ellipse(
        cls,
        x: int,
        y: int,
        width: int,
        height: int,
        *,
        line_color: str = "#000000",
        line_width_mm: float = 0.12,
        fill_color: str | None = None,
    ) -> "ContainerMember":
        """An ellipse member — see :func:`_create_ellipse_element`."""

        from .objects import _create_ellipse_element

        element = _create_ellipse_element(
            width, height, line_color=line_color, line_width=str(line_width_units(line_width_mm)),
            fill_color=fill_color,
        )
        return cls(element, x, y)

    @classmethod
    def polygon(
        cls,
        x: int,
        y: int,
        points: Sequence[tuple[int, int]],
        *,
        line_color: str = "#000000",
        line_width_mm: float = 0.12,
        fill_color: str | None = None,
        closed: bool = True,
    ) -> "ContainerMember":
        """A polygon member — see :func:`_create_polygon_element`. It is
        closed (the first vertex repeated at the end) unless *closed* is
        false."""

        from .objects import _closed_points, _create_polygon_element

        element = _create_polygon_element(
            _closed_points(points) if closed else points,
            line_color=line_color, line_width=str(line_width_units(line_width_mm)), fill_color=fill_color,
        )
        return cls(element, x, y)

    @classmethod
    def line(
        cls,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        *,
        line_color: str = "#000000",
        line_width_mm: float = 0.12,
    ) -> "ContainerMember":
        """A line member from (*start_x*, *start_y*) to (*end_x*, *end_y*) in the
        group's space. Like a freestanding line it is placed at the top-left
        of its two ends, which it keeps relative to that corner."""

        from .objects import _create_line_element

        x, y = min(start_x, end_x), min(start_y, end_y)
        element = _create_line_element(
            start_x - x, start_y - y, end_x - x, end_y - y,
            line_color=line_color, line_width=str(line_width_units(line_width_mm)),
        )
        return cls(element, x, y)

    @classmethod
    def text_box(
        cls,
        x: int,
        y: int,
        width: int,
        height: int,
        text: str,
        *,
        ratio: int = 0,
        line_color: str = "#000000",
        line_width_mm: float = 0.12,
        fill_color: str | None = None,
        name: str = "",
        editable: bool = False,
        margin: dict[str, int] | None = None,
        char_pr_id_ref: str | int | None = None,
        para_pr_id_ref: str | int | None = None,
        vertical_alignment: str | None = None,
    ) -> "ContainerMember":
        """A rectangle holding *text*, as :meth:`HwpxOxmlShape.set_draw_text`
        writes it (same *name*, *editable*, *margin*, *char_pr_id_ref*,
        *para_pr_id_ref* and *vertical_alignment*). The text is written when the group
        is inserted, so its paragraphs take ids unused in the section; a bad
        *vertical_alignment* is refused here, before any document is touched."""

        validate_draw_text_vert_align(vertical_alignment, argument="vertical_alignment")
        member = cls.rect(x, y, width, height, ratio=ratio, line_color=line_color,
                          line_width_mm=line_width_mm, fill_color=fill_color)
        spec = _MemberText(text, name, editable, dict(margin) if margin else None,
                           char_pr_id_ref, para_pr_id_ref, vertical_alignment)
        return cls(member.element, x, y, text=spec)

    @classmethod
    def picture(
        cls,
        x: int,
        y: int,
        width: int,
        height: int,
        image: Any,
    ) -> "ContainerMember":
        """A picture member showing *image*: the binary item
        :meth:`doc.media.add_image <hwpx._document.ns.media.MediaNamespace.add_image>`
        returned, or its id. The picture fills *width* × *height*."""

        from .objects import _create_picture_element

        validate_shape_size(width, height)
        image_id = str(image).strip()
        if not image_id:
            from ..errors import HwpxValueError

            raise HwpxValueError(
                "a picture member needs the image's binary item",
                code="shape-container-picture-image",
                context={"image": repr(image)},
                suggestion="Pass what doc.media.add_image(data, format) returned.",
            )
        return cls(_create_picture_element(image_id, width, height), x, y)

    @classmethod
    def group(cls, x: int, y: int, members: Sequence["ContainerMember"]) -> "ContainerMember":
        """A group inside the group, placed at (*x*, *y*) and holding *members*
        in its own local space, as Hancom keeps a group that was grouped again."""

        children = tuple(members)
        return cls(_group_element(children, top=False), x, y, members=children)


def _member_size(member: "ContainerMember") -> tuple[int, int]:
    org_sz = member.element.find(f"{_HP}orgSz")
    if org_sz is None:  # pragma: no cover - defensive, every builder sets this
        return 0, 0
    return int(org_sz.get("width", "0")), int(org_sz.get("height", "0"))


def _group_element(
    members: Sequence["ContainerMember"],
    *,
    top: bool,
    treat_as_char: bool = True,
) -> ET.Element:
    from .objects import _build_shape_base_children, _build_shape_common_children

    if not members:
        from ..errors import HwpxValueError

        raise HwpxValueError(
            "add_container requires at least one member",
            code="shape-container-no-members",
            context={},
            suggestion="Pass one or more ContainerMember instances "
            "(ContainerMember.rect/.ellipse/.polygon/.line/.text_box/.picture/.group).",
        )

    min_x = min(m.x for m in members)
    min_y = min(m.y for m in members)
    width = max(m.x + _member_size(m)[0] for m in members) - min_x
    height = max(m.y + _member_size(m)[1] for m in members) - min_y

    el = ET.Element(f"{_HP}container")
    _build_shape_common_children(el, width, height, treat_as_char=treat_as_char)
    el.set("numberingType", "PICTURE")
    for member in members:
        # A fresh copy (a group inside is assembled again from its members): the ContainerMember passed in is
        # never changed, so the same one can go into several groups, or twice into one.
        member_el = _group_element(member.members, top=False) if member.members else copy.deepcopy(member.element)
        local_x, local_y = member.x - min_x, member.y - min_y
        _place(member_el, local_x, local_y)
        # Hancom draws every shape of a group at its own transMatrix in the outermost group's space, so the
        # members of a group inside go where that group goes (its members are stored in that space too).
        _shift_shapes_inside(member_el, local_x, local_y)
        # Members share a small, non-unique id (almost always "0"); instid stays unique.
        member_el.set("id", "0")
        member_el.set("zOrder", "0")
        member_el.set("numberingType", "NONE")
        # Every member is TOP_AND_BOTTOM; the group's own placement decides how text goes around it.
        member_el.set("textWrap", "TOP_AND_BOTTOM")
        for tail_name in _MEMBER_DROPPED_TAIL:
            tail_el = member_el.find(f"{_HP}{tail_name}")
            if tail_el is not None:
                member_el.remove(tail_el)
        el.append(member_el)

    if top:
        _set_group_levels(el, 1)
        _build_shape_base_children(el, width, height)
        # The outermost group (not its members) closes with an empty shapeComment, as hp:pic does.
        _append_child(el, f"{_HP}shapeComment", {})
    else:  # a group inside has no sz/pos tail: drop the builder's marker the tail would have taken
        el.attrib.pop("_treatAsChar", None)
    return el


def _place(element: ET.Element, x: int, y: int) -> None:
    """Set a member's offset, and the transMatrix translation that mirrors it."""

    offset = element.find(f"{_HP}offset")
    if offset is not None:
        offset.set("x", str(x))
        offset.set("y", str(y))
    rendering_info = element.find(f"{_HP}renderingInfo")
    trans = rendering_info.find(f"{_HC}transMatrix") if rendering_info is not None else None
    if trans is not None:
        trans.set("e3", str(x))
        trans.set("e6", str(y))


def _shapes_inside(group: ET.Element) -> list[ET.Element]:
    return [child for child in group if str(child.tag).rsplit("}", 1)[-1] in _MEMBER_TAGS]


def _shift_shapes_inside(element: ET.Element, dx: int, dy: int) -> None:
    for shape in _shapes_inside(element) if element.tag == f"{_HP}container" else ():
        offset = shape.find(f"{_HP}offset")
        if offset is not None:
            _place(shape, int(offset.get("x", "0")) + dx, int(offset.get("y", "0")) + dy)
        _shift_shapes_inside(shape, dx, dy)


def _set_group_levels(group: ET.Element, level: int) -> None:
    for shape in _shapes_inside(group):
        shape.set("groupLevel", str(level))
        if shape.tag == f"{_HP}container":
            _set_group_levels(shape, level + 1)


def _create_container_element(
    members: Sequence["ContainerMember"],
    *,
    treat_as_char: bool = True,
) -> ET.Element:
    """Build a complete ``<hp:container>`` grouping *members*.

    The group is structured like any other drawing object —
    ``numberingType="PICTURE"``, its own ``offset``/``orgSz``/``curSz``/
    ``flip``/``rotationInfo``/``renderingInfo`` + ``sz``/``pos``/
    ``outMargin``/``shapeComment`` tail — except its payload is complete
    member shapes instead of geometry. ``orgSz`` is the union bounding box
    of every member's own (*x*, *y*, ``orgSz``) in the group's local space,
    so members never need to be pre-translated by the caller; a group inside
    it does the same in its own space.
    """

    return _group_element(members, top=True, treat_as_char=treat_as_char)


def _write_member_texts(
    members: Sequence["ContainerMember"], group: Any, section: "HwpxOxmlSection"
) -> None:
    """Write the text of every text-box member, at any depth, into *group* — the group element now in
    *section* (insertion copies the element, so its members are paired with *members* by order)."""

    from .objects import _write_draw_text

    placed = _shapes_inside(group)
    for member, element in zip(members, placed):
        if member.text is not None:
            spec = member.text
            _write_draw_text(
                element, spec.text, section=section, name=spec.name,
                editable=spec.editable, margin=spec.margin, char_pr_id_ref=spec.char_pr_id_ref,
                para_pr_id_ref=spec.para_pr_id_ref, vert_align=spec.vert_align,
            )
            draw_text = element.find(f"{_HP}drawText")
            if draw_text is not None:  # a member has no sz: its text width is its own width
                draw_text.set("lastWidth", str(_member_size(member)[0]))
        if member.members:
            _write_member_texts(member.members, element, section)


# --------------------------------------------------------------------------------------------------
# Taking one member out of a group


def _local(node: Any) -> str:
    return str(node.tag).rsplit("}", 1)[-1]


def _matrix(node: Any) -> list[float]:
    values = []
    for key in ("e1", "e2", "e3", "e4", "e5", "e6"):
        try:
            values.append(float(node.get(key, "0")))
        except ValueError:
            values.append(0.0)
    return values


def _plain(matrix: list[float], *, scale: bool = False) -> bool:
    """*matrix* is identity -- or, with *scale*, only scales and moves (no turn, no skew)."""

    if abs(matrix[1]) > 1e-3 or abs(matrix[3]) > 1e-3:
        return False
    return scale and matrix[0] > 0 and matrix[4] > 0 or (
        abs(matrix[0] - 1) <= 1e-3 and abs(matrix[4] - 1) <= 1e-3 and abs(matrix[2]) <= 0.5 and abs(matrix[5]) <= 0.5)


def _outer_scale_fits(scale: list[float], trans: list[float], factors: tuple[float, float]) -> bool:
    """*scale* is the outermost group's: its *factors*, moving a shape at *trans* by that times the factor less 1
    (what ``shape_position.resize_group`` writes and Hancom's resized groups hold)."""

    return (abs(scale[1]) <= 1e-3 and abs(scale[3]) <= 1e-3
            and abs(scale[0] - factors[0]) <= 1e-3 and abs(scale[4] - factors[1]) <= 1e-3
            and abs(scale[2] - trans[2] * (factors[0] - 1)) <= 1.5 and abs(scale[5] - trans[5] * (factors[1] - 1)) <= 1.5)


def _unturned_box(shape: Any, factors: tuple[float, float] = (1.0, 1.0)) -> tuple[float, float, float, float] | None:
    """The box an unturned, unflipped shape of a group takes in the outermost group's own (unscaled) space: its
    original size through its own scaMatrix, moved by its transMatrix. *factors* is how the outermost group is
    drawn (its own scaMatrix), which a member's first scaMatrix repeats. ``None`` for a shape this cannot say
    for: turned, flipped, skewed, or holding a matrix of a group that is turned or stretched otherwise."""

    info, flip, original = shape.find(f"{_HP}rotationInfo"), shape.find(f"{_HP}flip"), shape.find(f"{_HP}orgSz")
    rendering = shape.find(f"{_HP}renderingInfo")
    if rendering is None or original is None or (info is not None and info.get("angle", "0") not in ("0", "")):
        return None
    if flip is not None and "1" in (flip.get("horizontal"), flip.get("vertical")):
        return None
    matrices = [_matrix(node) for node in rendering]
    if len(matrices) < 3 or len(matrices) % 2 == 0 or not _plain(matrices[-1]):
        return None
    middle = matrices[1:-2]
    if middle and not (_outer_scale_fits(middle[0], matrices[0], factors) and all(_plain(m) for m in middle[1:])):
        return None  # a group around it turned it, or stretched it otherwise than the outermost one
    if not _plain(matrices[-2], scale=True):
        return None  # its own matrix does more than scale it
    sca, trans = matrices[-2], matrices[0]
    try:
        width, height = float(original.get("width", "0")), float(original.get("height", "0"))
    except ValueError:
        return None
    left, top = trans[2] + sca[2], trans[5] + sca[5]
    return left, top, left + width * sca[0], top + height * sca[4]


def _union(boxes: Sequence[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _outermost_factors(group: Any) -> tuple[float, float] | None:
    """How the outermost group is drawn: the factors of its own scaMatrix (1 when Hancom has not resized it),
    when its ``curSz`` and ``hp:sz`` say the same (0 on an axis left alone). ``None`` when it is turned, flipped,
    moved by its matrices or skewed, or its sizes disagree."""

    box = _unturned_box(group)
    rendering, original = group.find(f"{_HP}renderingInfo"), group.find(f"{_HP}orgSz")
    if box is None or rendering is None or original is None or abs(box[0]) > 0.5 or abs(box[1]) > 0.5:
        return None
    scale = _matrix(list(rendering)[-2])
    factors = (1.0 if abs(scale[0] - 1) <= 1e-3 else scale[0], 1.0 if abs(scale[4] - 1) <= 1e-3 else scale[4])
    current, size = group.find(f"{_HP}curSz"), group.find(f"{_HP}sz")
    for index, side in enumerate(("width", "height")):
        drawn = float(original.get(side, "0")) * factors[index]
        for node, unscaled in ((current, "0"), (size, None)):
            value = node.get(side) if node is not None else None
            if value is None or factors[index] == 1 and value in (unscaled, original.get(side)):
                continue
            if abs(float(value) - drawn) > 2:
                return None
    return factors


def member_removal_refusal(element: Any, chain: Sequence[Any]) -> str | None:
    """Why *element* cannot be taken out of the groups *chain* (its group first, the outermost last) with the
    groups fitted to what is left, or ``None`` when it can.

    It can when no group on the chain is turned, flipped or stretched (the outermost one may be resized, as
    ``Shape.resize`` and Hancom resize a group) and each holds, besides *element*, only unturned members whose
    boxes make up exactly the group's box -- the relation the groups of Hancom-saved documents keep (the
    outermost group's ``orgSz`` is the box around its members: 138 of 171 public groups by this measure, the
    rest differing only by turned members, which this does not measure).
    """

    factors = _outermost_factors(chain[-1])
    if factors is None:
        return "its group is turned, flipped or its sizes disagree"
    for index, group in enumerate(chain):
        members = _shapes_inside(group)
        if index == 0 and len(members) < 2:
            return "it is the group's only member: remove the group"
        outermost = index == len(chain) - 1
        if outermost:
            original = group.find(f"{_HP}orgSz")
            own: tuple[float, float, float, float] | None = (
                0.0, 0.0, float(original.get("width", "0")), float(original.get("height", "0")))
        else:
            rendering = group.find(f"{_HP}renderingInfo")
            own = _unturned_box(group, factors)
            if rendering is None or not _plain(_matrix(list(rendering)[-2])):
                own = None  # a group inside drawn at another size than its own
        if own is None:
            return "a group it is in is turned, flipped or stretched"
        boxes = [_unturned_box(member, factors) for member in members]
        if any(box is None for box in boxes):
            return "a member of its group is turned, flipped or stretched by a matrix this does not measure"
        if any(abs(a - b) > 2 for a, b in zip(_union(boxes), own)):  # type: ignore[arg-type]
            return "its group's box is not the box around its members"
    return None


def fit_groups_after_removal(chain: Sequence[Any]) -> None:
    """Fit each group of *chain* (innermost first) to the members left in it: a group inside takes the box around
    its members as its place and size; the outermost group moves every shape in it so that box starts at its
    origin, takes its size (drawn at its factors when it is resized), and moves on the page by as much when it
    floats from the left and top of its frame, so what is left stays where it was drawn. Call it only for a chain
    :func:`member_removal_refusal` accepted (before the member went)."""

    from .shape_position import _matrix_number, _signed_offset

    factors = _outermost_factors(chain[-1]) or (1.0, 1.0)
    for index, group in enumerate(chain):
        boxes = [_unturned_box(member, factors) for member in _shapes_inside(group)]
        left, top, right, bottom = _union(boxes)  # type: ignore[arg-type]
        width, height = max(1, round(right - left)), max(1, round(bottom - top))
        if index < len(chain) - 1:
            _place(group, round(left), round(top))
            _set_outer_scale(group, factors, _matrix_number)
            _set_group_size(group, width, height, (1.0, 1.0))
            continue
        dx, dy = round(left), round(top)
        if dx or dy:
            _shift_shapes_inside(group, -dx, -dy)
            for shape in _all_shapes_inside(group):
                _set_outer_scale(shape, factors, _matrix_number)
        position = group.find(f"{_HP}pos")
        if position is not None and position.get("treatAsChar") in ("0", "false"):
            for axis, shift, align, start in (("horzOffset", round(dx * factors[0]), "horzAlign", "LEFT"),
                                              ("vertOffset", round(dy * factors[1]), "vertAlign", "TOP")):
                if shift and position.get(align, start) == start:
                    moved = (_signed_offset(position.get(axis)) or 0) + shift
                    position.set(axis, str(moved & 0xFFFFFFFF))
        _set_group_size(group, width, height, factors)


def _all_shapes_inside(group: Any) -> list[Any]:
    found = []
    for shape in _shapes_inside(group):
        found.append(shape)
        if shape.tag == f"{_HP}container" or str(shape.tag).endswith("}container"):
            found.extend(_all_shapes_inside(shape))
    return found


def _set_outer_scale(shape: Any, factors: tuple[float, float], number: Any) -> None:
    """A shape's first scaMatrix (the outermost group's, in a resized group) moving it from its new place."""

    rendering = shape.find(f"{_HP}renderingInfo")
    matrices = list(rendering) if rendering is not None else []
    if factors == (1.0, 1.0) or len(matrices) < 5:
        return
    trans = _matrix(matrices[0])
    matrices[1].set("e3", number(trans[2] * (factors[0] - 1)))
    matrices[1].set("e6", number(trans[5] * (factors[1] - 1)))


def _set_group_size(group: Any, width: int, height: int, factors: tuple[float, float]) -> None:
    """A group's own size *width* x *height*, drawn at *factors* (``curSz`` 0 on an axis it leaves alone, ``hp:sz``
    as drawn) with its rotation centre in the middle of its own size, as Hancom keeps a resized group's."""

    original = group.find(f"{_HP}orgSz")
    if original is not None:
        original.set("width", str(width))
        original.set("height", str(height))
    current = group.find(f"{_HP}curSz")
    if current is not None:
        for side, own, factor in (("width", width, factors[0]), ("height", height, factors[1])):
            if factor != 1:
                current.set(side, str(int(own * factor + 1e-6)))
            elif current.get(side, "0") != "0":  # Hancom writes 0; a group python-hwpx made, its own size
                current.set(side, str(own))
    size = group.find(f"{_HP}sz")
    if size is not None:
        size.set("width", str(round(width * factors[0])))
        size.set("height", str(round(height * factors[1])))
    info = group.find(f"{_HP}rotationInfo")
    if info is not None:
        info.set("centerX", str(width // 2))
        info.set("centerY", str(height // 2))


__all__ = ["ContainerMember", "fit_groups_after_removal", "member_removal_refusal"]
