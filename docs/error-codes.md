# 오류 코드 (`HwpxError.code`)

`python-hwpx` 의 구조화 예외는 사람이 읽는 문장(`message`) 위에 기계가 읽는
세 필드를 얹는다 — `code`, `context`, `suggestion`. 호출자는 **`code` 로
분기**하면 되고, 그 문자열은 계약이라 **major 경계에서만** 바뀐다.

```python
from hwpx import HwpxDocument
from hwpx.errors import HwpxError

document = HwpxDocument.new()
try:
    document.add_paragraph("본문", style="개요1")
except HwpxError as exc:
    if exc.code == "style-not-found":
        print(exc.context["closest"])   # ['개요 1', '개요 10']
        print(exc.suggestion)           # 가장 가까운 이름: '개요 1' ...
```

5.x 코드는 그대로 돌아간다. typed 예외는 자기가 대체한 builtin 을 함께
상속하므로 `except ValueError` 가 여전히 잡는다.

## 두 어휘는 통합하지 않는다

이 문서의 코드는 **kebab-case** 이고 `HwpxError.code` 에만 쓰인다.
`hwpx.quality.report` 에는 **SCREAMING_SNAKE** 코드가 따로 있다.

| | `HwpxError.code` | `QualityError.code` |
|---|---|---|
| 형태 | `style-not-found` | `VISUAL_COMPLETE_FAILED` |
| 쓰임 | 예외 분기 | **발행된 영수증 스키마의 필드값** |
| 관리 | major 경계 | 영수증 스키마 버전 |
| 개수 | 122 | 11 |

통합하지 않는 이유: quality 코드는 `hwpx.mutation-report/v1` 과
`VisualCompleteReport` 에 이미 실려 나간 값이다. 이름을 바꾸면 영수증을 읽는
쪽이 깨지고, 그건 이 라인이 막 복구한 영수증 무결성을 다시 흔드는 일이다.

**둘이 만나는 곳은 한 군데뿐이다** — 품질 게이트가 저장을 막으면
`hwpx._document.persistence` 가 그것을 `quality-gate-failed` 로 감싸고,
원래의 SCREAMING_SNAKE 코드는 `context` 에 담아 보낸다.

## 형식

`<도메인>-<조건>`, 전부 소문자 kebab-case. 도메인은 6.0 네임스페이스와
패키지 수준 관심사에서 온다:

`capability`, `contract`, `document`, `field`, `header`, `heading`, `hwpx`, `master`, `media`, `note`, `open`, `package`, `page`, `paragraph`, `parts`, `plan`, `preservation`, `quality`, `ref`, `save`, `section`, `shape`, `style`, `table`, `text`, `track`

유예 2건 — `unknown-contract-document`, `unknown-contract-schema` —
은 5.6.0 에 이미 나간 이름이라 문법에 맞지 않아도 바꾸지 않는다(7.0 정리).

## 전체 목록

이 표는 `hwpx.errors.ERROR_CODES` 에서 **생성**된다. 레지스트리가 정본이고
문서가 사본이다 — 문서끼리 대조하는 가드는 "양쪽에 다 없으면 통과"하므로,
문서를 코드에서 유도하는 쪽이 옳다.


### `contract-*`

| 코드 | 뜻 |
|---|---|
| `contract-document-missing` | 동봉돼야 할 계약 문서가 휠에 없다. |

### `document-*`

| 코드 | 뜻 |
|---|---|
| `document-header-missing` | 문서에 header.xml 파트가 없다. |
| `document-history-root-invalid` | history.xml 루트가 history 가 아니다. |
| `document-master-page-root-invalid` | 바탕쪽 파트 루트가 masterPage 가 아니다. |
| `document-merge-index-out-of-range` | after_paragraph_index 가 대상 섹션의 문단 개수 범위를 벗어났다. |
| `document-merge-unsupported-policy-axis` | 그 정책 축의 값이 아직 지원 기본값 밖이다(신규 값 미구현). |
| `document-merge-unsupported-reference` | 가져올 문단이 아직 지원 안 하는 참조 요소를 담고 있다(예: 메모 필드). |
| `document-settings-root-invalid` | settings.xml 루트가 ha:HWPApplicationSetting이 아니다. |
| `document-validation-failed` | 저장 전 문서 검증이 실패했다. |
| `document-version-root-invalid` | version.xml 루트가 HCFVersion 이 아니다. |

### `field-*`

