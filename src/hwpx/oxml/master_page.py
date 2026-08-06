# SPDX-License-Identifier: Apache-2.0
"""바탕쪽(``Contents/masterpageN.xml``, 루트 ``masterPage``) 읽기 모델.

실코퍼스 실측(``hwpxlib_corpus`` 1파일 + 접근 가능한 개인 실문서 중 바탕쪽을
가진 것 110건, 서로 다른 두 문서 계열): ``DevDoc/OWPML SCHEMA/MasterPage XML
schema.xml``이 선언하는 2024 초안 스키마(타겟 네임스페이스
``http://www.owpml.org/owpml/2024/master-page``, 루트 ``hm:masterPage``)는
실 산출물과 다르다 — 실 문서의 루트 ``masterPage``는 **네임스페이스가 없다**
(``docs/_extra/element-census.json``의 ``unnamespacedElements``가 이미 기록한
사실). ``version.xml``(``version_part.py`` 참조)에서도 같은 부류의 2024
초안-대-2011 실물 드리프트가 확인됐다.

자식은 스키마가 말하는 그대로 ``hp:subList``(일반 ``ParaListType``) 하나 —
문단 본문. 이 파트는 몸통 section에 속하지 않는 독립 파트라
``HwpxOxmlParagraph``(``mark_dirty`` 등 section 결합을 요구)로 감싸지 않고,
읽기 전용으로 평문 텍스트만 뽑는다.

관측된 ``type`` 값 3개(OPTIONAL_PAGE·EVEN·ODD) — 스키마가 말하는 나머지
(BOTH/LAST_PAGE)는 미관측이라 문서화된 열거값을 신뢰만 한다(``pageNumber``·
``pageDuplicate``·``pageFront``도 관측 범위 내에서 스키마와 일치, 전부
0/false 기본형).
"""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

from .utils import local_name, parse_bool, parse_int

__all__ = ["MasterPage", "parse_master_page"]

#: 스키마가 선언하는 ``type`` 열거값(1개만 실측: OPTIONAL_PAGE) — 검증에는
#: 쓰지 않는다(실측이 얇아, 미관측 값을 거부하면 미래의 실문서를 무음으로
#: 오탐할 위험이 검증 이득보다 크다). 문서화 목적으로만 남긴다.
MASTER_PAGE_TYPES = frozenset({"BOTH", "EVEN", "ODD", "LAST_PAGE", "OPTIONAL_PAGE"})


@dataclass(slots=True)
class MasterPage:
    """바탕쪽 파트 루트(``masterPage``, 네임스페이스 없음 — 실측)."""

    id: str | None
    type: str | None
    page_number: int | None
    page_duplicate: bool | None
    page_front: bool | None
    paragraph_texts: tuple[str, ...]


def _sublist_paragraph_texts(sublist: etree._Element) -> tuple[str, ...]:
    """``hp:subList``의 각 ``hp:p`` 평문 텍스트.

    ``HwpxOxmlParagraph.text``와 같은 ``hp:t``/``hp:tab`` 규칙을 쓰지만,
    바탕쪽은 몸통 section에 속하지 않는 독립 파트라 section 결합 없는
    독립 함수로 둔다(읽기 전용이라 ``mark_dirty`` 등이 필요 없다).
    """

    texts = []
    for p in sublist:
        if local_name(p) != "p":
            continue
        parts = []
        for run in p:
            if local_name(run) != "run":
                continue
            for child in run:
                name = local_name(child)
                if name == "t":
                    if child.text:
                        parts.append(child.text)
                elif name == "tab":
                    parts.append("\t")
        texts.append("".join(parts))
    return tuple(texts)


def parse_master_page(node: etree._Element) -> MasterPage:
    root_name = local_name(node)
    if root_name != "masterPage":
        from ..errors import HwpxValueError

        raise HwpxValueError(
            "expected a masterpage part root named masterPage, "
            f"got {root_name!r}",
            code="document-master-page-root-invalid",
            context={"requested": root_name},
        )

    sublist = None
    for child in node:
        if local_name(child) == "subList":
            sublist = child
            break

    return MasterPage(
        id=node.get("id"),
        type=node.get("type"),
        page_number=parse_int(node.get("pageNumber")),
        page_duplicate=parse_bool(node.get("pageDuplicate")),
        page_front=parse_bool(node.get("pageFront")),
        paragraph_texts=_sublist_paragraph_texts(sublist) if sublist is not None else (),
    )
