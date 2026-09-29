# SPDX-License-Identifier: Apache-2.0
"""Page estimate (experimental): the pages and line positions Hancom lays a document out on.

:func:`estimate_pages` follows every body paragraph onto its page and column, without Hancom:

* Lines: a paragraph keeps the lines of its own layout cache (``hp:linesegarray``) when the save
  path would keep that cache -- those are the lines Hancom drew. Other paragraphs break like
  FormFit (:func:`hwpx.form_fit.measure.hancom_line_starts`) at the column width less the
  paragraph's margins and first-line indent.
* Height: a line advances by the paragraph's line spacing (percent, fixed, between lines, at
  least), paragraphs add their spacing before and after, and a line stays on the page while its
  bottom is within the body height. Page and column breaks, page break before, keep lines
  together, keep with next and widow/orphan control; columns of equal width.
* Objects: a table or picture set as a character is one line as tall as it; a top-and-bottom
  object anchored to an empty paragraph pushes the next line below it; a table flowing with the
  text is laid out row by row -- split between cell lines, moved row by row or moved whole --
  with its header rows repeated. Footnotes take room at the foot of the page and go on over the
  page end.

Anything else makes the estimate unsupported: endnotes, a column change inside a section, section
settings after a section's first paragraph (Hancom starts a new section there), a line or
character grid, an object with text or other objects in its paragraph, mixed character sizes in a
paragraph, merged or nested cells in a table the estimate measures, objects placed on the page or
the paper, composed characters and ruby text. ``pages`` is then ``None`` and ``unsupported`` says
why, per section.
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..form_fit.measure import hancom_line_starts, text_style_from_refs
from ..oxml._document_primitives import _remove_stale_paragraph_layout_cache
from ..oxml.namespaces import HH, HP
from ..oxml.section import _remove_short_paragraph_layout_cache
from ..oxml.section_format import _drawn_page_size
from ..oxml.table_sizes import cell_margins_of

if TYPE_CHECKING:
    from ..document import HwpxDocument

__all__ = ["EstimatedLine", "PageEstimate", "estimate_pages"]

#: Objects in a run, placed by their ``hp:pos``.
_OBJECTS = frozenset({
    "tbl", "pic", "rect", "ellipse", "line", "arc", "polygon", "curve", "connectLine", "textart",
    "container", "ole", "equation", "video", "chart", "checkBtn", "radioBtn", "btn", "button",
    "comboBox", "edit", "listBox", "scrollBar",
})
#: Run content that changes a line's height in ways the estimate does not follow.
_UNSUPPORTED_CONTENT = frozenset({"compose", "dutmal"})
#: The narrowest line FormFit breaks at, in HWPUNIT.
_MIN_LINE_WIDTH = 1440


@dataclass(frozen=True)
class EstimatedLine:
    """Where one line of a body paragraph goes."""

    #: 0-based page of the document.
    page: int
    #: 0-based column on that page.
    column: int
    #: Distance of the line's top from the top of the column, in HWPUNIT (as ``hp:lineseg@vertpos``).
    vertpos: int


@dataclass(frozen=True)
class PageEstimate:
    """The estimated layout of a document, from :func:`estimate_pages`."""

    #: Number of pages, or ``None`` when the estimate does not support the document.
    pages: int | None
    #: The lines of each body paragraph (``hs:sec/hp:p``), sections in order. A paragraph anchoring a
    #: table that flows with the text has one line, under the table's top. Empty when unsupported.
    lines: tuple[tuple[EstimatedLine, ...], ...]
    #: Why the estimate does not support the document, one reason per section it stopped at.
    unsupported: tuple[str, ...]


class _Unsupported(Exception):
    """Something the estimate does not follow."""


def estimate_pages(document: "HwpxDocument | bytes | str | os.PathLike[str]") -> PageEstimate:
    """Estimate the pages Hancom lays *document* out on, and where each body line goes.

    *document* is an :class:`~hwpx.document.HwpxDocument` (estimated as it is in memory) or the
    bytes or path of an HWPX file. See the module description for what the estimate follows.
    """

    root = getattr(_open(document), "_root")
    measure = _Measure(root)
    layouts: list[_SectionLayout] = []
    reasons: list[str] = []
    for number, section in enumerate(root.sections):
        try:
            layouts.append(_lay_section(measure, section.element))
        except _Unsupported as exc:
            reasons.append(f"section {number}: {exc}")
    if reasons:
        return PageEstimate(None, (), tuple(reasons))
    return _assemble(layouts)


def _open(document: Any) -> Any:
    from ..document import HwpxDocument

    if isinstance(document, HwpxDocument):
        return document
    if isinstance(document, (bytes, bytearray)):
        return HwpxDocument.open(bytes(document))
    return HwpxDocument.open(os.fspath(document))


# -- the paragraph model ------------------------------------------------------------------------


def _local(element: Any) -> str:
    tag = element.tag
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _child(element: Any, name: str) -> Any:
    return next((child for child in element if _local(child) == name), None)


@dataclass(frozen=True)
class _Shape:
    """What the estimate reads from a paragraph shape (``hh:paraPr``)."""

    kind: str
    value: int
    prev: int
    next: int
    left: int
    right: int
    indent: int
    flags: dict[str, str]


def _para_shape(header: Any, para_pr_id: str) -> _Shape:
    shape = next((el for el in header.iter(f"{HH}paraPr") if el.get("id") == para_pr_id), None)
    if shape is None:
        raise _Unsupported(f"paragraph shape {para_pr_id} is missing")
    # The hp:case holding margin and lineSpacing: outline levels 8-10 put hh:heading in an earlier switch.
    case = next((c for c in shape.iter(f"{HP}case") if _child(c, "lineSpacing") is not None), None)
    holder = case if case is not None else shape
    spacing = _child(holder, "lineSpacing")
    margin = _child(holder, "margin")

    def value(name: str) -> int:
        element = _child(margin, name) if margin is not None else None
        return int(element.get("value", 0)) if element is not None else 0

    breaks = shape.find(f"{HH}breakSetting")
    kind, amount = ("PERCENT", 160)
    if spacing is not None:
        kind, amount = spacing.get("type", "PERCENT"), int(spacing.get("value", 160))
    return _Shape(kind, amount, value("prev"), value("next"), value("left"), value("right"), value("intent"),
                  dict(breaks.attrib) if breaks is not None else {})


def _pitch(kind: str, value: int, size: int) -> int:
    """The distance from one line's top to the next line's top in a paragraph."""

    if kind == "FIXED":
        return value
    if kind == "BETWEEN_LINES":
        return size + value
    if kind == "AT_LEAST":
        return max(size, value)
    # PERCENT: the spacing over the size is counted in 1/1800 inch from the em (height // 4), rounded.
    extra = (size // 4) * (value - 100) / 100
    units = int(abs(extra) + 0.5)
    return size + 4 * (units if extra >= 0 else -units)


def _on(flags: dict[str, str], name: str) -> bool:
    return flags.get(name) in ("1", "true")


def _t_text(text_element: Any) -> str:
    """The text of one ``hp:t``, with ``hp:lineBreak`` as a newline and ``hp:tab`` as a tab."""

    parts = [text_element.text or ""]
    for child in text_element:
        name = _local(child)
        parts.append("\n" if name == "lineBreak" else "\t" if name == "tab" else "")
        parts.append(child.tail or "")
    return "".join(parts)


def _run_text(runs: list[Any]) -> str:
    return "".join(_t_text(t) for run in runs for t in run.findall(f"{HP}t"))


def _cache_lines(paragraph: Any) -> int:
    """How many lines the paragraph's own layout cache holds; 0 when it has none or the save path
    would drop it as not matching the text."""

    segments = paragraph.findall(f"{HP}linesegarray/{HP}lineseg")
    if not segments:
        return 0
    probe = copy.deepcopy(paragraph)
    if _remove_stale_paragraph_layout_cache(probe) or _remove_short_paragraph_layout_cache(probe):
        return 0
    return len(segments)


class _Measure:
    """Shapes and line breaking of one document."""

    def __init__(self, root: Any) -> None:
        self._root = root
        self._header = root.headers[0].element
        self._shapes: dict[str, _Shape] = {}

    def shape(self, para_pr_id: Any) -> _Shape:
        key = str(para_pr_id)
        if key not in self._shapes:
            self._shapes[key] = _para_shape(self._header, key)
        return self._shapes[key]

    def char_height(self, char_pr_id: Any) -> int:
        style = self._root.char_property(char_pr_id)
        return int(style.attributes.get("height", 1000)) if style is not None else 1000

    def style(self, para_pr_id: Any, char_pr_ids: list[Any]) -> Any:
        return text_style_from_refs(self._root, para_pr_id, char_pr_ids)

    def lines(self, text: str, widths: list[float], size: int, style: Any) -> int:
        """How many lines FormFit breaks *text* into (a newline starts a line)."""

        if not text:
            return 1
        return sum(len(hancom_line_starts(line, widths, size / 100, style)) if line else 1
                   for line in text.split("\n"))

    def line_starts(self, text: str, widths: list[float], size: int, style: Any) -> list[int]:
        """Where each line starts, as offsets into *text*."""

        starts: list[int] = []
        base = 0
        for line in text.split("\n"):
            starts += [base + start for start in (hancom_line_starts(line, widths, size / 100, style) if line else [0])]
            base += len(line) + 1
        return starts

    def stack(self, paragraphs: list[Any], width: int, caches: bool) -> tuple[int, int, int, int]:
        """(height, lines, pitch, size) of *paragraphs* laid out one under another at *width*; pitch
        and size are the last paragraph's. With *caches* a paragraph keeps the lines of its cache."""

        height, lines, pitch, size, pending = 0, 0, 0, 0, None
        for paragraph in paragraphs:
            runs = paragraph.findall(f"{HP}run")
            refs = [run.get("charPrIDRef") for run in runs] or ["0"]
            size = self.char_height(refs[0])
            shape = self.shape(paragraph.get("paraPrIDRef"))
            pitch = _pitch(shape.kind, shape.value, size)
            count = (_cache_lines(paragraph) if caches else 0) or self.lines(
                _run_text(runs), [max(width, _MIN_LINE_WIDTH)], size, self.style(paragraph.get("paraPrIDRef"), refs)
            )
            if pending is not None:
                height += pending + shape.prev
            height += (count - 1) * pitch + size
            pending = pitch - size + shape.next
            lines += count
        return height, lines, pitch, size


