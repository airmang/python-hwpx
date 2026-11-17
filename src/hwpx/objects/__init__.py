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

7.0은 stable 이름이 돌려주는데 어느 계약에도 없던 형식 26개(``Style``·``RunStyle``·
``ParagraphProperty``·``Font``·``Caption``·``GridPosition`` …, 결정 D15)를 이 모듈에서도
내보내 잠근다. 같은 객체다(구현 모듈의 클래스를 그대로 다시 내보낸다). 구현 모듈이 이
패키지보다 늦게 읽히므로 처음 꺼낼 때 읽는다(:data:`_RE_EXPORTED`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .binary_item import BinaryItem
from .checkbox import Button, CheckBox, ComboBox, EditBox, RadioButton
from .form_field import (
    Bookmark,
    CellField,
    CrossReference,
    FieldControl,
    FieldLocation,
    FieldParameter,
    FormField,
    FormulaField,
    Hyperlink,
    TableOfContents,
    TextBoxField,
    TocEntry,
)
from .highlight import ComposedCharacter, Highlight, Ruby
from .results import (
    Alignment,
    BorderFillInfo,
    BorderLine,
    CellMargins,
    CellZone,
    ClearBodyReport,
    ColumnLayout,
    FieldFillResult,
    FontReplaceReport,
    LineSegment,
    LineSpacing,
    LineSpacingType,
    ListFormatResult,
    NumberingInfo,
    NumberingLevel,
    ObjectPosition,
    PageMargins,
    PageSetup,
    PageSize,
    ParagraphFormatResult,
    PictureReplacement,
    Units,
)
from .results import (  # 쪽·구역 설정의 읽기 값 (doc.page / doc.parts)
    AutoNumber,
    BeginNumbers,
    ColumnDefinition,
    DocumentOptions,
    InlineItem,
    NoteShapeInfo,
    NumberRestart,
    ObjectPlace,
    PageBorder,
    PageHiding,
    PageNumberControl,
    ParagraphPlace,
    StartNumbers,
    SwitchChoice,
)
from .results import LanguageFonts, TextMatch  # run.fonts, doc.text.find()
from .tracked import TrackedChange, TrackedReplacement

if TYPE_CHECKING:
    from .._document.text_blocks import TextBlock, TextChangeReport, TextOutline
    from ..hwp5.errors import Hwp5ConversionReport
    from ..oxml.common import GenericElement
    from ..oxml.container import ContainerMember
    from ..oxml.document_metadata import DocumentMetadata
    from ..oxml.header import (
        Bullet,
        Font,
        MemoShape,
        ParagraphProperty,
        Style,
        TabDefinition,
        TrackChange,
        TrackChangeAuthor,
    )
    from ..oxml.objects import Caption
    from ..oxml.run import RunStyle
    from ..oxml.section_format import LineNumberShape, SectionGrid, SectionVisibility
    from ..oxml.shape_position import PictureGlow, PictureReflection, PictureShadow
    from ..oxml.table import HwpxTableGridPosition as GridPosition
    from ..tools.table_navigation import TableMapResult
    from ..tools.validator import ValidationReport

#: D15: 다시 내보내는 형식 → ``(구현 모듈, 클래스 이름)``. 처음 꺼낼 때 읽어 모듈에 붙인다.
_RE_EXPORTED: dict[str, tuple[str, str]] = {
    "Bullet": ("hwpx.oxml.header", "Bullet"),
    "Font": ("hwpx.oxml.header", "Font"),
    "MemoShape": ("hwpx.oxml.header", "MemoShape"),
    "ParagraphProperty": ("hwpx.oxml.header", "ParagraphProperty"),
    "Style": ("hwpx.oxml.header", "Style"),
    "TabDefinition": ("hwpx.oxml.header", "TabDefinition"),
    "TrackChange": ("hwpx.oxml.header", "TrackChange"),
    "TrackChangeAuthor": ("hwpx.oxml.header", "TrackChangeAuthor"),
    "RunStyle": ("hwpx.oxml.run", "RunStyle"),
    "LineNumberShape": ("hwpx.oxml.section_format", "LineNumberShape"),
    "SectionGrid": ("hwpx.oxml.section_format", "SectionGrid"),
    "SectionVisibility": ("hwpx.oxml.section_format", "SectionVisibility"),
    "DocumentMetadata": ("hwpx.oxml.document_metadata", "DocumentMetadata"),
    "TextBlock": ("hwpx._document.text_blocks", "TextBlock"),
    "TextChangeReport": ("hwpx._document.text_blocks", "TextChangeReport"),
    "TextOutline": ("hwpx._document.text_blocks", "TextOutline"),
    "ValidationReport": ("hwpx.tools.validator", "ValidationReport"),
    "Hwp5ConversionReport": ("hwpx.hwp5.errors", "Hwp5ConversionReport"),
    "TableMapResult": ("hwpx.tools.table_navigation", "TableMapResult"),
    "GridPosition": ("hwpx.oxml.table", "HwpxTableGridPosition"),
    "Caption": ("hwpx.oxml.objects", "Caption"),
    "PictureGlow": ("hwpx.oxml.shape_position", "PictureGlow"),
    "PictureReflection": ("hwpx.oxml.shape_position", "PictureReflection"),
    "PictureShadow": ("hwpx.oxml.shape_position", "PictureShadow"),
    "ContainerMember": ("hwpx.oxml.container", "ContainerMember"),
    "GenericElement": ("hwpx.oxml.common", "GenericElement"),
}


def _implementation_module(path: str) -> Any:
    # Plain relative imports (the product-boundary gate allows no importlib here).
    if path == "hwpx.oxml.header":
        from ..oxml import header as module
    elif path == "hwpx.oxml.run":
        from ..oxml import run as module
    elif path == "hwpx.oxml.section_format":
        from ..oxml import section_format as module
    elif path == "hwpx.oxml.document_metadata":
        from ..oxml import document_metadata as module
    elif path == "hwpx._document.text_blocks":
        from .._document import text_blocks as module
    elif path == "hwpx.tools.validator":
        from ..tools import validator as module
    elif path == "hwpx.hwp5.errors":
        from ..hwp5 import errors as module
    elif path == "hwpx.tools.table_navigation":
        from ..tools import table_navigation as module
    elif path == "hwpx.oxml.table":
        from ..oxml import table as module
    elif path == "hwpx.oxml.objects":
        from ..oxml import objects as module
    elif path == "hwpx.oxml.shape_position":
        from ..oxml import shape_position as module
    elif path == "hwpx.oxml.container":
        from ..oxml import container as module
    else:
        from ..oxml import common as module
    return module


def __getattr__(name: str) -> Any:
    target = _RE_EXPORTED.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(_implementation_module(target[0]), target[1])
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_RE_EXPORTED))


