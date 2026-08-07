# 편집기 표면 인벤토리 (Editor Surface Inventory) v1

`docs/coverage-ledger.json`(요소 축)이 답할 수 없는 질문에 답하기 위한
문서다: 우리 엔진이 한컴 편집기의 **사용자 가시 기능**을 카테고리별로
얼마나 덮고 있는가? 요소 하나하나가 아니라 "글자 굵게", "표 만들기",
"메모 달기" 같은, 사람이 한컴 리본/메뉴에서 실제로 클릭하는 단위로 센다.

이 문서는 2026-08-04 완전성 감사 판정문(§2 갭 지도, `docs/2026-08-04-
completeness-audit-verdict.md`)이 처음 시도했던 "기능군 관점"을 계승하되,
그 문서는 한 시점의 스냅샷(이후 사이클들이 §2의 15개 기능군 중 대부분을
이미 메웠다)이었던 반면, 이 문서는 **재생성 가능한 살아있는 측정기**로
설계됐다 — `scripts/editor_surface_inventory.py --check`로 드리프트를
잡는다(원장 자신의 `--check`와 같은 원칙).

## 방법론

각 행은 3축을 기계 대조 가능한 형태로 싣는다:

- **[엔진 상태]** — `저작 api` / `읽기만` / `보존만` / `없음(거부)` /
  `미확인` 5갈래.
- **[근거]** — 원장 요소 · capabilities 영역 · 지원 매트릭스 행 ·
  해당없음 중 실제로 있는 것.
- **[실한컴 검증 여부]** — `Render-verified` / `해당없음(의도적 거부)` /
  `미실측`.

근거 소스는 세 자산(`hwpx.capabilities._CAPABILITY_AREAS` · `docs/
support-matrix.md` · `docs/coverage-ledger.json`)과 OWPML 스키마 ·
`docs/owpml-deviations.md` DEV 레지스트리다. 세 자산 어디에도 흔적이
없는 항목은 추측하지 않고 `[미확인]`으로 정직 표기한다 — 그 사실
자체가 다음 실한컴 확인 목록이 된다.

## 카테고리 — 등록된 캐파빌리티 (자동 생성)

아래 블록은 `python scripts/editor_surface_inventory.py`가 생성한다.
`hwpx.capabilities._CAPABILITY_AREAS`(23개 등록 영역) 하나하나를 지원
매트릭스의 등급 문자열로 대조해 [엔진 상태]/[실한컴 검증]을 유도한다.
손으로 편집하지 말 것 — 마커 밖의 섹션만 손으로 유지보수한다.

<!-- AUTO-GENERATED:BEGIN (scripts/editor_surface_inventory.py) -->

자동 생성 시점 교차 확인: 원장(요소 축) 87건 render-verified(요소 345개 중) · 캐파빌리티 영역(기능 축) 31개 등록됨.

### 서식

| 기능 | 엔진 상태 | 근거 | 실한컴 검증 |
|---|---|---|---|
| 글꼴 등록 | 저작 api | 지원 매트릭스 「글꼴 등록」(`Create·Render-verified`) · capabilities 영역 `font-registration` · 위치 `doc.styles` | Render-verified |
| 목록 서식(글머리표·번호매기기) | 저작 api | 지원 매트릭스 「목록 서식(글머리표·번호매기기)」(`Create·Edit`) · capabilities 영역 `list-formatting` · 위치 `doc.styles` | 미실측 |
| 문단·표 저작/편집 | 저작 api | 지원 매트릭스 「문단·표 저작/편집」(`Parse·Preserve·Edit·Create·Render-verified`) · capabilities 영역 `paragraph-table-authoring` · 위치 루트 — `doc.add_paragraph` · `doc.add_heading` · `doc.add_section` | Render-verified |
| 문자 서식(굵게·기울임·밑줄·글꼴·크기·색 등) | 저작 api | 지원 매트릭스 「문자 서식(굵게·기울임·밑줄·글꼴·크기·색 등)」(`Edit·Create·Render-verified(부분)`) · capabilities 영역 `character-formatting` · 위치 `doc.styles` | Render-verified(부분만 -- 근거 칸의 등급 문자열 참조) |
| 찾아바꾸기 | 저작 api | 지원 매트릭스 「찾아바꾸기」(`Edit`) · capabilities 영역 `find-replace` · 위치 `doc.text` | 미실측 |
| 테두리 채우기(이미지·그라데이션) | 저작 api | 지원 매트릭스 「테두리 채우기(이미지·그라데이션)」(`Parse·Create(experimental)·Render-verified`) · capabilities 영역 `border-fill-image-gradient` · 위치 `doc.styles` | Render-verified(experimental 저작 포함) |
| 형광펜(하이라이트) | 저작 api | 지원 매트릭스 「형광펜(하이라이트)」(`Parse·Create(experimental)·Render-verified`) · capabilities 영역 `highlight` · 위치 `doc.text` | Render-verified(experimental 저작 포함) |

