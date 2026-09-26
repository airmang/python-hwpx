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
_HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
#: Elements whose sub-lists hold text outside the body: headers and footers,
#: foot/end notes, memos (a memo's text sits under its ``hp:fieldBegin``) and
#: hidden comments. The exporters do not read below them.
_NOT_BODY_TAGS = frozenset(
    f"{_HP}{name}"
    for name in ("header", "footer", "footNote", "endNote", "fieldBegin", "hiddenComment")
)

_SECTION_RE = re.compile(r"^Contents/section\d+\.xml$")

#: Placed blocks whose own paragraphs are exported in place: text boxes and captions.
_PARAGRAPH_BLOCKS = frozenset((f"{_HP}drawText", f"{_HP}caption"))


def _header_xml(source: HwpxDocument | bytes) -> ET.Element | None:
    """The document's ``header.xml`` root (styles, numberings, bullets), if it has one."""
    if isinstance(source, bytes):
        with ZipFile(io.BytesIO(source)) as zf:
            guard_zip_file(zf)
            name = "Contents/header.xml"
            return parse_xml_stdlib(read_member(zf, name), part_name=name) if name in zf.namelist() else None
    headers = source._root.headers
    return headers[0].element if headers else None


_HANGUL_SYLLABLES = "가나다라마바사아자차카타파하"
_HANGUL_JAMO = "ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ"
_ROMAN = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"),
          (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))


def _roman(value: int) -> str:
    out = ""
    for amount, symbol in _ROMAN:
        count, value = divmod(value, amount)
        out += symbol * count
    return out


_NUMBER_FORMATS: dict[str, Callable[[int], str]] = {
    "HANGUL_SYLLABLE": lambda n: _HANGUL_SYLLABLES[(n - 1) % len(_HANGUL_SYLLABLES)],
    "HANGUL_JAMO": lambda n: _HANGUL_JAMO[(n - 1) % len(_HANGUL_JAMO)],
    "CIRCLED_DIGIT": lambda n: chr(0x2460 + n - 1) if n <= 20 else str(n),
    "CIRCLED_HANGUL_SYLLABLE": lambda n: chr(0x326E + (n - 1) % 14),
    "CIRCLED_HANGUL_JAMO": lambda n: chr(0x3260 + (n - 1) % 14),
    "ROMAN_CAPITAL": _roman,
    "ROMAN_SMALL": lambda n: _roman(n).lower(),
    "LATIN_CAPITAL": lambda n: chr(ord("A") + (n - 1) % 26),
    "LATIN_SMALL": lambda n: chr(ord("a") + (n - 1) % 26),
}


#: Symbol-font characters (private use area) that Hancom's text save writes as a Unicode
#: symbol when one of them is a whole list label. Other labels, and symbol characters in
#: the text, are kept.
_BULLET_SYMBOLS = {
    "\uf046": "\u261e",  # ☞
    "\uf06c": "\u25cf",  # ●
    "\uf06e": "\u25a0",  # ■
    "\uf06f": "\u25a1",  # □
    "\uf075": "\u25c6",  # ◆
    "\uf076": "\u2605",  # ★
    "\uf077": "\u25c6",  # ◆
    "\uf09f": "\u25cf",  # ●
    "\uf0a1": "\u25cb",  # ○
    "\uf0a4": "\u25cb",  # ○
    "\uf0a7": "\u25a0",  # ■
    "\uf0ab": "\u2605",  # ★
    "\uf0fc": "\u25cf",  # ●
    "\uf0fe": "\u25a1",  # □
}

#: The label of a bullet paragraph whose bullet is not defined.
_DEFAULT_BULLET = "\u25cf"


def _number_text(value: int, number_format: str) -> str:
    if value <= 0:
        return str(value)
    return _NUMBER_FORMATS.get(number_format, str)(value)


