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

## stable (66)

major 경계에서만 깨지는 이름들입니다.

### 문서 열기·저장·패키지
- `HwpxDocument`, `HwpxPackage`
- `SavePipeline`, `QualityPolicy`, `VisualCompleteReport`
- `MutationReport`, `PreservationDowngradeError`
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
