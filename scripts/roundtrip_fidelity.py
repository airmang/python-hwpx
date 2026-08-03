# SPDX-License-Identifier: Apache-2.0
"""실한컴 저장본 왕복 충실도 측정 하니스 (S-120 Q4b).

목표: 실한컴이 저장한 문서를 우리가 열고 **무편집** 재직렬화(``open()`` →
``to_bytes()``, 어떤 op도 안 부름)했을 때 (a) 바이트 단위로 무엇이 변하는지
분류하고 (b) 그 산출물을 ``work/roundtrip-v1/``에 남겨 실한컴 개봉 판정
배치(박스, 별도 실행)가 그대로 집어 쓰게 한다. 개봉 판정 자체는 이
스크립트의 범위가 아니다 — 로컬 절반(코퍼스 선별 + 바이트 분류)만 한다.

## 코퍼스 선별 — "실한컴 저장본만 자격이 있다"

``tests/fixtures/**/*.hwpx``를 전수 훑되, 각 파일의 ``version.xml``에서
``application``/``appVersion``을 직접 읽어 실한컴 산출물임을 증명한다
(``application="Hancom Office Hangul"`` — 실 Skeleton.hwpx·이 저장소의
모든 gold 픽스처가 공유하는 리터럴). 증명 못 하는 파일은 **정직하게
제외**하고 사유를 남긴다:

- ``hwpxlib_corpus/tool__blank.hwpx`` — ``version.xml``의 ``application``이
  ``"hwpxlib"``다(직접 확인). hwpxlib 자체 산출물이지 실한컴이 아니다.
- ``reader_robustness/irb_form_blank.hwpx``·``irb_form_filled.hwpx`` — 같은
  디렉터리의 ``NOTICE.md``가 명시: "real Hancom rejects as 손상(corrupt)"
  — 실한컴이 열지도 못하는 의도적 비표준 픽스처라 왕복 충실도의 분모가
  될 수 없다(오라클 입력이 아님, 수리하면 그 픽스처의 존재 목적이 깨진다).

## 바이트 분류

파일 전체가 바이트 동일하지 않아도 원인은 여러 층위일 수 있다:

1. ``byte-identical`` — 파일 전체가 원본과 바이트 단위로 같다.
2. ``zip-container-only`` — 모든 zip 멤버의 **압축 해제 내용**은 같지만
   전체 zip 바이트는 다르다(멤버 순서·압축 파라미터 등 컨테이너 프레이밍
   차이 — 콘텐츠 손실이 아니다).
3. ``cosmetic:<카테고리,...>`` — 멤버 내용이 다르지만 전부 알려진 무해한
   카테고리(``boolean-spelling``: xs:boolean의 "0"/"1" ↔ "true"/"false"
   표기 정규화, ``whitespace``: 순수 공백/들여쓰기 차이). 네임스페이스
   **접두 문자열**(``hp`` vs 자동생성 접두 등) 차이는 이 분류에 들어오지도
   않는다 — lxml이 태그를 ``{네임스페이스URI}로컬명``으로 비교해 접두
   자체가 애초에 안 보인다(``test_redline_authoring.py``의 xfail이 말하는
   "changes namespace prefixes"는 그래서 이 계측에서 무해로 자동 흡수된다).
4. ``substantive-structural-change`` — 태그·속성값(불리언 등가 아님)·자식
   수·의미 있는 텍스트가 실제로 다르다. 수리 후보.

## 결정론

타임스탬프를 어디에도 안 남긴다(``generatedAt`` 류 필드 없음) — 같은
입력 트리라면 몇 번을 돌려도 ``manifest.json``이 바이트 동일해야 한다.

    python scripts/roundtrip_fidelity.py             # 측정 + work/roundtrip-v1/ 갱신
    python scripts/roundtrip_fidelity.py --list-only  # 코퍼스 선별 결과만(측정 안 함)
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = ROOT / "tests" / "fixtures"
OUTPUT_DIR = ROOT / "work" / "roundtrip-v1"
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"

SCHEMA_VERSION = "python-hwpx.roundtrip-fidelity/v1"

#: 파일별 실한컴 비산출물 확정 사유 — 코드/문서로 직접 근거를 확인한 것만.
KNOWN_NON_ORACLE_EXCLUSIONS: dict[str, str] = {
    "hwpxlib_corpus/tool__blank.hwpx": (
        'version.xml application="hwpxlib"(직접 확인) — hwpxlib 자체 산출물, 실한컴 아님'
    ),
    "reader_robustness/irb_form_blank.hwpx": (
        "NOTICE.md 명시: 실한컴이 손상(header.xml 부재 + hs:sec 직속 comment/PI 노드)으로 "
        "거부 — 의도적 비표준 픽스처, 오라클 입력 아님"
    ),
    "reader_robustness/irb_form_filled.hwpx": (
        "NOTICE.md 명시: 실한컴이 손상으로 거부 — 오라클 입력 아님(irb_form_blank와 동일 사유)"
    ),
}

_XML_MEMBER_RE = re.compile(r"\.(xml|hpf)$", re.IGNORECASE)
_BOOLEAN_TRUE = {"1", "true", "True", "TRUE"}
_BOOLEAN_FALSE = {"0", "false", "False", "FALSE"}
_COSMETIC_CATEGORIES = {"boolean-spelling", "whitespace"}


# ---------------------------------------------------------------------------
# 코퍼스 선별
# ---------------------------------------------------------------------------


@dataclass
class CorpusEntry:
    rel_path: str
    path: Path
    provenance: str  # 왜 실한컴산이라 믿는가


@dataclass
class ExclusionEntry:
    rel_path: str
    reason: str


def _hancom_provenance(path: Path) -> str | None:
    """version.xml의 application/appVersion을 실한컴 증거로 반환, 아니면 None."""

    try:
        with zipfile.ZipFile(path) as archive:
            if "version.xml" not in archive.namelist():
                return None
            text = archive.read("version.xml").decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, KeyError, OSError):
        return None

    app_match = re.search(r'application="([^"]*)"', text)
    ver_match = re.search(r'appVersion="([^"]*)"', text)
    app = app_match.group(1) if app_match else None
    version = ver_match.group(1) if ver_match else None
    if not app or "hancom" not in app.lower():
        return None
    return f"version.xml application={app!r} appVersion={version!r}"


def discover_corpus() -> tuple[list[CorpusEntry], list[ExclusionEntry]]:
    included: list[CorpusEntry] = []
    excluded: list[ExclusionEntry] = []

    for path in sorted(FIXTURES_DIR.rglob("*.hwpx")):
        rel = path.relative_to(FIXTURES_DIR).as_posix()
        if rel in KNOWN_NON_ORACLE_EXCLUSIONS:
            excluded.append(ExclusionEntry(rel, KNOWN_NON_ORACLE_EXCLUSIONS[rel]))
            continue
        provenance = _hancom_provenance(path)
        if provenance is None:
            excluded.append(
                ExclusionEntry(rel, "version.xml에 실한컴 application 마커가 없거나 확인 불가")
            )
            continue
        included.append(CorpusEntry(rel, path, provenance))

    return included, excluded


# ---------------------------------------------------------------------------
# XML 구조 비교 (네임스페이스 URI+로컬명 기준 — 접두 문자열은 애초에 안 보임)
# ---------------------------------------------------------------------------


@dataclass
class ElementDiff:
    path: str
    category: str  # "boolean-spelling" | "whitespace" | "structural"
    detail: str


def _is_boolean_pair(a: str, b: str) -> bool:
    both_boolean_literals = (a in _BOOLEAN_TRUE or a in _BOOLEAN_FALSE) and (
        b in _BOOLEAN_TRUE or b in _BOOLEAN_FALSE
    )
    if not both_boolean_literals:
        return False
    return (a in _BOOLEAN_TRUE) == (b in _BOOLEAN_TRUE)


def _local_path(element: etree._Element) -> str:
    return etree.QName(element).localname


def diff_elements(
    a: etree._Element, b: etree._Element, path: str = "/"
) -> list[ElementDiff]:
    diffs: list[ElementDiff] = []

    if a.tag != b.tag:
        diffs.append(ElementDiff(path, "structural", f"tag differs: {a.tag} != {b.tag}"))
        return diffs  # 태그 자체가 다르면 자식 대응이 무의미하다

    a_attrs, b_attrs = dict(a.attrib), dict(b.attrib)
    for key in sorted(set(a_attrs) | set(b_attrs)):
        av, bv = a_attrs.get(key), b_attrs.get(key)
        if av == bv:
            continue
        if av is None or bv is None:
            diffs.append(
                ElementDiff(path, "structural", f"attr {key!r} presence differs: {av!r} vs {bv!r}")
            )
        elif _is_boolean_pair(av, bv):
            diffs.append(ElementDiff(path, "boolean-spelling", f"attr {key!r}: {av!r} vs {bv!r}"))
        else:
            diffs.append(
                ElementDiff(path, "structural", f"attr {key!r} value differs: {av!r} vs {bv!r}")
            )

    a_text, b_text = a.text or "", b.text or ""
    if a_text != b_text:
        if a_text.strip() == "" and b_text.strip() == "":
            diffs.append(ElementDiff(path, "whitespace", "text whitespace differs"))
        else:
            diffs.append(ElementDiff(path, "structural", f"text differs: {a_text!r} vs {b_text!r}"))

    a_children, b_children = list(a), list(b)
    if len(a_children) != len(b_children):
        diffs.append(
            ElementDiff(
                path,
                "structural",
                f"child count differs: {len(a_children)} vs {len(b_children)}",
            )
        )
        return diffs  # 자식 수가 다르면 페어와이즈 대응이 신뢰할 수 없다

    for index, (ca, cb) in enumerate(zip(a_children, b_children)):
        child_path = f"{path}{_local_path(ca)}[{index}]/"
        diffs.extend(diff_elements(ca, cb, child_path))
        a_tail, b_tail = ca.tail or "", cb.tail or ""
        if a_tail != b_tail:
            if a_tail.strip() == "" and b_tail.strip() == "":
                diffs.append(ElementDiff(child_path, "whitespace", "tail whitespace differs"))
            else:
                diffs.append(ElementDiff(child_path, "structural", "tail text differs"))

    return diffs


# ---------------------------------------------------------------------------
# 파일/멤버 측정
# ---------------------------------------------------------------------------


@dataclass
class MemberResult:
    name: str
    identical: bool
    categories: list[str] = field(default_factory=list)
    structural_diffs: list[str] = field(default_factory=list)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def measure_zip_member(name: str, original: bytes, resaved: bytes) -> MemberResult:
    if original == resaved:
        return MemberResult(name, identical=True)

    if not _XML_MEMBER_RE.search(name):
        return MemberResult(
            name, identical=False, categories=["binary"], structural_diffs=["비-XML 멤버가 바이트 단위로 다름"]
        )

    try:
        tree_a = etree.fromstring(original)
        tree_b = etree.fromstring(resaved)
    except etree.XMLSyntaxError as exc:
        return MemberResult(
            name, identical=False, categories=["structural"], structural_diffs=[f"XML 파싱 실패: {exc}"]
        )

    diffs = diff_elements(tree_a, tree_b)
    categories = sorted({d.category for d in diffs})
    structural = [f"{d.path} :: {d.detail}" for d in diffs if d.category not in _COSMETIC_CATEGORIES]
    return MemberResult(name, identical=False, categories=categories, structural_diffs=structural[:25])


@dataclass
class FileResult:
    rel_path: str
    provenance: str
    original_sha256: str
    resaved_sha256: str
    overall_category: str
    members: list[MemberResult] = field(default_factory=list)


def measure_file(entry: CorpusEntry) -> FileResult:
    from hwpx.document import HwpxDocument

    original_bytes = entry.path.read_bytes()
    doc = HwpxDocument.open(entry.path)
    resaved_bytes = doc.to_bytes()
    doc.close()

    whole_identical = original_bytes == resaved_bytes

    with zipfile.ZipFile(io.BytesIO(original_bytes)) as za, zipfile.ZipFile(
        io.BytesIO(resaved_bytes)
    ) as zb:
        names_a, names_b = set(za.namelist()), set(zb.namelist())
        members: list[MemberResult] = []
        for extra in sorted(names_a - names_b):
            members.append(
                MemberResult(extra, identical=False, categories=["structural"], structural_diffs=["원본에만 존재하는 zip 멤버"])
            )
        for extra in sorted(names_b - names_a):
            members.append(
                MemberResult(extra, identical=False, categories=["structural"], structural_diffs=["재직렬화본에만 존재하는 zip 멤버"])
            )
        for name in sorted(names_a & names_b):
            members.append(measure_zip_member(name, za.read(name), zb.read(name)))

    members.sort(key=lambda m: m.name)
    all_content_identical = names_a == names_b and all(m.identical for m in members)
    all_categories = sorted({c for m in members for c in m.categories})
    has_structural_or_binary = any(c not in _COSMETIC_CATEGORIES for c in all_categories)

    if whole_identical:
        overall = "byte-identical"
    elif all_content_identical:
        overall = "zip-container-only"
    elif has_structural_or_binary:
        overall = "substantive-structural-change"
    elif all_categories:
        overall = "cosmetic:" + ",".join(all_categories)
    else:  # pragma: no cover - whole_identical이 False인데 카테고리가 비면 논리 모순
        overall = "unknown"

    out_path = OUTPUT_DIR / entry.rel_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(resaved_bytes)

    return FileResult(
        rel_path=entry.rel_path,
        provenance=entry.provenance,
        original_sha256=_sha256(original_bytes),
        resaved_sha256=_sha256(resaved_bytes),
        overall_category=overall,
        members=members,
    )


# ---------------------------------------------------------------------------
# 보고
# ---------------------------------------------------------------------------


def _member_to_dict(member: MemberResult) -> dict[str, object]:
    return {
        "name": member.name,
        "identical": member.identical,
        "categories": member.categories,
        "structuralDiffs": member.structural_diffs,
    }


def build_manifest(
    included: list[FileResult], excluded: list[ExclusionEntry]
) -> dict[str, object]:
    summary: dict[str, int] = {}
    for result in included:
        summary[result.overall_category] = summary.get(result.overall_category, 0) + 1

    return {
        "schemaVersion": SCHEMA_VERSION,
        "corpusRoot": "tests/fixtures",
        "excluded": [
            {"file": entry.rel_path, "reason": entry.reason}
            for entry in sorted(excluded, key=lambda e: e.rel_path)
        ],
        "included": [
            {
                "file": result.rel_path,
                "provenance": result.provenance,
                "originalSha256": result.original_sha256,
                "resavedSha256": result.resaved_sha256,
                "overallCategory": result.overall_category,
                # 완전 동일 파일은 멤버 세부를 생략해 manifest를 가볍게 유지.
                "members": (
                    [] if result.overall_category == "byte-identical"
                    else [_member_to_dict(m) for m in result.members if not m.identical]
                ),
            }
            for result in included
        ],
        "summary": {
            "totalIncluded": len(included),
            "totalExcluded": len(excluded),
            "categoryDistribution": dict(sorted(summary.items())),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list-only", action="store_true", help="코퍼스 선별 결과만 출력(측정/저장 없음)"
    )
    args = parser.parse_args()

    included, excluded = discover_corpus()

    print(f"코퍼스 선별: 포함 {len(included)}건, 제외 {len(excluded)}건")
    for entry in excluded:
        print(f"  제외: {entry.rel_path} — {entry.reason}")

    if args.list_only:
        for entry in included:
            print(f"  포함: {entry.rel_path} — {entry.provenance}")
        return 0

    results: list[FileResult] = []
    for entry in included:
        result = measure_file(entry)
        results.append(result)
        print(f"  {result.overall_category:32s} {result.rel_path}")

    manifest = build_manifest(results, excluded)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )

    print()
    print(f"[OK] {MANIFEST_PATH.relative_to(ROOT)}")
    print(f"[OK] 재직렬화 산출물: {OUTPUT_DIR.relative_to(ROOT)}/ ({len(results)}개 파일)")
    print()
    print("분류 분포:")
    for category, count in sorted(manifest["summary"]["categoryDistribution"].items()):
        print(f"  {category}: {count}")

    structural = [r for r in results if r.overall_category == "substantive-structural-change"]
    print()
    if not structural:
        print("실질 구조 변화: 0건")
    else:
        print(f"실질 구조 변화: {len(structural)}건 (수리 후보)")
        for result in structural:
            print(f"  - {result.rel_path}")
            for member in result.members:
                if member.identical:
                    continue
                if any(c not in _COSMETIC_CATEGORIES for c in member.categories):
                    print(f"      {member.name}: {member.categories}")
                    for detail in member.structural_diffs[:5]:
                        print(f"        {detail}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
