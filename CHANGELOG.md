# 변경 로그

모든 중요한 변경 사항은 이 문서에 기록됩니다. 형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)과 [Semantic Versioning](https://semver.org/lang/ko/)을 따릅니다.

## [Unreleased]

## [2.23.0] - 2026-07-03
### 추가
- **폰트 shrink-to-fit (M10 후속, S-064)**: `hwpx.table_patch.fill_cells`에 `fit_max_lines`(+ 셀별 `max_lines`) — 셀 텍스트가 템플릿 폰트로 목표 줄수를 넘겨 wrap되면 `form_fit` FitEngine이 확신을 갖고 들어가는 가장 큰 폰트(≥ `min_font_pt`)를 골라 **실제 `<hh:charPr>`로 재료화**(base charPr 복제·height 변경)하고 셀 run을 그 charPr로 재지정. byte-preserving(header.xml의 새 charPr + 해당 섹션만 변경, opt-in이라 목표 없는 채움은 바이트 동일). FitEngine 정직 게이트가 borderline shrink는 거부(확실히 들어갈 때만 축소).
### 비고
- 오라클 실증: 실제 3학년 양식 성취기준 셀을 긴 텍스트 + `max_lines=4`로 채우니 9pt→6.5pt 축소, 실한컴 clean 렌더(나머지 표는 9pt 유지). 정직: 도교육청 폼은 base 9pt라 축소 여지(→8pt)가 작아 `autofit_columns`(가로)가 주력이고 폰트 축소는 보조; base 폰트 큰 폼엔 효과적. README 3스택 정비(python-hwpx 425→171·mcp 599→184·skill 471→178줄) 동반.

## [2.22.0] - 2026-07-03
### 추가
- **열 너비 조정 (M10 후속, S-064)**: `hwpx.table_patch.apply_table_ops` 새 op 2종 — `set_column_widths(table_index, widths)`(명시적 논리 열너비; 각 셀 cellSz.width = 걸친 열들의 합, 병합 인식)·`autofit_columns(table_index)`(내용에 맞춰 열너비 재균형: demand = 최장 단일-span 셀 텍스트폭[`form_fit` 어드밴스 모델], sqrt-damped로 문단 열 폭주 방지, 열별 최소폭 floor, 표 총폭 보존). 둘 다 **byte-preserving**(cellSz만 편집, charPr/header 불변)이며 grid 검증. 배경: 텍스트가 길어지면 한컴이 행 높이를 자동으로 늘려 넘침은 없으나 좁은 열은 촘촘히 wrap됨 — autofit이 내용 많은 열을 넓혀 완화한다(오라클 실증: 운영계획 성취기준 열 14186→16441, wrap 약 16→9줄, 총폭 보존).

## [2.21.0] - 2026-07-03
### 추가
- **M10 바이트보존 구조적 양식채움 (S-064)**: `hwpx.table_patch` — 2026-07-03 실전 실패(도교육청 평가계획 양식을 재생성으로 채워 서식 파괴)를 드라이버로, S-052 바이트 코어 위에 "양식 채움 층"을 완성. `fill_cells(source, cells)` — `(table_index, row, col)` 주소로 셀 텍스트를 바이트보존 splice(빈/self-closing 셀 삽입, 다중 문단 셀 전체 교체, 병합 앵커 해석). 미변경 셀·표·섹션은 **바이트 동일**(원칙 VII), no-op=바이트동일, 미해결 주소는 mutate 없이 `skipped`.
- **표 구조 프리미티브** `apply_table_ops(source, ops)`: `delete_column`(자유폭 재분배 + 열삭제로 빈 행 생기면 캐스케이드 삭제·rowSpan 붕괴)·`delete_row`·`delete_table`·`insert_row_by_clone`(rowSpan==1 참조행 복제, 서식보존·문단 id 리프레시 — 균등 재생성 금지). 각 편집 후 `build_grid` 검증(overlap/hole/oob)으로 무효면 거부(fail-closed, 원칙 VI). 중첩표 거부.
- **실한컴 오라클 게이트** `verify_fill(before, after, require=)`: `resolve_oracle`+`visual_check`로 before/after를 실제 한컴 렌더 대조 → `render_checked`·overflow·overlap(글자겹침)·page_count. 오라클 없으면 정직 degrade(`render_checked=False`), `require=True`면 fail-closed. open-safety/HTML 프리뷰를 한컴 수용으로 오인 금지.
### 비고
- 오라클 실증: 실제 3학년 양식에서 `delete_column`(반영비율 7→5열 캐스케이드)·`insert_row_by_clone`(세부기준 +행, 85병합 표)·content-complete 운영계획 채움이 실한컴에서 서식보존·clean 렌더. MCP 표면(`apply_table_ops`·`verify_form_fill`)은 hwpx-mcp-server 2.13.0에서 합류.

## [2.20.0] - 2026-07-02
### 추가
- **M7 네이티브 자동 차례·상호참조 (S-062)**: `hwpx.tools.toc_author` — `add_native_toc`(한컴 네이티브 `TABLEOFCONTENTS` 필드영역 + Command DSL, `dirty=1` 기본 = 한컴이 처음 여는 순간 항목·차례 스타일·쪽번호를 재계산), `add_page_crossref`(쪽 번호 `CROSSREF` 필드 + 캐시 결과런 — 한컴이 편집/저장 시 자동 재계산), `mark_toc_dirty`(편집 후 재번호 재트리거), `ensure_paragraph_anchor_id`/`outline_heading_paragraphs`. 계약은 실제 한컴 저작 gold pair에서 리버스엔지니어링(`tests/fixtures/m7_toc_gold/`).
- **차례 충실도 하니스**: `hwpx.tools.toc_fidelity` — `parse_toc_model`(하이퍼링크·평문 재생성 항목 모두), `structural_report`(오라클 없이도 CROSSREF↔차례 캐시 모순으로 stale 탐지), `toc_verify`(한컴 렌더 대조 `toc_correctness_ratio`, 무오라클 시 정직 `unverified`), `grow_paragraph`.
- **Mac 오라클 새로고침 레그**: `MacHancomOracle.refresh_document`(+`_refresh_hwpx_mac.applescript`) — 열기→dirty 필드 재생성→제자리 저장→닫기. dirty-재생성 직후 같은 세션 PDF export가 이 한컴 빌드를 크래시시키는 실측 때문에 refresh와 render는 의도적으로 별도 세션.
### 수정
- Mac 렌더 스크립트 `waitForFile`이 `%%EOF` 트레일러를 요구 — size>0만으로는 비동기 export 도중의 잘린 PDF를 캡처했다(실측).
### 비고
- E2E 오라클 증명: 저작→새로고침→ratio 1.0(2/5/8쪽) → 재페이지네이션+`mark_toc_dirty`→새로고침→ratio 1.0 + 페이지 SHIFT(2/7/10). 실측 수집 규칙: `ContentsStyles:0:`이 바탕글(스타일 0) 문단도 차례 항목으로 수집 — 본문은 본문(스타일 1) 등 비수집 스타일 권장. MCP 표면(`add_toc`·`add_cross_reference`·`verify_toc`)은 hwpx-mcp-server 2.12.0에서 합류.

## [2.19.0] - 2026-07-02
### 추가
- **M6 런서식 충실 읽기 하니스 (S-060)**: `hwpx.tools.read_fidelity` — `resolve_run_spans`(런별 bold/italic/underline/strikeout/color/size_pt/font/super-subscript를 charPr+fontface 해석), `collect_notes`(각주/미주 본문 + 본문 서식), `roundtrip_fidelity`/`corpus_fidelity`(콘텐츠-레벨 라운드트립 충실도), `spans_fidelity`/`notes_fidelity` 비교기, 공개 `fontface_maps`/`run_span`. 요소-카운트만 재던 `roundtrip_diff`와 달리 charPr-해석 런-스팬 및 각주 본문의 무손실을 측정한다.
- `strikeout`은 shape 속성으로 정규화(항상 존재하는 `<hh:strikeout shape="NONE"/>`가 상시-on으로 오독되던 문제 회피), `underline` type `NONE`→`None` 정규화.
### 비고
- 코퍼스 런서식 라운드트립 충실도 1.0(4075 런 / hwpxlib 47편). reading 차원 4→5(구조적 corpus-scale, 오라클 불요). 설치 MCP 표면 노출은 hwpx-mcp-server 2.11.0에서 합류.

## [2.18.0] - 2026-07-01
### 추가
- **M5 개인정보(PII) 마스킹 엔진 (S-059)**: `hwpx.tools.pii` — `detect_pii` / `mask_pii` / `mask_value` / `PIIPolicy`. 기계검증 세트(주민등록번호·휴대폰·이메일·카드+Luhn)는 항상-on high-confidence, 맥락형(계좌·주소·이름)은 라벨 게이트 low-confidence(과마스킹 방지). 필드 최소화 `minimize_fields`, 가명 `Pseudonymizer`(결정적 토큰맵), 비식별 `deidentify`(불가역 salted-SHA256), 로그 위생 `PiiLogFilter` / `scrub_exception_message`.
- **메일머지·추출 경로 마스킹**: `mail_merge(masking_policy=DEFAULT_POLICY)` 기본 ON — 명부 산출물의 기계검증 PII 자동 마스킹(마스킹 길이로 FitPolicy 재측정). `export_text` / `export_html` / `export_markdown(masking_policy=...)` opt-in 추출 마스킹(기본 `None` = 내부 placeholder 탐지 보존).
### 비고
- 폼필(form-fill) 경로 마스킹·`scan_personal_info`·전 경로 0-누출 게이트는 MCP 표면(hwpx-mcp-server) 단계에서 합류합니다.

## [2.17.0] - 2026-06-30
### 추가
- **M4 변경추적(redline) 저작 (S-058)**: `HwpxDocument.add_tracked_insert` / `add_tracked_delete` / `add_tracked_replace` — 에이전트가 변경추적(삽입/삭제/치환)을 작성자·일자와 함께 저작하고, 사람이 한컴 검토 리본에서 개별 수락/거부할 수 있습니다. 헤더 `trackChanges`/`trackChangeAuthors` surgical splice(작성자 dedup·표시 플래그) + 본문 `insertBegin/End`·`deleteBegin/End` 마크(charPrIDRef 상속, paraend=0). 한컴 수용성은 measure-first 스파이크로 입증(실 Windows 한컴 COM `IsTrackChange=1`·opens-clean·roundtrip + 검토 리본 수락→반영/거부→취소 확인).
- `hwpx.tools.redline.verify_redline(before, after, *, oracle=None)` — 구조 검증(변경 수·TcId 마크 연결·표시 플래그·opens-clean) + `visual_check` `render_checked` 를 정직하게 fold(오라클 없으면 `unverified`, 거짓 통과 없음).
### 수정
- **메모(코멘트) 본문이 숫자로 표시되던 버그**: `attach_memo_field` 가 MEMO 필드 subList에 코멘트 내용 대신 메모 ID(숫자)를 넣어, 한컴이 메모 박스에 숫자를 렌더했습니다. 한컴 오라클 구조에 맞춰 subList에 코멘트 텍스트를 넣고 `MemoShapeIDRef`(기본 65535)로 박스를 연결하도록 수정했습니다(실 Windows 한컴 검증).
### 비고
- 수락/거부는 사람이 한컴 검토 리본에서 수행합니다(COM accept 액션 미노출 — 정석 워크플로).
- byte-identity: 미수정 part(ZIP 엔트리)는 byte-identical. 수정 섹션 내부의 문단단위 완전 byte-identical(surgical splice)은 stretch로 연기(한컴 렌더·수용엔 무영향).

## [2.16.0] - 2026-06-29
### 추가
- **M3 문서 작성 (S-057)**: `create_document_from_plan` 이 `document_type`(공문/보고서/가정통신문)을 보고 실제 한컴-harvest 프로파일(`hwpx.design.compose`)로 라우팅합니다. 미매칭 유형은 기존 제로베이스 경로를 유지하고 `-> HwpxDocument` 반환 계약을 보존합니다. 공문은 결문 메타 `document_plan.gyeolmun = {issuer, productionNumber, enforcementDate, disclosure}` 를 지원합니다.
- `hwpx.design.profiles.home_notice` — 실제 가정통신문에서 harvest한 디자인 프로파일.
- **공문 구조 hard-gate**: `inspect_official_document_style(source, *, document_type="공문")` 이 시행문 척추(수신·발신명의·시행·공개구분·끝.)를 ERROR 심각도로 검사하고 `structure_pass` 를 반환합니다. 표 셀까지 읽는 table-aware 텍스트 추출(실 시행문의 두문/결문은 표 안에 있음)을 추가했고, 진짜 시행문(`tests/fixtures/m3_gongmun_gold/seoul_sihaengmun.hwpx`)을 앵커로 삼습니다.
- `inspect_document_authoring_quality` 에 `korean_proofing_status`(정직 `unverified` / `llm_proofed_not_oracle_verified`, 거짓 통과 없음)와 `verify_render=True` 시 실제 한컴 렌더 영수증 `render_checked`/`visual_complete` 를 추가했습니다.
### 비고
- 각주(footnote) 작성은 한컴 렌더가 확인되지 않아 honest-deferred(`unverified`) 상태입니다.

## [2.15.0] - 2026-06-27
### 추가
- `HwpxDocument.set_paragraph_format(keep_with_next=, keep_lines=, page_break_before=)` — 문단 keep-together 플래그를 엔진 `ensure_paragraph_format(break_setting=)`로 전달한다(새 paraPr 발행, 기존 paraPr 미수정 = 무손실). 시험지 조판 등에서 한 문항이 단/쪽 경계에서 잘리지 않게 묶을 때 쓴다.
- `hwpx.exam`: re-typeset an authored exam (Markdown) into a school form `.hwpx`
  — Exam IR + strict md parser, form profiler (role→existing form style),
  keep-together body composition (insert into the form's body region, never
  append; 관리박스 + footer preserved byte-identical), and an oracle convergence
  driver `compose_exam_into_form`. The driver renders via Hancom and, when the
  composed 문항 are in the extractable text layer, verifies 문항-split / overflow
  / placeholder integrity (inserting column/page breaks to converge); when they
  are not (forms whose body Hancom exports as vector curves) or no oracle is
  available, it returns `render_checked`/`splits=None` + `needs_review` rather
  than a silent pass (Constitution V — honest unverified).
- `find_seal_anchor` — 발신명의가 좁은 표 셀에서 **여러 줄로 wrap**된 경우도 앵커를 찾는 fallback(연속 줄 윈도우, 최대 3줄). 단일 줄 매칭이 우선이라 기존 동작 불변; spurious 다중줄 매칭은 윈도우·동일페이지로 차단.
### 수정
- `paragraph.add_picture` — `treat_as_char=True`(inline)인데 `pos_overrides`(PAPER relTo/offset)를 주면 모순된 inline/floating `<hp:pos>`를 방출하던 것을 `ValueError`로 fail-fast. floating 배치는 `treat_as_char=False`에서만.

## [2.14.0] - 2026-06-25
### 추가
- `hwpx.form_fit.seal` — 직인/관인 배치 + 규정 검사(M2 P3). `find_seal_anchor`(발신명의 줄의 끝글자=도장 중심), `check_seal_placement`(중심 tol·가림 글자 차별 pass/fail), `seal_pos_offsets`(PDF pt 앵커→PAPER HWPUNIT offset), `place_seal`(발신명의 소스 문단—표 셀까지 탐색—에 직인을 floating 스탬프; 오라클 검증 0.12pt, fail-closed, page/clamp 정직신호).
- `hwpx.form_fit.wordbox.extract_image_boxes` — 렌더된 PDF에서 임베디드 이미지(직인) rect 추출. 직인은 글자가 아니라 그림이라 `get_text`로 안 잡힘.
- `add_picture(treat_as_char=False, pos_overrides=, text_wrap=)` — floating 그림 경로. PAPER 상대 `<hp:pos>`(offset은 xs:nonNegativeInteger로 coerce) + `textWrap`(직인은 `IN_FRONT_OF_TEXT`로 텍스트 안 밀고 위에 스탬프).
- `mail_merge(fit_policy=, max_lines=)` — fit-aware 배치(M2 P4 / FR-004). 각 placeholder 슬롯을 템플릿에서 한 번 측정(template-once-measure, advance-model·오라클 불필요)하고 레코드별로 fit. 넘침/결측 행을 `needsReview[]`/`skipped[]`(reason 코드 + retry advice)로 격리—자동 truncate 없음. `[xlsx]` extra(openpyxl)로 Excel/명부(.xlsx/.xlsm) 수용.
### 수정
- 임베디드 이미지 manifest `<opf:item>`에 `isEmbeded="1"`(OWPML 단일-d 철자) 방출 — 없으면 한컴이 `add_picture`로 넣은 **모든 그림을 렌더 드롭**하던 잠복 버그(한컴 GUI 렌더로 확정).
- `mail_merge`가 **표 셀** 안 placeholder도 치환 — `replace_text_in_runs`(본문 전용)가 셀 런에 안 닿아 발신·결재/안내 표 안 `{{토큰}}`이 미치환으로 남던 버그.

## [2.13.0] - 2026-06-24
### 추가
- `hwpx.conformance` — VisualComplete 적합성 코퍼스 + 배지 등급(plan §2 Phase G). `hwpx-conformance run`이 코퍼스를 4개 배지 등급(Open-Safe/Semantic-Safe/Form-Safe/VisualComplete)으로 채점하고 등급별 통과율을 산출합니다. 임계값은 엄격 기본값(구조 등급 100%, 폼셋 overflow 0%, VisualComplete ≥95%). golden 베이스라인(`tests/conformance/golden/structural.json`) 대비 회귀를 숫자로 감지하며(`--check`), CI가 구조 등급을 추적합니다. 어슈어런스 등급은 절대 섞지 않습니다(§0.0): 한컴이 없는 구조 실행은 VisualComplete를 `unverified`로 보고하고, 오라클 실행(도달 가능한 한컴 백엔드)만 VisualComplete를 검증합니다. 케이스에 `before`(+선택적 `editMask`)를 선언하면 VisualComplete가 오라클의 **before/after diff 경로**로 게이트됩니다(마스크 밖 변경·글자 겹침을 잡음). `expectVisualDefect`는 일부러 깨뜨린 쌍을 positive control로 삼아 게이트가 결함을 실제로 잡는지 검증합니다. (실측: 실제 한컴-저장 코퍼스에서 clean 쌍은 통과, out-of-slot 변경은 catch.)

## [2.12.0] - 2026-06-24
### 추가
- `hwpx.quality` — 단일 저장 게이트 `SavePipeline`, `QualityPolicy`, `VisualCompleteReport`. 모든 직렬화 출력이 이 게이트를 통과합니다(무결성·XML·OPC/ID·열림안전·시각 오라클 → 단일 리포트). `HwpxDocument.save_report(...)`로 노출.
- `hwpx.form_fit` — FormFit 엔진(`FitPolicy`/`FitResult`). 폼 값이 셀/필드 박스에 맞는지 측정(한글=1.0em, 한컴 실측 보정)해 wrap/shrink/truncate/fail 처리. `set_cell_text(fit=...)` / `fill_form_field(fit_policy=...)`로 연결.
- `hwpx.layout` — 렌더러 없는 구조적 시각 스모크 `lint_layout`(stale lineseg·dirty/lineseg·overflow risk·표 구조). `QualityPolicy.layout_lint`로 SavePipeline 하드 게이트로 연결.
- `hwpx.design` — 검증된 한컴 저장 템플릿 + harvest 프래그먼트로 새 문서를 생성하는 `compose`/`DocumentPlan`/profile 빌더. `official_notice`/`report`/`application_form` 프로파일 동봉.
- 시각 오라클 `hwpx.visual`에 Mac 한컴 백엔드(`MacHancomOracle`) 추가.

## [2.11.1] - 2026-06-12
### 수정
- `create_document_from_plan()`의 `heading` block과 builder `Heading`이 기본 템플릿의 `개요 N`/`Outline N` 문단 스타일을 실제로 적용하도록 수정했습니다. 생성 문서가 한컴 개요/문서 탐색과 MCP outline readback에서 구조화된 제목으로 인식됩니다.
- document-plan 기본 스타일 preset에 제목 18pt, 부제 12pt, 장 제목 14pt 글자 크기와 함초롬바탕 폰트를 적용해 보고서 생성 시 제목/본문 시각 위계가 명확하게 보이도록 했습니다.

## [2.11.0] - 2026-06-12
### 추가
- 시드 결정적 퍼징 수렴 루프 `hwpx.tools.fuzz`(시나리오 카탈로그·생성기·3중 오라클 러너·최소화)와 `tests/fixtures/fuzz_regressions` 회귀 박제 수트를 추가했습니다.
- 레이아웃 근사 프리뷰 렌더러 `hwpx.tools.layout_preview`를 추가했습니다(페이지 박스·표·여백 근사 HTML/PNG — 에이전트 자기검증용).
- section XML 바이트 splice 기반 문단 패치 경로 `hwpx.patch`를 추가했습니다(미수정 영역 바이트 보존).
- 그림 자산 안전 삽입·치환 API(`add_picture` 및 치환 워크플로)와 manifest 검증을 추가했습니다.
- 기존 문서 서식 편집 API를 추가했습니다: 문단 정렬·줄간격·들여쓰기·문단 간격, 용지·여백·방향, 머리말/꼬리말·쪽번호, 불릿/번호 형식.
- 누름틀(클릭히어 필드) 1급 조회·채움 API를 추가했습니다.
- 공문서 작성규정 lint `hwpx.tools.official_lint`(항목기호 위계·"끝." 표시·붙임·날짜 표기)와 결재란 프리셋을 추가했습니다.
- 고급 생성기 `hwpx.tools.advanced_generators`를 추가했습니다: 사진대지(`build_image_grid`)·회의 명패(`build_meeting_nameplates`)·표 기반 조직도.
- 신구대조 문단 diff와 참조 정합 lint `hwpx.tools.doc_diff`를 추가했습니다.
- 메일머지 대량 생성과 표 합계·평균 계산 유틸 `hwpx.tools.mail_merge`를 추가했습니다.
- 참조 문서 서식 프로파일 추출·적용과 템플릿 레지스트리 `hwpx.tools.style_profile`을 추가했습니다.
- template analyzer 리포트를 강화했습니다(열너비 재구성·cell margin·vertAlign).

### 변경
- `hwpx.oxml.document` 모놀리스(5,700여 줄)를 요소별 모듈(`_document_impl` 외 18개)로 분할했습니다. 공개 API는 변하지 않습니다.

### 수정
- 신뢰할 수 없는 입력 파싱을 강건화했습니다(`hwpx.opc.security`): XML entity 선언 거부와 깊이/크기 한도, ZIP 압축비·멤버 수 한도를 적용해 entity 폭탄·압축 폭탄 입력을 안전하게 거부합니다.

## [2.10.3] - 2026-06-09
### 추가
- `hwpx.tools.validate_editor_open_safety()`와 `EditorOpenSafetyReport`를 추가해 package validation, document validation, 재오픈 검증을 한 곳에서 확인할 수 있게 했습니다.

### 수정
- 텍스트를 줄이는 저수준 편집 뒤 stale `hp:linesegarray`가 남아 한컴 편집기에서 열리지 않을 수 있는 문제를 막기 위해, 저장 직전 plain-text 문단의 무효한 layout cache를 제거합니다.
- 편집된 section과 public 저수준 section write 경로는 모든 `hp:lineSegArray` layout cache를 제거해, 복합 문단처럼 stale 여부를 안전하게 계산하기 어려운 경우도 편집기가 다시 계산하도록 했습니다.
- public 저수준 section/header XML write 경로도 Hancom-compatible root namespace 선언과 `standalone="yes"` XML declaration을 보정해 generic XML serializer 출력이 그대로 저장되지 않도록 했습니다.
- `HwpxDocument.to_bytes()`, `save_to_path()`, `save_to_stream()`이 생성된 패키지의 editor-open safety를 확인한 뒤에만 결과를 반환하거나 쓰도록 보강했습니다. `save_to_path()`는 safety 실패 시 기존 대상 파일을 교체하지 않습니다.
- `HwpxPackage.save()`도 editor-open safety를 기본 검증해 저수준 package 직접 편집이 unsafe HWPX를 bytes/path/stream으로 내보내지 않도록 막습니다.
- public `HwpxPackage.save()`에서 editor-open safety 검증을 우회하는 파라미터를 제공하지 않도록 정리했습니다. 검증 실패 상태의 bytes snapshot은 package 내부 진단 토큰이 있는 경로에서만 생성하며, unchecked 경로는 caller-provided file path/stream에 직접 쓸 수 없습니다.
- `HwpxDocument._to_bytes_raw()`의 open-safety bypass 인자를 제거해 document 객체에서 unchecked bytes를 얻는 실수성 우회 경로를 더 좁혔습니다.
- private archive writer도 save 내부 컨텍스트에서만 동작하게 해, `_write_archive()`/`_write_zip_entry()` 직접 호출로 editor-open safety 검증을 건너뛴 ZIP을 만드는 실수성 우회 경로를 막았습니다.
- 문서/package 저장 중 open-safety, 실제 파일 쓰기, stream short write가 실패하면 dirty 상태를 성공처럼 정리하지 않도록 보강했습니다. seek 가능하고 안전하게 복원 가능한 stream은 쓰기 실패 시 원래 내용으로 rollback합니다.
- archive pack CLI가 재패킹 결과를 editor-open safety 리포트로 재검증하고, 실패 시 기존 output을 보존합니다. 성공 시 `PackResult.open_safety`와 CLI `open_safety_ok=true` 출력으로 handoff evidence를 제공합니다.
- repair/recover 출력도 CRC와 package validation 뒤에 editor-open safety를 재검증하고, section의 `hp:lineSegArray` layout cache 제거와 section/header root namespace 및 `standalone="yes"` 보정을 적용합니다. 실패 시 기존 output은 보존하고, 성공 시 `RepairResult.open_safety`로 handoff evidence를 제공합니다.
- template form-fit apply가 최종 목적지에 먼저 복사하지 않고 temp 파일에서 저장 및 editor-open safety 검증을 끝낸 뒤에만 교체하도록 보강했습니다.
- builder `Document.save_to_path()` 리포트에 `editor_open_safety` hard gate와 세부 리포트를 포함합니다.
- template form-fit paragraph clone 경로가 텍스트를 직접 바꿀 때도 layout cache를 제거합니다.
- package validator가 실제 텍스트 길이를 넘어서는 `lineseg/@textpos`를 hard error로 보고하도록 보강했습니다.
- `EditorOpenSafetyReport.ok`가 package/reopen뿐 아니라 document validation 실행 실패와 hard error도 반영하도록 보강했습니다.
- 저장 직전 paragraph의 `styleIDRef`가 `Normal`/`본문`처럼 header style 이름으로 잘못 들어간 경우, 일치하는 numeric style id로 정규화해 저수준 편집 산출물이 document validation에서 차단되거나 편집기 오픈 리스크를 만들지 않도록 했습니다.
- `HwpxPackage.save(updates=...)` 같은 순수 package 저수준 저장 경로도 header style 이름으로 된 paragraph `styleIDRef`를 numeric id로 정규화해, MCP를 거치지 않는 직접 ZIP/XML 편집 산출물도 같은 safety 보정을 받도록 했습니다.

## [2.10.2] - 2026-06-06
### 추가
- `hwpx.tools.markdown_export.export_markdown()`와 `HwpxDocument.export_rich_markdown()`을 추가해 풍부한 Markdown 변환을 지원합니다. 인라인 서식(굵게/기울임/취소선/색상/하이라이트), 표 병합 셀(colspan/rowspan HTML), 중첩 표 재귀, `rect`/`ellipse`/`polygon` 도형 내부 paragraph, BinData 이미지 추출, `Ⅰ.`/`1.` 패턴 기반 헤딩 감지(`# `/`## `), 각주·미주(정확 위치 마커 + `fn1`/`en1` 일련번호 + 본문 인라인 서식), 하이퍼링크(`[text](url)`) 보존을 한 번에 처리합니다. 기존 `HwpxDocument.export_markdown()`은 그대로 유지됩니다.
- `HwpxOxmlNote`에 본문 paragraph 접근/편집 helper를 추가했습니다: `body_paragraph` property, `add_run(text, *, char_pr_id_ref=..., bold=..., italic=..., underline=..., color=..., font=..., size=..., highlight=..., strike=..., attributes=...)`, `add_hyperlink(url, display_text, *, char_pr_id_ref=...)`. XML 직접 조작 없이 각주 본문에 혼합 서식 run과 하이퍼링크를 추가할 수 있습니다.
- `get_table_map()` 결과에 본문 표 anchor `location`, 셀 문단별 `table_cell_paragraph` location, `caption_text`, `preceding_paragraph_text`를 추가했습니다.
- 새 컨버터와 helper에 대한 회귀 테스트를 `tests/test_markdown_export.py`에 추가했습니다.

### 변경
- `HwpxOxmlTableCell.text`가 셀 내부 여러 문단을 줄바꿈으로 보존하고, `set_text(..., preserve_format=True, split_paragraphs=True)` 경로에서 기존 run `charPrIDRef`를 유지하도록 개선했습니다.

### 수정
- `HwpxOxmlParagraph.add_footnote()`/`add_endnote()`의 `char_pr_id_ref` 인자가 외부 호스팅 run에만 적용되고 각주 본문 run은 항상 `charPrIDRef="0"`으로 하드코딩되던 문제를 수정했습니다. 인자가 사용자 의도대로 본문 run에도 적용됩니다.

## [2.10.1] - 2026-06-04
### 추가
- `document_plan` authoring을 builder lowering 중심으로 확장하고 v2 builder node, TOC, government_report preset을 지원합니다.
- 정부보고서 계산/파싱 유틸리티(`hwpx.tools.report_utils`, `hwpx.tools.report_parser`)와 computed field 치환을 추가했습니다.
- generic element coverage inventory, table cleanup, table profile/caption/unit preservation, id reference integrity checker를 추가했습니다.
- `linesegarray`, `transMatrix`, `scaMatrix`, `rotMatrix`, edit/combo box control을 first-class OXML 모델로 승격했습니다.

### 변경
- builder save report의 hard gate가 id integrity를 실제 검사 결과로 반영하도록 강화했습니다.
- 패키지 rewrite 시 `mimetype` 엔트리를 보존하도록 OPC 저장 경로를 정리했습니다.

## [2.10.0] - 2026-06-02
### 추가
- `hwpx.builder` 공개 패키지를 추가했습니다. `Document`, `Section`, `Paragraph`, `Run`, `Heading`, `Bullet`, `NumberedList`, `Table`, `Image`, `Header`, `Footer`, `PageNumber`, `PageBreak`, `Metadata`, `PageSize`, `Margins` 노드로 조립형 HWPX 생성을 지원합니다.
- `BuilderSaveReport`와 `ReopenReport`를 추가해 builder 저장 후 package validation, document error/lint, reopen, feature flags, visual review 필요 여부를 확인할 수 있게 했습니다.
- 머리글/바닥글 리치 content, 자동 쪽번호, 리치 런 서식(color/font/size/highlight/strike), 다단계 목록, 표 병합/음영/열너비, 이미지 배치를 위한 `HwpxDocument` facade 및 OXML wrapper 메서드를 추가했습니다.
- `hwpx.document_plan.v1`, 운영 계획서 품질 프로필, template form-fit authoring, proposal/form-fill 품질 검증 흐름을 강화했습니다.
- hwpxlib sample corpus 기반 oracle fixture와 builder vertical slice 통합 테스트를 추가했습니다.
- `src/hwpx/tools/_schemas/owpml/`에 2011 Hancom 네임스페이스용 subset XSD 번들을 추가했습니다 (`header.xsd`, `body.xsd`, `paralist.xsd`, `core.xsd`, `xml.xsd`, `NOTICE`).
- `hwpx.oxml.load_compound_schema()`와 `SchemaImportError`를 추가해 offline compound XSD 로딩을 지원합니다.
- fixture matrix 기반 Phase 1 validation 리포트(`shared/hwpx/HWPX_STACK_VALIDATION_2026-04-20_pre-phase1.md`, `..._post-phase1.md`)와 회귀 테스트를 추가했습니다.

### 변경
- `validate_document().ok`는 error 기준으로 유지하고 schema warning은 lint/warning으로 분리해 가시화합니다.
- `HwpxDocument.save_to_path()` 기반 저장/재오픈 검증 경로를 builder와 authoring workflow에서 일관되게 사용하도록 정리했습니다.
- `hwpx-validate`는 이제 기본 strict 모드로 Phase 1 subset schema bundle을 사용합니다. `--no-strict`로 warning-only 분류를 지원합니다.
- `HwpxDocument.validate()`는 기본 `strict=False`로 동작하며, `validate_on_save_strict` 옵션으로 저장 시 strict 검증을 제어할 수 있습니다.
- 패키지 배포물(sdist/wheel)에 OWPML subset schema bundle이 포함되도록 package-data를 확장했습니다.

### 수정
- split-run placeholder, template form-fit, proposal/document-plan 생성 경로의 회귀를 보강했습니다.
- builder vertical slice에서 Hancom Office HWP 재오픈과 구조 hard gate가 통과하도록 머리글/바닥글 lowering과 page number control 배치를 정렬했습니다.

## [2.9.1] - 2026-04-27

상호운용성(interop) 버그 묶음 릴리즈입니다. 외부 기여자들이 보고하고 수정한 세 가지 문제를 정리합니다.

### 수정
- `HwpxOxmlTableCell._ensure_text_element`와 `ensure_run_style` 내 modifier가 lxml 엘리먼트 상에서 또한 `ET.SubElement`를 호출해 `TypeError`를 발생시키던 경로를 기본 헬퍼 `_append_child`로 정리했습니다. 이제 `cell.text = ...`와 `paragraph.add_run(..., bold=True)`가 monkey-patch 없이 정상 동작합니다 (#30, [@hhy827](https://github.com/hhy827)).
- `_paragraph_id` / `_object_id` / `_memo_id`가 `uuid4().int & 0xFFFFFFFF`로부터 signed int32 범위를 벗어나는 값을 약 50% 확률로 생성하던 문제를 수정했습니다. id 값을 signed 32-bit 양수 범위(`0 <= x < 2^31`)로 클램프해 downstream 소비자와의 상호운용성을 확보했습니다 (#34, [@seonghoony](https://github.com/seonghoony)).
- `HwpxDocument.new()`의 seed로 쓰이는 번들 `Skeleton.hwpx`에 signed int32 범위를 벗어나는 `<hp:p id="3121190098">`가 포함돼 있던 문제를 수정했습니다 (#35, [@seonghoony](https://github.com/seonghoony)).
- `pyproject.toml`에 PEP 639 `license` expression과 같이 남아 있던 legacy `License :: OSI Approved :: Apache Software License` classifier를 제거해 `setuptools>=77`에서의 소스 설치/바이너리 빌드 실패를 해소했습니다.

### 추가
- 위 세 버그에 대한 회귀 테스트를 추가했습니다 (`tests/test_document_formatting.py`, `tests/test_id_generator_range.py`, `tests/test_skeleton_template_ids.py`).
- 머지된 기여를 인정하는 `CONTRIBUTORS.md`를 추가하고 `README.md` / `CONTRIBUTING.md`에서 연결했습니다.

### 변경
- License relicensed to Apache-2.0 (sole author, full consent). Previous license terms no longer apply to future releases.

## [2.9.0] - 2026-04-02
### 추가
- `HwpxDocument.get_table_map()`, `find_cell_by_label()`, `fill_by_path()`를 추가해 HWPX 양식/템플릿 표를 문서 순서 기반으로 탐색하고 채울 수 있게 했습니다.
- `hwpx.tools.table_navigation` 모듈을 추가해 엔진 레벨에서 재사용 가능한 표 탐색, 라벨 정규화, 방향 이동, 배치 채우기 helper를 공개했습니다.

### 변경
- 라벨 매칭이 공백 축약, 대소문자 무시, 후행 콜론 허용 규칙을 따르도록 정규화 로직을 추가했습니다.
- 표 자동화 API에 대한 회귀 테스트와 README/API 레퍼런스 문서를 추가했습니다.

## [2.8.3] - 2026-03-10
### 변경
- 저장소와 배포 메타데이터의 라이선스 표기를 실제 `LICENSE` 파일과 일치하도록 정렬했습니다.
- `pyproject.toml`을 PEP 639 방식의 `LicenseRef-python-hwpx-NonCommercial` + `license-files` 구성으로 갱신하고, 잘못된 MIT 분류자를 제거했습니다.
- README 라이선스 배지/섹션을 커스텀 비상업적 라이선스 기준으로 수정하고, wheel/sdist 산출물의 라이선스 메타데이터를 검증하는 회귀 테스트를 추가했습니다.

## [2.8.2] - 2026-03-08
### 변경
- README를 현재 공개 API와 CLI 범위에 맞춰 정리했습니다. Quick start, 텍스트 추출, 객체 검색 예시를 실제 호출 방식 기준으로 수정했습니다.
- `add_memo()`/`add_memo_with_anchor()`가 `HwpxDocument.new()`로 만든 실제 `lxml` 기반 문서에서도 동작하도록 memo XML 생성 경로를 엔진 호환 방식으로 정리했습니다.
- 실제 빈 문서 템플릿에서 메모 추가 후 roundtrip 되는 회귀 테스트를 추가했습니다.

## [2.8.1] - 2026-03-08
### 추가
- 템플릿 자동화 회귀 스위트를 추가했습니다 (`tests/template_automation/`). 단순 토큰, 반복 토큰, split-run, 공백 정규화, 표/머리글/바닥글/다중 섹션, 체크박스 토글, extract-repack, 비표준 rootfile 패턴을 대표 fixture + 시나리오 계약으로 점검합니다.
- `DevDoc/template-automation-regression-suite.md`를 추가해 스위트의 보장 범위, 한계, fixture 추가 절차를 문서화했습니다.

### 변경
- 실제 `lxml` 기반 문서에서 `set_header_text()`/`set_footer_text()`가 동작하도록 header/footer 생성 경로를 XML 엔진 호환 방식으로 정리했습니다.
- 섹션 속성(`secPr`)이 비어 있을 때 보강 생성하는 경로를 XML 엔진 호환 방식으로 정리했습니다.
- `add_section()`이 새 섹션을 잘못된 네임스페이스로 만들던 문제를 수정했습니다.
- mypy/pyright gradual scope에 이번에 추가한 template automation helper/generator 모듈을 포함했습니다.
## [2.8] - 2026-03-08
### 변경
- `HwpxPackage`와 OXML 로딩/저장이 rootfile/manifest-relative 경로를 실제로 따르도록 정렬했습니다.
- `hwpx-analyze-template --extract-dir`가 재구성에 바로 쓸 수 있는 작업 디렉터리와 `.hwpx-pack-metadata.json`을 생성하도록 확장했습니다.
- `hwpx-validate-package`를 엔진 정합 기준으로 재작성해 dynamic rootfile/manifest 관계, CRC, fallback warning을 구분하도록 했습니다.
- `hwpx-unpack` 기본값을 raw-byte preserving으로 바꾸고 `--pretty-xml` opt-in을 추가했습니다.
- tooling/OPC 회귀 테스트를 확대하고, coverage threshold를 60으로 올렸으며, pyright는 touched OPC/tooling 범위에서 `basic`으로 상향했습니다.

## [2.7.1] - 2026-03-08
### 변경
- 공개 저장소와 배포 산출물에서 내부 감사 문서를 제거했습니다.

## [2.7] - 2026-03-08
### 추가
- `hwpx-unpack`, `hwpx-pack`, `hwpx-analyze-template` CLI를 추가했습니다.
- `src/hwpx/tools/archive_cli.py`를 추가해 unpack/pack 워크플로를 패키지 레벨 도구로 승격했습니다.
- unpack 시 `.hwpx-pack-metadata.json`을 기록하고, pack 시 이를 사용해 원본 ZIP 엔트리 순서/압축 방식을 가능한 범위에서 보존하도록 했습니다.
- `src/hwpx/tools/template_analyzer.py`를 추가했습니다.

### 변경
- `scripts/office/unpack.py`, `scripts/office/pack.py`, `scripts/analyze_template.py`를 패키지 도구 래퍼로 정리했습니다.
- `page_guard`에 shape/control count 및 히스토그램 비교를 추가하고, 실제 페이지 수 계산기가 아니라 구조 변화 징후 점검 도구임을 문서와 CLI 설명에 명시했습니다.
- README와 `docs/usage.md`에 새 CLI 사용 예시를 추가했습니다.
- 새 tooling에 대한 CLI/추출/overwrite/page-guard 회귀 테스트를 강화했습니다.

## [2.6] - 2026-03-08
### 추가
- `hwpx-validate-package` CLI와 `hwpx.tools.package_validator`를 추가해 ZIP/OPC/HWPX 패키지 구조, `mimetype`, `container.xml`, manifest/spine 참조, XML well-formedness를 점검할 수 있게 했습니다.
- `hwpx-page-guard` CLI와 `hwpx.tools.page_guard`를 추가해 섹션 수, 단락 수, page/column break, 표 구조, 텍스트 길이 변화량을 기준으로 문서 드리프트를 비교할 수 있게 했습니다.
- `hwpx-text-extract` CLI를 추가해 기존 `TextExtractor` 기능을 plain/markdown 형태로 바로 사용할 수 있게 했습니다.
- `scripts/office/unpack.py`, `scripts/office/pack.py`, `scripts/analyze_template.py`를 추가해 XML-first HWPX 작업 흐름을 지원합니다.
- gap-closure 반영분에 대한 테스트를 추가했습니다 (`tests/test_gap_closure_tools.py`).

### 수정
- `HwpxDocument.validate()`가 내부 직렬화 과정에서 dirty 상태를 지워 버리던 부작용을 제거해, 검증 이후에도 저장 필요 상태가 유지되도록 수정했습니다.

## [2.3.1] - 2026-02-28
### 추가
- **단락 삭제 API**: `paragraph.remove()`, `section.remove_paragraph()`, `document.remove_paragraph()` 메서드를 추가했습니다. 마지막 단락 삭제 시 `ValueError`가 발생합니다.
- **섹션 추가/삭제 API**: `document.add_section(after=)`, `document.remove_section()` 메서드를 추가했습니다. 새 섹션은 manifest/spine에 자동 등록되며, 마지막 섹션 삭제 시 `ValueError`가 발생합니다.
- **네임스페이스 상수 모듈**: `hwpx.oxml.namespaces` 모듈을 추가하여 HP, HH, HC 등 공유 네임스페이스 상수를 제공합니다.
- 새 API에 대한 16개 테스트 케이스를 추가했습니다 (`test_paragraph_section_management.py`).

### 수정
- `import hwpx`만으로 `DeprecationWarning`이 발생하던 문제를 수정했습니다. `hwpx.package` 경고는 이제 사용자가 직접 해당 모듈을 import할 때만 표시됩니다.
- `HwpxOxmlTableCell.text`가 셀에 여러 단락이 있을 때 첫 번째 텍스트만 반환하던 버그를 수정했습니다. 모든 `<hp:t>` 요소의 텍스트를 결합하여 반환합니다.
- `add_hyperlink()` 메서드에서 사용되지 않는 `field_inst_id` 변수를 제거했습니다.
- deprecated `save()` 호출을 사용하던 테스트 코드를 `save_to_path()`/`save_to_stream()`으로 업데이트했습니다.

## [1.9] - 2026-02-18
### 변경
- `hwpx.__version__` 하드코딩 값을 제거하고 `importlib.metadata.version("python-hwpx")` 기반으로 노출하도록 정리했습니다.
- editable/로컬 소스 실행처럼 배포 메타데이터가 없는 환경에서도 동작하도록 `PackageNotFoundError` fallback(`0+unknown`)을 추가했습니다.

## [0.1.0] - 2025-09-17
### 추가
- `hwpx.opc.package.HwpxPackage`와 `hwpx.document.HwpxDocument`를 포함한 핵심 API를 공개했습니다.
- 텍스트 추출, 객체 탐색, 문서 유효성 검사 등 도구 모듈과 `hwpx-validate` CLI를 제공합니다.
- HWPX 스키마 리소스와 예제 스크립트를 번들링해 바로 사용할 수 있도록 했습니다.
- 설치 가이드, 사용 예제, 스키마 개요 등 배포 문서를 정리했습니다.
