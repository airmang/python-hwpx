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
| 개수 | 355 | 11 |

통합하지 않는 이유: quality 코드는 `hwpx.mutation-report/v1` 과
`VisualCompleteReport` 에 이미 실려 나간 값이다. 이름을 바꾸면 영수증을 읽는
쪽이 깨지고, 그건 이 라인이 막 복구한 영수증 무결성을 다시 흔드는 일이다.

**둘이 만나는 곳은 한 군데뿐이다** — 품질 게이트가 저장을 막으면
`hwpx._document.persistence` 가 그것을 `quality-gate-failed` 로 감싸고,
원래의 SCREAMING_SNAKE 코드는 `context` 에 담아 보낸다.

## 형식

`<도메인>-<조건>`, 전부 소문자 kebab-case. 도메인은 6.0 네임스페이스와
패키지 수준 관심사에서 온다:

`body`, `capability`, `cell`, `contract`, `document`, `equation`, `field`, `header`, `heading`, `hwp5`, `hwpx`, `master`, `media`, `note`, `open`, `package`, `page`, `paragraph`, `parts`, `plan`, `preservation`, `quality`, `recover`, `ref`, `save`, `section`, `shape`, `story`, `style`, `table`, `text`, `toc`, `track`

문법에 맞지 않는 코드는 없다. 7.0 에서 바뀐 코드(`hwpx.errors.RENAMED_CODES`):

- `unknown-contract-document` → `contract-document-unknown`
- `unknown-contract-schema` → `contract-schema-unknown`

## 전체 목록

이 표는 `hwpx.errors.ERROR_CODES` 에서 **생성**된다. 레지스트리가 정본이고
문서가 사본이다 — 문서끼리 대조하는 가드는 "양쪽에 다 없으면 통과"하므로,
문서를 코드에서 유도하는 쪽이 옳다.


### `body-*`

| 코드 | 뜻 |
|---|---|
| `body-op-nested-paragraph` | 본문 op 가 다른 문단(글상자·각주 등)을 품은 문단의 글을 바꾸려 했다(안쪽 글이 지워진다). |
| `body-op-section-settings` | 본문 op 가 구역 설정(hp:secPr)을 담은 문단을 지우거나 복제하거나 자리를 옮기려 했다(구역마다 하나, 첫 문단에 있어야 한다). |

### `cell-*`

| 코드 | 뜻 |
|---|---|
| `cell-border-edit-unsupported` | 셀 테두리 편집 대상 스타일이 없거나 모호하거나 네 변이 온전하지 않다(또는 색·선 종류가 잘못됐다). |
| `cell-margin-value` | 셀 여백 값이 0 이상 2**31 미만의 int(HWPUNIT)가 아니다(bool 도 거부). |

### `contract-*`

| 코드 | 뜻 |
|---|---|
| `contract-document-missing` | 동봉돼야 할 계약 문서가 휠에 없다. |
| `contract-document-unknown` | 그런 이름의 계약 문서가 없다(6.x 의 unknown-contract-document). |
| `contract-schema-unknown` | 그런 이름의 계약 스키마가 없다(6.x 의 unknown-contract-schema). |

### `document-*`

| 코드 | 뜻 |
|---|---|
| `document-caret-place-unsupported` | 캐럿을 본문 밖 문단(표 칸·글상자·각주)에 두려 했거나, 한/글의 자리 셈을 모르는 것이 든 문단에 두려 했다. |
| `document-clock-invalid` | new()/open() 의 now 가 datetime 이 아니다. |
| `document-header-missing` | 문서에 header.xml 파트가 없다. |
| `document-history-root-invalid` | history.xml 루트가 history 가 아니다. |
| `document-master-page-root-invalid` | 바탕쪽 파트 루트가 masterPage 가 아니다. |
| `document-merge-index-out-of-range` | after_paragraph_index 가 대상 섹션의 문단 개수 범위를 벗어났다. |
| `document-merge-unsupported-policy-axis` | 그 정책 축의 값이 아직 지원 기본값 밖이다(신규 값 미구현). |
| `document-merge-unsupported-reference` | 가져올 문단이 아직 지원 안 하는 참조 요소를 담고 있다(예: 메모 필드). |
| `document-name-moved` | 7.0에서 python-hwpx-automation으로 옮긴 문서 메서드(doc.text.markdown 등 묶음 메서드 8개, export_markdown 등 루트 옛 이름 5개)를 불렀다(새 자리는 context.replacement, 설치는 context.install). |
| `document-name-removed` | 7.0에서 없어지거나 바뀐 6.x 이름(루트 HwpxDocument·묶음·모델·값 형식·모듈의 이름)을 불렀다(새 자리는 context.replacement). |
| `document-seed-invalid` | new()/open() 의 seed 가 정수가 아니다. |
| `document-settings-root-invalid` | settings.xml 루트가 ha:HWPApplicationSetting이 아니다. |
| `document-validation-failed` | 저장 전 문서 검증이 실패했다. |
| `document-version-root-invalid` | version.xml 루트가 HCFVersion 이 아니다. |

### `equation-*`

| 코드 | 뜻 |
|---|---|
| `equation-conversion` | 한글 수식 스크립트와 LaTeX 사이의 변환에 실패했다. |
| `equation-latex-unsupported` | LaTeX 조각이 검증된 명령 집합 밖의 명령을 쓴다. |

### `field-*`

| 코드 | 뜻 |
|---|---|
| `field-ambiguous` | 선택자가 누름틀 여럿에 걸린다. |
| `field-cell-not-found` | 그 이름(과 순번)의 셀 필드(이름 붙은 표 칸)가 없다. |
| `field-char-pr-not-found` | fields.fill 의 char_pr_id_ref 가 문서 머리의 글자 모양(hh:charPr) id 가 아니다. |
| `field-checkbox-ambiguous` | 선택자가 체크박스 여럿에 걸린다. |
| `field-checkbox-caption-empty` | 체크박스 캡션이 비어 있다. |
| `field-checkbox-not-created` | 만든 체크박스를 표준 리더가 다시 찾지 못했다. |
| `field-checkbox-not-found` | 그 선택자로 체크박스를 찾지 못했다. |
| `field-choice-unknown` | 직접 입력할 수 없는 콤보 상자에 그 항목이 없다(combo_box.items 로 항목을 본다). |
| `field-date-format-unsupported` | 날짜/시간 필드 date_format 값이 실증된 어휘(단일 관측값) 밖이다. |
| `field-end-missing` | 누름틀에 끝(fieldEnd)이 없어 바꿀 내용이 없다(한/글도 이런 누름틀은 채우지 않는다). |
| `field-fill-char-shape-conflict` | fields.fill 에 char_pr_id_ref 와 fit 을 함께 줬다(fit 이 값의 글자 모양을 스스로 정한다). |
| `field-fit-failed` | 값이 FitPolicy 하에서 필드 상자에 들어가지 않는다(측정치·재시도 제안 동봉). |
| `field-form-not-created` | 만든 양식 개체(라디오 단추·콤보 상자·입력 상자)를 표준 리더가 다시 찾지 못했다. |
| `field-form-text-value` | 콤보 상자·입력 상자에 넣을 글(text)이 str 가 아니다. |
| `field-mail-merge-empty-name` | 메일 머지 필드 이름이 비어 있다. |
| `field-name-empty` | 누름틀 이름이 비어 있다. |
| `field-not-created` | 만든 누름틀을 표준 매처가 다시 찾지 못했다. |
| `field-not-found` | 그 선택자로 누름틀을 찾지 못했다. |
| `field-path-format-unsupported` | 파일 이름 필드 path_format 값이 실증된 어휘(단일 관측값) 밖이다. |
| `field-proofreading-mark-unsupported` | 교정 부호 mark 값이 $RevisionSign 인덱스가 확인된 어휘 밖이다. |
| `field-radio-caption-empty` | 라디오 단추 캡션(옆에 그리는 글)이 비어 있다. |
| `field-radio-group-value` | 라디오 단추 묶음 이름(group)이 str 가 아니다. |
| `field-selector-conflict` | 선택자를 둘 이상 동시에 지정했다. |
| `field-text-box-not-found` | 그 이름의 글상자 필드가 없다(doc.fields.text_boxes 로 이름을 본다). |

