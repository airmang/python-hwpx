# Benchmark Pass 1: python-docx

검토일: 2026-04-16
대상: `python-openxml/python-docx`

## 왜 봤나

`python-docx`는 Python 문서 라이브러리에서 가장 이해하기 쉬운 사용자 표면 중 하나다. HWPX 스택 기준으로는 특히 `python-hwpx`의 고수준 API 설계와 문서/예제 구조를 비교하기 좋다.

## 바로 보이는 강점

1. **첫 성공 경험이 짧다**
- `Document()` → `add_paragraph()` → `save()` 한 흐름만으로 바로 성공한다.
- README 첫 예제가 아주 짧다.

2. **문서 구조가 API 구조와 잘 맞는다**
- documents, tables, text, sections, headers/footers, styles처럼 사용자가 생각하는 단위로 문서가 조직돼 있다.

3. **고수준 객체 모델이 선명하다**
- Document / Paragraph / Run / Table 같은 기본 객체가 명확하다.
- 초보 사용자가 내부 XML을 몰라도 된다.

## HWPX 스택에 가져올 점

### 1. `python-hwpx` quick success path를 더 짧게 보여주기
지금도 기능은 많다. 하지만 첫 예제는 여전히 HWPX 도메인 설명이 먼저 들어간다. `python-docx`처럼 가장 짧은 happy path를 더 앞에 내세우는 편이 낫다.

권장 액션:
- README 상단에 5줄짜리 최소 예제를 더 전면 배치
- `new/open/add/save` 중심 quickstart를 가장 먼저 노출

### 2. 사용 가이드를 객체 단위로 재정렬 검토
`python-docx`는 사용자가 찾는 단위와 문서 단위가 거의 같다. `python-hwpx`도 기능이 늘수록 문서 인덱스를 `문단/표/텍스트/스타일/추출/검증` 같은 객체 중심으로 더 세우는 게 좋다.

### 3. 고급 기능과 기본 기능의 심리적 거리 벌리기
`python-docx`는 고급 API가 있어도 초반 경험을 방해하지 않는다. `python-hwpx`도 XML-first 강점을 유지하되, 초반 진입부에서는 저수준 제어를 뒤로 빼는 편이 낫다.

## 그대로 베끼면 안 되는 점

- DOCX와 HWPX는 포맷과 생태계가 다르다.
- `python-hwpx`는 검증, namespace, package 구조 등 HWPX 특유의 문제를 더 많이 설명해야 한다.
- 따라서 단순함만 좇으면 HWPX의 실제 위험을 숨기게 된다.

## 적용 우선순위

1. README quick success path 강화
2. 사용 가이드 인덱스의 객체 중심 재정렬 검토
3. 기본 API와 XML/패키지 고급 기능의 문서 분리 강화

한 줄 결론:

**`python-docx`에서 배울 핵심은 기능 수가 아니라, 사용자가 첫 5분 안에 성공하게 만드는 표면 설계다.**
