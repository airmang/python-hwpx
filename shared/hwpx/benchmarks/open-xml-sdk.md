# Benchmark Note: Open XML SDK

## 왜 봤나

`Open XML SDK`는 문서 포맷 라이브러리의 정석급 기준점이다. HWPX와 포맷은 다르지만, ZIP + XML 기반 문서 조작 라이브러리로서 다음 질문에 답을 준다.

- 저수준 패키지와 고수준 모델을 어떻게 함께 노출하는가
- 검증 기능을 어떻게 제품의 일부로 다루는가
- 문서 포맷 안정성과 breaking change를 어떻게 운영하는가

## 관찰

### 1. 고수준 모델과 저수준 패키지를 둘 다 인정한다

GitHub README는 SDK가 low-level OPC package 조작, strongly-typed classes, LINQ to XML까지 함께 제공한다고 명시한다.

핵심 인상:
- 추상화를 강요하지 않는다.
- 대신 계층을 분명히 보여준다.
- 사용자는 작업 난이도에 따라 위계적으로 내려갈 수 있다.

HWPX 스택에 주는 시사점:
- `python-hwpx`도 고수준 편집 API와 패키지/XML 접근을 모두 갖고 있다.
- 문제는 기능 부족보다 **노출 순서**다.
- 초보자에게는 고수준 경로를 먼저, 고급 사용자에게는 패키지 경로를 별도로 보여주는 편이 낫다.

### 2. 검증이 옵션이 아니라 제품 표면이다

Microsoft Learn의 `OpenXmlValidator` 문서는 validator 클래스를 독립된 핵심 표면으로 취급한다.

핵심 인상:
- validate는 부가 기능이 아니다.
- 특정 element와 package 둘 다 검증할 수 있다.
- 오류 개수 제한 같은 운용 관점도 드러난다.

HWPX 스택에 주는 시사점:
- `validate_structure`, `lint_text_conventions` 같은 기능은 더 밀어줄 가치가 있다.
- 지금은 advanced zone에만 있지만, release/automation 문맥에서는 핵심이다.
- `python-hwpx`와 `hwpx-mcp-server` 모두에서 검증 흐름을 더 공식화할 필요가 있다.

### 3. 문서는 능력 과시보다 문제 유형 중심이다

README와 Learn 문서는 "무엇을 할 수 있는가"를 작업 유형으로 보여준다.

예:
- 생성
- 수정
- 검색/치환
- 분해/병합
- 차트/임베디드 데이터 갱신

HWPX 스택에 주는 시사점:
- 현재 문서는 기능이 많지만, 사용자 작업 유형으로 더 재정렬할 여지가 있다.
- 특히 `python-hwpx` docs index는 작업별 바로가기가 중요하다.

### 4. breaking change를 숨기지 않는다

README는 `3.0.0` breaking changes를 전면에서 언급한다.

핵심 인상:
- 사용자에게 불편한 사실도 초기에 알려준다.
- changelog와 milestone을 함께 연결한다.

HWPX 스택에 주는 시사점:
- `python-hwpx` 버전 변화가 `hwpx-mcp-server`, `hwpx-skill`에 미치는 영향은 더 구조적으로 기록해야 한다.
- support matrix와 release note 연결은 계속 강화해야 한다.

## 바로 흡수할 액션

### python-hwpx
- docs 첫 화면에서 작업별 진입점을 더 강하게 제공한다.
- quickstart는 고수준 편집 경로를 우선 배치한다.
- XML/패키지 레벨은 심화 주제로 분리 노출한다.

### hwpx-mcp-server
- 구조/텍스트/검증 도구를 단순 읽기 도구와 고급 점검 도구로 더 분명히 나눈다.
- edit 계열은 preview/apply/validate 흐름을 강조한다.

### hwpx-skill
- 설치 후 검증 루프에서 "생성 -> 추출 -> 치환 -> 재검수"를 표준 경로로 노출한다.

## 한 줄 결론

**Open XML SDK는 기능 자체보다 계층화와 검증 표면이 강하다. HWPX 스택도 그 방향으로 더 선명해져야 한다.**

## 참고
- https://github.com/dotnet/Open-XML-SDK
- https://learn.microsoft.com/en-us/office/open-xml/open-xml-sdk
- https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.validation.openxmlvalidator
