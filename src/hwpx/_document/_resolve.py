# SPDX-License-Identifier: Apache-2.0
"""`section=` / `paragraph=` 인자의 단일 해석 지점.

## 왜 이 파일이 생겼나

5.x에서 `doc.set_header_text("머리말", section=0)`은 이렇게 터졌다:

    AttributeError: 'int' object has no attribute 'properties'

`section=`은 객체를 요구하는데 사용자는 당연히 인덱스를 넘기고, 정답이던
`section_index=`는 이름이 따로 있어 발견되지 않았다. 터지는 것도 내부가
새는 `AttributeError`라 호출자가 잡으려던 `TypeError`에 걸리지 않았다.
별 142개짜리 서드파티 스킬이 이것 때문에 "python-hwpx API를 우회해 XML을
손으로 풀라"고 자기 사용자에게 가르치고 있었다.

원인은 옛 `_resolve_section`이 `is None`만 보고 int를 그대로 통과시킨 것이다.
게다가 그 리졸버를 거치는 메서드가 `section`을 받는 31개 중 6개뿐이었다.

아이러니는 **저수준 `oxml` 층이 이미 int를 받는다**는 점이다
(`oxml/document_parts.py`의 섹션 해석은 "`HwpxOxmlSection` 또는 정수 인덱스"를
문서화한다). 파사드가 저수준보다 까다로웠다.

## 규약

- `section=`은 인덱스도 객체도 받는다 — 이것이 유일한 인자다.
- 6.x의 별칭 `section_index=`는 7.0에서 없어졌다. 주면
  `hwpx-argument-removed` 오류가 `section=`을 알려 준다
  (:func:`hwpx.errors.rejects_removed_arguments`).
- 실패는 전부 `HwpxError` 계열이다. `AttributeError`가 공개 경로로 새어
  나가지 않는다.
"""

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, TypeVar, cast

from ..errors import HwpxLookupError, HwpxTypeError, HwpxValueError

_F = TypeVar("_F", bound=Callable[..., Any])


def refused_leaves_no_paragraph(func: _F) -> _F:
    """For a function that puts something into *paragraph*, or -- given none -- into a paragraph it
    appends to a section first (:func:`home_paragraph`): when the call is refused, that new paragraph
    goes again.

    The paragraph is made before the thing itself is checked (its text, its sizes, its colours), so a
    refused ``doc.shapes.add_line(line_color="nope")`` or ``doc.notes.add_footnote(123)`` used to leave
    an empty paragraph at the end of the section. Only the paragraph the function made for itself is
    taken out: whatever else changed while the call ran (an argument that edits the document as it is
    read) is not this function's to undo, and the section stays marked as changed.
    """

    @wraps(func)
    def wrapper(doc: Any, *args: Any, **kwargs: Any) -> Any:
        made: list[Any] = []
        records = doc.__dict__.setdefault("_home_paragraph_records", [])
        records.append(made)
        try:
            return func(doc, *args, **kwargs)
        except BaseException:
            for paragraph in made:
                element = paragraph.element
                holder = element.getparent() if hasattr(element, "getparent") else None
                if holder is not None:
                    holder.remove(element)
            raise
        finally:
            records.pop()

    return cast(_F, wrapper)


def home_paragraph(doc: Any, *args: Any, **kwargs: Any) -> "HwpxOxmlParagraph":
    """``doc.add_paragraph(...)`` for the paragraph a function makes to put its object into, noted so
    that :func:`refused_leaves_no_paragraph` takes it out again when the function is refused."""

    return note_home_paragraph(doc, doc.add_paragraph(*args, **kwargs))


def note_home_paragraph(doc: Any, paragraph: "HwpxOxmlParagraph") -> "HwpxOxmlParagraph":
    """Note *paragraph* as the one the running function made for its object (see
    :func:`refused_leaves_no_paragraph`) and return it."""

    records = doc.__dict__.get("_home_paragraph_records")
    if records:
        records[-1].append(paragraph)
    return paragraph

if TYPE_CHECKING:
    from ..oxml import HwpxOxmlParagraph, HwpxOxmlSection
    from ..document import HwpxDocument

__all__ = ["resolve_section", "resolve_paragraph", "optional_paragraph"]


def _sections(document: "HwpxDocument") -> tuple["HwpxOxmlSection", ...]:
    return document.oxml.sections


