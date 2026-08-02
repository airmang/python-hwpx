# SPDX-License-Identifier: Apache-2.0
"""``hwpx.capabilities`` — 기계가독 자기서술 (experimental, 5.6.0 신규).

동기(실측 드리프트 사례): 사람 손으로 갱신하는 자기서술 문서는 릴리스 트레인
하루 만에도 실표면과 드리프트한다. 이 모듈이 단일 진실 원천이고, 드리프트
가드 테스트가 다음 세 방향을 강제한다:

1. 여기 등재된 진입점은 전부 실제로 import 가능해야 한다.
2. ``editPlanOps``는 :data:`hwpx.plan.PLAN_OPS`·실행 디스패치·edit-plan JSON
   Schema enum과 일치해야 한다.
3. :data:`_CAPABILITY_AREAS`의 매트릭스 행 제목은 ``docs/support-matrix.md``
   표의 행 제목과 집합 일치해야 한다.

**core는 환경 변수를 읽지 않는다** — 렌더 오라클 가용성은 여기 없다(자기서술은
``renderOracle.bundled="none"``으로 그 사실 자체를 말한다). 오라클 탐지·실행은
automation 계층(python-hwpx-automation)이 보고한다.
"""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Any

from .errors import HwpxError

CAPABILITIES_SCHEMA = "hwpx.capabilities/v1"

_DIST_NAME = "python-hwpx"

#: extras 이름 → 그 extra가 끄는 런타임 모듈들. ``visual``은 5.0부터 의도적으로
#: 빈 extra(설치 호환 유지용)라 백킹 모듈이 없고, 프로브는 공허하게 참이다.
_EXTRA_MODULES: dict[str, tuple[str, ...]] = {
    "visual": (),
    "xlsx": ("openpyxl",),
    "preview": ("latex2mathml",),
}

#: 능력 영역 레지스트리. ``matrix_row``는 ``docs/support-matrix.md`` 표 1열
#: 제목과 **정확히** 일치해야 한다(가드 테스트가 집합 대조). ``entry_points``는
#: ``"모듈:이름"`` — 전부 import 가능해야 한다(가드 테스트가 해석).
_CAPABILITY_AREAS: tuple[dict[str, Any], ...] = (
    {
        "area": "paragraph-table-authoring",
        "matrix_row": "문단·표 저작/편집",
        "entry_points": ("hwpx.document:HwpxDocument",),
    },
    {
        "area": "table-structure",
        "matrix_row": "표 구조 변경(행·열·표 삭제/삽입, 열 오토핏)",
        "entry_points": ("hwpx.table_patch:apply_table_ops",),
    },
    {
        "area": "table-create",
        "matrix_row": "표 생성(병합·중첩 포함)",
        "entry_points": ("hwpx.document:HwpxDocument",),
    },
    {
        "area": "form-fill",
        "matrix_row": "양식 채움(byte-splice)",
        "entry_points": (
            "hwpx.patch:paragraph_patch",
            "hwpx.table_patch:fill_cells",
            "hwpx.body_patch:apply_body_ops",
        ),
    },
    {
        "area": "edit-plan",
        "matrix_row": "편집 계획 실행(edit plan)",
        "entry_points": (
            "hwpx.plan:apply_edit_plan",
            "hwpx.plan:validate_edit_plan",
        ),
    },
    {
        "area": "shape-authoring",
        "matrix_row": "도형 저작(선·사각형·타원)",
        "entry_points": ("hwpx.document:HwpxDocument",),
    },
    {
        "area": "shape-escape-hatch",
        "matrix_row": "저수준 도형·컨트롤 탈출구",
        "entry_points": ("hwpx.document:HwpxDocument",),
    },
    {
        "area": "curve-objects",
        "matrix_row": "arc·polygon·curve·connectLine",
        "entry_points": (),
    },
    {
        "area": "picture",
        "matrix_row": "그림 삽입/치환",
        "entry_points": ("hwpx.document:HwpxDocument",),
    },
    {
        "area": "chart",
        "matrix_row": "차트",
        "entry_points": ("hwpx.document:HwpxDocument",),
    },
    {
        "area": "equation",
        "matrix_row": "수식",
        "entry_points": ("hwpx.equation.authoring:latex_to_eqedit",),
    },
    {
        "area": "redline",
        "matrix_row": "변경추적(redline)",
        "entry_points": ("hwpx.tools.redline:verify_redline",),
    },
    {
        "area": "memo",
        "matrix_row": "메모(코멘트)",
        "entry_points": ("hwpx.document:HwpxDocument",),
    },
    {
        "area": "footnote-endnote",
        "matrix_row": "각주/미주",
        "entry_points": ("hwpx.document:HwpxDocument",),
    },
    {
        "area": "toc-crossref",
        "matrix_row": "네이티브 목차(TOC)/상호참조",
        "entry_points": ("hwpx.tools.toc_author:add_native_toc",),
    },
    {
        "area": "encrypted-hwpx",
        "matrix_row": "암호화 HWPX",
        "entry_points": (),
    },
    {
        "area": "hwp5-binary",
        "matrix_row": "HWP 5.x 바이너리",
        "entry_points": (),
    },
    {
        "area": "form-field-create",
        "matrix_row": "누름틀(form field) 생성",
        "entry_points": ("hwpx.document:HwpxDocument",),
    },
)