class _ListLabels:
    """Hancom's labels of numbered, outline and bullet paragraphs, counted in reading order.

    Each numbering keeps one counter per level. A paragraph at level L counts level L up
    (from the level's ``start``) and resets the deeper levels; levels skipped on the way
    down count at their start value. The label is the level's ``hh:paraHead`` text with
    ``^k`` replaced by level k's counter in level k's number format, and ``^N`` by the
    counters of levels 1 to L in digits, each followed by a dot (``1.2.``). A numbering
    that is not defined numbers every level that way. A bullet's label is its character,
    ``●`` when the bullet is not defined. A label that is one symbol-font character is
    written as the Unicode symbol Hancom's text save writes for it (U+F09F as ``●``).
    Outline paragraphs use the section's outline numbering (``outline``).
    """

    def __init__(self, header: ET.Element | None) -> None:
        self.outline: str | None = None
        self._numberings: dict[str, dict[int, tuple[str, str, int]]] = {}
        self._bullets: dict[str, str] = {}
        self._headings: dict[str, tuple[str, str, int]] = {}
        self._counters: dict[str, dict[int, int]] = {}
        if header is None:
            return
        for numbering in header.iter(f"{_HH}numbering"):
            heads = self._numberings.setdefault(numbering.get("id") or "", {})
            for head in numbering.iter(f"{_HH}paraHead"):
                level = _int_attribute(head, "level") or 1
                heads[level] = (head.text or "", head.get("numFormat") or "DIGIT", _int_attribute(head, "start") or 1)
        for bullet in header.iter(f"{_HH}bullet"):
            self._bullets[bullet.get("id") or ""] = bullet.get("char") or ""
        for para_pr in header.iter(f"{_HH}paraPr"):
            heading = para_pr.find(f"{_HH}heading")
            kind = heading.get("type", "NONE") if heading is not None else "NONE"
            if heading is not None and kind != "NONE":
                self._headings[para_pr.get("id") or ""] = (kind, heading.get("idRef") or "", _int_attribute(heading, "level") or 0)

    def label(self, p: ET.Element) -> str:
        heading = self._headings.get(p.get("paraPrIDRef") or "")
        if heading is None:
            return ""
        kind, ref, level = heading[0], heading[1], heading[2] + 1
        if kind == "BULLET":
            text = self._bullets.get(ref, _DEFAULT_BULLET)
        else:
            text = self._number_label((self.outline or "") if kind == "OUTLINE" else ref, level)
        return _BULLET_SYMBOLS.get(text, text)

    def _number_label(self, numbering: str, level: int) -> str:
        heads = self._numberings.get(numbering)
        if heads is None and numbering:
            heads = {k: ("^N", "DIGIT", 1) for k in range(1, max(level, 10) + 1)}
        if not heads or level not in heads:
            return ""
        counters = self._counters.setdefault(numbering, {})
        for upper in range(1, level):
            if upper not in counters and upper in heads:
                counters[upper] = heads[upper][2]
        counters[level] = counters[level] + 1 if level in counters else heads[level][2]
        for deeper in [k for k in counters if k > level]:
            del counters[deeper]

        def fill(match: re.Match[str]) -> str:
            if match.group(1) == "N":
                return "".join(f"{counters.get(k, 1)}." for k in range(1, level + 1))
            k = int(match.group(1))
            _, number_format, start = heads.get(k, ("", "DIGIT", 1))
            return _number_text(counters.get(k, start), number_format)

        return re.sub(r"\^(\d+|N)", fill, heads[level][0])

    def start_section(self, section: ET.Element) -> None:
        sec_pr = next(section.iter(f"{_HP}secPr"), None)
        self.outline = sec_pr.get("outlineShapeIDRef") if sec_pr is not None else None


def _labelled(text: str, label: str) -> str:
    if not label:
        return text
    return label + (" " if text and not text[0].isspace() else "") + text


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


def _paragraph_text(p: ET.Element, *, tab_token: str = "\t", labels: _ListLabels | None = None) -> str:
    """Extract paragraph text from direct runs, preserving tab semantics.

    With *labels*, a numbered, outline or bullet paragraph starts with its label.
    """
    if labels is not None:
        return _labelled(_paragraph_text(p, tab_token=tab_token), labels.label(p))
    return "".join(piece for piece in _paragraph_pieces(p, tab_token=tab_token) if isinstance(piece, str))


def _run_child_text(child: ET.Element, tab_token: str) -> str | None:
    """The text a run child adds, or ``None`` when it is a control or an object."""
    if child.tag == f"{_HP}t":
        return _text_element_content(child, tab=tab_token)
    if child.tag == f"{_HP}tab" or _is_tab_control(child):
        return tab_token
    if child.tag == f"{_HP}lineBreak":
        return "\n"
    if child.tag == f"{_HP}dutmal":
        return _dutmal_text(child)
    return None


def _paragraph_pieces(p: ET.Element, *, tab_token: str = "\t") -> "list[str | ET.Element]":
    """The text of paragraph *p* and the tables, text boxes and captions placed in it, in order."""
    pieces: list[str | ET.Element] = []
    for run in p.findall(f"{_HP}run"):
        for child in run:
            text = _run_child_text(child, tab_token)
            if text is None:
                pieces.extend(_blocks_in(child))
            elif text:
                pieces.append(text)
    return pieces


