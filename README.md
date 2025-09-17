# python-hwpx

python-hwpx는 Hancom HWPX 패키지를 분석하고 편집하기 위한 Python 유틸리티 모음입니다. Open Packaging Convention(OPC) 컨테이너를 검증하고, 문단/섹션 조작을 위한 고수준 래퍼와 텍스트 추출 도구를 함께 제공합니다.

## 주요 기능

- **패키지 검사 및 로딩** – `hwpx.opc.package.HwpxPackage`는 `mimetype`, `META-INF/container.xml`, `version.xml`을 확인하면서 루트 파일과 매니페스트를 메모리에 적재합니다.
- **문서 편집 API** – `hwpx.document.HwpxDocument`는 문단 추가, 표/개체/컨트롤 삽입, 섹션·헤더 속성 업데이트 등 편집 기능을 제공합니다.
- **메모 CRUD와 필드 앵커** – 섹션의 `<hp:memogroup>`와 헤더의 `memoProperties`를 연결해 메모를 관리하고, 본문에 MEMO 필드 컨트롤을 삽입해 편집기에서 풍선 메모가 표시되도록 할 수 있습니다.
- **스타일 기반 텍스트 변환** – 런의 문자 서식을 분석해 특정 색상/밑줄을 가진 텍스트만 찾아 치환하거나 삭제할 수 있습니다.
- **텍스트 추출 파이프라인** – `hwpx.tools.text_extractor.TextExtractor`는 하이라이트/각주/컨트롤 표시 방식을 세밀하게 제어하면서 문단 텍스트를 추출합니다.
- **객체 검색 유틸리티** – `hwpx.tools.object_finder.ObjectFinder`는 XPath, 속성 매칭, 주석 종류 필터를 활용해 원하는 XML 요소를 찾습니다.

## 빠른 시작

### 1. 환경 준비

가상 환경을 만든 뒤 PyPI에 배포된 패키지를 설치하세요.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install python-hwpx
```

최신 개발 버전을 사용하거나 소스 코드를 수정하려면 편집 가능한 설치를 권장합니다.

```bash
python -m pip install -e .[dev]
```

설치와 환경 구성에 관한 더 자세한 내용은 [설치 가이드](docs/installation.md)를 참고하세요.

### 2. 패키지 구조 살펴보기

```python
from hwpx.opc.package import HwpxPackage

package = HwpxPackage.open("sample.hwpx")
print("MIME type:", package.mimetype)

for rootfile in package.iter_rootfiles():
    print(f"{rootfile.full_path} ({rootfile.media_type})")

main = package.main_content
print("Main content located at:", main.full_path)
```

### 3. 문서 편집하기

```python
from hwpx.document import HwpxDocument

document = HwpxDocument.open("sample.hwpx")
section = document.sections[0]

headline = document.add_paragraph(
    "새 소식",
    section=section,
    style_id_ref=1,
    char_pr_id_ref=6,
)

table = document.add_table(
    rows=2,
    cols=3,
    section=section,
    border_fill_id_ref="3",
)
table.set_cell_text(0, 0, "Quarter")
table.set_cell_text(0, 1, "Results")
table.set_cell_text(0, 2, "Forecast")
table.merge_cells(0, 0, 0, 2)
table.cell(1, 0).text = "Q1"

header = document.headers[0]
header.set_begin_numbering(page=1)

document.save("sample-updated.hwpx")
```

### 4. 메모 필드 연결과 스타일 치환

한글 편집기에서 메모가 보이려면 본문 문단에 MEMO 필드 컨트롤이 존재해야 합니다. 아래 예제는 새 메모를 추가한 뒤, 해당 문단 앞뒤에 `fieldBegin`/`fieldEnd`를 삽입합니다. 고유 식별자는 프로젝트 상황에 맞게 생성하세요.

```python
section = document.sections[0]
todo = document.add_paragraph(
    "TODO: 통합 테스트 결과",
    section=section,
    char_pr_id_ref=10,
)

