# hp:linesegarray — 조판(줄나눔) 캐시

`hp:linesegarray`는 HWPX를 편집할 때 가장 조용히, 그러나 확실하게 문서를 깨뜨릴 수 있는 요소입니다. 텍스트를 고친 뒤 이 캐시를 방치하면 한/글 렌더에서 **글자가 겹쳐** 보입니다. 이 문서는 그것이 무엇이고, 언제 stale이 되며, 이 라이브러리가 어떻게 처리하는지 설명합니다.

## 무엇인가

`<hp:linesegarray>`는 문단(`<hp:p>`) 안에 들어가는 **조판 결과 캐시**입니다. 자식으로 `<hp:lineseg>` 요소들을 가지며, 각 `lineseg`는 한 줄의 세로 위치·높이·베이스라인·시작 텍스트 위치(`textpos`)·가로 위치/크기 등 한/글이 **저장 시점에 계산해 둔 줄나눔 기하**를 담습니다. 저수준 모델이 이 필드를 전부 표현합니다 — `src/hwpx/oxml/body.py`의 `class LineSeg`(text_pos, vert_pos, vert_size, text_height, baseline, ... 필드)와 `class LineSegArray`(linesegs 리스트).

핵심은 이것이 **의미 있는 콘텐츠가 아니라 파생된 레이아웃 메타데이터**라는 점입니다. `src/hwpx/oxml/section_story.py`의 주석이 이를 명확히 합니다:

> A cached `lineSegArray` is layout metadata and may be discarded after a text edit; every other child is semantic content and therefore fails closed before mutation.

즉 텍스트·서식은 지우면 안 되지만, 조판 캐시는 지워도 됩니다. 지우면 한/글이 문서를 열 때 스스로 다시 계산합니다.

## 언제 stale이 되나

`lineseg`의 `textpos`는 "이 줄이 문단 텍스트의 몇 번째 글자에서 시작하는가"를 가리킵니다. 문단의 텍스트 길이를 편집으로 바꾸면, 이전에 캐시된 `textpos` 값들이 새 텍스트와 어긋납니다. 특히 `textpos`가 새 문단의 텍스트 길이를 넘어서면 그 캐시는 명백히 **stale**입니다.

라이브러리는 이 정의를 그대로 검사합니다 — `src/hwpx/tools/package_validator.py`:

```python
if textpos > text_length:
    _error(
        issues,
        part_name,
        f"paragraph {paragraph_index} has stale lineseg textpos={textpos} "
        f"beyond text length {text_length}",
    )
```

`src/hwpx/layout/lint.py`도 같은 조건을 `STALE_LINESEG_DETECTED`로 잡아냅니다(렌더러 없이도 탐지 가능한 하드 에러).

**stale을 남기면 무슨 일이 생기나.** 캐시된 줄 기하는 *옛* 텍스트를 기준으로 하므로, 한/글은 새(더 긴) 텍스트를 옛 줄 슬롯에 밀어 넣어 렌더합니다. 그 결과가 글자 겹침입니다. `src/hwpx/patch.py`의 주석이 이 인과를 못 박아 둡니다:

> Splicing new text into a paragraph invalidates its cached line geometry, so the byte path must drop the cache; otherwise Hangul renders the new text into the stale line slots and overlapping glyphs result.

이 동작은 실제 한컴 렌더 오라클로 확인된 것입니다: 텍스트를 교체한 문단은 줄이 겹치고, 캐시를 제거한 동일 문단은 정상 렌더됩니다.

## 두 가지 전략

편집 후 캐시를 다룰 방법은 두 가지입니다.

1. **지운다 → 한/글이 재계산.** 편집한 문단의 `linesegarray`를 제거하면 한/글이 열 때 그 문단만 다시 조판합니다. 안전하지만, 제거된 바이트만큼 파일이 달라집니다.
2. **보존한다 → 바이트 보존에 유리, 그러나 stale 위험.** 캐시를 그대로 두면 미편집 영역의 바이트가 원본과 동일하게 유지됩니다. 편집한 문단의 캐시까지 남기면 위험합니다.

이 라이브러리의 설계 원칙은 **둘의 조합 — "손댄 문단만" 무효화**입니다. 편집한 문단의 캐시는 지우고(전략 1), 손대지 않은 문단의 캐시는 보존합니다(전략 2).

## 라이브러리의 실제 처리: 문단 단위 스코프 무효화

