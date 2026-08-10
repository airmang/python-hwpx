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

from typing import TYPE_CHECKING, Iterable

from ...errors import HwpxValueError
from ...oxml._document_primitives import _HH
from ...oxml.header_compat import (
    apply_paragraph_auto_spacing as _apply_paragraph_auto_spacing,
    set_compatible_document_target_program as _set_compatible_document_target_program,
    set_doc_option_link_info as _set_doc_option_link_info,
    set_layout_compatibility_flags as _set_layout_compatibility_flags,
)
from ._base import _Namespace

if TYPE_CHECKING:
    from ...oxml import (
        HwpxOxmlHeader,
        HwpxOxmlHistory,
        HwpxOxmlMasterPage,
        HwpxOxmlSettings,
        HwpxOxmlVersion,
    )
    from ...oxml.document_metadata import DocumentMetadata

__all__ = ["PartsNamespace"]


class PartsNamespace(_Namespace):
    """OPC 파트 접근 — `header.xml`·바탕쪽·이력·버전."""

    __slots__ = ()
    _path = "doc.parts"

    @property
    def headers(self) -> list["HwpxOxmlHeader"]:
        """문서가 참조하는 `Contents/header.xml` 파트들.

        쪽 머리말이 아니다 — 그쪽은 `doc.page.set_header(...)`.
        """

        return self._doc.oxml.headers

    @property
    def master_pages(self) -> list["HwpxOxmlMasterPage"]:
        """매니페스트가 선언한 바탕쪽 파트들. `.to_model()`로 `MasterPage`를
        얻는다. 실코퍼스 1파일 역설계 기반(`hwpx.oxml.master_page` 모듈
        독스트링 참조) — 스키마 문서의 루트 네임스페이스는 실 산출물과
        다르다."""

        return self._doc.oxml.master_pages

    def add_master_page(
        self,
        *,
        text: str | None = None,
        paragraphs: Iterable[str] | None = None,
        page_type: str = "OPTIONAL_PAGE",
        page_number: int = 1,
        page_duplicate: bool = False,
        page_front: bool = False,
    ) -> str:
        """새 바탕쪽 파트를 만들고, 그 id(``"masterpageN"``)를 돌려준다.

        6.13 트레인㊻ — 편집기 메뉴 표면 역매핑이 [부분 대응](읽기만,
        쓰기 없음)으로 지목한 갭. 이 메서드는 파트만 만든다 — 어느
        절에서도 참조하지 않는다. 실제로 쓰려면
        ``section.properties.add_master_page_reference(id)``를 호출할
        것(``doc.oxml.sections[i].properties``).

        실측(유일한 실 예시): 절의 `hp:secPr` 자식 시퀀스에서
        `hp:masterPage`는 맨 끝에 오고, `masterPageCnt`가 그 개수와
        일치한다. 실한컴 렌더 검증은 v17 배치 대기(Create(experimental)).
        """

        return self._doc.oxml.add_master_page(
            text=text,
            paragraphs=list(paragraphs) if paragraphs is not None else None,
            page_type=page_type,
            page_number=page_number,
            page_duplicate=page_duplicate,
            page_front=page_front,
        )

    @property
    def histories(self) -> list["HwpxOxmlHistory"]:
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
    def metadata(self) -> "DocumentMetadata | None":
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
    ) -> None:
        """``opf:metadata``의 제목/작성자/주제/키워드/작성일/수정일을
        설정한다(6.12 트레인㊸) — 생략(`None`)한 필드는 그대로 둔다.
        `date`(사람이 읽는 자유형식 날짜)·`description`·`lastsaveby`·
        `language`는 저작 대상 밖이다(`date`는 특히 실코퍼스가 최소
        5가지 서로 다른 포맷을 씀 — 단일 정본이 없어 저작하면 무근거
        포맷 추정이 된다, `hwpx.oxml.document_metadata` 참조).
        `created_date`/`modified_date`는 이미 포맷된 ISO 8601 문자열을
        받는다(`"%Y-%m-%dT%H:%M:%SZ"`, 실코퍼스 100% 일관 관측) — 이
        함수가 포맷을 강제하지 않는다."""

        self._doc.package.set_document_metadata(
            title=title,
            creator=creator,
            subject=subject,
            keyword=keyword,
            created_date=created_date,
            modified_date=modified_date,
        )

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

    def set_compatible_document_target_program(self, target_program: str) -> None:
        """`hh:compatibleDocument/@targetProgram` 설정. 실코퍼스 47/47이
        `"HWP201X"`만 관측(다른 값의 실증은 없음 — 값을 강제하지 않는다)."""

        _set_compatible_document_target_program(self._primary_header(), target_program)

    def set_layout_compatibility_flags(self, flags: Iterable[str] = ()) -> None:
        """`hh:compatibleDocument/hh:layoutCompatibility`의 플래그 자식을
        *flags*로 교체. 실코퍼스 47/47은 플래그 0개 — 스키마가 선언한 48종
        중 실사용 관측 0건(read model `LayoutCompatibility`와 대칭 위해
        존재, 빈 이터러블이 코퍼스 전형)."""

        _set_layout_compatibility_flags(self._primary_header(), flags)

    def set_doc_option_link_info(
        self,
        *,
        path: str | None = None,
        page_inherit: bool | None = None,
        footnote_inherit: bool | None = None,
    ) -> None:
        """`hh:docOption/hh:linkinfo` 설정. 실코퍼스: `path`는 항상 빈
        문자열·`footnoteInherit`는 항상 `"0"`, `pageInherit`만 실제로
        갈린다(8/47 `"1"`)."""

        _set_doc_option_link_info(
            self._primary_header(),
            path=path,
            page_inherit=page_inherit,
            footnote_inherit=footnote_inherit,
        )

    def set_paragraph_auto_spacing(
        self,
        para_pr_id: str | int,
        *,
        e_asian_eng: bool | None = None,
        e_asian_num: bool | None = None,
    ) -> None:
        """*para_pr_id*가 가리키는 `hh:paraPr`의 `hh:autoSpacing`(한글·영문/
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
                if header._id_matches(candidate.get("id"), para_pr_id):
                    para_pr = candidate
                    break
        if para_pr is None:
            raise HwpxValueError(
                f"no hh:paraPr with id={para_pr_id!r}",
                code="parts-auto-spacing-unknown-para-pr",
                context={"para_pr_id": para_pr_id},
                suggestion="Pass an id returned by ensure_paragraph_format or an existing paraPr's id.",
            )
        _apply_paragraph_auto_spacing(
            header, para_pr, e_asian_eng=e_asian_eng, e_asian_num=e_asian_num
        )
