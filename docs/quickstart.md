# 5분 안에 HWPX 문서 다루기

이 가이드는 `python-hwpx`를 처음 접하는 분을 위한 초간단 튜토리얼입니다. 처음에는 `new/open -> add/edit -> save_to_path` 흐름만 익히면 충분합니다. 바이트 스트림, 패키지 조작, XML 심화는 뒤로 미뤄도 된다.

## 준비물

```bash
pip install python-hwpx
```

이 문서는 **경로 기반 예제**부터 시작한다. 손에 `.hwpx` 파일이 이미 있다면 바로 열어서 수정하면 되고, 없으면 새 문서를 하나 만들면 된다.

## 1. 새 문서 만들고 저장하기

가장 쉬운 시작은 빈 문서를 만들고 문단 하나를 넣은 뒤 저장하는 것이다.

```python
from pathlib import Path

from hwpx import HwpxDocument

Path("output").mkdir(parents=True, exist_ok=True)

document = HwpxDocument.new()
document.add_paragraph("python-hwpx로 만든 첫 문서")
document.save_to_path("output/hello.hwpx")

print("저장 완료: output/hello.hwpx")
```

`HwpxDocument.new()`는 기본 템플릿이 포함된 새 HWPX 문서를 만든다. `save_to_path()`는 원자적 쓰기(임시 파일 → rename)와 ZIP 무결성 검증을 수행한다.

## 2. 기존 문서 열어 수정하기

이미 있는 파일을 고칠 때는 `open()`으로 열고, 수정한 뒤 다른 이름으로 저장하면 된다.

```python
from pathlib import Path

from hwpx import HwpxDocument

Path("output").mkdir(parents=True, exist_ok=True)

with HwpxDocument.open("input/sample.hwpx") as document:
    document.add_paragraph("자동화로 추가한 검토 문단")
    document.save_to_path("output/sample-updated.hwpx")

print("저장 완료: output/sample-updated.hwpx")
```

`HwpxDocument.open()`은 파일 경로뿐 아니라 바이트, 파일 객체도 받을 수 있다. 하지만 첫 시작은 경로 기반 예제가 가장 덜 헷갈린다. `with`를 쓰면 블록 종료 시점에 내부 자원 정리도 자동으로 끝난다.

## 3. 첫 성공 다음에 자주 하는 편집

문서를 한 번 저장해봤다면, 그다음은 보통 문단, 표, 메모 순서로 간다.

### 3-1. 문단 추가와 삭제

```python
paragraph = document.add_paragraph("추가한 문단")
print("추가된 문단:", paragraph.text)

document.remove_paragraph(paragraph)
```

```{note}
섹션에는 최소 하나의 단락이 필요합니다. 마지막 단락을 삭제하면 `ValueError`가 발생합니다.
```

### 3-2. 표와 메모 추가

```python
section = document.sections[0]
paragraph = document.add_paragraph("검토용 문단", section=section)

table = document.add_table(rows=2, cols=2, section=section)
table.set_cell_text(0, 0, "항목")
table.set_cell_text(0, 1, "값")
table.set_cell_text(1, 0, "상태")
table.set_cell_text(1, 1, "검토 중")

memo, _, field_id = document.add_memo_with_anchor(
    "이 문단을 다시 확인하세요.",
    paragraph=paragraph,
    memo_shape_id_ref="0",
)

print("메모 ID:", memo.id)
print("필드 ID:", field_id)
```

기본 템플릿에는 적어도 하나의 메모 모양이 포함되어 있으므로 `memo_shape_id_ref="0"`부터 시작하면 된다. 더 복잡한 표 편집, 병합 셀, 섹션 추가/삭제는 {doc}`usage`에서 이어서 보면 된다.

## 4. 저장 방식 더 보기

기본은 `save_to_path()`다. 메모리 안에서 계속 다뤄야 하면 스트림이나 바이트 직렬화도 쓸 수 있다.

```python
from io import BytesIO

buf = BytesIO()
document.save_to_stream(buf)

raw = document.to_bytes()
print("바이트 길이:", len(raw))
```

## 5. 파일이 없으면 기본 템플릿 바이트로 열기

파일 경로 없이도 바로 문서를 열 수 있다. 다만 이건 첫 성공 다음 단계로 보면 된다.

```python
from io import BytesIO

from hwpx import HwpxDocument
from hwpx.templates import blank_document_bytes

source = BytesIO(blank_document_bytes())
document = HwpxDocument.open(source)
print("총 섹션 수:", len(document.sections))
```

## 다음 단계

- {doc}`usage`에서 문단, 표, 메모, 섹션, 추출, 검증, 패키지 조작까지 이어서 보기
- {doc}`examples`에 있는 실행 가능한 예제 스크립트로 전체 흐름 익히기
- XML 구조와 매니페스트가 궁금하면 {doc}`schema-overview` 참고
- 설치 검증이나 개발 환경 점검은 {doc}`installation` 참고
