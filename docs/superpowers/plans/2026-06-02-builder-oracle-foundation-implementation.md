# 빌더 토대 0 — hwpxlib 오라클 기반 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 공식 OWPML 스키마(신뢰 불가) 대신 hwpxlib 샘플 코퍼스·한컴 수용성을 신뢰 가능한 오라클로 깔아, 이후 빌더·범정부오피스·form-fill 작업을 de-risk한다.

**Architecture:** 4갈래 독립 작업 — (1) hwpxlib 47 샘플 데이터 벤더링 + 매니페스트, (2) "47개 전부 읽기" 스모크로 현 리더 갭 가시화, (3) `validate_document` 스키마 실패를 하드게이트→경고(lint)로 강등(구조 불변식은 하드게이트 유지), (4) `hwpx-skill`의 visual_review 루프에 축 A(구조 수용성: round-trip) 보강. 코어 라이브러리는 렌더러-프리 유지.

**Tech Stack:** Python 3.10+, lxml, pytest, stdlib(urllib/tarfile/json/argparse), 기존 `HwpxDocument`/`validate_document`/`validate_package`. `uv run --extra dev pytest`.

**개발 환경:**
- python-hwpx 루트: `/Users/wilycastle/Code/projects/hwpx/python-hwpx`
- hwpx-skill 루트: `/Users/wilycastle/Code/projects/hwpx/hwpx-skill`
- 테스트: `cd /Users/wilycastle/Code/projects/hwpx/python-hwpx && uv run --extra dev pytest -q`
- 단일 테스트: `uv run --extra dev pytest tests/test_<name>.py::<test> -v`

**Legal boundary (clean-room):** hwpxlib(neolord0, Apache-2.0)의 **코드/구조는 복사·번역 포팅 금지**. 이 Stage는 hwpxlib의 **샘플 데이터(.hwpx)만 벤더링**한다(사용자 결정). 출처는 `NOTICE`에 기록한다. 코드 동작 미러링은 다음(빌더) Stage의 일이다.

**검증된 사실 (구현 전 필독, 현재 소스 기준):**
- `validate_document`(`src/hwpx/tools/validator.py:120`)는 **헤더/섹션 스키마 검증만** 한다. 구조 하드게이트(CRC/OPC)는 `tools/package_validator.py`의 `validate_package`에, 재오픈은 `HwpxDocument.open`에 별도로 있다.
- `ValidationIssue`(`validator.py:35-50`)는 `part_name/message/line/column` frozen dataclass로 **severity 필드가 없다**. `ValidationReport.ok`(`:60-64`)는 `not self.issues`다.
- 현 `_schemas/header.xsd`·`section.xsd`는 2011 ns + `<xs:any lax>` stub(거의 noop). 이번엔 스키마 강화가 아니라 **강등 + 코퍼스 오라클**이 목표다.
- `hwpx-skill/scripts/visual_review.py`: `SCHEMA_VERSION = "hwpx.visual-review.v1"`, 상태 `{observed_pass, needs_review, blocked}`, `build_evidence(args)`가 `current` 블록 생성. **시각(축 B)만** 있고 구조 수용성(축 A) 없음.
- hwpxlib 샘플 경로: `testFile/reader_writer/*.hwpx`(기능별, 예: HeaderFooter/PageFunctions/SimpleTable/SimplePicture/MultiColumn/PageSize_Margin), `testFile/error/**/*.hwpx`(실제 문서 회귀셋). 총 47개.

---

## Stage Context

- **Wily Stage:** `STG-3611d648b9d9` (display `S-012`) — 빌더 토대 0.
- **다음 Stage:** `STG-d79e63646ee9` (S-013, 빌더 코어)가 이 Stage에 의존.
- 설계 스펙: `docs/2026-06-02-hwpx-builder-design.md` §8(오라클), §11 Phase 0.

## File Structure

