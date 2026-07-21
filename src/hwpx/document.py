# SPDX-License-Identifier: Apache-2.0
"""High-level representation of an HWPX document."""

from __future__ import annotations

import xml.etree.ElementTree as ET
import io
from datetime import datetime
import logging

from os import PathLike
from typing import (
    TYPE_CHECKING,
    Any,
    BinaryIO,
    Iterator,
    Literal,
    Mapping,
    Sequence,
    cast,
    overload,
)


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
)
from .oxml.namespaces import register_owpml_namespaces
from .mutation_report import Fallback, Mode, MutationReport
from .quality import QualityPolicy, SavePipeline, VisualCompleteReport
from .templates import blank_document_bytes

from ._document import fields as _fields
from ._document import memos as _memos
from ._document import tracked as _tracked
from ._document import layout as _layout
from ._document import media as _media
from ._document import persistence as _persistence
from ._document import shapes as _shapes
from ._document.memos import _append_element  # noqa: F401  # test_coverage_targets imports this name

register_owpml_namespaces(ET.register_namespace)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .form_fit.policy import FitPolicy
    from .tools.validator import ValidationReport
    from .tools.table_navigation import (
        SearchDirection,
        TableFillResult,
        TableLabelSearchResult,
        TableMapResult,
    )


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
        # HwpxPackage/ZipFile accepts os.PathLike at runtime; its narrower
        # compatibility annotation intentionally remains frozen.
        package = HwpxPackage.open(cast(Any, open_source))
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

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:  # type: ignore[exit-return]  # frozen public signature
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

    def add_track_change(
        self,
        change_type: str,
        *,
        author_name: str = "AI Agent",
        date: str | None = None,
    ) -> int:
        """Add tracked-change header metadata and return the new change id."""

        return _tracked.add_track_change(
            self,
            change_type,
            author_name=author_name,
            date=date,
        )


    def add_tracked_insert(
        self,
        paragraph: HwpxOxmlParagraph,
        text: str,
        *,
        author: str = "AI Agent",
        date: str | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> int:
        """Append tracked inserted *text* to *paragraph* and return its change id."""

        return _tracked.add_tracked_insert(
            self,
            paragraph,
            text,
            author=author,
            date=date,
            char_pr_id_ref=char_pr_id_ref,
        )

    def add_tracked_delete(
        self,
        paragraph: HwpxOxmlParagraph,
        *,
        match: str | None = None,
        author: str = "AI Agent",
        date: str | None = None,
    ) -> int:
        """Wrap paragraph text or the first matching substring in delete marks."""

        return _tracked.add_tracked_delete(
            self,
            paragraph,
            match=match,
            author=author,
            date=date,
        )

    def add_tracked_replace(
        self,
        paragraph: HwpxOxmlParagraph,
        old: str,
        new: str,
        *,
        author: str = "AI Agent",
        date: str | None = None,
    ) -> tuple[int, int]:
        """Represent a replacement as tracked delete of *old* plus tracked insert of *new*."""

        return _tracked.add_tracked_replace(
            self,
            paragraph,
            old,
            new,
            author=author,
            date=date,
        )

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

        return _memos.add_memo(
            self,
            text,
            section=section,
            section_index=section_index,
            memo_shape_id_ref=memo_shape_id_ref,
            memo_id=memo_id,
            char_pr_id_ref=char_pr_id_ref,
            attributes=attributes,
        )

    def remove_memo(self, memo: HwpxOxmlMemo) -> None:
        """Remove *memo* from the section it belongs to."""

        return _memos.remove_memo(self, memo)

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

        return _memos.attach_memo_field(
            self,
            paragraph,
            memo,
            field_id=field_id,
            author=author,
            created=created,
            number=number,
            char_pr_id_ref=char_pr_id_ref,
        )

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

        return _memos.add_memo_with_anchor(
            self,
            text,
            paragraph=paragraph,
            section=section,
            section_index=section_index,
            paragraph_text=paragraph_text,
            memo_shape_id_ref=memo_shape_id_ref,
            memo_id=memo_id,
            char_pr_id_ref=char_pr_id_ref,
            attributes=attributes,
            field_id=field_id,
            author=author,
            created=created,
            number=number,
            anchor_char_pr_id_ref=anchor_char_pr_id_ref,
        )

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
            **cast(Any, extra_attrs),
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
            **cast(Any, extra_attrs),
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

        return _media.add_picture(
            self,
            image_data=image_data,
            image_format=image_format,
            section=section,
            section_index=section_index,
            width=width,
            height=height,
            width_mm=width_mm,
            height_mm=height_mm,
            align=align,
            para_pr_id_ref=para_pr_id_ref,
            style_id_ref=style_id_ref,
            char_pr_id_ref=char_pr_id_ref,
            run_attributes=run_attributes,
            **extra_attrs,
        )


    def picture_references(self) -> list[dict[str, Any]]:
        """Return body picture references in document order."""

        return _media.picture_references(self)

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

        return _media.replace_picture(
            self,
            image_data=image_data,
            image_format=image_format,
            picture_index=picture_index,
            binary_item_id_ref=binary_item_id_ref,
            remove_orphaned=remove_orphaned,
            item_id=item_id,
        )

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

        return find_cell_by_label(
            self,
            label_text,
            direction=cast("SearchDirection", direction),
        )


    def _iter_form_field_matches(self) -> list[dict[str, Any]]:
        return _fields._iter_form_field_matches(self)

    def list_form_fields(self) -> list[dict[str, Any]]:
        """Return native form/click-here fields in document order.

        The result intentionally excludes memo and hyperlink fields because
        those are annotation/navigation mechanisms rather than fillable form
        slots.
        """

        return _fields.list_form_fields(self)


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

        return _fields.fill_form_field(
            self,
            value,
            field_index=field_index,
            field_id=field_id,
            name=name,
            fit_policy=fit_policy,
            box_width=box_width,
            font_pt=font_pt,
        )


    def fill_by_path(
        self,
        mappings: Mapping[str, str],
    ) -> TableFillResult:
        """Fill table cells using ``label > direction > ...`` navigation paths."""

        return _fields.fill_by_path(self, mappings)

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

        return _shapes.add_shape(
            self,
            shape_type=shape_type,
            section=section,
            section_index=section_index,
            attributes=attributes,
            para_pr_id_ref=para_pr_id_ref,
            style_id_ref=style_id_ref,
            char_pr_id_ref=char_pr_id_ref,
            run_attributes=run_attributes,
            **extra_attrs,
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

        return _shapes.add_control(
            self,
            section=section,
            section_index=section_index,
            attributes=attributes,
            control_type=control_type,
            para_pr_id_ref=para_pr_id_ref,
            style_id_ref=style_id_ref,
            char_pr_id_ref=char_pr_id_ref,
            run_attributes=run_attributes,
            **extra_attrs,
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

        return _shapes.add_footnote(
            self,
            text=text,
            paragraph=paragraph,
            section=section,
            section_index=section_index,
            char_pr_id_ref=char_pr_id_ref,
        )

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

        return _shapes.add_endnote(
            self,
            text=text,
            paragraph=paragraph,
            section=section,
            section_index=section_index,
            char_pr_id_ref=char_pr_id_ref,
        )

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

        return _shapes.add_line(
            self,
            start_x=start_x,
            start_y=start_y,
            end_x=end_x,
            end_y=end_y,
            line_color=line_color,
            line_width=line_width,
            treat_as_char=treat_as_char,
            paragraph=paragraph,
            section=section,
            section_index=section_index,
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

        return _shapes.add_rectangle(
            self,
            width=width,
            height=height,
            ratio=ratio,
            line_color=line_color,
            line_width=line_width,
            fill_color=fill_color,
            treat_as_char=treat_as_char,
            paragraph=paragraph,
            section=section,
            section_index=section_index,
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

        return _shapes.add_ellipse(
            self,
            width=width,
            height=height,
            line_color=line_color,
            line_width=line_width,
            fill_color=fill_color,
            treat_as_char=treat_as_char,
            paragraph=paragraph,
            section=section,
            section_index=section_index,
        )

    # ------------------------------------------------------------------
    # Existing-document formatting
    # ------------------------------------------------------------------


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

        return _layout.set_paragraph_format(
            self,
            paragraph_index=paragraph_index,
            paragraph_indexes=paragraph_indexes,
            alignment=alignment,
            line_spacing_percent=line_spacing_percent,
            indent_left_mm=indent_left_mm,
            indent_right_mm=indent_right_mm,
            first_line_indent_mm=first_line_indent_mm,
            spacing_before_pt=spacing_before_pt,
            spacing_after_pt=spacing_after_pt,
            outline_level=outline_level,
            keep_with_next=keep_with_next,
            keep_lines=keep_lines,
            page_break_before=page_break_before,
            bottom_border=bottom_border,
            border_color=border_color,
            border_width=border_width,
        )

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

        return _layout.set_list_format(
            self,
            paragraph_index=paragraph_index,
            paragraph_indexes=paragraph_indexes,
            kind=kind,
            level=level,
            bullet_char=bullet_char,
            number_format=number_format,
            start=start,
        )

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

        return _layout.set_page_setup(
            self,
            paper_size=paper_size,
            width_mm=width_mm,
            height_mm=height_mm,
            orientation=orientation,
            margins_mm=margins_mm,
            margin_left_mm=margin_left_mm,
            margin_right_mm=margin_right_mm,
            margin_top_mm=margin_top_mm,
            margin_bottom_mm=margin_bottom_mm,
            header_margin_mm=header_margin_mm,
            footer_margin_mm=footer_margin_mm,
            gutter_mm=gutter_mm,
            columns=columns,
            column_gap_mm=column_gap_mm,
            section=section,
            section_index=section_index,
        )

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

        return _layout.set_columns(
            self,
            col_count=col_count,
            col_type=col_type,
            layout=layout,
            same_size=same_size,
            same_gap=same_gap,
            column_widths=column_widths,
            separator_type=separator_type,
            separator_width=separator_width,
            separator_color=separator_color,
            paragraph=paragraph,
            section=section,
            section_index=section_index,
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

        return _layout.add_bookmark(
            self,
            name=name,
            paragraph=paragraph,
            section=section,
            section_index=section_index,
        )

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

        return _layout.add_hyperlink(
            self,
            url=url,
            display_text=display_text,
            paragraph=paragraph,
            section=section,
            section_index=section_index,
        )


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

        return _layout.set_page_size(
            self,
            width=width,
            height=height,
            orientation=orientation,
            gutter_type=gutter_type,
            section=section,
            section_index=section_index,
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

        return _layout.set_page_margins(
            self,
            left=left,
            right=right,
            top=top,
            bottom=bottom,
            header=header,
            footer=footer,
            gutter=gutter,
            section=section,
            section_index=section_index,
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

        return _layout.set_header_text(
            self,
            text=text,
            section=section,
            section_index=section_index,
            page_type=page_type,
        )

    def set_footer_text(
        self,
        text: str,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        page_type: str = "BOTH",
    ) -> HwpxOxmlSectionHeaderFooter:
        """Ensure the requested section contains a footer for *page_type* and set its text."""

        return _layout.set_footer_text(
            self,
            text=text,
            section=section,
            section_index=section_index,
            page_type=page_type,
        )

    def set_header_content(
        self,
        content: Sequence[Mapping[str, Any]],
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        page_type: str = "BOTH",
    ) -> HwpxOxmlSectionHeaderFooter:
        """Ensure the requested section contains a rich header for *page_type*."""

        return _layout.set_header_content(
            self,
            content=content,
            section=section,
            section_index=section_index,
            page_type=page_type,
        )

    def set_footer_content(
        self,
        content: Sequence[Mapping[str, Any]],
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        page_type: str = "BOTH",
    ) -> HwpxOxmlSectionHeaderFooter:
        """Ensure the requested section contains a rich footer for *page_type*."""

        return _layout.set_footer_content(
            self,
            content=content,
            section=section,
            section_index=section_index,
            page_type=page_type,
        )

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

        return _layout.set_header_footer(
            self,
            kind=kind,
            text=text,
            content=content,
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

        return _layout.set_page_number(
            self,
            target=target,
            page_type=page_type,
            format=format,
            align=align,
            position=position,
            prefix=prefix,
            suffix=suffix,
            format_type=format_type,
            section=section,
            section_index=section_index,
        )

    def remove_header(
        self,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        page_type: str = "BOTH",
    ) -> None:
        """Remove the header linked to *page_type* from the requested section if present."""

        return _layout.remove_header(
            self,
            section=section,
            section_index=section_index,
            page_type=page_type,
        )

    def remove_footer(
        self,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        page_type: str = "BOTH",
    ) -> None:
        """Remove the footer linked to *page_type* from the requested section if present."""

        return _layout.remove_footer(
            self,
            section=section,
            section_index=section_index,
            page_type=page_type,
        )

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

        return _media.add_image(
            self,
            image_data=image_data,
            image_format=image_format,
            item_id=item_id,
        )


    def list_images(self) -> list[dict[str, str]]:
        """Return metadata dicts for all embedded binary data items.

        Each dict contains the ``<hh:binItem>`` attributes (``id``, ``Type``,
        ``BinData``, ``Format``, …).
        """

        return _media.list_images(self)

    def remove_image(self, item_id: str) -> bool:
        """Remove an embedded image by its manifest item id.

        This removes the binary data from the ZIP, the manifest entry, and
        the header binItem entry.

        Returns:
            ``True`` if any component was removed.
        """

        return _media.remove_image(
            self,
            item_id=item_id,
        )

    # ------------------------------------------------------------------
    # Export helpers
    # ------------------------------------------------------------------

    def export_text(self, **kwargs: object) -> str:
        """Export content as plain text.  Keyword args forwarded to :func:`~hwpx.tools.exporter.export_text`."""

        return _persistence.export_text(
            self,
            **kwargs,
        )

    def export_html(self, **kwargs: object) -> str:
        """Export content as HTML.  Keyword args forwarded to :func:`~hwpx.tools.exporter.export_html`."""

        return _persistence.export_html(
            self,
            **kwargs,
        )

    def export_markdown(self, **kwargs: object) -> str:
        """Export content as Markdown.  Keyword args forwarded to :func:`~hwpx.tools.exporter.export_markdown`."""

        return _persistence.export_markdown(
            self,
            **kwargs,
        )

    def export_rich_markdown(self, **kwargs: object) -> str:
        """Export rich Markdown preserving inline styles, tables, footnotes, hyperlinks, images, and shape text.

        Keyword args forwarded to :func:`~hwpx.tools.markdown_export.export_markdown`.
        """

        return _persistence.export_rich_markdown(
            self,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> "ValidationReport":
        """Run XML schema validation on the current document state.

        Returns a :class:`~hwpx.tools.validator.ValidationReport` with
        any issues found.  This does **not** require ``validate_on_save``
        to be enabled.
        """

        return _persistence.validate(self)


    def _run_open_safety_validation(self, archive_bytes: bytes) -> None:
        """Raise if generated bytes are unsafe to hand to an HWPX editor."""

        return _persistence._run_open_safety_validation(
            self,
            archive_bytes=archive_bytes,
        )


    @overload
    def save_to_path(
        self,
        path: str | PathLike[str],
        *,
        mode: Mode = ...,
        fallback: Fallback = ...,
        return_report: Literal[False] = ...,
    ) -> str | PathLike[str]: ...

    @overload
    def save_to_path(
        self,
        path: str | PathLike[str],
        *,
        mode: Mode = ...,
        fallback: Fallback = ...,
        return_report: Literal[True],
    ) -> MutationReport: ...

    def save_to_path(
        self,
        path: str | PathLike[str],
        *,
        mode: Mode = "auto",
        fallback: Fallback = "error",
        return_report: bool = False,
    ) -> str | PathLike[str] | MutationReport:
        """Persist pending changes to *path* and return the same path.

        ``return_report=True`` returns the Safe Write Contract
        :class:`~hwpx.mutation_report.MutationReport` instead. ``mode="patch"``
        with ``fallback="error"`` raises
        :class:`~hwpx.mutation_report.PreservationDowngradeError` and writes
        nothing when an untouched part would not stay byte-identical.
        """

        return _persistence.save_to_path(
            self,
            path=path,
            mode=mode,
            fallback=fallback,
            return_report=return_report,
        )

    @overload
    def save_to_stream(
        self,
        stream: BinaryIO,
        *,
        mode: Mode = ...,
        fallback: Fallback = ...,
        return_report: Literal[False] = ...,
    ) -> BinaryIO: ...

    @overload
    def save_to_stream(
        self,
        stream: BinaryIO,
        *,
        mode: Mode = ...,
        fallback: Fallback = ...,
        return_report: Literal[True],
    ) -> MutationReport: ...

    def save_to_stream(
        self,
        stream: BinaryIO,
        *,
        mode: Mode = "auto",
        fallback: Fallback = "error",
        return_report: bool = False,
    ) -> BinaryIO | MutationReport:
        """Persist pending changes to *stream* and return the same stream.

        ``return_report=True`` returns the Safe Write Contract
        :class:`~hwpx.mutation_report.MutationReport` instead. See
        :meth:`save_to_path` for the ``mode``/``fallback`` grade semantics.
        """

        return _persistence.save_to_stream(
            self,
            stream=stream,
            mode=mode,
            fallback=fallback,
            return_report=return_report,
        )

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

        return _persistence.save_report(
            self,
            path_or_stream=path_or_stream,
            quality=quality,
            before=before,
            edit_mask=edit_mask,
            ledger=ledger,
        )

    def to_bytes(
        self,
        *,
        mode: Mode = "auto",
        fallback: Fallback = "error",
    ) -> bytes:
        """Serialize pending changes and return the HWPX archive as bytes.

        ``mode="patch"`` with ``fallback="error"`` raises
        :class:`~hwpx.mutation_report.PreservationDowngradeError` before
        returning when the archive is not patch-grade; the byte return itself is
        unchanged.
        """

        return _persistence.to_bytes(self, mode=mode, fallback=fallback)

    def _to_bytes_raw(
        self,
        *,
        reset_dirty: bool = True,
    ) -> bytes:
        """Serialize and run editor-open safety validation.

        When ``reset_dirty`` is ``False``, the document remains marked as
        modified after the archive snapshot is generated.
        """

        return _persistence._to_bytes_raw(
            self,
            reset_dirty=reset_dirty,
        )