### 표

| 기능 | 엔진 상태 | 근거 | 실한컴 검증 |
|---|---|---|---|
| 표 구조 변경(행·열·표 삭제/삽입, 열 오토핏) | 저작 api | 지원 매트릭스 「표 구조 변경(행·열·표 삭제/삽입, 열 오토핏)」(`Preserve·Edit`) · capabilities 영역 `table-structure` · 위치 `doc.tables` | 미실측 |
| 표 생성(병합·중첩 포함) | 저작 api | 지원 매트릭스 「표 생성(병합·중첩 포함)」(`Create·Render-verified`) · capabilities 영역 `table-create` · 위치 루트 — `doc.add_table` | Render-verified |
| 표 탐색 기반 채움(라벨 매칭 네비게이션) | 저작 api | 지원 매트릭스 「표 탐색 기반 채움(라벨 매칭 네비게이션)」(`Edit`) · capabilities 영역 `table-navigation-fill` · 위치 `doc.tables` | 미실측 |

### 개체

| 기능 | 엔진 상태 | 근거 | 실한컴 검증 |
|---|---|---|---|
| arc·polygon·curve·connectLine | 저작 api | 지원 매트릭스 「arc·polygon·curve·connectLine」(`Parse·Preserve·Create(arc·polygon, experimental)·Unsupported-but-preserved(curve·connectLine)`) · capabilities 영역 `curve-objects` · 위치 `doc.shapes` | 미실측 |
| 그룹 개체(컨테이너) | 저작 api | 지원 매트릭스 「그룹 개체(컨테이너)」(`Parse·Create(experimental)·Render-verified`) · capabilities 영역 `container-authoring` · 위치 `doc.shapes` | Render-verified(experimental 저작 포함) |
| 그림 삽입/치환 | 저작 api | 지원 매트릭스 「그림 삽입/치환」(`Edit·Create`) · capabilities 영역 `picture` · 위치 루트 `doc.add_picture` + `doc.media` (이진 항목) | 미실측 |
| 도형 저작(선·사각형·타원) | 저작 api | 지원 매트릭스 「도형 저작(선·사각형·타원)」(`Parse·Preserve·Edit·Create·Render-verified`) · capabilities 영역 `shape-authoring` · 위치 `doc.shapes` | Render-verified |
| 수식 | 저작 api | 지원 매트릭스 「수식」(`Parse·Create(experimental)·Render-verified`) · capabilities 영역 `equation` · 위치 `doc.shapes` | Render-verified(experimental 저작 포함) |
| 저수준 도형·컨트롤 탈출구 | 저작 api | 지원 매트릭스 「저수준 도형·컨트롤 탈출구」(`Edit`) · capabilities 영역 `shape-escape-hatch` · 위치 `doc.shapes` | 미실측 |
| 차트 | 저작 api | 지원 매트릭스 「차트」(`Create(experimental)·Preserve`) · capabilities 영역 `chart` · 위치 `doc.shapes` | 미실측 |

### 필드

