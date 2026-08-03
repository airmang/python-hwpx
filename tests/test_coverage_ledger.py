# SPDX-License-Identifier: Apache-2.0
"""OWPML 커버리지 원장 생성기 계약 테스트.

세 축을 확인한다: (a) 커밋된 원장이 재생성본과 일치(``--check`` 그린),
(b) 원장 JSON 스키마가 유효, (c) frozen-template 판정 표본이 실제
``Skeleton.hwpx`` 바이트와 맞는지. 나머지는 까다로운 내부 로직(루프-변수
태그 조립 복원, 접두 없는 디스패치 탐지, 지원 매트릭스 표 파싱)에 대한
빠른 단위 테스트다 — 전체 레포 스캔 없이 합성 조각으로 회귀를 잡는다.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "coverage_ledger.py"
LEDGER_JSON = ROOT / "docs" / "coverage-ledger.json"
LEDGER_MD = ROOT / "docs" / "coverage-ledger.md"
SKELETON = ROOT / "src" / "hwpx" / "data" / "Skeleton.hwpx"

_ELEMENT_KEYS = {
    "namespace",
    "element",
    "schemaSource",
    "corpusFrequency",
    "corpusFileCount",
    "codeRead",
    "codeWrite",
    "capabilityArea",
    "capabilityStatus",
    "verificationBasis",
}
_KNOWN_PREFIXES = {"hp", "hh", "hc", "hs", "hm", "hhs", "hv"}


def _module():
    spec = importlib.util.spec_from_file_location("coverage_ledger", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_ledger() -> dict:
    return json.loads(LEDGER_JSON.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# (a) --check는 그린이다
# ---------------------------------------------------------------------------


def test_check_is_green() -> None:
    """커밋된 원장(JSON+MD)이 재생성본과 바이트 동일하다 — CI 게이트 본체."""

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "in sync" in proc.stdout


def test_check_fails_closed_on_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--check가 실제로 드리프트를 감지하는지 — 위 그린 테스트의 대조군.

    커밋된 ``docs/coverage-ledger.json``/``.md``는 절대 건드리지 않는다 —
    이 레포는 다른 에이전트와 공유하는 워크트리라, 실 파일을 잠깐이라도
    손상시키면 동시 실행 중인 다른 프로세스(예: 이 파일과 전체 스위트를
    동시에 도는 pytest 두 개)와 경합해 원복이 씹힐 수 있다(실제로 한 번
    겪었다). 대신 ``LEDGER_JSON``/``LEDGER_MD`` 모듈 상수만 tmp_path로
    monkeypatch하고 ``main()``을 프로세스 안에서 직접 불러 비교 대상만
    격리한다 — 나머지 입력(스키마·census·매트릭스·Skeleton)은 그대로 실제
    레포를 읽으므로 진짜 코드 경로를 검증한다.
    """

    module = _module()
    ledger = module.build_ledger(module.DEFAULT_CENSUS_PATH)

    fake_json = tmp_path / "coverage-ledger.json"
    fake_md = tmp_path / "coverage-ledger.md"
    mutated = dict(ledger)
    mutated["corpusTotalFiles"] = ledger["corpusTotalFiles"] + 1
    fake_json.write_text(json.dumps(mutated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fake_md.write_text(module.render_markdown(ledger), encoding="utf-8")

    monkeypatch.setattr(module, "LEDGER_JSON", fake_json)
    monkeypatch.setattr(module, "LEDGER_MD", fake_md)
    monkeypatch.setattr(sys, "argv", ["coverage_ledger.py", "--check"])

    assert module.main() == 1


# ---------------------------------------------------------------------------
# (b) 원장 스키마가 유효하다
# ---------------------------------------------------------------------------


def test_ledger_schema_is_valid() -> None:
    ledger = _load_ledger()

    assert ledger["schemaVersion"] == "python-hwpx.coverage-ledger/v1"
    assert set(ledger) == {
        "schemaVersion",
        "generatedFrom",
        "corpusTotalFiles",
        "summary",
        "elements",
    }
    assert ledger["corpusTotalFiles"] > 0

    summary = ledger["summary"]
    assert set(summary) == {
        "totalElements",
        "schemaDeclared",
        "corpusOnly",
        "corpusObserved",
        "codeRead",
        "codeWriteApi",
        "codeWriteFrozenTemplate",
        "codeWriteNone",
        "capabilityMapped",
        "renderVerified",
    }
    assert summary["totalElements"] == len(ledger["elements"]) > 0
    assert summary["schemaDeclared"] + summary["corpusOnly"] == summary["totalElements"]
    assert (
        summary["codeWriteApi"] + summary["codeWriteFrozenTemplate"] + summary["codeWriteNone"]
        == summary["totalElements"]
    )
    assert summary["capabilityMapped"] >= summary["renderVerified"]

    seen: set[tuple[str, str]] = set()
    for entry in ledger["elements"]:
        assert set(entry) == _ELEMENT_KEYS
        key = (entry["namespace"], entry["element"])
        assert key not in seen, f"duplicate element row: {key}"
        seen.add(key)

        assert entry["namespace"] in _KNOWN_PREFIXES
        assert isinstance(entry["element"], str) and entry["element"]
        assert entry["schemaSource"] is None or entry["schemaSource"].endswith(".xml")
        assert isinstance(entry["corpusFileCount"], int) and entry["corpusFileCount"] >= 0
        assert 0.0 <= entry["corpusFrequency"] <= 1.0
        expected_freq = round(entry["corpusFileCount"] / ledger["corpusTotalFiles"], 4)
        assert entry["corpusFrequency"] == expected_freq
        assert isinstance(entry["codeRead"], bool)
        assert entry["codeWrite"] in {"api", "frozen-template", "none"}

        if entry["capabilityArea"] is None:
            assert entry["capabilityStatus"] is None
            assert entry["verificationBasis"] is None
        if entry["verificationBasis"] is not None:
            assert entry["verificationBasis"] == "by-capability-area"
            assert entry["capabilityArea"] is not None
            assert "Render-verified" in entry["capabilityStatus"]

    # 재현성: (namespace, element) 오름차순 결정론적 정렬.
    pairs = [(e["namespace"], e["element"]) for e in ledger["elements"]]
    assert pairs == sorted(pairs)


def test_markdown_summary_matches_json_totals() -> None:
    ledger = _load_ledger()
    md = LEDGER_MD.read_text(encoding="utf-8")
    assert f"| 요소 총수 | {ledger['summary']['totalElements']} | — |" in md
    assert str(ledger["corpusTotalFiles"]) in md


# ---------------------------------------------------------------------------
# (c) frozen-template 표본 3건이 실제 Skeleton.hwpx 바이트와 맞다
# ---------------------------------------------------------------------------


def test_frozen_template_samples_match_skeleton_bytes() -> None:
    """frozen-template 판정 3건을 골라, 원장 코드와 별도로 zip을 다시 열어
    독립 검증한다(같은 판정 함수를 재호출하는 자기증명을 피한다)."""

    ledger = _load_ledger()
    frozen = [e for e in ledger["elements"] if e["codeWrite"] == "frozen-template"]
    assert len(frozen) >= 3, "표본을 뽑을 frozen-template 요소가 부족합니다"

    with zipfile.ZipFile(SKELETON) as archive:
        skeleton_text = "\n\n".join(
            archive.read(info.filename).decode("utf-8", errors="ignore")
            for info in archive.infolist()
            if info.filename.endswith((".xml", ".hpf", ".rdf"))
        )

    samples = sorted(frozen, key=lambda e: (e["namespace"], e["element"]))[:3]
    assert len(samples) == 3
    for entry in samples:
        prefix, name = entry["namespace"], entry["element"]
        open_tag = f"<{prefix}:{name}"
        idx = skeleton_text.find(open_tag)
        assert idx != -1, (
            f"{prefix}:{name}이 frozen-template로 표시됐지만 Skeleton.hwpx에 여는 태그가 없습니다"
        )
        boundary_char = skeleton_text[idx + len(open_tag)]
        assert boundary_char in (" ", "/", ">"), (
            f"{open_tag} 뒤 경계 문자가 이상합니다({boundary_char!r}) — "
            "더 긴 태그 이름의 부분열을 잘못 잡았을 수 있습니다"
        )


def test_frozen_template_elements_have_no_write_api_evidence() -> None:
    """frozen-template로 분류된 요소는 정의상 codeWrite가 api가 아니어야
    한다(분류 로직이 스스로 모순되지 않는지)."""

    ledger = _load_ledger()
    for entry in ledger["elements"]:
        if entry["codeWrite"] == "frozen-template":
            assert entry["namespace"] and entry["element"]  # 자리 표시만 아님을 확인
    frozen_keys = {
        (e["namespace"], e["element"]) for e in ledger["elements"] if e["codeWrite"] == "frozen-template"
    }
    api_keys = {(e["namespace"], e["element"]) for e in ledger["elements"] if e["codeWrite"] == "api"}
    assert frozen_keys.isdisjoint(api_keys)


# ---------------------------------------------------------------------------
# 내부 로직 단위 테스트 (합성 조각, 전체 레포 스캔 없음)
# ---------------------------------------------------------------------------


def test_schema_parser_finds_known_elements_across_all_seven_families() -> None:
    """실제 DevDoc XSD 7종을 파싱해 각 패밀리에서 알려진 요소가 나오는지."""

    module = _module()
    by_prefix = module.parse_schema_elements()

    assert set(by_prefix) == _KNOWN_PREFIXES
    assert by_prefix["hp"]["tbl"] == "ParaList XML schema.xml"
    assert by_prefix["hc"]["color"] == "Core XML schema.xml"
    assert by_prefix["hh"]["styles"] == "Header XML schema.xml"
    assert by_prefix["hs"]["sec"] == "Body XML schema.xml"
    assert by_prefix["hm"]["masterPage"] == "MasterPage XML schema.xml"
    assert by_prefix["hhs"]["history"] == "Document History XML schema.xml"
    assert by_prefix["hv"] == {"version": "Version XML schema.xml"}


def test_dispatch_window_catches_bare_local_name_comparison() -> None:
    """`name = local_name(child); if name == "docOption":` 관용구 인식."""

    module = _module()
    source = (
        "def parse_header_element(node):\n"
        "    for child in node:\n"
        "        name = local_name(child)\n"
        "        if name == 'beginNum':\n"
        "            pass\n"
        "        elif name == 'docOption':\n"
        "            pass\n"
    )
    windows = module._build_dispatch_windows(source)
    assert module._bare_name_dispatched("docOption", windows)
    assert module._bare_name_dispatched("beginNum", windows)
    assert not module._bare_name_dispatched("neverMentioned", windows)


def test_dispatch_window_rejects_unrelated_same_scope_string() -> None:
    """`version = root.get("version")`처럼 getter와 무관한 동명 변수는
    디스패치로 오인하면 안 된다(실제로 겪은 오탐 회귀 테스트: 이 정확한
    모양이 ``hv:version``을 잘못 True로 만들었다가 비교 연산자를 앵커로
    좁히는 지금 방식으로 고쳐졌다). 실제 파일에서처럼 비교 지점과 무관한
    줄 사이에 200자보다 넉넉한 거리를 둔다 — 너무 촘촘하면 우연히 비교
    윈도(200자) 안에 들어와 이 테스트 자체가 오탐의 재현이 아니라 새로운
    우연의 일치가 돼버린다."""

    module = _module()
    padding = "\n".join(f"    # filler line {i} to push past the comparison window" for i in range(12))
    source = (
        "def parse_version(root):\n"
        "    name = local_name(root)\n"
        "    if name == 'HCFVersion':\n"
        "        pass\n"
        f"{padding}\n"
        "    version = root.get('version')\n"
        "    return version\n"
    )
    assert len(padding) > module._COMPARISON_WINDOW, "padding must exceed the comparison window"
    windows = module._build_dispatch_windows(source)
    assert module._bare_name_dispatched("HCFVersion", windows)
    assert not module._bare_name_dispatched("version", windows)


def test_direct_getter_comparison_without_intermediate_variable() -> None:
    """`local_name(child) == "run"`처럼 변수를 거치지 않는 직접 비교."""

    module = _module()
    source = "runs = [c for c in node if local_name(c) == 'run']\n"
    windows = module._build_dispatch_windows(source)
    assert module._bare_name_dispatched("run", windows)


def test_resolve_loop_tag_tables_handles_tuple_of_tuples() -> None:
    """``for name, attrs in _TABLE: ET.SubElement(el, f"{_HH}{name}", attrs)``
    처럼 튜플의 튜플을 도는 루프에서 실제 요소 이름을 복원한다."""

    module = _module()
    source = (
        "_HH = '{http://example/head}'\n"
        "_BASIC_BORDER_CHILDREN = (\n"
        "    ('leftBorder', {'type': 'SOLID'}),\n"
        "    ('rightBorder', {'type': 'SOLID'}),\n"
        ")\n"
        "\n"
        "def _create(el):\n"
        "    for child_name, child_attrs in _BASIC_BORDER_CHILDREN:\n"
        "        ET.SubElement(el, f'{_HH}{child_name}', dict(child_attrs))\n"
    )
    resolved = module._resolve_loop_tag_tables([(Path("synthetic.py"), source)])
    assert resolved[("hh", "leftBorder")] == (True, True)
    assert resolved[("hh", "rightBorder")] == (True, True)


def test_resolve_loop_tag_tables_handles_dict_items_read_only() -> None:
    """``for side, child_name in _SIDES.items(): element.find(f"{_HH}{child_name}")``
    처럼 dict.items()를 도는 읽기 전용 루프에서 값 쪽을 복원한다."""

    module = _module()
    source = (
        "_HH = '{http://example/head}'\n"
        "_SIDES = {'left': 'leftBorder', 'right': 'rightBorder'}\n"
        "\n"
        "def _check(element):\n"
        "    for side, child_name in _SIDES.items():\n"
        "        child = element.find(f'{_HH}{child_name}')\n"
        "        if child is None:\n"
        "            return False\n"
        "    return True\n"
    )
    resolved = module._resolve_loop_tag_tables([(Path("synthetic.py"), source)])
    assert resolved[("hh", "leftBorder")] == (True, False)
    assert resolved[("hh", "rightBorder")] == (True, False)
    # 키(side) 쪽은 태그로 쓰이지 않았으니 복원 대상이 아니다.
    assert ("hh", "left") not in resolved
    assert ("hh", "right") not in resolved


def test_resolve_loop_tag_tables_skips_function_parameter_iterables() -> None:
    """루프 대상이 함수 인자 등 정적으로 못 푸는 값이면 조용히 건너뛴다
    (오탐보다 누락을 택한다는 설계 그대로)."""

    module = _module()
    source = (
        "_HP = '{http://example/paragraph}'\n"
        "\n"
        "def _create(el, candidates):\n"
        "    for tag in candidates:\n"
        "        ET.SubElement(el, f'{_HP}{tag}')\n"
    )
    resolved = module._resolve_loop_tag_tables([(Path("synthetic.py"), source)])
    assert resolved == {}


def test_support_matrix_status_parser_isolates_matrix_section() -> None:
    module = _module()
    text = (
        "# 지원 매트릭스\n\n"
        "| 등급 | 의미 |\n|---|---|\n| **Parse** | 읽는다 |\n\n"
        "## 매트릭스\n\n"
        "| 능력 영역 | 상태 | 증거 |\n"
        "|---|---|---|\n"
        "| 차트 | Create(experimental)·Preserve | 근거 |\n"
        "| 수식 | Parse·Create(experimental)·Render-verified | 근거 |\n\n"
        "## 상태 판정 근거 요약\n\n어떤 다른 표 | 도 | 있다\n"
    )
    status = module._parse_support_matrix_status(text)
    assert status == {
        "차트": "Create(experimental)·Preserve",
        "수식": "Parse·Create(experimental)·Render-verified",
    }
    assert "어떤 다른 표" not in status


def test_classify_capability_requires_render_verified_for_basis() -> None:
    module = _module()
    status_by_area = {
        "차트": "Create(experimental)·Preserve",
        "수식": "Parse·Create(experimental)·Render-verified",
    }
    area, status, basis = module.classify_capability("hp", "chart", status_by_area)
    assert area == "차트"
    assert basis is None, "Render-verified가 없는 행은 승격하면 안 된다"

    area, status, basis = module.classify_capability("hp", "equation", status_by_area)
    assert area == "수식"
    assert basis == "by-capability-area"

    area, status, basis = module.classify_capability("hp", "totallyUnmapped", status_by_area)
    assert (area, status, basis) == (None, None, None)


def test_capability_keywords_all_resolve_against_real_support_matrix() -> None:
    """CAPABILITY_KEYWORDS의 모든 행 라벨이 실제 support-matrix.md 표에
    존재하는지 — 매트릭스 산문이 바뀌면 이 테스트가 드리프트를 잡는다."""

    module = _module()
    status_by_area = module._parse_support_matrix_status(
        module.SUPPORT_MATRIX_PATH.read_text(encoding="utf-8")
    )
    referenced_areas = set(module.CAPABILITY_KEYWORDS.values())
    missing = referenced_areas - set(status_by_area)
    assert not missing, f"CAPABILITY_KEYWORDS가 매트릭스에 없는 행을 가리킵니다: {missing}"
