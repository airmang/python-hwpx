# python-hwpx 7.0 이주 가이드

6.12.0 에서 7.0.0 으로 올리면 **결과가 달라지는 호출**이 있다. 대부분은 인자 하나로
6.x 의 결과를 그대로 얻는다. 6.0 에서 옮긴 옛 이름과 `section_index=` 의 정리는
[옛 이름 제거](#옛-이름-제거) 절에 있다. 변환·짐작 기능(Markdown·HTML, ingest, 이름표로 칸 찾기,
메일 머지, 미리보기 …)은 python-hwpx-automation 으로 옮겼다 — [옮겨 간 기능](#옮겨-간-기능) 절.

## 옮겨 간 기능

7.0 의 python-hwpx 는 "파일에 적힌 대로 읽고 쓰는" 엔진만 남긴다. 다른 형식으로의 변환, 양식의 뜻
짐작, 보고서 모양 같은 취향, 미리보기 그리기, 장르 규칙은 **python-hwpx-automation 8.0** 으로
옮겼다. 인자와 결과는 6.x 와 같고, 문서의 메서드였던 것은 문서를 첫 인자로 받는 함수가 됐다.

```bash
pip install python-hwpx-automation        # python-hwpx 7.0 을 함께 설치한다
pip install "python-hwpx-automation[xlsx]"      # 메일 머지의 .xlsx 명부
pip install "python-hwpx-automation[preview]"   # 미리보기의 수식 MathML
```

옛 이름을 부르면 새 자리와 설치 명령을 알려 주는 오류가 난다. 본체는 자동화 패키지를 import 하지 않는다.

| 형태 | 오류 |
|---|---|
| `from hwpx import X`, `from hwpx.tools import X`, `from hwpx.experimental import X`, `from hwpx.equation import X` 등 | `hwpx.MovedToCompanion`(`ImportError`) — 메시지에 `from hwpx_automation... import ...` 한 줄 |
| `import hwpx.tools.markdown_import` 등 지운 모듈 | `ModuleNotFoundError` — 메시지에 새 모듈 |
| `doc.text.markdown(...)` 등 문서 메서드 | `hwpx.errors.HwpxAttributeError`, `code="document-name-moved"`(`context` 에 `replacement`·`install`). `hasattr` 는 `False` |

| python-hwpx 6.x | python-hwpx-automation 8.0 |
|---|---|
| `hwpx.tools.markdown_import.from_markdown`·`MarkdownStyle` | `hwpx_automation.markdown.from_markdown`·`MarkdownStyle` |
| `doc.text.append_markdown(md, ...)` | `hwpx_automation.markdown.append_markdown(doc, md, ...)` |
| `doc.text.markdown(...)`, `doc.text.markdown(rich=True, ...)`, `hwpx.tools.markdown_export.export_markdown` | `hwpx_automation.markdown.to_markdown(doc, ...)`, `to_markdown(doc, rich=True, ...)` |
| `doc.text.html(...)`, `hwpx.tools.exporter.export_html` | `hwpx_automation.markdown.to_html(doc, ...)` |
| `hwpx.tools.exporter.export_markdown` | `hwpx_automation.markdown.to_markdown(doc)` |
| `hwpx.tools.markdown_export.equation_markdown` | `hwpx_automation.markdown.equation_markdown` |
| `hwpx.HwpxMarkdownConverter`, `hwpx.ingest.*`, `hwpx.experimental` 의 ingest 7개 | `hwpx_automation.ingest.*` |
| `hwpx.integrations.langchain.HwpxLoader`, `hwpx.integrations.llama_index.HwpxReader` | `hwpx_automation.integrations.langchain` / `.llama_index` |
| `doc.tables.find_cell_by_label(label, ...)`, `form_slots(...)`, `fill_by_path(mappings, ...)` | `hwpx_automation.forms.find_cell_by_label(doc, label, ...)`, `form_slots(doc, ...)`, `fill_by_path(doc, mappings, ...)` |
| `doc.fields.choices()`, `doc.fields.choose(selections)` | `hwpx_automation.forms.form_choices(doc)`, `choose(doc, selections)` |
| `hwpx.merge_template_rows`·`load_mail_merge_rows`·`inspect_mail_merge_placeholders`·`MAIL_MERGE_REPORT_VERSION`, `hwpx.tools.mail_merge` | `hwpx_automation.mail_merge.*` |
| `hwpx.experimental.render_layout_preview`·`LayoutPreview`·`PreviewPage`·`render_document_viewer`·`DocumentViewer`, `hwpx.tools.layout_preview`·`document_viewer` | `hwpx_automation.preview.*` |
| `hwpx.equation.render_equation`·`EquationRender`·`LABEL_*`·`latex_to_mathml`·`latex2mathml_available`·`MathMLUnavailableError` | `hwpx_automation.preview.*` |
| `hwpx.tools.format_rules`, 명령 `hwpx-check-format` | `hwpx_automation.format_rules`, 같은 이름의 명령(python-hwpx-automation 이 선언) |
| `hwpx.tools.table_cleanup`, `hwpx.tools.report_utils` | `hwpx_automation.office.utilities` |
| `hwpx.inspect_reference_consistency`, `REFERENCE_CONSISTENCY_REPORT_VERSION` | `hwpx_automation.office.compliance` |
| 루트 옛 이름 `doc.export_markdown()`·`export_rich_markdown()`·`export_html()`·`fill_by_path()`·`find_cell_by_label()` | 위 `to_markdown`·`to_html`·`forms.*` |
| `hwpx-text-extract --format markdown` | `hwpx_automation.markdown.to_markdown(doc)` (평문 추출 `--format plain` 은 그대로) |

```python
from hwpx import HwpxDocument
from hwpx_automation.forms import fill_by_path
from hwpx_automation.markdown import append_markdown, to_markdown

doc = HwpxDocument.open("신청서.hwpx")
append_markdown(doc, "## 덧붙임\n\n- 확인 완료")        # 6.x doc.text.append_markdown(...)
result = fill_by_path(doc, {"성명 > right": "홍길동"})  # 6.x doc.tables.fill_by_path(...)
markdown = to_markdown(doc, rich=True)                  # 6.x doc.text.markdown(rich=True)
```

엔진에 남는 것: 평문(`doc.text.plain()`·`export_text`)·`outline`·`paragraphs`·`blocks`, 표 지도
(`doc.tables.map()`), 수식 변환(`latex_to_eqedit`·`eqedit_to_latex`)과 측정, 네이티브 메일 머지
**필드**(`paragraph.add_mail_merge_field`), 문서 합치기, 목차, 문서 비교(`doc_diff`), 변경 추적, 칸 맞춤
(`hwpx.form_fit`), 줄 배치 캐시, 품질 게이트. 미리보기가 쓰는 `EQEDIT_MATHML_OPERATOR_COMMANDS` 는
`hwpx.equation` 에서 내보낸다.

달라지는 점:

- `to_markdown`·`to_html` 은 **문서**를 받는다. 6.x `hwpx.tools.exporter.export_markdown`·`export_html` 은
  패키지 바이트도 받았다. 바이트는 `HwpxDocument.open(data)` 로 연 뒤 넘긴다.
- 본체의 `MarkdownStyle` 객체는 새 `from_markdown` 이 받지 않는다(클래스가 다르다).
  `hwpx_automation.markdown.MarkdownStyle` 을 쓴다.
- extra `xlsx`·`preview`·`langchain`·`llamaindex` 는 `pip install "python-hwpx[xlsx]"` 가 깨지지 않게 이름만
  남고 아무것도 설치하지 않는다(5.0 의 `visual` 과 같다). 그 의존성은 python-hwpx-automation 의 같은 이름
  extra 가 끈다.
- 오류 code `ingest-failed`·`ingest-format-unsupported`·`equation-mathml-unavailable`·`text-markdown-style-invalid`·
  `table-path-invalid-type` 는 그 기능과 함께 옮겨 갔다(자동화 패키지가 `hwpx.errors` 의 같은 클래스·code 로 낸다).

## 가장 먼저 볼 것 — `HwpxDocument.new()` 의 첫 줄

| 무엇이 달라지나 | 옛 동작을 유지하는 법 |
|---|---|
| `new()` 로 만든 문서에 처음 더한 문단(`add_paragraph`, `add_heading`)이 구역 설정을 담은 빈 첫 문단의 자리를 차지한다. 6.x 문서는 늘 빈 줄로 시작했다. **문단 번호가 하나씩 당겨진다**: 6.x 의 `doc.paragraphs[1]` 이 7.0 의 `doc.paragraphs[0]` 이다. 구역 설정과 먼저 넣어 둔 머리말·꼬리말·쪽 번호는 그 문단으로 옮겨 간다 | `HwpxDocument.new(empty_first_line=True)` |

달라지지 않는 경우: 표나 개체를 먼저 더한 문서(빈 줄 다음에 온다), 첫 줄을 직접 쓴 문서
(`doc.paragraphs[0].text = ...`), `open()` 으로 연 문서.

이 변경으로 함께 고쳐야 하는 습관이 둘 있다.

- **빈 첫 줄을 지우던 코드는 지운다.** 6.x 에서 흔하던 `doc.paragraphs[0].remove()`·
  `section.remove_paragraph(0)`·`paragraphs[0].runs[0].remove()` 는 7.0 에서 방금 쓴 첫 문단이나
  구역 설정을 지운다. 구역 설정(`hp:secPr`)이 사라진 문서는 용지 크기가 0×0 이 된다.
- **문단 번호와 `runs[0]` 에 기대지 않는다.** `add_paragraph()` 가 돌려준 문단 객체를 그대로 쓴다.
  첫 문단의 첫 런은 구역 설정을 담은 빈 런이라, `paragraph.runs[0]` 이 방금 쓴 글이 아닐 수 있다.

```python
from hwpx import HwpxDocument

doc = HwpxDocument.new()
title = doc.add_paragraph("2026 운영계획")   # 7.0: doc.paragraphs[0] (6.x: [1])
title.text = "2026 학교 운영계획"              # 번호 대신 돌려받은 객체로 고친다

legacy = HwpxDocument.new(empty_first_line=True)   # 6.x 처럼 빈 줄로 시작
legacy.add_paragraph("2026 운영계획")                # legacy.paragraphs[1]
```

## 만들기 — 결과 모양이 달라지는 것

| 무엇이 달라지나 | 옛 동작을 유지하는 법 |
|---|---|
| `add_equation` 이 적는 수식 글꼴이 `HYhwpEQ` 에서 `HancomEQN`(한/글 수식 편집기의 글꼴)으로 바뀌었다. 획이 조금 굵어지고 일부 글자 폭이 달라진다 | `doc.shapes.add_equation(script, font="HYhwpEQ")` |
| 수식 상자 폭을 한/글 2024(Windows)가 실제로 필요로 한 폭에 맞춰 다시 잡는다. 같은 수식의 `hp:sz` 폭이 6.x 와 다르다(맥 한/글이 저장한 상자보다 평균 10% 넓다) | 없음(6.x 폭은 수식 뒤 글자와 겹쳤다) |
| `latex_to_eqedit`: `\mathrm{H_2O}` 처럼 첨자가 든 곧은 글자 묶음을 곧은 글자의 수식으로 바꾼다(6.x 는 `H _ 2 O` 글자 그대로). `\text{...}` 안의 `^`·`_` 는 거부한다(`UnsupportedLatexError`) | `\text{}` 안의 첨자는 `\text{}` 밖으로 꺼내 쓴다 |
| `add_heading` 뒤에 `add_paragraph` 로 더한 본문이 제목의 문단 모양·스타일(개요)을 물려받지 않는다. 6.x 에서는 한/글이 그 본문에 다음 개요 번호("나." …)를 붙였다 | `doc.add_paragraph(text, inherit_style=True)` |
| 정렬을 준 머리말·꼬리말·쪽 번호(`set_header`/`set_footer` 의 `align`, `set_page_number`)가 본문 문단의 테두리·간격을 물려받지 않는다 | 없음(6.x 결과는 쪽 번호 밑에 줄이 그어지던 오류다) |

## Markdown 가져오기 — `from_markdown`·`append_markdown` (이제 python-hwpx-automation)

아래 동작 변화는 [옮겨 간](#옮겨-간-기능) `hwpx_automation.markdown` 의 함수에 그대로 있다.

| 무엇이 달라지나 | 옛 동작을 유지하는 법 |
|---|---|
| `from_markdown(text)` 이 모양을 주지 않으면 보고서 모양(색 띠 제목 상자, `Ⅰ` 번호 상자, 줄 표, 쪽 번호, 휴먼명조·HY헤드라인M)으로 만든다. 6.12.0 은 꾸미지 않은 모양이었다. `append_markdown(doc, ...)`(6.x `doc.text.append_markdown`) 의 기본은 그대로다 | `from_markdown(text, style="plain")` (또는 `style=MarkdownStyle()`) |
| 표의 열 너비를 내용에 맞추고, 머리 행을 가운데로 놓고, 구분선의 `:---`·`:---:`·`---:` 를 열 정렬로 읽는다 | `MarkdownStyle(table_fit_columns=False, table_header_align=None)` |
| 목록 안의 목록을 깊이마다 오른쪽으로 들여 쓴다 | `MarkdownStyle(list_indent_mm=0)` |

```python
from hwpx_automation.markdown import MarkdownStyle, from_markdown   # 6.x hwpx.tools.markdown_import

doc = from_markdown("# 제목\n\n- 항목\n  - 하위 항목\n", style="plain")   # 6.12 모양
old_tables = MarkdownStyle(table_fit_columns=False, table_header_align=None, list_indent_mm=0)
```

## 읽기 — Markdown 내보내기와 ingest (이제 python-hwpx-automation)

아래 동작 변화는 [옮겨 간](#옮겨-간-기능) `hwpx_automation.markdown`·`hwpx_automation.ingest` 에 그대로 있다.

| 무엇이 달라지나 | 옛 동작을 유지하는 법 |
|---|---|
| ingest(6.x `hwpx.ingest`, LangChain·LlamaIndex 어댑터 포함)의 Markdown 에 머리말·꼬리말·메모·수식(`$LaTeX$`)이 실린다. 6.x 는 이것들을 빼고 `metadata["left_out"]`·`warnings` 에 보고만 했다 | `convert(path, markdown_options={"headers_and_footers": False, "memos": False, "equations": False})` |
| 그림을 꺼내지 않을 때(`image_dir` 없이) 그림 캡션이 `*캡션*` 으로 나간다. 6.x 는 캡션까지 뺐다 | 없음 |

`to_markdown(doc, rich=True)`(6.x `doc.text.markdown(rich=True)`) 의 기본 결과는 그대로다. 새 옵션
`headers_and_footers=`·`memos=`·`equations=` 은 기본이 꺼짐이다.

## 양식 채우기와 바꾸기

| 무엇이 달라지나 | 옛 동작을 유지하는 법 |
|---|---|
| 표 이름표를 공백을 무시하고 견준다(`fill_by_path`·`find_cell_by_label`, 이제 `hwpx_automation.forms`). `"성명"` 으로 `"성  명"` 칸을 찾는다. 대신 공백만 다른 이름표 둘이 한 문서에 있으면 이제 `"ambiguous label"` 이다 | 몇 번째 이름표인지 적는다: `"성명[2] > right"`(실패 결과의 `candidates` 가 고르는 표기를 알려 준다) |
| `fill_by_path` 가 호출을 시작할 때의 문서로 모든 경로의 이름표를 먼저 정한다. 한 경로가 써 넣은 값이 다른 경로의 이름표로 잡히지 않고, 결과가 경로 순서에 달라지지 않는다 | 없음(앞 값이 뒤 이름표가 되던 동작에 기대던 코드는 호출을 나눈다) |
| `doc.text.replace` 가 기본 범위(본문 문단의 런 하나 안)에서 0건인데 찾는 글이 표 칸·글상자·머리말이나 서식이 다른 런에 걸쳐 있으면 `ReplaceScopeWarning`(`hwpx.errors`)을 낸다. 돌려주는 횟수와 문서는 같다 | 경고만 끄려면 `warnings.filterwarnings("ignore", category=ReplaceScopeWarning)`. 문서 전체를 바꾸려면 `everywhere=True` |

## `.hwp` 와 열기

| 무엇이 달라지나 | 옛 동작을 유지하는 법 |
|---|---|
| `.hwp` 로 쓰기가 실험 기능이 되었다. `.hwp` 에서 연 문서를 그 원본 경로에 `.hwp` 로 저장하면 `Hwp5Error`(`hwp5-overwrite-source`), 열 때 옮기지 못한 내용이 있는 문서를 `.hwp` 로 쓰면 `Hwp5Error`(`hwp5-write-lossy-source`) 로 거부한다 | `.hwpx` 로 저장한다(두 경우 모두 `.hwpx` 로는 저장된다). 다른 경로의 `.hwp` 로 쓰는 것은 그대로 된다 |
| `META-INF/container.xml` 이 가리키는 미리보기(`Preview/PrvText.txt` 등)가 없는 문서를 열고 저장한다. 6.x 는 `HwpxStructureError` 로 거부했다 | 없음 |
| HWP 3.x 이하 `.hwp` 를 열면 "File is not a zip file" 대신 지원하지 않는 형식이라고 알린다. 오류 형(`HwpxArchiveError`)은 같다 | 오류 문구를 비교하던 코드는 형이나 `code` 로 비교한다 |

## 조정자가 채울 자리

아래 절은 7.0 배포 전에 함께 들어가는 수정이 정해지면 채운다.

### 옛 이름 제거

### 수식 변환 수정

### Markdown 제목 판정

### Markdown 이스케이프

## 되돌리기

`pip install "python-hwpx<7"`. 6.x 라인은 그대로 있다.
