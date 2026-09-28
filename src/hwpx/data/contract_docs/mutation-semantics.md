# 편집 의미론 — 무엇이 돌아오고, 어떻게 실패하고, 다시 실행하면 어떻게 되나

stable 편집 표면의 계약을 한 곳에 모았다. 아래 표의 실패 모드와 재실행
성질은 전부 이 저장소의 테스트·실측으로 확인된 동작이다. 보존 등급 어휘는
[안전한 쓰기 계약](safe-write-contract.md), stable/experimental 구분은
[stable API](stable-api.md)를 따른다.

> **Python 블록 판정:** [실행 분류 ledger](python-example-ledger.json)가 이
> current manual의 모든 Python 블록을 동결합니다. 이 문서의 블록은 앞 문맥의
> `document`가 필요한 조각입니다.

## 핵심 편집 호출 계약

| 호출 | 반환 | 대표 실패 모드 | 다시 실행하면 |
|---|---|---|---|
| `add_paragraph(text)` | `HwpxOxmlParagraph` | 사실상 없음 | 문단이 하나 더 추가된다(append, 비멱등) |
| `paragraph.remove()` | `None` | 문단을 담은 곳(구역·표 셀·머리말·꼬리말)의 마지막 문단이면 `HwpxValueError`(`ValueError` 하위, `code="paragraph-remove-last"`, `context["container"]`는 `section`·`cell`·`header`·`footer`) | 이미 제거된 문단이면 조용히 무시된다(무해) |
| `add_table(rows, cols)` | `HwpxOxmlTable` | 사실상 없음 | 표가 하나 더 추가된다(비멱등) |
| `table.set_cell_text(r, c, text)` | `FitResult \| None` | 범위 밖 좌표는 `IndexError` (`exceed table bounds`) | 같은 값이면 결과 동일(수렴). 무엇을 남기고 다시 만드는지는 아래 |
| `paragraph.char_pr_id_ref = id` | — | 사실상 없음 | 그 문단에 바로 딸린 run 전부에 같은 값이 들어간다(수렴). 안쪽 표 셀의 run은 건드리지 않는다. run이 없으면 하나 만든다. `None`은 속성을 지운다 |
| `table.equalize_column_widths()` | `None` | 칸 영역이 새 열 격자에 맞지 않거나 세로로 합친 칸이 행마다 다른 너비를 받아야 하면 표를 그대로 두고 `HwpxValueError` | 행마다 칸을 같게 나눈다(한/글 "셀 너비를 같게", 표 너비는 행별 칸 수의 공배수로 올림). 예전 나눔(표 너비 유지, 앞 `n-1`열 `round(W / n)`, 마지막 열 나머지)이 필요하면 `table.set_column_widths([1] * table.column_count)` |
| `cell.set_margins(left=, right=, top=, bottom=)` | `CellMargins` | 값이 `int`가 아니거나(`bool` 포함) `0 <= v < 2**31` 밖이면 바꾸기 전에 `HwpxValueError`(`cell-margin-value`) | 같은 값이면 결과 동일(수렴). 인자가 없으면 아무것도 바꾸지 않고 지금 여백을 돌려준다 |
| `document.text.replace(search, repl, everywhere=False)` | `int` (치환 수) | 빈 `search`는 `ValueError` | 치환할 것이 없으면 `0` — 1회차 후 수렴 |
| `document.notes.add_memo(..., anchor=p)` | `Memo` (`paragraph`, `field_id` 속성) | 아래 캐비앗 참고 | 메모가 하나 더 붙는다(비멱등) |
| `document.notes.add_footnote(text, paragraph)` | `HwpxOxmlNote` | 사실상 없음 | 각주가 하나 더 붙는다(비멱등) |
| `section.clear_body(on_control_content="raise")` | `ClearBodyReport` | 첫 문단 첫 run에 `hp:secPr`가 없으면 `section-clear-no-section-properties`, 남길 `hp:secPr`/`hp:ctrl` 안에 글·표·개체·양식 개체·덧말·글자 겹침이 있으면 `section-clear-control-content`(`context["tags"]`), 모르는 모드면 `section-clear-mode-invalid` — 모두 바꾸기 전에 거부 | 이미 비운 섹션이면 아무것도 바꾸지 않고 dirty로 표시하지도 않는다(멱등, 보고 수치 0) |
| `run.content_kinds()` | `frozenset[str]` (`RUN_CONTENT_KINDS` 어휘) | 사실상 없음 | 읽기 전용 |