def resolve_section(
    document: "HwpxDocument",
    section: "int | HwpxOxmlSection | None" = None,
    *,
    caller: str = "",
) -> "HwpxOxmlSection":
    """`section` 인자(번호·객체·``None``)를 하나의 섹션 객체로 해석한다.

    Args:
        document: 대상 문서.
        section: 섹션 객체 **또는 인덱스**. ``None``이면 마지막 섹션.
        caller: 오류 ``context``에 실릴 호출 API 이름.

    Raises:
        HwpxValueError: 문서에 섹션이 없다.
        HwpxLookupError: 인덱스가 범위 밖이다.
        HwpxTypeError: 섹션도 정수도 아닌 값을 줬다.
    """

    from ..oxml import HwpxOxmlSection  # 순환 import 회피 — 런타임에만 필요

    ctx: dict[str, Any] = {"caller": caller} if caller else {}

    sections = _sections(document)
    if not sections:
        raise HwpxValueError(
            "문서에 섹션이 하나도 없습니다.",
            code="section-missing",
            context=ctx,
            suggestion="doc.add_section() 으로 섹션을 먼저 만드세요.",
        )

    requested = section
    if requested is None:
        return sections[-1]

    if isinstance(requested, HwpxOxmlSection):
        if not any(requested is own for own in sections):
            # Another document's section (or one removed from this one): the paragraph went into that
            # document and the image, the styles and the ids into this one -- a picture in one file
            # and its image in the other.
            raise HwpxLookupError(
                "그 섹션은 이 문서의 섹션이 아닙니다.",
                code="section-not-found",
                context=ctx,
                suggestion="이 문서의 doc.sections[i] 나 정수 인덱스를 넘기세요.",
            )
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


def _belongs(document: "HwpxDocument", paragraph: "HwpxOxmlParagraph") -> bool:
    """Whether *paragraph*'s element sits in one of *document*'s sections (body, cell, header,
    footer, note or memo): not another document's, and not one taken out."""

    sections = _sections(document)
    element = paragraph.element
    if not hasattr(element, "getparent"):  # a stdlib tree: its section must be this document's
        return any(section is paragraph.section for section in sections) and any(
            node is element for section in sections for node in section.element.iter()
        )
    root: Any = element  # an lxml element here; the stdlib type has no getparent
    while (parent := root.getparent()) is not None:
        root = parent
    return any(section.element is root for section in sections)


def optional_paragraph(
    document: "HwpxDocument",
    paragraph: "int | HwpxOxmlParagraph | None",
    *,
    section: "int | HwpxOxmlSection | None" = None,
    caller: str = "",
) -> "HwpxOxmlParagraph | None":
    """:func:`resolve_paragraph` for a ``paragraph=`` that may be left out: ``None`` stays
    ``None`` (the caller adds a paragraph); an index or a paragraph object is resolved and
    checked to belong to *document*."""

    if paragraph is None:
        return None
    return resolve_paragraph(document, paragraph, section=section, caller=caller)


def resolve_paragraph(
    document: "HwpxDocument",
    paragraph: "int | HwpxOxmlParagraph | None" = None,
    *,
    section: "int | HwpxOxmlSection | None" = None,
    caller: str = "",
) -> "HwpxOxmlParagraph":
    """`paragraph` 인자를 문단 객체로 해석한다 — `section` 과 같은 규약.

    정수를 주면 **해석된 섹션 안에서의 인덱스**다. 섹션을 지정하지 않으면
    문서 전체 문단 목록의 인덱스로 읽는다(5.x `doc.paragraphs` 의 순서).
    """

    from ..oxml import HwpxOxmlParagraph

    ctx: dict[str, Any] = {"caller": caller} if caller else {}

    if isinstance(paragraph, HwpxOxmlParagraph):
        if not _belongs(document, paragraph):
            raise HwpxValueError(
                "넘긴 문단은 이 문서에 속한 문단이 아닙니다(다른 문서의 문단이거나 지운 문단).",
                code="paragraph-not-in-document",
                context=ctx,
                suggestion="이 문서의 doc.paragraphs, cell.paragraphs, header.paragraphs 에서 문단을 넘기세요.",
            )
        return paragraph

    scoped = section is not None
    if scoped:
        target = resolve_section(document, section, caller=caller)
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
