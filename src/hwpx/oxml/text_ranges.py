# SPDX-License-Identifier: Apache-2.0
"""Putting text in, taking a range out, and moving or copying a range of a paragraph.

Positions count as ``paragraph.text`` does (see :mod:`hwpx.oxml.text_offsets`): a character, a tab, a line
break and a special space are one each; a control, an object or a mark none. A thing that takes no
character stands at its ``offset``, "after character ``offset - 1``, before character ``offset``". A range
``[start, end)`` holds the zero-width things strictly inside it (``start < offset < end``); those at its
ends stay outside. Text put at a position goes after the zero-width things already there and before the
character there, the place an object's ``move_to(offset=)`` takes.

How Hancom writes what these calls write, from documents Hangul 2024 saved (``tests/fixtures/hancom_saved``):

- a note or a bookmark in the middle of a run's text: ``<hp:t>..</hp:t><hp:ctrl>..</hp:ctrl><hp:t>..</hp:t>``
  in that one run (``mid_footnote``, ``mid_bookmark``, ``mid_note_and_mark``);
- a highlight across runs: its start in the first run's ``hp:t``, its end in a later run's, once each
  (``highlight_across_runs``); a highlight never crosses a paragraph (``highlight_two_paragraphs``);
- a tab and a line break inside ``hp:t`` (``line_cache_tabs``, ``line_cache_line_breaks``).
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterator, Mapping, cast

from ..errors import HwpxTypeError, HwpxValueError
from ._document_primitives import (
    _TEXT_INLINE_ATOMS,
    _clear_paragraph_layout_cache,
    _fill_text_element,
    _is_tab_control_element,
    _require_text,
)
from ._paragraph_text_edit import is_section_setting

if TYPE_CHECKING:
    from .paragraph import HwpxOxmlParagraph
    from .run import HwpxOxmlRun

_MARKPEN = ("markpenBegin", "markpenEnd")
_TRACK_MARKS = frozenset({"insertBegin", "insertEnd", "deleteBegin", "deleteEnd"})
_NOTES = frozenset({"footNote", "endNote"})
#: What ``obj.copy_to`` refuses to bring into another document: an object holding text (a table, a text box,
#: a caption) and a connector.
_TEXT_HOLDERS = frozenset({"tbl", "drawText", "caption", "connectLine"})
_OBJECTS_CHOICES = ("refuse", "remove")


def _local(node: Any) -> str:
    tag = getattr(node, "tag", None)
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


@dataclass(eq=False)
class _Unit:
    """One piece of a paragraph, in file order: ``kind`` is ``text`` (a stretch of an ``hp:t``: its text when
    ``holder`` is ``None``, else the tail of ``holder``), ``atom`` (a tab, line break or special space in
    ``hp:t``), ``mark`` (an empty element in ``hp:t``: a highlight's or tracked change's mark), ``inner``
    (an element in ``hp:t`` with text of its own), ``t`` (an ``hp:t`` itself, where it opens), ``tab`` (a
    tab written beside ``hp:t``), ``settings`` (a section's settings) or ``item`` (any other child of a run:
    a control, an object)."""

    kind: str
    start: int
    length: int
    run: Any
    element: Any = None
    text: Any = None
    holder: Any = None

    @property
    def end(self) -> int:
        return self.start + self.length


def _runs(paragraph: Any) -> list[Any]:
    return [child for child in paragraph if _local(child) == "run"]


def _units(paragraph: Any) -> Iterator[_Unit]:
    position = 0
    for run in _runs(paragraph):
        for child in run:
            name = _local(child)
            if not name:
                continue
            if name == "t":
                yield _Unit("t", position, 0, run, child, child)
                if child.text:
                    yield _Unit("text", position, len(child.text), run, None, child, None)
                    position += len(child.text)
                for inner in child:
                    inner_name = _local(inner)
                    if inner_name in _TEXT_INLINE_ATOMS:
                        yield _Unit("atom", position, 1, run, inner, child)
                        position += 1
                    elif inner_name:
                        length = len("".join(inner.itertext()))
                        yield _Unit("inner" if length else "mark", position, length, run, inner, child)
                        position += length
                    if inner.tail:
                        yield _Unit("text", position, len(inner.tail), run, None, child, inner)
                        position += len(inner.tail)
            elif name == "tab" or _is_tab_control_element(child):
                yield _Unit("tab", position, 1, run, child)
                position += 1
            elif is_section_setting(child):
                yield _Unit("settings", position, 0, run, child)
            else:
                yield _Unit("item", position, 0, run, child)


def _check_offset(name: str, value: object, low: int, high: int) -> int:
    from .formatting import _check_offset as check

    return check(name, value, low, high)


def _changed(paragraph: "HwpxOxmlParagraph") -> None:
    from .utils import holding_paragraphs

    _clear_paragraph_layout_cache(paragraph.element)
    for holder in holding_paragraphs(paragraph.element):
        _clear_paragraph_layout_cache(holder)
    paragraph.section.mark_dirty()


# --------------------------------------------------------------------------
# Strings of an hp:t


def _string(text: Any, holder: Any) -> str:
    return (text.text if holder is None else holder.tail) or ""


def _set_string(text: Any, holder: Any, value: str) -> None:
    if holder is None:
        text.text = value or None
    else:
        holder.tail = value or None


def _remove_keeping_tail(element: Any) -> None:
    """Take *element* out of its ``hp:t``; the text after it joins the text before it."""

    parent = element.getparent()
    tail = element.tail or ""
    previous = element.getprevious()
    parent.remove(element)
    if tail:
        if previous is None:
            parent.text = (parent.text or "") + tail
        else:
            previous.tail = (previous.tail or "") + tail


def _splice_into_text(text: Any, holder: Any, at: int, piece: Any) -> None:
    """Put the content of the ``hp:t`` *piece* (its text and elements) into the ``hp:t`` *text*, at character
    *at* of the string *holder* names (:class:`_Unit`)."""

    value = _string(text, holder)
    before, after = value[:at], value[at:]
    children = list(piece)
    if not children:
        _set_string(text, holder, before + (piece.text or "") + after)
        return
    _set_string(text, holder, before + (piece.text or ""))
    index = 0 if holder is None else list(text).index(holder) + 1
    for offset, child in enumerate(children):
        text.insert(index + offset, child)
    last = children[-1]
    last.tail = ((last.tail or "") + after) or None


def _put_mark_before(unit: _Unit, at: int, mark: Any) -> None:
    """Put *mark* (an element for inside ``hp:t``) at character *at* of the text unit *unit*, or just before
    the atom or element *unit* is."""

    if unit.kind == "text":
        value = _string(unit.text, unit.holder)
        _set_string(unit.text, unit.holder, value[:at])
        mark.tail = value[at:] or None
        index = 0 if unit.holder is None else list(unit.text).index(unit.holder) + 1
        unit.text.insert(index, mark)
        return
    # Right before the element: the text before it (the parent's text, or the previous child's tail) stays
    # before the mark. Moving it into the mark's tail put the mark in front of that text.
    element = unit.element
    parent = element.getparent()
    mark.tail = None
    parent.insert(list(parent).index(element), mark)


def _merge_text_siblings(run: Any) -> None:
    """Join each ``hp:t`` of *run* to the ``hp:t`` right before it with the same attributes."""

    previous = None
    for child in list(run):
        if _local(child) != "t":
            previous = None
            continue
        if previous is not None and dict(previous.attrib) == dict(child.attrib):
            _splice_into_text(previous, previous[-1] if len(previous) else None,
                              len(_string(previous, previous[-1] if len(previous) else None)), child)
            run.remove(child)
            continue
        previous = child


def _merge_runs(paragraph: Any, runs: list[Any]) -> None:
    """Join each run of *runs* still in *paragraph* to the run right before it when both have the same
    attributes, as Hancom keeps one run for one character shape."""

    for run in runs:
        if run.getparent() is not paragraph:
            continue
        previous = run.getprevious()
        while previous is not None and not _local(previous):
            previous = previous.getprevious()
        if previous is None or _local(previous) != "run" or dict(previous.attrib) != dict(run.attrib):
            _merge_text_siblings(run)
            continue
        for child in list(run):
            previous.append(child)
        paragraph.remove(run)
        _merge_text_siblings(previous)


# --------------------------------------------------------------------------
# Where text goes


def _landing(paragraph: Any, offset: int) -> tuple[str, Any, Any, int]:
    """Where text put at *offset* goes: ``("text", hp:t, holder, at)`` -- into a string of an ``hp:t`` -- or
    ``("new", run, index, 0)`` -- a new ``hp:t`` at *index* of *run*. After the zero-width things at
    *offset*, before the character there; in the run of the character before when nothing is between."""

    last: _Unit | None = None
    first: _Unit | None = None
    for unit in _units(paragraph):
        if unit.kind == "t":
            if unit.start == offset and len(unit.element) == 0 and not unit.element.text:
                last = unit  # an empty hp:t right here takes it
            continue
        if unit.kind == "settings":
            continue  # a section's settings stand at no place in the text
        if unit.kind == "text" and unit.start < offset < unit.end:
            return ("text", unit.text, unit.holder, offset - unit.start)
        if unit.length and unit.start >= offset:
            first = unit
            break
        if unit.end == offset:
            last = unit
    if last is None:
        if first is not None:
            return _before(first)
        runs = _runs(paragraph)
        if not runs:
            return ("none", None, None, 0)
        return ("new", runs[0], len(runs[0]), 0)
    if last.kind == "t":
        return ("text", last.element, None, 0)
    if last.kind == "text":
        return ("text", last.text, last.holder, last.length)
    if last.kind in ("atom", "mark", "inner"):
        return ("text", last.text, last.element, 0)
    following = last.element.getnext()
    while following is not None and not _local(following):
        following = following.getnext()
    if following is not None and _local(following) == "t":
        return ("text", following, None, 0)
    return ("new", last.run, list(last.run).index(last.element) + 1, 0)


def _before(unit: _Unit) -> tuple[str, Any, Any, int]:
    """The place right before the character *unit* (the first of the paragraph)."""

    if unit.kind == "text":
        return ("text", unit.text, unit.holder, 0)
    if unit.kind in ("atom", "inner"):
        previous = unit.element.getprevious()
        return ("text", unit.text, previous, len(_string(unit.text, previous)))
    return ("new", unit.run, list(unit.run).index(unit.element), 0)


def _new_text_element(run: Any, value: str) -> Any:
    from ._document_primitives import _HP_NS, _child_tag_like

    piece = run.makeelement(_child_tag_like(run, "t", _HP_NS), {})
    _fill_text_element(piece, value)
    return piece


def _put_text(paragraph: "HwpxOxmlParagraph", offset: int, value: str) -> Any:
    """Write *value* at *offset* and return the run holding it."""

    element = paragraph.element
    kind, where, holder, at = _landing(element, offset)
    if kind == "none":
        from ._document_primitives import _HP

        run = element.makeelement(f"{_HP}run", {"charPrIDRef": str(paragraph.char_pr_id_ref or "0")})
        linesegs = [child for child in element if _local(child) == "linesegarray"]
        element.insert(list(element).index(linesegs[0]) if linesegs else len(element), run)
        kind, where, holder, at = "new", run, 0, 0
    if kind == "new":
        where.insert(holder, _new_text_element(where, value))
        return where
    _splice_into_text(where, holder, at, _new_text_element(where, value))
    return cast(Any, where).getparent()


# --------------------------------------------------------------------------
# insert_text


def insert_text(
    paragraph: "HwpxOxmlParagraph", offset: int, text: str, char_pr_id_ref: "str | int | None",
    changes: Mapping[str, Any],
) -> "tuple[HwpxOxmlRun, ...]":
    """``paragraph.insert_text``."""

    from .formatting import _char_changes, _cut_at, _header_of, _run_elements, _run_length, find_definition
    from .run import HwpxOxmlRun

    from ._paragraph_text_edit import require_in_document

    _require_text(text)
    if changes:  # a character shape to find or make in the header: the document's side
        require_in_document(paragraph, caller="insert_text")
    length = len(paragraph.text)
    offset = _check_offset("offset", offset, 0, length)
    if changes:
        _char_changes(changes)  # checked before anything is written
    if char_pr_id_ref is not None:
        if isinstance(char_pr_id_ref, bool) or not isinstance(char_pr_id_ref, (str, int)):
            raise HwpxTypeError(f"char_pr_id_ref must be a str or an int; got {char_pr_id_ref!r}",
                                code="style-char-pr-missing", context={"requested": repr(char_pr_id_ref)},
                                suggestion="Pass the id of an hh:charPr of the document's header.")
        if find_definition(_header_of(paragraph.section.document), "charPr", char_pr_id_ref) is None:
            raise HwpxValueError(
                f"the document has no character shape {char_pr_id_ref!r}",
                code="style-char-pr-missing",
                context={"requested": str(char_pr_id_ref)},
                suggestion="Use a run's char_pr_id_ref, or doc.styles to make the character shape first.",
            )
    if not text:
        return ()
    run = _put_text(paragraph, offset, text)
    added = len(paragraph.text) - length
    if char_pr_id_ref is None and not changes or not added:
        _changed(paragraph)
        return (HwpxOxmlRun(run, paragraph),)
    _cut_at(paragraph, offset + added)
    _cut_at(paragraph, offset)
    inside: list[Any] = []
    position = 0
    for candidate in _run_elements(paragraph):
        size = _run_length(candidate)
        if size and offset <= position and position + size <= offset + added:
            inside.append(candidate)
        position += size
    if char_pr_id_ref is not None:
        for candidate in inside:
            candidate.set("charPrIDRef", str(char_pr_id_ref).strip())
    if changes:
        from .formatting import format_range

        format_range(paragraph, offset, offset + added, changes)
    seams = [candidate for candidate in _run_elements(paragraph) if candidate in inside]
    following = cast(Any, seams[-1]).getnext() if seams else None
    _merge_runs(paragraph.element, seams + ([following] if following is not None else []))
    _changed(paragraph)
    position, result = 0, []
    for candidate in _runs(paragraph.element):
        size = _run_length(candidate)
        if size and position < offset + added and offset < position + size:
            result.append(HwpxOxmlRun(candidate, paragraph))
        position += size
    return tuple(result)


# --------------------------------------------------------------------------
# What a range holds


@dataclass
class _Held:
    """The zero-width things strictly inside a range, sorted."""

    items: list[_Unit]
    marks: list[_Unit]
    pens: list[tuple[_Unit, _Unit | None, _Unit | None]]  # (inside mark, its begin, its end)


def _pen_pairs(units: list[_Unit]) -> dict[int, tuple[_Unit | None, _Unit | None]]:
    """Each highlight mark's (begin, end) pair, by ``id()`` of the mark's unit."""

    pairs: dict[int, tuple[_Unit | None, _Unit | None]] = {}
    begin: _Unit | None = None
    for unit in units:
        if unit.kind != "mark":
            continue
        name = _local(unit.element)
        if name == "markpenBegin":
            if begin is not None:
                pairs[id(begin)] = (begin, None)
            begin = unit
        elif name == "markpenEnd":
            pairs[id(unit)] = (begin, unit)
            if begin is not None:
                pairs[id(begin)] = (begin, unit)
            begin = None
    if begin is not None:
        pairs[id(begin)] = (begin, None)
    return pairs


def _field_ends(element: Any) -> tuple[list[str], list[str]]:
    begins = [str(node.get("id") or "") for node in element.iter() if _local(node) == "fieldBegin"]
    ends = [str(node.get("beginIDRef") or "") for node in element.iter() if _local(node) == "fieldEnd"]
    return begins, ends


def _held(units: list[_Unit], start: int, end: int) -> _Held:
    held = _Held([], [], [])
    pairs = _pen_pairs(units)
    inside_begins: list[str] = []
    inside_ends: list[str] = []
    for unit in units:
        if unit.kind == "inner" and (unit.start < start < unit.end or unit.start < end < unit.end):
            raise HwpxValueError(
                "the range ends inside an element of the text that cannot be divided",
                code="paragraph-split-inside-element",
                context={"element": _local(unit.element), "start": start, "end": end},
                suggestion="Pick a range that holds that element whole or leaves it out.",
            )
        if unit.length or not start < unit.start < end:
            continue
        if unit.kind == "item":
            held.items.append(unit)
            begins, ends = _field_ends(unit.element)
            inside_begins += begins
            inside_ends += ends
        elif unit.kind == "mark":
            name = _local(unit.element)
            if name in _TRACK_MARKS:
                raise HwpxValueError(
                    "the range holds a tracked change's mark; a tracked change is accepted or rejected whole",
                    code="paragraph-range-splits-mark",
                    context={"mark": name, "offset": unit.start},
                    suggestion="Accept or reject the tracked change first (doc.tracking).",
                )
            if name in _MARKPEN:
                begin, finish = pairs.get(id(unit), (None, None))
                held.pens.append((unit, begin, finish))
            else:
                held.marks.append(unit)
    for field_id in inside_begins:
        if field_id not in inside_ends:
            raise _splits_field(field_id, start, end)
    for field_id in inside_ends:
        if field_id not in inside_begins:
            raise _splits_field(field_id, start, end)
    return held


def _splits_field(field_id: str, start: int, end: int) -> HwpxValueError:
    return HwpxValueError(
        f"characters {start}..{end} hold one end of a field (id {field_id}) and not the other",
        code="paragraph-range-splits-field",
        context={"field": field_id, "start": start, "end": end},
        suggestion="Widen or narrow the range to hold the whole field, or neither of its ends.",
    )


def _item_kinds(items: list[_Unit]) -> list[str]:
    kinds = []
    for unit in items:
        name = _local(unit.element)
        if name == "ctrl":
            kinds += [_local(child) for child in unit.element if _local(child)]
        else:
            kinds.append(name)
    return kinds


def _holds_objects(items: list[_Unit], start: int, end: int) -> HwpxValueError:
    return HwpxValueError(
        f"characters {start}..{end} hold things that take no character: {', '.join(_item_kinds(items))}",
        code="paragraph-range-holds-objects",
        context={"start": start, "end": end, "kinds": _item_kinds(items),
                 "offsets": [unit.start for unit in items]},
        suggestion="Pass objects='remove' to take them out with the text, or leave them out of the range.",
    )


# --------------------------------------------------------------------------
# delete_range


def _remove_items(paragraph: "HwpxOxmlParagraph", items: list[_Unit]) -> None:
    """Take the controls and objects *items* out as each one's own ``remove()`` does -- a note renumbers the
    notes after it, an object drops the images nobody uses any more, a field's two controls go together and
    a memo with its field -- and a bare control (a bookmark, an auto number ...) as it is. The text stays:
    the range's characters are cut after."""

    from .run import HwpxOxmlRun

    wanted = {id(unit.element) for unit in items}
    pieces = [piece for run in _runs(paragraph.element) for piece in HwpxOxmlRun(run, paragraph).content
              if id(piece.element.getparent() if piece.container == "ctrl" else piece.element) in wanted]
    for piece in pieces:
        element = piece.element
        if element.getparent() is None or piece.kind == "field_end":
            continue
        remove = getattr(piece.object, "remove", None)
        if piece.kind in ("ruby", "composed_character"):
            remove = None  # its remove() keeps its base text as characters; it takes none, and goes whole
        if remove is not None and (piece.kind in ("footnote", "endnote") or piece.container == "run"):
            remove()
        elif remove is not None and piece.kind == "field_begin":
            try:
                remove(keep_text=True)
            except TypeError:
                remove()
        if element.getparent() is not None:
            if piece.kind == "field_begin":
                _drop_field(paragraph.element, element)
            else:
                _drop_control(element)
    for unit in items:  # whatever no piece named
        if unit.element.getparent() is not None:
            unit.element.getparent().remove(unit.element)


