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

from typing import Any, Mapping

from .namespaces import HH, HP

#: The namespace of the ``hp:case`` holding an outline heading of level 8 to 10.
PARAGRAPH_2016_NAMESPACE = "http://www.hancom.co.kr/hwpml/2016/paragraph"

#: The first ``level`` (0-based) of an outline heading Hancom writes in an ``hp:switch``.
FIRST_SWITCHED_OUTLINE_LEVEL = 7


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
