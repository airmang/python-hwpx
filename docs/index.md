# python-hwpx 문서

`python-hwpx`는 HWPX 문서를 읽고 편집하고 생성하는 파이썬 도구 모음입니다. 가장 빠른 진입로는 `new/open -> add/edit -> save_to_path`입니다. 먼저 {doc}`quickstart`로 첫 성공 경로를 잡고, 그다음 필요에 따라 사용 가이드와 심화 문서를 보면 된다.

> **Python 블록 판정:** [실행 분류 ledger](python-example-ledger.json)가 이 current
> manual의 모든 Python 블록을 동결합니다. **독립 실행 예제** 표시가 없는
> 블록은 기존 입력 파일이나 앞 문맥이 필요한 조각입니다.

```{toctree}
:maxdepth: 2
:hidden:
:caption: 시작하기

quickstart
installation
recipes-traversal
mutation-semantics
usage
examples
```

```{toctree}
:maxdepth: 2
:hidden:
:caption: 심화 주제

corpus-metrics
support-matrix
stable-api
compatibility-observation-4.x
safe-write-contract
schema-overview
internals/README
faq
changelog
```

```{toctree}
:maxdepth: 1
:hidden:
:caption: API 참조

api_reference
```

## 가장 빠른 경로

처음에는 이 네 단계면 충분하다.

1. 문서를 연다, 또는 새로 만든다.
2. 문단 하나를 추가하거나 수정한다.
3. `save_to_path()`로 저장한다.
4. 더 복잡한 편집과 추출/검증은 다음 문서로 내려간다.

```python
from hwpx import HwpxDocument

# 기존 문서 수정
document = HwpxDocument.open("sample.hwpx")
document.add_paragraph("자동화로 추가한 문단")
document.save_to_path("sample-updated.hwpx")

# 새 문서 생성
new_document = HwpxDocument.new()
new_document.add_paragraph("새 HWPX 문서")
new_document.save_to_path("new-document.hwpx")
```

## 작업별 바로가기

원하는 작업 단위로 바로 들어가면 된다.

- **첫 파일을 열고 저장하는 최소 경로** → {doc}`quickstart`
- **문단·표·각주에서 원하는 것을 꺼내고 싶다** → {doc}`recipes-traversal`
- **편집 호출이 무엇을 돌려주고 어떻게 실패하는지 알고 싶다** → {doc}`mutation-semantics`
- **저장이 무엇을 보존했는지 영수증으로 확인하고 싶다** → {doc}`safe-write-contract`
- **문단, 표, 메모, 섹션 편집을 넓게 보고 싶다** → {doc}`usage`
- **텍스트 추출, 구조 조회, 패키지 검증을 하고 싶다** → {doc}`usage`
- **설치 확인과 개발 환경 점검이 먼저다** → {doc}`installation`
- **실행 가능한 예제 파일을 보고 싶다** → {doc}`examples`
- **패키지 구조와 스키마를 이해하고 싶다** → {doc}`schema-overview`
- **4.x 호환 import·CLI·스키마의 유지/이행 정책을 보고 싶다** → {doc}`compatibility-observation-4.x`
- **클래스/메서드 시그니처를 바로 찾고 싶다** → {doc}`api_reference`

```{seealso}
- {doc}`quickstart` — 설치부터 첫 번째 문서를 열고 저장하기까지 따라 하는 튜토리얼
- {doc}`usage` — 문단, 표, 메모, 추출, 검증, 패키지 조작까지 포함한 핵심 사용 패턴
- {doc}`compatibility-observation-4.x` — 4.x 호환 family·CLI·스키마의 관찰, canonical 경로, rollback 정책
- {doc}`api_reference` — 세부 클래스와 함수 시그니처 모음
```