document.add_memo_with_anchor(
    "테스트 시나리오를 12월 2일까지 업데이트하세요.",
    paragraph=todo,
    memo_shape_id_ref="0",
    memo_id="release-memo-1",
    char_pr_id_ref="10",
    attributes={"author": "QA"},
    anchor_char_pr_id_ref="10",
)

document.replace_text_in_runs("TODO", "DONE", text_color="#C00000")

document.save("sample-memo.hwpx")
```

`examples/build_release_checklist.py`는 동일한 패턴으로 QA용 점검 문서를 생성하므로, 메모 핸들링을 자동화하고 싶다면 참고하세요.

### 5. 텍스트 추출 및 주석 처리

```python
from hwpx.tools.text_extractor import AnnotationOptions, TextExtractor

options = AnnotationOptions(
    highlight="markers",
    hyperlink="target",
    control="placeholder",
)

with TextExtractor("sample.hwpx") as extractor:
    for paragraph in extractor.iter_document_paragraphs():
        text = paragraph.text(annotations=options)
        if text.strip():
            print(text)
```

주요 사용 패턴과 추가적인 매개변수는 [사용 가이드](docs/usage.md)에서 더 자세히 확인할 수 있습니다.

## 알려진 제약
- 머리말/꼬리말 편집 시 `<hp:headerApply>`와 마스터 페이지 연결을 아직 구현하지 않아, `set_header_text()`로 작성한 내용이 한글 편집기에는 표시되지 않습니다.
- `add_shape()`/`add_control()`은 필수 하위 노드를 생성하지 않으므로, 새 도형이나 컨트롤을 추가한 문서는 한글 편집기에서 열리지 않거나 예기치 않게 종료될 수 있습니다.
- 메모와 스타일 기반 텍스트 치환 기능은 단일 `<hp:t>`로 구성된 단순 런에 최적화되어 있으며, 마크업이 중첩된 복합 텍스트 스팬에서는 동작이 제한될 수 있습니다. 메모를 본문에 노출하려면 반드시 대응되는 MEMO 필드 컨트롤을 삽입해야 합니다.



## 문서

- [설치 가이드](docs/installation.md)
- [사용 가이드](docs/usage.md)
- [실전 예제](docs/examples.md)
- [자주 묻는 질문](docs/faq.md)
- [HWPX 스키마 구조와 파이썬 모델 현황](docs/schema-overview.md)
- [릴리스 가이드](docs/release.md)

## 예제 스크립트

`examples/` 디렉터리에는 다음과 같은 샘플이 포함되어 있습니다.

- `extract_text.py` – `TextExtractor`를 이용한 문단 텍스트 추출.
- `find_objects.py` – `ObjectFinder`로 특정 요소와 주석 검색.
- `build_release_checklist.py` – 메모 필드 앵커와 스타일 치환을 포함한 QA용 HWPX 생성 스크립트.
- `FormattingShowcase.hwpx` – 각종 서식과 개체가 포함된 샘플 문서.

## 추가 자료

- [DevDoc/OWPML 스키마 구성.md](DevDoc/OWPML%20%EC%8A%A4%ED%82%A4%EB%A7%88%20%EA%B5%AC%EC%84%B1.md) – HWPX 문서에서 사용되는 OWPML 요소를 자세히 다룹니다.
- [DevDoc/컨테이너 패키징.md](DevDoc/%EC%BB%A8%ED%85%8C%EC%9D%B4%EB%84%88%20%ED%8C%A8%ED%82%A4%EC%A7%95.md) – HWPX OPC 아카이브 구성 규칙과 관례를 정리했습니다.
- [hancom-io/hwpx-owpml-model](https://github.com/hancom-io/hwpx-owpml-model) – 스키마 동작을 참조하기 위한 공식 C++ 기반 OWPML 모델 구현입니다.
- [neolord0/hwpxlib](https://github.com/neolord0/hwpxlib) – HWPX 문서를 읽고 쓰기 위한 레퍼런스 Java 라이브러리입니다.

## 기여하기

버그 리포트와 패치 제안은 언제나 환영합니다. 개발 환경 설정과 테스트 방법은 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.

## 연락처
- kokyuhyun@hotmail.com