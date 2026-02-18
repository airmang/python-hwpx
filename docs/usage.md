# 사용 가이드

python-hwpx-codex는 HWPX 컨테이너를 검증하고 편집하기 위한 여러 계층의 API를 제공합니다. 이 문서에서는 패키지 수준에서 문서를 여는 방법부터 문단과 주석을 다루는 고수준 도구까지 핵심 사용 패턴을 소개합니다.

## 빠른 예제 모음

### 예제 1: 문단 수 세기

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
print("paragraphs:", len(document.paragraphs))
```

### 예제 2: 빈 템플릿으로 새 문서 생성

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
document.add_paragraph("첫 문단입니다.")
document.save("new-document.hwpx")
```

### 예제 3: 특정 단어 일괄 교체

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
document.replace_text_in_runs("TODO", "DONE", text_color="#FF0000")
document.save("my-document-updated.hwpx")
```

### 예제 4: 문서 전체 메모 확인

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
for memo in document.memos:
    print(memo.id, memo.text)
```

### 예제 5: 매니페스트에서 섹션 경로 추출

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
print(document.package.section_paths())
```


### 예제 6: 메모리 버퍼로 저장하기

```python
from io import BytesIO

from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
buffer = BytesIO()
document.save(buffer)
raw_bytes = buffer.getvalue()
print("bytes:", len(raw_bytes))
```

### 예제 7: 다른 파일명으로 저장하기

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
document.save("output/copy.hwpx")
```

### 예제 8: 바이트 스트림에서 열기

```python
from io import BytesIO
from pathlib import Path

from hwpx import HwpxDocument

raw = Path("my-document.hwpx").read_bytes()
document = HwpxDocument.open(BytesIO(raw))
```

### 예제 9: 페이지 크기 확인

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
section = document.sections[0]
size = section.properties.page_size
print(size.width, size.height, size.orientation)
```

### 예제 10: 가로 방향 페이지로 전환

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
section = document.sections[0]
section.properties.set_page_size(width=297000, height=210000, orientation="LANDSCAPE")
```

### 예제 11: 여백 조정하기

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
section = document.sections[0]
section.properties.set_page_margins(left=1800, right=1800, top=2000, bottom=2000)
```

### 예제 12: 번호 매기기 시작값 읽기

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
section = document.sections[0]
start = section.properties.start_numbering
print(start.page_starts_on, start.page)
```

### 예제 13: 번호 매기기 시작값 변경

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
section = document.sections[0]
section.properties.set_start_numbering(page=3, table=1)
```

### 예제 14: 머리말 텍스트 설정

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
section = document.sections[0]
header = section.properties.set_header_text("Confidential", page_type="BOTH")
print(header.apply_page_type)
```

`set_header_text()`과 `set_footer_text()`는 새 헤더/꼬리말 파트를 만들거나 기존 텍스트를 교체할 뿐 아니라, 같은 구역의 `<hp:headerApply>`/`<hp:footerApply>` 노드와 연결된 마스터 페이지 참조까지 일관되게 유지합니다. 위 예제의 `apply_page_type` 속성은 방금 요청한 페이지 유형(`BOTH`)으로 자동 설정됩니다.

### 예제 15: 머리말 제거

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
section = document.sections[0]
section.properties.remove_header()
```

헤더나 꼬리말을 제거하면 `<hp:headerApply>`/`<hp:footerApply>` 노드와 마스터 페이지 링크도 함께 정리되므로, 편집기에서 더 이상 이전 머리말이 표시되지 않습니다.

### 예제 16: 홀수 페이지 꼬리말 넣기

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
section = document.sections[0]
section.properties.set_footer_text("© Company", page_type="ODD")
```

페이지 유형을 변경할 때마다 구역의 `<hp:footerApply>` 노드가 동일한 유형으로 갱신되고, 필요한 경우 마스터 페이지 목록에 새로운 참조가 생성됩니다.

### 예제 17: 헤더 파트 이름 나열

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
print([header.part_name for header in document.headers])
```

### 예제 18: 메모 모양 ID 확인

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
print(sorted(document.memo_shapes.keys()))
```

