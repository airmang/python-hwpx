# SPDX-License-Identifier: Apache-2.0
"""Small helpers for editing the text inside ``hp:t`` and for taking a paragraph out of its list or
moving it to another place in the same document."""

from __future__ import annotations

import xml.etree.ElementTree as ET
import functools
import itertools
import inspect
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Callable, Iterable, cast

from ..errors import HwpxValueError
from ._document_primitives import (
    _HP_NS,
    _TEXT_MARK_SPLIT_RE,
    _child_tag_like,
    _fill_text_element,
    _is_tab_control_element,
    _require_text,
    _sanitize_text,
)
from .namespaces import tag_local_name

if TYPE_CHECKING:
    from ._document_primitives import IdSource
    from ..objects.results import Alignment, LineSegment, LineSpacing, NumberingInfo
    from .header import Bullet, Style
    from .paragraph import HwpxOxmlParagraph
    from .run import HwpxOxmlRun


def sanitize_keeping_tabs(value: str) -> str:
    """``_sanitize_text``, but keep tabs for :func:`set_text_with_tabs`."""

    _require_text(value)
    return "\t".join(_sanitize_text(part) for part in value.split("\t"))


def checked_tab_widths(text: str, tab_widths: "Sequence[int] | None") -> "tuple[int, ...]":
    """*tab_widths* checked against the tabs of *text* (``add_run(tab_widths=)``)."""

    if tab_widths is None:
        return ()
    widths = tuple(tab_widths)
    count = text.count("\t")
    if len(widths) != count or any(isinstance(w, bool) or not isinstance(w, int) or not 0 <= w < 2**31
                                   for w in widths):
        raise HwpxValueError(
            f"tab_widths needs one whole HWPUNIT width (0 to 2**31-1) for each of the {count} tab(s) of the text;"
            f" got {widths!r}",
            code="paragraph-tab-widths",
            context={"tabs": count, "widths": [repr(w) for w in widths]},
            suggestion="Pass one width for each tab, in order, or leave tab_widths out to let Hancom work them out.",
        )
    return widths


def write_tab_widths(run_element: Any, widths: "Sequence[int]") -> None:
    """Write *widths* on the tabs of *run_element*, in order, in Hancom's saved form
    (``width``, ``leader="0"``, ``type="1"``; ``add_run(tab_widths=)``)."""

    tabs = [node for node in run_element.iter() if _local(node) == "tab"]
    for tab, width in zip(tabs, widths):
        tab.set("width", str(width))
        tab.set("leader", "0")
        tab.set("type", "1")


def set_text_with_tabs(text_element: ET.Element, value: str) -> None:
    """Make *value* the whole content of the ``hp:t`` *text_element*.

    Each tab becomes an ``hp:tab`` and each line break an ``hp:lineBreak`` inside it, the way Hancom writes
    them. Elements already inside it (line breaks, tabs, spaces, marks) go, with the text after them: they
    belong to the old value.
    """

    for child in list(text_element):
        text_element.remove(child)
    _fill_text_element(text_element, value)


def text_marks_as_elements(text_element: ET.Element) -> bool:
    """Write each tab or line-break character left in the ``hp:t`` *text_element* as the element
    Hancom writes for it (``hp:tab``, ``hp:lineBreak``), the way :func:`set_text_with_tabs` does.

    For edits that put characters into the text already there (find and replace, a model applied
    back) instead of filling the element: the rest of the element stays as it is. Returns whether
    anything changed.
    """

    tab_tag = _child_tag_like(text_element, "tab", _HP_NS)
    break_tag = _child_tag_like(text_element, "lineBreak", _HP_NS)
    changed = False
    position = 0  # where the elements for the text in front of the next child go
    for holder in (None, *list(text_element)):
        if holder is not None:
            position += 1
        value = (text_element.text if holder is None else holder.tail) or ""
        parts = _TEXT_MARK_SPLIT_RE.split(value)
        if len(parts) == 1:
            continue
        changed = True
        if holder is None:
            text_element.text = parts[0]
        else:
            holder.tail = parts[0]
        for mark, segment in zip(parts[1::2], parts[2::2]):
            element = text_element.makeelement(tab_tag if mark == "\t" else break_tag, {})
            element.tail = segment
            text_element.insert(position, element)
            position += 1
    return changed


def text_marks_as_elements_in(root: ET.Element) -> bool:
    """:func:`text_marks_as_elements` for every ``hp:t`` at or under *root*."""

    changed = False
    for node in list(root.iter()):
        if isinstance(node.tag, str) and tag_local_name(node.tag) == "t":
            changed = text_marks_as_elements(node) or changed
    return changed


def clear_text_element(text_element: ET.Element) -> None:
    """Empty an ``hp:t``: its text, and the elements inside it with the text after them."""

    for child in list(text_element):
        text_element.remove(child)
    if text_element.text:
        text_element.text = ""


def paragraph_container(element: ET.Element, section_element: ET.Element) -> ET.Element | None:
    """The element that directly holds the paragraph *element*: its section or a ``hp:subList``."""

    if hasattr(element, "getparent"):
        return element.getparent()
    return next((node for node in section_element.iter() if any(child is element for child in node)), None)


#: What holds a ``hp:subList`` paragraph list, as a refusal names it.
_SUBLIST_OWNERS = {"tc": "cell", "header": "header", "footer": "footer"}

#: What an ``hp:ctrl`` holds when it sets up the pages of a section rather than marking a place in
#: the text: columns, a header or footer, page numbering, hiding, a new number.
PAGE_LEVEL_CONTROLS = frozenset({"colPr", "header", "footer", "pageNum", "pageHiding", "newNum", "pageNumCtrl"})


def is_section_setting(child: ET.Element) -> bool:
    """Whether the run child *child* is part of a section's settings: its ``hp:secPr``, or an
    ``hp:ctrl`` holding only page-level controls (:data:`PAGE_LEVEL_CONTROLS`)."""

    name = tag_local_name(child.tag) if isinstance(child.tag, str) else ""
    if name == "secPr":
        return True
    return name == "ctrl" and len(child) > 0 and all(
        isinstance(inner.tag, str) and tag_local_name(inner.tag) in PAGE_LEVEL_CONTROLS for inner in child
    )


def section_setting_runs(paragraph: ET.Element) -> list[tuple[ET.Element, list[ET.Element]]]:
    """The runs of *paragraph* holding section settings, each with those children.

    Empty unless the paragraph holds an ``hp:secPr``: only the paragraph that starts a section
    carries its settings. Its page-level controls (columns, header, footer, page numbering) go
    with it, wherever in the paragraph Hancom wrote them.
    """

    runs = [child for child in paragraph if isinstance(child.tag, str) and tag_local_name(child.tag) == "run"]
    if not any(isinstance(child.tag, str) and tag_local_name(child.tag) == "secPr" for run in runs for child in run):
        return []
    found = []
    for run in runs:
        settings = [child for child in run if is_section_setting(child)]
        if settings:
            found.append((run, settings))
    return found


def split_column_controls(paragraph: ET.Element) -> None:
    """Give a column layout (``hp:colPr``) that shares its ``hp:ctrl`` with other controls (a page-number
    restart, a field begin -- some Hancom files do) a ctrl of its own, right before, so it reads as a section
    setting; the others stay where they were."""

    for run in [child for child in paragraph if _local(child) == "run"]:
        for ctrl in [child for child in run if _local(child) == "ctrl" and not is_section_setting(child)]:
            columns = [child for child in ctrl if _local(child) == "colPr"]
            if not columns:
                continue
            own = ctrl.makeelement(ctrl.tag, dict(ctrl.attrib))
            for column in columns:
                ctrl.remove(column)
                own.append(column)
            run.insert(list(run).index(ctrl), own)


