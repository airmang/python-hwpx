# 목차 필드(TABLEOFCONTENTS)와 dirty="1"

한/글의 자동 목차는 `<hp:fieldBegin type="TABLEOFCONTENTS">` 필드로 표현됩니다. 이 필드에 대해 "언제 페이지 번호가 다시 계산되는가"는 자동화 환경에서 특히 중요합니다 — 메뉴 없이 목차를 갱신할 방법이 딱 하나뿐이기 때문입니다. 이 문서는 `dirty="1"` 플래그의 실제 동작과 그 한계를 설명합니다.

## 목차 필드의 구조

이 라이브러리는 한/글이 직접 저장한 문서를 리버스 엔지니어링해 목차 필드 계약을 재현합니다(`src/hwpx/tools/toc_author.py`). 골자는:

- `<hp:fieldBegin type="TABLEOFCONTENTS">`가 `TableOfContents:set:...` Command 문자열과 함께 목차 영역을 엽니다.
- 각 목차 항목은 HYPERLINK 필드로, 하나의 `<hp:t>` 안에 "제목텍스트 + 점선(dot-leader) `<hp:tab>` + 쪽번호" 형태를 담습니다. 쪽번호는 중첩된 `hp:tab`의 tail에 들어갑니다.
- 항목의 앵커는 대상 문단의 `id` 속성입니다. 따라서 목차가 가리키는 제목 문단은 **문서 전체에서 유일한 id**를 가져야 합니다(`ensure_paragraph_anchor_id`가 이를 보장). 한/글이 새로 생성한 문단은 상수 id `2147483648`을 공유하는 경우가 있어 앵커로는 쓸 수 없습니다(`src/hwpx/tools/toc_fidelity.py`의 `NON_UNIQUE_PARA_ID`).

## dirty="1"이 하는 일

라이브러리가 목차를 삽입할 때(`add_native_toc`), 항목의 쪽번호는 **naive한 추정치**로 채워집니다. 라이브러리는 한/글이 아니므로 실제 페이지네이션을 알 수 없습니다. 대신 필드에 `dirty="1"`을 세팅합니다.

**실제 한/글에서 확인된 동작**: `dirty="1"`인 TABLEOFCONTENTS 필드는 한/글이 **문서를 여는 시점에** 통째로 재생성됩니다 — 항목, 스타일, 쪽번호 전부를 한/글이 직접 계산합니다. `src/hwpx/visual/oracle.py`의 `refresh_document` 주석이 이 트리거를 기록합니다:

> The measured native-TOC re-number trigger: a `dirty="1"` TABLEOFCONTENTS is rebuilt on open — Hancom itself computes entries and page numbers — and CROSSREF caches recompute automatically.

`src/hwpx/tools/toc_author.py`의 `mark_toc_dirty()`가 바로 이 용도입니다: 모든 TABLEOFCONTENTS 필드에 `dirty="1"`을 세팅해, 다음 열기 때 한/글이 재계산하도록 만듭니다. 페이지네이션을 바꾸는 편집 후 호출합니다.

```python
def mark_toc_dirty(doc: HwpxDocument) -> int:
    """Set dirty="1" on every TABLEOFCONTENTS field — the measured
    re-number trigger: Hancom regenerates a dirty TOC (entries, styles, page
    numbers) when it next opens the document."""
```

결과적으로, 사용자가 파일을 처음 열었을 때 보는 목차는 **한/글이 스스로 계산한** 목차입니다. 라이브러리의 추정 쪽번호가 아니라.

## 왜 이것이 유일하게 신뢰할 수 있는 갱신 경로인가

한/글 데스크톱에서는 목차를 우클릭해 "차례 새로 고침"으로 갱신할 수 있습니다. 하지만 **메뉴가 없는 자동화 환경**(서버, CI, 헤드리스 파이프라인)에서는 그 UI 조작이 불가능합니다. 남는 것은 XML에 `dirty="1"`을 심어 두고, 한/글이 문서를 여는 순간 재계산에 맡기는 방법뿐입니다.

이 프로젝트의 렌더 오라클은 정확히 이 경로를 활용합니다 — `refresh_document`는 문서를 열어 dirty 필드가 재생성되게 하고, 제자리 저장 후 닫습니다. 한 가지 실측된 함정: **재생성 중인 세션에서 곧바로 PDF export를 시도하면 이 한/글 빌드가 크래시**합니다(잘린 PDF 후 프로세스 사망). 그래서 refresh와 render는 의도적으로 별개의 세션으로 분리됩니다.

## 중요한 한계: dirty는 "신선도 표시"가 아니다

`dirty="1"`은 **재계산 트리거**이지, 캐시된 쪽번호가 맞는지 틀린지를 알려주는 **신선도(staleness) 표시가 아닙니다**. `src/hwpx/tools/toc_fidelity.py`가 이 구분을 명확히 합니다:

> the TOC block only recomputes after an explicit 차례 새로 고침 — so `dirty` is NOT a reliable staleness marker and the only honest verdict comes from comparing cached page numbers against rendered ones (Hancom render -> fitz words).

즉:

- 파일 안의 목차 쪽번호를 보고 "dirty가 꺼져 있으니 맞다"고 단정할 수 없습니다. 한/글이 실제로 다시 열어 재계산하기 전까지는, 그 숫자는 그저 캐시일 뿐입니다.
- 목차 쪽번호가 정말 맞는지 **정직하게 검증**하려면, 한/글로 렌더한 뒤 실제 렌더된 쪽번호와 캐시 값을 비교해야 합니다(`toc_fidelity`가 하는 일). 오라클이 없으면 이 검사는 구조 검증(`render_checked=False`)으로 낮춰지며, 통과로 위장하지 않습니다.

## CROSSREF는 다르다

같은 필드 계열이지만 페이지 상호참조(`<hp:fieldBegin type="CROSSREF">`)는 동작이 다릅니다. **실제 한/글에서 확인된 동작**: CROSSREF 캐시는 편집/저장 시 **자동으로** 재계산됩니다(`src/hwpx/tools/toc_fidelity.py`·`toc_author.py`에 measured로 기록). 목차 블록처럼 명시적 재생성 트리거가 필요하지 않습니다.

## 실전 요약

- 목차를 삽입/편집한 뒤에는 `mark_toc_dirty()`(또는 `dirty=True`)로 TABLEOFCONTENTS 필드를 dirty 상태로 남기세요. 한/글이 다음 열기 때 쪽번호까지 재계산합니다.
- 라이브러리가 채운 쪽번호는 추정치입니다. 최종 값은 한/글이 만듭니다.
- 목차 정합을 **검증**하려면 한/글 렌더와 비교하세요. `dirty` 값만으로 신선도를 판단하지 마세요.
- 목차가 가리키는 제목 문단은 유일한 `id`를 가져야 합니다(상수 id `2147483648`은 앵커로 부적합).
