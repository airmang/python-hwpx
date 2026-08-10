# SPDX-License-Identifier: Apache-2.0
"""OWPML 요소 커버리지 원장 생성기.

"우리가 OWPML의 무엇을 읽고/쓰고/실한컴 검증했는가"를 손으로 쓴 지원 주장이
아니라 5개 입력에서 결정론적으로 재산출한다:

1. **스키마 전집** — ``DevDoc/OWPML SCHEMA/*.xml`` (OWPML 2024 XSD 7종)에서
   ``xs:element name="..."`` 선언을 전부 걷어 네임스페이스 접두(hp/hh/hc/hs/
   hm/hhs/hv)별 요소 집합을 만든다. 접두는 ``hwpx.oxml.namespaces``의
   ``HWPML_COMPAT_ROOT_NAMESPACES``/``namespace_family()``에서 파생한다 —
   즉 이 스크립트가 별도로 접두 규약을 하드코딩하지 않고, 라이브러리가 실제
   문서를 읽고 쓸 때 쓰는 바로 그 접두를 그대로 쓴다.
2. **실코퍼스 빈도** — ``docs/_extra/element-census.json``. 생성기는
   ``scripts/build_element_census.py``로 커밋돼 있다(2026-08-04 감사 §3-C1이
   지적한 "생성기 미보존" 결함의 수리) — 전 파트·전 네임스페이스를 스캔하고
   ``--census``로 다른 경로를 줄 수 있다. census에 없는 요소는 조작·추정
   없이 빈도 0으로 정직하게 기록한다.
3. **코드 참조** — ``src/hwpx/`` 전체에서 요소별 태그 리터럴·QName 조립
   패턴, 접두 없는 ``local_name()`` 계열 비교 디스패치, 루프 변수로 태그가
   조립되는 자리, 그리고 함수 파라미터로 태그가 전달되는 자리(고정점
   전파 + 리터럴 호출부 해석)까지 네 경로를 합쳐 찾는다. 스캔 전에
   주석·독스트링은 블랭크 처리한다(``tokenize``+``ast``) —  비코드 텍스트가
   커버리지로 잘못 집계되는 것을 막는다(2026-08-04 감사 §3-C2 수리).
   ``makeelement``/``SubElement``/``_append_child``/``etree.Element(``/여는
   태그 리터럴(``<hp:xxx``) 근방이면 쓰기(``api``), 그 밖의 참조는 읽기로
   잡는다. 코드에 없지만 ``Skeleton.hwpx``에 상수로 박혀 있으면
   ``frozen-template``(구조는 통과하되 절대 못 바꾸는 영역)로 분류한다 —
   이게 이 원장의 핵심 정직 포인트다. 완전히 동적으로 조립되는 태그는
   근거-필수 명시 화이트리스트(``_MANUAL_CODE_USAGE_OVERRIDES``)로 다룬다.
4. **실한컴 검증 여부(지원 매트릭스)** — ``src/hwpx/data/contract_docs/
   support-matrix.md``의 행별 등급을 요소로 근사 매핑한다. 매핑은 매트릭스
   산문에 실제로 언급된 태그·헬퍼로만 근거를 두며(예: "hp:formCharPr",
   "add_line"), 근거 없는 승격은 하지 않는다 — 대응 행이 불분명한 요소는
   ``capabilityArea: null``로 남는다. 매핑된 요소라도 그 행의 등급 문자열에
   "Render-verified"가 없으면 이 출처로는 ``verificationBasis``가 null이다.
5. **실한컴 검증 여부(openrate 코퍼스, v4~v16)** — ``docs/openrate/
   report-v{4,5,6,7,8,9,10,11,12,13,14,15,16}.json``의 스트라타별 실제 Hancom 수용 receipt를
   ``verificationBasis``로 환류한다(2026-08-04 감사 R4 수리 — "두 산출물이
   서로를 모른다" — 의 v4 배선을 v5~v8까지 확장(2026-08 사이클 6.5 트레인
   ⑰), v9까지 확장(2026-08 사이클 6.6 트레인⑳), v10까지 확장(2026-08
   사이클 6.7 트레인㉔), v11까지 확장(2026-08 사이클 6.8 트레인㉘), v12까지
   확장(2026-08 사이클 6.9 트레인㉜), v13까지 확장(2026-08 사이클 6.10
   트레인㉟), v14까지 확장(2026-08 사이클 6.11 트레인㊳), v15까지 확장
   (2026-08 사이클 6.12 트레인㊶), v16까지 확장(2026-08 사이클 6.13
   트레인㊹ — 5개 신규 스트라타 전부 (b) 갈래에도 안 얹힌다: 요소가
   이미 다른 영역 소유라 재등록하면 그 영역 카운트를 덮어쓰므로,
   지원 매트릭스 산문 인용만으로 등급을 올린다)). 두 갈래로
   다룬다: (a)
   스트라타가 **이미 등록된 capabilityArea**와 1:1로 대응하면
   (``CAPABILITY_KEYWORDS``에 그 요소가 실재 등재돼 있으면)
   ``_OPENRATE_STRATUM_TO_CAPABILITY_AREA``를 거쳐 그 영역의 전 요소에
   환류한다. (b) capabilityArea가 아예 등록돼 있지 않거나, 있어도 그
   요소만 지목한 것이 아닌 혼합 지원 영역이면 ``_OPENRATE_STRATUM_TO_ELEMENTS``로
   **요소를 직접** 지목한다 — 근거는 각 corpus 생성기 스크립트(
   ``scripts/generate_openrate_corpus_v{5,6,7,8,9,10,11,12,13,14,15}.py``)의 독스트링이 실제로
   호출한다고 명시한 API·요소뿐이다(무근거 매핑 금지, 기존 (a) 경로와
   같은 원칙). ``by-v4-corpus``라는 이름은 지금은 v4 하나만이 아니라
   v4~v16 전체를 가리키므로 ``by-openrate-corpus``로 이번에 이름도
   바로잡았다(이 문자열을 읽는 외부 소비자는 이 레포 안에 없음을 grep으로
   확인 — 파기하는 계약이 아니다).

이 스크립트는 지원 매트릭스·capabilities 레지스트리·census 원본을 전혀
쓰지 않는다(읽기 전용 입력). 산출은 ``docs/coverage-ledger.json``(기계 판독)과
``docs/coverage-ledger.md``(사람 요약) 두 파일이다.

    python scripts/coverage_ledger.py          # 원장 재생성
    python scripts/coverage_ledger.py --check  # 드리프트 검사만(비제로 exit)
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sys
import tokenize
import zipfile
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "DevDoc" / "OWPML SCHEMA"
DEFAULT_CENSUS_PATH = ROOT / "docs" / "_extra" / "element-census.json"
SUPPORT_MATRIX_PATH = ROOT / "src" / "hwpx" / "data" / "contract_docs" / "support-matrix.md"
SKELETON_PATH = ROOT / "src" / "hwpx" / "data" / "Skeleton.hwpx"
SRC_DIR = ROOT / "src" / "hwpx"
#: v4~v16 전부 — 신버전이 생기면 여기 한 줄만 추가하면 된다(receipts 로더
#: 둘 다 이 리스트를 그대로 순회한다). 존재하지 않는 파일은 조용히
#: 건너뛴다(``_load_*`` 쪽에서 ``is_file()`` 가드).
OPENRATE_REPORT_PATHS: tuple[Path, ...] = tuple(
    ROOT / "docs" / "openrate" / f"report-{version}.json"
    for version in ("v4", "v5", "v6", "v7", "v8", "v9", "v10", "v11", "v12", "v13", "v14", "v15", "v16")
)
LEDGER_JSON = ROOT / "docs" / "coverage-ledger.json"
LEDGER_MD = ROOT / "docs" / "coverage-ledger.md"

SCHEMA_VERSION = "python-hwpx.coverage-ledger/v1"
XS_NS = "http://www.w3.org/2001/XMLSchema"

#: 2026-08-04 완전성 감사(§0 요약표)가 인용한 사전-수리 하한 — 실코퍼스 관측
#: 228건 중 write=none 70 · read=none 56 · frozen-template 28. 이 원장의
#: 재생성 시점 population과는 다르므로(census 재구축) 정확한 재현이 아니라
#: "수리 기록" 절의 방향성 참고용 상수다. 값 자체를 바꾸지 말 것 — 감사
#: 문서에 박제된 역사적 사실이다.
_AUDIT_BASELINE_OBSERVED = 228
_AUDIT_BASELINE_WRITE_NONE = 70
_AUDIT_BASELINE_READ_NONE = 56
_AUDIT_BASELINE_FROZEN = 28

#: "version" 패밀리는 ``hwpx.oxml.namespaces.NAMESPACE_URIS``에 아예 없다
#: (버전 레지스트리 자체의 실결함 — ``version.xml``은 ``opc/package.py``의
#: 리터럴 바이트 템플릿으로만 다뤄진다). 접두는 실문서·코드 리터럴
#: (``hv:HCFVersion``)에서 확인된 값을 그대로 쓴다.
_FALLBACK_FAMILY_PREFIX = {"version": "hv"}


def _family_to_prefix() -> dict[str, str]:
    """``hwpx.oxml.namespaces``에서 패밀리→표준 접두 매핑을 파생시킨다.

    하드코딩된 별도 표를 두지 않는다 — 라이브러리가 실제로 문서를 읽고 쓸
    때 쓰는 ``HWPML_COMPAT_ROOT_NAMESPACES``(2011 표준형) 순서를 그대로
    따라가면 각 패밀리의 "기본" 접두(hp10이 아니라 hp 등)가 먼저 등록된다.
    """

    from hwpx.oxml.namespaces import HWPML_COMPAT_ROOT_NAMESPACES, namespace_family

    mapping: dict[str, str] = {}
    for prefix, uri in HWPML_COMPAT_ROOT_NAMESPACES.items():
        family = namespace_family(uri)
        if family is not None:
            mapping.setdefault(family, prefix)
    mapping.update(_FALLBACK_FAMILY_PREFIX)
    return mapping


def _namespace_family_lookup() -> Callable[[str], str | None]:
    from hwpx.oxml.namespaces import namespace_family

    return namespace_family


# ---------------------------------------------------------------------------
# 1) 스키마 전집
# ---------------------------------------------------------------------------


def parse_schema_elements() -> dict[str, dict[str, str]]:
    """``DevDoc/OWPML SCHEMA/*.xml``에서 접두별 {요소: 스키마 파일명}을 만든다."""

    family_to_prefix = _family_to_prefix()
    namespace_family = _namespace_family_lookup()

    by_prefix: dict[str, dict[str, str]] = {}
    for schema_path in sorted(SCHEMA_DIR.glob("*.xml")):
        tree = etree.parse(str(schema_path))
        root = tree.getroot()
        target_ns = root.get("targetNamespace")
        if not target_ns:
            continue
        family = namespace_family(target_ns)
        if family is None:
            # 2024 URI가 namespaces.py 레지스트리에 없는 패밀리(version).
            if target_ns.rsplit("/", 1)[-1] not in _FALLBACK_FAMILY_PREFIX:
                raise ValueError(f"unrecognized targetNamespace: {target_ns} ({schema_path.name})")
            family = target_ns.rsplit("/", 1)[-1]
        prefix = family_to_prefix.get(family)
        if prefix is None:
            raise ValueError(f"no known prefix for family {family!r} ({schema_path.name})")

        names = sorted(
            {
                el.get("name")
                for el in root.iter(f"{{{XS_NS}}}element")
                if el.get("name")
            }
        )
        bucket = by_prefix.setdefault(prefix, {})
        for name in names:
            bucket[name] = schema_path.name
    return by_prefix


# ---------------------------------------------------------------------------
# 2) 실코퍼스 빈도
# ---------------------------------------------------------------------------


@dataclass
class CorpusCensus:
    frequencies: dict[tuple[str, str], int]
    total_real_files: int
    attribute_names: dict[tuple[str, str], list[str]]
    foreign_namespaces: dict[str, int]
    unnamespaced_elements: dict[str, int]
    unknown_files: dict[str, object]
    population_note: str | None


def load_corpus(census_path: Path) -> CorpusCensus:
    """실코퍼스 census를 읽는다.

    ``build_element_census.py``(v2 스키마)로 재생성된 census는 요소 빈도
    외에 속성 축(``real_attribute_names_by_element``)·외부 네임스페이스
    가시화(``foreignNamespaces``)·비네임스페이스 요소(``unnamespacedElements``)·
    unknown 파일 처분(``unknownFiles``)을 함께 싣는다. 구 스키마(v1, 요소
    빈도만)로 넘어온 census도 그대로 읽힌다 — 새 필드는 전부 ``.get``으로
    선택적이다."""

    if not census_path.is_file():
        raise FileNotFoundError(
            f"corpus census not found: {census_path}\n"
            "vendored snapshot이 없으면 --census로 원본 census 경로를 넘기거나 "
            "scripts/build_element_census.py로 새로 생성할 것."
        )
    document = json.loads(census_path.read_text(encoding="utf-8"))
    total_real_files = int(document["files"]["real"])
    frequencies: dict[tuple[str, str], int] = {}
    for key, count in document["real_element_filecounts"].items():
        prefix, _, name = key.partition(":")
        frequencies[(prefix, name)] = int(count)

    attribute_names: dict[tuple[str, str], list[str]] = {}
    for key, names in document.get("real_attribute_names_by_element", {}).items():
        prefix, _, name = key.partition(":")
        attribute_names[(prefix, name)] = list(names)

    return CorpusCensus(
        frequencies=frequencies,
        total_real_files=total_real_files,
        attribute_names=attribute_names,
        foreign_namespaces=dict(document.get("foreignNamespaces", {})),
        unnamespaced_elements=dict(document.get("unnamespacedElements", {})),
        unknown_files=dict(document.get("unknownFiles", {"count": document["files"].get("unknown", 0), "reasons": {}})),
        population_note=document.get("populationNote"),
    )


# ---------------------------------------------------------------------------
# 3) 코드 참조 (읽기/쓰기)
# ---------------------------------------------------------------------------

#: makeelement/append 근방이면 "새 요소를 만든다"는 강한 신호.
#:
#: ``etree.Element(`` (bare, unaliased ``from lxml import etree``)는
#: 2026-08-04 감사가 실증한 위음성이었다: ``oxml/body.py``의 변경추적 마크
#: 방출(``_track_change_mark_to_xml``)을 포함해 14곳이 이 형태로 쓰는데
#: ``ET.Element(``/``LET.Element(`` 별칭만 있어 전부 안 보였다.
_WRITE_MARKERS = (
    "makeelement",
    "SubElement",
    "ET.Element(",
    "LET.Element(",
    "etree.Element(",
    "_append_child",
    "_build_",
)

#: 매치 앞뒤로 몇 글자를 봐서 쓰기 신호(위 마커)를 찾을지 — 멀티라인 호출
#: (예: ``_append_child(\n    parent,\n    _child_tag_like(parent, "p", _HP_NS),\n)``)
#: 을 잡기 위해 줄 단위가 아니라 글자 단위 윈도로 잡는다.
_WINDOW_BACK = 150
_WINDOW_FORWARD = 50


def _read_source_files() -> list[tuple[Path, str]]:
    """``src/hwpx/**/*.py``를 (경로, 텍스트) 쌍의 결정론적 순서 목록으로 읽는다."""

    paths = sorted(SRC_DIR.rglob("*.py"))
    return [(path, path.read_text(encoding="utf-8")) for path in paths]


def _build_line_offsets(text: str) -> list[int]:
    offsets = [0]
    for line in text.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def _strip_non_code_text(text: str) -> str:
    """주석과 "베어 문자열" 문(독스트링 포함)을 공백으로 지운다(레이아웃·줄
    번호는 보존) — 아래 평문 마커/디스패치 스캐너가 설명 산문을 실제 태그
    참조로 오인하지 못하게 한다.

    이 모듈의 ``ast`` 기반 리졸버(``_resolve_loop_tag_tables``,
    ``_resolve_argument_tag_literals``)는 이 함수와 무관하게 원본 텍스트를
    그대로 읽는다 — 문자열 리터럴 안에서는 파이썬 문법상 진짜
    ``ast.For``/``ast.Call`` 노드가 나올 수 없으므로 애초에 이 위양성에
    노출되지 않는다. 노출됐던 건 평문 부분열 매칭 스캐너뿐이다(2026-08-04
    감사 실증: 스트립 후 재계산하면 13개 요소 판정이 뒤집힌다 —
    codeWriteApi 134→123, codeRead 192→186)."""

    line_offsets = _build_line_offsets(text)

    def to_offset(line: int, col: int) -> int:
        return line_offsets[line - 1] + col

    spans: list[tuple[int, int]] = []

    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                spans.append((to_offset(*tok.start), to_offset(*tok.end)))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass

    try:
        tree = ast.parse(text)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                continue
            value = node.value
            if value.end_lineno is None or value.end_col_offset is None:
                continue
            spans.append(
                (
                    to_offset(value.lineno, value.col_offset),
                    to_offset(value.end_lineno, value.end_col_offset),
                )
            )

    if not spans:
        return text

    chars = list(text)
    for start, end in spans:
        for i in range(start, end):
            if chars[i] != "\n":
                chars[i] = " "
    return "".join(chars)


def _read_source_corpus(files: list[tuple[Path, str]]) -> str:
    """파일 목록을 주석·독스트링을 지운 뒤 하나의 탐색용 텍스트로 합친다."""

    return "\n\n".join(_strip_non_code_text(text) for _path, text in files)


#: 이 코드베이스 전역에 반복되는 관용구: ``name = local_name(child)`` 로 접두
#: 없는 로컬 네임을 뽑은 뒤 ``if name == "xxx": ... elif name == "yyy":``로
#: 디스패치한다(body.py/header.py/document_parts.py/header_part.py/
#: _document/fields.py/tools/*.py 등 전역). 이 호출은 어떤 네임스페이스
#: 접두 마커도 근방에 남기지 않으므로 한정 태그 패턴으로는 못 잡는다.
#:
#: 단순히 "getter 호출 근방의 아무 따옴표 문자열"을 다 읽기로 치면 오탐이
#: 난다 — 예: ``version = root.get("version")``는 getter 호출과 무관하게
#: 우연히 같은 스코프에 있을 뿐인 속성 읽기다. 그래서 두 단계로 좁힌다:
#: (a) ``VAR = local_name(...)`` 뒤 나머지 함수 본문에서 그 **같은 VAR**가
#: ``==``/``!=``/``in``으로 비교되는 자리, (b) getter 호출 결과를 변수 없이
#: 바로 ``== "xxx"``/``in {...}``로 비교하는 자리 — 이 두 경우에만, 비교
#: 연산자 바로 뒤 짧은 구간에서 따옴표 문자열을 찾는다.
#: ``strip_namespace``(사이클 6.5 트레인⑲ 추가): text_extractor.py/
#: object_finder.py 전용 로컬-네임 게터 — oxml 계열의 ``local_name``과
#: 이름만 다를 뿐 동일한 관용구(``tag = strip_namespace(child.tag); if tag
#: == "xxx":``)를 쓴다. 실측: 이 이름을 추가하기 전에는 `text_extractor.py`
#: 안에서 이 관용구로만 디스패치되는 요소(hh:nbSpace/fwSpace)가 read=False로
#: 잡혔다 — 재현·수리 테스트는
#: `test_local_name_getters_recognizes_strip_namespace_dispatch`
#: (tests/test_coverage_ledger.py) 참조.
_LOCAL_NAME_GETTERS = (
    "local_name", "tag_local_name", "_element_local_name", "_local_name",
    "strip_namespace",
)
_ASSIGN_GETTER_RE = re.compile(
    r"(\w+)\s*=\s*(?:" + "|".join(_LOCAL_NAME_GETTERS) + r")\("
)
_DIRECT_GETTER_RE = re.compile(r"(?:" + "|".join(_LOCAL_NAME_GETTERS) + r")\([^()]*\)")
_COMPARISON_TAIL_RE = re.compile(r"\s*(?:==|!=|\bin\b)")
_DEF_OR_CLASS_RE = re.compile(r"^([ \t]*)(?:def|class)\s", re.MULTILINE)
_DISPATCH_SCOPE_CAP = 4000
_COMPARISON_WINDOW = 200


def _scope_end(source_text: str, pos: int, def_starts: list[tuple[int, int]]) -> int:
    line_start = source_text.rfind("\n", 0, pos) + 1
    indent = len(source_text[line_start:pos]) - len(source_text[line_start:pos].lstrip(" \t"))
    end = len(source_text)
    for def_pos, def_indent in def_starts:
        if def_pos > pos and def_indent <= indent:
            return def_pos
    return end


def _build_dispatch_windows(source_text: str) -> list[str]:
    """"비교 연산자 바로 뒤" 구간만 모은다(요소 이름 후보를 찾는 검색 범위)."""

    def_starts = [(m.start(), len(m.group(1))) for m in _DEF_OR_CLASS_RE.finditer(source_text)]
    windows: list[str] = []

    # (a) VAR = getter(...) 후, 같은 함수 안에서 VAR가 비교되는 모든 자리.
    for assign_match in _ASSIGN_GETTER_RE.finditer(source_text):
        var = assign_match.group(1)
        pos = assign_match.start()
        end = min(_scope_end(source_text, pos, def_starts), pos + _DISPATCH_SCOPE_CAP)
        scope = source_text[pos:end]
        anchor_re = re.compile(rf"\b{re.escape(var)}\b\s*(?:==|!=|\bin\b)")
        for anchor in anchor_re.finditer(scope):
            windows.append(scope[anchor.end() : anchor.end() + _COMPARISON_WINDOW])

    # (b) getter(...) 결과를 변수 경유 없이 바로 비교하는 자리.
    for getter_match in _DIRECT_GETTER_RE.finditer(source_text):
        tail = source_text[getter_match.end() : getter_match.end() + 10]
        if _COMPARISON_TAIL_RE.match(tail):
            op_end = getter_match.end() + _COMPARISON_TAIL_RE.match(tail).end()
            windows.append(source_text[op_end : op_end + _COMPARISON_WINDOW])

    return windows


def _bare_name_dispatched(name: str, dispatch_windows: list[str]) -> bool:
    pattern = re.compile(rf'["\']{re.escape(name)}["\']')
    return any(pattern.search(window) for window in dispatch_windows)


# ---------------------------------------------------------------------------
# 3b) 태그가 루프 변수로 조립되는 관용구 (예: ``for child_name, attrs in
#     _BASIC_BORDER_CHILDREN: ET.SubElement(el, f"{_HH}{child_name}", attrs)``)
# ---------------------------------------------------------------------------

#: 패밀리 상수 이름(HP/HH/HC/HS/HM/HHS/HV, 밑줄·10 접미 허용) → 우리 접두.
_CONST_TO_PREFIX = {
    "HP": "hp", "HH": "hh", "HC": "hc", "HS": "hs",
    "HM": "hm", "HHS": "hhs", "HV": "hv",
}
_QUALIFIED_VAR_TAG_RE = re.compile(r"_?(HP|HH|HC|HS|HHS|HM|HV)(?:10)?\}\{(\w+)\}")


def _literal_eval_or_none(node: ast.AST) -> object | None:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def _resolve_loop_tag_tables(files: list[tuple[Path, str]]) -> dict[tuple[str, str], tuple[bool, bool]]:
    """``for VAR[, VAR2] in TABLE:`` 루프가 ``f"{CONST}{VAR}"``로 태그를
    조립하는 자리를 찾아, ``TABLE``이 모듈 레벨 리터럴(인라인이든 상수
    참조든)이면 실제로 어떤 (접두, 이름)이 오가는지 되짚는다.

    ``TABLE``이 함수 인자 등 정적으로 못 푸는 값이면 조용히 건너뛴다(오탐보다
    누락이 낫다 — 이 자리는 방법론 메모에 한계로 남긴다).
    """

    resolved: dict[tuple[str, str], tuple[bool, bool]] = {}

    for _path, text in files:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue

        module_consts: dict[str, object] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and target.id.startswith("_"):
                    value = _literal_eval_or_none(node.value)
                    if value is not None:
                        module_consts[target.id] = value

        for node in ast.walk(tree):
            if not isinstance(node, ast.For):
                continue
            body_text = ast.get_source_segment(text, node) or ""

            # 대상 변수: `for VAR in X:` 또는 `for VAR, VAR2 in X:`
            if isinstance(node.target, ast.Name):
                target_names = [node.target.id]
            elif isinstance(node.target, ast.Tuple):
                target_names = [
                    elt.id if isinstance(elt, ast.Name) else None for elt in node.target.elts
                ]
            else:
                continue

            var_match = _QUALIFIED_VAR_TAG_RE.search(body_text)
            if var_match is None or var_match.group(2) not in target_names:
                continue
            prefix = _CONST_TO_PREFIX[var_match.group(1)]
            var = var_match.group(2)
            position = target_names.index(var)

            # 반복 대상: 인라인 리터럴이거나, `.items()`를 포함해 앞서 모은
            # 모듈 상수를 가리키는 이름.
            iter_node = node.iter
            uses_items = False
            if (
                isinstance(iter_node, ast.Call)
                and isinstance(iter_node.func, ast.Attribute)
                and iter_node.func.attr == "items"
                and isinstance(iter_node.func.value, ast.Name)
            ):
                uses_items = True
                iterable = module_consts.get(iter_node.func.value.id)
            elif isinstance(iter_node, ast.Name):
                iterable = module_consts.get(iter_node.id)
            else:
                iterable = _literal_eval_or_none(iter_node)

            if iterable is None:
                continue

            names: list[str] = []
            if uses_items and isinstance(iterable, dict):
                pairs = list(iterable.items())
                for key, value in pairs:
                    chosen = (key, value)[position] if len(target_names) > 1 else key
                    if isinstance(chosen, str):
                        names.append(chosen)
            elif isinstance(iterable, dict):
                names.extend(k for k in iterable if isinstance(k, str))
            else:
                for item in iterable:
                    if isinstance(item, str) and position == 0 and len(target_names) == 1:
                        names.append(item)
                    elif isinstance(item, (tuple, list)) and position < len(item):
                        candidate = item[position]
                        if isinstance(candidate, str):
                            names.append(candidate)

            is_write = any(marker in body_text for marker in _WRITE_MARKERS)
            for name in names:
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", name):
                    continue
                prior_read, prior_write = resolved.get((prefix, name), (False, False))
                resolved[(prefix, name)] = (True, prior_write or is_write)

    return resolved


# ---------------------------------------------------------------------------
# 3c) 태그가 함수 인자로 전달되는 관용구 (예: ``self._note_shape("footNotePr")``
#     → ``_note_pr_element(self, tag): ET.SubElement(self.element,
#     f"{_HP}{tag}", {})`` — 리터럴과 실제 쓰기가 서로 다른 함수에 있다)
# ---------------------------------------------------------------------------
#
# 2026-08-04 감사 실증(§3-C2): ``hh:ratio``/``hh:spacing``이 frozen으로
# 잘못 집계된 근본 원인이자, ``hp:footNotePr``/``endNotePr``의 write=api
# 판정이 "우연히 독스트링이 태그를 언급한 덕"이었던(맞는 값, 틀린 근거)
# 자리 — 코멘트를 지운 뒤에는 이 두 요소가 실제로는 뒤집힌다. 콜그래프
# 전체를 해석하는 대신, 이 코드베이스에 실제로 나타나는 두 가지 얕은
# 관용구만 좇는다: (a) 함수 파라미터가 자기 본문에서 ``f"{_HP}{param}"``
# 형태로 태그 조립에 직접 쓰이는 자리, (b) 그 파라미터가 리터럴 문자열
# 없이 다른 함수(주로 ``self.<메서드>``)에 그대로 전달되는 자리 — 이
# 전달은 유한 라운드(≤6)로 고정점까지 전파한 뒤, 마지막에 실제 리터럴
# 인자가 있는 모든 호출부에서 해석한다. 태그가 완전히 동적으로 조립되는
# 자리(``oxml/body.py``의 변경추적 마크 — dict 값 문자열을 런타임에
# 이어붙임)는 이 메커니즘으로 못 잡는다 — 그런 자리는 아래
# ``_MANUAL_CODE_USAGE_OVERRIDES``의 근거-필수 화이트리스트로 다룬다.

_ARG_TAG_RE = re.compile(r"_?(HP|HH|HC|HS|HHS|HM|HV)(?:10)?\}\{(\w+)\}([A-Za-z]*)")
_SAFE_ELEMENT_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")
_ARG_TAG_PROPAGATION_ROUNDS = 6


@dataclass
class _ArgTagFunc:
    qualname: str
    class_name: str | None
    node: ast.AST
    params: list[str]


def _collect_arg_tag_functions(tree: ast.AST) -> dict[str, _ArgTagFunc]:
    """모듈 안의 함수/메서드를 ``Class.method`` 정규명으로 인덱싱한다.

    중첩 함수(클로저)는 재귀하지 않는다 — 이 관용구가 실제로 나타나는
    세 파일(document_parts.py/paragraph.py/section_format.py)에는 없고,
    없는 것을 일반화하면 오탐 표면만 넓어진다."""

    functions: dict[str, _ArgTagFunc] = {}

    def visit(node: ast.AST, class_stack: list[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, class_stack + [child.name])
                continue
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                class_name = class_stack[-1] if class_stack else None
                qualname = f"{class_name}.{child.name}" if class_name else child.name
                params = [a.arg for a in child.args.args if a.arg not in ("self", "cls")]
                params += [a.arg for a in child.args.kwonlyargs]
                functions[qualname] = _ArgTagFunc(qualname, class_name, child, params)
                continue
            visit(child, class_stack)

    visit(tree, [])
    return functions


def _direct_arg_tag_specs(
    func: _ArgTagFunc, module_text: str
) -> dict[str, set[tuple[str, str, bool]]]:
    """함수 자기 본문에서 ``f"{_HP}{param}<suffix>"`` 형태로 파라미터가
    태그 조립에 쓰이는 자리를 찾아 (접두, 접미사, is_write) 집합을
    파라미터별로 모은다."""

    body_text = ast.get_source_segment(module_text, func.node) or ""
    specs: dict[str, set[tuple[str, str, bool]]] = {}
    for match in _ARG_TAG_RE.finditer(body_text):
        const, var, suffix = match.group(1), match.group(2), match.group(3)
        if var not in func.params:
            continue
        prefix = _CONST_TO_PREFIX[const]
        window = body_text[max(0, match.start() - _WINDOW_BACK) : match.end() + _WINDOW_FORWARD]
        is_write = any(marker in window for marker in _WRITE_MARKERS)
        specs.setdefault(var, set()).add((prefix, suffix, is_write))
    return specs


def _call_callee_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None


def _resolve_callee_qualname(
    callee_name: str, current_class: str | None, functions: dict[str, _ArgTagFunc]
) -> str | None:
    if current_class is not None:
        scoped = f"{current_class}.{callee_name}"
        if scoped in functions:
            return scoped
    if callee_name in functions:
        return callee_name
    return None


def _build_arg_tag_forwarding_edges(
    functions: dict[str, _ArgTagFunc],
) -> list[tuple[str, str, str, str]]:
    """``def f(self, tag): ... self.g(tag) ...``처럼 자기 파라미터를 리터럴
    없이 다른(이미 알려진) 함수에 그대로 넘기는 자리를 엣지로 모은다."""

    edges: list[tuple[str, str, str, str]] = []
    for qualname, func in functions.items():
        for node in ast.walk(func.node):
            if not isinstance(node, ast.Call):
                continue
            callee_name = _call_callee_name(node)
            if callee_name is None:
                continue
            target_qualname = _resolve_callee_qualname(callee_name, func.class_name, functions)
            if target_qualname is None or target_qualname == qualname:
                continue
            target_params = functions[target_qualname].params
            for index, arg in enumerate(node.args):
                if index >= len(target_params):
                    break
                if isinstance(arg, ast.Name) and arg.id in func.params:
                    edges.append((qualname, arg.id, target_qualname, target_params[index]))
            for kw in node.keywords:
                if (
                    kw.arg is not None
                    and kw.arg in target_params
                    and isinstance(kw.value, ast.Name)
                    and kw.value.id in func.params
                ):
                    edges.append((qualname, kw.value.id, target_qualname, kw.arg))
    return edges


def _propagate_arg_tag_specs(
    functions: dict[str, _ArgTagFunc], module_text: str
) -> dict[str, dict[str, set[tuple[str, str, bool]]]]:
    specs: dict[str, dict[str, set[tuple[str, str, bool]]]] = {
        qualname: _direct_arg_tag_specs(func, module_text) for qualname, func in functions.items()
    }
    edges = _build_arg_tag_forwarding_edges(functions)
    for _round in range(_ARG_TAG_PROPAGATION_ROUNDS):
        changed = False
        for src_q, src_param, dst_q, dst_param in edges:
            dst_specs = specs.get(dst_q, {}).get(dst_param)
            if not dst_specs:
                continue
            bucket = specs.setdefault(src_q, {}).setdefault(src_param, set())
            before = len(bucket)
            bucket |= dst_specs
            if len(bucket) != before:
                changed = True
        if not changed:
            break
    return specs


def _apply_arg_tag_literal(
    spec_set: set[tuple[str, str, bool]] | None,
    arg_node: ast.expr,
    resolved: dict[tuple[str, str], tuple[bool, bool]],
) -> None:
    if not spec_set:
        return
    if not (isinstance(arg_node, ast.Constant) and isinstance(arg_node.value, str)):
        return
    literal = arg_node.value
    if not _SAFE_ELEMENT_NAME_RE.fullmatch(literal):
        return
    for prefix, suffix, is_write in spec_set:
        name = literal + suffix
        if not _SAFE_ELEMENT_NAME_RE.fullmatch(name):
            continue
        prior_read, prior_write = resolved.get((prefix, name), (False, False))
        resolved[(prefix, name)] = (True, prior_write or is_write)


def _resolve_argument_tag_literals(
    files: list[tuple[Path, str]],
) -> dict[tuple[str, str], tuple[bool, bool]]:
    """전 소스를 훑어 "태그를 함수 인자로 전달"하는 자리를 (접두, 이름)→
    (read, write)로 해석한다. 단일 파일 안에서만 동작한다(모듈 간 호출은
    쫓지 않는다 — 대상 세 파일 모두 자기 클래스 안에서만 전달한다)."""

    resolved: dict[tuple[str, str], tuple[bool, bool]] = {}
    for _path, text in files:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        functions = _collect_arg_tag_functions(tree)
        if not functions:
            continue
        specs = _propagate_arg_tag_specs(functions, text)

        def visit(node: ast.AST, class_stack: list[str]) -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.ClassDef):
                    visit(child, class_stack + [child.name])
                    continue
                if isinstance(child, ast.Call):
                    callee_name = _call_callee_name(child)
                    if callee_name is not None:
                        current_class = class_stack[-1] if class_stack else None
                        qualname = _resolve_callee_qualname(callee_name, current_class, functions)
                        if qualname is not None:
                            params = functions[qualname].params
                            callee_specs = specs.get(qualname, {})
                            for index, arg in enumerate(child.args):
                                if index >= len(params):
                                    break
                                _apply_arg_tag_literal(callee_specs.get(params[index]), arg, resolved)
                            for kw in child.keywords:
                                if kw.arg is not None and kw.arg in params:
                                    _apply_arg_tag_literal(callee_specs.get(kw.arg), kw.value, resolved)
                visit(child, class_stack)

        visit(tree, [])

    return resolved


# ---------------------------------------------------------------------------
# 3d) 명시 화이트리스트 — 콜그래프로도 못 쫓는, 완전히 동적으로 조립되는
#     태그(runtime dict 값 문자열 연결 등). 근거 없는 항목은 생성기가 거부.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ManualCodeUsageOverride:
    prefix: str
    name: str
    code_read: bool
    code_write: bool
    evidence: str


_EVIDENCE_LOCATION_RE = re.compile(r"\.py:\d")


def _validate_manual_overrides(overrides: tuple[ManualCodeUsageOverride, ...]) -> None:
    for override in overrides:
        if not override.evidence.strip():
            raise ValueError(
                f"manual override for {override.prefix}:{override.name} has empty evidence"
            )
        if not _EVIDENCE_LOCATION_RE.search(override.evidence):
            raise ValueError(
                f"manual override for {override.prefix}:{override.name} evidence must cite a "
                f"file:line — got {override.evidence!r}"
            )


_MANUAL_CODE_USAGE_OVERRIDES: tuple[ManualCodeUsageOverride, ...] = (
    ManualCodeUsageOverride(
        "hp",
        "insertBegin",
        code_read=True,
        code_write=True,
        evidence=(
            "src/hwpx/oxml/body.py:46-49 _TRACK_CHANGE_TYPES + body.py:291-312 "
            "create_track_change_mark assembles the tag as "
            "f'{normalized}{\"Begin\" if is_begin else \"End\"}' — a runtime "
            "dict-value string concatenation with no literal substring anywhere "
            "in source, so no static scanner can find it. body.py:871-881 "
            "_track_change_mark_to_xml emits it via "
            "etree.Element(_qualified_tag(mark.tag, mark.name)). Shipped and "
            "Hancom-COM-verified via add_tracked_insert/delete/replace "
            "(2026-06-30, the tracked-change/redline train)."
        ),
    ),
    ManualCodeUsageOverride(
        "hp",
        "insertEnd",
        code_read=True,
        code_write=True,
        evidence=(
            "Same mechanism as hp:insertBegin — src/hwpx/oxml/body.py:46-49, "
            "291-312, 871-881."
        ),
    ),
    ManualCodeUsageOverride(
        "hp",
        "deleteBegin",
        code_read=True,
        code_write=True,
        evidence=(
            "Same mechanism as hp:insertBegin — src/hwpx/oxml/body.py:46-49, "
            "291-312, 871-881."
        ),
    ),
    ManualCodeUsageOverride(
        "hp",
        "deleteEnd",
        code_read=True,
        code_write=True,
        evidence=(
            "Same mechanism as hp:insertBegin — src/hwpx/oxml/body.py:46-49, "
            "291-312, 871-881. body.py:366-378 additionally reads mark.name == "
            "'deleteEnd' by attribute comparison, not tag literal, in "
            "_reorder_replace_marks."
        ),
    ),
    ManualCodeUsageOverride(
        "hp",
        "markpenBegin",
        code_read=True,
        code_write=True,
        evidence=(
            "src/hwpx/oxml/body.py:481 create_highlight_mark assembles the tag "
            "as name = 'markpenBegin' if is_begin else 'markpenEnd' — a literal "
            "substring, but with no hp:/{_HP} namespace marker adjacent in "
            "source, so the prefix-anchored patterns cannot find it (same blind "
            "spot as hp:insertBegin above, different cause: there it is dynamic "
            "concatenation, here it is a namespace-free literal). body.py:485 "
            "returns GenericElement(name=name, tag=_qualified_tag(None, name), "
            "...); body.py:818-826 _generic_element_to_xml emits it via "
            "etree.Element(_qualified_tag(element.tag, element.name)) — again a "
            "generic parameter, not a literal 'markpenBegin' token. "
            "wrap_highlight_in_span (body.py:488-532) splices the begin/end "
            "pair into TextSpan.marks; oxml/paragraph.py:249-274 add_highlight "
            "is the paragraph-level call site reached from doc.text.highlight. "
            "Shipped and real-corpus-verified via "
            "tests/test_highlight_authoring.py "
            "test_real_corpus_new_highlight_coexists_with_the_original_malformed_pair "
            "(2026-08 cycle-6.2 highlight authoring)."
        ),
    ),
    ManualCodeUsageOverride(
        "hp",
        "markpenEnd",
        code_read=True,
        code_write=True,
        evidence=(
            "Same mechanism as hp:markpenBegin — src/hwpx/oxml/body.py:470-532, "
            "818-826, oxml/paragraph.py:249-274."
        ),
    ),
    ManualCodeUsageOverride(
        "hhs",
        "insert",
        code_read=True,
        code_write=False,
        evidence=(
            "src/hwpx/oxml/history_part.py:103-112 _parse_diff_op is a generic "
            "recursive descent: name = local_name(node) (line 104) is stored "
            "directly as DiffNode.op with no '==' / 'in' comparison anywhere in "
            "the function, so neither the prefix-anchored literal patterns nor "
            "the bare-name dispatch-window detector can find it — there is no "
            "comparison site to anchor on, and no fixed set of literal tag "
            "strings. _parse_diff_entry (history_part.py:92-100) feeds this "
            "function whatever the first child of a packageDiff/headDiff/"
            "bodyDiff/tailDiff element is, and _parse_diff_op recurses into its "
            "own children (line 108) the same way, so it genuinely parses "
            "'insert' when that is the tag it is handed — not a hypothetical. "
            "Wired to the reader: simple_parts.py:85-87 "
            "HwpxOxmlHistory.to_model -> parse_history, reached from "
            "doc.parts.histories. Exercised end-to-end (not just theoretically "
            "reachable) by "
            "tests/test_part_hierarchy_read_models.py:179 "
            "test_parse_history_handles_a_schema_shaped_synthetic_fixture, "
            "which asserts DiffNode(op='insert', ...) on parsed output. No "
            "writer exists anywhere in src/hwpx for hhs:insert "
            "(grep-confirmed), so code_write stays False."
        ),
    ),
    ManualCodeUsageOverride(
        "hhs",
        "update",
        code_read=True,
        code_write=False,
        evidence="Same mechanism as hhs:insert — src/hwpx/oxml/history_part.py:103-112.",
    ),
    ManualCodeUsageOverride(
        "hhs",
        "delete",
        code_read=True,
        code_write=False,
        evidence="Same mechanism as hhs:insert — src/hwpx/oxml/history_part.py:103-112.",
    ),
    ManualCodeUsageOverride(
        "hhs",
        "position",
        code_read=True,
        code_write=False,
        evidence="Same mechanism as hhs:insert — src/hwpx/oxml/history_part.py:103-112.",
    ),
    ManualCodeUsageOverride(
        "hh",
        "trackChange",
        code_read=True,
        code_write=True,
        evidence=(
            "src/hwpx/oxml/header.py:1599-1610 track_change_to_xml emits "
            "etree.Element(\"{http://www.hancom.co.kr/hwpml/2011/head}"
            "trackChange\", attributes) — a full Clark-notation namespace URI "
            "spelled out as a literal string, not the codebase's usual "
            "{_HH}trackChange f-string alias, so pattern 3 "
            "(_?HH(?:10)?\\}name) never matches: the characters immediately "
            "before '}' are 'head', not 'HH'. (codeRead was already correctly "
            "True via the direct-getter dispatch window — header.py:1469 "
            "`if local_name(child) == \"trackChange\"` matches "
            "_DIRECT_GETTER_RE; only codeWrite was the false negative.) "
            "Genuinely wired end to end, not dead code: header_part.py:870-893 "
            "HwpxOxmlHeader.add_track_change calls track_change_to_xml and "
            "appends the result; reached from "
            "src/hwpx/_document/ns/tracking.py:114-127 "
            "TrackingNamespace.add_change (doc.tracked.add_change), the "
            "primitive behind add_tracked_insert/delete/replace — shipped and "
            "Hancom-COM-verified 2026-06-30 (commit 2026-06-30 "
            "'feat(m4-p1): redline authoring primitives (insert/delete/"
            "replace)', predates this cycle)."
        ),
    ),
    ManualCodeUsageOverride(
        "hh",
        "trackChangeAuthor",
        code_read=True,
        code_write=True,
        evidence=(
            "Same mechanism as hh:trackChange — "
            "src/hwpx/oxml/header.py:1613-1629 track_change_author_to_xml "
            "emits the same full-URI Clark-notation literal for "
            "trackChangeAuthor. Wired via header_part.py:894-914 (the same "
            "add_track_change call registers the author entry the first time "
            "that author id appears)."
        ),
    ),
    ManualCodeUsageOverride(
        "hp",
        "lineBreak",
        code_read=True,
        code_write=True,
        evidence=(
            "src/hwpx/oxml/_document_primitives.py:425-478 "
            "_RUN_CHOICE_ATOM_MARKERS/_append_text_with_run_choice_atoms "
            "(cycle 6.5 train 19) maps '\\n' -> the bare string literal "
            "'lineBreak' as a dict VALUE, then builds the tag via "
            "_child_tag_like(run, marker_name, _HP_NS) where marker_name is "
            "the variable holding that value — no hp:/{_HP} namespace marker "
            "sits adjacent to the literal itself, so none of the six "
            "prefix-anchored patterns can find it (same blind spot family as "
            "hp:markpenBegin above: the write marker 'makeelement' is near "
            "the call site, not near the literal). Genuinely wired: "
            "paragraph.py's add_run(expand_special_characters=True) calls "
            "it. codeRead was already True independently, via a different "
            "and unrelated site: tools/exporter.py:67 and "
            "tools/layout_preview.py:228 both compare "
            "`child.tag == f\"{_HP}lineBreak\"` (real f-string literal "
            "adjacency, correctly matched by pattern 3) — those predate this "
            "train and read hp:lineBreak for their own export/preview "
            "purposes, unrelated to _append_text_with_run_choice_atoms."
        ),
    ),
    ManualCodeUsageOverride(
        "hp",
        "nbSpace",
        code_read=True,
        code_write=True,
        evidence=(
            "Write: same mechanism as hp:lineBreak above — "
            "_document_primitives.py:425-478, marker_name='nbSpace' as a "
            "dict value with no adjacent namespace marker. Read: already "
            "fixed generically by registering 'strip_namespace' in "
            "_LOCAL_NAME_GETTERS (this file, cycle 6.5 train 19) — no "
            "override needed for the read half, kept here only because "
            "ManualCodeUsageOverride sets both flags together and the write "
            "half must be True."
        ),
    ),
    ManualCodeUsageOverride(
        "hp",
        "fwSpace",
        code_read=True,
        code_write=True,
        evidence=(
            "Same mechanism as hp:nbSpace directly above (write: "
            "_document_primitives.py:425-478 dict-value tag; read: fixed "
            "generically via the strip_namespace getter registration)."
        ),
    ),
    # 6.10 트레인㉟ — v13 환류 도중 발견: dutmal/compose 저작(cycle 6.9
    # 트레인㉞)이 write=api로 안 잡혀 authored-dutmal-compose의 실한컴
    # 수용 영수증(report-v13.json, 30/30)이 요소 축에 반영될 길이 없었다
    # (write_mode != "api"면 corpus_accepted를 강제로 False로 되돌리는
    # 방어 로직, 이 파일 위쪽 주석 참조). 원인: body.py의
    # _composed_character_to_xml/_dutmal_to_xml가 `_qualified_tag(tag,
    # "compose")` 처럼 이름 없는 문자열 리터럴을 헬퍼 함수에 넘기는
    # 관용구를 쓴다 — 태그가 호출부에 인접한 리터럴이 아니라 헬퍼가
    # 내부적으로 네임스페이스를 붙이므로 6개 정규식 어느 것도 안 걸린다.
    # mainText/subText는 `f"{_DEFAULT_HP}mainText"`(body.py 자신의
    # `_DEFAULT_HP` 별칭 — 패턴3이 찾는 `_HP`/`HP`와 이름이 달라 경계
    # 매칭이 실패)로 또 다른 이유로 안 걸린다. read는 이미 별도 경로로
    # True(`_bare_name_dispatched`가 parse_preserved_element의
    # `if name == "compose":` 식 맨이름 디스패치를 잡는다).
    ManualCodeUsageOverride(
        "hp",
        "compose",
        code_read=True,
        code_write=True,
        evidence=(
            "Write: src/hwpx/oxml/body.py:1225 "
            "_qualified_tag(composed.tag, \"compose\") -- a helper call, "
            "not a literal adjacent to the call site. Genuinely wired: "
            "paragraph.py's add_composed_character (via "
            "oxml/dutmal_compose.py) calls it. Real-Hancom accepted "
            "(docs/openrate/report-v13.json, authored-dutmal-compose "
            "10/10)."
        ),
    ),
    ManualCodeUsageOverride(
        "hp",
        "dutmal",
        code_read=True,
        code_write=True,
        evidence=(
            "Write: src/hwpx/oxml/body.py:1238 "
            "_qualified_tag(dutmal.tag, \"dutmal\") -- same helper-call "
            "shape as hp:compose above. Genuinely wired: paragraph.py's "
            "add_dutmal (via oxml/dutmal_compose.py) calls it. "
            "Real-Hancom accepted (docs/openrate/report-v13.json, "
            "authored-dutmal-compose 10/10)."
        ),
    ),
    ManualCodeUsageOverride(
        "hp",
        "mainText",
        code_read=True,
        code_write=True,
        evidence=(
            "Write: src/hwpx/oxml/body.py:1239 "
            "etree.SubElement(node, f\"{_DEFAULT_HP}mainText\") -- "
            "body.py's own _DEFAULT_HP alias, not the _HP/HP name pattern 3 "
            "looks for, so no adjacency match. Genuinely wired: "
            "add_dutmal's only mainText writer. Real-Hancom accepted "
            "(docs/openrate/report-v13.json, authored-dutmal-compose "
            "10/10)."
        ),
    ),
    ManualCodeUsageOverride(
        "hp",
        "subText",
        code_read=True,
        code_write=True,
        evidence=(
            "Write: src/hwpx/oxml/body.py:1241 "
            "etree.SubElement(node, f\"{_DEFAULT_HP}subText\") -- same "
            "_DEFAULT_HP-alias gap as hp:mainText above. Real-Hancom "
            "accepted (docs/openrate/report-v13.json, "
            "authored-dutmal-compose 10/10)."
        ),
    ),
)

_validate_manual_overrides(_MANUAL_CODE_USAGE_OVERRIDES)
MANUAL_CODE_USAGE_OVERRIDES_BY_KEY: dict[tuple[str, str], ManualCodeUsageOverride] = {
    (override.prefix, override.name): override for override in _MANUAL_CODE_USAGE_OVERRIDES
}


def _build_element_patterns(prefix: str, name: str, family: str) -> list[re.Pattern[str]]:
    const = re.escape(prefix.upper())
    esc_name = re.escape(name)
    esc_prefix = re.escape(prefix)
    esc_family = re.escape(family)
    boundary = r"(?<![A-Za-z0-9_])"
    return [
        # 여는 태그 리터럴: <hp:tbl  (XML 템플릿·Skeleton 바이트열)
        re.compile(rf"<{esc_prefix}:{esc_name}(?=[\s/>])"),
        # 맨 태그 리터럴(따옴표 안 등, '<' 없이): "hp:tbl"
        re.compile(rf'(?<!<){esc_prefix}:{esc_name}(?=[\s/>"\'])'),
        # f-string/속성 조립: {_HP}tbl 또는 {HP}tbl
        re.compile(rf"{boundary}_?{const}(?:10)?\}}{esc_name}\b"),
        # 연결 조립: _HP + \"tbl\" / HP_NS + \"tbl\"
        re.compile(rf'{boundary}_?{const}(?:_NS)?\s*\+\s*["\']{esc_name}["\']'),
        # qn(\"paragraph\", \"tbl\") / element_qn_like(x, \"paragraph\", \"tbl\")
        re.compile(rf'["\']{esc_family}["\']\s*,\s*["\']{esc_name}["\']'),
        # _child_tag_like(parent, \"tbl\", _HP_NS)
        re.compile(rf'["\']{esc_name}["\']\s*,\s*{boundary}_?{const}_NS\b'),
    ]


def classify_code_usage(
    prefix: str,
    name: str,
    family: str,
    source_text: str,
    dispatch_windows: list[str],
    indirect_resolved: dict[tuple[str, str], tuple[bool, bool]],
) -> tuple[bool, bool]:
    """(codeRead, codeWriteApi)를 돌려준다.

    ``indirect_resolved``는 평문 패턴 매칭으로 못 잡는 두 부류를 병합한
    (읽기, 쓰기) 사실 테이블이다 — 루프 변수 태그 조립
    (``_resolve_loop_tag_tables``)과 함수-인자 태그 전달
    (``_resolve_argument_tag_literals``). 둘 다 ``ast`` 기반이라 스트립되지
    않은 원본 텍스트에서 계산된다."""

    code_read = False
    code_write = False
    for pattern in _build_element_patterns(prefix, name, family):
        for match in pattern.finditer(source_text):
            is_open_tag_literal = source_text[match.start()] == "<" or (
                match.start() > 0 and source_text[match.start() - 1] == "<"
            )
            window = source_text[
                max(0, match.start() - _WINDOW_BACK) : match.end() + _WINDOW_FORWARD
            ]
            if is_open_tag_literal or any(marker in window for marker in _WRITE_MARKERS):
                code_write = True
            else:
                code_read = True
    if not code_read and _bare_name_dispatched(name, dispatch_windows):
        # 접두 없는 local_name() 디스패치(예: header.py의
        # `name = local_name(child); if name == "docOption":`) — 네임스페이스
        # 마커가 근방에 없어 위 한정 패턴으로는 못 잡히지만 엄연한 읽기다.
        code_read = True
    indirect_read, indirect_write = indirect_resolved.get((prefix, name), (False, False))
    code_read = code_read or indirect_read
    code_write = code_write or indirect_write
    override = MANUAL_CODE_USAGE_OVERRIDES_BY_KEY.get((prefix, name))
    if override is not None:
        code_read = code_read or override.code_read
        code_write = code_write or override.code_write
    # 쓰기 신호는 코드가 요소를 "알고 있다"는 것도 함께 증명한다.
    if code_write:
        code_read = True
    return code_read, code_write


def _read_skeleton_text() -> str:
    """Skeleton.hwpx의 모든 XML part를 하나의 텍스트로 합친다."""

    with zipfile.ZipFile(SKELETON_PATH) as archive:
        parts = []
        for info in sorted(archive.infolist(), key=lambda item: item.filename):
            if info.filename.endswith((".xml", ".hpf", ".rdf")):
                parts.append(archive.read(info.filename).decode("utf-8", errors="ignore"))
        return "\n\n".join(parts)


def is_in_skeleton(prefix: str, name: str, skeleton_text: str) -> bool:
    pattern = re.compile(rf"<{re.escape(prefix)}:{re.escape(name)}(?=[\s/>])")
    return pattern.search(skeleton_text) is not None


# ---------------------------------------------------------------------------
# 4) 능력 영역 매핑 (support-matrix.md)
# ---------------------------------------------------------------------------

#: (접두, 요소) → support-matrix.md의 "능력 영역" 행 라벨. 매트릭스 산문에
#: 실제 언급된 태그·헬퍼(예: "hp:formCharPr", "add_line", "add_tracked_*")만
#: 근거로 삼는다 — 애매하게 여러 행에 걸치는 저수준 공용 요소(fieldBegin류
#: 하이퍼링크/누름틀/TOC 공유, autoNum류 각주/쪽번호 공유, pt0류 도형 좌표
#: 공유)는 무근거 승격을 피하기 위해 일부러 비워 둔다.
CAPABILITY_KEYWORDS: dict[tuple[str, str], str] = {}


def _register(area: str, prefix: str, *names: str) -> None:
    for name in names:
        CAPABILITY_KEYWORDS[(prefix, name)] = area


_register(
    "문단·표 저작/편집",
    "hp",
    "p", "run", "t", "lineBreak", "tab", "nbSpace", "fwSpace", "secPr",
    "tbl", "tr", "tc", "cellAddr", "cellSpan", "cellSz", "cellMargin",
    "cellzone", "cellzoneList", "lineseg", "linesegarray",
)
_register("문단·표 저작/편집", "hh", "paraPr", "charPr", "paraProperties", "charProperties")
_register(
    "도형 저작(선·사각형·타원)",
    "hp",
    "line", "rect", "ellipse", "lineShape", "offset", "orgSz", "curSz", "sz", "pos",
)
_register("arc·polygon·curve·connectLine", "hp", "arc", "polygon", "curve", "connectLine", "seg")
_register("그룹 개체(컨테이너)", "hp", "container")
_register(
    "그림 삽입/치환", "hp", "pic", "imgRect", "imgDim", "imgClip", "effects",
)
_register("그림 삽입/치환", "hc", "img")
_register("테두리 채우기(이미지·그라데이션)", "hc", "imgBrush", "gradation", "color")
_register("차트", "hp", "chart")
_register("수식", "hp", "equation", "script")
_register(
    "변경추적(redline)",
    "hp",
    "insertBegin", "insertEnd", "deleteBegin", "deleteEnd",
)
_register(
    "변경추적(redline)",
    "hh",
    "trackChange", "trackChanges", "trackChangeAuthors", "trackChangeAuthor",
    "trackchangeConfig", "trackchageConfig",
)
_register("메모(코멘트)", "hp", "memo", "memogroup")
_register("메모(코멘트)", "hh", "memoPr", "memoProperties")
_register(
    "각주/미주", "hp", "footNote", "endNote", "footNotePr", "endNotePr", "noteLine", "noteSpacing",
)
_register("체크박스 양식개체", "hp", "checkBtn", "formCharPr", "radioBtn", "btn")
_register("형광펜(하이라이트)", "hp", "markpenBegin", "markpenEnd")
_register(
    "문서 옵션·호환성", "hh",
    "compatibleDocument", "layoutCompatibility", "docOption", "linkinfo", "autoSpacing",
)
# 6.8 트레인㉚ — 편집기 표면 인벤토리(트레인㉙)가 등재. "페이지 레이아웃"은
# doc.page의 19개 메서드를 아우르는 넓은 매트릭스 행이지만, 여기 등록하는
# 건 실한컴 증거가 실제로 있는 5개 요소뿐이다(v4 authored-page-structure·
# v6 authored-pagecontrol) — 나머지(여백·용지크기·머리말/꼬리말·쪽번호
# 서식·단)의 요소는 일부러 등록하지 않는다(무근거 승격 금지, 위 v8
# polygon/arc 주석과 같은 원칙 — 매트릭스 행의 상태 문자열 자체에
# "Render-verified"가 있어도 CAPABILITY_KEYWORDS에 없는 요소는 이 등록의
# 영향을 안 받는다).
_register("페이지 레이아웃(용지·여백·머리말/꼬리말·쪽번호·단·줄번호·격자·요소 숨김)", "hp", "visibility", "lineNumberShape", "grid", "newNum", "pageHiding")
# 6.9 트레인㉜ — v12(authored-pagelayout)가 이전엔 미실측이던 doc.page의
# 나머지 표면을 실측했다. 여기 추가하는 6종은 각각 하나의 setter와 1:1로
# 대응하고(set_size→pagePr, set_margins→margin, set_header/footer→header/
# footer, set_columns→colPr, set_page_number→pageNum) 다른 어떤 능력
# 영역도 이 이름들을 안 쓴다(직접 확인) — hp:autoNum은 의도적으로 뺐다:
# paragraph.py의 add_new_num(각주/목록류 자동번호)도 같은 이름을 쓰는
# 공유 요소라 fieldBegin류와 같은 무근거 승격 위험이 있다(실제 표시
# 요소인 hp:pageNum은 이미 커버하므로 사용자 가시 결과는 검증됨).
_register(
    "페이지 레이아웃(용지·여백·머리말/꼬리말·쪽번호·단·줄번호·격자·요소 숨김)", "hp",
    "pagePr", "margin", "header", "footer", "colPr", "pageNum",
)
# "글꼴 등록"은 authored-fontface(v5)가 정확히 겨냥하는 4개 요소와 1:1이라
# 무근거 승격 위험이 없다 — 이전엔 대응 capabilityArea가 없어서
# _OPENRATE_STRATUM_TO_ELEMENTS로 요소 직접 지목했으나(v5 주석 참조), 이제
# 정식 영역이 생겨 _OPENRATE_STRATUM_TO_CAPABILITY_AREA로 옮긴다(아래).
_register("글꼴 등록", "hh", "font", "fontface", "fontfaces", "substFont")
# 6.9 트레인㉜ — hp:bookmark는 hyperlink-bookmark 영역과 1:1이다(다른
# 어떤 코드 경로도 이 이름을 안 쓴다, 직접 확인). hp:fieldBegin(하이퍼링크
# 자신이 쓰는 컨트롤)은 CLICKHERE/TOC/CROSSREF/하이퍼링크가 공유하는
# 저수준 요소라 여기서도 여전히 등록하지 않는다 — 위 CAPABILITY_KEYWORDS
# 상단 주석의 fieldBegin 원칙과 동일.
_register("하이퍼링크·책갈피", "hp", "bookmark")
# 6.9 트레인㉞ — hp:compose/hp:dutmal은 이 영역과 1:1이다(다른 어떤 코드
# 경로도 이 이름들을 안 쓴다, 직접 확인). hp:dutmal의 mainText/subText는
# dutmal 전용 자식이라 같이 등록하지만, hp:compose 안의 hp:charPr(슬롯
# 서식 참조)는 "문단·표 저작/편집" 영역이 이미 소유한 공유 요소라 여기서
# 등록하지 않는다(fieldBegin류와 같은 무근거 승격 회피 원칙).
_register("덧말·글자 겹치기", "hp", "compose", "dutmal", "mainText", "subText")
# 6.11 트레인㊳ — v14. "목록 서식(글머리표·번호매기기)"은 새로 등록하는
# 영역이다(이전엔 대응 capabilityArea 자체가 없어 인벤토리 행이 계속
# 미실측으로 남아 있었다). hh:bullet/numbering(과 그 컨테이너·자식)은
# 다른 어떤 능력 영역도 안 쓰는 요소다(직접 확인, CAPABILITY_KEYWORDS
# 전수 grep) — doc.styles.ensure_numbering/apply_list_format이 실제로
# 만드는 요소와 1:1이라 무근거 승격 위험이 없다. hh:heading(paraPr
# 안에서 numbering/bullet을 가리키는 polymorphic idRef)은 일부러 뺐다 —
# document_merge.py의 _remap_headings 등 다른 경로도 이 이름을 건드리는
# 공유 요소라 fieldBegin류와 같은 무근거 승격 회피 원칙을 따른다.
_register(
    "목록 서식(글머리표·번호매기기)", "hh",
    "bullet", "bullets", "numbering", "numberings", "paraHead",
)
# 6.12 트레인㊸ — "문단 첫 글자 장식(드롭캡)"은 의도적으로 요소 등록이
# 없다. dropcapstyle은 hp:rect의 속성일 뿐 새 요소 이름이 아니고, hp:rect
# 자체는 이미 위에서 "도형 저작(선·사각형·타원)"에 등록돼 있다 —
# _register는 (prefix, name) 키 하나에 영역 하나만 담으므로, 여기서
# "rect"를 다시 등록하면 fieldBegin류의 "공유 요소" 문제가 아니라 아예
# 기존 등록을 덮어써 도형 저작 카운트를 조용히 망가뜨린다. 드롭캡 실증은
# support-matrix.md 산문으로만 남긴다(무근거 승격 회피 원칙).
#
# 6.12 트레인㊸ 갭③ — "페이지 레이아웃" 행에 추가한 text_direction/
# set_text_direction(hp:secPr의 textDirection/textVerticalWidthHead)도
# 같은 이유로 요소 등록이 없다. 이 둘은 hp:secPr 자신의 *속성*이고,
# hp:secPr 자체는 이 파일이 이미 등록한 11개 자식 요소(pagePr/margin/
# header/footer/colPr/pageNum/visibility/lineNumberShape/grid/newNum/
# pageHiding)를 담는 컨테이너 — 세로쓰기를 한 번도 안 쓴 문서를 포함해
# **모든** 문서가 hp:secPr을 가지므로, secPr 자체를 등록하면 전량 위양성이
# 된다(위 6.8 트레인㉚ 주석의 "부분만 등록" 원칙보다 더 명백한 사례).


def _parse_support_matrix_status(text: str) -> dict[str, str]:
    """"## 매트릭스" 표에서 능력 영역 → 상태(등급) 문자열을 뽑는다."""

    marker = "## 매트릭스"
    start = text.index(marker)
    end = text.index("\n## ", start + len(marker))
    section = text[start:end]

    status_by_area: dict[str, str] = {}
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.startswith("|---"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2 or cells[0] == "능력 영역":
            continue
        status_by_area[cells[0]] = cells[1]
    return status_by_area


def classify_capability(
    prefix: str, name: str, status_by_area: dict[str, str]
) -> tuple[str | None, str | None, str | None]:
    area = CAPABILITY_KEYWORDS.get((prefix, name))
    if area is None:
        return None, None, None
    status = status_by_area.get(area)
    basis = "by-capability-area" if status and "Render-verified" in status else None
    return area, status, basis


# ---------------------------------------------------------------------------
# 4b) openrate 코퍼스 환류(v4~v16) — support-matrix 산문과 별개인 두 번째
#     실측 근거. 감사 R4: "v4 스트라타의 요소별 실한컴 수용이 원장의
#     verificationBasis로 환류되지 않아 두 산출물이 서로를 모른다." (2026-08
#     사이클 6.5 트레인⑰이 이 배선을 v5~v8까지 확장, 사이클 6.6 트레인⑳이
#     v9까지, 사이클 6.7 트레인㉔이 v10까지, 사이클 6.8 트레인㉘이 v11까지,
#     사이클 6.9 트레인㉜이 v12까지, 사이클 6.10 트레인㉟이 v13까지 확장했다.)
# ---------------------------------------------------------------------------

#: openrate 스트라타 → capabilityArea. CAPABILITY_KEYWORDS와 같은 원칙(무근거
#: 승격 금지)으로, 기존에 이미 등록된 능력 영역과 스트라타가 1:1로 명확히
#: 대응하는 경우만 싣는다 — 즉 그 요소가 ``CAPABILITY_KEYWORDS``에 실재
#: 등재돼 있는지 먼저 확인하고서만 여기 추가한다. v4의
#: authored-formfield/heading/named-style/page-structure·baseline-regen/
#: edit-plan은 대응하는 단일 capabilityArea가 없어(예: formfield는
#: fieldBegin류처럼 여러 영역이 공유) 의도적으로 뺐다 — CAPABILITY_KEYWORDS가
#: fieldBegin을 일부러 안 매핑한 것과 같은 이유다. v5(글꼴·탭·도형텍스트·
#: 캡션)·v6의 authored-pagecontrol·v7(문자서식·필드파라미터) 스트라타도
#: 같은 이유로 여기 없다 — 대응하는 capabilityArea 자체가 지원 매트릭스에
#: 아직 없다(이번 사이클 신규 능력이라 행이 안 생겼을 뿐). v8의
#: authored-polygon/authored-arc도 여기 없다 — 다른 이유로: 대응 영역
#: "arc·polygon·curve·connectLine"은 **혼합** 지원 영역이라(polygon·arc는
#: 저작되지만 curve·connectLine·seg는 정직 보류 — 지원 매트릭스 자신도
#: "Unsupported-but-preserved(curve·connectLine)"라고 명시), 영역 전체에
#: 수용 신호를 흘리면 curve/connectLine/seg까지 검증된 것처럼 보이는
#: 위양성이 생긴다(구현 중 실제로 한 번 이렇게 배선했다가, write=none인
#: 요소가 verificationBasis를 갖는 모순을 발견하고 되돌렸다). 그래서 이
#: 둘도 ``_OPENRATE_STRATUM_TO_ELEMENTS``로 요소를 개별 지목한다.
_OPENRATE_STRATUM_TO_CAPABILITY_AREA: dict[str, str] = {
    "authored-chart": "차트",
    "authored-checkbox": "체크박스 양식개체",
    "authored-equation": "수식",
    "authored-footnote": "각주/미주",
    "authored-note-shape": "각주/미주",
    # v6(cycle 6.2) — CAPABILITY_KEYWORDS가 이미 이 정확한 요소들을 등록해
    # 뒀다(_register 호출부 확인): "테두리 채우기(이미지·그라데이션)" ←
    # hc:imgBrush/gradation/color, "형광펜(하이라이트)" ←
    # hp:markpenBegin/markpenEnd, "메모(코멘트)" ← hh:memoPr/memoProperties.
    "authored-fill": "테두리 채우기(이미지·그라데이션)",
    "authored-highlight": "형광펜(하이라이트)",
    "authored-memoshape": "메모(코멘트)",
    # v9(cycle 6.6, 트레인⑳) — "그룹 개체(컨테이너)"는 hp:container 단 하나만
    # 등록된 1:1 영역이다(_register 호출부 확인, 위 v8 주석의 혼합-영역
    # 위험이 없다) — authored-container 스트라텀이 add_container로 저작한
    # 것이 정확히 이 요소이므로 영역째 흘려도 안전하다.
    "authored-container": "그룹 개체(컨테이너)",
    # v10(cycle 6.7, 트레인㉔) — "문서 옵션·호환성"은 hh:compatibleDocument/
    # layoutCompatibility/docOption/linkinfo/autoSpacing 5종만 등록된 1:1
    # 영역이다(_register 호출부 확인 — 이 5종 중 어느 것도 다른 영역이
    # 공유하지 않는다, 위 v8 주석의 혼합-영역 위험이 없다). authored-compat
    # 스트라텀이 트레인㉓의 doc.parts.set_* 4종으로 저작한 것이 정확히 이
    # 5종이므로 영역째 흘려도 안전하다.
    "authored-compat": "문서 옵션·호환성",
    # 6.8 트레인㉚ — "페이지 레이아웃"/"글꼴 등록" 영역이 새로 생기면서
    # v4/v5/v6이 예전부터 갖고 있던 관련 receipt를 이제 영역 경로로 옮긴다
    # (이전엔 대응 영역이 없어 요소 직접 지목이었다 — 위 옛 주석·아래
    # _OPENRATE_STRATUM_TO_ELEMENTS의 이력 주석 참조). "페이지 레이아웃"은
    # CAPABILITY_KEYWORDS에 이 두 스트라텀이 겨냥하는 5개 요소만 등록돼
    # 있어(위 _register 호출부) 영역째 흘려도 안전하다 — 나머지 요소(여백·
    # 용지크기 등)는 애초에 이 영역에 등록돼 있지 않으므로 오염 경로가 없다.
    "authored-page-structure": "페이지 레이아웃(용지·여백·머리말/꼬리말·쪽번호·단·줄번호·격자·요소 숨김)",
    "authored-pagecontrol": "페이지 레이아웃(용지·여백·머리말/꼬리말·쪽번호·단·줄번호·격자·요소 숨김)",
    # "글꼴 등록"은 authored-fontface가 겨냥하는 4개 요소와 정확히 1:1이다.
    "authored-fontface": "글꼴 등록",
    # 6.9 트레인㉜ — v12. authored-pagelayout이 위에서 새로 등록한 6종
    # (pagePr/margin/header/footer/colPr/pageNum)을 정확히 겨냥한다 —
    # doc.page의 남은 setter 전부(autoNum만 공유-요소라 의도적 제외).
    # authored-hyperlink-bookmark는 hp:bookmark 하나만 겨냥한다(hp:
    # fieldBegin은 위 CAPABILITY_KEYWORDS 주석대로 여전히 미등록 공유 요소).
    "authored-pagelayout": "페이지 레이아웃(용지·여백·머리말/꼬리말·쪽번호·단·줄번호·격자·요소 숨김)",
    "authored-hyperlink-bookmark": "하이퍼링크·책갈피",
    # 6.10 트레인㉟ — v13. authored-dutmal-compose는 "덧말·글자 겹치기"가
    # 겨냥하는 4개 요소(hp:compose/hp:dutmal/hp:mainText/hp:subText)와
    # 정확히 1:1이다(위 _register 호출부 확인) — 영역째 흘려도 안전하다.
    # authored-docmerge/authored-mailmerge는 **일부러 여기 없다**: "문서
    # 끼워 넣기(문서 병합)"·"메일머지"는 mail-merge·table-navigation-fill·
    # find-replace와 같은 이유로 CAPABILITY_KEYWORDS에 등록된 요소가
    # 0개다(신규 요소를 만드는 게 아니라 기존 요소를 재매핑/치환하는
    # 구조라서) — 여기 추가해도 원장(요소 축)에 붙일 대상이 없어
    # 완전히 무동작이다. 이 두 영역의 등급 갱신은 support-matrix.md
    # 산문에서만 이뤄지고, 근거는 docs/openrate/report-v13.json을 직접
    # 인용한다. 6.11 트레인㊳ — v14의 authored-docmerge2(document_merge.py
    # v2 산출물)도 같은 이유로 같은 취급: document_merge 모듈 전체가
    # capabilityArea 0개인 건 v1이든 v2든 변하지 않는다(등급 갱신은
    # support-matrix.md 산문, 근거는 report-v14.json 직접 인용).
    # authored-tablenavfill/authored-findreplace/authored-editplan도
    # 같은 이유로 여기 없다(기존 요소를 변형만 하는 구조 — 이 셋은
    # 생성기 자신의 독스트링이 이미 이렇게 정직 고지한다). authored-
    # tablestructure는 다르다 — apply_table_ops가 건드리는
    # hp:tbl/tr/tc/cellAddr/cellSpan/cellSz/cellMargin은 전부 실제로
    # 등록돼 있다(위 _register 호출부, "문단·표 저작/편집"). 하지만 그
    # 영역은 v8 polygon/arc 주석이 경고하는 바로 그 대형 혼합 영역이라
    # (p/run/t/secPr/paraPr/charPr 등을 함께 묶음) 여기 추가하면 이
    # 스트라텀이 실제로 검증한 적 없는 이웃 요소(예: hp:secPr, 순수
    # 텍스트 문단)까지 openrate 근거를 얻는 위양성이 생긴다 — 그래서
    # authored-tablestructure도 라우팅하지 않는다(등급 갱신은 산문,
    # 근거는 report-v14.json 직접 인용, 위 다섯과 동일 취급).
    "authored-dutmal-compose": "덧말·글자 겹치기",
    # 6.11 트레인㊳ — v14, 편집기 표면 인벤토리의 미실측 행 소탕. 세 영역
    # 모두 이미 CAPABILITY_KEYWORDS에 등록돼 있던(위 _register 호출부)
    # 1:1 영역이고, 이 사이클 전까지 어느 스트라텀도 겨냥한 적이 없었다.
    # "차트"는 authored-chart로 v4(15건)가 이미 겨냥했으므로 여기 새로
    # 추가하지 않는다 — v14의 authored-chart는 **같은 이름의 스트라텀**이라
    # (다른 stratum이 아니다) receipts 로더가 report-v4/v14 두 파일에서
    # OR로 자동 누적한다(코드 변경 불필요, _load_openrate_capability_
    # receipts의 stratum_name→area 단일 매핑 구조 자체가 그렇게 동작).
    "authored-redline": "변경추적(redline)",
    "authored-picture": "그림 삽입/치환",
    "authored-listformat": "목록 서식(글머리표·번호매기기)",
}

#: capabilityArea가 아직 없거나(v7), 있어도 혼합 지원이라 영역 전체로
#: 흘리면 위양성이 생기는(v8, v9의 authored-inlineatoms) openrate 스트라타
#: → 요소 직접 지목. 근거는 각 생성기 스크립트(``scripts/generate_openrate_
#: corpus_v{5,6,7,8,9}.py``)의 독스트링이 그 스트라텀이 실제로 호출한다고
#: 명시하는 API·요소뿐이다 — 스트라텀 전체가 아니라 독스트링이 이름으로
#: 지목한 요소만 싣는다(예: authored-fieldparams는 hp:parameterset이 아니라
#: hp:parameters를 쓴다고 독스트링이 명시하므로 parameterset은 여기 없다).
#: authored-inlineatoms가 영역 경로 대신 여기 있는 이유: hp:lineBreak/
#: nbSpace/fwSpace는 "문단·표 저작/편집"에 등록돼 있지만 그 영역은 p/run/
#: t/tab/tbl/tr/tc/paraPr/charPr 등을 함께 묶은 대형 혼합 영역이다 —
#: 영역째 흘리면 이 스트라텀이 실제로 검증한 적 없는 이웃 요소들까지
#: openrate 근거를 얻는 v8 polygon/arc와 같은 위양성이 재발한다.
#: (6.8 트레인㉚: authored-fontface·authored-pagecontrol은 예전엔 대응
#: capabilityArea가 없어 여기 있었으나, "글꼴 등록"/"페이지 레이아웃"
#: 영역이 새로 생기면서 위 _OPENRATE_STRATUM_TO_CAPABILITY_AREA로 옮겼다
#: — 옮긴 이유가 이력으로 남도록 여기 적어 둔다.)
_OPENRATE_STRATUM_TO_ELEMENTS: dict[str, tuple[tuple[str, str], ...]] = {
    # v5(cycle 6.1) — generate_openrate_corpus_v5.py 독스트링.
    "authored-tabstops": (("hh", "tabItem"), ("hh", "tabPr"), ("hh", "tabProperties")),
    "authored-drawtext": (("hp", "drawText"),),
    "authored-caption": (("hp", "caption"),),
    # v7(cycle 6.3) — generate_openrate_corpus_v7.py 독스트링.
    "authored-charformat": (
        ("hh", "supscript"), ("hh", "subscript"), ("hh", "outline"),
        ("hh", "emboss"), ("hh", "engrave"),
    ),
    # v8(cycle 6.4) — 요소만 개별 지목(위 capabilityArea 딕셔너리 주석 참조
    # — "arc·polygon·curve·connectLine"은 혼합 지원 영역이라 영역째 못 씀).
    "authored-polygon": (("hp", "polygon"),),
    "authored-arc": (("hp", "arc"),),
    "authored-fieldparams": (
        ("hp", "parameters"), ("hp", "booleanParam"), ("hp", "integerParam"),
        ("hp", "stringParam"), ("hp", "listParam"),
    ),
    # v9(cycle 6.6, 트레인⑳) — generate_openrate_corpus_v9.py 독스트링:
    # 스트라텀이 실제로 호출하는 것은 paragraph.add_run(expand_special_
    # characters=True)이고 그 저작 표면이 만드는 요소가 정확히 이 셋뿐이다
    # (위 주석 참조 — "문단·표 저작/편집" 영역째 흘리면 위양성).
    "authored-inlineatoms": (("hp", "lineBreak"), ("hp", "nbSpace"), ("hp", "fwSpace")),
    # v11(cycle 6.7 트레인㉖·6.8 트레인㉘) — hp:label은 트레인㉖에서 의도적으로
    # capabilityArea=None으로 남겨졌다(HwpxOxmlTable.set_label이 실제로
    # 검증하는 건 hp:label 하나뿐인데, 그걸 "문단·표 저작/편집"(이미 다른
    # 근거로 Render-verified인 대형 혼합 영역) 밑에 등록하면 그 영역의 미검증
    # 이웃 요소들까지 이 openrate 성분을 흘려받는 위양성이 생긴다 — 위 v8/v9
    # 주석과 같은 이유). authored-label 스트라텀이 실제로 호출하는 것은
    # table.set_label(...) 하나이고 그게 만드는 요소도 hp:label 하나뿐이므로
    # 요소 직접 지목으로 충분하다.
    "authored-label": (("hp", "label"),),
    # 6.11 트레인㊳ — v14. hh:underline/strikeout/ratio/spacing/shadow는
    # 대응하는 단일 capabilityArea가 없다(직접 확인 — CAPABILITY_KEYWORDS
    # 전수 grep, 어느 _register 호출도 이 5개를 안 씀). "문자 서식"은
    # support-matrix.md 자신도 "capabilities 영역 배선 없이 매트릭스
    # 산문으로만 근거를 남긴다"고 명시한 영역이라(v7의 authored-charformat
    # 주석도 이 이유로 요소 직접 지목한다) 여기서도 같은 패턴을 따른다.
    # base_char_pr_id는 XML 요소가 아니라 파이썬 레벨 조합 방식(기존
    # charPr을 복제 후 오버라이드)이라 등록할 요소 자체가 없다.
    "authored-charformat2": (
        ("hh", "underline"), ("hh", "strikeout"), ("hh", "ratio"),
        ("hh", "spacing"), ("hh", "shadow"),
    ),
}

#: 원장 재검증(사이클 6.5 트레인⑰ 사후 검토)이 잡은 두 번째 사례 — 영역
#: 경로(capabilityArea)로 openrate 수용 신호를 흘렸더니, 그 영역이 공유하는
#: write=none 요소까지 검증된 것처럼 verificationBasis가 붙는 문제. 이번엔
#: v8의 authored-polygon/arc처럼 이 트레인이 새로 매핑한 스트라타가 원인이
#: 아니라, v4의 authored-checkbox(감사 R4 수리, 이 트레인 이전부터 존재)가
#: "체크박스 양식개체" 영역 전체에 흘리는 기존 신호다 — 그 영역의 저작
#: 표면(`add_check_box`)이 실제로 검증하는 건 `hp:checkBtn`/`formCharPr`뿐,
#: `hp:radioBtn`/`btn`은 지원 매트릭스 자신도 "읽기·보존만 하고 저작 API
#: 없음"이라고 명시한다(오너 결정 보류, 빈도 컷). 이 두 요소만 영역의
#: openrate 성분을 안 받도록 예외 처리한다 — capabilityArea 라벨(그 영역에
#: 속한다는 사실)은 유지하고, verificationBasis만 by-capability-area
#: 단독으로 강등한다(매트릭스 산문 자체가 이미 그렇게 말하고 있으므로 그
#: 성분은 정당).
_OPENRATE_MIXED_SUPPORT_AREA_EXCLUSIONS: frozenset[tuple[str, str]] = frozenset({
    ("hp", "btn"),
    ("hp", "radioBtn"),
})


def _stratum_accepted(row: dict[str, object]) -> bool:
    """단일 스트라텀 행이 실한컴 수용 판정을 통과했는지.

    두 세대의 openrate 스키마를 다 받는다: v1~v5(Windows COM 오라클)는
    연 것과 렌더한 것을 별도로 재는 ``opened``/``requested`` 필드가 있고,
    v6+(macOS GUI 오라클)는 PDF export 성공이 열기를 함의하므로 그 필드가
    아예 없다 — 각 report의 ``scopeNote``가 이 방법론 차이를 명시한다("a
    successful PDF export requires the document to open, so opened is
    implied by render_checked"). 필드가 있으면 그 값까지 검사하고, 없으면
    render_checked/render_failed만으로 판단한다 — 약화가 아니라 그 세대가
    실제로 재는 것 자체가 다르다는 사실을 그대로 반영한다."""

    render_checked = int(row.get("render_checked", 0))  # type: ignore[arg-type]
    render_failed = int(row.get("render_failed", 0))  # type: ignore[arg-type]
    if render_checked <= 0 or render_failed != 0:
        return False
    if "opened" in row or "requested" in row:
        return int(row.get("opened", 0)) == int(row.get("requested", 0)) > 0  # type: ignore[arg-type]
    return True


def _iter_valid_openrate_strata(paths: Sequence[Path]) -> Iterator[tuple[Path, dict[str, dict[str, object]]]]:
    """존재하고 ``harness_valid``인 report 파일들의 (경로, strata) 쌍만.

    오염된 런(음성 대조군이 열려버린 런)이나 없는 파일은 조용히 건너뛴다
    — 오염 런의 headline 수치를 openrate 파이프라인 자신도 withhold하는
    것과 같은 원칙."""

    for path in paths:
        if not path.is_file():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        if not document.get("harness_valid", False):
            continue
        yield path, document.get("strata", {})


def _load_openrate_capability_receipts(paths: Sequence[Path]) -> dict[str, bool]:
    """스트라타별 실한컴 수용 결과를 capabilityArea → 수용 여부로 접는다."""

    receipts: dict[str, bool] = {}
    for _path, strata in _iter_valid_openrate_strata(paths):
        for stratum_name, area in _OPENRATE_STRATUM_TO_CAPABILITY_AREA.items():
            row = strata.get(stratum_name)
            if not row:
                continue
            receipts[area] = receipts.get(area, False) or _stratum_accepted(row)
    return receipts


def _load_openrate_element_receipts(
    paths: Sequence[Path],
) -> dict[tuple[str, str], bool]:
    """capabilityArea 없이 요소를 직접 지목하는 스트라타의 수용 결과."""

    receipts: dict[tuple[str, str], bool] = {}
    for _path, strata in _iter_valid_openrate_strata(paths):
        for stratum_name, keys in _OPENRATE_STRATUM_TO_ELEMENTS.items():
            row = strata.get(stratum_name)
            if not row:
                continue
            accepted = _stratum_accepted(row)
            for key in keys:
                receipts[key] = receipts.get(key, False) or accepted
    return receipts


def _combine_verification_basis(
    support_matrix_basis: str | None, corpus_accepted: bool
) -> str | None:
    if support_matrix_basis == "by-capability-area" and corpus_accepted:
        return "by-capability-area+openrate-corpus"
    if support_matrix_basis is not None:
        return support_matrix_basis
    return "by-openrate-corpus" if corpus_accepted else None


# ---------------------------------------------------------------------------
# 원장 조립
# ---------------------------------------------------------------------------


def _merge_indirect_resolved(
    *tables: dict[tuple[str, str], tuple[bool, bool]],
) -> dict[tuple[str, str], tuple[bool, bool]]:
    merged: dict[tuple[str, str], tuple[bool, bool]] = {}
    for table in tables:
        for key, (read, write) in table.items():
            prior_read, prior_write = merged.get(key, (False, False))
            merged[key] = (prior_read or read, prior_write or write)
    return merged


def build_ledger(
    census_path: Path, openrate_report_paths: Sequence[Path] = OPENRATE_REPORT_PATHS
) -> dict[str, object]:
    schema_elements = parse_schema_elements()
    census = load_corpus(census_path)
    corpus_counts = census.frequencies
    total_real_files = census.total_real_files
    source_files = _read_source_files()
    # 평문 마커/디스패치 스캔은 주석·독스트링을 지운 텍스트에서 돈다(§3-C2
    # 위양성 수리). ast 기반 리졸버(루프 태그·인자 태그)는 원본 텍스트를
    # 그대로 쓴다 — 문자열 리터럴 안에서는 진짜 ast 노드가 나올 수 없어
    # 애초에 이 위양성에 노출되지 않는다.
    source_text = _read_source_corpus(source_files)
    dispatch_windows = _build_dispatch_windows(source_text)
    loop_resolved = _resolve_loop_tag_tables(source_files)
    arg_tag_resolved = _resolve_argument_tag_literals(source_files)
    indirect_resolved = _merge_indirect_resolved(loop_resolved, arg_tag_resolved)
    skeleton_text = _read_skeleton_text()
    status_by_area = _parse_support_matrix_status(
        SUPPORT_MATRIX_PATH.read_text(encoding="utf-8")
    )
    openrate_capability_receipts = _load_openrate_capability_receipts(openrate_report_paths)
    openrate_element_receipts = _load_openrate_element_receipts(openrate_report_paths)
    family_to_prefix = _family_to_prefix()
    prefix_to_family = {prefix: family for family, prefix in family_to_prefix.items()}

    all_keys: set[tuple[str, str]] = set()
    for prefix, names in schema_elements.items():
        all_keys.update((prefix, name) for name in names)
    all_keys.update(corpus_counts)

    elements: list[dict[str, object]] = []
    for prefix, name in sorted(all_keys):
        family = prefix_to_family.get(prefix, prefix)
        schema_source = schema_elements.get(prefix, {}).get(name)
        file_count = corpus_counts.get((prefix, name), 0)
        frequency = round(file_count / total_real_files, 4) if total_real_files else 0.0
        code_read, code_write_api = classify_code_usage(
            prefix, name, family, source_text, dispatch_windows, indirect_resolved
        )
        if code_write_api:
            write_mode = "api"
        elif is_in_skeleton(prefix, name, skeleton_text):
            write_mode = "frozen-template"
        else:
            write_mode = "none"
        area, status, basis = classify_capability(prefix, name, status_by_area)
        area_accepted = area is not None and openrate_capability_receipts.get(area, False)
        if (prefix, name) in _OPENRATE_MIXED_SUPPORT_AREA_EXCLUSIONS:
            area_accepted = False
        corpus_accepted = area_accepted or openrate_element_receipts.get((prefix, name), False)
        # An openrate component on the basis asserts "real Hancom accepted our
        # authoring of this element" - which is only a coherent claim for
        # elements we can author. Area-routed receipts otherwise leak the
        # verified label onto read-only siblings mapped into the same area
        # (observed: hp:btn/hp:radioBtn riding the checkbox area's receipt).
        if write_mode != "api":
            corpus_accepted = False
        basis = _combine_verification_basis(basis, corpus_accepted)
        observed_attributes = census.attribute_names.get((prefix, name), [])

        elements.append(
            {
                "namespace": prefix,
                "element": name,
                "schemaSource": schema_source,
                "corpusFrequency": frequency,
                "corpusFileCount": file_count,
                "codeRead": code_read,
                "codeWrite": write_mode,
                "capabilityArea": area,
                "capabilityStatus": status,
                "verificationBasis": basis,
                "observedAttributes": observed_attributes,
            }
        )

    summary = {
        "totalElements": len(elements),
        "schemaDeclared": sum(1 for e in elements if e["schemaSource"] is not None),
        "corpusOnly": sum(1 for e in elements if e["schemaSource"] is None),
        "corpusObserved": sum(1 for e in elements if e["corpusFileCount"] > 0),
        "codeRead": sum(1 for e in elements if e["codeRead"]),
        "codeWriteApi": sum(1 for e in elements if e["codeWrite"] == "api"),
        "codeWriteFrozenTemplate": sum(1 for e in elements if e["codeWrite"] == "frozen-template"),
        "codeWriteNone": sum(1 for e in elements if e["codeWrite"] == "none"),
        "capabilityMapped": sum(1 for e in elements if e["capabilityArea"] is not None),
        "renderVerified": sum(1 for e in elements if e["verificationBasis"] is not None),
        "renderVerifiedByOpenrateCorpus": sum(
            1
            for e in elements
            if e["verificationBasis"] in ("by-openrate-corpus", "by-capability-area+openrate-corpus")
        ),
        "attributesObserved": sum(1 for e in elements if e["observedAttributes"]),
    }

    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedFrom": {
            "schemaDir": "DevDoc/OWPML SCHEMA",
            "corpusCensus": str(census_path.relative_to(ROOT))
            if census_path.is_relative_to(ROOT)
            else str(census_path),
            "corpusCensusGenerator": "scripts/build_element_census.py",
            "corpusPopulationNote": census.population_note,
            "supportMatrix": "src/hwpx/data/contract_docs/support-matrix.md",
            "openrateReports": [
                str(path.relative_to(ROOT))
                for path in openrate_report_paths
                if path.is_relative_to(ROOT) and path.is_file()
            ],
            "skeleton": "src/hwpx/data/Skeleton.hwpx",
            "sourceScanned": "src/hwpx/**/*.py",
        },
        "corpusTotalFiles": total_real_files,
        "corpusUnknownFiles": census.unknown_files,
        "corpusForeignNamespaces": census.foreign_namespaces,
        "corpusUnnamespacedElements": census.unnamespaced_elements,
        "summary": summary,
        "elements": elements,
    }


# ---------------------------------------------------------------------------
# Markdown 요약
# ---------------------------------------------------------------------------


def _fmt_pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0.0%"
    return f"{numerator / denominator * 100:.1f}%"


def render_markdown(ledger: dict[str, object]) -> str:
    summary = ledger["summary"]
    elements: list[dict[str, object]] = ledger["elements"]  # type: ignore[assignment]
    total = summary["totalElements"]

    lines: list[str] = []
    lines.append("# OWPML 커버리지 원장")
    lines.append("")
    lines.append(
        "`scripts/coverage_ledger.py`가 OWPML 2024 스키마(`DevDoc/OWPML SCHEMA/`) · "
        "실코퍼스 census(`scripts/build_element_census.py`) · `src/hwpx/` 코드 "
        "참조 · 지원 매트릭스 · v4~v16 openrate 실한컴 코퍼스에서 결정론적으로 "
        "재산출하는 원장이다. 손으로 쓴 지원 주장이 아니라 기계 판독 "
        "[coverage-ledger.json](coverage-ledger.json)의 사람용 요약이며, "
        "`python scripts/coverage_ledger.py --check`가 드리프트를 게이트한다."
    )
    lines.append("")
    lines.append(
        "**주의**: `capabilityArea`는 지원 매트릭스 산문에 명시적으로 언급된 "
        "요소만 근사 매핑했다(무근거 승격 금지). `null`은 \"미지원\"이 아니라 "
        "\"매트릭스 행과 요소가 1:1로 대응되지 않음\"을 뜻한다 — 저수준 공용 "
        "요소(fieldBegin·autoNum·좌표류)가 대표적이다."
    )
    lines.append("")
    lines.append("## 수리 기록 (2026-08-04 독립 감사 §3 실증 → 같은 사이클 내 수리)")
    lines.append("")
    lines.append(
        "이 원장은 2026-08-04 독립 감사에서 \"결정론은 재현되지만 정확도는 "
        "불합격\" 판정을 받았다([감사 판정문 §3]"
        "(2026-08-04-completeness-audit-verdict.md)). 아래는 그 §3 결론 4항목을 "
        "그대로 수리한 기록이다 — 무엇이 어떻게 고쳐졌고, 되돌리면 감사가 인용한 "
        "오판이 그대로 재현됨을 확인했다(양방향 실행 로그는 커밋 메시지·리뷰 "
        "기록 참조)."
    )
    lines.append("")
    lines.append(
        "**1) 분류기 — 위양성(주석/독스트링) 수리.** 스캔 전에 `tokenize`로 "
        "주석을, `ast`로 베어 문자열 문(독스트링 포함)을 블랭크 처리한다"
        "(`_strip_non_code_text`). 감사가 실측한 13개 요소 판정 뒤집힘"
        "(codeWriteApi 134→123, codeRead 192→186)이 이 텍스트에서 재현됨을 "
        "확인했다 — 예: `hp:case`/`hp:switch`는 `table_patch.py`의 독스트링이 "
        "태그를 언급한 덕에 read=True로 잘못 집계돼 있었고, `hp:lineseg`/"
        "`hp:seg`는 `patch.py`/`objects.py` 주석의 예시 태그 표기"
        "(`<hp:lineseg>`, `<hp:seg>`)가 여는 태그 리터럴로 오인됐다."
    )
    lines.append(
        "**2) 분류기 — 위음성(`etree.Element(` 별칭) 수리.** `_WRITE_MARKERS`에 "
        "`etree.Element(`를 추가했다(`ET.Element(`/`LET.Element(`만 있었다) — "
        "`oxml/body.py`·`header.py`가 이 별칭으로 방출하는 자리를 넓게 잡는다."
    )
    lines.append(
        "**3) 분류기 — 함수-인자 태그 전달 수리(신규 리졸버 + 명시 화이트리스트).** "
        "두 갈래로 다뤘다:"
    )
    lines.append(
        "   - **일반 리졸버**(`_resolve_argument_tag_literals`, 3c절): 함수 "
        "파라미터가 자기 본문에서 `f\"{_HP}{param}\"` 형태로 태그 조립에 쓰이는 "
        "자리를 찾고, 그 파라미터가 리터럴 없이 다른 함수에 그대로 전달되는 "
        "자리(예: `_note_shape(tag) → _note_pr_element(tag)`)를 고정점까지 "
        "전파한 뒤, 실제 리터럴 인자가 있는 호출부에서 해석한다. 감사가 "
        "지목한 `hh:ratio`/`hh:spacing`(장평/자간, `document_parts.py`) 외에 "
        "같은 관용구로 저평가돼 있던 `hh:relSz`/`hh:offset`(첨자), "
        "`hh:margin`/`hh:lineSpacing`(`header_part.py`의 문단 서식 setter), "
        "`hp:footNotePr`/`endNotePr`(`section_format.py`, 2단계 전달), "
        "`hp:header`/`footer`/`footNote`/`endNote`, `hp:booleanParam`"
        "(`toc_author.py`)까지 같은 결함 계열로 실측·수리됐다 — 감사는 앞의 "
        "둘만 스팟체크했지만 결함 자체는 훨씬 넓었다."
    )
    lines.append(
        "   - **명시 화이트리스트**(`_MANUAL_CODE_USAGE_OVERRIDES`, 3d절): "
        "`hp:insertBegin`/`insertEnd`/`deleteBegin`/`deleteEnd`(변경추적 마크)는 "
        "태그가 런타임 dict 값 문자열 연결로 조립돼(`body.py`의 "
        "`create_track_change_mark`) 어떤 정적 분석으로도 못 잡는다 — 근거 "
        "파일:라인을 필수로 요구하는 화이트리스트로 처리했고, 생성기가 시작 "
        "시점에 근거 문자열의 존재·형식을 검증한다(근거 없는 항목은 "
        "`ValueError`)."
    )
    lines.append(
        "**4) census 재구축.** 생성 스크립트를 `scripts/build_element_census.py`로 "
        "신설·커밋했다(기존 census는 생성기 미보존이 결함이었다). 전 파트·전 "
        "네임스페이스를 스캔한다 — `ha:*`(settings.xml)·`hv:HCFVersion`"
        "(version.xml)이 이제 1급 요소 행이고, `hs:sec`도 실제 관측 빈도로 "
        "잡힌다. 모집단은 **명시적으로 재정의**했다: 레거시 166파일(그 중 "
        "hwpxlib 47은 지금도 이 레포에 남아 있고 검증 가능하다 — 나머지 119는 "
        "이 워크트리 어디에도 원본이나 목록이 보존돼 있지 않아 정체를 확인할 "
        "수 없다)은 재현·확장이 불가능했다 — 조용히 계승하는 대신 접근 가능한 "
        "새 모집단으로 바꿨다. 상세는 `generatedFrom.corpusPopulationNote`."
    )
    if ledger.get("corpusUnknownFiles"):
        unknown = ledger["corpusUnknownFiles"]
        lines.append(
            f"   unknown 파일: {unknown.get('count', 0)}건"
            + (f" — 사유: {unknown.get('reasons')}" if unknown.get("reasons") else " (전량 유효한 zip으로 열림)")
            + "."
        )
    lines.append(
        "**5) 속성 축.** 요소별 관측 속성 **이름** 집합을 census가 함께 "
        "기록한다(`observedAttributes` 컬럼, 값 빈도까지는 이번 사이클 범위 "
        "밖 — 생성기 독스트링에 명시)."
    )
    lines.append(
        "**6) openrate 코퍼스 환류(v4~v16).** `docs/openrate/report-v{4,5,6,7,8,9,10,11,12,13,14,15,16}."
        "json`의 스트라타별 실한컴 수용(`render_checked>0`·`render_failed==0`, "
        "구세대 스키마는 `opened==requested>0`도 함께)을 `verificationBasis`로 "
        "환류한다(`by-openrate-corpus`/`by-capability-area+openrate-corpus`) — "
        "2026-08-04 감사 R4가 지목한 v4 배선(원 이름 `by-v4-corpus`)을 2026-08 "
        "사이클 6.5 트레인⑰에서 v8까지, 사이클 6.6 트레인⑳에서 v9까지, "
        "사이클 6.7 트레인㉔에서 v10까지 확장하며 "
        "버전-중립 이름으로 바꿨다. 두 경로로 매핑한다: 이미 등록된 "
        "capabilityArea와 1:1 대응하는 스트라타는 "
        "`_OPENRATE_STRATUM_TO_CAPABILITY_AREA`(차트·체크박스·수식·각주 2종·"
        "테두리채우기·하이라이트·메모·그룹컨테이너·문서옵션호환성), capabilityArea가 아직 "
        "없거나 있어도 혼합 지원 영역이라 요소만 지목해야 하는 신규 능력"
        "(글꼴·탭·도형텍스트·캡션·쪽번호제어·문자서식·필드파라미터·arc/polygon·"
        "인라인 원자 3종)은 `_OPENRATE_STRATUM_TO_ELEMENTS`로 요소를 직접 "
        "지목한다 — 둘 다 근거는 각 생성기 스크립트 독스트링이 실제로 부른다고 "
        "명시하는 것뿐(무근거 매핑 금지, `fieldBegin`을 일부러 안 매핑한 것과 "
        "같은 원칙)."
    )
    lines.append("")
    observed = [e for e in elements if e["corpusFileCount"] > 0]
    new_write_none_observed = sum(1 for e in observed if e["codeWrite"] == "none")
    new_read_none_observed = sum(1 for e in observed if not e["codeRead"])
    new_frozen_observed = sum(1 for e in observed if e["codeWrite"] == "frozen-template")
    lines.append(
        f"**전 vs 후 (감사가 하한을 인용한 것과 같은 슬라이스 — corpusFileCount>0인 "
        f"요소만)**: 감사 인용 하한은 관측 {_AUDIT_BASELINE_OBSERVED}건 중 "
        f"write=none **{_AUDIT_BASELINE_WRITE_NONE}** · read=none "
        f"**{_AUDIT_BASELINE_READ_NONE}** · frozen-template "
        f"**{_AUDIT_BASELINE_FROZEN}**([감사 판정문](2026-08-04-completeness-audit-verdict.md) "
        f"요약표). 이 원장 재생성 기준으로는 관측 {len(observed)}건 중 "
        f"write=none **{new_write_none_observed}** · read=none "
        f"**{new_read_none_observed}** · frozen-template **{new_frozen_observed}**. "
        f"**주의**: 두 population이 다르다(모집단을 재정의했다 — 위 4항목) — "
        f"이 비교는 \"같은 잣대로 다시 잰 정확한 델타\"가 아니라 분류기 수리가 "
        f"방향대로 움직였는지의 참고 신호다. 분류기 수리 자체의 정확도 증거는 "
        f"위 1~3항의 요소별 재현 로그가 1차 근거다."
    )
    lines.append("")

    lines.append("## 전체 통계")
    lines.append("")
    lines.append("| 지표 | 값 | 비율 |")
    lines.append("|---|---|---|")
    lines.append(f"| 요소 총수 | {total} | — |")
    lines.append(
        f"| 스키마 선언 | {summary['schemaDeclared']} | {_fmt_pct(summary['schemaDeclared'], total)} |"
    )
    lines.append(
        f"| 코퍼스에만 있음(스키마 미대응) | {summary['corpusOnly']} | {_fmt_pct(summary['corpusOnly'], total)} |"
    )
    lines.append(
        f"| 실코퍼스에서 관측(빈도>0) | {summary['corpusObserved']} | {_fmt_pct(summary['corpusObserved'], total)} |"
    )
    lines.append(f"| 코드 읽기 | {summary['codeRead']} | {_fmt_pct(summary['codeRead'], total)} |")
    lines.append(
        f"| 코드 쓰기(api) | {summary['codeWriteApi']} | {_fmt_pct(summary['codeWriteApi'], total)} |"
    )
    lines.append(
        f"| 쓰기 frozen-template | {summary['codeWriteFrozenTemplate']} | "
        f"{_fmt_pct(summary['codeWriteFrozenTemplate'], total)} |"
    )
    lines.append(
        f"| 쓰기 none | {summary['codeWriteNone']} | {_fmt_pct(summary['codeWriteNone'], total)} |"
    )
    lines.append(
        f"| 능력 영역 매핑됨 | {summary['capabilityMapped']} | {_fmt_pct(summary['capabilityMapped'], total)} |"
    )
    lines.append(
        f"| Render-verified(매핑 근거) | {summary['renderVerified']} | "
        f"{_fmt_pct(summary['renderVerified'], total)} |"
    )
    lines.append(
        f"| ..중 openrate 코퍼스(v4~v16) 환류분 | {summary['renderVerifiedByOpenrateCorpus']} | "
        f"{_fmt_pct(summary['renderVerifiedByOpenrateCorpus'], total)} |"
    )
    lines.append(
        f"| 속성 이름 축 관측됨 | {summary['attributesObserved']} | "
        f"{_fmt_pct(summary['attributesObserved'], total)} |"
    )
    lines.append("")
    population_note = ledger["generatedFrom"].get("corpusPopulationNote")
    lines.append(f"실코퍼스 표본: 실문서 {ledger['corpusTotalFiles']}개.")
    if population_note:
        lines.append("")
        lines.append(f"> {population_note}")
    unknown = ledger.get("corpusUnknownFiles") or {}
    if unknown.get("count"):
        lines.append("")
        lines.append(
            f"unknown(zip으로 못 열렸거나 XML 파트가 전부 파싱 실패한 파일): "
            f"{unknown['count']}건 — 사유별: {unknown.get('reasons', {})}."
        )
    foreign = ledger.get("corpusForeignNamespaces") or {}
    if foreign:
        lines.append("")
        lines.append(
            "임베드/외부 네임스페이스(OWPML 요소 스키마 밖 — per-element 행이 "
            "아니라 여기 파일수로만 가시화): "
            + ", ".join(f"`{uri}` {count}건" for uri, count in sorted(foreign.items()))
            + "."
        )
    unnamespaced = ledger.get("corpusUnnamespacedElements") or {}
    if unnamespaced:
        lines.append("")
        lines.append(
            "네임스페이스 접두 없이 방출된 요소(스키마는 네임스페이스를 "
            "선언하나 실문서 어휘가 접두를 안 씀 — `hc:pt0` vs `hp:pt0`류와 "
            "같은 편차): "
            + ", ".join(f"`{tag}` {count}건" for tag, count in sorted(unnamespaced.items()))
            + " — `docs/owpml-deviations.md` 후보."
        )
    lines.append("")

    lines.append("## 실코퍼스 빈도 상위인데 frozen-template 또는 none인 요소")
    lines.append("")
    lines.append(
        "코퍼스에서 실제로 자주 관측되지만(구조는 통과) 코드에서 독립적으로 "
        "만들거나 편집할 API가 없는 요소 — Q3b 작업 목록 후보."
    )
    lines.append("")
    worklist = sorted(
        (e for e in elements if e["codeWrite"] in ("frozen-template", "none") and e["corpusFileCount"] > 0),
        key=lambda e: (-e["corpusFileCount"], e["namespace"], e["element"]),
    )
    lines.append("| 네임스페이스:요소 | 코퍼스 빈도 | 파일수 | codeRead | codeWrite | 능력 영역 |")
    lines.append("|---|---|---|---|---|---|")
    shown = worklist[:40]
    for e in shown:
        area = e["capabilityArea"] or "—"
        lines.append(
            f"| `{e['namespace']}:{e['element']}` | {e['corpusFrequency']:.4f} | "
            f"{e['corpusFileCount']} | {e['codeRead']} | {e['codeWrite']} | {area} |"
        )
    if len(worklist) > len(shown):
        lines.append("")
        lines.append(
            f"(총 {len(worklist)}건 중 상위 {len(shown)}건만 표시 — 전체는 "
            "coverage-ledger.json의 `elements` 참조.)"
        )
    lines.append("")

    lines.append("## 네임스페이스별 표")
    lines.append("")
    lines.append(
        "| 네임스페이스 | 요소 수 | 스키마 선언 | 코퍼스 관측 | 읽기 | 쓰기 api | frozen-template | 쓰기 none |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    by_ns: dict[str, list[dict[str, object]]] = {}
    for e in elements:
        by_ns.setdefault(e["namespace"], []).append(e)
    for prefix in sorted(by_ns):
        group = by_ns[prefix]
        lines.append(
            f"| `{prefix}` | {len(group)} | "
            f"{sum(1 for e in group if e['schemaSource'] is not None)} | "
            f"{sum(1 for e in group if e['corpusFileCount'] > 0)} | "
            f"{sum(1 for e in group if e['codeRead'])} | "
            f"{sum(1 for e in group if e['codeWrite'] == 'api')} | "
            f"{sum(1 for e in group if e['codeWrite'] == 'frozen-template')} | "
            f"{sum(1 for e in group if e['codeWrite'] == 'none')} |"
        )
    lines.append("")

    lines.append("## 방법론 메모")
    lines.append("")
    lines.append(
        "- **접두 규약**: `hwpx.oxml.namespaces.HWPML_COMPAT_ROOT_NAMESPACES`에서 "
        "파생(hp=paragraph, hh=head, hc=core, hs=section, hm=master-page, "
        "hhs=history). `hv`(version)만 예외 — 그 레지스트리 자체에 `version` "
        "패밀리가 없어(실결함) 코드 리터럴에서 확인한 값을 하드코딩했다."
    )
    lines.append(
        "- **스키마 vs 코퍼스 접두 불일치는 의도적으로 병합하지 않았다**: 예를 들어 "
        "`ParaList XML schema.xml`은 `pt0`을 자신의 타깃 네임스페이스(hp)에 "
        "선언하지만 실문서는 `hc:pt0`을 쓴다(`hp:line`은 `hc:startPt`를, "
        "`hp:connectLine`은 `hp:startPt`를 쓰는 것과 같은 종류의 드리프트 — "
        "`src/hwpx/opc/package.py`의 `_SHAPE_POINT_LOCAL_NAMES` 주석 참조). "
        "두 항목 다 원장에 남아 있으며, 이런 드리프트 자체가 "
        "`docs/owpml-deviations.md`(Q4 편차 레지스트리)의 입력 후보다."
    )
    lines.append(
        "- **codeRead/codeWrite는 정적 패턴 매칭 + 두 단계 ast 리졸버**다. "
        "1단계(평문, 스캔 전 주석·독스트링 블랭크): 한정 태그 리터럴/QName "
        "조립, 접두 없는 `local_name()` 계열 비교 디스패치, `for name in TABLE:` "
        "형태로 루프 변수가 태그가 되는 자리(`ast`로 `TABLE`을 정적 평가). "
        "2단계(원본 텍스트, `_resolve_argument_tag_literals`): 태그가 함수 "
        "파라미터로 전달되는 자리 — 파라미터가 자기 본문에서 태그 조립에 "
        "쓰이는 함수를 찾고, 그 파라미터를 리터럴 없이 그대로 전달하는 호출 "
        "체인을 고정점까지 추적한 뒤, 실제 리터럴이 있는 호출부에서 해석한다 "
        "(2026-08-04 감사 §3-C2 수리 — 전엔 이 부류가 통째로 과소 집계됐다). "
        "**남은 한계**: 이 2단계 리졸버는 단일 파일 안에서만 동작한다(모듈 "
        "간 호출은 안 쫓는다) — 다른 파일의 함수로 전달되는 태그가 있다면 "
        "여전히 놓칠 수 있다. 완전히 동적으로 조립되는 태그(런타임 문자열 "
        "연결 등)는 `_MANUAL_CODE_USAGE_OVERRIDES`의 근거-필수 화이트리스트로 "
        "다룬다."
    )
    lines.append(
        "- **capabilityArea**는 지원 매트릭스 산문에 명시적으로 나온 요소만 "
        "매핑했다. 여러 능력 영역이 공유하는 저수준 요소(예: `fieldBegin`은 "
        "누름틀·TOC·하이퍼링크가 다 쓴다)는 일부러 매핑하지 않았다. "
        "`verificationBasis`는 두 독립 출처를 결합한다 — 지원 매트릭스 산문의 "
        "\"Render-verified\" 표기(`by-capability-area`)와 `docs/openrate/"
        "report-v{4,5,6,7,8,9,10,11,12,13,14,15,16}.json` 실한컴 openrate 코퍼스의 스트라타별 수용 "
        "receipt(`by-openrate-corpus`) — capabilityArea 경로는 매핑이 명확한 "
        "스트라타에 한해서만, capabilityArea가 아직 없는 스트라타는 생성기 "
        "독스트링이 명시하는 요소에 직접."
    )
    lines.append(
        "- **census 생성기**(`scripts/build_element_census.py`)는 전 파트·전 "
        "네임스페이스를 스캔하고, unknown 파일은 사유와 함께 기록하며, "
        "OWPML 요소 스키마 밖의 임베드/외부 네임스페이스와 비네임스페이스 "
        "요소는 별도 버킷(`foreignNamespaces`/`unnamespacedElements`)으로 "
        "가시화한다(삼키지 않는다). 두 번 실행하면 바이트까지 같은 출력을 "
        "낸다(결정론) — 단, 이 레포가 vendoring한 census 스냅샷은 소유자의 "
        "비공개 실문서 코퍼스를 포함해 생성됐으므로, 그 서브셋은 소유자만 "
        "재현 가능하다(`generatedFrom.corpusPopulationNote` 참조) — 이는 "
        "감사가 지적한 \"생성기 자체가 없다\"는 결함과는 다른 종류다: 생성기는 "
        "있고 커밋돼 있고 결정론적이다, 다만 입력 중 하나가 공개 레포 밖에 "
        "있을 뿐이다."
    )
    lines.append("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _display_path(path: Path) -> str:
    """``ROOT`` 기준 상대경로로 보여주되, 벗어난 경로(테스트의 tmp_path
    리다이렉션 등)라도 절대경로로 조용히 대체한다 — 어느 쪽이든 죽지 않는다."""

    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="드리프트 검사만(비제로 exit)")
    parser.add_argument(
        "--census",
        type=Path,
        default=DEFAULT_CENSUS_PATH,
        help="실코퍼스 census JSON 경로 (기본: 동봉 스냅샷)",
    )
    args = parser.parse_args()

    ledger = build_ledger(args.census)
    json_text = json.dumps(ledger, ensure_ascii=False, indent=2) + "\n"
    md_text = render_markdown(ledger)

    if args.check:
        drift: list[str] = []
        if not LEDGER_JSON.is_file() or LEDGER_JSON.read_text(encoding="utf-8") != json_text:
            drift.append(_display_path(LEDGER_JSON))
        if not LEDGER_MD.is_file() or LEDGER_MD.read_text(encoding="utf-8") != md_text:
            drift.append(_display_path(LEDGER_MD))
        if drift:
            print(
                "coverage ledger drift (run scripts/coverage_ledger.py): " + ", ".join(drift),
                file=sys.stderr,
            )
            return 1
        print("coverage ledger in sync")
        return 0

    LEDGER_JSON.write_text(json_text, encoding="utf-8")
    LEDGER_MD.write_text(md_text, encoding="utf-8")
    summary = ledger["summary"]
    print(f"[OK] {_display_path(LEDGER_JSON)} ({summary['totalElements']} elements)")
    print(f"[OK] {_display_path(LEDGER_MD)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