@dataclass(frozen=True)
class _Row:
    height: int   # the row's full height
    lines: int    # lines of its tallest cell, for splitting between them
    pitch: int
    size: int
    margins: int  # top + bottom cell margins
    header: bool


@dataclass(frozen=True)
class _FlowTable:
    rows: list[_Row]
    mode: str                  # hp:tbl@pageBreak: CELL, TABLE or NONE
    repeat_header: bool
    margins: tuple[int, int]   # hp:outMargin top, bottom: kept above and below the table


def _rows(measure: _Measure, table: Any) -> list[_Row]:
    """Each row as its tallest cell: the cell's declared height or its content with its margins."""

    rows = []
    for tr in table.findall(f"{HP}tr"):
        cells = [_cell_row(measure, table, tc) for tc in tr.findall(f"{HP}tc")]
        if cells:
            rows.append(max(cells, key=lambda row: row.height))
    return rows


def _cell_row(measure: _Measure, table: Any, cell: Any) -> _Row:
    span = cell.find(f"{HP}cellSpan")
    if span is not None and span.get("rowSpan", "1") != "1":
        raise _Unsupported("a table with merged rows")
    if cell.find(f".//{HP}tbl") is not None:
        raise _Unsupported("a nested table")
    size = cell.find(f"{HP}cellSz")
    margins = cell_margins_of(cell, table)
    inner = int(size.get("width", 0)) - margins.left - margins.right
    content, lines, pitch, char_size = measure.stack(cell.findall(f"{HP}subList/{HP}p"), inner, caches=True)
    vertical = margins.top + margins.bottom
    height = max(int(size.get("height", 0)), vertical + content)
    return _Row(height, lines, pitch, char_size, vertical, cell.get("header") == "1")


