# HWPX Stack Operating Plan v1

이 문서는 `python-hwpx`, `hwpx-mcp-server`, `hwpx-skill`을 하나의 스택으로 보고 지속 개선하기 위한 운영 기준이다.

## 1. 범위

대상 레포:
- `.` (`python-hwpx` 현재 레포)
- `../hwpx-mcp-server`
- `../hwpx-skill`

역할:
- `python-hwpx`: 코어 문서 엔진, 편집 API, CLI, XML/OPC 처리
- `hwpx-mcp-server`: AI 클라이언트용 MCP 도구 표면
- `hwpx-skill`: 에이전트용 실전 워크플로와 설치 자산

핵심 목표:
- 실제 HWPX 작업을 더 안전하고 빠르고 예측 가능하게 만든다.
- 코어, MCP, Skill 사이의 호환성 깨짐을 줄인다.
- 기능 추가보다 실사용 흐름, 문서, 테스트, 예제를 함께 강화한다.

## 2. 현재 기준선

### python-hwpx
- 현재 버전: `2.9.0`
- Python 요구 사항: `>=3.10`
- 핵심 의존성: `lxml>=4.9,<6`
- 강점: 편집 API, CLI, XML-first 구조, 테스트 폭이 넓음

### hwpx-mcp-server
- 현재 버전: `2.2.5`
- Python 요구 사항: `>=3.10`
- 핵심 의존성: `python-hwpx>=2.6`
- 강점: 도구 표면이 넓고 테스트/문서가 이미 있음

### hwpx-skill
- 패키지형 배포보다 스킬 폴더 배치 중심
- `python-hwpx` 기반 예제/스크립트/설치 가이드 제공
- 강점: 실제 에이전트 사용 흐름에 가깝다

## 3. 운영 원칙

1. 스택 전체를 제품처럼 본다.
2. 코어 변경은 항상 MCP와 Skill 영향까지 본다.
3. 문서, 예제, 테스트, 설치 경험도 기능으로 취급한다.
4. 기능 추가 전후로 round-trip 안정성과 저장 안정성을 확인한다.
5. 릴리스 판단은 개별 레포가 아니라 스택 호환성 기준으로 내린다.

## 4. 변경 우선순위

변경은 아래 순서로 판단한다.

1. `python-hwpx`
   - API, 데이터 모델, 저장/검증, CLI
2. `hwpx-mcp-server`
   - 도구 이름, 인자, 안전한 편집 플로우, MCP 계약
3. `hwpx-skill`
   - 설치, 트리거, 예제, 스크립트, 실전 가이드

원칙:
- 코어가 흔들리면 위 계층은 전부 흔들린다.
- Skill에서 반복되는 pain point는 가능하면 코어나 MCP로 끌어내린다.
- MCP에서 반복되는 우회로는 코어 API 부족 신호로 취급한다.

## 5. 작업 유형별 기본 흐름

### A. 코어 기능 추가/수정
1. `python-hwpx`에서 API/행동 변경
2. 코어 테스트 추가 또는 수정
3. `hwpx-mcp-server`에서 해당 기능 노출 방식 검토
4. `hwpx-skill`에서 예제/가이드/스크립트 업데이트 필요 여부 확인
5. 세 레포 기준으로 문서와 샘플 사용 흐름 점검

### B. MCP 사용성 개선
1. 도구 이름과 인자 구조 정리
2. 실제 AI 호출 관점에서 불필요한 단계 제거
3. 가능하면 `python-hwpx`의 안정된 API 위에 얹기
4. Skill 문서에서 같은 흐름을 재사용 가능하게 맞추기

### C. Skill 실전성 개선
1. 자주 쓰는 작업 시나리오를 먼저 수집
2. 스크립트/예제/설치 가이드를 줄이고 단순화
3. 반복되는 한계가 있으면 MCP 또는 코어로 역제안

## 6. 완료 기준

코드 변경 완료 기준:
- 변경 의도가 문서화되어 있음
- 테스트 또는 재현 절차가 있음
- 영향 받는 상위 레이어를 확인함
- README 또는 관련 가이드가 필요하면 같이 수정함

스택 완료 기준:
- 코어 동작 확인
- MCP 도구 경로 확인
- Skill 예제/설치 흐름 확인
- 버전/호환성 설명이 모순되지 않음

## 7. 릴리스 순서

