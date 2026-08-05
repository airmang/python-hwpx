# SPDX-License-Identifier: Apache-2.0
"""`add_*`가 돌려주는 도메인 객체와 결과 페이로드.

5.x의 `add_*` 24종은 반환이 객체·dict·str·int·tuple **5종 + `Any`**였다.
6.0의 규약은 하나다 — **모든 `add_*`는 방금 만든 것을 대표하는 살아있는
도메인 객체를 반환한다.** id가 필요하면 객체의 속성으로 읽는다.

집 스타일은 이미 정해져 있다:

- 살아있는 개체(문서를 계속 가리키는 것) → 클래스
  (`CheckBox`·`FormField`·`TrackedChange`·`BinaryItem`)
- 순수 결과 페이로드 → `@dataclass(frozen=True)` + `to_dict()`
  (`hwpx.mutation_report`의 `ChangedPart`·`PreservationSummary` 형태)
- 이미 발행된 JSON 스키마에 묶인 것 → `TypedDict` 유지
  (`hwpx.tools.table_navigation`의 `TableMapResult` 등)

WP-A는 이 패키지의 자리만 만든다. 내용은 WP-C가 채운다 — 설계서 §9의
배타적 파일 소유 규칙.
"""

from __future__ import annotations

from .binary_item import BinaryItem, PictureRef
from .checkbox import CheckBox
from .form_field import FieldLocation, FieldParameter, FormField
from .highlight import Highlight
from .results import (
    ColumnLayout,
    FieldFillResult,
    ListFormatResult,
    PageMargins,
    PageSetup,
    PageSize,
    ParagraphFormatResult,
    PictureReplacement,
    Units,
)
from .tracked import TrackedChange, TrackedReplacement

__all__ = [
    "BinaryItem",
    "CheckBox",
    "ColumnLayout",
    "FieldFillResult",
    "FieldLocation",
    "FieldParameter",
    "FormField",
    "Highlight",
    "ListFormatResult",
    "PageMargins",
    "PageSetup",
    "PageSize",
    "ParagraphFormatResult",
    "PictureRef",
    "PictureReplacement",
    "TrackedChange",
    "TrackedReplacement",
    "Units",
]