def move_section_settings(source: ET.Element, target: ET.Element) -> bool:
    """Move the section settings of the paragraph *source* to the front of the paragraph *target*.

    A run holding nothing else moves whole; from a run holding text or objects too, only the
    settings move, into a new run with the same attributes. Both paragraphs lose their line
    layout cache: the controls in front of the text (8 positions each in ``lineseg/@textpos``)
    shift every position the cache records, in *target* by coming and in *source* by going.
    Returns whether anything moved.
    """

    if not section_setting_runs(source):
        return False
    split_column_controls(source)
    found = section_setting_runs(source)
    position = 0
    for run, settings in found:
        if len(settings) == len(run):
            source.remove(run)
            moved = run
        else:
            moved = run.makeelement(run.tag, dict(run.attrib))
            for child in settings:
                run.remove(child)
                moved.append(child)
        target.insert(position, moved)
        position += 1
    for paragraph in (target, source):
        for cache in [child for child in paragraph
                      if isinstance(child.tag, str) and tag_local_name(child.tag).lower() == "linesegarray"]:
            paragraph.remove(cache)
    return True


def _local(element: ET.Element) -> str:
    return tag_local_name(element.tag) if isinstance(element.tag, str) else ""


def blank_settings_paragraph(paragraph: ET.Element) -> bool:
    """Whether *paragraph* is a blank line that only holds section settings: its runs hold
    nothing but :func:`is_section_setting` children and empty ``hp:t``, and it holds nothing
    besides runs and a line cache (the first paragraph :meth:`HwpxDocument.new` makes)."""

    if any(_local(child) not in ("run", "linesegarray") for child in paragraph):
        return False
    children = [child for run in paragraph if _local(run) == "run" for child in run]
    settings = [child for child in children if is_section_setting(child)]
    rest = [child for child in children if not is_section_setting(child)]
    return bool(settings) and all(_local(child) == "t" and not (child.text or "") and not len(child) for child in rest)


def take_over_paragraph(kept: ET.Element, added: ET.Element) -> None:
    """Give the blank settings paragraph *kept* the content of *added*.

    *kept* keeps its runs of section settings and its ``id``; its other runs and its line
    cache go. It takes the attributes of *added* (paragraph shape, style...) and its
    children, behind the settings. *added* is left empty; the caller removes it.
    """

    for child in list(kept):
        if _local(child) == "run":
            for grand in list(child):
                if not is_section_setting(grand):
                    child.remove(grand)
        if _local(child) != "run" or not len(child):
            kept.remove(child)
    for name in [name for name in kept.attrib if name != "id" and name not in added.attrib]:
        del kept.attrib[name]
    for name, value in added.attrib.items():
        if name != "id":
            kept.set(name, value)
    for child in list(added):
        if _local(child) != "linesegarray":
            kept.append(child)


def _next_paragraph(parent: ET.Element, element: ET.Element) -> ET.Element | None:
    seen = False
    for child in parent:
        if child is element:
            seen = True
        elif seen and isinstance(child.tag, str) and tag_local_name(child.tag) == "p":
            return child
    return None


def _leave_out(root: ET.Element, node: ET.Element) -> None:
    """Take *node* out of *root*, with the ``hp:ctrl`` that held nothing else (Hancom does not open a
    document with an empty one). Text after it stays."""

    holders = {child: holder for holder in root.iter() for child in holder}
    while node in holders:
        holder = holders[node]
        position = list(holder).index(node)
        if node.tail:
            if position:
                holder[position - 1].tail = (holder[position - 1].tail or "") + node.tail
            else:
                holder.text = (holder.text or "") + node.tail
        holder.remove(node)
        if tag_local_name(holder.tag) != "ctrl" or len(holder) or holder is root:
            return
        node = holder


def renumber_copied_fields(copy: ET.Element, *, ids: "IdSource | None",
                           taken: "set[str] | None" = None, avoid: "set[str] | None" = None,
                           halves: bool = False) -> int:
    """Give each field whose begin and end are both inside *copy* a new id pair.

    A field's begin and end pair by id (``hp:fieldBegin/@id``, ``hp:fieldEnd/@beginIDRef``); a copy
    keeping them leaves two fields of one id, which readers and form filling cannot tell apart.
    A ``fieldid`` equal to the old id follows it. A field reaching outside *copy* is left as it is,
    unless *halves*: the copy then stands beside what it was copied from, which keeps the field whole
    (``paragraph.insert_after()`` with no text), so a begin whose end is outside the copy is renumbered
    alone -- kept under its id it was a second begin for the one end -- and an end whose begin is
    outside is left out of the copy. Content brought in piece by piece is not such a copy: the end
    that arrives in a later piece belongs to the begin that arrived in an earlier one.
    An end goes to the begin of its id that is open in front of it (the innermost, when fields of one
    id nest): *copy* may hold the same field more than once (one paragraph copied twice in one call),
    and the first begin took every end of the id then, leaving the second copy's begin with the first
    copy's end. An end in front of its begin goes to the first begin of its id, as before.
    With *taken* (the field ids the place the copy goes to already has) only a field whose id is taken,
    or met a second time in *copy*, gets a new pair: content brought from another document keeps the
    ids it is known by where nothing there has them. A new id is never one of *avoid* (ids in use
    where the copy goes): a document holding fields brought from another one made with the same seed
    was handed one of their ids.
    Returns how many fields were renumbered.
    """

    from ._document_primitives import _object_id

    hp_begin, hp_end = f"{{{_HP_NS}}}fieldBegin", f"{{{_HP_NS}}}fieldEnd"
    groups: list[tuple[ET.Element, list[ET.Element]]] = []
    still_open: dict[str, list[list[ET.Element]]] = {}  # per id: the begins not yet ended, innermost last
    last_ended: dict[str, list[ET.Element]] = {}  # per id: the begin that took the last end
    early: dict[str, list[ET.Element]] = {}  # per id: ends met before any begin of the id
    for node in copy.iter():
        if node.tag == hp_begin and node.get("id"):
            ends: list[ET.Element] = []
            still_open.setdefault(str(node.get("id")), []).append(ends)
            groups.append((node, ends))
        elif node.tag == hp_end:
            named = node.get("beginIDRef") or ""
            if still_open.get(named):
                taking = still_open[named].pop()  # the innermost begin of the id that is still open
                last_ended[named] = taking
            elif named in last_ended:
                taking = last_ended[named]  # a further end of a field that has one already
            else:
                taking = early.setdefault(named, [])  # in front of its begin
            taking.append(node)
    for begin, ends in groups:  # an end in front of its begin goes to the first begin left without one
        waiting = early.get(str(begin.get("id")))
        if waiting:
            ends.extend(waiting)
            waiting.clear()
    renumbered = 0
    met: set[str] = set()
    # ids that stay in use: those where the copy goes, and those the copy itself holds (one of them may
    # be kept, and the id source of a document made with the same seed hands out the same numbers)
    in_use = set(taken or ()) | set(avoid or ()) | {str(begin.get("id")) for begin, _ in groups}
    if halves:
        for lone in early.values():
            for node in lone:
                _leave_out(copy, node)
    for begin, ends in groups:
        if not ends and not halves:
            continue
        old = str(begin.get("id"))
        if taken is not None and old not in taken and old not in met:
            met.add(old)
            continue  # no field where it goes has this id: it keeps it
        met.add(old)
        new_id = _object_id(ids)
        # A source handing out ids of its own can meet each id in use once (a document that took in the
        # fields of another one made with the same seed meets every one of them). One that still hands
        # out an id in use after that repeats itself: the id is then the lowest number not in use.
        for _ in range(len(in_use) + 1):
            if new_id not in in_use:
                break
            new_id = _object_id(ids)
        else:
            new_id = next(number for number in map(str, itertools.count(1)) if number not in in_use)
        in_use.add(new_id)
        for node in (begin, *ends):
            node.set("id" if node is begin else "beginIDRef", new_id)
            if node.get("fieldid") == old:
                node.set("fieldid", new_id)
        renumbered += 1
    return renumbered


