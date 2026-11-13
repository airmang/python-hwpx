# SPDX-License-Identifier: Apache-2.0
"""Choices a form offers as check marks typed into the text (``□ 예  □ 아니오``).

Korean forms rarely use form objects for a choice: the boxes are characters.
The same characters also start list lines (``○ 추진 배경``), so a mark alone is
not a choice. Only a paragraph holding two or more marks of one family (squares
``□☐■☑☒▣`` or circles ``○◯●``) is read as a group of options; the text after
each mark, up to the next one, is that option's name.

:func:`form_choices` lists the groups with the label each is chosen by, and
:func:`choose` checks options by name or position. A mark is replaced by one
character of the same family, so nothing else in the paragraph moves.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypedDict, Union

from ..oxml._document_primitives import _clear_paragraph_layout_cache
from .table_navigation import (
    _OCCURRENCE_RE,
    _collapse_whitespace,
    _collect_document_tables,
    _normalize_label_text,
    _text_of_cell,
)

if TYPE_CHECKING:
    from ..document import HwpxDocument

__all__ = [
    "ChoiceApplied",
    "ChoiceFailed",
    "ChoiceGroup",
    "ChoiceOption",
    "ChoiceSelection",
    "ChooseResult",
    "FormChoicesResult",
    "choose",
    "form_choices",
]

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

#: family -> (unchecked marks, checked marks)
_FAMILIES: dict[str, tuple[str, str]] = {
    "square": ("□☐", "■☑☒▣"),
    "circle": ("○◯", "●"),
}
_CHECKED_FOR = {"□": "■", "☐": "☑", "○": "●", "◯": "●"}
_UNCHECKED_FOR = {"■": "□", "☑": "☐", "☒": "☐", "▣": "□", "●": "○"}
_FAMILY_OF = {mark: family for family, pair in _FAMILIES.items() for mark in pair[0] + pair[1]}
_CHECKED = frozenset(mark for _, checked in _FAMILIES.values() for mark in checked)
_MARK_RE = re.compile("[" + "".join(_FAMILY_OF) + "]")
#: Punctuation that separates options or closes a label, not part of a name.
_EDGE = " \t\r\n,;/·ㆍ:："

ChoiceSelection = Union[str, int, Sequence[Union[str, int]]]


class ChoiceOption(TypedDict):
    position: int
    text: str
    checked: bool
    mark: str


class _ChoiceGroupRequired(TypedDict):
    index: int
    path: str
    label: str
    options: list[ChoiceOption]


class ChoiceGroup(_ChoiceGroupRequired, total=False):
    paragraph_index: int
    table_index: int
    row: int
    col: int


class FormChoicesResult(TypedDict):
    choices: list[ChoiceGroup]
    count: int


class ChoiceApplied(TypedDict):
    path: str
    label: str
    checked: list[str]
    changed: int


class _ChoiceFailedRequired(TypedDict):
    path: str
    reason: str


class ChoiceFailed(_ChoiceFailedRequired, total=False):
    options: list[str]
    candidates: list[str]


class ChooseResult(TypedDict):
    applied_count: int
    failed_count: int
    applied: list[ChoiceApplied]
    failed: list[ChoiceFailed]


@dataclass(slots=True)
class _Mark:
    node: Any  # the element whose text or tail holds the character
    in_tail: bool
    offset: int
    char: str
    text: str = ""  # the option's name


@dataclass(slots=True)
class _Group:
    paragraph: Any  # element
    owner: Any  # the object to mark dirty (a table or a section)
    marks: list[_Mark]
    label: str = ""
    location: dict[str, int] = field(default_factory=dict)
    index: int = 0
    path: str = ""


def _segments(paragraph: Any) -> list[tuple[Any, bool, str]]:
    """The paragraph's own text as ``(node, in_tail, text)`` pieces, in order.

    A control inside the text (a tab, a line break) stands between two pieces
    as a piece of one space that belongs to no node.
    """

    pieces: list[tuple[Any, bool, str]] = []
    for text_element in paragraph.iterfind(f"{_HP}run/{_HP}t"):
        if text_element.text:
            pieces.append((text_element, False, text_element.text))
        for child in text_element:
            pieces.append((None, False, " "))
            if child.tail:
                pieces.append((child, True, child.tail))
    return pieces


def _read_marks(paragraph: Any) -> tuple[str, list[_Mark]]:
    """The text before the first mark and the marks of the paragraph's choice group.

    No group (an empty list) unless one family has two or more marks; marks of
    the other family are then plain characters of the names around them.
    """

    pieces = _segments(paragraph)
    whole = "".join(text for _, _, text in pieces)
    found = [(match.start(), match.group()) for match in _MARK_RE.finditer(whole)]
    by_family = Counter(_FAMILY_OF[char] for _, char in found)
    if not by_family:
        return whole, []
    family, count = by_family.most_common(1)[0]
    if count < 2 or list(by_family.values()).count(count) > 1:
        return whole, []  # a single mark is a bullet; two families equally often is not ours to guess
    positions = [(start, char) for start, char in found if _FAMILY_OF[char] == family]

    marks: list[_Mark] = []
    cursor = 0
    lookup = iter(positions)
    wanted = next(lookup, None)
    for node, in_tail, text in pieces:
        while wanted is not None and cursor <= wanted[0] < cursor + len(text):
            if node is None:
                return whole, []
            marks.append(_Mark(node=node, in_tail=in_tail, offset=wanted[0] - cursor, char=wanted[1]))
            wanted = next(lookup, None)
        cursor += len(text)
    bounds = [start for start, _ in positions] + [len(whole)]
    for number, mark in enumerate(marks):
        mark.text = _collapse_whitespace(whole[bounds[number] + 1 : bounds[number + 1]]).strip(_EDGE)
    return whole[: positions[0][0]], marks


def _is_choice_text(text: str) -> bool:
    return max(Counter(_FAMILY_OF[char] for char in _MARK_RE.findall(text)).values(), default=0) >= 2


def _label_text(text: str) -> str:
    return _collapse_whitespace(text).strip(_EDGE)


def _neighbour_label(table: Any, row: int, col: int, cell: Any) -> str:
    """The nearest cell to the left, then above, that holds a name and not choices."""

    for step_row, step_col in ((0, -1), (-1, 0)):
        r, c = row + step_row, col + step_col
        while r >= 0 and c >= 0:
            try:
                other = table.cell(r, c)
            except (IndexError, ValueError):
                break
            if other.element is not cell.element:
                text = _text_of_cell(other)
                if text.strip() and not _is_choice_text(text):
                    return _label_text(text)
            r, c = r + step_row, c + step_col
    return ""


def _collect(document: "HwpxDocument") -> list[_Group]:
    groups: list[_Group] = []
    tables = _collect_document_tables(document)
    by_anchor: dict[int, list[Any]] = {}
    for table_ref in tables:
        by_anchor.setdefault(table_ref.paragraph_index, []).append(table_ref)

    for paragraph_index, paragraph in enumerate(document.paragraphs):
        before, marks = _read_marks(paragraph.element)
        if marks:
            groups.append(
                _Group(
                    paragraph=paragraph.element,
                    owner=paragraph.section,
                    marks=marks,
                    label=_label_text(before),
                    location={"paragraph_index": paragraph_index},
                )
            )
        for table_ref in by_anchor.get(paragraph_index, ()):
            table = table_ref.table
            for position in table.iter_grid():
                if not position.is_anchor:
                    continue
                row, col = position.anchor
                cell = position.cell
                earlier = ""
                for cell_paragraph in cell.paragraphs:
                    before, marks = _read_marks(cell_paragraph.element)
                    if not marks:
                        own = _label_text(before)
                        if own:
                            earlier = own
                        continue
                    label = _label_text(before) or earlier or _neighbour_label(table, row, col, cell)
                    groups.append(
                        _Group(
                            paragraph=cell_paragraph.element,
                            owner=table,
                            marks=marks,
                            label=label,
                            location={"table_index": table_ref.table_index, "row": row, "col": col},
                        )
                    )

    seen: Counter[str] = Counter()
    totals = Counter(_normalize_label_text(group.label) for group in groups if group.label)
    for number, group in enumerate(groups, start=1):
        group.index = number
        key = _normalize_label_text(group.label)
        if not key:
            group.path = f"#{number}"
            continue
        seen[key] += 1
        group.path = group.label if totals[key] == 1 else f"{group.label}[{seen[key]}]"
    return groups


def _payload(group: _Group) -> ChoiceGroup:
    entry: ChoiceGroup = {
        "index": group.index,
        "path": group.path,
        "label": group.label,
        "options": [
            {"position": number, "text": mark.text, "checked": mark.char in _CHECKED, "mark": mark.char}
            for number, mark in enumerate(group.marks, start=1)
        ],
    }
    entry.update(group.location)  # type: ignore[typeddict-item]
    return entry


def form_choices(document: "HwpxDocument") -> FormChoicesResult:
    """List the choices typed as check marks, in document order.

    Each group has the ``path`` :func:`choose` takes: its label (the text
    before the first mark, else the line above it in the cell, else the cell to
    its left or above), with ``[n]`` when several groups share the label, or
    ``#n`` (its number in this list) when it has none. Body paragraphs and
    table cells are read; headers, notes and text boxes are not.
    """

    groups = [_payload(group) for group in _collect(document)]
    return {"choices": groups, "count": len(groups)}


def _find_groups(groups: list[_Group], path: str) -> tuple[list[_Group], str | None]:
    token = path.strip()
    if token.startswith("#") and token[1:].isdigit():
        number = int(token[1:])
        chosen = [group for group in groups if group.index == number]
        return chosen, None if chosen else f"no choice group #{number} (there are {len(groups)})"
    key = _normalize_label_text(token)
    if not key:
        return [], "path must name a choice group"
    pool = [group for group in groups if _normalize_label_text(group.label) == key]
    if pool:
        return pool, None
    occurrence = _OCCURRENCE_RE.match(token)
    if occurrence is None:
        return [], None
    pool = [group for group in groups if _normalize_label_text(group.label) == _normalize_label_text(occurrence["label"])]
    number = int(occurrence["number"])
    if pool and number > len(pool):
        return [], f"label occurrence out of range: {number} of {len(pool)}"
    return pool[number - 1 : number], None


def _wanted_positions(group: _Group, selection: ChoiceSelection) -> tuple[set[int], str | None]:
    items: Sequence[Any]
    if isinstance(selection, (str, int)) and not isinstance(selection, bool):
        items = [selection]
    elif isinstance(selection, Sequence):
        items = list(selection)
    else:
        return set(), "selection must be an option name, a position, or a list of them"
    wanted: set[int] = set()
    for item in items:
        if isinstance(item, bool) or not isinstance(item, (str, int)):
            return set(), "selection must be an option name, a position, or a list of them"
        if isinstance(item, int):
            if not 1 <= item <= len(group.marks):
                return set(), f"option position out of range: {item} of {len(group.marks)}"
            wanted.add(item - 1)
            continue
        key = _normalize_label_text(item.strip(_EDGE))
        matches = [number for number, mark in enumerate(group.marks) if key and _normalize_label_text(mark.text) == key]
        if not matches:
            return set(), "option not found"
        if len(matches) > 1:
            return set(), "ambiguous option"
        wanted.add(matches[0])
    return wanted, None


def _pairings(groups: list[_Group]) -> tuple[Counter[tuple[str, str]], Counter[tuple[str, str]]]:
    """How often each unchecked mark stands in a group with each checked mark, both ways."""

    checked_for: Counter[tuple[str, str]] = Counter()
    for group in groups:
        chars = {mark.char for mark in group.marks}
        for empty in chars - _CHECKED:
            for full in chars & _CHECKED:
                checked_for[(empty, full)] += 1
    unchecked_for = Counter({(full, empty): count for (empty, full), count in checked_for.items()})
    return checked_for, unchecked_for


def _replacement(char: str, want_checked: bool, group: _Group, pairings: tuple[Counter, Counter]) -> str:
    """The mark to write in place of *char*: the group's own, else the document's habit, else the usual pair."""

    targets = _CHECKED if want_checked else frozenset(_FAMILY_OF) - _CHECKED
    family = _FAMILY_OF[char]
    own = Counter(mark.char for mark in group.marks if mark.char in targets and _FAMILY_OF[mark.char] == family)
    if own:
        return own.most_common(1)[0][0]
    habit = Counter({other: count for (source, other), count in pairings[0 if want_checked else 1].items() if source == char})
    if habit:
        return habit.most_common(1)[0][0]
    return (_CHECKED_FOR if want_checked else _UNCHECKED_FOR)[char]


def _write(mark: _Mark, char: str) -> None:
    current = mark.node.tail if mark.in_tail else mark.node.text
    updated = current[: mark.offset] + char + current[mark.offset + 1 :]
    if mark.in_tail:
        mark.node.tail = updated
    else:
        mark.node.text = updated
    mark.char = char


def choose(document: "HwpxDocument", selections: Mapping[str, ChoiceSelection]) -> ChooseResult:
    """Check the named options of choice groups and uncheck the group's others.

    A key is a group's ``path`` from :func:`form_choices`: its label (compared
    without whitespace or case), ``label[2]`` for the second group with that
    label, or ``#3`` for the third group in the document. A value is an
    option's name, its position (from 1), or a list of them; an empty list
    clears the group. After the call exactly the options given are checked.

    A checked mark is written as the group already writes it, else as the
    document pairs it elsewhere, else ``□→■``, ``☐→☑``, ``○→●``. A group or
    option that cannot be told apart is not changed and is reported under
    ``failed`` with the groups or option names to choose from.
    """

    groups = _collect(document)
    pairings = _pairings(groups)
    applied: list[ChoiceApplied] = []
    failed: list[ChoiceFailed] = []
    plans: list[tuple[str, _Group, set[int]]] = []

    for path, selection in selections.items():
        found, error = _find_groups(groups, path)
        if error is not None:
            failed.append({"path": path, "reason": error})
            continue
        if not found:
            failed.append({"path": path, "reason": "choice group not found", "candidates": [g.path for g in groups]})
            continue
        if len(found) > 1:
            failed.append({"path": path, "reason": "ambiguous label", "candidates": [g.path for g in found]})
            continue
        group = found[0]
        wanted, error = _wanted_positions(group, selection)
        if error is not None:
            failed.append({"path": path, "reason": error, "options": [mark.text for mark in group.marks]})
            continue
        plans.append((path, group, wanted))

    for path, group, wanted in plans:
        changed = 0
        for number, mark in enumerate(group.marks):
            want_checked = number in wanted
            if (mark.char in _CHECKED) == want_checked:
                continue
            _write(mark, _replacement(mark.char, want_checked, group, pairings))
            changed += 1
        if changed:
            _clear_paragraph_layout_cache(group.paragraph)
            group.owner.mark_dirty()
        applied.append(
            {
                "path": path,
                "label": group.label,
                "checked": [group.marks[number].text for number in sorted(wanted)],
                "changed": changed,
            }
        )

    return {
        "applied_count": len(applied),
        "failed_count": len(failed),
        "applied": applied,
        "failed": failed,
    }
