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
from typing import TYPE_CHECKING, Any, Iterable, Iterator, Mapping

if TYPE_CHECKING:
    from ..document import HwpxDocument
    from ..objects.results import ObjectPlace, ParagraphPlace
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

    from ..errors import HwpxLookupError, HwpxValueError, argument_type_error

    for name, value in (("max_chars", max_chars), ("max_block_chars", max_block_chars), ("max_items", max_items)):
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise argument_type_error(name, value, "an int", code="text-outline-budget")
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
            suggestion="Pass the next_after of the previous page, or an id from doc.text.iter_blocks().",
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

    if not isinstance(changes, Mapping):
        from ..errors import argument_type_error

        raise argument_type_error(
            "changes", changes, "a mapping of block id to new text",
            suggestion="Pass {block_id: new_text}, e.g. {'s0p0': '새 글'}.",
        )
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


# ---------------------------------------------------------------------------
# Whole-document walk: every paragraph and every object, with where it sits.

#: Where a paragraph can sit (``ParagraphPlace.where``), innermost container first.
PLACES = (
    "body", "cell", "text_box", "caption", "header", "footer", "footnote", "endnote", "memo", "master_page",
    "hidden_comment",
)
#: Object kinds ``doc.text.iter_objects()`` reports, by element name.
OBJECT_KINDS = {
    "tbl": "table",
    "pic": "picture",
    "equation": "equation",
    "ole": "ole",
    "chart": "chart",
    "video": "video",
    "textart": "textart",
    "line": "shape",
    "rect": "shape",
    "ellipse": "shape",
    "arc": "shape",
    "polygon": "shape",
    "curve": "shape",
    "connectLine": "shape",
    "container": "shape",
}
_SHAPE_TAGS = frozenset(name for name, kind in OBJECT_KINDS.items() if kind == "shape")
_NOTE_PLACES = {"footNote": "footnote", "endNote": "endnote"}


@dataclass(frozen=True)
class _Context:
    where: str
    section: int | None
    part: Any
    page_type: str | None = None
    table: Any = None  # the innermost table element holding the paragraph
    table_paragraph: Any = None  # the paragraph element holding that table
    row: int | None = None
    col: int | None = None
    owner: Any = None  # the innermost object element holding the paragraph
    owner_paragraph: Any = None
    depth: int = 0


def _local(element: Any) -> str:
    tag = element.tag if isinstance(element.tag, str) else ""
    return tag.rsplit("}", 1)[-1]


def _story_counts(section_element: Any) -> dict[tuple[str, str | None, str], int]:
    """How often each header/footer story stands under ``hp:secPr``, and (``("memo", id, "")``) the ids of
    the memos the section's ``hp:memogroup`` holds."""

    counts: dict[tuple[str, str | None, str], int] = {}
    for node in section_element.iter():
        name = _local(node)
        if name == "secPr":
            for story in node:
                if _local(story) in ("header", "footer"):
                    key = (_local(story), story.get("id"), story.get("applyPageType", "BOTH"))
                    counts[key] = counts.get(key, 0) + 1
        elif name == "memo" and node.get("id"):
            counts[("memo", node.get("id"), "")] = 1
    return counts


