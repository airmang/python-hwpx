# SPDX-License-Identifier: Apache-2.0
"""Top-level HWPX OXML part composition and dirty serialization service."""

from __future__ import annotations

from copy import deepcopy
import logging
from typing import TYPE_CHECKING, Iterable, Sequence
import xml.etree.ElementTree as ET

from hwpx.opc.relationships import resolve_part_name

from ._document_primitives import (
    _DEFAULT_PARAGRAPH_ATTRS,
    _FONT_REF_ATTRIBUTES,
    _HH,
    _HP,
    _HS,
    _append_child,
    _char_height_from_points,
    _element_local_name,
    _is_integer_literal,
    _normalize_color,
    _object_id,
    _paragraph_id,
    _serialize_xml,
)
from .common import GenericElement
from .header import (
    Bullet,
    MemoShape,
    ParagraphProperty,
    Style,
    TrackChange,
    TrackChangeAuthor,
)
from .header_part import HwpxOxmlHeader
from .namespaces import tag_local_name
from .paragraph import HwpxOxmlParagraph
from .run import RunStyle, _char_properties_from_header
from .section import HwpxOxmlSection
from .simple_parts import HwpxOxmlHistory, HwpxOxmlMasterPage, HwpxOxmlVersion

if TYPE_CHECKING:
    from hwpx.opc.package import HwpxPackage