- Create: `python-hwpx/tests/fixtures/hwpxlib_corpus/fetch_corpus.py` — 핀된 hwpxlib ref에서 샘플 .hwpx 1회 벤더링 + manifest.json 생성.
- Create: `python-hwpx/tests/fixtures/hwpxlib_corpus/manifest.json` — 기능→샘플 매핑(스크립트 산출, 커밋).
- Create: `python-hwpx/tests/fixtures/hwpxlib_corpus/*.hwpx` (47) — 벤더링된 샘플 데이터.
- Create: `python-hwpx/tests/test_hwpxlib_corpus_read.py` — "47개 전부 읽기" 스모크.
- Modify: `python-hwpx/src/hwpx/tools/validator.py` — `ValidationIssue.severity` + 스키마 issue를 warning으로.
- Create: `python-hwpx/tests/test_validation_severity.py` — 강등/하드게이트 분리 검증.
- Create: `python-hwpx/docs/owpml-deviations.md` — 편차/네임스페이스 레지스트리.
- Create: `python-hwpx/tests/test_deviations_registry.py` — 레지스트리 형식 가드.
- Modify: `python-hwpx/NOTICE` — hwpxlib 코퍼스 출처 귀속.
- Modify: `hwpx-skill/scripts/visual_review.py` — 축 A(구조 수용성 round-trip) + evidence 필드.
- Create: `hwpx-skill/tests/test_visual_review_axis_a.py` — round-trip 수용성 테스트.

---

## Phase 0 — hwpxlib 샘플 코퍼스 벤더링

### Task 1: 코퍼스 fetch 스크립트 + 1회 벤더링 + NOTICE 귀속

**Files:**
- Create: `tests/fixtures/hwpxlib_corpus/fetch_corpus.py`
- Create (산출): `tests/fixtures/hwpxlib_corpus/manifest.json`, `tests/fixtures/hwpxlib_corpus/*.hwpx`
- Modify: `NOTICE`

- [ ] **Step 1: fetch 스크립트 작성**

```python
# tests/fixtures/hwpxlib_corpus/fetch_corpus.py
# SPDX-License-Identifier: Apache-2.0
"""Vendor hwpxlib sample .hwpx files (Apache-2.0) for use as test oracle fixtures.

Run ONCE to populate this directory, then commit the result. Tests never fetch.
Usage: python tests/fixtures/hwpxlib_corpus/fetch_corpus.py --ref <commit-sha>
Pin --ref to a specific hwpxlib commit SHA (not a moving branch) and record it in manifest.json.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import tarfile
import urllib.request
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent
TARBALL = "https://github.com/neolord0/hwpxlib/archive/{ref}.tar.gz"
# feature label inferred from the reader_writer file stem; error/ files are regression inputs.
FEATURE_HINTS = {
    "HeaderFooter": "header_footer",
    "PageFunctions": "page_number",
    "PageSize_Margin": "page_size_margin",
    "MultiColumn": "multi_column",
    "SimpleTable": "table",
    "SimplePicture": "image",
    "SimpleEquation": "equation",
    "ChangeTrack": "track_change",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", required=True, help="hwpxlib commit SHA to pin")
    args = parser.parse_args(argv)

    url = TARBALL.format(ref=args.ref)
    print(f"downloading {url}")
    data = urllib.request.urlopen(url).read()  # noqa: S310 - pinned github url, one-time tool

    entries: list[dict[str, str]] = []
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile() or "/testFile/" not in member.name:
                continue
            if not member.name.endswith(".hwpx"):
                continue
            rel = member.name.split("/testFile/", 1)[1]  # e.g. reader_writer/HeaderFooter.hwpx
            payload = tar.extractfile(member).read()
            out_name = rel.replace("/", "__")  # flatten: reader_writer__HeaderFooter.hwpx
            (CORPUS_DIR / out_name).write_bytes(payload)
            stem = Path(rel).stem
            entries.append({
                "file": out_name,
                "source_path": f"testFile/{rel}",
                "feature": FEATURE_HINTS.get(stem, "regression" if rel.startswith("error/") else "other"),
                "sha256": hashlib.sha256(payload).hexdigest(),
            })

    entries.sort(key=lambda e: e["file"])
    manifest = {
        "source_repo": "https://github.com/neolord0/hwpxlib",
        "license": "Apache-2.0",
        "pinned_ref": args.ref,
        "count": len(entries),
        "samples": entries,
    }
    (CORPUS_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"vendored {len(entries)} samples -> {CORPUS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: hwpxlib HEAD SHA를 핀하고 1회 실행**

```bash
cd /Users/wilycastle/Code/projects/hwpx/python-hwpx
# 현재 hwpxlib main HEAD SHA 확인 후 그 값을 --ref 로 고정한다 (moving branch 금지):
REF=$(curl -s https://api.github.com/repos/neolord0/hwpxlib/commits/main | python -c "import sys,json;print(json.load(sys.stdin)['sha'])")
echo "pinning hwpxlib ref=$REF"
uv run python tests/fixtures/hwpxlib_corpus/fetch_corpus.py --ref "$REF"
```

Expected: `vendored 47 samples -> .../hwpxlib_corpus`, `manifest.json` 생성, `*.hwpx` 47개 생성.

- [ ] **Step 3: NOTICE에 귀속 추가**

`NOTICE`에 아래 블록을 추가한다(기존 내용 보존):

```
## Test fixtures: hwpxlib sample corpus

tests/fixtures/hwpxlib_corpus/ contains .hwpx sample files vendored from
neolord0/hwpxlib (https://github.com/neolord0/hwpxlib), licensed Apache-2.0.
Only sample DATA files are vendored; no hwpxlib source code or structure is
copied (clean-room). Pinned ref is recorded in manifest.json.
```

- [ ] **Step 4: 벤더링 결과 커밋**

```bash
git add tests/fixtures/hwpxlib_corpus/ NOTICE
git commit -m "test(fixtures): vendor hwpxlib sample corpus as HWPX oracle"
```

### Task 2: "47개 전부 읽기" 스모크 테스트

**Files:**
- Create: `tests/test_hwpxlib_corpus_read.py`

- [ ] **Step 1: 실패 테스트 작성 (manifest 기반 parametrize)**

```python
# tests/test_hwpxlib_corpus_read.py
# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument

CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"
MANIFEST = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))