### `header-*`

| 코드 | 뜻 |
|---|---|
| `header-compat-empty-flag-name` | layout compatibility 플래그 이름이 비어 있다. |
| `header-compat-empty-license-mark-type` | 라이선스 표시 mark_type 값이 비어 있다. |
| `header-compat-empty-target-program` | target_program 값이 비어 있다. |

### `heading-*`

| 코드 | 뜻 |
|---|---|
| `heading-level-invalid` | 개요 수준이 정수가 아니다. |
| `heading-level-out-of-range` | 개요 수준이 1~10 밖이다. |
| `heading-style-missing` | 이 문서에 해당 수준의 개요 스타일이 없다. |

### `hwp5-*`

| 코드 | 뜻 |
|---|---|
| `hwp5-damaged` | HWP 5.0 문서의 컨테이너나 레코드가 깨졌다(잘림·범위 밖 섹터·순환·레코드 길이·압축). |
| `hwp5-distribution` | 배포용 HWP 5.0 문서라 본문이 암호화돼 있다. |
| `hwp5-drm` | DRM·인증서로 암호화된 HWP 5.0 문서다. |
| `hwp5-limit-exceeded` | HWP 5.0 입력이 파싱 상한(스트림 크기·레코드 수·디렉터리 수)을 넘는다. |
| `hwp5-not-hwp5` | 복합 파일이지만 HWP 5.0 FileHeader가 없다. |
| `hwp5-overwrite-source` | 문서를 연 원본 .hwp 경로에 .hwp로 덮어쓰려 했다. |
| `hwp5-password` | 암호가 걸린 HWP 5.0 문서다. |
| `hwp5-version-unsupported` | FileHeader의 주 버전이 5가 아니다. |
| `hwp5-write-lossy-source` | 열 때 옮기지 못한 내용이 있는 문서를 .hwp로 쓰려 했다. |
| `hwp5-write-unsupported` | HWP 5.0 작성기가 표현할 수 없는 내용이다. |

### `hwpx-*`

| 코드 | 뜻 |
|---|---|
| `hwpx-argument-removed` | 7.0에서 없어지거나 바뀐 인자(section_index=·style_id_ref=, 메서드마다 이름이 바뀐 키워드, 키워드 전용이 된 위치 인자, 없어진 XML 속성 키워드)를 주었다(새 인자는 context.replacement, 안내는 suggestion). |
| `hwpx-attribute-error` | 그런 이름의 속성·메서드가 없다(분류되지 않음, AttributeError 계열이기도 하다). |
| `hwpx-error` | 분류되지 않은 구조화 오류(베이스 기본값). |
| `hwpx-index-error` | 인덱스가 범위를 벗어났다(분류되지 않음, IndexError 계열이기도 하다). |
| `hwpx-lookup-error` | 이름·인덱스로 지목한 것이 없다(분류되지 않음). |
| `hwpx-state-error` | 문서 상태가 이 연산을 할 수 있는 상태가 아니다(분류되지 않음). |
| `hwpx-type-error` | 인자 타입이 이 연산이 받는 것이 아니다(분류되지 않음). |
| `hwpx-value-error` | 인자 값이 이 연산에 쓸 수 없다(분류되지 않음). |

### `master-*`

| 코드 | 뜻 |
|---|---|
| `master-page-in-use` | 지우려는 바탕쪽을 아직 어떤 절이 참조한다. |
| `master-page-manifest-missing` | content.hpf 매니페스트에 opf:manifest 요소가 없다. |
| `master-page-not-found` | 그 id의 바탕쪽 파트가 문서에 없다. |
| `master-page-pages-taken` | 그 구역에 같은 쪽(종류와 번호)의 바탕쪽이 이미 있다. |
| `master-page-type-unsupported` | 바탕쪽 type 값이 OWPML 어휘(BOTH/EVEN/ODD/LAST_PAGE/OPTIONAL_PAGE) 밖이다. |
| `master-page-unlinked` | 이번에 만든 바탕쪽을 어느 구역에도 잇지 않고 저장하려 했다(한/글은 그 파트를 버린다). |

### `media-*`

| 코드 | 뜻 |
|---|---|
| `media-image-invalid` | 그림 형식 이름을 모르거나, 데이터의 첫 바이트가 그 형식의 그림이 아니다(context.detected). |
| `media-item-id-taken` | 그 이진 항목 id 가 이미 쓰이고 있다. |
| `media-item-in-use` | 지우려는 이진 항목을 문서가 아직 가리킨다(그림·채우기·동영상·OLE 등). force=True 로만 지운다. |
| `media-owner-paragraph-missing` | 교체한 그림 요소가 소속 문단을 찾지 못했다(방어적 분기). |
| `media-picture-not-found` | picture_index 번째 그림이 없다(binaryItemIDRef 로 고른 경우 그 안에서). |

### `note-*`

| 코드 | 뜻 |
|---|---|
| `note-anchor-detached` | 앵커를 걸 문단이 섹션에 속해 있지 않다. |
| `note-argument-conflict` | 앵커 없는 메모에 앵커 전용 인자를 줬다. |
| `note-match-not-found` | 메모를 걸 글(match)이 그 문단의 한 런 안에 없다. |
| `note-memo-anchor-elsewhere` | 메모를 고리(MEMO 누름틀)가 없는 구역으로 옮기려 했다(고리가 다른 구역에 있거나 한/글이 누름틀에 담아 둔 메모). |
| `note-memo-detached` | 메모가 섹션에 속해 있지 않다. |
| `note-memo-index-value` | 메모를 넣을 자리(index)가 int 가 아니거나 0..메모 묶음의 메모 수 밖이다. |
| `note-memo-shape-not-found` | 구역에 줄 메모 모양(hh:memoPr) id 가 머리에 없다. |
| `note-memo-unanchored` | 이번에 만든 메모를 어느 문단에도 걸지 않고 저장하려 했다(한/글은 메모를 MEMO 누름틀 안에만 둔다). |
| `note-other-document-unsupported` | 각주·미주를 다른 문서로 옮기거나 복사하려 했다(그 글 구간을 paragraph.copy_range 로 복사한다). |

