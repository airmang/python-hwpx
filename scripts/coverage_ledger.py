# SPDX-License-Identifier: Apache-2.0
"""OWPML 요소 커버리지 원장 생성기.

"우리가 OWPML의 무엇을 읽고/쓰고/실한컴 검증했는가"를 손으로 쓴 지원 주장이
아니라 4개 입력에서 결정론적으로 재산출한다:

1. **스키마 전집** — ``DevDoc/OWPML SCHEMA/*.xml`` (OWPML 2024 XSD 7종)에서
   ``xs:element name="..."`` 선언을 전부 걷어 네임스페이스 접두(hp/hh/hc/hs/
   hm/hhs/hv)별 요소 집합을 만든다. 접두는 ``hwpx.oxml.namespaces``의
   ``HWPML_COMPAT_ROOT_NAMESPACES``/``namespace_family()``에서 파생한다 —
   즉 이 스크립트가 별도로 접두 규약을 하드코딩하지 않고, 라이브러리가 실제
   문서를 읽고 쓸 때 쓰는 바로 그 접두를 그대로 쓴다.
2. **실코퍼스 빈도** — ``docs/_extra/element-census.json``(166개 실문서
   census의 동봉 스냅샷; 원본은 harness 상위 레포
   ``specs/056-authoring-fidelity-audit/evidence/p0/element-census.json``에
   있고, 이 레포 CI는 그 레포를 보지 못하므로 스냅샷을 vendoring했다 —
   ``--census``로 다른 경로를 줄 수 있다). census에 없는 요소는 조작·추정
   없이 빈도 0으로 정직하게 기록한다.
3. **코드 참조** — ``src/hwpx/`` 전체에서 요소별 태그 리터럴·QName 조립
   패턴, 접두 없는 ``local_name()`` 계열 비교 디스패치, 그리고 루프 변수로
   태그가 조립되는 자리(``ast``로 그 루프가 도는 테이블을 정적 평가)까지
   세 경로를 합쳐 찾는다. ``makeelement``/``SubElement``/``_append_child``/
   여는 태그 리터럴(``<hp:xxx``) 근방이면 쓰기(``api``), 그 밖의 참조는
   읽기로 잡는다. 코드에 없지만 ``Skeleton.hwpx``에 상수로 박혀 있으면
   ``frozen-template``(구조는 통과하되 절대 못 바꾸는 영역)로 분류한다 —
   이게 이 원장의 핵심 정직 포인트다. 태그가 함수 인자로 넘어오는 자리는
   호출부까지 추적하지 않는 알려진 한계다.
4. **실한컴 검증 여부** — ``src/hwpx/data/contract_docs/support-matrix.md``의
   행별 등급을 요소로 근사 매핑한다. 매핑은 매트릭스 산문에 실제로 언급된
   태그·헬퍼로만 근거를 두며(예: "hp:formCharPr", "add_line"), 근거 없는
   승격은 하지 않는다 — 대응 행이 불분명한 요소는 ``capabilityArea: null``로
   남는다. 매핑된 요소라도 그 행의 등급 문자열에 "Render-verified"가 없으면
   ``verificationBasis``는 null이다(무근거 승격 금지).

이 스크립트는 지원 매트릭스·capabilities 레지스트리·census 원본을 전혀
쓰지 않는다(읽기 전용 입력). 산출은 ``docs/coverage-ledger.json``(기계 판독)과
``docs/coverage-ledger.md``(사람 요약) 두 파일이다.

    python scripts/coverage_ledger.py          # 원장 재생성
    python scripts/coverage_ledger.py --check  # 드리프트 검사만(비제로 exit)
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "DevDoc" / "OWPML SCHEMA"
DEFAULT_CENSUS_PATH = ROOT / "docs" / "_extra" / "element-census.json"
SUPPORT_MATRIX_PATH = ROOT / "src" / "hwpx" / "data" / "contract_docs" / "support-matrix.md"
SKELETON_PATH = ROOT / "src" / "hwpx" / "data" / "Skeleton.hwpx"
SRC_DIR = ROOT / "src" / "hwpx"
LEDGER_JSON = ROOT / "docs" / "coverage-ledger.json"
LEDGER_MD = ROOT / "docs" / "coverage-ledger.md"

SCHEMA_VERSION = "python-hwpx.coverage-ledger/v1"
XS_NS = "http://www.w3.org/2001/XMLSchema"

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


def load_corpus(census_path: Path) -> tuple[dict[tuple[str, str], int], int]:
    """실코퍼스 census에서 (접두, 요소)→파일수와 전체 실문서 수를 읽는다."""

    if not census_path.is_file():
        raise FileNotFoundError(
            f"corpus census not found: {census_path}\n"
            "vendored snapshot이 없으면 --census로 원본 census 경로를 넘기거나 "
            "harness 상위 레포의 specs/056-authoring-fidelity-audit/evidence/p0/"
            "element-census.json을 docs/_extra/element-census.json으로 복사할 것."
        )
    document = json.loads(census_path.read_text(encoding="utf-8"))
    total_real_files = int(document["files"]["real"])
    frequencies: dict[tuple[str, str], int] = {}
    for key, count in document["real_element_filecounts"].items():
        prefix, _, name = key.partition(":")
        frequencies[(prefix, name)] = int(count)
    return frequencies, total_real_files


# ---------------------------------------------------------------------------
# 3) 코드 참조 (읽기/쓰기)
# ---------------------------------------------------------------------------

#: makeelement/append 근방이면 "새 요소를 만든다"는 강한 신호.
_WRITE_MARKERS = (
    "makeelement",
    "SubElement",
    "ET.Element(",
    "LET.Element(",
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


def _read_source_corpus(files: list[tuple[Path, str]]) -> str:
    """파일 목록을 하나의 탐색용 텍스트로 합친다."""

    return "\n\n".join(text for _path, text in files)


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
_LOCAL_NAME_GETTERS = ("local_name", "tag_local_name", "_element_local_name", "_local_name")
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
    loop_resolved: dict[tuple[str, str], tuple[bool, bool]],
) -> tuple[bool, bool]:
    """(codeRead, codeWriteApi)를 돌려준다."""

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
    loop_read, loop_write = loop_resolved.get((prefix, name), (False, False))
    code_read = code_read or loop_read
    code_write = code_write or loop_write
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
    "p", "run", "t", "lineBreak", "tab", "nbSpace", "secPr",
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
_register(
    "그림 삽입/치환", "hp", "pic", "imgRect", "imgDim", "imgClip", "effects",
)
_register("그림 삽입/치환", "hc", "img", "imgBrush")
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
# 원장 조립
# ---------------------------------------------------------------------------


def build_ledger(census_path: Path) -> dict[str, object]:
    schema_elements = parse_schema_elements()
    corpus_counts, total_real_files = load_corpus(census_path)
    source_files = _read_source_files()
    source_text = _read_source_corpus(source_files)
    dispatch_windows = _build_dispatch_windows(source_text)
    loop_resolved = _resolve_loop_tag_tables(source_files)
    skeleton_text = _read_skeleton_text()
    status_by_area = _parse_support_matrix_status(
        SUPPORT_MATRIX_PATH.read_text(encoding="utf-8")
    )
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
            prefix, name, family, source_text, dispatch_windows, loop_resolved
        )
        if code_write_api:
            write_mode = "api"
        elif is_in_skeleton(prefix, name, skeleton_text):
            write_mode = "frozen-template"
        else:
            write_mode = "none"
        area, status, basis = classify_capability(prefix, name, status_by_area)

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
    }

    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedFrom": {
            "schemaDir": "DevDoc/OWPML SCHEMA",
            "corpusCensus": str(census_path.relative_to(ROOT))
            if census_path.is_relative_to(ROOT)
            else str(census_path),
            "corpusCensusUpstream": (
                "specs/056-authoring-fidelity-audit/evidence/p0/element-census.json "
                "(harness 상위 레포; 이 레포 CI에서는 보이지 않아 스냅샷을 vendoring)"
            ),
            "supportMatrix": "src/hwpx/data/contract_docs/support-matrix.md",
            "skeleton": "src/hwpx/data/Skeleton.hwpx",
            "sourceScanned": "src/hwpx/**/*.py",
        },
        "corpusTotalFiles": total_real_files,
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
        "실코퍼스 census · `src/hwpx/` 코드 참조 · 지원 매트릭스에서 결정론적으로 "
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
    lines.append("## ⚠ 알려진 측정 오차 (2026-08-04 독립 감사 실증 — 수리 전 필독)")
    lines.append("")
    lines.append(
        "이 원장의 **결정론은 재현되지만 정확도는 불합격 판정**을 받았다"
        "([감사 판정문 §3](2026-08-04-completeness-audit-verdict.md)). 아래 "
        "수치를 인용할 때는 양방향 오차를 함께 인용해야 한다:"
    )
    lines.append("")
    lines.append(
        "- **위양성**: 주석·독스트링 텍스트가 커버리지로 집계된다 — 비코드 "
        "텍스트를 제거하고 재계산하면 13개 요소의 판정이 뒤집힌다"
        "(codeWriteApi 134→123, codeRead 192→186)."
    )
    lines.append(
        "- **위음성**: `etree.Element(` alias와 함수-인자 태그 전달을 스캐너가 "
        "못 본다 — 실제 출하·실한컴 검증된 변경추적 마크(`hp:insertBegin` 4종)가 "
        "write=none으로, 실저작 가능한 `hh:ratio`(장평)·`hh:spacing`(자간)이 "
        "frozen으로 잘못 집계돼 있다."
    )
    lines.append(
        "- **모집단 부분성**: census가 hp:/hh:/hc: 요소만 센다 — "
        "`ha:*`(settings, 실파일 100%)·`hv:HCFVersion`(100%)·`hs:sec`(100%)·"
        "임베드 외부 XML이 모집단 밖이고, census 생성 스크립트는 레포에 보존돼 "
        "있지 않으며, 분모 166 밖의 unknown 84파일 처분이 미기록이다."
    )
    lines.append("- **속성 축 부재**: 요소만 세고 속성은 측정하지 않는다.")
    lines.append("")
    lines.append(
        "수리 계획은 감사 판정문 §3 결론의 4항목이며 다음 사이클의 1순위다. "
        "수리 전까지 이 원장은 \"작업 방향을 잡는 지도\"로만 유효하고 \"지원 "
        "여부의 판정 근거\"로는 인용 불가다."
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
    lines.append("")
    lines.append(f"실코퍼스 표본: 실문서 {ledger['corpusTotalFiles']}개 (저작 충실도 감사 census).")
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
        "- **codeRead/codeWrite는 정적 패턴 매칭**이다 — 한정 태그 리터럴/QName "
        "조립, 접두 없는 `local_name()` 계열 비교 디스패치, `for name in TABLE:` "
        "형태로 루프 변수가 태그가 되는 자리(`ast`로 `TABLE`을 정적 평가) 세 "
        "경로를 합친다. `makeelement`/`SubElement`/`_append_child`/여는 태그 "
        "리터럴 근방이면 쓰기, 그 밖은 읽기로 분류한다. **알려진 한계**: 태그가 "
        "함수 인자로 넘어오는 자리(예: `section_format.py`의 header/footer "
        "`tag` 매개변수)는 호출부 인자까지 추적하지 않아 못 잡는다 — 이런 "
        "요소는 실제로는 코드가 다루는데도 `codeRead/codeWrite`가 과소 집계될 "
        "수 있다."
    )
    lines.append(
        "- **capabilityArea**는 지원 매트릭스 산문에 명시적으로 나온 요소만 "
        "매핑했다. 여러 능력 영역이 공유하는 저수준 요소(예: `fieldBegin`은 "
        "누름틀·TOC·하이퍼링크가 다 쓴다)는 일부러 매핑하지 않았다."
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
