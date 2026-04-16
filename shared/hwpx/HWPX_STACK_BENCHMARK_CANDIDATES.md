# HWPX Stack Benchmark Candidates

정확히 같은 HWPX 스택은 드물다. 그래서 같은 포맷이 아니라도 **같은 계층 문제를 잘 푸는 프로젝트**를 벤치마크 대상으로 잡는다.

## 1. Core library layer

### 1. python-docx
- Repo: `python-openxml/python-docx`
- 왜 보나:
  - Python 문서 편집 API의 대표 사례다
  - 고수준 객체 모델과 저수준 XML 사이 경계 설계가 좋다
- 볼 것:
  - API naming 일관성
  - user-facing examples 구성
  - table/paragraph/run 추상화 방식
- 흡수 포인트:
  - 자주 쓰는 작업의 “짧은 행복 경로”
  - 객체 탐색과 수정 API의 예측 가능성

### 2. Open XML SDK
- Repo: `dotnet/Open-XML-SDK`
- 왜 보나:
  - 문서 포맷 라이브러리의 정석급 사례다
  - 검증, strongly-typed model, 도구/문서 체계가 강하다
- 볼 것:
  - validator 설계
  - schema-derived 타입 구조
  - breaking change 관리 방식
- 흡수 포인트:
  - 검증 기능의 계층화
  - 문서 포맷 안정성에 대한 태도

### 3. docx4j
- Repo: `plutext/docx4j`
- 왜 보나:
  - 복잡한 XML 문서 조작을 실전적으로 오래 운영한 프로젝트다
- 볼 것:
  - 패키지 구조
  - 고급 기능과 기본 기능의 분리
  - 샘플/레퍼런스 자산 운영 방식
- 흡수 포인트:
  - 고급 기능을 무리하게 메인 API에 섞지 않는 방법

### 4. pyhwp
- Repo: `mete0r/pyhwp`
- 왜 보나:
  - 같은 한글 계열 문서 도메인이다. 포맷은 다르지만 문제 공간이 가깝다
- 볼 것:
  - CLI와 라이브러리 경계
  - 포맷 분석/추출 중심 워크플로
- 흡수 포인트:
  - 한국어 문서 생태계에 맞는 도구 노출 방식

### 5. pyhwpx
- 도구 성격: Windows COM 자동화 계열
- 왜 보나:
  - 직접 경쟁/비교 대상이다
- 볼 것:
  - 사용자가 기대하는 작업 종류
  - 자동화 UX 기대치
- 흡수 포인트:
  - `python-hwpx`가 무엇을 대체하고 무엇은 대체하지 않는지 더 명확히 설명하는 방식

## 2. MCP server layer

### 1. modelcontextprotocol reference servers
- Repo: `modelcontextprotocol/servers`
- 왜 보나:
  - MCP 도구 설계의 기준점이다
- 볼 것:
  - 도구 설명 문구
  - 입력 스키마 명확성
  - stateless 호출 패턴
- 흡수 포인트:
  - 도구 이름을 짧고 분명하게 유지하는 방식
  - 안전한 파일 수정 플로우

### 2. filesystem / git 계열 MCP servers
- 왜 보나:
  - 문서 편집처럼 상태가 있는 작업을 MCP로 어떻게 안전하게 푸는지 보기 좋다
- 볼 것:
  - preview/apply 분리
  - 읽기와 쓰기 경계
  - 실수 방지 가드레일
- 흡수 포인트:
  - `plan_edit` / `preview_edit` / `apply_edit`의 UX 개선 아이디어

### 3. context7 / docs-oriented MCP tools
- 왜 보나:
  - “읽기 쉬운 출력”과 “도구 응답 품질”이 중요하다
- 볼 것:
  - 검색 응답 구조
  - 긴 문서를 다루는 방식
- 흡수 포인트:
  - HWPX 추출/요약/구조 조회 도구의 응답 설계

## 3. Skill / agent-workflow layer

### 1. VS Code Agent Skills docs/examples
- 문서: VS Code agent skills 공식 문서/예제
- 왜 보나:
  - 스킬 설치, 트리거, 참조 파일 구조가 잘 정리돼 있다
- 볼 것:
  - `SKILL.md` 구조
  - examples/references 분리
  - 트리거 설명 방식
- 흡수 포인트:
  - `hwpx-skill`의 설치/트리거 문구 정제

### 2. 공개 skill collections
- 예: markdown-viewer/skills 같은 구조가 좋은 스킬 저장소
- 왜 보나:
  - 다수 스킬을 운영할 때의 정보 구조를 배울 수 있다
- 볼 것:
  - examples, references, layouts 분리
  - README에서 사용 시나리오를 보여주는 방식
- 흡수 포인트:
  - `hwpx-skill`의 examples/references 확장 방향

### 3. GitHub AGENTS.md / agent instruction best practices
- 왜 보나:
  - 에이전트가 언제 어떤 도구/스킬을 써야 하는지 더 정확하게 쓰는 법을 배울 수 있다
- 볼 것:
  - 역할 정의
  - scope guard
  - ask-first boundaries
- 흡수 포인트:
  - `SKILL.md`의 판단 트리 선명화

## 4. HWPX 스택에 바로 적용할 벤치마크 질문

각 후보를 볼 때 아래 질문으로 본다.

- 이 프로젝트는 **초보 사용자 첫 성공 경험**을 어떻게 만들었나?
- API나 도구 이름이 **한 번 보고 이해되는가**?
- 고급 기능은 기본 기능과 **어떻게 분리**했나?
- 문서와 예제가 **실제 최신 버전과 얼마나 잘 맞는가**?
- 회귀를 막기 위해 **어떤 fixture / smoke test / validator**를 두었나?
- 사용자가 가장 자주 밟는 경로를 **몇 단계로 줄였나**?

## 5. 1차 착수 현황

완료:
- `shared/hwpx/benchmarks/python-docx.md`
- `shared/hwpx/benchmarks/modelcontextprotocol-servers.md`
- `shared/hwpx/benchmarks/open-xml-sdk.md`
- `shared/hwpx/benchmarks/vscode-agent-skills.md`

다음 후보:
- `docx4j`
- `pyhwp`

## 6. 추천 우선순위

가장 먼저 볼 것:
1. `python-docx`
2. `Open XML SDK`
3. `modelcontextprotocol/servers`
4. VS Code Agent Skills docs/examples
5. `pyhwp`

이유:
- 코어 API 설계
- 검증/문서/릴리스 운영
- MCP 표면 설계
- Skill 구조화
- 한글 문서 도메인 인접성

한 줄 원칙:

**같은 포맷이 없어도 같은 계층 문제를 잘 푸는 프로젝트에서 배운다.**
