# SPDX-License-Identifier: Apache-2.0
"""Owned section layout, numbering, and story-link behavior."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping, Optional, Sequence
import xml.etree.ElementTree as ET

from ._document_primitives import (
    _DEFAULT_PARAGRAPH_ATTRS,
    _HP,
    _append_child,
    _apply_optional_attrs,
    _apply_optional_bool_attrs,
    _bool_str,
    _get_bool_attr,
    _get_int_attr,
    _object_id,
    _optional_int_attr,
    _paragraph_id,
)
from .numbering import SectionStartNumbering
from .section_story import HwpxOxmlSectionHeaderFooter

if TYPE_CHECKING:
    from .section import HwpxOxmlSection


@dataclass(slots=True)
class PageSize:
    """Represents the size and orientation of a page."""

    width: int
    height: int
    orientation: str
    gutter_type: str


@dataclass(slots=True)
class PageMargins:
    """Encapsulates page margin values in HWP units."""

    left: int
    right: int
    top: int
    bottom: int
    header: int
    footer: int
    gutter: int


@dataclass(slots=True)
class SectionGrid:
    """Represents ``<hp:grid>`` — line/character grid alignment."""

    line_grid: int
    char_grid: int
    wonggoji_format: bool


@dataclass(slots=True)
class SectionVisibility:
    """Represents ``<hp:visibility>`` — first-page show/hide flags."""

    hide_first_header: bool
    hide_first_footer: bool
    hide_first_master_page: bool
    hide_first_page_num: bool
    hide_first_empty_line: bool
    show_line_number: bool
    border: str | None
    fill: str | None


@dataclass(slots=True)
class LineNumberShape:
    """Represents ``<hp:lineNumberShape>`` — line-numbering display."""

    restart_type: int | None
    count_by: int | None
    distance: int | None
    start_number: int | None


@dataclass(slots=True)
class PageBorderFill:
    """Represents one ``<hp:pageBorderFill>`` entry (keyed by ``page_type``)."""

    page_type: str
    border_fill_id_ref: str | None
    text_border: str | None
    header_inside: bool
    footer_inside: bool
    fill_area: str | None
    offset_left: int
    offset_right: int
    offset_top: int
    offset_bottom: int


@dataclass(slots=True)
class NoteAutoNumFormat:
    """Represents a note's ``<hp:autoNumFormat>`` — shared by foot/endnotes."""

    type: str
    user_char: str | None
    prefix_char: str | None
    suffix_char: str
    supscript: bool


@dataclass(slots=True)
class NoteLine:
    """Represents a note's ``<hp:noteLine>`` separator — shared by foot/endnotes."""

    length: int
    type: str
    width: str
    color: str


@dataclass(slots=True)
class NoteSpacing:
    """Represents a note's ``<hp:noteSpacing>`` — shared by foot/endnotes."""

    between_notes: int
    below_line: int
    above_line: int


@dataclass(slots=True)
class NoteNumbering:
    """Represents a note's ``<hp:numbering>`` — CONTINUOUS/ON_SECTION(/ON_PAGE)."""

    type: str
    new_num: int


@dataclass(slots=True)
class NotePlacement:
    """Represents a note's ``<hp:placement>`` — footnote/endnote vocab differs."""

    place: str
    beneath_text: bool


@dataclass(slots=True)
class NoteShape:
    """Aggregate read view of a ``<hp:footNotePr>``/``<hp:endNotePr>``."""

    auto_num_format: NoteAutoNumFormat
    note_line: NoteLine
    note_spacing: NoteSpacing
    numbering: NoteNumbering
    placement: NotePlacement


