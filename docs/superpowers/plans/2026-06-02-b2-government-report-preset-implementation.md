# 강화 B2 — government_report 빌더 프리셋 + 보고서 유틸 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 차단된 범정부오피스 Phase 1+2를 좁은 authoring.py 경로가 아니라 S-013/B1 빌더 위로 재루팅한다. (1) `government_report`를 빌더 스타일 프리셋으로(gov heading level별·강조·callout, 한국 공문 불릿 □/○/-/※/*), (2) `report_utils` 순수 계산기 + 텍스트 내 `{{ }}` computed field 치환(eval 금지).

**Architecture:** 빌더는 의도 중심 노드(Heading level별·Bullet 다단계·Run 서식)를 이미 지원하므로, government_report는 그 위에 **기본 스타일 토큰 묶음(preset)** 을 얹는 얇은 레이어다. report_utils는 HWPX와 분리된 순수 함수 모듈. computed field는 작은 safe parser로 치환(eval 금지).

**Tech Stack:** Python 3.10+, pytest, S-013 `hwpx.builder` + B1 plan v2. `uv run --extra dev pytest`.

**개발 환경:** 루트 `/Users/wilycastle/Code/projects/hwpx/python-hwpx`. 브랜치: **`feat/builder-integration`(A1+A2+B1 통합본)에서 `feat/s024-gov-preset` 분기**. 테스트: `uv run --extra dev pytest -q`.

**Legal boundary:** 범정부오피스는 비공개 Windows exe — 코드 미참조, 기능/워크플로만. 독립 구현.

**검증된 사실 (현재 소스 기준, SPIKE에서 재확인):**
- S-013 빌더(`src/hwpx/builder/core.py`)는 `Heading(level=)`·`Bullet(level=,items=)`·`Run(bold/italic/underline/color/font/size)`을 노드로 지원하고 facade-only lower한다. **현재 "프리셋" 개념은 없다** — government_report는 빌더에 추가할 첫 프리셋.
- B1이 `create_document_from_plan`을 빌더 lower로 재구현(plan v2). government_report는 빌더 코드 경로와 plan v2 양쪽에서 동작해야 한다.
- report_utils 함수 스펙(구 gov P2): `format_krw_hangul`, `format_number_commas`, `calculate_age`, `format_delta`(음수 기본 △), `format_delta_percent`, `calculate_ratios`(0 나눔 명시오류/N-A), `normalize_korean_date`('2026. 6. 2.'/'2026-06-02'/'2026/06/02').
- computed field delimiter는 `{{ ... }}` (잔여 마커 검사와 동일 delimiter). bare `{...}`는 아님.

## Stage Context
- Wily Stage: `STG-3ad9a878c853` (S-024). 선행: B1(`STG-b2f62757b415`, 통합 완료). 구 gov P1+P2(S-014/S-015, blocked) 흡수.

## File Structure
- Modify: `src/hwpx/builder/core.py` — government_report 프리셋(스타일 토큰 묶음) + 한국 공문 불릿.
- Create: `src/hwpx/tools/report_utils.py` — 순수 계산기.
- Modify: `src/hwpx/authoring.py` 또는 builder — `{{ }}` computed field 치환(텍스트 lower 시점).
- Create: `tests/test_government_report_preset.py`, `tests/test_report_utils.py`, `tests/test_document_plan_computed_fields.py`.

## Execution Protocol
각 Task RED→narrow FAIL→GREEN→narrow PASS→`uv run --extra dev pytest -q` 전체 PASS→범위 파일만 commit. batch 금지.

### Task 1: SPIKE — 빌더 스타일 산출 경로 + 프리셋 훅 결정
- [ ] **SPIKE:** `builder/core.py`에서 Heading/Run/Bullet이 스타일(charPr/불릿 prefix)을 어떻게 산출하는지 읽고, "프리셋"을 어디에 끼울지 결정한다(예: `Document(preset="government_report")` → 노드 lower 시 기본 토큰 주입). 구 gov P1(S-014, blocked) acceptance의 토큰/불릿 스펙을 참고. 결정한 프리셋 훅 지점을 이 Task에 주석으로 고정.