def _drop_control(element: Any) -> None:
    parent = element.getparent()
    if parent is None:
        return
    if _local(parent) == "ctrl":
        parent.remove(element)
        if not any(_local(child) for child in parent):
            parent.getparent().remove(parent)
    else:
        parent.remove(element)


def _drop_field(paragraph: Any, begin: Any) -> None:
    field_id = begin.get("id")
    for node in list(paragraph.iter()):
        if _local(node) == "fieldEnd" and node.get("beginIDRef") == field_id:
            _drop_control(node)
    _drop_control(begin)


def _move_pens(units: list[_Unit], pens: list[tuple[_Unit, _Unit | None, _Unit | None]], start: int,
               end: int, *, dry: bool = False) -> list[Any]:
    """Keep a highlight that reaches out of the range: its mark inside the range goes to the range's edge
    (Hancom ends a highlight anywhere in a run's text, ``highlight_across_runs``). Returns the marks to
    take out with the range. *dry*: only refuse what cannot be done, change nothing."""

    gone: list[Any] = []
    inside = {id(unit) for unit, _b, _e in pens}
    for unit, begin, finish in pens:
        name = _local(unit.element)
        partner = finish if name == "markpenBegin" else begin
        if partner is not None and id(partner) in inside:
            gone.append(unit.element)
            continue
        if partner is None or (name == "markpenBegin" and partner.start == end) or (
                name == "markpenEnd" and partner.start == start):
            gone.append(unit.element)  # nothing of the highlight is left
            if partner is not None:
                gone.append(partner.element)
            continue
        # the highlight goes on outside the range: its edge moves to the range's edge
        at_char = end if name == "markpenBegin" else start - 1
        target = next(u for u in units if u.length and u.start <= at_char < u.end)
        if target.kind == "tab":
            raise HwpxValueError(
                "a highlight would have to start or end at a tab written beside the text",
                code="paragraph-range-splits-mark",
                context={"mark": name, "offset": unit.start},
                suggestion="Remove the highlight first, or widen the range to hold it whole.",
            )
        gone.append(unit.element)
        if dry:
            continue
        mark = deepcopy(unit.element)
        mark.tail = None
        if target.kind == "text":
            _put_mark_before(target, at_char - target.start + (0 if name == "markpenBegin" else 1), mark)
        elif name == "markpenBegin":
            _put_mark_before(target, 0, mark)
        else:  # right after a tab, line break or special space of hp:t
            element = target.element
            mark.tail, element.tail = element.tail, None
            parent = element.getparent()
            parent.insert(list(parent).index(element) + 1, mark)
    return gone


