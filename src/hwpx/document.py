# SPDX-License-Identifier: Apache-2.0
"""High-level representation of an HWPX document."""

from __future__ import annotations

import xml.etree.ElementTree as ET
import io
import os
import re
import tempfile
import warnings
from datetime import datetime
import logging
import uuid

from os import PathLike
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, BinaryIO, Iterator, Mapping, Sequence, overload

from lxml import etree

from .oxml import (
    Bullet,
    GenericElement,
    HwpxOxmlDocument,
    HwpxOxmlHeader,
    HwpxOxmlHistory,
    HwpxOxmlInlineObject,
    HwpxOxmlMasterPage,
    HwpxOxmlMemo,
    HwpxOxmlNote,
    HwpxOxmlParagraph,
    HwpxOxmlRun,
    HwpxOxmlSection,
    HwpxOxmlSectionHeaderFooter,
    HwpxOxmlShape,
    HwpxOxmlTable,
    HwpxOxmlVersion,
    MemoShape,
    ParagraphProperty,
    RunStyle,
    Style,
    TrackChange,
    TrackChangeAuthor,
)
from .opc.package import (
    HwpxPackage,
    _UNCHECKED_SAVE_TOKEN,
)
from .oxml.namespaces import HC, HH, HH_NS, HP, HP_NS, register_owpml_namespaces
from .quality import QualityPolicy, SavePipeline, VisualCompleteReport
from .quality.report import OpenSafetyReport
from .templates import blank_document_bytes

register_owpml_namespaces(ET.register_namespace)

_HP_NS = HP_NS
_HP = HP
_HC = HC
_HH_NS = HH_NS
_HH = HH
_HWP_UNITS_PER_MM = 7200 / 25.4
_HWP_UNITS_PER_PT = 100

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .tools.table_navigation import TableFillResult, TableLabelSearchResult, TableMapResult


def _append_element(
    parent: Any,
    tag: str,
    attributes: dict[str, str] | None = None,
) -> Any:
    """Create and append a child element that matches *parent*'s element type."""

    child = parent.makeelement(tag, attributes or {})
    parent.append(child)
    return child


def _mm_to_hwp_units(value: float) -> int:
    return round(value * _HWP_UNITS_PER_MM)


def _pt_to_hwp_units(value: float) -> int:
    return round(value * _HWP_UNITS_PER_PT)


_PAPER_SIZES_MM: dict[str, tuple[float, float]] = {
    "A3": (297.0, 420.0),
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "B4": (257.0, 364.0),
    "B5": (182.0, 257.0),
    "LETTER": (215.9, 279.4),
    "LEGAL": (215.9, 355.6),
}

_FORM_FIELD_EXCLUDED_TYPES = {"HYPERLINK", "MEMO"}
_FORM_FIELD_TYPES = {"FORM", "CLICKHERE", "CLICK_HERE", "CLICK-HERE", "NURUMTUL", "누름틀"}
_FORM_FIELD_NAME_ATTRS = ("fieldName", "fieldname", "name", "title", "id", "fieldid")
_FORM_FIELD_PROMPT_ATTRS = ("prompt", "instruction", "description", "desc", "help", "memo")
_FORM_FIELD_PARAM_NAMES = {
    "fieldname",
    "field_name",
    "name",
    "title",
    "prompt",
    "instruction",
    "description",
    "desc",
    "help",
    "memo",
    "guide",
}
_TEXT_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def _local_name(node_or_tag: Any) -> str:
    tag = getattr(node_or_tag, "tag", node_or_tag)
    if not isinstance(tag, str):
        return ""
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _sanitize_field_text(value: str) -> str:
    return _TEXT_ILLEGAL.sub("", value)


def _field_type_tokens(*values: str | None) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        if not value:
            continue
        raw = str(value).strip()
        if not raw:
            continue
        tokens.add(raw.upper())
        tokens.add(raw.replace("_", "").replace("-", "").upper())
    return tokens


def _is_form_field_begin(ctrl: Any, field_begin: Any) -> bool:
    tokens = _field_type_tokens(
        ctrl.get("type"),
        field_begin.get("type"),
        field_begin.get("name"),
        field_begin.get("fieldName"),
        field_begin.get("fieldname"),
    )
    if tokens & _FORM_FIELD_EXCLUDED_TYPES:
        return False
    if tokens & _FORM_FIELD_TYPES:
        return True
    return (ctrl.get("type") or "").strip().upper() == "FORM"


def _field_identifier(field_begin: Any) -> str:
    for attr in ("id", "fieldid", "name", "fieldName", "fieldname"):
        value = (field_begin.get(attr) or "").strip()
        if value:
            return value
    return ""


def _field_end_matches(field_begin: Any, field_end: Any) -> bool:
    begin_keys = {
        value
        for value in (
            field_begin.get("id"),
            field_begin.get("fieldid"),
            field_begin.get("name"),
        )
        if value
    }
    end_keys = {
        value
        for value in (
            field_end.get("beginIDRef"),
            field_end.get("fieldid"),
            field_end.get("id"),
        )
        if value
    }
    if begin_keys and end_keys:
        return bool(begin_keys & end_keys)
    return not begin_keys


def _field_parameters(field_begin: Any) -> list[dict[str, str]]:
    parameters: list[dict[str, str]] = []
    for node in field_begin.iter():
        if not _local_name(node).endswith("Param"):
            continue
        name = (node.get("name") or "").strip()
        value = "".join(node.itertext()).strip()
        if name or value:
            parameters.append({"name": name, "value": value})
    return parameters


def _first_attr(element: Any, names: Sequence[str]) -> str:
    for name in names:
        value = (element.get(name) or "").strip()
        if value:
            return value
    return ""


def _field_parameter_value(parameters: Sequence[dict[str, str]], *names: str) -> str:
    wanted = {name.casefold() for name in names}
    for item in parameters:
        name = item.get("name", "").casefold()
        value = item.get("value", "").strip()
        if name in wanted and value:
            return value
    return ""


def _clear_form_field_layout_cache(paragraph: Any) -> int:
    removed = 0
    for child in list(paragraph):
        if _local_name(child).lower() == "linesegarray":
            paragraph.remove(child)
            removed += 1
    return removed


