# SPDX-License-Identifier: Apache-2.0
"""Export HWPX document content to plain text, HTML, and Markdown formats.

All exporters accept either an :class:`~hwpx.document.HwpxDocument` instance
or raw HWPX file bytes and produce a string in the target format.
"""

from __future__ import annotations

import io
import re
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET
from zipfile import ZipFile

if TYPE_CHECKING:
    from ..document import HwpxDocument

__all__ = [
    "export_text",
    "export_html",
    "export_markdown",
]

_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_HP = f"{{{_HP_NS}}}"

_SECTION_RE = re.compile(r"^Contents/section\d+\.xml$")


def _section_xmls(source: HwpxDocument | bytes) -> list[ET.Element]:
    """Return a list of section root elements from *source*."""
    if isinstance(source, bytes):
        with ZipFile(io.BytesIO(source)) as zf:
            names = sorted(n for n in zf.namelist() if _SECTION_RE.match(n))
            return [ET.fromstring(zf.read(n)) for n in names]
    return [sec.element for sec in source._root.sections]


def _iter_paragraphs(section: ET.Element) -> list[ET.Element]:
    """Yield top-level ``<hp:p>`` elements in document order."""
    return section.findall(f"{_HP}p")


def _is_tab_control(child: ET.Element) -> bool:
    return child.tag == f"{_HP}ctrl" and (child.get("id") or "").lower() == "tab"


def _paragraph_text(p: ET.Element, *, tab_token: str = "\t") -> str:
    """Extract paragraph text from direct runs, preserving tab semantics."""
    parts: list[str] = []
    for run in p.findall(f"{_HP}run"):
        for child in run:
            if child.tag == f"{_HP}t":
                if child.text:
                    parts.append(child.text)
            elif child.tag == f"{_HP}tab" or _is_tab_control(child):
                parts.append(tab_token)
            elif child.tag == f"{_HP}lineBreak":
                parts.append("\n")
    return "".join(parts)


def _table_cells_text(tbl: ET.Element, *, tab_token: str = "\t") -> list[list[str]]:
    """Return a row-major 2D list of cell texts from a table element."""
    rows: list[list[str]] = []
    for tr in tbl.findall(f"{_HP}tr"):
        row: list[str] = []
        for tc in tr.findall(f"{_HP}tc"):
            cell_parts: list[str] = []
            for paragraph in tc.findall(f".//{_HP}p"):
                text = _paragraph_text(paragraph, tab_token=tab_token)
                if text:
                    cell_parts.append(text)
            row.append("\n".join(cell_parts).strip())
        rows.append(row)
    return rows


def _find_tables(p: ET.Element) -> list[ET.Element]:
    return p.findall(f".//{_HP}tbl")


def export_text(source: HwpxDocument | bytes, *, paragraph_separator: str = "\n", section_separator: str = "\n\n", include_tables: bool = True, tab_token: str = "\t") -> str:
    """Export document content as plain text."""
    sections = _section_xmls(source)
    section_texts: list[str] = []
    for section_root in sections:
        para_texts: list[str] = []
        for p in _iter_paragraphs(section_root):
            text = _paragraph_text(p, tab_token=tab_token)
            if text:
                para_texts.append(text)
            if include_tables:
                for tbl in _find_tables(p):
                    rows = _table_cells_text(tbl, tab_token=tab_token)
                    for row in rows:
                        para_texts.append(tab_token.join(row))
        section_texts.append(paragraph_separator.join(para_texts))
    return section_separator.join(section_texts)


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def export_html(source: HwpxDocument | bytes, *, include_tables: bool = True, full_document: bool = True, title: str = "HWPX Document", tab_token: str = "\t") -> str:
    """Export document content as HTML."""
    sections = _section_xmls(source)
    body_parts: list[str] = []
    for sec_idx, section_root in enumerate(sections):
        if sec_idx > 0:
            body_parts.append("<hr />")
        for p in _iter_paragraphs(section_root):
            text = _paragraph_text(p, tab_token=tab_token)
            if text:
                body_parts.append(f"<p>{_escape_html(text)}</p>")
            if include_tables:
                for tbl in _find_tables(p):
                    rows = _table_cells_text(tbl, tab_token=tab_token)
                    if rows:
                        body_parts.append('<table border="1">')
                        for row in rows:
                            body_parts.append("  <tr>")
                            for cell in row:
                                body_parts.append(f"    <td>{_escape_html(cell)}</td>")
                            body_parts.append("  </tr>")
                        body_parts.append("</table>")
    body = "\n".join(body_parts)
    if full_document:
        return (
            "<!DOCTYPE html>\n"
            '<html lang="ko">\n'
            "<head>\n"
            '  <meta charset="utf-8" />\n'
            f"  <title>{_escape_html(title)}</title>\n"
            "</head>\n"
            "<body>\n"
            f"{body}\n"
            "</body>\n"
            "</html>"
        )
    return body


def export_markdown(source: HwpxDocument | bytes, *, include_tables: bool = True, section_separator: str = "\n---\n\n", tab_token: str = "\t") -> str:
    """Export document content as Markdown."""
    sections = _section_xmls(source)
    section_parts: list[str] = []
    for section_root in sections:
        lines: list[str] = []
        for p in _iter_paragraphs(section_root):
            text = _paragraph_text(p, tab_token=tab_token)
            if text:
                lines.append(text)
                lines.append("")
            if include_tables:
                for tbl in _find_tables(p):
                    rows = _table_cells_text(tbl, tab_token=tab_token)
                    if rows:
                        header = rows[0]
                        lines.append("| " + " | ".join(header) + " |")
                        lines.append("| " + " | ".join("---" for _ in header) + " |")
                        for row in rows[1:]:
                            padded = row + [""] * max(0, len(header) - len(row))
                            lines.append("| " + " | ".join(padded[: len(header)]) + " |")
                        lines.append("")
        section_parts.append("\n".join(lines).rstrip())
    return section_separator.join(section_parts)