| 기능 | 엔진 상태 | 근거 | 실한컴 검증 |
|---|---|---|---|
| 누름틀(form field) 생성 | 저작 api | 지원 매트릭스 「누름틀(form field) 생성」(`Parse·Edit·Create(experimental)`) · capabilities 영역 `form-field-create` · 위치 `doc.fields` | 미실측 |
| 양식 채움(byte-splice) | 저작 api | 지원 매트릭스 「양식 채움(byte-splice)」(`Preserve·Edit`) · capabilities 영역 `form-fill` · 위치 `doc.tables` | 미실측 |
| 체크박스 양식개체 | 저작 api | 지원 매트릭스 「체크박스 양식개체」(`Create·Render-verified`) · capabilities 영역 `check-box` · 위치 `doc.fields` | Render-verified |

### 참조

| 기능 | 엔진 상태 | 근거 | 실한컴 검증 |
|---|---|---|---|
| 각주/미주 | 저작 api | 지원 매트릭스 「각주/미주」(`Edit·Create·Render-verified`) · capabilities 영역 `footnote-endnote` · 위치 `doc.notes` | Render-verified |
| 네이티브 목차(TOC)/상호참조 | 저작 api | 지원 매트릭스 「네이티브 목차(TOC)/상호참조」(`Create·Render-verified`) · capabilities 영역 `toc-crossref` · 위치 `doc.refs` | Render-verified |
| 하이퍼링크·책갈피 | 저작 api | 지원 매트릭스 「하이퍼링크·책갈피」(`Create`) · capabilities 영역 `hyperlink-bookmark` · 위치 `doc.refs` | 미실측 |

### 검토

| 기능 | 엔진 상태 | 근거 | 실한컴 검증 |
|---|---|---|---|
| 메모(코멘트) | 저작 api | 지원 매트릭스 「메모(코멘트)」(`Edit·Create·Render-verified`) · capabilities 영역 `memo` · 위치 `doc.notes` | Render-verified |
| 변경추적(redline) | 저작 api | 지원 매트릭스 「변경추적(redline)」(`Edit·Create`) · capabilities 영역 `redline` · 위치 `doc.tracking` | 미실측 |

### 보안/호환성

| 기능 | 엔진 상태 | 근거 | 실한컴 검증 |
|---|---|---|---|
| HWP 5.x 바이너리 | 없음(거부) | 지원 매트릭스 「HWP 5.x 바이너리」(`Unsupported-and-rejected`) · capabilities 영역 `hwp5-binary` · 위치 미지원 | 해당없음(의도적 거부, 실측으로 확인) |
| 문서 옵션·호환성 | 저작 api | 지원 매트릭스 「문서 옵션·호환성」(`Parse·Preserve·Edit·Render-verified`) · capabilities 영역 `document-options-compatibility` · 위치 `doc.parts` | Render-verified |
| 암호화 HWPX | 없음(거부) | 지원 매트릭스 「암호화 HWPX」(`Unsupported-and-rejected`) · capabilities 영역 `encrypted-hwpx` · 위치 미지원 | 해당없음(의도적 거부, 실측으로 확인) |

### 레이아웃

| 기능 | 엔진 상태 | 근거 | 실한컴 검증 |
|---|---|---|---|
| 페이지 레이아웃(용지·여백·머리말/꼬리말·쪽번호·단·줄번호·격자·요소 숨김) | 저작 api | 지원 매트릭스 「페이지 레이아웃(용지·여백·머리말/꼬리말·쪽번호·단·줄번호·격자·요소 숨김)」(`Edit·Create·Render-verified(부분)`) · capabilities 영역 `page-layout` · 위치 `doc.page` | Render-verified(부분만 -- 근거 칸의 등급 문자열 참조) |

### 자동화

| 기능 | 엔진 상태 | 근거 | 실한컴 검증 |
|---|---|---|---|
| 메일머지(placeholder 템플릿 배치 생성) | 저작 api | 지원 매트릭스 「메일머지(placeholder 템플릿 배치 생성)」(`Edit`) · capabilities 영역 `mail-merge` · 위치 모듈 — `hwpx.tools.mail_merge` | 미실측 |
| 편집 계획 실행(edit plan) | 저작 api | 지원 매트릭스 「편집 계획 실행(edit plan)」(`Preserve·Edit`) · capabilities 영역 `edit-plan` · 위치 모듈 — `hwpx.plan` | 미실측 |

<!-- AUTO-GENERATED:END -->