#: 패키지에 동봉되는 계약 문서 이름 → 파일. MCP resources 표면의 원천.
_CONTRACT_DOCS: dict[str, str] = {
    "support-matrix": "support-matrix.md",
    "recipes-traversal": "recipes-traversal.md",
    "mutation-semantics": "mutation-semantics.md",
    "known-traps": "known-traps.md",
}

_CONTRACT_DOCS_DIR = Path(__file__).resolve().parent / "data" / "contract_docs"


def _extra_installed(extra: str) -> bool:
    """extra 설치 여부 — 함수 스코프 **정적 import** try/except 프로브.

    core의 importlib 표면은 boundary ratchet상 ``from importlib import
    resources`` 한 형태뿐이라 동적 프로브(find_spec/import_module)를 쓰지
    않는다. 닫힌 extras 집합이므로 하우스 패턴(mail_merge의 지연 import)과
    같은 정적 guarded import면 충분하다.
    """

    if extra == "xlsx":
        try:
            import openpyxl  # noqa: F401
        except Exception:
            return False
        return True
    if extra == "preview":
        from .equation.mathml import latex2mathml_available

        return latex2mathml_available()
    # visual: 5.0부터 의도적 빈 extra(설치 호환 유지) — 공허하게 참.
    return True


def _package_version() -> str:
    from . import __version__

    return str(__version__)


# 진입점 실해석(import_module)은 런타임에 없다 — core의 동적 import 능력은
# __init__의 핀된 lazy 로더뿐(boundary ratchet). 레지스트리 진입점이 전부
# 해석되는지는 tests/test_capabilities_surface.py의 드리프트 가드가 실측한다.