def _walk(
    node: Any, context: _Context, holder: Any, parent: str, counts: Mapping[Any, int]
) -> Iterator[tuple[str, Any, _Context, Any]]:
    """Yield ``("p", p, context, None)`` and ``("object", element, context, holding p)`` in document order."""

    for child in node:
        name = _local(child)
        if name == "p":
            yield "p", child, context, None
            yield from _walk(child, context, child, name, counts)
        elif name == "fieldBegin":
            # A MEMO field holds the memo's text in its hp:subList. python-hwpx also keeps the memo in
            # hp:memogroup (read there, below); a memo kept only in its field -- the form Hancom 2024
            # saves, and what it makes of python-hwpx's memo on saving -- is read here, as doc.notes.memos
            # reads it. Other fields' parameters hold no paragraphs.
            from ..oxml.memo import memo_field_id

            if child.get("type") == "MEMO" and counts.get(("memo", memo_field_id(child), "")) is None:
                for part in child:
                    if _local(part) == "subList":
                        yield from _walk(part, replace(context, where="memo"), None, name, counts)
            continue
        elif name in OBJECT_KINDS:
            yield "object", child, context, holder
            inner = replace(context, owner=child, owner_paragraph=holder, depth=context.depth + 1)
            if name == "tbl":
                for part in child:
                    part_name = _local(part)
                    if part_name == "tr":
                        for cell in part:
                            if _local(cell) != "tc":
                                continue
                            address = next((n for n in cell if _local(n) == "cellAddr"), None)
                            cell_context = replace(
                                inner,
                                where="cell",
                                table=child,
                                table_paragraph=holder,
                                row=_int_attr(address, "rowAddr"),
                                col=_int_attr(address, "colAddr"),
                            )
                            yield from _walk(cell, cell_context, holder, "tc", counts)
                    elif part_name == "caption":
                        # A table's caption is a child of hp:tbl like its rows: its paragraphs (and a
                        # table inside them) sit in the caption, not where the table itself sits.
                        yield from _walk(part, replace(inner, where="caption"), holder, part_name, counts)
                    else:
                        yield from _walk(part, inner, holder, part_name, counts)
            else:
                yield from _walk(child, inner, holder, name, counts)
        elif name == "caption":
            yield from _walk(child, replace(context, where="caption"), holder, name, counts)
        elif name == "drawText":
            yield from _walk(child, replace(context, where="text_box"), holder, name, counts)
        elif name in ("header", "footer"):
            key = (name, child.get("id"), child.get("applyPageType", "BOTH"))
            if parent == "ctrl" and counts.get(key) == 1:
                continue  # the control copy of a story python-hwpx 6.x also kept under hp:secPr
            story = replace(context, where=name, page_type=child.get("applyPageType", "BOTH"))
            yield from _walk(child, story, holder, name, counts)
        elif name in _NOTE_PLACES:
            yield from _walk(child, replace(context, where=_NOTE_PLACES[name]), holder, name, counts)
        elif name == "memogroup":
            yield from _walk(child, replace(context, where="memo"), None, name, counts)
        elif name == "hiddenComment":
            # 숨은 설명: text Hancom keeps with the paragraph but neither shows nor prints.
            yield from _walk(child, replace(context, where="hidden_comment"), holder, name, counts)
        else:
            yield from _walk(child, context, holder, name, counts)


def _int_attr(element: Any, name: str) -> int | None:
    if element is None:
        return None
    try:
        return int(element.get(name))
    except (TypeError, ValueError):
        return None


def _parts(doc: "HwpxDocument") -> Iterator[tuple[Any, _Context]]:
    for index, section in enumerate(doc.sections):
        yield section, _Context(where="body", section=index, part=section)
    for master_page in doc.oxml.master_pages:
        yield master_page, _Context(where="master_page", section=None, part=master_page)


def _object_model(element: Any, paragraph: Any) -> Any:
    """The model object for an object element, as ``paragraph.objects`` gives it: a table, a shape,
    a picture (:class:`hwpx.model.Picture`, with ``item_id``), an equation (:class:`hwpx.model.Equation`,
    with ``script``), or an inline object for the rest (OLE, chart, video, text art). Pictures and
    equations are inline objects too, so code that took them as such keeps working."""

    from ..oxml import HwpxOxmlInlineObject, HwpxOxmlTable
    from ..oxml.objects import HwpxOxmlEquation, HwpxOxmlPicture, HwpxOxmlShape

    name = _local(element)
    if name == "tbl":
        return HwpxOxmlTable(element, paragraph)
    if name in _SHAPE_TAGS:
        return HwpxOxmlShape(element, paragraph)
    if name == "pic":
        return HwpxOxmlPicture(element, paragraph)
    if name == "equation":
        return HwpxOxmlEquation(element, paragraph)
    return HwpxOxmlInlineObject(element, paragraph)


def _place_fields(context: _Context) -> dict[str, Any]:
    from ..oxml import HwpxOxmlParagraph

    part = context.part
    table = None
    if context.table is not None:
        table = _object_model(context.table, HwpxOxmlParagraph(context.table_paragraph, part))
    owner = None
    if context.owner is not None:
        owner = _object_model(context.owner, HwpxOxmlParagraph(context.owner_paragraph, part))
    return {
        "where": context.where,
        # The body part is the section itself; a master page belongs to no section.
        "section": part if context.section is not None else None,
        "page_type": context.page_type,
        "table": table,
        "row": context.row,
        "col": context.col,
        "owner": owner,
        "depth": context.depth,
    }


