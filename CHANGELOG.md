# 변경 로그

모든 중요한 변경 사항은 이 문서에 기록됩니다. 형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)과 [Semantic Versioning](https://semver.org/lang/ko/)을 따릅니다.

## [Unreleased]
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