### `open-*`

| 코드 | 뜻 |
|---|---|
| `open-archive-damaged` | HWPX(ZIP)가 잘렸거나 압축 데이터가 손상됐다. |
| `open-empty-file` | 연 파일이 비어 있다(0바이트). HwpxArchiveError 에 실린다. |
| `open-encrypted` | 암호가 걸린 HWPX 다(HwpxXmlSyntaxError, lxml 의 숫자 코드는 lxml_code 에). |
| `open-hwp3-unsupported` | HWP 3.x 이하 .hwp 문서다(열지 못한다). |
| `open-hwp5-not-package` | HwpxPackage.open 에 HWP 5.0(.hwp) 파일을 주었다(HwpxDocument.open 으로 연다). |
| `open-input-unsafe` | 입력이 안전한 읽기 한도(ZIP 항목 수·크기·압축률·경로, XML 크기·깊이)를 넘었다(HwpxSecurityError, ValueError 이기도 하다). |
| `open-invalid-type` | HwpxDocument.open 에 경로·bytes·이진 스트림이 아닌 값을 주었다. |
| `open-is-folder` | 문서 파일 대신 폴더 경로를 주었다(IsADirectoryError 이기도 하다). |
| `open-not-hwp` | 확장자가 .hwp 인데 HWP 5.0 복합 파일 머리가 없다. |
| `open-not-hwpx` | 연 파일이 HWPX 가 아니다(ZIP 이 아닌 텍스트·다른 형식, 또는 mimetype 없는 ZIP·Office 문서). |
| `open-safety-failed` | 산출 패키지가 편집기 열기 안전성 검사를 통과하지 못했다. |

### `package-*`

| 코드 | 뜻 |
|---|---|
| `package-invalid` | 패키지(HwpxPackage)가 계약을 어겼다(까닭을 따로 가리지 않은 HwpxPackageError 기본값). |
| `package-structure-invalid` | HWPX 패키지 구조가 요구를 어겼다(HwpxStructureError 기본값). |
| `package-text-replacement-key-empty` | 치환할 텍스트(키)가 비어 있다. |
| `package-xml-invalid` | 패키지의 XML 파트가 올바르지 않다(HwpxXmlSyntaxError 기본값, lxml 의 숫자 코드는 lxml_code 에). |

### `page-*`

| 코드 | 뜻 |
|---|---|
| `page-argument-conflict` | text 와 content 를 동시에 지정했다. |
| `page-argument-missing` | text 또는 content 중 하나는 있어야 한다. |
| `page-border-fill-invalid` | 쪽 테두리 page_type·fill_area 가 OWPML 어휘 밖이거나, 오프셋이 0 이상 32767 이하의 int 가 아니다. |
| `page-column-gap-value` | 같은 폭 단의 간격(same_gap)이 0 이상 32767 이하의 int(HWPUNIT)가 아니다(bool 도 거부). |
| `page-column-widths-value` | 단 너비(column_widths)가 0 이상의 int 로 된 (너비, 간격) 쌍이 아니거나 모두 0이다. |
| `page-columns-invalid` | 단 수는 1 이상이어야 한다. |
| `page-gutter-type-invalid` | 제본 방식(gutter_type)이 OWPML 어휘(LEFT_ONLY/LEFT_RIGHT/TOP_BOTTOM) 밖이다(한/글은 LEFT_ONLY 로 읽는다). |
| `page-kind-invalid` | kind 는 'header' 또는 'footer' 여야 한다. |
| `page-new-num-kind-invalid` | 쪽번호 재시작 kind 값이 OWPML 어휘(hp:AutoNumNewNumType/@numType) 밖이다. |
| `page-new-num-value` | 새 번호(hp:newNum/@num)가 0 이상 65535 이하가 아니다. |
| `page-note-shape-invalid` | 각주·미주 모양의 번호 매기기·놓는 곳·시작 번호·간격·구분선 길이가 한/글이 받는 값이 아니다. |
| `page-number-value` | 줄 번호(시작·간격·거리·재시작)나 구역 시작 번호가 한/글이 두는 범위(16비트 번호, 32비트 거리) 밖이다. |
| `page-orientation-unsupported` | 지원하지 않는 용지 방향이다. |
| `page-paper-size-unsupported` | 지원하지 않는 용지 규격이다. |
| `page-section-all-invalid` | doc.page 의 section='all' 에 한 구역에만 있는 문단을 함께 줬다. |
| `page-size-value` | 쪽 크기·여백이 0 이상 2**31 미만의 int(HWPUNIT)가 아니다(bool 도 거부, 음수는 0으로 쓰였다). |
| `page-start-numbers-invalid` | 구역 시작 번호의 page_starts_on 이 BOTH·EVEN·ODD 가 아니다. |
| `page-text-direction-unsupported` | 글자 방향 값이 OWPML 어휘(hp:secPr/@textDirection: HORIZONTAL/VERTICAL/VERTICALALL) 밖이다. |

### `paragraph-*`

