# SPDX-License-Identifier: Apache-2.0
"""`doc.parts` — OPC 파트 접근(`header.xml`·바탕쪽·이력·버전).

## 왜 이 네임스페이스가 생겼나 — 이름 충돌 해소

5.x의 `doc.headers`는 **쪽 머리말이 아니라** `Contents/header.xml` 파트 목록
이었다. 그런데 같은 객체에 `set_header_text`·`remove_header`가 나란히 있어서,
`doc.headers`를 쪽 머리말로 읽는 것이 자연스러웠다. 이름 하나가 두 가지를
가리키는 상태였다.

6.0은 둘을 갈라 놓는다:

- `doc.parts.headers` — 스타일·문단모양 등 **정의가 사는 파트**
- `doc.page.set_header(...)` — 인쇄되는 **쪽 머리말**

`doc.version` 도 같은 부류였다. 그건 라이브러리 버전(`hwpx.__version__`)이
아니라 패키지의 `version.xml` 파트다.
"""

from __future__ import annotations

import struct
import zlib
from types import ModuleType
from datetime import datetime
from typing import TYPE_CHECKING, Iterable

from ...errors import HwpxTypeError, HwpxValueError
from ...oxml._document_primitives import _HH
from ...oxml.header_compat import (
    apply_paragraph_auto_spacing as _apply_paragraph_auto_spacing,
    remove_license_mark as _remove_license_mark,
    set_compatible_document_target_program as _set_compatible_document_target_program,
    set_doc_option_link_info as _set_doc_option_link_info,
    set_layout_compatibility_flags as _set_layout_compatibility_flags,
    set_license_mark as _set_license_mark,
)
from ...oxml import (
    HwpxOxmlHeader,
    HwpxOxmlHistory,
    HwpxOxmlMasterPage,
    HwpxOxmlSection,
    HwpxOxmlSettings,
    HwpxOxmlVersion,
)
from ...objects.results import BeginNumbers, DocumentOptions
from .._resolve import resolve_section
from ._base import _LazyModule, _Namespace

# Named in an annotation only; loaded when the hint is resolved (``import hwpx`` stays light).
def _load_document_metadata() -> ModuleType:
    from ...oxml import document_metadata

    return document_metadata


if TYPE_CHECKING:
    from ...oxml import document_metadata as _document_metadata
else:
    _document_metadata = _LazyModule(_load_document_metadata)

__all__ = ["PartsNamespace"]

_PREVIEW_TEXT_PART = "Preview/PrvText.txt"
_PREVIEW_IMAGE_PART = "Preview/PrvImage.png"


def _png_chunk(tag: bytes, body: bytes) -> bytes:
    crc = zlib.crc32(tag + body) & 0xFFFFFFFF
    return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", crc)


def _master_page_by_id(
    master_pages: "Iterable[HwpxOxmlMasterPage]", master_page_id: str
) -> "HwpxOxmlMasterPage":
    """The master page part ``add_master_page`` just made under *master_page_id* (its element and manifest
    item carry the same id)."""

    for master_page in master_pages:
        if master_page.id == master_page_id:
            return master_page
    from ...errors import HwpxLookupError

    raise HwpxLookupError(  # pragma: no cover - add_master_page registers the part it makes
        f"the new master page {master_page_id!r} is not among the document's master pages",
        code="master-page-not-found",
        context={"requested": master_page_id},
    )


#: `clear_preview`가 `Preview/PrvImage.png` 자리에 넣는 1×1 흰 RGB PNG.
_NEUTRAL_PREVIEW_PNG = (
    b"\x89PNG\r\n\x1a\n"
    + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    + _png_chunk(b"IDAT", zlib.compress(b"\x00" + b"\xff\xff\xff"))
    + _png_chunk(b"IEND", b"")
)