"사실상 없음"은 정상 인자에서 실패 경로가 없다는 뜻이다 — 타입이 어긋난
인자는 여느 파이썬 API처럼 `TypeError` 계열로 즉시 드러난다.

### 셀 글 쓰기가 남기는 것과 다시 만드는 것

`table.set_cell_text(r, c, text)`(= `cell.set_text(text)`)의 기본 동작은 문단을
다시 만들지 않는다.

- 글은 셀 자신의 문단에 있는 첫 `hp:t`에 들어간다. 없으면 첫 문단의 빈 run에,
  빈 run도 없으면 첫 문단 맨 앞의 새 run에 만든다. 셀 자신의 문단에 있는 다른
  `hp:t`는 비운다. 셀 안의 표·개체는 글을 그대로 둔다(누름틀 칸 채우기
  `doc.fields.fill_cell()`도 같다).
- 이번 쓰기로 글이 비워져 빈 `hp:t`만 남은 셀 문단은 지운다. 원래 비어 있던
  문단(빈 줄)과 안쪽 표·개체를 담은 문단은 남는다.
- 남는 문단은 id와 `paraPrIDRef`, run의 `charPrIDRef`가 그대로다.
- `preserve_format=False`면 글을 받은 run 하나만 `charPrIDRef="0"`이 된다.
- 셀 문단의 줄 배치 캐시(`hp:linesegarray`)를 지워 한/글이 줄을 다시 나누게 한다.

`split_paragraphs=True`면 셀 문단을 **다시 만든다**. 기존 문단은 모두 지워지고
(안쪽 표를 담은 문단도 함께), 줄마다 run 하나짜리 새 문단이 새 id로 생긴다.
줄 `i`는 기존 `i`번째 문단(없으면 첫 문단)의 `paraPrIDRef`·`styleIDRef`·
`pageBreak`·`columnBreak`·`merged`와 그 문단 첫 run의 `charPrIDRef`를 이어받는다.

### 셀 여백

`cell.margins`는 한/글이 셀을 배치할 때 쓰는 안쪽 여백을 `CellMargins`
(HWPUNIT, `left`·`right`·`top`·`bottom`)로 돌려준다. 셀의 `hasMargin`이 켜져
있지 않으면 표의 `hp:inMargin`을, 켜져 있으면 셀의 `hp:cellMargin`을 쓴다.
`add_table()`이 만든 셀은 `CellMargins(510, 510, 141, 141)`이다.
`cell.set_margins(...)`는 주지 않은 면을 지금 여백으로 채워 네 면 모두를 셀의
`hp:cellMargin`에 쓰고 `hasMargin="1"`로 켠다. 그 뒤로는 표 여백이 이 셀에
적용되지 않는다. 실제 여백이 바뀌면 그 셀 `hp:subList`에 바로 든 문단의 줄 배치
캐시(`hp:linesegarray`)를 지워 한/글이 줄을 다시 나누게 한다. 안쪽 표의 문단은
건드리지 않는다. 여백이 그대로면 캐시도 그대로다.

## 저장 의미론

```python
report = document.save_to_path("out.hwpx", return_report=True)
print(report.actual_mode)
```

- `save_to_path()`는 원자적이다: 임시 파일에 쓴 뒤 rename하고, editor-open
  안전 검증을 통과한 결과만 대상 경로를 교체한다.
