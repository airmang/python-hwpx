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
import re
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
    "observedAttributes",
}
#: "ha"(app/settings.xml)는 2026-08-04 감사 §3-C1이 지목한 모집단 맹점
#: 수리로 census에 편입됐다 — `hwpx.oxml.namespaces.HWPML_COMPAT_ROOT_NAMESPACES`
#: 에는 원래부터 등록돼 있었으나(family "app"), OWPML XSD 7종에는 대응
#: 스키마 파일이 없어 이전에는 원장에 한 번도 나타나지 않았다.
_KNOWN_PREFIXES = {"hp", "hh", "hc", "hs", "hm", "hhs", "hv", "ha"}
_VALID_VERIFICATION_BASES = {
    "by-capability-area",
    "by-openrate-corpus",
    "by-capability-area+openrate-corpus",
}


def _module():
    spec = importlib.util.spec_from_file_location("coverage_ledger", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec: the module defines ``@dataclass`` classes, and
    # dataclass's ``from __future__ import annotations`` string-annotation
    # resolution looks the module up via ``sys.modules`` -- without this it
    # raises AttributeError on Python 3.12+.
    sys.modules[spec.name] = module
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
        "corpusUnknownFiles",
        "corpusForeignNamespaces",
        "corpusUnnamespacedElements",
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
        "renderVerifiedByOpenrateCorpus",
        "attributesObserved",
    }
    assert summary["totalElements"] == len(ledger["elements"]) > 0
    assert summary["schemaDeclared"] + summary["corpusOnly"] == summary["totalElements"]
    assert (
        summary["codeWriteApi"] + summary["codeWriteFrozenTemplate"] + summary["codeWriteNone"]
        == summary["totalElements"]
    )
    # capabilityMapped와 renderVerified는 더 이상 부분집합 관계가 아니다 —
    # openrate 코퍼스가 capabilityArea 없는 요소를 직접 검증할 수 있다(D항
    # _OPENRATE_STRATUM_TO_ELEMENTS 경로). renderVerified 자체는 여전히
    # renderVerifiedByOpenrateCorpus의 상위집합이어야 한다.
    assert summary["renderVerified"] >= summary["renderVerifiedByOpenrateCorpus"] >= 0

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
        assert isinstance(entry["observedAttributes"], list)
        assert all(isinstance(a, str) for a in entry["observedAttributes"])
        assert entry["observedAttributes"] == sorted(entry["observedAttributes"])

        if entry["capabilityArea"] is None:
            assert entry["capabilityStatus"] is None
            # verificationBasis는 여기서도 non-None일 수 있다— 요소 직접
            # 경로(_OPENRATE_STRATUM_TO_ELEMENTS)가 capabilityArea 없는
            # 요소도 검증한다(D항). 순수 "by-openrate-corpus"(capabilityArea
            # 경로 성분이 전혀 없는 경우)만 아래에서 마저 검사한다.
            if entry["verificationBasis"] is not None:
                assert entry["verificationBasis"] == "by-openrate-corpus"
        if entry["verificationBasis"] is not None:
            assert entry["verificationBasis"] in _VALID_VERIFICATION_BASES
            if "capability-area" in entry["verificationBasis"]:
                assert entry["capabilityArea"] is not None
                assert "Render-verified" in entry["capabilityStatus"]
            if "openrate-corpus" in entry["verificationBasis"]:
                # openrate 코퍼스 증거는 순수("by-openrate-corpus")든 복합
                # ("by-capability-area+openrate-corpus")든 "실한컴이 저작을
                # 수용했다"는 주장이다 — 못 만드는(write=none) 요소가 이
                # 표시를 갖는 건 모순이다. 순수 경로 회귀(구현 중 실제로
                # 겪음): arc·polygon·curve·connectLine을 capabilityArea째
                # 매핑했다가 정직 보류 중인 curve/connectLine에 신호가 샜다.
                # 복합 경로 회귀(트레인⑰ 사후 재검증이 잡음): v4의
                # authored-checkbox가 "체크박스 양식개체" 영역 전체에 흘려,
                # 저작 API 없는 hp:btn/radioBtn까지 신호가 샜다 — 두 요소는
                # _OPENRATE_MIXED_SUPPORT_AREA_EXCLUSIONS로 강등했다.
                assert entry["codeWrite"] == "api", (
                    f"{entry['namespace']}:{entry['element']} has verificationBasis="
                    f"{entry['verificationBasis']!r} but codeWrite="
                    f"{entry['codeWrite']!r} — corpus-authored verification claims "
                    "require write=api regardless of whether the basis is pure or "
                    "combined with a capability-area claim"
                )

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
    """실제 DevDoc XSD 7종을 파싱해 각 패밀리에서 알려진 요소가 나오는지.

    ``DevDoc/OWPML SCHEMA/``에는 7개 파일(hp/hh/hc/hs/hm/hhs/hv 패밀리)만
    있다 — "ha"(app/settings.xml)는 대응 XSD가 없는 실결함이라 여기 절대
    안 나온다(census가 실코퍼스 관측으로만 채우는 이유이기도 하다). 이
    스크립트가 실제로 만들어 낼 수 있는 원장 네임스페이스 전체 집합은
    ``_KNOWN_PREFIXES``(스키마 7 + census-only "ha")다."""

    module = _module()
    by_prefix = module.parse_schema_elements()

    schema_only_prefixes = {"hp", "hh", "hc", "hs", "hm", "hhs", "hv"}
    assert set(by_prefix) == schema_only_prefixes
    assert schema_only_prefixes < _KNOWN_PREFIXES
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


