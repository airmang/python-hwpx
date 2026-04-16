# HWPX Stack Compatibility Baseline

작성 시점 기준 빠른 기준선이다. 정식 릴리스 전에는 실제 테스트 결과로 갱신한다.

## 1. 현재 확인된 버전

| Layer | Repo | Current Version | Python | Notes |
|---|---|---:|---|---|
| Core | `python-hwpx` | `2.9.0` | `>=3.10` | 코어 라이브러리/CLI |
| MCP | `hwpx-mcp-server` | `2.2.5` | `>=3.10` | `python-hwpx>=2.6` 의존 |
| Skill | `hwpx-skill` | package version 없음 | Python 설치 필요 | 복사형 설치/예제 중심 |

## 2. 현재 문서상 호환성 상태

### 확인된 사실
- `hwpx-mcp-server` 런타임 의존성은 `python-hwpx>=2.6`
- release-facing 문서는 현재 `python-hwpx 2.9.0` 검증 기준과 `>=2.6` 최소 지원 기준으로 정리됐다
- 일부 `2.7.1` 언급은 과거 audit/changelog 문맥의 역사 기록으로 남아 있다
- 실제 코어 repo 현재 버전은 `python-hwpx 2.9.0`

### 해석
- 최소 지원 버전과 최근 검증 버전은 분리해 설명해야 한다.
- 현재 사용자에게 보이는 주요 문서는 최신 로컬 검증 기준을 반영한다.
- 역사 기록 문서의 과거 버전 언급과 현재 지원 판단을 혼동하지 않게 유지해야 한다.

## 3. 임시 지원 판단

| 조합 | 상태 | 판단 |
|---|---|---|
| `python-hwpx 2.6.x` + `hwpx-mcp-server 2.2.5` | 문서상 최소 | 기능 축소/회귀 위험 확인 필요 |
| `python-hwpx 2.7.1` + `hwpx-mcp-server 2.2.5` | 문서상 검증 | 기존 문서 기준 안전 조합 |
| `python-hwpx 2.9.0` + `hwpx-mcp-server 2.2.5` | 로컬 검증 완료 | `pytest -q` 전체 통과 |
| `python-hwpx 2.9.0` + `hwpx-skill` | 로컬 검증 완료 | 생성, 추출, 치환 smoke test 통과 |

## 4. 갱신 이력

| 날짜 | 검증 조합 | 결과 | 리포트 |
|---|---|---|---|
| 2026-04-15 | `python-hwpx 2.9.0` + `hwpx-mcp-server 2.2.5` | 통과 | `HWPX_STACK_VALIDATION_2026-04-15.md` |
| 2026-04-15 | `python-hwpx 2.9.0` + `hwpx-skill` smoke path | 통과 | `HWPX_STACK_VALIDATION_2026-04-15.md` |
| 2026-04-16 | automated stack smoke (`python-hwpx` + focused MCP smoke + `hwpx-skill`) | 통과 | `HWPX_STACK_VALIDATION_2026-04-16.md` |

## 5. 정식 매트릭스가 가져야 할 항목

- 최소 지원 코어 버전
- 권장 코어 버전
- 최신 검증 코어 버전
- MCP 회귀 테스트 통과 여부
- Skill 예제 통과 여부
- 알려진 제한 사항

한 줄 결론:

**현재 확인된 최신 로컬 검증 조합과 automated smoke 기준은 모두 `python-hwpx 2.9.0` 기반이다.**