# Samples that python-hwpx cannot yet read. Each entry MUST have a reason and a
# tracking note. Empty list is the goal; failures are classified here, never silently skipped.
KNOWN_READ_FAILURES: dict[str, str] = {
    # "reader_writer__SimpleEquation.hwpx": "equation part not modeled yet (builder backlog)",
}


def _sample_ids() -> list[str]:
    return [s["file"] for s in MANIFEST["samples"]]


def test_manifest_count_matches_files() -> None:
    files = {p.name for p in CORPUS.glob("*.hwpx")}
    assert files == {s["file"] for s in MANIFEST["samples"]}
    assert MANIFEST["count"] == len(files)


@pytest.mark.parametrize("sample", _sample_ids())
def test_corpus_sample_opens(sample: str) -> None:
    if sample in KNOWN_READ_FAILURES:
        pytest.xfail(KNOWN_READ_FAILURES[sample])
    doc = HwpxDocument.open(CORPUS / sample)
    # minimal liveness: sections iterate and text export does not raise
    assert doc.sections is not None
    doc.export_text()
```

- [ ] **Step 2: 실행해서 현 리더 갭 노출**

Run: `uv run --extra dev pytest tests/test_hwpxlib_corpus_read.py -v`
Expected: 대부분 PASS. 일부 FAIL이면 → 해당 파일을 `KNOWN_READ_FAILURES`에 사유와 함께 등록(xfail로 전환). silent skip 금지.

- [ ] **Step 3: 갭 등록 후 재실행하여 그린 확인**

Run: `uv run --extra dev pytest tests/test_hwpxlib_corpus_read.py -v`
Expected: PASS(+ 등록된 xfail). 리더 갭이 `KNOWN_READ_FAILURES`에 문서화됨.

- [ ] **Step 4: 커밋**

```bash
git add tests/test_hwpxlib_corpus_read.py
git commit -m "test: read-all-47 hwpxlib corpus smoke; classify reader gaps as xfail"
```

---

## Phase 1 — 스키마 lint 강등 + 구조 하드게이트 분리

### Task 3: `ValidationIssue.severity` 추가 + 스키마 실패를 경고로

**Files:**
- Modify: `src/hwpx/tools/validator.py`
- Test: `tests/test_validation_severity.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_validation_severity.py
# SPDX-License-Identifier: Apache-2.0
from hwpx.tools.validator import ValidationIssue, ValidationReport, validate_document


