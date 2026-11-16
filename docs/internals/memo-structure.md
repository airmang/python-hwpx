# 메모(MEMO 필드) 구조

한/글의 메모(주석)를 프로그램으로 붙일 때 흔히 겪는 함정은 "요소는 만들었는데 한/글에서 메모가 안 보인다"입니다. 이 문서는 한/글 2024가 저장하는 메모의 구조와, 7.0이 그것을 어떻게 그대로 쓰는지를 코드로 짚습니다.

## 두 조각

### 1. 본문의 MEMO 필드: `<hp:fieldBegin type="MEMO">`

메모는 본문 문단에 걸린 MEMO 필드입니다. `src/hwpx/_document/memos.py`의 `attach_memo_field`가 문단 앞에 `<hp:ctrl><hp:fieldBegin type="MEMO">` run을, 뒤에 `<hp:fieldEnd>` run을 넣어 필드가 문단 내용을 감싸게 합니다. `fieldBegin`의 `id`와 `fieldEnd`의 `beginIDRef`가 짝을 이룹니다. 문단 첫 run에 `hp:secPr`가 있으면(구역의 첫 문단) 필드는 한/글처럼 그 run 뒤에 놓입니다.

**메모 글은 이 필드의 `hp:subList` 안에 있습니다.** 한/글 2024는 여백 풍선의 글을 여기서 읽고, 저장할 때 `<hp:memogroup>`을 쓰지 않습니다. 7.0도 `hp:memogroup`을 쓰지 않습니다. subList에 글이 아니라 id를 넣으면 한/글은 코멘트 대신 숫자를 그립니다(과거 회귀).

필드의 매개변수는 한/글 2024 저장본(`tests/fixtures/hancom_saved`)과 같은 일곱 개를 같은 순서로 씁니다.

```
<hp:parameters cnt="7" name="">
  <hp:integerParam name="Prop">0</hp:integerParam>
  <hp:stringParam name="Command">MEMO/65535/1/<FILETIME 하위>/<FILETIME 상위>/<작성자>/\;;</hp:stringParam>
  <hp:stringParam name="ID">memo1</hp:stringParam>
  <hp:integerParam name="Number">1</hp:integerParam>
  <hp:stringParam name="Author">작성자</hp:stringParam>
  <hp:stringParam name="MemoShapeIDRef">65535</hp:stringParam>
  <hp:stringParam name="CreateDateTime">2026-11-17T14:00:00Z</hp:stringParam>
</hp:parameters>
```

- `ID`는 `memo<Number>`입니다. 호출자가 `memo_id=`로 이름을 준 메모만 그 이름을 씁니다.
- `CreateDateTime`은 그 컴퓨터의 시각입니다(끝에 `Z`가 붙지만 UTC가 아닙니다). `Command`의 FILETIME은 같은 순간을 UTC로, 초 단위로 적습니다. 한/글이 저장한 메모는 모두 두 값이 그 컴퓨터의 UTC 차이(9시간)만큼 다릅니다.
- 작성자가 없으면 `Author`는 빈 요소입니다.
- 6.x는 매개변수 다섯 개(`ID`, `Number`, `Author`, `MemoShapeIDRef`, `CreateDateTime`)를 썼습니다. 이 꼴도 그대로 읽습니다.

### 2. 메모 모양: 구역의 `memoShapeIDRef`

메모 상자의 모양(테두리 선 굵기·색, 채움색, 폭)은 헤더의 `<hh:memoPr>`(모델상 `MemoShape`; `src/hwpx/oxml/header.py`)에 있습니다. 한/글은 이것을 **메모가 아니라 구역**에 겁니다. 구역 속성 `hp:secPr`의 `memoShapeIDRef`가 `hh:memoPr` 하나를 가리키고(`0`은 기본 모양), MEMO 필드에는 늘 `MemoShapeIDRef=65535`를 씁니다. 한/글이 저장한 문서(`hwpxlib_corpus/error__20251107__test.hwpx`)는 구역들이 `memoPr` 1과 2를 가리키고, 필드는 모두 65535입니다.

