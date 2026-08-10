# SPDX-License-Identifier: Apache-2.0
"""``Contents/content.hpf``'s ``opf:metadata`` block -- read model.

실코퍼스 67파일 전수 실측(2026-08-10, 사이클 6.12 트레인㊸): 이 블록은
스키마 미선언(다른 OPC 파트군과 같은 부류)이지만 벤더드 코퍼스 전체가
같은 모양을 공유한다 -- ``opf:title``(65/67에 요소 존재, 그중 31건은 빈
문자열) + ``opf:language``(항상 ``"ko"``) + ``opf:meta name="..."
content="text"`` 8종(``creator``/``subject``/``description``/
``lastsaveby``/``CreatedDate``/``ModifiedDate``/``date``/``keyword``).

**날짜 필드 둘의 근본적으로 다른 성격(실측으로 확정, 추측 아님)**:

- ``CreatedDate``/``ModifiedDate``: 65/65 항상 존재·항상 비어있지 않고,
  **단일 포맷**(ISO 8601 + ``Z`` 접미, 예 ``"2025-09-17T04:32:50Z"``)으로
  100% 일관됨 -- 구조화(파싱) 가치가 있다.
- ``date``: 64/67 존재하나 **최소 5가지 서로 다른 포맷**을 관측했다(예:
  ``"2025년 9월 17일 수요일 오후 1:32:50"``(현행, 다수)·
  ``"1997년 4월 24일 목요일, 18시 44분"``(구버전, 쉼표+24시간제+초 없음)·
  ``"2002년 12월 4일 수요일, 9시 49분"``·
  ``"Tuesday, May 20, 2025 1:04:56 AM"``(영어 로캘)·
  ``"2025년 1월 24일 9시 25분"``(요일 생략)) -- 한컴 앱 버전/OS 로캘에
  따라 갈리는 것으로 보이며 **단일 정본 포맷이 없다**. 이 필드는
  파싱·생성을 시도하지 않고 **불투명 문자열로만** 보존한다(무근거
  포맷 추정 금지 원칙 -- curve/connectLine·DEV-021과 같은 이유).

``subject``/``description``/``keyword``는 요소 자체는 항상 있지만
65개 중 각각 1건만 비어있지 않다 -- 존재는 관용이고 값 채움은 드물다.
``lastsaveby``는 64/65에 존재(1건 완전 누락, ``mfds_admin_notice.hwpx``).

패키지 루트 속성(``version``/``unique-identifier``/``id``)은 전량 빈
문자열 -- 실사용 관측 0건이라 이 모델에서 다루지 않는다(다른 파트군의
"관측 0건은 모델링 안 함" 원칙과 동일).
"""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

from .utils import text_or_none

__all__ = ["DocumentMetadata", "parse_document_metadata"]

OPF_NS = "http://www.idpf.org/2007/opf/"


@dataclass(slots=True)
class DocumentMetadata:
    """``opf:metadata`` -- ``content.hpf`` 파트의 문서 속성 블록.

    ``created_date``/``modified_date``는 실측상 단일 ISO 8601 포맷이라
    원문 문자열 그대로 노출한다(파싱은 호출자 책임 -- ``datetime.
    fromisoformat``이 ``Z`` 접미까지 그대로 받는 파이썬 버전이 다양해
    이 모델 자신이 변환을 강제하지 않는다). ``date``는 다중 포맷이라
    **항상** 불투명 문자열이다 -- 절대 파싱 시도하지 않음.
    """

    title: str | None
    language: str | None
    creator: str | None
    subject: str | None
    description: str | None
    keyword: str | None
    lastsaveby: str | None
    created_date: str | None
    modified_date: str | None
    date: str | None


def _meta_text(metadata: "etree._Element", name: str) -> str | None:
    for meta in metadata.findall(f"{{{OPF_NS}}}meta"):
        if meta.get("name") == name:
            return text_or_none(meta)
    return None


def parse_document_metadata(node: "etree._Element") -> DocumentMetadata:
    """*node*는 ``opf:metadata`` 요소 자신(``opf:package``의 자식)."""

    title_el = node.find(f"{{{OPF_NS}}}title")
    language_el = node.find(f"{{{OPF_NS}}}language")
    return DocumentMetadata(
        title=text_or_none(title_el) if title_el is not None else None,
        language=text_or_none(language_el) if language_el is not None else None,
        creator=_meta_text(node, "creator"),
        subject=_meta_text(node, "subject"),
        description=_meta_text(node, "description"),
        keyword=_meta_text(node, "keyword"),
        lastsaveby=_meta_text(node, "lastsaveby"),
        created_date=_meta_text(node, "CreatedDate"),
        modified_date=_meta_text(node, "ModifiedDate"),
        date=_meta_text(node, "date"),
    )