### 예제 19: 특정 메모 모양 살펴보기

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
shape = document.memo_shape("0")
if shape:
    print(shape.memo_type, shape.line_color)
```

### 예제 20: 두 번째 섹션에 메모 추가

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
memo = document.add_memo("검토 메모", section_index=0, memo_shape_id_ref="0")
print(memo.text)
```

### 예제 21: 메모를 필드와 함께 앵커링

```python
from datetime import datetime

from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
section = document.sections[0]
paragraph = document.add_paragraph("앵커 단락", section=section)
memo, _, field_id = document.add_memo_with_anchor(
    "승인 필요",
    paragraph=paragraph,
    memo_shape_id_ref="0",
    author="PM",
    created=datetime.now(),
)
print(field_id)
```

### 예제 22: 조건에 맞는 메모 삭제

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
for memo in list(document.memos):
    if memo.text.startswith("임시"):
        document.remove_memo(memo)
```

### 예제 23: 새 문자 서식 확보

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
style_id = document.ensure_run_style(bold=True, underline=True)
print("style id:", style_id)
```

### 예제 24: 굵고 밑줄 친 런 추가

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
section = document.sections[0]
paragraph = document.add_paragraph("기본 문단", section=section)
paragraph.add_run("강조 텍스트", bold=True, underline=True)
```

### 예제 25: 기존 런을 기울임 처리

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
paragraph = document.paragraphs[0]
if paragraph.runs:
    paragraph.runs[0].italic = True
```

### 예제 26: 특정 서식 ID로 런 찾기

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
style_id = document.ensure_run_style(bold=True)
matches = document.find_runs_by_style(char_pr_id_ref=style_id)
print("bold runs:", len(matches))
```

### 예제 27: TODO 한 건만 치환하기

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
changed = document.replace_text_in_runs("TODO", "DONE", limit=1)
print("replaced:", changed)
```

### 예제 28: 모든 런 텍스트 이어 붙이기

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
all_text = "".join(run.text for run in document.iter_runs())
print(all_text[:80])
```

### 예제 29: 첫 문단 텍스트 교체

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
if document.paragraphs:
    document.paragraphs[0].text = "새로운 첫 문단"
```

### 예제 30: 첫 런의 텍스트 읽기

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
if document.paragraphs and document.paragraphs[0].runs:
    print(document.paragraphs[0].runs[0].text)
```

### 예제 31: 첫 런 삭제

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
if document.paragraphs and document.paragraphs[0].runs:
    document.paragraphs[0].runs[0].remove()
```

### 예제 32: 고정 폭 표 만들기

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
section = document.sections[0]
table = document.add_table(rows=3, cols=3, section=section, width=54000)
```

`add_table()`은 문서에 등록된 테두리 채우기가 없으면 헤더 참조 목록에 기본 실선 `borderFill`을 자동으로 추가하고 표 전체에 그 ID를 연결합니다. 생성된 항목은 `document.border_fills` 또는 `document.border_fill("0")`으로 확인할 수 있습니다.

### 예제 33: 표 헤더 병합

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
section = document.sections[0]
table = document.add_table(rows=2, cols=3, section=section)
table.merge_cells(0, 0, 0, 2)
```

병합된 표의 상태를 점검하려면 `iter_grid()` 또는 `get_cell_map()`으로 논리 좌표와 실제 셀을 매핑할 수 있습니다. `logical=True` 옵션을 사용하면 논리 좌표 기준으로 텍스트를 갱신하고, `split_merged=True`를 추가하면 병합을 해제한 뒤 값을 기록합니다.

```python
header_map = table.get_cell_map()[0]
for entry in header_map:
    print(entry.column, "=>", entry.anchor, "span", entry.span)

table.set_cell_text(0, 1, "실적", logical=True)
table.set_cell_text(0, 2, "예상", logical=True, split_merged=True)
```

### 예제 34: 셀 너비 조정

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
section = document.sections[0]
table = document.add_table(rows=2, cols=2, section=section)
cell = table.cell(1, 0)
cell.set_size(width=7200)
```

### 예제 35: 표 행·열 수 확인

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
section = document.sections[0]
table = document.add_table(rows=4, cols=2, section=section)
print(table.row_count, table.column_count)
```

