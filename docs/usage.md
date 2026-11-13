# 사용 가이드

python-hwpx는 HWPX 컨테이너를 검증하고 편집하기 위한 여러 계층의 API를 제공합니다. 이 문서에서는 패키지 수준에서 문서를 여는 방법부터 문단과 주석을 다루는 고수준 도구까지 핵심 사용 패턴을 소개합니다.

> **Python 블록 판정:** [실행 분류 ledger](python-example-ledger.json)가 이
> current manual의 모든 Python 블록을 동결합니다. **독립 실행 예제** 표시가
> 없는 블록은 기존 입력 파일이나 앞 문맥이 필요한 조각입니다.

> **예제 관례** — 아래 예제는 대부분 `HwpxDocument.new()` 로 시작한다. 붙여넣어
> 그대로 실행되게 하기 위해서다(문서 예제는 CI 가 설치된 휠에서 실행한다).
> 자기 파일에 쓰려면 그 줄을 `HwpxDocument.open("your-document.hwpx")` 로 바꾸면
> 된다 — 나머지는 같다.

## CLI 워크플로

라이브러리 API 외에도 템플릿 보존형 작업 흐름을 위한 CLI를 제공합니다.

```bash
# 패키지 구조 점검
hwpx-validate-package sample.hwpx

# XML-first 편집용 unpack / pack (기본값: XML/HWPF 바이트 보존)
hwpx-unpack sample.hwpx ./sample-unpacked
hwpx-unpack sample.hwpx ./sample-pretty --pretty-xml
hwpx-pack ./sample-unpacked ./sample-repacked.hwpx

# 템플릿 분석과 작업 디렉터리 추출
hwpx-analyze-template sample.hwpx --extract-dir ./template-parts --json
hwpx-pack ./template-parts ./template-roundtrip.hwpx
hwpx-validate-package ./template-roundtrip.hwpx

# 텍스트 추출
hwpx-text-extract sample.hwpx --format markdown --output sample.md

# 문서 구조 변화 징후 점검
hwpx-page-guard --reference sample.hwpx --output edited.hwpx

# 서식 규칙 파일에 맞는지 점검
hwpx-check-format rules.json sample.hwpx
```

