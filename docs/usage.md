# 사용 가이드

python-hwpx-codex는 HWPX 컨테이너를 검증하고 편집하기 위한 여러 계층의 API를 제공합니다. 이 문서에서는 패키지 수준에서 문서를 여는 방법부터 문단과 주석을 다루는 고수준 도구까지 핵심 사용 패턴을 소개합니다.

## 패키지 열기와 기본 점검

`hwpx.opc.package.HwpxPackage`는 OPC 컨테이너 전체를 메모리에 적재하면서 필수 파트 존재 여부를 확인합니다. 루트 파일 목록과 `version.xml`에 기록된 메타데이터는 구조 검증과 후속 편집 단계에서 활용할 수 있습니다.

```python
from hwpx.opc.package import HwpxPackage

package = HwpxPackage.open("sample.hwpx")
print("MIME type:", package.mimetype)
print("Declared root files:")
for rootfile in package.iter_rootfiles():
    print(f"- {rootfile.full_path} ({rootfile.media_type})")

main = package.main_content
print("Main document:", main.full_path)
```

패키지 객체는 임의의 파트를 가져오거나 수정하는 도우미 메서드도 제공합니다.

```python
manifest = package.get_xml("Contents/content.hpf")
print("Spine items:", [item.get("href") for item in manifest.findall(".//{*}item")])
```

## HwpxDocument로 문서 편집하기

고수준 `hwpx.document.HwpxDocument`는 섹션, 문단, 헤더 파트를 파이썬 객체로 노출하며, 새 문단/표/개체를 생성하는 편의 메서드를 제공합니다.

```python
from hwpx.document import HwpxDocument

document = HwpxDocument.open("sample.hwpx")
section = document.sections[0]

paragraph = document.add_paragraph(
    "자동 생성된 문단",
    section=section,
    para_pr_id_ref=3,
    char_pr_id_ref=5,
)
paragraph.set_attribute("outlineLevel", "1")

# 표를 추가하고 헤더 행을 병합합니다.
table = document.add_table(2, 3, section=section, border_fill_id_ref="2")
table.set_cell_text(0, 0, "Quarter")
table.set_cell_text(0, 1, "Actual")
table.set_cell_text(0, 2, "Forecast")
table.merge_cells(0, 0, 0, 2)
table.cell(1, 0).text = "Q1"

# 개체와 컨트롤도 문서 또는 문단 수준에서 추가할 수 있습니다.
shape = document.add_shape(
    "rect",
    section=section,
    attributes={"width": "9000", "height": "4500"},
)
control = document.add_control(
    section=section,
    control_type="LINE",
    attributes={"id": "ctrl1"},
)
```

`HwpxDocument.sections`, `HwpxDocument.paragraphs`, `HwpxDocument.headers` 속성은 각각 구역, 모든 문단, 헤더 파트를 리스트로 반환합니다. 섹션 속성(`section.properties`)을 사용하면 페이지 크기, 여백, 바탕쪽 연결과 같은 레이아웃 설정도 쉽게 변경할 수 있습니다.

```python
options = section.properties
options.set_page_size(width=72000, height=43200, orientation="WIDELY")
options.set_page_margins(left=2000, right=2000, header=1500, footer=1500)

document.headers[0].set_begin_numbering(page=1)
```

## 메모 다루기

문서에 첨부된 메모는 섹션의 `<hp:memogroup>` 요소와 헤더의 `memoProperties` 정의를 통해 연결됩니다. `HwpxDocument.memos` 속성은 모든 섹션에 포함된 메모 객체를 반환하며, `add_memo()`/`remove_memo()`를 사용하면 새 메모를 생성하거나 삭제할 수 있습니다.

