# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import logging
from copy import deepcopy
from pathlib import Path
from typing import Optional, Tuple, Union

logger = logging.getLogger(__name__)

from lxml import etree

from .namespaces import HP10_NS, HP_NS, tag_local_name

_TRUE_VALUES = {"1", "true", "True", "TRUE"}
_FALSE_VALUES = {"0", "false", "False", "FALSE"}


def local_name(node: etree._Element) -> str:
    """Return the local (namespace-stripped) tag name for *node*.

    Comment and processing-instruction nodes expose a callable ``tag`` (e.g.
    ``lxml.etree.Comment``) instead of a string; ``tag_local_name`` maps those
    to ``""`` so callers that filter children by local name transparently skip
    them (mirrors ``tag_local_name`` / ``_element_local_name``).
    """
    return tag_local_name(node.tag)


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


#: Text positions Hancom gives the inline elements of ``hp:t`` in a paragraph's
#: layout cache (``hp:lineseg@textpos``). A tab takes 8, as an inline control of
#: the HWP text model does; a line break, a hyphen and the two fixed spaces
#: take 1. Other inline elements (highlight marks and the like) take none.
HANCOM_INLINE_TEXT_WIDTHS = {"tab": 8, "lineBreak": 1, "hyphen": 1, "nbSpace": 1, "fwSpace": 1}


def hancom_text_length(text_element: etree._Element) -> int:
    """Length of an ``hp:t`` in Hancom's text positions, inline elements included."""

    total = len(text_element.text or "")
    for child in text_element:
        if isinstance(child.tag, str):
            total += HANCOM_INLINE_TEXT_WIDTHS.get(tag_local_name(child.tag), 0)
            total += len("".join(child.itertext()))
        total += len(child.tail or "")
    return total


def tabs_as_elements(root: etree._Element) -> bool:
    """Write each tab character inside ``hp:t`` of *root* as an ``hp:tab`` element.

    Hancom reads a tab only as an ``hp:tab`` element inside ``hp:t``; with a tab
    character there it keeps laying the paragraph out, so the document never
    finishes opening. Returns whether anything changed.
    """

    changed = False
    for text in root.iter(f"{{{HP_NS}}}t", f"{{{HP10_NS}}}t"):
        tab_tag = text.tag[: -len("t")] + "tab"
        value = text.text or ""
        if "	" in value:
            head, *rest = value.split("	")
            text.text = head
            for index, segment in enumerate(rest):
                tab = text.makeelement(tab_tag, {})
                tab.tail = segment
                text.insert(index, tab)
            changed = True
        for child in list(text):
            tail = child.tail or ""
            if "	" in tail:
                head, *rest = tail.split("	")
                child.tail = head
                position = text.index(child) + 1
                for offset, segment in enumerate(rest):
                    tab = text.makeelement(tab_tag, {})
                    tab.tail = segment
                    text.insert(position + offset, tab)
                changed = True
    return changed


def tab_elements_in(xml: bytes) -> bytes:
    """*xml* with each tab character inside ``hp:t`` written as an ``hp:tab`` element."""

    if b"	" not in xml:
        return xml
    root = etree.fromstring(xml)
    if not tabs_as_elements(root):
        return xml
    return etree.tostring(root, encoding="utf-8", xml_declaration=True)


def without_markup_nodes(element: etree._Element) -> etree._Element:
    """*element*, or a copy of it without XML comments and processing instructions.

    Parts are serialized with ``xml.etree``, which cannot write lxml's comment
    and processing-instruction nodes; a part read from a document that carries
    them (real documents do, inside table rows) failed to save once edited.
    They are not content, so the copy drops them and keeps the text after them.
    """

    if not isinstance(element, etree._Element):
        return element
    if next(element.iter(etree.Comment), None) is None and next(element.iter(etree.ProcessingInstruction), None) is None:
        return element
    copy = deepcopy(element)
    etree.strip_elements(copy, etree.Comment, etree.ProcessingInstruction, with_tail=False)
    return copy
