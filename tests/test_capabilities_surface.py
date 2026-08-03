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


#: ``add_*``이지만 능력 영역이 아닌 것 — 각각 이유를 적는다.
#:
#: 지금은 비어 있다. 항목을 넣으려면 "왜 이 저작 메서드가 사용자에게 알릴
#: 능력이 아닌지"를 적어야 한다. 사유 없는 면제는 곧 드리프트다.
_NON_CAPABILITY_AUTHORING_METHODS: dict[str, str] = {}


def test_registry_covers_every_authoring_method_on_the_facade() -> None:
    """레지스트리를 **코드에** 대조한다 — 이 방향이라야 잡힌다.

    위 테스트는 레지스트리 행 제목과 문서 행 제목을 대조한다. 문서 둘이 서로
    맞는다는 사실은 코드에 대해 아무것도 말해주지 않으므로 **양쪽에 다 없는**
    능력은 통과한다. `add_check_box`가 정확히 그렇게 5.7.0으로 출하됐다 —
    실한컴 수용 게이트까지 통과했는데 레지스트리에도 매트릭스에도 없었고,
    이 부류를 "구조적으로 막는다"고 선언한 다음 릴리스에서 벌어졌다.

    그래서 이 테스트는 라이브 클래스를 진실 원천으로 삼는다. 새 `add_*`가
    등재 없이 출하되면 여기서 붉어진다.
    """

    from hwpx.document import HwpxDocument

    live = {name for name in dir(HwpxDocument) if name.startswith("add_")}
    registered: dict[str, str] = {}
    duplicates: list[str] = []
    for row in _CAPABILITY_AREAS:
        for method in row.get("authoring_methods", ()):
            if method in registered:
                duplicates.append(f"{method} ({registered[method]} / {row['area']})")
            registered[method] = row["area"]

    assert not duplicates, (
        f"한 저작 메서드가 여러 능력 영역에 등재됐습니다: {sorted(duplicates)}"
    )

    unregistered = sorted(live - set(registered) - set(_NON_CAPABILITY_AUTHORING_METHODS))
    assert not unregistered, (
        "HwpxDocument에 있는데 능력 레지스트리에 없는 저작 메서드입니다 — "
        "출하하면 자기서술이 거짓이 되고, 우리 문서를 읽는 에이전트가 이 "
        f"기능을 회피합니다: {unregistered}. _CAPABILITY_AREAS에 등재하거나 "
        "_NON_CAPABILITY_AUTHORING_METHODS에 사유와 함께 넣으십시오."
    )

    phantom = sorted(set(registered) - live)
    assert not phantom, (
        "레지스트리가 존재하지 않는 저작 메서드를 주장합니다 — 자기서술이 "
        f"실표면을 앞질렀습니다: {phantom}"
    )

    stale_exemptions = sorted(set(_NON_CAPABILITY_AUTHORING_METHODS) - live)
    assert not stale_exemptions, (
        f"면제 목록이 사라진 메서드를 가리킵니다: {stale_exemptions}"
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
