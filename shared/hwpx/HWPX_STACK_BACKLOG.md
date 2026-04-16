# HWPX Stack Backlog v1

빠른 기준선 점검에서 바로 보인 우선 과제만 모았다.

## P0

### 1. 호환성 매트릭스 명문화
- 목적: `python-hwpx` 버전 변화가 `hwpx-mcp-server`, `hwpx-skill`에 미치는 영향 추적
- 산출물:
  - 지원 최소 버전
  - 검증 완료 버전
  - 주의 필요 변경점

### 2. end-to-end 스모크 테스트 운용 고정
- 자동화 스크립트 추가 완료:
  - `shared/hwpx/scripts/run_stack_smoke_test.sh`
- 현재 남은 일:
  - release 전 재실행 기준으로 고정
  - 필요하면 CI 또는 pre-release 체크리스트에 편입

### 3. release-facing 문서 동기화 유지
- release-facing 문서는 `python-hwpx 2.9.0` 검증 기준과 `>=2.6` 최소 지원 기준으로 정리 완료
- 현재 남은 일:
  - generated metadata와 public docs의 동기화 유지
  - 이후 support matrix 갱신 시 동일 기준을 반복 적용

## P1

### 4. MCP 도구 표면 재점검
- 목표: 자주 쓰는 작업이 최소 호출 수로 끝나는지 확인
- 포인트:
  - 읽기/검색/치환/표 편집 흐름
  - 도구 이름과 파라미터 일관성
  - 고급 도구와 기본 도구 경계 명확화

### 5. Skill 검증 체계 추가
- 현재 skill은 예제와 스크립트는 있지만 패키징/테스트 체계가 약함
- 해야 할 일:
  - 예제 실행 기준서
  - 샘플 문서 기반 스모크 절차
  - 설치 후 바로 확인 가능한 quick verification 추가

### 6. 공통 샘플/픽스처 전략 수립
- 같은 샘플 문서를 레포마다 따로 들고 갈지
- 공유 샘플 묶음을 둘지
- 민감정보 없는 공개 가능한 fixture 세트로 정리할지 결정 필요
- 진행 상황:
  - `shared/hwpx/fixtures/README.md` 생성
  - `shared/hwpx/fixtures/manifests/`에 초기 candidate manifest 작성
  - repo 안에서 즉시 읽히는 `.hwpx` 후보 4종과 generated supplemental 1종 분류 완료
  - NAS 원본 `hwpx_smoke` 실경로 확인: `private://hwpx_smoke`
  - editor-authored 원본 8개를 `shared/hwpx/fixtures/`로 로컬 복사 완료
  - imported 8개에 creator metadata scrub 적용 완료
  - `fixture_matrix.json` + `fixture_smoke_matrix.py` + 갱신된 `run_stack_smoke_test.sh`로 editor-authored smoke 경로 고정 완료
  - feature별 manifest와 import report(`EDITOR_AUTHORED_IMPORT_2026-04-16.md`) 작성 완료
  - validation report에 editor-authored fixture baseline 반영 완료
- 현재 남은 일:
  - dedicated history/version editor-authored fixture를 따로 확보할지 결정
  - 필요 시 MCP/Skill 표면별 fixture 시나리오를 더 세분화

### 7. 벤치마크 검토
- 완료:
  - `shared/hwpx/benchmarks/python-docx.md`
  - `shared/hwpx/benchmarks/modelcontextprotocol-servers.md`
  - `shared/hwpx/benchmarks/open-xml-sdk.md`
  - `shared/hwpx/benchmarks/vscode-agent-skills.md`
  - `shared/hwpx/HWPX_STACK_ACTION_MAP.md`
- 현재 남은 일:
  - 액션맵 기준으로 각 레포 수정 묶음을 계속 실행
  - 다음 후보 검토 (`docx4j`, `pyhwp`)

## P2

### 8. Skill 배포 경험 개선
- 현재는 폴더 복사 중심
- 설치/업데이트/버전 추적이 번거롭다
- 후보:
  - 배포 템플릿 단순화
  - 설치 스크립트 제공
  - 에디터별 설정 예시 자동 생성

### 9. 코어 타입/정적검사 범위 확장
- `python-hwpx`는 일부 모듈 위주로 typecheck 범위가 잡혀 있음
- 안정화된 영역부터 점진 확대 검토

## 작업 원칙
- P0부터 처리
- 작은 개선이라도 상위 레이어 영향 확인
- 문서만 고치는 작업도 스택 기준으로 본다