def _emit_paragraph(
    p: ET.Element,
    *,
    tab_token: str,
    labels: _ListLabels | None,
    masking_policy: "TextSanitizer | None",
    write_text: Callable[[str], None],
    write_block: Callable[[ET.Element], None],
) -> None:
    """Write paragraph *p*, its text split where a table, text box or caption sits.

    Hancom's text save writes a placed object where its control sits in the paragraph;
    a numbered paragraph's label goes with the first piece of text.
    """
    label = labels.label(p) if labels is not None else ""
    buffer: list[str] = []
    for piece in [*_paragraph_pieces(p, tab_token=tab_token), None]:
        if isinstance(piece, str):
            buffer.append(piece)
            continue
        text = _mask_text(_labelled("".join(buffer), label), masking_policy)
        if text:
            write_text(text)
        label = ""
        buffer.clear()
        if piece is not None:
            write_block(piece)


def _dutmal_text(dutmal: ET.Element) -> str:
    """덧말 as Hancom's text save writes it: the main text, then ``(덧말:<sub text>)``."""
    main = dutmal.findtext(f"{_HP}mainText") or ""
    sub = dutmal.findtext(f"{_HP}subText") or ""
    return f"{main}(덧말:{sub})" if sub else main


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
    labels: _ListLabels | None = None,
) -> list[list[str]]:
    """Return a row-major 2D list of cell texts from a table element."""
    rows: list[list[str]] = []
    for tr in tbl.findall(f"{_HP}tr"):
        row: list[str] = []
        for tc in tr.findall(f"{_HP}tc"):
            row.append(_cell_text(tc, tab_token=tab_token, masking_policy=masking_policy, labels=labels))
        rows.append(row)
    return rows


def _cell_text(
    tc: ET.Element,
    *,
    tab_token: str = "\t",
    masking_policy: "TextSanitizer | None" = None,
    labels: _ListLabels | None = None,
) -> str:
    """The text of cell *tc*, a line per paragraph.

    Tables, text boxes and captions in the cell come where they sit, as in the body: a
    nested table's cells in order, then its caption.
    """
    lines: list[str] = []
    for paragraph in tc.findall(f"{_HP}subList/{_HP}p"):
        _emit_nested_paragraph(paragraph, lines, tab_token=tab_token, labels=labels)
    return _mask_text("\n".join(lines).strip(), masking_policy)


def _emit_nested_paragraph(
    p: ET.Element, lines: list[str], *, tab_token: str, labels: _ListLabels | None
) -> None:
    """Add paragraph *p* of a cell, text box or caption to *lines*, its objects where they sit."""

    def write_block(block: ET.Element) -> None:
        if block.tag in _PARAGRAPH_BLOCKS:
            for inner in _text_box_paragraphs(block):
                _emit_nested_paragraph(inner, lines, tab_token=tab_token, labels=labels)
            return
        for tc in block.findall(f"{_HP}tr/{_HP}tc"):
            text = _cell_text(tc, tab_token=tab_token, labels=labels)
            if text:
                lines.append(text)

    _emit_paragraph(p, tab_token=tab_token, labels=labels, masking_policy=None,
                    write_text=lines.append, write_block=write_block)


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
    labels: _ListLabels | None = None,
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
            placed[(row_addr, col_addr)] = _cell_text(tc, tab_token=tab_token, masking_policy=masking_policy, labels=labels)
            span = _int_attribute(tc.find(f"{_HP}cellSpan"), "colSpan")
            column = col_addr + max(span or 1, 1)
            width = max(width, column)
    if not placed:
        return []
    height = max(row for row, _ in placed) + 1
    return [[placed.get((row, col), "") for col in range(width)] for row in range(height)]


def _blocks_in(element: ET.Element) -> list[ET.Element]:
    """Tables, text boxes and captions in *element* (a run child), in document order, outermost only.

    A text box is returned as its ``hp:drawText``. A table's caption follows the
    table, where Hancom's text save puts it; the caption of a picture or a shape
    comes where it sits. A table or text box nested in a cell is already part of
    that cell's text, and one in a header, footer, note or memo is not body text.
    """
    if element.tag in _NOT_BODY_TAGS:
        return []
    if element.tag == f"{_HP}tbl":
        return [element, *element.findall(f"{_HP}caption")]
    if element.tag in _PARAGRAPH_BLOCKS:
        return [element]
    return [block for child in element for block in _blocks_in(child)]


