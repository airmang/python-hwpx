# SPDX-License-Identifier: Apache-2.0
"""`HwpxDocument`의 11개 도메인 네임스페이스.

경계는 발명한 것이 아니라 `hwpx.capabilities._CAPABILITY_AREAS`에서 유도했다.
그 레지스트리는 이미 모든 `add_*`를 정확히 한 능력 영역에 귀속시키고,
`tests/test_capabilities_surface.py`가 그것을 라이브 클래스에 대조해 CI로
강제한다. 같은 분할을 표면에 그대로 쓰면 네임스페이스 경계도 기계 검증
대상이 된다.

| 능력 영역 | 네임스페이스 |
|---|---|
| `shape-authoring`·`shape-escape-hatch`·`curve-objects`·`chart`·`equation` | `doc.shapes` |
| `picture`(BinData 절반) | `doc.media` |
| `redline` | `doc.tracking` |
| `memo`·`footnote-endnote` | `doc.notes` |
| `toc-crossref` | `doc.refs` |
| `form-field-create`·`check-box` | `doc.fields` |
| `table-structure`·`form-fill` | `doc.tables` |

나머지 네 개(`doc.styles`·`doc.page`·`doc.text`·`doc.parts`)는 `add_*`가 아니라
레지스트리가 다루지 않는 축이라 표면 축(서식 정의·쪽 기하·텍스트·OPC 파트)으로
나눴다.
"""

from __future__ import annotations

from .fields import FieldsNamespace
from .media import MediaNamespace
from .notes import NotesNamespace
from .page import PageNamespace
from .parts import PartsNamespace
from .refs import RefsNamespace
from .shapes import ShapesNamespace
from .styles import StylesNamespace
from .tables import TablesNamespace
from .text import TextNamespace
from .tracking import TrackingNamespace

#: 루트 속성 이름 → 네임스페이스 클래스. `HwpxDocument`가 이 표대로 속성을
#: 노출하고, 게이트 테스트가 같은 표로 표면을 대조한다.
NAMESPACES = {
    "styles": StylesNamespace,
    "tables": TablesNamespace,
    "fields": FieldsNamespace,
    "shapes": ShapesNamespace,
    "media": MediaNamespace,
    "notes": NotesNamespace,
    "refs": RefsNamespace,
    "tracking": TrackingNamespace,
    "page": PageNamespace,
    "text": TextNamespace,
    "parts": PartsNamespace,
}

__all__ = [
    "NAMESPACES",
    "FieldsNamespace",
    "MediaNamespace",
    "NotesNamespace",
    "PageNamespace",
    "PartsNamespace",
    "RefsNamespace",
    "ShapesNamespace",
    "StylesNamespace",
    "TablesNamespace",
    "TextNamespace",
    "TrackingNamespace",
]
