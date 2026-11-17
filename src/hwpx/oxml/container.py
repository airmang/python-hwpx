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
import dataclasses
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Sequence
import xml.etree.ElementTree as ET

from ._document_primitives import _HC, _HP, PENDING_IDS, IdSource, _append_child, _object_id, attributes_in_order
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
            width, height, ids=PENDING_IDS, ratio=ratio, line_color=line_color,
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
            width, height, ids=PENDING_IDS, line_color=line_color, line_width=str(line_width_units(line_width_mm)),
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
            ids=PENDING_IDS, line_color=line_color, line_width=str(line_width_units(line_width_mm)), fill_color=fill_color,
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
            ids=PENDING_IDS, line_color=line_color, line_width=str(line_width_units(line_width_mm)),
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
        return cls(_create_picture_element(image_id, width, height, ids=PENDING_IDS), x, y)

    @classmethod
    def group(cls, x: int, y: int, members: Sequence["ContainerMember"]) -> "ContainerMember":
        """A group inside the group, placed at (*x*, *y*) and holding *members*
        in its own local space, as Hancom keeps a group that was grouped again."""

        children = tuple(members)
        return cls(_group_element(children, top=False, ids=PENDING_IDS), x, y, members=children)


def _member_size(member: "ContainerMember") -> tuple[int, int]:
    org_sz = member.element.find(f"{_HP}orgSz")
    if org_sz is None:  # pragma: no cover - defensive, every builder sets this
        return 0, 0
    return int(org_sz.get("width", "0")), int(org_sz.get("height", "0"))


def _group_element(
    members: Sequence["ContainerMember"],
    *,
    top: bool,
    ids: "IdSource | None",
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
    _build_shape_common_children(el, width, height, ids=ids, treat_as_char=treat_as_char)
    el.set("numberingType", "PICTURE")
    for member in members:
        # A fresh copy (a group inside is assembled again from its members): the ContainerMember passed in is
        # never changed, so the same one can go into several groups, or twice into one.
        member_el = _group_element(member.members, top=False, ids=ids) if member.members else copy.deepcopy(member.element)
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
    ids: "IdSource | None",
    treat_as_char: bool = True,
) -> ET.Element:
    """Build a complete ``<hp:container>`` grouping *members*, for the document whose id source is *ids*.

    The group is structured like any other drawing object —
    ``numberingType="PICTURE"``, its own ``offset``/``orgSz``/``curSz``/
    ``flip``/``rotationInfo``/``renderingInfo`` + ``sz``/``pos``/
    ``outMargin``/``shapeComment`` tail — except its payload is complete
    member shapes instead of geometry. ``orgSz`` is the union bounding box
    of every member's own (*x*, *y*, ``orgSz``) in the group's local space,
    so members never need to be pre-translated by the caller; a group inside
    it does the same in its own space.
    """

    group = _group_element(bind_member_ids(members, ids), top=True, ids=ids, treat_as_char=treat_as_char)
    assert not any(node.get("instid") == "" for node in group.iter()), "a group member was given no id"
    return group


def bind_member_ids(members: Sequence["ContainerMember"], ids: "IdSource | None") -> tuple["ContainerMember", ...]:
    """Copies of *members* holding the ids they were made without, from *ids* -- the source of the document
    that takes them. A member is made for no document (its ``instid`` empty); the document gives it one
    when it takes it: the members of a group inside before that group, each in the order given (the order
    members written out in one expression are made in). A member that has its id keeps it; the members
    passed in are not changed, so one can go into several groups."""

    bound = []
    for member in members:
        inner = bind_member_ids(member.members, ids) if member.members else ()
        element = copy.deepcopy(member.element)
        if element.get("instid") == "":
            value = _object_id(ids)
            element.set("instid", value)
            if element.get("id") == "":
                element.set("id", value)
        bound.append(dataclasses.replace(member, element=element, members=inner))
    return tuple(bound)


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
                attributes_in_order(draw_text, ("lastWidth", "name", "editable"))  # as Hancom writes it
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


# --------------------------------------------------------------------------------------------------
# Turning a whole group


def _flipped(shape: Any) -> bool:
    flip = shape.find(f"{_HP}flip")
    return flip is not None and "1" in (flip.get("horizontal"), flip.get("vertical"))


def _angle(shape: Any) -> int:
    info = shape.find(f"{_HP}rotationInfo")
    try:
        return int(info.get("angle", "0")) % 360 if info is not None else 0
    except ValueError:
        return -1


def _close(values: Sequence[float], expected: Sequence[float], tolerance: float) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(values, expected))


