# 안정 API 표면 (Stable API)

`from hwpx import ...` 최상위 표면은 세 계층으로 나뉩니다. 계층에 따라 계약의
강도와 변경 예고 방식이 다릅니다.

## 계층 정책

- **stable** — `hwpx.__all__`에 있는 이름. 계약(시그니처·동작·반환 스키마)이 굳어
  있고, **major 경계에서만** 깨질 수 있습니다. 접근 시 경고가 없습니다.
- **experimental** — 계약이 **유동적**입니다. minor 릴리스에서 변경될 수 있으므로
  `from hwpx.experimental import ...`로 import하세요. 4.0~6.x가 경고와 함께 유지하던
  최상위 `from hwpx import ...` 재내보내기는 **7.0에서 제거됐습니다** — 접근하면
  `hwpx.experimental`을 알려 주는 `MovedToExperimental`(ImportError)이 납니다(실제 구현
  모듈·`hwpx.experimental` 경로는 유지).
- **deprecated** — 대체 경로로 이전하세요. 접근 시 `DeprecationWarning`이 나고 경고
  메시지에 대체 경로가 포함됩니다. **다음 major에서 제거**될 예정입니다.

### 최소 deprecation window

이름을 제거하려면 **먼저 한 번의 major에서 `DeprecationWarning`을 낸 뒤** 그다음
major에서 제거합니다(경고 없는 즉시 제거 금지). 4.0.0은 이 창을 여는 major였고
제거된 이름이 **0개**였습니다. 5.0.0은 그 창을 닫는 major로, 4.x에서 경고를 내던
deprecated 표면 4종을 제거합니다(아래 「5.0에서 제거된 deprecated 표면」).
응용 계층으로 옮겨 간 이름은 제거가 아니라 **이동**이며, import하면 어디로 갔는지
알려 주는 오류가 납니다 — [5.0 마이그레이션 가이드](migration-5.0.md) 참조.

### 반환되는 객체 — `hwpx.model` 이 계약이다 (6.0)

5.x 의 이 절은 자기모순이었다. `hwpx.oxml.*` 을 "공개 표면이 아니다"라고
선언하면서, stable 로 선언한 `HwpxDocument` 의 메서드들이 `HwpxOxmlParagraph`·
`HwpxOxmlTable`·`HwpxOxmlSection` 등 **18종을 반환**했다. 사용자는
"비공개"라고 적힌 타입을 손에 쥐고 그것으로 일할 수밖에 없었다.

6.0 은 이렇게 정리한다.

**`hwpx.model` 이 계약이고, `hwpx.oxml` 은 그것이 사는 곳이다.**

```python
from hwpx import model
from hwpx.oxml.paragraph import HwpxOxmlParagraph

assert model.Paragraph is HwpxOxmlParagraph   # 래퍼가 아니라 별칭이다
```

래퍼를 만들지 않은 이유: 객체 모델이 두 벌이 되고, 래퍼는 결국 `.oxml` 을
노출해야 하므로 같은 누출에 코드만 두 배가 된다. 반대로 `hwpx.oxml` 전체를
stable 로 올리면 24개 모듈 수백 멤버가 major 에서만 바뀔 수 있게 되어, 바로 그
클래스들에 요소를 더해야 하는 포맷 깊이 작업이 멈춘다.

**계약은 클래스가 아니라 멤버 목록이다.** 공개 표면 잠금 `tests/data/public_surface.json` 의
`model` 층이 클래스별로 stable 멤버(`members`, 서명까지)와 목록 밖 공개 이름(`internal`)을
정확히 나열한다. 수는 아래 「공개 표면 잠금」 표에 있다.

- 목록 **안**의 멤버 → stable. major 경계에서만 바뀐다.
- 목록 **밖**의 멤버(`apply_model`·`mark_dirty`·`remove_stale_layout_caches`
  등) → 구현 세부. minor 에서 바뀔 수 있다.

`hwpx.oxml.*` import 경로는 그대로 살아 있다. 옮기지도, deprecate 하지도 않는다.

### 지원되지 않는(비공개) 표면

`hwpx._document.*` 등 구현 모듈을 직접 import 하는 것은 공개 표면이 아니다.
`hwpx.oxml.*` 은 위 규칙을 따른다 — 경로는 열려 있고, 계약은 `hwpx.model` 의
멤버 목록이 정한다.

### 6.0 파사드 표면

`HwpxDocument` 의 공개 멤버는 **35개**다(5.x 는 102개, 6.0 출시 때는 34개). 35개는 공개
이름 31개와 지원 dunder 4개(`__init__`·`__repr__`·`__enter__`·`__exit__`)다. 나머지 79개는 도메인
네임스페이스로 이동했다. 6.x는 옛 이름을 `DeprecationWarning` 과 함께 남겨 두었고,
**7.0 에서 제거했다** — 부르면 새 자리를 알려 주는 `HwpxAttributeError`
(`document-name-removed`)가 난다. 같은 때 `section_index=`·`style_id_ref=` 인자도 없어졌다
(`hwpx-argument-removed`). 대응표는 [6.0 이주 가이드](migration-6.0.md).

지운 79개 이름의 안내 표는 `tests/data/document_legacy_shims.json` 이 잠근다.

### 공개 표면 잠금

공개 표면 전체를 파일 하나, `tests/data/public_surface.json` 이 잠근다. 멤버마다 종류,
인자(이름·위치/키워드·기본값 있음), 속성의 쓰기 가능 여부, 반환 표기를 적고,
`tests/test_public_surface.py` 가 설치본과 하나라도 다르면(늘어도 줄어도) 실패한다.