def insert_paragraph_beside(
    element: ET.Element, section_element: ET.Element, text: str | None, *, after: bool, ids: "IdSource | None"
) -> ET.Element:
    """Put a new paragraph next to the paragraph *element* (in its section, cell, header...) and
    return it.

    *text* ``None`` copies *element* (fresh ids, field ids among them, and no line caches) without
    its section settings; otherwise the new paragraph holds *text* in *element*'s paragraph shape,
    style and first run's character shape. Put in front of the paragraph that starts a section,
    it starts the section instead: the section's settings move to it.
    """

    from ._document_primitives import (
        paragraph_attributes, _append_text_with_tabs, _clone_paragraph_element, _paragraph_id,
    )

    parent = paragraph_container(element, section_element)
    if parent is None:
        raise HwpxValueError(
            "이 단락은 문서에서 빠져 있어 옆에 단락을 넣을 수 없습니다.",
            code="paragraph-not-in-document",
            suggestion="문서의 doc.paragraphs 에서 단락을 다시 가져오세요.",
        )
    if text is None:
        new = _clone_paragraph_element(element, ids=ids)
        renumber_copied_fields(new, ids=ids, halves=True)  # beside the paragraph it copies, which keeps its fields
        for run, settings in section_setting_runs(new):
            for child in settings:
                run.remove(child)
            if len(run) == 0:
                new.remove(run)
    else:
        text_run = next((child for child in element if _local(child) == "run" and (
            not len(child) or not all(is_section_setting(grand) for grand in child))), None)
        new = element.makeelement(element.tag, paragraph_attributes(_paragraph_id(ids)))
        for name in ("paraPrIDRef", "styleIDRef"):
            if element.get(name) is not None:
                new.set(name, element.get(name) or "")
        run = new.makeelement(f"{{{_HP_NS}}}run", {
            "charPrIDRef": (text_run.get("charPrIDRef") if text_run is not None else None) or "0"})
        new.append(run)
        _append_text_with_tabs(run, text)
    index = list(parent).index(element)
    parent.insert(index + 1 if after else index, new)
    if not after and parent is section_element:
        move_section_settings(element, new)
    return new


def remove_paragraph_element(element: ET.Element, section_element: ET.Element) -> bool:
    """Take the paragraph *element* out of the section or ``hp:subList`` holding it.

    Returns ``False`` when it is already gone. The last paragraph of its list
    stays: HWPX needs one ``<hp:p>`` per section, and Hancom cannot open a cell,
    header or footer whose paragraph list is empty.

    The paragraph that starts a section holds the section's settings (``hp:secPr``: paper,
    margins, numbering start; and its columns, header, footer and page numbering). Those move
    to the front of the next paragraph, which then starts the section. A paragraph holding them
    with no paragraph after it is refused (``paragraph-remove-section-settings``).
    """

    parent = paragraph_container(element, section_element)
    if parent is None:
        return False
    if len(parent.findall(f"{{{_HP_NS}}}p")) > 1 and section_setting_runs(element):
        following = _next_paragraph(parent, element)
        if following is None:
            raise HwpxValueError(
                "이 단락은 구역 설정(용지·여백·단·머리말·꼬리말·쪽 번호)을 담고 있고 뒤에 단락이 없어 지울 수 없습니다.",
                code="paragraph-remove-section-settings",
                context={"container": "section"},
                suggestion='단락을 지우지 말고 글을 비우세요(paragraph.text = "").',
            )
        move_section_settings(element, following)
    if len(parent.findall(f"{{{_HP_NS}}}p")) <= 1:
        if parent is section_element:
            container = "section"
        else:
            owner = paragraph_container(parent, section_element)
            name = tag_local_name(owner.tag) if owner is not None else "subList"
            container = _SUBLIST_OWNERS.get(name, name)
        raise HwpxValueError(
            "섹션과 셀·머리말·꼬리말에는 최소 하나의 단락이 필요합니다. "
            "마지막 단락은 삭제할 수 없습니다.",
            code="paragraph-remove-last",
            context={"container": container},
            suggestion='마지막 단락은 지우지 말고 글을 비우세요(paragraph.text = "").',
        )
    parent.remove(element)
    return True


def remove_paragraph(paragraph: Any) -> None:
    """``paragraph.remove()``: take the paragraph out (:func:`remove_paragraph_element`), mark its section
    and number the notes again whose count it changed -- the notes after the ones it held, or after a
    restart (``hp:newNum``) it held, kept the numbers they were saved with."""

    from .note_authoring import note_kinds_in_document, renumber_note_kinds

    section = paragraph.section
    note_kinds = note_kinds_in_document(section, paragraph.element)
    if remove_paragraph_element(paragraph.element, section.element):
        section.mark_dirty()
        renumber_note_kinds(section, note_kinds)


def _section_holding(element: Any, sections: list[Any]) -> Any:
    """The section of *sections* whose tree holds *element*, or ``None``."""

    if hasattr(element, "getparent"):
        root = element
        while (parent := root.getparent()) is not None:
            root = parent
        return next((section for section in sections if section.element is root), None)
    return next((section for section in sections if any(node is element for node in section.element.iter())), None)


def live_holder(element: Any, held: Any) -> Any:
    """The section (or master page) of the document *held* belongs to whose tree holds *element* now.

    *held* is the section a wrapper object was made with. While *element* stays in it, that is *held*;
    once a move took it into another section of the same document (a table, text box or note moved, a
    paragraph moved with ``move_after``), it is that section, so an edit through an object taken before
    the move marks the section that is saved. *held* again when *element* is in none of the document's
    sections and master pages (taken out, or in a removed section): the edits that write on the
    document's side refuse such an object (``paragraph-not-in-document``)."""

    if held is None or not hasattr(element, "getparent"):
        return held
    top = element
    while (parent := top.getparent()) is not None:
        top = parent
    if getattr(held, "element", None) is top:
        return held
    document = getattr(held, "document", None)
    if document is None:
        return held
    for holder in (*document.sections, *getattr(document, "master_pages", ())):
        if holder.element is top:
            return holder
    return held


def _live_paragraph(self: Any) -> "HwpxOxmlParagraph":
    held = self.__dict__.get("_held_paragraph")
    element = self.element
    if held is None or not hasattr(element, "getparent"):
        return cast("HwpxOxmlParagraph", held)
    node = element.getparent()
    nearest = None
    while node is not None:
        if node is held.element:
            return cast("HwpxOxmlParagraph", held)
        if nearest is None and _local(node) == "p":
            nearest = node
        node = node.getparent()
    if nearest is None:  # taken out with no paragraph around it: keep the one it was taken from
        return cast("HwpxOxmlParagraph", held)
    moved = type(held)(nearest, held.section)
    self.__dict__["_held_paragraph"] = moved
    return cast("HwpxOxmlParagraph", moved)


def _set_live_paragraph(self: Any, value: "HwpxOxmlParagraph") -> None:
    self.__dict__["_held_paragraph"] = value


live_paragraph = property(
    _live_paragraph,
    _set_live_paragraph,
    doc="The paragraph holding it now. Moved out of the paragraph it was taken from (a range moved to "
        "another paragraph or section), it is the paragraph it went to, so an edit through it marks the "
        "section that is saved.",
)


class LiveSection:
    """``paragraph.section``: the section holding the paragraph now (see :func:`live_holder`), not the one
    it was taken from. A table, text box or note moved to another section takes its paragraphs along; an
    edit through a paragraph object taken before the move then marks the section that is saved."""

    def __get__(self, obj: Any, owner: Any = None) -> Any:
        if obj is None:
            raise AttributeError("section")  # a field without a default
        held = obj.__dict__["_held_section"]
        current = live_holder(obj.element, held)
        if current is not held:
            obj.__dict__["_held_section"] = current
        return current

    def __set__(self, obj: Any, value: Any) -> None:
        obj.__dict__["_held_section"] = value