### Task 2: report_utils 순수 계산기
**Files:** `src/hwpx/tools/report_utils.py`, `tests/test_report_utils.py`
- [ ] **RED:** 각 함수 + 엣지케이스 테스트:

```python
from hwpx.tools.report_utils import (
    format_krw_hangul, format_number_commas, calculate_age,
    format_delta, format_delta_percent, calculate_ratios, normalize_korean_date,
)
def test_krw_hangul_zero(): assert "영" in format_krw_hangul(0) or format_krw_hangul(0) == "0원"
def test_commas(): assert format_number_commas(1234567) == "1,234,567"
def test_delta_negative_triangle(): assert format_delta(-5).startswith("△")
def test_ratio_zero_division_explicit():
    import pytest
    with pytest.raises(Exception):
        calculate_ratios(1, 0)          # 또는 'N/A' 반환 — 구현이 명시오류/NA 중 택1, 테스트도 일치
def test_date_polymorphic():
    for s in ("2026. 6. 2.", "2026-06-02", "2026/06/02"):
        assert normalize_korean_date(s) == "2026-06-02"
```

- [ ] **GREEN:** 순수 함수 구현(HWPX 의존 0). 0 나눔은 명시 오류 또는 'N/A'로 — 테스트와 일치시킨다.
- [ ] **PASS + Commit:** `feat(tools): add pure Korean report calculators`

### Task 3: `{{ }}` computed field 치환 (safe parser, eval 금지)
**Files:** `authoring.py`(또는 builder lower), `tests/test_document_plan_computed_fields.py`
- [ ] **RED:** plan/빌더 텍스트의 `{{ krw_hangul(5000000) }}`·`{{ commas(1234567) }}` 등이 최종 렌더에서 값으로 치환됨을 단언. 알 수 없는 함수 → validation error. 렌더 후 살아남은 `{{ }}` → 잔여 마커로 검출.
- [ ] **GREEN:** 작은 safe parser(함수명 화이트리스트 + 인자 파싱, `eval`/`exec` 금지)로 report_utils 함수 디스패치. 텍스트 lower 시점에 치환.
- [ ] **PASS + Commit:** `feat(authoring): computed {{ }} fields via safe parser`

### Task 4: government_report 빌더 프리셋 + 차별화 가드
**Files:** `builder/core.py`, `tests/test_government_report_preset.py`
- [ ] **RED:** ① 동일 입력으로 만든 government_report vs 기본 프리셋 문서의 run-style이 실제로 다름(차별화 가드, 예: gov heading underline 유무). ② 한국 공문 불릿(default→•, square→□, circle→○, dash→-, note→※, star→*)이 빌더 노드로 렌더되고 reopen으로 확인. ③ plan v2 `preset:"government_report"` 경로도 동일.
- [ ] **GREEN:** Task 1 SPIKE에서 정한 훅에 government_report 토큰 묶음(gov heading level별·강조·callout) + 불릿 스타일 매핑 구현.
- [ ] **PASS:** `uv run --extra dev pytest tests/test_government_report_preset.py tests/test_report_utils.py tests/test_document_plan_computed_fields.py tests/test_document_plan.py tests/test_builder_plan_v2.py -v` + 전체 그린.
- [ ] **Commit:** `feat(builder): government_report style preset`

## Stage 완료 게이트
- [ ] government_report 프리셋이 빌더 + plan v2 양쪽에서 동작, 기본 프리셋과 run-style 차별화(가드 테스트).
- [ ] 한국 공문 불릿(□/○/-/※/*) 빌더 렌더 + reopen 확인.
- [ ] report_utils 7개 함수 순수 구현 + 엣지케이스(0원·음수 △·0나눔·날짜 다형) 통과.
- [ ] `{{ }}` computed field 치환(eval 미사용), unknown→error, 잔여→마커 검출.
- [ ] `uv run --extra dev pytest -q` 전체 그린(기본 프리셋·plan v1/v2 회귀 없음).