| 코드 | 뜻 |
|---|---|
| `field-ambiguous` | 선택자가 누름틀 여럿에 걸린다. |
| `field-checkbox-ambiguous` | 선택자가 체크박스 여럿에 걸린다. |
| `field-checkbox-caption-empty` | 체크박스 캡션이 비어 있다. |
| `field-checkbox-not-created` | 만든 체크박스를 표준 리더가 다시 찾지 못했다. |
| `field-checkbox-not-found` | 그 선택자로 체크박스를 찾지 못했다. |
| `field-date-format-unsupported` | 날짜/시간 필드 date_format 값이 실증된 어휘(단일 관측값) 밖이다. |
| `field-fit-failed` | 값이 FitPolicy 하에서 필드 상자에 들어가지 않는다(측정치·재시도 제안 동봉). |
| `field-name-empty` | 누름틀 이름이 비어 있다. |
| `field-not-created` | 만든 누름틀을 표준 매처가 다시 찾지 못했다. |
| `field-not-found` | 그 선택자로 누름틀을 찾지 못했다. |
| `field-path-format-unsupported` | 파일 이름 필드 path_format 값이 실증된 어휘(단일 관측값) 밖이다. |
| `field-proofreading-mark-unsupported` | 교정 부호 mark 값이 $RevisionSign 인덱스가 확인된 어휘 밖이다. |
| `field-selector-conflict` | 선택자를 둘 이상 동시에 지정했다. |

### `header-*`

| 코드 | 뜻 |
|---|---|
| `header-compat-empty-flag-name` | layout compatibility 플래그 이름이 비어 있다. |
| `header-compat-empty-target-program` | target_program 값이 비어 있다. |

### `heading-*`

| 코드 | 뜻 |
|---|---|
| `heading-level-invalid` | 개요 수준이 정수가 아니다. |
| `heading-level-out-of-range` | 개요 수준이 1~10 밖이다. |
| `heading-style-missing` | 이 문서에 해당 수준의 개요 스타일이 없다. |

### `hwpx-*`

| 코드 | 뜻 |
|---|---|
| `hwpx-error` | 분류되지 않은 구조화 오류(베이스 기본값). |
| `hwpx-lookup-error` | 이름·인덱스로 지목한 것이 없다(분류되지 않음). |
| `hwpx-state-error` | 문서 상태가 이 연산을 할 수 있는 상태가 아니다(분류되지 않음). |
| `hwpx-type-error` | 인자 타입이 이 연산이 받는 것이 아니다(분류되지 않음). |
| `hwpx-value-error` | 인자 값이 이 연산에 쓸 수 없다(분류되지 않음). |

### `master-*`

| 코드 | 뜻 |
|---|---|
| `master-page-manifest-missing` | content.hpf 매니페스트에 opf:manifest 요소가 없다. |
| `master-page-type-unsupported` | 바탕쪽 type 값이 OWPML 어휘(BOTH/EVEN/ODD/LAST_PAGE/OPTIONAL_PAGE) 밖이다. |

### `media-*`

| 코드 | 뜻 |
|---|---|
| `media-item-id-taken` | 그 이진 항목 id 가 이미 쓰이고 있다. |
| `media-owner-paragraph-missing` | 교체한 그림 요소가 소속 문단을 찾지 못했다(방어적 분기). |

### `note-*`

| 코드 | 뜻 |
|---|---|
| `note-anchor-detached` | 앵커를 걸 문단이 섹션에 속해 있지 않다. |
| `note-argument-conflict` | 앵커 없는 메모에 앵커 전용 인자를 줬다. |
| `note-memo-detached` | 메모가 섹션에 속해 있지 않다. |

### `open-*`

| 코드 | 뜻 |
|---|---|
| `open-safety-failed` | 산출 패키지가 편집기 열기 안전성 검사를 통과하지 못했다. |

### `page-*`

| 코드 | 뜻 |
|---|---|
| `page-argument-conflict` | text 와 content 를 동시에 지정했다. |
| `page-argument-missing` | text 또는 content 중 하나는 있어야 한다. |
| `page-columns-invalid` | 단 수는 1 이상이어야 한다. |
| `page-kind-invalid` | kind 는 'header' 또는 'footer' 여야 한다. |
| `page-new-num-kind-invalid` | 쪽번호 재시작 kind 값이 OWPML 어휘(hp:AutoNumNewNumType/@numType) 밖이다. |
| `page-orientation-unsupported` | 지원하지 않는 용지 방향이다. |
| `page-paper-size-unsupported` | 지원하지 않는 용지 규격이다. |
| `page-text-direction-unsupported` | 글자 방향 값이 OWPML 어휘(hp:secPr/@textDirection: HORIZONTAL/VERTICAL/VERTICALALL) 밖이다. |

