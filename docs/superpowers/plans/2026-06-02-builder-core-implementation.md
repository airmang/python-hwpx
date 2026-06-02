# 빌더 토대 1 - hwpx.builder 코어 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `python-hwpx`의 검증된 `HwpxDocument` facade 위에 docx-js급 조립형 생성 API `hwpx.builder`를 만든다. 빌더는 `Document/Section/Paragraph/Run/Heading/Bullet/NumberedList/Table/Image/Header/Footer/PageNumber/PageBreak/Metadata/PageSize/Margins`를 공개하고, OWPML ID 테이블 관리는 엔진/facade가 맡게 한다. S-013은 TOC와 document_plan.v2 재루팅을 제외한 빌더 코어 첫 수직 슬라이스를 끝낸다.

**Architecture:** builder 노드는 의도 중심 dataclass 모델이다. `hwpx.builder.Document.lower()`가 새 `HwpxDocument`를 만들고 오직 공개 facade와 명명된 엔진 wrapper만 호출한다. facade로 표현되지 않는 빈틈은 builder 내부 XML 조작이 아니라 `src/hwpx/document.py`와 `src/hwpx/oxml/document.py`의 명명된 신규 메서드로 올린다. `hwpxlib` 샘플 코퍼스는 코드/구조 포팅 없이 샘플 데이터만 clean-room oracle로 참조한다.

**Tech Stack:** Python 3.10+, dataclasses, lxml, pytest, existing `HwpxDocument`, `validate_document`, `validate_package`, S-012 `tests/fixtures/hwpxlib_corpus`, `hwpx-skill/scripts/visual_review.py`. 테스트 명령은 `uv run --extra dev pytest`.

**개발 환경:**
- python-hwpx 루트: `/Users/wilycastle/Code/projects/hwpx/python-hwpx`
- hwpx-skill 루트: `/Users/wilycastle/Code/projects/hwpx/hwpx-skill`
- 작업 브랜치: `feat/s013-builder-core` (S-012 브랜치 `feat/s012-oracle-foundation`에서 생성)
- 전체 테스트: `cd /Users/wilycastle/Code/projects/hwpx/python-hwpx && uv run --extra dev pytest -q`
- 단일 테스트: `uv run --extra dev pytest tests/test_<name>.py::<test> -v`
- Computer Use 검증 산출물(커밋 금지): `python-hwpx/work/s013-builder-core/`

**Legal boundary (clean-room):** hwpxlib(neolord0, Apache-2.0)의 코드, 함수 구조, 구현 흐름은 복사/번역 포팅하지 않는다. S-012가 벤더링한 `.hwpx` 샘플 데이터만 열어 생성 결과와 구조를 비교한다. 대응 토큰은 샘플 파일의 동작/출력 구조 관찰로 확정한다.

---

## Stage Context

- Wily Stage: `STG-d79e63646ee9` (display `S-013`) - 빌더 토대 1.
- 선행 Stage: `STG-3611d648b9d9` (display `S-012`) - MCP 기준 `status=done`, `plan_status=planned`.
- S-013 MCP 상태 확인: `status=draft`, `plan_status=needs_plan`, dependency `STG-3611d648b9d9`.
- 승인 게이트: 이 문서 작성 후 멈춘다. 사용자 승인 전에는 테스트 추가, 소스 수정, lifecycle claim/plan/complete를 하지 않는다.

## 검증된 사실 (현재 소스 기준)