def test_strip_namespace_is_a_registered_local_name_getter() -> None:
    """사이클 6.5 트레인⑲ 수리: `tools/text_extractor.py`의 `strip_namespace`는
    oxml 쪽 `local_name`과 이름만 다를 뿐 같은 관용구
    (`tag = strip_namespace(child.tag); if tag == "xxx":`)로 쓰인다 —
    등록 전에는 원장이 이 파일 안에서만 디스패치되는 요소(hp:nbSpace/
    fwSpace)를 read=False로 오판했다."""

    module = _module()
    assert "strip_namespace" in module._LOCAL_NAME_GETTERS
    source = (
        "def paragraph_text(self, paragraph):\n"
        "    for child in run:\n"
        "        tag = strip_namespace(child.tag)\n"
        "        if tag == 'nbSpace':\n"
        "            pass\n"
        "        elif tag == 'fwSpace':\n"
        "            pass\n"
    )
    windows = module._build_dispatch_windows(source)
    assert module._bare_name_dispatched("nbSpace", windows)
    assert module._bare_name_dispatched("fwSpace", windows)


def test_strip_namespace_getter_reproduces_nbspace_fwspace_false_negative_on_real_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """결함-부활: 실제 `text_extractor.py` 소스에서, `strip_namespace`를
    게터 목록에서 빼면(수리 OFF) `hp:nbSpace`/`hp:fwSpace`가 다시
    read=False로 재현되고, 실제 등록된 목록(수리 ON)을 쓰면 고쳐진다."""

    module = _module()
    text_extractor_py = ROOT / "src" / "hwpx" / "tools" / "text_extractor.py"
    raw_text = text_extractor_py.read_text(encoding="utf-8")
    stripped = module._strip_non_code_text(raw_text)

    monkeypatch.setattr(
        module,
        "_LOCAL_NAME_GETTERS",
        ("local_name", "tag_local_name", "_element_local_name", "_local_name"),
    )
    monkeypatch.setattr(
        module,
        "_ASSIGN_GETTER_RE",
        re.compile(r"(\w+)\s*=\s*(?:" + "|".join(module._LOCAL_NAME_GETTERS) + r")\("),
    )
    monkeypatch.setattr(
        module,
        "_DIRECT_GETTER_RE",
        re.compile(r"(?:" + "|".join(module._LOCAL_NAME_GETTERS) + r")\([^()]*\)"),
    )
    broken_windows = module._build_dispatch_windows(stripped)
    for name in ("nbSpace", "fwSpace"):
        assert not module._bare_name_dispatched(name, broken_windows), (
            f"hp:{name} should be a false negative without strip_namespace registered"
        )

    monkeypatch.undo()
    fixed_windows = module._build_dispatch_windows(stripped)
    for name in ("nbSpace", "fwSpace"):
        assert module._bare_name_dispatched(name, fixed_windows), (
            f"hp:{name} should resolve once strip_namespace is registered"
        )


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