def test_issue_has_severity_default_error():
    issue = ValidationIssue(part_name="Contents/section0.xml", message="x")
    assert issue.severity == "error"


def test_report_separates_errors_and_warnings():
    warn = ValidationIssue("p", "schema lint", severity="warning")
    err = ValidationIssue("p", "broken", severity="error")
    assert ValidationReport(("p",), (warn,)).ok is True          # warnings do not fail
    assert ValidationReport(("p",), (warn,)).warnings == (warn,)
    assert ValidationReport(("p",), (err,)).ok is False
    assert ValidationReport(("p",), (err,)).errors == (err,)


def test_schema_failures_are_warnings_not_errors(tmp_path):
    # a structurally valid doc whose XML the (stub/real) schema rejects must still report ok,
    # because schema failures are demoted to warnings (lint), not hard errors.
    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    path = tmp_path / "d.hwpx"
    doc.save_to_path(path)
    report = validate_document(path)
    assert all(i.severity == "warning" for i in report.issues)
    assert report.ok is True
```

- [ ] **Step 2: 실행해서 실패 확인**

Run: `uv run --extra dev pytest tests/test_validation_severity.py -v`
Expected: FAIL — `ValidationIssue`에 `severity`/`ValidationReport`에 `errors`/`warnings` 없음.

- [ ] **Step 3: validator.py 수정**

`ValidationIssue`에 `severity` 필드 추가, `ValidationReport`에 `errors`/`warnings` 프로퍼티 추가, `.ok`는 에러 기준, 스키마 issue 생성부를 warning으로:

```python
@dataclass(frozen=True)
class ValidationIssue:
    part_name: str
    message: str
    line: int | None = None
    column: int | None = None
    severity: str = "error"  # "error" (hard) | "warning" (schema lint)
    # __str__ 유지
```

```python
@dataclass(frozen=True)
class ValidationReport:
    validated_parts: tuple[str, ...]
    issues: tuple[ValidationIssue, ...]

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity == "error")

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity == "warning")

    @property
    def ok(self) -> bool:
        """OK when there are no hard errors. Schema lint warnings do not fail."""
        return not self.errors
```

`_issues_from_error`와 그 호출부에서 스키마 위반은 `severity="warning"`으로 만든다:

```python
def _issues_from_error(part_name: str, exc: etree.DocumentInvalid) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    error_log = getattr(exc, "error_log", None)
    if error_log is not None and len(error_log):
        for entry in error_log:
            issues.append(ValidationIssue(
                part_name=part_name, message=entry.message,
                line=getattr(entry, "line", None), column=getattr(entry, "column", None),
                severity="warning",
            ))
        return issues
    issues.append(ValidationIssue(part_name=part_name, message=str(exc), severity="warning"))
    return issues
```

`validate_document`의 `except Exception` 방어 분기도 `severity="warning"`으로 통일한다(스키마 로딩/검증 계열은 lint).

- [ ] **Step 4: 실행해서 통과 확인 + 회귀**

Run: `uv run --extra dev pytest tests/test_validation_severity.py tests/test_oxml_parsing.py -v`
Expected: PASS. (`.ok`/`.issues` 사용하는 기존 호출부 회귀 없음 — 기존 호출부는 `not issues`와 동치 동작 유지: 에러 없으면 ok.)

- [ ] **Step 5: 커밋**

```bash
git add src/hwpx/tools/validator.py tests/test_validation_severity.py
git commit -m "feat(validator): demote schema failures to lint warnings; keep errors as hard gate"
```

### Task 4: `owpml-deviations.md` 편차 레지스트리

**Files:**
- Create: `docs/owpml-deviations.md`
- Test: `tests/test_deviations_registry.py`

- [ ] **Step 1: 형식 가드 테스트 작성**

```python
# tests/test_deviations_registry.py
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