## 트레인㉚ — 측정 갭 등재 완료

트레인㉙이 찾은 측정 갭 8건 + 오귀속 1건은 전부 처리됐다:

- **7건은 정식 캐파빌리티 영역으로 등재**되어 위 AUTO 섹션에 흡수됐다 —
  페이지 레이아웃(`page-layout`)·문자 서식(`character-formatting`)·
  목록 서식(`list-formatting`)·글꼴 등록(`font-registration`)·
  표 탐색 기반 채움(`table-navigation-fill`)·찾아바꾸기(`find-replace`).
  등급은 실제 증거 기준으로만 매겼다 — 코드 존재는 Create/Edit,
  실한컴 증거가 있는 것만 Render-verified. 특히 페이지 레이아웃(19개
  메서드 중 5개만 증거 있음)과 문자 서식(17개 인자 중 8개만 증거 있음)은
  전체를 Render-verified로 뭉뚱그리지 않고 `Render-verified(부분)`으로
  정직하게 스코프를 좁혔다(등급 문자열 전체는 지원 매트릭스·AUTO 섹션의
  근거 칸에 그대로 인용돼 있다).
- **오귀속 1건 수리**: `add_hyperlink`/`add_bookmark`를 "toc-crossref"
  영역에서 분리해 독립 영역(`hyperlink-bookmark`)으로 등재 — 그 영역의
  실한컴 증거는 TOC 얘기뿐이었으므로 정직하게 미실측(`Create`만)으로
  등재했다. 다음 v12 openrate 배치(`authored-hyperlink-bookmark`)가 이
  영역의 첫 실한컴 판정이 된다(hp:label/v11의 전례와 같은 사슬).

**탭 설정 정정**: 애초 이 문서 초판이 "탭 설정 편집"을 읽기만으로
잘못 적었다 — 실제로는 `apply_paragraph_format(tab_stops=)`/
`ensure_tab_definition`이 실재하는 저작 경로이고, `docs/openrate/
report-v5.json`의 `authored-tabstops` 스트라텀(15/15 render_checked,
LEFT/RIGHT/CENTER/DECIMAL × NONE/DOT/DASH/SOLID/DASH_DOT/LONG_DASH 전
어휘 회전)이 이미 `hh:tabItem`/`hh:tabPr`/`hh:tabProperties` 세 요소를
`by-openrate-corpus`로 검증해 뒀다(원장에 트레인㉚ 이전부터 이미
반영돼 있었다 — 이번에 새로 배선한 게 아니라 이 문서의 서술 오류를
고쳤을 뿐). 독립 캐파빌리티 영역은 아직 없다(다음 트레인 후보 — 지금은
"문단·표 저작/편집"의 일부로 암묵적으로만 커버된다).

**문서 텍스트 변환/추출(html/markdown/plain) 스코프 확정**: 이 인벤토리의
전제("사용자가 한컴 리본/메뉴에서 실제로 클릭하는" 편집기 기능)에
안 맞는다고 확정했다 — `doc.text.html`/`.markdown`/`.plain`은 저작이
아니라 읽기·변환 유틸리티다(MCP 계층의 `hwpx_to_html`/`hwpx_to_markdown`
과 겹치는 것도 이 판단을 뒷받침). 측정 갭이 아니라 **스코프 밖**으로
분류하고 이 인벤토리의 추적 대상에서 제외한다.

**메일머지 core/MCP 계층 판정 + 등재 완료(트레인㉛)**: `grep`으로 직접
확인 — `src/hwpx/tools/mail_merge.py`(`merge_template_rows`·
`inspect_mail_merge_placeholders`·`load_mail_merge_rows`)가 **core에
실재한다**. capabilities.py에 언급은 있었으나(lazy-import 패턴 설명
문맥) 정식 캐파빌리티 영역으로 등재된 적은 없었다 — 트레인㉚이 찾은
신규 측정 갭을 트레인㉛에서 `mail-merge` 영역으로 등재했다(위 AUTO
섹션에 흡수됨, `자동화` 카테고리). `{{field}}`/`${field}`/`<<field>>`
플레이스홀더 치환이라 기존 요소를 갈아 끼울 뿐 새 요소를 안 만든다 —
등급은 `Edit`(Create 아님). 실한컴 증거 없음, 다음 v13+ 배치 후보.