```python
# 메모 모양 정의는 header.ref_list.memo_properties 또는 document.memo_shapes로 조회할 수 있습니다.
default_shape = next(iter(document.memo_shapes))  # 첫 번째 모양 ID

memo = document.add_memo(
    "검토 의견을 정리했습니다.",
    section=section,
    memo_shape_id_ref=default_shape,
)
memo.text = "표 1은 최신 수치로 업데이트가 필요합니다."

for existing in document.memos:
    print(existing.id, existing.memo_shape_id_ref, existing.text)

document.remove_memo(memo)
```

> **주의:** 한글 편집기에서 메모 풍선을 표시하려면 본문 문단에 대응되는 MEMO 필드 컨트롤(`hp:fieldBegin`/`hp:fieldEnd`)이 있어야 합니다.

```python
todo = document.add_paragraph("TODO: QA 서명", section=section, char_pr_id_ref=10)

document.add_memo_with_anchor(
    "배포 전 QA 서명을 확인하세요.",
    paragraph=todo,
    memo_shape_id_ref="0",
    memo_id="release-memo-qa",
    char_pr_id_ref="10",
    attributes={"author": "QA"},
    anchor_char_pr_id_ref="10",
)
```

`examples/build_release_checklist.py`는 이러한 과정을 자동화하여 QA 점검용 문서를 생성하는 스크립트입니다.

## 스타일 기반 텍스트 변환

런(`HwpxOxmlRun`)은 `charPrIDRef`를 통해 헤더의 문자 서식(`charPr`)과 연결됩니다. `HwpxDocument.find_runs_by_style()`는 색상, 밑줄 종류, 문자 속성 ID 등의 조건으로 런을 필터링하고, `replace_text_in_runs()`는 선택된 런 내부의 부분 문자열만 치환하거나 삭제합니다.

```python
# 빨간색 텍스트에만 TODO 태그가 남아 있는지 검사합니다.
for run in document.find_runs_by_style(text_color="#FF0000"):
    if "TODO" in run.text:
        print("검토 필요:", run.text)

# 빨간색 텍스트에서 TODO를 DONE으로 교체하고, 최대 두 번만 수행합니다.
document.replace_text_in_runs(
    "TODO",
    "DONE",
    text_color="#FF0000",
    limit=2,
)

# 밑줄이 그어진 텍스트에서 임시 주석을 제거합니다.
document.replace_text_in_runs(
    "(draft)",
    "",
    underline_type="SOLID",
)
```

반환된 `RunStyle` 객체(`run.style`)를 사용하면 문자 색상, 밑줄 색상 등 서식 속성을 직접 확인할 수 있습니다. 치환기는 단일 `<hp:t>` 하위 요소를 가진 단순 런에 최적화되어 있으며, 텍스트 마크업이 중첩된 복잡한 구조에서는 예상과 다른 결과가 나올 수 있습니다.

## 런 서식 지정

헤더의 `<hh:charPr>` 정의는 여러 런이 공유하는 문자 서식을 담고 있습니다. `HwpxDocument.ensure_run_style()`은 굵게/기울임/밑줄 조합에 맞는 `charPr` 항목을 찾아 ID를 반환하고, 필요한 경우 새 항목을 생성합니다. 문단 객체는 `add_run()` 메서드를 통해 해당 서식을 즉시 사용하는 런을 만들 수 있습니다.

```python
section = document.sections[0]
paragraph = section.paragraphs[0]

# 굵은 밑줄 서식을 확보하고, 동일한 서식을 가진 런을 추가합니다.
style_id = document.ensure_run_style(bold=True, underline=True)
run = paragraph.add_run("강조된 텍스트", bold=True, underline=True)

# 반환된 런은 즉시 서식 토글 속성을 제공합니다.
run.italic = True  # 새로운 charPr가 생성되고 참조가 갱신됩니다.
assert run.bold is True and run.underline is True
```

런의 `bold`, `italic`, `underline` 속성은 문서와 연결된 상태에서만 동작하며, 속성을 변경하면 헤더의 `charProperties` 목록과 관련 캐시가 자동으로 업데이트됩니다.