- 읽기: `document.sections[i].properties.memo_shape_id_ref`(기본 모양이면 `None`)
- 쓰기: `document.notes.set_memo_shape(shape_id, section=i)`(`section="all"`이면 모든 구역). 헤더에 없는 id는 `note-memo-shape-not-found`.
- 모양 정의: `document.styles.ensure_memo_shape(...)`, `document.styles.memo_shape(id)`

6.x는 메모마다 모양을 주었습니다(`add_memo(memo_shape_id_ref=)`, `memo.memo_shape_id_ref`). 7.0에서 둘 다 없어졌고, 쓰면 새 자리를 알려 주는 오류(`hwpx-argument-removed`, `document-name-removed`)가 납니다. 6.x 문서가 필드에 65535가 아닌 id를 적어 두었으면 그 값은 읽은 그대로 둡니다. 필드 메모는 `memo.attributes["MemoShapeIDRef"]`로 볼 수 있습니다.

> 표기 주의: 6.x `hp:memogroup`의 `<hp:memo>` 속성은 소문자 `memoShapeIDRef`, MEMO 필드 매개변수는 대문자 `MemoShapeIDRef`, 구역 속성은 `hp:secPr@memoShapeIDRef`입니다.

## 6.x 문서의 `hp:memogroup`

6.x로 만든 문서는 메모 글을 구역의 `<hp:memogroup>/<hp:memo>/<hp:paraList>`에도 적었습니다. 7.0은 이것을 읽기 전용으로 읽습니다(`HwpxOxmlMemoGroup`, `HwpxOxmlMemo`). 그 메모를 고치면 글을 필드의 subList로 옮기고 `hp:memogroup` 쪽 사본은 지웁니다.

## 고수준 API

- `document.notes.add_memo(text, paragraph=paragraph)` — 대상 문단에 MEMO 필드를 붙여 **표시까지** 보장합니다(`src/hwpx/_document/memos.py`). 돌려받은 메모의 `memo.paragraph`·`memo.field_id`로 앵커를 읽습니다. (5.x·6.x의 `add_memo_with_anchor`는 7.0에서 없어졌습니다.)
- `document.notes.add_memo(text)` — 문단에 걸지 않은 메모. 저장 전에 `document.notes.attach(paragraph, memo)`로 걸어야 합니다. 걸리지 않은 메모가 남아 있으면 저장이 `note-memo-unanchored`로 거절됩니다.
- `document.notes.set_memo_shape(shape_id, section=i)` — 구역의 메모 모양.

필드 run의 `charPrIDRef`는 인자 → 문단의 `char_pr_id_ref` → 메모가 추론한 값 → `"0"` 순으로 해결됩니다(`document.notes.attach`).

> 참고: MCP 서버 쪽에는 `add_memo_by_anchor`라는 도구 이름이 있지만, 그것은 이 라이브러리 함수를 감싼 래퍼입니다.

## 테스트로 고정된 계약

- `tests/test_memo_and_style_editing.py::test_attach_memo_field_inserts_control_runs` — 매개변수 일곱 개와 순서, `MemoShapeIDRef=65535`, `Command` 꼴, 그리고 (회귀 방지) 필드 subList가 **id가 아니라 코멘트 텍스트**를 담는지.
- 같은 파일의 `test_memo_create_time_is_written_as_hancom_writes_it`, `test_memo_command_filetime_is_the_same_moment_in_utc` — 두 시각.
- `tests/test_memo_shape_authoring.py` — 구역 메모 모양 쓰기·왕복·거절, 없어진 6.x 이름의 안내.
- `tests/test_memo_kept_in_field.py` — 메모가 필드에만 있고 `hp:memogroup`이 없음.
- `tests/test_oxml_parsing.py` — 헤더의 `<hh:memoPr>` 파싱과 id 정규화 조회(`memo_shape("07") == shapes["7"]`).

## 실전 요약

- 메모를 "보이게" 하려면 본문 문단에 MEMO 필드(`fieldBegin`/`fieldEnd`)가 있고, 그 subList에 메모 글이 있어야 합니다.
- 모양은 구역에 겁니다. 필드에는 65535를 씁니다.
- 직접 XML을 조립하지 말고 `document.notes.add_memo(paragraph=...)`를 쓰면 이 배선이 자동입니다.