| 코드 | 뜻 |
|---|---|
| `paragraph-alignment-invalid` | 문단 정렬 값이 LEFT/CENTER/RIGHT/JUSTIFY/DISTRIBUTE/DISTRIBUTE_SPACE 밖이다. |
| `paragraph-argument-conflict` | paragraph_index·paragraph_indexes·paragraphs 중 둘 이상을 동시에 지정했다. |
| `paragraph-border-invalid` | 문단 테두리(border) 지정에 모르는 키·면이 있거나 여백이 네 개의 0 이상 수가 아니다. |
| `paragraph-format-empty` | 적용할 문단 서식 항목이 하나도 없다. |
| `paragraph-format-invalid` | 문단 서식 값의 형이 틀렸거나 범위 밖이다(여백·간격은 수, 간격은 음수 불가, 줄 나눔 기준·condense 어휘). |
| `paragraph-index-mark-empty-key` | 찾아보기 표시의 first/second 키가 빈 문자열이다. |
| `paragraph-index-mark-no-text-run` | 문단에 hp:t를 가진 run이 없어 indexmark를 넣을 자리가 없다. |
| `paragraph-indexes-empty` | paragraph_indexes 또는 paragraphs 가 비어 있다. |
| `paragraph-invalid-type` | paragraph 인자가 정수도 문단 객체도 아니다. |
| `paragraph-line-spacing-invalid` | 줄 간격은 양수여야 한다. |
| `paragraph-missing` | 문서(또는 지정 범위)에 문단이 하나도 없다. |
| `paragraph-mixed-text-unsupported` | hp:t 안에 인라인 마크업이 섞여 있어 안전하게 고칠 수 없다. |
| `paragraph-move-into-itself` | 문단을 자기 안(그 문단의 표 칸·글상자·각주)으로 옮기려 했다. |
| `paragraph-move-place-unsupported` | 메모의 문단을 옮기거나 문단을 메모 안으로 옮기려 했다(메모 글은 memo.text 로 고친다). |
| `paragraph-not-found` | 문단 인덱스가 범위를 벗어났다. |
| `paragraph-not-in-document` | 넘긴 문단 객체가 이 문서에 속해 있지 않다(다른 문서의 문단이거나 지운 문단). |
| `paragraph-outline-level-out-of-range` | 문단 개요 수준이 0~10 밖이다. |
| `paragraph-range-crosses-element` | 바꿀 글자 범위가 한 덩이 글이 아니다(탭·줄 바꿈·컨트롤·개체가 끼어 있다). |
| `paragraph-range-holds-objects` | 지울 글자 범위 안에 컨트롤·개체(각주·책갈피·누름틀·표·그림 …)가 있다(objects='remove' 로 함께 지운다. 범위 양 끝의 것은 남는다). |
| `paragraph-range-into-itself` | 글자 범위를 그 범위 안 자리나, 범위가 품은 표 칸·글상자·각주 안으로 옮기려 했다. |
| `paragraph-range-invalid` | 글자 위치(start·end·offset)가 int 가 아니거나 paragraph.text 범위 밖이다. |
| `paragraph-range-splits-field` | 글자 범위가 누름틀·하이퍼링크 같은 필드의 시작이나 끝 한쪽만 품는다. |
| `paragraph-range-splits-mark` | 글자 범위가 변경 추적 표시를 품거나, 형광펜 끝을 런 바로 아래 탭에 두어야 한다. |
| `paragraph-remove-last` | 구역·셀·머리말·꼬리말의 마지막 문단은 지울 수 없다(담은 곳은 context.container). |
| `paragraph-remove-section-settings` | 구역 설정(hp:secPr·단·머리말·꼬리말·쪽 번호)을 담은 문단 뒤에 옮겨 받을 문단이 없어 지울 수 없다. |
| `paragraph-run-section-settings` | 구역 설정(hp:secPr·단·머리말·꼬리말·쪽 번호)만 담은 run은 지울 수 없다. |
| `paragraph-split-inside-element` | 나눌 위치가 hp:t 안의 나눌 수 없는 요소(글자를 가진 요소) 한가운데다. |
| `paragraph-style-char-type` | 문단에 글자 스타일(type CHAR)을 적용하려 했다. |
| `paragraph-tab-leader-invalid` | 탭 정지 leader 값이 OWPML 어휘(hc:LineType2) 밖이다. |
| `paragraph-tab-pos-invalid` | 탭 정지 위치(pos_mm/pos)가 없거나 음수다. |
| `paragraph-tab-target-required` | 탭 컨트롤이 있는 문단은 고칠 run을 명시해야 한다. |
| `paragraph-tab-type-invalid` | 탭 정지 type 값이 OWPML 어휘(LEFT/RIGHT/CENTER/DECIMAL) 밖이다. |
| `paragraph-tab-widths` | add_run(tab_widths=) 의 폭 개수가 글의 탭 수와 다르거나 폭이 0~2**31-1 정수가 아니다. |
| `paragraph-text-invalid-type` | 문단 글(text)이 문자열이 아니다. |
| `paragraph-text-missing` | 문단에 고칠 일반 텍스트(hp:t) 노드가 없다. |
| `paragraph-text-style-ambiguous` | 텍스트 수정이 run 경계를 넘거나 삽입할 글자 모양이 모호하다. |
| `paragraph-title-mark-no-text-run` | 문단에 hp:t를 가진 run이 없어 titleMark를 넣을 자리가 없다. |

### `parts-*`

| 코드 | 뜻 |
|---|---|
| `parts-auto-spacing-unknown-para-pr` | 그 id 의 hh:paraPr 를 문서에서 찾지 못했다. |
| `parts-begin-numbers-invalid` | 문서 시작 번호(hh:beginNum)가 1 이상 65535 이하의 정수가 아니다. |
| `parts-license-mark-incomplete` | 라이선스 표시가 없는 문서에 license_type·license_flag 를 함께 주지 않고 표시를 쓰려 했다. |
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
| `quality-gate-failed` | 품질 게이트가 저장을 막았다(quality 코드는 context 에, 게이트의 VisualCompleteReport 는 SaveError.report). |

### `recover-*`

| 코드 | 뜻 |
|---|---|
| `recover-unsafe` | 로컬 헤더 항목이 있지만 안전하게 복구할 수 없다. |

### `ref-*`

| 코드 | 뜻 |
|---|---|
| `ref-bookmark-name-empty` | 책갈피 이름이 비어 있다. |
| `ref-cross-reference-content-value` | 상호 참조에 보일 것(content_type)이 OBJECT_TYPE_PAGE·NUMBER·CONTENTS·UPDOWNPOS 밖이다. |
| `ref-cross-reference-hyperlink-value` | 상호 참조 hyperlink 가 True·False 가 아니다. |
| `ref-cross-reference-target-unsupported` | 상호 참조 대상이 이 문서의 개요 문단·책갈피·표가 아니다(한/글 파일에서 본 대상만 쓴다). |
| `ref-link-end-missing` | 하이퍼링크의 끝이 그 문단에 없어 글을 고칠 수 없다. |
| `ref-link-target-empty` | 하이퍼링크 대상이 비어 있다. |

### `save-*`

| 코드 | 뜻 |
|---|---|
| `save-failed` | 저장 경로가 아무것도 쓰기 전에 fail-closed 했다. |
| `save-format-unsupported` | 저장 형식(format)이 'hwpx'도 'hwp'도 아니다. |
| `save-mode-invalid` | 저장 mode 가 auto/patch/rebuild 밖이거나 fallback 이 error/rebuild 밖이다. |
| `save-package-contract-violated` | package.save(None) 이 bytes 를 돌려주지 않았다. |
| `save-pipeline-invalid-type` | doc.save 의 pipeline= 에 SavePipeline 도 None 도 아닌 것을 주었다. |
| `save-target-denied` | 저장할 파일에 쓸 권한이 없다(읽기 전용이거나 다른 프로그램이 열고 있다). |
| `save-target-folder-missing` | 저장할 경로의 상위 폴더가 없다. |
| `save-target-invalid-type` | doc.save 에 경로도 쓰기 가능한 이진 스트림도 아닌 것을 주었다. |
| `save-target-is-folder` | 저장할 경로가 폴더다. |
| `save-target-unwritable` | 저장할 파일을 쓰지 못했다(운영체제 오류, 종류는 context.os_error). |

### `section-*`

