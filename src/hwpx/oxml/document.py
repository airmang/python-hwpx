"""Object model mapping for the XML parts of an HWPX document."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple
from uuid import uuid4
import xml.etree.ElementTree as ET

from .header import MemoProperties, MemoShape, memo_shape_from_attributes
from .utils import parse_int

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


def _element_local_name(node: ET.Element) -> str:
    tag = node.tag
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _distribute_size(total: int, parts: int) -> List[int]:
    """Return *parts* integers that sum to *total* and are as even as possible."""

    if parts <= 0:
        return []

    base = total // parts
    remainder = total - (base * parts)
    sizes: List[int] = []
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
    attributes: Dict[str, str]
    child_attributes: Dict[str, Dict[str, str]]

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


def _char_properties_from_header(element: ET.Element) -> Dict[str, RunStyle]:
    mapping: Dict[str, RunStyle] = {}
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
        child_attributes: Dict[str, Dict[str, str]] = {}
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
    ):
        self.element = element
        self._properties = properties

    @property
    def id(self) -> str | None:
        """Return the identifier assigned to the header/footer element."""

        return self.element.get("id")

    @id.setter
    def id(self, value: str | None) -> None:
        if value is None:
            if "id" in self.element.attrib:
                del self.element.attrib["id"]
                self._properties.section.mark_dirty()
            return

        new_value = str(value)
        if self.element.get("id") != new_value:
            self.element.set("id", new_value)
            self._properties.section.mark_dirty()

    @property
    def apply_page_type(self) -> str:
        """Return the page type the header/footer applies to."""

        return self.element.get("applyPageType", "BOTH")

    @apply_page_type.setter
    def apply_page_type(self, value: str) -> None:
        if self.element.get("applyPageType") != value:
            self.element.set("applyPageType", value)
            self._properties.section.mark_dirty()

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

        parts: List[str] = []
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
    def _find_header_footer(self, tag: str, page_type: str) -> ET.Element | None:
        for element in self.element.findall(f"{_HP}{tag}"):
            if element.get("applyPageType", "BOTH") == page_type:
                return element
        return None

    def _ensure_header_footer(self, tag: str, page_type: str) -> ET.Element:
        element = self._find_header_footer(tag, page_type)
        if element is None:
            element = ET.SubElement(
                self.element,
                f"{_HP}{tag}",
                {"id": _object_id(), "applyPageType": page_type},
            )
            self.section.mark_dirty()
        return element

    @property
    def headers(self) -> List[HwpxOxmlSectionHeaderFooter]:
        return [HwpxOxmlSectionHeaderFooter(el, self) for el in self.element.findall(f"{_HP}header")]

    @property
    def footers(self) -> List[HwpxOxmlSectionHeaderFooter]:
        return [HwpxOxmlSectionHeaderFooter(el, self) for el in self.element.findall(f"{_HP}footer")]

    def get_header(self, page_type: str = "BOTH") -> Optional[HwpxOxmlSectionHeaderFooter]:
        element = self._find_header_footer("header", page_type)
        if element is None:
            return None
        return HwpxOxmlSectionHeaderFooter(element, self)

    def get_footer(self, page_type: str = "BOTH") -> Optional[HwpxOxmlSectionHeaderFooter]:
        element = self._find_header_footer("footer", page_type)
        if element is None:
            return None
        return HwpxOxmlSectionHeaderFooter(element, self)

    def set_header_text(self, text: str, page_type: str = "BOTH") -> HwpxOxmlSectionHeaderFooter:
        element = self._ensure_header_footer("header", page_type)
        wrapper = HwpxOxmlSectionHeaderFooter(element, self)
        wrapper.text = text
        return wrapper

    def set_footer_text(self, text: str, page_type: str = "BOTH") -> HwpxOxmlSectionHeaderFooter:
        element = self._ensure_header_footer("footer", page_type)
        wrapper = HwpxOxmlSectionHeaderFooter(element, self)
        wrapper.text = text
        return wrapper

    def remove_header(self, page_type: str = "BOTH") -> None:
        element = self._find_header_footer("header", page_type)
        if element is not None:
            self.element.remove(element)
            self.section.mark_dirty()

    def remove_footer(self, page_type: str = "BOTH") -> None:
        element = self._find_header_footer("footer", page_type)
        if element is not None:
            self.element.remove(element)
            self.section.mark_dirty()


class HwpxOxmlRun:
    """Lightweight wrapper around an ``<hp:run>`` element."""

    def __init__(self, element: ET.Element, paragraph: "HwpxOxmlParagraph"):
        self.element = element
        self.paragraph = paragraph

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

    def _plain_text_nodes(self) -> List[ET.Element]:
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
        parts: List[str] = []
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
        """Replace ``search`` with ``replacement`` in-place.

        Returns the number of replacements that were performed.
        """

        if not search:
            raise ValueError("search text must be a non-empty string")

        total = 0
        remaining = count
        for node in self._plain_text_nodes():
            current = node.text or ""
            if not current:
                continue
            max_replace: int | None
            if remaining is None:
                max_replace = None
            else:
                if remaining <= 0:
                    break
                max_replace = remaining
            if max_replace is None:
                new_text = current.replace(search, replacement)
                replaced_here = current.count(search)
            else:
                new_text = current.replace(search, replacement, max_replace)
                replaced_here = min(max_replace, current.count(search))
                remaining -= replaced_here
            if replaced_here:
                node.text = new_text
                total += replaced_here
                if remaining is not None and remaining <= 0:
                    break
        if total:
            self.paragraph.section.mark_dirty()
        return total

    def remove(self) -> None:
        parent = self.paragraph.element
        try:
            parent.remove(self.element)
        except ValueError:  # pragma: no cover - defensive branch
            return
        self.paragraph.section.mark_dirty()


class HwpxOxmlMemoGroup:
    """Wrapper providing access to ``<hp:memogroup>`` containers."""

    def __init__(self, element: ET.Element, section: "HwpxOxmlSection"):
        self.element = element
        self.section = section

    @property
    def memos(self) -> List["HwpxOxmlMemo"]:
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
    def paragraphs(self) -> List["HwpxOxmlParagraph"]:
        paragraphs: List[HwpxOxmlParagraph] = []
        for node in self.element.findall(f".//{_HP}p"):
            paragraphs.append(HwpxOxmlParagraph(node, self.group.section))
        return paragraphs

    @property
    def text(self) -> str:
        parts: List[str] = []
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
        run = paragraph.find(f"{_HP}run")
        if run is None:
            run = ET.SubElement(paragraph, f"{_HP}run", {"charPrIDRef": "0"})
        text = run.find(f"{_HP}t")
        if text is None:
            text = ET.SubElement(run, f"{_HP}t")
        return text

    @property
    def address(self) -> Tuple[int, int]:
        addr = self._addr_element()
        if addr is None:
            return (0, 0)
        row = int(addr.get("rowAddr", "0"))
        col = int(addr.get("colAddr", "0"))
        return (row, col)

    @property
    def span(self) -> Tuple[int, int]:
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
        self.table.mark_dirty()

    def remove(self) -> None:
        self._row_element.remove(self.element)
        self.table.mark_dirty()


class HwpxOxmlTableRow:
    """Represents a table row."""

    def __init__(self, element: ET.Element, table: "HwpxOxmlTable"):
        self.element = element
        self.table = table

    @property
    def cells(self) -> List[HwpxOxmlTableCell]:
        return [
            HwpxOxmlTableCell(cell_element, self.table, self.element)
            for cell_element in self.element.findall(f"{_HP}tc")
        ]


class HwpxOxmlTable:
    """Representation of an ``<hp:tbl>`` inline object."""

    def __init__(self, element: ET.Element, paragraph: "HwpxOxmlParagraph"):
        self.element = element
        self.paragraph = paragraph

    @classmethod
    def create(
        cls,
        rows: int,
        cols: int,
        *,
        width: int | None = None,
        height: int | None = None,
        border_fill_id_ref: str | int = "0",
    ) -> ET.Element:
        if rows <= 0 or cols <= 0:
            raise ValueError("rows and cols must be positive integers")

        table_width = width if width is not None else cols * _DEFAULT_CELL_WIDTH
        table_height = height if height is not None else rows * _DEFAULT_CELL_HEIGHT
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
    def rows(self) -> List[HwpxOxmlTableRow]:
        return [HwpxOxmlTableRow(row, self) for row in self.element.findall(f"{_HP}tr")]

    def cell(self, row_index: int, col_index: int) -> HwpxOxmlTableCell:
        if row_index < 0 or col_index < 0:
            raise IndexError("row_index and col_index must be non-negative")

        for row in self.element.findall(f"{_HP}tr"):
            for cell in row.findall(f"{_HP}tc"):
                wrapper = HwpxOxmlTableCell(cell, self, row)
                start_row, start_col = wrapper.address
                span_row, span_col = wrapper.span
                if (
                    start_row <= row_index < start_row + span_row
                    and start_col <= col_index < start_col + span_col
                ):
                    return wrapper
        raise IndexError("cell coordinates out of range")

    def set_cell_text(self, row_index: int, col_index: int, text: str) -> None:
        cell = self.cell(row_index, col_index)
        cell.text = text

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

    def _run_elements(self) -> List[ET.Element]:
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
    def runs(self) -> List[HwpxOxmlRun]:
        """Return the runs contained in this paragraph."""
        return [HwpxOxmlRun(run, self) for run in self._run_elements()]

    @property
    def text(self) -> str:
        """Return the concatenated textual content of this paragraph."""
        texts: List[str] = []
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
        return ET.SubElement(self.element, f"{_HP}run", attrs)

    @property
    def tables(self) -> List["HwpxOxmlTable"]:
        """Return the tables embedded within this paragraph."""

        tables: List[HwpxOxmlTable] = []
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
        border_fill_id_ref: str | int = "0",
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlTable:
        run = self._create_run_for_object(
            run_attributes,
            char_pr_id_ref=char_pr_id_ref,
        )
        table_element = HwpxOxmlTable.create(
            rows,
            cols,
            width=width,
            height=height,
            border_fill_id_ref=border_fill_id_ref,
        )
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
    def paragraphs(self) -> List[HwpxOxmlParagraph]:
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
    def memos(self) -> List[HwpxOxmlMemo]:
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

        paragraph = ET.Element(f"{_HP}p", attrs)

        if include_run:
            run_attrs = dict(run_attributes or {})
            if char_pr_id_ref is not None:
                run_attrs["charPrIDRef"] = str(char_pr_id_ref)
            elif "charPrIDRef" not in run_attrs:
                run_attrs["charPrIDRef"] = "0"

            run = ET.SubElement(paragraph, f"{_HP}run", run_attrs)
            text_element = ET.SubElement(run, f"{_HP}t")
            text_element.text = text

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

    def __init__(self, part_name: str, element: ET.Element):
        self.part_name = part_name
        self._element = element
        self._dirty = False

    @property
    def element(self) -> ET.Element:
        return self._element

    def _begin_num_element(self, create: bool = False) -> ET.Element | None:
        element = self._element.find(f"{_HH}beginNum")
        if element is None and create:
            element = ET.SubElement(self._element, f"{_HH}beginNum")
        return element

    def _memo_properties_element(self) -> ET.Element | None:
        ref_list = self._element.find(f"{_HH}refList")
        if ref_list is None:
            return None
        return ref_list.find(f"{_HH}memoProperties")

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
    ):
        self._manifest = manifest
        self._sections = list(sections)
        self._headers = list(headers)
        self._char_property_cache: dict[str, RunStyle] | None = None

        for section in self._sections:
            section.attach_document(self)

    @classmethod
    def from_package(cls, package: "HwpxPackage") -> "HwpxOxmlDocument":
        from hwpx.package import HwpxPackage  # Local import to avoid cycle during typing

        if not isinstance(package, HwpxPackage):
            raise TypeError("package must be an instance of HwpxPackage")

        manifest = package.get_xml(package.MANIFEST_PATH)
        section_paths = package.section_paths()
        header_paths = package.header_paths()

        sections = [
            HwpxOxmlSection(path, package.get_xml(path)) for path in section_paths
        ]
        headers = [HwpxOxmlHeader(path, package.get_xml(path)) for path in header_paths]
        return cls(manifest, sections, headers)

    @property
    def manifest(self) -> ET.Element:
        return self._manifest

    @property
    def sections(self) -> List[HwpxOxmlSection]:
        return list(self._sections)

    @property
    def headers(self) -> List[HwpxOxmlHeader]:
        return list(self._headers)

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
    def paragraphs(self) -> List[HwpxOxmlParagraph]:
        paragraphs: List[HwpxOxmlParagraph] = []
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
        return updates

    def reset_dirty(self) -> None:
        """Mark all parts as clean after a successful save."""
        for section in self._sections:
            section.reset_dirty()
        for header in self._headers:
            header.reset_dirty()
