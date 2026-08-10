# SPDX-License-Identifier: Apache-2.0
"""``ensure_numbering``'s full body (6.13 트레인㊻).

``header_part.py``의 owner-file 1600줄 캡에 헤드룸이 없어(㊻ 착지 시
1617줄) 이 메서드 전체를 새 모듈로 뺀다(`section_layout.py`의 "그대로
옮김" 전례와 같은 패턴) — `header_part.py`의 자리는 1줄 위임만 남는다.

세 kind(``"bullet"``/``"number"``/``"outline"``) 중 뒤 둘은 완전히 같은
메커니즘(``hh:numbering``/``hh:paraHead`` 정의를 만들고 각 레벨의 paraPr
id를 돌려준다)을 서로 다른 ``heading_type``(``"NUMBER"``/``"OUTLINE"``)
으로만 참조한다 — ``_numbering_refs_for_kind``가 그 공통 로직 하나로 둘
다 담당한다(중복 제거, 신규 계산 로직 없음).

``"outline"``은 6.13 트레인㊻이 새로 연 kind다: `hh:heading
type="OUTLINE"`이 목록 서식과 **같은** id-space를 쓴다는 사실은 이미
알려져 있었으나(`bind_outline_level`, `_document/headings.py`),
`ensure_numbering` 자신은 `"bullet"`/`"number"`만 받았다 — 개요 번호
*모양*(numFormat/start)을 커스터마이즈할 길이 없었다(`add_heading`/
`apply_paragraph_format(outline_level=)`는 항상 고정 `idRef="0"`만
참조). 실코퍼스 67파일 전수: `hh:heading type="OUTLINE"` 451건 전부
`idRef="0"`뿐이라 커스텀 idRef 조합은 미실측(Create(experimental), v17
배치 대기) — 재사용하는 `hh:numbering`/`hh:paraHead` 구조 자체는 v14의
`authored-listformat`에서 이미 render-verified라 구조적 추측 위험은
없다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Mapping, Sequence

if TYPE_CHECKING:
    from .header_part import HwpxOxmlHeader

__all__ = ["ensure_numbering_refs"]

_DEFAULT_BULLET_CHARS = ("-", "○", "□", "•")


def _numbering_refs_for_kind(
    header: "HwpxOxmlHeader",
    heading_type: str,
    resolved_levels: Sequence[Mapping[str, str]],
) -> list[str]:
    """``hh:numbering`` 정의를 만들고 각 레벨의 paraPr id를 돌려준다.

    *heading_type*은 ``"NUMBER"``(번호매기기) 또는 ``"OUTLINE"``(개요
    번호 모양) — 만드는 ``hh:numbering``/``hh:paraHead`` 구조 자체는
    완전히 동일, 참조하는 `hh:heading`의 `type`만 다르다.
    """
    numbering_id = header._create_numbering_definition(list(resolved_levels))
    return [
        header._ensure_para_property_heading(
            heading_type=heading_type,
            id_ref=numbering_id,
            level=index,
        )
        for index in range(len(resolved_levels))
    ]


def ensure_numbering_refs(
    header: "HwpxOxmlHeader",
    *,
    kind: str,
    levels: Sequence[Mapping[str, str]] | None = None,
) -> list[str]:
    """``header_part.py``의 ``HwpxOxmlHeader.ensure_numbering``이 그대로
    위임하는 전체 구현 — 원래 위치에서 옮긴 것뿐, 동작 변경 없음(``bullet``/
    ``number`` 두 branch)에 ``outline``이 새로 붙었다."""

    resolved_levels = list(levels or [{}])
    if not resolved_levels:
        resolved_levels = [{}]
    normalized_kind = kind.lower()

    if normalized_kind == "bullet":
        refs: list[str] = []
        for index, level in enumerate(resolved_levels):
            bullet_char = str(
                level.get("char") or _DEFAULT_BULLET_CHARS[index % len(_DEFAULT_BULLET_CHARS)]
            )
            bullet_id = header._ensure_bullet_definition(bullet_char)
            refs.append(
                header._ensure_para_property_heading(
                    heading_type="BULLET",
                    id_ref=bullet_id,
                    level=index,
                )
            )
        return refs

    if normalized_kind in {"number", "numbered", "numbering"}:
        return _numbering_refs_for_kind(header, "NUMBER", resolved_levels)

    if normalized_kind == "outline":
        return _numbering_refs_for_kind(header, "OUTLINE", resolved_levels)

    raise ValueError("kind must be 'bullet', 'number', or 'outline'")