def in_document(element: Any, holder: Any) -> bool:
    """True when the element *element* hangs in the live tree of the document *holder* (a section or a
    master page object) belongs to: under one of its sections or master pages, not under a table, note,
    text box or paragraph taken out of it, nor under a section removed from it."""

    document = getattr(holder, "document", None)
    if document is not None:
        roots = [section.element for section in document.sections]
        roots += [page.element for page in getattr(document, "master_pages", ())]
    else:
        roots = [holder.element]
    if not hasattr(element, "getparent"):  # xml.etree: no way up, so down from the roots
        return any(node is element for root in roots for node in root.iter())
    top = element
    while (parent := top.getparent()) is not None:
        top = parent
    return any(top is root for root in roots)


def require_in_document(paragraph: Any, *, caller: str, role: str = "paragraph") -> None:
    """Refuse (``paragraph-not-in-document``) to edit a paragraph that is no longer in its document --
    one of a table, note or text box taken out, or of a removed section. Without this an edit reported
    success while what it moved went with the piece taken out: nothing of it was saved."""

    if not in_document(paragraph.element, paragraph.section):
        raise HwpxValueError(
            f"the {role} is not in the document any more (it sits in a table, note or text box taken out, or "
            "in a removed section)",
            code="paragraph-not-in-document",
            context={"caller": caller, "role": role},
            suggestion="Take the paragraph again from the document (doc.paragraphs, cell.paragraphs ...).",
        )


def resolve_paragraph_in(source: Any, paragraph: Any, *, caller: str) -> Any:
    """*paragraph* -- a paragraph object or its index in the document's paragraphs (``doc.paragraphs``)
    -- as a paragraph of the document the paragraph object *source* belongs to, its ``section`` the
    section holding it (a paragraph of a cell, a text box, a note, a header or a footer too).

    Refused: a paragraph of another document, of a master page or one taken out
    (``paragraph-not-in-document``), an index out of range (``paragraph-not-found``), anything else
    (``paragraph-invalid-type``).
    """

    from ..errors import HwpxLookupError, HwpxTypeError
    from .paragraph import HwpxOxmlParagraph

    section = source.section
    document = section.document
    sections = list(document.sections) if document is not None else [section]
    if isinstance(paragraph, int) and not isinstance(paragraph, bool):
        paragraphs = document.paragraphs if document is not None else section.paragraphs
        count = len(paragraphs)
        if not -count <= paragraph < count:
            raise HwpxLookupError(
                f"paragraph index {paragraph} is out of range ({count} paragraphs)",
                code="paragraph-not-found",
                context={"caller": caller, "requested": paragraph, "count": count},
                suggestion=f"Pass an index in 0..{count - 1} of doc.paragraphs, or the paragraph object itself.",
            )
        return paragraphs[paragraph]
    if not isinstance(paragraph, HwpxOxmlParagraph):
        raise HwpxTypeError(
            f"paragraph must be a paragraph or its index; got {type(paragraph).__name__}",
            code="paragraph-invalid-type",
            context={"caller": caller, "type": type(paragraph).__name__},
            suggestion="Pass doc.paragraphs[i], cell.paragraphs[i] (any paragraph of this document) or an index.",
        )
    holder = _section_holding(paragraph.element, sections)
    if holder is None:
        raise HwpxValueError(
            "the paragraph is not in this document (another document's, a master page's, or one taken out)",
            code="paragraph-not-in-document",
            context={"caller": caller},
            suggestion="Pass a paragraph of the same document. To bring content from another document, insert "
                       "its paragraphs with hwpx.tools.document_merge.insert_document.",
        )
    return paragraph if holder is paragraph.section else HwpxOxmlParagraph(paragraph.element, holder)


def _paragraph_lists(paragraph: Any, anchor: Any) -> tuple[ET.Element, ET.Element]:
    """The lists holding the paragraph objects *paragraph* and *anchor* (a section or ``hp:subList``),
    after refusing a move of *paragraph* into itself, out of or into a memo, or of a paragraph taken out."""

    from .shape_position import paragraph_box

    element, target = paragraph.element, anchor.element
    if any(node is target for node in element.iter()):
        raise HwpxValueError(
            "a paragraph cannot move into its own table cells, text boxes or notes",
            code="paragraph-move-into-itself",
            suggestion="Pick a paragraph outside this one.",
        )
    parent = paragraph_container(element, paragraph.section.element)
    destination = paragraph_container(target, anchor.section.element)
    if parent is None or destination is None:
        raise HwpxValueError(
            "the paragraph is not in a paragraph list any more",
            code="paragraph-not-in-document",
            suggestion="Take the paragraphs again from the document.",
        )
    for box in (paragraph_box(element, paragraph.section.element), paragraph_box(target, anchor.section.element)):
        if box in ("memo", "other"):
            raise HwpxValueError(
                "paragraphs move between the body, cells, text boxes, notes, captions, headers and footers; "
                "a memo's text changes through memo.text",
                code="paragraph-move-place-unsupported",
                context={"box": box},
                suggestion="Set the memo's text with memo.set_text(), or move memos with memo.move_to(section).",
            )
    return parent, destination


def _last_paragraph_refused(parent: ET.Element, section_element: ET.Element) -> HwpxValueError:
    owner = paragraph_container(parent, section_element) if parent is not section_element else None
    name = "section" if owner is None else _SUBLIST_OWNERS.get(_local(owner), _local(owner))
    return HwpxValueError(
        "the last paragraph of a section, cell, header or footer cannot leave it",
        code="paragraph-remove-last",
        context={"container": name},
        suggestion="Copy it there (insert_after/insert_before on the paragraph beside) and empty this one.",
    )


def _settings_taker(siblings: list[ET.Element], position: int) -> ET.Element:
    """The paragraph after ``siblings[position]`` (the first of a section, holding its settings) that takes them."""

    if position + 1 >= len(siblings):
        raise HwpxValueError(
            "this paragraph holds the section settings and no paragraph after it can take them",
            code="paragraph-remove-section-settings",
            context={"container": "section"},
            suggestion="Add a paragraph after it first, or move the other paragraphs instead.",
        )
    return siblings[position + 1]


def move_paragraph_beside(paragraph: Any, anchor: Any, *, after: bool) -> Any:
    """``paragraph.move_after``/``move_before``: move the paragraph object *paragraph* right after (or
    before) the paragraph object *anchor* of the same document and return the section now holding it.

    The paragraph keeps its id and content and loses its line layout cache, as do the paragraphs holding
    the cells and captions it left and joined. The section settings of a section's first paragraph go
    to the paragraph after it, and a paragraph put in front of a section's first paragraph takes that
    section's settings, as :func:`remove_paragraph_element` and :func:`insert_paragraph_beside` move
    them. Memos anchored in it go along to the memo group of its new section.
    """

    from ._document_primitives import _clear_paragraph_layout_cache
    from .memo import carry_memos
    from .shape_position import _sections_of
    from .utils import holding_paragraphs

    element, target = paragraph.element, anchor.element
    source_section, target_section = paragraph.section, anchor.section
    if target is element:
        return source_section
    parent, destination = _paragraph_lists(paragraph, anchor)
    siblings = [child for child in parent if _local(child) == "p"]
    position = next(index for index, child in enumerate(siblings) if child is element)
    if parent is destination:
        anchor_position = next(index for index, child in enumerate(siblings) if child is target)
        if anchor_position + (1 if after else -1) == position:
            return source_section  # already there
    elif len(siblings) <= 1:
        raise _last_paragraph_refused(parent, source_section.element)
    following = None
    if parent is source_section.element and section_setting_runs(element):
        following = _settings_taker(siblings, position)
    old_holders = holding_paragraphs(element)
    if following is not None:
        move_section_settings(element, following)
    parent.remove(element)
    index = next(position for position, child in enumerate(destination) if child is target)
    destination.insert(index + 1 if after else index, element)
    if not after and destination is target_section.element and section_setting_runs(target):
        move_section_settings(target, element)
    for holder in old_holders:
        _clear_paragraph_layout_cache(holder)
    _clear_paragraph_layout_cache(element)  # laid out where it was; its new cell or caption grows too
    if target_section.element is not source_section.element:
        carry_memos(element, _sections_of(paragraph, anchor), target_section)
    from .note_authoring import renumber_notes_holding

    renumber_notes_holding(target_section, (element,))  # its notes now stand elsewhere in the order
    source_section.mark_dirty()
    target_section.mark_dirty()
    return target_section


