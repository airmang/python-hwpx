# 메모(hp:memo) 구조

한/글의 메모(주석)를 프로그램으로 붙일 때 흔히 겪는 함정은 "요소는 만들었는데 한/글에서 메모가 안 보인다"입니다. 메모가 표시되려면 **세 조각 — 메모 본체, 본문의 MEMO 필드, 그리고 둘을 잇는 참조 — 가 모두 맞아야** 하기 때문입니다. 이 문서는 실제로 표시되는 메모의 구조를 코드로 짚습니다.

## 세 조각

### 1. 메모 본체: `<hp:memogroup>` 안의 `<hp:memo>`

메모 본체는 섹션의 `<hp:memogroup>` 컨테이너 안에 `<hp:memo>`로 들어갑니다(`src/hwpx/oxml/memo.py`의 `HwpxOxmlMemoGroup`, `HwpxOxmlMemo`). 각 `<hp:memo>`는 `id`와 `memoShapeIDRef` 속성을 가집니다.

메모의 **본문 텍스트**는 `<hp:memo>` 안의 `<hp:paraList>` → `<hp:p>` → `<hp:run>` → `<hp:t>`에 놓입니다(`HwpxOxmlMemo.set_text`). 즉 메모 본체가 만들어내는 구조는:

```
<hp:memogroup>
  <hp:memo id="..." memoShapeIDRef="5">
    <hp:paraList>
      <hp:p><hp:run charPrIDRef="0"><hp:t>메모 내용</hp:t></hp:run></hp:p>
    </hp:paraList>
  </hp:memo>
</hp:memogroup>
```

> 주의: 여기서 본문을 담는 컨테이너는 `paraList`입니다. 아래에 나오는 MEMO **필드**의 `subList`와 혼동하기 쉬운데, 둘은 서로 다른 위치입니다. (참고로 각주/미주 `<hp:footNote>`/`<hp:endNote>`는 또 별개로 `subList`를 씁니다.)

### 2. 본문의 MEMO 필드: `<hp:fieldBegin type="MEMO">`

메모가 한/글 편집기의 여백에 **풍선으로 표시되려면**, 본문 문단에 대응하는 MEMO 필드 컨트롤이 있어야 합니다. `docs/usage.md`가 이를 명시합니다:

> 한글 편집기에서 메모 풍선을 표시하려면 본문 문단에 대응되는 MEMO 필드 컨트롤(`hp:fieldBegin`/`hp:fieldEnd`)이 있어야 합니다.

이 필드는 `src/hwpx/_document/memos.py`의 `attach_memo_field`가 만듭니다. 문단의 앞뒤에 `<hp:ctrl><hp:fieldBegin type="MEMO">`와 `<hp:fieldEnd>` run을 삽입해, 필드가 문단 내용을 감싸게 합니다. `fieldBegin`의 `id`와 `fieldEnd`의 `beginIDRef`가 짝을 이룹니다.

**중요한 실측 함정**: 여백에 실제로 보이는 코멘트 텍스트는 이 MEMO **필드의 `subList`** 에 담깁니다. `memos.py`의 주석이 과거 회귀를 기록합니다:

> The MEMO field's subList holds the comment TEXT — this is what Hancom shows in the margin memo box. (Previously this emitted `memo.id`, so Hancom rendered the numeric id instead of the comment.)

즉 이 subList에 텍스트가 아니라 id를 넣으면, 한/글은 코멘트 대신 숫자를 그립니다. 표시는 되지만 내용이 틀린 셈입니다.

### 3. 잇는 참조: MemoShapeIDRef

메모 본체와 그 시각적 속성(메모 상자의 색·테두리 등)을 잇는 것이 **MemoShapeIDRef**입니다. MEMO 필드의 파라미터로 들어갑니다(`attach_memo_field`):

