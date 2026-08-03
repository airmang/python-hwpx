# SPDX-License-Identifier: Apache-2.0
"""공개 객체 모델 — stable 메서드가 돌려주는 타입들의 계약 이름.

## 무엇을 고치는가

5.x는 자기모순을 안고 있었다. `docs/stable-api.md`는

> `hwpx.oxml.*`, `hwpx._document.*` 등 내부 XML/구현 모듈을 직접 import하는
> 것은 **공개 표면이 아닙니다**

라고 선언하면서, 같은 문서가 stable로 선언한 `HwpxDocument`의 메서드들이
`HwpxOxmlParagraph`·`HwpxOxmlTable`·`HwpxOxmlSection` 등 **15종을 반환**했다.
사용자는 "비공개"라고 적힌 타입을 손에 쥐고 그것으로 일할 수밖에 없었다.

## 어떻게 고치는가

이 모듈은 **별칭 재수출이지 래퍼가 아니다.**

    hwpx.model.Paragraph is hwpx.oxml.paragraph.HwpxOxmlParagraph   # True

래퍼를 만들면 객체 모델이 두 벌이 되고, 래퍼는 결국 `.oxml`을 노출해야 하므로
같은 누출에 코드만 두 배가 된다. 반대로 `hwpx.oxml` 전체를 stable로 올리면
24개 모듈 수백 멤버가 major에서만 바뀔 수 있게 되어, 바로 그 클래스들에
요소를 더해야 하는 포맷 깊이 작업이 멈춘다.

그래서 **계약은 클래스가 아니라 멤버 allowlist다.**
`tests/data/model_surface.json`이 클래스별 stable 멤버를 정확히 나열한다.

- allowlist **안**의 멤버 → stable. major 경계에서만 바뀐다.
- allowlist **밖**의 멤버(`apply_model`·`mark_dirty`·`remove_stale_layout_caches` …)
  → 구현 세부. minor에서 바뀔 수 있다.

`hwpx.oxml.*` import 경로는 그대로 살아 있다. 옮기지도, deprecate하지도
않는다. 달라진 것은 문장 하나다 — **`hwpx.model`이 계약이고 `hwpx.oxml`은
그것이 사는 곳이다.**
"""

from __future__ import annotations

from .oxml.document_parts import HwpxOxmlDocument as Document
from .oxml.header_part import HwpxOxmlHeader as HeaderPart
from .oxml.memo import HwpxOxmlMemo as Memo
from .oxml.memo import HwpxOxmlMemoGroup as MemoGroup
from .oxml.memo import HwpxOxmlNote as Note
from .oxml.objects import HwpxOxmlInlineObject as InlineObject
from .oxml.objects import HwpxOxmlShape as Shape
from .oxml.paragraph import HwpxOxmlParagraph as Paragraph
from .oxml.run import HwpxOxmlRun as Run
from .oxml.section import HwpxOxmlSection as Section
from .oxml.section_format import HwpxOxmlSectionProperties as SectionProperties
from .oxml.section_story import HwpxOxmlSectionHeaderFooter as HeaderFooter
from .oxml.simple_parts import HwpxOxmlHistory as History
from .oxml.simple_parts import HwpxOxmlMasterPage as MasterPage
from .oxml.simple_parts import HwpxOxmlVersion as Version
from .oxml.table import HwpxOxmlTable as Table
from .oxml.table import HwpxOxmlTableCell as TableCell
from .oxml.table import HwpxOxmlTableRow as TableRow

__all__ = [
    "Document",
    "HeaderFooter",
    "HeaderPart",
    "History",
    "InlineObject",
    "MasterPage",
    "Memo",
    "MemoGroup",
    "Note",
    "Paragraph",
    "Run",
    "Section",
    "SectionProperties",
    "Shape",
    "Table",
    "TableCell",
    "TableRow",
    "Version",
]