def insert_paragraph_copy(new: ET.Element, anchor: Any, *, before: bool) -> None:
    """Put the paragraph element *new* (a copy made for it) right after -- *before*: before -- the paragraph
    object *anchor*, in whatever list holds it (a section, a cell, a text box, a note, a header or footer).

    In front of a section's first paragraph the copy starts the section: the settings move to it, as
    :func:`insert_paragraph_beside` puts them. The copy and the paragraphs holding its new cell or caption
    lose their line layout cache. Refused: a memo's paragraph (``paragraph-move-place-unsupported``), a
    paragraph taken out (``paragraph-not-in-document``).
    """

    from ._document_primitives import _clear_paragraph_layout_cache
    from .shape_position import paragraph_box
    from .utils import holding_paragraphs

    destination = paragraph_container(anchor.element, anchor.section.element)
    if destination is None:
        raise HwpxValueError(
            "the paragraph is not in a paragraph list any more",
            code="paragraph-not-in-document",
            suggestion="Take the paragraphs again from the document.",
        )
    if paragraph_box(anchor.element, anchor.section.element) in ("memo", "other"):
        raise HwpxValueError(
            "a copy goes into the body, a cell, a text box, a note, a caption, a header or a footer; "
            "a memo's text changes through memo.text",
            code="paragraph-move-place-unsupported",
            context={"box": "memo"},
            suggestion="Pick a paragraph outside the memo.",
        )
    index = next(position for position, child in enumerate(destination) if child is anchor.element)
    destination.insert(index if before else index + 1, new)
    if before and destination is anchor.section.element and section_setting_runs(anchor.element):
        move_section_settings(anchor.element, new)
    for node in new.iter():
        if _local(node) == "p":
            _clear_paragraph_layout_cache(node)
    for holder in holding_paragraphs(new):
        _clear_paragraph_layout_cache(holder)
    anchor.section.mark_dirty()


def own_text_nodes(sublist: ET.Element) -> list[ET.Element]:
    """The ``hp:t`` nodes of a cell's own paragraphs (not those of a table or
    object inside them)."""

    hp_p, hp_run, hp_t = (_child_tag_like(sublist, name, _HP_NS) for name in ("p", "run", "t"))
    return [node for paragraph in sublist.findall(hp_p) for node in paragraph.findall(f"{hp_run}/{hp_t}")]


def new_own_text_node(sublist: ET.Element, char_pr_id_ref: str) -> ET.Element:
    """A text node for a cell whose own paragraphs hold none: in an empty run
    of the first paragraph (Hancom's empty cell is one), or in a new run in
    front of the objects the paragraph holds."""

    hp_p, hp_run, hp_t = (_child_tag_like(sublist, name, _HP_NS) for name in ("p", "run", "t"))
    first = sublist.find(hp_p)
    if first is None:
        first = sublist.makeelement(hp_p, {})
        sublist.append(first)
    run = next((run for run in first.findall(hp_run) if len(run) == 0), None)
    if run is None:
        run = first.makeelement(hp_run, {"charPrIDRef": char_pr_id_ref})
        first.insert(next((i for i, child in enumerate(first) if tag_local_name(child.tag) == "run"), len(first)), run)
    node = run.makeelement(hp_t, {})
    run.append(node)
    return node


_LINE_SEGMENT_FIELDS = (
    ("textpos", "text_position"), ("vertpos", "vertical_position"), ("vertsize", "height"),
    ("textheight", "text_height"), ("baseline", "baseline"), ("spacing", "spacing"),
    ("horzpos", "horizontal_position"), ("horzsize", "width"), ("flags", "flags"),
)


def _stored_int(value: str | None) -> int:
    """An ``hp:lineseg`` number: 0 when missing or unreadable, a negative one Hancom wrote in its unsigned
    32-bit form back to signed."""

    try:
        number = int(value or 0)
    except ValueError:
        return 0
    return number - 2**32 if 2**31 <= number < 2**32 else number


def paragraph_line_segments(self: Any) -> "tuple[LineSegment, ...]":
    """The paragraph's lines as they were last laid out and saved (``hp:linesegarray``), one
    :class:`~hwpx.objects.LineSegment` per line, top to bottom. Read only.

    Hancom writes them when it saves; python-hwpx writes them only through the experimental
    ``hwpx.layout.line_cache.write_line_caches``. Every edit that changes a paragraph's text, size or placement
    drops them, so a paragraph that is new or edited since its last Hancom save reads ``()``: the
    values describe the saved document, not the edits made after it.
    """

    from ..objects.results import LineSegment

    array = next((child for child in self.element if tag_local_name(child.tag) == "linesegarray"), None)
    if array is None:
        return ()
    return tuple(
        LineSegment(**{name: _stored_int(segment.get(attribute)) for attribute, name in _LINE_SEGMENT_FIELDS})
        for segment in array if tag_local_name(segment.tag) == "lineseg"
    )


#: What a mark inside ``hp:t`` reads as in ``paragraph.text`` and how many of Hancom's text positions it
#: takes (``hp:lineseg@textpos``): a tab 8, a line break and the special spaces 1, a highlight's start and
#: end none.
_LINE_TEXT_MARKS = {"tab": ("\t", 8), "lineBreak": ("\n", 1), "nbSpace": (" ", 1),
                    "fwSpace": ("　", 1), "hyphen": ("­", 1), "markpenBegin": ("", 0), "markpenEnd": ("", 0)}


def _hancom_position_map(
    paragraph: ET.Element, *, controls: dict[Any, int] | None = None, run_refs: list[str] | None = None,
) -> tuple[list[tuple[int, str]], int] | None:
    """(Hancom text position, piece of ``paragraph.text``) for each character and object of *paragraph*,
    with the final position, or ``None`` when the count is unknown."""

    pieces: list[tuple[int, str]] = []
    position = 0
    for run in paragraph:
        name = tag_local_name(run.tag)
        if name == "linesegarray":
            continue
        if name != "run":
            return None
        run_start = len(pieces)
        for child in run:
            kind = tag_local_name(child.tag)
            if kind == "t":
                for character in child.text or "":
                    pieces.append((position, character))
                    position += 2 if ord(character) > 0xFFFF else 1  # Hancom counts UTF-16 units
                for mark in child:
                    known = _LINE_TEXT_MARKS.get(tag_local_name(mark.tag))
                    if known is None:
                        return None  # a tracked change or table-of-contents mark: count not established
                    pieces.append((position, known[0]))
                    position += known[1]
                    for character in mark.tail or "":
                        pieces.append((position, character))
                        position += 2 if ord(character) > 0xFFFF else 1
            elif kind == "tab" or _is_tab_control_element(child):
                return None  # a tab outside hp:t: Hancom drops it
            else:  # a control holds one per child; secPr, a table, picture, equation or shape one each
                if controls is not None:
                    controls[child] = position
                position += 8 * max(1, len(child)) if kind == "ctrl" else 8
        if run_refs is not None:
            run_refs.extend([run.get("charPrIDRef", "0")] * (len(pieces) - run_start))
    return pieces, position


def _hancom_positions(paragraph: ET.Element) -> list[tuple[int, str]] | None:
    mapping = _hancom_position_map(paragraph)
    return mapping[0] if mapping is not None else None


