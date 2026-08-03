# SPDX-License-Identifier: Apache-2.0
"""``hwpx.capabilities`` — 기계가독 자기서술 (experimental, 5.6.0 신규).

동기(실측 드리프트 사례): 사람 손으로 갱신하는 자기서술 문서는 릴리스 트레인
하루 만에도 실표면과 드리프트한다. 이 모듈이 단일 진실 원천이고, 드리프트
가드 테스트가 다음 세 방향을 강제한다:

1. 여기 등재된 진입점은 전부 실제로 import 가능해야 한다.
2. ``editPlanOps``는 :data:`hwpx.plan.PLAN_OPS`·실행 디스패치·edit-plan JSON
   Schema enum과 일치해야 한다.
3. :data:`_CAPABILITY_AREAS`의 ``authoring_methods``는 라이브
   ``HwpxDocument``의 ``add_*`` 전수와 정확히 일치해야 한다 — **레지스트리를
   코드에 대조하는 방향**이다.
4. 매트릭스 행 제목은 ``docs/support-matrix.md`` 표의 행 제목과 집합 일치해야
   한다.

3번이 있는 이유: 4번만으로는 부족하다. 문서 둘이 서로 맞는다는 사실은 코드에
대해 아무것도 말해주지 않으므로, **양쪽에 다 없는** 능력은 통과한다. 실제로
``add_check_box``가 5.7.0에서 실한컴 수용 게이트까지 통과해 출하됐는데
레지스트리에도 매트릭스에도 없었다 — 이 부류의 드리프트를 "구조적으로
막는다"고 선언한 바로 다음 릴리스에서다. 코드에 대조해야 잡힌다.

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
#: Every ``HwpxDocument.add_*`` method must be claimed by exactly one area.
#:
#: ``namespace`` 는 6.0 표면에서 그 영역이 사는 자리다. 표면 분할의 **근거가**
#: 이 레지스트리였으므로(설계서 §1.2 — 경계를 발명하지 않고 여기서 유도했다),
#: 근거와 결과가 어긋나지 않도록 매핑을 여기 박제한다. ``None`` 은 루트에
#: 남았거나(``add_paragraph``·``add_table``·``add_picture``) 파사드 밖 모듈이
#: 소유하는 영역이다.
#:
#: ``entry_points`` names modules, which is too coarse to notice a new
#: authoring method: ten areas all point at ``hwpx.document:HwpxDocument``. So
#: ``authoring_methods`` names the methods, and the guard in
#: ``tests/test_capabilities_surface.py`` compares this registry against the
#: live class.
#:
#: Why the guard runs in that direction: the previous guard compared the
#: registry's row titles against the row titles in ``docs/support-matrix.md``.
#: Two documents agreeing with each other says nothing about the code, so a
#: capability missing from *both* passed. ``add_check_box`` shipped in 5.7.0
#: with a real-Hancom acceptance gate and appeared in neither, one release
#: after the changelog announced that this class of drift was now structurally
#: blocked. Comparing against the class is the direction that can catch it.
_CAPABILITY_AREAS: tuple[dict[str, Any], ...] = (
    {
        "area": "paragraph-table-authoring",
        "namespace": None,
        "matrix_row": "문단·표 저작/편집",
        "entry_points": ("hwpx.document:HwpxDocument",),
        "authoring_methods": ("add_heading", "add_paragraph", "add_section"),
    },
    {
        "area": "table-structure",
        "namespace": "doc.tables",
        "matrix_row": "표 구조 변경(행·열·표 삭제/삽입, 열 오토핏)",
        "entry_points": ("hwpx.table_patch:apply_table_ops",),
        "authoring_methods": (),
    },
    {
        "area": "table-create",
        "namespace": None,
        "matrix_row": "표 생성(병합·중첩 포함)",
        "entry_points": ("hwpx.document:HwpxDocument",),
        "authoring_methods": ("add_table",),
    },
    {
        "area": "form-fill",
        "namespace": "doc.tables",
        "matrix_row": "양식 채움(byte-splice)",
        "entry_points": (
            "hwpx.patch:paragraph_patch",
            "hwpx.table_patch:fill_cells",
            "hwpx.body_patch:apply_body_ops",
        ),
        "authoring_methods": (),
    },
    {
        "area": "edit-plan",
        "namespace": None,
        "matrix_row": "편집 계획 실행(edit plan)",
        "entry_points": (
            "hwpx.plan:apply_edit_plan",
            "hwpx.plan:validate_edit_plan",
        ),
        "authoring_methods": (),
    },
    {
        "area": "shape-authoring",
        "namespace": "doc.shapes",
        "matrix_row": "도형 저작(선·사각형·타원)",
        "entry_points": ("hwpx.document:HwpxDocument",),
        "authoring_methods": ("add_line", "add_rectangle", "add_ellipse"),
    },
    {
        "area": "shape-escape-hatch",
        "namespace": "doc.shapes",
        "matrix_row": "저수준 도형·컨트롤 탈출구",
        "entry_points": ("hwpx.document:HwpxDocument",),
        "authoring_methods": ("add_shape", "add_control"),
    },
    {
        "area": "curve-objects",
        "namespace": "doc.shapes",
        "matrix_row": "arc·polygon·curve·connectLine",
        "entry_points": (),
        "authoring_methods": (),
    },
    {
        "area": "picture",
        "namespace": None,
        "matrix_row": "그림 삽입/치환",
        "entry_points": ("hwpx.document:HwpxDocument",),
        "authoring_methods": ("add_picture", "add_image"),
    },
    {
        "area": "chart",
        "namespace": "doc.shapes",
        "matrix_row": "차트",
        "entry_points": ("hwpx.document:HwpxDocument",),
        "authoring_methods": ("add_chart",),
    },
    {
        "area": "equation",
        "namespace": "doc.shapes",
        "matrix_row": "수식",
        "entry_points": ("hwpx.equation.authoring:latex_to_eqedit",),
        "authoring_methods": ("add_equation",),
    },
    {
        "area": "redline",
        "namespace": "doc.tracking",
        "matrix_row": "변경추적(redline)",
        "entry_points": ("hwpx.tools.redline:verify_redline",),
        "authoring_methods": ("add_track_change", "add_tracked_insert", "add_tracked_delete", "add_tracked_replace"),
    },
    {
        "area": "memo",
        "namespace": "doc.notes",
        "matrix_row": "메모(코멘트)",
        "entry_points": ("hwpx.document:HwpxDocument",),
        "authoring_methods": ("add_memo", "add_memo_with_anchor"),
    },
    {
        "area": "footnote-endnote",
        "namespace": "doc.notes",
        "matrix_row": "각주/미주",
        "entry_points": ("hwpx.document:HwpxDocument",),
        "authoring_methods": ("add_footnote", "add_endnote"),
    },
    {
        "area": "toc-crossref",
        "namespace": "doc.refs",
        "matrix_row": "네이티브 목차(TOC)/상호참조",
        "entry_points": ("hwpx.tools.toc_author:add_native_toc",),
        "authoring_methods": ("add_bookmark", "add_hyperlink"),
    },
    {
        "area": "encrypted-hwpx",
        "namespace": None,
        "matrix_row": "암호화 HWPX",
        "entry_points": (),
        "authoring_methods": (),
    },
    {
        "area": "hwp5-binary",
        "namespace": None,
        "matrix_row": "HWP 5.x 바이너리",
        "entry_points": (),
        "authoring_methods": (),
    },
    {
        "area": "form-field-create",
        "namespace": "doc.fields",
        "matrix_row": "누름틀(form field) 생성",
        "entry_points": ("hwpx.document:HwpxDocument",),
        "authoring_methods": ("add_form_field",),
    },
    {
        "area": "check-box",
        "namespace": "doc.fields",
        "matrix_row": "체크박스 양식개체",
        "entry_points": ("hwpx.document:HwpxDocument",),
        "authoring_methods": ("add_check_box",),
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

#: 파사드 계약의 일부로 인정하는 dunder(락 생성기와 같은 규칙).
_PUBLIC_DUNDERS = frozenset({"__init__", "__repr__", "__enter__", "__exit__"})

#: 위임 shim 이 사라지는 major. ``_document._legacy`` 와 같은 값이어야 한다.
_LEGACY_REMOVED_IN = "7.0"


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
                "namespace": row.get("namespace"),
                "entryPoints": list(row["entry_points"]),
            }
            for row in _CAPABILITY_AREAS
        ],
        "contractDocuments": sorted(_CONTRACT_DOCS),
        "surfaceShape": {
            "root": _root_surface_size(),
            "legacyShimCount": _legacy_shim_count(),
            "legacyShimsRemovedIn": _LEGACY_REMOVED_IN,
            "note": (
                "root 는 6.0 파사드의 공개 멤버 수다. legacyShimCount 는 5.x 이름을 "
                "유지하는 위임 shim 수이며 7.0에서 0이 된다 — 이동을 제거로 보이지 "
                "않게 하려고 따로 센다."
            ),
        },
    }


def _root_surface_size() -> int:
    """6.0 파사드의 공개 멤버 수 — 클래스 자기 ``__dict__`` 만 센다."""

    from .document import HwpxDocument

    return sum(
        1
        for name in vars(HwpxDocument)
        if not name.startswith("_") or name in _PUBLIC_DUNDERS
    )


def _legacy_shim_count() -> int:
    """5.x 이름을 유지하는 위임 shim 수. 7.0에서 0이 된다."""

    from ._document._legacy import _LegacyFacade

    return sum(1 for name in vars(_LegacyFacade) if not name.startswith("__"))


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
                    "required": ["area", "matrixRow", "namespace", "entryPoints"],
                    "properties": {
                        "area": {"type": "string"},
                        "matrixRow": {"type": "string"},
                        "namespace": {"type": ["string", "null"]},
                        "entryPoints": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
            "contractDocuments": {"type": "array", "items": {"type": "string"}},
            "surfaceShape": {
                "type": "object",
                "required": [
                    "root",
                    "legacyShimCount",
                    "legacyShimsRemovedIn",
                    "note",
                ],
                "properties": {
                    "root": {"type": "integer"},
                    "legacyShimCount": {"type": "integer"},
                    "legacyShimsRemovedIn": {"type": "string"},
                    "note": {"type": "string"},
                },
            },
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


def verify_self_description() -> list[str]:
    """설치된 휠에서 자기서술이 실표면과 맞는지 직접 검사한다.

    왜 라이브러리 안에 있나: 5.6.0의 CHANGELOG는 이 부류의 드리프트를 "이제
    구조적으로 막습니다"라고 **선언**했고, 바로 다음 릴리스에서 같은 드리프트를
    냈다. 두 번째 선언은 신뢰받을 이유가 없다. 그래서 선언 대신 **누구나 자기
    설치본에서 돌려 볼 수 있는 검사**를 동봉한다 —
    ``python -m hwpx.capabilities --verify``.

    저장소의 테스트가 아니라 설치된 패키지에서 도는 것이 요점이다. 사용자가
    받은 휠이 실제로 무엇을 할 수 있는지 그 휠 자신에게 물어볼 수 있다.

    Returns:
        위반 목록. 빈 리스트면 자기서술이 실표면과 일치한다.
    """

    from .document import HwpxDocument

    problems: list[str] = []

    live = {name for name in dir(HwpxDocument) if name.startswith("add_")}
    registered: dict[str, str] = {}
    for row in _CAPABILITY_AREAS:
        for method in row.get("authoring_methods", ()):
            if method in registered:
                problems.append(
                    f"authoring method {method!r} is claimed by both "
                    f"{registered[method]!r} and {row['area']!r}"
                )
            registered[method] = row["area"]

    for method in sorted(live - set(registered)):
        problems.append(
            f"HwpxDocument.{method} exists but no capability area claims it; "
            "the self-description understates what this install can do"
        )
    for method in sorted(set(registered) - live):
        problems.append(
            f"capability registry claims HwpxDocument.{method}, which this "
            "install does not have; the self-description overstates it"
        )

    matrix_rows = {row["matrix_row"] for row in _CAPABILITY_AREAS}
    try:
        text = contract_document("support-matrix")
    except HwpxError as exc:  # pragma: no cover - only when the doc is absent
        problems.append(f"bundled support matrix is unreadable: {exc}")
    else:
        documented = {
            line.split("|")[1].strip()
            for line in text.splitlines()
            if line.startswith("|")
        }
        for row in sorted(matrix_rows - documented):
            problems.append(f"capability area {row!r} has no support-matrix row")

    problems.extend(_verify_surface_shape())
    return problems


def _verify_surface_shape() -> list[str]:
    """6.0 표면 서술이 실제 클래스와 맞는지 검사한다.

    레지스트리가 표면 분할의 근거였으므로, 그것이 가리키는 네임스페이스가
    실재하지 않으면 자기서술이 거짓을 말하는 것이다.
    """

    from .document import HwpxDocument

    problems: list[str] = []
    root_members = {
        name
        for name in vars(HwpxDocument)
        if not name.startswith("_") or name in _PUBLIC_DUNDERS
    }

    for row in _CAPABILITY_AREAS:
        namespace = row.get("namespace")
        if namespace is None:
            continue
        if not namespace.startswith("doc."):
            problems.append(
                f"capability area {row['area']!r} names namespace {namespace!r}, "
                "which is not a doc.* path"
            )
            continue
        attribute = namespace.split(".", 1)[1]
        if attribute not in root_members:
            problems.append(
                f"capability area {row['area']!r} claims namespace {namespace!r}, "
                "which this install does not expose"
            )

    from ._document._legacy import LEGACY_REMOVED_IN

    if LEGACY_REMOVED_IN != _LEGACY_REMOVED_IN:
        problems.append(
            f"legacy shim removal version disagrees: capabilities says "
            f"{_LEGACY_REMOVED_IN!r}, the shim module says {LEGACY_REMOVED_IN!r}"
        )

    return problems


def _verify_main(argv: list[str] | None = None) -> int:
    import argparse
    import json as _json
    import sys

    parser = argparse.ArgumentParser(
        prog="python -m hwpx.capabilities",
        description="Report or verify this install's machine-readable self-description.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="check the self-description against the installed surface",
    )
    args = parser.parse_args(argv)

    if not args.verify:
        print(_json.dumps(describe_capabilities(), ensure_ascii=False, indent=2))
        return 0

    problems = verify_self_description()
    for problem in problems:
        print(f"self-description error: {problem}", file=sys.stderr)
    if problems:
        print(
            f"{len(problems)} self-description problem(s) found in "
            f"python-hwpx {_package_version()}",
            file=sys.stderr,
        )
        return 1
    print(
        f"python-hwpx {_package_version()}: self-description matches the "
        f"installed surface ({len(_CAPABILITY_AREAS)} capability areas)"
    )
    return 0


__all__ = [
    "CAPABILITIES_SCHEMA",
    "describe_capabilities",
    "contract_document",
    "contract_json_schema",
    "verify_self_description",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_verify_main())
