# Benchmark Note: VS Code Agent Skills docs/examples

## 왜 봤나

`hwpx-skill`은 설치형 스킬 자산이다. 그래서 VS Code Agent Skills 문서는 직접적인 비교 기준이다.

보고 싶은 점은 셋이다.

- 스킬과 custom instructions를 어떻게 구분하는가
- 설치 위치와 트리거 구조를 얼마나 선명하게 보여주는가
- SKILL.md와 추가 리소스의 관계를 어떻게 설명하는가

## 관찰

### 1. skill과 custom instructions의 역할을 분리한다

VS Code 문서는 Agent Skills를 "전문화된 capability/workflow", custom instructions를 "코딩 규칙/가이드라인"으로 선명하게 구분한다.

HWPX 스택에 주는 시사점:
- `hwpx-skill` README와 SKILL은 단순 규칙 모음이 아니라 **실행 가능한 워크플로 자산**이라는 점을 더 분명히 해야 한다.
- examples, scripts, references가 왜 함께 들어있는지 설명하는 것이 중요하다.

### 2. 설치 위치와 discovery 규칙이 매우 명확하다

문서는 project skills와 personal skills 위치를 표로 보여주고, 추가 탐색 위치 설정도 설명한다.

HWPX 스택에 주는 시사점:
- `hwpx-skill`도 에이전트별 설치 경로를 지금처럼 계속 분명하게 유지해야 한다.
- 다만 설치 다음 단계인 **quick verification**이 더 앞쪽에 있어야 한다.

### 3. frontmatter 품질을 아주 강하게 요구한다

문서는 `name`, `description`을 스킬 discovery 핵심으로 보고, 이름 제약과 description 역할을 자세히 설명한다.

HWPX 스택에 주는 시사점:
- `hwpx-skill`의 description은 계속 도메인 키워드와 사용 맥락을 충분히 담아야 한다.
- 반대로 body에는 실제 절차와 리소스 링크를 집중시키는 편이 낫다.

### 4. 추가 파일은 SKILL.md에서 직접 참조해야 한다

문서는 scripts/examples/resources를 넣을 수 있지만, 상대 경로 링크로 SKILL.md에서 명시적으로 연결하라고 안내한다.

HWPX 스택에 주는 시사점:
- `hwpx-skill`은 이미 구조가 좋다.
- 앞으로도 `references/api.md`, `scripts/*.py`, `examples/*.py`를 SKILL 본문에서 직접 연결하는 원칙을 유지해야 한다.

### 5. progressive loading 관점이 강하다

필요한 skill만 로드된다는 점을 강조한다. 즉, SKILL 본문은 과하게 길 필요가 없다.

HWPX 스택에 주는 시사점:
- `hwpx-skill/SKILL.md`는 의사결정과 워크플로 중심으로 유지한다.
- 세부 시그니처는 `references/api.md`로 밀어두는 현재 방향이 맞다.

## 바로 흡수할 액션

### hwpx-skill
- README 앞부분에 quick verification을 넣는다.
- SKILL.md에는 설치 직후 최소 성공 경로를 짧게 넣는다.
- 기준 버전과 최근 로컬 검증 버전을 최신 상태로 유지한다.
- examples/references/scripts 링크를 계속 SKILL 본문에서 직접 유지한다.

### 스택 전체
- skill 문서는 "설치됨"보다 "검증됨" 상태를 더 중요하게 보여준다.
- release note나 validation report와 skill README의 버전 기준이 어긋나지 않게 관리한다.

## 한 줄 결론

**좋은 skill 문서는 설명서가 아니라, discovery가 잘 되고 설치 직후 바로 검증되는 실행 자산이다.**

## 참고
- https://code.visualstudio.com/docs/copilot/customization/agent-skills
