# 순회 레시피 — 문서에서 원하는 것 꺼내기

과업 중심으로 정리한 읽기·순회 레시피다. 전부 공개 API만 사용하며, ZIP이나
XML을 직접 열 필요가 없다. 예제의 `input.hwpx`는 여러분의 문서로 바꿔 쓰면
된다.

> **Python 블록 판정:** [실행 분류 ledger](python-example-ledger.json)가 이
> current manual의 모든 Python 블록을 동결합니다. 이 문서의 블록은 모두
> 기존 입력 파일(`input.hwpx`)이 필요한 조각입니다.

## 문단 텍스트를 전부 읽기

가장 단순한 순회다. `document.paragraphs`는 본문 문단 리스트를 준다.

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("input.hwpx")
for paragraph in document.paragraphs:
    print(paragraph.text)
```

## 중첩 표 안까지, 위치 정보와 함께 통독하기

표 셀·각주 속 문단까지 포함해 "이 문단이 어디에 있는지"가 필요하면
`TextExtractor.iter_document_paragraphs()`를 쓴다. `ParagraphInfo.path`는
`sec/p[3]/run/tbl/tr[0]/tc[0]/subList/p`처럼 문단의 구조 경로를 준다.

```python
from hwpx import TextExtractor

extractor = TextExtractor("input.hwpx")
for info in extractor.iter_document_paragraphs(include_nested=True):
    marker = "  (중첩)" if info.is_nested else ""
    print(f"[{info.section.index}:{info.index}] {info.path}{marker}")
    print("   ", info.text())
```

## 각주·미주를 본문과 함께 추출하기

`extract_text()`는 기본으로 각주를 무시한다. `AnnotationOptions`로 동작을
고른다 — `"ignore"`(기본), `"placeholder"`(자리표시), `"inline"`(본문에 삽입).
각주 문단은 중첩 문단으로도 잡히므로, 인라인으로 합칠 때는
`include_nested=False`로 중복을 피한다.

```python
from hwpx import TextExtractor
from hwpx.tools.text_extractor import AnnotationOptions

extractor = TextExtractor("input.hwpx")
text = extractor.extract_text(
    include_nested=False,
    annotations=AnnotationOptions(footnote="inline", endnote="inline"),
)
print(text)
```

각주가 있는 문단은 `본문 문단이다[footnote:각주 내용이다]`처럼 나온다.
하이라이트·하이퍼링크·컨트롤도 같은 방식의 옵션이 있다(`highlight`,
`hyperlink`, `control`).

## 표를 찾아 셀 문단 읽기

구조 검색은 `ObjectFinder`가 맡는다. 태그로 요소를 찾고, 각 결과의
`path`·`section`·`text`를 읽는다. `text`는 **속성**이며, 표처럼 텍스트가
직접 없는 컨테이너 요소에서는 `None`이다 — 셀 내용은 위의
`iter_document_paragraphs()` 경로(`.../tc[i]/subList/p`)로 읽는 편이 쉽다.

```python
from hwpx import ObjectFinder

finder = ObjectFinder("input.hwpx")
for table in finder.find_all(tag="tbl"):
    print("표 위치:", table.path, "| 섹션:", table.section.index)

cells = finder.find_all(tag="tc")
print("셀 수:", len(cells))
```

## 런 단위로 서식과 함께 순회하기

굵기·색 같은 서식은 런(run)에 붙는다. 문서 전체 런을 순회하거나, 특정
서식의 런만 골라낼 수 있다.

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("input.hwpx")
for run in document.iter_runs():
    print(repr(run.text), "charPr:", run.char_pr_id_ref)

red_runs = document.find_runs_by_style(text_color="#FF0000")
print("빨간 런:", len(red_runs))
```

## 메모와 누름틀(필드) 나열하기

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("input.hwpx")
for memo in document.memos:
    print("메모:", memo.id)

for field in document.list_form_fields():
    print("누름틀:", field)
```

문서에 해당 요소가 없으면 빈 리스트가 나온다 — 예외가 아니다.

## 다음 단계

- 편집 호출이 무엇을 돌려주고 어떻게 실패하는지는 {doc}`mutation-semantics`
- 추출 전용 CLI와 더 많은 패턴은 {doc}`usage`
- 요소·속성 이름의 의미는 {doc}`schema-overview`