- 설계 원칙: builder는 공개 `HwpxDocument` facade만 호출해야 하며, 불가능한 빈틈은 facade/oxml의 명명된 신규 메서드로 추가한다(`docs/2026-06-02-hwpx-builder-design.md:129-135`).
- 설계 §6의 1차 공개 노드는 `Document`, `Section`, `PageSize`, `Margins`, `Metadata`, `Heading`, `Paragraph`, `Run`, `Bullet`, `NumberedList`, `Table`, `Image`, `Header`, `Footer`, `PageNumber`, `PageBreak`다(`docs/2026-06-02-hwpx-builder-design.md:143-188`).
- 설계 §7의 5개 엔진 빈틈은 자동 쪽번호, 리치 header/footer, rich run style, 다단계 numbering/list, table merge/shading/width다(`docs/2026-06-02-hwpx-builder-design.md:196-204`).
- 설계 §9는 `visual_review.py` 증거 계약에 `visual_review_required`를 연결하고, 축 A(복구 다이얼로그 없이 열림 + save->reload)와 축 B(시각 레이아웃)를 구분한다(`docs/2026-06-02-hwpx-builder-design.md:257-267`).
- 설계 §10 수직 슬라이스는 metadata, A4+margin, rich header+page number, footer, Heading 1/2, mixed runs, multilevel bullets, merged/shaded/width table, image, PageBreak를 포함한다(`docs/2026-06-02-hwpx-builder-design.md:271-283`). 단, §10의 document_plan.v2 JSON parity는 S-013 MCP scope와 Done 게이트에 없으므로 S-014+로 넘긴다.
- S-012 계획 형식은 헤더, REQUIRED SUB-SKILL, Goal/Architecture/Tech Stack/개발환경, 검증된 사실, File Structure, Phase/Task, Stage 완료 게이트를 사용한다(`docs/superpowers/plans/2026-06-02-builder-oracle-foundation-implementation.md:1-46`).
- S-012 산출물: `tests/fixtures/hwpxlib_corpus`에는 `.hwpx` 47개가 있고, manifest에 `reader_writer__HeaderFooter.hwpx`, `PageFunctions`, `PageSize_Margin`, `SimplePicture`, `SimpleTable`가 기록되어 있다(`tests/fixtures/hwpxlib_corpus/manifest.json:104-225`).
- `HwpxDocument.open()`과 `HwpxDocument.new()`는 공개 생성 진입점이다(`src/hwpx/document.py:107-131`).
- `HwpxDocument.ensure_run_style()` facade는 현재 `bold/italic/underline/base_char_pr_id`만 받는다(`src/hwpx/document.py:565-580`). oxml 구현도 동일한 세 플래그만 비교/생성한다(`src/hwpx/oxml/document.py:4519-4591`).
- `HwpxOxmlParagraph.add_run()`은 style id가 없으면 document의 `ensure_run_style(bold, italic, underline)`만 호출한다(`src/hwpx/oxml/document.py:2931-2966`).
- `HwpxDocument.add_paragraph()`는 section 선택, para/style/charPr ref, raw paragraph attrs를 받는 공개 facade다(`src/hwpx/document.py:667-704`).
- `HwpxDocument.add_table()`은 rows/cols/width/height/border fill/style refs를 받고 `HwpxOxmlTable`을 반환한다(`src/hwpx/document.py:706-746`). 기존 table은 `cell().text`, `set_span()`, `set_size()` 같은 oxml wrapper 기능이 있다(`src/hwpx/oxml/document.py:2083-2120`, `src/hwpx/oxml/document.py:2522-2524`).
- `set_header_text()`/`set_footer_text()`는 text-only facade다(`src/hwpx/document.py:1070-1106`). oxml wrapper의 `text` setter는 기존 subList를 지우고 단일 텍스트 paragraph로 바꾼다(`src/hwpx/oxml/document.py:642-653`).
- 현재 `HwpxDocument` facade에는 `set_page_size`/`set_page_margins`가 없다. 실제 page size/margin 구현은 `section.properties.set_page_size()`와 `set_page_margins()`에 있다(`src/hwpx/oxml/document.py:709-788`).
- `HwpxDocument.add_image()`는 ZIP/manifest/header binData 등록 후 manifest item id만 반환한다. 본문에 `<hp:pic>`를 배치하는 공개 facade는 아직 없다(`src/hwpx/document.py:1159-1215`).
- 기존 `HwpxDocument.save_to_path()`는 path를 저장하고 같은 path 또는 package result를 반환한다(`src/hwpx/document.py:1329-1336`). 이 계약은 `tests/test_document_save_api.py:20-27`가 지킨다. S-013의 report 반환은 builder `Document.save_to_path()`에만 추가한다.
- `ValidationReport.ok`는 hard error가 없으면 schema warning이 있어도 true다(`src/hwpx/tools/validator.py:61-73`). `PackageValidationReport.ok`도 error 기준이다(`src/hwpx/tools/package_validator.py:58-73`).
- `hwpx-skill/scripts/visual_review.py`에는 S-012 축 A 함수 `structural_acceptance()`가 있고 open + save->reopen round-trip을 evidence에 넣는다(`hwpx-skill/scripts/visual_review.py:75-95`, `hwpx-skill/scripts/visual_review.py:252-289`).
- `authoring.py`의 document_plan은 현재 bullets에서 style을 버리고 table에서 caption/columns/rows만 보존한다(`src/hwpx/authoring.py:866-878`). heading render는 level별 처리 없이 `tokens["heading"]`만 쓴다(`src/hwpx/authoring.py:941-947`). 이 한계는 builder 일반화로 해결하고 S-013에서 authoring.py를 패치하지 않는다.

