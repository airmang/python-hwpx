# 안정 API 표면 (Stable API)

`from hwpx import ...` 최상위 표면은 세 계층으로 나뉩니다. 계층에 따라 계약의
강도와 변경 예고 방식이 다릅니다.

## 계층 정책

- **stable** — `hwpx.__all__`에 있는 이름. 계약(시그니처·동작·반환 스키마)이 굳어
  있고, **major 경계에서만** 깨질 수 있습니다. 접근 시 경고가 없습니다.
- **experimental** — 계약이 **유동적**입니다. minor 릴리스에서 변경될 수 있으므로
  `from hwpx.experimental import ...`로 import하세요. 최상위 `from hwpx import ...`
  경로도 하위 호환을 위해 유지하지만 접근 시 `DeprecationWarning`이 나며, **다음
  major에서 최상위 재내보내기가 제거**될 예정입니다(실제 구현 모듈·`hwpx.experimental`
  경로는 유지).
- **deprecated** — 대체 경로로 이전하세요. 접근 시 `DeprecationWarning`이 나고 경고
  메시지에 대체 경로가 포함됩니다. **다음 major에서 제거**될 예정입니다.

### 최소 deprecation window

이름을 제거하려면 **먼저 한 번의 major에서 `DeprecationWarning`을 낸 뒤** 그다음
major에서 제거합니다(경고 없는 즉시 제거 금지). 4.0.0에서 제거되는 이름은 **0개**
입니다 — 기존 최상위 이름은 전부 계속 import 가능하며, 비-stable 이름만 경고를 냅니다.

### 지원되지 않는(비공개) 표면

`hwpx.oxml.*`, `hwpx._document.*` 등 내부 XML/구현 모듈을 직접 import하는 것은
**공개 표면이 아닙니다**. 이 경로들은 예고 없이 바뀔 수 있으니 위 계층의 이름만
사용하세요.

## stable (67)

major 경계에서만 깨지는 이름들입니다.

### 문서 열기·저장·패키지
- `HwpxDocument`, `HwpxPackage`
- `SavePipeline`, `QualityPolicy`, `VisualCompleteReport`
- `MutationReport`, `PreservationDowngradeError`
- `HwpxError` (구조화 예외 베이스 — 아래 오류 계약 참조)
- `EditorOpenSafetyReport`, `PackageValidationReport`,
  `validate_editor_open_safety`, `validate_package`

### 바이트 보존 패치
- `BytePreservingPatchResult`, `ParagraphTextPatch`, `PatchApplied`,
  `PatchSkipped`, `paragraph_patch`

### 문서 생성(plan) · authoring
- `DocumentPlan`, `DocumentBlock`, `DocumentStylePreset`, `DEFAULT_STYLE_PRESET`
- `create_document_from_plan`, `normalize_document_plan`, `validate_document_plan`,
  `get_document_plan_schema`
- `PlanValidationReport`, `PlanValidationIssue`
- `inspect_document_authoring_quality`, `inspect_operating_plan_quality`
- `approval_box`
- `AUTHORING_REPORT_VERSION`, `DOCUMENT_PLAN_SCHEMA_VERSION`

### 읽기·추출
- `TextExtractor`, `ParagraphInfo`, `SectionInfo`, `DEFAULT_NAMESPACES`
- `ObjectFinder`, `FoundElement`
- `HwpxMarkdownConverter`

### 스타일 프로필·템플릿
- `extract_style_profile`, `apply_style_profile_to_plan`, `compare_style_profiles`,
  `placeholder_fill_report`
- `describe_template`, `list_templates`, `register_template`
- `STYLE_PROFILE_SCHEMA_VERSION`, `STYLE_PROFILE_COMPARISON_SCHEMA_VERSION`,
  `TEMPLATE_REGISTRY_SCHEMA_VERSION`

### 비교·메일머지·표 계산·공문 린트·고급 생성기
- `doc_diff`, `diff_paragraphs`, `build_comparison_table_plan`,
  `inspect_reference_consistency`
- `mail_merge`, `load_mail_merge_rows`, `inspect_mail_merge_placeholders`
- `table_compute`
- `inspect_official_document_style`
- `build_image_grid`, `build_meeting_nameplates`, `build_organization_chart`
- `DOC_DIFF_REPORT_VERSION`, `REFERENCE_CONSISTENCY_REPORT_VERSION`,
  `MAIL_MERGE_REPORT_VERSION`, `TABLE_COMPUTE_REPORT_VERSION`,
  `OFFICIAL_DOCUMENT_STYLE_REPORT_VERSION`