### 예제 36: 도형 삽입

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
section = document.sections[0]
shape = document.add_shape("rect", section=section, attributes={"width": "9000", "height": "4500"})
```

### 예제 37: 도형 속성 수정

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
shape = document.add_shape("rect", section=document.sections[0])
shape.set_attribute("width", "12000")
```

### 예제 38: 컨트롤 객체 추가

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
control = document.add_control(section=document.sections[0], control_type="LINE", attributes={"id": "line1"})
```

### 예제 39: 컨트롤 속성 변경

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
control = document.add_control(section=document.sections[0], control_type="LINE")
control.set_attribute("dirty", "false")
```

### 예제 40: 섹션 파트 이름 확인

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
print([section.part_name for section in document.sections])
```

### 예제 41: 헤더 경로 목록 확인

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
print(document.package.header_paths())
```

### 예제 42: 섹션 경로 목록 확인

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
print(document.package.section_paths())
```

### 예제 43: 패키지 파트 이름 나열

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
print(document.package.part_names())
```

### 예제 44: 헤더 파트 바이트 길이 확인

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
header_paths = document.package.header_paths()
if header_paths:
    data = document.package.get_part(header_paths[0])
    print("header bytes:", len(data))
```

### 예제 45: version.xml 텍스트 읽기

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
version_text = document.package.get_text("version.xml")
print(version_text.splitlines()[0])
```

### 예제 46: version.xml 속성 수정

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
version_xml = document.package.get_xml("version.xml")
version_xml.set("writer", "python-hwpx")
document.package.set_xml("version.xml", version_xml)
```

### 예제 47: 새 파트 추가하기

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
document.package.set_part("META-INF/notes.txt", "Generated with python-hwpx")
```

### 예제 48: 문자 서식 ID 나열

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
for style_id in sorted(document.char_properties.keys()):
    print("style:", style_id)
```

### 예제 49: 문자 서식 세부 정보 조회

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
style_id = document.ensure_run_style(bold=True)
style = document.char_property(style_id)
if style:
    print(style.text_color(), style.underline_type())
```

### 예제 50: TODO 문단 찾아 출력

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
for paragraph in document.paragraphs:
    if "TODO" in paragraph.text:
        print(paragraph.text)
```

### 예제 51: 섹션별 문단 수 계산

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
counts = [len(section.paragraphs) for section in document.sections]
print(counts)
```

### 예제 52: 현재 여백 값 읽기

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
section = document.sections[0]
margins = section.properties.page_margins
print(margins.left, margins.right)
```

### 예제 53: 전체 번호 초기값 설정

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
section = document.sections[0]
section.properties.set_begin_numbering(page=1, table=1)
```

### 예제 54: 헤더 번호 초기값 읽기

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
if document.headers:
    begin = document.headers[0].begin_numbering
    print(begin.page, begin.table)
```

### 예제 55: 헤더 번호 초기값 조정

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
if document.headers:
    document.headers[0].set_begin_numbering(page=1, table=1)
```

### 예제 56: 헤더 글머리표 정의 나열

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
for bullet_id, bullet in sorted(document.bullets.items()):
    print(bullet_id, bullet.char, bullet.para_head.align)
```

### 예제 57: 문단/스타일 참조 살펴보기

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
para_pr = document.paragraph_property("1")
style = document.style("0")
if para_pr and style:
    print(para_pr.align.horizontal, para_pr.tab_pr_id_ref, style.name)
```

### 예제 58: 변경 추적과 작성자 정보 확인

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
change = document.track_change("1")
if change:
    author = document.track_change_author(change.author_id)
    if author:
        print(change.change_type, author.name, author.color)
```

### 예제 59: 바탕쪽 이름 수정하기

```python
from hwpx import HwpxDocument

HM = "{http://www.hancom.co.kr/hwpml/2011/master-page}"

