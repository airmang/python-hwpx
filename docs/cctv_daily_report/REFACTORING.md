# 리팩토링 진단 (cctv_daily_report 앱 레이어)

작성일: 2026-06-05. 본 문서는 진단·계획만 담는다. 실제 코드 수정은 별도 작업으로 진행.

## 1. 범위 구분

이 레포는 성격이 다른 두 레이어가 공존한다. 리팩토링 범위를 분리한다.

| 레이어 | 위치 | 상태 | 방침 |
|---|---|---|---|
| 코어 라이브러리 | `src/hwpx` | v2.9.1 배포본, 테스트 보유, 성숙 | 손대지 않음 (PyPI 배포·외부 의존, 변경 리스크 큼) |
| 앱 레이어 | `src/cctv_daily_report` | 1160줄, untracked, 테스트 0, 미등록 | 리팩토링 대상 (작고 격리, 저위험·고효용) |

앱 레이어 모듈 분리(config/mock/statistics/event_selector/images/vlm/summarizer/translator/renderer/pipeline)는 이미 양호하다. 구조 재설계가 아니라 부채 정리와 인터페이스 정돈 수준으로 충분하다.

## 2. 선행 조건

앱 레이어가 전부 untracked(커밋 0)이다. 리팩토링 전에 현재 동작본을 한 번 커밋해 비교 기준점을 확보할 것을 권장한다.

## 3. 발견 항목 (우선순위순)

### 높음 — 실사용 전환을 막는 것들

1. 패키지 미등록
   - 현상: `pyproject.toml`의 `[tool.setuptools.packages.find] include = ["hwpx*"]` 때문에 `cctv_daily_report`가 install 대상에서 빠진다. 실행을 매번 `PYTHONPATH=src python -m cctv_daily_report.cli`로 우회.
   - 방향: 정식 등록(`include`에 추가) 또는 의도적 분리 유지 여부를 먼저 결정. 분리 유지라면 실행 진입점만 문서화.
   - 위험/노력: 낮음 / 낮음

2. 데이터 소스 추상화 부재
   - 현상: `mock_data.build_mock_dataset`이 하드코딩. 실데이터(DB·이벤트 로그) 연동 지점이 인터페이스로 분리돼 있지 않아 교체 시 코드 수정이 필요.
   - 방향: `EventSource`(또는 콜러블) 프로토콜로 추상화해 mock과 실데이터를 스위칭. `CctvEvent`/`ReportInfo` dataclass는 그대로 계약으로 사용.
   - 위험/노력: 중간 / 중간

3. 하드코딩 날짜 `2026-05-11`
   - 현상: `cli.py`, `pipeline.py`(2곳), `mock_data.py`에 과거 고정 날짜가 기본값으로 산재.
   - 방향: 기본값을 "오늘"로 바꾸거나 상수 한 곳으로 모은다.
   - 위험/노력: 낮음 / 낮음

### 중간 — 견고성·유지보수

4. 렌더러 인덱스 의존
   - 현상: `renderer.py`(229줄, 최대)가 문단 13/23/31 등 인덱스로 접근. 템플릿에 문단이 추가/삭제되면 매핑이 전부 어긋남.
   - 방향: placeholder 토큰(예: `{{report_date}}`) 치환 방식으로 전환해 인덱스 의존 제거. 표/도형 안은 이미 내용 비의존 치환으로 개선됨.
   - 위험/노력: 중간 / 중간 (템플릿도 토큰화 필요)

5. `sys.path.insert` 핵
   - 현상: `vlm.py`가 `pia_summary/prompts`를 임포트하려고 런타임에 `sys.path`를 조작.
   - 방향: 어댑터 모듈로 감싸거나 정식 의존성으로 정리.
   - 위험/노력: 낮음 / 낮음

6. 번역 단계 존재
   - 현상: vLLM 서버가 영어 단일 출력 사양이라 `translator.py`로 영→한 재번역. 0.8B 한계로 품질도 불안정.
   - 방향: 한국어 직접 출력 모델로 전환하면 `translator.py`를 통째로 제거 가능. 아키텍처 결정사항.
   - 위험/노력: 낮음(제거 자체) / 결정 선행 필요

