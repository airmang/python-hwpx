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

자동 생성 시점 교차 확인: 원장(요소 축) 84건 render-verified(요소 345개 중) · 캐파빌리티 영역(기능 축) 23개 등록됨.

### 서식

| 기능 | 엔진 상태 | 근거 | 실한컴 검증 |
|---|---|---|---|
| 문단·표 저작/편집 | 저작 api | 지원 매트릭스 「문단·표 저작/편집」(`Parse·Preserve·Edit·Create·Render-verified`) · capabilities 영역 `paragraph-table-authoring` · 위치 루트 — `doc.add_paragraph` · `doc.add_heading` · `doc.add_section` | Render-verified |
| 테두리 채우기(이미지·그라데이션) | 저작 api | 지원 매트릭스 「테두리 채우기(이미지·그라데이션)」(`Parse·Create(experimental)·Render-verified`) · capabilities 영역 `border-fill-image-gradient` · 위치 `doc.styles` | Render-verified(experimental 저작 포함) |
| 형광펜(하이라이트) | 저작 api | 지원 매트릭스 「형광펜(하이라이트)」(`Parse·Create(experimental)·Render-verified`) · capabilities 영역 `highlight` · 위치 `doc.text` | Render-verified(experimental 저작 포함) |

### 표

| 기능 | 엔진 상태 | 근거 | 실한컴 검증 |
|---|---|---|---|
| 표 구조 변경(행·열·표 삭제/삽입, 열 오토핏) | 저작 api | 지원 매트릭스 「표 구조 변경(행·열·표 삭제/삽입, 열 오토핏)」(`Preserve·Edit`) · capabilities 영역 `table-structure` · 위치 `doc.tables` | 미실측 |
| 표 생성(병합·중첩 포함) | 저작 api | 지원 매트릭스 「표 생성(병합·중첩 포함)」(`Create·Render-verified`) · capabilities 영역 `table-create` · 위치 루트 — `doc.add_table` | Render-verified |

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

### 자동화

| 기능 | 엔진 상태 | 근거 | 실한컴 검증 |
|---|---|---|---|
| 편집 계획 실행(edit plan) | 저작 api | 지원 매트릭스 「편집 계획 실행(edit plan)」(`Preserve·Edit`) · capabilities 영역 `edit-plan` · 위치 모듈 — `hwpx.plan` | 미실측 |

<!-- AUTO-GENERATED:END -->

## 새로 드러난 갭 — 실제로 동작하지만 캐파빌리티 추적이 전혀 없는 기능 (트레인㉙ 신규 발견)

23개 등록 영역을 전수 대조하는 과정에서, `HwpxDocument`의 네임스페이스별
공개 메서드를 전수 스캔(`doc.page`/`doc.styles`/`doc.refs`/`doc.text`/
`doc.tables`의 `dir()`)해 캐파빌리티 레지스트리·지원 매트릭스 어느
쪽에도 이름이 없는 실제 동작 기능을 찾았다. 이건 엔진 갭이 아니라
**측정 갭**이다 — 코드는 있고 동작하는데(대부분 이 사이클의 프로브들이
이미 라이브로 exercised) 우리 자신의 두 자산 어디에도 등재가 없어서,
원장의 요소 축조차 이 기능들이 "완료됐다"는 신호를 낼 방법이 없다.

