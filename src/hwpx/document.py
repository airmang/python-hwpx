# SPDX-License-Identifier: Apache-2.0
"""High-level representation of an HWPX document."""

from __future__ import annotations

import xml.etree.ElementTree as ET
import io
from datetime import datetime
import os
import logging

from os import PathLike
from typing import (
    TYPE_CHECKING,
    Any,
    BinaryIO,
    Mapping,
    cast,
)

from .oxml import (
    HwpxOxmlDocument,
    HwpxOxmlParagraph,
    HwpxOxmlSection,
    HwpxOxmlTable,
    PictureGlow,
    PictureReflection,
    PictureShadow,
    Style,
)
from .opc.package import (
    HwpxPackage,
    structure_errors,
)
from .oxml.namespaces import register_owpml_namespaces
from .oxml._document_primitives import IdSource, keep_ids_clear_of
from .oxml.table_sizes import new_table_width
from .mutation_report import Fallback, Mode, MutationReport
from .quality import QualityPolicy, SavePipeline
from .templates import new_document_bytes

from ._document import fields as _fields
from ._document import media as _media
from ._document import persistence as _persistence
from ._document.persistence import SaveFormat
from ._document import _resolve
from ._document import headings as _headings
from ._document import layout as _layout
from .model import Paragraph, Picture
from ._removed_names import install as _install_removed_name_hints
from ._removed_names import removed_name_error
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
from .errors import HwpxTypeError, HwpxValueError, rejects_removed_arguments
from ._document.memos import _append_element  # noqa: F401  # test_coverage_targets imports this name

register_owpml_namespaces(ET.register_namespace)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .hwp5.errors import Hwp5ConversionReport
    from .objects import Alignment, CellMargins
    from .tools.package_validator import EditorOpenSafetyReport
    from .tools.validator import ValidationReport
    from .oxml.settings import CaretPosition


class _DocumentType(type):
    """``HwpxDocument`` 의 메타클래스: 클래스로 부른 없어진 이름(``HwpxDocument.from_package``)도
    새 자리를 알려 준다. 인스턴스의 이름은 ``HwpxDocument.__getattr__`` 이 맡는다."""

    if not TYPE_CHECKING:  # 타입 검사기에는 숨긴다: 없는 이름을 정적으로 계속 잡게.

        def __getattr__(cls, name: str) -> Any:
            error = removed_name_error("doc", name)
            if error is None:
                error = AttributeError(f"type object {cls.__name__!r} has no attribute {name!r}")
            error.name = name
            error.obj = cls
            raise error