def _emptied_pens(units: list[_Unit], start: int, end: int) -> list[Any]:
    """The marks of a highlight that starts right at the range's start and ends right at its end: with
    the range gone it holds nothing, and Hancom writes no empty highlight."""

    gone: list[Any] = []
    for begin, finish in _pen_pairs(units).values():
        if begin is not None and finish is not None and begin.start == start and finish.start == end:
            gone += [begin.element, finish.element]
    return gone


def _cut_units(paragraph: Any, start: int, end: int, extra: list[Any]) -> tuple[list[Any], list[Any]]:
    """Take the characters ``[start, end)`` out, and the elements *extra*. Returns the ``hp:t`` and runs
    touched."""

    units = list(_units(paragraph))
    touched_text: list[Any] = []
    touched_runs: list[Any] = []
    doomed = {id(element) for element in extra}
    for unit in reversed(units):
        if unit.kind in ("t", "settings"):
            continue
        cut = unit.length and unit.start < end and start < unit.end
        if not cut and id(unit.element) not in doomed:
            continue
        if unit.run not in touched_runs:
            touched_runs.append(unit.run)
        if unit.text is not None and unit.text not in touched_text:
            touched_text.append(unit.text)
        if unit.kind == "text":
            value = _string(unit.text, unit.holder)
            low, high = max(start - unit.start, 0), min(end - unit.start, unit.length)
            _set_string(unit.text, unit.holder, value[:low] + value[high:])
        elif unit.kind in ("atom", "inner", "mark"):
            _remove_keeping_tail(unit.element)
        elif unit.kind in ("tab", "item"):
            unit.run.remove(unit.element)
    return touched_text, touched_runs