| 코드 | 뜻 |
|---|---|
| `section-clear-control-content` | clear_body 가 남길 hp:secPr/hp:ctrl 안에 글·표·개체가 있다(머리말·꼬리말 등, strip 으로도 못 지우는 경우 포함, 태그는 context 에). |
| `section-clear-mode-invalid` | clear_body 의 on_control_content 값이 raise/keep/strip 밖이다. |
| `section-clear-no-section-properties` | 섹션 첫 문단의 첫 run 에 hp:secPr 가 없어 clear_body 가 남길 쪽 설정이 없다. |
| `section-invalid-type` | section 인자가 정수도 섹션 객체도 아니다. |
| `section-missing` | 문서에 섹션이 하나도 없다. |
| `section-not-found` | 섹션 인덱스가 범위를 벗어났다. |
| `section-properties-not-first` | 구역 설정(hp:secPr)이 구역 첫 문단이 아닌 뒤 문단에 있다(한/글은 첫 문단에서만 읽고 구역을 기본 용지·여백으로 바꾼다). |
| `section-remove-last` | 문서의 마지막 섹션은 지울 수 없다. |

### `shape-*`

| 코드 | 뜻 |
|---|---|
| `shape-arc-corner-invalid` | add_arc 의 corner 인자가 지원하는 모서리(TOP_LEFT 등) 밖이다. |
| `shape-arc-type-invalid` | add_arc 의 arc_type 인자가 OWPML 어휘(NORMAL/PIE/CHORD) 밖이다. |
| `shape-caption-gap-value` | 캡션 간격(gap)이 -32768 이상 32767 이하의 int(HWPUNIT)가 아니다(bool 도 거부). |
| `shape-caption-side-invalid` | 캡션 side 값이 OWPML 어휘(LEFT/RIGHT/TOP/BOTTOM) 밖이다. |
| `shape-chart-anchor-detached` | 만든 차트 앵커가 자기 파트를 가리키지 않는다. |
| `shape-chart-axes-missing` | 축이 필요한 차트(막대·꺾은선·영역·분산형·방사형·거품형 등)에 두 축(c:axId와 정의된 축)이 없다(한컴이 빈 차트를 그리거나 멈춘다). |
| `shape-chart-not-created` | 만든 차트를 표준 스캔이 다시 찾지 못했다. |
| `shape-chart-reference-empty` | paragraph.add_chart 의 chart_id_ref(차트 파트 경로)가 비어 있다. |
| `shape-chart-root-invalid` | 차트 XML 루트가 c:chartSpace 가 아니다. |
| `shape-chart-xml-empty` | 차트 XML 이 비어 있다. |
| `shape-chart-xml-malformed` | 차트 XML 이 올바른 XML 이 아니다. |
| `shape-compose-arrangement-value` | 글자 겹치기 방식(arrangement)이 SPREAD·OVERLAP 밖이다. |
| `shape-compose-frame-value` | 글자 겹치기 테두리(frame)가 스키마 어휘(CHAR, SHAPE_CIRCLE …) 밖이다. |
| `shape-compose-text-value` | 글자 겹치기 글자가 빈 문자열이거나 줄 바꿈·탭·제어 문자를 담았다. |
| `shape-connector-frame` | 연결선을 이으려는 두 도형이 같은 기준에서 왼쪽·위로 놓여 있지 않다. |
| `shape-connector-kind-unsupported` | 연결선 모양이 실증된 어휘(STRAIGHT, STROKE) 밖이다(ARC 는 제어점이 필요). |
| `shape-connector-length-zero` | 연결선의 두 끝이 한 점이다(이을 변이나 도형 자리를 바꾼다). |
| `shape-connector-side-invalid` | 연결선 끝의 변이 top/right/bottom/left 밖이다. |
| `shape-connector-target-inline` | 연결선을 이으려는 도형이 글자처럼 놓였거나 instid 가 없다. |
| `shape-container-no-members` | add_container 에 부재를 하나도 안 줬다. |
| `shape-container-picture-image` | 그룹의 그림 부재(ContainerMember.picture)에 그림 이진 항목을 안 줬다. |
| `shape-copy-document-unsupported` | 다른 문서로 그 개체를 옮기거나 복사할 수 없다: 글이 든 개체(글상자·캡션·표)는 한/글이 다른 문서에 붙인 뒤 다시 열지 못했고, 연결선은 도형을 놓아 한/글이 그리지 않는다(문서 끼워 넣기 insert_document 를 쓴다). |
| `shape-curve-too-few-points` | add_curve 에 앵커를 2개(닫으면 3개) 미만으로 줬다. |
| `shape-description-value` | 개체 설명(hp:shapeComment)이 str 이 아니다. |
| `shape-draw-text-vert-align` | 도형 글상자 vert_align 값이 OWPML 어휘(hp:subList/@vertAlign, TOP/CENTER/BOTTOM) 밖이다. |
| `shape-drop-cap-anchor-detached` | 만든 드롭캡이 요청한 dropcapstyle 을 안 갖고 있다(방어적 분기). |
| `shape-drop-cap-character-empty` | 드롭캡으로 키울 문자가 비어 있다. |
| `shape-drop-cap-not-created` | 만든 드롭캡을 표준 섹션 스캔이 다시 찾지 못했다. |
| `shape-drop-cap-style-unsupported` | 드롭캡 dropcapstyle 값이 실증된 어휘(DoubleLine, TripleLine) 밖이다. |
| `shape-equation-base-unit-value` | 수식 글자 크기(font_size)가 0.01 pt 이상의 유한한 pt 수가 아니다(bool 도 거부; 저장 값 baseUnit 은 1/100 pt 정수). |
| `shape-equation-font-empty` | 수식 글꼴(font)이 비어 있거나 문자열이 아니다. |
| `shape-equation-not-created` | 만든 수식을 표준 스캔이 다시 찾지 못했다. |
| `shape-equation-not-verbatim` | 만든 수식이 스크립트를 그대로 담지 않았다. |
| `shape-equation-resize-unsupported` | 수식은 크기를 바꾸지 않는다: 상자는 스크립트와 글자 크기로 정해지고 한/글도 준 크기를 버리고 다시 잰다(한/글에 없는 기능). |
| `shape-equation-script-empty` | 수식 스크립트가 비어 있다. |
| `shape-equation-script-latex` | 수식 스크립트에 LaTeX 명령(\frac 등)이 있다(latex_to_eqedit 로 바꿔 넘긴다). |
| `shape-equation-script-too-large` | 수식 스크립트가 크기 한도를 넘었다. |
| `shape-equation-script-unbalanced` | 수식 스크립트의 중괄호 짝이 맞지 않는다. |
| `shape-flip-unsupported` | 한/글 저장본으로 확인하지 못한 뒤집기다: 사각형·글상자·타원·다각형·선·호·곡선·그림·묶음 밖의 개체(OLE·수식 등), 높이(너비) 0으로 그린 선을 뒤집고 돌린 뒤 다시 뒤집기, 비스듬한 선을 뒤집은 뒤 크기 바꾸기(한/글은 거울을 버리고 표시만 남긴다), 뒤집은 그림 자르기. |
| `shape-flip-value` | 뒤집기(flip_horizontal·flip_vertical)에 bool 이 아닌 값을 주었다. |
| `shape-group-member-unsupported` | 묶음(hp:container) 구성원 하나만은 돌리거나 크기를 바꾸거나 옮길 수 없고(한/글 근거 대기), 설명·바깥 여백은 구성원에 자리가 없다(묶음 단위 속성, 한/글에 없는 기능). 돌았거나 늘인 묶음에서는 혼자 지울 수 없다(묶음째 다루거나 ungroup() 으로 푼다). |
| `shape-move-into-itself` | 개체를 자기 안(글상자·표 칸·캡션)의 문단으로 옮기려 했다(복사는 된다). |
| `shape-move-place-unsupported` | 한/글이 그렇게 두는 근거가 없거나 다시 열지 못한 자리로 옮기거나 복사하려 했다: 표 칸에 문단 기준으로 위로 올라가는 떠 있는 개체(한/글이 다시 열지 못함), 개체를 메모·바탕쪽으로, 떠 있는 표를 칸·글상자·각주·캡션으로(문단 기준·쪽 영역 안이 아니면); context.box·placement·reason. |
| `shape-not-in-document` | 옮기거나 복사할 개체가 문단에 없다(지운 개체). |
| `shape-numbering-type-value` | 개체·표의 numbering_type 이 NONE·PICTURE·TABLE·EQUATION 가운데 하나(대문자, 정확히)가 아니다. |
| `shape-original-size-invalid` | add_rectangle/add_ellipse 의 original_size 가 양의 정수 두 개(HWPUNIT)가 아니다. |
| `shape-out-margin-value` | 개체 바깥 여백(out_margins)이 0 이상 2**31 미만의 int(HWPUNIT)가 아니다(bool 도 거부). |
| `shape-picture-border-value` | 그림 테두리·도형 선 굵기(line_width_mm)가 0 이상의 유한한 mm 수가 아니다(bool 도 거부, 0 은 선 없음; 저장 값은 mm × 283 의 정수 HWPUNIT). |
| `shape-picture-crop-value` | 그림 자르기(crop)가 0 이상의 int 네 개(왼쪽·위·오른쪽·아래, HWPUNIT)가 아니거나 그림을 다 잘라 낸다. |
| `shape-picture-effect-value` | 그림 그림자·빛남 값이 범위 밖이다(투명도 0~1, 그림자 방향 0~359도 int, 흐림·거리·반경·부드러운 가장자리 0 이상 int, 색 #RRGGBB, 반사 크기 0 초과 1 이하, shadow/glow/reflection 은 PictureShadow/PictureGlow/PictureReflection). |
| `shape-picture-image-value` | 그림의 밝기·대비(-100~100)·투명도(alpha, 0~255)가 범위 밖의 int 이거나(bool 도 거부) 효과가 REAL_PIC/GRAY_SCALE/BLACK_WHITE 밖이다. |
| `shape-polygon-too-few-points` | add_polygon 에 꼭짓점을 3개 미만으로 줬다. |
| `shape-position-frame` | 도형 기준 프레임·정렬 값이 OWPML 어휘(hp:pos 의 vertRelTo/horzRelTo/vertAlign/horzAlign) 밖이다. |
| `shape-position-unsupported` | 위치를 바꿀 도형이 떠 있는 개체가 아니거나 hp:pos 가 없다. |
| `shape-position-value` | 도형 오프셋이 signed 32-bit 정수(HWPUNIT)가 아니다. |
| `shape-raw-tag-empty` | 탈출구 add_shape/add_raw 에 줄 태그 이름이 비어 있다. |
| `shape-rect-ratio-value` | 사각형 모서리 곡률(ratio)이 0 이상 2**31 미만의 int(%)가 아니다(bool 도 거부). |
| `shape-rotation-unsupported` | 돌리려는 개체에 hp:rotationInfo 가 없거나(수식·차트 등은 돌지 않는다) 한/글 저장본으로 확인하지 못한 모양이다: 뒤집을 수 없는 종류의 뒤집힌 개체, 행렬이 hp:flip 을 따르지 않는 개체, 혼자 돌았거나 뒤집힌 구성원이 든 묶음, 한/글 개체 속성으로 돈 상자의 크기를 바꿔 기울어진 개체(읽고 그대로 둘 뿐 다시 바꾸지 않는다). 수식·차트는 한/글도 돌리지 않는다(한/글에 없는 기능). 글이 든 도형, 뒤집힌 사각형·타원·다각형·선·그림(늘인 그림 포함)과 뒤집힌 묶음(양쪽·늘인 것 포함), 묶음 전체(늘인 묶음, 묶음 안 묶음, 이미 돈 묶음 포함)는 돌고, 돈 개체의 resize 는 돌리기 전 자기 크기를 받는다. |
| `shape-rotation-value` | 회전 각도가 int(도)가 아니다(bool 도 거부). 음수·360 이상은 한/글처럼 0~359로 바꿔 쓴다(-30 → 330). |
| `shape-ruby-alignment-value` | 덧말 정렬이 Alignment 값(LEFT·CENTER·RIGHT·JUSTIFY·DISTRIBUTE·DISTRIBUTE_SPACE) 밖이다. |
| `shape-ruby-position-value` | 덧말 위치가 TOP(위)·BOTTOM(아래) 밖이다. |
| `shape-ruby-text-value` | 덧말의 본말·덧말 글이 빈 문자열이거나 줄 바꿈·탭·제어 문자를 담았다(덧말을 걷으려면 ruby.remove()). |
| `shape-size-value` | 도형·그림·수식·차트 크기가 0 이상 2**31 미만의 int(HWPUNIT)가 아니다(bool 도 거부). 수식·차트의 size 는 (너비, 높이) 쌍이어야 하고 0일 수 없다. |
| `shape-ungroup-unsupported` | 풀 수 없는 묶음이다: 묶음이 아니거나, 글자처럼 놓였거나 오른쪽·아래·안쪽·바깥쪽 정렬이거나, 한/글 저장본으로 확인하지 못한 꼴(혼자 돌았거나 뒤집힌 구성원, 돈 뒤 늘여 기울어진 묶음)이다; context.reason. |
| `shape-z-order-value` | 개체의 z_order 가 signed 32-bit int 가 아니다(bool 도 거부). |

### `story-*`

| 코드 | 뜻 |
|---|---|
| `story-ambiguous` | 그 쪽 종류·id 에 맞는 머리말/꼬리말 story 가 여럿이거나 식별이 모호하다. |
| `story-linkage` | 기존 머리말/꼬리말 컨트롤과 구역 적용 정보가 서로 맞지 않는다. |
| `story-paragraph-not-here` | 머리말·꼬리말 메서드에 그 머리말·꼬리말에 없는 문단을 줬다. |

### `style-*`

| 코드 | 뜻 |
|---|---|
| `style-ambiguous` | 같은 이름을 쓰는 스타일이 둘 이상이다(후보 동봉). |
| `style-border-base-conflict` | base_border_fill_id 와 함께 sides·fill_color 밖의 테두리 인자를 주었다. |
| `style-border-fill-conflict` | fill_color/fill_image/fill_gradient 를 둘 이상 동시에 지정했다. |
| `style-border-fill-gradient-colors-invalid` | fill_gradient 의 colors 가 2개 미만이다. |
| `style-border-fill-gradient-type-invalid` | fill_gradient 의 type 값이 OWPML 어휘(LINEAR/RADIAL/CONICAL/SQUARE) 밖이다. |
| `style-border-fill-image-effect-invalid` | fill_image 의 effect 값이 OWPML 어휘(REAL_PIC/GRAY_SCALE/BLACK_WHITE) 밖이다. |
| `style-border-fill-image-missing` | fill_image 가 doc.media 이진 항목을 가리키지 않는다. |
| `style-border-fill-image-mode-invalid` | fill_image 의 mode 값이 OWPML 어휘(hc:imgBrush/@mode) 밖이다. |
| `style-border-fill-width-invalid` | hh:borderFill 선의 width 가 '<숫자> mm' 꼴이 아니다(doc.styles.border_fill). |
| `style-border-side-invalid` | ensure_border_fill 의 sides 에 모르는 면이나 type·width·color 밖의 키를 주었다. |
| `style-bullet-char-invalid` | 글머리표 글자(char)가 글자 하나짜리 문자열이 아니다. |
| `style-char-pr-missing` | char_pr_id_ref 가 문서 머리의 글자 모양(hh:charPr) id 가 아니다. |
| `style-color-invalid` | 색 인자가 #RRGGBB·#AARRGGBB(16진 6·8자리)나 none이 아니다. |
| `style-container-create-failed` | styles 컨테이너를 만들지 못했다(방어적 분기). |
| `style-definition-kind-invalid` | remove_unused_definitions 의 kinds 가 비었거나 char_properties·paragraph_properties·border_fills·tab_properties 밖의 이름이다. |
| `style-definition-not-found` | 기준으로 준 글자 모양·문단 모양·탭·테두리·번호·글머리표 정의 id 가 헤더에 없다. |
| `style-font-container-create-failed` | fontfaces/fontface 컨테이너를 만들지 못했다. |
| `style-font-face-empty` | face 값이 비어 있다. |
| `style-font-lang-invalid` | lang 값이 OWPML 어휘(HANGUL/LATIN/HANJA/JAPANESE/OTHER/SYMBOL/USER) 밖이다. |
| `style-font-replace-same-face` | replace_font 의 src_face 와 dst_face 가 같은 글꼴이다. |
| `style-font-substitute-incomplete` | 대체 글꼴 인자가 일부만 주어졌다(subst_face 가 필요하다). |
| `style-font-type-invalid` | font_type/subst_type 값이 OWPML 어휘(REP/TTF/HFT) 밖이다. |
| `style-format-empty` | set_style_format 에 고칠 서식이 하나도 없다. |
| `style-in-use` | 지우려는 스타일을 쓰는 문단이 있는데 replacement 를 주지 않았다(또는 replacement 가 그 스타일이다). |
| `style-line-width-invalid` | 테두리·단 구분선·메모 선 굵기가 한/글 굵기 목록의 mm 값(0.1·0.12·0.15·0.2·0.25·0.3·0.4·0.5·0.6·0.7·1.0·1.5·2.0·3.0·4.0·5.0)이 아니다(가까운 값으로 바꿔 쓰지 않는다. 쓸 수 있는 값은 suggestion). |
| `style-list-continue-conflict` | continue_list 와 number_format·start 를 함께 주었다(이어 붙이는 목록은 앞 목록의 번호 모양을 쓴다). |
| `style-list-kind-invalid` | 목록 종류(kind)가 bullet/number/outline 밖이다. |
| `style-list-level-invalid` | 글머리표/번호 수준이 1 이상 10 이하의 int 가 아니다(bool 도 거부, 한/글 목록은 10수준까지다). |
| `style-list-property-failed` | 번호 문단모양을 만들지 못했다. |
| `style-list-start-value` | 목록 시작 번호(start)가 0 이상 65535 이하의 int 가 아니다(bool 도 거부, 한/글은 16비트로 둔다). |
| `style-memo-shape-line-type-invalid` | 메모 모양의 line_type 값이 OWPML 어휘(hc:LineType2) 밖이다. |
| `style-memo-shape-memo-type-invalid` | 메모 모양의 memo_type 값이 OWPML 어휘(NOMAL/USER_INSERT/USER_DELETE/USER_UPDATE) 밖이다. |
| `style-not-found` | 그 id·이름의 스타일이 없다(가용 목록·가장 가까운 이름 동봉). |
| `style-number-format-invalid` | 번호 형식이 한컴 번호 모양 밖이다(목록·개요 머리와 쪽 번호는 hc:NumberType1 15개, 각주·미주 번호는 hc:NumberType2 19개). |
| `style-numbering-level-invalid` | 번호 수준 지정(add_numbering 의 levels 한 항목, set_numbering_level 의 인자)이 text·number_format·start 밖의 키를 갖거나, text 가 문자열이 아니거나, 바꿀 값이 없다. |
| `style-numbering-level-missing` | 번호 정의에 고치려는 수준(hh:paraHead)이 없다. |
| `style-remove-default` | 첫 스타일(id 0, 바탕글)은 지울 수 없다. |
| `style-run-font-by-lang-invalid` | font_by_lang 이 언어 이름 → 글꼴 이름 매핑이 아니다(문자열 아닌 키·값, 같은 언어 두 번). |
| `style-run-format-empty` | 바꿀 글자 서식이 하나도 없다. |
| `style-run-format-invalid` | 글자 서식 이름이 모르는 것이거나 값의 형·범위가 틀렸다(자간 -50~50, 장평 50~200, 위·아래 첨자 동시). |
| `style-run-outline-type-invalid` | ensure_run 의 outline 값이 OWPML 어휘(hc:LineType1: NONE/SOLID/DOT/THICK/DASH/DASH_DOT/DASH_DOT_DOT) 밖이다. |
| `style-run-size-value` | 글자 크기(size, pt)가 0 이상의 수가 아니거나 너무 크다(음수는 0으로 쓰였다). |
| `style-tab-container-create-failed` | tabProperties 컨테이너를 만들지 못했다. |

### `table-*`

| 코드 | 뜻 |
|---|---|
| `table-alignment-value` | 표 가로 정렬(alignment)이 LEFT·CENTER·RIGHT 중 하나가 아니거나 문서 머리 정보가 없다. |
| `table-border-fill-not-found` | 표 자체에 준 테두리/배경 id(border_fill_id_ref)가 문서 머리의 hh:borderFill 에 없다. |
| `table-border-value` | 칸 테두리의 면·선 종류·굵기·색 지정이 잘못됐거나 문서 머리 정보가 없다. |
| `table-cell-flag-value` | 칸 보호(protected)·편집 가능(editable) 값이 bool 이 아니다. |
| `table-cell-no-sublist` | hp:subList 없이 문단을 바로 품은 칸(한/글이 쓰지도 열지도 않는 꼴)에 쓰려 해서 거부했다(읽기만 한다). |
| `table-cell-not-found` | 칸 좌표가 표 밖이거나 병합에 덮여 가리킬 칸이 없다. |
| `table-cell-remove-unsupported` | 표 칸 하나만 지우면 격자에 구멍이 나서 거부했다(행·열 삭제나 병합을 쓴다). |
| `table-cell-spacing-value` | 표의 칸 간격(cell_spacing)이 0 이상 32767 이하의 int(HWPUNIT)가 아니다(bool 도 거부). |
| `table-cell-text-direction-value` | 칸 글자 방향(text_direction)이 HORIZONTAL·VERTICAL 중 하나가 아니다. |
| `table-cell-vertical-alignment-value` | 칸 세로 정렬(vertical_alignment)이 TOP·CENTER·BOTTOM 중 하나가 아니다. |
| `table-cell-zone-border-fill-unknown` | 칸 영역에 줄 테두리/배경(border_fill_id_ref)이 문서 머리에 없는 id 이거나 id 형식이 아니다. |
| `table-cell-zone-grid-mismatch` | 셀 영역(hp:cellzone)이 새 열 격자에서 같은 셀들을 덮을 수 없어 열 너비를 바꾸지 않았다. |
| `table-cell-zone-not-found` | 그 번호의 칸 영역이 표에 없다(table.cell_zones 로 본다). |
| `table-column-width-value` | 열 폭이 양의 int(HWPUNIT)가 아니거나 한/글이 그리는 최소 폭(칸 좌우 여백+283)보다 좁다. |
| `table-header-rows-value` | 제목 행 수가 0..행 수 밖이거나, 병합 칸이 제목 행 경계를 가로지르거나, 참/거짓 값이 bool 이 아니다. |
| `table-margin-value` | 표 바깥·안 여백 값이 0 이상 2**31 미만의 int(HWPUNIT)가 아니다(bool 도 거부). |
| `table-merge-range-invalid` | 병합 범위가 표 밖이거나 사각형이 아니거나 'A1:B2' 꼴이 아니다. |
| `table-no-adjust-value` | noAdjust 값이 bool 이 아니다. |
| `table-not-found` | 표 인덱스가 범위를 벗어났다(doc.tables[i]). |
| `table-page-split-value` | 표가 쪽 경계에서 나뉘는 방식(page_split)이 TABLE·CELL·NONE 중 하나가 아니다. |
| `table-position-missing` | 표에 hp:pos 가 없어 글자처럼 취급을 바꿀 수 없다. |
| `table-row-height-value` | 행 높이가 양의 int(HWPUNIT)가 아니다. |
| `table-row-heights-value` | 행 높이(heights)가 행마다 하나씩인 양의 int(HWPUNIT)가 아니다. |
| `table-shading-value` | 칸 배경색이 #RRGGBB 나 None 이 아니다. |
| `table-size-invalid` | 새 표의 행·열 수가 1 이상의 int 가 아니다(bool 도 거부). |
| `table-width-value` | 표 폭(width)이 0 초과 2**31 미만의 int(HWPUNIT)가 아니다(bool 도 거부). |

### `text-*`

| 코드 | 뜻 |
|---|---|
| `text-block-unknown` | outline 의 after 에 준 글 덩어리 id 가 문서에 없다. |
| `text-highlight-color-invalid` | 형광펜 색이 #RRGGBB 6자리 16진 형식이 아니다. |
| `text-highlight-match-crosses-markup` | 찾은 구간이 인라인 마크업을 가로질러 안전하게 감쌀 수 없다. |
| `text-highlight-match-empty` | 형광펜으로 감쌀 문자열이 비어 있다. |
| `text-highlight-match-not-found` | 문단에서 형광펜으로 감쌀 문자열을 찾지 못했다. |
| `text-outline-budget` | outline 의 글자·항목 예산이 1보다 작다. |
| `text-pattern-invalid` | doc.text.find/replace 에 regex=True 로 준 찾을 글이 정규식으로 컴파일되지 않는다. |
| `text-place-invalid` | doc.text.iter_paragraphs()/iter_objects() 의 where·kinds 에 모르는 자리·개체 종류를 줬다. |
| `text-replacement-invalid` | 정규식 바꾸기의 바꿀 글이 패턴에 없는 묶음(\3, \g<이름>)을 부른다. |
| `text-search-empty` | 바꿀 대상 문자열이 비어 있다. |

### `toc-*`

| 코드 | 뜻 |
|---|---|
| `toc-command-unknown` | 차례가 몇 수준을 모으는지(ContentsLevel) 적혀 있지 않아 항목을 다시 만들 수 없다. |
| `toc-leader-value` | 차례 쪽 번호 앞 채움(leader)이 탭 채움 이름(NONE·SOLID·DOT·DASH …) 밖이다. |
| `toc-levels-value` | 차례 수준(levels)이 1~10의 int 가 아니거나 title·hyperlink 형식이 틀렸다. |
| `toc-no-headings` | 차례에 넣을 개요 문단(수준 1~levels)이 문서에 없다. |
| `toc-refresh-value` | 차례 refresh_on_open 이 True·False 가 아니다. |
| `toc-region-unsupported` | 차례의 시작과 끝이 한 문단에 있어 항목 문단을 둘 자리가 없다. |
| `toc-word-box-extractor-required` | PDF에서 글자 상자를 읽을 방법 없이 차례 쪽 대조를 불렀다. |

### `track-*`

| 코드 | 뜻 |
|---|---|
| `track-change-not-found` | 그 id 의 변경 추적 항목이 문서에 없다(doc.tracking.changes 로 본다). |
| `track-format-change-unconfirmed` | 글자·문단 모양 변경 추적(CharShape/ParaShape)은 쓰지도 거절하지도 않는다(본문이 가리키는 것은 수락도) — 한/글 2024는 스키마대로 쓴 서식 변경을 저장 때 버린다. |
| `track-match-crosses-markup` | 찾은 구간이 인라인 마크업을 가로질러 안전하게 감쌀 수 없다. |
| `track-match-empty` | 찾을 문자열이 비어 있다. |
| `track-match-not-found` | 문단에서 찾을 문자열을 찾지 못했다. |
| `track-paragraph-empty` | 지울 텍스트가 문단에 없다. |
| `track-selector-conflict` | 수락·거절할 변경을 change 와 author 로 함께 골랐다(하나만 준다). |
| `track-text-empty` | 변경추적 삽입 텍스트가 비어 있다. |