기본 순서:
1. `python-hwpx`
2. `hwpx-mcp-server`
3. `hwpx-skill`

릴리스 전에 확인할 것:
- `python-hwpx` 버전 변경이 README, 의존성 범위, 예제에 반영됐는지
- `hwpx-mcp-server`의 최소 지원 버전 문구와 실제 테스트 버전이 맞는지
- `hwpx-skill`의 설치 가이드가 현재 코어 버전/스크립트 흐름과 맞는지

## 8. 공통 검증 루프

### python-hwpx
```bash
cd /path/to/python-hwpx
python -m pip install -e ".[test]"
python -m pytest -q
```

### hwpx-mcp-server
```bash
cd /path/to/hwpx-mcp-server
python -m pip install -e ".[test]"
python -m pytest -q
```

### hwpx-skill
```bash
cd /path/to/hwpx-skill
python -m pip install -U python-hwpx lxml
python scripts/text_extract.py <sample.hwpx>
python scripts/zip_replace_all.py <template.hwpx> <output.hwpx> --replace "{키}=값"
```

권장 추가 검증:
- 하나의 샘플 `.hwpx` 문서를 기준으로
  - 코어 편집
  - MCP 도구 호출
  - Skill 스크립트 실행
  세 경로를 모두 통과시키는 end-to-end 스모크 테스트를 유지한다.
- fixture 메타데이터 기준점:
  - `shared/hwpx/fixtures/README.md`
  - `shared/hwpx/fixtures/manifests/`
  - `shared/hwpx/fixtures/fixture_matrix.json`
- fixture scrub/검증 스크립트:
  - `shared/hwpx/scripts/sanitize_fixture_metadata.py`
  - `shared/hwpx/scripts/fixture_smoke_matrix.py`
- 현재 editor-authored sanitized baseline:
  - `shared/hwpx/fixtures/core/00_smoke_min.hwpx`
  - `shared/hwpx/fixtures/fields/10_fieldcodes_min.hwpx`
  - `shared/hwpx/fixtures/forms/20_formcontrols_min.hwpx`
  - `shared/hwpx/fixtures/tables/30_table_merge_min.hwpx`
  - `shared/hwpx/fixtures/change-tracking/40_trackchange_min.hwpx`
  - `shared/hwpx/fixtures/sections/50_master_min.hwpx`
  - `shared/hwpx/fixtures/history/60_history_version_min.hwpx` (history/version semantic baseline으로는 사용 금지)
  - `shared/hwpx/fixtures/stress/99_all_in_one_stress.hwpx`
- generated writer smoke 산출물은 여전히 유용하지만 canonical fixture로 취급하지 않는다.
- 현재 반복 실행 경로:
  - `shared/hwpx/scripts/run_stack_smoke_test.sh`
- 최신 자동화 검증 리포트:
  - `shared/hwpx/HWPX_STACK_VALIDATION_2026-04-16.md`

## 9. 벤치마크 축

정확히 같은 HWPX 스택이 드물기 때문에, 아래 계층별로 배운다.

### 문서 라이브러리 계층
- `python-docx`
- `Open XML SDK`
- `docx4j`

볼 것:
- 문서 모델 노출 방식
- round-trip 안전성
- 예제와 문서 구조
- 테스트/픽스처 운영 방식

### MCP 서버 계층
- 성숙한 파일/문서 계열 MCP 서버들
- `modelcontextprotocol` 레퍼런스 서버 패턴

볼 것:
- 도구 이름/인자 설계
- stateless 호출 패턴
- 안전한 쓰기 플로우
- 스키마 명확성

### Skill 계층
- VS Code Agent Skills 문서/예제
- 구조가 좋은 공개 스킬 저장소

볼 것:
- 트리거 문구 설계
- 설치 난이도
- 예제 배치 방식
- 참조 문서 구조

## 10. 이 스레드의 기본 운영 방식

이 스레드에서는 항상 아래 순서로 본다.

1. 목표가 코어 문제인지, MCP 문제인지, Skill 문제인지 분류
2. 실제 영향 레이어를 다시 체크
3. 변경 범위를 최소화
4. 필요하면 세 레포에 나눠서 반영
5. 마지막에 스택 관점으로 다시 검토

한 줄 요약:

**코어에서 안정화하고, MCP에서 노출하고, Skill에서 실전성을 다듬는다.**