## File Structure

- Create: `src/hwpx/builder/__init__.py` - 공개 node export.
- Create: `src/hwpx/builder/core.py` - builder node dataclasses, lowering, unit conversion, report orchestration.
- Create: `src/hwpx/builder/report.py` - `BuilderSaveReport`, validation/reopen result helpers.
- Modify: `src/hwpx/document.py` - 명명된 facade 보강: page size/margins, rich run style args, rich header/footer content, page-number field entry, numbering, table wrapper, picture placement.
- Modify: `src/hwpx/oxml/document.py` - 실제 oxml wrapper 구현. Builder가 직접 XML을 만지지 않게 여기에만 토큰 구현.
- Create: `tests/test_builder_core.py` - node 단위와 facade 보강 RED/GREEN.
- Create: `tests/test_builder_vertical_slice.py` - §10 slice, hard gates, hwpxlib sample 구조 대조, text/table rollback.
- Generated only, do not commit: `work/s013-builder-core/builder_vertical_slice.hwpx`, `work/s013-builder-core/visual_review/*`.

No changes in S-013:
- `src/hwpx/authoring.py` (document_plan v2/re-routing is follow-up).
- `hwpx-skill/scripts/visual_review.py` (S-012 already added axis A; this Stage only invokes it).
- Existing proposal/form-fill/document_plan tests except as regression commands.

---

## Execution Protocol

After user approval only:

- [ ] Run branch/status preflight and record dirty files without reverting unrelated changes.
- [ ] For each Task below: write failing test first (RED), run the narrow test and confirm FAIL, implement the minimal GREEN, run narrow PASS, run full `uv run --extra dev pytest -q`, commit only files listed in that Task, then move to the next Task.
- [ ] Never batch multiple Tasks into one commit.
- [ ] For every Task, append one-line RED/GREEN evidence to the working notes and final report.
- [ ] **Discovery-first for OWPML gap Tasks (5, 7, 8):** these reverse-engineer OWPML from samples, so the expected output is unknown until inspected. Each starts with a **SPIKE** step that unzips the relevant `tests/fixtures/hwpxlib_corpus` sample, dumps the target XML (element/attribute/parent shape), and pins it as a comment in the test/Task before any RED assertion. A RED test cannot assert structure you have not yet discovered. Observe sample *output* only — never read or port hwpxlib code (clean-room).

---

## Phase 1 - Builder Core Shell and Save Report

### Task 1: Public builder package + minimal paragraph/page-break lower

**Objective:** Create `hwpx.builder` import surface and make a tiny builder document save/reopen with report, without rich formatting yet.

**Files:**
- Create: `src/hwpx/builder/__init__.py`
- Create: `src/hwpx/builder/core.py`
- Create: `src/hwpx/builder/report.py`
- Create/modify: `tests/test_builder_core.py`

- [ ] **RED:** Add tests importing all §6 public nodes and saving `Document(sections=[Section(children=[Paragraph(text="hello"), PageBreak(), Paragraph(text="after")])])`.
- [ ] **RED 확인:** `uv run --extra dev pytest tests/test_builder_core.py::test_builder_public_nodes_and_basic_save_report -v` fails on missing `hwpx.builder`.
- [ ] **GREEN:** Add minimal dataclasses and lower to `HwpxDocument.new()`, `add_paragraph()`, and `add_paragraph("", pageBreak="1")`.
- [ ] **GREEN:** Add builder-only `Document.save_to_path(path) -> BuilderSaveReport`; it calls facade `HwpxDocument.save_to_path(path)`, `validate_package(path)`, `validate_document(path)`, and `HwpxDocument.open(path)`.
- [ ] **PASS:** Narrow test passes and full pytest passes.
- [ ] **Commit:** `feat(builder): add public builder shell and save report baseline`