# ---------------------------------------------------------------------------
# 2026-08-04 감사 §3 수리 회귀
# ---------------------------------------------------------------------------


def test_comment_only_source_is_not_counted_as_coverage() -> None:
    """감사 실증: 주석·독스트링에 태그를 언급하는 것만으로는 커버리지로
    잡히면 안 된다 — 코드가 없으면 아무것도 안 잡혀야 한다."""

    module = _module()
    fake_source = (
        '"""Module docstring mentions <hp:tbl and ET.Element("hp:sneakyWrite").'
        '"""\n'
        "# comment also mentions <hp:commentOnly and SubElement(\n"
        "\"bare string statement mentions hh:bareStatement SubElement\"\n"
        "import os\n"
    )
    stripped = module._strip_non_code_text(fake_source)
    assert "hp:tbl" not in stripped
    assert "hp:sneakyWrite" not in stripped
    assert "hp:commentOnly" not in stripped
    assert "hh:bareStatement" not in stripped
    assert "import os" in stripped


def test_strip_non_code_text_preserves_real_code() -> None:
    """진짜 코드(할당·호출·리터럴 인자)는 하나도 안 지워야 한다 — 스트립이
    과하면 진짜 커버리지까지 날아간다."""

    module = _module()
    source = (
        "_HP = '{http://example/paragraph}'\n"
        "\n"
        "def f(el):\n"
        "    # not a real write\n"
        "    node = ET.SubElement(el, f'{_HP}tbl', {})\n"
        "    return node\n"
    )
    stripped = module._strip_non_code_text(source)
    assert "ET.SubElement(el, f'{_HP}tbl', {})" in stripped
    assert "def f(el):" in stripped
    assert "not a real write" not in stripped


def test_etree_element_alias_counts_as_write_marker() -> None:
    """감사 실증: `etree.Element(` 별칭이 `_WRITE_MARKERS`에 없어서
    `oxml/body.py`의 변경추적 마크 방출 등 14곳이 안 보였다."""

    module = _module()
    assert "etree.Element(" in module._WRITE_MARKERS

    source = "node = etree.Element(f'{_HP}deliberateWrite', {})\n"
    read, write = module.classify_code_usage(
        "hp", "deliberateWrite", "paragraph", source, [], {}
    )
    assert (read, write) == (True, True)


def test_argument_tag_resolver_single_hop() -> None:
    """함수 파라미터가 자기 본문에서 직접 태그 조립에 쓰이고, 그 함수가
    리터럴로 호출되는 자리 — 감사가 실증한 hh:ratio/hh:spacing 결함의
    최소 재현."""

    module = _module()
    source = (
        "_HH = '{http://example/head}'\n"
        "\n"
        "def _set_lang_values(element, tag, value):\n"
        "    node = element.find(f'{_HH}{tag}')\n"
        "    if node is None:\n"
        "        node = _append_child(element, f'{_HH}{tag}')\n"
        "    node.set('hangul', str(value))\n"
        "\n"
        "def _apply(element, spec):\n"
        "    _set_lang_values(element, 'ratio', spec.ratio)\n"
        "    _set_lang_values(element, 'spacing', spec.letter_spacing)\n"
    )
    resolved = module._resolve_argument_tag_literals([(Path("synthetic.py"), source)])
    assert resolved[("hh", "ratio")] == (True, True)
    assert resolved[("hh", "spacing")] == (True, True)


