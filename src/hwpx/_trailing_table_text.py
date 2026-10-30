# SPDX-License-Identifier: Apache-2.0
"""QName-aware, bounded byte edits for text after a table in its paragraph."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from lxml import etree

from .errors import HwpxValueError
from .opc.xml_utils import _XML_MARKUP, parse_xml
from .oxml.namespaces import tag_in_family, tag_local_name


@dataclass
class _Span:
    start: int
    close: int
    end: int


def _element_spans(source: bytes, root: etree._Element) -> dict[etree._Element, _Span]:
    """Bind the secure parsed elements to original bytes without serializing."""
    elements = (node for node in root.iter() if isinstance(node.tag, str))
    stack: list[etree._Element] = []
    spans: dict[etree._Element, _Span] = {}
    for markup in _XML_MARKUP.finditer(source):
        token = markup.group()
        if token.startswith((b"<!", b"<?")):
            continue
        if token.startswith(b"</"):
            element = stack.pop()
            spans[element].close, spans[element].end = markup.start(), markup.end()
        else:
            element = next(elements)
            spans[element] = _Span(markup.start(), markup.end(), markup.end())
            if not token.endswith(b"/>"):
                stack.append(element)
    if stack or next(elements, None) is not None:
        raise HwpxValueError("could not bind paragraph XML to source bytes", context={"operation": "strip_trailing_table_text"})
    return spans


def _is(element: etree._Element, local: str) -> bool:
    return isinstance(element.tag, str) and tag_in_family(element.tag, "paragraph") and tag_local_name(element.tag) == local


def trailing_text_edits(
    source: bytes, predicate: Callable[[str], bool],
) -> list[tuple[int, int, bytes, str]]:
    """Select at most the last direct table per wrapper; every scan is bounded."""
    root = parse_xml(source)
    spans = _element_spans(source, root)
    edits: list[tuple[int, int, bytes, str]] = []
    for paragraph in root.iter():
        if not _is(paragraph, "p"):
            continue
        children = list(paragraph)
        cache_index = next((i for i, child in enumerate(children) if _is(child, "linesegarray")), None)
        if cache_index is None:
            continue
        candidate = None
        for run_index, run in enumerate(children[:cache_index]):
            if _is(run, "run"):
                for table_index, table in enumerate(run):
                    if _is(table, "tbl"):
                        candidate = run_index, table_index, run, table
        if candidate is None:
            continue
        run_index, table_index, run, table = candidate
        following_runs = children[run_index + 1:cache_index]
        if any(not _is(item, "run") or (item.text or "").strip() or (item.tail or "").strip()
               for item in following_runs) or (table.tail or "").strip() or (run.tail or "").strip():
            continue
        texts = list(run)[table_index + 1:]
        for item in following_runs:
            texts.extend(item)
        if not texts or any(not _is(item, "t") or len(item) or (item.tail or "").strip() for item in texts):
            continue
        text = "".join(item.text or "" for item in texts).strip()
        if predicate(text):
            original_run = spans[run]
            closing_run = source[original_run.close:original_run.end]
            edits.append((spans[table].end, spans[children[cache_index]].start, closing_run, text))
    return edits