| 기능 | 근거 코드 | [엔진 상태] | [실한컴 검증] | 비고 |
|---|---|---|---|---|
| 페이지 레이아웃(용지 크기·여백·머리말/꼬리말·쪽번호·단·줄번호·격자·요소 숨김) | `doc.page`(19개 메서드: `set_size`/`set_margins`/`set_header`/`set_footer`/`set_page_number`/`set_columns`/`set_line_numbers`/`set_grid`/`set_visibility`/`hide_page_elements`/`restart_page_number` 등) | 저작 api(코드 존재·동작 확인됨 — DEV-033 프로브가 `set_header(page_type=)`를 라이브 exercise) | 미실측(캐파빌리티·매트릭스 등재 자체가 없어 openrate 스트라텀도 없다) | **가장 큰 단일 갭** — 19개 메서드짜리 표면 전체가 통째로 미등재. 다음 사이클 최우선 후보 |
| 문자 서식(굵게·기울임·밑줄·글꼴·크기·색·취소선·외곽선·양각/음각·그림자·장평·자간·위/아래첨자) | `doc.styles.ensure_run`(`_document/ns/styles.py`, 17개 키워드 인자) | 저작 api(코드 존재·동작 확인됨 — DEV-028 프로브가 `ensure_run(script=)`를 라이브 exercise, 이 세션 전체가 이 함수에 크게 의존) | 미실측(캐파빌리티·매트릭스 등재 없음 — "문단·표 저작/편집" 영역의 `entry_points`가 `add_heading`/`add_paragraph`/`add_section`만 지목, `ensure_run` 자체는 어느 영역에도 안 걸림) | 편집기의 가장 기초적인 기능인데 이름을 가진 자리가 없다 |
| 목록 서식(글머리표·번호매기기) | `doc.styles.bullet`/`.bullets`/`.apply_list_format`/`.ensure_numbering` | 저작 api(코드 존재) | 미실측 | |
| 탭 설정 편집 | `doc.styles.tab_properties`/`.tab_property` | 읽기만(DEV-002·DEV-022가 읽기 모델은 깊이 조사·수리했으나, 편집 API 자체의 캐파빌리티 등재는 없음) | 미실측 | |
| 글꼴 등록 | `doc.styles.ensure_font` | 저작 api(코드 존재 — 2026-08-04 감사 §2 갭#1이었으나 이후 사이클에서 구현된 것으로 보임, 등재만 안 됨) | 미실측 | |
| 표 탐색 기반 채움(라벨 매칭 네비게이션) | `doc.tables.fill_by_path`/`.find_cell_by_label`/`.map` | 저작 api(코드 존재) | 미실측 | "양식 채움(byte-splice)" 영역과 다른 메커니즘(byte-splice가 아니라 구조적 셀 채움) — 혼동 주의, 별도 등재 필요 |
| 찾아바꾸기 | `doc.text.replace`/`.find_runs` | 저작 api(코드 존재) | 미실측 | |
| 하이퍼링크·책갈피의 **독립** 실한컴 검증 | `doc.refs.add_hyperlink`/`.add_bookmark` | 저작 api(코드는 있음 — DEV-030 프로브가 `add_hyperlink`를 라이브 exercise) | **오귀속 위험**: capabilities.py가 이 둘을 "toc-crossref"(네이티브 목차/상호참조) 영역의 `authoring_methods`에 같이 등재해뒀지만, 그 영역의 지원 매트릭스 39행 근거 문구("네이티브 목차 구조 15/15, 페이지 정합 5/5")는 **TOC 얘기뿐 — 하이퍼링크·책갈피는 한 번도 독립적으로 실한컴 검증된 적이 없다** | 이 세션 초반부에 element-axis 원장에서 계속 잡아냈던 "혼합 지원 영역이 이웃까지 오염" 패턴과 동형 문제가 capability-area 축에도 있었다 |
| 문서 텍스트 변환/추출(html/markdown/plain) | `doc.text.html`/`.markdown`/`.plain` | 저작 api(추출 방향이라 "저작"은 부정확한 라벨일 수 있음 — 편집기 기능이라기보다 읽기·변환 유틸리티에 가까움, 판단 보류) | 해당없음 | 엄밀히 "편집기 기능"인지는 애매(MCP 계층의 `hwpx_to_html`/`hwpx_to_markdown`과 겹침) — 카테고리 배정은 다음 트레인에서 |

## 확인 필요 — 우리 세 자산 어디에도 근거가 없는 표준 워드프로세서 기능 (실한컴 확인 목록)

아래는 한컴을 포함한 일반적 워드프로세서가 보통 갖는 기능이지만, 우리
세 자산(원장·capabilities·지원 매트릭스) 어디에도 이름조차 없다.
**추측이다 — 한컴 실물 UI로 존재 여부·정확한 명칭을 확인해야
[미확인]에서 벗어난다.** 이 표 자체가 오너의 다음 실한컴 확인 체크리스트
역할을 한다.

| 기능(추정) | [엔진 상태] | [근거] | [실한컴 검증] | 확인 필요 사항 |
|---|---|---|---|---|
| 맞춤법 검사 | 없음 | 해당없음 | 미실측 | 한컴 UI에 실재할 것이 거의 확실하나(언어 도구), 문서 구조 조작이 아니라 언어 분석이라 이 라이브러리의 스코프 밖일 가능성이 높다 — 스코프 판단 자체가 확인 필요 |
| 유의어 사전·한자 변환 | 없음 | 해당없음 | 미실측 | 상동(언어 도구, 스코프 밖 가능성) |
| 매크로/스크립트 자동화 | 없음 | 해당없음 | 미실측 | 한컴 자체 매크로 언어 — 이 라이브러리와는 다른 층위, 스코프 밖 확실도 높음 |
| 메일머지(사용자 UI 경로) | 미확인 | 해당없음(core에는 없음) | 미실측 | **주의**: `mail_merge`라는 이름의 기능이 MCP 서버 계층에 존재한다고 알려져 있으나, 그게 core의 캐파빌리티인지 MCP 전용 조합 로직인지 이 조사에서 확인 못 함 — 다음 트레인에서 계층 구분 필요 |
| 인쇄 설정(매수·범위·양면 등 다이얼로그 옵션) | 없음 | 해당없음 | 미실측 | PDF export 자체는 automation 컴패니언 계층 소관(core는 문서 조작만) — 인쇄 다이얼로그 옵션이 OWPML에 저장되는 상태인지조차 미확인 |
| 디지털 서명·배포용 문서 | 없음 | 해당없음 | 미실측 | "암호화 HWPX"(fail-closed 거부)와는 다른 기능일 가능성 — 배포용 문서는 편집 제한이지 암호화가 아닐 수 있다(한컴 UI 확인 필요) |
| 문자표(특수문자 삽입 다이얼로그) | 미확인 | 해당없음 | 미실측 | UI 다이얼로그일 뿐 별도 OWPML 표현이 없을 가능성 — 있다면 이미 `add_run`의 텍스트 삽입으로 커버될 것 |
| 개인정보 보호(찾기·마스킹) | 미확인 | 해당없음(core에는 없음) | 미실측 | MCP 계층에 `scan_personal_info` 도구가 존재 — core 레벨 존재 여부 미확인, 위 메일머지와 같은 계층 구분 문제 |

## 관련 문서

- [지원 매트릭스](support-matrix.md) — 영역별 등급·증거
- [원장(요소 축)](coverage-ledger.md) · [coverage-ledger.json](coverage-ledger.json)
- [OWPML 편차 레지스트리](owpml-deviations.md) — 스키마/실물 편차 40건
- [2026-08-04 완전성 감사 판정문](2026-08-04-completeness-audit-verdict.md) — 이 문서의 선행 스냅샷
