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
    _get_int_attr,
    _object_id,
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