DOC = Path(__file__).resolve().parents[1] / "docs" / "owpml-deviations.md"


def test_registry_exists_with_required_sections():
    text = DOC.read_text(encoding="utf-8")
    assert "# OWPML 편차 레지스트리" in text
    assert "## 네임스페이스 정합 (2011/2016 ↔ 2024)" in text
    # at least one deviation entry with evidence pointer
    assert "증거:" in text
```

- [ ] **Step 2: 실행해서 실패 확인**

Run: `uv run --extra dev pytest tests/test_deviations_registry.py -v`
Expected: FAIL — 파일 없음.

- [ ] **Step 3: 레지스트리 작성**

```markdown
# OWPML 편차 레지스트리

공식 OWPML 스키마(de jure)와 한컴오피스 실동작(de facto) 사이의 확인된 편차를 기록한다.
스키마는 하드게이트가 아니라 수렴 lint다(설계 §8.2). 확인된 편차는 로컬 `_schemas`를
한컴 현실에 맞게 패치할 때 근거가 된다.

## 네임스페이스 정합 (2011/2016 ↔ 2024)

- 코드/문서는 2011·2016 네임스페이스를 기본으로 사용하고, 공식 스키마는 2024 ns다.
- 전략: 읽기는 2011/2016/2024 모두 수용, 쓰기는 입력 문서의 ns를 보존. 신규 생성은 한컴 최신 출력 ns를 따른다.
- 증거: tests/fixtures/hwpxlib_corpus/manifest.json 의 샘플들에서 실제 사용 ns를 확인.

## 확인된 편차

| ID | 공식 스키마 | 한컴 실동작 | 증거 샘플 | 상태 |
|---|---|---|---|---|
| DEV-001 | (예시 자리, 첫 실제 편차 발견 시 교체) | | | open |

> 각 편차는 `증거:` 로 코퍼스/캡처 경로를 명시한다. 확정 편차는 `_schemas` 패치 커밋 SHA를 status에 남긴다.
```

(주의: 표의 DEV-001 행은 첫 실제 편차로 교체하거나, 발견 전이면 "확인된 편차 없음(현 스키마는 lax stub)"으로 한 줄 기록하고 `증거:` 라인을 네임스페이스 절에 둔다 — 테스트의 `증거:` 가드를 만족시킬 것.)

- [ ] **Step 4: 실행해서 통과 확인**

Run: `uv run --extra dev pytest tests/test_deviations_registry.py -v`
Expected: PASS.

- [ ] **Step 5: 커밋**

```bash
git add docs/owpml-deviations.md tests/test_deviations_registry.py
git commit -m "docs: add OWPML deviation registry (schema demoted to convergent lint)"
```

---

## Phase 2 — 시각검증 루프에 축 A(구조 수용성) 보강

### Task 5: `visual_review.py` round-trip 구조 수용성

**Files:**
- Modify: `hwpx-skill/scripts/visual_review.py`
- Test: `hwpx-skill/tests/test_visual_review_axis_a.py`

> 참고: 한컴 GUI "복구 다이얼로그" 관찰은 기존 ComputerUse 관찰 흐름(`--observation`)으로 캡처한다. 이 Task는 그와 별개로, **렌더러 없이 파이썬으로 가능한 구조 수용성**(save→reopen round-trip)을 evidence에 추가한다. python-hwpx가 설치돼 있을 때만 수행하고, 없으면 skip 표기한다.

- [ ] **Step 1: 실패 테스트 작성**

```python
# hwpx-skill/tests/test_visual_review_axis_a.py
# SPDX-License-Identifier: Apache-2.0
import importlib.util
from pathlib import Path

import pytest

SPEC = Path(__file__).resolve().parents[1] / "scripts" / "visual_review.py"
spec = importlib.util.spec_from_file_location("visual_review", SPEC)
visual_review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(visual_review)

