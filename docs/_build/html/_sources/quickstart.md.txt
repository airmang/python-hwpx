# 5분 안에 HWPX 문서 다루기

이 가이드는 `python-hwpx`를 처음 접하는 분을 위한 초간단 튜토리얼입니다. 설치부터 문서를 열고 수정한 뒤 저장하는 과정까지 핵심 흐름만 빠르게 익힙니다.

## 준비물

```bash
pip install python-hwpx
```

패키지에는 기본 템플릿이 함께 포함되어 있습니다. 실습용 문서를 만들고 싶다면 `hwpx.templates.blank_document_bytes()`를 사용해 빈 문서를 즉시 생성할 수 있습니다. 보유 중인 HWPX 파일이 있다면 경로만 교체해 실행해도 됩니다.

```{tip}
Jupyter Notebook이나 IPython에서 실험하면 XML 구조를 꾸준히 탐색하면서 결과를 확인하기 편리합니다.
```

## 1. 문서 열기와 기본 정보 확인

```python
from io import BytesIO

from hwpx.document import HwpxDocument
from hwpx.templates import blank_document_bytes

source = BytesIO(blank_document_bytes())
document = HwpxDocument.open(source)
print("총 섹션 수:", len(document.sections))
print("첫 번째 문단 텍스트:", document.paragraphs[0].text)
```

`HwpxDocument.open()`은 파일 경로, 바이트, 파일 객체 등 다양한 입력을 받아 문서를 로드합니다. 반환된 `document` 객체는 섹션, 문단, 표 등 주요 구성 요소에 바로 접근할 수 있는 고수준 API를 제공합니다.

## 2. 새 문단 추가하기

```python
section = document.sections[0]
paragraph = document.add_paragraph(
    "python-hwpx로 생성한 문단입니다.",
    section=section,
)

print("추가된 문단:", paragraph.text)
```

문단은 항상 특정 섹션에 속합니다. 섹션을 지정하지 않으면 마지막 섹션을 사용합니다. 리턴값으로 받은 `paragraph`는 런(run) 추가, 메모 앵커 연결 등 후속 조작을 할 때 계속 활용할 수 있습니다.

## 3. 표 만들기와 값 채우기

```python
table = document.add_table(rows=2, cols=2, section=section)

table.set_cell_text(0, 0, "항목")
table.set_cell_text(0, 1, "값")
table.set_cell_text(1, 0, "문단 수")
table.set_cell_text(1, 1, str(len(document.paragraphs)))
```

생성된 표는 첫 번째 행을 헤더처럼 활용하고, 두 번째 행에 현재 문단 수를 기록합니다. 셀 텍스트는 UTF-8 문자열로 바로 입력하면 됩니다.

## 4. 메모와 필드 컨트롤 추가하기

```python
memo, paragraph, field_id = document.add_memo_with_anchor(
    "검토 중입니다.",
    paragraph=paragraph,
    memo_shape_id_ref="0",
)

print("새 메모 ID:", memo.id)
print("필드 컨트롤 ID:", field_id)
```

`memo_shape_id_ref`는 문서 헤더에 정의된 메모 모양(풍선 모양)을 가리킵니다. 기본 템플릿에는 적어도 하나의 모양이 정의되어 있으므로 "0"을 그대로 사용할 수 있습니다.

```{note}
문서에 MEMO 컨트롤이 없으면 한/글에서 메모 풍선이 보이지 않습니다. `add_memo_with_anchor()`는 필수 컨트롤을 자동으로 만들어 주므로 초보자도 안전하게 사용할 수 있습니다.
```

## 5. 다른 이름으로 저장하기

```python
output_path = "output/quickstart.hwpx"
document.save(output_path)
print("저장 완료:", output_path)
```

`HwpxDocument.save()`에 경로를 넘기면 zip 기반의 HWPX 아카이브가 생성됩니다. 디렉터리가 없다면 `Path(output_path).parent.mkdir(parents=True, exist_ok=True)`로 먼저 준비해 주세요.

## 다음 단계

- {doc}`usage`에서 더 많은 편집 패턴과 타 객체 조작 방법을 살펴보기
- {doc}`examples`에 정리된 스크립트를 실행하며 전체 워크플로를 익히기
- XML 구조와 매니페스트가 궁금하다면 {doc}`schema-overview` 문서를 참고하기