def test_argument_tag_resolver_propagates_through_forwarding_call() -> None:
    """파라미터가 리터럴 없이 다른 함수로 그대로 넘어간 뒤, 그 함수가 태그
    조립을 하는 2단계 전달 — 감사가 실증한 hp:footNotePr 결함의 최소
    재현(section_format.py의 _note_shape → _note_pr_element 패턴)."""

    module = _module()
    source = (
        "_HP = '{http://example/paragraph}'\n"
        "\n"
        "class SectionFormat:\n"
        "    def _note_pr_element(self, tag, create=False):\n"
        "        element = self.element.find(f'{_HP}{tag}')\n"
        "        if element is not None or not create:\n"
        "            return element\n"
        "        return ET.SubElement(self.element, f'{_HP}{tag}', {})\n"
        "\n"
        "    def _note_shape(self, tag):\n"
        "        return self._note_pr_element(tag)\n"
        "\n"
        "    @property\n"
        "    def footnote_shape(self):\n"
        "        return self._note_shape('footNotePr')\n"
    )
    resolved = module._resolve_argument_tag_literals([(Path("synthetic.py"), source)])
    assert resolved[("hp", "footNotePr")] == (True, True)


def test_manual_code_usage_overrides_require_evidence() -> None:
    """근거 없는 화이트리스트 항목은 생성기가 거부한다."""

    module = _module()
    with pytest.raises(ValueError, match="evidence"):
        module._validate_manual_overrides(
            (module.ManualCodeUsageOverride("hp", "fake", True, True, evidence=""),)
        )
    with pytest.raises(ValueError, match="file:line"):
        module._validate_manual_overrides(
            (
                module.ManualCodeUsageOverride(
                    "hp", "fake", True, True, evidence="trust me, it's real"
                ),
            )
        )
    # 실제 등재된 화이트리스트는 자기 검증을 통과해야 한다(임포트 시점에
    # 이미 통과했지만, 회귀를 위해 다시 실행).
    module._validate_manual_overrides(module._MANUAL_CODE_USAGE_OVERRIDES)


def test_manual_override_reproduces_insert_begin_family_write() -> None:
    """감사 인용 오판(`hp:insertBegin` write=none)의 반증: 화이트리스트를
    끄면 오판이 재현되고, 켜면 고쳐진다."""

    module = _module()
    for name in ("insertBegin", "insertEnd", "deleteBegin", "deleteEnd"):
        assert ("hp", name) in module.MANUAL_CODE_USAGE_OVERRIDES_BY_KEY
        read, write = module.classify_code_usage("hp", name, "paragraph", "", [], {})
        assert (read, write) == (True, True), f"hp:{name} should resolve via the manual whitelist"


def test_manual_override_reproduces_track_change_family_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """이번 사이클(6.5) 원장 재스캔이 새로 찾은 위음성의 반증:
    `hh:trackChange`/`trackChangeAuthor`는 `header.py`의
    `track_change_to_xml`/`track_change_author_to_xml`이 실제로 쓴다 —
    `etree.Element("{http://www.hancom.co.kr/hwpml/2011/head}trackChange", ...)`
    처럼 전체 네임스페이스 URI를 문자열 리터럴로 그대로 박아 넣는 관용구라,
    코드베이스가 보통 쓰는 `{_HH}trackChange` 별칭 패턴(패턴 3)이 못 잡는다
    — `}` 바로 앞 글자가 `HH`가 아니라 `head`이기 때문이다. 실제 소스로
    재현한다: 화이트리스트를 지우면(수리 OFF) 실 `header.py` 텍스트만으로는
    write=none이 재현되고, 실제 등재된 화이트리스트(수리 ON)를 쓰면 고쳐진다.
    (read는 원래도 정확했다 — `local_name(child) == "trackChange"` 직접
    비교가 디스패치 윈도로 이미 잡혔다.)"""

    module = _module()
    header_py = ROOT / "src" / "hwpx" / "oxml" / "header.py"
    raw_text = header_py.read_text(encoding="utf-8")
    stripped = module._strip_non_code_text(raw_text)
    dispatch_windows = module._build_dispatch_windows(stripped)

    names = ("trackChange", "trackChangeAuthor")
    for name in names:
        assert ("hh", name) in module.MANUAL_CODE_USAGE_OVERRIDES_BY_KEY

    monkeypatch.setattr(module, "MANUAL_CODE_USAGE_OVERRIDES_BY_KEY", {})
    for name in names:
        broken = module.classify_code_usage(
            "hh", name, "head", stripped, dispatch_windows, {}
        )
        assert broken == (True, False), (
            f"hh:{name} should read=True (dispatch window still finds it) but "
            "write=False (whitelist removed) without the whitelist"
        )

    monkeypatch.undo()
    for name in names:
        fixed = module.classify_code_usage(
            "hh", name, "head", stripped, dispatch_windows, {}
        )
        assert fixed == (True, True), f"hh:{name} should resolve to (read, write) via the manual whitelist"


