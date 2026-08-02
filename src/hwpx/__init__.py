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
from dataclasses import dataclass
from typing import Literal


def _resolve_version() -> str:
    """패키지 메타데이터에서 배포 버전을 조회합니다(import는 함수 스코프 유지)."""
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version("python-hwpx")
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
    # 수식 저작(5.2.0 신규, LaTeX -> EqEdit). 계약 유동.
    "UnsupportedLatexError": "hwpx.equation.authoring",
    "estimate_equation_size": "hwpx.equation.authoring",
    "latex_to_eqedit": "hwpx.equation.authoring",
    # 편집 계획 실행기(5.6.0 신규, 선언적 다단 편집 -> 원자 실행). 계약 유동.
    "EditPlan": "hwpx.plan",
    "PlanReport": "hwpx.plan",
    "PlanValidationError": "hwpx.plan",
    "apply_edit_plan": "hwpx.plan",
    "validate_edit_plan": "hwpx.plan",
    # 기계가독 자기서술(5.6.0 신규, 드리프트 가드 포함). 계약 유동.
    # 함수명은 describe_capabilities — 모듈 hwpx.capabilities와 이름이 같으면
    # 서브모듈 바인딩이 lazy 알리아스를 그림자로 가려 경고 계약이 깨진다.
    "describe_capabilities": "hwpx.capabilities",
    "contract_document": "hwpx.capabilities",
    "contract_json_schema": "hwpx.capabilities",
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


# --- 5.0에서 이동한 이름 -------------------------------------------------
#
# 응용 워크플로는 companion 패키지가 소유한다. 여기 남는 것은 **표뿐**이다 —
# 그 패키지를 import하지 않는다. 설치돼 있는지에 따라 core의 동작이 달라지면
# 의존 방향이 뒤집히고, 그건 5.0이 없애려던 바로 그 결합이다.
#
# 표가 하는 일은 오류 메시지 하나다. 기본 Python 오류는 이름이 사라졌다는 것만
# 알려주고 어디로 갔는지는 말해주지 않는다.
_SurfaceKind = Literal["symbol", "module", "renamed", "retired"]


@dataclass(frozen=True, slots=True)
class _CompanionSurface:
    """One executable migration hint without importing the companion."""

    kind: _SurfaceKind
    target_module: str | None = None
    target_name: str | None = None
    replacement: str | None = None

    def import_statement(self, legacy_name: str) -> str | None:
        if self.kind == "retired":
            return None
        if self.target_module is None:
            raise AssertionError(f"{legacy_name}: target_module is required")
        if self.kind == "module" or (
            self.kind == "renamed" and self.target_name is None
        ):
            return f"import {self.target_module} as {legacy_name}"
        target_name = self.target_name or legacy_name
        alias = f" as {legacy_name}" if target_name != legacy_name else ""
        return f"from {self.target_module} import {target_name}{alias}"


def _symbol(target_module: str, target_name: str | None = None) -> _CompanionSurface:
    return _CompanionSurface("symbol", target_module, target_name)


def _module(target_module: str) -> _CompanionSurface:
    return _CompanionSurface("module", target_module)


def _renamed(
    target_module: str,
    target_name: str | None = None,
) -> _CompanionSurface:
    return _CompanionSurface("renamed", target_module, target_name)


