# SPDX-License-Identifier: Apache-2.0
"""Small helpers for editing the text inside ``hp:t`` and for taking a paragraph out of its list."""

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
    from ..objects.results import Alignment, LineSpacing
    from .header import Style
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
    settings move, into a new run with the same attributes. *target* loses its line layout cache:
    the controls in front of its text shift every position the cache records. Returns whether
    anything moved.
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
    for cache in [child for child in target if isinstance(child.tag, str) and tag_local_name(child.tag).lower() == "linesegarray"]:
        target.remove(cache)
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