Expected public shape:

```python
from hwpx.builder import Document, Section, Paragraph, PageBreak

report = Document(sections=[Section(children=[Paragraph(text="hello")])]).save_to_path(path)
assert report.validate_package.ok
assert report.validate_document.ok
assert report.reopened.ok
```

### Task 2: Section page setup + Metadata front matter

**Objective:** Make `Section(page=PageSize.A4, margins=Margins(...))` lower through facade-only calls and make `Metadata` observable without hidden XML guesses.

**Files:**
- Modify: `src/hwpx/document.py`
- Modify: `src/hwpx/builder/core.py`
- Modify: `tests/test_builder_core.py`

- [ ] **RED:** Add tests that `HwpxDocument` exposes `set_page_size()`/`set_page_margins()` facade methods and builder section applies A4 + margins to the first section.
- [ ] **RED:** Add test that `Metadata(title, author, organization)` becomes visible front matter text/table in the generated document and is recorded in `BuilderSaveReport.metadata`.
- [ ] **RED 확인:** Narrow tests fail because facade methods and metadata lowering do not exist.
- [ ] **GREEN:** Add `HwpxDocument.set_page_size()` and `set_page_margins()` delegating to selected section properties. Do not expose oxml in builder.
- [ ] **GREEN:** Implement `PageSize.A4`, `Margins(...mm)`, `Metadata`; for S-013, metadata lowers to visible front matter using existing paragraph/table facade, not unverified hidden document-property XML. (알려진 한계: 진짜 OWPML 문서 속성(`head`의 docProperties 등) 매핑은 후속 — 본 Stage는 본문 가시화로 충분.)
- [ ] **PASS:** Narrow tests and full pytest pass.
- [ ] **Commit:** `feat(builder): lower section page setup and metadata`

---

## Phase 2 - Run and Heading Formatting

### Task 3: Rich Run formatting and charPr auto-management

**Objective:** Extend run style management for `bold/italic/underline/color/font/size/highlight/strike` and make builder `Run` consume it.

**Files:**
- Modify: `src/hwpx/document.py`
- Modify: `src/hwpx/oxml/document.py`
- Modify: `src/hwpx/builder/core.py`
- Modify: `tests/test_builder_core.py`

- [ ] **RED:** Add tests for `document.ensure_run_style(color="C00000", font="함초롬바탕", size=12, highlight="FFFF00", strike=True)` and for `Paragraph(children=[Run(...), Run(...rich...)])`.
- [ ] **RED:** Assert generated charPr includes the requested properties and that a reopened document preserves the styled run reference.
- [ ] **RED 확인:** Tests fail because current facade only accepts bold/italic/underline.
- [ ] **GREEN:** Extend facade and oxml signatures. Derive exact child/attribute tokens by inspecting S-012 sample data only; do not read/copy hwpxlib code.
- [ ] **GREEN:** Update `HwpxOxmlParagraph.add_run()` to forward the richer args when no explicit `char_pr_id_ref` exists.
- [ ] **PASS:** Narrow tests, `tests/test_document_formatting.py`, `tests/test_document_plan.py`, and full pytest pass.
- [ ] **Commit:** `feat(builder): support rich run char styles`

### Task 4: Heading per-level node lowering

**Objective:** Implement `Heading(level=1/2/3, text=...)` as distinct builder semantics, with level-aware styling and stable text rollback.

**Files:**
- Modify: `src/hwpx/builder/core.py`
- Modify: `tests/test_builder_core.py`

- [ ] **RED:** Add tests that Heading 1 and Heading 2 lower to paragraphs with distinct style ids or style attributes, and reopened `export_text()` preserves heading order.
- [ ] **RED 확인:** Tests fail because Heading is not implemented or is not level-aware.
- [ ] **GREEN:** Add builder heading style registry using `HwpxDocument.ensure_run_style()` only. Keep this Task charPr-based; paragraph outline/TOC semantics are follow-up unless required by tests.
- [ ] **PASS:** Narrow tests and full pytest pass.
- [ ] **Commit:** `feat(builder): add level-aware heading nodes`