def _normalize_page_orientation(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    aliases = {
        "PORTRAIT": "PORTRAIT",
        "NARROW": "PORTRAIT",
        "NARROWLY": "PORTRAIT",
        "LANDSCAPE": "WIDELY",
        "WIDE": "WIDELY",
        "WIDELY": "WIDELY",
    }
    orientation = aliases.get(normalized)
    if orientation is None:
        raise ValueError(f"unsupported page orientation: {value}")
    return orientation


def _png_dimensions(image_data: bytes) -> tuple[int, int] | None:
    if len(image_data) < 24 or not image_data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    width = int.from_bytes(image_data[16:20], "big")
    height = int.from_bytes(image_data[20:24], "big")
    if width <= 0 or height <= 0:
        return None
    return width, height


def _bin_data_stem(value: Any) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    stem = PurePosixPath(raw).stem
    return stem or None


# The atomic byte writer and the stream checkpoint/rollback writer now live in
# ``hwpx.quality.save_pipeline`` — the single SavePipeline is the only thing that
# writes serialized HWPX output to a destination (plan §2 Phase B, "zero bypass").
# ``save_to_path`` / ``save_to_stream`` / ``save_report`` route every write through
# ``self._save_pipeline.run(...)`` below.


def _summarize_validation_issues(issues: Sequence[Any], *, limit: int = 5) -> str:
    selected = [str(issue) for issue in issues[:limit]]
    remaining = len(issues) - len(selected)
    summary = "; ".join(selected)
    if remaining > 0:
        summary += f" ... and {remaining} more"
    return summary


class HwpxDocument:
    """Provides a user-friendly API for editing HWPX documents."""

    def __init__(
        self,
        package: HwpxPackage,
        root: HwpxOxmlDocument,
        *,
        managed_resources: tuple[Any, ...] = (),
        validate_on_save: bool = False,
    ):
        self._package = package
        self._root = root
        self._managed_resources = list(managed_resources)
        self._closed = False
        self.validate_on_save = validate_on_save
        # The one gate every write funnels through (plan §2 Phase B). The oracle
        # is resolved lazily and only when a policy actually renders, so normal
        # (transparent) saves never probe Hancom.
        self._save_pipeline = SavePipeline()

    def __repr__(self) -> str:
        """Return a compact and safe summary of the document state."""

        return (
            f"{self.__class__.__name__}("
            f"sections={len(self.sections)}, "
            f"paragraphs={len(self.paragraphs)}, "
            f"headers={len(self.headers)}, "
            f"master_pages={len(self.master_pages)}, "
            f"histories={len(self.histories)}, "
            f"closed={self._closed}"
            ")"
        )

    # ------------------------------------------------------------------
    # construction helpers
    @classmethod
    def open(
        cls,
        source: str | PathLike[str] | bytes | BinaryIO,
    ) -> "HwpxDocument":
        """Open *source* and return a :class:`HwpxDocument` instance.

        Raises:
            HwpxStructureError: 필수 파일이나 구조가 올바르지 않은 HWPX를 열 때 발생합니다.
            HwpxPackageError: 패키지를 여는 과정에서 일반적인 I/O/포맷 오류가 발생하면 전달됩니다.
        """
        internal_resources: list[Any] = []
        open_source = source
        if isinstance(source, bytes):
            stream = io.BytesIO(source)
            open_source = stream
            internal_resources.append(stream)
        package = HwpxPackage.open(open_source)
        root = HwpxOxmlDocument.from_package(package)
        return cls(package, root, managed_resources=tuple(internal_resources))

    @classmethod
    def new(cls) -> "HwpxDocument":
        """Return a new blank document based on the default skeleton template."""

        return cls.open(blank_document_bytes())

    @classmethod
    def from_package(cls, package: HwpxPackage) -> "HwpxDocument":
        """Create a document backed by an existing :class:`HwpxPackage`.

        Args:
            package: :class:`hwpx.opc.package.HwpxPackage` 인스턴스.
        """
        root = HwpxOxmlDocument.from_package(package)
        return cls(package, root)

    def __enter__(self) -> "HwpxDocument":
        """컨텍스트 매니저 진입 시 현재 문서 인스턴스를 반환합니다."""

        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        """예외 발생 여부와 무관하게 내부 자원을 안전하게 정리합니다."""

        self.close()
        return False

    def close(self) -> None:
        """문서가 관리하는 내부 패키지/스트림 자원을 정리합니다.

        정리 정책:
        - ``flush()`` 가능한 자원은 먼저 flush를 시도합니다.
        - ``close()`` 가능한 자원은 flush 이후 close를 시도합니다.
        - flush/close 중 발생한 예외는 로깅하고 무시하여 정리 루틴을 계속 진행합니다.
        - 같은 문서에서 ``close()``를 여러 번 호출해도 안전합니다.
        """

        if self._closed:
            return

        self._flush_resource(self._package)
        for resource in self._managed_resources:
            self._flush_resource(resource)

        self._close_resource(self._package)
        for resource in self._managed_resources:
            self._close_resource(resource)

        self._managed_resources.clear()
        self._closed = True

    @staticmethod
    def _flush_resource(resource: Any) -> None:
        flush = getattr(resource, "flush", None)
        if not callable(flush):
            return
        try:
            flush()
        except Exception:
            logger.debug("자원 flush 중 예외를 무시합니다: resource=%r", resource, exc_info=True)

    @staticmethod
    def _close_resource(resource: Any) -> None:
        close = getattr(resource, "close", None)
        if not callable(close):
            return
        try:
            close()
        except Exception:
            logger.debug("자원 close 중 예외를 무시합니다: resource=%r", resource, exc_info=True)

    # ------------------------------------------------------------------
    # properties exposing document content
    @property
    def package(self) -> HwpxPackage:
        """Return the :class:`HwpxPackage` backing this document."""
        return self._package

    @property
    def oxml(self) -> HwpxOxmlDocument:
        """Return the low-level XML object tree representing the document."""
        return self._root

    @property
    def sections(self) -> list[HwpxOxmlSection]:
        """Return the sections contained in the document."""
        return self._root.sections

    @property
    def headers(self) -> list[HwpxOxmlHeader]:
        """Return the header parts referenced by the document."""
        return self._root.headers

    @property
    def master_pages(self) -> list[HwpxOxmlMasterPage]:
        """Return the master-page parts declared in the manifest."""
        return self._root.master_pages

    @property
    def histories(self) -> list[HwpxOxmlHistory]:
        """Return document history parts referenced by the manifest."""
        return self._root.histories

    @property
    def version(self) -> HwpxOxmlVersion | None:
        """Return the version metadata part if present."""
        return self._root.version

    @property
    def border_fills(self) -> dict[str, GenericElement]:
        """Return border fill definitions declared in the headers."""

        return self._root.border_fills

    def border_fill(self, border_fill_id_ref: int | str | None) -> GenericElement | None:
        """Return the border fill definition referenced by *border_fill_id_ref*."""

        return self._root.border_fill(border_fill_id_ref)

    def ensure_border_fill(
        self,
        *,
        border_color: str = "#BFBFBF",
        border_width: str = "0.12 mm",
        fill_color: str | None = None,
        active_borders: Sequence[str] | None = None,
    ) -> str:
        """Return a borderFill id matching the requested border/fill attributes."""

        return self._root.ensure_border_fill(
            border_color=border_color,
            border_width=border_width,
            fill_color=fill_color,
            active_borders=active_borders,
        )

    @property
    def memo_shapes(self) -> dict[str, MemoShape]:
        """Return memo shapes available in the header reference lists."""

        return self._root.memo_shapes

    def memo_shape(self, memo_shape_id_ref: int | str | None) -> MemoShape | None:
        """Return the memo shape definition referenced by *memo_shape_id_ref*."""

        return self._root.memo_shape(memo_shape_id_ref)

    @property
    def bullets(self) -> dict[str, Bullet]:
        """Return bullet definitions declared in header reference lists."""

        return self._root.bullets

    def bullet(self, bullet_id_ref: int | str | None) -> Bullet | None:
        """Return the bullet definition referenced by *bullet_id_ref*."""

        return self._root.bullet(bullet_id_ref)

    @property
    def paragraph_properties(self) -> dict[str, ParagraphProperty]:
        """Return paragraph property definitions declared in headers."""

        return self._root.paragraph_properties

    def paragraph_property(
        self, para_pr_id_ref: int | str | None
    ) -> ParagraphProperty | None:
        """Return the paragraph property referenced by *para_pr_id_ref*."""

        return self._root.paragraph_property(para_pr_id_ref)

    def ensure_numbering(
        self,
        *,
        kind: str,
        levels: Sequence[dict[str, str]] | None = None,
    ) -> list[str]:
        """Return paragraph property ids for bullet or numbered-list levels."""

        return self._root.ensure_numbering(kind=kind, levels=levels)

    @property
    def styles(self) -> dict[str, Style]:
        """Return style definitions available in the document."""

        return self._root.styles

    def style(self, style_id_ref: int | str | None) -> Style | None:
        """Return the style definition referenced by *style_id_ref*."""

        return self._root.style(style_id_ref)

    @property
    def track_changes(self) -> dict[str, TrackChange]:
        """Return tracked change metadata declared in the headers."""

        return self._root.track_changes

    def track_change(self, change_id_ref: int | str | None) -> TrackChange | None:
        """Return tracked change metadata referenced by *change_id_ref*."""

        return self._root.track_change(change_id_ref)

    @property
    def track_change_authors(self) -> dict[str, TrackChangeAuthor]:
        """Return tracked change author metadata declared in the headers."""

        return self._root.track_change_authors

    def track_change_author(
        self, author_id_ref: int | str | None
    ) -> TrackChangeAuthor | None:
        """Return tracked change author details referenced by *author_id_ref*."""

        return self._root.track_change_author(author_id_ref)

    @property
    def memos(self) -> list[HwpxOxmlMemo]:
        """Return all memo entries declared in every section."""

        memos: list[HwpxOxmlMemo] = []
        for section in self._root.sections:
            memos.extend(section.memos)
        return memos

    def add_memo(
        self,
        text: str = "",
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        memo_shape_id_ref: str | int | None = None,
        memo_id: str | None = None,
        char_pr_id_ref: str | int | None = None,
        attributes: dict[str, str] | None = None,
    ) -> HwpxOxmlMemo:
        """Create a memo entry inside *section* (or the last section by default)."""

        if section is None and section_index is not None:
            section = self._root.sections[section_index]
        if section is None:
            if not self._root.sections:
                raise ValueError("document does not contain any sections")
            section = self._root.sections[-1]
        return section.add_memo(
            text,
            memo_shape_id_ref=memo_shape_id_ref,
            memo_id=memo_id,
            char_pr_id_ref=char_pr_id_ref,
            attributes=attributes,
        )

    def remove_memo(self, memo: HwpxOxmlMemo) -> None:
        """Remove *memo* from the section it belongs to."""

        memo.remove()

    def attach_memo_field(
        self,
        paragraph: HwpxOxmlParagraph,
        memo: HwpxOxmlMemo,
        *,
        field_id: str | None = None,
        author: str | None = None,
        created: datetime | str | None = None,
        number: int = 1,
        char_pr_id_ref: str | int | None = None,
    ) -> str:
        """Attach a MEMO field control to *paragraph* so Hangul shows *memo*."""

        if paragraph.section is None:
            raise ValueError("paragraph must belong to a section before anchoring a memo")
        if memo.group.section is None:
            raise ValueError("memo is not attached to a section")

        field_value = field_id or uuid.uuid4().hex
        author_value = author or memo.attributes.get("author") or ""

        created_value = created if created is not None else memo.attributes.get("createDateTime")
        if isinstance(created_value, datetime):
            created_value = created_value.strftime("%Y-%m-%d %H:%M:%S")
        elif created_value is None:
            created_value = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            created_value = str(created_value)

        memo_shape_id = memo.memo_shape_id_ref or ""

        char_ref = char_pr_id_ref
        if char_ref is None:
            char_ref = paragraph.char_pr_id_ref
        if char_ref is None:
            char_ref = memo._infer_char_pr_id_ref()
        if char_ref is None:
            char_ref = "0"
        char_ref = str(char_ref)

        paragraph_element = paragraph.element
        run_begin = paragraph_element.makeelement(f"{_HP}run", {"charPrIDRef": char_ref})
        ctrl_begin = _append_element(run_begin, f"{_HP}ctrl")
        field_begin = _append_element(
            ctrl_begin,
            f"{_HP}fieldBegin",
            {
                "id": field_value,
                "type": "MEMO",
                "editable": "true",
                "dirty": "false",
                "fieldid": field_value,
            },
        )

        parameters = _append_element(field_begin, f"{_HP}parameters", {"count": "5", "name": ""})
        _append_element(parameters, f"{_HP}stringParam", {"name": "ID"}).text = memo.id or ""
        _append_element(parameters, f"{_HP}integerParam", {"name": "Number"}).text = str(max(1, number))
        _append_element(parameters, f"{_HP}stringParam", {"name": "CreateDateTime"}).text = created_value
        _append_element(parameters, f"{_HP}stringParam", {"name": "Author"}).text = author_value
        _append_element(parameters, f"{_HP}stringParam", {"name": "MemoShapeID"}).text = memo_shape_id

        sub_list = _append_element(
            field_begin,
            f"{_HP}subList",
            {
                "id": f"memo-field-{memo.id or field_value}",
                "textDirection": "HORIZONTAL",
                "lineWrap": "BREAK",
                "vertAlign": "TOP",
            },
        )
        sub_para = _append_element(
            sub_list,
            f"{_HP}p",
            {
                "id": f"memo-field-{(memo.id or field_value)}-p",
                "paraPrIDRef": "0",
                "styleIDRef": "0",
                "pageBreak": "0",
                "columnBreak": "0",
                "merged": "0",
            },
        )
        sub_run = _append_element(sub_para, f"{_HP}run", {"charPrIDRef": char_ref})
        _append_element(sub_run, f"{_HP}t").text = memo.id or field_value

        run_end = paragraph_element.makeelement(f"{_HP}run", {"charPrIDRef": char_ref})
        ctrl_end = _append_element(run_end, f"{_HP}ctrl")
        _append_element(ctrl_end, f"{_HP}fieldEnd", {"beginIDRef": field_value, "fieldid": field_value})

        paragraph.element.insert(0, run_begin)
        paragraph.element.append(run_end)
        paragraph.section.mark_dirty()

        return field_value

    def add_memo_with_anchor(
        self,
        text: str = "",
        *,
        paragraph: HwpxOxmlParagraph | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        paragraph_text: str | None = None,
        memo_shape_id_ref: str | int | None = None,
        memo_id: str | None = None,
        char_pr_id_ref: str | int | None = None,
        attributes: dict[str, str] | None = None,
        field_id: str | None = None,
        author: str | None = None,
        created: datetime | str | None = None,
        number: int = 1,
        anchor_char_pr_id_ref: str | int | None = None,
    ) -> tuple[HwpxOxmlMemo, HwpxOxmlParagraph, str]:
        """Create a memo and ensure it is visible by anchoring a MEMO field."""

        memo = self.add_memo(
            text,
            section=section,
            section_index=section_index,
            memo_shape_id_ref=memo_shape_id_ref,
            memo_id=memo_id,
            char_pr_id_ref=char_pr_id_ref,
            attributes=attributes,
        )

        target_paragraph = paragraph
        if target_paragraph is None:
            memo_section = memo.group.section
            if memo_section is None:
                raise ValueError("memo must belong to a section")
            paragraph_value = "" if paragraph_text is None else paragraph_text
            anchor_char = anchor_char_pr_id_ref or char_pr_id_ref
            target_paragraph = self.add_paragraph(
                paragraph_value,
                section=memo_section,
                char_pr_id_ref=anchor_char,
            )
        elif paragraph_text is not None:
            target_paragraph.text = paragraph_text

        field_value = self.attach_memo_field(
            target_paragraph,
            memo,
            field_id=field_id,
            author=author,
            created=created,
            number=number,
            char_pr_id_ref=anchor_char_pr_id_ref,
        )

        return memo, target_paragraph, field_value

    def remove_paragraph(
        self,
        paragraph: HwpxOxmlParagraph | int,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> None:
        """Remove a paragraph from the document.

        *paragraph* may be a :class:`HwpxOxmlParagraph` instance or an
        integer index into the paragraphs of the specified (or last)
        section.

        Raises ``ValueError`` if the target section would become empty.
        """
        self._root.remove_paragraph(
            paragraph,
            section=section,
            section_index=section_index,
        )

    def add_section(self, *, after: int | None = None) -> HwpxOxmlSection:
        """Append a new empty section to the document.

        If *after* is given, the section is inserted after the section at
        that index.  Returns the newly created section.
        """
        return self._root.add_section(after=after)

    def remove_section(
        self, section: HwpxOxmlSection | int,
    ) -> None:
        """Remove a section from the document.

        Raises ``ValueError`` if the document would have no sections left.
        """
        self._root.remove_section(section)

    @property
    def paragraphs(self) -> list[HwpxOxmlParagraph]:
        """Return all paragraphs across every section."""
        return self._root.paragraphs

    @property
    def char_properties(self) -> dict[str, RunStyle]:
        """Return the resolved character style definitions available to the document."""

        return self._root.char_properties

    def char_property(self, char_pr_id_ref: int | str | None) -> RunStyle | None:
        """Return the style referenced by *char_pr_id_ref* if known."""

        return self._root.char_property(char_pr_id_ref)

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
        """Return a ``charPr`` identifier matching the requested flags."""

        return self._root.ensure_run_style(
            bold=bold,
            italic=italic,
            underline=underline,
            color=color,
            font=font,
            size=size,
            highlight=highlight,
            strike=strike,
            base_char_pr_id=base_char_pr_id,
        )

    def iter_runs(self) -> Iterator[HwpxOxmlRun]:
        """Yield every run element contained in the document."""

        for paragraph in self.paragraphs:
            for run in paragraph.runs:
                yield run

    def find_runs_by_style(
        self,
        *,
        text_color: str | None = None,
        underline_type: str | None = None,
        underline_color: str | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> list[HwpxOxmlRun]:
        """Return runs matching the requested style criteria."""

        matches: list[HwpxOxmlRun] = []
        target_char = str(char_pr_id_ref).strip() if char_pr_id_ref is not None else None

        for run in self.iter_runs():
            if target_char is not None:
                run_char = (run.char_pr_id_ref or "").strip()
                if run_char != target_char:
                    continue
            style = run.style
            if text_color is not None:
                if style is None or style.text_color() != text_color:
                    continue
            if underline_type is not None:
                if style is None or style.underline_type() != underline_type:
                    continue
            if underline_color is not None:
                if style is None or style.underline_color() != underline_color:
                    continue
            matches.append(run)
        return matches

    def replace_text_in_runs(
        self,
        search: str,
        replacement: str,
        *,
        text_color: str | None = None,
        underline_type: str | None = None,
        underline_color: str | None = None,
        char_pr_id_ref: str | int | None = None,
        limit: int | None = None,
    ) -> int:
        """Replace occurrences of *search* in runs matching the provided style filters."""

        if not search:
            raise ValueError("search must be a non-empty string")

        replacements = 0
        runs = self.find_runs_by_style(
            text_color=text_color,
            underline_type=underline_type,
            underline_color=underline_color,
            char_pr_id_ref=char_pr_id_ref,
        )

        for run in runs:
            remaining = None
            if limit is not None:
                remaining = limit - replacements
                if remaining <= 0:
                    break
            original_char_pr = run.char_pr_id_ref
            replaced_here = run.replace_text(
                search,
                replacement,
                count=remaining,
            )
            if replaced_here and original_char_pr is not None:
                # Ensure the run retains its original formatting reference even
                # if XML nodes were rewritten during substitution.
                run.char_pr_id_ref = original_char_pr
            replacements += replaced_here
            if limit is not None and replacements >= limit:
                break
        return replacements

    # ------------------------------------------------------------------
    # editing helpers
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
        """Append a paragraph to the document and return it.

        When *inherit_style* is ``True`` (the default) and no explicit
        style references are given, the new paragraph inherits
        ``paraPrIDRef``, ``styleIDRef`` and ``charPrIDRef`` from the
        last paragraph in the target section so that consecutive
        paragraphs share the same formatting.

        Formatting references may be overridden via ``para_pr_id_ref``,
        ``style_id_ref`` and ``char_pr_id_ref``. Any additional keyword
        arguments are added as raw paragraph attributes.
        """
        return self._root.add_paragraph(
            text,
            section=section,
            section_index=section_index,
            para_pr_id_ref=para_pr_id_ref,
            style_id_ref=style_id_ref,
            char_pr_id_ref=char_pr_id_ref,
            run_attributes=run_attributes,
            include_run=include_run,
            inherit_style=inherit_style,
            **extra_attrs,
        )

    def add_table(
        self,
        rows: int,
        cols: int,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        width: int | None = None,
        height: int | None = None,
        border_fill_id_ref: str | int | None = None,
        para_pr_id_ref: str | int | None = None,
        style_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        **extra_attrs: str,
    ) -> HwpxOxmlTable:
        """Create a table in a new paragraph and return it."""

        resolved_border_fill: str | int | None = border_fill_id_ref
        if resolved_border_fill is None:
            resolved_border_fill = self._root.ensure_basic_border_fill()

        paragraph = self.add_paragraph(
            "",
            section=section,
            section_index=section_index,
            para_pr_id_ref=para_pr_id_ref,
            style_id_ref=style_id_ref,
            char_pr_id_ref=char_pr_id_ref,
            include_run=False,
            **extra_attrs,
        )
        return paragraph.add_table(
            rows,
            cols,
            width=width,
            height=height,
            border_fill_id_ref=resolved_border_fill,
            run_attributes=run_attributes,
            char_pr_id_ref=char_pr_id_ref,
        )

    def add_picture(
        self,
        image_data: bytes,
        image_format: str,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        width: int | None = None,
        height: int | None = None,
        width_mm: float | None = None,
        height_mm: float | None = None,
        align: str | None = None,
        para_pr_id_ref: str | int | None = None,
        style_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        **extra_attrs: str,
    ) -> HwpxOxmlInlineObject:
        """Embed image data and place a picture object in a new paragraph."""

        binary_item_id_ref = self.add_image(image_data, image_format)

        resolved_width = width
        if resolved_width is None:
            resolved_width = _mm_to_hwp_units(width_mm) if width_mm is not None else 14400

        resolved_height = height
        if resolved_height is None:
            if height_mm is not None:
                resolved_height = _mm_to_hwp_units(height_mm)
            else:
                dimensions = _png_dimensions(image_data)
                if dimensions is not None:
                    source_width, source_height = dimensions
                    resolved_height = round(resolved_width * source_height / source_width)
                else:
                    resolved_height = resolved_width

        paragraph = self.add_paragraph(
            "",
            section=section,
            section_index=section_index,
            para_pr_id_ref=para_pr_id_ref,
            style_id_ref=style_id_ref,
            char_pr_id_ref=char_pr_id_ref,
            include_run=False,
            **extra_attrs,
        )
        return paragraph.add_picture(
            binary_item_id_ref,
            width=resolved_width,
            height=resolved_height,
            align=align,
            run_attributes=run_attributes,
            char_pr_id_ref=char_pr_id_ref,
        )

    def _iter_picture_images(
        self,
    ) -> Iterator[tuple[int, HwpxOxmlSection, Any, Any]]:
        for section_index, section in enumerate(self._root.sections):
            for picture in section.element.findall(f".//{_HP}pic"):
                image = picture.find(f"{_HC}img")
                if image is not None:
                    yield section_index, section, picture, image

    def picture_references(self) -> list[dict[str, Any]]:
        """Return body picture references in document order."""

        refs: list[dict[str, Any]] = []
        for picture_index, (section_index, _section, picture, image) in enumerate(self._iter_picture_images()):
            size = picture.find(f"{_HP}sz")
            refs.append(
                {
                    "picture_index": picture_index,
                    "section_index": section_index,
                    "binaryItemIDRef": image.get("binaryItemIDRef"),
                    "width": size.get("width") if size is not None else None,
                    "height": size.get("height") if size is not None else None,
                }
            )
        return refs

    def replace_picture(
        self,
        image_data: bytes,
        image_format: str,
        *,
        picture_index: int = 0,
        binary_item_id_ref: str | None = None,
        remove_orphaned: bool = True,
        item_id: str | None = None,
    ) -> dict[str, Any]:
        """Replace a body picture's image asset while preserving its geometry.

        The existing ``<hp:pic>`` element is left in place.  Only the child
        ``<hc:img>`` ``binaryItemIDRef`` is changed, so size, position, crop,
        rotation, and wrapping geometry remain untouched.
        """

        if picture_index < 0:
            raise IndexError("picture_index must be non-negative")

        selected: tuple[int, HwpxOxmlSection, Any, Any] | None = None
        matched_index = -1
        for current_index, picture in enumerate(self._iter_picture_images()):
            _section_index, _section, _picture_element, image = picture
            current_ref = (image.get("binaryItemIDRef") or "").strip()
            if binary_item_id_ref is not None and current_ref != str(binary_item_id_ref):
                continue
            matched_index += 1
            if matched_index == picture_index:
                selected = picture
                break

        if selected is None:
            if binary_item_id_ref is None:
                raise IndexError(f"picture_index {picture_index} is out of range")
            raise IndexError(
                f"picture_index {picture_index} for binaryItemIDRef "
                f"{binary_item_id_ref!r} is out of range"
            )

        section_index, section, _picture_element, image = selected
        old_ref = (image.get("binaryItemIDRef") or "").strip()
        new_ref = self.add_image(image_data, image_format, item_id=item_id)
        image.set("binaryItemIDRef", new_ref)
        section.mark_dirty()

        removed_old_image = False
        if remove_orphaned and old_ref and old_ref != new_ref:
            if not any(
                (other_image.get("binaryItemIDRef") or "").strip() == old_ref
                for _other_section_index, _other_section, _other_picture, other_image in self._iter_picture_images()
            ):
                removed_old_image = self.remove_image(old_ref)

        return {
            "picture_index": matched_index,
            "section_index": section_index,
            "old_binaryItemIDRef": old_ref,
            "new_binaryItemIDRef": new_ref,
            "removedOldImage": removed_old_image,
            "geometryPreserved": True,
        }

    def merge_table_cells(
        self,
        table: HwpxOxmlTable,
        cell_range: str,
    ) -> Any:
        """Merge a table cell range using spreadsheet notation such as ``A1:C1``."""

        return table.merge_cells(cell_range)

    def get_table_map(self) -> TableMapResult:
        """Return compact metadata for every table in document order."""

        from .tools.table_navigation import get_table_map

        return get_table_map(self)

    def find_cell_by_label(
        self,
        label_text: str,
        direction: str = "right",
    ) -> TableLabelSearchResult:
        """Return every label/target cell pair that matches *label_text*."""

        from .tools.table_navigation import find_cell_by_label

        return find_cell_by_label(self, label_text, direction=direction)

    def _find_field_end_position(
        self,
        runs: Sequence[Any],
        *,
        begin_run_index: int,
        begin_child_index: int,
        field_begin: Any,
    ) -> tuple[int, int, Any] | None:
        for run_index in range(begin_run_index, len(runs)):
            children = list(runs[run_index])
            start = begin_child_index + 1 if run_index == begin_run_index else 0
            for child_index in range(start, len(children)):
                child = children[child_index]
                if _local_name(child) != "ctrl":
                    continue
                for field_end in child.findall(f"{_HP}fieldEnd"):
                    if _field_end_matches(field_begin, field_end):
                        return run_index, child_index, field_end
        return None

    def _field_text_nodes(
        self,
        runs: Sequence[Any],
        *,
        begin_run_index: int,
        begin_child_index: int,
        end_run_index: int | None,
        end_child_index: int | None,
    ) -> list[Any]:
        nodes: list[Any] = []
        last_run = end_run_index if end_run_index is not None else begin_run_index
        for run_index in range(begin_run_index, last_run + 1):
            children = list(runs[run_index])
            start = begin_child_index + 1 if run_index == begin_run_index else 0
            stop = end_child_index if end_run_index == run_index and end_child_index is not None else len(children)
            for child in children[start:stop]:
                if _local_name(child) == "t":
                    nodes.append(child)
        return nodes

    def _form_field_payload(
        self,
        *,
        index: int,
        section_index: int,
        paragraph_index: int,
        paragraph_index_in_section: int,
        run_index: int,
        child_index: int,
        ctrl: Any,
        field_begin: Any,
        current_value: str,
        has_end: bool,
    ) -> dict[str, Any]:
        parameters = _field_parameters(field_begin)
        name = _first_attr(field_begin, _FORM_FIELD_NAME_ATTRS)
        if not name:
            name = _field_parameter_value(parameters, "fieldName", "fieldname", "field_name", "name", "title")
        prompt = _first_attr(field_begin, _FORM_FIELD_PROMPT_ATTRS)
        if not prompt:
            prompt = _field_parameter_value(parameters, *_FORM_FIELD_PARAM_NAMES)
        instruction = _field_parameter_value(parameters, "instruction", "guide", "help", "description", "desc")
        if not instruction:
            instruction = prompt
        return {
            "index": index,
            "field_id": _field_identifier(field_begin),
            "id": field_begin.get("id", ""),
            "fieldid": field_begin.get("fieldid", ""),
            "name": name,
            "prompt": prompt,
            "instruction": instruction,
            "current_value": current_value,
            "field_type": field_begin.get("type", ""),
            "control_type": ctrl.get("type", ""),
            "section_index": section_index,
            "paragraph_index": paragraph_index,
            "paragraph_index_in_section": paragraph_index_in_section,
            "run_index": run_index,
            "child_index": child_index,
            "has_end": has_end,
            "parameters": parameters,
        }

    def _iter_form_field_matches(self) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        paragraph_index = 0
        for section_index, section in enumerate(self.sections):
            for paragraph_index_in_section, paragraph in enumerate(section.paragraphs):
                runs = [child for child in paragraph.element if _local_name(child) == "run"]
                for run_index, run in enumerate(runs):
                    children = list(run)
                    for child_index, child in enumerate(children):
                        if _local_name(child) != "ctrl":
                            continue
                        for field_begin in child.findall(f"{_HP}fieldBegin"):
                            if not _is_form_field_begin(child, field_begin):
                                continue
                            end_position = self._find_field_end_position(
                                runs,
                                begin_run_index=run_index,
                                begin_child_index=child_index,
                                field_begin=field_begin,
                            )
                            end_run_index: int | None = None
                            end_child_index: int | None = None
                            if end_position is not None:
                                end_run_index, end_child_index, _field_end = end_position
                            text_nodes = self._field_text_nodes(
                                runs,
                                begin_run_index=run_index,
                                begin_child_index=child_index,
                                end_run_index=end_run_index,
                                end_child_index=end_child_index,
                            )
                            current_value = "".join("".join(node.itertext()) for node in text_nodes)
                            payload = self._form_field_payload(
                                index=len(matches),
                                section_index=section_index,
                                paragraph_index=paragraph_index,
                                paragraph_index_in_section=paragraph_index_in_section,
                                run_index=run_index,
                                child_index=child_index,
                                ctrl=child,
                                field_begin=field_begin,
                                current_value=current_value,
                                has_end=end_position is not None,
                            )
                            payload["_paragraph"] = paragraph
                            payload["_runs"] = runs
                            payload["_begin_run_index"] = run_index
                            payload["_begin_child_index"] = child_index
                            payload["_end_run_index"] = end_run_index
                            payload["_end_child_index"] = end_child_index
                            payload["_text_nodes"] = text_nodes
                            matches.append(payload)
                paragraph_index += 1
        return matches

    def list_form_fields(self) -> list[dict[str, Any]]:
        """Return native form/click-here fields in document order.

        The result intentionally excludes memo and hyperlink fields because
        those are annotation/navigation mechanisms rather than fillable form
        slots.
        """

        return [
            {key: value for key, value in match.items() if not key.startswith("_")}
            for match in self._iter_form_field_matches()
        ]

    def _select_form_field(
        self,
        matches: Sequence[dict[str, Any]],
        *,
        field_index: int | None,
        field_id: str | None,
        name: str | None,
    ) -> dict[str, Any]:
        selectors = [field_index is not None, bool(field_id), bool(name)]
        if selectors.count(True) != 1:
            raise ValueError("provide exactly one of field_index, field_id, or name")
        if field_index is not None:
            for match in matches:
                if match["index"] == field_index:
                    return match
            raise ValueError(f"form field index not found: {field_index}")
        if field_id:
            wanted = field_id.strip()
            candidates = [
                match
                for match in matches
                if wanted in {match.get("field_id"), match.get("id"), match.get("fieldid")}
            ]
        else:
            wanted_name = (name or "").strip().casefold()
            candidates = [
                match
                for match in matches
                if wanted_name
                and wanted_name
                in {
                    str(match.get("name", "")).strip().casefold(),
                    str(match.get("prompt", "")).strip().casefold(),
                    str(match.get("instruction", "")).strip().casefold(),
                }
            ]
        if not candidates:
            selector = f"field_id={field_id!r}" if field_id else f"name={name!r}"
            raise ValueError(f"form field not found for {selector}")
        if len(candidates) > 1:
            labels = [candidate.get("name") or candidate.get("field_id") for candidate in candidates]
            raise ValueError(f"form field selector is ambiguous: {labels}")
        return candidates[0]

    def _field_run_style_snapshot(
        self,
        runs: Sequence[Any],
        *,
        begin_run_index: int,
        end_run_index: int | None,
    ) -> list[str | None]:
        last_run = end_run_index if end_run_index is not None else begin_run_index
        return [runs[index].get("charPrIDRef") for index in range(begin_run_index, last_run + 1)]

    def _insert_form_field_text_run(
        self,
        match: dict[str, Any],
        value: str,
    ) -> None:
        paragraph = match["_paragraph"]
        runs: list[Any] = match["_runs"]
        begin_run_index = int(match["_begin_run_index"])
        end_run_index = match.get("_end_run_index")
        begin_run = runs[begin_run_index]
        char_ref = begin_run.get("charPrIDRef") or paragraph.char_pr_id_ref or "0"
        run = paragraph.element.makeelement(f"{_HP}run", {"charPrIDRef": str(char_ref)})
        text_node = run.makeelement(f"{_HP}t", {})
        text_node.text = _sanitize_field_text(value)
        run.append(text_node)
        if end_run_index is None:
            paragraph.element.insert(begin_run_index + 1, run)
        else:
            paragraph.element.insert(int(end_run_index), run)

    def fill_form_field(
        self,
        value: str,
        *,
        field_index: int | None = None,
        field_id: str | None = None,
        name: str | None = None,
        fit_policy: "FitPolicy | None" = None,
        box_width: int | None = None,
        font_pt: float | None = None,
    ) -> dict[str, Any]:
        """Fill a native form/click-here field while preserving surrounding runs.

        When *fit_policy* and *box_width* (the field's usable width, in HWPUNIT)
        are supplied, the value is run through the FormFit engine (plan §2 C): it
        is measured against the box and may be shrunk/​truncated, the inserted run
        is re-pointed at a smaller ``charPr`` for a real (oracle-visible) shrink,
        and the response carries a ``fit`` verdict with ``ok`` propagated from it.
        Without a box width a native field has no reliable geometry, so the fit is
        reported low-confidence and never hard-fails (measurement honesty).
        """

        matches = self._iter_form_field_matches()
        match = self._select_form_field(
            matches,
            field_index=field_index,
            field_id=field_id,
            name=name,
        )
        paragraph = match["_paragraph"]
        runs = match["_runs"]
        before_value = str(match.get("current_value", ""))
        before_style = self._field_run_style_snapshot(
            runs,
            begin_run_index=int(match["_begin_run_index"]),
            end_run_index=match.get("_end_run_index"),
        )

        fit_result = None
        write_value = str(value)
        if fit_policy is not None:
            fit_result = self._measure_form_field_fit(
                str(value), match, fit_policy, box_width, font_pt
            )
            write_value = fit_result.applied_value

        text_nodes: list[Any] = match.get("_text_nodes", [])
        sanitized = _sanitize_field_text(write_value)
        if text_nodes:
            primary = text_nodes[0]
            primary.text = sanitized
            for child in list(primary):
                child.tail = ""
            for node in text_nodes[1:]:
                node.text = ""
                for child in list(node):
                    child.tail = ""
        else:
            self._insert_form_field_text_run(match, sanitized)

        if fit_result is not None:
            self._apply_form_field_fit_style(match, fit_result)

        _clear_form_field_layout_cache(paragraph.element)
        paragraph.section.mark_dirty()
        updated = self._iter_form_field_matches()[int(match["index"])]
        after_style = self._field_run_style_snapshot(
            updated["_runs"],
            begin_run_index=int(updated["_begin_run_index"]),
            end_run_index=updated.get("_end_run_index"),
        )
        field = {key: value for key, value in updated.items() if not key.startswith("_")}
        response = {
            "ok": True if fit_result is None else fit_result.ok,
            "field": field,
            "before_value": before_value,
            "after_value": str(field.get("current_value", "")),
            "style_before": before_style,
            "style_after": after_style,
            "style_preserved": before_style == after_style[: len(before_style)],
        }
        if fit_result is not None:
            response["fit"] = fit_result.to_dict()
            if not fit_result.ok:
                response["suggestedRetry"] = fit_result.suggested_retry()
        return response

    def _measure_form_field_fit(
        self,
        value: str,
        match: Mapping[str, Any],
        fit_policy: "FitPolicy",
        box_width: int | None,
        font_pt: float | None,
    ) -> "FitResult":
        """Run the FormFit engine for a native field (plan §2 C)."""

        from hwpx.form_fit import DEFAULT_SAFETY, FitEngine, FitResult, SlotMetrics

        runs = match["_runs"]
        begin_index = int(match["_begin_run_index"])
        begin_ref = None
        if 0 <= begin_index < len(runs):
            begin_ref = runs[begin_index].get("charPrIDRef")
        if begin_ref is None:
            begin_ref = match["_paragraph"].char_pr_id_ref or "0"
        resolved_pt = font_pt if font_pt is not None else self._font_pt_for_ref(begin_ref)
        field_id = str(match.get("name") or match.get("field_id") or match.get("index"))

        if not box_width:
            # No reliable geometry: measure-free, low-confidence, never a hard fail.
            return FitResult(
                ok=True,
                value=value,
                applied_value=value,
                font_pt=resolved_pt,
                confidence="low",
                warnings=[
                    "native field has no box_width; fit is unverified — supply "
                    "box_width or rely on the render oracle"
                ],
                field_id=field_id,
            )

        slot = SlotMetrics(
            available_width=float(box_width) * DEFAULT_SAFETY,
            font_pt=resolved_pt,
            max_lines=fit_policy.effective_max_lines,
        )
        return FitEngine().fit(value, slot, fit_policy, field_id=field_id)

    def _font_pt_for_ref(self, char_pr_id_ref: object) -> float:
        style = self.char_property(char_pr_id_ref)
        if style is not None:
            height = style.attributes.get("height")
            if height:
                try:
                    return int(height) / 100.0
                except (TypeError, ValueError):  # pragma: no cover - defensive
                    pass
        return 10.0

    def _apply_form_field_fit_style(
        self, match: Mapping[str, Any], fit_result: "FitResult"
    ) -> None:
        """Materialise a font shrink on the field's primary run (real change)."""

        new_pt = fit_result.applied_style_changes.get("font_pt")
        if not new_pt:
            return
        text_nodes: list[Any] = match.get("_text_nodes", [])
        run = None
        if text_nodes and hasattr(text_nodes[0], "getparent"):
            run = text_nodes[0].getparent()
        if run is None:
            return
        base_ref = run.get("charPrIDRef")
        try:
            new_ref = self.ensure_run_style(size=float(new_pt), base_char_pr_id=base_ref)
        except Exception:  # pragma: no cover - defensive: never break the fill
            fit_result.warnings.append("font shrink could not be materialised")
            return
        run.set("charPrIDRef", str(new_ref))

    def fill_by_path(
        self,
        mappings: Mapping[str, str],
    ) -> TableFillResult:
        """Fill table cells using ``label > direction > ...`` navigation paths."""

        from .tools.table_navigation import fill_by_path

        return fill_by_path(self, mappings)

    def add_shape(
        self,
        shape_type: str,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        attributes: dict[str, str] | None = None,
        para_pr_id_ref: str | int | None = None,
        style_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        **extra_attrs: str,
    ) -> HwpxOxmlInlineObject:
        """Insert an inline shape into a new paragraph."""

        paragraph = self.add_paragraph(
            "",
            section=section,
            section_index=section_index,
            para_pr_id_ref=para_pr_id_ref,
            style_id_ref=style_id_ref,
            char_pr_id_ref=char_pr_id_ref,
            include_run=False,
            **extra_attrs,
        )
        return paragraph.add_shape(
            shape_type,
            attributes=attributes,
            run_attributes=run_attributes,
            char_pr_id_ref=char_pr_id_ref,
        )

    def add_control(
        self,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        attributes: dict[str, str] | None = None,
        control_type: str | None = None,
        para_pr_id_ref: str | int | None = None,
        style_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        **extra_attrs: str,
    ) -> HwpxOxmlInlineObject:
        """Insert a control inline object into a new paragraph."""

        paragraph = self.add_paragraph(
            "",
            section=section,
            section_index=section_index,
            para_pr_id_ref=para_pr_id_ref,
            style_id_ref=style_id_ref,
            char_pr_id_ref=char_pr_id_ref,
            include_run=False,
            **extra_attrs,
        )
        return paragraph.add_control(
            attributes=attributes,
            control_type=control_type,
            run_attributes=run_attributes,
            char_pr_id_ref=char_pr_id_ref,
        )

    # ------------------------------------------------------------------
    # Footnote / Endnote helpers
    # ------------------------------------------------------------------

    def add_footnote(
        self,
        text: str,
        paragraph: HwpxOxmlParagraph | None = None,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlNote:
        """Add a footnote to an existing paragraph, or create a new one.

        When *paragraph* is ``None`` a new paragraph is appended to the given
        (or last) section.
        """

        if paragraph is None:
            paragraph = self.add_paragraph(
                "",
                section=section,
                section_index=section_index,
                include_run=False,
            )
        return paragraph.add_footnote(text, char_pr_id_ref=char_pr_id_ref)

    def add_endnote(
        self,
        text: str,
        paragraph: HwpxOxmlParagraph | None = None,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlNote:
        """Add an endnote to an existing paragraph, or create a new one."""

        if paragraph is None:
            paragraph = self.add_paragraph(
                "",
                section=section,
                section_index=section_index,
                include_run=False,
            )
        return paragraph.add_endnote(text, char_pr_id_ref=char_pr_id_ref)

    # ------------------------------------------------------------------
    # Drawing shapes
    # ------------------------------------------------------------------

    def add_line(
        self,
        start_x: int = 0,
        start_y: int = 0,
        end_x: int = 14400,
        end_y: int = 0,
        *,
        line_color: str = "#000000",
        line_width: str = "283",
        treat_as_char: bool = True,
        paragraph: HwpxOxmlParagraph | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> HwpxOxmlShape:
        """Insert a line drawing shape.

        Coordinates are in HWPUNIT (7200 per inch).
        """
        if paragraph is None:
            paragraph = self.add_paragraph(
                "", section=section, section_index=section_index,
                include_run=False,
            )
        return paragraph.add_line(
            start_x, start_y, end_x, end_y,
            line_color=line_color, line_width=line_width,
            treat_as_char=treat_as_char,
        )

    def add_rectangle(
        self,
        width: int = 14400,
        height: int = 7200,
        *,
        ratio: int = 0,
        line_color: str = "#000000",
        line_width: str = "283",
        fill_color: str | None = None,
        treat_as_char: bool = True,
        paragraph: HwpxOxmlParagraph | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> HwpxOxmlShape:
        """Insert a rectangle drawing shape.

        Dimensions are in HWPUNIT.  *ratio* controls corner roundness
        (0 = sharp, 50 = semicircle).
        """
        if paragraph is None:
            paragraph = self.add_paragraph(
                "", section=section, section_index=section_index,
                include_run=False,
            )
        return paragraph.add_rectangle(
            width, height, ratio=ratio,
            line_color=line_color, line_width=line_width,
            fill_color=fill_color, treat_as_char=treat_as_char,
        )

    def add_ellipse(
        self,
        width: int = 14400,
        height: int = 7200,
        *,
        line_color: str = "#000000",
        line_width: str = "283",
        fill_color: str | None = None,
        treat_as_char: bool = True,
        paragraph: HwpxOxmlParagraph | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> HwpxOxmlShape:
        """Insert an ellipse drawing shape.

        Dimensions are in HWPUNIT.
        """
        if paragraph is None:
            paragraph = self.add_paragraph(
                "", section=section, section_index=section_index,
                include_run=False,
            )
        return paragraph.add_ellipse(
            width, height,
            line_color=line_color, line_width=line_width,
            fill_color=fill_color, treat_as_char=treat_as_char,
        )

    # ------------------------------------------------------------------
    # Existing-document formatting
    # ------------------------------------------------------------------

    def _resolve_paragraph_targets(
        self,
        *,
        paragraph_index: int | None = None,
        paragraph_indexes: Sequence[int] | None = None,
    ) -> list[tuple[int, HwpxOxmlParagraph]]:
        paragraphs = self.paragraphs
        if not paragraphs:
            raise ValueError("document does not contain any paragraphs")
        if paragraph_index is not None and paragraph_indexes is not None:
            raise ValueError("use either paragraph_index or paragraph_indexes, not both")

        if paragraph_indexes is None:
            indexes = list(range(len(paragraphs))) if paragraph_index is None else [paragraph_index]
        else:
            indexes = [int(index) for index in paragraph_indexes]
            if not indexes:
                raise ValueError("paragraph_indexes must not be empty")

        targets: list[tuple[int, HwpxOxmlParagraph]] = []
        for index in indexes:
            if index < 0 or index >= len(paragraphs):
                raise IndexError("paragraph index out of range")
            targets.append((index, paragraphs[index]))
        return targets

    def set_paragraph_format(
        self,
        *,
        paragraph_index: int | None = None,
        paragraph_indexes: Sequence[int] | None = None,
        alignment: str | None = None,
        line_spacing_percent: int | float | None = None,
        indent_left_mm: float | None = None,
        indent_right_mm: float | None = None,
        first_line_indent_mm: float | None = None,
        spacing_before_pt: float | None = None,
        spacing_after_pt: float | None = None,
        outline_level: int | None = None,
        keep_with_next: bool | None = None,
        keep_lines: bool | None = None,
        page_break_before: bool | None = None,
        bottom_border: bool = False,
        border_color: str = "#BFBFBF",
        border_width: str = "0.12 mm",
    ) -> dict[str, Any]:
        """Apply paragraph-level formatting using human units.

        Millimetre inputs are converted to HWP units; paragraph spacing uses
        points; line spacing is stored as a percent value. ``keep_with_next`` /
        ``keep_lines`` / ``page_break_before`` set the paragraph's keep-together
        (``<hh:breakSetting>``) flags via a freshly minted paraPr.
        """

        if not self._root.headers:
            raise ValueError("document does not contain any headers")
        header = self._root.headers[0]

        if line_spacing_percent is not None and float(line_spacing_percent) <= 0:
            raise ValueError("line_spacing_percent must be positive")

        margins: dict[str, int] = {}
        if first_line_indent_mm is not None:
            margins["intent"] = _mm_to_hwp_units(float(first_line_indent_mm))
        if indent_left_mm is not None:
            margins["left"] = _mm_to_hwp_units(float(indent_left_mm))
        if indent_right_mm is not None:
            margins["right"] = _mm_to_hwp_units(float(indent_right_mm))
        if spacing_before_pt is not None:
            margins["prev"] = _pt_to_hwp_units(float(spacing_before_pt))
        if spacing_after_pt is not None:
            margins["next"] = _pt_to_hwp_units(float(spacing_after_pt))

        heading: dict[str, str | int] | None = None
        if outline_level is not None:
            level = int(outline_level)
            if level <= 0:
                heading = {"type": "NONE", "idRef": "0", "level": "0"}
            elif level <= 10:
                heading = {"type": "OUTLINE", "idRef": "0", "level": str(level - 1)}
            else:
                raise ValueError("outline_level must be between 0 and 10")

        break_setting: dict[str, bool] = {}
        if keep_with_next is not None:
            break_setting["keep_with_next"] = bool(keep_with_next)
        if keep_lines is not None:
            break_setting["keep_lines"] = bool(keep_lines)
        if page_break_before is not None:
            break_setting["page_break_before"] = bool(page_break_before)

        if (
            alignment is None
            and line_spacing_percent is None
            and not margins
            and heading is None
            and not bottom_border
            and not break_setting
        ):
            raise ValueError("at least one paragraph formatting option is required")

        border: dict[str, str] | None = None
        if bottom_border:
            border_fill_id = header.ensure_border_fill(
                border_color=border_color,
                border_width=border_width,
                active_borders=("bottom",),
            )
            border = {
                "borderFillIDRef": border_fill_id,
                "offsetLeft": "0",
                "offsetRight": "0",
                "offsetTop": "0",
                "offsetBottom": "0",
                "connect": "0",
                "ignoreMargin": "0",
            }

        targets = self._resolve_paragraph_targets(
            paragraph_index=paragraph_index,
            paragraph_indexes=paragraph_indexes,
        )
        formatted: list[dict[str, Any]] = []
        for index, paragraph in targets:
            para_pr_id = header.ensure_paragraph_format(
                base_para_pr_id=paragraph.para_pr_id_ref,
                alignment=alignment,
                line_spacing_percent=line_spacing_percent,
                margins=margins,
                heading=heading,
                border=border,
                break_setting=break_setting or None,
            )
            paragraph.para_pr_id_ref = para_pr_id
            formatted.append({"paragraph_index": index, "paraPrIDRef": para_pr_id})

        return {
            "formatted": len(formatted),
            "paragraphs": formatted,
            "units": {
                "indent": "mm",
                "paragraphSpacing": "pt",
                "lineSpacing": "%",
            },
        }

    def set_list_format(
        self,
        *,
        paragraph_index: int | None = None,
        paragraph_indexes: Sequence[int] | None = None,
        kind: str = "bullet",
        level: int = 1,
        bullet_char: str | None = None,
        number_format: str | None = None,
        start: int | None = None,
    ) -> dict[str, Any]:
        """Apply bullet or numbered-list paragraph properties to paragraphs."""

        if level < 1:
            raise ValueError("level must be 1 or greater")
        if not self._root.headers:
            raise ValueError("document does not contain any headers")

        level_specs: list[dict[str, str]] = [{} for _ in range(level)]
        if bullet_char:
            level_specs[level - 1]["char"] = str(bullet_char)
        if number_format:
            level_specs[level - 1]["format"] = str(number_format).upper()
        if start is not None:
            level_specs[level - 1]["start"] = str(max(1, int(start)))

        refs = self._root.ensure_numbering(kind=kind, levels=level_specs)
        list_para_pr_id = refs[level - 1]
        header = self._root.headers[0]
        list_para_pr = header.element.find(f".//{_HH}paraPr[@id='{list_para_pr_id}']")
        heading_element = list_para_pr.find(f"{_HH}heading") if list_para_pr is not None else None
        if heading_element is None:
            raise RuntimeError("failed to create list paragraph property")
        heading = {
            "type": heading_element.get("type", "NONE"),
            "idRef": heading_element.get("idRef", "0"),
            "level": heading_element.get("level", str(level - 1)),
        }
        targets = self._resolve_paragraph_targets(
            paragraph_index=paragraph_index,
            paragraph_indexes=paragraph_indexes,
        )

        formatted: list[dict[str, Any]] = []
        for index, paragraph in targets:
            para_pr_id = header.ensure_paragraph_format(
                base_para_pr_id=paragraph.para_pr_id_ref,
                heading=heading,
            )
            paragraph.para_pr_id_ref = para_pr_id
            formatted.append({"paragraph_index": index, "paraPrIDRef": para_pr_id})

        return {
            "formatted": len(formatted),
            "paragraphs": formatted,
            "kind": kind,
            "level": level,
            "paraPrIDRef": formatted[0]["paraPrIDRef"] if formatted else list_para_pr_id,
        }

    def set_page_setup(
        self,
        *,
        paper_size: str | None = None,
        width_mm: float | None = None,
        height_mm: float | None = None,
        orientation: str | None = None,
        margins_mm: Mapping[str, float] | None = None,
        margin_left_mm: float | None = None,
        margin_right_mm: float | None = None,
        margin_top_mm: float | None = None,
        margin_bottom_mm: float | None = None,
        header_margin_mm: float | None = None,
        footer_margin_mm: float | None = None,
        gutter_mm: float | None = None,
        columns: int | None = None,
        column_gap_mm: float | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> dict[str, Any]:
        """Set page size, margins, orientation, and optional columns in human units."""

        normalized_orientation = _normalize_page_orientation(orientation)
        target_width_mm = width_mm
        target_height_mm = height_mm
        if paper_size:
            paper_key = paper_size.strip().upper()
            if paper_key not in _PAPER_SIZES_MM:
                raise ValueError(f"unsupported paper_size: {paper_size}")
            paper_width, paper_height = _PAPER_SIZES_MM[paper_key]
            target_width_mm = paper_width if target_width_mm is None else target_width_mm
            target_height_mm = paper_height if target_height_mm is None else target_height_mm

        if target_width_mm is not None and target_height_mm is not None:
            if normalized_orientation == "WIDELY" and target_width_mm < target_height_mm:
                target_width_mm, target_height_mm = target_height_mm, target_width_mm
            elif normalized_orientation == "PORTRAIT" and target_width_mm > target_height_mm:
                target_width_mm, target_height_mm = target_height_mm, target_width_mm

        width = _mm_to_hwp_units(float(target_width_mm)) if target_width_mm is not None else None
        height = _mm_to_hwp_units(float(target_height_mm)) if target_height_mm is not None else None
        if width is not None or height is not None or normalized_orientation is not None:
            self.set_page_size(
                width=width,
                height=height,
                orientation=normalized_orientation,
                section=section,
                section_index=section_index,
            )

        margin_source = dict(margins_mm or {})
        margin_values = {
            "left": margin_left_mm if margin_left_mm is not None else margin_source.get("left"),
            "right": margin_right_mm if margin_right_mm is not None else margin_source.get("right"),
            "top": margin_top_mm if margin_top_mm is not None else margin_source.get("top"),
            "bottom": margin_bottom_mm if margin_bottom_mm is not None else margin_source.get("bottom"),
            "header": header_margin_mm if header_margin_mm is not None else margin_source.get("header"),
            "footer": footer_margin_mm if footer_margin_mm is not None else margin_source.get("footer"),
            "gutter": gutter_mm if gutter_mm is not None else margin_source.get("gutter"),
        }
        hwp_margins = {
            name: _mm_to_hwp_units(float(value))
            for name, value in margin_values.items()
            if value is not None
        }
        if hwp_margins:
            self.set_page_margins(
                section=section,
                section_index=section_index,
                **hwp_margins,
            )

        column_result: dict[str, Any] | None = None
        if columns is not None:
            col_count = int(columns)
            if col_count < 1:
                raise ValueError("columns must be 1 or greater")
            gap = _mm_to_hwp_units(float(column_gap_mm or 0))
            self.set_columns(
                col_count=col_count,
                same_gap=gap,
                section=section,
                section_index=section_index,
            )
            column_result = {"count": col_count, "gap": gap}

        return {
            "pageSize": {"width": width, "height": height, "orientation": normalized_orientation},
            "margins": hwp_margins,
            "columns": column_result,
            "units": {"page": "mm", "margins": "mm", "columnsGap": "mm"},
        }

    # ------------------------------------------------------------------
    # Column layout
    # ------------------------------------------------------------------

    def set_columns(
        self,
        col_count: int = 2,
        *,
        col_type: str = "NEWSPAPER",
        layout: str = "LEFT",
        same_size: bool = True,
        same_gap: int = 1200,
        column_widths: "Sequence[tuple[int, int]] | None" = None,
        separator_type: str | None = None,
        separator_width: str | None = None,
        separator_color: str | None = None,
        paragraph: HwpxOxmlParagraph | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert a column definition control.

        This adds a ``<hp:ctrl><hp:colPr>`` element to the specified paragraph.
        Text that follows will be laid out in the specified number of columns.

        Args:
            col_count: Number of columns (1–255).
            col_type: ``NEWSPAPER``, ``BALANCED_NEWSPAPER``, or ``PARALLEL``.
            same_gap: Gap in HWPUNIT (7200 = 1 inch).
            separator_type: Optional column separator line type (e.g. ``SOLID``).
        """
        if paragraph is None:
            paragraph = self.add_paragraph(
                "", section=section, section_index=section_index,
                include_run=False,
            )
        return paragraph.add_column_definition(
            col_count,
            col_type=col_type,
            layout=layout,
            same_size=same_size,
            same_gap=same_gap,
            column_widths=column_widths,
            separator_type=separator_type,
            separator_width=separator_width,
            separator_color=separator_color,
        )

    # ------------------------------------------------------------------
    # Bookmarks and hyperlinks
    # ------------------------------------------------------------------

    def add_bookmark(
        self,
        name: str,
        *,
        paragraph: HwpxOxmlParagraph | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert a bookmark marker in the document.

        Returns the ``<hp:ctrl>`` wrapper element.
        """
        if paragraph is None:
            paragraph = self.add_paragraph(
                "", section=section, section_index=section_index,
                include_run=False,
            )
        return paragraph.add_bookmark(name)

    def add_hyperlink(
        self,
        url: str,
        display_text: str,
        *,
        paragraph: HwpxOxmlParagraph | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert a hyperlink (fieldBegin + text + fieldEnd).

        Returns the ``<hp:ctrl>`` wrapper containing the ``<hp:fieldBegin>``.
        """
        if paragraph is None:
            paragraph = self.add_paragraph(
                "", section=section, section_index=section_index,
                include_run=False,
            )
        return paragraph.add_hyperlink(url, display_text)

    def _resolve_section(
        self,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> HwpxOxmlSection:
        target_section = section
        if target_section is None and section_index is not None:
            target_section = self._root.sections[section_index]
        if target_section is None:
            if not self._root.sections:
                raise ValueError("document does not contain any sections")
            target_section = self._root.sections[-1]
        return target_section

    def set_page_size(
        self,
        *,
        width: int | None = None,
        height: int | None = None,
        orientation: str | None = None,
        gutter_type: str | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> None:
        """Set page dimensions on the requested section through the public facade."""

        target_section = self._resolve_section(section=section, section_index=section_index)
        target_section.properties.set_page_size(
            width=width,
            height=height,
            orientation=orientation,
            gutter_type=gutter_type,
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
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> None:
        """Set page margins on the requested section through the public facade."""

        target_section = self._resolve_section(section=section, section_index=section_index)
        target_section.properties.set_page_margins(
            left=left,
            right=right,
            top=top,
            bottom=bottom,
            header=header,
            footer=footer,
            gutter=gutter,
        )

    def set_header_text(
        self,
        text: str,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        page_type: str = "BOTH",
    ) -> HwpxOxmlSectionHeaderFooter:
        """Ensure the requested section contains a header for *page_type* and set its text."""

        target_section = self._resolve_section(section=section, section_index=section_index)
        return target_section.properties.set_header_text(text, page_type=page_type)

    def set_footer_text(
        self,
        text: str,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        page_type: str = "BOTH",
    ) -> HwpxOxmlSectionHeaderFooter:
        """Ensure the requested section contains a footer for *page_type* and set its text."""

        target_section = self._resolve_section(section=section, section_index=section_index)
        return target_section.properties.set_footer_text(text, page_type=page_type)

    def set_header_content(
        self,
        content: Sequence[Mapping[str, Any]],
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        page_type: str = "BOTH",
    ) -> HwpxOxmlSectionHeaderFooter:
        """Ensure the requested section contains a rich header for *page_type*."""

        target_section = self._resolve_section(section=section, section_index=section_index)
        return target_section.properties.set_header_content(content, page_type=page_type)

    def set_footer_content(
        self,
        content: Sequence[Mapping[str, Any]],
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        page_type: str = "BOTH",
    ) -> HwpxOxmlSectionHeaderFooter:
        """Ensure the requested section contains a rich footer for *page_type*."""

        target_section = self._resolve_section(section=section, section_index=section_index)
        return target_section.properties.set_footer_content(content, page_type=page_type)

    def set_header_footer(
        self,
        *,
        kind: str,
        text: str | None = None,
        content: Sequence[Mapping[str, Any]] | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        page_type: str = "BOTH",
    ) -> HwpxOxmlSectionHeaderFooter:
        """Set a header or footer using plain text or rich content specs."""

        normalized = kind.strip().lower()
        if normalized not in {"header", "footer"}:
            raise ValueError("kind must be 'header' or 'footer'")
        if content is not None and text is not None:
            raise ValueError("use either text or content, not both")
        if content is not None:
            if normalized == "header":
                return self.set_header_content(
                    content,
                    section=section,
                    section_index=section_index,
                    page_type=page_type,
                )
            return self.set_footer_content(
                content,
                section=section,
                section_index=section_index,
                page_type=page_type,
            )

        value = "" if text is None else text
        if normalized == "header":
            return self.set_header_text(
                value,
                section=section,
                section_index=section_index,
                page_type=page_type,
            )
        return self.set_footer_text(
            value,
            section=section,
            section_index=section_index,
            page_type=page_type,
        )

    def set_page_number(
        self,
        *,
        target: str = "footer",
        page_type: str = "BOTH",
        format: str = "page",
        align: str = "CENTER",
        position: str = "BOTTOM_CENTER",
        prefix: str = "",
        suffix: str = "",
        format_type: str | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> HwpxOxmlSectionHeaderFooter:
        """Replace header/footer content with an automatic page-number field."""

        children: list[dict[str, Any]] = []
        if prefix:
            children.append({"type": "run", "text": prefix})
        children.append(
            {
                "type": "page_number",
                "page_number": format,
                "position": position,
                "formatType": format_type,
            }
        )
        if suffix:
            children.append({"type": "run", "text": suffix})

        return self.set_header_footer(
            kind=target,
            content=[{"align": align, "children": children}],
            section=section,
            section_index=section_index,
            page_type=page_type,
        )

    def remove_header(
        self,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        page_type: str = "BOTH",
    ) -> None:
        """Remove the header linked to *page_type* from the requested section if present."""

        target_section = section
        if target_section is None and section_index is not None:
            target_section = self._root.sections[section_index]
        if target_section is None:
            if not self._root.sections:
                return
            target_section = self._root.sections[-1]
        target_section.properties.remove_header(page_type=page_type)

    def remove_footer(
        self,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        page_type: str = "BOTH",
    ) -> None:
        """Remove the footer linked to *page_type* from the requested section if present."""

        target_section = section
        if target_section is None and section_index is not None:
            target_section = self._root.sections[section_index]
        if target_section is None:
            if not self._root.sections:
                return
            target_section = self._root.sections[-1]
        target_section.properties.remove_footer(page_type=page_type)

    # ------------------------------------------------------------------
    # BinData / Image management
    # ------------------------------------------------------------------

    _FORMAT_TO_MEDIA_TYPE: dict[str, str] = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "bmp": "image/bmp",
        "tiff": "image/tiff",
        "tif": "image/tiff",
        "svg": "image/svg+xml",
    }

    def add_image(
        self,
        image_data: bytes,
        image_format: str,
        *,
        item_id: str | None = None,
    ) -> str:
        """Embed an image file and return the manifest item id.

        Args:
            image_data: Raw image bytes.
            image_format: Image format extension (``jpg``, ``png``, …).
            item_id: Optional explicit manifest item id.  When omitted an
                     auto-generated ``BIN####`` id is used.

        Returns:
            The manifest item id that can be passed to
            ``binaryItemIDRef`` when constructing a ``<hp:pic>`` element.
        """

        fmt = image_format.lower().lstrip(".")
        media_type = self._FORMAT_TO_MEDIA_TYPE.get(fmt, f"image/{fmt}")

        existing_ids = self._existing_image_item_ids()

        # Determine a unique item id
        if item_id is None:
            n = 1
            while True:
                item_id = f"BIN{n:04d}"
                if item_id not in existing_ids:
                    break
                n += 1
        elif item_id in existing_ids:
            raise ValueError(f"image item_id {item_id!r} already exists")

        # File path inside the ZIP
        bin_data_name = f"{item_id}.{fmt}"
        bin_data_path = f"BinData/{bin_data_name}"

        # 1) Write image bytes into the package
        self._package.write(bin_data_path, image_data)

        # 2) Register in manifest. ``isEmbeded="1"`` (OWPML's single-d spelling) marks
        #    the BinData image as embedded — real Hancom drops the picture without it.
        self._package.add_manifest_item(
            item_id, bin_data_path, media_type, extra_attrs={"isEmbeded": "1"}
        )

        # 3) Register in header binDataList
        header = self._root.headers[0] if self._root.headers else None
        if header is not None:
            header.add_bin_item(
                item_type="Embedding",
                bin_data_id=bin_data_name,
                format=fmt,
            )

        return item_id

    def _existing_image_item_ids(self) -> set[str]:
        existing_ids: set[str] = set()
        header = self._root.headers[0] if self._root.headers else None
        if header is not None:
            for item in header.list_bin_items():
                stem = _bin_data_stem(item.get("BinData"))
                if stem:
                    existing_ids.add(stem)

        for item in self._package._manifest_items():
            href = str(item.get("href", "")).strip()
            media_type = str(item.get("media-type", "")).strip().lower()
            href_path = PurePosixPath(href)
            if (
                media_type.startswith("image/")
                or (len(href_path.parts) >= 2 and href_path.parts[0] == "BinData")
            ):
                item_id = str(item.get("id", "")).strip()
                if item_id:
                    existing_ids.add(item_id)
                stem = _bin_data_stem(href)
                if stem:
                    existing_ids.add(stem)

        for part_name in self._package.part_names():
            path = PurePosixPath(str(part_name))
            if len(path.parts) >= 2 and path.parts[0] == "BinData" and path.stem:
                existing_ids.add(path.stem)
        return existing_ids

    def list_images(self) -> list[dict[str, str]]:
        """Return metadata dicts for all embedded binary data items.

        Each dict contains the ``<hh:binItem>`` attributes (``id``, ``Type``,
        ``BinData``, ``Format``, …).
        """

        header = self._root.headers[0] if self._root.headers else None
        if header is None:
            return []
        return header.list_bin_items()

    def remove_image(self, item_id: str) -> bool:
        """Remove an embedded image by its manifest item id.

        This removes the binary data from the ZIP, the manifest entry, and
        the header binItem entry.

        Returns:
            ``True`` if any component was removed.
        """

        removed = False
        header = self._root.headers[0] if self._root.headers else None

        # Find file path and binItem numeric id from header metadata
        bin_data_path: str | None = None
        bin_item_numeric_id: str | None = None
        if header is not None:
            for bi in header.list_bin_items():
                bin_data_val = bi.get("BinData", "")
                # Match by data file name prefix (e.g. "BIN0001" matches "BIN0001.jpg")
                if bin_data_val.startswith(item_id):
                    bin_item_numeric_id = bi.get("id")
                    if bin_data_val:
                        bin_data_path = f"BinData/{bin_data_val}"
                    break

        # Also try manifest-based lookup for the file path
        if bin_data_path is None:
            manifest_el = self._package._manifest_element()
            if manifest_el is not None:
                ns = {"opf": "http://www.idpf.org/2007/opf/"}
                for it in manifest_el.findall("opf:item", ns):
                    if it.get("id") == item_id:
                        href = it.get("href", "")
                        if href:
                            bin_data_path = href
                        break

        # Remove from header binDataList (use the numeric id)
        if header is not None and bin_item_numeric_id is not None:
            if header.remove_bin_item(bin_item_numeric_id):
                removed = True

        # Remove from manifest
        if self._package.remove_manifest_item(item_id):
            removed = True

        # Remove from ZIP
        if bin_data_path and self._package.has_part(bin_data_path):
            self._package.delete(bin_data_path)
            removed = True

        return removed

    # ------------------------------------------------------------------
    # Export helpers
    # ------------------------------------------------------------------

    def export_text(self, **kwargs: object) -> str:
        """Export content as plain text.  Keyword args forwarded to :func:`~hwpx.tools.exporter.export_text`."""
        from .tools.exporter import export_text
        return export_text(self, **kwargs)  # type: ignore[arg-type]

    def export_html(self, **kwargs: object) -> str:
        """Export content as HTML.  Keyword args forwarded to :func:`~hwpx.tools.exporter.export_html`."""
        from .tools.exporter import export_html
        return export_html(self, **kwargs)  # type: ignore[arg-type]

    def export_markdown(self, **kwargs: object) -> str:
        """Export content as Markdown.  Keyword args forwarded to :func:`~hwpx.tools.exporter.export_markdown`."""
        from .tools.exporter import export_markdown
        return export_markdown(self, **kwargs)  # type: ignore[arg-type]

    def export_rich_markdown(self, **kwargs: object) -> str:
        """Export rich Markdown preserving inline styles, tables, footnotes, hyperlinks, images, and shape text.

        Keyword args forwarded to :func:`~hwpx.tools.markdown_export.export_markdown`.
        """
        from .tools.markdown_export import export_markdown as _rich
        return _rich(self, **kwargs)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> "ValidationReport":
        """Run XML schema validation on the current document state.

        Returns a :class:`~hwpx.tools.validator.ValidationReport` with
        any issues found.  This does **not** require ``validate_on_save``
        to be enabled.
        """
        from .tools.validator import validate_document

        return validate_document(
            self._to_bytes_for_validation()
        )

    def _run_pre_save_validation(self) -> None:
        """Raise if validate_on_save is enabled and the document is invalid."""
        if not self.validate_on_save:
            return
        report = self.validate()
        if not report.ok:
            msgs = _summarize_validation_issues(report.issues)
            raise ValueError(f"Document validation failed: {msgs}")

    def _run_open_safety_validation(self, archive_bytes: bytes) -> None:
        """Raise if generated bytes are unsafe to hand to an HWPX editor."""

        from .tools.package_validator import validate_editor_open_safety

        report = validate_editor_open_safety(archive_bytes)
        if not report.ok:
            raise ValueError(
                "Generated HWPX package failed open-safety validation: "
                + report.summary
            )

    def _gate_and_write(
        self,
        archive_bytes: bytes,
        *,
        output_path: str | PathLike[str] | None = None,
        output_stream: BinaryIO | None = None,
        source_label: str,
    ) -> VisualCompleteReport:
        """Funnel a serialized archive through the SavePipeline (transparent).

        ``_to_bytes_raw`` already ran open-safety and raised on failure, so the
        gate is transparent here — it performs the single atomic write and returns
        the uniform report. Raises if the gate unexpectedly rejects the bytes.
        """

        report = self._save_pipeline.run(
            archive_bytes,
            output_path=output_path,
            output_stream=output_stream,
            quality=QualityPolicy.transparent(),
            open_safety=OpenSafetyReport.passed("validated during serialize"),
            publish="on_pass",
            source_label=source_label,
        )
        if not report.ok:
            detail = "; ".join(str(error) for error in report.errors)
            raise ValueError(f"Document save failed the quality gate: {detail}")
        return report

    def save_to_path(self, path: str | PathLike[str]) -> str | PathLike[str]:
        """Persist pending changes to *path* and return the same path."""

        self._run_pre_save_validation()
        archive_bytes = self._to_bytes_raw(reset_dirty=False)
        self._gate_and_write(
            archive_bytes, output_path=path, source_label="document.save_to_path"
        )
        self._mark_save_clean()
        return path

    def save_to_stream(self, stream: BinaryIO) -> BinaryIO:
        """Persist pending changes to *stream* and return the same stream."""

        self._run_pre_save_validation()
        archive_bytes = self._to_bytes_raw(reset_dirty=False)
        self._gate_and_write(
            archive_bytes, output_stream=stream, source_label="document.save_to_stream"
        )
        self._mark_save_clean()
        return stream

    def save_report(
        self,
        path_or_stream: str | PathLike[str] | BinaryIO | None = None,
        *,
        quality: QualityPolicy | None = None,
        before: str | PathLike[str] | None = None,
        edit_mask: Any | None = None,
        ledger: Any | None = None,
    ) -> VisualCompleteReport:
        """Save through the SavePipeline and return the full ``VisualCompleteReport``.

        This is the canonical Phase-B write: it funnels through the one gate and
        returns the uniform report (open-safety, reference integrity, and — when
        the policy renders and a Hancom oracle is reachable — the visual verdict).
        ``quality`` defaults to :meth:`QualityPolicy.transparent` so the call is a
        drop-in for ``save_to_path`` that simply also hands back the report; pass
        ``QualityPolicy.strict()`` (or ``render_check="required"``) to demand the
        oracle-verified ``visual_complete`` tier (plan §0.0).

        Like the legacy savers it raises only if the serialize step's open-safety
        check fails; all other gate outcomes are returned in the report.
        """

        self._run_pre_save_validation()
        archive_bytes = self._to_bytes_raw(reset_dirty=False)

        output_path: str | PathLike[str] | None = None
        output_stream: BinaryIO | None = None
        if isinstance(path_or_stream, (str, PathLike)):
            output_path = path_or_stream
        elif path_or_stream is not None:
            output_stream = path_or_stream

        report = self._save_pipeline.run(
            archive_bytes,
            output_path=output_path,
            output_stream=output_stream,
            quality=quality or QualityPolicy.transparent(),
            before=before,
            edit_mask=edit_mask,
            ledger=ledger,
            reference_document=self,
            source_label="document.save_report",
        )
        if report.ok:
            self._mark_save_clean()
        return report

    def to_bytes(self) -> bytes:
        """Serialize pending changes and return the HWPX archive as bytes."""

        self._run_pre_save_validation()
        return self._to_bytes_raw()

    def _to_bytes_raw(
        self,
        *,
        reset_dirty: bool = True,
    ) -> bytes:
        """Serialize and run editor-open safety validation.

        When ``reset_dirty`` is ``False``, the document remains marked as
        modified after the archive snapshot is generated.
        """
        updates = self._root.serialize()
        if updates:
            for part_name, payload in updates.items():
                self._package.set_part(part_name, payload)
        result = self._package._save_to_bytes(
            verify_open_safety=True,
            mark_clean=False,
        )
        if isinstance(result, bytes):
            self._run_open_safety_validation(result)
            if reset_dirty:
                self._mark_save_clean()
            return result
        raise TypeError("package.save(None) must return bytes")

    def _to_bytes_for_validation(self) -> bytes:
        """Serialize current state for document validation without handing bytes to callers."""

        updates = self._root.serialize()
        return self._package._save_bytes_unchecked(
            updates,
            _unchecked_token=_UNCHECKED_SAVE_TOKEN,
        )

    def _mark_save_clean(self) -> None:
        self._root.reset_dirty()
        self._package.version_info.mark_clean()

    @overload
    def save(self, path_or_stream: None = None) -> bytes: ...

    @overload
    def save(self, path_or_stream: str | PathLike[str]) -> str | PathLike[str]: ...

    @overload
    def save(self, path_or_stream: BinaryIO) -> BinaryIO: ...

    def save(
        self,
        path_or_stream: str | PathLike[str] | BinaryIO | None = None,
    ) -> str | PathLike[str] | BinaryIO | bytes:
        """Deprecated compatibility wrapper around save_to_path/save_to_stream/to_bytes.

        Deprecated:
            ``save()``는 하위 호환을 위해 유지되며 향후 제거될 수 있습니다.
            - 경로 저장: ``save_to_path(path)``
            - 스트림 저장: ``save_to_stream(stream)``
            - 바이트 반환: ``to_bytes()``
        """

        warnings.warn(
            "HwpxDocument.save()는 deprecated 예정입니다. "
            "save_to_path()/save_to_stream()/to_bytes() 사용을 권장합니다.",
            DeprecationWarning,
            stacklevel=2,
        )
        if path_or_stream is None:
            return self.to_bytes()
        if isinstance(path_or_stream, (str, PathLike)):
            return self.save_to_path(path_or_stream)
        return self.save_to_stream(path_or_stream)
