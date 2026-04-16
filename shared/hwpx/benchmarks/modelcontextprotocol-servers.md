# Benchmark Pass 1: modelcontextprotocol/servers

검토일: 2026-04-16
대상: `modelcontextprotocol/servers`

## 왜 봤나

이 저장소는 production app이 아니라 **reference implementation 집합**이다. 그래서 `hwpx-mcp-server`와 직접 비교하기보다, MCP 서버가 어떤 태도로 도구 표면을 설명하고 분리하는지 보는 기준점으로 쓴다.

## 바로 보이는 강점

1. **레퍼런스 구현이라는 경계가 명확하다**
- 이 저장소는 교육용/예시용임을 README 초반에 분명히 적는다.
- production-ready가 아니라는 경계를 숨기지 않는다.

2. **서버별 책임이 짧고 분명하다**
- Fetch, Filesystem, Git, Memory처럼 이름만 봐도 역할이 명확하다.
- 도구 표면이 서버 정체성과 바로 연결된다.

3. **보안과 접근 통제 관점을 초반에 강조한다**
- MCP는 곧 도구 노출이므로, 기능보다 접근 범위와 통제 모델을 같이 설명한다.

## HWPX 스택에 가져올 점

### 1. `hwpx-mcp-server`의 제품 경계 문구를 더 선명하게 유지
이미 README가 꽤 잘 정리돼 있다. 그래도 `reference workflow`와 `stable public MCP surface`를 계속 분리해서 적는 게 중요하다.

권장 액션:
- README와 docs에서 `public tool surface`와 `workflow/orchestration examples`를 더 일관되게 구분
- 문서가 새 기능 제안처럼 읽히지 않게 유지

### 2. 도구 이름과 설명을 더 엄격하게 다듬기
reference servers는 이름이 짧고 역할이 분명하다. `hwpx-mcp-server`도 도구 수가 많아질수록 이름, 입력 스키마, advanced mode 경계를 더 엄격히 관리해야 한다.

권장 액션:
- 도구 설명을 “무엇을 읽는지 / 무엇을 바꾸는지 / 즉시 저장되는지” 기준으로 다시 점검
- advanced tool은 기본 도구와 섞여 보이지 않게 문서에서 더 분리

### 3. 문서에서 안전한 쓰기 흐름을 더 전면화
filesystem/git 계열 레퍼런스가 보여주는 핵심은 기능보다 가드레일이다. `hwpx-mcp-server`도 `copy_document` 선행, immediate persistence, advanced inspection 같은 안전 흐름을 더 강조할 가치가 있다.

## 그대로 베끼면 안 되는 점

- reference server repo는 교육용 예시에 최적화돼 있다.
- `hwpx-mcp-server`는 실제 사용자가 바로 설치해 쓰는 product surface다.
- 따라서 너무 얇고 예시적인 문서만 남기면 오히려 실사용 가이드가 약해진다.

## 적용 우선순위

1. public tool surface vs workflow docs 경계 유지 강화
2. 도구 설명 문구 재점검
3. copy-first / immediate-persist 규칙을 README와 use-cases에서 더 명시

한 줄 결론:

**`modelcontextprotocol/servers`에서 배울 핵심은 기능 수가 아니라, 서버 책임과 공개 표면의 경계를 문서에서 선명하게 고정하는 방식이다.**