class HwpxOxmlSectionProperties:
    """Provides convenient access to ``<hp:secPr>`` configuration."""

    def __init__(self, element: ET.Element, section: "HwpxOxmlSection"):
        self.element = element
        self.section = section

    # -- page configuration -------------------------------------------------
    def _page_pr_element(self, create: bool = False) -> ET.Element | None:
        page_pr = self.element.find(f"{_HP}pagePr")
        if page_pr is None and create:
            page_pr = ET.SubElement(
                self.element,
                f"{_HP}pagePr",
                {"landscape": "PORTRAIT", "width": "0", "height": "0", "gutterType": "LEFT_ONLY"},
            )
            self.section.mark_dirty()
        return page_pr

    def _margin_element(self, create: bool = False) -> ET.Element | None:
        page_pr = self._page_pr_element(create=create)
        if page_pr is None:
            return None
        margin = page_pr.find(f"{_HP}margin")
        if margin is None and create:
            margin = ET.SubElement(
                page_pr,
                f"{_HP}margin",
                {
                    "left": "0",
                    "right": "0",
                    "top": "0",
                    "bottom": "0",
                    "header": "0",
                    "footer": "0",
                    "gutter": "0",
                },
            )
            self.section.mark_dirty()
        return margin

    @property
    def page_size(self) -> PageSize:
        page_pr = self._page_pr_element()
        if page_pr is None:
            return PageSize(width=0, height=0, orientation="PORTRAIT", gutter_type="LEFT_ONLY")
        return PageSize(
            width=_get_int_attr(page_pr, "width", 0),
            height=_get_int_attr(page_pr, "height", 0),
            orientation=page_pr.get("landscape", "PORTRAIT"),
            gutter_type=page_pr.get("gutterType", "LEFT_ONLY"),
        )

    def set_page_size(
        self,
        *,
        width: int | None = None,
        height: int | None = None,
        orientation: str | None = None,
        gutter_type: str | None = None,
    ) -> None:
        page_pr = self._page_pr_element(create=True)
        if page_pr is None:
            return

        changed = False
        if width is not None:
            value = str(max(width, 0))
            if page_pr.get("width") != value:
                page_pr.set("width", value)
                changed = True
        if height is not None:
            value = str(max(height, 0))
            if page_pr.get("height") != value:
                page_pr.set("height", value)
                changed = True
        if orientation is not None and page_pr.get("landscape") != orientation:
            page_pr.set("landscape", orientation)
            changed = True
        if gutter_type is not None and page_pr.get("gutterType") != gutter_type:
            page_pr.set("gutterType", gutter_type)
            changed = True
        if changed:
            self.section.mark_dirty()

    @property
    def page_margins(self) -> PageMargins:
        margin = self._margin_element()
        if margin is None:
            return PageMargins(left=0, right=0, top=0, bottom=0, header=0, footer=0, gutter=0)
        return PageMargins(
            left=_get_int_attr(margin, "left", 0),
            right=_get_int_attr(margin, "right", 0),
            top=_get_int_attr(margin, "top", 0),
            bottom=_get_int_attr(margin, "bottom", 0),
            header=_get_int_attr(margin, "header", 0),
            footer=_get_int_attr(margin, "footer", 0),
            gutter=_get_int_attr(margin, "gutter", 0),
        )

    def set_page_margins(
        self,
        *,
        left: int | None = None,
        right: int | None = None,
        top: int | None = None,
        bottom: int | None = None,
        header: int | None = None,
        footer: int | None = None,
        gutter: int | None = None,
    ) -> None:
        margin = self._margin_element(create=True)
        if margin is None:
            return

        changed = False
        for name, value in (
            ("left", left),
            ("right", right),
            ("top", top),
            ("bottom", bottom),
            ("header", header),
            ("footer", footer),
            ("gutter", gutter),
        ):
            if value is None:
                continue
            safe_value = str(max(value, 0))
            if margin.get(name) != safe_value:
                margin.set(name, safe_value)
                changed = True
        if changed:
            self.section.mark_dirty()

    # -- numbering ----------------------------------------------------------
    @property
    def start_numbering(self) -> SectionStartNumbering:
        start_num = self.element.find(f"{_HP}startNum")
        if start_num is None:
            return SectionStartNumbering(
                page_starts_on="BOTH",
                page=0,
                picture=0,
                table=0,
                equation=0,
            )
        return SectionStartNumbering(
            page_starts_on=start_num.get("pageStartsOn", "BOTH"),
            page=_get_int_attr(start_num, "page", 0),
            picture=_get_int_attr(start_num, "pic", 0),
            table=_get_int_attr(start_num, "tbl", 0),
            equation=_get_int_attr(start_num, "equation", 0),
        )

    def set_start_numbering(
        self,
        *,
        page_starts_on: str | None = None,
        page: int | None = None,
        picture: int | None = None,
        table: int | None = None,
        equation: int | None = None,
    ) -> None:
        start_num = self.element.find(f"{_HP}startNum")
        if start_num is None:
            start_num = ET.SubElement(
                self.element,
                f"{_HP}startNum",
                {
                    "pageStartsOn": "BOTH",
                    "page": "0",
                    "pic": "0",
                    "tbl": "0",
                    "equation": "0",
                },
            )
            self.section.mark_dirty()

        changed = False
        if page_starts_on is not None and start_num.get("pageStartsOn") != page_starts_on:
            start_num.set("pageStartsOn", page_starts_on)
            changed = True

        for name, value in (
            ("page", page),
            ("pic", picture),
            ("tbl", table),
            ("equation", equation),
        ):
            if value is None:
                continue
            safe_value = str(max(value, 0))
            if start_num.get(name) != safe_value:
                start_num.set(name, safe_value)
                changed = True

        if changed:
            self.section.mark_dirty()

    # -- grid / visibility / line numbering ----------------------------------
    # ``<hp:grid>``, ``<hp:visibility>``, ``<hp:lineNumberShape>`` are direct
    # ``<hp:secPr>`` children (schema: ``SectionDefinitionType``) that ship on
    # every generated document (166/166 real-corpus files per the coverage
    # ledger) but previously had no edit API — only whatever the Skeleton
    # template happened to carry forward untouched.

    @property
    def grid(self) -> SectionGrid:
        element = self.element.find(f"{_HP}grid")
        if element is None:
            return SectionGrid(line_grid=0, char_grid=0, wonggoji_format=False)
        return SectionGrid(
            line_grid=_get_int_attr(element, "lineGrid", 0),
            char_grid=_get_int_attr(element, "charGrid", 0),
            wonggoji_format=_get_bool_attr(element, "wonggojiFormat", False),
        )

    def set_grid(
        self,
        *,
        line_grid: int | None = None,
        char_grid: int | None = None,
        wonggoji_format: bool | None = None,
    ) -> None:
        element = self.element.find(f"{_HP}grid")
        if element is None:
            element = ET.SubElement(
                self.element,
                f"{_HP}grid",
                {"lineGrid": "0", "charGrid": "0", "wonggojiFormat": "0"},
            )
            self.section.mark_dirty()

        changed = False
        for name, value in (("lineGrid", line_grid), ("charGrid", char_grid)):
            if value is None:
                continue
            safe_value = str(max(value, 0))
            if element.get(name) != safe_value:
                element.set(name, safe_value)
                changed = True
        if wonggoji_format is not None:
            wonggoji_value = _bool_str(wonggoji_format)
            if _get_bool_attr(element, "wonggojiFormat", False) != wonggoji_format:
                element.set("wonggojiFormat", wonggoji_value)
                changed = True
        if changed:
            self.section.mark_dirty()

    @property
    def visibility(self) -> SectionVisibility:
        element = self.element.find(f"{_HP}visibility")
        if element is None:
            return SectionVisibility(
                hide_first_header=False,
                hide_first_footer=False,
                hide_first_master_page=False,
                hide_first_page_num=False,
                hide_first_empty_line=False,
                show_line_number=False,
                border=None,
                fill=None,
            )
        return SectionVisibility(
            hide_first_header=_get_bool_attr(element, "hideFirstHeader", False),
            hide_first_footer=_get_bool_attr(element, "hideFirstFooter", False),
            hide_first_master_page=_get_bool_attr(element, "hideFirstMasterPage", False),
            hide_first_page_num=_get_bool_attr(element, "hideFirstPageNum", False),
            hide_first_empty_line=_get_bool_attr(element, "hideFirstEmptyLine", False),
            show_line_number=_get_bool_attr(element, "showLineNumber", False),
            border=element.get("border"),
            fill=element.get("fill"),
        )

    def set_visibility(
        self,
        *,
        hide_first_header: bool | None = None,
        hide_first_footer: bool | None = None,
        hide_first_master_page: bool | None = None,
        hide_first_page_num: bool | None = None,
        hide_first_empty_line: bool | None = None,
        show_line_number: bool | None = None,
        border: str | None = None,
        fill: str | None = None,
    ) -> None:
        element = self.element.find(f"{_HP}visibility")
        if element is None:
            element = ET.SubElement(
                self.element,
                f"{_HP}visibility",
                {
                    "hideFirstHeader": "false",
                    "hideFirstFooter": "false",
                    "hideFirstMasterPage": "false",
                    "hideFirstPageNum": "false",
                    "hideFirstEmptyLine": "false",
                    "showLineNumber": "false",
                },
            )
            self.section.mark_dirty()

        changed = False
        for name, value in (
            ("hideFirstHeader", hide_first_header),
            ("hideFirstFooter", hide_first_footer),
            ("hideFirstMasterPage", hide_first_master_page),
            ("hideFirstPageNum", hide_first_page_num),
            ("hideFirstEmptyLine", hide_first_empty_line),
            ("showLineNumber", show_line_number),
        ):
            if value is None:
                continue
            if _get_bool_attr(element, name, False) != value:
                element.set(name, _bool_str(value))
                changed = True
        for name, text_value in (("border", border), ("fill", fill)):
            if text_value is None:
                continue
            if element.get(name) != text_value:
                element.set(name, text_value)
                changed = True
        if changed:
            self.section.mark_dirty()

    @property
    def line_number_shape(self) -> LineNumberShape:
        element = self.element.find(f"{_HP}lineNumberShape")
        if element is None:
            return LineNumberShape(
                restart_type=None, count_by=None, distance=None, start_number=None
            )
        return LineNumberShape(
            restart_type=_optional_int_attr(element, "restartType"),
            count_by=_optional_int_attr(element, "countBy"),
            distance=_optional_int_attr(element, "distance"),
            start_number=_optional_int_attr(element, "startNumber"),
        )

    def set_line_number_shape(
        self,
        *,
        restart_type: int | None = None,
        count_by: int | None = None,
        distance: int | None = None,
        start_number: int | None = None,
    ) -> None:
        element = self.element.find(f"{_HP}lineNumberShape")
        if element is None:
            element = ET.SubElement(self.element, f"{_HP}lineNumberShape", {})
            self.section.mark_dirty()

        changed = False
        for name, value in (
            ("restartType", restart_type),
            ("countBy", count_by),
            ("distance", distance),
            ("startNumber", start_number),
        ):
            if value is None:
                continue
            safe_value = str(max(value, 0))
            if element.get(name) != safe_value:
                element.set(name, safe_value)
                changed = True
        if changed:
            self.section.mark_dirty()

    # -- page border/fill -----------------------------------------------
    # ``<hp:pageBorderFill>`` can repeat up to 3 times (schema
    # ``maxOccurs="3"``), keyed by its own ``type`` attribute
    # (BOTH/EVEN/ODD) — same shape as header/footer page-type variants.

    def _page_border_fill_element(
        self, page_type: str = "BOTH", *, create: bool = False
    ) -> ET.Element | None:
        for element in self.element.findall(f"{_HP}pageBorderFill"):
            if element.get("type", "BOTH") == page_type:
                return element
        if not create:
            return None
        element = ET.SubElement(self.element, f"{_HP}pageBorderFill", {"type": page_type})
        ET.SubElement(
            element,
            f"{_HP}offset",
            {"left": "1417", "right": "1417", "top": "1417", "bottom": "1417"},
        )
        self.section.mark_dirty()
        return element

    def page_border_fill(self, page_type: str = "BOTH") -> PageBorderFill | None:
        element = self._page_border_fill_element(page_type)
        if element is None:
            return None
        offset = element.find(f"{_HP}offset")
        return PageBorderFill(
            page_type=element.get("type", "BOTH"),
            border_fill_id_ref=element.get("borderFillIDRef"),
            text_border=element.get("textBorder"),
            header_inside=_get_bool_attr(element, "headerInside", False),
            footer_inside=_get_bool_attr(element, "footerInside", False),
            fill_area=element.get("fillArea"),
            offset_left=_get_int_attr(offset, "left", 1417) if offset is not None else 1417,
            offset_right=_get_int_attr(offset, "right", 1417) if offset is not None else 1417,
            offset_top=_get_int_attr(offset, "top", 1417) if offset is not None else 1417,
            offset_bottom=_get_int_attr(offset, "bottom", 1417) if offset is not None else 1417,
        )

    def set_page_border_fill(
        self,
        *,
        page_type: str = "BOTH",
        border_fill_id_ref: str | int | None = None,
        text_border: str | None = None,
        header_inside: bool | None = None,
        footer_inside: bool | None = None,
        fill_area: str | None = None,
        offset_left: int | None = None,
        offset_right: int | None = None,
        offset_top: int | None = None,
        offset_bottom: int | None = None,
    ) -> None:
        """Create or update the ``page_type`` (BOTH/EVEN/ODD) page border/fill.

        *page_type* selects which of up to 3 entries to touch — it is not a
        "leave unchanged" field like the rest. Everything else follows the
        established convention: omitted (``None``) keyword args leave the
        existing value alone.
        """

        element = self._page_border_fill_element(page_type, create=True)
        if element is None:  # pragma: no cover - defensive branch
            return

        changed = _apply_optional_attrs(
            element,
            (
                ("borderFillIDRef", None if border_fill_id_ref is None else str(border_fill_id_ref)),
                ("textBorder", text_border),
                ("fillArea", fill_area),
            ),
        )
        changed = (
            _apply_optional_bool_attrs(
                element,
                (("headerInside", header_inside), ("footerInside", footer_inside)),
            )
            or changed
        )
        changed = (
            self._apply_page_border_fill_offset(
                element, offset_left, offset_right, offset_top, offset_bottom
            )
            or changed
        )

        if changed:
            self.section.mark_dirty()

    def _apply_page_border_fill_offset(
        self,
        element: ET.Element,
        left: int | None,
        right: int | None,
        top: int | None,
        bottom: int | None,
    ) -> bool:
        offset_values = (("left", left), ("right", right), ("top", top), ("bottom", bottom))
        if not any(value is not None for _name, value in offset_values):
            return False

        offset = element.find(f"{_HP}offset")
        created = offset is None
        if offset is None:
            offset = ET.SubElement(
                element,
                f"{_HP}offset",
                {"left": "1417", "right": "1417", "top": "1417", "bottom": "1417"},
            )
        safe_pairs = tuple(
            (name, None if value is None else str(max(value, 0))) for name, value in offset_values
        )
        return _apply_optional_attrs(offset, safe_pairs) or created

    # -- footnote / endnote shape --------------------------------------
    # ``<hp:footNotePr>``/``<hp:endNotePr>`` share ``NoteShapeType``'s three
    # mandatory children (autoNumFormat/noteLine/noteSpacing) and each adds
    # its own numbering/placement vocabulary. Every setter here updates
    # exactly one nested block — the other four are never touched, so a
    # caller that only wants to change e.g. the separator line never
    # perturbs autoNumFormat/numbering/etc. on a real document (required for
    # safe round-tripping of Hancom-authored notes).

    _NOTE_DEFAULTS: dict[str, dict[str, dict[str, str]]] = {
        "footNotePr": {
            "numbering": {"type": "CONTINUOUS", "newNum": "1"},
            "placement": {"place": "EACH_COLUMN", "beneathText": "false"},
        },
        "endNotePr": {
            "numbering": {"type": "CONTINUOUS", "newNum": "1"},
            "placement": {"place": "END_OF_DOCUMENT", "beneathText": "false"},
        },
    }

    def _note_pr_element(self, tag: str, *, create: bool = False) -> ET.Element | None:
        element = self.element.find(f"{_HP}{tag}")
        if element is not None or not create:
            return element
        # NoteShapeType의 5개 자식 전부 minOccurs 생략(=1, 필수) — 하나라도
        # 빠지면 스키마 위반이라 생성 시 다섯 개를 한 번에 원자적으로 만든다.
        element = ET.SubElement(self.element, f"{_HP}{tag}", {})
        ET.SubElement(
            element, f"{_HP}autoNumFormat", {"type": "DIGIT", "suffixChar": ")", "supscript": "false"}
        )
        ET.SubElement(
            element,
            f"{_HP}noteLine",
            {"length": "0", "type": "SOLID", "width": "0.12 mm", "color": "#000000"},
        )
        ET.SubElement(
            element,
            f"{_HP}noteSpacing",
            {"betweenNotes": "850", "belowLine": "567", "aboveLine": "567"},
        )
        ET.SubElement(element, f"{_HP}numbering", dict(self._NOTE_DEFAULTS[tag]["numbering"]))
        ET.SubElement(element, f"{_HP}placement", dict(self._NOTE_DEFAULTS[tag]["placement"]))
        self.section.mark_dirty()
        return element

    def _note_shape(self, tag: str) -> NoteShape | None:
        parent = self._note_pr_element(tag)
        if parent is None:
            return None
        auto_num = parent.find(f"{_HP}autoNumFormat")
        note_line = parent.find(f"{_HP}noteLine")
        note_spacing = parent.find(f"{_HP}noteSpacing")
        numbering = parent.find(f"{_HP}numbering")
        placement = parent.find(f"{_HP}placement")
        return NoteShape(
            auto_num_format=NoteAutoNumFormat(
                type=(auto_num.get("type", "DIGIT") if auto_num is not None else "DIGIT"),
                user_char=(auto_num.get("userChar") if auto_num is not None else None),
                prefix_char=(auto_num.get("prefixChar") if auto_num is not None else None),
                suffix_char=(auto_num.get("suffixChar", ")") if auto_num is not None else ")"),
                supscript=(
                    _get_bool_attr(auto_num, "supscript", False) if auto_num is not None else False
                ),
            ),
            note_line=NoteLine(
                length=(_get_int_attr(note_line, "length", 0) if note_line is not None else 0),
                type=(note_line.get("type", "SOLID") if note_line is not None else "SOLID"),
                width=(note_line.get("width", "0.12 mm") if note_line is not None else "0.12 mm"),
                color=(note_line.get("color", "#000000") if note_line is not None else "#000000"),
            ),
            note_spacing=NoteSpacing(
                between_notes=(
                    _get_int_attr(note_spacing, "betweenNotes", 850) if note_spacing is not None else 850
                ),
                below_line=(
                    _get_int_attr(note_spacing, "belowLine", 567) if note_spacing is not None else 567
                ),
                above_line=(
                    _get_int_attr(note_spacing, "aboveLine", 567) if note_spacing is not None else 567
                ),
            ),
            numbering=NoteNumbering(
                type=(numbering.get("type", "CONTINUOUS") if numbering is not None else "CONTINUOUS"),
                new_num=(_get_int_attr(numbering, "newNum", 1) if numbering is not None else 1),
            ),
            placement=NotePlacement(
                place=(
                    placement.get("place", self._NOTE_DEFAULTS[tag]["placement"]["place"])
                    if placement is not None
                    else self._NOTE_DEFAULTS[tag]["placement"]["place"]
                ),
                beneath_text=(
                    _get_bool_attr(placement, "beneathText", False) if placement is not None else False
                ),
            ),
        )

    def _set_note_auto_num_format(
        self,
        tag: str,
        *,
        type: str | None = None,
        user_char: str | None = None,
        prefix_char: str | None = None,
        suffix_char: str | None = None,
        supscript: bool | None = None,
    ) -> None:
        parent = self._note_pr_element(tag, create=True)
        element = parent.find(f"{_HP}autoNumFormat") if parent is not None else None
        if element is None:  # pragma: no cover - defensive branch, schema-mandatory
            return
        changed = False
        for name, value in (
            ("type", type),
            ("userChar", user_char),
            ("prefixChar", prefix_char),
            ("suffixChar", suffix_char),
        ):
            if value is not None and element.get(name) != value:
                element.set(name, value)
                changed = True
        if supscript is not None and _get_bool_attr(element, "supscript", False) != supscript:
            element.set("supscript", _bool_str(supscript))
            changed = True
        if changed:
            self.section.mark_dirty()

    def _set_note_line(
        self,
        tag: str,
        *,
        length: int | None = None,
        type: str | None = None,
        width: str | None = None,
        color: str | None = None,
    ) -> None:
        parent = self._note_pr_element(tag, create=True)
        element = parent.find(f"{_HP}noteLine") if parent is not None else None
        if element is None:  # pragma: no cover - defensive branch, schema-mandatory
            return
        changed = False
        if length is not None:
            value = str(length)
            if element.get("length") != value:
                element.set("length", value)
                changed = True
        if type is not None and element.get("type") != type:
            element.set("type", type)
            changed = True
        if width is not None and element.get("width") != width:
            element.set("width", width)
            changed = True
        if color is not None and element.get("color") != color:
            element.set("color", color)
            changed = True
        if changed:
            self.section.mark_dirty()

    def _set_note_spacing(
        self,
        tag: str,
        *,
        between_notes: int | None = None,
        below_line: int | None = None,
        above_line: int | None = None,
    ) -> None:
        parent = self._note_pr_element(tag, create=True)
        element = parent.find(f"{_HP}noteSpacing") if parent is not None else None
        if element is None:  # pragma: no cover - defensive branch, schema-mandatory
            return
        changed = False
        for name, value in (
            ("betweenNotes", between_notes),
            ("belowLine", below_line),
            ("aboveLine", above_line),
        ):
            if value is None:
                continue
            safe_value = str(max(value, 0))
            if element.get(name) != safe_value:
                element.set(name, safe_value)
                changed = True
        if changed:
            self.section.mark_dirty()

    def _set_note_numbering(
        self,
        tag: str,
        *,
        type: str | None = None,
        new_num: int | None = None,
    ) -> None:
        parent = self._note_pr_element(tag, create=True)
        element = parent.find(f"{_HP}numbering") if parent is not None else None
        if element is None:  # pragma: no cover - defensive branch, schema-mandatory
            return
        changed = False
        if type is not None and element.get("type") != type:
            element.set("type", type)
            changed = True
        if new_num is not None:
            value = str(max(new_num, 1))
            if element.get("newNum") != value:
                element.set("newNum", value)
                changed = True
        if changed:
            self.section.mark_dirty()

    def _set_note_placement(
        self,
        tag: str,
        *,
        place: str | None = None,
        beneath_text: bool | None = None,
    ) -> None:
        parent = self._note_pr_element(tag, create=True)
        element = parent.find(f"{_HP}placement") if parent is not None else None
        if element is None:  # pragma: no cover - defensive branch, schema-mandatory
            return
        changed = False
        if place is not None and element.get("place") != place:
            element.set("place", place)
            changed = True
        if beneath_text is not None and _get_bool_attr(element, "beneathText", False) != beneath_text:
            element.set("beneathText", _bool_str(beneath_text))
            changed = True
        if changed:
            self.section.mark_dirty()

    @property
    def footnote_shape(self) -> NoteShape | None:
        return self._note_shape("footNotePr")

    def set_footnote_auto_num_format(self, **kwargs: Any) -> None:
        self._set_note_auto_num_format("footNotePr", **kwargs)

    def set_footnote_note_line(self, **kwargs: Any) -> None:
        self._set_note_line("footNotePr", **kwargs)

    def set_footnote_note_spacing(self, **kwargs: Any) -> None:
        self._set_note_spacing("footNotePr", **kwargs)

    def set_footnote_numbering(self, **kwargs: Any) -> None:
        self._set_note_numbering("footNotePr", **kwargs)

    def set_footnote_placement(self, **kwargs: Any) -> None:
        self._set_note_placement("footNotePr", **kwargs)

    @property
    def endnote_shape(self) -> NoteShape | None:
        return self._note_shape("endNotePr")

    def set_endnote_auto_num_format(self, **kwargs: Any) -> None:
        self._set_note_auto_num_format("endNotePr", **kwargs)

    def set_endnote_note_line(self, **kwargs: Any) -> None:
        self._set_note_line("endNotePr", **kwargs)

    def set_endnote_note_spacing(self, **kwargs: Any) -> None:
        self._set_note_spacing("endNotePr", **kwargs)

    def set_endnote_numbering(self, **kwargs: Any) -> None:
        self._set_note_numbering("endNotePr", **kwargs)

    def set_endnote_placement(self, **kwargs: Any) -> None:
        self._set_note_placement("endNotePr", **kwargs)

    # -- header/footer helpers ---------------------------------------------
    def _apply_id_attributes(self, tag: str) -> tuple[str, ...]:
        base = "header" if tag == "header" else "footer"
        return ("idRef", f"{base}IDRef", f"{base}IdRef", f"{base}Ref")

    def _apply_elements(self, tag: str) -> list[ET.Element]:
        return self.element.findall(f"{_HP}{tag}Apply")

    def _apply_reference(self, apply: ET.Element, tag: str) -> str | None:
        candidate_keys = {name.lower() for name in self._apply_id_attributes(tag)}
        for attr, value in apply.attrib.items():
            if attr.lower() in candidate_keys and value:
                return value
        return None

    def _match_apply_for_element(self, tag: str, element: ET.Element | None) -> ET.Element | None:
        if element is None:
            return None

        target_id = element.get("id")
        if target_id:
            for apply in self._apply_elements(tag):
                if self._apply_reference(apply, tag) == target_id:
                    return apply

        page_type = element.get("applyPageType", "BOTH")
        for apply in self._apply_elements(tag):
            if apply.get("applyPageType", "BOTH") == page_type:
                return apply
        return None

    def _set_apply_reference(
        self,
        apply: ET.Element,
        tag: str,
        new_id: str | None,
    ) -> bool:
        candidate_keys = {name.lower(): name for name in self._apply_id_attributes(tag)}
        existing_attrs = [
            attr for attr in list(apply.attrib.keys()) if attr.lower() in candidate_keys
        ]

        changed = False
        if new_id is None:
            for attr in existing_attrs:
                if attr in apply.attrib:
                    del apply.attrib[attr]
                    changed = True
            return changed

        if existing_attrs:
            target_attr = existing_attrs[0]
        else:
            target_attr = self._apply_id_attributes(tag)[0]

        if apply.get(target_attr) != new_id:
            apply.set(target_attr, new_id)
            changed = True

        for attr in existing_attrs:
            if attr != target_attr and attr in apply.attrib:
                del apply.attrib[attr]
                changed = True

        return changed

    def _ensure_header_footer_apply(
        self,
        tag: str,
        page_type: str,
        element: ET.Element,
    ) -> ET.Element:
        apply = self._match_apply_for_element(tag, element)
        header_id = element.get("id")
        changed = False
        if apply is None:
            attrs = {"applyPageType": page_type}
            if header_id is not None:
                attrs[self._apply_id_attributes(tag)[0]] = header_id
            apply = _append_child(self.element, f"{_HP}{tag}Apply", attrs)
            changed = True
        else:
            if apply.get("applyPageType") != page_type:
                apply.set("applyPageType", page_type)
                changed = True
            if self._set_apply_reference(apply, tag, header_id):
                changed = True
        if changed:
            self.section.mark_dirty()
        return apply

    def _remove_header_footer_apply(
        self,
        tag: str,
        page_type: str,
        element: ET.Element | None = None,
    ) -> bool:
        apply = self._match_apply_for_element(tag, element)
        if apply is None:
            for candidate in self._apply_elements(tag):
                if candidate.get("applyPageType", "BOTH") == page_type:
                    apply = candidate
                    break
        if apply is None and element is not None:
            target_id = element.get("id")
            if target_id:
                for candidate in self._apply_elements(tag):
                    if self._apply_reference(candidate, tag) == target_id:
                        apply = candidate
                        break
        if apply is None:
            return False
        self.element.remove(apply)
        return True

    def _find_header_footer(self, tag: str, page_type: str) -> ET.Element | None:
        for element in self.element.findall(f"{_HP}{tag}"):
            if element.get("applyPageType", "BOTH") == page_type:
                return element
        return None

    def _ensure_header_footer(self, tag: str, page_type: str) -> ET.Element:
        element = self._find_header_footer(tag, page_type)
        changed = False
        if element is None:
            element = _append_child(
                self.element,
                f"{_HP}{tag}",
                {"id": _object_id(), "applyPageType": page_type},
            )
            changed = True
        else:
            if element.get("applyPageType") != page_type:
                element.set("applyPageType", page_type)
                changed = True
        if element.get("id") is None:
            element.set("id", _object_id())
            changed = True
        if changed:
            self.section.mark_dirty()
        return element

    def _header_footer_control_run(self) -> ET.Element:
        paragraph = self.section.element.find(f"{_HP}p")
        if paragraph is None:
            paragraph = _append_child(
                self.section.element,
                f"{_HP}p",
                {"id": _paragraph_id(), **_DEFAULT_PARAGRAPH_ATTRS},
            )
        run = paragraph.find(f"{_HP}run")
        if run is None:
            run = _append_child(paragraph, f"{_HP}run", {"charPrIDRef": "0"})
        return run

    def _sync_header_footer_control(self, tag: str, source: ET.Element) -> None:
        run = self._header_footer_control_run()
        for ctrl in list(run.findall(f"{_HP}ctrl")):
            if ctrl.find(f"{_HP}{tag}") is not None:
                run.remove(ctrl)
        ctrl = _append_child(run, f"{_HP}ctrl", {})
        ctrl.append(deepcopy(source))
        self.section.mark_dirty()

    def _remove_header_footer_controls(self, tag: str) -> bool:
        removed = False
        for run in self.section.element.findall(f".//{_HP}run"):
            for ctrl in list(run.findall(f"{_HP}ctrl")):
                if ctrl.find(f"{_HP}{tag}") is not None:
                    run.remove(ctrl)
                    removed = True
        return removed

    @property
    def headers(self) -> list[HwpxOxmlSectionHeaderFooter]:
        wrappers: list[HwpxOxmlSectionHeaderFooter] = []
        for element in self.element.findall(f"{_HP}header"):
            apply = self._match_apply_for_element("header", element)
            wrappers.append(HwpxOxmlSectionHeaderFooter(element, self, apply))
        return wrappers

    @property
    def footers(self) -> list[HwpxOxmlSectionHeaderFooter]:
        wrappers: list[HwpxOxmlSectionHeaderFooter] = []
        for element in self.element.findall(f"{_HP}footer"):
            apply = self._match_apply_for_element("footer", element)
            wrappers.append(HwpxOxmlSectionHeaderFooter(element, self, apply))
        return wrappers

    def get_header(self, page_type: str = "BOTH") -> Optional[HwpxOxmlSectionHeaderFooter]:
        element = self._find_header_footer("header", page_type)
        if element is None:
            return None
        apply = self._match_apply_for_element("header", element)
        return HwpxOxmlSectionHeaderFooter(element, self, apply)

    def get_footer(self, page_type: str = "BOTH") -> Optional[HwpxOxmlSectionHeaderFooter]:
        element = self._find_header_footer("footer", page_type)
        if element is None:
            return None
        apply = self._match_apply_for_element("footer", element)
        return HwpxOxmlSectionHeaderFooter(element, self, apply)

    def set_header_text(self, text: str, page_type: str = "BOTH") -> HwpxOxmlSectionHeaderFooter:
        element = self._ensure_header_footer("header", page_type)
        apply = self._ensure_header_footer_apply("header", page_type, element)
        wrapper = HwpxOxmlSectionHeaderFooter(element, self, apply)
        wrapper.text = text
        self._sync_header_footer_control("header", element)
        return wrapper

    def set_footer_text(self, text: str, page_type: str = "BOTH") -> HwpxOxmlSectionHeaderFooter:
        element = self._ensure_header_footer("footer", page_type)
        apply = self._ensure_header_footer_apply("footer", page_type, element)
        wrapper = HwpxOxmlSectionHeaderFooter(element, self, apply)
        wrapper.text = text
        self._sync_header_footer_control("footer", element)
        return wrapper

    def set_header_content(
        self,
        content: Sequence[Mapping[str, Any]],
        page_type: str = "BOTH",
    ) -> HwpxOxmlSectionHeaderFooter:
        element = self._ensure_header_footer("header", page_type)
        apply = self._ensure_header_footer_apply("header", page_type, element)
        wrapper = HwpxOxmlSectionHeaderFooter(element, self, apply)
        wrapper.set_content(content)
        self._sync_header_footer_control("header", element)
        return wrapper

    def set_footer_content(
        self,
        content: Sequence[Mapping[str, Any]],
        page_type: str = "BOTH",
    ) -> HwpxOxmlSectionHeaderFooter:
        element = self._ensure_header_footer("footer", page_type)
        apply = self._ensure_header_footer_apply("footer", page_type, element)
        wrapper = HwpxOxmlSectionHeaderFooter(element, self, apply)
        wrapper.set_content(content)
        self._sync_header_footer_control("footer", element)
        return wrapper

    def remove_header(self, page_type: str = "BOTH") -> None:
        element = self._find_header_footer("header", page_type)
        removed = False
        if element is not None:
            self.element.remove(element)
            removed = True
        if self._remove_header_footer_apply("header", page_type, element):
            removed = True
        if self._remove_header_footer_controls("header"):
            removed = True
        if removed:
            self.section.mark_dirty()

    def remove_footer(self, page_type: str = "BOTH") -> None:
        element = self._find_header_footer("footer", page_type)
        removed = False
        if element is not None:
            self.element.remove(element)
            removed = True
        if self._remove_header_footer_apply("footer", page_type, element):
            removed = True
        if self._remove_header_footer_controls("footer"):
            removed = True
        if removed:
            self.section.mark_dirty()