---

## Phase 3 - Lists and Numbering

### Task 5: Bullet and NumberedList multi-level numbering

**Objective:** Add `Bullet(level=...)` and `NumberedList(level=...)` with engine-level `ensure_numbering()`/paragraph property references.

**Files:**
- Modify: `src/hwpx/document.py`
- Modify: `src/hwpx/oxml/document.py`
- Modify: `src/hwpx/builder/core.py`
- Modify: `tests/test_builder_core.py`

- [ ] **SPIKE(발견):** 코퍼스에서 다단계 목록/번호를 쓰는 샘플(예: `reader_writer__sample1.hwpx`, `tool__textextractor__ParaHead.hwpx` 등 — unzip 후 `header.xml`의 `refList`/numbering·bullet, `section*.xml`의 `paraPr`/`numberingIDRef`·`paraPrIDRef` 보유 파일을 찾는다)을 unzip해 numbering/bullet 정의와 문단의 level 참조 구조(요소·속성·부모관계)를 덤프하고, 목표 OWPML 구조를 이 Task에 주석으로 고정한다. 적합 샘플이 없으면 그 사실과 대안(최소 numbering 정의 자작)을 기록한다. (샘플 출력만 관찰 — clean-room.)
- [ ] **RED:** Add tests that `HwpxDocument.ensure_numbering(kind="bullet", levels=...)` creates/reuses header refList numbering/bullet structures and returns paragraph property ids for levels.
- [ ] **RED:** Add builder tests for multilevel Bullet/NumberedList that inspect generated paragraph refs and reopened text.
- [ ] **RED 확인:** Tests fail because no `ensure_numbering()` facade exists.
- [ ] **GREEN:** Implement named facade `ensure_numbering()` and oxml helpers for numbering/bullet and `paraProperties` references using hwpxlib corpus samples as structural oracle.
- [ ] **GREEN:** Builder calls only `HwpxDocument.ensure_numbering()` plus `add_paragraph(..., para_pr_id_ref=...)`.
- [ ] **PASS:** Narrow tests and full pytest pass.
- [ ] **Commit:** `feat(builder): add multilevel list numbering facade`

---

## Phase 4 - Tables

### Task 6: Table merge, header shading, and column widths

**Objective:** Make `Table(header=, rows=, column_widths=, header_shading=, merges=)` lower through named table wrappers, not direct builder XML.

**Files:**
- Modify: `src/hwpx/document.py`
- Modify: `src/hwpx/oxml/document.py`
- Modify: `src/hwpx/builder/core.py`
- Modify: `tests/test_builder_core.py`

> 입자 분할(S-1): 병합/음영/열너비를 3개 독립 RED→GREEN→Commit 사이클(6a/6b/6c)로 나눈다. 각 사이클은 narrow + full pytest 통과 후 단독 커밋한다.

- [ ] **SPIKE(발견):** `tests/fixtures/hwpxlib_corpus/reader_writer__SimpleTable.hwpx`를 unzip해 `section*.xml`에서 셀 병합(`cellSpan`/`colSpan`·`rowSpan`), 셀 크기·열 너비(`cellSz`/`cellMargin`/grid), 배경 음영/테두리(`borderFill`/`fillBrush` 계열)의 요소·속성·부모관계를 덤프하고, 목표 구조를 이 Task에 주석으로 고정한다. 기존 `set_span()`(L43)·`set_size()`가 무엇을 이미 쓰는지도 대조한다. (샘플 출력만 관찰 — clean-room.)

**6a) 셀 병합**
- [ ] **RED:** 스프레드시트 병합 표기(`"A2:A3"`, `"A1:C1"`) → `cellSpan`/spans 단언 + reopened 셀 텍스트 단언. 현재는 고수준 병합 wrapper 없음(`set_span`만)이라 실패.
- [ ] **GREEN:** 명명된 wrapper `HwpxOxmlTable.merge_cells(range)` 추가(내부적으로 기존 `set_span` 활용). Builder `Table`이 range를 파싱해 호출, XML 직접 조작 금지.
- [ ] **PASS:** narrow + `tests/test_split_merged_cell.py` + full pytest.
- [ ] **Commit:** `feat(builder): add table cell merge wrapper`

