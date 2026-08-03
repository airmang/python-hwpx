# SPDX-License-Identifier: Apache-2.0
"""High-level representation of an HWPX document."""

from __future__ import annotations

import xml.etree.ElementTree as ET
import io
import logging

from os import PathLike
from typing import (
    TYPE_CHECKING,
    Any,
    BinaryIO,
    Literal,
    cast,
    overload,
)

from .oxml import (
    HwpxOxmlDocument,
    HwpxOxmlInlineObject,
    HwpxOxmlParagraph,
    HwpxOxmlSection,
    HwpxOxmlTable,
    Style,
)
from .opc.package import (
    HwpxPackage,
)
from .oxml.namespaces import register_owpml_namespaces
from .mutation_report import Fallback, Mode, MutationReport
from .quality import QualityPolicy, SavePipeline, VisualCompleteReport
from .templates import blank_document_bytes

from ._document import fields as _fields
from ._document import media as _media
from ._document import persistence as _persistence
from ._document import _resolve
from ._document import headings as _headings
from .model import Paragraph
from ._document._legacy import _LegacyFacade
from ._document.ns import (
    FieldsNamespace,
    MediaNamespace,
    NotesNamespace,
    PageNamespace,
    PartsNamespace,
    RefsNamespace,
    ShapesNamespace,
    StylesNamespace,
    TablesNamespace,
    TextNamespace,
    TrackingNamespace,
)
from .errors import HwpxValueError
from ._document.memos import _append_element  # noqa: F401  # test_coverage_targets imports this name

register_owpml_namespaces(ET.register_namespace)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .tools.validator import ValidationReport