def _tidy(paragraph: Any, touched_text: list[Any], touched_runs: list[Any], first_run_attrib: dict) -> None:  # noqa: C901
    """Hancom's form after a cut: an emptied ``hp:t`` goes when its run keeps another ``hp:t`` or nothing
    else (and a run left empty goes); one emptied ``hp:t`` beside a run's controls or objects stays as the
    empty ``<hp:t/>`` Hancom writes there; neighbouring runs of one character shape become one."""

    for text in touched_text:
        run = text.getparent()
        if run is None or text.text or len(text):
            continue
        others = [child for child in run if child is not text and _local(child)]
        trailing = others and run[-1] is text  # Hancom's <hp:t/> after a run's controls and objects
        if not trailing or any(_local(child) == "t" for child in others):
            run.remove(text)
    seams: list[Any] = []  # runs that came to stand beside another when the runs between went
    removed: list[dict] = []
    for run in touched_runs:
        if run.getparent() is not paragraph:
            continue
        if any(_local(child) for child in run):
            _merge_text_siblings(run)
            continue
        following = run.getnext()
        removed.append(dict(run.attrib))
        paragraph.remove(run)
        if following is not None and _local(following) == "run":
            seams.append(following)
    if not any(_local(child) == "t" for run in _runs(paragraph) for child in run):
        # nothing of the text is left: Hancom's empty line, a run holding <hp:t/> (after the settings' run)
        from ._document_primitives import _HP

        run = paragraph.makeelement(f"{_HP}run", removed[-1] if removed else first_run_attrib)
        run.append(_new_text_element(run, ""))
        runs = _runs(paragraph)
        paragraph.insert(list(paragraph).index(runs[-1]) + 1 if runs else 0, run)
    _merge_runs(paragraph, [run for run in seams if run.getparent() is paragraph])


def delete_range(paragraph: "HwpxOxmlParagraph", start: int, end: int, objects: str) -> None:
    """``paragraph.delete_range``."""

    if objects not in _OBJECTS_CHOICES:
        raise HwpxValueError(f"objects must be 'refuse' or 'remove'; got {objects!r}", code="paragraph-range-invalid",
                             context={"name": "objects", "requested": repr(objects)},
                             suggestion="Pass objects='remove' to take controls and objects out with the text.")
    length = len(paragraph.text)
    start = _check_offset("start", start, 0, length)
    end = _check_offset("end", end, start, length)
    if start == end:
        return
    units = list(_units(paragraph.element))
    held = _held(units, start, end)
    if held.items and objects == "refuse":
        raise _holds_objects(held.items, start, end)
    _move_pens(units, held.pens, start, end, dry=True)
    runs = _runs(paragraph.element)
    first_attrib = dict(runs[0].attrib) if runs else {}
    if held.items:
        _remove_items(paragraph, held.items)
        units = list(_units(paragraph.element))
        held = _held(units, start, end)
    gone = _move_pens(units, held.pens, start, end) + [unit.element for unit in held.marks]
    gone += _emptied_pens(units, start, end)
    touched_text, touched_runs = _cut_units(paragraph.element, start, end, gone)
    _tidy(paragraph.element, touched_text, touched_runs, first_attrib)
    _changed(paragraph)


# --------------------------------------------------------------------------
# copy_range and move_range


def _fragment(paragraph: Any, start: int, end: int, *, take: bool) -> list[Any]:
    """The runs that write the characters ``[start, end)`` of *paragraph* and the zero-width things strictly
    inside them: new runs and ``hp:t``, the controls and objects moved out of *paragraph* when *take*, else
    copied. A highlight reaching out of the range is opened or closed at the fragment's edge, as Hancom
    writes one highlight a paragraph; section settings stay behind."""

    units = list(_units(paragraph))
    result: list[Any] = []
    for run in _runs(paragraph):
        pieces = [unit for unit in units if unit.run is run and (
            (unit.length and start <= unit.start and unit.end <= end)
            or (unit.kind == "text" and unit.start < end and start < unit.end)
            or (not unit.length and unit.kind in ("item", "mark") and start < unit.start < end))]
        if not pieces:
            continue
        copy = run.makeelement(run.tag, dict(run.attrib))
        text: Any = None
        source: Any = None
        for unit in pieces:
            if unit.kind in ("text", "atom", "inner", "mark"):
                if text is None or source is not unit.text or copy[-1] is not text:
                    text = copy.makeelement(unit.text.tag, dict(unit.text.attrib))
                    copy.append(text)
                    source = unit.text
                if unit.kind == "text":
                    value = _string(unit.text, unit.holder)
                    piece = text.makeelement(text.tag, {})
                    piece.text = value[max(start - unit.start, 0):min(end - unit.start, unit.length)]
                    last = text[-1] if len(text) else None
                    _splice_into_text(text, last, len(_string(text, last)), piece)
                else:
                    element = deepcopy(unit.element)
                    element.tail = None
                    text.append(element)
                continue
            text = None
            # A zero-width control or object is moved out here; a character written as an element straight
            # under the run (an hp:tab there) is copied, like the text: the range's characters are cut from
            # the paragraph afterwards, and taking it here as well cut the character after it too.
            moved = take and not unit.length
            element = unit.element if moved else deepcopy(unit.element)
            if moved:
                tail = element.tail
                unit.run.remove(element)
                element.tail = tail
            copy.append(element)
        result.append(copy)
    # Any character in the range -- also one inside a text unit that starts before it (a range in the middle
    # of a highlighted run): the highlights around it are put on the fragment.
    if not any(unit.length and unit.start < end and start < unit.end for unit in units):
        return result
    seen: set[int] = set()
    for begin, finish in _pen_pairs(units).values():
        if begin is None or id(begin) in seen:
            continue
        seen.add(id(begin))
        begin_inside = start < begin.start < end
        end_inside = finish is not None and start < finish.start < end
        if begin_inside and not end_inside:
            _close_pen(result, begin.element)
        elif end_inside and not begin_inside:
            _open_pen(result, begin.element)
        elif not begin_inside and begin.start <= start and (finish is None or finish.start >= end):
            _open_pen(result, begin.element)
            _close_pen(result, begin.element)
    return result


def _open_pen(runs: list[Any], begin: Any) -> None:
    text = next((child for run in runs for child in run if _local(child) == "t"), None)
    if text is None:
        return
    mark = deepcopy(begin)
    mark.tail, text.text = text.text, None
    text.insert(0, mark)


