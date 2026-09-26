# SPDX-License-Identifier: Apache-2.0
"""Export HWPX document content to plain text, HTML, and Markdown formats.

All exporters accept either an :class:`~hwpx.document.HwpxDocument` instance
or raw HWPX file bytes and produce a string in the target format.
"""

from __future__ import annotations

from collections.abc import Callable

import io
import re
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from ..opc.security import guard_zip_file, parse_xml_stdlib, read_member
from ..oxml._document_primitives import _text_element_content
#: A caller-supplied redaction step. Declared here rather than imported from
#: mail_merge, which imports export_text — the two would form a cycle.
TextSanitizer = Callable[[str], str]

if TYPE_CHECKING:
    from ..document import HwpxDocument

__all__ = [
    "export_text",
    "export_html",
    "export_markdown",
]

_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_HP = f"{{{_HP_NS}}}"
#: Elements whose sub-lists hold text outside the body: headers and footers,
#: foot/end notes, memos (a memo's text sits under its ``hp:fieldBegin``) and
#: hidden comments. The exporters do not read below them.
_NOT_BODY_TAGS = frozenset(
    f"{_HP}{name}"
    for name in ("header", "footer", "footNote", "endNote", "fieldBegin", "hiddenComment")
)

_SECTION_RE = re.compile(r"^Contents/section\d+\.xml$")


def _section_xmls(source: HwpxDocument | bytes) -> list[ET.Element]:
    """Return a list of section root elements from *source*."""
    if isinstance(source, bytes):
        with ZipFile(io.BytesIO(source)) as zf:
            guard_zip_file(zf)
            names = sorted(n for n in zf.namelist() if _SECTION_RE.match(n))
            return [parse_xml_stdlib(read_member(zf, n), part_name=n) for n in names]
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
                parts.append(_text_element_content(child, tab=tab_token))
            elif child.tag == f"{_HP}tab" or _is_tab_control(child):
                parts.append(tab_token)
            elif child.tag == f"{_HP}lineBreak":
                parts.append("\n")
    return "".join(parts)


def _mask_text(text: str, masking_policy: "TextSanitizer | None") -> str:
    """Apply the caller's sanitizer, if one was supplied.

    Core knows text should pass a redaction step before it leaves the document;
    what counts as personal information is institutional policy and varies by
    jurisdiction and organisation, so the rule is the caller's. ``None`` means
    unmasked, which is what it has always meant here — reading is not writing,
    and flipping that default silently would be the wrong kind of surprise.
    """

    if masking_policy is None:
        return text
    return masking_policy(text)


def _table_cells_text(
    tbl: ET.Element,
    *,
    tab_token: str = "\t",
    masking_policy: "TextSanitizer | None" = None,
) -> list[list[str]]:
    """Return a row-major 2D list of cell texts from a table element."""
    rows: list[list[str]] = []
    for tr in tbl.findall(f"{_HP}tr"):
        row: list[str] = []
        for tc in tr.findall(f"{_HP}tc"):
            row.append(_cell_text(tc, tab_token=tab_token, masking_policy=masking_policy))
        rows.append(row)
    return rows


def _cell_text(
    tc: ET.Element,
    *,
    tab_token: str = "\t",
    masking_policy: "TextSanitizer | None" = None,
) -> str:
    cell_parts: list[str] = []
    for paragraph in _body_paragraphs(tc):
        text = _paragraph_text(paragraph, tab_token=tab_token)
        if text:
            cell_parts.append(text)
    return _mask_text("\n".join(cell_parts).strip(), masking_policy)


def _int_attribute(element: ET.Element | None, name: str) -> int | None:
    if element is None:
        return None
    try:
        return int(element.get(name) or "")
    except ValueError:
        return None


def _table_grid_text(
    tbl: ET.Element,
    *,
    tab_token: str = "\t",
    masking_policy: "TextSanitizer | None" = None,
) -> list[list[str]]:
    """Cell texts laid on the table's column grid.

    Each cell goes to its ``hp:cellAddr`` position (a cell without one follows
    the previous cell of its row), and the grid is as wide as the widest row,
    so no cell is dropped. The positions a merged cell covers stay empty.
    """
    placed: dict[tuple[int, int], str] = {}
    width = 0
    for row_index, tr in enumerate(tbl.findall(f"{_HP}tr")):
        column = 0
        for tc in tr.findall(f"{_HP}tc"):
            address = tc.find(f"{_HP}cellAddr")
            row_addr = _int_attribute(address, "rowAddr")
            col_addr = _int_attribute(address, "colAddr")
            if row_addr is None or col_addr is None or row_addr < 0 or col_addr < 0:
                row_addr, col_addr = row_index, column
            while (row_addr, col_addr) in placed:
                col_addr += 1
            placed[(row_addr, col_addr)] = _cell_text(tc, tab_token=tab_token, masking_policy=masking_policy)
            span = _int_attribute(tc.find(f"{_HP}cellSpan"), "colSpan")
            column = col_addr + max(span or 1, 1)
            width = max(width, column)
    if not placed:
        return []
    height = max(row for row, _ in placed) + 1
    return [[placed.get((row, col), "") for col in range(width)] for row in range(height)]