@dataclass(frozen=True)
class _Para:
    lines: int
    size: int
    pitch: int
    prev: int
    next: int
    break_before: bool
    keep_lines: bool
    keep_next: bool
    widow_orphan: bool
    page_break: bool = False     # hp:p@pageBreak
    column_break: bool = False   # hp:p@columnBreak
    table: _FlowTable | None = None
    #: line index -> (height of the notes anchored in it, how many, size of the first one's first line)
    notes: dict[int, tuple[int, int, int]] = field(default_factory=dict)


@dataclass(frozen=True)
class _Page:
    body: int
    column_width: int
    columns: int


def _page(section: Any) -> _Page:
    page = next(section.iter(f"{HP}pagePr"), None)
    margin = page.find(f"{HP}margin") if page is not None else None
    if margin is None:
        raise _Unsupported("no page settings")
    width, height = _drawn_page_size(int(page.get("width", 0)), int(page.get("height", 0)), page.get("landscape"))
    body = height - sum(int(margin.get(key, 0)) for key in ("top", "bottom", "header", "footer"))
    text_width = width - sum(int(margin.get(key, 0)) for key in ("left", "right", "gutter"))
    columns, column_width = _columns(section, text_width)
    return _Page(body, column_width, columns)


def _columns(section: Any, text_width: int) -> tuple[int, int]:
    settings = list(section.iter(f"{HP}colPr"))
    if len(settings) > 1:
        raise _Unsupported("the columns change inside the section")
    count = int(settings[0].get("colCount", "1")) if settings else 1
    if count <= 1:
        return 1, text_width
    if settings[0].get("sameSz") != "1":
        raise _Unsupported("columns of unequal width")
    gap = int(settings[0].get("sameGap", 0))
    return count, (text_width - (count - 1) * gap) // count // 4 * 4