def _close_pen(runs: list[Any], begin: Any) -> None:
    texts = [child for run in runs for child in run if _local(child) == "t"]
    if texts:
        texts[-1].append(texts[-1].makeelement(str(begin.tag).replace("markpenBegin", "markpenEnd"), {}))


def _fragment_length(runs: list[Any]) -> int:
    from .formatting import _run_length

    return sum(_run_length(run) for run in runs)


def _splice_runs(target: "HwpxOxmlParagraph", offset: int, runs: list[Any]) -> None:
    """Put the runs *runs* into *target* at *offset* (after the zero-width things there), dividing the
    run there in two; runs of one character shape at the seams become one."""

    element = target.element
    kind, where, holder, at = _landing(element, offset)
    if kind == "none":
        for run in runs:
            linesegs = [child for child in element if _local(child) == "linesegarray"]
            element.insert(list(element).index(linesegs[0]) if linesegs else len(element), run)
        _merge_runs(element, runs)
        return
    if kind == "text":
        text, run = where, where.getparent()
        right_text = text.makeelement(text.tag, dict(text.attrib))
        value = _string(text, holder)
        _set_string(text, holder, value[:at])
        right_text.text = value[at:] or None
        index = 0 if holder is None else list(text).index(holder) + 1
        for child in list(text)[index:]:
            right_text.append(child)
        cut = list(run).index(text) + 1
        moving = [right_text] + list(run)[cut:]
        if not text.text and not len(text):
            run.remove(text)
    else:
        run, cut = where, holder
        moving = list(run)[cut:]
    right = run.makeelement(run.tag, dict(run.attrib))
    for child in moving:
        right.append(child)
    if len(right) and _local(right[0]) == "t" and not right[0].text and not len(right[0]):
        right.remove(right[0])
    position = list(element).index(run) + 1
    for offset_index, new in enumerate(runs):
        element.insert(position + offset_index, new)
    seams = list(runs)
    if len(right):
        element.insert(position + len(runs), right)
        seams.append(right)
    if not any(_local(child) for child in run):
        element.remove(run)
    _merge_runs(element, seams)


def _range_args(paragraph: "HwpxOxmlParagraph", start: int, end: int, to: Any, offset: Any) -> tuple[int, int, int]:
    from .paragraph import HwpxOxmlParagraph

    length = len(paragraph.text)
    start = _check_offset("start", start, 0, length)
    end = _check_offset("end", end, start, length)
    if not isinstance(to, HwpxOxmlParagraph):
        raise HwpxTypeError(f"to must be a paragraph object; got {type(to).__name__}",
                            code="paragraph-invalid-type",
                            context={"type": type(to).__name__},
                            suggestion="Pass the paragraph to put the range in, e.g. doc.paragraphs[i] or cell.paragraphs[0].")
    from ._paragraph_text_edit import require_in_document

    require_in_document(paragraph, caller="range", role="paragraph the range is taken from")
    require_in_document(to, caller="range", role="paragraph to put the range in")
    target_length = len(to.text)
    offset = target_length if offset is None else _check_offset("offset", offset, 0, target_length)
    return start, end, offset


def _refuse_place(paragraph: "HwpxOxmlParagraph", start: int, end: int, to: "HwpxOxmlParagraph",
                  offset: int, held: _Held, *, copying: bool = False) -> None:
    from .shape_position import paragraph_box

    for unit in held.items:
        if any(node is to.element for node in unit.element.iter()):
            raise HwpxValueError(
                "the range holds the cell, text box or note the paragraph to put it in sits in",
                code="paragraph-range-into-itself",
                context={"start": start, "end": end},
                suggestion="Pick a paragraph outside what the range holds.",
            )
    if not copying and to.element is paragraph.element and start < offset < end:
        raise HwpxValueError(
            f"offset {offset} is inside the range {start}..{end} that moves",
            code="paragraph-range-into-itself",
            context={"start": start, "end": end, "offset": offset},
            suggestion="Pick a place before the range's start or after its end.",
        )
    box = paragraph_box(to.element, to.section.element)
    if box in ("memo", "other"):
        raise HwpxValueError(
            "a range goes into the body, a cell, a text box, a note, a caption, a header or a footer; "
            "a memo's text changes through memo.text",
            code="paragraph-move-place-unsupported",
            context={"box": box},
            suggestion="Pick a paragraph outside the memo.",
        )
    from .shape_position import _check_place

    for unit in held.items:  # a table goes where table.move_to/copy_to puts one, or is refused as there
        if _local(unit.element) == "tbl":
            _check_place(unit.element, paragraph, to)
    notes = [kind for kind in _item_kinds(held.items) if kind in _NOTES]
    if notes and box in ("note", "header_footer"):
        raise HwpxValueError(
            "a footnote or an endnote cannot go into a note, a header or a footer",
            code="paragraph-move-place-unsupported",
            context={"box": box, "kinds": notes},
            suggestion="Leave the note out of the range, or put the range in the body, a cell or a text box.",
        )


def _copy_runs(paragraph: "HwpxOxmlParagraph", start: int, end: int, to: "HwpxOxmlParagraph") -> list[Any]:
    """Copies of the runs of ``[start, end)``, made for *to*'s document as ``paragraph.copy_to`` makes a
    paragraph's: fresh ids, definitions and images brought over from another document."""

    from ._document_primitives import _HP, _clone_paragraph_element
    from ._paragraph_text_edit import renumber_copied_fields
    from .memo import renew_copied_memos
    from .shape_position import unique_object_ids

    runs = _fragment(deepcopy(paragraph.element), start, end, take=False)
    stage = paragraph.element.makeelement(f"{_HP}p", dict(paragraph.element.attrib))
    for run in runs:
        stage.append(run)
    source_root, target_root = paragraph.section.document, to.section.document
    if source_root is target_root:
        copy = _clone_paragraph_element(stage, ids=to.section._ids)
        renumber_copied_fields(copy, ids=to.section._ids)
        sections = list(target_root.sections) if target_root is not None else [to.section]
        renew_copied_memos(copy, sections, to.section)
    else:
        copy = _copy_into_other_document(paragraph, stage, to)
    unique_object_ids(to.section, (copy,))
    return [child for child in copy if _local(child) == "run"]


def _copy_into_other_document(paragraph: "HwpxOxmlParagraph", stage: Any, to: "HwpxOxmlParagraph") -> Any:
    import weakref

    from ..tools.document_merge import _facade_of, _insert_memos_into_target_section, _merge_paragraphs

    for node in stage.iter():
        name = _local(node)
        if name in _TEXT_HOLDERS:
            raise HwpxValueError(
                "a range holding a table, a text box or a caption cannot go into another document",
                code="shape-copy-document-unsupported",
                context={"holds": name},
                suggestion="Copy the whole paragraph (paragraph.copy_to) or use insert_document.",
            )
    source_root, target_root = paragraph.section.document, to.section.document
    source_doc, target_doc = _facade_of(source_root), _facade_of(target_root)
    if source_doc is None or target_doc is None:
        raise HwpxValueError(
            "copying a range into another document needs both documents opened or created as documents",
            code="paragraph-not-in-document",
            suggestion="Open both with HwpxDocument.open(...) or make them with HwpxDocument.new().",
        )
    holder: Any = target_root
    registry = getattr(holder, "_copied_headings", None)
    if registry is None:
        registry = weakref.WeakKeyDictionary()
        holder._copied_headings = registry
    known: dict[str, dict[str, str]] = registry.setdefault(source_root, {})
    copies, memo_clones, _report = _merge_paragraphs(
        target_doc, source_doc, source_section_index=None, paragraphs=[stage], known_headings=known
    )
    _insert_memos_into_target_section(to.section, memo_clones)
    return copies[0]


