# python-hwpx 6.0 이주 가이드 (7.0에서 제거된 이름 포함)

6.0 은 `HwpxDocument` 의 공개 표면을 **102개에서 34개로** 줄였다. 나머지
79개는 도메인 네임스페이스로 **옮겨갔다**.

## 7.0 에서 제거됨

6.x 는 옛 이름 79개를 `DeprecationWarning` 과 함께 남겨 두었다. **7.0 은 예고대로
그 이름들을 지웠다.** 부르면 새 자리를 알려 주는 오류가 난다:

```text
>>> doc.set_header_text("머리말")
HwpxAttributeError: doc.set_header_text(...) 는 python-hwpx 7.0에서 없어졌습니다.
doc.page.set_header(text=...) 를 쓰세요. 예: doc.page.set_header(text="머리말")
```

`HwpxAttributeError` 는 `AttributeError` 이기도 하다 — `hasattr(doc, "set_header_text")`
는 `False` 다. 오류의 `code` 는 `document-name-removed`, 새 자리는 `context["replacement"]`.

함께 지운 것:

| 7.0 에서 없어진 것 | 대신 | 부르면 |
|---|---|---|
| `section_index=` 인자(루트·묶음 46개 메서드, 모델 4개) | `section=` — 번호와 구역 객체를 모두 받는다 | `HwpxTypeError`(`hwpx-argument-removed`) |
| `style_id_ref=` 인자(`add_paragraph`·`add_table`·`add_picture`, `doc.shapes.add_raw`/`add_control`, 모델 `Document`/`Section`/`TableCell.add_paragraph`) | `style=` — 이름·번호·`Style` 객체 | `HwpxTypeError`(`hwpx-argument-removed`) |
| `from hwpx import <실험 기능>` 26개 | `from hwpx.experimental import ...` | `hwpx.MovedToExperimental`(ImportError) |

`style=` 과 옛 `style_id_ref=` 는 동작이 다르다. `style=` 은 한/글이 스타일을 적용할 때처럼
그 스타일의 문단 모양·글자 모양도 쓴다(`para_pr_id_ref`·`char_pr_id_ref` 를 함께 주면 그것이
먼저다). 모양은 그대로 두고 스타일 **이름표만** 붙이려면 만든 문단에 직접 쓴다:

```python
paragraph = doc.add_paragraph("본문")
paragraph.style_id_ref = 2   # 옛 add_paragraph("본문", style_id_ref=2)
```

호출을 한꺼번에 옮기는 스크립트(`migrate_calls.py`, dry-run 뒤 `--write`)가 저장소의 7.0 이주
자료에 있다. 아래 대응표가 그 근거다.

## 6.0 에서 깨진 것(반환 형식)

**경로 이동은 6.x 동안 아무것도 깨뜨리지 않았다.** 7.0 부터는 위처럼 옛 이름이 없다.

깨지는 것은 **반환 타입**뿐이다. `add_*` 가 dict·str·int·tuple 대신 도메인
객체를 돌려준다.

| 5.x 반환 | 6.0 반환 | 옮기는 법 |
|---|---|---|
| `add_form_field(...)` → 20키 `dict` | `FormField` | `f["name"]` → `f.name`. id 별칭 `id`/`fieldid` 는 `field_id` 하나로 |
| `list_form_fields()` → `list[dict]` | `tuple[FormField, ...]` | 원소 접근을 속성으로 |
| `fill_form_field(...)` → `dict` (`ok` 포함) | `FieldFillResult` | `r["after_value"]` → `r.after`. **`ok` 는 없다** — 실패는 예외로 |
| `add_check_box(...)` / `set_check_box(...)` → `dict` | `CheckBox` | `cb["checked"]` → `cb.checked` (쓰기도 된다) |
| `add_image(...)` → `str` | `BinaryItem` | `item.item_id`. `str(item)`·f-string 은 그대로 동작 |
| `list_images()` / `picture_references()` → `list[dict]` | `tuple[BinaryItem/PictureRef, ...]` | 속성 접근. 빈 값은 `[]` 가 아니라 `()` |
| `replace_picture(...)` → `dict` | `PictureReplacement` | `r["new_binaryItemIDRef"]` → `r.item_id` |
| `add_track_change` / `add_tracked_insert` / `add_tracked_delete` → `int` | `TrackedChange` | `ch.change_id`. **`int()` 변환은 없다** |
| `add_tracked_replace(...)` → `tuple[int, int]` | `TrackedReplacement` | `r.insert` / `r.delete` — 어느 쪽인지 타입이 말한다 |
| `add_memo_with_anchor(...)` → 3-튜플 | `Memo` | `memo.paragraph` / `memo.field_id` |
| `attach_memo_field(...)` → `str` | `Memo` | `memo.field_id` |
| `set_paragraph_format(...)` / `set_list_format(...)` → `dict` | `ParagraphFormatResult` / `ListFormatResult` | `r["formatted"]` → `r.formatted` |
| `set_page_setup(...)` → 중첩 `dict` | `PageSetup` | `r["pageSize"]` → `r.page_size` |
| `merge_table_cells(...)` → `Any` | `TableCell` | 런타임은 그대로 — 타입만 정직해졌다 |

