# HWPX Stack Action Map v2

벤치마크와 최근 검증 결과를 바로 실행 가능한 레포별 액션으로 분해한 문서다.

## 1. python-hwpx

### 목표
- 첫 성공 경험을 더 짧게 만든다.
- 객체 중심 문서 구조를 더 쉽게 찾게 만든다.
- 편집 경로와 분석/심화 경로를 더 분리한다.

### 바로 할 일
1. README와 docs 첫 화면에서 `new/open -> add/edit -> save_to_path` 흐름을 가장 먼저 보여준다.
2. docs 인덱스에 작업별 바로가기를 더 선명하게 유지한다.
   - 문서 열기/읽기
   - 문단/표 편집
   - 메모/스타일
   - 추출/검증
   - 패키지/스키마 심화
3. 고급 XML/패키지 제어는 quickstart와 심화 문서를 더 분리해서 노출한다.
4. 읽기/분석 예제를 편집 예제만큼 찾기 쉽게 둔다.
5. 버전 변화와 호환성 영향은 README, release note, support matrix에서 같이 보이게 유지한다.

### 근거
- `python-docx`는 첫 성공 경로가 짧다.
- `docx4j`는 복잡한 내부 구조를 문서 계층으로 분리한다.
- `pyhwp`는 분석 중심 진입점을 아주 선명하게 드러낸다.

## 2. hwpx-mcp-server

### 목표
- 공개 MCP surface를 더 예측 가능하게 만든다.
- 읽기 전용, 즉시 저장, payload 변환, advanced 점검 경계를 더 선명하게 만든다.

### 바로 할 일
1. README와 tool docstring에서 저장 동작을 계속 명시한다.
2. 자주 쓰는 작업 예시를 read-first / copy-first 기준으로 정리한다.
3. 읽기 전용 구조 조회 흐름과 즉시 저장 편집 흐름을 문서에서 더 분리한다.
4. advanced mode 문서를 기본 흐름과 섞이지 않게 유지한다.
5. release-facing 문서와 generated metadata의 버전 동기화를 반복 점검한다.

### 근거
- MCP reference servers는 공개 표면 경계를 선명하게 유지한다.
- `pyhwp`는 inspection 계열 작업 이름을 이해하기 쉽게 노출한다.
- 현재 HWPX 서버는 안전한 흐름이 중요하고, 즉시 저장 도구가 많다.

## 3. hwpx-skill

### 목표
- 설치형 자산으로서 바로 검증 가능하게 만든다.
- 트리거 문구와 실제 로컬 검증 기준을 최신 상태로 유지한다.

### 바로 할 일
1. `SKILL.md`의 기준 버전/로컬 검증 버전을 최신 기준으로 갱신한다.
2. README에 quick verification 섹션을 유지하고 실제 검증 루프와 맞춘다.
3. examples와 scripts를 실제 검증 루프와 연결한다.
4. 설치 직후 최소 성공 경로를 문서 맨 앞쪽에 노출한다.
5. 트리거 문구를 `추출`, `구조 확인`, `검증`, `치환` 같은 작업명 중심으로 다듬는다.

### 근거
- VS Code Agent Skills 계열은 설치와 트리거 구조가 선명하다.
- `pyhwp`는 작업 단위 중심 문서 구성이 강하다.
- 현재 `hwpx-skill`은 예제는 좋지만 트리거와 검증 루프를 더 단단히 묶을 여지가 있다.

## 4. 공통 스택

### 목표
- 문서 선언이 아니라 반복 가능한 운영 루프를 만든다.
- 안정 기능과 실험 기능의 경계를 스택 전체에서 일관되게 보여준다.

### 바로 할 일
1. `shared/hwpx/scripts/run_stack_smoke_test.sh`를 release 전 필수 경로로 고정한다.
2. support matrix는 상태 스냅샷으로 유지하고, 해야 할 일은 backlog로만 보낸다.
3. 공통 fixture/샘플 전략을 정해서 세 레포가 같은 smoke path를 재사용하게 만든다.
4. 벤치마크 요약은 바로 backlog 액션으로 연결한다.
5. 실험적/제한적 기능은 README, skill 문서, validation report에서 같은 표현으로 표기한다.

## 5. 다음 우선순위

1. `python-hwpx` README/quickstart 2차 정리
2. `hwpx-mcp-server` inspect vs mutate 문서 구획 강화
3. 실험적 기능 표기 기준 통일
4. `pyhwpx` 벤치마크
5. filesystem / git 계열 MCP server 벤치마크

한 줄 원칙:

**좋은 아이디어 메모로 끝내지 말고, 각 레포의 다음 수정 단위로 바로 내린다.**
