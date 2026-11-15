# python-hwpx 7.0 이주 가이드

6.12.0 에서 7.0.0 으로 올리면 **결과가 달라지는 호출**이 있다. 대부분은 인자 하나로
6.x 의 결과를 그대로 얻는다. 6.0 에서 옮긴 옛 이름과 `section_index=` 의 정리는
[옛 이름 제거](#옛-이름-제거) 절에 있다.

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

## Markdown 가져오기 — `from_markdown`·`append_markdown`

| 무엇이 달라지나 | 옛 동작을 유지하는 법 |
|---|---|
| `from_markdown(text)` 이 모양을 주지 않으면 보고서 모양(색 띠 제목 상자, `Ⅰ` 번호 상자, 줄 표, 쪽 번호, 휴먼명조·HY헤드라인M)으로 만든다. 6.12.0 은 꾸미지 않은 모양이었다. `doc.text.append_markdown` 의 기본은 그대로다 | `from_markdown(text, style="plain")` (또는 `style=MarkdownStyle()`) |
| 표의 열 너비를 내용에 맞추고, 머리 행을 가운데로 놓고, 구분선의 `:---`·`:---:`·`---:` 를 열 정렬로 읽는다 | `MarkdownStyle(table_fit_columns=False, table_header_align=None)` |
| 목록 안의 목록을 깊이마다 오른쪽으로 들여 쓴다 | `MarkdownStyle(list_indent_mm=0)` |

```python
from hwpx.tools.markdown_import import MarkdownStyle, from_markdown

doc = from_markdown("# 제목\n\n- 항목\n  - 하위 항목\n", style="plain")   # 6.12 모양
old_tables = MarkdownStyle(table_fit_columns=False, table_header_align=None, list_indent_mm=0)
```

## 읽기 — Markdown 내보내기와 `hwpx.ingest`

| 무엇이 달라지나 | 옛 동작을 유지하는 법 |
|---|---|
| `hwpx.ingest`(LangChain·LlamaIndex 어댑터 포함)의 Markdown 에 머리말·꼬리말·메모·수식(`$LaTeX$`)이 실린다. 6.x 는 이것들을 빼고 `metadata["left_out"]`·`warnings` 에 보고만 했다 | `convert(path, markdown_options={"headers_and_footers": False, "memos": False, "equations": False})` |
| 그림을 꺼내지 않을 때(`image_dir` 없이) 그림 캡션이 `*캡션*` 으로 나간다. 6.x 는 캡션까지 뺐다 | 없음 |

`doc.text.markdown(rich=True)` 의 기본 결과는 그대로다. 새 옵션 `headers_and_footers=`·`memos=`·
`equations=` 은 기본이 꺼짐이다.

## 양식 채우기와 바꾸기

| 무엇이 달라지나 | 옛 동작을 유지하는 법 |
|---|---|
| 표 이름표를 공백을 무시하고 견준다(`fill_by_path`·`find_cell_by_label`). `"성명"` 으로 `"성  명"` 칸을 찾는다. 대신 공백만 다른 이름표 둘이 한 문서에 있으면 이제 `"ambiguous label"` 이다 | 몇 번째 이름표인지 적는다: `"성명[2] > right"`(실패 결과의 `candidates` 가 고르는 표기를 알려 준다) |
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
