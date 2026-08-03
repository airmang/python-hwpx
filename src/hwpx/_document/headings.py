# SPDX-License-Identifier: Apache-2.0
"""`add_heading` 의 개요 스타일 해석과 개요 수준 결합.

## 이 모듈이 닫는 결함

5.x에서 개요 **스타일**과 개요 **수준**은 분리돼 있었다.
`set_paragraph_format(outline_level=1)` 은 새 `paraPr` 에
`<hh:heading type="OUTLINE" level="0">` 을 쓰지만 `styleIDRef` 는 건드리지
않는다. 그래서 "개요 번호는 붙는데 스타일은 바탕글(0)"인 문단이 나왔다.
반대로 스타일만 "개요 1"로 지정하면 스타일 자신의 `paraPr` 에 개요 정보가
있더라도 문단 수준에서는 그것을 선언하지 않는다.

`add_heading` 은 둘을 한 번에 묶는 유일한 경로다 — :func:`resolve_heading_style`
로 스타일을 정하고 :func:`bind_outline_level` 로 개요 수준을 보장한다.

## 스타일 해석 폴백

야생 문서는 스타일 이름이 바뀌어 있을 수 있다. 그래서 이름만 보지 않고,
마지막에 **구조**를 본다 — 스타일의 `paraPr` 가 이미 `hh:heading` 으로 그
수준을 선언하고 있으면 이름이 무엇이든 그 스타일이 그 수준의 개요다.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..errors import HwpxLookupError, HwpxValueError

if TYPE_CHECKING:
    from ..oxml import HwpxOxmlParagraph, Style
    from ..document import HwpxDocument

__all__ = [
    "MIN_HEADING_LEVEL",
    "MAX_HEADING_LEVEL",
    "resolve_heading_style",
    "bind_outline_level",
]

#: HWPX 개요는 정확히 10수준이다(Skeleton 의 "개요 1"~"개요 10" = id 2~11).
MIN_HEADING_LEVEL = 1
MAX_HEADING_LEVEL = 10

_OUTLINE_NAME = "개요 {level}"
_OUTLINE_ENG_NAME = re.compile(r"^outline\s*(\d+)$", re.IGNORECASE)


def _check_level(level: int) -> int:
    if not isinstance(level, int) or isinstance(level, bool):
        raise HwpxValueError(
            f"level 은 정수여야 합니다 — {type(level).__name__} 을(를) 받았습니다.",
            code="heading-level-invalid",
            context={"requested": repr(level)},
            suggestion=f"{MIN_HEADING_LEVEL}..{MAX_HEADING_LEVEL} 사이의 정수를 주세요.",
        )
    if not MIN_HEADING_LEVEL <= level <= MAX_HEADING_LEVEL:
        raise HwpxValueError(
            f"개요 수준 {level} 은(는) 범위를 벗어났습니다.",
            code="heading-level-out-of-range",
            context={
                "requested": level,
                "min": MIN_HEADING_LEVEL,
                "max": MAX_HEADING_LEVEL,
            },
            suggestion=(
                "HWPX 개요는 1~10 수준입니다. 문서 제목에는 "
                "style= 로 그 문서에 실재하는 스타일을 지정하세요."
            ),
        )
    return level


def _style_declares_outline_level(
    document: "HwpxDocument", style: "Style", level: int
) -> bool:
    """스타일의 `paraPr` 가 이미 이 개요 수준을 선언하고 있는가.

    이름이 바뀐 야생 문서를 위한 구조 기반 폴백. `ParagraphProperty.heading`
    은 이미 파싱되는 필드라 추가 비용이 없다.
    """

    para_pr = document.oxml.paragraph_property(style.para_pr_id_ref)
    heading = getattr(para_pr, "heading", None)
    if heading is None:
        return False
    if (getattr(heading, "type", "") or "").upper() != "OUTLINE":
        return False
    try:
        declared = int(str(getattr(heading, "level", "")).strip())
    except (TypeError, ValueError):
        return False
    return declared == level - 1


def resolve_heading_style(
    document: "HwpxDocument",
    *,
    level: int,
    style: "int | str | Style | None" = None,
) -> "Style":
    """개요 수준(또는 명시 *style*)에 해당하는 스타일을 돌려준다.

    폴백 순서:

    1. 명시 ``style`` — 이름·영문명·숫자 id (``doc.styles.resolve`` 위임)
    2. ``name == "개요 {level}"``
    3. ``eng_name == "Outline {level}"``
    4. ``paraPr`` 의 ``hh:heading`` 이 그 수준을 선언하는 스타일 (이름이 바뀐
       야생 문서 대응)
    5. 실패 → ``heading-style-missing``

    Raises:
        HwpxValueError: *level* 이 1~10 밖이다.
        HwpxLookupError: 명시 스타일이 없거나(``style-not-found`` /
            ``style-ambiguous``), 이 문서에 해당 개요 스타일이 없다
            (``heading-style-missing``).
    """

    if style is not None:
        # 명시 지정은 개요 수준과 무관하게 사용자 뜻이 우선이다. 실패 메시지
        # (가장 가까운 이름·모호성 후보)도 스타일 해석기가 만든다.
        return document.styles.resolve(style)

    _check_level(level)
    styles = document.oxml.styles
    wanted = _OUTLINE_NAME.format(level=level)

    for entry in styles.values():
        if (entry.name or "").strip() == wanted:
            return entry
    for entry in styles.values():
        match = _OUTLINE_ENG_NAME.match((entry.eng_name or "").strip())
        if match and int(match.group(1)) == level:
            return entry
    for entry in styles.values():
        if _style_declares_outline_level(document, entry, level):
            return entry

    available = document.styles.names()
    raise HwpxLookupError(
        f"level {level} 개요 스타일을 찾을 수 없습니다.",
        code="heading-style-missing",
        context={
            "level": level,
            "tried": [wanted, f"Outline {level}", f"paraPr heading level {level - 1}"],
            "available": available,
            "availableCount": len(available),
        },
        suggestion=(
            "이 문서에는 개요 스타일이 없습니다. "
            'style="<이 문서의 스타일 이름>" 으로 직접 지정하거나, '
            "doc.styles.names() 로 목록을 확인하세요."
        ),
    )


def bind_outline_level(
    document: "HwpxDocument",
    paragraph: "HwpxOxmlParagraph",
    *,
    level: int,
) -> None:
    """문단의 `paraPr` 에 `<hh:heading type="OUTLINE">` 을 보장한다.

    스타일만 붙이면 한컴이 개요 번호를 매기지 않는다 — 5.x에서 개요 스타일과
    개요 수준이 분리돼 있던 결함이 여기서 닫힌다.
    """

    from . import layout as _layout

    _check_level(level)
    target = paragraph.element
    for index, candidate in enumerate(document.paragraphs):
        if candidate.element is target:
            _layout.set_paragraph_format(
                document, paragraph_index=index, outline_level=level
            )
            return
    # 방금 만든 문단이라 항상 찾힌다. 못 찾으면 조용히 넘어가는 대신 말한다 —
    # 개요 수준이 빠진 문단은 "번호가 안 붙는 제목"이라 무음 실패가 가장 나쁘다.
    raise HwpxLookupError(  # pragma: no cover - 방어
        "개요 수준을 붙일 문단을 문서에서 찾지 못했습니다.",
        code="paragraph-not-found",
        context={"level": level},
        suggestion="문단이 이 문서에 속해 있는지 확인하세요.",
    )