def _group_turn_refusal(group: Any, shapes: Sequence[Any], turned: int, flips: tuple[int, int],
                        wanted: tuple[int, int]) -> str | None:
    """Why the group cannot be turned by :func:`turn_group` (``None`` when it can). *turned* and *flips* are how it
    is turned and flipped now (a turned or flipped group must hold the form :func:`turn_group` writes, Hancom's,
    to be turned or flipped again), *wanted* how it is to be flipped."""

    rendering, original = group.find(f"{_HP}renderingInfo"), group.find(f"{_HP}orgSz")
    if rendering is None or original is None or group.find(f"{_HP}rotationInfo") is None or len(rendering) != 3:
        return "its rendering matrices are not one trans/sca/rot set"
    if turned < 0:
        return "its angle is not a whole number"
    scale = _matrix(rendering[1])
    # a group flipped and then resized is moved in its scaMatrix on the flipped axis (shift_flipped_group); Hancom
    # turns it so about the centre it holds (rotate8 g-f-S1-30, g-f-S2-30)
    if not _scales_only(scale) or (abs(scale[2]) > 0.5 and flips[0] == 1) or (abs(scale[5]) > 0.5 and flips[1] == 1):
        return "its scaMatrix does more than scale it"
    if not turned and flips == (1, 1):
        width, height = float(original.get("width", "0")), float(original.get("height", "0"))
        size = group.find(f"{_HP}sz")
        drawn = (float(size.get("width", "0")), float(size.get("height", "0"))) if size is not None else (0, 0)
        if not _close(drawn, (width * scale[0], height * scale[4]), 2) or not _plain(_matrix(rendering[0])) \
                or not _plain(_matrix(rendering[2])):
            return "its size is not its own size through its scaMatrix, or its matrices move or turn it"
    if not any(_local(shape) != "container" for shape in shapes):
        return "it holds no member"
    for holder in [group, *(shape for shape in shapes if _local(shape) == "container")]:
        for child in holder:
            if child.find(f"{_HP}renderingInfo") is not None and _local(child) not in _MEMBER_TAGS:
                return f"it holds a {_local(child)} this does not turn"
    for shape in shapes:
        own = shape.find(f"{_HP}renderingInfo")
        if own is None or len(own) != 3 or shape.find(f"{_HP}orgSz") is None:
            return ("a member's rendering matrices are not one trans/sca/rot set: no Hancom-saved document shows "
                    "how one turns")
        if _flipped(shape) or (_angle(shape) != 0 and flips == (1, 1)) or _angle(shape) < 0:
            # members of a flipped group carry Hancom's mark of the flip (see turn_group's member_flip)
            return "a member is turned or flipped on its own: no Hancom-saved document shows how one turns"
        if not _scales_only(_matrix(own[1])):
            return "a member's scaMatrix does more than scale it"
        trans = _matrix(own[0])
        if not _close([trans[0], trans[1], trans[3], trans[4]], [1, 0, 0, 1], 1e-3):
            return "a member's transMatrix does more than move it"
        if not turned and flips == (1, 1) and not _plain(_matrix(own[2])):
            return "a member is turned on its own"
    return None


def _held_middle(group: Any) -> tuple[float, float] | None:
    """The group's ``rotationInfo`` centre less its move (``hc:transMatrix``): where it holds its middle."""

    info, rendering = group.find(f"{_HP}rotationInfo"), group.find(f"{_HP}renderingInfo")
    if info is None or rendering is None:
        return None
    try:
        center = (float(info.get("centerX", "0")), float(info.get("centerY", "0")))
    except ValueError:
        return None
    move = _matrix(rendering[0])
    return center[0] - move[2], center[1] - move[5]


def _scales_only(matrix: list[float]) -> bool:
    return abs(matrix[1]) <= 1e-3 and abs(matrix[3]) <= 1e-3 and matrix[0] > 0 and matrix[4] > 0