class PartsNamespace(_Namespace):
    """OPC 파트 접근 — `header.xml`·바탕쪽·이력·버전."""

    __slots__ = ()
    _path = "doc.parts"

    @property
    def headers(self) -> tuple["HwpxOxmlHeader", ...]:
        """문서가 참조하는 `Contents/header.xml` 파트들.

        쪽 머리말이 아니다 — 그쪽은 `doc.page.set_header(...)`.
        """

        return self._doc.oxml.headers

    @property
    def master_pages(self) -> tuple["HwpxOxmlMasterPage", ...]:
        """매니페스트가 선언한 바탕쪽 파트들. `.to_model()`로 `MasterPage`를
        얻는다. 실코퍼스 1파일 역설계 기반(`hwpx.oxml.master_page` 모듈
        독스트링 참조) — 스키마 문서의 루트 네임스페이스는 실 산출물과
        다르다."""

        return self._doc.oxml.master_pages

    def add_master_page(
        self,
        *,
        text: str | None = None,
        page_type: str = "OPTIONAL_PAGE",
        page_number: int | None = None,
        page_duplicate: bool = False,
        page_front: bool = False,
        section: "int | HwpxOxmlSection | None" = None,
    ) -> "HwpxOxmlMasterPage":
        """새 바탕쪽 파트를 만들고 :attr:`master_pages` 가 읽는 ``MasterPage`` 를 돌려준다(id 는 ``.id``).

        6.13 트레인㊻ — 편집기 메뉴 표면 역매핑이 [부분 대응](읽기만,
        쓰기 없음)으로 지목한 갭. *section* 을 주지 않으면 파트만 만든다 — 어느
        절에서도 참조하지 않는다. 쓰려면 ``doc.page.set_master_page(mp, section=...)`` 로 잇는다.
        저장할 때까지 어느 절에도 잇지 않으면 저장이 ``HwpxValueError``(``master-page-unlinked``)로
        거부된다 — 한/글은 어느 절도 가리키지 않는 바탕쪽 파트를 버린다(한/글 2024에서 열고 다시 저장해 확인).
        바탕쪽의 글은 *text* (첫 문단)로 주고, 문단을 더 넣으려면 ``mp.add_paragraph("...")``.

        기본 ``page_type="OPTIONAL_PAGE"``는 ``page_number``(그 쪽 번호, 주지 않으면 1)
        한 쪽에만 나온다. 모든 쪽이면 ``"BOTH"``, 홀수·짝수 쪽만이면 ``"ODD"``·
        ``"EVEN"``을 준다. 이 종류들은 ``page_number``를 주지 않으면 0을 쓴다. 한
        절에는 같은 쪽의 바탕쪽을 하나만 둘 수 있어서, 이미 있는 종류의 바탕쪽을
        절에 연결하면 ``HwpxValueError``가 난다.

        실측(유일한 실 예시): 절의 `hp:secPr` 자식 시퀀스에서
        `hp:masterPage`는 맨 끝에 오고, `masterPageCnt`가 그 개수와
        일치한다. 실한컴 렌더 검증은 v17 배치 대기(Create(experimental)).

        *section*(절 객체 또는 인덱스)을 주면 만든 바탕쪽을 그 절에 바로
        연결한다. 그 절에 같은 쪽의 바탕쪽이 이미 있으면 파트를 만들기 전에
        ``HwpxValueError``(``master-page-pages-taken``)를 내므로, 거부된
        호출은 문서에 아무것도 남기지 않는다.
        """

        target = (
            resolve_section(self._doc, section, caller="doc.parts.add_master_page")
            if section is not None
            else None
        )
        master_page_id = self._doc.oxml.add_master_page(
            text=text,
            page_type=page_type,
            page_number=page_number,
            page_duplicate=page_duplicate,
            page_front=page_front,
            section=target,
        )
        return _master_page_by_id(self._doc.oxml.master_pages, master_page_id)

    def remove_master_page(self, master_page_id: "str | HwpxOxmlMasterPage") -> None:
        """어느 절도 참조하지 않는 바탕쪽(id 나 ``MasterPage``)을 문서에서 지운다.

        매니페스트 항목과 파트를 함께 지운다. 이미 저장된 적이 있어 패키지에
        파트 파일이 있으면 그 파일도 지운다. 없는 id는
        ``HwpxLookupError``(``master-page-not-found``), 아직 어떤 절이
        참조하는 바탕쪽은 ``HwpxValueError``(``master-page-in-use``)로
        거부한다. 거부되면 아무것도 바뀌지 않는다. 구역과의 연결만 끊는 것은
        ``doc.page.remove_master_page_reference``.
        """

        from ...oxml.master_page_authoring import remove_master_page as _remove_master_page

        if isinstance(master_page_id, HwpxOxmlMasterPage):
            master_page_id = master_page_id.id or ""
        part_name = _remove_master_page(self._doc.oxml, master_page_id)
        package = self._doc.package
        if package.has_part(part_name):
            package.delete(part_name)

    @property
    def histories(self) -> tuple["HwpxOxmlHistory", ...]:
        """매니페스트가 참조하는 문서 이력 파트들. `.to_model()`로
        `History`를 얻는다. **스키마 전용**: 실코퍼스 0건이라
        (`hwpx.oxml.history_part` 모듈 독스트링 참조) 상세 필드는 실 문서로
        검증되지 않았다."""

        return self._doc.oxml.histories

    @property
    def version(self) -> "HwpxOxmlVersion | None":
        """패키지의 `version.xml` 파트. 라이브러리 버전이 아니다.
        `.to_model()`로 `HcfVersion`을 얻는다. 실코퍼스 47/47 전수 역설계
        기반(`hwpx.oxml.version_part` 모듈 독스트링 참조)."""

        return self._doc.oxml.version

    @property
    def settings(self) -> "HwpxOxmlSettings | None":
        """패키지의 `settings.xml` 파트(`ha:HWPApplicationSetting` — 커서
        위치·인쇄 설정 등). 읽기 전용: `.to_model()`로 `ApplicationSettings`
        를 얻는다. 스키마 미선언 파트라 실코퍼스 역설계 기반이다
        (`hwpx.oxml.settings` 모듈 독스트링 참조)."""

        return self._doc.oxml.settings

    @property
    def metadata(self) -> "_document_metadata.DocumentMetadata | None":
        """``Contents/content.hpf``의 ``opf:metadata`` 스냅샷(제목·작성자·
        주제·키워드·작성일·수정일 등). 실코퍼스 67파일 전수 역설계 기반
        (`hwpx.oxml.document_metadata` 모듈 독스트링 참조). `None`이면
        이 파트에 metadata 블록 자체가 없다(실측상 65/67은 있음)."""

        return self._doc.package.document_metadata()

    def set_document_metadata(
        self,
        *,
        title: str | None = None,
        creator: str | None = None,
        subject: str | None = None,
        keyword: str | None = None,
        created_date: str | None = None,
        modified_date: str | None = None,
        description: str | None = None,
        lastsaveby: str | None = None,
        date: "datetime | str | None" = None,
    ) -> None:
        """``opf:metadata``의 제목/만든 사람/주제/키워드/만든 날짜/고친 날짜/설명/마지막 저장한
        사람/사람이 읽는 날짜를 쓴다 — 생략(`None`)한 칸은 그대로 두고, `""`를 주면 그 칸을 비운다
        (요소와 ``content="text"``는 남는다). `language`는 쓰지 않는다.

        `created_date`/`modified_date`는 이미 포맷된 ISO 8601 문자열을 받는다
        (`"%Y-%m-%dT%H:%M:%SZ"`, 실코퍼스 100% 일관 관측) — 이 함수가 포맷을 강제하지 않는다.

        `date`(사람이 읽는 만든 날짜)는 시간대가 있는 `datetime`을 받아 한/글의 꼴(한국 시각
        ``2025년 9월 17일 수요일 오후 1:32:50``, :func:`hwpx.oxml.document_metadata.hangul_date_text`)로
        쓴다. `CreatedDate`와 같은 순간을 주면 한/글이 쓰는 것처럼 둘이 같은 때를 가리킨다. `""`는
        비운다. 그 밖의 문자열은 거부한다(``parts-date-invalid-type``) — 근거로 정한 꼴 밖의 날짜
        글은 쓰지 않는다. 시간대 없는 `datetime`은 ``parts-date-naive``다.

        양식에서 온 사람 이름(`creator`·`lastsaveby`)을 한 번에 지우려면 `clear_document_authors`,
        모든 칸을 비우려면 `clear_document_metadata`를 쓴다."""

        date_text: str | None
        if date is None:
            date_text = None
        elif isinstance(date, str) and date == "":
            date_text = ""
        elif isinstance(date, str):
            raise HwpxTypeError(
                "set_document_metadata(date=) takes a datetime (written in Hangul's form) or \"\" to clear "
                f"it, not the text {date!r}",
                code="parts-date-invalid-type",
                context={"type": "str"},
                suggestion="pass datetime.now(timezone.utc), or doc.package.set_document_metadata(date=...) "
                "to write a text as it is",
            )
        else:
            from ...oxml.document_metadata import hangul_date_text

            date_text = hangul_date_text(date)
        self._doc.package.set_document_metadata(
            title=title,
            creator=creator,
            subject=subject,
            keyword=keyword,
            created_date=created_date,
            modified_date=modified_date,
            description=description,
            lastsaveby=lastsaveby,
            date=date_text,
        )

    def clear_document_authors(self) -> tuple[str, ...]:
        """문서 정보의 사람 이름 — 만든 사람(``creator``)과 마지막 저장한 사람(``lastsaveby``) —
        을 비우고, 비운 칸을 문서 순서대로 돌려준다(값이 있던 칸만).

        양식에서 따라온 이름을 걷는 한 번의 호출이다. 요소와 ``content="text"``는 두고 내용만
        비운다(한/글이 이름 없는 문서를 쓰는 꼴). 같은 이름의 칸이 둘 이상이면(한/글은 이렇게 쓰지
        않는다) 모두 비우고, 값이 있던 칸마다 이름을 하나씩 돌려준다(``("creator", "creator",
        "lastsaveby")``). 없는 요소는 만들지 않고, metadata 블록이 없으면 ``()``다. 제목·주제·설명·
        키워드와 날짜는 그대로다."""

        return tuple(self._doc.package._clear_named_meta(("creator", "lastsaveby")))

    def clear_document_metadata(
        self,
        *,
        keep: Iterable[str] = ("title", "language"),
        timestamp: str = "1970-01-01T00:00:00Z",
    ) -> tuple[str, ...]:
        """``opf:metadata``에서 *keep* 밖의 필드를 모두 비우고, 비운 키를
        문서 순서대로 돌려준다.

        키는 ``opf:meta``면 ``name`` 속성, 그 밖의 요소면 로컬 이름
        (``title``·``language``)이다. 이 라이브러리가 모르는 ``opf:meta``
        이름도 비운다 — 호출자가 모르는 메타데이터가 남지 않게 하려는
        것이다. 이름에 ``"Date"``가 든 ``opf:meta``(``CreatedDate``·
        ``ModifiedDate``)에는 *timestamp*를 넣고, 나머지는 요소와 속성
        (``content="text"`` 등)을 두고 내용만 비운다. 자유형식 ``date``는
        비울 뿐 timestamp를 넣지 않는다. 없는 요소는 만들지 않고, metadata
        블록이 없으면 ``()``다. 무엇을 지울지(개인정보 정책)는 호출자가
        정한다."""

        return tuple(self._doc.package.clear_document_metadata(keep=keep, timestamp=timestamp))

    def clear_preview(self) -> tuple[str, ...]:
        """패키지에 저장된 미리 보기를 비우고, 바꾼 파트 이름을 돌려준다.

        ``Preview/PrvText.txt``가 있으면 빈 바이트로 덮어쓴다. 지우지 않는
        까닭은 ``META-INF/container.xml``이 보통 이 파트를 rootfile로
        선언하기 때문이다. ``Preview/PrvImage.png``가 있으면 1×1 흰 PNG로
        바꾼다. 이 그림에는 본문 내용이 보일 수 있다. 이것도 지우지 않고
        바꿔서 패키지의 파트 구성을 유지한다. 없는 파트는 만들지 않는다.
        다른 확장자의 미리 보기 파트(예: ``PrvImage.bmp``)는 건드리지
        않는다."""

        package = self._doc.package
        changed: list[str] = []
        for part_name, payload in (
            (_PREVIEW_TEXT_PART, b""),
            (_PREVIEW_IMAGE_PART, _NEUTRAL_PREVIEW_PNG),
        ):
            if package.has_part(part_name):
                package.write(part_name, payload)
                changed.append(part_name)
        return tuple(changed)

    def _primary_header(self) -> "HwpxOxmlHeader":
        headers = self._doc.oxml.headers
        if not headers:
            raise HwpxValueError(
                "document has no header.xml part",
                code="parts-no-header-part",
                suggestion="This document is missing Contents/header.xml entirely.",
            )
        return headers[0]

    # ------------------------------------------------------------------
    # 6.6 트레인㉓ — 문서 옵션·호환성 저작(가산). 읽기 쪽(c38bf07)이 이미
    # LayoutCompatibility/CompatibleDocument를 스냅샷 모델로 노출했으니,
    # 이 자리는 그 대응 쓰기 표면이다. 자세한 실코퍼스 근거는
    # `hwpx.oxml.header_compat` 모듈 독스트링 참조 — `HwpxOxmlHeader`가
    # 자기 owner 파일(header_part.py)의 1600줄 캡에 헤드룸이 없어(측정
    # 1599/1600) 새 모듈에 자유함수로 산다.
    # ------------------------------------------------------------------

    @property
    def document_options(self) -> "DocumentOptions":
        """문서 옵션·호환 설정(``hh:compatibleDocument``·``hh:docOption``)의 읽기 값.

        :meth:`set_document_options` 가 쓰는 값을 같은 필드 이름으로 읽는다.
        """

        from ...objects.results import DocumentOptions

        model = self._primary_header().to_model()
        compatible = model.compatible_document
        option = model.doc_option
        link = option.link_info if option is not None else None
        mark = option.license_mark if option is not None else None
        flags = (
            compatible.layout_compatibility.flags
            if compatible is not None and compatible.layout_compatibility is not None
            else frozenset()
        )
        return DocumentOptions(
            target_program=compatible.target_program if compatible is not None else None,
            layout_compatibility=tuple(sorted(flags)),
            link_path=link.path if link is not None else "",
            page_inherit=bool(link.page_inherit) if link is not None else False,
            footnote_inherit=bool(link.footnote_inherit) if link is not None else False,
            license_type=mark.type if mark is not None else None,
            license_flag=mark.flag if mark is not None else None,
            license_lang=mark.lang if mark is not None else None,
        )

    @property
    def begin_numbers(self) -> "BeginNumbers":
        """문서 전체의 시작 번호(``hh:beginNum``): 쪽·각주·미주·그림·표·수식."""

        from ...objects.results import BeginNumbers

        value = self._primary_header().begin_numbering
        return BeginNumbers(
            page=value.page,
            footnote=value.footnote,
            endnote=value.endnote,
            picture=value.picture,
            table=value.table,
            equation=value.equation,
        )

    def set_begin_numbers(
        self,
        *,
        page: int | None = None,
        footnote: int | None = None,
        endnote: int | None = None,
        picture: int | None = None,
        table: int | None = None,
        equation: int | None = None,
    ) -> None:
        """문서 전체의 시작 번호를 바꾼다. 주지 않은 값은 그대로 둔다(1..65535)."""

        for name, value in (("page", page), ("footnote", footnote), ("endnote", endnote),
                            ("picture", picture), ("table", table), ("equation", equation)):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 0xFFFF):
                raise HwpxValueError(
                    f"{name} 는 1..65535 의 정수여야 합니다 — {value!r}.",
                    code="parts-begin-numbers-invalid",
                    context={"argument": name, "value": repr(value)},
                    suggestion=f"{name}= 에 1 이상의 정수를 주세요.",
                )
        self._primary_header().set_begin_numbering(
            page=page, footnote=footnote, endnote=endnote, picture=picture, table=table, equation=equation
        )

    def set_document_options(
        self,
        *,
        target_program: str | None = None,
        layout_compatibility: Iterable[str] | None = None,
        link_path: str | None = None,
        page_inherit: bool | None = None,
        footnote_inherit: bool | None = None,
        license_type: str | None = None,
        license_flag: int | None = None,
        license_lang: int | None = None,
    ) -> "DocumentOptions":
        """문서 옵션·호환 설정을 바꾸고, 바꾼 뒤의 :attr:`document_options` 를 돌려준다.

        인자 이름은 :attr:`document_options` (``DocumentOptions``)의 필드 이름 그대로이고, 주지 않은
        (``None``) 값은 그대로 둔다.

        - *target_program*: ``hh:compatibleDocument/@targetProgram``. 실코퍼스 47/47이 ``"HWP201X"``만
          관측(다른 값의 실증은 없음 — 값을 강제하지 않는다).
        - *layout_compatibility*: ``hh:compatibleDocument/hh:layoutCompatibility`` 의 플래그 자식을 이것으로
          바꾼다. 실코퍼스 47/47은 플래그 0개 — 스키마가 선언한 48종 중 실사용 관측 0건(빈 이터러블이 코퍼스 전형).
        - *link_path*·*page_inherit*·*footnote_inherit*: ``hh:docOption/hh:linkinfo`` 의 ``path``·
          ``pageInherit``·``footnoteInherit``. 실코퍼스: ``path``는 항상 빈 문자열·``footnoteInherit``는 항상
          ``"0"``, ``pageInherit``만 실제로 갈린다(8/47 ``"1"``).
        - *license_type*·*license_flag*·*license_lang*: ``hh:docOption/hh:licensemark`` ("입력 > CCL 넣기…"가
          남기는 문서 수준 라이선스 레코드). 실측 gold는 ``type="CCL" flag="0" lang="6"`` — 스키마가
          ``type``을 ``xs:unsignedInt``로 선언하는데도 실물은 문자열이다. 레코드가 없을 때 새로 쓰려면
          *license_type* 과 *license_flag* 가 함께 있어야 한다(``parts-license-mark-incomplete``). 있는
          레코드에서는 주지 않은 값이 그대로 남는다(*license_lang* 도). 눈에
          보이는 CC 배지는 별개다 — 라이선스 증서 URL을 ``href``로 단 평범한 그림(``add_picture``)이다.
          레코드를 지우는 것은 :meth:`remove_license_mark`.

        값이 하나도 없으면 아무것도 바꾸지 않는다.
        """

        header = self._primary_header()
        # Every value is checked before anything changes.
        if target_program is not None and not target_program:
            raise HwpxValueError(
                "target_program must be a non-empty string",
                code="header-compat-empty-target-program",
                context={"target_program": target_program},
                suggestion='Pass the observed real-corpus value, e.g. "HWP201X".',
            )
        flags = None if layout_compatibility is None else tuple(layout_compatibility)
        if flags is not None and not all(flags):
            raise HwpxValueError(
                "layout compatibility flag names must be non-empty strings",
                code="header-compat-empty-flag-name",
                suggestion="Drop the empty entry, or pass layout_compatibility=() to clear all flags.",
            )
        license_mark: tuple[str, int, int | None] | None = None
        if license_type is not None or license_flag is not None or license_lang is not None:
            current = self.document_options
            mark_type = license_type if license_type is not None else current.license_type
            flag = license_flag if license_flag is not None else current.license_flag
            if mark_type is None or flag is None:
                raise HwpxValueError(
                    "a new license mark needs license_type and license_flag",
                    code="parts-license-mark-incomplete",
                    context={"license_type": repr(license_type), "license_flag": repr(license_flag)},
                    suggestion='Pass both, e.g. set_document_options(license_type="CCL", license_flag=0).',
                )
            if not mark_type:
                raise HwpxValueError(
                    "license_type must be a non-empty string",
                    code="header-compat-empty-license-mark-type",
                    context={"license_type": mark_type},
                    suggestion='Pass the observed real-Hancom value, e.g. "CCL".',
                )
            license_mark = (str(mark_type), int(flag), license_lang if license_lang is not None else current.license_lang)
        if target_program is not None:
            _set_compatible_document_target_program(header, target_program)
        if flags is not None:
            _set_layout_compatibility_flags(header, flags)
        if link_path is not None or page_inherit is not None or footnote_inherit is not None:
            _set_doc_option_link_info(
                header, path=link_path, page_inherit=page_inherit, footnote_inherit=footnote_inherit
            )
        if license_mark is not None:
            _set_license_mark(header, mark_type=license_mark[0], flag=license_mark[1], lang=license_mark[2])
        return self.document_options

    def remove_license_mark(self) -> bool:
        """`hh:docOption/hh:licensemark`를 지운다. 실제로 지웠으면 True."""

        return _remove_license_mark(self._primary_header())

    def set_paragraph_auto_spacing(
        self,
        para_pr_id_ref: str | int,
        *,
        e_asian_eng: bool | None = None,
        e_asian_num: bool | None = None,
    ) -> None:
        """*para_pr_id_ref*가 가리키는 `hh:paraPr`의 `hh:autoSpacing`(한글·영문/
        숫자 자동 간격)을 설정. `_apply_paragraph_margins`/
        `_apply_paragraph_line_spacing`과 같은 자손-순회 관용구를 쓰지만,
        margin/lineSpacing과 달리 실 autoSpacing은 hp:switch로 감싸이지
        않는다(실코퍼스 1832/1832 전부 hh:paraPr 직속 자식, 0건 중첩 —
        `hwpx.oxml.header_compat` 모듈독스트링 참조)."""

        header = self._primary_header()
        para_properties = header._para_properties_element(create=False)
        para_pr = None
        if para_properties is not None:
            for candidate in para_properties.findall(f"{_HH}paraPr"):
                if header._id_matches(candidate.get("id"), para_pr_id_ref):
                    para_pr = candidate
                    break
        if para_pr is None:
            raise HwpxValueError(
                f"no hh:paraPr with id={para_pr_id_ref!r}",
                code="parts-auto-spacing-unknown-para-pr",
                context={"para_pr_id_ref": para_pr_id_ref},
                suggestion="Pass an id returned by ensure_paragraph_format or an existing paraPr's id.",
            )
        _apply_paragraph_auto_spacing(
            header, para_pr, e_asian_eng=e_asian_eng, e_asian_num=e_asian_num
        )