### `paragraph-*`

| 코드 | 뜻 |
|---|---|
| `paragraph-argument-conflict` | paragraph_index 와 paragraph_indexes 를 동시에 지정했다. |
| `paragraph-format-empty` | 적용할 문단 서식 항목이 하나도 없다. |
| `paragraph-indexes-empty` | paragraph_indexes 가 비어 있다. |
| `paragraph-invalid-type` | paragraph 인자가 정수도 문단 객체도 아니다. |
| `paragraph-line-spacing-invalid` | 줄 간격은 양수여야 한다. |
| `paragraph-missing` | 문서(또는 지정 범위)에 문단이 하나도 없다. |
| `paragraph-not-found` | 문단 인덱스가 범위를 벗어났다. |
| `paragraph-outline-level-out-of-range` | 문단 개요 수준이 0~10 밖이다. |
| `paragraph-tab-leader-invalid` | 탭 정지 leader 값이 OWPML 어휘(hc:LineType2) 밖이다. |
| `paragraph-tab-pos-invalid` | 탭 정지 위치(pos_mm/pos)가 없거나 음수다. |
| `paragraph-tab-type-invalid` | 탭 정지 type 값이 OWPML 어휘(LEFT/RIGHT/CENTER/DECIMAL) 밖이다. |

### `parts-*`

| 코드 | 뜻 |
|---|---|
| `parts-auto-spacing-unknown-para-pr` | 그 id 의 hh:paraPr 를 문서에서 찾지 못했다. |
| `parts-no-header-part` | 문서에 header.xml 파트가 없다(doc.parts 경로). |

### `plan-*`

| 코드 | 뜻 |
|---|---|
| `plan-invalid` | 편집 계획이 v1 계약을 위반한다. |

### `preservation-*`

| 코드 | 뜻 |
|---|---|
| `preservation-downgrade` | 요청한 보존 등급을 저장이 달성하지 못했다. |

### `quality-*`

| 코드 | 뜻 |
|---|---|
| `quality-gate-failed` | 품질 게이트가 저장을 막았다(quality 코드는 context 에). |

### `save-*`

| 코드 | 뜻 |
|---|---|
| `save-failed` | 저장 경로가 아무것도 쓰기 전에 fail-closed 했다. |
| `save-package-contract-violated` | package.save(None) 이 bytes 를 돌려주지 않았다. |

### `section-*`

| 코드 | 뜻 |
|---|---|
| `section-argument-conflict` | section 과 section_index 를 동시에 지정했다. |
| `section-invalid-type` | section 인자가 정수도 섹션 객체도 아니다. |
| `section-missing` | 문서에 섹션이 하나도 없다. |
| `section-not-found` | 섹션 인덱스가 범위를 벗어났다. |

### `shape-*`

| 코드 | 뜻 |
|---|---|
| `shape-arc-corner-invalid` | add_arc 의 corner 인자가 지원하는 모서리(TOP_LEFT 등) 밖이다. |
| `shape-arc-type-invalid` | add_arc 의 arc_type 인자가 OWPML 어휘(NORMAL/PIE/CHORD) 밖이다. |
| `shape-caption-side-invalid` | 캡션 side 값이 OWPML 어휘(LEFT/RIGHT/TOP/BOTTOM) 밖이다. |
| `shape-chart-anchor-detached` | 만든 차트 앵커가 자기 파트를 가리키지 않는다. |
| `shape-chart-not-created` | 만든 차트를 표준 스캔이 다시 찾지 못했다. |
| `shape-chart-root-invalid` | 차트 XML 루트가 c:chartSpace 가 아니다. |
| `shape-chart-xml-empty` | 차트 XML 이 비어 있다. |
| `shape-chart-xml-malformed` | 차트 XML 이 올바른 XML 이 아니다. |
| `shape-container-no-members` | add_container 에 부재를 하나도 안 줬다. |
| `shape-drop-cap-anchor-detached` | 만든 드롭캡이 요청한 dropcapstyle 을 안 갖고 있다(방어적 분기). |
| `shape-drop-cap-character-empty` | 드롭캡으로 키울 문자가 비어 있다. |
| `shape-drop-cap-not-created` | 만든 드롭캡을 표준 섹션 스캔이 다시 찾지 못했다. |
| `shape-drop-cap-style-unsupported` | 드롭캡 dropcapstyle 값이 실증된 어휘(TripleLine) 밖이다. |
| `shape-equation-not-created` | 만든 수식을 표준 스캔이 다시 찾지 못했다. |
| `shape-equation-not-verbatim` | 만든 수식이 스크립트를 그대로 담지 않았다. |
| `shape-equation-script-empty` | 수식 스크립트가 비어 있다. |
| `shape-equation-script-too-large` | 수식 스크립트가 크기 한도를 넘었다. |
| `shape-polygon-too-few-points` | add_polygon 에 꼭짓점을 3개 미만으로 줬다. |