def turn_group(group: Any, angle: int, *, flips: tuple[int, int] | None = None,
               member_flip: tuple[int, int] | None = None) -> None:
    """Turn the group *group* (``hp:container``) *angle* degrees clockwise about its middle, as Hancom 2024 turns
    one (its object dialog, saved): the group's ``hc:rotMatrix`` turns it about the middle of its own size
    (``hp:orgSz``, also when it is resized) and its ``hc:transMatrix``/``hp:offset`` move the box around its turned
    shapes to its origin; that box is its ``hp:sz`` and the turned middle its ``rotationInfo`` centre, its
    ``rotationInfo/@angle`` the angle. Every shape in it, at every depth, takes the same turn, written from its own
    place (``hc:rotMatrix`` about the group's middle less the shape's place), and the same move added to its place
    (``hc:transMatrix``, ``hp:offset``); it keeps angle 0, its ``rotationInfo`` centre becomes the middle of its
    own turned box as drawn (a group inside keeps its own) and its text is laid out across that box's width.

    A group turned so turns again to another angle (from its unturned form, as Hancom's dialog does) or back
    to 0. *flips* (-1 on an axis to mirror) flips it as Hancom does (``ShapeObjHorzFlip``/``VertFlip``): the
    group's and every member's ``hc:rotMatrix`` mirror before they turn, the group's ``hp:flip`` takes the flags,
    the members' stay 0. ``None`` keeps the group's own. *member_flip* (axis 0 left-right / 1 up-down, the
    group's angle before the flip) marks each member's ``rotationInfo/@angle`` as Hancom does when it flips a
    group: (180 or 0) less the member's and the group's angle; members of a group flipped back to neither way get
    0. ``None`` keeps their marks (a turn leaves them).

    The group turns and flips about where it holds its middle: its ``rotationInfo`` centre less its move -- the
    middle of its own size, or for a group Hancom resized, of the size it is drawn at (Hancom moves the centre so;
    a group resized by ``resize`` keeps it).

    A group resized and then turned flips as Hancom flips one, mirrored as drawn
    (:func:`_mirror_resized_turned_group`).

    Refused (``shape-rotation-unsupported``) for what no Hancom-saved document shows: a member turned or flipped
    on its own. A group flipped and then resized (its ``scaMatrix`` moves it) turns about the centre it holds, and
    one resized, turned and flipped turns again as :func:`_turn_mirrored_group` does (rotate8). Everything is
    checked before anything changes."""

    from .shape_position import (
        _half_up, _rotation_refused, flip_signs, set_text_width, set_turn, turn_cos_sin, turned_frame,
    )

    shapes = _all_shapes_inside(group)
    turned = _angle(group)
    now = flip_signs(group)
    wanted = now if flips is None else flips
    why = _group_turn_refusal(group, shapes, turned, now, wanted)
    original = group.find(f"{_HP}orgSz")
    width, height = (float(original.get("width", "0")), float(original.get("height", "0"))) \
        if original is not None else (0.0, 0.0)
    middle = (width / 2, height / 2)
    rendering = group.find(f"{_HP}renderingInfo")
    if why is None and member_flip is not None and rendering is not None and turned \
            and not _close([_matrix(rendering[1])[0], _matrix(rendering[1])[4]], [1, 1], 1e-3):
        # resized and turned: Hancom mirrors it as drawn (rotate7 g-S1-30-f/v, g-S2-30-f/v)
        why = _mirror_resized_turned_group(group, shapes, now, wanted, member_flip, angle)
        if why is not None:
            raise _rotation_refused(group, why)
        return
    if member_flip is not None and rendering is not None and turned:
        # A turned group flips in place about where it holds its middle: the centre of its turn (less its move)
        held = _held_middle(group)
        if held is not None:
            middle = held
    elif member_flip is not None and rendering is not None:
        # A flip mirrors the group about the middle of the size it is drawn at (its own size through its
        # scaMatrix): a 12000 x 6000 group resized to 18000 x 9000 and flipped holds rotMatrix e3 18000 and centre
        # 9000 x 4500 -- whatever centre its resize left (Hancom's and resize both leave the old one).
        scale = _matrix(rendering[1])
        middle = (width * scale[0] / 2, height * scale[4] / 2)
    else:
        held = _held_middle(group)  # a turn goes about the centre the group holds (less its move)
        if held is not None and (abs(held[0] - middle[0]) > 1 or abs(held[1] - middle[1]) > 1):
            middle = held
    if why is None and (turned or now != (1, 1)):
        why = _turned_group_mismatch(group, shapes, turned, middle, now)
        if why is not None and member_flip is None and turned and now != (1, 1) and rendering is not None \
                and not _close([_matrix(rendering[1])[0], _matrix(rendering[1])[4]], [1, 1], 1e-3):
            # resized, turned and then flipped by Hancom's mirror: turned again as Hancom turns it
            mirrored_why = _turn_mirrored_group(group, now, angle)
            if mirrored_why is None:
                return
    if why is not None:
        raise _rotation_refused(group, why)
    if not angle and not turned and now == wanted == (1, 1):
        return
    rendering = group.find(f"{_HP}renderingInfo")
    move = _matrix(rendering[0]) if turned or now != (1, 1) else [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    factors = (_matrix(rendering[1])[0], _matrix(rendering[1])[4])
    # Each shape's place before any turn: its transMatrix less the group's move (in the outermost group's space).
    places = [(_matrix(s.find(f"{_HP}renderingInfo")[0])[2] - move[2],
               _matrix(s.find(f"{_HP}renderingInfo")[0])[5] - move[5]) for s in shapes]
    drawn: list[tuple[float, float, float, float]] = []  # each shape's own box as drawn: left, top, width, height
    for shape, (x, y) in zip(shapes, places):
        scale, own = _matrix(shape.find(f"{_HP}renderingInfo")[1]), shape.find(f"{_HP}orgSz")
        drawn.append((x + scale[2], y + scale[5], float(own.get("width", "0")) * scale[0],
                      float(own.get("height", "0")) * scale[4]))
    cos, sin = turn_cos_sin(angle)
    if angle or wanted != (1, 1):
        # Hancom turns the group about the middle of its own size (unscaled, in the space the members are drawn in)
        # and fits its box around the turned shapes -- the shapes, not the groups inside.
        corners = [corner for shape, (left, top, w, h) in zip(shapes, drawn) if _local(shape) != "container"
                   for corner in ((left, top), (left + w, top), (left + w, top + h), (left, top + h))]
        shift, box = turned_frame(cos, sin, middle, corners, wanted)
    else:  # back to 0: every shape back at its place, the group at its size
        shift, box = (0, 0), (round(width * factors[0]), round(height * factors[1]))
    size = group.find(f"{_HP}sz")
    if member_flip is not None and size is not None:
        # A flip mirrors the group in place about where it holds its middle: Hancom keeps its move, box and centre
        # (a group turned 30 degrees and flipped up-down keeps transMatrix 428, 3598 and 16856 x 12330, its turned
        # shapes no longer tight in the box when they are not even about the middle).
        shift = (round(move[2]), round(move[5]))
        box = (int(size.get("width", "0")), int(size.get("height", "0")))
    set_turn(group, cos, sin, middle, shift, wanted)
    flip = group.find(f"{_HP}flip")
    if flip is not None:
        flip.set("horizontal", "1" if wanted[0] == -1 else "0")
        flip.set("vertical", "1" if wanted[1] == -1 else "0")
    info = group.find(f"{_HP}rotationInfo")
    info.set("angle", str(angle))
    info.set("centerX", str(_half_up(middle[0] + shift[0]) if angle else int(middle[0])))
    info.set("centerY", str(_half_up(middle[1] + shift[1]) if angle else int(middle[1])))
    size = group.find(f"{_HP}sz")
    if size is not None:
        size.set("width", str(box[0]))
        size.set("height", str(box[1]))
    for shape, (x, y), (_, _, w, h) in zip(shapes, places, drawn):
        set_turn(shape, cos, sin, (middle[0] - x, middle[1] - y), (round(x + shift[0]), round(y + shift[1])),
                 wanted)
        member_info = shape.find(f"{_HP}rotationInfo")
        if member_info is not None and member_flip is not None:  # set as the group is flipped, kept as it turns
            # (a group inside takes the mark too: Hancom's nested-f holds 180 on it and its members)
            axis, before = member_flip
            mark = 0 if wanted == (1, 1) else ((180 if axis == 0 else 0) - _angle(shape) - before) % 360
            member_info.set("angle", str(mark))
        if _local(shape) == "container":
            continue  # a group inside keeps its centre (Hancom leaves it)
        # The middle of its own turned box as drawn, its size rounded first (6363.96 wide: 3182; 8485.28: 4242), and
        # its text across that width -- at 0 too, as Hangul saves a resized group's members (drawn 9000: 4500).
        if not angle and member_flip is None and any(_local(other) == "container" for other in shapes):
            # unturned in a group holding a group, Hancom keeps a resized member's own centre (1500 for 3000 drawn
            # at 4500), where it writes the drawn one in a group holding none
            own = shape.find(f"{_HP}orgSz")
            w, h = float(own.get("width", "0")), float(own.get("height", "0"))
        turned_width, turned_height = w * abs(cos) + h * abs(sin), w * abs(sin) + h * abs(cos)
        shape_info = shape.find(f"{_HP}rotationInfo")
        if shape_info is not None:
            shape_info.set("centerX", str(_half_up(turned_width) // 2))
            shape_info.set("centerY", str(_half_up(turned_height) // 2))
        set_text_width(shape, _half_up(turned_width))


def _mirror_axis_middle(group: Any, axis: int) -> float:
    """Where on *axis* (0 across, 1 down) Hancom mirrors a resized turned group: the middle of the whole-unit box
    around the group's own rectangle as drawn (its ``orgSz`` through its ``scaMatrix``, turned by its ``rotMatrix``
    and moved by its ``transMatrix``) -- for a group turned about the middle of its size as drawn, that middle."""

    rendering, original = group.find(f"{_HP}renderingInfo"), group.find(f"{_HP}orgSz")
    trans, scale, rot = (_matrix(matrix) for matrix in rendering)
    width = float(original.get("width", "0")) * scale[0]
    height = float(original.get("height", "0")) * scale[4]
    left, top = scale[2], scale[5]
    corners = [_apply(rot, point) for point in ((left, top), (left + width, top), (left + width, top + height),
                                                (left, top + height))]
    along = [corner[axis] + (trans[2] if axis == 0 else trans[5]) for corner in corners]
    return (math.floor(min(along) + 0.5) + math.floor(max(along) + 0.5)) / 2


def _mirror_rot(node: Any, axis: int, middle: float) -> None:
    """Mirror *node* as drawn about the page line *middle* on *axis*: its ``hc:rotMatrix`` row on that axis negated
    and moved so the drawn point lands at ``2 * middle`` less where it was (its ``transMatrix`` kept)."""

    from .shape_position import _matrix_number

    rendering = node.find(f"{_HP}renderingInfo")
    trans, rot = _matrix(rendering[0]), rendering[2]
    keys = ("e1", "e2", "e3") if axis == 0 else ("e4", "e5", "e6")
    move = trans[2] if axis == 0 else trans[5]
    values = [float(rot.get(key, "0")) for key in keys]
    for key, value in zip(keys, (-values[0], -values[1], 2 * middle - 2 * move - values[2])):
        rot.set(key, _matrix_number(round(value, 6) + 0.0))


def _mirror_resized_turned_group(group: Any, shapes: Sequence[Any], now: tuple[int, int], wanted: tuple[int, int],
                                 member_flip: tuple[int, int], angle: int) -> str | None:
    """Flip the resized and turned group *group* as Hancom 2024 flips one (rotate7 ``g-S1-30-f``, ``g-S1-30-v``,
    ``g-S2-30-f``, ``g-S2-30-v``: a group resized to 24000 x 6000 or 16000 x 16000 and turned 30 degrees, then
    flipped): the group and every member, as drawn, are mirrored about the middle of the box around the group's own
    rectangle as drawn (:func:`_mirror_axis_middle`; a group resized before its turn turns about the middle of its
    own size, not of the size it is drawn at, so that box is not its ``hp:sz``) -- each ``hc:rotMatrix`` row on
    the axis negated and moved, every ``transMatrix``, ``hp:offset``, ``hp:sz`` and member's centre kept. The
    group is turned the other way (*angle*), flagged *wanted*, its centre the middle of its ``hp:sz``, and its
    members marked as :func:`turn_group` marks them. ``None`` when done, else why not (nothing changed): before the
    flip the group must hold the form :func:`turn_group` writes, mirrored on the axes it is flipped on."""

    axis, before = member_flip
    check = copy.deepcopy(group)
    check_shapes = _all_shapes_inside(check)
    for flipped_axis in (0, 1):  # undo the mirrors it holds: mirrors about lines across each other commute
        if now[flipped_axis] == -1:
            middle = _mirror_axis_middle(check, flipped_axis)
            for node in [check, *check_shapes]:
                _mirror_rot(node, flipped_axis, middle)
    unturned_angle = _angle(group) if now in ((1, 1), (-1, -1)) else (-_angle(group)) % 360
    rot = _matrix(check.find(f"{_HP}renderingInfo")[2])
    a, b, c, d = rot[0], rot[1], rot[3], rot[4]
    det = (1 - a) * (1 - d) - b * c  # the point it turns about: (I - L) P = e
    if abs(det) < 1e-9:
        return "its matrices are not a turn about one point"
    pivot = (((1 - d) * rot[2] + b * rot[5]) / det, (c * rot[2] + (1 - a) * rot[5]) / det)
    why = _turned_group_mismatch(check, check_shapes, unturned_angle, pivot, (1, 1))
    if why is not None:
        return why
    middle = _mirror_axis_middle(group, axis)
    for node in [group, *shapes]:
        _mirror_rot(node, axis, middle)
    flip = group.find(f"{_HP}flip")
    if flip is not None:
        flip.set("horizontal", "1" if wanted[0] == -1 else "0")
        flip.set("vertical", "1" if wanted[1] == -1 else "0")
    info, size = group.find(f"{_HP}rotationInfo"), group.find(f"{_HP}sz")
    info.set("angle", str(angle))
    if size is not None:
        info.set("centerX", str(int(size.get("width", "0")) // 2))
        info.set("centerY", str(int(size.get("height", "0")) // 2))
    for shape in shapes:
        member_info = shape.find(f"{_HP}rotationInfo")
        if member_info is not None:
            mark = 0 if wanted == (1, 1) else ((180 if axis == 0 else 0) - _angle(shape) - before) % 360
            member_info.set("angle", str(mark))
    return None


def _turn_mirrored_group(group: Any, now: tuple[int, int], angle: int) -> str | None:
    """Turn to *angle* a resized group Hancom turned and then flipped (mirrored as drawn,
    :func:`_mirror_resized_turned_group`), as Hancom 2024 turns one (rotate8 ``g-S1-30-f-60``, ``g-S1-30-v-60``,
    ``g-S2-30-f-60``, ``g-S2-30-v-60``: resized, turned 30, flipped, then given 60 in the object dialog): the group
    and every member, as drawn, turn by what the angle changes (60 - 330 = 90) about where the group holds its centre
    (its ``rotationInfo`` centre less its move), the box around its shapes is fitted again (``hp:sz``,
    ``transMatrix``, ``hp:offset``) and its centre stays that point; its members' centres, text and marks stay.
    ``None`` when done, else why not (nothing changed): the group must hold the mirrored form."""

    from .shape_position import _half_up, _matrix_number, set_text_width, turn_cos_sin

    check = copy.deepcopy(group)
    check_shapes = _all_shapes_inside(check)
    for axis in (0, 1):  # it must hold the mirrored form: undone, a turn about one point
        if now[axis] == -1:
            middle = _mirror_axis_middle(check, axis)
            for node in [check, *check_shapes]:
                _mirror_rot(node, axis, middle)
    one_way = now in ((-1, 1), (1, -1))
    rot = _matrix(check.find(f"{_HP}renderingInfo")[2])
    a, b, c, d = rot[0], rot[1], rot[3], rot[4]
    det = (1 - a) * (1 - d) - b * c
    if abs(det) < 1e-9:
        return "its matrices are not a turn about one point"
    pivot = (((1 - d) * rot[2] + b * rot[5]) / det, (c * rot[2] + (1 - a) * rot[5]) / det)
    why = _turned_group_mismatch(check, check_shapes, (-_angle(group)) % 360 if one_way else _angle(group), pivot)
    if why is not None:
        return why
    shapes = _all_shapes_inside(group)
    info = group.find(f"{_HP}rotationInfo")
    group_move = _matrix(group.find(f"{_HP}renderingInfo")[0])
    held = (float(info.get("centerX", "0")) - group_move[2], float(info.get("centerY", "0")) - group_move[5])
    cos, sin = turn_cos_sin((angle - _angle(group)) % 360)
    turned: list[tuple[Any, tuple[float, float], list[float]]] = []
    corners: list[tuple[float, float]] = []
    for node in [group, *shapes]:
        rendering = node.find(f"{_HP}renderingInfo")
        move, scale, old = (_matrix(matrix) for matrix in rendering)
        place = (move[2] - group_move[2], move[5] - group_move[5])  # where it is in the group's space

        def turn(point: tuple[float, float]) -> tuple[float, float]:
            x, y = point[0] - held[0], point[1] - held[1]
            return cos * x - sin * y + held[0], sin * x + cos * y + held[1]

        linear = [cos * old[0] - sin * old[3], cos * old[1] - sin * old[4], sin * old[0] + cos * old[3],
                  sin * old[1] + cos * old[4]]
        moved = turn((old[2] + place[0], old[5] + place[1]))
        entries = [linear[0], linear[1], moved[0] - place[0], linear[2], linear[3], moved[1] - place[1]]
        turned.append((node, place, entries))
        if node is not group and _local(node) != "container":
            own = node.find(f"{_HP}orgSz")
            w, h = float(own.get("width", "0")), float(own.get("height", "0"))
            for x, y in ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)):
                sx, sy = scale[0] * x + scale[1] * y + scale[2], scale[3] * x + scale[4] * y + scale[5]
                corners.append((entries[0] * sx + entries[1] * sy + entries[2] + place[0],
                                entries[3] * sx + entries[4] * sy + entries[5] + place[1]))
    shift = (_half_up(-min(x for x, _ in corners)), _half_up(-min(y for _, y in corners)))
    box = (_half_up(max(x for x, _ in corners) + shift[0]), _half_up(max(y for _, y in corners) + shift[1]))
    for node, place, entries in turned:
        rendering = node.find(f"{_HP}renderingInfo")
        for key, value in zip(("e1", "e2", "e3", "e4", "e5", "e6"), entries):
            rendering[2].set(key, _matrix_number(round(value, 6) + 0.0))
        new_move = (round(place[0] + shift[0]), round(place[1] + shift[1]))
        rendering[0].set("e3", _matrix_number(float(new_move[0])))
        rendering[0].set("e6", _matrix_number(float(new_move[1])))
        offset = node.find(f"{_HP}offset")
        if offset is not None:
            offset.set("x", _unsigned(new_move[0]))
            offset.set("y", _unsigned(new_move[1]))
    size = group.find(f"{_HP}sz")
    if size is not None:
        size.set("width", str(box[0]))
        size.set("height", str(box[1]))
    info.set("angle", str(angle))
    info.set("centerX", str(_half_up(held[0] + shift[0])))
    info.set("centerY", str(_half_up(held[1] + shift[1])))
    # each member's centre the middle of its own box as drawn turned to the new angle, its text across that width,
    # as turn_group writes them (a 9000 x 6000 member at 60 degrees: 4848, 5397, lastWidth 9696)
    whole_cos, whole_sin = turn_cos_sin(angle)
    for shape in shapes:
        if _local(shape) == "container":
            continue
        own, scale = shape.find(f"{_HP}orgSz"), _matrix(shape.find(f"{_HP}renderingInfo")[1])
        w, h = float(own.get("width", "0")) * scale[0], float(own.get("height", "0")) * scale[4]
        turned_width = w * abs(whole_cos) + h * abs(whole_sin)
        turned_height = w * abs(whole_sin) + h * abs(whole_cos)
        shape_info = shape.find(f"{_HP}rotationInfo")
        if shape_info is not None:
            shape_info.set("centerX", str(_half_up(turned_width) // 2))
            shape_info.set("centerY", str(_half_up(turned_height) // 2))
        set_text_width(shape, _half_up(turned_width))
    return None


def _turned_group_mismatch(group: Any, shapes: Sequence[Any], angle: int, middle: tuple[float, float],
                           flips: tuple[int, int] = (1, 1)) -> str | None:
    """``None`` when the group turned *angle* degrees and flipped (*flips*) holds the form :func:`turn_group` (and
    Hancom) writes, so it can be turned or flipped again or back; else why not."""

    from .shape_position import turn_cos_sin, turn_entries

    cos, sin = turn_cos_sin(angle)
    rendering = group.find(f"{_HP}renderingInfo")
    move = _matrix(rendering[0])
    if not _close(move, [1, 0, move[2], 0, 1, move[5]], 1e-3) \
            or not _close(_matrix(rendering[2]), turn_entries(cos, sin, middle, flips), 0.05):
        return "its matrices are not a turn about its middle"
    for shape in shapes:
        own = shape.find(f"{_HP}renderingInfo")
        trans = _matrix(own[0])
        about = (middle[0] - (trans[2] - move[2]), middle[1] - (trans[5] - move[5]))
        if not _close(_matrix(own[2]), turn_entries(cos, sin, about, flips), 0.05):
            return "a member is turned otherwise than with its group"
    return None


def _ungroup_refused(why: str) -> Any:
    from ..errors import HwpxValueError

    return HwpxValueError(
        f"this group cannot be ungrouped: {why}",
        code="shape-ungroup-unsupported",
        context={"reason": why},
        suggestion="묶음의 꼴이 한/글 저장본으로 확인한 것(떠 있는 묶음, 구성원이 혼자 돌거나 뒤집히지 않음, 뒤집혔다면 "
                   "한쪽으로만 자기 크기에서)일 때 풉니다. 그렇지 않으면 묶음째 다룹니다.",
    )


def _apply(matrix: Sequence[float], point: tuple[float, float]) -> tuple[float, float]:
    x, y = point
    return matrix[0] * x + matrix[1] * y + matrix[2], matrix[3] * x + matrix[4] * y + matrix[5]


def _unsigned(value: int) -> str:
    return str(value & 0xFFFFFFFF)  # a negative offset in its unsigned 32-bit form, as Hancom writes it


def _signed(value: str | None) -> int:
    number = int(value or 0) & 0xFFFFFFFF
    return number - (1 << 32) if number >= 1 << 31 else number


def ungroup_refusal(group: Any) -> str | None:
    """Why the group *group* is not one :func:`ungroup_elements` knows how Hancom ungroups, or ``None``."""

    position = group.find(f"{_HP}pos")
    if position is None or position.get("treatAsChar") not in ("0", "false", "False"):
        return "it is set as a character"
    if position.get("horzAlign", "LEFT") not in ("LEFT", "CENTER") \
            or position.get("vertAlign", "TOP") not in ("TOP", "CENTER"):
        return "it is placed from another side of its frame than the left, top or centre"
    flip = group.find(f"{_HP}flip")
    flipped = flip is not None and "1" in (flip.get("horizontal"), flip.get("vertical"))
    for member in _shapes_inside(group):
        rendering = member.find(f"{_HP}renderingInfo")
        if rendering is None or [_local(child) for child in rendering] != ["transMatrix", "scaMatrix", "rotMatrix"]:
            return "a member is drawn by other matrices than one move, scale and turn"
        own_flip = member.find(f"{_HP}flip")
        own_turn = member.find(f"{_HP}rotationInfo")
        # a flipped group's members carry the mark of its flip as their angle (turn_group), not a turn of their own
        if (own_flip is not None and "1" in (own_flip.get("horizontal"), own_flip.get("vertical"))) or (
                own_turn is not None and (own_turn.get("angle") or "0") != "0" and not flipped):
            return "a member is turned or flipped on its own"
        scale = rendering.find(f"{_HC}scaMatrix")
        if scale is not None and any(abs(float(scale.get(key, "0"))) > 1e-6 for key in ("e2", "e4")):
            return "it is turned and then stretched (skewed): no Hancom-saved document shows one ungrouped"
    return None


def ungroup_elements(group: Any, *, ids: "IdSource | None") -> list[Any]:
    """Take the floating group *group* (``hp:container`` in a run) apart as Hancom 2024 ungroups one and return
    its members, now shapes of their own, in the order they stand in the run (the group's last member first,
    as Hancom puts them).

    Each member keeps its matrices, which already draw it where it is in the group (the group's turn and
    stretch included): where the shape they draw starts (its box's top left in the group, ``(x, y)``) is taken
    out of its move -- ``transMatrix`` e3/e6 and ``hp:offset`` lose ``(x, y)`` -- and given to its place, the
    group's ``hp:pos`` offsets plus ``(x, y)``, the rest of the group's ``hp:pos`` (its frames) kept. Its box
    (``hp:sz``) is the box of the shape drawn, ``hp:curSz`` its own size drawn at its scale (0 on an axis it is
    not stretched on), the rotation centre the middle of its box and the angle the group's. It takes the
    group's ``textWrap``, ``textFlow``, ``numberingType`` and outer margins, ``groupLevel`` 0, a new ``id``
    and the group's place in the drawing order -- the first member the group's ``zOrder``, each next one above it,
    every other object above the group moved up to make room (Hancom 2024 ungrouping a group at 1 between objects at
    0 and 2: members at 1 and 2, the object above at 3; rotate9 z-u) -- and keeps its ``instid`` (a connector attached to it
    stays). Hancom 2024 wrote this for a group of a rectangle and an ellipse ungrouped plain, stretched
    1.6 x 1.8 and 0.6 x 2.4, turned 30, 45 and 90 degrees, and stretched then turned 45 (objlim evidence ungroup2,
    ungroup3, ungroupstretch, ungroupstretch2, ungroupturned2, ungroupturned45b, ungroupturned90, ungroupturned45: its boxes a unit
    apart here and there). Hancom also hangs each member on the paragraph at whose height it
    starts, which needs the line layout; here every member stays in the group's paragraph, measured from it,
    which draws it in the same spot.

    The caller checks :func:`ungroup_refusal` first.
    """

    from ._document_primitives import _object_id
    from .shape_position import _matrix_number

    position = group.find(f"{_HP}pos")
    turn = group.find(f"{_HP}rotationInfo")
    angle = (turn.get("angle") or "0") if turn is not None else "0"
    left, top = _signed(position.get("horzOffset")), _signed(position.get("vertOffset"))
    margin = group.find(f"{_HP}outMargin")
    group_flip = group.find(f"{_HP}flip")
    group_size = group.find(f"{_HP}sz")
    group_box = (int(group_size.get("width", "0")), int(group_size.get("height", "0"))) if group_size is not None \
        else (0, 0)
    freed: list[Any] = []
    members = _shapes_inside(group)
    count, base = len(members), int(group.get("zOrder") or 0)
    inside = set(group.iter())
    for node in group.getroottree().getroot().iter():  # make room above the group for its members
        order = node.get("zOrder")
        if node not in inside and order is not None and order.lstrip("-").isdigit() and int(order) > base:
            node.set("zOrder", str(int(order) + count - 1))
    for index, member in enumerate(members):
        rendering = member.find(f"{_HP}renderingInfo")
        trans, scale, rot = ([float(node.get(key, "1" if key in ("e1", "e5") else "0"))
                              for key in ("e1", "e2", "e3", "e4", "e5", "e6")] for node in rendering)
        original = member.find(f"{_HP}orgSz")
        width, height = (int(original.get("width", "0")), int(original.get("height", "0"))) \
            if original is not None else (0, 0)
        drawn = [_apply(trans, _apply(rot, _apply(scale, corner)))
                 for corner in ((0.0, 0.0), (float(width), 0.0), (0.0, float(height)), (float(width), float(height)))]
        x0, y0 = min(p[0] for p in drawn), min(p[1] for p in drawn)
        box = (round(max(p[0] for p in drawn) - x0), round(max(p[1] for p in drawn) - y0))
        start = (round(x0), round(y0))
        rendering[0].set("e3", _matrix_number(trans[2] - start[0]))
        rendering[0].set("e6", _matrix_number(trans[5] - start[1]))
        offset = member.find(f"{_HP}offset")
        if offset is not None:
            offset.set("x", _unsigned(round(trans[2]) - start[0]))
            offset.set("y", _unsigned(round(trans[5]) - start[1]))
        current = member.find(f"{_HP}curSz")
        if current is not None:
            current.set("width", str(int(width * scale[0] + 1e-6)) if abs(scale[0] - 1) > 1e-6 else "0")
            current.set("height", str(int(height * scale[4] + 1e-6)) if abs(scale[4] - 1) > 1e-6 else "0")
        own_turn = member.find(f"{_HP}rotationInfo")
        if own_turn is not None:
            own_turn.set("angle", angle)
            own_turn.set("centerX", str(box[0] // 2))
            own_turn.set("centerY", str(box[1] // 2))
        own_flip = member.find(f"{_HP}flip")
        if own_flip is not None and group_flip is not None:  # its matrices already mirror it: it takes the flags
            own_flip.set("horizontal", group_flip.get("horizontal", "0"))
            own_flip.set("vertical", group_flip.get("vertical", "0"))
        if _local(member) == "container":  # a group inside: its shapes measured from it now, a level up
            for inner in _all_shapes_inside(member):
                inner_rendering = inner.find(f"{_HP}renderingInfo")
                inner_move = _matrix(inner_rendering[0])
                inner_rendering[0].set("e3", _matrix_number(inner_move[2] - start[0]))
                inner_rendering[0].set("e6", _matrix_number(inner_move[5] - start[1]))
                inner_offset = inner.find(f"{_HP}offset")
                if inner_offset is not None:
                    inner_offset.set("x", _unsigned(round(inner_move[2] - start[0])))
                    inner_offset.set("y", _unsigned(round(inner_move[5] - start[1])))
                inner.set("groupLevel", str(max(0, int(inner.get("groupLevel", "1")) - 1)))
        for name in ("textWrap", "textFlow", "numberingType"):
            if group.get(name) is not None:
                member.set(name, str(group.get(name)))
        member.set("groupLevel", "0")
        member.set("id", _object_id(ids))
        member.set("zOrder", str(base + index))  # the first member the group's place, the last on top
        member.append(member.makeelement(f"{_HP}sz", {
            "width": str(box[0]), "widthRelTo": "ABSOLUTE", "height": str(box[1]), "heightRelTo": "ABSOLUTE",
            "protect": "0"}))
        place = copy.deepcopy(position)
        place.tail = None
        # centred in its frame, a member keeps its place by its middle: the group's offset plus where it starts in
        # the group's box, less half the group's box, plus half its own (rotate9 g-center-30-u: 3281, -4330)
        centred = (position.get("horzAlign") == "CENTER", position.get("vertAlign") == "CENTER")
        place.set("horzOffset", _unsigned(left + start[0] + (box[0] // 2 - group_box[0] // 2 if centred[0] else 0)))
        place.set("vertOffset", _unsigned(top + start[1] + (box[1] // 2 - group_box[1] // 2 if centred[1] else 0)))
        member.append(place)
        if margin is not None:
            out = copy.deepcopy(margin)
            out.tail = None
        else:
            out = member.makeelement(f"{_HP}outMargin", {"left": "0", "right": "0", "top": "0", "bottom": "0"})
        member.append(out)
        freed.append(member)
    holder = group.getparent()
    at = list(holder).index(group)
    holder.remove(group)
    for member in reversed(freed):
        member.tail = None
        holder.insert(at, member)
        at += 1
    return list(reversed(freed))


__all__ = ["ContainerMember", "fit_groups_after_removal", "member_removal_refusal", "turn_group"]
