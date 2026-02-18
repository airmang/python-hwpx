"""Object model mapping for the XML parts of an HWPX document."""

from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable, Iterable, Iterator, Optional, Sequence, TypeVar
from uuid import uuid4
import xml.etree.ElementTree as ET

from lxml import etree as LET

from . import body
from .common import GenericElement
from .header import (
    Bullet,
    MemoProperties,
    MemoShape,
    ParagraphProperty,
    Style,
    TrackChange,
    TrackChangeAuthor,
    memo_shape_from_attributes,
    parse_bullets,
    parse_border_fills,
    parse_paragraph_properties,
    parse_styles,
    parse_track_change_authors,
    parse_track_changes,
)
from .utils import parse_int

ET.register_namespace("hp", "http://www.hancom.co.kr/hwpml/2011/paragraph")
ET.register_namespace("hs", "http://www.hancom.co.kr/hwpml/2011/section")
ET.register_namespace("hc", "http://www.hancom.co.kr/hwpml/2011/core")
ET.register_namespace("hh", "http://www.hancom.co.kr/hwpml/2011/head")
logger = logging.getLogger(__name__)

_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_HP = f"{{{_HP_NS}}}"
_HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
_HH = f"{{{_HH_NS}}}"

_DEFAULT_PARAGRAPH_ATTRS = {
    "paraPrIDRef": "0",
    "styleIDRef": "0",
    "pageBreak": "0",
    "columnBreak": "0",
    "merged": "0",
}

_DEFAULT_CELL_WIDTH = 7200
_DEFAULT_CELL_HEIGHT = 3600

_BASIC_BORDER_FILL_ATTRIBUTES = {
    "threeD": "0",
    "shadow": "0",
    "centerLine": "NONE",
    "breakCellSeparateLine": "0",
}

_BASIC_BORDER_CHILDREN: tuple[tuple[str, dict[str, str]], ...] = (
    ("slash", {"type": "NONE", "Crooked": "0", "isCounter": "0"}),
    ("backSlash", {"type": "NONE", "Crooked": "0", "isCounter": "0"}),
    ("leftBorder", {"type": "SOLID", "width": "0.12 mm", "color": "#000000"}),
    ("rightBorder", {"type": "SOLID", "width": "0.12 mm", "color": "#000000"}),
    ("topBorder", {"type": "SOLID", "width": "0.12 mm", "color": "#000000"}),
    ("bottomBorder", {"type": "SOLID", "width": "0.12 mm", "color": "#000000"}),
    ("diagonal", {"type": "SOLID", "width": "0.1 mm", "color": "#000000"}),
)

T = TypeVar("T")


def _serialize_xml(element: ET.Element) -> bytes:
    """Return a UTF-8 encoded XML document for *element*."""
    return ET.tostring(element, encoding="utf-8", xml_declaration=True)


def _paragraph_id() -> str:
    """Generate an identifier for a new paragraph element."""
    return str(uuid4().int & 0xFFFFFFFF)


def _object_id() -> str:
    """Generate an identifier suitable for table and shape objects."""
    return str(uuid4().int & 0xFFFFFFFF)


def _memo_id() -> str:
    """Generate a lightweight identifier for memo elements."""
    return str(uuid4().int & 0xFFFFFFFF)


def _create_paragraph_element(
    text: str,
    *,
    char_pr_id_ref: str | int | None = None,
    para_pr_id_ref: str | int | None = None,
    style_id_ref: str | int | None = None,
    paragraph_attributes: Optional[dict[str, str]] = None,
    run_attributes: Optional[dict[str, str]] = None,
) -> ET.Element:
    """Return a paragraph element populated with a single run and text node."""

    attrs = {"id": _paragraph_id(), **_DEFAULT_PARAGRAPH_ATTRS}
    attrs.update(paragraph_attributes or {})

    if para_pr_id_ref is not None:
        attrs["paraPrIDRef"] = str(para_pr_id_ref)
    if style_id_ref is not None:
        attrs["styleIDRef"] = str(style_id_ref)

    paragraph = ET.Element(f"{_HP}p", attrs)

    run_attrs: dict[str, str] = dict(run_attributes or {})
    if char_pr_id_ref is not None:
        run_attrs.setdefault("charPrIDRef", str(char_pr_id_ref))
    else:
        run_attrs.setdefault("charPrIDRef", "0")

    run = ET.SubElement(paragraph, f"{_HP}run", run_attrs)
    text_element = ET.SubElement(run, f"{_HP}t")
    text_element.text = text
    return paragraph


_LAYOUT_CACHE_ELEMENT_NAMES = {"linesegarray"}


def _clear_paragraph_layout_cache(paragraph: ET.Element) -> None:
    """Remove cached layout metadata such as ``<hp:lineSegArray>``."""

    for child in list(paragraph):
        if _element_local_name(child).lower() in _LAYOUT_CACHE_ELEMENT_NAMES:
            paragraph.remove(child)


def _element_local_name(node: ET.Element) -> str:
    tag = node.tag
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _normalize_length(value: str | None) -> str:
    if value is None:
        return ""
    return value.replace(" ", "").lower()


def _border_fill_is_basic_solid_line(element: ET.Element) -> bool:
    if _element_local_name(element) != "borderFill":
        return False

    for attr, expected in _BASIC_BORDER_FILL_ATTRIBUTES.items():
        actual = element.get(attr)
        if attr == "centerLine":
            if (actual or "").upper() != expected:
                return False
        else:
            if actual != expected:
                return False

    for child_name, child_attrs in _BASIC_BORDER_CHILDREN:
        child = element.find(f"{_HH}{child_name}")
        if child is None:
            return False
        for attr, expected in child_attrs.items():
            actual = child.get(attr)
            if attr == "type":
                if (actual or "").upper() != expected:
                    return False
            elif attr == "width":
                if _normalize_length(actual) != _normalize_length(expected):
                    return False
            elif attr == "color":
                if (actual or "").upper() != expected.upper():
                    return False
            else:
                if actual != expected:
                    return False

    for child in element:
        if _element_local_name(child) == "fillBrush":
            return False

    return True


def _create_basic_border_fill_element(border_id: str) -> ET.Element:
    attrs = {"id": border_id, **_BASIC_BORDER_FILL_ATTRIBUTES}
    element = ET.Element(f"{_HH}borderFill", attrs)
    for child_name, child_attrs in _BASIC_BORDER_CHILDREN:
        ET.SubElement(element, f"{_HH}{child_name}", dict(child_attrs))
    return element


def _distribute_size(total: int, parts: int) -> list[int]:
    """Return *parts* integers that sum to *total* and are as even as possible."""

    if parts <= 0:
        return []

    base = total // parts
    remainder = total - (base * parts)
    sizes: list[int] = []
    for index in range(parts):
        value = base
        if remainder > 0:
            value += 1
            remainder -= 1
        sizes.append(max(value, 0))
    return sizes


def _default_cell_attributes(border_fill_id_ref: str) -> dict[str, str]:
    return {
        "name": "",
        "header": "0",
        "hasMargin": "0",
        "protect": "0",
        "editable": "0",
        "dirty": "0",
        "borderFillIDRef": border_fill_id_ref,
    }


def _default_sublist_attributes() -> dict[str, str]:
    return {
        "id": "",
        "textDirection": "HORIZONTAL",
        "lineWrap": "BREAK",
        "vertAlign": "CENTER",
        "linkListIDRef": "0",
        "linkListNextIDRef": "0",
        "textWidth": "0",
        "textHeight": "0",
        "hasTextRef": "0",
        "hasNumRef": "0",
    }


def _default_cell_paragraph_attributes() -> dict[str, str]:
    attrs = dict(_DEFAULT_PARAGRAPH_ATTRS)
    attrs["id"] = _paragraph_id()
    return attrs


def _default_cell_margin_attributes() -> dict[str, str]:
    return {"left": "0", "right": "0", "top": "0", "bottom": "0"}


def _get_int_attr(element: ET.Element, name: str, default: int = 0) -> int:
    """Return *name* attribute of *element* as an integer."""

    value = element.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


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
class SectionStartNumbering:
    """Starting numbers for section-level counters."""

    page_starts_on: str
    page: int
    picture: int
    table: int
    equation: int


@dataclass(slots=True)
class DocumentNumbering:
    """Document-wide numbering initial values defined in ``<hh:beginNum>``."""

    page: int = 1
    footnote: int = 1
    endnote: int = 1
    picture: int = 1
    table: int = 1
    equation: int = 1


@dataclass(slots=True)
class RunStyle:
    """Represents the resolved character style applied to a run."""

    id: str
    attributes: dict[str, str]
    child_attributes: dict[str, dict[str, str]]

    def text_color(self) -> str | None:
        return self.attributes.get("textColor")

    def underline_type(self) -> str | None:
        underline = self.child_attributes.get("underline")
        if underline is None:
            return None
        return underline.get("type")

    def underline_color(self) -> str | None:
        underline = self.child_attributes.get("underline")
        if underline is None:
            return None
        return underline.get("color")

    def matches(
        self,
        *,
        text_color: str | None = None,
        underline_type: str | None = None,
        underline_color: str | None = None,
    ) -> bool:
        if text_color is not None and self.text_color() != text_color:
            return False
        if underline_type is not None and self.underline_type() != underline_type:
            return False
        if underline_color is not None and self.underline_color() != underline_color:
            return False
        return True


def _char_properties_from_header(element: ET.Element) -> dict[str, RunStyle]:
    mapping: dict[str, RunStyle] = {}
    ref_list = element.find(f"{_HH}refList")
    if ref_list is None:
        return mapping
    char_props_element = ref_list.find(f"{_HH}charProperties")
    if char_props_element is None:
        return mapping

    for child in char_props_element.findall(f"{_HH}charPr"):
        char_id = child.get("id")
        if not char_id:
            continue
        attributes = {key: value for key, value in child.attrib.items() if key != "id"}
        child_attributes: dict[str, dict[str, str]] = {}
        for grandchild in child:
            if len(list(grandchild)) == 0 and (grandchild.text is None or not grandchild.text.strip()):
                child_attributes[_element_local_name(grandchild)] = {
                    key: value for key, value in grandchild.attrib.items()
                }
        style = RunStyle(id=char_id, attributes=attributes, child_attributes=child_attributes)
        if char_id not in mapping:
            mapping[char_id] = style
        try:
            normalized = str(int(char_id))
        except (TypeError, ValueError):
            normalized = None
        if normalized and normalized not in mapping:
            mapping[normalized] = style
    return mapping


