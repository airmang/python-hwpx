# SPDX-License-Identifier: Apache-2.0
"""Text blocks with stable ids — read a short list, write changes back by id.

A *text block* is one paragraph of the body or of a table cell (nested tables
included), in document order. Its id is positional::

    s0p16                 section 0, body paragraph 16
    s0p16t0r3c0q0         … its table 0, the cell at row 3 / column 0, cell paragraph 0
    s0p16t0r3c0q0t0r1c1q0 … a table nested in that cell paragraph

``r``/``c`` are the cell's own address (``hp:cellAddr``), so a merged cell
appears once, at its anchor. Ids survive save and reopen; they change only
when paragraphs, tables or cells are inserted or removed before them.

This is the engine side of the "the model reads a short list and writes
changes, code assembles the document" workflow: :func:`outline` makes the
budgeted list, :func:`apply_text_changes` puts the answers back.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Iterator, Mapping

if TYPE_CHECKING:
    from ..document import HwpxDocument
    from ..oxml import HwpxOxmlParagraph, HwpxOxmlTableCell

__all__ = [
    "TextBlock",
    "TextChangeReport",
    "TextOutline",
    "apply_text_changes",
    "iter_text_blocks",
    "outline",
]

_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class TextBlock:
    """One body or table-cell paragraph with its stable id."""

    id: str
    #: Human-readable position, e.g. ``"본문 17문단"`` or ``"표2 4행 1열"``.
    location: str
    paragraph: "HwpxOxmlParagraph"
    #: The table cell holding the paragraph, ``None`` for a body paragraph.
    cell: "HwpxOxmlTableCell | None" = None

    @property
    def text(self) -> str:
        return self.paragraph.text

    @property
    def in_table(self) -> bool:
        return self.cell is not None


def _cells_in_order(table: Any) -> list[tuple[int, int, Any]]:
    """Each physical cell once (a merged cell at its anchor), row by row, with its address.

    The address is the cell's ``hp:cellAddr``. A table where a cell has none, or
    two cells share one, is addressed by physical position instead (row element,
    cell element within it) so its ids stay unique.
    """

    cells = [(row_index, cell_index, cell) for row_index, row in enumerate(table.rows) for cell_index, cell in enumerate(row.cells)]
    addresses = [cell.address if cell._addr_element() is not None else None for _r, _c, cell in cells]
    if None in addresses or len(set(addresses)) != len(addresses):
        return cells
    return [(row, col, cell) for (row, col), (_r, _c, cell) in zip(addresses, cells)]  # type: ignore[misc]


def _walk_cell_tables(
    paragraph: "HwpxOxmlParagraph",
    prefix: str,
    where: str,
    table_numbers: list[int] | None,
) -> Iterator[TextBlock]:
    for table_index, table in enumerate(paragraph.tables):
        if table_numbers is not None:
            table_numbers[0] += 1
            label = f"표{table_numbers[0]}"
        else:
            label = f"{where} 안 표{table_index + 1}"
        for row, col, cell in _cells_in_order(table):
            cell_prefix = f"{prefix}t{table_index}r{row}c{col}"
            cell_where = f"{label} {row + 1}행 {col + 1}열"
            for cell_paragraph_index, cell_paragraph in enumerate(cell.paragraphs):
                block_id = f"{cell_prefix}q{cell_paragraph_index}"
                yield TextBlock(block_id, cell_where, cell_paragraph, cell)
                yield from _walk_cell_tables(cell_paragraph, block_id, cell_where, None)


def iter_text_blocks(document: "HwpxDocument") -> Iterator[TextBlock]:
    """Yield every body paragraph and table-cell paragraph in document order.

    Top-level tables are numbered in document order across sections (``표1``,
    ``표2``…); a nested table is named inside its cell (``표2 1행 1열 안 표1``).
    Headers, footers, notes, memos and text boxes are not included.
    """

    sections = document.sections
    table_numbers = [0]
    for section_index, section in enumerate(sections):
        section_label = f"{section_index + 1}구역 " if len(sections) > 1 else ""
        for paragraph_index, paragraph in enumerate(section.paragraphs):
            block_id = f"s{section_index}p{paragraph_index}"
            yield TextBlock(block_id, f"{section_label}본문 {paragraph_index + 1}문단", paragraph)
            yield from _walk_cell_tables(paragraph, block_id, "", table_numbers)


# --------------------------------------------------------------------------- #
# outline: the budgeted short list
# --------------------------------------------------------------------------- #
class TextOutline(list):  # type: ignore[type-arg]
    """``list[dict]`` of ``{"id", "where", "text"}`` items, plus paging facts.

    It is a plain list for JSON (``json.dumps`` writes the items only); the
    attributes say whether the budget cut it short and where to resume.
    """

    #: ``True`` when every non-empty block fit in the budget.
    complete: bool
    #: Pass as ``after=`` to read the next page; ``None`` when complete.
    next_after: str | None
    #: Non-empty blocks after the ``after`` cursor, listed or not.
    total: int

    def __init__(self, items: list[dict[str, Any]], *, complete: bool, next_after: str | None, total: int):
        super().__init__(items)
        self.complete = complete
        self.next_after = next_after
        self.total = total

    def to_text(self) -> str:
        """One line per item — ``[id] where: text`` — the cheapest prompt form."""

        lines = [f"[{item['id']}] {item['where']}: {item['text']}" for item in self]
        if not self.complete:
            lines.append(f"… {self.total - len(self)} more (after={self.next_after})")
        return "\n".join(lines)


def _clean(text: str) -> str:
    """Tabs and line breaks become spaces; other control characters go."""

    text = "".join(" " if ch in "\t\n\r" else ch for ch in text if ch in "\t\n\r" or unicodedata.category(ch) != "Cc")
    return _WHITESPACE_RE.sub(" ", text).strip()


def outline(
    document: "HwpxDocument",
    *,
    max_chars: int = 8000,
    max_items: int | None = None,
    max_block_chars: int = 200,
    after: str | None = None,
) -> TextOutline:
    """The non-empty text blocks as a short list that fits *max_chars*.

    Empty paragraphs are left out, tabs and line breaks become spaces and
    control characters are dropped, and a block longer than *max_block_chars*
    keeps its start and ends with ``…`` (its item gets ``"truncated": True``).
    *max_chars* counts each item's id, location and text. When the budget or
    *max_items* runs out the outline stops at a whole item: ``complete`` is
    ``False`` and ``next_after`` is the last id listed, to pass as *after* for
    the next page. A page always holds at least one item, even one larger than
    *max_chars*.
    """

    from ..errors import HwpxLookupError, HwpxValueError

    for name, value in (("max_chars", max_chars), ("max_block_chars", max_block_chars), ("max_items", max_items)):
        if value is not None and value < 1:
            raise HwpxValueError(
                f"{name} must be >= 1",
                code="text-outline-budget",
                context={name: value},
                suggestion="Pass a positive budget, or leave max_items unset for no item cap.",
            )

    items: list[dict[str, Any]] = []
    used = 0
    total = 0
    full = False
    seen_cursor = after is None
    for block in iter_text_blocks(document):
        if not seen_cursor:
            seen_cursor = block.id == after
            continue
        text = _clean(block.text)
        if not text:
            continue
        total += 1
        if full:
            continue
        item: dict[str, Any] = {"id": block.id, "where": block.location, "text": text}
        if len(text) > max_block_chars:
            item["text"] = text[: max_block_chars - 1].rstrip() + "…"
            item["truncated"] = True
        cost = len(block.id) + len(block.location) + len(item["text"])
        # A page always holds one item, so paging moves on even when a single
        # item is larger than the whole budget.
        if items and (used + cost > max_chars or (max_items is not None and len(items) >= max_items)):
            full = True
            continue
        used += cost
        items.append(item)
    if after is not None and not seen_cursor:
        raise HwpxLookupError(
            f"unknown text block id: {after!r}",
            code="text-block-unknown",
            context={"after": after},
            suggestion="Pass the next_after of the previous page, or an id from doc.text.blocks().",
        )
    complete = len(items) == total
    return TextOutline(
        items,
        complete=complete,
        next_after=None if complete or not items else items[-1]["id"],
        total=total,
    )


# --------------------------------------------------------------------------- #
# apply_text_changes: write answers back by id
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class TextChangeReport:
    """What :func:`apply_text_changes` did with each id."""

    changed: list[str] = field(default_factory=list)
    #: Ids the document does not have (nothing was written for them).
    unknown_ids: list[str] = field(default_factory=list)
    #: Ids whose text was already the requested text.
    unchanged: list[str] = field(default_factory=list)
    #: Changed ids whose runs could not all be kept: the edit crossed runs of
    #: different formatting, or added a tab or line break. The new text took the
    #: paragraph's first run's formatting.
    rewritten: list[str] = field(default_factory=list)
    #: Cells whose new text is estimated to need more lines than the cell holds,
    #: so the row would grow: ``{"id", "where", "lines", "lineBudget",
    #: "linesBefore", "confidence"}``. An estimate from the form-fit measurer,
    #: not a render.
    overflow: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """``True`` when every id was known and no cell is estimated to overflow."""

        return not self.unknown_ids and not self.overflow

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "changed": list(self.changed),
            "unknownIds": list(self.unknown_ids),
            "unchanged": list(self.unchanged),
            "rewritten": list(self.rewritten),
            "overflow": [dict(entry) for entry in self.overflow],
            "warnings": list(self.warnings),
        }


def _write(paragraph: "HwpxOxmlParagraph", value: str) -> bool:
    """Write *value*; return ``True`` when the runs had to be rewritten."""

    from ..errors import HwpxValueError

    if "\t" not in value and "\n" not in value:
        try:
            paragraph.set_text_preserving_runs(value)
            return False
        except HwpxValueError:
            pass
    paragraph.text = value
    return True


def _cell_lines(cell: Any, texts: list[str]) -> tuple[int, int | None, str]:
    """Estimated lines of *texts* (one per cell paragraph) and the cell's budget."""

    from ..form_fit.measure import measure, resolve_slot_metrics

    # The same document handle set_cell_text(fit=...) measures with.
    document = getattr(getattr(cell.table.paragraph, "section", None), "document", None)
    slot = resolve_slot_metrics(cell, document, max_lines=1)
    wide = replace(slot, max_lines=100_000)
    lines = 0
    confidence = "high"
    for text in texts:
        for line in text.split("\n"):
            if not line:
                lines += 1
                continue
            measured = measure(line, wide)
            lines += max(1, measured.lines)
            if measured.confidence != "high":
                confidence = "low"
    return lines, slot.height_lines(), confidence