## 확인 필요 — 우리 세 자산 어디에도 근거가 없는 표준 워드프로세서 기능 (실한컴 확인 목록)

아래는 한컴을 포함한 일반적 워드프로세서가 보통 갖는 기능이지만, 우리
세 자산(원장·capabilities·지원 매트릭스) 어디에도 이름조차 없다.
**추측이다 — 한컴 실물 UI로 존재 여부·정확한 명칭을 확인해야
[미확인]에서 벗어난다.** 이 표 자체가 오너의 다음 실한컴 확인 체크리스트
역할을 한다(오너 본인이 사이클 말에 Mac 실한컴 메뉴 표면을 직접
스캔하기로 함).

| 기능(추정) | [엔진 상태] | [근거] | [실한컴 검증] | 확인 필요 사항 |
|---|---|---|---|---|
| 맞춤법 검사 | 없음 | 해당없음 | 미실측 | 한컴 UI에 실재할 것이 거의 확실하나(언어 도구), 문서 구조 조작이 아니라 언어 분석이라 이 라이브러리의 스코프 밖일 가능성이 높다 — 스코프 판단 자체가 확인 필요 |
| 유의어 사전·한자 변환 | 없음 | 해당없음 | 미실측 | 상동(언어 도구, 스코프 밖 가능성) |
| 매크로/스크립트 자동화 | 없음 | 해당없음 | 미실측 | 한컴 자체 매크로 언어 — 이 라이브러리와는 다른 층위, 스코프 밖 확실도 높음 |
| 메일머지(한컴 UI에서의 대응 메뉴 존재 여부) | 저작 api(core, `mail-merge` 영역으로 등재 완료 — 위 AUTO 섹션 참조) | `hwpx.tools.mail_merge` | 미실측 | **엔진·등재 쪽은 트레인㉚·㉛에서 전부 해결**(core 실재 확인 + 정식 영역 등재). 남은 건 이거 하나뿐 — 한컴 UI 자체에 "메일머지"라는 이름의 메뉴가 실재하는지, 있다면 우리 placeholder 문법(`{{}}`/`${}`/`<<>>`)과 대응하는 개념인지는 여전히 [미확인] |
| 인쇄 설정(매수·범위·양면 등 다이얼로그 옵션) | 없음 | 해당없음 | 미실측 | PDF export 자체는 automation 컴패니언 계층 소관(core는 문서 조작만) — 인쇄 다이얼로그 옵션이 OWPML에 저장되는 상태인지조차 미확인 |
| 디지털 서명·배포용 문서 | 없음 | 해당없음 | 미실측 | "암호화 HWPX"(fail-closed 거부)와는 다른 기능일 가능성 — 배포용 문서는 편집 제한이지 암호화가 아닐 수 있다(한컴 UI 확인 필요) |
| 문자표(특수문자 삽입 다이얼로그) | 미확인 | 해당없음 | 미실측 | UI 다이얼로그일 뿐 별도 OWPML 표현이 없을 가능성 — 있다면 이미 `add_run`의 텍스트 삽입으로 커버될 것 |
| 개인정보 보호(찾기·마스킹) | **없음(core에 없음, 확인 완료)** | 해당없음 | 해당없음 | **트레인㉚에서 계층 판정 완료** — `grep`으로 `src/hwpx/` 전체를 확인한 결과 `personal_info`/`pii`/`scan_pii`/`mask_pii` 어떤 이름으로도 core에 존재하지 않는다. MCP 계층(`scan_personal_info` 도구)에만 있다 — core의 측정 갭이 아니다 |

## 관련 문서

- [지원 매트릭스](support-matrix.md) — 영역별 등급·증거
- [원장(요소 축)](coverage-ledger.md) · [coverage-ledger.json](coverage-ledger.json)
- [OWPML 편차 레지스트리](owpml-deviations.md) — 스키마/실물 편차 40건
- [2026-08-04 완전성 감사 판정문](2026-08-04-completeness-audit-verdict.md) — 이 문서의 선행 스냅샷