def test_manual_override_reproduces_run_choice_atom_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """사이클 6.5 트레인⑲(특수 인라인 텍스트 원자 저작)이 새로 낸 위음성의
    반증: `_document_primitives.py`의 `_RUN_CHOICE_ATOM_MARKERS`는
    `"\\n": "lineBreak"`처럼 요소 이름을 **딕셔너리 값**으로만 담고, 실제
    태그는 `_child_tag_like(run, marker_name, _HP_NS)`처럼 그 값을 담은
    변수로 조립한다 — 리터럴 옆에 `hp:`/`{_HP}` 네임스페이스 마커가 없어
    한정 패턴이 못 잡는다(hp:markpenBegin과 같은 결함 계열). 실제 소스로
    재현한다: 화이트리스트를 지우면(수리 OFF) 이 파일 안에서는 세 이름
    다 read=False·write=False가 재현되고, 실제 등재된 화이트리스트(수리
    ON)를 쓰면 고쳐진다."""

    module = _module()
    primitives_py = ROOT / "src" / "hwpx" / "oxml" / "_document_primitives.py"
    raw_text = primitives_py.read_text(encoding="utf-8")
    stripped = module._strip_non_code_text(raw_text)
    dispatch_windows = module._build_dispatch_windows(stripped)

    names = ("lineBreak", "nbSpace", "fwSpace")
    for name in names:
        assert ("hp", name) in module.MANUAL_CODE_USAGE_OVERRIDES_BY_KEY

    monkeypatch.setattr(module, "MANUAL_CODE_USAGE_OVERRIDES_BY_KEY", {})
    for name in names:
        broken = module.classify_code_usage(
            "hp", name, "paragraph", stripped, dispatch_windows, {}
        )
        assert broken == (False, False), (
            f"hp:{name} should be a false negative in _document_primitives.py "
            "alone without the whitelist"
        )

    monkeypatch.undo()
    for name in names:
        fixed = module.classify_code_usage(
            "hp", name, "paragraph", stripped, dispatch_windows, {}
        )
        assert fixed == (True, True), f"hp:{name} should resolve via the manual whitelist"


def test_manual_override_reproduces_hhs_diff_op_family_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """감사 이후(cycle 6.4 train 15)에 새로 생긴 위음성의 반증:
    `hhs:insert/update/delete/position`은 `history_part.py`의 범용 재귀
    파서(`_parse_diff_op`)가 실제로 읽는다 — `name = local_name(node)`를
    비교 없이 그대로 `DiffNode.op`에 담기 때문에(태그 리터럴도 `==`/`in`
    비교 디스패치도 없음), 한정 태그 패턴도 접두-없는 디스패치 탐지기도
    못 잡는다. 실제 소스로 재현한다: 화이트리스트를 지우면(수리 OFF)
    실 `history_part.py` 텍스트만으로는 여전히 위음성이 재현되고, 실제
    등재된 화이트리스트(수리 ON)를 쓰면 고쳐진다."""

    module = _module()
    history_part = ROOT / "src" / "hwpx" / "oxml" / "history_part.py"
    raw_text = history_part.read_text(encoding="utf-8")
    stripped = module._strip_non_code_text(raw_text)
    dispatch_windows = module._build_dispatch_windows(stripped)

    names = ("insert", "update", "delete", "position")
    for name in names:
        assert ("hhs", name) in module.MANUAL_CODE_USAGE_OVERRIDES_BY_KEY

    # 수리 OFF: 화이트리스트를 빈 테이블로 바꾸면, 진짜 소스 텍스트를 스캔해도
    # 위음성이 재현된다 — 이 결함이 화이트리스트 없이는 실제로 못 잡히는
    # 부류임을 실코드로 증명한다.
    monkeypatch.setattr(module, "MANUAL_CODE_USAGE_OVERRIDES_BY_KEY", {})
    for name in names:
        broken = module.classify_code_usage(
            "hhs", name, "history", stripped, dispatch_windows, {}
        )
        assert broken == (False, False), f"hhs:{name} should be a false negative without the whitelist"

    # 수리 ON: 실제 등재된 화이트리스트를 복원하면 고쳐진다.
    monkeypatch.undo()
    for name in names:
        fixed = module.classify_code_usage(
            "hhs", name, "history", stripped, dispatch_windows, {}
        )
        assert fixed == (True, False), f"hhs:{name} should resolve via the manual whitelist (read-only)"


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