<!-- public-surface-lock:begin (scripts/public_surface_lock.py가 다시 쓴다. 손으로 고치지 않는다) -->
| 층 | 잠근 것 | 수 |
|---|---|---:|
| 최상위 `hwpx.__all__` | 이름(함수는 서명까지) | 29 |
| 루트 `HwpxDocument` | 공개 멤버와 지원 dunder 4개의 서명 | 35 |
| 묶음 11개(`doc.styles` …) | 멤버의 서명(꺼내기·세기 dunder 포함) | 189 |
| `hwpx.model` 22개 클래스 — 계약 | 멤버의 서명 | 376 |
| `hwpx.model` — 계약 밖 | 이름만(구현 세부, minor에서 바뀔 수 있다) | 164 |
| `hwpx.objects` 51개 값 형식 | 필드 238 · 멤버 104 · enum 값 10 | 352 |
| 모듈 수준 stable 이름(11개 모듈) | 서명(클래스는 멤버까지) | 66 |
<!-- public-surface-lock:end -->

공개 이름을 바꾸면 잠금을 손으로 고치지 않고 다시 만든다. 바뀐 것마다
`tests/data/public_surface_changes.jsonl` 에 까닭과 함께 한 줄이 남는다. 지우기·이름
바꾸기·서명 바꾸기는 패키지 메이저가 잠금의 `major` 보다 클 때만 받는다(다음 메이저를
만드는 동안에는 `--allow-major-break`). 자세한 절차는 [기여 안내](../CONTRIBUTING.md#공개-표면-잠금).

```bash
python scripts/public_surface_lock.py check                                  # 같은지 본다
python scripts/public_surface_lock.py check --update --reason "무엇을 왜"    # 다시 만든다
python scripts/public_surface_lock.py rebuild                                # git 병합 뒤
```

설치본에 직접 물어볼 수도 있다:

```bash
python -m hwpx.capabilities --verify
```

## 엔진 계약 (7.0)

python-hwpx는 파일에 적힌 대로 읽고 쓰는 엔진이다. 아래 아홉 가지를 약속하고, 약속마다
그것을 지키는 테스트를 적는다(`tests/test_engine_contract.py` 가 여기 적힌 테스트가 모두
있는지 확인한다). 약속은 major 경계에서만 바뀐다.

1. **같은 바이트는 같은 결과다.** 같은 바이트를 열면 몇 번을, 어느 프로세스에서 열어도 같은
   모델·같은 글을 읽고, 고치지 않고 저장하면 같은 바이트가 나온다.
   `tests/test_engine_contract.py::test_same_bytes_open_to_the_same_model_text_and_bytes`,
   `tests/test_engine_contract.py::test_same_bytes_give_the_same_answer_in_another_process`
2. **고치지 않은 저장은 바이트 그대로다.** 열고 고치지 않고 저장하면 모든 파트가 바이트 그대로다.
   대개 파일 전체가 같고, 몇몇은 ZIP 항목의 순서·플래그·폴더 항목만 다르다(공개·시험 HWPX 중
   열리는 1,299개: 1,112개는 파일째 같고 187개는 파트가 같다).
   `tests/test_engine_contract.py::test_an_unedited_hancom_document_saves_its_parts_unchanged`,
   `tests/test_mutation_report.py::test_noop_patch_save_reports_whole_package_identical`
3. **공개 편집은 그 파트만 바꾸고, 바꾼 파트를 알린다.** 공개 API로 고치면 그 내용을 담은 파트만
   바뀌고 나머지 파트는 바이트 그대로다. 바뀐 파트는 `MutationReport.changed_parts` 에 적힌다
   (`save_to_path(..., return_report=True)`).
   `tests/test_engine_contract.py::test_a_public_edit_changes_only_its_part_and_says_so`,
   `tests/test_mutation_report.py::test_one_cell_edit_patch_lists_dirty_section`
4. **성공한 저장은 열기 안전 검사를 통과한 것이다.** 저장(`to_bytes`·`save_to_path`·
   `save_to_stream`)은 산출물이 편집기 열기 안전 검사를 통과할 때만 끝나고, 통과하지 못하면
   아무것도 쓰지 않고 `open-safety-failed` 로 실패한다(있던 파일은 그대로 둔다).
   `tests/test_document_save_api.py::test_to_bytes_rejects_generated_package_that_fails_open_safety`,
   `tests/test_document_save_api.py::test_save_to_path_preserves_existing_file_when_open_safety_fails`
5. **"한/글에서 열린다"는 한/글 기록이 있는 것에만 말한다.** 한/글에서 열어 확인했다
   (Render-verified)는 말은 실제 한/글로 열어 본 기록(`docs/openrate/` 보고, 한컴 오라클
   측정)이 있는 만들기·편집 영역에만 붙는다([지원 매트릭스](support-matrix.md)).
   `tests/test_engine_contract.py::test_render_verified_claims_cite_real_hancom_evidence`
6. **모르는 요소는 읽은 대로 쓴다.** 엔진이 모르는 요소·속성(다른 이름공간의 요소, 새 버전의
   목록)은 그 파트를 다시 쓸 때도 이름공간·이름·속성·글·자식이 읽은 그대로 남는다(접두사
   이름은 바뀔 수 있다).
   `tests/test_engine_contract.py::test_unknown_elements_are_written_as_read`
7. **결정 모드에서는 만들기도 결정적이다.** `HwpxDocument.new(seed=, now=)`·
   `HwpxDocument.open(..., seed=, now=)` 는 새 id와 날짜를 정해진 값으로 만들어, 같은 코드가 어느
   프로세스에서나 같은 바이트를 쓴다. 주지 않으면 id는 무작위다.
   `tests/test_deterministic_creation.py::test_two_processes_with_seed_and_now_write_identical_parts`,
   `tests/test_deterministic_creation.py::test_open_with_seed_makes_edits_deterministic`
8. **실패는 `HwpxError` 다.** 공개 경로의 실패는 `hwpx.errors.HwpxError` 계열(대체한 내장 예외도
   함께 상속)로 나가고 `code`·`suggestion` 을 싣는다. 잘못된 타입의 인자도 내장
   `TypeError`·`AttributeError` 가 그대로 새지 않는다(운영체제·손상 패키지 실패는 아래
   「오류 계약」대로).
   `tests/test_error_contract.py::test_the_public_path_raises_no_bare_builtins`,
   `tests/test_argument_type_holes.py::test_a_wrong_argument_fails_typed_and_catchable`
9. **공개 이름은 다음 major까지 얼린다.** 7.0의 공개 이름(루트 표면과 `hwpx.model` 의 계약
   멤버)은 8.0 전에는 지우거나 바꾸지 않는다. 락 파일과 다르면 테스트가 실패한다.
   `tests/test_document_facade_surface.py::test_document_facade_public_surface_is_frozen`,
   `tests/test_engine_surface_6_0.py::test_model_surface_lock_matches_the_live_classes`

## stable (29)

major 경계에서만 깨지는 이름들입니다. 7.0에서 7개(`HwpxMarkdownConverter`, 메일 머지 4개,
`inspect_reference_consistency`, `REFERENCE_CONSISTENCY_REPORT_VERSION`)가
`python-hwpx-automation`으로 옮겨 갔습니다. 부르면 새 자리를 알려 주는 `ImportError`가
납니다([7.0 이주 가이드](migration-7.0.md#옮겨-간-기능)).

### 문서 열기·저장·패키지
- `HwpxDocument`, `HwpxPackage`
- `SavePipeline`, `QualityPolicy`, `VisualCompleteReport`
- `MutationReport`, `PreservationDowngradeError`
- `HwpxError` (구조화 예외 베이스 — 아래 오류 계약 참조)
- `Hwp5Error`, `Hwp5ConversionWarning` (HWP 5.0 `.hwp` 읽기와 실험 단계의 쓰기 — 아래 오류 계약 참조)
- `EditorOpenSafetyReport`, `PackageValidationReport`,
  `validate_editor_open_safety`, `validate_package`

### 바이트 보존 패치
- `BytePreservingPatchResult`, `ParagraphTextPatch`, `PatchApplied`,
  `PatchSkipped`, `paragraph_patch`

### 읽기·추출
- `TextExtractor`, `ParagraphInfo`, `SectionInfo`, `DEFAULT_NAMESPACES`
- `ObjectFinder`, `FoundElement`

### 비교
- `doc_diff`, `diff_paragraphs`, `DOC_DIFF_REPORT_VERSION`

### 메타
- `__version__`

## experimental (14)

`from hwpx.experimental import ...`로 사용하세요. 계약이 유동적입니다. 7.0부터 최상위
`hwpx`에서는 가져올 수 없습니다. 문서 ingest 7개(`DocumentIngestor` …)와 미리보기 5개
(`render_layout_preview`, `LayoutPreview`, `PreviewPage`, `render_document_viewer`,
`DocumentViewer`)는 7.0에서 `python-hwpx-automation`(`hwpx_automation.ingest`·
`hwpx_automation.preview`)으로 옮겼습니다.

- **쪽 수 추정**(한/글 없이, `hwpx.layout.pages`): `estimate_pages`, `PageEstimate`,
  `EstimatedLine` — 본문 문단의 줄마다 쪽·단·세로 위치를 추정한다. 따르지 않는 요소가
  있으면 `pages`는 `None`이고 `unsupported`가 까닭을 구역마다 적는다
- **수식 저작**(5.2.0 신규, LaTeX → EqEdit): `latex_to_eqedit`,
  `estimate_equation_size`, `UnsupportedLatexError`. 구현 모듈 `hwpx.equation`에서
  가져와도 같은 객체이고, 사용 가이드와 퀵스타트는 `from hwpx.equation import latex_to_eqedit`를 쓴다
  — 이 세 이름은 5.2.0부터 experimental이었으나 이 문서가 누락하고 있었다
  (자기서술 드리프트 — `describe_capabilities()`의 라이브 census가 이제 이런
  누락을 구조적으로 막는다)
- **편집 계획 실행기**(5.6.0 신규, `hwpx.plan`): `apply_edit_plan`,
  `validate_edit_plan`, `EditPlan`, `PlanReport`, `PlanValidationError`
- **기계가독 자기서술**(5.6.0 신규, `hwpx.capabilities`):
  `describe_capabilities`, `contract_document`, `contract_json_schema`

## 7.0: 엔진의 공개 읽기 (모듈 경로로 import)

7.0은 변환·짐작 기능(Markdown·HTML 내보내기, ingest, 메일머지, 미리보기 …)을
`python-hwpx-automation`으로 옮겼다. 옮겨 간 코드는 이 문서의 계약만 쓴다. 그 코드가
쓰던 엔진 기능 가운데 엔진으로서 뜻이 있는 것을 아래 이름으로 계약에 올렸다. 최상위
`from hwpx import ...`에는 넣지 않고, 적힌 모듈 경로에서 가져온다. `hwpx.oxml.*`의 다른
이름은 이 목록에 없으면 계약이 아니다(경로는 열려 있다). 미리보기의 MathML 변환이 쓰는
`EQEDIT_MATHML_OPERATOR_COMMANDS`는 `hwpx.equation`에서 가져온다.

**stable** — major 경계에서만 바뀐다.

| 이름 | 모듈 | 하는 일 |
|---|---|---|
| `Paragraph.clear_layout_cache() -> int` | `hwpx.model` | 문단(과 그 문단을 담은 문단)의 줄 배치 캐시를 지운다. XML을 직접 고친 뒤 부른다 |
| `Paragraph.available_width -> int \| None` | `hwpx.model` | 문단이 쓸 수 있는 폭(HWPUNIT): 칸이면 칸 너비 − 안 여백, 본문이면 본문 폭(다단이면 단 폭) |
| `doc.styles.outline_style(level) -> Style \| None` | 문서 | 개요 N 수준의 스타일(`add_heading`이 고르는 것) |
| `doc.styles.outline_level(style) -> int \| None` | 문서 | 스타일이 개요 스타일이면 그 수준 |
| `ListLabels(doc)` · `.label(paragraph) -> str` · `.kind(paragraph)` | `hwpx.tools.exporter` | 한/글이 문단 앞에 그리는 번호·글머리(`"1."`, `"가."`, `"●"`) |
| `NoteLabels(doc)` · `.label(note) -> str` | `hwpx.tools.exporter` | 각주·미주 번호(`"1)"`) |
| `number_text(value, number_format) -> str \| None`, `NUMBER_TEXT_FORMATS` | `hwpx.tools.exporter` | 수를 한/글 번호 형식으로(`3, "HANGUL_SYLLABLE"` → `"다"`) |
| `table_grid_text(table, *, tab_token) -> tuple[tuple[str, ...], ...]` | `hwpx.tools.exporter` | 표의 칸 글을 열 격자에(한/글 텍스트 저장과 같은 칸 글) |
| `text_element_content(element, *, tab_token) -> str` | `hwpx.oxml.run` | `hp:t` 요소의 글(안의 탭·줄바꿈·특수 공백 포함) |
| `heading_outline_level(para_pr)`, `outline_style_level(name)`, `paragraph_heading(para_pr)` | `hwpx.oxml.paragraph_heading` | 문단 모양의 개요 수준, 개요 스타일 이름(`개요 N`/`Outline N`)의 수준 |
| `hyperlink_target(field_begin) -> str` | `hwpx.oxml.hyperlink_form` | 하이퍼링크 필드가 가리키는 곳(`Paragraph.hyperlinks`의 `url`과 같다) |
| `cell_margins_of(cell_element, table_element)` | `hwpx.oxml.table_sizes` | `hp:tc` 요소의 실제 안 여백(`TableCell.margins`와 같다) |
| `PAGE_PORTRAIT`, `PAGE_LANDSCAPE` | `hwpx.oxml.section_format` | `hp:pagePr@landscape`의 세로(`WIDELY`)·가로(`NARROWLY`) 값 |
| `HP`·`HH`·`HC`·`HS`·`qn`·`tag_local_name` 등 | `hwpx.oxml.namespaces` | OWPML 이름공간과 태그 도우미 |
| `__all__`의 이름(`guard_zip_file`, `read_member`, `read_zip_members`, `parse_xml_stdlib`, `guard_xml_bytes`, `guard_xml_depth`, `ZipGuardLimits`, `HwpxSecurityError`, `MAX_*`) | `hwpx.opc.security` | HWPX 바이트를 엔진과 같은 상한으로 여는 입력 방어. 상한 값(`MAX_*`)은 보안을 위해 minor에서 좁아질 수 있다 |

XML 요소를 받는 함수(`text_element_content`, `paragraph_heading`, `hyperlink_target`,
`cell_margins_of` …)는 lxml과 표준 `ElementTree` 요소를 모두 받는다. `ListLabels`·
`NoteLabels`·`table_grid_text`는 모델 객체(문단·각주·표)와 그 XML 요소를 모두 받고, 문단은
`doc.paragraphs`의 번호로도 받는다.

**stable 서명, 값은 실측에 따라** — 이름·인자·반환 형식은 major에서만 바뀐다. 돌려주는
수치는 한/글 실측에 맞춰 minor에서 달라질 수 있다(측정이 더 맞아지는 것은 고침이다).

| 이름 | 모듈 |
|---|---|
| `char_advance`, `estimate_text_width`, `indented_widths`, `text_style_from_refs`, `TextStyle` | `hwpx.form_fit` (`hwpx.form_fit.measure`) |
| `resolve_slot_metrics`, `SlotMetrics`, `FitEngine`, `FitPolicy`, `FitResult` | `hwpx.form_fit` |

**experimental** — minor에서 바뀔 수 있다.

| 이름 | 모듈 | 하는 일 |
|---|---|---|
| `input_file_problem(path, *, tool, accepts_hwp=False) -> str \| None` | `hwpx.tools.archive_cli` | 명령줄 도구가 그 경로를 읽을 수 없는 까닭 한 줄(없는 파일, 폴더, HWP 3, HWP 5를 HWPX만 읽는 도구에) |

## 5.0에서 제거된 deprecated 표면 (4)

대체 = **구조적 form-fill 경로**(라이브러리 `hwpx.table_patch.fill_cells` 계열,
MCP `analyze_form_fill`/`apply_form_fill`/`verify_form_fill`).

- `analyze_template_formfit`, `apply_template_formfit`
- `TEMPLATE_FORMFIT_BASELINE_SCHEMA_VERSION`, `TEMPLATE_FORMFIT_PLAN_SCHEMA_VERSION`

## 오류 계약 (4.0.0 도입)

아래 표에 있는 예외 — 쓰기 보존 계약, 저장 경로 게이트, 표 구조 편집, 이동된 표면
안내 — 는 `hwpx.errors.HwpxError`(최상위 `hwpx.HwpxError`로도 import) 베이스를
상속합니다. 모든 호출을 감싸는 포괄 계약은 아닙니다: 없는 파일은
`FileNotFoundError`처럼 파이썬이 원래 내는 예외가 그대로 올라옵니다
([지원 매트릭스](support-matrix.md) 참조).

손상된 HWPX를 열 때(`HwpxDocument.open`, `HwpxPackage.open`)의 예외는 모두
`hwpx.opc.package.HwpxStructureError`의 하위 클래스이면서, 파이썬·lxml이 원래 내던
예외이기도 합니다. 그래서 `except zipfile.BadZipFile` 같은 기존 처리는 그대로 잡고,
`except HwpxStructureError` 하나로 "손상된 파일"을 모두 잡을 수도 있습니다. 원래
예외는 `__cause__`에 있습니다.

| 입력 | 예외 | 함께 상속 |
|---|---|---|
| ZIP이 아님·잘린 파일·빈 파일 | `HwpxArchiveError` | `zipfile.BadZipFile` |
| 압축 데이터 손상 | `HwpxCompressedDataError` | `zlib.error` |
| 깨진 XML 파트, 암호가 걸린 HWPX | `HwpxXmlSyntaxError`(`part_name`) | `lxml.etree.XMLSyntaxError` |
| `mimetype`·`container.xml`·rootfile 없음 | `HwpxStructureError` | — |

`HwpxPackageError`·`HwpxStructureError` 계열은 `HwpxError`를 상속하지 않습니다
(`code`·`context`·`suggestion` 필드가 없습니다). 크기·압축률 상한을 넘는 입력은
`HwpxSecurityError`(`ValueError`)로 거부합니다.
구조화된 예외는 사람용 문장(`str(exc)`)을 그대로 두고, 세 가지 **기계가 읽는**
필드를 얹습니다:

| 속성 | 의미 |
|---|---|
| `code` | 실패 종류의 안정 식별자(kebab-case). 분기 가능하며 major 경계에서만 바뀜. |
| `context` | 실패를 유발한 **실측 값** 딕셔너리(오프닝 part·인덱스·개수…). 없으면 `{}`. |
| `suggestion` | 실행 가능한 다음 한 단계, 없으면 `None`. |

`exc.to_dict()`는 `{code, message, context, suggestion}` 봉투를 돌려줍니다.

### 상속으로 하위 호환 유지

구조화 이전에도 각 예외는 `ValueError`/`RuntimeError`/`Exception`이었고, 4.0.0과
5.0.0 모두 그 관계를 유지합니다 — 기존 `except`가 깨지지 않습니다.

| 예외 | `code` | 상속 | 발생 경로 |
|---|---|---|---|
| `PreservationDowngradeError` | `preservation-downgrade` | `HwpxError` | `save_to_path`/`save_to_stream`/`to_bytes`의 `mode="patch"` + `fallback="error"` 미달 |
| `hwpx.errors.SaveError` | `save-failed`(기본), `document-validation-failed`·`open-safety-failed`·`quality-gate-failed` | `HwpxError`, `ValueError` | 대표 저장 경로의 사전검증·open-safety·품질 게이트 실패 |
| `hwpx.table_patch.TableStructureError` | `table-structure` | `HwpxError`, `ValueError` | 표 구조 편집 거부(fail-closed)·미지원 |
| `hwpx.table_patch.RenderCheckRequired` | `render-check-required` | `HwpxError`, `RuntimeError` | `verify_fill(require=True)`인데 실한컴 오라클 미렌더 |
| `Hwp5Error` | `hwp5-damaged`(기본)·`hwp5-password`·`hwp5-distribution`·`hwp5-drm`·`hwp5-not-hwp5`·`hwp5-version-unsupported`·`hwp5-limit-exceeded`·`hwp5-write-unsupported`·`hwp5-overwrite-source`·`hwp5-write-lossy-source` | `HwpxError`, `ValueError` | `.hwp` 열기(`HwpxDocument.open`)와 HWP 5.0 쓰기(`save_to_path("x.hwp")`, `format="hwp"`) |
| `hwpx.equation.EquationConversionError` | `equation-conversion` | `HwpxError`, `ValueError` | 한글 수식 스크립트 ↔ LaTeX 변환 실패 |
| `hwpx.equation.authoring.UnsupportedLatexError` | `equation-latex-unsupported` | `EquationConversionError` | 검증된 집합 밖의 LaTeX 명령 |
| `hwpx.tools.recover.RecoverError` | `recover-unsafe` | `HwpxError`, `ValueError` | 로컬 헤더 항목을 안전하게 복구할 수 없음 |
| `hwpx.tools.toc_fidelity.WordBoxExtractorRequired` | `toc-word-box-extractor-required` | `HwpxError`, `RuntimeError` | PDF 글자 상자 추출기 없이 차례 쪽 대조 호출 |

### HWP 5.0 (`.hwp`)

`HwpxDocument.open`은 `.hwp`(HWP 5.0)도 열어 같은 문서 모델로 바꿉니다. 옮기지 못한
내용은 읽기 전용 `document.conversion_report`(`unconverted`·`dropped` 개수)에 남고,
`unconverted`가 있으면 `Hwp5ConversionWarning`을 한 번 냅니다. `.hwpx`로 연 문서에서는
`conversion_report`가 `None`입니다. `save_to_path("x.hwp")`, `save_to_stream(..., format="hwp")`,
`to_bytes(format="hwp")`는 HWP 5.0으로 씁니다(실험). 쓸 수 없는 내용이 있으면 아무것도 쓰기 전에
`Hwp5Error`(`hwp5-write-unsupported`)로 거부합니다. 문서를 연 원본 `.hwp` 경로에는 쓰지 않고
(`hwp5-overwrite-source`), `conversion_report`가 비어 있지 않은 문서도 `.hwp`로 쓰지 않습니다
(`hwp5-write-lossy-source`). 두 경우 모두 `.hwpx`로 저장하면 됩니다. `format`에 `"hwpx"`·`"hwp"` 밖의 값을
주면 `hwpx.errors.HwpxValueError`(`save-format-unsupported`)입니다.

응용 계층의 agent·exam 오류 계약은 `python-hwpx-automation`이 소유합니다.
이 문서는 core에 실제로 남은 공개 예외만 기술합니다.

## 스키마 동결 정책

core가 발행하는 versioned contract(`hwpx.mutation-report/v1`)는 required 필드
집합이 **동결**됩니다. document-plan·agent-batch·mixed-form-plan 스키마는 5.0에서
`python-hwpx-automation`이 발행 주체가 됐으며 그쪽 계약 정책을 따릅니다. 정책·계약 테스트는 [스키마 동결](schema-freeze.md)을 보세요.

## 기존 도형과 페이지 story 편집

`Shape.set_position(horizontal_offset=..., vertical_offset=...)`는 기존 떠 있는
도형의 `hp:pos` 오프셋을 바꿉니다(단위 HWPUNIT, signed 32-bit 정수).
`horz_rel_to`·`vert_rel_to`·`horz_align`·`vert_align`을 주면 `hp:pos`의
`horzRelTo`·`vertRelTo`·`horzAlign`·`vertAlign`도 씁니다. 값은 OWPML 스키마
철자 그대로(대문자, 정확히 일치)입니다 — `horz_rel_to`는 `PAPER`/`PAGE`/`COLUMN`/
`PARA`, `vert_rel_to`는 `PAPER`/`PAGE`/`PARA`(스키마에 세로 `COLUMN`은 없습니다),
`horz_align`은 `LEFT`/`CENTER`/`RIGHT`/`INSIDE`/`OUTSIDE`, `vert_align`은 `TOP`/
`CENTER`/`BOTTOM`/`INSIDE`/`OUTSIDE`. 예를 들어 `PAPER`는 용지 가장자리를 기준으로
삼으므로 확인 도장을 쪽 여백에 고정할 수 있습니다. 주지 않은 값(`None`)은 그대로
두므로, 오프셋만 주는 호출은 이전과 같은 결과를 냅니다. 앵커·기하 정보는
보존합니다. 모든 인자는 변경 전에 검사합니다 — 글자처럼 배치된 개체, 위치 요소가
없는 개체는 `shape-position-unsupported`, 잘못된 오프셋은 `shape-position-value`,
스키마 밖의 프레임·정렬 값은 `shape-position-frame`으로 거부합니다. 이동 후 실제
배치는 한컴으로 확인해야 합니다. 7.0부터 `Shape.set_position`은 `InlineObject.set_position`과
같은 호출입니다 — `treat_as_char=`(글자처럼↔떠 있음)와 `text_wrap=`도 받고, 오프셋은 생략할 수
있으며, 문단의 줄 배치 캐시를 지웁니다. 글자처럼 놓인 채 오프셋을 주면 여전히
`shape-position-unsupported`입니다.

### 개체의 생명주기·배치·수식 (7.0)

`model.InlineObject`(그림·수식·차트·OLE)와 `model.Shape`(선·사각형·타원·호·다각형·곡선·
연결선·글상자·묶음)는 같은 배치 어휘를 갖습니다 — 읽기 `position`(`hwpx.objects.ObjectPosition`:
`set_position`이 받는 이름 그대로), `z_order`/`set_z_order`, `rotation`/`set_rotation`,
`description`/`set_description`(`hp:shapeComment`, 대체 글), `caption`, 그리고 `remove()`.
`remove()`는 `table.remove()`와 같은 규칙입니다 — 문단은 남고(다른 것이 없으면 빈 줄),
빈 run은 빠지며, 문단과 그 문단을 품은 문단의 줄 배치 캐시를 지웁니다. 붙어 있던 연결선은
끝점을 그대로 두고 연결을 놓습니다(`subjectIDRef="0"`). 그림의 이진 항목은 패키지에 남으니
`doc.media.remove_unused_images()`로 정리합니다. 묶음 안의 개체는 혼자 지우거나 돌리거나
설명을 달 수 없습니다(`shape-group-member-unsupported`). `set_rotation`은 한/글 저장본이 보여 주는
관계(상자 `hp:sz`는 돈 개체를 감싸는 상자, 개체는 그 가운데로 옮겨 자기 가운데를 축으로 돈다)를
그대로 쓰며, 그 관계가 확인되지 않은 경우 — 늘이거나 줄인 개체(`hc:scaMatrix`가 항등이 아님,
`resize`한 그림 포함), 뒤집은 개체, 묶음, 글자가 든 도형(한/글은 글을 돈 도형이 아니라 감싸는
상자에 가로로 놓아 글이 도형 밖으로 나온다) — 는 `shape-rotation-unsupported`로 거부합니다. 각도 0으로
되돌리는 것은 언제나 됩니다.

`InlineObject.width`/`height`/`resize(width=None, height=None)`와 `Shape.resize`는 하나만 주면
가로세로 비율을 지킵니다. `model.Picture`(`add_picture`·`doc.media.pictures`가 돌려줌)는
`item_id`, `original_size`(`hp:imgDim`), `crop`/`set_crop((left, top, right, bottom))`와
`add_picture`가 쓰는 값의 읽기(`brightness`·`contrast`·`effect`·`alpha`·`line_color`·`line_width`·
`shadow`·`glow`)를 더합니다. `Shape`에는 `line_width`·`fill_color` 읽기가 더해졌습니다.
`model.Equation`(`add_equation`·`paragraph.equations`·`doc.shapes.equations`)은 `script`, `font`,
`base_unit`, `base_line`, `set_script(script)`(상자를 `add_equation`처럼 다시 잽니다)를 더합니다.
`Paragraph.objects`/`pictures`/`equations`는 그 문단의 run이 품은 개체를 순서대로,
`Shape.members`는 묶음의 구성원을 모델 객체로 돌려줍니다.

### 개체·표·문단·메모 옮기기와 복사 (7.0)

`InlineObject`·`Picture`·`Equation`·`Shape`·`Table`의 `move_to(paragraph, *, offset=None)`는 개체를
같은 문서의 다른 문단(본문·표 칸·글상자·각주·미주·머리말·꼬리말)으로 옮기고,
`copy_to(paragraph, *, offset=None)`는 복사본을 넣어 그 모델 객체를 돌려줍니다. `paragraph`는 문단
객체나 `doc.paragraphs`의 번호, `offset`은 `paragraph.text`와 같은 규칙으로 센 글자 위치(`None`은
끝)이고, 개체는 그 글자 앞, 그 자리에 이미 있는 컨트롤·개체 뒤에 놓입니다(글 노드 한가운데면 노드를
나누어 같은 run 안에). 옮긴 개체는 id·캡션·내용을 지키고 원래 자리는 `remove()`처럼 정리됩니다(빈
run, 붙어 있던 연결선은 연결을 놓음). 복사본은 개체·표·문단·누름틀 id를 새로 받고(묶음 구성원의
`id="0"`은 그대로), 그림은 같은 이진 항목을 함께 쓰며, 그 안에 걸린 메모는 다음 번호를 받은 메모가
따로 생깁니다. 두 문단과 그 문단의 칸·캡션을 품은 문단은 줄 배치 캐시를 잃습니다.

떠 있는 개체는 기준과 오프셋을 파일에 적힌 그대로 가져가고, 엔진이 몰래 바꾸지 않습니다 — 문단
기준(`PARA`·`COLUMN`)이면 새 문단을 따라가고, 쪽·용지 기준(`PAGE`·`PAPER`)이면 쪽 위의 자리가 그대로라
새 문단이 놓인 쪽만 따라갑니다. 그래서 같은 쪽 안에서 쪽·용지 기준 개체를 `copy_to`하면 사본이 원본과
정확히 같은 자리에 겹쳐 그려지고, `move_to`해도 제자리입니다. 다른 자리에 두려면 `set_position`으로
옮깁니다. 한/글 문서가 그런 개체를 두지 않는 곳은 바꾸기 전에 `shape-move-place-unsupported`로
거부합니다: 표 칸·글상자·각주로는 문단에서 세로로 재고(`vertRelTo="PARA"`) 쪽 영역 안에 두거나
(`flowWithText="1"`) 가로도 문단에서 재는(`horzRelTo="PARA"`) 떠 있는 개체만 갑니다(공개 문서 1,304개의
칸 634개 중 633개, 각주 40개·글상자 2개 전부가 이 모양이고, 아닌 그림을 칸에 넣으면 한/글은 위 칸에
겹쳐 그립니다 — 먼저 `set_position(vert_rel_to="PARA", horz_rel_to="PARA")`나 `treat_as_char=True`로
바꿉니다). 쪽 기준 개체를 용지나 여백이 다른 구역으로, 떠 있는 개체를 캡션으로, 어떤 개체든
메모·바탕쪽으로도 거부합니다. 자기 글상자·칸·
캡션으로 옮기기는 `shape-move-into-itself`(복사는 됨), 묶음 구성원은 `shape-group-member-unsupported`,
지운 개체는 `shape-not-in-document`, 다른 문서의 문단은 `paragraph-not-in-document`입니다. 다른
문서로 가져오기는 머리 정의·이진 항목을 함께 옮겨야 하므로 `hwpx.tools.document_merge.insert_document`
(문단 단위)를 씁니다.

`Paragraph.move_after(paragraph)`/`move_before(paragraph)`는 문단 자체를 옮깁니다(복사는
`insert_after`/`insert_before`). id·내용을 지키고, 구역의 첫 문단이면 구역 설정이 다음 문단으로 가고,
구역 첫 문단 앞에 놓이면 구역 설정을 넘겨받습니다. 다른 구역으로 가면 그 문단에 걸린 메모가 새 구역의
메모 묶음으로 따라갑니다. 칸·머리말의 마지막 문단은 `paragraph-remove-last`, 자기 칸 안으로는
`paragraph-move-into-itself`, 메모의 문단은 `paragraph-move-place-unsupported`로 거부합니다.

`Memo.move_to(section, *, index=None)`는 메모를 그 구역의 메모 묶음 `index` 번째로 옮기고(묶음이
없으면 만들고, 비게 된 묶음은 지움), `copy_to(section, *, index=None)`는 새 id의 고리 없는 복사본을
돌려줍니다(`doc.notes.attach`로 겁니다). 메모는 고리(MEMO 누름틀)가 있는 구역에 두므로, 고리가 다른
구역에 있는 메모와 한/글이 누름틀에 담아 둔 메모의 이동은 `note-memo-anchor-elsewhere`입니다.

`doc.tables.with_nested`는 본문의 표와 그 칸 안의 표(중첩 포함)를 표 지도(`doc.tables.map()`)와
같은 순서의 tuple로 돌려줍니다 — `doc.tables.with_nested[i]`가 지도의 `table_index == i`인 표입니다
(공개 문서 786개·표 6,418개에서 지도 순서와 같음). `doc.tables.all`은 본문에 바로 놓인 표만입니다.

`Shape.draw_text`·`set_draw_text`·`remove_draw_text`와 이들이 돌려주는
`model.DrawText`는 stable입니다. `set_draw_text(..., para_pr_id_ref=..., vert_align=...)`는
도형 안 문단의 `paraPrIDRef`와 `hp:subList/@vertAlign`(`TOP`/`CENTER`/`BOTTOM`)을
정합니다. 둘 다 생략하면 이전과 같은 XML이 나옵니다 — 새 글상자는 `paraPrIDRef="0"`·
`CENTER`, 기존 글상자는 제 정렬을 유지합니다. 잘못된 정렬 값은
`shape-draw-text-vert-align`으로 변경 전에 거부합니다.

`SectionProperties.headers`/`footers`와 `get_header`/`get_footer`는 본문 컨트롤에
있는 기존 머리말·꼬리말도 찾습니다. `set_simple_text_preserving`은 빈 문단·빈 run을
유지하면서 단일 표시 텍스트를 수정합니다. 복수 표시 텍스트, 중첩 제어, 중복
identity/적용 범위 충돌은 거부합니다. 새로 만드는 `set_header_text` 등의 경로와
기존 story 보존 편집의 지원 범위를 혼동하지 마세요.

`Table.set_cell_borders(row, col, color="#0055AA", line_type="SOLID")`는 선택한
셀의 네 변 색과 선 종류만 수정합니다. 기존 선 두께·배경·대각선·기타 속성을
복제해 보존하고 동일한 스타일이 있으면 재사용합니다. 공유 원본 스타일은
수정하지 않습니다. 스타일이 없거나 중복되었으면 변경 전에 거부합니다.
전체 스타일을 바꾸려면 기존 `set_cell_border_fill`을 사용하세요.

`TableCell.margins`는 한/글이 셀을 배치하는 안쪽 여백을 `hwpx.objects.CellMargins`
(HWPUNIT)로 돌려줍니다. 셀의 `hasMargin`이 꺼져 있으면 표의 `hp:inMargin`,
켜져 있으면 셀의 `hp:cellMargin`입니다. `add_table()`이 만든 셀은
`CellMargins(510, 510, 141, 141)`입니다. `TableCell.set_margins(left=..., right=...,
top=..., bottom=...)`는 주지 않은 면을 지금 여백으로 채워 셀 여백 네 면을 쓰고
`hasMargin`을 켭니다. 값은 `0 <= v < 2**31`인 `int`여야 하며, 아니면 바꾸기 전에
`cell-margin-value`로 거부합니다. 인자가 없으면 아무것도 바꾸지 않습니다.

`Table.insert_rows(ref_row, count=1, side="below", blank=False)`,
`insert_columns(ref_col, count=1, side="right", blank=False)`, `delete_rows(rows)`,
`delete_columns(cols)`, `split_cell(row, col, rows=1, cols=1)`은 행·열을 넣고 지우고 칸을
나눕니다. `hwpx.table_patch.apply_table_ops`의 같은 편집과 같은 규칙(한/글의 줄/칸
추가하기·지우기, 셀 나누기)을 따르고, 새 칸은 기준 칸의 글을 복제하며 `blank=True`면
빈 문단 하나만 둡니다. 거부하면 `TableStructureError`를 내고 표를 바꾸지 않습니다.
편집 전에 얻은 셀·행 객체는 표에 속하지 않으니 다시 얻으세요.

표의 모양과 크기는 7.0 에서 한 줄로 읽고 쓴다. `TableCell.vert_align`/`set_vert_align("CENTER")`
(칸 세로 정렬), `Table.alignment`/`set_alignment("CENTER")`(글자처럼 취급한 표는 그 문단의
정렬, 떠 있는 표는 `hp:pos/@horzAlign`), `Table.width`/`set_width(w, proportional=True)`,
`column_widths`·`row_heights`(격자 열 폭·행 높이 tuple), `set_column_width(col, w)`·
`set_row_height(row, h)`, `Table.columns`(`TableColumn`: `index`·`cells`·`width`·`set_width`),
`TableRow.index`·`height`·`set_height`, `cells_in("A1:C2")`, `set_borders(cell_range, sides=,
line_type=, width_mm=, color=, inner=)`·`set_shading(cell_range, color=)`(칸의 다른 변·대각선·
배경은 그대로 두고 그 칸의 테두리 정의에서 파생), `TableCell.border_fill`(`BorderFillInfo`),
`header_rows`/`set_header_rows(n, repeat=True)`·`repeat_header`·`TableCell.is_header`/`set_header`,
`page_break`/`set_page_break("CELL")`, `no_adjust`/`set_no_adjust`, `in_margins`/`set_in_margins`,
`text_wrap`·`set_position(...)`(개체와 같은 배치 어휘), `cell_zones`(`hwpx.objects.CellZone`),
`TableCell.clear()`, `copy_after(paragraph=None)`(새 id 로 복사). 길이는 모두 HWPUNIT,
선 굵기만 `_mm` 이다.
