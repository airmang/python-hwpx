# SPDX-License-Identifier: Apache-2.0
"""Small helpers for editing the text inside ``hp:t`` and for taking a paragraph out of its list or
moving it to another place in the same document."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Any

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
    from ..objects.results import Alignment, LineSegment, LineSpacing, NumberingInfo
    from .header import Bullet, Style
    from .run import HwpxOxmlRun


def plain_text_nodes_for_edit(runs: list[ET.Element]) -> list[ET.Element]:
    nodes: list[ET.Element] = []
    for run in runs:
        for child in run:
            if tag_local_name(child.tag) == "t":
                if len(child):
                    raise HwpxValueError(
                        "mixed text markup cannot be edited safely",
                        code="paragraph-mixed-text-unsupported",
                    )
                nodes.append(child)
            elif tag_local_name(child.tag) == "tab" or _is_tab_control_element(child):
                raise HwpxValueError(
                    "tab controls require an explicit run target",
                    code="paragraph-tab-target-required",
                )
    return nodes


def edit_node_candidates(
    nodes: list[ET.Element], prefix: int, end: int
) -> list[tuple[ET.Element, int]]:
    offset = 0
    candidates: list[tuple[ET.Element, int]] = []
    for node in nodes:
        length = len(node.text or "")
        if offset <= prefix and end <= offset + length:
            candidates.append((node, offset))
        offset += length
    return candidates


def sanitize_keeping_tabs(value: str) -> str:
    """``_sanitize_text``, but keep tabs for :func:`set_text_with_tabs`."""

    _require_text(value)
    return "\t".join(_sanitize_text(part) for part in value.split("\t"))


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


def move_section_settings(source: ET.Element, target: ET.Element) -> bool:
    """Move the section settings of the paragraph *source* to the front of the paragraph *target*.

    A run holding nothing else moves whole; from a run holding text or objects too, only the
    settings move, into a new run with the same attributes. Both paragraphs lose their line
    layout cache: the controls in front of the text (8 positions each in ``lineseg/@textpos``)
    shift every position the cache records, in *target* by coming and in *source* by going.
    Returns whether anything moved.
    """

    found = section_setting_runs(source)
    if not found:
        return False
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


def renumber_copied_fields(copy: ET.Element) -> int:
    """Give each field whose begin and end are both inside *copy* a new id pair.

    A field's begin and end pair by id (``hp:fieldBegin/@id``, ``hp:fieldEnd/@beginIDRef``); a copy
    keeping them leaves two fields of one id, which readers and form filling cannot tell apart.
    A ``fieldid`` equal to the old id follows it. A field reaching outside *copy* is left as it is.
    Returns how many fields were renumbered.
    """

    from ._document_primitives import _object_id

    hp_begin, hp_end = f"{{{_HP_NS}}}fieldBegin", f"{{{_HP_NS}}}fieldEnd"
    ends: dict[str, list[ET.Element]] = {}
    for end in copy.iter(hp_end):
        ends.setdefault(end.get("beginIDRef") or "", []).append(end)
    renumbered = 0
    for begin in copy.iter(hp_begin):
        old = begin.get("id")
        if not old or old not in ends:
            continue
        new_id = _object_id()
        for node in (begin, *ends.pop(old)):
            node.set("id" if node is begin else "beginIDRef", new_id)
            if node.get("fieldid") == old:
                node.set("fieldid", new_id)
        renumbered += 1
    return renumbered


def insert_paragraph_beside(
    element: ET.Element, section_element: ET.Element, text: str | None, *, after: bool
) -> ET.Element:
    """Put a new paragraph next to the paragraph *element* (in its section, cell, header...) and
    return it.

    *text* ``None`` copies *element* (fresh ids, field ids among them, and no line caches) without
    its section settings; otherwise the new paragraph holds *text* in *element*'s paragraph shape,
    style and first run's character shape. Put in front of the paragraph that starts a section,
    it starts the section instead: the section's settings move to it.
    """

    from ._document_primitives import (
        _DEFAULT_PARAGRAPH_ATTRS, _append_text_with_tabs, _clone_paragraph_element, _paragraph_id,
    )

    parent = paragraph_container(element, section_element)
    if parent is None:
        raise HwpxValueError(
            "이 단락은 문서에서 빠져 있어 옆에 단락을 넣을 수 없습니다.",
            code="paragraph-not-in-document",
            suggestion="문서의 doc.paragraphs 에서 단락을 다시 가져오세요.",
        )
    if text is None:
        new = _clone_paragraph_element(element)
        renumber_copied_fields(new)
        for run, settings in section_setting_runs(new):
            for child in settings:
                run.remove(child)
            if len(run) == 0:
                new.remove(run)
    else:
        text_run = next((child for child in element if _local(child) == "run" and (
            not len(child) or not all(is_section_setting(grand) for grand in child))), None)
        new = element.makeelement(element.tag, {"id": _paragraph_id(), **_DEFAULT_PARAGRAPH_ATTRS})
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


def _section_holding(element: Any, sections: list[Any]) -> Any:
    """The section of *sections* whose tree holds *element*, or ``None``."""

    if hasattr(element, "getparent"):
        root = element
        while (parent := root.getparent()) is not None:
            root = parent
        return next((section for section in sections if section.element is root), None)
    return next((section for section in sections if any(node is element for node in section.element.iter())), None)


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
    source_section.mark_dirty()
    target_section.mark_dirty()
    return target_section


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
        """
        from .formatting import format_range

        return format_range(self, start, end, changes)
