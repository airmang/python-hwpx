# SPDX-License-Identifier: Apache-2.0
"""Section body, layout-cache, memo, and composition OXML service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Optional, Sequence
import xml.etree.ElementTree as ET

from ._document_primitives import (
    _DEFAULT_PARAGRAPH_ATTRS,
    _HP,
    _HP_NS,
    _append_child,
    _append_text_with_tabs,
    _child_tag_like,
    _children_by_local,
    _clear_paragraph_layout_cache,
    _clone_paragraph_element,
    _element_local_name,
    _first_child_by_local,
    _paragraph_id,
    _remove_stale_paragraph_layout_cache,
    _serialize_xml,
)
from .memo import HwpxOxmlMemo, HwpxOxmlMemoGroup
from .paragraph import HwpxOxmlParagraph
from .section_format import HwpxOxmlSectionProperties
from .section_story import HwpxOxmlSectionHeaderFooter

if TYPE_CHECKING:
    from .document_parts import HwpxOxmlDocument


class HwpxOxmlSection:
    """Represents the contents of a section XML part."""

    def __init__(
        self,
        part_name: str,
        element: ET.Element,
        document: "HwpxOxmlDocument" | None = None,  # type: ignore[reportGeneralTypeIssues]  # frozen public annotation
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

        paragraph = _first_child_by_local(self._element, "p")
        if paragraph is None:
            paragraph_attrs = dict(_DEFAULT_PARAGRAPH_ATTRS)
            paragraph_attrs["id"] = _paragraph_id()
            paragraph = _append_child(
                self._element,
                _child_tag_like(self._element, "p", _HP_NS),
                paragraph_attrs,
            )
        run = _first_child_by_local(paragraph, "run")
        if run is None:
            run = _append_child(
                paragraph,
                _child_tag_like(paragraph, "run", _HP_NS),
                {"charPrIDRef": "0"},
            )
        element = _append_child(run, _child_tag_like(run, "secPr", _HP_NS))
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
        return _children_by_local(self._element, "p")

    @property
    def element(self) -> ET.Element:
        """Return the underlying XML element."""
        return self._element

    @property
    def document(self) -> "HwpxOxmlDocument" | None:  # type: ignore[reportGeneralTypeIssues]  # frozen public annotation
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
            element = _append_child(self._element, f"{_HP}memogroup", {})
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

    def remove_paragraph(
        self,
        paragraph: HwpxOxmlParagraph | int,
    ) -> None:
        """Remove *paragraph* from this section.

        Accepts either a :class:`HwpxOxmlParagraph` instance or an integer
        index into :attr:`paragraphs`.  Raises ``ValueError`` if the section
        would become empty (HWPX requires at least one ``<hp:p>``).
        """
        if isinstance(paragraph, int):
            paras = self.paragraphs
            if paragraph < 0 or paragraph >= len(paras):
                raise IndexError(f"단락 인덱스 {paragraph}이(가) 범위를 벗어났습니다 (총 {len(paras)}개)")
            paragraph = paras[paragraph]
        paragraph.remove()

    def add_paragraph(
        self,
        text: str = "",
        *,
        para_pr_id_ref: str | int | None = None,
        style_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        include_run: bool = True,
        inherit_style: bool = True,
        **extra_attrs: str,
    ) -> HwpxOxmlParagraph:
        """Create a new paragraph element appended to this section.

        When *inherit_style* is ``True`` (the default) and no explicit
        ``paraPrIDRef``, ``styleIDRef`` or ``charPrIDRef`` is given, the
        values are inherited from the **last** paragraph in the section so
        that consecutive paragraphs share the same formatting.

        The optional ``para_pr_id_ref`` and ``style_id_ref`` parameters
        control the paragraph-level references, while ``char_pr_id_ref`` and
        ``run_attributes`` customise the initial ``<hp:run>`` element when
        ``include_run`` is :data:`True`.
        """

        # Collect style refs from the last paragraph for inheritance.
        prev_para_ref: str | None = None
        prev_style_ref: str | None = None
        prev_char_ref: str | None = None
        if inherit_style:
            existing = self.paragraphs
            if existing:
                last = existing[-1]
                prev_para_ref = last.para_pr_id_ref
                prev_style_ref = last.style_id_ref
                prev_char_ref = last.char_pr_id_ref

        attrs = {"id": _paragraph_id(), **_DEFAULT_PARAGRAPH_ATTRS}
        attrs.update(extra_attrs)

        if para_pr_id_ref is not None:
            attrs["paraPrIDRef"] = str(para_pr_id_ref)
        elif prev_para_ref is not None:
            attrs["paraPrIDRef"] = prev_para_ref
        if style_id_ref is not None:
            attrs["styleIDRef"] = str(style_id_ref)
        elif prev_style_ref is not None:
            attrs["styleIDRef"] = prev_style_ref

        paragraph = self._element.makeelement(f"{_HP}p", attrs)

        if include_run:
            run_attrs = dict(run_attributes or {})
            if char_pr_id_ref is not None:
                run_attrs["charPrIDRef"] = str(char_pr_id_ref)
            elif "charPrIDRef" not in run_attrs:
                if prev_char_ref is not None:
                    run_attrs["charPrIDRef"] = prev_char_ref
                else:
                    run_attrs["charPrIDRef"] = "0"

            run = paragraph.makeelement(f"{_HP}run", run_attrs)
            paragraph.append(run)
            _append_text_with_tabs(run, text)

        self._element.append(paragraph)
        self._dirty = True
        return HwpxOxmlParagraph(paragraph, self)

    def insert_paragraphs(
        self,
        index: int,
        paragraphs: Sequence[HwpxOxmlParagraph | ET.Element],
    ) -> list[HwpxOxmlParagraph]:
        """Insert paragraph copies at *index* and return wrappers for them."""

        existing = self.paragraphs
        if index < 0 or index > len(existing):
            raise IndexError(f"단락 인덱스 {index}이(가) 범위를 벗어났습니다 (총 {len(existing)}개)")

        inserted: list[HwpxOxmlParagraph] = []
        for offset, paragraph in enumerate(paragraphs):
            source_element = paragraph.element if isinstance(paragraph, HwpxOxmlParagraph) else paragraph
            cloned = _clone_paragraph_element(source_element)
            self._element.insert(index + offset, cloned)
            inserted.append(HwpxOxmlParagraph(cloned, self))

        if inserted:
            self._dirty = True
        return inserted

    def copy_paragraph_range(self, start: int, end: int) -> list[ET.Element]:
        """Return deep-copied paragraph elements for the inclusive range."""

        paragraphs = self.paragraphs
        total = len(paragraphs)
        if start < 0 or end < 0 or start >= total or end >= total or start > end:
            raise IndexError(f"문단 범위 {start}..{end}이(가) 유효하지 않습니다 (총 {total}개)")
        return [_clone_paragraph_element(paragraphs[index].element) for index in range(start, end + 1)]

    def mark_dirty(self) -> None:
        self._dirty = True

    @property
    def dirty(self) -> bool:
        return self._dirty

    def reset_dirty(self) -> None:
        self._dirty = False

    def remove_stale_layout_caches(self) -> int:
        """Drop paragraph layout caches that no longer match plain text length."""

        removed = 0
        for paragraph in self._element.iter():
            if _element_local_name(paragraph) != "p":
                continue
            if _remove_stale_paragraph_layout_cache(paragraph):
                removed += 1
        if removed:
            self.mark_dirty()
        return removed

    def remove_layout_caches(self) -> int:
        """Drop all paragraph layout caches from this section.

        Layout cache is editor-derived metadata. Once a section has been
        modified, preserving it is riskier than allowing the editor to
        recalculate it on open.
        """

        removed = 0
        for paragraph in self._element.iter():
            if _element_local_name(paragraph) != "p":
                continue
            removed += _clear_paragraph_layout_cache(paragraph)
        if removed:
            self.mark_dirty()
        return removed

    def to_bytes(self) -> bytes:
        return _serialize_xml(self._element)

__all__ = ["HwpxOxmlSection", "HwpxOxmlSectionHeaderFooter", "HwpxOxmlSectionProperties"]
