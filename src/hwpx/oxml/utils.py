from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple, Union

from lxml import etree

_TRUE_VALUES = {"1", "true", "True", "TRUE"}
_FALSE_VALUES = {"0", "false", "False", "FALSE"}


def local_name(node: etree._Element) -> str:
    """Return the local (namespace-stripped) tag name for *node*."""
    return etree.QName(node).localname


def parse_int(value: Optional[str], *, allow_none: bool = True) -> Optional[int]:
    """Parse *value* as an integer.

    When *allow_none* is ``True`` (the default) ``None`` is returned unchanged.
    ``ValueError`` is raised if conversion fails.
    """

    if value is None:
        if allow_none:
            return None
        raise ValueError("Missing integer value")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive branch
        raise ValueError(f"Invalid integer value: {value!r}") from exc


def parse_bool(value: Optional[str], *, default: Optional[bool] = None) -> Optional[bool]:
    """Convert a string attribute into a boolean."""

    if value is None:
        return default
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def text_or_none(node: etree._Element) -> Optional[str]:
    """Return the text content of *node* stripped of leading/trailing whitespace."""

    if node.text is None:
        return None
    text = node.text.strip()
    return text if text else None


XmlSource = Union[str, bytes, Path, etree._Element, etree._ElementTree]


def coerce_xml_source(source: XmlSource) -> Tuple[etree._Element, etree._ElementTree]:
    """Return ``(root, tree)`` for *source*.

    *source* may be an ``lxml`` element, element tree, path-like object or
    raw XML (``str``/``bytes``). The helper normalises the input so that callers
    always receive both the element and the owning tree which is handy for XSD
    validation.
    """

    if isinstance(source, etree._Element):
        return source, source.getroottree()
    if isinstance(source, etree._ElementTree):
        return source.getroot(), source

    if isinstance(source, (str, Path)):
        path = Path(source)
        if path.exists():
            tree = etree.parse(str(path))
            return tree.getroot(), tree
        xml_bytes = str(source).encode("utf-8")
    else:
        xml_bytes = bytes(source)

    root = etree.fromstring(xml_bytes)
    return root, root.getroottree()