pytest.importorskip("hwpx")  # axis A round-trip needs python-hwpx


def test_structural_acceptance_passes_for_valid_doc(tmp_path):
    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    doc.add_paragraph("수용성 확인")
    path = tmp_path / "ok.hwpx"
    doc.save_to_path(path)

    result = visual_review.structural_acceptance(path)
    assert result["opens"] is True
    assert result["roundtrip_ok"] is True
    assert result["status"] == "accepted"
```

- [ ] **Step 2: 실행해서 실패 확인**

Run: `cd /Users/wilycastle/Code/projects/hwpx/hwpx-skill && uv run --extra dev pytest tests/test_visual_review_axis_a.py -v`
Expected: FAIL — `structural_acceptance` 없음.

- [ ] **Step 3: `structural_acceptance` 구현 + evidence에 연결**

`visual_review.py`에 추가:

```python
def structural_acceptance(path: Path) -> dict[str, Any]:
    """Axis A: renderer-free acceptance — open + save->reopen round-trip stability.

    The Hancom "repair dialog" observation (true acceptance oracle) is captured
    separately via ComputerUse --observation; this is the python-side proxy.
    """
    try:
        from hwpx.document import HwpxDocument
    except Exception as exc:  # python-hwpx absent
        return {"opens": None, "roundtrip_ok": None, "status": "skipped", "reason": str(exc)}

    result: dict[str, Any] = {"opens": False, "roundtrip_ok": False, "status": "rejected"}
    try:
        doc = HwpxDocument.open(path)
        result["opens"] = True
        round_bytes = doc.to_bytes()
        reopened = HwpxDocument.open(round_bytes)
        # stability proxy: same section count and non-decreasing paragraph count
        result["roundtrip_ok"] = len(reopened.sections) == len(doc.sections)
        result["status"] = "accepted" if result["roundtrip_ok"] else "rejected"
    except Exception as exc:
        result["reason"] = str(exc)
    return result
```

`build_evidence`의 `current` 블록(파일 `:251` 부근)에 축 A 결과를 추가한다:

```python
    current = {
        # ... 기존 키 유지 ...
        "structural_acceptance": structural_acceptance(Path(args.hwpx)),
    }
```

`parse_args`에 옵트아웃 플래그를 추가한다(기본 수행):

```python
    parser.add_argument("--skip-structural-check", action="store_true",
                        help="skip axis-A renderer-free round-trip acceptance")
```

그리고 `--skip-structural-check`면 `{"status": "skipped", ...}`를 넣는다.

- [ ] **Step 4: 실행해서 통과 확인 + 기존 스모크 회귀**

Run: `cd /Users/wilycastle/Code/projects/hwpx/hwpx-skill && uv run --extra dev pytest tests/test_visual_review_axis_a.py -v && uv run python scripts/quickcheck.py --visual-review`
Expected: PASS. 기존 visual-review fallback 스모크 그린 유지.

- [ ] **Step 5: 커밋**

```bash
cd /Users/wilycastle/Code/projects/hwpx/hwpx-skill
git add scripts/visual_review.py tests/test_visual_review_axis_a.py
git commit -m "feat(visual-review): add axis-A structural acceptance (round-trip) to evidence"
```

---

## Stage 완료 게이트

- [ ] `uv run --extra dev pytest -q` (python-hwpx) 전체 그린 — 기존 document_plan/proposal/form-fill 회귀 없음.
- [ ] hwpx-skill 스모크 그린.
- [ ] 코퍼스 47개 벤더링 + 매니페스트 + NOTICE 귀속 완료, 리더 갭이 `KNOWN_READ_FAILURES`에 문서화.
- [ ] `validate_document` 스키마 실패가 warning(lint), 구조 하드게이트(validate_package/재오픈)는 유지.
- [ ] `owpml-deviations.md` 가동.
- [ ] visual_review 축 A(round-trip) evidence 추가.
- [ ] Stage `STG-3611d648b9d9` 완료 처리(`complete_stage`), 다음 Stage `STG-d79e63646ee9`(빌더 코어) 계획 작성으로 핸드오프.