`hwpx-check-format`은 글자 모양·문단 모양·표·문자 범위·하이퍼링크·매크로가 규칙 파일(JSON)에 맞는지 봅니다. 규칙의 항목 이름과 단위는 한컴이 공개한 검사기([hancom-io/dvc](https://github.com/hancom-io/dvc))와 같습니다(`fontsize`는 1/100pt, 길이는 HWPUNIT). 지원하는 항목은 `hwpx.tools.format_rules.SUPPORTED_RULES`에 있고, 그 밖의 항목은 건너뛰지 않고 "점검하지 않음"으로 알립니다. 어긋난 곳은 구역·문단 번호와 그 자리의 글로 알려 주며, 쪽·줄 번호는 주지 않습니다. 규칙에 맞으면 종료 코드 0, 어긋나면 1입니다.

`hwpx-page-guard`는 실제 렌더러의 쪽수를 계산하지 않고, 구조 및 텍스트 통계를 비교해 편집 전후 변화 징후를 점검하는 도구입니다.

`hwpx-validate-package`는 고정 기본 경로를 전제로 두지 않고 `container.xml`과 실제 rootfile/manifest 관계를 따라가며 검사합니다. 엔진이 열 수 있는 비표준 패키지는 에러 대신 경고로 분리해 볼 수 있습니다.

`hwpx-analyze-template --extract-dir`는 `mimetype`, `META-INF/container.xml`, rootfile, manifest 관련 파일, 중요 자산, `.hwpx-pack-metadata.json`을 포함한 작업 디렉터리를 만듭니다. 다시 묶고 구조를 점검하는 흐름을 돕기 위한 것이며, 렌더링 결과까지 보장하지는 않습니다.

## 빠른 예제 모음

### 예제 1: 문단 수 세기

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
print("paragraphs:", len(document.paragraphs))
```

### 예제 2: 빈 템플릿으로 새 문서 생성

**독립 실행 예제** — 빈 작업 디렉터리와 core wheel만으로 실행됩니다.
<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
document.add_paragraph("첫 문단입니다.")
document.save_to_path("new-document.hwpx")
```

### 예제 3: 특정 단어 일괄 교체

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
document.text.replace("TODO", "DONE", text_color="#FF0000")
document.save_to_path("my-document-updated.hwpx")
```

### 예제 4: 문서 전체 메모 확인

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
for memo in document.notes.memos:
    print(memo.id, memo.text)
```

### 예제 5: 매니페스트에서 섹션 경로 추출

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
print(document.package.section_paths())
```


### 예제 6: 메모리 버퍼로 저장하기

<!-- standalone-python-example -->

```python
from io import BytesIO

from hwpx import HwpxDocument

document = HwpxDocument.new()
buffer = BytesIO()
document.save_to_stream(buffer)
raw_bytes = buffer.getvalue()
print("bytes:", len(raw_bytes))
```

### 예제 7: 다른 파일명으로 저장하기

<!-- standalone-python-example -->

```python
from pathlib import Path

from hwpx import HwpxDocument

Path("output").mkdir(parents=True, exist_ok=True)

document = HwpxDocument.new()
document.save_to_path("output/copy.hwpx")
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

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
section = document.sections[0]
size = section.properties.page_size
print(size.width, size.height, size.orientation)
```

### 예제 10: 가로 방향 페이지로 전환

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
section = document.sections[0]
section.properties.set_page_size(width=297000, height=210000, orientation="LANDSCAPE")
```

### 예제 11: 여백 조정하기

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
section = document.sections[0]
section.properties.set_page_margins(left=1800, right=1800, top=2000, bottom=2000)
```

### 예제 12: 번호 매기기 시작값 읽기

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
section = document.sections[0]
start = section.properties.start_numbering
print(start.page_starts_on, start.page)
```

### 예제 13: 번호 매기기 시작값 변경

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
section = document.sections[0]
section.properties.set_start_numbering(page=3, table=1)
```

### 예제 14: 머리말 텍스트 설정

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
section = document.sections[0]
header = section.properties.set_header_text("Confidential", page_type="BOTH")
print(header.apply_page_type)
```

`set_header_text()`과 `set_footer_text()`는 새 헤더/꼬리말 파트를 만들거나 기존 텍스트를 교체할 뿐 아니라, 같은 구역의 `<hp:headerApply>`/`<hp:footerApply>` 노드와 연결된 마스터 페이지 참조까지 일관되게 유지합니다. 위 예제의 `apply_page_type` 속성은 방금 요청한 페이지 유형(`BOTH`)으로 자동 설정됩니다.

### 예제 15: 머리말 제거

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
section = document.sections[0]
section.properties.remove_header()
```

헤더나 꼬리말을 제거하면 `<hp:headerApply>`/`<hp:footerApply>` 노드와 마스터 페이지 링크도 함께 정리되므로, 편집기에서 더 이상 이전 머리말이 표시되지 않습니다.

### 예제 16: 홀수 페이지 꼬리말 넣기

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
section = document.sections[0]
section.properties.set_footer_text("© Company", page_type="ODD")
```

페이지 유형을 변경할 때마다 구역의 `<hp:footerApply>` 노드가 동일한 유형으로 갱신되고, 필요한 경우 마스터 페이지 목록에 새로운 참조가 생성됩니다.

### 예제 17: 헤더 파트 이름 나열

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
print([header.part_name for header in document.parts.headers])
```

### 예제 18: 메모 모양 ID 확인

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
print(sorted(document.styles.memo_shapes.keys()))
```

### 예제 19: 특정 메모 모양 살펴보기

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
shape = document.styles.memo_shape("0")
if shape:
    print(shape.memo_type, shape.line_color)
```

### 예제 20: 두 번째 섹션에 메모 추가

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
memo = document.notes.add_memo("검토 메모", section_index=0, memo_shape_id_ref="0")
print(memo.text)
```

### 예제 21: 메모를 필드와 함께 앵커링

<!-- standalone-python-example -->

```python
from datetime import datetime

from hwpx import HwpxDocument

document = HwpxDocument.new()
paragraph = document.add_paragraph("앵커 단락", section=0)
memo = document.notes.add_memo(
    "승인 필요",
    anchor=paragraph,
    memo_shape_id_ref="0",
    author="PM",
    created=datetime.now(),
)
print(memo.field_id)
```

### 예제 22: 조건에 맞는 메모 삭제

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
for memo in list(document.notes.memos):
    if memo.text.startswith("임시"):
        document.notes.remove_memo(memo)
```

### 예제 23: 새 문자 서식 확보

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
style_id = document.styles.ensure_run(bold=True, underline=True)
print("style id:", style_id)
```

### 예제 24: 굵고 밑줄 친 런 추가

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
section = document.sections[0]
paragraph = document.add_paragraph("기본 문단", section=section)
paragraph.add_run("강조 텍스트", bold=True, underline=True)
```

### 예제 25: 기존 런을 기울임 처리

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
paragraph = document.paragraphs[0]
if paragraph.runs:
    paragraph.runs[0].italic = True
```

### 예제 26: 특정 서식 ID로 런 찾기

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
style_id = document.styles.ensure_run(bold=True)
matches = document.text.find_runs(char_pr_id_ref=style_id)
print("bold runs:", len(matches))
```

### 예제 27: TODO 한 건만 치환하기

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
changed = document.text.replace("TODO", "DONE", limit=1)
print("replaced:", changed)
```

### 예제 28: 모든 런 텍스트 이어 붙이기

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
all_text = "".join(run.text for run in document.text.runs())
print(all_text[:80])
```

### 예제 29: 첫 문단 텍스트 교체

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
if document.paragraphs:
    document.paragraphs[0].text = "새로운 첫 문단"
```

### 예제 30: 첫 런의 텍스트 읽기

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
if document.paragraphs and document.paragraphs[0].runs:
    print(document.paragraphs[0].runs[0].text)
```

### 예제 31: 첫 런 삭제

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
if document.paragraphs and document.paragraphs[0].runs:
    document.paragraphs[0].runs[0].remove()
```

### 예제 32: 고정 폭 표 만들기

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
section = document.sections[0]
table = document.add_table(rows=3, cols=3, section=section, width=54000)
```

`add_table()`은 문서에 등록된 테두리 채우기가 없으면 헤더 참조 목록에 기본 실선 `borderFill`을 자동으로 추가하고 표 전체에 그 ID를 연결합니다. 생성된 항목은 `document.styles.border_fills` 또는 `document.styles.border_fill("0")`으로 확인할 수 있습니다.

### 예제 33: 표 헤더 병합

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
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

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
section = document.sections[0]
table = document.add_table(rows=2, cols=2, section=section)
cell = table.cell(1, 0)
cell.set_size(width=7200)
```

### 예제 35: 표 행·열 수 확인

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
section = document.sections[0]
table = document.add_table(rows=4, cols=2, section=section)
print(table.row_count, table.column_count)
```

### 예제 36: 도형 삽입

선·사각형·타원은 전용 헬퍼로 만듭니다. 좌표와 크기는 HWPUNIT(1인치 = 7200)이며,
한컴이 요구하는 하위 요소를 헬퍼가 모두 채우므로 결과가 그대로 열립니다.

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
section = document.sections[0]
line = document.shapes.add_line(0, 0, 14400, 0, line_color="#333333", section=section)
rectangle = document.shapes.add_rectangle(14400, 7200, fill_color="#FFD9CC", section=section)
ellipse = document.shapes.add_ellipse(9000, 4500, section=section)
```

### 예제 37: 도형 크기 변경

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
shape = document.shapes.add_rectangle(14400, 7200, section=document.sections[0])
shape.resize(9000, 4500)
print(shape.shape_type, shape.width, shape.height)
```

### 예제 38: 컨트롤 객체 추가

`doc.shapes.add_control()`은 저수준 탈출구입니다. 건네준 요소와 속성만 쓰고 한컴이 요구하는
나머지 하위 요소는 만들지 않으므로, 호출자가 채우지 않은 채 저장한 문서는 한컴에서
열리지 않습니다. 그래서 호출 시 `UserWarning`이 나며, 경고 메시지가 대신 쓸 전용
헬퍼를 알려 줍니다.

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
control = document.shapes.add_control(section=document.sections[0], control_type="LINE", attributes={"id": "line1"})
```

### 예제 39: 컨트롤 속성 변경

앞 예제와 같은 탈출구 경로이므로, 필요한 하위 요소는 호출자가 직접 채워야 합니다.

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
control = document.shapes.add_control(section=document.sections[0], control_type="LINE")
control.set_attribute("dirty", "false")
```

### 예제 40: 섹션 파트 이름 확인

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
print([section.part_name for section in document.sections])
```

### 예제 41: 헤더 경로 목록 확인

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
print(document.package.header_paths())
```

### 예제 42: 섹션 경로 목록 확인

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
print(document.package.section_paths())
```

### 예제 43: 패키지 파트 이름 나열

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
print(document.package.part_names())
```

### 예제 44: 헤더 파트 바이트 길이 확인

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
header_paths = document.package.header_paths()
if header_paths:
    data = document.package.get_part(header_paths[0])
    print("header bytes:", len(data))
```

### 예제 45: version.xml 텍스트 읽기

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
version_text = document.package.get_text("version.xml")
print(version_text.splitlines()[0])
```

### 예제 46: version.xml 속성 수정

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
version_xml = document.package.get_xml("version.xml")
version_xml.set("writer", "python-hwpx")
document.package.set_xml("version.xml", version_xml)
```

### 예제 47: 새 파트 추가하기

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
document.package.set_part("META-INF/notes.txt", "Generated with python-hwpx")
```

### 예제 48: 문자 서식 ID 나열

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
for style_id in sorted(document.styles.char_properties.keys()):
    print("style:", style_id)
```

### 예제 49: 문자 서식 세부 정보 조회

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
style_id = document.styles.ensure_run(bold=True)
style = document.styles.char_property(style_id)
if style:
    print(style.text_color(), style.underline_type())
```

### 예제 50: TODO 문단 찾아 출력

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
for paragraph in document.paragraphs:
    if "TODO" in paragraph.text:
        print(paragraph.text)
```

### 예제 51: 섹션별 문단 수 계산

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
counts = [len(section.paragraphs) for section in document.sections]
print(counts)
```

### 예제 52: 현재 여백 값 읽기

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
section = document.sections[0]
margins = section.properties.page_margins
print(margins.left, margins.right)
```

### 예제 53: 전체 번호 초기값 설정

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
section = document.sections[0]
section.properties.set_start_numbering(page=1, table=1)
```

### 예제 54: 헤더 번호 초기값 읽기

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
if document.parts.headers:
    begin = document.parts.headers[0].begin_numbering
    print(begin.page, begin.table)
```

### 예제 55: 헤더 번호 초기값 조정

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
if document.parts.headers:
    document.parts.headers[0].set_begin_numbering(page=1, table=1)
```

### 예제 56: 헤더 글머리표 정의 나열

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
for bullet_id, bullet in sorted(document.styles.bullets.items()):
    print(bullet_id, bullet.char, bullet.para_head.align)
```

### 예제 57: 문단/스타일 참조 살펴보기

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
para_pr = document.styles.paragraph_property("1")
style = document.styles.get("0")
if para_pr and style:
    print(para_pr.align.horizontal, para_pr.tab_pr_id_ref, style.name)
```

### 예제 58: 변경 추적과 작성자 정보 확인

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
change = document.tracking.change("1")
if change:
    author = document.tracking.author(change.author_id)
    if author:
        print(change.change_type, author.name, author.color)
```

### 예제 59: 바탕쪽 이름 수정하기

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

HM = "{http://www.hancom.co.kr/hwpml/2011/master-page}"

document = HwpxDocument.new()
if document.parts.master_pages:
    master = document.parts.master_pages[0]
    item = master.element.find(f"{HM}masterPageItem")
    if item is not None:
        item.set("name", "보고서 바탕쪽")
        master.mark_dirty()
document.save_to_path("my-document.hwpx")
```

### 예제 60: 문서 이력 주석 갱신

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

HHS = "{http://www.hancom.co.kr/hwpml/2011/history}"

document = HwpxDocument.new()
for history in document.parts.histories:
    comment = history.element.find(f"{HHS}historyEntry/{HHS}comment")
    if comment is not None:
        comment.text = "QA 점검 완료"
        history.mark_dirty()
document.save_to_path("my-document.hwpx")
```

### 예제 61: 버전 메타데이터 업데이트

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
if document.parts.version:
    document.parts.version.element.set("appVersion", "15.0.0.100 WIN32")
    document.parts.version.mark_dirty()
    document.save_to_path("my-document.hwpx")
```

### 예제 62: 단락 삭제하기

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
# 마지막 단락 삭제
if len(document.sections[0].paragraphs) > 1:
    document.paragraphs[-1].remove()
document.save_to_path("my-document.hwpx")
```

### 예제 63: 섹션 내 인덱스로 단락 삭제

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
section = document.sections[0]
if len(section.paragraphs) > 1:
    section.remove_paragraph(0)
```

### 예제 64: 새 섹션 추가

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
new_section = document.add_section()
new_section.add_paragraph("새 섹션의 내용")
document.save_to_path("my-document.hwpx")
```

### 예제 65: 특정 위치에 섹션 삽입

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
mid = document.add_section(after=0)
mid.add_paragraph("중간에 삽입")
print("섹션 수:", len(document.sections))
```

### 예제 66: 섹션 삭제

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
if len(document.sections) > 1:
    document.remove_section(len(document.sections) - 1)
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
paragraph.element.set("outlineLevel", "1")

# 표를 추가하고 헤더 행을 병합합니다. border_fill_id_ref를 생략하면 기본 실선 채우기가 자동 생성됩니다.
# 글이 든 칸을 병합하면 가려지는 칸의 글도 병합 칸에 줄로 남으므로(한/글과 같음), 병합한 뒤 글을 넣습니다.
table = document.add_table(2, 3, section=section, border_fill_id_ref="2")
table.merge_cells(0, 0, 0, 2)
table.set_cell_text(0, 0, "Quarter")
table.cell(1, 0).text = "Q1"
table.set_cell_text(1, 1, "Actual")
table.set_cell_text(1, 2, "Forecast")

# 개체도 문서 또는 문단 수준에서 추가할 수 있습니다.
rectangle = document.shapes.add_rectangle(9000, 4500, fill_color="#FFD9CC", section=section)

# add_control은 저수준 탈출구입니다 — 필수 하위 요소를 만들지 않아 UserWarning이
# 나고, 호출자가 채우지 않으면 한컴이 열지 못하는 문서가 됩니다.
control = document.shapes.add_control(
    section=section,
    control_type="LINE",
    attributes={"id": "ctrl1"},
)
```

`HwpxDocument.sections`, `HwpxDocument.paragraphs`, `doc.parts.headers` 속성은 각각 구역, 모든 문단, 헤더 파트를 리스트로 반환합니다. 섹션 속성(`section.properties`)을 사용하면 페이지 크기, 여백, 바탕쪽 연결과 같은 레이아웃 설정도 쉽게 변경할 수 있습니다. 매니페스트에 등록된 바탕쪽(`document.parts.master_pages`), 문서 이력(`document.parts.histories`), 버전(`document.parts.version`) 파트도 동일한 방식으로 노출되므로 XML 트리를 직접 수정한 뒤 `mark_dirty()`만 호출하면 저장 시 함께 반영됩니다.

```python
options = section.properties
options.set_page_size(width=72000, height=43200, orientation="LANDSCAPE")
options.set_page_margins(left=2000, right=2000, header=1500, footer=1500)

document.parts.headers[0].set_begin_numbering(page=1)
```

## Markdown으로 문서 만들기

언어 모델이 가장 안정적으로 쓰는 형식이 Markdown이다. `from_markdown`은 흔히 쓰는 부분 집합
(`#`~`####` 제목, 문단, `-`/`1.` 목록, `|` 표, `**굵게**`·`*기울임*`)으로 새 문서를 만들고,
모르는 Markdown은 평문으로 쓴다. 이미 있는 문서에는 `doc.text.append_markdown`으로 덧붙인다.
새 문서는 모양을 주지 않으면 아래의 보고서 모양으로 만들고, 덧붙일 때는 받은 문서의 모양을 해치지 않게
꾸미지 않은 모양(`style="plain"`)으로 쓴다.
표는 열 너비를 내용에 맞추고(짧은 이름 열은 좁게, 글이 긴 열은 넓게) 머리 행을 가운데로 놓는다.
구분선의 `:---`·`:---:`·`---:`로 열 정렬을 정할 수 있다. 목록 안의 목록은 깊이마다 오른쪽으로 들여 쓴다.

<!-- standalone-python-example -->
```python
from hwpx.tools.markdown_import import MarkdownStyle, from_markdown

doc = from_markdown(
    "# 운영 보고\n\n이번 학기 **핵심 성과**를 정리한다.\n\n"
    "- 참여 학생 120명\n- 만족도 4.6점\n\n"
    "| 구분 | 목표 | 실적 |\n|---|---|---|\n| 1학기 | 10 | 12 |\n",
    style=MarkdownStyle(heading_sizes=(18, 13, 11, 10)),
)
doc.text.append_markdown("## 맺음\n\n다음 학기에도 이어 간다.")
doc.save_to_path("report.hwpx")
```

새 문단은 앞 문단의 모양을 물려받지 않아 제목·목록 번호가 뒤 문단에 따라붙지 않는다. 직접
`add_paragraph`로 문서를 쌓을 때도 제목(`add_heading`)과 목록 문단의 모양은 뒤 문단이 물려받지 않고,
본문 문단의 모양만 다음 문단이 따른다. 그것도 물려받지 않게 하려면 `HwpxDocument.new(inherit_style=False)`로
문서를 만든다.

### 보고서 모양

`from_markdown`은 모양을 주지 않으면 보고서 모양(`style="report"`, `"보고서"`)으로 만든다. 꾸미지 않은
모양은 `style="plain"`이다. `byline`에는 제목 아래 오른쪽에 쓸 부서·날짜 줄을 준다.

<!-- standalone-python-example -->
```python
from hwpx.tools.markdown_import import from_markdown

doc = from_markdown(
    "# 방과후학교 운영 계획\n\n## 목적\n\n학생의 소질과 적성을 살린다.\n\n"
    "## 운영 방침\n\n### 프로그램 편성\n\n- 수요 조사 결과를 반영한다.\n  - 조사는 2월에 한다.\n",
    byline="교무기획부",
)
doc.save_to_path("plan.hwpx")
```

학교와 기관에서 쓰는 운영 계획·안내 문서의 모양이다.

- `#`은 제목이다. 본문 너비의 회색 상자 안에 21pt로 가운데 놓고, 상자 위아래에 색 띠를 두른다.
- `##`은 큰 항목이다. 남색 칸에 번호(`Ⅰ`, `Ⅱ` …)를 넣고 그 옆에 남색 제목과 밑줄을 그린다. 상자 너비는 제목
  길이에 맞추고, 본문 너비보다 긴 제목은 칸 안에서 줄을 바꾼다.
- `###`·`####`에는 `1.`·`가.` 번호를 붙인다. 윗수준 제목이 나오면 아랫수준 번호는 다시 시작한다.
- 번호를 직접 쓴 제목은 쓴 번호를 그대로 쓴다. `## Ⅱ. 현황`은 칸에 `Ⅱ`를 넣고, `### 1. 목적`에는 번호를 더 붙이지
  않는다. `## 제2장 현황`처럼 칸에 넣기 어려운 번호는 제목에 두고 번호 칸 없이 그린다.
- 본문은 12pt 휴먼명조, 제목은 HY헤드라인M이다. 글머리표는 깊이에 따라 `□`·`-`·`·`이고 깊이마다 들여 쓴다.
  `####` 아래의 목록은 `◦`로 시작하고, `####` 아래의 본문은 그 제목만큼 들여 쓴다.
- `※`로 시작하는 문단은 주석으로 보고 10pt 한컴산뜻돋움으로 쓴다. 목록 항목 안의 `※`는 그대로 둔다.
- 줄 끝을 조금 넘는 목록 항목은 자간을 좁혀 한 줄에 넣는다. 좁히는 폭은 1%씩 8%까지이고, 그보다 더 좁혀야 하는
  항목은 손대지 않고 줄을 바꾼다. 폭을 잘못 재도 줄이 바뀔 뿐 글자가 겹치지 않는다. 정해 둔 자간만 쓰고 한/글의
  "한 줄로 입력"은 쓰지 않기 때문이다. 글꼴이 다른 것으로 바뀌는 환경에서는 한 줄에 들어가지 않을 수 있다.
- 표는 12pt 한컴산뜻돋움이다. 좌우를 트고 위아래에 굵은 줄을, 연한 파랑 머리 행 아래에 이중선을 긋는다.
- 표의 본문 칸은 내용에 따라 놓는다. 한 줄에 들어가는 열은 가운데에, 줄이 바뀌는 열은 왼쪽에 놓는다. 두 열짜리
  표는 첫 열을 이름표로 보고 열 너비에 고르게 펴며(균등 분할) 둘째 열은 왼쪽에 놓는다. 이름표가 한 글자뿐이면
  펴지 않고 가운데에 놓는다. 구분선의 `:---`·`:---:`·`---:`로 정렬을 준 열은 그대로 둔다.
- `byline`은 제목 상자 아래 오른쪽에 13pt 한컴산뜻돋움 굵게로 쓴다. 제목(`#`)이 없으면 첫 줄에 쓰고, `\n`은 줄
  바꿈이다.
- 새 문서는 여백을 20mm(아래 15mm)로 잡고 꼬리말 가운데에 `- 1 -`을 넣는다.
  `doc.text.append_markdown(..., style="report")`는 받은 문서의 여백과 꼬리말을 건드리지 않는다.

글꼴 세 가지는 한컴오피스에 들어 있다. 글꼴이 없는 환경에서는 보는 프로그램이 다른 글꼴로 바꾸어 그린다.

이 모양은 모두 `MarkdownStyle`의 값이다. `MarkdownStyle.report()`를 받아 `dataclasses.replace`로 일부만 바꿀 수
있다. 아래는 색 띠와 큰 항목 상자의 색을 바꾸고 본문 글꼴을 함초롬바탕으로 바꾼 것이다.

<!-- standalone-python-example -->
```python
from dataclasses import replace

from hwpx.tools.markdown_import import MarkdownStyle, from_markdown

style = replace(
    MarkdownStyle.report(),
    banner_colors=("#1F4E79", "#1F4E79", "#BF9000", "#BF9000"),
    section_colors=("#1F4E79", "#9DC3E6", "#1F4E79"),
    body_font="함초롬바탕",
)
doc = from_markdown("# 학교 교육 계획\n\n## 교육 목표\n\n- 배움이 즐거운 학교\n", style=style)
doc.save_to_path("plan-blue.hwpx")
```

| 값 | 하는 일 |
|---|---|
| `heading_numbers`, `bullet_chars`, `sub_bullet_chars` | 수준별 번호 형식, 깊이별 글머리표, `####` 아래 목록의 글머리표 |
| `heading_sizes`, `heading_bold`, `heading_fonts` | 수준별 제목 크기·굵기·글꼴 |
| `body_size`, `body_font`, `table_size`, `table_font` | 본문과 표의 글자 크기·글꼴 |
| `title_look`, `banner_colors`, `banner_fill` | `"banner"`면 제목을 색 띠 상자로 그린다. 띠 색 넷(위 왼쪽·위 오른쪽·아래 왼쪽·아래 오른쪽)과 상자 색 |
| `title_align`, `title_rule`, `title_space_after_pt` | 상자 없는 제목의 정렬과 밑줄, 제목 아래 간격 |
| `section_look`, `section_colors` | `"box"`면 `##`을 번호 상자로 그린다. 색 셋(번호 칸·선·제목 글자) |
| `table_look`, `table_header_shading`, `table_row_height_mm` | `"ruled"`면 좌우가 트인 줄 표. 머리 행 색, 행의 최소 높이 |
| `table_align` | `"auto"`면 본문 칸을 내용에 따라 가운데·왼쪽·균등 분할로 놓는다 |
| `note_size`, `note_font` | `※`로 시작하는 문단의 크기·글꼴 |
| `list_fit_spacing` | 목록 항목을 한 줄에 넣으려고 좁힐 수 있는 자간(%, 0~10). `0`이면 좁히지 않는다 |
| `heading_indents_mm`, `list_first_indent_mm`, `list_indent_mm` | 수준별 제목 들여쓰기, 목록 첫 수준과 그다음 수준의 들여쓰기 |
| `byline_size`, `byline_font`, `byline_bold` | 부서·날짜 줄의 크기·글꼴·굵기 |
| `page_margins_mm`, `page_number`, `page_number_side` | 새 문서의 여백(왼쪽·오른쪽·위·아래, 이어서 머리말·꼬리말), 쪽 번호와 양옆 글자 |

라이브러리가 이름 붙여 싣는 모양은 이것 하나다. 공문·가정통신문처럼 넣어야 할 내용이 정해진 장르는 응용 계층이
`MarkdownStyle`로 정한다.

## 단락 삭제

문단 객체의 `remove()` 메서드를 호출하거나, 섹션/문서 수준에서 인덱스 또는 인스턴스로 단락을 삭제할 수 있습니다.

```python
# 인스턴스로 삭제
paragraph = document.paragraphs[-1]
paragraph.remove()

# 섹션 내 인덱스로 삭제
section = document.sections[0]
section.remove_paragraph(2)

# 단락 객체에서 직접 삭제
section.paragraphs[1].remove()
```

```{warning}
섹션에는 최소 하나의 단락이 필요합니다. 마지막 단락을 삭제하려고 하면 `ValueError`가 발생합니다.
```

## 섹션 추가·삭제

문서에 새 섹션을 추가하거나 기존 섹션을 삭제할 수 있습니다. 섹션 추가 시 manifest/spine에 자동 등록되므로 별도의 매니페스트 조작이 필요 없습니다.

```python
# 문서 끝에 새 섹션 추가
new_section = document.add_section()
new_section.add_paragraph("새 섹션의 첫 문단")

# 특정 위치에 삽입 (섹션 0 뒤)
mid_section = document.add_section(after=0)
mid_section.add_paragraph("중간에 삽입된 섹션")

# 인스턴스로 삭제
document.remove_section(mid_section)

# 인덱스로 삭제
document.remove_section(1)
```

```{warning}
문서에는 최소 하나의 섹션이 필요합니다. 마지막 섹션을 삭제하려고 하면 `ValueError`가 발생합니다.
```

## 메모 다루기

문서에 첨부된 메모는 섹션의 `<hp:memogroup>` 요소와 헤더의 `memoProperties` 정의를 통해 연결됩니다. `doc.notes.memos` 속성은 모든 섹션에 포함된 메모 객체를 반환하며, `doc.notes.add_memo()`/`doc.notes.remove_memo()`를 사용하면 새 메모를 생성하거나 삭제할 수 있습니다.

```python
# 메모 모양 정의는 header.ref_list.memo_properties 또는 document.memo_shapes로 조회할 수 있습니다.
default_shape = next(iter(document.styles.memo_shapes))  # 첫 번째 모양 ID

memo = document.notes.add_memo(
    "검토 의견을 정리했습니다.",
    section=section,
    memo_shape_id_ref=default_shape,
)
memo.text = "표 1은 최신 수치로 업데이트가 필요합니다."

for existing in document.notes.memos:
    print(existing.id, existing.memo_shape_id_ref, existing.text)

document.notes.remove_memo(memo)
```

> **주의:** 한글 편집기에서 메모 풍선을 표시하려면 본문 문단에 대응되는 MEMO 필드 컨트롤(`hp:fieldBegin`/`hp:fieldEnd`)이 있어야 합니다.

```python
todo = document.add_paragraph("TODO: QA 서명", section=section, char_pr_id_ref=10)

document.notes.add_memo(
    "배포 전 QA 서명을 확인하세요.",
    anchor=todo,
    memo_shape_id_ref="0",
    memo_id="release-memo-qa",
    char_pr_id_ref="10",
    attributes={"author": "QA"},
    anchor_char_pr_id_ref="10",
)
```

`examples/build_release_checklist.py`는 이러한 과정을 자동화하여 QA 점검용 문서를 생성하는 스크립트입니다.

## 스타일 기반 텍스트 변환

런(`HwpxOxmlRun`)은 `charPrIDRef`를 통해 헤더의 문자 서식(`charPr`)과 연결됩니다. `doc.text.find_runs()`는 색상, 밑줄 종류, 문자 속성 ID 등의 조건으로 런을 필터링하고, `doc.text.replace()`는 선택된 런 내부의 부분 문자열만 치환하거나 삭제합니다.

```python
# 빨간색 텍스트에만 TODO 태그가 남아 있는지 검사합니다.
for run in document.text.find_runs(text_color="#FF0000"):
    if "TODO" in run.text:
        print("검토 필요:", run.text)

# 빨간색 텍스트에서 TODO를 DONE으로 교체하고, 최대 두 번만 수행합니다.
document.text.replace(
    "TODO",
    "DONE",
    text_color="#FF0000",
    limit=2,
)

# 밑줄이 그어진 텍스트에서 임시 주석을 제거합니다.
document.text.replace(
    "(draft)",
    "",
    underline_type="BOTTOM",
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

모델로 문단의 글이나 런을 바꾸면 `apply_model()`이 그 문단의 줄 배치 캐시(`hp:linesegarray`)를 지웁니다. 한/글은 캐시의 줄 수를 믿고 글을 그 안에 눌러 담으므로, 바뀐 내용 위에 옛 캐시를 남기지 않습니다. 런 텍스트에 넣은 `"\n"`과 탭은 `hp:lineBreak`·`hp:tab`으로 기록됩니다.

## 런 서식 지정

헤더의 `<hh:charPr>` 정의는 여러 런이 공유하는 문자 서식을 담고 있습니다. `doc.styles.ensure_run()`은 굵게/기울임/밑줄 조합에 맞는 `charPr` 항목을 찾아 ID를 반환하고, 필요한 경우 새 항목을 생성합니다. 문단 객체는 `add_run()` 메서드를 통해 해당 서식을 즉시 사용하는 런을 만들 수 있습니다.

```python
section = document.sections[0]
paragraph = section.paragraphs[0]

# 굵은 밑줄 서식을 확보하고, 동일한 서식을 가진 런을 추가합니다.
style_id = document.styles.ensure_run(bold=True, underline=True)
run = paragraph.add_run("강조된 텍스트", bold=True, underline=True)

# 반환된 런은 즉시 서식 토글 속성을 제공합니다.
run.italic = True  # 새로운 charPr가 생성되고 참조가 갱신됩니다.
assert run.bold is True and run.underline is True
```

런의 `bold`, `italic`, `underline` 속성은 문서와 연결된 상태에서만 동작하며, 속성을 변경하면 헤더의 `charProperties` 목록과 관련 캐시가 자동으로 업데이트됩니다.

편집이 끝나면 `save_to_path()` 또는 `save_to_stream()`을 호출해 변경 사항을 파일이나 스트림에 기록합니다.

```python
document.save_to_path("edited.hwpx")
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

`hp:tab` 또는 `ctrl id="tab"`이 들어 있는 문단도 같은 방식으로 처리됩니다. 예를 들어 `left<tab>right` 형태의 런은 `paragraph.text()`에서 `"left\tright"`로 보이며, `HwpxDocument`로 다시 저장한 뒤 다시 열어도 탭 의미가 유지됩니다.

문단 객체(`ParagraphInfo`)의 `text()` 메서드에는 추가로 다음과 같은 인자를 전달할 수 있습니다.

- `object_behavior`: 표, 도형 등 인라인 개체를 `"skip"`, `"placeholder"`, `"nested"` 중 하나로 처리합니다.
- `object_placeholder`: 자리표시자 모드를 사용할 때 형식을 지정합니다.
- `preserve_breaks`: 줄바꿈과 탭을 유지할지 여부를 결정합니다. 기본값은 `True`이며, `hp:tab`과 `ctrl id="tab"`은 `\t`로 렌더링됩니다. `False`로 주면 탭/줄바꿈을 공백 기반으로 평탄화할 수 있습니다.

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

`HwpxDocument`는 세 가지 저장 방법을 제공합니다.

| 메서드 | 설명 |
|--------|------|
| `save_to_path(path)` | 원자적 쓰기 + ZIP 무결성 + editor-open safety 검증 후 파일 저장 |
| `save_to_stream(stream)` | 검증된 HWPX만 `BinaryIO` 스트림에 기록 |
| `to_bytes()` | 검증된 HWPX를 `bytes`로 직렬화 |

세 방법의 기본 검사가 보는 범위는 다음과 같습니다.

- 보는 것: ZIP과 각 XML 파트가 읽히는지, 한/글이 열지 못하는 구조(필수 자식이 없는 표·도형·글맵시·OLE·동영상, 빈 컨트롤, 필수 파트·속성 누락), 글보다 뒤를 가리키거나 줄 수가 크게 모자란 줄 배치 캐시.
- 보지 않는 것: **참조 무결성**. 본문이 가리키는 글자 모양(`charPrIDRef`)·문단 모양(`paraPrIDRef`)·스타일·테두리·그림 자료가 `header.xml`과 패키지에 실제로 있는지는 기본 저장에서 확인하지 않습니다. 없는 id를 가리키는 문서도 기본 검사를 통과해 저장됩니다.

참조까지 확인하려면 `save_report(path, quality=QualityPolicy.strict())`를 쓰거나(`REFERENCE_INTEGRITY_FAILED`로 보고), `hwpx.tools.id_integrity.check_id_integrity(document)`를 직접 부릅니다. 이 검사는 문서를 여는 시간의 0.7배쯤 더 걸리고, 한/글이 저장한 문서 가운데에도 걸리는 것이 있어(정의되지 않은 글머리표 `idRef="0"`) 기본 저장에는 넣지 않았습니다.

```python
# 파일로 저장
document.save_to_path("result.hwpx")

# 스트림으로 저장
from io import BytesIO
buf = BytesIO()
document.save_to_stream(buf)

# 바이트로 직렬화
raw = document.to_bytes()
with open("result.hwpx", "wb") as fp:
    fp.write(raw)
```

저장 API는 결과 HWPX를 편집기에서 열 수 있는지 확인하기 위해 패키지 검증, document validation, 재오픈 검증을 수행합니다. 별도 pack/repack 파이프라인에서 같은 증거가 필요하면 `hwpx.validate_editor_open_safety(path)` 또는 `hwpx.tools.validate_editor_open_safety(path)`를 호출해 `EditorOpenSafetyReport`를 확인하세요.

패키지 수준에서 바로 작업하고 싶다면 `HwpxPackage.set_part()`/`save()`를 사용해 XML 조각을 교체할 수도 있습니다. 이 경우에도 최종 출력은 반드시 `HwpxPackage.save()`를 거쳐야 합니다. `_write_archive()`나 `_write_zip_entry()` 같은 raw ZIP writer는 내부 구현 세부사항이며, safety 검증을 건너뛴 산출물을 만들 수 있으므로 직접 호출하지 마세요.

## AI 파이프라인에서 읽기

검색·요약 파이프라인에 넣을 글은 `hwpx.ingest`로 뽑습니다. `.hwpx`와 `.hwp`를 같은 방식으로 받고, 제목·목록·표를
살린 Markdown과 함께 무엇이 빠졌는지를 알려 줍니다.

```python
from hwpx.ingest import DocumentIngestor

result = DocumentIngestor.default().convert(path)   # path: .hwpx나 .hwp 파일 경로
print(result.markdown)
print(result.lossiness)        # "low": 빠진 것이 없다. "medium"·"high": warnings에 종류와 개수
print(result.flat_metadata())  # 출처·형식·개수·경고를 글자와 숫자 값만으로
```

암호 문서나 HWP 3.x처럼 읽을 수 없는 파일은 `UnsupportedDocumentFormat`으로 거부하고, 사유가 오류 문구에
들어갑니다.

### LangChain 로더

`pip install "python-hwpx[langchain]"`로 `langchain-core`를 함께 설치하면 로더를 쓸 수 있습니다. 파일 하나가
Markdown 문서 하나가 되고, 메타데이터는 위의 `flat_metadata()`입니다.

```python
from hwpx.integrations.langchain import HwpxLoader

docs = HwpxLoader(path).load()   # path: .hwpx나 .hwp 파일 경로
print(docs[0].page_content[:200])
print(docs[0].metadata["lossiness"])
```

나누기는 LangChain의 분할기에 맡깁니다. Markdown에 `#` 제목이 남아 있어 `MarkdownHeaderTextSplitter`로 문서의
절을 따라 자를 수 있습니다. 폴더를 통째로 읽으려면 `DirectoryLoader(폴더, glob="**/*.hwp*", loader_cls=HwpxLoader)`
처럼 넘깁니다. 로더와 `hwpx.ingest`는 실험 기능이라 6.x 안에서 이름과 메타데이터 키가 바뀔 수 있습니다.

## 제안서 프리셋 — 5.0에서 이동

제안서·기획안 생성은 `hwpx_automation.office.authoring`이 소유합니다. 5.0의
`python-hwpx`는 그 프리셋이 사용하던 재료(문단·표·런 스타일·페이지 설정)를
제공하고, 장르 판단은 하지 않습니다. 이동 내역은
[5.0 마이그레이션 가이드](migration-5.0.md)를 보세요.

## 응용 워크플로 — automation 문서로 이동

선언형 document plan, 운영계획서 품질 프로필, template form-fit처럼 장르
판단·정책·렌더 검증이 결합된 워크플로는 5.0부터 이 core 패키지의 사용
예제가 아닙니다. 해당 API와 실행 예제의 정식 소유자는
[`python-hwpx-automation` 사용 사례](https://github.com/airmang/python-hwpx-automation/blob/main/docs/use-cases.md)입니다.

이 문서에서는 `HwpxDocument`와 `HwpxPackage`의 포맷 수준 읽기·편집·저장
계약만 다룹니다. 4.x 코드의 이관 경로는
[5.0 마이그레이션 가이드](migration-5.0.md)를 참고하세요.