**6b) 헤더 음영**
- [ ] **RED:** `header_shading="EAF1FB"` → 해당 셀 borderFill/fill 노드가 SPIKE에서 고정한 구조와 일치하는지 단언.
- [ ] **GREEN:** 명명된 wrapper `set_cell_shading()`(+필요 시 borderFill 자동 할당). Builder가 호출.
- [ ] **PASS:** narrow + `tests/test_tables_default_border.py` + full pytest.
- [ ] **Commit:** `feat(builder): add table cell shading wrapper`

**6c) 열 너비 + Builder Table 통합**
- [ ] **RED:** `column_widths=[2,3,1]` 가중치 → 열 너비/grid 단언 + Builder `Table(header=,rows=,column_widths=,header_shading=,merges=)` 통합 생성·reopen·셀 텍스트 rollback 단언.
- [ ] **GREEN:** `set_column_widths()` wrapper + Builder `Table` 통합(값 쓰기→merge→shading→widths 순). XML 직접 조작 금지.
- [ ] **PASS:** narrow + `tests/test_table_navigation.py` + full pytest.
- [ ] **Commit:** `feat(builder): add table column widths and integrate builder Table`

---

## Phase 5 - Images

### Task 7: Image placement node

**Objective:** Make `Image(path|bytes, width_mm, align, caption)` register binData and place an actual picture object in the body.

**Files:**
- Modify: `src/hwpx/document.py`
- Modify: `src/hwpx/oxml/document.py`
- Modify: `src/hwpx/builder/core.py`
- Modify: `tests/test_builder_core.py`

- [ ] **SPIKE(발견):** `tests/fixtures/hwpxlib_corpus/reader_writer__SimplePicture.hwpx`를 unzip해 본문 `<hp:pic>`(또는 그림 컨테이너) 요소의 구조 — `binaryItemIDRef`, 크기/위치 속성, 부모 run/paragraph 관계 — 와 header binItem/manifest 등록 구조를 덤프하고, 목표 OWPML 구조를 이 Task에 주석으로 고정한다. RED는 이 고정 구조를 기댓값으로 단언한다. (샘플 출력만 관찰 — clean-room.)
- [ ] **RED:** Add tests that builder `Image` produces package `BinData`, header binItem, manifest item, and a body picture object referencing the binary item.
- [ ] **RED:** Add sample diff assertion against `reader_writer__SimplePicture.hwpx` for `binaryItemIDRef`/picture structure presence.
- [ ] **RED 확인:** Tests fail because `HwpxDocument.add_image()` only returns a manifest item id and there is no body placement facade.
- [ ] **GREEN:** Add named facade `add_picture()` or `insert_image()` that composes existing `add_image()` with an oxml picture wrapper.
- [ ] **GREEN:** Builder uses only the new facade; captions are normal paragraphs.
- [ ] **PASS:** Narrow tests and full pytest pass.
- [ ] **Commit:** `feat(builder): add image placement facade`

---

## Phase 6 - Header, Footer, and Page Numbers

### Task 8: Rich Header/Footer content + automatic PageNumber

**Objective:** Implement `Header/Footer(children=[Paragraph(...Run..., PageNumber())])` and `PageNumber(format="page/total")` with named engine methods.

**Files:**
- Modify: `src/hwpx/document.py`
- Modify: `src/hwpx/oxml/document.py`
- Modify: `src/hwpx/builder/core.py`
- Modify: `tests/test_builder_core.py`

