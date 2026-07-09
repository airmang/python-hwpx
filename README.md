<p align="center">
  <h1 align="center">python-hwpx</h1>
  <p align="center">
    <strong>한글 없이 HWPX 문서를 Python으로 읽고, 편집하고, 생성하고, 검증합니다.</strong>
  </p>
  <p align="center">
    <a href="https://pypi.org/project/python-hwpx/"><img src="https://img.shields.io/pypi/v/python-hwpx?color=blue&label=PyPI" alt="PyPI"></a>
    <a href="https://pypi.org/project/python-hwpx/"><img src="https://img.shields.io/pypi/pyversions/python-hwpx" alt="Python"></a>
    <a href="https://github.com/airmang/python-hwpx/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="License"></a>
    <a href="https://airmang.github.io/python-hwpx/"><img src="https://img.shields.io/badge/docs-Sphinx-8CA1AF" alt="Docs"></a>
  </p>
</p>

---

## 🧩 HWPX Stack (3종)

| 계층 | 레포 | 역할 |
|---|---|---|
| 📦 라이브러리 | **[`python-hwpx`](https://github.com/airmang/python-hwpx)** | 순수 파이썬 HWPX 파싱·편집·생성 코어 |
| 🔌 MCP 서버 | [`hwpx-mcp-server`](https://github.com/airmang/hwpx-mcp-server) | MCP 클라이언트(Claude Desktop, VS Code 등)에서 HWPX 조작 |
| 🎯 에이전트 스킬 | [`hwpx-skill`](https://github.com/airmang/hwpx-plugins) | 에이전트가 HWPX를 바로 쓰게 해주는 공식 온보딩 스킬 |

---

## 왜 python-hwpx인가

- **한컴오피스 설치 불필요** — HWPX는 ZIP+XML(OWPML/OPC) 구조라, 순수 파이썬으로 Windows·macOS·Linux·CI 어디서나 읽고 씁니다.
- **읽기부터 생성까지 한 코어** — 텍스트/서식 추출, 문단·표·양식 편집, 새 문서 생성, XSD 스키마 검증을 하나의 API로 처리합니다.
- **에이전트·자동화 친화** — 같은 스택 위에서 `hwpx-mcp-server`와 공식 스킬이 직결됩니다.

## 빠른 시작

```bash
pip install python-hwpx      # Python 3.10+ · lxml ≥ 4.9
```

```python
from hwpx import HwpxDocument

# 기존 문서 열기 → 편집 → 저장
doc = HwpxDocument.open("보고서.hwpx")
doc.add_paragraph("자동화로 추가한 문단입니다.")
doc.save_to_path("보고서-수정.hwpx")

# 새 문서 만들기
new = HwpxDocument.new()
new.add_paragraph("python-hwpx로 만든 새 문서")
new.save_to_path("새문서.hwpx")
```

> 💡 컨텍스트 매니저도 지원합니다 — `with` 블록을 벗어나면 리소스가 자동 정리됩니다:
> ```python
> with HwpxDocument.open("보고서.hwpx") as doc:
>     doc.add_paragraph("자동으로 리소스가 정리됩니다.")
>     doc.save_to_path("결과물.hwpx")
> ```

`open`/`new` → `edit`/`extract` → `save_to_path` 흐름만 잡으면 나머지는 필요할 때 확장하면 됩니다.

## 무엇을 하나

### 🔍 읽기 · 추출
- 텍스트/HTML/Markdown 내보내기 — `export_text()` · `export_html()` · `export_markdown()`
- **풍부한 Markdown** — `export_rich_markdown()`은 인라인 서식(`**굵게**`·`*기울임*`·`~~취소선~~`), 중첩 표(colspan/rowspan 안전), 도형 텍스트, 이미지, 각주/미주, 하이퍼링크, 제목(`#`/`##`) 자동 감지까지 보존
- **문서 ingest 게이트웨이** — `hwpx.ingest.DocumentIngestor`가 HWPX를 감지해 rich Markdown과 섹션/표 메타데이터로 정규화
- `TextExtractor` / `ObjectFinder` — 섹션·문단 순회, 태그·속성·XPath로 객체 탐색 (`hp:tab`은 `\t`로 보존, roundtrip 안전)

```python
doc = HwpxDocument.open("보고서.hwpx")
md = doc.export_rich_markdown(
    image_dir="out/images",       # BinData 이미지를 디스크에 추출
    image_ref_prefix="images/",   # 마크다운 내 ![](images/...) 경로 접두
    detect_headings=True,         # Ⅰ./1. 패턴 기반 #/## 자동
)
```

### ✏️ 편집
- 문단 추가/삭제/서식, Run 단위 볼드·이탤릭·밑줄·색상
- 섹션 추가/삭제(`add_section(after=)`·`remove_section()`, manifest 자동 관리)
- 표 생성·셀 텍스트·병합/분할·중첩 테이블, 이미지 임베드, 머리글/바닥글, 메모(앵커 기반), 각주/미주, 북마크/하이퍼링크, 다단 편집
- **기존 문서 서식 편집** — 정렬·줄간격·들여쓰기·문단 간격, 용지·여백·방향, 쪽번호, 불릿/번호
- **스타일 기반 치환** — 색상·밑줄·`charPrIDRef`로 Run을 필터링해 선택 교체(`replace_text_in_runs`·`find_runs_by_style`)

```python
# 빨간색 텍스트만 찾아서 치환
doc.replace_text_in_runs("임시", "확정", text_color="#FF0000")
```

### 🖊️ 양식 채우기 (byte-preserving)
- 누름틀(클릭히어) 필드 조회·서식 보존 채움, 라벨 기반 셀 탐색(`find_cell_by_label`)·경로 채우기(`fill_by_path`)
- **바이트 보존 구조 편집** — 셀 채우기 / 행·열·표 삭제·삽입 / 열 너비 오토핏 / 폰트 shrink-to-fit 을 문서 재조립 없이 수행해 양식 서식을 그대로 보존. 미수정 영역은 `hwpx.patch`가 section XML 바이트를 splice해 손대지 않음

```python
doc = HwpxDocument.open("신청서.hwpx")
result = doc.fill_by_path({
    "성명 > right": "홍길동",
    "소속 > right": "플랫폼팀",
})
doc.save_to_path("신청서-작성완료.hwpx")
print(result["applied_count"], result["failed_count"])
```

### 🏗️ 생성 · 공문서 도구
- `hwpx.builder` — Section/Heading/Table/Image/Header 조립형 생성 + 하드게이트 저장 리포트
- 공문서 도구 — `official_lint`(항목기호 위계·"끝." 표시·붙임·날짜 lint), 결재란 프리셋
- `advanced_generators` — 사진대지(image_grid)·회의 명패·표 기반 조직도
- `mail_merge` — 템플릿+데이터 N부 대량 생성, 표 합계·평균 계산
- `doc_diff` — 문단 LCS diff·신구대조표·참조 정합 lint
- `style_profile` — 참조 문서 프로파일 추출·적용, 템플릿 레지스트리

### ✅ 검증 · 안전 · 저수준
- XSD 스키마 + 패키지 구조 검증 — CLI `hwpx-validate` · `hwpx-validate-package`, `hwpx-analyze-template`
- `validate_editor_open_safety` — 저장/팩/리페어/빌더 출력 게이트, `openSafety` 증거 반환
- `hwpx.tools.fuzz`(시드 결정적 시나리오·3중 오라클) · `hwpx.tools.layout_preview`(페이지 박스 근사 HTML/PNG 자기검증) · `opc.security`(XML entity·ZIP 압축 폭탄 가드)
- `hwpx.oxml` 데이터클래스로 OWPML 스키마 ↔ Python 객체 직접 조작, HWPML 2016→2011 네임스페이스 자동 정규화

```bash
hwpx-validate-package 보고서.hwpx
hwpx-analyze-template 보고서.hwpx
```

> 전체 기능·클래스·메서드 목록은 [사용 가이드](docs/usage.md)와 [API 레퍼런스](https://airmang.github.io/python-hwpx/api_reference.html)를 참고하세요.

## 대항 라이브러리 비교

| | python-hwpx | pyhwpx | pyhwp |
|---|---|---|---|
| **대상 포맷** | `.hwpx` (OWPML/OPC) | `.hwpx` | `.hwp` (v5 바이너리) |
| **한/글 설치** | 불필요 | 필요 (Windows COM) | 불필요 |
| **크로스 플랫폼** | ✅ Linux / macOS / Windows / CI | ❌ Windows 전용 | ✅ |
| **편집/생성 API** | ✅ | ✅ (COM) | ❌ 대부분 읽기 |
| **스키마 검증** | ✅ | ❌ | ❌ |
| **AI 에이전트 연동 (MCP)** | ✅ `hwpx-mcp-server` | ❌ | ❌ |

> HWP(v5 바이너리) 파일은 지원하지 않습니다. 한컴오피스에서 HWPX로 변환 후 사용하세요.

## 알려진 제약

- `add_shape()` / `add_control()`은 한/글이 요구하는 모든 하위 요소를 생성하지 않습니다. 복잡한 개체 추가 시 한/글에서 열어 검증하세요.
- 이미지 바이너리 임베드는 지원하지만 `<hp:pic>` 요소의 완전 자동 생성은 제공하지 않습니다.
- 암호화된 HWPX 파일의 암복호화는 지원하지 않습니다.

## 더 보기

- **[🚀 빠른 시작](docs/quickstart.md)** · **[📚 사용 가이드](docs/usage.md)** — 첫 파일 열기부터 문단·표·메모·섹션 편집, 텍스트 추출·검증까지
- **[💡 예제 모음](docs/examples.md)** · [`examples/`](examples/) — `build_release_checklist.py`(메모·스타일 편집 HWPX 생성), `extract_text.py`(CLI 텍스트 추출), `find_objects.py`(OWPML 노드 추적) 등
- **[📐 스키마 개요](docs/schema-overview.md)** · **[🔧 설치 검증](docs/installation.md)**
- **[📖 전체 문서 (Sphinx)](https://airmang.github.io/python-hwpx/)** — API 레퍼런스·50+ 실전 패턴·FAQ
- **[📝 CHANGELOG](CHANGELOG.md)** · **[🤝 CONTRIBUTING](CONTRIBUTING.md)** · **[👥 CONTRIBUTORS](CONTRIBUTORS.md)**

## 기여하기

버그 리포트, 기능 제안, PR 모두 환영합니다.

```bash
git clone https://github.com/airmang/python-hwpx.git
cd python-hwpx
pip install -e ".[dev]"
pytest
```

## 감사의 말

아래 공개 표준·프로젝트에 빚지고 있습니다.

- **[OWPML — 개방형 워드프로세서 마크업 언어 (KS X 6101)](https://www.kssn.net/search/stddetail.do?itemNo=K001010119985)** — HWPX가 기반하는 한국 산업 표준
- **[hancom-io/hwpx-owpml-model](https://github.com/hancom-io/hwpx-owpml-model)** — OWPML 요소 구조 참조 모델 · **[neolord0/hwpxlib](https://github.com/neolord0/hwpxlib)** — 오라클 샘플 코퍼스
- **[edwardkim/rhwp](https://github.com/edwardkim/rhwp)** — 멱등성·검증 게이트 설계 영감
- **범정부오피스** — 공무 문서 편집 워크플로 아이디어

## License

Apache License 2.0. See LICENSE and NOTICE.

## Maintainer

Primary maintainer/contact: **고규현** — 광교고등학교 정보·컴퓨터 교사

- ✉️ [kokyuhyun@hotmail.com](mailto:kokyuhyun@hotmail.com)
- 🐙 [@airmang](https://github.com/airmang)