class HwpxDocument(_LegacyFacade):
    """Provides a user-friendly API for editing HWPX documents.

    6.0의 루트 표면은 34개다(5.x는 102개). 나머지는 도메인 네임스페이스로
    옮겨갔고, 옛 이름은 :class:`~hwpx._document._legacy._LegacyFacade`가
    위임 shim으로 유지한다 — 호출하면 행선지를 담은 ``DeprecationWarning``이
    나며 7.0에서 제거된다. 대응표는 ``docs/migration-6.0.md``.
    """

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
            # 6.0에서 이 셋은 doc.parts.* 로 이동했다. repr 이 자기 요약을
            # 만들려고 자기 deprecation 경고를 내면 안 되므로 소유 트리를
            # 직접 읽는다.
            f"headers={len(self._root.headers)}, "
            f"master_pages={len(self._root.master_pages)}, "
            f"histories={len(self._root.histories)}, "
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

    # ------------------------------------------------------------------
    # domain namespaces
    #
    # 6.0은 5.x 루트 102개 중 79개를 이 11개 네임스페이스로 옮겼다. 경계는
    # 발명한 것이 아니라 ``hwpx.capabilities._CAPABILITY_AREAS`` — 이미 모든
    # ``add_*``를 정확히 한 능력 영역에 귀속시키고 CI가 라이브 클래스에
    # 대조하는 그 레지스트리 — 에서 유도했다. 매핑표는 ``hwpx._document.ns``
    # 모듈 문서에 있다.
    #
    # 네임스페이스 객체는 상태를 갖지 않는다. 매번 새로 만들어도 같은 문서를
    # 가리키므로 캐시 무효화 문제를 아예 만들지 않는다.

    @property
    def styles(self) -> StylesNamespace:
        """서식 정의 — 스타일·문단모양·글자모양·테두리·글머리표.

        5.x에서 이 이름은 ``dict[str, Style]``이었다. 6.0의
        :class:`~hwpx._document.ns.styles.StylesNamespace`는
        ``Mapping[str, Style]``이라 ``doc.styles["0"]``·``.items()``·
        ``if doc.styles:``가 그대로 동작한다. 이름이 옮겨간 것이 아니라
        **같은 이름의 의미가 넓어졌다** — ``python-docx``의
        ``document.styles``도 같은 형태의 컬렉션 객체다.
        """

        return StylesNamespace(self)

    @property
    def tables(self) -> TablesNamespace:
        """표 탐색·매핑·병합·경로 채움."""

        return TablesNamespace(self)

    @property
    def fields(self) -> FieldsNamespace:
        """누름틀·체크박스 양식개체."""

        return FieldsNamespace(self)

    @property
    def shapes(self) -> ShapesNamespace:
        """도형·차트·수식 등 인라인 개체 저작."""

        return ShapesNamespace(self)

    @property
    def media(self) -> MediaNamespace:
        """BinData 이진 항목과 그림 참조 관리."""

        return MediaNamespace(self)

    @property
    def notes(self) -> NotesNamespace:
        """각주·미주·메모 — 본문 흐름 밖 주석."""

        return NotesNamespace(self)

    @property
    def refs(self) -> RefsNamespace:
        """책갈피·하이퍼링크."""

        return RefsNamespace(self)

    @property
    def tracking(self) -> TrackingNamespace:
        """변경추적(redline) 저작과 조회."""

        return TrackingNamespace(self)

    @property
    def page(self) -> PageNamespace:
        """쪽 기하 — 용지·여백·단·머리말/꼬리말·쪽번호."""

        return PageNamespace(self)

    @property
    def text(self) -> TextNamespace:
        """텍스트 순회·검색·치환·내보내기."""

        return TextNamespace(self)

    @property
    def parts(self) -> PartsNamespace:
        """OPC 파트 접근 — ``header.xml``·바탕쪽·이력·버전.

        5.x의 ``doc.headers``가 여기로 왔다. 그 이름은 쪽 머리말이 아니라
        ``Contents/header.xml`` 파트였는데, 같은 객체에 ``set_header_text``가
        있어 오독을 유발했다.
        """

        return PartsNamespace(self)

    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # editing helpers
    def add_paragraph(
        self,
        text: str = "",
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        para_pr_id_ref: str | int | None = None,
        style: int | str | Style | None = None,
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

        ``style`` 은 스타일을 **이름으로** 지정한다(``style="개요 1"``). 이름은
        **호출 시점에** 해석되고, 못 찾으면 가용 목록과 가장 가까운 이름을 담은
        ``HwpxLookupError`` 가 그 자리에서 난다. 5.x 는 이름을 serialize 시점에만
        해석했고 오타는 저장까지 조용히 통과했다 — 한컴에서 스타일이 안 먹은
        문서가 나오는 경로였다. 숫자 id 를 쓰던 ``style_id_ref`` 는 그대로 동작한다.
        """
        style_id_ref = self._resolve_style_ref(style, style_id_ref, caller="add_paragraph")
        section = _resolve.resolve_section(
            self, section, section_index, caller="add_paragraph"
        )
        return self._root.add_paragraph(
            text,
            section=section,
            section_index=None,
            para_pr_id_ref=para_pr_id_ref,
            style_id_ref=style_id_ref,
            char_pr_id_ref=char_pr_id_ref,
            run_attributes=run_attributes,
            include_run=include_run,
            inherit_style=inherit_style,
            **cast(Any, extra_attrs),
        )

    def _resolve_style_ref(
        self,
        style: int | str | Style | None,
        style_id_ref: str | int | None,
        *,
        caller: str,
    ) -> str | int | None:
        """``style=`` 을 호출 시점에 해석해 ``styleIDRef`` 로 쓸 값을 돌려준다.

        둘 다 주면 실패한다 — 하나는 이름, 하나는 id 인데 서로 다른 스타일을
        가리킬 수 있고, 어느 쪽을 이겼는지 조용히 정하는 것이 5.x 가 저지른
        종류의 실수다.
        """

        if style is None:
            return style_id_ref
        if style_id_ref is not None:
            raise HwpxValueError(
                "style 과 style_id_ref 를 동시에 지정할 수 없습니다.",
                code="style-argument-conflict",
                context={"caller": caller, "style": repr(style), "styleIdRef": style_id_ref},
                suggestion="style= 하나만 쓰세요. 이름과 숫자 id 를 모두 받습니다.",
            )
        return self.styles.resolve(style).id

    def add_heading(
        self,
        text: str = "",
        level: int = 1,
        *,
        style: int | str | Style | None = None,
        section: int | HwpxOxmlSection | None = None,
        section_index: int | None = None,
        char_pr_id_ref: str | int | None = None,
        **extra_attrs: str,
    ) -> Paragraph:
        """개요 수준 *level* 의 제목 문단을 추가하고 반환한다.

        ``python-docx`` 이주자가 가장 먼저 찾는 이름이고, 5.x에는 없었다.
        단순한 편의 래퍼가 아니라 **결함 수리**다 — 5.x에서 개요 스타일과
        개요 수준은 분리돼 있었다. ``set_paragraph_format(outline_level=1)``은
        문단에 ``<hh:heading type="OUTLINE">``을 쓰지만 ``styleIDRef``는
        건드리지 않아, "개요 번호는 붙는데 스타일은 바탕글(0)"인 문단이
        나왔다. ``add_heading``은 그 둘을 한 번에 묶는 유일한 API다.

        Args:
            text: 제목 텍스트.
            level: 개요 수준 1~10. HWPX 개요는 정확히 10수준이다.
            style: 주면 *level* 로 유도한 스타일 대신 이것을 쓴다.
                이름(``"개요 1"``)·영문명(``"Outline 1"``)·숫자 id 모두 받는다.
            section: 섹션 객체 **또는 인덱스**. ``None``이면 마지막 섹션.
            section_index: 6.x deprecated 별칭 — ``section`` 을 쓰세요.

        Raises:
            HwpxValueError: *level* 이 1~10 밖이다.
            HwpxLookupError: 이 문서에 해당 개요 스타일이 없다.

        Note:
            ``level=0``(``python-docx`` 의 Title)은 지원하지 않는다. Skeleton에
            "제목" 스타일이 없고, 없는 스타일을 만들어 넣으면 한컴의 개요 번호
            매기기가 그 문단을 세지 않아 번호가 어긋난 문서가 나온다. 문서
            제목에는 ``style=`` 로 그 문서에 실재하는 스타일을 지정한다.
        """

        target = _resolve.resolve_section(
            self, section, section_index, caller="add_heading"
        )
        resolved = _headings.resolve_heading_style(self, level=level, style=style)
        paragraph = self._root.add_paragraph(
            text,
            section=target,
            style_id_ref=resolved.id,
            char_pr_id_ref=char_pr_id_ref,
            inherit_style=False,
            **cast(Any, extra_attrs),
        )
        _headings.bind_outline_level(self, paragraph, level=level)
        return paragraph

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
        style: int | str | Style | None = None,
        style_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        inherit_style: bool = False,
        **extra_attrs: str,
    ) -> HwpxOxmlTable:
        """Create a table in a neutral new paragraph and return it.

        A table anchor must not inherit the preceding paragraph's heading or
        list style.  Hancom renders that inherited numbering beside the table
        (for example, a stray ``2.`` after a level-one heading).  Callers that
        intentionally need a styled anchor can pass explicit paragraph/style
        references or set *inherit_style* to :data:`True`.
        """

        style_id_ref = self._resolve_style_ref(style, style_id_ref, caller="add_table")
        section = _resolve.resolve_section(
            self, section, section_index, caller="add_table"
        )
        section_index = None
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
            inherit_style=inherit_style,
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
        style: int | str | Style | None = None,
        style_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        **extra_attrs: str,
    ) -> HwpxOxmlInlineObject:
        """Embed image data and place a picture object in a new paragraph."""

        style_id_ref = self._resolve_style_ref(style, style_id_ref, caller="add_picture")
        section = _resolve.resolve_section(
            self, section, section_index, caller="add_picture"
        )
        section_index = None
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

    def _iter_form_field_matches(self) -> list[dict[str, Any]]:
        return _fields._iter_form_field_matches(self)

    # ------------------------------------------------------------------
    # Footnote / Endnote helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Drawing shapes
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Existing-document formatting
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Column layout
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Bookmarks and hyperlinks
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Export helpers
    # ------------------------------------------------------------------

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