# ---------------------------------------------------------------------------
# openrate 코퍼스 환류 v4~v8 (D항 + 2026-08 사이클 6.5 트레인⑰ 확장)
# ---------------------------------------------------------------------------


def test_openrate_stratum_mapping_resolves_against_real_capability_keywords() -> None:
    """_OPENRATE_STRATUM_TO_CAPABILITY_AREA가 가리키는 영역은 전부
    CAPABILITY_KEYWORDS에도 실재해야 한다(무근거 매핑 방지)."""

    module = _module()
    registered_areas = set(module.CAPABILITY_KEYWORDS.values())
    for area in module._OPENRATE_STRATUM_TO_CAPABILITY_AREA.values():
        assert area in registered_areas, f"{area!r} is not a real capability area"


def test_openrate_stratum_to_elements_resolves_against_real_elements() -> None:
    """_OPENRATE_STRATUM_TO_ELEMENTS가 지목하는 (prefix, name)은 전부
    스키마 또는 코퍼스에 실재하는 요소여야 한다(무근거 지목 방지) — census나
    스키마 어느 쪽에도 없는 오타 키를 조용히 통과시키지 않는다."""

    module = _module()
    schema_elements = module.parse_schema_elements()
    known_keys = {
        (prefix, name) for prefix, names in schema_elements.items() for name in names
    }
    for stratum, keys in module._OPENRATE_STRATUM_TO_ELEMENTS.items():
        for key in keys:
            assert key in known_keys, f"{stratum!r} names unknown element {key!r}"


def test_openrate_stratum_maps_are_disjoint() -> None:
    """같은 스트라텀이 capabilityArea 경로와 요소-직접 경로 둘 다에 등록되면
    안 된다 — 하나의 스트라텀은 하나의 매핑 방식만 쓴다(§4b 독스트링이
    설명하는 이유 그대로: capabilityArea가 있으면 그 경로, 없으면 요소
    직접)."""

    module = _module()
    area_strata = set(module._OPENRATE_STRATUM_TO_CAPABILITY_AREA)
    element_strata = set(module._OPENRATE_STRATUM_TO_ELEMENTS)
    assert area_strata.isdisjoint(element_strata)


def test_stratum_accepted_handles_both_schema_generations() -> None:
    """v1~v5(Windows COM, opened/requested 필드 있음)와 v6+(macOS GUI,
    그 필드가 아예 없음 — PDF export 성공이 열기를 함의) 둘 다 받는다."""

    module = _module()
    # 구세대: opened/requested까지 맞아야 수용.
    assert module._stratum_accepted(
        {"render_checked": 15, "render_failed": 0, "opened": 15, "requested": 15}
    )
    assert not module._stratum_accepted(
        {"render_checked": 15, "render_failed": 0, "opened": 14, "requested": 15}
    )
    # 신세대: 그 필드가 없으면 render_checked/render_failed만으로 판단.
    assert module._stratum_accepted({"render_checked": 15, "render_failed": 0})
    assert not module._stratum_accepted({"render_checked": 0, "render_failed": 0})
    assert not module._stratum_accepted({"render_checked": 15, "render_failed": 1})