### `style-*`

| 코드 | 뜻 |
|---|---|
| `style-ambiguous` | 같은 이름을 쓰는 스타일이 둘 이상이다(후보 동봉). |
| `style-argument-conflict` | style 과 style_id_ref 를 동시에 지정했다. |
| `style-border-fill-conflict` | fill_color/fill_image/fill_gradient 를 둘 이상 동시에 지정했다. |
| `style-border-fill-gradient-colors-invalid` | fill_gradient 의 colors 가 2개 미만이다. |
| `style-border-fill-gradient-type-invalid` | fill_gradient 의 type 값이 OWPML 어휘(LINEAR/RADIAL/CONICAL/SQUARE) 밖이다. |
| `style-border-fill-image-effect-invalid` | fill_image 의 effect 값이 OWPML 어휘(REAL_PIC/GRAY_SCALE/BLACK_WHITE) 밖이다. |
| `style-border-fill-image-missing` | fill_image 가 doc.media 이진 항목을 가리키지 않는다. |
| `style-border-fill-image-mode-invalid` | fill_image 의 mode 값이 OWPML 어휘(hc:imgBrush/@mode) 밖이다. |
| `style-container-create-failed` | styles 컨테이너를 만들지 못했다(방어적 분기). |
| `style-font-container-create-failed` | fontfaces/fontface 컨테이너를 만들지 못했다. |
| `style-font-face-empty` | face 값이 비어 있다. |
| `style-font-lang-invalid` | lang 값이 OWPML 어휘(HANGUL/LATIN/HANJA/JAPANESE/OTHER/SYMBOL/USER) 밖이다. |
| `style-font-substitute-incomplete` | 대체 글꼴 인자가 일부만 주어졌다(subst_face 가 필요하다). |
| `style-font-type-invalid` | font_type/subst_type 값이 OWPML 어휘(REP/TTF/HFT) 밖이다. |
| `style-list-level-invalid` | 글머리표/번호 수준은 1 이상이어야 한다. |
| `style-list-property-failed` | 번호 문단모양을 만들지 못했다. |
| `style-memo-shape-line-type-invalid` | 메모 모양의 line_type 값이 OWPML 어휘(hc:LineType2) 밖이다. |
| `style-memo-shape-memo-type-invalid` | 메모 모양의 memo_type 값이 OWPML 어휘(NOMAL/USER_INSERT/USER_DELETE/USER_UPDATE) 밖이다. |
| `style-not-found` | 그 id·이름의 스타일이 없다(가용 목록·가장 가까운 이름 동봉). |
| `style-run-outline-type-invalid` | ensure_run 의 outline 값이 OWPML 어휘(hc:LineType1: NONE/SOLID/DOT/THICK/DASH/DASH_DOT/DASH_DOT_DOT) 밖이다. |
| `style-tab-container-create-failed` | tabProperties 컨테이너를 만들지 못했다. |

### `text-*`

| 코드 | 뜻 |
|---|---|
| `text-highlight-color-invalid` | 형광펜 색이 #RRGGBB 6자리 16진 형식이 아니다. |
| `text-highlight-match-crosses-markup` | 찾은 구간이 인라인 마크업을 가로질러 안전하게 감쌀 수 없다. |
| `text-highlight-match-empty` | 형광펜으로 감쌀 문자열이 비어 있다. |
| `text-highlight-match-not-found` | 문단에서 형광펜으로 감쌀 문자열을 찾지 못했다. |
| `text-search-empty` | 바꿀 대상 문자열이 비어 있다. |

### `track-*`

| 코드 | 뜻 |
|---|---|
| `track-match-crosses-markup` | 찾은 구간이 인라인 마크업을 가로질러 안전하게 감쌀 수 없다. |
| `track-match-empty` | 찾을 문자열이 비어 있다. |
| `track-match-not-found` | 문단에서 찾을 문자열을 찾지 못했다. |
| `track-paragraph-empty` | 지울 텍스트가 문단에 없다. |
| `track-text-empty` | 변경추적 삽입 텍스트가 비어 있다. |

### `unknown-*`

| 코드 | 뜻 |
|---|---|
| `unknown-contract-document` | 그런 이름의 계약 문서가 없다. |
| `unknown-contract-schema` | 그런 이름의 계약 스키마가 없다. |