def paragraph_line_texts(self: Any) -> "tuple[str, ...] | None":
    """The text of each line of :attr:`line_segments`, top to bottom: the part of ``paragraph.text``
    whose characters Hancom laid out on that line when it last saved.

    Lines are cut where each line's ``text_position`` says, counting as Hancom counts (a tab or a
    control, a table, a picture, an equation or a shape 8 places, a line break or a special space 1,
    a character outside the basic plane 2, a highlight's marks none). Those places are
    Hancom's, not places in ``paragraph.text`` (where a tab is one and a control none); the line texts
    themselves are parts of ``paragraph.text``. An object is no text, so a line
    holding only an object reads ``""``. ``()`` when the paragraph has no saved lines; ``None`` when it
    holds a mark whose count is not established (a tracked change's start or end, a table-of-contents
    mark) or a tab outside ``hp:t``: then the lines are not cut at a guess.
    """

    segments = paragraph_line_segments(self)
    if not segments:
        return ()
    pieces = _hancom_positions(self.element)
    if pieces is None or "".join(text for _position, text in pieces) != self.text:
        return None
    starts = [segment.text_position for segment in segments]
    ends = starts[1:] + [2**63]
    return tuple("".join(text for position, text in pieces if start <= position < end)
                 for start, end in zip(starts, ends))


