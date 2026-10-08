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
from .shape_position import validate_draw_text_vert_align, validate_shape_size

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
    the bare constructor, which expects an already-built element.

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
        line_width: str = "33",
        fill_color: str | None = None,
    ) -> "ContainerMember":
        """A rectangle member — see :func:`_create_rectangle_element`."""

        from .objects import _create_rectangle_element

        element = _create_rectangle_element(
            width, height, ratio=ratio, line_color=line_color,
            line_width=line_width, fill_color=fill_color,
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
        line_width: str = "33",
        fill_color: str | None = None,
    ) -> "ContainerMember":
        """An ellipse member — see :func:`_create_ellipse_element`."""

        from .objects import _create_ellipse_element

        element = _create_ellipse_element(
            width, height, line_color=line_color, line_width=line_width,
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
        line_width: str = "33",
        fill_color: str | None = None,
        closed: bool = True,
    ) -> "ContainerMember":
        """A polygon member — see :func:`_create_polygon_element`. It is
        closed (the first vertex repeated at the end) unless *closed* is
        false."""

        from .objects import _closed_points, _create_polygon_element

        element = _create_polygon_element(
            _closed_points(points) if closed else points,
            line_color=line_color, line_width=line_width, fill_color=fill_color,
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
        line_width: str = "33",
    ) -> "ContainerMember":
        """A line member from (*start_x*, *start_y*) to (*end_x*, *end_y*) in the
        group's space. Like a freestanding line it is placed at the top-left
        of its two ends, which it keeps relative to that corner."""

        from .objects import _create_line_element

        x, y = min(start_x, end_x), min(start_y, end_y)
        element = _create_line_element(
            start_x - x, start_y - y, end_x - x, end_y - y,
            line_color=line_color, line_width=line_width,
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
        line_width: str = "33",
        fill_color: str | None = None,
        name: str = "",
        editable: bool = False,
        margin: dict[str, int] | None = None,
        char_pr_id_ref: str | int | None = None,
        para_pr_id_ref: str | int | None = None,
        vert_align: str | None = None,
    ) -> "ContainerMember":
        """A rectangle holding *text*, as :meth:`HwpxOxmlShape.set_draw_text`
        writes it (same *name*, *editable*, *margin*, *char_pr_id_ref*,
        *para_pr_id_ref* and *vert_align*). The text is written when the group
        is inserted, so its paragraphs take ids unused in the section; a bad
        *vert_align* is refused here, before any document is touched."""

        validate_draw_text_vert_align(vert_align)
        member = cls.rect(x, y, width, height, ratio=ratio, line_color=line_color,
                          line_width=line_width, fill_color=fill_color)
        spec = _MemberText(text, name, editable, dict(margin) if margin else None,
                           char_pr_id_ref, para_pr_id_ref, vert_align)
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


__all__ = ["ContainerMember"]
