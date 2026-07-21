# SPDX-License-Identifier: Apache-2.0
"""실험적(experimental) 공개 표면.

여기 노출되는 이름들은 **계약이 유동적**입니다 — minor 릴리스에서 시그니처,
동작, 반환 스키마가 예고 없이 바뀔 수 있습니다. 안정 계약이 필요하면 stable 표면
(:mod:`hwpx` 최상위 ``__all__`` / ``docs/stable-api.md``)만 사용하세요.

이 모듈은 실제 구현 모듈에서 이름을 **재내보내기(re-export)** 만 합니다(모듈을
옮기지 않음). 최상위 ``from hwpx import ...`` 경로도 하위 호환을 위해 당분간
동작하지만 ``DeprecationWarning``을 내며 다음 major에서 제거될 예정입니다 —
새 코드는 ``from hwpx.experimental import ...``를 쓰세요.
"""

from __future__ import annotations

from .ingest import (
    ConversionAttempt,
    DocumentConverter,
    DocumentIngestError,
    DocumentIngestResult,
    DocumentIngestor,
    DocumentSourceInfo,
    UnsupportedDocumentFormat,
)
from .tools.document_viewer import (
    DocumentViewer,
    render_document_viewer,
)
from .tools.layout_preview import (
    LayoutPreview,
    PreviewPage,
    render_layout_preview,
)

__all__ = [
    "ConversionAttempt",
    "DocumentConverter",
    "DocumentIngestError",
    "DocumentIngestResult",
    "DocumentIngestor",
    "DocumentSourceInfo",
    "UnsupportedDocumentFormat",
    "LayoutPreview",
    "PreviewPage",
    "render_layout_preview",
    "DocumentViewer",
    "render_document_viewer",
]
