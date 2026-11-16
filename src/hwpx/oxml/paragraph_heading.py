# SPDX-License-Identifier: Apache-2.0
"""The heading (``hh:heading``) of a paragraph shape, as Hancom writes it.

The 2011 paragraph namespace has outline levels 1 to 7 (``level`` 0 to 6). Outline levels
8 to 10 exist only in the 2016 paragraph namespace, and Hancom writes such a heading in an
``hp:switch``: its ``hp:case`` for that namespace holds the heading, its ``hp:default``
holds ``type="NONE"`` for readers of the older one. The outline styles 개요 8 to 개요 10
of a new document are written so, and Hancom writes a bare outline heading of those
levels back the same way when it saves.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from .namespaces import HH, HP

__all__ = [
    "FIRST_SWITCHED_OUTLINE_LEVEL",
    "PARAGRAPH_2016_NAMESPACE",
    "heading_outline_level",
    "outline_style_level",
    "paragraph_heading",
    "set_paragraph_heading",
]

#: The namespace of the ``hp:case`` holding an outline heading of level 8 to 10.
PARAGRAPH_2016_NAMESPACE = "http://www.hancom.co.kr/hwpml/2016/paragraph"

#: The first ``level`` (0-based) of an outline heading Hancom writes in an ``hp:switch``.
FIRST_SWITCHED_OUTLINE_LEVEL = 7

#: The names of Hancom's outline styles: ``개요 1`` … ``개요 10`` (``Outline 1`` … in English).
_OUTLINE_STYLE_NAME = re.compile(r"^(?:개요|Outline)\s*(\d+)$")


def _local(element: Any) -> str:
    tag = element.tag
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _children(element: Any, local_name: str) -> list[Any]:
    return [child for child in element if _local(child) == local_name]


def paragraph_heading(para_pr: Any) -> Any | None:
    """The ``hh:heading`` of paragraph shape *para_pr*: its own, else the one an
    ``hp:switch`` holds (in its ``hp:case``, else in its ``hp:default``)."""

    own = _children(para_pr, "heading")
    if own:
        return own[0]
    for switch in _children(para_pr, "switch"):
        for branch in (*_children(switch, "case"), *_children(switch, "default")):
            found = _children(branch, "heading")
            if found:
                return found[0]
    return None


def heading_outline_level(para_pr: Any) -> int | None:
    """The outline level (1 to 10) paragraph shape *para_pr* gives its paragraphs, or ``None``.

    A paragraph shape makes its paragraphs outline paragraphs of level L when its heading
    (:func:`paragraph_heading`) has ``type="OUTLINE"`` and ``level="L-1"``. Any other
    heading (a number, a bullet, ``NONE``) or no heading gives ``None``.

    This is the one rule every reader of a paragraph's outline level uses
    (``Paragraph.outline_level``, ``doc.styles.outline_level``, the heading levels of the
    exports). It reads the attributes as OWPML declares them and as Hancom writes them —
    in the 1,299 HWPX files of the public and test corpora (32,133 headings) every
    ``type`` is upper case and every outline ``level`` is 0 to 9. So ``type`` is compared
    as written (``"outline"`` is not ``"OUTLINE"``), and a ``level`` that is missing or
    not a whole number from 0 to 9 takes the attribute's default 0, level 1.
    *para_pr* is an ``hh:paraPr`` element (lxml or ElementTree).
    """

    heading = paragraph_heading(para_pr)
    if heading is None or heading.get("type") != "OUTLINE":
        return None
    raw = (heading.get("level") or "").strip()
    level = int(raw) if raw.isdecimal() else 0
    return level + 1 if level <= 9 else 1


def outline_style_level(name: str | None) -> int | None:
    """The outline level of a style named *name*: 3 for ``개요 3`` or ``Outline 3``, else ``None``.

    These are the names Hancom gives its outline styles. Spaces around the name and
    between the word and the number do not count; anything else does (``개요3`` is
    level 3, ``개요 3 강조`` is not an outline style).
    """

    match = _OUTLINE_STYLE_NAME.match((name or "").strip())
    return int(match.group(1)) if match else None


def set_paragraph_heading(para_pr: Any, attributes: Mapping[str, str]) -> None:
    """Give paragraph shape *para_pr* the heading *attributes* (``type``, ``idRef``,
    ``level``) right after its ``hh:align``, in place of the heading it had (its own
    or one in an ``hp:switch``). An outline heading of level 8 to 10 goes in an
    ``hp:switch`` as Hancom writes it."""

    for child in list(para_pr):
        name = _local(child)
        if name == "heading" or (name == "switch" and any(_local(node) == "heading" for node in child.iter())):
            para_pr.remove(child)
    heading = para_pr.makeelement(f"{HH}heading", dict(attributes))
    placed = heading
    if attributes.get("type") == "OUTLINE" and int(attributes.get("level") or 0) >= FIRST_SWITCHED_OUTLINE_LEVEL:
        placed = para_pr.makeelement(f"{HP}switch", {})
        case = placed.makeelement(f"{HP}case", {f"{HP}required-namespace": PARAGRAPH_2016_NAMESPACE})
        case.append(heading)
        default = placed.makeelement(f"{HP}default", {})
        default.append(default.makeelement(f"{HH}heading", {"type": "NONE", "idRef": "0", "level": "0"}))
        placed.append(case)
        placed.append(default)
    aligns = [index for index, child in enumerate(para_pr) if _local(child) == "align"]
    para_pr.insert(aligns[-1] + 1 if aligns else 0, placed)