class ParagraphFormats:
    """The paragraph-format members of :class:`~hwpx.oxml.paragraph.HwpxOxmlParagraph`,
    kept here so the owner file stays small; the bodies live in ``formatting.py``."""

    element: ET.Element
    section: Any
    para_pr_id_ref: Any
    style_id_ref: Any

    # -- Paragraph formats read and written on this paragraph alone ----------
    # (bodies in formatting.py). Reads come from the paragraph's ``hh:paraPr``
    # (the ``hp:case`` branch Hancom reads); ``None`` without one. A write gives
    # this paragraph a derived paragraph shape: others that shared the old one keep
    # it, and writing the value it has changes nothing. Units follow
    # ``doc.styles.apply_paragraph_format``: indents in mm, spacing in pt.

    @property
    def alignment(self) -> "Alignment | None":
        """The horizontal alignment (:class:`hwpx.objects.Alignment`, also a ``str``)."""
        from .formatting import paragraph_alignment

        return paragraph_alignment(self)

    @alignment.setter
    def alignment(self, value: "Alignment | str") -> None:
        from .formatting import set_paragraph_alignment

        set_paragraph_alignment(self, value)

    def _margin_mm(self, name: str) -> float | None:
        from .formatting import paragraph_margin

        value = paragraph_margin(self, name)
        return None if value is None else round(value * 25.4 / 7200, 2)

    def _margin_pt(self, name: str) -> float | None:
        from .formatting import paragraph_margin

        value = paragraph_margin(self, name)
        return None if value is None else value / 100

    def _set_margin(self, name: str, value: float, unit: str) -> None:
        from .formatting import set_paragraph_margin

        set_paragraph_margin(self, name, value, unit=unit)

    @property
    def indent_left_mm(self) -> float | None:
        """왼쪽 여백 in mm."""
        return self._margin_mm("left")

    @indent_left_mm.setter
    def indent_left_mm(self, value: float) -> None:
        self._set_margin("left", value, "mm")

    @property
    def indent_right_mm(self) -> float | None:
        """오른쪽 여백 in mm."""
        return self._margin_mm("right")

    @indent_right_mm.setter
    def indent_right_mm(self, value: float) -> None:
        self._set_margin("right", value, "mm")

    @property
    def first_line_indent_mm(self) -> float | None:
        """첫 줄 들여쓰기 in mm; negative is 내어쓰기 (a hanging indent)."""
        return self._margin_mm("intent")

    @first_line_indent_mm.setter
    def first_line_indent_mm(self, value: float) -> None:
        self._set_margin("intent", value, "mm")

    @property
    def spacing_before_pt(self) -> float | None:
        """문단 위 간격 in pt."""
        return self._margin_pt("prev")

    @spacing_before_pt.setter
    def spacing_before_pt(self, value: float) -> None:
        self._set_margin("prev", value, "pt")

    @property
    def spacing_after_pt(self) -> float | None:
        """문단 아래 간격 in pt."""
        return self._margin_pt("next")

    @spacing_after_pt.setter
    def spacing_after_pt(self, value: float) -> None:
        self._set_margin("next", value, "pt")

    @property
    def line_spacing(self) -> "LineSpacing | None":
        """줄 간격: :class:`hwpx.objects.LineSpacing` (type and value). Set a number
        for a percentage (``p.line_spacing = 160``) or a ``LineSpacing``
        (``LineSpacing("FIXED", 2000)``, HWPUNIT)."""
        from .formatting import paragraph_line_spacing

        return paragraph_line_spacing(self)

    @line_spacing.setter
    def line_spacing(self, value: "LineSpacing | int | float") -> None:
        from .formatting import set_paragraph_line_spacing

        set_paragraph_line_spacing(self, value)

    def _break_flag(self, name: str) -> bool | None:
        from .formatting import paragraph_break_flag

        return paragraph_break_flag(self, name)

    def _set_break_flag(self, name: str, value: bool) -> None:
        from .formatting import set_paragraph_break_flag

        set_paragraph_break_flag(self, name, value)

    @property
    def page_break_before(self) -> bool | None:
        """문단 앞에서 항상 쪽 나눔 (the paragraph shape's ``pageBreakBefore``)."""
        return self._break_flag("page_break_before")

    @page_break_before.setter
    def page_break_before(self, value: bool) -> None:
        self._set_break_flag("page_break_before", value)

    @property
    def keep_with_next(self) -> bool | None:
        """다음 문단과 함께."""
        return self._break_flag("keep_with_next")

    @keep_with_next.setter
    def keep_with_next(self, value: bool) -> None:
        self._set_break_flag("keep_with_next", value)

    @property
    def keep_lines(self) -> bool | None:
        """문단 보호 (the paragraph's lines kept on one page)."""
        return self._break_flag("keep_lines")

    @keep_lines.setter
    def keep_lines(self, value: bool) -> None:
        self._set_break_flag("keep_lines", value)

    @property
    def widow_orphan(self) -> bool | None:
        """외톨이줄 보호."""
        return self._break_flag("widow_orphan")

    @widow_orphan.setter
    def widow_orphan(self, value: bool) -> None:
        self._set_break_flag("widow_orphan", value)

    @property
    def page_break(self) -> bool:
        """Whether a page break comes before this paragraph (``hp:p``'s own ``pageBreak``,
        what Hancom writes for 쪽 나누기 Ctrl+Enter), beside :attr:`column_break`."""
        return self.element.get("pageBreak") == "1"

    @page_break.setter
    def page_break(self, value: bool) -> None:
        from .formatting import set_paragraph_page_break

        set_paragraph_page_break(self, value)

    @property
    def outline_level(self) -> int:
        """The outline level 1..10 of an outline paragraph (개요), 0 for any other."""
        from .formatting import paragraph_outline_level

        return paragraph_outline_level(self)

    @outline_level.setter
    def outline_level(self, value: int) -> None:
        from .formatting import set_paragraph_outline_level

        set_paragraph_outline_level(self, value)

    def set_numbering(self, numbering: "NumberingInfo | int | str | None", *, level: int = 1) -> None:
        """Number this paragraph with numbering *numbering* at *level* (1 to 10).

        *numbering* is a definition of this document — the ``NumberingInfo``
        ``doc.styles.add_numbering()`` returns, one from ``doc.styles.numbering(id)``, or
        its id. Hancom counts on through every paragraph of one definition, so the paragraphs
        given the same one make one list. The rest of the paragraph's shape (margins,
        spacing, alignment) stays; the paragraph is laid out again. ``None`` takes its head
        away (no number, bullet or outline level). An id the document lacks is
        ``style-definition-not-found``, a level outside 1 to 10 ``style-list-level-invalid``.
        """
        from .numbering_kinds import set_paragraph_list

        set_paragraph_list(self, "NUMBER", numbering, level)  # type: ignore[arg-type]

    def set_bullet(self, bullet: "Bullet | int | str | None", *, level: int = 1) -> None:
        """Give this paragraph bullet *bullet* at list *level* (1 to 10).

        *bullet* is the id ``doc.styles.ensure_bullet("●")`` returns, a ``Bullet`` from
        ``doc.styles.bullets``, or another bullet id of this document. The rest of the
        paragraph's shape stays; the paragraph is laid out again. ``None`` takes its head
        away, as :meth:`set_numbering` does.
        """
        from .numbering_kinds import set_paragraph_list

        set_paragraph_list(self, "BULLET", bullet, level)  # type: ignore[arg-type]

    @property
    def style(self) -> "Style | None":
        """The paragraph's style (``styleIDRef``), ``None`` without one; its name is ``.name``.

        Setting a style name, English name, id or ``Style`` applies it as Hancom does
        and as ``doc.add_paragraph(style=...)`` does: the paragraph takes the style's
        paragraph shape, and every run the style's character shape.
        """
        document = self.section.document
        return None if document is None else document.style(self.style_id_ref)

    @style.setter
    def style(self, value: "int | str | Style") -> None:
        from .formatting import apply_paragraph_style

        apply_paragraph_style(self, value)

    def split_run(self, offset: int) -> "HwpxOxmlRun":
        """Make character *offset* (``0 < offset < len(paragraph.text)``) a run boundary
        and return the run that starts there.

        Positions count as ``paragraph.text`` does: a tab or a line break is one
        character, a control or an object none. The run holding *offset* becomes two
        runs with the same attributes; its tabs, line breaks, controls and marks each
        stay on one side, the zero-width ones at the cut on the left. Already a
        boundary: nothing changes.
        """
        from .formatting import split_run

        return split_run(self, offset)

    def format_range(self, start: int, end: int, **changes: Any) -> "tuple[HwpxOxmlRun, ...]":
        """Give the characters ``[start, end)`` the character *changes* and return their runs.

        *changes* are the keyword arguments of :meth:`"HwpxOxmlRun".set_format`
        (``size``, ``font``, ``color``, ``bold``, ...). The runs are split at *start*
        and *end* (:meth:`split_run`); each run inside gets its own shape changed
        (bold added to an italic run stays italic). ``start == end`` changes nothing.
        ``highlight=`` is the character shape's shade colour (``shadeColor``); the marker pen
        Hancom writes inside ``hp:t`` is ``doc.text.highlight(paragraph, match)``.
        """
        from .formatting import format_range

        return format_range(self, start, end, changes)

    def replace_range(self, start: int, end: int, text: str) -> None:
        """Put *text* in place of the characters ``[start, end)``, the runs staying as they are.

        Positions count as ``paragraph.text`` does. Each new character takes the place, and so the
        run and character shape, of the old character at the same position; new characters beyond
        the range follow its last character, old ones beyond the text are removed (a run may be left
        empty) -- what ``doc.text.replace`` and Hancom's 찾아 바꾸기 write. ``start == end`` inserts
        *text* there, in the shape of the character before it (or after it at the start). A tab or a
        line break in *text* is written as Hancom writes it. The range must lie in one stretch of
        text: one not crossing a tab, a line break, a control or an object
        (``paragraph-range-crosses-element``). The paragraph loses its line layout cache.
        """
        from .formatting import replace_range

        replace_range(self, start, end, text)

    # Ranges of the text; the bodies live in ``text_ranges.py``.

    def insert_text(
        self, offset: int, text: str, *, char_pr_id_ref: "str | int | None" = None, **format: Any
    ) -> "tuple[HwpxOxmlRun, ...]":
        """Put *text* at character *offset* (``0 <= offset <= len(paragraph.text)``) and return the runs holding it.

        Positions count as ``paragraph.text`` does: a tab or a line break is one character, a control or an
        object none. The text goes after the controls and objects already at *offset* (an object's
        ``move_to(offset=)`` puts one there) and before the character there, in the run it lands in: the
        run of the last control there, else of the character before. With *char_pr_id_ref* (an ``hh:charPr``
        of the document, ``style-char-pr-missing`` otherwise) or *format* -- the keyword arguments of
        :meth:`format_range` -- it is a run of its own in that shape. A tab or a line break is written as
        Hancom writes it, inside ``hp:t``. The paragraph, and the ones holding its cell or caption, lose
        their line layout cache.
        """
        from .text_ranges import insert_text

        return insert_text(cast(Any, self), offset, text, char_pr_id_ref, format)

    def delete_range(self, start: int, end: int, *, objects: str = "refuse") -> None:
        """Take the characters ``[start, end)`` out: text, tabs, line breaks, special spaces, and the
        highlight and other marks inside. Runs left empty go; runs of one character shape left side by
        side become one; a section's settings stay.

        A control or an object strictly inside the range (``start < obj.offset < end``; those at either end
        stay) is refused with ``paragraph-range-holds-objects`` unless ``objects="remove"``: then each goes
        as its own ``remove()`` takes it out (notes renumbered, images nobody uses dropped, a memo with its
        field). Refused whatever *objects* says: a field one end of which is in the range
        (``paragraph-range-splits-field``), a tracked change's mark (``paragraph-range-splits-mark``). A
        highlight reaching out of the range keeps the part outside it.
        """
        from .text_ranges import delete_range

        delete_range(cast(Any, self), start, end, objects)

    def copy_range(self, start: int, end: int, *, to: Any, offset: "int | None" = None) -> tuple[int, int]:
        """Put a copy of the characters ``[start, end)`` -- with the controls and objects strictly inside --
        into the paragraph *to* at its character *offset* (``None``: its end), and return where the copy
        stands there, ``(offset, offset + n)``.

        *to* may be a paragraph of another document; the copy comes as :meth:`copy_to` brings a paragraph
        over (character shapes and the rest made definitions of that document, images and charts brought,
        fresh ids), apart from a table, a text box or a caption, which do not go to another document
        (``shape-copy-document-unsupported``). In the same document objects, fields and memos get fresh ids
        as :meth:`insert_after` gives a copy. A highlight reaching out of the range is closed at the copy's
        edge. A floating object going into a cell, text box, note or caption takes the placement Hancom gives
        one pasted there, as ``obj.copy_to`` places it; a table goes only where ``table.copy_to`` puts one
        (``shape-move-place-unsupported`` otherwise: a floating table not measured down from its paragraph and
        kept in the page area, into a cell, text box or note). Refused as :meth:`delete_range` refuses a split
        field or tracked change, and a note into a note, header or footer (``paragraph-move-place-unsupported``).
        """
        from .text_ranges import copy_range

        return copy_range(cast(Any, self), start, end, to, offset)

    def move_range(self, start: int, end: int, *, to: Any, offset: "int | None" = None) -> tuple[int, int]:
        """Move the characters ``[start, end)`` -- with the controls and objects strictly inside -- into the
        paragraph *to* at its character *offset* (``None``: its end, counted before the move takes them out),
        and return where they stand there.

        In the same document the controls and objects themselves move (their ids stay; memos go along to
        the memo group of their new section). To another document it is :meth:`copy_range` and then
        :meth:`delete_range` with ``objects="remove"``. Refused: an *offset* inside the range itself, or a
        paragraph inside a cell or text box the range holds (``paragraph-range-into-itself``), and what
        :meth:`copy_range` refuses.
        """
        from .text_ranges import move_range

        return move_range(cast(Any, self), start, end, to, offset)