document = HwpxDocument.open("my-document.hwpx")
if document.master_pages:
    master = document.master_pages[0]
    item = master.element.find(f"{HM}masterPageItem")
    if item is not None:
        item.set("name", "보고서 바탕쪽")
        master.mark_dirty()
document.save("my-document.hwpx")
```

### 예제 60: 문서 이력 주석 갱신

```python
from hwpx import HwpxDocument

HHS = "{http://www.hancom.co.kr/hwpml/2011/history}"

document = HwpxDocument.open("my-document.hwpx")
for history in document.histories:
    comment = history.element.find(f"{HHS}historyEntry/{HHS}comment")
    if comment is not None:
        comment.text = "QA 점검 완료"
        history.mark_dirty()
document.save("my-document.hwpx")
```

### 예제 61: 버전 메타데이터 업데이트

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("my-document.hwpx")
if document.version:
    document.version.element.set("appVersion", "15.0.0.100 WIN32")
    document.version.mark_dirty()
    document.save("my-document.hwpx")
```


## 패키지 열기와 기본 점검

`hwpx.opc.package.HwpxPackage`는 OPC 컨테이너 전체를 메모리에 적재하면서 필수 파트 존재 여부를 확인합니다. 루트 파일 목록과 `version.xml`에 기록된 메타데이터는 구조 검증과 후속 편집 단계에서 활용할 수 있습니다.

```python
from hwpx import HwpxPackage

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
from hwpx import HwpxDocument

document = HwpxDocument.open("sample.hwpx")
section = document.sections[0]

paragraph = document.add_paragraph(
    "자동 생성된 문단",
    section=section,
    para_pr_id_ref=3,
    char_pr_id_ref=5,
)
paragraph.set_attribute("outlineLevel", "1")

# 표를 추가하고 헤더 행을 병합합니다. border_fill_id_ref를 생략하면 기본 실선 채우기가 자동 생성됩니다.
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

`HwpxDocument.sections`, `HwpxDocument.paragraphs`, `HwpxDocument.headers` 속성은 각각 구역, 모든 문단, 헤더 파트를 리스트로 반환합니다. 섹션 속성(`section.properties`)을 사용하면 페이지 크기, 여백, 바탕쪽 연결과 같은 레이아웃 설정도 쉽게 변경할 수 있습니다. 매니페스트에 등록된 바탕쪽(`document.master_pages`), 문서 이력(`document.histories`), 버전(`document.version`) 파트도 동일한 방식으로 노출되므로 XML 트리를 직접 수정한 뒤 `mark_dirty()`만 호출하면 저장 시 함께 반영됩니다.

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

반환된 `RunStyle` 객체(`run.style`)를 사용하면 문자 색상, 밑줄 색상 등 서식 속성을 직접 확인할 수 있습니다. 치환기는 하이라이트 마커(`<hp:markpenBegin>`/`<hp:markpenEnd>`)나 태그로 나뉜 토큰도 순회하며 기존 서식 구조를 유지한 채 교체합니다.

## 본문 데이터 모델 살펴보기

`hwpx.oxml.body` 모듈은 `<hp:p>`와 `<hp:run>`을 데이터 클래스(표·컨트롤·인라인 도형·변경 추적 태그 등)로 역직렬화합니다. `HwpxOxmlParagraph.model`과 `HwpxOxmlRun.model` 속성은 이러한 구조화된 모델을 즉시 반환하며, 수정 후 `apply_model()`을 호출하면 변경 사항이 원본 XML에 반영됩니다.

```python
from hwpx.oxml.body import TrackChangeMark

paragraph = section.paragraphs[0]
model = paragraph.model
run_model = model.runs[0]

# 컨트롤 유형을 변경하고 ID 속성을 갱신합니다.
control = run_model.controls[0]
control.control_type = "PAGE_NUMBER"
control.attributes["id"] = "ctrl-updated"

# 변경 추적 태그도 타입 안전하게 접근할 수 있습니다.
span = run_model.text_spans[0]
for mark in span.marks:
    if isinstance(mark.element, TrackChangeMark) and mark.element.is_begin:
        mark.element.tc_id = 99

# 수정한 모델을 문단에 적용합니다.
paragraph.apply_model(model)
```

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