- 요청한 보존 등급(`mode="patch"` 등)을 지킬 수 없으면
  `PreservationDowngradeError`로 실패하고 **아무것도 쓰지 않는다**
  (`mode="patch", fallback="error"`). 기본 `auto`는 달성 가능한 등급을 선택하며,
  명시한 `fallback="rebuild"`는 강등을 허용한다.
- `return_report=True`는 `MutationReport`를 돌려준다 — 실제 저장 모드,
  손대지 않은 파트의 바이트 보존 검증 결과까지. 스키마와 전체 규칙은
  [안전한 쓰기 계약](safe-write-contract.md).
- `report.ok`는 요청 내용 반영을 검사하지 않는다. 요청 건수와 출력 값을 별도로
  확인하고 `verification.visual="not_performed"`를 시각 통과로 읽지 않는다.
- **직렬화는 결정론적이다**: 같은 문서 상태에서 `to_bytes()`를 두 번 부르면
  바이트가 동일하다(실측). diff·해시 기반 파이프라인에 안전하다.

## 알아둘 캐비앗 (정직 고지)

- `document.notes.add_memo(memo_shape_id_ref=...)`는 참조가 실재하는 메모
  모양인지 **검증하지 않고 조용히 수용한다**. 존재하지 않는 ID를 넣으면
  저장은 되지만 편집기 표시가 어긋날 수 있다. `document.styles.memo_shapes`로
  실재 ID를 확인하고 쓰는 것을 권장한다.
- `document.text.replace`는 기본으로 본문 문단의 개별 런 안에서 치환한다. 여러
  런에 걸친 검색어와 표 칸·머리말 같은 다른 곳의 문단은 대상이 아니다.
  `everywhere=True`면 한/글 "모두 바꾸기"처럼 표 칸(칸 안 표 포함)·글상자·캡션·
  머리말·꼬리말·각주·미주·바탕쪽의 문단과 여러 런에 걸친 말까지 바꾼다(바꿀 글의 글자는
  같은 자리의 찾은 글자가 있던 런의 서식). 메모 본문은 어느 쪽이든 바꾸지 않는다. `0`을 반환하면
  저장 성공 여부와 관계없이 요청이 반영되지 않은 것이다.
- `add_*` 계열은 전부 append 의미론이다. "없으면 추가"가 필요하면 먼저
  {doc}`recipes-traversal`의 순회로 존재 여부를 확인하라.
- `section.clear_body()`는 첫 문단 첫 run의 `hp:secPr`(쪽 설정)와 첫 문단 모든
  run의 `hp:ctrl`(단·머리말·꼬리말·쪽 번호)만 남긴다. 한/글은 쪽 번호·머리말
  컨트롤을 흔히 둘째 run에 쓴다. 컨트롤이 없는 뒤쪽 run은 지우고, 첫 문단 안 표
  속의 컨트롤은 표와 함께 지운다. `on_control_content="strip"`은 내용이 든
  `hp:ctrl`과, `set_header()`·`set_footer()`가 `hp:secPr` 안에 따로 쓰는
  머리말·꼬리말 사본(한컴은 `hp:ctrl` 쪽만 읽는다)과 그것을 가리키는
  `headerApply`·`footerApply`를 지운다. 그래도 내용이 남을 자리(`hp:secPr`의
  다른 자식 등)에 내용이 있으면 지우지 않고 `section-clear-control-content`로
  거부한다 — `"strip"`이 성공했다면 남은 내용은 없다. 공유 전에 무엇을 지울지는
  호출자가 정한다.
- 편집은 저장 전까지 메모리에만 있다. 저장 경로가 곧 커밋이다.

## 다음 단계

- 문서에서 원하는 것을 꺼내는 법 → {doc}`recipes-traversal`
- 보존 등급·영수증 스키마 → [안전한 쓰기 계약](safe-write-contract.md)
- 표면 안정성 구분(stable/experimental) → [stable API](stable-api.md)