편집이 끝나면 `HwpxDocument.save()`를 호출해 변경 사항을 원본 또는 새 파일에 기록합니다.

```python
document.save("edited.hwpx")
```

## 텍스트 추출과 주석 표현

`hwpx.tools.text_extractor.TextExtractor`는 섹션과 문단을 순회하며 텍스트를 문자열로 변환합니다. `AnnotationOptions`를 통해 하이라이트, 각주, 하이퍼링크, 컨트롤 등 주석 요소의 표현 방식을 제어할 수 있습니다.

```python
from hwpx.tools.text_extractor import AnnotationOptions, TextExtractor

options = AnnotationOptions(
    highlight="markers",
    footnote="inline",
    endnote="placeholder",
    note_inline_format="[{kind}:{text}]",
    note_placeholder="[{kind}:{inst_id}]",
    hyperlink="target",
    hyperlink_target_format="[LINK:{target}]",
    control="placeholder",
    control_placeholder="[CTRL {name} {type}]",
)

with TextExtractor("sample.hwpx") as extractor:
    for paragraph in extractor.iter_document_paragraphs():
        text = paragraph.text(annotations=options)
        if text.strip():
            print(text)
```

문단 객체(`ParagraphInfo`)의 `text()` 메서드에는 추가로 다음과 같은 인자를 전달할 수 있습니다.

- `object_behavior`: 표, 도형 등 인라인 개체를 `"skip"`, `"placeholder"`, `"nested"` 중 하나로 처리합니다.
- `object_placeholder`: 자리표시자 모드를 사용할 때 형식을 지정합니다.
- `preserve_breaks`: 줄바꿈과 탭을 유지할지 여부를 결정합니다.

`iter_sections()`와 `iter_paragraphs()` 메서드를 사용하면 원하는 구역에만 접근하거나 중첩 문단을 제외하는 등 탐색 범위를 세밀하게 조정할 수 있습니다.

## ObjectFinder로 요소 검색하기

`hwpx.tools.object_finder.ObjectFinder`는 XPath, 태그/속성 필터를 기반으로 XML 요소를 찾아내는 고수준 API입니다. 텍스트 추출 옵션과 동일한 주석 렌더링 설정을 재사용할 수 있습니다.

```python
from hwpx.tools.object_finder import ObjectFinder
from hwpx.tools.text_extractor import AnnotationOptions

finder = ObjectFinder("sample.hwpx")
options = AnnotationOptions(hyperlink="target", control="placeholder")

for match in finder.iter_annotations(options=options):
    print(match.kind, match.value, match.element.path)
```

특정 태그나 속성을 찾고 싶다면 `find_all()`/`find_first()` 메서드를 사용할 수 있습니다.

```python
paragraphs_with_bookmark = finder.find_all(
    tag=("hp:p", "hp:run"),
    attrs={"id": lambda value: value.startswith("bookmark")},
)
for element in paragraphs_with_bookmark:
    print(element.section.name, element.path)
```

## 변경 사항 저장과 결과물 확인

`HwpxDocument.save()`는 내부적으로 `hwpx.package.HwpxPackage.save()`를 호출하여 수정된 파트만 새 ZIP 아카이브로 직렬화합니다. 저장 대상 경로를 생략하면 원본 파일을 덮어쓰고, 파일 객체나 바이트 버퍼를 전달하면 인메모리 출력도 지원합니다.

```python
buffer = document.save()  # 원본 경로가 없을 때는 bytes 를 반환
with open("result.hwpx", "wb") as fp:
    fp.write(buffer)
```

패키지 수준에서 바로 작업하고 싶다면 `HwpxPackage.set_part()`/`save()`를 사용해 XML 조각을 교체할 수도 있습니다. 다만 고수준 API(`HwpxDocument`)를 통해 편집한 경우에는 `document.save()`를 호출해 내부 캐시 상태를 깨끗하게 유지하는 것이 좋습니다.
