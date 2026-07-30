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
| `remove_paragraph(p)` | `None` | 섹션의 마지막 단락 삭제 시 `ValueError` | 이미 제거된 문단이면 조용히 무시된다(무해) |
| `add_table(rows, cols)` | `HwpxOxmlTable` | 사실상 없음 | 표가 하나 더 추가된다(비멱등) |
| `table.set_cell_text(r, c, text)` | `FitResult \| None` | 범위 밖 좌표는 `IndexError` (`exceed table bounds`) | 같은 값이면 결과 동일(수렴) |
| `replace_text_in_runs(search, repl)` | `int` (치환 수) | 빈 `search`는 `ValueError` | 치환할 것이 없으면 `0` — 1회차 후 수렴 |
| `add_memo_with_anchor(...)` | `(memo, paragraph, field_id)` 튜플 | 아래 캐비앗 참고 | 메모가 하나 더 붙는다(비멱등) |
| `add_footnote(text, paragraph)` | `HwpxOxmlNote` | 사실상 없음 | 각주가 하나 더 붙는다(비멱등) |

"사실상 없음"은 정상 인자에서 실패 경로가 없다는 뜻이다 — 타입이 어긋난
인자는 여느 파이썬 API처럼 `TypeError` 계열로 즉시 드러난다.

## 저장 의미론

```python
report = document.save_to_path("out.hwpx", return_report=True)
print(report.actual_mode)
```

- `save_to_path()`는 원자적이다: 임시 파일에 쓴 뒤 rename하고, editor-open
  안전 검증을 통과한 결과만 대상 경로를 교체한다.
- 요청한 보존 등급(`mode="patch"` 등)을 지킬 수 없으면
  `PreservationDowngradeError`로 실패하고 **아무것도 쓰지 않는다**
  (fail-closed). 자동 다운그레이드는 없다.
- `return_report=True`는 `MutationReport`를 돌려준다 — 실제 저장 모드,
  손대지 않은 파트의 바이트 보존 검증 결과까지. 스키마와 전체 규칙은
  [안전한 쓰기 계약](safe-write-contract.md).
- **직렬화는 결정론적이다**: 같은 문서 상태에서 `to_bytes()`를 두 번 부르면
  바이트가 동일하다(실측). diff·해시 기반 파이프라인에 안전하다.

## 알아둘 캐비앗 (정직 고지)

- `add_memo_with_anchor(memo_shape_id_ref=...)`는 참조가 실재하는 메모
  모양인지 **검증하지 않고 조용히 수용한다**. 존재하지 않는 ID를 넣으면
  저장은 되지만 편집기 표시가 어긋날 수 있다. `document.memo_shapes`로
  실재 ID를 확인하고 쓰는 것을 권장한다.
- `add_*` 계열은 전부 append 의미론이다. "없으면 추가"가 필요하면 먼저
  {doc}`recipes-traversal`의 순회로 존재 여부를 확인하라.
- 편집은 저장 전까지 메모리에만 있다. 저장 경로가 곧 커밋이다.

## 다음 단계

- 문서에서 원하는 것을 꺼내는 법 → {doc}`recipes-traversal`
- 보존 등급·영수증 스키마 → [안전한 쓰기 계약](safe-write-contract.md)
- 표면 안정성 구분(stable/experimental) → [stable API](stable-api.md)