def copy_range(paragraph: "HwpxOxmlParagraph", start: int, end: int, to: Any, offset: Any) -> tuple[int, int]:
    """``paragraph.copy_range``."""

    start, end, offset = _range_args(paragraph, start, end, to, offset)
    units = list(_units(paragraph.element))
    held = _held(units, start, end)
    _refuse_place(paragraph, start, end, to, offset, held, copying=True)
    if start == end:
        return (offset, offset)
    runs = _copy_runs(paragraph, start, end, to)
    size = _fragment_length(runs)
    notes = _note_kinds(runs)
    _fit_pasted_objects(runs, to)
    from .shape_position import _object_nodes, stack_new_object

    copied = [node for run in runs for node in _object_nodes(run)]
    _splice_runs(to, offset, runs)
    # Each copied object -- in a note or text box of the range too -- goes over the others in the order it
    # stands, as note.copy_to and shape.copy_to stack a copy; the copies kept the originals' zOrder before.
    for node in copied:
        stack_new_object(node, to.section)
    _changed(to)
    _renumber_kinds(notes, to.section)
    return (offset, offset + size)


def move_range(paragraph: "HwpxOxmlParagraph", start: int, end: int, to: Any, offset: Any) -> tuple[int, int]:
    """``paragraph.move_range``."""

    start, end, offset = _range_args(paragraph, start, end, to, offset)
    units = list(_units(paragraph.element))
    held = _held(units, start, end)
    _refuse_place(paragraph, start, end, to, offset, held)
    _move_pens(units, held.pens, start, end, dry=True)
    if start == end:
        return (offset, offset)  # nothing moves: the place it would land, as copy_range answers
    if to.element is paragraph.element and offset in (start, end):
        return (start, end)  # it lands where it is
    if paragraph.section.document is not to.section.document:
        position = copy_range(paragraph, start, end, to, offset)
        delete_range(paragraph, start, end, "remove")
        return position
    runs_before = _runs(paragraph.element)
    first_attrib = dict(runs_before[0].attrib) if runs_before else {}
    runs = _fragment(paragraph.element, start, end, take=True)
    size = _fragment_length(runs)
    units = list(_units(paragraph.element))
    left = _held(units, start, end)
    gone = _move_pens(units, left.pens, start, end) + [unit.element for unit in left.marks]
    gone += _emptied_pens(units, start, end)
    touched_text, touched_runs = _cut_units(paragraph.element, start, end, gone)
    _tidy(paragraph.element, touched_text, touched_runs, first_attrib)
    if to.element is paragraph.element and offset >= end:
        offset -= end - start
    if to.section.element is not paragraph.section.element:
        from ._document_primitives import _HP
        from .memo import carry_memos
        from .shape_position import _sections_of

        stage = paragraph.element.makeelement(f"{_HP}p", {})
        for run in runs:
            stage.append(run)
        carry_memos(stage, _sections_of(paragraph, to), to.section)
        runs = [child for child in stage if _local(child) == "run"]
        for run in runs:
            stage.remove(run)
    notes = _note_kinds(runs)
    _fit_pasted_objects(runs, to)
    _splice_runs(to, offset, runs)
    _changed(paragraph)
    _changed(to)
    _renumber_kinds(notes, paragraph.section, to.section)
    return (offset, offset + size)


# --------------------------------------------------------------------------
# set_text_preserving_runs (N11)


def set_text_preserving_runs(paragraph: "HwpxOxmlParagraph", value: str) -> None:
    """``paragraph.set_text_preserving_runs``: the one stretch that changes, in one ``hp:t``."""

    from ._paragraph_text_edit import _local as local

    _require_text(value)
    texts: list[tuple[Any, int, int]] = []
    position = 0
    for run in _runs(paragraph.element):
        for child in run:
            name = local(child)
            if name == "t":
                if any(local(inner) and local(inner) not in _TEXT_INLINE_ATOMS for inner in child):
                    raise HwpxValueError("mixed text markup cannot be edited safely",
                                         code="paragraph-mixed-text-unsupported")
                from ._document_primitives import _text_element_content

                size = len(_text_element_content(child))
                texts.append((child, position, size))
                position += size
            elif name == "tab" or _is_tab_control_element(child):
                raise HwpxValueError("tab controls require an explicit run target",
                                     code="paragraph-tab-target-required")
    old = paragraph.text
    if old == value:
        return
    if not texts:
        raise HwpxValueError("paragraph has no plain text node", code="paragraph-text-missing")
    prefix = 0
    while prefix < min(len(old), len(value)) and old[prefix] == value[prefix]:
        prefix += 1
    suffix = 0
    while (suffix < len(old) - prefix and suffix < len(value) - prefix
           and old[len(old) - suffix - 1] == value[len(value) - suffix - 1]):
        suffix += 1
    end = len(old) - suffix
    replacement = value[prefix:len(value) - suffix]
    candidates = [(node, begin) for node, begin, size in texts if begin <= prefix and end <= begin + size]
    if len(candidates) != 1:
        raise HwpxValueError(
            "text edit crosses run boundaries or has ambiguous insertion style",
            code="paragraph-text-style-ambiguous",
        )
    node, begin = candidates[0]
    if any(local(inner) in _TEXT_INLINE_ATOMS for inner in node):
        _replace_in_text(node, prefix - begin, end - begin, replacement)
    else:
        from ._paragraph_text_edit import set_text_with_tabs

        current = node.text or ""
        set_text_with_tabs(node, current[:prefix - begin] + replacement + current[end - begin:])
    _clear_paragraph_layout_cache(paragraph.element)
    paragraph.section.mark_dirty()


def _replace_in_text(node: Any, low: int, high: int, replacement: str) -> None:
    """Put *replacement* in place of characters ``[low, high)`` of the ``hp:t`` *node*, whose tabs, line
    breaks and special spaces outside them stay the elements they are."""

    units = list(_text_units(node))
    for unit in reversed(units):
        if not (unit.start < high and low < unit.end):
            continue
        if unit.kind == "text":
            text = _string(node, unit.holder)
            a, b = max(low - unit.start, 0), min(high - unit.start, unit.length)
            _set_string(node, unit.holder, text[:a] + text[b:])
        else:
            _remove_keeping_tail(unit.element)
    if not replacement:
        return
    last = None
    for unit in _text_units(node):
        if unit.end == low or (unit.start == low and unit.kind == "text" and last is None and low == 0):
            last = unit
        if unit.start >= low and unit.length:
            break
    piece = node.makeelement(node.tag, {})
    _fill_text_element(piece, replacement)
    if last is None:
        _splice_into_text(node, None, 0, piece)
    elif last.kind == "text":
        _splice_into_text(node, last.holder, min(low - last.start, last.length), piece)
    else:
        _splice_into_text(node, last.element, 0, piece)


def _text_units(node: Any) -> Iterator[_Unit]:
    position = 0
    if node.text:
        yield _Unit("text", 0, len(node.text), None, None, node, None)
        position = len(node.text)
    for inner in node:
        if _local(inner) in _TEXT_INLINE_ATOMS:
            yield _Unit("atom", position, 1, None, inner, node)
            position += 1
        if inner.tail:
            yield _Unit("text", position, len(inner.tail), None, None, node, inner)
            position += len(inner.tail)


__all__ = ["copy_range", "delete_range", "insert_text", "move_range", "set_text_preserving_runs"]


# --------------------------------------------------------------------------
# Putting a control or a mark at a place