class HwpxOxmlSectionHeaderFooter:
    """Wraps a ``<hp:header>`` or ``<hp:footer>`` element."""

    def __init__(
        self,
        element: ET.Element,
        properties: "HwpxOxmlSectionProperties",
        apply_element: ET.Element | None = None,
    ):
        self.element = element
        self._properties = properties
        self._apply_element = apply_element

    @property
    def apply_element(self) -> ET.Element | None:
        """Return the corresponding ``<hp:headerApply>``/``<hp:footerApply>`` element."""

        return self._apply_element

    @property
    def id(self) -> str | None:
        """Return the identifier assigned to the header/footer element."""

        return self.element.get("id")

    @id.setter
    def id(self, value: str | None) -> None:
        if value is None:
            changed = False
            if "id" in self.element.attrib:
                del self.element.attrib["id"]
                changed = True
            if self._update_apply_reference(None):
                changed = True
            if changed:
                self._properties.section.mark_dirty()
            return

        new_value = str(value)
        changed = False
        if self.element.get("id") != new_value:
            self.element.set("id", new_value)
            changed = True
        if self._update_apply_reference(new_value):
            changed = True
        if changed:
            self._properties.section.mark_dirty()

    @property
    def apply_page_type(self) -> str:
        """Return the page type the header/footer applies to."""

        value = self.element.get("applyPageType")
        if value is not None:
            return value
        if self._apply_element is not None:
            return self._apply_element.get("applyPageType", "BOTH")
        return "BOTH"

    @apply_page_type.setter
    def apply_page_type(self, value: str) -> None:
        changed = False
        if self.element.get("applyPageType") != value:
            self.element.set("applyPageType", value)
            changed = True
        if self._apply_element is not None and self._apply_element.get("applyPageType") != value:
            self._apply_element.set("applyPageType", value)
            changed = True
        if changed:
            self._properties.section.mark_dirty()

    def _apply_id_attributes(self) -> tuple[str, ...]:
        if self.element.tag.endswith("header"):
            return ("idRef", "headerIDRef", "headerIdRef", "headerRef")
        return ("idRef", "footerIDRef", "footerIdRef", "footerRef")

    def _update_apply_reference(self, value: str | None) -> bool:
        apply = self._apply_element
        if apply is None:
            return False

        candidate_keys = {name.lower() for name in self._apply_id_attributes()}
        attr_candidates: list[str] = []
        for name in list(apply.attrib.keys()):
            if name.lower() in candidate_keys:
                attr_candidates.append(name)

        changed = False
        if value is None:
            for attr in attr_candidates:
                if attr in apply.attrib:
                    del apply.attrib[attr]
                    changed = True
            return changed

        target_attr = None
        for attr in attr_candidates:
            lower = attr.lower()
            if lower == "idref" or (
                self.element.tag.endswith("header") and "header" in lower
            ) or (
                self.element.tag.endswith("footer") and "footer" in lower
            ):
                target_attr = attr
                break
        if target_attr is None:
            target_attr = self._apply_id_attributes()[0]

        if apply.get(target_attr) != value:
            apply.set(target_attr, value)
            changed = True

        for attr in list(apply.attrib.keys()):
            if attr == target_attr:
                continue
            if attr.lower() in candidate_keys:
                del apply.attrib[attr]
                changed = True

        return changed

    def _initial_sublist_attributes(self) -> dict[str, str]:
        attrs = dict(_default_sublist_attributes())
        attrs["vertAlign"] = "TOP" if self.element.tag.endswith("header") else "BOTTOM"
        return attrs

    def _ensure_text_element(self) -> ET.Element:
        sublist = self.element.find(f"{_HP}subList")
        if sublist is None:
            sublist = ET.SubElement(self.element, f"{_HP}subList", self._initial_sublist_attributes())
        paragraph = sublist.find(f"{_HP}p")
        if paragraph is None:
            paragraph_attrs = dict(_DEFAULT_PARAGRAPH_ATTRS)
            paragraph_attrs["id"] = _paragraph_id()
            paragraph = ET.SubElement(sublist, f"{_HP}p", paragraph_attrs)
        run = paragraph.find(f"{_HP}run")
        if run is None:
            run = ET.SubElement(paragraph, f"{_HP}run", {"charPrIDRef": "0"})
        text = run.find(f"{_HP}t")
        if text is None:
            text = ET.SubElement(run, f"{_HP}t")
        return text

    @property
    def text(self) -> str:
        """Return the concatenated text content of the header/footer."""

        parts: list[str] = []
        for node in self.element.findall(f".//{_HP}t"):
            if node.text:
                parts.append(node.text)
        return "".join(parts)

    @text.setter
    def text(self, value: str) -> None:
        # Replace existing content with a simple paragraph.
        for child in list(self.element):
            if child.tag == f"{_HP}subList":
                self.element.remove(child)
        text_node = self._ensure_text_element()
        text_node.text = value
        self._properties.section.mark_dirty()


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
            apply = ET.SubElement(self.element, f"{_HP}{tag}Apply", attrs)
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
            element = ET.SubElement(
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
        return wrapper

    def set_footer_text(self, text: str, page_type: str = "BOTH") -> HwpxOxmlSectionHeaderFooter:
        element = self._ensure_header_footer("footer", page_type)
        apply = self._ensure_header_footer_apply("footer", page_type, element)
        wrapper = HwpxOxmlSectionHeaderFooter(element, self, apply)
        wrapper.text = text
        return wrapper

    def remove_header(self, page_type: str = "BOTH") -> None:
        element = self._find_header_footer("header", page_type)
        removed = False
        if element is not None:
            self.element.remove(element)
            removed = True
        if self._remove_header_footer_apply("header", page_type, element):
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
        if removed:
            self.section.mark_dirty()


class HwpxOxmlRun:
    """Lightweight wrapper around an ``<hp:run>`` element."""

    def __init__(self, element: ET.Element, paragraph: "HwpxOxmlParagraph"):
        self.element = element
        self.paragraph = paragraph

    def to_model(self) -> "body.Run":
        xml_bytes = ET.tostring(self.element, encoding="utf-8")
        node = LET.fromstring(xml_bytes)
        return body.parse_run_element(node)

    @property
    def model(self) -> "body.Run":
        return self.to_model()

    def apply_model(self, model: "body.Run") -> None:
        new_node = body.serialize_run(model)
        xml_bytes = LET.tostring(new_node)
        replacement = ET.fromstring(xml_bytes)
        parent = self.paragraph.element
        run_children = list(parent)
        index = run_children.index(self.element)
        parent.remove(self.element)
        parent.insert(index, replacement)
        self.element = replacement
        self.paragraph.section.mark_dirty()

    def _current_format_flags(self) -> tuple[bool, bool, bool] | None:
        style = self.style
        if style is None:
            return None
        bold = "bold" in style.child_attributes
        italic = "italic" in style.child_attributes
        underline_attrs = style.child_attributes.get("underline")
        underline = False
        if underline_attrs is not None:
            underline = underline_attrs.get("type", "").upper() != "NONE"
        return bold, italic, underline

    def _apply_format_change(
        self,
        *,
        bold: bool | None = None,
        italic: bool | None = None,
        underline: bool | None = None,
    ) -> None:
        document = self.paragraph.section.document
        if document is None:
            raise RuntimeError("run is not attached to a document")

        current = self._current_format_flags()
        if current is None:
            current = (False, False, False)

        target = [
            current[0] if bold is None else bool(bold),
            current[1] if italic is None else bool(italic),
            current[2] if underline is None else bool(underline),
        ]

        if tuple(target) == current:
            return

        style_id = document.ensure_run_style(
            bold=target[0],
            italic=target[1],
            underline=target[2],
        )
        self.char_pr_id_ref = style_id

    @property
    def char_pr_id_ref(self) -> str | None:
        """Return the character property reference applied to the run."""
        return self.element.get("charPrIDRef")

    @char_pr_id_ref.setter
    def char_pr_id_ref(self, value: str | int | None) -> None:
        if value is None:
            if "charPrIDRef" in self.element.attrib:
                del self.element.attrib["charPrIDRef"]
                self.paragraph.section.mark_dirty()
            return

        new_value = str(value)
        if self.element.get("charPrIDRef") != new_value:
            self.element.set("charPrIDRef", new_value)
            self.paragraph.section.mark_dirty()

    def _plain_text_nodes(self) -> list[ET.Element]:
        return [
            node
            for node in self.element.findall(f"{_HP}t")
            if len(list(node)) == 0
        ]

    def _ensure_plain_text_node(self) -> ET.Element:
        nodes = self._plain_text_nodes()
        if nodes:
            return nodes[0]
        return ET.SubElement(self.element, f"{_HP}t")

    @property
    def text(self) -> str:
        parts: list[str] = []
        for node in self.element.findall(f"{_HP}t"):
            parts.append("".join(node.itertext()))
        return "".join(parts)

    @text.setter
    def text(self, value: str) -> None:
        primary = self._ensure_plain_text_node()
        changed = (primary.text or "") != value
        primary.text = value
        for node in self._plain_text_nodes()[1:]:
            if node.text:
                node.text = ""
                changed = True
        if changed:
            self.paragraph.section.mark_dirty()

    @property
    def style(self) -> RunStyle | None:
        document = self.paragraph.section.document
        if document is None:
            return None
        char_pr_id = self.char_pr_id_ref
        if char_pr_id is None:
            return None
        return document.char_property(char_pr_id)

    def replace_text(
        self,
        search: str,
        replacement: str,
        *,
        count: int | None = None,
    ) -> int:
        """Replace ``search`` with ``replacement`` within ``<hp:t>`` nodes.

        The replacement traverses nested markup tags (e.g. highlights) and
        preserves the existing element structure so formatting metadata remains
        intact. Returns the number of replacements that were performed.
        """

        if not search:
            raise ValueError("search text must be a non-empty string")

        if count is not None and count <= 0:
            return 0

        # Helper structure to keep references to text segments and update them
        # while editing nested nodes.
        class _Segment:
            __slots__ = ("element", "attr", "text")

            def __init__(self, element: ET.Element, attr: str, text: str) -> None:
                self.element = element
                self.attr = attr
                self.text = text

            def set(self, value: str) -> None:
                self.text = value
                if value:
                    setattr(self.element, self.attr, value)
                else:
                    setattr(self.element, self.attr, "")

        def _gather_segments(node: ET.Element) -> list[_Segment]:
            segments: list[_Segment] = []

            def visit(element: ET.Element) -> None:
                text_value = element.text or ""
                segments.append(_Segment(element, "text", text_value))
                for child in list(element):
                    visit(child)
                    tail_value = child.tail or ""
                    segments.append(_Segment(child, "tail", tail_value))

            visit(node)
            return segments

        def _segment_boundaries(segments: Sequence[_Segment]) -> list[tuple[int, int]]:
            bounds: list[tuple[int, int]] = []
            offset = 0
            for segment in segments:
                start = offset
                offset += len(segment.text)
                bounds.append((start, offset))
            return bounds

        def _distribute(total: int, weights: Sequence[int]) -> list[int]:
            if not weights:
                return []
            if total <= 0:
                return [0 for _ in weights]
            weight_sum = sum(weights)
            if weight_sum <= 0:
                # Evenly spread characters when no weight information is
                # available (e.g. replacement inside empty segments).
                base = total // len(weights)
                remainder = total - base * len(weights)
                allocation = [base] * len(weights)
                for index in range(remainder):
                    allocation[index] += 1
                return allocation

            allocation = []
            remainder = total
            residuals: list[tuple[int, int]] = []
            for index, weight in enumerate(weights):
                share = total * weight // weight_sum
                allocation.append(share)
                remainder -= share
                residuals.append((total * weight % weight_sum, index))

            # Distribute leftover characters based on the size of the modulus so
            # that larger weights receive the extra characters first.
            residuals.sort(key=lambda item: (-item[0], item[1]))
            idx = 0
            while remainder > 0 and residuals:
                _, target = residuals[idx]
                allocation[target] += 1
                remainder -= 1
                idx = (idx + 1) % len(residuals)

            if remainder > 0:
                allocation[-1] += remainder
            return allocation

        def _apply_replacement(
            segments: list[_Segment],
            start: int,
            end: int,
            replacement_text: str,
        ) -> None:
            bounds = _segment_boundaries(segments)
            affected: list[tuple[int, int, int]] = []
            for index, (seg_start, seg_end) in enumerate(bounds):
                if start >= seg_end or end <= seg_start:
                    continue
                local_start = max(0, start - seg_start)
                local_end = min(len(segments[index].text), end - seg_start)
                affected.append((index, local_start, local_end))

            if not affected:
                return

            weights = [local_end - local_start for _, local_start, local_end in affected]
            allocation = _distribute(len(replacement_text), weights)

            replacement_offset = 0
            first_index = affected[0][0]
            last_index = affected[-1][0]

            for (segment_index, local_start, local_end), share in zip(affected, allocation):
                segment = segments[segment_index]
                prefix = segment.text[:local_start] if segment_index == first_index else ""
                suffix = segment.text[local_end:] if segment_index == last_index else ""
                portion = replacement_text[replacement_offset : replacement_offset + share]
                replacement_offset += share
                segment.set(prefix + portion + suffix)

        segments: list[_Segment] = []
        for text_node in self.element.findall(f"{_HP}t"):
            segments.extend(_gather_segments(text_node))

        if not segments:
            return 0

        total_replacements = 0
        remaining = count
        search_start = 0
        combined = "".join(segment.text for segment in segments)

        while True:
            if remaining is not None and remaining <= 0:
                break
            position = combined.find(search, search_start)
            if position == -1:
                break
            end_position = position + len(search)
            _apply_replacement(segments, position, end_position, replacement)
            total_replacements += 1
            if remaining is not None:
                remaining -= 1
            combined = "".join(segment.text for segment in segments)
            if replacement:
                search_start = position + len(replacement)
            else:
                search_start = position
            if search_start > len(combined):
                search_start = len(combined)

        if total_replacements:
            self.paragraph.section.mark_dirty()
        return total_replacements

    def remove(self) -> None:
        parent = self.paragraph.element
        try:
            parent.remove(self.element)
        except ValueError:  # pragma: no cover - defensive branch
            return
        self.paragraph.section.mark_dirty()

    @property
    def bold(self) -> bool | None:
        flags = self._current_format_flags()
        if flags is None:
            return None
        return flags[0]

    @bold.setter
    def bold(self, value: bool | None) -> None:
        self._apply_format_change(bold=value)

    @property
    def italic(self) -> bool | None:
        flags = self._current_format_flags()
        if flags is None:
            return None
        return flags[1]

    @italic.setter
    def italic(self, value: bool | None) -> None:
        self._apply_format_change(italic=value)

    @property
    def underline(self) -> bool | None:
        flags = self._current_format_flags()
        if flags is None:
            return None
        return flags[2]

    @underline.setter
    def underline(self, value: bool | None) -> None:
        self._apply_format_change(underline=value)


class HwpxOxmlMemoGroup:
    """Wrapper providing access to ``<hp:memogroup>`` containers."""

    def __init__(self, element: ET.Element, section: "HwpxOxmlSection"):
        self.element = element
        self.section = section

    @property
    def memos(self) -> list["HwpxOxmlMemo"]:
        return [
            HwpxOxmlMemo(child, self)
            for child in self.element.findall(f"{_HP}memo")
        ]

    def add_memo(
        self,
        text: str = "",
        *,
        memo_shape_id_ref: str | int | None = None,
        memo_id: str | None = None,
        char_pr_id_ref: str | int | None = None,
        attributes: Optional[dict[str, str]] = None,
    ) -> "HwpxOxmlMemo":
        memo_attrs = dict(attributes or {})
        memo_attrs.setdefault("id", memo_id or _memo_id())
        if memo_shape_id_ref is not None:
            memo_attrs.setdefault("memoShapeIDRef", str(memo_shape_id_ref))
        memo_element = ET.SubElement(self.element, f"{_HP}memo", memo_attrs)
        memo = HwpxOxmlMemo(memo_element, self)
        memo.set_text(text, char_pr_id_ref=char_pr_id_ref)
        self.section.mark_dirty()
        return memo

    def _cleanup(self) -> None:
        if list(self.element):
            return
        try:
            self.section.element.remove(self.element)
        except ValueError:  # pragma: no cover - defensive branch
            return
        self.section.mark_dirty()


class HwpxOxmlMemo:
    """Represents a memo entry contained within a memo group."""

    def __init__(self, element: ET.Element, group: HwpxOxmlMemoGroup):
        self.element = element
        self.group = group

    @property
    def id(self) -> str | None:
        return self.element.get("id")

    @id.setter
    def id(self, value: str | None) -> None:
        if value is None:
            if "id" in self.element.attrib:
                del self.element.attrib["id"]
                self.group.section.mark_dirty()
            return
        new_value = str(value)
        if self.element.get("id") != new_value:
            self.element.set("id", new_value)
            self.group.section.mark_dirty()

    @property
    def memo_shape_id_ref(self) -> str | None:
        return self.element.get("memoShapeIDRef")

    @memo_shape_id_ref.setter
    def memo_shape_id_ref(self, value: str | int | None) -> None:
        if value is None:
            if "memoShapeIDRef" in self.element.attrib:
                del self.element.attrib["memoShapeIDRef"]
                self.group.section.mark_dirty()
            return
        new_value = str(value)
        if self.element.get("memoShapeIDRef") != new_value:
            self.element.set("memoShapeIDRef", new_value)
            self.group.section.mark_dirty()

    @property
    def attributes(self) -> dict[str, str]:
        return dict(self.element.attrib)

    def set_attribute(self, name: str, value: str | int | None) -> None:
        if value is None:
            if name in self.element.attrib:
                del self.element.attrib[name]
                self.group.section.mark_dirty()
            return
        new_value = str(value)
        if self.element.get(name) != new_value:
            self.element.set(name, new_value)
            self.group.section.mark_dirty()

    def _infer_char_pr_id_ref(self) -> str | None:
        for paragraph in self.paragraphs:
            for run in paragraph.runs:
                if run.char_pr_id_ref:
                    return run.char_pr_id_ref
        return None

    @property
    def paragraphs(self) -> list["HwpxOxmlParagraph"]:
        paragraphs: list[HwpxOxmlParagraph] = []
        for node in self.element.findall(f".//{_HP}p"):
            paragraphs.append(HwpxOxmlParagraph(node, self.group.section))
        return paragraphs

    @property
    def text(self) -> str:
        parts: list[str] = []
        for paragraph in self.paragraphs:
            value = paragraph.text
            if value:
                parts.append(value)
        return "\n".join(parts)

    def set_text(
        self,
        value: str,
        *,
        char_pr_id_ref: str | int | None = None,
    ) -> None:
        desired = value or ""
        existing_char = char_pr_id_ref or self._infer_char_pr_id_ref()
        for child in list(self.element):
            if _element_local_name(child) in {"paraList", "p"}:
                self.element.remove(child)
        para_list = ET.SubElement(self.element, f"{_HP}paraList")
        paragraph = _create_paragraph_element(
            desired,
            char_pr_id_ref=existing_char if existing_char is not None else "0",
        )
        para_list.append(paragraph)
        self.group.section.mark_dirty()

    @text.setter
    def text(self, value: str) -> None:
        self.set_text(value)

    def remove(self) -> None:
        try:
            self.group.element.remove(self.element)
        except ValueError:  # pragma: no cover - defensive branch
            return
        self.group.section.mark_dirty()
        self.group._cleanup()


class HwpxOxmlInlineObject:
    """Wrapper providing attribute helpers for inline objects."""

    def __init__(self, element: ET.Element, paragraph: "HwpxOxmlParagraph"):
        self.element = element
        self.paragraph = paragraph

    @property
    def tag(self) -> str:
        """Return the fully qualified XML tag for the inline object."""

        return self.element.tag

    @property
    def attributes(self) -> dict[str, str]:
        """Return a copy of the element attributes."""

        return dict(self.element.attrib)

    def get_attribute(self, name: str) -> str | None:
        """Return the value of attribute *name* if present."""

        return self.element.get(name)

    def set_attribute(self, name: str, value: str | int | None) -> None:
        """Update or remove attribute *name* and mark the paragraph dirty."""

        if value is None:
            if name in self.element.attrib:
                del self.element.attrib[name]
                self.paragraph.section.mark_dirty()
            return

        new_value = str(value)
        if self.element.get(name) != new_value:
            self.element.set(name, new_value)
            self.paragraph.section.mark_dirty()


class HwpxOxmlTableCell:
    """Represents an individual table cell."""

    def __init__(
        self,
        element: ET.Element,
        table: "HwpxOxmlTable",
        row_element: ET.Element,
    ):
        self.element = element
        self.table = table
        self._row_element = row_element

    def _addr_element(self) -> ET.Element | None:
        return self.element.find(f"{_HP}cellAddr")

    def _span_element(self) -> ET.Element:
        span = self.element.find(f"{_HP}cellSpan")
        if span is None:
            span = ET.SubElement(self.element, f"{_HP}cellSpan", {"colSpan": "1", "rowSpan": "1"})
        return span

    def _size_element(self) -> ET.Element:
        size = self.element.find(f"{_HP}cellSz")
        if size is None:
            size = ET.SubElement(self.element, f"{_HP}cellSz", {"width": "0", "height": "0"})
        return size

    def _ensure_text_element(self) -> ET.Element:
        sublist = self.element.find(f"{_HP}subList")
        if sublist is None:
            sublist = ET.SubElement(self.element, f"{_HP}subList", _default_sublist_attributes())
        paragraph = sublist.find(f"{_HP}p")
        if paragraph is None:
            paragraph = ET.SubElement(sublist, f"{_HP}p", _default_cell_paragraph_attributes())
        _clear_paragraph_layout_cache(paragraph)
        run = paragraph.find(f"{_HP}run")
        if run is None:
            run = ET.SubElement(paragraph, f"{_HP}run", {"charPrIDRef": "0"})
        text = run.find(f"{_HP}t")
        if text is None:
            text = ET.SubElement(run, f"{_HP}t")
        return text

    @property
    def address(self) -> tuple[int, int]:
        addr = self._addr_element()
        if addr is None:
            return (0, 0)
        row = int(addr.get("rowAddr", "0"))
        col = int(addr.get("colAddr", "0"))
        return (row, col)

    @property
    def span(self) -> tuple[int, int]:
        span = self._span_element()
        row_span = int(span.get("rowSpan", "1"))
        col_span = int(span.get("colSpan", "1"))
        return (row_span, col_span)

    def set_span(self, row_span: int, col_span: int) -> None:
        span = self._span_element()
        span.set("rowSpan", str(max(row_span, 1)))
        span.set("colSpan", str(max(col_span, 1)))
        self.table.mark_dirty()

    @property
    def width(self) -> int:
        size = self._size_element()
        return int(size.get("width", "0"))

    @property
    def height(self) -> int:
        size = self._size_element()
        return int(size.get("height", "0"))

    def set_size(self, width: int | None = None, height: int | None = None) -> None:
        size = self._size_element()
        if width is not None:
            size.set("width", str(max(width, 0)))
        if height is not None:
            size.set("height", str(max(height, 0)))
        self.table.mark_dirty()

    @property
    def text(self) -> str:
        text_element = self.element.find(f".//{_HP}t")
        if text_element is None or text_element.text is None:
            return ""
        return text_element.text

    @text.setter
    def text(self, value: str) -> None:
        text_element = self._ensure_text_element()
        text_element.text = value
        self.element.set("dirty", "1")
        self.table.mark_dirty()

    def remove(self) -> None:
        self._row_element.remove(self.element)
        self.table.mark_dirty()


@dataclass(frozen=True)
class HwpxTableGridPosition:
    """Mapping between a logical table position and a physical cell."""

    row: int
    column: int
    cell: HwpxOxmlTableCell
    anchor: tuple[int, int]
    span: tuple[int, int]

    @property
    def is_anchor(self) -> bool:
        return (self.row, self.column) == self.anchor

    @property
    def row_span(self) -> int:
        return self.span[0]

    @property
    def col_span(self) -> int:
        return self.span[1]


class HwpxOxmlTableRow:
    """Represents a table row."""

    def __init__(self, element: ET.Element, table: "HwpxOxmlTable"):
        self.element = element
        self.table = table

    @property
    def cells(self) -> list[HwpxOxmlTableCell]:
        return [
            HwpxOxmlTableCell(cell_element, self.table, self.element)
            for cell_element in self.element.findall(f"{_HP}tc")
        ]


class HwpxOxmlTable:
    """Representation of an ``<hp:tbl>`` inline object."""

    def __init__(self, element: ET.Element, paragraph: "HwpxOxmlParagraph"):
        self.element = element
        self.paragraph = paragraph

    def __repr__(self) -> str:
        """Return a compact and safe summary of table geometry."""

        return (
            f"{self.__class__.__name__}("
            f"rows={self.row_count}, "
            f"cols={self.column_count}, "
            f"physical_rows={len(self.rows)}"
            ")"
        )

    @classmethod
    def create(
        cls,
        rows: int,
        cols: int,
        *,
        width: int | None = None,
        height: int | None = None,
        border_fill_id_ref: str | int | None = None,
    ) -> ET.Element:
        if rows <= 0 or cols <= 0:
            raise ValueError("rows and cols must be positive integers")

        table_width = width if width is not None else cols * _DEFAULT_CELL_WIDTH
        table_height = height if height is not None else rows * _DEFAULT_CELL_HEIGHT
        if border_fill_id_ref is None:
            raise ValueError("border_fill_id_ref must be provided")
        border_fill = str(border_fill_id_ref)

        table_attrs = {
            "id": _object_id(),
            "zOrder": "0",
            "numberingType": "TABLE",
            "textWrap": "TOP_AND_BOTTOM",
            "textFlow": "BOTH_SIDES",
            "lock": "0",
            "dropcapstyle": "None",
            "pageBreak": "CELL",
            "repeatHeader": "0",
            "rowCnt": str(rows),
            "colCnt": str(cols),
            "cellSpacing": "0",
            "borderFillIDRef": border_fill,
            "noAdjust": "0",
        }

        table = ET.Element(f"{_HP}tbl", table_attrs)
        ET.SubElement(
            table,
            f"{_HP}sz",
            {
                "width": str(max(table_width, 0)),
                "widthRelTo": "ABSOLUTE",
                "height": str(max(table_height, 0)),
                "heightRelTo": "ABSOLUTE",
                "protect": "0",
            },
        )
        ET.SubElement(
            table,
            f"{_HP}pos",
            {
                "treatAsChar": "1",
                "affectLSpacing": "0",
                "flowWithText": "1",
                "allowOverlap": "0",
                "holdAnchorAndSO": "0",
                "vertRelTo": "PARA",
                "horzRelTo": "COLUMN",
                "vertAlign": "TOP",
                "horzAlign": "LEFT",
                "vertOffset": "0",
                "horzOffset": "0",
            },
        )
        ET.SubElement(table, f"{_HP}outMargin", _default_cell_margin_attributes())
        ET.SubElement(table, f"{_HP}inMargin", _default_cell_margin_attributes())

        column_widths = _distribute_size(max(table_width, 0), cols)
        row_heights = _distribute_size(max(table_height, 0), rows)

        for row_index in range(rows):
            row = ET.SubElement(table, f"{_HP}tr")
            for col_index in range(cols):
                cell = ET.SubElement(row, f"{_HP}tc", _default_cell_attributes(border_fill))
                sublist = ET.SubElement(cell, f"{_HP}subList", _default_sublist_attributes())
                paragraph = ET.SubElement(sublist, f"{_HP}p", _default_cell_paragraph_attributes())
                run = ET.SubElement(paragraph, f"{_HP}run", {"charPrIDRef": "0"})
                ET.SubElement(run, f"{_HP}t")
                ET.SubElement(
                    cell,
                    f"{_HP}cellAddr",
                    {"colAddr": str(col_index), "rowAddr": str(row_index)},
                )
                ET.SubElement(cell, f"{_HP}cellSpan", {"colSpan": "1", "rowSpan": "1"})
                ET.SubElement(
                    cell,
                    f"{_HP}cellSz",
                    {
                        "width": str(column_widths[col_index] if column_widths else 0),
                        "height": str(row_heights[row_index] if row_heights else 0),
                    },
                )
                ET.SubElement(cell, f"{_HP}cellMargin", _default_cell_margin_attributes())
        return table

    def mark_dirty(self) -> None:
        self.paragraph.section.mark_dirty()

    @property
    def row_count(self) -> int:
        value = self.element.get("rowCnt")
        if value is not None and value.isdigit():
            return int(value)
        return len(self.element.findall(f"{_HP}tr"))

    @property
    def column_count(self) -> int:
        value = self.element.get("colCnt")
        if value is not None and value.isdigit():
            return int(value)
        first_row = self.element.find(f"{_HP}tr")
        if first_row is None:
            return 0
        return len(first_row.findall(f"{_HP}tc"))

    @property
    def rows(self) -> list[HwpxOxmlTableRow]:
        return [HwpxOxmlTableRow(row, self) for row in self.element.findall(f"{_HP}tr")]

    def _build_cell_grid(self) -> dict[tuple[int, int], HwpxTableGridPosition]:
        mapping: dict[tuple[int, int], HwpxTableGridPosition] = {}
        for row in self.element.findall(f"{_HP}tr"):
            for cell_element in row.findall(f"{_HP}tc"):
                wrapper = HwpxOxmlTableCell(cell_element, self, row)
                start_row, start_col = wrapper.address
                span_row, span_col = wrapper.span
                for logical_row in range(start_row, start_row + span_row):
                    for logical_col in range(start_col, start_col + span_col):
                        key = (logical_row, logical_col)
                        existing = mapping.get(key)
                        entry = HwpxTableGridPosition(
                            row=logical_row,
                            column=logical_col,
                            cell=wrapper,
                            anchor=(start_row, start_col),
                            span=(span_row, span_col),
                        )
                        if (
                            existing is not None
                            and existing.cell.element is not wrapper.element
                        ):
                            raise ValueError(
                                "table grid contains overlapping cell spans"
                            )
                        mapping[key] = entry
        return mapping

    def _grid_entry(self, row_index: int, col_index: int) -> HwpxTableGridPosition:
        if row_index < 0 or col_index < 0:
            raise IndexError("row_index and col_index must be non-negative")

        row_count = self.row_count
        col_count = self.column_count
        if row_index >= row_count or col_index >= col_count:
            raise IndexError(
                "cell coordinates (%d, %d) exceed table bounds %dx%d"
                % (row_index, col_index, row_count, col_count)
            )

        entry = self._build_cell_grid().get((row_index, col_index))
        if entry is None:
            raise IndexError(
                "cell coordinates (%d, %d) are covered by a merged cell"
                " without an accessible anchor; inspect iter_grid() for details"
                % (row_index, col_index)
            )
        return entry

    def iter_grid(self) -> Iterator[HwpxTableGridPosition]:
        """Yield grid-aware mappings for every logical table position."""

        mapping = self._build_cell_grid()
        row_count = self.row_count
        col_count = self.column_count
        for row_index in range(row_count):
            for col_index in range(col_count):
                entry = mapping.get((row_index, col_index))
                if entry is None:
                    raise IndexError(
                        "cell coordinates (%d, %d) do not resolve to a physical cell"
                        % (row_index, col_index)
                    )
                yield entry

    def get_cell_map(self) -> list[list[HwpxTableGridPosition]]:
        """Return a 2D list mapping logical positions to physical cells."""

        row_count = self.row_count
        col_count = self.column_count
        grid: list[list[HwpxTableGridPosition | None]] = [
            [None for _ in range(col_count)] for _ in range(row_count)
        ]
        for entry in self.iter_grid():
            grid[entry.row][entry.column] = entry

        for row_index in range(row_count):
            for col_index in range(col_count):
                if grid[row_index][col_index] is None:
                    raise IndexError(
                        "cell coordinates (%d, %d) do not resolve to a physical cell"
                        % (row_index, col_index)
                    )

        return [
            [grid[row_index][col_index] for col_index in range(col_count)]
            for row_index in range(row_count)
        ]

    def cell(self, row_index: int, col_index: int) -> HwpxOxmlTableCell:
        entry = self._grid_entry(row_index, col_index)
        return entry.cell

    def set_cell_text(
        self,
        row_index: int,
        col_index: int,
        text: str,
        *,
        logical: bool = False,
        split_merged: bool = False,
    ) -> None:
        if logical:
            entry = self._grid_entry(row_index, col_index)
            if split_merged and not entry.is_anchor:
                cell = self.split_merged_cell(row_index, col_index)
            else:
                cell = entry.cell
        else:
            cell = self.cell(row_index, col_index)
        cell.text = text

    def split_merged_cell(
        self, row_index: int, col_index: int
    ) -> HwpxOxmlTableCell:
        entry = self._grid_entry(row_index, col_index)
        cell = entry.cell
        start_row, start_col = entry.anchor
        span_row, span_col = entry.span

        if span_row == 1 and span_col == 1:
            return cell

        row_elements = self.element.findall(f"{_HP}tr")
        if len(row_elements) < start_row + span_row:
            raise IndexError(
                "table rows missing while splitting merged cell covering"
                f" ({start_row}, {start_col})"
            )

        width_segments = _distribute_size(cell.width, span_col)
        height_segments = _distribute_size(cell.height, span_row)
        if not width_segments:
            width_segments = [cell.width] + [0] * (span_col - 1)
        if not height_segments:
            height_segments = [cell.height] + [0] * (span_row - 1)

        template_attrs = {key: value for key, value in cell.element.attrib.items()}
        preserved_children = [
            deepcopy(child)
            for child in cell.element
            if _element_local_name(child)
            not in {"subList", "cellAddr", "cellSpan", "cellSz", "cellMargin"}
        ]
        template_sublist = cell.element.find(f"{_HP}subList")
        template_margin = cell.element.find(f"{_HP}cellMargin")

        for row_offset in range(span_row):
            logical_row = start_row + row_offset
            row_element = row_elements[logical_row]
            row_height = height_segments[row_offset] if row_offset < len(height_segments) else cell.height
            for col_offset in range(span_col):
                logical_col = start_col + col_offset
                col_width = width_segments[col_offset] if col_offset < len(width_segments) else cell.width

                if row_offset == 0 and col_offset == 0:
                    addr = cell._addr_element()
                    if addr is None:
                        addr = ET.SubElement(cell.element, f"{_HP}cellAddr")
                    addr.set("rowAddr", str(start_row))
                    addr.set("colAddr", str(start_col))
                    span_element = cell._span_element()
                    span_element.set("rowSpan", "1")
                    span_element.set("colSpan", "1")
                    size_element = cell._size_element()
                    size_element.set("width", str(col_width))
                    size_element.set("height", str(row_height))
                    continue

                existing_target: HwpxOxmlTableCell | None = None
                for existing in row_element.findall(f"{_HP}tc"):
                    wrapper = HwpxOxmlTableCell(existing, self, row_element)
                    existing_row, existing_col = wrapper.address
                    span_r, span_c = wrapper.span
                    if existing_row == logical_row and existing_col == logical_col:
                        existing_target = wrapper
                        break
                    if (
                        existing_row <= logical_row < existing_row + span_r
                        and existing_col <= logical_col < existing_col + span_c
                    ):
                        if wrapper.element is cell.element:
                            continue
                        raise ValueError(
                            "Cannot split merged cell covering (%d, %d) because"
                            " position (%d, %d) overlaps another merged cell"
                            % (start_row, start_col, logical_row, logical_col)
                        )

                if existing_target is not None:
                    existing_target.set_span(1, 1)
                    existing_target.set_size(col_width, row_height)
                    continue

                new_cell_element = ET.Element(f"{_HP}tc", dict(template_attrs))
                for child in preserved_children:
                    new_cell_element.append(deepcopy(child))

                sublist_attrs = _default_sublist_attributes()
                template_para = None
                if template_sublist is not None:
                    for key, value in template_sublist.attrib.items():
                        if key == "id":
                            continue
                        sublist_attrs.setdefault(key, value)
                    template_para = template_sublist.find(f"{_HP}p")

                sublist = ET.SubElement(new_cell_element, f"{_HP}subList", sublist_attrs)
                paragraph_attrs = _default_cell_paragraph_attributes()
                run_attrs = {"charPrIDRef": "0"}
                if template_para is not None:
                    for key, value in template_para.attrib.items():
                        if key == "id":
                            continue
                        paragraph_attrs.setdefault(key, value)
                    template_run = template_para.find(f"{_HP}run")
                    if template_run is not None:
                        run_attrs = dict(template_run.attrib)
                        if "charPrIDRef" not in run_attrs:
                            run_attrs["charPrIDRef"] = "0"
                paragraph = ET.SubElement(sublist, f"{_HP}p", paragraph_attrs)
                run = ET.SubElement(paragraph, f"{_HP}run", run_attrs)
                ET.SubElement(run, f"{_HP}t")

                ET.SubElement(
                    new_cell_element,
                    f"{_HP}cellAddr",
                    {"rowAddr": str(logical_row), "colAddr": str(logical_col)},
                )
                ET.SubElement(
                    new_cell_element,
                    f"{_HP}cellSpan",
                    {"rowSpan": "1", "colSpan": "1"},
                )
                ET.SubElement(
                    new_cell_element,
                    f"{_HP}cellSz",
                    {"width": str(col_width), "height": str(row_height)},
                )
                if template_margin is not None:
                    new_cell_element.append(deepcopy(template_margin))
                else:
                    ET.SubElement(
                        new_cell_element,
                        f"{_HP}cellMargin",
                        _default_cell_margin_attributes(),
                    )

                existing_cells = list(row_element.findall(f"{_HP}tc"))
                insert_index = len(existing_cells)
                for idx, existing in enumerate(existing_cells):
                    wrapper = HwpxOxmlTableCell(existing, self, row_element)
                    if wrapper.address[1] > logical_col:
                        insert_index = idx
                        break
                row_element.insert(insert_index, new_cell_element)

        self.mark_dirty()
        return self.cell(row_index, col_index)

    def merge_cells(
        self,
        start_row: int,
        start_col: int,
        end_row: int,
        end_col: int,
    ) -> HwpxOxmlTableCell:
        if start_row > end_row or start_col > end_col:
            raise ValueError("merge coordinates must describe a valid rectangle")
        if start_row < 0 or start_col < 0:
            raise IndexError("merge coordinates must be non-negative")
        if end_row >= self.row_count or end_col >= self.column_count:
            raise IndexError("merge coordinates exceed table bounds")

        target = self.cell(start_row, start_col)
        addr_row, addr_col = target.address
        if addr_row != start_row or addr_col != start_col:
            raise ValueError("top-left cell must align with merge starting position")

        new_row_span = end_row - start_row + 1
        new_col_span = end_col - start_col + 1

        element_to_row: dict[ET.Element, ET.Element] = {}
        for row in self.element.findall(f"{_HP}tr"):
            for cell in row.findall(f"{_HP}tc"):
                element_to_row[cell] = row

        removal_elements: set[ET.Element] = set()
        width_elements: set[ET.Element] = set()
        height_elements: set[ET.Element] = set()
        total_width = 0
        total_height = 0

        for row_index in range(start_row, end_row + 1):
            for col_index in range(start_col, end_col + 1):
                cell = self.cell(row_index, col_index)
                cell_row, cell_col = cell.address
                span_row, span_col = cell.span
                if (
                    cell_row < start_row
                    or cell_col < start_col
                    or cell_row + span_row - 1 > end_row
                    or cell_col + span_col - 1 > end_col
                ):
                    raise ValueError("Cells to merge must be entirely inside the merge region")
                if row_index == start_row and cell.element not in width_elements:
                    width_elements.add(cell.element)
                    total_width += cell.width
                if col_index == start_col and cell.element not in height_elements:
                    height_elements.add(cell.element)
                    total_height += cell.height
                if cell.element is not target.element:
                    removal_elements.add(cell.element)

        if not removal_elements and target.span == (new_row_span, new_col_span):
            return target

        for element in removal_elements:
            row_element = element_to_row.get(element)
            if row_element is not None:
                try:
                    row_element.remove(element)
                except ValueError:
                    continue

        target.set_span(new_row_span, new_col_span)
        target.set_size(total_width or target.width, total_height or target.height)
        self.mark_dirty()
        return target

@dataclass
class HwpxOxmlParagraph:
    """Lightweight wrapper around an ``<hp:p>`` element."""

    element: ET.Element
    section: HwpxOxmlSection

    def __repr__(self) -> str:
        """Return a compact and safe summary of paragraph contents."""

        runs = self._run_elements()
        return (
            f"{self.__class__.__name__}("
            f"runs={len(runs)}, "
            f"tables={len(self.tables)}, "
            f"text_length={len(self.text)}"
            ")"
        )

    def to_model(self) -> "body.Paragraph":
        xml_bytes = ET.tostring(self.element, encoding="utf-8")
        node = LET.fromstring(xml_bytes)
        return body.parse_paragraph_element(node)

    @property
    def model(self) -> "body.Paragraph":
        return self.to_model()

    def apply_model(self, model: "body.Paragraph") -> None:
        new_node = body.serialize_paragraph(model)
        xml_bytes = LET.tostring(new_node)
        replacement = ET.fromstring(xml_bytes)
        parent = self.section.element
        paragraph_children = list(parent)
        index = paragraph_children.index(self.element)
        parent.remove(self.element)
        parent.insert(index, replacement)
        self.element = replacement
        self.section.mark_dirty()

    def _run_elements(self) -> list[ET.Element]:
        return self.element.findall(f"{_HP}run")

    def _ensure_run(self) -> ET.Element:
        runs = self._run_elements()
        if runs:
            return runs[0]

        run_attrs: dict[str, str] = {}
        default_char = self.char_pr_id_ref or "0"
        if default_char is not None:
            run_attrs["charPrIDRef"] = default_char
        return ET.SubElement(self.element, f"{_HP}run", run_attrs)

    @property
    def runs(self) -> list[HwpxOxmlRun]:
        """Return the runs contained in this paragraph."""
        return [HwpxOxmlRun(run, self) for run in self._run_elements()]

    @property
    def text(self) -> str:
        """Return the concatenated textual content of this paragraph."""
        texts: list[str] = []
        for text_element in self.element.findall(f".//{_HP}t"):
            if text_element.text:
                texts.append(text_element.text)
        return "".join(texts)

    @text.setter
    def text(self, value: str) -> None:
        """Replace the textual contents of this paragraph."""
        # Remove existing text nodes but preserve other children (e.g. controls).
        for run in self._run_elements():
            for child in list(run):
                if child.tag == f"{_HP}t":
                    run.remove(child)
        run = self._ensure_run()
        text_element = ET.SubElement(run, f"{_HP}t")
        text_element.text = value
        self.section.mark_dirty()

    def _create_run_for_object(
        self,
        run_attributes: dict[str, str] | None = None,
        *,
        char_pr_id_ref: str | int | None = None,
    ) -> ET.Element:
        attrs = dict(run_attributes or {})
        if char_pr_id_ref is not None:
            attrs.setdefault("charPrIDRef", str(char_pr_id_ref))
        elif "charPrIDRef" not in attrs:
            default_char = self.char_pr_id_ref or "0"
            if default_char is not None:
                attrs["charPrIDRef"] = str(default_char)
        run = self.element.makeelement(f"{_HP}run", attrs)
        self.element.append(run)
        return run

    def add_run(
        self,
        text: str = "",
        *,
        char_pr_id_ref: str | int | None = None,
        bold: bool = False,
        italic: bool = False,
        underline: bool = False,
        attributes: dict[str, str] | None = None,
    ) -> HwpxOxmlRun:
        """Append a new run to the paragraph and return its wrapper."""

        run_attrs = dict(attributes or {})

        if "charPrIDRef" not in run_attrs:
            if char_pr_id_ref is not None:
                run_attrs["charPrIDRef"] = str(char_pr_id_ref)
            else:
                document = self.section.document
                if document is not None:
                    style_id = document.ensure_run_style(
                        bold=bool(bold),
                        italic=bool(italic),
                        underline=bool(underline),
                    )
                    run_attrs["charPrIDRef"] = style_id
                else:
                    default_char = self.char_pr_id_ref or "0"
                    if default_char is not None:
                        run_attrs["charPrIDRef"] = str(default_char)

        run_element = ET.SubElement(self.element, f"{_HP}run", run_attrs)
        text_element = ET.SubElement(run_element, f"{_HP}t")
        text_element.text = text
        self.section.mark_dirty()
        return HwpxOxmlRun(run_element, self)

    @property
    def tables(self) -> list["HwpxOxmlTable"]:
        """Return the tables embedded within this paragraph."""

        tables: list[HwpxOxmlTable] = []
        for run in self._run_elements():
            for child in run:
                if child.tag == f"{_HP}tbl":
                    tables.append(HwpxOxmlTable(child, self))
        return tables

    def add_table(
        self,
        rows: int,
        cols: int,
        *,
        width: int | None = None,
        height: int | None = None,
        border_fill_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlTable:
        if border_fill_id_ref is None:
            document = self.section.document
            if document is not None:
                resolved_border_fill: str | int = document.ensure_basic_border_fill()
            else:
                resolved_border_fill = "0"
        else:
            resolved_border_fill = border_fill_id_ref

        run = self._create_run_for_object(
            run_attributes,
            char_pr_id_ref=char_pr_id_ref,
        )
        table_element = HwpxOxmlTable.create(
            rows,
            cols,
            width=width,
            height=height,
            border_fill_id_ref=resolved_border_fill,
        )
        if type(table_element) is not type(run):
            table_element = LET.fromstring(ET.tostring(table_element, encoding="utf-8"))

        run.append(table_element)
        self.section.mark_dirty()
        return HwpxOxmlTable(table_element, self)

    def add_shape(
        self,
        shape_type: str,
        attributes: dict[str, str] | None = None,
        *,
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlInlineObject:
        if not shape_type:
            raise ValueError("shape_type must be a non-empty string")
        run = self._create_run_for_object(
            run_attributes,
            char_pr_id_ref=char_pr_id_ref,
        )
        element = ET.SubElement(run, f"{_HP}{shape_type}", dict(attributes or {}))
        self.section.mark_dirty()
        return HwpxOxmlInlineObject(element, self)

    def add_control(
        self,
        attributes: dict[str, str] | None = None,
        *,
        control_type: str | None = None,
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlInlineObject:
        attrs = dict(attributes or {})
        if control_type is not None:
            attrs.setdefault("type", control_type)
        run = self._create_run_for_object(
            run_attributes,
            char_pr_id_ref=char_pr_id_ref,
        )
        element = ET.SubElement(run, f"{_HP}ctrl", attrs)
        self.section.mark_dirty()
        return HwpxOxmlInlineObject(element, self)

    @property
    def para_pr_id_ref(self) -> str | None:
        """Return the paragraph property reference applied to this paragraph."""
        return self.element.get("paraPrIDRef")

    @para_pr_id_ref.setter
    def para_pr_id_ref(self, value: str | int | None) -> None:
        if value is None:
            if "paraPrIDRef" in self.element.attrib:
                del self.element.attrib["paraPrIDRef"]
                self.section.mark_dirty()
            return

        new_value = str(value)
        if self.element.get("paraPrIDRef") != new_value:
            self.element.set("paraPrIDRef", new_value)
            self.section.mark_dirty()

    @property
    def style_id_ref(self) -> str | None:
        """Return the style reference applied to this paragraph."""
        return self.element.get("styleIDRef")

    @style_id_ref.setter
    def style_id_ref(self, value: str | int | None) -> None:
        if value is None:
            if "styleIDRef" in self.element.attrib:
                del self.element.attrib["styleIDRef"]
                self.section.mark_dirty()
            return

        new_value = str(value)
        if self.element.get("styleIDRef") != new_value:
            self.element.set("styleIDRef", new_value)
            self.section.mark_dirty()

    @property
    def char_pr_id_ref(self) -> str | None:
        """Return the shared character property reference across runs.

        If runs use multiple different references the value ``None`` is
        returned, indicating the paragraph does not have a uniform character
        style applied.
        """

        values: set[str] = set()
        for run in self._run_elements():
            value = run.get("charPrIDRef")
            if value is not None:
                values.add(value)

        if not values:
            return None
        if len(values) == 1:
            return next(iter(values))
        return None

    @char_pr_id_ref.setter
    def char_pr_id_ref(self, value: str | int | None) -> None:
        new_value = None if value is None else str(value)
        runs = self._run_elements()
        if not runs:
            runs = [self._ensure_run()]

        changed = False
        for run in runs:
            if new_value is None:
                if "charPrIDRef" in run.attrib:
                    del run.attrib["charPrIDRef"]
                    changed = True
            else:
                if run.get("charPrIDRef") != new_value:
                    run.set("charPrIDRef", new_value)
                    changed = True

        if changed:
            self.section.mark_dirty()


class _HwpxOxmlSimplePart:
    """Common base for standalone XML parts that are not sections or headers."""

    def __init__(
        self,
        part_name: str,
        element: ET.Element,
        document: "HwpxOxmlDocument" | None = None,
    ):
        self.part_name = part_name
        self._element = element
        self._document = document
        self._dirty = False

    @property
    def element(self) -> ET.Element:
        return self._element

    @property
    def document(self) -> "HwpxOxmlDocument" | None:
        return self._document

    def attach_document(self, document: "HwpxOxmlDocument") -> None:
        self._document = document

    @property
    def dirty(self) -> bool:
        return self._dirty

    def mark_dirty(self) -> None:
        self._dirty = True

    def reset_dirty(self) -> None:
        self._dirty = False

    def replace_element(self, element: ET.Element) -> None:
        self._element = element
        self.mark_dirty()

    def to_bytes(self) -> bytes:
        return _serialize_xml(self._element)


class HwpxOxmlMasterPage(_HwpxOxmlSimplePart):
    """Represents a master page part in the package."""


class HwpxOxmlHistory(_HwpxOxmlSimplePart):
    """Represents a document history part."""


class HwpxOxmlVersion(_HwpxOxmlSimplePart):
    """Represents the ``version.xml`` part."""


class HwpxOxmlSection:
    """Represents the contents of a section XML part."""

    def __init__(
        self,
        part_name: str,
        element: ET.Element,
        document: "HwpxOxmlDocument" | None = None,
    ):
        self.part_name = part_name
        self._element = element
        self._dirty = False
        self._properties_cache: HwpxOxmlSectionProperties | None = None
        self._document = document

    def __repr__(self) -> str:
        """Return a compact and safe summary of section structure."""

        return (
            f"{self.__class__.__name__}("
            f"part_name={self.part_name!r}, "
            f"paragraphs={len(self.paragraphs)}, "
            f"memos={len(self.memos)}"
            ")"
        )

    def _section_properties_element(self) -> ET.Element | None:
        return self._element.find(f".//{_HP}secPr")

    def _ensure_section_properties_element(self) -> ET.Element:
        element = self._section_properties_element()
        if element is not None:
            return element

        paragraph = self._element.find(f"{_HP}p")
        if paragraph is None:
            paragraph_attrs = dict(_DEFAULT_PARAGRAPH_ATTRS)
            paragraph_attrs["id"] = _paragraph_id()
            paragraph = ET.SubElement(self._element, f"{_HP}p", paragraph_attrs)
        run = paragraph.find(f"{_HP}run")
        if run is None:
            run = ET.SubElement(paragraph, f"{_HP}run", {"charPrIDRef": "0"})
        element = ET.SubElement(run, f"{_HP}secPr")
        self._properties_cache = None
        self.mark_dirty()
        return element

    @property
    def properties(self) -> HwpxOxmlSectionProperties:
        """Return a wrapper exposing section-level options."""

        if self._properties_cache is None:
            element = self._section_properties_element()
            if element is None:
                element = self._ensure_section_properties_element()
            self._properties_cache = HwpxOxmlSectionProperties(element, self)
        return self._properties_cache

    def _paragraph_elements(self) -> Iterable[ET.Element]:
        return self._element.findall(f"{_HP}p")

    @property
    def element(self) -> ET.Element:
        """Return the underlying XML element."""
        return self._element

    @property
    def document(self) -> "HwpxOxmlDocument" | None:
        return self._document

    def attach_document(self, document: "HwpxOxmlDocument") -> None:
        self._document = document

    @property
    def paragraphs(self) -> list[HwpxOxmlParagraph]:
        """Return the paragraphs defined in this section."""
        return [HwpxOxmlParagraph(elm, self) for elm in self._paragraph_elements()]

    def _memo_group_element(self, create: bool = False) -> ET.Element | None:
        element = self._element.find(f"{_HP}memogroup")
        if element is None and create:
            element = ET.SubElement(self._element, f"{_HP}memogroup")
            self.mark_dirty()
        return element

    @property
    def memo_group(self) -> HwpxOxmlMemoGroup | None:
        element = self._memo_group_element()
        if element is None:
            return None
        return HwpxOxmlMemoGroup(element, self)

    @property
    def memos(self) -> list[HwpxOxmlMemo]:
        group = self.memo_group
        if group is None:
            return []
        return group.memos

    def add_memo(
        self,
        text: str = "",
        *,
        memo_shape_id_ref: str | int | None = None,
        memo_id: str | None = None,
        char_pr_id_ref: str | int | None = None,
        attributes: Optional[dict[str, str]] = None,
    ) -> HwpxOxmlMemo:
        element = self._memo_group_element(create=True)
        if element is None:  # pragma: no cover - defensive branch
            raise RuntimeError("failed to create memo group element")
        group = HwpxOxmlMemoGroup(element, self)
        return group.add_memo(
            text,
            memo_shape_id_ref=memo_shape_id_ref,
            memo_id=memo_id,
            char_pr_id_ref=char_pr_id_ref,
            attributes=attributes,
        )

    def add_paragraph(
        self,
        text: str = "",
        *,
        para_pr_id_ref: str | int | None = None,
        style_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        include_run: bool = True,
        **extra_attrs: str,
    ) -> HwpxOxmlParagraph:
        """Create a new paragraph element appended to this section.

        The optional ``para_pr_id_ref`` and ``style_id_ref`` parameters
        control the paragraph-level references, while ``char_pr_id_ref`` and
        ``run_attributes`` customise the initial ``<hp:run>`` element when
        ``include_run`` is :data:`True`.
        """
        attrs = {"id": _paragraph_id(), **_DEFAULT_PARAGRAPH_ATTRS}
        attrs.update(extra_attrs)

        if para_pr_id_ref is not None:
            attrs["paraPrIDRef"] = str(para_pr_id_ref)
        if style_id_ref is not None:
            attrs["styleIDRef"] = str(style_id_ref)

        paragraph = self._element.makeelement(f"{_HP}p", attrs)

        if include_run:
            run_attrs = dict(run_attributes or {})
            if char_pr_id_ref is not None:
                run_attrs["charPrIDRef"] = str(char_pr_id_ref)
            elif "charPrIDRef" not in run_attrs:
                run_attrs["charPrIDRef"] = "0"

            run = paragraph.makeelement(f"{_HP}run", run_attrs)
            paragraph.append(run)
            text_element = run.makeelement(f"{_HP}t", {})
            text_element.text = text
            run.append(text_element)

        self._element.append(paragraph)
        self._dirty = True
        return HwpxOxmlParagraph(paragraph, self)

    def mark_dirty(self) -> None:
        self._dirty = True

    @property
    def dirty(self) -> bool:
        return self._dirty

    def reset_dirty(self) -> None:
        self._dirty = False

    def to_bytes(self) -> bytes:
        return _serialize_xml(self._element)


class HwpxOxmlHeader:
    """Represents a header XML part."""

    def __init__(self, part_name: str, element: ET.Element, document: "HwpxOxmlDocument" | None = None):
        self.part_name = part_name
        self._element = element
        self._dirty = False
        self._document = document

    @property
    def element(self) -> ET.Element:
        return self._element

    @property
    def document(self) -> "HwpxOxmlDocument" | None:
        return self._document

    def attach_document(self, document: "HwpxOxmlDocument") -> None:
        self._document = document

    def _begin_num_element(self, create: bool = False) -> ET.Element | None:
        element = self._element.find(f"{_HH}beginNum")
        if element is None and create:
            element = self._element.makeelement(f"{_HH}beginNum", {})
            self._element.append(element)
        return element

    def _ref_list_element(self, create: bool = False) -> ET.Element | None:
        element = self._element.find(f"{_HH}refList")
        if element is None and create:
            element = self._element.makeelement(f"{_HH}refList", {})
            self._element.append(element)
            self.mark_dirty()
        return element

    def _border_fills_element(self, create: bool = False) -> ET.Element | None:
        ref_list = self._ref_list_element(create=create)
        if ref_list is None:
            return None
        element = ref_list.find(f"{_HH}borderFills")
        if element is None and create:
            element = ref_list.makeelement(f"{_HH}borderFills", {"itemCnt": "0"})
            ref_list.append(element)
            self.mark_dirty()
        return element

    def _char_properties_element(self, create: bool = False) -> ET.Element | None:
        ref_list = self._ref_list_element(create=create)
        if ref_list is None:
            return None
        element = ref_list.find(f"{_HH}charProperties")
        if element is None and create:
            element = ref_list.makeelement(f"{_HH}charProperties", {"itemCnt": "0"})
            ref_list.append(element)
            self.mark_dirty()
        return element

    def _update_char_properties_item_count(self, element: ET.Element) -> None:
        count = len(list(element.findall(f"{_HH}charPr")))
        element.set("itemCnt", str(count))

    def _update_border_fills_item_count(self, element: ET.Element) -> None:
        count = len(list(element.findall(f"{_HH}borderFill")))
        element.set("itemCnt", str(count))

    def _allocate_char_property_id(
        self,
        element: ET.Element,
        *,
        preferred_id: str | int | None = None,
    ) -> str:
        existing: set[str] = {
            child.get("id") or ""
            for child in element.findall(f"{_HH}charPr")
        }
        existing.discard("")

        if preferred_id is not None:
            candidate = str(preferred_id)
            if candidate not in existing:
                return candidate

        numeric_ids: list[int] = []
        for value in existing:
            try:
                numeric_ids.append(int(value))
            except ValueError:
                continue
        next_id = 0 if not numeric_ids else max(numeric_ids) + 1
        candidate = str(next_id)
        while candidate in existing:
            next_id += 1
            candidate = str(next_id)
        return candidate

    def _allocate_border_fill_id(self, element: ET.Element) -> str:
        existing: set[str] = {
            child.get("id") or ""
            for child in element.findall(f"{_HH}borderFill")
        }
        existing.discard("")

        numeric_ids: list[int] = []
        for value in existing:
            try:
                numeric_ids.append(int(value))
            except ValueError:
                continue
        next_id = 0 if not numeric_ids else max(numeric_ids) + 1
        candidate = str(next_id)
        while candidate in existing:
            next_id += 1
            candidate = str(next_id)
        return candidate

    def ensure_char_property(
        self,
        *,
        predicate: Callable[[ET.Element], bool] | None = None,
        modifier: Callable[[ET.Element], None] | None = None,
        base_char_pr_id: str | int | None = None,
        preferred_id: str | int | None = None,
    ) -> ET.Element:
        """Return a ``<hh:charPr>`` element matching *predicate* or create one.

        When an existing entry satisfies *predicate*, it is returned unchanged.
        Otherwise a new element is produced by cloning ``base_char_pr_id`` (or the
        first available entry) and applying *modifier* before assigning a fresh
        identifier and updating ``itemCnt``.
        """

        char_props = self._char_properties_element(create=True)
        if char_props is None:  # pragma: no cover - defensive branch
            raise RuntimeError("failed to create <charProperties> element")

        if predicate is not None:
            for child in char_props.findall(f"{_HH}charPr"):
                if predicate(child):
                    return child

        base_element: ET.Element | None = None
        if base_char_pr_id is not None:
            base_element = char_props.find(f"{_HH}charPr[@id='{base_char_pr_id}']")
        if base_element is None:
            existing = char_props.find(f"{_HH}charPr")
            if existing is not None:
                base_element = existing

        if base_element is None:
            new_char_pr = ET.Element(f"{_HH}charPr")
        else:
            new_char_pr = deepcopy(base_element)
            if "id" in new_char_pr.attrib:
                del new_char_pr.attrib["id"]

        if modifier is not None:
            modifier(new_char_pr)

        char_id = self._allocate_char_property_id(char_props, preferred_id=preferred_id)
        new_char_pr.set("id", char_id)
        char_props.append(new_char_pr)
        self._update_char_properties_item_count(char_props)
        self.mark_dirty()
        document = self.document
        if document is not None:
            document.invalidate_char_property_cache()
        return new_char_pr

    def _memo_properties_element(self) -> ET.Element | None:
        ref_list = self._element.find(f"{_HH}refList")
        if ref_list is None:
            return None
        return ref_list.find(f"{_HH}memoProperties")

    def _bullets_element(self) -> ET.Element | None:
        ref_list = self._ref_list_element()
        if ref_list is None:
            return None
        return ref_list.find(f"{_HH}bullets")

    def _para_properties_element(self) -> ET.Element | None:
        ref_list = self._ref_list_element()
        if ref_list is None:
            return None
        return ref_list.find(f"{_HH}paraProperties")

    def _styles_element(self) -> ET.Element | None:
        ref_list = self._ref_list_element()
        if ref_list is None:
            return None
        return ref_list.find(f"{_HH}styles")

    def _track_changes_element(self) -> ET.Element | None:
        ref_list = self._ref_list_element()
        if ref_list is None:
            return None
        return ref_list.find(f"{_HH}trackChanges")

    def _track_change_authors_element(self) -> ET.Element | None:
        ref_list = self._ref_list_element()
        if ref_list is None:
            return None
        return ref_list.find(f"{_HH}trackChangeAuthors")

    def find_basic_border_fill_id(self) -> str | None:
        element = self._border_fills_element()
        if element is None:
            return None
        for child in element.findall(f"{_HH}borderFill"):
            if _border_fill_is_basic_solid_line(child):
                identifier = child.get("id")
                if identifier:
                    return identifier
        return None

    def ensure_basic_border_fill(self) -> str:
        element = self._border_fills_element(create=True)
        if element is None:  # pragma: no cover - defensive branch
            raise RuntimeError("failed to create <borderFills> element")

        existing = self.find_basic_border_fill_id()
        if existing is not None:
            return existing

        new_id = self._allocate_border_fill_id(element)
        new_border_fill = _create_basic_border_fill_element(new_id)
        if isinstance(element, LET._Element):
            new_border_fill = LET.fromstring(ET.tostring(new_border_fill, encoding="utf-8"))
        element.append(new_border_fill)
        self._update_border_fills_item_count(element)
        self.mark_dirty()
        return new_id

    @property
    def border_fills(self) -> dict[str, GenericElement]:
        element = self._border_fills_element()
        if element is None:
            return {}

        fill_list = parse_border_fills(self._convert_to_lxml(element))
        mapping: dict[str, GenericElement] = {}
        for border_fill in fill_list.fills:
            raw_id = border_fill.attributes.get("id")
            keys: list[str] = []
            if raw_id:
                keys.append(raw_id)
                try:
                    normalized = str(int(raw_id))
                except ValueError:
                    normalized = None
                if normalized and normalized not in keys:
                    keys.append(normalized)
            for key in keys:
                if key not in mapping:
                    mapping[key] = border_fill
        return mapping

    def border_fill(self, border_fill_id_ref: int | str | None) -> GenericElement | None:
        return self._lookup_by_id(self.border_fills, border_fill_id_ref)

    @staticmethod
    def _convert_to_lxml(element: ET.Element) -> LET._Element:
        return LET.fromstring(ET.tostring(element, encoding="utf-8"))

    @staticmethod
    def _lookup_by_id(mapping: dict[str, T], identifier: int | str | None) -> T | None:
        if identifier is None:
            return None

        if isinstance(identifier, str):
            key = identifier.strip()
        else:
            key = str(identifier)

        if not key:
            return None

        value = mapping.get(key)
        if value is not None:
            return value

        try:
            normalized = str(int(key))
        except (TypeError, ValueError):
            return None
        return mapping.get(normalized)

    @property
    def begin_numbering(self) -> DocumentNumbering:
        element = self._begin_num_element()
        if element is None:
            return DocumentNumbering()
        return DocumentNumbering(
            page=_get_int_attr(element, "page", 1),
            footnote=_get_int_attr(element, "footnote", 1),
            endnote=_get_int_attr(element, "endnote", 1),
            picture=_get_int_attr(element, "pic", 1),
            table=_get_int_attr(element, "tbl", 1),
            equation=_get_int_attr(element, "equation", 1),
        )

    def set_begin_numbering(
        self,
        *,
        page: int | None = None,
        footnote: int | None = None,
        endnote: int | None = None,
        picture: int | None = None,
        table: int | None = None,
        equation: int | None = None,
    ) -> None:
        element = self._begin_num_element(create=True)
        if element is None:
            return

        current = self.begin_numbering
        values = {
            "page": page if page is not None else current.page,
            "footnote": footnote if footnote is not None else current.footnote,
            "endnote": endnote if endnote is not None else current.endnote,
            "pic": picture if picture is not None else current.picture,
            "tbl": table if table is not None else current.table,
            "equation": equation if equation is not None else current.equation,
        }

        changed = False
        for attr, value in values.items():
            safe_value = str(max(value, 0))
            if element.get(attr) != safe_value:
                element.set(attr, safe_value)
                changed = True

        if changed:
            self.mark_dirty()

    @property
    def memo_shapes(self) -> dict[str, MemoShape]:
        memo_props_element = self._memo_properties_element()
        if memo_props_element is None:
            return {}

        memo_shapes = [
            memo_shape_from_attributes(child.attrib)
            for child in memo_props_element.findall(f"{_HH}memoPr")
        ]
        memo_properties = MemoProperties(
            item_cnt=parse_int(memo_props_element.get("itemCnt")),
            memo_shapes=memo_shapes,
            attributes={
                key: value
                for key, value in memo_props_element.attrib.items()
                if key != "itemCnt"
            },
        )
        return memo_properties.as_dict()

    def memo_shape(self, memo_shape_id_ref: int | str | None) -> MemoShape | None:
        if memo_shape_id_ref is None:
            return None

        if isinstance(memo_shape_id_ref, str):
            key = memo_shape_id_ref.strip()
        else:
            key = str(memo_shape_id_ref)

        if not key:
            return None

        shapes = self.memo_shapes
        shape = shapes.get(key)
        if shape is not None:
            return shape

        try:
            normalized = str(int(key))
        except (TypeError, ValueError):
            return None
        return shapes.get(normalized)

    @property
    def bullets(self) -> dict[str, Bullet]:
        bullets_element = self._bullets_element()
        if bullets_element is None:
            return {}

        bullet_list = parse_bullets(self._convert_to_lxml(bullets_element))
        return bullet_list.as_dict()

    def bullet(self, bullet_id_ref: int | str | None) -> Bullet | None:
        return self._lookup_by_id(self.bullets, bullet_id_ref)

    @property
    def paragraph_properties(self) -> dict[str, ParagraphProperty]:
        para_props_element = self._para_properties_element()
        if para_props_element is None:
            return {}

        para_properties = parse_paragraph_properties(
            self._convert_to_lxml(para_props_element)
        )
        return para_properties.as_dict()

    def paragraph_property(
        self, para_pr_id_ref: int | str | None
    ) -> ParagraphProperty | None:
        return self._lookup_by_id(self.paragraph_properties, para_pr_id_ref)

    @property
    def styles(self) -> dict[str, Style]:
        styles_element = self._styles_element()
        if styles_element is None:
            return {}

        style_list = parse_styles(self._convert_to_lxml(styles_element))
        return style_list.as_dict()

    def style(self, style_id_ref: int | str | None) -> Style | None:
        return self._lookup_by_id(self.styles, style_id_ref)

    @property
    def track_changes(self) -> dict[str, TrackChange]:
        changes_element = self._track_changes_element()
        if changes_element is None:
            return {}

        change_list = parse_track_changes(self._convert_to_lxml(changes_element))
        return change_list.as_dict()

    def track_change(self, change_id_ref: int | str | None) -> TrackChange | None:
        return self._lookup_by_id(self.track_changes, change_id_ref)

    @property
    def track_change_authors(self) -> dict[str, TrackChangeAuthor]:
        authors_element = self._track_change_authors_element()
        if authors_element is None:
            return {}

        author_list = parse_track_change_authors(
            self._convert_to_lxml(authors_element)
        )
        return author_list.as_dict()

    def track_change_author(
        self, author_id_ref: int | str | None
    ) -> TrackChangeAuthor | None:
        return self._lookup_by_id(self.track_change_authors, author_id_ref)

    @property
    def dirty(self) -> bool:
        return self._dirty

    def mark_dirty(self) -> None:
        self._dirty = True

    def reset_dirty(self) -> None:
        self._dirty = False

    def to_bytes(self) -> bytes:
        return _serialize_xml(self._element)


class HwpxOxmlDocument:
    """Aggregates the XML parts that make up an HWPX document."""

    def __init__(
        self,
        manifest: ET.Element,
        sections: Sequence[HwpxOxmlSection],
        headers: Sequence[HwpxOxmlHeader],
        *,
        master_pages: Sequence[HwpxOxmlMasterPage] | None = None,
        histories: Sequence[HwpxOxmlHistory] | None = None,
        version: HwpxOxmlVersion | None = None,
    ):
        self._manifest = manifest
        self._sections = list(sections)
        self._headers = list(headers)
        self._master_pages = list(master_pages or [])
        self._histories = list(histories or [])
        self._version = version
        self._char_property_cache: dict[str, RunStyle] | None = None

        for section in self._sections:
            section.attach_document(self)
        for header in self._headers:
            header.attach_document(self)
        for master_page in self._master_pages:
            master_page.attach_document(self)
        for history in self._histories:
            history.attach_document(self)
        if self._version is not None:
            self._version.attach_document(self)

    @classmethod
    def from_package(cls, package: "HwpxPackage") -> "HwpxOxmlDocument":
        from hwpx.opc.package import HwpxPackage  # Local import to avoid cycle during typing

        if not isinstance(package, HwpxPackage):
            raise TypeError("package must be an instance of HwpxPackage")

        manifest = package.get_xml(package.MANIFEST_PATH)
        section_paths = package.section_paths()
        header_paths = package.header_paths()
        master_page_paths = package.master_page_paths()
        history_paths = package.history_paths()
        version_path = package.version_path()

        sections: list[HwpxOxmlSection] = []
        for section_index, path in enumerate(section_paths):
            try:
                sections.append(HwpxOxmlSection(path, package.get_xml(path)))
            except Exception:
                logger.exception(
                    "section 파싱 실패: section_index=%d, part_path=%s",
                    section_index,
                    path,
                )
                raise

        headers: list[HwpxOxmlHeader] = []
        for path in header_paths:
            try:
                headers.append(HwpxOxmlHeader(path, package.get_xml(path)))
            except Exception:
                logger.exception("header 파싱 실패: part_path=%s", path)
                raise

        master_pages: list[HwpxOxmlMasterPage] = []
        for path in master_page_paths:
            if not package.has_part(path):
                logger.warning("masterPage 파트 누락: part_path=%s", path)
                continue
            try:
                master_pages.append(HwpxOxmlMasterPage(path, package.get_xml(path)))
            except Exception:
                logger.exception("masterPage 파싱 실패: part_path=%s", path)
                raise

        histories: list[HwpxOxmlHistory] = []
        for path in history_paths:
            if not package.has_part(path):
                logger.warning("history 파트 누락: part_path=%s", path)
                continue
            try:
                histories.append(HwpxOxmlHistory(path, package.get_xml(path)))
            except Exception:
                logger.exception("history 파싱 실패: part_path=%s", path)
                raise

        version = None
        if version_path and package.has_part(version_path):
            try:
                version = HwpxOxmlVersion(version_path, package.get_xml(version_path))
            except Exception:
                logger.exception("version 파싱 실패: part_path=%s", version_path)
                raise
        elif version_path:
            logger.warning("manifest가 가리키는 version 파트가 누락되었습니다: part_path=%s", version_path)
        return cls(
            manifest,
            sections,
            headers,
            master_pages=master_pages,
            histories=histories,
            version=version,
        )

    @property
    def manifest(self) -> ET.Element:
        return self._manifest

    @property
    def sections(self) -> list[HwpxOxmlSection]:
        return list(self._sections)

    @property
    def headers(self) -> list[HwpxOxmlHeader]:
        return list(self._headers)

    @property
    def master_pages(self) -> list[HwpxOxmlMasterPage]:
        return list(self._master_pages)

    @property
    def histories(self) -> list[HwpxOxmlHistory]:
        return list(self._histories)

    @property
    def version(self) -> HwpxOxmlVersion | None:
        return self._version

    def _ensure_char_property_cache(self) -> dict[str, RunStyle]:
        if self._char_property_cache is None:
            mapping: dict[str, RunStyle] = {}
            for header in self._headers:
                mapping.update(_char_properties_from_header(header.element))
            self._char_property_cache = mapping
        return self._char_property_cache

    def invalidate_char_property_cache(self) -> None:
        self._char_property_cache = None

    @property
    def char_properties(self) -> dict[str, RunStyle]:
        return dict(self._ensure_char_property_cache())

    def char_property(self, char_pr_id_ref: int | str | None) -> RunStyle | None:
        if char_pr_id_ref is None:
            return None
        key = str(char_pr_id_ref).strip()
        if not key:
            return None
        cache = self._ensure_char_property_cache()
        style = cache.get(key)
        if style is not None:
            return style
        try:
            normalized = str(int(key))
        except (TypeError, ValueError):
            return None
        return cache.get(normalized)

    def ensure_run_style(
        self,
        *,
        bold: bool = False,
        italic: bool = False,
        underline: bool = False,
        base_char_pr_id: str | int | None = None,
    ) -> str:
        """Return a char property identifier matching the requested flags."""

        if not self._headers:
            raise ValueError("document does not contain any headers")

        target = (bool(bold), bool(italic), bool(underline))
        header = self._headers[0]

        def element_flags(element: ET.Element) -> tuple[bool, bool, bool]:
            bold_present = element.find(f"{_HH}bold") is not None
            italic_present = element.find(f"{_HH}italic") is not None
            underline_element = element.find(f"{_HH}underline")
            underline_present = False
            if underline_element is not None:
                underline_present = underline_element.get("type", "").upper() != "NONE"
            return bold_present, italic_present, underline_present

        def predicate(element: ET.Element) -> bool:
            return element_flags(element) == target

        def modifier(element: ET.Element) -> None:
            underline_nodes = list(element.findall(f"{_HH}underline"))
            base_underline_attrs = dict(underline_nodes[0].attrib) if underline_nodes else {}

            for child in list(element.findall(f"{_HH}bold")):
                element.remove(child)
            for child in list(element.findall(f"{_HH}italic")):
                element.remove(child)
            for child in underline_nodes:
                element.remove(child)

            if target[0]:
                ET.SubElement(element, f"{_HH}bold")
            if target[1]:
                ET.SubElement(element, f"{_HH}italic")

            underline_attrs = dict(base_underline_attrs)
            if target[2]:
                underline_attrs.setdefault("type", "SOLID")
                if underline_attrs.get("type", "").upper() == "NONE":
                    underline_attrs["type"] = "SOLID"
                underline_attrs.setdefault("shape", base_underline_attrs.get("shape", "SOLID"))
                if "color" not in underline_attrs and "color" in base_underline_attrs:
                    underline_attrs["color"] = base_underline_attrs["color"]
                if "color" not in underline_attrs:
                    underline_attrs["color"] = "#000000"
                ET.SubElement(element, f"{_HH}underline", underline_attrs)
            else:
                attrs = dict(base_underline_attrs)
                attrs["type"] = "NONE"
                attrs.setdefault("shape", base_underline_attrs.get("shape", "SOLID"))
                if "color" in base_underline_attrs:
                    attrs["color"] = base_underline_attrs["color"]
                ET.SubElement(element, f"{_HH}underline", attrs)

        element = header.ensure_char_property(
            predicate=predicate,
            modifier=modifier,
            base_char_pr_id=base_char_pr_id,
        )

        char_id = element.get("id")
        if char_id is None:  # pragma: no cover - defensive branch
            raise RuntimeError("charPr element is missing an id")
        return char_id

    @property
    def border_fills(self) -> dict[str, GenericElement]:
        mapping: dict[str, GenericElement] = {}
        for header in self._headers:
            mapping.update(header.border_fills)
        return mapping

    def border_fill(self, border_fill_id_ref: int | str | None) -> GenericElement | None:
        return HwpxOxmlHeader._lookup_by_id(self.border_fills, border_fill_id_ref)

    def ensure_basic_border_fill(self) -> str:
        if not self._headers:
            return "0"

        for header in self._headers:
            existing = header.find_basic_border_fill_id()
            if existing is not None:
                return existing

        return self._headers[0].ensure_basic_border_fill()

    @property
    def memo_shapes(self) -> dict[str, MemoShape]:
        shapes: dict[str, MemoShape] = {}
        for header in self._headers:
            shapes.update(header.memo_shapes)
        return shapes

    def memo_shape(self, memo_shape_id_ref: int | str | None) -> MemoShape | None:
        if memo_shape_id_ref is None:
            return None
        key = str(memo_shape_id_ref).strip()
        if not key:
            return None
        shapes = self.memo_shapes
        shape = shapes.get(key)
        if shape is not None:
            return shape
        try:
            normalized = str(int(key))
        except (TypeError, ValueError):
            return None
        return shapes.get(normalized)

    @property
    def bullets(self) -> dict[str, Bullet]:
        mapping: dict[str, Bullet] = {}
        for header in self._headers:
            mapping.update(header.bullets)
        return mapping

    def bullet(self, bullet_id_ref: int | str | None) -> Bullet | None:
        return HwpxOxmlHeader._lookup_by_id(self.bullets, bullet_id_ref)

    @property
    def paragraph_properties(self) -> dict[str, ParagraphProperty]:
        mapping: dict[str, ParagraphProperty] = {}
        for header in self._headers:
            mapping.update(header.paragraph_properties)
        return mapping

    def paragraph_property(
        self, para_pr_id_ref: int | str | None
    ) -> ParagraphProperty | None:
        return HwpxOxmlHeader._lookup_by_id(self.paragraph_properties, para_pr_id_ref)

    @property
    def styles(self) -> dict[str, Style]:
        mapping: dict[str, Style] = {}
        for header in self._headers:
            mapping.update(header.styles)
        return mapping

    def style(self, style_id_ref: int | str | None) -> Style | None:
        return HwpxOxmlHeader._lookup_by_id(self.styles, style_id_ref)

    @property
    def track_changes(self) -> dict[str, TrackChange]:
        mapping: dict[str, TrackChange] = {}
        for header in self._headers:
            mapping.update(header.track_changes)
        return mapping

    def track_change(self, change_id_ref: int | str | None) -> TrackChange | None:
        return HwpxOxmlHeader._lookup_by_id(self.track_changes, change_id_ref)

    @property
    def track_change_authors(self) -> dict[str, TrackChangeAuthor]:
        mapping: dict[str, TrackChangeAuthor] = {}
        for header in self._headers:
            mapping.update(header.track_change_authors)
        return mapping

    def track_change_author(
        self, author_id_ref: int | str | None
    ) -> TrackChangeAuthor | None:
        return HwpxOxmlHeader._lookup_by_id(self.track_change_authors, author_id_ref)

    @property
    def paragraphs(self) -> list[HwpxOxmlParagraph]:
        paragraphs: list[HwpxOxmlParagraph] = []
        for section in self._sections:
            paragraphs.extend(section.paragraphs)
        return paragraphs

    def add_paragraph(
        self,
        text: str = "",
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        para_pr_id_ref: str | int | None = None,
        style_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        include_run: bool = True,
        **extra_attrs: str,
    ) -> HwpxOxmlParagraph:
        """Append a new paragraph to the requested section."""
        if section is None and section_index is not None:
            section = self._sections[section_index]
        if section is None:
            if not self._sections:
                raise ValueError("document does not contain any sections")
            section = self._sections[-1]
        return section.add_paragraph(
            text,
            para_pr_id_ref=para_pr_id_ref,
            style_id_ref=style_id_ref,
            char_pr_id_ref=char_pr_id_ref,
            run_attributes=run_attributes,
            include_run=include_run,
            **extra_attrs,
        )

    def serialize(self) -> dict[str, bytes]:
        """Return a mapping of part names to updated XML payloads."""
        updates: dict[str, bytes] = {}
        for section in self._sections:
            if section.dirty:
                updates[section.part_name] = section.to_bytes()
        headers_dirty = False
        for header in self._headers:
            if header.dirty:
                updates[header.part_name] = header.to_bytes()
                headers_dirty = True
        if headers_dirty:
            self.invalidate_char_property_cache()
        for master_page in self._master_pages:
            if master_page.dirty:
                updates[master_page.part_name] = master_page.to_bytes()
        for history in self._histories:
            if history.dirty:
                updates[history.part_name] = history.to_bytes()
        if self._version is not None and self._version.dirty:
            updates[self._version.part_name] = self._version.to_bytes()
        return updates

    def reset_dirty(self) -> None:
        """Mark all parts as clean after a successful save."""
        for section in self._sections:
            section.reset_dirty()
        for header in self._headers:
            header.reset_dirty()
        for master_page in self._master_pages:
            master_page.reset_dirty()
        for history in self._histories:
            history.reset_dirty()
        if self._version is not None:
            self._version.reset_dirty()