class HwpxDocument(metaclass=_DocumentType):
    """Provides a user-friendly API for editing HWPX documents.

    6.0의 루트 표면은 34개다(5.x는 102개). 나머지는 도메인 네임스페이스로
    옮겨갔다. 6.x가 경고와 함께 남겨 둔 옛 이름 79개와 7.0이 ``doc.save`` 하나로 합친
    저장 동사(``save_to_path``·``save_to_stream``·``save_report``), ``from_package`` 는
    7.0에서 없어졌다 — 부르면 새 자리를 알려 주는 :class:`~hwpx.errors.HwpxAttributeError`
    가 난다(표: :data:`hwpx._removed_names.NAMES` 의 ``"doc"`` 칸).
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
        # What an ``.hwp`` conversion could not carry into the model (None for HWPX).
        self._hwp5_report: Hwp5ConversionReport | None = None
        # The ``.hwp`` path the document was opened from, so a save cannot replace it.
        self._hwp5_source_path: str | None = None
        # What add_paragraph(inherit_style=None) means for this document (new(inherit_style=...)).
        self._inherit_style_default = True
        # True while a document from new() still has only its empty first paragraph: the first
        # paragraph added then takes that line (see _take_first_line).
        self._first_line_free = False
        # The id/clock source from new(seed=..., now=...) / open(...): this document's only.
        self._id_source: IdSource | None = None

    if not TYPE_CHECKING:  # 타입 검사기에는 숨긴다: 없는 이름을 정적으로 계속 잡게.

        def __getattr__(self, name: str) -> Any:
            """7.0에서 지운 옛 루트 이름이면 새 자리를 알려 주는 오류를 낸다."""

            error = removed_name_error("doc", name)
            if error is None:
                error = AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")
            error.name = name
            error.obj = self
            raise error

    def __repr__(self) -> str:
        """Return a compact and safe summary of the document state."""

        return (
            f"{self.__class__.__name__}("
            f"sections={len(self.sections)}, "
            f"paragraphs={len(self.paragraphs)}, "
            # 6.0에서 이 셋은 doc.parts.* 로 이동했다. 소유 트리를 직접 읽는다.
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
        source: str | PathLike[str] | bytes | BinaryIO | HwpxPackage,
        *,
        seed: int | None = None,
        now: datetime | None = None,
    ) -> "HwpxDocument":
        """Open *source* and return a :class:`HwpxDocument` instance.

        *source*는 경로, 바이트, 읽을 수 있는 이진 스트림, 또는 이미 연
        :class:`~hwpx.opc.package.HwpxPackage` 다(6.x 의 ``from_package``). 내용이 HWP 5.0
        복합 파일(``.hwp``)로 시작하면 같은 문서 모델로 바꿔서 연다.

        ``seed=``·``now=`` 는 :meth:`new` 와 같다: 이 문서를 고치며 새로 생기는
        문단·개체·메모 id 와 메모·변경 추적의 날짜를 고정해서, 같은 파일에 같은
        편집을 하면 같은 바이트가 나온다. 파일에 이미 있는 값은 바꾸지 않는다.
        이 값은 이 문서에만 쓰인다: 함께 열린 다른 문서는 이 seed 를 쓰지 않고,
        이 문서의 결과를 바꾸지도 않는다.

        Raises:
            FileNotFoundError: 경로에 파일이 없다. 그 밖의 ``OSError``(권한 등)도
                파이썬이 낸 그대로 올라온다.
            HwpxStructureError: 손상됐거나 필수 구성이 없는 HWPX. 손상 종류는 하위
                클래스로 가린다. 원래 예외는 ``__cause__``에 있다.

                - ``HwpxArchiveError``: ZIP이 아니거나 잘린 파일, 빈 파일.
                  ``zipfile.BadZipFile``이기도 하다.
                - ``HwpxCompressedDataError``: 압축 데이터 손상.
                  ``zlib.error``이기도 하다.
                - ``HwpxXmlSyntaxError``: 깨진 XML 파트(암호가 걸린 HWPX 포함).
                  ``lxml.etree.XMLSyntaxError``이기도 하다.
                - ``HwpxStructureError`` 자체: ``mimetype``·``container.xml``·
                  rootfile 같은 필수 구성이 없다.
            HwpxSecurityError: 항목 수·크기·압축률이 안전 상한을 넘는다
                (``ValueError`` 계열).
            Hwp5Error: ``.hwp`` 입력이 손상됐거나 암호·배포용·DRM 문서다.
        """
        id_source = cls._id_source_for(seed, now, "open")
        if isinstance(source, HwpxPackage):
            with structure_errors():
                package_root = HwpxOxmlDocument.from_package(source)
            from_package = cls(source, package_root)
            from_package._install_id_source(id_source, opened=True)
            return from_package
        internal_resources: list[Any] = []
        open_source = source
        if isinstance(source, bytes):
            stream = io.BytesIO(source)
            open_source = stream
            internal_resources.append(stream)
        if HwpxPackage._leading_bytes(cast(Any, open_source), 8) == HwpxPackage.OLE2_MAGIC:
            converted = cls._open_hwp5(open_source)
            converted._install_id_source(id_source, opened=True)
            return converted
        # HwpxPackage/ZipFile accepts os.PathLike at runtime; its narrower
        # compatibility annotation intentionally remains frozen.
        package = HwpxPackage.open(cast(Any, open_source))
        with structure_errors():
            root = HwpxOxmlDocument.from_package(package)
        document = cls(package, root, managed_resources=tuple(internal_resources))
        document._install_id_source(id_source, opened=True)
        return document

    @classmethod
    def _open_hwp5(cls, source: Any) -> "HwpxDocument":
        """Convert an HWP 5.0 (``.hwp``) file into the HWPX document model."""

        import warnings

        from .hwp5.errors import Hwp5ConversionReport, Hwp5ConversionWarning
        from .hwp5.package import MAX_FILE_BYTES, convert, to_hwpx_bytes

        # One byte past the limit is enough for convert() to refuse the file.
        if isinstance(source, (str, PathLike)):
            with open(source, "rb") as handle:
                data = handle.read(MAX_FILE_BYTES + 1)
        else:
            source.seek(0)
            data = source.read(MAX_FILE_BYTES + 1)
        converted = convert(data)
        package = HwpxPackage.open(to_hwpx_bytes(converted.files))
        package._source_archive = None  # converted, not opened from an HWPX file: no records to keep
        root = HwpxOxmlDocument.from_package(package)
        document = cls(package, root)
        document._hwp5_report = Hwp5ConversionReport.of(converted.report.unconverted, converted.report.dropped)
        if isinstance(source, (str, PathLike)):
            document._hwp5_source_path = os.path.abspath(os.fspath(source))
        skipped = converted.report.unconverted
        if skipped:
            summary = ", ".join(f"{kind} x{count}" for kind, count in sorted(skipped.items()))
            warnings.warn(
                f"HWP content not converted into the document model: {summary}",
                Hwp5ConversionWarning,
                stacklevel=3,
            )
        return document

    @property
    def conversion_report(self) -> Hwp5ConversionReport | None:
        """What opening an ``.hwp`` file could not carry into the document
        model, as read-only counts by kind (``unconverted``, ``dropped``);
        None for a document that was not opened from ``.hwp``."""

        return self._hwp5_report

    @staticmethod
    def _id_source_for(seed: "int | None", now: "datetime | None", caller: str) -> "IdSource | None":
        if seed is None and now is None:
            return None
        if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
            raise HwpxTypeError(
                f"seed 는 int 여야 합니다 — {type(seed).__name__} {seed!r}.",
                code="document-seed-invalid",
                context={"caller": caller, "type": type(seed).__name__},
                suggestion=f"HwpxDocument.{caller}(seed=7) 처럼 정수를 주세요.",
            )
        if now is not None and not isinstance(now, datetime):
            raise HwpxTypeError(
                f"now 는 datetime 이어야 합니다 — {type(now).__name__} {now!r}.",
                code="document-clock-invalid",
                context={"caller": caller, "type": type(now).__name__},
                suggestion=(
                    f"HwpxDocument.{caller}(now=datetime(2026, 1, 1, tzinfo=timezone.utc)) "
                    "처럼 시각을 주세요."
                ),
            )
        return IdSource(seed, now)

    def _install_id_source(self, source: "IdSource | None", *, opened: bool = False) -> None:
        if source is None:
            return
        self._id_source = source
        self._root._id_source = source
        if opened and source.seed is not None:
            # A seeded source hands out the same ids each time, so a document saved and opened again
            # with its seed would be given the ids it already holds (two fields with one id, neither
            # of which can then be filled by id). What the file holds is told to the source first.
            keep_ids_clear_of(
                source,
                (
                    node.get(name)
                    for part in (*self._root.sections, *self._root.master_pages, *self._root.headers)
                    for node in part.element.iter()
                    for name in ("id", "instid", "instId", "fieldid")
                ),
            )

    @classmethod
    def new(
        cls,
        *,
        inherit_style: bool = True,
        empty_first_line: bool = False,
        seed: int | None = None,
        now: datetime | None = None,
    ) -> "HwpxDocument":
        """Return a new blank document based on the default skeleton template.

        Its only paragraph is empty and holds the section settings. The first
        paragraph added with :meth:`add_paragraph` or :meth:`add_heading` takes
        that line, so the document starts with what was added first. (Up to
        6.x the first added paragraph came after it and every new document began
        with an empty line.) A table or another object added first still comes
        after the empty line: the paragraph holding the section settings does
        not hold objects.

        ``empty_first_line=True`` keeps the 6.x behaviour: every added paragraph
        comes after the empty one, so paragraph indexes written for 6.x stay valid.

        ``inherit_style=False`` makes a clean document: :meth:`add_paragraph`
        then starts every paragraph from the base shapes (바탕글) instead of
        copying the last paragraph's, unless a call passes ``inherit_style``
        itself. A paragraph added after a heading or a list item then does not
        pick up its outline or list numbering. The default keeps the inheriting
        behaviour.

        The document's metadata starts clean: no author, no last-saved-by, and
        the creation and modification dates set to now (UTC). Set the author
        with ``document.package.set_document_metadata(creator=...)``.

        **Same input, same file.** ``seed=`` and ``now=`` fix what a new document
        otherwise draws from chance and the clock, so the same calls in the same
        order write the same bytes, in another process too::

            doc = HwpxDocument.new(seed=7, now=datetime(2026, 1, 1, tzinfo=timezone.utc))

        *seed* (int) makes every paragraph, object and memo id come from
        ``random.Random(seed)`` instead of ``uuid4``. The ids keep the range of
        the random ones (1 .. 2**31 - 1) and do not repeat. *now* (a
        ``datetime``; a naive one is local time) is written as the creation and
        modification date and used for every memo or tracked change made without
        its own date. A memo's time is written as the machine's local wall time, as
        Hangul writes it, so a document that makes memos writes the same bytes
        where the time zone is the same. Both belong to this document until :meth:`close` (or the
        end of a ``with`` block): another document made, edited, closed or left
        unclosed meanwhile neither uses them nor changes what this one writes, so
        a document writes the same bytes whatever else is open. Content copied in
        from another document (``paragraph.copy_to``, ``obj.copy_to``,
        ``insert_document``) gets this document's ids. A group member
        (``ContainerMember``) is made without an id and gets one when a
        document takes it (``doc.shapes.add_container``). Without them a document
        gets random ids and the current time, as before: documents made
        separately must not share ids when their content is later combined.
        ``SOURCE_DATE_EPOCH`` still fixes the dates when *now* is not given.
        """

        source = cls._id_source_for(seed, now, "new")
        document = cls.open(
            new_document_bytes(source.now if source is not None else None)
        )
        # Built from parts, not opened from a file: no source records to keep (written as before).
        document._package._source_archive = None
        document._install_id_source(source)
        document._inherit_style_default = bool(inherit_style)
        document._first_line_free = not empty_first_line
        document.reset_caret()  # the body's start, by the rule a reset follows (the template's own value)
        return document

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
        self._root._id_source = None  # ids made after close are random, as before new(seed=)
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
    def sections(self) -> tuple[HwpxOxmlSection, ...]:
        """Return the sections contained in the document (a tuple, in order)."""
        return tuple(self._root.sections)

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

        The section's part goes too: it is no longer listed in the manifest, and
        a saved file does not keep it (with the section's text) as a stray file.
        Raises ``ValueError`` if the document would have no sections left.
        """
        before = [existing.part_name for existing in self._root.sections]
        self._root.remove_section(section)
        remaining = {existing.part_name for existing in self._root.sections}
        for part_name in before:
            if part_name not in remaining and self.package.has_part(part_name):
                self.package.delete(part_name)

    @property
    def paragraphs(self) -> tuple[HwpxOxmlParagraph, ...]:
        """Return all paragraphs across every section (a tuple, in document order)."""
        return tuple(self._root.paragraphs)

    # ------------------------------------------------------------------
    # editing helpers
    @rejects_removed_arguments
    def add_paragraph(
        self,
        text: str = "",
        *,
        section: int | HwpxOxmlSection | None = None,
        para_pr_id_ref: str | int | None = None,
        style: int | str | Style | None = None,
        char_pr_id_ref: str | int | None = None,
        include_run: bool = True,
        inherit_style: bool | None = None,
    ) -> HwpxOxmlParagraph:
        """Append a paragraph to the document and return it.

        *inherit_style* ``None`` (the default) follows the document: ``True``
        unless it was made with ``HwpxDocument.new(inherit_style=False)``.
        When it is ``True`` and no explicit
        style references are given, the new paragraph inherits
        ``paraPrIDRef``, ``styleIDRef`` and ``charPrIDRef`` from the
        last paragraph in the target section so that consecutive
        paragraphs share the same formatting. A heading is the exception:
        left at ``None``, a paragraph added after an outline paragraph
        (``add_heading``) is body text and does not take the heading's
        paragraph shape and style; pass ``inherit_style=True`` to take them.

        *section* is a section index or a section object (``None``: the last
        section). Formatting references may be overridden via ``para_pr_id_ref``,
        ``style`` and ``char_pr_id_ref``. Anything else is a property of the
        returned paragraph (``p.page_break = True``): 7.0 took away the keyword
        arguments written as raw XML attributes (``pageBreak="1"``) and
        ``run_attributes=``, and a call that still passes one is told so.

        ``style`` 은 스타일을 **이름으로** 지정한다(``style="개요 1"``). 이름은
        **호출 시점에** 해석되고, 못 찾으면 가용 목록과 가장 가까운 이름을 담은
        ``HwpxLookupError`` 가 그 자리에서 난다. 5.x 는 이름을 serialize 시점에만
        해석했고 오타는 저장까지 조용히 통과했다 — 한컴에서 스타일이 안 먹은
        문서가 나오는 경로였다. 숫자 id(``style=2``)와 ``Style`` 객체도 받는다.

        ``style`` 을 주면 문단은 그 스타일의 문단 모양과 글자 모양을 쓴다. 한/글이
        스타일을 적용할 때와 같다. 문단 모양·글자 모양 id 를 함께 주면
        (``para_pr_id_ref``·``char_pr_id_ref``) 그 값이 먼저다.

        7.0에서 ``style_id_ref=``(스타일 이름표만 붙이던 인자)와 ``section_index=`` 가
        없어졌다. 모양은 그대로 두고 이름표만 붙이려면 만든 문단에
        ``paragraph.style_id_ref = 2`` 처럼 쓴다.
        """
        return self._add_paragraph(
            text,
            section=_resolve.resolve_section(self, section, caller="add_paragraph"),
            para_pr_id_ref=para_pr_id_ref,
            style=style,
            char_pr_id_ref=char_pr_id_ref,
            include_run=include_run,
            inherit_style=inherit_style,
        )

    def _add_paragraph(
        self,
        text: str = "",
        *,
        section: int | HwpxOxmlSection | None = None,
        para_pr_id_ref: str | int | None = None,
        style: int | str | Style | None = None,
        char_pr_id_ref: str | int | None = None,
        include_run: bool = True,
        inherit_style: bool | None = None,
        xml_attributes: Mapping[str, str] | None = None,
    ) -> HwpxOxmlParagraph:
        """:meth:`add_paragraph`, plus raw ``hp:p`` attributes (*xml_attributes*) for the
        low-level escape hatches that still take them (``doc.shapes.add_raw``/``add_control``)."""

        if not isinstance(text, str):
            raise HwpxTypeError(
                f"문단 글은 문자열이어야 합니다 — {type(text).__name__} {text!r}.",
                code="paragraph-text-invalid-type",
                context={"type": type(text).__name__},
                suggestion=f"str() 로 바꿔 넘기세요: doc.add_paragraph(str({text!r})).",
            )
        extra = dict(xml_attributes or {})
        resolved_style = self.styles.resolve(style) if style is not None else None
        if resolved_style is not None:
            para_pr_id_ref, char_pr_id_ref = self._style_shapes(
                resolved_style,
                para_pr_id_ref if para_pr_id_ref is not None else extra.get("paraPrIDRef"),
                char_pr_id_ref,
            )
        section = _resolve.resolve_section(self, section, caller="add_paragraph")
        paragraph = self._root._add_paragraph(
            text,
            section=section,
            para_pr_id_ref=para_pr_id_ref,
            style=resolved_style,
            char_pr_id_ref=char_pr_id_ref,
            include_run=include_run,
            inherit_style=self._inherit_style_default if inherit_style is None else inherit_style,
            inherit_outline=inherit_style is not None,
            xml_attributes=extra,
        )
        if include_run:  # a paragraph made to hold an object does not take the first line
            self._take_first_line(paragraph)
        return paragraph

    def _take_first_line(self, paragraph: HwpxOxmlParagraph) -> None:
        """Put *paragraph*, just appended, on the empty first line of a document from :meth:`new`.

        The empty paragraph stays, so a paragraph object taken from it before
        (``doc.paragraphs[0]``) still writes into the document: what was just
        appended (its runs, its paragraph shape and style references) moves
        into it, behind its section settings, and the appended element goes.
        *paragraph* is pointed at the kept element. Only the first paragraph
        added does this, and only while the document is as :meth:`new` made
        it: one paragraph in the first section, without text or objects.
        """

        from .oxml._paragraph_text_edit import blank_settings_paragraph, take_over_paragraph

        if not self._first_line_free:
            return
        self._first_line_free = False
        section = self.sections[0]
        paragraphs = section.paragraphs
        if len(paragraphs) != 2 or paragraphs[1].element is not paragraph.element:
            return
        first = paragraphs[0].element
        if not blank_settings_paragraph(first):
            return  # not the blank paragraph new() makes: leave the document as it is
        take_over_paragraph(first, paragraph.element)
        section.element.remove(paragraph.element)
        paragraph.element = first
        section.mark_dirty()

    def _style_shapes(
        self,
        style: int | str | Style,
        para_pr_id_ref: str | int | None,
        char_pr_id_ref: str | int | None,
    ) -> tuple[str | int | None, str | int | None]:
        """The paragraph and character shapes Hancom applies with *style*, where
        the caller gave none (``oxml.section.style_shape_refs``, which every
        ``add_paragraph(style=)`` uses)."""

        from .oxml.section import style_shape_refs

        _, para_pr_id_ref, char_pr_id_ref = style_shape_refs(self._root, style, para_pr_id_ref, char_pr_id_ref)
        return para_pr_id_ref, char_pr_id_ref

    @rejects_removed_arguments
    def add_heading(
        self,
        text: str = "",
        level: int = 1,
        *,
        style: int | str | Style | None = None,
        section: int | HwpxOxmlSection | None = None,
        char_pr_id_ref: str | int | None = None,
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

        Raises:
            HwpxValueError: *level* 이 1~10 밖이다.
            HwpxLookupError: 이 문서에 해당 개요 스타일이 없다.

        Note:
            ``level=0``(``python-docx`` 의 Title)은 지원하지 않는다. Skeleton에
            "제목" 스타일이 없고, 없는 스타일을 만들어 넣으면 한컴의 개요 번호
            매기기가 그 문단을 세지 않아 번호가 어긋난 문서가 나온다. 문서
            제목에는 ``style=`` 로 그 문서에 실재하는 스타일을 지정한다.
        """

        target = _resolve.resolve_section(self, section, caller="add_heading")
        # the level first: with a style given it was checked after the paragraph was added, and a level
        # that is refused left that paragraph in the document
        _headings._check_level(level)
        resolved = _headings.resolve_heading_style(self, level=level, style=style)
        # Hancom draws a paragraph by its own shapes, not its style's: start from the style's.
        paragraph = self._root.add_paragraph(
            text,
            section=target,
            para_pr_id_ref=resolved.para_pr_id_ref,
            style=resolved,
            char_pr_id_ref=char_pr_id_ref if char_pr_id_ref is not None else resolved.char_pr_id_ref,
            inherit_style=False,
        )
        _headings.bind_outline_level(self, paragraph, level=level)
        self._take_first_line(paragraph)
        return paragraph

    @rejects_removed_arguments
    def add_table(
        self,
        rows: int,
        cols: int,
        *,
        section: int | HwpxOxmlSection | None = None,
        width: int | None = None,
        height: int | None = None,
        border_fill_id_ref: str | int | None = None,
        para_pr_id_ref: str | int | None = None,
        style: int | str | Style | None = None,
        char_pr_id_ref: str | int | None = None,
        inherit_style: bool = False,
        in_margins: "CellMargins | None" = None,
    ) -> HwpxOxmlTable:
        """Create a table in a neutral new paragraph and return it.

        *in_margins* (:class:`~hwpx.objects.CellMargins`, HWPUNIT) sets the table's inner cell margins
        and every cell's ``hp:cellMargin`` (``table.set_in_margins``), checked first.

        A table anchor must not inherit the preceding paragraph's heading or
        list style.  Hancom renders that inherited numbering beside the table
        (for example, a stray ``2.`` after a level-one heading).  Callers that
        intentionally need a styled anchor can pass explicit paragraph/style
        references or set *inherit_style* to :data:`True`.
        """

        for name, value in (("rows", rows), ("cols", cols)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise HwpxTypeError(
                    f"{name} 는 int 여야 합니다 — {type(value).__name__} {value!r}.",
                    code="table-size-invalid",
                    context={"name": name, "value": repr(value)},
                    suggestion="행·열 수는 doc.add_table(2, 3) 처럼 정수로 주세요.",
                )
            if value < 1:
                raise HwpxValueError(
                    f"{name} 는 1 이상이어야 합니다 — {value}.",
                    code="table-size-invalid",
                    context={"name": name, "value": value},
                    suggestion="표는 적어도 1행 1열입니다.",
                )
        section = _resolve.resolve_section(self, section, caller="add_table")
        new_table_width(width, cols)  # checked before a paragraph or a border fill is added
        from .oxml.table_sizes import check_new_table_height, checked_in_margins

        height = check_new_table_height(height)

        checked_in_margins(in_margins)
        paragraph = self.add_paragraph(
            "",
            section=section,
            para_pr_id_ref=para_pr_id_ref,
            style=style,
            char_pr_id_ref=char_pr_id_ref,
            include_run=False,
            inherit_style=inherit_style,
        )
        # after the paragraph, which refuses a style that is not there: the border definition was made
        # first and stayed in the header of a refused call
        resolved_border_fill: str | int | None = border_fill_id_ref
        if resolved_border_fill is None:
            resolved_border_fill = self._root.ensure_basic_border_fill()

        table = paragraph.add_table(
            rows,
            cols,
            width=width,
            height=height,
            border_fill_id_ref=resolved_border_fill,
            char_pr_id_ref=char_pr_id_ref,
            in_margins=in_margins,
        )
        _layout.flow_table_taller_than_page(self, table)
        return table

    @rejects_removed_arguments
    def add_picture(
        self,
        image_data: bytes,
        image_format: str,
        *,
        section: int | HwpxOxmlSection | None = None,
        width: int | None = None,
        height: int | None = None,
        width_mm: float | None = None,
        height_mm: float | None = None,
        alignment: Alignment | str | None = None,
        brightness: int = 0,
        contrast: int = 0,
        effect: str = "REAL_PIC",
        alpha: int = 0,
        line_color: str | None = None,
        line_width_mm: float = 0.12,
        crop: tuple[int, int, int, int] | None = None,
        shadow: PictureShadow | None = None,
        glow: PictureGlow | None = None,
        soft_edge: int | None = None,
        reflection: PictureReflection | None = None,
        para_pr_id_ref: str | int | None = None,
        style: int | str | Style | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> Picture:
        """Embed image data and place a picture object in a new paragraph.

        *alignment* (``LEFT``, ``CENTER`` or ``RIGHT``) places the picture in its line. *brightness* and
        *contrast* (-100 to 100), *effect* (``REAL_PIC``, ``GRAY_SCALE`` or ``BLACK_WHITE``) and *alpha*
        (transparency, 0 opaque to 255 not drawn) adjust the image; *line_color* (with *line_width_mm*, mm)
        gives it a solid border. *crop* ``(left, top, right, bottom)`` cuts that much (HWPUNIT) from the sides
        of the *width* x *height* picture, keeping its scale. *shadow* (``hwpx.oxml.PictureShadow``) and *glow*
        (``hwpx.oxml.PictureGlow``) draw a shadow and a glow; *soft_edge* (HWPUNIT) fades its edge and
        *reflection* (``hwpx.oxml.PictureReflection``) reflects it below.

        7.0: ``align=`` is ``alignment=``, ``line_width=`` (HWPUNIT) is ``line_width_mm=`` (mm, the default
        0.12 mm is the 33 HWPUNIT 6.x wrote), and ``run_attributes=`` and the raw XML attribute keywords are
        gone; a call that still passes one is told the new name."""

        section = _resolve.resolve_section(self, section, caller="add_picture")
        return _media.add_picture(
            self,
            image_data=image_data,
            image_format=image_format,
            section=section,
            width=width,
            height=height,
            width_mm=width_mm,
            height_mm=height_mm,
            alignment=None if alignment is None else str(alignment),
            brightness=brightness,
            contrast=contrast,
            effect=effect,
            alpha=alpha,
            line_color=line_color,
            line_width_mm=line_width_mm,
            crop=crop,
            shadow=shadow,
            glow=glow,
            soft_edge=soft_edge,
            reflection=reflection,
            para_pr_id_ref=para_pr_id_ref,
            style=style,
            char_pr_id_ref=char_pr_id_ref,
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
    # Where Hangul opens the document (settings.xml's caret)
    # ------------------------------------------------------------------

    @property
    def caret(self) -> "CaretPosition | None":
        """Where Hangul puts the caret when it opens the document (``settings.xml``'s ``ha:CaretPosition``):
        ``list_id_ref`` (``0`` is the body, every section's paragraphs in one row), ``para_id_ref`` and ``pos``
        counted as Hangul counts a paragraph (a control or an object eight). ``None`` without one; Hangul then
        opens at the body's start."""

        from .oxml.caret import read_caret

        return read_caret(self._root)

    def set_caret(self, paragraph: "HwpxOxmlParagraph", offset: int = 0) -> "CaretPosition":
        """Put the caret at character *offset* of *paragraph* -- a paragraph of the body (``doc.paragraphs``);
        a cell's, a text box's or a note's list is refused (``document-caret-place-unsupported``): the documents Hangul
        saved do not settle their list numbers. The caret goes after the controls and objects at *offset*, where
        text put there goes."""

        from .oxml.caret import set_caret

        return set_caret(self._root, paragraph, offset)

    def reset_caret(self) -> "CaretPosition":
        """Put the caret at the start of the body's first paragraph's text, where Hangul opens a document whose
        caret points at nothing (``listIDRef 0, paraIDRef 0``, ``pos`` after the section's settings and columns:
        16 in a new document). A document built from a template keeps the template's caret until this is
        called. On saving, a caret pointing at a body paragraph that is gone is put there by itself."""

        from .oxml.caret import reset_caret

        return reset_caret(self._root)

    # ------------------------------------------------------------------
    # Export helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> "ValidationReport":
        """Validate the current document state, as ``hwpx-validate`` does.

        Checks the header and section XML against the schemas and warns
        about manifest items with no part and ``BinData/`` parts with no
        manifest item. Returns a :class:`~hwpx.tools.validator.ValidationReport`.
        Package structure (ZIP, container, manifest hrefs) is checked by
        :func:`~hwpx.tools.package_validator.validate_package`. This does
        **not** require ``validate_on_save`` to be enabled.
        """

        return _persistence.validate(self)

    def _run_open_safety_validation(self, archive_bytes: bytes) -> "EditorOpenSafetyReport | None":
        """Raise if generated bytes are unsafe to hand to an HWPX editor; else return the report."""

        return _persistence._run_open_safety_validation(
            self,
            archive_bytes=archive_bytes,
        )

    def save(
        self,
        target: str | PathLike[str] | BinaryIO,
        *,
        format: SaveFormat | None = None,
        mode: Mode = "auto",
        fallback: Fallback = "error",
        quality: QualityPolicy | None = None,
        pipeline: SavePipeline | None = None,
    ) -> MutationReport:
        """Save pending changes to *target* — a file path or a writable binary stream —
        and return the :class:`~hwpx.mutation_report.MutationReport` receipt.

        A stream must be seekable (``tell``/``seek``) and readable from its position, or already at its
        end; the document is written at that position and the stream is cut (``truncate``) where the
        document ends, so a stream that held something longer opens as the new document (a stream that
        cannot be cut short is refused and left as it was). A write-only stream raises ``OSError``: save
        to a path instead.

        ``report.path`` is the path written (``None`` for a stream), and
        ``report.editor_open_safety`` the editor-open safety report the save reached for
        what it wrote (``validate_editor_open_safety`` of those bytes, not run again). *format* ``None``
        writes HWP 5.0 to a path ending in ``.hwp`` and HWPX otherwise, a stream
        included; ``format="hwp"`` or ``"hwpx"`` says it outright. HWPX to a name not
        ending in ``.hwpx`` warns unless ``format="hwpx"`` is given (a ``.hwp`` name
        warns even then). ``mode="patch"``
        with ``fallback="error"`` raises
        :class:`~hwpx.mutation_report.PreservationDowngradeError` and writes nothing
        when an untouched part would not stay byte-identical.

        *quality* (a :class:`~hwpx.quality.QualityPolicy`, e.g.
        ``QualityPolicy.strict()``) runs that quality gate before the write and puts
        its :class:`~hwpx.quality.VisualCompleteReport` in ``report.quality``. A gate
        that refuses the archive writes nothing and raises
        :class:`~hwpx.errors.SaveError` (``quality-gate-failed``) whose ``.report`` is
        the gate's report. For a gate run without writing, or with ``before=``/
        ``edit_mask=``/``ledger=``, use ``SavePipeline().run(doc.to_bytes(), ...)``.

        *pipeline* (a :class:`~hwpx.quality.SavePipeline`) is the gate the save runs
        through instead of a plain ``SavePipeline()`` — the way to give the gate a
        renderer, e.g. ``pipeline=SavePipeline(oracle_factory=make_backend)``. The
        factory is called only when *quality* renders (``render_check`` not ``"off"``);
        without *quality* the gate is transparent and the pipeline renders nothing.
        Everything else is the same save: one open-safety check, the same bytes,
        ``.hwp`` targets, the receipt, and on refusal nothing written and the
        document left unsaved.

        7.0 folded ``save_to_path``, ``save_to_stream`` and ``save_report`` into this
        one verb; :meth:`to_bytes` returns the bytes.
        """

        return _persistence.save(
            self,
            target,
            format=format,
            mode=mode,
            fallback=fallback,
            quality=quality,
            pipeline=pipeline,
        )

    def to_bytes(
        self,
        *,
        mode: Mode = "auto",
        fallback: Fallback = "error",
        format: SaveFormat = "hwpx",
    ) -> bytes:
        """Serialize pending changes and return the HWPX archive as bytes.

        ``mode="patch"`` with ``fallback="error"`` raises
        :class:`~hwpx.mutation_report.PreservationDowngradeError` before
        returning when the archive is not patch-grade; the byte return itself is
        unchanged. ``format="hwp"`` returns an HWP 5.0 file instead.
        """

        return _persistence.to_bytes(self, mode=mode, fallback=fallback, format=format)

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


# The guide for 6.x names 7.0 renamed or removed on the model and value-type classes
# (hwpx._removed_names): the classes all exist once this module has loaded.
_install_removed_name_hints()