def put_at(paragraph: Any, offset: int, element: Any) -> None:
    """Put the run child *element* -- a control or an object, taken out of where it was -- at character
    *offset* of the paragraph element *paragraph*: after the zero-width things already there, before the
    character there. In the middle of a run's text the ``hp:t`` is divided around it, in that one run, as
    Hancom writes a note or a bookmark there (``mid_text_footnote``, ``mid_text_bookmark``)."""

    parent = element.getparent()
    if parent is not None:
        parent.remove(element)
    element.tail = None
    kind, where, holder, at = _landing(paragraph, offset)
    if kind == "none":
        from ._document_primitives import _HP

        run = paragraph.makeelement(f"{_HP}run", {"charPrIDRef": "0"})
        paragraph.insert(0, run)
        run.append(element)
        return
    if kind == "new":
        where.insert(holder, element)
        return
    text, run = where, where.getparent()
    value = _string(text, holder)
    children = list(text)
    after = children[children.index(holder) + 1:] if holder is not None else children
    before = holder is not None or bool(value[:at])
    rest = bool(value[at:]) or bool(after)
    index = list(run).index(text)
    if not before:
        run.insert(index, element)  # at the start of the hp:t (or before an empty one)
        return
    if not rest:
        run.insert(index + 1, element)
        return
    right = text.makeelement(text.tag, dict(text.attrib))
    right.text = value[at:] or None
    _set_string(text, holder, value[:at])
    for child in after:
        right.append(child)
    run.insert(index + 1, element)
    run.insert(index + 2, right)


def place_created(paragraph: "HwpxOxmlParagraph", offset: int, element: Any, made_in: Any) -> None:
    """Move *element*, just written at the paragraph's end into the run *made_in*, to character *offset*
    (checked first); *made_in* goes when nothing else is left in it."""

    from ._paragraph_text_edit import require_in_document

    try:
        require_in_document(paragraph, caller="offset")
        offset = _check_offset("offset", offset, 0, len(paragraph.text))
    except Exception:
        element.getparent().remove(element)  # nothing written stays behind a refused offset
        drop_if_empty(paragraph.element, made_in)
        raise
    put_at(paragraph.element, offset, element)
    drop_if_empty(paragraph.element, made_in)
    _clear_paragraph_layout_cache(paragraph.element)


def drop_if_empty(paragraph: Any, run: Any) -> None:
    """Take *run* out of *paragraph* when it holds nothing but an empty ``hp:t`` (or nothing), and the
    paragraph keeps text elsewhere: a run made for a control that has since moved."""

    if run.getparent() is not paragraph:
        return
    children = [child for child in run if _local(child)]
    if any(_local(child) != "t" or child.text or len(child) for child in children):
        return
    others = [child for other in _runs(paragraph) if other is not run for child in other if _local(child) == "t"]
    if others or not children:
        paragraph.remove(run)


def _pen_overlaps(units: list[_Unit], start: int, end: int) -> bool:
    total = sum(unit.length for unit in units)
    for begin, finish in _pen_pairs(units).values():
        if begin is None:
            continue
        low, high = begin.start, finish.start if finish is not None else total
        if low < end and start < high:
            return True
    return False


def highlight_range(paragraph: "HwpxOxmlParagraph", start: int, end: int, color: str) -> None:
    """Mark characters ``[start, end)`` with a highlight: ``hp:markpenBegin`` right before character *start*
    and ``hp:markpenEnd`` right after character ``end - 1``, each inside the ``hp:t`` holding that character
    -- in two runs when the range crosses one (``highlight_across_runs``)."""

    from ._document_primitives import _HP

    first, start, end = check_highlight_range(paragraph, start, end)
    begin = paragraph.element.makeelement(f"{_HP}markpenBegin", {"color": color})
    _put_mark_before(first, start - first.start if first.kind == "text" else 0, begin)
    last = next(u for u in _units(paragraph.element) if u.length and u.start <= end - 1 < u.end)
    finish = paragraph.element.makeelement(f"{_HP}markpenEnd", {})
    if last.kind == "text":
        _put_mark_before(last, end - last.start, finish)
    else:
        element = last.element
        finish.tail, element.tail = element.tail, None
        holder = element.getparent()
        holder.insert(list(holder).index(element) + 1, finish)
    paragraph.section.mark_dirty()


def check_highlight_range(paragraph: "HwpxOxmlParagraph", start: Any, end: Any) -> "tuple[_Unit, int, int]":
    """A highlight's range checked before anything is written: (the unit of its first character, start, end)."""

    length = len(paragraph.text)
    start = _check_offset("start", start, 0, length)
    end = _check_offset("end", end, start, length)
    if start == end:
        raise HwpxValueError("a highlight needs at least one character", code="paragraph-range-invalid",
                             context={"start": start, "end": end},
                             suggestion="Pass end > start (positions count as paragraph.text does).")
    units = list(_units(paragraph.element))
    if _pen_overlaps(units, start, end):
        raise HwpxValueError(
            f"characters {start}..{end} overlap a highlight already there",
            code="paragraph-range-splits-mark",
            context={"start": start, "end": end},
            suggestion="Remove that highlight first, or highlight a range beside it.",
        )
    first = next(u for u in units if u.length and u.start <= start < u.end)
    last = next(u for u in units if u.length and u.start <= end - 1 < u.end)
    for unit in (first, last):
        if unit.kind not in ("text", "atom"):
            raise HwpxValueError(
                "a highlight starts and ends inside the text: the range starts or ends at a tab written beside "
                "the text or inside an element holding text of its own",
                code="paragraph-range-splits-mark",
                context={"start": start, "end": end, "at": unit.kind},
                suggestion="Start or end the range one character further in.",
            )
    return first, start, end


def check_field_range(paragraph: "HwpxOxmlParagraph", start: Any, end: Any) -> "tuple[int, int] | None":
    """``add_form_field(start=, end=)``'s range checked before anything is written (``None`` without one)."""

    from ._paragraph_text_edit import require_in_document

    require_in_document(paragraph, caller="add_form_field")
    if start is None and end is None:
        return None
    if start is None or end is None:
        raise HwpxValueError("a field's range needs both start and end", code="paragraph-range-invalid",
                             context={"start": repr(start), "end": repr(end)},
                             suggestion="Pass start and end (positions count as paragraph.text does).")
    length = len(paragraph.text)
    start = _check_offset("start", start, 0, length)
    end = _check_offset("end", end, start, length)
    _held(list(_units(paragraph.element)), start, end)  # one end of another field inside: refused
    return (start, end)


def wrap_in_field(
    paragraph: "HwpxOxmlParagraph", span: "tuple[int, int]", begin: Any, finish: Any, prompt: Any = None
) -> None:
    """Move a new field's begin and end controls (each with the run made for it) to the ends of *span*.

    *prompt*, the 안내문 run of a field around no character, goes right after the begin control: the run
    holding the begin is divided there, the end control and what follows it going to a run of its own
    after the prompt, as Hancom saves an empty click-here field (``count_click_here_between``)."""

    start, end = span
    put_at(paragraph.element, start, begin[0])
    put_at(paragraph.element, end, finish[0])
    if prompt is not None:
        paragraph.element.remove(prompt)
        holder = begin[0].getparent()
        after = list(holder)[list(holder).index(begin[0]) + 1:]
        index = list(paragraph.element).index(holder)
        if after:
            rest = holder.makeelement(holder.tag, dict(holder.attrib))
            rest.extend(after)
            paragraph.element.insert(index + 1, rest)
        paragraph.element.insert(index + 1, prompt)
    for _control, run in (begin, finish):
        drop_if_empty(paragraph.element, run)
    _clear_paragraph_layout_cache(paragraph.element)


