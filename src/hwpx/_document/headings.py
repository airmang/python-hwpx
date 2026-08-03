# SPDX-License-Identifier: Apache-2.0
"""`add_heading` 의 스타일 해석과 개요 수준 결합.

WP-A는 **이음새(seam)만** 만든다 — `document.py`가 부를 두 함수의 시그니처와,
설계서 §4.2 폴백 4단계 중 1~2단계(이름/영문명 정확 일치)까지의 최소 구현이다.
WP-B1이 3단계(``paraPr`` 의 ``hh:heading`` 수준으로 역추적 — 스타일 이름이
바뀐 야생 문서 대응)와 이름 해석기(`doc.styles.resolve`) 통합을 채운다.

이 파일이 WP-A에 포함된 이유: `document.py`(WP-A 배타 소유)가 이 이음새를
불러야 하는데, 로직을 `document.py` 안에 인라인하면 WP-B1이 WP-A의 파일을
편집해야 한다. 이음새를 여기 두면 B1은 이 파일의 **본문만** 바꾸면 된다.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..errors import HwpxLookupError, HwpxValueError

if TYPE_CHECKING:
    from ..oxml import HwpxOxmlParagraph, Style
    from ..document import HwpxDocument

__all__ = ["MIN_HEADING_LEVEL", "MAX_HEADING_LEVEL", "resolve_heading_style", "bind_outline_level"]

#: HWPX 개요는 정확히 10수준이다(Skeleton의 "개요 1"~"개요 10" = id 2~11).
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
            context={"requested": level, "min": MIN_HEADING_LEVEL, "max": MAX_HEADING_LEVEL},
            suggestion=(
                "HWPX 개요는 1~10 수준입니다. 문서 제목에는 "
                "style= 로 그 문서에 실재하는 스타일을 지정하세요."
            ),
        )
    return level


def resolve_heading_style(
    document: "HwpxDocument",
    *,
    level: int,
    style: "int | str | Style | None" = None,
) -> "Style":
    """개요 수준(또는 명시 *style*)에 해당하는 스타일을 돌려준다.

    폴백 순서(설계서 §4.2):

    1. 명시 ``style`` — 이름·영문명·숫자 id
    2. ``name == "개요 {level}"``
    3. ``eng_name == "Outline {level}"``
    4. *(WP-B1)* ``paraPr`` 의 ``hh:heading`` 수준으로 역추적
    5. 실패 → ``heading-style-missing``
    """

    styles = document.oxml.styles
    if style is not None:
        resolved = _lookup(styles, style)
        if resolved is not None:
            return resolved
        raise HwpxLookupError(
            f"스타일 {style!r} 을(를) 찾을 수 없습니다.",
            code="style-not-found",
            context={
                "requested": style if isinstance(style, (int, str)) else repr(style),
                "available": _names(styles),
                "availableCount": len(styles),
            },
            suggestion="doc.styles 로 이 문서의 스타일 목록을 확인하세요.",
        )

    _check_level(level)
    wanted = _OUTLINE_NAME.format(level=level)
    for entry in styles.values():
        if (getattr(entry, "name", "") or "").strip() == wanted:
            return entry
    for entry in styles.values():
        match = _OUTLINE_ENG_NAME.match((getattr(entry, "eng_name", "") or "").strip())
        if match and int(match.group(1)) == level:
            return entry

    raise HwpxLookupError(
        f"level {level} 개요 스타일을 찾을 수 없습니다.",
        code="heading-style-missing",
        context={
            "level": level,
            "tried": [wanted, f"Outline {level}"],
            "available": _names(styles),
            "availableCount": len(styles),
        },
        suggestion=(
            "이 문서에는 개요 스타일이 없습니다. "
            'style="<이 문서의 스타일 이름>" 으로 직접 지정하거나, '
            "doc.styles 로 목록을 확인하세요."
        ),
    )


def bind_outline_level(
    document: "HwpxDocument",
    paragraph: "HwpxOxmlParagraph",
    *,
    level: int,
) -> None:
    """문단의 ``paraPr`` 에 ``<hh:heading type="OUTLINE">`` 을 보장한다.

    스타일만 붙이면 한컴이 개요 번호를 매기지 않는다 — 5.x에서 개요 스타일과
    개요 수준이 분리돼 있던 결함이 여기서 닫힌다.
    """

    from . import layout as _layout

    _check_level(level)
    try:
        index = document.paragraphs.index(paragraph)
    except ValueError:  # pragma: no cover - 방금 만든 문단이라 항상 있다
        return
    _layout.set_paragraph_format(document, paragraph_index=index, outline_level=level)


def _lookup(styles: "dict[str, Style]", spec: "int | str | Style") -> "Style | None":
    if hasattr(spec, "id") and not isinstance(spec, (int, str)):
        return spec  # type: ignore[return-value]
    if isinstance(spec, int) or (isinstance(spec, str) and spec.strip().isdigit()):
        key = str(int(str(spec).strip()))
        for style_id, entry in styles.items():
            if str(style_id) == key or str(getattr(entry, "id", "")) == key:
                return entry
        return None
    wanted = str(spec).strip()
    for entry in styles.values():
        if (getattr(entry, "name", "") or "").strip() == wanted:
            return entry
    lowered = wanted.lower()
    for entry in styles.values():
        if (getattr(entry, "eng_name", "") or "").strip().lower() == lowered:
            return entry
    return None


def _names(styles: "dict[str, Style]") -> list[str]:
    return [n for n in ((getattr(e, "name", "") or "").strip() for e in styles.values()) if n]