def _text_box_paragraphs(block: ET.Element) -> list[ET.Element]:
    """The paragraphs of a text box (``hp:drawText``) or a caption."""
    return block.findall(f"{_HP}subList/{_HP}p")


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
    list_labels: bool = False,
) -> str:
    """Export document content as plain text.

    A paragraph's tables, text boxes and captions come where they sit in its text, as in
    Hancom's text save (a table's caption after the table). A 덧말 is its main text and
    ``(덧말:<sub text>)``.
    With *list_labels*, numbered, outline and bullet paragraphs start with the label
    Hancom draws for them (``1.``, ``가.``, ``●`` ...) and a space.
    """
    sections = _section_xmls(source)
    labels = _ListLabels(_header_xml(source)) if list_labels else None
    section_texts: list[str] = []
    for section_root in sections:
        para_texts: list[str] = []
        if labels is not None:
            labels.start_section(section_root)

        def write_block(block: ET.Element) -> None:
            if block.tag in _PARAGRAPH_BLOCKS:
                for inner in _text_box_paragraphs(block):
                    emit(inner)
            elif include_tables:
                rows = _table_cells_text(block, tab_token=tab_token, masking_policy=masking_policy, labels=labels)
                for row in rows:
                    para_texts.append(tab_token.join(row))

        def emit(p: ET.Element) -> None:
            _emit_paragraph(p, tab_token=tab_token, labels=labels, masking_policy=masking_policy,
                            write_text=para_texts.append, write_block=write_block)

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
    list_labels: bool = False,
) -> str:
    """Export document content as HTML.

    A paragraph's tables, text boxes and captions come where they sit in its text, as in
    Hancom's text save (a table's caption after the table). A 덧말 is its main text and
    ``(덧말:<sub text>)``.
    With *list_labels*, numbered, outline and bullet paragraphs start with their label.
    """
    sections = _section_xmls(source)
    labels = _ListLabels(_header_xml(source)) if list_labels else None
    body_parts: list[str] = []

    def write_block(block: ET.Element) -> None:
        if block.tag in _PARAGRAPH_BLOCKS:
            for inner in _text_box_paragraphs(block):
                emit(inner)
            return
        rows = (
            _table_cells_text(block, tab_token=tab_token, masking_policy=masking_policy, labels=labels)
            if include_tables
            else []
        )
        if rows:
            body_parts.append('<table border="1">')
            for row in rows:
                body_parts.append("  <tr>")
                for cell in row:
                    body_parts.append(f"    <td>{_escape_html(cell)}</td>")
                body_parts.append("  </tr>")
            body_parts.append("</table>")

    def emit(p: ET.Element) -> None:
        _emit_paragraph(p, tab_token=tab_token, labels=labels, masking_policy=masking_policy,
                        write_text=lambda text: body_parts.append(f"<p>{_escape_html(text)}</p>"),
                        write_block=write_block)

    for sec_idx, section_root in enumerate(sections):
        if sec_idx > 0:
            body_parts.append("<hr />")
        if labels is not None:
            labels.start_section(section_root)
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
    list_labels: bool = False,
) -> str:
    """Export document content as Markdown.

    A paragraph's tables, text boxes and captions come where they sit in its text, as in
    Hancom's text save (a table's caption after the table). A 덧말 is its main text and
    ``(덧말:<sub text>)``.
    With *list_labels*, numbered, outline and bullet paragraphs start with their label.
    """
    sections = _section_xmls(source)
    labels = _ListLabels(_header_xml(source)) if list_labels else None
    section_parts: list[str] = []
    for section_root in sections:
        lines: list[str] = []
        if labels is not None:
            labels.start_section(section_root)

        def write_text(text: str) -> None:
            lines.append(text)
            lines.append("")

        def write_block(block: ET.Element) -> None:
            if block.tag in _PARAGRAPH_BLOCKS:
                for inner in _text_box_paragraphs(block):
                    emit(inner)
                return
            rows = (
                _table_grid_text(block, tab_token=tab_token, masking_policy=masking_policy, labels=labels)
                if include_tables
                else []
            )
            if rows:
                header = rows[0]
                lines.append("| " + " | ".join(_markdown_cell(cell) for cell in header) + " |")
                lines.append("| " + " | ".join("---" for _ in header) + " |")
                for row in rows[1:]:
                    lines.append("| " + " | ".join(_markdown_cell(cell) for cell in row) + " |")
                lines.append("")

        def emit(p: ET.Element) -> None:
            _emit_paragraph(p, tab_token=tab_token, labels=labels, masking_policy=masking_policy,
                            write_text=write_text, write_block=write_block)

        for p in _iter_paragraphs(section_root):
            emit(p)
        section_parts.append("\n".join(lines).rstrip())
    return section_separator.join(section_parts)
