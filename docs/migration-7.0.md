# python-hwpx 7.0 이주 가이드

7.0 은 python-hwpx 를 "파일에 적힌 대로 읽고 쓰는" 한/글 문서의 기본 엔진으로 정리한 판이다. 6.12.0 에서 7.0.0 으로
올리면 네 가지가 달라진다.

1. **저장** 은 `doc.save(target)` 하나다 — [저장](#저장).
2. **변환·짐작 기능**(Markdown·HTML, ingest, 이름표로 칸 찾기, 메일 머지, 미리보기 …)은 python-hwpx-automation 으로
   옮겼다 — [옮겨 간 기능](#옮겨-간-기능).
3. **공개 이름** 을 한 가지 규칙으로 맞추고 얼렸다 — [이름 규칙과 바뀐 이름](#이름-규칙과-바뀐-이름).
4. 몇몇 호출의 **결과** 가 달라진다 — 아래 표들의 "옛 동작을 유지하는 법".

지운 이름·인자를 부르면 대부분 새 자리와 한 줄 예를 알려 주는 오류가 난다. 테스트를 한 번 돌려 오류가 가리키는 대로
고치고, 오류 없이 결과만 달라지는 것은 아래 표로 확인한다. 가장 먼저 바로 아래 `new()` 의 첫 줄을 본다.

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

## 저장

저장 동사 넷을 `doc.save(target, *, format=None, mode="auto", fallback="error", quality=None, pipeline=None)` 하나로 모았다.
`target` 은 경로(str·PathLike)나 쓰기 가능한 이진 스트림이다. `save()` 는 늘 `MutationReport` 를 돌려준다.
바이트가 필요하면 `doc.to_bytes()` 다(그대로).

| python-hwpx 6.x | python-hwpx 7.0 |
|---|---|
| `doc.save_to_path(path)`, `doc.save_to_path(path, return_report=True)` | `doc.save(path)`. 저장한 경로는 `report.path` |
| `doc.save_to_stream(stream)`, `doc.save_to_stream(stream, format="hwp")` | `doc.save(stream)`, `doc.save(stream, format="hwp")`. `format=None` 이면 `.hwp` 경로만 HWP 5.0 으로 쓴다 |
| `doc.save_report(target, quality=q)` | `doc.save(target, quality=q)` 의 `report.quality`. 게이트 실패는 `SaveError`(`quality-gate-failed`)의 `.report`. `before=`·`edit_mask=`·`ledger=` 는 `SavePipeline().run(...)` |
| `HwpxDocument.from_package(pkg)` | `HwpxDocument.open(pkg)` |
| 저장 뒤 열기 안전 검사를 다시 돌리던 코드 | `report.editor_open_safety` — 저장이 쓴 바이트에 대해 이미 낸 보고 |
| 렌더러를 쓰려고 `doc._save_pipeline = SavePipeline(oracle_factory=f)` 를 넣던 코드(비공개 속성) | `doc.save(target, quality=q, pipeline=SavePipeline(oracle_factory=f))`. 7.0 에는 그 속성이 없어 넣어도 쓰이지 않는다. 렌더러는 `q` 가 렌더링할 때만 만들어진다 |

옛 이름을 부르면 `HwpxAttributeError`(`document-name-removed`)가 위 표의 새 호출을 알려 준다.
`doc.save(path, mode="fast")` 처럼 없는 `mode`·`fallback` 은 거부하고, `.hwpx`·`.hwp` 가 아닌 이름은 경고한다.

```python
import io

from hwpx import HwpxDocument

doc = HwpxDocument.new()
doc.add_paragraph("2026 운영계획")
report = doc.save("plan-out.hwpx")                 # 6.x doc.save_to_path("plan-out.hwpx")
print(report.path, [part.path for part in report.changed_parts])

buffer = io.BytesIO()
doc.save(buffer)                                    # 6.x doc.save_to_stream(buffer)
same = HwpxDocument.open(doc.to_bytes())            # 6.x 의 from_package 도 open 으로
```

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

엔진에 남는 것: 평문(`doc.text.plain()`)·`outline`·`paragraphs`·`blocks`, 표 지도
(`doc.tables.map()`), 수식 변환(`latex_to_eqedit`·`eqedit_to_latex`)과 측정, 한/글의 메일 머지
**필드**(`paragraph.add_mail_merge_field`), 문서 합치기, 차례, 문서 비교(`doc_diff`), 변경 추적, 칸 맞춤
(`hwpx.form_fit`), 줄 배치 캐시, 품질 게이트. 미리보기가 쓰는 `EQEDIT_MATHML_OPERATOR_COMMANDS` 는
`hwpx.equation` 에서 내보낸다.

달라지는 점:

- `to_markdown`·`to_html` 은 **문서** 를 받는다. 6.x `hwpx.tools.exporter.export_markdown`·`export_html` 은
  패키지 바이트도 받았다(`hwpx_automation` 은 바이트를 받지 않는다). 바이트는 `HwpxDocument.open(data)` 로 연 뒤 넘긴다.
- 본체의 `MarkdownStyle` 객체는 새 `from_markdown` 이 받지 않는다(클래스가 다르다).
  `hwpx_automation.markdown.MarkdownStyle` 을 쓴다.
- extra `xlsx`·`preview`·`langchain`·`llamaindex` 는 `pip install "python-hwpx[xlsx]"` 가 깨지지 않게 이름만
  남고 아무것도 설치하지 않는다(5.0 의 `visual` 과 같다). 그 의존성은 python-hwpx-automation 의 같은 이름
  extra 가 끈다.
- 오류 code `ingest-failed`·`ingest-format-unsupported`·`equation-mathml-unavailable`·`text-markdown-style-invalid`·
  `table-path-invalid-type` 는 그 기능과 함께 옮겨 갔다(자동화 패키지가 같은 code 로 내고, 예외는 모두 `hwpx.errors.HwpxError` 계열이다).
- `except hwpx.ingest.DocumentIngestError` 처럼 옛 모듈의 예외를 잡던 코드는 `hwpx_automation.ingest` 의 같은 이름으로 바꾼다.

## 이름 규칙과 바뀐 이름

7.0 이 마지막 이름 변경이다. 7.0 의 공개 이름(최상위 `hwpx.__all__`, 루트 `HwpxDocument`, 묶음 `doc.styles`·`doc.page` …,
`hwpx.model` 의 계약 멤버, `hwpx.objects` 값 형식, 안정 모듈 이름)은 8.0 전에는 지우거나 바꾸지 않는다.
저장소의 `tests/data/public_surface.json` 이 그 목록이다.

### 규칙

새 이름은 다음 규칙을 따른다. 처음 보는 이름도 이 규칙으로 짐작할 수 있다.

- **값 하나는 속성으로 읽고 쓴다**: `paragraph.alignment = "CENTER"`, `run.size = 14`, `cell.vertical_alignment = "CENTER"`,
  `obj.rotation = 90`. 여러 값을 한 번에 바꾸는 것만 `set_…(...)` 메서드다(`set_position`, `set_borders`, `set_format`).
- **인자 없는 읽기는 속성, 인자를 받는 읽기는 메서드** 다. `get_` 을 붙이지 않는다(`table.cell_map`, `properties.header()`).
  묶음의 읽기가 `section=` 때문에 메서드여도, 모델 객체에서는 같은 값을 속성으로 읽는다
  (`doc.page.headers(section=0)` ↔ `section.properties.headers`).
- **여러 개를 돌려주는 읽기는 `tuple`** 이다. 문서 전체를 차례로 훑는 것은 Iterator 를 돌려주는 메서드다.
- **줄임말과 XML 이름을 쓰지 않는다**: `vertical_alignment`, `horizontal_relative_to`, `full_size`, `item_id`.
- **단위는 이름에 붙인다**: 접미사가 없으면 HWPUNIT(int), `_mm` 은 mm, `_pt` 는 pt. 글자 크기 `size`·`font_size` 는 pt.
  선 굵기는 어디서나 `…_width_mm`(mm, float)이다.
- **인자 이름**: 문단은 `paragraph=`(하나)·`paragraphs=`(여럿)이고 번호와 문단 객체를 모두 받는다. 구역은 `section=`,
  몇 번째는 `index=`, 표 좌표는 `row`·`col`, 머리(`header.xml`) 정의를 가리키는 것은 `…_id_ref`.
- **`add_<종류>` 는 그 종류를 읽을 때와 같은 객체를 돌려준다**(`add_hyperlink` → `Hyperlink`). 문단을 담는 모든 그릇
  (문서·구역·표 칸·각주·머리말·바탕쪽)의 `add_paragraph` 는 `text` 와 `style=`·`para_pr_id_ref=`·`char_pr_id_ref=` 를 같은
  이름으로 받고, 정렬 같은 것은 돌려받은 문단의 속성으로 쓴다.
- **같은 이름은 어디서나 같은 값** 이다. `alignment` 는 문단·표·그림 어디서나 `Alignment` 값으로 읽고 문자열로 쓴다.
  뜻이 다른 것은 이름을 나눈다(문단의 `page_break` 는 쪽 나눔, 표의 `page_split` 은 쪽 경계에서 나누는 방식).
- **한 가지 일은 한 곳에서** 한다(변경 추적은 `doc.tracking`, 서식 정의는 `doc.styles`).
- **실패는 `hwpx.errors.HwpxError` 계열** 이고 `code`·`suggestion` 을 싣는다. 대신하는 내장 예외(`TypeError` 등)도 함께 상속한다.

### 안내 오류

6.x 에 나간 이름을 7.0 에서 바꾸거나 지웠으면 새 자리를 알려 주는 오류가 난다. 7.0 개발 중에만 있던 이름은 안내 없이 바뀌었다.

| 부른 것 | 오류 |
|---|---|
| 없어진 메서드·속성(`doc.save_to_path`, `table.get_cell_map` …) | `HwpxAttributeError`(`AttributeError`), `code="document-name-removed"`, `context` 에 `replacement`. `hasattr` 는 `False` |
| 없어지거나 바뀐 인자(`row_index=`, `section_index=`, `pageBreak="1"` …) | `HwpxTypeError`(`TypeError`), `code="hwpx-argument-removed"` |
| 최상위에서 빠진 이름(`from hwpx import latex_to_eqedit` 등) | `ImportError` 계열, 메시지에 새 `import` 한 줄 |
| 옮긴 기능 | [옮겨 간 기능](#옮겨-간-기능) |

오류가 나지 않는 것 — 반환 형식만 바뀐 것과, 같은 이름이 메서드에서 속성이 된 것 — 은 아래
[반환 형식](#반환-형식만-바뀐-것) 표에 있다.

### 루트와 가져오기

| python-hwpx 6.x | python-hwpx 7.0 |
|---|---|
| 6.0 이 묶음으로 옮기고 경고와 함께 남겨 둔 루트 이름 79개(`doc.set_header_text(...)`, `doc.add_footnote(...)` …) | 묶음의 새 자리(`doc.page.set_header(text=...)`, `doc.notes.add_footnote(...)` …). 오류 문구가 7.0 의 자리를 알려 준다. 6.0 의 대응표는 [6.0 이주 가이드](migration-6.0.md) |
| `section_index=` | `section=`(번호·구역 객체) |
| `style_id_ref=` | `style=`(이름·번호·`Style`). 스타일의 문단·글자 모양까지 적용한다. 스타일 번호만 붙이려면 `paragraph.style_id_ref = 2` |
| `doc.add_paragraph(..., pageBreak="1")` 같은 XML 속성 키워드, `run_attributes=`(`add_paragraph`·`add_heading`·`add_table`·`add_picture`) | 돌려받은 객체의 속성: `p = doc.add_paragraph(...)`; `p.page_break = True` |
| `doc.add_picture(..., align=, line_width=33)` → `InlineObject` | `doc.add_picture(..., alignment=, line_width_mm=0.12)` → `Picture` |
| `from hwpx import <실험 기능>`(26개) | `from hwpx.experimental import ...` |
| `from hwpx import latex_to_eqedit`(·`estimate_equation_size`·`UnsupportedLatexError`), `hwpx.experimental` 의 같은 이름 | `from hwpx.equation import ...`(7.0 에서 안정 계약) |

### 문단·런·서식

| python-hwpx 6.x | python-hwpx 7.0 |
|---|---|
| `paragraph.add_new_num(...)` | `paragraph.add_number_restart(...)` → `NumberRestart` |
| `paragraph.add_tracked_insert(...)`·`add_tracked_delete(...)` | `doc.tracking.insert(paragraph, text)`·`doc.tracking.delete(paragraph, match=...)` |
| `paragraph.add_picture(binary_item_id_ref, align=, line_width=33)` | `paragraph.add_picture(item_id, alignment=, line_width_mm=0.12)` |
| `paragraph.add_line`·`add_rectangle`·`add_ellipse`·`add_arc`·`add_polygon`·`add_curve`·`add_connector` 의 `line_width='33'` | `line_width_mm=0.12` |
| `paragraph.add_equation(script, base_unit=1100, size=(w, h))` | `paragraph.add_equation(script, font_size=11.0, width=w, height=h)` |
| `paragraph.add_chart(..., size=(w, h))` | `add_chart(..., width=w, height=h)` |
| `RunStyle.is_superscript()`·`is_subscript()`·`is_emboss()`·`is_engrave()` | 속성 `superscript`·`subscript`·`emboss`·`engrave` |
| `RunStyle.text_color()` | `RunStyle.color` |
| `Font.binary_item_id_ref`, `FontSubstitution.binary_item_id_ref` | `item_id` |
| `ParagraphProperty.align` | `ParagraphProperty.alignment` |

### 개체·수식

| python-hwpx 6.x | python-hwpx 7.0 |
|---|---|
| `obj.get_attribute(name)` | `obj.attributes.get(name)` |
| `shape.set_position(horz_rel_to=, vert_rel_to=, horz_align=, vert_align=)` | `horizontal_relative_to=`, `vertical_relative_to=`, `horizontal_alignment=`, `vertical_alignment=`(그림·수식·표도 같은 이름) |
| `shape.set_draw_text(vert_align=)` | `vertical_alignment=`(표 칸과 같은 이름) |
| `obj.set_caption(full_sz=)`, `caption.full_sz` | `full_size` |
| `estimate_equation_size(script, base_unit=1100)` | `estimate_equation_size(script, font_size=11.0)` |

### 표

| python-hwpx 6.x | python-hwpx 7.0 |
|---|---|
| `table.cell(row_index=, col_index=)`, `set_cell_text`·`set_cell_shading`·`set_cell_borders`·`set_cell_border_fill`·`set_cell_fill_gradient`·`set_cell_fill_image`·`split_merged_cell` 의 같은 인자 | `row=`, `col=`(위치 인자로 부르면 그대로) |
| `table.get_cell_map()` | 속성 `table.cell_map`(tuple 의 tuple) |
| `table.insert_rows(..., blank=True)`·`insert_columns(..., blank=True)`(`doc.tables.` 도) | `blank=` 를 지운다 — 빈 칸이 기본이다([아래](#표에-넣는-행과-열은-빈-칸이다)) |
| `table.insert_rows(..., blank=False)`·`insert_columns(..., blank=False)` | `copy_content=True` |

### 구역·머리말·바탕쪽·각주

| python-hwpx 6.x | python-hwpx 7.0 |
|---|---|
| 모델 `Document`·`Section` 의 `add_paragraph(run_attributes=, inherit_outline=, <XML 속성>=)` | 없어졌다. 돌려받은 문단의 속성으로 쓴다 |
| `header.add_paragraph(text, align="CENTER")` | `p = header.add_paragraph(text)`; `p.alignment = "CENTER"`. 머리말·바탕쪽·각주의 `add_paragraph` 가 `style=`·`para_pr_id_ref=`·`char_pr_id_ref=` 를 받는다 |
| `header.apply_page_type` | `header.page_type`(읽고 쓰기) |
| `properties.get_header()`·`get_footer()` | `properties.header()`·`footer()` |
| `properties.start_numbering`·`set_start_numbering(...)` | `properties.start_numbers`·`set_start_numbers(...)` → `hwpx.objects.StartNumbers`(`hwpx.oxml.SectionStartNumbering` 은 없어졌다) |
| `properties.add_master_page_reference(id_ref=)` | `add_master_page_reference(master_page_id=)`. `MasterPage` 도 받는다 |
| `properties.remove_master_page_reference(id_ref)` | `remove_master_page_reference(master_page_id)`. `MasterPage` 도 받는다 |

### 반환 형식만 바뀐 것

오류가 나지 않으므로 결과를 쓰는 곳을 직접 본다.

| python-hwpx 6.x | python-hwpx 7.0 | 고칠 것 |
|---|---|---|
| 여러 개를 돌려주는 읽기가 `list` | `tuple`: `doc.paragraphs`·`doc.sections`, `doc.oxml.sections`·`headers`·`master_pages`·`histories`, `doc.parts.headers`·`master_pages`·`histories`, `section.paragraphs`·`memos`, `paragraph.runs`·`tables`·`shapes`·`footnotes`·`endnotes`, `table.rows`, `row.cells`, `cell.paragraphs`·`tables`, `properties.headers`·`footers`, `memo.paragraphs` 등 | 목록을 고치던 코드(`append`, `sort`)는 `list(...)` 로 |
| `paragraph.bookmarks` → 이름의 `list` | `Bookmark` 의 tuple | 이름은 `[b.name for b in paragraph.bookmarks]` |
| `paragraph.hyperlinks` → dict 처럼 읽히는 값 | `Hyperlink` 의 tuple | `link["url"]` 대신 `link.url`·`link.to_dict()` |
| `paragraph.add_bookmark`·`add_hyperlink`·`add_form_field`·`add_check_box`·`add_highlight`·`add_page_hiding` → `InlineObject` 또는 `None` | `Bookmark`·`Hyperlink`·`FormField`·`CheckBox`·`Highlight`·`PageHiding` | XML 요소는 `.element` |
| 머리말·꼬리말의 `add_paragraph`·`add_run`·`add_page_number_field` → XML 요소 | 문단·런·개체 객체 | 옛 요소는 `.element` |
| `note.add_hyperlink(...)` | `Hyperlink` | |
| `HeaderPart.border_fill(id)`·`border_fills` → XML 요소 | `BorderFillInfo` | |
| `RunStyle.underline_type()`·`underline_color()`·`outline_type()`, `run.content_kinds()` | 같은 이름의 속성 | 괄호를 뗀다(부르면 `TypeError`) |
| `note.text` → 문단 글을 붙여서 | 문단 글을 줄 바꿈(`"\n"`)으로 잇는다 | |
| `doc.oxml` 의 서식 읽기 16개(`char_property`·`styles` 등)가 공개 계약 | 계약에서 내렸다(메서드는 남는다) | `doc.styles` 의 같은 이름을 쓴다 |
| `doc.styles.names()`, `doc.text.highlights()` | 속성 `doc.styles.names`(tuple)·`doc.text.highlights` | 괄호를 뗀다 |
| `doc.styles.border_fill(id)`·`border_fills`, `numbering(id)`·`numberings` → XML 요소 | `BorderFillInfo`·`NumberingInfo` | XML 요소는 `doc.oxml.border_fill(id)` |
| `doc.tracking.changes` → id 를 키로 한 `TrackChange` dict, `change(id)` → `TrackChange` | 문서 순서의 `TrackedChange` tuple, `TrackedChange`(`change_id`·`kind`·`author`·`date`·`paragraph`) | `changes[id]` 는 `doc.tracking.change(id)` 로 |
| `doc.tables.all`·`doc.tables[a:b]`, `doc.text.find_runs()`, `doc.notes.memos`, `doc.styles.ensure_numbering()`, `doc.parts.clear_document_metadata()`·`clear_preview()` → `list` | `tuple` | 목록을 고치던 코드는 `list(...)` 로 |
| `doc.refs.add_bookmark()`·`add_hyperlink()` → `InlineObject` | `Bookmark`·`Hyperlink` | XML 요소는 `.element` |

### 묶음(`doc.*`)과 값 형식

| python-hwpx 6.x | python-hwpx 7.0 |
|---|---|
| `doc.text.runs()`·`blocks()` | `doc.text.iter_runs()`·`iter_blocks()`(문서 전체를 차례로 훑는 것은 `iter_`). 7.0 개발 중의 `paragraphs()`·`objects()` 도 `iter_paragraphs()`·`iter_objects()` |
| `doc.shapes.add_line`·`add_rectangle`·`add_ellipse`·`add_arc`·`add_polygon`·`add_curve`·`add_connector` 의 `line_width='33'` | `line_width_mm=0.12`(0 은 선 없음) |
| `doc.styles.ensure_border_fill(border_width='0.12 mm', base_border_fill_id=)` | `ensure_border_fill(border_width_mm=0.12, base_border_fill_id_ref=)`. 한/글 굵기 목록에 있는 값만 받는다(아래 "결과가 달라지는 것") |
| `doc.styles.apply_paragraph_format(paragraph_index=, paragraph_indexes=, line_spacing_percent=, border_width='0.12 mm')` | `apply_paragraph_format(paragraph=, paragraphs=, line_spacing=, border_width_mm=0.12)`. `paragraph=`·`paragraphs=` 는 번호와 문단 객체를 모두 받는다 |
| `doc.styles.apply_list_format(paragraph_index=, paragraph_indexes=)` | `apply_list_format(paragraph=, paragraphs=)` |
| `doc.styles.ensure_paragraph_format(base_para_pr_id=, line_spacing_percent=)` | `ensure_paragraph_format(base_para_pr_id_ref=, line_spacing=)` |
| `doc.styles.ensure_run(base_char_pr_id=)` | `ensure_run(base_char_pr_id_ref=)` |
| `doc.styles.ensure_font(binary_item_id_ref=, subst_binary_item_id_ref=)` | `ensure_font(item_id=, subst_item_id=)` |
| `doc.styles.border_fill_info(id)` | `doc.styles.border_fill(id)`(→ `BorderFillInfo`). 7.0 개발 중의 `numbering_info(id)` 는 `numbering(id)` |
| `doc.page.restart_page_number(p, ...)`·`hide_page_elements(p, ...)` | `doc.page.add_number_restart(p, ...)`(→ `NumberRestart`)·`add_page_hiding(p, ...)`(→ `PageHiding`) |
| `doc.page.set_page_number(align=)` | `set_page_number(alignment=)` |
| `doc.page.set_columns(separator_width='0.12 mm')` | `set_columns(separator_width_mm=0.12)` |
| 7.0 개발 중의 `doc.page.remove_master_page(id)`(구역과의 연결 끊기) | `doc.page.remove_master_page_reference(id)`. 바탕쪽 파트를 지우는 것은 `doc.parts.remove_master_page(id)` |
| `doc.parts.add_master_page(..., paragraphs=[...])` → id 문자열 | `mp = doc.parts.add_master_page(...)` → `MasterPage`(id 는 `mp.id`), 글은 `mp.add_paragraph("...")`. `doc.page.set_master_page`·`doc.parts.remove_master_page` 는 `MasterPage` 도 받는다 |
| `doc.parts.set_compatible_document_target_program(...)`·`set_layout_compatibility_flags(...)`·`set_doc_option_link_info(path=, page_inherit=, footnote_inherit=)`·`set_license_mark(mark_type=, flag=, lang=)` | `doc.parts.set_document_options(target_program=, layout_compatibility=, link_path=, page_inherit=, footnote_inherit=, license_type=, license_flag=, license_lang=)` → 읽기 `doc.parts.document_options` 와 같은 `DocumentOptions`. 준 것만 바꾼다 |
| `doc.parts.set_paragraph_auto_spacing(para_pr_id=)` | `para_pr_id_ref=`(위치 인자로 부르면 그대로) |
| `doc.shapes.add_dutmal(main_text, sub_text, pos_type=, align=, sz_ratio=)` → `InlineObject` | `doc.shapes.add_ruby(text, ruby_text, position=, alignment=, size_ratio=)` → `Ruby` |
| `doc.shapes.add_composed_character(compose_text, circle_type=, char_sz=, compose_type=)` → `InlineObject` | `add_composed_character(text, frame=, inner_size=, arrangement=)` → `ComposedCharacter` |
| `doc.shapes.add_drop_cap(style=)` | `kind=`(`style=` 은 어디서나 문단 스타일) |
| `doc.shapes.add_equation(script, base_unit=1100, size=(w, h))` | `add_equation(script, font_size=11.0, width=w, height=h)` |
| `doc.shapes.add_chart(..., size=(w, h))` | `add_chart(..., width=w, height=h)` |
| `doc.media.replace_picture(picture_index=, binary_item_id_ref=)` | `replace_picture(index=, old_item_id=)` |
| `doc.media.picture_references()` → `PictureRef` | `doc.media.pictures`(`Picture`: `item_id`·`width`·`height`, 몇 번째는 tuple 순서) |
| `doc.notes.add_footnote(text, p)`·`add_endnote(text, p)` | `add_footnote(text, paragraph=p)`·`add_endnote(text, paragraph=p)` |
| `doc.notes.add_memo(anchor=p, anchor_char_pr_id_ref=)` | `add_memo(paragraph=p, paragraph_char_pr_id_ref=)` |
| `doc.fields.fill(value, field_index=, fit_policy=)` | `fill(value, index=, fit=)` |
| `doc.tracking.add_change(change_type, author_name=)` | `add_change(change_type, author=)` |

값 형식(`hwpx.objects`)과 그 안의 매핑:

| python-hwpx 6.x | python-hwpx 7.0 |
|---|---|
| `check_box.section_index`(구역 번호) | `check_box.section`(구역 객체). 번호는 `doc.sections.index(check_box.section)` |
| `from hwpx.objects import PictureRef`, `PictureRef.picture_index`·`section_index`·`binary_item_id_ref`·`width`·`height` | 없어졌다: `doc.media.pictures` 의 `Picture`(`item_id`·`width`·`height`, 몇 번째는 tuple 순서) |
| `ensure_border_fill(sides={"top": {"width": "0.4 mm"}})`, `apply_paragraph_format(border={"width": "0.4 mm"})` | `"width_mm": 0.4`(mm 수, 한/글 굵기 목록의 값). 옛 키는 `style-border-side-invalid`·`paragraph-border-invalid` 로 거부하며 문장이 `width_mm` 을 알려 준다 |
| `ContainerMember.rect`·`ellipse`·`polygon`·`line`·`text_box` 의 `line_width="33"`, `text_box(vert_align=)` | `line_width_mm=0.12`, `vertical_alignment=`(도형·`set_draw_text` 와 같은 이름) |
| `doc.styles.bullet(id).para_head.align`(문자열) | `.para_head.alignment`(`Alignment`) |
| `doc.styles.ensure_memo_shape(line_width=1)`(XML `lineWidth` 를 그대로 적음, 모델 `ensure_memo_shape` 도) | `ensure_memo_shape(line_width_mm=0.12)`. `lineWidth` 는 한/글 굵기 목록의 순번이고(0.12 mm → 1, 0.2 mm → 3) 목록의 값만 받는다. `memo_shape(id).line_width_mm` 은 순번이 아닌 값(`"0.6mm"`)을 한/글처럼 0.1 mm 로 읽는다 |
| `doc.page.text_direction(section=s)` → `SectionTextDirection(direction, vertical_header_footer)` | `doc.page.text_direction(section=s)` → `"HORIZONTAL"`·`"VERTICAL"`·`"VERTICALALL"`(표 칸의 `cell.text_direction` 과 같은 말), 머리말·꼬리말 세로쓰기는 `doc.page.vertical_header_footer(section=s)`. 쓰기 `set_text_direction(...)` 은 그대로. 반환 모양이 바뀐 것이라 안내 오류는 없다(`.direction` 을 부르면 `AttributeError`) |

7.0 개발 중에 생긴 값 형식의 이름(안내 없이 바꿈):

| 7.0 개발 중 | python-hwpx 7.0 |
|---|---|
| `RadioButton`·`ComboBox`·`EditBox` 의 `section_index` | `section`(구역 객체) |
| `ParagraphPlace`·`ObjectPlace`(`doc.text.iter_paragraphs()`·`iter_objects()`)·`TextMatch`(`doc.text.find()`) 의 `section`(번호) | 구역 객체(바탕쪽이면 `None`). `to_dict()` 의 `"section"` 은 그대로 번호 |
| `ObjectPosition.horz_rel_to`·`vert_rel_to`·`horz_align`·`vert_align`(`obj.position`) | `horizontal_relative_to`·`vertical_relative_to`·`horizontal_alignment`·`vertical_alignment`(`set_position` 의 인자와 같은 이름. `to_dict()` 열쇠도 `horizontalRelativeTo` …) |
| `NumberingLevel.align`(문자열, `doc.styles.numbering(id).levels`) | `alignment`(`Alignment`. `to_dict()` 열쇠도 `alignment`) |

새로 계약에 올린 것(이름은 그대로, 다음 major 까지 고정): stable 이름이 돌려주던 형식 26개를 `hwpx.objects` 에서도 가져올
수 있다 — `Style`·`RunStyle`·`ParagraphProperty`·`Bullet`·`Font`·`MemoShape`·`TabDefinition`·`TrackChange`·`TrackChangeAuthor`·
`SectionGrid`·`SectionVisibility`·`LineNumberShape`·`DocumentMetadata`·`TextBlock`·`TextOutline`·`TextChangeReport`·
`ValidationReport`·`Hwp5ConversionReport`·`TableMapResult`·`GridPosition`(`table.cell_map` 의 칸)·`Caption`·`PictureShadow`·
`PictureGlow`·`PictureReflection`·`ContainerMember`·`GenericElement`(구현 모듈의 같은 클래스다). `paragraph.section`(문단이 든
구역)도 계약이다. 그림·수식·도형·표도 `obj.section`(바탕쪽이면 `None`)으로 구역을 읽는다 — 6.x 에서 `obj.paragraph.section.element`
를 `doc.sections` 와 견주던 코드는 `doc.sections.index(obj.section)`. 번호 수준은 `NumberingLevel.use_instance_width`
(`useInstWidth`)까지 값으로 읽으므로 머리 XML(`hh:paraHead`)을 직접 읽을 필요가 없다.

### 가장 자주 고치는 곳

자동화·학교 도구 저장소에서 센 깨지는 호출 수(받는 쪽을 가리지 못한 수는 상한)가 많은 순서다. 대부분 이름만 바꾸면 된다.

| 6.x | 7.0 | 옮기는 법 |
|---|---|---|
| `doc.save_to_path(p)` | `doc.save(p)` | 이름만. 반환값(경로)을 쓰던 곳은 `report.path` |
| `doc.styles.paragraph_property(id).align` | `.alignment` | 이름만 |
| `apply_paragraph_format(paragraph_index=, line_spacing_percent=, border_width=)` | `paragraph=`, `line_spacing=`, `border_width_mm=` | 키워드 이름. `border_width_mm` 은 mm 수 |
| `doc.save_report(t, quality=q)` | `doc.save(t, quality=q).quality` | 게이트 실패는 반환 대신 `SaveError` |
| `table.get_cell_map()` | `table.cell_map` | 괄호를 뗀다 |
| `doc.add_picture(..., line_width=33, align=)`, `paragraph.add_picture(binary_item_id_ref, ...)` | `line_width_mm=0.12, alignment=`, `item_id` | 값도 mm 로 |
| `doc.add_paragraph(..., pageBreak="1")` | `p = doc.add_paragraph(...)`; `p.page_break = True` | 손으로 |
| `ensure_border_fill(border_width="0.4 mm", sides={...: {"width": "0.4 mm"}})` | `border_width_mm=0.4`, `{"width_mm": 0.4}` | 값도 mm 수로 |
| `ensure_run(base_char_pr_id=)` | `base_char_pr_id_ref=` | 이름만 |
| `RunStyle.text_color()` | `RunStyle.color` | 속성 |
| `doc.notes.add_memo(anchor=p)` | `paragraph=p` | 이름만 |
| `doc.media.picture_references()`, `PictureRef` | `doc.media.pictures`(`Picture`) | 필드: `binary_item_id_ref` → `item_id`, 번호는 순서 |
| `from hwpx.experimental import latex_to_eqedit` | `from hwpx.equation import latex_to_eqedit` | 가져오는 자리만 |

```python
from hwpx import HwpxDocument
from hwpx.equation import latex_to_eqedit          # 6.x from hwpx import latex_to_eqedit

doc = HwpxDocument.new()
title = doc.add_paragraph("2026 운영계획")
title.alignment = "CENTER"                          # 6.x add_paragraph(..., run_attributes=/XML 속성)
table = doc.add_table(2, 2)
cell = table.cell(row=0, col=1)                     # 6.x cell(row_index=0, col_index=1)
cell.vertical_alignment = "CENTER"
grid = table.cell_map                               # 6.x table.get_cell_map()
rows = list(table.rows)                             # tuple → 고칠 목록이 필요하면 list(...)
equation = title.add_equation(latex_to_eqedit(r"\frac{a}{b}"), font_size=11.0)  # 6.x base_unit=1100
```

## 만들기·고치기 — 결과가 달라지는 것

| 무엇이 달라지나 | 옛 동작을 유지하는 법 |
|---|---|
| `add_equation` 이 적는 수식 글꼴이 `HYhwpEQ` 에서 `HancomEQN`(한/글 수식 편집기의 글꼴)으로 바뀌었다. 획이 조금 굵어지고 일부 글자 폭이 달라진다 | `doc.shapes.add_equation(script, font="HYhwpEQ")` |
| 수식 상자 폭을 한/글 2024(Windows)가 실제로 필요로 한 폭에 맞춰 다시 잡는다. 같은 수식의 `hp:sz` 폭이 6.x 와 다르다(맥 한/글이 저장한 상자보다 평균 10% 넓다) | 없음(6.x 폭은 수식 뒤 글자와 겹쳤다) |
| `add_heading` 뒤에 `add_paragraph` 로 더한 본문이 제목의 문단 모양·스타일(개요)을 물려받지 않는다. 6.x 에서는 한/글이 그 본문에 다음 개요 번호("나." …)를 붙였다 | `doc.add_paragraph(text, inherit_style=True)` |
| 정렬을 준 머리말·꼬리말·쪽 번호(`set_header`/`set_footer` 의 `align`, `set_page_number`)가 본문 문단의 테두리·간격을 물려받지 않는다 | 없음(6.x 결과는 쪽 번호 밑에 줄이 그어지던 오류다) |
| 머리말·꼬리말을 한/글처럼 첫 문단의 본문 컨트롤(`hp:ctrl`) 한 곳에만 쓴다. 6.x 는 `hp:secPr` 아래에 사본과 `headerApply` 를 하나 더 썼다(OWPML 스키마에 없는 모양, 공개 한/글 저장본 68개에는 없다). 6.x 로 만든 문서는 그 머리말을 다시 설정할 때 사본을 걷어 낸다 | 없음 |
| `doc.add_table(style=)`·`doc.add_picture(style=)` 가 스타일의 문단·글자 모양도 적용한다. 6.x 는 스타일 이름표만 붙였다 | 스타일의 모양을 원하지 않으면 `style=` 을 주지 않는다 |
| `obj.remove()`·`table.remove()` 가 다른 곳에서 쓰지 않게 된 그림 데이터(`BinData`)도 함께 지운다 | `obj.remove(remove_orphaned=False)` |
| 표 칸·글상자·각주·머리말 안에 떠 있게 만든 개체는 문단 기준으로 그 안에 머무르게 놓인다(한/글 저장본의 그 자리 개체들이 쓰는 배치). 본문에 만드는 개체는 그대로다 | 없음(6.x 배치는 한/글에서 표 밖에 그려졌다). 다른 배치는 `set_position(...)` 으로 준다 |
| 각주·미주를 더하거나 지우면 같은 종류의 번호를 문서 순서대로 다시 매긴다(쪽마다 새로 매기는 구역은 [아래](#쪽마다-새로-매기는-각주)) | 없음 |
| 칸에 색을 칠해도(`set_cell_shading`, `set_shading`) 그 칸의 선·대각선과 그림 배경이 남고, 그러데이션은 새 색으로 바뀐다. 그림을 넣으면 면 색이 남는다. 칸마다 제 테두리 정의에서 사본을 만들므로 `header.xml` 의 테두리 정의가 늘 수 있다 | 없음(6.x 는 같은 색의 다른 정의를 가져와 선이 바뀌거나 사라졌다) |
| 글자·문단 모양 변경 추적은 쓰지도 거절하지도 않는다(`track-format-change-unconfirmed`). 한/글 2024 가 다시 저장할 때 그 항목을 버리기 때문이다 | 없음(6.x 의 거절은 표시만 걷어 수락처럼 굴었다) |
| `doc.styles["바탕글"]` 처럼 이름·영문 이름·번호로 스타일을 찾는다. `"바탕글" in doc.styles` 도 `True` 다 | `KeyError` 에 기대던 코드는 `in` 으로 묻는다 |
| 크기가 0 인 수식·차트, 빈 책갈피 이름, 빈 링크 주소를 거부한다. `paragraph.style` 에 스타일이 아닌 값을 주면 `HwpxTypeError` 다 | 없음 |
| 공개 메서드에 잘못된 타입을 주면 `code`·`suggestion` 을 실은 `HwpxError` 계열이 난다(내장 `TypeError` 등도 상속). 문단·런의 글을 잘못 주면 옛 글을 지우기 전에 실패한다 | `except TypeError` 는 그대로 잡는다 |
| `doc.refs.cross_references` 의 항목이 살아 있는 `CrossReference` 다(값을 바꾸고 지울 수 있다). 같은지는 요소로 견준다 | 없음 |
| `paragraph.clear_layout_cache()` 가 늘 그 문단의 파트를 바뀐 것으로 표시한다. 고치지 않은 문단에 불러도 그 구역을 다시 쓴다(바이트가 읽은 것과 다를 수 있다) | 고치지 않았으면 부르지 않는다 |
| `doc.text.iter_paragraphs()`·`iter_objects()` 가 표 캡션 안의 문단과 표를 `where="caption"` 으로 내놓는다(6.x 는 본문·표 칸). `where="body"` 는 이제 `doc.paragraphs` 와 같다 | `where=("body", "caption")` |
| 다단 문서에서 새 표와 차트의 기본 폭이 본문 전체 폭이 아니라 단 폭이다 | `width=` 를 준다 |
| 구역이 여럿인 문서에서 `doc.page.*` 를 `section` 없이 부르면 마지막 구역만 바뀐다는 경고가 한 번 난다 | `section=` 을 준다. 모든 구역은 `section="all"` |
| 테두리·단 구분선·각주/미주 구분선·메모 선 굵기(`border_width_mm=`·`sides`/`border` 의 `width_mm`·`table.set_borders(border_width_mm=)`·`separator_width_mm=`·`ensure_memo_shape(line_width_mm=)`)는 한/글 굵기 목록(0.1·0.12·0.15·0.2·0.25·0.3·0.4·0.5·0.6·0.7·1·1.5·2·3·4·5 mm)의 값만 받는다. 목록에 없는 값(0.45 등)은 문서를 바꾸기 전에 `HwpxValueError`(`style-line-width-invalid`, `suggestion` 에 쓸 수 있는 값)로 거부한다. 6.x 와 7.0 개발 중에는 가장 가까운 값으로 바꿔 썼다. 도형·그림 선(`line_width_mm=`)은 그대로 mm × 283 HWPUNIT 이다 | 목록의 값을 직접 고른다(0.45 → 0.4 또는 0.5). 목록은 `hwpx.oxml.utils.LINE_WIDTHS_MM` 에 있다. 6.x 의 HWPUNIT 선 굵기 `n` 은 `hwpx.oxml.shape_position.line_width_mm_for_units(n)` 이 같은 HWPUNIT 으로 돌아가는 mm 다 |
| `obj.rotation = 각도` 가 글이 든 도형(글상자)과 묶음 전체도 돌린다(6.x·7.0 개발 중에는 `shape-rotation-unsupported`). 글은 돌지 않고 돈 도형을 감싸는 상자 폭에 가로로 다시 놓인다(한/글과 같다). 돌린 개체의 숫자는 한/글처럼 cos·sin 소수 여섯 자리로 계산하고 옮기는 양을 정수로 써서, 같은 각도라도 상자 크기·행렬 끝자리가 6.x 와 한 단위쯤 다를 수 있다. 늘인 묶음, 묶음 안 묶음, 이미 돈 묶음을 다른 각도로 돌리는 것도 된다. 각도는 0~359 밖도 받아 한/글처럼 바꿔 쓴다(-30 → 330, 6.x 는 `shape-rotation-value`). 묶음 구성원 하나, 뒤집은 개체·묶음은 여전히 거부한다 | 거부에 기대던 코드는 돌리기 전에 `shape.shape_type == "container"` 등을 직접 본다. 각도 범위 검사에 기대던 코드는 직접 검사한다 |
| `editable` 속성이 없는 누름틀의 `field.editable` 이 OWPML 스키마 기본값 `True` 다(6.x 는 `False`). 번호 수준(`NumberingLevel`)의 `autoIndent`·`textOffset` 이 없으면 `auto_indent`·`text_offset` 이 스키마 기본값 `True`·`50` 이다(6.x 는 `False`·`0`). 한/글은 이 속성들을 늘 적으므로 한/글 저장본은 전과 같다 | 없음. "적히지 않음"을 따로 보려면 `field.element.get("editable")` |
| **`table.insert_rows()`·`insert_columns()`(`doc.tables.` 도)가 한/글처럼 빈 행·열을 넣는다.** 6.x 는 기준 칸의 글·개체까지 복사했다. `blank=` 없이 부르던 코드는 오류 없이 결과가 바뀐다([아래](#표에-넣는-행과-열은-빈-칸이다)) | `copy_content=True` |

### 표에 넣는 행과 열은 빈 칸이다

6.x 의 `insert_rows` 는 기준 행을 통째로 복제했다. 제목 행 아래에 줄을 넣으면 제목 글이 새 줄에 그대로 생겼다.
7.0 은 한/글의 "줄 추가하기"와 같다: 새 칸은 기준 칸의 서식(칸 속성·테두리/배경·여백·크기·문단 모양·글자 모양)만 받고
빈 문단 하나를 둔다. 합친 칸이 새 줄을 가로지르면 늘어나는 규칙은 전과 같다. 이 변경은 이름이 그대로라 **오류가 나지
않는다** — `blank=` 없이 `insert_rows`·`insert_columns` 를 부르는 곳을 찾아 확인한다(`blank=` 를 주던 곳은 안내 오류가 난다).

```python
from hwpx import HwpxDocument

doc = HwpxDocument.new()
table = doc.add_table(rows=2, cols=2)
table.cell(0, 0).text = "제목"

table.insert_rows(0)                      # 7.0: 새 줄은 빈 칸 (6.x: "제목"이 복사됐다)
assert table.cell(1, 0).text == ""

table.insert_rows(0, copy_content=True)   # 6.x 의 insert_rows(0) 과 같다 (6.x: blank=False)
assert table.cell(1, 0).text == "제목"
```

바이트 편집 `apply_table_ops` 의 `insert_row_by_clone`·`insert_column_by_clone` 은 이름대로 전처럼 복사가 기본이다
(빈 칸은 `"blank": True`).

## 쪽마다 새로 매기는 각주

각주 번호 방식이 "쪽마다 새로"(`ON_PAGE`)인 구역이 하나라도 있으면, 엔진은 각주를 더하거나 지워도 이미 적힌 번호를
다시 쓰지 않고(다른 구역도), 새 각주에는 문서 전체에서의 순번을 적는다. 그 번호는 쪽 배치에 달려 있는데 엔진은 쪽을
배치하지 않기 때문이다. `note.number` 는 그 구역에서 파일에 적힌 값이다.

한/글 2024 는 문서를 열 때 쪽마다 번호를 다시 매겨 그리고, 저장할 때 쪽별 번호를 파일에 적는다(문서 순번 1..6 을 1,2,1,2,1,2 로
고쳐 적었다). 그래서 화면의 번호는 맞지만, 한/글로 다시 저장하기 전의 `note.number` 는 화면의 번호와 다를 수 있다.
쪽마다의 번호가 필요하면 한/글로 한 번 열어 저장한 파일을 읽는다.

## 수식 변환

`latex_to_eqedit`·`eqedit_to_latex` 의 결과가 달라지는 경우. 6.x 결과는 한/글에서 다른 기호로 그려지거나 깨졌다.

| 무엇이 달라지나 | 옛 동작을 유지하는 법 |
|---|---|
| `\mathrm{H_2O}` 처럼 첨자가 든 곧은 글자 묶음을 곧은 글자의 수식(`{rm H _{2} O it}`)으로 바꾼다(6.x 는 `H _ 2 O` 글자 그대로). `\mathrm{km/h}` 는 원문 띄어쓰기를 따른다 | 없음 |
| `\text{...}` 안의 `^`·`_` 를 거부한다(`UnsupportedLatexError`) | 첨자는 `\text{}` 밖으로 꺼내거나 `\mathrm{}` 을 쓴다 |
| `\frac{1}`, `\sqrt{}`, `x^^2` 처럼 틀린 LaTeX 를 거부한다(`UnsupportedLatexError`). 6.x 는 받아서 한/글에서 깨진 수식을 만들었다 | 없음 |
| net, initial, In 처럼 한/글 예약어로 시작하는 이름을 글자로 지킨다(`net` → `"net"`). 6.x 결과는 한/글이 F≠t 같은 다른 기호로 그렸다 | 없음 |
| `\text{ 또는 }` 의 앞뒤 공백을 지키고, 따옴표 글의 `%`·`_`·`}` 를 이스케이프한다 | 없음 |
| `eqedit_to_latex`: `root3` → `\sqrt{3}`, `a over b^2` → `\frac{a}{b^2}`, `rarrow`·`ANGLE`·`CDOT`·`INF`·`pile`, 붙여 쓴 `sinx` 같은 한/글 낱말을 LaTeX 로 바꾼다 | 없음 |
| 받는 표기가 늘었다(유니코드 기호, `\displaystyle`, `\Leftrightarrow`, `aligned` …). `\mathbb`·`\widehat`·`\square` 는 계속 거부하되 대신 쓸 표기를 알려 준다 | 없음 |

## Markdown 가져오기 — `from_markdown`·`append_markdown` (이제 python-hwpx-automation)

아래 동작 변화는 [옮겨 간](#옮겨-간-기능) `hwpx_automation.markdown` 의 함수에 그대로 있다.

| 무엇이 달라지나 | 옛 동작을 유지하는 법 |
|---|---|
| `from_markdown(text)` 이 모양을 주지 않으면 보고서 모양(색 띠 제목 상자, `Ⅰ` 번호 상자, 줄 표, 쪽 번호, 휴먼명조·HY헤드라인M)으로 만든다. 6.12.0 은 꾸미지 않은 모양이었다. `append_markdown(doc, ...)`(6.x `doc.text.append_markdown`) 의 기본은 그대로다 | `from_markdown(text, style="plain")` (또는 `style=MarkdownStyle()`) |
| 표의 열 너비를 내용에 맞추고, 머리 행을 가운데로 놓고, 구분선의 `:---`·`:---:`·`---:` 를 열 정렬로 읽는다 | `MarkdownStyle(table_fit_columns=False, table_header_align=None)` |
| 목록 안의 목록을 깊이마다 오른쪽으로 들여 쓴다 | `MarkdownStyle(list_indent_mm=0)` |
| 중첩 번호 목록을 한/글처럼 `1.` `가.` `1)` `가)` 차례로 매긴다(6.x 는 `1.1.`). `#####`·`######` 제목도 제 수준의 번호를 받는다 | 없음 |

```python
from hwpx_automation.markdown import MarkdownStyle, from_markdown   # 6.x hwpx.tools.markdown_import

doc = from_markdown("# 제목\n\n- 항목\n  - 하위 항목\n", style="plain")   # 6.12 모양
old_tables = MarkdownStyle(table_fit_columns=False, table_header_align=None, list_indent_mm=0)
```

## 읽기 — Markdown 내보내기와 ingest (이제 python-hwpx-automation)

아래 동작 변화는 [옮겨 간](#옮겨-간-기능) `hwpx_automation.markdown`·`hwpx_automation.ingest` 에 그대로 있다.

| 무엇이 달라지나 | 옛 동작을 유지하는 법 |
|---|---|
| `to_markdown(doc)`(6.x `doc.text.markdown()`)이 문서 글을 이스케이프한다. 글에 든 `<img …>`, `[x](javascript:…)`, `*별표*`, 줄머리 `#`·`-`·`1.` 이 서식이나 HTML 로 읽히지 않는다. 글에 적힌 `$…$` 수식은 그대로 둔다 | 없음 |
| 제목을 문단의 개요 수준(개요 번호, `개요 N` 스타일)으로 정한다. `add_heading` 으로 만든 제목이 `#` 으로 나오고, 시험 문항이나 차례 줄이 제목으로 나오지 않는다. 기본 `to_markdown`·`to_html` 도 개요 문단을 제목으로 쓴다 | `to_markdown(doc, headings=False)`, rich 는 `heading_source="text"`(글 모양으로 짐작) |
| `notes=True` 의 각주가 각주 문법(`[^fn1]`, HTML 은 `<sup>`)으로 나간다(6.x 의 "문장1)1)각주" 꼴이 사라진다) | `notes="inline"` |
| `to_html` 이 칸 안 표를 칸 안 표로 둔다 | `to_html(doc, nested_tables=False)` |
| ingest(6.x `hwpx.ingest`, LangChain·LlamaIndex 어댑터 포함)의 Markdown 에 머리말·꼬리말·메모·수식(`$LaTeX$`)과 목록 번호가 실리고, 글자색 `<span>` 은 빠진다. 6.x 는 머리말 등을 빼고 `metadata["left_out"]`·`warnings` 에 보고만 했다 | `convert(path, markdown_options={"headers_and_footers": False, "memos": False, "equations": False})` |
| 그림을 꺼내지 않을 때(`image_dir` 없이) 그림 캡션이 `*캡션*` 으로 나간다. 6.x 는 캡션까지 뺐다 | 없음 |

`to_markdown(doc, rich=True)`(6.x `doc.text.markdown(rich=True)`) 의 새 옵션 `headers_and_footers=`·`memos=`·
`equations=`·`list_labels=` 은 기본이 꺼짐이다.

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
| `.hwp` 를 열 때 글자·문단 모양 변경 추적을 옮긴다: 머리에 변경 추적 정의(`hh:trackChanges`·작성자)가 생기고, run 에 `charTcId`, 문단에 `paraTcId` 가 붙는다. `conversion_report` 에 `unconverted["track-changes"]`·`unconverted["range-tag-18"]`·`dropped["range-tag-19"]` 가 더 나오지 않고, 그런 문서도 `.hwp` 로 다시 쓸 수 있다 | 없음(6.x 결과는 한/글이 지운 글까지 보통 글로 그렸다) |
| 문서 이력(DocHistory)이 든 `.hwp` 는 경고와 함께 `conversion_report.unconverted["doc-history"]` 로 알린다. 옮기지 못한 내용이 있는 문서라 `.hwp` 로 다시 쓰면 `hwp5-write-lossy-source` 로 거부한다 | `.hwpx` 로 저장한다 |
| 개체 바로 앞에서 시작하는 변경 표시가 `hp:t` 안에 들어가고(6.x 는 한/글이 읽지 않는 `hp:run` 바로 아래), 표시 `Id` 를 한/글처럼 모든 변경 범위로 센다 | 없음 |
| 테두리/배경 "없음"(id 0)을 가리키던 쪽 테두리·글자 모양·문단 모양·표 칸이, 머리에 새로 더한 "아무것도 그리지 않는" `hh:borderFill` 을 가리킨다. 머리의 테두리 정의가 하나 늘 수 있다 | 없음(OWPML 에는 id 0 이 없다) |
| 대각선 칸의 `centerLine`·꺾임(`Crooked`), 채우기 그림의 `bright`·`contrast`, 확인용이 아닌 글머리표의 `checkedChar`, 개체 설명의 줄 바꿈(CR → LF), 앞뒤 공백이 있는 수식의 `xml:space="preserve"` 가 한/글 변환과 같아진다 | 없음 |
| 한 구역 스트림에 구역 정의가 여럿인 `.hwp`(한/글이 쓰지 않은 파일)를 그 수만큼 구역으로 연다 | 없음 |
| `META-INF/container.xml` 이 가리키는 미리보기(`Preview/PrvText.txt` 등)가 없는 문서를 열고 저장한다. 6.x 는 `HwpxStructureError` 로 거부했다 | 없음 |
| HWP 3.x 이하 `.hwp` 를 열면 "File is not a zip file" 대신 지원하지 않는 형식이라고 알린다. 오류 형(`HwpxArchiveError`)은 같다 | 오류 문구를 비교하던 코드는 형이나 `code` 로 비교한다 |

## 되돌리기

`pip install "python-hwpx<7"`. 6.x 라인은 그대로 있다.
