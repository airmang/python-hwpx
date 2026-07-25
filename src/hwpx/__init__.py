# SPDX-License-Identifier: Apache-2.0
"""High-level utilities for working with HWPX documents.

최상위 ``from hwpx import ...`` 표면은 세 계층으로 나뉩니다(정책·전수 목록:
``docs/stable-api.md``):

- **stable** — ``__all__``에 있는 이름. 계약이 굳었고 major 경계에서만 깨질 수 있음.
- **experimental** — 계약이 유동적. ``from hwpx.experimental import ...``로 쓰세요.
  최상위 재내보내기는 하위 호환을 위해 유지하되 접근 시 ``DeprecationWarning``이 나며
  다음 major에서 제거될 예정입니다.
- **deprecated** — 대체 경로로 이전하세요. 접근 시 ``DeprecationWarning``이 납니다.
"""

import importlib
import warnings
from importlib.metadata import PackageNotFoundError, version as _metadata_version


def _resolve_version() -> str:
    """패키지 메타데이터에서 현재 배포 버전을 조회합니다."""
    try:
        return _metadata_version("python-hwpx")
    except PackageNotFoundError:
        return "0+unknown"


# --- experimental / deprecated 최상위 표면 (지연 접근, 접근 시 경고) ---------------
#
# stable 이름은 아래에서 eager import 되어 모듈 전역에 존재하므로 ``__getattr__``이
# 호출되지 않습니다(=경고 없음). 여기 등록된 이름만 지연 해석되어 경고를 냅니다.
# 4.0.0에서 제거되는 이름은 0개 — 모두 계속 import 가능합니다.

_EXPERIMENTAL_EXPORTS = {
    # 문서 ingestion 프레임워크(임의 포맷 -> HWPX). 계약 유동.
    "ConversionAttempt": "hwpx.ingest",
    "DocumentConverter": "hwpx.ingest",
    "DocumentIngestError": "hwpx.ingest",
    "DocumentIngestResult": "hwpx.ingest",
    "DocumentIngestor": "hwpx.ingest",
    "DocumentSourceInfo": "hwpx.ingest",
    "UnsupportedDocumentFormat": "hwpx.ingest",
    # 레이아웃 프리뷰(한컴 없는 정직 근사). 계약 유동.
    "LayoutPreview": "hwpx.tools.layout_preview",
    "PreviewPage": "hwpx.tools.layout_preview",
    "render_layout_preview": "hwpx.tools.layout_preview",
    # 문서 프리뷰 뷰어(3.8.0 신규). 계약 유동.
    "DocumentViewer": "hwpx.tools.document_viewer",
    "render_document_viewer": "hwpx.tools.document_viewer",
}

# Emptied in 5.0. The 4.x notice on these names said they would go in the next
# major, and this is it: analyze_template_formfit, apply_template_formfit and the
# two schema-version constants are gone with hwpx.template_formfit. Use
# hwpx.table_patch.fill_cells, or the MCP form-fill trio.
_DEPRECATED_EXPORTS: dict[str, str] = {}

# deprecated formfit 표면의 공통 대체 경로 안내.
_FORMFIT_REPLACEMENT = (
    "구조적 form-fill 경로를 사용하세요: 라이브러리는 "
    "hwpx.table_patch.fill_cells 계열, MCP는 analyze_form_fill/apply_form_fill/"
    "verify_form_fill."
)


def _experimental_message(name: str) -> str:
    return (
        f"'hwpx.{name}'는 실험적(experimental) 표면입니다. 계약이 유동적이므로 "
        f"'from hwpx.experimental import {name}'로 import하세요. 최상위 재내보내기는 "
        f"다음 major에서 제거될 예정입니다."
    )


def _deprecated_message(name: str) -> str:
    return (
        f"'hwpx.{name}'는 deprecated입니다. {_FORMFIT_REPLACEMENT} 이 이름은 "
        f"다음 major에서 제거될 예정입니다."
    )


def __getattr__(name: str) -> object:
    """Resolve dynamic module attributes.

    ``__version__``은 경고 없이 지연 해석하고, experimental/deprecated 이름은
    해석 시 ``DeprecationWarning``을 냅니다.
    """

    if name == "__version__":
        return _resolve_version()

    module_name = _EXPERIMENTAL_EXPORTS.get(name)
    if module_name is not None:
        warnings.warn(_experimental_message(name), DeprecationWarning, stacklevel=2)
        return getattr(importlib.import_module(module_name), name)

    module_name = _DEPRECATED_EXPORTS.get(name)
    if module_name is not None:
        warnings.warn(_deprecated_message(name), DeprecationWarning, stacklevel=2)
        return getattr(importlib.import_module(module_name), name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(
        set(globals())
        | set(__all__)
        | set(_EXPERIMENTAL_EXPORTS)
        | set(_DEPRECATED_EXPORTS)
    )


# --- stable 최상위 표면 (eager import) ------------------------------------------
from .tools.text_extractor import (
    DEFAULT_NAMESPACES,
    ParagraphInfo,
    SectionInfo,
    TextExtractor,
)
from .tools.object_finder import FoundElement, ObjectFinder
from .tools.doc_diff import (
    DOC_DIFF_REPORT_VERSION,
    REFERENCE_CONSISTENCY_REPORT_VERSION,
    diff_paragraphs,
    doc_diff,
    inspect_reference_consistency,
)
from .tools.mail_merge import (
    MAIL_MERGE_REPORT_VERSION,
    inspect_mail_merge_placeholders,
    load_mail_merge_rows,
    merge_template_rows,
)
from .tools.package_validator import (
    EditorOpenSafetyReport,
    PackageValidationReport,
    validate_editor_open_safety,
    validate_package,
)
from .ingest import HwpxMarkdownConverter
from .errors import HwpxError
from .mutation_report import (
    MutationReport,
    PreservationDowngradeError,
)
from .patch import (
    BytePreservingPatchResult,
    ParagraphTextPatch,
    PatchApplied,
    PatchSkipped,
    paragraph_patch,
)
from .document import HwpxDocument
from .package import HwpxPackage
from .quality import (
    QualityPolicy,
    SavePipeline,
    VisualCompleteReport,
)

__all__ = [
    "inspect_reference_consistency",
    "doc_diff",
    "diff_paragraphs",
    "REFERENCE_CONSISTENCY_REPORT_VERSION",
    "DOC_DIFF_REPORT_VERSION",
    "merge_template_rows",
    "load_mail_merge_rows",
    "inspect_mail_merge_placeholders",
    "MAIL_MERGE_REPORT_VERSION",
    "QualityPolicy",
    "SavePipeline",
    "VisualCompleteReport",
    "__version__",
    "DEFAULT_NAMESPACES",
    "EditorOpenSafetyReport",
    "ParagraphInfo",
    "PackageValidationReport",
    "BytePreservingPatchResult",
    "HwpxError",
    "MutationReport",
    "PreservationDowngradeError",
    "ParagraphTextPatch",
    "PatchApplied",
    "PatchSkipped",
    "SectionInfo",
    "TextExtractor",
    "FoundElement",
    "HwpxMarkdownConverter",
    "ObjectFinder",
    "HwpxDocument",
    "HwpxPackage",
    "validate_editor_open_safety",
    "validate_package",
    "paragraph_patch",
]