def _check_choices(argument: str, values: "Iterable[str] | None", allowed: "Iterable[str]") -> "frozenset[str] | None":
    from ..errors import HwpxValueError

    if values is None:
        return None
    chosen = frozenset([values] if isinstance(values, str) else values)
    allowed_set = frozenset(allowed)
    unknown = sorted(chosen - allowed_set)
    if unknown:
        raise HwpxValueError(
            f"{argument} 에 모르는 값이 있습니다: {unknown}",
            code="text-place-invalid",
            context={"argument": argument, "unknown": unknown, "allowed": sorted(allowed_set)},
            suggestion=f"{argument}= 에는 {', '.join(sorted(allowed_set))} 를 줍니다.",
        )
    return chosen


def iter_paragraph_places(doc: "HwpxDocument", where: "Iterable[str] | str | None" = None) -> Iterator["ParagraphPlace"]:
    """Every paragraph of *doc* (body, cells, text boxes, captions, headers, footers, notes, memos,
    master pages), in document order, with where it sits."""

    from ..objects.results import ParagraphPlace
    from ..oxml import HwpxOxmlParagraph

    wanted = _check_choices("where", where, PLACES)
    for part, root in _parts(doc):
        counts = _story_counts(part.element)
        for kind, element, context, _holder in _walk(part.element, root, None, "", counts):
            if kind != "p" or (wanted is not None and context.where not in wanted):
                continue
            yield ParagraphPlace(paragraph=HwpxOxmlParagraph(element, part), **_place_fields(context))


def _step(context: _Context, holder: Any, parent: Any, child: Any) -> tuple[_Context, Any]:
    """The context and holding paragraph :func:`_walk` has inside *child*, a child of *parent*."""

    name = _local(child)
    if name == "p":
        return context, child
    if name == "subList" and _local(parent) == "fieldBegin":
        return replace(context, where="memo"), None
    if name in OBJECT_KINDS:
        return replace(context, owner=child, owner_paragraph=holder, depth=context.depth + 1), holder
    if name == "tc" and _local(parent) == "tr":
        address = next((n for n in child if _local(n) == "cellAddr"), None)
        cell = replace(
            context,
            where="cell",
            table=parent.getparent(),
            table_paragraph=holder,
            row=_int_attr(address, "rowAddr"),
            col=_int_attr(address, "colAddr"),
        )
        return cell, holder
    if name == "caption":
        return replace(context, where="caption"), holder
    if name == "drawText":
        return replace(context, where="text_box"), holder
    if name in ("header", "footer"):
        return replace(context, where=name, page_type=child.get("applyPageType", "BOTH")), holder
    if name in _NOTE_PLACES:
        return replace(context, where=_NOTE_PLACES[name]), holder
    if name == "memogroup":
        return replace(context, where="memo"), None
    if name == "hiddenComment":
        return replace(context, where="hidden_comment"), holder
    return context, holder


def _scope(element: Any, part: Any) -> tuple[_Context, Any, Mapping[Any, int]]:
    """Where *element* (an element of the part *part*) sits, as :func:`_walk` would have it when it reaches
    the element: the context, the paragraph holding it and the story/memo counts of the part.

    Reads only the element's ancestors and the part's top level, so a caller can ask this for every
    paragraph of a document without walking the document again each time.
    """

    from ..errors import HwpxValueError
    from ..oxml.section import HwpxOxmlSection

    root = part.element
    chain = []
    node = element
    while node is not None and node is not root:
        chain.append(node)
        node = node.getparent()
    if node is None:
        raise HwpxValueError(
            "the element is not in the document",
            code="paragraph-not-in-document",
            suggestion="Read a paragraph or object of the document as it is now (it may have been removed).",
        )
    context = _Context(where="body" if isinstance(part, HwpxOxmlSection) else "master_page",
                       section=0 if isinstance(part, HwpxOxmlSection) else None, part=part)
    holder = None
    parent = root
    for child in reversed(chain):
        context, holder = _step(context, holder, parent, child)
        parent = child
    return context, holder, _PartCounts(root, chain[-1] if chain else root)


