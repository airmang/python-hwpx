<p align="center">
  <h1 align="center">python-hwpx</h1>
  <p align="center">
    <strong>HWPX 문서를 Python으로 읽고, 편집하고, 생성합니다.</strong>
  </p>
  <p align="center">
    <a href="https://pypi.org/project/python-hwpx/"><img src="https://img.shields.io/pypi/v/python-hwpx?color=blue&label=PyPI" alt="PyPI"></a>
    <a href="https://pypi.org/project/python-hwpx/"><img src="https://img.shields.io/pypi/pyversions/python-hwpx" alt="Python"></a>
    <a href="https://github.com/airmang/python-hwpx/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Custom%20Noncommercial-orange" alt="License: Custom Non-Commercial"></a>
    <a href="https://airmang.github.io/python-hwpx/"><img src="https://img.shields.io/badge/docs-Sphinx-8CA1AF" alt="Docs"></a>
  </p>
</p>

---

`python-hwpx`는 한컴오피스의 [HWPX 포맷](https://www.hancom.com/)을 순수 Python으로 다루는 라이브러리이자 CLI 도구 모음입니다.
한/글 설치 없이, OS에 관계없이 HWPX 문서의 구조를 파싱하고 콘텐츠를 조작할 수 있습니다.
문서 편집 API뿐 아니라 스키마/패키지 검증, unpack/pack, 템플릿 분석 같은 XML-first 워크플로도 함께 제공합니다.

> **pyhwpx / pyhwp와 다른 점?**
> | | python-hwpx | pyhwpx | pyhwp |
> |---|---|---|---|
> | **대상 포맷** | `.hwpx` (OWPML/OPC) | `.hwpx` | `.hwp` (v5 바이너리) |
> | **한/글 설치** | 불필요 | 필요 (Windows COM) | 불필요 |
> | **크로스 플랫폼** | ✅ Linux / macOS / Windows / CI | ❌ Windows 전용 | ✅ |
> | **방식** | 직접 XML 파싱 | COM 자동화 | OLE 파싱 |

## 🌍 크로스 플랫폼 지원

HWPX 파일은 **ZIP + XML** 구조이므로, 한/글 프로그램 없이 Python만으로 읽고 편집하는 워크플로를 구성할 수 있습니다.

| 플랫폼 | 읽기 | 쓰기 | 비고 |
|--------|------|------|------|
| ✅ Windows | ✅ | ✅ | 한컴오피스 |
| ✅ macOS | ✅ | ✅ | 한컴오피스 Mac |
| ✅ Linux | ✅ | ✅ | 한컴오피스 Linux |
| ✅ CI/CD | ✅ | ✅ | Docker, GitHub Actions 등 |

## 설치

```bash
pip install python-hwpx
```

> 유일한 의존성은 `lxml`입니다.

## Quick Start

```python
from hwpx import HwpxDocument

# 빈 문서 새로 만들기
doc = HwpxDocument.new()

# 기존 문서를 수정하려면:
# doc = HwpxDocument.open("보고서.hwpx")

# 문단 추가
paragraph = doc.add_paragraph("python-hwpx로 생성한 문단입니다.")

# 표 추가 (2×3)
table = doc.add_table(rows=2, cols=3)
table.set_cell_text(0, 0, "이름")
table.set_cell_text(0, 1, "부서")
table.set_cell_text(0, 2, "연락처")

# 메모 추가 (기본 템플릿의 memo shape 사용)
doc.add_memo_with_anchor("검토 필요", paragraph=paragraph, memo_shape_id_ref="0")

# 저장
doc.save_to_path("결과물.hwpx")
```

> 💡 컨텍스트 매니저도 지원합니다:
> ```python
> with HwpxDocument.open("보고서.hwpx") as doc:
>     doc.add_paragraph("자동으로 리소스가 정리됩니다.")
>     doc.save_to_path("결과물.hwpx")
> ```

## 주요 기능 한눈에 보기

| 카테고리 | 기능 | 설명 |
|----------|------|------|
| 📄 **문서 I/O** | 열기/저장/생성 | 파일, 바이트, 스트림 입출력 · 원자적 저장 · ZIP 무결성 검증 |
| 📝 **단락** | 추가/삭제/편집/서식 | 텍스트 설정, 단락 삭제(`remove_paragraph`), 스타일 참조 |
| ✏️ **Run** | 텍스트 조각 | 추가, 교체, 볼드/이탤릭/밑줄/색상 서식 |
| 📊 **표(Table)** | 생성/편집/병합 | N×M 표 생성, 셀 텍스트, 셀 병합/분할, 중첩 테이블 |
| 🧭 **표 자동화** | 탐색/채우기 | 테이블 맵, 라벨 기반 셀 탐색, 경로 기반 배치 채우기 |
| 📑 **섹션** | 추가/삭제 | `add_section(after=)`, `remove_section()`, manifest 자동 관리 |
| 🖼️ **이미지** | 임베드/삭제 | 바이너리 데이터 관리, manifest 자동 등록 |
| ✏️ **도형** | 선/사각형/타원 | OWPML 명세 준수 도형 삽입 |
| 📑 **머리글/바닥글** | 설정/제거 | 홀수/짝수/양쪽 페이지 구분 |
| 💬 **메모** | 추가/삭제 | 앵커 기반 메모, 메모 셰이프 참조 |
| 📌 **각주/미주** | 추가 | 텍스트 접근 |
| 🔗 **북마크/하이퍼링크** | 삽입/조회 | URL 링크, 내부 북마크 |
| 📰 **다단 편집** | 컬럼 정의 | 다단 레이아웃 제어 |
| 🔍 **텍스트 추출** | 파이프라인 | 섹션/단락 순회, 주석 렌더링, 중첩 객체 제어 |
| 🔎 **객체 검색** | 태그/속성/XPath | 특정 요소 탐색, 주석 이터레이터 |
| 🎨 **스타일 치환** | 서식 기반 필터 | 색상/밑줄/charPrIDRef 기반 Run 검색 및 교체 |
| 📤 **내보내기** | 텍스트/HTML/Markdown | 문서 변환 출력 |
| ✅ **유효성 검사** | XSD + 패키지 구조 | CLI(`hwpx-validate`, `hwpx-validate-package`) 및 API |
| 🧰 **작업 도구** | unpack/pack/분석/비교 | pack-ready 작업 디렉터리 추출과 재구성 점검 |
| 🏗️ **저수준 XML** | 데이터클래스 매핑 | OWPML 스키마 ↔ Python 객체 직접 조작 |
| 🔄 **네임스페이스 호환** | 자동 정규화 | HWPML 2016 → 2011 자동 변환 |

## 기능 상세

### 📄 문서 편집

문단, 표, 메모, 머리글/바닥글을 Python 객체로 다룹니다.

```python
# 단락 추가·삭제
doc.add_paragraph("새 문단")
doc.remove_paragraph(doc.paragraphs[-1])   # 마지막 단락 삭제

# 섹션 추가·삭제
new_sec = doc.add_section()          # 문서 끝에 섹션 추가
new_sec.add_paragraph("두 번째 섹션 내용")
doc.remove_section(1)                # 인덱스로 섹션 삭제

# 머리글·바닥글
doc.set_header_text("기밀 문서", page_type="BOTH")
doc.set_footer_text("1 / 10", page_type="BOTH")

# 표 셀 병합·분할
table.merge_cells(0, 0, 1, 1)   # (0,0)~(1,1) 병합
table.set_cell_text(0, 0, "병합된 셀", logical=True, split_merged=True)

# 양식형 표 자동 채우기
form = doc.add_table(2, 2)
form.cell(0, 0).text = "성명:"
form.cell(1, 0).text = "소속"

doc.find_cell_by_label("성명")    # {"matches": [...], "count": 1}
doc.fill_by_path({
    "성명 > right": "홍길동",
    "소속 > right": "플랫폼팀",
})
```

### 🔍 텍스트 추출 & 검색

```python
from hwpx import TextExtractor, ObjectFinder

# 텍스트 추출
with TextExtractor("문서.hwpx") as extractor:
    for section in extractor.iter_sections():
        for para in extractor.iter_paragraphs(section):
            print(para.text())

# 특정 객체 탐색
for obj in ObjectFinder("문서.hwpx").find_all(tag="tbl"):
    print(obj.tag, obj.path)
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

### 📤 내보내기

```python
# 텍스트, HTML, Markdown으로 변환
text = doc.export_text()
html = doc.export_html()
md   = doc.export_markdown()
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
├── hwpx.opc             # OPC 컨테이너 읽기/쓰기 (원자적 저장, ZIP 무결성 검증)
├── hwpx.oxml            # OWPML XML ↔ 데이터클래스 매핑
│   ├── document.py      #   섹션, 문단, 표, 런, 메모, 도형, 노트
│   ├── header.py        #   헤더 참조 목록 (스타일, 글머리표, 변경추적 등)
│   ├── body.py          #   타입이 지정된 본문 모델
│   └── common.py        #   범용 XML ↔ 데이터클래스
├── hwpx.tools
│   ├── archive_cli      #   unpack/pack CLI 및 재패킹 메타데이터
│   ├── text_extractor   #   텍스트 추출 파이프라인
│   ├── text_extract_cli #   텍스트 추출 CLI
│   ├── object_finder    #   객체 탐색 유틸리티
│   ├── exporter         #   텍스트/HTML/Markdown 내보내기
│   ├── validator        #   스키마 유효성 검사 (hwpx-validate CLI)
│   ├── package_validator#   ZIP/OPC/HWPX 구조 검사
│   ├── page_guard       #   구조 변화 징후 점검
│   └── template_analyzer#   레퍼런스 문서 분석/추출
└── hwpx.templates       # 내장 빈 문서 템플릿
```

## CLI

```bash
# HWPX 문서 스키마 유효성 검사
hwpx-validate 문서.hwpx

# ZIP/OPC/HWPX 패키지 구조 검사
hwpx-validate-package 문서.hwpx

# HWPX 풀기 / 다시 묶기 (기본값: XML/HWPF 바이트 보존)
hwpx-unpack 문서.hwpx ./unpacked
hwpx-unpack 문서.hwpx ./pretty-unpacked --pretty-xml
hwpx-pack ./unpacked ./repacked.hwpx

# 레퍼런스 문서 분석과 작업 디렉터리 추출
hwpx-analyze-template 문서.hwpx --extract-dir ./template-parts --json
hwpx-pack ./template-parts ./template-roundtrip.hwpx
hwpx-validate-package ./template-roundtrip.hwpx

# plain / markdown 텍스트 추출
hwpx-text-extract 문서.hwpx --format markdown --output 문서.md

# 문서 구조 변화 징후 비교
hwpx-page-guard --reference 원본.hwpx --output 결과.hwpx
```

`hwpx-page-guard`는 렌더된 실제 쪽수를 계산하지 않습니다. 대신 단락 수, 표 수, shape/control 수, 명시적 page/column break, 텍스트 길이 같은 구조 지표를 비교해 편집 전후 변화 징후를 빠르게 점검합니다.

`hwpx-validate-package`는 `Contents/content.hpf` 같은 고정 경로를 전제로 두지 않고, `META-INF/container.xml`과 실제 rootfile/manifest 선언을 따라가며 패키지 구조를 확인합니다. 엔진이 열 수 있는 비표준 패키지는 가능한 경우 경고로 분리해 보여줍니다.

`hwpx-analyze-template --extract-dir`는 다시 묶고 점검하기 쉬운 작업 디렉터리를 만듭니다. 재구성과 구조 검증에 필요한 파일을 함께 꺼내는 용도이며, 편집기에서의 최종 렌더링 결과까지 보장한다는 뜻은 아닙니다.

## 문서

| | |
|---|---|
| **[📖 전체 문서](https://airmang.github.io/python-hwpx/)** | Sphinx 기반 API 레퍼런스, 사용 가이드, FAQ |
| **[🚀 빠른 시작](https://airmang.github.io/python-hwpx/quickstart.html)** | 5분 안에 HWPX 문서 다루기 |
| **[📚 사용 가이드](https://airmang.github.io/python-hwpx/usage.html)** | 50+ 실전 사용 패턴 |
| **[🔧 API 레퍼런스](https://airmang.github.io/python-hwpx/api_reference.html)** | 클래스·메서드 상세 명세 |
| **[📐 스키마 개요](https://airmang.github.io/python-hwpx/schema-overview.html)** | OWPML 스키마 구조 설명 |

## 지원 포맷

| 포맷 | 확장자 | 읽기 | 쓰기 |
|------|--------|------|------|
| HWPX | `.hwpx` | ✅ | ✅ |
| HWP | `.hwp` | ❌ | ❌ |

> **Note:** HWP(v5 바이너리) 파일은 지원하지 않습니다. 한컴오피스에서 HWPX로 변환 후 사용하세요.

## 요구 사항

- Python 3.10+
- lxml ≥ 4.9

## 알려진 제약

- `add_shape()` / `add_control()`은 한/글이 요구하는 모든 하위 요소를 생성하지 않습니다.
  복잡한 개체를 추가할 때는 한/글에서 열어 검증해 주세요.
- 이미지 삽입 시 바이너리 임베드는 지원하지만, `<hp:pic>` 요소의 완전한 자동 생성은 제공하지 않습니다.
- 암호화된 HWPX 파일의 암복호화는 지원하지 않습니다.

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

[Custom Non-Commercial License](LICENSE) © python-hwpx Maintainers

Commercial use requires separate permission from the copyright holders.

<br>

## Maintainer

Primary maintainer/contact: **고규현** — 광교고등학교 정보·컴퓨터 교사

- ✉️ [kokyuhyun@hotmail.com](mailto:kokyuhyun@hotmail.com)
- 🐙 [@airmang](https://github.com/airmang)