def describe_capabilities() -> dict[str, Any]:
    """설치된 core의 기계가독 자기서술 — ``hwpx.capabilities/v1``.

    전부 실측이다: 버전은 배포 메타데이터, extras는 import 프로브, 표면 목록은
    라이브 ``__all__``, op 어휘는 실행기 디스패치와 같은 표. 렌더 오라클은
    core에 없다는 사실 자체를 보고한다(측정 없는 가용성 주장 금지).
    """

    from . import __all__ as stable_names
    from .experimental import __all__ as experimental_names
    from .plan import PLAN_OPS

    return {
        "schemaVersion": CAPABILITIES_SCHEMA,
        "package": {"name": _DIST_NAME, "version": _package_version()},
        "python": platform.python_version(),
        "extras": {name: _extra_installed(name) for name in _EXTRA_MODULES},
        "renderOracle": {
            "bundled": "none",
            "note": (
                "core는 렌더 백엔드를 동봉하지 않습니다(RenderBackend 주입 seam). "
                "실한컴 오라클 탐지·실행과 그 가용성 보고는 python-hwpx-automation"
                "이 소유합니다."
            ),
        },
        "editPlanOps": sorted(PLAN_OPS),
        "schemas": sorted(_SCHEMA_BUILDERS),
        "surfaces": {
            "stable": sorted(stable_names),
            "experimental": sorted(experimental_names),
        },
        "features": [
            {
                "area": row["area"],
                "matrixRow": row["matrix_row"],
                "entryPoints": list(row["entry_points"]),
            }
            for row in _CAPABILITY_AREAS
        ],
        "contractDocuments": sorted(_CONTRACT_DOCS),
    }


def contract_document(name: str) -> str:
    """패키지에 동봉된 계약 문서(markdown 원문)를 돌려준다.

    이름 어휘는 ``describe_capabilities()["contractDocuments"]``와 같다. 미지 이름은
    typed 거부(fail-closed).
    """

    filename = _CONTRACT_DOCS.get(name)
    if filename is None:
        raise HwpxError(
            f"미지 계약 문서 '{name}'입니다.",
            code="unknown-contract-document",
            suggestion=f"가능한 이름: {', '.join(sorted(_CONTRACT_DOCS))}",
        )
    path = _CONTRACT_DOCS_DIR / filename
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HwpxError(
            f"계약 문서가 패키지에 없습니다: {name}",
            code="contract-document-missing",
            context={"path": str(path)},
            suggestion=(
                "개발 체크아웃이라면 scripts/sync_contract_docs.py를 실행해 "
                "docs/ 원본을 data/contract_docs/로 동기화하세요."
            ),
        ) from exc