@dataclass(frozen=True)
class _NoteShape:
    above: int = 0     # hp:noteSpacing@aboveLine
    line: int = 0      # the separator's width
    below: int = 0     # hp:noteSpacing@belowLine
    between: int = 0   # hp:noteSpacing@betweenNotes

    def area(self, height: int, count: int) -> int:
        return 0 if count == 0 else self.above + self.line + self.below + height + self.between * (count - 1)


def _note_shape(section: Any) -> _NoteShape:
    if next(section.iter(f"{HP}endNote"), None) is not None:
        raise _Unsupported("endnotes")
    settings = next(section.iter(f"{HP}footNotePr"), None)
    if settings is None:
        return _NoteShape()
    placement = settings.find(f"{HP}placement")
    if placement is not None and placement.get("beneathText") == "1":
        raise _Unsupported("footnotes beneath the text")
    spacing = settings.find(f"{HP}noteSpacing")
    rule = settings.find(f"{HP}noteLine")
    millimetres = float((rule.get("width", "0 mm") if rule is not None else "0 mm").split()[0])

    def value(name: str) -> int:
        return int(spacing.get(name, 0)) if spacing is not None else 0

    return _NoteShape(value("aboveLine"), round(millimetres * 7200 / 25.4), value("belowLine"), value("betweenNotes"))


def _check_section(section: Any) -> None:
    grid = next(section.iter(f"{HP}grid"), None)
    if grid is not None and (grid.get("lineGrid", "0") != "0" or grid.get("charGrid", "0") != "0"):
        raise _Unsupported("a line or character grid")
    # Hancom starts a new section, on a new page, at a later paragraph holding section settings.
    if any(next(paragraph.iter(f"{HP}secPr"), None) is not None for paragraph in section.findall(f"{HP}p")[1:]):
        raise _Unsupported("section settings (hp:secPr) after the first paragraph")


def _placed_objects(runs: list[Any]) -> list[Any]:
    contents = {_local(child) for run in runs for child in run}
    odd = sorted(contents & _UNSUPPORTED_CONTENT)
    if odd:
        raise _Unsupported(f"{odd[0]} in a paragraph")
    objects = [child for run in runs for child in run if _local(child) in _OBJECTS]
    for obj in objects:
        if obj.find(f"{HP}pos") is None or obj.find(f"{HP}sz") is None:
            raise _Unsupported(f"{_local(obj)} without a position")
    return objects


def _text_size(measure: _Measure, runs: list[Any], text: str) -> tuple[int, list[Any]]:
    refs = [run.get("charPrIDRef") for run in runs if run.find(f"{HP}t") is not None]
    refs = refs or [run.get("charPrIDRef") for run in runs] or ["0"]
    sizes = {measure.char_height(ref) for ref in refs}
    if text and len(sizes) > 1:
        raise _Unsupported("mixed character sizes in a paragraph")
    return min(sizes), refs