class _PartCounts(dict):  # type: ignore[type-arg]
    """:func:`_story_counts` for a walk inside one top-level child of a part: the stories of the
    ``hp:secPr`` its runs hold, and -- read once, when the walk first asks about a memo -- the memos
    of the part's ``hp:memogroup``. Asking for every paragraph of a document stays linear."""

    def __init__(self, root: Any, top: Any) -> None:
        super().__init__()
        self._root: Any = root
        for run in top if _local(top) == "p" else ():
            for setting in run if _local(run) == "run" else ():
                if _local(setting) != "secPr":
                    continue
                for story in setting:
                    if _local(story) in ("header", "footer"):
                        key = (_local(story), story.get("id"), story.get("applyPageType", "BOTH"))
                        self[key] = self.get(key, 0) + 1

    def get(self, key: Any, default: Any = None) -> Any:
        if self._root is not None and key[0] == "memo":
            root, self._root = self._root, None
            for group in root:
                if _local(group) == "memogroup":
                    for memo in group.iter():
                        if _local(memo) == "memo" and memo.get("id"):
                            self[("memo", memo.get("id"), "")] = 1
        return super().get(key, default)


#: The ``iter`` tag filters for a choice of object kinds (``None``: every kind).
_KIND_TAGS: dict["frozenset[str] | None", tuple[str, ...]] = {}
_OBJECT_KIND_SET = frozenset(OBJECT_KINDS.values())


def paragraph_object_places(
    paragraph: Any,
    kinds: "Iterable[str] | str | None" = None,
    where: "Iterable[str] | str | None" = None,
) -> Iterator["ObjectPlace"]:
    """Every object inside *paragraph* (``paragraph.iter_objects()``), at any depth, in document order.

    Checks the arguments at once and returns an empty iterator, without walking, when nothing of
    those kinds sits anywhere inside the paragraph (most paragraphs)."""

    wanted_kinds = None if kinds is None else _check_choices("kinds", kinds, _OBJECT_KIND_SET)
    wanted_places = None if where is None else _check_choices("where", where, PLACES)
    tags = _KIND_TAGS.get(wanted_kinds)
    if tags is None:
        tags = _KIND_TAGS[wanted_kinds] = tuple(
            f"{{*}}{name}" for name, kind in OBJECT_KINDS.items() if wanted_kinds is None or kind in wanted_kinds
        )
    if next(paragraph.element.iter(*tags), None) is None:
        return iter(())
    return _paragraph_object_places(paragraph, wanted_kinds, wanted_places)


def _paragraph_object_places(
    paragraph: Any, wanted_kinds: "frozenset[str] | None", wanted_places: "frozenset[str] | None"
) -> Iterator["ObjectPlace"]:
    from ..objects.results import ObjectPlace
    from ..oxml import HwpxOxmlParagraph

    part = paragraph.section
    context, _holder, counts = _scope(paragraph.element, part)
    for kind, element, inner, holder in _walk(paragraph.element, context, paragraph.element, "p", counts):
        if kind != "object":
            continue
        object_kind = OBJECT_KINDS[_local(element)]
        if wanted_kinds is not None and object_kind not in wanted_kinds:
            continue
        if wanted_places is not None and inner.where not in wanted_places:
            continue
        holding = paragraph if holder is paragraph.element else HwpxOxmlParagraph(holder, part)
        yield ObjectPlace(object=_object_model(element, holding), kind=object_kind, **_place_fields(inner))


def paragraph_paragraph_places(paragraph: Any, where: "Iterable[str] | str | None" = None) -> Iterator["ParagraphPlace"]:
    """Every paragraph inside *paragraph* (``paragraph.iter_paragraphs()``), at any depth, in document order:
    the walk of ``doc.text.iter_paragraphs()`` narrowed to what the paragraph holds, itself left out."""

    from ..objects.results import ParagraphPlace
    from ..oxml import HwpxOxmlParagraph

    wanted = _check_choices("where", where, PLACES)
    if next(paragraph.element.iter("{*}p"), None) is None:
        return iter(())
    return _paragraph_paragraph_places(paragraph, wanted, ParagraphPlace, HwpxOxmlParagraph)


def _paragraph_paragraph_places(
    paragraph: Any, wanted: "frozenset[str] | None", place: Any, model: Any
) -> Iterator["ParagraphPlace"]:
    part = paragraph.section
    context, _holder, counts = _scope(paragraph.element, part)
    for kind, element, inner, _ in _walk(paragraph.element, context, paragraph.element, "p", counts):
        if kind == "p" and (wanted is None or inner.where in wanted):
            yield place(paragraph=model(element, part), **_place_fields(inner))


