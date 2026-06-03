# 강화 A2 — 네임스페이스 다중수용·보존 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 읽기는 2011/2016/2024 OWPML 네임스페이스를 모두 수용하고, 쓰기는 입력 문서의 ns를 보존하도록(하드코딩 2011 강제 제거) 코어 ns 처리를 중앙화·강화한다.

**Architecture:** ns 상수/해석을 `oxml/namespaces.py`로 중앙화하고, 파싱은 ns-무관(local-name) 또는 다중 ns prefix로, 직렬화는 원본 ns를 보존한다. de-facto 우선 — 현행 ns는 `hancom-io/hwpx-owpml-model`(공식)과 실제 한컴/코퍼스 문서로 확인, 공식 스키마는 lint.

**Tech Stack:** Python 3.10+, lxml/ElementTree, pytest, 기존 `HwpxDocument`/`HwpxPackage`. `uv run --extra dev pytest`.

**개발 환경:** 루트 `/Users/wilycastle/Code/projects/hwpx/python-hwpx`. 브랜치: 현재 빌더 base에서 `feat/s022-namespace` 분기. 테스트: `uv run --extra dev pytest -q`.

**Legal boundary (clean-room):** owpml-model/hwpxlib는 **동작·ns 문자열 관찰만**, 코드 미복사.

**검증된 사실 (현재 소스 기준, SPIKE에서 재확인):**
- 2011 ns 하드코딩 분산 지점: `src/hwpx/document.py:45-52`(`ET.register_namespace` + `_HP_NS`/`_HH_NS` 등), `src/hwpx/oxml/body.py:14`(`_DEFAULT_HP_NS`), `src/hwpx/tools/exporter.py:25`, `src/hwpx/tools/template_analyzer.py:16`.
- `src/hwpx/tools/text_extractor.py:32-37`은 이미 다중 prefix(hp=2011, hp10=2016, hs/hc/ha/hh) NS dict를 가짐 — 읽기 다중수용의 부분 선례.
- `src/hwpx/oxml/namespaces.py`가 이미 존재(중앙화 대상). SPIKE에서 현재 내용·사용처 확인.
- `src/hwpx/oxml/parser.py`의 `_ELEMENT_FACTORY`는 local-name 기반(`local_name(node)`) — 파싱은 일부 이미 ns-무관.

## Stage Context
- Wily Stage: `STG-af86103d6acd` (S-022). 선행: `STG-3611d648b9d9`(S-012, done). A1·B1과 병렬(파일 분리).
- 격차: W2. 설계 §8.2(ns 정합), `docs/owpml-deviations.md`.

## File Structure
- Modify: `src/hwpx/oxml/namespaces.py` — 중앙 ns 레지스트리(2011/2016/2024) + 헬퍼.
- Modify: `src/hwpx/document.py`, `src/hwpx/oxml/body.py`, `src/hwpx/tools/text_extractor.py` — 하드코딩 제거, namespaces.py 사용.
- Modify: `docs/owpml-deviations.md` — ns 정합 전략을 실제 구현으로 갱신.
- Create: `tests/test_namespace_handling.py`.

## Execution Protocol
SPIKE로 현 ns 처리·코퍼스 실제 ns를 고정한 뒤 TDD. 각 Task narrow→full pytest→commit. batch 금지.

### Task 1: SPIKE — 현 ns 처리 + 코퍼스 실제 ns 고정
- [ ] **SPIKE:** ① `oxml/namespaces.py` 현재 내용과 import 사용처를 읽는다. ② 하드코딩 4개 지점(검증된 사실)이 정확한지 확인. ③ 코퍼스 47개 각 `Contents/section0.xml`·`header.xml`의 루트 `xmlns:*` 선언을 grep/파싱해 **실제로 어떤 ns가 쓰이는지**(2011 vs 2016 vs 2024) 표로 만든다. ④ (가능하면) `hancom-io/hwpx-owpml-model`의 현행 ns 문자열을 확인. 결과(현행 한컴 ns + 코퍼스 ns 분포)를 이 Task에 주석으로 고정. 이 분포가 "신규 생성 ns" 선택의 근거.

### Task 2: 중앙 ns 레지스트리 + 다중수용 읽기
**Files:** `oxml/namespaces.py`, `tests/test_namespace_handling.py`
- [ ] **RED:** namespaces.py가 2011/2016/2024 각 영역(paragraph/section/core/head 등)의 ns URI 집합과, `resolve(localname)`·prefix 매핑·`detect_namespaces(element)` 헬퍼를 노출하도록 테스트. 2016/2024 ns를 쓰는 합성(또는 코퍼스) 문서를 `HwpxDocument.open()`이 파싱하는 테스트.
- [ ] **RED 확인 → GREEN:** namespaces.py에 다중 ns 레지스트리 추가. 파싱 경로가 local-name 또는 다중 ns를 수용하도록(이미 local-name 기반인 parser는 유지, ns-고정 조회가 있으면 다중 허용). text_extractor의 NS dict는 namespaces.py를 재사용.
- [ ] **PASS + Commit:** `feat(oxml): centralize namespaces and accept 2011/2016/2024 on read`

### Task 3: 쓰기 ns 보존
**Files:** `document.py`, `oxml/body.py`, `tests/test_namespace_handling.py`
- [ ] **RED:** 기존 2011 ns 문서를 열어 `to_bytes()` 한 결과의 ns가 **원본과 동일하게 보존**됨을 단언(루트 `xmlns:*` 또는 요소 tag ns 비교). 하드코딩 2011 강제가 없음을 증명.
- [ ] **RED 확인 → GREEN:** `document.py`/`body.py`의 하드코딩 2011 리터럴을 namespaces.py 기반 + **문서에서 감지한 ns 보존**으로 교체. 신규 `HwpxDocument.new()` 생성 ns는 SPIKE에서 정한 현행 ns(기본 2011 유지가 안전하면 그대로, 단 중앙 상수 경유).
- [ ] **PASS + Commit:** `feat(oxml): preserve source namespace on write`

### Task 4: deviations 레지스트리 갱신
- [ ] `docs/owpml-deviations.md`의 ns 정합 항목을 실제 구현 전략(읽기 다중수용/쓰기 보존/신규 생성 ns)으로 갱신. Commit `docs: update namespace reconciliation strategy`.

## Stage 완료 게이트
- [ ] ns 상수가 namespaces.py로 중앙화, 하드코딩 2011 분산 제거.
- [ ] 2016/2024 ns 입력이 `HwpxDocument.open()`으로 파싱됨(테스트).
- [ ] 2011 문서 open→to_bytes 시 ns 보존(구조/ns diff 단언).
- [ ] deviations.md ns 항목 실제 전략으로 갱신.
- [ ] `uv run --extra dev pytest -q` 전체 그린(기존 텍스트추출/oxml/round-trip 회귀 없음).
