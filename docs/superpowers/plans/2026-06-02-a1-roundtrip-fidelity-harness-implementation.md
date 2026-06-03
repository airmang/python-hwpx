# 강화 A1 — 라운드트립 충실도 하니스 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** hwpxlib 코퍼스 47개를 `open→to_bytes→reopen` 한 뒤 구조 유실을 측정하는 진단 하니스를 만들어, 무엇이 라운드트립에서 사라지는지 데이터로 드러낸다(이후 C1 커버리지 우선순위의 근거).

**Architecture:** 순수 진단 — 코어 동작을 바꾸지 않는다. `roundtrip_diff.py`가 요소 local-name 카운트 기반 구조 diff를 산출하고, 테스트가 47개에 대해 재오픈을 하드 단언 + 유실 인벤토리를 집계한다.

**Tech Stack:** Python 3.10+, stdlib(`xml.etree.ElementTree`, `collections.Counter`, json), pytest, 기존 `HwpxDocument`. `uv run --extra dev pytest`.

**개발 환경:** python-hwpx 루트 `/Users/wilycastle/Code/projects/hwpx/python-hwpx`. 작업 브랜치: `feat/s013-builder-core`(또는 거기서 분기한 `feat/s021-roundtrip-harness`). 테스트: `uv run --extra dev pytest -q`.

**검증된 사실 (현재 소스 기준, 시작 전 재확인):**
- `HwpxDocument.open(source)`는 path/bytes/stream 수용, `HwpxDocument.to_bytes()`는 직렬화 bytes 반환(`src/hwpx/document.py`). `doc.oxml.headers`/`doc.oxml.sections`의 각 part는 `.part_name`과 `.element`(ElementTree Element)를 가진다(validator.py:85-96의 `_iter_parts`가 이 접근을 사용).
- 코퍼스: `tests/fixtures/hwpxlib_corpus/*.hwpx` 47개 + `manifest.json`(`samples[].file`). S-012 산출물.
- 기존 코퍼스 스모크 `tests/test_hwpxlib_corpus_read.py`는 open+export_text만 — 이 Stage는 그 위에 구조 보존 측정을 더한다(중복 아님).

## Stage Context
- Wily Stage: `STG-29539fd1eb76` (S-021). 선행: `STG-3611d648b9d9`(S-012, done).
- 설계 근거: `docs/2026-06-02-hwpx-builder-design.md` §8(오라클), 충실도 격차 W3.

## File Structure
- Create: `src/hwpx/tools/roundtrip_diff.py` — 구조 diff + 코퍼스 집계.
- Create: `tests/test_roundtrip_fidelity.py` — 47개 재오픈 하드 단언 + 유실 인벤토리.
- Generated (커밋 금지): `work/s021-roundtrip/roundtrip_inventory.json`.

## Execution Protocol
SPIKE로 diff 의미를 먼저 고정한 뒤 TDD. 각 단계 narrow→full pytest→commit.

### Task 1: SPIKE — diff 의미 고정
- [ ] **SPIKE:** 코퍼스 샘플 2~3개(예: `reader_writer__SimpleTable.hwpx`, `reader_writer__SimpleEquation.hwpx`)를 `open→to_bytes→reopen` 한 뒤, before/after의 전체 요소 local-name 카운트(`Counter`)를 출력해 본다. 확인할 것: ① 네임스페이스 prefix·ID 재번호·요소 순서 차이는 local-name 카운트에 영향 없음(= false loss 아님), ② 진짜 유실(before에 있고 after에 없는 local-name)이 보이는지. 관찰 결과(어떤 local-name이 줄어드는지)를 테스트 주석에 고정한다.

### Task 2: roundtrip_diff 헬퍼
**Files:** Create `src/hwpx/tools/roundtrip_diff.py`
- [ ] **RED:** `tests/test_roundtrip_fidelity.py`에 단위 테스트 작성:

```python
from hwpx.tools.roundtrip_diff import roundtrip_report

def test_roundtrip_report_shape(tmp_path):
    from hwpx.document import HwpxDocument
    doc = HwpxDocument.new(); doc.add_paragraph("본문")
    p = tmp_path / "d.hwpx"; doc.save_to_path(p)
    rep = roundtrip_report(p)
    assert rep["reopened"] is True
    assert isinstance(rep["lost_elements"], dict)   # {local_name: count_lost}
    assert isinstance(rep["added_elements"], dict)
    assert "p" in rep["before_counts"]
```

- [ ] **RED 확인:** `uv run --extra dev pytest tests/test_roundtrip_fidelity.py::test_roundtrip_report_shape -v` → FAIL(module 없음).
- [ ] **GREEN:** 구현:

```python
# src/hwpx/tools/roundtrip_diff.py
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any
from hwpx.document import HwpxDocument

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]

def _doc_local_counts(doc: HwpxDocument) -> Counter:
    counts: Counter = Counter()
    for part in list(doc.oxml.headers) + list(doc.oxml.sections):
        for el in part.element.iter():
            counts[_local(el.tag)] += 1
    return counts

def roundtrip_report(source: str | Path | bytes) -> dict[str, Any]:
    before = HwpxDocument.open(source)
    before_counts = _doc_local_counts(before)
    data = before.to_bytes()
    after = HwpxDocument.open(data)
    after_counts = _doc_local_counts(after)
    lost = {k: before_counts[k] - after_counts.get(k, 0)
            for k in before_counts if before_counts[k] > after_counts.get(k, 0)}
    added = {k: after_counts[k] - before_counts.get(k, 0)
             for k in after_counts if after_counts[k] > before_counts.get(k, 0)}
    return {
        "reopened": True,
        "before_counts": dict(before_counts),
        "after_counts": dict(after_counts),
        "lost_elements": lost,
        "added_elements": added,
    }
```

- [ ] **PASS + Commit:** `feat(tools): add roundtrip structural-diff helper`

### Task 3: 코퍼스 47 충실도 테스트 + 유실 인벤토리
**Files:** `tests/test_roundtrip_fidelity.py`
- [ ] **RED:** manifest 기반 parametrize 테스트 + 집계:

```python
import json
from collections import Counter
from pathlib import Path
import pytest
from hwpx.tools.roundtrip_diff import roundtrip_report

CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"
SAMPLES = [s["file"] for s in json.loads((CORPUS / "manifest.json").read_text("utf-8"))["samples"]]

# 재오픈 자체가 실패하는 샘플(현재). 사유 명기, silent skip 금지.
KNOWN_REOPEN_FAILURES: dict[str, str] = {}

@pytest.mark.parametrize("sample", SAMPLES)
def test_corpus_sample_roundtrips(sample):
    if sample in KNOWN_REOPEN_FAILURES:
        pytest.xfail(KNOWN_REOPEN_FAILURES[sample])
    rep = roundtrip_report(CORPUS / sample)
    assert rep["reopened"] is True   # 하드 게이트: 재오픈은 반드시 성공

def test_emit_loss_inventory(tmp_path):
    agg: Counter = Counter()
    per_sample = {}
    for s in SAMPLES:
        if s in KNOWN_REOPEN_FAILURES:
            continue
        rep = roundtrip_report(CORPUS / s)
        if rep["lost_elements"]:
            per_sample[s] = rep["lost_elements"]
            agg.update(rep["lost_elements"])
    out = Path("work/s021-roundtrip"); out.mkdir(parents=True, exist_ok=True)
    (out / "roundtrip_inventory.json").write_text(
        json.dumps({"aggregate_lost_by_local_name": dict(agg.most_common()),
                    "per_sample": per_sample}, ensure_ascii=False, indent=2), "utf-8")
    print("LOSS INVENTORY:", dict(agg.most_common(20)))
    # 진단 테스트 — 유실이 있어도 실패시키지 않되, 인벤토리를 남긴다.
    assert (out / "roundtrip_inventory.json").exists()
```

- [ ] **RED 확인 → GREEN:** 실행. **재오픈 실패 샘플이 있으면** `KNOWN_REOPEN_FAILURES`에 사유와 함께 등록(그 자체가 W-급 발견 — 보고). 통과시킨다.
- [ ] **PASS:** `uv run --extra dev pytest tests/test_roundtrip_fidelity.py -v` + 전체 `uv run --extra dev pytest -q` 회귀 없음.
- [ ] **Commit:** `test: corpus roundtrip fidelity harness + loss inventory`

## Stage 완료 게이트
- [ ] `roundtrip_diff.roundtrip_report`가 before/after local-name 카운트와 lost/added를 반환.
- [ ] 47개 전부 재오픈 하드 단언(실패는 `KNOWN_REOPEN_FAILURES`에 분류·보고).
- [ ] `work/s021-roundtrip/roundtrip_inventory.json`에 **요소 local-name별 유실 집계**가 산출(= C1 우선순위 입력).
- [ ] 전체 pytest 그린, 회귀 없음. 코어 동작 변경 없음(순수 진단).
- [ ] 완료 시 유실 인벤토리 상위 항목을 보고(다음 C1 스코프 결정용).