### 메타
- `__version__`

## experimental (12)

`from hwpx.experimental import ...`로 사용하세요. 계약이 유동적입니다.

- **문서 ingestion 프레임워크**(임의 포맷 → HWPX): `DocumentIngestor`,
  `DocumentConverter`, `DocumentIngestResult`, `DocumentSourceInfo`,
  `ConversionAttempt`, `DocumentIngestError`, `UnsupportedDocumentFormat`
- **레이아웃 프리뷰**(한컴 없는 정직 근사): `render_layout_preview`,
  `LayoutPreview`, `PreviewPage`
- **문서 프리뷰 뷰어**(3.8.0 신규): `render_document_viewer`, `DocumentViewer`

> `HwpxMarkdownConverter`(HWPX → Markdown 읽기)는 성숙한 경로라 **stable**입니다.
> 위 ingestion 프레임워크(임의 포맷 → HWPX)만 experimental입니다.

## deprecated (4)

대체 = **구조적 form-fill 경로**(라이브러리 `hwpx.table_patch.fill_cells` 계열,
MCP `analyze_form_fill`/`apply_form_fill`/`verify_form_fill`).

- `analyze_template_formfit`, `apply_template_formfit`
- `TEMPLATE_FORMFIT_BASELINE_SCHEMA_VERSION`, `TEMPLATE_FORMFIT_PLAN_SCHEMA_VERSION`

## 오류 계약 (4.0.0 신규)

fail-closed 공개 경로가 던지는 예외는 `hwpx.errors.HwpxError`(최상위 `hwpx.HwpxError`
로도 import) 베이스를 상속합니다. 사람용 문장(`str(exc)`)은 그대로 두고, 세 가지
**기계가 읽는** 필드를 얹습니다:

| 속성 | 의미 |
|---|---|
| `code` | 실패 종류의 안정 식별자(kebab-case). 분기 가능하며 major 경계에서만 바뀜. |
| `context` | 실패를 유발한 **실측 값** 딕셔너리(오프닝 part·인덱스·개수…). 없으면 `{}`. |
| `suggestion` | 실행 가능한 다음 한 단계, 없으면 `None`. |

`exc.to_dict()`는 `{code, message, context, suggestion}` 봉투를 돌려줍니다.

### 상속으로 하위 호환 유지

구조화 이전에도 각 예외는 `ValueError`/`RuntimeError`/`Exception`이었고, 4.0.0에서도
그 관계를 유지합니다 — 기존 `except`가 깨지지 않습니다.

| 예외 | `code` | 상속 | 발생 경로 |
|---|---|---|---|
| `PreservationDowngradeError` | `preservation-downgrade` | `HwpxError` | `save_to_path`/`save_to_stream`/`to_bytes`의 `mode="patch"` + `fallback="error"` 미달 |
| `hwpx.errors.SaveError` | `save-failed`(기본), `document-validation-failed`·`open-safety-failed`·`quality-gate-failed` | `HwpxError`, `ValueError` | 대표 저장 경로의 사전검증·open-safety·품질 게이트 실패 |
| `hwpx.table_patch.TableStructureError` | `table-structure` | `HwpxError`, `ValueError` | 표 구조 편집 거부(fail-closed)·미지원 |
| `hwpx.table_patch.RenderCheckRequired` | `render-check-required` | `HwpxError`, `RuntimeError` | `verify_fill(require=True)`인데 실한컴 오라클 미렌더 |

이번 major에서 **공개 계약 경로부터** 이행했습니다. 도메인 하위 시스템(agent
`AgentContractError`/`AgentError`는 이미 code·suggestion을 별도로 보유, exam·equation
등)의 나머지 raise 사이트는 §11(대규모 일괄 개조 금지) 정신에 따라 후속으로 남깁니다.

## 스키마 동결 정책

published versioned contract(`hwpx.mutation-report/v1`·`hwpx.document_plan.v1`/`v2`·
`hwpx.agent-batch/v1`·`hwpx.mixed-form-plan/v1`)는 4.0.0에서 **required 필드 집합이
동결**됩니다. 정책·계약 테스트는 [스키마 동결](schema-freeze.md)을 보세요.
