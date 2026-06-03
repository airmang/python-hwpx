# 강화 C1 — 커버리지 1차 승격 (GenericElement → 1급 모델) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 현재 GenericElement로만 들어오는 고빈도 body 요소를 1급 데이터클래스+파서로 승격해 읽기/편집 충실도를 높인다. 승격 대상은 C1 자체가 생성하는 "미모델링 body 요소 빈도 인벤토리"로 데이터 기반 결정한다.

**Architecture:** `_ELEMENT_FACTORY`에 전용 파서를 추가해 대상 요소를 GenericElement 대신 전용 모델로 읽는다. **불변식: 승격은 라운드트립 무손실을 절대 깨지 않는다** — 현재 GenericElement는 미지 요소를 통째 보존하므로(A1: 유실 0), 새 모델은 *최소한 동등하게* 보존해야 한다(필요 시 미지 자식/속성을 보존하는 typed-preserving wrapper).

**Tech Stack:** Python 3.10+, lxml/ElementTree, pytest, A1 `roundtrip_diff`(회귀 가드), S-012 코퍼스. `uv run --extra dev pytest`.

**개발 환경:** 루트 `/Users/wilycastle/Code/projects/hwpx/python-hwpx`. 브랜치: **`feat/builder-integration`에서 `feat/s025-coverage` 분기**(A1 harness 포함). 테스트: `uv run --extra dev pytest -q`.

**Legal boundary (clean-room):** `hancom-io/hwpx-owpml-model`(공식 .h)·hwpxlib는 **요소 구조·동작 관찰만**, 코드/구조 포팅 금지. 독립 재구현. 출처는 `NOTICE`에 기록.

**검증된 사실 (현재 소스 기준, SPIKE에서 재확인):**
- `src/hwpx/oxml/parser.py`의 `_ELEMENT_FACTORY`는 head/sec/p/run/t(base) + `ctrl`(parse_control_element)·`tbl`(parse_table_element)·`body.INLINE_OBJECT_NAMES`(parse_inline_object_element)·track-change marks만 등록. 그 외 local-name은 GenericElement로 fallback.
- A1(`src/hwpx/tools/roundtrip_diff.py`, 통합 완료)이 open→to_bytes→reopen 요소 local-name 유실을 측정. 현재 코퍼스 47개 유실 0(무손실 기준선) — **C1은 이 0을 깨면 안 된다**.
- 예비 후보(검증 전, C1 Task 1이 확정): MCE 호환 래핑(switch/case/default, 46개 문서), 도형 기하/그리기(scaMatrix·rotMatrix·transMatrix·flip 등 25개 문서; line/rect/ellipse/curve/polygon/connectLine), equation/chart/ole/video/textart/form control.

## Stage Context
- Wily Stage: `STG-e9363f37844a` (S-025). 선행: A1(`STG-29539fd1eb76`)·A2(`STG-af86103d6acd`) 통합 완료.

## File Structure
- Create: `src/hwpx/tools/generic_inventory.py` — 엔진 GenericElement 분류로 미모델링 body 요소 빈도 집계.
- Modify: `src/hwpx/oxml/body.py`, `src/hwpx/oxml/parser.py` — 승격 요소 전용 파서/데이터클래스 + 등록.
- Modify: `src/hwpx/oxml/document.py` — (필요 시) 승격 요소 접근 wrapper.
- Modify: `tests/test_roundtrip_fidelity.py` — 회귀 가드(무손실 유지) + 승격 검증.
- Create: `tests/test_coverage_promotion.py` — 요소별 구조 대조 + 보존.
- Modify: `NOTICE` — owpml-model/hwpxlib 참조 귀속.

## Execution Protocol
Task 1(인벤토리)로 대상을 데이터 확정 → 각 대상 SPIKE(구조 고정)→RED→GREEN. 각 Task narrow→full pytest→commit. batch 금지. **매 승격마다 A1 하니스로 무손실 회귀 확인.**

### Task 1: 미모델링 body 요소 빈도 인벤토리 (대상 데이터 확정)
**Files:** `src/hwpx/tools/generic_inventory.py`, `tests/test_coverage_promotion.py`
- [ ] **RED:** `generic_inventory.scan_corpus(corpus_dir)`가 각 .hwpx를 `HwpxDocument.open` 후 **엔진이 GenericElement로 분류한 body 요소**를 tag별 빈도·등장문서수로 집계한 dict를 반환하는 테스트(헤더 mapping-table 내부요소 제외 — body/run 하위만).
- [ ] **RED 확인 → GREEN:** 엔진의 GenericElement 인스턴스를 순회·집계 구현(파서가 GenericElement로 떨군 요소를 식별). 코퍼스 47 스캔 결과를 `work/s025-coverage/generic_inventory.json`으로 출력하고, 상위 N개를 로그로 남긴다.
- [ ] **결정:** 상위 빈도 + 모델링 가능성 기준으로 **승격 대상 ≥3종**을 고른다(복잡·불투명 내부 요소는 typed-preserving wrapper로). 선택과 근거를 이 Task에 기록·보고.
- [ ] **PASS + Commit:** `feat(tools): generic-element coverage inventory`

### Task 2..N: 대상 요소별 승격 (각 1 Task, ≥3회 반복)
**Files:** `oxml/body.py`, `oxml/parser.py`, (필요 시 `oxml/document.py`), `tests/test_coverage_promotion.py`, `tests/test_roundtrip_fidelity.py`, `NOTICE`
- [ ] **SPIKE(요소별):** 해당 요소의 정본 구조를 hancom-io/hwpx-owpml-model `.h` + 대응 hwpxlib 샘플 출력으로 고정(요소/속성/자식). 코드 미복사. 미지 자식은 보존 대상으로 식별.
- [ ] **RED:** ① 대응 hwpxlib 샘플을 열어 해당 요소가 GenericElement가 아니라 **전용 모델**로 읽힘을 단언(속성/자식 접근). ② open→save→reopen에서 그 요소가 **무손실 보존**(라운드트립 구조 동치)됨을 단언. ③ A1 `roundtrip_report`로 코퍼스 무손실이 회귀 없음을 단언.
- [ ] **RED 확인 → GREEN:** 전용 데이터클래스 + 파서 구현, `_ELEMENT_FACTORY` 등록. 모델은 알려진 속성/자식을 노출하되 **미지 자식/속성을 보존**(typed-preserving)해 직렬화 시 원본 복원. NOTICE에 출처 추가.
- [ ] **PASS:** `uv run --extra dev pytest tests/test_coverage_promotion.py tests/test_roundtrip_fidelity.py tests/test_oxml_parsing.py -v` + 전체.
- [ ] **Commit:** `feat(oxml): promote <element> to first-class model`

## Stage 완료 게이트
- [ ] `generic_inventory`가 코퍼스 47의 미모델링 body 요소를 tag별로 집계, 승격 대상을 데이터로 지정(인벤토리 산출물).
- [ ] 상위 미모델링 요소 ≥3종이 전용 모델+파서로 승격, 대응 hwpxlib 샘플에서 전용 모델로 읽힘.
- [ ] **무손실 불변식 유지**: A1 하니스 재실행 시 코퍼스 유실 여전히 0(승격이 보존을 깨지 않음), 승격 요소 open→save→reopen 구조 동치.
- [ ] owpml-model/hwpxlib 참조가 NOTICE에 기록(clean-room, 코드 미복사).
- [ ] `uv run --extra dev pytest -q` 전체 그린.