def object_paragraph_places(obj: Any, where: "Iterable[str] | str | None" = None) -> Iterator["ParagraphPlace"]:
    """Every paragraph inside the object *obj* (``shape.iter_paragraphs()``), in document order."""

    from ..objects.results import ParagraphPlace
    from ..oxml import HwpxOxmlParagraph

    wanted = _check_choices("where", where, PLACES)
    paragraph = obj.paragraph
    if paragraph is None or next(obj.element.iter("{*}p"), None) is None:
        return
    part = paragraph.section
    context, holder, counts = _scope(obj.element, part)
    name = _local(obj.element)
    for kind, element, inner, _holder in _walk(obj.element, context, holder, name, counts):
        if kind == "p" and (wanted is None or inner.where in wanted):
            yield ParagraphPlace(paragraph=HwpxOxmlParagraph(element, part), **_place_fields(inner))


def _top_paragraphs(node: Any) -> Iterator[Any]:
    """The ``hp:p`` elements inside *node* that no other ``hp:p`` inside it holds, in document order."""

    for child in node:
        if _local(child) == "p":
            yield child
        else:
            yield from _top_paragraphs(child)


def paragraph_nested_text(paragraph: Any, where: "Iterable[str] | str | None" = None) -> str:
    """The text of *paragraph* with that of the paragraphs inside it (``paragraph.nested_text()``)."""

    from ..oxml._document_primitives import _is_tab_control_element, _text_element_content

    wanted = None if where is None else _check_choices("where", where, PLACES)
    if next(paragraph.element.iter("{*}p"), None) is None:
        return paragraph.text  # nothing inside: no need to walk
    context, _holder, counts = _scope(paragraph.element, paragraph.section)
    places = {
        element: inner.where
        for kind, element, inner, _ in _walk(paragraph.element, context, paragraph.element, "p", counts)
        if kind == "p"
    }
    stretches: list[str] = []

    def read(p_element: Any, own: bool) -> None:
        current: list[str] = []

        def flush() -> None:
            if own and current:
                stretches.append("".join(current))
            current.clear()

        for run in p_element:
            if _local(run) != "run":
                continue
            for child in run:
                name = _local(child)
                if name == "t":
                    current.append(_text_element_content(child))
                elif name == "tab" or _is_tab_control_element(child):
                    current.append("\t")
                elif name:
                    inner = [element for element in _top_paragraphs(child) if element in places]
                    if inner:
                        flush()
                        for element in inner:
                            read(element, wanted is None or places[element] in wanted)
        flush()

    read(paragraph.element, True)
    return "\n".join(stretches)


def section_blocks(section: Any) -> tuple[Any, ...]:
    """The paragraphs of *section* and the tables placed right in it, in file order (``section.blocks``)."""

    from ..oxml import HwpxOxmlParagraph, HwpxOxmlTable

    blocks: list[Any] = []
    for child in section.element:
        name = _local(child)
        if name == "p":
            blocks.append(HwpxOxmlParagraph(child, section))
        elif name == "tbl":
            table = HwpxOxmlTable(child, None)  # type: ignore[arg-type]  # no paragraph holds it
            table._section = section
            blocks.append(table)
    return tuple(blocks)


def iter_object_places(
    doc: "HwpxDocument",
    kinds: "Iterable[str] | str | None" = None,
    where: "Iterable[str] | str | None" = None,
) -> Iterator["ObjectPlace"]:
    """Every table, picture, equation, shape (container members included), OLE object, chart,
    video and text art of *doc*, in document order, with the place of the paragraph holding it."""

    from ..objects.results import ObjectPlace
    from ..oxml import HwpxOxmlParagraph

    wanted_kinds = _check_choices("kinds", kinds, set(OBJECT_KINDS.values()))
    wanted_places = _check_choices("where", where, PLACES)
    for part, root in _parts(doc):
        counts = _story_counts(part.element)
        for kind, element, context, holder in _walk(part.element, root, None, "", counts):
            if kind != "object":
                continue
            object_kind = OBJECT_KINDS[_local(element)]
            if wanted_kinds is not None and object_kind not in wanted_kinds:
                continue
            if wanted_places is not None and context.where not in wanted_places:
                continue
            paragraph = HwpxOxmlParagraph(holder, part) if holder is not None else None
            yield ObjectPlace(object=_object_model(element, paragraph), kind=object_kind, **_place_fields(context))
