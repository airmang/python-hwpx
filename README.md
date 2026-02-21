<p align="center">
  <h1 align="center">python-hwpx</h1>
  <p align="center">
    <strong>HWPX 문서를 Python으로 읽고, 편집하고, 생성합니다.</strong>
  </p>
  <p align="center">
    <a href="https://pypi.org/project/python-hwpx/"><img src="https://img.shields.io/pypi/v/python-hwpx?color=blue&label=PyPI" alt="PyPI"></a>
    <a href="https://pypi.org/project/python-hwpx/"><img src="https://img.shields.io/pypi/pyversions/python-hwpx" alt="Python"></a>
    <a href="https://github.com/airmang/python-hwpx/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Non--Commercial-green" alt="License"></a>
    <a href="https://airmang.github.io/python-hwpx/"><img src="https://img.shields.io/badge/docs-Sphinx-8CA1AF" alt="Docs"></a>
  </p>
</p>

---

`python-hwpx`는 한컴오피스의 [HWPX 포맷](https://www.hancom.com/)을 순수 Python으로 다루는 라이브러리입니다.
한/글 설치 없이, OS에 관계없이 HWPX 문서의 구조를 파싱하고 콘텐츠를 조작할 수 있습니다.

> **pyhwpx / pyhwp와 다른 점?**
> `pyhwpx`는 Windows COM 자동화 기반이라 한/글이 설치된 Windows에서만 동작합니다.
> `pyhwp`는 레거시 `.hwp`(v5 바이너리) 전용입니다.
> `python-hwpx`는 OWPML/OPC 기반 `.hwpx`를 직접 파싱하므로 **Linux, macOS, CI 환경 어디서든** 동작합니다.

## 설치

```bash
pip install python-hwpx
```

> 유일한 의존성은 `lxml`입니다.

## Quick Start

```python
from hwpx.document import HwpxDocument

# 기존 문서 열기
doc = HwpxDocument.open("보고서.hwpx")

# 빈 문서 새로 만들기
doc = HwpxDocument.new()

# 문단 추가
doc.add_paragraph("python-hwpx로 생성한 문단입니다.")

# 표 추가 (2×3)
table = doc.add_table(rows=2, cols=3)
table.set_cell_text(0, 0, "이름")
table.set_cell_text(0, 1, "부서")
table.set_cell_text(0, 2, "연락처")

# 메모 추가 (한/글에서 바로 표시)
paragraph = doc.paragraphs[0]
doc.add_memo_with_anchor("검토 필요", paragraph=paragraph)

# 저장
doc.save("결과물.hwpx")
```

## 주요 기능

### 📄 문서 편집

문단, 표, 메모, 머리말/꼬리말을 Python 객체로 다룹니다.

```python
# 머리말·꼬리말
doc.set_header_text("기밀 문서", page_type="BOTH")
doc.set_footer_text("— 1 —", page_type="BOTH")

# 표 셀 병합·분할
table.merge_cells(0, 0, 1, 1)   # (0,0)~(1,1) 병합
table.set_cell_text(0, 0, "병합된 셀", logical=True, split_merged=True)
```

### 🔍 텍스트 추출 & 검색

```python
from hwpx import TextExtractor, ObjectFinder

# 텍스트 추출
for section in TextExtractor("문서.hwpx"):
    for para in section.paragraphs:
        print(para.text)

# 특정 객체 탐색
for obj in ObjectFinder("문서.hwpx").find("tbl"):
    print(obj.tag, obj.attributes)
```

### 🎨 스타일 기반 텍스트 치환

서식(색상, 밑줄, charPrIDRef)으로 런을 필터링해 선택적으로 교체합니다.

```python
# 빨간색 텍스트만 찾아서 치환
doc.replace_text_in_runs(
    "임시", "확정",
    text_color="#FF0000",
)

# 특정 서식의 런 검색
runs = doc.find_runs_by_style(underline_type="SINGLE")
```

### 🏗️ 저수준 XML 제어

OWPML 스키마에 매핑된 데이터클래스로 XML 구조를 직접 다룹니다.

```python
# 헤더 참조 목록
doc.border_fills    # 테두리 채우기
doc.bullets         # 글머리표
doc.styles          # 스타일
doc.track_changes   # 변경 추적

# 바탕쪽·이력·버전 파트
doc.master_pages
doc.histories
doc.version
```

## 아키텍처

```
python-hwpx
├── hwpx.document        # 고수준 편집 API (HwpxDocument)
├── hwpx.package         # OPC 컨테이너 읽기/쓰기
├── hwpx.oxml            # OWPML XML ↔ 데이터클래스 매핑
│   ├── document.py      #   섹션, 문단, 표, 런, 메모
│   ├── header.py        #   헤더 참조 목록 (스타일, 글머리표, 변경추적 등)
│   └── body.py          #   타입이 지정된 본문 모델
├── hwpx.tools
│   ├── text_extractor   #   텍스트 추출 파이프라인
│   ├── object_finder    #   객체 탐색 유틸리티
│   └── validator        #   스키마 유효성 검사 (hwpx-validate CLI)
└── hwpx.templates       # 내장 빈 문서 템플릿
```

## CLI

```bash
# HWPX 문서 스키마 유효성 검사
hwpx-validate 문서.hwpx
```

## 문서

| | |
|---|---|
| **[📖 전체 문서](https://airmang.github.io/python-hwpx/)** | Sphinx 기반 API 레퍼런스, 사용 가이드, FAQ |
| **[🚀 빠른 시작](https://airmang.github.io/python-hwpx/quickstart.html)** | 5분 안에 HWPX 문서 다루기 |
| **[📚 사용 가이드](https://airmang.github.io/python-hwpx/usage.html)** | 50+ 실전 사용 패턴 |
| **[🔧 API 레퍼런스](https://airmang.github.io/python-hwpx/api_reference.html)** | 클래스·메서드 상세 명세 |
| **[📐 스키마 개요](https://airmang.github.io/python-hwpx/schema-overview.html)** | OWPML 스키마 구조 설명 |

## 요구 사항

- Python 3.10+
- lxml ≥ 4.9

## 알려진 제약

`add_shape()` / `add_control()`은 한/글이 요구하는 모든 하위 요소를 생성하지 않습니다.
복잡한 개체를 추가할 때는 한/글에서 열어 검증해 주세요.

## 기여하기

버그 리포트, 기능 제안, PR 모두 환영합니다.
개발 환경 설정과 테스트 방법은 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.

```bash
git clone https://github.com/airmang/python-hwpx.git
cd python-hwpx
pip install -e ".[dev]"
pytest
```

## License

[MIT](LICENSE) © 고규현 (Kyuhyun Koh)

<br>

## Author

**고규현** — 광교고등학교 정보·컴퓨터 교사

- ✉️ [kokyuhyun@hotmail.com](mailto:kokyuhyun@hotmail.com)
- 🐙 [@airmang](https://github.com/airmang)