def apply_text_changes(
    document: "HwpxDocument",
    changes: Mapping[str, str],
    *,
    check_overflow: bool = True,
) -> TextChangeReport:
    """Replace the text of each block id in *changes* and report per id.

    Every id is resolved before anything is written, so an unknown id never
    leaves a half-applied batch behind it: unknown ids are reported and the
    rest is applied. A change that stays inside one run keeps every run and
    control (:meth:`~hwpx.oxml.HwpxOxmlParagraph.set_text_preserving_runs`);
    one that crosses differently formatted runs or adds a tab or line break
    is written into the first run (``rewritten``). With *check_overflow*,
    each changed cell is measured before and after: a cell estimated to need
    more lines than it holds, and more than it needed before, is listed in
    ``overflow``.
    """

    report = TextChangeReport()
    wanted = {str(key): "" if value is None else str(value) for key, value in changes.items()}
    blocks: dict[str, TextBlock] = {}
    pending = set(wanted)
    if pending:
        for block in iter_text_blocks(document):
            if block.id in pending:
                blocks[block.id] = block
                pending.discard(block.id)
                if not pending:
                    break
    report.unknown_ids = [key for key in wanted if key not in blocks]

    # Measure the touched cells before writing.
    before: dict[int, tuple[Any, str, int, int | None]] = {}
    if check_overflow:
        for key, block in blocks.items():
            cell = block.cell
            if cell is None or id(cell.element) in before or wanted[key] == block.text:
                continue
            try:
                lines, budget, _confidence = _cell_lines(cell, [p.text for p in cell.paragraphs])
            except Exception as error:  # measuring must never block the edit
                report.warnings.append(f"{key}: overflow not measured ({type(error).__name__})")
                continue
            # The room is the cell as authored: an auto-growing row measured after
            # the write would count the new text into its own budget.
            before[id(cell.element)] = (cell, key, lines, budget)

    for key in wanted:
        block = blocks.get(key)
        if block is None:
            continue
        if block.text == wanted[key]:
            report.unchanged.append(key)
            continue
        if _write(block.paragraph, wanted[key]):
            report.rewritten.append(key)
        report.changed.append(key)

    for cell, key, lines_before, budget in before.values():
        try:
            lines, _budget_after, confidence = _cell_lines(cell, [p.text for p in cell.paragraphs])
        except Exception as error:  # pragma: no cover - measured once already
            report.warnings.append(f"{key}: overflow not measured ({type(error).__name__})")
            continue
        if budget is not None and lines > budget and lines > lines_before:
            report.overflow.append(
                {
                    "id": key,
                    "where": blocks[key].location,
                    "lines": lines,
                    "lineBudget": budget,
                    "linesBefore": lines_before,
                    "confidence": confidence,
                }
            )
    return report