```python
parameters = _append_element(field_begin, f"{_HP}parameters", {"count": "5", "name": ""})
_append_element(parameters, f"{_HP}stringParam", {"name": "ID"}).text = memo.id or ""
...
# Hancom's own files use MemoShapeIDRef (65535 = the built-in default memo
# shape) — an empty/absent ref leaves the memo box unlinked.
_append_element(parameters, f"{_HP}stringParam", {"name": "MemoShapeIDRef"}).text = (
    memo_shape_id or "65535"
)
```

여기서 두 가지를 알 수 있습니다.

- **`65535`는 기본 메모 상자를 뜻하는 센티넬**입니다. 메모에 고유한 `memoShapeIDRef`가 없으면 이 값을 씁니다.
- **참조가 비어 있거나 없으면 메모 상자가 연결되지 않습니다**("leaves the memo box unlinked"). 즉 유효한 참조가 있어야 한/글이 메모를 제대로 표시합니다.

한편 메모 본체의 `memoShapeIDRef`는 헤더에 정의된 메모 도형 속성(`<hh:memoPr>`, 모델상 `MemoShape`; `src/hwpx/oxml/header.py`)을 가리킵니다. `document.memo_shape(id)`로 조회할 수 있습니다.

> 표기 주의: 속성 이름은 위치에 따라 다릅니다. 메모 본체 요소의 속성은 소문자 `memoShapeIDRef`이고, MEMO 필드 파라미터의 이름은 대문자 `MemoShapeIDRef`입니다. 코드가 둘을 구분해 씁니다.

## 고수준 API

이 세 조각을 손으로 맞추지 않도록, 라이브러리는 앵커 기반 API를 제공합니다.

- `document.add_memo(text, memo_shape_id_ref=...)` — 메모 본체만 추가.
- `document.add_memo_with_anchor(text, paragraph=...)` — 메모 본체 생성 + 대상 문단(없으면 새로 생성)에 MEMO 필드를 붙여 **표시까지** 보장(`src/hwpx/_document/memos.py`). 문단을 지정하지 않으면 `anchor_char_pr_id_ref`/`char_pr_id_ref`로 새 문단을 만듭니다.

필드 run의 `charPrIDRef`는 인자 → 문단의 `char_pr_id_ref` → 메모가 추론한 값 → `"0"` 순으로 해결됩니다(`attach_memo_field`).

> 참고: 이 라이브러리의 앵커 API 이름은 `add_memo_with_anchor`입니다. (MCP 서버 쪽에는 `add_memo_by_anchor`라는 도구 이름이 있지만, 그것은 이 라이브러리 함수를 감싼 래퍼입니다.)

## 테스트로 고정된 계약

- `tests/test_memo_and_style_editing.py::test_attach_memo_field_inserts_control_runs` — 파라미터 개수, `MemoShapeIDRef`가 메모의 참조와 일치, 그리고 (회귀 방지) 필드 subList가 **id가 아니라 코멘트 텍스트**를 담는지 검증.
- 같은 파일의 `test_section_memo_parsing_exposes_text_and_shape`, `test_document_add_edit_and_remove_memos`, `test_add_memo_with_anchor_roundtrips_on_real_document` — 파싱·추가·편집·삭제·왕복.
- `tests/test_oxml_parsing.py` — 헤더의 `<hh:memoPr>` 파싱과 id 정규화 조회(`memo_shape("07") == shapes["7"]`).

## 실전 요약

- 메모를 "보이게" 하려면 세 조각이 다 필요합니다: 본체(`<hp:memo>` + `paraList` 본문), 본문의 MEMO 필드(`fieldBegin`/`fieldEnd`), 그리고 둘을 잇는 유효한 `MemoShapeIDRef`.
- 여백 풍선에 뜨는 텍스트는 **MEMO 필드의 `subList`** 에서 옵니다. 여기에 텍스트가 아닌 값을 넣으면 엉뚱한 내용이 표시됩니다.
- 참조가 비면 상자가 연결되지 않습니다. 고유 도형이 없으면 `65535`(기본 도형)를 쓰세요.
- 직접 XML을 조립하지 말고 `add_memo_with_anchor`를 쓰면 이 배선이 자동입니다.