## 6.0 이 고친 것

**① `section=0` 이 동작한다.** 5.x 는 내부가 새는 `AttributeError` 를 냈다.
(7.0: 옛 별칭 `section_index=` 는 없어졌다.)

```python
document.page.set_header(text="머리말", section=0)   # 인덱스도 객체도 받는다
```

잘못된 값은 전부 typed error 다 — 범위 밖은 `section-not-found`, 타입 오류는
`section-invalid-type`.

**② 스타일을 이름으로 지정하고, 오타를 호출 시점에 잡는다.**

```python
document.add_paragraph("본문", style="개요 1")
document.add_paragraph("본문", style="개요1")
# HwpxLookupError(code="style-not-found"), context["closest"] == ["개요 1", "개요 10"]
```

숫자 id 를 받던 `style_id_ref=` 는 6.x 동안 동작했고 7.0 에서 없어졌다(위 「7.0 에서 제거됨」).

**③ `add_heading` 이 생겼다.** 개요 스타일과 개요 수준을 **함께** 붙인다 —
5.x 는 둘이 분리돼 "번호는 붙는데 스타일은 바탕글"인 문단이 나왔다.

```python
document.add_heading("2026 학년도 운영계획", level=1)   # level 1..10
```

**④ 공개 경로의 실패가 전부 typed 다.** `code`·`context`·`suggestion` 을
싣는다(70종 — `docs/error-codes.md`). 기존 `except ValueError` 는 그대로
작동한다 — typed 클래스가 자기가 대체한 builtin 을 함께 상속한다.

## 이주가 급하지 않다면

6.x 에 머무르면 옛 이름이 경고와 함께 계속 답한다: `pip install "python-hwpx<7"`.
6.x 에서 경고를 한 번에 보려면:

```bash
python -W error::DeprecationWarning -m pytest
```

## 전수 대응표 (79)

`doc` 는 `HwpxDocument` 인스턴스다. 왼쪽은 6.x 동안 경고와 함께 동작했고,
**7.0 에서 제거됐다**(부르면 오른쪽을 알려 주는 오류). `export_html`·`export_markdown`·
`export_rich_markdown`·`fill_by_path`·`find_cell_by_label`·`get_table_map` 의 새 자리는
자동화 패키지(python-hwpx-automation)로 다시 이사할 예정이다.

### `doc.styles` — 서식 정의 (16)

| 5.x | 6.0 |
|---|---|
| `doc.border_fill(…)` | `doc.styles.border_fill` |
| `doc.border_fills` | `doc.styles.border_fills` |
| `doc.bullet(…)` | `doc.styles.bullet` |
| `doc.bullets` | `doc.styles.bullets` |
| `doc.char_properties` | `doc.styles.char_properties` |
| `doc.char_property(…)` | `doc.styles.char_property` |
| `doc.ensure_border_fill(…)` | `doc.styles.ensure_border_fill` |
| `doc.ensure_numbering(…)` | `doc.styles.ensure_numbering` |
| `doc.ensure_run_style(…)` | `doc.styles.ensure_run` |
| `doc.memo_shape(…)` | `doc.styles.memo_shape` |
| `doc.memo_shapes` | `doc.styles.memo_shapes` |
| `doc.paragraph_properties` | `doc.styles.paragraph_properties` |
| `doc.paragraph_property(…)` | `doc.styles.paragraph_property` |
| `doc.set_list_format(…)` | `doc.styles.apply_list_format` |
| `doc.set_paragraph_format(…)` | `doc.styles.apply_paragraph_format` |
| `doc.style(…)` | `doc.styles.get` |

### `doc.page` — 쪽 기하 (11)

| 5.x | 6.0 |
|---|---|
| `doc.remove_footer(…)` | `doc.page.remove_footer` |
| `doc.remove_header(…)` | `doc.page.remove_header` |
| `doc.set_columns(…)` | `doc.page.set_columns` |
| `doc.set_footer_content(…)` | `doc.page.set_footer(content=...)` |
| `doc.set_footer_text(…)` | `doc.page.set_footer(text=...)` |
| `doc.set_header_content(…)` | `doc.page.set_header(content=...)` |
| `doc.set_header_text(…)` | `doc.page.set_header(text=...)` |
| `doc.set_page_margins(…)` | `doc.page.set_margins` |
| `doc.set_page_number(…)` | `doc.page.set_page_number` |
| `doc.set_page_setup(…)` | `doc.page.setup` |
| `doc.set_page_size(…)` | `doc.page.set_size` |

### `doc.text` — 텍스트 (6)