- [ ] **SPIKE(발견):** `reader_writer__PageFunctions.hwpx`(쪽번호)와 `reader_writer__HeaderFooter.hwpx`(머리글/바닥글)를 unzip해 ① 자동 쪽번호 필드 토큰(`hp:ctrl`/`fieldBegin` type 또는 autoNum 계열 요소·속성)과 ② header/footer subList 안의 paragraph/run/그림 구조를 덤프하고, 목표 OWPML 구조를 이 Task에 주석으로 고정한다. 현 `set_header_text`/`set_footer_text`는 text-only이며 `text` setter가 subList를 단일 텍스트로 덮어쓴다(검증된 사실 L44)는 점을 기준으로, 리치 콘텐츠 helper가 그 파괴적 동작을 피하도록 설계한다. RED는 고정 구조를 기댓값으로 단언한다. (샘플 출력만 관찰 — clean-room.)
- [ ] **RED:** Add tests for `HeaderFooter.add_page_number_field()` at oxml wrapper level and facade-level `set_header_content()`/`set_footer_content()`.
- [ ] **RED:** Add builder tests comparing generated header/footer structures with `reader_writer__HeaderFooter.hwpx` and `reader_writer__PageFunctions.hwpx`.
- [ ] **RED 확인:** Tests fail because current header/footer facade is text-only.
- [ ] **GREEN:** Add `HwpxOxmlSectionHeaderFooter.add_page_number_field()` and rich content helpers. Add facade methods that accept simple content specs and create paragraphs/runs/page-number fields.
- [ ] **GREEN:** Builder converts its nodes to those content specs, then calls `HwpxDocument.set_header_content()`/`set_footer_content()`.
- [ ] **PASS:** Narrow tests, `tests/test_section_headers.py`, `tests/test_document_formatting.py`, and full pytest pass.
- [ ] **Commit:** `feat(builder): add rich header footer page numbers`

---

## Phase 7 - Report Hard Gates

### Task 9: Authoring-quality BuilderSaveReport

**Objective:** Complete builder `Document.save_to_path()` report fields required by S-013 while preserving existing `HwpxDocument.save_to_path()` behavior.

**Files:**
- Modify: `src/hwpx/builder/report.py`
- Modify: `src/hwpx/builder/core.py`
- Modify: `tests/test_builder_core.py`

- [ ] **RED:** Add tests for report fields: `path`, `validate_package.ok`, `validate_document.ok`, `validate_document.warnings`, `reopened.ok`, `hard_gates`, `visual_review_required`, `metadata`, and serializable `to_dict()`.
- [ ] **RED:** Add regression assertion that `HwpxDocument.save_to_path()` still returns the path as in `tests/test_document_save_api.py`.
- [ ] **RED 확인:** Tests fail because report is incomplete.
- [ ] **GREEN:** Implement report dataclasses and hard-gate summary. Hard gates include package validation, schema-lint separation, and reopen. **먼저 확인:** `package_validator`에 ID/reference 무결성 체크가 실제로 있는지 검증 — 없으면 hard_gates에서 "id_integrity": "unavailable"로 정직히 표기하고, 별도 ID 체커 구현은 본 Stage 범위 밖(후속)으로 둔다(태스크 팽창 방지). builder feature flags는 포함.
- [ ] **GREEN:** Set `visual_review_required=True` when the document contains layout-sensitive nodes (header/footer/page number/table/image/page break) or when explicitly requested.
- [ ] **PASS:** Narrow tests, `tests/test_document_save_api.py`, and full pytest pass.
- [ ] **Commit:** `feat(builder): return builder save quality report`

---

## Phase 8 - §10 Vertical Slice and Oracle Verification

### Task 10: First vertical slice integration test

**Objective:** Generate the full §10 document and prove it through hard gates, rollback, hwpxlib sample structure comparison, and Computer Use observed_pass evidence.

**Files:**
- Modify: `tests/test_builder_vertical_slice.py`
- Modify only if needed by failing slice: files from prior Tasks in `src/hwpx/builder/**`, `src/hwpx/document.py`, `src/hwpx/oxml/document.py`