문서 전체의 캐시를 몽땅 지우는 것이 아니라, **편집한 문단(들)의 캐시만** 지웁니다. 이것이 이 라이브러리에서 가장 중요한 불변식입니다.

편집 진입점마다 스코프 무효화가 걸려 있습니다.

- **바이트 스플라이스 경로** (`src/hwpx/patch.py`): `_strip_paragraph_layout_cache()`가 정규식으로 한 문단의 `<hp:linesegarray>`만 제거하고, 스플라이스한 문단에만 적용합니다. 미편집 span은 캐시까지 원본 바이트 그대로 round-trip됩니다.
- **본문 텍스트 교체** (`src/hwpx/body_patch.py`): `replace_text`가 편집된 문단을 **가장 안쪽 `<hp:p>` 단위**로 묶어 그 블록의 캐시만 제거합니다.
- **표 셀 채움** (`src/hwpx/table_patch.py`): `fill_cells`·`_blank_cell_text`가 채운(또는 비운) 셀 문단의 캐시만 제거하고, 손대지 않은 표는 바이트 동일하게 유지합니다.
- **머리글/바닥글 스토리** (`src/hwpx/oxml/section_story.py`): 텍스트 세터가 대상 문단의 캐시를 `_clear_paragraph_layout_cache()`로 지웁니다(주석: `Clear cached lineseg so Hangul recalculates layout.`).
- **오브젝트 모델 세터** (`src/hwpx/oxml/run.py`, `paragraph.py`, `table.py`): run/문단/셀 텍스트·스타일을 바꾸는 API가 자신이 건드린 문단의 캐시를 그 자리에서 제거합니다.

### 왜 "전부 지우기"가 아니라 "스코프"인가

모델 전체를 재직렬화할 때조차 캐시를 전부 지우지 않고, **명백히 stale한 것만** 정리합니다(안전망). `src/hwpx/oxml/document_parts.py`의 주석이 그 이유를 설명합니다:

> The mutating APIs clear the caches of exactly the paragraphs they touch, so even a dirty section only needs the stale sweep as a safety net. Nuking every cache here forced Hancom to re-lay-out untouched pages of multi-page forms, which is what stacked glyphs and shifted page counts.

즉 **전부 지우기가 오히려 버그**였습니다. 여러 페이지짜리 양식에서 캐시를 통째로 날리면, 한/글이 손대지 않은 페이지까지 재조판하면서 페이지 수가 바뀌고 글자가 겹쳤습니다. 그래서 저장 경계의 sweep은 stale한 것만 제거합니다 — `src/hwpx/opc/package.py`의 `_strip_section_layout_caches`는 `textpos > text length`인 캐시만 지웁니다.

`src/hwpx/oxml/section.py`에는 전량 제거 메서드 `remove_layout_caches()`가 존재하지만, 저장 파이프라인에 연결되어 있지 않습니다. 실제로 배선된 것은 stale-only인 `remove_stale_layout_caches()`뿐입니다.

## 테스트로 고정된 계약

이 동작은 여러 테스트로 못 박혀 있습니다.

- `tests/test_layout_cache_scope.py` — 단일 셀 채움이 "그 셀 문단의 캐시만" 무효화하고 나머지는 보존함을 검증. no-op 저장은 모든 캐시를 보존(`test_noop_save_preserves_every_layout_cache`).
- `tests/test_kordoc_absorption.py::test_byte_preserving_patch_strips_only_patched_paragraph_layout_cache` — 스플라이스가 대상 문단만 제거하고 이웃 문단 캐시는 살아 있음을 검증.
- `tests/test_layout_lint.py`, `tests/test_gap_closure_tools.py` — seeded stale 캐시가 렌더러 없이도 하드 에러/`ValueError`로 잡히는지 검증.
- `tests/test_coverage_promotion.py` — 미편집 문단의 `LineSeg`/`LineSegArray`가 저장·재파싱을 거쳐 손실 없이 round-trip됨을 검증.

## 실전 요약

- HWPX 텍스트를 직접 편집한다면(문자열 치환, XML 조작), **그 문단의 `<hp:linesegarray>`를 반드시 제거**하세요. 안 그러면 한/글에서 글자가 겹칩니다.
- 단, **손대지 않은 문단의 캐시는 남겨 두세요.** 전량 삭제는 미편집 페이지의 재조판을 유발해 페이지 수/레이아웃을 흐트러뜨립니다.
- 이 라이브러리의 고수준·바이트 보존 API를 쓰면 이 처리는 자동입니다. 저수준으로 내려갈 때만 직접 신경 쓰면 됩니다.
