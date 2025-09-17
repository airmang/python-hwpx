from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from lxml import etree

from .utils import local_name


@dataclass(slots=True)
class GenericElement:
    """Fallback representation for XML elements without a specialised model."""

    name: str
    attributes: Dict[str, str] = field(default_factory=dict)
    children: List["GenericElement"] = field(default_factory=list)
    text: Optional[str] = None


def parse_generic_element(node: etree._Element) -> GenericElement:
    """Convert *node* into a :class:`GenericElement`."""

    children = [parse_generic_element(child) for child in node]
    text = node.text if node.text is not None else None
    return GenericElement(
        name=local_name(node),
        attributes={key: value for key, value in node.attrib.items()},
        children=children,
        text=text,
    )