| 5.x | 6.0 |
|---|---|
| `doc.export_html(…)` | `doc.text.html` |
| `doc.export_markdown(…)` | `doc.text.markdown` |
| `doc.export_text(…)` | `doc.text.plain` |
| `doc.find_runs_by_style(…)` | `doc.text.find_runs` |
| `doc.iter_runs(…)` | `doc.text.runs` |
| `doc.replace_text_in_runs(…)` | `doc.text.replace` |

### `doc.parts` — OPC 파트 (4)

| 5.x | 6.0 |
|---|---|
| `doc.headers` | `doc.parts.headers` |
| `doc.histories` | `doc.parts.histories` |
| `doc.master_pages` | `doc.parts.master_pages` |
| `doc.version` | `doc.parts.version` |

### `doc.tables` — 표 (4)

| 5.x | 6.0 |
|---|---|
| `doc.fill_by_path(…)` | `doc.tables.fill_by_path` |
| `doc.find_cell_by_label(…)` | `doc.tables.find_cell_by_label` |
| `doc.get_table_map(…)` | `doc.tables.map` |
| `doc.merge_table_cells(…)` | `doc.tables.merge_cells` |

### `doc.fields` — 양식개체 (6)

| 5.x | 6.0 |
|---|---|
| `doc.add_check_box(…)` | `doc.fields.add_check_box` |
| `doc.add_form_field(…)` | `doc.fields.add` |
| `doc.fill_form_field(…)` | `doc.fields.fill` |
| `doc.list_check_boxes(…)` | `doc.fields.check_boxes` |
| `doc.list_form_fields(…)` | `doc.fields.all` |
| `doc.set_check_box(…)` | `doc.fields.set_check_box` (또는 `doc.fields.check_boxes[i].checked = …`) |

### `doc.shapes` — 인라인 개체 (7)

| 5.x | 6.0 |
|---|---|
| `doc.add_chart(…)` | `doc.shapes.add_chart` |
| `doc.add_control(…)` | `doc.shapes.add_control` |
| `doc.add_ellipse(…)` | `doc.shapes.add_ellipse` |
| `doc.add_equation(…)` | `doc.shapes.add_equation` |
| `doc.add_line(…)` | `doc.shapes.add_line` |
| `doc.add_rectangle(…)` | `doc.shapes.add_rectangle` |
| `doc.add_shape(…)` | `doc.shapes.add_raw` |

### `doc.media` — 이진 항목 (5)

| 5.x | 6.0 |
|---|---|
| `doc.add_image(…)` | `doc.media.add_image` |
| `doc.list_images(…)` | `doc.media.images` |
| `doc.picture_references(…)` | `doc.media.picture_references` |
| `doc.remove_image(…)` | `doc.media.remove_image` |
| `doc.replace_picture(…)` | `doc.media.replace_picture` |

### `doc.notes` — 주석 (7)

| 5.x | 6.0 |
|---|---|
| `doc.add_endnote(…)` | `doc.notes.add_endnote` |
| `doc.add_footnote(…)` | `doc.notes.add_footnote` |
| `doc.add_memo(…)` | `doc.notes.add_memo` |
| `doc.add_memo_with_anchor(…)` | `doc.notes.add_memo(anchor=...)` |
| `doc.attach_memo_field(…)` | `doc.notes.attach` |
| `doc.memos` | `doc.notes.memos` |
| `doc.remove_memo(…)` | `doc.notes.remove_memo` |

### `doc.refs` — 참조 (2)

| 5.x | 6.0 |
|---|---|
| `doc.add_bookmark(…)` | `doc.refs.add_bookmark` |
| `doc.add_hyperlink(…)` | `doc.refs.add_hyperlink` |

### `doc.tracking` — 변경추적 (8)

| 5.x | 6.0 |
|---|---|
| `doc.add_track_change(…)` | `doc.tracking.add_change` |
| `doc.add_tracked_delete(…)` | `doc.tracking.delete` |
| `doc.add_tracked_insert(…)` | `doc.tracking.insert` |
| `doc.add_tracked_replace(…)` | `doc.tracking.replace` |
| `doc.track_change(…)` | `doc.tracking.change` |
| `doc.track_change_author(…)` | `doc.tracking.author` |
| `doc.track_change_authors` | `doc.tracking.authors` |
| `doc.track_changes` | `doc.tracking.changes` |

### 강등 3종 (3)

| 5.x | 6.0 |
|---|---|
| `doc.export_rich_markdown(…)` | `doc.text.markdown(rich=True)` |
| `doc.remove_paragraph(…)` | `paragraph.remove()` |
| `doc.set_header_footer(…)` | `doc.page.set_header / doc.page.set_footer` |


## 이 표는 어디서 오는가

`tests/data/document_legacy_shims.json` 에서 생성된다. 7.0 에서 그 락은 지운 이름의
안내 표(`hwpx._document._legacy.REMOVED_NAMES`: 이름·새 자리·한 줄 예)에서 유도되고,
옛 이름을 부를 때 나는 오류 문구도 같은 표에서 나온다.
