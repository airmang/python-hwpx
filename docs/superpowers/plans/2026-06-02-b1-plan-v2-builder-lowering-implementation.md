# 강화 B1 — document_plan v2 = 빌더 lowering + TOC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** `create_document_from_plan`을 plan→`hwpx.builder` 노드 lower로 재구현해 코드 경로와 JSON(plan) 경로가 한 코어(빌더)를 공유하게 한다. v1은 v2의 부분집합으로 하위호환을 유지하고, plan v2가 빌더 전 기능을 표현하며, TOC 노드를 추가한다.

**Architecture:** plan(JSON dict)을 빌더 노드 트리로 정규화(lower)하는 단일 변환을 도입한다. 기존 `_render_block`(좁은 authoring 경로)을 빌더로 위임해 일반화한다. v1 블록(heading/paragraph/bullets/table/page_break/memo)은 빌더 노드로 1:1 매핑, v2는 거기에 rich run·header/footer·page number·multilevel list·table merge/shading/width·image·TOC를 추가.

**Tech Stack:** Python 3.10+, pytest, 기존 `hwpx.builder`(S-013), `authoring.py`, `HwpxDocument`. `uv run --extra dev pytest`.

**개발 환경:** 루트 `/Users/wilycastle/Code/projects/hwpx/python-hwpx`. 브랜치: 현재 빌더 base에서 `feat/s023-plan-v2` 분기. 테스트: `uv run --extra dev pytest -q`.

**검증된 사실 (현재 소스 기준, SPIKE에서 재확인):**
- `hwpx.builder`(S-013)는 `Document/Section/Paragraph/Run/Heading/Bullet/NumberedList/Table/Image/Header/Footer/PageNumber/PageBreak/Metadata/PageSize/Margins`를 공개하고 facade-only로 lower한다(`src/hwpx/builder/core.py`).
- `authoring.py`의 document_plan: v1 블록 = heading/paragraph/bullets/table/page_break/memo. `_normalize_block`은 bullets에서 style을 버리고 table에서 caption/columns/rows만 유지. `_render_block`(약 :936-976)은 paragraph가 `tokens.get(style, tokens["body"])`, heading은 level 무시 `tokens["heading"]`, bullets는 `f"• {item}"` 하드코딩(govoffice 플랜 기록). 이것이 빌더 위임으로 일반화할 대상.
- `create_document_from_plan`/`validate_document_plan`은 `authoring.py`의 공개 API이며 proposal/operating-plan/MCP가 소비(`hwpx-mcp-server`). 하위호환 필수.
- 기존 회귀 스위트: `tests/test_document_plan.py`, `test_proposal_preset.py`.

## Stage Context
- Wily Stage: `STG-b2f62757b415` (S-023). 선행: `STG-d79e63646ee9`(S-013, done). A1·A2와 병렬(authoring.py/builder만 건드림 — A2의 document.py/oxml와 대체로 분리).
- 격차/방향: 설계 §5·§11 Phase 2(plan v2 + 빌더). TOC는 빌더 Phase 2 항목.

## File Structure
- Modify: `src/hwpx/authoring.py` — `create_document_from_plan`을 plan→빌더 lower로; `_render_block` 위임. v2 블록 정규화/검증.
- Modify: `src/hwpx/builder/core.py` — TOC 노드 추가, plan-lower에 필요한 보조.
- Create: `tests/test_builder_plan_v2.py` — v2 표현·코드/JSON parity·TOC.
- Modify (회귀): `tests/test_document_plan.py`만 필요 시 보강(기존 단언은 유지).

## Execution Protocol
SPIKE로 현 plan 처리 흐름을 고정한 뒤 TDD. 각 Task narrow→full pytest→commit. batch 금지.

### Task 1: SPIKE — v1 블록→빌더 노드 매핑 고정
- [ ] **SPIKE:** `authoring.py`의 `create_document_from_plan`·`_normalize_block`·`_render_block`·블록 검증 경로를 정독해, v1 블록 6종(heading/paragraph/bullets/table/page_break/memo) 각각이 어떤 빌더 노드로 lower되는지 매핑표를 이 Task에 고정한다. 기존 v1 출력의 불변 지점(테스트가 단언하는 텍스트/구조)을 식별해 parity 기준선으로 삼는다.

### Task 2: v1 plan을 빌더로 lower (하위호환)
**Files:** `authoring.py`, `tests/test_document_plan.py`(회귀만)
- [ ] **RED:** 기존 `tests/test_document_plan.py` 전체가 빌더-lower 경로에서도 통과해야 함을 기준선으로(먼저 실행해 GREEN 확인 → 리팩터 후에도 GREEN). 신규로 "v1 plan을 빌더 lower로 생성한 결과가 기존과 구조/텍스트 parity"임을 단언하는 테스트 추가.
- [ ] **GREEN:** `create_document_from_plan` 내부를 plan→빌더 노드 정규화 + `Document(...).lower()` 경유로 재구현. `_render_block`의 좁은 분기를 빌더 노드(Heading level별·Bullet 다단계·Run)로 위임. 기존 공개 시그니처/반환 계약 유지.
- [ ] **PASS:** `uv run --extra dev pytest tests/test_document_plan.py tests/test_proposal_preset.py -v` + 전체 그린.
- [ ] **Commit:** `refactor(authoring): lower document_plan v1 through builder (backward-compatible)`

### Task 3: plan v2 블록 + 코드/JSON parity
**Files:** `authoring.py`, `tests/test_builder_plan_v2.py`
- [ ] **RED:** v2 plan(rich run 서식·header/footer·page_number·multilevel list·table merge/shading/width·image)을 정규화·검증·생성하는 테스트. 동일 내용을 (a) 빌더 코드와 (b) plan v2 JSON으로 만들면 출력이 동치임을 단언하는 parity 테스트.
- [ ] **GREEN:** v2 블록 정규화/검증을 추가하고 빌더 노드로 lower. v1은 v2의 부분집합으로 계속 동작.
- [ ] **PASS + Commit:** `feat(authoring): document_plan v2 expressing full builder surface`

### Task 4: TOC 노드
**Files:** `builder/core.py`, `authoring.py`, `tests/test_builder_plan_v2.py`
- [ ] **SPIKE:** TOC 구조는 hwpxlib 코퍼스에 TOC 샘플이 있으면 그 구조를, 없으면 최소 TOC 필드 구조를 owpml-model로 확인해 고정(clean-room). 코퍼스에 적합 샘플이 없으면 그 사실과 범위(최소 TOC 또는 후속 연기)를 보고.
- [ ] **RED → GREEN:** 빌더 `Toc()` 노드 + plan v2 `{"type":"toc"}` lower. reopen·구조 검증.
- [ ] **PASS + Commit:** `feat(builder): add TOC node`

## Stage 완료 게이트
- [ ] 기존 v1 plan이 동일 결과로 작동(test_document_plan/proposal 회귀 그린, parity).
- [ ] plan v2가 빌더 전 기능 표현·생성.
- [ ] 코드 빌더 vs plan v2 JSON 출력 동치 parity 테스트 존재.
- [ ] TOC 노드 생성·reopen·구조 검증(또는 적합 샘플 부재 시 범위 보고).
- [ ] create_document_from_plan의 기존 호출부(proposal/operating-plan/MCP) 그린.
- [ ] `uv run --extra dev pytest -q` 전체 그린.