def _object_line(
    measure: _Measure, obj: Any, count: int, size: int, pitch: int
) -> tuple[int, int, int, _FlowTable | None]:
    """(lines, size, pitch, flowing table) of a paragraph holding *obj* and nothing else."""

    pos = obj.find(f"{HP}pos")
    out_margin = obj.find(f"{HP}outMargin")
    top, bottom = (0, 0)
    if out_margin is not None:
        top, bottom = int(out_margin.get("top", 0)), int(out_margin.get("bottom", 0))
    tall = int(obj.find(f"{HP}sz").get("height", 0)) + top + bottom
    name = _local(obj)
    if pos.get("treatAsChar") == "1":
        if name == "tbl":
            tall = sum(row.height for row in _rows(measure, obj)) + top + bottom
        return 1, tall, tall + pitch - size, None
    on_paragraph = pos.get("vertRelTo") == "PARA" and pos.get("vertAlign", "TOP") == "TOP"
    if obj.get("textWrap") == "TOP_AND_BOTTOM" and on_paragraph:
        if name == "tbl":
            rows = _rows(measure, obj)
            table = _FlowTable(rows, obj.get("pageBreak", "CELL"), obj.get("repeatHeader") == "1", (top, bottom))
            return count, size, pitch, table
        below = int(pos.get("vertOffset", 0)) + tall
        return 1, below, below, None
    raise _Unsupported(f"{name} placed {obj.get('textWrap')} relative to {pos.get('vertRelTo')}")


def _note_anchors(runs: list[Any]) -> list[tuple[int, Any]]:
    """(text offset, hp:footNote) of each footnote in the runs."""

    offset, anchors = 0, []
    for run in runs:
        for child in run:
            name = _local(child)
            if name == "t":
                offset += len(_t_text(child))
            elif name == "ctrl" and child.find(f"{HP}footNote") is not None:
                anchors.append((offset, child.find(f"{HP}footNote")))
    return anchors


def _anchored_notes(measure: _Measure, runs: list[Any], text: str, widths: list[float], size: int, style: Any,
                    width: int) -> dict[int, tuple[int, int, int]]:
    anchors = _note_anchors(runs)
    if not anchors:
        return {}
    starts = measure.line_starts(text, widths, size, style)
    anchored: dict[int, tuple[int, int, int]] = {}
    for offset, note in anchors:
        line = max(index for index, start in enumerate(starts) if start <= max(offset - 1, 0))
        paragraphs = note.findall(f"{HP}subList/{HP}p")
        tall = measure.stack(paragraphs, width, caches=False)[0]
        first_runs = paragraphs[0].findall(f"{HP}run") if paragraphs else []
        head = measure.char_height(first_runs[0].get("charPrIDRef") if first_runs else "0")
        height, many, first = anchored.get(line, (0, 0, 0))
        anchored[line] = (height + tall, many + 1, first or head)
    return anchored


def _paragraph(measure: _Measure, page: _Page, paragraph: Any) -> _Para:
    runs = paragraph.findall(f"{HP}run")
    objects = _placed_objects(runs)
    text = _run_text(runs)
    if objects and (len(objects) > 1 or text.strip()):
        raise _Unsupported("an object with text or other objects in its paragraph")
    size, refs = _text_size(measure, runs, text)
    shape = measure.shape(paragraph.get("paraPrIDRef"))
    style = measure.style(paragraph.get("paraPrIDRef"), refs)
    line = page.column_width - shape.left - shape.right
    widths: list[float] = [line - max(shape.indent, 0), line - max(-shape.indent, 0)]
    count = (0 if objects else _cache_lines(paragraph)) or measure.lines(text, widths, size, style)
    pitch = _pitch(shape.kind, shape.value, size)
    table = None
    if objects:
        count, size, pitch, table = _object_line(measure, objects[0], count, size, pitch)
    notes = _anchored_notes(measure, runs, text, widths, size, style, page.column_width)
    flags = shape.flags
    return _Para(count, size, pitch, shape.prev, shape.next, _on(flags, "pageBreakBefore"), _on(flags, "keepLines"),
                 _on(flags, "keepWithNext"), _on(flags, "widowOrphan"), paragraph.get("pageBreak") == "1",
                 paragraph.get("columnBreak") == "1", table, notes)


# -- laying the paragraphs out ---------------------------------------------------------------------