# --------------------------------------------------------------------------
# Edits through an object taken out of its document
#
# Edits through an object taken out of its document.
#
# A paragraph, run, table, cell, row, column, note, text box or object of a table, note or text box taken
# out, of a removed section, or removed itself, is no longer in its document: nothing written into it is
# saved. One rule decides what such an object still takes:
#
# * an edit that changes only the object's own content and values, and writes nothing on the document's
#   side, works -- a paragraph's text (``text =``, ``insert_text``, ``delete_range``, ``replace_range``,
#   ``set_text_preserving_runs``, ``clear_text``), a run without a new shape (``add_run`` with no
#   formatting, ``split_run``), an existing shape id (``char_pr_id_ref =``), sizes, margins, placement
#   and values of a table, cell or object;
# * an edit that writes on the document's side is refused before anything changes
#   (``paragraph-not-in-document``, ``table-not-in-document``, ``shape-not-in-document``): one that may
#   register a character, paragraph or border shape in the header (formatting), one that numbers
#   (notes, number restarts, page hiding, bullets and numbering), one that makes a mark or an object the
#   document counts (highlights, bookmarks, fields, links, check boxes, pictures, charts, shapes,
#   equations, tables), one that adds a paragraph beside it or rows, columns and cells to its table, and
#   one that moves or copies it into the document.
#
# The second kind is wrapped here, on the classes, so every way of calling it is covered; the edits the
# paragraph and range code already refuse are left as they are.


_SUGGESTION = (
    "Take it again from the document (doc.paragraphs, doc.tables, cell.paragraphs ...); an object taken out "
    "is no longer saved."
)

# add_run/insert_text arguments that ask for a character shape (one to find or make in the header)
_FORMAT_ARGUMENTS = ("bold", "italic", "underline", "color", "font", "size", "highlight", "strike", "attributes",
                     "tab_widths")


def _holder_and_element(obj: Any) -> tuple[Any, Any]:
    """The section (or master page) *obj* was taken from, and the element to look for in it."""

    element = getattr(obj, "element", None)
    table = getattr(obj, "table", None)
    if element is None and table is not None:  # a column has no element of its own
        element = table.element
    owner: Any = obj
    if table is not None and not hasattr(obj, "paragraph"):
        owner = table  # a cell, row or column: its table's
    holder = owner.__dict__.get("_held_section") if hasattr(owner, "__dict__") else None
    if holder is None:
        holder = getattr(owner, "section", None) if not hasattr(owner, "paragraph") else None
    if holder is None:
        paragraph = getattr(owner, "paragraph", None)
        holder = paragraph.section if paragraph is not None else getattr(owner, "_section", None)
    return holder, element


def taken_out(obj: Any) -> bool:
    """True when *obj* (a paragraph, run, table, cell, row, column, note, text box or object) is no longer
    in its document. ``False`` when that cannot be told (an object made without a section)."""

    holder, element = _holder_and_element(obj)
    if holder is None or element is None or not hasattr(element, "getparent"):
        return False
    return not in_document(element, holder)


def _refusal(code: str, role: str, caller: str) -> HwpxValueError:
    return HwpxValueError(
        f"the {role} is not in the document any more (it sits in a table, note or text box taken out, in a "
        f"removed section, or was removed); {caller} writes on the document's side",
        code=code,
        context={"caller": caller, "role": role},
        suggestion=_SUGGESTION,
    )


def refuse_taken_out(obj: Any, caller: str, code: str = "paragraph-not-in-document", role: str = "paragraph") -> None:
    """Refuse (*code*) the call *caller* on *obj* when it is taken out of its document. For a method that warns
    (its warning names its caller's line, which a wrapper would take): it calls this itself."""

    if taken_out(obj):
        raise _refusal(code, role, caller)


def _formatting(arguments: dict[str, Any]) -> bool:
    for name in _FORMAT_ARGUMENTS:
        value = arguments.get(name)
        if value is not None and value is not False:
            return True
    return False


def _guard_method(cls: type, name: str, code: str, role: str,
                  when: Callable[[dict[str, Any]], bool] | None = None) -> None:
    original = getattr(cls, name)
    signature = inspect.signature(original)

    @functools.wraps(original)
    def guarded(self: Any, *args: Any, **kwargs: Any) -> Any:
        if taken_out(self) and (when is None or when(signature.bind_partial(self, *args, **kwargs).arguments)):
            raise _refusal(code, role, name)
        return original(self, *args, **kwargs)

    setattr(cls, name, guarded)


def _guard_setter(cls: type, name: str, code: str, role: str) -> None:
    original = inspect.getattr_static(cls, name)
    setter = original.fset  # a settable property of the class (install() names them)

    @functools.wraps(setter)
    def guarded(self: Any, value: Any) -> None:
        if taken_out(self):
            raise _refusal(code, role, f"{name} =")
        setter(self, value)

    setattr(cls, name, property(original.fget, guarded, original.fdel, original.__doc__))


def _guard(cls: type, code: str, role: str, methods: Iterable[str] = (), setters: Iterable[str] = (),
           when: dict[str, Callable[[dict[str, Any]], bool]] | None = None) -> None:
    for name in methods:
        _guard_method(cls, name, code, role, (when or {}).get(name))
    for name in setters:
        _guard_setter(cls, name, code, role)


def install_detached_guard() -> None:
    """Wrap the writes on the document's side of the model classes (once)."""

    from .memo import HwpxOxmlNote
    from .objects import Caption, DrawText
    from .paragraph import HwpxOxmlParagraph
    from .run import HwpxOxmlRun
    from .table import HwpxOxmlTable, HwpxOxmlTableCell

    if getattr(HwpxOxmlParagraph, "_detached_guard_installed", False):
        return
    HwpxOxmlParagraph._detached_guard_installed = True  # type: ignore[attr-defined]

    paragraph = ("paragraph-not-in-document", "paragraph")
    _guard(
        HwpxOxmlParagraph, *paragraph,
        methods=(
            # a paragraph beside it
            "insert_before", "insert_after",
            # marks and objects the document counts (ids, z-order, doc.text.highlights ...)
            "add_highlight", "add_table", "add_rectangle", "add_ellipse", "add_line", "add_equation", "add_arc",
            "add_polygon", "add_curve", "add_container", "add_date_field",  # add_shape, add_control: in them
            "add_path_field", "add_mail_merge_field", "add_index_mark", "add_title_mark", "add_proofreading_mark",
            "add_drop_cap", "add_dutmal", "add_composed_character", "add_column_definition",
            # numbering
            "add_number_restart", "add_page_hiding", "set_bullet", "set_numbering",
            # a character shape to find or make in the header
            "format_range", "add_run",
        ),
        setters=(
            "alignment", "first_line_indent_mm", "indent_left_mm", "indent_right_mm", "keep_lines",
            "keep_with_next", "line_spacing", "outline_level", "page_break_before", "spacing_after_pt",
            "spacing_before_pt", "widow_orphan",
        ),
        when={"add_run": _formatting},
    )
    _guard(
        HwpxOxmlRun, "paragraph-not-in-document", "run",
        methods=("set_font", "set_format"),
        setters=("bold", "color", "font", "highlight", "italic", "letter_spacing", "ratio", "size", "strike",
                 "subscript", "superscript", "underline"),
    )
    table = ("table-not-in-document", "table")
    _guard(
        HwpxOxmlTable, *table,
        methods=(
            "copy_after", "insert_rows", "delete_rows", "insert_columns", "delete_columns", "merge_cells",
            "split_cell", "split_merged_cell", "set_borders", "set_cell_borders", "set_cell_border_fill",
            "set_cell_fill_gradient", "set_cell_fill_image", "set_cell_shading", "set_shading",
        ),
        setters=("alignment",),
    )
    _guard(HwpxOxmlTableCell, "table-not-in-document", "cell", methods=("add_paragraph", "add_table"))
    _guard(HwpxOxmlNote, "paragraph-not-in-document", "note", methods=("add_paragraph", "add_run"),
           when={"add_run": _formatting})
    _guard(DrawText, "shape-not-in-document", "text box", methods=("add_paragraph",))
    _guard(Caption, "shape-not-in-document", "caption", methods=("add_paragraph",))
