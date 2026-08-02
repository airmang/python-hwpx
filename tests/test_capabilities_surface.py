# SPDX-License-Identifier: Apache-2.0
"""hwpx.capabilities — 자기서술↔실표면 드리프트 가드 (specs/059 §6).

동기 실물: 5.5.0이 각주 방출을 수리하고도 support-matrix 각주 행을 낡은 채로
출하했다(사람 손 갱신의 드리프트). 이 테스트들이 그 부류를 구조적으로 막는다:
레지스트리의 진입점은 import로, 매트릭스 행은 문서 파싱으로, op 어휘는 실행
디스패치와의 3자 대조로 실측 검증된다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import hwpx
from hwpx import experimental
from hwpx.capabilities import (
    _CAPABILITY_AREAS,
    _CONTRACT_DOCS,
    contract_document,
    contract_json_schema,
    describe_capabilities,
)
from hwpx.errors import HwpxError
from hwpx.mutation_report import project_byte_splice
from hwpx.plan import PLAN_OPS
from hwpx.plan._execute import _DISPATCH

REPO = Path(__file__).resolve().parent.parent


def test_capabilities_report_shape() -> None:
    caps = describe_capabilities()
    schema = contract_json_schema("hwpx.capabilities/v1")
    for key in schema["required"]:
        assert key in caps, f"describe_capabilities()에 필수 키 누락: {key}"
    assert caps["schemaVersion"] == "hwpx.capabilities/v1"
    assert caps["package"]["name"] == "python-hwpx"
    assert caps["renderOracle"]["bundled"] == "none"
    assert all(isinstance(v, bool) for v in caps["extras"].values())


def _resolve_entry_point(spec: str) -> object:
    """레지스트리 ``"모듈:이름"`` 해석 — 실해석은 테스트에만 있다(core는
    boundary ratchet상 핀된 lazy 로더 밖 동적 import를 갖지 않는다)."""

    import importlib

    module_name, _, attr = spec.partition(":")
    assert module_name and attr, spec
    return getattr(importlib.import_module(module_name), attr)


def test_every_entry_point_resolves() -> None:
    for row in _CAPABILITY_AREAS:
        for spec in row["entry_points"]:
            assert _resolve_entry_point(spec) is not None, spec


def test_edit_plan_ops_three_way_identity() -> None:
    caps = describe_capabilities()
    assert caps["editPlanOps"] == sorted(PLAN_OPS)
    assert sorted(_DISPATCH) == sorted(PLAN_OPS)
    enum = contract_json_schema("hwpx.edit-plan/v1")["properties"]["steps"]["items"][
        "properties"
    ]["op"]["enum"]
    assert enum == sorted(PLAN_OPS)


def _matrix_row_titles() -> set[str]:
    text = (REPO / "docs" / "support-matrix.md").read_text(encoding="utf-8")
    matrix = text.split("## 매트릭스", 1)[1]
    titles: set[str] = set()
    for line in matrix.splitlines():
        if not line.startswith("|"):
            continue
        first = line.split("|")[1].strip()
        if first in ("능력 영역", "") or set(first) <= {"-"}:
            continue
        titles.add(first)
    return titles


def test_registry_matches_support_matrix_rows() -> None:
    doc_rows = _matrix_row_titles()
    registry_rows = {row["matrix_row"] for row in _CAPABILITY_AREAS}
    assert registry_rows == doc_rows, (
        "capabilities 레지스트리와 docs/support-matrix.md 행이 어긋났습니다 — "
        f"레지스트리에만: {sorted(registry_rows - doc_rows)} / "
        f"문서에만: {sorted(doc_rows - registry_rows)}"
    )


def test_surfaces_census_is_live() -> None:
    caps = describe_capabilities()
    assert caps["surfaces"]["stable"] == sorted(hwpx.__all__)
    assert caps["surfaces"]["experimental"] == sorted(experimental.__all__)


def test_mutation_report_schema_matches_real_projection() -> None:
    report = project_byte_splice(
        data=b"",
        changed_part_names=(),
        byte_identical=True,
        open_safety={"ok": True},
    ).to_dict()
    schema = contract_json_schema("hwpx.mutation-report/v1")
    assert set(schema["required"]) == set(report), (
        "mutation-report 스키마 필수 키가 실제 to_dict() 키와 다릅니다"
    )
    assert report["verification"]["visual"] in ("passed", "failed", "not_performed")


def test_contract_documents_served_and_fail_closed() -> None:
    caps = describe_capabilities()
    assert caps["contractDocuments"] == sorted(_CONTRACT_DOCS)
    for name in caps["contractDocuments"]:
        assert contract_document(name).strip(), name
    with pytest.raises(HwpxError) as excinfo:
        contract_document("no-such-doc")
    assert excinfo.value.code == "unknown-contract-document"
    with pytest.raises(HwpxError) as excinfo2:
        contract_json_schema("no-such-schema")
    assert excinfo2.value.code == "unknown-contract-schema"


def test_capabilities_validates_against_own_schema_structure() -> None:
    """jsonschema 의존 없이 스키마의 형태 선언을 수작업 대조한다."""

    caps = describe_capabilities()
    schema = contract_json_schema("hwpx.capabilities/v1")
    props = schema["properties"]
    assert caps["package"]["name"] == props["package"]["properties"]["name"]["const"]
    assert caps["schemaVersion"] == props["schemaVersion"]["const"]
    for feature in caps["features"]:
        assert set(feature) == {"area", "matrixRow", "entryPoints"}