def _mutation_report_json_schema() -> dict[str, Any]:
    """``hwpx.mutation-report/v1``의 JSON Schema.

    형태의 진실 원천은 :mod:`hwpx.mutation_report`의 ``to_dict()``들이다 —
    테스트가 실제 리포트 사영을 이 스키마로 검증해 두 표현의 드리프트를 막는다.
    최상위 필수 키 9개는 automation의 동결 계약(FROZEN_MUTATION_REPORT_KEYS)과
    같다.
    """

    verification_value = {"enum": ["passed", "failed", "not_performed"]}
    counts = {
        "type": "object",
        "required": ["verified", "changed"],
        "properties": {
            "verified": {"type": "integer", "minimum": 0},
            "changed": {"type": "integer", "minimum": 0},
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://airmang.github.io/python-hwpx/schemas/mutation-report-v1.json",
        "title": "hwpx.mutation-report/v1",
        "type": "object",
        "required": [
            "schemaVersion",
            "ok",
            "path",
            "requestedMode",
            "actualMode",
            "fallbackUsed",
            "changedParts",
            "preservation",
            "verification",
        ],
        "properties": {
            "schemaVersion": {"const": "hwpx.mutation-report/v1"},
            "ok": {"type": "boolean"},
            "path": {"type": ["string", "null"]},
            "requestedMode": {"enum": ["patch", "rebuild", "auto"]},
            "actualMode": {"enum": ["patch", "rebuild"]},
            "fallbackUsed": {"type": "boolean"},
            "changedParts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["path", "reason", "ranges"],
                    "properties": {
                        "path": {"type": "string"},
                        "reason": {"enum": ["dirty-part", "unexpected"]},
                        "ranges": {
                            "type": ["array", "null"],
                            "items": {
                                "type": "object",
                                "required": ["start", "end", "coordinateSpace"],
                                "properties": {
                                    "start": {"type": "integer", "minimum": 0},
                                    "end": {"type": "integer", "minimum": 0},
                                    "coordinateSpace": {
                                        "const": "uncompressed-part-bytes"
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "preservation": {
                "type": "object",
                "required": [
                    "untouchedPartPayloads",
                    "untouchedLocalZipRecords",
                    "wholePackageIdentical",
                ],
                "properties": {
                    "untouchedPartPayloads": counts,
                    "untouchedLocalZipRecords": counts,
                    "wholePackageIdentical": {"type": "boolean"},
                },
            },
            "verification": {
                "type": "object",
                "required": ["package", "openSafety", "reopen", "visual"],
                "properties": {
                    "package": verification_value,
                    "openSafety": verification_value,
                    "reopen": verification_value,
                    "visual": verification_value,
                },
            },
        },
    }


def _capabilities_json_schema() -> dict[str, Any]:
    """``hwpx.capabilities/v1``의 JSON Schema."""

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://airmang.github.io/python-hwpx/schemas/capabilities-v1.json",
        "title": CAPABILITIES_SCHEMA,
        "type": "object",
        "required": [
            "schemaVersion",
            "package",
            "python",
            "extras",
            "renderOracle",
            "editPlanOps",
            "schemas",
            "surfaces",
            "features",
            "contractDocuments",
        ],
        "properties": {
            "schemaVersion": {"const": CAPABILITIES_SCHEMA},
            "package": {
                "type": "object",
                "required": ["name", "version"],
                "properties": {
                    "name": {"const": _DIST_NAME},
                    "version": {"type": "string"},
                },
            },
            "python": {"type": "string"},
            "extras": {
                "type": "object",
                "additionalProperties": {"type": "boolean"},
            },
            "renderOracle": {
                "type": "object",
                "required": ["bundled", "note"],
                "properties": {
                    "bundled": {"const": "none"},
                    "note": {"type": "string"},
                },
            },
            "editPlanOps": {"type": "array", "items": {"type": "string"}},
            "schemas": {"type": "array", "items": {"type": "string"}},
            "surfaces": {
                "type": "object",
                "required": ["stable", "experimental"],
                "properties": {
                    "stable": {"type": "array", "items": {"type": "string"}},
                    "experimental": {"type": "array", "items": {"type": "string"}},
                },
            },
            "features": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["area", "matrixRow", "entryPoints"],
                    "properties": {
                        "area": {"type": "string"},
                        "matrixRow": {"type": "string"},
                        "entryPoints": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
            "contractDocuments": {"type": "array", "items": {"type": "string"}},
        },
    }


def _edit_plan_schema() -> dict[str, Any]:
    from .plan import edit_plan_json_schema

    return edit_plan_json_schema()


def _plan_report_schema() -> dict[str, Any]:
    from .plan import plan_report_json_schema

    return plan_report_json_schema()


_SCHEMA_BUILDERS: dict[str, Any] = {
    "hwpx.edit-plan/v1": _edit_plan_schema,
    "hwpx.plan-report/v1": _plan_report_schema,
    "hwpx.mutation-report/v1": _mutation_report_json_schema,
    "hwpx.capabilities/v1": _capabilities_json_schema,
}


def contract_json_schema(name: str) -> dict[str, Any]:
    """계약 스키마를 이름으로 돌려준다(라이브 빌드 — 파일 박제 없음).

    이름 어휘는 ``describe_capabilities()["schemas"]``와 같다. 미지 이름은 typed 거부.
    """

    builder = _SCHEMA_BUILDERS.get(name)
    if builder is None:
        raise HwpxError(
            f"미지 계약 스키마 '{name}'입니다.",
            code="unknown-contract-schema",
            suggestion=f"가능한 이름: {', '.join(sorted(_SCHEMA_BUILDERS))}",
        )
    return builder()


__all__ = [
    "CAPABILITIES_SCHEMA",
    "describe_capabilities",
    "contract_document",
    "contract_json_schema",
]