_MOVED_TO_COMPANION: dict[str, _CompanionSurface] = {
    "AUTHORING_REPORT_VERSION": _symbol("hwpx_automation.office.authoring"),
    "DEFAULT_STYLE_PRESET": _symbol("hwpx_automation.office.authoring"),
    "DOCUMENT_PLAN_SCHEMA_VERSION": _symbol("hwpx_automation.office.authoring"),
    "DocumentBlock": _symbol("hwpx_automation.office.authoring"),
    "DocumentPlan": _symbol("hwpx_automation.office.authoring"),
    "DocumentStylePreset": _symbol("hwpx_automation.office.authoring"),
    "OFFICIAL_DOCUMENT_STYLE_REPORT_VERSION": _symbol(
        "hwpx_automation.office.compliance.official_lint"
    ),
    "PlanValidationIssue": _symbol("hwpx_automation.office.authoring"),
    "PlanValidationReport": _symbol("hwpx_automation.office.authoring"),
    "STYLE_PROFILE_COMPARISON_SCHEMA_VERSION": _symbol(
        "hwpx_automation.office.authoring.style_profile"
    ),
    "STYLE_PROFILE_SCHEMA_VERSION": _symbol(
        "hwpx_automation.office.authoring.style_profile"
    ),
    "TABLE_COMPUTE_REPORT_VERSION": _symbol("hwpx_automation.office.utilities"),
    "TEMPLATE_REGISTRY_SCHEMA_VERSION": _symbol(
        "hwpx_automation.office.authoring.style_profile"
    ),
    "agent": _module("hwpx_automation.office.agent"),
    "apply_style_profile_to_plan": _symbol(
        "hwpx_automation.office.authoring.style_profile"
    ),
    "approval_box": _symbol("hwpx_automation.office.authoring.builder"),
    "authoring": _module("hwpx_automation.office.authoring"),
    "build_comparison_table_plan": _symbol(
        "hwpx_automation.office.document_ops"
    ),
    "build_image_grid": _symbol("hwpx_automation.office.authoring"),
    "build_meeting_nameplates": _symbol(
        "hwpx_automation.office.authoring.advanced_generators"
    ),
    "build_organization_chart": _symbol(
        "hwpx_automation.office.authoring.advanced_generators"
    ),
    "builder": _module("hwpx_automation.office.authoring.builder"),
    "compare_style_profiles": _symbol(
        "hwpx_automation.office.authoring.style_profile"
    ),
    "create_document_from_plan": _symbol("hwpx_automation.office.authoring"),
    "describe_template": _symbol(
        "hwpx_automation.office.authoring.style_profile"
    ),
    "design": _module("hwpx_automation.office.authoring.design"),
    "evalplan_fill": _renamed("hwpx_automation.office.evalplan"),
    "exam": _module("hwpx_automation.office.exam"),
    "extract_style_profile": _symbol(
        "hwpx_automation.office.authoring.style_profile"
    ),
    "fill_residue": _module(
        "hwpx_automation.office.form_fill.fill_residue"
    ),
    "form_fill": _module("hwpx_automation.office.form_fill"),
    "formfill_quality": _renamed(
        "hwpx_automation.office.form_fill.quality"
    ),
    "get_document_plan_schema": _symbol("hwpx_automation.office.authoring"),
    "guidance_scan": _renamed(
        "hwpx_automation.office.form_fill.guidance"
    ),
    "inspect_document_authoring_quality": _symbol(
        "hwpx_automation.office.authoring"
    ),
    "inspect_official_document_style": _symbol(
        "hwpx_automation.office.compliance.official_lint"
    ),
    "inspect_operating_plan_quality": _symbol(
        "hwpx_automation.office.authoring"
    ),
    "list_templates": _symbol(
        "hwpx_automation.office.authoring.style_profile"
    ),
    "mail_merge": _renamed(
        "hwpx_automation.office.document_ops",
        "build_mail_merge",
    ),
    "normalize_document_plan": _symbol("hwpx_automation.office.authoring"),
    "placeholder_fill_report": _symbol(
        "hwpx_automation.office.authoring.style_profile"
    ),
    "presets": _module("hwpx_automation.office.authoring.presets"),
    "register_template": _symbol(
        "hwpx_automation.office.authoring.style_profile"
    ),
    "table_compute": _symbol("hwpx_automation.office.utilities"),
    "template_formfit": _module(
        "hwpx_automation.office.form_fill.template_formfit"
    ),
    "validate_document_plan": _symbol("hwpx_automation.office.authoring"),
    "visual": _renamed("hwpx_automation.office.rendering"),
}

