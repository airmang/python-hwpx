# python-hwpx 문서

`python-hwpx`는 HWPX 문서를 읽고 편집하고 생성하는 파이썬 도구 모음입니다. 이 사이트는 파이썬 코드 예제를 중심으로 빠르게 실무에 적용할 수 있는 사용법을 안내합니다. 먼저 "5분 안에 문서 열기" 예제를 따라 한 뒤, 필요에 따라 설치, 사용 가이드, 참조 문서를 살펴보세요.

```{toctree}
:maxdepth: 2
:hidden:
:caption: 시작하기

quickstart
installation
usage
examples
```

```{toctree}
:maxdepth: 2
:hidden:
:caption: 심화 주제

schema-overview
faq
```

```{toctree}
:maxdepth: 1
:hidden:
:caption: API 참조

api_reference
```

## 지금 바로 시작하기

아래는 `python-hwpx`의 대표적인 패턴 세 가지입니다.

1. 로컬 HWPX 문서를 열어 문단을 읽어오기
2. 빈 템플릿에서 새 문서를 만들고 표 및 메모를 추가하기
3. 완성된 문서를 파일로 저장하기

자세한 단계별 설명은 {doc}`quickstart`에서 확인할 수 있습니다.

```python
from hwpx import HwpxDocument

# 1) 문서 열기
document = HwpxDocument.open("sample.hwpx")
print("문단 수:", len(document.paragraphs))

# 2) 새 문단과 메모 추가
section = document.sections[0]
paragraph = document.add_paragraph("자동으로 추가된 문단", section=section)

memo, _, field_id = document.add_memo_with_anchor(
    "검토 의견은 여기에 적으세요.",
    paragraph=paragraph,
    memo_shape_id_ref="0",
)
print("생성된 메모 ID:", memo.id)
print("필드 컨트롤 ID:", field_id)

# 3) 저장
document.save("updated-sample.hwpx")
```

```{seealso}
- {doc}`quickstart` — 설치부터 첫 번째 문서를 편집하기까지 따라 하는 튜토리얼
- {doc}`usage` — 패키지 전반의 핵심 개념과 고급 편집 패턴
- {doc}`api_reference` — 세부 클래스와 함수 시그니처 모음
```
