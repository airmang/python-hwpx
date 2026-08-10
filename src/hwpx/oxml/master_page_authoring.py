# SPDX-License-Identifier: Apache-2.0
"""바탕쪽(masterPage) 저작 -- 파트 생성 + 절 참조 배선 (6.13 트레인㊻).

읽기 모델(`oxml/master_page.py`)은 이미 있었으나 쓰기 경로가 전혀 없었다
-- `HwpxOxmlMasterPage`(`simple_parts.py`) 자신의 독스트링이 "읽기
전용... 쓰기 경로는 열지 않는다"고 명시한다(6.4 트레인⑮가 원장
read=none 해소만 목표한 의도적 스코프 축소). 이 모듈이 그 쓰기 경로를
연다 -- 편집기 메뉴 표면 역매핑(트레인㊷)이 [부분 대응]으로 지목한
"바탕쪽…" 메뉴 항목.

**실측(유일한 실 예시, `error__20250808__2015년_12월_재난안전종합상황_
분석_및_전망.hwpx`)**: 파트 파일명·매니페스트 `opf:item id`·`masterPage`
루트 자신의 `id`·절의 `hp:masterPage/@idRef` 넷 다 **같은 문자열**을
쓴다(``"masterpage0"``). 매니페스트에 이 파트는 있으나 spine
`opf:itemref`는 없다(바탕쪽은 읽기 순서가 아니다 -- 절 파트와 다르게
스파인 배선이 필요 없다). `hp:secPr`의 자식 시퀀스에서 `hp:masterPage`는
맨 끝(pageBorderFill들 뒤)에 오고 `masterPageCnt`가 그 개수와 일치한다
(``SectionProperties.add_master_page_reference``, `section_format.py`).
`masterPage`는 `hp:subList` 자식 하나만 갖는다(문단 본문) --
`textWidth`/`textHeight`는 실 예시가 페이지 여백에서 계산한 값을 쓰지만
그 공식을 역산할 근거가 1건으로는 없어 다른 subList 빌더의 정직한
기본값(``"0"``)을 그대로 둔다(curve와 같은 원칙, 무근거 추정 금지).

**신규 바탕쪽이 여러 절 사이에서 어떻게 공유/독립되는 게 관행인지는
실증 근거가 없다** -- 이 모듈은 "바탕쪽 하나를 만들고, 호출자가 지정한
절(들)에서 참조하게 배선한다"는 최소 계약만 제공한다(`add_master_page`
+ `SectionProperties.add_master_page_reference` 조합, 후자는 호출자가
원하는 절마다 명시적으로 호출).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Sequence

from lxml import etree as _etree  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

from ._document_primitives import (
    _DEFAULT_PARAGRAPH_ATTRS,
    _HP,
    _append_child,
    _default_sublist_attributes,
    _paragraph_id,
)
from .simple_parts import HwpxOxmlMasterPage

if TYPE_CHECKING:
    from .document_parts import HwpxOxmlDocument

__all__ = ["add_master_page"]

_OPF_NS = "http://www.idpf.org/2007/opf/"
_PART_INDEX_RE = re.compile(r"masterpage(\d+)")

#: 스키마가 선언하는 type 열거값 -- 실측은 OPTIONAL_PAGE 1건뿐
#: (`oxml/master_page.py` 참조), 나머지는 스키마 문서화만 신뢰한다(거부
#: 안 함, 그 모듈의 기존 관용 그대로).
_MASTER_PAGE_TYPES = frozenset({"BOTH", "EVEN", "ODD", "LAST_PAGE", "OPTIONAL_PAGE"})


def _manifest_element(document: "HwpxOxmlDocument") -> _etree._Element:
    ns = {"opf": _OPF_NS}
    manifest_el = document._manifest.find("opf:manifest", ns)
    if manifest_el is None:
        from ..errors import HwpxStateError

        raise HwpxStateError(
            "content manifest is missing <opf:manifest>",
            code="master-page-manifest-missing",
            suggestion="Check that this is an intact HWPX package.",
        )
    return manifest_el


def add_master_page(
    document: "HwpxOxmlDocument",
    *,
    text: str | None = None,
    paragraphs: Sequence[str] | None = None,
    page_type: str = "OPTIONAL_PAGE",
    page_number: int = 1,
    page_duplicate: bool = False,
    page_front: bool = False,
) -> str:
    """새 바탕쪽 파트를 만들고 매니페스트에 등록한다.

    돌려주는 값은 그 id(``"masterpageN"``) -- 절에서 실제로 쓰려면
    ``section.properties.add_master_page_reference(id)``를 별도로 호출할 것
    (이 함수는 파트를 만들 뿐, 어느 절과도 자동으로 연결하지 않는다).

    *text*/*paragraphs* 중 하나로 본문을 채운다(둘 다 없으면 빈 문단
    하나). *page_type*은 스키마 선언 열거값만 받는다.
    """
    from ..errors import HwpxValueError

    if page_type not in _MASTER_PAGE_TYPES:
        raise HwpxValueError(
            f"unsupported master page type: {page_type!r}",
            code="master-page-type-unsupported",
            context={"requested": page_type, "supported": sorted(_MASTER_PAGE_TYPES)},
            suggestion=f"Supported values: {', '.join(sorted(_MASTER_PAGE_TYPES))}",
        )

    body_lines = list(paragraphs) if paragraphs is not None else [text or ""]

    existing_indices: list[int] = []
    for master_page in document._master_pages:
        match = _PART_INDEX_RE.search(master_page.part_name)
        if match:
            existing_indices.append(int(match.group(1)))
    next_index = (max(existing_indices) + 1) if existing_indices else 0
    master_page_id = f"masterpage{next_index}"
    part_name = f"Contents/{master_page_id}.xml"

    root = _etree.Element(
        "masterPage",
        {
            "id": master_page_id,
            "type": page_type,
            "pageNumber": str(max(page_number, 0)),
            "pageDuplicate": "1" if page_duplicate else "0",
            "pageFront": "1" if page_front else "0",
        },
    )
    sub_list_attrs = _default_sublist_attributes()
    sub_list_attrs["vertAlign"] = "TOP"  # 실 예시 관측값(다른 subList의 CENTER와 다름)
    sub_list = _append_child(root, f"{_HP}subList", sub_list_attrs)
    for line in body_lines:
        para = _append_child(
            sub_list, f"{_HP}p", {"id": _paragraph_id(), **_DEFAULT_PARAGRAPH_ATTRS}
        )
        run = _append_child(para, f"{_HP}run", {"charPrIDRef": "0"})
        text_el = _append_child(run, f"{_HP}t", {})
        if line:
            text_el.text = line
        _append_child(para, f"{_HP}linesegarray")

    manifest_el = _manifest_element(document)
    item = manifest_el.makeelement(
        f"{{{_OPF_NS}}}item",
        {"id": master_page_id, "href": part_name, "media-type": "application/xml"},
    )
    manifest_el.append(item)
    # add_section's exact idiom (_add_section_to_manifest) -- serialize()
    # only re-writes content.hpf when this flag is set (document_parts.py's
    # save pipeline checks it, not just "was self._manifest mutated").
    document._manifest_dirty = True

    new_master_page = HwpxOxmlMasterPage(part_name, root, document)
    new_master_page.mark_dirty()
    document._master_pages.append(new_master_page)

    return master_page_id