def _body_paragraphs(element: ET.Element) -> list[ET.Element]:
    """Paragraphs below *element* in document order.

    Paragraphs of nested tables and text boxes count; those of notes, memos,
    headers and footers do not.
    """
    found: list[ET.Element] = []
    for child in element:
        if child.tag in _NOT_BODY_TAGS:
            continue
        if child.tag == f"{_HP}p":
            found.append(child)
        found.extend(_body_paragraphs(child))
    return found


def _placed_blocks(p: ET.Element) -> list[ET.Element]:
    """Tables and text boxes placed in paragraph *p*, in document order, outermost only.

    A text box is returned as its ``hp:drawText``. A table or text box nested in
    a cell is already part of that cell's text, and one in a header, footer,
    note or memo is not body text.
    """
    found: list[ET.Element] = []
    for child in p:
        if child.tag in _NOT_BODY_TAGS:
            continue
        if child.tag in (f"{_HP}tbl", f"{_HP}drawText"):
            found.append(child)
            continue
        found.extend(_placed_blocks(child))
    return found


def _text_box_paragraphs(draw_text: ET.Element) -> list[ET.Element]:
    return draw_text.findall(f"{_HP}subList/{_HP}p")


def _markdown_cell(text: str) -> str:
    """Cell text on one Markdown table line: ``|`` escaped, line breaks as ``<br>``."""
    return text.replace("|", "\\|").replace("\n", "<br>")


def export_text(
    source: HwpxDocument | bytes,
    *,
    paragraph_separator: str = "\n",
    section_separator: str = "\n\n",
    include_tables: bool = True,
    tab_token: str = "\t",
    masking_policy: "TextSanitizer | None" = None,
) -> str:
    """Export document content as plain text.

    The tables and text boxes of a paragraph follow its text, in document order.
    """
    sections = _section_xmls(source)
    section_texts: list[str] = []
    for section_root in sections:
        para_texts: list[str] = []

        def emit(p: ET.Element) -> None:
            text = _mask_text(_paragraph_text(p, tab_token=tab_token), masking_policy)
            if text:
                para_texts.append(text)
            for block in _placed_blocks(p):
                if block.tag == f"{_HP}drawText":
                    for inner in _text_box_paragraphs(block):
                        emit(inner)
                elif include_tables:
                    rows = _table_cells_text(block, tab_token=tab_token, masking_policy=masking_policy)
                    for row in rows:
                        para_texts.append(tab_token.join(row))

        for p in _iter_paragraphs(section_root):
            emit(p)
        section_texts.append(paragraph_separator.join(para_texts))
    return section_separator.join(section_texts)


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def export_html(
    source: HwpxDocument | bytes,
    *,
    include_tables: bool = True,
    full_document: bool = True,
    title: str = "HWPX Document",
    tab_token: str = "\t",
    masking_policy: "TextSanitizer | None" = None,
) -> str:
    """Export document content as HTML.

    The tables and text boxes of a paragraph follow its text, in document order.
    """
    sections = _section_xmls(source)
    body_parts: list[str] = []

    def emit(p: ET.Element) -> None:
        text = _mask_text(_paragraph_text(p, tab_token=tab_token), masking_policy)
        if text:
            body_parts.append(f"<p>{_escape_html(text)}</p>")
        for block in _placed_blocks(p):
            if block.tag == f"{_HP}drawText":
                for inner in _text_box_paragraphs(block):
                    emit(inner)
                continue
            rows = _table_cells_text(block, tab_token=tab_token, masking_policy=masking_policy) if include_tables else []
            if rows:
                body_parts.append('<table border="1">')
                for row in rows:
                    body_parts.append("  <tr>")
                    for cell in row:
                        body_parts.append(f"    <td>{_escape_html(cell)}</td>")
                    body_parts.append("  </tr>")
                body_parts.append("</table>")

    for sec_idx, section_root in enumerate(sections):
        if sec_idx > 0:
            body_parts.append("<hr />")
        for p in _iter_paragraphs(section_root):
            emit(p)
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


def export_markdown(
    source: HwpxDocument | bytes,
    *,
    include_tables: bool = True,
    section_separator: str = "\n---\n\n",
    tab_token: str = "\t",
    masking_policy: "TextSanitizer | None" = None,
) -> str:
    """Export document content as Markdown.

    The tables and text boxes of a paragraph follow its text, in document order.
    """
    sections = _section_xmls(source)
    section_parts: list[str] = []
    for section_root in sections:
        lines: list[str] = []

        def emit(p: ET.Element) -> None:
            text = _mask_text(_paragraph_text(p, tab_token=tab_token), masking_policy)
            if text:
                lines.append(text)
                lines.append("")
            for block in _placed_blocks(p):
                if block.tag == f"{_HP}drawText":
                    for inner in _text_box_paragraphs(block):
                        emit(inner)
                    continue
                rows = _table_grid_text(block, tab_token=tab_token, masking_policy=masking_policy) if include_tables else []
                if rows:
                    header = rows[0]
                    lines.append("| " + " | ".join(_markdown_cell(cell) for cell in header) + " |")
                    lines.append("| " + " | ".join("---" for _ in header) + " |")
                    for row in rows[1:]:
                        lines.append("| " + " | ".join(_markdown_cell(cell) for cell in row) + " |")
                    lines.append("")

        for p in _iter_paragraphs(section_root):
            emit(p)
        section_parts.append("\n".join(lines).rstrip())
    return section_separator.join(section_parts)
