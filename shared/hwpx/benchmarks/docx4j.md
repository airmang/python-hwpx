# Benchmark Note: docx4j

## 왜 봤나

`docx4j`는 복잡한 XML 문서 조작을 오래 실전 운영한 라이브러리다. HWPX와 포맷은 다르지만, 기능이 커질수록 생기는 같은 문제를 본다.

- 빠른 시작과 깊은 참조 문서를 어떻게 같이 운영하는가
- 파트/패키지/객체 모델 같은 고급 개념을 어디까지 전면에 두는가
- breaking change와 버전 전환을 얼마나 솔직하게 드러내는가

## 관찰

### 1. 얇은 진입로와 두꺼운 레퍼런스를 같이 둔다

README는 기능 범위를 넓게 보여주지만, 곧바로 Getting Started, docs, sample code, cheat sheet로 연결한다.

핵심 인상:
- 초보자 경로와 전문가 경로를 한 문서에 다 우겨넣지 않는다.
- 대신 입구는 짧게, 깊이는 별도 자산으로 푼다.

HWPX 스택에 주는 시사점:
- `python-hwpx`도 README에서 모든 능력을 다 설명하려 하지 말고, 최소 성공 경로 이후에는 작업별 문서로 더 빨리 분기시키는 편이 낫다.
- `hwpx-skill`도 examples/references 분리를 계속 유지하는 쪽이 맞다.

### 2. 복잡한 내부 구조를 숨기지 않되, 단계적으로 노출한다

Getting Started 목차만 봐도 architecture, parts list, MainDocumentPart, XPath, samples, creating a new docx, adding a paragraph, creating a table 같은 항목이 분명하다.

핵심 인상:
- 고급 내부 구조를 감추지 않는다.
- 대신 사용자가 어디서 얕게 시작하고 어디서 깊게 내려가는지 문서가 안내한다.

HWPX 스택에 주는 시사점:
- `python-hwpx`는 quickstart와 `schema/package/XML` 계층 문서를 더 의식적으로 분리하는 편이 좋다.
- `hwpx-mcp-server`도 기본 편집 흐름과 고급 inspection 흐름을 더 구획할 가치가 있다.

### 3. 샘플과 레퍼런스 자산이 제품 표면의 일부다

docx4j는 sample code, getting started 문서, 별도 docs 자산이 강하다.

핵심 인상:
- 샘플은 부록이 아니라 진입점이다.
- 문서가 API만 설명하는 것이 아니라, 실제 작업 단위를 보여준다.

HWPX 스택에 주는 시사점:
- `python-hwpx`는 작업별 예제 링크를 첫 화면에서 더 강하게 연결할 수 있다.
- `shared/hwpx` fixture/smoke 자산도 내부 운영 자료가 아니라 공개 문서에서 더 쉽게 찾게 만들 가치가 있다.

### 4. breaking change를 초반에 숨기지 않는다

README는 `jakarta.xml.bind` 전환 같은 버전 변화와 모듈 구조를 초반부터 언급한다.

핵심 인상:
- 호환성 비용을 사용자에게 늦게 알리지 않는다.
- 버전 전환 사실을 문서 앞단에서 고지한다.

HWPX 스택에 주는 시사점:
- `python-hwpx` 버전 변화가 `hwpx-mcp-server`, `hwpx-skill`에 미치는 영향은 release note와 compatibility 문서에서 더 전면화하는 편이 낫다.
- support matrix, validation report, README 기준 버전이 계속 같이 움직여야 한다.

## 바로 흡수할 액션

### python-hwpx
- README는 `create/open -> add/edit -> save` 최소 경로를 유지하고, 고급 패키지/XML 주제는 별도 작업별 문서로 분기한다.
- docs 인덱스에 `문서 생성`, `문단/표 편집`, `추출/검증`, `패키지/스키마 심화` 같은 경로를 더 선명하게 둔다.
- 버전/호환성 변화는 README와 release note 양쪽에서 바로 보이게 유지한다.

### hwpx-mcp-server
- 기본 편집 도구와 고급 inspection 도구를 문서에서 더 분리한다.
- 안전한 편집 경로와 깊은 구조 점검 경로를 별도 사용 시나리오로 보여준다.

### hwpx-skill
- examples/references/scripts를 계속 분리하되, 설치 직후 어디로 들어가야 하는지 더 선명하게 연결한다.

## 한 줄 결론

**docx4j에서 배울 핵심은 복잡함을 없애는 게 아니라, 그 복잡함이 초보자 진입로를 오염시키지 않게 문서와 샘플로 층을 나누는 방식이다.**

## 참고
- https://github.com/plutext/docx4j
- https://github.com/plutext/docx4j/tree/master/docs
- https://raw.githubusercontent.com/plutext/docx4j/master/docs/Docx4j_GettingStarted.html
