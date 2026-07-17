# SPDX-License-Identifier: Apache-2.0
"""Contents/header.xml style, numbering, tracked-change, and resource service."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Callable, Iterable, Mapping, Sequence
import xml.etree.ElementTree as ET

from lxml import etree as LET  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

from ._document_primitives import (
    T,
    _FONT_FACE_LANG_TO_REF,
    _FONT_REF_ATTRIBUTES,
    _HC,
    _HC_NS,
    _HH,
    _append_child,
    _border_fill_is_basic_solid_line,
    _border_fill_matches,
    _create_basic_border_fill_element,
    _create_border_fill_element,
    _element_local_name,
    _get_int_attr,
    _normalize_border_side_names,
    _normalize_color,
    _serialize_xml,
)
from .common import GenericElement
from .header import (
    Bullet,
    Header,
    MemoProperties,
    MemoShape,
    ParagraphProperty,
    Style,
    TrackChange,
    TrackChangeAuthor,
    memo_shape_from_attributes,
    parse_bullets,
    parse_border_fills,
    parse_header_element,
    parse_paragraph_properties,
    parse_styles,
    parse_track_change_authors,
    parse_track_change_config,
    parse_track_changes,
    track_change_author_to_xml,
    track_change_to_xml,
)
from .namespaces import tag_local_name, tag_namespace
from .numbering import DocumentNumbering
from .utils import parse_int

if TYPE_CHECKING:
    from .document_parts import HwpxOxmlDocument


class HwpxOxmlHeader:
    """Represents a header XML part."""

    def __init__(self, part_name: str, element: ET.Element, document: "HwpxOxmlDocument" | None = None):  # type: ignore[reportGeneralTypeIssues]  # frozen public annotation
        self.part_name = part_name
        self._element = element
        self._dirty = False
        self._document = document

    @property
    def element(self) -> ET.Element:
        return self._element

    @property
    def document(self) -> "HwpxOxmlDocument" | None:  # type: ignore[reportGeneralTypeIssues]  # frozen public annotation
        return self._document

    def attach_document(self, document: "HwpxOxmlDocument") -> None:
        self._document = document

    def to_model(self) -> Header:
        return parse_header_element(self._convert_to_lxml(self._element))

    @staticmethod
    def _coerce_serialized_child(parent: ET.Element, child: LET._Element) -> ET.Element:
        if isinstance(parent, LET._Element):
            return child
        return ET.fromstring(LET.tostring(child, encoding="utf-8"))

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

    def font_ref_for_face(self, face: str) -> dict[str, str] | None:
        """Return ``hh:fontRef`` attributes for *face* when the header defines it."""

        target = face.strip()
        if not target:
            return None

        refs: dict[str, str] = {}
        for fontface in self._element.findall(f".//{_HH}fontface"):
            attr_name = _FONT_FACE_LANG_TO_REF.get(fontface.get("lang", "").upper())
            if attr_name is None:
                continue
            for font in fontface.findall(f"{_HH}font"):
                if font.get("face") == target and font.get("id"):
                    refs[attr_name] = font.get("id", "")
                    break

        if not refs:
            return None
        fallback = next(iter(refs.values()))
        return {name: refs.get(name, fallback) for name in _FONT_REF_ATTRIBUTES}

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

    def _bullets_element(self, create: bool = False) -> ET.Element | None:
        ref_list = self._ref_list_element(create=create)
        if ref_list is None:
            return None
        element = ref_list.find(f"{_HH}bullets")
        if element is None and create:
            element = ref_list.makeelement(f"{_HH}bullets", {"itemCnt": "0"})
            ref_list.append(element)
            self.mark_dirty()
        return element

    def _numberings_element(self, create: bool = False) -> ET.Element | None:
        ref_list = self._ref_list_element(create=create)
        if ref_list is None:
            return None
        element = ref_list.find(f"{_HH}numberings")
        if element is None and create:
            element = ref_list.makeelement(f"{_HH}numberings", {"itemCnt": "0"})
            ref_list.append(element)
            self.mark_dirty()
        return element

    def _para_properties_element(self, create: bool = False) -> ET.Element | None:
        ref_list = self._ref_list_element(create=create)
        if ref_list is None:
            return None
        element = ref_list.find(f"{_HH}paraProperties")
        if element is None and create:
            element = ref_list.makeelement(f"{_HH}paraProperties", {"itemCnt": "0"})
            ref_list.append(element)
            self.mark_dirty()
        return element

    @staticmethod
    def _allocate_ref_id(parent: ET.Element, child_tag: str) -> str:
        existing: set[str] = {
            child.get("id") or ""
            for child in parent.findall(child_tag)
        }
        existing.discard("")
        numeric_ids: list[int] = []
        for value in existing:
            try:
                numeric_ids.append(int(value))
            except ValueError:
                continue
        next_id = 1 if not numeric_ids else max(numeric_ids) + 1
        candidate = str(next_id)
        while candidate in existing:
            next_id += 1
            candidate = str(next_id)
        return candidate

    @staticmethod
    def _update_item_count(parent: ET.Element, child_tag: str) -> None:
        parent.set("itemCnt", str(len(parent.findall(child_tag))))

    @staticmethod
    def _default_para_head_attributes(level: int) -> dict[str, str]:
        return {
            "start": "1",
            "level": str(level),
            "align": "LEFT",
            "useInstWidth": "1",
            "autoIndent": "1",
            "widthAdjust": "0",
            "textOffsetType": "PERCENT",
            "textOffset": "50",
            "numFormat": "DIGIT",
            "charPrIDRef": "4294967295",
            "checkable": "0",
        }

    def _ensure_bullet_definition(self, char: str) -> str:
        bullets = self._bullets_element(create=True)
        if bullets is None:  # pragma: no cover - defensive branch
            raise RuntimeError("failed to create <bullets> element")
        for bullet in bullets.findall(f"{_HH}bullet"):
            if bullet.get("char") == char:
                bullet_id = bullet.get("id")
                if bullet_id:
                    return bullet_id

        bullet_id = self._allocate_ref_id(bullets, f"{_HH}bullet")
        bullet = bullets.makeelement(
            f"{_HH}bullet",
            {"id": bullet_id, "char": char, "useImage": "0"},
        )
        head_attrs = self._default_para_head_attributes(0)
        head_attrs.pop("start", None)
        head_attrs["useInstWidth"] = "0"
        _append_child(bullet, f"{_HH}paraHead", head_attrs)
        bullets.append(bullet)
        self._update_item_count(bullets, f"{_HH}bullet")
        self.mark_dirty()
        return bullet_id

    def _create_numbering_definition(self, levels: int | Sequence[Mapping[str, str]]) -> str:
        if isinstance(levels, int):
            level_specs: list[Mapping[str, str]] = [{} for _ in range(max(1, levels))]
        else:
            level_specs = list(levels) or [{}]

        numberings = self._numberings_element(create=True)
        if numberings is None:  # pragma: no cover - defensive branch
            raise RuntimeError("failed to create <numberings> element")

        first_start = str(level_specs[0].get("start") or "1")
        numbering_id = self._allocate_ref_id(numberings, f"{_HH}numbering")
        numbering = numberings.makeelement(
            f"{_HH}numbering",
            {"id": numbering_id, "start": first_start},
        )
        for index, level_spec in enumerate(level_specs):
            level = index + 1
            head_attrs = self._default_para_head_attributes(level)
            num_format = level_spec.get("numFormat") or level_spec.get("format")
            if num_format:
                head_attrs["numFormat"] = str(num_format).upper()
            start = level_spec.get("start")
            if start is not None:
                head_attrs["start"] = str(start)
            head = _append_child(
                numbering,
                f"{_HH}paraHead",
                head_attrs,
            )
            head.text = str(
                level_spec.get("text")
                or ".".join(f"^{part}" for part in range(1, level + 1)) + "."
            )
        numberings.append(numbering)
        self._update_item_count(numberings, f"{_HH}numbering")
        self.mark_dirty()
        return numbering_id

    def _ensure_para_property_heading(
        self,
        *,
        heading_type: str,
        id_ref: str,
        level: int,
    ) -> str:
        para_properties = self._para_properties_element(create=True)
        if para_properties is None:  # pragma: no cover - defensive branch
            raise RuntimeError("failed to create <paraProperties> element")

        for para_pr in para_properties.findall(f"{_HH}paraPr"):
            heading = para_pr.find(f"{_HH}heading")
            if heading is None:
                continue
            if (
                heading.get("type") == heading_type
                and heading.get("idRef") == str(id_ref)
                and heading.get("level") == str(level)
            ):
                para_pr_id = para_pr.get("id")
                if para_pr_id:
                    return para_pr_id

        base = para_properties.find(f"{_HH}paraPr")
        para_pr = deepcopy(base) if base is not None else para_properties.makeelement(f"{_HH}paraPr", {})
        para_pr.attrib.pop("id", None)
        for heading in list(para_pr.findall(f"{_HH}heading")):
            para_pr.remove(heading)
        heading = para_pr.makeelement(
            f"{_HH}heading",
            {"type": heading_type, "idRef": str(id_ref), "level": str(level)},
        )
        insert_at = 0
        for index, child in enumerate(list(para_pr)):
            if _element_local_name(child) == "align":
                insert_at = index + 1
                break
        para_pr.insert(insert_at, heading)
        para_pr_id = self._allocate_ref_id(para_properties, f"{_HH}paraPr")
        para_pr.set("id", para_pr_id)
        para_properties.append(para_pr)
        self._update_item_count(para_properties, f"{_HH}paraPr")
        self.mark_dirty()
        return para_pr_id

    def ensure_paragraph_alignment(self, align: str) -> str:
        """Return a paragraph property id with the requested horizontal alignment."""

        horizontal = self._normalize_paragraph_alignment(align)

        para_properties = self._para_properties_element(create=True)
        if para_properties is None:  # pragma: no cover - defensive branch
            raise RuntimeError("failed to create <paraProperties> element")

        for para_pr in para_properties.findall(f"{_HH}paraPr"):
            align_element = para_pr.find(f"{_HH}align")
            if align_element is not None and align_element.get("horizontal") == horizontal:
                para_pr_id = para_pr.get("id")
                if para_pr_id:
                    return para_pr_id

        base = para_properties.find(f"{_HH}paraPr")
        para_pr = deepcopy(base) if base is not None else para_properties.makeelement(f"{_HH}paraPr", {})
        para_pr.attrib.pop("id", None)
        align_element = para_pr.find(f"{_HH}align")
        if align_element is None:
            align_element = para_pr.makeelement(
                f"{_HH}align",
                {"horizontal": horizontal, "vertical": "BASELINE"},
            )
            para_pr.insert(0, align_element)
        else:
            align_element.set("horizontal", horizontal)
            if align_element.get("vertical") is None:
                align_element.set("vertical", "BASELINE")
        para_pr_id = self._allocate_ref_id(para_properties, f"{_HH}paraPr")
        para_pr.set("id", para_pr_id)
        para_properties.append(para_pr)
        self._update_item_count(para_properties, f"{_HH}paraPr")
        self.mark_dirty()
        return para_pr_id

    @staticmethod
    def _normalize_paragraph_alignment(align: str) -> str:
        normalized = align.strip().upper()
        aliases = {
            "LEFT": "LEFT",
            "START": "LEFT",
            "CENTER": "CENTER",
            "CENTRE": "CENTER",
            "MIDDLE": "CENTER",
            "RIGHT": "RIGHT",
            "END": "RIGHT",
            "JUSTIFY": "JUSTIFY",
            "DISTRIBUTE": "DISTRIBUTE",
        }
        horizontal = aliases.get(normalized)
        if horizontal is None:
            raise ValueError(f"unsupported paragraph alignment: {align}")
        return horizontal

    @staticmethod
    def _id_matches(raw_id: str | None, target: str | int | None) -> bool:
        if raw_id is None or target is None:
            return False
        raw = str(raw_id).strip()
        candidate = str(target).strip()
        if raw == candidate:
            return True
        try:
            return int(raw) == int(candidate)
        except ValueError:
            return False

    @staticmethod
    def _direct_child_by_local(parent: ET.Element, local_name: str) -> ET.Element | None:
        for child in parent:
            if _element_local_name(child) == local_name:
                return child
        return None

    @staticmethod
    def _descendants_by_local(parent: ET.Element, local_name: str) -> list[ET.Element]:
        return [
            child
            for child in parent.iter()
            if child is not parent and _element_local_name(child) == local_name
        ]

    @staticmethod
    def _remove_descendants_by_local(parent: ET.Element, local_name: str) -> None:
        for candidate_parent in list(parent.iter()):
            for child in list(candidate_parent):
                if _element_local_name(child) == local_name:
                    candidate_parent.remove(child)

    @staticmethod
    def _insert_child_after(
        parent: ET.Element,
        child: ET.Element,
        after_local_names: set[str],
    ) -> None:
        insert_at = 0
        for index, existing in enumerate(list(parent)):
            if _element_local_name(existing) in after_local_names:
                insert_at = index + 1
        parent.insert(insert_at, child)

    def _ensure_direct_para_child(
        self,
        para_pr: ET.Element,
        local_name: str,
        *,
        after_local_names: set[str],
    ) -> ET.Element:
        child = self._direct_child_by_local(para_pr, local_name)
        if child is not None:
            return child
        child = para_pr.makeelement(f"{_HH}{local_name}", {})
        self._insert_child_after(para_pr, child, after_local_names)
        return child

    def _base_para_property(
        self,
        para_properties: ET.Element,
        base_para_pr_id: str | int | None,
    ) -> ET.Element | None:
        if base_para_pr_id is not None:
            for para_pr in para_properties.findall(f"{_HH}paraPr"):
                if self._id_matches(para_pr.get("id"), base_para_pr_id):
                    return para_pr
        return para_properties.find(f"{_HH}paraPr")

    @staticmethod
    def _set_margin_unit_value(element: ET.Element, value: int) -> None:
        safe_value = str(int(value))
        if "value" in element.attrib or tag_namespace(element.tag) == _HC_NS:
            element.set("value", safe_value)
            element.set("unit", "HWPUNIT")
            element.text = None
            return
        element.text = safe_value
        if "unit" in element.attrib:
            element.set("unit", "HWPUNIT")

    def _apply_paragraph_margins(self, para_pr: ET.Element, margins: Mapping[str, int]) -> None:
        margin_elements = self._descendants_by_local(para_pr, "margin")
        if not margin_elements:
            margin = self._ensure_direct_para_child(
                para_pr,
                "margin",
                after_local_names={"breakSetting", "autoSpacing", "heading", "align"},
            )
            margin_elements = [margin]

        for margin in margin_elements:
            for name, value in margins.items():
                if value is None:
                    continue
                child = self._direct_child_by_local(margin, name)
                if child is None:
                    child = margin.makeelement(f"{_HH}{name}", {})
                    margin.append(child)
                self._set_margin_unit_value(child, int(value))

    def _apply_paragraph_line_spacing(self, para_pr: ET.Element, percent: int | float) -> None:
        value = str(int(round(float(percent))))
        line_spacing_elements = self._descendants_by_local(para_pr, "lineSpacing")
        if not line_spacing_elements:
            line_spacing = self._ensure_direct_para_child(
                para_pr,
                "lineSpacing",
                after_local_names={"margin"},
            )
            line_spacing_elements = [line_spacing]
        for line_spacing in line_spacing_elements:
            line_spacing.set("type", "PERCENT")
            line_spacing.set("value", value)
            line_spacing.set("unit", "PERCENT")

    def _apply_paragraph_border(self, para_pr: ET.Element, border: Mapping[str, str | int]) -> None:
        self._remove_descendants_by_local(para_pr, "border")
        attrs = {
            "borderFillIDRef": str(border.get("borderFillIDRef", border.get("border_fill_id_ref", "0"))),
            "offsetLeft": str(border.get("offsetLeft", border.get("offset_left", "0"))),
            "offsetRight": str(border.get("offsetRight", border.get("offset_right", "0"))),
            "offsetTop": str(border.get("offsetTop", border.get("offset_top", "0"))),
            "offsetBottom": str(border.get("offsetBottom", border.get("offset_bottom", "0"))),
            "connect": str(border.get("connect", "0")),
            "ignoreMargin": str(border.get("ignoreMargin", border.get("ignore_margin", "0"))),
        }
        border_element = para_pr.makeelement(f"{_HH}border", attrs)
        self._insert_child_after(
            para_pr,
            border_element,
            {"align", "heading", "breakSetting", "autoSpacing", "margin", "lineSpacing", "switch"},
        )

    def _apply_paragraph_break_setting(
        self, para_pr: ET.Element, break_setting: Mapping[str, bool]
    ) -> None:
        element = self._ensure_direct_para_child(
            para_pr,
            "breakSetting",
            after_local_names={"align", "heading"},
        )
        attr_map = {
            "keep_with_next": "keepWithNext",
            "keep_lines": "keepLines",
            "page_break_before": "pageBreakBefore",
            "widow_orphan": "widowOrphan",
        }
        for key, attr in attr_map.items():
            if key in break_setting and break_setting[key] is not None:
                element.set(attr, "1" if break_setting[key] else "0")

    def ensure_paragraph_format(
        self,
        *,
        base_para_pr_id: str | int | None = None,
        alignment: str | None = None,
        line_spacing_percent: int | float | None = None,
        margins: Mapping[str, int] | None = None,
        heading: Mapping[str, str | int] | None = None,
        border: Mapping[str, str | int] | None = None,
        break_setting: Mapping[str, bool] | None = None,
    ) -> str:
        """Return a new paragraph property id with requested formatting changes."""

        para_properties = self._para_properties_element(create=True)
        if para_properties is None:  # pragma: no cover - defensive branch
            raise RuntimeError("failed to create <paraProperties> element")

        base = self._base_para_property(para_properties, base_para_pr_id)
        para_pr = deepcopy(base) if base is not None else para_properties.makeelement(f"{_HH}paraPr", {})
        para_pr.attrib.pop("id", None)

        if alignment is not None:
            align_element = self._ensure_direct_para_child(
                para_pr,
                "align",
                after_local_names=set(),
            )
            align_element.set("horizontal", self._normalize_paragraph_alignment(alignment))
            if align_element.get("vertical") is None:
                align_element.set("vertical", "BASELINE")

        if heading is not None:
            self._remove_descendants_by_local(para_pr, "heading")
            heading_element = para_pr.makeelement(
                f"{_HH}heading",
                {
                    "type": str(heading.get("type", "NONE")).upper(),
                    "idRef": str(heading.get("idRef", heading.get("id_ref", "0"))),
                    "level": str(heading.get("level", "0")),
                },
            )
            self._insert_child_after(para_pr, heading_element, {"align"})

        clean_margins = {name: value for name, value in dict(margins or {}).items() if value is not None}
        if clean_margins:
            self._apply_paragraph_margins(para_pr, clean_margins)

        if line_spacing_percent is not None:
            self._apply_paragraph_line_spacing(para_pr, line_spacing_percent)

        if break_setting is not None:
            self._apply_paragraph_break_setting(para_pr, break_setting)
        if border is not None:
            self._apply_paragraph_border(para_pr, border)

        para_pr_id = self._allocate_ref_id(para_properties, f"{_HH}paraPr")
        para_pr.set("id", para_pr_id)
        para_properties.append(para_pr)
        self._update_item_count(para_properties, f"{_HH}paraPr")
        self.mark_dirty()
        return para_pr_id

    def ensure_numbering(
        self,
        *,
        kind: str,
        levels: Sequence[dict[str, str]] | None = None,
    ) -> list[str]:
        resolved_levels = list(levels or [{}])
        if not resolved_levels:
            resolved_levels = [{}]
        normalized_kind = kind.lower()
        if normalized_kind == "bullet":
            refs: list[str] = []
            default_chars = ["-", "○", "□", "•"]
            for index, level in enumerate(resolved_levels):
                bullet_char = str(level.get("char") or default_chars[index % len(default_chars)])
                bullet_id = self._ensure_bullet_definition(bullet_char)
                refs.append(
                    self._ensure_para_property_heading(
                        heading_type="BULLET",
                        id_ref=bullet_id,
                        level=index,
                    )
                )
            return refs
        if normalized_kind in {"number", "numbered", "numbering"}:
            numbering_id = self._create_numbering_definition(resolved_levels)
            return [
                self._ensure_para_property_heading(
                    heading_type="NUMBER",
                    id_ref=numbering_id,
                    level=index,
                )
                for index in range(len(resolved_levels))
            ]
        raise ValueError("kind must be 'bullet' or 'number'")

    def _styles_element(self) -> ET.Element | None:
        ref_list = self._ref_list_element()
        if ref_list is None:
            return None
        return ref_list.find(f"{_HH}styles")

    def _track_changes_element(self, create: bool = False) -> ET.Element | None:
        ref_list = self._ref_list_element(create=create)
        if ref_list is None:
            return None
        return ref_list.find(f"{_HH}trackChanges")

    def _track_changes_element_or_create(self) -> ET.Element:
        ref_list = self._ref_list_element(create=True)
        if ref_list is None:  # pragma: no cover - defensive branch
            raise RuntimeError("failed to create <refList> element")
        element = ref_list.find(f"{_HH}trackChanges")
        if element is None:
            element = ref_list.makeelement(f"{_HH}trackChanges", {"itemCnt": "0"})
            ref_list.append(element)
            self.mark_dirty()
        return element

    def _track_change_authors_element(self, create: bool = False) -> ET.Element | None:
        ref_list = self._ref_list_element(create=create)
        if ref_list is None:
            return None
        return ref_list.find(f"{_HH}trackChangeAuthors")

    def _track_change_authors_element_or_create(self) -> ET.Element:
        ref_list = self._ref_list_element(create=True)
        if ref_list is None:  # pragma: no cover - defensive branch
            raise RuntimeError("failed to create <refList> element")
        element = ref_list.find(f"{_HH}trackChangeAuthors")
        if element is None:
            element = ref_list.makeelement(f"{_HH}trackChangeAuthors", {"itemCnt": "0"})
            ref_list.append(element)
            self.mark_dirty()
        return element

    def _track_change_config_element(self, create: bool = False) -> ET.Element | None:
        for child in self._element:
            if tag_local_name(child.tag) in {"trackchageConfig", "trackchangeConfig"}:
                return child
        if not create:
            return None
        element = self._element.makeelement(f"{_HH}trackchageConfig", {"flags": "0"})
        self._element.append(element)
        self.mark_dirty()
        return element

    @property
    def track_change_config(self):
        element = self._track_change_config_element()
        if element is None:
            return None
        return parse_track_change_config(self._convert_to_lxml(element))

    def add_track_change(
        self,
        change_type: str,
        *,
        author_name: str = "AI Agent",
        date: str | None = None,
    ) -> int:
        model = self.to_model()
        change_id = model.add_track_change(
            change_type,
            author_name=author_name,
            date=date,
        )
        if model.ref_list is None or model.ref_list.track_changes is None:
            raise RuntimeError("failed to create tracked-change metadata")

        change = next(
            candidate
            for candidate in model.ref_list.track_changes.changes
            if candidate.id == change_id
        )
        changes_element = self._track_changes_element_or_create()
        changes_element.append(
            self._coerce_serialized_child(changes_element, track_change_to_xml(change))
        )
        changes_element.set("itemCnt", str(model.ref_list.track_changes.item_cnt or 0))

        authors = model.ref_list.track_change_authors
        if authors is not None and change.author_id is not None:
            author = authors.author_by_id(change.author_id)
            if author is not None:
                authors_element = self._track_change_authors_element_or_create()
                existing_ids = {
                    child.get("id")
                    for child in authors_element.findall(f"{_HH}trackChangeAuthor")
                }
                author_ids = {str(author.id)} if author.id is not None else set()
                if author.raw_id is not None:
                    author_ids.add(author.raw_id)
                if not existing_ids.intersection(author_ids):
                    authors_element.append(
                        self._coerce_serialized_child(
                            authors_element,
                            track_change_author_to_xml(author),
                        )
                    )
                authors_element.set("itemCnt", str(authors.item_cnt or 0))

        config_element = self._track_change_config_element(create=True)
        if config_element is None:  # pragma: no cover - defensive branch
            raise RuntimeError("failed to create <trackchageConfig> element")
        flags = 1
        if model.track_change_config is not None and model.track_change_config.flags is not None:
            flags = model.track_change_config.flags
        config_element.set("flags", str(flags | 1))
        self.mark_dirty()
        return change_id

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

    def ensure_border_fill(
        self,
        *,
        border_color: str = "#BFBFBF",
        border_width: str = "0.12 mm",
        fill_color: str | None = None,
        active_borders: Iterable[str] | None = None,
    ) -> str:
        element = self._border_fills_element(create=True)
        if element is None:  # pragma: no cover - defensive branch
            raise RuntimeError("failed to create <borderFills> element")

        normalized_border_color = _normalize_color(border_color) or "#BFBFBF"
        normalized_border_width = str(border_width or "0.12 mm")
        normalized_active_borders = _normalize_border_side_names(active_borders)
        normalized_fill_color = _normalize_color(fill_color)

        for border_fill in element.findall(f"{_HH}borderFill"):
            if _border_fill_matches(
                border_fill,
                border_color=normalized_border_color,
                border_width=normalized_border_width,
                fill_color=normalized_fill_color,
                active_borders=normalized_active_borders,
            ):
                border_id = border_fill.get("id")
                if border_id:
                    return border_id

        new_id = self._allocate_border_fill_id(element)
        new_border_fill = _create_border_fill_element(
            new_id,
            border_color=normalized_border_color,
            border_width=normalized_border_width,
            fill_color=normalized_fill_color,
            active_borders=normalized_active_borders,
        )
        if isinstance(element, LET._Element):
            new_border_fill = LET.fromstring(ET.tostring(new_border_fill, encoding="utf-8"))
        element.append(new_border_fill)
        self._update_border_fills_item_count(element)
        self.mark_dirty()
        return new_id

    def ensure_shading_border_fill(
        self,
        color: str,
        *,
        base_border_fill_id: str | int | None = None,
    ) -> str:
        element = self._border_fills_element(create=True)
        if element is None:  # pragma: no cover - defensive branch
            raise RuntimeError("failed to create <borderFills> element")
        face_color = _normalize_color(color) or "none"

        for border_fill in element.findall(f"{_HH}borderFill"):
            fill_brush = next(
                (child for child in border_fill if _element_local_name(child) == "fillBrush"),
                None,
            )
            if fill_brush is None:
                continue
            win_brush = next(
                (child for child in fill_brush if _element_local_name(child) == "winBrush"),
                None,
            )
            if win_brush is not None and win_brush.get("faceColor") == face_color:
                border_id = border_fill.get("id")
                if border_id:
                    return border_id

        base_element: ET.Element | None = None
        if base_border_fill_id is not None:
            base_element = element.find(f"{_HH}borderFill[@id='{base_border_fill_id}']")
        if base_element is None:
            existing_basic = self.find_basic_border_fill_id()
            if existing_basic is not None:
                base_element = element.find(f"{_HH}borderFill[@id='{existing_basic}']")
        new_id = self._allocate_border_fill_id(element)
        if base_element is None:
            new_border_fill = _create_basic_border_fill_element(new_id)
        else:
            new_border_fill = deepcopy(base_element)
            new_border_fill.set("id", new_id)
            for child in list(new_border_fill):
                if _element_local_name(child) == "fillBrush":
                    new_border_fill.remove(child)

        fill_brush = new_border_fill.makeelement(f"{_HC}fillBrush", {})
        _append_child(
            fill_brush,
            f"{_HC}winBrush",
            {"faceColor": face_color, "hatchColor": "#FF000000", "alpha": "0"},
        )
        new_border_fill.append(fill_brush)
        if isinstance(element, LET._Element) and not isinstance(new_border_fill, LET._Element):
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

    # ------------------------------------------------------------------
    # BinData / Image management
    # ------------------------------------------------------------------

    def _bin_data_list_element(self, create: bool = False) -> ET.Element | None:
        """Return the ``<hh:binDataList>`` element inside ``<hh:refList>``."""

        ref_list = self._ref_list_element(create=create)
        if ref_list is None:
            return None
        element = ref_list.find(f"{_HH}binDataList")
        if element is None and create:
            element = ref_list.makeelement(f"{_HH}binDataList", {"itemCnt": "0"})
            ref_list.append(element)
            self.mark_dirty()
        return element

    def _update_bin_data_list_count(self, bin_data_list: ET.Element) -> None:
        count = len(list(bin_data_list.findall(f"{_HH}binItem")))
        bin_data_list.set("itemCnt", str(count))

    def _allocate_bin_item_id(self, bin_data_list: ET.Element) -> str:
        """Return the next available numeric id for a ``<hh:binItem>``."""

        existing: set[int] = set()
        for child in bin_data_list.findall(f"{_HH}binItem"):
            raw = child.get("id")
            if raw is not None:
                try:
                    existing.add(int(raw))
                except ValueError:
                    pass
        next_id = 0 if not existing else max(existing) + 1
        return str(next_id)

    def add_bin_item(
        self,
        *,
        item_type: str = "Embedding",
        bin_data_id: str | None = None,
        format: str | None = None,
        a_path: str | None = None,
        r_path: str | None = None,
    ) -> tuple[str, ET.Element]:
        """Add a ``<hh:binItem>`` and return ``(id, element)``.

        For embedded images *bin_data_id* should be the ``BIN0001.jpg``-style
        identifier stored in the ZIP and *format* should be the image format
        extension (``jpg``, ``png``, …).
        """

        bin_data_list = self._bin_data_list_element(create=True)
        if bin_data_list is None:  # pragma: no cover
            raise RuntimeError("failed to create <binDataList> element")

        item_id = self._allocate_bin_item_id(bin_data_list)

        attrs: dict[str, str] = {"id": item_id, "Type": item_type}
        if bin_data_id is not None:
            attrs["BinData"] = bin_data_id
        if format is not None:
            attrs["Format"] = format
        if a_path is not None:
            attrs["APath"] = a_path
        if r_path is not None:
            attrs["RPath"] = r_path

        element = bin_data_list.makeelement(f"{_HH}binItem", attrs)
        bin_data_list.append(element)
        self._update_bin_data_list_count(bin_data_list)
        self.mark_dirty()
        return item_id, element

    def list_bin_items(self) -> list[dict[str, str]]:
        """Return a list of dicts describing each ``<hh:binItem>``."""

        bin_data_list = self._bin_data_list_element()
        if bin_data_list is None:
            return []
        items: list[dict[str, str]] = []
        for child in bin_data_list.findall(f"{_HH}binItem"):
            items.append(dict(child.attrib))
        return items

    def remove_bin_item(self, item_id: str | int) -> bool:
        """Remove a ``<hh:binItem>`` by ID.  Returns ``True`` if removed."""

        bin_data_list = self._bin_data_list_element()
        if bin_data_list is None:
            return False
        target_id = str(item_id)
        for child in bin_data_list.findall(f"{_HH}binItem"):
            if child.get("id") == target_id:
                bin_data_list.remove(child)
                self._update_bin_data_list_count(bin_data_list)
                self.mark_dirty()
                return True
        return False

    def to_bytes(self) -> bytes:
        return _serialize_xml(self._element)

__all__ = ["HwpxOxmlHeader"]