logger = logging.getLogger(__name__)


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
        manifest_path: str = "Contents/content.hpf",
    ):
        self._manifest_path = manifest_path
        self._manifest = manifest
        self._sections = list(sections)
        self._headers = list(headers)
        self._master_pages = list(master_pages or [])
        self._histories = list(histories or [])
        self._version = version
        self._char_property_cache: dict[str, RunStyle] | None = None
        self._manifest_dirty = False

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
        from hwpx.opc.package import (
            HwpxPackage,
        )  # Local import to avoid cycle during typing

        if not isinstance(package, HwpxPackage):
            raise TypeError("package must be an instance of HwpxPackage")

        manifest = package.manifest_tree()
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
            logger.warning(
                "manifest가 가리키는 version 파트가 누락되었습니다: part_path=%s",
                version_path,
            )
        return cls(
            manifest,
            sections,
            headers,
            master_pages=master_pages,
            histories=histories,
            version=version,
            manifest_path=package.main_content.full_path,
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
        color: str | None = None,
        font: str | None = None,
        size: int | float | None = None,
        highlight: str | None = None,
        strike: bool | None = None,
        base_char_pr_id: str | int | None = None,
    ) -> str:
        """Return a char property identifier matching the requested flags."""

        if not self._headers:
            raise ValueError("document does not contain any headers")

        header = self._headers[0]
        target = (bool(bold), bool(italic), bool(underline))
        target_color = _normalize_color(color)
        target_highlight = _normalize_color(highlight)
        target_height = _char_height_from_points(size)
        target_font_ref = header.font_ref_for_face(font) if font is not None else None

        def element_flags(element: ET.Element) -> tuple[bool, bool, bool]:
            bold_present = element.find(f"{_HH}bold") is not None
            italic_present = element.find(f"{_HH}italic") is not None
            underline_element = element.find(f"{_HH}underline")
            underline_present = False
            if underline_element is not None:
                underline_present = underline_element.get("type", "").upper() != "NONE"
            return bold_present, italic_present, underline_present

        def element_strike(element: ET.Element) -> bool:
            strike_element = element.find(f"{_HH}strikeout")
            if strike_element is None:
                return False
            return strike_element.get("shape", "").upper() != "NONE"

        def predicate(element: ET.Element) -> bool:
            if element_flags(element) != target:
                return False
            if target_color is not None and element.get("textColor") != target_color:
                return False
            if (
                target_highlight is not None
                and element.get("shadeColor") != target_highlight
            ):
                return False
            if target_height is not None and element.get("height") != target_height:
                return False
            if strike is not None and element_strike(element) != bool(strike):
                return False
            if target_font_ref is not None:
                font_ref = element.find(f"{_HH}fontRef")
                if font_ref is None:
                    return False
                if {
                    key: font_ref.get(key, "") for key in _FONT_REF_ATTRIBUTES
                } != target_font_ref:
                    return False
            return True

        def modifier(element: ET.Element) -> None:
            underline_nodes = list(element.findall(f"{_HH}underline"))
            base_underline_attrs = (
                dict(underline_nodes[0].attrib) if underline_nodes else {}
            )
            strike_nodes = list(element.findall(f"{_HH}strikeout"))
            base_strike_attrs = dict(strike_nodes[0].attrib) if strike_nodes else {}

            for child in list(element.findall(f"{_HH}bold")):
                element.remove(child)
            for child in list(element.findall(f"{_HH}italic")):
                element.remove(child)
            for child in underline_nodes:
                element.remove(child)
            for child in strike_nodes:
                element.remove(child)

            if target_color is not None:
                element.set("textColor", target_color)
            if target_highlight is not None:
                element.set("shadeColor", target_highlight)
            if target_height is not None:
                element.set("height", target_height)
            if target_font_ref is not None:
                font_ref = element.find(f"{_HH}fontRef")
                if font_ref is None:
                    font_ref = element.makeelement(f"{_HH}fontRef", {})
                    element.insert(0, font_ref)
                for attr_name in list(font_ref.attrib.keys()):
                    if attr_name not in _FONT_REF_ATTRIBUTES:
                        del font_ref.attrib[attr_name]
                for attr_name, attr_value in target_font_ref.items():
                    font_ref.set(attr_name, attr_value)

            if target[0]:
                _append_child(element, f"{_HH}bold")
            if target[1]:
                _append_child(element, f"{_HH}italic")

            underline_attrs = dict(base_underline_attrs)
            if target[2]:
                underline_attrs.setdefault("type", "SOLID")
                if underline_attrs.get("type", "").upper() == "NONE":
                    underline_attrs["type"] = "SOLID"
                underline_attrs.setdefault(
                    "shape", base_underline_attrs.get("shape", "SOLID")
                )
                if "color" not in underline_attrs and "color" in base_underline_attrs:
                    underline_attrs["color"] = base_underline_attrs["color"]
                if "color" not in underline_attrs:
                    underline_attrs["color"] = "#000000"
                _append_child(element, f"{_HH}underline", underline_attrs)
            else:
                attrs = dict(base_underline_attrs)
                attrs["type"] = "NONE"
                attrs.setdefault("shape", base_underline_attrs.get("shape", "SOLID"))
                if "color" in base_underline_attrs:
                    attrs["color"] = base_underline_attrs["color"]
                _append_child(element, f"{_HH}underline", attrs)
            if strike is not None:
                strike_attrs = dict(base_strike_attrs)
                strike_attrs["shape"] = "SOLID" if strike else "NONE"
                strike_attrs.setdefault(
                    "color", base_strike_attrs.get("color", "#000000")
                )
                _append_child(element, f"{_HH}strikeout", strike_attrs)

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

    def border_fill(
        self, border_fill_id_ref: int | str | None
    ) -> GenericElement | None:
        return HwpxOxmlHeader._lookup_by_id(self.border_fills, border_fill_id_ref)

    def ensure_basic_border_fill(self) -> str:
        if not self._headers:
            return "0"

        for header in self._headers:
            existing = header.find_basic_border_fill_id()
            if existing is not None:
                return existing

        return self._headers[0].ensure_basic_border_fill()

    def ensure_border_fill(
        self,
        *,
        border_color: str = "#BFBFBF",
        border_width: str = "0.12 mm",
        fill_color: str | None = None,
        active_borders: Iterable[str] | None = None,
    ) -> str:
        if not self._headers:
            return "0"
        return self._headers[0].ensure_border_fill(
            border_color=border_color,
            border_width=border_width,
            fill_color=fill_color,
            active_borders=active_borders,
        )

    def ensure_shading_border_fill(
        self,
        color: str,
        *,
        base_border_fill_id: str | int | None = None,
    ) -> str:
        if not self._headers:
            return "0"
        return self._headers[0].ensure_shading_border_fill(
            color,
            base_border_fill_id=base_border_fill_id,
        )

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

    def ensure_numbering(
        self,
        *,
        kind: str,
        levels: Sequence[dict[str, str]] | None = None,
    ) -> list[str]:
        if not self._headers:
            raise ValueError("document does not contain any headers")
        return self._headers[0].ensure_numbering(kind=kind, levels=levels)

    @property
    def styles(self) -> dict[str, Style]:
        mapping: dict[str, Style] = {}
        for header in self._headers:
            mapping.update(header.styles)
        return mapping

    def style(self, style_id_ref: int | str | None) -> Style | None:
        return HwpxOxmlHeader._lookup_by_id(self.styles, style_id_ref)

    def _style_name_id_map(self) -> dict[str, str]:
        """Return unique style name/engName aliases that resolve to numeric ids."""

        aliases: dict[str, str] = {}
        conflicts: set[str] = set()
        for header in self._headers:
            for style in header.element.iter():
                if _element_local_name(style) != "style":
                    continue
                style_id = style.get("id")
                if style_id is None or not _is_integer_literal(style_id):
                    continue
                resolved_id = style_id.strip()
                for attr_name in ("name", "engName"):
                    alias = (style.get(attr_name) or "").strip()
                    if not alias:
                        continue
                    existing = aliases.get(alias)
                    if existing is not None and existing != resolved_id:
                        conflicts.add(alias)
                        continue
                    aliases[alias] = resolved_id

        for alias in conflicts:
            aliases.pop(alias, None)
        return aliases

    def _normalize_named_style_references(self) -> int:
        """Convert paragraph ``styleIDRef`` names to ids when headers define them."""

        style_ids_by_name = self._style_name_id_map()
        if not style_ids_by_name:
            return 0

        replacements = 0
        for section in self._sections:
            section_replacements = 0
            for paragraph in section.element.iter():
                if _element_local_name(paragraph) != "p":
                    continue
                style_id_ref = paragraph.get("styleIDRef")
                if style_id_ref is None or _is_integer_literal(style_id_ref):
                    continue
                replacement = style_ids_by_name.get(style_id_ref.strip())
                if replacement is None:
                    continue
                if style_id_ref != replacement:
                    paragraph.set("styleIDRef", replacement)
                    section_replacements += 1
            if section_replacements:
                section.mark_dirty()
                replacements += section_replacements
        return replacements

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

    def add_track_change(
        self,
        change_type: str,
        *,
        author_name: str = "AI Agent",
        date: str | None = None,
    ) -> int:
        if not self._headers:
            raise ValueError("document does not contain any headers")
        return self._headers[0].add_track_change(
            change_type,
            author_name=author_name,
            date=date,
        )

    def next_track_change_mark_id(self) -> int:
        max_id = 0
        for section in self._sections:
            for element in section.element.iter():
                if tag_local_name(element.tag) not in {
                    "insertBegin",
                    "insertEnd",
                    "deleteBegin",
                    "deleteEnd",
                }:
                    continue
                raw_id = element.get("Id")
                if raw_id is None:
                    continue
                try:
                    max_id = max(max_id, int(raw_id))
                except ValueError:
                    continue
        return max_id + 1

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
        inherit_style: bool = True,
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
            inherit_style=inherit_style,
            **extra_attrs,
        )

    def remove_paragraph(
        self,
        paragraph: HwpxOxmlParagraph | int,
        *,
        section: "HwpxOxmlSection | None" = None,
        section_index: int | None = None,
    ) -> None:
        """Remove *paragraph* from the document.

        When *paragraph* is an integer it is treated as an index into the
        paragraphs of the specified (or last) section.
        """
        if isinstance(paragraph, int):
            if section is None and section_index is not None:
                section = self._sections[section_index]
            if section is None:
                if not self._sections:
                    raise ValueError("document does not contain any sections")
                section = self._sections[-1]
            section.remove_paragraph(paragraph)
        else:
            paragraph.remove()

    def copy_paragraph_range(
        self,
        start: int,
        end: int,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> list[ET.Element]:
        """Return deep-copied paragraph elements for an inclusive range."""

        if section is None and section_index is not None:
            section = self._sections[section_index]
        if section is None:
            if not self._sections:
                raise ValueError("document does not contain any sections")
            section = self._sections[-1]
        return section.copy_paragraph_range(start, end)

    def insert_paragraphs(
        self,
        index: int,
        paragraphs: Sequence[HwpxOxmlParagraph | ET.Element],
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> list[HwpxOxmlParagraph]:
        """Insert copied paragraphs into the requested section."""

        if section is None and section_index is not None:
            section = self._sections[section_index]
        if section is None:
            if not self._sections:
                raise ValueError("document does not contain any sections")
            section = self._sections[-1]
        return section.insert_paragraphs(index, paragraphs)

    # ------------------------------------------------------------------
    # Section management
    # ------------------------------------------------------------------

    @staticmethod
    def _has_positive_page_geometry(section_properties: ET.Element) -> bool:
        page_properties = section_properties.find(f"{_HP}pagePr")
        if page_properties is None or page_properties.find(f"{_HP}margin") is None:
            return False
        try:
            page_width = int(page_properties.get("width", "0"))
            page_height = int(page_properties.get("height", "0"))
        except (TypeError, ValueError):
            return False
        return page_width > 0 and page_height > 0

    @classmethod
    def _renderable_section_carriers(
        cls,
        section: HwpxOxmlSection,
    ) -> tuple[ET.Element, ET.Element, ET.Element] | None:
        """Locate a valid ``secPr`` and its ``colPr`` carrier."""
        first_paragraph = section.element.find(f"{_HP}p")
        if first_paragraph is None:
            return None
        first_run = first_paragraph.find(f"{_HP}run")
        if first_run is None:
            return None

        section_properties = first_run.find(f"{_HP}secPr")
        if section_properties is None:
            return None
        if not cls._has_positive_page_geometry(section_properties):
            return None

        for control in first_run.findall(f"{_HP}ctrl"):
            column_properties = control.find(f"{_HP}colPr")
            if column_properties is not None:
                return section_properties, control, column_properties
        return None

    @classmethod
    def _copy_renderable_section_layout(
        cls,
        section: HwpxOxmlSection,
    ) -> tuple[ET.Element, ET.Element] | None:
        """Return story-free ``secPr`` and ``colPr`` carriers from *section*.

        Hancom requires every section part to carry positive page geometry and
        a column definition in its first paragraph's first run.  Header/footer
        stories are deliberately excluded because their object identifiers and
        content belong to the source section.
        """
        carriers = cls._renderable_section_carriers(section)
        if carriers is None:
            return None
        section_properties, column_control, column_properties = carriers

        copied_properties = deepcopy(section_properties)
        story_children = {
            "header",
            "footer",
            "headerApply",
            "footerApply",
            "masterPage",
            "presentation",
        }
        for child in list(copied_properties):
            if _element_local_name(child) in story_children:
                copied_properties.remove(child)
        copied_properties.set("masterPageCnt", "0")
        if copied_properties.get("id") is None:
            copied_properties.set("id", "")

        copied_column_control = column_control.makeelement(
            column_control.tag,
            dict(column_control.attrib),
        )
        copied_column_properties = deepcopy(column_properties)
        column_id = copied_column_properties.get("id")
        if column_id:
            copied_column_properties.set("id", _object_id())
        elif column_id is None:
            copied_column_properties.set("id", "")
        copied_column_control.append(copied_column_properties)
        return copied_properties, copied_column_control

    def _section_layout_for_insertion(
        self,
        *,
        after: int | None,
    ) -> tuple[ET.Element, ET.Element]:
        """Select the nearest renderable layout for a newly inserted section."""
        if not self._sections:
            raise ValueError(
                "cannot add a renderable section: the document has no source section"
            )

        anchor = len(self._sections) - 1 if after is None else after
        candidate_indices = sorted(
            range(len(self._sections)),
            key=lambda index: (abs(index - anchor), index),
        )
        for index in candidate_indices:
            layout = self._copy_renderable_section_layout(self._sections[index])
            if layout is not None:
                return layout

        raise ValueError(
            "cannot add a renderable section: no existing section has positive "
            "page geometry, margins, and a column definition"
        )

    def _normalize_section_anchor(self, after: int | None) -> int | None:
        """Resolve a Python-style section index without mutating the document."""
        if after is None:
            return None
        section_count = len(self._sections)
        normalized = after if after >= 0 else section_count + after
        if normalized < 0 or normalized >= section_count:
            raise IndexError(
                f"section index {after} is out of range ({section_count} sections)"
            )
        return normalized

    def _sync_header_section_count(self) -> None:
        """Keep ``hh:head/@secCnt`` aligned with the section spine."""
        document_headers = [
            header
            for header in self._headers
            if _element_local_name(header.element) == "head"
        ]
        if not document_headers:
            raise ValueError("cannot update sections: the document has no hh:head part")
        section_count = str(len(self._sections))
        for header in document_headers:
            if header.element.get("secCnt") != section_count:
                header.element.set("secCnt", section_count)
                header.mark_dirty()

    def add_section(self, *, after: int | None = None) -> HwpxOxmlSection:
        """Append a new empty section to the document.

        If *after* is given, the section is inserted after the section at
        that index. Otherwise it is appended at the end.

        Returns the newly created :class:`HwpxOxmlSection`.
        """
        normalized_after = self._normalize_section_anchor(after)
        section_properties, column_control = self._section_layout_for_insertion(
            after=normalized_after
        )
        if not any(
            _element_local_name(header.element) == "head" for header in self._headers
        ):
            raise ValueError(
                "cannot add a renderable section: the document has no hh:head part"
            )
        self._manifest_section_containers()

        # Determine part name
        existing_indices: list[int] = []
        for sec in self._sections:
            import re as _section_re

            m = _section_re.search(r"section(\d+)", sec.part_name)
            if m:
                existing_indices.append(int(m.group(1)))
        next_index = (max(existing_indices) + 1) if existing_indices else 0
        section_id = f"section{next_index}"
        part_name = f"Contents/{section_id}.xml"

        # Build a renderable empty section.  ``secPr`` and ``colPr`` must
        # precede body text in the first paragraph's first run.
        section_element = section_properties.makeelement(f"{_HS}sec", {})
        para_attrs = {"id": _paragraph_id(), **_DEFAULT_PARAGRAPH_ATTRS}
        para = _append_child(section_element, f"{_HP}p", para_attrs)
        run = _append_child(para, f"{_HP}run", {"charPrIDRef": "0"})
        run.append(section_properties)
        run.append(column_control)
        _append_child(run, f"{_HP}t", {})

        new_section = HwpxOxmlSection(part_name, section_element, self)

        if normalized_after is not None:
            insert_pos = normalized_after + 1
            self._sections.insert(insert_pos, new_section)
        else:
            self._sections.append(new_section)
        spine_index = self._sections.index(new_section)

        # Update manifest: add <opf:item> and <opf:itemref>
        self._add_section_to_manifest(
            section_id,
            part_name,
            spine_index=spine_index,
        )
        self._sync_header_section_count()

        new_section.mark_dirty()
        return new_section

    def remove_section(
        self,
        section: "HwpxOxmlSection | int",
    ) -> None:
        """Remove a section from the document.

        Accepts either a :class:`HwpxOxmlSection` or an integer index.
        Raises ``ValueError`` if the document would be left with no sections.
        """
        if len(self._sections) <= 1:
            raise ValueError(
                "문서에는 최소 하나의 섹션이 필요합니다. 마지막 섹션은 삭제할 수 없습니다."
            )
        if not any(
            _element_local_name(header.element) == "head" for header in self._headers
        ):
            raise ValueError(
                "cannot remove a section: the document has no hh:head part"
            )
        if isinstance(section, int):
            if section < 0 or section >= len(self._sections):
                raise IndexError(
                    f"섹션 인덱스 {section}이(가) 범위를 벗어났습니다 (총 {len(self._sections)}개)"
                )
            removed = self._sections[section]
        else:
            if section not in self._sections:
                raise ValueError("해당 섹션이 이 문서에 속하지 않습니다.") from None
            removed = section

        self._section_manifest_references(removed.part_name)
        self._sections.remove(removed)

        # Update manifest: remove <opf:item> and <opf:itemref>
        self._remove_section_from_manifest(removed.part_name)
        self._sync_header_section_count()

    # ------------------------------------------------------------------
    # Manifest helpers (private)
    # ------------------------------------------------------------------

    _OPF_NS = "http://www.idpf.org/2007/opf/"

    def _manifest_section_containers(self) -> tuple[ET.Element, ET.Element]:
        """Return manifest/spine containers or fail before section mutation."""
        ns = {"opf": self._OPF_NS}
        manifest_el = self._manifest.find("opf:manifest", ns)
        spine_el = self._manifest.find("opf:spine", ns)
        missing: list[str] = []
        if manifest_el is None:
            missing.append("opf:manifest")
        if spine_el is None:
            missing.append("opf:spine")
        if missing:
            raise ValueError(
                "cannot update sections: content manifest is missing "
                + " and ".join(missing)
            )
        assert manifest_el is not None
        assert spine_el is not None
        return manifest_el, spine_el

    def _section_manifest_references(
        self,
        part_name: str,
    ) -> tuple[ET.Element, ET.Element, ET.Element, ET.Element]:
        """Resolve a section's item and itemref across full/relative href forms."""
        manifest_el, spine_el = self._manifest_section_containers()
        known_parts = {part_name, *(section.part_name for section in self._sections)}
        target_item: ET.Element | None = None
        for item in manifest_el.findall(f"{{{self._OPF_NS}}}item"):
            href = item.get("href")
            if (
                href
                and resolve_part_name(
                    self._manifest_path,
                    href,
                    known_parts=known_parts,
                )
                == part_name
            ):
                target_item = item
                break
        if target_item is None or not target_item.get("id"):
            raise ValueError(
                f"cannot update sections: manifest item for {part_name!r} is missing"
            )
        target_id = target_item.get("id")
        target_ref = next(
            (
                itemref
                for itemref in spine_el.findall(f"{{{self._OPF_NS}}}itemref")
                if itemref.get("idref") == target_id
            ),
            None,
        )
        if target_ref is None:
            raise ValueError(
                f"cannot update sections: spine itemref for {part_name!r} is missing"
            )
        return manifest_el, spine_el, target_item, target_ref

    def _add_section_to_manifest(
        self,
        section_id: str,
        href: str,
        *,
        spine_index: int,
    ) -> None:
        """Add an ``<opf:item>`` + ``<opf:itemref>`` for a new section."""
        manifest_el, spine_el = self._manifest_section_containers()
        item = manifest_el.makeelement(
            f"{{{self._OPF_NS}}}item",
            {"id": section_id, "href": href, "media-type": "application/xml"},
        )
        manifest_el.append(item)
        itemref = spine_el.makeelement(
            f"{{{self._OPF_NS}}}itemref",
            {"idref": section_id, "linear": "yes"},
        )
        section_hrefs = {section.part_name for section in self._sections}
        section_ids = {
            candidate.get("id")
            for candidate in manifest_el.findall(f"{{{self._OPF_NS}}}item")
            if candidate.get("href")
            and resolve_part_name(
                self._manifest_path,
                candidate.get("href", ""),
                known_parts=section_hrefs,
            )
            in section_hrefs
        }
        section_positions = [
            index
            for index, candidate in enumerate(spine_el)
            if candidate.get("idref") in section_ids
        ]
        if spine_index < len(section_positions):
            insert_at = section_positions[spine_index]
        elif section_positions:
            insert_at = section_positions[-1] + 1
        else:
            insert_at = len(spine_el)
        spine_el.insert(insert_at, itemref)
        self._manifest_dirty = True

    def _remove_section_from_manifest(self, part_name: str) -> None:
        """Remove the ``<opf:item>`` + ``<opf:itemref>`` for a deleted section."""
        manifest_el, spine_el, target_item, target_ref = (
            self._section_manifest_references(part_name)
        )
        manifest_el.remove(target_item)
        spine_el.remove(target_ref)
        self._manifest_dirty = True

    def serialize(self) -> dict[str, bytes]:
        """Return a mapping of part names to updated XML payloads."""
        updates: dict[str, bytes] = {}
        self._normalize_named_style_references()
        if self._manifest_dirty:
            updates[self._manifest_path] = _serialize_xml(self._manifest)
        for section in self._sections:
            if section.dirty:
                section.remove_layout_caches()
            else:
                section.remove_stale_layout_caches()
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
        self._manifest_dirty = False
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


__all__ = ["HwpxOxmlDocument"]