- [ ] **RED:** Add integration test building one document with metadata, A4+margin, rich header with `PageNumber`, footer page/total, Heading 1/2, mixed run paragraph, multilevel Bullet, merged/shaded/width table, Image, and PageBreak.
- [ ] **RED:** The test must assert `save_to_path()` report gates, reopen, `export_text()`, table rollback, and sample structure comparison against HeaderFooter/PageFunctions/SimpleTable/SimplePicture.
- [ ] **RED 확인:** Test fails on missing final wiring or incomplete feature flags.
- [ ] **GREEN:** Fix only the minimal missing lowering/report behavior from prior Tasks.
- [ ] **PASS:** `uv run --extra dev pytest tests/test_builder_vertical_slice.py -v` and full pytest pass.
- [ ] **Computer Use:** Generate `work/s013-builder-core/builder_vertical_slice.hwpx`, open with `open -a "Hancom Office HWP" <file>`, observe no repair dialog, take screenshot, visually check header/page number/footer/table shading+merge/image/page break/no placeholders, close without saving.
- [ ] **visual_review evidence:** Run S-012 script to create `work/s013-builder-core/visual_review/hancom-observed-pass-evidence.json` with `current.status=="observed_pass"` and screenshot path.
- [ ] **PASS evidence:** If visual review finds defects, adjust builder input or implementation, regenerate, and repeat. Do not forge evidence.
- [ ] **Commit:** `test(builder): add vertical slice oracle integration`

Evidence command after Hancom observation (verified against `scripts/visual_review.py`: target is a **positional** arg; output flag is **`--evidence`**; `--viewer` accepts `none`/`auto`/`command:<cmd>` — there is no `hancom`/`--target`/`--output`). `observed_pass`는 존재하는 `--screenshot`, viewer!=none, 그리고 `--launch-viewer` 성공을 요구한다:

```bash
cd /Users/wilycastle/Code/projects/hwpx/hwpx-skill
SLICE=/Users/wilycastle/Code/projects/hwpx/python-hwpx/work/s013-builder-core
uv run python scripts/visual_review.py \
  "$SLICE/builder_vertical_slice.hwpx" \
  --viewer "command:open -a 'Hancom Office HWP'" \
  --launch-viewer \
  --status observed_pass \
  --screenshot "$SLICE/visual_review/screenshot.png" \
  --evidence "$SLICE/visual_review/hancom-observed-pass-evidence.json" \
  --observation "rich header page number visible; footer page/total; table shading+merge; image placed; page break; no placeholders"
```

(`--viewer`/`--launch-viewer` 인자 형식은 실행 전 `scripts/visual_review.py`의 `_viewer_command`/`parse_args`로 재확인한다. 복구 다이얼로그·결함이면 `--status needs_review`로 정직히 기록.)

---

## Regression Gate

Run before final completion:

```bash
cd /Users/wilycastle/Code/projects/hwpx/python-hwpx
uv run --extra dev pytest -q
uv run --extra dev pytest tests/test_document_plan.py tests/test_proposal_preset.py tests/test_form_fill_split_run.py -v
```

Confirm:

- [ ] Existing document_plan/proposal/form-fill tests remain green.
- [ ] Existing `HwpxDocument.save_to_path()` contract remains path-returning.
- [ ] Builder save report is only on `hwpx.builder.Document.save_to_path()`.
- [ ] No source edits outside File Structure.
- [ ] No unrelated dirty files are reverted or committed.

## Stage 완료 게이트

- [ ] `src/hwpx/builder/` package exists and exports all §6 first-slice nodes.
- [ ] Builder lower path is facade-only; builder code does not construct or mutate XML elements.
- [ ] Run formatting supports charPr auto-management for bold/italic/underline/color/font/size/highlight/strike.
- [ ] 5 gap reinforcements exist as named engine/facade methods: `HeaderFooter.add_page_number_field`, rich `set_header_content`/`set_footer_content`, extended `ensure_run_style`, `ensure_numbering`, table merge/shading/width wrappers.
- [ ] Each gap has tests using S-012 hwpxlib sample data as structural oracle and package/reopen hard gates.
- [ ] Builder `Document.save_to_path()` returns authoring-quality `BuilderSaveReport`; existing `HwpxDocument.save_to_path()` remains unchanged.
- [ ] §10 vertical slice integration test passes: save->reopen, structure hard gates, text/table rollback, hwpxlib cross-check.
- [ ] Computer Use + Hancom Office observation produces real `observed_pass` evidence with screenshot path, no repair dialog, and no visual defects in header/page number/footer/table/image/page break/placeholder checks.
- [ ] Full `uv run --extra dev pytest -q` passes.
- [ ] After implementation only: if Wily lifecycle tools are available, complete `STG-d79e63646ee9`; if only list/get tools remain available, report that lifecycle completion is unavailable.

