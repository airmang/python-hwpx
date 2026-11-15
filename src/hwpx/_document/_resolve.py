# SPDX-License-Identifier: Apache-2.0
"""`section=` / `paragraph=` 인자의 단일 해석 지점.

## 왜 이 파일이 생겼나

5.x에서 `doc.set_header_text("머리말", section=0)`은 이렇게 터졌다:

    AttributeError: 'int' object has no attribute 'properties'

`section=`은 객체를 요구하는데 사용자는 당연히 인덱스를 넘기고, 정답인
`section_index=`는 이름이 따로 있어 발견되지 않는다. 터지는 것도 내부가
새는 `AttributeError`라 호출자가 잡으려던 `TypeError`에 걸리지 않았다.
별 142개짜리 서드파티 스킬이 이것 때문에 "python-hwpx API를 우회해 XML을
손으로 풀라"고 자기 사용자에게 가르치고 있었다.

원인은 옛 `_resolve_section`이 `is None`만 보고 int를 그대로 통과시킨 것이다.
게다가 그 리졸버를 거치는 메서드가 `section`을 받는 31개 중 6개뿐이었다.

아이러니는 **저수준 `oxml` 층이 이미 int를 받는다**는 점이다
(`oxml/document_parts.py`의 섹션 해석은 "`HwpxOxmlSection` 또는 정수 인덱스"를
문서화한다). 파사드가 저수준보다 까다로웠다.

## 규약

- `section=`은 인덱스도 객체도 받는다 — 이것이 정본.
- `section_index=`는 6.x 동안 살아 있는 deprecated 별칭이고 7.0에서 사라진다.
  6.0에서 바로 없애면 **문서를 읽고 올바르게 쓴 사람만** 깨진다.
- 실패는 전부 `HwpxError` 계열이다. `AttributeError`가 공개 경로로 새어
  나가지 않는다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..errors import HwpxLookupError, HwpxTypeError, HwpxValueError

if TYPE_CHECKING:
    from ..oxml import HwpxOxmlParagraph, HwpxOxmlSection
    from ..document import HwpxDocument

__all__ = ["resolve_section", "resolve_paragraph"]


def _sections(document: "HwpxDocument") -> list["HwpxOxmlSection"]:
    return document.oxml.sections


def resolve_section(
    document: "HwpxDocument",
    section: "int | HwpxOxmlSection | None" = None,
    section_index: int | None = None,
    *,
    caller: str = "",
) -> "HwpxOxmlSection":
    """`section` / `section_index` 삼형을 하나의 섹션 객체로 해석한다.

    Args:
        document: 대상 문서.
        section: 섹션 객체 **또는 인덱스**. ``None``이면 마지막 섹션.
        section_index: 6.x deprecated 별칭. ``section``과 동시에 줄 수 없다.
        caller: 오류 ``context``에 실릴 호출 API 이름.

    Raises:
        HwpxValueError: 두 인자를 동시에 줬거나 문서에 섹션이 없다.
        HwpxLookupError: 인덱스가 범위 밖이다.
        HwpxTypeError: 섹션도 정수도 아닌 값을 줬다.
    """

    from ..oxml import HwpxOxmlSection  # 순환 import 회피 — 런타임에만 필요

    ctx: dict[str, Any] = {"caller": caller} if caller else {}

    if section is not None and section_index is not None:
        raise HwpxValueError(
            "section 과 section_index 를 동시에 지정할 수 없습니다.",
            code="section-argument-conflict",
            context={**ctx, "section": repr(section), "sectionIndex": section_index},
            suggestion="section= 하나만 쓰세요. section= 은 인덱스와 객체를 모두 받습니다.",
        )

    sections = _sections(document)
    if not sections:
        raise HwpxValueError(
            "문서에 섹션이 하나도 없습니다.",
            code="section-missing",
            context=ctx,
            suggestion="doc.add_section() 으로 섹션을 먼저 만드세요.",
        )

    requested = section if section is not None else section_index
    if requested is None:
        return sections[-1]

    if isinstance(requested, HwpxOxmlSection):
        return requested

    # bool 은 int 의 서브클래스다. `section=True` 를 인덱스 1 로 읽으면
    # 조용히 엉뚱한 섹션에 쓴다 — 타입 오류로 막는다.
    if isinstance(requested, int) and not isinstance(requested, bool):
        count = len(sections)
        if -count <= requested < count:
            return sections[requested]
        raise HwpxLookupError(
            f"섹션 인덱스 {requested} 가 범위를 벗어났습니다.",
            code="section-not-found",
            context={**ctx, "requested": requested, "count": count},
            suggestion=f"이 문서의 섹션 인덱스는 0..{count - 1} 입니다.",
        )

    raise HwpxTypeError(
        f"section 인자는 정수 인덱스나 섹션 객체여야 합니다 — {type(requested).__name__} 을(를) 받았습니다.",
        code="section-invalid-type",
        context={**ctx, "requested": repr(requested), "type": type(requested).__name__},
        suggestion="정수 인덱스(section=0) 또는 doc.sections[i] 를 넘기세요.",
    )


def resolve_paragraph(
    document: "HwpxDocument",
    paragraph: "int | HwpxOxmlParagraph | None" = None,
    *,
    section: "int | HwpxOxmlSection | None" = None,
    section_index: int | None = None,
    caller: str = "",
) -> "HwpxOxmlParagraph":
    """`paragraph` 인자를 문단 객체로 해석한다 — `section` 과 같은 규약.

    정수를 주면 **해석된 섹션 안에서의 인덱스**다. 섹션을 지정하지 않으면
    문서 전체 문단 목록의 인덱스로 읽는다(5.x `doc.paragraphs` 의 순서).
    """

    from ..oxml import HwpxOxmlParagraph

    ctx: dict[str, Any] = {"caller": caller} if caller else {}

    if isinstance(paragraph, HwpxOxmlParagraph):
        return paragraph

    scoped = section is not None or section_index is not None
    if scoped:
        target = resolve_section(document, section, section_index, caller=caller)
        paragraphs = target.paragraphs
    else:
        paragraphs = document.paragraphs

    if paragraph is None:
        if not paragraphs:
            raise HwpxValueError(
                "문서에 문단이 하나도 없습니다.",
                code="paragraph-missing",
                context=ctx,
                suggestion="doc.add_paragraph() 으로 문단을 먼저 만드세요.",
            )
        return paragraphs[-1]

    if isinstance(paragraph, int) and not isinstance(paragraph, bool):
        count = len(paragraphs)
        if -count <= paragraph < count:
            return paragraphs[paragraph]
        raise HwpxLookupError(
            f"문단 인덱스 {paragraph} 가 범위를 벗어났습니다.",
            code="paragraph-not-found",
            context={**ctx, "requested": paragraph, "count": count, "scoped": scoped},
            suggestion=f"이 범위의 문단 인덱스는 0..{count - 1} 입니다.",
        )

    raise HwpxTypeError(
        f"paragraph 인자는 정수 인덱스나 문단 객체여야 합니다 — {type(paragraph).__name__} 을(를) 받았습니다.",
        code="paragraph-invalid-type",
        context={**ctx, "requested": repr(paragraph), "type": type(paragraph).__name__},
        suggestion="정수 인덱스(paragraph=0) 또는 doc.paragraphs[i] 를 넘기세요.",
    )