__all__ = [
    "Alignment",
    "AutoNumber",
    "BeginNumbers",
    "ColumnDefinition",
    "DocumentOptions",
    "InlineItem",
    "NoteShapeInfo",
    "NumberRestart",
    "ObjectPlace",
    "PageBorder",
    "PageHiding",
    "PageNumberControl",
    "ParagraphPlace",
    "StartNumbers",
    "SwitchChoice",
    "BinaryItem",
    "Bookmark",
    "BorderFillInfo",
    "BorderLine",
    "Button",
    "CellField",
    "TextBoxField",
    "CellMargins",
    "CellZone",
    "CheckBox",
    "ClearBodyReport",
    "ComboBox",
    "ComposedCharacter",
    "CrossReference",
    "EditBox",
    "Hyperlink",
    "RadioButton",
    "Ruby",
    "ColumnLayout",
    "FieldFillResult",
    "FieldControl",
    "FieldLocation",
    "FieldParameter",
    "FontReplaceReport",
    "LineSegment",
    "LanguageFonts",
    "LineSpacing",
    "LineSpacingType",
    "FormField",
    "FormulaField",
    "Highlight",
    "ListFormatResult",
    "NumberingInfo",
    "NumberingLevel",
    "ObjectPosition",
    "PageMargins",
    "PageSetup",
    "PageSize",
    "ParagraphFormatResult",
    "PictureReplacement",
    "TableOfContents",
    "TextMatch",
    "TocEntry",
    "TrackedChange",
    "TrackedReplacement",
    "Units",
    # D15: 7.0에서 계약에 올린 형식(구현 모듈의 클래스를 그대로 다시 내보낸다)
    "Bullet",
    "Caption",
    "ContainerMember",
    "DocumentMetadata",
    "Font",
    "GenericElement",
    "GridPosition",
    "Hwp5ConversionReport",
    "LineNumberShape",
    "MemoShape",
    "ParagraphProperty",
    "PictureGlow",
    "PictureReflection",
    "PictureShadow",
    "RunStyle",
    "SectionGrid",
    "SectionVisibility",
    "Style",
    "TabDefinition",
    "TableMapResult",
    "TextBlock",
    "TextChangeReport",
    "TextOutline",
    "TrackChange",
    "TrackChangeAuthor",
    "ValidationReport",
]