def _flow_table(table: _FlowTable, frame: int, y: int, body: int) -> tuple[int, int]:
    """Lay the rows out from vertical position *y*; the frame and position where the table ends."""

    header = sum(row.height for row in table.rows if row.header) if table.repeat_header else 0
    for row in table.rows:
        frame, y = _flow_row(table.mode, row, frame, y, body, header)
    return frame, y


def _flow_row(mode: str, row: _Row, frame: int, y: int, body: int, header: int) -> tuple[int, int]:
    """A row that does not fit even a fresh page is drawn there anyway, cut at the paper's edge;
    CELL breaks a row between its lines."""

    remaining, height = row.lines, row.height
    while True:
        if y + height <= body:
            return frame, y + height
        fresh = y == header
        if mode == "CELL":
            fitting = 0
            while fitting < remaining and y + row.margins + fitting * row.pitch + row.size <= body:
                fitting += 1
            if fitting:
                remaining -= fitting
                height = row.margins + (remaining - 1) * row.pitch + row.size
            elif fresh:
                return frame, y + height
        elif fresh:
            return frame, y + height
        frame, y = frame + 1, header


class _Paginator:
    """Frames (a page's columns, in order) and vertical positions of every line of a section."""

    def __init__(self, body: int, columns: int, notes: _NoteShape) -> None:
        self.body = body
        self.columns = columns
        self.notes = notes
        self.out: list[tuple[int, int]] = []
        self.frame = 0
        self.last_vp: int | None = None
        self.last_pitch = 0
        self.pending_next = 0
        self.extra_frames = 0   # frames a table that does not split takes past the text
        self.table_end = 0      # the last frame a flowing table reaches
        self.page_notes = [0, 0]  # height and count of the notes on the current page
        self.carry = 0          # height of notes going on over the page end

    def run(self, paras: list[_Para]) -> int:
        """Lay *paras* out; the number of frames used."""

        for index, para in enumerate(paras):
            self._paragraph(index, paras, para)
        return max(self.out[-1][0] if self.out else 0, self.extra_frames, self.table_end) + 1

    def _paragraph(self, index: int, paras: list[_Para], para: _Para) -> None:
        start = para.prev if self.last_vp is None else self.last_vp + self.last_pitch + self.pending_next + para.prev
        table = para.table
        if table is not None and table.mode == "NONE" and start + sum(row.height for row in table.rows) > self.body:
            self.extra_frames = max(self.extra_frames, self.frame + 1)  # the table moves whole to the next page
        if table is not None and table.mode != "NONE":
            self._flow(para, table, start)
            return
        start, broke = self._breaks(para, start)
        if self._lay(index, paras, para, start, broke):
            self.last_vp, self.last_pitch, self.pending_next = self.out[-1][1], para.pitch, para.next

    def _flow(self, para: _Para, table: _FlowTable, start: int) -> None:
        self.out.append((self.frame, start))  # the anchor paragraph's line, under the table's top
        before = self.frame
        self.frame, end = _flow_table(table, self.frame, start + table.margins[0], self.body)
        self.table_end = max(self.table_end, self.frame)
        if self.frame != before:
            self.page_notes = [0, 0]
        self.last_vp, self.last_pitch, self.pending_next = end + table.margins[1], 0, para.next

    def _breaks(self, para: _Para, start: int) -> tuple[int, bool]:
        if self.last_vp is None:
            return start, False
        if para.page_break or para.break_before:
            self.frame = (self.frame // self.columns + 1) * self.columns
        elif para.column_break:
            self.frame += 1
        else:
            return start, False
        self.page_notes = [0, 0]
        return para.prev, True

    def _lay(self, index: int, paras: list[_Para], para: _Para, start: int, broke: bool) -> bool:
        """Place the lines of *para*; False when its notes ended the page after it."""

        remaining, first_chunk = para.lines, True
        fresh = self.last_vp is None or broke
        while remaining:
            done = para.lines - remaining
            count = self._chunk(index, paras, para, start, remaining, done, first_chunk)
            if count == 0 and (self.last_vp is None or fresh):
                count = 1  # a line taller than the page still takes an empty page (and overflows it)
            self.out.extend((self.frame, start + j * para.pitch) for j in range(count))
            self._place(para, done, count)
            remaining -= count
            if not remaining and self.carry:  # the page ends with this paragraph's notes
                self.frame += 1
                self.page_notes = [self.carry, 1]
                self.last_vp, self.last_pitch, self.pending_next = None, 0, 0
                return False
            if remaining:
                start = self._next_frame(para, count, first_chunk)
            fresh = bool(remaining)
            first_chunk = False
        return True

    def _next_frame(self, para: _Para, count: int, first_chunk: bool) -> int:
        self.frame += 1
        self.page_notes = [self.carry, 1] if self.carry else [0, 0]
        return para.prev if count == 0 and first_chunk else 0

    def _chunk(self, index: int, paras: list[_Para], para: _Para, start: int, remaining: int, done: int,
               first_chunk: bool) -> int:
        """How many of the paragraph's remaining lines stay in this frame."""

        count = self._fits(start, remaining, para, done)
        if not first_chunk:
            return count
        if count < remaining:
            count = self._keep_rules(para, start, remaining, count)
        if count == remaining and para.keep_next and index + 1 < len(paras):
            count = self._keep_with_next(para, paras[index + 1], start, remaining, count)
        return count

    def _keep_rules(self, para: _Para, start: int, remaining: int, count: int) -> int:
        if para.keep_lines and self._fits(para.prev, para.lines, para) == para.lines and start != para.prev:
            return 0
        if para.widow_orphan:
            if count == 1 and remaining > 1:
                return 0
            if remaining - count == 1 and count > 1:
                return count - 1
        return count

    def _keep_with_next(self, para: _Para, following: _Para, start: int, remaining: int, count: int) -> int:
        after = start + (remaining - 1) * para.pitch + para.pitch + para.next + following.prev
        need = 2 if following.widow_orphan and following.lines > 1 else 1
        if self._fits(after, need, following) < need and start != para.prev:
            return 0
        return count

    def _fits(self, start: int, count: int, para: _Para, first: int = 0) -> int:
        """How many of *count* lines (from line *first*) from *start* stay in the frame, each above the
        note area including the notes anchored in it. A line whose notes fit only in part (at least
        their first line) still stays, and ends the frame."""

        fitting, height, many = 0, self.page_notes[0], self.page_notes[1]
        self.carry = 0
        while fitting < count:
            note_height, notes, head = para.notes.get(first + fitting, (0, 0, 0))
            bottom = start + fitting * para.pitch + para.size
            if bottom <= self.body - self.notes.area(height + note_height, many + notes):
                height, many, fitting = height + note_height, many + notes, fitting + 1
                continue
            if notes and bottom <= self.body - self.notes.area(height + head, many + notes):
                room = self.body - bottom - self.notes.area(height, many + notes) + note_height
                self.carry = max(note_height - room, 0)
                fitting += 1
            break
        return fitting

    def _place(self, para: _Para, first: int, count: int) -> None:
        for line in range(first, first + count):
            note_height, notes, _ = para.notes.get(line, (0, 0, 0))
            self.page_notes[0] += note_height
            self.page_notes[1] += notes


@dataclass(frozen=True)
class _SectionLayout:
    columns: int
    frames: int
    lines: list[tuple[int, int]]   # (frame, vertpos) of every line, in paragraph order
    counts: list[int]              # lines per paragraph


def _lay_section(measure: _Measure, section: Any) -> _SectionLayout:
    page = _page(section)
    notes = _note_shape(section)
    _check_section(section)
    paras = [_paragraph(measure, page, paragraph) for paragraph in section.findall(f"{HP}p")]
    paginator = _Paginator(page.body, page.columns, notes)
    frames = paginator.run(paras)
    return _SectionLayout(page.columns, frames, paginator.out, [para.lines for para in paras])


def _assemble(layouts: list[_SectionLayout]) -> PageEstimate:
    pages = 0
    lines: list[tuple[EstimatedLine, ...]] = []
    for layout in layouts:
        start = 0
        for count in layout.counts:
            lines.append(tuple(
                EstimatedLine(pages + frame // layout.columns, frame % layout.columns, vertpos)
                for frame, vertpos in layout.lines[start:start + count]
            ))
            start += count
        pages += (layout.frames - 1) // layout.columns + 1
    return PageEstimate(pages, tuple(lines), ())
