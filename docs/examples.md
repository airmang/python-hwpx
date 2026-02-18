# 실전 예제

다음 예제는 python-hwpx의 주요 API를 조합해 실제 시나리오를 해결하는 방법을 보여 줍니다. `examples/` 디렉터리에 포함된 샘플 HWPX 파일(`FormattingShowcase.hwpx`)을 기준으로 작성되었으며, 해당 파일은 저장소를 직접 클론했을 때만 사용할 수 있습니다. PyPI로 설치했다면 보유 중인 HWPX 문서를 사용하거나, `hwpx.templates.blank_document_bytes()`로 임시 문서를 생성해 실습하세요.

## 0. 빈 문서를 생성해 실습 환경 만들기

```python
from io import BytesIO

from hwpx import HwpxDocument
from hwpx.templates import blank_document_bytes

document = HwpxDocument.open(BytesIO(blank_document_bytes()))
document.add_paragraph("첫 문단입니다.")
document.save("playground.hwpx")
```

## 1. 보고서 템플릿에 표와 개체 추가하기

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("examples/FormattingShowcase.hwpx")
section = document.sections[-1]

# 머리글 문단을 추가하고 강조 스타일을 적용합니다.
headline = document.add_paragraph(
    "분기별 요약",
    section=section,
    style_id_ref=1,
    char_pr_id_ref=6,
)
headline.text = "분기별 실적 요약"

# 2x3 표를 생성하고 헤더 행을 병합합니다.
table = document.add_table(
    rows=2,
    cols=3,
    section=section,
    border_fill_id_ref="3",
)
table.merge_cells(0, 0, 0, 2)

# 병합된 헤더 행은 논리 좌표를 기준으로 편집할 수 있습니다.
table.set_cell_text(0, 0, "Quarter", logical=True)
table.set_cell_text(0, 1, "Actual", logical=True)
table.set_cell_text(0, 2, "Forecast", logical=True)

# iter_grid()/get_cell_map()으로 병합 구조를 확인하거나, 필요 시 병합을 해제할 수 있습니다.
header_map = table.get_cell_map()[0]
for entry in header_map:
    print(f"({entry.row}, {entry.column}) -> anchor={entry.anchor}, span={entry.span}")
# table.split_merged_cell(0, 1)  # 병합 해제가 필요하다면 사용

# 본문 행을 채우고 셀 크기를 조정합니다.
q1_label = table.cell(1, 0)
q1_label.text = "Q1"

actual_cell = table.cell(1, 1)
actual_cell.text = "42,000"
actual_cell.set_size(width=3600)

forecast_cell = table.cell(1, 2)
forecast_cell.text = "44,500"

# 강조 도형과 컨트롤을 문단으로 추가합니다.
shape = document.add_shape(
    "rect",
    section=section,
    attributes={"width": "9000", "height": "3500", "textWrap": "SQUARE"},
)
shape.set_attribute("width", "9600")

document.add_control(
    section=section,
    control_type="LINE",
    attributes={"id": "guideline-1", "type": "LINE"},
)

document.save("examples/FormattingShowcase-updated.hwpx")
```

## 2. 하이라이트와 주석을 포함한 텍스트 보고서 생성하기

```python
from hwpx.tools.text_extractor import AnnotationOptions, TextExtractor

template = "* {section}:{index} — {text}"

options = AnnotationOptions(
    highlight="markers",
    footnote="inline",
    endnote="inline",
    hyperlink="target",
    control="placeholder",
    control_placeholder="[CTRL:{name}]",
)

with TextExtractor("examples/FormattingShowcase.hwpx") as extractor:
    for paragraph in extractor.iter_document_paragraphs():
        text = paragraph.text(annotations=options)
        if not text.strip():
            continue
        print(
            template.format(
                section=paragraph.section.index,
                index=paragraph.index,
                text=text.replace("\n", " "),
            )
        )
```

`AnnotationOptions`를 활용하면 하이라이트 구간이 `[HIGHLIGHT color=#ffff00]텍스트[/HIGHLIGHT]` 형태로 출력되고, 각주와 미주 내용은 인라인으로 삽입됩니다. 하이퍼링크는 실제 URL을 포함하며, 컨트롤은 `control_placeholder` 형식에 따라 자리표시자로 치환됩니다.

## 3. 특정 태그를 검색해 요약 정보 만들기

```python
from hwpx.tools.object_finder import ObjectFinder

finder = ObjectFinder("examples/FormattingShowcase.hwpx")

# 문서 내 모든 각주 요소를 찾습니다.
notes = finder.find_all(tag="hp:footNote")
print("Found", len(notes), "footnotes")

# 책갈피 ID로 시작하는 문단만 가져옵니다.
bookmarked = finder.find_all(
    tag="hp:p",
    attrs={"id": lambda value: value.startswith("bookmark")},
)
for element in bookmarked:
    print(element.section.name, element.path)
```

`ObjectFinder`는 XPath 표현식, 태그/속성 매칭, 주석 전용 이터레이터(`iter_annotations`)를 모두 지원하므로 문서 내부 구조를 탐색하거나 특정 개체만 선별하는 자동화 스크립트를 쉽게 작성할 수 있습니다.