def _note_target(note: Any, paragraph: Any, offset: Any) -> int:
    from .paragraph import HwpxOxmlParagraph
    from .shape_position import paragraph_box

    if not isinstance(paragraph, HwpxOxmlParagraph):
        raise HwpxTypeError(f"paragraph must be a paragraph object; got {type(paragraph).__name__}",
                            code="paragraph-invalid-type", context={"type": type(paragraph).__name__},
                            suggestion="Pass the paragraph to put the note in, e.g. doc.paragraphs[i].")
    from ._paragraph_text_edit import in_document, require_in_document

    require_in_document(paragraph, caller="note", role="paragraph to put the note in")
    if not in_document(note.element, note.paragraph.section):
        raise HwpxValueError(
            "the note is not in the document any more (it was removed, or sits in something taken out)",
            code="paragraph-not-in-document",
            context={"caller": "note", "role": "note"},
            suggestion="Take the note again from the document (doc.notes.footnotes ...).",
        )
    if paragraph.section.document is not note.paragraph.section.document:
        raise HwpxValueError(
            "a note moves and copies within its document",
            code="note-other-document-unsupported",
            suggestion="Copy the range holding it into the other document: paragraph.copy_range(...).",
        )
    box = paragraph_box(paragraph.element, paragraph.section.element)
    if not hasattr(paragraph.section, "_section_properties_element"):
        box = "master_page"  # also a cell or a text box on one: add_footnote refuses a master page too
    if box in ("note", "header_footer", "memo", "other", "master_page"):
        raise HwpxValueError(
            "a footnote or an endnote goes into the body, a cell, a text box or a caption",
            code="paragraph-move-place-unsupported",
            context={"box": box},
            suggestion="Pick a paragraph of the body, a cell or a text box.",
        )
    length = len(paragraph.text)
    return length if offset is None else _check_offset("offset", offset, 0, length)


def _fit_pasted_objects(runs: list[Any], to: "HwpxOxmlParagraph") -> None:
    """Place each floating object the runs carry into a cell, text box, note or caption as Hancom pastes one
    there (:func:`~hwpx.oxml.shape_position.pasted_placement`), the rule ``shape.copy_to`` and ``move_to``
    follow: a range carried a page-measured object there as it was."""

    from .shape_position import _PASTE_FITTED, _Z_ORDERED_SET, paragraph_box, pasted_placement

    if paragraph_box(to.element, to.section.element) not in _PASTE_FITTED:
        return
    for run in runs:
        for child in run:
            if child.tag not in _Z_ORDERED_SET or _local(child) == "tbl":
                continue
            changes = pasted_placement(child)
            position = child.find(f"{child.tag.rsplit('}', 1)[0]}}}pos")
            if changes and position is not None:
                for name, value in changes.items():
                    position.set(name, value)


def _note_kinds(runs: list[Any]) -> set[str]:
    """The kinds of note (``footNote``, ``endNote``) the runs *runs* hold."""

    return {_local(node) for run in runs for node in run.iter() if _local(node) in ("footNote", "endNote")}


def _renumber_kinds(kinds: set[str], *sections: Any) -> None:
    """Write the numbers of the notes of *kinds* again, in document order, as a single note moved or copied
    gets them: a range holding notes left the stored numbers repeated or out of order."""

    from .note_authoring import renumber_notes

    for tag in sorted(kinds):
        for section in {id(section): section for section in sections}.values():
            renumber_notes(section, tag)


def _renumber_after(note_element: Any, *sections: Any) -> None:
    from .note_authoring import renumber_notes

    tag = _local(note_element)
    for section in {id(section): section for section in sections}.values():
        renumber_notes(section, tag)


def move_note(note: Any, paragraph: Any, offset: Any) -> None:
    """``note.move_to``."""

    offset = _note_target(note, paragraph, offset)
    if any(node is paragraph.element for node in note.element.iter()):
        # A cell or a text box in the note's own text: the place check sees "a cell" and lets it by, and
        # putting the note there took it out of the document first and then failed on lxml's "cannot
        # append parent to itself" -- the note and what it held were gone from the saved file.
        raise HwpxValueError(
            "a note cannot move into its own text (a cell or a text box inside it)",
            code="note-move-into-itself",
            context={"caller": "note"},
            suggestion="Pick a paragraph outside the note, or copy it there with copy_to().",
        )
    control = note.element.getparent()
    old_run, old_paragraph = control.getparent(), note.paragraph
    put_at(paragraph.element, offset, control)
    if old_run.getparent() is not None:
        _merge_text_siblings(old_run)  # the two hp:t the note stood between are one again
    drop_if_empty(old_paragraph.element, old_run)
    _changed(old_paragraph)
    _changed(paragraph)
    note.paragraph = paragraph
    _renumber_after(note.element, old_paragraph.section, paragraph.section)


def copy_note(note: Any, paragraph: Any, offset: Any) -> Any:
    """``note.copy_to``."""

    from ._document_primitives import _object_id
    from .memo import HwpxOxmlNote

    offset = _note_target(note, paragraph, offset)
    control = deepcopy(note.element.getparent())
    copy = next(child for child in control if _local(child) == _local(note.element))
    fresh = _object_id(paragraph.section._ids)
    # Hancom writes a note's instance id as instId (all 138 notes of tests/fixtures/hancom_saved); other writers
    # and python-hwpx 6.6 and before wrote instid. The copy gets a new one in whichever spelling it carries --
    # leaving one behind gave two notes of one document the same instance id.
    spellings = [name for name in ("instId", "instid") if name in copy.attrib] or ["instId"]
    for name in spellings:
        copy.set(name, fresh)
    for node in copy.iter():
        if _local(node) == "p":
            _clear_paragraph_layout_cache(node)
    # A memo anchored in the note's text is a memo of its own (its number and id), as one in a copied
    # paragraph: the two were one memo to Hancom. First, since a 6.x memo's text comes into its field
    # here and may hold fields ...
    from ._paragraph_text_edit import renumber_copied_fields
    from .memo import renew_copied_memos

    document = paragraph.section.document
    renew_copied_memos(copy, list(document.sections) if document is not None else [paragraph.section],
                       paragraph.section)
    # ... and a field in the note's text (a 누름틀, a hyperlink) gets a new id pair, as a copied
    # paragraph's or table's does: the copy kept the original's, and the two fields of one id could not
    # be told apart (``field-ambiguous`` on filling either).
    from ._document_primitives import _HP as hp

    in_document: set[str] = set()  # the field ids in use: a new one is none of them
    if next(copy.iter(f"{hp}fieldBegin"), None) is not None:
        owners: list[Any] = ([*document.sections, *getattr(document, "master_pages", ())]
                             if document is not None else [paragraph.section])
        in_document = {str(node.get("id")) for owner in owners for node in owner.element.iter(f"{hp}fieldBegin")}
    renumber_copied_fields(copy, ids=paragraph.section._ids, avoid=in_document)
    put_at(paragraph.element, offset, control)
    # The objects in the note's text are copies too: each gets an id no other object has and goes over the
    # others, as a copied object does (shape.copy_to); they kept the original's id and zOrder before.
    from .shape_position import _object_nodes, stack_new_object

    for node in list(_object_nodes(copy)):
        stack_new_object(node, paragraph.section)
    _changed(paragraph)
    # the copy's kind, and the kinds of the notes in its text (a footnote in a copied endnote kept its
    # number, so two footnotes had one)
    from .note_authoring import renumber_notes_holding

    renumber_notes_holding(paragraph.section, (control,))
    return HwpxOxmlNote(copy, paragraph)