def test_load_openrate_capability_receipts_rejects_invalid_harness(tmp_path: Path) -> None:
    module = _module()
    path = tmp_path / "report-v4.json"
    path.write_text(
        json.dumps(
            {
                "harness_valid": False,
                "strata": {
                    "authored-chart": {
                        "render_checked": 15,
                        "render_failed": 0,
                        "opened": 15,
                        "requested": 15,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    assert module._load_openrate_capability_receipts([path]) == {}


def test_load_openrate_capability_receipts_accepts_clean_stratum(tmp_path: Path) -> None:
    module = _module()
    path = tmp_path / "report-v4.json"
    path.write_text(
        json.dumps(
            {
                "harness_valid": True,
                "strata": {
                    "authored-chart": {
                        "render_checked": 15,
                        "render_failed": 0,
                        "opened": 15,
                        "requested": 15,
                    },
                    "authored-formfield": {
                        "render_checked": 15,
                        "render_failed": 0,
                        "opened": 15,
                        "requested": 15,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    receipts = module._load_openrate_capability_receipts([path])
    assert receipts == {"차트": True}, "unmapped strata (authored-formfield) must not leak in"


def test_load_openrate_capability_receipts_merges_across_multiple_reports(
    tmp_path: Path,
) -> None:
    """여러 report 파일에 걸친 스트라타를 하나의 receipts 테이블로 OR-병합
    한다 — 서로 다른 스트라타가 같은 capabilityArea를 가리키는 실제 사례
    (v4의 authored-footnote/authored-note-shape → 둘 다 "각주/미주")를
    두 개의 서로 다른 report 파일에 걸쳐 재현한다."""

    module = _module()
    v4a = tmp_path / "report-v4.json"
    v4b = tmp_path / "report-v4b.json"
    v4a.write_text(
        json.dumps({"harness_valid": True, "strata": {"authored-chart": {
            "render_checked": 15, "render_failed": 0, "opened": 15, "requested": 15,
        }, "authored-footnote": {
            "render_checked": 15, "render_failed": 0, "opened": 15, "requested": 15,
        }}}),
        encoding="utf-8",
    )
    v4b.write_text(
        json.dumps({"harness_valid": True, "strata": {
            "authored-note-shape": {
                "render_checked": 10, "render_failed": 0, "opened": 10, "requested": 10,
            },
        }}),
        encoding="utf-8",
    )
    receipts = module._load_openrate_capability_receipts([v4a, v4b])
    assert receipts == {"차트": True, "각주/미주": True}


def test_load_openrate_element_receipts_accepts_clean_stratum(tmp_path: Path) -> None:
    module = _module()
    path = tmp_path / "report-v5.json"
    path.write_text(
        json.dumps(
            {
                "harness_valid": True,
                "strata": {
                    "authored-caption": {
                        "render_checked": 15,
                        "render_failed": 0,
                        "opened": 15,
                        "requested": 15,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    receipts = module._load_openrate_element_receipts([path])
    assert receipts == {("hp", "caption"): True}


def test_mixed_support_capability_area_is_not_used_for_openrate_mapping() -> None:
    """구현 중 실제로 겪은 회귀의 재현 가드: authored-polygon/authored-arc를
    "arc·polygon·curve·connectLine" capabilityArea에 매핑했더니, 그 영역이
    공유하는 curve/connectLine/seg(정직 보류 중 — write=none)까지 검증된
    것처럼 verificationBasis가 붙었다. 이 스트라타는 capabilityArea 경로가
    아니라 요소 직접 경로여야 한다."""

    module = _module()
    assert "authored-polygon" not in module._OPENRATE_STRATUM_TO_CAPABILITY_AREA
    assert "authored-arc" not in module._OPENRATE_STRATUM_TO_CAPABILITY_AREA
    assert module._OPENRATE_STRATUM_TO_ELEMENTS["authored-polygon"] == (("hp", "polygon"),)
    assert module._OPENRATE_STRATUM_TO_ELEMENTS["authored-arc"] == (("hp", "arc"),)


def test_checkbox_area_openrate_signal_does_not_bleed_onto_radio_and_button() -> None:
    """트레인⑰ 사후 재검증이 잡은 두 번째 사례(위 테스트의 복합-경로
    버전): v4의 authored-checkbox 스트라타가 "체크박스 양식개체" 영역
    전체에 openrate 수용 신호를 흘린다 — 그 영역의 저작 표면
    (add_check_box)이 실제로 검증하는 건 hp:checkBtn/formCharPr뿐인데,
    같은 영역에 속한 hp:radioBtn/btn(읽기·보존만, 저작 API 없음 —
    지원 매트릭스 자신도 그렇게 명시)까지 검증된 것처럼 보였다.
    _OPENRATE_MIXED_SUPPORT_AREA_EXCLUSIONS로 이 둘만 영역의 openrate
    성분을 안 받도록 강등해야 한다."""

    module = _module()
    assert ("hp", "btn") in module._OPENRATE_MIXED_SUPPORT_AREA_EXCLUSIONS
    assert ("hp", "radioBtn") in module._OPENRATE_MIXED_SUPPORT_AREA_EXCLUSIONS

    ledger = _load_ledger()
    by_key = {(e["namespace"], e["element"]): e for e in ledger["elements"]}

    for name in ("btn", "radioBtn"):
        entry = by_key[("hp", name)]
        assert entry["codeWrite"] == "none"
        assert entry["capabilityArea"] == "체크박스 양식개체"  # 라벨은 유지
        assert entry["verificationBasis"] == "by-capability-area"  # openrate 성분 제거
        assert entry["verificationBasis"] is None or "openrate-corpus" not in entry["verificationBasis"]

    # 대조군: 같은 영역의 실제 저작 표면은 복합 경로를 그대로 유지해야 한다
    # (강등이 영역 전체가 아니라 이 두 요소에만 적용됐는지 확인).
    for name in ("checkBtn", "formCharPr"):
        entry = by_key[("hp", name)]
        assert entry["codeWrite"] == "api"
        assert entry["verificationBasis"] == "by-capability-area+openrate-corpus"


# 위 회귀의 일반화된 불변식("openrate-corpus" 성분이 있으면 순수·복합
# 무관하게 codeWrite=="api"를 요구)은 test_ledger_schema_is_valid에 상시
# 체크로 이미 들어가 있다 — 전 요소를 훑는 자리라 여기 따로 반복하지 않는다.
# 복합 경로("by-capability-area+openrate-corpus")의 회귀 사례(hp:btn/
# radioBtn — "체크박스 양식개체" 영역의 authored-checkbox 신호가 흘렀던
# 것)는 test_checkbox_area_openrate_signal_does_not_bleed_onto_radio_and_button
# 이 이름 붙여 고정한다(_OPENRATE_MIXED_SUPPORT_AREA_EXCLUSIONS로 강등).


def test_combine_verification_basis() -> None:
    module = _module()
    assert module._combine_verification_basis(None, False) is None
    assert module._combine_verification_basis(None, True) == "by-openrate-corpus"
    assert module._combine_verification_basis("by-capability-area", False) == "by-capability-area"
    assert (
        module._combine_verification_basis("by-capability-area", True)
        == "by-capability-area+openrate-corpus"
    )


def test_openrate_basis_requires_authoring_api_everywhere() -> None:
    """No element may carry an openrate verification component unless we can
    author it - pure or area-composed alike. The area-routed receipt otherwise
    leaks "real Hancom accepted our authoring" onto read-only siblings."""
    import json
    from pathlib import Path

    ledger = json.loads(
        (Path(__file__).resolve().parents[1] / "docs" / "coverage-ledger.json").read_text(
            encoding="utf-8"
        )
    )
    offenders = [
        f"{e['namespace']}:{e['element']}"
        for e in ledger["elements"]
        if "openrate" in str(e.get("verificationBasis") or "")
        and e["codeWrite"] != "api"
    ]
    assert offenders == [], offenders