_RETIRED_SURFACES: dict[str, _CompanionSurface] = {
    "analyze_template_formfit": _CompanionSurface(
        "retired",
        replacement=(
            "MCP analyze_form_fill → apply_form_fill → verify_form_fill 경로를 "
            "사용하세요."
        ),
    ),
    "apply_template_formfit": _CompanionSurface(
        "retired",
        replacement=(
            "MCP analyze_form_fill → apply_form_fill → verify_form_fill 경로를 "
            "사용하세요."
        ),
    ),
    "TEMPLATE_FORMFIT_BASELINE_SCHEMA_VERSION": _CompanionSurface(
        "retired",
        replacement="새 form-fill ToolSpec 스키마를 사용하세요.",
    ),
    "TEMPLATE_FORMFIT_PLAN_SCHEMA_VERSION": _CompanionSurface(
        "retired",
        replacement="새 form-fill ToolSpec 스키마를 사용하세요.",
    ),
}


class MovedToCompanion(ImportError):
    """이동한 이름에 접근했다.

    ImportError인 이유. ``from hwpx import X``는 모듈 ``__getattr__``이 던진
    AttributeError를 잡아 자기만의 밋밋한 ImportError로 바꿔버린다 — 행선지를
    적어 넣어도 사용자에게 닿지 않는다는 뜻이다. ImportError로 던지면 그대로
    올라간다. 공개 코드에서 깨지는 형태가 압도적으로 ``from hwpx import X``라
    그쪽을 택했다.

    대가는 ``hasattr(hwpx, "...")``이다. Python의 hasattr은 AttributeError만
    잡으므로 False 대신 예외가 나간다. 둘 다 상속해서 해결하려 했지만
    ImportError와 AttributeError는 C 레벨 레이아웃이 충돌해 불가능하다.
    예외가 나가더라도 메시지가 이유를 말해주므로 조용히 False가 되는 것보다는
    낫다고 판단했다.
    """


class RetiredSurface(ImportError):
    """A removed compatibility surface whose replacement is not another import."""


def __getattr__(name: str) -> object:
    """Resolve dynamic module attributes.

    ``__version__``은 경고 없이 지연 해석하고, experimental/deprecated 이름은
    해석 시 ``DeprecationWarning``을 냅니다.
    """

    if name == "__version__":
        return _resolve_version()

    module_name = _EXPERIMENTAL_EXPORTS.get(name)
    if module_name is not None:
        if module_name != "hwpx" and not module_name.startswith("hwpx."):
            raise AttributeError(
                "hwpx lazy-export targets must remain inside the 'hwpx' package"
            )
        warnings.warn(_experimental_message(name), DeprecationWarning, stacklevel=2)
        return getattr(importlib.import_module(module_name), name)

    module_name = _DEPRECATED_EXPORTS.get(name)
    if module_name is not None:
        if module_name != "hwpx" and not module_name.startswith("hwpx."):
            raise AttributeError(
                "hwpx lazy-export targets must remain inside the 'hwpx' package"
            )
        warnings.warn(_deprecated_message(name), DeprecationWarning, stacklevel=2)
        return getattr(importlib.import_module(module_name), name)

    moved = _MOVED_TO_COMPANION.get(name)
    if moved is not None:
        statement = moved.import_statement(name)
        assert statement is not None
        raise MovedToCompanion(
            f"{name}은(는) python-hwpx 5.0에서 companion 패키지로 이동했습니다.\n"
            f"    pip install python-hwpx-automation\n"
            f"    {statement}\n"
            f'4.x를 계속 쓰려면: pip install "python-hwpx<5"\n'
            f"전체 대체표: docs/migration-5.0.md"
        )

    retired = _RETIRED_SURFACES.get(name)
    if retired is not None:
        raise RetiredSurface(
            f"{name}은(는) 예고대로 python-hwpx 5.0에서 제거되었습니다. "
            f"{retired.replacement}\n"
            f'4.x를 계속 쓰려면: pip install "python-hwpx<5"\n'
            f"전체 대체표: docs/migration-5.0.md"
        )

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