7. private 함수 누수
   - 현상: `pipeline.py`가 `summarizer._rule_based_fallback`을 직접 import.
   - 방향: public API로 승격하거나 fallback 분기를 summarizer 내부로 캡슐화.
   - 위험/노력: 낮음 / 낮음

### 낮음 — 위생

8. 테스트 0건
   - 현상: 코어는 테스트가 탄탄하나 앱 레이어는 전무.
   - 방향: 최소 `statistics`, `event_selector`, `renderer`(빈/채워진 템플릿 렌더 후 placeholder 잔존·줄바꿈 검증) 단위 테스트.
   - 위험/노력: 낮음 / 중간

9. 루트 문서 산재
   - 현상: `PLAN.md`, `RESULT.md`, `ARCHITECTURE.md`, `feature_docs.md`, 본 문서가 레포 루트에 흩어져 있음.
   - 방향: `docs/cctv_daily_report/`로 이동.
   - 위험/노력: 낮음 / 낮음

## 4. 권장 진행 순서

코어는 손대지 않고 앱 레이어만 위험 낮은 순서로 점진 진행한다.

- 0단계: 현재 동작본 커밋 (기준점 확보)
- 1단계(위생) [완료 2026-06-05]: 하드코딩 날짜 정리(3), private 누수 제거(7), `sys.path` 핵 정리(5), 문서 `docs/`로 이동(9)
- 2단계(구조) [완료 2026-06-05]: 데이터 소스 인터페이스 추상화(2), 렌더러 토큰 치환 전환(4)
- 3단계(결정 후): 패키지 등록 여부(1), 번역 단계 제거 여부(6)
- 각 단계마다 최소 단위 테스트 추가(8)

### 1단계 완료 내역

- (3) 하드코딩 날짜 `2026-05-11` 제거 → `config.today_iso()` 헬퍼로 통일.
  `cli`/`pipeline.run_report`/`pipeline.dump_payload`/`mock_data.build_mock_dataset`
  모두 `report_date=None` 기본값 → 미지정 시 오늘 날짜.
- (7) `pipeline`이 직접 import하던 `summarizer._rule_based_fallback`을
  public `rule_based_fallback`으로 승격.
- (5) `vlm.py`의 import-time `sys.path.insert` 부작용 제거 →
  `_load_build_chat_payload()` 지연 로딩으로 캡슐화(실제 VLM 호출 시점에만 등록).
- (9) `PLAN.md`/`RESULT.md`/`ARCHITECTURE.md`/`feature_docs.md`/`REFACTORING.md`를
  `docs/cctv_daily_report/`로 이동(루트엔 코어 repo 문서만 잔존).
- 검증: import 무결성 OK, `--report-date` 미지정 시 오늘 날짜로 렌더,
  rule-based fallback 경로 동작, `hwpx-validate-package` 통과.

### 2단계 완료 내역

- (2) `sources.py` 신설: `EventSource` 프로토콜 + `MockEventSource`.
  `pipeline.run_report(..., source=None)`에 주입, 미지정 시 `MockEventSource`.
  실데이터 연동 시 pipeline 수정 없이 `EventSource` 구현체만 추가하면 됨.
  `CctvEvent`/`ReportInfo`가 소스↔pipeline 계약.
- (4) 렌더러를 문단 인덱스 → `{{token}}` 치환 방식으로 전환.
  - blank 템플릿에 토큰 임베드(단일 라인 8종 + 다중 라인 3종).
  - `_replace_single_tokens`(substring, 본문+표/도형 일괄) +
    다중 라인 토큰은 `_set_multiline`(<hp:lineBreak/>).
  - 제목·부서명·섹션 헤더는 literal 유지(보고서마다 불변).
  - 렌더러에서 하드코딩 문단 인덱스 완전 제거.
- 검증: 토큰 잔존 0, `hwpx-validate-package` 통과, 줄바꿈 3개 정상.
  구조 변경 내성 증명 — 템플릿 앞에 문단을 끼워 인덱스를 +1 밀어도
  토큰 치환 정상(구버전 인덱스 렌더러였다면 전부 깨졌을 케이스).

## 5. 손대지 않을 것

- `src/hwpx` 코어 라이브러리 전체 (배포본·테스트 보유)
- `pia_summary/prompts.py` (영어 단일 출력 가이드 존중, 기존 결정)
- 검증 시 나오는 manifest version 파트 누락 경고 (열람 무해)
